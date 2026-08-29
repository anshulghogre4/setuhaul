import type { OnTimePoint } from '../lib/types'

/**
 * The on-time sparkline — `05-carrier-portal/components.md` §1, `stitch-prompts.md` §2.
 *
 * ## Form, and why each choice is not a preference
 *
 * - **One series, never two.** No benchmark line, no shaded "industry range", no target drawn
 *   from anyone else's performance. `auth-and-scoping.md`'s inference rule makes a comparison
 *   line here a data leak, not a design flourish.
 * - **No hue.** Stroke is `text-tertiary`, the same ink as the tile's own label.
 *   `stitch-prompts.md`'s own "Notes on values" #1 records the mockup's original `green-600`
 *   as the bug: hue in this product is rationed to promise state and danger, and a green trend
 *   line sitting ~40px above a green `CONFIRMED` chip invites exactly the misread the
 *   four-state chip system exists to prevent. The line carries *shape*; the headline `91%`
 *   carries the value.
 * - **End marker by lightness, not hue** — a filled `text-primary` dot with a 2px ring in the
 *   tile's own surface so it stays legible where it lands on the line.
 * - **Drawn at its rendered pixel size.** `width`/`height` match the `viewBox` 1:1 and there is
 *   no `preserveAspectRatio="none"`: a non-uniform stretch renders a "2px" stroke thicker in
 *   one axis than the other, which prompt 2 forbids by name (and which the mockup's own legacy
 *   state 1 still does — recorded there as a defect, not copied here).
 * - **No motion.** It does not draw in, the number does not count up, nothing pulses.
 *
 * ## Gaps are gaps, not zeros
 *
 * `get_on_time_daily_series` omits days with no arrivals rather than zero-filling them, because
 * a zero-percent point would draw a trough that reads as "everything was late" when it actually
 * means "no data". So x is positioned by the point's **real date** inside the window, not by its
 * index in the array: a quiet week renders as one longer segment, never as a compressed one that
 * silently implies daily coverage.
 */

const W = 300
const H = 24
const PAD = 4

export function Sparkline({
  series,
  windowStart,
  windowEnd,
  endingPercent,
}: {
  series: OnTimePoint[]
  windowStart: string
  windowEnd: string
  endingPercent: number | null
}) {
  const points = series.filter((p) => p.percent !== null)
  // Two points is the minimum that can carry a shape. One point is a dot with no trend, which
  // is not what a sparkline claims to be, so it renders nothing rather than something misleading.
  if (points.length < 2) return null

  const t0 = new Date(windowStart).getTime()
  const t1 = new Date(windowEnd).getTime()
  if (!Number.isFinite(t0) || !Number.isFinite(t1) || t1 <= t0) return null

  const x = (iso: string) => {
    const t = new Date(iso).getTime()
    const frac = Math.min(1, Math.max(0, (t - t0) / (t1 - t0)))
    return PAD + frac * (W - PAD * 2)
  }

  /**
   * The y domain, decided by rendering both options rather than by argument.
   *
   * A full 0–100% domain is the more literally honest axis, and it was what this component drew
   * first. Measured against real-shaped data (a carrier at 88–96% over thirty days) it produced a
   * **flat line**: an 8-point spread inside a 100-point domain is under two pixels in a 24px box.
   * That fails the component's own stated job — `components.md` §1 says the sparkline "exists to
   * show shape (trending up/down/flat), not to be read as precise data points", and a line that
   * cannot show a trend is decoration.
   *
   * So the domain fits the data with a **4-point margin on each side**, clamped to 0–100. The
   * margin is what stops the other failure mode: without it, the min and max points pin to the
   * exact top and bottom edge every time, which makes any series — however small its real spread
   * — look like a full-height swing. There is no axis, no gridline and no tick label precisely
   * because the domain is relative; the headline `91%` carries the value, as prompt 2 requires.
   */
  const values = points.map((p) => p.percent as number)
  const lo = Math.max(0, Math.min(...values) - 4)
  const hi = Math.min(100, Math.max(...values) + 4)
  const span = hi - lo || 1

  const y = (percent: number) => {
    const frac = Math.min(1, Math.max(0, (percent - lo) / span))
    return H - PAD - frac * (H - PAD * 2)
  }

  const coords = points.map((p) => `${x(p.day).toFixed(1)},${y(p.percent as number).toFixed(1)}`)
  const last = points[points.length - 1]

  return (
    <svg
      className="mt-2 block"
      width={W}
      height={H}
      viewBox={`0 0 ${W} ${H}`}
      role="img"
      aria-label={`On-time performance over the last 30 days${
        endingPercent === null ? '' : `, ending at ${endingPercent}%`
      }.`}
    >
      {/* components.md §1: "a thin area/line fill, faint baseline". The baseline is what a
          30-point line is read against; without it the shape has no reference. */}
      <line
        x1={PAD}
        y1={H - 1}
        x2={W - PAD}
        y2={H - 1}
        className="stroke-border"
        strokeWidth={1}
      />
      <polyline
        fill="none"
        className="stroke-subtle-foreground"
        strokeWidth={2}
        strokeLinejoin="round"
        strokeLinecap="round"
        points={coords.join(' ')}
      />
      <circle
        cx={x(last.day)}
        cy={y(last.percent as number)}
        r={4}
        className="fill-foreground stroke-card"
        strokeWidth={2}
      />
    </svg>
  )
}
