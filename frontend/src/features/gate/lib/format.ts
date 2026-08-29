/**
 * Gate/yard formatting.
 *
 * **`Intl`, not hardcoded strings.** `mockup.html` renders every time and duration as a literal
 * ("Tue 4 Aug", "18:04", "1h 22m") and `implementation-spec.md` section 5.3 records that as a
 * *build* requirement rather than a board defect -- this is where it gets paid. `data-formatting.md`
 * is the source for the en dash, the space between number and unit, and the never-pluralised unit
 * symbol.
 *
 * Deliberately a small surface-local file rather than an import from `features/driver/lib/format`:
 * each surface owns its own lib copy in this codebase (same reason `facility-names.ts` is
 * duplicated), and two of the formatters below -- dwell and the overrun minute count -- are
 * specific to this surface's own copy rules and have no driver equivalent.
 */

const LOCALE = 'en-IN'

/**
 * Facility-local, not device-local. A gate officer's clock has to match the sign at the gate and
 * the appointment the planner booked; a kiosk whose OS timezone drifted must not render a
 * different wall clock from the shipment record. `Asia/Kolkata` is the only value in seeded
 * `facilities.timezone`, but it is a parameter for the same reason the driver surface made it one.
 */
export const DEFAULT_FACILITY_TZ = 'Asia/Kolkata'

const timeFmt = new Map<string, Intl.DateTimeFormat>()
const dayFmt = new Map<string, Intl.DateTimeFormat>()

function timeFormatter(timeZone: string): Intl.DateTimeFormat {
  let hit = timeFmt.get(timeZone)
  if (!hit) {
    hit = new Intl.DateTimeFormat(LOCALE, {
      hour: '2-digit',
      minute: '2-digit',
      hour12: false,
      timeZone,
    })
    timeFmt.set(timeZone, hit)
  }
  return hit
}

function dayFormatter(timeZone: string): Intl.DateTimeFormat {
  let hit = dayFmt.get(timeZone)
  if (!hit) {
    hit = new Intl.DateTimeFormat(LOCALE, {
      weekday: 'short',
      day: 'numeric',
      month: 'short',
      timeZone,
    })
    dayFmt.set(timeZone, hit)
  }
  return hit
}

/**
 * `Tue 4 Aug`, not `Tue, 4 Aug`.
 *
 * Same `formatToParts` technique the driver surface arrived at by measuring a real render:
 * `en-IN` inserts a comma literal the specified copy does not have, and dropping only the
 * machine-generated literals keeps the locale's own field ORDER intact for a future translation.
 * A `.replace(', ', ' ')` would break on the first locale with a different separator.
 */
function joinDateParts(parts: Intl.DateTimeFormatPart[]): string {
  return parts
    .filter((p) => p.type !== 'literal')
    .map((p) => p.value)
    .join(' ')
}

/** `18:04`. 24-hour throughout this surface (`mockup.html` screen 15's own note). */
export function clockTime(iso: string | null | undefined, timeZone = DEFAULT_FACILITY_TZ): string {
  if (!iso) return ''
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return ''
  return timeFormatter(timeZone).format(d)
}

/** `Tue 4 Aug`. */
export function calendarDay(iso: string | null | undefined, timeZone = DEFAULT_FACILITY_TZ): string {
  if (!iso) return ''
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return ''
  return joinDateParts(dayFormatter(timeZone).formatToParts(d))
}

/**
 * `18:00` en-dash `19:00`. **En dash, never a hyphen** (`data-formatting.md`); the caller renders
 * it in `font-mono` with tabular numerals so the halves do not shift as the digits change.
 */
export function clockRange(
  startIso: string,
  endIso: string,
  timeZone = DEFAULT_FACILITY_TZ,
): string {
  const a = clockTime(startIso, timeZone)
  const b = clockTime(endIso, timeZone)
  if (!a || !b) return ''
  return a + '–' + b
}

/**
 * `22 min`. Space between number and unit, unit symbol never pluralised (`data-formatting.md`,
 * restated in `mockup.html` screen 18's own note). Rounded to whole minutes: the backend returns a
 * float to two decimals (`overrun_min`, `actual_unload_min`), and "21.83 min over expected" is not
 * a fact an officer standing at a dock does anything with.
 */
export function minutesText(min: number): string {
  // The separator below is U+00A0, matching the mockup's own `22&nbsp;min` / `60&nbsp;min` /
  // `82&nbsp;min`. Still a space, so `data-formatting.md`'s rule holds; a non-breaking one so a
  // wrapping outcome headline cannot split a measurement across two lines.
  return Math.round(min) + ' min'
}

/**
 * `1h 22m`, taken verbatim from `edge-cases.md` #6 and rendered on screens 12 and 16. The space is
 * U+00A0, matching the mockup's own `1h&nbsp;22m` at both render sites -- the value must never
 * wrap between its halves.
 *
 * **This format is a known open item, not a settled rule.** `mockup.html`'s own closing notes flag
 * that it contradicts `data-formatting.md`'s "space between number and unit" (which would give
 * "1 h 22 min") and that no grammar for absolute compound durations is defined anywhere -- that
 * file covers countdowns (`M:SS`) and relative-time bands only. Rendered as the surface file
 * specifies, with the conflict carried here rather than silently resolved in either direction.
 *
 * Under an hour renders as bare minutes (`47m`) rather than `0h 47m`; over a day still renders in
 * hours (`26h 5m`), because a dwell measured in days is an operational fact an officer should see
 * as an unusually large hour count rather than have compressed into "1d 2h".
 */
export function dwellText(min: number): string {
  const total = Math.max(0, Math.round(min))
  const hours = Math.floor(total / 60)
  const mins = total % 60
  if (hours === 0) return mins + 'm'
  return hours + 'h ' + mins + 'm'
}
