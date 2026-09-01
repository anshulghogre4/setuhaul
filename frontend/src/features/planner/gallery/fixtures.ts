import type {
  BulkConfirmOutcome,
  DockBoard,
  FeasibleSlotOption,
  PlannerQueueRow,
} from '../lib/types'

/**
 * Fixture rows for `/planner/_states` ONLY.
 *
 * Explicitly fixture-only, and kept in its own file for the same reason `features/ops/gallery`
 * and `features/driver/gallery` do it: the live `/planner` route imports `lib/api.ts` and never
 * this file, so there is no path by which a rendered fixture could be mistaken for real
 * operational data. `AGENTS.md`: *"Never invent shipment, ETA, dock, appointment, capacity, or
 * operational data."* -- a states gallery is the one sanctioned exception, and it is fenced.
 *
 * The shapes are the real `PlannerQueueRow`, so a field the server stops sending breaks this file
 * at compile time rather than only in production.
 */

const BASE: PlannerQueueRow = {
  appointment_id: 'APT-GALLERY-0001',
  shipment_id: 'SHP1014',
  slot_id: 'SLOT-GALLERY-0001',
  appointment_status: 'PENDING_CONFIRMATION',
  booking_source: 'DRIVER_APP',
  booked_at: '2026-08-29T06:00:00+00:00',
  order_reference: 'RJ14-8821',

  driver_id: 'DRV001',
  driver_name: 'Ravi K.',
  carrier_id: 'CAR001',
  carrier_name: 'Rajasthan Roadlines',

  facility_id: 'FAC-JAI-01',
  dock_id: 'DOCK-JAI-D1',
  dock_code: 'D1',
  dock_type: 'STANDARD',
  interval_start: '2026-08-29T07:30:00+00:00',
  interval_end: '2026-08-29T08:45:00+00:00',
  interval_source: 'dock_occupancy',

  receipt: {
    priority_code: 'CRITICAL',
    lateness_minutes: 70,
    wait_after_eta_minutes: 0,
    dock_match: 'exact',
    text: 'CRITICAL · 70 min late · exact dock · 0 min wait',
  },
  displacement: { status: 'NONE', conflicts: [] },
  eta: { effective_eta_ts: '2026-08-29T07:30:00+00:00', confidence: 'MEDIUM', source: 'DRIVER' },
  latest_acceptable_ts: '2026-08-29T08:00:00+00:00',
  latest_acceptable_exception_id: null,
  latest_acceptable_breached: false,
  ttl: { deadline_ts: '2026-08-29T06:15:00+00:00', remaining_seconds: 134, expired: false, hold_used: false },
  gate: { queue_state: null, queue_position: null, gate_in_ts: null, physically_waiting: false },
  urgency: { score: 4600, priority_score: 4000, ttl_pressure: 600, waiting_bonus: 0 },
  snapshot_hash: 'f0e1d2c3b4a5968778695a4b3c2d1e0ff0e1d2c3b4a5968778695a4b3c2d1e0f',
}

/** The flagship row: CRITICAL, no displacement, exact dock -- inside the safe batch. */
export const ROW_CLEAN: PlannerQueueRow = BASE

/** Displacement + LOW ETA confidence: two of the three predicates this screen can see, failing.
 *  The displacement sentence must WRAP, never truncate (`components.md` section 1). */
export const ROW_CONFLICTED: PlannerQueueRow = {
  ...BASE,
  appointment_id: 'APT-GALLERY-0002',
  shipment_id: 'SHP1013',
  driver_name: 'Neha P.',
  carrier_name: 'GGN Logistics',
  dock_code: 'D3',
  receipt: {
    priority_code: 'NORMAL',
    lateness_minutes: 0,
    wait_after_eta_minutes: 0,
    dock_match: 'compatible',
    text: 'NORMAL · 0 min late · nearest dock · 0 min wait',
  },
  displacement: {
    status: 'CONFLICT',
    conflicts: [
      {
        conflict_type: 'INTERVAL_CONFLICT',
        claim_id: 'APT-OTHER-77',
        claim_source: 'appointments',
        appointment_id: 'APT-OTHER-77',
        shipment_id: 'SHP1009',
        order_reference: null,
        appointment_status: 'CONFIRMED',
        hold_expires_at: null,
        window_start: '2026-08-29T09:30:00+00:00',
        window_end: '2026-08-29T10:30:00+00:00',
      },
    ],
  },
  eta: { effective_eta_ts: '2026-08-29T09:30:00+00:00', confidence: 'LOW', source: 'SYSTEM' },
  latest_acceptable_breached: true,
  ttl: { deadline_ts: '2026-08-29T06:09:00+00:00', remaining_seconds: 252, expired: false, hold_used: false },
  urgency: { score: 2400, priority_score: 2000, ttl_pressure: 400, waiting_bonus: 0 },
  snapshot_hash: '11223344556677889900aabbccddeeff11223344556677889900aabbccddeeff',
}

/** No `dock_occupancy` claim, so the window was recomputed -- the row says so rather than
 *  presenting a derived interval as D1's own authoritative answer. Also has no driver limit
 *  on file, which is a different fact from a limit of "none". */
export const ROW_DERIVED: PlannerQueueRow = {
  ...BASE,
  appointment_id: 'APT-GALLERY-0003',
  shipment_id: 'SHP1021',
  driver_name: 'Amit S.',
  carrier_name: 'Kota Transport',
  dock_code: 'D2',
  interval_source: 'appointment_slot_derived',
  latest_acceptable_ts: null,
  latest_acceptable_breached: null,
  receipt: {
    priority_code: 'HIGH',
    lateness_minutes: 20,
    wait_after_eta_minutes: 5,
    dock_match: 'exact',
    text: 'HIGH · 20 min late · exact dock · 5 min wait',
  },
  ttl: { deadline_ts: '2026-08-29T06:14:00+00:00', remaining_seconds: 640, expired: false, hold_used: false },
  urgency: { score: 3200, priority_score: 3000, ttl_pressure: 200, waiting_bonus: 0 },
  snapshot_hash: 'aabbccddeeff00112233445566778899aabbccddeeff001122334455667788990',
}

/**
 * **States 7 / 14 / 15 -- a request whose one D9 extension has been spent** (issue #64).
 *
 * `ttl.hold_used` is the server's own `appointments.expires_at IS NOT NULL`, and `deadline_ts` is
 * the *extended* deadline rather than the original -- which is exactly why the row still shows a
 * running number. Everything the plate needs to prove is on this one row: the held countdown
 * treatment, and the Hold affordance disabled with its reason (the one-shot cap prevented rather
 * than handled, `edge-cases.md` #6).
 */
export const ROW_HELD: PlannerQueueRow = {
  ...BASE,
  appointment_id: 'APT-GALLERY-0005',
  shipment_id: 'SHP1027',
  driver_name: 'Sunil M.',
  carrier_name: 'Alwar Carriers',
  dock_code: 'D4',
  ttl: {
    deadline_ts: '2026-08-29T06:30:00+00:00',
    remaining_seconds: 900,
    expired: false,
    hold_used: true,
  },
}

/** One `bulk_confirm` per-id outcome, for the skipped-row plate. */
export const OUTCOME_SKIPPED: BulkConfirmOutcome = {
  appointment_id: 'APT-GALLERY-0002',
  shipment_id: 'SHP1013',
  code: 'NOT_ELIGIBLE',
  detail: 'Failed safe-batch predicates: EXACT_DOCK_MATCH, ETA_CONFIDENCE_NOT_LOW.',
  failed_predicates: ['EXACT_DOCK_MATCH', 'ETA_CONFIDENCE_NOT_LOW'],
  conflicts: [],
  snapshot_hash: null,
}

/* ==============================================================================================
 * Board at rest (states 2, 22) -- fixture only, for `/planner/_states`.
 *
 * Shaped exactly like `GET /api/v1/planner/board`'s payload (`planner_service.DockBoard`), so the
 * gallery plate exercises the SAME component the live Board tab mounts. The horizon is fixed rather
 * than `now`-relative: a plate whose bars drift with wall-clock time cannot be screenshot-diffed,
 * and the now-line's position is one of the things worth looking at.
 * ============================================================================================ */

const BOARD_START = '2026-08-29T05:30:00+00:00' // 11:00 IST
const BOARD_END = '2026-08-29T09:30:00+00:00' // 15:00 IST — the full four-hour horizon

/** Every bar treatment `components.md` section 3 can produce, on one board: CONFIRMED, PENDING,
 *  HELD (dashed), IN_PROGRESS (icon, not a new hue), plus a terminal state that must render as
 *  open space and an outage hatch. D4 is deliberately empty -- a lane with no bar still renders. */
export const BOARD: DockBoard = {
  as_of: BOARD_START,
  source: 'postgresql',
  freshness: 'live',
  facility_id: 'FAC-JAI-01',
  facility_name: 'Jaipur',
  timezone: 'Asia/Kolkata',
  horizon_start: BOARD_START,
  horizon_end: BOARD_END,
  horizon_end_reason: 'ROLLING_WINDOW',
  holds_enabled: true,
  docks: [
    { dock_id: 'D1', dock_code: 'D1', dock_type: 'STANDARD', dock_status: 'ACTIVE', supports_refrigerated: false, max_vehicle_weight_kg: 20000 },
    { dock_id: 'D2', dock_code: 'D2', dock_type: 'REEFER', dock_status: 'ACTIVE', supports_refrigerated: true, max_vehicle_weight_kg: 20000 },
    { dock_id: 'D3', dock_code: 'D3', dock_type: 'HEAVY', dock_status: 'ACTIVE', supports_refrigerated: false, max_vehicle_weight_kg: 40000 },
    { dock_id: 'D4', dock_code: 'D4', dock_type: 'STANDARD', dock_status: 'ACTIVE', supports_refrigerated: false, max_vehicle_weight_kg: 20000 },
    { dock_id: 'D5', dock_code: 'D5', dock_type: 'STANDARD', dock_status: 'MAINTENANCE', supports_refrigerated: false, max_vehicle_weight_kg: 20000 },
  ],
  bars: [
    {
      occupancy_id: '1', dock_id: 'D1', state: 'CONFIRMED', claim_source: 'appointments',
      appointment_id: 'APT-1042', shipment_id: 'SHP1009', order_reference: 'ORD-1009',
      window_start: '2026-08-29T05:45:00+00:00', window_end: '2026-08-29T07:00:00+00:00',
      hold_expires_at: null,
    },
    {
      // Starts BEFORE the horizon: a truck already unloading. The bar has to clamp to the left
      // edge rather than escape its lane -- that clamp is what `placeOnTrack` exists for.
      occupancy_id: '2', dock_id: 'D2', state: 'IN_PROGRESS', claim_source: 'appointments',
      appointment_id: 'APT-1043', shipment_id: 'SHP1015', order_reference: 'ORD-1015',
      window_start: '2026-08-29T05:00:00+00:00', window_end: '2026-08-29T06:15:00+00:00',
      hold_expires_at: null,
    },
    {
      occupancy_id: '3', dock_id: 'D2', state: 'PENDING_CONFIRMATION', claim_source: 'appointments',
      appointment_id: 'APT-1044', shipment_id: 'SHP1021', order_reference: 'ORD-1021',
      window_start: '2026-08-29T07:30:00+00:00', window_end: '2026-08-29T08:45:00+00:00',
      hold_expires_at: null,
    },
    {
      // A D2 hold: no appointment row at all, and the only bar with an `expires_at`.
      occupancy_id: '4', dock_id: 'D3', state: 'HELD', claim_source: 'dock_occupancy_hold',
      appointment_id: null, shipment_id: 'SHP1031', order_reference: 'ORD-1031',
      window_start: '2026-08-29T06:30:00+00:00', window_end: '2026-08-29T07:45:00+00:00',
      hold_expires_at: '2026-08-29T05:31:30+00:00',
    },
    {
      // Terminal. **Renders as open space, never a ghost bar** -- the mapping table returns null.
      // Kept in the fixture precisely so the plate proves the absence rather than asserting it.
      occupancy_id: '5', dock_id: 'D4', state: 'COMPLETED', claim_source: 'appointments',
      appointment_id: 'APT-1040', shipment_id: 'SHP1002', order_reference: 'ORD-1002',
      window_start: '2026-08-29T06:00:00+00:00', window_end: '2026-08-29T07:00:00+00:00',
      hold_expires_at: null,
    },
  ],
  blocks: [
    {
      dock_event_id: 'DEVT002', dock_id: 'D5', event_type: 'MAINTENANCE',
      event_start_ts: '2026-08-29T04:00:00+00:00', event_end_ts: null,
      reason: 'DEVT002 outage',
    },
  ],
}

/** The empty variant: same lanes, no bars. `stitch-prompts.md` section 8 is explicit that this is
 *  the lanes plus one line of text, never a blank panel. */
export const BOARD_EMPTY: DockBoard = { ...BOARD, bars: [], blocks: [] }

/**
 * **Issue #88's second displacement leg: a blocked dock.**
 *
 * The regression guard for a real defect. `describeDisplacement` used to map `c.shipment_id` over
 * every conflict, and a `DOCK_BLOCKED` entry carries none -- so this row rendered
 * *"Confirming this displaces undefined."* in the column section 7.3 calls "the single most
 * important field". The fixture carries **both** legs at once, because the two must render as two
 * distinct sentences rather than one merged list: one names a shipment that would be displaced,
 * the other names an outage that displaces nobody.
 *
 * Field set copied from the producing SQL (`scheduling/snapshot.py:323-327`), not invented: a
 * DOCK_BLOCKED entry has `dock_event_id` / `dock_id` / `event_type` / `reason` and nothing else.
 */
export const ROW_DOCK_BLOCKED: PlannerQueueRow = {
  ...BASE,
  appointment_id: 'APT-GALLERY-0004',
  shipment_id: 'SHP1044',
  driver_name: 'Imran S.',
  carrier_name: 'Jaipur Freight',
  dock_code: 'D5',
  displacement: {
    status: 'CONFLICT',
    conflicts: [
      {
        conflict_type: 'INTERVAL_CONFLICT',
        claim_id: 'APT-OTHER-91',
        claim_source: 'appointments',
        appointment_id: 'APT-OTHER-91',
        shipment_id: 'SHP1051',
        order_reference: null,
        appointment_status: 'CONFIRMED',
        hold_expires_at: null,
        window_start: '2026-08-29T07:00:00+00:00',
        window_end: '2026-08-29T08:00:00+00:00',
      },
      {
        conflict_type: 'DOCK_BLOCKED',
        dock_event_id: 'DEVT002',
        dock_id: 'D5',
        event_type: 'MAINTENANCE',
        reason: 'Leveller failure',
      },
    ],
  },
}

/* ==============================================================================================
 * Counter-offer board picker (U103, `screens.md` section 4) -- states 3 / 24 / 25.
 *
 * Shaped like a real `find_feasible_slots` answer for ONE shipment against `BOARD` above, chosen
 * so the plate exercises all three of the picker's renderings at once:
 *
 *   - **D1 and D2 eligible** -- two clickable intervals, one of them overlapping an existing bar's
 *     lane so the plate shows an offer drawn above occupancy rather than beside it.
 *   - **D3, D4 and D5 ineligible** -- no option lands on them, so those lanes dim. D5 additionally
 *     carries the DEVT002 outage hatch, which is the case worth looking at: an ineligible lane and
 *     a blocked lane are different facts with different encodings, and the plate proves they do
 *     not collapse into one grey.
 *   - **One option outside the horizon** (`BOARD_END` is 09:30Z; this one starts 10:15Z), which
 *     `placeOnTrack` cannot position. It must be COUNTED in the banner and DRAWN nowhere -- the
 *     boundary `lib/flags.ts::plannerBoardPickerEnabled` commits to stating rather than hiding.
 * ============================================================================================ */

export const PICKER_ROW: PlannerQueueRow = {
  ...BASE,
  appointment_id: 'APT-GALLERY-PICK',
  shipment_id: 'SHP1014',
  driver_name: 'Ravi K.',
  carrier_name: 'Rajasthan Roadlines',
}

export const PICKER_OPTIONS: FeasibleSlotOption[] = [
  {
    slot_id: 'SLOT-G1',
    facility_id: 'FAC-JAI-01',
    dock_id: 'D1',
    dock_code: 'D1',
    dock_type: 'STANDARD',
    slot_start_ts: '2026-08-29T07:15:00+00:00',
    slot_end_ts: '2026-08-29T08:00:00+00:00',
    slot_local_date: '2026-08-29',
    is_same_day: true,
    differentiator: 'Earliest available',
    ranking_explanation: [],
  },
  {
    slot_id: 'SLOT-G2',
    facility_id: 'FAC-JAI-01',
    dock_id: 'D2',
    dock_code: 'D2',
    dock_type: 'REEFER',
    slot_start_ts: '2026-08-29T06:30:00+00:00',
    slot_end_ts: '2026-08-29T07:15:00+00:00',
    slot_local_date: '2026-08-29',
    is_same_day: true,
    differentiator: '',
    ranking_explanation: [],
  },
  {
    // Beyond `BOARD_END`. Deliberately unplottable -- see the block comment above.
    slot_id: 'SLOT-G3',
    facility_id: 'FAC-JAI-01',
    dock_id: 'D1',
    dock_code: 'D1',
    dock_type: 'STANDARD',
    slot_start_ts: '2026-08-29T10:15:00+00:00',
    slot_end_ts: '2026-08-29T11:00:00+00:00',
    slot_local_date: '2026-08-29',
    is_same_day: true,
    differentiator: 'Latest available',
    ranking_explanation: [],
  },
]
