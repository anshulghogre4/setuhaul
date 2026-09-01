import { useCallback, useEffect, useMemo, useState } from 'react'
import type { ReactNode } from 'react'
import type { Session } from '@supabase/supabase-js'

import type { Identity } from '@/core/auth/identity'
import { AuthContext, type AuthState, type AuthStatus } from '@/core/auth/auth-context'
import { getSession, onAuthChange, signOut, supabaseConfigured } from '@/core/auth/supabase'
import {
  readStoredFacilityChoice,
  selectableFacilityIds,
  writeStoredFacilityChoice,
} from '@/core/auth/active-facility'
import { toIdentity, UnmappedRoleError, type AccountProfile } from '@/core/auth/identity-mapping'
import { apiGet, apiPost, isApiError, type MeProfile } from '@/core/http/api'
import { registerUnauthorizedHandler } from '@/core/http/unauthorized'

/**
 * Fills `AuthContext`. See `auth-context.ts` for the contract, the no-fixture-fallback rule and
 * the failure-state table; this file is only the implementation.
 */
export function AuthProvider({ children }: { children: ReactNode }) {
  const [session, setSession] = useState<Session | null>(null)
  /**
   * The identity exactly as the server described it. The value published on the context is
   * `identity` below, which is this plus the viewer's own facility choice -- kept apart so the
   * choice can never widen `facilities`, only pick within it.
   */
  const [serverIdentity, setServerIdentity] = useState<Identity | null>(null)
  /** `null` = "whatever the server said". Only ever set to a member of
   *  `selectableFacilityIds(serverIdentity)`; see `active-facility.ts`. */
  const [facilityChoice, setFacilityChoice] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [status, setStatus] = useState<AuthStatus>('loading')
  const [retryToken, setRetryToken] = useState(0)

  const signOutLocal = useCallback(async () => {
    await signOut()
    // Do not wait for the `SIGNED_OUT` event to repaint: a sign-out click must clear the shell
    // immediately, and the event handler below is idempotent with this.
    setSession(null)
    setServerIdentity(null)
    setFacilityChoice(null)
    setError(null)
    setStatus('anonymous')
  }, [])

  /**
   * §7.5.8 `sign_out_everywhere` (issue #99.2). Server first, local session second.
   *
   * The order is the whole design of this function. The backend forwards the caller's OWN bearer
   * token to `POST /auth/v1/logout?scope=global` (`account_service.sign_out_everywhere`) -- so the
   * token has to still be live when the call goes out. Clearing the Supabase session first would
   * leave `authHeaders()` with nothing to attach and the request would never be made, which is
   * exactly the failure mode "sign out everywhere" must not have: it would look identical to
   * success from this device.
   *
   * On failure nothing is cleared and the error propagates -- see the contract in
   * `auth-context.ts` for why signing out locally after a failed global revoke would be a lie.
   */
  const signOutEverywhere = useCallback(async () => {
    await apiPost('/api/v1/sign-out-everywhere', {})
    await signOutLocal()
  }, [signOutLocal])

  /**
   * Session subscription.
   *
   * `onAuthChange` emits `INITIAL_SESSION` to a new subscriber as soon as the client settles, so
   * this alone would be sufficient. `getSession()` is still called once alongside it because it is
   * the call that *forces* initialisation and refreshes a token sitting inside the expiry margin --
   * which matters for the first paint after a long-idle tab, and for the Playwright suites, whose
   * sessions arrive pre-injected in localStorage rather than through a sign-in.
   */
  useEffect(() => {
    let live = true

    if (!supabaseConfigured) {
      // No VITE_SUPABASE_* configured: honestly unauthenticated rather than silently "logged in".
      setStatus('anonymous')
      return
    }

    const unsubscribe = onAuthChange((next) => {
      if (!live) return
      setSession(next)
      if (next === null) {
        setServerIdentity(null)
        setFacilityChoice(null)
        setError(null)
        setStatus('anonymous')
      }
    })

    void getSession().then((current) => {
      if (!live) return
      setSession((prev) => prev ?? current)
      if (current === null) setStatus((s) => (s === 'loading' ? 'anonymous' : s))
    })

    return () => {
      live = false
      unsubscribe()
    }
  }, [])

  /**
   * The central 401 handler (rule 3 of `core/http/api.ts`'s interceptor contract).
   *
   * Clears the session and nothing else -- deliberately no navigation here. `RequireAuth` is
   * already watching the session, so clearing it makes the guard redirect through the router and
   * preserve the attempted location for free, without a page reload that would discard typed work
   * (`auth-and-scoping.md`: "On expiry, in-flight work is preserved").
   */
  useEffect(() => registerUnauthorizedHandler(() => void signOutLocal()), [signOutLocal])

  /**
   * The identity read.
   *
   * Keyed on the authenticated SUBJECT, not on the access token: the token rotates roughly hourly
   * under `autoRefreshToken`, and re-reading `/auth/me` on every rotation would be a pointless
   * hourly round trip on a surface a planner leaves open all shift. The subject only changes when
   * a different person signs in.
   */
  const subject = session?.user?.id ?? null

  useEffect(() => {
    if (subject === null) return
    const controller = new AbortController()
    let live = true

    setStatus((s) => (s === 'authenticated' ? s : 'loading'))

    void (async () => {
      try {
        const me = (await apiGet<MeProfile>('/api/v1/auth/me', { signal: controller.signal })).data

        /**
         * `/account-profile` is fetched second and **best-effort**. It contributes exactly
         * one thing `/auth/me` cannot: `scoped_facility_ids` from `user_scopes`, the only source
         * that can express more than one facility per user
         * (`backend/app/services/account_service.py:76-87`). Losing it narrows the facility
         * switcher to the single `users.facility_id`; it is not a reason to refuse a session that
         * the server has already validated.
         */
        let profile: AccountProfile | null = null
        try {
          profile = (
            await apiGet<AccountProfile>('/api/v1/account-profile', {
              signal: controller.signal,
            })
          ).data
        } catch {
          profile = null
        }

        if (!live) return
        const next = toIdentity(me, profile)
        setServerIdentity(next)
        /**
         * Restore the viewer's own facility choice, **validated against the identity the server
         * just handed us** (M15). `localStorage` is attacker-writable, so a stored id is treated
         * exactly like a fresh click: if it is not in `selectableFacilityIds` it is dropped, not
         * repaired and not trusted. A facility this user held yesterday and lost today therefore
         * falls back to the server's own `activeFacilityId` silently, which is the correct answer.
         */
        const stored = readStoredFacilityChoice(next.userId)
        setFacilityChoice(stored !== null && selectableFacilityIds(next).has(stored) ? stored : null)
        setError(null)
        setStatus('authenticated')
      } catch (err) {
        if (!live || controller.signal.aborted) return

        // A 401 here means the token is dead. `apiGet` has already fired the central handler, so
        // the session is being cleared; do not also raise an error screen for it.
        if (isApiError(err) && err.status === 401) return

        setServerIdentity(null)
        setFacilityChoice(null)
        if (err instanceof UnmappedRoleError) {
          setError(
            `Your account's role (${err.roleName}) has no SetuHaul surface yet. ` +
              `Ask an administrator to change it.`,
          )
        } else if (isApiError(err) && err.status === 403) {
          // USER_UNMAPPED / USER_DISABLED (`deps.py:180,185`) -- a verdict about the account, so
          // the server's own sentence is the most useful thing to show.
          setError(err.message)
        } else {
          setError('Could not load your account. Check your connection and try again.')
        }
        setStatus('error')
      }
    })()

    return () => {
      live = false
      controller.abort()
    }
  }, [subject, retryToken])

  const retry = useCallback(() => setRetryToken((n) => n + 1), [])

  /**
   * The published identity = the server's identity with the viewer's facility choice applied.
   *
   * Only `activeFacilityId` is overridden. `facilities` and `canSelectAllFacilities` stay exactly
   * as the server described them, which is what keeps the switcher's option list -- and therefore
   * every id this client can ever produce -- server-derived (M15).
   */
  const identity = useMemo<Identity | null>(() => {
    if (serverIdentity === null) return null
    if (facilityChoice === null) return serverIdentity
    return { ...serverIdentity, activeFacilityId: facilityChoice }
  }, [serverIdentity, facilityChoice])

  const setActiveFacility = useCallback(
    (facilityId: string) => {
      if (serverIdentity === null) return
      // The M15 gate. A client-supplied id that the server-supplied identity does not list is
      // dropped outright rather than sent and refused -- the server would refuse it anyway
      // (`resolve_facility_scope`), but a request that could never be legitimate should not leave
      // the browser in the first place.
      if (!selectableFacilityIds(serverIdentity).has(facilityId)) return
      setFacilityChoice(facilityId)
      writeStoredFacilityChoice(serverIdentity.userId, facilityId)
    },
    [serverIdentity],
  )

  const value = useMemo<AuthState>(
    () => ({
      status,
      session,
      identity,
      error,
      retry,
      signOutLocal,
      signOutEverywhere,
      setActiveFacility,
    }),
    [
      status,
      session,
      identity,
      error,
      retry,
      signOutLocal,
      signOutEverywhere,
      setActiveFacility,
    ],
  )

  return <AuthContext value={value}>{children}</AuthContext>
}

