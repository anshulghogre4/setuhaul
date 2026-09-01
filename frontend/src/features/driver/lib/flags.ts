/**
 * Driver-surface feature flags.
 *
 * Named for the DEPENDENCY, not for the feature, so it is obvious what removes a flag
 * rather than obvious what it hides (E5.1 implementation-spec section 7, "Feature flag").
 */

/**
 * Gates the four `HELD`-state screens: screen 5 (HELD, 90s live), screen 15 (hold lapsed),
 * the Held column of screen 9's option-card state matrix, and the `HELD` branch of screen 1's
 * thread card.
 *
 * **ON since 2026-08-31.** All three of the previous exit criteria are met, and the consumption
 * work they implied has been done — which was the part flipping alone would not have delivered.
 *
 * ## The three gates, each verified against live source rather than an issue's text
 *
 *  1. **The D2 migration is applied to production.** `dock_occupancy.state` / `.expires_at` exist.
 *  2. **`TWO_PHASE_HOLD_ENABLED` defaults `True`** (`core/settings.py`), so `request_slot` takes the
 *     `_request_slot_as_hold` branch and returns a HELD outcome rather than going straight to
 *     `PENDING_CONFIRMATION`.
 *  3. **#83 landed, and #86 with it.** `holds.live_hold_for_shipment` is the single read behind
 *     `get_current_appointment`'s `hold`, `get_appointment_request_status`'s `hold`, and
 *     `/api/v1/driver/context`'s `current_hold` + `promise_state` + `promise_state_source`. One
 *     function, so the REST payload and the model's own prefetch cannot disagree about the same
 *     shipment inside one turn — which is precisely the failure #86 was filed for.
 *
 * ## What flipping this actually required on the client — the shapes were built before they existed
 *
 * E5.1 built these four screens against the *design*, before #83/#86 defined the real payload. The
 * components were right; **nothing fed them**. Three gaps, all closed in this pass:
 *
 *  - `use-driver-turn.ts` rendered only `find_feasible_slots` / `explain_slot_eligibility` results,
 *    so `request_slot`'s HELD outcome and `confirm_held_slot`'s result reached the client and were
 *    dropped. They are now consumed as **promise transitions** rather than as cards (`PROMISE_TOOLS`
 *    — a hold mutates the tapped card in place per U50, it does not append a fourth card).
 *  - `data.ts` derived the promise state from `appointment_status` alone, which structurally cannot
 *    say `HELD`. It now reads the server's **composed** `promise_state` and its `current_hold`.
 *  - Nothing seeded the countdown clock's server offset from `/driver/context`, so every hold would
 *    have been measured against the handset's own clock. `thread-list.tsx` now feeds `as_of`.
 *
 * **The 90-second countdown reads `dock_occupancy.expires_at`, reconciled through the shared
 * clock's measured server offset, and never a client-derived deadline.** `mappers.toHold` refuses a
 * hold with no `expires_at` outright rather than substituting `now + 90s`: a deadline the server
 * never asserted would drift by the round-trip time, in the direction that shows the driver time
 * they do not have. The server's `expires_in_seconds` is carried as a receipt of what it believed at
 * answer time, deliberately **not** as a second thing to tick from — R4's lesson was that two rules
 * for one hold end up disagreeing on screen.
 *
 * ## Still deliberately absent, and why that is not this flag's problem
 *
 * `appointments_appointment_status_check` admits **no** `HELD` value and must not: §4 says "Held ≠
 * booked: no `appointments` row exists yet", and there is a test that fails if someone adds it, to
 * force the conversation rather than let two models quietly coexist. A hold is a `dock_occupancy`
 * row and nothing else, which is exactly why `promise_state` is composed server-side.
 *
 * ## Why the flag is kept rather than deleted
 *
 * Its own previous instruction was "then flip, then delete the flag and every branch". Kept, and
 * this is the argued reason rather than an omission: `heldStateEnabled` is a **client** constant and
 * `TWO_PHASE_HOLD_ENABLED` is a **server** one, and they are independently revertible by design (the
 * D2 migration and its switch-on were deliberately separated for the same reason). Deleting this
 * would leave the client with no way to stop rendering HELD if the server flag is rolled back mid-
 * incident, and the remaining branches are not dead weight — `option-card.tsx`'s is a fail-closed
 * guard that renders `default` rather than a HELD treatment the rest of the surface is not showing.
 * A one-line revert on the most consequential state in the product is worth more than the tidiness.
 *
 * **To revert:** set this to `false`. Holds keep being granted server-side (that is the server
 * flag's business); this surface stops rendering the HELD chip, countdown, card treatment and lapse
 * notice, and falls back to the thread row's appointment-derived state.
 */
export const heldStateEnabled = true

/**
 * Web push. Blocker updated 2026-09-02 (#94): the old reason here — "nothing writes a row
 * yet" — is RESOLVED; the notification_outbox producer/drain now feeds `notifications` for
 * the in-app bell. What this flag actually gates is the WEB_PUSH delivery leg, and that
 * still has none of its parts: no VAPID key pair, no subscription store (SOLUTION_DESIGN
 * §6.1 specifies none — TECH_STACK §6 designs it but nothing is built), and no
 * service-worker `push` listener (vite-plugin-pwa registers offline/update only). Flipping
 * this would register browser subscriptions no server can ever send to.
 *
 * Screens 14A/14B (priming, denied) are built and shipped regardless: they are about the
 * browser permission, which works today, not about the delivery of a payload.
 */
export const pushSubscriptionEnabled = false
