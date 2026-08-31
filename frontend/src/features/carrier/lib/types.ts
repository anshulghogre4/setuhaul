/**
 * Response shapes for §7.5.6's five carrier-portal reads.
 *
 * **Copied from the live payloads, not from the design docs** — every field below was read off
 * `backend/app/services/carrier_reads.py` and `backend/app/repositories/carrier.py` during this
 * build, so a field the design assumes but the backend never returns is visibly absent here
 * rather than silently optional. Two such absences are load-bearing on this surface and are
 * recorded where they bite:
 *
 *  1. **`promise_state` is no longer a raw column read (issues #85/#87, 2026-08-31).** It is
 *     composed server-side from `appointments` *and* `dock_occupancy`, so `HELD` can now arrive
 *     here and does. `SHOWN` still cannot, and that is a decision rather than a gap: it is a
 *     presentation-only state with no persisted counterpart anywhere in the product. A shipment
 *     with neither an appointment nor a live hold is `null` — not `'SHOWN'`. See `flags.ts` and
 *     `promise.ts`.
 *  2. There is **no decision-deadline field anywhere** on `get_shipment_detail`.
 *     `public.appointments` has no `expires_at`/deadline column at all (verified against the
 *     baseline migration and `backend/app/scheduling/expiry.py:75-81`, whose own comment states
 *     the D9 deadline is *derived* as `booked_at + ttl` server-side and never stored). So
 *     `stitch-prompts.md` §8's `Decision by 11:57.` line has nothing to render from. See
 *     `screens/shipment-detail.tsx`.
 */

/** The four states the DESIGN specifies. Only the last two can occur in live data today (#53). */
export type PromiseState = 'SHOWN' | 'HELD' | 'PENDING_CONFIRMATION' | 'CONFIRMED'

/**
 * What `promise_state` can actually be on the wire.
 *
 * `appointments_appointment_status_check` admits eight values and nothing else — **plus `HELD`,
 * which is not one of them and never will be** (issue #85/#87, 2026-08-31).
 *
 * `promise_state` stopped being a raw column read: `repositories/carrier.py::_PROMISE_STATE_SQL`
 * composes it from two tables, because §4 is explicit that a hold has no `appointments` row at all
 * (*"Held is not booked"*). An active appointment status passes straight through; otherwise a live
 * `dock_occupancy` hold answers `HELD`. So this union is the set of values the *derived* field can
 * take, which is deliberately not the same set the CHECK constraint admits.
 *
 * `null` still means no current appointment **and** no live hold.
 */
export type LivePromiseState =
  | 'HELD'
  | 'PENDING_CONFIRMATION'
  | 'CONFIRMED'
  | 'IN_PROGRESS'
  | 'COMPLETED'
  | 'CANCELLED'
  | 'REJECTED'
  | 'EXPIRED'
  | 'NO_SHOW'

/** Which table named the promise. A surface rendering a HELD countdown has to know it came from
 *  `dock_occupancy` and not from a status column that structurally cannot express it. */
export type PromiseStateSource = 'appointments' | 'dock_occupancy_hold'

export type ScopeBlock = {
  carrier_id: string
  read_only: boolean
}

export type OnTimeSummary = {
  window: string
  /** `null`, never `0`, when there were no arrivals to measure (`carrier_reads._percent`). */
  percent: number | null
  arrivals: number
  previous_percent: number | null
  previous_arrivals: number
  /** Percentage POINTS, not a percentage. `null` unless both windows have data. */
  delta_percentage_points: number | null
}

export type FleetOverview = {
  as_of: string
  source: string
  scope: ScopeBlock
  active_shipment_count: number
  open_exception_count: number
  on_time_performance: OnTimeSummary
  freshness: string
  note: string
}

export type FleetShipment = {
  shipment_id: string
  order_reference: string | null
  current_status: string
  latest_eta_ts: string | null
  original_eta_ts: string | null
  updated_at: string | null
  driver_id: string
  driver_name: string
  facility_id: string
  facility_name: string
  facility_city: string | null
  promise_state: LivePromiseState | null
  /** Which table named it (issue #85). `dock_occupancy_hold` is the only value that comes with an
   *  `hold_expires_at`, and it is the only one that draws the HELD chip's countdown. */
  promise_state_source: PromiseStateSource | null
  /** `dock_occupancy.occupancy_id` as text. Present only on a held row. */
  hold_id: string | null
  /** The hold's server-side deadline. **The countdown's only legitimate source** — a client that
   *  derived `now + 90s` would be inventing a deadline the server never asserted. Null off a hold.
   *
   *  ⚠ Present only while the server's `TWO_PHASE_HOLD_ENABLED` is on: with it off,
   *  `_LEGACY_PROMISE_STATE_SQL` projects `appointment_status AS promise_state` and no hold columns
   *  at all, so these three fields are simply absent from the payload rather than null. Typed
   *  optional-by-null and read defensively for that reason. */
  hold_expires_at: string | null
  slot_start_ts: string | null
  slot_end_ts: string | null
  dock_code: string | null
  has_open_exception: boolean
}

/** Server-decided, and the client must not second-guess it: an empty array alone cannot tell
 *  "caught up" from "nothing yet" from "no match", and U74 makes those three different screens. */
export type EmptyReason = 'NONE_RIGHT_NOW' | 'NONE_YET' | 'NO_MATCH_FOR_FILTER'

export type FleetShipmentList = {
  as_of: string
  source: string
  scope: ScopeBlock
  status_filter: string | null
  items: FleetShipment[]
  empty_reason: EmptyReason | null
  freshness: string
  note: string
}

export type ShipmentDetailRecord = {
  shipment_id: string
  order_reference: string | null
  carrier_id: string
  driver_id: string
  origin_name: string | null
  origin_city: string | null
  customer_name: string | null
  product_category: string | null
  load_weight_kg: number | null
  pallet_count: number | null
  required_dock_type: string | null
  temperature_control_required: number | boolean | null
  priority_code: string | null
  planned_departure_ts: string | null
  actual_departure_ts: string | null
  original_eta_ts: string | null
  latest_eta_ts: string | null
  expected_unload_min: number | null
  current_status: string
  created_at: string | null
  updated_at: string | null
  driver_name: string
  registration_number: string | null
  vehicle_type_code: string | null
  facility_id: string
  facility_name: string
  facility_city: string | null
  appointment_id: string | null
  promise_state: LivePromiseState | null
  /** Which table named it (issue #85). `dock_occupancy_hold` is the only value that comes with an
   *  `hold_expires_at`, and it is the only one that draws the HELD chip's countdown. */
  promise_state_source: PromiseStateSource | null
  /** `dock_occupancy.occupancy_id` as text. Present only on a held row. */
  hold_id: string | null
  /** The hold's server-side deadline. **The countdown's only legitimate source** — a client that
   *  derived `now + 90s` would be inventing a deadline the server never asserted. Null off a hold.
   *
   *  ⚠ Present only while the server's `TWO_PHASE_HOLD_ENABLED` is on: with it off,
   *  `_LEGACY_PROMISE_STATE_SQL` projects `appointment_status AS promise_state` and no hold columns
   *  at all, so these three fields are simply absent from the payload rather than null. Typed
   *  optional-by-null and read defensively for that reason. */
  hold_expires_at: string | null
  slot_start_ts: string | null
  slot_end_ts: string | null
  dock_code: string | null
  booked_at: string | null
  confirmed_at: string | null
}

/** `list_shipment_history`'s column allowlist — outcomes only. There is deliberately no free-text
 *  field here (`components.md` §4: "History never surfaces another party's internal-only
 *  content"), which is enforced at the repository, not by a redaction pass on the client. */
export type ShipmentHistoryEntry = {
  event_type:
    | 'ETA_UPDATE'
    | 'APPOINTMENT_BOOKED'
    | 'APPOINTMENT_CONFIRMED'
    | 'APPOINTMENT_CANCELLED'
    | 'EXCEPTION_REPORTED'
    | 'GATE_IN'
    | 'DOCK_IN'
    | 'GATE_OUT'
  occurred_at: string
  detail_code: string | null
  reason_code: string | null
}

export type ShipmentDetail = {
  as_of: string
  source: string
  scope: ScopeBlock
  shipment: ShipmentDetailRecord
  history: ShipmentHistoryEntry[]
  freshness: string
  note: string
}

export type FleetExceptionItem = {
  source: 'DRIVER_EXCEPTION' | 'ESCALATION'
  reference_id: string
  shipment_id: string
  driver_name: string | null
  reason_code: string
  status: string
  occurred_at: string
}

export type FleetExceptionList = {
  as_of: string
  source: string
  scope: ScopeBlock
  items: FleetExceptionItem[]
  freshness: string
  note: string
}

export type OnTimePoint = {
  day: string
  arrivals: number
  /** Never `null` in practice — the series only contains days that had at least one arrival, and
   *  days with none are ABSENT rather than zero-filled, so a quiet day cannot draw a false
   *  trough (`repositories/carrier.get_on_time_daily_series`). Typed nullable anyway. */
  percent: number | null
}

export type OnTimePerformance = {
  as_of: string
  source: string
  scope: ScopeBlock
  window: string
  window_start: string
  window_end: string
  percent: number | null
  arrivals: number
  series: OnTimePoint[]
  freshness: string
  note: string
}

/** The one status filter the design offers that is not an `appointment_status`. */
export const HAS_OPEN_EXCEPTION = 'HAS_OPEN_EXCEPTION'
