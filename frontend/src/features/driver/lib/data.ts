import { apiGet } from '@/core/http/api'
import { formatDay, formatTime } from './format'
import { toHold } from './mappers'
import { TTL_MS } from './use-promise-countdown'
import type { DriverHold, DriverThread, PriorityCode, PromiseState } from './types'

/**
 * The driver surface's real server reads, and an honest account of what the server does not have.
 *
 * ## What exists (verified against source 2026-08-27, not assumed)
 *
 * | Endpoint | Gives |
 * |---|---|
 * | `GET /api/v1/driver/context` | `driver`, `profile`, up to 20 `shipments[]`, `primary_shipment`, `current_appointment`, **`current_hold` / `promise_state` / `promise_state_source`** (issue #86), `latest_eta`, `facility` |
 * | `POST /api/v1/chat/stream` | the turn (see `use-driver-turn.ts`) |
 * | `GET /api/v1/chat/history` | bounded Redis transcript restore, 24h TTL |
 *
 * ## What does not exist — recorded, not papered over
 *
 * `/driver/context`'s `shipments[]` projection is
 * `(shipment_id, order_reference, destination_facility_id, current_status, latest_eta_ts,
 * original_eta_ts, priority_code, updated_at)` — read off
 * `backend/app/repositories/drivers.py::load_driver_operational_snapshot`. Consequences, each
 * one a real gap in screen 1's card anatomy:
 *
 * 1. **No `origin_city` and no destination facility *name*.** The human descriptor
 *    ("Kota load → IndustrialHub") cannot be built for any shipment except the primary one,
 *    whose facility row *is* fetched. So: the primary thread gets a real descriptor; the others
 *    fall back to the **order reference**, which is a real fact the driver can match against
 *    their paperwork. Deliberately *not* the shipment id as a sentence subject
 *    (`voice-and-tone.md` forbids that), and deliberately not a fabricated city.
 *
 * 2. **Promise state is fetched for the primary shipment only** — and since issue #86 that
 *    promise is composed from *both* `appointments` and `dock_occupancy`, so a HELD hold now
 *    reaches this surface where it previously read as "no appointment at all". The other threads
 *    still render `promiseState: null`, which hides the chip and the state line entirely — the
 *    specified behaviour for "no active promise", and honest rather than optimistic. A thread
 *    whose promise the client cannot see must not draw a chip.
 *
 * 3. **No last-message preview anywhere.** There is no per-thread "latest message" endpoint;
 *    `/chat/history` is a single-thread restore. `lastMessagePreview` is `null` and the line is
 *    omitted (U81: a gap is a real answer).
 *
 * 4. **No unread state.** Nothing server-side tracks read position for a driver, so `unread` is
 *    always `false` rather than guessed from timestamps.
 *
 * **The clean fix is a `GET /api/v1/driver/threads` returning one row per thread with
 * descriptor + promise state + preview + unread.** That is a backend contract addition outside
 * issue #36's `area:frontend` scope, so it is filed as a follow-up rather than done here. Every
 * absence above renders as an absence; nothing renders as an invention.
 */

type RawShipment = {
  shipment_id: string
  order_reference: string | null
  destination_facility_id: string | null
  current_status: string | null
  priority_code: string | null
  updated_at: string | null
}

type RawAppointment = {
  appointment_id: string
  shipment_id: string
  appointment_status: string | null
  is_current: number | boolean | null
  slot_start_ts: string | null
  slot_end_ts: string | null
  dock_id: string | null
  updated_at: string | null
}

type RawFacility = {
  facility_id: string
  facility_name: string | null
  timezone: string | null
}

/** `holds.live_hold_for_shipment`'s row. Typed loosely here and narrowed by `mappers.toHold`,
 *  which refuses a hold with no server `expires_at` rather than rendering one without a deadline. */
type RawHold = Record<string, unknown>

export type DriverContext = {
  /** Server clock reading. Fed to `CountdownProvider` so the 90-second hold is measured against the
   *  server's time and not the phone's -- a handset three minutes fast would otherwise show a live
   *  hold as already lapsed. */
  as_of: string
  driver: {
    driver_id: string
    driver_name: string | null
    phone: string | null
    licence_number: string | null
    home_base_city: string | null
    driver_status: string | null
  } | null
  profile: { user_id: string; full_name: string | null; email: string | null } | null
  shipments: RawShipment[]
  primary_shipment: RawShipment | null
  current_appointment: RawAppointment | null
  /** Issue #86. Its own key rather than being flattened into `current_appointment`, because a hold
   *  genuinely is not one: no `appointment_id`, no `booked_at`, no D9 clock. */
  current_hold: RawHold | null
  /** The composed promise -- an active appointment outranks a live hold, a live hold outranks a
   *  terminal appointment status (`driver_reads.resolve_promise_state`). **Preferred over deriving
   *  it from `current_appointment` here**, so this client and the assistant answering in the same
   *  turn cannot disagree about the same shipment. */
  promise_state: string | null
  promise_state_source: 'appointments' | 'dock_occupancy_hold' | null
  facility: RawFacility | null
}

export async function fetchDriverContext(): Promise<DriverContext> {
  const res = await apiGet<DriverContext>('/api/v1/driver/context')
  return res.data
}

/** Statuses that take a shipment out of a driver's active workload. Mirrors
 *  `drivers.py::_INACTIVE_STATUSES` exactly — kept in step deliberately so the list and the
 *  server agree on what "active" means. */
const INACTIVE = new Set(['COMPLETED', 'CANCELLED'])

/**
 * The server's composed `promise_state` -> the designed chip state.
 *
 * **`HELD` is here now** (issues #83/#86). It does not come from
 * `appointments.appointment_status`, whose CHECK constraint has no such value and deliberately
 * never will: the server composes `promise_state` from `appointments` *and* `dock_occupancy` in
 * `driver_reads.resolve_promise_state`, and this function reads that composed value rather than
 * re-deriving one. That is what stops this surface and the assistant, answering about the same
 * shipment in the same turn, from saying two different things.
 *
 * `IN_PROGRESS` maps to `CONFIRMED`: from the driver's point of view an appointment being
 * unloaded is still the agreed one, and there is no fifth chip state.
 */
function toPromiseState(status: string | null): PromiseState | null {
  switch (status) {
    case 'HELD':
      // Behind `heldStateEnabled` at the render site, not here -- this function reports what the
      // server said; the flag decides whether the surface may draw it.
      return 'HELD'
    case 'PENDING_CONFIRMATION':
      return 'PENDING_CONFIRMATION'
    case 'CONFIRMED':
    case 'IN_PROGRESS':
      return 'CONFIRMED'
    default:
      // EXPIRED / REJECTED / CANCELLED / NO_SHOW / COMPLETED all mean "no active promise", and
      // the state line hides entirely. Rendering a terminal status as a chip would put a state
      // hue on something that is not one of the four states.
      return null
  }
}

const PRIORITIES = new Set(['CRITICAL', 'HIGH', 'NORMAL', 'LOW'])

/** The live D2 hold on the driver's primary shipment, or `null`. Refuses a hold with no server
 *  `expires_at` -- see `mappers.toHold`. */
export function currentHold(ctx: DriverContext): DriverHold | null {
  return toHold(ctx.current_hold)
}

export function toThreads(ctx: DriverContext): DriverThread[] {
  const facilityName = ctx.facility?.facility_name ?? null
  const primaryId = ctx.primary_shipment?.shipment_id
  const hold = currentHold(ctx)

  return ctx.shipments.map((s) => {
    const isPrimary = s.shipment_id === primaryId
    const appt = isPrimary ? ctx.current_appointment : null
    // The SERVER's composed promise for the primary shipment, not a status this client re-derived.
    // For every other thread there is no promise on this payload at all, so it stays null.
    const promiseState = isPrimary ? toPromiseState(ctx.promise_state) : null
    const heldHere = isPrimary && promiseState === 'HELD' ? hold : null

    return {
      // The thread id the chat endpoints use is minted server-side per conversation. Until a
      // real thread listing exists (see the header note), the shipment id is the stable key the
      // conversation route resolves against, and `/chat/stream` is called with `thread_id: null`
      // for a shipment that has no thread yet -- the server mints and returns one.
      threadId: s.shipment_id,
      shipmentId: s.shipment_id,
      descriptor: descriptorFor(s, isPrimary, facilityName),
      orderReference: s.order_reference ?? '',
      priority: PRIORITIES.has(s.priority_code ?? '') ? (s.priority_code as PriorityCode) : null,
      promiseState,
      // **HELD carries a real, server-stamped deadline** (`dock_occupancy.expires_at`, issue #86),
      // so its countdown is read rather than computed. PENDING_CONFIRMATION still carries none:
      // D9's fifteen minutes are enforced by the M8 sweeper from `booked_at` and are not exposed on
      // this read, so no countdown is drawn rather than one being derived from `booked_at + 15min`
      // -- which would be the client inventing a deadline. Two states, two different reasons, and
      // only one of them is a gap now.
      expiresAt: heldHere?.expiresAt,
      ttlMs: heldHere ? TTL_MS.HELD : undefined,
      operationalLine:
        operationalLineFor(appt, ctx.facility?.timezone ?? undefined) ??
        holdOperationalLine(heldHere, ctx.facility?.timezone ?? undefined),
      lastMessagePreview: null,
      lastActivityAt: s.updated_at ?? new Date(0).toISOString(),
      resolved: INACTIVE.has(s.current_status ?? ''),
      unread: false,
    }
  })
}

/**
 * "Kota load → IndustrialHub" needs an origin city and a facility name; `shipments[]` carries
 * neither. Only the primary shipment's facility row is fetched, so only it can have the real
 * descriptor. Everything else falls back to the order reference — a real fact on the driver's
 * own paperwork — rather than to a guessed city or to the shipment id.
 */
function descriptorFor(
  s: RawShipment,
  isPrimary: boolean,
  facilityName: string | null,
): string {
  if (isPrimary && facilityName) return `Load to ${facilityName}`
  return s.order_reference ?? s.shipment_id
}

/** Dock · dated range, always together, never a bare time (`voice-and-tone.md`).
 *  `dock_id` is a UUID, not a code — `docks.dock_code` is not on this read, so the dock is
 *  omitted rather than rendered as a UUID. Same class of gap as the descriptor. */
function operationalLineFor(
  appt: RawAppointment | null,
  timeZone?: string,
): string | null {
  if (!appt?.slot_start_ts || !appt.slot_end_ts) return null
  const day = formatDay(appt.slot_start_ts, timeZone)
  const start = formatTime(appt.slot_start_ts, timeZone)
  const end = formatTime(appt.slot_end_ts, timeZone)
  if (!day || !start || !end) return null
  return `${day} · ${start} – ${end}`
}

/**
 * The same dock · dated-range line, built from a HELD hold instead of an appointment.
 *
 * A hold has no appointment row and therefore no `slot_start_ts` on `current_appointment` — but it
 * does carry its own occupancy window and its dock *code* (`live_hold_for_shipment` joins `docks`
 * for exactly that), so this line is fully renderable and does not fall back to a UUID the way the
 * appointment path has to. Returns `null` rather than a partial line if any component is missing:
 * `voice-and-tone.md` forbids a bare time, so half a line is not an improvement on none.
 */
function holdOperationalLine(hold: DriverHold | null, timeZone?: string): string | null {
  if (!hold?.windowStart || !hold.windowEnd) return null
  const day = formatDay(hold.windowStart, timeZone)
  const start = formatTime(hold.windowStart, timeZone)
  const end = formatTime(hold.windowEnd, timeZone)
  if (!day || !start || !end) return null
  const dock = hold.dockCode ? `Dock ${hold.dockCode} · ` : ''
  return `${dock}${day} · ${start} – ${end}`
}

/**
 * Screens 3A vs 3B, and the distinction is a **server-side history check, never `count === 0`**
 * (U74).
 *
 * `shipments[]` is the driver's last 20 shipments *including* completed and cancelled ones, so
 * "any row at all" genuinely answers "has this driver ever had a load", and "no active rows"
 * answers "are they caught up". That is why the two states can be told apart honestly here — it
 * is a property of what this endpoint returns, not an inference.
 */
export function emptyKind(ctx: DriverContext): 'caught-up' | 'nothing-yet' | 'has-threads' {
  if (ctx.shipments.length === 0) return 'nothing-yet'
  const active = ctx.shipments.filter((s) => !INACTIVE.has(s.current_status ?? ''))
  return active.length === 0 ? 'caught-up' : 'has-threads'
}
