import { createContext, use } from 'react'
import type { Session } from '@supabase/supabase-js'

import type { Identity } from '@/core/auth/identity'

/**
 * The session + identity CONTEXT and its two hooks. The provider that fills it lives beside
 * this file in `auth-provider.tsx` -- split in two only so each module has a single kind of
 * export and Fast Refresh stays intact (oxlint `react(only-export-components)`).
 *
 * **The thing that replaced the #52 fixture seam.**
 *
 * Before this existed, `App.tsx` rendered `PLANNER_MULTI_ROLE` -- a made-up planner -- into the
 * shell for every visitor, and `SignIn`'s `onSubmit` just called `navigate('/planner')`, so any
 * string in the password box "logged you in". This provider is the honest replacement.
 *
 * ## The one rule that must not be relaxed
 *
 * **There is no fixture fallback, at any point, for any failure.** If the session is missing the
 * app is anonymous; if `/auth/me` fails the app says so and offers a retry. Rendering a fixture
 * identity when the real one could not be read is precisely the bug this change exists to close --
 * it would show a real user someone else's name, role and facility, and would put a planner rail
 * in front of a driver.
 *
 * ## Where authority lives
 *
 * Nowhere in here. Scope is derived server-side from the verified token (M15,
 * `auth-and-scoping.md`); this provider transports the server's answer into React state and
 * derives *presentation* from it (rail, density, labels). Every one of those derivations already
 * lived in `core/auth/identity.ts` before this change and is untouched by it.
 *
 * ## Failure states, and why each is what it is
 *
 * | Condition | State | Why |
 * |---|---|---|
 * | no session | `anonymous` | the guards send the visitor to `/signin` |
 * | `/auth/me` 401 | `anonymous`, session cleared | the token is revoked or expired; the only 401s the backend issues are token failures (`deps.py:157`, `security.py:51-66`) |
 * | `/auth/me` 403 `USER_UNMAPPED`/`USER_DISABLED` | `error` (not retryable in practice, but retry is harmless) | a real server verdict about the account, not a transport fault |
 * | role has no UI surface | `error` naming the role | `FACILITY_MANAGER` / `REGIONAL_OPERATIONS_HEAD` are deferred personas with no screens |
 * | network / 5xx | `error` with retry | the session is fine; the read is not |
 */

export type AuthStatus = 'loading' | 'anonymous' | 'authenticated' | 'error'

export type AuthState = {
  status: AuthStatus
  session: Session | null
  identity: Identity | null
  /** Human sentence for the `error` status. Never shown alongside a fixture identity. */
  error: string | null
  /** Re-runs the identity read. Only meaningful while `status === 'error'`. */
  retry: () => void
  /** Local (single-device) sign-out. Clears the Supabase session; the guards do the redirect. */
  signOutLocal: () => Promise<void>
  /**
   * §7.5.8 `sign_out_everywhere` -- revokes every refresh token for this account through
   * `POST /api/v1/sign-out-everywhere`, THEN clears the local session.
   *
   * Rejects if the server refused, and deliberately does not sign out locally in that case: a
   * button that logs you out of this device while the other devices stay signed in would report
   * the opposite of what happened. The caller renders the failure.
   *
   * Honesty note carried from `account_service.sign_out_everywhere`'s own docstring: this revokes
   * refresh tokens, so another device stays usable until its already-issued access token expires
   * on its own. The menu copy says "signs you out on every device", never "immediately".
   */
  signOutEverywhere: () => Promise<void>
  /**
   * Sets the active facility for this viewer's session (issue #99.1).
   *
   * **Ignores any id the server-supplied identity does not grant** (M15): the argument is a
   * client-supplied value and is checked against `selectableFacilityIds(identity)` before it can
   * reach a read. See `core/auth/active-facility.ts` for where that set comes from and what the
   * server still re-derives on every request regardless.
   */
  setActiveFacility: (facilityId: string) => void
}

export const AuthContext = createContext<AuthState | null>(null)

/** Throws rather than returning a default: a component reading identity outside the provider is a
 *  wiring bug, and a silent `null` identity would look exactly like "signed out". */
export function useAuth(): AuthState {
  const ctx = use(AuthContext)
  if (ctx === null) throw new Error('useAuth() used outside <AuthProvider>')
  return ctx
}

/**
 * The identity for a route that is already behind `<RequireAuth>`.
 *
 * Non-null by construction: the guard does not render its children until `status` is
 * `authenticated`, which is the only state in which `identity` is set. This is what lets shell
 * routes take `Identity` (not `Identity | null`) and stay exactly as prop-driven as they were with
 * the fixtures.
 */
export function useIdentity(): Identity {
  const { identity } = useAuth()
  if (identity === null) {
    throw new Error('useIdentity() used outside a <RequireAuth> boundary')
  }
  return identity
}

