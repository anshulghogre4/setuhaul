"""Issue #57 -- the ops co-pilot's resolution-action suggestion.

Three things are actually worth testing here, and the rest is scaffolding around them:

1. **The engine can never recommend an action the server would refuse.** `test_never_recommends_
   an_unavailable_action` walks a matrix of lifecycle states x reasons and asserts the invariant
   over every one of them. This is the property that makes the panel trustworthy: a co-pilot that
   points at a button returning `NOT_OWNER` is worse than no co-pilot.
2. **It abstains rather than inventing.** Six of §7.4's nine reasons have no ops tool that fixes
   them, and each abstains with a named code instead of steering to resolve/cancel.
3. **It writes nothing.** `test_the_suggestion_path_never_writes` asserts no `commit` and no
   non-`SELECT` statement over a full orchestrated call -- structural, not a promise in a comment.

The rule engine is a pure function over a literal dict, so most of this file needs no database
mock at all. Only the orchestration tests mock a session, and they do it with the same sequential
`session.execute` shape `test_e52_coordinator_reply_path.py` established.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.core.errors import AppError
from app.core.execution_context import ExecutionContext, RoleName
from app.services import ops_copilot
from app.services.ops_copilot import (
    ACK,
    CANCEL,
    HAND_BACK,
    POST_MESSAGE,
    REASSIGN,
    RESOLVE,
    SEQUENCER,
    START,
    TAKE_OVER,
    build_suggestion,
    get_resolution_suggestion,
)

FACILITY = "FAC-JAI-01"
OTHER_FACILITY = "FAC-GGN-01"
ME = "USR-OPS-1"
SOMEONE_ELSE = "USR-OPS-2"
NOW = datetime(2026, 8, 31, 12, 0, tzinfo=timezone.utc)


def _ops_ctx(*, facility_id: str = FACILITY, user_id: str = ME,
             role: RoleName = RoleName.OPERATIONS_EXECUTIVE) -> ExecutionContext:
    return ExecutionContext(
        request_id="req-1", auth_subject="sub-1", user_id=user_id, email="ops@setuhaul.com",
        full_name="Priya Nair", role_id="ROL002", role_name=role, facility_id=facility_id,
    )


def _escalation(**overrides) -> dict:
    base = {
        "escalation_id": "ESC-1",
        "shipment_id": "SHP1015",
        "facility_id": FACILITY,
        "driver_id": "DRV1",
        "escalation_type": "NO_FEASIBLE_SLOT",
        "escalation_status": "OPEN",
        "severity_code": "HIGH",
        "payload_json": "{}",
        # 10 minutes old: inside every SLA_BUDGET_MIN budget, so the breach evidence stays out of
        # the way of tests that are not about SLA.
        "created_at": (NOW - timedelta(minutes=10)).isoformat(),
        "updated_at": (NOW - timedelta(minutes=10)).isoformat(),
        "owner_user_id": None,
        "owner_name": None,
        "thread_id": "THR-1",
        "thread_status": "OPEN",
    }
    base.update(overrides)
    return base


def _inputs(escalation: dict | None = None, **overrides) -> dict:
    base = {
        "escalation": escalation or _escalation(),
        "payload": {},
        "shipment": {
            "shipment_id": "SHP1015", "current_status": "IN_TRANSIT", "priority_code": "HIGH",
            "required_dock_type": "REEFER", "original_eta_ts": NOW.isoformat(),
            "latest_eta_ts": NOW.isoformat(), "destination_facility_id": FACILITY,
        },
        "appointment": None,
        "latest_eta": None,
        "last_message": None,
        "unroutable_contacts": [],
    }
    base.update(overrides)
    return base


def _suggest(inputs: dict, *, user_id: str = ME, is_admin: bool = False) -> dict:
    return build_suggestion(inputs, caller_user_id=user_id, caller_is_admin=is_admin, now=NOW)


def _action(result: dict, name: str) -> dict:
    return next(a for a in result["actions"] if a["action"] == name)


# ---------------------------------------------------------------------------------------------
# The invariant that makes the panel trustworthy
# ---------------------------------------------------------------------------------------------

ALL_REASONS = [
    "NO_FEASIBLE_SLOT", "PENDING_EXPIRED_UNACTIONED", "AMBIGUOUS_SHIPMENT", "LOW_CONFIDENCE_ETA",
    "WAREHOUSE_REPLY_CONFLICT", "NOTIFICATION_FAILED", "NOTIFICATION_UNROUTABLE",
    "SAFETY_OR_REGULATED", "CAPACITY_EVENT_CASCADE",
]
ALL_STATUSES = ["OPEN", "ACKNOWLEDGED", "IN_PROGRESS", "RESOLVED", "CANCELLED"]


def test_never_recommends_an_unavailable_action() -> None:
    """The load-bearing property, asserted over the whole state space rather than a happy path.

    405 combinations: nine reasons x five statuses x owner (nobody / me / someone else) x thread
    state (open thread / taken-over thread / no thread).

    **The legality is re-derived independently**, by calling `_classify_actions` on the same row,
    rather than reading `actions[]` back out of the result. Reading it back would only prove that
    `build_suggestion` stamped `"recommended"` on whatever it picked -- which is true by
    construction and proves nothing. Asking the classifier separately proves the recommendation was
    drawn from the *available* set.
    """
    checked = 0
    for reason in ALL_REASONS:
        for status in ALL_STATUSES:
            for owner in (None, ME, SOMEONE_ELSE):
                for thread_id, thread_status in (("THR-1", "OPEN"), ("THR-1", "ESCALATED"), (None, None)):
                    esc = _escalation(
                        escalation_type=reason, escalation_status=status, owner_user_id=owner,
                        owner_name="Priya Nair" if owner else None,
                        thread_id=thread_id, thread_status=thread_status,
                    )
                    result = _suggest(_inputs(esc))
                    checked += 1
                    recommended = result["recommended_action"]
                    if recommended is None:
                        assert result["abstain_reason"] is not None, (reason, status, owner)
                        assert result["rationale"] is None
                        assert result["confidence"] is None
                        continue
                    legality = ops_copilot._classify_actions(
                        esc, caller_user_id=ME, caller_is_admin=False
                    )
                    assert legality[recommended]["status"] == "available", (
                        reason, status, owner, thread_status, recommended,
                        legality[recommended],
                    )
                    assert _action(result, recommended)["status"] == "recommended"
                    assert result["rationale"], (reason, status, owner)
                    assert result["confidence"] in {"high", "medium"}
                    assert result["abstain_reason"] is None
    assert checked == 9 * 5 * 3 * 3


def test_removing_an_actions_availability_removes_the_recommendation() -> None:
    """Take the availability away and the recommendation goes with it, every time.

    Each rule is guarded by `available(...)` at the point it fires, so this exercises those guards
    directly rather than the fail-closed net behind them -- that net is deliberately unreachable
    today and exists for the rule someone adds later without a guard. What is asserted here is the
    property both mechanisms serve: an action the classifier will not vouch for never becomes a
    recommendation, and the response abstains honestly (no rationale, no confidence) instead.
    """
    esc = _escalation(escalation_type="AMBIGUOUS_SHIPMENT", escalation_status="ACKNOWLEDGED",
                      owner_user_id=ME)
    assert _suggest(_inputs(esc))["recommended_action"] == TAKE_OVER

    real_classify = ops_copilot._classify_actions

    def crippled(escalation, **kwargs):
        actions = real_classify(escalation, **kwargs)
        for name in (TAKE_OVER, POST_MESSAGE):
            actions[name] = {"status": "unavailable", "reason_code": "NOT_OWNER",
                             "arguments": None}
        return actions

    ops_copilot._classify_actions = crippled
    try:
        result = _suggest(_inputs(esc))
    finally:
        ops_copilot._classify_actions = real_classify

    assert result["recommended_action"] is None
    assert result["abstain_reason"] is not None
    assert result["rationale"] is None
    assert result["confidence"] is None


def test_every_evidence_item_names_the_column_it_came_from() -> None:
    """"Never invent operational data", made checkable by reading the response.

    Every fact carries the column it was read from. A future rule that adds a sentence without a
    source fails here rather than at a coordinator's desk.
    """
    for reason in ALL_REASONS:
        esc = _escalation(escalation_type=reason, escalation_status="ACKNOWLEDGED", owner_user_id=ME)
        result = _suggest(_inputs(esc))
        assert result["evidence"], reason
        for item in result["evidence"]:
            assert item["code"] and item["label"] and item["source"], (reason, item)


def test_a_terminal_escalation_offers_nothing_at_all() -> None:
    for status in ("RESOLVED", "CANCELLED"):
        result = _suggest(_inputs(_escalation(escalation_status=status, owner_user_id=ME)))
        assert result["recommended_action"] is None
        assert result["abstain_reason"]["code"] == "ALREADY_TERMINAL"
        assert {a["status"] for a in result["actions"]} == {"unavailable"}


# ---------------------------------------------------------------------------------------------
# Legality mirrors the real service guards
# ---------------------------------------------------------------------------------------------


def test_legality_matches_the_service_guards() -> None:
    """Each assertion below pairs with the guard it mirrors in the write path.

    `acknowledge_escalation` -> `WHERE escalation_status = 'OPEN'`;
    `start_escalation_work` -> ACKNOWLEDGED + owner == caller;
    `take_over_thread` -> ACKNOWLEDGED/IN_PROGRESS + owned + thread not already ESCALATED;
    `post_operations_message` -> thread ESCALATED;
    `hand_back_thread` -> thread ESCALATED + IN_PROGRESS + owned;
    `reassign_escalation` -> owner not null.
    """
    open_unowned = _suggest(_inputs(_escalation(escalation_status="OPEN")))
    assert _action(open_unowned, ACK)["status"] == "recommended"
    assert _action(open_unowned, START)["reason_code"] == "NOT_ACKNOWLEDGED"
    assert _action(open_unowned, REASSIGN)["reason_code"] == "NOT_ACKNOWLEDGED"
    assert _action(open_unowned, TAKE_OVER)["reason_code"] == "NOT_ACKNOWLEDGED"

    acked_mine = _suggest(
        _inputs(_escalation(escalation_status="ACKNOWLEDGED", owner_user_id=ME))
    )
    assert _action(acked_mine, START)["status"] == "available"
    assert _action(acked_mine, REASSIGN)["status"] == "available"
    assert _action(acked_mine, TAKE_OVER)["status"] in {"available", "recommended"}
    assert _action(acked_mine, POST_MESSAGE)["reason_code"] == "NOT_TAKEN_OVER"
    assert _action(acked_mine, HAND_BACK)["reason_code"] == "NOT_TAKEN_OVER"

    acked_theirs = _suggest(
        _inputs(_escalation(escalation_status="ACKNOWLEDGED", owner_user_id=SOMEONE_ELSE))
    )
    assert _action(acked_theirs, START)["reason_code"] == "NOT_OWNER"
    assert _action(acked_theirs, TAKE_OVER)["reason_code"] == "NOT_OWNER"

    taken_over = _suggest(
        _inputs(
            _escalation(
                escalation_status="IN_PROGRESS", owner_user_id=ME, thread_status="ESCALATED"
            )
        )
    )
    assert _action(taken_over, TAKE_OVER)["reason_code"] == "ALREADY_TAKEN_OVER"
    assert _action(taken_over, POST_MESSAGE)["status"] in {"available", "recommended"}
    assert _action(taken_over, HAND_BACK)["status"] == "available"

    no_thread = _suggest(
        _inputs(_escalation(escalation_status="ACKNOWLEDGED", owner_user_id=ME, thread_id=None,
                            thread_status=None))
    )
    assert _action(no_thread, TAKE_OVER)["reason_code"] == "NO_THREAD"
    assert _action(no_thread, POST_MESSAGE)["reason_code"] == "NO_THREAD"


def test_an_admin_may_act_on_another_coordinators_case() -> None:
    """`assert_facility_write_scope` and `start_escalation_work` both let ADMIN through the owner
    check, so the legality mirror has to as well -- otherwise the co-pilot would go silent for the
    one role that can actually unblock a stuck case."""
    esc = _escalation(escalation_status="ACKNOWLEDGED", owner_user_id=SOMEONE_ELSE,
                      escalation_type="AMBIGUOUS_SHIPMENT")
    as_peer = _suggest(_inputs(esc))
    assert as_peer["abstain_reason"]["code"] == "NOT_YOUR_CASE"

    as_admin = _suggest(_inputs(esc), user_id="USR-ADM-1", is_admin=True)
    assert as_admin["recommended_action"] == TAKE_OVER


def test_the_sequencer_action_follows_the_delegates_own_guards() -> None:
    """`request_sequencer_proposal` is the eighth §7.5.5 tool, **built 2026-09-02** (#54/#49).

    Until then this asserted `unavailable / NOT_IMPLEMENTED`. Now it asserts the thing that
    actually protects a coordinator: the entry is `available` exactly when
    `sequencer.request_sequencer_proposal` would succeed, and carries that function's own refusal
    code otherwise. The co-pilot's one hard guarantee is that it never points at a button the
    server is about to refuse.
    """
    owned = _suggest(_inputs(_escalation(escalation_status="ACKNOWLEDGED", owner_user_id=ME)))
    assert _action(owned, SEQUENCER)["status"] == "available"

    unowned = _suggest(_inputs(_escalation(escalation_status="OPEN", owner_user_id=None)))
    entry = _action(unowned, SEQUENCER)
    assert entry["status"] == "unavailable"
    assert entry["reason_code"] == "NOT_ACKNOWLEDGED"

    other = _suggest(_inputs(_escalation(escalation_status="ACKNOWLEDGED", owner_user_id="USR-X")))
    entry = _action(other, SEQUENCER)
    assert entry["status"] == "unavailable"
    assert entry["reason_code"] == "NOT_OWNER"


# ---------------------------------------------------------------------------------------------
# The rules themselves
# ---------------------------------------------------------------------------------------------


def test_a_cancelled_shipment_recommends_cancel_not_resolve() -> None:
    """`flows-and-states.md` Flow 1 step 5, verbatim: Cancel is for "the escalation no longer
    applies — e.g. the shipment itself was cancelled elsewhere". Resolve would claim the underlying
    issue was fixed, which is a different and false statement.
    """
    inputs = _inputs(
        _escalation(escalation_status="ACKNOWLEDGED", owner_user_id=ME),
        shipment={"shipment_id": "SHP1015", "current_status": "CANCELLED", "priority_code": "HIGH",
                  "required_dock_type": "REEFER", "original_eta_ts": None, "latest_eta_ts": None,
                  "destination_facility_id": FACILITY},
    )
    result = _suggest(inputs)
    assert result["recommended_action"] == CANCEL
    assert _action(result, CANCEL)["arguments"] == {"reason_code": "SHIPMENT_CANCELLED"}
    assert any(e["code"] == "SHIPMENT_CANCELLED" for e in result["evidence"])
    # The reason code must be one `cancel_escalation` actually accepts.
    from app.services.escalation_service import CANCEL_REASON_CODES

    assert _action(result, CANCEL)["arguments"]["reason_code"] in CANCEL_REASON_CODES


def test_a_stale_no_feasible_slot_escalation_recommends_resolve() -> None:
    """The one genuinely non-obvious inference in the engine: the escalation's own problem was
    solved somewhere else and nobody closed the case. Grounded in
    `appointments.appointment_status`, not in a guess."""
    inputs = _inputs(
        _escalation(escalation_status="ACKNOWLEDGED", owner_user_id=ME),
        appointment={"appointment_id": "APT-9", "appointment_status": "CONFIRMED",
                     "booking_source": "PLANNER", "confirmed_at": NOW.isoformat(),
                     "booked_at": NOW.isoformat(), "slot_start_ts": "2026-08-31T22:15:00+00:00",
                     "slot_end_ts": "2026-08-31T23:15:00+00:00", "dock_id": "DOCK-JAI-D5"},
    )
    result = _suggest(inputs)
    assert result["recommended_action"] == RESOLVE
    assert _action(result, RESOLVE)["arguments"] == {"reason_code": "ISSUE_FIXED"}
    assert any(e["code"] == "APPOINTMENT_CONFIRMED" for e in result["evidence"])


def test_a_pending_no_feasible_slot_appointment_is_not_treated_as_solved() -> None:
    """`PENDING_CONFIRMATION` is not `CONFIRMED`. A held-but-unconfirmed appointment can still
    expire (D9), so closing the escalation on it would be premature."""
    inputs = _inputs(
        _escalation(escalation_status="ACKNOWLEDGED", owner_user_id=ME),
        appointment={"appointment_id": "APT-9", "appointment_status": "PENDING_CONFIRMATION",
                     "booking_source": "DRIVER_CHAT", "confirmed_at": None,
                     "booked_at": NOW.isoformat(), "slot_start_ts": "2026-08-31T22:15:00+00:00",
                     "slot_end_ts": "2026-08-31T23:15:00+00:00", "dock_id": "DOCK-JAI-D5"},
    )
    result = _suggest(inputs)
    assert result["recommended_action"] is None
    assert result["abstain_reason"]["code"] == "NO_OPS_TOOL_FOR_REPLAN"


def test_no_feasible_slot_without_a_new_appointment_abstains() -> None:
    """Ops has no rescheduling tool. §7.5.5 has none, and §7.5.1's apply/confirm are the planner's
    (D5: the sequencer proposes, the planner applies). Abstaining is the honest output."""
    result = _suggest(_inputs(_escalation(escalation_status="ACKNOWLEDGED", owner_user_id=ME)))
    assert result["recommended_action"] is None
    assert result["abstain_reason"]["code"] == "NO_OPS_TOOL_FOR_REPLAN"


def test_ambiguous_shipment_recommends_takeover_then_reply() -> None:
    """Flow 1 step 4 names this reason's resolution explicitly: "take over the thread for
    `AMBIGUOUS_SHIPMENT`"."""
    before = _suggest(
        _inputs(_escalation(escalation_type="AMBIGUOUS_SHIPMENT", escalation_status="ACKNOWLEDGED",
                            owner_user_id=ME))
    )
    assert before["recommended_action"] == TAKE_OVER

    after = _suggest(
        _inputs(_escalation(escalation_type="AMBIGUOUS_SHIPMENT", escalation_status="IN_PROGRESS",
                            owner_user_id=ME, thread_status="ESCALATED"))
    )
    assert after["recommended_action"] == POST_MESSAGE
    # The scope decision, asserted: the co-pilot recommends the *act* of replying and never
    # supplies the words. Nothing in the response carries draft text.
    assert "arguments" in _action(after, POST_MESSAGE)
    assert _action(after, POST_MESSAGE)["arguments"] is None


def test_ambiguous_shipment_with_no_thread_abstains() -> None:
    result = _suggest(
        _inputs(_escalation(escalation_type="AMBIGUOUS_SHIPMENT", escalation_status="ACKNOWLEDGED",
                            owner_user_id=ME, thread_id=None, thread_status=None))
    )
    assert result["abstain_reason"]["code"] == "NO_THREAD_TO_TAKE_OVER"


def test_capacity_cascade_now_recommends_the_sequencer_proposal() -> None:
    """`flows-and-states.md` Flow 1 step 4's own mapping -- "request a sequencer proposal for
    `CAPACITY_EVENT_CASCADE`" -- reachable at last.

    This branch abstained with `SEQUENCER_UNBUILT` until issues #54/#49 landed; the abstention was
    always a statement about the tool catalog rather than about the reasoning, so building the tool
    is the whole of the change. The evidence assertion is unchanged and deliberately kept: a
    recommendation must not cost the coordinator the facts underneath it.
    """
    esc = _escalation(escalation_type="CAPACITY_EVENT_CASCADE", escalation_status="ACKNOWLEDGED",
                      owner_user_id=ME)
    inputs = _inputs(esc, payload={"affected_count": 4, "dock_id": "DOCK-JAI-D3",
                                   "reason": "Dock block overlaps live appointments."})
    result = _suggest(inputs)
    assert result["recommended_action"] == SEQUENCER
    assert result["abstain_reason"] is None
    assert result["confidence"] == "high"
    # D5 must survive the recommendation: ops requests, a planner applies.
    assert "planner applies" in result["rationale"]
    assert any(e["code"] == "AFFECTED_SHIPMENTS" and "4 appointments" in e["label"]
               for e in result["evidence"])


def test_unroutable_never_suggests_a_retry_and_names_the_broken_contact() -> None:
    """`edge-cases.md` #6: "UNROUTABLE's resolution is **never** 'retry send'". There is also no
    tool anywhere in §7.5 that edits `facility_contacts`, so this abstains with the record named.
    """
    esc = _escalation(escalation_type="NOTIFICATION_UNROUTABLE", escalation_status="ACKNOWLEDGED",
                      owner_user_id=ME)
    result = _suggest(
        _inputs(esc, unroutable_contacts=[
            {"contact_id": "CON005", "contact_role": "NIGHT_SHIFT", "contact_name": "R. Sharma",
             "email": None, "phone": "+91..."},
        ])
    )
    assert result["recommended_action"] is None
    assert result["abstain_reason"]["code"] == "NO_TOOL_FOR_CONTACT_REPAIR"
    assert any("has no email" in e["label"] for e in result["evidence"])
    assert "retry" not in (result["rationale"] or "").lower()


def test_notification_failed_and_unroutable_do_not_produce_the_same_answer() -> None:
    """`edge-cases.md` #6 and FR-OPS's acceptance criteria: the two must not look alike. Different
    abstain code, different evidence -- one fails before a send is attempted, the other in flight.
    """
    common = {"escalation_status": "ACKNOWLEDGED", "owner_user_id": ME}
    failed = _suggest(_inputs(_escalation(escalation_type="NOTIFICATION_FAILED", **common)))
    unroutable = _suggest(
        _inputs(_escalation(escalation_type="NOTIFICATION_UNROUTABLE", **common))
    )
    assert failed["abstain_reason"]["code"] != unroutable["abstain_reason"]["code"]


def test_warehouse_reply_conflict_is_never_auto_reconciled() -> None:
    """§7.4: "Immediate, never auto-reconcile"."""
    result = _suggest(
        _inputs(_escalation(escalation_type="WAREHOUSE_REPLY_CONFLICT",
                            escalation_status="ACKNOWLEDGED", owner_user_id=ME))
    )
    assert result["recommended_action"] is None
    assert result["abstain_reason"]["code"] == "HUMAN_RECONCILIATION_REQUIRED"


def test_safety_escalations_never_get_a_terminal_recommendation() -> None:
    """§7.4 marks `SAFETY_OR_REGULATED` "Immediate, human-only".

    Resolve and Cancel are marked `suppressed` (a distinct status from `unavailable` -- they are
    legal, the co-pilot simply will not point at them), never `recommended`. Even on the stale-
    appointment path, which for any other reason would recommend Resolve.
    """
    esc = _escalation(escalation_type="SAFETY_OR_REGULATED", escalation_status="ACKNOWLEDGED",
                      owner_user_id=ME)
    result = _suggest(_inputs(esc))
    assert _action(result, RESOLVE)["status"] == "suppressed"
    assert _action(result, RESOLVE)["reason_code"] == "SAFETY_HUMAN_ONLY"
    assert _action(result, CANCEL)["status"] == "suppressed"
    assert result["recommended_action"] == TAKE_OVER

    with_appointment = _suggest(
        _inputs(esc, appointment={"appointment_id": "APT-9", "appointment_status": "CONFIRMED",
                                  "booking_source": "PLANNER", "confirmed_at": NOW.isoformat(),
                                  "booked_at": NOW.isoformat(), "slot_start_ts": "x",
                                  "slot_end_ts": "y", "dock_id": "DOCK-JAI-D5"})
    )
    assert with_appointment["recommended_action"] != RESOLVE


def test_safety_shipment_cancelled_still_suppresses_cancel() -> None:
    """The R1 shortcut must not outrank the safety rule -- the whole point of `suppressed` is that
    it holds regardless of which branch would otherwise have fired."""
    esc = _escalation(escalation_type="SAFETY_OR_REGULATED", escalation_status="ACKNOWLEDGED",
                      owner_user_id=ME)
    result = _suggest(
        _inputs(esc, shipment={"shipment_id": "SHP1015", "current_status": "CANCELLED",
                               "priority_code": "HIGH", "required_dock_type": "ANY",
                               "original_eta_ts": None, "latest_eta_ts": None,
                               "destination_facility_id": FACILITY})
    )
    assert result["recommended_action"] != CANCEL


def test_low_confidence_eta_resolves_once_a_firmer_estimate_arrives() -> None:
    esc = _escalation(escalation_type="LOW_CONFIDENCE_ETA", escalation_status="ACKNOWLEDGED",
                      owner_user_id=ME)
    firmed = _suggest(
        _inputs(esc, latest_eta={"eta_update_id": "ETA-9", "source_type": "DRIVER_DECLARED",
                                 "declared_eta_ts": NOW.isoformat(), "confidence_code": "HIGH",
                                 "delay_reason_code": "TRAFFIC",
                                 "created_at": (NOW - timedelta(minutes=2)).isoformat()})
    )
    assert firmed["recommended_action"] == RESOLVE

    still_low = _suggest(
        _inputs(esc, latest_eta={"eta_update_id": "ETA-8", "source_type": "DRIVER_DECLARED",
                                 "declared_eta_ts": NOW.isoformat(), "confidence_code": "LOW",
                                 "delay_reason_code": "TRAFFIC",
                                 "created_at": (NOW - timedelta(minutes=2)).isoformat()})
    )
    assert still_low["recommended_action"] == TAKE_OVER


def test_a_stale_but_firmer_eta_declared_before_the_escalation_does_not_resolve_it() -> None:
    """An ETA that predates the escalation cannot be the thing that fixed it. Guards against the
    obvious version of this rule that compares confidence and forgets the clock."""
    esc = _escalation(escalation_type="LOW_CONFIDENCE_ETA", escalation_status="ACKNOWLEDGED",
                      owner_user_id=ME)
    result = _suggest(
        _inputs(esc, latest_eta={"eta_update_id": "ETA-7", "source_type": "ORIGINAL_PLAN",
                                 "declared_eta_ts": NOW.isoformat(), "confidence_code": "HIGH",
                                 "delay_reason_code": None,
                                 "created_at": (NOW - timedelta(hours=3)).isoformat()})
    )
    assert result["recommended_action"] != RESOLVE


def test_an_sla_breach_is_reported_with_its_assumption_flag_attached() -> None:
    """The budgets behind this number are `Source: assumption, untested`. The caveat has to reach
    the reader, not be laundered into a fact by the time it renders."""
    esc = _escalation(escalation_status="OPEN", severity_code="HIGH",
                      created_at=(NOW - timedelta(hours=6)).isoformat())
    result = _suggest(_inputs(esc))
    breach = next(e for e in result["evidence"] if e["code"] == "SLA_BREACHED")
    assert "assumption, untested" in breach["source"]


def test_a_driver_waiting_is_reported_as_a_fact_not_a_drafted_reply() -> None:
    esc = _escalation(escalation_type="AMBIGUOUS_SHIPMENT", escalation_status="IN_PROGRESS",
                      owner_user_id=ME, thread_status="ESCALATED")
    result = _suggest(
        _inputs(esc, last_message={"chat_message_id": "MSG-9", "sender_type": "DRIVER",
                                   "message_ts": (NOW - timedelta(minutes=40)).isoformat(),
                                   "requires_human_review": 0})
    )
    waiting = next(e for e in result["evidence"] if e["code"] == "DRIVER_SPOKE_LAST")
    assert "40 minutes ago" in waiting["label"]


def test_an_unparseable_payload_costs_evidence_not_the_response() -> None:
    """A malformed `payload_json` must degrade one fact, never 500 the panel -- `edge-cases.md` #5:
    "the console is fully operable with the co-pilot entirely down"."""
    esc = _escalation(escalation_type="CAPACITY_EVENT_CASCADE", escalation_status="ACKNOWLEDGED",
                      owner_user_id=ME)
    result = _suggest(_inputs(esc, payload={}))
    # The recommendation survives an unreadable payload -- it is derived from lifecycle columns,
    # not from the payload -- and only the one payload-derived evidence line is lost.
    assert result["recommended_action"] == SEQUENCER
    assert not any(e["code"] == "AFFECTED_SHIPMENTS" for e in result["evidence"])


# ---------------------------------------------------------------------------------------------
# Orchestration: scope, and the no-write guarantee
# ---------------------------------------------------------------------------------------------


def _result(rows: list[dict] | dict | None) -> MagicMock:
    m = MagicMock()
    if isinstance(rows, list):
        m.mappings.return_value.all.return_value = rows
        m.mappings.return_value.first.return_value = rows[0] if rows else None
    else:
        m.mappings.return_value.first.return_value = rows
        m.mappings.return_value.all.return_value = [rows] if rows else []
    return m


def _session(*results) -> AsyncMock:
    session = AsyncMock()
    session.execute = AsyncMock(side_effect=[_result(r) for r in results])
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    return session


def _statements(session: AsyncMock) -> list[str]:
    return [str(call.args[0]) for call in session.execute.await_args_list]


async def test_the_suggestion_path_never_writes() -> None:
    """Structural, not a promise in a docstring. `AGENTS.md`: the assistant layer "never executes
    SQL or directly mutates business tables" -- so every statement this path runs must be a SELECT
    and it must never commit."""
    esc = _escalation(escalation_status="ACKNOWLEDGED", owner_user_id=ME,
                      escalation_type="AMBIGUOUS_SHIPMENT")
    session = _session(
        esc,                       # get_escalation_with_thread
        {"shipment_id": "SHP1015", "current_status": "IN_TRANSIT", "priority_code": "HIGH",
         "required_dock_type": "ANY", "original_eta_ts": None, "latest_eta_ts": None,
         "destination_facility_id": FACILITY},                                # get_shipment_state
        None,                                                          # get_current_appointment
        None,                                                          # get_latest_eta_update
        [{"chat_message_id": "MSG-1", "sender_type": "DRIVER",
          "message_ts": NOW.isoformat(), "requires_human_review": 0}],  # get_last_thread_message
    )
    result = await get_resolution_suggestion(session, _ops_ctx(), "ESC-1")

    assert result["recommended_action"] == TAKE_OVER
    assert result["generator"] == "deterministic:v1"
    session.commit.assert_not_awaited()
    for sql in _statements(session):
        head = sql.strip().split()[0].upper()
        assert head == "SELECT", sql


async def test_another_facilitys_escalation_is_refused() -> None:
    """M15/NFR-019: the facility comes off the escalation's own row, and there is no argument by
    which the client could ask for a different one."""
    session = _session(_escalation(facility_id=OTHER_FACILITY))
    with pytest.raises(AppError) as exc:
        await get_resolution_suggestion(session, _ops_ctx(facility_id=FACILITY), "ESC-1")
    assert exc.value.status_code == 403


async def test_a_global_read_persona_may_read_a_suggestion_without_write_authority() -> None:
    """`assert_facility_visible`, not `assert_facility_write_scope`: TRANSPORT_MANAGER holds only
    `*_read_global` permissions and can already see this row in the queue. Gating a pure read on
    write authority would hide the reasoning behind a case they can read anyway."""
    session = _session(
        _escalation(facility_id=OTHER_FACILITY, escalation_status="ACKNOWLEDGED",
                    owner_user_id=SOMEONE_ELSE),
        None, None, None, [],
    )
    result = await get_resolution_suggestion(
        session, _ops_ctx(facility_id=None, role=RoleName.TRANSPORT_MANAGER, user_id="USR-TM-1"),
        "ESC-1",
    )
    # They can read it; the engine still declines to recommend somebody else's case.
    assert result["abstain_reason"]["code"] == "NOT_YOUR_CASE"


async def test_an_unknown_escalation_is_a_404_not_an_empty_suggestion() -> None:
    session = _session(None)
    with pytest.raises(AppError) as exc:
        await get_resolution_suggestion(session, _ops_ctx(), "ESC-nope")
    assert exc.value.status_code == 404
    assert exc.value.code == "NOT_FOUND"


async def test_unroutable_reads_the_contact_table_and_others_do_not() -> None:
    """The contact read is conditional on the reason, so an `AMBIGUOUS_SHIPMENT` row does not pay
    for a query it will never use. Asserted on the statements actually run, not on timing."""
    esc = _escalation(escalation_type="NOTIFICATION_UNROUTABLE", escalation_status="ACKNOWLEDGED",
                      owner_user_id=ME, thread_id=None, thread_status=None)
    session = _session(
        esc, None, None, None,
        [{"contact_id": "CON005", "contact_role": "NIGHT_SHIFT", "contact_name": "R. Sharma",
          "email": None, "phone": "+91..."}],
    )
    result = await get_resolution_suggestion(session, _ops_ctx(), "ESC-1")
    assert any("facility_contacts" in sql for sql in _statements(session))
    assert any(e["code"] == "CONTACT_MISSING_FIELD" for e in result["evidence"])

    other = _escalation(escalation_type="AMBIGUOUS_SHIPMENT", escalation_status="ACKNOWLEDGED",
                        owner_user_id=ME, thread_id=None, thread_status=None)
    session2 = _session(other, None, None, None)
    await get_resolution_suggestion(session2, _ops_ctx(), "ESC-2")
    assert not any("facility_contacts" in sql for sql in _statements(session2))


async def test_a_malformed_payload_json_does_not_break_the_orchestrator() -> None:
    session = _session(
        _escalation(payload_json="{not json", escalation_status="ACKNOWLEDGED", owner_user_id=ME,
                    thread_id=None, thread_status=None),
        None, None, None,
    )
    result = await get_resolution_suggestion(session, _ops_ctx(), "ESC-1")
    assert result["escalation_id"] == "ESC-1"


def test_the_action_catalog_matches_the_design_tool_names() -> None:
    """§7.5.5's table plus the two tools E5.2 added (#55, #56). A typo in an action name is a
    silently dead recommendation on the client, so the names are asserted rather than trusted."""
    result = _suggest(_inputs())
    assert [a["action"] for a in result["actions"]] == [
        "acknowledge_escalation", "start_escalation_work", "reassign_escalation",
        "take_over_thread", "post_operations_message", "hand_back_thread",
        "resolve_escalation", "cancel_escalation", "request_sequencer_proposal",
    ]


def test_no_action_argument_ever_carries_a_scope_id() -> None:
    """M15/NFR-019 by construction: the only value that may appear in `arguments` is a
    `reason_code` drawn from `escalation_service`'s own frozensets. If a future rule adds a
    facility, carrier or driver id here, this fails."""
    from app.services.escalation_service import CANCEL_REASON_CODES, RESOLVE_REASON_CODES

    allowed = set(CANCEL_REASON_CODES) | set(RESOLVE_REASON_CODES)
    for reason in ALL_REASONS:
        for status in ALL_STATUSES:
            result = _suggest(
                _inputs(_escalation(escalation_type=reason, escalation_status=status,
                                    owner_user_id=ME))
            )
            for entry in result["actions"]:
                args = entry["arguments"]
                if args is None:
                    continue
                assert set(args) == {"reason_code"}, entry
                assert args["reason_code"] in allowed, entry


def test_json_serialisable() -> None:
    """The router hands this straight to `ok()` and FastAPI serialises it. A `datetime` or a
    `frozenset` leaking into the payload would be a 500 at request time, not at import time."""
    result = _suggest(_inputs(_escalation(escalation_status="ACKNOWLEDGED", owner_user_id=ME)))
    assert json.loads(json.dumps(result))["escalation_id"] == "ESC-1"


def test_the_module_exposes_its_generator_so_an_llm_swap_is_visible_to_clients() -> None:
    """If this ever becomes LLM-backed, the client must be able to tell -- the response shape is
    designed to stay identical, which is only safe if the provenance field changes with it."""
    assert ops_copilot.GENERATOR == "deterministic:v1"
    assert _suggest(_inputs())["generator"] == ops_copilot.GENERATOR


# ---------------------------------------------------------------------------------------------
# HTTP layer: the route exists, is role-gated, and returns the standard envelope
# ---------------------------------------------------------------------------------------------


def test_the_endpoint_is_reachable_role_gated_and_enveloped() -> None:
    """Closes the last unverified hop before the flag flip: routing, auth gate and envelope.

    The service and the SQL are covered above and were separately probed against the live schema;
    what this adds is that `GET /api/v1/operations/escalations/{id}/suggestion` is actually
    mounted, that a non-ops role is refused before any read happens, and that the payload arrives
    inside `ok()`'s `{success, data, request_id}` envelope the frontend's `apiGet` unwraps.
    """
    from fastapi.testclient import TestClient

    from app.core import deps
    from app.main import create_app

    app = create_app()
    esc = _escalation(escalation_status="ACKNOWLEDGED", owner_user_id=ME,
                      escalation_type="AMBIGUOUS_SHIPMENT")
    session = _session(esc, None, None, None, [])

    async def _session_override():
        yield session

    app.dependency_overrides[deps.get_db_session] = _session_override
    app.dependency_overrides[deps.get_execution_context] = lambda: _ops_ctx()
    try:
        client = TestClient(app)
        res = client.get("/api/v1/operations/escalations/ESC-1/suggestion")
        assert res.status_code == 200, res.text
        body = res.json()
        assert body["success"] is True
        assert body["data"]["recommended_action"] == TAKE_OVER
        assert body["data"]["generator"] == "deterministic:v1"
        assert body["request_id"]

        # A driver must not reach an ops read. `require_roles(*OPS_PORTAL_ROLES)` excludes DRIVER,
        # and this asserts the refusal lands before the service runs rather than trusting the
        # decorator by inspection.
        app.dependency_overrides[deps.get_execution_context] = lambda: ExecutionContext(
            request_id="req-d", auth_subject="sub-d", user_id="USR-DRV-1",
            email="d@setuhaul.com", full_name="Ravi", role_id="ROL001",
            role_name=RoleName.DRIVER, driver_id="DRV1",
        )
        denied = TestClient(app).get("/api/v1/operations/escalations/ESC-1/suggestion")
        assert denied.status_code == 403
    finally:
        app.dependency_overrides.clear()


def test_the_route_is_a_get_with_no_mutating_sibling() -> None:
    """Structural guarantee that the co-pilot cannot act.

    Asserted against the app's own OpenAPI path table rather than by walking `app.routes`: on
    FastAPI 0.141 an `include_router` call leaves an opaque `_IncludedRouter` in `app.routes`
    whose children are not reachable by a flat scan, so a naive walk finds nothing and passes
    vacuously. `openapi()["paths"]` is the flattened, version-stable view.

    There is exactly one `/suggestion` path, its only method is GET, and nothing in the whole app
    exposes a mutating verb on a suggestion/copilot path. If someone later adds an "apply this
    suggestion" endpoint, this fails.
    """
    from app.main import create_app

    paths = create_app().openapi()["paths"]
    hits = {p: {m.upper() for m in ops} for p, ops in paths.items() if "suggestion" in p}
    assert hits == {"/api/v1/operations/escalations/{escalation_id}/suggestion": {"GET"}}
    for path, operations in paths.items():
        if "suggestion" in path or "copilot" in path:
            assert not ({m.upper() for m in operations} & {"POST", "PUT", "PATCH", "DELETE"}), path


def test_the_frontend_calls_the_path_the_backend_actually_mounts() -> None:
    """The one seam neither side's own tests can see: the URL string.

    `lib/api.ts` builds the request path as a template literal and `operations.py` declares a
    route; a typo in either is invisible to TypeScript *and* to pytest, and would surface only as
    a 404 in a browser. With no working POC credentials in `.env` there is no authenticated live
    round trip available to catch it, so the two strings are compared directly instead.

    Deliberately narrow: it checks this one path, not every endpoint, because inventing a general
    frontend/backend route linter is a different (and much larger) piece of work than closing the
    seam this change opened.
    """
    import re
    from pathlib import Path

    from app.main import create_app

    api_ts = (
        # tests/unit/ -> tests/ -> backend/ -> repo root.
        Path(__file__).resolve().parents[3] / "frontend" / "src" / "features" / "ops" / "lib"
        / "api.ts"
    )
    if not api_ts.exists():  # backend-only checkouts (the Docker image, agentcore/codezip)
        pytest.skip("frontend/ not present in this checkout")

    source = api_ts.read_text(encoding="utf-8")
    called = re.findall(r"`(/api/v1/operations/escalations/\$\{[^}]+\}/suggestion)`", source)
    assert len(called) == 1, called
    # Normalise the JS template placeholder to FastAPI's path-parameter syntax.
    normalised = re.sub(r"\$\{[^}]+\}", "{escalation_id}", called[0])
    assert normalised in create_app().openapi()["paths"], normalised
