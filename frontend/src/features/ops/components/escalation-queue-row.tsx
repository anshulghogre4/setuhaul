import { cn } from '@/shared/lib/utils'
import { facilityDisplayName } from '../lib/facility-names'
import { REASON_META } from '../lib/reasons'
import { formatSlaRemaining, slaPosture } from '../lib/sla'
import type { EscalationQueueItem } from '../lib/types'

/**
 * `components.md` (this folder) section 1, `screens.md` section 2. Scoped variant of the shared
 * queue component (`00-foundations/components.md` section 19, U23).
 *
 * **Fork C, applied here rather than left unbuilt (implementation-spec.md section 6).**
 * `components.md` section 19 specifies the keyboard model (roving tabindex, j/k, Enter, Space)
 * but names no ARIA role for the row -- measured on the reference mockup at zero `role`,
 * `tabindex`, `aria-selected`. Shipping a real, keyboard-operated console with literally no row
 * semantics would be a worse outcome than picking one, so this build applies the spec's own
 * recommendation (a): `role="option"` inside the queue's `role="listbox"`
 * (`queue-pane.tsx`), matching "select one, detail follows" -- this surface's exact model, and
 * roving tabindex is the listbox's own native pattern. **Not yet written back to
 * `00-foundations/components.md` section 19** -- U23 says ops and planner share this component,
 * and `03-planner-dock-board/` does not exist yet to confirm this generalises, so the decision is
 * applied ops-only and flagged for the owner (Fork C) rather than silently promoted to the shared
 * foundations file.
 *
 * **The priority marker (`components.md` section 5, a 3px left edge) is not rendered.** Beyond
 * the mockup's own gap (Fork D item 1 -- it collides with the selection edge), `GET
 * /operations/escalation-queue` does not return a priority field on the queue item at all
 * (`escalation_service.py::get_exception_queue`'s SELECT has no `shipments.priority_code` join) --
 * so there is no data to render even once the collision question is answered. Not invented here.
 */
export function EscalationQueueRow({
  item,
  selected,
  stale,
  gone = false,
  onSelect,
}: {
  item: EscalationQueueItem
  selected: boolean
  /**
   * `edge-cases.md` section 2 -- another coordinator acted on this row while it was in view.
   *
   * `announce` is the politeness decision and it is the CALLER's, because it turns on whether the
   * coordinator is focused on this exact row: `accessibility-behaviour.md` makes that case
   * `assertive` by name ("a user about to act on a row that just changed underneath them must be
   * interrupted, not politely queued") and every other case silent. Rendering `role="alert"`
   * unconditionally -- which this component used to do -- would interrupt a coordinator over a row
   * they are not even looking at, which is the opposite of what the matrix asks for.
   */
  stale?: { winningOwnerName: string | null; announce?: boolean } | null
  /** The server has stopped returning this escalation but it is still on screen (it is the one the
   *  coordinator has open, or the sort is frozen). Marked in place; removed on the next re-sort. */
  gone?: boolean
  onSelect: () => void
}) {
  const reason = REASON_META[item.escalation_type]
  const Icon = reason.icon
  const posture = slaPosture(item.severity_code, item.sla_remaining_min)

  return (
    <div
      role="option"
      aria-selected={selected}
      tabIndex={selected ? 0 : -1}
      data-qrow=""
      data-row-id={item.escalation_id}
      onClick={onSelect}
      onKeyDown={(e) => {
        if (e.key === 'Enter') onSelect()
      }}
      className={cn(
        'flex cursor-pointer flex-col gap-1 border-b border-border px-4 py-3 outline-none',
        'hover:bg-hover focus-visible:outline-2 focus-visible:outline-ring focus-visible:-outline-offset-2',
        selected && 'bg-selected',
      )}
    >
      <div className="flex items-baseline justify-between gap-2">
        <span className="font-data text-body font-semibold tabular-nums">{item.escalation_id}</span>
        <span
          className={cn(
            'text-micro font-medium tracking-wide',
            item.owner_name === null ? 'text-warning-fg' : 'text-muted-foreground',
          )}
        >
          {item.owner_name ?? 'Unowned'}
        </span>
      </div>

      <span className="flex items-center gap-1.5 text-label tracking-wide text-muted-foreground uppercase">
        <Icon className="size-3.5" aria-hidden="true" />
        {reason.label}
      </span>

      <div className="flex items-baseline justify-between gap-2">
        <span className="text-body-lg text-muted-foreground">
          {item.shipment_id} · {facilityDisplayName(item.facility_id)}
        </span>
        <span
          className={cn(
            'font-data text-body tabular-nums',
            posture === 'ok' && 'text-muted-foreground',
            posture === 'warning' && 'text-sla-warning',
            posture === 'breach' && 'text-sla-breach font-semibold',
          )}
        >
          {formatSlaRemaining(item.sla_remaining_min)}
        </span>
      </div>

      {stale ? (
        <p
          role={stale.announce ? 'alert' : undefined}
          className="mt-1 rounded-md bg-warning-bg px-2 py-1 text-supporting text-warning-fg"
        >
          Already actioned{stale.winningOwnerName ? ` by ${stale.winningOwnerName}` : ''}.
        </p>
      ) : null}

      {gone && !stale ? (
        // Silent by construction: no live region. A row leaving the open queue while the
        // coordinator is looking elsewhere is the matrix's "row a user is not focused on
        // disappears" case, and it stays visible only so nothing moves under them.
        <p className="mt-1 rounded-md bg-warning-bg px-2 py-1 text-supporting text-warning-fg">
          No longer in the open queue. It clears when you re-sort.
        </p>
      ) : null}
    </div>
  )
}
