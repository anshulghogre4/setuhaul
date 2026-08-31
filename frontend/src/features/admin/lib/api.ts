import { apiGet, apiGetBlob, apiPost } from '@/core/http/api'
import type {
  ActivePolicyResponse,
  AuditFilters,
  AuditLogResponse,
  ListFacilitiesResponse,
  ListFacilityRulesResponse,
  ListUsersResponse,
  PolicyPublishResult,
  PolicySimulation,
  PolicyWeights,
  UserMutationResult,
  UserRemovalImpact,
} from './types'

/**
 * Real calls against the endpoints M3/E3.4 shipped (`backend/app/api/v1/routers/admin.py`). No
 * fixture data here — this file is the one the live `/admin` route uses; `gallery/fixtures.ts` is
 * the separate, explicitly-fixture-only file for `/admin/_states`.
 *
 * **Only the endpoints the built UI actually calls are wrapped.** `create_facility_rule` and
 * `update_facility_rule` are deliberately absent: their screens are flag-gated off (`lib/flags.ts`
 * — `adminRuleEditorEnabled`), and an exported wrapper no caller can reach would read as "this is
 * wired" to the next person opening the file. Same posture E5.3 took with the tools behind
 * `get_planner_queue`.
 *
 * **Updated 2026-08-31:** `get_active_policy_version`, `simulate_policy_weights` and
 * `publish_policy_version` are now wrapped and genuinely called — the Policy tab (Screens 8/10) is
 * built. They were absent under exactly the rule above; the rule did not change, the caller
 * appeared. See the policy section at the foot of this file.
 *
 * Idempotency: `remove_user` and `revoke_invite` are the two mutations the built UI performs that
 * the backend requires an `Idempotency-Key` for — both delete a Supabase Auth identity, which no
 * retry can undo (`admin.py`'s own `_require_idempotency_key`, High tier per `components.md` §19).
 * Each gets one from `crypto.randomUUID()`, the same mechanism `features/ops` and
 * `features/planner` already use. `invite_user`/`update_user`/`deactivate_user`/`reactivate_user`/
 * `resend_invite` take none — `admin.py` names none for them, and this file does not invent one.
 * `resend_invite`'s own docstring states why: a duplicate resend costs a duplicate email, and
 * GoTrue's `over_email_send_rate_limit` already bounds that.
 */

/**
 * `GET /api/v1/admin/facilities` (A-G10, issue #78).
 *
 * The read that lets a facility with no users and no rules be selected at all. Everything on this
 * surface that names a facility — both filters, the invite form's scope picker, both tables'
 * display names — now comes from here rather than from ids scraped out of already-loaded rows.
 * See `lib/facilities.ts` for what that replaced.
 */
export async function listFacilities(): Promise<ListFacilitiesResponse> {
  const res = await apiGet<ListFacilitiesResponse>('/api/v1/admin/facilities')
  return res.data
}

export async function listUsers(params?: {
  roleFilter?: string | null
  facilityFilter?: string | null
}): Promise<ListUsersResponse> {
  const query = new URLSearchParams()
  if (params?.roleFilter) query.set('role_filter', params.roleFilter)
  if (params?.facilityFilter) query.set('facility_filter', params.facilityFilter)
  // `include_removed` is deliberately not sent. `list_users` defaults it to false, which is
  // `edge-cases.md` #8's rule ("a genuinely removed user does not reappear in search"), and this
  // console offers no toggle for it — see `components/users-tab.tsx` for why that is a decision
  // rather than an omission.
  const suffix = query.toString() ? `?${query.toString()}` : ''
  const res = await apiGet<ListUsersResponse>(`/api/v1/admin/users${suffix}`)
  return res.data
}

/**
 * `POST /api/v1/admin/users/invite`.
 *
 * `scope` takes one id or many (A-G4, issue #72): `InviteUserBody.scope` is `str | list[str] |
 * None` and `normalize_scope` de-duplicates whichever arrives. The form sends an **array** for
 * facility roles, because that is what a multi-select collects — a single-element array and a bare
 * string are the same thing to `normalize_scope`, so there is no reason to encode two shapes here.
 *
 * It is omitted entirely for global roles rather than sent as `null`: the body model is
 * `extra="forbid"` but `scope` is optional, and `_validate_scope` returns early for `GLOBAL_ROLES`
 * before looking at it. Sending nothing is the honest encoding of "this role has no scope",
 * matching `screens.md` §2's "admin roles need no scope at all".
 */
export async function inviteUser(payload: {
  email: string
  role: string
  scope?: string[]
}): Promise<UserMutationResult> {
  const body: Record<string, unknown> = { email: payload.email, role: payload.role }
  if (payload.scope && payload.scope.length > 0) body.scope = payload.scope
  const res = await apiPost<UserMutationResult>('/api/v1/admin/users/invite', body)
  return res.data
}

/**
 * `POST /api/v1/admin/users/{user_id}/update`.
 *
 * **The shipped semantics changed with #72 and this comment used to describe the old ones.** A
 * scope-only edit is now a real edit: when `role` is absent, `update_user` re-reads the role **from
 * the database** and validates the scope against it, rather than silently ignoring `scope` as it
 * did before. The edit form still submits both, because its role select is pre-filled and the user
 * may have changed it — but a caller sending scope alone is no longer a silent no-op.
 */
export async function updateUser(
  userId: string,
  payload: { role?: string; scope?: string[] },
): Promise<UserMutationResult> {
  const body: Record<string, unknown> = {}
  if (payload.role) body.role = payload.role
  if (payload.scope && payload.scope.length > 0) body.scope = payload.scope
  const res = await apiPost<UserMutationResult>(
    `/api/v1/admin/users/${encodeURIComponent(userId)}/update`,
    body,
  )
  return res.data
}

/**
 * `POST /api/v1/admin/users/{user_id}/resend-invite` (A-G5, issue #73).
 *
 * **Takes `user_id`, never an email** — the address the invite goes to is read from the stored row
 * server-side, so this cannot be used to send a Supabase Auth invite to an arbitrary address (M15).
 *
 * Two refusals a caller must expect and must not flatten into a generic failure:
 *  - **429 `AUTH_EMAIL_RATE_LIMITED`** — GoTrue's `over_email_send_rate_limit`. This is the
 *    realistic failure of a Resend button (an impatient admin pressing it repeatedly), not an
 *    exotic one, so `users-tab.tsx` renders it as named copy.
 *  - **409 `NOT_PENDING_INVITE`** — the row is no longer pending. An admin acting on a list that
 *    went stale thirty seconds ago gets a refusal rather than a resend to someone who has already
 *    accepted (which GoTrue would 422 anyway).
 */
export async function resendInvite(userId: string): Promise<UserMutationResult> {
  const res = await apiPost<UserMutationResult>(
    `/api/v1/admin/users/${encodeURIComponent(userId)}/resend-invite`,
    {},
  )
  return res.data
}

/**
 * `POST /api/v1/admin/users/{user_id}/revoke-invite` (A-G5, issue #73).
 *
 * Carries an `Idempotency-Key` because it deletes a Supabase Auth identity, which no retry can
 * undo — the same reason `removeUser` below carries one. The key is minted per click here rather
 * than held across retries, matching `removeUser`; a *user-initiated* second click is a second
 * intent, and the server's own `NOT_PENDING_INVITE` precondition makes the second one a no-op
 * refusal rather than a double delete.
 */
export async function revokeInvite(userId: string): Promise<UserMutationResult> {
  const res = await apiPost<UserMutationResult>(
    `/api/v1/admin/users/${encodeURIComponent(userId)}/revoke-invite`,
    {},
    { idempotencyKey: crypto.randomUUID() },
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

/**
 * `GET /api/v1/admin/users/{user_id}/removal-impact` — the count behind `edge-cases.md` #1's
 * confirmation sentence (issue #76 / A-G8, shipped 2026-08-29).
 *
 * A **pure read, and advisory only.** `remove_user` recomputes the same count inside its own
 * removing transaction and never trusts this result (`admin_user_service.py`'s own docstring), so
 * a failure here must not block the removal — the dialog drops the sentence and still commits,
 * exactly as it did before this endpoint existed. That is why the call site swallows the error
 * rather than surfacing it as a write failure.
 */
export async function getUserRemovalImpact(userId: string): Promise<UserRemovalImpact> {
  const res = await apiGet<UserRemovalImpact>(
    `/api/v1/admin/users/${encodeURIComponent(userId)}/removal-impact`,
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
 * `apiGet` cannot be used: it calls `res.json()` and would throw on valid CSV. That used to mean a
 * hand-rolled fetch here; since 2026-08-31 the shared layer has `apiGetBlob`, which keeps the
 * bearer/base-URL logic in one place and — the part that actually mattered — still throws the same
 * code-bearing `ApiError` on a refusal, because a *failed* CSV export still answers with the JSON
 * envelope (`app_error_handler` is media-type-blind). The old local version reported every failure
 * as the string `Export failed (<status>)`, which was the only thing an operator ever saw.
 *
 * `filters` is the same object the table is currently showing, which is what makes
 * `screens.md` §5's "export respects the current filter set" genuinely true rather than
 * aspirational — and `export_audit_log` accepts exactly these four, no more
 * (`admin_governance_service.py:400-409`), which is why the Audit tab offers no fifth filter.
 */
export async function exportAuditLogCsv(filters: AuditFilters): Promise<Blob> {
  const query = auditQuery(filters).toString()
  return await apiGetBlob(`/api/v1/admin/audit-log/export${query ? `?${query}` : ''}`, {
    accept: 'text/csv',
  })
}

/**
 * Hands the CSV to the browser as a download.
 *
 * `URL.createObjectURL` + an anchor click is still the current MDN-documented way to do this, and
 * MDN is explicit that `revokeObjectURL` must be called or the blob leaks for the page's lifetime
 * — so the revoke happens in the same tick, immediately after the click, rather than being left
 * to a timeout. (MDN, `URL.createObjectURL()`, checked 2026-08-29.)
 */
/* ---------------------------------------------------------------------------------------------
 * Policy (Screens 8 and 10)
 * ------------------------------------------------------------------------------------------- */

/**
 * The policy writes need the server's error **code**, not just its message.
 *
 * `edge-cases.md` #3's refusal has to be told apart from an ordinary failure, and the three
 * outcomes `publish_policy_version` can produce (`ALREADY_ACTIONED` 409, `BASE_VERSION_REQUIRED`
 * 422, `UNKNOWN_WEIGHT_KEYS` 422) need three different screens, not one generic banner.
 * Discriminating on the human message string would be exactly the free-text matching this
 * project's typed-registry discipline exists to stop.
 *
 * **This used to require a local `AdminApiError` and a hand-rolled `policyPost`** because
 * `core/http/api.ts`'s `apiPost` threw `new Error(errors[0].detail)` and discarded the code. Since
 * 2026-08-31 it throws `ApiError` (`core/http/errors.ts`) with `code`, `detail`, `status` and the
 * envelope's own sentence as `envelopeMessage`, so both duplicates are gone and the ordinary
 * `apiPost` serves these two calls. `components/policy-tab.tsx` branches on `isApiError(e)` and
 * `e.code`.
 */


/**
 * `GET /api/v1/admin/policy/active` — the baseline `screens.md` §4 requires be "always visible
 * above the editor so an admin can see what they're changing *from*", and the source of the
 * `based_on_version_id` that `publish_policy_version` now demands.
 *
 * This read is what unblocked Screens 8 and 10. Before it existed there was no way to show the
 * current version, no way to seed the weight fields from anything but a hardcoded copy of
 * `constraints.json`, and no way to obtain the publish baseline at all.
 */
export async function getActivePolicy(): Promise<ActivePolicyResponse> {
  const res = await apiGet<ActivePolicyResponse>('/api/v1/admin/policy/active')
  return res.data
}

/**
 * `POST /api/v1/admin/policy/simulate` — **read-only**; never writes a `policy_versions` row
 * (§7.5.7, `screens.md` §4).
 *
 * `window_start` / `window_end` are required `datetime`s, not the design's `window='30d'` string:
 * `SimulatePolicyBody` (`routers/admin.py`) declares both and is `extra="forbid"`, so the client
 * computes the interval the button's own label names and sends it explicitly.
 */
export async function simulatePolicyWeights(args: {
  weights: PolicyWeights
  windowStart: Date
  windowEnd: Date
}): Promise<PolicySimulation> {
  const res = await apiPost<PolicySimulation>('/api/v1/admin/policy/simulate', {
    weights: args.weights,
    window_start: args.windowStart.toISOString(),
    window_end: args.windowEnd.toISOString(),
  })
  return res.data
}

/**
 * `POST /api/v1/admin/policy/publish` — the one write on this tab. High tier: an
 * `Idempotency-Key` is required and the backend rejects a missing one with 400.
 *
 * **`basedOnVersionId` is sent whenever one exists, never omitted for convenience.**
 * `publish_policy_version`'s own docstring is explicit that "an optional guard is not a guard: any
 * caller that forgets the argument gets exactly the old silent-overwrite behaviour back, which is
 * the defect" — and the server enforces it with `BASE_VERSION_REQUIRED` (422) whenever an active
 * version exists. `null` here is only ever the genuine first-publish case.
 *
 * **`idempotencyKey` is a parameter, not minted here**, unlike `removeUser` above — and the
 * difference is deliberate. An idempotency key only does its job if a *retry of the same attempt*
 * carries the *same* key: minting one per call would mean a publish whose response was lost in
 * flight, then retried, writes a second `policy_versions` row. The caller therefore owns the key's
 * lifetime and holds it across retries. It must be re-minted whenever the payload changes, because
 * `lookup_idempotency` hashes `{weights, based_on_version_id}` and refuses a reused key against a
 * different payload with `IDEMPOTENCY_PAYLOAD_MISMATCH` (409) — see `services/idempotency.py`, and
 * the backend's own `test_publish_policy_version_hashes_the_baseline_into_the_idempotency_payload`.
 */
export async function publishPolicyVersion(args: {
  weights: PolicyWeights
  basedOnVersionId: string | null
  idempotencyKey: string
}): Promise<PolicyPublishResult> {
  const body: Record<string, unknown> = { weights: args.weights }
  if (args.basedOnVersionId) body.based_on_version_id = args.basedOnVersionId
  const res = await apiPost<PolicyPublishResult>('/api/v1/admin/policy/publish', body, {
    idempotencyKey: args.idempotencyKey,
  })
  return res.data
}

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
