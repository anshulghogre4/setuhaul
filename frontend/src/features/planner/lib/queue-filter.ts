import type { PlannerQueueRow } from './types'

/**
 * The Queue tab's priority / ETA-confidence filter -- `screens.md` section 2's Rules:
 *
 * > **Filter by priority or ETA confidence, narrowing membership only, never changing sort**
 * > (caught missing in a `checklist-design` audit -- added, unlike ops's cross-facility filter set,
 * > because a spike is exactly when a planner wants to isolate "CRITICAL only" or "LOW confidence
 * > only" for a focused pass). Small surface: no filter chips needed at this scale (15-35 rows) the
 * > way ops's cross-facility view needed them -- the active filter is visible directly in the
 * > toolbar text ("Filter: CRITICAL · 6 shown").
 *
 * Three properties of that paragraph are load-bearing and are why this is a leaf module rather
 * than an inline `.filter()` in `queue-tab.tsx`:
 *
 *  1. **Membership only, never sort.** This is a pure predicate over an already-ordered array. It
 *     cannot reorder, because it never sees the comparator -- `applyResort` / `mergeQueue` remain
 *     the only things in this surface allowed to move a row (U19).
 *  2. **No chips**, unlike `features/ops`. The design says so explicitly and gives the reason, so
 *     the toolbar summary below is the whole affordance and there is no second dismissal surface
 *     to keep in sync.
 *  3. **Shared with the gallery.** `/planner/_states` mounts this same function over fixture rows,
 *     so the narrowing that a click-sweep observes is the narrowing the live route performs -- not
 *     a look-alike written twice.
 *
 * ## Both vocabularies are copied from the database's own CHECK constraints, not from the artboards
 *
 * `shipments.priority_code IN ('LOW','NORMAL','HIGH','CRITICAL')` and
 * `driver_eta_reports.confidence_code IN ('LOW','MEDIUM','HIGH')` --
 * `supabase/migrations/20260805201923_setuhaul_baseline.sql:123` and `:198`. A filter offering a
 * value the column cannot hold would be a control that always returns nothing.
 */

export const PRIORITY_CODES = ['CRITICAL', 'HIGH', 'NORMAL', 'LOW'] as const
export const ETA_CONFIDENCE_CODES = ['LOW', 'MEDIUM', 'HIGH'] as const

export type PriorityCode = (typeof PRIORITY_CODES)[number]
export type EtaConfidenceCode = (typeof ETA_CONFIDENCE_CODES)[number]

/** `null` on either axis means "any" -- the unfiltered default, and the only state in which the
 *  toolbar renders no filter summary at all. */
export type QueueFilter = {
  priority: PriorityCode | null
  etaConfidence: EtaConfidenceCode | null
}

export const EMPTY_QUEUE_FILTER: QueueFilter = { priority: null, etaConfidence: null }

export function isQueueFilterActive(filter: QueueFilter): boolean {
  return filter.priority !== null || filter.etaConfidence !== null
}

/**
 * A row matches when it satisfies **every** active axis (AND, not OR).
 *
 * `eta.confidence` is genuinely nullable -- `get_planner_queue` returns `null` when no driver ETA
 * report exists for the shipment. A row with no confidence on file is **excluded** by an active
 * confidence filter rather than treated as a match: "we have no ETA confidence" is not the same
 * fact as "its confidence is LOW", and the design's stated use ("isolate LOW confidence only for a
 * focused pass") is about rows that carry a measured warning. The same three-valued discipline
 * `lib/types.ts` already applies to `latest_acceptable_breached`.
 *
 * Comparison is case-folded because the column is `TEXT` with a CHECK rather than an enum type, so
 * a differently-cased row would silently vanish from a filtered view instead of failing loudly.
 */
export function matchesQueueFilter(row: PlannerQueueRow, filter: QueueFilter): boolean {
  if (filter.priority !== null) {
    if ((row.receipt.priority_code ?? '').toUpperCase() !== filter.priority) return false
  }
  if (filter.etaConfidence !== null) {
    const confidence = row.eta.confidence
    if (confidence === null) return false
    if (confidence.toUpperCase() !== filter.etaConfidence) return false
  }
  return true
}

export function filterQueueRows(
  rows: PlannerQueueRow[],
  filter: QueueFilter,
): PlannerQueueRow[] {
  if (!isQueueFilterActive(filter)) return rows
  return rows.filter((row) => matchesQueueFilter(row, filter))
}

/**
 * The toolbar summary, in the design's own format: `Filter: CRITICAL · 6 shown`.
 *
 * Returns `null` when nothing is filtered, so the caller renders no summary rather than
 * "Filter: none" -- an inactive control that describes itself as active is the specific confusion
 * the chip row solves on ops, and this surface deliberately has no chips to solve it with.
 */
export function describeQueueFilter(filter: QueueFilter, shown: number): string | null {
  if (!isQueueFilterActive(filter)) return null
  const terms: string[] = []
  if (filter.priority !== null) terms.push(filter.priority)
  if (filter.etaConfidence !== null) terms.push(`${filter.etaConfidence} ETA confidence`)
  return `Filter: ${terms.join(' · ')} · ${shown} shown`
}
