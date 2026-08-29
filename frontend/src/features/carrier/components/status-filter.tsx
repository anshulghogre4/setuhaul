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
 * ## Two options are missing, on purpose (issue #53)
 *
 * The design lists six: `All statuses · Shown · Held · Pending confirmation · Confirmed · Has
 * open exception`. `Shown` and `Held` are **omitted while `carrierShownHeldEnabled` is off**,
 * because `carrier_reads._validate_status_filter` answers **400 `FILTER_UNSUPPORTED`** for
 * either — the live `appointments.appointment_status` CHECK constraint has no such value, and
 * the endpoint refuses rather than returning a misleading empty list. Rendering the options
 * anyway would put two controls in front of a carrier that error on click.
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

const SHOWN_HELD_OPTIONS: Option[] = [
  { value: 'SHOWN', label: 'Shown' },
  { value: 'HELD', label: 'Held' },
]

function statusFilterOptions(shownHeldEnabled: boolean): Option[] {
  if (!shownHeldEnabled) return BASE_OPTIONS
  // Design order: All · Shown · Held · Pending confirmation · Confirmed · Has open exception.
  return [BASE_OPTIONS[0], ...SHOWN_HELD_OPTIONS, ...BASE_OPTIONS.slice(1)]
}

export function StatusFilter({
  value,
  onChange,
  shownHeldEnabled,
}: {
  value: StatusFilterValue
  onChange: (value: StatusFilterValue) => void
  shownHeldEnabled: boolean
}) {
  const options = statusFilterOptions(shownHeldEnabled)
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
