
import { Button } from '@/shared/ui/button'
import { Popover, PopoverContent, PopoverTrigger } from '@/shared/ui/popover'
import { sequencerProposalEnabled } from '../lib/flags'

/**
 * `screens.md` section 3 / state 21 (SS5.3-R23 in `implementation-spec.md`): *"`[ Review proposal
 * (N) ]` is Inactive (`components.md` foundations section 18) with `(0)` when no sequencer run is
 * pending."* Flow 9: it *"goes from Inactive-with-`(0)` to active the moment either origin produces
 * a `scheduling_run_id`"*.
 *
 * Inactive stays fully focusable and explains itself on activation, deliberately not a faded
 * Disabled control -- a planner needs to tell "no run pending" apart from "a run exists but I can't
 * act on it yet". That is why the `(0)` case below is a Popover rather than a `disabled` button,
 * and it is unchanged from this component's first version.
 *
 * ## The count had three states while no list endpoint existed. It now has two, and that is a fix
 *
 * This component previously carried a `count === null` branch meaning *"the server has no read that
 * can answer"* -- correct at the time, because SS7.5.3 defines propose / apply / get-by-id and no
 * list, so a run handed off from ops was undiscoverable here and rendering `(0)` would have told a
 * planner nothing was waiting when something was. `GET /api/v1/scheduling/runs` landed 2026-09-02
 * and closed that, so:
 *
 *  - `count > 0` -- a real, server-confirmed pending run. Active.
 *  - `count === 0` -- the server answered and there are none. Inactive with `(0)`, per the design.
 *
 * The unknown branch is **deleted rather than kept as a defensive fallback**: an unknown count was
 * only ever the honest answer while the server genuinely could not answer, and leaving it in would
 * be a state no code path can now produce.
 */
export function ReviewProposalButton({
  count = 0,
  onReview,
}: {
  /** Pending runs at this facility, as reported by `GET /api/v1/scheduling/runs`. */
  count?: number
  onReview?: () => void
}) {
  if (!sequencerProposalEnabled) {
    return (
      <Popover>
        <PopoverTrigger asChild>
          <Button variant="neutral">Review proposal (0)</Button>
        </PopoverTrigger>
        <PopoverContent role="dialog" aria-label="Why this isn't available">
          Not available yet. This delegates to section 7.5.3&rsquo;s Sequencer engine, which is
          entirely unbuilt (issue #49) — a proposal arrives either self-triggered here or handed off
          from the ops exception console&rsquo;s Flow 4, and neither path exists until it lands.
        </PopoverContent>
      </Popover>
    )
  }

  if (count === 0) {
    return (
      <Popover>
        <PopoverTrigger asChild>
          <Button variant="neutral">Review proposal (0)</Button>
        </PopoverTrigger>
        <PopoverContent role="dialog" aria-label="Why this isn't available">
          No sequencer run is pending for this facility right now. A proposal arrives either from
          &ldquo;Request re-sequence&rdquo; here, or handed off from the ops exception console when a
          coordinator triages a capacity incident.
        </PopoverContent>
      </Popover>
    )
  }

  return (
    <Button variant="constructive" onClick={onReview}>
      Review proposal ({count})
    </Button>
  )
}
