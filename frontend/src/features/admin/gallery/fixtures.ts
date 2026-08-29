import type { AdminUser, AuditEntry, FacilityRule } from '../lib/types'

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
  },
  {
    user_id: 'USR-002',
    full_name: 'Ramesh K.',
    email: 'ramesh.kumar@setuhaul.example',
    role_name: 'WAREHOUSE_PLANNER',
    facility_id: 'FAC-JAI-01',
    driver_id: null,
    is_active: 1,
    last_login_ts: '2026-08-29T06:40:00Z',
  },
  {
    user_id: 'USR-003',
    full_name: 'Priya S.',
    email: 'priya.sharma@setuhaul.example',
    role_name: 'WAREHOUSE_PLANNER',
    facility_id: 'FAC-JAI-01',
    driver_id: null,
    is_active: 0,
    last_login_ts: '2026-07-02T11:05:00Z',
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
  },
]

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
