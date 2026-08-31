import { TableCard } from './primitives'
import { formatEffectiveWindow, formatRuleValue } from '../lib/rule-types'
import type { FacilityRule } from '../lib/types'

/**
 * The Facility Rules table, presentational only. Same split as `users-table.tsx`.
 *
 * Rows carry **no status colour** (`mockup.html` §5): "a rule is not a state, and colour here
 * would dilute promise state and danger." There is no per-row toggle, reorder handle or simulate
 * affordance either, per the same note — rule changes apply immediately on save; only policy
 * weights are simulated.
 *
 * There is no row overflow menu, unlike the mockup: its only two items would be Edit and Remove,
 * and Edit is 🔴 (issues #70/#71) while no `delete_facility_rule` tool exists anywhere in the
 * backend at all. An overflow button whose menu is empty is worse than no button.
 */
export function RulesTable({
  rules,
  facilityName,
}: {
  rules: FacilityRule[]
  /** Injected, not imported: facility names now come from `GET /admin/facilities` (issue #78) and
   *  this component stays fetch-free so the gallery can render it against fixtures. */
  facilityName: (facilityId: string) => string
}) {
  return (
    <TableCard>
      <table className="w-full table-fixed border-collapse text-body">
        <colgroup>
          <col className="w-[18%]" />
          <col className="w-[28%]" />
          <col className="w-[22%]" />
          <col className="w-[32%]" />
        </colgroup>
        <thead>
          <tr className="border-b border-border text-left text-label text-muted-foreground uppercase tracking-wide">
            <th scope="col" className="px-4 py-3">Facility</th>
            <th scope="col" className="px-4 py-3">Rule type</th>
            <th scope="col" className="px-4 py-3">Value</th>
            <th scope="col" className="px-4 py-3">Effective</th>
          </tr>
        </thead>
        <tbody>
          {rules.map((rule) => (
            <tr key={rule.rule_id} className="border-b border-border last:border-b-0 hover:bg-hover">
              <td className="truncate px-4 py-3">{facilityName(rule.facility_id)}</td>
              {/* Registry values render as uppercase mono enum tokens -- registry values, not
                  prose (`mockup.html` §5). */}
              <td className="truncate px-4 py-3 font-data">{rule.rule_type}</td>
              <td className="truncate px-4 py-3 font-data tabular-nums">
                {formatRuleValue(rule.rule_type, rule.rule_value)}
              </td>
              <td className="truncate px-4 py-3">
                {formatEffectiveWindow(rule.effective_from, rule.effective_to)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </TableCard>
  )
}
