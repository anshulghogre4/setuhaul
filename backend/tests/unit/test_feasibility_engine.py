import pytest
from app.services.scheduling.feasibility import (
    check_arrival_feasibility,
    check_dock_compatibility,
    score_and_rank_slots,
)


def test_dock_compatibility():
    dock = {
        "dock_id": "DOCK-01",
        "dock_type": "REEFER",
        "supports_refrigerated": 1,
        "max_vehicle_weight_kg": 25000,
        "dock_status": "ACTIVE",
    }
    shipment_reefer = {
        "required_dock_type": "REEFER",
        "temperature_control_required": 1,
        "load_weight_kg": 15000,
    }
    is_comp, notes = check_dock_compatibility(dock, shipment_reefer)
    assert is_comp is True
    assert "Compatible REEFER bay" in notes

    shipment_heavy = {
        "required_dock_type": "REEFER",
        "temperature_control_required": 1,
        "load_weight_kg": 30000,
    }
    is_comp2, notes2 = check_dock_compatibility(dock, shipment_heavy)
    assert is_comp2 is False
    assert any("weight" in n for n in notes2)


def test_arrival_feasibility():
    slot_start = "2026-08-08T19:30:00+00:00"
    eta_on_time = "2026-08-08T18:00:00+00:00"
    eta_too_late = "2026-08-08T19:25:00+00:00"

    feasible, wait_min = check_arrival_feasibility(slot_start, eta_on_time, buffer_minutes=15)
    assert feasible is True
    assert wait_min == 90.0

    infeasible, _ = check_arrival_feasibility(slot_start, eta_too_late, buffer_minutes=15)
    assert infeasible is False


def test_score_and_rank_slots():
    cands = [
        {
            "slot": {
                "slot_id": "SLOT-01",
                "facility_id": "FAC-JAI-01",
                "slot_start_ts": "2026-08-08T20:00:00+00:00",
                "slot_end_ts": "2026-08-08T20:45:00+00:00",
            },
            "dock": {
                "dock_id": "DOCK-01",
                "dock_code": "D1",
                "dock_type": "STANDARD",
            },
            "wait_minutes": 60.0,
            "notes": ["Compatible STANDARD bay"],
        },
        {
            "slot": {
                "slot_id": "SLOT-02",
                "facility_id": "FAC-JAI-01",
                "slot_start_ts": "2026-08-08T19:00:00+00:00",
                "slot_end_ts": "2026-08-08T19:45:00+00:00",
            },
            "dock": {
                "dock_id": "DOCK-02",
                "dock_code": "D2",
                "dock_type": "STANDARD",
            },
            "wait_minutes": 15.0,
            "notes": ["Compatible STANDARD bay"],
        },
    ]

    ranked = score_and_rank_slots(cands, priority_code="HIGH", driver_eta_ts="2026-08-08T18:30:00+00:00")
    assert len(ranked) == 2
    # SLOT-02 has shorter wait time (15m vs 60m), so higher score
    assert ranked[0].slot_id == "SLOT-02"
    assert ranked[0].state == "SHOWING_ONLY"
