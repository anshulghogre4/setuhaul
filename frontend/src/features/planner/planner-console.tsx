import { useCallback, useEffect, useId, useRef, useState, type ReactNode, type Ref } from 'react'
import { toast } from 'sonner'

import { BlockDockDialog } from './components/block-dock-dialog'
import { DockBoardPanel } from './components/dock-board'
import { NarrowViewportGuard } from './components/narrow-viewport'
import { NotYetAvailable } from './components/not-yet-available'
import { ProposalOverlay } from './components/proposal-overlay'
import { QueueTab } from './components/queue-tab'
import { RequestResequenceButton } from './components/request-resequence-button'
import { ReviewProposalButton } from './components/review-proposal-button'
import { listPendingSchedulingRuns, proposeFacilitySchedule } from './lib/api'
import {
  dockBoardEnabled,
  plannerBoardPickerEnabled,
  plannerQueueLiveEnabled,
  sequencerProposalEnabled,
} from './lib/flags'
import type { PlannerQueueRow } from './lib/types'
import { Button } from '@/shared/ui/button'
import { formatUserFriendlyError } from '@/core/http/api'

type Tab = 'queue' | 'board'

/**
 * `screens.md` section 1 (issue #38/E5.3). One workspace, two TABS -- never routes
 * (`00-foundations/components.md`'s "rail destination vs tab" table names Planner Queue/Board
 * explicitly). §7's suggested build order step 1: real tab semantics first, everything else
 * mounts inside it.
 *
 * **`data-density="compact"` is already set by the shell** (`identity.ts`'s
 * `densityFor('planner')`, resolved from `WAREHOUSE_PLANNER`'s rail destination) -- not repeated
 * here, same comment E5.2's `OpsConsole` makes for its own surface.
 *
 * **Queue tab: real backend wiring** (2026-08-29) -- `get_planner_queue` plus confirm / reject /
 * counter-offer / bulk-confirm, all shipped and all reachable. **Board tab: real occupancy**
 * (2026-08-31) -- `GET /api/v1/planner/board` over the hold-aware `list_live_dock_occupancy` that
 * issue #84 fixed, rendered through `components.md` section 3's nine-value mapping table. The
 * counter-offer picker's interactive mode is still the interim dialog; see `lib/flags.ts` for what
 * each flag now gates and what was verified before it moved.
 */
export function PlannerConsole({ facilityId }: { facilityId: string }) {
  const [tab, setTab] = useState<Tab>('queue')
  const [blockDialogOpen, setBlockDialogOpen] = useState(false)
  /** Flow 7 step 4 (issue #100): a successful `block_dock` must update the board's outage layer
   *  immediately. The dialog and the board are siblings, so the console owns the signal between
   *  them; `DockBoardPanel` folds this into its own fetch effect. */
  const [boardReloadToken, setBoardReloadToken] = useState(0)
  /**
   * U103's picker context, owned here because entering it is a **tab switch**:
   *
   * > `screens.md` section 3: *"Selecting **Counter-offer** on a queue row switches to Board
   * > automatically, pinned to that request (U103). Everything else about tab-switching is a plain,
   * > explicit click — the surface never silently changes tabs on its own."*
   *
   * This is the one sanctioned automatic switch, and it is the reason this state cannot live in
   * `QueueTab` (which has no say over the tab) or in `DockBoardPanel` (which never sees a row).
   */
  const [picking, setPicking] = useState<PlannerQueueRow | null>(null)
  /** Bumped after a counter-offer commits, so the Queue tab re-reads rather than showing the row's
   *  pre-offer interval and a now-stale `snapshot_hash`. */
  const [queueReloadToken, setQueueReloadToken] = useState(0)

  /* ------------------------------------------------------------------------------------------
   * Flow 9 -- the sequencer proposal, owned here for the same reason `picking` is: the two
   * entry points (this toolbar's "Request re-sequence" and "Review proposal (N)") and the
   * overlay's effect on the board are three different children of this console, and no one of
   * them can see the other two.
   * ---------------------------------------------------------------------------------------- */

  /**
   * Pending runs the SERVER reports, newest first.
   *
   * Was `string[] | null` while no list endpoint existed, so the toolbar could say "unknown" rather
   * than lie with "(0)". `GET /api/v1/scheduling/runs` landed 2026-09-02, so the null case is gone:
   * an empty array now genuinely means "the server answered, and there are none".
   */
  const [pendingRunIds, setPendingRunIds] = useState<string[]>([])
  /** The run currently open in the overlay. */
  const [reviewingRunId, setReviewingRunId] = useState<string | null>(null)
  const [proposing, setProposing] = useState(false)
  const [proposeFailure, setProposeFailure] = useState<string | null>(null)
  const [activeRunId, setActiveRunId] = useState<string | null>(null)
  const [runAlreadyActive, setRunAlreadyActive] = useState(false)

  const refreshPendingRuns = useCallback(async () => {
    if (!sequencerProposalEnabled) return
    try {
      const runs = await listPendingSchedulingRuns(facilityId || null)
      setPendingRunIds(runs.map((r) => r.scheduling_run_id))
    } catch {
      // Deliberately silent and deliberately NOT cleared: this read is advisory, and a transient
      // failure must neither take the Board tab down nor retract a count the server already gave.
    }
  }, [facilityId])

  useEffect(() => {
    void refreshPendingRuns()
  }, [refreshPendingRuns])

  const onRequestResequence = useCallback(async () => {
    if (proposing) return
    setProposing(true)
    setProposeFailure(null)
    setRunAlreadyActive(false)
    try {
      // No Idempotency-Key: the route takes none, and its own docstring gives the better reason --
      // a proposal consumes no capacity, and `scheduling_runs`' partial unique index turns a
      // double-press into ONE run plus a named RUN_ALREADY_ACTIVE naming it. See
      // `lib/http.ts::plannerPostNoKey`.
      const run = await proposeFacilitySchedule({ facilityId: facilityId || null })
      if (run.code === 'RUN_ALREADY_ACTIVE') {
        // The debounce answers with a run-shaped body: `active_run` names the incumbent, and the
        // run's own id is the fallback when it does not.
        setRunAlreadyActive(true)
        const incumbent = run.active_run?.scheduling_run_id
        setActiveRunId(
          typeof incumbent === 'string' ? incumbent : (run.scheduling_run_id ?? null),
        )
        return
      }
      // Flow 9 step 1: the planner requested it, so open the review rather than making them find
      // the button that just became live.
      setReviewingRunId(run.scheduling_run_id)
      // Prepended, not appended: this is the newest run, and the list is newest-first.
      setPendingRunIds((current) => [run.scheduling_run_id, ...current])
    } catch (error) {
      setProposeFailure(formatUserFriendlyError(error))
    } finally {
      setProposing(false)
    }
  }, [proposing, facilityId])

  const queueTabRef = useRef<HTMLButtonElement | null>(null)
  const boardTabRef = useRef<HTMLButtonElement | null>(null)
  const queuePanelId = useId()
  const boardPanelId = useId()

  // accessibility.md: Cmd/Ctrl+1 / +2 switch Queue / Board -- global to this surface, registered
  // at the console root the same way AppShell's own Cmd/Ctrl+K binding is.
  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (!(e.metaKey || e.ctrlKey)) return
      if (e.key === '1') {
        e.preventDefault()
        setTab('queue')
        queueTabRef.current?.focus()
      } else if (e.key === '2') {
        e.preventDefault()
        setTab('board')
        boardTabRef.current?.focus()
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [])

  return (
    <NarrowViewportGuard>
      <div className="flex h-full min-h-0 flex-col">
        <div
          role="tablist"
          aria-label="Planner console"
          className="flex shrink-0 gap-1 border-b border-border pb-2"
          // Standard WAI-ARIA tabs arrow-key navigation. accessibility.md's own keyboard model
          // only mandates Cmd/Ctrl+1/+2 for this surface; Left/Right is added on top as the
          // ordinary role="tab" contract, not a substitute for it.
          onKeyDown={(e) => {
            if (e.key !== 'ArrowLeft' && e.key !== 'ArrowRight') return
            e.preventDefault()
            const next = tab === 'queue' ? 'board' : 'queue'
            setTab(next)
            ;(next === 'queue' ? queueTabRef : boardTabRef).current?.focus()
          }}
        >
          <TabButton
            ref={queueTabRef}
            id="queue"
            panelId={queuePanelId}
            active={tab === 'queue'}
            onSelect={() => setTab('queue')}
          >
            Queue
          </TabButton>
          <TabButton
            ref={boardTabRef}
            id="board"
            panelId={boardPanelId}
            active={tab === 'board'}
            onSelect={() => setTab('board')}
          >
            Board
          </TabButton>
        </div>

        <div
          id={queuePanelId}
          role="tabpanel"
          aria-labelledby="queue"
          hidden={tab !== 'queue'}
          className="min-h-0 flex-1 overflow-auto pt-4"
        >
          <QueueTabRegion
            facilityId={facilityId}
            externalReloadToken={queueReloadToken}
            onPickOnBoard={
              plannerBoardPickerEnabled
                ? (row) => {
                    setPicking(row)
                    setTab('board')
                    // Focus follows the switch, or a keyboard planner is left with focus on a row
                    // in a panel that is now `hidden`.
                    requestAnimationFrame(() => boardTabRef.current?.focus())
                  }
                : undefined
            }
          />
        </div>

        <div
          id={boardPanelId}
          role="tabpanel"
          aria-labelledby="board"
          hidden={tab !== 'board'}
          className="flex min-h-0 flex-1 flex-col overflow-auto pt-4"
        >
          <div className="mb-3 flex shrink-0 items-center justify-between">
            <h2 className="text-h3">Board</h2>
            <div className="flex items-center gap-3">
              <Button variant="neutral" onClick={() => setBlockDialogOpen(true)}>
                Block a dock
              </Button>
              {/* Flow 9's self-triggered origin. Sits beside Review proposal because the two are
                  the two halves of one job -- produce a proposal, then decide about it. */}
              <RequestResequenceButton
                busy={proposing}
                runAlreadyActive={runAlreadyActive}
                alreadyActiveRunId={activeRunId}
                failure={proposeFailure}
                onRequest={() => void onRequestResequence()}
                onReviewActive={
                  activeRunId ? () => setReviewingRunId(activeRunId) : undefined
                }
              />
              <ReviewProposalButton
                count={pendingRunIds.length}
                onReview={() => {
                  // Newest first: the server's own index is `created_at DESC`
                  // (`ix_scheduling_runs_facility_created`), so element 0 is the newest run.
                  const next = pendingRunIds[0] ?? null
                  if (next) setReviewingRunId(next)
                }}
              />
            </div>
          </div>

          <div className="min-h-0 flex-1">
            {dockBoardEnabled ? (
              /* `DockBoardPanel` owns its own fetch, its own skeleton (state 28) and its own
                 scoped error (state 23) -- the same shape `QueueTab` took, and for the same
                 reason: a board that renders an at-rest state without having asked the server
                 would tell a planner the lanes are clear when it has never looked. */
              <DockBoardPanel
                facilityId={facilityId || null}
                externalReloadToken={boardReloadToken}
                picking={picking}
                // Section 4: "a clean way out without committing anything". Returning to the Queue
                // undoes the automatic switch that brought them here, rather than leaving a planner
                // on a tab they never chose.
                onPickerCancel={() => {
                  setPicking(null)
                  setTab('queue')
                  requestAnimationFrame(() => queueTabRef.current?.focus())
                }}
                onPickerDone={(outcome) => {
                  setPicking(null)
                  setTab('queue')
                  if (outcome.ok) toast.success(outcome.message)
                  else toast.error(outcome.message)
                  // Section 4: "the surface returns to the Queue tab with the row updated to
                  // reflect the new proposed interval". A re-read is the only way to get that and
                  // the fresh snapshot_hash -- there is no local edit that could produce a correct
                  // hash. Bumped on refusals too: ALREADY_ACTIONED and SNAPSHOT_STALE both mean the
                  // row on screen is out of date, which is the whole reason they fired.
                  setQueueReloadToken((n) => n + 1)
                  requestAnimationFrame(() => queueTabRef.current?.focus())
                }}
              />
            ) : (
              <NotYetAvailable
                title="Dock occupancy view isn't available yet."
                body="dock_occupancy has no state column to colour the board by (issue #53) -- the same migration gap blocks the HELD promise-state. Block a dock and Review proposal both work regardless, above."
              />
            )}
          </div>
        </div>
      </div>

      <BlockDockDialog
        open={blockDialogOpen}
        onOpenChange={setBlockDialogOpen}
        facilityId={facilityId}
        onBlocked={(dockCode) => {
          toast.success(`${dockCode} blocked; affected appointments named in the response.`)
          setBoardReloadToken((n) => n + 1)
        }}
      />

      {reviewingRunId === null ? null : (
        <ProposalOverlay
          schedulingRunId={reviewingRunId}
          facilityId={facilityId || null}
          open
          onOpenChange={(next) => {
            if (!next) setReviewingRunId(null)
          }}
          onApplied={(result) => {
            toast.success('Proposal applied in full.')
            // Flow 9 step 3: the board reflects the new committed schedule. The queue reloads too
            // -- an applied run moves appointment intervals, so every row's own snapshot_hash is
            // now stale, and a confirm against a stale hash is precisely what the guard refuses.
            setBoardReloadToken((n) => n + 1)
            setQueueReloadToken((n) => n + 1)
            setPendingRunIds((current) =>
              current.filter((id) => id !== result.scheduling_run_id),
            )
            setActiveRunId(null)
            setRunAlreadyActive(false)
          }}
          onRequestFresh={() => {
            // `edge-cases.md` section 5: drift's fix is a NEW proposal. The drifted run is dropped
            // from the pending set first, so the toolbar cannot offer it again.
            setPendingRunIds((current) => current.filter((id) => id !== reviewingRunId))
            void onRequestResequence()
          }}
        />
      )}
    </NarrowViewportGuard>
  )
}

/**
 * The flag gates the **fetch**, not a rendered state.
 *
 * That ordering is the whole point of this wrapper and it is worth stating, because the previous
 * shape of this function was a live trap: with the flag on it rendered `QueueEmptyCaughtUp`
 * unconditionally, so flipping it would have told a planner "no pending requests" without the
 * surface ever having asked the server -- strictly worse than an honest stub, because a stub does
 * not claim to know anything. `QueueTab` now owns its own fetch, so its empty state can only ever
 * be reached *after* a successful read that genuinely returned nothing.
 */
function QueueTabRegion({
  facilityId,
  externalReloadToken,
  onPickOnBoard,
}: {
  facilityId: string
  externalReloadToken?: number
  onPickOnBoard?: (row: PlannerQueueRow) => void
}) {
  if (!plannerQueueLiveEnabled) {
    return (
      <NotYetAvailable
        title="Live queue isn't available yet."
        body="Turn on plannerQueueLiveEnabled once GET /api/v1/planner/queue is reachable from this identity. The block-dock group on the Board tab works today regardless."
      />
    )
  }
  return (
    <QueueTab
      facilityId={facilityId || null}
      externalReloadToken={externalReloadToken}
      onPickOnBoard={onPickOnBoard}
    />
  )
}

const TabButton = ({
  id,
  panelId,
  active,
  onSelect,
  children,
  ref,
}: {
  id: string
  panelId: string
  active: boolean
  onSelect: () => void
  children: ReactNode
  ref: Ref<HTMLButtonElement>
}) => (
  <button
    ref={ref}
    id={id}
    type="button"
    role="tab"
    aria-selected={active}
    aria-controls={panelId}
    tabIndex={active ? 0 : -1}
    onClick={onSelect}
    className={
      active
        ? 'rounded-md bg-info-bg px-3 py-1.5 text-supporting font-semibold text-primary'
        : 'rounded-md px-3 py-1.5 text-supporting font-semibold text-muted-foreground hover:bg-hover'
    }
  >
    {children}
  </button>
)
