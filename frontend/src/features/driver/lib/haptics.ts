/**
 * Haptics (U21) — `flows-and-states.md` "Haptics" and `accessibility.md` "Haptics as an
 * accessibility channel".
 *
 * These are **not polish**. They are the channel that works when the screen does not: phone
 * face-down on the dash, screen unreadable in glare, driver mid-call with dispatch. No audio
 * anywhere (U21) — a truck cab is loud and the phone is usually not being looked at.
 *
 * ## Two real constraints, both verified rather than assumed
 *
 * 1. **`navigator.vibrate` is "limited availability", not Baseline** (MDN, fetched
 *    2026-08-27): Chrome Android supports it, Safari/iOS does not, at all. So this degrades
 *    silently and **haptics are never the only signal** — every pattern below is paired with
 *    a visual change (the countdown colour band, the pulse, the card mutation).
 *
 * 2. **Sticky user activation is required** (same MDN page: *"the user has to interact with the
 *    page or a UI element in order for this feature to work"*). This matters specifically for
 *    the timer-driven patterns: `holdTenSeconds` / `holdFiveSeconds` / `holdLapsed` fire from
 *    the shared 1 Hz tick, not from a tap. In the designed flow the driver has already tapped
 *    an option card to create the hold, so the page has sticky activation and they work — but a
 *    hold or a confirmation that arrives *server-pushed*, with no prior interaction on that page
 *    load, will silently not vibrate. That is an accepted, stated limitation, not a bug to chase:
 *    the visual signal carries it.
 */

/** Every pattern in `flows-and-states.md`'s table, verbatim, in one place so no call site
 *  invents a rhythm. Milliseconds; odd indices are pauses. */
export const HAPTIC = {
  /** Option card tapped. Fires on touch-down, not on resolution — the perceived-responsiveness
   *  reason `01-driver-chat/components.md` section 2 gives for the Pressed state. */
  optionTap: [10],
  /** Hold granted. Behind `heldStateEnabled` (#53) like everything else HELD. */
  holdGranted: [10, 40, 10],
  holdTenSeconds: [200],
  holdFiveSeconds: [200, 100, 200],
  holdLapsed: [400],
  confirmed: [10, 40, 10, 40, 10],
  sendFailed: [300],
} as const satisfies Record<string, readonly number[]>

export type HapticName = keyof typeof HAPTIC

/**
 * Fire a pattern. Returns whether the platform accepted it, which callers ignore — the point
 * of the return value is that this function never throws and never needs a try/catch at the
 * call site.
 *
 * **No penalty pattern on `SLOT_CONFLICT`** (`edge-cases.md` section 3: *"losing a race is not
 * the driver's error"*). There is deliberately no `lostRace` key above; if one appears here in
 * future, that is a design change, not an omission being fixed.
 */
export function haptic(name: HapticName): boolean {
  if (typeof navigator === 'undefined' || typeof navigator.vibrate !== 'function') return false
  try {
    return navigator.vibrate(HAPTIC[name] as unknown as number[])
  } catch {
    // Some Android WebViews throw rather than returning false when vibration is disabled at
    // the OS level. Swallowed on purpose: a failed haptic must never surface to a driver.
    return false
  }
}
