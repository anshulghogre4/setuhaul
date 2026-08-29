import { Construction, Inbox, OctagonAlert, SearchX, TriangleAlert } from 'lucide-react'
import type { ReactNode } from 'react'

import { Button } from '@/shared/ui/button'
import { EmptyState } from '@/shared/ui/empty-state'
import { Skeleton } from '@/shared/ui/skeleton'
import { cn } from '@/shared/lib/utils'

/**
 * Screen 12's states, plus the two table primitives all four tabs share.
 *
 * `implementation-spec.md` §3 marks Screen 12 🟢 with no backend dependency — these are
 * frontend-owned rendering states. Every string is verbatim from `mockup.html` §12.A–12.F; where
 * the mockup has none (an empty rule list), the string follows the same pattern rather than being
 * invented in a different register.
 */

/**
 * The card every table on this surface sits in.
 *
 * `table-layout: fixed` with an explicit `<colgroup>` at each call site, matching the mockup's own
 * per-table `<colgroup>` widths. `implementation-spec.md` §5.3 checked the two `auto` instances in
 * the mockup and confirmed them correct for header-less 2-row key/value tables — neither of which
 * exists in the built surface, so every table here is `fixed`.
 */
export function TableCard({ children }: { children: ReactNode }) {
  return (
    <div className="overflow-hidden rounded-md border border-border bg-card">
      <div className="overflow-auto">{children}</div>
    </div>
  )
}

/**
 * Screen 12.D — table loading.
 *
 * A skeleton that matches the final row layout rather than a centred spinner: `mockup.html` §10.A
 * states the reason ("a spinner followed by content is a layout jump, and a jump under a cursor is
 * a mis-click"), and it applies to every table here, not only the simulation panel.
 *
 * `role="status"` + `aria-label` so a screen-reader user learns the table is loading rather than
 * meeting a silent block of empty boxes. The shimmer itself is `data-motion="decorative"` inside
 * `Skeleton` and goes static under `prefers-reduced-motion`.
 */
export function TableSkeleton({ columns, rows = 6 }: { columns: number; rows?: number }) {
  return (
    <div role="status" aria-label="Loading" className="flex flex-col gap-px bg-border">
      {Array.from({ length: rows }, (_, rowIndex) => (
        <div key={rowIndex} className="flex items-center gap-4 bg-card px-4 py-3">
          {Array.from({ length: columns }, (_, colIndex) => (
            <Skeleton
              key={colIndex}
              className={cn('h-4', colIndex === 0 ? 'w-32' : 'w-full max-w-48')}
            />
          ))}
        </div>
      ))}
    </div>
  )
}

/**
 * Screen 12.F — write failed.
 *
 * A banner across the top of the content region, not a full-region state: the table beneath is
 * still valid and still readable.
 *
 * **"Nothing has changed" is essential phrasing, not optional** (`mockup.html` §12.F, verbatim) —
 * in a system where a click commits warehouse capacity, an admin has to know a failure left no
 * partial state behind. `role="alert"` because a failed action is
 * `accessibility-behaviour.md`'s assertive tier.
 */
export function WriteFailedBanner({
  detail,
  onRetry,
}: {
  detail?: string
  onRetry?: () => void
}) {
  return (
    <div
      role="alert"
      className="mb-4 flex items-start gap-3 rounded-md border border-danger-border bg-danger-bg px-4 py-3 text-body text-danger-fg"
    >
      <OctagonAlert className="mt-0.5 size-4 shrink-0" aria-hidden="true" />
      <p>
        That didn’t save. <strong className="font-semibold">Nothing has changed.</strong>
        {detail ? <span className="block text-supporting">{detail}</span> : null}
        {onRetry ? (
          <button
            type="button"
            onClick={onRetry}
            className="ml-2 rounded-sm underline underline-offset-2 outline-none hover:no-underline focus-visible:outline-2 focus-visible:outline-ring focus-visible:outline-offset-2"
          >
            Try again
          </button>
        ) : null}
      </p>
    </div>
  )
}

/**
 * Screen 12.A — nothing yet. Deliberately NOT the same treatment as "no results" (12.B): `inbox`
 * versus `search-x`, and different copy, "because a working-but-empty system and a filter that
 * matched nothing are different facts" (`mockup.html` §12.A).
 */
export function NothingYet({
  title,
  body,
  action,
}: {
  title: string
  body: string
  action?: ReactNode
}) {
  return <EmptyState icon={Inbox} title={title} body={body} actions={action} />
}

/** Screen 12.B / 12.C — a filter or search that matched nothing. */
export function NoMatches({
  title,
  body,
  onClear,
  clearLabel,
}: {
  title: string
  body: string
  onClear: () => void
  clearLabel: string
}) {
  return (
    <EmptyState
      icon={SearchX}
      title={title}
      body={body}
      actions={
        <Button variant="neutral" onClick={onClear}>
          {clearLabel}
        </Button>
      }
    />
  )
}

/**
 * Screen 12.E — load failed.
 *
 * `role="alert"` matches `mockup.html` §12.E's own `<div class="empty" role="alert">`. Scoped to
 * the tab panel, never the whole app: the shell and the other three tabs are unaffected, which is
 * the same per-region discipline `components/states/region-states.tsx` established.
 */
export function LoadFailed({ what, onRetry }: { what: string; onRetry: () => void }) {
  return (
    <div role="alert">
      <EmptyState
        icon={OctagonAlert}
        title={`Couldn’t load ${what} — usually a connection problem.`}
        actions={
          <Button variant="neutral" onClick={onRetry}>
            Try again
          </Button>
        }
      />
    </div>
  )
}

/**
 * The honest stub for a screen whose entire live path is flag-gated off.
 *
 * Same posture as `features/planner`'s own `NotYetAvailable` — a local copy rather than an import,
 * because two other surface builds are working in this tree concurrently and cross-feature imports
 * couple them. Never a fake table or a fake editor: `AGENTS.md` — "Never invent shipment, ETA,
 * dock, appointment, capacity, or operational data."
 */
export function NotYetAvailable({ title, body }: { title: string; body: string }) {
  return <EmptyState icon={Construction} title={title} body={body} />
}

/**
 * An inline "this control has nowhere to send its value" note, for a field that is rendered
 * Inactive rather than hidden.
 *
 * `components.md` foundations §18's Disabled tier: the control stays visible and its reason is
 * stated, as opposed to the Hidden tier used for scope-denied actions. Reuses the same shape
 * E5.2 established for ops' "Take over thread".
 */
export function InactiveNote({ children }: { children: ReactNode }) {
  return (
    <p className="flex items-start gap-2 text-supporting text-muted-foreground">
      <TriangleAlert className="mt-0.5 size-3.5 shrink-0" aria-hidden="true" />
      <span>{children}</span>
    </p>
  )
}
