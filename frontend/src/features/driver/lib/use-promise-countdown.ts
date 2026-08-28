import { useEffect, useRef } from 'react'

import { useCountdown, type CountdownReading } from '@/shared/lib/countdown'
import { haptic } from './haptics'
import type { PromiseState } from './types'

/**
 * ONE reading of a promise's countdown, shared by the chip, the option card's inline line and
 * the header state line.
 *
 * **This exists because of a measured defect, not for tidiness.** `implementation-spec.md`
 * section 5.3-R4: in the reference mockup the chip's countdown and the option card's inline
 * countdown were driven by two different rules, and at the *same instant* on the same 46-second
 * hold they rendered `rgb(220,38,38)` (red-600, urgent) and `rgb(180,83,9)` (amber-700, rest)
 * — two renderings of one hold showing different urgency simultaneously, on the surface's most
 * consequential component. It is invisible in markup and only appears ~37 seconds into a live
 * render.
 *
 * Making the band a single derived value means R4 cannot recur: there is no second rule to
 * drift from. Treat this as a regression test target, not a one-off fix (spec section 7 item 9).
 *
 * Bands are `00-foundations/components.md` section 3's table, all six rows.
 */

export type CountdownBand = 'rest' | 'mid' | 'urgent' | 'final' | 'expired'

export type PromiseCountdown = CountdownReading & {
  band: CountdownBand
  /** Tailwind text-colour class for the numeric, from the band. Never a hex at a call site. */
  colorClass: string
  /** `font-semibold` below 20%, per the table's weight column. */
  weightClass: string
  /** True only for `HELD` below 20% — the pulse is never applied to
   *  `PENDING_CONFIRMATION`, whose TTL is fifteen minutes (see the keyframe's comment). */
  pulsing: boolean
}

/**
 * The 20–50% amber band is a **one-step shift inside the hue a `HELD` chip is already painted
 * in** (`--color-state-held-text` is amber-700 #B45309, `--color-urgent-mid` is amber-600
 * #D97706). The design measured this and flagged it (Fork B / section 2.2); the owner's
 * resolution was to keep the palette and fix the rationale, so the band is implemented as
 * specified and the near-invisibility on `HELD` specifically is a known, recorded limitation
 * rather than something this hook quietly "improves".
 */
const BAND_COLOR: Record<CountdownBand, string> = {
  rest: '', // the state's own text token, inherited from the chip — never re-declared here
  mid: 'text-urgent-mid',
  urgent: 'text-urgent',
  final: 'text-urgent',
  expired: 'text-expired-fg',
}

function bandFor(reading: CountdownReading): CountdownBand {
  // Derived from useCountdown's own thresholds rather than recomputing the arithmetic, so the
  // announcement throttle and the colour band can never disagree about where 20% is.
  switch (reading.threshold) {
    case 'expired':
      return 'expired'
    case 'ten-seconds':
      return 'final'
    case 'fifth':
      return 'urgent'
    case 'half':
      return 'mid'
    case 'none':
      return 'rest'
  }
}

export function usePromiseCountdown(
  state: PromiseState,
  expiresAtIso: string,
  totalMs: number,
): PromiseCountdown {
  const reading = useCountdown(expiresAtIso, totalMs)
  const band = bandFor(reading)

  // Haptics at 10s and 5s, and 400ms on lapse (flows-and-states.md "Haptics"). Fired from the
  // shared tick rather than a per-instance timer, and latched so a re-render inside the same
  // second cannot double-buzz. See haptics.ts on why a server-pushed hold may not vibrate at
  // all: sticky user activation.
  const fired = useRef<Set<string>>(new Set())
  const secondsLeft = Math.ceil(reading.remainingMs / 1000)

  useEffect(() => {
    if (!reading.live) return
    const mark = (key: string) => {
      if (fired.current.has(key)) return false
      fired.current.add(key)
      return true
    }
    if (secondsLeft === 10 && mark('10s')) haptic('holdTenSeconds')
    if (secondsLeft === 5 && mark('5s')) haptic('holdFiveSeconds')
    if (reading.expired && mark('expired')) haptic('holdLapsed')
  }, [secondsLeft, reading.expired, reading.live])

  return {
    ...reading,
    band,
    colorClass: BAND_COLOR[band],
    weightClass: band === 'urgent' || band === 'final' ? 'font-semibold' : 'font-normal',
    pulsing: state === 'HELD' && (band === 'urgent' || band === 'final'),
  }
}

/** Total TTLs, from the design decisions rather than a magic number at a call site.
 *  D2: a hold is 90 seconds. D9: a pending request is 15 minutes. */
export const TTL_MS: Partial<Record<PromiseState, number>> = {
  HELD: 90_000,
  PENDING_CONFIRMATION: 900_000,
}
