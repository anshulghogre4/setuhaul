import { ChevronRight } from 'lucide-react'
import { Link } from 'react-router-dom'

import { cn } from '@/shared/lib/utils'
import { Skeleton } from '@/shared/ui/skeleton'
import { formatTime } from '../lib/format'
import { presentException } from '../lib/reasons'
import type { FleetExceptionItem } from '../lib/types'

/**
 * "Open exceptions" — `stitch-prompts.md` §4, `05-carrier-portal/components.md` §3.
 *
 * One line per open item, read left to right, middot-separated, with a leading reason icon and a
 * trailing chevron. **The row is neutral, not an alarm** — ordinary primary/secondary ink, no
 * red, no amber wash, no pulse, no badge counter. A carrier's open exception is a status; red
 * stays reserved for genuine danger, which is what keeps red meaningful elsewhere.
 *
 * ## The boundary this component protects
 *
 * No owner, no "assigned to", no avatar, no SLA countdown, no `OPEN → ACKNOWLEDGED →
 * IN_PROGRESS → RESOLVED` stepper, no priority label, no internal note, no activity feed. **The
 * carrier learns *that* it is being handled, never how** (§7.5.6, `components.md` §3). None of
 * those fields is even reachable from here — `repositories/carrier.list_open_exceptions` selects
 * a fixed seven-column projection and `resolved_by_user_id`, `severity_code`, `policy_version`
 * and `payload_json` are absent from it by design, so this is enforced at the query, not by a
 * client that remembers not to render them.
 *
 * No actions either: no Escalate, Chase, Nudge, Message operations, Add comment, Resolve,
 * Dismiss or Snooze. The whole row is one navigation target and it opens **the same** read-only
 * shipment detail a shipment row opens — this surface has exactly one detail destination,
 * reached two ways (`flows-and-states.md` Flow 4).
 *
 * A shipment appearing in both this list and the shipments table is normal and needs no
 * de-duplication (`edge-cases.md` #3): the two sections answer different questions.
 */

export function ExceptionsList({
  items,
  dimmed = false,
}: {
  items: FleetExceptionItem[]
  dimmed?: boolean
}) {
  return (
    <div
      className={cn('flex flex-col gap-3', dimmed && 'opacity-60')}
      aria-busy={dimmed || undefined}
    >
      {items.map((item) => {
        const { icon: Icon, clause, timePrefix } = presentException(item)
        const time = formatTime(item.occurred_at)
        const who = item.driver_name ? `${item.driver_name} · ` : ''

        return (
          <Link
            key={`${item.source}-${item.reference_id}`}
            to={`/carrier/shipments/${encodeURIComponent(item.shipment_id)}`}
            className="flex min-h-11 items-center gap-3 rounded-md border border-border bg-card px-(--cell-px) py-3 text-body text-foreground no-underline shadow-raised transition-colors duration-(--d-fast) ease-(--e-out) hover:bg-hover focus-visible:outline-2 focus-visible:outline-ring focus-visible:outline-offset-2"
          >
            <Icon className="size-4 shrink-0" aria-hidden="true" strokeWidth={2} />
            <span className="min-w-0 flex-1">
              <span className="font-mono font-semibold">{item.shipment_id}</span>
              {' · '}
              {who}
              {clause}
              {time ? (
                <>
                  {' — '}
                  {timePrefix}{' '}
                  <span className="font-mono tabular-nums" data-numeric>
                    {time}
                  </span>
                </>
              ) : null}
            </span>
            <ChevronRight
              className="size-4 shrink-0 text-subtle-foreground"
              aria-hidden="true"
              strokeWidth={2}
            />
          </Link>
        )
      })}
    </div>
  )
}

/** Two 44px skeleton rows, full width (`stitch-prompts.md` §5). */
export function ExceptionsListSkeleton() {
  return (
    <div className="flex flex-col gap-3" aria-hidden="true">
      {[340, 280].map((w) => (
        <div
          key={w}
          className="flex h-11 items-center rounded-md border border-border px-(--cell-px)"
        >
          <Skeleton className="h-3 rounded-sm" style={{ width: w }} />
        </div>
      ))}
    </div>
  )
}
