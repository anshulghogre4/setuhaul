/**
 * `reject_request`'s controlled vocabulary -- and, since issue #63, `counter_offer`'s too.
 *
 * ## Copied from the service, not from the artboards, and the difference is not cosmetic
 *
 * The design prose this surface was drafted against called the wire field `rejection_reason` and
 * treated the five values as a client-side courtesy (`implementation-spec.md` section 5.1 G7:
 * *"the five-value vocabulary appears nowhere in `backend/app/`"*). **Both halves of that are now
 * out of date.** Issue #66 renamed the field to `reason_code` and froze the vocabulary in
 * `allocation.REJECTION_REASON_CODES`, enforced by `_assert_reason_code` with a 422
 * `INVALID_REASON_CODE` naming the supported set. A form built from the older prose would send
 * `rejection_reason` into a `model_config = ConfigDict(extra="forbid")` body and fail on every
 * single submit.
 *
 * So this array is copied verbatim from `backend/app/scheduling/allocation.py:70-72`, read
 * 2026-08-29, and `COUNTER_OFFER_REASON_CODES = REJECTION_REASON_CODES` on line 80 is why the
 * counter-offer dialog reuses it rather than inventing a second list. That aliasing is the
 * server's own explicitly-flagged assumption ("Source: assumption, untested" -- section 7.5.1
 * gives `counter_offer` a `reason_code` but never names its vocabulary), carried here rather than
 * silently re-derived.
 */

export const REJECT_REASON_CODES = [
  'CAPACITY',
  'RULE_VIOLATION',
  'PRIORITY_CONFLICT',
  'SAFETY',
  'DATA_CONFLICT',
] as const

export type RejectReasonCode = (typeof REJECT_REASON_CODES)[number]

/** The planner-facing radio labels -- `mockup.html` State 12's own five, verbatim. */
export const REASON_LABELS: Record<RejectReasonCode, string> = {
  CAPACITY: 'Capacity',
  RULE_VIOLATION: 'Rule violation',
  PRIORITY_CONFLICT: 'Priority conflict',
  SAFETY: 'Safety review',
  DATA_CONFLICT: 'Data conflict',
}

/**
 * The exact driver-facing sentences, `stitch-prompts.md` section 5: *"The five reasons and their
 * exact driver-facing sentences -- never rewritten, never generated"*.
 *
 * These render in the preview block, which is the reason the preview step exists at all: the
 * value is sent to the driver, so the person sending it reads the exact words first. Nothing here
 * is model-generated and nothing is composed at runtime.
 *
 * **Honest limit, stated rather than implied:** the server stores the *code* in
 * `appointments.cancellation_reason` (`_ops_pending_transition`, and `reject_appointment`'s own
 * docstring: *"What lands in `cancellation_reason` is the code itself, not prose"*). No shipped
 * renderer turns that code back into these sentences on the driver's side yet. The preview is
 * therefore an accurate statement of what the enum *means*, and the driver-side rendering of it is
 * a real remaining gap -- not something this dialog can close from here.
 */
export const DRIVER_FACING_SENTENCE: Record<RejectReasonCode, string> = {
  CAPACITY: "The warehouse couldn't fit this slot alongside the trucks already scheduled.",
  RULE_VIOLATION: "That slot isn't allowed for your load at this facility.",
  PRIORITY_CONFLICT: 'A higher-priority load needed that dock time.',
  SAFETY: 'Operations needs to review this before scheduling.',
  DATA_CONFLICT: "Some details don't match our records — operations is checking.",
}

/** `stitch-prompts.md` section 5: *"A rejection is never the last message in a thread"* -- the
 *  preview always ends pointing at alternatives. Appended to the sentence, never baked into it,
 *  so the five values above stay byte-identical to the design's own list. */
export const NEXT_STEP_SENTENCE = 'Here are the next available options.'

/**
 * The five safe-batch predicate names, for rendering a `bulk_confirm` skip in words rather than
 * as a raw enum. Copied from `allocation.py:86-97` (`PREDICATE_*`), not invented.
 */
export const PREDICATE_LABELS: Record<string, string> = {
  ZERO_DISPLACEMENT: 'it would displace another booking',
  EXACT_DOCK_MATCH: 'the dock type is only compatible, not exact',
  ETA_CONFIDENCE_NOT_LOW: 'its ETA confidence is LOW',
  INSIDE_HOURS_AND_BEFORE_LAST_NEW_START: 'it falls outside the operating window',
  NO_OPEN_ESCALATION: 'it has an open escalation',
}

export function describePredicates(failed: string[]): string {
  if (failed.length === 0) return ''
  return failed.map((code) => PREDICATE_LABELS[code] ?? code).join('; ')
}
