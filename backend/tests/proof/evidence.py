"""The measured-evidence store for the section 10 proof suite.

Design citation: `SOLUTION_DESIGN.md` section 10's own framing -- "This document is not done when
the code compiles. It is done when section 10 passes." GitHub issue #44.

A green tick is not evidence. Whoever reviews an exit gate needs the actual figures -- the 1-of-50
outcome split, which rows the weight invariant returned, how many distinct rankings five identical
searches produced -- not a count of assertions that happened to hold. Each part records the numbers
it has already computed and `conftest.pytest_terminal_summary` prints them as one block.

## Why this is a module of its own and not just a dict in `conftest.py`

`backend/tests/` is not a Python package (no `__init__.py`), so `from tests.proof.conftest import
record_evidence` inside a test module imports a *second copy* of conftest under a different module
name than the one pytest itself loaded -- two separate dicts, and the hook prints the empty one.
Observed exactly that on the first run, 2026-09-01: every part recorded evidence and the summary
block was silently absent. One plain module, imported the same way by both sides, has one dict.
"""

from __future__ import annotations

EVIDENCE: dict[str, object] = {}


def record_evidence(key: str, value: object) -> None:
    """Record one measured figure. Never raises and never affects a test's outcome."""
    EVIDENCE[key] = value
