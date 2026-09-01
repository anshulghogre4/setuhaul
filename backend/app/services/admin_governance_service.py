"""Admin console -- facility rules, policy, and audit. SOLUTION_DESIGN.md section 7.5.7,
FR-ADM-006 .. FR-ADM-010.

Rule-type changes go through the typed registry (`RULE_TYPES`, matching
`supabase/migrations/20260825213000_e34_policy_versions_and_rule_registry.sql`'s live `CHECK`
constraint) -- never a free string, per section 0.9 issue 10's resolution.

**`simulate_policy_weights` is a deliberate isolation choice, not an oversight**: it does not call
into `scheduling/feasibility.py`'s live ranking code (`_rank_slot`) at all, and re-implements the
same score formula locally instead (`_score`, a direct copy of `feasibility.py`'s formula). This is
the one place in this codebase where duplicating a formula is the safer choice: touching the D1
booking hot path -- the single most safety-critical code in this system -- to add a simulation
feature is a risk this tool has no reason to take. If the live formula ever changes, this copy must
be updated to match; a unit test pins both to the same output for the same inputs so drift is
caught rather than silently diverging.

**`simulate_policy_weights` is also an honest approximation of "replay the window's actual
decisions"**, not a literal one: no historical decision log exists anywhere in this system (confirmed
live 2026-08-25 -- no policy/decision/allocation-history table of any kind), so there is nothing to
literally replay. This instead re-scores each shipment's **actual current appointment** against a
handful of **other slots open today** at the same facility near the same time, under both the live
and proposed weights, and calls it a "flip" when the top-ranked slot differs. That is a current-
state proxy for "would this outcome have gone differently," not a reconstruction of the exact
candidate set that existed at the real booking moment (which cannot be recovered without a stored
snapshot). Flagged here and in the tool's own response, not silently presented as more than it is.

**Weight keys are validated against the live engine's own key set, not against a hand-written
list** (A-G1, issue #69, 2026-08-29). Before this change `weights` was an untyped `dict[str, Any]`
all the way down, so `simulate_policy_weights` accepted `w_fairness`/`P_churn`/a typo and silently
dropped it -- an admin could believe they had simulated a fairness-aware policy and get a real
`flip_count` back that the field contributed nothing to. That is strictly worse than a refusal,
because the result *looks* authoritative. `_validate_weight_keys` now rejects anything the ranking
engine does not read, deriving the allowlist from `constraints.json`'s own `score_weights` so the
two can never drift apart. `publish_policy_version` validates too: writing an unread key into an
immutable `policy_versions` row is the same lie, made durable.
"""

from __future__ import annotations

import csv
import io
import json
from datetime import datetime, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.core.execution_context import ExecutionContext
from app.scheduling.constraints import load_scheduling_constraints
from app.scheduling.feasibility import (
    WEIGHT_FAIRNESS,
    active_facility_rules,
    check_facility_rules,
    parse_rule_boundary,
)
from app.services.idempotency import lookup_idempotency, payload_hash, store_idempotency
from app.services.ids import new_id

# Matches the live CHECK constraint added by this epic's migration -- the five real rule_type
# values seeded in facility_rules, not SS7.5.7's illustrative (and unmatched) example names.
RULE_TYPES = frozenset(
    {"HEAVY_DOCK_REQUIRED_KG", "LAST_NEW_START_TIME", "CHECKIN_EARLY_LIMIT_MIN", "NO_SHOW_GRACE_MIN", "REEFER_DOCK_REQUIRED"}
)

DEFAULT_PRIORITY_SCORES = {"CRITICAL": 4000, "HIGH": 3000, "NORMAL": 2000, "LOW": 1000, "UNKNOWN": 500}
ACTIVE_APPOINTMENT_STATUSES = ("PENDING_CONFIRMATION", "CONFIRMED", "IN_PROGRESS")

# The subset of RULE_TYPES `scheduling/feasibility.py::check_facility_rules` actually evaluates
# mechanically. Kept in sync with that function's own FACILITY_RULE_* constants -- it names the
# other two (CHECKIN_EARLY_LIMIT_MIN is a gate-arrival rule, NO_SHOW_GRACE_MIN needs an injected
# clock) as deliberately unenforced, so an impact preview for either has nothing to evaluate and
# must say so rather than returning a confident zero (A-G6, issue #74).
ENGINE_EVALUATED_RULE_TYPES = frozenset(
    {"LAST_NEW_START_TIME", "HEAVY_DOCK_REQUIRED_KG", "REEFER_DOCK_REQUIRED"}
)

# A rule-impact scan is a preview, not a report: bounded so a facility with a large forward book
# cannot turn a confirmation dialog into an unbounded read. Truncation is reported, never hidden.
RULE_IMPACT_SCAN_LIMIT = 500

# `weights` keys the ranking engine genuinely reads. `priority_scores` is not a score_weights
# entry but IS read by simulate_policy_weights, so it joins the allowlist explicitly.
NON_WEIGHT_POLICY_KEYS = frozenset({"priority_scores"})

# Named separately from the generic "unknown key" path because this one has a real, documented
# reason and a tracking issue: P_churn counts promises the SEQUENCER moved (SOLUTION_DESIGN.md
# section 5, "Pricing churn"), and the sequencer (section 7.5.3, issue #49) is entirely unbuilt.
# It is not a typo and telling the admin so is more useful than "unknown key".
BLOCKED_WEIGHT_KEYS = {
    "P_churn": (
        "P_churn counts promises the facility sequencer moved. The sequencer is not built "
        "(issue #49), so there is nothing to count and the term cannot affect a simulation. "
        "Rejected rather than accepted-and-ignored."
    ),
}


def allowed_weight_keys() -> set[str]:
    """The live engine's own key set, read from `constraints.json` rather than restated here.

    Deriving the allowlist from the file `feasibility.py::_rank_slot` actually reads is what makes
    this validation impossible to drift: adding a coefficient to the engine automatically makes it
    accepted here, and removing one automatically makes it refused.
    """
    return set(load_scheduling_constraints().ranking_policy.score_weights) | set(NON_WEIGHT_POLICY_KEYS)


def _validate_weight_keys(weights: dict[str, Any]) -> None:
    """Refuse any weight key the ranking engine does not read (A-G1, issue #69).

    Silent acceptance is the specific defect this closes: `SimulatePolicyBody.weights` is an
    untyped `dict[str, Any]`, so before this an admin could send `w_fairness` (or a typo, or
    `P_churn`) and receive a real-looking `flip_count` the field contributed nothing to.
    """
    unknown = sorted(set(weights) - allowed_weight_keys())
    if not unknown:
        return
    reasons = [BLOCKED_WEIGHT_KEYS[key] for key in unknown if key in BLOCKED_WEIGHT_KEYS]
    detail = " ".join(reasons) if reasons else ""
    supported = ", ".join(sorted(allowed_weight_keys()))
    raise AppError(
        f"Unsupported policy weight key(s): {', '.join(unknown)}.",
        code="UNKNOWN_WEIGHT_KEYS", status_code=422,
        detail=(f"{detail} " if detail else "") + f"Supported keys: {supported}.",
    )


def _as_of() -> str:
    return datetime.now(timezone.utc).isoformat()


def _to_dt(value: datetime | str) -> datetime:
    return value if isinstance(value, datetime) else datetime.fromisoformat(str(value))


# --------------------------------------------------------------------------------------
# Audit (FR-ADM-009 / M14, `06-admin-console/flows-and-states.md` Flow 9)
# --------------------------------------------------------------------------------------


async def _write_audit_entry(
    session: AsyncSession, *, actor_id: str, action_type: str, entity_name: str, entity_id: str,
    new_value: dict[str, Any], created_at: str, old_value: dict[str, Any] | None = None,
) -> None:
    """The one place this module writes `audit_logs` -- Flow 9's "every write on this console
    becomes its own audit entry", through M14's ordinary pipeline rather than a weaker admin path.

    **This module wrote none at all before issue #80.** It exposes the Audit tab
    (`get_audit_log`/`export_audit_log`) while three of its own writes -- a rule create, a rule
    edit, and a policy publish -- left no trace in the table that tab reads. The publish is the
    sharpest case: it changes the ranking formula every subsequent allocation is scored against
    (D7), which makes it arguably the highest-consequence write in the product, and it was
    invisible.

    **`action_type` stays the generic CRUD verb and the specific event lives in
    `new_value_json.event`** -- the convention `admin_user_service`'s four pre-existing entries
    already established, and the one `audit_logs_action_type_check` permits without a migration
    (`supabase/migrations/20260829134929_d2_held_state_dock_occupancy.sql:290-296`; its sixteen
    values are LOGIN/LOGOUT/VIEW/CRUD/appointment/hold verbs, none console-specific).

    **No commit here, deliberately.** Every caller issues its own single `session.commit()` after
    calling this, so the audit row and the write it records land in the same transaction and fail
    together -- FR-ADM-009 is worthless if a write can succeed with its audit entry rolled back.

    Deliberately a near-duplicate of `admin_user_service._write_audit_entry` rather than a shared
    import: the two admin modules are peers, neither imports the other today, and issue #80's scope
    is these two files. Folding both onto one `services/audit.py` is a worthwhile follow-up, not
    something to smuggle in here.
    """
    await session.execute(
        text(
            """
            INSERT INTO public.audit_logs (
              audit_id, user_id, action_type, entity_name, entity_id, old_value_json,
              new_value_json, ip_address, user_agent, created_at
            ) VALUES (
              :audit_id, :actor_id, :action_type, :entity_name, :entity_id, :old_value_json,
              :new_value_json, NULL, NULL, :created_at
            )
            """
        ),
        {
            "audit_id": new_id("AUD"), "actor_id": actor_id, "action_type": action_type,
            "entity_name": entity_name, "entity_id": entity_id,
            "old_value_json": None if old_value is None else json.dumps(old_value, default=str),
            "new_value_json": json.dumps(new_value, default=str),
            "created_at": created_at,
        },
    )


# --------------------------------------------------------------------------------------
# Facility rules
# --------------------------------------------------------------------------------------


async def list_facility_rules(session: AsyncSession, ctx: ExecutionContext, facility_id: str | None = None) -> dict[str, Any]:
    """SS7.5.7 `list_facility_rules` -- `facility_id?`."""
    if not ctx.is_admin:
        raise AppError("Admin console access required.", code="FORBIDDEN", status_code=403)
    facility_filter = ""
    params: dict[str, Any] = {}
    if facility_id:
        facility_filter = "AND facility_id = :facility_id"
        params["facility_id"] = facility_id
    rows = (
        await session.execute(
            text(
                f"""
                SELECT rule_id, facility_id, rule_type, rule_value, description,
                       effective_from, effective_to, active_flag
                FROM public.facility_rules
                WHERE 1=1 {facility_filter}
                ORDER BY facility_id, rule_type
                """
            ),
            params,
        )
    ).mappings().all()
    return {"as_of": _as_of(), "source": "postgresql", "items": [dict(r) for r in rows]}


def _validate_rule_type(rule_type: str) -> str:
    upper = rule_type.upper()
    if upper not in RULE_TYPES:
        raise AppError(
            f"Unsupported rule_type '{rule_type}'.", code="INVALID_RULE_TYPE", status_code=422,
            detail=f"Supported: {', '.join(sorted(RULE_TYPES))}.",
        )
    return upper


async def create_facility_rule(
    session: AsyncSession, ctx: ExecutionContext,
    *, facility_id: str, rule_type: str, rule_value: str, effective_from: str | None = None,
    effective_to: str | None = None, description: str = "",
) -> dict[str, Any]:
    """SS7.5.7 `create_facility_rule` -- `rule_type` drawn from the registry, never free text.

    Audited (FR-ADM-009 / Flow 9, issue #80): `old_value_json` is genuinely NULL here, matching
    `invite_user`'s entry -- a created row has no before -- while the new value carries the whole
    rule payload, so "who added the 21:00 cutoff at Jaipur, and with what window" is answerable
    from the Audit tab without joining back to `facility_rules` (which a later edit will have moved
    on anyway).
    """
    if not ctx.is_admin:
        raise AppError("Admin console access required.", code="FORBIDDEN", status_code=403)
    validated_type = _validate_rule_type(rule_type)
    rule_id = new_id("RULE")
    row = (
        await session.execute(
            text(
                """
                INSERT INTO public.facility_rules (
                  rule_id, facility_id, rule_type, rule_value, description,
                  effective_from, effective_to, active_flag
                ) VALUES (:rule_id, :facility_id, :rule_type, :rule_value, :description, :eff_from, :eff_to, 1)
                RETURNING rule_id, facility_id, rule_type, rule_value, effective_from, effective_to
                """
            ),
            {
                "rule_id": rule_id, "facility_id": facility_id, "rule_type": validated_type,
                "rule_value": rule_value, "description": description, "eff_from": effective_from,
                "eff_to": effective_to,
            },
        )
    ).mappings().one()
    await _write_audit_entry(
        session, actor_id=ctx.user_id, action_type="CREATE", entity_name="facility_rules",
        entity_id=rule_id, created_at=_as_of(),
        new_value={
            "event": "CREATE_FACILITY_RULE", "facility_id": facility_id,
            "rule_type": validated_type, "rule_value": rule_value,
            "effective_from": effective_from, "effective_to": effective_to,
            "description": description, "active_flag": 1,
        },
    )
    await session.commit()
    result = dict(row)
    result["code"] = "CREATED"
    return result


async def update_facility_rule(
    session: AsyncSession, ctx: ExecutionContext,
    *, rule_id: str, rule_value: str | None = None, effective_from: str | None = None,
    effective_to: str | None = None,
) -> dict[str, Any]:
    """SS7.5.7 `update_facility_rule`. `rule_type`/`facility_id` are not editable here -- changing
    which rule a row represents is a new rule, not an update to an existing one.

    **The pre-edit values come from an aliased self-join, not a second read** (FR-ADM-009, issue
    #80). Production Supabase is PostgreSQL 17.6 and `RETURNING OLD.*` is a PostgreSQL **18**
    feature, so the before-values need another source; the `UPDATE` docs' own sanctioned form is
    the aliased self-join ("do not repeat the target table as a from_item unless you intend a
    self-join (in which case it must appear with an alias)"), and joining on `facility_rules`'
    primary key satisfies the same docs' one-output-row-per-target-row requirement, so their
    indeterminacy warning does not apply.

    The before/after is the entire content of a rule-edit audit entry: every argument here is
    `COALESCE`d, so an entry recording only the new state cannot distinguish "the admin changed the
    cutoff from 21:00 to 20:00" from "the admin re-saved 20:00 unchanged". The three `previous_*`
    columns are popped off before the result is returned, so this tool's response shape is
    unchanged.
    """
    if not ctx.is_admin:
        raise AppError("Admin console access required.", code="FORBIDDEN", status_code=403)
    row = (
        await session.execute(
            text(
                """
                UPDATE public.facility_rules AS fr
                SET rule_value = COALESCE(:rule_value, fr.rule_value),
                    effective_from = COALESCE(:eff_from, fr.effective_from),
                    effective_to = COALESCE(:eff_to, fr.effective_to)
                FROM public.facility_rules AS prev
                WHERE fr.rule_id = :rule_id AND prev.rule_id = fr.rule_id
                RETURNING fr.rule_id, fr.facility_id, fr.rule_type, fr.rule_value,
                          fr.effective_from, fr.effective_to,
                          prev.rule_value AS previous_rule_value,
                          prev.effective_from AS previous_effective_from,
                          prev.effective_to AS previous_effective_to
                """
            ),
            {"rule_value": rule_value, "eff_from": effective_from, "eff_to": effective_to, "rule_id": rule_id},
        )
    ).mappings().first()
    if row is None:
        raise AppError(f"Rule '{rule_id}' not found.", code="NOT_FOUND", status_code=404)
    result = dict(row)
    previous = {
        "rule_value": result.pop("previous_rule_value", None),
        "effective_from": result.pop("previous_effective_from", None),
        "effective_to": result.pop("previous_effective_to", None),
    }
    await _write_audit_entry(
        session, actor_id=ctx.user_id, action_type="UPDATE", entity_name="facility_rules",
        entity_id=rule_id, created_at=_as_of(),
        old_value=previous,
        new_value={
            "event": "UPDATE_FACILITY_RULE",
            "facility_id": result.get("facility_id"), "rule_type": result.get("rule_type"),
            "rule_value": result.get("rule_value"),
            "effective_from": result.get("effective_from"),
            "effective_to": result.get("effective_to"),
        },
    )
    await session.commit()
    result["code"] = "UPDATED"
    return result


def _rule_shape(rule_value: Any, effective_from: Any, effective_to: Any) -> dict[str, Any]:
    return {
        "rule_value": None if rule_value is None else str(rule_value),
        "effective_from": effective_from,
        "effective_to": effective_to,
    }


async def get_facility_rule_impact(
    session: AsyncSession, ctx: ExecutionContext, *, rule_id: str,
    rule_value: str | None = None, effective_from: str | None = None, effective_to: str | None = None,
) -> dict[str, Any]:
    """The read behind `edge-cases.md` #4's High-tier confirmation (A-G6, issue #74).

    That edge case is explicit about the ordering: "`components.md` section 2's High-tier
    confirmation names the count of affected appointments **before** the edit commits, giving the
    admin the choice to proceed or not, but the edit itself does not reach into `appointments` and
    mutate or escalate them." So this is a **pure read** and `update_facility_rule` is unchanged --
    a rule edit still governs future feasibility checks only and never un-commits a promise.

    **Not in section 7.5.7's own catalog**: flagged as an addition rather than silently folded in,
    the same discipline `planner_service.get_dock_block_impact` and `get_user_removal_impact`
    already use. Shaped deliberately like `get_dock_block_impact` -- the identical "confirmation
    dialog needs a count before the write" problem, solved once in this codebase, so it is solved
    the same way here rather than a second way.

    **Why it evaluates through `feasibility.py` rather than re-implementing the rule semantics.**
    `active_facility_rules` decides *when* a rule is in force and `check_facility_rules` decides
    *what* it forbids. Calling both is what guarantees the preview and the enforcing engine
    disagree about nothing: a locally-rewritten "is 20:30 after 20:00" check would be right until
    the day someone changed the engine's strict-vs-inclusive boundary and not this copy. It also
    inherits the engine's own honest limits for free -- see `ENGINE_EVALUATED_RULE_TYPES`.

    **Arguments mirror `update_facility_rule`'s exactly, `None` meaning unchanged**, so the
    preview is computed against precisely what the update's `COALESCE` would apply. Passing no
    proposal at all is legal and answers "who does this rule already exclude today", which is
    `affected_count = 0` plus a non-zero `already_non_compliant_count`.

    **No wall-clock "future only" filter, deliberately.** The scan is bounded by the *proposed
    rule's own effectivity window*, not by `now()`. `check_facility_rules`' own docstring already
    records that this engine has no injected clock (section 9.1's "Deterministic clock" is not
    built), and a `now()` filter would silently return zero against any dataset whose snapshot
    clock differs from the wall clock -- a confirmation dialog that always says "0 affected" is
    worse than one that says nothing. Terminal appointments are excluded by status instead, which
    is a fact about the data rather than about the clock.
    """
    if not ctx.is_admin:
        raise AppError("Admin console access required.", code="FORBIDDEN", status_code=403)

    rule = (
        await session.execute(
            text(
                """
                SELECT fr.rule_id, fr.facility_id, fr.rule_type, fr.rule_value, fr.description,
                       fr.effective_from, fr.effective_to, fr.active_flag, f.timezone
                FROM public.facility_rules fr
                JOIN public.facilities f ON f.facility_id = fr.facility_id
                WHERE fr.rule_id = :rule_id
                """
            ),
            {"rule_id": rule_id},
        )
    ).mappings().first()
    if rule is None:
        raise AppError(f"Rule '{rule_id}' not found.", code="NOT_FOUND", status_code=404)

    rule_type = str(rule["rule_type"])
    tz_name = str(rule["timezone"])
    current = _rule_shape(rule["rule_value"], rule["effective_from"], rule["effective_to"])
    proposed = _rule_shape(
        rule_value if rule_value is not None else rule["rule_value"],
        effective_from if effective_from is not None else rule["effective_from"],
        effective_to if effective_to is not None else rule["effective_to"],
    )
    current_rule = {"rule_id": rule_id, "rule_type": rule_type, **current}
    proposed_rule = {"rule_id": rule_id, "rule_type": rule_type, **proposed}

    envelope: dict[str, Any] = {
        "as_of": _as_of(), "source": "postgresql", "rule_id": rule_id,
        "facility_id": str(rule["facility_id"]), "rule_type": rule_type,
        "active_flag": int(rule["active_flag"] or 0),
        "current": current, "proposed": proposed,
        "evaluable": rule_type in ENGINE_EVALUATED_RULE_TYPES,
        "affected_count": 0, "affected_appointments": [],
        "already_non_compliant_count": 0, "scanned_count": 0, "truncated": False,
    }

    if not envelope["evaluable"]:
        # A confident "0 affected" for a rule type the engine never evaluates would be a lie of
        # omission -- the honest answer is that this edit cannot make any appointment
        # retroactively non-compliant because nothing checks it at offer time in the first place.
        envelope["note"] = (
            f"'{rule_type}' is not evaluated by the feasibility engine "
            f"(only {', '.join(sorted(ENGINE_EVALUATED_RULE_TYPES))} are), so no appointment can "
            "be made retroactively non-compliant by editing it. This is a real answer, not a "
            "count of zero."
        )
        return envelope
    if not envelope["active_flag"]:
        envelope["note"] = (
            "This rule is inactive (active_flag = 0). The feasibility engine only loads active "
            "rules, so editing it affects nothing until it is reactivated."
        )
        return envelope

    scan_from = parse_rule_boundary(proposed["effective_from"], tz_name)
    scan_to = parse_rule_boundary(proposed["effective_to"], tz_name)
    # Built conditionally rather than with `:param IS NULL` guards: an untyped NULL bind against a
    # timestamptz comparison is what asyncpg cannot infer a type for.
    window_clauses, params = "", {
        "facility_id": str(rule["facility_id"]),
        "active_statuses": list(ACTIVE_APPOINTMENT_STATUSES),
        "scan_limit": RULE_IMPACT_SCAN_LIMIT,
    }
    if scan_from is not None:
        window_clauses += " AND sl.slot_start_ts >= :scan_from"
        params["scan_from"] = scan_from
    if scan_to is not None:
        window_clauses += " AND sl.slot_start_ts < :scan_to"
        params["scan_to"] = scan_to

    rows = (
        await session.execute(
            text(
                f"""
                SELECT a.appointment_id, a.shipment_id, a.appointment_status,
                       sl.slot_id, sl.slot_start_ts, sl.slot_end_ts,
                       d.dock_id, d.dock_code, d.dock_type, d.supports_refrigerated,
                       s.load_weight_kg, s.temperature_control_required, s.carrier_id
                FROM public.appointments a
                JOIN public.appointment_slots sl ON sl.slot_id = a.slot_id
                JOIN public.docks d ON d.dock_id = sl.dock_id
                JOIN public.shipments s ON s.shipment_id = a.shipment_id
                WHERE a.is_current = 1
                  AND a.appointment_status = ANY(:active_statuses)
                  AND sl.facility_id = :facility_id
                  {window_clauses}
                ORDER BY sl.slot_start_ts, a.appointment_id
                LIMIT :scan_limit
                """
            ),
            params,
        )
    ).mappings().all()

    affected: list[dict[str, Any]] = []
    already = 0
    for row in rows:
        start = _to_dt(row["slot_start_ts"])
        shipment = {
            "load_weight_kg": int(row["load_weight_kg"] or 0),
            "temperature_control_required": int(row["temperature_control_required"] or 0),
        }
        candidate = {
            "dock_type": str(row["dock_type"]),
            "supports_refrigerated": int(row["supports_refrigerated"] or 0),
        }
        # A promised appointment's real unload start is its slot start -- there is no live ETA to
        # take a max() against once the interval is committed.
        proposed_hit = _rule_violation(proposed_rule, shipment, candidate, start, tz_name)
        current_hit = _rule_violation(current_rule, shipment, candidate, start, tz_name)
        if current_hit is not None:
            already += 1
            continue
        if proposed_hit is not None:
            affected.append(
                {
                    "appointment_id": row["appointment_id"], "shipment_id": row["shipment_id"],
                    "appointment_status": row["appointment_status"], "slot_id": row["slot_id"],
                    "dock_code": row["dock_code"], "carrier_id": row["carrier_id"],
                    "slot_start_ts": row["slot_start_ts"], "slot_end_ts": row["slot_end_ts"],
                    "reason": proposed_hit,
                }
            )

    envelope.update(
        {
            "affected_count": len(affected), "affected_appointments": affected,
            "already_non_compliant_count": already, "scanned_count": len(rows),
            "truncated": len(rows) >= RULE_IMPACT_SCAN_LIMIT,
            "note": (
                "affected_count counts appointments this edit would newly make non-compliant: "
                "they satisfy the rule as stored and violate it as proposed. Appointments the "
                "current rule already forbids are reported separately as "
                "already_non_compliant_count, because this edit did not cause those. Nothing is "
                "cancelled or escalated by reading this -- facility rules govern future "
                "feasibility checks only (edge-cases.md #4)."
            ),
        }
    )
    return envelope


def _rule_violation(
    rule: dict[str, Any], shipment: dict[str, Any], candidate: dict[str, Any],
    start: datetime, tz_name: str,
) -> str | None:
    """The engine's own verdict for one rule against one committed interval, or None.

    Two calls, in the engine's own order: `active_facility_rules` first (is the rule even in force
    at this instant), then `check_facility_rules` (does it forbid this interval). Skipping the
    first would count appointments outside the rule's effective window, which is exactly the
    mistake a hand-rolled preview makes.
    """
    in_force = active_facility_rules([rule], at=start, tz_name=tz_name)
    if not in_force:
        return None
    hit = check_facility_rules(
        shipment=shipment, candidate=candidate, rules=in_force, feasible_start=start, tz_name=tz_name
    )
    return None if hit is None else hit[1]


# --------------------------------------------------------------------------------------
# Policy simulate/publish
# --------------------------------------------------------------------------------------


def _score(
    *, priority_code: str, lateness_minutes: int, wait_after_eta_minutes: int, fit_slack_minutes: int,
    exact_dock_type_match: bool, weights: dict[str, Any], priority_scores: dict[str, int],
    carrier_concentration: int = 0,
) -> int:
    """A direct copy of `feasibility.py::_rank_slot`'s formula -- see module docstring for why
    this is duplicated rather than imported.

    `carrier_concentration` mirrors `_rank_slot`'s own parameter of the same name (issue #69) and
    defaults to 0 for the same reason: the formula-parity test calls both with the default, and at
    the shipped `w_fairness = 0` the term is arithmetically absent either way.
    """
    lateness_cap = weights.get("lateness_cap_minutes", 720)
    fit_slack_cap = weights.get("fit_slack_cap_minutes", 120)
    return int(
        priority_scores.get(priority_code, priority_scores.get("UNKNOWN", 500))
        + min(lateness_minutes, lateness_cap) * weights.get("lateness_per_minute", 4)
        + wait_after_eta_minutes * weights.get("wait_after_eta_per_minute", -6)
        + min(fit_slack_minutes, fit_slack_cap) * weights.get("fit_slack_per_minute", 1)
        + (0 if exact_dock_type_match else weights.get("compatible_but_not_exact_dock_penalty", -25))
        + weights.get(WEIGHT_FAIRNESS, 0) * carrier_concentration
    )


async def _replayable_candidates(
    session: AsyncSession, *, window_start: datetime, window_end: datetime,
) -> list[dict[str, Any]]:
    rows = (
        await session.execute(
            text(
                """
                SELECT s.shipment_id, s.priority_code, s.original_eta_ts, s.latest_eta_ts,
                       s.required_dock_type, s.expected_unload_min, s.carrier_id,
                       sl.slot_id, sl.dock_id,
                       sl.slot_start_ts, sl.slot_end_ts, sl.facility_id, d.dock_type,
                       f.timezone
                FROM public.appointments a
                JOIN public.shipments s ON s.shipment_id = a.shipment_id
                JOIN public.appointment_slots sl ON sl.slot_id = a.slot_id
                JOIN public.docks d ON d.dock_id = sl.dock_id
                JOIN public.facilities f ON f.facility_id = sl.facility_id
                WHERE a.is_current = 1
                  AND a.appointment_status = ANY(:active_statuses)
                  AND sl.slot_start_ts >= :window_start AND sl.slot_start_ts < :window_end
                ORDER BY sl.slot_start_ts
                LIMIT 100
                """
            ),
            {"active_statuses": list(ACTIVE_APPOINTMENT_STATUSES), "window_start": window_start, "window_end": window_end},
        )
    ).mappings().all()
    return [dict(r) for r in rows]


async def _alternative_slots(session: AsyncSession, *, facility_id: str, near: datetime, exclude_slot_id: str) -> list[dict[str, Any]]:
    rows = (
        await session.execute(
            text(
                """
                SELECT sl.slot_id, sl.dock_id, sl.slot_start_ts, sl.slot_end_ts, d.dock_type
                FROM public.appointment_slots sl
                JOIN public.docks d ON d.dock_id = sl.dock_id
                WHERE sl.facility_id = :facility_id
                  AND sl.slot_id <> :exclude_slot_id
                  AND sl.slot_start_ts >= :start AND sl.slot_start_ts < :end
                LIMIT 5
                """
            ),
            {
                "facility_id": facility_id, "exclude_slot_id": exclude_slot_id,
                "start": near - timedelta(hours=12), "end": near + timedelta(hours=12),
            },
        )
    ).mappings().all()
    return [dict(r) for r in rows]


async def _carrier_concentration_map(
    session: AsyncSession, *, window_start: datetime, window_end: datetime,
) -> dict[tuple[str, str, str], int]:
    """D7's fairness input for the simulator, keyed `(carrier_id, facility_id, local_date)`.

    Deliberately ONE grouped read for the whole window rather than a per-candidate query: the
    simulator already loops up to 100 candidates x 6 pool slots, and a per-slot round trip would
    turn a preview into a scan. Only called when `w_fairness` is actually non-zero on one side of
    the comparison (issue #69).

    `AT TIME ZONE <name>` on a timestamptz gives the facility-local wall clock, so this counts a
    local calendar day -- the same definition `feasibility.py` uses, so the simulator and the live
    engine measure the same quantity rather than two similar-sounding ones.
    """
    rows = (
        await session.execute(
            text(
                """
                SELECT other.carrier_id AS carrier_id, sl.facility_id AS facility_id,
                       to_char(sl.slot_start_ts AT TIME ZONE f.timezone, 'YYYY-MM-DD') AS local_date,
                       CAST(count(*) AS integer) AS held_count
                FROM public.appointments a
                JOIN public.appointment_slots sl ON sl.slot_id = a.slot_id
                JOIN public.shipments other ON other.shipment_id = a.shipment_id
                JOIN public.facilities f ON f.facility_id = sl.facility_id
                WHERE a.is_current = 1
                  AND a.appointment_status = ANY(:active_statuses)
                  AND sl.slot_start_ts >= :window_start AND sl.slot_start_ts < :window_end
                GROUP BY 1, 2, 3
                """
            ),
            {
                "active_statuses": list(ACTIVE_APPOINTMENT_STATUSES),
                "window_start": window_start, "window_end": window_end,
            },
        )
    ).mappings().all()
    return {
        (str(r["carrier_id"]), str(r["facility_id"]), str(r["local_date"])): int(r["held_count"])
        for r in rows
    }


def _local_date(moment: datetime, tz_name: str) -> str:
    return moment.astimezone(ZoneInfo(tz_name)).date().isoformat()


async def simulate_policy_weights(
    session: AsyncSession, ctx: ExecutionContext,
    *, weights: dict[str, Any], window_start: datetime, window_end: datetime,
) -> dict[str, Any]:
    """SS7.5.7 `simulate_policy_weights` -- `weights`, `window`. **Read-only**: never writes a
    `policy_versions` row. See module docstring for the approximation this makes.

    Unknown keys are refused up front (issue #69). A simulation whose headline number was produced
    by quietly discarding half the admin's input is worse than no simulation at all, because it
    reads as evidence.
    """
    if not ctx.is_admin:
        raise AppError("Admin console access required.", code="FORBIDDEN", status_code=403)
    _validate_weight_keys(weights)

    live = load_scheduling_constraints().ranking_policy
    live_weights = live.score_weights
    live_priority = live.priority_scores or DEFAULT_PRIORITY_SCORES
    proposed_priority = weights.get("priority_scores") or live_priority

    candidates = await _replayable_candidates(session, window_start=window_start, window_end=window_end)
    # Fetched only when one side of the comparison actually enables the term -- a simulation of
    # four routine coefficients must not pay for a fairness read it will multiply by zero.
    fairness_active = bool(live_weights.get(WEIGHT_FAIRNESS, 0)) or bool(weights.get(WEIGHT_FAIRNESS, 0))
    concentration = (
        await _carrier_concentration_map(session, window_start=window_start, window_end=window_end)
        if fairness_active
        else {}
    )
    flips: list[dict[str, Any]] = []
    for row in candidates:
        if not row.get("latest_eta_ts"):
            continue
        latest_eta_dt = _to_dt(row["latest_eta_ts"])
        original_eta_dt = _to_dt(row["original_eta_ts"]) if row.get("original_eta_ts") else latest_eta_dt
        unload_min = int(row["expected_unload_min"] or 0)
        lateness_minutes = max(0, int((latest_eta_dt - original_eta_dt).total_seconds() // 60))

        alternatives = await _alternative_slots(
            session, facility_id=str(row["facility_id"]), near=row["slot_start_ts"], exclude_slot_id=str(row["slot_id"])
        )
        pool = [row] + [
            {**alt, "required_dock_type": row["required_dock_type"]} for alt in alternatives
        ]

        facility_id = str(row["facility_id"])
        carrier_id = str(row["carrier_id"])
        tz_name = str(row["timezone"])
        # This shipment's own appointment is inside the grouped count, so it is subtracted back
        # out on its own local date -- the live engine excludes the shipment being ranked
        # (`other.shipment_id <> :shipment_id`), and a simulator that did not would report a
        # concentration one higher on exactly the date that matters most.
        own_local_date = _local_date(row["slot_start_ts"], tz_name) if fairness_active else ""

        def _concentration(cand: dict[str, Any]) -> int:
            if not fairness_active:
                return 0
            cand_local_date = _local_date(cand["slot_start_ts"], tz_name)
            held = concentration.get((carrier_id, facility_id, cand_local_date), 0)
            return max(0, held - (1 if cand_local_date == own_local_date else 0))

        def _rank(pool: list[dict[str, Any]], w: dict[str, Any], pri: dict[str, int]) -> str:
            best_slot, best_score = None, None
            for cand in pool:
                wait_after_eta = max(0, int((cand["slot_start_ts"] - latest_eta_dt).total_seconds() // 60))
                feasible_end = cand["slot_start_ts"] + timedelta(minutes=unload_min)
                fit_slack = max(0, int((cand["slot_end_ts"] - feasible_end).total_seconds() // 60))
                exact = str(cand["dock_type"]) == str(cand["required_dock_type"])
                score = _score(
                    priority_code=str(row["priority_code"]), lateness_minutes=lateness_minutes,
                    wait_after_eta_minutes=wait_after_eta, fit_slack_minutes=fit_slack,
                    exact_dock_type_match=exact, weights=w, priority_scores=pri,
                    carrier_concentration=_concentration(cand),
                )
                if best_score is None or score > best_score:
                    best_score, best_slot = score, str(cand["slot_id"])
            return best_slot or ""

        live_top = _rank(pool, live_weights, live_priority)
        proposed_top = _rank(pool, weights, proposed_priority)
        if live_top != proposed_top:
            flips.append({"shipment_id": row["shipment_id"], "live_top_slot": live_top, "proposed_top_slot": proposed_top})

    return {
        "as_of": _as_of(), "code": "SIMULATED", "candidates_evaluated": len(candidates),
        "flip_count": len(flips), "example_flips": flips[:10],
        # States outright whether D7's fairness term participated in this run, so the Danger Zone
        # never has to infer it from a flip count (issue #69). False here is a real answer: both
        # sides ran at w_fairness = 0, so the term was arithmetically absent, not skipped.
        "fairness_term_evaluated": fairness_active,
        "live_w_fairness": live_weights.get(WEIGHT_FAIRNESS, 0),
        "proposed_w_fairness": weights.get(WEIGHT_FAIRNESS, live_weights.get(WEIGHT_FAIRNESS, 0)),
        "note": (
            "Approximation, not a literal replay: no historical decision log exists, so this "
            "re-scores each shipment's current appointment against other slots open today at the "
            "same facility, not the exact candidate set available at the real booking moment."
        ),
    }


async def get_active_policy_version(session: AsyncSession, ctx: ExecutionContext) -> dict[str, Any]:
    """The currently-active `policy_versions` row, plus the weights the live engine is actually
    running (A-G7, issue #75).

    Two things need this and neither had a read before: `screens.md` section 4's Policy tab renders
    "read-only current version" as the baseline an admin edits away from, and
    `publish_policy_version`'s new `based_on_version_id` guard is unusable if there is no way to
    learn what the current version id *is*. **Not in section 7.5.7's own catalog** -- flagged as an
    addition rather than silently folded in, the same discipline
    `planner_service.get_dock_block_impact` uses.

    `live_weights` comes from `constraints.json`, not from the active row, and the two can honestly
    disagree: `publish_policy_version`'s own docstring records that publishing writes a durable
    decision but does **not** rewrite the file the ranking engine reads. Returning both, plus
    `engine_matches_active_version`, states that divergence rather than letting the UI imply the
    published version is live.
    """
    if not ctx.is_admin:
        raise AppError("Admin console access required.", code="FORBIDDEN", status_code=403)
    row = (
        await session.execute(
            text(
                """
                SELECT policy_version_id, weights_json, published_at, published_by_user_id
                FROM public.policy_versions
                WHERE is_active = 1
                """
            )
        )
    ).mappings().first()

    live = load_scheduling_constraints().ranking_policy
    live_weights = dict(live.score_weights)
    active: dict[str, Any] | None = None
    if row is not None:
        active = {
            "policy_version_id": str(row["policy_version_id"]),
            "published_at": row["published_at"],
            "published_by_user_id": row["published_by_user_id"],
            "weights": json.loads(row["weights_json"]),
        }
    return {
        "as_of": _as_of(), "source": "postgresql", "active_version": active,
        "live_weights": live_weights,
        "live_priority_scores": dict(live.priority_scores or DEFAULT_PRIORITY_SCORES),
        "engine_matches_active_version": (
            active is not None and active["weights"] == live_weights
        ),
        "note": (
            "live_weights is scheduling/constraints.json -- the file the ranking engine actually "
            "reads. publish_policy_version records a decision durably; it does not rewrite that "
            "file, so a just-published version can legitimately differ from what is running."
        ),
    }


def _weights_of(row: Any) -> dict[str, Any] | None:
    """The stored coefficients of a `policy_versions` row, or None if they cannot be read.

    `weights_json` is `text NOT NULL` in the live schema, so the None branches are defensive rather
    than expected -- but this runs inside the publish transaction, and an audit entry is not worth
    turning a successful publish into a 500 over a row whose JSON somebody hand-edited. A missing
    "before" degrades the entry; a raised exception loses both the entry and the publish.
    """
    if row is None:
        return None
    raw = dict(row).get("weights_json")
    if not raw:
        return None
    try:
        return json.loads(str(raw))
    except (TypeError, ValueError):
        return None


async def publish_policy_version(
    session: AsyncSession, ctx: ExecutionContext, *, weights: dict[str, Any], idempotency_key: str,
    based_on_version_id: str | None = None,
) -> dict[str, Any]:
    """SS7.5.7 `publish_policy_version` -- creates a new, immutable `policy_versions` row (D7);
    never mutates a prior version. Does **not** write `scheduling/constraints.json`: that file is
    the live ranking engine's actual input and changing it is a deploy-time decision, not a runtime
    admin write -- this tool records the decision durably and auditably; wiring the live engine to
    read the active `policy_versions` row instead of the static file is separate, larger scope.

    **`based_on_version_id` is the optimistic-concurrency guard `edge-cases.md` #3 requires**
    (A-G7, issue #75): "if another admin publishes a version between this admin's simulation and
    their own Publish attempt, the tool refuses with a named conflict -- same shape as
    `confirm_request`'s `ALREADY_ACTIONED`." It is an argument section 7.5.7's table does not list,
    so it is a deliberate extension of that catalog, not an implementation of it -- but without it
    the refusal that edge case documents is not expressible at all: the pre-#75 tool cleared
    whatever row happened to be active and inserted its own, so Admin A publishing on top of Admin
    B's just-published version succeeded silently.

    **It is required whenever an active version exists**, rather than optional-and-honoured. An
    optional guard is not a guard: any caller that forgets the argument gets exactly the old
    silent-overwrite behaviour back, which is the defect. The first-ever publish (no active row)
    correctly takes no baseline.

    **Why `FOR UPDATE`, and why the "no active row" branch is a conflict too.** Two genuinely
    simultaneous publishes serialise on that row lock. Under READ COMMITTED the loser then
    re-evaluates its `WHERE is_active = 1` against the winner's committed version of the row
    (PostgreSQL "Transaction Isolation" 13.2.1 -- SELECT FOR UPDATE re-checks the updated row), and
    the winner has set `is_active = 0`, so the loser sees **no** active row while holding a
    `based_on_version_id` -- which is why "baseline supplied but nothing is active" is treated as
    a conflict rather than a first publish. Before this change that same race did not silently
    succeed either: it died on `idx_policy_versions_one_active` with a raw IntegrityError, i.e. a
    500 rather than a named refusal.
    """
    if not ctx.is_admin:
        raise AppError("Admin console access required.", code="FORBIDDEN", status_code=403)
    # Before the idempotency lookup: a request that can never be honoured should not be able to
    # occupy a key, and a rejected publish must not be replayable as a success (issue #69).
    _validate_weight_keys(weights)
    key = (idempotency_key or "").strip()
    if not key:
        raise AppError("Idempotency-Key header is required.", code="IDEMPOTENCY_KEY_REQUIRED", status_code=400)

    route = "POST /api/v1/admin/policy/publish"
    req_hash = payload_hash({"weights": weights, "based_on_version_id": based_on_version_id})
    replay = await lookup_idempotency(session, key=key, user_id=ctx.user_id, route=route, request_hash=req_hash)
    if replay is not None:
        return {**replay["response"], "idempotent_replay": True}

    baseline = (based_on_version_id or "").strip() or None
    active = (
        await session.execute(
            text(
                """
                SELECT policy_version_id, published_by_user_id, published_at, weights_json
                FROM public.policy_versions
                WHERE is_active = 1
                FOR UPDATE
                """
            )
        )
    ).mappings().first()
    current_id = str(active["policy_version_id"]) if active is not None else None

    if current_id is not None and baseline is None:
        raise AppError(
            "Publishing over an existing active policy version requires based_on_version_id.",
            code="BASE_VERSION_REQUIRED", status_code=422,
            detail=f"The current active version is {current_id}.",
        )
    if baseline is not None and baseline != current_id:
        raise await _policy_version_conflict(session, attempted_baseline=baseline, active=active)

    version_id = new_id("POLV")
    now_dt = datetime.now(timezone.utc)
    await session.execute(
        text("UPDATE public.policy_versions SET is_active = 0 WHERE is_active = 1"),
    )
    await session.execute(
        text(
            """
            INSERT INTO public.policy_versions (policy_version_id, weights_json, published_at, published_by_user_id, is_active)
            VALUES (:id, :weights_json, :published_at, :published_by, 1)
            """
        ),
        {
            "id": version_id, "weights_json": json.dumps(weights, default=str),
            "published_at": now_dt, "published_by": ctx.user_id,
        },
    )
    # FR-ADM-009 / Flow 9 (issue #80), and the one M14 field this table can carry directly: the
    # design's audit row is "who, what, when, **which policy version**, which tool call", and both
    # version ids go into this entry. `weights_json` came out of the FOR UPDATE read above, so the
    # superseded coefficients cost no extra round trip -- which matters because the diff *is* the
    # decision here: "w_fairness went from 0 to 0.4 on Tuesday" is the fact an auditor needs, and
    # it is not recoverable from the new row alone.
    await _write_audit_entry(
        session, actor_id=ctx.user_id, action_type="CREATE", entity_name="policy_versions",
        entity_id=version_id, created_at=now_dt.isoformat(),
        old_value=(
            None if current_id is None
            else {"policy_version_id": current_id, "weights": _weights_of(active)}
        ),
        new_value={
            "event": "PUBLISH_POLICY_VERSION", "policy_version_id": version_id,
            "weights": weights, "superseded_version_id": current_id,
        },
    )
    result = {
        "as_of": _as_of(), "code": "PUBLISHED", "policy_version_id": version_id,
        "superseded_version_id": current_id,
    }
    await store_idempotency(session, key=key, user_id=ctx.user_id, route=route, request_hash=req_hash, response=result)
    await session.commit()
    return result


async def _policy_version_conflict(
    session: AsyncSession, *, attempted_baseline: str, active: Any
) -> AppError:
    """The loser-facing refusal for A-G7, shaped exactly like `allocation._already_actioned_error`.

    Same code (`ALREADY_ACTIONED`), same 409, same "name the winning transition rather than a
    generic failure" rule -- section 7.5.1's reason for that shape applies unchanged here: the
    difference between "your click failed" and "someone else published first" is the difference
    between retrying blind and re-simulating against what is actually current.

    Costs one extra query **only on the error path**, and only in the branch where the active row
    is already gone (the true simultaneous race) -- the common sequential case names the winner
    from the row `publish_policy_version` already locked.
    """
    winner = active
    if winner is None:
        winner = (
            await session.execute(
                text(
                    """
                    SELECT policy_version_id, published_by_user_id, published_at
                    FROM public.policy_versions
                    ORDER BY published_at DESC
                    LIMIT 1
                    """
                )
            )
        ).mappings().first()
    if winner is None:
        return AppError(
            "Cannot publish against a baseline version that no longer exists: no policy version "
            "has ever been published.",
            code="ALREADY_ACTIONED", status_code=409,
            detail=f"based_on_version_id={attempted_baseline}",
        )
    winner_id = str(winner["policy_version_id"])
    return AppError(
        f"Cannot publish this policy version: {winner_id} was published first. "
        "Re-read the current version and re-run the simulation against it before publishing.",
        code="ALREADY_ACTIONED", status_code=409,
        detail=(
            f"based_on_version_id={attempted_baseline}, current_version_id={winner_id}, "
            f"published_by={winner['published_by_user_id']}"
        ),
    )


# --------------------------------------------------------------------------------------
# Audit log
# --------------------------------------------------------------------------------------


def _audit_filters(actor: str | None, event_type: str | None, date_from: str | None, date_to: str | None, resource: str | None) -> tuple[str, dict[str, Any]]:
    clauses, params = [], {}
    if actor:
        clauses.append("user_id = :actor")
        params["actor"] = actor
    if event_type:
        clauses.append("action_type = :event_type")
        params["event_type"] = event_type.upper()
    if resource:
        clauses.append("entity_name = :resource")
        params["resource"] = resource
    if date_from:
        clauses.append("created_at >= :date_from")
        params["date_from"] = date_from
    if date_to:
        clauses.append("created_at < :date_to")
        params["date_to"] = date_to
    return (" AND " + " AND ".join(clauses)) if clauses else "", params


async def get_audit_log(
    session: AsyncSession, ctx: ExecutionContext,
    *, actor: str | None = None, event_type: str | None = None, date_from: str | None = None,
    date_to: str | None = None, resource: str | None = None,
) -> dict[str, Any]:
    """SS7.5.7 `get_audit_log` -- `actor?`, `event_type?`, `date_range?`, `resource?`."""
    if not ctx.is_admin:
        raise AppError("Admin console access required.", code="FORBIDDEN", status_code=403)
    filters, params = _audit_filters(actor, event_type, date_from, date_to, resource)
    rows = (
        await session.execute(
            text(
                f"""
                SELECT audit_id, user_id, action_type, entity_name, entity_id,
                       old_value_json, new_value_json, created_at
                FROM public.audit_logs
                WHERE 1=1 {filters}
                ORDER BY created_at DESC
                LIMIT 200
                """
            ),
            params,
        )
    ).mappings().all()
    return {"as_of": _as_of(), "source": "postgresql", "items": [dict(r) for r in rows]}


async def export_audit_log(
    session: AsyncSession, ctx: ExecutionContext,
    *, actor: str | None = None, event_type: str | None = None, date_from: str | None = None,
    date_to: str | None = None,
) -> str:
    """SS7.5.7 `export_audit_log` -- CSV, same filters as the current view. Never a silent
    full-table export ignoring whatever the admin was actually looking at."""
    if not ctx.is_admin:
        raise AppError("Admin console access required.", code="FORBIDDEN", status_code=403)
    filters, params = _audit_filters(actor, event_type, date_from, date_to, None)
    rows = (
        await session.execute(
            text(
                f"""
                SELECT audit_id, user_id, action_type, entity_name, entity_id, created_at
                FROM public.audit_logs
                WHERE 1=1 {filters}
                ORDER BY created_at DESC
                LIMIT 5000
                """
            ),
            params,
        )
    ).mappings().all()

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["audit_id", "user_id", "action_type", "entity_name", "entity_id", "created_at"])
    for row in rows:
        writer.writerow([row["audit_id"], row["user_id"], row["action_type"], row["entity_name"], row["entity_id"], row["created_at"]])
    return buf.getvalue()
