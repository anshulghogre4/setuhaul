import { useState, type ReactNode } from 'react'

import { BoardSkeleton } from '../components/board-skeleton'
import { BoardPlate } from '../components/dock-board'
import { NarrowViewportGuard } from '../components/narrow-viewport'
import { NotYetAvailable } from '../components/not-yet-available'
import {
  QueueEmptyCaughtUp,
  QueueEmptyNothingYet,
  QueueSearchEmpty,
  QueueSkeleton,
} from '../components/queue-region-states'
import { QueueRow } from '../components/queue-row'
import { ReviewProposalButton } from '../components/review-proposal-button'
import { Maintenance, NotFound, RegionError } from '@/components/states/region-states'
import { BOARD, BOARD_EMPTY, OUTCOME_SKIPPED, ROW_CLEAN, ROW_CONFLICTED, ROW_DERIVED } from './fixtures'
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
          The queue is live; the board and the hold are not
        </h1>
        <p className="mt-2 max-w-[80ch] text-body text-muted-foreground">
          Updated 2026-08-29: `get_planner_queue` and the four write tools that start from one of
          its rows all shipped, so the Queue tab, its five affordances, the refusal taxonomy and
          bulk confirm are real. What is still stubbed is stubbed for a reason no UI can fix --
          `dock_occupancy.state` does not exist in any live database (issue #53, migration
          unapplied), `hold_for_information` is unbuilt (#64), the Sequencer is entirely unbuilt
          (#49), and there is no live-update transport for the "N new" pill (#59). See
          `features/planner/lib/flags.ts` for what each flag now gates and what was verified before
          it moved.
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

        <Plate n="—" title="Review proposal — Inactive with (0), issue #49">
          <ReviewProposalButton />
        </Plate>

        <Note n="12, 13" title="Reject dialog — built, and reachable on /planner">
          Not duplicated here as a fixture: it needs a live row to reject, and the preview block's
          whole point is that it renders the exact words the driver receives for the reason code
          actually chosen. Open it from a queue row on `/planner` (`R`, or the ✕ affordance). Built
          against `allocation.REJECTION_REASON_CODES` — the field is `reason_code`, not the older
          prose's `rejection_reason`, and the 422 naming the supported set is handled rather than
          assumed unreachable.
        </Note>

        <Note n="3, 24, 25" title="Counter-offer — built as an interim form, not the board picker">
          `counter_offer` shipped (#63) and is reachable from a queue row (`O`), but U103's
          dock/time grid needs `dock_occupancy.state` — a column no live database has (#53,
          migration unapplied). The interim dialog offers the intervals Stage 1 says are feasible
          for that shipment, which is the same eligibility the dimmed lanes were going to express;
          what is lost is the spatial context. Flagged in `lib/flags.ts`, not treated as the
          finished design.
        </Note>

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

        <Note n="7, 14, 15" title="Hold for information — still blocked, and it needs a tool">
          The `appointments.expires_at` column the original blocker named now exists in the #53
          migration, but that migration is applied to no database and `hold_for_information`
          itself is unbuilt (#64). Two gates, not one — the Hold affordance renders Inactive with
          that explanation rather than as a button with nowhere to go.
        </Note>

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
