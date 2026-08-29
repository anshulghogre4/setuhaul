import { CircleCheckBig, Inbox, SearchX } from 'lucide-react'

import { Button } from '@/shared/ui/button'
import { EmptyState } from '@/shared/ui/empty-state'
import { Skeleton } from '@/shared/ui/skeleton'

/**
 * `stitch-prompts.md` section 12, states 26-27 (`implementation-spec.md` table B, both 🟢 --
 * buildable regardless of `plannerQueueLiveEnabled`, since they are structural/negative states
 * independent of what `get_planner_queue` (issue #60) would return).
 *
 * **These two empty states must never share an icon or copy** (`stitch-prompts.md` section 12,
 * item 2) -- the same visual emptiness means two opposite things, and showing the wrong one makes
 * a working system look broken.
 */
export function QueueEmptyCaughtUp() {
  return (
    <EmptyState
      icon={CircleCheckBig}
      title="No pending requests."
      body="New ones appear here automatically."
    />
  )
}

export function QueueEmptyNothingYet() {
  return (
    <EmptyState
      icon={Inbox}
      title="This facility has no requests yet."
      body="Once shipments start arriving, they'll show up here."
    />
  )
}

export function QueueSearchEmpty({ query, onClear }: { query: string; onClear: () => void }) {
  return (
    <EmptyState
      icon={SearchX}
      title={`No shipment matches '${query}'.`}
      actions={
        <Button variant="neutral" onClick={onClear}>
          Clear search
        </Button>
      }
    />
  )
}

/**
 * State 27. **Not a centred spinner.** The real 36px table rows hold their exact height and
 * column widths, shimmering rather than a layout jump when real data arrives
 * (`stitch-prompts.md` section 12, item 4). The shell -- rail, top bar, status bar -- already
 * never unmounts (U71, `AppShell`); this is the content-region half of that rule.
 */
export function QueueSkeleton() {
  return (
    <div aria-busy="true" aria-label="Loading queue" className="flex flex-col gap-px">
      {Array.from({ length: 8 }).map((_, i) => (
        <div key={i} className="flex h-9 items-center gap-3 border-b border-border px-3">
          <Skeleton className="size-4 shrink-0 rounded-sm" />
          <Skeleton className="h-3.5 w-32 shrink-0" />
          <Skeleton className="h-3.5 w-28 shrink-0" />
          <Skeleton className="h-3.5 flex-1" />
          <Skeleton className="h-3.5 w-16 shrink-0" />
          <Skeleton className="h-3.5 w-12 shrink-0" />
        </div>
      ))}
    </div>
  )
}
