import { CircleCheck, ClockFading, Info, Timer } from 'lucide-react'

import { Popover, PopoverContent, PopoverTrigger } from '@/shared/ui/popover'
import { cn } from '@/shared/lib/utils'
import { copy } from '../lib/copy'
import { formatTime } from '../lib/format'
import { TTL_MS, usePromiseCountdown } from '../lib/use-promise-countdown'
import type { PromiseState } from '../lib/types'

/**
 * The persistent state line — conversation header row two
 * (`01-driver-chat/components.md` section 6, `screens.md` section 2).
 *
 * Present **at all times**, not only when the establishing message is on screen: a driver who
 * scrolls up to re-read something must not lose sight of a hold burning down. Tapping scrolls
 * the transcript back to the message that established the state.
 *
 * When there is no active promise the line is **hidden entirely** and the header is one row —
 * not an empty row, and not "no promise" as text.
 *
 * ## R7, and which of two sources wins
 *
 * `01-driver-chat/components.md` section 6 specifies `◷ PENDING · decision by 11:57` — an
 * absolute deadline, **no countdown**. `00-foundations/components.md` section 3 marks the
 * countdown **mandatory** for `PENDING_CONFIRMATION`. The mockup rendered both and broke
 * (R7: *"PENDING CONFIRMATION 12:44 · DECISION BY 11:57"*, a relative countdown and an absolute
 * deadline meaning the same thing, with an orphaned middot).
 *
 * Resolved the way the fix pass resolved it: **the countdown lives on the chip** (where section
 * 3's mandate applies) **and the absolute deadline lives beside it on the state line** (where
 * section 6's wording applies). One time expression per element, two elements, no duplication —
 * and the state word is never abbreviated.
 *
 * Truncation order is specified and is not the browser default: **dock/date truncate before the
 * state word**. That is why the state word sits in a `shrink-0` span and the operational detail
 * gets `min-w-0 truncate`.
 */

const ICON = {
  SHOWN: null,
  HELD: Timer,
  PENDING_CONFIRMATION: ClockFading,
  CONFIRMED: CircleCheck,
} as const

const HELP: Record<PromiseState, string> = {
  SHOWN: copy.helpShown,
  HELD: copy.helpHeld,
  PENDING_CONFIRMATION: copy.helpPending,
  CONFIRMED: copy.helpConfirmed,
}

export type StateLineProps = {
  /** `null` hides the whole row. */
  state: PromiseState | null
  /** ISO. The deadline shown for `PENDING_CONFIRMATION` and the countdown source for `HELD`. */
  expiresAt?: string
  /** "Dock D1 · Tue 4 Aug 13:00" — dock and dated range, never a bare time. */
  operationalLine?: string
  /** Minutes since the last successful sync. Rendered only when offline (U68). */
  staleMinutes?: number
  onScrollToOrigin?: () => void
}

export function StateLine({
  state,
  expiresAt,
  operationalLine,
  staleMinutes,
  onScrollToOrigin,
}: StateLineProps) {
  if (state === null) return null

  const Icon = ICON[state]

  return (
    <div className="flex min-h-12 items-center gap-2 px-4">
      <button
        type="button"
        onClick={onScrollToOrigin}
        // An explicit name, because the button's own text is a status, not an action. Measured
        // without it, the accessible name came out as the concatenated status with no separator
        // spacing -- "PENDING · decision by 18:48· Dock D1 · ..." -- which says nothing about
        // what tapping does. accessibility-behaviour.md's focus contract requires the target of
        // an interaction to be stated, not inferred.
        aria-label="Go to the message that set this state"
        // 48px min block-size so the row itself clears the touch floor even though its visual
        // content is a single line of text (R8's class of defect: a real target measured
        // 18x6.9 against its own stated 48x48).
        className={cn(
          'flex min-h-12 min-w-0 flex-1 items-center gap-2 rounded-md text-left',
          'text-body text-foreground',
          'focus-visible:outline-2 focus-visible:outline-ring focus-visible:outline-offset-2',
        )}
      >
        {Icon ? <Icon size={16} strokeWidth={2} aria-hidden="true" className="shrink-0" /> : null}
        {/* shrink-0: the state word never truncates. */}
        <span className="shrink-0 font-semibold">{stateWord(state, expiresAt)}</span>
        {/* HELD is the one state whose state line carries a live numeric: `⏱ HELD 1:24`
            (components.md section 6). PENDING carries its ABSOLUTE deadline in the state word
            instead -- one time expression per element, which is R7's fix. */}
        {state === 'HELD' && expiresAt ? <StateLineCountdown expiresAt={expiresAt} /> : null}
        {operationalLine ? (
          <span className="min-w-0 truncate text-muted-foreground">· {operationalLine}</span>
        ) : null}
        {typeof staleMinutes === 'number' ? (
          <span className="shrink-0 text-muted-foreground">· {copy.staleness(staleMinutes)}</span>
        ) : null}
      </button>

      {/* The one place this surface uses the shared help affordance (U73). This is the driver's
          ENTIRE help surface -- there is no FAQ -- and the four state explanations are the thing
          most worth explaining in the whole product. 44x44 hit area around a 14px glyph
          (accessibility.md's touch-target table). */}
      <Popover>
        <PopoverTrigger
          className="grid size-11 shrink-0 place-items-center rounded-md text-subtle-foreground focus-visible:outline-2 focus-visible:outline-ring focus-visible:outline-offset-2"
          aria-label={`What does ${state.replace(/_/g, ' ').toLowerCase()} mean?`}
        >
          <Info size={14} strokeWidth={2} aria-hidden="true" />
        </PopoverTrigger>
        <PopoverContent className="max-w-[36ch] text-body">{HELP[state]}</PopoverContent>
      </Popover>
    </div>
  )
}

/** `HELD 1:24` / `PENDING · decision by 11:57` / `CONFIRMED` — the state word plus at most ONE
 *  time expression, per R7. */
function stateWord(state: PromiseState, expiresAt?: string): string {
  switch (state) {
    case 'SHOWN':
      return copy.stateLineShown
    case 'HELD':
      return copy.stateLineHeld
    case 'PENDING_CONFIRMATION':
      return expiresAt ? copy.stateLinePending(formatTime(expiresAt)) : 'PENDING CONFIRMATION'
    case 'CONFIRMED':
      return 'CONFIRMED'
  }
}

/**
 * The `HELD` countdown as it appears on the state line. Split out so the numeric goes through
 * the same `usePromiseCountdown` band as the chip and the option card (R4 — one rule, no
 * possible disagreement).
 */
export function StateLineCountdown({ expiresAt }: { expiresAt: string }) {
  const c = usePromiseCountdown('HELD', expiresAt, TTL_MS.HELD ?? 90_000)
  return (
    <span aria-hidden="true" className={cn('font-mono tabular-nums', c.colorClass, c.weightClass)}>
      {c.label}
    </span>
  )
}
