import { atom } from 'jotai'

import type { DriverMessage, DriverThread, UxState } from './types'

/**
 * The driver surface's message store.
 *
 * ## Why we hold the messages and not the runtime
 *
 * `implementation-spec.md` section 1.1 forced this choice rather than left it open:
 * `useChatRuntime` wants the Vercel AI SDK wire format (ours is a bespoke `event:`/`data:`
 * stream), `LangGraphRuntime` wants a LangGraph server (section 9.3 is a custom `bind_tools`
 * loop), and `LocalRuntime` wants to own message state and re-run turns — but our transcript is
 * also restorable from Redis (`GET /chat/history`) **and** mutated by *server-pushed* events
 * (U50), which is two writers into a store `LocalRuntime` thinks it owns.
 *
 * `ExternalStoreRuntime` is the only option where *"a system event mutates an existing message
 * part in place"* is a normal state update rather than a fight with the runtime. So: `jotai`
 * holds the array, assistant-ui renders it.
 *
 * Verified against the installed `@assistant-ui/react@0.15.16` rather than the library's current
 * docs — `useExternalStoreRuntime` and `ExternalStoreAdapter` are both exported, and
 * `ThreadMessageLike` carries `tool-call` parts plus a `metadata.custom` bag, which is what
 * carries the U47 tier and the delivery status.
 *
 * ## Keyed by thread
 *
 * One driver has several loads, so the transcript is per `thread_id`. Keeping it in one atom
 * keyed by thread (rather than an atom per thread) means the thread list can read every
 * thread's last message without subscribing to a dynamic set of atoms.
 */

export type TurnState = {
  /** Wall-clock ms when the turn started, for the 400ms/8s thinking thresholds. */
  startedAtMs: number
  /** The tool named by the most recent `status` frame. Name only — the frame carries no args
   *  and no result, and is emitted BEFORE execution. */
  currentTool: string | null
  /**
   * Text accumulated from `token` frames, **held here and not committed to the transcript until
   * `done`** — Fork C, locked to "buffer until `done`, render together".
   *
   * The reason is a real screen consequence, not a preference: the live stream delivers the
   * assistant's sentence *"Three options are open right now"* before the option cards exist,
   * because `status` carries a tool NAME before execution and results appear only in `done`.
   * Streaming the text first opens a window — the length of the LLM's closing generation — where
   * the driver reads a claim with nothing under it. That is the mis-promise shape this product
   * exists to remove, in miniature.
   *
   * The cost is the streaming feel, and it is paid deliberately. The `status` frame drives the
   * thinking indicator so the driver is not staring at nothing.
   */
  bufferedText: string
  error: { code: string; message: string } | null
}

export const messagesByThreadAtom = atom<Record<string, DriverMessage[]>>({})

export const threadsAtom = atom<DriverThread[]>([])

/** `null` when no turn is in flight. */
export const turnAtom = atom<TurnState | null>(null)

/** The last `done.data.ux_state`. **The branch key for which screen renders, not the prose.** */
export const uxStateAtom = atom<UxState>('chat')

/** Quick replies for the current question, derived by the caller from `done.data.confirmation`
 *  and cleared on the next turn. Literal strings — they are sent verbatim as driver messages. */
export const quickRepliesAtom = atom<string[]>([])

/**
 * Connection state. Drives three things at once and they must not drift apart: the composer's
 * placeholder, the option cards' disabled-with-a-reason treatment, and `CountdownProvider`'s
 * `setLive(false)` — which is what makes a countdown **hold at last-known instead of
 * free-running against a clock we can no longer reconcile** (U68, `edge-cases.md` section 10).
 */
export const onlineAtom = atom<boolean>(typeof navigator === 'undefined' ? true : navigator.onLine)

/**
 * Thread-list ordering. **Ours, not the library's** (`screens.md` section 1):
 *
 *   1. Threads with a **running TTL** (`HELD`, then `PENDING`) — soonest deadline first
 *   2. Other active threads, most recent activity first
 *   3. Resolved, most recent first
 *
 * A `HELD` thread with 20 seconds left is always the first thing on screen. Same
 * urgency-over-recency logic as the planner's queue (section 7.3), applied to a driver's own
 * loads.
 *
 * Sorted here in the store rather than in the component, so the *rendered* order and the
 * *announced* order are one list — a screen reader walking a `role="list"` gets DOM order, and a
 * component that re-sorted at render time would give it a different sequence from the one the
 * design specifies.
 */
export const orderedThreadsAtom = atom((get) => {
  const threads = get(threadsAtom)
  const withTtl = (t: DriverThread) => t.expiresAt !== undefined && !t.resolved

  return [...threads].sort((a, b) => {
    if (a.resolved !== b.resolved) return a.resolved ? 1 : -1
    if (!a.resolved) {
      const aTtl = withTtl(a)
      const bTtl = withTtl(b)
      if (aTtl !== bTtl) return aTtl ? -1 : 1
      if (aTtl && bTtl) {
        // Soonest deadline first. Ties broken on threadId so the order is stable across
        // re-renders -- an unstable sort here would reorder cards under a driver's thumb.
        const d = Date.parse(a.expiresAt!) - Date.parse(b.expiresAt!)
        return d !== 0 ? d : a.threadId.localeCompare(b.threadId)
      }
    }
    const recency = Date.parse(b.lastActivityAt) - Date.parse(a.lastActivityAt)
    return recency !== 0 ? recency : a.threadId.localeCompare(b.threadId)
  })
})
