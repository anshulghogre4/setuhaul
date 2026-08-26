import { useState } from 'react'
import { Navigate, Route, Routes, useNavigate } from 'react-router-dom'

import { AppShell, type ShellChrome } from '@/components/shell/app-shell'
import type { Density } from '@/core/auth/identity'
import { NotFound } from '@/components/states/region-states'
import { PasswordReset } from '@/features/auth/password-reset'
import { SignIn } from '@/features/auth/sign-in'
import { StatesGallery } from '@/features/gallery/states-gallery'
import {
  NOTIFICATIONS,
  PLANNER_MULTI_ROLE,
  RECENT_SEARCHES,
  SEARCH_RESULTS,
} from '@/features/gallery/fixtures'
import { SettingsPage } from '@/features/settings/settings-page'
import { EmptyState } from '@/shared/ui/empty-state'
import { ChartGantt } from 'lucide-react'

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

      <Route path="/_states" element={<StatesGallery />} />

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
