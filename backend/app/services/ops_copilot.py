"""Ops co-pilot: the resolution-action suggestion (issue #57, `SOLUTION_DESIGN.md` §7.5.5).

## What this is, and the one sentence that bounds it

Given one escalation, this returns **which ops tool the coordinator should call next, and which
facts about that escalation point at it**. It writes nothing. It composes no driver-facing text. It
never calls the tool it names. `AGENTS.md`: *"The LLM orchestrates typed tools and never executes
SQL or directly mutates business tables"* -- a suggestion is a read plus a recommendation, and the
coordinator presses the button that is already on their screen.

This is a **narrower scope than the design docs describe**, by owner decision (2026-08-31).
`02-ops-exception-console/components.md` §3 and `screens.md` §4 specify three co-pilot capabilities
-- summarise thread, fetch context, draft a reply -- and `REQUIREMENTS.md` `FR-OPS-003` names the
same three. None of those is built here. Summarisation and reply-drafting are explicitly out of
scope; what earns the panel's space is the *reasoning*, not another button. That divergence is
real and is written up rather than papered over: see the report accompanying this change.

## Deterministic, not LLM-backed -- and why

1. **The rules are already written down.** §7.4's reason table and `flows-and-states.md` Flow 1
   step 4 enumerate the reason-to-resolution mapping in prose ("fix a contact record for
   `NOTIFICATION_UNROUTABLE`, retry a send for `NOTIFICATION_FAILED`, take over the thread for
   `AMBIGUOUS_SHIPMENT`, request a sequencer proposal for `CAPACITY_EVENT_CASCADE`"). Asking a
   model to reproduce a nine-row lookup table buys a lookup table plus a hallucination rate.
2. **"Never invent operational data" is *enforceable* here and only *monitorable* in a model.**
   Every sentence this module emits is built from a column it read, and carries that column's name
   in `evidence[].source`. A model can be prompted to do that and evaluated statistically; this
   cannot do otherwise.
3. **Half the answer is a state machine.** Whether a tool would even succeed right now is fully
   determined by `escalation_status`, `owner_user_id`, `thread_status` and `thread_id` -- and those
   preconditions are already implemented as guards in `escalation_service.py`
   (`NOT_ACKNOWLEDGED`, `NOT_OWNER`, `ALREADY_TAKEN_OVER`, `NOT_IN_PROGRESS`,
   `NOT_TAKEN_OVER`). `_classify_actions` below mirrors those guards exactly, so the co-pilot
   cannot recommend a button the server is about to refuse. That property is worth more than
   fluency.
4. **Calibration.** `NFR-016` sizes this at five concurrent coordinators. A model call per row
   selection is a per-click cost and a p95 this console has no streaming affordance for (its only
   transport is plain request/response -- `implementation-spec.md` §5.1 G6).
5. **`NFR-024` auditability.** A recommendation whose reasoning is a list of `(fact, column)` pairs
   is reconstructable months later. Prose is not.

**If the owner prefers LLM-backed**, the contract below does not change: `generator` flips from
`"deterministic:v1"` to a model id, `_collect_evidence` stays exactly as it is and becomes the
model's grounding input, and `_classify_actions` stays as a *post-filter* on whatever the model
picks. That hybrid is the only version worth building -- and it needs the `NFR-025` thread-scoped
tracing and an eval set that do not exist for this surface yet.

## Response contract

```
{ as_of, source, generator, escalation_id, escalation_type, escalation_status,
  recommended_action: str|null, rationale: str|null, confidence: "high"|"medium"|null,
  abstain_reason: {code, label}|null,
  evidence: [{code, label, source}],
  actions:  [{action, label, status, reason_code, arguments}] }
```

`actions[].status` is one of `recommended` / `available` / `suppressed` / `unavailable`, one list
rather than four, so a client reads one array. `arguments` never carries a scope id -- the only
value that ever appears there is a `reason_code` from `escalation_service`'s own frozensets, so
there is no argument by which a client could widen its own scope (`M15`/`NFR-019`).

**Abstention is a first-class outcome, not a failure.** When the honest answer is "the action this
reason calls for has no tool," `recommended_action` is `null`, `abstain_reason` names why, and
`evidence` is still populated -- the panel shows the facts without a recommendation rather than
manufacturing one. **Five** of the nine §7.4 reasons resolve this way today, which is a statement
about the tool catalog, not about the engine -- and the number moved from six to five on
2026-09-02, when issues #54/#49 built `request_sequencer_proposal` and `CAPACITY_EVENT_CASCADE`
stopped abstaining. That is the abstention list working as intended: it is an inventory of what the
catalog cannot do, so building a tool must shorten it.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.core.execution_context import ExecutionContext
from app.repositories import copilot as copilot_repo
from app.repositories.scope import assert_facility_visible
# `_sla_remaining_min` is imported despite its leading underscore, deliberately. The per-severity
# budgets behind it are flagged `Source: assumption, untested` in `escalation_service`, and a
# second copy of an unverified number is how two surfaces end up quietly disagreeing about whether
# a case has breached. One definition, imported, beats two definitions that drift.
from app.services.escalation_service import STEPPER_POSITIONS, _sla_remaining_min

GENERATOR = "deterministic:v1"

# §7.5.5's tool names, spelled exactly as the design's table spells them, so a client mapping a
# recommendation onto a button is matching the contract rather than a local nickname. The two that
# are not in that table are named for what shipped: `start_escalation_work` is the
# "eighth-and-a-half tool" issue #56 added, and `post_operations_message` is issue #55's.
ACK = "acknowledge_escalation"
START = "start_escalation_work"
REASSIGN = "reassign_escalation"
TAKE_OVER = "take_over_thread"
POST_MESSAGE = "post_operations_message"
HAND_BACK = "hand_back_thread"
RESOLVE = "resolve_escalation"
CANCEL = "cancel_escalation"
SEQUENCER = "request_sequencer_proposal"

ACTION_LABELS: dict[str, str] = {
    ACK: "Acknowledge",
    START: "Mark in progress",
    REASSIGN: "Reassign",
    TAKE_OVER: "Take over thread",
    POST_MESSAGE: "Reply in the thread",
    HAND_BACK: "Hand back",
    RESOLVE: "Resolve",
    CANCEL: "Cancel",
    SEQUENCER: "Request sequencer proposal",
}

TERMINAL_STATUSES = frozenset({"RESOLVED", "CANCELLED"})

# edge-cases.md #11 and REQUIREMENTS.md's FR-OPS acceptance criteria both single out
# SAFETY_OR_REGULATED. The design suppresses *draft-reply* on it, on the stated grounds that
# "gathering context carries none of the liability a drafted message does" -- summarise and
# fetch-context stay available. This engine generates no message at all, so that exact rule has
# nothing to bite on; the equivalent applied here is narrower and stricter in the place that
# matters: **never recommend a terminal action on a safety escalation.** §7.4 calls the reason
# "Immediate, human-only", and closing a safety case is precisely the judgment a rule engine has
# no standing to nudge. Procedural steps (acknowledge, take over -- a *human* joining the thread
# is what "human-only" asks for) stay recommendable.
SAFETY_SUPPRESSED_ACTIONS = frozenset({RESOLVE, CANCEL})


def _as_of() -> str:
    return datetime.now(timezone.utc).isoformat()


def _ev(code: str, label: str, source: str) -> dict[str, str]:
    """One fact, its plain-English rendering, and the column it came from.

    `source` is not decoration. It is what makes "never invent operational data" checkable by
    reading the response instead of trusting the code: every label here must be derivable from the
    named column, and a reviewer can hold the two side by side.
    """
    return {"code": code, "label": label, "source": source}


def _parse_ts(value: Any) -> datetime | None:
    """Timestamps in this schema are `TEXT` ISO-8601, not `timestamptz` -- parse defensively.

    Returns `None` rather than raising on anything unparseable: a malformed timestamp must cost the
    suggestion one piece of evidence, never the whole response. A co-pilot that 500s because a seed
    row has an odd date is worse than one that says less.
    """
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value))
    except ValueError:
        return None
    return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed


def _minutes_since(value: Any, now: datetime) -> int | None:
    parsed = _parse_ts(value)
    if parsed is None:
        return None
    return int((now - parsed).total_seconds() // 60)


def _humanise_minutes(minutes: int) -> str:
    if minutes < 1:
        return "just now"
    if minutes < 60:
        return f"{minutes} minutes ago"
    hours = minutes // 60
    return f"{hours} hour{'s' if hours != 1 else ''} ago"


# ---------------------------------------------------------------------------------------------
# Layer 1 -- legality. Which tools would actually succeed against this row, right now.
# ---------------------------------------------------------------------------------------------


def _classify_actions(esc: dict[str, Any], *, caller_user_id: str, caller_is_admin: bool) -> dict[str, dict[str, Any]]:
    """Mirror of the guards in `escalation_service.py` / `thread_message_service.py`.

    This is the load-bearing half of the feature. A recommendation is only ever drawn from the
    entries this marks `available`, so the co-pilot structurally cannot point at a control the
    backend is about to refuse -- which would be a worse outcome than no co-pilot at all.

    Each guard below cites the function it mirrors. If one of those guards is tightened and this is
    not, the suggestion goes stale in the *safe* direction (it stops recommending something that
    now fails) only by luck -- so the pairing is asserted in
    `tests/unit/test_ops_copilot.py::test_legality_matches_the_service_guards`.
    """
    status = str(esc.get("escalation_status") or "")
    owner = esc.get("owner_user_id")
    thread_id = esc.get("thread_id")
    thread_status = str(esc.get("thread_status") or "")
    terminal = status in TERMINAL_STATUSES
    owned = owner is not None
    owned_by_caller = owned and (str(owner) == caller_user_id or caller_is_admin)

    def entry(available: bool, reason_code: str | None) -> dict[str, Any]:
        return {
            "status": "available" if available else "unavailable",
            "reason_code": None if available else reason_code,
            "arguments": None,
        }

    if terminal:
        # The queue read never returns terminal rows, but this endpoint accepts any id the client
        # holds -- including one another coordinator closed a second ago. Everything is off.
        return {name: entry(False, "ALREADY_TERMINAL") for name in ACTION_LABELS}

    actions: dict[str, dict[str, Any]] = {}

    # `acknowledge_escalation`: `WHERE escalation_status = 'OPEN'` on the UPDATE.
    actions[ACK] = entry(status == "OPEN", "ALREADY_ACKNOWLEDGED")

    # `start_escalation_work`: ACKNOWLEDGED only, owner must be the caller (or admin).
    actions[START] = entry(
        status == "ACKNOWLEDGED" and owned_by_caller,
        "NOT_OWNER" if status == "ACKNOWLEDGED" else "NOT_ACKNOWLEDGED",
    )

    # `reassign_escalation`: refuses `NOT_ACKNOWLEDGED` when nobody owns it. It has no *status*
    # guard of its own -- the terminal case above is this module's own narrowing, since reassigning
    # a closed escalation is legal SQL and meaningless work.
    actions[REASSIGN] = entry(owned, "NOT_ACKNOWLEDGED")

    # `take_over_thread`: needs a thread, needs it not already ESCALATED, and refuses
    # `NOT_ACKNOWLEDGED` unless the escalation is ACKNOWLEDGED/IN_PROGRESS *and* owned.
    if not thread_id:
        actions[TAKE_OVER] = entry(False, "NO_THREAD")
    elif thread_status == "ESCALATED":
        actions[TAKE_OVER] = entry(False, "ALREADY_TAKEN_OVER")
    elif status not in {"ACKNOWLEDGED", "IN_PROGRESS"} or not owned:
        actions[TAKE_OVER] = entry(False, "NOT_ACKNOWLEDGED")
    else:
        actions[TAKE_OVER] = entry(owned_by_caller, "NOT_OWNER")

    # `post_operations_message`: `NOT_TAKEN_OVER` unless thread_status == 'ESCALATED'.
    if not thread_id:
        actions[POST_MESSAGE] = entry(False, "NO_THREAD")
    else:
        actions[POST_MESSAGE] = entry(thread_status == "ESCALATED", "NOT_TAKEN_OVER")

    # `hand_back_thread`: thread ESCALATED, and an owned IN_PROGRESS escalation behind it
    # (precondition tightened by issue #56).
    if not thread_id or thread_status != "ESCALATED":
        actions[HAND_BACK] = entry(False, "NOT_TAKEN_OVER")
    else:
        actions[HAND_BACK] = entry(status == "IN_PROGRESS" and owned, "NOT_IN_PROGRESS")

    # resolve/cancel guard only on facility scope, which the caller already passed to get here.
    actions[RESOLVE] = entry(True, None)
    actions[RESOLVE]["arguments"] = {"reason_code": "ISSUE_FIXED"}
    actions[CANCEL] = entry(True, None)

    # `request_sequencer_proposal` -- the eighth §7.5.5 tool, **built 2026-09-02** (issues #54/#49).
    # It shipped here as `entry(False, "NOT_IMPLEMENTED")` for as long as the Sequencer did not
    # exist; this is that shim's removal, not a widening of what the co-pilot does. The co-pilot
    # still only *names* the button -- it never calls the tool (see this module's opening line).
    #
    # The guard mirrors `scheduling/sequencer.request_sequencer_proposal`'s exactly: non-terminal
    # (handled above), ACKNOWLEDGED/IN_PROGRESS, owned by the caller or admin. Same shape as
    # `take_over_thread`'s below it, because both are "work on a case somebody has claimed", and
    # `test_ops_copilot.py::test_legality_matches_the_service_guards` asserts the pairing rather
    # than trusting this comment.
    if status not in {"ACKNOWLEDGED", "IN_PROGRESS"} or not owned:
        actions[SEQUENCER] = entry(False, "NOT_ACKNOWLEDGED")
    else:
        actions[SEQUENCER] = entry(owned_by_caller, "NOT_OWNER")

    if str(esc.get("escalation_type")) == "SAFETY_OR_REGULATED":
        for name in SAFETY_SUPPRESSED_ACTIONS:
            if actions[name]["status"] == "available":
                actions[name] = {
                    "status": "suppressed",
                    "reason_code": "SAFETY_HUMAN_ONLY",
                    "arguments": None,
                }

    return actions


# ---------------------------------------------------------------------------------------------
# Layer 2 -- evidence. The facts, gathered regardless of which action (if any) is recommended.
# ---------------------------------------------------------------------------------------------


def _collect_evidence(inputs: dict[str, Any], now: datetime) -> list[dict[str, str]]:
    """Every fact this engine read, whether or not it changed the recommendation.

    Populated on the abstain path too, deliberately: the owner's constraint is *fewer suggestions
    or none* when the inputs are thin -- not an empty panel. A coordinator who gets no
    recommendation should still learn that the driver wrote 40 minutes ago and that the shipment
    now holds a confirmed appointment.
    """
    esc = inputs["escalation"]
    shipment = inputs.get("shipment")
    appointment = inputs.get("appointment")
    eta = inputs.get("latest_eta")
    last_message = inputs.get("last_message")
    contacts = inputs.get("unroutable_contacts") or []
    payload = inputs.get("payload") or {}

    out: list[dict[str, str]] = []

    # --- ownership and lifecycle -------------------------------------------------------------
    owner_name = esc.get("owner_name") or esc.get("owner_user_id")
    if esc.get("owner_user_id") is None:
        out.append(_ev("UNOWNED", "Nobody owns this escalation yet.", "escalation_queue.owner_user_id"))
    else:
        out.append(
            _ev("OWNED", f"Owned by {owner_name}.", "escalation_queue.owner_user_id")
        )

    # --- SLA ----------------------------------------------------------------------------------
    # The budgets behind this number are flagged `Source: assumption, untested` in
    # `escalation_service.SLA_BUDGET_MIN` -- no documented SLA policy grounds them. The caveat
    # travels in `source` so it reaches the reader instead of being laundered into a fact.
    remaining = _sla_remaining_min(
        severity_code=str(esc.get("severity_code") or "HIGH"),
        created_at_iso=str(esc.get("created_at") or now.isoformat()),
    )
    if remaining < 0:
        out.append(
            _ev(
                "SLA_BREACHED",
                f"Past its SLA budget by {abs(int(remaining))} minutes.",
                "derived from escalation_queue.created_at + SLA_BUDGET_MIN "
                "(Source: assumption, untested)",
            )
        )

    # --- shipment ------------------------------------------------------------------------------
    if shipment is not None:
        shipment_status = str(shipment.get("current_status") or "")
        if shipment_status == "CANCELLED":
            out.append(
                _ev(
                    "SHIPMENT_CANCELLED",
                    f"{shipment['shipment_id']} has been cancelled.",
                    "shipments.current_status",
                )
            )
        elif shipment_status == "COMPLETED":
            out.append(
                _ev(
                    "SHIPMENT_COMPLETED",
                    f"{shipment['shipment_id']} has already completed.",
                    "shipments.current_status",
                )
            )

    # --- appointment ---------------------------------------------------------------------------
    if appointment is None:
        out.append(
            _ev(
                "NO_CURRENT_APPOINTMENT",
                "The shipment holds no live appointment.",
                "appointments (is_current = 1)",
            )
        )
    else:
        window = f"{appointment.get('slot_start_ts')} to {appointment.get('slot_end_ts')}"
        out.append(
            _ev(
                f"APPOINTMENT_{appointment['appointment_status']}",
                f"Appointment {appointment['appointment_id']} is "
                f"{appointment['appointment_status']} on {appointment.get('dock_id')} "
                f"({window}).",
                "appointments.appointment_status",
            )
        )

    # --- thread ---------------------------------------------------------------------------------
    if not esc.get("thread_id"):
        out.append(
            _ev(
                "NO_THREAD",
                "This shipment has no chat thread, so there is no conversation to take over.",
                "chat_threads (no row for this shipment)",
            )
        )
    else:
        if str(esc.get("thread_status")) == "ESCALATED":
            out.append(
                _ev("THREAD_TAKEN_OVER", "The thread is already taken over.", "chat_threads.thread_status")
            )
        if last_message is not None:
            minutes = _minutes_since(last_message.get("message_ts"), now)
            when = _humanise_minutes(minutes) if minutes is not None else "at an unknown time"
            sender = str(last_message.get("sender_type") or "UNKNOWN")
            if sender == "DRIVER":
                out.append(
                    _ev(
                        "DRIVER_SPOKE_LAST",
                        f"The driver wrote last, {when}, and nobody has answered.",
                        "chat_messages.sender_type / message_ts",
                    )
                )
            else:
                out.append(
                    _ev(
                        "LAST_MESSAGE_NOT_DRIVER",
                        f"The last message on the thread was from {sender}, {when}.",
                        "chat_messages.sender_type / message_ts",
                    )
                )

    # --- reason-specific payload ------------------------------------------------------------------
    escalation_type = str(esc.get("escalation_type") or "")

    if escalation_type == "NO_FEASIBLE_SLOT":
        # `feasibility.py` writes `blocking_reasons` as `[{slot_id, failure_code, message}]` and
        # `search_horizon_hours` alongside it. Reported as the distinct failure codes rather than
        # ten near-identical sentences.
        codes = sorted({str(r.get("failure_code")) for r in payload.get("blocking_reasons", []) if r})
        if codes:
            out.append(
                _ev(
                    "BLOCKING_REASONS",
                    "Every candidate slot was rejected for: " + ", ".join(codes) + ".",
                    "escalation_queue.payload_json.blocking_reasons",
                )
            )
        horizon = payload.get("search_horizon_hours")
        if horizon:
            out.append(
                _ev(
                    "SEARCH_HORIZON",
                    f"The feasibility search covered {horizon} hours and found nothing.",
                    "escalation_queue.payload_json.search_horizon_hours",
                )
            )

    if escalation_type == "CAPACITY_EVENT_CASCADE":
        count = payload.get("affected_count")
        if count:
            out.append(
                _ev(
                    "AFFECTED_SHIPMENTS",
                    f"{count} appointments were stranded by the block on "
                    f"{payload.get('dock_id') or 'this dock'}.",
                    "escalation_queue.payload_json.affected_count",
                )
            )

    if escalation_type == "PENDING_EXPIRED_UNACTIONED":
        appointment_id = payload.get("appointment_id")
        if appointment_id:
            out.append(
                _ev(
                    "EXPIRED_APPOINTMENT",
                    f"Appointment {appointment_id} expired unactioned and its capacity was released.",
                    "escalation_queue.payload_json.appointment_id",
                )
            )

    if escalation_type == "LOW_CONFIDENCE_ETA" and eta is not None:
        confidence = str(eta.get("confidence_code") or "UNKNOWN")
        newer = _parse_ts(eta.get("created_at"))
        raised = _parse_ts(esc.get("created_at"))
        is_newer = bool(newer and raised and newer > raised)
        out.append(
            _ev(
                "LATEST_ETA_CONFIDENCE",
                f"The most recent ETA is {confidence}-confidence and was declared "
                f"{'after' if is_newer else 'before'} this escalation was raised.",
                "eta_updates.confidence_code / created_at",
            )
        )

    if escalation_type == "NOTIFICATION_UNROUTABLE":
        for contact in contacts:
            missing = "email" if contact.get("email") is None else "phone number"
            out.append(
                _ev(
                    "CONTACT_MISSING_FIELD",
                    f"Facility contact {contact.get('contact_name')} "
                    f"({contact.get('contact_role')}) has no {missing}.",
                    "facility_contacts.email / phone",
                )
            )
        if not contacts:
            out.append(
                _ev(
                    "NO_BROKEN_CONTACT_FOUND",
                    "No active facility contact is missing an email or phone number, so the "
                    "unroutable recipient is not one of them.",
                    "facility_contacts (no matching row)",
                )
            )

    return out


# ---------------------------------------------------------------------------------------------
# Layer 3 -- the rules. First match wins; every branch either recommends or abstains explicitly.
# ---------------------------------------------------------------------------------------------

# Abstention codes and the sentence each one shows. Kept in one dict rather than inline so the
# full set of "reasons this said nothing" is readable at a glance -- that list is the honest
# summary of what the tool catalog cannot do today, and it should be easy to audit.
ABSTAIN_LABELS: dict[str, str] = {
    "ALREADY_TERMINAL": "This escalation is already closed.",
    "NOT_YOUR_CASE": "Another coordinator owns this. Reassign it first if you need to work it.",
    "NO_OPS_TOOL_FOR_REPLAN": (
        "Re-planning this shipment is a planner action. The ops console has no rescheduling tool, "
        "so there is nothing here to recommend."
    ),
    "NO_TOOL_FOR_CONTACT_REPAIR": (
        "The fix is to correct the contact record, and no tool in this product edits facility "
        "contacts. Retrying the send is never the fix for an unroutable recipient."
    ),
    "NO_TOOL_FOR_NOTIFICATION_RETRY": (
        "The fix is to retry the send, and no notification retry tool exists yet."
    ),
    "HUMAN_RECONCILIATION_REQUIRED": (
        "A warehouse reply contradicts the stored schedule. This is never auto-reconciled — a "
        "person decides which record is right."
    ),
    "NO_THREAD_TO_TAKE_OVER": (
        "The reason for this escalation is resolved by talking to the driver, and this shipment "
        "has no chat thread to take over."
    ),
    "HUMAN_JUDGEMENT_ONLY": (
        "Safety and regulated escalations are closed by a person's judgement, not on a "
        "suggestion."
    ),
    "NO_CONFIDENT_RECOMMENDATION": (
        "Nothing in this escalation's current state points clearly at one action."
    ),
}


def _abstain(code: str) -> dict[str, str]:
    return {"code": code, "label": ABSTAIN_LABELS[code]}


def build_suggestion(
    inputs: dict[str, Any],
    *,
    caller_user_id: str,
    caller_is_admin: bool,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Pure function: assembled facts in, suggestion out. No session, no I/O, no clock of its own.

    Kept pure on purpose -- every rule below is unit-testable against a literal dict, which is what
    makes "would this ever recommend a button the server refuses?" an assertion rather than an
    opinion.
    """
    now = now or datetime.now(timezone.utc)
    esc = inputs["escalation"]
    shipment = inputs.get("shipment")
    appointment = inputs.get("appointment")
    eta = inputs.get("latest_eta")
    payload = inputs.get("payload") or {}

    escalation_type = str(esc.get("escalation_type") or "")
    status = str(esc.get("escalation_status") or "")
    owner = esc.get("owner_user_id")
    owned_by_other = owner is not None and str(owner) != caller_user_id and not caller_is_admin

    actions = _classify_actions(esc, caller_user_id=caller_user_id, caller_is_admin=caller_is_admin)
    evidence = _collect_evidence(inputs, now)

    def available(name: str) -> bool:
        return actions[name]["status"] == "available"

    recommended: str | None = None
    rationale: str | None = None
    confidence: str | None = None
    abstain: dict[str, str] | None = None

    appointment_status = str((appointment or {}).get("appointment_status") or "")
    shipment_status = str((shipment or {}).get("current_status") or "")

    # R0 -- terminal. Nothing to suggest and nothing legal to suggest it with.
    if status in TERMINAL_STATUSES:
        abstain = _abstain("ALREADY_TERMINAL")

    # R1 -- the shipment itself is gone. `flows-and-states.md` Flow 1 step 5 names this exact case
    # as the difference between Cancel and Resolve: "the escalation no longer applies — e.g. the
    # shipment itself was cancelled elsewhere." Highest priority because it is decisive regardless
    # of reason: no reason-specific work is worth doing on a cancelled shipment.
    elif shipment_status == "CANCELLED" and available(CANCEL):
        recommended, confidence = CANCEL, "high"
        actions[CANCEL]["arguments"] = {"reason_code": "SHIPMENT_CANCELLED"}
        rationale = (
            f"{esc.get('shipment_id')} was cancelled elsewhere, so this escalation no longer "
            "applies. Cancel is the terminal state for that — not Resolve, which would claim the "
            "underlying issue was fixed."
        )

    # R2 -- somebody else's case. `start_escalation_work` and `take_over_thread` would both return
    # NOT_OWNER, so recommending either would be recommending a refusal. Reassign is legal but
    # "take this off Priya" is a judgement this engine has no facts for. Abstain, and let the
    # evidence and the `actions` list carry the state.
    elif owned_by_other:
        abstain = _abstain("NOT_YOUR_CASE")

    # R3 -- staleness. The escalation's own problem was solved somewhere else and nobody closed the
    # case. This is the one inference in the engine a coordinator scanning a queue genuinely does
    # not have, and it is grounded in a column, not a guess: `appointments.appointment_status`.
    elif (
        escalation_type in {"NO_FEASIBLE_SLOT", "PENDING_EXPIRED_UNACTIONED"}
        and appointment_status == "CONFIRMED"
        and available(RESOLVE)
    ):
        recommended, confidence = RESOLVE, "high"
        rationale = (
            f"A confirmed appointment now exists for {esc.get('shipment_id')} "
            f"({(appointment or {}).get('appointment_id')}), so the slot problem this escalation "
            "was raised for has already been solved elsewhere."
        )

    # R4 -- nobody owns it. The floor of the lifecycle: no reason-specific action is reachable
    # until someone claims the case (§7.4: "An escalation with no owner is just a list"), and every
    # write tool except cancel/resolve refuses an unowned row. Low-information as an *action* --
    # deliberately so; the value on this row is the evidence list beside it.
    elif available(ACK):
        recommended, confidence = ACK, "high"
        rationale = (
            "Nothing else can be worked on this escalation until someone owns it — acknowledging "
            "claims it and starts the clock against your name."
        )

    # R5 -- reason-specific. Flow 1 step 4's own list, one branch per reason, each either
    # recommending a tool that exists or saying plainly that the design's stated fix has none.
    elif escalation_type == "CAPACITY_EVENT_CASCADE":
        # Flow 1 step 4's own mapping for this reason -- "request a sequencer proposal for
        # `CAPACITY_EVENT_CASCADE`" -- and, since issues #54/#49 landed, a tool that exists. This
        # branch abstained with `SEQUENCER_UNBUILT` until 2026-09-02; the abstention was a statement
        # about the tool catalog, not about the reasoning, so building the tool is the whole of the
        # change here.
        if available(SEQUENCER):
            recommended, confidence = SEQUENCER, "high"
            rationale = (
                "A capacity incident is one row covering N stranded shipments. Ops triages and "
                "requests; the sequencer computes one proposal for the whole facility and a "
                "planner applies it (D5). Nothing is re-promised by pressing this."
            )
        else:
            # Reachable only when another coordinator owns the case -- R2 catches the caller's own
            # not-owned rows earlier, so this is the admin-viewing-someone-else's-row path.
            abstain = _abstain("NO_CONFIDENT_RECOMMENDATION")

    elif escalation_type == "NOTIFICATION_UNROUTABLE":
        # edge-cases.md #6: "UNROUTABLE's resolution is never 'retry send'". There is no contact
        # editor either, so this abstains with the broken contact named in the evidence.
        abstain = _abstain("NO_TOOL_FOR_CONTACT_REPAIR")

    elif escalation_type == "NOTIFICATION_FAILED":
        abstain = _abstain("NO_TOOL_FOR_NOTIFICATION_RETRY")

    elif escalation_type == "WAREHOUSE_REPLY_CONFLICT":
        # §7.4: "Immediate, never auto-reconcile", and FR-OPS's acceptance criteria repeat it.
        abstain = _abstain("HUMAN_RECONCILIATION_REQUIRED")

    elif escalation_type == "SAFETY_OR_REGULATED":
        if available(TAKE_OVER):
            recommended, confidence = TAKE_OVER, "medium"
            rationale = (
                "§7.4 marks safety and regulated escalations human-only. Taking over the thread is "
                "how a person joins the conversation; nothing is drafted for you."
            )
        else:
            abstain = _abstain("HUMAN_JUDGEMENT_ONLY")

    elif escalation_type == "AMBIGUOUS_SHIPMENT":
        if available(TAKE_OVER):
            recommended, confidence = TAKE_OVER, "high"
            rationale = (
                "The assistant could not tell which shipment the driver means. Flow 1 names taking "
                "over the thread as this reason's resolution — a person asks, the assistant stops "
                "guessing."
            )
        elif available(POST_MESSAGE):
            recommended, confidence = POST_MESSAGE, "medium"
            rationale = (
                "You have already taken this thread over. The ambiguity is still unresolved, so "
                "the next step is your reply — write it yourself; nothing is drafted here."
            )
        else:
            abstain = _abstain("NO_THREAD_TO_TAKE_OVER")

    elif escalation_type == "LOW_CONFIDENCE_ETA":
        eta_newer = _parse_ts((eta or {}).get("created_at"))
        raised = _parse_ts(esc.get("created_at"))
        firmed_up = bool(
            eta
            and str(eta.get("confidence_code")) in {"MEDIUM", "HIGH"}
            and eta_newer
            and raised
            and eta_newer > raised
        )
        if firmed_up and available(RESOLVE):
            recommended, confidence = RESOLVE, "medium"
            rationale = (
                f"A {eta.get('confidence_code')}-confidence ETA has been declared since this was "
                "raised, so the estimate this escalation was blocked on is no longer low-confidence."
            )
        elif available(TAKE_OVER):
            recommended, confidence = TAKE_OVER, "medium"
            rationale = (
                "The ETA behind this escalation is still low-confidence and no firmer estimate has "
                "arrived. Taking over the thread lets you ask the driver directly."
            )
        else:
            abstain = _abstain("NO_CONFIDENT_RECOMMENDATION")

    elif escalation_type in {"NO_FEASIBLE_SLOT", "PENDING_EXPIRED_UNACTIONED"}:
        # Both reasons want the shipment re-planned, and re-planning is a *planner* action
        # (§7.5.1's `confirm_request` / `apply_schedule_proposal`), preserving D5's "the sequencer
        # proposes, the planner applies" split across the two-surface handoff. Ops has no
        # rescheduling tool at all, and inventing a recommendation here would send a coordinator
        # looking for a button that does not exist on their screen.
        abstain = _abstain("NO_OPS_TOOL_FOR_REPLAN")

    else:
        abstain = _abstain("NO_CONFIDENT_RECOMMENDATION")

    # Defence in depth for the one property this whole module rests on, and **currently
    # unreachable**: every branch above is already guarded by `available(...)`. It exists for the
    # rule someone adds later without a guard, which must fail *closed* -- dropping to an honest
    # abstention -- rather than promoting an entry the server would refuse into a
    # confident-looking recommendation. Cheap, and it is the exact mistake that would be invisible
    # in review.
    if recommended is not None and actions[recommended]["status"] != "available":
        recommended, rationale, confidence = None, None, None
        abstain = _abstain("NO_CONFIDENT_RECOMMENDATION")
    if recommended is not None:
        actions[recommended]["status"] = "recommended"

    return {
        "as_of": _as_of(),
        "source": "postgresql",
        "generator": GENERATOR,
        "escalation_id": esc.get("escalation_id"),
        "escalation_type": escalation_type,
        "escalation_status": status,
        "stepper_position": STEPPER_POSITIONS.get(status, 0),
        "recommended_action": recommended,
        "rationale": rationale,
        "confidence": confidence,
        "abstain_reason": abstain,
        "evidence": evidence,
        "actions": [
            {
                "action": name,
                "label": ACTION_LABELS[name],
                "status": entry["status"],
                "reason_code": entry["reason_code"],
                "arguments": entry["arguments"],
            }
            # Stable order so a client renders the same list twice for the same state, and a
            # snapshot test compares cleanly.
            for name, entry in ((n, actions[n]) for n in ACTION_LABELS)
        ],
        "payload_reason": payload.get("reason"),
    }


# ---------------------------------------------------------------------------------------------
# Orchestration -- scope check, reads, engine.
# ---------------------------------------------------------------------------------------------


async def get_resolution_suggestion(
    session: AsyncSession, ctx: ExecutionContext, escalation_id: str
) -> dict[str, Any]:
    """`GET /api/v1/operations/escalations/{escalation_id}/suggestion`.

    **Scope (M15/NFR-019).** There is no `facility_id` argument and no way to introduce one: the
    facility is read off the escalation's own row and checked with `assert_facility_visible` before
    any further read runs. `escalation_id` is a *selector within* the caller's scope, exactly the
    shape §7.5's opening principle permits ("Where an id appears, it selects within the caller's
    scope and is validated against it"), not a scope argument.

    **`assert_facility_visible`, not `assert_facility_write_scope`.** This endpoint writes nothing,
    so gating it on write authority would refuse the global read-only personas
    (`TRANSPORT_MANAGER`, `REGIONAL_OPERATIONS_HEAD`) a view of the reasoning behind a case they
    can already read in the queue. `repositories/scope.py`'s own docstring is explicit that the two
    tiers must not be collapsed; using the read tier for a read is that rule applied, not relaxed.

    **No `Idempotency-Key`.** §7.5's third principle attaches idempotency keys to "anything that
    consumes capacity". This consumes nothing and mutates nothing; requiring a key here would be
    ceremony, and it would also be a lie about what the endpoint does.
    """
    escalation = await copilot_repo.get_escalation_with_thread(session, escalation_id)
    if escalation is None:
        raise AppError(
            f"Escalation '{escalation_id}' not found.", code="NOT_FOUND", status_code=404
        )
    assert_facility_visible(ctx, str(escalation["facility_id"]))

    try:
        payload = json.loads(escalation.get("payload_json") or "{}")
    except (TypeError, ValueError):
        # A payload that will not parse costs the reason-specific evidence, not the response.
        payload = {}
    if not isinstance(payload, dict):
        payload = {}

    shipment_id = str(escalation["shipment_id"])
    inputs: dict[str, Any] = {
        "escalation": escalation,
        "payload": payload,
        "shipment": await copilot_repo.get_shipment_state(session, shipment_id),
        "appointment": await copilot_repo.get_current_appointment(session, shipment_id),
        "latest_eta": await copilot_repo.get_latest_eta_update(session, shipment_id),
        "last_message": None,
        "unroutable_contacts": [],
    }

    thread_id = escalation.get("thread_id")
    if thread_id:
        inputs["last_message"] = await copilot_repo.get_last_thread_message(session, str(thread_id))
    if str(escalation.get("escalation_type")) == "NOTIFICATION_UNROUTABLE":
        inputs["unroutable_contacts"] = await copilot_repo.list_unroutable_contacts(
            session, str(escalation["facility_id"])
        )

    return build_suggestion(
        inputs, caller_user_id=ctx.user_id, caller_is_admin=ctx.is_admin
    )
