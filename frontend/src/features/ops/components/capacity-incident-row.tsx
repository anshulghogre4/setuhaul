import { useState } from 'react'
import { ChevronDown, ChevronRight, Network } from 'lucide-react'

import { Button } from '@/shared/ui/button'
import { Popover, PopoverContent, PopoverTrigger } from '@/shared/ui/popover'
import { sequencerProposalEnabled } from '../lib/flags'
import type { AffectedAppointment } from '../lib/types'

/**
 * `00-foundations/components.md` section 17 (U65) + `screens.md` section 5. One row per incident,
 * always -- the affected-count is part of the collapsed row's primary text.
 *
 * **"Request sequencer proposal" is gated behind `sequencerProposalEnabled` (issue #54, G1).** The
 * collapsed/expanded/scope-denied states all render regardless -- per the build's own suggested
 * order (implementation-spec.md section 7 item 9), only the action and its handoff state have
 * nothing to call.
 *
 * **No priority marker on the affected shipments.** `components.md` section 17 and `screens.md`
 * section 5 both show one; `payload.affected_appointments` (the only source, written by
 * `planner_service.py::_open_capacity_cascade`) does not carry `priority_code` even though the
 * query one function below it (`_affected_appointments`) reads it off `shipments` -- it is simply
 * never copied into the stored payload. Rendering a guessed priority here would be inventing data
 * this response does not have.
 */
export function CapacityIncidentRow({
  rowId: incidentEscalationId,
  dockLabel,
  affected,
  scopeDenied,
}: {
  /** The incident's own `escalation_id` -- lets the queue pane's roving-tabindex treat this row
   *  the same as an ordinary escalation row (Fork D item 3: one row, always). */
  rowId: string
  dockLabel: string
  affected: AffectedAppointment[]
  /** True when the incident belongs to a facility outside the caller's scope (U83: Hidden, not
   *  Disabled -- but this component still needs an honest state to demonstrate that rule). */
  scopeDenied?: boolean
}) {
  const [expanded, setExpanded] = useState(false)
  const panelId = `incident-panel-${incidentEscalationId}`

  if (scopeDenied) {
    return null // U83: scope-denied is Hidden, never rendered greyed-out.
  }

  return (
    <div className="border-b border-border">
      <button
        type="button"
        role="option"
        aria-selected={false}
        data-row-id={incidentEscalationId}
        aria-expanded={expanded}
        aria-controls={panelId}
        onClick={() => setExpanded((v) => !v)}
        className="flex w-full items-start gap-2 px-4 py-3 text-left hover:bg-hover focus-visible:outline-2 focus-visible:outline-ring focus-visible:-outline-offset-2"
      >
        {expanded ? (
          <ChevronDown className="mt-0.5 size-4 shrink-0 text-muted-foreground" aria-hidden="true" />
        ) : (
          <ChevronRight className="mt-0.5 size-4 shrink-0 text-muted-foreground" aria-hidden="true" />
        )}
        <Network className="mt-0.5 size-4 shrink-0 text-muted-foreground" aria-hidden="true" />
        <span className="flex min-w-0 flex-1 flex-col gap-0.5">
          <span className="text-body font-medium">Capacity incident · {dockLabel}</span>
          <span className="text-supporting text-muted-foreground" aria-live="polite">
            {affected.length} shipment{affected.length === 1 ? '' : 's'} affected
          </span>
        </span>
      </button>

      {expanded ? (
        <div id={panelId} className="flex flex-col gap-2 px-4 pb-3 pl-10">
          <ul className="flex flex-col gap-1">
            {affected.map((a) => (
              <li
                key={a.appointment_id}
                className="font-data flex items-center justify-between gap-2 rounded-md bg-sunken px-2 py-1.5 text-supporting tabular-nums"
              >
                <span>{a.shipment_id}</span>
                <span className="text-muted-foreground">{a.appointment_status}</span>
              </li>
            ))}
          </ul>

          {sequencerProposalEnabled ? (
            <Button variant="constructive" size="sm">
              Request sequencer proposal
            </Button>
          ) : (
            // Inactive, not Disabled (components.md foundations section 18): fully focusable,
            // explains itself on activation rather than doing nothing.
            <Popover>
              <PopoverTrigger asChild>
                <Button variant="neutral" size="sm">
                  Request sequencer proposal
                </Button>
              </PopoverTrigger>
              <PopoverContent role="dialog" aria-label="Why this isn't available">
                Not available yet. This delegates to section 7.5.3's Sequencer engine, which is
                entirely unbuilt (issue #49) — tracked for this console specifically as issue #54.
              </PopoverContent>
            </Popover>
          )}
        </div>
      ) : null}
    </div>
  )
}
