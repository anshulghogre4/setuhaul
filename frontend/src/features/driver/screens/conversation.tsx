import { ChevronLeft } from 'lucide-react'
import { useAtomValue } from 'jotai'
import { useCallback, useEffect, useMemo, useRef } from 'react'
import { Link, useParams } from 'react-router-dom'

import { useCountdown } from '@/shared/lib/countdown'
import { copy } from '../lib/copy'
import { heldStateEnabled } from '../lib/flags'
import { onlineAtom, quickRepliesAtom, threadsAtom } from '../lib/store'
import { TTL_MS } from '../lib/use-promise-countdown'
import { useDriverTurn } from '../lib/use-driver-turn'
import { Composer } from '../components/composer'
import { StateLine } from '../components/state-line'
import { Transcript, type TranscriptHandle } from '../components/transcript'
import type { DriverHold, DriverMessage, DriverOption } from '../lib/types'

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
  const { messages, send, retry, hold, lapseHold } = useDriverTurn(threadId)

  const thread = useMemo(
    () => threads.find((t) => t.threadId === threadId),
    [threads, threadId],
  )

  /**
   * The header's promise, and **the live hold wins over the thread row**.
   *
   * Two writers describe the same shipment: `threadsAtom`, written once per `/driver/context` load,
   * and `holdsByThreadAtom`, written inside a turn. Within a 90-second window the second is
   * strictly newer, and preferring the older one is exactly how a driver ends up watching a stale
   * "no promise" header while the assistant has just told them a slot is reserved for them.
   *
   * `heldStateEnabled` gates the *rendering*, not the state: with the flag off the header falls back
   * to whatever the thread row says, which is the same fail-closed choice `option-card.tsx` makes.
   */
  const heldNow = heldStateEnabled ? hold : null
  const state = heldNow ? ('HELD' as const) : (thread?.promiseState ?? null)
  const expiresAt = heldNow ? heldNow.expiresAt : thread?.expiresAt

  /**
   * The state line's tap target (issue #99.3, `components.md` §6: *"Tapping scrolls the transcript
   * to the message that established the state."*). The prop was never passed, so the line rendered
   * as a real focusable button that did nothing in every state.
   */
  const transcriptRef = useRef<TranscriptHandle>(null)
  const originMessageId = useMemo(
    () => establishingMessageId(messages, heldNow?.slotId ?? null),
    [messages, heldNow?.slotId],
  )
  const scrollToOrigin = useCallback(() => {
    if (originMessageId === null) return
    transcriptRef.current?.scrollToMessage(originMessageId)
  }, [originMessageId])

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
          state={state}
          expiresAt={expiresAt}
          operationalLine={thread?.operationalLine ?? undefined}
          onScrollToOrigin={scrollToOrigin}
        />
      </header>

      {/* Screen 15's trigger. Mounted only while a hold is live, so its countdown subscription
          exists for at most 90 seconds and unmounts the moment the hold resolves either way. */}
      {heldNow ? <HoldLapseWatch hold={heldNow} onLapse={lapseHold} /> : null}

      {/* `<main>` wrapping BOTH the transcript and the composer -- see the note in
          `thread-list.tsx`. Measured 2026-08-31: the driver surface had no main landmark on any
          screen. It carries the root's own flex classes so the transcript still grows and the
          composer still pins to the bottom; verified by re-render, not by inspection. The
          composer is inside `main` deliberately -- it is the primary content of this screen,
          not chrome around it. */}
      <main className="flex min-h-0 flex-1 flex-col">
        <Transcript
          ref={transcriptRef}
          messages={messages}
          heldUntil={heldNow?.expiresAt}
          onSelectOption={onSelectOption}
          onRetry={retry}
        />

        <Composer offline={!online} quickReplies={quickReplies} onSend={(text) => void send(text)} />
      </main>
    </div>
  )
}

/**
 * "The message that established the state" (`components.md` §6), resolved against what this
 * client actually holds — and honest about the case where that is not enough.
 *
 * Three tiers, most specific first:
 *
 *  1. **A live hold with a `slot_id`** — the establishing message is exactly the one carrying the
 *     option set that contains that slot, because that is the card the driver tapped and the card
 *     `use-driver-turn.ts` mutated in place (U50). Searched backwards for the same reason
 *     `findLastOptionSetIndex` is: an older, superseded set can legitimately contain the same
 *     `slot_id`, and jumping to it would land the driver on a card they can no longer act on.
 *  2. **The most recent promise-bearing structured part** — an `optionSet` *is* the `SHOWN` state
 *     (`find_feasible_slots` reserves nothing, so nothing on the wire can say `SHOWN`), and a
 *     `receipt` is what a committed promise leaves behind. Text parts are excluded deliberately:
 *     the assistant narrates a hold in prose too, and jumping to the narration rather than to the
 *     card would be jumping to a description of the fact instead of the fact.
 *  3. **The oldest loaded message**, as a stated boundary rather than a guess.
 *
 * ⚠ **Why tier 3 exists at all, and what it does not claim.** This surface does not restore the
 * transcript: `lib/data.ts` reads `/api/v1/driver/context` only, and `GET /api/v1/chat/history`
 * has no call site anywhere in `src/`. So a driver who opens a thread whose `PENDING_CONFIRMATION`
 * was established in an earlier session has an EMPTY transcript, and no message in this client is
 * the one that set the state. Tier 3 therefore scrolls as far back as this client's transcript
 * goes — "toward it", not "to it" — and returns nothing at all when the transcript is empty, which
 * is the only truthful answer available until history restore is wired. It deliberately does not
 * fabricate a target, and it never picks a message merely because a state happens to be active.
 */
function establishingMessageId(
  messages: DriverMessage[],
  heldSlotId: string | null,
): string | null {
  if (heldSlotId !== null) {
    for (let i = messages.length - 1; i >= 0; i -= 1) {
      const carriesSlot = messages[i].parts.some(
        (p) => p.kind === 'optionSet' && p.optionSet.options.some((o) => o.slotId === heldSlotId),
      )
      if (carriesSlot) return messages[i].id
    }
  }

  for (let i = messages.length - 1; i >= 0; i -= 1) {
    const promiseBearing = messages[i].parts.some(
      (p) => p.kind === 'optionSet' || p.kind === 'receipt',
    )
    if (promiseBearing) return messages[i].id
  }

  return messages[0]?.id ?? null
}

/**
 * Fires `onLapse` **once**, when the hold's server deadline passes.
 *
 * Renders nothing. It exists as a component rather than a hook inside `DriverConversation` for one
 * reason worth stating: `useCountdown` subscribes to the shared 1 Hz tick, so calling it
 * unconditionally in the screen would re-render the entire conversation every second for the ~99%
 * of the time no hold exists. Mounting it only while a hold is live confines that to 90 seconds.
 *
 * **The deadline is the server's `expires_at`, read through the shared clock's measured offset**
 * (`shared/lib/countdown.tsx`) -- never `Date.now()` against a locally-computed deadline. Two
 * consequences that are the whole reason the offset exists: a phone whose clock is three minutes
 * fast does not lapse a hold that is genuinely still live, and offline the tick **freezes**, so the
 * reading holds at last-known rather than free-running and lapsing a hold this client can no longer
 * reconcile. `edge-cases.md` section 10 requires exactly that behaviour.
 *
 * The client's lapse is a *display* decision, not a capacity one: the server refuses a lapsed
 * `confirm_held_slot` on its own (`holds._locked_hold` carries `expires_at > :now`, and §0.8 forbids
 * depending on the sweeper for correctness), so the worst case of a slow tick here is a card that
 * looks live for an extra second, not a hold that can be double-committed.
 */
function HoldLapseWatch({
  hold,
  onLapse,
}: {
  hold: DriverHold
  onLapse: (hold: DriverHold) => void
}) {
  const reading = useCountdown(hold.expiresAt, TTL_MS.HELD)
  // Latched per hold id: a re-render inside the same second, or a second hold arriving later, must
  // not re-fire the notice for one that already lapsed.
  const fired = useRef<string | null>(null)

  useEffect(() => {
    if (!reading.expired || !reading.live) return
    if (fired.current === hold.holdId) return
    fired.current = hold.holdId
    onLapse(hold)
  }, [reading.expired, reading.live, hold, onLapse])

  return null
}
