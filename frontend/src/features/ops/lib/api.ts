import { apiGet, apiPost, type MeProfile } from '@/core/http/api'
import type {
  AcknowledgeResult,
  CancelReasonCode,
  EscalationQueueResponse,
  HandBackResult,
  OwnerFilter,
  PostMessageResult,
  ReassignResult,
  ResolutionSuggestion,
  ResolveCancelResult,
  ResolveReasonCode,
  StartWorkResult,
  TakeOverResult,
  ThreadMessagesResponse,
} from './types'

/**
 * Real calls against the endpoints M3/E3.2 and E5.2 shipped
 * (`backend/app/api/v1/routers/operations.py`). No fixture data here -- this file is the one used
 * by the live `/ops` route; `gallery/fixtures.ts` is the separate, explicitly-fixture-only file
 * for `/ops/_states`.
 *
 * ## Idempotency keys are supplied by the caller, not generated here
 *
 * Everything except `fetchEscalationQueue`/`fetchMe`/`fetchThreadMessages` and `reassign` takes an
 * explicit `idempotencyKey`. That is a deliberate change from this file's first version, which
 * generated a fresh `crypto.randomUUID()` inside every function.
 *
 * `implementation-spec.md` section 3D requires the key be "reused verbatim on retry" -- a key
 * generated inside the call is a **new** key on every retry, so a retried write is a second write,
 * which is precisely what the header exists to prevent. The console now owns key lifetime
 * (`ops-console.tsx`'s `keyFor`/`clearKey`): one key per attempt, reused across retries of that
 * attempt, discarded on success.
 *
 * The opposite mistake matters too and is why the key is not simply derived from
 * `escalation_id + action`: `take_over_thread` stores its response against the key, so a stable
 * per-escalation key would make a genuine second takeover (after a hand-back) silently replay the
 * first one's response and never touch the thread.
 */

/** The signed-in coordinator. Needed for two things the console cannot do honestly without it:
 *  the queue's "Owner: mine" filter (which was previously approximated client-side as "owned by
 *  anyone", a real defect), and telling "you" apart from another coordinator in a transcript. */
export async function fetchMe(): Promise<MeProfile> {
  const res = await apiGet<MeProfile>('/api/v1/auth/me')
  return res.data
}

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

export async function acknowledgeEscalation(
  escalationId: string,
  idempotencyKey: string,
): Promise<AcknowledgeResult> {
  const res = await apiPost<AcknowledgeResult>(
    `/api/v1/operations/escalations/${escalationId}/acknowledge`,
    {},
    { idempotencyKey },
  )
  return res.data
}

/**
 * Issue #56 -- the explicit `ACKNOWLEDGED -> IN_PROGRESS` transition.
 *
 * Two callers, two different reasons: the coordinator marking real work started on a reason that
 * never involves a takeover (`NOTIFICATION_FAILED`), and the hand-back recovery path for a thread
 * taken over before the guard tightened (`takeover-control.tsx`).
 */
export async function startEscalationWork(
  escalationId: string,
  idempotencyKey: string,
): Promise<StartWorkResult> {
  const res = await apiPost<StartWorkResult>(
    `/api/v1/operations/escalations/${escalationId}/start`,
    {},
    { idempotencyKey },
  )
  return res.data
}

export async function reassignEscalation(
  escalationId: string,
  newOwnerId: string,
): Promise<ReassignResult> {
  // No Idempotency-Key: the route does not require one and Flow 5 classifies reassign as Low-tier,
  // reversible by reassigning again.
  const res = await apiPost<ReassignResult>(
    `/api/v1/operations/escalations/${escalationId}/reassign`,
    { new_owner_id: newOwnerId },
  )
  return res.data
}

export async function resolveEscalation(
  escalationId: string,
  reasonCode: ResolveReasonCode,
  idempotencyKey: string,
  resolutionNote?: string,
): Promise<ResolveCancelResult> {
  const res = await apiPost<ResolveCancelResult>(
    `/api/v1/operations/escalations/${escalationId}/resolve`,
    { reason_code: reasonCode, resolution_note: resolutionNote ?? null },
    { idempotencyKey },
  )
  return res.data
}

export async function cancelEscalation(
  escalationId: string,
  reasonCode: CancelReasonCode,
  idempotencyKey: string,
  resolutionNote?: string,
): Promise<ResolveCancelResult> {
  const res = await apiPost<ResolveCancelResult>(
    `/api/v1/operations/escalations/${escalationId}/cancel`,
    { reason_code: reasonCode, resolution_note: resolutionNote ?? null },
    { idempotencyKey },
  )
  return res.data
}

export async function takeOverThread(
  threadId: string,
  escalationId: string,
  idempotencyKey: string,
): Promise<TakeOverResult> {
  const res = await apiPost<TakeOverResult>(
    `/api/v1/operations/threads/${threadId}/take-over`,
    { escalation_id: escalationId },
    { idempotencyKey },
  )
  return res.data
}

export async function handBackThread(threadId: string): Promise<HandBackResult> {
  // The route genuinely does not require an Idempotency-Key (`operations.py`'s hand-back handler
  // takes no header at all, unlike take-over). Not sent, rather than sent and ignored.
  const res = await apiPost<HandBackResult>(`/api/v1/operations/threads/${threadId}/hand-back`, {})
  return res.data
}

/**
 * The ops-side durable transcript. **Not** the driver's `/chat/history`, which is
 * `require_roles(DRIVER)`-only and Redis-backed -- this reads `chat_messages`, so it includes the
 * `OPERATIONS` rows and the takeover dividers a coordinator needs to see.
 */
export async function fetchThreadMessages(threadId: string): Promise<ThreadMessagesResponse> {
  const res = await apiGet<ThreadMessagesResponse>(
    `/api/v1/operations/threads/${threadId}/messages`,
  )
  return res.data
}

/**
 * Issue #55 -- post as `OPERATIONS`.
 *
 * The body carries `message_text` and an optional `client_message_id` and **nothing else**: the
 * endpoint is `extra="forbid"`, and sender, driver and facility are all derived server-side from
 * the verified token and the thread's shipment (M15/NFR-019). There is deliberately no argument
 * here by which this client could name a facility, a driver or a sender.
 *
 * `clientMessageId` is passed as the same value as the key on purpose. It engages the endpoint's
 * *second* replay layer (the unique `external_message_id` index), so a retry that somehow varies
 * the header still cannot produce a duplicate message on a driver's screen.
 */
export async function postOperationsMessage(
  threadId: string,
  messageText: string,
  idempotencyKey: string,
): Promise<PostMessageResult> {
  const res = await apiPost<PostMessageResult>(
    `/api/v1/operations/threads/${threadId}/messages`,
    { message_text: messageText, client_message_id: idempotencyKey },
    { idempotencyKey },
  )
  return res.data
}

/**
 * Issue #57 -- the co-pilot's resolution-action suggestion.
 *
 * A `GET`, and there is no mutating counterpart anywhere in this file for it, deliberately. The
 * co-pilot **suggests and never acts**: this reads a recommendation and the facts behind it, and
 * the coordinator presses one of the buttons that were already on their screen. No auto-apply
 * path exists to be accidentally wired up later, because none is exported here.
 *
 * No `Idempotency-Key` (nothing is written) and no `facility_id` parameter (the backend derives
 * the facility from the escalation's own row -- M15/NFR-019). The only argument is the
 * `escalation_id` the console already holds from the queue read.
 */
export async function fetchResolutionSuggestion(
  escalationId: string,
): Promise<ResolutionSuggestion> {
  const res = await apiGet<ResolutionSuggestion>(
    `/api/v1/operations/escalations/${escalationId}/suggestion`,
  )
  return res.data
}
