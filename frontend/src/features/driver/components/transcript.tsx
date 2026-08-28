import { useAtomValue } from 'jotai'
import { useCallback, useEffect, useRef, useState } from 'react'

import { useCountdownClock } from '@/shared/lib/countdown'
import { cn } from '@/shared/lib/utils'
import { turnAtom } from '../lib/store'
import { DriverMessageRow } from './message'
import { MessageParts } from './message-parts'
import { ScrollToLatest } from './scroll-to-latest'
import { ThinkingIndicator } from './thinking'
import type { DriverMessage, DriverOption } from '../lib/types'

/**
 * The transcript.
 *
 * ## The one behaviour both chat checklists call the common bug
 *
 * **Never auto-scroll while the driver is reading history.** New content arriving must not yank
 * the view. So: auto-scroll happens only when the driver is already pinned near the bottom, and
 * otherwise the `ScrollToLatest` pill appears with a count. Implemented with a scroll listener
 * and a "pinned" flag rather than `scrollIntoView` on every render, which is the shape that
 * produces the bug.
 *
 * The pill's count **counts messages, not events** — a card mutating in place (U50) does not
 * increment it, because nothing new arrived.
 *
 * ## `role="log"` with real list items
 *
 * `accessibility.md`: message is `role="listitem"` within a `role="log"` transcript. The mockup
 * had 24 `role="log"` containers and **0 of 54** messages carrying `listitem`, i.e. a log with
 * no items. The `listitem` roles live on the message rows (`message.tsx`); the log lives here.
 *
 * The log is deliberately **not** an `aria-live` region: only four things interrupt on this
 * surface (promise-state transitions, countdown thresholds, option withdrawn / hold lapsed,
 * human joined) and each carries its own region. A driver using a screen reader while an option
 * set arrives must not have three cards announced over the assistant's message.
 *
 * ## `overscroll-behavior: contain`
 *
 * Stops a scroll that reaches the top of the transcript from chaining into a pull-to-refresh
 * that reloads the page mid-exception. Zero occurrences in the mockup; it matters on a
 * phone-first PWA.
 *
 * ## Virtualisation — the design's claim does not hold for the pinned version
 *
 * `accessibility.md` ("Low-end device performance") says *"Transcript virtualises beyond ~50
 * messages — assistant-ui provides this."* **Checked against the installed
 * `@assistant-ui/react@0.15.16` rather than the library's current docs: it does not.** There is
 * no virtualised list component; what 0.15.16 offers is `unstable_useThreadMessageIds` +
 * `ThreadPrimitive.Unstable_MessageById`, both carrying `@deprecated Unstable / Experimental —
 * may change in any release`, as *building blocks* for one. This is exactly the U52 lesson the
 * spec warned about (a library's headline capability may not be in the version you install), so
 * it is recorded rather than assumed, and virtualisation is **not** built here: at this
 * product's scale an operational thread is tens of messages, and taking an experimental API
 * dependency to pre-solve a load nobody has is the wrong trade.
 */

export type TranscriptProps = {
  messages: DriverMessage[]
  facilityName?: string
  onSelectOption?: (option: DriverOption) => void
  onEscalate?: () => void
  onRetry?: (message: DriverMessage) => void
}

/** Consecutive messages from the same sender within 2 minutes group: attribution on the first
 *  only, timestamp on the last only (`components.md` section 4, and the checklist's
 *  *Sender identification* tip). */
const GROUP_WINDOW_MS = 120_000

export function Transcript({
  messages,
  facilityName,
  onSelectOption,
  onEscalate,
  onRetry,
}: TranscriptProps) {
  const turn = useAtomValue(turnAtom)
  const { now } = useCountdownClock()
  const viewport = useRef<HTMLDivElement>(null)
  const [pinned, setPinned] = useState(true)
  const [unseen, setUnseen] = useState(0)
  const lastCount = useRef(messages.length)

  const scrollToBottom = useCallback(() => {
    const el = viewport.current
    if (!el) return
    el.scrollTop = el.scrollHeight
    setPinned(true)
    setUnseen(0)
  }, [])

  // "More than one screen from the bottom" is the design's own threshold for the pill, so the
  // pinned test uses the viewport's own height rather than a fixed pixel number.
  const onScroll = useCallback(() => {
    const el = viewport.current
    if (!el) return
    const distance = el.scrollHeight - el.scrollTop - el.clientHeight
    const nowPinned = distance < el.clientHeight
    setPinned(nowPinned)
    if (nowPinned) setUnseen(0)
  }, [])

  useEffect(() => {
    const added = messages.length - lastCount.current
    lastCount.current = messages.length
    if (added <= 0) return
    if (pinned) {
      scrollToBottom()
    } else {
      // Counts MESSAGES. A mutated card does not change `messages.length`, so it cannot
      // increment this -- which is the required behaviour, achieved structurally rather than by
      // remembering to exclude it.
      setUnseen((n) => n + added)
    }
  }, [messages.length, pinned, scrollToBottom])

  return (
    <div className="relative flex-1 overflow-hidden">
      <div
        ref={viewport}
        onScroll={onScroll}
        role="log"
        aria-label="Conversation"
        className={cn(
          'h-full overflow-y-auto overscroll-contain',
          // content padding is 24px at `comfortable` (F12: foundation wins over the mockup's
          // 12px). Driven by the density variable rather than a literal so the driver route root
          // stays the single place density is set.
          'flex flex-col gap-3 p-(--content-p)',
        )}
      >
        {messages.map((message, i) => {
          const prev = messages[i - 1]
          const next = messages[i + 1]
          const grouped = (a?: DriverMessage, b?: DriverMessage) =>
            !!a &&
            !!b &&
            a.tier === b.tier &&
            Math.abs(Date.parse(b.createdAt) - Date.parse(a.createdAt)) < GROUP_WINDOW_MS

          return (
            <DriverMessageRow
              key={message.id}
              message={message}
              nowMs={now}
              showAttribution={!grouped(prev, message)}
              showTimestamp={!grouped(message, next)}
              onRetry={onRetry}
            >
              {/* Structured parts render as siblings of the text, from typed tool results --
                  never parsed out of the prose (U48). Shared with the verification gallery so
                  the two cannot diverge -- see message-parts.tsx on why that matters. */}
              <MessageParts
                message={message}
                facilityName={facilityName}
                onSelectOption={onSelectOption}
                onEscalate={onEscalate}
              />
            </DriverMessageRow>
          )
        })}

        {turn ? <ThinkingIndicator startedAtMs={turn.startedAtMs} nowMs={now} /> : null}
      </div>

      {!pinned ? <ScrollToLatest newCount={unseen} onClick={scrollToBottom} /> : null}
    </div>
  )
}
