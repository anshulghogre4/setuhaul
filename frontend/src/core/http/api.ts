import { getSession } from '../auth/supabase'
import { apiErrorFromResponse, unauthenticatedError } from './errors'
import type { ApiEnvelope } from './errors'

/**
 * The shared HTTP layer. Every surface calls through here.
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
  const session = await getSession()
  if (!session?.access_token) {
    // Code-bearing rather than a bare Error, so a caller can tell "no session" from a 403 the
    // server actually issued. `.message` is unchanged ('Not authenticated'), so the existing
    // `formatUserFriendlyError` match still fires.
    throw unauthenticatedError()
  }
  return {
    Authorization: `Bearer ${session.access_token}`,
    Accept: 'application/json',
    ...extra,
  }
}

/**
 * Parses the envelope defensively.
 *
 * `Response.json()` **rejects with a `SyntaxError`** when the body is not valid JSON (MDN,
 * `Response.json()`, checked 2026-08-31). A proxy's HTML 502 page is exactly that case, and it is
 * still a real HTTP failure -- so a parse failure yields `null` here and the caller reports the
 * status, instead of a `SyntaxError` about an unexpected `<` masquerading as the problem.
 */
async function readEnvelope<T>(res: Response): Promise<ApiEnvelope<T> | null> {
  try {
    return (await res.json()) as ApiEnvelope<T>
  } catch {
    return null
  }
}

async function unwrap<T>(res: Response): Promise<ApiEnvelope<T>> {
  const body = await readEnvelope<T>(res)
  if (!res.ok || !body?.success) {
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
