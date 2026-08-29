import { CircleCheckBig, Inbox, OctagonAlert, RefreshCw, SearchX, TriangleAlert } from 'lucide-react'
import type { ReactNode } from 'react'

import { Button } from '@/shared/ui/button'
import { cn } from '@/shared/lib/utils'

/**
 * The negative and empty states — `stitch-prompts.md` §5/§6/§7, `flows-and-states.md` Flow 6,
 * `edge-cases.md` #4/#5.
 *
 * This surface's own `checklist-design` audit found these to be its strongest single item: five
 * different negative states where the checklist names one. They are built alongside the happy
 * path rather than after it (`implementation-spec.md` §5, build order item 4), because which one
 * renders is a correctness question, not a polish question.
 *
 * A dedicated set rather than `shared/ui/empty-state.tsx` for two of them, and the reason is
 * specific: `EmptyState` renders its title at `text-h3` (16px/600), which is right for a
 * full-region state but wrong for the **caught-up** and **no-match** blocks, whose copy the
 * design pins at 14px body — the "nothing yet" block is the only one of the three that takes
 * the 16px lead line, and that difference is the whole point of U74's distinction. Using one
 * component for all three would flatten exactly the thing these states exist to distinguish.
 */

function Block({
  icon: Icon,
  children,
  role = 'status',
  className,
}: {
  icon: typeof Inbox
  children: ReactNode
  role?: 'status' | 'alert'
  className?: string
}) {
  return (
    <div
      role={role}
      className={cn('flex flex-col items-center px-6 py-12 text-center', className)}
    >
      <Icon className="mb-4 size-8 text-subtle-foreground" aria-hidden="true" strokeWidth={2} />
      {children}
    </div>
  )
}

/**
 * "Caught up" — an established carrier with real history that happens to have nothing running.
 * A **good** state, reassuring in tone, and deliberately **no button**: there is nothing a
 * carrier could do here even if there were something to act on.
 */
export function CaughtUpBlock({ copy }: { copy: string }) {
  return (
    <Block icon={CircleCheckBig}>
      <p className="text-body">{copy}</p>
    </Block>
  )
}

/**
 * "Nothing yet" — a brand-new carrier with no history at all. Neutral and informational, never
 * reassuring: there is nothing yet to be reassured about.
 *
 * **The icon differs from `CaughtUpBlock`'s on purpose** — `inbox` reads "not started" where
 * `circle-check-big` reads "you're done". Using one glyph for both would undercut the whole U74
 * distinction. No call to action: this surface is read-only and a carrier cannot create a
 * shipment, so "Book a slot" / "Add a driver" / "Get started" would all be lies.
 */
export function NothingYetBlock() {
  return (
    <Block icon={Inbox}>
      <p className="text-h3">No shipments on record yet</p>
      <p className="mt-2 max-w-[48ch] text-supporting text-muted-foreground">
        New deliveries will appear here automatically once they&rsquo;re scheduled.
      </p>
    </Block>
  )
}

/** Filtered with no matches. The heading, the filter control and the column headers all stay
 *  put, so nothing about the layout moves when a match returns. Clearing a filter is a Low-tier
 *  action (`components.md` §19) — it acts immediately, with no confirmation. */
export function NoFilterMatchBlock({ onClear }: { onClear: () => void }) {
  return (
    <Block icon={SearchX}>
      <p className="text-body">No shipments match this filter.</p>
      <Button type="button" variant="neutral" className="mt-4" onClick={onClear}>
        Clear filter
      </Button>
    </Block>
  )
}

/**
 * A primary region failed to load. States a cause and offers a route out — never a bare
 * "something went wrong", never a raw error code, HTTP status or request id, and never a
 * full-page error screen for one failed region: each section owns its own boundary and the
 * others stay fully rendered.
 *
 * `role="alert"`, matching `accessibility.md`'s announcement table (an unsuccessful action is
 * assertive).
 */
export function RegionFailedBlock({ what, onRetry }: { what: string; onRetry: () => void }) {
  return (
    <Block icon={OctagonAlert} role="alert">
      <p className="text-body">Couldn&rsquo;t load your {what} &mdash; usually a connection problem.</p>
      <Button type="button" variant="neutral" className="mt-4" onClick={onRetry}>
        Try again
      </Button>
    </Block>
  )
}

/**
 * Past roughly 3 seconds a skeleton is joined by a `Retry` rather than pulsing indefinitely
 * (`stitch-prompts.md` §5's latency bands). Under 1 second nothing renders at all — that gate
 * lives in the screen, not here, since it decides whether this component mounts.
 */
export function StalledRow({ onRetry }: { onRetry: () => void }) {
  return (
    <div
      role="status"
      className="flex items-center justify-center gap-3 border-t border-border p-4 text-supporting text-muted-foreground"
    >
      <span>This is taking longer than usual.</span>
      <Button type="button" variant="neutral" size="sm" onClick={onRetry}>
        Retry
      </Button>
    </div>
  )
}

/**
 * The stale-data notice — `stitch-prompts.md` §7 variant (c).
 *
 * **One notice, not five.** A page reporting a separate warning per region has stopped being
 * informative, so this sits once above the tiles and the stale sections below stay fully
 * rendered and legible: not greyed, not overlaid, not blurred.
 *
 * **Warning tokens, never danger red.** A page that looks like it is on fire when the real
 * problem is "these numbers are forty seconds old" trains people to stop trusting red when it
 * matters. `--color-warning-*` is the functional feedback family; the promise-state
 * `--color-state-held-*` tokens are reserved to the chip alone (`components.md` §2: "nothing
 * else may borrow them") and borrowing them would render a staleness warning in `HELD`'s exact
 * palette — the defect `implementation-spec.md` §4.0's R9 caught in the mockup.
 *
 * `role="status"` and not a toast: staleness is a persistent condition, not an event.
 */
export function StaleNotice({ since, onRetry }: { since: string; onRetry: () => void }) {
  return (
    <div
      role="status"
      className="mb-3 flex items-center gap-2 rounded-md border border-warning-border bg-warning-bg px-(--cell-px) py-3 text-body text-warning-fg"
    >
      <TriangleAlert className="size-4 shrink-0" aria-hidden="true" strokeWidth={2} />
      <span>
        This page couldn&rsquo;t refresh. You&rsquo;re seeing data from{' '}
        <span className="font-mono tabular-nums" data-numeric>
          {since}
        </span>
        .
      </span>
      <button
        type="button"
        onClick={onRetry}
        className="ml-1 inline-flex min-h-11 items-center rounded-sm font-semibold text-inherit underline outline-none focus-visible:outline-2 focus-visible:outline-ring focus-visible:outline-offset-2"
      >
        Try again
      </button>
    </div>
  )
}

/**
 * "Last updated 2 minutes ago · Refresh".
 *
 * A **manual** refresh model, and the absence it implies is deliberate: no live-updating region,
 * no auto-refresh, no websocket indicator, no "3 new" badge anywhere on this surface
 * (`flows-and-states.md` Flow 5). A scoped read dashboard for a role with no time-pressured
 * decision does not need one, and implying real-time urgency this role does not have would be a
 * lie about the data.
 *
 * `refresh-cw` is the one icon in this product permitted to spin, and it spins only while a
 * refresh is genuinely in flight.
 */
export function LastUpdatedLine({
  relative,
  refreshing,
  onRefresh,
}: {
  relative: string | null
  refreshing: boolean
  onRefresh: () => void
}) {
  return (
    <div className="mb-5 flex items-center gap-2 text-micro text-subtle-foreground">
      <span>{relative ? `Last updated ${relative}` : 'Last updated just now'}</span>
      <button
        type="button"
        onClick={onRefresh}
        className="inline-flex min-h-11 items-center gap-1 rounded-sm text-label font-semibold tracking-normal text-link outline-none hover:underline focus-visible:outline-2 focus-visible:outline-ring focus-visible:outline-offset-2"
      >
        <RefreshCw
          className={cn('size-3.5', refreshing && 'animate-spin')}
          data-motion="decorative"
          aria-hidden="true"
          strokeWidth={2}
        />
        Refresh
      </button>
    </div>
  )
}

/** Section heading — 12px/600/0.04em uppercase in tertiary ink, with an optional right-aligned
 *  control on the same line. `h2` because the screen's own `h1` is the carrier's name. */
export function SectionHead({ children, action }: { children: ReactNode; action?: ReactNode }) {
  return (
    <div className="mb-2 flex items-center justify-between gap-4">
      <h2 className="text-label text-subtle-foreground uppercase">{children}</h2>
      {action}
    </div>
  )
}
