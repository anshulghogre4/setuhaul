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
 * `admin_user_service.py::list_users`. `is_active` is a Postgres `INTEGER NOT NULL CHECK (is_active
 * IN (0,1))` (`20260805201923_setuhaul_baseline.sql:319-320`) — a number on the wire, not a
 * boolean, which is why `isActiveUser()` below exists rather than a bare truthiness check at
 * call sites.
 *
 * `full_name` is set to `email.split("@")[0]` at invite time and is `TEXT NOT NULL`, so it is never
 * null in practice — typed permissively anyway because the Users tab must not blank a row on an
 * unexpected null.
 *
 * `last_login_ts` is `TEXT` (ISO string), nullable. **It is not a pending-invitation signal, and
 * nothing on this surface may treat it as one** — it is written nowhere in the application (only
 * `seed.sql` sets it), so `last_login_ts === null` marks essentially every user. `lifecycle_state`
 * below is the real signal.
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
  /**
   * The Status column's real source (issues #73 and #81, migration
   * `20260831132101_users_invite_lifecycle.sql`). Derived server-side by
   * `admin_user_service.derive_lifecycle_state`, whose precedence IS the logic: `REMOVED` beats
   * `DEACTIVATED` beats `INVITED` beats `ACTIVE`.
   *
   * **Derived once, on the server, on purpose.** Re-deriving it here from the three stamps would
   * put a second copy of that precedence in a second language, and the two would eventually
   * disagree — with the badge next to a Resend button disagreeing with the tool that button calls.
   *
   * Optional on the wire so a response predating the migration degrades rather than crashing the
   * table; `lifecycleStateOf()` below is the only place that fallback is decided.
   */
  lifecycle_state?: string
  /** Set by `invite_user`, re-stamped by `resend_invite` — "when the currently-outstanding invite
   *  was sent". NULL for every seeded account, which is why those are `ACTIVE` and not pending. */
  invited_at?: string | null
  /** Set by `core/deps.py::get_execution_context` on the user's first authenticated request. Never
   *  written by an admin tool, and never reported by a client. */
  invite_accepted_at?: string | null
  /** Set by `remove_user` and `revoke_invite`. The discriminator that tells a permanent removal
   *  from a reversible deactivation, which `is_active = 0` alone cannot. */
  removed_at?: string | null
  /**
   * Every facility this user is scoped to (`user_scopes`, A-G4 / issue #72), ordered by the
   * server. `list_users` falls back to the single `users.facility_id` mirror when a row predates
   * E2.3's backfill, so this is never empty for a user who genuinely holds one facility.
   */
  scoped_facility_ids?: string[]
}

export type ListUsersResponse = {
  as_of: string
  source: string
  items: AdminUser[]
}

export function isActiveUser(user: AdminUser): boolean {
  return Number(user.is_active) === 1
}

/**
 * The four states `derive_lifecycle_state` can return.
 *
 * `REMOVED` is here even though `list_users` hides those rows by default (`edge-cases.md` #8):
 * the state is reachable through `include_removed`, and a union that omitted it would make the
 * opt-in un-typeable rather than merely unused.
 */
export type LifecycleState = 'ACTIVE' | 'INVITED' | 'DEACTIVATED' | 'REMOVED'

/**
 * The row's lifecycle state, with the pre-migration fallback in exactly one place.
 *
 * A response with no `lifecycle_state` at all is a backend older than issue #73's migration. The
 * fallback answers `DEACTIVATED`/`ACTIVE` from `is_active` — never `INVITED`, because inventing a
 * pending state from a row that carries no invite stamp is precisely the `last_login_ts` mistake
 * this field exists to retire.
 */
export function lifecycleStateOf(user: AdminUser): LifecycleState {
  const state = user.lifecycle_state
  if (state === 'ACTIVE' || state === 'INVITED' || state === 'DEACTIVATED' || state === 'REMOVED') {
    return state
  }
  return isActiveUser(user) ? 'ACTIVE' : 'DEACTIVATED'
}

/** `admin_user_service.py` — every user mutation returns this envelope shape. */
export type UserMutationResult = {
  as_of: string
  code:
    | 'INVITED'
    | 'UPDATED'
    | 'DEACTIVATED'
    | 'REACTIVATED'
    | 'REMOVED'
    /** `resend_invite` / `revoke_invite` (A-G5, issue #73). */
    | 'INVITE_RESENT'
    | 'INVITE_REVOKED'
  user_id: string
  email?: string
  role?: string
  /** `invite_user`/`update_user` echo the scope they actually applied (`normalize_scope`'s output),
   *  which is how a caller learns a duplicate facility was de-duplicated. */
  scope_values?: string[]
  /** Present only on an idempotent replay of `remove_user` or `revoke_invite`. */
  idempotent_replay?: boolean
}

/**
 * `GET /api/v1/admin/facilities` (A-G10, issue #78) — `admin_user_service.list_facilities`.
 *
 * **`active_flag` is served rather than filtered server-side**, because two callers need two
 * different answers from this one read: the Users tab's filter must still be able to name a closed
 * facility that users are scoped to, while the invite form must not offer one as a *new*
 * assignment. `INTEGER CHECK (active_flag IN (0,1))`
 * (`20260805201923_setuhaul_baseline.sql:35`), so a number on the wire like `is_active`.
 */
export type AdminFacility = {
  facility_id: string
  facility_name: string
  city: string
  active_flag: number
}

export type ListFacilitiesResponse = {
  as_of: string
  source: string
  items: AdminFacility[]
}

/**
 * `admin_user_service.py::get_user_removal_impact` (issue #76 / A-G8), the read behind
 * `edge-cases.md` #1's confirmation copy. Copied from the service's own return dict, not from
 * §7.5.7 — the tool is explicitly **not** in that catalog (its docstring says so), it is an
 * addition shaped after `planner_service.get_dock_block_impact`.
 *
 * `active_escalation_count` is a true `count(*) OVER ()` evaluated before the service's own
 * `LIMIT 50`, so it stays honest when `active_escalations` is truncated — which is why the
 * confirmation sentence reads the count and never `active_escalations.length`.
 *
 * `is_self` is served rather than derived client-side so Flow 4's hidden-on-own-account rule does
 * not depend on the client comparing ids. The Users tab already hides Remove on the signed-in
 * admin's own row, so nothing reads it yet; typed because it is on the wire.
 */
export type UserRemovalImpact = {
  as_of: string
  source: string
  user_id: string
  full_name: string | null
  email: string
  active_escalation_count: number
  /** All five columns are `NOT NULL` in `20260812010000_sprint3_lifecycle_escalation.sql:53-65`,
   *  so none is typed nullable. The sample is capped at 50 server-side; the count above is not. */
  active_escalations: Array<{
    escalation_id: string
    shipment_id: string
    facility_id: string
    escalation_status: string
    severity_code: string
  }>
  is_self: boolean
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

/* ---------------------------------------------------------------------------------------------
 * Policy (Screens 8 and 10)
 *
 * Copied from `admin_governance_service.get_active_policy_version` / `simulate_policy_weights` /
 * `publish_policy_version`'s own return dicts, read 2026-08-31 — not from §7.5.7's prose, which
 * does not describe `/policy/active` at all (`routers/admin.py` flags it as an addition to that
 * catalog, not an implementation of it).
 * ------------------------------------------------------------------------------------------- */

/**
 * `constraints.json`'s `score_weights`, and the same shape sent back on simulate/publish.
 *
 * A bare `Record<string, number>` rather than a four-key literal on purpose: the engine's key set
 * is the server's to define (`allowed_weight_keys()` derives the API's allowlist from that same
 * file), so pinning it in a client type would guarantee exactly the drift this surface keeps
 * hitting. `lib/policy.ts` names the four keys this console *edits*; the type stays open.
 */
export type PolicyWeights = Record<string, number>

/** The active `policy_versions` row. `weights` is the parsed `weights_json`. */
export type ActivePolicy = {
  policy_version_id: string
  published_at: string
  published_by_user_id: string
  weights: PolicyWeights
}

/**
 * `GET /api/v1/admin/policy/active`.
 *
 * **`engine_matches_active_version` is the field this whole tab hinges on, and it must not be
 * flattened into the header.** `publish_policy_version` deliberately does not rewrite
 * `scheduling/constraints.json` (its own docstring: "that file is the live ranking engine's actual
 * input and changing it is a deploy-time decision, not a runtime admin write"), so the published
 * version and the running weights can legitimately disagree. `live_weights` is the file; `active_version.weights`
 * is the record; this boolean is the server's own comparison of the two.
 *
 * `active_version` is `null` before anything has ever been published — a real state, not an error.
 */
export type ActivePolicyResponse = {
  as_of: string
  source: string
  active_version: ActivePolicy | null
  live_weights: PolicyWeights
  live_priority_scores: Record<string, number>
  engine_matches_active_version: boolean
  note: string
}

/**
 * `POST /api/v1/admin/policy/simulate`.
 *
 * `example_flips` is **not** the head-to-head shipment pair `mockup.html` §10.B's copy implies
 * ("SHP1014 vs SHP1009"). The tool compares one shipment's own current appointment against other
 * slots open at the same facility, so a flip names one shipment and two slots — the exact
 * content-shape mismatch `implementation-spec.md` §3's Screen 10 caveat (b) predicted. The built
 * UI renders the real shape.
 *
 * `candidates_evaluated` is the denominator behind "N of M would flip".
 */
export type PolicySimulation = {
  as_of: string
  code: 'SIMULATED'
  candidates_evaluated: number
  flip_count: number
  example_flips: Array<{
    shipment_id: string
    live_top_slot: string
    proposed_top_slot: string
  }>
  /** Whether D7's fairness term arithmetically participated. `false` is a real answer, not a skip. */
  fairness_term_evaluated: boolean
  live_w_fairness: number
  proposed_w_fairness: number
  /** The service's own statement of what it approximates. Rendered, never paraphrased. */
  note: string
}

/** `POST /api/v1/admin/policy/publish`. `superseded_version_id` is null on the first-ever publish. */
export type PolicyPublishResult = {
  as_of: string
  code: 'PUBLISHED'
  policy_version_id: string
  superseded_version_id: string | null
  /** Present only when the `Idempotency-Key` replayed a prior success. */
  idempotent_replay?: boolean
}
