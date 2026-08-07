-- Sprint 2: idempotent command ledger for ETA/exception writes (ADR 007 / ADR 010).
-- Additive only. Backend uses DATABASE_URL (postgres); table is not exposed to anon/authenticated.
-- Note: driver_exceptions.dedupe_key is NOT unique-indexed — seed contains intentional duplicates (THR001/THR009).

CREATE TABLE IF NOT EXISTS public.idempotency_requests (
  idempotency_key text PRIMARY KEY,
  user_id text NOT NULL,
  route text NOT NULL,
  request_hash text NOT NULL,
  response_json text NOT NULL,
  status_code integer NOT NULL DEFAULT 200,
  created_at text NOT NULL DEFAULT (CURRENT_TIMESTAMP)::text,
  expires_at text NOT NULL
);

COMMENT ON TABLE public.idempotency_requests IS
  'Command idempotency ledger. Same key+payload returns stored response; same key+different payload is conflict.';

CREATE INDEX IF NOT EXISTS idempotency_requests_user_route_idx
  ON public.idempotency_requests (user_id, route);

CREATE INDEX IF NOT EXISTS idempotency_requests_expires_idx
  ON public.idempotency_requests (expires_at);

-- Optional uniqueness for chat message external ids (client/message dedupe)
CREATE UNIQUE INDEX IF NOT EXISTS chat_messages_external_message_id_uidx
  ON public.chat_messages (external_message_id)
  WHERE external_message_id IS NOT NULL;

ALTER TABLE public.idempotency_requests ENABLE ROW LEVEL SECURITY;

-- Defense in depth: no Data API grants for anon/authenticated
REVOKE ALL ON TABLE public.idempotency_requests FROM anon, authenticated;
GRANT ALL ON TABLE public.idempotency_requests TO postgres, service_role;
