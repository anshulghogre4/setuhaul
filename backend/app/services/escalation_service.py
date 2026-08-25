from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.core.execution_context import ExecutionContext
from app.repositories.scope import assert_facility_write_scope, resolve_facility_scope
from app.services.idempotency import lookup_idempotency, payload_hash, store_idempotency
from app.services.ids import new_id

# E3.2 (issue #26, M3): escalation_status's stepper position (SS7.5.5 "stepper position" on
# get_escalation_queue). RESOLVED/CANCELLED share position 3 -- both are terminal, and the design
# never asks the stepper to distinguish which terminal state a case ended in, only how far along
# an in-flight one is.
STEPPER_POSITIONS: dict[str, int] = {
    "OPEN": 0,
    "ACKNOWLEDGED": 1,
    "IN_PROGRESS": 2,
    "RESOLVED": 3,
    "CANCELLED": 3,
}

# SS7.5.5's `get_escalation_queue` orders by "time-to-SLA-breach ascending", but no seeded case or
# documented policy anywhere grounds a concrete per-severity deadline -- `Source: assumption,
# untested`, the same epistemic honesty class the design doc itself already uses for resolve/
# cancel's reason_code enum (SS7.5.5's own words, two paragraphs below the tool table). These
# budgets are a reasonable, clearly-flagged placeholder, not a documented SLA policy: revisit the
# moment a real one is specified.
SLA_BUDGET_MIN: dict[str, int] = {"HIGH": 120, "MEDIUM": 480, "LOW": 1440}
DEFAULT_SLA_BUDGET_MIN = 480

RESOLVE_REASON_CODES = frozenset({"ISSUE_FIXED"})
CANCEL_REASON_CODES = frozenset({"SHIPMENT_CANCELLED", "DUPLICATE", "CREATED_IN_ERROR"})

# E2.4 (issue #24): SOLUTION_DESIGN.md section 7.4's nine canonical reasons. The live enum
# previously diverged almost completely (only WAREHOUSE_REPLY_CONFLICT overlapped) -- NO_SLOT was
# renamed to NO_FEASIBLE_SLOT (a real rename: two live rows migrated, see
# supabase/migrations/20260823100000_e24_escalation_vocabulary.sql), and CONTRADICTORY /
# APPROVAL_REQUIRED / REGULATED / EMERGENCY were dropped -- confirmed zero live usage and no
# other code reference before removing them.
#
# REQUIRES_TIME_RESOLUTION / REQUIRES_DOCK_REASSIGNMENT (D12's backfill worklist) are
# deliberately absent here: they are system-generated during the E1.1 backfill, never a value a
# caller of escalate_exception should be manually specifying.
ESCALATION_TYPES = frozenset(
    {
        "NO_FEASIBLE_SLOT",
        "PENDING_EXPIRED_UNACTIONED",
        "AMBIGUOUS_SHIPMENT",
        "LOW_CONFIDENCE_ETA",
        "WAREHOUSE_REPLY_CONFLICT",
        "NOTIFICATION_FAILED",
        "NOTIFICATION_UNROUTABLE",
        "SAFETY_OR_REGULATED",
        "CAPACITY_EVENT_CASCADE",
    }
)


class EscalateExceptionCommand(BaseModel):
    model_config = ConfigDict(extra="forbid")

    shipment_id: str = Field(min_length=1, max_length=100)
    escalation_type: str
    payload: dict[str, Any] = Field(default_factory=dict)
    severity_code: str = Field(default="HIGH", max_length=30)
    policy_version: str | None = Field(default=None, max_length=100)
    recommendation_id: str | None = Field(default=None, max_length=100)
    # Defaults True so existing deterministic/system callers (persist_noslot_escalation,
    # the ops REST route) keep writing immediately. Only the driver-chat tool passes
    # confirmed=False on its first call so an LLM misjudgment surfaces as a preview,
    # not a real escalation_queue row.
    confirmed: bool = Field(default=True)


def _as_of() -> str:
    return datetime.now(timezone.utc).isoformat()


async def _shipment_scope(session: AsyncSession, shipment_id: str) -> dict[str, Any]:
    row = (
        await session.execute(
            text(
                """
                SELECT shipment_id, destination_facility_id AS facility_id, driver_id
                FROM public.shipments WHERE shipment_id = :shipment_id
                """
            ),
            {"shipment_id": shipment_id},
        )
    ).mappings().first()
    if row is None:
        raise AppError("Shipment not found.", code="NOT_FOUND", status_code=404)
    return dict(row)


async def escalate_exception(
    session: AsyncSession, ctx: ExecutionContext, command: EscalateExceptionCommand
) -> dict[str, Any]:
    escalation_type = command.escalation_type.upper()
    if escalation_type not in ESCALATION_TYPES:
        raise AppError("Unsupported escalation type.", code="INVALID_ESCALATION_TYPE", status_code=422)

    if not command.confirmed:
        return {
            "status": "CONFIRMATION_REQUIRED",
            "code": "CONFIRMATION_REQUIRED",
            "shipment_id": command.shipment_id,
            "escalation_type": escalation_type,
            "reason": command.payload.get("reason"),
            "requires_confirmation": True,
            "note": (
                "Escalating creates a durable human-operations case for this shipment. "
                "No case has been created yet. Confirm with the driver before calling "
                "escalate_exception again with confirmed=true."
            ),
        }

    shipment = await _shipment_scope(session, command.shipment_id)
    if ctx.is_driver:
        if shipment["driver_id"] != ctx.driver_id:
            raise AppError("Shipment not in scope.", code="FORBIDDEN", status_code=403)
    else:
        assert_facility_write_scope(ctx, str(shipment["facility_id"]))

    now = _as_of()
    day = now[:10]
    dedupe_key = f"{command.shipment_id}:{day}:{escalation_type}"
    escalation_id = new_id("ESC")
    row = (
        await session.execute(
            text(
                """
                INSERT INTO public.escalation_queue (
                  escalation_id, shipment_id, facility_id, driver_id, escalation_type,
                  escalation_status, severity_code, policy_version, recommendation_id,
                  payload_json, dedupe_key, created_at, updated_at, resolved_at, resolved_by_user_id
                ) VALUES (
                  :escalation_id, :shipment_id, :facility_id, :driver_id, :escalation_type,
                  'OPEN', :severity_code, :policy_version, :recommendation_id,
                  :payload_json, :dedupe_key, :created_at, :updated_at, NULL, NULL
                )
                ON CONFLICT (dedupe_key) DO UPDATE
                SET payload_json = EXCLUDED.payload_json,
                    severity_code = EXCLUDED.severity_code,
                    policy_version = EXCLUDED.policy_version,
                    recommendation_id = EXCLUDED.recommendation_id,
                    updated_at = EXCLUDED.updated_at
                RETURNING escalation_id, shipment_id, facility_id, driver_id, escalation_type,
                          escalation_status, severity_code, policy_version, recommendation_id,
                          payload_json, dedupe_key, created_at, updated_at
                """
            ),
            {
                "escalation_id": escalation_id,
                "shipment_id": command.shipment_id,
                "facility_id": shipment["facility_id"],
                "driver_id": shipment["driver_id"],
                "escalation_type": escalation_type,
                "severity_code": command.severity_code,
                "policy_version": command.policy_version,
                "recommendation_id": command.recommendation_id,
                "payload_json": json.dumps(command.payload, default=str),
                "dedupe_key": dedupe_key,
                "created_at": now,
                "updated_at": now,
            },
        )
    ).mappings().one()
    await session.commit()
    data = dict(row)
    data["payload"] = json.loads(data.pop("payload_json"))
    return data


async def persist_noslot_escalation(
    session: AsyncSession,
    *,
    ctx: ExecutionContext,
    shipment_id: str,
    facility_id: str,
    driver_id: str | None,
    payload: dict[str, Any],
) -> dict[str, Any]:
    # Facility/driver fields are independently verified inside escalate_exception.
    del facility_id, driver_id
    return await escalate_exception(
        session,
        ctx,
        EscalateExceptionCommand(
            shipment_id=shipment_id,
            escalation_type="NO_FEASIBLE_SLOT",
            payload=payload,
            policy_version=payload.get("policy_version"),
            recommendation_id=payload.get("recommendation_id"),
        ),
    )


def _sla_remaining_min(*, severity_code: str, created_at_iso: str) -> float:
    budget = SLA_BUDGET_MIN.get(str(severity_code).upper(), DEFAULT_SLA_BUDGET_MIN)
    created_at = datetime.fromisoformat(created_at_iso)
    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=timezone.utc)
    elapsed_min = (datetime.now(timezone.utc) - created_at).total_seconds() / 60.0
    return round(budget - elapsed_min, 1)


async def get_exception_queue(
    session: AsyncSession,
    ctx: ExecutionContext,
    facility_id: str | None = None,
    owner: str = "all",
) -> dict[str, Any]:
    """SS7.5.5 `get_escalation_queue` -- `facility_id?`, `owner?` (`mine`\\|`unowned`\\|`all`).

    Ordered unowned-first, then by SLA remaining ascending (`SLA_BUDGET_MIN`'s stated caveat
    applies to the second key only -- unowned-first is the one part of the ordering SS7.5.5 states
    outright). `stepper_position` is a pure function of `escalation_status`
    (`STEPPER_POSITIONS`); `affected_shipments` is only populated for `CAPACITY_EVENT_CASCADE` rows,
    read out of the same `payload_json` `planner_service._open_capacity_cascade` already writes --
    no new column, no second query.
    """
    if owner not in {"mine", "unowned", "all"}:
        raise AppError(
            f"Unsupported owner filter '{owner}'.", code="INVALID_OWNER_FILTER", status_code=422,
            detail="Supported values: mine, unowned, all.",
        )
    # Read path: the global tier is read scope, not write authority (see ExecutionContext.is_admin).
    # A global-read persona that names no facility gets scope=None here, which deliberately means
    # "no facility filter" -- this query's WHERE clause is built conditionally, unlike the three
    # below, which bind :facility_id unconditionally and therefore pass require_facility=True.
    scope = resolve_facility_scope(ctx, facility_id)
    params: dict[str, Any] = {}
    facility_filter = ""
    if scope:
        facility_filter = "AND eq.facility_id = :facility_id"
        params["facility_id"] = scope
    owner_filter = ""
    if owner == "mine":
        owner_filter = "AND eq.owner_user_id = :caller_id"
        params["caller_id"] = ctx.user_id
    elif owner == "unowned":
        owner_filter = "AND eq.owner_user_id IS NULL"
    rows = (
        await session.execute(
            text(
                f"""
                SELECT eq.escalation_id, eq.shipment_id, eq.facility_id, eq.driver_id,
                       eq.escalation_type, eq.escalation_status, eq.severity_code,
                       eq.policy_version, eq.recommendation_id, eq.payload_json, eq.created_at,
                       eq.updated_at, eq.owner_user_id, u.full_name AS owner_name
                FROM public.escalation_queue eq
                LEFT JOIN public.users u ON u.user_id = eq.owner_user_id
                WHERE eq.escalation_status NOT IN ('RESOLVED', 'CANCELLED')
                  {facility_filter}
                  {owner_filter}
                ORDER BY (eq.owner_user_id IS NOT NULL) ASC, eq.created_at ASC
                LIMIT 100
                """
            ),
            params,
        )
    ).mappings().all()
    items = []
    for row in rows:
        item = dict(row)
        payload = json.loads(item.pop("payload_json"))
        item["payload"] = payload
        item["stepper_position"] = STEPPER_POSITIONS.get(str(item["escalation_status"]), 0)
        item["sla_remaining_min"] = _sla_remaining_min(
            severity_code=item["severity_code"], created_at_iso=item["created_at"]
        )
        item["affected_shipments"] = (
            payload.get("affected_appointments", [])
            if item["escalation_type"] == "CAPACITY_EVENT_CASCADE"
            else None
        )
        items.append(item)
    # SQL sorts on the raw column; the actual SLA-remaining ascending order (a computed value, not
    # a column) is applied here where the derived field already exists, rather than duplicating the
    # per-severity CASE expression into the query.
    items.sort(key=lambda i: (i["owner_user_id"] is not None, i["sla_remaining_min"]))
    return {"as_of": _as_of(), "source": "postgresql", "facility_id": scope, "owner": owner, "items": items}


async def _escalation_facility_id(session: AsyncSession, escalation_id: str) -> str | None:
    """The facility a write against this escalation must be scoped to.

    Tries `escalation_queue` first (it carries `facility_id` directly), then
    `driver_exceptions` joined through `shipments` (it carries none of its own). Returns `None`
    only when neither table has the id at all -- a real NOT_FOUND, not an unscoped write.
    """
    row = (
        await session.execute(
            text("SELECT facility_id FROM public.escalation_queue WHERE escalation_id = :eid"),
            {"eid": escalation_id},
        )
    ).mappings().first()
    if row is not None:
        return str(row["facility_id"])
    row = (
        await session.execute(
            text(
                """
                SELECT s.destination_facility_id AS facility_id
                FROM public.driver_exceptions e
                JOIN public.shipments s ON s.shipment_id = e.shipment_id
                WHERE e.exception_id = :eid
                """
            ),
            {"eid": escalation_id},
        )
    ).mappings().first()
    return str(row["facility_id"]) if row is not None else None


async def resolve_escalation(
    session: AsyncSession,
    ctx: ExecutionContext,
    escalation_id: str,
    resolution_note: str = "Resolved by Operations",
    reason_code: str = "ISSUE_FIXED",
    idempotency_key: str | None = None,
) -> dict[str, Any]:
    """SS7.5.5 `resolve_escalation` -- `escalation_id`, `reason_code` (`ISSUE_FIXED`).

    Fixes issue #48: the pre-E3.2 version checked only `is_operator`/`is_admin` (a role check),
    never the escalation's own `facility_id` -- any facility-scoped operator could resolve another
    facility's escalation. `assert_facility_write_scope` below is the actual fix; the role check
    stays as a fast-path rejection for roles that can never write regardless of facility.

    `idempotency_key` is optional, not required, unlike the driver-chat write tools: the existing
    REST caller (the Ops "Mark Resolved" button, live before this epic) sends no header at all,
    and making it required would break that button. When present, replay protection is real; when
    absent, the write still runs -- no worse than the endpoint's behaviour before this change.
    """
    if reason_code not in RESOLVE_REASON_CODES:
        raise AppError(
            f"Unsupported reason_code '{reason_code}'.", code="INVALID_REASON_CODE", status_code=422,
            detail=f"Supported: {', '.join(sorted(RESOLVE_REASON_CODES))}.",
        )
    if not (ctx.is_operator or ctx.is_admin):
        raise AppError("Insufficient permissions to resolve escalations.", code="FORBIDDEN", status_code=403)

    route = f"POST /api/v1/operations/escalations/{escalation_id}/resolve"
    req_hash = payload_hash({"escalation_id": escalation_id, "reason_code": reason_code})
    if idempotency_key:
        replay = await lookup_idempotency(
            session, key=idempotency_key, user_id=ctx.user_id, route=route, request_hash=req_hash
        )
        if replay is not None:
            return {**replay["response"], "idempotent_replay": True}

    facility_id = await _escalation_facility_id(session, escalation_id)
    if facility_id is None:
        raise AppError(f"Escalation '{escalation_id}' not found.", code="NOT_FOUND", status_code=404)
    assert_facility_write_scope(ctx, facility_id)

    now_iso = datetime.now(timezone.utc).isoformat()
    row = (
        await session.execute(
            text(
                """
                UPDATE public.escalation_queue
                SET escalation_status = 'RESOLVED',
                    updated_at = :now_iso,
                    resolved_at = :now_iso,
                    resolved_by_user_id = :user_id,
                    resolution_note = :note
                WHERE escalation_id = :eid
                RETURNING escalation_id, shipment_id, escalation_type, escalation_status, resolution_note
                """
            ),
            {"now_iso": now_iso, "eid": escalation_id, "user_id": ctx.user_id, "note": resolution_note},
        )
    ).mappings().first()

    if row is None:
        row = (
            await session.execute(
                text(
                    """
                    UPDATE public.driver_exceptions
                    SET exception_status = 'RESOLVED',
                        resolution_note = :note
                    WHERE exception_id = :eid
                    RETURNING exception_id AS escalation_id, shipment_id, exception_type AS escalation_type,
                              exception_status AS escalation_status, resolution_note
                    """
                ),
                {"eid": escalation_id, "note": resolution_note},
            )
        ).mappings().first()

    if row is None:
        raise AppError(f"Escalation '{escalation_id}' not found.", code="NOT_FOUND", status_code=404)

    shipment_id = row.get("shipment_id")
    if shipment_id:
        await session.execute(
            text(
                """
                UPDATE public.driver_exceptions
                SET exception_status = 'RESOLVED',
                    resolution_note = :note
                WHERE shipment_id = :shipment_id
                  AND exception_status NOT IN ('RESOLVED', 'CANCELLED', 'DUPLICATE')
                """
            ),
            {"shipment_id": shipment_id, "note": resolution_note},
        )

    result = dict(row)
    result["code"] = "RESOLVED"
    if idempotency_key:
        await store_idempotency(
            session, key=idempotency_key, user_id=ctx.user_id, route=route,
            request_hash=req_hash, response=result,
        )
    await session.commit()
    return result


async def cancel_escalation(
    session: AsyncSession,
    ctx: ExecutionContext,
    escalation_id: str,
    reason_code: str,
    resolution_note: str | None = None,
    idempotency_key: str | None = None,
) -> dict[str, Any]:
    """SS7.5.5 `cancel_escalation` -- `escalation_id`, `reason_code`, `Idempotency-Key`.

    Separate from `resolve_escalation`, not a `status` argument on it: SHIPMENT_CANCELLED/
    DUPLICATE/CREATED_IN_ERROR mean the case was never a real issue to fix, distinct from
    ISSUE_FIXED's "it was real and it's handled" -- collapsing the two into one free-form status
    string is exactly what made #48 easy to miss in the first place. `driver_exceptions` only
    (not `escalation_queue`) has no facility_id of its own, so the same `_escalation_facility_id`
    lookup used by `resolve_escalation` applies here too.
    """
    if reason_code not in CANCEL_REASON_CODES:
        raise AppError(
            f"Unsupported reason_code '{reason_code}'.", code="INVALID_REASON_CODE", status_code=422,
            detail=f"Supported: {', '.join(sorted(CANCEL_REASON_CODES))}.",
        )
    if not idempotency_key or not idempotency_key.strip():
        raise AppError(
            "Idempotency-Key header is required.", code="IDEMPOTENCY_KEY_REQUIRED", status_code=400
        )
    if not (ctx.is_operator or ctx.is_admin):
        raise AppError("Insufficient permissions to cancel escalations.", code="FORBIDDEN", status_code=403)

    route = f"POST /api/v1/operations/escalations/{escalation_id}/cancel"
    req_hash = payload_hash({"escalation_id": escalation_id, "reason_code": reason_code})
    replay = await lookup_idempotency(
        session, key=idempotency_key, user_id=ctx.user_id, route=route, request_hash=req_hash
    )
    if replay is not None:
        return {**replay["response"], "idempotent_replay": True}

    facility_id = await _escalation_facility_id(session, escalation_id)
    if facility_id is None:
        raise AppError(f"Escalation '{escalation_id}' not found.", code="NOT_FOUND", status_code=404)
    assert_facility_write_scope(ctx, facility_id)

    now_iso = datetime.now(timezone.utc).isoformat()
    note = resolution_note or f"Cancelled: {reason_code}"
    row = (
        await session.execute(
            text(
                """
                UPDATE public.escalation_queue
                SET escalation_status = 'CANCELLED',
                    updated_at = :now_iso,
                    resolved_at = :now_iso,
                    resolved_by_user_id = :user_id,
                    resolution_note = :note
                WHERE escalation_id = :eid
                RETURNING escalation_id, shipment_id, escalation_type, escalation_status, resolution_note
                """
            ),
            {"now_iso": now_iso, "eid": escalation_id, "user_id": ctx.user_id, "note": note},
        )
    ).mappings().first()

    if row is None:
        row = (
            await session.execute(
                text(
                    """
                    UPDATE public.driver_exceptions
                    SET exception_status = 'CANCELLED', resolution_note = :note
                    WHERE exception_id = :eid
                    RETURNING exception_id AS escalation_id, shipment_id, exception_type AS escalation_type,
                              exception_status AS escalation_status, resolution_note
                    """
                ),
                {"eid": escalation_id, "note": note},
            )
        ).mappings().first()

    if row is None:
        raise AppError(f"Escalation '{escalation_id}' not found.", code="NOT_FOUND", status_code=404)

    result = dict(row)
    result["code"] = "CANCELLED"
    await store_idempotency(
        session, key=idempotency_key, user_id=ctx.user_id, route=route,
        request_hash=req_hash, response=result,
    )
    await session.commit()
    return result


async def acknowledge_escalation(
    session: AsyncSession, ctx: ExecutionContext, escalation_id: str, idempotency_key: str,
) -> dict[str, Any]:
    """SS7.5.5 `acknowledge_escalation` -- `escalation_id`, `Idempotency-Key`.

    The nastiest race in this epic, same shape SS7.5.1 already names for `confirm_request` vs. the
    D9 sweeper: two coordinators acknowledging the same row. The `WHERE escalation_status = 'OPEN'`
    on the UPDATE is the actual race resolution -- exactly one commits, the loser's `RETURNING`
    comes back empty and gets `ALREADY_ACTIONED`, not a second silent claim.
    """
    if not idempotency_key or not idempotency_key.strip():
        raise AppError(
            "Idempotency-Key header is required.", code="IDEMPOTENCY_KEY_REQUIRED", status_code=400
        )
    if not (ctx.is_operator or ctx.is_admin):
        raise AppError("Insufficient permissions to acknowledge escalations.", code="FORBIDDEN", status_code=403)

    route = f"POST /api/v1/operations/escalations/{escalation_id}/acknowledge"
    req_hash = payload_hash({"escalation_id": escalation_id})
    replay = await lookup_idempotency(
        session, key=idempotency_key, user_id=ctx.user_id, route=route, request_hash=req_hash
    )
    if replay is not None:
        return {**replay["response"], "idempotent_replay": True}

    facility_id = await _escalation_facility_id(session, escalation_id)
    if facility_id is None:
        raise AppError(f"Escalation '{escalation_id}' not found.", code="NOT_FOUND", status_code=404)
    assert_facility_write_scope(ctx, facility_id)

    now_iso = datetime.now(timezone.utc).isoformat()
    row = (
        await session.execute(
            text(
                """
                UPDATE public.escalation_queue
                SET escalation_status = 'ACKNOWLEDGED', owner_user_id = :user_id, updated_at = :now_iso
                WHERE escalation_id = :eid AND escalation_status = 'OPEN'
                RETURNING escalation_id, shipment_id, escalation_status, owner_user_id
                """
            ),
            {"user_id": ctx.user_id, "now_iso": now_iso, "eid": escalation_id},
        )
    ).mappings().first()

    if row is None:
        current = (
            await session.execute(
                text(
                    "SELECT escalation_id, shipment_id, escalation_status, owner_user_id "
                    "FROM public.escalation_queue WHERE escalation_id = :eid"
                ),
                {"eid": escalation_id},
            )
        ).mappings().first()
        result = dict(current) if current else {"escalation_id": escalation_id}
        result["code"] = "ALREADY_ACTIONED"
        await session.commit()
        return result

    result = dict(row)
    result["code"] = "ACKNOWLEDGED"
    await store_idempotency(
        session, key=idempotency_key, user_id=ctx.user_id, route=route,
        request_hash=req_hash, response=result,
    )
    await session.commit()
    return result


async def reassign_escalation(
    session: AsyncSession, ctx: ExecutionContext, escalation_id: str, new_owner_id: str,
) -> dict[str, Any]:
    """SS7.5.5 `reassign_escalation` -- `escalation_id`, `new_owner_id`.

    `NOT_ACKNOWLEDGED` when nothing is owned yet -- SS7.5.5's own wording: "nothing to reassign
    until someone has claimed it". A bad `new_owner_id` (not a real `users.user_id`) is refused as
    `INVALID_OWNER` before the write, not left to surface as a raw FK violation.
    """
    if not (ctx.is_operator or ctx.is_admin):
        raise AppError("Insufficient permissions to reassign escalations.", code="FORBIDDEN", status_code=403)

    row = (
        await session.execute(
            text(
                "SELECT escalation_id, shipment_id, facility_id, owner_user_id "
                "FROM public.escalation_queue WHERE escalation_id = :eid"
            ),
            {"eid": escalation_id},
        )
    ).mappings().first()
    if row is None:
        raise AppError(f"Escalation '{escalation_id}' not found.", code="NOT_FOUND", status_code=404)
    assert_facility_write_scope(ctx, str(row["facility_id"]))
    if row["owner_user_id"] is None:
        return {
            "code": "NOT_ACKNOWLEDGED", "escalation_id": escalation_id,
            "shipment_id": row["shipment_id"], "owner_user_id": None,
        }

    owner_exists = (
        await session.execute(
            text("SELECT user_id FROM public.users WHERE user_id = :uid"), {"uid": new_owner_id}
        )
    ).mappings().first()
    if owner_exists is None:
        raise AppError(f"'{new_owner_id}' is not a known user.", code="INVALID_OWNER", status_code=422)

    updated = (
        await session.execute(
            text(
                """
                UPDATE public.escalation_queue
                SET owner_user_id = :new_owner_id, updated_at = :now_iso
                WHERE escalation_id = :eid
                RETURNING escalation_id, shipment_id, escalation_status, owner_user_id
                """
            ),
            {
                "new_owner_id": new_owner_id, "now_iso": datetime.now(timezone.utc).isoformat(),
                "eid": escalation_id,
            },
        )
    ).mappings().one()
    await session.commit()
    result = dict(updated)
    result["code"] = "REASSIGNED"
    return result


async def take_over_thread(
    session: AsyncSession, ctx: ExecutionContext, thread_id: str, escalation_id: str, idempotency_key: str,
) -> dict[str, Any]:
    """SS7.5.5 `take_over_thread` -- `thread_id`, `escalation_id`, `Idempotency-Key`.

    Sets `chat_threads.thread_status = 'ESCALATED'`, which is also the flag
    `assistant/run_assistant.py` now checks to suppress auto-reply on this thread (E3.2 wired that
    read in; before this epic nothing in the turn path ever looked at `thread_status` at all) --
    the more consequential half of "take over," since it actually stops the LLM from answering.

    Also inserts a `SYSTEM`-sender `chat_messages` row recording the join, per SS7.5.5's own
    wording ("posts the driver-visible join notice"). **Known gap, not silently glossed over**:
    the live driver chat surface renders its history from Redis (`ConversationMemory`), never from
    `chat_messages` -- confirmed by grep, nothing in the turn path reads that table. `chat_messages`
    is still the architecturally correct place for this (AGENTS.md: Redis is "bounded,
    non-authoritative conversation/session state," not a transcript source of truth), and a durable
    audit trail either way, but it will not appear inline in the driver's live feed until a future
    pass reads it into the turn's history. The auto-reply suppression above works today regardless
    of this gap; the notice's actual visibility does not.
    """
    if not idempotency_key or not idempotency_key.strip():
        raise AppError(
            "Idempotency-Key header is required.", code="IDEMPOTENCY_KEY_REQUIRED", status_code=400
        )
    if not (ctx.is_operator or ctx.is_admin):
        raise AppError("Insufficient permissions to take over a thread.", code="FORBIDDEN", status_code=403)

    route = f"POST /api/v1/operations/threads/{thread_id}/take-over"
    req_hash = payload_hash({"thread_id": thread_id, "escalation_id": escalation_id})
    replay = await lookup_idempotency(
        session, key=idempotency_key, user_id=ctx.user_id, route=route, request_hash=req_hash
    )
    if replay is not None:
        return {**replay["response"], "idempotent_replay": True}

    escalation_facility_id = await _escalation_facility_id(session, escalation_id)
    if escalation_facility_id is None:
        raise AppError(f"Escalation '{escalation_id}' not found.", code="NOT_FOUND", status_code=404)
    assert_facility_write_scope(ctx, escalation_facility_id)

    thread = (
        await session.execute(
            text("SELECT thread_id, shipment_id, thread_status FROM public.chat_threads WHERE thread_id = :tid"),
            {"tid": thread_id},
        )
    ).mappings().first()
    if thread is None:
        raise AppError(f"Thread '{thread_id}' not found.", code="NOT_FOUND", status_code=404)

    if str(thread["thread_status"]) == "ESCALATED":
        result = {
            "code": "ALREADY_TAKEN_OVER", "thread_id": thread_id, "escalation_id": escalation_id,
            "thread_status": "ESCALATED",
        }
        await session.commit()
        return result

    now_iso = datetime.now(timezone.utc).isoformat()
    await session.execute(
        text("UPDATE public.chat_threads SET thread_status = 'ESCALATED' WHERE thread_id = :tid"),
        {"tid": thread_id},
    )
    await session.execute(
        text(
            """
            INSERT INTO public.chat_messages (
              chat_message_id, thread_id, sender_type, sender_reference, message_text, message_ts
            ) VALUES (:mid, :tid, 'SYSTEM', :sender_ref, :text, :ts)
            """
        ),
        {
            "mid": new_id("MSG"), "tid": thread_id, "sender_ref": ctx.user_id,
            "text": f"{ctx.full_name} from Operations has joined this conversation.", "ts": now_iso,
        },
    )
    result = {
        "code": "TAKEN_OVER", "thread_id": thread_id, "escalation_id": escalation_id,
        "thread_status": "ESCALATED",
    }
    await store_idempotency(
        session, key=idempotency_key, user_id=ctx.user_id, route=route,
        request_hash=req_hash, response=result,
    )
    await session.commit()
    return result


async def hand_back_thread(session: AsyncSession, ctx: ExecutionContext, thread_id: str) -> dict[str, Any]:
    """SS7.5.5 `hand_back_thread` -- `thread_id` only.

    No `escalation_id` argument in the design's own table, unlike `take_over_thread` -- so this has
    to *find* the escalation this thread belongs to rather than being told. No FK links
    `chat_threads` to `escalation_queue` directly; the only column both tables share is
    `shipment_id`, so that is the join this uses (documented here since it is inferred, not an
    explicit schema relationship). `NOT_IN_PROGRESS` covers both "already handed back" (thread not
    `ESCALATED`) and "no acknowledged escalation to hand back" (SS7.5.5's own wording: "refuses on
    an unacknowledged escalation").
    """
    if not (ctx.is_operator or ctx.is_admin):
        raise AppError("Insufficient permissions to hand back a thread.", code="FORBIDDEN", status_code=403)

    thread = (
        await session.execute(
            text("SELECT thread_id, shipment_id, thread_status FROM public.chat_threads WHERE thread_id = :tid"),
            {"tid": thread_id},
        )
    ).mappings().first()
    if thread is None:
        raise AppError(f"Thread '{thread_id}' not found.", code="NOT_FOUND", status_code=404)

    if str(thread["thread_status"]) != "ESCALATED":
        return {"code": "NOT_IN_PROGRESS", "thread_id": thread_id, "thread_status": str(thread["thread_status"])}

    escalation = (
        await session.execute(
            text(
                """
                SELECT escalation_id, facility_id, owner_user_id
                FROM public.escalation_queue
                WHERE shipment_id = :shipment_id AND escalation_status IN ('ACKNOWLEDGED', 'IN_PROGRESS')
                ORDER BY created_at DESC
                LIMIT 1
                """
            ),
            {"shipment_id": thread["shipment_id"]},
        )
    ).mappings().first()
    if escalation is None or escalation["owner_user_id"] is None:
        return {"code": "NOT_IN_PROGRESS", "thread_id": thread_id, "thread_status": str(thread["thread_status"])}
    assert_facility_write_scope(ctx, str(escalation["facility_id"]))

    now_iso = datetime.now(timezone.utc).isoformat()
    await session.execute(
        text("UPDATE public.chat_threads SET thread_status = 'OPEN' WHERE thread_id = :tid"),
        {"tid": thread_id},
    )
    await session.execute(
        text(
            """
            INSERT INTO public.chat_messages (
              chat_message_id, thread_id, sender_type, sender_reference, message_text, message_ts
            ) VALUES (:mid, :tid, 'SYSTEM', :sender_ref, :text, :ts)
            """
        ),
        {
            "mid": new_id("MSG"), "tid": thread_id, "sender_ref": ctx.user_id,
            "text": "Operations has handed this conversation back to the assistant.", "ts": now_iso,
        },
    )
    await session.commit()
    return {
        "code": "HANDED_BACK", "thread_id": thread_id, "escalation_id": str(escalation["escalation_id"]),
        "thread_status": "OPEN",
    }


async def get_pending_confirmations(
    session: AsyncSession, ctx: ExecutionContext, facility_id: str | None
) -> dict[str, Any]:
    scope = resolve_facility_scope(ctx, facility_id, require_facility=True)
    rows = (
        await session.execute(
            text(
                """
                SELECT a.appointment_id, a.shipment_id, s.driver_id, s.order_reference,
                       sl.facility_id, sl.dock_id, sl.slot_start_ts, sl.slot_end_ts,
                       a.booked_at
                FROM public.appointments a
                JOIN public.appointment_slots sl ON sl.slot_id = a.slot_id
                JOIN public.shipments s ON s.shipment_id = a.shipment_id
                WHERE a.appointment_status = 'PENDING_CONFIRMATION'
                  AND sl.facility_id = :facility_id
                ORDER BY a.booked_at ASC
                LIMIT 100
                """
            ),
            {"facility_id": scope},
        )
    ).mappings().all()
    return {"as_of": _as_of(), "source": "postgresql", "facility_id": scope, "items": [dict(r) for r in rows]}


async def get_dock_status(session: AsyncSession, ctx: ExecutionContext, facility_id: str | None) -> dict[str, Any]:
    scope = resolve_facility_scope(ctx, facility_id, require_facility=True)
    rows = (
        await session.execute(
            text(
                """
                SELECT d.dock_id, d.dock_code, d.dock_type, d.dock_status,
                       count(sl.slot_id) FILTER (WHERE sl.slot_status = 'OPEN')::int AS open_slots
                FROM public.docks d
                LEFT JOIN public.appointment_slots sl ON sl.dock_id = d.dock_id
                WHERE d.facility_id = :facility_id
                GROUP BY d.dock_id, d.dock_code, d.dock_type, d.dock_status
                ORDER BY d.dock_code
                """
            ),
            {"facility_id": scope},
        )
    ).mappings().all()
    return {"as_of": _as_of(), "source": "postgresql", "facility_id": scope, "docks": [dict(row) for row in rows]}


async def get_queue_status(session: AsyncSession, ctx: ExecutionContext, facility_id: str | None) -> dict[str, Any]:
    scope = resolve_facility_scope(ctx, facility_id, require_facility=True)
    pending = (
        await session.execute(
            text(
                """
                SELECT count(*)::int FROM public.appointments a
                JOIN public.appointment_slots sl ON sl.slot_id = a.slot_id
                WHERE sl.facility_id = :facility_id AND a.appointment_status = 'PENDING_CONFIRMATION'
                """
            ),
            {"facility_id": scope},
        )
    ).scalar_one()
    open_escalations = (
        await session.execute(
            text(
                """
                SELECT count(*)::int FROM public.escalation_queue
                WHERE facility_id = :facility_id AND escalation_status IN ('OPEN', 'IN_PROGRESS')
                """
            ),
            {"facility_id": scope},
        )
    ).scalar_one()
    return {
        "as_of": _as_of(),
        "source": "postgresql",
        "facility_id": scope,
        "pending_appointments": pending,
        "open_escalations": open_escalations,
    }
