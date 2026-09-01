import { getSession } from '../auth/supabase'
import { apiErrorFromResponse, readEnvelope, unauthenticatedError } from './errors'
import type { ApiEnvelope } from './errors'
import { notifyUnauthorized } from './unauthorized'

/**
 * The shared HTTP layer. Every surface calls through here.
 *
 * ## THE INTERCEPTOR CONTRACT (one place, five rules)
 *
 * This module is the single choke point for authenticated traffic. Nothing under `features/**`
 * calls `fetch` directly; the one deliberate exception is `core/http/sse.ts`, which needs a
 * streaming POST that `fetch`-with-`unwrap` cannot express and which follows the identical rules
 * below. Verified by grep, 2026-09-01: `fetch(` appears in `src/` in exactly **two modules** --
 * this one (3 call sites: `apiGet`, `apiPost`, `apiGetBlob`) and `sse.ts` (1) -- and there is no
 * `axios`, no `XMLHttpRequest` and no `new EventSource` anywhere. `getSession()` and the string
 * `access_token` likewise appear nowhere outside `core/`, so no surface holds a token of its own.
 *
 *  1. **Attach on request.** Every call reads the access token from `getSession()` at send time
 *     (`authHeaders` below). No module-level token cache exists anywhere in `src/` -- a cached
 *     token is a token that goes stale silently, and this product's sessions are 1 hour long.
 *  2. **Refresh belongs to supabase-js, not to us.** `createClient` runs with
 *     `autoRefreshToken: true` (pinned explicitly in `core/auth/supabase.ts`), and
 *     `getSession()` itself refreshes when the access token is inside the expiry margin
 *     (`@supabase/auth-js@2.112.2`, `GoTrueClient.js:2526-2554`). So "read it fresh per request"
 *     is not a nicety, it is the whole refresh strategy.
 *  3. **401 is central.** A server 401 always means the token is missing/expired/invalid (see
 *     `./unauthorized.ts` for the backend citations). It fires `notifyUnauthorized()` once, and
 *     the auth provider clears the session; the route guard then redirects to `/signin`
 *     preserving the attempted location. **No screen implements 401 handling.**
 *  4. **403 is the caller's problem.** A scope or role refusal is a screen-level state -- the
 *     carrier portal renders a different screen for `FORBIDDEN`, the planner branches on five
 *     refusal codes. Signing someone out because they touched something outside their scope
 *     would be wrong, and would also hide a real product bug.
 *  5. **The server remains the authority.** Nothing here decides what a caller may see; it only
 *     transports the decision the server already made (M15, `auth-and-scoping.md`).
 *
 * **All failures throw `ApiError`** (`./errors.ts`), which carries the envelope's `code`, its
 * `detail` (parsed as `data` when the server sent a JSON document), the HTTP `status` and the
 * `request_id` -- so a caller branches on `err.code`, never on an English message string. That
 * error still `instanceof Error` and still has a sensible `.message`, so a `catch` block that only
 * reads `.message` needs no change. See `./errors.ts` for the message-precedence rule and why it
 * preserves what callers read before this file grew a real error type.
 *
 * A **transport** failure -- DNS, offline, CORS -- is still whatever `fetch` rejected with
 * (a `TypeError`), deliberately not wrapped: `formatUserFriendlyError` below matches on its
 * "failed to fetch" wording, and an `ApiError` with an invented status would claim the server
 * answered when it never did.
 */

const apiBase = (import.meta.env.VITE_API_BASE_URL as string | undefined) || 'http://localhost:8000'

export { ApiError, isApiError, hasApiErrorCode } from './errors'
export type { ApiEnvelope, ApiErrorDetail } from './errors'

export type MeProfile = {
  user_id: string
  email: string
  full_name: string
  role_id: string
  role_name: string
  driver_id: string | null
  facility_id: string | null
  permissions: string[]
  scope: { type: string; facility_id: string | null; driver_id: string | null }
}

async function authHeaders(extra?: Record<string, string>): Promise<Record<string, string>> {
  // Rule 1 + 2 of the contract: read the token from supabase-js at SEND time, every time. This
  // call is what makes refresh transparent -- `getSession()` refreshes when the token is inside
  // the expiry margin rather than handing back a nearly-dead one.
  const session = await getSession()
  if (!session?.access_token) {
    // Code-bearing rather than a bare Error, so a caller can tell "no session" from a 403 the
    // server actually issued. `.message` is unchanged ('Not authenticated'), so the existing
    // `formatUserFriendlyError` match still fires.
    //
    // Deliberately does NOT fire `notifyUnauthorized()`: no server answered, so there is no
    // verdict to act on. supabase-js already emits `SIGNED_OUT` when it drops a session whose
    // refresh failed, and the auth provider listens for exactly that -- firing here as well would
    // make the client's own missing-session state indistinguishable from a server revocation.
    throw unauthenticatedError()
  }
  return {
    Authorization: `Bearer ${session.access_token}`,
    Accept: 'application/json',
    ...extra,
  }
}

/**
 * Rule 3 of the contract above, in one function so there is exactly one place to change it.
 *
 * Called on every non-ok response before the error is thrown. Only 401 is intercepted; 403 and
 * every refusal code fall straight through to the caller untouched.
 */
function interceptResponseStatus(status: number): void {
  if (status === 401) notifyUnauthorized()
}

async function unwrap<T>(res: Response): Promise<ApiEnvelope<T>> {
  const body = await readEnvelope<T>(res)
  if (!res.ok || !body?.success) {
    interceptResponseStatus(res.status)
    throw apiErrorFromResponse(res, body)
  }
  return body
}

/**
 * `signal` is here because a surface that swaps the record it is showing must be able to abort the
 * previous read rather than race it (`features/carrier/screens/shipment-detail.tsx`). An aborted
 * fetch rejects with an `AbortError` `DOMException`, not an `ApiError`; callers check
 * `signal.aborted` before rendering a failure.
 */
export async function apiGet<T>(
  path: string,
  opts?: { signal?: AbortSignal },
): Promise<ApiEnvelope<T>> {
  const res = await fetch(`${apiBase}${path}`, {
    headers: await authHeaders(),
    signal: opts?.signal,
  })
  return unwrap<T>(res)
}

export async function apiPost<T>(
  path: string,
  payload: unknown,
  opts?: { idempotencyKey?: string; signal?: AbortSignal },
): Promise<ApiEnvelope<T>> {
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
  }
  if (opts?.idempotencyKey) {
    headers['Idempotency-Key'] = opts.idempotencyKey
  }
  const res = await fetch(`${apiBase}${path}`, {
    method: 'POST',
    headers: await authHeaders(headers),
    body: JSON.stringify(payload),
    signal: opts?.signal,
  })
  return unwrap<T>(res)
}

/**
 * A GET whose **success** body is not the JSON envelope -- currently only
 * `GET /api/v1/admin/audit-log/export`, which returns `PlainTextResponse(csv, "text/csv")`
 * (`backend/app/api/v1/routers/admin.py`).
 *
 * Its *failure* body still is the envelope (`app_error_handler` answers every `AppError` with
 * `fail(...)` regardless of the route's success media type), so a refusal here throws the same
 * code-bearing `ApiError` as everywhere else rather than a hand-made `Export failed (403)` string.
 * That is the whole reason this belongs in the shared layer instead of being hand-rolled per
 * surface: the error path is identical even though the success path is not.
 */
export async function apiGetBlob(
  path: string,
  opts?: { accept?: string; signal?: AbortSignal },
): Promise<Blob> {
  const res = await fetch(`${apiBase}${path}`, {
    headers: await authHeaders({ Accept: opts?.accept ?? '*/*' }),
    signal: opts?.signal,
  })
  if (!res.ok) {
    interceptResponseStatus(res.status)
    throw apiErrorFromResponse(res, await readEnvelope<unknown>(res))
  }
  return await res.blob()
}

export function formatUserFriendlyError(err: unknown): string {
  if (!err) return 'Something went wrong while processing your request. Please try again.'
  const message = err instanceof Error ? err.message : String(err)
  const lower = message.toLowerCase()

  if (
    lower.includes('failed to fetch') ||
    lower.includes('networkerror') ||
    lower.includes('network error') ||
    lower.includes('failed to connect') ||
    lower.includes('load failed')
  ) {
    return 'Unable to connect to SetuHaul server. Please check your internet connection or server status and try again.'
  }
  if (lower.includes('not authenticated') || lower.includes('401') || lower.includes('unauthorized') || lower.includes('token expired')) {
    return 'Your session has expired. Please sign in again.'
  }
  if (lower.includes('403') || lower.includes('forbidden') || lower.includes('permission')) {
    return 'Access denied. You do not have permission for this action.'
  }
  if (lower.includes('404') || lower.includes('not found')) {
    return 'The requested record or facility details could not be found.'
  }
  if (lower.includes('409') || lower.includes('conflict')) {
    return 'This request has already been processed or updated by another user. Please refresh and try again.'
  }
  if (lower.includes('500') || lower.includes('502') || lower.includes('503') || lower.includes('504')) {
    return 'SetuHaul server is temporarily busy. Please try again in a few moments.'
  }
  const cleaned = message.replace(/^(error:|apperror:|httperror:)\s*/i, '').trim()
  return cleaned || 'An unexpected error occurred. Please try again.'
}
