/**
 * Turning `delivered` / `delivery_reason` into something a coordinator can act on.
 *
 * ## Why this file exists at all
 *
 * `thread_message_service.py`'s module docstring states the architecture and its one residual
 * plainly: **PostgreSQL `chat_messages` is the write of record; Redis is a projection of an
 * already-committed row into the driver's live feed, never the reverse.** The consequence, in that
 * file's own words:
 *
 * > a message posted while the projection is unavailable is durable but will not appear in the
 * > driver's feed even after Redis recovers, because nothing back-fills Redis from
 * > `chat_messages`.
 *
 * So `delivered: false` is not a transient "still sending" -- it is **final**. A coordinator who
 * reads it as a spinner and waits will wait forever, and the driver they were reassuring never
 * hears from them. Every string below therefore says what happened AND what to do next, rather
 * than naming a state.
 *
 * ## Why this is not a read receipt
 *
 * `stitch-prompts.md` prompt 8 explicitly excludes "read receipts on outbound messages (whether
 * delivery state surfaces here is not specified -- do not invent an indicator)". This file does
 * **not** add a success indicator: a delivered message renders with no marker at all, exactly as
 * that exclusion requires. What it adds is a **failure** marker, which the design does already
 * specify for outbound messages -- `01-driver-chat/components.md` section 4's delivery-status
 * table has a `Failed` row rendering "not sent" in explicit words plus a retry affordance, chosen
 * there for the same reason: a symbol can be mistaken for sent, words cannot. Success stays
 * silent; failure speaks.
 */

/** `POSTED` with this reason is a replay of a message that already exists, not a delivery
 *  failure -- `post_operations_message`'s second replay layer
 *  (`chat_messages_external_message_id_uidx`). */
export const DUPLICATE_REASON = 'DUPLICATE_CLIENT_MESSAGE_ID'

/** `NOT_TAKEN_OVER` carries this. It is a refusal, not a projection failure -- nothing was
 *  written, so it must not render as "durable but undelivered". */
export const NOT_TAKEN_OVER_REASON = 'THREAD_NOT_TAKEN_OVER'

export type DeliveryExplanation = {
  /** The lead sentence, shown next to the message and rendered bold by callers. It states this
   *  reason's own fact rather than a fixed prefix -- most reasons mean the driver did not see the
   *  message, but `NOT_TAKEN_OVER` means nothing was written at all and `DUPLICATE` means the
   *  earlier copy stands with its delivery outcome unknown. A shared "not shown to the driver"
   *  prefix mislabelled both. */
  title: string
  /** What the coordinator should do instead. Never "try again" when retrying cannot help. */
  detail: string
  /** True when re-posting the same text could plausibly succeed (a transient Redis fault).
   *  False when the failure is structural -- retrying then only writes a second durable row the
   *  driver also cannot see. */
  retryable: boolean
}

/**
 * Every named reason `thread_message_service.py` can return, plus a safe default.
 *
 * `REDIS_UNAVAILABLE` / `REDIS_WRITE_FAILED` are the two that come back as
 * `memory.degrade_reason or "<constant>"`, so `degrade_reason` can be an arbitrary string this
 * file has never seen. That is exactly why the fallback below **echoes the raw code** rather than
 * collapsing unknowns into a generic apology -- an unrecognised reason is still a fact worth
 * putting in front of the person who has to act on it.
 */
export function describeDelivery(reason: string | null): DeliveryExplanation {
  const undelivered = 'The driver did not see this message.'

  switch (reason) {
    case 'NO_LIVE_DRIVER_SESSION':
      return {
        title: `${undelivered} They have no live chat session.`,
        detail:
          'Ordinary and expected: the driver has not opened this thread inside the last 24 hours, ' +
          'so there is no live feed to append to. The message is saved and is part of the record, ' +
          'but it will not appear for them later either. Contact them another way if it is urgent.',
        retryable: false,
      }
    case 'DRIVER_USER_UNMAPPED':
      return {
        title: `${undelivered} This driver has no user account.`,
        detail:
          'The driver record is not linked to a sign-in, so there is no feed to deliver to. ' +
          'Retrying will not change that -- the contact record needs fixing first.',
        retryable: false,
      }
    case 'THREAD_NOT_FOUND':
      return {
        title: `${undelivered} The thread could not be read back.`,
        detail: 'The message is saved. Refresh the console before posting again.',
        retryable: true,
      }
    case 'SETTINGS_UNAVAILABLE':
      return {
        title: `${undelivered} Delivery is not configured on this server.`,
        detail:
          'The message is saved to the permanent record, but this deployment cannot reach the ' +
          "driver's live feed at all. This is an operational problem, not something a retry fixes.",
        retryable: false,
      }
    case 'REDIS_UNAVAILABLE':
      return {
        title: `${undelivered} The live-feed service is unavailable.`,
        detail:
          'The message is saved permanently, but it will not reach the driver even once the ' +
          'service recovers -- nothing back-fills the feed. Reach the driver another way, then ' +
          'post again once the service is back if you still want it on the thread.',
        retryable: true,
      }
    case 'REDIS_WRITE_FAILED':
      return {
        title: `${undelivered} Writing to their live feed failed.`,
        detail:
          'The message is saved permanently. It will not appear for the driver later on its own. ' +
          'Try posting again; if it keeps failing, reach them another way.',
        retryable: true,
      }
    case NOT_TAKEN_OVER_REASON:
      return {
        title: 'Nothing was posted.',
        detail:
          'This thread is not under takeover, so the assistant is still answering it. Take over ' +
          'the thread first -- otherwise a person and the bot would be replying to the same ' +
          'driver with neither aware of the other.',
        retryable: false,
      }
    case DUPLICATE_REASON:
      // Reached when a retry varied its Idempotency-Key but reused the client_message_id, so the
      // endpoint's unique-index replay layer caught it. Deliberately does NOT claim the driver
      // missed it: the earlier copy's own delivery outcome was reported when it was posted and is
      // not stored anywhere to read back, so "unknown" is the only honest word here.
      return {
        title: 'Already posted — this did not send a second copy.',
        detail:
          'The earlier copy is the one on the thread. Whether it reached the driver was reported ' +
          'at the time and is not recorded, so this cannot confirm it either way.',
        retryable: false,
      }
    case null:
      return {
        title: undelivered,
        detail:
          'The message is saved permanently but did not reach their live feed, and no reason was ' +
          'given. Reach the driver another way if it is urgent.',
        retryable: true,
      }
    default:
      // Covers `PROJECTION_ERROR:<ExceptionName>` and any `degrade_reason` string this file has
      // not seen. Echo the raw code -- an unrecognised reason is still evidence, and swallowing it
      // would leave the coordinator with strictly less than the server actually told them.
      return {
        title: `${undelivered} Delivery failed (${reason}).`,
        detail:
          'The message is saved permanently. It will not appear for the driver later on its own. ' +
          'Reach them another way if it is urgent, and quote that code if you report this.',
        retryable: true,
      }
  }
}
