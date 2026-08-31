import { useCallback, useEffect, useRef } from 'react'
import { atom, useSetAtom } from 'jotai'

/**
 * The product's live-update transport, issue #59 -- **polling, decided by the owner** over SSE and
 * WebSocket, and the reasoning is recorded here rather than only in a commit message because the
 * next person to read this file will otherwise re-open it.
 *
 * The ops queue and the planner queue are **multi-viewer** problems (several coordinators on one
 * facility's queue). The only stream that exists in this product today is the driver `/chat` SSE
 * turn stream, which is single-consumer by construction -- extending it would mean real rework of
 * its race semantics, not a config change. At this product's stated scale (5 concurrent operators)
 * a poll is sufficient, adds no infrastructure to deploy, monitor or secure, and reverts by
 * flipping one flag per surface. If usage later justifies a push transport, the surfaces consume
 * `onData` and would not need to change shape.
 *
 * ## What this hook deliberately does NOT do
 *
 * It does not merge, sort, or apply anything. It fetches on a schedule and hands the payload to
 * `onData`. **U19's frozen sort is the caller's job**, because only the caller knows whether a row
 * has focus -- and getting that wrong (re-sorting under a planner mid-decision) is the specific
 * harm U19 exists to prevent. See `features/planner/lib/live-queue.ts` and
 * `features/ops/lib/live-queue.ts` for the two merges.
 *
 * ## Interval: 15s, and it is a judgement call, not a design citation
 *
 * No design file names a number -- `stitch-prompts.md` says "synced 4s ago" as artboard copy, not
 * as a policy. 15s is chosen because `SOLUTION_DESIGN.md` section 7.3's whole thesis for the
 * planner queue is a **30-second decision** per row: an arrivals signal that can be a full
 * decision-cycle stale is not a live signal, and one refreshed twice per decision is. The ops
 * console's own clocks are minutes-scale (SLA budgets), so the same number is comfortably inside
 * its tolerance too. At 5 operators across both queues that is ~0.33 requests/second aggregate,
 * which is not a load question at this scale.
 *
 * ## Visibility: a hidden tab does not poll at all
 *
 * `document.visibilityState === 'hidden'` stops the loop; `visibilitychange` back to `visible`
 * fetches immediately. This is MDN's own named use case for the Page Visibility API ("an
 * application showing a dashboard of information doesn't want to poll the server for updates when
 * the page isn't visible"), and it is preferred over `blur`/`focus`, which MDN calls imperfect
 * proxies -- a window that lost focus is often still visible on a second monitor, and a
 * coordinator watching a queue on a second monitor should keep getting updates.
 *
 * A slower background poll was considered and rejected as dishonest: Chrome applies *intensive
 * throttling* to `setTimeout`/`setInterval` in a tab hidden for over 5 minutes, checking timers
 * roughly once per minute (Chrome 88 timer-throttling release note). A "30-second background
 * poll" would therefore silently become a ~60-second one, so the code would claim a cadence the
 * browser does not honour. Stopping, and re-syncing on return, is the behaviour we can actually
 * promise.
 *
 * ## Failure: exponential backoff, capped, with jitter
 *
 * `backoffDelayMs` below. Jitter matters even here, where a herd is five clients rather than five
 * thousand: without it, every console that lost the API at the same moment retries in lockstep
 * forever, so the server sees its whole client population arrive in one spike on every attempt.
 *
 * ## `navigator.onLine` is used as a LABEL, never as a gate
 *
 * MDN is explicit that `onLine` is unreliable and "should not be used to disable features" -- a
 * LAN with no internet, a VPN, or a virtual adapter all report online, and Windows determines the
 * value by reaching a Microsoft host that a firewall may block. So an `offline` event changes what
 * the status bar *says* and nothing else; the poll keeps running on its own schedule and the real
 * verdict comes from whether the fetch succeeded. An `online` event triggers an immediate retry,
 * which is a hint used in the safe direction.
 */

export type PollStatus = 'idle' | 'connected' | 'syncing' | 'sync-failed' | 'offline'

export type PollHealth = {
  /** `idle` means no surface is polling -- the status bar falls back to its props. */
  status: PollStatus
  lastSuccessAtMs: number | null
  lastFailureAtMs: number | null
  consecutiveFailures: number
  /** Whatever the polling surface counts as "pending". `null` = unknown, which the status bar
   *  renders as "—" rather than "0" (`02-ops-exception-console/stitch-prompts.md`: "unknown and
   *  zero must never look the same"). */
  pendingCount: number | null
}

export const IDLE_POLL_HEALTH: PollHealth = {
  status: 'idle',
  lastSuccessAtMs: null,
  lastFailureAtMs: null,
  consecutiveFailures: 0,
  pendingCount: null,
}

/**
 * Provider-less by design. Jotai v2 has a module-scoped default store used whenever no `<Provider>`
 * is present, which is this app's situation (`providers.tsx` mounts theme + countdown only, and is
 * outside this epic's ownership). `features/driver/lib/store.ts` already uses atoms exactly this
 * way, so this is the established pattern here rather than a new one.
 *
 * One atom, last writer wins: only one polling surface is mounted at a time, and each resets to
 * `IDLE_POLL_HEALTH` on unmount so the next surface never inherits the previous one's health.
 */
export const pollHealthAtom = atom<PollHealth>(IDLE_POLL_HEALTH)

/**
 * The re-sort key for both live queues -- the "press <key>" half of `stitch-prompts.md`'s
 * "N new . press R" affordance.
 *
 * **It is `S`, not `R`, and that is a deliberate departure from the artboard copy.**
 * `03-planner-dock-board/accessibility.md`'s keyboard table binds `R` to **Reject** on the focused
 * queue row, while `03-planner-dock-board/stitch-prompts.md` section 4 (and State 9's pin line, and
 * `02-ops-exception-console/stitch-prompts.md` prompt 3) write the affordance as "press R to
 * re-sort". Both are the design's own words and they collide on the same tab; the collision only
 * became live when re-sort became real (issue #59).
 *
 * `R` stays with Reject: the AT matrix is the surface's own authority on key bindings, and Reject
 * is one of five single-key affordances carrying a 30-second decision, where re-sort also has a
 * real clickable pill. `S` is unbound on both surfaces and reads as "sort".
 *
 * **Flagged for the owner** -- the alternative is to move Reject and give `R` back to re-sort. Kept
 * as one constant so that decision is a one-line change.
 */
export const RESORT_KEY = 's'
export const RESORT_KEY_LABEL = 'S'

export const DEFAULT_POLL_INTERVAL_MS = 15_000
export const MAX_POLL_BACKOFF_MS = 120_000

/**
 * Equal jitter: half the capped delay, plus a random half. Full jitter (`random() * capped`) is
 * the other standard choice and was rejected here for one concrete reason -- it can return ~0ms,
 * which on the first failure produces an immediate retry against a server that just failed, and
 * at a 15s base the herd this protects against is five clients, so the extra spread buys nothing
 * worth that.
 */
export function backoffDelayMs(
  baseMs: number,
  consecutiveFailures: number,
  random: () => number = Math.random,
): number {
  if (consecutiveFailures <= 0) return baseMs
  const capped = Math.min(baseMs * 2 ** consecutiveFailures, MAX_POLL_BACKOFF_MS)
  return Math.round(capped / 2 + random() * (capped / 2))
}

/** "09:52:14" while healthy, "6m ago" once a sync has failed -- the two forms `StatusBar`'s own
 *  `lastSync` prop has always documented. Absolute while connected on purpose: a relative label
 *  would need a 1Hz tick to stay honest, and a status bar that re-renders every second to move one
 *  digit is a cost with no reader. */
export function formatLastSync(health: PollHealth, nowMs: number = Date.now()): string {
  if (health.lastSuccessAtMs === null) return '—'
  if (health.status === 'connected' || health.status === 'syncing') {
    return new Date(health.lastSuccessAtMs).toLocaleTimeString('en-GB', { hour12: false })
  }
  const ageMin = Math.floor((nowMs - health.lastSuccessAtMs) / 60_000)
  if (ageMin < 1) return 'under a minute ago'
  return `${ageMin}m ago`
}

export type LivePollOptions<T> = {
  /** The surface's own feature flag, plus anything else that makes polling meaningless. */
  enabled: boolean
  intervalMs?: number
  /**
   * **Skips a tick without counting it as a failure.** This is constraint 3 of issue #59: a poll
   * must not land underneath a coordinator mid-takeover or a planner mid-confirm. The caller
   * passes `true` while any write is in flight or any decision dialog is open; the loop simply
   * re-arms and the next tick reads post-write state, which is what the write's own reload
   * already produced.
   */
  paused?: boolean
  fetcher: () => Promise<T>
  onData: (data: T) => void
  onError?: (err: unknown) => void
  /** Surfaced in the status bar. `undefined` leaves whatever is there; `null` means unknown. */
  pendingCount?: number | null
}

export type LivePoll = {
  /** Fetch now and restart the interval from now. Safe to call while a fetch is in flight -- the
   *  call is dropped rather than queued, since two overlapping reads of the same queue can only
   *  disagree. */
  refreshNow: () => void
}

export function useLivePoll<T>(opts: LivePollOptions<T>): LivePoll {
  const { enabled, intervalMs = DEFAULT_POLL_INTERVAL_MS, paused = false, pendingCount } = opts

  const setHealth = useSetAtom(pollHealthAtom)

  // Latest-value refs so a re-render with a new inline closure does not tear down and restart the
  // polling loop -- a loop that restarts on every parent render never actually reaches its
  // interval, which is the classic way a "15s poll" silently becomes a request per keystroke.
  const fetcherRef = useRef(opts.fetcher)
  const onDataRef = useRef(opts.onData)
  const onErrorRef = useRef(opts.onError)
  fetcherRef.current = opts.fetcher
  onDataRef.current = opts.onData
  onErrorRef.current = opts.onError

  const pausedRef = useRef(paused)
  pausedRef.current = paused
  const intervalRef = useRef(intervalMs)
  intervalRef.current = intervalMs
  const enabledRef = useRef(enabled)
  enabledRef.current = enabled

  const timerRef = useRef<number | null>(null)
  const inFlightRef = useRef(false)
  const failuresRef = useRef(0)
  /** Bumped on unmount and on every `enabled` change, so a response that arrives after the loop
   *  was torn down is discarded instead of writing into an unmounted tree's state. */
  const generationRef = useRef(0)

  const clearTimer = useCallback(() => {
    if (timerRef.current !== null) {
      window.clearTimeout(timerRef.current)
      timerRef.current = null
    }
  }, [])

  const runRef = useRef<() => void>(() => {})

  const schedule = useCallback(
    (delayMs: number) => {
      clearTimer()
      timerRef.current = window.setTimeout(() => runRef.current(), delayMs)
    },
    [clearTimer],
  )

  useEffect(() => {
    runRef.current = () => {
      if (!enabledRef.current) return
      // A hidden tab does not re-arm at all; `visibilitychange` restarts the loop. See the header.
      if (typeof document !== 'undefined' && document.visibilityState === 'hidden') return
      if (pausedRef.current || inFlightRef.current) {
        schedule(intervalRef.current)
        return
      }

      const generation = generationRef.current
      inFlightRef.current = true

      void fetcherRef.current()
        .then((data) => {
          if (generation !== generationRef.current) return
          failuresRef.current = 0
          onDataRef.current(data)
          setHealth((prev) => ({
            ...prev,
            status: 'connected',
            lastSuccessAtMs: Date.now(),
            consecutiveFailures: 0,
          }))
        })
        .catch((err: unknown) => {
          if (generation !== generationRef.current) return
          failuresRef.current += 1
          onErrorRef.current?.(err)
          setHealth((prev) => ({
            ...prev,
            // `navigator.onLine` labels only; the fetch failing is the actual verdict. See header.
            status: typeof navigator !== 'undefined' && !navigator.onLine ? 'offline' : 'sync-failed',
            lastFailureAtMs: Date.now(),
            consecutiveFailures: failuresRef.current,
          }))
        })
        .finally(() => {
          if (generation !== generationRef.current) return
          inFlightRef.current = false
          schedule(backoffDelayMs(intervalRef.current, failuresRef.current))
        })
    }
  }, [schedule, setHealth])

  useEffect(() => {
    generationRef.current += 1
    if (!enabled) {
      clearTimer()
      setHealth(IDLE_POLL_HEALTH)
      return
    }

    // First read happens on the interval, not immediately: every caller already loads once on
    // mount through its own effect, and firing here too would double every page load.
    schedule(intervalMs)

    function onVisibility() {
      if (document.visibilityState === 'visible') {
        // Straight back on return rather than waiting out an interval -- a coordinator who
        // switches back to the tab is exactly the person who needs current data now.
        runRef.current()
      } else {
        clearTimer()
      }
    }
    function onOnline() {
      setHealth((prev) => ({ ...prev, status: prev.lastSuccessAtMs ? 'connected' : prev.status }))
      runRef.current()
    }
    function onOffline() {
      setHealth((prev) => ({ ...prev, status: 'offline' }))
    }

    document.addEventListener('visibilitychange', onVisibility)
    window.addEventListener('online', onOnline)
    window.addEventListener('offline', onOffline)

    return () => {
      generationRef.current += 1
      clearTimer()
      document.removeEventListener('visibilitychange', onVisibility)
      window.removeEventListener('online', onOnline)
      window.removeEventListener('offline', onOffline)
      setHealth(IDLE_POLL_HEALTH)
    }
  }, [enabled, intervalMs, schedule, clearTimer, setHealth])

  useEffect(() => {
    if (pendingCount === undefined) return
    setHealth((prev) => (prev.pendingCount === pendingCount ? prev : { ...prev, pendingCount }))
  }, [pendingCount, setHealth])

  const refreshNow = useCallback(() => {
    clearTimer()
    runRef.current()
  }, [clearTimer])

  return { refreshNow }
}
