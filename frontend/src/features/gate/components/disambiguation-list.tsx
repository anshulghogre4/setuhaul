import { ChevronRight } from 'lucide-react'

import { cn } from '@/shared/lib/utils'
import { calendarDay, clockRange } from '../lib/format'
import { TOUCH_CLASS } from '../lib/touch'
import type { GateTruckMatch } from '../lib/types'

/**
 * Screen 5 -- Flow 1.4. A plate shared across trips is unlikely but possible.
 *
 * **A list of rows, explicitly not a dropdown.** A native picker is unusable with gloves.
 * `screens.md` section 2 says this outright, and the consequence is structural: every row is a
 * single tap target of at least 64px (`--row-h` at `spacious`) spanning the full card width, and
 * **the chevron is a direction cue that is never itself the target** -- gloved accuracy comes from
 * the row being large, not from hitting a small affordance. No radio buttons plus a Continue step
 * either: the row itself is the action.
 *
 * The focus indicator is drawn **inside** the row as an inset two-ring treatment, so a row sitting
 * flush against the card edge cannot clip it -- which an `outline` with a positive offset would.
 * This is the one control on the surface where the shared outline treatment is genuinely wrong.
 *
 * `<ul>`/`<li>` with a real `<button>` in each row rather than `role="listbox"`/`role="option"`:
 * the ops console adopted the listbox pattern for a queue the user navigates *within* (arrow keys,
 * a selected item that persists), and neither applies here -- this list exists for exactly one tap
 * and then ceases to exist. A listbox would promise keyboard semantics this surface has no shape
 * for.
 */
export function DisambiguationList({
  query,
  matches,
  onPick,
}: {
  /** Echoed in the heading so the officer can see what was actually matched -- a plate typed with
   *  a stray character matches nothing, and a heading that repeats it is how they notice. */
  query: string
  matches: GateTruckMatch[]
  onPick: (truck: GateTruckMatch) => void
}) {
  return (
    <div className="flex flex-col gap-4">
      <h2 className="text-h1 text-balance">
        {matches.length} trucks match <span translate="no">{query}</span>
      </h2>
      <p className="text-body-lg">Pick the right one.</p>
      <ul className="flex flex-col">
        {matches.map((truck, i) => (
          <li key={truck.shipment_id} className={cn(i > 0 && 'border-t border-border')}>
            <button
              type="button"
              onClick={() => onPick(truck)}
              className={cn(
                'flex w-full min-h-(--row-h) items-center gap-6 px-(--cell-px) py-(--cell-py) text-left',
                'text-foreground',
                TOUCH_CLASS,
                'transition-colors duration-(--d-fast) ease-(--e-out) hover:bg-hover active:bg-hover',
                'outline-none focus-visible:inset-ring-4 focus-visible:inset-ring-ring',
              )}
            >
              <span className="flex flex-1 flex-col gap-1">
                <span className="text-h2">
                  <span className="font-mono tabular-nums" translate="no">
                    {truck.shipment_id}
                  </span>{' '}
                  · {truck.driver_name}
                </span>
                <span className="text-body-lg">
                  {truck.carrier_name}
                  {truck.appointment_dock_code && truck.slot_start_ts && truck.slot_end_ts ? (
                    <>
                      {' · '}
                      <span className="font-mono tabular-nums" translate="no">
                        {truck.appointment_dock_code} ·{' '}
                        {calendarDay(truck.slot_start_ts)} ·{' '}
                        {clockRange(truck.slot_start_ts, truck.slot_end_ts)}
                      </span>
                    </>
                  ) : null}
                </span>
              </span>
              <ChevronRight className="size-6 shrink-0 text-muted-foreground" aria-hidden="true" />
            </button>
          </li>
        ))}
      </ul>
    </div>
  )
}
