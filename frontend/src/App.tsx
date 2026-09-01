import { Suspense, lazy, useState } from 'react'
import { Navigate, Route, Routes, useLocation, useNavigate } from 'react-router-dom'
import { isAuthRetryableFetchError } from '@supabase/supabase-js'
import { toast } from 'sonner'

import { AppShell, type ShellChrome } from '@/components/shell/app-shell'
import { RequireAuth } from '@/components/auth/require-auth'
import type { Density } from '@/core/auth/identity'
import { facilityIdForReads } from '@/core/auth/active-facility'
import { useAuth, useIdentity } from '@/core/auth/auth-context'
import { formatUserFriendlyError } from '@/core/http/api'
import { signIn } from '@/core/auth/supabase'
import { canAccess, homePathFor } from '@/core/auth/surface-access'
import { NotFound } from '@/components/states/region-states'
import { PasswordReset } from '@/features/auth/password-reset'
import { SignIn, type SignInState } from '@/features/auth/sign-in'
import { NOTIFICATIONS, RECENT_SEARCHES, SEARCH_RESULTS } from '@/features/gallery/fixtures'
import { SettingsPage } from '@/features/settings/settings-page'
import { DriverShell } from '@/features/driver/driver-shell'
import { DriverConversation } from '@/features/driver/screens/conversation'
import { DriverProfile } from '@/features/driver/screens/profile'
import { DriverThreadList } from '@/features/driver/screens/thread-list'
import { OpsConsole } from '@/features/ops/ops-console'
import { PlannerConsole } from '@/features/planner/planner-console'
import { AdminConsole } from '@/features/admin'
import { CarrierPortal } from '@/features/carrier/carrier-portal'
import { GateRoute } from '@/features/gate/gate-route'

/**
 * The two verification galleries are **lazy**, and this is a measured decision rather than a
 * habit.
 *
 * Neither is linked from the app -- they exist so a human can see every artboard rendered by the
 * real components -- but statically imported they landed in the entry chunk that a driver on a
 * roadside 3G connection downloads before the thread list paints.
 *
 * **Measured with `vite build`, before and after, rather than assumed:**
 * entry `737.63 kB / 218.98 kB gzip` -> `699.29 kB / 207.93 kB gzip`, with the two galleries
 * moving into `states-gallery` (20.45 kB) and `driver-gallery` (18.98 kB) chunks that only load
 * when someone visits those routes. So ~38 kB raw / ~11 kB gzip off first paint -- a real but
 * modest 5%, not the "20%" that would have been a nicer sentence. Recorded as what it actually
 * is.
 *
 * This is the one place in E5.1 where a code-split earns itself. The rest of the surface is
 * deliberately NOT split: at this product's scale, splitting the driver's own four screens would
 * add a loading state on the path a driver takes under time pressure to save a few kilobytes,
 * which is the wrong trade in the opposite direction. The remaining 699 kB is React + router +
 * Radix + cmdk + supabase-js + lucide, i.e. the shared shell E5.0 already shipped -- reducing it
 * is a separate piece of work, not this epic's.
 */
const StatesGallery = lazy(() =>
  import('@/features/gallery/states-gallery').then((m) => ({ default: m.StatesGallery })),
)
const DriverStatesGallery = lazy(() =>
  import('@/features/driver/gallery/driver-gallery').then((m) => ({
    default: m.DriverStatesGallery,
  })),
)
const OpsStatesGallery = lazy(() =>
  import('@/features/ops/gallery/ops-gallery').then((m) => ({ default: m.OpsStatesGallery })),
)
const PlannerStatesGallery = lazy(() =>
  import('@/features/planner/gallery/planner-gallery').then((m) => ({
    default: m.PlannerStatesGallery,
  })),
)
const GateStatesGallery = lazy(() =>
  import('@/features/gate/gallery/gate-gallery').then((m) => ({ default: m.GateStatesGallery })),
)
const CarrierStatesGallery = lazy(() =>
  import('@/features/carrier/gallery/carrier-gallery').then((m) => ({
    default: m.CarrierStatesGallery,
  })),
)
const AdminStatesGallery = lazy(() =>
  import('@/features/admin/gallery/admin-gallery').then((m) => ({
    default: m.AdminStatesGallery,
  })),
)

/**
 * Application routes.
 *
 * **All six surfaces are now built** (E5.1-E5.6, 2026-08-31). E5.0's shared shell is still the
 * chrome most of them inherit, but there are no placeholder routes left -- `SurfacePlaceholder`
 * was deleted when the last three landed. Two surfaces deliberately mount OUTSIDE `<ShellRoute>`
 * and each says why at its own route: `/driver` (E5.1) and `/gate` (E5.4).
 *
 * Individual screens within a surface may still be flag-gated; each flag names its own blocking
 * issue in that surface's `lib/flags.ts`, and those comments are the authority on what is
 * actually reachable -- not this block.
 *
 * `/_states` renders all 32 shared-shell artboards; each surface has its own gallery beside it
 * (`/driver/_states`, `/ops/_states`, ...). None are linked from the app.
 *
 * ┌─────────────────────────────────────────────────────────────────────────────────────┐
 * │ AUTH (2026-09-01). The identity half of the old FIXTURE SEAM is GONE.                │
 * │                                                                                     │
 * │ Every surface route below is wrapped in `<RequireAuth>`, and the shell's `Identity`  │
 * │ now comes from `core/auth/auth-context.tsx`, mapped from a real `GET /auth/me` in    │
 * │ `core/auth/identity-mapping.ts`. `PLANNER_MULTI_ROLE`, `OPS_MANAGER`, `CARRIER` and  │
 * │ `ADMIN_IDENTITY` are no longer read by any route -- the fixtures survive only for    │
 * │ the `_states` galleries, which is what they were written for.                        │
 * │                                                                                     │
 * │ Guards are PRESENTATION, not authorisation: the server re-derives scope from the     │
 * │ token on every request (M15). See `core/auth/surface-access.ts`, whose table mirrors │
 * │ each backend `require_roles(...)` gate row by row.                                   │
 * │                                                                                     │
 * │ **The `_states` galleries stay UNGUARDED, deliberately.** They render fixture        │
 * │ artboards and make no authenticated call at all -- there is no real data behind them │
 * │ to protect, and they are the one tool for inspecting a surface's states without      │
 * │ holding that surface's role. Race suite 6 already drives `/gate/_states` as part of  │
 * │ its evidence.                                                                        │
 * └─────────────────────────────────────────────────────────────────────────────────────┘
 * ┌─────────────────────────────────────────────────────────────────────────────────────┐
 * │ CHROME SEAM — TODO(#52), the remaining half. One constant: `DEMO_CHROME` below.      │
 * │                                                                                     │
 * │ Connection state, last-sync, pending count, policy version, notifications and search │
 * │ results are still fixture-backed. Each needs its own server contract (`search_records`│
 * │ §7.5.8 for the palette, the notifications reads for the panel, a live-update          │
 * │ transport — issue #59 — for connection/last-sync), so they are a separate piece of   │
 * │ work from identity, not a leftover of it.                                            │
 * └─────────────────────────────────────────────────────────────────────────────────────┘
 */
export default function App() {
  return (
    <Routes>
      <Route path="/" element={<Navigate to="/signin" replace />} />

      <Route path="/signin" element={<SignInRoute />} />
      <Route path="/reset" element={<PasswordReset state="request" />} />
      <Route path="/reset/sent" element={<PasswordReset state="sent" />} />
      <Route path="/reset/new" element={<PasswordReset state="set-new" />} />
      <Route path="/reset/expired" element={<PasswordReset state="expired" />} />

      <Route path="/_states" element={<Lazy><StatesGallery /></Lazy>} />
      <Route path="/driver/_states" element={<Lazy><DriverStatesGallery /></Lazy>} />
      <Route path="/ops/_states" element={<Lazy><OpsStatesGallery /></Lazy>} />
      <Route path="/planner/_states" element={<Lazy><PlannerStatesGallery /></Lazy>} />
      <Route path="/gate/_states" element={<Lazy><GateStatesGallery /></Lazy>} />
      <Route path="/carrier/_states" element={<Lazy><CarrierStatesGallery /></Lazy>} />
      <Route path="/admin/_states" element={<Lazy><AdminStatesGallery /></Lazy>} />

      {/*
        E5.1 (#36) — driver chat. **Deliberately NOT inside `<ShellRoute>`.**
        `identity.ts` returns `rail: null`, `hasFacilityScope false` and `idlePolicyFor null`
        for DRIVER; `AppShell` exists to render exactly the chrome this surface does not have.
        `DriverShell` is the route root instead: it sets `data-density="comfortable"` once,
        renders the two-item bottom nav, and registers the service worker (the PWA is the
        driver's surface, not the desk surfaces' -- see driver-shell.tsx).

        `/driver/_states` is above this block on purpose: it must not mount the driver shell,
        because the gallery renders its own 390x844 frames and a bottom nav around them would
        be wrong.
      */}
      <Route
        path="/driver"
        element={
          <RequireAuth>
            <DriverShell />
          </RequireAuth>
        }
      >
        <Route index element={<DriverThreadList />} />
        <Route path="t/:threadId" element={<DriverConversation />} />
        <Route path="profile" element={<DriverProfile />} />
      </Route>

      {/* Settings is `comfortable` for every role (prompt 8), not the viewer's surface density. */}
      <Route
        path="/settings"
        element={
          <RequireAuth>
            <ShellRoute density="comfortable">
              <SettingsRoute />
            </ShellRoute>
          </RequireAuth>
        }
      />
      {/*
        E5.3 (#38) -- planner dock board. 10 of 30 designed screens ship unconditionally, 17 are
        honestly stubbed pending issues #60-66/#53/#49/#59 -- see `features/planner/lib/flags.ts`
        and `planner-console.tsx`'s own header comment. Only the block-dock group (states 16-18)
        has real backend wiring, since `get_planner_queue` (issue #60) -- the entry point for
        every other write on this surface -- does not exist yet.
      */}
      <Route path="/planner" element={<RequireAuth><PlannerRoute /></RequireAuth>} />
      {/*
        E5.2 (#37) -- ops exception console. 9 of 16 designed screens ship unconditionally; 3 are
        behind `sequencerProposalEnabled` (issue #54) and the rest are honestly stubbed pending
        #55/#56/#57/#58/#59 -- see `features/ops/lib/flags.ts` and `ops-console.tsx`'s own header
        comment. The rail/status-bar now render for the viewer's OWN ops role (any of
        OPERATIONS_EXECUTIVE / OPERATIONS_MANAGER / WAREHOUSE_PLANNER / TRANSPORT_MANAGER / ADMIN,
        mirroring `OPS_PORTAL_ROLES` -- see `core/auth/surface-access.ts`), not for a hard-coded
        `OPS_MANAGER` fixture.
      */}
      <Route path="/ops" element={<RequireAuth><OpsRoute /></RequireAuth>} />
      {/*
        E5.4 (#39) -- gate/yard kiosk. **Deliberately NOT inside `<ShellRoute>`**, like `/driver`.
        `stitch-prompts.md` and `mockup.html` both specify no icon rail, no top bar, no status bar,
        no facility switcher and no idle timeout on this surface. `GateRoute` sets its own
        `data-density="spacious"` root. Wrapping it would put a rail and a facility switcher on a
        mounted gate booth and override the density with the viewer's role default.

        Built against the facility-role model, not `GATE_OFFICER` -- nothing under `features/gate/`
        imports `core/auth/identity` or references `RoleName`, so issue #79 resolves either way
        without touching this route.
      */}
      <Route path="/gate" element={<RequireAuth><GateRoute /></RequireAuth>} />

      {/*
        E5.5 (#40) -- carrier portal, entirely read-only. All 9 screens ship. The HELD chip and
        its `Held` filter option are LIVE (`carrierHeldEnabled`, 2026-09-01 -- #85/#87 made the
        reads hold-aware and the filter run on the computed promise_state). `SHOWN` was removed
        outright rather than gated: it has no persisted counterpart in any flag state, so what it
        needs is an owner design decision, not engineering -- recorded in
        `features/carrier/lib/flags.ts`. `/carrier/*` splat because this surface has two screens:
        dashboard and shipment detail.
      */}
      <Route path="/carrier/*" element={<RequireAuth><CarrierRoute /></RequireAuth>} />

      {/*
        E5.6 (#41) -- admin console. The Policy tab (Screens 8/10) is now BUILT and live:
        `GET /admin/policy/active` (#75) supplies the baseline, so the editor renders nothing until
        the server answers and cannot display an invented coefficient. `adminRemovalImpactEnabled`
        and `adminPolicyEditorEnabled` are on; the rest stay gated -- see
        `features/admin/lib/flags.ts` for each one's real blocker. Note Screen 6 is NOT waiting on
        backend any more (#70/#71 are resolved); it waits on missing *design* -- three live rule
        types have no field set, and `DOCK_PIN`, the only two-field type, has no live analog.
      */}
      <Route path="/admin" element={<RequireAuth><AdminRoute /></RequireAuth>} />

      <Route path="*" element={<RequireAuth><NotFoundRoute /></RequireAuth>} />
    </Routes>
  )
}

/** Suspense boundary for the two lazy galleries. A plain sentence, not a spinner: these are
 *  internal verification pages and `components.md` section 13's skeleton rule is about states a
 *  real user sees. */
function Lazy({ children }: { children: React.ReactNode }) {
  return <Suspense fallback={<p className="p-6 text-body">Loading artboards…</p>}>{children}</Suspense>
}

/**
 * Real sign-in. **This route used to be the security hole**: `onSubmit={() => navigate('/planner')}`
 * accepted any string in either box and dropped the visitor on the planner console with a fixture
 * identity in the shell.
 *
 * ## What happens now
 *
 *   1. `signIn()` -> `supabase.auth.signInWithPassword` (the password grant).
 *   2. On success, supabase-js persists the session and emits `SIGNED_IN`; `AuthProvider` picks it
 *      up and reads the real identity from `GET /auth/me`.
 *   3. The redirect below fires from that identity -- never from the form. This is why the button
 *      stays busy until `status === 'authenticated'`: the landing surface is not known until the
 *      server has said who this is.
 *
 * ## Where it lands, and why not `roleToPortal`
 *
 * `landingPathFor` (via `homePathFor`) is the authority: it derives from `identity.ts`'s
 * `RAIL_BY_ROLE`, which derives from `auth-and-scoping.md`'s own "Role landing" table and covers
 * all six surfaces. `core/auth/supabase.ts`'s `roleToPortal` only knows two portals and predates
 * that model -- using it would send a gate officer and an admin both to `/ops`.
 *
 * The attempted location wins over the role's home when the role may actually open it, so a driver
 * who followed a link to `/driver/t/THREAD`, got bounced to sign-in, and signed in, lands on that
 * thread. `canAccess` is checked first so a *stale* attempted location belonging to another role
 * (a shared machine, a bookmarked `/planner`) can never bounce them straight back out again.
 *
 * ## Error branching is on `code`, never on a message
 *
 * `supabase.com/docs/guides/auth/debugging/error-codes` (checked 2026-09-01): *"Always use
 * `error.code` and `error.name` to identify errors, not string matching on error messages."*
 * `AuthApiError` carries `code` and `status` (`@supabase/auth-js@2.112.2`, `lib/errors.js:53-60`).
 *
 *  - `invalid_credentials` (and any other server-side refusal) -> the screen's own anti-enumeration
 *    copy, identical for a wrong address and a wrong password, with neither field marked.
 *  - `over_request_rate_limit` / HTTP 429 -> the rate-limited state, whose "Forgotten your
 *    password?" link stays live.
 *  - `AuthRetryableFetchError` -> a network sentence. Deliberately NOT the credential copy: telling
 *    a driver on a roadside that their details don't match when the request never left the phone
 *    burns their attempts against a real rate limit for a fault that is not theirs.
 */
function SignInRoute() {
  const { status, identity } = useAuth()
  const location = useLocation()
  const [state, setState] = useState<SignInState>('at-rest')
  const [errorMessage, setErrorMessage] = useState<string | undefined>(undefined)
  const [submitting, setSubmitting] = useState(false)

  // `location.state.from` is set by `RequireAuth` when it bounced an unauthenticated visitor.
  const from = (location.state as { from?: { pathname?: string } } | null)?.from?.pathname

  if (status === 'authenticated' && identity) {
    const home = homePathFor(identity.activeRole)
    const target = from && canAccess(identity.activeRole, from) ? from : home
    return <Navigate to={target} replace />
  }

  // `submitting` deliberately stays true across the whole of: password grant -> `SIGNED_IN` ->
  // `/auth/me` -> redirect. Clearing it when the grant returns would re-enable the button while the
  // destination is still unknown, inviting a second grant request against a real rate limit. It is
  // only cleared on a failure path, where there IS something for the user to do.
  return (
    <SignIn
      state={state}
      pending={submitting}
      errorMessage={errorMessage}
      onSubmit={(identifier, password) => {
        setSubmitting(true)
        setState('at-rest')
        setErrorMessage(undefined)
        void (async () => {
          try {
            const { error } = await signIn(identifier, password)
            if (error) {
              setSubmitting(false)
              if (isAuthRetryableFetchError(error)) {
                setState('error')
                setErrorMessage('Could not reach SetuHaul. Check your connection and try again.')
              } else if (error.code === 'over_request_rate_limit' || error.status === 429) {
                setState('rate-limited')
              } else {
                setState('error')
                setErrorMessage(undefined)
              }
              return
            }
            // Success: leave `submitting` true. `AuthProvider` is now reading the identity, and the
            // `<Navigate>` above fires as soon as it lands.
          } catch (err) {
            // `signIn` throws (rather than returning `error`) only when the Supabase client is not
            // configured at all -- a deployment fault, not a credential one, so say so.
            setSubmitting(false)
            setState('error')
            setErrorMessage(
              err instanceof Error && err.message.includes('not configured')
                ? 'Sign-in is not configured on this deployment.'
                : 'Could not reach SetuHaul. Check your connection and try again.',
            )
          }
        })()
      }}
    />
  )
}

/** 404 inside the shell. `backHref` is the viewer's OWN home rather than a hard-coded `/planner` --
 *  sending a driver "back" to a planner console they cannot open was the old behaviour. */
function NotFoundRoute() {
  const identity = useIdentity()
  return (
    <ShellRoute>
      <NotFound backHref={homePathFor(identity.activeRole)} />
    </ShellRoute>
  )
}

/**
 * CHROME SEAM — TODO(#52). **Chrome only: there is no identity in here any more.**
 * Held in one place so a future implementer replaces one constant rather than hunting
 * fixture imports across six files.  See the block comment at the top of this file.
 */
const DEMO_CHROME: ShellChrome = {
  connection: 'connected',
  lastSync: '09:52:14',
  pendingCount: 14,
  policyVersion: 'v12',
  notificationsState: 'items',
  notifications: NOTIFICATIONS,
  unreadCount: 3,
  searchResults: SEARCH_RESULTS,
  recentSearches: RECENT_SEARCHES,
}

/**
 * The shared shell wrapper.
 *
 * **No `identity` prop any more.** It reads the real one from `AuthProvider`, which is safe
 * precisely because every route that renders a `ShellRoute` sits inside `<RequireAuth>` -- and
 * `useIdentity()` throws rather than returning null if that ever stops being true. Passing an
 * identity down from each route was how four different fixtures ended up hard-coded in this file.
 */
function ShellRoute({
  children,
  density,
}: {
  children: React.ReactNode
  density?: Density
}) {
  const identity = useIdentity()
  const { signOutLocal, signOutEverywhere, setActiveFacility } = useAuth()
  const navigate = useNavigate()
  // CHROME SEAM — TODO(#52): stands in for the debounced `search_records` call the surface
  // epics will wire here.  Deliberately a state hand-off rather than filtering inside
  // AppShell: the shell must never decide what a user may see, because scope is
  // server-derived (M15).
  const [results, setResults] = useState(SEARCH_RESULTS)

  return (
    <AppShell
      identity={identity}
      density={density}
      chrome={{ ...DEMO_CHROME, searchResults: results }}
      /**
       * Facility switching, issue #99.1. **This was `() => {}`** -- a real popover with a real
       * option list whose selection went nowhere on both desk consoles.
       *
       * The handler is `AuthProvider`'s, not a local `useState`, for one load-bearing reason:
       * the shell renders the switcher from `identity`, and the surfaces read their scope from
       * the same `identity`. One writer keeps those two from disagreeing, which is precisely the
       * failure a shell-local state would reintroduce -- a switcher reading "Gurugram" over a
       * board still showing Jaipur.
       *
       * The id is validated against the server-supplied `identity.facilities` inside the provider
       * before it is applied (M15, `core/auth/active-facility.ts`), and the server re-derives
       * scope again on every request regardless (`repositories/scope.py::resolve_facility_scope`).
       * Nothing here grants reach.
       */
      onFacilityChange={setActiveFacility}
      onSearchQueryChange={(q) => {
        const needle = q.trim().toLowerCase()
        setResults(
          needle === ''
            ? SEARCH_RESULTS
            : SEARCH_RESULTS.filter(
                (r) =>
                  r.identifier.toLowerCase().includes(needle) ||
                  r.meta.toLowerCase().includes(needle),
              ),
        )
      }}
      /**
       * Sign-out was a REAL BUG until 2026-09-01: this handler only navigated, so the Supabase
       * session survived and the next visit to any surface walked straight back in. It now revokes
       * the session first (single-device -- `signOut({ scope: 'local' })`, see
       * `core/auth/supabase.ts` for why that argument is not optional), and only then navigates.
       *
       * The navigate is belt-and-braces: clearing the session already makes `RequireAuth`
       * redirect. It is kept so the transition is immediate rather than dependent on a state
       * round-trip, and `replace` keeps the signed-out surface out of the back stack.
       */
      onSignOut={() => {
        void signOutLocal().then(() => navigate('/signin', { replace: true }))
      }}
      /**
       * "Sign out everywhere", issue #99.2. **This prop was never passed** -- the account menu's
       * confirmation expanded in place and its commit button did nothing on every desk surface.
       *
       * `signOutEverywhere` calls `POST /api/v1/sign-out-everywhere` (E3.5) *before* clearing the
       * local session, because the endpoint forwards this caller's own bearer token; see the
       * provider for why that ordering is not incidental.
       *
       * A failure does NOT sign this device out and says so, rather than silently degrading into
       * an ordinary sign-out. The toast is the only surface available: `UserMenu` is specified as
       * one button with no error slot ("no modal, no separate dialog, no active-sessions list"),
       * and inventing an error row inside the popover would be redesigning a specified component
       * to report a transport fault.
       */
      onSignOutEverywhere={() => {
        void signOutEverywhere()
          .then(() => navigate('/signin', { replace: true }))
          .catch((err: unknown) => {
            toast.error(
              `${formatUserFriendlyError(err)} You are still signed in on this device and on your other devices.`,
            )
          })
      }}
    >
      {children}
    </AppShell>
  )
}

function SettingsRoute() {
  const identity = useIdentity()
  return <SettingsPage identity={identity} />
}

/**
 * E5.2 (#37). The rail/status-bar/density now resolve from the viewer's OWN role rather than from
 * a hard-coded `OPERATIONS_MANAGER` fixture -- which means an `OPERATIONS_EXECUTIVE` on this
 * console finally sees their own name and facility instead of "Priya Nair, All facilities".
 * `canSelectAllFacilities` is derived in `identity-mapping.ts` from the server's own reported
 * scope (`/auth/me`'s `scope.type`), per U91.
 *
 * `facilityId` (issue #99.1) is the viewer's ACTIVE facility, so the escalation queue re-reads
 * when the switcher changes. `facilityIdForReads` maps the "All facilities" sentinel to `null`,
 * which `fetchEscalationQueue` turns into an omitted `facility_id` -- §7.5.5's own "omitted means
 * every facility in scope", and the only form the server will honour for a global-read persona.
 */
function OpsRoute() {
  const identity = useIdentity()
  return (
    <ShellRoute>
      <OpsConsole facilityId={facilityIdForReads(identity.activeFacilityId)} />
    </ShellRoute>
  )
}

/**
 * E5.3 (#38). `facilityId` is the viewer's real active facility, from the server-derived identity.
 * It was `PLANNER_MULTI_ROLE.activeFacilityId` -- a hard-coded `FAC-JAI-01` -- so every planner,
 * whichever facility they actually belong to, was pointing this console's reads at Jaipur.
 * The empty-string fallback is unchanged: `PlannerConsole` already treats it as "no facility yet".
 *
 * Since issue #99.1 this follows the facility switcher too -- `PlannerConsole` already passes it
 * straight into `fetchPlannerQueue` / `fetchDockBoard` / the block-dock dock list, so changing it
 * re-scopes all three with no further wiring. `facilityIdForReads` cannot return the "All
 * facilities" sentinel; a planner is not a global-read persona, so that option is never offered,
 * and if it ever were, `''` here means "no facility yet" rather than "every facility".
 */
function PlannerRoute() {
  const identity = useIdentity()
  return (
    <ShellRoute>
      <PlannerConsole facilityId={facilityIdForReads(identity.activeFacilityId) ?? ''} />
    </ShellRoute>
  )
}

/**
 * E5.5 (#40). A real carrier identity has `facilities: []` (nothing in `user_scopes` of type
 * FACILITY for a `CARRIER` account), so `hasFacilityScope('TRANSPORT_MANAGER')` still resolves
 * false and the facility switcher and status-bar facility/policy fields stay absent from the DOM
 * rather than disabled (U83) -- the same property the `CARRIER` fixture used to encode by hand.
 */
function CarrierRoute() {
  const identity = useIdentity()
  return (
    <ShellRoute>
      <CarrierPortal identity={identity} />
    </ShellRoute>
  )
}

/**
 * E5.6 (#41). `currentUserId` is now the signed-in admin's real `user_id`, which matters for
 * correctness and not only for chrome: `AdminConsole` uses it to keep an admin from removing their
 * own account, and a fixture id could never match a real row, so that guard was inert.
 *
 * **Facility-switch boundary, stated rather than left to be discovered (issue #99.1):** an admin
 * DOES get the switcher (`hasFacilityScope('ADMIN')` is true) and, being a global-read persona,
 * gets its "All facilities" row -- but **no read on this console takes a `facility_id`**. Every
 * admin tool is scoped per action instead (a user's scope, a rule's facility, a policy version),
 * which `06-admin-console/screens.md` §1 states outright: "admin actions span facilities by
 * nature". So switching here changes the rail stripe and the status bar and nothing else, and
 * that is correct, not a missing hookup. `AdminConsole` is deliberately not given a `facilityId`
 * prop it would have nowhere to send.
 */
function AdminRoute() {
  const identity = useIdentity()
  return (
    <ShellRoute>
      <AdminConsole currentUserId={identity.userId} />
    </ShellRoute>
  )
}
