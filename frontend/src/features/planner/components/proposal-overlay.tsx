import { CalendarX, Info, OctagonAlert, TriangleAlert } from 'lucide-react'
import { useCallback, useEffect, useState } from 'react'

import { Button } from '@/shared/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/shared/ui/dialog'
import { Skeleton } from '@/shared/ui/skeleton'
import { formatUserFriendlyError } from '@/core/http/api'
import { applyScheduleProposal, fetchDockBoard, fetchSchedulingRun } from '../lib/api'
import { formatDate, formatTime } from '../lib/format'
import type {
  ApplyProposalResult,
  DockBoard,
  ProposalPlacement,
  SchedulingRun,
} from '../lib/types'
import { BoardPlate } from './dock-board'

/**
 * States 19-21 -- the sequencer proposal diff overlay.
 *
 * `screens.md` section 6 (U104) · `components.md` section 7 · `stitch-prompts.md` section 11 ·
 * `flows-and-states.md` Flow 9 · `edge-cases.md` sections 4-5 · SOLUTION_DESIGN.md SS5.1 and
 * SS7.5.3. FR-PLN-009.
 *
 * ## The three rules that are structural here, not stylistic
 *
 * 1. **No partial apply, anywhere, in any form.** SS7.5.3 omits the argument on purpose (*"cherry-
 *    picking produces a schedule nobody validated"*), `components.md` section 7 turns that into a UI
 *    rule (*"the UI does not offer a control the tool doesn't support"*), and `stitch-prompts.md`
 *    section 11 names the specific forbidden controls (*"no per-shipment checkbox, no 'apply these
 *    three' partial selection"*). So the change lists in this file are `<ul>`/`<li>` **static
 *    rows** -- no checkbox, no per-row button, no selection state exists to wire one to. That is
 *    also why `PARTIALLY_INFEASIBLE` below offers no "apply what's still valid" escape: *"none
 *    exists."*
 * 2. **SS5.1's four words, verbatim.** unchanged / moved / newly placed / unplaceable. Not
 *    "rescheduled", not "added", not "failed" -- the prompt bans those three by name.
 * 3. **An unplaceable shipment is never a bar.** It lists below the board, because *"a gap is a
 *    gap, never a zero-width bar pretending to be a real placement"*. Enforced upstream too: the
 *    board's delta grouping skips any change with no proposed dock.
 *
 * ## What this overlay reads, and why it reads the board again
 *
 * Two reads, both real: `get_scheduling_run` for the proposal, and `GET /planner/board` for the
 * schedule it is proposed *against*. The design's whole framing is a **before/after diff drawn on
 * the dock board itself**, so the "before" has to be the real committed board rather than a
 * reconstruction from the run's own `unchanged` list -- which would silently omit anything the run
 * did not consider (a blocked dock, an in-progress unload outside the job set) and quietly
 * misrepresent the very capacity the planner is deciding about.
 *
 * The board's horizon and the run's horizon come from the **same server-side helper** (the shipped
 * migration's `horizon_end_reason` comment says so outright: *"the board and the proposal must not
 * disagree about where the axis ends"*), so the delta lands on the axis it was computed against.
 * When they do diverge -- a run reviewed after its horizon has rolled -- that is stated rather than
 * drawn over.
 */
export function ProposalOverlay({
  schedulingRunId,
  facilityId,
  open,
  onOpenChange,
  onApplied,
  onRequestFresh,
}: {
  schedulingRunId: string
  facilityId: string | null
  open: boolean
  onOpenChange: (open: boolean) => void
  /** Flow 9 step 3: the board reflects the new committed schedule. The console owns the board's
   *  reload token, so applying reports upward rather than refetching a board it does not own. */
  onApplied: (result: ApplyProposalResult) => void
  /** `edge-cases.md` section 5: drift's fix is *a fresh proposal, not forcing the stale one
   *  through*. The console owns the propose call, so the overlay asks rather than calls -- which is
   *  also what makes "never a blind retry" true by construction here. */
  onRequestFresh: () => void
}) {
  const [run, setRun] = useState<SchedulingRun | null>(null)
  const [board, setBoard] = useState<DockBoard | null>(null)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [applying, setApplying] = useState(false)
  const [outcome, setOutcome] = useState<ApplyProposalResult | null>(null)
  const [applyError, setApplyError] = useState<string | null>(null)
  /**
   * One `Idempotency-Key` per apply INTENT, reused across retries of that intent.
   *
   * Minting it inside the call would defeat the header entirely: an apply whose response was lost
   * in flight and then retried would be a *second* all-or-nothing application of a schedule, which
   * is the one write on this surface that moves other people's promises. Same rule
   * `policy-tab.tsx` follows for publish and `queue-tab.tsx` for confirm.
   */
  const [applyKey, setApplyKey] = useState<string | null>(null)

  useEffect(() => {
    if (!open) return
    let cancelled = false
    setLoadError(null)
    setRun(null)
    setBoard(null)
    void (async () => {
      try {
        // Both reads in parallel: they are independent, and serialising them would double the
        // time the overlay spends in its skeleton for no ordering benefit.
        const [runResult, boardResult] = await Promise.all([
          fetchSchedulingRun(schedulingRunId),
          fetchDockBoard(facilityId),
        ])
        if (cancelled) return
        setRun(runResult)
        setBoard(boardResult)
      } catch (error) {
        if (!cancelled) setLoadError(formatUserFriendlyError(error))
      }
    })()
    return () => {
      cancelled = true
    }
  }, [open, schedulingRunId, facilityId])

  const onApply = useCallback(async () => {
    if (run === null || applying) return
    const key = applyKey ?? crypto.randomUUID()
    setApplyKey(key)
    setApplying(true)
    setApplyError(null)
    try {
      const result = await applyScheduleProposal({
        schedulingRunId: run.scheduling_run_id,
        // Verbatim from the run this planner actually reviewed. Never recomputed -- a recomputed
        // digest would either misrepresent what was on screen or accidentally match and defeat the
        // guard, which is the same rule every other write on this surface follows.
        snapshotHash: run.snapshot_hash,
        idempotencyKey: key,
      })
      setOutcome(result)
      if (result.code === 'APPLIED') {
        setApplyKey(null)
        onApplied(result)
      }
      // On a refusal the key is deliberately KEPT: neither refusal wrote anything, so a later
      // press against the same run and hash is the same intent, not a new one.
    } catch (error) {
      setApplyError(formatUserFriendlyError(error))
    } finally {
      setApplying(false)
    }
  }, [run, applying, applyKey, onApplied])

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      {/* Wider than the shared default: this is a full-width board overlay, not a form dialog
          (`stitch-prompts.md` section 11's "full-width overlay above the board region"). Escape
          exits without applying -- Radix's own default, and the prompt requires exactly it. */}
      <DialogContent className="max-h-[90vh] overflow-auto sm:max-w-[min(96vw,72rem)]">
        <DialogHeader>
          <DialogTitle>Schedule proposal</DialogTitle>
          <DialogDescription>
            {run === null
              ? 'Loading the proposal and the schedule it is proposed against.'
              : describeOrigin(run)}
          </DialogDescription>
        </DialogHeader>

        {loadError !== null ? (
          <p
            role="alert"
            className="rounded-md border border-danger-border bg-danger-bg px-3 py-2 text-supporting text-danger-fg"
          >
            {loadError}
          </p>
        ) : run === null || board === null ? (
          <ProposalSkeleton />
        ) : (
          <>
            <ProposalHeader run={run} />

            {/* The board, drawn by the SAME component the live Board tab uses -- the current
                schedule beneath, the proposal delta outlined above it. A second board built for
                this overlay would certify markup the planner never otherwise sees. */}
            <BoardPlate board={board} proposal={proposalDeltas(run)} />

            <ProposalReviewBody run={run} />

            {applyError !== null ? (
              <p
                role="alert"
                className="rounded-md border border-danger-border bg-danger-bg px-3 py-2 text-supporting text-danger-fg"
              >
                {applyError}
              </p>
            ) : null}

            {outcome === null ? (
              <ApplyBar
                run={run}
                applying={applying}
                onApply={() => void onApply()}
                onClose={() => onOpenChange(false)}
              />
            ) : outcome.code === 'APPLIED' ? (
              <AppliedNotice result={outcome} onClose={() => onOpenChange(false)} />
            ) : outcome.code === 'SNAPSHOT_DRIFT' ? (
              <SnapshotDrift
                result={outcome}
                onRequestFresh={() => {
                  onOpenChange(false)
                  onRequestFresh()
                }}
              />
            ) : (
              <PartiallyInfeasible result={outcome} onClose={() => onOpenChange(false)} />
            )}
          </>
        )}
      </DialogContent>
    </Dialog>
  )
}

/**
 * Everything the review reads below the board: the summary line, the objective, the moved list, the
 * unplaceable list and the run's own explanation.
 *
 * **Exported so `/planner/_states` mounts exactly this, not a look-alike.** The gallery's whole
 * value is that "it type-checks" is not "it has been seen rendering", which only holds if the plate
 * mounts the same component the route does -- the same argument `BoardPlate`'s own header makes.
 * It renders nothing interactive, so a plate mounting it still cannot write.
 */
export function ProposalReviewBody({ run }: { run: SchedulingRun }) {
  return (
    <>
      <SummaryLine run={run} />
      <ObjectiveLine run={run} />
      <MovedList run={run} />
      <UnplaceableList run={run} />
      {run.explanation ? (
        // SS5.1's own "Effect: ..." line, persisted with the run so it is replayable. Rendered
        // verbatim: paraphrasing the run's own explanation would make the replay and the review
        // disagree about what the sequencer did.
        <p className="text-supporting text-muted-foreground">{run.explanation}</p>
      ) : null}
    </>
  )
}

/**
 * Every change that has a place on the board -- moved and newly placed.
 *
 * `unchanged` is deliberately excluded: those appointments are **already drawn** by the board's own
 * committed bars, and outlining them too would say the sequencer proposes to move something it
 * proposes to leave alone. `unplaceable` is excluded because it has no interval at all.
 */
function proposalDeltas(run: SchedulingRun): ProposalPlacement[] {
  return [...run.diff.moved, ...run.diff.newly_placed]
}

/**
 * `stitch-prompts.md` section 11: *"Header metadata is mandatory: the run ID (mono), the origin ...
 * and the board's date. A proposal with no traceable origin is not reviewable."*
 *
 * The policy version is added beyond the artboard, and deliberately: SS5.1 says `P_churn` *"lives in
 * `policy_versions` ... and is stamped on every run"*, and SS8 requires "which policy produced
 * this" to be answerable later. A proposal whose objective numbers cannot be tied to the weights
 * that produced them is exactly as untraceable as one with no origin.
 */
function ProposalHeader({ run }: { run: SchedulingRun }) {
  return (
    <div className="flex flex-wrap items-baseline gap-x-4 gap-y-1 border-b border-border pb-2 text-supporting text-muted-foreground">
      <span>
        Run <span className="font-data text-foreground">{run.scheduling_run_id}</span>
      </span>
      <span>{describeOrigin(run)}</span>
      <span>
        {run.facility_name ?? run.facility_id} · {formatDate(run.horizon.start_ts)} ·{' '}
        {formatTime(run.horizon.start_ts)}–{formatTime(run.horizon.end_ts)}{' '}
        <span className="text-subtle-foreground">
          {run.horizon.end_reason === 'FACILITY_CLOSE' ? '(to closing time)' : '(next four hours)'}
        </span>
      </span>
      {run.policy_version ? (
        <span>
          Policy <span className="font-data">{run.policy_version}</span>
        </span>
      ) : null}
    </div>
  )
}

/** The prompt's two permitted origin sentences, and nothing invented for a third value. */
function describeOrigin(run: SchedulingRun): string {
  if (run.trigger_reason === 'CAPACITY_INCIDENT') return 'Requested from Ops (capacity incident)'
  if (run.trigger_reason === 'PLANNER_REQUESTED') return 'Requested by you'
  // An origin this client has not heard of renders as itself. Guessing which of the two sentences
  // applies would attribute the run to a surface that may not have asked for it.
  return `Trigger: ${run.trigger_reason}`
}

/**
 * `screens.md` section 6's summary line, in SS5.1's own vocabulary and order.
 *
 * Reads the **server's** `counts` map rather than the array lengths: the arrays may legitimately be
 * truncated on a large facility, and the summary is a statement about the *run*, not about how many
 * rows this response happened to carry. Falls back to the array length per category when the server
 * omits a key, so a partial `counts` degrades per-number rather than blanking the line.
 *
 * The total is the sum of the four categories rather than a separate field, so the line cannot claim
 * a shipment total that disagrees with its own breakdown.
 */
function SummaryLine({ run }: { run: SchedulingRun }) {
  const c = {
    unchanged: run.counts.unchanged ?? run.diff.unchanged.length,
    moved: run.counts.moved ?? run.diff.moved.length,
    newly_placed: run.counts.newly_placed ?? run.diff.newly_placed.length,
    unplaceable: run.counts.unplaceable ?? run.diff.unplaceable.length,
  }
  const total = c.unchanged + c.moved + c.newly_placed + c.unplaceable
  return (
    <p role="status" className="text-body text-foreground">
      <span className="font-data" data-numeric>
        {total}
      </span>{' '}
      shipment{total === 1 ? '' : 's'}:{' '}
      <span className="font-data" data-numeric>
        {c.unchanged}
      </span>{' '}
      unchanged ·{' '}
      <span className="font-data" data-numeric>
        {c.moved}
      </span>{' '}
      moved ·{' '}
      <span className="font-data" data-numeric>
        {c.newly_placed}
      </span>{' '}
      newly placed ·{' '}
      <span className="font-data" data-numeric>
        {c.unplaceable}
      </span>{' '}
      unplaceable
    </p>
  )
}

/**
 * SS5.1's *"Effect: total driver waiting −85 min · promises moved 1 · overtime 0"* line.
 *
 * ## Every term is rendered, including the zeros -- and that reversed an earlier decision here
 *
 * This component originally omitted any term the run did not report, on the reasoning that a
 * defaulted `0` would manufacture a measurement. **Reconciling against the shipped
 * `sequencer.ObjectiveValues` inverted that**: every field is a non-nullable `int` and the server's
 * own docstring states the rule -- *"Every term is reported even when it is zero -- the same rule
 * `_rank_slot`'s `ranking_factors` follows since issue #69: 'the fairness term contributed nothing'
 * and 'there is no fairness term' must be distinguishable by reading the receipt."* So a `0` here
 * genuinely IS a measurement, and hiding it would destroy exactly the distinction the backend went
 * out of its way to preserve. Rendering it is the honest choice given the real contract, not a
 * relaxation of the absence rule.
 *
 * ## `churn_count` and `promises_moved` are both shown, because they are different numbers
 *
 * `promises_moved` counts every move; `churn_count` counts only the ones that were **communicated**
 * and moved past SS5.1's 15-minute epsilon -- i.e. exactly what `P_churn` prices. `churn_count <=
 * promises_moved` always. Showing only one would let a planner read "3 promises moved" as three
 * drivers being notified when the real number is one, or read "1" as the whole extent of the
 * reshuffle. SS5.1's own sample line says "promises moved 1", which is the churn figure.
 */
function ObjectiveLine({ run }: { run: SchedulingRun }) {
  const o = run.objective
  const parts = [
    `total driver waiting ${signed(o.waiting_minutes_delta)} min`,
    `promises moved ${o.promises_moved}`,
    `communicated moves (churn) ${o.churn_count}`,
    `objective cost ${o.total_cost}`,
  ]
  return (
    <p className="font-data text-supporting text-muted-foreground" data-numeric>
      Effect: {parts.join(' · ')}
    </p>
  )
}

/** An improvement is negative in SS5.1's own notation, so the sign is always shown. */
function signed(value: number): string {
  return value > 0 ? `+${value}` : String(value)
}

/**
 * SS5.1's moved list, with the annotation that makes churn checkable:
 * *"SHP1013 D2 18:00 → 18:30 (not yet communicated) · SHP1009 D4 19:15 → 19:45 (communicated —
 * driver will be notified)"*.
 *
 * A static list. There is no per-row control here and there is deliberately nowhere to add one --
 * see this file's header rule 1.
 */
function MovedList({ run }: { run: SchedulingRun }) {
  if (run.diff.moved.length === 0) return null
  return (
    <section className="flex flex-col gap-1">
      <h3 className="text-label uppercase tracking-wide text-muted-foreground">Moved</h3>
      <ul className="flex flex-col gap-1">
        {run.diff.moved.map((change) => (
          <li key={change.shipment_id} className="text-supporting text-foreground">
            <span className="font-data">{change.shipment_id}</span>{' '}
            {change.previous_dock_code ?? change.previous_dock_id ?? '—'}{' '}
            <span className="font-data">
              {change.previous_start_ts ? formatTime(change.previous_start_ts) : '—'}
            </span>{' '}
            →{' '}
            <span className="font-data">
              {change.dock_code} {formatTime(change.start_ts)}
            </span>
            {/* The PROMISE interval, not the claim: this list quotes what the driver was told and
                what they would be told instead. The board above draws the claim, which is a
                different (longer) interval -- see `ProposalDeltaBar`'s own note on why the two
                fields are not interchangeable. */}
            <span className="text-muted-foreground">
              {change.communicated
                ? change.is_churn
                  ? ' (communicated — driver will be notified)'
                  : ' (communicated — within the 15-minute epsilon, so not counted as churn)'
                : ' (not yet communicated)'}
            </span>
          </li>
        ))}
      </ul>
    </section>
  )
}

/**
 * `screens.md` section 6: *"Unplaceable shipments list separately below the board, since they have
 * no interval to show -- a gap is a gap, never a zero-width bar pretending to be a real
 * placement."* The prompt gives it the warning tone and a `calendar-x` icon by name.
 *
 * The reason string is rendered verbatim (SS5.1's own example: *"no compatible reefer interval
 * before close"*). Paraphrasing it into "couldn't place" would throw away the only sentence that
 * tells a planner what to do next.
 */
function UnplaceableList({ run }: { run: SchedulingRun }) {
  if (run.diff.unplaceable.length === 0) return null
  return (
    <section className="flex flex-col gap-2 rounded-md border border-warning-border bg-warning-bg px-3 py-2 text-warning-fg">
      <h3 className="flex items-center gap-2 text-supporting font-semibold">
        <CalendarX className="size-4 shrink-0" aria-hidden="true" />
        Couldn&rsquo;t place ({run.diff.unplaceable.length})
      </h3>
      <ul className="flex flex-col gap-1">
        {run.diff.unplaceable.map((change) => (
          <li key={change.shipment_id} className="text-supporting">
            <span className="font-data">{change.shipment_id}</span>
            {change.priority_code ? ` (${change.priority_code})` : ''}
            {/* `message` verbatim -- it is `evaluate_candidate_slot`'s own InfeasibleSlotReason
                prose, the same vocabulary the driver path uses, and SS5.1's own example row is
                "no compatible reefer interval before close". `failure_code` is shown beside it
                because the sentence is for a human and the code is what a planner would quote
                when escalating. */}
            {change.message ? ` — ${change.message}` : ''}
            {change.failure_code ? (
              <span className="font-data text-muted-foreground"> [{change.failure_code}]</span>
            ) : null}
          </li>
        ))}
      </ul>
    </section>
  )
}

/**
 * `stitch-prompts.md` section 11: *"Apply is all-or-nothing: **one** `[ Apply ]` button ...
 * idempotency-keyed."* Applying state freezes the label's width and sets `aria-busy`.
 *
 * The safer control comes first in DOM and tab order (U79), and the two are separated by the 16px
 * `components.md` section 19 requires between a neutral and a committing control.
 */
function ApplyBar({
  run,
  applying,
  onApply,
  onClose,
}: {
  run: SchedulingRun
  applying: boolean
  onApply: () => void
  onClose: () => void
}) {
  // A run the server no longer considers pending cannot be applied. Rendered as a stated reason
  // rather than a hidden button: a planner who opened this from a stale toolbar count needs to know
  // why, and `status` is the server's own answer.
  const stillPending = run.status === 'PROPOSED'
  return (
    <div className="mt-2 flex flex-wrap items-center gap-4">
      <Button variant="neutral" onClick={onClose}>
        Close without applying
      </Button>
      <Button
        variant="constructive"
        aria-disabled={applying || !stillPending}
        aria-busy={applying}
        className={applying || !stillPending ? 'opacity-50' : undefined}
        title={stillPending ? undefined : `This run is ${run.status}, so it can no longer be applied.`}
        onClick={() => {
          if (applying || !stillPending) return
          onApply()
        }}
      >
        {applying ? 'Applying…' : 'Apply'}
      </Button>
      <p className="text-supporting text-muted-foreground">
        {stillPending
          ? 'Applies the whole proposal or nothing — there is no way to apply part of it.'
          : `This run is ${run.status}, so it can no longer be applied.`}
      </p>
    </div>
  )
}

/**
 * Flow 9 step 3. *"No celebratory state"* (`stitch-prompts.md` section 11: no confetti, no success
 * overlay), and the notification batch is **named rather than described**, because SS5.1's cascade
 * path ends in that batch and a planner asked "were the drivers told?" needs the id, not a promise.
 *
 * The escalation is deliberately NOT resolved from here: `components.md` section 7 states that the
 * originating incident *"is left for `02-ops-exception-console/` to mark resolved, per that
 * surface's Flow 4 step 6"*. So this surface does not touch the escalation lifecycle at all.
 */
export function AppliedNotice({
  result,
  onClose,
}: {
  result: ApplyProposalResult
  onClose: () => void
}) {
  const batch =
    result.notification_batch_id !== null
      ? `Notification batch ${result.notification_batch_id}.`
      : result.notifications_enqueued !== null
        ? `${result.notifications_enqueued} notification${result.notifications_enqueued === 1 ? '' : 's'} queued.`
        : null
  return (
    <div
      role="alert"
      className="mt-2 flex flex-col gap-2 rounded-md border border-success-border bg-success-bg px-3 py-2 text-supporting text-success-fg"
    >
      <p>
        Applied in full. Run <span className="font-data">{result.scheduling_run_id}</span> is now the
        committed schedule.
      </p>
      {batch ? <p>{batch}</p> : null}
      <p>
        If this run came from an ops capacity incident, that escalation is closed on the ops console,
        not here.
      </p>
      <Button variant="neutral" className="self-start" onClick={onClose}>
        Close
      </Button>
    </div>
  )
}

/**
 * Flow 9 step 4 / `edge-cases.md` section 5.
 *
 * **One action, and it is not a retry.** *"Never a blind retry of the stale proposal"* --
 * `onRequestFresh` closes this overlay and asks the console to compute a new run. The stale run's
 * id and hash are dropped with the overlay, so there is nothing left for a later press to re-send.
 *
 * ## Two causes, and only one of them is "the schedule changed"
 *
 * Measured against the live route on 2026-09-02: the refusal payload carries three hashes --
 * `expected_snapshot_hash` (the run's own), `current_snapshot_hash` (the facility's digest now) and
 * `supplied_snapshot_hash` (what the caller sent). Genuine drift is `expected !== current`: the
 * world moved under the proposal, which is the case `edge-cases.md` section 5 describes and the only
 * one this console can reach, since it always sends the run's hash verbatim.
 *
 * A malformed or stale *supplied* hash produces the same `SNAPSHOT_DRIFT` code while
 * `expected === current` -- nothing changed at all. Rendering the design's sentence in that case
 * would have the UI assert something untrue, so the two are told apart. The distinction costs one
 * comparison and keeps the one screen whose whole job is explaining *why* honest.
 *
 * **The run is retired either way**, and that is the server's deliberate behaviour rather than a
 * side effect: a drifted run comes back `status: SUPERSEDED` with `superseded_reason:
 * SNAPSHOT_DRIFT`, which enforces "the fix is a fresh proposal, not forcing the stale one through"
 * and frees the facility's one-active-run index so the button below can immediately succeed.
 */
export function SnapshotDrift({
  result,
  onRequestFresh,
}: {
  result?: ApplyProposalResult
  onRequestFresh: () => void
}) {
  const drift = (result?.drift ?? {}) as Record<string, unknown>
  const expected = drift.expected_snapshot_hash
  const current = drift.current_snapshot_hash
  // Only claim the schedule moved when the two server-side digests actually differ. Unknown fields
  // fall back to the design's sentence, which is the common and expected case.
  const scheduleMoved =
    typeof expected === 'string' && typeof current === 'string' ? expected !== current : true

  return (
    <div
      role="alert"
      className="mt-2 flex flex-col gap-2 rounded-md border border-danger-border bg-danger-bg px-3 py-2 text-supporting text-danger-fg"
    >
      <p className="flex items-start gap-2">
        <TriangleAlert className="mt-0.5 size-4 shrink-0" aria-hidden="true" />
        <span>
          <strong className="font-semibold">Nothing was applied.</strong>{' '}
          {scheduleMoved
            ? 'The schedule changed after this proposal was calculated, so it can no longer be applied safely.'
            : 'This proposal was submitted with a snapshot the server did not recognise, so it was refused rather than applied against capacity nobody re-checked.'}
        </span>
      </p>
      <p>This run has been retired — a fresh one is the only way forward, never a retry of this one.</p>
      <Button variant="constructive" className="self-start" onClick={onRequestFresh}>
        Request a fresh proposal
      </Button>
    </div>
  )
}

/**
 * Flow 9 step 5 / `edge-cases.md` section 5, and the screen most at risk of being "helpfully"
 * softened later.
 *
 * *"Partial infeasibility means the whole batch is invalid together -- the tool's own
 * all-or-nothing contract means there is no 'apply what's still valid' fallback to offer, and the
 * UI does not pretend otherwise."* So: the shipments that stopped fitting are **named** (step 5:
 * *"explains which constraint made the whole proposal invalid, not just that it failed"*), and the
 * only forward action is a fresh proposal or leaving it. There is no Apply button in this state and
 * no per-row control beside any named shipment.
 */
export function PartiallyInfeasible({
  result,
  onClose,
}: {
  result: ApplyProposalResult
  onClose: () => void
}) {
  return (
    <div
      role="alert"
      className="mt-2 flex flex-col gap-2 rounded-md border border-danger-border bg-danger-bg px-3 py-2 text-supporting text-danger-fg"
    >
      <p className="flex items-start gap-2">
        <OctagonAlert className="mt-0.5 size-4 shrink-0" aria-hidden="true" />
        <span>
          <strong className="font-semibold">Nothing was applied.</strong> This proposal can&rsquo;t be
          applied — the proposal only applies as a whole.
        </span>
      </p>
      {result.infeasible.length === 0 ? null : (
        <ul className="flex flex-col gap-1">
          {result.infeasible.map((row, i) => {
            // `ApplyResult.infeasible` is `list[dict[str, Any]]` on the wire -- the one loosely
            // typed field in the sequencer contract -- so each row is read defensively rather than
            // cast. A row that carries no shipment id still renders its position, because "one of
            // the placements failed" is a truer statement than dropping it silently.
            const shipment = typeof row.shipment_id === 'string' ? row.shipment_id : null
            const why =
              typeof row.message === 'string'
                ? row.message
                : typeof row.reason === 'string'
                  ? row.reason
                  : null
            return (
              <li key={shipment ?? i}>
                <span className="font-data">{shipment ?? 'A placement'}</span>
                {why ? ` — ${why}` : ' no longer fits any dock in the window'}
              </li>
            )
          })}
        </ul>
      )}
      <p className="flex items-start gap-2">
        <Info className="mt-0.5 size-4 shrink-0" aria-hidden="true" />
        <span>
          There is no option to apply the rest: the sequencer validated these placements together, so
          a subset is a schedule nobody checked.
        </span>
      </p>
      <Button variant="neutral" className="self-start" onClick={onClose}>
        Close
      </Button>
    </div>
  )
}

/**
 * `stitch-prompts.md` section 11's loading state: *"the board's lanes render at their real
 * dimensions with a pulsing block drawn over them, in the surface's own muted token; never a centred
 * spinner, which causes a layout jump."*
 */
function ProposalSkeleton() {
  return (
    <div aria-busy="true" aria-label="Loading the proposal" className="flex flex-col gap-2">
      <Skeleton className="h-4 w-2/3" />
      {Array.from({ length: 5 }).map((_, i) => (
        <div key={i} className="flex items-center gap-2">
          <Skeleton className="h-8 w-14 shrink-0" />
          <Skeleton className="h-8 flex-1" />
        </div>
      ))}
      <Skeleton className="h-4 w-1/2" />
    </div>
  )
}
