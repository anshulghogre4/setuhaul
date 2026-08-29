/**
 * Every date, time and number on this surface goes through here.
 *
 * `05-carrier-portal/implementation-spec.md` §4.2 marks hardcoded timestamps as the one
 * unfixed finding it hands to the build ("`Intl` with `en-IN` from the first component, not
 * retrofitted"), and `stitch-prompts.md` §8 makes three of the rules below non-negotiable
 * rather than stylistic.
 *
 * ## The four locked formatting rules, and how each is enforced here
 *
 * 1. **24-hour clock always** (`13:00`, never `1:00 PM`). Enforced with `hourCycle: 'h23'`
 *    rather than `hour12: false`. Both are documented to produce the 00-23 cycle — MDN's
 *    `Intl.DateTimeFormat()` page states `hour12: false` "sets `hourCycle` to `h23`" — but
 *    `h23` says the thing directly and cannot be re-derived by a locale's own `hc` extension.
 *    (Checked against MDN this session rather than recalled: `hour12` overrides both the `hc`
 *    tag and an explicit `hourCycle`, so the two must never be passed together. They are not.)
 * 2. **Dates carry their weekday** (`Tue 20 Aug`) — an option set can span two days and a bare
 *    date is a wrong-day arrival waiting to happen.
 * 3. **Ranges use an en dash** (`13:00–14:15`), never a hyphen.
 * 4. **Times are the FACILITY's local time, never converted to the viewer's.**
 *
 * ### The honest caveat on rule 4
 *
 * `public.facilities.timezone` exists (baseline migration line 30, `DEFAULT 'Asia/Kolkata'`)
 * but **§7.5.6's payloads never return it** — neither `list_fleet_shipments` nor
 * `get_shipment_detail` selects it. So this module pins `Asia/Kolkata` explicitly, which is
 * correct for every facility this product has today and is strictly better than the
 * alternative (omitting `timeZone`, which silently uses the *viewer's* zone and would break
 * rule 4 outright for a dispatcher travelling). If a facility outside IST is ever added, the
 * endpoint has to start returning `facility.timezone` and this constant becomes a parameter.
 * Recorded as a known limit, not left as an accident.
 */

/** See the caveat above. One constant so a future per-facility zone has one place to land. */
export const FACILITY_TIME_ZONE = 'Asia/Kolkata'

const LOCALE = 'en-IN'

/** `13:00` */
const timeFmt = new Intl.DateTimeFormat(LOCALE, {
  hour: '2-digit',
  minute: '2-digit',
  hourCycle: 'h23',
  timeZone: FACILITY_TIME_ZONE,
})

// NOTE: there is deliberately no seconds-bearing time formatter here. The only place the design
// asks for one is `HELD`'s `Held for the driver until 11:42:30.` -- and no §7.5.6 payload carries
// a hold expiry to put in it (see `types.ts`). Adding the formatter would leave a helper standing
// for a capability this surface does not have.

/**
 * `Tue 20 Aug`.
 *
 * **Assembled from `formatToParts`, not from `format`, and that is a measured correction rather
 * than a preference.** Rendered in headless Chromium, `format()` with these options produces
 * `Thu, 20 Aug` under `en-IN` — the locale's own literal comma after the weekday. The design
 * pins this string exactly (`stitch-prompts.md` §8's dock line, `screens.md` §2's wireframe), and
 * the comma also collides visually with the middot separators the dock line already uses to group
 * its four facts as one unit. So the parts are read and the locale's literal separators dropped,
 * keeping the locale's own weekday/month **names** and numbering while pinning the layout the
 * design fixed.
 */
const dateParts = new Intl.DateTimeFormat(LOCALE, {
  weekday: 'short',
  day: 'numeric',
  month: 'short',
  timeZone: FACILITY_TIME_ZONE,
})

function formatDateParts(d: Date): string {
  const parts = dateParts.formatToParts(d)
  const get = (type: Intl.DateTimeFormatPartTypes) => parts.find((p) => p.type === type)?.value ?? ''
  return `${get('weekday')} ${get('day')} ${get('month')}`.trim()
}

const relativeFmt = new Intl.RelativeTimeFormat(LOCALE, { numeric: 'auto' })

function parse(iso: string | null | undefined): Date | null {
  if (!iso) return null
  const d = new Date(iso)
  return Number.isNaN(d.getTime()) ? null : d
}

export function formatTime(iso: string | null | undefined): string | null {
  const d = parse(iso)
  return d ? timeFmt.format(d) : null
}

export function formatDate(iso: string | null | undefined): string | null {
  const d = parse(iso)
  return d ? formatDateParts(d) : null
}

/**
 * `Jaipur · D5 · Tue 20 Aug · 13:00–14:15` — **mandatory in this exact shape**
 * (`stitch-prompts.md` §8: "an operational time never appears without its dock and its date").
 *
 * Returns `null` rather than a partial line when there is no slot at all: a shipment with no
 * current appointment has no dock, no date and no interval, and half a line would read as data
 * loss. Where the dock itself is genuinely absent but the interval is not (`dock_code` is a
 * `LEFT JOIN` and can be null on its own) the dock segment renders as `—`, matching the table's
 * own treatment of an absent dock — an explicit dash, never a blank.
 */
export function formatDockLine(input: {
  facilityName: string | null | undefined
  dockCode: string | null | undefined
  slotStart: string | null | undefined
  slotEnd: string | null | undefined
}): string | null {
  const start = parse(input.slotStart)
  if (!start || !input.facilityName) return null

  const end = parse(input.slotEnd)
  // U+2013 EN DASH. Never a hyphen — `data-formatting.md`, restated by prompt 8.
  const interval = end ? `${timeFmt.format(start)}–${timeFmt.format(end)}` : timeFmt.format(start)
  return [input.facilityName, input.dockCode || '—', formatDateParts(start), interval].join(' · ')
}

/**
 * `2 minutes ago` for the "last updated" line.
 *
 * `Intl.RelativeTimeFormat` rather than a hand-rolled ladder, and `numeric: 'auto'` so a
 * zero-minute delta reads "now" instead of "in 0 minutes".
 */
export function formatRelative(iso: string | null | undefined, now: number = Date.now()): string | null {
  const d = parse(iso)
  if (!d) return null
  // Negative = in the past, which is the only direction this line ever points.
  const deltaSec = Math.round((d.getTime() - now) / 1000)
  const abs = Math.abs(deltaSec)
  // Under a minute lands on 0 deliberately: `numeric: 'auto'` renders that as "this minute"
  // rather than "in 0 minutes", which is the readable answer for a freshly-loaded page.
  if (abs < 3600) return relativeFmt.format(Math.trunc(deltaSec / 60), 'minute')
  if (abs < 86400) return relativeFmt.format(Math.trunc(deltaSec / 3600), 'hour')
  return relativeFmt.format(Math.trunc(deltaSec / 86400), 'day')
}

/**
 * Percentages. A genuine `0` renders as `0%`; an unknown renders as `—`.
 *
 * Those are different facts and `stitch-prompts.md` §6 makes the distinction a correctness
 * requirement, not a copy nit ("no dashes or blanks where a real zero exists, and no zeros
 * where a value is genuinely unknown"). `carrier_reads._percent` already returns `None` rather
 * than `0.0` for "nothing to measure", so the two arrive here already distinguished.
 */
export function formatPercent(value: number | null | undefined): string {
  if (value === null || value === undefined) return '—'
  return `${Number.isInteger(value) ? value : value.toFixed(1)}%`
}

/** A count. Always the digit, never a blank — a real zero is a fact. */
export function formatCount(value: number | null | undefined): string {
  return value === null || value === undefined ? '—' : String(value)
}

/**
 * Mid-truncation for machine identifiers: `SH-2026-0819-00…17`, never `SH-2026-08…`.
 *
 * `data-formatting.md`'s rule, restated in `edge-cases.md` #6 and `stitch-prompts.md` §3: the
 * *distinguishing suffix* has to survive, an ellipsis stands for three or more removed
 * characters, and at least four characters always remain. Below that threshold the value is
 * returned untouched — truncating a short id would remove information for no gain.
 */
export function midTruncate(value: string, max = 18): string {
  if (value.length <= max) return value
  // 1 char for the ellipsis; the remainder split so the tail keeps the distinguishing suffix.
  const keep = max - 1
  if (keep < 4) return value
  const tail = Math.max(2, Math.floor(keep / 3))
  const head = keep - tail
  if (value.length - head - tail < 3) return value
  return `${value.slice(0, head)}…${value.slice(value.length - tail)}`
}

/** End-truncation is CSS's job (`text-overflow: ellipsis`) for names — identity is at the start,
 *  so the browser's own clipping is correct and stays selection- and search-friendly. This
 *  helper only answers "does this need a title tooltip?", which CSS cannot tell the markup. */
export function needsTitle(value: string | null | undefined, softMax: number): boolean {
  return Boolean(value && value.length > softMax)
}
