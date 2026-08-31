/**
 * Gate/yard kiosk -- types.
 *
 * Mirrors `backend/app/services/gate_yard_service.py::GateEventResult` field-for-field (E5.4,
 * issue #39). This is the one response shape all five section 7.5.2 write tools share --
 * `record_gate_in`, `update_queue_state`, `record_dock_in`, `record_unload_start_end`,
 * `record_gate_out` -- each populates a different subset of the optional fields depending on
 * `code`. Nothing here is invented: every field is read off the Pydantic model directly,
 * `gate_yard_service.py:106-142`.
 */

export type GateOutcomeCode =
  // record_gate_in
  | 'GATE_IN_RECORDED'
  | 'ALREADY_CHECKED_IN'
  | 'NO_ACTIVE_APPOINTMENT'
  // update_queue_state
  | 'QUEUE_UPDATED'
  | 'INVALID_TRANSITION'
  // record_dock_in
  | 'DOCK_IN_RECORDED'
  | 'DOCK_MISMATCH'
  | 'DOCK_OCCUPIED'
  // record_unload_start_end
  | 'RECORDED'
  // record_gate_out
  | 'COMPLETED'
  | 'ALREADY_GATED_OUT'

export type QueueState =
  | 'NOT_QUEUED'
  | 'WAITING_EARLY'
  | 'WAITING_LATE'
  | 'WAITING_DOCK_UNAVAILABLE'
  | 'CALLED_TO_DOCK'
  | 'IN_DOCK'
  | 'COMPLETED'

export type ArrivalState = 'EARLY' | 'ON_TIME' | 'LATE'

/**
 * Not a `GateEventResult` code -- listed here so nobody adds it to `GateOutcomeCode` later.
 *
 * `NOT_CHECKED_IN` is raised as an `AppError(409)` by `record_dock_in`, `record_unload_start_end`
 * and `record_gate_out` (`gate_yard_service.py:626, 728, 822`), so it arrives as a rejected
 * envelope (`success: false`) and is thrown by `apiPost`, never returned as a result body. It has
 * no outcome screen in `stitch-prompts.md` because U110's state -> action table can never offer an
 * action that produces it: every one of those three tools is only ever reached from a
 * `queue_state` that already implies a gate-in.
 */
export type NotAResultCode = 'NOT_CHECKED_IN'

/** `gate_yard_service.py::GateEventResult` -- every field it can return, across all five tools. */
export type GateEventResult = {
  as_of: string
  source: string
  freshness: string
  code: GateOutcomeCode
  shipment_id: string
  facility_id: string
  checkin_id: string | null
  queue_state: QueueState | string | null
  queue_position: number | null
  arrival_state: ArrivalState | string | null
  actual_dock_id: string | null
  appointment_id: string | null
  // record_gate_in
  gate_in_ts: string | null
  minutes_from_slot_start: number | null
  early_limit_min: number | null
  beyond_early_limit: boolean | null
  // record_dock_in
  expected_dock_id: string | null
  occupying_shipment_id: string | null
  // record_unload_start_end
  phase: 'START' | 'END' | null
  unload_start_ts: string | null
  unload_end_ts: string | null
  actual_unload_min: number | null
  expected_unload_min: number | null
  overrun_min: number | null
  // record_gate_out
  gate_out_ts: string | null
  dwell_min: number | null
  idempotency_key: string | null
  idempotent_replay: boolean
  /**
   * U111's shift label as the **server** normalised and stored it (issue #68), not as the kiosk
   * sent it: trimmed, whitespace-collapsed, control characters sanitised, truncated. Echoed so a
   * difference between typed and stored is visible rather than silent.
   *
   * `null` means no officer was attributed to this event -- a legitimate, recorded state, not an
   * error. On an idempotent replay this is the *original* caller's label, since that is the one
   * actually on the stored event.
   *
   * **Never render this as proof of who acted.** Nothing verifies it.
   */
  officer_name: string | null
}

/**
 * The one valid action for a truck, **derived server-side** and returned by the Flow 1 search.
 *
 * `gate_yard_reads.NEXT_ACTIONS`, copied verbatim. `null` means there is no next action at all --
 * `edge-cases.md` #6's terminal truck (screen 12), where no button renders.
 *
 * **The kiosk does not compute this, deliberately.** `derive_next_action`'s own docstring is
 * explicit about why: "a kiosk that derived its own next action would be a second copy of
 * `QUEUE_TRANSITIONS` free to drift from the one the writes actually enforce," and section 7.5.2
 * states the state machine is enforced server-side, not by the kiosk. An earlier draft of this
 * surface did derive it client-side from `queue_state` alone, and that draft had a real defect the
 * server version does not: it would have offered "Call to dock" to a truck sitting in a `WAITING_*`
 * state with a null `gate_in_ts`, which every write except `record_gate_in` refuses outright with
 * `NOT_CHECKED_IN`. `derive_next_action` checks `gate_in_ts` *before* the state for exactly that
 * reason. The kiosk still owns the label and the icon -- that is rendering, not policy.
 */
export type NextAction =
  | 'GATE_IN'
  | 'CALL_TO_DOCK'
  | 'DOCK_IN'
  | 'START_UNLOAD'
  | 'END_UNLOAD'
  | 'GATE_OUT'

/**
 * One truck the officer could be standing in front of.
 *
 * Mirrors `backend/app/services/gate_yard_reads.py::GateTruckMatch` field-for-field -- the Flow 1
 * read that closes `GY-G1` (issue #67). Read off the shipped Pydantic model, not designed here.
 *
 * It carries everything `components.md` section 3's truck-identity card renders **and** both
 * arguments the follow-on write needs (`shipment_id` for all five tools, `appointment_dock_id` for
 * `record_dock_in`, which Flow 5 requires the kiosk to read off the appointment rather than let the
 * officer choose), so Flow 1 -> Flow 2 -> Flow 3..7 never needs a second round trip.
 *
 * Appointment fields are **flat, not nested**, matching the server model exactly. An earlier draft
 * of this file nested them into an `appointment` object; that was a guess made before the endpoint
 * existed, and translating between two shapes at the client boundary buys nothing but a place for
 * them to disagree.
 */
export type GateTruckMatch = {
  shipment_id: string
  order_reference: string
  facility_id: string
  current_status: string
  registration_number: string
  driver_name: string
  carrier_name: string

  checkin_id: string | null
  /** Never null -- the server defaults a missing `facility_checkins` row to `NOT_QUEUED`. */
  queue_state: QueueState | string
  queue_position: number | null
  arrival_state: ArrivalState | string | null
  actual_dock_id: string | null
  gate_in_ts: string | null
  dock_in_ts: string | null
  unload_start_ts: string | null
  unload_end_ts: string | null
  gate_out_ts: string | null
  /** Set only once the cycle is terminal. The same subtraction `record_gate_out` returns, computed
   *  server-side so `edge-cases.md` #6's "dwell 1h 22m" does not need the kiosk to redo date
   *  arithmetic the server already owns. */
  dwell_min: number | null

  appointment_id: string | null
  appointment_status: string | null
  /** The opaque id Flow 5 submits to `record_dock_in`. */
  appointment_dock_id: string | null
  /** What an officer actually reads. `D5`, not `D16-DOCK-JAI-D5`. */
  appointment_dock_code: string | null
  slot_start_ts: string | null
  slot_end_ts: string | null

  next_action: NextAction | null
}

/** `gate_yard_reads.py::GateTruckSearchResult`. `NO_MATCH` is a 200 with an empty list, not a 404:
 *  a search that found nothing is an answer, not a failure, and Flow 1.3 needs the officer to stay
 *  on the search screen with the field still focused. */
export type GateTruckSearchResult = {
  as_of: string
  source: string
  freshness: string
  code: 'MATCH' | 'NO_MATCH' | 'MULTIPLE_MATCHES'
  query: string
  /** The scope actually searched, echoed back. Derived from the verified token (M15), never read
   *  from the request -- there is no `facility_id` parameter to send. */
  facility_id: string | null
  match_count: number
  /** True when more than `MAX_MATCHES` rows existed. The server fetches one extra row so this is a
   *  real overflow signal rather than a guess from a full page. */
  truncated: boolean
  matches: GateTruckMatch[]
}
