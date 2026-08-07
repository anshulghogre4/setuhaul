-- Additive: link Supabase Auth subjects to seeded app users (ADR 005 / ADR 010).
-- Does not rewrite frozen baseline tables beyond one nullable unique column.
-- Applied to hosted project kujffzgqjmqphkmrbawy via Supabase MCP on 2026-08-07.

ALTER TABLE public.users
  ADD COLUMN IF NOT EXISTS auth_user_id uuid;

COMMENT ON COLUMN public.users.auth_user_id IS
  'Supabase auth.users.id; nullable until mapped. Never use password_hash for login.';

CREATE UNIQUE INDEX IF NOT EXISTS users_auth_user_id_uidx
  ON public.users (auth_user_id)
  WHERE auth_user_id IS NOT NULL;
