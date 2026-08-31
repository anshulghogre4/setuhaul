import type { LivePromiseState, PromiseState } from './types'

/**
 * Wire `promise_state` → the four-state promise chip, or "no chip".
 *
 * ## `HELD` arrives here now; `SHOWN` never will (issues #85/#87, 2026-08-31)
 *
 * `promise_state` used to be `appointments.appointment_status` verbatim, which structurally could
 * not express either. It is now composed server-side over `appointments` **and** `dock_occupancy`
 * (`repositories/carrier.py::_PROMISE_STATE_SQL`), so `HELD` is a real value on this wire, with its
 * `hold_expires_at` beside it.
 *
 * `SHOWN` is a different case and its branch was **removed rather than kept behind a flag**: §0.8/§4
 * define it as what `find_feasible_slots` returned to one caller, and that read reserves nothing and
 * writes no row anywhere. There is no table to derive it from, and the tempting "no appointment and
 * no hold" mapping would label every never-offered shipment `SHOWN`. Whether the state belongs in a
 * carrier's vocabulary at all is a design decision, recorded in `flags.ts`.
 *
 * ## The gap this function still exists to render honestly (issue #53, Fork A)
 *
 * `05-carrier-portal/implementation-spec.md` §6 Fork A asks a question the design docs do not
 * answer anywhere: **what does a null-promise-state row look like?** Mockup state 4a renders a
 * `SHOWN` chip on a row (`SH-2026-0819-00…17`) that live data cannot produce — a shipment with
 * neither an appointment nor a live hold returns `promise_state: null`, not `'SHOWN'`.
 *
 * Neither of the two obvious answers is right:
 *   - a `SHOWN` chip claims a promise state the system does not have, and (until #53) cannot
 *     have;
 *   - a blank cell is forbidden outright by `stitch-prompts.md` §6, which makes `0`, `—` and
 *     absent three distinct renderings that "must never look alike".
 *
 * So: **an explicit `—`**, which is that same prompt's own rendering for a genuinely unknown
 * value, matched by an `sr-only` sentence so the dash is not the only channel. This is the one
 * string on this surface with no design source, and it is flagged as such rather than quietly
 * adopted — Fork A names it as needing a design answer, and this is a placeholder for that
 * answer, not the answer.
 *
 * ## The five other live values the design never anticipated
 *
 * `appointment_status` also admits `IN_PROGRESS / COMPLETED / CANCELLED / REJECTED / EXPIRED /
 * NO_SHOW`, none of which is one of the design's four promise states. They are real and a
 * carrier's fleet list will contain them. Rendering any of them as one of the four chips would
 * be a lie about a locked, four-state visual language (`components.md` §2, U14), so they get
 * the plain neutral text treatment below instead — the same shape the exception marker uses:
 * a sentence-case label, no border, no fill, nothing that could be mistaken for a chip.
 */

export type PromiseCellKind =
  /** One of the four designed states — render the shared promise chip. `expiresAt` is set only for
   *  `HELD`, where the chip's countdown is mandatory and the server's `hold_expires_at` is its only
   *  legitimate source. */
  | { kind: 'chip'; state: PromiseState; expiresAt?: string }
  /** A real lifecycle value outside the four-state language — render as plain text. */
  | { kind: 'plain'; label: string }
  /** No current appointment and no live hold. */
  | { kind: 'none'; spoken: string }

/** Sentence-case labels for the lifecycle values that are NOT promise states. Derived from the
 *  live CHECK constraint's own vocabulary, not invented: each is its own value, title-cased. */
const PLAIN_LABEL: Record<string, string> = {
  IN_PROGRESS: 'In progress',
  COMPLETED: 'Completed',
  CANCELLED: 'Cancelled',
  REJECTED: 'Rejected',
  EXPIRED: 'Expired',
  NO_SHOW: 'No show',
}

/**
 * @param heldEnabled `flags.carrierHeldEnabled`. Passed rather than imported so the states gallery
 *   can render both variants for review without flipping the live flag.
 * @param holdExpiresAt the row's `hold_expires_at`, used **only** for the `HELD` countdown.
 */
export function promiseCell(
  state: LivePromiseState | null | undefined,
  heldEnabled: boolean,
  holdExpiresAt?: string | null,
): PromiseCellKind {
  if (!state) {
    return { kind: 'none', spoken: 'No appointment yet.' }
  }
  if (state === 'PENDING_CONFIRMATION' || state === 'CONFIRMED') {
    return { kind: 'chip', state }
  }
  if (state === 'HELD') {
    // The countdown's source is the server's own `hold_expires_at` and nothing else. When it is
    // absent -- which happens on a deploy with `TWO_PHASE_HOLD_ENABLED` off, where the legacy
    // projection carries no hold columns at all -- the chip renders its static branch rather than
    // a countdown computed from a deadline nobody asserted.
    return heldEnabled
      ? { kind: 'chip', state, expiresAt: holdExpiresAt ?? undefined }
      : { kind: 'none', spoken: 'No appointment yet.' }
  }
  return { kind: 'plain', label: PLAIN_LABEL[state] ?? state }
}

/** Spoken form of a promise state, for a row's accessible name. Never abbreviated. */
export const PROMISE_SPOKEN: Record<PromiseState, string> = {
  SHOWN: 'shown',
  HELD: 'held',
  PENDING_CONFIRMATION: 'pending confirmation',
  CONFIRMED: 'confirmed',
}
