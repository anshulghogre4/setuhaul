import { Truck } from 'lucide-react'
import { useCallback, useEffect, useMemo, useState } from 'react'

import { RegionError } from '@/components/states/region-states'
import { useCountdownClock } from '@/shared/lib/countdown'
import { cn } from '@/shared/lib/utils'
import { fetchDockBoard } from '../lib/api'
import {
  LEGEND_STATES,
  barTreatment,
  groupByDock,
  hourTicks,
  placeOnTrack,
} from '../lib/board'
import { formatDate, formatTime } from '../lib/format'
import { BoardSkeleton } from './board-skeleton'
import type { BoardBar, BoardBlock, BoardDock, DockBoard as DockBoardPayload } from '../lib/types'

/**
 * The Board tab at rest -- `03-planner-dock-board/screens.md` section 3, `stitch-prompts.md`
 * section 8, states 2 and 22.
 *
 * One horizontal lane per dock, time along the x-axis, one bar per live `dock_occupancy` claim.
 * Every bar's treatment comes from `lib/board.ts`'s single mapping table (components.md section 3's
 * own rule); there is no per-state branch in this file.
 *
 * ## The three rules from the prompt that are code here rather than review notes
 *
 * 1. **Nothing on this board is draggable.** No drag-to-reschedule, no resize handles, no
 *    range-select. Bars are focusable elements with tooltips; every action happens through an
 *    explicit control. A drag affordance on a capacity board is a mis-book waiting for a slip.
 * 2. **The now-line is server time**, reconciled through `CountdownProvider`'s measured offset --
 *    never bare `Date.now()`. A planner whose laptop clock is three minutes fast would otherwise
 *    see the line, and therefore every "is this already running" judgement, three minutes wrong.
 * 3. **A terminal state renders as open space, never a ghost bar.** Enforced by the mapping table
 *    returning `null`, not by a filter here.
 *
 * ## The board owns its fetch
 *
 * Same reason `QueueTab` does, and it is the trap E5.3's own flag audit named: a component that
 * renders an empty/at-rest state without having asked the server tells a planner the board is clear
 * when it has simply never looked. The empty caption below is reachable only after a successful read
 * that genuinely returned nothing.
 *
 * ## What is deliberately NOT here
 *
 * The counter-offer picker's interactive mode (states 3, 24, 25 -- eligible lanes highlighted,
 * ineligible dimmed) is not built. It needs per-shipment eligibility over these lanes, which is a
 * different read from this one, and `plannerCounterOfferEnabled`'s interim dialog remains the entry
 * point until it exists. Stated here rather than hinted at by absence.
 */

/** Lane geometry. 32px lanes and a 56px label column, from `stitch-prompts.md` section 8. */
const LANE_H = 'h-8'
const LABEL_W = 'w-14'
/** Kept in sync with `LABEL_W` (`w-14` = 3.5rem = 56px). The now-line's offset has to be expressed
 *  in the same units as the label column it starts after, so the number appears twice by necessity
 *  and is named once here rather than inlined. */
const LABEL_WIDTH_PX = 56

export function DockBoardPanel({ facilityId }: { facilityId: string | null }) {
  const [board, setBoard] = useState<DockBoardPayload | null>(null)
  const [failed, setFailed] = useState(false)
  const [reloadToken, setReloadToken] = useState(0)
  const { now, offsetMs, setServerTime } = useCountdownClock()

  useEffect(() => {
    let ignore = false
    setFailed(false)
    fetchDockBoard(facilityId)
      .then((data) => {
        if (ignore) return
        setBoard(data)
        // Same reconciliation the queue does: the now-line and any hold countdown on this board are
        // only as honest as the offset between this browser's clock and the server's.
        setServerTime(data.as_of)
      })
      .catch(() => {
        if (!ignore) setFailed(true)
      })
    return () => {
      ignore = true
    }
  }, [facilityId, reloadToken, setServerTime])

  const retry = useCallback(() => setReloadToken((n) => n + 1), [])

  if (failed) {
    // State 23. Scoped to this region -- the Queue tab stays usable, per the prompt's own error
    // variant ("never a whole-app error screen").
    return <RegionError regionName="dock board" onRetry={retry} />
  }
  if (board === null) return <BoardSkeleton />

  return <Board board={board} nowMs={now + offsetMs} />
}

/**
 * The board rendered from a payload the caller already has, with **no fetch**.
 *
 * Exists for `/planner/_states`: the gallery's whole purpose is that "it type-checks" is not "it has
 * been seen rendering", which only holds if the plate mounts the *same* component the route does.
 * A second board built for the gallery would certify markup the live surface never uses.
 *
 * The now-line still comes from the shared clock, so on a fixture whose horizon is in the past the
 * line is correctly absent rather than pinned to an edge.
 */
export function BoardPlate({ board }: { board: DockBoardPayload }) {
  const { now, offsetMs } = useCountdownClock()
  return <Board board={board} nowMs={now + offsetMs} />
}

function Board({ board, nowMs }: { board: DockBoardPayload; nowMs: number }) {
  const horizonStartMs = useMemo(() => Date.parse(board.horizon_start), [board.horizon_start])
  const horizonEndMs = useMemo(() => Date.parse(board.horizon_end), [board.horizon_end])

  const barsByDock = useMemo(() => groupByDock(board.bars), [board.bars])
  const blocksByDock = useMemo(() => groupByDock(board.blocks), [board.blocks])
  const ticks = useMemo(
    () => hourTicks(horizonStartMs, horizonEndMs),
    [horizonStartMs, horizonEndMs],
  )

  const nowPlacement =
    nowMs >= horizonStartMs && nowMs <= horizonEndMs
      ? ((nowMs - horizonStartMs) / (horizonEndMs - horizonStartMs)) * 100
      : null

  const facility = board.facility_name ?? board.facility_id

  return (
    <div className="flex flex-col gap-3">
      {/* The board's own DATE, always. A board of times with no date is the wrong-day hazard this
          product designs against, and it is the one thing `stitch-prompts.md` section 8 puts in
          the header by name. */}
      <p className="text-supporting text-muted-foreground">
        {facility} · {formatDate(board.horizon_start)} · {formatTime(board.horizon_start)}–
        {formatTime(board.horizon_end)}{' '}
        <span className="text-subtle-foreground">
          {board.horizon_end_reason === 'FACILITY_CLOSE'
            ? '(to closing time)'
            : '(next four hours)'}
        </span>
      </p>

      <div className="flex flex-col">
        {/* Axis. `aria-hidden` because every tick's information is already in each bar's own
            accessible name as a dated interval -- a screen-reader user should not have to
            reconstruct a time from a pixel offset. */}
        <div aria-hidden="true" className="flex items-end">
          <div className={cn(LABEL_W, 'shrink-0')} />
          <div className="relative h-5 flex-1">
            {ticks.map((t) => (
              <span
                key={t}
                className="absolute font-mono text-micro text-subtle-foreground"
                style={{
                  left: `${((t - horizonStartMs) / (horizonEndMs - horizonStartMs)) * 100}%`,
                  transform: 'translateX(-50%)',
                }}
              >
                {formatTime(new Date(t).toISOString())}
              </span>
            ))}
          </div>
        </div>

        {/* `role="list"` of lanes: the board is a set of docks, and a screen reader walking it
            should hear that structure rather than a table it cannot navigate cell-wise. */}
        <div
          role="list"
          aria-label={`Dock occupancy at ${facility}`}
          className={cn(
            'relative flex flex-col',
            // Fork F's component-scoped token (U85, tokens.md's component tier). See `board.ts`
            // for the measurement and why this is not a change to `color.md`. Dark deliberately
            // falls through to the foundations token, which already clears 3:1 there.
            '[--dock-bar-held-border:var(--amber-700)]',
            'dark:[--dock-bar-held-border:var(--color-state-held-border)]',
          )}
        >
          {board.docks.map((dock) => (
            <Lane
              key={dock.dock_id}
              dock={dock}
              bars={barsByDock.get(dock.dock_id) ?? []}
              blocks={blocksByDock.get(dock.dock_id) ?? []}
              horizonStartMs={horizonStartMs}
              horizonEndMs={horizonEndMs}
              ticks={ticks}
            />
          ))}

          {/* The now-line spans the whole lane stack. Static: `stitch-prompts.md` section 8
              excludes a pulsing now-line explicitly, along with every other ambient movement. */}
          {nowPlacement !== null && board.docks.length > 0 ? (
            <span
              aria-hidden="true"
              className="pointer-events-none absolute inset-y-0 w-0.5 bg-foreground"
              style={{ left: `calc(${LABEL_WIDTH_PX}px + (100% - ${LABEL_WIDTH_PX}px) * ${nowPlacement / 100})` }}
            />
          ) : null}
        </div>

        {board.docks.length === 0 ? (
          <p className="py-6 text-supporting text-muted-foreground">
            No docks are configured at {facility}.
          </p>
        ) : null}
      </div>

      {/* The empty variant renders the LANES and then says this, rather than replacing the board
          with a blank panel -- `stitch-prompts.md` section 8's own wording. */}
      {board.docks.length > 0 && board.bars.length === 0 ? (
        <p className="text-supporting text-muted-foreground">
          {board.horizon_end_reason === 'FACILITY_CLOSE'
            ? `No appointments before closing time at ${facility}.`
            : `No appointments in the next four hours at ${facility}.`}
        </p>
      ) : null}

      <Legend holdsEnabled={board.holds_enabled} hasBlocks={board.blocks.length > 0} />
    </div>
  )
}

function Lane({
  dock,
  bars,
  blocks,
  horizonStartMs,
  horizonEndMs,
  ticks,
}: {
  dock: BoardDock
  bars: BoardBar[]
  blocks: BoardBlock[]
  horizonStartMs: number
  horizonEndMs: number
  ticks: number[]
}) {
  return (
    <div role="listitem" className="flex items-center border-b border-border">
      <span
        className={cn(
          LABEL_W,
          'shrink-0 truncate py-1 pr-2 font-mono text-supporting text-muted-foreground',
        )}
      >
        {dock.dock_code}
      </span>
      <div className={cn('relative flex-1 rounded-sm bg-hover', LANE_H)}>
        {/* One 1px hour tick, and nothing else -- every other gridline decoration is excluded. */}
        {ticks.map((t) => (
          <span
            key={t}
            aria-hidden="true"
            className="absolute inset-y-0 w-px bg-border"
            style={{ left: `${((t - horizonStartMs) / (horizonEndMs - horizonStartMs)) * 100}%` }}
          />
        ))}

        {/* Outage windows render UNDER the bars deliberately. The block-dock form is what stops a
            dock being blocked and booked over the same instant (components.md section 4), so an
            overlap on screen is a data anomaly and the booking is the fact a planner must not lose
            sight of. */}
        {blocks.map((block) => (
          <BlockMarker
            key={block.dock_event_id}
            block={block}
            horizonStartMs={horizonStartMs}
            horizonEndMs={horizonEndMs}
          />
        ))}

        {bars.map((bar) => (
          <Bar
            key={bar.occupancy_id}
            bar={bar}
            dock={dock}
            horizonStartMs={horizonStartMs}
            horizonEndMs={horizonEndMs}
          />
        ))}
      </div>
    </div>
  )
}

function Bar({
  bar,
  dock,
  horizonStartMs,
  horizonEndMs,
}: {
  bar: BoardBar
  dock: BoardDock
  horizonStartMs: number
  horizonEndMs: number
}) {
  const treatment = barTreatment(bar.state)
  const place = placeOnTrack(bar.window_start, bar.window_end, horizonStartMs, horizonEndMs)
  // Two independent reasons to draw nothing, and both are correct answers rather than failures:
  // a terminal state occupies no capacity, and an interval outside the horizon is not on this board.
  if (treatment === null || place === null) return null

  const interval = `${formatDate(bar.window_start)} · ${formatTime(bar.window_start)}–${formatTime(bar.window_end)}`
  const identity = bar.order_reference ?? bar.shipment_id ?? bar.occupancy_id
  // Colour is never the only carrier: the state word is in the tooltip and in the accessible name
  // alongside the identity and the dated interval (`stitch-prompts.md` section 8's legend rule).
  const description = `${treatment.label} · ${identity} · Dock ${dock.dock_code} · ${interval}${
    bar.hold_expires_at ? ` · hold expires ${formatTime(bar.hold_expires_at)}` : ''
  }`

  return (
    <button
      type="button"
      // A real button, so it is keyboard-reachable and gets focus-visible for free. It performs no
      // action on activation by design -- the board is read-and-act-via-affordances, and every
      // action lives in an explicit control elsewhere. `title` carries the same string the
      // accessible name does, so the two cannot drift.
      title={description}
      aria-label={description}
      className={cn(
        'absolute inset-y-0.5 flex items-center gap-1 overflow-hidden rounded-sm px-1',
        'text-micro font-medium whitespace-nowrap',
        'focus-visible:outline-2 focus-visible:outline-ring focus-visible:outline-offset-1',
        treatment.className,
      )}
      style={{ left: `${place.leftPct}%`, width: `${place.widthPct}%` }}
    >
      {treatment.icon === 'truck' ? (
        <Truck size={12} strokeWidth={2} aria-hidden="true" className="shrink-0" />
      ) : null}
      <span aria-hidden="true" className="truncate font-mono">
        {identity}
      </span>
    </button>
  )
}

function BlockMarker({
  block,
  horizonStartMs,
  horizonEndMs,
}: {
  block: BoardBlock
  horizonStartMs: number
  horizonEndMs: number
}) {
  const place = placeOnTrack(
    block.event_start_ts,
    block.event_end_ts,
    horizonStartMs,
    horizonEndMs,
  )
  if (place === null) return null

  const reason = block.reason ? `blocked — ${block.reason}` : `blocked — ${block.event_type}`
  const ends = block.event_end_ts
    ? `${formatTime(block.event_start_ts)}–${formatTime(block.event_end_ts)}`
    : `from ${formatTime(block.event_start_ts)}, no end set`
  const description = `${reason} · ${ends}`

  return (
    <span
      // A 45-degree hatch, no elevation, no promise-state colour: an unavailability and a booking
      // are different facts and must never share an encoding. Elevation here would imply something
      // is booked in the window (components.md section 4).
      title={description}
      aria-label={description}
      role="img"
      // `border-subtle-foreground`, NOT `border-border`. Measured in a real render (2026-08-31):
      // the design's own `#CBD5E1` (= `--color-input`) sits at **1.13:1** against this board's
      // `surface-hover` track, far under WCAG 1.4.11's 3:1 for a UI component boundary -- and it is
      // the same 1.36 the E5.3 fix pass already caught and raised to 4.34 for this exact marker
      // (`implementation-spec.md` section 5.2's bar table). `neutral-500` is the value that produces
      // that 4.34, so this uses the corrected token rather than the prompt's original hex. Same
      // token for the hatch stripe, because a hatch nobody can see is not an encoding.
      className="absolute inset-y-0 overflow-hidden rounded-sm border border-subtle-foreground px-1 text-micro text-muted-foreground"
      style={{
        left: `${place.leftPct}%`,
        width: `${place.widthPct}%`,
        backgroundImage:
          'repeating-linear-gradient(45deg, var(--color-subtle-foreground) 0 2px, transparent 2px 6px)',
      }}
    >
      <span aria-hidden="true" className="truncate">
        {reason}
      </span>
    </span>
  )
}

/**
 * One legend row. Each swatch carries its own **border style**, not just its fill -- that is what
 * makes dashed-means-temporary legible in the legend as well as on the bar.
 *
 * The HELD entry is omitted when `holds_enabled` is false: on a deploy where the D2 path is off, no
 * `dock_occupancy` row can be in that state, so a HELD swatch would be a legend entry for something
 * this board can never show. Omitted rather than greyed, per `components.md` section 18.
 */
function Legend({ holdsEnabled, hasBlocks }: { holdsEnabled: boolean; hasBlocks: boolean }) {
  const states = holdsEnabled ? LEGEND_STATES : LEGEND_STATES.filter((s) => s !== 'HELD')
  return (
    <ul
      role="list"
      className={cn(
        'flex flex-wrap items-center gap-4 text-micro text-muted-foreground',
        // Same component-scoped Fork F token as the board, so the legend's HELD swatch and the bar
        // it stands for cannot render different borders.
        '[--dock-bar-held-border:var(--amber-700)]',
        'dark:[--dock-bar-held-border:var(--color-state-held-border)]',
      )}
    >
      {states.map((state) => {
        const treatment = barTreatment(state)
        if (!treatment) return null
        return (
          <li key={state} className="flex items-center gap-1.5">
            <span
              aria-hidden="true"
              className={cn('inline-block size-2 rounded-[2px]', treatment.className)}
            />
            {treatment.label}
          </li>
        )
      })}
      {hasBlocks ? (
        <li className="flex items-center gap-1.5">
          <span
            aria-hidden="true"
            className="inline-block size-2 rounded-[2px] border border-subtle-foreground"
            style={{
              backgroundImage:
                'repeating-linear-gradient(45deg, var(--color-subtle-foreground) 0 1px, transparent 1px 3px)',
            }}
          />
          Blocked
        </li>
      ) : null}
    </ul>
  )
}
