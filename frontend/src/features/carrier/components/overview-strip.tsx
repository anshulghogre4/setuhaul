import { ArrowDown, ArrowUp } from 'lucide-react'
import type { ReactNode } from 'react'

import { Skeleton } from '@/shared/ui/skeleton'
import { cn } from '@/shared/lib/utils'
import { Sparkline } from './sparkline'
import { formatCount, formatPercent } from '../lib/format'
import type { FleetOverview, OnTimePerformance } from '../lib/types'

/**
 * The fleet overview strip — `stitch-prompts.md` §2, `05-carrier-portal/components.md` §1,
 * `00-foundations/components.md` §14 (stat tile, U66).
 *
 * Three tiles, one `get_fleet_overview` call, plus a second call
 * (`get_carrier_on_time_performance`) for the third tile's trend series only. The headline `91%`
 * renders from the overview alone; the sparkline waits on its own call, which is why the two
 * arrive as separate props here rather than one merged object (`flows-and-states.md` Flow 1).
 *
 * ## Value type size — a real fork, decided by the standing rule, not silently
 *
 * `00-foundations/components.md` §14 specifies `text-h3` (16px/600) for a stat-tile value;
 * `mockup.html` renders 24px/700 and `implementation-spec.md` §4.0's R8 sweep explicitly left
 * the *size* unreconciled as "a design call, not a mockup bug" (24/600 is `text-h1`, also a real
 * token). Issue #40's own standing rule settles it: **"If the mockup and a `00-foundations/`
 * file disagree, foundations wins and the deviation gets recorded."** So: `text-h3`, and this
 * comment is the record. Flagged to the owner as a one-line change if they prefer the larger
 * figure.
 *
 * ## What is absent, on purpose
 *
 * No benchmark, no rank, no percentile, no "vs. industry", no count of anything outside this
 * account. Tiles 1 and 2 carry no trend line — point-in-time facts with no meaningful shape at a
 * glance, and forcing a sparkline onto every tile is decoration, not information. No coloured
 * tile background and no coloured left border: the delta tints the arrow and its number only.
 */

function Tile({ label, children }: { label: ReactNode; children: ReactNode }) {
  return (
    <div className="rounded-md border border-border bg-card p-(--card-p) shadow-raised">
      {label}
      {children}
    </div>
  )
}

function TileLabel({ children }: { children: ReactNode }) {
  return <div className="text-label text-subtle-foreground uppercase">{children}</div>
}

function TileValue({ children }: { children: ReactNode }) {
  return (
    <div className="mt-1 font-mono text-h3 tabular-nums" data-numeric>
      {children}
    </div>
  )
}

/**
 * The on-time delta, in percentage POINTS against a named period.
 *
 * **Direction is carried in text, not only in the arrow.** `implementation-spec.md` §4.0's R14b
 * found the arrow to be the sole channel and `aria-hidden` at that — the accessible name read
 * "2 pts vs. prior 30 days" with the direction missing entirely, the same "meaning in one hidden
 * channel" failure the promise-state chip's four redundant encodings exist to prevent. The
 * `sr-only` word below is the fix, and unlike the mockup (which had one sign in its dataset) it
 * branches on the real value.
 */
function Delta({ points }: { points: number }) {
  const rising = points > 0
  const flat = points === 0
  const Icon = rising ? ArrowUp : ArrowDown
  const word = flat ? 'Unchanged, ' : rising ? 'Increased ' : 'Decreased '

  return (
    <span
      className={cn(
        'inline-flex items-center gap-0.5 text-label tracking-normal',
        // The delta colours the glyph and its number ONLY. A tile that turns green is a tile
        // shouting; the arrow is sufficient (components.md §14). A zero move spends no colour
        // at all, because there is no direction to report.
        flat ? 'text-muted-foreground' : rising ? 'text-success-fg' : 'text-danger-fg',
      )}
    >
      {flat ? null : <Icon className="size-3" aria-hidden="true" strokeWidth={2} />}
      <span className="sr-only">{word}</span>
      <span className="tabular-nums" data-numeric>
        {Math.abs(points)}
      </span>
      <span>&nbsp;pts</span>
      <span className="font-medium text-subtle-foreground tracking-normal">
        &nbsp;vs. prior 30 days
      </span>
    </span>
  )
}

export function OverviewStrip({
  overview,
  performance,
  dimmed = false,
}: {
  overview: FleetOverview
  /** `null` when the trend call failed or has not resolved. **Secondary content: it simply is
   *  not there** — no error, no placeholder box, no ghosted chart, nothing on the page
   *  mentioning it (`stitch-prompts.md` §7 variant (b)). */
  performance: OnTimePerformance | null
  dimmed?: boolean
}) {
  const ot = overview.on_time_performance

  return (
    <div
      className={cn('grid grid-cols-3 gap-4', dimmed && 'muted-region cursor-progress')}
      // Retoned, not skeleton-flashed over an already-rendered tile (`stitch-prompts.md` §2's
      // motion rule). aria-busy tells AT the same thing.
      //
      // ⚠ NOT `opacity-60` any more (issue #90, 2026-09-01). 60% opacity put these tiles'
      // 12px labels at 2.29:1 -- measured, and the smallest type on the surface was the part
      // it hurt most. `muted-region` demotes the token instead of compositing the pixels, so
      // the values land at 7.58:1 (light) / 12.02:1 (dark) while still visibly receding.
      // `cursor-progress` carries the transient "busy" half of the old signal; there is no
      // container surface or border here to change (the tiles own theirs), so the pointer
      // affordance plus aria-busy is the honest substitute rather than an invented box.
      aria-busy={dimmed || undefined}
    >
      <Tile label={<TileLabel>Active shipments</TileLabel>}>
        <TileValue>{formatCount(overview.active_shipment_count)}</TileValue>
      </Tile>

      <Tile label={<TileLabel>Open exceptions</TileLabel>}>
        <TileValue>{formatCount(overview.open_exception_count)}</TileValue>
      </Tile>

      <Tile
        label={
          <div className="flex flex-wrap items-baseline gap-2">
            <TileLabel>On-time (30d)</TileLabel>
            {/* No delta at all when either window had no arrivals — `carrier_reads` returns
                `null` rather than inventing a trend out of an absence, and so does this. */}
            {ot.delta_percentage_points === null ? null : (
              <Delta points={ot.delta_percentage_points} />
            )}
          </div>
        }
      >
        <TileValue>{formatPercent(ot.percent)}</TileValue>
        {performance && ot.percent !== null ? (
          <Sparkline
            series={performance.series}
            windowStart={performance.window_start}
            windowEnd={performance.window_end}
            endingPercent={performance.percent}
          />
        ) : null}
      </Tile>
    </div>
  )
}

/**
 * Skeleton at the exact dimensions of the content it replaces, so nothing jumps when it
 * resolves: a 90×12 label block and a 48×16 value block per tile. **The sparkline slot stays
 * empty** — it is secondary content and does not get its own skeleton (`stitch-prompts.md` §5).
 */
export function OverviewStripSkeleton() {
  return (
    <div className="grid grid-cols-3 gap-4" aria-hidden="true">
      {[0, 1, 2].map((i) => (
        <div key={i} className="rounded-md border border-border bg-card p-(--card-p) shadow-raised">
          <Skeleton className="h-3 w-[90px] rounded-sm" />
          <Skeleton className="mt-2 h-4 w-12 rounded-sm" />
        </div>
      ))}
    </div>
  )
}
