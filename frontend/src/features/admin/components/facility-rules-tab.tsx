import { useCallback, useEffect, useMemo, useState } from 'react'

import {
  InactiveNote,
  LoadFailed,
  NothingYet,
  NotYetAvailable,
  TableCard,
  TableSkeleton,
} from './primitives'
import { RulesTable } from './rules-table'
import { FilterSelect, Toolbar, ToolbarSpacer } from './toolbar'
import { listFacilityRules } from '../lib/api'
import { useFacilities } from '../lib/facilities'
import { adminRuleEditorEnabled, adminRuleImpactEnabled } from '../lib/flags'
import type { FacilityRule } from '../lib/types'
import { Button } from '@/shared/ui/button'

type LoadState = 'loading' | 'ready' | 'failed'

/**
 * Screen 5 — Facility Rules list. **🟡, built for real against the LIVE registry**
 * (`implementation-spec.md` §3, §5.1 G2).
 *
 * `list_facility_rules` is a plain, correct read and the table renders from it unchanged. The
 * weakening the spec records is that the `rule_type` values it returns
 * (`HEAVY_DOCK_REQUIRED_KG`, `LAST_NEW_START_TIME`, `CHECKIN_EARLY_LIMIT_MIN`, `NO_SHOW_GRACE_MIN`,
 * `REEFER_DOCK_REQUIRED`) do not match this surface's own design copy, which still carries
 * §7.5.7's illustrative `EARLY_LIMIT`/`DOCK_PIN`/`WEIGHT_LIMIT`/`NEW_START_CUTOFF`. Per this
 * build's brief and the spec's own Fork A recommendation, the **live** registry wins here and the
 * design side is what issue #70 reconciles. See `lib/rule-types.ts`.
 *
 * Screens 6 (rule editor) and 7 (dependent-appointment confirmation) are 🔴 and render honest
 * stubs — see `lib/flags.ts`'s `adminRuleEditorEnabled` / `adminRuleImpactEnabled`.
 *
 * Rows carry **no status colour** (`mockup.html` §5): "a rule is not a state, and colour here
 * would dilute promise state and danger."
 */
export function FacilityRulesTab() {
  const [state, setState] = useState<LoadState>('loading')
  const [rules, setRules] = useState<FacilityRule[]>([])
  const facilities = useFacilities()
  const [facilityFilter, setFacilityFilter] = useState<string | null>(null)

  const load = useCallback(async () => {
    setState('loading')
    try {
      const result = await listFacilityRules(facilityFilter)
      setRules(result.items)
      setState('ready')
    } catch {
      setState('failed')
    }
  }, [facilityFilter])

  useEffect(() => {
    void load()
  }, [load])

  /**
   * Every facility, from `GET /admin/facilities` (A-G10 / issue #78) — including ones with no rules
   * yet, which the previous derived-from-loaded-rows list could not name at all. That mattered here
   * as well as on the Users tab: "show me the rules at the facility that has none" is a real
   * question, and the old filter could not even ask it. The `knownFacilityIds` accumulator that
   * worked around the derived list's self-narrowing is deleted with it. Server-ordered by name.
   */
  const facilityOptions = useMemo(
    () => facilities.all.map((f) => ({ value: f.facility_id, label: f.facility_name })),
    [facilities.all],
  )

  return (
    <div className="flex flex-col">
      <Toolbar>
        <FilterSelect
          label="Facility"
          value={facilityFilter}
          onChange={setFacilityFilter}
          allLabel="All facilities"
          options={facilityOptions}
        />
        <ToolbarSpacer />
        {/*
          🔴 Screen 6 (A-G2 #70 + A-G3 #71). Rendered Inactive with the reason stated rather than
          hidden: the action is not scope-denied — an admin genuinely may add a rule — it simply
          has no editor that can be built as designed yet. Foundations §18's Disabled tier, the
          same posture E5.2 used for ops' "Take over thread".
        */}
        <Button
          variant="constructive"
          aria-disabled={!adminRuleEditorEnabled}
          tabIndex={0}
          title={
            adminRuleEditorEnabled ? undefined : 'The rule editor isn’t available yet — issues #70 and #71.'
          }
          className={adminRuleEditorEnabled ? undefined : 'opacity-50'}
        >
          Add rule
        </Button>
      </Toolbar>

      {adminRuleEditorEnabled ? null : (
        <div className="mb-4">
          <InactiveNote>
            Adding and editing rules is not built. The type-specific value fields{' '}
            <code>components.md</code> §2 requires are designed around four rule types the live{' '}
            <code>CHECK</code> constraint does not accept (issue #70), and three of the five types
            it does accept have no field set designed anywhere. The effective-window control needs
            issue #71 — the ranking engine evaluates <code>effective_from</code>/
            <code>effective_to</code> as a plain absolute range and has no recurring-weekly concept
            {adminRuleImpactEnabled ? '' : ', and nothing counts the appointments an edit would affect (issue #74)'}
            .
          </InactiveNote>
        </div>
      )}

      {state === 'loading' ? (
        <TableCard>
          <TableSkeleton columns={4} />
        </TableCard>
      ) : state === 'failed' ? (
        <LoadFailed what="the facility rules" onRetry={() => void load()} />
      ) : rules.length === 0 ? (
        <NothingYet
          title="No facility rules are configured."
          body="Rules constrain what the scheduling engine will offer at a facility. None exist here yet."
        />
      ) : (
        <RulesTable rules={rules} facilityName={facilities.nameOf} />
      )}

      {adminRuleImpactEnabled ? null : (
        <div className="mt-6">
          {/*
            🔴 Screen 7. Its own stub rather than a line folded into Screen 6's, because it is a
            distinct dependency (#74) that survives #70/#71 closing.
          */}
          <NotYetAvailable
            title="Dependent-appointment impact isn’t available."
            body="edge-cases.md #4 requires naming how many already-CONFIRMED appointments a tightened rule would affect before the edit commits. No query anywhere computes it (issue #74) — update_facility_rule is a bare UPDATE. A guessed count is worse than none, so none is shown."
          />
        </div>
      )}
    </div>
  )
}
