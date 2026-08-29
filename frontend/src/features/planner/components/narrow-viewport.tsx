import { useEffect, useState, type ReactNode } from 'react'
import { Monitor } from 'lucide-react'

import { EmptyState } from '@/shared/ui/empty-state'

/**
 * State 30 -- `screens.md` section 1 / `stitch-prompts.md` section 12, item 8. **Not a squeezed
 * table**: a plain full-region statement, no responsive fallback layout, no horizontal-scroll
 * mini table. `spacing-and-layout.md`'s surface table gives Planner 1280px+; below 1024px is out
 * of support entirely (the 1024-1280px reduced-column band has no artboard of its own -- Fork D,
 * `implementation-spec.md` section 6 -- and is not attempted here).
 *
 * Content-region only, matching `RegionError`/`NotFound` (`components/states/region-states.tsx`)
 * -- the shell itself never unmounts (U71).
 */
export function NarrowViewportGuard({ children }: { children: ReactNode }) {
  const [narrow, setNarrow] = useState(() => window.innerWidth < 1024)

  useEffect(() => {
    const onResize = () => setNarrow(window.innerWidth < 1024)
    window.addEventListener('resize', onResize)
    return () => window.removeEventListener('resize', onResize)
  }, [])

  if (narrow) {
    return (
      <EmptyState
        icon={Monitor}
        title="The planner console needs a screen at least 1024px wide."
        body="Seven fields and a 30-second decision don't survive a phone screen."
      />
    )
  }
  return children
}
