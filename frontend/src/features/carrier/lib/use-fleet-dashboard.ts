import { useCallback, useEffect, useRef, useState } from 'react'

import {
  fetchFleetExceptions,
  fetchFleetOverview,
  fetchFleetShipments,
  fetchOnTimePerformance,
} from './api'
import type {
  FleetExceptionList,
  FleetOverview,
  FleetShipmentList,
  OnTimePerformance,
} from './types'

/**
 * The dashboard's data layer — `flows-and-states.md` Flow 1 and Flow 5, `edge-cases.md` #4,
 * `stitch-prompts.md` §5's latency bands.
 *
 * ## Four calls, four independently-resolving sections
 *
 * `get_fleet_overview`, `get_carrier_on_time_performance`, `list_fleet_shipments` and
 * `list_fleet_exceptions` are fired together and each section renders **the moment its own data
 * arrives** — the shipments table is never blocked waiting on the overview, or vice versa. Every
 * request carries its own error, so one failing region cannot take the others down. That is why
 * this hook keeps a separate result/error pair per section rather than one `Promise.all` and one
 * status flag.
 *
 * The on-time tile is the one section that waits on two calls, and only partly: the headline
 * percentage renders from `get_fleet_overview` alone, while the sparkline waits on
 * `get_carrier_on_time_performance`. If that second call never arrives the sparkline is **simply
 * not there** — no error, no placeholder, no retry (`stitch-prompts.md` §7 variant (b):
 * secondary content disappears silently rather than competing with the fleet list).
 *
 * ## The latency bands, which decide whether anything appears at all
 *
 * - **under 1s in flight: show nothing.** An indicator that flashes for under a second is pure
 *   distraction.
 * - **1–3s:** per-section skeletons at the exact dimensions of the content they replace.
 * - **past ~3s:** the skeleton is joined by a `Retry` rather than pulsing indefinitely.
 *
 * ## Refresh is manual, and a re-fetch is not a first load
 *
 * There is no live-updating region and no auto-refresh anywhere on this surface. On a manual
 * refresh the previous render is **held at 0.6 opacity** rather than skeleton-flashed — and only
 * once the request has been in flight for a second. If the refresh fails outright, the
 * previously-loaded data stays on screen and `staleSince` drives the one page-level stale notice
 * (`edge-cases.md` #4: the "last updated" timestamp is the carrier's signal for the page as a
 * whole, not a per-section guarantee).
 *
 * ## Why sequence numbers and not `AbortController`
 *
 * A filter change fires while the first load's overview may still be in flight. Aborting the
 * previous request set would cancel that overview and leave the tile permanently empty, since
 * a filter change deliberately does **not** re-request it (Flow 2). So each section carries its
 * own monotonic sequence and a late response for an older sequence is discarded — the same
 * protection against out-of-order responses, without cancelling calls the new request never
 * intended to replace. Requests are still aborted on unmount, which is the one case where
 * cancelling is unambiguously right.
 */

const SKELETON_AFTER_MS = 1000
const STALLED_AFTER_MS = 3000

export type SectionState<T> = {
  data: T | null
  /** Truthy only for a genuine failure of THIS section. */
  failed: boolean
}

type Sections = { overview?: boolean; shipments?: boolean; exceptions?: boolean }

const ALL_SECTIONS: Sections = { overview: true, shipments: true, exceptions: true }

export type FleetDashboardState = {
  overview: SectionState<FleetOverview>
  shipments: SectionState<FleetShipmentList>
  exceptions: SectionState<FleetExceptionList>
  /** No `failed` flag by design: a failed trend series renders as absence, not as an error. */
  performance: OnTimePerformance | null

  /** Server-supplied `as_of` of the newest successful load, for the "last updated" line. */
  lastUpdated: string | null
  /** Set when a refresh failed outright while previously-loaded data is still on screen. */
  staleSince: string | null

  /** True until something has resolved successfully at least once. */
  firstLoad: boolean
  /** In flight AND has been for at least a second. */
  showLoading: boolean
  /** In flight for more than ~3s — the band that adds a Retry beside the skeleton. */
  stalled: boolean

  statusFilter: string | null
  setStatusFilter: (value: string | null) => void
  refresh: () => void
  retryShipments: () => void
  retryExceptions: () => void
}

export function useFleetDashboard(): FleetDashboardState {
  const [overview, setOverview] = useState<SectionState<FleetOverview>>({
    data: null,
    failed: false,
  })
  const [shipments, setShipments] = useState<SectionState<FleetShipmentList>>({
    data: null,
    failed: false,
  })
  const [exceptions, setExceptions] = useState<SectionState<FleetExceptionList>>({
    data: null,
    failed: false,
  })
  const [performance, setPerformance] = useState<OnTimePerformance | null>(null)

  const [statusFilter, setStatusFilterState] = useState<string | null>(null)
  const [lastUpdated, setLastUpdated] = useState<string | null>(null)
  const [staleSince, setStaleSince] = useState<string | null>(null)
  const [inFlight, setInFlight] = useState(0)
  const [showLoading, setShowLoading] = useState(false)
  const [stalled, setStalled] = useState(false)

  const seq = useRef({ overview: 0, performance: 0, shipments: 0, exceptions: 0 })
  const lastUpdatedRef = useRef<string | null>(null)
  const loadedOnceRef = useRef(false)
  const abortRef = useRef<AbortController | null>(null)

  const load = useCallback(async (filter: string | null, sections: Sections = ALL_SECTIONS) => {
    const ac = new AbortController()
    abortRef.current = ac
    setInFlight((n) => n + 1)

    let anySucceeded = false
    let anyFailed = false
    let newestAsOf: string | null = null
    const note = (asOf: string) => {
      anySucceeded = true
      if (!newestAsOf || asOf > newestAsOf) newestAsOf = asOf
    }

    const jobs: Promise<unknown>[] = []

    if (sections.overview) {
      const mine = ++seq.current.overview
      jobs.push(
        fetchFleetOverview(ac.signal)
          .then((data) => {
            if (mine !== seq.current.overview) return
            setOverview({ data, failed: false })
            note(data.as_of)
          })
          .catch(() => {
            if (mine !== seq.current.overview || ac.signal.aborted) return
            anyFailed = true
            setOverview((prev) => ({ data: prev.data, failed: true }))
          }),
      )

      const minePerf = ++seq.current.performance
      jobs.push(
        fetchOnTimePerformance(ac.signal)
          .then((data) => {
            if (minePerf === seq.current.performance) setPerformance(data)
          })
          .catch(() => {
            // Secondary content: no error surface at all, and no `anyFailed`. The sparkline
            // simply is not there, and nothing on the page mentions it.
            if (minePerf === seq.current.performance && !ac.signal.aborted) setPerformance(null)
          }),
      )
    }

    if (sections.shipments) {
      const mine = ++seq.current.shipments
      jobs.push(
        fetchFleetShipments(filter, ac.signal)
          .then((data) => {
            if (mine !== seq.current.shipments) return
            setShipments({ data, failed: false })
            note(data.as_of)
          })
          .catch(() => {
            if (mine !== seq.current.shipments || ac.signal.aborted) return
            anyFailed = true
            setShipments((prev) => ({ data: prev.data, failed: true }))
          }),
      )
    }

    if (sections.exceptions) {
      const mine = ++seq.current.exceptions
      jobs.push(
        fetchFleetExceptions(ac.signal)
          .then((data) => {
            if (mine !== seq.current.exceptions) return
            setExceptions({ data, failed: false })
            note(data.as_of)
          })
          .catch(() => {
            if (mine !== seq.current.exceptions || ac.signal.aborted) return
            anyFailed = true
            setExceptions((prev) => ({ data: prev.data, failed: true }))
          }),
      )
    }

    try {
      await Promise.all(jobs)
    } finally {
      setInFlight((n) => Math.max(0, n - 1))
    }
    if (ac.signal.aborted) return

    const hadDataBefore = loadedOnceRef.current
    if (anySucceeded) {
      loadedOnceRef.current = true
      lastUpdatedRef.current = newestAsOf
      setLastUpdated(newestAsOf)
    }
    // Staleness is specifically "a refresh failed and you are looking at older numbers". A
    // first load that fails is a section error, not staleness -- there is nothing stale to warn
    // about when nothing was ever loaded. And a partial success is not staleness either: the
    // failing section shows its own error, and one notice per region is exactly what §7's
    // "one notice, not five" rules out.
    setStaleSince(hadDataBefore && anyFailed && !anySucceeded ? lastUpdatedRef.current : null)
  }, [])

  useEffect(() => {
    void load(null)
    const ac = abortRef.current
    return () => ac?.abort()
    // Deliberately once. `load` has no reactive dependencies (every mutable value it reads is a
    // ref), so this cannot go stale.
  }, [load])

  // The latency bands. Timers rather than an indicator that appears instantly, because the rule
  // is that nothing at all renders under a second.
  useEffect(() => {
    if (inFlight === 0) {
      setShowLoading(false)
      setStalled(false)
      return
    }
    const a = window.setTimeout(() => setShowLoading(true), SKELETON_AFTER_MS)
    const b = window.setTimeout(() => setStalled(true), STALLED_AFTER_MS)
    return () => {
      window.clearTimeout(a)
      window.clearTimeout(b)
    }
  }, [inFlight])

  const setStatusFilter = useCallback(
    (value: string | null) => {
      setStatusFilterState(value)
      // Flow 2: filtering "never re-fetches the on-time/exception-count tiles, which reflect the
      // whole fleet regardless of the shipment list's current filter".
      void load(value, { shipments: true })
    },
    [load],
  )

  const refresh = useCallback(() => {
    void load(statusFilter)
  }, [load, statusFilter])

  const retryShipments = useCallback(() => {
    void load(statusFilter, { shipments: true })
  }, [load, statusFilter])

  const retryExceptions = useCallback(() => {
    void load(statusFilter, { exceptions: true })
  }, [load, statusFilter])

  return {
    overview,
    shipments,
    exceptions,
    performance,
    lastUpdated,
    staleSince,
    firstLoad: !loadedOnceRef.current,
    showLoading: showLoading && inFlight > 0,
    stalled: stalled && inFlight > 0,
    statusFilter,
    setStatusFilter,
    refresh,
    retryShipments,
    retryExceptions,
  }
}
