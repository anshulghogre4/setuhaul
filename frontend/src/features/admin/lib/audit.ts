import type { AuditEntry } from './types'

/**
 * Audit-log vocabulary and row rendering.
 *
 * **A contract mismatch this surface's design files do not record**, found while wiring the real
 * call and stated here rather than smoothed over:
 *
 * `mockup.html` §11.2's Event-type filter offers five DOMAIN phrases — "Policy published",
 * "User removed", "User invited", "Rule created", "Rule updated". `get_audit_log`'s `event_type`
 * parameter filters `action_type = :event_type.upper()`
 * (`admin_governance_service.py:359-360`), and `action_type` is constrained by the baseline
 * migration to ten CRUD-shaped values (`20260805201923_setuhaul_baseline.sql:344-366`). Sending
 * "POLICY PUBLISHED" matches nothing and returns an empty page **with no error** — the same
 * silently-ignored-argument failure mode `w_fairness` has on the Policy tab.
 *
 * So the filter is built on the real ten-value vocabulary, and the Event *column* derives its
 * domain sentence from fields that genuinely exist on the row (`action_type` + `entity_name`,
 * plus the `event` key `invite_user`/`remove_user` write into `new_value_json`). That is
 * derivation from stored data, not invented copy.
 *
 * A second, related mismatch: the mockup renders the filter as **checkboxes** (multi-select).
 * `event_type` is a single `str | None` server-side, so this is built as a single-select. Stated
 * rather than approximated with an OR the backend cannot express.
 */

/**
 * The ten real `action_type` values, in sentence case.
 *
 * `components.md` §6: "event type (a controlled vocabulary label, not free text — mirrors every
 * other typed-enum discipline in this product)". The vocabulary is the enum; only the casing is
 * presentational.
 */
export const AUDIT_EVENT_TYPES: Array<{ value: string; label: string }> = [
  { value: 'CREATE', label: 'Created' },
  { value: 'UPDATE', label: 'Updated' },
  { value: 'DELETE', label: 'Deleted' },
  { value: 'VIEW', label: 'Viewed' },
  { value: 'LOGIN', label: 'Signed in' },
  { value: 'LOGOUT', label: 'Signed out' },
  { value: 'BOOK_APPOINTMENT', label: 'Appointment booked' },
  { value: 'CANCEL_APPOINTMENT', label: 'Appointment cancelled' },
  { value: 'UPDATE_ETA', label: 'ETA updated' },
  { value: 'SEND_MESSAGE', label: 'Message sent' },
]

/** `invite_user`/`remove_user` stamp a domain `event` key into `new_value_json`. */
const DOMAIN_EVENT_LABELS: Record<string, string> = {
  INVITE_USER: 'User invited',
  REMOVE_USER: 'User removed',
}

const ENTITY_LABELS: Record<string, string> = {
  users: 'User',
  facility_rules: 'Rule',
  policy_versions: 'Policy',
  appointments: 'Appointment',
  shipments: 'Shipment',
  escalation_queue: 'Escalation',
}

const ACTION_VERBS: Record<string, string> = {
  CREATE: 'created',
  UPDATE: 'updated',
  DELETE: 'deleted',
  VIEW: 'viewed',
  BOOK_APPOINTMENT: 'booked',
  CANCEL_APPOINTMENT: 'cancelled',
  UPDATE_ETA: 'ETA updated',
  SEND_MESSAGE: 'message sent',
}

/**
 * The Event column's sentence, derived — never composed prose.
 *
 * Order of preference: the explicit domain `event` key if one was stamped, then
 * `<entity> <verb>` ("User removed", "Rule updated"), then the raw `action_type`. Falling all the
 * way through to the raw enum is deliberate: an event this frontend has no label for should read
 * as the literal thing that was logged, not as a guess.
 */
export function auditEventLabel(entry: AuditEntry): string {
  const domain = readDomainEvent(entry.new_value_json)
  if (domain && DOMAIN_EVENT_LABELS[domain]) return DOMAIN_EVENT_LABELS[domain]

  const entity = ENTITY_LABELS[entry.entity_name]
  const verb = ACTION_VERBS[entry.action_type]
  if (entity && verb) return `${entity} ${verb}`
  if (verb) return `${entry.entity_name} ${verb}`
  return entry.action_type
}

function readDomainEvent(newValueJson: string | null): string | null {
  if (!newValueJson) return null
  try {
    const parsed: unknown = JSON.parse(newValueJson)
    if (parsed && typeof parsed === 'object' && 'event' in parsed) {
      const value = (parsed as { event: unknown }).event
      return typeof value === 'string' ? value : null
    }
  } catch {
    // `new_value_json` is an unstructured TEXT column; a non-JSON value is possible and is not
    // an error worth surfacing — the row still renders from action_type/entity_name.
  }
  return null
}

/**
 * The Resource column — a plain reference, never a link.
 *
 * `screens.md` §5: "no drill-down beyond the log row itself", and `mockup.html` §11.1 is explicit
 * that this column has "no interactive affordance at all — no underline, no hover, no cursor
 * change", because a read-only value that looks clickable and does nothing reads as broken.
 */
export function auditResourceLabel(entry: AuditEntry): string {
  return entry.entity_id ? `${entry.entity_name} ${entry.entity_id}` : entry.entity_name
}

/**
 * `components.md` §6: system-generated events render as the literal string "(system)", never a
 * blank actor — "a blank actor field reads as a data-quality problem; `(system)` reads as a fact."
 *
 * `audit_logs.user_id` is `TEXT NOT NULL` with an FK to `users`, so a truly blank actor should not
 * occur; this handles the case anyway rather than rendering an empty cell if it ever does.
 */
export const SYSTEM_ACTOR_LABEL = '(system)'

export function isSystemActor(entry: AuditEntry): boolean {
  return !entry.user_id || entry.user_id.trim() === ''
}

/**
 * ISO date `N` days before now, for the default "last 7 days" filter.
 *
 * `audit_logs.created_at` is `TEXT` holding ISO-8601, and `get_audit_log` compares it with a plain
 * `>=` (`admin_governance_service.py:364-369`). ISO-8601 sorts lexicographically, so a string
 * comparison is a correct date comparison here — which is why this returns a string rather than
 * a Date.
 */
export function isoDaysAgo(days: number): string {
  const d = new Date()
  d.setDate(d.getDate() - days)
  return d.toISOString()
}

/** Time column. `tabular-nums` is applied by the cell's class, not here. */
export function formatAuditTimestamp(createdAt: string): string {
  const parsed = new Date(createdAt)
  if (Number.isNaN(parsed.getTime())) return createdAt
  return parsed.toLocaleString('en-IN', {
    year: 'numeric',
    month: 'short',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  })
}
