import type { BoardBar, BoardBlock, DockOccupancyState } from './types'

/**
 * The board's one shared render pass -- `03-planner-dock-board/components.md` section 3.
 *
 * That section states the rule this file exists to obey, and it is a maintenance rule with teeth:
 * *"every dock row runs the same state->token function; a new `dock_occupancy` state added later
 * gets a mapping-table row, not a bespoke branch."* So the nine values live in one record below and
 * every bar -- occupied, held, in progress -- is drawn from its entry. There is deliberately no
 * `if (state === 'HELD')` anywhere in `dock-board.tsx`.
 *
 * ## Terminal states render nothing, and that is a mapping row rather than a filter
 *
 * `COMPLETED` / `CANCELLED` / `EXPIRED` / `NO_SHOW` / `REJECTED` map to `null`. The board's horizon
 * is forward-looking, so a terminal state means the interval no longer occupies capacity: it is
 * open lane space, **never a faded ghost bar** (`stitch-prompts.md` section 8 excludes ghost bars by
 * name). The server's occupancy read already declines to return them, so this is belt-and-braces --
 * but it is the *table* that says so, which is what makes the rule inspectable.
 *
 * ## Dashed vs solid is a shape channel, not decoration
 *
 * `stitch-prompts.md` section 8: *"a dashed bar says 'temporary' in greyscale, under glare, and for
 * a colour-blind user. Do not normalise all bars to one border style."* Same argument as the promise
 * chip's own dashed HELD border, and the same instruction not to tidy it away.
 */

export type BarTreatment = {
  /** Tailwind classes for the bar itself. */
  className: string
  /** Spoken/visible state word for the tooltip and the accessible name. Never abbreviated. */
  label: string
  /** `IN_PROGRESS` is the committed category distinguished by an ICON, not by a new hue -- keeping
   *  the hue budget exactly where U10/U59/U85 fixed it. */
  icon?: 'truck'
}

/**
 * `--dock-bar-held-border` is a **component-scoped token**, declared on the board root in
 * `dock-board.tsx` rather than in `theme.css`.
 *
 * This is `implementation-spec.md` section 6 **Fork F**, resolved as its own recommendation (c).
 * Measured there: after inheriting `color.md`'s corrected `amber-600`, the HELD bar's border sits at
 * **2.91:1** against the board's `surface-hover` track -- 0.09 short of WCAG 1.4.11's 3:1 for a UI
 * component boundary, while every other bar treatment clears it. The cause is contextual rather
 * than a bad token: the promise-state border palette was tuned against *chip* backgrounds, and a
 * Gantt bar sits on a lighter-relative track no chip occupies.
 *
 * Option (b) -- raising `state-held-border` in `color.md` -- would change the chip on three other
 * surfaces to fix one. `tokens.md`'s component tier (U85) exists for exactly this case, so the
 * board declares its own value and the foundations token is left alone. Light mode takes
 * `amber-700` (measured 4.58:1 against `--neutral-100`); **dark is left on the foundations token**,
 * because dark's `amber-500` already clears 3:1 and overriding it would be deviating for no
 * measured reason.
 */
const BAR_TREATMENT: Record<DockOccupancyState, BarTreatment | null> = {
  HELD: {
    className:
      'bg-state-held-bg border-2 border-dashed border-(--dock-bar-held-border) text-state-held-text',
    label: 'Held',
  },
  PENDING_CONFIRMATION: {
    className:
      'bg-state-pending-bg border-2 border-solid border-state-pending-border text-state-pending-text',
    label: 'Pending confirmation',
  },
  CONFIRMED: {
    className:
      'bg-state-confirmed-bg border-2 border-solid border-state-confirmed-border text-state-confirmed-text',
    label: 'Confirmed',
  },
  IN_PROGRESS: {
    className:
      'bg-state-confirmed-bg border-2 border-solid border-state-confirmed-border text-state-confirmed-text',
    label: 'In progress',
    icon: 'truck',
  },
  COMPLETED: null,
  CANCELLED: null,
  EXPIRED: null,
  NO_SHOW: null,
  REJECTED: null,
}

/**
 * The whole state->treatment decision, in one lookup.
 *
 * An unrecognised state returns `null` -- no bar -- rather than throwing or falling back to a
 * treatment. A `dock_occupancy.state` this client has never heard of is a contract change, and
 * drawing it as CONFIRMED would be the one direction that can mislead a planner about capacity.
 */
export function barTreatment(state: string): BarTreatment | null {
  return BAR_TREATMENT[state as DockOccupancyState] ?? null
}

/** The four states that can actually produce a bar, in the legend's own order. */
export const LEGEND_STATES: DockOccupancyState[] = [
  'CONFIRMED',
  'PENDING_CONFIRMATION',
  'IN_PROGRESS',
  'HELD',
]

/* ----------------------------------------------------------------------------------------------
 * Geometry
 * -------------------------------------------------------------------------------------------- */

export type LanePlacement = {
  /** Percent of the track, clamped to [0, 100]. */
  leftPct: number
  widthPct: number
}

/**
 * Where an interval sits on the horizon track, as percentages.
 *
 * **Clamped at both ends, and the clamp is the point.** A bar that starts before `horizonStart` or
 * runs past `horizonEnd` is a real, normal case -- an unload in progress right now began in the
 * past, and a block is frequently open-ended -- and it must render as a bar that reaches the edge
 * of the board rather than as a negative offset that escapes its lane. Returns `null` when the
 * interval does not intersect the horizon at all, which is a different answer from "zero width".
 *
 * Percent rather than pixels so the lanes stay fluid at every measured width (1280 / 1440 / 1600)
 * without a resize observer; the dock-label column is a fixed sibling, not part of this track.
 */
export function placeOnTrack(
  startIso: string,
  endIso: string | null,
  horizonStartMs: number,
  horizonEndMs: number,
): LanePlacement | null {
  const span = horizonEndMs - horizonStartMs
  if (span <= 0) return null
  const start = Date.parse(startIso)
  // A null end is open-ended (an unfinished block). It reaches the edge of the board, which is the
  // honest rendering of "out until someone ends it" -- not an invented end instant.
  const end = endIso === null ? horizonEndMs : Date.parse(endIso)
  if (Number.isNaN(start) || Number.isNaN(end)) return null
  if (end <= horizonStartMs || start >= horizonEndMs) return null

  const clampedStart = Math.max(start, horizonStartMs)
  const clampedEnd = Math.min(end, horizonEndMs)
  const leftPct = ((clampedStart - horizonStartMs) / span) * 100
  const widthPct = ((clampedEnd - clampedStart) / span) * 100
  return { leftPct, widthPct: Math.max(widthPct, 0) }
}

/**
 * Hour ticks across the horizon -- one per whole hour strictly inside it.
 *
 * `stitch-prompts.md` section 8 allows *"a 1px hour tick"* and excludes every other gridline
 * decoration, so this returns the ticks and nothing else (no half-hours, no minor grid).
 */
export function hourTicks(horizonStartMs: number, horizonEndMs: number): number[] {
  const ticks: number[] = []
  const first = new Date(horizonStartMs)
  first.setMinutes(0, 0, 0)
  let t = first.getTime()
  if (t < horizonStartMs) t += 3_600_000
  // A four-hour horizon has at most four interior ticks; the bound is a guard against a malformed
  // horizon rather than an expected path.
  while (t < horizonEndMs && ticks.length < 24) {
    ticks.push(t)
    t += 3_600_000
  }
  return ticks
}

/** Bars grouped by lane, so each dock row renders from its own list rather than filtering the
 *  whole set once per row (35 docks x 200 bars is the shape this avoids). */
export function groupByDock<T extends BoardBar | BoardBlock>(items: T[]): Map<string, T[]> {
  const map = new Map<string, T[]>()
  for (const item of items) {
    const list = map.get(item.dock_id)
    if (list) list.push(item)
    else map.set(item.dock_id, [item])
  }
  return map
}
