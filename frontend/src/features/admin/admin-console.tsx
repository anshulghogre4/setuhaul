import {
  useEffect,
  useId,
  useRef,
  useState,
  type KeyboardEvent as ReactKeyboardEvent,
  type ReactNode,
  type Ref,
} from 'react'

import { AuditTab } from './components/audit-tab'
import { FacilityRulesTab } from './components/facility-rules-tab'
import { PolicyTab } from './components/policy-tab'
import { UsersTab } from './components/users-tab'
import { RegionErrorBoundary } from '@/components/states/region-states'

type TabId = 'users' | 'rules' | 'policy' | 'audit'

const TABS: Array<{ id: TabId; label: string }> = [
  { id: 'users', label: 'Users' },
  { id: 'rules', label: 'Facility Rules' },
  { id: 'policy', label: 'Policy' },
  { id: 'audit', label: 'Audit' },
]

/**
 * Screen 1 — the admin console shell. **🟢, no backend dependency** (`implementation-spec.md` §3).
 *
 * Four TABS, never routes: `identity.ts:85`'s own comment names them ("Admin: Users / Rules /
 * Policy / Audit are four TABS"), matching ops's and planner's same reasoning. Users opens by
 * default (`screens.md`'s screen map: "no default preference stated — first tab, Users, opens by
 * default").
 *
 * **`data-density="comfortable"` is already set by the shell** (`identity.ts`'s
 * `densityFor('admin')`), so it is not repeated here — the same note E5.2's `OpsConsole` and
 * E5.3's `PlannerConsole` each make for their own surface.
 *
 * ## Tab wiring, and why it is built this way
 *
 * `implementation-spec.md` §5.3's R23/R26/R27 were three separate structural corruptions of the
 * mockup's tab↔tabpanel wiring — hand-written `id` / `aria-controls` / `aria-labelledby` strings
 * that pointed at the wrong element, or at no element, across four artboards, one of which was
 * only found because fixing another collided with it. That whole class of defect is **structurally
 * impossible here**: every tab and every panel takes its id from one `useId()` per tab, so a tab
 * and its panel cannot disagree without the same variable being wrong in both places.
 *
 * Four separate panels (one per tab, `hidden` when inactive) rather than the mockup's single
 * reused panel that all four tabs point `aria-controls` at — the W3C ARIA Authoring Practices
 * tabs pattern specifies each tab's `aria-controls` referencing "its associated tabpanel element",
 * and separate panels also mean each tab's own state survives a tab switch instead of remounting.
 * (W3C APG, Tabs pattern, checked 2026-08-29.)
 *
 * Keyboard, per the same APG page: Left/Right move between tabs and **wrap** at both ends, Home
 * and End jump to first/last, and the tablist uses a roving `tabIndex` so Tab enters the strip
 * once and then leaves it. `Cmd/Ctrl+1..4` is added on top as this surface's own shortcut,
 * matching the pane/tab-jump binding ops and planner already established — not as a substitute
 * for the standard arrow behaviour.
 *
 * Each panel is wrapped in its own `RegionErrorBoundary`: an admin mid-invite on Users must not
 * lose that dialog because the Audit tab threw.
 */
export function AdminConsole({ currentUserId }: { currentUserId: string }) {
  const [tab, setTab] = useState<TabId>('users')

  // One id per tab; the panel's id is derived from it, so the pair can never drift apart.
  const usersId = useId()
  const rulesId = useId()
  const policyId = useId()
  const auditId = useId()
  const tabIds: Record<TabId, string> = {
    users: usersId,
    rules: rulesId,
    policy: policyId,
    audit: auditId,
  }

  const refs = useRef<Partial<Record<TabId, HTMLButtonElement | null>>>({})

  function select(next: TabId) {
    setTab(next)
    refs.current[next]?.focus()
  }

  useEffect(() => {
    function onKey(event: KeyboardEvent) {
      if (!(event.metaKey || event.ctrlKey)) return
      const index = Number(event.key) - 1
      if (!Number.isInteger(index) || index < 0 || index >= TABS.length) return
      event.preventDefault()
      select(TABS[index].id)
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
    // Registered once, deliberately. `select` only ever touches `setTab` (stable across renders
    // by React's own contract) and `refs.current` (a mutable ref object whose identity never
    // changes), so this listener cannot capture a stale value -- re-registering on every tab
    // change would add and remove a window listener per keystroke for no behavioural difference.
  }, [])

  function onTabKeyDown(event: ReactKeyboardEvent<HTMLDivElement>) {
    const current = TABS.findIndex((t) => t.id === tab)
    let next = current
    if (event.key === 'ArrowRight') next = (current + 1) % TABS.length
    else if (event.key === 'ArrowLeft') next = (current - 1 + TABS.length) % TABS.length
    else if (event.key === 'Home') next = 0
    else if (event.key === 'End') next = TABS.length - 1
    else return
    event.preventDefault()
    select(TABS[next].id)
  }

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div
        role="tablist"
        aria-label="Admin console sections"
        className="flex shrink-0 gap-1 border-b border-border pb-2"
        onKeyDown={onTabKeyDown}
      >
        {TABS.map((entry) => (
          <TabButton
            key={entry.id}
            ref={(node) => {
              refs.current[entry.id] = node
            }}
            id={tabIds[entry.id]}
            panelId={`${tabIds[entry.id]}-panel`}
            active={tab === entry.id}
            onSelect={() => setTab(entry.id)}
          >
            {entry.label}
          </TabButton>
        ))}
      </div>

      {TABS.map((entry) => (
        <div
          key={entry.id}
          id={`${tabIds[entry.id]}-panel`}
          role="tabpanel"
          aria-labelledby={tabIds[entry.id]}
          hidden={tab !== entry.id}
          tabIndex={0}
          className="min-h-0 flex-1 overflow-auto pt-4"
        >
          {/*
            Rendered only while selected. The alternative -- keeping all four mounted -- would run
            three tabs' `list_users` / `list_facility_rules` / `get_audit_log` fetches on every
            visit to this console, for a surface whose whole usage context is "low time pressure,
            deliberate" (`accessibility.md`). Panel identity and ARIA wiring survive either way,
            since the panel element itself is always present.
          */}
          {tab === entry.id ? (
            <RegionErrorBoundary regionName={`admin ${entry.id}`}>
              {entry.id === 'users' ? <UsersTab currentUserId={currentUserId} /> : null}
              {entry.id === 'rules' ? <FacilityRulesTab /> : null}
              {entry.id === 'policy' ? <PolicyTab /> : null}
              {entry.id === 'audit' ? <AuditTab /> : null}
            </RegionErrorBoundary>
          ) : null}
        </div>
      ))}
    </div>
  )
}

const TabButton = ({
  id,
  panelId,
  active,
  onSelect,
  children,
  ref,
}: {
  id: string
  panelId: string
  active: boolean
  onSelect: () => void
  children: ReactNode
  ref: Ref<HTMLButtonElement>
}) => (
  <button
    ref={ref}
    id={id}
    type="button"
    role="tab"
    aria-selected={active}
    aria-controls={panelId}
    tabIndex={active ? 0 : -1}
    onClick={onSelect}
    className={
      active
        ? 'rounded-md bg-info-bg px-3 py-1.5 text-supporting font-semibold text-primary'
        : 'rounded-md px-3 py-1.5 text-supporting font-semibold text-muted-foreground hover:bg-hover'
    }
  >
    {children}
  </button>
)
