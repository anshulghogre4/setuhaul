from __future__ import annotations

import hashlib
import json
from datetime import datetime, time, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import bindparam, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.core.execution_context import ExecutionContext
from app.repositories.scope import assert_shipment_visible
from app.scheduling.constraints import load_scheduling_constraints

ACTIVE_APPOINTMENT_STATUSES = frozenset({"PENDING_CONFIRMATION", "CONFIRMED", "IN_PROGRESS"})
CANCELLED_SHIPMENT_STATUSES = frozenset({"COMPLETED", "CANCELLED"})
PRIORITY_RANK = {"CRITICAL": 0, "HIGH": 1, "NORMAL": 2, "LOW": 3}

# SOLUTION_DESIGN.md section 5 Stage 0: the search horizon is explicit and multi-day --
# "a rolling horizon, default 48 hours from the effective ETA ... never unbounded, because
# an option five days out is noise, not an option." Exposed as a find_feasible_slots
# parameter so a per-facility override can be threaded through later without a signature
# change; there is no facility-level horizon column in the schema yet.
SEARCH_HORIZON_HOURS = 48

# Stage 0's three mutually exclusive outcomes. Only NO_FEASIBLE_SLOT escalates
# (SOLUTION_DESIGN.md section 5 Stage 0 table, and section 7.4's NO_FEASIBLE_SLOT row:
# "same-day exhaustion is NO_SAME_DAY_SLOT, which is not an escalation").
OUTCOME_FEASIBLE = "FEASIBLE"
OUTCOME_NO_SAME_DAY_SLOT = "NO_SAME_DAY_SLOT"
OUTCOME_NO_FEASIBLE_SLOT = "NO_FEASIBLE_SLOT"

# driver_exceptions rows in these states are historical: their acceptable-time window is a
# record of a past constraint, not a live one. Same exclusion set escalation_service.py
# already uses when cascading a resolution across a shipment's exceptions.
INACTIVE_EXCEPTION_STATUSES = ("RESOLVED", "CANCELLED", "DUPLICATE")

# facility_rules.rule_type values this engine can evaluate mechanically. Deliberately a
# closed set: an unrecognised rule_type is ignored rather than guessed at, because
# rule_value is free text and the operational meaning lives in the human-readable
# description column (SOLUTION_DESIGN.md section 5 Stage 1, "facility rule evaluation with
# time-bounded effectivity").
FACILITY_RULE_LAST_NEW_START = "LAST_NEW_START_TIME"
FACILITY_RULE_HEAVY_DOCK_KG = "HEAVY_DOCK_REQUIRED_KG"
FACILITY_RULE_REEFER_DOCK = "REEFER_DOCK_REQUIRED"

# ---------------------------------------------------------------------------
# Option-card differentiator (E5.1 / issue #36, owner "Fork A", 2026-08-27)
# ---------------------------------------------------------------------------
# UI-UX/01-driver-chat/components.md section 2 and screens.md section 4 both require
# exactly one short differentiator line per option card -- and both say it is
# "never computed by the interface" (U48: the interface renders receipts, it never
# reasons). Before this change no such string existed anywhere in the backend:
# ranking_factors carries raw numbers, and ranking_explanation carries four
# long internal-voice sentences that do not fit a 340px card. The owner closed
# that gap by putting the label on the server, which is what these constants and
# `assign_differentiators` are.
#
# The vocabulary is CLOSED and is exactly the three labels the design names. It is
# deliberately not open-ended: a free-text label would put ranking language back
# into something that can drift from what the ranker actually did.
DIFFERENTIATOR_SOONEST = "soonest"
DIFFERENTIATOR_NO_WAITING = "no waiting"
DIFFERENTIATOR_MOST_BUFFER = "most buffer"
DIFFERENTIATOR_VOCABULARY = frozenset(
    {DIFFERENTIATOR_SOONEST, DIFFERENTIATOR_NO_WAITING, DIFFERENTIATOR_MOST_BUFFER}
)

# "no waiting" has to be TRUE, not merely comparatively-least. An option whose
# feasible start is 100 minutes after the driver's ETA is not "no waiting" just
# because the alternatives are worse -- printing that on a card is precisely the
# mis-promise this product exists to remove. So the label is gated on a real
# threshold as well as on being the minimum in the set.
# Source: assumption, untested. No documented "acceptable dwell before unload"
# policy exists in constraints.json or facility_rules; 15 minutes is the value
# used here and it is stated as an assumption rather than presented as policy.
NO_WAITING_MAX_MINUTES = 15

# ---------------------------------------------------------------------------
# Fairness term (A-G1 / issue #69, SOLUTION_DESIGN.md D7, 2026-08-29)
# ---------------------------------------------------------------------------
# D7: "the formula therefore *defines* a per-carrier displacement penalty term with
# weight `w_fairness = 0`, so the shipped policy is exactly the specification above
# ... while the term has a real home and a policy version to land in if the data
# turns ugly. Enabling the term is a policy decision with an audit trail, not a
# code change."
#
# Before this change the term had no home at all: `constraints.json`'s `score_weights`
# carried four coefficients plus two caps and `_rank_slot` had no fairness input, so
# "defaulted off" was indistinguishable from "absent" -- and an admin who typed a
# `w_fairness` into `POST /admin/policy/simulate` got it silently dropped.
#
# WHAT THE TERM MEASURES, stated precisely because D7 only names it:
#   `carrier_concentration` = how many OTHER active appointments this shipment's
#   carrier already holds at this facility on the candidate interval's own
#   facility-local date. That is the per-day, per-facility form of D7's own canary
#   metric ("share of contested slots won per carrier per facility per day").
#
# WHY PER LOCAL DATE and not simply per carrier: Stage 2 ranks one shipment's own
# candidate slots against each other. A quantity that is constant across that pool
# (a bare per-carrier count) can never change which slot a driver is offered, so it
# would be a term in name only. Keying on the candidate's local date makes it vary
# across the 48-hour horizon -- a carrier that already owns today's evening capacity
# is pushed toward tomorrow morning, which is exactly the displacement D7 describes.
#
# SIGN: `w_fairness` is expected NEGATIVE when enabled, matching the sign convention
# the other penalties already use (`wait_after_eta_per_minute: -6`,
# `compatible_but_not_exact_dock_penalty: -25`). It ships at 0.
WEIGHT_FAIRNESS = "w_fairness"


class FeasibleSlotOption(BaseModel):
    slot_id: str
    facility_id: str
    dock_id: str
    dock_code: str
    dock_type: str
    slot_start_ts: str
    slot_end_ts: str
    feasible_start_ts: str
    feasible_end_ts: str
    # Stage 0: "Every offered interval carries its date, and the SHOWN template renders it"
    # (SOLUTION_DESIGN.md section 5). The ISO timestamps above carry a UTC offset, so their
    # date component is NOT always the facility-local date a driver would recognise -- a
    # 2026-08-16T19:00:00+00:00 slot is 2026-08-17 in Asia/Kolkata. slot_local_date is the
    # facility-local calendar date, which is the value any driver-facing renderer must use.
    slot_local_date: str = ""
    is_same_day: bool = True
    rank_score: int
    ranking_factors: dict[str, Any]
    ranking_explanation: list[str]
    checked_constraints: list[str]
    option_status: str = "DISPLAYED_NOT_RESERVED"
    # E5.1 Fork A. One short comparative label from DIFFERENTIATOR_VOCABULARY, or ""
    # when no label in the closed vocabulary is TRUE of this option. Empty is a real
    # answer, not a missing one: the renderer omits the line rather than inventing a
    # fourth phrase (data-formatting.md's blank-vs-zero rule, U81).
    #
    # Deliberately NOT set by evaluate_candidate_slot: the label is comparative
    # ("soonest" only means anything against the set it is shown with), and
    # evaluate_candidate_slot only ever sees one candidate at a time and is also
    # called by allocation.py's single-slot revalidation path, which has no set to
    # compare against. It is assigned once, in find_feasible_slots, after the sort
    # and the truncate -- see assign_differentiators.
    differentiator: str = ""


class InfeasibleSlotReason(BaseModel):
    slot_id: str | None = None
    failure_code: str
    message: str


class FeasibleSlotsResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    as_of: str
    source: str = "postgresql"
    freshness: str = "live"
    policy_version: str
    recommendation_id: str
    shipment_id: str
    facility_id: str
    effective_eta_ts: str
    eta_source: str
    expected_unload_min: int
    # Stage 0 outcome split. FEASIBLE / NO_SAME_DAY_SLOT / NO_FEASIBLE_SLOT -- see the
    # OUTCOME_* constants. Callers must branch on this rather than on `escalation is None`,
    # because NO_SAME_DAY_SLOT deliberately returns options AND no escalation.
    outcome: str = OUTCOME_FEASIBLE
    search_horizon_hours: int = SEARCH_HORIZON_HOURS
    search_horizon_end_ts: str = ""
    eta_local_date: str = ""
    same_day_option_count: int = 0
    options_are_reserved: bool = False
    options: list[FeasibleSlotOption]
    rejected_reasons: list[InfeasibleSlotReason]
    escalation: dict[str, Any] | None = None
    current_active_appointment: dict[str, Any] | None = None
    note: str = (
        "Displayed options are not reserved. A later request/hold/confirm flow must "
        "transactionally revalidate the selected slot."
    )


def _as_of() -> str:
    return datetime.now(timezone.utc).isoformat()


def recommendation_id_for(
    *,
    shipment_id: str,
    policy_version: str,
    effective_eta_ts: str,
    option_slot_ids: list[str],
) -> str:
    """Build a deterministic displayed-options fingerprint, never a reservation."""
    option_part = ",".join(option_slot_ids) if option_slot_ids else "NOSLOT"
    source = f"{shipment_id}|{policy_version}|{effective_eta_ts}|{option_part}"
    return f"REC-{hashlib.sha256(source.encode('utf-8')).hexdigest()[:24]}"


def _parse_timestamp(value: str) -> datetime:
    raw = value.strip()
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    parsed = datetime.fromisoformat(raw)
    if parsed.tzinfo is None:
        raise ValueError("Timestamp must include timezone offset.")
    return parsed


def _coerce_timestamp(value: Any) -> datetime | None:
    """Accept either a real timestamptz (asyncpg hands back datetime) or an ISO string.

    Needed because the six tables converted by migration 20260823060000 now return
    datetime objects while facility_rules and driver_exceptions are still TEXT columns,
    so a single feasibility call sees both shapes in the same request.
    """
    if value is None:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo is not None else None
    raw = str(value).strip()
    if not raw:
        return None
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError:
        return None
    # A naive result means the stored text carried no offset (e.g. facility_rules'
    # '2026-01-01'). Returning it would silently produce naive/aware comparison errors, so
    # the caller is told "not a usable instant" and applies its own timezone.
    return parsed if parsed.tzinfo is not None else None


def _parse_local_time(value: str) -> time:
    return time.fromisoformat(value.strip())


def _to_local(moment: datetime, tz_name: str) -> datetime:
    return moment.astimezone(ZoneInfo(tz_name))


def active_facility_rules(rules: list[dict[str, Any]], *, at: datetime, tz_name: str) -> list[dict[str, Any]]:
    """Filter facility rules to those in force at `at`.

    SOLUTION_DESIGN.md section 5 Stage 1 requires "facility rule evaluation with
    time-bounded effectivity" -- facility_rules.effective_from/to. Those two columns are
    still TEXT and the live data carries two shapes: a bare date ('2026-01-01', from the
    original seed) and a full offset-bearing ISO timestamp ('2026-08-10T00:00:00+05:30',
    from the demo-day overlay). A bare date is read as facility-local midnight, which is
    what a warehouse rule author means by "effective from the 1st".

    Callers pass only rules already filtered to this facility. Rule absence is permission,
    not inheritance (section 5 Stage 1): FAC-GGN-01 defines no LAST_NEW_START_TIME and must
    never inherit Jaipur's, so nothing here back-fills a missing rule_type from elsewhere.

    **What "time-bounded effectivity" does and does NOT mean here** (A-G3 / issue #71,
    corrected 2026-08-29 -- `06-admin-console/screens.md` section 3 previously claimed more
    than this function delivers):

      SUPPORTED -- a single ABSOLUTE window, to whatever precision the stored text carries.
      '2026-08-10T18:00:00+05:30' really is an 18:00 boundary, so a rule can genuinely be
      scoped to part of one day. This is intraday in the literal sense.

      NOT SUPPORTED -- a RECURRING window. There is no day-of-week concept and no weekly
      pattern anywhere in this evaluation: "Weekdays only, 18:00-23:59" cannot be expressed,
      and nothing downstream parses such a pattern out of the TEXT column.

    **Known consequence of the TEXT column, deliberately left as-is**: a non-empty
    `effective_from`/`effective_to` this function cannot parse (a recurring pattern string,
    say) yields `None` for that boundary, which means "unbounded on that side" -- so an
    unparseable window makes the rule apply ALWAYS rather than never. That is the safer of
    the two directions for this product (a rule that over-applies rejects a slot; a rule
    that under-applies lets the system promise an interval the facility forbids), and it is
    pinned by a characterisation test rather than left as an accident. Changing it, or
    supporting recurrence properly, needs real columns and therefore a migration -- see the
    issue #71 write-up.
    """
    in_force: list[dict[str, Any]] = []
    for rule in rules:
        start = parse_rule_boundary(rule.get("effective_from"), tz_name)
        end = parse_rule_boundary(rule.get("effective_to"), tz_name)
        if start is not None and at < start:
            continue
        if end is not None and at >= end:
            continue
        in_force.append(rule)
    return in_force


def parse_rule_boundary(value: Any, tz_name: str) -> datetime | None:
    """One `facility_rules.effective_from`/`effective_to` boundary as a real instant, or None.

    Extracted from `active_facility_rules`'s body unchanged so that A-G6's rule-edit impact
    preview (`admin_governance_service.get_facility_rule_impact`, issue #74) can bound its
    scan by exactly the same parse the enforcing engine uses. Reusing this rather than
    re-implementing it is the point: a preview that disagrees with the engine about when a
    rule is in force would name the wrong appointments.

    None means "no bound on this side" -- for an empty value, and also for a non-empty value
    no accepted shape parses. See `active_facility_rules`'s docstring for why that direction
    is deliberate.
    """
    parsed = _coerce_timestamp(value)
    if parsed is None and value:
        parsed = _parse_bare_local_date(str(value), ZoneInfo(tz_name))
    return parsed


def _parse_bare_local_date(value: str, tz: ZoneInfo) -> datetime | None:
    try:
        return datetime.fromisoformat(value.strip()).replace(tzinfo=tz)
    except ValueError:
        return None


def check_facility_rules(
    *,
    shipment: dict[str, Any],
    candidate: dict[str, Any],
    rules: list[dict[str, Any]],
    feasible_start: datetime,
    tz_name: str,
) -> tuple[str, str] | None:
    """Return (rule_id, message) for the first facility rule this interval violates.

    Only the three mechanically-evaluable rule_types are enforced (see the FACILITY_RULE_*
    constants). CHECKIN_EARLY_LIMIT_MIN and NO_SHOW_GRACE_MIN are deliberately not enforced
    here: the first is a gate-arrival rule, not an offer-time rule, and the second needs an
    injected `now` (SOLUTION_DESIGN.md section 9.1 "Deterministic clock") which this engine
    does not have yet -- enforcing it against the wall clock would reject every slot in the
    frozen demo dataset.
    """
    local_start = _to_local(feasible_start, tz_name)
    for rule in rules:
        rule_type = str(rule.get("rule_type") or "")
        rule_value = str(rule.get("rule_value") or "").strip()
        rule_id = str(rule.get("rule_id") or rule_type)

        if rule_type == FACILITY_RULE_LAST_NEW_START:
            try:
                cutoff = _parse_local_time(rule_value)
            except ValueError:
                continue
            # "No new unloading operation should start after 21:00" (RULE005) -- strictly
            # after, so a start exactly at the cutoff is still permitted. The unload's real
            # start is feasible_start (max of ETA and slot start), not slot_start_ts.
            if local_start.time() > cutoff:
                return rule_id, (
                    f"Facility rule {rule_id} forbids a new unload starting after {rule_value} "
                    f"local time; this interval would start at {local_start.time().isoformat()}."
                )

        elif rule_type == FACILITY_RULE_HEAVY_DOCK_KG:
            try:
                threshold = int(float(rule_value))
            except ValueError:
                continue
            if int(shipment["load_weight_kg"]) > threshold and str(candidate["dock_type"]) != "HEAVY":
                return rule_id, (
                    f"Facility rule {rule_id} routes loads above {threshold} kg to a heavy dock; "
                    f"this load is {shipment['load_weight_kg']} kg and the dock is {candidate['dock_type']}."
                )

        elif rule_type == FACILITY_RULE_REEFER_DOCK:
            if rule_value.upper() not in {"TRUE", "1", "YES"}:
                continue
            if int(shipment["temperature_control_required"]) and not int(candidate["supports_refrigerated"]):
                return rule_id, (
                    f"Facility rule {rule_id} requires temperature-controlled loads to use a "
                    "refrigerated dock."
                )
    return None


def derive_outcome(options: list[FeasibleSlotOption]) -> str:
    """Stage 0's two-way split over an already-ranked option list.

    SOLUTION_DESIGN.md section 5 Stage 0, "Two distinct outcomes, only one of which is an
    escalation": NO_SAME_DAY_SLOT means today is exhausted but the horizon still has
    capacity, and it is explicitly NOT an escalation; NO_FEASIBLE_SLOT means the whole
    horizon is exhausted, and it is. Callers must branch on this rather than on
    `escalation is None`, and must never treat an empty same-day set as an escalation on
    its own.
    """
    if not options:
        return OUTCOME_NO_FEASIBLE_SLOT
    if not any(option.is_same_day for option in options):
        return OUTCOME_NO_SAME_DAY_SLOT
    return OUTCOME_FEASIBLE


def check_driver_window(
    *,
    driver_window: dict[str, Any],
    feasible_start: datetime,
    feasible_end: datetime,
) -> str | None:
    """Enforce both ends of the driver's own acceptable window.

    SOLUTION_DESIGN.md section 5 Stage 1: latest_acceptable_ts ("I must leave by 9 PM",
    EXC002) *and* earliest_acceptable_ts are both binding -- "an interval before the driver
    can physically be there is not an option". Sourced from driver_exceptions; when a
    shipment has several live exceptions the caller intersects them (latest MAX of the
    earliests, earliest MIN of the latests), so the tightest stated constraint wins.
    """
    earliest = _coerce_timestamp(driver_window.get("earliest_acceptable_ts"))
    latest = _coerce_timestamp(driver_window.get("latest_acceptable_ts"))
    if earliest is not None and feasible_start < earliest:
        return (
            f"Interval starts {feasible_start.isoformat()}, before the driver's earliest "
            f"acceptable arrival {earliest.isoformat()}."
        )
    if latest is not None and feasible_end > latest:
        return (
            f"Unload would finish {feasible_end.isoformat()}, after the driver's latest "
            f"acceptable time {latest.isoformat()}."
        )
    return None


def _facility_window_ok(start_dt: datetime, end_dt: datetime, *, tz_name: str, open_time: str, close_time: str) -> bool:
    tz = ZoneInfo(tz_name)
    local_start = start_dt.astimezone(tz)
    local_end = end_dt.astimezone(tz)
    if local_start.date() != local_end.date():
        return False
    return _parse_local_time(open_time) <= local_start.time() and local_end.time() <= _parse_local_time(close_time)


def _dock_type_ok(required: str, actual: str) -> bool:
    return required == "ANY" or required == actual


def _minutes_between(start_dt: datetime, end_dt: datetime) -> int:
    return int((end_dt.timestamp() - start_dt.timestamp()) // 60)


def _rank_slot(
    *,
    shipment: dict[str, Any],
    eta_dt: datetime,
    candidate: dict[str, Any],
    feasible_start: datetime,
    feasible_end: datetime,
    slot_end: datetime,
    carrier_concentration: int = 0,
) -> tuple[int, dict[str, Any]]:
    """Stage 2's deterministic weighted score for one candidate interval.

    `carrier_concentration` defaults to 0, which is what every caller outside
    `find_feasible_slots` passes: `allocation.py`'s transactional revalidation and
    `explain_slot_eligibility` both evaluate ONE interval, where a comparative fairness
    penalty has nothing to compare against and no effect on the yes/no answer they produce.
    Combined with the shipped `w_fairness = 0` this keeps the score those paths compute
    identical to the score `find_feasible_slots` computed when it offered the interval.
    """
    ranking_policy = load_scheduling_constraints().ranking_policy
    priority_scores = ranking_policy.priority_scores or {
        "CRITICAL": 4000,
        "HIGH": 3000,
        "NORMAL": 2000,
        "LOW": 1000,
        "UNKNOWN": 500,
    }
    weights = ranking_policy.score_weights
    priority_code = str(shipment.get("priority_code") or "NORMAL")
    original_eta_raw = shipment.get("original_eta_ts")
    original_eta_dt = _parse_timestamp(str(original_eta_raw)) if original_eta_raw else eta_dt
    lateness_minutes = max(0, _minutes_between(original_eta_dt, eta_dt))
    wait_after_eta_minutes = max(0, _minutes_between(eta_dt, feasible_start))
    fit_slack_minutes = max(0, _minutes_between(feasible_end, slot_end))
    exact_dock_type_match = str(shipment["required_dock_type"]) == str(candidate["dock_type"])
    disruption_score = 0 if exact_dock_type_match else abs(weights.get("compatible_but_not_exact_dock_penalty", -25))
    lateness_cap = weights.get("lateness_cap_minutes", 720)
    fit_slack_cap = weights.get("fit_slack_cap_minutes", 120)
    # D7's per-carrier displacement penalty. `w_fairness` ships at 0, so this product is
    # exactly 0 and the score below is arithmetically identical to the pre-#69 formula --
    # pinned by test_scheduling_feasibility.py's byte-identity test, not merely asserted.
    w_fairness = weights.get(WEIGHT_FAIRNESS, 0)
    fairness_penalty = w_fairness * carrier_concentration

    score = (
        priority_scores.get(priority_code, priority_scores.get("UNKNOWN", 500))
        + min(lateness_minutes, lateness_cap) * weights.get("lateness_per_minute", 4)
        + wait_after_eta_minutes * weights.get("wait_after_eta_per_minute", -6)
        + min(fit_slack_minutes, fit_slack_cap) * weights.get("fit_slack_per_minute", 1)
        + (0 if exact_dock_type_match else weights.get("compatible_but_not_exact_dock_penalty", -25))
        + fairness_penalty
    )
    return score, {
        "priority_code": priority_code,
        "priority_score": priority_scores.get(priority_code, priority_scores.get("UNKNOWN", 500)),
        "lateness_minutes": lateness_minutes,
        "wait_after_eta_minutes": wait_after_eta_minutes,
        "fit_slack_minutes": fit_slack_minutes,
        "dock_match": "exact" if exact_dock_type_match else "compatible",
        "operational_disruption_score": disruption_score,
        # Reported ALWAYS, including as a pair of zeroes. A decision receipt that omits a
        # term because it evaluated to zero is the same silent-ignore failure #69 exists to
        # remove -- "the fairness term contributed nothing" and "there is no fairness term"
        # must be distinguishable by reading the receipt.
        "carrier_concentration": carrier_concentration,
        "fairness_penalty": fairness_penalty,
        "stable_tiebreaker": f"{shipment['shipment_id']}:{candidate['slot_id']}",
    }


def _explain_option(
    *,
    shipment: dict[str, Any],
    eta_dt: datetime,
    option: dict[str, Any],
    ranking_factors: dict[str, Any],
) -> list[str]:
    explanation = [
        f"Latest authoritative ETA {eta_dt.isoformat()} fits inside this slot with unload duration.",
        f"Dock {option['dock_code']} is compatible with required dock type {shipment['required_dock_type']}.",
        "No active appointment currently occupies the slot.",
        (
            "Ranked by deterministic policy: priority "
            f"{ranking_factors['priority_code']}, lateness {ranking_factors['lateness_minutes']} min, "
            f"wait after ETA {ranking_factors['wait_after_eta_minutes']} min, "
            f"fit slack {ranking_factors['fit_slack_minutes']} min, "
            f"dock match {ranking_factors['dock_match']}."
        ),
    ]
    # Prose is driver-facing (section 12.1 Q11's explanation is generated from this list), so the
    # fairness sentence appears only when the term actually moved the score. The structured
    # `ranking_factors` above always carries it -- that is the auditable receipt; this is copy.
    if ranking_factors.get("fairness_penalty"):
        explanation.append(
            "Fairness term applied (D7): this carrier already holds "
            f"{ranking_factors['carrier_concentration']} other appointment(s) at this facility on "
            f"this date, for a score adjustment of {ranking_factors['fairness_penalty']}."
        )
    return explanation


def assign_differentiators(options: list[FeasibleSlotOption]) -> None:
    """Stamp one comparative differentiator label onto each displayed option, in place.

    E5.1 / issue #36, owner "Fork A" (2026-08-27). `01-driver-chat/components.md` section 2
    requires one differentiator per option card and forbids the interface computing it
    (U48). This is the server side of that contract.

    Called once per option SET, after ranking and truncation, because every label in the
    vocabulary is comparative -- "soonest" is a claim about this card set, not about a slot.
    That is also why it cannot live in `evaluate_candidate_slot`: that function is shared
    with `allocation.py`'s single-slot revalidation, which has no set.

    Assignment is a fixed pass order, each label claimed by at most one option, an already
    labelled option skipped. Ties break on `slot_id` so the same input always produces the
    same labels (the same determinism requirement `recommendation_id_for` exists for):

      1. "soonest"     -> earliest `feasible_start_ts`.
      2. "no waiting"  -> smallest `wait_after_eta_minutes`, AND that value must actually
                          be <= NO_WAITING_MAX_MINUTES. Comparative-least is not enough;
                          see the constant.
      3. "most buffer" -> largest `fit_slack_minutes`, AND strictly larger than every other
                          option's. "Most" is false in a tie, so nothing is labelled.

    Anything left over keeps "" -- there is no fourth comparative fact in the vocabulary,
    and a card with no differentiator line is honest where an invented one is not.
    """
    if not options:
        return

    unlabelled = {option.slot_id: option for option in options}

    def _claim(candidate: FeasibleSlotOption | None, label: str) -> None:
        if candidate is None:
            return
        candidate.differentiator = label
        unlabelled.pop(candidate.slot_id, None)

    soonest = min(
        unlabelled.values(),
        key=lambda o: (_parse_timestamp(o.feasible_start_ts), o.slot_id),
    )
    _claim(soonest, DIFFERENTIATOR_SOONEST)

    if unlabelled:
        least_wait = min(
            unlabelled.values(),
            key=lambda o: (int(o.ranking_factors.get("wait_after_eta_minutes", 0)), o.slot_id),
        )
        if int(least_wait.ranking_factors.get("wait_after_eta_minutes", 0)) <= NO_WAITING_MAX_MINUTES:
            _claim(least_wait, DIFFERENTIATOR_NO_WAITING)

    if unlabelled:
        def _slack(option: FeasibleSlotOption) -> int:
            return int(option.ranking_factors.get("fit_slack_minutes", 0))

        # sorted(-slack, slot_id) rather than max(): max()'s tie-break would need an
        # inverted string key to stay deterministic, which reads worse than this.
        most_buffer = sorted(unlabelled.values(), key=lambda o: (-_slack(o), o.slot_id))[0]
        top = _slack(most_buffer)
        # Strictly greater than every OTHER remaining option, so "most" is a true claim.
        if all(_slack(other) < top for other in unlabelled.values() if other.slot_id != most_buffer.slot_id):
            _claim(most_buffer, DIFFERENTIATOR_MOST_BUFFER)


def evaluate_candidate_slot(
    *,
    shipment: dict[str, Any],
    facility: dict[str, Any],
    eta_dt: datetime,
    candidate: dict[str, Any],
    checked_constraints: list[str],
    facility_rules: list[dict[str, Any]] | None = None,
    driver_window: dict[str, Any] | None = None,
    carrier_concentration_by_local_date: dict[str, int] | None = None,
) -> tuple[FeasibleSlotOption | None, InfeasibleSlotReason | None]:
    """Stage 1 eligibility guard for one candidate interval.

    `facility_rules` and `driver_window` are optional because this function is also called
    by allocation.py's transactional revalidation path, which does not fetch them yet.
    Passing None means those two Stage-1 invariants are NOT evaluated for that call --
    see the E1.4 follow-up note: request_slot can still claim an interval that
    find_feasible_slots would have filtered out on a facility rule or a driver window.

    `carrier_concentration_by_local_date` is D7's fairness input (issue #69), keyed by the
    facility-LOCAL date of the interval's real start. It is None on every path except
    `find_feasible_slots` with a non-zero `w_fairness`, so the default costs one falsy
    check and nothing else -- see WEIGHT_FAIRNESS's comment for why the key is a local date
    rather than the carrier alone.
    """
    slot_id = str(candidate["slot_id"])

    # Cheap, timestamp-independent checks run first so a slot that is already
    # unavailable (occupied, closed, incompatible) is rejected without any datetime work.
    # This ordering originally also protected against unparseable TEXT timestamps
    # (truncated seconds fields like "10:30:0" in legacy background-inventory rows);
    # migration 20260823060000 converted slot_start_ts/slot_end_ts to real timestamptz, so
    # Postgres now normalises those values and the parse can no longer fail. The
    # cheap-first ordering is kept because it is still the cheaper order.
    if candidate["slot_status"] != "OPEN":
        return None, InfeasibleSlotReason(
            slot_id=slot_id,
            failure_code="SLOT_NOT_OPEN",
            message=f"Slot status is {candidate['slot_status']}.",
        )
    if candidate.get("active_appointment_id"):
        return None, InfeasibleSlotReason(
            slot_id=slot_id,
            failure_code="SLOT_CAPACITY_UNAVAILABLE",
            message="An active appointment already occupies this slot.",
        )
    if candidate.get("active_dock_event_id"):
        return None, InfeasibleSlotReason(
            slot_id=slot_id,
            failure_code="DOCK_UNAVAILABLE",
            message="A dock event overlaps this slot.",
        )
    if candidate["dock_status"] != "ACTIVE":
        return None, InfeasibleSlotReason(
            slot_id=slot_id,
            failure_code="DOCK_UNAVAILABLE",
            message=f"Dock status is {candidate['dock_status']}.",
        )
    if not _dock_type_ok(str(shipment["required_dock_type"]), str(candidate["dock_type"])):
        return None, InfeasibleSlotReason(
            slot_id=slot_id,
            failure_code="DOCK_INCOMPATIBLE_VEHICLE",
            message=f"Shipment requires {shipment['required_dock_type']} dock, candidate is {candidate['dock_type']}.",
        )
    if int(shipment["temperature_control_required"]) and not int(candidate["supports_refrigerated"]):
        return None, InfeasibleSlotReason(
            slot_id=slot_id,
            failure_code="DOCK_INCOMPATIBLE_LOAD",
            message="Temperature-controlled shipment requires refrigerated dock support.",
        )
    if int(shipment["load_weight_kg"]) > int(candidate["max_vehicle_weight_kg"]):
        return None, InfeasibleSlotReason(
            slot_id=slot_id,
            failure_code="DOCK_INCOMPATIBLE_VEHICLE",
            message="Shipment load exceeds dock vehicle weight limit.",
        )

    slot_start = _parse_timestamp(str(candidate["slot_start_ts"]))
    slot_end = _parse_timestamp(str(candidate["slot_end_ts"]))
    unload_min = int(shipment["expected_unload_min"])
    feasible_start = max(eta_dt, slot_start)
    feasible_end = feasible_start.timestamp() + unload_min * 60
    feasible_end_dt = datetime.fromtimestamp(feasible_end, tz=feasible_start.tzinfo)

    if feasible_end_dt > slot_end:
        return None, InfeasibleSlotReason(
            slot_id=slot_id,
            failure_code="ETA_AFTER_SLOT_WINDOW",
            message="ETA plus unload duration does not fit inside the slot window.",
        )
    if not _facility_window_ok(
        slot_start,
        slot_end,
        tz_name=str(facility["timezone"]),
        open_time=str(facility["open_time"]),
        close_time=str(facility["close_time"]),
    ):
        return None, InfeasibleSlotReason(
            slot_id=slot_id,
            failure_code="FACILITY_CLOSED",
            message="Slot falls outside facility operating hours.",
        )

    facility_tz = str(facility["timezone"])
    if facility_rules:
        rule_hit = check_facility_rules(
            shipment=shipment,
            candidate=candidate,
            rules=active_facility_rules(facility_rules, at=feasible_start, tz_name=facility_tz),
            feasible_start=feasible_start,
            tz_name=facility_tz,
        )
        if rule_hit is not None:
            # rule_id is returned separately (and already named inside the message) because
            # section 7.1's explain_slot_eligibility contract wants it as a structured field,
            # not only as prose.
            _rule_id, message = rule_hit
            return None, InfeasibleSlotReason(
                slot_id=slot_id,
                failure_code="FACILITY_RULE_VIOLATION",
                message=message,
            )
    if driver_window:
        window_hit = check_driver_window(
            driver_window=driver_window,
            feasible_start=feasible_start,
            feasible_end=feasible_end_dt,
        )
        if window_hit is not None:
            return None, InfeasibleSlotReason(
                slot_id=slot_id,
                failure_code="DRIVER_WINDOW_VIOLATION",
                message=window_hit,
            )

    # The interval's own facility-local date -- computed once here and reused for both the
    # fairness lookup and `slot_local_date` below, rather than converting twice.
    local_date = _to_local(feasible_start, facility_tz).date().isoformat()
    carrier_concentration = (
        int(carrier_concentration_by_local_date.get(local_date, 0))
        if carrier_concentration_by_local_date
        else 0
    )

    rank_score, ranking_factors = _rank_slot(
        shipment=shipment,
        eta_dt=eta_dt,
        candidate=candidate,
        feasible_start=feasible_start,
        feasible_end=feasible_end_dt,
        slot_end=slot_end,
        carrier_concentration=carrier_concentration,
    )

    return (
        FeasibleSlotOption(
            slot_id=slot_id,
            facility_id=str(candidate["facility_id"]),
            dock_id=str(candidate["dock_id"]),
            dock_code=str(candidate["dock_code"]),
            dock_type=str(candidate["dock_type"]),
            slot_start_ts=slot_start.isoformat(),
            slot_end_ts=slot_end.isoformat(),
            feasible_start_ts=feasible_start.isoformat(),
            feasible_end_ts=feasible_end_dt.isoformat(),
            # Facility-local date of the actual unload start, and whether that lands on the
            # same local day as the effective ETA. Stage 0 uses is_same_day to decide
            # FEASIBLE vs NO_SAME_DAY_SLOT; the renderer uses slot_local_date so an offered
            # interval can never be shown without its date.
            slot_local_date=local_date,
            is_same_day=(
                _to_local(feasible_start, facility_tz).date() == _to_local(eta_dt, facility_tz).date()
            ),
            rank_score=rank_score,
            ranking_factors=ranking_factors,
            ranking_explanation=_explain_option(
                shipment=shipment,
                eta_dt=eta_dt,
                option=candidate,
                ranking_factors=ranking_factors,
            ),
            checked_constraints=checked_constraints,
        ),
        None,
    )


def _assert_scope(ctx: ExecutionContext, shipment: dict[str, Any]) -> None:
    # find_feasible_slots only reads and ranks, so this uses the read tier (require_write=False,
    # the default): the global personas' visibility applies, their write authority does not.
    # E2.2 (issue #22): rule owned by repositories.scope; this is the row-unpacking adapter.
    assert_shipment_visible(
        ctx,
        shipment_driver_id=shipment["driver_id"],
        shipment_facility_id=shipment["destination_facility_id"],
    )


async def find_feasible_slots(
    session: AsyncSession,
    ctx: ExecutionContext,
    shipment_id: str,
    *,
    limit: int = 5,
    horizon_hours: int = SEARCH_HORIZON_HOURS,
) -> FeasibleSlotsResult:
    constraints = load_scheduling_constraints()
    checked_constraints = sorted(constraints.hard_constraint_ids())

    shipment = (
        await session.execute(
            text(
                """
                SELECT s.shipment_id, s.driver_id, s.vehicle_id, s.destination_facility_id,
                       s.carrier_id,
                       s.priority_code, s.required_dock_type, s.temperature_control_required,
                       s.load_weight_kg, s.expected_unload_min, s.current_status,
                       s.original_eta_ts, s.latest_eta_ts,
                       le.effective_eta_ts, le.eta_source, le.eta_confidence,
                       (SELECT max(de.earliest_acceptable_ts::timestamptz)
                          FROM public.driver_exceptions de
                         WHERE de.shipment_id = s.shipment_id
                           AND de.exception_status NOT IN :inactive_exception_statuses
                           AND de.earliest_acceptable_ts IS NOT NULL) AS driver_earliest_acceptable_ts,
                       (SELECT min(de.latest_acceptable_ts::timestamptz)
                          FROM public.driver_exceptions de
                         WHERE de.shipment_id = s.shipment_id
                           AND de.exception_status NOT IN :inactive_exception_statuses
                           AND de.latest_acceptable_ts IS NOT NULL) AS driver_latest_acceptable_ts
                FROM public.shipments s
                JOIN public.v_latest_eta le ON le.shipment_id = s.shipment_id
                WHERE s.shipment_id = :shipment_id
                """
            ).bindparams(bindparam("inactive_exception_statuses", expanding=True)),
            # The driver's acceptable window is fetched as two aggregates inside this
            # existing statement rather than as a separate round trip -- COMPARISON-latency
            # F16 already flags the four sequential trips this function makes, so a Stage-1
            # addition must not add a fifth. MAX(earliest)/MIN(latest) intersects several
            # live exceptions to the tightest stated window.
            #
            # These two columns are still TEXT (they were not in migration 20260823060000's
            # six tables), so the ::timestamptz cast is required for a correct MIN/MAX --
            # lexicographic text ordering is not chronological when offsets differ. Unlike
            # the candidate-slot query below, this cast is harmless: the filter here is an
            # equality on shipment_id, so nothing depends on an index over the cast column.
            {
                "shipment_id": shipment_id,
                "inactive_exception_statuses": list(INACTIVE_EXCEPTION_STATUSES),
            },
        )
    ).mappings().first()
    if shipment is None:
        raise AppError("Shipment not found.", code="NOT_FOUND", status_code=404)
    shipment_data = dict(shipment)
    _assert_scope(ctx, shipment_data)

    if shipment_data["current_status"] in CANCELLED_SHIPMENT_STATUSES:
        raise AppError(
            "Shipment is not eligible for slot search.",
            code="SHIPMENT_NOT_ACTIVE",
            status_code=409,
        )

    facility = (
        await session.execute(
            text(
                """
                SELECT f.facility_id, f.facility_name, f.timezone, f.open_time, f.close_time,
                       f.active_flag,
                       (SELECT coalesce(json_agg(json_build_object(
                                 'rule_id', fr.rule_id,
                                 'rule_type', fr.rule_type,
                                 'rule_value', fr.rule_value,
                                 'effective_from', fr.effective_from,
                                 'effective_to', fr.effective_to))::text, '[]')
                          FROM public.facility_rules fr
                         WHERE fr.facility_id = f.facility_id
                           AND fr.active_flag = 1) AS facility_rules_json
                FROM public.facilities f
                WHERE f.facility_id = :facility_id
                """
            ),
            # Facility rules ride along on the facility read (a correlated aggregate, not a
            # second round trip). Scoped strictly to this facility_id: SOLUTION_DESIGN.md
            # section 5 Stage 1 -- "rule absence is permission, not inheritance" -- so a
            # facility with no LAST_NEW_START_TIME must never pick up another facility's.
            {"facility_id": shipment_data["destination_facility_id"]},
        )
    ).mappings().first()
    if facility is None or not int(facility["active_flag"]):
        raise AppError("Destination facility is not active.", code="FACILITY_UNAVAILABLE", status_code=409)
    facility_data = dict(facility)
    facility_rules: list[dict[str, Any]] = json.loads(str(facility_data.pop("facility_rules_json") or "[]"))
    driver_window = {
        "earliest_acceptable_ts": shipment_data.get("driver_earliest_acceptable_ts"),
        "latest_acceptable_ts": shipment_data.get("driver_latest_acceptable_ts"),
    }

    active_appt = (
        await session.execute(
            text(
                """
                SELECT a.appointment_id, a.shipment_id, a.slot_id, a.appointment_status,
                       a.is_current, sl.facility_id, sl.dock_id, sl.slot_start_ts, sl.slot_end_ts
                FROM public.appointments a
                JOIN public.appointment_slots sl ON sl.slot_id = a.slot_id
                WHERE a.shipment_id = :shipment_id
                  AND a.is_current = 1
                  AND a.appointment_status IN ('PENDING_CONFIRMATION', 'CONFIRMED', 'IN_PROGRESS')
                ORDER BY a.updated_at DESC NULLS LAST
                LIMIT 1
                """
            ),
            {"shipment_id": shipment_id},
        )
    ).mappings().first()

    eta_dt = _parse_timestamp(str(shipment_data["effective_eta_ts"]))
    # Stage 0: bound the search to a rolling horizon measured from the effective ETA, not
    # from wall-clock now -- the whole engine is ETA-relative, and an ETA-relative horizon is
    # what makes "no slot today, but 06:00 tomorrow" answerable at all.
    horizon_end = eta_dt + timedelta(hours=horizon_hours)

    # D7's fairness input (issue #69). Fetched ONLY when the policy actually enables the term.
    # COMPARISON-latency F16 already flags this function's four sequential round trips, so the
    # default path must not gain a fifth: at the shipped `w_fairness = 0` this branch is a
    # dict lookup against an already-loaded constraints object and nothing more. When an admin
    # deliberately turns fairness on, one extra grouped read is the honest cost of the feature.
    carrier_concentration_by_local_date: dict[str, int] | None = None
    if constraints.ranking_policy.score_weights.get(WEIGHT_FAIRNESS, 0):
        concentration_rows = (
            await session.execute(
                text(
                    """
                    SELECT to_char(sl.slot_start_ts AT TIME ZONE :tz_name, 'YYYY-MM-DD') AS local_date,
                           CAST(count(*) AS integer) AS held_count
                    FROM public.appointments a
                    JOIN public.appointment_slots sl ON sl.slot_id = a.slot_id
                    JOIN public.shipments other ON other.shipment_id = a.shipment_id
                    WHERE a.is_current = 1
                      AND a.appointment_status IN ('PENDING_CONFIRMATION', 'CONFIRMED', 'IN_PROGRESS')
                      AND sl.facility_id = :facility_id
                      AND other.carrier_id = :carrier_id
                      AND other.shipment_id <> :shipment_id
                      AND sl.slot_start_ts >= :eta_ts
                      AND sl.slot_start_ts < :horizon_end_ts
                    GROUP BY 1
                    """
                ),
                # `AT TIME ZONE <name>` on a timestamptz yields the local wall-clock timestamp,
                # which is what makes this a facility-LOCAL calendar day rather than a UTC one --
                # the same distinction `slot_local_date` exists for. The shipment's own current
                # appointment is excluded: the term measures what the carrier ALREADY holds
                # besides this booking, not the booking being decided.
                {
                    "tz_name": str(facility_data["timezone"]),
                    "facility_id": shipment_data["destination_facility_id"],
                    "carrier_id": shipment_data["carrier_id"],
                    "shipment_id": shipment_id,
                    "eta_ts": eta_dt,
                    "horizon_end_ts": horizon_end,
                },
            )
        ).mappings().all()
        carrier_concentration_by_local_date = {
            str(row["local_date"]): int(row["held_count"]) for row in concentration_rows
        }

    candidates = (
        await session.execute(
            text(
                """
                SELECT sl.slot_id, sl.facility_id, sl.dock_id, sl.slot_start_ts, sl.slot_end_ts,
                       sl.slot_status, sl.block_reason, d.dock_code, d.dock_type,
                       d.supports_refrigerated, d.max_vehicle_weight_kg, d.dock_status,
                       a.appointment_id AS active_appointment_id,
                       de.dock_event_id AS active_dock_event_id
                FROM public.appointment_slots sl
                JOIN public.docks d ON d.dock_id = sl.dock_id
                LEFT JOIN public.appointments a
                  ON a.slot_id = sl.slot_id
                 AND a.appointment_status IN ('PENDING_CONFIRMATION', 'CONFIRMED', 'IN_PROGRESS')
                LEFT JOIN public.dock_status_events de
                  ON de.dock_id = sl.dock_id
                 AND de.event_start_ts < sl.slot_end_ts
                 AND (de.event_end_ts IS NULL OR de.event_end_ts > sl.slot_start_ts)
                WHERE sl.facility_id = :facility_id
                  AND sl.slot_end_ts > :eta_ts
                  AND sl.slot_start_ts < :horizon_end_ts
                ORDER BY sl.slot_start_ts, sl.slot_id
                LIMIT 500
                """
            ),
            # No CAST(... AS timestamptz) here any more. Migration 20260823060000 made
            # slot_start_ts/slot_end_ts real timestamptz, so the cast became a no-op and the
            # predicate/sort now hit ix_slots_facility_time
            # (facility_id, slot_start_ts, slot_end_ts) directly -- verified by
            # EXPLAIN ANALYZE against the live database, which reports
            # "Index Cond: (facility_id = ... AND slot_start_ts < ... AND slot_end_ts > ...)".
            # NFR-003's <50 ms budget: 1.5 ms for the busiest 48-hour window at FAC-JAI-01
            # (384 rows, 192 slots/day x 2 days), measured 2026-08-23.
            #
            # LIMIT is 500 rather than 200 because Stage 0 now needs the horizon's next-day
            # capacity to be visible in the same scan; 200 truncated inside a single day at
            # the busiest facility, which would have made NO_SAME_DAY_SLOT unreachable.
            {
                "facility_id": shipment_data["destination_facility_id"],
                "eta_ts": eta_dt,
                "horizon_end_ts": horizon_end,
            },
        )
    ).mappings().all()

    options: list[FeasibleSlotOption] = []
    rejected: list[InfeasibleSlotReason] = []
    for row in candidates:
        option, reason = evaluate_candidate_slot(
            shipment=shipment_data,
            facility=facility_data,
            eta_dt=eta_dt,
            candidate=dict(row),
            checked_constraints=checked_constraints,
            facility_rules=facility_rules,
            driver_window=driver_window,
            carrier_concentration_by_local_date=carrier_concentration_by_local_date,
        )
        if option:
            options.append(option)
        elif reason and len(rejected) < 20:
            rejected.append(reason)
        if len(options) >= limit:
            break

    options.sort(
        key=lambda option: (
            -option.rank_score,
            PRIORITY_RANK.get(str(shipment_data["priority_code"]), 9),
            option.ranking_factors["wait_after_eta_minutes"],
            option.ranking_factors["operational_disruption_score"],
            _parse_timestamp(option.slot_start_ts),
            option.slot_id,
        )
    )

    displayed_options = options[:limit]
    # E5.1 Fork A: after the sort AND after the truncate, because the label is a claim
    # about the set the driver actually sees. Labelling before the truncate could stamp
    # "soonest" on an option that never reaches the card set.
    assign_differentiators(displayed_options)
    same_day_option_count = sum(1 for option in displayed_options if option.is_same_day)

    # The candidate scan is ordered by slot_start_ts, so same-day intervals are always
    # evaluated before later ones: reaching a next-day option at all means the same-day set
    # was genuinely exhausted, not merely truncated by the `limit` break above. Same-day
    # still outranks next-day through the existing lateness/wait terms -- no new coefficient.
    outcome = derive_outcome(displayed_options)

    escalation = None
    if outcome == OUTCOME_NO_FEASIBLE_SLOT:
        escalation = {
            "required": True,
            "outcome": outcome,
            "shipment_id": shipment_id,
            "facility_id": shipment_data["destination_facility_id"],
            "as_of": _as_of(),
            "policy_version": constraints.policy_version,
            "checked_constraints": checked_constraints,
            "search_horizon_hours": horizon_hours,
            "search_horizon_end_ts": horizon_end.isoformat(),
            "blocking_reasons": [reason.model_dump() for reason in rejected[:10]]
            or [{"failure_code": "NO_CANDIDATE_SLOTS", "message": "No candidate slots were found."}],
            "recommended_human_queue": "OPERATIONS_EXCEPTION_QUEUE",
        }

    return FeasibleSlotsResult(
        as_of=_as_of(),
        policy_version=constraints.policy_version,
        recommendation_id=recommendation_id_for(
            shipment_id=shipment_id,
            policy_version=constraints.policy_version,
            effective_eta_ts=eta_dt.isoformat(),
            option_slot_ids=[option.slot_id for option in displayed_options],
        ),
        shipment_id=shipment_id,
        facility_id=str(shipment_data["destination_facility_id"]),
        effective_eta_ts=eta_dt.isoformat(),
        eta_source=str(shipment_data["eta_source"]),
        expected_unload_min=int(shipment_data["expected_unload_min"]),
        outcome=outcome,
        search_horizon_hours=horizon_hours,
        search_horizon_end_ts=horizon_end.isoformat(),
        eta_local_date=_to_local(eta_dt, str(facility_data["timezone"])).date().isoformat(),
        same_day_option_count=same_day_option_count,
        options=displayed_options,
        rejected_reasons=rejected,
        escalation=escalation,
        current_active_appointment=dict(active_appt) if active_appt else None,
    )


class SlotEligibilityResult(BaseModel):
    """FR-DRV-006 (E3.1, issue #25): 'eligibility answered per-invariant; browse-only, no
    exception created.' Deliberately returns the same failure_code/message shape
    evaluate_candidate_slot already produces for request_slot's own rejection path, rather
    than a third vocabulary for the same set of reasons -- a driver asking "why can't I book
    this slot" and request_slot's own 409 should name the same thing."""

    model_config = ConfigDict(extra="forbid")

    shipment_id: str
    slot_id: str
    eligible: bool
    checked_constraints: list[str]
    failure_code: str | None = None
    message: str | None = None
    explanation: list[str] = Field(default_factory=list)


async def explain_slot_eligibility(
    session: AsyncSession,
    ctx: ExecutionContext,
    shipment_id: str,
    slot_id: str,
) -> SlotEligibilityResult:
    """FR-DRV-006: answer "is this specific slot eligible, and why" without creating an
    appointment or an exception -- browse-only, per the requirement's own wording.

    Deliberately re-fetches shipment/facility/candidate rather than sharing find_feasible_slots's
    in-flight state: that function only ever holds one candidate slot's row in memory at a time
    during its scan (never the full set), so there is nothing to look up post hoc, and threading
    a "just check this one slot_id" mode through find_feasible_slots's control flow would risk
    the exact kind of change this session has repeatedly found expensive to get right in an
    already-verified function (see COMPARISON-latency F16 on that function's round-trip budget).
    A second, narrower query is the lower-risk shape for a read that a driver may call often
    while deciding, on a slot_id they already have in hand from find_feasible_slots's own output.
    """
    constraints = load_scheduling_constraints()
    checked_constraints = sorted(constraints.hard_constraint_ids())

    shipment = (
        await session.execute(
            text(
                """
                SELECT s.shipment_id, s.driver_id, s.destination_facility_id,
                       s.required_dock_type, s.temperature_control_required,
                       s.load_weight_kg, s.expected_unload_min,
                       le.effective_eta_ts,
                       (SELECT max(de.earliest_acceptable_ts::timestamptz)
                          FROM public.driver_exceptions de
                         WHERE de.shipment_id = s.shipment_id
                           AND de.exception_status NOT IN :inactive_exception_statuses
                           AND de.earliest_acceptable_ts IS NOT NULL) AS driver_earliest_acceptable_ts,
                       (SELECT min(de.latest_acceptable_ts::timestamptz)
                          FROM public.driver_exceptions de
                         WHERE de.shipment_id = s.shipment_id
                           AND de.exception_status NOT IN :inactive_exception_statuses
                           AND de.latest_acceptable_ts IS NOT NULL) AS driver_latest_acceptable_ts
                FROM public.shipments s
                JOIN public.v_latest_eta le ON le.shipment_id = s.shipment_id
                WHERE s.shipment_id = :shipment_id
                """
            ).bindparams(bindparam("inactive_exception_statuses", expanding=True)),
            {
                "shipment_id": shipment_id,
                "inactive_exception_statuses": list(INACTIVE_EXCEPTION_STATUSES),
            },
        )
    ).mappings().first()
    if shipment is None:
        raise AppError("Shipment not found.", code="NOT_FOUND", status_code=404)
    shipment_data = dict(shipment)
    assert_shipment_visible(
        ctx,
        shipment_driver_id=shipment_data.get("driver_id"),
        shipment_facility_id=str(shipment_data["destination_facility_id"]),
    )

    candidate = (
        await session.execute(
            text(
                """
                SELECT sl.slot_id, sl.facility_id, sl.dock_id, sl.slot_start_ts, sl.slot_end_ts,
                       sl.slot_status, sl.block_reason, d.dock_code, d.dock_type,
                       d.supports_refrigerated, d.max_vehicle_weight_kg, d.dock_status,
                       a.appointment_id AS active_appointment_id,
                       de.dock_event_id AS active_dock_event_id
                FROM public.appointment_slots sl
                JOIN public.docks d ON d.dock_id = sl.dock_id
                LEFT JOIN public.appointments a
                  ON a.slot_id = sl.slot_id
                 AND a.appointment_status IN ('PENDING_CONFIRMATION', 'CONFIRMED', 'IN_PROGRESS')
                LEFT JOIN public.dock_status_events de
                  ON de.dock_id = sl.dock_id
                 AND de.event_start_ts < sl.slot_end_ts
                 AND (de.event_end_ts IS NULL OR de.event_end_ts > sl.slot_start_ts)
                WHERE sl.slot_id = :slot_id AND sl.facility_id = :facility_id
                """
            ),
            {"slot_id": slot_id, "facility_id": shipment_data["destination_facility_id"]},
        )
    ).mappings().first()
    if candidate is None:
        return SlotEligibilityResult(
            shipment_id=shipment_id,
            slot_id=slot_id,
            eligible=False,
            checked_constraints=checked_constraints,
            failure_code="SLOT_NOT_FOUND",
            message="No slot with this id exists at the shipment's destination facility.",
        )
    candidate_data = dict(candidate)

    facility = (
        await session.execute(
            text(
                """
                SELECT f.facility_id, f.timezone, f.open_time, f.close_time, f.active_flag,
                       (SELECT coalesce(json_agg(json_build_object(
                                 'rule_id', fr.rule_id,
                                 'rule_type', fr.rule_type,
                                 'rule_value', fr.rule_value,
                                 'effective_from', fr.effective_from,
                                 'effective_to', fr.effective_to))::text, '[]')
                          FROM public.facility_rules fr
                         WHERE fr.facility_id = f.facility_id
                           AND fr.active_flag = 1) AS facility_rules_json
                FROM public.facilities f
                WHERE f.facility_id = :facility_id
                """
            ),
            {"facility_id": shipment_data["destination_facility_id"]},
        )
    ).mappings().first()
    if facility is None or not int(facility["active_flag"]):
        raise AppError("Destination facility is not active.", code="FACILITY_UNAVAILABLE", status_code=409)
    facility_data = dict(facility)
    facility_rules: list[dict[str, Any]] = json.loads(str(facility_data.pop("facility_rules_json") or "[]"))
    driver_window = {
        "earliest_acceptable_ts": shipment_data.get("driver_earliest_acceptable_ts"),
        "latest_acceptable_ts": shipment_data.get("driver_latest_acceptable_ts"),
    }

    eta_dt = _parse_timestamp(str(shipment_data["effective_eta_ts"]))
    option, reason = evaluate_candidate_slot(
        shipment=shipment_data,
        facility=facility_data,
        eta_dt=eta_dt,
        candidate=candidate_data,
        checked_constraints=checked_constraints,
        facility_rules=facility_rules,
        driver_window=driver_window,
    )

    if option is not None:
        return SlotEligibilityResult(
            shipment_id=shipment_id,
            slot_id=slot_id,
            eligible=True,
            checked_constraints=checked_constraints,
            explanation=option.ranking_explanation,
        )
    assert reason is not None  # evaluate_candidate_slot always returns exactly one of the two
    return SlotEligibilityResult(
        shipment_id=shipment_id,
        slot_id=slot_id,
        eligible=False,
        checked_constraints=checked_constraints,
        failure_code=reason.failure_code,
        message=reason.message,
    )
