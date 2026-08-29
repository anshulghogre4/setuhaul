import { Download } from 'lucide-react'
import { useCallback, useEffect, useMemo, useState } from 'react'

import {
  LoadFailed,
  NoMatches,
  NothingYet,
  TableCard,
  TableSkeleton,
  WriteFailedBanner,
} from './primitives'
import { AuditTable } from './audit-table'
import { FilterSelect, Toolbar, ToolbarSpacer } from './toolbar'
import { downloadCsv, exportAuditLogCsv, getAuditLog, listUsers } from '../lib/api'
import { AUDIT_EVENT_TYPES, isoDaysAgo } from '../lib/audit'
import type { AuditEntry, AuditFilters } from '../lib/types'
import { formatUserFriendlyError } from '@/core/http/api'
import { Button } from '@/shared/ui/button'

type LoadState = 'loading' | 'ready' | 'failed'

const DATE_RANGES = [
  { value: '1', label: 'Last 24 hours' },
  { value: '7', label: 'Last 7 days' },
  { value: '30', label: 'Last 30 days' },
  { value: '90', label: 'Last 90 days' },
]

/**
 * Screen 11 — Audit tab. **🟢, built for real** (`implementation-spec.md` §3, §5.5: "the strongest
 * area of the whole surface").
 *
 * Everything `screens.md` §5 promises is genuinely backed:
 *  - **Recent-first, always** — `get_audit_log` orders `created_at DESC`
 *    (`admin_governance_service.py:391`), so there is no sort control implying otherwise and the
 *    Time header carries `aria-sort="descending"`.
 *  - **Filters re-query the server**, never filter an already-fetched page — `flows-and-states.md`
 *    Flow 8 is explicit about this, "since the log can be arbitrarily large."
 *  - **Actor carries a name and a stable id** — the display name comes from `list_users`, the id
 *    is what was logged, and the id is what the filter actually sends (`user_id = :actor`).
 *  - **Export respects the current filter set** — `export_audit_log` accepts exactly the four
 *    filters this toolbar holds and no others (`admin_governance_service.py:400-409`), which is
 *    also why no fifth filter is offered.
 *  - **`(system)` never a blank actor.**
 *  - **No drill-down** — the Resource column is plain text with no interactive affordance at all.
 *
 * Two honest divergences from the artboards, both contract-shaped rather than stylistic, and both
 * new findings this build made (they are not among `implementation-spec.md`'s own eight gaps):
 *
 *  1. **The Event-type filter uses the real ten-value `action_type` vocabulary**, not
 *     `mockup.html` §11.2's five domain phrases ("Policy published", "User removed", …). Sending
 *     a domain phrase matches nothing and returns an empty page with no error. The Event
 *     *column* still shows the domain sentence — derived from `action_type` + `entity_name` +
 *     the `event` key stored in `new_value_json`, which is real data, not composed prose. See
 *     `lib/audit.ts`.
 *  2. **Single-select, not the mockup's checkboxes.** `event_type` is one `str | None`
 *     server-side; there is no way to express an OR of several event types.
 *
 * **The free-text search box is not built at all, and this is not an oversight.** `get_audit_log`
 * has no search parameter (only `actor`, `event_type`, `date_from`, `date_to`, `resource`), and
 * Flow 8 forbids the client-side fallback. Both paths are closed, so nothing is rendered rather
 * than a control that silently does nothing. `resource` exists but is an exact `entity_name`
 * match — not a search — and `export_audit_log` does not accept it, so wiring it would break the
 * "export respects the current filter set" guarantee that makes this tab the strong one.
 */
export function AuditTab() {
  const [state, setState] = useState<LoadState>('loading')
  const [entries, setEntries] = useState<AuditEntry[]>([])
  const [actorNames, setActorNames] = useState<Record<string, string>>({})
  const [actorOptions, setActorOptions] = useState<Array<{ value: string; label: string }>>([])

  const [days, setDays] = useState('7')
  const [actor, setActor] = useState<string | null>(null)
  const [eventType, setEventType] = useState<string | null>(null)
  const [exportError, setExportError] = useState<string | null>(null)

  const filters: AuditFilters = useMemo(
    () => ({
      actor,
      eventType,
      dateFrom: isoDaysAgo(Number(days)),
      dateTo: null,
    }),
    [actor, eventType, days],
  )

  const load = useCallback(async (active: AuditFilters) => {
    setState('loading')
    try {
      const result = await getAuditLog(active)
      setEntries(result.items)
      setState('ready')
    } catch {
      setState('failed')
    }
  }, [])

  useEffect(() => {
    void load(filters)
  }, [load, filters])

  // The Actor filter's options and the Actor column's display names both need user_id -> name.
  // `list_users` is the only read that provides it; fetched once rather than per filter change,
  // and a failure here degrades to raw ids rather than breaking the tab.
  useEffect(() => {
    void (async () => {
      try {
        const result = await listUsers()
        const names: Record<string, string> = {}
        for (const user of result.items) names[user.user_id] = user.full_name ?? user.email
        setActorNames(names)
        setActorOptions(
          result.items
            .map((user) => ({ value: user.user_id, label: user.full_name ?? user.email }))
            .sort((a, b) => a.label.localeCompare(b.label)),
        )
      } catch {
        setActorNames({})
        setActorOptions([])
      }
    })()
  }, [])

  const filtersActive = actor !== null || eventType !== null || days !== '7'
  // `edge-cases.md` #5: Export is genuinely disabled when the filter returns nothing, "so an
  // admin never receives a file and has to guess whether it's empty because nothing happened or
  // because something went wrong."
  const canExport = state === 'ready' && entries.length > 0

  async function onExport() {
    setExportError(null)
    try {
      const blob = await exportAuditLogCsv(filters)
      downloadCsv(blob, `setuhaul-audit-${new Date().toISOString().slice(0, 10)}.csv`)
    } catch (error) {
      setExportError(formatUserFriendlyError(error))
    }
  }

  return (
    <div className="flex flex-col">
      {exportError ? (
        <WriteFailedBanner detail={exportError} onRetry={() => void onExport()} />
      ) : null}

      <Toolbar>
        <FilterSelect
          label="Date range"
          value={days}
          onChange={(value) => setDays(value ?? '7')}
          allLabel="Last 7 days"
          options={DATE_RANGES}
        />
        <FilterSelect
          label="Actor"
          value={actor}
          onChange={setActor}
          allLabel="All actors"
          options={actorOptions}
        />
        <FilterSelect
          label="Event type"
          value={eventType}
          onChange={setEventType}
          allLabel="All event types"
          options={AUDIT_EVENT_TYPES}
        />
        <ToolbarSpacer />
        <Button
          variant="neutral"
          aria-disabled={!canExport}
          tabIndex={0}
          title={canExport ? undefined : 'There is nothing to export with this filter'}
          className={canExport ? undefined : 'opacity-50'}
          onClick={() => {
            if (!canExport) return
            void onExport()
          }}
        >
          <Download aria-hidden="true" />
          Export
        </Button>
      </Toolbar>

      {state === 'loading' ? (
        <TableCard>
          <TableSkeleton columns={4} />
        </TableCard>
      ) : state === 'failed' ? (
        <LoadFailed what="the audit log" onRetry={() => void load(filters)} />
      ) : entries.length === 0 && filtersActive ? (
        <NoMatches
          title="No events match this filter."
          body="Widen the date range, or clear the actor and event-type filters."
          onClear={() => {
            setActor(null)
            setEventType(null)
            setDays('7')
          }}
          clearLabel="Clear filters"
        />
      ) : entries.length === 0 ? (
        <NothingYet
          title="No events have been recorded yet."
          body="Every write in this product lands here through the same audit mechanism, including this console’s own."
        />
      ) : (
        <AuditTable entries={entries} actorNames={actorNames} />
      )}
    </div>
  )
}
