import { apiGet, isApiError } from '@/core/http/api'
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
 * ## This file used to hand-roll its own fetch. It no longer does (2026-08-31).
 *
 * The reason it did was real: `apiGet` threw `new Error(detail)` and discarded the envelope's
 * `errors[0].code`, and this surface has one screen whose entire correctness depends on that code
 * — `05-carrier-portal/edge-cases.md` #1's out-of-scope refusal, which must render its own
 * designed screen for a `FORBIDDEN` and the ordinary "couldn't load" treatment for anything else.
 * Matching an English message string would have made a security-relevant screen depend on copy
 * nobody promised to keep stable.
 *
 * `core/http/api.ts` now throws a code-bearing `ApiError` for every surface, so the duplicate
 * fetch, the duplicate envelope type and the duplicate error class are gone. `isOutOfScope` below
 * is unchanged in meaning and is still the only place this surface reads a code.
 */

/**
 * True for the refusal `assert_shipment_in_carrier_fleet` raises — identical for a shipment that
 * does not exist and one belonging to another carrier, by design (`edge-cases.md` #1). The client
 * must never try to tell those apart, and with this envelope it structurally cannot.
 *
 * A transport failure is not an `ApiError` and so can never match here, which is the property that
 * keeps "the network died" from ever being rendered as "you are not allowed to see this".
 */
export function isOutOfScope(err: unknown): boolean {
  return isApiError(err) && err.status === 403 && (err.code === 'FORBIDDEN' || err.code === 'CARRIER_UNMAPPED')
}

async function carrierGet<T>(path: string, signal?: AbortSignal): Promise<T> {
  const res = await apiGet<T>(path, { signal })
  return res.data
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
