import pytest
from unittest.mock import AsyncMock, MagicMock
from app.core.execution_context import ExecutionContext, RoleName
from app.core.errors import AppError
from app.services.driver_reads import (
    get_vehicle_and_carrier_details,
    get_gate_and_queue_status,
    get_facility_rules_and_restrictions,
    report_vehicle_breakdown_or_incident,
    get_dock_maintenance_alerts,
    get_exception_status,
)


@pytest.fixture
def driver_ctx():
    return ExecutionContext(
        request_id="req-test-1",
        auth_subject="sub-test-1",
        user_id="USR001",
        role_id="ROL001",
        role_name=RoleName.DRIVER,
        roles=[RoleName.DRIVER],
        full_name="Ravi Kumar",
        email="ravi.kumar@setuhaul.com",
        driver_id="DRV001",
    )


@pytest.fixture
def mock_session():
    session = AsyncMock()
    session.execute = AsyncMock()
    return session


@pytest.mark.asyncio
async def test_get_vehicle_and_carrier_details_forbidden(mock_session, driver_ctx):
    mock_active = MagicMock()
    mock_active.mappings.return_value.all.return_value = []
    
    row_data = {
        "shipment_id": "SHP1002",
        "carrier_id": "CAR001",
        "driver_id": "DRV002",
        "vehicle_id": "VEH001",
        "load_weight_kg": 5000,
        "registration_number": "MH12AB1234",
        "capacity_kg": 10000,
        "refrigeration_capable": 1,
        "vehicle_type_code": "REEFER_24",
        "vehicle_type_description": "24ft Refrigerated Truck",
        "typical_dock_type": "REEFER",
        "carrier_name": "SetuExpress",
        "contact_email": "ops@setuexpress.com",
        "contact_phone": "+919876543210",
    }
    
    mapping_mock = MagicMock()
    mapping_mock.mappings.return_value.first.return_value = row_data
    mock_session.execute.return_value = mapping_mock

    with pytest.raises(AppError) as exc_info:
        await get_vehicle_and_carrier_details(mock_session, driver_ctx, "SHP1002")
    assert exc_info.value.code == "FORBIDDEN"


@pytest.mark.asyncio
async def test_get_exception_status_returns_resolution_note(mock_session, driver_ctx):
    mock_rows = MagicMock()
    mock_rows.mappings.return_value.all.return_value = [
        {
            "exception_id": "EXC-1",
            "shipment_id": "SHP1017",
            "driver_id": "DRV001",
            "thread_id": "THR-1",
            "exception_type": "DELAY",
            "reported_at": "2026-08-16T10:00:00Z",
            "reported_delay_min": 30,
            "declared_eta_ts": "2026-08-16T12:00:00Z",
            "severity_code": "MEDIUM",
            "exception_status": "RESOLVED",
            "description": "Traffic delay",
            "dedupe_key": "SHP1017:2026-08-16:DELAY",
            "resolution_note": "Slot manually confirmed at dock",
        }
    ]
    mock_session.execute.return_value = mock_rows

    res = await get_exception_status(mock_session, driver_ctx, "SHP1017")

    assert res["items"][0]["exception_status"] == "RESOLVED"
    assert res["items"][0]["resolution_note"] == "Slot manually confirmed at dock"


@pytest.mark.asyncio
async def test_report_vehicle_breakdown_or_incident(mock_session, driver_ctx):
    mock_mapping = MagicMock()
    mock_mapping.mappings.return_value.first.return_value = {
        "shipment_id": "SHP1017",
        "driver_id": "DRV001",
        "destination_facility_id": "FAC001",
    }
    mock_mapping.mappings.return_value.all.return_value = [
        {"shipment_id": "SHP1017", "driver_id": "DRV001", "current_status": "IN_TRANSIT", "destination_facility_id": "FAC001"}
    ]
    mock_session.execute.return_value = mock_mapping

    res = await report_vehicle_breakdown_or_incident(
        mock_session,
        driver_ctx,
        shipment_id="SHP1017",
        incident_type="BREAKDOWN",
        description="Engine breakdown on NH-48 highway",
        reported_delay_min=60,
    )

    assert res["status"] == "PERSISTED"
    assert res["code"] == "INCIDENT_REPORTED"
    assert res["incident_type"] == "BREAKDOWN"
    assert res["severity_code"] == "CRITICAL"
    assert res["driver_id"] == "DRV001"


@pytest.mark.asyncio
async def test_get_dock_maintenance_alerts(mock_session, driver_ctx):
    mock_active = MagicMock()
    mock_active.mappings.return_value.all.return_value = []
    
    rows = [
        {
            "dock_event_id": "DEV001",
            "dock_id": "DCK001",
            "dock_code": "D-01",
            "facility_id": "FAC001",
            "event_type": "MAINTENANCE",
            "event_start_ts": "2026-08-10T10:00:00Z",
            "event_end_ts": "2026-08-10T16:00:00Z",
            "reason": "Hydraulic lift maintenance",
            "created_at": "2026-08-10T09:00:00Z",
        }
    ]
    mock_mapping = MagicMock()
    mock_mapping.mappings.return_value.all.return_value = rows
    mock_mapping.mappings.return_value.first.return_value = None
    mock_session.execute.return_value = mock_mapping

    res = await get_dock_maintenance_alerts(mock_session, driver_ctx, facility_id="FAC001")
    assert res["source"] == "postgresql"
    assert len(res["alerts"]) == 1
    assert res["alerts"][0]["dock_code"] == "D-01"
