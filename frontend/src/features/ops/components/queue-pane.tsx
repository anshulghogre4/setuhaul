import { useEffect, useMemo, useRef, useState } from 'react'
import { CircleCheckBig, Inbox, OctagonAlert, SearchX, X } from 'lucide-react'

import { RESORT_KEY, RESORT_KEY_LABEL } from '@/shared/lib/live-poll'
import { Button } from '@/shared/ui/button'
import {
  DropdownMenu,
  DropdownMenuCheckboxItem,
  DropdownMenuContent,
  DropdownMenuTrigger,
} from '@/shared/ui/dropdown-menu'
import { EmptyState } from '@/shared/ui/empty-state'
import { Skeleton } from '@/shared/ui/skeleton'
import { REASON_META, REASON_ORDER } from '../lib/reasons'
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
 * Filter is client-side over the already-fetched page (reason + owner). Filtering narrows
 * membership only; it never changes the sort.
 *
 * **Live arrivals (issue #59), built 2026-08-31.** Prompt 3's "N new · press S" pill and U19's
 * frozen-while-focused sort are real: `ops-console.tsx` polls the existing escalation-queue read
 * and holds arrivals behind this pill whenever the pane has focus. Two things about it are
 * deliberate and easy to get wrong:
 *
 *  - **The pill's count and its announcement are separate elements.** The pill reads
 *    "2 new · press S"; the live region beside it says only "2 new escalations".
 *    `accessibility-behaviour.md` throttles this row to the count precisely because a spike is
 *    when it fires most, and reading "press S" aloud on every arrival is the distracting-stream
 *    case that row exists to prevent.
 *  - **The key is `S`, not the `R` prompt 3's copy names.** `R` is Reject on the planner queue
 *    (`03-planner-dock-board/accessibility.md`) and the two surfaces must not disagree about a
 *    single-key binding; see `shared/lib/live-poll.ts::RESORT_KEY` for the collision and the flag
 *    raised for the owner.
 */
export function QueuePane({
  state,
  items,
  selectedId,
  currentUserId = null,
  onSelect,
  onRetry,
  newCount = 0,
  onApplyArrivals = () => {},
  sortPinned = false,
  goneIds,
  raceOn = null,
  announceRace = false,
}: {
  state: LoadState
  items: EscalationQueueItem[]
  selectedId: string | null
  /** The signed-in coordinator, from `GET /auth/me`. `null` while it is still loading or if that
   *  read failed -- in which case "Owner: mine" degrades to "owned by anyone" and SAYS so, rather
   *  than silently showing a different set than its label promises. */
  currentUserId?: string | null
  onSelect: (item: EscalationQueueItem) => void
  onRetry: () => void
  /** Arrivals held behind the frozen sort -- prompt 3's "N new" (issue #59). */
  newCount?: number
  onApplyArrivals?: () => void
  /** Whether the order is currently held. Stated on screen, never merely true internally --
   *  a coordinator has to be able to tell a held order from a current one. */
  sortPinned?: boolean
  /** Rows still rendered that the server has stopped returning. Marked in place, never removed:
   *  `edge-cases.md` section 2's "the row updates in place ... never removed and re-inserted". */
  goneIds?: Set<string>
  /** `edge-cases.md` section 2 -- the escalation somebody else just claimed, and who won. */
  raceOn?: { escalationId: string; ownerName: string | null } | null
  /** Assertive vs silent for `raceOn`, decided by the console from whether this pane holds focus
   *  (`accessibility-behaviour.md`: assertive only for the row the user is focused on). */
  announceRace?: boolean
}) {
  const [ownerFilter, setOwnerFilter] = useState<OwnerFilter>('all')
  const [reasonFilter, setReasonFilter] = useState<EscalationReason | null>(null)
  const listRef = useRef<HTMLDivElement | null>(null)
  const paneRef = useRef<HTMLElement | null>(null)

  const filtered = useMemo(() => {
    return items.filter((i) => {
      if (reasonFilter && i.escalation_type !== reasonFilter) return false
      // "Mine" means owned by the signed-in coordinator. The previous implementation compared
      // against `null` -- i.e. "owned by anyone" -- which is a different question and quietly
      // showed other coordinators' work under a filter labelled "mine". With no identity yet,
      // fall back to that broader set rather than emptying the queue, and label it honestly
      // below.
      if (ownerFilter === 'mine') {
        return currentUserId === null ? i.owner_user_id !== null : i.owner_user_id === currentUserId
      }
      if (ownerFilter === 'unowned') return i.owner_user_id === null
      return true
    })
  }, [items, reasonFilter, ownerFilter, currentUserId])

  /**
   * `S` applies the held arrivals. Scoped to this pane by DOM containment rather than bound
   * globally: `accessibility.md` states that the planner's single-key row actions
   * (`C`/`R`/`O`/`H`/`E`) are deliberately NOT offered here, and a stray global letter key on a
   * three-pane console would fire while a coordinator is typing in the composer. The composer, the
   * filter and every other text field are excluded explicitly for the same reason.
   */
  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.metaKey || e.ctrlKey || e.altKey) return
      if (e.key.toLowerCase() !== RESORT_KEY) return
      const target = e.target as HTMLElement | null
      const tag = target?.tagName
      if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT' || target?.isContentEditable) return
      const pane = paneRef.current
      if (!pane || !pane.contains(target ?? null)) return
      e.preventDefault()
      onApplyArrivals()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onApplyArrivals])

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
      label:
        ownerFilter === 'mine' && currentUserId === null
          ? 'Owner: any (identity unavailable)'
          : `Owner: ${ownerFilter}`,
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
    <section
      ref={paneRef}
      aria-label="Escalation queue"
      role="region"
      className="flex h-full min-w-0 flex-col border-r border-border"
    >
      <div className="flex items-center justify-between gap-2 border-b border-border px-4 py-3">
        <h2 className="text-h3">Escalations ({filtered.length})</h2>

        {/* Prompt 3: right-aligned beside the count, a real button as well as a keyboard hint. */}
        {newCount > 0 ? (
          <button
            type="button"
            onClick={onApplyArrivals}
            className="ml-auto inline-flex items-center gap-1 rounded border border-info-border bg-info-bg px-2 py-0.5 text-supporting font-semibold tabular-nums text-info-fg focus-visible:outline-2 focus-visible:outline-ring focus-visible:outline-offset-2"
          >
            {newCount} new · press {RESORT_KEY_LABEL}
          </button>
        ) : null}

        {/* Polite, count only -- and rendered unconditionally so the live region is in the DOM
            before its text changes rather than appearing with content already in it. */}
        <span role="status" className="sr-only">
          {newCount > 0 ? `${newCount} new escalation${newCount === 1 ? '' : 's'}` : ''}
        </span>

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
            {/* `REASON_ORDER`, not `Object.keys(REASON_META)`. The lookup now also carries the two
                D12 backfill reasons so the queue cannot crash on them (`lib/reasons.ts`), but the
                *filter* stays §7.4's nine -- offering "Needs a dock reassigned" as a filter would
                present a backfill worklist as a peer of the escalation vocabulary. */}
            {REASON_ORDER.map((r) => (
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
        {sortPinned ? 'Sort pinned · ' : 'Sorted: '}unowned first, then time-to-breach ascending.
        {sortPinned ? ` Press ${RESORT_KEY_LABEL} to apply new arrivals.` : ''}
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
                  gone={goneIds?.has(item.escalation_id) ?? false}
                  stale={
                    raceOn && raceOn.escalationId === item.escalation_id
                      ? { winningOwnerName: raceOn.ownerName, announce: announceRace }
                      : null
                  }
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
