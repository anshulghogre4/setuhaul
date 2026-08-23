-- E2.3 (issue #23, M2): the carrier identity model. user_scopes did not exist -- scope rode
-- directly on users.facility_id, which cannot express a carrier scope. Backup taken before this
-- migration: pg_dump to local scratchpad, 2026-08-23 (not committed).
--
-- Design citation: M15, SOLUTION_DESIGN.md section 2 (persona table), section 7.5.6 (carrier
-- portal), line 204/653/1290/1313 (RBAC scoping: facility / carrier / driver).
--
-- Scope: this migration creates the identity model and backfills it from existing data. It does
-- NOT rewire the four independent scope-check call sites onto user_scopes yet -- that
-- consolidation is E2.2's job ("move scope enforcement into the repository tier, one
-- implementation not four"). Doing both in one change would make this migration's own rollback
-- note impossible to honour ("re-check that every existing role's scope resolves identically
-- before and after") -- users.facility_id keeps working exactly as it does today; user_scopes is
-- added alongside it, not instead of it, until E2.2 consolidates the readers.

BEGIN;

-- 1. CARRIER role. role_id follows the existing ROL00N sequence (8 rows today, ROL001-ROL008).
INSERT INTO public.roles (role_id, role_name, description)
VALUES ('ROL009', 'CARRIER', 'Read-only fleet visibility, scoped to the carrier''s own shipments and drivers (SS7.5.6)')
ON CONFLICT (role_id) DO NOTHING;

-- 2. user_scopes: the scoping half of RBAC the design names (facility / carrier / driver), not
-- previously created. A user can hold more than one scope row (e.g. a future multi-facility
-- FACILITY_MANAGER), so this is a proper child table, not a single nullable column on users.
CREATE TABLE IF NOT EXISTS public.user_scopes (
  scope_id     text NOT NULL PRIMARY KEY,
  user_id      text NOT NULL REFERENCES public.users(user_id),
  scope_type   text NOT NULL CHECK (scope_type IN ('FACILITY', 'CARRIER', 'DRIVER')),
  scope_value  text NOT NULL,
  created_at   timestamptz NOT NULL DEFAULT now(),
  UNIQUE (user_id, scope_type, scope_value)
);

CREATE INDEX IF NOT EXISTS ix_user_scopes_user ON public.user_scopes (user_id);
CREATE INDEX IF NOT EXISTS ix_user_scopes_lookup ON public.user_scopes (scope_type, scope_value);

-- 3. Backfill FACILITY scope for every user who already has one. ADMIN /
-- REGIONAL_OPERATIONS_HEAD / TRANSPORT_MANAGER have facility_id NULL today (global read reach,
-- confirmed live) and correctly get no FACILITY row -- global scope is the absence of a facility
-- constraint, not a row naming every facility.
INSERT INTO public.user_scopes (scope_id, user_id, scope_type, scope_value, created_at)
SELECT 'SCP-FAC-' || u.user_id, u.user_id, 'FACILITY', u.facility_id, now()
FROM public.users u
WHERE u.facility_id IS NOT NULL
ON CONFLICT (user_id, scope_type, scope_value) DO NOTHING;

-- 4. Backfill DRIVER scope for every driver user, from their own driver_id -- the third scope
-- type the design names alongside facility/carrier.
INSERT INTO public.user_scopes (scope_id, user_id, scope_type, scope_value, created_at)
SELECT 'SCP-DRV-' || u.user_id, u.user_id, 'DRIVER', u.driver_id, now()
FROM public.users u
WHERE u.driver_id IS NOT NULL
ON CONFLICT (user_id, scope_type, scope_value) DO NOTHING;

-- No CARRIER-scope backfill: zero CARRIER-role users exist today (confirmed live before this
-- migration) -- the role and the table exist so M3/E3.3 has somewhere to attach carrier users
-- when that epic creates them, not because any exist yet.

COMMIT;
