import { useCallback, useEffect, useMemo, useState, type ReactNode } from 'react'

import {
  densityFor,
  railDestinationFor,
  type Density,
  type Identity,
  type RoleGrant,
} from '@/core/auth/identity'
import { IconRail } from '@/components/shell/icon-rail'
import { StatusBar, type ConnectionState } from '@/components/shell/status-bar'
import { TopBar } from '@/components/shell/top-bar'
import {
  SearchPalette,
  type RecentSearch,
  type SearchResult,
} from '@/components/shell/search-palette'
import type {
  NotificationItem,
  NotificationsState,
} from '@/components/shell/notifications-panel'
import { RegionErrorBoundary } from '@/components/states/region-states'

export type ShellChrome = {
  connection: ConnectionState
  lastSync: string
  pendingCount: number
  policyVersion: string
  notificationsState: NotificationsState
  notifications: NotificationItem[]
  unreadCount: number
  searchResults: SearchResult[]
  recentSearches: RecentSearch[]
}

/**
 * The persistent shell.  Rail, top bar and status bar **never unmount** on navigation (U71)
 * -- only the content region between them changes.  What loads is data, not the shell.
 *
 * Density is set ONCE here, at the shell root, from the role's surface
 * (spacing-and-layout.md).  Never per component, and never as a user preference in v1.
 *
 * The content region carries its own error boundary.  A crash in one region must not take
 * the others down.
 */
export function AppShell({
  identity,
  chrome,
  children,
  density: densityOverride,
  onFacilityChange,
  onSearchQueryChange,
  onSwitchRole,
  onSignOut,
  onSignOutEverywhere,
}: {
  identity: Identity
  chrome: ShellChrome
  children: ReactNode
  /**
   * Per-route density override.  Density is normally derived from the ROLE's surface
   * (spacing-and-layout.md's table maps densities to operational surfaces), but a few routes
   * belong to no operational surface: Settings is specified as `comfortable` in prompt 8
   * regardless of who is looking at it, so a planner on `compact` still gets a comfortable
   * settings page.  This is the "set once per ROUTE at the shell root" half of the rule.
   */
  density?: Density
  onFacilityChange: (facilityId: string) => void
  /**
   * Fired on every keystroke in the palette.  The shell owns the query STRING but never the
   * results: search is `search_records` (section 7.5.8), a server call whose scope is derived
   * from the caller's token -- deriving or filtering results client-side would be the client
   * deciding what a user may see, which auth-and-scoping.md's governing rule forbids.
   * Callers are expected to debounce and to call the tool.
   */
  onSearchQueryChange?: (query: string) => void
  onSwitchRole?: (grant: RoleGrant) => void
  onSignOut?: () => void
  onSignOutEverywhere?: () => void
}) {
  const [searchOpen, setSearchOpen] = useState(false)
  const [query, setQuery] = useState('')

  const destination = railDestinationFor(identity.activeRole)
  const density = densityOverride ?? densityFor(destination?.surface ?? 'driver')

  const activeFacility = useMemo(
    () => identity.facilities.find((f) => f.id === identity.activeFacilityId) ?? null,
    [identity.facilities, identity.activeFacilityId],
  )

  // Cmd/Ctrl+K opens the palette.  Registered on the shell rather than the top bar so it
  // works regardless of where focus is, which is the point of a command palette.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key.toLowerCase() === 'k' && (e.metaKey || e.ctrlKey)) {
        e.preventDefault()
        setSearchOpen((v) => !v)
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [])

  /** Changing facility clears row focus and any pending selection, so a stale selection can
   *  never be acted on in a new context (components.md section 7). */
  const handleFacilityChange = useCallback(
    (facilityId: string) => {
      if (document.activeElement instanceof HTMLElement) document.activeElement.blur()
      onFacilityChange(facilityId)
    },
    [onFacilityChange],
  )

  return (
    <div
      data-density={density}
      className="flex h-dvh flex-col bg-background text-foreground"
      // index.html sets viewport-fit=cover; without these the notch/home-indicator just
      // covers content instead of the layout accounting for it.  Cheap here, and the
      // driver PWA and the gate kiosk in landscape both land on it.
      style={{
        paddingLeft: 'env(safe-area-inset-left)',
        paddingRight: 'env(safe-area-inset-right)',
        paddingBottom: 'env(safe-area-inset-bottom)',
      }}
    >
      <a
        href="#content"
        className="absolute -left-[9999px] top-2 z-tooltip rounded-md border border-border bg-card px-4 py-2.5 text-body font-medium focus:left-4"
      >
        Skip to content
      </a>

      <div className="flex min-h-0 flex-1">
        <IconRail role={identity.activeRole} activeFacility={activeFacility} />

        <div className="flex min-w-0 flex-1 flex-col">
          <TopBar
            identity={identity}
            notificationsState={chrome.notificationsState}
            notifications={chrome.notifications}
            unreadCount={chrome.unreadCount}
            onOpenSearch={() => setSearchOpen(true)}
            onFacilityChange={handleFacilityChange}
            onSwitchRole={onSwitchRole}
            onSignOut={onSignOut}
            onSignOutEverywhere={onSignOutEverywhere}
          />

          <main id="content" tabIndex={-1} className="min-h-0 flex-1 overflow-auto p-(--content-p)">
            <RegionErrorBoundary regionName="content">{children}</RegionErrorBoundary>
          </main>
        </div>
      </div>

      <StatusBar
        role={identity.activeRole}
        connection={chrome.connection}
        lastSync={chrome.lastSync}
        facilityName={activeFacility?.name ?? null}
        pendingCount={chrome.pendingCount}
        policyVersion={chrome.policyVersion}
      />

      <SearchPalette
        open={searchOpen}
        onOpenChange={setSearchOpen}
        query={query}
        onQueryChange={(q) => {
          setQuery(q)
          onSearchQueryChange?.(q)
        }}
        results={chrome.searchResults}
        recent={chrome.recentSearches}
        scopeLabel={activeFacility ? `${activeFacility.name} only` : 'Your scope only'}
      />
    </div>
  )
}
