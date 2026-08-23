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
    """
    tz = ZoneInfo(tz_name)
    in_force: list[dict[str, Any]] = []
    for rule in rules:
        start = _coerce_timestamp(rule.get("effective_from"))
        if start is None and rule.get("effective_from"):
            start = _parse_bare_local_date(str(rule["effective_from"]), tz)
        end = _coerce_timestamp(rule.get("effective_to"))
        if end is None and rule.get("effective_to"):
            end = _parse_bare_local_date(str(rule["effective_to"]), tz)
        if start is not None and at < start:
            continue
        if end is not None and at >= end:
            continue
        in_force.append(rule)
    return in_force


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
) -> tuple[int, dict[str, Any]]:
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

    score = (
        priority_scores.get(priority_code, priority_scores.get("UNKNOWN", 500))
        + min(lateness_minutes, lateness_cap) * weights.get("lateness_per_minute", 4)
        + wait_after_eta_minutes * weights.get("wait_after_eta_per_minute", -6)
        + min(fit_slack_minutes, fit_slack_cap) * weights.get("fit_slack_per_minute", 1)
        + (0 if exact_dock_type_match else weights.get("compatible_but_not_exact_dock_penalty", -25))
    )
    return score, {
        "priority_code": priority_code,
        "priority_score": priority_scores.get(priority_code, priority_scores.get("UNKNOWN", 500)),
        "lateness_minutes": lateness_minutes,
        "wait_after_eta_minutes": wait_after_eta_minutes,
        "fit_slack_minutes": fit_slack_minutes,
        "dock_match": "exact" if exact_dock_type_match else "compatible",
        "operational_disruption_score": disruption_score,
        "stable_tiebreaker": f"{shipment['shipment_id']}:{candidate['slot_id']}",
    }


def _explain_option(
    *,
    shipment: dict[str, Any],
    eta_dt: datetime,
    option: dict[str, Any],
    ranking_factors: dict[str, Any],
) -> list[str]:
    return [
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


def evaluate_candidate_slot(
    *,
    shipment: dict[str, Any],
    facility: dict[str, Any],
    eta_dt: datetime,
    candidate: dict[str, Any],
    checked_constraints: list[str],
    facility_rules: list[dict[str, Any]] | None = None,
    driver_window: dict[str, Any] | None = None,
) -> tuple[FeasibleSlotOption | None, InfeasibleSlotReason | None]:
    """Stage 1 eligibility guard for one candidate interval.

    `facility_rules` and `driver_window` are optional because this function is also called
    by allocation.py's transactional revalidation path, which does not fetch them yet.
    Passing None means those two Stage-1 invariants are NOT evaluated for that call --
    see the E1.4 follow-up note: request_slot can still claim an interval that
    find_feasible_slots would have filtered out on a facility rule or a driver window.
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

    rank_score, ranking_factors = _rank_slot(
        shipment=shipment,
        eta_dt=eta_dt,
        candidate=candidate,
        feasible_start=feasible_start,
        feasible_end=feasible_end_dt,
        slot_end=slot_end,
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
            slot_local_date=_to_local(feasible_start, facility_tz).date().isoformat(),
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
    # find_feasible_slots only reads and ranks; the global tier is read scope, not write authority.
    if ctx.is_driver:
        if shipment["driver_id"] != ctx.driver_id:
            raise AppError("Shipment not in scope.", code="FORBIDDEN", status_code=403)
        return
    if ctx.is_operator:
        if shipment["destination_facility_id"] != ctx.facility_id:
            raise AppError("Shipment not in scope.", code="FORBIDDEN", status_code=403)
        return
    if ctx.has_global_read_scope:
        return
    raise AppError("Insufficient permissions.", code="FORBIDDEN", status_code=403)


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
