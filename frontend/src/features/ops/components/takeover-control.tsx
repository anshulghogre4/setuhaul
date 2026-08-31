import { useId } from 'react'
import { Info, TriangleAlert } from 'lucide-react'

import { Button } from '@/shared/ui/button'
import { describeDelivery } from '../lib/delivery'
import type { EscalationQueueItem } from '../lib/types'

/**
 * Take over / hand back -- `components.md` (this folder) section 5, U94,
 * `flows-and-states.md` Flow 2.
 *
 * ## What changed since E5.2 shipped this as a dead control
 *
 * E5.2 rendered `[ Take over thread ]` as an Inactive popover explaining two real gaps: no tool
 * posted as `OPERATIONS` (#55), and **no read anywhere returned the `chat_threads.thread_id` that
 * `take_over_thread` needs as an argument**. Both are closed -- `get_escalation_queue` now carries
 * `thread_id`/`thread_status` via `LEFT JOIN LATERAL`, and `post_operations_message` exists -- so
 * the control is wired for real here.
 *
 * A note the previous version of this file got wrong and is corrected rather than quietly
 * dropped: its comment claimed "take-over has no ownership precondition server-side... unlike
 * Hand-back". **That is no longer true.** `take_over_thread` now returns `NOT_ACKNOWLEDGED` unless
 * the escalation is `ACKNOWLEDGED`/`IN_PROGRESS` **and owned** (issue #56), and advances
 * `ACKNOWLEDGED -> IN_PROGRESS` in the same transaction. That is the order Flow 1 always
 * prescribed (step 3 acknowledge, step 4 take over), so the console leads with Acknowledge and
 * marks Take over as waiting on it.
 *
 * ## Why the prerequisite renders Disabled and not Hidden
 *
 * `00-foundations/components.md` section 18: **scope**-denied is Hidden; a **temporary product
 * state** ("prerequisite not met yet") is Disabled, paired with the reason. Not being acknowledged
 * yet is the textbook second case -- and the fix is the Acknowledge button sitting immediately
 * beside it. Implemented as `aria-disabled` + `title` rather than the `disabled` attribute, which
 * would remove it from the tab order and take the explanation with it; this is the same pattern
 * `implementation-spec.md` section 3D singled out as "U83's Disabled tier, used correctly" on the
 * reason picker's commit button.
 */

export type TakeoverNotice =
  /** `take_over_thread` refused: the escalation is unowned or not acknowledged. */
  | { kind: 'not-acknowledged' }
  /** `take_over_thread` found the thread already `ESCALATED`. Not an error -- someone got there
   *  first, or this is a replay. */
  | { kind: 'already-taken-over' }
  /** `hand_back_thread` refused and the thread is no longer `ESCALATED`: already handed back. */
  | { kind: 'handback-noop' }
  /** `hand_back_thread` refused while the thread IS still `ESCALATED` -- the live-data case
   *  `hand_back_thread`'s docstring names: taken over before issue #56 tightened the guard, so
   *  the escalation sits on `ACKNOWLEDGED` and no `IN_PROGRESS` row backs it. One call recovers. */
  | { kind: 'handback-needs-start' }
  /** `start_escalation_work` refused: the escalation belongs to someone else. */
  | { kind: 'not-owner'; ownerName: string | null }
  /** `post_operations_message` returned `NOT_TAKEN_OVER`. **Nothing was written** -- so this must
   *  not reuse the undelivered-divider copy, which would tell a coordinator their message is
   *  saved but unseen when in fact no message exists at all. */
  | { kind: 'post-refused' }
  /** The takeover/hand-back divider was written but did not reach the driver's live feed. */
  | { kind: 'divider-undelivered'; reason: string | null; event: 'joined' | 'handed-back' }
  /** A thrown request (network, 403, 409 `THREAD_UNSCOPED`). Carries the server's own detail. */
  | { kind: 'failed'; message: string }

export function TakeoverControl({
  item,
  busy,
  onTakeOver,
  onHandBack,
}: {
  item: EscalationQueueItem
  busy?: boolean
  onTakeOver: () => void
  onHandBack: () => void
}) {
  // Issue #91: was the literal "takeover-prereq"; the states gallery renders three of these
  // side by side, so three elements shared one id. See the note in `owner-control.tsx`.
  const prereqId = useId()
  const underTakeover = item.thread_status === 'ESCALATED'
  const acknowledged =
    item.owner_user_id !== null &&
    (item.escalation_status === 'ACKNOWLEDGED' || item.escalation_status === 'IN_PROGRESS')

  return (
    <div className="flex flex-col gap-2">
      <div className="flex flex-wrap items-center gap-2">
        {item.thread_id === null ? (
          // Not Hidden: the absence is a fact about this escalation, not about the viewer's
          // permissions, and a coordinator looking for the takeover action needs to know why it
          // is not there. `NOTIFICATION_FAILED` legitimately has no thread at all.
          <p className="flex items-center gap-1.5 text-supporting text-muted-foreground">
            <Info className="size-3.5 shrink-0" aria-hidden="true" />
            No driver conversation is attached to this escalation, so there is nothing to take
            over.
          </p>
        ) : underTakeover ? (
          <Button variant="neutral" onClick={onHandBack} disabled={busy}>
            Hand back
          </Button>
        ) : acknowledged ? (
          <Button variant="cautionary" onClick={onTakeOver} disabled={busy}>
            Take over thread
          </Button>
        ) : (
          <Button
            variant="cautionary"
            aria-disabled="true"
            aria-describedby={prereqId}
            title="Acknowledge this escalation first — taking over a driver's conversation needs a named owner."
            // aria-disabled, not `disabled`: keeps the control focusable so the reason is
            // reachable by keyboard. The click is a no-op rather than a request the server would
            // refuse with NOT_ACKNOWLEDGED anyway.
            onClick={(e) => e.preventDefault()}
            className="opacity-70"
          >
            Take over thread
          </Button>
        )}
      </div>

      {item.thread_id !== null && !underTakeover && !acknowledged ? (
        <p id={prereqId} className="text-supporting text-muted-foreground">
          Acknowledge first. Taking over disables the assistant on this thread, so the conversation
          needs a named owner before a person steps into it.
        </p>
      ) : null}

    </div>
  )
}

/**
 * The refusal / partial-success banner.
 *
 * Exported separately from the control on purpose: its text runs to several lines, and inside the
 * detail pane's `flex flex-wrap` action row it would be squeezed to the width of the Take-over
 * button. The pane renders it full-width beneath that row instead.
 */
export function TakeoverNoticeBanner({
  notice,
  busy,
  onRecover,
  onDismiss,
}: {
  notice: TakeoverNotice
  busy?: boolean
  onRecover: () => void
  onDismiss: () => void
}) {
  const content = render(notice, busy, onRecover)

  return (
    <div
      // `alert` for refusals and failures (an action the coordinator took did not do what they
      // expected -- accessibility-behaviour.md's assertive tier); `status` for the
      // divider-undelivered case, where the action DID succeed and this only qualifies it.
      role={notice.kind === 'divider-undelivered' ? 'status' : 'alert'}
      className="flex items-start gap-2 rounded-md bg-warning-bg px-3 py-2 text-supporting text-warning-fg"
    >
      <TriangleAlert className="mt-0.5 size-4 shrink-0" aria-hidden="true" />
      <div className="flex flex-1 flex-col gap-2">
        {content}
        {/* `relative tap-floor` (issue #91): 11px/1.3 = 14.3px tall against a 32px --tap.
            Invisible ::after region only -- the banner's copy rhythm is unchanged. */}
        <button
          type="button"
          onClick={onDismiss}
          className="relative tap-floor self-start text-micro underline focus-visible:outline-2 focus-visible:outline-ring"
        >
          Dismiss
        </button>
      </div>
    </div>
  )
}

function render(notice: TakeoverNotice, busy: boolean | undefined, onRecover: () => void) {
  switch (notice.kind) {
    case 'not-acknowledged':
      return (
        <p>
          <strong className="font-medium">Not taken over.</strong> This escalation has to be
          acknowledged, and owned by you, before you can step into the driver&rsquo;s conversation.
          Acknowledge it first, then take over.
        </p>
      )

    case 'already-taken-over':
      return (
        <p>
          <strong className="font-medium">Already taken over.</strong> This thread was already
          handed to a person — the assistant is not answering it. You can reply below.
        </p>
      )

    case 'handback-noop':
      return (
        <p>
          <strong className="font-medium">Already handed back.</strong> The assistant is answering
          this thread again. Nothing changed.
        </p>
      )

    case 'handback-needs-start':
      // The recovery path. `hand_back_thread` requires IN_PROGRESS; a thread taken over before
      // issue #56 made that value writable sits on ACKNOWLEDGED and refuses. One call fixes it,
      // and offering the call is the difference between a recoverable state and a dead end.
      return (
        <>
          <p>
            <strong className="font-medium">Hand-back refused.</strong> This thread is still under
            takeover, but its escalation was never marked as being worked on — so there is no
            in-progress record to hand back from. This happens to threads taken over before the
            console tracked that status.
          </p>
          <Button variant="constructive" size="sm" onClick={onRecover} disabled={busy}>
            Mark in progress, then hand back
          </Button>
        </>
      )

    case 'not-owner':
      return (
        <p>
          <strong className="font-medium">This escalation belongs to someone else</strong>
          {notice.ownerName ? ` (${notice.ownerName})` : ''}. Only its owner can mark it as being
          worked on. Reassign it first if it should be yours.
        </p>
      )

    case 'post-refused':
      return (
        <p>
          <strong className="font-medium">Nothing was posted.</strong> This thread is not under
          takeover, so the assistant is still answering it — a person and the bot replying to the
          same driver with neither aware of the other is exactly what takeover prevents. Take over
          the thread, then send again. Your text is kept below.
        </p>
      )

    case 'divider-undelivered': {
      const explanation = describeDelivery(notice.reason)
      const event = notice.event === 'joined' ? 'joined' : 'handed the thread back'
      return (
        <p>
          <strong className="font-medium">
            The driver was not told you {event}.
          </strong>{' '}
          {explanation.title} {explanation.detail} A silent takeover reads to a driver as the
          assistant ignoring them.
        </p>
      )
    }

    case 'failed':
      return (
        <p>
          <strong className="font-medium">That didn&rsquo;t save. Nothing has changed.</strong>{' '}
          {notice.message}
        </p>
      )

    default: {
      // Compile-time exhaustiveness. Adding a `TakeoverNotice` kind without copy for it would
      // otherwise render an empty warning box -- a coordinator told that something went wrong and
      // not what -- which is the exact failure mode this whole component exists to remove. TS
      // fails the build here instead.
      const unhandled: never = notice
      return unhandled
    }
  }
}
