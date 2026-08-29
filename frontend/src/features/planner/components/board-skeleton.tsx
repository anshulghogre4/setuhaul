import { Skeleton } from '@/shared/ui/skeleton'

/**
 * State 28 (`implementation-spec.md` table C, 🟢 -- ships regardless of `dockBoardEnabled`).
 * "Shaped like lanes, not rows" (`stitch-prompts.md` section 12, item 5): the dock-label column
 * and lane tracks render at their real dimensions with the shimmer over them -- a different shape
 * from `QueueSkeleton`, per that same item's "each destination gets a skeleton matching its own
 * final layout; never one generic loader for both tabs."
 */
export function BoardSkeleton() {
  return (
    <div aria-busy="true" aria-label="Loading dock board" className="flex flex-col gap-px">
      {Array.from({ length: 6 }).map((_, i) => (
        <div key={i} className="flex h-11 items-center gap-3 border-b border-border px-3">
          <Skeleton className="h-4 w-10 shrink-0" />
          <Skeleton className="h-6 flex-1" />
        </div>
      ))}
    </div>
  )
}
