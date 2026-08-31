import type { GateEventResult, GateTruckMatch, NextAction } from '../lib/types'

/**
 * **Fixtures. Gallery only. Never imported by anything under `components/` or by the route.**
 *
 * `AGENTS.md`: "Never invent shipment, ETA, dock, appointment, capacity, or operational data." The
 * rule this file lives inside is that invented data may exist *for a verification plate a human
 * looks at*, and may never reach a surface an officer looks at. `/gate` itself renders nothing from
 * here -- the search field says plainly that lookup is not available (issue #67) rather than
 * showing one of these trucks.
 *
 * Every value is copied from `mockup.html`'s own artboards so the plates are comparable to the
 * board side by side, rather than being a second, differently-wrong set of numbers. Timestamps are
 * written as `+05:30` ISO strings for the 2026-08-04 operating day the mockup uses, because the
 * real components format through `Intl` in `Asia/Kolkata` and hardcoded display strings would test
 * nothing.
 *
 * **`next_action` is set per fixture rather than derived here**, mirroring the live contract: the
 * server computes it (`gate_yard_reads.derive_next_action`) and the kiosk renders it. Each value
 * below is the one that function would return for that row's timestamps and state -- checked
 * against its actual branches, not guessed -- so a plate showing the wrong verb is a real defect in
 * `actionFor`, not a fixture typo.
 */

const DAY = '2026-08-04'

function ist(time: string, day = DAY): string {
  return `${day}T${time}:00+05:30`
}

/** Screens 5-7, 11, 12, 14, 16, 19, 20. `SHP1015` / Ravi K. / Rajasthan Roadlines / D5. */
const RAVI_APPOINTMENT = {
  appointment_id: 'APT-FIXTURE-1015',
  appointment_status: 'CONFIRMED',
  appointment_dock_id: 'D16-DOCK-JAI-D5',
  appointment_dock_code: 'D5',
  slot_start_ts: ist('18:00'),
  slot_end_ts: ist('19:00'),
}

/** Screens 8-10, 15, 17, 18, 21, 22. `SHP1009` / Amit S. / Kota Transport / D2. */
const AMIT_APPOINTMENT = {
  appointment_id: 'APT-FIXTURE-1009',
  appointment_status: 'CONFIRMED',
  appointment_dock_id: 'D16-DOCK-JAI-D2',
  appointment_dock_code: 'D2',
  slot_start_ts: ist('14:00'),
  slot_end_ts: ist('14:45'),
}

function truck(
  base: {
    shipment_id: string
    order_reference: string
    registration_number: string
    driver_name: string
    carrier_name: string
  },
  appointment: typeof RAVI_APPOINTMENT,
  overrides: Partial<GateTruckMatch> & { next_action: NextAction | null },
): GateTruckMatch {
  return {
    ...base,
    facility_id: 'FAC-JAI-01',
    current_status: 'IN_TRANSIT',
    checkin_id: null,
    queue_state: 'NOT_QUEUED',
    queue_position: null,
    arrival_state: null,
    actual_dock_id: null,
    gate_in_ts: null,
    dock_in_ts: null,
    unload_start_ts: null,
    unload_end_ts: null,
    gate_out_ts: null,
    dwell_min: null,
    ...appointment,
    ...overrides,
  }
}

const RAVI = {
  shipment_id: 'SHP1015',
  order_reference: 'ORD-260804-015',
  registration_number: 'RJ14 GH 2211',
  driver_name: 'Ravi K.',
  carrier_name: 'Rajasthan Roadlines',
}

const AMIT = {
  shipment_id: 'SHP1009',
  order_reference: 'ORD-260804-009',
  registration_number: 'RJ09 KT 8830',
  driver_name: 'Amit S.',
  carrier_name: 'Kota Transport',
}

/** Screen 6. No check-in row yet, so `NOT_QUEUED` and no state row renders. */
export const TRUCK_NOT_QUEUED = truck(RAVI, RAVI_APPOINTMENT, { next_action: 'GATE_IN' })

/** Screen 7a. */
export const TRUCK_WAITING_LATE = truck(RAVI, RAVI_APPOINTMENT, {
  checkin_id: 'CHK-FIXTURE-1015',
  queue_state: 'WAITING_LATE',
  arrival_state: 'LATE',
  gate_in_ts: ist('18:04'),
  next_action: 'CALL_TO_DOCK',
})

/** Screen 7b. */
export const TRUCK_WAITING_EARLY = truck(RAVI, RAVI_APPOINTMENT, {
  checkin_id: 'CHK-FIXTURE-1015',
  queue_state: 'WAITING_EARLY',
  arrival_state: 'EARLY',
  gate_in_ts: ist('17:52'),
  next_action: 'CALL_TO_DOCK',
})

/** Screen 8. */
export const TRUCK_DOCK_UNAVAILABLE = truck(AMIT, AMIT_APPOINTMENT, {
  checkin_id: 'CHK-FIXTURE-1009',
  queue_state: 'WAITING_DOCK_UNAVAILABLE',
  arrival_state: 'ON_TIME',
  gate_in_ts: ist('13:58'),
  next_action: 'CALL_TO_DOCK',
})

/** Screen 9. */
export const TRUCK_CALLED_TO_DOCK = truck(AMIT, AMIT_APPOINTMENT, {
  checkin_id: 'CHK-FIXTURE-1009',
  queue_state: 'CALLED_TO_DOCK',
  arrival_state: 'ON_TIME',
  gate_in_ts: ist('13:58'),
  next_action: 'DOCK_IN',
})

/** Screen 10a. */
export const TRUCK_IN_DOCK = truck(AMIT, AMIT_APPOINTMENT, {
  checkin_id: 'CHK-FIXTURE-1009',
  queue_state: 'IN_DOCK',
  arrival_state: 'ON_TIME',
  gate_in_ts: ist('13:58'),
  dock_in_ts: ist('14:09'),
  actual_dock_id: AMIT_APPOINTMENT.appointment_dock_id,
  next_action: 'START_UNLOAD',
})

/** Screen 10b / 22b. */
export const TRUCK_UNLOADING = truck(AMIT, AMIT_APPOINTMENT, {
  checkin_id: 'CHK-FIXTURE-1009',
  queue_state: 'IN_DOCK',
  arrival_state: 'ON_TIME',
  gate_in_ts: ist('13:58'),
  dock_in_ts: ist('14:09'),
  unload_start_ts: ist('14:12'),
  actual_dock_id: AMIT_APPOINTMENT.appointment_dock_id,
  next_action: 'END_UNLOAD',
})

/** Screen 11. Unload has ended (`queue_state` COMPLETED) but the truck has not left. */
export const TRUCK_COMPLETED = truck(RAVI, RAVI_APPOINTMENT, {
  checkin_id: 'CHK-FIXTURE-1015',
  queue_state: 'COMPLETED',
  arrival_state: 'EARLY',
  gate_in_ts: ist('17:52'),
  dock_in_ts: ist('18:20'),
  unload_start_ts: ist('18:25'),
  unload_end_ts: ist('19:10'),
  actual_dock_id: RAVI_APPOINTMENT.appointment_dock_id,
  next_action: 'GATE_OUT',
})

/** Screen 12. Terminal -- `derive_next_action` returns null on a non-null `gate_out_ts` before it
 *  looks at anything else, so no button renders at all. 17:52 to 19:14 is 82 min = "1h 22m". */
export const TRUCK_GATED_OUT = truck(RAVI, RAVI_APPOINTMENT, {
  checkin_id: 'CHK-FIXTURE-1015',
  queue_state: 'COMPLETED',
  arrival_state: 'EARLY',
  gate_in_ts: ist('17:52'),
  gate_out_ts: ist('19:14'),
  dwell_min: 82,
  next_action: null,
})

/** Screen 5: two trips sharing plate `RJ14 GH 2211`. */
export const DISAMBIGUATION_MATCHES: GateTruckMatch[] = [
  TRUCK_WAITING_LATE,
  truck(
    { ...RAVI, shipment_id: 'SHP1021', order_reference: 'ORD-260805-021' },
    {
      appointment_id: 'APT-FIXTURE-1021',
      appointment_status: 'CONFIRMED',
      appointment_dock_id: 'D16-DOCK-JAI-D2',
      appointment_dock_code: 'D2',
      slot_start_ts: ist('06:00', '2026-08-05'),
      slot_end_ts: ist('07:15', '2026-08-05'),
    },
    { next_action: 'GATE_IN' },
  ),
]

function result(
  overrides: Partial<GateEventResult> & Pick<GateEventResult, 'code'>,
): GateEventResult {
  return {
    as_of: ist('14:06'),
    source: 'postgresql',
    freshness: 'live',
    shipment_id: 'SHP1009',
    facility_id: 'FAC-JAI-01',
    checkin_id: 'CHK-FIXTURE-1009',
    queue_state: null,
    queue_position: null,
    arrival_state: null,
    actual_dock_id: null,
    appointment_id: null,
    gate_in_ts: null,
    minutes_from_slot_start: null,
    early_limit_min: null,
    beyond_early_limit: null,
    expected_dock_id: null,
    occupying_shipment_id: null,
    phase: null,
    unload_start_ts: null,
    unload_end_ts: null,
    actual_unload_min: null,
    expected_unload_min: null,
    overrun_min: null,
    gate_out_ts: null,
    dwell_min: null,
    idempotency_key: null,
    idempotent_replay: false,
    // Issue #68. `'Ramesh K.'` and not `null`, so the gallery renders the shape the live surface
    // now produces -- a fixture that defaulted to null would quietly stop exercising the attributed
    // case the moment somebody added a screen that reads it.
    officer_name: 'Ramesh K.',
    ...overrides,
  }
}

/** Screen 14. */
export const RESULT_GATE_IN = result({
  code: 'GATE_IN_RECORDED',
  shipment_id: 'SHP1015',
  gate_in_ts: ist('18:04'),
  arrival_state: 'ON_TIME',
  queue_state: 'WAITING_LATE',
})

/** Screen 15a. */
export const RESULT_QUEUE_UPDATED = result({
  code: 'QUEUE_UPDATED',
  as_of: ist('14:06'),
  queue_state: 'CALLED_TO_DOCK',
})

/** Screen 15b. */
export const RESULT_DOCK_IN = result({
  code: 'DOCK_IN_RECORDED',
  as_of: ist('14:09'),
  queue_state: 'IN_DOCK',
  actual_dock_id: AMIT_APPOINTMENT.appointment_dock_id,
  expected_dock_id: AMIT_APPOINTMENT.appointment_dock_id,
})

/** Screen 15c. */
export const RESULT_UNLOAD_START = result({
  code: 'RECORDED',
  phase: 'START',
  unload_start_ts: ist('14:12'),
  queue_state: 'IN_DOCK',
})

/** Screen 16. */
export const RESULT_GATE_OUT = result({
  code: 'COMPLETED',
  shipment_id: 'SHP1015',
  gate_out_ts: ist('19:14'),
  dwell_min: 82,
  queue_state: 'COMPLETED',
})

/**
 * Screen 17. `expected_dock_id` differs from `actual_dock_id`, which is the only way this code can
 * arise -- and, per `outcome-screen.tsx`'s own note, is only reachable when the appointment's dock
 * changed server-side between the card rendering and the tap landing, because the kiosk always
 * submits the dock it read off the card. The confirmed dock therefore has no code available in the
 * response and renders as its raw id, which is exactly what this plate exists to make visible.
 */
export const RESULT_DOCK_MISMATCH = result({
  code: 'DOCK_MISMATCH',
  actual_dock_id: AMIT_APPOINTMENT.appointment_dock_id,
  expected_dock_id: 'D16-DOCK-JAI-D4',
  queue_state: 'IN_DOCK',
})

/** Screen 18. 14:12 to 15:34 is 82 minutes against an expected 60 -- 22 over, the mockup's own
 *  numbers. */
export const RESULT_UNLOAD_OVERRUN = result({
  code: 'RECORDED',
  phase: 'END',
  unload_start_ts: ist('14:12'),
  unload_end_ts: ist('15:34'),
  actual_unload_min: 82,
  expected_unload_min: 60,
  overrun_min: 22,
  queue_state: 'COMPLETED',
})

/** The unload END that finished on time -- no artboard exists for it (see `outcome-screen.tsx`).
 *  `overrun_min` is signed, not clamped, so an early finish is genuinely negative. */
export const RESULT_UNLOAD_ON_TIME = result({
  code: 'RECORDED',
  phase: 'END',
  unload_start_ts: ist('14:12'),
  unload_end_ts: ist('15:05'),
  actual_unload_min: 53,
  expected_unload_min: 60,
  overrun_min: -7,
  queue_state: 'COMPLETED',
})

/** Screen 19. */
export const RESULT_ALREADY_CHECKED_IN = result({
  code: 'ALREADY_CHECKED_IN',
  shipment_id: 'SHP1015',
  gate_in_ts: ist('17:52'),
  arrival_state: 'EARLY',
  queue_state: 'WAITING_EARLY',
})

/** Screen 20. */
export const RESULT_NO_APPOINTMENT = result({
  code: 'NO_ACTIVE_APPOINTMENT',
  shipment_id: 'SHP1015',
})

/** Screen 21. */
export const RESULT_DOCK_OCCUPIED = result({
  code: 'DOCK_OCCUPIED',
  expected_dock_id: AMIT_APPOINTMENT.appointment_dock_id,
  occupying_shipment_id: 'SHP1030',
  queue_state: 'WAITING_DOCK_UNAVAILABLE',
})

/** Screen 22a. */
export const RESULT_INVALID_TRANSITION = result({
  code: 'INVALID_TRANSITION',
  queue_state: 'IN_DOCK',
})

/** No artboard: a real code the design files never name (see `outcome-screen.tsx`). */
export const RESULT_ALREADY_GATED_OUT = result({
  code: 'ALREADY_GATED_OUT',
  shipment_id: 'SHP1015',
  gate_out_ts: ist('19:14'),
  dwell_min: 82,
  queue_state: 'COMPLETED',
})
