-- E3.4 (issue #28, M3): admin console -- policy versioning and the facility-rule type registry.
--
-- Design citation: SOLUTION_DESIGN.md section 7.5.7. `publish_policy_version` needs a
-- `policy_versions` row to actually write to -- confirmed live 2026-08-25 no such table existed.
-- `facility_rules.rule_type` was genuinely free text -- confirmed live: no CHECK constraint at
-- all, contradicting section 7.5.7's own stated closure of "the typed rule-type registry (section
-- 0.9 issue 10's resolution -- never free-text rule matching)". That resolution was never actually
-- applied to the schema; this migration is what applies it.
--
-- The registry values are the five REAL live `rule_type` strings (read directly from
-- `facility_rules`, not invented): HEAVY_DOCK_REQUIRED_KG, LAST_NEW_START_TIME,
-- CHECKIN_EARLY_LIMIT_MIN, NO_SHOW_GRACE_MIN, REEFER_DOCK_REQUIRED. Section 7.5.7's own illustrative
-- names (EARLY_LIMIT, DOCK_PIN, WEIGHT_LIMIT, NEW_START_CUTOFF) do not match any value actually
-- seeded or referenced anywhere in code -- they read as descriptive placeholders, not the intended
-- literal enum, so this migration codifies what the system actually uses today, not the doc's prose.

BEGIN;

ALTER TABLE public.facility_rules
  ADD CONSTRAINT facility_rules_rule_type_check
  CHECK (rule_type IN (
    'HEAVY_DOCK_REQUIRED_KG', 'LAST_NEW_START_TIME', 'CHECKIN_EARLY_LIMIT_MIN',
    'NO_SHOW_GRACE_MIN', 'REEFER_DOCK_REQUIRED'
  ));

-- One immutable row per publish (D7): a policy is never mutated in place, only superseded.
-- `is_active` is a plain flag, not an exclusion constraint -- publish_policy_version is
-- responsible for clearing the prior active row in the same transaction it sets a new one,
-- the same "one writer, one transaction" discipline used throughout this project's writes.
CREATE TABLE IF NOT EXISTS public.policy_versions (
  policy_version_id text PRIMARY KEY,
  weights_json text NOT NULL,
  published_at timestamptz NOT NULL DEFAULT now(),
  published_by_user_id text NOT NULL REFERENCES public.users(user_id),
  is_active integer NOT NULL DEFAULT 0 CHECK (is_active IN (0, 1))
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_policy_versions_one_active
  ON public.policy_versions ((is_active))
  WHERE is_active = 1;

COMMIT;
