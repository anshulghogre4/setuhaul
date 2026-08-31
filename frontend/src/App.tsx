import { Suspense, lazy, useState } from 'react'
import { Navigate, Route, Routes, useNavigate } from 'react-router-dom'

import { AppShell, type ShellChrome } from '@/components/shell/app-shell'
import type { Density, Identity } from '@/core/auth/identity'
import { NotFound } from '@/components/states/region-states'
import { PasswordReset } from '@/features/auth/password-reset'
import { SignIn } from '@/features/auth/sign-in'
import {
  CARRIER,
  NOTIFICATIONS,
  OPS_MANAGER,
  PLANNER_MULTI_ROLE,
  RECENT_SEARCHES,
  SEARCH_RESULTS,
} from '@/features/gallery/fixtures'
import { SettingsPage } from '@/features/settings/settings-page'
import { DriverShell } from '@/features/driver/driver-shell'
import { DriverConversation } from '@/features/driver/screens/conversation'
import { DriverProfile } from '@/features/driver/screens/profile'
import { DriverThreadList } from '@/features/driver/screens/thread-list'
import { OpsConsole } from '@/features/ops/ops-console'
import { PlannerConsole } from '@/features/planner/planner-console'
import { ADMIN_IDENTITY, AdminConsole } from '@/features/admin'
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
 * │ FIXTURE SEAM — TODO(#52). Grep for `FIXTURE SEAM` to find every part of it.          │
 * │                                                                                     │
 * │ The shell is driven entirely by an `Identity` object the server is meant to supply.  │
 * │ `GET /api/v1/auth/me` currently returns a single `role_name`, NOT a multi-role       │
 * │ `grants[]` list, so the role picker has no server contract to sit on.  Rather than   │
 * │ invent an endpoint, the shell renders from a fixture behind exactly two named        │
 * │ constants, both in this file:                                                        │
 * │                                                                                     │
 * │   1. `PLANNER_MULTI_ROLE`  (imported from features/gallery/fixtures)  -> `Identity`  │
 * │   2. `DEMO_CHROME`         (defined below)                            -> `ShellChrome`│
 * │                                                                                     │
 * │ TO REPLACE: fetch the real identity + chrome, delete both constants and the          │
 * │ `features/gallery/fixtures` import, and pass the fetched values to `<AppShell>`.     │
 * │ Nothing else in `components/shell/**` reads a fixture — every one of those components │
 * │ is already fully prop-driven, so no component needs changing when #52 lands.         │
 * │ Verified by grep: `features/gallery/fixtures` is imported by this file and by the    │
 * │ states gallery only.                                                                 │
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
      <Route path="/driver" element={<DriverShell />}>
        <Route index element={<DriverThreadList />} />
        <Route path="t/:threadId" element={<DriverConversation />} />
        <Route path="profile" element={<DriverProfile />} />
      </Route>

      {/* Settings is `comfortable` for every role (prompt 8), not the viewer's surface density. */}
      <Route path="/settings" element={<ShellRoute density="comfortable"><SettingsRoute /></ShellRoute>} />
      {/*
        E5.3 (#38) -- planner dock board. 10 of 30 designed screens ship unconditionally, 17 are
        honestly stubbed pending issues #60-66/#53/#49/#59 -- see `features/planner/lib/flags.ts`
        and `planner-console.tsx`'s own header comment. Only the block-dock group (states 16-18)
        has real backend wiring, since `get_planner_queue` (issue #60) -- the entry point for
        every other write on this surface -- does not exist yet.
      */}
      <Route path="/planner" element={<PlannerRoute />} />
      {/*
        E5.2 (#37) -- ops exception console. 9 of 16 designed screens ship unconditionally; 3 are
        behind `sequencerProposalEnabled` (issue #54) and the rest are honestly stubbed pending
        #55/#56/#57/#58/#59 -- see `features/ops/lib/flags.ts` and `ops-console.tsx`'s own header
        comment. Uses `OPS_MANAGER` (not `PLANNER_MULTI_ROLE`) so the rail/status-bar render for
        the actual OPERATIONS_MANAGER role this surface is built for -- same FIXTURE SEAM
        (TODO #52) as every other route here, just a different fixture identity.
      */}
      <Route path="/ops" element={<OpsRoute />} />
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
      <Route path="/gate" element={<GateRoute />} />

      {/*
        E5.5 (#40) -- carrier portal, entirely read-only. All 9 screens ship. The HELD chip and
        its `Held` filter option are LIVE (`carrierHeldEnabled`, 2026-09-01 -- #85/#87 made the
        reads hold-aware and the filter run on the computed promise_state). `SHOWN` was removed
        outright rather than gated: it has no persisted counterpart in any flag state, so what it
        needs is an owner design decision, not engineering -- recorded in
        `features/carrier/lib/flags.ts`. `/carrier/*` splat because this surface has two screens:
        dashboard and shipment detail.
      */}
      <Route path="/carrier/*" element={<CarrierRoute />} />

      {/*
        E5.6 (#41) -- admin console. The Policy tab (Screens 8/10) is now BUILT and live:
        `GET /admin/policy/active` (#75) supplies the baseline, so the editor renders nothing until
        the server answers and cannot display an invented coefficient. `adminRemovalImpactEnabled`
        and `adminPolicyEditorEnabled` are on; the rest stay gated -- see
        `features/admin/lib/flags.ts` for each one's real blocker. Note Screen 6 is NOT waiting on
        backend any more (#70/#71 are resolved); it waits on missing *design* -- three live rule
        types have no field set, and `DOCK_PIN`, the only two-field type, has no live analog.
      */}
      <Route path="/admin" element={<AdminRoute />} />

      <Route path="*" element={<ShellRoute><NotFound backHref="/planner" /></ShellRoute>} />
    </Routes>
  )
}

/** Suspense boundary for the two lazy galleries. A plain sentence, not a spinner: these are
 *  internal verification pages and `components.md` section 13's skeleton rule is about states a
 *  real user sees. */
function Lazy({ children }: { children: React.ReactNode }) {
  return <Suspense fallback={<p className="p-6 text-body">Loading artboards…</p>}>{children}</Suspense>
}

function SignInRoute() {
  const navigate = useNavigate()
  return <SignIn onSubmit={() => navigate('/planner')} />
}

/**
 * FIXTURE SEAM — TODO(#52).  Chrome values that will come from the server.
 * Held in one place so a future implementer replaces two constants rather than hunting
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

function ShellRoute({
  children,
  density,
  identity = PLANNER_MULTI_ROLE,
}: {
  children: React.ReactNode
  density?: Density
  /** FIXTURE SEAM — TODO(#52). Defaults to the multi-role planner fixture every other
   *  still-placeholder route uses; `OpsRoute` below passes `OPS_MANAGER` instead so E5.2's real
   *  console renders the rail/status-bar for the role it is actually built for. */
  identity?: Identity
}) {
  const navigate = useNavigate()
  // FIXTURE SEAM — TODO(#52): stands in for the debounced `search_records` call the surface
  // epics will wire here.  Deliberately a state hand-off rather than filtering inside
  // AppShell: the shell must never decide what a user may see, because scope is
  // server-derived (M15).
  const [results, setResults] = useState(SEARCH_RESULTS)

  return (
    <AppShell
      identity={identity}
      density={density}
      chrome={{ ...DEMO_CHROME, searchResults: results }}
      onFacilityChange={() => {}}
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
      onSignOut={() => navigate('/signin')}
    >
      {children}
    </AppShell>
  )
}

function SettingsRoute() {
  // FIXTURE SEAM — TODO(#52)
  return <SettingsPage identity={PLANNER_MULTI_ROLE} />
}

/**
 * E5.2 (#37). `OPS_MANAGER` rather than `PLANNER_MULTI_ROLE` so `railDestinationFor` /
 * `densityFor` resolve for `OPERATIONS_MANAGER` (rail = "Exceptions", density = compact) instead
 * of `WAREHOUSE_PLANNER`. `activeFacilityId: null` matches U91's "All facilities" default for the
 * one role that can select it (`canSelectAllFacilities: true` on this fixture already).
 */
const OPS_IDENTITY: Identity = { ...OPS_MANAGER, activeFacilityId: null }

function OpsRoute() {
  return (
    <ShellRoute identity={OPS_IDENTITY}>
      <OpsConsole />
    </ShellRoute>
  )
}

/**
 * E5.3 (#38). Uses the default `PLANNER_MULTI_ROLE` fixture (`ShellRoute`'s own default identity
 * prop) rather than a dedicated constant -- unlike ops, this surface's rail/density/facility-scope
 * derivation already resolves correctly for `WAREHOUSE_PLANNER` from that fixture as-is
 * (`screens.md` section 1: single-facility, not "All facilities" -- `PLANNER_MULTI_ROLE.
 * canSelectAllFacilities` is already `false`). Same FIXTURE SEAM (TODO #52) as every other route.
 */
function PlannerRoute() {
  return (
    <ShellRoute>
      <PlannerConsole facilityId={PLANNER_MULTI_ROLE.activeFacilityId ?? ''} />
    </ShellRoute>
  )
}

/**
 * E5.5 (#40). `CARRIER` rather than `PLANNER_MULTI_ROLE`: this fixture is the only one with
 * `facilities: []`, `activeFacilityId: null` and a real `carrierId`, so `hasFacilityScope`
 * resolves false and the facility switcher and status-bar facility/policy fields are absent from
 * the DOM rather than disabled (U83). Same FIXTURE SEAM (TODO #52) as every other route.
 */
function CarrierRoute() {
  return (
    <ShellRoute identity={CARRIER}>
      <CarrierPortal identity={CARRIER} />
    </ShellRoute>
  )
}

/**
 * E5.6 (#41). `ADMIN_IDENTITY` lives in `features/admin/admin-identity.ts` rather than
 * `features/gallery/fixtures.ts` because that shared file was being read by two concurrent
 * surface builds when this was written. Same FIXTURE SEAM (TODO #52) as every other route.
 */
function AdminRoute() {
  return (
    <ShellRoute identity={ADMIN_IDENTITY}>
      <AdminConsole currentUserId={ADMIN_IDENTITY.userId} />
    </ShellRoute>
  )
}
