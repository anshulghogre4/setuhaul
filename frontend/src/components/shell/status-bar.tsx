import { CloudAlert, RefreshCw, Wifi, WifiOff } from 'lucide-react'
import { useAtomValue } from 'jotai'

import { statusBarFields, type RoleName } from '@/core/auth/identity'
import { formatLastSync, pollHealthAtom } from '@/shared/lib/live-poll'
import { cn } from '@/shared/lib/utils'

export type ConnectionState = 'connected' | 'syncing' | 'sync-failed' | 'offline'

const CONNECTION = {
  connected: { icon: Wifi, label: 'Connected', danger: false, spin: false },
  syncing: { icon: RefreshCw, label: 'Syncing', danger: false, spin: true },
  'sync-failed': { icon: CloudAlert, label: 'Sync failed', danger: false, spin: false },
  offline: { icon: WifiOff, label: 'Offline', danger: true, spin: false },
} as const

/**
 * Artboard 31.  28px.  Five fields in fixed order:
 * connection state · last sync · active facility · pending count · policy version.
 *
 * **Connection state carries an icon AND text, never a coloured dot alone**, and Offline is
 * the only state that takes danger colour -- on the icon *and* the word.  The "last sync"
 * value beside it is what makes "Offline" actionable rather than merely alarming: a stale
 * number is a warning, not a fire (auth-and-scoping.md's degradation policy).
 *
 * **Exactly one live region, on the connection field only.**  This closed a real spec gap:
 * U82's announcement matrix had no row for the status bar, and its *general* rule routes
 * ambient state TO the status bar as the silent alternative to a push -- which would have
 * silently swallowed a connection drop.  That is not ambient: a planner who goes offline and
 * keeps confirming is acting on stale capacity data.  Polite rather than assertive because
 * the *consequence* carries the urgency (primary content goes Inactive, and Confirm goes
 * with it).  Last sync, pending count, facility and policy version tick continuously and are
 * deliberately **silent** -- a live region over them would make the bar unusable with a
 * screen reader, the same reasoning that throttles the countdown to four thresholds.
 *
 * **Only the facility name truncates.**  It is the one variable-length field; a truncated
 * "14 pending" or a half-shown policy version is worse than no field at all.  Every child
 * needs `min-w-0` or a long facility name pushes the policy version out of the bar.
 *
 * ## Real poll health, not a decorative dot (issue #59, 2026-08-31)
 *
 * The connection field now reads `pollHealthAtom` whenever a surface is actually polling
 * (`shared/lib/live-poll.ts`), and falls back to its props when none is -- so on the ops and
 * planner consoles it reports the **last real read**: connected with the clock time of the last
 * success, "Sync failed" with how long ago that success was, or "Offline".  Before this it always
 * rendered whatever `App.tsx`'s `DEMO_CHROME` said, which was permanently "Connected · 09:52:14".
 *
 * That matters beyond honesty: `auth-and-scoping.md`'s degradation policy is that a planner who
 * goes offline and keeps confirming is acting on stale capacity data, and this row is the only
 * thing on screen that can say so.  A green dot that is green regardless is worse than no dot.
 *
 * The pending count follows the same rule and renders **"—" when unknown** rather than "0" --
 * `02-ops-exception-console/stitch-prompts.md`'s error state is explicit that "unknown and zero
 * must never look the same".
 *
 * The live region is unchanged and stays on the connection field only.  It contains the state
 * WORD and nothing else, which is what keeps it announcing on transition rather than on every
 * poll: the clock time beside it changes every 15 seconds and sits deliberately outside the
 * region, so a screen-reader user is not told "Connected" four times a minute.
 */
export function StatusBar({
  role,
  connection,
  lastSync,
  facilityName,
  pendingCount,
  policyVersion,
}: {
  role: RoleName
  connection: ConnectionState
  /** Already formatted: "09:52:14" when live, "6m ago" when offline. */
  lastSync: string
  facilityName: string | null
  pendingCount: number
  policyVersion: string
}) {
  const fields = statusBarFields(role)
  const health = useAtomValue(pollHealthAtom)
  // `idle` means no surface is polling on this route -- keep the props, which is what every
  // non-polling surface still supplies.
  const livePolling = health.status !== 'idle'
  const effectiveConnection: ConnectionState = livePolling
    ? (health.status as Exclude<typeof health.status, 'idle'>)
    : connection
  const effectiveLastSync = livePolling ? formatLastSync(health) : lastSync
  const effectivePending = livePolling ? health.pendingCount : pendingCount
  const { icon: Icon, label, danger, spin } = CONNECTION[effectiveConnection]

  return (
    <div className="flex h-7 w-full shrink-0 items-center gap-3 border-t border-input bg-card px-3 text-[11px] leading-[1.3] text-muted-foreground">
      <span
        role="status"
        className={cn(
          'inline-flex shrink-0 items-center gap-1.5 whitespace-nowrap',
          danger ? 'text-danger-fg' : '',
        )}
      >
        <Icon
          className={cn('size-3.5', danger ? 'text-danger-fg' : 'text-subtle-foreground', spin && 'animate-spin')}
          aria-hidden="true"
        />
        {label}
      </span>

      <Separator />
      <span className="inline-flex shrink-0 items-center gap-1.5 whitespace-nowrap">
        Last sync <span className="font-mono" translate="no">{effectiveLastSync}</span>
      </span>

      {/* The facility name is the ONLY field allowed to shrink, and the only one that
          truncates -- a truncated "14 pending" or a half-shown policy version is worse
          than no field at all.  `shrink-0` on every other field is what makes that true:
          with all fields shrinkable, flexbox distributes the shortfall proportionally
          across items that are `whitespace-nowrap` and cannot actually give any back, and
          the bar overflows.  Measured: a 60-char facility name produced scrollWidth 603 vs
          clientWidth 598 before this. */}
      {fields.facility && facilityName ? (
        <>
          <Separator />
          {/* `min-w-0` + default `flex: 0 1 auto` = allowed to SHRINK but not to grow.
              `flex-1` here would stretch the field and shove the pending count over to the
              right edge, which is not the mockup's left-grouped layout. */}
          <span className="min-w-0 truncate" translate="no">{facilityName}</span>
        </>
      ) : null}

      <Separator />
      <span className="inline-flex shrink-0 items-center gap-1.5 whitespace-nowrap">
        <span className="font-mono" translate="no">{effectivePending ?? '—'}</span> pending
      </span>

      {fields.policyVersion ? (
        <span className="ml-auto inline-flex shrink-0 items-center gap-1.5 whitespace-nowrap">
          Policy <span className="font-mono" translate="no">{policyVersion}</span>
        </span>
      ) : null}
    </div>
  )
}

function Separator() {
  return <span aria-hidden="true" className="h-3 w-px shrink-0 bg-border" />
}
