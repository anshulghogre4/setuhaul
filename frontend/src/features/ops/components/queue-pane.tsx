import { useMemo, useRef, useState } from 'react'
import { CircleCheckBig, Inbox, OctagonAlert, SearchX, X } from 'lucide-react'

import { Button } from '@/shared/ui/button'
import {
  DropdownMenu,
  DropdownMenuCheckboxItem,
  DropdownMenuContent,
  DropdownMenuTrigger,
} from '@/shared/ui/dropdown-menu'
import { EmptyState } from '@/shared/ui/empty-state'
import { Skeleton } from '@/shared/ui/skeleton'
import { REASON_META } from '../lib/reasons'
import type { EscalationQueueItem, EscalationReason, OwnerFilter } from '../lib/types'
import { CapacityIncidentRow } from './capacity-incident-row'
import { EscalationQueueRow } from './escalation-queue-row'

type LoadState = 'loading' | 'error' | 'ready'

/**
 * `screens.md` section 2, prompts 2/4/5/6, `components.md` (this folder) section 1.
 *
 * **U95's sort is applied server-side already** (`escalation_service.py::get_exception_queue`:
 * `(owner_user_id is not None, sla_remaining_min)`) -- this pane renders `items` in the order the
 * API returns them and does not re-sort client-side, so there is exactly one sort implementation
 * to keep correct, not two that could drift.
 *
 * **Sort indicator (Fork D item 2), applied**: a small caption states the rule, since
 * `checklist-design`'s Data Table audit found nothing on the reference mockup states it at all.
 *
 * Filter is client-side over the already-fetched page (reason + owner). U95's frozen-while-
 * focused sort and the live "N new · press R" pill (prompt 3) are **not built** -- there is no
 * live-update transport (issue #59, G6) to accumulate arrivals behind in the first place; this
 * pane is a snapshot refreshed by an explicit action, never claims to be live.
 */
export function QueuePane({
  state,
  items,
  selectedId,
  onSelect,
  onRetry,
}: {
  state: LoadState
  items: EscalationQueueItem[]
  selectedId: string | null
  onSelect: (item: EscalationQueueItem) => void
  onRetry: () => void
}) {
  const [ownerFilter, setOwnerFilter] = useState<OwnerFilter>('all')
  const [reasonFilter, setReasonFilter] = useState<EscalationReason | null>(null)
  const listRef = useRef<HTMLDivElement | null>(null)

  const filtered = useMemo(() => {
    return items.filter((i) => {
      if (reasonFilter && i.escalation_type !== reasonFilter) return false
      if (ownerFilter === 'mine') return i.owner_user_id !== null // caller identity check happens server-side too
      if (ownerFilter === 'unowned') return i.owner_user_id === null
      return true
    })
  }, [items, reasonFilter, ownerFilter])

  const hasHistory = true // no "unprovisioned facility" signal exists yet; see queue empty state below.

  const activeChips: { key: string; label: string; onDismiss: () => void }[] = []
  if (reasonFilter) {
    activeChips.push({
      key: 'reason',
      label: `Reason: ${REASON_META[reasonFilter].label}`,
      onDismiss: () => setReasonFilter(null),
    })
  }
  if (ownerFilter !== 'all') {
    activeChips.push({
      key: 'owner',
      label: `Owner: ${ownerFilter}`,
      onDismiss: () => setOwnerFilter('all'),
    })
  }

  /** Roving tabindex, `components.md` foundations section 19. Moves FOCUS only -- selection is a
   *  separate, explicit `Enter` (`accessibility.md`'s keyboard model for this surface), so a
   *  coordinator can arrow through the queue without opening a different row into the detail
   *  pane on every keystroke. */
  function moveFocus(fromId: string | null, dir: 1 | -1) {
    const ids = filtered.map((i) => i.escalation_id)
    const idx = fromId ? ids.indexOf(fromId) : -1
    const next = ids[Math.min(ids.length - 1, Math.max(0, idx + dir))]
    if (!next) return
    const el = listRef.current?.querySelector<HTMLElement>(`[data-row-id="${CSS.escape(next)}"]`)
    el?.focus()
  }

  return (
    <section aria-label="Escalation queue" role="region" className="flex h-full min-w-0 flex-col border-r border-border">
      <div className="flex items-center justify-between gap-2 border-b border-border px-4 py-3">
        <h2 className="text-h3">Escalations ({filtered.length})</h2>
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button variant="ghost" size="sm">
              Filter
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end">
            <DropdownMenuCheckboxItem
              checked={ownerFilter === 'mine'}
              onCheckedChange={(c) => setOwnerFilter(c ? 'mine' : 'all')}
            >
              Owner: mine
            </DropdownMenuCheckboxItem>
            <DropdownMenuCheckboxItem
              checked={ownerFilter === 'unowned'}
              onCheckedChange={(c) => setOwnerFilter(c ? 'unowned' : 'all')}
            >
              Owner: unowned
            </DropdownMenuCheckboxItem>
            {(Object.keys(REASON_META) as EscalationReason[]).map((r) => (
              <DropdownMenuCheckboxItem
                key={r}
                checked={reasonFilter === r}
                onCheckedChange={(c) => setReasonFilter(c ? r : null)}
              >
                {REASON_META[r].label}
              </DropdownMenuCheckboxItem>
            ))}
          </DropdownMenuContent>
        </DropdownMenu>
      </div>

      {activeChips.length > 0 ? (
        <div className="flex flex-wrap items-center gap-2 border-b border-border px-4 py-2">
          {activeChips.map((chip) => (
            <button
              key={chip.key}
              type="button"
              onClick={chip.onDismiss}
              className="flex items-center gap-1 rounded-full border border-input bg-card px-2 py-1 text-supporting hover:bg-hover"
            >
              {chip.label}
              <X className="size-3" aria-hidden="true" />
            </button>
          ))}
          <button
            type="button"
            onClick={() => {
              setReasonFilter(null)
              setOwnerFilter('all')
            }}
            className="text-supporting text-link hover:underline"
          >
            Clear all
          </button>
        </div>
      ) : null}

      <p className="border-b border-border px-4 py-1.5 text-micro text-muted-foreground">
        Sorted: unowned first, then time-to-breach ascending.
      </p>

      <div
        ref={listRef}
        role="listbox"
        aria-label="Escalations"
        className="min-h-0 flex-1 overflow-auto"
        onKeyDown={(e) => {
          if (e.key === 'j' || e.key === 'ArrowDown') {
            e.preventDefault()
            moveFocus(selectedId, 1)
          } else if (e.key === 'k' || e.key === 'ArrowUp') {
            e.preventDefault()
            moveFocus(selectedId, -1)
          }
        }}
      >
        {state === 'loading' ? <QueueSkeleton /> : null}

        {state === 'error' ? (
          <div role="alert">
            <EmptyState
              icon={OctagonAlert}
              title="Couldn't load escalations — usually a connection problem."
              actions={
                <Button variant="constructive" onClick={onRetry}>
                  Retry
                </Button>
              }
            />
          </div>
        ) : null}

        {state === 'ready' && filtered.length === 0 && items.length > 0 ? (
          <EmptyState icon={SearchX} title="No escalations match this filter." />
        ) : null}

        {state === 'ready' && items.length === 0 && hasHistory ? (
          <EmptyState
            icon={CircleCheckBig}
            title="No open escalations."
            body="New ones appear here automatically."
          />
        ) : null}

        {state === 'ready' && items.length === 0 && !hasHistory ? (
          <EmptyState
            icon={Inbox}
            title="This facility has no escalations recorded yet."
            body="Once one is raised, it will show up here."
          />
        ) : null}

        {state === 'ready'
          ? filtered.map((item) =>
              item.escalation_type === 'CAPACITY_EVENT_CASCADE' ? (
                <CapacityIncidentRow
                  key={item.escalation_id}
                  rowId={item.escalation_id}
                  dockLabel={String((item.payload as { dock_id?: string }).dock_id ?? item.shipment_id)}
                  affected={item.affected_shipments ?? []}
                />
              ) : (
                <EscalationQueueRow
                  key={item.escalation_id}
                  item={item}
                  selected={item.escalation_id === selectedId}
                  onSelect={() => onSelect(item)}
                />
              ),
            )
          : null}
      </div>
    </section>
  )
}

/** Prompt 4 -- skeleton rows matching final row height, `aria-busy`, shell never unmounts. */
function QueueSkeleton() {
  return (
    <div aria-busy="true" aria-label="Loading escalations" className="flex flex-col gap-0 p-4">
      {Array.from({ length: 5 }).map((_, i) => (
        <div key={i} className="flex flex-col gap-2 border-b border-border py-3">
          <Skeleton className="h-4 w-24" />
          <Skeleton className="h-3 w-32" />
          <Skeleton className="h-4 w-48" />
        </div>
      ))}
    </div>
  )
}
