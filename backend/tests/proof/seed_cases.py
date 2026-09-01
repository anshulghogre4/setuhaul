"""Mechanical coverage of the database guide's seeded-case table.

Design citation: `SOLUTION_DESIGN.md` section 10.4 -- "Each of the 29 seeded cases in the database
guide section 6 becomes a named test with an expected outcome ... **Coverage is asserted
mechanically: a case with no named test fails the suite, so the mapping cannot silently rot.**"
Also section 9.2. GitHub issue #44.

## The table is parsed, not transcribed

A hand-copied list of case names is exactly the thing section 10.4 says must not exist: it rots the
first time the guide gains, loses or renames a row, and nothing notices. So this module reads
`docs/database_docs/setuhaul_database_guide.md` section 6's markdown table at test time and returns
whatever is actually in it. The registry in `test_part4_scenario_replay.py` is then compared
against that, in both directions.

## A measured discrepancy, recorded here rather than smoothed over

`SOLUTION_DESIGN.md` says **29** cases, twice (section 9.2 and section 10.4). The guide's section 6
table actually contains **30** rows -- counted mechanically, 2026-09-01. Nothing in the design
names which case is the odd one out, so this module does not guess: it returns all 30 and the
coverage test requires a named test for every one. The count is asserted separately so the
discrepancy stays visible instead of being quietly absorbed.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
GUIDE = REPO_ROOT / "docs" / "database_docs" / "setuhaul_database_guide.md"

# `SOLUTION_DESIGN.md`'s stated count, kept as a constant so the mismatch below is a real assertion
# and not a comment someone can ignore.
DESIGN_STATED_CASE_COUNT = 29


@dataclass(frozen=True)
class SeededCase:
    name: str
    what_it_tests: str
    seed_reference: str
    main_tables: str


_SECTION_HEADING = re.compile(r"^##\s+6\.\s", re.MULTILINE)
_NEXT_HEADING = re.compile(r"^##\s+7\.\s", re.MULTILINE)


def load_seeded_cases() -> list[SeededCase]:
    """Every row of the guide's section 6 table, in document order.

    Deliberately strict: a missing guide, a missing section or a malformed table raises rather than
    returning an empty list, because an empty list would make the coverage assertion pass
    vacuously -- the precise failure mode section 10.4 exists to prevent.
    """
    if not GUIDE.is_file():
        raise FileNotFoundError(f"database guide not found at {GUIDE}")
    text = GUIDE.read_text(encoding="utf-8")

    start = _SECTION_HEADING.search(text)
    if start is None:
        raise ValueError("section 6 ('Seeded cases and edge cases') not found in the database guide")
    rest = text[start.end():]
    end = _NEXT_HEADING.search(rest)
    section = rest[: end.start()] if end else rest

    cases: list[SeededCase] = []
    for line in section.splitlines():
        stripped = line.strip()
        if not stripped.startswith("|"):
            continue
        cells = [cell.strip() for cell in stripped.strip("|").split("|")]
        if len(cells) < 4:
            continue
        header_or_rule = cells[0].lower() in {"case", ""} or set(cells[0]) <= {"-", ":"}
        if header_or_rule:
            continue
        cases.append(
            SeededCase(
                name=cells[0],
                what_it_tests=cells[1],
                seed_reference=cells[2].replace("`", ""),
                main_tables=cells[3].replace("`", ""),
            )
        )

    if not cases:
        raise ValueError("section 6's case table parsed to zero rows; the guide's format changed")
    return cases


def seeded_case_names() -> list[str]:
    return [case.name for case in load_seeded_cases()]
