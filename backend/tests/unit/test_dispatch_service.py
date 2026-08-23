"""Dispatch route/service tests for GitHub issues #10 (read-only roles) and #11 (idempotency)."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.errors import AppError
from app.core.execution_context import ExecutionContext, RoleName
from app.services.dispatch_service import (
    DISPATCH_CREATE_ROUTE,
    CreateDispatchShipmentCommand,
    create_dispatch_shipment,
)


def _ctx(role: RoleName, role_id: str = "ROL002", facility_id: str | None = "FAC-GGN-01") -> ExecutionContext:
    return ExecutionContext(
        request_id="r",
        auth_subject="sub",
        user_id="USR-DISP-TEST",
        email="ops@setuhaul.com",
        full_name="Ops User",
        role_id=role_id,
        role_name=role,
        facility_id=facility_id,
    )


def _cmd() -> CreateDispatchShipmentCommand:
    return CreateDispatchShipmentCommand(
        driver_id="DRV001",
        destination_facility_id="FAC-GGN-01",
        original_eta_ts="2026-08-16T09:00:00+05:30",
    )


# --- Issue #10: read-only ops personas must not reach a dispatch write -------------------


@pytest.mark.asyncio
async def test_create_dispatch_shipment_forbids_global_read_only_roles():
    for role_id, role in (("ROL006", RoleName.TRANSPORT_MANAGER), ("ROL007", RoleName.REGIONAL_OPERATIONS_HEAD)):
        session = AsyncMock()
        with pytest.raises(AppError) as exc_info:
            await create_dispatch_shipment(
                session, _ctx(role, role_id, None), _cmd(), idempotency_key="IDEM-RO-1"
            )
        assert exc_info.value.code == "FORBIDDEN", role
        assert exc_info.value.status_code == 403, role
        # Refused before any query runs, so no partial shipment row is possible.
        assert not session.execute.called, role
        assert not session.commit.called, role


# --- Issue #11: idempotency ---------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_dispatch_shipment_replays_stored_response_without_writing():
    """A retry carrying the same Idempotency-Key must return the stored response and create
    neither a second shipment nor a second booking."""
    stored = {"shipment_id": "SHP-DISP-ABC123", "order_reference": "ORD-XYZ"}
    session = AsyncMock()
    with patch(
        "app.services.dispatch_service.lookup_idempotency",
        new_callable=AsyncMock,
        return_value={"response": stored, "status_code": 200, "replayed": True},
    ) as lookup:
        res = await create_dispatch_shipment(
            session, _ctx(RoleName.OPERATIONS_EXECUTIVE), _cmd(), idempotency_key="IDEM-DISP-FIXED"
        )

    assert res["shipment_id"] == "SHP-DISP-ABC123"
    assert res["idempotent_replay"] is True
    assert not session.execute.called, "replay must not issue any statement"
    assert not session.commit.called, "replay must not commit"
    assert lookup.await_args.kwargs["key"] == "IDEM-DISP-FIXED"
    assert lookup.await_args.kwargs["route"] == DISPATCH_CREATE_ROUTE


@pytest.mark.asyncio
async def test_create_dispatch_shipment_derives_inner_slot_key_from_caller_key():
    """The internal request_slot call previously minted a fresh uuid4 key, which can never match
    a prior attempt and so defeated request_slot's own idempotency guard."""
    row = MagicMock()
    row.mappings.return_value.first.return_value = {
        "driver_id": "DRV001",
        "carrier_id": "CAR001",
        "driver_name": "Ravi Kumar",
        "home_base_city": "Gurugram",
        "vehicle_id": "VEH001",
        "facility_id": "FAC-GGN-01",
        "facility_name": "Gurugram DC",
    }
    session = AsyncMock()
    session.execute.return_value = row

    options = MagicMock()
    options.options = [MagicMock(slot_id="SLOT-GGN-001")]
    options.policy_version = "POL-1"
    options.recommendation_id = "REC-1"

    booking = MagicMock()
    booking.model_dump.return_value = {"code": "SLOT_REQUESTED", "appointment": {"appointment_id": "APT-1"}}

    with (
        patch("app.services.dispatch_service.lookup_idempotency", new_callable=AsyncMock, return_value=None),
        patch("app.services.dispatch_service.store_idempotency", new_callable=AsyncMock) as store,
        patch("app.services.dispatch_service.find_feasible_slots", new_callable=AsyncMock, return_value=options),
        patch("app.services.dispatch_service.request_slot", new_callable=AsyncMock, return_value=booking) as req,
    ):
        res = await create_dispatch_shipment(
            session,
            _ctx(RoleName.OPERATIONS_EXECUTIVE),
            CreateDispatchShipmentCommand(
                shipment_id="SHP-DISP-FIXED",
                driver_id="DRV001",
                destination_facility_id="FAC-GGN-01",
                original_eta_ts="2026-08-16T09:00:00+05:30",
            ),
            idempotency_key="IDEM-DISP-FIXED",
        )

    inner_key = req.await_args.kwargs["idempotency_key"]
    assert inner_key == "IDEM-DISP-FIXED:dispatch-initial-slot"
    assert inner_key != "IDEM-DISP-FIXED", "must differ from the outer key (different ledger route)"
    assert store.await_args.kwargs["key"] == "IDEM-DISP-FIXED"
    assert store.await_args.kwargs["route"] == DISPATCH_CREATE_ROUTE
    assert res["idempotent_replay"] is False
    assert res["idempotency_key"] == "IDEM-DISP-FIXED"


@pytest.mark.asyncio
async def test_dispatch_route_rejects_missing_idempotency_key():
    """Every other mutating route rejects a missing header with a typed 400; this one accepted
    the request and minted its own key."""
    from app.api.v1.routers.dispatch import dispatch_create_shipment

    request = MagicMock()
    request.state.request_id = "req-1"
    session = AsyncMock()

    for missing in (None, "", "   "):
        with pytest.raises(AppError) as exc_info:
            await dispatch_create_shipment(
                _cmd(), request, _ctx(RoleName.OPERATIONS_EXECUTIVE), session, missing
            )
        assert exc_info.value.code == "IDEMPOTENCY_KEY_REQUIRED"
        assert exc_info.value.status_code == 400
    assert not session.execute.called


@pytest.mark.asyncio
async def test_dispatch_route_threads_stripped_key_into_service():
    from app.api.v1.routers.dispatch import dispatch_create_shipment

    request = MagicMock()
    request.state.request_id = "req-1"
    session = AsyncMock()

    with patch(
        "app.api.v1.routers.dispatch.create_dispatch_shipment",
        new_callable=AsyncMock,
        return_value={"shipment_id": "SHP-DISP-1"},
    ) as svc:
        body = await dispatch_create_shipment(
            _cmd(), request, _ctx(RoleName.OPERATIONS_EXECUTIVE), session, "  IDEM-DISP-PADDED  "
        )

    assert svc.await_args.kwargs["idempotency_key"] == "IDEM-DISP-PADDED"
    assert body["success"] is True


@pytest.mark.asyncio
async def test_create_dispatch_shipment_duplicate_id_is_409_not_500():
    """A caller-supplied shipment_id that already exists previously escaped as an unhandled
    IntegrityError (500). asyncpg raises it when the INSERT executes, so the handler has to
    wrap execute(), not just commit()."""
    from sqlalchemy.exc import IntegrityError

    lookup_row = MagicMock()
    lookup_row.mappings.return_value.first.return_value = {
        "driver_id": "DRV001",
        "carrier_id": "CAR001",
        "driver_name": "Ravi Kumar",
        "home_base_city": "Gurugram",
        "vehicle_id": "VEH001",
        "facility_id": "FAC-GGN-01",
        "facility_name": "Gurugram DC",
    }

    calls = {"n": 0}

    async def execute_side_effect(*_args, **_kwargs):
        calls["n"] += 1
        # 1=driver, 2=vehicle, 3=facility lookups; 4 is the shipment INSERT.
        if calls["n"] >= 4:
            raise IntegrityError("INSERT", {}, Exception("duplicate key value"))
        return lookup_row

    session = AsyncMock()
    session.execute.side_effect = execute_side_effect

    with patch("app.services.dispatch_service.lookup_idempotency", new_callable=AsyncMock, return_value=None):
        with pytest.raises(AppError) as exc_info:
            await create_dispatch_shipment(
                session,
                _ctx(RoleName.OPERATIONS_EXECUTIVE),
                CreateDispatchShipmentCommand(
                    shipment_id="SHP-DISP-DUPLICATE",
                    driver_id="DRV001",
                    destination_facility_id="FAC-GGN-01",
                    original_eta_ts="2026-08-16T09:00:00+05:30",
                ),
                idempotency_key="IDEM-DISP-DUP",
            )

    assert exc_info.value.code == "SHIPMENT_ALREADY_EXISTS"
    assert exc_info.value.status_code == 409
    assert session.rollback.called


# --- Issue #47: E1.1 timestamptz bind types ----------------------------------------------
# `shipments.planned_departure_ts / original_eta_ts / latest_eta_ts / created_at / updated_at`
# all became `timestamptz` in E1.1, and asyncpg encodes a timestamptz parameter with its datetime
# codec only -- a `str` raises DataError, which 500'd every dispatch create in production. The
# mock session here never encodes a parameter, so the bind type has to be asserted explicitly.


def _dispatch_lookup_row() -> MagicMock:
    row = MagicMock()
    row.mappings.return_value.first.return_value = {
        "driver_id": "DRV001",
        "carrier_id": "CAR001",
        "driver_name": "Ravi Kumar",
        "home_base_city": "Gurugram",
        "vehicle_id": "VEH001",
        "facility_id": "FAC-GGN-01",
        "facility_name": "Gurugram DC",
    }
    return row


@pytest.mark.asyncio
async def test_create_dispatch_shipment_binds_datetimes_into_shipments_insert():
    from datetime import datetime

    session = AsyncMock()
    session.execute.return_value = _dispatch_lookup_row()

    with patch(
        "app.services.dispatch_service.lookup_idempotency", new_callable=AsyncMock, return_value=None
    ), patch(
        "app.services.dispatch_service.store_idempotency", new_callable=AsyncMock
    ), patch(
        "app.services.dispatch_service.find_feasible_slots", new_callable=AsyncMock
    ) as slots:
        slots.return_value = MagicMock(options=[])
        await create_dispatch_shipment(
            session, _ctx(RoleName.OPERATIONS_EXECUTIVE), _cmd(), idempotency_key="IDEM-DISP-BIND"
        )

    insert_params = next(
        call.args[1]
        for call in session.execute.await_args_list
        if len(call.args) > 1
        and isinstance(call.args[1], dict)
        and "INSERT INTO public.shipments" in str(call.args[0])
    )
    # `now` covers planned_departure_ts, created_at and updated_at; `original_eta_ts` covers both
    # original_eta_ts and latest_eta_ts. Both must be datetimes, not ISO strings.
    assert isinstance(insert_params["now"], datetime)
    assert isinstance(insert_params["original_eta_ts"], datetime)
    assert insert_params["original_eta_ts"].tzinfo is not None


@pytest.mark.asyncio
async def test_create_dispatch_shipment_rejects_eta_without_timezone():
    """`original_eta_ts` used to be written straight into a text column, so a tz-less or
    unparseable value was accepted silently. It now has to become an offset-aware datetime before
    it can be bound at all, so the refusal is explicit and happens before any write."""
    session = AsyncMock()
    session.execute.return_value = _dispatch_lookup_row()

    with patch(
        "app.services.dispatch_service.lookup_idempotency", new_callable=AsyncMock, return_value=None
    ):
        with pytest.raises(AppError) as exc_info:
            await create_dispatch_shipment(
                session,
                _ctx(RoleName.OPERATIONS_EXECUTIVE),
                CreateDispatchShipmentCommand(
                    driver_id="DRV001",
                    destination_facility_id="FAC-GGN-01",
                    original_eta_ts="2026-08-16T09:00:00",  # no offset
                ),
                idempotency_key="IDEM-DISP-NAIVE",
            )

    assert exc_info.value.code == "INVALID_ETA"
    assert exc_info.value.status_code == 422
    assert "original_eta_ts" in str(exc_info.value)
    # Refused before the INSERT: no shipment row was attempted.
    assert not any(
        "INSERT INTO public.shipments" in str(call.args[0])
        for call in session.execute.await_args_list
        if call.args
    )
