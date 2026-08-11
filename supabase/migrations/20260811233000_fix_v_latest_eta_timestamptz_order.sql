-- ADR 008: order ETA updates by real timestamptz, not lexicographic text.
-- Seed uses +05:30; app writes often use +00:00 UTC. Text DESC picks the wrong row when dates collide.

CREATE OR REPLACE VIEW public.v_latest_eta
WITH (security_invoker = true) AS
WITH ranked AS (
    SELECT
        e.*,
        ROW_NUMBER() OVER (
            PARTITION BY e.shipment_id
            ORDER BY (e.created_at::timestamptz) DESC, e.eta_update_id DESC
        ) AS rn
    FROM public.eta_updates e
)
SELECT
    s.shipment_id,
    s.original_eta_ts,
    COALESCE(r.declared_eta_ts, s.latest_eta_ts, s.original_eta_ts) AS effective_eta_ts,
    COALESCE(r.source_type, 'ORIGINAL_PLAN') AS eta_source,
    COALESCE(r.confidence_code, 'HIGH') AS eta_confidence,
    r.delay_reason_code,
    r.note AS eta_note,
    r.created_at AS eta_updated_at
FROM public.shipments s
LEFT JOIN ranked r ON r.shipment_id = s.shipment_id AND r.rn = 1;

REVOKE ALL ON TABLE public.v_latest_eta FROM anon, authenticated;
GRANT SELECT ON TABLE public.v_latest_eta TO service_role;
