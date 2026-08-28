import { cva } from 'class-variance-authority'
import { CircleCheck, ClockFading, List, Timer } from 'lucide-react'
import type { LucideIcon } from 'lucide-react'
import { useRef } from 'react'

import { cn } from '@/shared/lib/utils'
import { spokenRemaining } from '../lib/format'
import { TTL_MS, usePromiseCountdown } from '../lib/use-promise-countdown'
import type { PromiseState } from '../lib/types'

/**
 * The promise-state chip — **the most important component in the product**
 * (`00-foundations/components.md` section 2). Four redundant encodings (U14):
 * **icon · label · border treatment · colour**.
 *
 * Driver surface is `filled`, **always** (`01-driver-chat/accessibility.md`). Note the corrected
 * rationale (amended 2026-08-27): the fill is *not* what survives glare — measured, the filled
 * grounds sit at 1.00–1.04:1 against the page. What survives is the **border treatment**
 * (dashed vs 2px-solid vs 1px-solid is a *shape* difference, immune to contrast compression),
 * the **icon shape**, and the **label text** at 4.84–9.90:1. `filled` stays mandatory because a
 * tint still helps in ordinary light and costs nothing; it is simply not load-bearing. Which is
 * why none of the three shape channels below may be "simplified" into colour alone.
 *
 * ## Icon-name deviation, recorded
 *
 * `00-foundations/iconography.md` line 56 names `clock-fade` for `PENDING_CONFIRMATION`.
 * **`lucide-react@1.34` has no such export** — the icon is `clock-fading` / `ClockFading`
 * (verified by grepping the installed `lucide-react.d.ts`, which has
 * `Clock`, `ClockAlert`, the four `ClockArrow…`, `ClockCheck`, `ClockFading`, `ClockPlus` — and
 * no `ClockFade`). Same
 * class of finding as E5.0's `ChartGantt` after Lucide's rename sweep, and the same handling:
 * use the real export, record the rename rather than silently substituting a different glyph.
 *
 * Icons are imported per-icon, never through the barrel
 * (`00-foundations/implementation-spec.md` section 3).
 */

const chip = cva(
  [
    'inline-flex items-center gap-1.5 rounded-sm px-2.5 py-1',
    // **14px, not text-label's 12px.** Two sources disagree and the later one is locked:
    // implementation-spec.md section 2.1's code sketch says `text-label` (12px), but section 6
    // Fork B -- decided by the owner 2026-08-27, after the render was measured -- says "the
    // chip is 14px", and 01-driver-chat/accessibility.md states a hard "no text below 14px on
    // this surface". The audit found the chip rendering at 11px, which made the single most
    // important component on the surface its third-smallest text. So: text-body's 14px with
    // text-label's weight and tracking, rather than text-label itself.
    'text-body font-semibold tracking-[0.04em] uppercase',
    // U31: layouts tolerate ~30% text expansion and grow VERTICALLY. No fixed height, and
    // `whitespace-normal` rather than `nowrap` so `PENDING CONFIRMATION` wraps to two lines
    // instead of being abbreviated (components.md section 2 forbids the abbreviation, not the
    // wrap).
    //
    // ⚠ `text-balance` was here and is deliberately GONE. Found by measuring the render, not by
    // reading this file: `tailwind-merge` puts `text-body` and `text-balance` in the same
    // conflict group (both are `text-*` and it cannot tell a custom font-size token from a
    // text-wrap keyword), so the later class won and **`text-body` was silently stripped from
    // the emitted class list**. Measured: the chip's rendered classes contained
    // `... uppercase whitespace-normal text-balance ...` with no font size at all, and it
    // computed to the inherited 16px. It happened to still clear the 14px floor, which is
    // exactly why this would have shipped: the most important component in the product had its
    // type size decided by a class-merging heuristic. Balanced wrapping is cosmetic; the locked
    // 14px is not, so the font size stays and the balance goes.
    'whitespace-normal',
  ],
  {
    variants: {
      state: {
        shown: 'bg-state-shown-bg text-state-shown-text border border-state-shown-border',
        // 2px DASHED is the "temporary" shape channel. Do not make it solid.
        held: 'bg-state-held-bg text-state-held-text border-2 border-dashed border-state-held-border',
        pending: 'bg-state-pending-bg text-state-pending-text border-2 border-state-pending-border',
        confirmed:
          'bg-state-confirmed-bg text-state-confirmed-text border-2 border-state-confirmed-border',
      },
      /** Expiry **replaces the countdown in place, it never removes it**
       *  (components.md section 3). The chip keeps its state identity and the numeric slot
       *  becomes the expired treatment, so the record persists. */
      expired: { true: 'bg-expired-bg text-expired-fg border-strong', false: '' },
    },
    defaultVariants: { state: 'shown', expired: false },
  },
)

const VARIANT: Record<PromiseState, 'shown' | 'held' | 'pending' | 'confirmed'> = {
  SHOWN: 'shown',
  HELD: 'held',
  PENDING_CONFIRMATION: 'pending',
  CONFIRMED: 'confirmed',
}

const ICON: Record<PromiseState, LucideIcon> = {
  SHOWN: List,
  HELD: Timer,
  PENDING_CONFIRMATION: ClockFading,
  CONFIRMED: CircleCheck,
}

/** **Never abbreviated.** If it does not fit, the container is too small. */
const LABEL: Record<PromiseState, string> = {
  SHOWN: 'Shown',
  HELD: 'Held',
  PENDING_CONFIRMATION: 'Pending confirmation',
  CONFIRMED: 'Confirmed',
}

const SPOKEN_THRESHOLD: Record<string, string> = {
  half: 'Half the time remaining.',
  fifth: 'Less than a fifth of the time remaining.',
  'ten-seconds': 'Ten seconds remaining.',
  expired: 'Expired.',
}

export type PromiseChipProps = {
  state: PromiseState
  /** ISO. Required for `HELD` and `PENDING_CONFIRMATION`, where the countdown is mandatory. */
  expiresAt?: string
  className?: string
}

/**
 * ARIA. **Not `role="status"` on the chip** — corrected at source 2026-08-27 in
 * `components.md` section 2 and recorded in `accessibility-behaviour.md`'s matrix as the one
 * collision in that matrix.
 *
 * Two matrix rows land on this one element and a single live region cannot serve both:
 *   - promise-state transition -> `assertive`, once, on the hard-swap
 *   - countdown               -> `polite`, throttled to 50% / 20% / 10s / expiry
 *
 * A live region re-announces its **entire contents** on any mutation, so `role="status"` around
 * a per-second numeric produces *"Held one twenty-three… Held one twenty-two…"* every second —
 * exactly what section 3 forbids.
 *
 * ## THREE regions, not the two the spec's markup sketch shows — found by rendering
 *
 * The sketch in `components.md` section 2 puts the state name inside the `role="alert"` node and
 * `aria-hidden` on everything visible. Built literally, that measured wrong in two ways at once:
 *
 * 1. **A thread list of three cards fired three assertive announcements on first paint.** The
 *    alert's content is written at mount, and mount is not a transition. §2's own wording says
 *    the regions must *"stay mounted and empty rather than being added and removed, so the
 *    announcement fires on content change rather than on insertion"* — so the alert has to start
 *    empty and only fill when the state actually changes. That needs the previous state, which
 *    is why `PromiseChip` tracks it in a ref.
 * 2. **With the alert empty, the chip then had no accessible name at all** — the visible label is
 *    `aria-hidden`, so a screen-reader user navigating the list would hear a dock and a time with
 *    no promise state. Which is the exact misread U14 exists to prevent.
 *
 * So: a **plain `sr-only` label** carries the name on navigation (no live role, announced only
 * when read), a `role="alert"` fires **only on a real transition**, and an `aria-live="polite"`
 * fires only on a threshold change. Accepted, minor, transient cost: for one announcement after a
 * transition the name and the alert say the same words. That is better than either silence or
 * announcing on load.
 *
 * ## No `key={state}` — and why the U75 hard-swap is still guaranteed
 *
 * The spec asks for `key={state}` to force a remount so the chip cannot morph between states. A
 * remount also resets the previous-state ref, which would make (1) above undetectable. It turns
 * out the key is not needed for the visual guarantee: **no chip property carries a transition or
 * an animation** (measured — `transition-property: all` is nowhere on this element and
 * `animation-name` is `none` except the deliberate HELD pulse), so re-rendering the same element
 * with new classes already produces an instantaneous swap at `--d-instant`. The key would have
 * bought nothing and cost the announcement. Recorded rather than silently dropped.
 *
 * The general lesson worth keeping: when two matrix rows resolve to one element, the element
 * needs one live region per row — plus, it turns out, one non-live label for the name.
 */
export function PromiseChip({ state, expiresAt, className }: PromiseChipProps) {
  const Icon = ICON[state]
  const wantsCountdown = state === 'HELD' || state === 'PENDING_CONFIRMATION'
  const justTransitioned = useJustTransitioned(state)

  return wantsCountdown && expiresAt ? (
    <CountingChip
      state={state}
      expiresAt={expiresAt}
      className={className}
      Icon={Icon}
      justTransitioned={justTransitioned}
    />
  ) : (
    <span className={cn(chip({ state: VARIANT[state] }), className)}>
      <Icon size={14} strokeWidth={2} aria-hidden="true" />
      <span aria-hidden="true">{LABEL[state]}</span>
      {/* name, always present, not a live region */}
      <span className="sr-only">{LABEL[state]}.</span>
      {/* transition, assertive, empty until the state actually changes */}
      <span role="alert" className="sr-only">
        {justTransitioned ? `${LABEL[state]}.` : ''}
      </span>
      <span aria-live="polite" className="sr-only" />
    </span>
  )
}

/** `true` on the render immediately after `state` changes, `false` on first mount. The whole
 *  point is that a first paint is not a transition. */
function useJustTransitioned(state: PromiseState): boolean {
  const previous = useRef<PromiseState | null>(null)
  const changed = previous.current !== null && previous.current !== state
  previous.current = state
  return changed
}

function CountingChip({
  state,
  expiresAt,
  className,
  Icon,
  justTransitioned,
}: {
  state: PromiseState
  expiresAt: string
  className?: string
  Icon: LucideIcon
  justTransitioned: boolean
}) {
  const c = usePromiseCountdown(state, expiresAt, TTL_MS[state] ?? 0)

  return (
    <span
      className={cn(
        chip({ state: VARIANT[state], expired: c.expired }),
        // The pulse is HELD-only and below-20%-only. Under prefers-reduced-motion the
        // `held-expiring` class is what theme.css REPLACES with a solid high-contrast border
        // plus an " · expiring" label -- the pulse is never merely dropped.
        c.pulsing && 'animate-held-pulse held-expiring',
        className,
      )}
    >
      <Icon size={14} strokeWidth={2} aria-hidden="true" />
      <span aria-hidden="true">{LABEL[state]}</span>
      <span
        aria-hidden="true"
        // --font-data + tabular-nums so the digits do not shift width as they tick. Never
        // animate the digit change (motion.md) -- ticks must read as discrete, so there is no
        // transition class here and there must not be one added.
        className={cn('font-mono tabular-nums', c.colorClass, c.weightClass)}
      >
        {c.label}
        {/*
          `remaining` on the long-TTL form only.

          `00-foundations/components.md` section 3's anatomy gives **two** shapes -- `⏱ 1:24` and
          `⏱ 14:32 remaining` -- without saying which applies when. Found by screenshotting: a
          15-minute PENDING chip rendered `PENDING CONFIRMATION 11:37` directly beside the state
          line's `decision by 18:59`, and `11:37` in that company reads as a wall-clock time, not
          as eleven minutes and thirty-seven seconds. That is R7's confusion returning in a
          different costume, on the state whose deadline matters for a full quarter of an hour.

          The suffix is chosen by the TOTAL TTL, not by the current value, so the label's shape
          never changes mid-countdown: a 90-second hold is always bare (`1:24` cannot be a clock
          time), a 15-minute pending window always carries the word. Matching the doc's own two
          examples.
        */}
        {(TTL_MS[state] ?? 0) >= 600_000 && !c.expired ? (
          <span className="font-sans font-normal normal-case"> remaining</span>
        ) : null}
      </span>
      {/* Offline the reading HOLDS at last-known rather than free-running (edge-cases.md
          section 10) -- the provider freezes the shared tick and `c.live` goes false.  The
          staleness MARKER is deliberately not drawn here: edge-cases.md section 10 puts it on
          the header state line (`⏱ HELD 1:24 · updated 2m ago`), and adding a second sub-14px
          word inside the chip is exactly what F1 was about. See `state-line.tsx`. */}

      {/* 0. the accessible NAME. Not a live region -- read on navigation, never announced
             spontaneously. Without this the chip is nameless, because everything visible above
             is aria-hidden. */}
      <span className="sr-only">{`${LABEL[state]}. ${spokenRemaining(c.remainingMs)}.`}</span>

      {/* 1. state transition — assertive, and EMPTY until the state actually changes. Mount is
             not a transition: three thread cards on first paint must not shout three times. */}
      <span role="alert" className="sr-only">
        {justTransitioned ? `${LABEL[state]}. ${spokenRemaining(c.remainingMs)}.` : ''}
      </span>

      {/* 2. countdown thresholds — polite, four times per hold, NEVER per tick. Gated on the
             threshold value, so the content only changes when a band is crossed. */}
      <span aria-live="polite" className="sr-only">
        {c.threshold === 'none' ? '' : (SPOKEN_THRESHOLD[c.threshold] ?? '')}
      </span>
    </span>
  )
}
