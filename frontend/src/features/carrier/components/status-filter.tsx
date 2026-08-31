import { ChevronDown } from 'lucide-react'

import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuRadioGroup,
  DropdownMenuRadioItem,
  DropdownMenuTrigger,
} from '@/shared/ui/dropdown-menu'

/**
 * The status filter — `stitch-prompts.md` §3 state (b), `flows-and-states.md` Flow 2.
 *
 * Single-select, membership-only. **Selecting a value filters the table and nothing else**: the
 * three stat tiles describe the whole fleet regardless of the filter, because they answer "what
 * is my fleet doing" and the list answers "which of them match this". `get_fleet_overview` is
 * deliberately not re-called on a filter change.
 *
 * **Focus stays on the trigger after a selection** and does not jump into the results — the
 * product-wide rule in `accessibility-behaviour.md`'s focus-management contract. That is Radix's
 * own documented default for `DropdownMenu` (focus returns to the trigger on close), so it is
 * inherited rather than re-implemented; nothing here overrides it.
 *
 * ## Five options, not the design's six — and the missing one is a design question (2026-08-31)
 *
 * The design lists six: `All statuses · Shown · Held · Pending confirmation · Confirmed · Has open
 * exception`.
 *
 * **`Held` ships** behind `carrierHeldEnabled`: issue #87 made
 * `carrier_reads._validate_status_filter` answer it against the derived `promise_state` whenever the
 * server's own `TWO_PHASE_HOLD_ENABLED` is on, and refuse it *with a stated reason* when it is off.
 * The flag exists so this popover and that server flag cannot disagree about whether the option is
 * clickable.
 *
 * **`Shown` is removed outright, not flagged.** `carrier_reads` refuses it in every flag state, by
 * argued decision: §0.8/§4 make `SHOWN` a presentation-only state with no persisted counterpart
 * anywhere in the product, so there is nothing to select on. A flag would imply a pending
 * engineering task; what it actually needs is an owner decision about whether the state belongs in
 * a carrier's status vocabulary at all (recorded in `lib/flags.ts`). Shipping it as an option that
 * 400s on click would be the one thing worse than omitting it.
 *
 * Omitted, not disabled: `components.md` §18 requires an unavailable control to be **Hidden**,
 * never greyed out.
 */

export type StatusFilterValue = string | null

const ALL = '__all__'

type Option = { value: string; label: string }

const BASE_OPTIONS: Option[] = [
  { value: ALL, label: 'All statuses' },
  { value: 'PENDING_CONFIRMATION', label: 'Pending confirmation' },
  { value: 'CONFIRMED', label: 'Confirmed' },
  { value: 'HAS_OPEN_EXCEPTION', label: 'Has open exception' },
]

const HELD_OPTION: Option = { value: 'HELD', label: 'Held' }

function statusFilterOptions(heldEnabled: boolean): Option[] {
  if (!heldEnabled) return BASE_OPTIONS
  // Design order minus `Shown`: All · Held · Pending confirmation · Confirmed · Has open exception.
  return [BASE_OPTIONS[0], HELD_OPTION, ...BASE_OPTIONS.slice(1)]
}

export function StatusFilter({
  value,
  onChange,
  heldEnabled,
}: {
  value: StatusFilterValue
  onChange: (value: StatusFilterValue) => void
  heldEnabled: boolean
}) {
  const options = statusFilterOptions(heldEnabled)
  const current = options.find((o) => o.value === (value ?? ALL)) ?? options[0]

  return (
    <DropdownMenu>
      <DropdownMenuTrigger
        className="inline-flex min-h-11 items-center gap-1.5 rounded-sm border border-input px-3 text-label font-semibold tracking-normal text-muted-foreground outline-none transition-colors duration-(--d-fast) ease-(--e-out) hover:bg-hover focus-visible:outline-2 focus-visible:outline-ring focus-visible:outline-offset-2"
        aria-label={`Filter shipments by status. Currently ${current.label}.`}
      >
        Filter: {current.label}
        <ChevronDown className="size-3.5" aria-hidden="true" strokeWidth={2} />
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="min-w-55">
        <DropdownMenuRadioGroup
          value={value ?? ALL}
          onValueChange={(next) => onChange(next === ALL ? null : next)}
        >
          {options.map((o) => (
            /* 44px items -- `comfortable` density's tap-target floor, which the design's own fix
               pass raised the mockup's 40px rows to. */
            <DropdownMenuRadioItem key={o.value} value={o.value} className="h-11 text-body">
              {o.label}
            </DropdownMenuRadioItem>
          ))}
        </DropdownMenuRadioGroup>
      </DropdownMenuContent>
    </DropdownMenu>
  )
}
