import type { LivePromiseState, PromiseState } from './types'

/**
 * Wire `promise_state` → the four-state promise chip, or "no chip".
 *
 * ## The gap this function exists to render honestly (issue #53, Fork A)
 *
 * `05-carrier-portal/implementation-spec.md` §6 Fork A asks a question the design docs do not
 * answer anywhere: **what does a null-promise-state row look like?** Mockup state 4a renders a
 * `SHOWN` chip on a row (`SH-2026-0819-00…17`) that live data cannot produce — a shipment with
 * no current appointment returns `promise_state: null`, not `'SHOWN'`, because the payload's
 * `LEFT JOIN LATERAL` yields no row at all.
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
  /** One of the four designed states — render the shared promise chip. */
  | { kind: 'chip'; state: PromiseState }
  /** A real lifecycle value outside the four-state language — render as plain text. */
  | { kind: 'plain'; label: string }
  /** No current appointment at all. */
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
 * @param shownHeldEnabled `flags.carrierShownHeldEnabled`. Passed rather than imported so the
 *   states gallery can render the flagged-on variants for review without flipping the live flag.
 */
export function promiseCell(
  state: LivePromiseState | null | undefined,
  shownHeldEnabled: boolean,
): PromiseCellKind {
  if (!state) {
    return { kind: 'none', spoken: 'No appointment yet.' }
  }
  if (state === 'PENDING_CONFIRMATION' || state === 'CONFIRMED') {
    return { kind: 'chip', state }
  }
  // Unreachable against the live schema today; reachable the moment #53 lands, at which point
  // these two values start arriving here and the flag is what decides whether they may render.
  if ((state as string) === 'SHOWN' || (state as string) === 'HELD') {
    return shownHeldEnabled
      ? { kind: 'chip', state: state as unknown as PromiseState }
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
