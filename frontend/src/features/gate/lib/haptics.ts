/**
 * Gate/yard haptics.
 *
 * Two patterns only, both named in this surface's own mockup notes: a **15ms pulse on a recorded
 * gate event** (`mockup.html` screen 14's non-visual note) and a **300ms pulse on a rejected gate
 * action** (screen 17's note, which is careful to say the rejection pattern does *not* fire for
 * `DOCK_MISMATCH`, because nothing was rejected there -- the deviation was recorded).
 *
 * A separate table from the driver surface's on purpose: the values differ (15ms vs the driver's
 * 10ms tap), the semantics differ, and a shared table would invite a call site here to reach for a
 * driver-only rhythm like `holdGranted` that has no meaning on a kiosk.
 *
 * **Two constraints, taken from the driver surface's own verified findings rather than re-derived:**
 * `navigator.vibrate` is limited-availability, not Baseline (no Safari/iOS at all), and it requires
 * sticky user activation. Both hold here trivially -- every haptic on this surface fires directly
 * from an officer's tap, never from a timer -- but the degradation rule still applies: haptics are
 * never the only signal. Every one of these is paired with the outcome banner that renders anyway.
 */
export const HAPTIC = {
  /** A gate event was genuinely recorded. Includes `DOCK_MISMATCH`, which is a recorded deviation
   *  rather than a rejection. */
  recorded: [15],
  /** The action was refused and nothing the officer intended happened:
   *  `NO_ACTIVE_APPOINTMENT`, `DOCK_OCCUPIED`, `INVALID_TRANSITION`, or a transport failure. */
  rejected: [300],
} as const satisfies Record<string, readonly number[]>

export type HapticName = keyof typeof HAPTIC

/** Never throws; callers ignore the return value. Some Android WebViews throw rather than
 *  returning false when vibration is disabled at the OS level, and a failed haptic must never
 *  surface to an officer. */
export function haptic(name: HapticName): boolean {
  if (typeof navigator === 'undefined' || typeof navigator.vibrate !== 'function') return false
  try {
    return navigator.vibrate(HAPTIC[name] as unknown as number[])
  } catch {
    return false
  }
}
