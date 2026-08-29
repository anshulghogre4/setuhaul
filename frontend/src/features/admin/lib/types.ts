/**
 * Response shapes for the admin console, **copied from the live service bodies**, not from
 * `SOLUTION_DESIGN.md` §7.5.7's prose. Same discipline E5.2/E5.3 used: the design doc describes
 * the tool, the service decides the wire shape, and where they disagree the service wins because
 * it is what actually answers.
 *
 * Sources, read 2026-08-29:
 *   - `backend/app/services/admin_user_service.py::list_users` (the exact `SELECT` column list)
 *   - `backend/app/services/admin_governance_service.py::list_facility_rules` / `get_audit_log`
 *   - `backend/app/api/v1/routers/admin.py` (envelope + query/body params)
 *
 * Every one of these arrives inside `ApiEnvelope<T>` (`core/http/api.ts`), so the `data` these
 * types describe is `envelope.data`, never the raw response body.
 */

/**
 * `admin_user_service.py:168-169`. `is_active` is a Postgres `INTEGER NOT NULL CHECK (is_active
 * IN (0,1))` (`20260805201923_setuhaul_baseline.sql:319-320`) — a number on the wire, not a
 * boolean, which is why `isActiveUser()` below exists rather than a bare truthiness check at
 * call sites.
 *
 * `full_name` is set to `email.split("@")[0]` at invite time (`admin_user_service.py:226`) and is
 * `TEXT NOT NULL`, so it is never null in practice — typed permissively anyway because the Users
 * tab must not blank a row on an unexpected null.
 *
 * `last_login_ts` is `TEXT` (ISO string), nullable. **It is not a pending-invitation signal** —
 * see `lib/flags.ts`'s `adminPendingInvitesEnabled` for why (issue #73 / A-G5).
 */
export type AdminUser = {
  user_id: string
  full_name: string | null
  email: string
  role_name: string
  facility_id: string | null
  driver_id: string | null
  is_active: number
  last_login_ts: string | null
}

export type ListUsersResponse = {
  as_of: string
  source: string
  items: AdminUser[]
}

export function isActiveUser(user: AdminUser): boolean {
  return Number(user.is_active) === 1
}

/** `admin_user_service.py:264/311/329/397` — every user mutation returns this envelope shape. */
export type UserMutationResult = {
  as_of: string
  code: 'INVITED' | 'UPDATED' | 'DEACTIVATED' | 'REACTIVATED' | 'REMOVED'
  user_id: string
  email?: string
  role?: string
  /** Present only on an idempotent replay of `remove_user` (`admin_user_service.py:363`). */
  idempotent_replay?: boolean
}

/**
 * `admin_governance_service.py:81-83`. `rule_type` is constrained server-side to the five live
 * values in `20260825213000_e34_policy_versions_and_rule_registry.sql:19-24` — see
 * `lib/rule-types.ts`, which is the single place those five are named on this surface.
 *
 * `effective_from`/`effective_to` are plain `TEXT` absolute instants. There is no recurring
 * weekly window anywhere in the engine (issue #71 / A-G3), which is why the Facility Rules table
 * renders "Always" or a literal range and never the design's "Weekdays only, 18:00–23:59".
 */
export type FacilityRule = {
  rule_id: string
  facility_id: string
  rule_type: string
  rule_value: string
  description: string | null
  effective_from: string | null
  effective_to: string | null
  active_flag: number
}

export type ListFacilityRulesResponse = {
  as_of: string
  source: string
  items: FacilityRule[]
}

/**
 * `admin_governance_service.py:386-387`.
 *
 * `action_type` is one of the ten values the baseline `CHECK` constraint allows
 * (`20260805201923_setuhaul_baseline.sql:344-366`) — **not** the domain phrases
 * `06-admin-console/mockup.html`'s Event column shows. `lib/audit.ts` derives those phrases from
 * `action_type` + `entity_name` + the `event` key inside `new_value_json`, which is real
 * derivation from stored fields rather than invented copy.
 */
export type AuditEntry = {
  audit_id: string
  user_id: string
  action_type: string
  entity_name: string
  entity_id: string | null
  old_value_json: string | null
  new_value_json: string | null
  created_at: string
}

export type AuditLogResponse = {
  as_of: string
  source: string
  items: AuditEntry[]
}

/** The filter set the Audit tab holds, and the exact set `export_audit_log` also accepts. */
export type AuditFilters = {
  actor: string | null
  eventType: string | null
  dateFrom: string | null
  dateTo: string | null
}
