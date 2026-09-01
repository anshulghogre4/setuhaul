/**
 * The one error type every SetuHaul HTTP call throws.
 *
 * ## Why this file exists
 *
 * `apiGet`/`apiPost` used to throw `new Error(detail)`, which **discarded the envelope's
 * `errors[0].code`**. Three surfaces independently hand-rolled their own fetch to get that code
 * back -- `features/carrier/lib/api.ts` (a `FORBIDDEN` scope refusal must render a different screen
 * from a network fault), `features/planner/lib/http.ts` (five refusal codes, three of which carry a
 * **JSON document** in `detail`), and `features/admin/lib/api.ts` (`ALREADY_ACTIONED` vs
 * `BASE_VERSION_REQUIRED` need different screens). A fourth surface, ops, hit the same wall and
 * recorded that `THREAD_UNSCOPED` was distinguishable only by message string. Three independent
 * workarounds for one missing field is the signal to fix the field, not to write a fourth.
 *
 * ## The backend contract this models (read off source, not assumed)
 *
 * `backend/app/core/envelope.py::fail` builds every failure as
 * `{ success: false, message, errors: [{ code, detail, field }], request_id }`, and crucially
 * `detail = detail or message` -- so for most failures **`detail` and `message` are the same
 * string**. They diverge only where a service passes an explicit `detail`, and there `detail` is
 * one of two quite different things:
 *
 *  - extra *prose* that narrows the message (`"Supported: A, B, C."`,
 *    `"based_on_version_id=<uuid>"`), or
 *  - a **JSON document** the client is meant to parse -- `scheduling/allocation.py`'s
 *    `_snapshot_stale_error`, `_displacement_error` and `_interval_unavailable_error` all
 *    `json.dumps(...)` into it, carrying `current_snapshot_hash`, the named conflict set and the
 *    failure code that the planner's recovery path is built on.
 *
 * That dual typing is the whole reason a single string field cannot serve. `ApiError` therefore
 * keeps `detail` raw, publishes the parsed document separately as `data`, and keeps the envelope's
 * human sentence as `envelopeMessage`.
 */

/** One entry of the envelope's `errors` array (`backend/app/core/envelope.py::ErrorDetail`). */
export type ApiErrorDetail = {
  code: string
  detail: string
  field?: string | null
}

/** The success/failure envelope every JSON endpoint returns (`SuccessEnvelope`/`ErrorEnvelope`). */
export type ApiEnvelope<T> = {
  success: boolean
  message: string
  data: T
  timestamp: string
  request_id: string
  errors?: ApiErrorDetail[]
}

/**
 * `detail` parsed, but only when it is genuinely a JSON *document*.
 *
 * The object/non-array test is deliberate and is lifted verbatim from the rule
 * `features/planner/lib/refusals.ts` already proved against these exact endpoints: a `detail` of
 * `"123"` is valid JSON but is not a document, and treating it as one would hide a real sentence.
 * A parse failure here is **ordinary, not exceptional** -- it just means this refusal put prose in
 * `detail`, which most of them do.
 */
function parseDetailDocument(detail: string): Record<string, unknown> | null {
  if (!detail) return null
  try {
    const parsed: unknown = JSON.parse(detail)
    if (typeof parsed !== 'object' || parsed === null || Array.isArray(parsed)) return null
    return parsed as Record<string, unknown>
  } catch {
    return null
  }
}

export type ApiErrorInit = {
  /** `errors[0].code`, or `'ERROR'` when the envelope named none. Never empty. */
  code: string
  /** `errors[0].detail`, raw and unparsed. May be prose or a JSON document. */
  detail: string
  /** The envelope's own `message` -- always a human sentence, never a document. */
  envelopeMessage: string
  status: number
  field?: string | null
  requestId?: string | null
  cause?: unknown
}

/**
 * A failed API call, carrying everything the envelope actually said.
 *
 * **`instanceof Error` still holds and `.message` is still a sensible human sentence**, which is
 * what lets every pre-existing `catch (e) { show(e.message) }` block keep working untouched --
 * including `formatUserFriendlyError`, which only ever reads `.message`. `target` is `es2023`
 * (`tsconfig.app.json`), well past the ES5 down-level emit that used to break `instanceof` on
 * `Error` subclasses, so no prototype fix-up is needed here.
 */
export class ApiError extends Error {
  /** Branch on THIS, never on `.message`. `'ERROR'` when the envelope named no code. */
  readonly code: string
  /** Raw `errors[0].detail`. Prefer `data` when the server sent a document. */
  readonly detail: string
  /**
   * `detail` parsed when it was a JSON document, otherwise `null`.
   *
   * This is the field that made `features/planner/lib/http.ts` necessary: flattening the envelope
   * to one string threw away `current_snapshot_hash` and the named conflict set that
   * `SNAPSHOT_STALE` / `DISPLACEMENT_DETECTED` / `INTERVAL_UNAVAILABLE` deliberately send.
   */
  readonly data: Record<string, unknown> | null
  /** The envelope's `message`. For `ALREADY_ACTIONED` this is the only place the *winning*
   *  transition is named (`allocation.py::_already_actioned_error` builds it into the message,
   *  not into `detail`), which is why it is carried rather than collapsed away. */
  readonly envelopeMessage: string
  readonly status: number
  readonly field: string | null
  /** `request_id` from the envelope -- the token that ties a user report to a server log line. */
  readonly requestId: string | null

  constructor(init: ApiErrorInit) {
    /*
     * Message precedence, and why it is this way rather than simply "detail first":
     *
     * `detail` is the more specific string whenever it is prose, and the old `apiGet`/`apiPost`
     * put it in `.message` -- so prose-detail keeps winning, byte-for-byte preserving what every
     * existing caller reads today. But when `detail` is a JSON document it is not a sentence at
     * all, and putting it in `.message` would render a raw blob at whatever `formatUserFriendlyError`
     * feeds. In that case the envelope's own sentence wins, which is exactly the rule
     * `PlannerApiError` and `AdminApiError` chose for themselves.
     */
    const document = parseDetailDocument(init.detail)
    const message =
      document === null
        ? init.detail || init.envelopeMessage || 'Request failed'
        : init.envelopeMessage || 'Request failed'
    super(message, init.cause === undefined ? undefined : { cause: init.cause })
    this.name = 'ApiError'
    this.code = init.code
    this.detail = init.detail
    this.data = document
    this.envelopeMessage = init.envelopeMessage
    this.status = init.status
    this.field = init.field ?? null
    this.requestId = init.requestId ?? null
  }
}

/**
 * Parses the envelope defensively.
 *
 * `Response.json()` **rejects with a `SyntaxError`** when the body is not valid JSON (MDN,
 * `Response.json()`, checked 2026-08-31). A proxy's HTML 502 page is exactly that case, and it is
 * still a real HTTP failure -- so a parse failure yields `null` here and the caller reports the
 * status, instead of a `SyntaxError` about an unexpected `<` masquerading as the problem.
 *
 * Lives here rather than in `api.ts` because the SSE transport (`core/http/sse.ts`) needs the same
 * parser for its own failure path, and two copies of "parse the envelope, tolerantly" is exactly
 * how the two halves drift.
 */
export async function readEnvelope<T>(res: Response): Promise<ApiEnvelope<T> | null> {
  try {
    return (await res.json()) as ApiEnvelope<T>
  } catch {
    return null
  }
}

/**
 * Builds an `ApiError` from a response and whatever body could be parsed from it.
 *
 * `body` is nullable on purpose: a proxy error page or a truncated stream is still a failure, it
 * just has no envelope. `Response.json()` rejects with a `SyntaxError` on a non-JSON body (MDN,
 * `Response.json()`, checked 2026-08-31), so the callers below parse defensively and pass `null`
 * rather than letting a `SyntaxError` escape in place of the real HTTP failure.
 */
export function apiErrorFromResponse(
  res: Response,
  body: Partial<ApiEnvelope<unknown>> | null,
): ApiError {
  const first = body?.errors?.[0]
  const envelopeMessage = body?.message || res.statusText || 'Request failed'
  return new ApiError({
    code: first?.code ?? 'ERROR',
    detail: first?.detail ?? body?.message ?? res.statusText ?? '',
    envelopeMessage,
    status: res.status,
    field: first?.field ?? null,
    requestId: body?.request_id ?? null,
  })
}

/**
 * No usable session. Thrown before the request leaves the browser, so there is no status to
 * report -- 401 is the honest stand-in and `UNAUTHENTICATED` is the code to branch on.
 *
 * The message is deliberately the exact string the old helpers threw (`'Not authenticated'`), so
 * `formatUserFriendlyError`'s existing `'not authenticated'` match keeps firing.
 */
export function unauthenticatedError(): ApiError {
  return new ApiError({
    code: 'UNAUTHENTICATED',
    detail: 'Not authenticated',
    envelopeMessage: 'Not authenticated',
    status: 401,
  })
}

/** Narrowing guard. Prefer this to a bare `instanceof` at module boundaries. */
export function isApiError(err: unknown): err is ApiError {
  return err instanceof ApiError
}

/**
 * `true` when the failure is the server refusing with one of the named codes.
 *
 * The point of this helper is that it is impossible to misuse the way message matching is: a
 * transport failure is not an `ApiError` and therefore matches no code, so a caller can never
 * accidentally treat "the network died" as "the server said FORBIDDEN".
 */
export function hasApiErrorCode(err: unknown, ...codes: string[]): boolean {
  return isApiError(err) && codes.includes(err.code)
}
