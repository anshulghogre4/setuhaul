import { ArrowDown } from 'lucide-react'

import { cn } from '@/shared/lib/utils'
import { copy } from '../lib/copy'

/**
 * Screen 11C — the scroll-to-latest pill (`flows-and-states.md`, "Scroll to latest").
 *
 * Three rules, and the first is the one both chat checklists call the common bug:
 *
 * 1. **The transcript never auto-scrolls while the driver is reading history.** New content
 *    arriving must not yank the view. Owned by the caller (`transcript.tsx`), which is the only
 *    place that knows the scroll position — this component is the escape hatch, not the policy.
 * 2. Appears only when scrolled **more than one screen** from the bottom. A pill that appears
 *    after 40px of scroll is noise.
 * 3. **Counts messages, not events.** A card mutating in place (U50) does not increment it —
 *    nothing new arrived, something existing changed, and offering to scroll to it would be
 *    wrong.
 */
export function ScrollToLatest({
  newCount,
  onClick,
}: {
  newCount: number
  onClick: () => void
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        'absolute bottom-3 left-1/2 -translate-x-1/2',
        'z-sticky flex min-h-11 items-center gap-2 rounded-full px-4',
        'border border-floating-border bg-popover shadow-floating',
        'text-body',
        'focus-visible:outline-2 focus-visible:outline-ring focus-visible:outline-offset-2',
      )}
    >
      <ArrowDown size={16} strokeWidth={2} aria-hidden="true" />
      {newCount > 0 ? copy.scrollToLatest(newCount) : 'Latest'}
    </button>
  )
}
