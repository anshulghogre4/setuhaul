import { createContext, use, useEffect, useMemo, useRef, useState, type ReactNode } from 'react'

/**
 * ONE shared 1 Hz interval for every countdown in the app -- components.md section 3.
 *
 * 35 pending rows must not run 35 timers.  This lives in E5.0 rather than the planner epic
 * because every surface needs it: the driver's HELD chip, the planner queue's TTLs, the ops
 * console's SLA remaining.
 *
 * Two things this deliberately does, both correctness rather than tidiness:
 *
 *  1. It computes from **server** time with a measured offset, never from `Date.now()`
 *     alone.  A client clock that is three minutes fast would show a hold as already
 *     expired, or worse, show 90 seconds left on a hold the server already released.  The
 *     server's `expires_at` is authoritative; the offset is how we read it honestly.
 *
 *  2. Offline it **holds at last-known value** rather than free-running (auth-and-scoping.md
 *     section "Driver offline behaviour").  A ticking countdown against a clock we can no
 *     longer reconcile is a confident lie.
 */

type CountdownContextValue = {
  /** Monotonically increasing tick, once per second.  Subscribe by reading it. */
  now: number
  /** serverNow - clientNow, in ms.  Zero until a response has been observed. */
  offsetMs: number
  setServerTime: (serverIsoOrEpochMs: string | number) => void
  /** When false the tick freezes -- see (2) above. */
  live: boolean
  setLive: (live: boolean) => void
}

const CountdownContext = createContext<CountdownContextValue | null>(null)

export function CountdownProvider({ children }: { children: ReactNode }) {
  const [now, setNow] = useState(() => Date.now())
  const [offsetMs, setOffsetMs] = useState(0)
  const [live, setLive] = useState(true)
  const offsetRef = useRef(0)

  useEffect(() => {
    if (!live) return
    const id = window.setInterval(() => setNow(Date.now()), 1000)
    return () => window.clearInterval(id)
  }, [live])

  const value = useMemo<CountdownContextValue>(
    () => ({
      now,
      offsetMs,
      live,
      setLive,
      setServerTime: (serverIsoOrEpochMs) => {
        const server =
          typeof serverIsoOrEpochMs === 'number'
            ? serverIsoOrEpochMs
            : Date.parse(serverIsoOrEpochMs)
        if (Number.isNaN(server)) return
        const next = server - Date.now()
        // Only re-render on a meaningful drift change; a 5ms jitter every response would
        // otherwise re-render every countdown in the app.
        if (Math.abs(next - offsetRef.current) > 1000) {
          offsetRef.current = next
          setOffsetMs(next)
        }
      },
    }),
    [now, offsetMs, live],
  )

  return <CountdownContext value={value}>{children}</CountdownContext>
}

export function useCountdownClock(): CountdownContextValue {
  const ctx = use(CountdownContext)
  if (!ctx) throw new Error('useCountdownClock must be used inside <CountdownProvider>')
  return ctx
}

export type CountdownReading = {
  /** Milliseconds left, floored at zero. */
  remainingMs: number
  /** "1:24" / "0:09".  Always mono + tabular-nums at the render site. */
  label: string
  expired: boolean
  /** Announcement thresholds -- accessibility-behaviour.md throttles the live region to
   *  50%, 20%, 10s and expiry.  A per-second live region is unusable. */
  threshold: 'none' | 'half' | 'fifth' | 'ten-seconds' | 'expired'
  /** Whether the countdown is trustworthy right now.  False offline, where the reading
   *  holds instead of ticking. */
  live: boolean
}

export function useCountdown(expiresAtIso: string, totalMs?: number): CountdownReading {
  const { now, offsetMs, live } = useCountdownClock()
  const expiresAt = Date.parse(expiresAtIso)

  return useMemo(() => {
    const serverNow = now + offsetMs
    const remainingMs = Math.max(0, expiresAt - serverNow)
    const total = totalMs ?? 0
    const mins = Math.floor(remainingMs / 60000)
    const secs = Math.floor((remainingMs % 60000) / 1000)

    let threshold: CountdownReading['threshold'] = 'none'
    if (remainingMs <= 0) threshold = 'expired'
    else if (remainingMs <= 10_000) threshold = 'ten-seconds'
    else if (total > 0 && remainingMs <= total * 0.2) threshold = 'fifth'
    else if (total > 0 && remainingMs <= total * 0.5) threshold = 'half'

    return {
      remainingMs,
      label: `${mins}:${String(secs).padStart(2, '0')}`,
      expired: remainingMs <= 0,
      threshold,
      live,
    }
  }, [now, offsetMs, expiresAt, totalMs, live])
}
