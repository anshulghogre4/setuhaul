import { Hexagon } from 'lucide-react'
import { useEffect, useState } from 'react'

import { Skeleton } from '@/shared/ui/skeleton'
import { copy } from '../lib/copy'

/**
 * Screen 11A — assistant thinking (`flows-and-states.md`, "Assistant thinking").
 *
 * Two timings, both from the design and both load-bearing on a 3G roadside connection:
 *
 * - **400ms before anything appears.** A fast reply makes the indicator flash distractingly, so
 *   the indicator is not the response to a request — it is the response to a request that is
 *   taking a noticeable amount of time.
 * - **8 seconds -> "Still working on this…".** A driver at a roadside with no feedback assumes
 *   the app is broken. This is the cheapest possible defence against that.
 *
 * Driven by the SSE `status` frame (`{ tool: name }`, emitted *before* execution), which is why
 * the driver is not staring at nothing during section 1.2's buffer-until-`done` window.
 *
 * Under `prefers-reduced-motion` the dots become a **static label**, not nothing
 * (`motion.md`). Done with a CSS media query in the component rather than a JS `matchMedia`
 * read: `matchMedia` in a render is a second source of truth for a preference the stylesheet
 * already knows, and E5.0 removed exactly that pattern from the shared shell.
 */
export function ThinkingIndicator({ startedAtMs, nowMs }: { startedAtMs: number; nowMs: number }) {
  const elapsed = nowMs - startedAtMs
  const [visible, setVisible] = useState(false)

  useEffect(() => {
    // A real timer rather than a derived `elapsed > 400`, because the shared clock only ticks
    // once per second -- deriving it would make the threshold anywhere from 400ms to 1400ms.
    const id = window.setTimeout(() => setVisible(true), 400)
    return () => window.clearTimeout(id)
  }, [startedAtMs])

  if (!visible) return null

  return (
    <div role="listitem" className="flex flex-col items-start">
      <p className="mb-1 flex items-center gap-1.5 text-body text-muted-foreground">
        <Hexagon size={14} strokeWidth={2} aria-hidden="true" />
        SetuHaul assistant
      </p>
      <div className="rounded-lg border border-border bg-card px-4 py-3">
        {/* The dots are decoration; the label under them is the signal. `motion-reduce:hidden`
            and `motion-reduce:block` are Tailwind's own prefers-reduced-motion variants, so the
            swap is a stylesheet fact, not a JS branch. */}
        <span className="flex gap-1 motion-reduce:hidden" aria-hidden="true">
          <Dot delayMs={0} />
          <Dot delayMs={160} />
          <Dot delayMs={320} />
        </span>
        <span className="hidden text-body text-muted-foreground motion-reduce:block">
          {copy.thinkingReducedMotion}
        </span>
        {/* Announced once, politely: a driver using a screen reader while a turn is in flight
            should hear that something is happening, not a per-frame stream. */}
        <span role="status" className="sr-only">
          {copy.thinkingReducedMotion}
        </span>
      </div>
      {elapsed > 8000 ? (
        <p className="mt-1 text-body text-muted-foreground" role="status">
          {copy.thinkingStillWorking}
        </p>
      ) : null}
    </div>
  )
}

function Dot({ delayMs }: { delayMs: number }) {
  return (
    <span
      data-motion="decorative"
      className="size-2 animate-shim rounded-full bg-subtle-foreground"
      style={{ animationDelay: `${delayMs}ms` }}
    />
  )
}

/** Screen 11B — transcript skeleton, **3 alternating bubble shapes** so it reads as a
 *  conversation loading rather than a form. `animate-shim` (1600ms ease-in-out), never
 *  `animate-pulse`, per `motion.md` as the motion authority. */
export function TranscriptSkeleton() {
  return (
    <div className="space-y-4 p-4" aria-hidden="true">
      <Skeleton className="h-16 w-[70%]" />
      <Skeleton className="ml-auto h-12 w-[55%]" />
      <Skeleton className="h-20 w-[80%]" />
    </div>
  )
}

/** Screen 2 — thread-list skeleton. Cards shaped like the **final layout**, not generic bars
 *  (`components.md` section 13): a skeleton whose shape differs from what arrives is a second
 *  layout shift. */
export function ThreadListSkeleton({ count = 3 }: { count?: number }) {
  return (
    <div className="space-y-3 p-4" aria-hidden="true">
      {Array.from({ length: count }, (_, i) => (
        <Skeleton key={i} className="h-28 w-full rounded-lg" />
      ))}
    </div>
  )
}
