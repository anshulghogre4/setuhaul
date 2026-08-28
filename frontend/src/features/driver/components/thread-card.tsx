import { Link } from 'react-router-dom'

import { useCountdownClock } from '@/shared/lib/countdown'
import { cn } from '@/shared/lib/utils'
import { formatMessageTimestamp } from '../lib/format'
import { PromiseChip } from './promise-chip'
import type { DriverThread, PriorityCode } from '../lib/types'

/**
 * The thread list's row (`01-driver-chat/components.md` section 1, anatomy in `screens.md`
 * section 1).
 *
 * The whole card is the tap target — **minimum 88px tall**, well past the 44×44 floor, because
 * this is glanced at and tapped one-handed in sunlight. Rendered as a `<Link>` so it is a real
 * navigable target with real keyboard behaviour, not a div with an onClick.
 *
 * ## The unread/priority edge collision (F6), resolved here
 *
 * `stitch-prompts.md`'s F6 flags it and the mockup never draws them together: the **unread
 * marker** is specified as a 2px `border-focus` left inset and the **priority marker** as a 3px
 * left edge bar (`00-foundations/components.md` section 5). Two thin vertical bars competing for
 * one edge — the exact hazard `components.md` section 7 names for the rail, recurring on a
 * different component.
 *
 * **Resolution taken here, and it is a build decision the design left open rather than a
 * redesign:** the left edge belongs to **priority** (it is the operational signal and it is on
 * every active card), and **unread moves to weight** — the descriptor at 700 — which
 * `components.md` section 1 already lists as part of the unread treatment ("2px border-focus left
 * inset **and** the descriptor at weight 700"). So nothing is invented; the half of the specified
 * treatment that collides is dropped and the half that does not is kept, plus an `sr-only`
 * "unread" so the signal is not weight-only for a screen reader. Flagged to the owner as F6's
 * answer rather than presented as settled design.
 */

/** Neutral VALUE ramp, never a hue (U10). Always accompanied by a text label — the bar alone is
 *  not sufficient signal (U30), which is what the `sr-only` priority word below is for. */
const PRIORITY_COLOR: Record<PriorityCode, string> = {
  CRITICAL: 'bg-priority-critical',
  HIGH: 'bg-priority-high',
  NORMAL: 'bg-priority-normal',
  LOW: 'bg-priority-low',
}

export function ThreadCard({ thread }: { thread: DriverThread }) {
  const { now } = useCountdownClock()

  return (
    <li>
      <Link
        to={`/driver/t/${thread.threadId}`}
        className={cn(
          'relative flex min-h-22 flex-col gap-2 overflow-hidden rounded-lg border p-4',
          'border-border bg-card',
          'active:bg-hover',
          'focus-visible:outline-2 focus-visible:outline-ring focus-visible:outline-offset-2',
          // Resolved cards keep their state chip -- a driver checking "what dock did I agree to
          // last Tuesday" is a real need and the card is the record. They lose the priority
          // marker and the countdown, and drop to 60%.
          thread.resolved && 'opacity-60',
        )}
      >
        {/* Priority marker: 3px, left edge, active threads only. */}
        {!thread.resolved && thread.priority ? (
          <span
            aria-hidden="true"
            className={cn(
              'absolute inset-y-0 left-0 w-[3px]',
              PRIORITY_COLOR[thread.priority],
            )}
          />
        ) : null}

        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            {/* Human descriptor, NEVER the shipment id (voice-and-tone.md's mechanics). The
                order reference sits beneath it in --font-data. min-w-0 + truncate because the
                descriptor is variable-length and the thread card's own preview line was one of
                the two places the web-design-guidelines pass flagged for missing min-w-0. */}
            <p
              className={cn(
                'truncate text-body-lg',
                thread.unread ? 'font-bold' : 'font-semibold',
              )}
            >
              {thread.descriptor}
              {thread.unread ? <span className="sr-only"> — unread</span> : null}
            </p>
            <p className="mt-0.5 truncate font-mono text-body text-muted-foreground">
              {thread.orderReference}
            </p>
          </div>
          <span className="shrink-0 text-body text-subtle-foreground">
            {formatMessageTimestamp(thread.lastActivityAt, now)}
          </span>
        </div>

        {/* `filled` variant, mandatory here -- the thread list is glanced at in sunlight. The
            chip carries its own countdown when HELD or PENDING (components.md section 2's
            mandate), which is why `expiresAt` is passed through rather than rendered separately:
            two renderings of one deadline is R4. */}
        {thread.promiseState ? (
          <PromiseChip
            state={thread.promiseState}
            expiresAt={thread.resolved ? undefined : thread.expiresAt}
          />
        ) : null}

        {/* Dock · dated range, always together, never a bare time. */}
        {thread.operationalLine ? (
          <p className="text-body text-foreground">{thread.operationalLine}</p>
        ) : null}

        {/* One line, truncated. `null` when the server has no message to preview -- rendered as
            absent rather than as an empty quotation, per U81. */}
        {thread.lastMessagePreview ? (
          <p className="truncate text-body text-muted-foreground">{thread.lastMessagePreview}</p>
        ) : null}

        {/* The bar alone is not sufficient signal (U30). Spoken, not drawn, because the visible
            label would compete with the descriptor for the one line a driver actually reads. */}
        {!thread.resolved && thread.priority ? (
          <span className="sr-only">{thread.priority.toLowerCase()} priority</span>
        ) : null}
      </Link>
    </li>
  )
}
