import { useEffect, useRef } from 'react'
import { OctagonAlert, TriangleAlert } from 'lucide-react'

import { Button } from '@/shared/ui/button'
import { EmptyState } from '@/shared/ui/empty-state'
import { Skeleton } from '@/shared/ui/skeleton'
import { cn } from '@/shared/lib/utils'
import { describeDelivery } from '../lib/delivery'
import { messageClock, relativeTime } from '../lib/format'
import type { ThreadMessage } from '../lib/types'

/**
 * The thread's durable transcript, read from `GET /operations/threads/{id}/messages`.
 *
 * **This replaces an honest stub, not a fake.** E5.2 shipped a dashed-border note here reading
 * "Thread preview isn't available yet -- there is no backend read for operations to view a driver
 * conversation", because at that point `GET /chat/history` was `require_roles(DRIVER)`-only and
 * Redis-backed. `operations_reads.get_thread_messages` now exists and is `chat_messages`-backed,
 * which is the right source for this caller: the console needs the durable, complete, attributable
 * record -- including `sender_type = 'OPERATIONS'` rows and the takeover dividers -- not the
 * driver's bounded 24h Redis view.
 *
 * ## U47's tiers, mapped to `sender_type`
 *
 * `01-driver-chat/screens.md` section 3's table is the source; this surface renders the same
 * substrate scoped to a different sender set. The one intentional inversion: on the **driver's**
 * screen the driver is the right-aligned "self". On the **coordinator's** screen the coordinator
 * is -- so `OPERATIONS` sits right and `DRIVER` sits left. The tiers themselves (bubble weight,
 * named attribution, centred system events) are unchanged, because the property they protect is
 * "a person and a bot must not be mistaken for each other", which is orientation-independent.
 */

type PendingMessage = {
  /** The idempotency key, reused verbatim on retry -- also the `client_message_id`. */
  key: string
  text: string
  state: 'sending' | 'failed'
}

export function ThreadTranscript({
  state,
  messages,
  pending,
  /** `delivery_reason` keyed by `chat_message_id` for messages this session posted that the
   *  driver's live feed did not receive. Not persisted anywhere -- the API has no per-message
   *  delivery column -- so it is deliberately session-scoped and says so in the UI. */
  undelivered,
  currentUserId,
  onRetry,
  onRetryPending,
  onDiscardPending,
}: {
  state: 'loading' | 'error' | 'ready' | 'none'
  messages: ThreadMessage[]
  pending: PendingMessage[]
  undelivered: Record<string, string | null>
  currentUserId: string | null
  onRetry: () => void
  onRetryPending: (key: string) => void
  onDiscardPending: (key: string) => void
}) {
  const endRef = useRef<HTMLDivElement | null>(null)
  const count = messages.length + pending.length

  // Scroll the newest message into view when the transcript grows. `block: 'nearest'` so this
  // never yanks the whole page when the pane is already scrolled to the bottom.
  useEffect(() => {
    if (count > 0) endRef.current?.scrollIntoView({ block: 'nearest' })
  }, [count])

  if (state === 'none') {
    return (
      <p className="rounded-md border border-dashed border-border p-3 text-body text-muted-foreground">
        This escalation has no driver conversation attached. Nothing links it to a chat thread, so
        there is nothing to read or take over here.
      </p>
    )
  }

  if (state === 'loading') {
    return (
      <div aria-busy="true" aria-label="Loading conversation" className="flex flex-col gap-3">
        <Skeleton className="h-12 w-3/4" />
        <Skeleton className="ml-auto h-12 w-2/3" />
        <Skeleton className="h-12 w-1/2" />
      </div>
    )
  }

  if (state === 'error') {
    // Regional, not global: `edge-cases.md` section 5's degradation posture -- a failure here must
    // not take the queue or the terminal actions down with it.
    return (
      <div role="alert">
        <EmptyState
          icon={OctagonAlert}
          title="Couldn't load this conversation — usually a connection problem."
          body="Acknowledge, Resolve and Cancel still work."
          actions={
            <Button variant="constructive" onClick={onRetry}>
              Retry
            </Button>
          }
          className="items-start px-0 text-left"
        />
      </div>
    )
  }

  if (count === 0) {
    return (
      <p className="rounded-md border border-dashed border-border p-3 text-body text-muted-foreground">
        No messages on this thread yet.
      </p>
    )
  }

  return (
    <div className="flex max-h-80 flex-col gap-2 overflow-auto rounded-md border border-border p-3">
      {messages.map((m, i) => (
        <MessageRow
          key={m.chat_message_id}
          message={m}
          previous={messages[i - 1] ?? null}
          currentUserId={currentUserId}
          undeliveredReason={
            m.chat_message_id in undelivered ? undelivered[m.chat_message_id] : undefined
          }
        />
      ))}

      {pending.map((p) => (
        <PendingRow
          key={p.key}
          pending={p}
          onRetry={() => onRetryPending(p.key)}
          onDiscard={() => onDiscardPending(p.key)}
        />
      ))}

      <div ref={endRef} />
    </div>
  )
}

/**
 * `SYSTEM` rows are the takeover and hand-back notices `take_over_thread` / `hand_back_thread`
 * insert. `01-driver-chat/components.md` section 5 and `voice-and-tone.md`'s `HUMAN_JOINED`
 * template both require these render as a **centred divider with rules either side, not a
 * bubble** -- "it is an event, not a message" -- and never dismissible.
 */
function SystemDivider({ text }: { text: string }) {
  return (
    <div className="my-2 flex items-center gap-2" role="separator" aria-label={text}>
      <span aria-hidden="true" className="h-px flex-1 bg-border" />
      <span className="text-micro text-muted-foreground">{text}</span>
      <span aria-hidden="true" className="h-px flex-1 bg-border" />
    </div>
  )
}

function MessageRow({
  message,
  previous,
  currentUserId,
  undeliveredReason,
}: {
  message: ThreadMessage
  previous: ThreadMessage | null
  currentUserId: string | null
  /** `undefined` = delivered or unknown (render nothing). A present key -- including `null` --
   *  means this session posted it and the driver's feed did not get it. */
  undeliveredReason?: string | null
}) {
  if (message.sender_type === 'SYSTEM') {
    return <SystemDivider text={message.message_text} />
  }

  const isSelf = message.sender_type === 'OPERATIONS' || message.sender_type === 'WAREHOUSE'
  const isMine = isSelf && currentUserId !== null && message.sender_reference === currentUserId

  // Consecutive same-sender grouping within 2 minutes: attribution header on the first only
  // (`01-driver-chat/components.md` section 4's grouping rule).
  const grouped =
    previous !== null &&
    previous.sender_type === message.sender_type &&
    previous.sender_reference === message.sender_reference &&
    Math.abs(new Date(message.message_ts).getTime() - new Date(previous.message_ts).getTime()) <
      2 * 60_000

  return (
    <div className={cn('flex flex-col gap-0.5', isSelf ? 'items-end' : 'items-start')}>
      {!grouped ? (
        <span className="text-micro tracking-wide text-muted-foreground uppercase">
          {attribution(message, isMine)}
        </span>
      ) : null}

      <div
        className={cn(
          'max-w-[85%] rounded-md px-3 py-2 text-body',
          // U47: the OPERATIONS/WAREHOUSE tier carries the HEAVIER border. The AI/human
          // distinction has to survive a glance, and it is carried by border weight + real name
          // together, not by either alone.
          isSelf
            ? 'border border-border bg-selected'
            : message.sender_type === 'AGENT'
              ? 'border border-border/60 bg-card'
              : 'border border-input bg-card',
        )}
      >
        {message.message_text}
      </div>

      <span className="font-data text-micro tabular-nums text-muted-foreground">
        {messageClock(message.message_ts)} · {relativeTime(message.message_ts)}
      </span>

      {undeliveredReason !== undefined ? (
        <UndeliveredNotice reason={undeliveredReason} />
      ) : null}
    </div>
  )
}

function attribution(message: ThreadMessage, isMine: boolean): string {
  switch (message.sender_type) {
    case 'DRIVER':
      return message.sender_name ? `${message.sender_name} · Driver` : 'Driver'
    case 'AGENT':
      return 'SetuHaul assistant'
    case 'OPERATIONS':
      if (isMine) return 'You · Operations'
      return message.sender_name ? `${message.sender_name} · Operations` : 'Operations'
    case 'WAREHOUSE':
      return message.sender_name ? `${message.sender_name} · Warehouse` : 'Warehouse'
    default:
      return message.sender_type
  }
}

/**
 * The `delivered: false` marker. **This is the residual issue #58 left open, made visible.**
 *
 * Rendered per message rather than as a one-off toast, because the fact is permanent: nothing
 * back-fills Redis from `chat_messages`, so this message will never reach the driver, and a
 * coordinator scrolling back through the thread tomorrow needs to still see that. A toast would
 * have told them once and then erased the only trace.
 *
 * `role="status"` rather than `role="alert"`: the write itself succeeded, so this is not a failed
 * action interrupting the coordinator -- it is a qualification on a success, which
 * `accessibility-behaviour.md`'s politeness matrix puts in the polite tier.
 */
function UndeliveredNotice({ reason }: { reason: string | null }) {
  const explanation = describeDelivery(reason)
  return (
    <div
      role="status"
      className="mt-0.5 flex max-w-[85%] items-start gap-1.5 rounded-md bg-warning-bg px-2 py-1 text-supporting text-warning-fg"
    >
      <TriangleAlert className="mt-0.5 size-3.5 shrink-0" aria-hidden="true" />
      <span>
        {/* The lead sentence comes from `describeDelivery`, not a hard-coded "Not shown to the
            driver" -- several reasons are not that, and a fixed prefix would have mislabelled
            them. Each reason states its own fact. */}
        <strong className="font-medium">{explanation.title}</strong> {explanation.detail}
      </span>
    </div>
  )
}

/**
 * A message this session is posting, or has failed to post.
 *
 * The failed variant is the one that matters: `01-driver-chat/components.md` section 4's
 * delivery-status table specifies "not sent" **in explicit words, not a symbol, so it cannot be
 * mistaken for sent**, paired with an inline Retry. Retry re-posts with the **same** key, so the
 * backend's idempotency record collapses a double-press into one message rather than sending a
 * driver the same sentence twice.
 */
function PendingRow({
  pending,
  onRetry,
  onDiscard,
}: {
  pending: PendingMessage
  onRetry: () => void
  onDiscard: () => void
}) {
  return (
    <div className="flex flex-col items-end gap-0.5">
      <span className="text-micro tracking-wide text-muted-foreground uppercase">
        You · Operations
      </span>
      <div
        className={cn(
          'max-w-[85%] rounded-md border px-3 py-2 text-body',
          pending.state === 'failed'
            ? 'border-destructive/50 bg-card'
            : 'border-border bg-selected opacity-70',
        )}
      >
        {pending.text}
      </div>

      {pending.state === 'sending' ? (
        <span className="text-micro text-muted-foreground">Sending…</span>
      ) : (
        <div role="alert" className="flex items-center gap-2">
          <span className="text-micro font-medium text-destructive">Not sent.</span>
          {/* `relative tap-floor` (issue #91): both of these draw at `text-micro`'s 11px/1.3,
              i.e. 14.3px tall, against this surface's 32px --tap. They stay 14.3px tall --
              growing them would push the failed-send row into the transcript's rhythm -- and
              gain an invisible 32x32 pointer region instead. Retry and Discard sit 8px apart,
              so their expanded regions overlap slightly in the middle but neither covers the
              other's centre; verified by elementFromPoint, not by geometry. */}
          <button
            type="button"
            onClick={onRetry}
            className="relative tap-floor text-micro text-link underline focus-visible:outline-2 focus-visible:outline-ring"
          >
            Retry
          </button>
          <button
            type="button"
            onClick={onDiscard}
            className="relative tap-floor text-micro text-muted-foreground underline focus-visible:outline-2 focus-visible:outline-ring"
          >
            Discard
          </button>
        </div>
      )}
    </div>
  )
}

export type { PendingMessage }
