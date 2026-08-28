/**
 * Driver-surface formatting. **`Intl` with `en-IN`, from the start.**
 *
 * `01-driver-chat/accessibility.md` ("Language and i18n readiness", U31) and
 * `00-foundations/data-formatting.md` both require this — not `date-fns`'s `format`, which is
 * installed but is for *arithmetic* here, not presentation. Hardcoding "Tue 4 Aug" would make
 * the Hindi translation a code change instead of a locale change.
 *
 * Every formatter is built once at module scope. `Intl.DateTimeFormat` construction is the
 * expensive part; on the cheap Android this surface targets, rebuilding one per render inside
 * a transcript of 50 messages is measurable.
 */

const LOCALE = 'en-IN'

/**
 * Facility-local, not device-local (U64).
 *
 * Every driver-facing time is the *facility's* wall clock: a driver whose phone is on a
 * different timezone must not be shown a slot time that does not match the sign at the gate.
 * `Asia/Kolkata` is the only facility timezone in the seeded data
 * (`facilities.timezone`), but it is threaded as a parameter rather than baked in, because
 * `facilities` genuinely carries the column and a second-region facility would otherwise
 * silently render wrong.
 */
export const DEFAULT_FACILITY_TZ = 'Asia/Kolkata'

function timeFormatter(timeZone: string) {
  return new Intl.DateTimeFormat(LOCALE, {
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
    timeZone,
  })
}

function dayFormatter(timeZone: string) {
  return new Intl.DateTimeFormat(LOCALE, {
    weekday: 'short',
    day: 'numeric',
    month: 'short',
    timeZone,
  })
}

/**
 * `Tue 4 Aug` — space-separated, **no comma**.
 *
 * `voice-and-tone.md`'s mechanics specify exactly `Tue 4 Aug`, but `en-IN` with
 * `{weekday:'short', day:'numeric', month:'short'}` renders `Tue, 4 Aug`. Found by measuring the
 * render, not by reading the format options. The comma also made the option card's accessible
 * name read *"Dock D4, Tue, 4 Aug, 12:15 to 13:30"* — three commas where the label wants a clean
 * three-part list.
 *
 * Fixed with `formatToParts` rather than a `.replace(', ', ' ')`: the parts API keeps the
 * locale's own weekday/month names and its own field ORDER (which is what a translation to Hindi
 * needs) and only drops the machine-generated literal separators. A regex over the formatted
 * string would break the moment a locale used a different separator.
 */
function joinDateParts(parts: Intl.DateTimeFormatPart[]): string {
  return parts
    .filter((p) => p.type !== 'literal')
    .map((p) => p.value)
    .join(' ')
}

const cache = new Map<string, { time: Intl.DateTimeFormat; day: Intl.DateTimeFormat }>()

function formatters(timeZone: string) {
  let hit = cache.get(timeZone)
  if (!hit) {
    hit = { time: timeFormatter(timeZone), day: dayFormatter(timeZone) }
    cache.set(timeZone, hit)
  }
  return hit
}

/** `13:00`. 24-hour, because a driver reading `1:00` at a roadside has to work out am/pm. */
export function formatTime(iso: string, timeZone = DEFAULT_FACILITY_TZ): string {
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return ''
  return formatters(timeZone).time.format(d)
}

/** `Tue 4 Aug`. */
export function formatDay(iso: string, timeZone = DEFAULT_FACILITY_TZ): string {
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return ''
  return joinDateParts(formatters(timeZone).day.formatToParts(d))
}

/**
 * `12:15 – 13:30`. **En dash, not a hyphen** (`data-formatting.md`), and the caller renders it
 * in `--font-data` with `tabular-nums` so the two halves do not shift width as the digits
 * change.
 */
export function formatRange(
  startIso: string,
  endIso: string,
  timeZone = DEFAULT_FACILITY_TZ,
): string {
  const start = formatTime(startIso, timeZone)
  const end = formatTime(endIso, timeZone)
  if (!start || !end) return ''
  return `${start} – ${end}`
}

/**
 * `Dock D4 · Tue 4 Aug` — dock and date, **never separable** (`screens.md` section 4).
 *
 * `slotLocalDate` is a bare `YYYY-MM-DD`, so it is parsed as a local calendar date rather than
 * pushed through the timezone formatter a second time: it has *already* been converted
 * facility-side. Re-applying a zone to a date-only string is how a card ends up one day out.
 */
export function formatDockAndDate(dockCode: string, slotLocalDate: string): string {
  const label = formatLocalDate(slotLocalDate)
  return label ? `Dock ${dockCode} · ${label}` : `Dock ${dockCode}`
}

/** `Tue 4 Aug` from a bare `YYYY-MM-DD`. */
export function formatLocalDate(ymd: string): string {
  const parts = /^(\d{4})-(\d{2})-(\d{2})$/.exec(ymd)
  if (!parts) return ''
  // Constructed at local noon deliberately: midnight UTC of a `YYYY-MM-DD` can land on the
  // previous day for negative offsets, which is the same class of off-by-one-day bug
  // `slot_local_date` exists to remove.
  const d = new Date(Number(parts[1]), Number(parts[2]) - 1, Number(parts[3]), 12)
  return joinDateParts(
    new Intl.DateTimeFormat(LOCALE, {
      weekday: 'short',
      day: 'numeric',
      month: 'short',
    }).formatToParts(d),
  )
}

/**
 * Relative under an hour ("9m ago"), absolute above ("09:41") — `screens.md` section 1 and the
 * *Timestamps* checklist row.
 *
 * `Intl.RelativeTimeFormat` rather than a hand-rolled "Xm ago", same U31 reason as above.
 */
const relative = new Intl.RelativeTimeFormat(LOCALE, { numeric: 'auto', style: 'narrow' })

export function formatMessageTimestamp(
  iso: string,
  nowMs: number,
  timeZone = DEFAULT_FACILITY_TZ,
): string {
  const then = Date.parse(iso)
  if (Number.isNaN(then)) return ''
  const deltaMs = nowMs - then
  if (deltaMs < 60_000) return 'just now'
  if (deltaMs < 3_600_000) return relative.format(-Math.floor(deltaMs / 60_000), 'minute')
  return formatTime(iso, timeZone)
}

/**
 * The countdown's spoken form — words, not the glyph string
 * (`01-driver-chat/accessibility.md`, "Screen reader": *"Held. One minute twenty-four seconds
 * remaining."*). `1:24` read aloud by a screen reader is "one colon twenty-four".
 *
 * Deliberately a small hand-written table rather than `Intl.NumberFormat` with
 * `style: 'unit'`: that produces "1 min, 24 sec", which is a different sentence from the one
 * the accessibility file specifies, and this string is the promise a low-vision driver acts on.
 */
export function spokenRemaining(remainingMs: number): string {
  const total = Math.max(0, Math.round(remainingMs / 1000))
  const mins = Math.floor(total / 60)
  const secs = total % 60
  const bits: string[] = []
  if (mins > 0) bits.push(`${mins} ${mins === 1 ? 'minute' : 'minutes'}`)
  if (secs > 0) bits.push(`${secs} ${secs === 1 ? 'second' : 'seconds'}`)
  // At zero the spoken form is "expired", not "no time remaining" -- caught by reading the
  // rendered accessible name, which came out as "Pending confirmation. no time." Nothing
  // remains, so nothing should claim to.
  if (bits.length === 0) return 'expired'
  return `${bits.join(' ')} remaining`
}

/** `14,500 / 25,000 kg` — grouped per `en-IN`, which uses lakh grouping above 5 digits.
 *  That is the correct grouping for this audience and is exactly why it goes through `Intl`. */
const integer = new Intl.NumberFormat(LOCALE, { maximumFractionDigits: 0 })

export function formatKg(value: number): string {
  return `${integer.format(value)} kg`
}
