import { useAtom, useSetAtom } from 'jotai'
import { useCallback, useEffect, useRef } from 'react'

import { getSession } from '@/core/auth/supabase'
import { streamChat } from '@/core/http/sse'
import { useCountdownClock } from '@/shared/lib/countdown'
import { copy } from './copy'
import { haptic } from './haptics'
import { toEligibilityAnswer, toOptionSet } from './mappers'
import {
  messagesByThreadAtom,
  onlineAtom,
  quickRepliesAtom,
  turnAtom,
  uxStateAtom,
} from './store'
import type {
  DriverEventCode,
  DriverMessage,
  DriverPart,
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

      const ux = (UX_STATES.has(data.ux_state ?? '') ? data.ux_state : 'chat') as UxState
      setUxState(ux)
      // The only client-supplied quick replies, and only on the one branch where the two
      // readings are closed and generic. See copy.ts's note on the missing server contract.
      setQuickReplies(
        ux === 'confirmation_required' ? [copy.quickReplyConfirm, copy.quickReplyDecline] : [],
      )
      if (ux === 'persisted_success') haptic('confirmed')

      // `as_of` on any tool result is a server clock reading. Feeding it to the countdown
      // provider is what makes the 90-second hold honest on a phone whose clock is three minutes
      // fast -- components.md section 3: server time is authoritative, never bare Date.now().
      const asOf = firstAsOf(data.tool_calls)
      if (asOf) setServerTime(asOf)
    },
    [append, setQuickReplies, setServerTime, setUxState],
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
        const session = await getSession()
        if (!session?.access_token) throw new Error('Not authenticated')

        for await (const frame of streamChat({
          url: `${apiBase}/api/v1/chat/stream`,
          accessToken: session.access_token,
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

  return { messages: messages[threadId] ?? [], send, retry }
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
