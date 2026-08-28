import { apiGet } from '@/core/http/api'
import { formatDay, formatTime } from './format'
import type { DriverThread, PriorityCode, PromiseState } from './types'

/**
 * The driver surface's real server reads, and an honest account of what the server does not have.
 *
 * ## What exists (verified against source 2026-08-27, not assumed)
 *
 * | Endpoint | Gives |
 * |---|---|
 * | `GET /api/v1/driver/context` | `driver`, `profile`, up to 20 `shipments[]`, `primary_shipment`, `current_appointment`, `latest_eta`, `facility` |
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
 * 2. **Appointment/promise state is fetched for the primary shipment only.** The other threads
 *    therefore render `promiseState: null`, which hides the chip and the state line entirely —
 *    the specified behaviour for "no active promise", and honest rather than optimistic. A
 *    thread whose promise the client cannot see must not draw a chip.
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

export type DriverContext = {
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
 * `appointments.appointment_status` -> the designed promise state.
 *
 * **Note what is NOT here: `HELD`.** `appointments_appointment_status_check` admits
 * `PENDING_CONFIRMATION / CONFIRMED / IN_PROGRESS / COMPLETED / COMPLETED / CANCELLED /
 * NO_SHOW / REJECTED / EXPIRED` and no `HELD` value at all (issue #53). So there is no server
 * status this function could map to `HELD` even if the flag were on — which is the structural
 * reason the flag exists rather than a bug it is hiding.
 *
 * `IN_PROGRESS` maps to `CONFIRMED`: from the driver's point of view an appointment being
 * unloaded is still the agreed one, and there is no fifth chip state.
 */
function toPromiseState(status: string | null): PromiseState | null {
  switch (status) {
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

export function toThreads(ctx: DriverContext): DriverThread[] {
  const facilityName = ctx.facility?.facility_name ?? null
  const primaryId = ctx.primary_shipment?.shipment_id

  return ctx.shipments.map((s) => {
    const isPrimary = s.shipment_id === primaryId
    const appt = isPrimary ? ctx.current_appointment : null
    const promiseState = appt ? toPromiseState(appt.appointment_status) : null

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
      // No `expires_at` is returned for a PENDING_CONFIRMATION appointment either -- D9's
      // fifteen-minute deadline is enforced by the M8 sweeper, not exposed on the read. So no
      // countdown is drawn rather than one being computed from `booked_at + 15min`, which would
      // be the client inventing a deadline.
      expiresAt: undefined,
      ttlMs: undefined,
      operationalLine: operationalLineFor(appt, ctx.facility?.timezone ?? undefined),
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
