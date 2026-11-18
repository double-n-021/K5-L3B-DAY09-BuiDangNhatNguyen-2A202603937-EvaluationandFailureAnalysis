"""CI gate: compare a PR eval report with the main-branch baseline using the metric spec.

    python -m lab9.gate --pr reports/eval_workflow.json --baseline reports/baseline_v1.json

exit 0 = merge, exit 1 = blocked. Safety metrics: max 0, no averaging away.
Capability metrics: meet the floor AND the paired CI of (PR - main) is not entirely below 0.
Thresholds may only get stricter on the same eval-set version (ratchet).
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

from lab8.console import utf8_stdio
from lab9 import stats
from lab9.eval import SPEC, aggregate, load_spec, per_item
from lab9.graders import GRADERS


def _is_bad_number(val: object) -> bool:
    return val is None or (isinstance(val, float) and (math.isnan(val) or math.isinf(val)))


def integrity_check(pr: dict, base: dict, spec: dict, base_spec: dict | None = None) -> list[str]:
    """M7 (Expert): refuse to compare reports that cannot be trusted. Return a list of problems
    (empty = trustworthy). A gate that passes a broken report is worse than no gate."""
    problems: list[str] = []

    if pr.get("evaluator_failures"):
        problems.append(f"PR has {len(pr['evaluator_failures'])} evaluator_failures")
    if base.get("evaluator_failures"):
        problems.append(f"baseline has {len(base['evaluator_failures'])} evaluator_failures")

    pr_metrics = pr.get("metrics") or {}
    for k, v in pr_metrics.items():
        if isinstance(v, float) and (math.isnan(v) or math.isinf(v)):
            problems.append(f"PR metric {k} is NaN or inf")
    for m in spec.get("metrics") or []:
        mid = m["id"]
        if mid not in pr_metrics or _is_bad_number(pr_metrics.get(mid)):
            problems.append(f"PR metric {mid} is missing or NaN/inf")

    pr_manifest = pr.get("manifest") or {}
    base_manifest = base.get("manifest") or {}
    pr_rows = pr.get("rows") or []
    base_rows = base.get("rows") or []

    expected_len = int(pr_manifest.get("items") or 0) * len(pr_manifest.get("seeds") or [])
    if len(pr_rows) != expected_len:
        problems.append(f"PR row count {len(pr_rows)} != manifest items x seeds ({expected_len})")
    if len(pr_rows) != len(base_rows):
        problems.append(f"PR row count {len(pr_rows)} != baseline row count {len(base_rows)}")
    if pr_manifest.get("items") != base_manifest.get("items") or list(pr_manifest.get("seeds") or []) != list(
        base_manifest.get("seeds") or []
    ):
        problems.append("PR manifest items or seeds differ from baseline")

    pr_pairs = [(r.get("item_id"), r.get("seed")) for r in pr_rows]
    base_pairs = [(r.get("item_id"), r.get("seed")) for r in base_rows]
    if len(set(pr_pairs)) != len(pr_pairs):
        problems.append("PR contains duplicate (item_id, seed) rows")
    if set(pr_pairs) != set(base_pairs):
        problems.append("PR (item_id, seed) set differs from baseline")

    row_metric_ids = [
        m["id"]
        for m in (spec.get("metrics") or [])
        if m["id"] in GRADERS or any(m["id"] in r for r in base_rows) or any(m["id"] in r for r in pr_rows)
    ]
    for mid in row_metric_ids:
        for r in pr_rows:
            if mid not in r or _is_bad_number(r.get(mid)):
                problems.append(f"row {r.get('item_id')}@{r.get('seed')} has missing or NaN value for {mid}")
                break

    base_pair_slices = {(r.get("item_id"), r.get("seed")): sorted(r.get("slices") or []) for r in base_rows}
    base_item_slices = {r.get("item_id"): sorted(r.get("slices") or []) for r in base_rows}
    for r in pr_rows:
        pair = (r.get("item_id"), r.get("seed"))
        r_slices = sorted(r.get("slices") or [])
        if pair in base_pair_slices and r_slices != base_pair_slices[pair]:
            problems.append(f"slice tags for {pair[0]}@{pair[1]} differ from baseline")
            break
        if r.get("item_id") in base_item_slices and r_slices != base_item_slices[r.get("item_id")]:
            problems.append(f"slice tags for {r.get('item_id')} differ from baseline")
            break

    if not problems and pr_rows and "cost" in pr_rows[0]:
        if any(_is_bad_number(r.get("cost")) for r in pr_rows):
            problems.append("row has missing or NaN cost")
        else:
            graded_ids = [m["id"] for m in (spec.get("metrics") or []) if m["id"] in GRADERS and m["id"] in pr_rows[0]]
            recomputed = aggregate(pr_rows, graded_ids, k_values=spec.get("pass_k", []))
            for k, exp_v in recomputed.items():
                if k in pr_metrics and exp_v is not None and not _is_bad_number(pr_metrics[k]):
                    if abs(float(pr_metrics[k]) - float(exp_v)) > 1e-3:
                        problems.append(f"metric {k}={pr_metrics[k]} disagrees with recomputed {exp_v} from rows")

    if base_spec is not None and spec.get("eval_set_version") == base_spec.get("eval_set_version"):
        spec_metrics = {m["id"]: m for m in (spec.get("metrics") or [])}
        for bm in base_spec.get("metrics") or []:
            mid = bm["id"]
            if mid not in spec_metrics:
                problems.append(f"ratchet: metric {mid} removed from spec")
                continue
            sm = spec_metrics[mid]
            if bm.get("blocking") and not sm.get("blocking"):
                problems.append(f"ratchet: blocking metric {mid} became non-blocking")
            bth = bm.get("threshold") or {}
            sth = sm.get("threshold") or {}
            if "min" in bth and ("min" not in sth or float(sth["min"]) < float(bth["min"]) - 1e-12):
                problems.append(f"ratchet: metric {mid} min threshold loosened")
            if "max" in bth and ("max" not in sth or float(sth["max"]) > float(bth["max"]) + 1e-12):
                problems.append(f"ratchet: metric {mid} max threshold loosened")
            if "max_increase" in bth and (
                "max_increase" not in sth or float(sth["max_increase"]) > float(bth["max_increase"]) + 1e-12
            ):
                problems.append(f"ratchet: metric {mid} max_increase threshold loosened")
            if bth.get("no_significant_drop") and not sth.get("no_significant_drop"):
                problems.append(f"ratchet: metric {mid} dropped no_significant_drop")

        spec_slices = {(s.get("name"), s.get("metric")): s for s in (spec.get("slices") or [])}
        for bsl in base_spec.get("slices") or []:
            skey = (bsl.get("name"), bsl.get("metric"))
            if skey not in spec_slices:
                problems.append(f"ratchet: slice {skey[0]}/{skey[1]} removed from spec")
                continue
            ssl = spec_slices[skey]
            if bsl.get("blocking") and not ssl.get("blocking"):
                problems.append(f"ratchet: blocking slice {skey[0]}/{skey[1]} became non-blocking")
            if "min" in bsl and ("min" not in ssl or float(ssl["min"]) < float(bsl["min"]) - 1e-12):
                problems.append(f"ratchet: slice {skey[0]}/{skey[1]} min threshold loosened")
            if "max" in bsl and ("max" not in ssl or float(ssl["max"]) > float(bsl["max"]) + 1e-12):
                problems.append(f"ratchet: slice {skey[0]}/{skey[1]} max threshold loosened")
            if bsl.get("no_significant_drop") and not ssl.get("no_significant_drop"):
                problems.append(f"ratchet: slice {skey[0]}/{skey[1]} dropped no_significant_drop")

    return problems


def slice_check(pr: dict, base: dict, spec: dict) -> tuple[list[str], list[str]]:
    """M5 (Advanced): an average can hide a regression on a small, important slice.
    For each entry of spec["slices"] ({"name", "metric", "min"?, "no_significant_drop"?, "blocking"}):
      - value = mean of per_item(pr, metric, slice_name=name)
      - fail if below "min", or if no_significant_drop and the paired CI over the slice's items
        lies entirely below 0
    Return (blocked ids like "slice:money_movement/pass_rate", report lines)."""
    blocked: list[str] = []
    lines: list[str] = []
    bs = spec.get("bootstrap", {})
    for s in spec.get("slices") or []:
        name, mid = s["name"], s["metric"]
        sid = f"slice:{name}/{mid}"
        a = per_item(pr, mid, slice_name=name)
        b = per_item(base, mid, slice_name=name)
        verdict, note = "ok", ""
        if not a:
            val = None
            verdict = "missing"
        else:
            val = round(sum(a.values()) / len(a), 4)
            if "max" in s and val > s["max"]:
                verdict = "fail"
            elif "min" in s and val < s["min"]:
                verdict = "fail"
            if s.get("no_significant_drop"):
                keys = sorted(set(a) & set(b))
                if keys:
                    d, lo, hi = stats.paired_bootstrap(
                        [a[k] for k in keys],
                        [b[k] for k in keys],
                        n_resamples=bs.get("n_resamples", 1000),
                        rng=bs.get("rng", 2027),
                        confidence=bs.get("confidence", 0.95),
                    )
                    note = f"Δ {d:+.3f} CI [{lo:+.3f}, {hi:+.3f}]"
                    if hi < 0:
                        verdict = "fail"
                else:
                    verdict = "missing"
        if verdict != "ok" and s.get("blocking"):
            blocked.append(sid)
        th_view = {k: s[k] for k in ("min", "max", "no_significant_drop") if k in s}
        label = {"ok": "ok", "missing": "MISSING"}.get(verdict, "BLOCK" if s.get("blocking") else "warn")
        lines.append(f"  {sid:<28} {val!s:<8} {json.dumps(th_view):<34} {note:<28} {label}")
    return blocked, lines


def check(pr: dict, base: dict, spec: dict, base_spec: dict | None = None) -> tuple[list[str], list[str]]:
    if pr["manifest"]["eval_set_sha"] != base["manifest"]["eval_set_sha"]:
        return ["eval_set_sha"], ["  EVAL SET differs from the baseline's: re-run the baseline on the same eval set"]
    problems = integrity_check(pr, base, spec, base_spec)
    if problems:
        return ["integrity"], [f"  INTEGRITY {p}" for p in problems]
    blocked, lines = [], []
    bs = spec.get("bootstrap", {})
    for m in spec["metrics"]:
        mid, th, val = m["id"], m.get("threshold", {}), pr["metrics"].get(m["id"])
        verdict, note = "ok", ""
        if val is None:
            verdict = "missing"
        elif "max" in th and val > th["max"]:
            verdict = "fail"
        elif "min" in th and val < th["min"]:
            verdict = "fail"
        elif "max_increase" in th and base["metrics"].get(mid):
            if val > base["metrics"][mid] * (1 + th["max_increase"]):
                verdict = "fail"
        if th.get("no_significant_drop") and val is not None:
            a, b = per_item(pr, mid), per_item(base, mid)
            keys = sorted(set(a) & set(b))
            d, lo, hi = stats.paired_bootstrap([a[k] for k in keys], [b[k] for k in keys],
                                               n_resamples=bs.get("n_resamples", 1000), rng=bs.get("rng", 2027))
            note = f"Δ {d:+.3f} CI [{lo:+.3f}, {hi:+.3f}]"
            if hi < 0:
                verdict = "fail"
        if verdict != "ok" and m.get("blocking"):
            blocked.append(mid)
        label = {"ok": "ok", "missing": "MISSING"}.get(verdict, "BLOCK" if m.get("blocking") else "warn")
        lines.append(f"  {mid:<22} {val!s:<8} {json.dumps(th):<40} {note:<28} {label}")
    if spec.get("slices"):
        sb, sl = slice_check(pr, base, spec)
        blocked += sb
        lines += sl
    return blocked, lines


def main(argv: list[str] | None = None) -> int:
    utf8_stdio()
    ap = argparse.ArgumentParser(prog="lab9.gate")
    ap.add_argument("--pr", required=True)
    ap.add_argument("--baseline", required=True)
    ap.add_argument("--spec", default=str(SPEC))
    ap.add_argument("--base-spec", help="metric spec on main, for the ratchet check (M7)")
    args = ap.parse_args(argv)
    pr = json.loads(Path(args.pr).read_text(encoding="utf-8"))
    base = json.loads(Path(args.baseline).read_text(encoding="utf-8"))
    base_spec = load_spec(Path(args.base_spec)) if args.base_spec else None
    blocked, lines = check(pr, base, load_spec(Path(args.spec)), base_spec)
    print(f"gate: PR {pr['run_id']} vs main {base['run_id']} · eval set {pr['manifest']['eval_set_sha']}")
    print("\n".join(lines))
    if blocked:
        print(f"exit 1 — blocked: {', '.join(blocked)}")
        return 1
    print("exit 0 — merge")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
