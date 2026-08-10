from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class FeasibleSlotDTO(BaseModel):
    slot_id: str
    facility_id: str
    dock_id: str
    dock_code: str
    dock_type: str
    slot_start_ts: str
    slot_end_ts: str
    score: float
    wait_minutes_from_eta: float
    state: Literal["SHOWING_ONLY"] = "SHOWING_ONLY"
    is_reserved: bool = False
    feasibility_notes: list[str] = Field(default_factory=list)


class FeasibilitySearchCommand(BaseModel):
    shipment_id: str
    target_date: str | None = None  # YYYY-MM-DD
    after_time_ts: str | None = None  # ISO timestamp filter
    revised_eta_ts: str | None = None  # optional revised ETA override


class FeasibilitySearchResultDTO(BaseModel):
    recommendation_id: str
    version_hash: str
    expires_at: str
    shipment_id: str
    destination_facility_id: str
    effective_arrival_ts: str
    feasible_slots: list[FeasibleSlotDTO]
    total_found: int


class SlotBookingCommand(BaseModel):
    shipment_id: str
    slot_id: str
    idempotency_key: str
    recommendation_id: str | None = None
    note: str | None = None


class RescheduleCommand(BaseModel):
    current_appointment_id: str
    target_slot_id: str
    idempotency_key: str
    reason: str | None = None


class CancelAppointmentCommand(BaseModel):
    appointment_id: str
    idempotency_key: str
    reason: str | None = None


class BookingResultDTO(BaseModel):
    appointment_id: str
    shipment_id: str
    slot_id: str
    dock_id: str
    appointment_status: str
    booking_source: str
    booked_at: str
    confirmed_at: str | None = None
    message: str


class EscalationCommand(BaseModel):
    shipment_id: str
    reason: str
    urgency: Literal["NORMAL", "HIGH", "CRITICAL"] = "HIGH"
