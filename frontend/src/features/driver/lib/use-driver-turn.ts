import { useAtom, useSetAtom } from 'jotai'
import { useCallback, useEffect, useRef } from 'react'

import { streamChat } from '@/core/http/sse'
import { useCountdownClock } from '@/shared/lib/countdown'
import { copy } from './copy'
import { heldStateEnabled } from './flags'
import { haptic } from './haptics'
import { toEligibilityAnswer, toHoldFromRequestSlot, toOptionSet } from './mappers'
import {
  holdsByThreadAtom,
  messagesByThreadAtom,
  onlineAtom,
  quickRepliesAtom,
  turnAtom,
  uxStateAtom,
} from './store'
import type {
  DriverEventCode,
  DriverHold,
  DriverMessage,
  DriverPart,
  OptionCardState,
  SystemNoticeVariant,
  UxState,
} from './types'

/**
 * One driver turn, end to end: optimistic bubble -> SSE -> committed transcript.
 *
 * This is the only place in the surface that talks to `/api/v1/chat/stream`, and the only place
 * that knows the SSE frame contract:
 *
 * ```
 * event: start   -> { thread_id, session_id }
 * event: status  -> { tool: "find_feasible_slots" }   ← NAME ONLY. no args, no result.
 * event: token   -> { content: "Three options are open " }
 * event: done    -> { response, tool_calls[], ux_state, confirmation, ... }
 *                                    ↑ the ONLY place option data appears
 * event: error   -> { code, message, status_code? }
 * ```
 *
 * ## Fork C, locked: buffer text until `done`, commit text and tool parts in one paint
 *
 * See `store.ts`'s `bufferedText` comment for why. The consequence to keep in mind while
 * reading this file: **there is no code path that appends an assistant text bubble before the
 * `done` frame.** If one appears, the transcript can show *"Three options are open right now"*
 * with nothing under it, which is the mis-promise this product exists to remove.
 *
 * ## Idempotency (U70)
 *
 * `client_message_id` is a client-generated UUID **reused verbatim on Retry**. That is precisely
 * what makes screen 27A (message failed -> inline Retry) safe and what makes `edge-cases.md`
 * section 11's duplicate invisible: the server's `dedupe_key` collapses it, and the driver never
 * sees an error about a duplicate that was handled correctly. Generating a fresh id on Retry
 * would defeat both.
 */

const apiBase =
  (import.meta.env.VITE_API_BASE_URL as string | undefined) || 'http://localhost:8000'

/** Tool names whose results have a dedicated renderer. Everything else is deliberately NOT
 *  rendered as a card: an unrecognised tool result must not be guessed at, and the assistant's
 *  own prose already narrates it (section 7.2b — the assistant narrates the receipt). */
const RENDERABLE_TOOLS = new Set(['find_feasible_slots', 'explain_slot_eligibility'])

/**
 * The three tools that change which promise this thread holds. **Not in `RENDERABLE_TOOLS`**, and
 * the distinction is the point: these produce no card of their own. `request_slot`'s HELD outcome
 * *mutates the card the driver already tapped* (U50 — "cards mutate in place rather than being
 * replaced by a new message", so the driver sees *which* thing changed), and the state it grants is
 * rendered by the persistent state line and the thread card, both of which already exist.
 *
 * Appending a fourth card here would be the mistake §7.2b warns about from the other direction: the
 * assistant's own prose already narrates the hold, and a card repeating it would make one hold read
 * as two events.
 */
const PROMISE_TOOLS = new Set(['request_slot', 'confirm_held_slot'])

type RawToolCall = {
  name?: string
  args?: Record<string, unknown>
  result?: unknown
}

type DoneData = {
  thread_id?: string
  response?: string
  tool_calls?: RawToolCall[]
  ux_state?: string
  confirmation?: Record<string, unknown> | null
}

const UX_STATES: ReadonlySet<string> = new Set([
  'chat',
  'confirmation_required',
  'clarification_required',
  'capability_not_enabled',
  'persisted_success',
])

export function useDriverTurn(threadId: string) {
  const [messages, setMessages] = useAtom(messagesByThreadAtom)
  const setTurn = useSetAtom(turnAtom)
  const setUxState = useSetAtom(uxStateAtom)
  const setQuickReplies = useSetAtom(quickRepliesAtom)
  const [online, setOnline] = useAtom(onlineAtom)
  const [holds, setHolds] = useAtom(holdsByThreadAtom)
  const { setLive, setServerTime } = useCountdownClock()
  const abort = useRef<AbortController | null>(null)

  /**
   * Connection state wiring. Three consumers, one source (see `store.ts`'s `onlineAtom`).
   *
   * `setLive(false)` is the load-bearing half: it freezes the shared 1 Hz tick so every
   * countdown **holds at last-known** rather than free-running against a clock we can no longer
   * reconcile. A ticking countdown offline is a confident lie.
   */
  useEffect(() => {
    const sync = () => {
      const next = navigator.onLine
      setOnline(next)
      setLive(next)
    }
    window.addEventListener('online', sync)
    window.addEventListener('offline', sync)
    sync()
    return () => {
      window.removeEventListener('online', sync)
      window.removeEventListener('offline', sync)
    }
  }, [setOnline, setLive])

  // A driver navigating away mid-turn should not leave an inference running. The fetch-based SSE
  // client gives us AbortSignal for free, which was one of the stated reasons it is not
  // EventSource.
  useEffect(() => () => abort.current?.abort(), [])

  const append = useCallback(
    (message: DriverMessage) => {
      setMessages((prev) => ({ ...prev, [threadId]: [...(prev[threadId] ?? []), message] }))
    },
    [setMessages, threadId],
  )

  const patch = useCallback(
    (id: string, next: Partial<DriverMessage>) => {
      setMessages((prev) => ({
        ...prev,
        [threadId]: (prev[threadId] ?? []).map((m) => (m.id === id ? { ...m, ...next } : m)),
      }))
    },
    [setMessages, threadId],
  )

  /**
   * **U50's mutate-in-place, implemented literally.** Sets one card's state inside the option-set
   * part it already lives in, on the message that already carries it — no new message, no
   * replacement part.
   *
   * Two properties this deliberately has:
   *
   *  - It writes `perOption[slotId]` and **nothing else**, so the siblings stay `default`.
   *    `components.md` §2's *"Sibling of a held card"* row is explicit that a hold does not dim its
   *    siblings, and the mockup got that wrong precisely because the change was applied set-wide.
   *  - It patches only the **most recent** set containing the slot. An older, superseded set can
   *    contain the same `slot_id`, and mutating it would put a live HELD countdown on a card the
   *    driver can no longer act on.
   */
  const setOptionState = useCallback(
    (slotId: string, state: OptionCardState) => {
      setMessages((prev) => {
        const list = prev[threadId] ?? []
        const index = findLastOptionSetIndex(list, slotId)
        if (index < 0) return prev
        const next = list.slice()
        next[index] = {
          ...next[index],
          parts: next[index].parts.map((part) =>
            part.kind === 'optionSet' && part.optionSet.options.some((o) => o.slotId === slotId)
              ? {
                  ...part,
                  optionSet: {
                    ...part.optionSet,
                    perOption: { ...part.optionSet.perOption, [slotId]: state },
                  },
                }
              : part,
          ),
        }
        return { ...prev, [threadId]: next }
      })
    },
    [setMessages, threadId],
  )

  const setHold = useCallback(
    (hold: DriverHold | null) => {
      setHolds((prev) => ({ ...prev, [threadId]: hold }))
    },
    [setHolds, threadId],
  )

  /** Text and tool parts committed together, in ONE paint. */
  const commitDone = useCallback(
    (data: DoneData, bufferedText: string) => {
      const parts: DriverPart[] = []
      const prose = data.response ?? bufferedText
      if (prose.trim()) parts.push({ kind: 'text', text: prose })

      for (const call of data.tool_calls ?? []) {
        if (!call.name || !RENDERABLE_TOOLS.has(call.name)) continue
        const part = toPart(call)
        if (part) parts.push(part)
      }

      if (parts.length > 0) {
        append({
          id: crypto.randomUUID(),
          tier: 'AGENT',
          createdAt: new Date().toISOString(),
          parts,
        })
      }

      /**
       * The D2 promise transitions, applied after the parts are committed so the card being
       * mutated already exists in the transcript.
       *
       * The whole block is behind `heldStateEnabled`. With the flag off the server may still return
       * a HELD outcome (its own `TWO_PHASE_HOLD_ENABLED` is independent of this constant), and the
       * correct client behaviour then is to render nothing HELD-shaped rather than a chip the rest
       * of the surface is not wired for — the same fail-closed choice `option-card.tsx` makes.
       */
      let grantedHold: DriverHold | null = null
      let confirmedHold = false
      if (heldStateEnabled) {
        for (const call of data.tool_calls ?? []) {
          if (!call.name || !PROMISE_TOOLS.has(call.name)) continue
          if (call.name === 'request_slot') {
            const hold = toHoldFromRequestSlot(call.result)
            if (hold) grantedHold = hold
          } else if (call.name === 'confirm_held_slot') {
            // Only a real PENDING_CONFIRMATION consumes the hold. A `CONFLICTED` result
            // (`HOLD_EXPIRED` / `HOLD_ALREADY_ACTIONED` / `SLOT_CONFLICT_REFRESH_REQUIRED`) means
            // the hold is already gone server-side, which the countdown's own lapse handles --
            // clearing it here too would be harmless but would pre-empt screen 15's notice.
            const result = call.result as { status?: unknown } | undefined
            if (result?.status === 'PENDING_CONFIRMATION') confirmedHold = true
          }
        }
      }

      if (grantedHold) {
        setHold(grantedHold)
        // The tapped card takes the HELD treatment IN PLACE (U50, screen 5). `slot_id` comes off
        // the server's own result, never off the message the driver sent -- the tap goes through
        // the assistant as prose, so the server's answer is the only thing that knows which slot
        // was actually held.
        if (grantedHold.slotId) setOptionState(grantedHold.slotId, 'held')
        haptic('holdGranted')
      }
      if (confirmedHold) setHold(null)

      const ux = (UX_STATES.has(data.ux_state ?? '') ? data.ux_state : 'chat') as UxState
      setUxState(ux)
      /**
       * Quick replies.
       *
       * Screen 5's own pair — "Request this slot" / "Choose a different one" — is F7's specified
       * row and it takes precedence over the generic confirm/decline pair while a hold is live.
       * Both are literal driver messages (`components.md` §3: *"what they send: the literal text on
       * the chip, as a normal driver message"*), so the assistant receives an ordinary sentence and
       * decides for itself whether that means `confirm_held_slot`. Nothing here calls a tool.
       *
       * **No ordinal and no slot id in either string** — the second one names no option at all,
       * which is what keeps §7.2b's ordinal trap unreachable through this path too.
       */
      setQuickReplies(
        grantedHold
          ? [copy.heldRequestAction, copy.heldChooseAnother]
          : ux === 'confirmation_required'
            ? [copy.quickReplyConfirm, copy.quickReplyDecline]
            : [],
      )
      if (ux === 'persisted_success') haptic('confirmed')

      // `as_of` on any tool result is a server clock reading. Feeding it to the countdown
      // provider is what makes the 90-second hold honest on a phone whose clock is three minutes
      // fast -- components.md section 3: server time is authoritative, never bare Date.now().
      const asOf = firstAsOf(data.tool_calls)
      if (asOf) setServerTime(asOf)
    },
    [append, setHold, setOptionState, setQuickReplies, setServerTime, setUxState],
  )

  /**
   * Screen 15 (`HOLD_LAPSED`). Called once, by the countdown, when the hold's server deadline
   * passes with no confirm.
   *
   * Everything §15 specifies happens here and nothing else does: the card is **replaced in place**
   * (never removed), the notice is a centred system row beneath it, the state line clears because
   * the hold atom goes null, and a single "Find options again" quick reply is offered as part of
   * the notice rather than left for the driver to think of. The 400ms haptic fires from
   * `usePromiseCountdown`'s own lapse branch, so it is not duplicated here.
   *
   * It takes the hold as an argument rather than reading the atom, because the caller is a
   * countdown effect that already holds the exact value that expired — reading the atom would
   * reintroduce the race where a hold granted moments later gets lapsed by the previous one's timer.
   */
  const lapseHold = useCallback(
    (hold: DriverHold) => {
      setHolds((prev) => {
        // The guard that makes this idempotent AND race-safe: if the atom no longer holds *this*
        // hold, it was already confirmed or replaced, and lapsing it would erase a live promise.
        if (prev[threadId]?.holdId !== hold.holdId) return prev
        return { ...prev, [threadId]: null }
      })
      if (hold.slotId) setOptionState(hold.slotId, 'lapsed')
      const line = holdLine(hold)
      append(systemNotice('HOLD_LAPSED', copy.holdLapsed(line), 'event'))
      setQuickReplies([copy.findOptionsAgainAction])
    },
    [append, setHolds, setOptionState, setQuickReplies, threadId],
  )

  const send = useCallback(
    async (text: string, existing?: DriverMessage) => {
      // Reused verbatim on Retry -- see the U70 note in this file's header.
      const clientMessageId = existing?.clientMessageId ?? crypto.randomUUID()
      const localId = existing?.id ?? clientMessageId

      if (existing) {
        patch(localId, { delivery: 'sending' })
      } else {
        // Optimistic bubble, immediately, with `○ sending` (flows-and-states.md "Loading").
        append({
          id: localId,
          tier: 'DRIVER',
          createdAt: new Date().toISOString(),
          parts: [{ kind: 'text', text }],
          delivery: online ? 'sending' : 'queued',
          clientMessageId,
        })
      }

      if (!online) {
        // Offline: the message stays `queued` and the composer stays enabled. Nothing is sent
        // and nothing pretends to have been -- `queued` is words, not a glyph, exactly so it
        // cannot be misread as sent.
        append(systemNotice('CONNECTION_LOST', copy.connectionLost, 'connection'))
        return
      }

      const controller = new AbortController()
      abort.current = controller
      setTurn({ startedAtMs: Date.now(), currentTool: null, bufferedText: '', error: null })
      setQuickReplies([])

      let buffered = ''
      try {
        // The token is NOT resolved here any more (2026-09-01): `streamChat` reads it from
        // supabase-js itself, so this surface goes through the same attach-on-request /
        // central-401 path as every other call. See `core/http/api.ts`'s interceptor contract.
        for await (const frame of streamChat({
          url: `${apiBase}/api/v1/chat/stream`,
          body: {
            message: text,
            thread_id: threadId === NEW_THREAD ? null : threadId,
            client_message_id: clientMessageId,
          },
          signal: controller.signal,
        })) {
          if (frame.event === 'status') {
            const tool = (frame.data as { tool?: string })?.tool ?? null
            setTurn((t) => (t ? { ...t, currentTool: tool } : t))
          } else if (frame.event === 'token') {
            // BUFFERED, not appended. See the Fork C note above.
            buffered += (frame.data as { content?: string })?.content ?? ''
          } else if (frame.event === 'error') {
            const e = frame.data as { code?: string; message?: string }
            throw new Error(e?.message || e?.code || 'Turn failed')
          } else if (frame.event === 'done') {
            commitDone(frame.data as DoneData, buffered)
          }
        }
        patch(localId, { delivery: 'delivered' })
      } catch (err) {
        if (controller.signal.aborted) return
        // Screen 27A. Text is preserved (the optimistic bubble still holds it), Retry is inline,
        // 300ms haptic. Never a toast: the failure belongs beside the message it happened to.
        patch(localId, { delivery: 'failed' })
        haptic('sendFailed')
        setTurn((t) =>
          t ? { ...t, error: { code: 'SEND_FAILED', message: String(err) } } : t,
        )
      } finally {
        setTurn(null)
        abort.current = null
      }
    },
    [append, commitDone, patch, online, setQuickReplies, setTurn, threadId],
  )

  const retry = useCallback(
    (m: DriverMessage) => {
      const part = m.parts.find((p) => p.kind === 'text')
      if (part?.kind === 'text') void send(part.text, m)
    },
    [send],
  )

  return {
    messages: messages[threadId] ?? [],
    send,
    retry,
    /** The live hold on THIS thread, or null. Server-stamped `expiresAt` guaranteed. */
    hold: holds[threadId] ?? null,
    setHold,
    lapseHold,
  }
}

/**
 * Index of the most recent message carrying an option set that contains `slotId`, or `-1`.
 *
 * Backwards, and that is the whole behaviour: an older set can legitimately contain the same slot,
 * and mutating it would put a live HELD countdown on a card the driver can no longer act on
 * (`components.md` §2's Superseded row).
 */
function findLastOptionSetIndex(list: DriverMessage[], slotId: string): number {
  for (let i = list.length - 1; i >= 0; i -= 1) {
    const hit = list[i].parts.some(
      (p) => p.kind === 'optionSet' && p.optionSet.options.some((o) => o.slotId === slotId),
    )
    if (hit) return i
  }
  return -1
}

/**
 * The operational line a lapse notice names — "Dock D1 · 13:00–14:15".
 *
 * `copy.holdLapsed` interpolates it into *"That hold has lapsed — {line} is available to other
 * drivers again"*, so it has to be a phrase that reads as a subject. When the hold carries no
 * window (the `request_slot` receipt does not include one), the fallback is deliberately generic
 * rather than a fabricated dock or time: `voice-and-tone.md` forbids a bare time, and inventing an
 * interval in a sentence about capacity someone else can now take is the worst place to guess.
 */
function holdLine(hold: DriverHold): string {
  const dock = hold.dockCode ? `Dock ${hold.dockCode}` : null
  if (dock && hold.windowStart && hold.windowEnd) {
    const t = (iso: string) =>
      new Intl.DateTimeFormat('en-IN', {
        hour: '2-digit',
        minute: '2-digit',
        hour12: false,
      }).format(new Date(iso))
    return `${dock} · ${t(hold.windowStart)}–${t(hold.windowEnd)}`
  }
  return dock ?? 'that slot'
}

/** `find_feasible_slots` / `explain_slot_eligibility` -> a typed part. Never text parsing. */
function toPart(call: RawToolCall): DriverPart | null {
  const result = call.result
  if (!result || typeof result !== 'object') return null

  if (call.name === 'find_feasible_slots') {
    const raw = result as Record<string, unknown>
    if (typeof raw.recommendation_id !== 'string') return null
    return { kind: 'optionSet', optionSet: toOptionSet(raw as never) }
  }

  if (call.name === 'explain_slot_eligibility') {
    const raw = result as Record<string, unknown>
    if (typeof raw.slot_id !== 'string') return null
    // dock_code is not on SlotEligibilityResult (it is a slot-level field the tool does not echo
    // back). The tool's own `args` carry the slot the driver asked about, so the card names the
    // slot rather than inventing a dock code it was never given.
    const dockCode = String((call.args?.dock_code as string | undefined) ?? '')
    return { kind: 'eligibility', answer: toEligibilityAnswer(raw as never, dockCode) }
  }

  return null
}

function firstAsOf(calls?: RawToolCall[]): string | null {
  for (const call of calls ?? []) {
    const asOf = (call.result as { as_of?: unknown } | undefined)?.as_of
    if (typeof asOf === 'string') return asOf
  }
  return null
}

export function systemNotice(
  code: DriverEventCode,
  body: string,
  variant: SystemNoticeVariant,
): DriverMessage {
  return {
    id: crypto.randomUUID(),
    tier: 'SYSTEM',
    createdAt: new Date().toISOString(),
    parts: [],
    notice: { variant, code, body },
  }
}

/** Sentinel for "the driver is starting a conversation the server has no thread for yet".
 *  `/chat/stream` accepts `thread_id: null` and mints one, returning it on the `start` frame. */
export const NEW_THREAD = '__new__'
