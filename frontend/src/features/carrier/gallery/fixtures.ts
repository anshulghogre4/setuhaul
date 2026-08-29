import type {
  FleetExceptionList,
  FleetOverview,
  FleetShipment,
  FleetShipmentList,
  LivePromiseState,
  OnTimePerformance,
  ShipmentDetail,
} from '../lib/types'
import type { FleetDashboardState } from '../lib/use-fleet-dashboard'

/**
 * Fixtures for `/carrier/_states` ONLY. **Never imported by an application route** — `lib/api.ts`
 * is what the live surface uses, and it calls the real endpoints.
 *
 * Every string below is copied from `05-carrier-portal/mockup.html` or `stitch-prompts.md`,
 * which are the one place these values are authorised. Operational data is not something to make
 * up.
 *
 * Timestamps are fixed rather than relative to `Date.now()`, so two runs of the gallery produce
 * the same plates and a screenshot diff means a real change.
 */

const AS_OF = '2026-08-20T04:11:00+00:00' // 09:41 IST — the mockup's own stale-notice timestamp

function scope() {
  return { carrier_id: 'CAR001', read_only: true }
}

const NOTE = 'Own-carrier data only.'

export const OVERVIEW: FleetOverview = {
  as_of: AS_OF,
  source: 'postgresql',
  scope: scope(),
  active_shipment_count: 18,
  open_exception_count: 3,
  on_time_performance: {
    window: '30d',
    percent: 91,
    arrivals: 212,
    previous_percent: 89,
    previous_arrivals: 198,
    delta_percentage_points: 2,
  },
  freshness: 'live',
  note: NOTE,
}

/** Frame A of `stitch-prompts.md` §6 — an established carrier currently at zero. Real zeroes,
 *  and the on-time figure and its history intact. */
export const OVERVIEW_CAUGHT_UP: FleetOverview = {
  ...OVERVIEW,
  active_shipment_count: 0,
  open_exception_count: 0,
  on_time_performance: {
    window: '30d',
    percent: 94,
    arrivals: 180,
    previous_percent: 94,
    previous_arrivals: 175,
    delta_percentage_points: 0,
  },
}

/** Frame B — a brand-new carrier. `percent: null` is what `carrier_reads._percent` genuinely
 *  returns with no arrivals, and it renders as `—`, never `0%`. */
export const OVERVIEW_NOTHING_YET: FleetOverview = {
  ...OVERVIEW,
  active_shipment_count: 0,
  open_exception_count: 0,
  on_time_performance: {
    window: '30d',
    percent: null,
    arrivals: 0,
    previous_percent: null,
    previous_arrivals: 0,
    delta_percentage_points: null,
  },
}

function series(end: number): OnTimePerformance['series'] {
  // 30 daily points, one per day, ending at `end`. Shape only — the tile's headline carries the
  // value, which is the whole argument for a sparkline having no axis.
  const shape = [
    88, 89, 87, 90, 89, 91, 90, 88, 91, 92, 90, 93, 91, 92, 94, 92, 93, 91, 94, 93, 95, 94, 92, 95,
    94, 96, 95, 93, 95,
  ]
  const points = [...shape, end]
  const start = Date.UTC(2026, 6, 22)
  return points.map((percent, i) => ({
    day: new Date(start + i * 86_400_000).toISOString(),
    arrivals: 6 + (i % 4),
    percent,
  }))
}

export const PERFORMANCE: OnTimePerformance = {
  as_of: AS_OF,
  source: 'postgresql',
  scope: scope(),
  window: '30d',
  window_start: new Date(Date.UTC(2026, 6, 22)).toISOString(),
  window_end: new Date(Date.UTC(2026, 7, 20)).toISOString(),
  percent: 91,
  arrivals: 212,
  series: series(91),
  freshness: 'live',
  note: NOTE,
}

export const PERFORMANCE_CAUGHT_UP: OnTimePerformance = {
  ...PERFORMANCE,
  percent: 94,
  series: series(94),
}

function shipment(partial: Partial<FleetShipment> & { shipment_id: string }): FleetShipment {
  return {
    order_reference: null,
    current_status: 'IN_TRANSIT',
    latest_eta_ts: null,
    original_eta_ts: null,
    updated_at: AS_OF,
    driver_id: 'DRV000',
    driver_name: 'Ravi K.',
    facility_id: 'FAC-JAI-01',
    facility_name: 'Jaipur',
    facility_city: 'Jaipur',
    promise_state: null,
    slot_start_ts: null,
    slot_end_ts: null,
    dock_code: null,
    has_open_exception: false,
    ...partial,
  }
}

export const SHIPMENTS: FleetShipment[] = [
  shipment({
    shipment_id: 'SHP1015',
    driver_name: 'Ravi K.',
    facility_name: 'Jaipur',
    dock_code: 'D5',
    promise_state: 'PENDING_CONFIRMATION',
  }),
  shipment({
    shipment_id: 'SHP1009',
    driver_name: 'Amit S.',
    facility_name: 'Gurugram',
    dock_code: 'D2',
    promise_state: 'CONFIRMED',
  }),
  shipment({
    shipment_id: 'SHP1013',
    driver_name: 'Neha P.',
    facility_name: 'Kota',
    has_open_exception: true,
  }),
  // A chip and an exception marker co-occurring — normal, not a bug (`edge-cases.md` #3).
  shipment({
    shipment_id: 'SHP1021',
    driver_name: 'Priya M.',
    facility_name: 'Jaipur',
    dock_code: 'D2',
    promise_state: 'PENDING_CONFIRMATION',
    has_open_exception: true,
  }),
  // Both truncation rules, and the null-promise-state row. **The mockup renders this row with a
  // `SHOWN` chip; live data cannot produce one** — a shipment with no current appointment
  // returns `promise_state: null`, which is Fork A's open question. Rendered here exactly as the
  // live surface renders it, so the gallery shows the truth rather than the illustration.
  shipment({
    shipment_id: 'SH-2026-0819-0041217',
    driver_name: 'Sunil Thackeray',
    facility_name: 'Gurugram Cross-Dock Terminal 2',
  }),
]

export function shipmentList(
  items: FleetShipment[],
  empty: FleetShipmentList['empty_reason'] = null,
  statusFilter: string | null = null,
): FleetShipmentList {
  return {
    as_of: AS_OF,
    source: 'postgresql',
    scope: scope(),
    status_filter: statusFilter,
    items,
    empty_reason: empty,
    freshness: 'live',
    note: NOTE,
  }
}

/** All three authorised clauses, one per reason family (`stitch-prompts.md` §4). */
export const EXCEPTIONS: FleetExceptionList = {
  as_of: AS_OF,
  source: 'postgresql',
  scope: scope(),
  items: [
    {
      source: 'ESCALATION',
      reference_id: 'ESC-0001',
      shipment_id: 'SHP1013',
      driver_name: 'Neha P.',
      reason_code: 'NO_FEASIBLE_SLOT',
      status: 'OPEN',
      occurred_at: '2026-08-20T03:42:00+00:00', // 09:12 IST
    },
    {
      source: 'ESCALATION',
      reference_id: 'ESC-0002',
      shipment_id: 'SHP1015',
      driver_name: 'Ravi K.',
      reason_code: 'PENDING_EXPIRED_UNACTIONED',
      status: 'OPEN',
      occurred_at: '2026-08-20T06:27:00+00:00', // 11:57 IST
    },
    {
      source: 'DRIVER_EXCEPTION',
      reference_id: 'EXC-0003',
      shipment_id: 'SHP1021',
      driver_name: 'Priya M.',
      reason_code: 'DELAY',
      status: 'OPEN',
      occurred_at: '2026-08-20T02:50:00+00:00', // 08:20 IST
    },
  ],
  freshness: 'live',
  note: NOTE,
}

export const EXCEPTIONS_EMPTY: FleetExceptionList = { ...EXCEPTIONS, items: [] }

function detail(
  partial: Partial<ShipmentDetail['shipment']> & { shipment_id: string },
  history: ShipmentDetail['history'] = [],
): ShipmentDetail {
  return {
    as_of: AS_OF,
    source: 'postgresql',
    scope: scope(),
    shipment: {
      order_reference: null,
      carrier_id: 'CAR001',
      driver_id: 'DRV000',
      origin_name: null,
      origin_city: null,
      customer_name: null,
      product_category: null,
      load_weight_kg: null,
      pallet_count: null,
      required_dock_type: null,
      temperature_control_required: null,
      priority_code: null,
      planned_departure_ts: null,
      actual_departure_ts: null,
      original_eta_ts: null,
      latest_eta_ts: null,
      expected_unload_min: null,
      current_status: 'IN_TRANSIT',
      created_at: null,
      updated_at: AS_OF,
      driver_name: 'Ravi K.',
      registration_number: null,
      vehicle_type_code: null,
      facility_id: 'FAC-JAI-01',
      facility_name: 'Jaipur',
      facility_city: 'Jaipur',
      appointment_id: null,
      promise_state: null,
      slot_start_ts: null,
      slot_end_ts: null,
      dock_code: null,
      booked_at: null,
      confirmed_at: null,
      ...partial,
    },
    history,
    freshness: 'live',
    note: NOTE,
  }
}

const SLOT_START = '2026-08-20T07:30:00+00:00' // 13:00 IST
const SLOT_END = '2026-08-20T08:45:00+00:00' // 14:15 IST

const HISTORY: ShipmentDetail['history'] = [
  {
    event_type: 'ETA_UPDATE',
    occurred_at: '2026-08-20T04:11:00+00:00',
    detail_code: 'DRIVER_CHAT',
    reason_code: 'TRAFFIC',
  },
  {
    event_type: 'APPOINTMENT_BOOKED',
    occurred_at: '2026-08-20T04:23:00+00:00',
    detail_code: 'PENDING_CONFIRMATION',
    reason_code: null,
  },
]

export const DETAIL_SHOWN = detail(
  {
    shipment_id: 'SHP1044',
    driver_name: 'Kiran D.',
    dock_code: 'D3',
    slot_start_ts: SLOT_START,
    slot_end_ts: SLOT_END,
    // Not a live value -- `LivePromiseState` deliberately has no SHOWN/HELD (#53). Cast so the
    // gallery can show the flag-gated variants; nothing in the app can construct this.
    promise_state: 'SHOWN' as unknown as LivePromiseState,
  },
  HISTORY,
)

export const DETAIL_HELD = detail(
  {
    shipment_id: 'SHP1015',
    dock_code: 'D5',
    slot_start_ts: SLOT_START,
    slot_end_ts: SLOT_END,
    promise_state: 'HELD' as unknown as LivePromiseState,
  },
  HISTORY,
)

export const DETAIL_PENDING = detail(
  {
    shipment_id: 'SHP1015',
    dock_code: 'D5',
    slot_start_ts: SLOT_START,
    slot_end_ts: SLOT_END,
    promise_state: 'PENDING_CONFIRMATION',
  },
  HISTORY,
)

export const DETAIL_CONFIRMED = detail(
  {
    shipment_id: 'SHP1009',
    driver_name: 'Amit S.',
    facility_name: 'Gurugram',
    dock_code: 'D2',
    slot_start_ts: SLOT_START,
    slot_end_ts: SLOT_END,
    promise_state: 'CONFIRMED',
    appointment_id: 'APT-1042',
  },
  [
    ...HISTORY,
    {
      event_type: 'APPOINTMENT_CONFIRMED',
      occurred_at: '2026-08-20T05:42:00+00:00',
      detail_code: 'CONFIRMED',
      reason_code: null,
    },
  ],
)

/** The null-promise-state detail — Fork A's undesigned case, shown as the live surface shows it. */
export const DETAIL_NO_APPOINTMENT = detail({ shipment_id: 'SHP1050', driver_name: 'Meera J.' }, [])

/** A `FleetDashboardState` shaped by hand, so full-dashboard plates can be rendered without a
 *  network. The callbacks are no-ops: the gallery is for looking at states, not driving them. */
export function dashboardState(overrides: Partial<FleetDashboardState> = {}): FleetDashboardState {
  const noop = () => {}
  return {
    overview: { data: OVERVIEW, failed: false },
    shipments: { data: shipmentList(SHIPMENTS), failed: false },
    exceptions: { data: EXCEPTIONS, failed: false },
    performance: PERFORMANCE,
    // Relative-to-now so the line reads `Last updated 2 minutes ago`, the design's own copy.
    lastUpdated: new Date(Date.now() - 2 * 60_000).toISOString(),
    staleSince: null,
    firstLoad: false,
    showLoading: false,
    stalled: false,
    statusFilter: null,
    setStatusFilter: noop,
    refresh: noop,
    retryShipments: noop,
    retryExceptions: noop,
    ...overrides,
  }
}

export const STALE_AS_OF = AS_OF
