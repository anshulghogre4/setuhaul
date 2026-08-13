"""Locust Suite A prompts must stay verbatim with the demo runbook."""

from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
LOADTESTS = REPO / "loadtests"
if str(LOADTESTS) not in sys.path:
    sys.path.insert(0, str(LOADTESTS))

from common import CONTEND_CAST, RUNBOOK_PROMPTS  # noqa: E402


def test_locust_prompts_are_verbatim_in_runbook():
    runbook = (REPO / "docs" / "DEMO_MANUAL_RUNBOOK.md").read_text(encoding="utf-8")
    assert RUNBOOK_PROMPTS
    for key, text in RUNBOOK_PROMPTS.items():
        assert text in runbook, f"{key} missing from DEMO_MANUAL_RUNBOOK.md"


def test_contend_cast_is_ten_drivers():
    assert len(CONTEND_CAST) == 10
    assert CONTEND_CAST[0] == ("driver.drv004@setuhaul.com", "SHP-D16-CONTEND-01")
    assert CONTEND_CAST[-1] == ("driver.drv013@setuhaul.com", "SHP-D16-CONTEND-10")
    runbook = (REPO / "docs" / "DEMO_MANUAL_RUNBOOK.md").read_text(encoding="utf-8")
    assert "D16-SLT-RACE" in runbook
    assert "SHP-D16-CONTEND-01..10" in runbook
