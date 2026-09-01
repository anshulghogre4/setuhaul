/**
 * The one place a "the server rejected this token" signal is published.
 *
 * ## Why a registry and not a direct import
 *
 * `core/http/api.ts` is the HTTP interceptor; `core/auth/auth-context.tsx` is the React provider
 * that owns session state. The interceptor must be able to tell the provider "this token is dead"
 * **without importing it** -- api.ts is imported *by* the provider (it calls `apiGet('/auth/me')`),
 * so a direct import back would be a module cycle. A one-slot registry inverts the dependency: the
 * provider registers a handler on mount, the interceptor fires it, and neither file imports the
 * other's implementation.
 *
 * ## Why the handler does NOT navigate
 *
 * Deliberately: it only clears the session. The route guards (`components/auth/require-auth.tsx`)
 * are already watching the session, so clearing it makes the guard redirect to `/signin` **and
 * preserve the attempted location** for free, through the router, with no full page reload. A
 * `window.location = '/signin'` here would throw away in-flight typed work, which
 * `auth-and-scoping.md`'s "On expiry, in-flight work is preserved" rule forbids.
 *
 * ## What counts as a 401, verified against the backend rather than assumed
 *
 * Every 401 this application can receive means the bearer token itself is missing, expired or
 * invalid -- there is no "wrong role" 401:
 *   - `backend/app/core/deps.py:157`   -- `UNAUTHORIZED`, missing bearer token
 *   - `backend/app/core/security.py:51` -- `TOKEN_EXPIRED`
 *   - `backend/app/core/security.py:53,62,66` -- `TOKEN_INVALID`
 * Role refusal is `require_roles` -> `FORBIDDEN` **403** (`backend/app/core/deps.py:279`), and so
 * are `USER_UNMAPPED` / `USER_DISABLED` (`deps.py:180,185`). That asymmetry is what makes
 * "401 => sign out centrally, 403 => hand to the caller" a safe rule rather than a guess.
 */

type UnauthorizedHandler = () => void

let handler: UnauthorizedHandler | null = null

/** Registers the single handler. Returns an unsubscribe for React effect cleanup. */
export function registerUnauthorizedHandler(fn: UnauthorizedHandler): () => void {
  handler = fn
  return () => {
    if (handler === fn) handler = null
  }
}

/**
 * Called by the HTTP layer on a server 401. A no-op when nothing is registered -- which is the
 * correct behaviour in the states gallery routes and in unit contexts that render a component
 * without the provider, rather than a crash.
 */
export function notifyUnauthorized(): void {
  handler?.()
}
