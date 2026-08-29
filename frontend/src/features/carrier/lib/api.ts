import { getSession } from '@/core/auth/supabase'
import type {
  FleetExceptionList,
  FleetOverview,
  FleetShipmentList,
  OnTimePerformance,
  ShipmentDetail,
} from './types'

/**
 * The five §7.5.6 reads, called for real — same pattern E5.1/E5.2/E5.3 used, not fixtures.
 * `gallery/fixtures.ts` is the separate, explicitly-fixture-only file behind `/carrier/_states`.
 *
 * ## Why this file has its own fetch instead of `core/http/api.ts`'s `apiGet`
 *
 * **One reason only, and it is a real requirement rather than a preference**: `apiGet` throws
 * `new Error(detail)`, which discards the envelope's `errors[0].code`. This surface has exactly
 * one screen whose entire correctness depends on that code —
 * `05-carrier-portal/edge-cases.md` #1's out-of-scope refusal, which must render its own
 * designed screen for a `FORBIDDEN` and the ordinary "couldn't load" treatment for anything
 * else. Distinguishing those by matching on an English message string would make a
 * security-relevant screen depend on copy nobody has promised to keep stable.
 *
 * The auth-header logic below is otherwise identical to `apiGet`'s. That duplication is
 * deliberate and reported rather than fixed in place: `core/http/**` is shared infrastructure
 * two other surface builds are reading concurrently, so the proper fix — teaching `apiGet` to
 * throw a code-bearing error — belongs to whoever owns that file next, not to this epic.
 */

const apiBase = (import.meta.env.VITE_API_BASE_URL as string | undefined) || 'http://localhost:8000'

type ErrorDetail = { code: string; detail: string; field?: string }

type Envelope<T> = {
  success: boolean
  message: string
  data: T
  timestamp: string
  request_id: string
  errors?: ErrorDetail[]
}

/** Carries the envelope's own `code`, which is what tells a scope refusal from a network fault. */
export class CarrierApiError extends Error {
  readonly code: string
  readonly status: number

  constructor(message: string, code: string, status: number) {
    super(message)
    this.name = 'CarrierApiError'
    this.code = code
    this.status = status
  }
}

/** True for the refusal `assert_shipment_in_carrier_fleet` raises — identical for a shipment that
 *  does not exist and one belonging to another carrier, by design (`edge-cases.md` #1). The
 *  client must never try to tell those apart, and with this envelope it structurally cannot. */
export function isOutOfScope(err: unknown): boolean {
  return (
    err instanceof CarrierApiError && err.status === 403 &&
    (err.code === 'FORBIDDEN' || err.code === 'CARRIER_UNMAPPED')
  )
}

async function carrierGet<T>(path: string, signal?: AbortSignal): Promise<T> {
  const session = await getSession()
  if (!session?.access_token) {
    throw new CarrierApiError('Not authenticated', 'UNAUTHENTICATED', 401)
  }

  const res = await fetch(`${apiBase}${path}`, {
    signal,
    headers: {
      Authorization: `Bearer ${session.access_token}`,
      Accept: 'application/json',
    },
  })

  let body: Envelope<T> | null = null
  try {
    body = (await res.json()) as Envelope<T>
  } catch {
    // A non-JSON body (a proxy error page, say) is still a failure — it just has no envelope.
    body = null
  }

  if (!res.ok || !body?.success) {
    const first = body?.errors?.[0]
    throw new CarrierApiError(
      first?.detail || body?.message || res.statusText || 'Request failed',
      first?.code ?? 'ERROR',
      res.status,
    )
  }
  return body.data
}

export function fetchFleetOverview(signal?: AbortSignal): Promise<FleetOverview> {
  return carrierGet<FleetOverview>('/api/v1/carrier/fleet-overview', signal)
}

/**
 * `status_filter` narrows list membership only. It is **not** a scope control — the carrier is
 * derived from the verified token by `resolve_carrier_scope`, which takes no argument at all
 * (M15), so there is no wire format here in which a carrier id could be expressed.
 */
export function fetchFleetShipments(
  statusFilter: string | null,
  signal?: AbortSignal,
): Promise<FleetShipmentList> {
  const qs = statusFilter ? `?status_filter=${encodeURIComponent(statusFilter)}` : ''
  return carrierGet<FleetShipmentList>(`/api/v1/carrier/shipments${qs}`, signal)
}

export function fetchFleetExceptions(signal?: AbortSignal): Promise<FleetExceptionList> {
  return carrierGet<FleetExceptionList>('/api/v1/carrier/exceptions', signal)
}

/** `window` accepts only `30d` (`carrier_reads._SUPPORTED_WINDOWS`); the design fixes the window
 *  by decision, so no picker exists to send anything else. Left unsent, letting the server apply
 *  its own default rather than the client restating it. */
export function fetchOnTimePerformance(signal?: AbortSignal): Promise<OnTimePerformance> {
  return carrierGet<OnTimePerformance>('/api/v1/carrier/on-time-performance', signal)
}

/**
 * `shipment_id` names a row; it is not a scope identifier and does not violate M15 — the carrier
 * that row must belong to still comes from the verified identity, server-side. **Do not add a
 * client-side ownership check around this call.** The refusal is the server's, and a second
 * client-side guard would look like the real one while protecting nothing.
 */
export function fetchShipmentDetail(
  shipmentId: string,
  signal?: AbortSignal,
): Promise<ShipmentDetail> {
  return carrierGet<ShipmentDetail>(
    `/api/v1/carrier/shipments/${encodeURIComponent(shipmentId)}`,
    signal,
  )
}
