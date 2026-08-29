import { useEffect, useId, useRef, useState, type ReactNode, type Ref } from 'react'
import { toast } from 'sonner'

import { BlockDockDialog } from './components/block-dock-dialog'
import { BoardSkeleton } from './components/board-skeleton'
import { NarrowViewportGuard } from './components/narrow-viewport'
import { NotYetAvailable } from './components/not-yet-available'
import { QueueEmptyCaughtUp } from './components/queue-region-states'
import { ReviewProposalButton } from './components/review-proposal-button'
import { dockBoardEnabled, plannerQueueLiveEnabled } from './lib/flags'
import { RegionError } from '@/components/states/region-states'
import { Button } from '@/shared/ui/button'

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
 * **Real backend wiring for the block-dock group only** (states 16-18) -- the one group with a
 * complete backend this pass (`implementation-spec.md` section 0.1). Everything else on this
 * surface starts from a queue row `get_planner_queue` (issue #60) would produce, and that tool
 * does not exist -- see `lib/flags.ts`'s header comment for why every other flag defaults off.
 */
export function PlannerConsole({ facilityId }: { facilityId: string }) {
  const [tab, setTab] = useState<Tab>('queue')
  const [blockDialogOpen, setBlockDialogOpen] = useState(false)
  const [boardLoadError, setBoardLoadError] = useState(false)

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
          <QueueTab />
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
              <ReviewProposalButton />
            </div>
          </div>

          <div className="min-h-0 flex-1">
            {boardLoadError ? (
              <RegionError regionName="dock board" onRetry={() => setBoardLoadError(false)} />
            ) : dockBoardEnabled ? (
              <BoardSkeleton />
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
        onBlocked={(dockCode) => toast.success(`${dockCode} blocked; affected appointments named in the response.`)}
      />
    </NarrowViewportGuard>
  )
}

function QueueTab() {
  // `plannerQueueLiveEnabled` gates the fetch itself, not just a rendered state -- there is
  // nothing to attempt against `get_planner_queue` (issue #60) yet, so a skeleton would falsely
  // imply a request is in flight. States 27/29/30 (skeleton, load-failed/out-of-scope,
  // below-1024px) remain real, reusable components -- exercised in the gallery -- for the day the
  // fetch this tab needs actually exists.
  if (!plannerQueueLiveEnabled) {
    return (
      <NotYetAvailable
        title="Live queue isn't available yet."
        body="get_planner_queue doesn't exist in the shape section 7.5.1 needs (issue #60), and there's no live-update transport for it either (issue #59). The block-dock group on the Board tab works today regardless."
      />
    )
  }
  // Unreachable until #60/#59 land -- kept as the documented shape this branch takes, matching
  // `QueueEmptyCaughtUp`'s own real component rather than an inline placeholder.
  return <QueueEmptyCaughtUp />
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
