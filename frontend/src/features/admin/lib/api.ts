import { getSession } from '@/core/auth/supabase'
import { apiGet, apiPost } from '@/core/http/api'
import type {
  AuditFilters,
  AuditLogResponse,
  ListFacilityRulesResponse,
  ListUsersResponse,
  UserMutationResult,
} from './types'

/**
 * Real calls against the endpoints M3/E3.4 shipped (`backend/app/api/v1/routers/admin.py`). No
 * fixture data here — this file is the one the live `/admin` route uses; `gallery/fixtures.ts` is
 * the separate, explicitly-fixture-only file for `/admin/_states`.
 *
 * **Only the endpoints the built UI actually calls are wrapped.** `create_facility_rule`,
 * `update_facility_rule`, `simulate_policy_weights` and `publish_policy_version` are deliberately
 * absent: their screens are flag-gated off (`lib/flags.ts` — `adminRuleEditorEnabled`,
 * `adminPolicyEditorEnabled`), and an exported wrapper no caller can reach would read as "this is
 * wired" to the next person opening the file. Same posture E5.3 took with the tools behind
 * `get_planner_queue`.
 *
 * Idempotency: `remove_user` is the only mutation the built UI performs that the backend requires
 * an `Idempotency-Key` for (`admin.py:158-169`, High tier per `components.md` §19). It gets one
 * from `crypto.randomUUID()`, the same mechanism `features/ops` and `features/planner` already
 * use. `invite_user`/`update_user`/`deactivate_user`/`reactivate_user` take none — `admin.py`
 * names none for them, and this file does not invent one.
 */

export async function listUsers(params?: {
  roleFilter?: string | null
  facilityFilter?: string | null
}): Promise<ListUsersResponse> {
  const query = new URLSearchParams()
  if (params?.roleFilter) query.set('role_filter', params.roleFilter)
  if (params?.facilityFilter) query.set('facility_filter', params.facilityFilter)
  const suffix = query.toString() ? `?${query.toString()}` : ''
  const res = await apiGet<ListUsersResponse>(`/api/v1/admin/users${suffix}`)
  return res.data
}

/**
 * `POST /api/v1/admin/users/invite`.
 *
 * `scope` is omitted entirely for global roles rather than sent as `null` — the body model is
 * `extra="forbid"` (`admin.py:57`) but `scope` is optional, and `_validate_scope` returns early
 * for `GLOBAL_ROLES` before looking at it. Sending nothing is the honest encoding of "this role
 * has no scope", matching `screens.md` §2's "no scope field for admin roles".
 */
export async function inviteUser(payload: {
  email: string
  role: string
  scope?: string
}): Promise<UserMutationResult> {
  const body: Record<string, string> = { email: payload.email, role: payload.role }
  if (payload.scope) body.scope = payload.scope
  const res = await apiPost<UserMutationResult>('/api/v1/admin/users/invite', body)
  return res.data
}

/**
 * `POST /api/v1/admin/users/{user_id}/update`.
 *
 * Note the shipped semantics, which the UI has to respect rather than assume: `update_user` only
 * re-derives `facility_id`/`driver_id` when `role` is provided (`admin_user_service.py:284-300` —
 * the `CASE WHEN :role_provided` branch). Sending `scope` alone is accepted and silently changes
 * nothing, so the edit form always submits `role` alongside `scope`.
 */
export async function updateUser(
  userId: string,
  payload: { role?: string; scope?: string },
): Promise<UserMutationResult> {
  const body: Record<string, string> = {}
  if (payload.role) body.role = payload.role
  if (payload.scope) body.scope = payload.scope
  const res = await apiPost<UserMutationResult>(
    `/api/v1/admin/users/${encodeURIComponent(userId)}/update`,
    body,
  )
  return res.data
}

export async function deactivateUser(userId: string): Promise<UserMutationResult> {
  const res = await apiPost<UserMutationResult>(
    `/api/v1/admin/users/${encodeURIComponent(userId)}/deactivate`,
    {},
  )
  return res.data
}

export async function reactivateUser(userId: string): Promise<UserMutationResult> {
  const res = await apiPost<UserMutationResult>(
    `/api/v1/admin/users/${encodeURIComponent(userId)}/reactivate`,
    {},
  )
  return res.data
}

/** High tier (`components.md` §19). The backend rejects a missing `Idempotency-Key` with 400. */
export async function removeUser(userId: string): Promise<UserMutationResult> {
  const res = await apiPost<UserMutationResult>(
    `/api/v1/admin/users/${encodeURIComponent(userId)}/remove`,
    {},
    { idempotencyKey: crypto.randomUUID() },
  )
  return res.data
}

export async function listFacilityRules(
  facilityId?: string | null,
): Promise<ListFacilityRulesResponse> {
  const suffix = facilityId ? `?facility_id=${encodeURIComponent(facilityId)}` : ''
  const res = await apiGet<ListFacilityRulesResponse>(`/api/v1/admin/facility-rules${suffix}`)
  return res.data
}

function auditQuery(filters: AuditFilters): URLSearchParams {
  const query = new URLSearchParams()
  if (filters.actor) query.set('actor', filters.actor)
  if (filters.eventType) query.set('event_type', filters.eventType)
  if (filters.dateFrom) query.set('date_from', filters.dateFrom)
  if (filters.dateTo) query.set('date_to', filters.dateTo)
  return query
}

export async function getAuditLog(filters: AuditFilters): Promise<AuditLogResponse> {
  const query = auditQuery(filters).toString()
  const res = await apiGet<AuditLogResponse>(
    `/api/v1/admin/audit-log${query ? `?${query}` : ''}`,
  )
  return res.data
}

/**
 * `GET /api/v1/admin/audit-log/export` — the one endpoint on this surface that does **not** return
 * the standard JSON envelope.
 *
 * It returns a `PlainTextResponse(csv_text, media_type="text/csv")` (`admin.py:251-262`), so
 * `apiGet` cannot be used: it calls `res.json()` unconditionally and would throw on valid CSV.
 * Hence the hand-rolled fetch here. The auth header is built the same way `core/http/api.ts`
 * builds it (bearer from the Supabase session), and the base URL is read from the same env var —
 * duplicated rather than exported from that module, because widening a shared file that two other
 * builds are reading right now is not this build's to do. Flagged for the coordinator as a small,
 * real cleanup: `core/http/api.ts` has no non-JSON GET helper.
 *
 * `filters` is the same object the table is currently showing, which is what makes
 * `screens.md` §5's "export respects the current filter set" genuinely true rather than
 * aspirational — and `export_audit_log` accepts exactly these four, no more
 * (`admin_governance_service.py:400-409`), which is why the Audit tab offers no fifth filter.
 */
export async function exportAuditLogCsv(filters: AuditFilters): Promise<Blob> {
  const base = (import.meta.env.VITE_API_BASE_URL as string | undefined) || 'http://localhost:8000'
  const session = await getSession()
  if (!session?.access_token) throw new Error('Not authenticated')

  const query = auditQuery(filters).toString()
  const res = await fetch(`${base}/api/v1/admin/audit-log/export${query ? `?${query}` : ''}`, {
    headers: { Authorization: `Bearer ${session.access_token}`, Accept: 'text/csv' },
  })
  if (!res.ok) throw new Error(`Export failed (${res.status})`)
  return await res.blob()
}

/**
 * Hands the CSV to the browser as a download.
 *
 * `URL.createObjectURL` + an anchor click is still the current MDN-documented way to do this, and
 * MDN is explicit that `revokeObjectURL` must be called or the blob leaks for the page's lifetime
 * — so the revoke happens in the same tick, immediately after the click, rather than being left
 * to a timeout. (MDN, `URL.createObjectURL()`, checked 2026-08-29.)
 */
export function downloadCsv(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = filename
  document.body.append(anchor)
  anchor.click()
  anchor.remove()
  URL.revokeObjectURL(url)
}
