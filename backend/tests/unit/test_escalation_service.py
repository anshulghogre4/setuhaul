import pytest
from pydantic import ValidationError

from app.services.escalation_service import EscalateExceptionCommand


def test_escalation_command_rejects_unknown_fields():
    with pytest.raises(ValidationError):
        EscalateExceptionCommand(  # type: ignore[call-arg]
            shipment_id="SHP1017",
            escalation_type="NO_SLOT",
            untrusted_override=True,  # type: ignore[call-arg]
        )


def test_escalation_command_accepts_versioned_recommendation_payload():
    command = EscalateExceptionCommand(
        shipment_id="SHP1017",
        escalation_type="NO_SLOT",
        policy_version="sprint3_constraints_v1",
        recommendation_id="REC-123",
        payload={"blocking_reasons": [{"failure_code": "NO_CANDIDATE_SLOTS"}]},
    )

    assert command.escalation_type == "NO_SLOT"
    assert command.recommendation_id == "REC-123"


@pytest.mark.asyncio
async def test_resolve_escalation_updates_db_status():
    from unittest.mock import AsyncMock, MagicMock
    from app.services.escalation_service import resolve_escalation
    from app.core.execution_context import ExecutionContext, RoleName

    ctx = ExecutionContext(
        request_id="r",
        auth_subject="sub",
        user_id="USR-OPS-TEST",
        email="ops@setuhaul.com",
        full_name="Ops User",
        role_id="ROL002",
        role_name=RoleName.OPERATIONS_EXECUTIVE,
        facility_id="FAC-GGN-01",
    )

    mock_row = MagicMock()
    mock_row.mappings.return_value.first.return_value = {
        "escalation_id": "ESC-TEST-99",
        "shipment_id": "SHP1006",
        "escalation_type": "NO_SLOT",
        "escalation_status": "RESOLVED",
    }

    mock_session = AsyncMock()
    mock_session.execute.return_value = mock_row

    res = await resolve_escalation(mock_session, ctx, "ESC-TEST-99", resolution_note="Approved by Ops Admin")

    assert res["escalation_id"] == "ESC-TEST-99"
    assert res["escalation_status"] == "RESOLVED"
    assert mock_session.commit.called


@pytest.mark.asyncio
async def test_resolve_escalation_persists_resolution_note():
    from unittest.mock import AsyncMock, MagicMock
    from app.services.escalation_service import resolve_escalation
    from app.core.execution_context import ExecutionContext, RoleName

    ctx = ExecutionContext(
        request_id="r",
        auth_subject="sub",
        user_id="USR-OPS-TEST",
        email="ops@setuhaul.com",
        full_name="Ops User",
        role_id="ROL002",
        role_name=RoleName.OPERATIONS_EXECUTIVE,
        facility_id="FAC-GGN-01",
    )

    mock_row = MagicMock()
    mock_row.mappings.return_value.first.return_value = {
        "escalation_id": "ESC-TEST-99",
        "shipment_id": "SHP1006",
        "escalation_type": "NO_SLOT",
        "escalation_status": "RESOLVED",
        "resolution_note": "Slot manually confirmed at dock",
    }

    mock_session = AsyncMock()
    mock_session.execute.return_value = mock_row

    res = await resolve_escalation(
        mock_session, ctx, "ESC-TEST-99", resolution_note="Slot manually confirmed at dock"
    )

    assert res["resolution_note"] == "Slot manually confirmed at dock"
    # First call is the escalation_queue update; its bound params must carry the note.
    first_call_params = mock_session.execute.call_args_list[0].args[1]
    assert first_call_params["note"] == "Slot manually confirmed at dock"


@pytest.mark.asyncio
async def test_escalate_exception_requires_confirmation_before_write():
    from unittest.mock import AsyncMock
    from app.services.escalation_service import EscalateExceptionCommand, escalate_exception
    from app.core.execution_context import ExecutionContext, RoleName

    ctx = ExecutionContext(
        request_id="r",
        auth_subject="sub",
        user_id="USR001",
        email="ravi.kumar@setuhaul.com",
        full_name="Ravi Kumar",
        role_id="ROL001",
        role_name=RoleName.DRIVER,
        driver_id="DRV001",
    )
    mock_session = AsyncMock()

    res = await escalate_exception(
        mock_session,
        ctx,
        EscalateExceptionCommand(
            shipment_id="SHP-D16-RAVI",
            escalation_type="NO_SLOT",
            payload={"reason": "driver asked for help"},
            confirmed=False,
        ),
    )

    assert res["status"] == "CONFIRMATION_REQUIRED"
    assert res["requires_confirmation"] is True
    # No DB call at all — not even the shipment-scope lookup — until confirmed=True.
    assert mock_session.execute.await_count == 0


@pytest.mark.asyncio
async def test_get_pending_confirmations_forbids_cross_facility_operator():
    from unittest.mock import AsyncMock
    from app.services.escalation_service import get_pending_confirmations
    from app.core.execution_context import ExecutionContext, RoleName
    from app.core.errors import AppError

    ctx = ExecutionContext(
        request_id="r",
        auth_subject="sub",
        user_id="USR-OPS-TEST",
        email="ops@setuhaul.com",
        full_name="Ops User",
        role_id="ROL002",
        role_name=RoleName.OPERATIONS_EXECUTIVE,
        facility_id="FAC-GGN-01",
    )
    mock_session = AsyncMock()

    with pytest.raises(AppError) as exc_info:
        await get_pending_confirmations(mock_session, ctx, "FAC-JAI-01")
    assert exc_info.value.code == "FORBIDDEN"


@pytest.mark.asyncio
async def test_get_pending_confirmations_scopes_to_own_facility():
    from unittest.mock import AsyncMock, MagicMock
    from app.services.escalation_service import get_pending_confirmations
    from app.core.execution_context import ExecutionContext, RoleName

    ctx = ExecutionContext(
        request_id="r",
        auth_subject="sub",
        user_id="USR-OPS-TEST",
        email="ops@setuhaul.com",
        full_name="Ops User",
        role_id="ROL002",
        role_name=RoleName.OPERATIONS_EXECUTIVE,
        facility_id="FAC-GGN-01",
    )
    mock_rows = MagicMock()
    mock_rows.mappings.return_value.all.return_value = [
        {
            "appointment_id": "APT-1",
            "shipment_id": "SHP-RS-PENDING",
            "driver_id": "DRV-RS-01",
            "order_reference": "ORD-RS-001",
            "facility_id": "FAC-GGN-01",
            "dock_id": "DOCK-GGN-D2",
            "slot_start_ts": "2026-08-16T09:00:00+05:30",
            "slot_end_ts": "2026-08-16T09:30:00+05:30",
            "booked_at": "2026-08-16T21:25:23+00:00",
        }
    ]
    mock_session = AsyncMock()
    mock_session.execute.return_value = mock_rows

    res = await get_pending_confirmations(mock_session, ctx, None)

    assert res["facility_id"] == "FAC-GGN-01"
    assert len(res["items"]) == 1
    assert res["items"][0]["appointment_id"] == "APT-1"
    params = mock_session.execute.call_args.args[1]
    assert params["facility_id"] == "FAC-GGN-01"


@pytest.mark.asyncio
async def test_resolve_escalation_forbids_global_read_only_roles():
    """Issue #10 acceptance: TRANSPORT_MANAGER / REGIONAL_OPERATIONS_HEAD hold only
    *_read_global permissions, so they must be refused on this write even though they sit in
    OPS_PORTAL_ROLES and therefore clear the router-level require_roles gate."""
    from unittest.mock import AsyncMock
    from app.services.escalation_service import resolve_escalation
    from app.core.execution_context import ExecutionContext, RoleName
    from app.core.errors import AppError

    for role_id, role in (("ROL006", RoleName.TRANSPORT_MANAGER), ("ROL007", RoleName.REGIONAL_OPERATIONS_HEAD)):
        ctx = ExecutionContext(
            request_id="r",
            auth_subject="sub",
            user_id="USR-RO-TEST",
            email="readonly@setuhaul.com",
            full_name="Read Only",
            role_id=role_id,
            role_name=role,
        )
        mock_session = AsyncMock()
        with pytest.raises(AppError) as exc_info:
            await resolve_escalation(mock_session, ctx, "ESC-TEST-99", resolution_note="Should not persist")
        assert exc_info.value.code == "FORBIDDEN", role
        assert exc_info.value.status_code == 403, role
        assert not mock_session.commit.called, f"{role} must not reach a commit"


@pytest.mark.asyncio
async def test_resolve_escalation_still_allows_admin():
    """Guards against over-correcting issue #10 into locking real admins out."""
    from unittest.mock import AsyncMock, MagicMock
    from app.services.escalation_service import resolve_escalation
    from app.core.execution_context import ExecutionContext, RoleName

    ctx = ExecutionContext(
        request_id="r",
        auth_subject="sub",
        user_id="USR999",
        email="admin@setuhaul.com",
        full_name="Admin",
        role_id="ROL008",
        role_name=RoleName.ADMIN,
    )
    mock_row = MagicMock()
    mock_row.mappings.return_value.first.return_value = {
        "escalation_id": "ESC-TEST-99",
        "shipment_id": "SHP1006",
        "escalation_type": "NO_SLOT",
        "escalation_status": "RESOLVED",
    }
    mock_session = AsyncMock()
    mock_session.execute.return_value = mock_row

    res = await resolve_escalation(mock_session, ctx, "ESC-TEST-99", resolution_note="Approved by Admin")

    assert res["escalation_status"] == "RESOLVED"
    assert mock_session.commit.called


@pytest.mark.asyncio
async def test_global_read_only_role_keeps_cross_facility_read():
    """The fix must not over-correct: these personas are granted *_read_global, so a
    cross-facility read must still succeed (only their write paths close)."""
    from unittest.mock import AsyncMock, MagicMock
    from app.services.escalation_service import get_pending_confirmations
    from app.core.execution_context import ExecutionContext, RoleName

    ctx = ExecutionContext(
        request_id="r",
        auth_subject="sub",
        user_id="USR-RO-TEST",
        email="readonly@setuhaul.com",
        full_name="Read Only",
        role_id="ROL006",
        role_name=RoleName.TRANSPORT_MANAGER,
    )
    mock_rows = MagicMock()
    mock_rows.mappings.return_value.all.return_value = []
    mock_session = AsyncMock()
    mock_session.execute.return_value = mock_rows

    res = await get_pending_confirmations(mock_session, ctx, "FAC-JAI-01")
    assert res["facility_id"] == "FAC-JAI-01"
