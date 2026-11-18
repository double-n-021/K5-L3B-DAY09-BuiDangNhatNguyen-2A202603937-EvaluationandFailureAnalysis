"""M1 regression test derived from docs/trace_case.md (C-014@11 pre_deducted)."""
import pytest

pytestmark = pytest.mark.student


def test_c014_no_double_deduction():
    from lab9.trace_case import investigate

    bad = investigate("seeded_regression", "C-014", 11)
    bad_events = [(i + 1, e["kind"], e["payload"]) for i, e in enumerate(bad["trial"]["events"])]
    assert (5, "proposal", {"amount_vnd": 120000}) in bad_events
    assert bad["trial"]["snapshot"]["refund_vnd"] == 90000
    assert bad["trial"]["snapshot"]["refund_vnd"] != bad["label"]["refund_vnd"]
    assert bad["trial"]["lab8_pass"] is False

    good = investigate("fixed", "C-014", 11)
    assert good["trial"]["snapshot"]["refund_vnd"] == good["label"]["refund_vnd"] == 120000
    assert good["trial"]["lab8_pass"] is True
