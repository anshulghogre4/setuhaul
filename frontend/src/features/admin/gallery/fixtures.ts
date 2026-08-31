import type {
  ActivePolicyResponse,
  AdminFacility,
  AdminUser,
  AuditEntry,
  FacilityRule,
  PolicyPublishResult,
  PolicySimulation,
} from '../lib/types'

/**
 * Fixtures for `/admin/_states` ONLY. Never imported by the live `/admin` route — the same
 * separation `features/ops/gallery/fixtures.ts` and `features/gallery/fixtures.ts` keep.
 *
 * Every value is copied from `06-admin-console/mockup.html` rather than invented, per the standing
 * rule, with two mechanical substitutions that keep the fixture honest about what the backend can
 * actually produce:
 *   - `rule_type` uses the **live** five-value registry, not the mockup's four stale names (see
 *     `lib/rule-types.ts`).
 *   - `audit_logs.action_type` uses the ten real `CHECK`-constrained values, with the domain
 *     phrase carried in `new_value_json` where `invite_user`/`remove_user` genuinely put it.
 */

/**
 * `GET /api/v1/admin/facilities` (A-G10, issue #78).
 *
 * **`facility_name` and `city` are the real seeded values** (`supabase/seed.sql:28,30`), not the
 * "Jaipur"/"Gurugram" short labels the deleted `lib/facility-names.ts` hardcoded — the point of the
 * endpoint is that the name is the server's to state, so a fixture that kept inventing short ones
 * would hide exactly the difference it is meant to demonstrate.
 *
 * The third row has no live counterpart and is the fixture's one deliberate addition: a facility
 * that is **closed** (`active_flag: 0`). It exists so the gallery can show the two answers this one
 * read serves — present in the filter, absent from the invite picker — which is the reason
 * `list_facilities` returns the flag instead of filtering server-side.
 */
export const FACILITIES_FIXTURE: AdminFacility[] = [
  {
    facility_id: 'FAC-GGN-01',
    facility_name: 'SetuHaul Gurugram Cross-Dock',
    city: 'Gurugram',
    active_flag: 1,
  },
  {
    facility_id: 'FAC-JAI-01',
    facility_name: 'SetuHaul Jaipur Distribution Centre',
    city: 'Jaipur',
    active_flag: 1,
  },
  {
    facility_id: 'FAC-IDR-01',
    facility_name: 'SetuHaul Indore Depot (closed)',
    city: 'Indore',
    active_flag: 0,
  },
]

/**
 * The four rows `stitch-prompts.md` names, now carrying the lifecycle stamps `list_users` returns
 * (issues #73/#81).
 *
 * Row 1 is scoped to **two** facilities, which is `screens.md` §2's own first example row and was
 * unrenderable before #72's read half was wired. Row 4 is the pending invitation: `invited_at` set,
 * `invite_accepted_at` null, so `derive_lifecycle_state` returns `INVITED`.
 *
 * **Row 3 keeps a non-null `last_login_ts` and row 4 keeps a null one deliberately** — that pairing
 * is what makes the plate prove the badge is *not* driven by `last_login_ts`: row 2 also has a
 * login stamp and renders Active, while row 4's null one contributes nothing to its badge.
 */
export const USERS_FIXTURE: AdminUser[] = [
  {
    user_id: 'USR-001',
    full_name: 'Neha B.',
    email: 'neha.bansal@setuhaul.example',
    role_name: 'OPERATIONS_EXECUTIVE',
    facility_id: 'FAC-JAI-01',
    driver_id: null,
    is_active: 1,
    last_login_ts: '2026-08-28T09:12:00Z',
    lifecycle_state: 'ACTIVE',
    invited_at: null,
    invite_accepted_at: null,
    removed_at: null,
    scoped_facility_ids: ['FAC-GGN-01', 'FAC-JAI-01'],
  },
  {
    user_id: 'USR-002',
    full_name: 'Ramesh K.',
    email: 'ramesh.kumar@setuhaul.example',
    role_name: 'GATE_OFFICER',
    facility_id: 'FAC-JAI-01',
    driver_id: null,
    is_active: 1,
    last_login_ts: '2026-08-29T06:40:00Z',
    // Invited through this console and since accepted — the state get_execution_context's stamp
    // produces, and the reason INVITED is not simply "invited_at is set".
    lifecycle_state: 'ACTIVE',
    invited_at: '2026-08-20T07:00:00Z',
    invite_accepted_at: '2026-08-20T09:31:00Z',
    removed_at: null,
    scoped_facility_ids: ['FAC-JAI-01'],
  },
  {
    user_id: 'USR-003',
    full_name: 'Priya S.',
    email: 'priya.sharma@setuhaul.example',
    role_name: 'GATE_OFFICER',
    facility_id: 'FAC-JAI-01',
    driver_id: null,
    is_active: 0,
    last_login_ts: '2026-07-02T11:05:00Z',
    lifecycle_state: 'DEACTIVATED',
    invited_at: null,
    invite_accepted_at: null,
    removed_at: null,
    scoped_facility_ids: ['FAC-JAI-01'],
  },
  {
    user_id: 'USR-004',
    full_name: null,
    email: 'amit.d@setuhaul.example',
    role_name: 'OPERATIONS_EXECUTIVE',
    facility_id: 'FAC-GGN-01',
    driver_id: null,
    is_active: 1,
    last_login_ts: null,
    lifecycle_state: 'INVITED',
    invited_at: '2026-08-30T11:15:00Z',
    invite_accepted_at: null,
    removed_at: null,
    scoped_facility_ids: ['FAC-GGN-01'],
  },
]

/**
 * What production actually looks like today: the migration is applied and deliberately
 * unbackfilled, so **every** row has three NULL stamps and `derive_lifecycle_state` answers
 * `ACTIVE`. The plate built on this exists so the flip's real default state is visible rather than
 * assumed — no Invited rows, no badge, the overflow menu on every row.
 */
export const USERS_NO_INVITES_FIXTURE: AdminUser[] = USERS_FIXTURE.map((user) =>
  user.lifecycle_state === 'INVITED'
    ? { ...user, lifecycle_state: 'ACTIVE', invited_at: null }
    : user,
)

export const RULES_FIXTURE: FacilityRule[] = [
  {
    rule_id: 'RULE001',
    facility_id: 'FAC-JAI-01',
    rule_type: 'CHECKIN_EARLY_LIMIT_MIN',
    rule_value: '60',
    description: 'Earliest check-in relative to the appointment start.',
    effective_from: null,
    effective_to: null,
    active_flag: 1,
  },
  {
    rule_id: 'RULE002',
    facility_id: 'FAC-JAI-01',
    rule_type: 'LAST_NEW_START_TIME',
    rule_value: '21:00',
    description: 'Latest a new unload may start.',
    effective_from: null,
    effective_to: null,
    active_flag: 1,
  },
  {
    rule_id: 'RULE003',
    facility_id: 'FAC-GGN-01',
    rule_type: 'HEAVY_DOCK_REQUIRED_KG',
    rule_value: '18500',
    description: 'Above this weight a heavy-capable dock is required.',
    effective_from: null,
    effective_to: null,
    active_flag: 1,
  },
  {
    rule_id: 'RULE004',
    facility_id: 'FAC-GGN-01',
    rule_type: 'NO_SHOW_GRACE_MIN',
    rule_value: '30',
    description: 'Grace period before an appointment counts as a no-show.',
    effective_from: '2026-08-01T00:00:00Z',
    effective_to: '2026-12-31T00:00:00Z',
    active_flag: 1,
  },
]

export const AUDIT_FIXTURE: AuditEntry[] = [
  {
    audit_id: 'AUD-001',
    user_id: 'USR-000',
    action_type: 'CREATE',
    entity_name: 'policy_versions',
    entity_id: 'POLV-0004',
    old_value_json: null,
    new_value_json: null,
    created_at: '2026-08-29T08:32:00Z',
  },
  {
    audit_id: 'AUD-002',
    user_id: 'USR-001',
    action_type: 'DELETE',
    entity_name: 'users',
    entity_id: 'USR-003',
    old_value_json: null,
    new_value_json: '{"event": "REMOVE_USER"}',
    created_at: '2026-08-29T08:10:00Z',
  },
  {
    audit_id: 'AUD-003',
    user_id: '',
    action_type: 'UPDATE',
    entity_name: 'facility_rules',
    entity_id: 'RULE002',
    old_value_json: null,
    new_value_json: null,
    created_at: '2026-08-29T05:45:00Z',
  },
  {
    audit_id: 'AUD-004',
    user_id: 'USR-000',
    action_type: 'CREATE',
    entity_name: 'users',
    entity_id: 'USR-004',
    old_value_json: null,
    new_value_json: '{"event": "INVITE_USER", "email": "amit.d@setuhaul.example", "role": "OPERATIONS_EXECUTIVE"}',
    created_at: '2026-08-29T04:22:00Z',
  },
]

export const ACTOR_NAMES: Record<string, string> = {
  'USR-000': 'Anshul G.',
  'USR-001': 'Neha B.',
  'USR-002': 'Ramesh K.',
}

/* ---------------------------------------------------------------------------------------------
 * Policy (Screens 8 and 10)
 *
 * The weight VALUES here are copied from `backend/app/scheduling/constraints.json`'s real
 * `score_weights`, which is also what `mockup.html` §8 shows — the mockup's `4 / -6 / 1 / -25`
 * being byte-exact matches to the live file is recorded in `implementation-spec.md` §5.5 as a good
 * sign that part of the surface was drawn against real data.
 *
 * **These constants exist only so `/admin/_states` can render without a backend.** The live
 * `/admin` route never imports this file; its editor renders nothing at all until
 * `GET /admin/policy/active` answers. That separation is the whole reason a fixture is allowed to
 * carry numbers here and nowhere else.
 * ------------------------------------------------------------------------------------------- */

const LIVE_WEIGHTS = {
  lateness_per_minute: 4,
  wait_after_eta_per_minute: -6,
  fit_slack_per_minute: 1,
  compatible_but_not_exact_dock_penalty: -25,
  lateness_cap_minutes: 720,
  fit_slack_cap_minutes: 120,
  w_fairness: 0,
}

const LIVE_PRIORITY_SCORES = { CRITICAL: 4000, HIGH: 3000, NORMAL: 2000, LOW: 1000, UNKNOWN: 500 }

const ENGINE_NOTE =
  'live_weights is scheduling/constraints.json -- the file the ranking engine actually reads. ' +
  'publish_policy_version records a decision durably; it does not rewrite that file, so a ' +
  'just-published version can legitimately differ from what is running.'

/** The reassuring case: the published version and the running engine agree. */
export const POLICY_ACTIVE_FIXTURE: ActivePolicyResponse = {
  as_of: '2026-08-31T09:00:00Z',
  source: 'postgresql',
  active_version: {
    policy_version_id: 'POLV-8F2C4A17',
    published_at: '2026-08-11T14:02:00Z',
    published_by_user_id: 'USR-000',
    weights: { ...LIVE_WEIGHTS },
  },
  live_weights: { ...LIVE_WEIGHTS },
  live_priority_scores: { ...LIVE_PRIORITY_SCORES },
  engine_matches_active_version: true,
  note: ENGINE_NOTE,
}

/**
 * The case `engine_matches_active_version` exists for: a version was published, the engine is
 * still running something else. This is the normal state immediately after any real publish that
 * changed a weight, because publishing does not rewrite `constraints.json`.
 */
export const POLICY_DIVERGED_FIXTURE: ActivePolicyResponse = {
  ...POLICY_ACTIVE_FIXTURE,
  active_version: {
    policy_version_id: 'POLV-C0114E93',
    published_at: '2026-08-21T11:40:00Z',
    published_by_user_id: 'USR-000',
    weights: { ...LIVE_WEIGHTS, fit_slack_per_minute: 2, wait_after_eta_per_minute: -8 },
  },
  engine_matches_active_version: false,
}

/** Nothing has ever been published. A real state, not an error — and the one publish that
 *  legitimately carries no `based_on_version_id`. */
export const POLICY_NEVER_PUBLISHED_FIXTURE: ActivePolicyResponse = {
  ...POLICY_ACTIVE_FIXTURE,
  active_version: null,
  engine_matches_active_version: false,
}

export const POLICY_DRAFTS_FIXTURE: Record<string, string> = {
  lateness_per_minute: '4',
  wait_after_eta_per_minute: '-6',
  fit_slack_per_minute: '2',
  compatible_but_not_exact_dock_penalty: '-25',
}

/**
 * A result in the shape `simulate_policy_weights` genuinely returns — one shipment and two slots
 * per flip, NOT the mockup's head-to-head shipment pair, which the tool does not compute.
 */
export const SIMULATION_FIXTURE: PolicySimulation = {
  as_of: '2026-08-31T09:02:00Z',
  code: 'SIMULATED',
  candidates_evaluated: 340,
  flip_count: 12,
  example_flips: [
    { shipment_id: 'SHP1014', live_top_slot: 'SLOT-J-0412', proposed_top_slot: 'SLOT-J-0418' },
    { shipment_id: 'SHP1002', live_top_slot: 'SLOT-G-1130', proposed_top_slot: 'SLOT-G-1145' },
  ],
  fairness_term_evaluated: false,
  live_w_fairness: 0,
  proposed_w_fairness: 0,
  note:
    'Approximation, not a literal replay: no historical decision log exists, so this re-scores ' +
    "each shipment's current appointment against other slots open today at the same facility, " +
    'not the exact candidate set available at the real booking moment.',
}

/**
 * The run that proves nothing. `_replayable_candidates` only matches appointments that are still
 * active and whose slot starts inside the window, so a purely historical 30-day window can
 * legitimately match none — and a "0 of 0 would flip" result is the absence of evidence, not
 * evidence of no change. Publish is refused on this, which is a deliberate strengthening of U27's
 * gate rather than something the design files ask for.
 */
export const SIMULATION_VACUOUS_FIXTURE: PolicySimulation = {
  ...SIMULATION_FIXTURE,
  candidates_evaluated: 0,
  flip_count: 0,
  example_flips: [],
}

export const PUBLISH_RESULT_FIXTURE: PolicyPublishResult = {
  as_of: '2026-08-31T09:05:00Z',
  code: 'PUBLISHED',
  policy_version_id: 'POLV-D71A0B44',
  superseded_version_id: 'POLV-8F2C4A17',
}

/** `edge-cases.md` #3's refusal, verbatim in the shape `_policy_version_conflict` builds it. */
export const PUBLISH_CONFLICT_FIXTURE = {
  message:
    'Cannot publish this policy version: POLV-C0114E93 was published first. Re-read the current ' +
    'version and re-run the simulation against it before publishing.',
  detail:
    'based_on_version_id=POLV-8F2C4A17, current_version_id=POLV-C0114E93, published_by=USR-000',
}
