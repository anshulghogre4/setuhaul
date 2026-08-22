# Comparison — backend core / scheduling / db (correctness-critical layer)

> Scope: `backend/app/scheduling/{allocation,constraints,feasibility}.py`, `backend/app/core/{deps,envelope,errors,execution_context,middleware,security,settings,tls}.py`,
> `backend/app/db/session.py`, and all 6 files in `supabase/migrations/`. Compared against
> `SOLUTION_DESIGN.md` §0 (D1–D16), §0.9 (M1–M15), §5 (3-stage engine), §9.3 (migration sequence),
> and `ARCHITECTURE/SYSTEM_DESIGN.md` §4 (transaction boundary) and §6 (resilience). Every file below
> was read in full, including every migration's actual SQL. This is a doc-only output — nothing under
> `backend/`, `frontend/`, or `supabase/` was modified.

---

## 0. Headline finding — read this first

**D1 has not been built. Capacity correctness today rests entirely on two partial unique indexes on
`appointments`, not on a `dock_occupancy` table or a GiST exclusion constraint.** Both D1 preconditions
(§0 "D1 in concrete terms") are still false in the live schema:

- `btree_gist` is not installed anywhere in the 6 migration files (`grep -rn "CREATE EXTENSION"
  supabase/migrations/` → zero hits).
- Every timestamp column (`slot_start_ts`, `slot_end_ts`, `declared_eta_ts`, `gate_in_ts`, etc.) is still
  `TEXT`, exactly as the baseline created it (`supabase/migrations/20260805201923_setuhaul_baseline.sql:143-144,
  190-224, 230-235`). The **only** `timestamptz` usage in any of the 6 files is one inline cast inside a
  view's `ORDER BY` (`20260811233000_fix_v_latest_eta_timestamptz_order.sql:11`) — not a column type
  change, and irrelevant to D1.
- `dock_occupancy` does not exist. `grep -rn "dock_occupancy" backend/ supabase/` returns nothing.

This means `TASKS.md` Phase 1 steps 1.3, 1.4, and 1.5 are **0% done**, not partially done. Step 1.2
("reconcile migration drift" — is `20260817040000_escalation_resolution_note.sql` actually applied to the
live project?) cannot be verified from files on disk alone; that needs a live Supabase check, which is out
of this pass's tool access (no authenticated Supabase MCP session this run). Flagging rather than guessing,
per this persona's own research mandate.

Confirmed against current external guidance, not memory: the `EXCLUDE USING gist (dock_id WITH =, window
WITH &&)` pattern `SOLUTION_DESIGN.md` §0 specifies is exactly the documented industry-standard shape for
this problem (Neon's `btree_gist` docs and multiple independent Postgres-range-type writeups converge on
`EXCLUDE USING GIST (resource_id WITH =, period WITH &&)` for booking/double-booking prevention). The
design is not over-engineered here — it is the textbook answer the live code has not yet adopted.

---

## 1. `supabase/migrations/` — all 6 files, in applied order

| # | File | What it actually does |
|---|---|---|
| 1 | `20260805201923_setuhaul_baseline.sql` | Full 18-table baseline. All timestamp columns `TEXT`. Capacity control = two partial unique indexes: `ux_active_appointment_per_slot` on `appointments(slot_id) WHERE appointment_status IN (...)` (line 428-430) and `ux_current_active_appointment_per_shipment` on `appointments(shipment_id) WHERE is_current=1 AND ...` (line 432-435). RLS enabled on every table, all grants revoked from `anon`/`authenticated`, service-role only. |
| 2 | `20260807100550_add_users_auth_user_id.sql` | Adds `users.auth_user_id uuid` + unique partial index, linking Supabase Auth subjects to app users. Unrelated to D1. |
| 3 | `20260807184700_sprint2_idempotency_requests.sql` | Adds `idempotency_requests` table (M9's mechanism) — `idempotency_key` PK, `request_hash`, `response_json`, `expires_at` (still `TEXT`, not `timestamptz`). Also a partial unique index on `chat_messages.external_message_id`. |
| 4 | `20260811233000_fix_v_latest_eta_timestamptz_order.sql` | Fixes `v_latest_eta`'s `ORDER BY` to cast `created_at::timestamptz` instead of sorting lexicographically as text — a real bug fix (mixed `+05:30` seed data and `+00:00` app-written rows sorted wrong as text), but scoped to one view's ordering, not a column type change. |
| 5 | `20260812010000_sprint3_lifecycle_escalation.sql` | Widens `appointments.appointment_status` CHECK to add `'EXPIRED'` (needed for M8/D9). Widens `audit_logs.action_type` CHECK to add `RESCHEDULE_APPOINTMENT`/`REJECT_APPOINTMENT`/`EXPIRE_APPOINTMENT`. Creates `escalation_queue` (M11's table) with `escalation_type`, `escalation_status`, `severity_code`, `dedupe_key UNIQUE`, `resolved_by_user_id` — **no SLA-deadline column and no `owner`/assignee column**, which is what `SOLUTION_DESIGN.md` §6.1's table promises ("With SLA + owner") and what §7.5.5's `acknowledge_escalation`/`reassign_escalation` tools would need to write to. |
| 6 | `20260817040000_escalation_resolution_note.sql` | Adds `resolution_note` to `escalation_queue` and `driver_exceptions`. Small, correctly additive. |

**Keep as-is**: Migrations 2, 3, 4, 6 are small, correctly additive, well-commented with the actual
production incident or ADR that motivated them, and don't touch anything D1-related. Good migration
hygiene (`IF NOT EXISTS`, RLS + revoke-then-grant-service-role pattern repeated consistently).

**Needs improvement**: Migration 5's `escalation_queue` is missing the SLA/owner columns the design's own
data-model table promises for this exact table (§6.1). Right now `get_escalation_queue`'s described "Rows
ordered by time-to-SLA-breach ascending" (§7.5.5) has no column to order by, and `acknowledge_escalation`'s
"owner set to caller" (§7.5.5) has no column to set (`resolved_by_user_id` only fires on resolution, not on
acknowledgement).

**Functional requirement mapping**: M11 (escalation queue exists, mapped ✓ partially — table exists, full
contract per §7.5.5 does not). D9/M8 (EXPIRED status added to the CHECK constraint, mapped ✓ for the status
value; the automated 15-minute sweeper that would use it does not exist — see §3 below).

**Wrong optimisation flag**: None of these 6 migrations attempt D1 at all — not over-built, not
under-built for what they cover; they simply have not started the correctness-bedrock work yet. The real
flag is Phase 1's absence, covered in §0 above and repeated at the end of this document.

---

## 2. `backend/app/scheduling/feasibility.py` — Stage 1/2 (hard constraints + ranking)

**What it does**: `find_feasible_slots` (line 321) pulls the shipment + latest ETA + facility, then queries
up to 200 `appointment_slots` candidates joined against `docks`, active `appointments`, and overlapping
`dock_status_events` (lines 396-422), evaluates each through `evaluate_candidate_slot` (line 185), and
returns a ranked, capped list plus an `escalation` payload when none survive.

**Keep as-is**:
- The eight Stage-1 checks in `evaluate_candidate_slot` map directly onto `constraints.json`'s
  `feasibility_hard_constraints` (slot open, no active appointment, no dock event overlap, dock ACTIVE,
  dock-type compatibility, refrigeration, weight limit, ETA+unload fits inside slot, facility hours) — this
  is a faithful, deterministic, in-code implementation of §5 Stage 1, not delegated to the LLM anywhere.
  Matches M3.
- The comment at lines 195-203 explaining why cheap, timestamp-independent checks run before
  `_parse_timestamp` is a real, specific, well-reasoned ordering decision (legacy truncated-seconds rows
  parse fine in Postgres's own cast but not in `datetime.fromisoformat`) — good defensive engineering, not
  cargo-culted.
- `_rank_slot` (line 116) implements §5 Stage 2's exact formula: priority score + lateness (capped,
  `+4/min`) + wait-after-ETA (`-6/min`) + fit-slack (capped, `+1/min`) + non-exact-dock penalty (`-25`),
  pulled from `constraints.json`'s `ranking_policy.score_weights` rather than hardcoded twice — one source
  of truth for the weights. Matches D7's "shipped policy is exactly the specification above."
  `stable_tiebreaker` (line 160) plus the final `.sort()` (line 441, tie-broken by `shipment_id`/`slot_id`)
  gives the zero-randomness, deterministic-order guarantee M4 requires.
- `recommendation_id_for` (line 72) is a deterministic SHA-256 fingerprint over
  `shipment_id|policy_version|effective_eta_ts|option_slot_ids` — this is the staleness-detection mechanism
  M10 needs, and it is a pure function of inputs, so it reproduces byte-identically. Good M4/M10
  implementation even though it lives as a hash rather than a persisted `slot_recommendations` row (see
  below).
- `_assert_scope` (line 307) derives the caller's allowed shipment set from `ctx.driver_id` /
  `ctx.facility_id` — both populated server-side from the verified-JWT → DB lookup in `core/deps.py`, never
  from a client argument. This is M15 done correctly at the point of use.

**Needs improvement**:
- **Stage 0 (multi-day search horizon) does not exist.** `SOLUTION_DESIGN.md` §5 Stage 0 requires a
  rolling 48-hour horizon and a `NO_SAME_DAY_SLOT` vs `NO_FEASIBLE_SLOT` distinction so "no slot tonight"
  does not always read as an escalation. `find_feasible_slots` queries `appointment_slots` with only
  `CAST(sl.slot_end_ts AS timestamptz) > :eta_ts` (line 415) and a `LIMIT 200` (line 417) — there is no
  explicit horizon bound, and more importantly no distinction anywhere in `FeasibleSlotsResult` between
  "nothing today, try tomorrow" and "nothing anywhere in range, escalate." Every empty-options case produces
  the single `escalation` block (line 452-464) with `"recommended_human_queue": "OPERATIONS_EXCEPTION_QUEUE"`
  — i.e. today's code treats every no-slot outcome as escalation-worthy, which is exactly the "wrong
  default answer" §5 Stage 0 was written to correct.
- **No `slot_recommendations` persistence.** §6.1's table for "what was shown, to whom, when, against which
  snapshot" doesn't exist; staleness is instead re-derived by recomputing `recommendation_id_for` and
  comparing against a Redis flag (`ConversationMemory.is_recommendation_stale`, called from
  `allocation.py:483`). Functionally this satisfies M10 for the common case, but it means "you saw X, here's
  why it changed" (§6.1's stated purpose) has no durable record once the 24h Redis TTL passes or Redis is
  cold — which directly collides with `SYSTEM_DESIGN.md` §6.2's own chaos-lite requirement that "freshness
  comes from the database, never from cache." Today, for this one purpose, freshness partially *does* come
  from cache (Redis), with the DB-hash comparison as the only fallback once Redis is silent.
- Candidate weight/reefer checks (lines 234-240) correctly compare `shipments.load_weight_kg` against
  `docks.max_vehicle_weight_kg` and `temperature_control_required` against `supports_refrigerated` — this
  matches §5 Stage 1's two data-forced corrections. Good. But there is no equivalent check for
  `facility_rules.effective_from/effective_to` (RULE003/RULE004/RULE005 in §5 Stage 1's "Add four the
  dataset demands") or for `driver_exceptions.latest_acceptable_ts`/`earliest_acceptable_ts`. Those four
  additional hard constraints the design calls for are simply absent from `evaluate_candidate_slot`.

**Functional requirement mapping**: M2 (latest-ETA-only, `latest_eta_only`/`STALE_ETA` constraint, line
96-98 of `constraints.json`, enforced via the `v_latest_eta` join) ✓. M3 (Stage 1, eight of the design's
constraints implemented; four — facility-rule effectivity windows, driver latest/earliest-acceptable —
not yet) partial. M4 (deterministic ranking + receipt) ✓. M10 (stale options refused) ✓ functionally, ⚠
persistence gap noted above.

**Wrong optimisation flag**: The 200-row candidate cap with an in-Python loop (lines 396-439) is reasonable
at current data volume, but note it explicitly for the volume the design targets: D8's seven-day,
600-1,000-shipment, 2,000-3,000-slot generator will make "top 200 slots by start time, then filter in
Python" a real scan cost per feasibility call, against a `<50ms` budget the design states explicitly (§0
"Budget `find_feasible_slots` at <50ms"). This is not over-engineering — it is the opposite: the current
implementation has no index-assisted range filtering because there is no `dock_occupancy`/`tstzrange`
column to index on yet. Once D1 lands, this query should be rewritten against the GiST-indexed table rather
than against `TEXT` timestamp casts, which is exactly the ordering `SOLUTION_DESIGN.md` §0 states ("Database
before tools before UI").

---

## 3. `backend/app/scheduling/allocation.py` — Stage 3 (transactional claim) + lifecycle transitions

**What it does**: `request_slot` (line 774) is the Stage-3 claim path — row-locks the shipment (`FOR UPDATE
OF s`, line 828) and the slot (`FOR UPDATE OF sl`, line 897), re-validates through
`evaluate_candidate_slot`, and inserts a `PENDING_CONFIRMATION` appointment inside a `try/except
IntegrityError` block (lines 963-1045) that maps a unique-constraint violation to
`SLOT_CONFLICT_REFRESH_REQUIRED`. `confirm_appointment` (line 658), `reject_appointment`/`expire_appointment`
(via the shared `_ops_pending_transition` at line 1083), `cancel_appointment` (line 538), and
`reschedule_appointment` (line 1184) round out the lifecycle.

**Keep as-is**:
- Idempotency is real and load-bearing, not decorative: every mutating function computes `payload_hash`
  (e.g. line 550, 670, 786) and calls `lookup_idempotency` before doing anything, replaying the stored
  response on a repeat key+payload rather than re-executing (this is exactly M9's THR001/THR009 duplicate-
  intake requirement, implemented at the transport layer generically rather than special-cased per route).
- `allocation_unique_constraint_name` (line 200) correctly maps a caught `IntegrityError` back to one of
  the two named unique indexes and turns it into a typed `SLOT_CONFLICT_REFRESH_REQUIRED` outcome with
  fresh options attached (`_conflict_result`, line 413) — this is the right shape for what §5 Stage 3
  demands ("The loser catches the constraint violation, is mapped to `SLOT_CONFLICT_REFRESH_REQUIRED`, and
  is handed fresh options — never a corrupted state, never a 5xx"). The *mechanism* underneath (a unique
  index rather than a GiST exclusion constraint) is the real gap — see below — but the *code pattern* around
  whatever constraint exists is correct and would carry over unchanged once `dock_occupancy` lands.
- Every mutating path re-reads the row post-commit (`_reread_appointment`, called after every commit, e.g.
  lines 654, 770, 1071, 1318) before returning it to the caller — satisfies `constraints.json`'s own
  `write_safety.required_for_business_writes` list ("post-commit authoritative reread").
- Every transition writes a paired `audit_logs` row in the same transaction as the state change (e.g. lines
  603-634, 722-750, 1128-1147) — this is M14 done correctly: the audit record cannot exist without the
  business write, or vice versa, because they share one `session`/transaction and one `commit()`.
- Scope assertions (`_assert_driver_scope`/`_assert_read_scope`/`_assert_ops_scope`, lines 146-174) live in
  this service module, not in the router (`api/v1/routers/scheduling.py`) and not as a tool-schema
  parameter — `shipment_id` is looked up from the DB and the *caller's own* `ctx.driver_id`/`ctx.facility_id`
  is what's compared, never a client-supplied `facility_id`/`carrier_id`. This is the exact pattern §7.5's
  opening principle requires and the exact violation `TASKS.md` 5.3 was written to audit for — on this file,
  the audit passes.
- `reschedule_appointment`'s comment block at lines 1212-1214 and 1248-1256 is unusually good self-documentation
  of a real subtlety (why the staleness hash must *not* be re-checked against the post-cancel snapshot) —
  worth calling out as a positive example of recording *why*, not just *what*.

**Needs improvement — this is the load-bearing finding for this file**:
- **The Stage-3 "database itself decides the winner" claim in `SOLUTION_DESIGN.md` §5 is not actually true
  of this code, because the constraint being raced on is a *slot-row* unique index, not a *dock-time-interval*
  exclusion constraint.** `request_slot`'s `INSERT` (lines 964-984) can only conflict with another row that
  targets the exact same `slot_id`. Two different `appointment_slots` rows on the same dock with overlapping
  real time windows — the precise defect `SOLUTION_DESIGN.md` §0/§5 names ("a 75-minute unload booked at
  11:00 colliding with a booking at 12:00 — because those are different slot rows") — are **not caught by
  anything in this file.** The row locks at lines 828 and 897 only serialise contenders for the *same*
  shipment row and the *same* slot row respectively; per `SYSTEM_DESIGN.md` §4's own framing, this is
  exactly the "`SELECT … FOR UPDATE` on a slot row" pattern the design explicitly says is weaker than the
  GiST exclusion constraint, still in place today.
- **The sweeper-vs-confirm race (§9.2 #3, `SYSTEM_DESIGN.md` §4's second named must-share-a-transaction
  operation) is not implemented as a race resolution at all, because there is no sweeper.** `expire_appointment`
  (line 1173, routed through `_ops_pending_transition` at line 1083) is only reachable via the
  ops-authenticated REST endpoint `POST /appointments/{id}/expire` (`api/v1/routers/scheduling.py:272-290`,
  guarded by `require_roles(*OPS_PORTAL_ROLES)`). Repo-wide search (`grep -rn "sweep|EventBridge|APScheduler|
  scheduler|cron" backend/`) finds nothing that calls it automatically. D9's 15-minute PENDING TTL is
  therefore **not enforced anywhere** — a `PENDING_CONFIRMATION` row simply sits until a human manually
  expires or confirms it. M8 ("Pending expiry releases capacity") is unmet.
  - The good news inside this gap: *if* a sweeper existed and called `expire_appointment` through this same
    code path, the actual concurrent-access race with `confirm_appointment` would be correctly serialized —
    both go through `_locked_appointment`'s `SELECT … FOR UPDATE` (line 268) inside their own transaction, so
    a second transaction blocks until the first commits and then observes the new `appointment_status`. What
    is *not* correct even in that hypothetical: `_ops_pending_transition`'s guard (line 1110) raises a
    generic `AppError(code="INVALID_APPOINTMENT_TRANSITION", status_code=409)` when the row has already
    moved — not the `ALREADY_ACTIONED` outcome with "the winning transition named" that §7.5.1 explicitly
    requires so a planner who loses the race gets a reason rather than a bare refresh. The transactional
    *safety* is present in the row-lock pattern; the *typed, explainable outcome* the design mandates is not.
- **No `HELD` state, so D2's soft hold with 90-second TTL does not exist.** `request_slot` inserts a
  `PENDING_CONFIRMATION` row directly (line 972) — there is no intermediate `HELD` row, no `expires_at`
  column anywhere in `appointments`, and `ACTIVE_APPOINTMENT_STATUSES` (line 27) never includes `'HELD'`.
  `constraints.json`'s own `appointment_lifecycle.requested_or_held` field (line 137: "A bounded hold/request
  exists only after an authorized transactional write") reads as if it anticipated this state but it was
  never built. Practical effect: every driver slot selection immediately consumes a
  `PENDING_CONFIRMATION`-tier capacity claim with no TTL of its own (only the *outer* 15-minute pending TTL,
  which — per the point above — is also unenforced), rather than a cheap, auto-expiring 90-second reservation
  that would let a driver's indecision or dropped connection self-heal without waiting on a human. This
  compounds the D2+D6 risk `SOLUTION_DESIGN.md` §0 calls "the one real risk in this design": today there is
  neither the fast self-expiring layer (D2) nor the slower human-triggered one (D9) actually running.
- `bulk_confirm` (§7.5.1) does not exist in this file or the router — every confirm is single-appointment,
  so the described spike-clearing throughput path for the planner console has no backing implementation yet.

**Functional requirement mapping**: M6 (capacity never double-promised) — **partially met, and met for the
wrong reason**: correctness today comes from `ux_active_appointment_per_slot`/`ux_current_active_appointment_per_shipment`
(one-slot-id-at-a-time, one-active-appointment-per-shipment), which happens to be sufficient only because
`appointment_slots` rows in the current seed don't overlap in real time across different rows for the same
dock in a way the app has been tested against — it is not sufficient by construction, which is D1's entire
point. M7 (human confirms PENDING→CONFIRMED, D6) ✓ — `confirm_appointment` requires `OPS_PORTAL_ROLES`
(`api/v1/routers/scheduling.py:220`), no code path lets a rule or the LLM call it directly. M8 (pending
expiry releases capacity) ✗ — mechanism exists (`expire_appointment`) but nothing triggers it on a timer.
M9 (idempotent intake) ✓. M14 (audit) ✓ for every transition in this file.

**Wrong optimisation flag — bluntly**: This is the highest-stakes gap in the entire review. The code
*behaves* as though Stage 3's concurrency guarantee is in place — it has the right shape (row locks,
`IntegrityError` → typed conflict, idempotency, audit) — but the actual invariant it enforces (`one
appointment per slot_id`) is strictly weaker than the invariant the product needs (`no two dock-time
intervals overlap for one dock`). A 50-way race per `SOLUTION_DESIGN.md` §10's own verification test would
currently pass *only* because all 50 contenders target one `slot_id`; run the same race across two adjacent,
overlapping `appointment_slots` rows on the same dock and this code has no defense at all. This is not a
theoretical gap — it is precisely the defect D1 was written to fix, still present, unflagged by any test in
this file or its router. Do not let the presence of *a* unique-constraint-catch pattern read as "M6 is
done" — it is not.

---

## 4. `backend/app/scheduling/constraints.py` (+ `constraints.json`)

**What it does**: `load_scheduling_constraints` (line 79) reads a bundled `constraints.json` once
(`lru_cache`) and validates it into a typed `SchedulingConstraints` model — the single source for policy
version, hard-constraint list, ranking weights, lifecycle vocabulary, and write-safety rules that
`feasibility.py`/`allocation.py` both consume.

**Keep as-is**: Using one Pydantic-validated JSON file as the shared contract between the two scheduling
modules (rather than duplicating weight constants) is good practice — it's exactly what lets
`feasibility.py`'s ranking and `allocation.py`'s checked-constraints list stay in lockstep. `extra="forbid"`
on `SchedulingConstraints` (line 56) means a typo'd or removed key fails loudly at load time rather than
silently defaulting.

**Needs improvement**: `SOLUTION_DESIGN.md` §5 Stage 2 explicitly calls for weights to live in a
`policy_versions` **table** — "admin-editable, auditable, and reproducible... 'Which policy produced this
promise?' must be answerable a month later." Today `policy_version` is a string
(`"sprint3_constraints_v1"`, `constraints.json:2`) baked into a file shipped with the backend build. It is
stamped onto every decision (e.g. `allocation.py:1007`) so the *traceability* half of the requirement is
met, but the *admin-editable without a deploy* half is not — changing a weight today means editing the JSON
and redeploying (and, per `AGENTS.md`'s own hard rule, re-staging the AgentCore codezip snapshot), not an
audited admin-console action. §7.5.7's `create_facility_rule`/policy-management tools, once built, would
have nothing to write to.

**Functional requirement mapping**: D7 (policy = specified formula, `w_fairness` reserved-but-zero) — the
formula in `feasibility.py` matches; there is no explicit `w_fairness=0` term visible in
`ranking_policy.score_weights` (line 123-130 of `constraints.json`) the way §5 Stage 2 describes reserving a
named slot for it — it is simply absent rather than present-and-disabled, which is a smaller gap than it
sounds (nothing currently *contradicts* D7) but means "enabling the term is a policy decision with an audit
trail" (§5) has no field to flip yet.

**Wrong optimisation flag**: None — a cached, validated, file-backed config is a reasonable stopgap for a
single-policy-version system; the flag is the same "not yet a DB table" gap named above, not overbuilding.

---

## 5. `backend/app/core/security.py`, `deps.py`, `execution_context.py` — M15 (RBAC with scope)

**What they do**: `JwtVerifier.verify_access_token` (`security.py:36`) verifies a Supabase-issued JWT via
JWKS (issuer, audience, expiry, subject, `ES256`/`RS256`/`HS256`), never trusting an unverified claim.
`get_execution_context` (`deps.py:84`) takes the verified `sub`, looks up the corresponding row in
`public.users` joined to `roles` (line 97-111), and builds a frozen `ExecutionContext`
(`execution_context.py:17`) carrying `driver_id`/`facility_id`/`role_name` — all **server-derived**, never
accepted from the client.

**Keep as-is**:
- This is the correct architecture for M15/§7.5's opening principle. `ExecutionContext` is `frozen=True`
  (line 20) — it cannot be mutated after construction by a later handler. The DB lookup (`deps.py:97-111`)
  is keyed on `auth_user_id = CAST(:auth_user_id AS uuid)` from the JWT's verified `sub`, not from any
  header or body field the client controls. Combined with §2's scope-check functions in `allocation.py`/
  `feasibility.py` (already reviewed above), the full chain — verify token → server-side identity lookup →
  compare caller's own scope against the resource's true owner — is intact end to end for every path this
  review covers.
- `JwtVerifier` correctly rejects a token whose issuer/audience don't match (`jwt.decode(...,
  audience=..., issuer=...)`, `security.py:39-47`), sets a 300-second leeway (reasonable clock-skew
  tolerance, not a security hole), and re-fetches the JWKS client hourly (line 24) rather than caching it
  forever — a defensible key-rotation posture.
- `require_roles` (`deps.py:142`) is a real FastAPI dependency-level allowlist gate, not a comment or a
  convention — every ops-only route in `scheduling.py` (confirm, reject, expire) is wired through it.

**Needs improvement**:
- `SOLUTION_DESIGN.md` §6.1 lists `user_scopes` as a genuinely new table needed for RBAC-with-scope: "the
  scoping half of RBAC (facility / carrier / driver)... `users`, `roles`, `audit_logs` and `api_logs`
  already exist." `user_scopes` does not exist in any of the 6 migrations, and `deps.py`'s lookup instead
  reads a single `driver_id`/`facility_id` column directly off `users` (`deps.py:101-102`). This models
  "one user, one facility (or one driver)" — correct for today's v1 persona set, but it cannot express a
  regional/multi-facility ops role or a carrier-scoped user (carriers aren't modelled as an identity scope
  at all in `users` yet — no `carrier_id` column). §0.9's own "Two consequences" callout ("carrier scoping
  must be enforced in the data-access layer from the first query") is not yet buildable on this schema for
  the carrier-portal catalog (§7.5.6), because there is nowhere server-side to read a caller's `carrier_id`
  from.
- `TASKS.md` Phase 5.2 asks specifically whether scope resolution happens "in the repository layer — not
  the router, not the tool schema." The honest answer for this codebase: it happens in a FastAPI
  *dependency* (`deps.py`), which is architecturally closer to "framework wiring that hands the service
  layer a trusted identity" than either a router doing its own lookup or a tool schema accepting an id — a
  defensible middle ground, but worth naming precisely rather than rounding to "yes" or "no."

**Functional requirement mapping**: M15 ✓ for the driver/facility-operator/admin scoping that exists today;
⚠ not yet extended to carrier scoping (no `carrier_id` on any identity path) or to a many-to-many
`user_scopes` model. `server_authoritative_auth` (`constraints.json` line 40-41) — the stated non-negotiable
invariant — is genuinely upheld by this code, not just declared.

**Wrong optimisation flag**: None — this is right-sized for the v1 persona set (driver, single-facility
ops, admin) the migrations actually support. It would become under-built the moment a carrier-portal or
multi-facility-ops user needs to authenticate, because there is no scope table to extend into; that is a
schema gap (§6.1's `user_scopes`), not a code-complexity gap.

---

## 6. `backend/app/core/middleware.py` — resilience (§6)

**What it does, in full**: one class, `RequestIdMiddleware` (16 lines) — reads or generates an
`X-Request-ID`, stashes it on `request.state`, echoes it back on the response header. That is the entire
contents of this file.

**Needs improvement — significant, and worth being direct about**: `SYSTEM_DESIGN.md` §6 specifies a
circuit breaker for the LLM provider (§6.3: CLOSED/OPEN/HALF-OPEN, sized against measured "~5% of LLM call
spans error"), a bulkhead capping concurrent in-flight LLM calls (§6.4), a derived per-call timeout ceiling
of ~800ms-1s (§6.5), and jittered retry gated on idempotency (§6.6). **None of this exists in
`middleware.py`, and nothing else in this review's scope implements it either** — `db/session.py` has
connection-pool sizing (reviewed below) but no request-level timeout/breaker logic, and no other file in
this file list touches LLM-call resilience at all (that machinery, if it exists, would live in
`app/assistant/`, outside this review's assigned scope).

**Keep as-is, correctly**: the one hard rule §6.1 states — "Circuit breakers belong on external and
optional dependencies. Never on the correctness path" — is trivially satisfied today, because there is no
circuit breaker anywhere to misapply to Postgres. Absence of a wrongly-placed breaker is not the same as
presence of a correctly-placed one; see below.

**Functional requirement mapping**: No M-number maps directly to §6 (it's an NFR out of `SYSTEM_DESIGN.md`,
not `SOLUTION_DESIGN.md`'s M-list), but §6.2's per-dependency failure matrix implies concrete NFRs (p95 <
2.5s per `TECH_STACK.md`, LLM breaker, Postgres fail-loud). None of the LLM-facing NFRs are implemented in
this file; the Postgres fail-loud NFR is satisfied only by *default* SQLAlchemy/asyncpg exception
propagation (an unhandled `OperationalError` surfaces as a 500 via `unhandled_error_handler` in
`errors.py:64`) rather than by any deliberate "fail loudly, no fallback, no cache-serve" logic — which
happens to be the right behavior today, but by omission rather than by design.

**Wrong optimisation flag**: This is the second-most load-bearing gap in the review, just under §3's
allocation.py finding. `middleware.py` is not over-engineered — it is essentially empty relative to what
§6 specifies. If LLM-provider resilience genuinely lives entirely in `app/assistant/` (outside this pass's
scope) that would be the *right* location per §6's own module boundaries, but this file's name and this
review's assignment both suggest `core/middleware.py` was the expected home for at least the bulkhead/
timeout cross-cutting pieces, and it is not there. Flag for the `app/assistant/` owner to confirm one way or
the other rather than assuming either "already handled elsewhere" or "missing entirely."

---

## 7. `backend/app/core/envelope.py`, `errors.py`, `settings.py`, `tls.py` — supporting core

**What they do**: `envelope.py` defines the `{success, message, data, timestamp, request_id}` /
`{success, message, errors[], ...}` response shape used by every router in this review (`ok()`/`fail()`).
`errors.py` defines `AppError` and FastAPI exception handlers that route `AppError`, `HTTPException`,
`RequestValidationError`, and any unhandled `Exception` through that same envelope shape. `settings.py` is
a `pydantic_settings.BaseSettings` reading `.env`/`.env.local` from either `backend/` or the repo root, with
typed `ready_*` properties for DB/auth/LLM/Upstash readiness. `tls.py` is a 15-line best-effort
`truststore.inject_into_ssl()` wrapper for corporate-proxy TLS interception, swallowing any import/injection
failure silently (logged at `debug` level only).

**Keep as-is**:
- The consistent success/error envelope shape is genuinely used everywhere in `scheduling.py` (verified
  above) — one contract, not reinvented per router. `unhandled_error_handler` (`errors.py:64`) truncates
  the raw exception string to 500 chars (line 71) before putting it in a client-facing response — a small
  but real defensive choice against leaking an overly long stack-trace-derived message.
- `settings.py`'s comment on `database_url` pointing at the session-mode pooler (referenced from
  `db/session.py`, reviewed next) is consistent between the two files — no drift between where the setting
  is declared and where its constraint is enforced.
- `tls.py`'s silent-catch-and-log-at-debug is deliberately low-severity because it's a *best-effort*
  enhancement (use the OS trust store if `truststore` is importable) rather than a security control — failing
  open here is the correct choice, not a swallowed real error.

**Needs improvement**: `settings.py`'s `client_supplied_fields_to_ignore_for_authority` list lives in
`constraints.json` (`write_safety.client_supplied_fields_to_ignore_for_authority`, lines 183-190), not in
`settings.py` or any enforcement code path in this review's scope — it is documentation of intent, not a
mechanism. The actual enforcement is the pattern already verified in §5 above (scope derived from
`ExecutionContext`, never from a request body field) — so the intent is upheld in practice, but there is no
single place that mechanically enforces "if a client sends `facility_id` in a body, ignore it," short of
every Pydantic command model in `allocation.py` simply never declaring such a field (which is in fact the
case, verified across all command models in §3 — `RequestSlotCommand`, `CancelAppointmentCommand`, etc.
carry no `facility_id`/`carrier_id`/`driver_id` field anywhere).

**Functional requirement mapping**: No direct M-number; these are cross-cutting infra that other M's depend
on (M14's audit records inherit `errors.py`'s consistent shape when a write fails partway; M9's idempotency
responses are wrapped in the same envelope).

**Wrong optimisation flag**: None in any of these four files — appropriately small, single-purpose, no
speculative generality.

---

## 8. `backend/app/db/session.py` — connection management

**What it does**: `Database.configure` (line 22) builds one `AsyncEngine` per process via
`create_async_engine`, forcing `postgresql+asyncpg://`, `connect_args={"statement_cache_size": 0}`, and a
deliberately small `pool_size=3, max_overflow=2` (lines 27-56).

**Keep as-is, and confirmed against current external guidance, not memory**: the two large comments (lines
30-41 and 43-53) document a real, previously-reproduced production incident (`DuplicatePreparedStatementError`
under Supavisor transaction-mode pooling, and a global-connection-budget exhaustion under session mode) and
the fix taken for each. Checked against current third-party documentation of the same asyncpg + Supavisor/
PgBouncer interaction: the standard fix for asyncpg's server-side prepared-statement caching colliding with
a connection multiplexer is exactly `statement_cache_size=0` (paired with `prepared_statement_cache_size=0`
in some write-ups) — this code uses session-mode pooling (port 5432, one physical backend per pooled
connection for its lifetime) specifically *because* that mode supports prepared statements safely, which
matches current guidance that transaction-mode pooling is the mode requiring the disable-prepared-statements
workaround. The small `pool_size=3`/`max_overflow=2` is a defensible, explicitly-reasoned response to a
real global pool-size ceiling (documented as Supavisor's configured `pool_size=15` in the comment), sized so
multiple concurrent ECS/AgentCore containers can coexist rather than one process claiming the whole budget.
This is exactly the kind of "verify current docs, not intuition" case this persona's own mandate names, and
it holds up.

**Needs improvement**: `Database.session()` (line 59) is a single async context manager yielding one
session per call; nothing in this file enforces or documents *transaction boundaries* across multiple
service calls within one request — that discipline currently lives entirely in each function in
`allocation.py` (explicit `session.commit()`/`session.rollback()` calls, reviewed in §3). That is workable
today because every mutating flow in `allocation.py` is a single function using one session end-to-end, but
it means `SYSTEM_DESIGN.md` §4's "three operations must share a single transaction" rule is enforced by
convention across `allocation.py`'s functions, not by anything in `session.py` that would catch a future
call site accidentally splitting a `dock_occupancy` write and its audit row across two sessions. Worth a
lint/review-checklist note once `dock_occupancy` writes exist, since that is precisely the operation §4 names
first.

**Functional requirement mapping**: Indirectly supports M6/M9/M14 by keeping each mutating flow inside one
session; no direct M-number of its own.

**Wrong optimisation flag**: None. `pool_size=3`/`max_overflow=2` looks small in isolation but is the
*correct*, evidence-based size given a shared 15-connection Supavisor budget across multiple concurrent
compute containers — sizing it larger without also raising the Supavisor-side budget would silently
reproduce the exact incident the comment describes. This is right-sized, not under-provisioned.

---

## 9. Cross-cutting summary against the four review categories

| Area | Keep as-is | Needs improvement | FR mapping | Wrong-optimisation flag |
|---|---|---|---|---|
| Migrations (6 files) | 4 of 6 are clean, well-motivated, additive | `escalation_queue` missing SLA/owner columns | M11 partial, D9 status value ✓ | Phase 1 (D1) not started — see §0 |
| `feasibility.py` | Stage 1/2 logic, determinism, scoping | No Stage 0 horizon/escalation split; no `slot_recommendations` table; 4 hard constraints missing | M2 ✓, M3 partial, M4 ✓, M10 ✓ w/ persistence gap | 200-row Python-side scan will miss the `<50ms` budget at D8 scale without index-assisted range filtering |
| `allocation.py` | Idempotency, audit pairing, scope checks, self-documented reschedule logic | **M6 enforced by the wrong mechanism (slot-id uniqueness, not interval-overlap exclusion)**; no sweeper → M8 unenforced; no HELD state → D2 absent; race outcome not typed as `ALREADY_ACTIONED` | M6 partial/wrong-mechanism, M7 ✓, M8 ✗, M9 ✓, M14 ✓ | **Highest-stakes flag in this review: Stage 3's core guarantee is not actually built, only its surrounding pattern is** |
| `constraints.py`/`.json` | Shared typed contract, cache | Weights in a file, not a `policy_versions` table | D7 mostly ✓, no reserved `w_fairness=0` field | None |
| `security.py`/`deps.py`/`execution_context.py` | Server-derived identity end to end, frozen context | No `user_scopes` table; no carrier scoping path | M15 ✓ for v1 personas, ⚠ for carrier/multi-facility | None |
| `middleware.py` | Correctly avoids circuit-breaking Postgres (by omission) | **Effectively empty relative to §6's breaker/bulkhead/timeout/retry requirements** | No direct M-number; §6 NFRs unmet here | Second-highest flag: confirm with the `app/assistant/` owner whether this logic lives elsewhere, or is simply missing |
| `envelope.py`/`errors.py`/`settings.py`/`tls.py` | All four, no changes needed | Client-field-ignore list is intent-only, enforced by omission elsewhere | Supports M9/M14 indirectly | None |
| `db/session.py` | Pool sizing and pooling-mode choice, confirmed against current external guidance | Transaction-boundary discipline is convention, not mechanism | Supports M6/M9/M14 indirectly | None — correctly sized against real evidence |

---

## 10. What this means for `TASKS.md`

- **Phase 0.1** (confirm `scheduling/{feasibility,allocation}.py` and `db/session.py` exist at the assumed
  paths): confirmed — all three exist exactly where `TASKS.md` assumed, plus `scheduling/constraints.py`,
  which the task list didn't separately name but which both other modules depend on.
- **Phase 0.5** (re-run the live-schema audit — applied-migration count, `btree_gist` status, column
  types): **partially answerable from files alone.** File-based evidence confirms `btree_gist` is not
  referenced in any migration and no timestamp column has been converted — this matches the 2026-08-19
  audit's findings and shows no drift on those two points. What files alone cannot confirm: whether all 6
  migrations are actually *applied* to the live `kujffzgqjmqphkmrbawy` project (`TASKS.md` 1.2 flags
  `20260817040000_escalation_resolution_note.sql` specifically as unconfirmed-applied). That needs a live
  Supabase check this pass did not have authenticated access to.
- **Phase 1 is untouched.** Steps 1.3 (`btree_gist`), 1.4 (`text`→`timestamptz`), 1.5 (`dock_occupancy` +
  backfill) all remain to be done exactly as `TASKS.md` describes them. This review adds one concrete
  reason the backup-first discipline (1.1, D16) matters even more than the document already states: the
  live capacity-correctness mechanism (`allocation.py`'s two unique indexes) will need to coexist with or be
  superseded by `dock_occupancy` mid-migration, and the backfill step (1.5-1.6) is the first point at which
  the 85/116-row worklist becomes real rather than theoretical.

---

*Compiled 2026-08-22. No files under `backend/`, `frontend/`, or `supabase/` were modified. Per this
persona's output-location instruction, this file is the only artifact of this pass, written to
`docs/New-Solution-New-Design/APPLY-TO-EXISTING/`.*
