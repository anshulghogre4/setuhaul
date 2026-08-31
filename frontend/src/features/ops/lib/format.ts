/**
 * Time rendering for the thread transcript, per `00-foundations/data-formatting.md`.
 *
 * `02-ops-exception-console/components.md` section 3 settles which model applies here -- a
 * `checklist-design` Chat audit flagged thread timestamps as inherited-by-assumption, and that
 * file resolves it explicitly: "follow `data-formatting.md`'s counting-up relative-time bands
 * ('Just now,' 'N minutes ago,' absolute date past 24h), same as every other chat surface in this
 * product. No surface-specific deviation."
 *
 * The bands, verbatim from that table:
 *   < 60s   -> "Just now"  (never "12 seconds ago", never milliseconds)
 *   1-59min -> "N minutes ago"
 *   1-23hr  -> "N hours ago"
 *   >= 24hr -> absolute date
 *
 * Built on `Intl.RelativeTimeFormat`, which that file requires by name ("via
 * `Intl.RelativeTimeFormat`, never raw seconds").
 */

const LOCALE = 'en-IN'

const relative = new Intl.RelativeTimeFormat(LOCALE, { numeric: 'auto' })

/** 24-hour, per `screens.md` section 3b's composer rule ("24-hour time if a time is entered") and
 *  the product-wide operational-time convention. `hourCycle: 'h23'` rather than `hour12: false`,
 *  because the latter still yields "24:05" for midnight in some ICU versions. */
const absoluteDate = new Intl.DateTimeFormat(LOCALE, {
  day: 'numeric',
  month: 'short',
  hour: '2-digit',
  minute: '2-digit',
  hourCycle: 'h23',
})

const clockTime = new Intl.DateTimeFormat(LOCALE, {
  hour: '2-digit',
  minute: '2-digit',
  hourCycle: 'h23',
})

/** The wall-clock time shown beside a message ("09:41" in `screens.md` section 3). Always
 *  rendered, so a coordinator reading a transcript for a record has the exact time, while the
 *  relative band below carries the at-a-glance recency. */
export function messageClock(iso: string): string {
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return iso
  return clockTime.format(d)
}

/** The relative band. `now` is injectable so this is testable and so a re-render does not depend
 *  on a hidden clock read. */
export function relativeTime(iso: string, now: number = Date.now()): string {
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return iso
  const elapsedMs = now - d.getTime()

  // Future timestamps (clock skew between the server and this browser) fall through to the
  // absolute date rather than rendering "in 3 minutes", which would read as a scheduling claim.
  if (elapsedMs < 0) return absoluteDate.format(d)

  const seconds = Math.floor(elapsedMs / 1000)
  if (seconds < 60) return 'Just now'

  const minutes = Math.floor(seconds / 60)
  if (minutes < 60) return relative.format(-minutes, 'minute')

  const hours = Math.floor(minutes / 60)
  if (hours < 24) return relative.format(-hours, 'hour')

  return absoluteDate.format(d)
}
