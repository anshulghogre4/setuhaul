import { Button } from '@/shared/ui/button'
import { Popover, PopoverContent, PopoverTrigger } from '@/shared/ui/popover'
import { sequencerProposalEnabled } from '../lib/flags'

/**
 * `screens.md` section 3 / state 21 (§5.3-R23 in `implementation-spec.md`): "`[ Review proposal
 * (N) ]` is Inactive (`components.md` foundations section 18) with `(0)` when no sequencer run is
 * pending." Mirrors `features/ops/components/capacity-incident-row.tsx`'s identical Inactive
 * treatment for the same underlying gap (issue #49) -- Inactive stays fully focusable and
 * explains itself on activation, deliberately not a faded Disabled control, since a planner needs
 * to tell "no run pending" apart from "a run exists but I can't act on it yet".
 */
export function ReviewProposalButton() {
  if (sequencerProposalEnabled) {
    // Real path lands with issue #49 -- not reachable today, kept as the documented shape this
    // branch will take.
    return <Button variant="constructive">Review proposal</Button>
  }
  return (
    <Popover>
      <PopoverTrigger asChild>
        <Button variant="neutral">Review proposal (0)</Button>
      </PopoverTrigger>
      <PopoverContent role="dialog" aria-label="Why this isn't available">
        Not available yet. This delegates to section 7.5.3's Sequencer engine, which is entirely
        unbuilt (issue #49) — a proposal arrives either self-triggered here or handed off from the
        ops exception console's Flow 4, and neither path exists until it lands.
      </PopoverContent>
    </Popover>
  )
}
