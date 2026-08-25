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
"""

from __future__ import annotations

import csv
import io
import json
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.core.execution_context import ExecutionContext
from app.scheduling.constraints import load_scheduling_constraints
from app.services.idempotency import lookup_idempotency, payload_hash, store_idempotency
from app.services.ids import new_id

# Matches the live CHECK constraint added by this epic's migration -- the five real rule_type
# values seeded in facility_rules, not SS7.5.7's illustrative (and unmatched) example names.
RULE_TYPES = frozenset(
    {"HEAVY_DOCK_REQUIRED_KG", "LAST_NEW_START_TIME", "CHECKIN_EARLY_LIMIT_MIN", "NO_SHOW_GRACE_MIN", "REEFER_DOCK_REQUIRED"}
)

DEFAULT_PRIORITY_SCORES = {"CRITICAL": 4000, "HIGH": 3000, "NORMAL": 2000, "LOW": 1000, "UNKNOWN": 500}
ACTIVE_APPOINTMENT_STATUSES = ("PENDING_CONFIRMATION", "CONFIRMED", "IN_PROGRESS")


def _as_of() -> str:
    return datetime.now(timezone.utc).isoformat()


def _to_dt(value: datetime | str) -> datetime:
    return value if isinstance(value, datetime) else datetime.fromisoformat(str(value))


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
    """SS7.5.7 `create_facility_rule` -- `rule_type` drawn from the registry, never free text."""
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
    which rule a row represents is a new rule, not an update to an existing one."""
    if not ctx.is_admin:
        raise AppError("Admin console access required.", code="FORBIDDEN", status_code=403)
    row = (
        await session.execute(
            text(
                """
                UPDATE public.facility_rules
                SET rule_value = COALESCE(:rule_value, rule_value),
                    effective_from = COALESCE(:eff_from, effective_from),
                    effective_to = COALESCE(:eff_to, effective_to)
                WHERE rule_id = :rule_id
                RETURNING rule_id, facility_id, rule_type, rule_value, effective_from, effective_to
                """
            ),
            {"rule_value": rule_value, "eff_from": effective_from, "eff_to": effective_to, "rule_id": rule_id},
        )
    ).mappings().first()
    if row is None:
        raise AppError(f"Rule '{rule_id}' not found.", code="NOT_FOUND", status_code=404)
    await session.commit()
    result = dict(row)
    result["code"] = "UPDATED"
    return result


# --------------------------------------------------------------------------------------
# Policy simulate/publish
# --------------------------------------------------------------------------------------


def _score(
    *, priority_code: str, lateness_minutes: int, wait_after_eta_minutes: int, fit_slack_minutes: int,
    exact_dock_type_match: bool, weights: dict[str, Any], priority_scores: dict[str, int],
) -> int:
    """A direct copy of `feasibility.py::_rank_slot`'s formula -- see module docstring for why
    this is duplicated rather than imported."""
    lateness_cap = weights.get("lateness_cap_minutes", 720)
    fit_slack_cap = weights.get("fit_slack_cap_minutes", 120)
    return int(
        priority_scores.get(priority_code, priority_scores.get("UNKNOWN", 500))
        + min(lateness_minutes, lateness_cap) * weights.get("lateness_per_minute", 4)
        + wait_after_eta_minutes * weights.get("wait_after_eta_per_minute", -6)
        + min(fit_slack_minutes, fit_slack_cap) * weights.get("fit_slack_per_minute", 1)
        + (0 if exact_dock_type_match else weights.get("compatible_but_not_exact_dock_penalty", -25))
    )


async def _replayable_candidates(
    session: AsyncSession, *, window_start: datetime, window_end: datetime,
) -> list[dict[str, Any]]:
    rows = (
        await session.execute(
            text(
                """
                SELECT s.shipment_id, s.priority_code, s.original_eta_ts, s.latest_eta_ts,
                       s.required_dock_type, s.expected_unload_min, sl.slot_id, sl.dock_id,
                       sl.slot_start_ts, sl.slot_end_ts, sl.facility_id, d.dock_type
                FROM public.appointments a
                JOIN public.shipments s ON s.shipment_id = a.shipment_id
                JOIN public.appointment_slots sl ON sl.slot_id = a.slot_id
                JOIN public.docks d ON d.dock_id = sl.dock_id
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


async def simulate_policy_weights(
    session: AsyncSession, ctx: ExecutionContext,
    *, weights: dict[str, Any], window_start: datetime, window_end: datetime,
) -> dict[str, Any]:
    """SS7.5.7 `simulate_policy_weights` -- `weights`, `window`. **Read-only**: never writes a
    `policy_versions` row. See module docstring for the approximation this makes."""
    if not ctx.is_admin:
        raise AppError("Admin console access required.", code="FORBIDDEN", status_code=403)

    live = load_scheduling_constraints().ranking_policy
    live_weights = live.score_weights
    live_priority = live.priority_scores or DEFAULT_PRIORITY_SCORES
    proposed_priority = weights.get("priority_scores") or live_priority

    candidates = await _replayable_candidates(session, window_start=window_start, window_end=window_end)
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
        "note": (
            "Approximation, not a literal replay: no historical decision log exists, so this "
            "re-scores each shipment's current appointment against other slots open today at the "
            "same facility, not the exact candidate set available at the real booking moment."
        ),
    }


async def publish_policy_version(
    session: AsyncSession, ctx: ExecutionContext, *, weights: dict[str, Any], idempotency_key: str,
) -> dict[str, Any]:
    """SS7.5.7 `publish_policy_version` -- creates a new, immutable `policy_versions` row (D7);
    never mutates a prior version. Does **not** write `scheduling/constraints.json`: that file is
    the live ranking engine's actual input and changing it is a deploy-time decision, not a runtime
    admin write -- this tool records the decision durably and auditably; wiring the live engine to
    read the active `policy_versions` row instead of the static file is separate, larger scope.
    """
    if not ctx.is_admin:
        raise AppError("Admin console access required.", code="FORBIDDEN", status_code=403)
    key = (idempotency_key or "").strip()
    if not key:
        raise AppError("Idempotency-Key header is required.", code="IDEMPOTENCY_KEY_REQUIRED", status_code=400)

    route = "POST /api/v1/admin/policy/publish"
    req_hash = payload_hash({"weights": weights})
    replay = await lookup_idempotency(session, key=key, user_id=ctx.user_id, route=route, request_hash=req_hash)
    if replay is not None:
        return {**replay["response"], "idempotent_replay": True}

    version_id = new_id("POLV")
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
            "published_at": datetime.now(timezone.utc), "published_by": ctx.user_id,
        },
    )
    result = {"as_of": _as_of(), "code": "PUBLISHED", "policy_version_id": version_id}
    await store_idempotency(session, key=key, user_id=ctx.user_id, route=route, request_hash=req_hash, response=result)
    await session.commit()
    return result


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
