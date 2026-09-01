"""`get_pending_confirmations` against a real cluster -- GitHub issue #82.

Design citation: `SOLUTION_DESIGN.md` §7.3 (*"Queue ordering -- not FIFO"* -- order by composite
urgency: TTL remaining, priority code, and whether the driver is physically waiting at the gate),
§13.1, FR-OPS-002.

**Not a tenth part of §10**, for the same reason parts 7 and 9 are not a seventh and a ninth: §10
defines six parts. This file lives beside them because the one thing it proves cannot be proved by
a mock.

## Why this file exists at all, when `tests/unit/test_escalation_service.py` already covers the
## ordering

Those tests hand the service a hand-built row list, so **the SQL never runs**. Issue #82's change
added two columns and a `LEFT JOIN public.facility_checkins` to the statement, and an unexecuted
statement is precisely the class of defect this repository has already been bitten by: the
`_claim_dock_occupancy` `shipment_id` omission reached a migration dry run undetected because every
test that covered it used a mocked session (`tests/unit/test_held_read_paths.py`'s own docstring
says so). A column that does not exist, or a join that fans a row out, fails here and nowhere else.

The seed clone is used rather than the work database so the assertions describe the shipped seed
rather than whatever the mutating parts happened to leave behind.
"""

from __future__ import annotations

import pytest

from app.core.clock import FrozenClock
from app.core.execution_context import ExecutionContext, RoleName
from app.scheduling.urgency import urgency_sort_key
from app.services.escalation_service import get_pending_confirmations
from tests.proof.conftest import SEED_DAY
from tests.proof.evidence import record_evidence

pytestmark = pytest.mark.asyncio(loop_scope="session")

FACILITY_ID = "FAC-JAI-01"


def _ops_ctx() -> ExecutionContext:
    """`USR102` / Rahul Verma -- the seed's WAREHOUSE_PLANNER at FAC-JAI-01, an OPS_PORTAL role."""
    return ExecutionContext(
        request_id="proof-p10",
        auth_subject="proof-p10",
        user_id="USR102",
        email="rahul.verma@setuhaul.com",
        full_name="Rahul Verma",
        role_id="ROL003",
        role_name=RoleName.WAREHOUSE_PLANNER,
        facility_id=FACILITY_ID,
    )


async def test_the_statement_executes_and_returns_the_facilitys_pending_rows(seed_session):
    """The column-existence proof. `s.priority_code` and `fc.queue_state` were added to the SELECT
    by issue #82; if either name were wrong this is an `UndefinedColumn`, not a wrong answer."""
    payload = await get_pending_confirmations(
        seed_session, _ops_ctx(), None, clock=FrozenClock(SEED_DAY)
    )
    record_evidence(
        "10. #82: pending-confirmations read",
        f"{len(payload['items'])} row(s), ordering={payload['ordering']['rule']}",
    )
    assert payload["facility_id"] == FACILITY_ID
    assert payload["ordering"]["rule"] == "composite_urgency"
    assert payload["items"], "the seed has no pending confirmations at FAC-JAI-01 to order"
    for item in payload["items"]:
        assert item["facility_id"] == FACILITY_ID
        # Every term present, so the sort is inspectable rather than magic (§7.3).
        assert set(item["urgency"]) == {
            "score",
            "priority_score",
            "ttl_pressure",
            "waiting_bonus",
        }


async def test_the_join_to_facility_checkins_does_not_fan_a_row_out(seed_session):
    """`facility_checkins` is joined on `shipment_id`, which is not declared unique.

    A second check-in row for one shipment would silently duplicate that appointment in the
    coordinator's list -- the same "a plain join fans the target row out" hazard
    `list_planner_queue_rows` avoids with a LATERAL. One appointment id, one row.
    """
    payload = await get_pending_confirmations(
        seed_session, _ops_ctx(), None, clock=FrozenClock(SEED_DAY)
    )
    ids = [item["appointment_id"] for item in payload["items"]]
    assert len(ids) == len(set(ids)), f"duplicated appointment rows: {ids}"


async def test_the_returned_order_is_the_shared_composite_ordering(seed_session):
    """The ordering itself, over real seeded rows.

    Asserted by re-deriving the key from `scheduling/urgency.urgency_sort_key` -- the same function
    the service sorts with and the same one `get_planner_queue` sorts with -- rather than by
    re-typing an expected sequence. Issue #82's point was one implementation, so a test that
    carried its own copy of the ordering rule would be a third one.
    """
    payload = await get_pending_confirmations(
        seed_session, _ops_ctx(), None, clock=FrozenClock(SEED_DAY)
    )
    keys = [
        urgency_sort_key(item["urgency"]["score"], item["appointment_id"])
        for item in payload["items"]
    ]
    assert keys == sorted(keys), (
        "rows are not in composite-urgency order: "
        f"{[(item['appointment_id'], item['urgency']['score']) for item in payload['items']]}"
    )
    # Not vacuous only if the scores actually differ; recorded either way so a future seed change
    # that flattens them is visible rather than silently making this test prove nothing.
    record_evidence(
        "10. #82: seeded urgency spread",
        ", ".join(f"{i['appointment_id']}={i['urgency']['score']}" for i in payload["items"]),
    )
