import { CircleCheckBig, Inbox } from 'lucide-react'

import { EmptyState } from '@/shared/ui/empty-state'
import { Skeleton } from '@/shared/ui/skeleton'
import { cn } from '@/shared/lib/utils'

export type NotificationItem = {
  id: string
  /** "Escalation raised", "Slot confirmed", "Policy published". */
  title: string
  /** The mono identifier that follows the title -- ESC-4471, APT-1042, v12. */
  reference?: string
  /** Every operational time carries its dock AND its date.  A bare "13:00" is a wrong-day
   *  booking waiting to happen: option sets span days. */
  body: string
  /** Relative and short: "2m", "18m", "1h", "Tue". */
  timestamp: string
  unread: boolean
  href: string
}

/** The four panel states (artboards 15-18). */
export type NotificationsState = 'items' | 'loading' | 'caught-up' | 'nothing-yet'

/**
 * Artboards 15-18.  400px, max height 480 with the list scrolling inside.
 *
 * Its job is: what happened, when, and take me to it.  Nothing else.
 *
 * **Unread is carried by three channels, never colour alone**: a 6px dot, a weight-600
 * title, and an `aria-label` beginning "Unread".
 *
 * **No per-item buttons of any kind** -- no Confirm, no Dismiss, no Snooze, no overflow
 * menu, no hover-revealed actions.  The whole item is one link to the record.  And no
 * promise-state chips: a notification is a *historical event*, and a live chip here could
 * contradict the record it links to.
 *
 * **"Caught up" and "Nothing yet" are different states, and the difference is a server-side
 * history check -- never `count === 0`.**  The same visual emptiness means two opposite
 * things, and showing the wrong one makes a working system look broken (U74).  That is why
 * `state` is a prop rather than derived from `items.length` here.
 *
 * **"Mark all read" appears only when something is unread** -- a control with nothing to act
 * on is not a control.
 */
export function NotificationsPanel({
  state,
  items = [],
  onMarkAllRead,
}: {
  state: NotificationsState
  items?: NotificationItem[]
  onMarkAllRead?: () => void
}) {
  const hasUnread = items.some((i) => i.unread)

  return (
    <div className="w-full">
      <div className="flex items-center justify-between gap-2 px-4 py-3">
        <span className="text-h3">Notifications</span>
        {state === 'items' && hasUnread ? (
          <button
            type="button"
            onClick={onMarkAllRead}
            className="text-supporting text-link underline underline-offset-2 hover:text-primary-hover focus-visible:outline-2 focus-visible:outline-ring focus-visible:outline-offset-2"
          >
            Mark all read
          </button>
        ) : null}
      </div>
      <hr className="h-px border-0 bg-border" />

      {state === 'loading' ? <LoadingRows /> : null}

      {state === 'caught-up' ? (
        <EmptyState
          icon={CircleCheckBig}
          title="You’re all caught up."
          body="New notifications appear here automatically."
        />
      ) : null}

      {state === 'nothing-yet' ? (
        <EmptyState
          icon={Inbox}
          title="No notifications yet."
          body="You’ll see escalations, appointment changes and policy updates here."
        />
      ) : null}

      {state === 'items' ? (
        <div className="max-h-108 overflow-y-auto overscroll-contain">
          {items.map((n) => (
            <a
              key={n.id}
              href={n.href}
              aria-label={`${n.unread ? 'Unread. ' : ''}${n.title}${n.reference ? `, ${n.reference}` : ''}, ${n.timestamp}`}
              className="block w-full border-b border-border px-4 py-3 text-left transition-colors duration-(--d-fast) ease-(--e-out) hover:bg-hover focus-visible:outline-2 focus-visible:outline-ring focus-visible:-outline-offset-2"
            >
              <span className="flex items-baseline gap-2">
                <span
                  aria-hidden="true"
                  className={cn(
                    'size-1.5 shrink-0 self-center rounded-full',
                    n.unread ? 'bg-primary' : 'bg-transparent',
                  )}
                />
                <span
                  className={cn(
                    'min-w-0 flex-1 truncate text-body text-foreground',
                    n.unread && 'font-semibold',
                  )}
                >
                  {n.title}
                  {n.reference ? (
                    <>
                      {' · '}
                      <span className="font-mono" translate="no">
                        {n.reference}
                      </span>
                    </>
                  ) : null}
                </span>
                <span className="shrink-0 font-mono text-[11px] leading-[1.3] font-medium text-subtle-foreground">
                  {n.timestamp}
                </span>
              </span>
              <span className="mt-0.5 ml-3.5 line-clamp-2 block text-supporting text-muted-foreground">
                {n.body}
              </span>
            </a>
          ))}
        </div>
      ) : null}
    </div>
  )
}

/** Three skeleton rows shaped exactly like real items -- dot, title bar, body bar, timestamp
 *  bar.  Never a centred spinner: a spinner followed by content is a layout jump, and a jump
 *  under a cursor is a mis-click. */
function LoadingRows() {
  const widths = [
    ['w-[70%]', 'w-[55%]'],
    ['w-[40%]', 'w-[70%]'],
    ['w-[55%]', 'w-[40%]'],
  ] as const

  return (
    <div aria-busy="true">
      {widths.map(([title, body], i) => (
        <div key={i} className="border-b border-border px-4 py-3">
          <span className="flex items-baseline gap-2">
            <Skeleton className="size-1.5 shrink-0 self-center rounded-full" />
            <Skeleton className={cn('h-3.5 rounded-sm', title)} />
            <Skeleton className="ml-auto h-3 w-6 shrink-0 rounded-sm" />
          </span>
          <Skeleton className={cn('mt-2 ml-3.5 h-3 rounded-sm', body)} />
        </div>
      ))}
    </div>
  )
}
