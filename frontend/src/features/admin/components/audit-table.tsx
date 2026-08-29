import { TableCard } from './primitives'
import {
  auditEventLabel,
  auditResourceLabel,
  formatAuditTimestamp,
  isSystemActor,
  SYSTEM_ACTOR_LABEL,
} from '../lib/audit'
import type { AuditEntry } from '../lib/types'

/**
 * The Audit log table, presentational only. Same split as `users-table.tsx`.
 *
 * `aria-sort="descending"` on Time is a statement of fact, not a control: `get_audit_log` orders
 * `created_at DESC` unconditionally (`admin_governance_service.py:391`), and `screens.md` §5 makes
 * recent-first "the default and not a sort the user has to choose", so no sort affordance is
 * offered that would imply otherwise.
 *
 * The Resource column is plain reference text with **no interactive affordance at all** — no
 * underline, no hover, no cursor change (`mockup.html` §11.1): "a read-only value that looks
 * clickable and does nothing reads as broken, and the tab that owns a resource already is its
 * detail view" (`screens.md` §5's no-drill-down rule).
 */
export function AuditTable({
  entries,
  actorNames,
}: {
  entries: AuditEntry[]
  /** `user_id` -> display name, from `list_users`. A missing entry renders the raw id. */
  actorNames: Record<string, string>
}) {
  return (
    <TableCard>
      <table className="w-full table-fixed border-collapse text-body">
        <colgroup>
          <col className="w-[18%]" />
          <col className="w-[20%]" />
          <col className="w-[22%]" />
          <col className="w-[40%]" />
        </colgroup>
        <thead>
          <tr className="border-b border-border text-left text-label text-muted-foreground uppercase tracking-wide">
            <th scope="col" aria-sort="descending" className="px-4 py-3">
              Time
            </th>
            <th scope="col" className="px-4 py-3">Actor</th>
            <th scope="col" className="px-4 py-3">Event</th>
            <th scope="col" className="px-4 py-3">Resource</th>
          </tr>
        </thead>
        <tbody>
          {entries.map((entry) => (
            <tr key={entry.audit_id} className="border-b border-border last:border-b-0 hover:bg-hover">
              <td className="truncate px-4 py-3 font-data tabular-nums">
                {formatAuditTimestamp(entry.created_at)}
              </td>
              <td className="truncate px-4 py-3">
                {isSystemActor(entry) ? (
                  <span className="text-subtle-foreground">{SYSTEM_ACTOR_LABEL}</span>
                ) : (
                  // The stable id lives in `title` so a renamed user's history stays attributable
                  // (`components.md` §6, `mockup.html` §11.1's own `title="user_id 8f2c…a417"`).
                  <span title={`user_id ${entry.user_id}`}>
                    {actorNames[entry.user_id] ?? entry.user_id}
                  </span>
                )}
              </td>
              <td className="truncate px-4 py-3">{auditEventLabel(entry)}</td>
              <td className="truncate px-4 py-3 font-data">{auditResourceLabel(entry)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </TableCard>
  )
}
