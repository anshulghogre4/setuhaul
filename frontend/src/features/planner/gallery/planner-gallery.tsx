import { useState, type ReactNode } from 'react'

import { BoardSkeleton } from '../components/board-skeleton'
import { BoardPickerBanner } from '../components/board-picker'
import { BoardPlate } from '../components/dock-board'
import { QueueFilterControl } from '../components/queue-filter'
import { NarrowViewportGuard } from '../components/narrow-viewport'
import { NotYetAvailable } from '../components/not-yet-available'
import {
  QueueEmptyCaughtUp,
  QueueEmptyNothingYet,
  QueueFilterEmpty,
  QueueSearchEmpty,
  QueueSkeleton,
} from '../components/queue-region-states'
import {
  AppliedNotice,
  PartiallyInfeasible,
  ProposalReviewBody,
  SnapshotDrift,
} from '../components/proposal-overlay'
import { QueueRow } from '../components/queue-row'
import { RequestResequenceButton } from '../components/request-resequence-button'
import { ReviewProposalButton } from '../components/review-proposal-button'
import { Maintenance, NotFound, RegionError } from '@/components/states/region-states'
import {
  BOARD,
  BOARD_EMPTY,
  OUTCOME_SKIPPED,
  PICKER_OPTIONS,
  PICKER_ROW,
  PROPOSAL_DELTAS,
  PROPOSAL_INFEASIBLE,
  PROPOSAL_RUN,
  ROW_CLEAN,
  ROW_CONFLICTED,
  ROW_DERIVED,
  ROW_DOCK_BLOCKED,
  ROW_HELD,
} from './fixtures'
import {
  EMPTY_QUEUE_FILTER,
  describeQueueFilter,
  filterQueueRows,
  type QueueFilter,
} from '../lib/queue-filter'
import type { RejectReasonCode } from '../lib/reasons'
import type { PlannerRefusal } from '../lib/refusals'
import type { BulkConfirmOutcome, PlannerQueueRow } from '../lib/types'

/**
 * Every planner-dock-board screen `implementation-spec.md` section 3 marks 🟢 or 🟡, rendered by
 * the **built components** -- route `/planner/_states`, not linked from the app. Same purpose as
 * `/ops/_states` and `/driver/_states`: "it type-checks" is not "it has been seen rendering."
 *
 * 🔴 screens (the live queue at rest, confirm/refusals, counter-offer, hold, bulk confirm, the
 * board at rest, sequencer diff) render an honest note instead of a fake plate -- this build's own
 * brief is explicit that a screen with nothing to call must not look like it works. The block-dock
 * group (16-18) is the one write path with real backend wiring; it lives on `/planner` itself
 * (`[ Block a dock ]`), not duplicated here as a fixture.
 */
export function PlannerStatesGallery() {
  return (
    <div className="min-h-dvh bg-background p-6 text-foreground" data-density="compact">
      <header className="mb-8">
        <p className="text-label text-primary uppercase">SetuHaul · planner dock board (E5.3)</p>
        <h1 className="mt-2 text-display text-balance">
          The queue, the board and the hold are live; the sequencer is not
        </h1>
        <p className="mt-2 max-w-[80ch] text-body text-muted-foreground">
          Updated 2026-09-02. `get_planner_queue` and every write tool that starts from one of its
          rows have shipped, so the Queue tab, its five affordances, the refusal taxonomy and bulk
          confirm are real. Since 2026-08-31 the Board tab renders live occupancy (#53 applied,
          #84 fixed); since 2026-09-02 the counter-offer <strong>board picker</strong> replaces the
          interim dialog (U103) and <strong>hold for information</strong> is wired to its shipped
          tool (#64). One thing genuinely remains stubbed for a reason no UI can fix: section
          7.5.3's Sequencer is entirely unbuilt (#49), so the proposal diff has nothing to call.
          Two divergences are deliberate and flagged rather than hidden -- the held countdown keeps
          its number (the shipped tool extends the deadline, it does not pause the clock), and
          lane eligibility in the picker is Stage 1's answer projected onto lanes rather than a
          per-dock constraint explanation. See `features/planner/lib/flags.ts` for what each flag
          gates and what was verified before it moved.
        </p>
      </header>

      <div className="flex flex-col gap-10">
        <Plate n="1" title="The 30-second row — clean: no displacement, exact dock, inside the safe batch">
          <RowPlate rows={[ROW_CLEAN, ROW_DERIVED]} />
        </Plate>

        <Plate
          n="1b"
          title="Displacement + LOW ETA confidence — the sentence wraps, the warning never truncates"
        >
          <RowPlate rows={[ROW_CONFLICTED]} />
        </Plate>

        <Plate
          n="1d"
          title="Issue #88 — both displacement legs: a displaced shipment AND a blocked dock, as two sentences"
        >
          {/* The regression plate for "Confirming this displaces undefined." A DOCK_BLOCKED
              conflict carries no shipment_id, so the old mapper printed undefined into section
              7.3's most important column. */}
          <RowPlate rows={[ROW_DOCK_BLOCKED]} />
        </Plate>

        <QueueFilterDemo />

        <Plate n="8a" title="ALREADY_ACTIONED — assertive, and the winning transition is named">
          <RowPlate
            rows={[ROW_CLEAN]}
            refusal={{
              kind: 'ALREADY_ACTIONED',
              message:
                'Cannot confirm this appointment: it is already EXPIRED. Reason recorded: D9 deadline passed.',
            }}
          />
        </Plate>

        <Plate n="8b" title="SNAPSHOT_STALE — deliberately quiet. Not a conflict, so it must not look like one">
          <RowPlate
            rows={[ROW_CLEAN]}
            refusal={{
              kind: 'SNAPSHOT_STALE',
              message: 'The queue row changed since it was rendered; re-read it before deciding again.',
              drift: null,
            }}
          />
        </Plate>

        <Plate
          n="8c"
          title="DISPLACEMENT_DETECTED — the SERVER's conflict set replaces the row's, because they are not the same set"
        >
          <RowPlate
            rows={[ROW_CLEAN]}
            refusal={{
              kind: 'DISPLACEMENT_DETECTED',
              message:
                'Cannot confirm: a conflict appeared on this dock interval since the row was rendered (APT-OTHER-77, DEVT002 dock block).',
              conflicts: [],
            }}
          />
        </Plate>

        <Plate n="9" title="Bulk confirm — a skipped row stays visible with its failing predicates named">
          <RowPlate rows={[ROW_CONFLICTED]} outcome={OUTCOME_SKIPPED} />
        </Plate>

        <Plate n="26a" title="Queue empty — caught up">
          <div className="w-[420px] border border-border">
            <QueueEmptyCaughtUp />
          </div>
        </Plate>

        <Plate n="26b" title="Queue empty — nothing yet (newly provisioned facility)">
          <div className="w-[420px] border border-border">
            <QueueEmptyNothingYet />
          </div>
        </Plate>

        <SearchEmptyDemo />

        <Plate n="27" title="Queue skeleton — real row dimensions, never a centred spinner">
          <div className="w-[560px] border border-border">
            <QueueSkeleton />
          </div>
        </Plate>

        <Plate n="29a" title="Queue load failed — scoped to the region">
          <div className="w-[420px] border border-border">
            <RegionError regionName="queue" onRetry={() => {}} />
          </div>
        </Plate>

        <Plate n="29b" title="404 / out of scope — the same message covers both cases">
          <div className="w-[420px] border border-border">
            <NotFound backHref="/planner" />
          </div>
        </Plate>

        <Plate n="29c" title="Maintenance — always states a duration">
          <div className="w-[420px] border border-border">
            <Maintenance estimatedMinutes={15} />
          </div>
        </Plate>

        <Plate n="30" title="Below 1024px — a statement, not a squeezed table">
          <div className="w-[420px] border border-border">
            {/* Forced, not resized: NarrowViewportGuard reads the real window width, which this
                gallery plate cannot shrink on its own without shrinking the whole page. */}
            <ForcedNarrow />
          </div>
        </Plate>

        <Plate n="23" title="Board failed to load — scoped to the region, queue stays usable">
          <div className="w-[420px] border border-border">
            <RegionError regionName="dock board" onRetry={() => {}} />
          </div>
        </Plate>

        <Plate n="28" title="Board skeleton — shaped like lanes, not rows">
          <div className="w-[560px] border border-border">
            <BoardSkeleton />
          </div>
        </Plate>

        <Plate n="—" title="Review proposal — Inactive with (0), and live with a real count">
          {/* Two states since `GET /api/v1/scheduling/runs` landed (2026-09-02). The third --
              "the server cannot answer, so the count is unknown" -- was real while no list
              endpoint existed and is now unreachable, so it is deleted rather than kept as a
              defensive branch. `(0)` stays Inactive-not-Disabled: focusable, and it explains
              itself on activation. */}
          <div className="flex flex-wrap items-center gap-4">
            <ReviewProposalButton count={0} />
            <ReviewProposalButton count={2} />
          </div>
        </Plate>

        <Plate n="—" title="Request re-sequence — idle, in flight, and RUN_ALREADY_ACTIVE">
          {/* `edge-cases.md` §4's debounce state is an INFO-toned inline notice with no retry
              affordance, deliberately distinct from the danger-toned apply refusals below --
              retrying is the exact thing the debounce exists to prevent. */}
          <div className="flex flex-col gap-3">
            <RequestResequenceButton />
            <RequestResequenceButton busy />
            <RequestResequenceButton runAlreadyActive alreadyActiveRunId="RUN-8f2a" />
          </div>
        </Plate>

        <Plate
          n="19, 20, 21"
          title="Sequencer proposal — the diff drawn on the board itself (§5.1's four categories)"
        >
          <div className="flex w-[860px] flex-col gap-3">
            {/* The delta layer rendered through the SAME `Board` the live overlay and the live
                Board tab both mount. Four things are worth looking at rather than reading:
                SHP1009's MOVED outline sits on D4 (the ARRIVAL lane, not the origin), SHP1044's
                badge reads NEW, SHP1031 is unchanged and therefore carries NO outline at all, and
                SHP1015 is unplaceable so it appears only in the list below -- never as a bar. */}
            <BoardPlate board={BOARD} proposal={PROPOSAL_DELTAS} />
            <ProposalReviewBody run={PROPOSAL_RUN} />
          </div>
        </Plate>

        <Plate n="20, 21" title="Apply outcomes — applied, and the two refusals that are never retries">
          {/* All three are the REAL components the overlay mounts. The two refusals are the pair
              §5.1 forbids softening: SNAPSHOT_DRIFT offers a FRESH proposal (never a retry of the
              stale one), and PARTIALLY_INFEASIBLE names the shipments and offers no "apply what's
              still valid" — because the tool has no argument for one. Neither renders an Apply
              button, and neither list carries a per-row control. */}
          <div className="flex w-[720px] flex-col gap-4">
            <AppliedNotice
              result={{
                as_of: PROPOSAL_RUN.as_of,
                code: 'APPLIED',
                scheduling_run_id: PROPOSAL_RUN.scheduling_run_id,
                status: 'APPLIED',
                notification_batch_id: PROPOSAL_RUN.scheduling_run_id,
                notifications_enqueued: 3,
                moved: 2,
                newly_placed: 1,
                unchanged: 1,
                drift: null,
                infeasible: [],
                idempotency_key: null,
                idempotent_replay: false,
              }}
              onClose={() => {}}
            />
            {/* Both drift causes. Only the first is reachable from this console (it always sends
                the run's own hash), but the second exists because the server answers the same code
                for a malformed supplied hash -- measured 2026-09-02 -- and the copy must not claim
                the schedule moved when the two server-side digests are identical. */}
            <SnapshotDrift onRequestFresh={() => {}} />
            <SnapshotDrift
              onRequestFresh={() => {}}
              result={{
                as_of: PROPOSAL_RUN.as_of,
                code: 'SNAPSHOT_DRIFT',
                scheduling_run_id: PROPOSAL_RUN.scheduling_run_id,
                status: 'SUPERSEDED',
                notification_batch_id: null,
                notifications_enqueued: 0,
                moved: 0,
                newly_placed: 0,
                unchanged: 0,
                drift: {
                  expected_snapshot_hash: 'sha256/same',
                  current_snapshot_hash: 'sha256/same',
                  supplied_snapshot_hash: 'sha256/stale',
                },
                infeasible: [],
                idempotency_key: null,
                idempotent_replay: false,
              }}
            />
            <PartiallyInfeasible
              result={{
                as_of: PROPOSAL_RUN.as_of,
                code: 'PARTIALLY_INFEASIBLE',
                scheduling_run_id: PROPOSAL_RUN.scheduling_run_id,
                status: 'PROPOSED',
                notification_batch_id: null,
                notifications_enqueued: 0,
                moved: 0,
                newly_placed: 0,
                unchanged: 0,
                drift: null,
                infeasible: PROPOSAL_INFEASIBLE,
                idempotency_key: null,
                idempotent_replay: false,
              }}
              onClose={() => {}}
            />
          </div>
        </Plate>

        <Note n="12, 13" title="Reject dialog — built, and reachable on /planner">
          Not duplicated here as a fixture: it needs a live row to reject, and the preview block's
          whole point is that it renders the exact words the driver receives for the reason code
          actually chosen. Open it from a queue row on `/planner` (`R`, or the ✕ affordance). Built
          against `allocation.REJECTION_REASON_CODES` — the field is `reason_code`, not the older
          prose's `rejection_reason`, and the 422 naming the supported set is handled rather than
          assumed unreachable.
        </Note>

        <BoardPickerDemo />

        <Plate n="2" title="Board at rest — every bar treatment components.md §3 can produce">
          <div className="w-[860px]">
            {/* Rendered from a fixture through the SAME component the live Board tab mounts, so a
                plate cannot certify markup the route does not use. Worth looking at rather than
                reading: D3's HELD bar is 2px DASHED (the shape channel that survives greyscale and
                glare), D2's IN_PROGRESS carries a truck icon rather than a fifth hue, D2's bar
                clamps to the left edge because its unload began before the horizon, D4 is EMPTY --
                its only occupancy is COMPLETED, which renders as open space and never a ghost bar --
                and D5 carries the outage hatch, which shares no encoding with any booking. */}
            <BoardPlate board={BOARD} />
          </div>
        </Plate>

        <Plate n="22" title="Board — empty horizon (the lanes stay, never a blank panel)">
          <div className="w-[860px]">
            <BoardPlate board={BOARD_EMPTY} />
          </div>
        </Plate>

        <Plate
          n="7, 14, 15"
          title="Hold for information — spent: held countdown, and the Hold affordance disabled with its reason"
        >
          {/* Issue #64 shipped, so this is a real state rather than a note about a missing tool.
              Worth looking at rather than reading: the TTL cell keeps its NUMBER. U67 says a
              paused countdown hides the value, but the shipped mechanism is a bounded EXTENSION,
              not a pause -- time is still elapsing, so hiding it would assert the opposite. See
              queue-row.tsx's TTL cell for the full reasoning and the owner fork it raises. */}
          <RowPlate rows={[ROW_HELD]} />
        </Plate>

        <Note n="—" title="Escalate — no tool in section 7.5.1's shape">
          `escalate_request(appointment_id, reason, owner?)` does not exist. The shipped
          `POST /operations/escalate` needs an `escalation_type` from a fixed nine-value
          vocabulary with no value meaning "a planner needs help deciding this request", and it
          would not remove the row from this queue the way Flow 5 requires. Rendered Inactive with
          that reason rather than wired to the nearest-looking endpoint.
        </Note>

        <Note n="11" title="Toasts — built, minus the undo affordance">
          U41's 5-second undo depends on the driver notification being queued and dispatched only
          when the window closes, with undo cancelling it silently. No server-side mechanism does
          that, so a button claiming to undo a committed confirm would be a lie. The confirm,
          reject, counter-offer and partial-batch toasts are all real; the undo bar is
          deliberately absent.
        </Note>

        <Note n="19, 20, 21" title="Sequencer proposal diff — blocked">
          Section 7.5.3 is entirely unbuilt (issue #49) — the planner half of the same handoff
          E5.2's prompt 14 is the ops half of.
        </Note>
      </div>
    </div>
  )
}

/**
 * Renders real `QueueRow`s inside a real table with the live colgroup, so a plate exercises the
 * component the route uses rather than a look-alike. Interaction is inert here on purpose -- the
 * handlers are no-ops, because a gallery must never be able to issue a write.
 */
function RowPlate({
  rows,
  refusal,
  outcome,
}: {
  rows: PlannerQueueRow[]
  refusal?: PlannerRefusal
  outcome?: BulkConfirmOutcome
}) {
  const [focused, setFocused] = useState<string | null>(null)
  return (
    <div className="w-[1180px] overflow-auto border border-border">
      <table className="w-full table-fixed border-collapse">
        <colgroup>
          <col style={{ width: '48px' }} />
          <col style={{ width: '164px' }} />
          <col style={{ width: '210px' }} />
          <col style={{ width: '190px' }} />
          <col style={{ width: '250px' }} />
          <col style={{ width: '72px' }} />
          <col style={{ width: '80px' }} />
          <col style={{ width: '66px' }} />
          <col style={{ width: '160px' }} />
        </colgroup>
        <tbody>
          {rows.map((row) => (
            <QueueRow
              key={row.appointment_id}
              row={row}
              ttlTotalMs={15 * 60_000}
              focused={focused === row.appointment_id}
              selected={false}
              busy={false}
              selectionCaveat={null}
              refusal={refusal ?? null}
              outcome={outcome ?? null}
              onFocusRow={() => setFocused(row.appointment_id)}
              onToggleSelect={() => {}}
              onConfirm={() => {}}
              onReject={() => {}}
              onCounterOffer={() => {}}
            />
          ))}
        </tbody>
      </table>
    </div>
  )
}

/**
 * **States 3 / 24 / 25 — the counter-offer board picker** (U103, `screens.md` section 4).
 *
 * Mounts the real `BoardPickerBanner` and the real `Board` (through `BoardPlate`) over fixture
 * options, so what a reviewer or a click-sweep sees is the component the `/planner` route renders,
 * not a look-alike. **It cannot write**: `BoardPlate` takes no `counterOffer` path at all -- that
 * call lives in `DockBoardPanel`, which this gallery never mounts -- so `Send counter-offer` here
 * is inert by construction rather than by a disabled attribute.
 *
 * This plate exists because the live surface cannot demonstrate the picker today, and that is an
 * environment fact rather than a build gap: `PlannerConsole` scopes to the signed-in planner's own
 * facility, `get_planner_queue` for `FAC-JAI-01` returns `count: 0`, and the only pending
 * appointment in the system sits at `FAC-GGN-01` where no `WAREHOUSE_PLANNER` account exists. With
 * no queue row there is no Counter-offer to press. Recorded here so the picker's rendering is
 * verifiable now and the live activation can be checked the moment a Jaipur row exists.
 */
function BoardPickerDemo() {
  const [chosen, setChosen] = useState<string | null>(null)
  const [reason, setReason] = useState<RejectReasonCode | null>(null)
  const [note, setNote] = useState('')
  const chosenOption = PICKER_OPTIONS.find((o) => o.slot_id === chosen) ?? null

  return (
    <Plate
      n="3, 24, 25"
      title="Counter-offer board picker — eligible lanes clickable, ineligible dimmed, out-of-horizon options counted"
    >
      <div className="w-[860px]">
        <BoardPickerBanner
          row={PICKER_ROW}
          chosen={chosenOption}
          reason={reason}
          note={note}
          optionCount={PICKER_OPTIONS.length}
          // SLOT-G3 starts at 10:15Z against a horizon ending 09:30Z -- see `fixtures.ts`.
          outOfHorizonCount={1}
          loading={false}
          busy={false}
          error={null}
          onReasonChange={setReason}
          onNoteChange={setNote}
          onClearChoice={() => setChosen(null)}
          onCancel={() => setChosen(null)}
          onSubmit={() => {}}
        />
        <BoardPlate
          board={BOARD}
          pickable={PICKER_OPTIONS}
          chosenSlotId={chosen}
          onPickInterval={(option) => setChosen(option.slot_id)}
        />
      </div>
    </Plate>
  )
}

/**
 * **The priority / ETA-confidence filter** (`screens.md` section 2's Rules).
 *
 * Mounts the real `QueueFilterControl` over the real `filterQueueRows` predicate and the same
 * fixture rows plate 1 uses, so the narrowing observed here is the narrowing `queue-tab.tsx`
 * performs -- one implementation, exercised twice, per `lib/queue-filter.ts`'s own header.
 *
 * The three fixtures cover the axes between them: `ROW_CLEAN` is CRITICAL / MEDIUM,
 * `ROW_DERIVED` is HIGH, and `ROW_CONFLICTED` is NORMAL / **LOW** — so "CRITICAL only" and
 * "LOW confidence only", the design's two stated use cases, both narrow to exactly one row.
 */
function QueueFilterDemo() {
  const [filter, setFilter] = useState<QueueFilter>(EMPTY_QUEUE_FILTER)
  const rows = [ROW_CLEAN, ROW_DERIVED, ROW_CONFLICTED]
  const shown = filterQueueRows(rows, filter)
  const summary = describeQueueFilter(filter, shown.length)

  return (
    <Plate n="1c" title="Filter by priority or ETA confidence — membership only, never the sort">
      <div className="flex flex-col gap-2">
        <div className="flex items-center gap-4 text-supporting">
          <QueueFilterControl filter={filter} onChange={setFilter} />
          {/* The design's chip-free affordance: "Filter: CRITICAL · 6 shown" in the toolbar. */}
          {summary ? <span className="font-semibold">{summary}</span> : null}
        </div>
        {shown.length === 0 ? (
          <QueueFilterEmpty description={summary ?? ''} onClear={() => setFilter(EMPTY_QUEUE_FILTER)} />
        ) : (
          <RowPlate rows={shown} />
        )}
      </div>
    </Plate>
  )
}

function SearchEmptyDemo() {
  const [query] = useState("RJ14")
  return (
    <Plate n="26c" title="Search returned nothing">
      <div className="w-[420px] border border-border">
        <QueueSearchEmpty query={query} onClear={() => {}} />
      </div>
    </Plate>
  )
}

function ForcedNarrow() {
  return (
    <NarrowViewportGuard>
      <NotYetAvailable title="(resize the window below 1024px to see this live)" body="" />
    </NarrowViewportGuard>
  )
}

function Plate({ n, title, children }: { n: string; title: string; children: ReactNode }) {
  return (
    <figure className="m-0">
      <figcaption className="mb-2 text-body">
        <span className="font-mono text-primary">{n}</span>{' '}
        <span className="text-muted-foreground">{title}</span>
      </figcaption>
      {children}
    </figure>
  )
}

function Note({ n, title, children }: { n: string; title: string; children: ReactNode }) {
  return (
    <figure className="m-0 max-w-[70ch]">
      <figcaption className="mb-2 text-body">
        <span className="font-mono text-primary">{n}</span>{' '}
        <span className="text-muted-foreground">{title}</span>
      </figcaption>
      <p className="rounded-md border border-dashed border-border p-4 text-body text-muted-foreground">
        {children}
      </p>
    </figure>
  )
}
