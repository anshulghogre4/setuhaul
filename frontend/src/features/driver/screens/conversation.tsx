import { ChevronLeft } from 'lucide-react'
import { useAtomValue } from 'jotai'
import { useMemo } from 'react'
import { Link, useParams } from 'react-router-dom'

import { copy } from '../lib/copy'
import { onlineAtom, quickRepliesAtom, threadsAtom } from '../lib/store'
import { useDriverTurn } from '../lib/use-driver-turn'
import { Composer } from '../components/composer'
import { StateLine } from '../components/state-line'
import { Transcript } from '../components/transcript'
import type { DriverOption } from '../lib/types'

/**
 * Screens 4, 6, 7, 8, 10A, 10B, 11A–C, 12A/B, 16A, 17, 18, 19, 20, 21, 22A/B, 23A/B, 24,
 * 25A–D, 26, 27A–C, 28A — the conversation. **The primary surface.**
 *
 * Chat as the spine with structured cards inside the transcript (U18). Almost every screen in
 * the epic is a *state of this one screen*, which is why they are not separate routes: the
 * transcript renders whichever parts and notices its messages carry, and the header renders
 * whichever promise state the thread is in. That is the design's own structure ("two screens and
 * a profile"), not a shortcut.
 *
 * Regions, from `screens.md` section 2:
 *
 * | Region | Behaviour |
 * |---|---|
 * | Header | Back · descriptor · persistent state line. Sticky. |
 * | Transcript | Scrolls. Auto-scrolls to latest on open; **never while the driver reads history**. |
 * | Quick replies | 0 or present. Part of the composer, so both rise with the keyboard together. |
 * | Composer | Grows to 3 lines then scrolls internally. Rises with the keyboard. |
 *
 * ## Header height — F2, resolved by measurement rather than by the stated number
 *
 * `screens.md` asserts a 56px header and then draws two rows inside it. Once the back button is
 * a real 48×48 target (R8: it measured 18×6.9), a two-row header is **48 + 48 + padding**, not
 * 56. So the header is `min-h-*` per row and the container has no fixed height at all — which is
 * also what U31's ~30% text expansion requires.
 *
 * ## Keyboard behaviour
 *
 * The composer and quick replies are inside the same flex child, below a `min-h-0 flex-1`
 * transcript. On both platforms the visual viewport shrinking makes the transcript shrink and the
 * composer rise, with the scroll position anchored to the **latest** message rather than the top
 * — which is the checklist's named common bug and is handled by `Transcript`'s pinned-to-bottom
 * logic falling out of the same resize.
 */
export function DriverConversation() {
  const { threadId = '' } = useParams()
  const threads = useAtomValue(threadsAtom)
  const quickReplies = useAtomValue(quickRepliesAtom)
  const online = useAtomValue(onlineAtom)
  const { messages, send, retry } = useDriverTurn(threadId)

  const thread = useMemo(
    () => threads.find((t) => t.threadId === threadId),
    [threads, threadId],
  )

  const onSelectOption = (option: DriverOption) => {
    /**
     * Tapping a card is a **capacity-affecting action**, so it carries an idempotency key bound
     * to `recommendation_id + slot_id` (U70 / spec section 3G) — not a fresh UUID, because the
     * point is that the *same* tap retried is the same request.
     *
     * It goes through the assistant as a message rather than through
     * `POST /shipments/{id}/slots/{slot_id}/request` directly, and that is deliberate: the
     * transcript must remain the record of what was asked for, and the assistant's own
     * confirm-gate (`ux_state: confirmation_required`) is what implements Flow 4's
     * preview -> explicit confirmation -> commit. Calling the REST endpoint from the card would
     * route around that gate.
     *
     * **No ordinal is sent** — the message names the dock and the time, which is the identifier
     * (U16). If this ever becomes "option 2", the ordinal trap is back.
     */
    void send(`Request ${option.dockCode} at ${option.feasibleStartTs}`)
  }

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <header className="shrink-0 border-b border-border bg-card">
        <div className="flex min-h-12 items-center gap-1 px-2">
          {/* 48x48. accessibility.md singles this element out for being ABOVE the floor --
              "top-left is the hardest place to hit one-handed" -- and R8 found it the worst miss
              on the board at 18x6.9. */}
          <Link
            to="/driver"
            aria-label={copy.backToThreads}
            className="grid size-12 shrink-0 place-items-center rounded-md text-foreground focus-visible:outline-2 focus-visible:outline-ring focus-visible:outline-offset-2"
          >
            <ChevronLeft size={24} strokeWidth={2} aria-hidden="true" />
          </Link>
          <h1 className="min-w-0 truncate text-body-lg font-semibold">
            {thread?.descriptor ?? ''}
          </h1>
        </div>

        {/* Row two. Hidden entirely when there is no active promise -- the header becomes one
            row rather than showing an empty one. */}
        <StateLine
          state={thread?.promiseState ?? null}
          expiresAt={thread?.expiresAt}
          operationalLine={thread?.operationalLine ?? undefined}
        />
      </header>

      <Transcript messages={messages} onSelectOption={onSelectOption} onRetry={retry} />

      <Composer offline={!online} quickReplies={quickReplies} onSend={(text) => void send(text)} />
    </div>
  )
}
