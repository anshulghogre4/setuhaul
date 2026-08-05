-- Generated from docs/database_docs/setuhaul_schema_and_seed.sql
-- Source SHA-256: b8a141fbcc57434b049ef1594245dc618905ef7db30bf3d89d358af287edf6e5
-- Do not edit this baseline by hand; regenerate it with
-- supabase/tools/build_postgres_baseline.py.

set search_path = public;

CREATE TABLE carriers (
    carrier_id TEXT PRIMARY KEY,
    carrier_name TEXT NOT NULL UNIQUE,
    contact_email TEXT,
    contact_phone TEXT,
    active_flag INTEGER NOT NULL DEFAULT 1 CHECK (active_flag IN (0,1))
);

CREATE TABLE vehicle_types (
    vehicle_type_code TEXT PRIMARY KEY,
    description TEXT NOT NULL,
    default_capacity_kg INTEGER NOT NULL CHECK (default_capacity_kg > 0),
    refrigerated_flag INTEGER NOT NULL DEFAULT 0 CHECK (refrigerated_flag IN (0,1)),
    typical_dock_type TEXT NOT NULL
        CHECK (typical_dock_type IN ('STANDARD','REEFER','HEAVY','ANY'))
);

CREATE TABLE facilities (
    facility_id TEXT PRIMARY KEY,
    facility_name TEXT NOT NULL UNIQUE,
    city TEXT NOT NULL,
    state TEXT NOT NULL,
    timezone TEXT NOT NULL DEFAULT 'Asia/Kolkata',
    open_time TEXT NOT NULL,
    close_time TEXT NOT NULL,
    checkin_grace_min INTEGER NOT NULL DEFAULT 30 CHECK (checkin_grace_min >= 0),
    default_unload_min INTEGER NOT NULL DEFAULT 60 CHECK (default_unload_min > 0),
    active_flag INTEGER NOT NULL DEFAULT 1 CHECK (active_flag IN (0,1))
);

CREATE TABLE roles (
    role_id             TEXT PRIMARY KEY,
    role_name           TEXT NOT NULL UNIQUE,
    description         TEXT,
    created_at          TEXT NOT NULL DEFAULT (CURRENT_TIMESTAMP::text)
);

CREATE TABLE docks (
    dock_id TEXT PRIMARY KEY,
    facility_id TEXT NOT NULL,
    dock_code TEXT NOT NULL,
    dock_type TEXT NOT NULL CHECK (dock_type IN ('STANDARD','REEFER','HEAVY')),
    supports_refrigerated INTEGER NOT NULL DEFAULT 0 CHECK (supports_refrigerated IN (0,1)),
    max_vehicle_weight_kg INTEGER NOT NULL CHECK (max_vehicle_weight_kg > 0),
    dock_status TEXT NOT NULL DEFAULT 'ACTIVE'
        CHECK (dock_status IN ('ACTIVE','MAINTENANCE','OUT_OF_SERVICE','INACTIVE')),
    UNIQUE (facility_id, dock_code),
    FOREIGN KEY (facility_id) REFERENCES facilities(facility_id)
);

CREATE TABLE drivers (
    driver_id TEXT PRIMARY KEY,
    carrier_id TEXT NOT NULL,
    driver_name TEXT NOT NULL,
    phone TEXT NOT NULL UNIQUE,
    licence_number TEXT NOT NULL UNIQUE,
    home_base_city TEXT,
    driver_status TEXT NOT NULL DEFAULT 'ACTIVE'
        CHECK (driver_status IN ('ACTIVE','OFF_DUTY','SUSPENDED','INACTIVE')),
    FOREIGN KEY (carrier_id) REFERENCES carriers(carrier_id)
);

CREATE TABLE facility_contacts (
    contact_id TEXT PRIMARY KEY,
    facility_id TEXT NOT NULL,
    contact_role TEXT NOT NULL,
    contact_name TEXT NOT NULL,
    email TEXT,
    phone TEXT,
    active_flag INTEGER NOT NULL DEFAULT 1 CHECK (active_flag IN (0,1)),
    FOREIGN KEY (facility_id) REFERENCES facilities(facility_id)
);

CREATE TABLE facility_rules (
    rule_id TEXT PRIMARY KEY,
    facility_id TEXT NOT NULL,
    rule_type TEXT NOT NULL,
    rule_value TEXT NOT NULL,
    description TEXT NOT NULL,
    effective_from TEXT,
    effective_to TEXT,
    active_flag INTEGER NOT NULL DEFAULT 1 CHECK (active_flag IN (0,1)),
    FOREIGN KEY (facility_id) REFERENCES facilities(facility_id)
);

CREATE TABLE vehicles (
    vehicle_id TEXT PRIMARY KEY,
    carrier_id TEXT NOT NULL,
    vehicle_type_code TEXT NOT NULL,
    registration_number TEXT NOT NULL UNIQUE,
    capacity_kg INTEGER NOT NULL CHECK (capacity_kg > 0),
    refrigeration_capable INTEGER NOT NULL DEFAULT 0 CHECK (refrigeration_capable IN (0,1)),
    active_flag INTEGER NOT NULL DEFAULT 1 CHECK (active_flag IN (0,1)),
    FOREIGN KEY (carrier_id) REFERENCES carriers(carrier_id),
    FOREIGN KEY (vehicle_type_code) REFERENCES vehicle_types(vehicle_type_code)
);

CREATE TABLE shipments (
    shipment_id TEXT PRIMARY KEY,
    order_reference TEXT NOT NULL UNIQUE,
    carrier_id TEXT NOT NULL,
    driver_id TEXT NOT NULL,
    vehicle_id TEXT NOT NULL,
    origin_name TEXT NOT NULL,
    origin_city TEXT NOT NULL,
    destination_facility_id TEXT NOT NULL,
    customer_name TEXT NOT NULL,
    product_category TEXT NOT NULL,
    load_weight_kg INTEGER NOT NULL CHECK (load_weight_kg > 0),
    pallet_count INTEGER CHECK (pallet_count IS NULL OR pallet_count >= 0),
    required_dock_type TEXT NOT NULL DEFAULT 'ANY'
        CHECK (required_dock_type IN ('ANY','STANDARD','REEFER','HEAVY')),
    temperature_control_required INTEGER NOT NULL DEFAULT 0
        CHECK (temperature_control_required IN (0,1)),
    priority_code TEXT NOT NULL DEFAULT 'NORMAL'
        CHECK (priority_code IN ('LOW','NORMAL','HIGH','CRITICAL')),
    planned_departure_ts TEXT NOT NULL,
    actual_departure_ts TEXT,
    original_eta_ts TEXT NOT NULL,
    latest_eta_ts TEXT,
    expected_unload_min INTEGER NOT NULL CHECK (expected_unload_min > 0),
    current_status TEXT NOT NULL
        CHECK (current_status IN ('PLANNED','ASSIGNED','IN_TRANSIT','AT_GATE','WAITING','IN_DOCK','COMPLETED','CANCELLED')),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (carrier_id) REFERENCES carriers(carrier_id),
    FOREIGN KEY (driver_id) REFERENCES drivers(driver_id),
    FOREIGN KEY (vehicle_id) REFERENCES vehicles(vehicle_id),
    FOREIGN KEY (destination_facility_id) REFERENCES facilities(facility_id)
);

CREATE TABLE appointment_slots (
    slot_id TEXT PRIMARY KEY,
    facility_id TEXT NOT NULL,
    dock_id TEXT NOT NULL,
    slot_start_ts TEXT NOT NULL,
    slot_end_ts TEXT NOT NULL,
    slot_status TEXT NOT NULL DEFAULT 'OPEN'
        CHECK (slot_status IN ('OPEN','BLOCKED','CLOSED')),
    block_reason TEXT,
    created_at TEXT NOT NULL,
    CHECK (slot_end_ts > slot_start_ts),
    UNIQUE (dock_id, slot_start_ts, slot_end_ts),
    FOREIGN KEY (facility_id) REFERENCES facilities(facility_id),
    FOREIGN KEY (dock_id) REFERENCES docks(dock_id)
);

CREATE TABLE chat_threads (
    thread_id TEXT PRIMARY KEY,
    driver_id TEXT NOT NULL,
    shipment_id TEXT,
    opened_at TEXT NOT NULL,
    closed_at TEXT,
    thread_status TEXT NOT NULL
        CHECK (thread_status IN ('OPEN','WAITING_FOR_DRIVER','WAITING_FOR_WAREHOUSE','RESOLVED','ESCALATED','CLOSED')),
    thread_intent TEXT NOT NULL
        CHECK (thread_intent IN ('REPORT_DELAY','ASK_SLOT_OPTIONS','CHECK_STATUS','EARLY_ARRIVAL','GENERAL_QUESTION','UNKNOWN')),
    FOREIGN KEY (driver_id) REFERENCES drivers(driver_id),
    FOREIGN KEY (shipment_id) REFERENCES shipments(shipment_id)
);

CREATE TABLE appointments (
    appointment_id TEXT PRIMARY KEY,
    shipment_id TEXT NOT NULL,
    slot_id TEXT NOT NULL,
    appointment_status TEXT NOT NULL
        CHECK (appointment_status IN ('PENDING_CONFIRMATION','CONFIRMED','IN_PROGRESS','COMPLETED','CANCELLED','NO_SHOW','REJECTED')),
    booking_source TEXT NOT NULL
        CHECK (booking_source IN ('PLANNER','DRIVER_CHAT','WAREHOUSE','SCHEDULING_TOOL','MANUAL_OVERRIDE')),
    is_current INTEGER NOT NULL DEFAULT 1 CHECK (is_current IN (0,1)),
    booked_at TEXT NOT NULL,
    confirmed_at TEXT,
    cancelled_at TEXT,
    cancellation_reason TEXT,
    replaced_appointment_id TEXT,
    warehouse_confirmation_ref TEXT,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (shipment_id) REFERENCES shipments(shipment_id),
    FOREIGN KEY (slot_id) REFERENCES appointment_slots(slot_id),
    FOREIGN KEY (replaced_appointment_id) REFERENCES appointments(appointment_id)
);

CREATE TABLE eta_updates (
    eta_update_id TEXT PRIMARY KEY,
    shipment_id TEXT NOT NULL,
    source_type TEXT NOT NULL
        CHECK (source_type IN ('ORIGINAL_PLAN','DRIVER_DECLARED','OPERATIONS_OVERRIDE','WAREHOUSE_ESTIMATE')),
    reported_by_driver_id TEXT,
    declared_eta_ts TEXT NOT NULL,
    confidence_code TEXT NOT NULL DEFAULT 'MEDIUM'
        CHECK (confidence_code IN ('LOW','MEDIUM','HIGH')),
    delay_reason_code TEXT
        CHECK (delay_reason_code IS NULL OR delay_reason_code IN ('TRAFFIC','BREAKDOWN','WEATHER','LATE_DEPARTURE','LOADING_DELAY','ROUTE_ISSUE','OTHER')),
    note TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY (shipment_id) REFERENCES shipments(shipment_id),
    FOREIGN KEY (reported_by_driver_id) REFERENCES drivers(driver_id)
);

CREATE TABLE facility_checkins (
    checkin_id TEXT PRIMARY KEY,
    shipment_id TEXT NOT NULL UNIQUE,
    facility_id TEXT NOT NULL,
    gate_in_ts TEXT,
    yard_queue_enter_ts TEXT,
    dock_in_ts TEXT,
    unload_start_ts TEXT,
    unload_end_ts TEXT,
    gate_out_ts TEXT,
    arrival_state TEXT
        CHECK (arrival_state IS NULL OR arrival_state IN ('EARLY','ON_TIME','LATE','NO_SHOW')),
    queue_state TEXT
        CHECK (queue_state IS NULL OR queue_state IN ('NOT_QUEUED','WAITING_EARLY','WAITING_LATE','WAITING_DOCK_UNAVAILABLE','CALLED_TO_DOCK','IN_DOCK','COMPLETED')),
    queue_position INTEGER CHECK (queue_position IS NULL OR queue_position > 0),
    actual_dock_id TEXT,
    notes TEXT,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (shipment_id) REFERENCES shipments(shipment_id),
    FOREIGN KEY (facility_id) REFERENCES facilities(facility_id),
    FOREIGN KEY (actual_dock_id) REFERENCES docks(dock_id)
);

CREATE TABLE dock_status_events (
    dock_event_id TEXT PRIMARY KEY,
    dock_id TEXT NOT NULL,
    event_type TEXT NOT NULL
        CHECK (event_type IN ('MAINTENANCE','BREAKDOWN','CAPACITY_REDUCTION','REOPENED','MANUAL_BLOCK')),
    event_start_ts TEXT NOT NULL,
    event_end_ts TEXT,
    reason TEXT NOT NULL,
    created_at TEXT NOT NULL,
    CHECK (event_end_ts IS NULL OR event_end_ts > event_start_ts),
    FOREIGN KEY (dock_id) REFERENCES docks(dock_id)
);

CREATE TABLE driver_exceptions (
    exception_id TEXT PRIMARY KEY,
    shipment_id TEXT,
    driver_id TEXT NOT NULL,
    thread_id TEXT NOT NULL,
    exception_type TEXT NOT NULL
        CHECK (exception_type IN ('DELAY','BREAKDOWN','TRAFFIC','WEATHER','EARLY_ARRIVAL','DOCK_UNAVAILABLE','UNKNOWN')),
    reported_at TEXT NOT NULL,
    reported_delay_min INTEGER CHECK (reported_delay_min IS NULL OR reported_delay_min >= 0),
    declared_eta_ts TEXT,
    earliest_acceptable_ts TEXT,
    latest_acceptable_ts TEXT,
    severity_code TEXT NOT NULL DEFAULT 'MEDIUM'
        CHECK (severity_code IN ('LOW','MEDIUM','HIGH','CRITICAL')),
    exception_status TEXT NOT NULL
        CHECK (exception_status IN ('OPEN','NEEDS_INFORMATION','SLOT_OPTIONS_SHARED','WAITING_CONFIRMATION','RESOLVED','ESCALATED','DUPLICATE','CANCELLED')),
    description TEXT NOT NULL,
    dedupe_key TEXT,
    FOREIGN KEY (shipment_id) REFERENCES shipments(shipment_id),
    FOREIGN KEY (driver_id) REFERENCES drivers(driver_id),
    FOREIGN KEY (thread_id) REFERENCES chat_threads(thread_id)
);

CREATE TABLE chat_messages (
    chat_message_id TEXT PRIMARY KEY,
    thread_id TEXT NOT NULL,
    sender_type TEXT NOT NULL
        CHECK (sender_type IN ('DRIVER','AGENT','OPERATIONS','WAREHOUSE','SYSTEM')),
    sender_reference TEXT,
    message_text TEXT NOT NULL,
    message_ts TEXT NOT NULL,
    external_message_id TEXT,
    is_duplicate INTEGER NOT NULL DEFAULT 0 CHECK (is_duplicate IN (0,1)),
    parsed_intent TEXT,
    extracted_eta_ts TEXT,
    requires_human_review INTEGER NOT NULL DEFAULT 0 CHECK (requires_human_review IN (0,1)),
    FOREIGN KEY (thread_id) REFERENCES chat_threads(thread_id)
);

CREATE TABLE operational_messages (
    operational_message_id TEXT PRIMARY KEY,
    shipment_id TEXT NOT NULL,
    appointment_id TEXT,
    channel TEXT NOT NULL CHECK (channel IN ('EMAIL','SMS','WHATSAPP','INTERNAL')),
    sender_address TEXT NOT NULL,
    recipient_address TEXT NOT NULL,
    subject TEXT,
    message_body TEXT NOT NULL,
    sent_at TEXT NOT NULL,
    delivery_status TEXT NOT NULL
        CHECK (delivery_status IN ('QUEUED','SENT','DELIVERED','FAILED','REPLIED')),
    reply_to_message_id TEXT,
    FOREIGN KEY (shipment_id) REFERENCES shipments(shipment_id),
    FOREIGN KEY (appointment_id) REFERENCES appointments(appointment_id),
    FOREIGN KEY (reply_to_message_id) REFERENCES operational_messages(operational_message_id)
);

CREATE TABLE users (
    user_id                 TEXT PRIMARY KEY,

    role_id                 TEXT NOT NULL,

    employee_code           TEXT UNIQUE,

    full_name               TEXT NOT NULL,

    email                   TEXT NOT NULL UNIQUE,

    phone_number            TEXT,

    password_hash           TEXT NOT NULL,

    driver_id               TEXT,

    facility_id             TEXT,

    is_active               INTEGER NOT NULL DEFAULT 1
        CHECK (is_active IN (0,1)),

    last_login_ts           TEXT,

    created_at              TEXT NOT NULL DEFAULT (CURRENT_TIMESTAMP::text),

    updated_at              TEXT,

    FOREIGN KEY(role_id)
        REFERENCES roles(role_id),

    FOREIGN KEY(driver_id)
        REFERENCES drivers(driver_id),

    FOREIGN KEY(facility_id)
        REFERENCES facilities(facility_id)
);

CREATE TABLE audit_logs (

    audit_id                TEXT PRIMARY KEY,

    user_id                 TEXT NOT NULL,

    action_type             TEXT NOT NULL
        CHECK(action_type IN (

            'LOGIN',

            'LOGOUT',

            'VIEW',

            'CREATE',

            'UPDATE',

            'DELETE',

            'BOOK_APPOINTMENT',

            'CANCEL_APPOINTMENT',

            'UPDATE_ETA',

            'SEND_MESSAGE'

        )),

    entity_name             TEXT NOT NULL,

    entity_id               TEXT,

    old_value_json          TEXT,

    new_value_json          TEXT,

    ip_address              TEXT,

    user_agent              TEXT,

    created_at              TEXT NOT NULL DEFAULT (CURRENT_TIMESTAMP::text),

    FOREIGN KEY(user_id)
        REFERENCES users(user_id)

);

CREATE TABLE api_logs (

    api_log_id              TEXT PRIMARY KEY,

    user_id                 TEXT,

    thread_id               TEXT,

    api_name                TEXT NOT NULL,

    http_method             TEXT,

    endpoint                TEXT,

    request_json            TEXT,

    response_json           TEXT,

    response_status         INTEGER,

    execution_time_ms       INTEGER,

    llm_model               TEXT,

    prompt_tokens           INTEGER,

    completion_tokens       INTEGER,

    total_tokens            INTEGER,

    created_at              TEXT NOT NULL DEFAULT (CURRENT_TIMESTAMP::text),

    FOREIGN KEY(user_id)
        REFERENCES users(user_id),

    FOREIGN KEY(thread_id)
        REFERENCES chat_threads(thread_id)

);

CREATE UNIQUE INDEX ux_active_appointment_per_slot
ON appointments(slot_id)
WHERE appointment_status IN ('PENDING_CONFIRMATION','CONFIRMED','IN_PROGRESS');

CREATE UNIQUE INDEX ux_current_active_appointment_per_shipment
ON appointments(shipment_id)
WHERE is_current = 1
  AND appointment_status IN ('PENDING_CONFIRMATION','CONFIRMED','IN_PROGRESS');

CREATE INDEX ix_shipments_destination_status
ON shipments(destination_facility_id, current_status);

CREATE INDEX ix_eta_updates_shipment_created
ON eta_updates(shipment_id, created_at DESC);

CREATE INDEX ix_slots_facility_time
ON appointment_slots(facility_id, slot_start_ts, slot_end_ts);

CREATE INDEX ix_chat_messages_thread_time
ON chat_messages(thread_id, message_ts);

CREATE INDEX ix_exceptions_status_time
ON driver_exceptions(exception_status, reported_at);

CREATE INDEX idx_users_role
ON users(role_id);

CREATE INDEX idx_users_driver
ON users(driver_id);

CREATE INDEX idx_users_facility
ON users(facility_id);

CREATE INDEX idx_audit_user
ON audit_logs(user_id);

CREATE INDEX idx_audit_created
ON audit_logs(created_at);

CREATE INDEX idx_api_user
ON api_logs(user_id);

CREATE INDEX idx_api_thread
ON api_logs(thread_id);

CREATE INDEX idx_api_created
ON api_logs(created_at);

CREATE VIEW v_latest_eta WITH (security_invoker = true) AS
WITH ranked AS (
    SELECT
        e.*,
        ROW_NUMBER() OVER (PARTITION BY shipment_id ORDER BY created_at DESC, eta_update_id DESC) AS rn
    FROM eta_updates e
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
FROM shipments s
LEFT JOIN ranked r ON r.shipment_id = s.shipment_id AND r.rn = 1;

CREATE VIEW v_slot_availability WITH (security_invoker = true) AS
SELECT
    sl.slot_id,
    sl.facility_id,
    d.dock_code,
    d.dock_type,
    d.supports_refrigerated,
    d.max_vehicle_weight_kg,
    sl.slot_start_ts,
    sl.slot_end_ts,
    CASE
        WHEN sl.slot_status <> 'OPEN' THEN sl.slot_status
        WHEN a.appointment_id IS NOT NULL THEN 'OCCUPIED'
        ELSE 'AVAILABLE'
    END AS availability_status,
    a.appointment_id,
    a.shipment_id,
    a.appointment_status
FROM appointment_slots sl
JOIN docks d ON d.dock_id = sl.dock_id
LEFT JOIN appointments a
    ON a.slot_id = sl.slot_id
   AND a.appointment_status IN ('PENDING_CONFIRMATION','CONFIRMED','IN_PROGRESS');

CREATE VIEW v_inbound_operational_state WITH (security_invoker = true) AS
SELECT
    s.shipment_id,
    s.driver_id,
    s.vehicle_id,
    s.destination_facility_id,
    s.priority_code,
    s.required_dock_type,
    s.temperature_control_required,
    s.load_weight_kg,
    s.expected_unload_min,
    s.current_status,
    le.effective_eta_ts,
    le.eta_source,
    le.eta_confidence,
    ap.appointment_id,
    sl.slot_id,
    sl.slot_start_ts,
    sl.slot_end_ts,
    d.dock_code AS planned_dock_code,
    fc.gate_in_ts,
    fc.queue_state,
    fc.queue_position,
    ad.dock_code AS actual_dock_code
FROM shipments s
JOIN v_latest_eta le ON le.shipment_id = s.shipment_id
LEFT JOIN appointments ap
    ON ap.shipment_id = s.shipment_id
   AND ap.is_current = 1
   AND ap.appointment_status IN ('PENDING_CONFIRMATION','CONFIRMED','IN_PROGRESS')
LEFT JOIN appointment_slots sl ON sl.slot_id = ap.slot_id
LEFT JOIN docks d ON d.dock_id = sl.dock_id
LEFT JOIN facility_checkins fc ON fc.shipment_id = s.shipment_id
LEFT JOIN docks ad ON ad.dock_id = fc.actual_dock_id;

CREATE VIEW v_current_facility_queue WITH (security_invoker = true) AS
SELECT
    fc.facility_id,
    fc.shipment_id,
    s.driver_id,
    s.vehicle_id,
    s.priority_code,
    fc.gate_in_ts,
    fc.arrival_state,
    fc.queue_state,
    fc.queue_position,
    le.effective_eta_ts,
    s.expected_unload_min,
    s.required_dock_type
FROM facility_checkins fc
JOIN shipments s ON s.shipment_id = fc.shipment_id
JOIN v_latest_eta le ON le.shipment_id = s.shipment_id
WHERE fc.queue_state IN ('WAITING_EARLY','WAITING_LATE','WAITING_DOCK_UNAVAILABLE','CALLED_TO_DOCK');

-- Deny direct Data API access until Auth/RLS policies are designed.
alter table public.carriers enable row level security;
revoke all on table public.carriers from anon, authenticated;
grant all on table public.carriers to service_role;
alter table public.vehicle_types enable row level security;
revoke all on table public.vehicle_types from anon, authenticated;
grant all on table public.vehicle_types to service_role;
alter table public.facilities enable row level security;
revoke all on table public.facilities from anon, authenticated;
grant all on table public.facilities to service_role;
alter table public.roles enable row level security;
revoke all on table public.roles from anon, authenticated;
grant all on table public.roles to service_role;
alter table public.docks enable row level security;
revoke all on table public.docks from anon, authenticated;
grant all on table public.docks to service_role;
alter table public.drivers enable row level security;
revoke all on table public.drivers from anon, authenticated;
grant all on table public.drivers to service_role;
alter table public.facility_contacts enable row level security;
revoke all on table public.facility_contacts from anon, authenticated;
grant all on table public.facility_contacts to service_role;
alter table public.facility_rules enable row level security;
revoke all on table public.facility_rules from anon, authenticated;
grant all on table public.facility_rules to service_role;
alter table public.vehicles enable row level security;
revoke all on table public.vehicles from anon, authenticated;
grant all on table public.vehicles to service_role;
alter table public.shipments enable row level security;
revoke all on table public.shipments from anon, authenticated;
grant all on table public.shipments to service_role;
alter table public.appointment_slots enable row level security;
revoke all on table public.appointment_slots from anon, authenticated;
grant all on table public.appointment_slots to service_role;
alter table public.chat_threads enable row level security;
revoke all on table public.chat_threads from anon, authenticated;
grant all on table public.chat_threads to service_role;
alter table public.appointments enable row level security;
revoke all on table public.appointments from anon, authenticated;
grant all on table public.appointments to service_role;
alter table public.eta_updates enable row level security;
revoke all on table public.eta_updates from anon, authenticated;
grant all on table public.eta_updates to service_role;
alter table public.facility_checkins enable row level security;
revoke all on table public.facility_checkins from anon, authenticated;
grant all on table public.facility_checkins to service_role;
alter table public.dock_status_events enable row level security;
revoke all on table public.dock_status_events from anon, authenticated;
grant all on table public.dock_status_events to service_role;
alter table public.driver_exceptions enable row level security;
revoke all on table public.driver_exceptions from anon, authenticated;
grant all on table public.driver_exceptions to service_role;
alter table public.chat_messages enable row level security;
revoke all on table public.chat_messages from anon, authenticated;
grant all on table public.chat_messages to service_role;
alter table public.operational_messages enable row level security;
revoke all on table public.operational_messages from anon, authenticated;
grant all on table public.operational_messages to service_role;
alter table public.users enable row level security;
revoke all on table public.users from anon, authenticated;
grant all on table public.users to service_role;
alter table public.audit_logs enable row level security;
revoke all on table public.audit_logs from anon, authenticated;
grant all on table public.audit_logs to service_role;
alter table public.api_logs enable row level security;
revoke all on table public.api_logs from anon, authenticated;
grant all on table public.api_logs to service_role;

revoke all on table public.v_latest_eta from anon, authenticated;
grant select on table public.v_latest_eta to service_role;
revoke all on table public.v_slot_availability from anon, authenticated;
grant select on table public.v_slot_availability to service_role;
revoke all on table public.v_inbound_operational_state from anon, authenticated;
grant select on table public.v_inbound_operational_state to service_role;
revoke all on table public.v_current_facility_queue from anon, authenticated;
grant select on table public.v_current_facility_queue to service_role;
