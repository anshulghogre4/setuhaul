import { cn } from '@/shared/lib/utils'

/**
 * Re-authored from shadcn's default, which shipped `animate-pulse bg-accent`.
 *
 * Two corrections, both from locked decisions rather than taste:
 *
 *  - **`animate-shim`, not `animate-pulse`.**  Tailwind's built-in runs 2000ms on
 *    `cubic-bezier(0.4,0,0.6,1)`; motion.md's inventory specifies 1600ms `ease-in-out`, and
 *    motion.md is the motion authority, so it wins over U78's original text.  Do not reach
 *    for the built-in because its class name is shorter.
 *  - **`bg-skeleton`, not `bg-accent`.**  `accent` is shadcn's menu-hover role; the skeleton
 *    has its own token in color.md.
 *
 * `data-motion="decorative"` opts this into the reduced-motion rule.  The shimmer is genuine
 * decoration -- the signal "this is loading, not empty" survives without it -- unlike the
 * HELD pulse or the TTL warming, which carry information and are handled per-motion instead.
 */
function Skeleton({ className, ...props }: React.ComponentProps<'div'>) {
  return (
    <div
      data-slot="skeleton"
      data-motion="decorative"
      className={cn('animate-shim rounded-md bg-skeleton', className)}
      {...props}
    />
  )
}

export { Skeleton }
