import { Loader, WifiOff } from 'lucide-react'
import { useState } from 'react'

import { cn } from '@/shared/lib/utils'
import { copy } from '../lib/copy'
import { formatDockAndDate, formatLocalDate, formatRange, formatTime } from '../lib/format'
import { haptic } from '../lib/haptics'
import { heldStateEnabled } from '../lib/flags'
import { TTL_MS, usePromiseCountdown } from '../lib/use-promise-countdown'
import type { DriverOption, OptionCardState } from '../lib/types'

/**
 * The option card — **the single most consequential component on this surface** (U16, U48).
 * Anatomy in `screens.md` section 4, states in `01-driver-chat/components.md` section 2.
 *
 * ```
 * ┌──────────────────────────────┐
 * │ Dock D4 · Tue 4 Aug          │  ← dock + date, never separable
 * │ 12:15 – 13:30                │  ← en dash, --font-data, tabular
 * │ soonest                      │  ← ONE differentiator, server-computed
 * └──────────────────────────────┘
 * ```
 *
 * ## Three rules that are code here, not review notes
 *
 * 1. **No ordinal, ever** — not displayed, not accepted, **not in the DOM**. That is what makes
 *    section 7.2b's ordinal trap unreachable rather than merely guarded, and it is why the
 *    accessible name is built from dock + time and never from an index. A screen-reader user who
 *    says "select option 2" to a voice assistant must not be able to act on a stale position.
 *
 * 2. **The differentiator is read, never computed** (U48). It arrives as
 *    `FeasibleSlotOption.differentiator`, added server-side by E5.1 Fork A
 *    (`backend/app/scheduling/feasibility.py::assign_differentiators`, closed vocabulary
 *    `soonest` / `no waiting` / `most buffer`). **`''` omits the line** — U81's blank-vs-zero
 *    rule; there is no fourth comparative fact in the vocabulary and a card with no
 *    differentiator is honest where an invented one is not. Nothing here inspects
 *    `ranking_factors`.
 *
 * 3. **A hold does not dim its siblings.** `01-driver-chat/components.md` section 2 gained the
 *    *"Sibling of a held card"* row on 2026-08-27 precisely because its absence let the mockup
 *    render the two siblings of a `HELD` card as `dead` (struck through, 40%) while a quick reply
 *    beneath them said *"Choose a different one"* — telling the driver those slots were dead and
 *    inviting them to pick one, simultaneously. So there is deliberately **no `sibling` state
 *    below**: a sibling is `default`. `Committing` is the one moment the set dims, because
 *    nothing is decided yet during a tap in flight.
 *
 * ## `touch-action` and the tap delay
 *
 * `touch-action: manipulation` removes the ~300ms double-tap-to-zoom delay on **the most
 * consequential tap in the product**. `theme.css` already sets it on `body`, and it inherits —
 * so it is not repeated per card. `-webkit-tap-highlight-color` is likewise already handled
 * there for `button`.
 */

/** The eight treatments. `dead` (struck through) is visually distinct from `off` (dimmed but not
 *  struck) — F8's collapse was that four states shared a bare 40% opacity, two of them with no
 *  status line at all, which made them literally indistinguishable. Every dimmed state below
 *  therefore renders a **full-opacity status line** naming which one it is. */
const card = {
  base: [
    'relative block w-full min-h-16 rounded-lg border p-4 text-left',
    'bg-card border-input',
    // No lift, no scale (motion.md). Colour only.
    'transition-colors duration-(--d-fast) ease-(--e-out)',
    'focus-visible:outline-2 focus-visible:outline-ring focus-visible:outline-offset-2',
  ].join(' '),
  default: 'hover:bg-hover active:bg-hover',
  pressed: 'bg-hover',
  committing: 'opacity-40 pointer-events-none',
  held: 'border-2 border-dashed border-state-held-border bg-state-held-bg',
  lost: 'opacity-40 pointer-events-none',
  withdrawn: 'opacity-40 pointer-events-none',
  offline: 'opacity-40 pointer-events-none',
  superseded: 'opacity-40 pointer-events-none',
} as const

/** Struck-through states, i.e. "this option is gone". Never applied to a sibling of a held card
 *  and never to Committing. */
const STRUCK: ReadonlySet<OptionCardState> = new Set<OptionCardState>(['lost', 'withdrawn'])

export type OptionCardProps = {
  option: DriverOption
  state?: OptionCardState
  /** ISO, `held` only. */
  heldUntil?: string
  onSelect?: (option: DriverOption) => void
}

export function OptionCard({ option, state = 'default', heldUntil, onSelect }: OptionCardProps) {
  const [pressed, setPressed] = useState(false)

  // Issue #53: `held` cannot be reached from a real server state today. If the flag is off and
  // something asks for it anyway, render `default` rather than a HELD chip over what is really
  // already a PENDING_CONFIRMATION -- components.md section 2 calls that a broken promise in the
  // business sense. Fail closed, loudly in dev.
  let effective = state
  if (state === 'held' && !heldStateEnabled) {
    if (import.meta.env.DEV) {
      console.warn('[driver] option-card asked for `held` while heldStateEnabled is false (#53)')
    }
    effective = 'default'
  }

  const interactive = effective === 'default' || effective === 'pressed'
  const struck = STRUCK.has(effective)
  const status = STATUS_LINE[effective]

  return (
    <button
      type="button"
      // role="button" is implicit on <button>; using a real button rather than a div with a role
      // is what the web-design-guidelines pass flagged (0 of 34 cards in the mockup carried
      // either). It also gets keyboard activation and focus-visible for free.
      disabled={!interactive}
      aria-label={accessibleName(option, effective)}
      onPointerDown={() => {
        if (!interactive) return
        setPressed(true)
        // Fires on touch-DOWN, not on resolution: components.md section 2's stated reason is
        // perceived responsiveness. Degrades silently where unsupported (see haptics.ts).
        haptic('optionTap')
      }}
      onPointerUp={() => setPressed(false)}
      onPointerCancel={() => setPressed(false)}
      onClick={() => {
        // Tapping a superseded or disabled card does nothing AND gives no haptic -- silence is
        // the correct feedback for a non-target (components.md section 2).
        if (!interactive) return
        onSelect?.(option)
      }}
      className={cn(
        card.base,
        card[effective],
        pressed && interactive && card.pressed,
        // 8px minimum between adjacent targets: two option cards 2px apart is a mis-tap that
        // commits the wrong dock (accessibility.md, "Touch targets").
        'mt-2 first:mt-0',
      )}
    >
      <span className={cn('block text-body-lg font-semibold', struck && 'line-through')}>
        {formatDockAndDate(option.dockCode, option.slotLocalDate)}
      </span>
      <span
        className={cn(
          'mt-0.5 block font-mono text-body tabular-nums text-muted-foreground',
          struck && 'line-through',
        )}
      >
        {formatRange(option.feasibleStartTs, option.feasibleEndTs)}
      </span>

      {/* ONE differentiator line only. Three cards each carrying a full receipt is unreadable
          on a phone at a roadside; the full receipt is one tap away via the help affordance.
          Replaced by the inline spinner while committing (components.md section 2). */}
      {effective === 'committing' ? (
        <span className="mt-1 flex items-center gap-1.5 text-body text-muted-foreground">
          {/* A spinner is correct HERE specifically: components.md section 2 names an inline
              spinner for Committing, and section 13's "skeleton, never a spinner" rule is about
              page/region loading, not a ~1s in-flight action on one control. `data-motion` opts
              it into the reduced-motion rule -- the rotation is decoration; "Sending…" carries
              the signal. */}
          <Loader
            size={14}
            strokeWidth={2}
            aria-hidden="true"
            data-motion="decorative"
            className="animate-spin"
          />
          Sending…
        </span>
      ) : option.differentiator ? (
        <span className="mt-1 block text-body text-muted-foreground">{option.differentiator}</span>
      ) : null}

      {/* The held card's own inline countdown. Goes through the SAME hook as the chip, so R4
          -- chip red while the card still showed amber at the same instant -- cannot recur. */}
      {effective === 'held' && heldUntil ? <HeldLine expiresAt={heldUntil} /> : null}

      {/* Full-opacity status line on every dimmed state (F8). `opacity-100` is deliberate: it
          survives the card's own 40%, which is what makes Lost distinguishable from
          Superseded instead of both being an unlabelled grey rectangle. */}
      {status ? (
        <span className="mt-1 flex items-center gap-1.5 text-body font-medium text-foreground opacity-100">
          {effective === 'offline' ? (
            <WifiOff size={14} strokeWidth={2} aria-hidden="true" />
          ) : null}
          {status}
        </span>
      ) : null}
    </button>
  )
}

/** Status copy per dimmed state. Not in `copy.ts` for the three that are pure state names —
 *  they are not sentences and have no template; the offline one IS in `copy.ts` because it is a
 *  driver-facing reason. */
const STATUS_LINE: Partial<Record<OptionCardState, string>> = {
  lost: 'Taken by another driver',
  withdrawn: 'No longer available',
  offline: copy.offlineCardReason,
  superseded: 'Replaced by newer options',
}

function HeldLine({ expiresAt }: { expiresAt: string }) {
  const c = usePromiseCountdown('HELD', expiresAt, TTL_MS.HELD ?? 90_000)
  return (
    <span className="mt-1 flex items-center gap-1.5 text-body">
      <span className="text-state-held-text">Held for you</span>
      <span aria-hidden="true" className={cn('font-mono tabular-nums', c.colorClass, c.weightClass)}>
        {c.label}
      </span>
    </span>
  )
}

/**
 * The full accessible name — `accessibility.md`, "Screen reader":
 *   *"Dock D4, Tuesday 4 August, 12:15 to 13:30, soonest. Tap to hold for 90 seconds."*
 *
 * **Never positional.** No "option 2 of 3" anywhere, which is the ordinal U16 removed.
 * "to" rather than the en dash, because a screen reader reads `–` as nothing or as "dash".
 */
function accessibleName(option: DriverOption, state: OptionCardState): string {
  const bits = [
    `Dock ${option.dockCode}`,
    formatLocalDate(option.slotLocalDate),
    `${formatTime(option.feasibleStartTs)} to ${formatTime(option.feasibleEndTs)}`,
  ]
  if (option.differentiator) bits.push(option.differentiator)
  const subject = bits.filter(Boolean).join(', ')

  switch (state) {
    case 'default':
    case 'pressed':
      // 90 seconds is D2's hold window. Stated in the label because it is the consequence of
      // the tap, and a driver deserves to know what a tap costs before making it.
      return heldStateEnabled
        ? `${subject}. Tap to hold for 90 seconds.`
        : `${subject}. Tap to request this slot.`
    case 'committing':
      return `${subject}. Sending.`
    case 'held':
      return `${subject}. Held for you.`
    default:
      return `${subject}. ${STATUS_LINE[state] ?? 'Not selectable'}.`
  }
}
