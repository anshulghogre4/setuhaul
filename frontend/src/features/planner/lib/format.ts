import { isDockBlockedConflict } from './types'
import type { PlannerQueueRow } from './types'

/**
 * Formatting for the 30-second row.
 *
 * `Intl` with `en-IN` **from the first component, not retrofitted** -- `implementation-spec.md`
 * section 7 item 12, raised as a real build requirement in section 5.4 after the mockup was found
 * to hardcode every date, time and duration ("Tue 4 Aug" x57). The formatters are module-level
 * singletons because constructing an `Intl.DateTimeFormat` per cell is measurably expensive and
 * this surface renders up to 35 rows x 4 time values.
 */

const DATE_FMT = new Intl.DateTimeFormat('en-IN', {
  weekday: 'short',
  day: 'numeric',
  month: 'short',
})

const TIME_FMT = new Intl.DateTimeFormat('en-IN', {
  hour: '2-digit',
  minute: '2-digit',
  hour12: false,
})

export function formatTime(iso: string): string {
  return TIME_FMT.format(new Date(iso))
}

export function formatDate(iso: string): string {
  return DATE_FMT.format(new Date(iso))
}

/**
 * The requested interval, **always dated**.
 *
 * `screens.md` section 2: *"Dock + dated time range -- always dated, per the multi-day-horizon
 * rule already governing every other surface"*, and `mockup.html` State 1's own correction note
 * calls a bare `D1 . 13:00-14:15` *"an operational time with no date, which is the wrong-day
 * booking hazard the whole product designs against"*. There is deliberately no un-dated variant
 * of this function for a caller to reach for.
 */
export function formatInterval(row: PlannerQueueRow): string {
  const dock = row.dock_code ?? row.dock_id
  return `${dock} · ${formatDate(row.interval_start)} · ${formatTime(row.interval_start)}–${formatTime(row.interval_end)}`
}

/** The driver's own limit -- a time, but rendered with its date in the `title` for the same
 *  wrong-day reason the interval carries one inline. */
export function formatLimit(iso: string): { text: string; title: string } {
  return {
    text: formatTime(iso),
    title: `Latest arrival the driver can make — ${formatDate(iso)} · ${formatTime(iso)}`,
  }
}

/* ---------------------------------------------------------------------------------------------
 * TTL urgency
 * ------------------------------------------------------------------------------------------- */

export type TtlBand = 'rest' | 'mid' | 'urgent' | 'expired'

/**
 * `00-foundations/color.md`'s TTL-urgency table, `PENDING` column, all four rows that apply to a
 * 15-minute D9 clock (the `< 10s` row is `HELD` only and has no meaning here):
 *
 *   > 50%   -> `blue-600`   = `--color-state-pending-text`
 *   20-50%  -> `amber-700`  = `--color-urgent-mid`
 *   < 20%   -> `red-600`    = `--color-urgent`, plus `font-weight: 600`
 *   Expired -> `neutral-500` on `neutral-100`, struck through
 *
 * The 20-50% band reads `--color-urgent-mid`, which `theme.css` carries at `amber-700` rather
 * than `color.md`'s literal `amber-600` -- that raise was E5.3's own Fork E fix (a 12px countdown
 * is normal text, and `amber-600` measures 3.2:1). Consuming the token rather than the doc's raw
 * value is what keeps this row correct.
 *
 * The band is derived from the fraction remaining, not from a duplicated arithmetic rule: the
 * driver surface learned this the hard way (`use-promise-countdown.ts`'s R4 note -- two rules for
 * one countdown rendered two different urgencies of the same hold at the same instant).
 */
export function ttlBand(remainingMs: number, totalMs: number): TtlBand {
  if (remainingMs <= 0) return 'expired'
  if (totalMs > 0 && remainingMs <= totalMs * 0.2) return 'urgent'
  if (totalMs > 0 && remainingMs <= totalMs * 0.5) return 'mid'
  return 'rest'
}

export const TTL_BAND_CLASS: Record<TtlBand, string> = {
  rest: 'text-state-pending-text',
  mid: 'text-urgent-mid',
  urgent: 'text-urgent font-semibold',
  expired: 'text-expired-fg line-through',
}

/* ---------------------------------------------------------------------------------------------
 * Priority marker
 * ------------------------------------------------------------------------------------------- */

/**
 * The row's left edge. A neutral **value** ramp, never a hue (U10, `color.md`: *"Priority as a
 * value ramp rather than a hue is the non-obvious call ... it leaves red exclusively meaning
 * danger, so a CRITICAL row never looks like a failing row"*).
 *
 * An unrecognised priority falls back to NORMAL rather than to no marker at all: a missing left
 * edge would read as "this row has no priority", which is a different and false claim.
 */
export function priorityMarkerClass(priorityCode: string): string {
  switch (priorityCode.toUpperCase()) {
    case 'CRITICAL':
      return 'bg-priority-critical'
    case 'HIGH':
      return 'bg-priority-high'
    case 'LOW':
      return 'bg-priority-low'
    default:
      return 'bg-priority-normal'
  }
}

/* ---------------------------------------------------------------------------------------------
 * Displacement
 * ------------------------------------------------------------------------------------------- */

/**
 * Section 7.3's single most important field, in words.
 *
 * `components.md` section 1: this column **never truncates**, even under the ellipsis rule every
 * other cell follows -- *"a truncated warning is a warning that failed at its one job"*. So every
 * conflicting shipment is named, however many there are; the cell wraps rather than clipping.
 *
 * A hold has no shipment-facing id of its own in the conflict payload beyond `shipment_id`, so
 * that is what is named; `claim_source` distinguishes an appointment from a D2 hold, which is the
 * difference between "another truck is booked here" and "another truck is mid-booking here".
 *
 * ## Two legs since issue #88, and they are different sentences
 *
 * `displacement.conflicts` now carries both of the things the write path refuses on, each tagged
 * with `conflict_type`:
 *
 *  - `INTERVAL_CONFLICT` -- another live claim overlaps. Somebody **is** displaced, and naming them
 *    is the whole job of this column.
 *  - `DOCK_BLOCKED` -- a `dock_status_events` outage overlaps. **Nobody is displaced**; the dock is
 *    offline. This leg carries no `shipment_id` at all.
 *
 * Before this fix the mapper read `c.shipment_id` off every entry, so a blocked dock rendered
 * *"Confirming this displaces undefined."* -- the literal defect #88's row-side change surfaced.
 * Worse than cosmetic on this column specifically: section 7.3 calls it "the single most important
 * field", and `undefined` in it is a planner being told a third party is at risk when the real
 * answer is that the dock cannot take anyone.
 *
 * The two are reported as separate clauses rather than one merged list, because they have
 * different recoveries: a displacement is a harm the planner may still choose to cause, an outage
 * is not something confirming can push through at all.
 */
export function describeDisplacement(row: PlannerQueueRow): string {
  if (row.displacement.status === 'NONE' || row.displacement.conflicts.length === 0) {
    return 'conflicts with none'
  }

  const displaced: string[] = []
  const blocked: string[] = []
  for (const conflict of row.displacement.conflicts) {
    if (isDockBlockedConflict(conflict)) {
      // The block's own identifiers, never a shipment. `reason` is free text and nullable, so
      // `event_type` is the fallback -- the same order `dock-board.tsx`'s BlockMarker uses, so the
      // board and the row name one outage the same way.
      blocked.push(conflict.reason ?? conflict.event_type)
    } else {
      displaced.push(
        conflict.claim_source === 'dock_occupancy_hold'
          ? `${conflict.shipment_id} (holding)`
          : conflict.shipment_id,
      )
    }
  }

  const clauses: string[] = []
  if (displaced.length > 0) clauses.push(`Confirming this displaces ${displaced.join(', ')}.`)
  if (blocked.length > 0) {
    clauses.push(
      blocked.length === 1
        ? `This dock is blocked (${blocked[0]}).`
        : `This dock is blocked (${blocked.join('; ')}).`,
    )
  }
  return clauses.join(' ')
}
