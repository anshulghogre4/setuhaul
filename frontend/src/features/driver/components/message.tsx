import { Hexagon, TriangleAlert, WifiOff } from 'lucide-react'
import type { ReactNode } from 'react'

import { Avatar, AvatarFallback } from '@/shared/ui/avatar'
import { cn } from '@/shared/lib/utils'
import { copy } from '../lib/copy'
import { formatMessageTimestamp } from '../lib/format'
import type { DeliveryStatus, DriverMessage, SenderTier } from '../lib/types'

/**
 * The three message tiers plus the centred system tier (U47, `screens.md` section 3).
 *
 * | Sender | Alignment | Treatment |
 * |---|---|---|
 * | `DRIVER` | Right | Filled bubble, `surface-selected`. Delivery status beneath. |
 * | `AGENT` | Left | `surface-raised` + `border-subtle`. Header `⬡ SetuHaul assistant`. |
 * | `OPERATIONS` | Left | `surface-raised` + `border-default` (heavier). Header **person's name + role**, with avatar. |
 * | `SYSTEM` | Centred | **No bubble** — an event, not a message. |
 *
 * **The AI/human distinction must survive a glance.** A driver who thinks they are still talking
 * to a bot phrases things differently from one who knows a person is reading. The avatar, the
 * real name and the heavier border carry that **together** — not any one of them alone, which is
 * why none of the three is optional on the OPERATIONS tier.
 *
 * Consecutive messages from the same sender within 2 minutes group: attribution header on the
 * first only, timestamp on the last only. Grouping is decided by the caller (it needs the
 * neighbours), which is why `showAttribution` / `showTimestamp` are props rather than derived
 * here.
 *
 * `role="listitem"` inside the transcript's `role="log"` — the web-design-guidelines pass found
 * 0 of 54 mockup messages carrying it, i.e. a `log` with no list items.
 */

const BUBBLE: Record<Exclude<SenderTier, 'SYSTEM'>, string> = {
  DRIVER: 'bg-selected border border-transparent',
  AGENT: 'bg-card border border-border',
  // border-default (--color-input) is deliberately heavier than AGENT's border-subtle.
  OPERATIONS: 'bg-card border-2 border-input',
}

export type DriverMessageRowProps = {
  message: DriverMessage
  nowMs: number
  showAttribution?: boolean
  showTimestamp?: boolean
  /** Rendered inside the bubble, after the text parts: option sets, eligibility answers,
   *  receipts. Passed in rather than switched on here so this component stays about the
   *  *tier*, and the parts stay one place (see `transcript.tsx`). */
  children?: ReactNode
  onRetry?: (message: DriverMessage) => void
}

export function DriverMessageRow({
  message,
  nowMs,
  showAttribution = true,
  showTimestamp = true,
  children,
  onRetry,
}: DriverMessageRowProps) {
  if (message.tier === 'SYSTEM') {
    return <SystemNoticeRow message={message} />
  }

  const isDriver = message.tier === 'DRIVER'

  return (
    <div
      role="listitem"
      className={cn('flex flex-col', isDriver ? 'items-end' : 'items-start')}
      data-tier={message.tier}
    >
      {showAttribution ? <Attribution message={message} /> : null}

      <div
        className={cn(
          'max-w-[85%] rounded-lg px-4 py-3 text-body-lg',
          // min-w-0 so a long unbroken token (an order reference pasted in) wraps instead of
          // widening the flex parent -- the web-design-guidelines pass flagged the absence of
          // min-w-0 on this surface's variable-length lines.
          'min-w-0 break-words',
          BUBBLE[message.tier],
        )}
      >
        {message.parts.map((part, i) =>
          part.kind === 'text' ? (
            <p key={i} className={cn(i > 0 && 'mt-2')}>
              {part.text}
            </p>
          ) : null,
        )}
        {children}
      </div>

      {isDriver ? (
        <Delivery status={message.delivery} onRetry={onRetry ? () => onRetry(message) : undefined} />
      ) : null}

      {showTimestamp ? (
        <span className="mt-1 text-body text-subtle-foreground">
          {formatMessageTimestamp(message.createdAt, nowMs)}
        </span>
      ) : null}
    </div>
  )
}

function Attribution({ message }: { message: DriverMessage }) {
  if (message.tier === 'DRIVER') return null

  if (message.tier === 'AGENT') {
    return (
      <p className="mb-1 flex items-center gap-1.5 text-body text-muted-foreground">
        <Hexagon size={14} strokeWidth={2} aria-hidden="true" />
        SetuHaul assistant
      </p>
    )
  }

  // OPERATIONS / WAREHOUSE: avatar + real name + role, all three.
  const author = message.author
  return (
    <div className="mb-1 flex items-center gap-2">
      <Avatar className="size-6">
        {/* aria-hidden: an avatar initial is a non-text graphic and the name is spelled out
            beside it at 14px, so nothing is carried by the glyph alone. This is the stated
            exclusion from the surface's 14px floor (F1), not an oversight. */}
        <AvatarFallback aria-hidden="true" className="text-body">
          {author?.initials ?? '?'}
        </AvatarFallback>
      </Avatar>
      <p className="text-body font-semibold">
        {author?.name ?? 'Operations'}
        <span className="font-normal text-muted-foreground"> · {author?.role ?? 'Operations'}</span>
      </p>
    </div>
  )
}

/**
 * Delivery status (`01-driver-chat/components.md` section 4). **Driver messages only, and
 * deliberately no "read" receipt** — there is no human on the other end in normal operation and
 * implying one would misrepresent the assistant.
 *
 * `queued` is **explicit words, not a symbol**, so it cannot be mistaken for sent. That is the
 * single most important row in this table: a queued message is one the server has never seen.
 */
function Delivery({ status, onRetry }: { status?: DeliveryStatus; onRetry?: () => void }) {
  if (!status) return null

  if (status === 'failed') {
    return (
      <p className="mt-1 flex items-center gap-2 text-body text-danger-fg">
        <span className="flex items-center gap-1">
          <TriangleAlert size={14} strokeWidth={2} aria-hidden="true" />
          {copy.messageNotSent}
        </span>
        {/* Inline Retry, and the caller resends with the SAME client_message_id so the server's
            dedupe collapses a double-send (U70). That is what makes this button safe and what
            makes edge-cases.md section 11's duplicate invisible to the driver. */}
        {onRetry ? (
          <button
            type="button"
            onClick={onRetry}
            className="min-h-11 underline focus-visible:outline-2 focus-visible:outline-ring focus-visible:outline-offset-2"
          >
            {copy.retryAction}
          </button>
        ) : null}
      </p>
    )
  }

  if (status === 'queued') {
    return (
      <p className="mt-1 flex items-center gap-1 text-body text-muted-foreground">
        <WifiOff size={14} strokeWidth={2} aria-hidden="true" />
        {copy.messageQueued}
      </p>
    )
  }

  const glyph = status === 'sending' ? '○' : status === 'sent' ? '✓' : '✓✓'
  const spoken = status === 'sending' ? 'sending' : status === 'sent' ? 'sent' : 'delivered'
  return (
    <p className="mt-1 text-body text-muted-foreground">
      <span aria-hidden="true">{glyph}</span>
      <span className="sr-only">{spoken}</span>
    </p>
  )
}

/**
 * The system tier: centred, **no bubble** (`01-driver-chat/components.md` section 5). Never
 * dismissible — these are the transcript's record of what happened, and section 12.2 requires
 * the driver be shown when an option changes or disappears.
 *
 * ## Politeness is split, and the split is the point
 *
 * `accessibility.md`, "Screen reader": `role="status"` for informational,
 * **`role="alert"` for hold lapsed / option withdrawn**. The mockup had 4 of 8 notices on
 * `alert` and **none** on `status`, i.e. everything announced assertively or not at all. The map
 * below is the fix, and it is data rather than a conditional at each call site so a new event
 * code cannot default to the wrong politeness silently.
 */
const ASSERTIVE_EVENTS: ReadonlySet<string> = new Set([
  'HOLD_LAPSED',
  'OPTION_WITHDRAWN',
  'PENDING_EXPIRED',
  'COMMIT_FAILED',
])

function SystemNoticeRow({ message }: { message: DriverMessage }) {
  const notice = message.notice
  if (!notice) return null

  const assertive = notice.code ? ASSERTIVE_EVENTS.has(notice.code) : false

  if (notice.variant === 'takeover') {
    return (
      <div role="listitem" className="my-4">
        {/* Full-width divider rules above AND below. A permanent event, not a message and not
            dismissible: section 7.4 — "silent takeover reads as the bot ignoring them." */}
        <div
          role="status"
          className="flex items-center gap-3 text-body text-muted-foreground"
        >
          <span aria-hidden="true" className="h-px flex-1 bg-border" />
          <span className="text-center">{notice.body}</span>
          <span aria-hidden="true" className="h-px flex-1 bg-border" />
        </div>
      </div>
    )
  }

  return (
    <div role="listitem" className="my-3 flex justify-center">
      <p
        role={assertive ? 'alert' : 'status'}
        className="flex max-w-[85%] items-start gap-1.5 text-center text-body text-muted-foreground"
      >
        {notice.variant === 'connection' ? (
          <WifiOff size={14} strokeWidth={2} aria-hidden="true" className="mt-0.5 shrink-0" />
        ) : null}
        <span>{notice.body}</span>
      </p>
    </div>
  )
}
