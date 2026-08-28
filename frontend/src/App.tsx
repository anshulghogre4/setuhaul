import { Suspense, lazy, useState } from 'react'
import { Navigate, Route, Routes, useNavigate } from 'react-router-dom'

import { AppShell, type ShellChrome } from '@/components/shell/app-shell'
import type { Density } from '@/core/auth/identity'
import { NotFound } from '@/components/states/region-states'
import { PasswordReset } from '@/features/auth/password-reset'
import { SignIn } from '@/features/auth/sign-in'
import {
  NOTIFICATIONS,
  PLANNER_MULTI_ROLE,
  RECENT_SEARCHES,
  SEARCH_RESULTS,
} from '@/features/gallery/fixtures'
import { SettingsPage } from '@/features/settings/settings-page'
import { DriverShell } from '@/features/driver/driver-shell'
import { DriverConversation } from '@/features/driver/screens/conversation'
import { DriverProfile } from '@/features/driver/screens/profile'
import { DriverThreadList } from '@/features/driver/screens/thread-list'
import { EmptyState } from '@/shared/ui/empty-state'
import { ChartGantt } from 'lucide-react'

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

/**
 * E5.0 routes.
 *
 * The six surfaces themselves are E5.1-E5.6 and are deliberately NOT built here -- each
 * surface route below mounts the real shell around a placeholder, which is the actual
 * deliverable of this epic: the chrome every surface inherits, proven to mount, scope and
 * theme correctly before six teams build inside it.
 *
 * `/_states` renders all 32 artboards for verification.  Not linked from the app.
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
      <Route path="/planner" element={<ShellRoute><SurfacePlaceholder name="Dock Command" /></ShellRoute>} />
      <Route path="/ops" element={<ShellRoute><SurfacePlaceholder name="Exceptions" /></ShellRoute>} />
      <Route path="/gate" element={<ShellRoute><SurfacePlaceholder name="Yard" /></ShellRoute>} />
      <Route path="/carrier" element={<ShellRoute><SurfacePlaceholder name="Fleet" /></ShellRoute>} />
      <Route path="/admin" element={<ShellRoute><SurfacePlaceholder name="Admin" /></ShellRoute>} />

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

function ShellRoute({ children, density }: { children: React.ReactNode; density?: Density }) {
  const navigate = useNavigate()
  // FIXTURE SEAM — TODO(#52): stands in for the debounced `search_records` call the surface
  // epics will wire here.  Deliberately a state hand-off rather than filtering inside
  // AppShell: the shell must never decide what a user may see, because scope is
  // server-derived (M15).
  const [results, setResults] = useState(SEARCH_RESULTS)

  return (
    <AppShell
      // FIXTURE SEAM — TODO(#52): replace with the identity fetched from /auth/me.
      identity={PLANNER_MULTI_ROLE}
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

/** Placeholder for a surface owned by a later epic.  Not an empty state pretending to be
 *  one: it says plainly that the surface is not built, rather than implying no data. */
function SurfacePlaceholder({ name }: { name: string }) {
  return (
    <EmptyState
      icon={ChartGantt}
      title={`${name} is not built yet.`}
      body="E5.0 delivers the shell this surface will mount inside. The surface itself is a later epic."
    />
  )
}
