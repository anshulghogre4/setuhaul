import type { SeverityCode, SlaPosture } from './types'

/**
 * Mirrors `backend/app/services/escalation_service.py`'s `SLA_BUDGET_MIN` verbatim, including its
 * own flag: **`Source: assumption, untested`** (escalation_service.py:29-35) -- no documented SLA
 * policy grounds these per-severity minute budgets anywhere in `SOLUTION_DESIGN.md`. Duplicated
 * here (not re-derived) because the API returns `sla_remaining_min` as an absolute value, not a
 * percentage, and `color.md`'s posture thresholds ("< 25% remaining" for warning) need the
 * denominator to compute a percentage from. If the backend constant changes, this one must move
 * with it -- there is no shared source for the two today.
 */
const SLA_BUDGET_MIN: Record<SeverityCode, number> = { HIGH: 120, MEDIUM: 480, LOW: 1440 }
const DEFAULT_SLA_BUDGET_MIN = 480

/**
 * `color.md` "Escalation severity" -- ok (>25% remaining, no colour), warning (<25%), breach
 * (deadline passed). `escalation-sla-ok` is deliberately uncoloured (`text-secondary`); this
 * function never returns a colour, only the three-way posture a caller maps to a token.
 */
export function slaPosture(severity: SeverityCode, remainingMin: number): SlaPosture {
  if (remainingMin <= 0) return 'breach'
  const budget = SLA_BUDGET_MIN[severity] ?? DEFAULT_SLA_BUDGET_MIN
  const fractionRemaining = remainingMin / budget
  return fractionRemaining < 0.25 ? 'warning' : 'ok'
}

const LOCALE = 'en-IN'

/**
 * "4:12 to breach" / "6m past breach" -- `screens.md` section 2, `edge-cases.md` section 1. The
 * colour is never the sole carrier (U30): this string is what survives forced-colors mode and
 * greyscale, so it is built with the same care as the token that colours it.
 *
 * `Intl.NumberFormat` for the digits (U31, `data-formatting.md`) rather than manual
 * string-building -- consistent with `01-driver-chat`'s `format.ts` precedent.
 */
const minutesFormat = new Intl.NumberFormat(LOCALE, { maximumFractionDigits: 0 })

export function formatSlaRemaining(remainingMin: number): string {
  if (remainingMin <= 0) {
    return `${minutesFormat.format(Math.abs(Math.round(remainingMin)))}m past breach`
  }
  const totalMin = Math.round(remainingMin)
  if (totalMin < 60) return `${minutesFormat.format(totalMin)}m to breach`
  const hours = Math.floor(totalMin / 60)
  const mins = totalMin % 60
  return `${hours}:${String(mins).padStart(2, '0')} to breach`
}
