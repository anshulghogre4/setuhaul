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
 * **Default OFF, and it must stay off until issue #53 lands.**
 *
 * Why (issue #53, filed 2026-08-27 — four independent confirmations in live source):
 *   - `confirm_held_slot` is not bound; the driver allowlist carries 11 of section 7.5.4's 12
 *     tools (`backend/app/assistant/tools.py`).
 *   - `appointments_appointment_status_check` admits no `HELD` value, and `dock_occupancy` has
 *     neither a `state` nor an `expires_at` column (`backend/app/scheduling/expiry.py`).
 *   - The M8 expiry sweeper's HELD leg returns `supported: false` with a reason string.
 *   - `request_slot` inserts straight at `PENDING_CONFIRMATION`
 *     (`backend/app/scheduling/allocation.py`) — there is no intermediate hold at all.
 *
 * So the live promise lifecycle is three states (`SHOWN → PENDING_CONFIRMATION → CONFIRMED`),
 * not the four `01-driver-chat/flows-and-states.md` specifies. Turning this on before #53
 * ships would render a `HELD` chip over a booking that is really already pending — which
 * `00-foundations/components.md` section 2 calls a broken promise in the business sense, and
 * which is exactly the mis-promise this product exists to remove.
 *
 * **Exit criterion:** issue #53 closed (schema + `confirm_held_slot` + sweeper leg), then flip
 * this to `true`, then delete the flag and every `heldStateEnabled` branch.
 *
 * Deliberately a module constant rather than an env var or a server-delivered flag: there is
 * nothing for an operator to decide here at 5-concurrent-user scale, and a runtime flag would
 * imply the backend can serve the state today. It cannot.
 */
export const heldStateEnabled = false

/**
 * Web push. Separate from the HELD flag because the four high-priority push events
 * (`flows-and-states.md` "Notifications") are only partly served: `notifications` /
 * `notification_preferences` tables exist (E3.5) but **nothing writes a row yet** — no
 * producer is wired on any write path. So the subscription plumbing is real and the feed is
 * honestly empty rather than broken.
 *
 * Screens 14A/14B (priming, denied) are built and shipped regardless: they are about the
 * browser permission, which works today, not about the delivery of a payload.
 */
export const pushSubscriptionEnabled = false
