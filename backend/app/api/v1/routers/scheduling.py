import json
from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, Query, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import (
    OPS_PORTAL_ROLES,
    get_db_session,
    get_execution_context,
    get_request_id,
    require_roles,
)
from app.core.envelope import ok
from app.core.errors import AppError
from app.core.execution_context import ExecutionContext, RoleName
from app.scheduling.allocation import (
    MAX_BULK_CONFIRM_IDS,
    BulkConfirmCommand,
    CancelAppointmentCommand,
    ConfirmAppointmentCommand,
    CounterOfferCommand,
    ExpireAppointmentCommand,
    HoldForInformationCommand,
    RejectAppointmentCommand,
    RequestSlotCommand,
    RescheduleAppointmentCommand,
    bulk_confirm,
    cancel_appointment,
    confirm_appointment,
    counter_offer,
    expire_appointment,
    get_appointment_request_status,
    hold_for_information,
    reject_appointment,
    request_slot,
    reschedule_appointment,
)
from app.scheduling.feasibility import find_feasible_slots
from app.scheduling.holds import confirm_held_slot
from app.scheduling.sequencer import (
    MAX_RUN_LIST,
    STATUS_APPLIED,
    STATUS_PROPOSED,
    STATUS_SUPERSEDED,
    TRIGGER_PLANNER_REQUESTED,
    apply_schedule_proposal,
    get_scheduling_run,
    list_scheduling_runs,
    propose_facility_schedule,
)

router = APIRouter(prefix="/api/v1", tags=["scheduling"])

# Section 7.5.3's own opening line -- *"D5 says the sequencer proposes and a planner applies, so
# these are planner-scoped, not agent-scoped"* -- and the same gate `routers/planner.py` uses for
# section 7.5.1's `block_dock`/`end_dock_block`, for the same reason its docstring gives:
# `OPS_PORTAL_ROLES` would admit every operator role, and this is the planner's own persona.
#
# The asymmetry with `GET /scheduling/runs/{id}` below is deliberate and is D5 in the role table:
# reading a proposal is open to the ops portal (section 7.5.3: *"The agent may read a proposal to
# explain it; it may never apply one"*), while proposing and applying are the planner's.
SequencerCtx = Annotated[
    ExecutionContext, Depends(require_roles(RoleName.WAREHOUSE_PLANNER, RoleName.ADMIN))
]


class CancelAppointmentBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    cancellation_reason: str = Field(min_length=1, max_length=500)
    client_message_id: str | None = Field(default=None, max_length=200)


class ConfirmAppointmentBody(BaseModel):
    """section 7.5.1 `confirm_request`. `snapshot_hash` is required (section 7.5 principle 3).

    `warehouse_confirmation_ref` became optional in issue #62 -- see
    `allocation.ConfirmAppointmentCommand` for why the mandatory version would have blocked every
    confirm the planner console makes.
    """

    model_config = ConfigDict(extra="forbid")

    snapshot_hash: str = Field(min_length=1, max_length=128)
    warehouse_confirmation_ref: str | None = Field(default=None, min_length=1, max_length=200)
    note: str | None = Field(default=None, max_length=500)


class CounterOfferBody(BaseModel):
    """section 7.5.1 `counter_offer` (issue #63). `appointment_id` comes from the path."""

    model_config = ConfigDict(extra="forbid")

    dock_id: str = Field(min_length=1, max_length=100)
    start_ts: datetime
    reason_code: str = Field(min_length=1, max_length=40)
    snapshot_hash: str = Field(min_length=1, max_length=128)
    note: str | None = Field(default=None, max_length=500)


class BulkConfirmBody(BaseModel):
    """section 7.5.1 `bulk_confirm` (issue #65).

    Not shipment-scoped, unlike every other route on this router: a spike-clearing batch crosses
    shipments by construction. Each id's facility scope is validated server-side, per id, from the
    verified identity (M15) -- there is no facility argument here for a client to supply.
    """

    model_config = ConfigDict(extra="forbid")

    appointment_ids: list[str] = Field(min_length=1, max_length=MAX_BULK_CONFIRM_IDS)
    snapshot_hash: str = Field(min_length=1, max_length=128)
    warehouse_confirmation_ref: str | None = Field(default=None, min_length=1, max_length=200)
    note: str | None = Field(default=None, max_length=500)


class RescheduleAppointmentBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    new_slot_id: str = Field(min_length=1, max_length=100)
    note: str | None = Field(default=None, max_length=500)
    displayed_policy_version: str | None = Field(default=None, max_length=100)
    displayed_recommendation_id: str | None = Field(default=None, max_length=100)
    client_message_id: str | None = Field(default=None, max_length=200)


class RejectAppointmentBody(BaseModel):
    """section 7.5.1 `reject_request` (issue #66).

    **Wire change:** `rejection_reason` (free prose, 1-500 chars) became `reason_code`, validated
    against `allocation.REJECTION_REASON_CODES` in the service with a 422 naming the supported set.
    The value is rendered to the driver, which is section 7.5.1's stated reason for it being an
    enum. The old field name is not accepted as an alias -- grepped 2026-08-29, this router was its
    only caller, and keeping a deprecated free-prose door open would defeat the change.
    """

    model_config = ConfigDict(extra="forbid")

    reason_code: str = Field(min_length=1, max_length=40)
    note: str | None = Field(default=None, max_length=500)


class ExpireAppointmentBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expire_reason: str = Field(min_length=1, max_length=500)


class HoldForInformationBody(BaseModel):
    """section 7.5.1 `hold_for_information` (issue #64). `appointment_id` comes from the path.

    One field, and the two that are absent are the point: no `snapshot_hash` (this consumes no
    capacity, so section 7.5's principle-3 guard does not attach -- see the command model), and no
    deadline or duration argument. **A client cannot choose how much time the hold buys.** Letting
    it would hand the caller the unbounded sit-on-capacity the catalog's own cap exists to prevent;
    the extension is D9's own TTL, resolved server-side.
    """

    model_config = ConfigDict(extra="forbid")

    question: str = Field(min_length=1, max_length=500)


class ProposeScheduleBody(BaseModel):
    """Section 7.5.3 `propose_facility_schedule` -- `facility_id`, `horizon_end?`,
    `trigger_reason`.

    `facility_id` is optional and is a **narrowing request, never a scope assertion** (M15 /
    section 7.5 principle 1): the service passes it through
    `repositories.scope.resolve_facility_scope_with_user_scopes`, so a planner may only ever name a
    facility the server itself grants them and an `ADMIN`'s global scope is what the field exists
    for. Omitting it resolves to the caller's own facility. `extra="forbid"` means an invented
    field is a 422 rather than a silently ignored one.

    `trigger_reason` is fixed to `PLANNER_REQUESTED` here and cannot be set to
    `CAPACITY_INCIDENT`: that value belongs to section 7.5.5's delegate, which is the only thing
    that can attach a real `escalation_id`, and a client-settable trigger reason would let a
    planner-initiated run masquerade as an incident response in the audit trail.
    """

    model_config = ConfigDict(extra="forbid")

    facility_id: str | None = Field(default=None, max_length=100)
    horizon_end: datetime | None = None


class ApplyScheduleBody(BaseModel):
    """Section 7.5.3 `apply_schedule_proposal` -- `scheduling_run_id` (path), `snapshot_hash`,
    `Idempotency-Key` (header).

    **There is deliberately no per-row argument**, and its absence is the contract rather than an
    oversight: section 7.5.3 says so outright -- *"There is deliberately no 'apply these three rows'
    argument -- cherry-picking produces a schedule nobody validated (section 5.1)."* `extra="forbid"`
    is what makes that structural: a client that tries to send `appointment_ids` gets a 422.
    """

    model_config = ConfigDict(extra="forbid")

    snapshot_hash: str = Field(min_length=1, max_length=128)


@router.post("/scheduling/proposals")
async def propose_schedule(
    body: ProposeScheduleBody,
    request: Request,
    ctx: SequencerCtx,
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> dict[str, Any]:
    """Section 7.5.3 `propose_facility_schedule` / FR-SYS-016 / FR-PLN-009 (issue #49).

    **No `Idempotency-Key`, deliberately.** Section 7.5 principle 3 attaches keys to calls that
    *consume capacity*, and this one writes no `dock_occupancy` row, no appointment and no
    notification -- D5: *"Sequencer output is a reviewable artifact, never a silent write."* The
    protection a key would give is already given, and given better, by the database: the partial
    unique index behind `RUN_ALREADY_ACTIVE` means a double-submit produces one run and a named
    refusal naming it, rather than two runs sharing a key.

    Returns **200 with a typed body in both outcomes**, matching `bulk_confirm`'s posture rather
    than `request_slot`'s 409: `RUN_ALREADY_ACTIVE` is not an error, it is section 5.1's debounce
    working, and the response carries the incumbent run the planner should look at instead.
    """
    result = await propose_facility_schedule(
        session,
        ctx,
        facility_id=body.facility_id,
        horizon_end=body.horizon_end,
        trigger_reason=TRIGGER_PLANNER_REQUESTED,
    )
    message = (
        f"Proposal {result.scheduling_run_id}: " + result.explanation
        if result.code == "PROPOSED"
        else "This facility already has a proposal awaiting review."
    )
    return ok(result.model_dump(), get_request_id(request), message=message)


@router.get("/scheduling/runs")
async def scheduling_runs(
    request: Request,
    ctx: Annotated[ExecutionContext, Depends(require_roles(*OPS_PORTAL_ROLES))],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    facility_id: Annotated[str | None, Query()] = None,
    status: Annotated[str | None, Query()] = STATUS_PROPOSED,
    limit: Annotated[int, Query(ge=1, le=MAX_RUN_LIST)] = MAX_RUN_LIST,
) -> dict[str, Any]:
    """The pending-proposals read. **An addition to section 7.5.3's catalog, not an implementation
    of it** -- flagged here and in `sequencer.list_scheduling_runs`, per the same discipline
    `planner.py::dock_block_impact` states for itself.

    Two shipped surfaces need it and neither can be built from `get_scheduling_run` alone, because
    both begin without a run id:

    * `03-planner-dock-board/screens.md` section 3's `[ Review proposal (N) ]` control, whose N is
      the count of live proposals for this facility;
    * `flows-and-states.md` Flow 9's **ops-handoff** origin -- the run is created on the ops console
      by `request_sequencer_proposal`, so the planner surface never observed its id.

    `facility_id` is a narrowing request, never a scope assertion (M15): it goes through
    `resolve_facility_scope_with_user_scopes`, so it can only narrow a global-read persona or name a
    facility this caller is granted. Unlike `/scheduling/proposals`, no facility is *required* --
    "is any facility waiting on a planner" is a legitimate question for a global-read tier, and this
    is a read.

    `status` defaults to `PROPOSED` (the live set the button counts) and accepts `APPLIED` /
    `SUPERSEDED` for the audit view section 8 asks for. An unknown value is a 422 rather than a
    silently empty list -- a filter that quietly matches nothing reads as "no proposals".
    """
    if status is not None and status not in {STATUS_PROPOSED, STATUS_APPLIED, STATUS_SUPERSEDED}:
        raise AppError(
            f"Unsupported status filter '{status}'.",
            code="INVALID_STATUS",
            status_code=422,
            detail=f"Supported: {STATUS_PROPOSED}, {STATUS_APPLIED}, {STATUS_SUPERSEDED}.",
        )
    result = await list_scheduling_runs(
        session, ctx, facility_id=facility_id, status=status, limit=limit
    )
    return ok(result.model_dump(), get_request_id(request))


@router.get("/scheduling/runs/{scheduling_run_id}")
async def scheduling_run(
    scheduling_run_id: str,
    request: Request,
    ctx: Annotated[ExecutionContext, Depends(require_roles(*OPS_PORTAL_ROLES))],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> dict[str, Any]:
    """Section 7.5.3 `get_scheduling_run` / FR-PLN-009 / FR-SYS-042 (issue #49).

    Gated at `OPS_PORTAL_ROLES` rather than the planner pair, and that is D5 rather than looseness:
    section 7.5.3 says *"The agent may **read** a proposal to explain it; it may never apply one"*,
    and ops Flow 4 step 4 keeps the incident row rendering its handoff state, which needs this read.
    The facility is derived from the run's own row, so a wider role set cannot see a wider set of
    runs -- `assert_facility_visible` still refuses another facility's.

    A `GET`, and that is the whole safety story rather than a REST nicety: replaying a stored
    decision writes nothing.
    """
    result = await get_scheduling_run(session, ctx, scheduling_run_id)
    return ok(result.model_dump(), get_request_id(request))


@router.post("/scheduling/runs/{scheduling_run_id}/apply")
async def apply_schedule(
    scheduling_run_id: str,
    body: ApplyScheduleBody,
    request: Request,
    ctx: SequencerCtx,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> dict[str, Any]:
    """Section 7.5.3 `apply_schedule_proposal` / FR-PLN-009 (issue #49).

    **The one route in the sequencer group that ops may not reach.** D5's whole content is the
    split -- *"Ops triages and requests; a planner still applies"* (section 7.5.5's own note on
    `request_sequencer_proposal`) -- and `SequencerCtx` is where that is enforced, not a UI
    decision. `sequencer.apply_schedule_proposal` re-checks facility write scope on top, so the
    role gate and the scope rule agree by construction.

    `Idempotency-Key` is required: this one consumes capacity, so section 7.5 principle 3 attaches.

    Returns 409 for the two refusals with the typed body still present, so the console can render
    Flow 9 steps 4 and 5 (*"offers 'Request a fresh proposal' rather than a bare error"*, *"explains
    which constraint made the whole proposal invalid"*) from the payload rather than from a status
    code alone.
    """
    if not idempotency_key or not idempotency_key.strip():
        raise AppError(
            "Idempotency-Key header is required.", code="IDEMPOTENCY_KEY_REQUIRED", status_code=400
        )
    try:
        result = await apply_schedule_proposal(
            session,
            ctx,
            scheduling_run_id=scheduling_run_id,
            snapshot_hash=body.snapshot_hash,
            idempotency_key=idempotency_key.strip(),
        )
    except AppError:
        await session.rollback()
        raise
    except Exception:
        await session.rollback()
        raise

    payload = ok(result.model_dump(), get_request_id(request))
    if result.code in {"SNAPSHOT_DRIFT", "PARTIALLY_INFEASIBLE"}:
        payload["success"] = False
        # `detail` carries the **typed result as JSON**, not prose, and that is this codebase's
        # existing convention rather than a new one: `allocation._snapshot_stale_error`,
        # `_displacement_error` and `_interval_unavailable_error` all `json.dumps` their structured
        # refusal into `detail` for the same reason. The frontend's central error type is built from
        # `errors[0]` alone, so anything that lives only in `data` is unreachable from a rejected
        # call -- which would put `infeasible[]` (Flow 9 step 5's "explains which constraint made
        # the whole proposal invalid") and `drift` (step 4's "states this plainly") out of the
        # console's reach at exactly the moment it needs them. `data` keeps the same object, so a
        # client reading either place sees one truth.
        payload["errors"] = [
            {
                "code": result.code,
                "detail": json.dumps(result.model_dump(), default=str),
                "field": None,
            }
        ]
        return JSONResponse(status_code=409, content=payload)
    return payload


@router.get("/shipments/{shipment_id}/slots/feasible")
async def feasible_slots(
    shipment_id: str,
    request: Request,
    ctx: Annotated[ExecutionContext, Depends(get_execution_context)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    limit: Annotated[int, Query(ge=1, le=10)] = 5,
) -> dict[str, Any]:
    result = await find_feasible_slots(session, ctx, shipment_id, limit=limit)
    return ok(result.model_dump(), get_request_id(request), message="Feasible slot options computed.")


@router.post("/shipments/{shipment_id}/slots/{slot_id}/request")
async def request_shipment_slot(
    shipment_id: str,
    slot_id: str,
    body: RequestSlotCommand,
    request: Request,
    ctx: Annotated[ExecutionContext, Depends(require_roles(RoleName.DRIVER))],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> dict[str, Any]:
    if not idempotency_key or not idempotency_key.strip():
        raise AppError(
            "Idempotency-Key header is required.",
            code="IDEMPOTENCY_KEY_REQUIRED",
            status_code=400,
        )
    try:
        result = await request_slot(
            session,
            ctx,
            shipment_id=shipment_id,
            slot_id=slot_id,
            command=body,
            idempotency_key=idempotency_key.strip(),
        )
    except AppError:
        await session.rollback()
        raise
    except Exception:
        await session.rollback()
        raise
    message = (
        "Slot request is pending warehouse confirmation."
        if result.code == "SLOT_REQUESTED"
        else "Selected slot is no longer available; refreshed options returned."
    )
    body = ok(result.model_dump(), get_request_id(request), message=message)
    if result.code in {"SLOT_CONFLICT_REFRESH_REQUIRED", "SLOT_OPTIONS_STALE"}:
        body["success"] = False
        body["errors"] = [{"code": result.code, "detail": message, "field": None}]
        return JSONResponse(status_code=409, content=body)
    return body


class ConfirmHeldSlotBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    note: str | None = Field(default=None, max_length=500)


@router.post("/holds/{hold_id}/confirm")
async def confirm_hold(
    hold_id: str,
    body: ConfirmHeldSlotBody,
    request: Request,
    ctx: Annotated[ExecutionContext, Depends(require_roles(RoleName.DRIVER))],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> dict[str, Any]:
    """Section 7.1's `confirm_held_slot`: turn a live D2 hold into a PENDING_CONFIRMATION request.

    The route is `/holds/{hold_id}/confirm` rather than
    `/shipments/{shipment_id}/holds/{hold_id}/confirm` on purpose, and the difference is M15 rather
    than aesthetics: a shipment id in the path would be a client-supplied identifier sitting beside
    the hold id, and the natural (wrong) implementation scopes on the one the client sent. With only
    the hold id in the path there is nothing to trust -- the shipment is read off the held row and
    the caller's authority over *that* shipment is what is checked.
    """
    if not idempotency_key or not idempotency_key.strip():
        raise AppError(
            "Idempotency-Key header is required.",
            code="IDEMPOTENCY_KEY_REQUIRED",
            status_code=400,
        )
    try:
        result = await confirm_held_slot(
            session,
            ctx,
            hold_id=hold_id,
            note=body.note,
            idempotency_key=idempotency_key.strip(),
        )
    except Exception:
        await session.rollback()
        raise
    response = ok(
        result.model_dump(),
        get_request_id(request),
        message="Slot request is pending warehouse confirmation.",
    )
    if result.code in {"HOLD_EXPIRED", "HOLD_ALREADY_ACTIONED", "SLOT_CONFLICT_REFRESH_REQUIRED"}:
        detail = (result.conflict or {}).get("message") or "That hold is no longer live."
        response["success"] = False
        response["errors"] = [{"code": result.code, "detail": detail, "field": None}]
        return JSONResponse(status_code=409, content=response)
    return response


@router.post("/shipments/{shipment_id}/appointments/{appointment_id}/reschedule")
async def reschedule_shipment_appointment(
    shipment_id: str, appointment_id: str, body: RescheduleAppointmentBody, request: Request,
    ctx: Annotated[ExecutionContext, Depends(require_roles(RoleName.DRIVER, *OPS_PORTAL_ROLES))],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> dict[str, Any]:
    if not idempotency_key or not idempotency_key.strip():
        raise AppError("Idempotency-Key header is required.", code="IDEMPOTENCY_KEY_REQUIRED", status_code=400)
    try:
        result = await reschedule_appointment(
            session, ctx, shipment_id=shipment_id,
            command=RescheduleAppointmentCommand(appointment_id=appointment_id, **body.model_dump()),
            idempotency_key=idempotency_key.strip(),
        )
    except Exception:
        await session.rollback()
        raise
    response = ok(result.model_dump(), get_request_id(request), message="Replacement appointment requested.")
    if result.code in {"SLOT_CONFLICT_REFRESH_REQUIRED", "SLOT_OPTIONS_STALE"}:
        response["success"] = False
        response["errors"] = [{"code": result.code, "detail": "Refresh options and select again.", "field": None}]
        return JSONResponse(status_code=409, content=response)
    return response


@router.get("/shipments/{shipment_id}/appointment-request/status")
async def appointment_request_status(
    shipment_id: str,
    request: Request,
    ctx: Annotated[ExecutionContext, Depends(get_execution_context)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    appointment_id: Annotated[str | None, Query()] = None,
) -> dict[str, Any]:
    result = await get_appointment_request_status(
        session,
        ctx,
        shipment_id=shipment_id,
        appointment_id=appointment_id,
    )
    return ok(result.model_dump(), get_request_id(request), message="Appointment request status loaded.")


@router.post("/shipments/{shipment_id}/appointments/{appointment_id}/cancel")
async def cancel_shipment_appointment(
    shipment_id: str,
    appointment_id: str,
    body: CancelAppointmentBody,
    request: Request,
    ctx: Annotated[
        ExecutionContext,
        Depends(require_roles(RoleName.DRIVER, *OPS_PORTAL_ROLES)),
    ],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> dict[str, Any]:
    if not idempotency_key or not idempotency_key.strip():
        raise AppError(
            "Idempotency-Key header is required.",
            code="IDEMPOTENCY_KEY_REQUIRED",
            status_code=400,
        )
    try:
        result = await cancel_appointment(
            session,
            ctx,
            shipment_id=shipment_id,
            command=CancelAppointmentCommand(
                appointment_id=appointment_id,
                **body.model_dump(),
            ),
            idempotency_key=idempotency_key.strip(),
        )
    except Exception:
        await session.rollback()
        raise
    return ok(
        result.model_dump(),
        get_request_id(request),
        message="Appointment cancelled and slot capacity released.",
    )


@router.post("/shipments/{shipment_id}/appointments/{appointment_id}/confirm")
async def confirm_shipment_appointment(
    shipment_id: str,
    appointment_id: str,
    body: ConfirmAppointmentBody,
    request: Request,
    ctx: Annotated[ExecutionContext, Depends(require_roles(*OPS_PORTAL_ROLES))],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> dict[str, Any]:
    if not idempotency_key or not idempotency_key.strip():
        raise AppError(
            "Idempotency-Key header is required.",
            code="IDEMPOTENCY_KEY_REQUIRED",
            status_code=400,
        )
    try:
        result = await confirm_appointment(
            session,
            ctx,
            shipment_id=shipment_id,
            command=ConfirmAppointmentCommand(
                appointment_id=appointment_id,
                **body.model_dump(),
            ),
            idempotency_key=idempotency_key.strip(),
        )
    except Exception:
        await session.rollback()
        raise
    return ok(
        result.model_dump(),
        get_request_id(request),
        message="Appointment confirmed by operations.",
    )


@router.post("/shipments/{shipment_id}/appointments/{appointment_id}/counter-offer")
async def counter_offer_shipment_appointment(
    shipment_id: str,
    appointment_id: str,
    body: CounterOfferBody,
    request: Request,
    ctx: Annotated[ExecutionContext, Depends(require_roles(*OPS_PORTAL_ROLES))],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> dict[str, Any]:
    """section 7.5.1 `counter_offer` / `FR-PLN-002` (issue #63).

    Role gate is `OPS_PORTAL_ROLES`, matching the confirm/reject/expire routes it sits beside, with
    `allocation._assert_ops_scope` doing the actual facility check. **Owner fork:** section 7.5.1 is
    the *planner* catalog, and `routers/planner.py` deliberately narrows its two tools to
    `WAREHOUSE_PLANNER` + `ADMIN`. Narrowing here too would be defensible -- but narrowing
    `confirm_request`, a shipped endpoint, is a behaviour change that belongs in its own issue, and
    a new route that is stricter than its own sibling confirm would be an inconsistency with no
    safety gain.
    """
    if not idempotency_key or not idempotency_key.strip():
        raise AppError(
            "Idempotency-Key header is required.", code="IDEMPOTENCY_KEY_REQUIRED", status_code=400
        )
    try:
        result = await counter_offer(
            session, ctx, shipment_id=shipment_id,
            command=CounterOfferCommand(appointment_id=appointment_id, **body.model_dump()),
            idempotency_key=idempotency_key.strip(),
        )
    except Exception:
        await session.rollback()
        raise
    return ok(
        result.model_dump(),
        get_request_id(request),
        message="Counter-offer recorded; the proposed interval is now held for this shipment.",
    )


@router.post("/shipments/{shipment_id}/appointments/{appointment_id}/hold-for-information")
async def hold_shipment_appointment_for_information(
    shipment_id: str,
    appointment_id: str,
    body: HoldForInformationBody,
    request: Request,
    ctx: Annotated[ExecutionContext, Depends(require_roles(*OPS_PORTAL_ROLES))],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> dict[str, Any]:
    """section 7.5.1 `hold_for_information` / `FR-PLN-004` (issue #64).

    **REST only, deliberately not an LLM tool.** Checked against the design rather than assumed:
    section 7.5.4 enumerates the driver allowlist in full -- twelve tools, `hold_for_information`
    not among them -- and it is a *planner console* affordance (section 7.5.1,
    `03-planner-dock-board/flows-and-states.md` Flow 4, keyboard `H`), not something a driver's
    assistant may invoke on its own request. `app/assistant/tools.py` builds only the driver
    allowlist, so it is left untouched.

    Role gate is `OPS_PORTAL_ROLES`, matching the confirm/reject/counter-offer routes it sits beside
    and inheriting the same recorded owner fork about narrowing them to `WAREHOUSE_PLANNER` +
    `ADMIN` (see `counter_offer_shipment_appointment`). `allocation._assert_ops_scope` does the real
    facility check off the shipment read server-side; no scope id is accepted from the caller (M15).
    """
    if not idempotency_key or not idempotency_key.strip():
        raise AppError(
            "Idempotency-Key header is required.", code="IDEMPOTENCY_KEY_REQUIRED", status_code=400
        )
    try:
        result = await hold_for_information(
            session, ctx, shipment_id=shipment_id,
            command=HoldForInformationCommand(appointment_id=appointment_id, **body.model_dump()),
            idempotency_key=idempotency_key.strip(),
        )
    except Exception:
        await session.rollback()
        raise
    return ok(
        result.model_dump(),
        get_request_id(request),
        message=(
            "Held for information; the request's deadline now runs to "
            f"{result.new_deadline}."
        ),
    )


@router.post("/appointments/bulk-confirm")
async def bulk_confirm_appointments(
    body: BulkConfirmBody,
    request: Request,
    ctx: Annotated[ExecutionContext, Depends(require_roles(*OPS_PORTAL_ROLES))],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> dict[str, Any]:
    """section 7.5.1 `bulk_confirm` / `FR-PLN-006` (issue #65).

    Always 200 with a per-id outcome list, never a partial 4xx: Flow 6 step 4 requires the skipped
    rows to be *named* rather than the call to fail, and a batch where 5 of 6 ids were written is
    not an error condition. The batch-level `code` stays `BULK_CONFIRM_COMPLETED`; the per-id codes
    carry the outcome.
    """
    if not idempotency_key or not idempotency_key.strip():
        raise AppError(
            "Idempotency-Key header is required.", code="IDEMPOTENCY_KEY_REQUIRED", status_code=400
        )
    try:
        result = await bulk_confirm(
            session, ctx,
            command=BulkConfirmCommand(**body.model_dump()),
            idempotency_key=idempotency_key.strip(),
        )
    except Exception:
        await session.rollback()
        raise
    return ok(
        result.model_dump(),
        get_request_id(request),
        message=f"{result.confirmed} confirmed, {result.skipped} skipped.",
    )


@router.post("/shipments/{shipment_id}/appointments/{appointment_id}/reject")
async def reject_shipment_appointment(
    shipment_id: str, appointment_id: str, body: RejectAppointmentBody, request: Request,
    ctx: Annotated[ExecutionContext, Depends(require_roles(*OPS_PORTAL_ROLES))],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> dict[str, Any]:
    if not idempotency_key or not idempotency_key.strip():
        raise AppError("Idempotency-Key header is required.", code="IDEMPOTENCY_KEY_REQUIRED", status_code=400)
    try:
        result = await reject_appointment(
            session, ctx, shipment_id=shipment_id,
            command=RejectAppointmentCommand(appointment_id=appointment_id, **body.model_dump()),
            idempotency_key=idempotency_key.strip(),
        )
    except Exception:
        await session.rollback()
        raise
    return ok(result.model_dump(), get_request_id(request), message="Appointment rejected by operations.")


@router.post("/shipments/{shipment_id}/appointments/{appointment_id}/expire")
async def expire_shipment_appointment(
    shipment_id: str, appointment_id: str, body: ExpireAppointmentBody, request: Request,
    ctx: Annotated[ExecutionContext, Depends(require_roles(*OPS_PORTAL_ROLES))],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> dict[str, Any]:
    if not idempotency_key or not idempotency_key.strip():
        raise AppError("Idempotency-Key header is required.", code="IDEMPOTENCY_KEY_REQUIRED", status_code=400)
    try:
        result = await expire_appointment(
            session, ctx, shipment_id=shipment_id,
            command=ExpireAppointmentCommand(appointment_id=appointment_id, **body.model_dump()),
            idempotency_key=idempotency_key.strip(),
        )
    except Exception:
        await session.rollback()
        raise
    return ok(result.model_dump(), get_request_id(request), message="Appointment expired by operations.")
