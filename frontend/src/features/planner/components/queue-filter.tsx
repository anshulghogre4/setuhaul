import { Button } from '@/shared/ui/button'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuLabel,
  DropdownMenuRadioGroup,
  DropdownMenuRadioItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/shared/ui/dropdown-menu'
import {
  ETA_CONFIDENCE_CODES,
  PRIORITY_CODES,
  isQueueFilterActive,
  type EtaConfidenceCode,
  type PriorityCode,
  type QueueFilter,
} from '../lib/queue-filter'

/**
 * `screens.md` section 2's priority / ETA-confidence filter.
 *
 * ## Two radio groups, not a checkbox list -- and that is an ARIA decision, not a style one
 *
 * `features/ops`'s queue filter uses `menuitemcheckbox` because its axes are genuinely
 * multi-select-shaped (nine reasons, any of which could be toggled). Here each axis is
 * **single-select with an explicit "Any"**: a row has exactly one priority and at most one ETA
 * confidence, so "CRITICAL and HIGH" is a query this filter deliberately does not express (the
 * design's stated use is isolating *one* band for a focused pass). `radiogroup` with an `Any`
 * member is the role that says that, and it gives a keyboard user the arrow-key semantics they
 * expect within each axis for free.
 *
 * ## No chips here, deliberately
 *
 * The design says so and gives the reason -- at 15-35 rows the toolbar summary ("Filter: CRITICAL
 * · 6 shown") is enough, where ops's cross-facility view needed dismissible chips. `Clear` below is
 * the single reset, rendered only while something is active so it never sits inert next to an
 * unfiltered queue.
 */
export function QueueFilterControl({
  filter,
  onChange,
}: {
  filter: QueueFilter
  onChange: (next: QueueFilter) => void
}) {
  const active = isQueueFilterActive(filter)

  return (
    <div className="flex items-center gap-1">
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          {/* The accessible name states the axes, so a screen-reader user knows what this filters
              by before opening it -- "Filter" alone is what the ops pane can afford because its
              own chips restate the predicate afterwards. */}
          <Button variant="ghost" size="sm" aria-label="Filter by priority or ETA confidence">
            Filter
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="start">
          <DropdownMenuLabel>Priority</DropdownMenuLabel>
          <DropdownMenuRadioGroup
            value={filter.priority ?? 'ANY'}
            onValueChange={(value) =>
              onChange({
                ...filter,
                priority: value === 'ANY' ? null : (value as PriorityCode),
              })
            }
          >
            <DropdownMenuRadioItem value="ANY">Any priority</DropdownMenuRadioItem>
            {PRIORITY_CODES.map((code) => (
              <DropdownMenuRadioItem key={code} value={code}>
                {code}
              </DropdownMenuRadioItem>
            ))}
          </DropdownMenuRadioGroup>

          <DropdownMenuSeparator />

          <DropdownMenuLabel>ETA confidence</DropdownMenuLabel>
          <DropdownMenuRadioGroup
            value={filter.etaConfidence ?? 'ANY'}
            onValueChange={(value) =>
              onChange({
                ...filter,
                etaConfidence: value === 'ANY' ? null : (value as EtaConfidenceCode),
              })
            }
          >
            <DropdownMenuRadioItem value="ANY">Any confidence</DropdownMenuRadioItem>
            {ETA_CONFIDENCE_CODES.map((code) => (
              <DropdownMenuRadioItem key={code} value={code}>
                {code}
              </DropdownMenuRadioItem>
            ))}
          </DropdownMenuRadioGroup>
        </DropdownMenuContent>
      </DropdownMenu>

      {active ? (
        <Button variant="ghost" size="sm" onClick={() => onChange({ priority: null, etaConfidence: null })}>
          Clear
        </Button>
      ) : null}
    </div>
  )
}
