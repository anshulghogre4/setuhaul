import { Info } from 'lucide-react'

import { Button } from '@/shared/ui/button'
import { Popover, PopoverContent, PopoverTrigger } from '@/shared/ui/popover'
import { sequencerProposalEnabled } from '../lib/flags'

/**
 * The Board tab's **self-triggered** proposal origin -- `flows-and-states.md` Flow 9.
 *
 * ## This control is the design's own inference, and that is recorded rather than hidden
 *
 * Flow 9 says so in as many words: *"SS7.3 frames re-sequencing as available to the planner but
 * doesn't specify a dedicated trigger UI beyond 'review proposal' -- treated here as a small
 * 'Request re-sequence' action on the Board tab that calls `propose_facility_schedule` with
 * `trigger_reason='PLANNER_REQUESTED'`."* `screens.md` section 6 repeats the caveat. So this button
 * exists because Flow 9 specified it, while `screens.md` section 3's toolbar sketch shows only
 * `[ Block a dock ]` and `[ Review proposal (0) ]`. Built per Flow 9, and it is also the control
 * issue #102 recorded as `MISSING` on the 2026-09-01 sweep.
 *
 * ## `RUN_ALREADY_ACTIVE` is an inline state on this control, not a toast and not an error
 *
 * `edge-cases.md` section 4 is explicit: SS5.1's debounce rule (*"at most one active run per
 * facility, serialised"*) *"shows an inline state ... rather than a bare rejection, since this is an
 * expected, recoverable condition, not a failure"*, and `stitch-prompts.md` section 11 gives it the
 * info tone rather than the danger tone the two apply-refusals get. Hence `feedback-info` tokens,
 * `role="status"`, and **no retry affordance** -- retrying is the exact thing the debounce exists to
 * prevent, and a second press would only reproduce the message.
 */
export function RequestResequenceButton({
  busy = false,
  alreadyActiveRunId,
  runAlreadyActive = false,
  failure = null,
  onRequest,
  onReviewActive,
}: {
  busy?: boolean
  /** The in-flight run the server named, when it named one. */
  alreadyActiveRunId?: string | null
  runAlreadyActive?: boolean
  failure?: string | null
  onRequest?: () => void
  /** Offered only when the server actually named the active run: reviewing it is a genuine next
   *  step, unlike retrying. Absent when the id is unknown, rather than a button that would have to
   *  guess which run to open. */
  onReviewActive?: () => void
}) {
  if (!sequencerProposalEnabled) {
    return (
      <Popover>
        <PopoverTrigger asChild>
          <Button variant="neutral">Request re-sequence</Button>
        </PopoverTrigger>
        <PopoverContent role="dialog" aria-label="Why this isn't available">
          Not available yet. This calls section 7.5.3&rsquo;s{' '}
          <code>propose_facility_schedule</code>, which is unbuilt (issue #49). Flow 9 specifies this
          control as the planner-side trigger; section 7.3 itself does not, which is why the design
          flags it as its own inference.
        </PopoverContent>
      </Popover>
    )
  }

  if (runAlreadyActive) {
    return (
      <div className="flex items-center gap-2">
        <p
          role="status"
          className="flex items-start gap-2 rounded-md border border-info-border bg-info-bg px-3 py-1.5 text-supporting text-info-fg"
        >
          <Info className="mt-0.5 size-4 shrink-0" aria-hidden="true" />
          <span>
            A re-sequence is already running — you&rsquo;ll be notified when it&rsquo;s ready.
            {alreadyActiveRunId ? (
              <>
                {' '}
                Run <span className="font-data">{alreadyActiveRunId}</span>.
              </>
            ) : null}
          </span>
        </p>
        {alreadyActiveRunId && onReviewActive ? (
          <Button variant="neutral" onClick={onReviewActive}>
            Review it
          </Button>
        ) : null}
      </div>
    )
  }

  return (
    <div className="flex items-center gap-2">
      <Button
        variant="neutral"
        aria-disabled={busy}
        aria-busy={busy}
        className={busy ? 'opacity-50' : undefined}
        onClick={() => {
          if (busy) return
          onRequest?.()
        }}
      >
        {busy ? 'Requesting…' : 'Request re-sequence'}
      </Button>
      {failure === null ? null : (
        // A genuine failure, and visually distinct from the debounce state above on purpose:
        // one is expected and one is not, and `edge-cases.md` section 4 turns on them not reading
        // alike.
        <p
          role="alert"
          className="rounded-md border border-danger-border bg-danger-bg px-3 py-1.5 text-supporting text-danger-fg"
        >
          {failure}
        </p>
      )}
    </div>
  )
}
