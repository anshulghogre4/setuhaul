import { CircleCheckBig, Inbox, Settings } from 'lucide-react'
import { useAtom, useAtomValue } from 'jotai'
import { useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'

import { Button } from '@/shared/ui/button'
import { EmptyState } from '@/shared/ui/empty-state'
import { copy } from '../lib/copy'
import { emptyKind, fetchDriverContext, toThreads } from '../lib/data'
import { orderedThreadsAtom, threadsAtom } from '../lib/store'
import { ThreadCard } from '../components/thread-card'
import { ThreadListSkeleton } from '../components/thinking'

/**
 * Screens 1, 2, 3A, 3B — the thread list (home).
 *
 * One card per active exception thread, resolved threads muted below. **This is where section
 * 7.2b's disambiguation ladder is solved structurally**: a driver with two loads picks the right
 * one *before* typing, rather than the assistant guessing from context and burning a
 * clarification turn (section 13.1 counts those as a cost).
 *
 * ## Ordering lives in the store, not here
 *
 * `orderedThreadsAtom` sorts running-TTL first (soonest deadline), then recency, then resolved.
 * Doing it there rather than at render time means the DOM order a screen reader walks and the
 * visual order are the same list — see the atom's own comment.
 *
 * ## Not `ThreadListPrimitive`, and why — a deviation from the design, recorded
 *
 * `implementation-spec.md` section 1.3 binds this screen to assistant-ui's
 * `ThreadListPrimitive` / `ThreadListItemPrimitive`. Checked against the **installed**
 * `@assistant-ui/react@0.15.16`: reaching them requires
 * `ExternalStoreAdapter.adapters.threadList`, whose own type declaration marks `threadId`,
 * `onSwitchToThread` and `onSwitchToNewThread` **`@deprecated — This API is still under active
 * development and might change without notice`**. Meanwhile everything this screen actually
 * renders is ours regardless: the ordering (section 1.3 says so explicitly), the promise chip,
 * the countdown, the priority marker and the unread treatment. So the primitive would contribute
 * a list wrapper and take an unstable API dependency for it. A plain `role="list"` of real
 * `<Link>`s gives better keyboard and screen-reader behaviour with no such dependency.
 *
 * **The architectural property U56/U48 exists to protect is untouched** — option sets and
 * eligibility answers still render from typed tool results with a fixed renderer per tool, never
 * from parsed text (see `transcript.tsx`). Flagged to the owner as the one genuine deviation
 * from section 1's wiring rather than presented as equivalent.
 *
 * ## Single-thread shortcut
 *
 * Exactly one active thread and no resolved history -> land directly in the conversation. The
 * list is navigation, and navigating a list of one is friction. **Back from that conversation
 * still reveals the list**, so the model stays consistent: it is a launch shortcut, not a
 * different information architecture.
 */
export function DriverThreadList() {
  const [, setThreads] = useAtom(threadsAtom)
  const ordered = useAtomValue(orderedThreadsAtom)
  const navigate = useNavigate()
  const [phase, setPhase] = useState<'loading' | 'ready' | 'error'>('loading')
  const [empty, setEmpty] = useState<'caught-up' | 'nothing-yet' | 'has-threads'>('has-threads')

  useEffect(() => {
    let cancelled = false
    void (async () => {
      try {
        const ctx = await fetchDriverContext()
        if (cancelled) return
        const threads = toThreads(ctx)
        setThreads(threads)
        setEmpty(emptyKind(ctx))
        setPhase('ready')

        const active = threads.filter((t) => !t.resolved)
        if (active.length === 1 && threads.length === 1) {
          navigate(`/driver/t/${active[0].threadId}`, { replace: true })
        }
      } catch {
        if (!cancelled) setPhase('error')
      }
    })()
    return () => {
      cancelled = true
    }
  }, [navigate, setThreads])

  const active = ordered.filter((t) => !t.resolved)
  const resolved = ordered.filter((t) => t.resolved)

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <header className="flex min-h-14 shrink-0 items-center justify-between gap-3 border-b border-border bg-card px-4">
        <h1 className="text-h2">SetuHaul</h1>
        {/* 48x48, not a 24px glyph: R8 measured the equivalent control at 18x6.9 against its own
            stated floor. `aria-label` because it is icon-only chrome, not driver-facing content
            (iconography.md forbids icon-only CONTROLS on this surface; the settings entry point
            is chrome and carries a label for AT). */}
        <Link
          to="/driver/profile"
          aria-label={copy.navProfile}
          className="grid size-12 place-items-center rounded-md text-muted-foreground focus-visible:outline-2 focus-visible:outline-ring focus-visible:outline-offset-2"
        >
          <Settings size={20} strokeWidth={2} aria-hidden="true" />
        </Link>
      </header>

      <div className="min-h-0 flex-1 overflow-y-auto overscroll-contain">
        {/* Screen 2: skeleton cards shaped like the final layout. */}
        {phase === 'loading' ? <ThreadListSkeleton /> : null}

        {/* Screen 27C's sibling for the list: names the cause and gives one action (U32). */}
        {phase === 'error' ? (
          <EmptyState
            icon={Inbox}
            title={copy.threadLoadFailedTitle}
            body={copy.threadLoadFailedBody}
            actions={
              <Button variant="neutral" onClick={() => window.location.reload()}>
                {copy.retryAction}
              </Button>
            }
          />
        ) : null}

        {phase === 'ready' && empty === 'caught-up' ? (
          // Screen 3A. **No CTA** (U74) -- this is a good state, and a button here would imply
          // the driver has something to fix.
          <EmptyState
            icon={CircleCheckBig}
            title={copy.emptyCaughtUpTitle}
            body={copy.emptyCaughtUpBody}
          />
        ) : null}

        {phase === 'ready' && empty === 'nothing-yet' ? (
          // Screen 3B. Distinct icon AND distinct copy from 3A -- `inbox` reads "not set up",
          // `circle-check-big` reads "you're done", and one icon for both would undercut the
          // whole point of U74.
          <EmptyState
            icon={Inbox}
            title={copy.emptyNothingYetTitle}
            body={copy.emptyNothingYetBody}
          />
        ) : null}

        {phase === 'ready' && empty === 'has-threads' ? (
          <>
            <ul role="list" className="flex flex-col gap-3 p-4">
              {active.map((thread) => (
                <ThreadCard key={thread.threadId} thread={thread} />
              ))}
            </ul>

            {resolved.length > 0 ? (
              <>
                {/* A labelled separator, not a bare rule: resolved cards keep their state chip
                    because the card is the record of what was agreed. */}
                <h2 className="flex items-center gap-3 px-4 pt-2 text-body text-subtle-foreground">
                  <span aria-hidden="true" className="h-px flex-1 bg-border" />
                  {copy.resolvedDivider}
                  <span aria-hidden="true" className="h-px flex-1 bg-border" />
                </h2>
                <ul role="list" className="flex flex-col gap-3 p-4">
                  {resolved.map((thread) => (
                    <ThreadCard key={thread.threadId} thread={thread} />
                  ))}
                </ul>
              </>
            ) : null}
          </>
        ) : null}
      </div>
    </div>
  )
}
