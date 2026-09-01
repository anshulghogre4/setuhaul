import { createClient, type Session, type SupabaseClient } from '@supabase/supabase-js'

const url = import.meta.env.VITE_SUPABASE_URL as string | undefined
const anon = import.meta.env.VITE_SUPABASE_ANON_KEY as string | undefined

export const supabaseConfigured = Boolean(url && anon)

/**
 * The one Supabase client. Everything that needs a token goes through `getSession()` below --
 * see the interceptor contract in `core/http/api.ts`.
 *
 * **The three auth options are pinned explicitly rather than left to the default**, even though
 * all three ARE the default in the pinned version. Verified, not assumed:
 * `node_modules/@supabase/auth-js/dist/main/GoTrueClient.js:17-31` (`@supabase/auth-js@2.112.2`,
 * the exact version `@supabase/supabase-js@2.112.2` resolves) declares
 * `DEFAULT_OPTIONS = { autoRefreshToken: true, persistSession: true, detectSessionInUrl: true, ... }`.
 *
 * They are written out because the whole token strategy rests on them and a silent upstream
 * default change would be invisible otherwise:
 *
 *  - `autoRefreshToken` -- the app never refreshes a token itself. `getSession()` refreshes when
 *    the access token is within the expiry margin (`GoTrueClient.js:2526-2554`), and a background
 *    ticker refreshes while a tab is foregrounded. Turning this off would make every desk surface
 *    die silently at the 1-hour mark.
 *  - `persistSession` -- localStorage under `sb-<project-ref>-auth-token`. This is also the seam
 *    the Playwright suites inject a real minted session through (`tests/support/session.ts`), so
 *    disabling it would break authenticated E2E as well as page reloads.
 *  - `detectSessionInUrl` -- the password-reset link comes back as a URL fragment; without this
 *    the recovery flow has no way to establish its session.
 */
export const supabase: SupabaseClient | null = supabaseConfigured
  ? createClient(url!, anon!, {
      auth: {
        autoRefreshToken: true,
        persistSession: true,
        detectSessionInUrl: true,
      },
    })
  : null

/**
 * ⚠ **Superseded for routing.** `Portal`/`portalHome`/`portalLogin`/`roleToPortal` describe the
 * two-entry-shell POC that predates the six-surface model. The authority for "which surface does
 * this role land on" is now `core/auth/identity.ts`'s `landingPathFor()` (derived from
 * `RAIL_BY_ROLE`, itself derived from `auth-and-scoping.md`'s Role-landing table), and the
 * authority for "may this role open this route" is `core/auth/surface-access.ts`, which mirrors
 * the backend's own `require_roles` gates.
 *
 * Kept rather than deleted because they are exported API and nothing in `src/` imports them
 * (verified by grep, 2026-09-01) -- removing exports is a separate cleanup, not part of wiring
 * real sign-in. Note `portalLogin`'s `/driver/login` and `/ops/login` routes do not exist: there
 * is one shared sign-in at `/signin`, per `auth-and-scoping.md` ("Single sign-in for all six
 * roles").
 */
export type Portal = 'driver' | 'ops'

export const portalHome: Record<Portal, string> = {
  driver: '/driver',
  ops: '/ops',
}

export const portalLogin: Record<Portal, string> = {
  driver: '/driver/login',
  ops: '/ops/login',
}

const OPS_PORTAL_ROLES = new Set([
  'OPERATIONS_EXECUTIVE',
  'WAREHOUSE_PLANNER',
  'OPERATIONS_MANAGER',
  'FACILITY_MANAGER',
  'TRANSPORT_MANAGER',
  'REGIONAL_OPERATIONS_HEAD',
  'ADMIN',
])

export function roleToPortal(roleName: string): Portal | null {
  if (roleName === 'DRIVER') return 'driver'
  if (OPS_PORTAL_ROLES.has(roleName)) return 'ops'
  return null
}

export async function getSession(): Promise<Session | null> {
  if (!supabase) return null
  const { data } = await supabase.auth.getSession()
  return data.session
}

/**
 * Subscribes to session changes. Returns an unsubscribe suitable for a React effect cleanup.
 *
 * The callback is deliberately **synchronous and trivial** (it only sets React state). The pinned
 * client's own docstring is the reason -- `@supabase/auth-js@2.112.2`, `GoTrueClient.js:3446-3448`:
 *
 *   > Events are emitted across tabs ... Use a quick and efficient callback function, and defer or
 *   > debounce as many operations as you can to be performed outside of the callback.
 *   > ... Events are awaited in order, so a slow callback delays subsequent events to subscribers.
 *
 * (The same block also records that in this version a callback *may* safely call other auth
 * methods -- the old deadlock warning no longer applies on the lockless path. The reason we still
 * do not fetch `/auth/me` from inside it is the "keep it quick" rule above, not deadlock.)
 *
 * `INITIAL_SESSION` is emitted to a new subscriber as soon as initialisation settles
 * (`GoTrueClient.js:3650`), which is what makes a page reload -- and a Playwright
 * `storageState`-injected session -- resolve without any extra call.
 */
export function onAuthChange(cb: (session: Session | null) => void): () => void {
  if (!supabase) return () => {}
  const { data } = supabase.auth.onAuthStateChange((_event, session) => {
    cb(session)
  })
  return () => data.subscription.unsubscribe()
}

export async function signIn(email: string, password: string) {
  if (!supabase) throw new Error('Supabase is not configured. Set VITE_SUPABASE_URL and VITE_SUPABASE_ANON_KEY.')
  return supabase.auth.signInWithPassword({ email, password })
}

export async function signOut() {
  if (!supabase) return
  // E3.5 (issue #29): Supabase's signOut() defaults to `scope: 'global'`, which revokes every
  // refresh token for this user, not just this device. This is the plain single-device "Sign
  // Out" button, so it must say so explicitly -- without `local` here it silently becomes
  // sign_out_everywhere. Found live in production during E3.5's implementation: this call had
  // no scope argument at all, meaning every ordinary sign-out was already doing the global
  // revoke by accident.
  await supabase.auth.signOut({ scope: 'local' })
  sessionStorage.clear()
  localStorage.removeItem('setuhaul.returnUrl')
}
