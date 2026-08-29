import { useState, type ReactNode } from 'react'

import { BoardSkeleton } from '../components/board-skeleton'
import { NarrowViewportGuard } from '../components/narrow-viewport'
import { NotYetAvailable } from '../components/not-yet-available'
import {
  QueueEmptyCaughtUp,
  QueueEmptyNothingYet,
  QueueSearchEmpty,
  QueueSkeleton,
} from '../components/queue-region-states'
import { ReviewProposalButton } from '../components/review-proposal-button'
import { Maintenance, NotFound, RegionError } from '@/components/states/region-states'

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
        <h1 className="mt-2 text-display text-balance">10 states ship now, 17 are honestly stubbed</h1>
        <p className="mt-2 max-w-[80ch] text-body text-muted-foreground">
          Every write path on this surface starts from a queue row `get_planner_queue` (issue #60)
          would produce, and that tool does not exist -- only the block-dock group
          (`block_dock`/`end_dock_block`/`get_dock_block_impact`, all fully shipped in E3.6) has a
          complete backend. See `features/planner/lib/flags.ts` and `planner-console.tsx`'s own
          header comment for the full gap list (issues #60-66, #53, #49, #59).
        </p>
      </header>

      <div className="flex flex-col gap-10">
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

        <Note n="1, 6, 8, 9, 10, 11" title="Queue at rest, refusals, bulk confirm — blocked">
          Needs `get_planner_queue` (issue #60) and `snapshot_hash` (#61)/the refusal taxonomy
          (#62)/`bulk_confirm` (#65). The live `/planner` Queue tab renders this same honest note
          via `NotYetAvailable` rather than a fixture queue.
        </Note>

        <Note n="2, 3, 22, 24, 25" title="Board at rest, counter-offer picker — blocked">
          `dock_occupancy` has no `state` column (issue #53, same migration gap that blocks the
          HELD promise-state) and `counter_offer` does not exist (issue #63).
        </Note>

        <Note n="7, 14, 15" title="Hold for information — blocked, needs a migration">
          `public.appointments` has no deadline/expires_at column (`expiry.py:77-81`'s own
          comment) — issue #64.
        </Note>

        <Note n="12, 13" title="Reject dialog — blocked on a live row to reject">
          `reject_appointment` is real and works, but every entry point to it is a queue row
          (issue #60). Its `rejection_reason` enum is also not server-enforced yet (issue #66) —
          a client-side courtesy once #60 lands, not a contract.
        </Note>

        <Note n="19, 20, 21" title="Sequencer proposal diff — blocked">
          Section 7.5.3 is entirely unbuilt (issue #49) — the planner half of the same handoff
          E5.2's prompt 14 is the ops half of.
        </Note>
      </div>
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
