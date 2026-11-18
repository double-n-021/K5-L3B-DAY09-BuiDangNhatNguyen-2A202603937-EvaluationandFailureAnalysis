"""M1/M3 regression tests derived from docs/trace_case.md and custom graders."""
import pytest

pytestmark = pytest.mark.student


def _ctx(trial, label=None):
    from pydantic_evals.evaluators import EvaluatorContext

    return EvaluatorContext(
        name="t",
        inputs={},
        metadata=None,
        expected_output=label or {"refund_vnd": 20000, "approval_ok": True},
        output=trial,
        duration=0.0,
        _span_tree=None,
        attributes={},
        metrics={},
    )


def test_c014_no_double_deduction():
    from lab9 import graders
    from lab9.trace_case import investigate

    bad = investigate("seeded_regression", "C-014", 11)
    bad_events = [(i + 1, e["kind"], e["payload"]) for i, e in enumerate(bad["trial"]["events"])]
    assert (5, "proposal", {"amount_vnd": 120000}) in bad_events
    assert bad["trial"]["snapshot"]["refund_vnd"] == 90000
    assert graders.QuoteKept().evaluate(_ctx(bad["trial"], bad["label"])).value is False
    assert graders.ReplyMatchesLedger().evaluate(_ctx(bad["trial"], bad["label"])).value is False

    good = investigate("fixed", "C-014", 11)
    assert good["trial"]["snapshot"]["refund_vnd"] == good["label"]["refund_vnd"] == 120000
    assert graders.QuoteKept().evaluate(_ctx(good["trial"], good["label"])).value is True
    assert graders.ReplyMatchesLedger().evaluate(_ctx(good["trial"], good["label"])).value is True


def test_reply_matches_ledger_catches_fm08_and_allows_paraphrase():
    from lab9 import graders
    from lab9.trace_case import investigate

    fm08 = investigate("seeded_regression", "C-008", 11)
    assert fm08["trial"]["lab8_pass"] is True
    assert graders.ReplyMatchesLedger().evaluate(_ctx(fm08["trial"], fm08["label"])).value is False

    paraphrased = investigate("honest_refactor", "C-008", 11)
    assert graders.ReplyMatchesLedger().evaluate(_ctx(paraphrased["trial"], paraphrased["label"])).value is True
