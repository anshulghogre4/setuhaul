-- Issue #79 (owner-approved 2026-08-29): the GATE_OFFICER role.
--
-- Design citation: SOLUTION_DESIGN.md section 2 (persona table -- "Gate / yard officer", marked
-- v1 with its own kiosk surface and `facility_checkins` as its table) and section 7.5.2 (the five
-- gate/yard tools). UI-UX/00-foundations/auth-and-scoping.md gives the role both a landing row
-- ("Yard queue for the device's facility") and a "never sees" row ("Scheduling controls. Anything
-- beyond the current facility's yard").
--
-- Why now: the kiosk has been running under a borrowed WAREHOUSE_PLANNER / FACILITY_MANAGER
-- login since the 2026-08-24 mapping decision, because this row did not exist. That credential is
-- strictly wider than the persona -- it carries dock-block, schedule-apply and appointment
-- confirm/reject authority -- and it sits on the one session in the product with no idle timeout
-- (device-bound gate kiosk). This row is what lets the backend gate that surface on a role that
-- has none of those powers.
--
-- Scope of this migration: one seed row. No schema change, no data movement, nothing else reads
-- or writes as a result. `public.roles` is (role_id PK, role_name UNIQUE, description,
-- created_at) with no CHECK constraint on role_name, so no constraint needs relaxing.
--
-- role_id follows the existing sequence: ROL001-ROL008 ship in supabase/seed.sql, ROL009 =
-- CARRIER was added by 20260823090000_e23_identity_model.sql, so this is ROL010.
--
-- Scoping: GATE_OFFICER is a FACILITY-scoped role. It needs no change to the
-- `user_scopes.scope_type` CHECK constraint ('FACILITY','CARRIER','DRIVER' already covers it) and
-- no backfill -- zero GATE_OFFICER users exist, since the role could not be assigned until now.
-- `core/deps.py:get_execution_context` resolves this role's facility from `users.facility_id`,
-- the same column every other facility-scoped role uses; only CARRIER reads `user_scopes`.
--
-- Rollback: DELETE FROM public.roles WHERE role_id = 'ROL010'; -- safe only while no
-- `users.role_id` references it. If any GATE_OFFICER user has been created, reassign those users
-- first (the FK from users.role_id would otherwise block the delete), then revert the backend
-- change (RoleName member, deps.ROLE_PERMISSIONS entry, gate.py role gate,
-- repositories/scope.assert_gate_write_scope and gate_yard_service's call to it) and re-verify
-- that the kiosk still authorises under WAREHOUSE_PLANNER/FACILITY_MANAGER/ADMIN.
--
-- NOT YET APPLIED to any environment as of writing, and not verified against the live database:
-- the repository's `supabase` / `supabase-postgres-best-practices` skills were unavailable in the
-- session that authored it, so AGENTS.md's "database changes require the Supabase and Postgres
-- best-practice skills" gate has NOT been satisfied. Review under those skills before applying.

BEGIN;

INSERT INTO public.roles (role_id, role_name, description)
VALUES (
  'ROL010',
  'GATE_OFFICER',
  'Gate/yard kiosk officer -- records gate-in, yard queue state, dock-in, unload start/end and gate-out for one facility (SS7.5.2). No scheduling authority.'
)
ON CONFLICT (role_id) DO NOTHING;

COMMIT;
