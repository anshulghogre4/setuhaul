import { apiGet, apiPost } from '@/core/http/api'
import type {
  AcknowledgeResult,
  CancelReasonCode,
  EscalationQueueResponse,
  HandBackResult,
  OwnerFilter,
  ReassignResult,
  ResolveCancelResult,
  ResolveReasonCode,
  TakeOverResult,
} from './types'

/**
 * Real calls against the endpoints M3/E3.2 shipped (`backend/app/api/v1/routers/operations.py`).
 * No fixture data here -- this file is the one used by the live `/ops` route; `gallery/fixtures.ts`
 * is the separate, explicitly-fixture-only file for `/ops/_states`.
 *
 * Every mutation that the backend requires an `Idempotency-Key` for (`operations.py:58-64`, U70)
 * gets one generated with `crypto.randomUUID()` and passed through `apiPost`'s existing
 * `idempotencyKey` option -- the same mechanism `core/http/api.ts` already exposes for the
 * driver-chat tools.
 */

export async function fetchEscalationQueue(opts: {
  facilityId?: string | null
  owner?: OwnerFilter
}): Promise<EscalationQueueResponse> {
  const params = new URLSearchParams()
  if (opts.facilityId) params.set('facility_id', opts.facilityId)
  if (opts.owner && opts.owner !== 'all') params.set('owner', opts.owner)
  const qs = params.toString()
  const res = await apiGet<EscalationQueueResponse>(
    `/api/v1/operations/escalation-queue${qs ? `?${qs}` : ''}`,
  )
  return res.data
}

export async function acknowledgeEscalation(escalationId: string): Promise<AcknowledgeResult> {
  const res = await apiPost<AcknowledgeResult>(
    `/api/v1/operations/escalations/${escalationId}/acknowledge`,
    {},
    { idempotencyKey: crypto.randomUUID() },
  )
  return res.data
}

export async function reassignEscalation(
  escalationId: string,
  newOwnerId: string,
): Promise<ReassignResult> {
  const res = await apiPost<ReassignResult>(
    `/api/v1/operations/escalations/${escalationId}/reassign`,
    { new_owner_id: newOwnerId },
  )
  return res.data
}

export async function resolveEscalation(
  escalationId: string,
  reasonCode: ResolveReasonCode,
  resolutionNote?: string,
): Promise<ResolveCancelResult> {
  const res = await apiPost<ResolveCancelResult>(
    `/api/v1/operations/escalations/${escalationId}/resolve`,
    { reason_code: reasonCode, resolution_note: resolutionNote ?? null },
    { idempotencyKey: crypto.randomUUID() },
  )
  return res.data
}

export async function cancelEscalation(
  escalationId: string,
  reasonCode: CancelReasonCode,
  resolutionNote?: string,
): Promise<ResolveCancelResult> {
  const res = await apiPost<ResolveCancelResult>(
    `/api/v1/operations/escalations/${escalationId}/cancel`,
    { reason_code: reasonCode, resolution_note: resolutionNote ?? null },
    { idempotencyKey: crypto.randomUUID() },
  )
  return res.data
}

export async function takeOverThread(
  threadId: string,
  escalationId: string,
): Promise<TakeOverResult> {
  const res = await apiPost<TakeOverResult>(
    `/api/v1/operations/threads/${threadId}/take-over`,
    { escalation_id: escalationId },
    { idempotencyKey: crypto.randomUUID() },
  )
  return res.data
}

export async function handBackThread(threadId: string): Promise<HandBackResult> {
  const res = await apiPost<HandBackResult>(`/api/v1/operations/threads/${threadId}/hand-back`, {})
  return res.data
}
