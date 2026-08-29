/**
 * Planner dock board -- types.
 *
 * Every field here is copied from a verified backend response, not invented. Source for each
 * block is named at the point it is used; the two authoritative reads for the block-dock group
 * (the only group with a complete backend this pass -- `implementation-spec.md` section 0.1) are
 * `backend/app/services/planner_service.py` (`DockBlockResult` / `DockBlockImpact`) and
 * `backend/app/services/operations_reads.py::get_dock_snapshot` (the dock list -- section 7.5.1
 * names no dock-listing tool of its own, so the facility's existing `dock-snapshot` read, already
 * reachable by `WAREHOUSE_PLANNER` via `OPS_PORTAL_ROLES`, supplies the block-dock form's dock
 * select. Flagged as an addition, same discipline `get_dock_block_impact`'s own docstring uses).
 */

/** `docks` row shape -- `repositories/facilities.py::list_docks`, via `GET /operations/dock-snapshot`. */
export type DockType = 'STANDARD' | 'REEFER' | 'HEAVY'
export type DockStatus = 'ACTIVE' | 'MAINTENANCE' | 'OUT_OF_SERVICE' | 'INACTIVE'

export type Dock = {
  dock_id: string
  facility_id: string
  dock_code: string
  dock_type: DockType
  supports_refrigerated: boolean
  max_vehicle_weight_kg: number | null
  dock_status: DockStatus
}

/** One row of `block_dock`/`get_dock_block_impact`'s `affected_appointments[]`
 *  (`planner_service.py::_affected_appointments`). */
export type AffectedAppointment = {
  occupancy_id: number
  appointment_id: string
  dock_id: string
  window_start: string
  window_end: string
  appointment_status: string
  shipment_id: string
  driver_id: string | null
  priority_code: string | null
  load_weight_kg: number | null
}

/** `dock_status_events` row shape, as returned inside `conflicting_event` (`ALREADY_BLOCKED`). */
export type ConflictingEvent = {
  dock_event_id: string
  dock_id: string
  event_type: string
  event_start_ts: string
  event_end_ts: string | null
  reason: string | null
}

/** `GET /planner/docks/{dock_id}/block-impact` -- `planner_service.py::DockBlockImpact`. */
export type DockBlockImpact = {
  as_of: string
  source: string
  freshness: string
  dock_id: string
  facility_id: string
  window_start: string
  window_end: string
  affected_appointments: AffectedAppointment[]
  affected_count: number
  conflicting_event: ConflictingEvent | null
}

/** `POST /planner/docks/{dock_id}/block` and `.../dock-status-events/{id}/end` --
 *  `planner_service.py::DockBlockResult`. */
export type DockBlockResult = {
  as_of: string
  source: string
  freshness: string
  code: 'BLOCKED' | 'ALREADY_BLOCKED' | 'UNBLOCKED' | 'NOT_BLOCKED'
  dock_id: string
  facility_id: string
  dock_status_event_id: string | null
  window_start: string | null
  window_end: string | null
  reason: string | null
  affected_appointments: AffectedAppointment[]
  affected_count: number
  escalation_id: string | null
  conflicting_event: ConflictingEvent | null
  idempotency_key: string | null
  idempotent_replay: boolean
}
