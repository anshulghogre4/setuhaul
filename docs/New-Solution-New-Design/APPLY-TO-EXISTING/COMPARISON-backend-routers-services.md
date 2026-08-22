# Backend routers/services vs. the redesign — file-by-file comparison

> Scope: `backend/app/api/v1/routers/{chat,dispatch,driver,health_auth,operations,scheduling,shipments}.py`
> and `backend/app/services/{dispatch_service,driver_reads,escalation_service,eta_service,idempotency,ids,redis_memory}.py`
> — 14 files, read in full. Design side: `SOLUTION_DESIGN.md` §7.5.1/.4/.5/.6/.8, §0.9 (M1–M15/S1–S8);
> `ARCHITECTURE/REQUIREMENTS.md` §2–5. This is Phase 0's codebase-opening for this file set — several
> `[A]`-marked assumptions in `APPLY-TO-EXISTING/TASKS.md` are confirmed or corrected below.

Tag legend: **KEEP** = keep as-is · **IMPROVE** = needs improvement · **FR** = requirement mapping ·
**FLAG** = wrong optimisation flag (over/under-engineered, or a real defect).

---

## 0. Headline findings (read this first)

1. **The carrier role does not exist in the identity model at all.** `app/core/execution_context.py`'s
   `RoleName` enum has no `CARRIER` value, and `ExecutionContext` has no `carrier_id` field — only
   `driver_id`/`facility_id`. §7.5.6's entire five-tool carrier-portal catalog (`get_fleet_overview`,
   `list_fleet_shipments`, `get_shipment_detail`, `list_fleet_exceptions`, `get_carrier_on_time_performance`)
   and FR-CAR-001…006 have **zero backing identity, not just zero tools**. This is a bigger gap than
   "the tools aren't written yet" — there is nowhere in the auth model to hang them.
2. **Two roles documented as read-only are wired as write-authorised.** `is_admin`'s own docstring
   (`app/core/execution_context.py:49-55`) calls `TRANSPORT_MANAGER`/`REGIONAL_OPERATIONS_HEAD` "Global
   **read-only** ops personas," and `ROLE_PERMISSIONS` (`app/core/deps.py:46-47`) grants them only
   `*_read_global` permission strings. But `OPS_PORTAL_ROLES` (`deps.py:50-58`) — the tuple every mutating
   ops router uses for `require_roles(*OPS_PORTAL_ROLES)` — includes both, and `ctx.is_admin` is the exact
   bypass condition used inside `escalation_service.resolve_escalation` (line 210-211: `if not (ctx.is_operator
   or ctx.is_admin): raise FORBIDDEN`) and `dispatch_service.create_dispatch_shipment` (line 71-72, identical
   pattern). A `TRANSPORT_MANAGER` account — permissioned for reads only — can resolve escalations and
   create dispatch shipments across every facility. This is an M15/NFR-019 violation grounded in the code's
   own stated intent, not a stylistic nit.
3. **`driver.py`'s `/driver/context` endpoint duplicates `driver_reads.get_driver_operational_context`
   almost line-for-line** (compare `api/v1/routers/driver.py:20-127` against
   `services/driver_reads.py:22-126` — same four queries, same shape, written twice). This is the clearest
   single instance of the "routers stay thin" rule being broken in this file set: the router should call the
   service instead of re-executing the same SQL.
4. **A driver-reported breakdown/incident is silently lost.**
   `driver_reads.report_vehicle_breakdown_or_incident` (lines 467-553) inserts into `chat_threads` and
   `driver_exceptions` but never calls `session.commit()`. Its only caller, the `report_vehicle_breakdown_or_incident`
   tool wrapper in `assistant/tools.py` (lines 659-665), doesn't commit either, and neither does
   `assistant/run_assistant.py` (grepped — no `session.commit()`/`session.rollback()` anywhere in that file).
   `core/deps.py:73-81`'s `get_db_session` is a bare `async with db.session_factory() as session: yield session`
   with no auto-commit. SQLAlchemy's async session does not commit on a clean `__aexit__`; an open
   transaction is discarded. Every other capacity/state-changing write reviewed in this pass
   (`eta_service.record_eta_update`, `escalation_service.escalate_exception`/`resolve_escalation`,
   `dispatch_service.create_dispatch_shipment`) explicitly calls `await session.commit()`. This one function
   doesn't, so a driver's "I broke down" report goes in memory only and then vanishes — a correctness defect
   against M13 (gate/yard and incident truth must be captured) with no FR-DRV-specific ID (closest is
   FR-DRV-001's escalation branch, since a breakdown is exactly the kind of thing that should reach ops).
5. **Escalation-reason vocabularies diverge completely between the design and the code.** §7.4's canonical
   set is `NO_FEASIBLE_SLOT`, `PENDING_EXPIRED_UNACTIONED`, `AMBIGUOUS_SHIPMENT`, `LOW_CONFIDENCE_ETA`,
   `WAREHOUSE_REPLY_CONFLICT`, `NOTIFICATION_FAILED`, `NOTIFICATION_UNROUTABLE`, `SAFETY_OR_REGULATED`,
   `CAPACITY_EVENT_CASCADE`. `escalation_service.py:15-17`'s `ESCALATION_TYPES` frozenset is
   `{NO_SLOT, CONTRADICTORY, APPROVAL_REQUIRED, REGULATED, EMERGENCY, WAREHOUSE_REPLY_CONFLICT}` — only one
   name overlaps (`WAREHOUSE_REPLY_CONFLICT`). None of `PENDING_EXPIRED_UNACTIONED`, `AMBIGUOUS_SHIPMENT`,
   `LOW_CONFIDENCE_ETA`, `NOTIFICATION_FAILED`, `NOTIFICATION_UNROUTABLE`, or `CAPACITY_EVENT_CASCADE` can be
   raised through this function today — a `D9` pending-expiry sweeper (Phase 3 of `TASKS.md`) or a
   capacity-incident cascade (S4/FR-SYS-019) has no valid `escalation_type` value to write.
6. **§7.5.5's ops catalog is ~15% implemented.** Of `get_escalation_queue`, `acknowledge_escalation`,
   `reassign_escalation`, `take_over_thread`, `hand_back_thread`, `resolve_escalation`, `cancel_escalation`,
   `request_sequencer_proposal`, only a loose analogue of `get_escalation_queue` (`get_exception_queue`) and
   a much-weakened `resolve_escalation` exist. There is no `owner` column being written anywhere
   (`escalate_exception`'s `INSERT` at `escalation_service.py:96-118` has no owner field), so
   `acknowledge_escalation`'s entire ownership model has no column to write to yet. This matches
   `TASKS.md` Phase 2.2's own framing ("Implement §7.5.5 in full") — confirmed genuinely not done, not an
   overstatement.

---

## 1. `api/v1/routers/chat.py`

**KEEP.** Thin by construction: both `/chat` and `/chat/message` (an explicit `DriverHome.tsx`-compat alias,
commented as such at line 92) parse the body and hand off entirely to `run_assistant`/`invoke_agentcore`
(lines 60-69). `/chat/history` (lines 25-40) does one call into `ConversationMemory.load_conversation_for_restore`
and returns. No business logic, no raw SQL, no scope logic beyond `require_roles(RoleName.DRIVER)`
(M15-correct — scope comes from the verified token, not from any request field).

**FR mapping**: FR-DRV-001…006 collectively (the chat surface), FR-X-002/FR-X-016 (memory-adjacent, not
this file's concern).

**FLAG**: none. Right-sized for the job.

---

## 2. `api/v1/routers/dispatch.py` + `services/dispatch_service.py`

**IMPROVE — no FR/§7.5.x mapping exists for this endpoint at all.** `dispatch_create_shipment`
(`dispatch.py:43-51` → `dispatch_service.create_dispatch_shipment`) is not named anywhere in §7.5's tool
catalogs or in `ARCHITECTURE/REQUIREMENTS.md`. It reads as an internal ops/demo tool for manually spinning
up a shipment + best-effort initial booking, pre-dating the redesign's tool catalogs. Not necessarily wrong
to keep, but it should either get its own FR-OPS/FR-ADM row or be marked explicitly out-of-catalog before
Phase 2 work proceeds, so nobody assumes it is one of the 46 named flows.

**FLAG — M9 (idempotency) is not honoured on a capacity-consuming write, and this is exploitable by an
ordinary retry, not just a theoretical race:**
- `dispatch.py:43-51` accepts no `Idempotency-Key` header at all — contrast every scheduling/shipments
  mutation in this file set, which all reject the request with `IDEMPOTENCY_KEY_REQUIRED` if the header is
  missing (`scheduling.py:97-102`, `137-139`, `186-192`, `223-229`, `257-259`, `278-280`; `shipments.py:127-133`).
- Inside the service, `create_dispatch_shipment` (`dispatch_service.py:113-114`) auto-generates
  `shipment_id` (`f"SHP-DISP-{uuid4()...}"`) when the caller doesn't supply one, and separately
  auto-generates a **random** idempotency key for the internal `request_slot` call
  (`dispatch_service.py:174`: `idem_key = f"IDEM-DISP-{uuid.uuid4().hex[:16]}"`). A random key defeats the
  entire purpose of an idempotency key — it can never match a prior attempt's key, so `request_slot`'s own
  idempotency guard (which does exist, in `scheduling/allocation.py`) can never detect a duplicate coming
  through this path.
- Net effect: an ordinary client-side retry (double-click, network timeout-and-resend) with no
  `cmd.shipment_id` supplied creates a **second** shipment row and attempts a **second** capacity-consuming
  slot request. If `cmd.shipment_id` *is* supplied and the retry lands after the first attempt's
  `session.commit()` at line 160, the second attempt's `INSERT` throws a raw, uncaught
  `IntegrityError`/`UniqueViolation` — there's no `try/except` around the shipment insert (only around the
  slot-booking step, lines 165-187) — surfacing as an unhandled 500, not a typed `ALREADY_ACTIONED`-style
  outcome.
- Concrete fix: require `Idempotency-Key` at the router (`dispatch.py`) exactly like every other mutating
  endpoint in this file set, and thread it into both `dispatch_service`'s own `lookup_idempotency`/
  `store_idempotency` (already available from `services/idempotency.py`) and the inner `request_slot` call
  instead of a freshly-minted random key.

**FLAG — non-atomic multi-step write.** The shipment `INSERT` is committed at line 160, then slot lookup
and booking happen afterward in the same session with no surrounding transaction. If the process dies
between the commit and the booking attempt, the shipment silently ends up with no appointment — tolerated
today ("shipment remains created," line 186 comment) but worth stating plainly: this is optimistic best-effort
booking, not the atomic all-or-nothing discipline §7.5.3's `apply_schedule_proposal` insists on for its own
capacity-affecting write. Acceptable for what looks like an internal ops-seeding tool; not acceptable if this
ever becomes a driver- or planner-facing path.

**KEEP**: `list_dispatch_drivers`/`list_dispatch_facilities` (`dispatch_service.py:35-65`) — simple reads,
role-gated at the router via `require_roles(*OPS_PORTAL_ROLES)` (see §0 finding 2 for why that gate itself
is suspect, independent of this file).

---

## 3. `api/v1/routers/driver.py`

**FLAG — duplicates an existing service instead of calling it** (§0 finding 3). `driver_context`
(`driver.py:20-127`) re-implements `driver_reads.get_driver_operational_context` query-for-query: same
`drivers` lookup, same `shipments` list, same "pick the first active shipment" logic, same appointment/
facility/latest-ETA joins. The only material difference is the response shape omits `active_shipments`
as its own key. This is a textbook "routers stay thin" violation (`AGENTS.md`) — the fix is
`return ok(await driver_reads.get_driver_operational_context(session, ctx), get_request_id(request))`,
deleting ~90 lines of duplicate SQL.

**KEEP** on the scope side: `require_roles(RoleName.DRIVER)` (line 23) and the `ctx.driver_id` check
(line 26-27) are both server-derived, never client-supplied — M15-correct.

**FR mapping**: `get_driver_operational_context` in §7.5.4 ("pre-fetched at session open, so usually zero
calls"). No FR-DRV-* ID names it directly (it's infrastructure the six flows sit on top of), same
class of gap the requirements doc itself flagged and fixed for `FR-PLN-010`/`FR-ADM-010` — this looks like
another one of those "load-bearing read with no ID" cases worth raising in a future `REQUIREMENTS.md` pass.

---

## 4. `api/v1/routers/health_auth.py`

**KEEP.** `/health/live`, `/health/ready` are infrastructure, correctly outside the tool catalogs.
`/api/v1/auth/me` (lines 43-63) is a clean, read-only projection of the verified `ExecutionContext` — this
is functionally `get_account_profile` from §7.5.8, though not named that and not under `/api/v1/account/...`.

**FR mapping**: closest is FR-X-025 (`get_account_profile`, §7.5.8) — same shape (name, email, role, scoped
facility, no write path), different route name and returns `permissions`/computed `scope` instead of the
phone number `get_account_profile` also promises. **IMPROVE**: rename/alias to match the catalog's
`get_account_profile` naming when §7.5.8 lands (Phase 2.7 of `TASKS.md`), or explicitly document that
`/auth/me` *is* that tool under a legacy route, so a future implementer doesn't build a second one.

**FLAG — none.** Right-sized, no idempotency needed (pure read), no scope-derivation risk (returns the
caller's own identity only).

---

## 5. `api/v1/routers/operations.py`

This file is the sharpest split-personality in the set: half its endpoints are properly thin (dispatch to
`escalation_service`), the other half embed raw SQL and scope resolution directly in the router.

**KEEP** (thin, delegate correctly): `escalation_queue` (49-57), `resolve_escalation_endpoint` (60-71),
`dock_status` (74-81), `queue_status` (84-91), `pending_confirmations` (94-101), `escalate` (104-116) — each
is a one-line call into `escalation_service`.

**IMPROVE — the other five endpoints carry the exact business logic + persistence that `AGENTS.md`
says belongs in a service/repository, not a router**: `dashboard_summary` (119-184), `list_exceptions`
(187-232), `appointment_schedule` (235-280), `dock_snapshot` (283-343), `facility_constraints`
(346-402). Each builds a raw SQL string with `text()` (five separate ad-hoc queries with dynamic
`WHERE`/`JOIN` fragments), executes it against `session` directly in the router function, and inlines its
own scope resolution via the router-local `_resolve_facility` helper (lines 39-46). None of this reaches a
`services/*.py` file. Concrete fix: extract these five into an `operations_reads` (or similarly named)
service module — mirroring exactly the pattern `driver_reads.py` already establishes for the driver side —
and have the router call into it.

**FLAG — scope-resolution logic is duplicated three independent ways across the reviewed file set,**
which is itself an M15 risk (one place drifting out of sync is a real vulnerability, not just untidy code):
1. `operations.py:39-46`'s `_resolve_facility` (router-local),
2. `escalation_service.py`'s inline pattern repeated four times verbatim — `get_exception_queue` (169-172),
   `get_pending_confirmations` (280-282), `get_dock_status` (306-308), `get_queue_status` (330-331): each is
   `scope = facility_id if ctx.is_admin else ctx.facility_id; if not scope or (not ctx.is_admin and facility_id
   and facility_id != scope): raise FORBIDDEN` — copy-pasted four times in one file,
3. `shipments.py` and `driver_reads.py`'s separate `if ctx.is_driver / elif ctx.is_operator / elif not
   ctx.is_admin` three-branch pattern, itself duplicated across `shipments.get_shipment` (48-55),
   `shipments.current_appointment` (82-87), `driver_reads.get_shipment_details` (151-156), and
   `eta_service._assert_driver_owns_shipment` (108-109, narrower single-branch version).

Per `NFR-020` ("Scope enforced in the repository layer, not the router or tool schema") this should be
**one** helper — e.g. `assert_facility_scope(ctx, facility_id)` / `assert_shipment_scope(ctx, shipment_row)`
in a shared module — called from every service and never re-derived in a router. Today there are effectively
three slightly-different implementations of the same rule; a fourth new endpoint has no canonical place to
copy from and is one dropped `elif` away from a real cross-tenant leak.

**FR mapping**: none of these five read-heavy endpoints map to a named §7.5.x tool or FR-OPS/FR-PLN ID —
they look like they predate the redesign's ops-console catalog (dashboard/exceptions/schedule/dock-snapshot/
facility-constraints as flat REST reads, versus the catalog's typed `get_escalation_queue`,
`get_planner_queue`, `list_facility_rules`, etc.). Worth an explicit decision: keep these as a
separate "ops dashboard" surface outside §7.5, or fold them into the matching catalog tools during Phase 2.

---

## 6. `services/escalation_service.py`

**FR mapping / catalog coverage — the central finding for this file** (expanded from §0.6): comparing
against §7.5.5's eight required tools —

| §7.5.5 tool | Present? | Note |
|---|---|---|
| `get_escalation_queue` | Partial — `get_exception_queue` (166-200) | No `owner` filter (`mine`/`unowned`/`all` — column doesn't exist), no SLA-remaining computation, no stepper position, no `CAPACITY_EVENT_CASCADE` affected-shipment set. Orders by `created_at DESC`, not "time-to-SLA-breach ascending, unowned pinned above owned" |
| `acknowledge_escalation` | **Absent** | No code path sets an owner or transitions `OPEN → ACKNOWLEDGED` |
| `reassign_escalation` | **Absent** | — |
| `take_over_thread` | **Absent** | No code touches `chat_threads.thread_status` in this file |
| `hand_back_thread` | **Absent** | — |
| `resolve_escalation` | Partial (203-274) | Free-text `status`/`resolution_note`, no `Idempotency-Key`, no `reason_code` enum (`ISSUE_FIXED`), no race protection against a second concurrent resolve (contrast `confirm_request`'s documented transactional pattern in §7.5.1) |
| `cancel_escalation` | **Absent** | Distinct terminal state from resolve is not modelled at all |
| `request_sequencer_proposal` | **Absent** | — |

This is the code-side confirmation that `TASKS.md`'s Phase 2.2 ("Implement §7.5.5 in full") describes real,
unstarted work, not overstated risk.

**FLAG — escalation-type vocabulary mismatch** (§0 finding 5, repeated here with the fix): `ESCALATION_TYPES`
at lines 15-17 should be replaced with §7.4's nine canonical reasons before any sweeper/cascade work in
`TASKS.md` Phase 3 lands, or every write from that phase will 422 against `INVALID_ESCALATION_TYPE`
(line 68).

**KEEP — the dedupe mechanism in `escalate_exception` is a reasonable, if different-shaped, idempotency
approach**: `dedupe_key = f"{shipment_id}:{day}:{escalation_type}"` with `ON CONFLICT (dedupe_key) DO UPDATE`
(lines 94, 109-114) gives "at most one open escalation per shipment/day/type" without needing a client-supplied
`Idempotency-Key`. This is defensible for THR001/THR009-style duplicate-report coalescing (M9), though it's
worth noting it is architecturally different from the `Idempotency-Key`-header pattern used everywhere else
in this file set (`services/idempotency.py`) — two idempotency mechanisms coexist in the codebase with no
shared vocabulary. Not wrong, but worth a one-line note in whichever doc becomes the implementation record,
so a future reader doesn't assume `escalate_exception` forgot the header pattern.

**IMPROVE — `resolve_escalation`'s two-table fallback is fragile.** Lines 238-253: if the `escalation_queue`
`UPDATE` matches zero rows, the function falls back to updating `driver_exceptions` by treating the same
`escalation_id` as an `exception_id`. These are two different ID spaces (`new_id("ESC")` vs `new_id("EXP")`/
`new_id("EXC")` elsewhere in this file set) with no visible guarantee they're disjoint — a collision would
silently resolve the wrong entity. Given `resolve_escalation` doesn't exist as a distinct tool per §7.5.5's
contract (it's meant to act only on `escalation_queue` rows; `driver_exceptions` isn't an escalation), this
fallback looks like a workaround for the REST route being asked to resolve things that were never actually
escalated. Worth resolving explicitly rather than papering over with an ID-space guess once Phase 2.2 is
implemented properly.

**KEEP**: `_assert_ops_scope` (40-43) and `_shipment_scope` (46-60) are small, single-purpose, and used
consistently within this file (unlike the operations.py-router/driver_reads.py duplication noted in §5) —
a reasonable pattern to promote to the shared scope helper recommended above, not to throw away.

---

## 7. `services/eta_service.py`

**KEEP — this is the strongest file in the set and a good template for the others.** `record_eta_update`
(236-531):
- Correctly implements the preview → explicit confirm → idempotent commit pattern §0's "Locked decisions"
  require: `confirmation_preview` (69-85) returns `CONFIRMATION_REQUIRED` on first call, and the real write
  only proceeds once `command.confirmed` is true **and** `confirmation_eta_ts` exactly matches
  `declared_eta_ts` (266-276) — a client can't silently promote a preview into a commit by resending with a
  different value.
- M9 idempotency done the recommended way: `payload_hash` → `lookup_idempotency` before any write
  (247-257), `store_idempotency` inside the same transaction as the write, before `session.commit()`
  (462-511) — replay returns the stored response with `idempotent_replay: True` rather than re-executing
  side effects.
- Writes `eta_updates`, updates `shipments.latest_eta_ts`, inserts a `chat_messages` row, upserts the open
  `driver_exceptions` row, and writes an `audit_logs` entry (330-491) — all in one transaction, one commit
  (511) — this is the atomicity `dispatch_service.py` (§2) is missing.
- Redis is used only to mark a display recommendation stale (514-520), wrapped in its own
  `try/except ... pass` explicitly commented "*a Redis outage must never turn a committed PostgreSQL ETA
  update into a failed write*" — this is §10's chaos-lite requirement satisfied by construction, not by
  accident.

**FR mapping**: `report_delay_or_update_eta` (§7.5.4), backing FR-DRV-001 and FR-DRV-005.

**IMPROVE — minor**: `EtaUpdateCommand.confidence_code: str = "MEDIUM"` (line 31) has no enum/`Literal`
constraint, unlike `exception_type` (validated against `ALLOWED_EXCEPTION_TYPES`, lines 23-25, 278-283) or
`escalation_type` in the previous file. M2 requires "LOW confidence blocks silent commitment" — that gating
logic isn't in this file (it may live in `assistant/tools.py`, out of this pass's scope); flagging here only
because if `confidence_code` can be an arbitrary string, whatever downstream code checks for `== "LOW"` is
one typo away from silently never firing. Worth a `Literal["LOW", "MEDIUM", "HIGH"]` here regardless of
where the gating logic lives.

**FLAG — none material.** This file does not need simplification or a different optimisation posture; it's
correctly sized for a 5-concurrent-user internal tool while still being transactionally careful where it
matters (the actual write), which is the right trade-off.

---

## 8. `services/idempotency.py`

**KEEP.** Small, focused, does one job: `payload_hash` (canonical JSON → SHA-256), `lookup_idempotency`
(scope-checks the replay against `user_id` **and** `route`, and rejects a reused key with a different
payload as `IDEMPOTENCY_PAYLOAD_MISMATCH` rather than silently replaying the wrong response — lines 42-53),
`store_idempotency` (24h TTL via an `expires_at` column). This is the mechanism M9/U70 asks for, and it's
used correctly by `eta_service.py` and (per grep) `scheduling/allocation.py`.

**FLAG — inconsistent adoption, not a defect in this file itself.** Confirmed by grep across
`backend/app`: only `eta_service.py` and `scheduling/allocation.py` call `lookup_idempotency`/
`store_idempotency`. `escalation_service.py` uses its own `dedupe_key`+`ON CONFLICT` mechanism instead (see
§6 — defensible but different), and `dispatch_service.py`'s capacity-consuming write uses neither this
module nor a real dedupe key (see §2 — not defensible). Recommend this module become the single required
mechanism for every future capacity-affecting write named in Phase 2 of `TASKS.md`, rather than three
different idempotency strategies accumulating across the codebase.

**IMPROVE — no visible expiry sweep for `idempotency_requests` rows.** `store_idempotency` writes
`expires_at` (72-73, 92) but nothing in this file (or elsewhere in the reviewed set) prunes expired rows —
worth confirming there's a cleanup job before this table grows unbounded; not urgent at 190-240
appointments/day (NFR-017) but worth a one-line TODO now rather than a surprise later.

---

## 9. `services/ids.py`

**KEEP.** Five lines, does one job (`f"{prefix}-{uuid4().hex[:12].upper()}"`), used consistently by every
other service in this set for `ESC-`, `THR-`, `ETA-`, `EXC-`, `AUD-`, `MSG-` ids. 48 bits of randomness per
id is more than sufficient collision resistance at this scale (NFR-017: 190-240 appointments/day). No
`[P]`-parallel-safety concern, no cross-cutting risk.

**FR/FLAG**: nothing to add — appropriately sized for the scale (`NFR-018`'s anti-requirement: no premature
scaling infrastructure).

---

## 10. `services/redis_memory.py`

**KEEP — this file correctly respects the Postgres-vs-Redis boundary throughout**, and this is worth
stating plainly given the task brief's specific concern about durable data leaking into Redis. Every method
reviewed writes only:
- conversation history (`_history_key`, `append_turn`) — bounded to `HISTORY_LIMIT = 40` (line 14), TTL'd
  at `TTL_SECONDS = 24*60*60` (line 13) on every write (e.g. `pipe.expire(hkey, TTL_SECONDS)`, line 339),
- rolling summaries (`_summaries_key`) — same TTL discipline,
- ephemeral session/turn state (`_session_key`) — same,
- a **display pointer** for "which recommendation was last shown" (`_recommendation_key`,
  `store_active_recommendation`/`mark_recommendation_stale`/`is_recommendation_stale`, lines 106-182) —
  explicitly commented "PostgreSQL remains authoritative" (line 114); this is a UI staleness signal, not a
  decision record,
- the "which thread was the user last in" pointer (`_active_key`, `set_active_conversation`/
  `get_active_conversation`) — used only to restore chat UI state, not business state.

None of this is the specific violation the design docs flag by name (`SOLUTION_DESIGN.md` lines 1371-1376:
notification preferences and notification read/unread state must live in Postgres, not Redis, because users
expect them to survive well past 24 hours). That's correct **because those tools don't exist in this
codebase yet** (§7.5.8 is entirely unimplemented — see below) — there's nothing here to flag today, but this
is exactly the trap to avoid when §7.5.8 gets built in Phase 2.7: `get_notification_preferences`/
`mark_notifications_read` must not be implemented by extending this class.

**FLAG — every public method degrades the same correct way** (`self.degraded = True`, logs a typed reason,
returns an empty/default value) rather than raising — this is what makes the chaos-lite requirement (§10
item 6: kill Redis mid-conversation, next turn answers correctly from Postgres) achievable. No
over-engineering here either: the rolling-summary mechanism (ERICA-style chunking, lines 441-505) is a
reasonable response to context-window cost at conversation scale, not gratuitous complexity for a 5-user
tool — it exists because LLM token cost is the actual constraint (FR-SYS-030), not because Redis needed
more surface area.

**FR mapping**: not itself a named §7.5.x tool — it's the memory layer `chat.py`'s `/chat/history` and the
assistant's tool-calling loop (`run_assistant.py`, out of this pass's scope) sit on top of. `auth-and-scoping.md`'s
namespace-not-access-grant framing (line 40-41 comment: *"a namespace for ephemeral memory. It never grants
access"*) is respected — Redis keys are scoped by `normalize_memory_id(user_id)`, but no code path in this
file trusts a Redis key to authorize anything; every read that matters is re-verified against Postgres
elsewhere (e.g. `eta_service.py`'s `_assert_driver_owns_shipment`).

---

## 11. `api/v1/routers/scheduling.py`

**KEEP.** Every endpoint is a thin dispatch into `app.scheduling.allocation`/`app.scheduling.feasibility`
(both out of this pass's assigned scope, but their entry points are visible from here). Idempotency-Key is
correctly required and rejected with a typed `IDEMPOTENCY_KEY_REQUIRED` error for every mutating route
(`request_shipment_slot` 97-102, `reschedule_shipment_appointment` 138-139, `cancel_shipment_appointment`
187-192, `confirm_shipment_appointment` 224-229, `reject_shipment_appointment` 258-259,
`expire_shipment_appointment` 279-280) — the one router in this set that enforces this consistently at the
boundary rather than leaving it to the service.

**KEEP** on race handling: `request_shipment_slot` (87-128) and `reschedule_shipment_appointment`
(131-154) both translate `SLOT_CONFLICT_REFRESH_REQUIRED`/`SLOT_OPTIONS_STALE` into an HTTP 409 with a typed
error body — exactly the "typed outcomes, never prose" principle §7.5 opens with (M10).

**Spot-checked, not fully audited (out of assigned scope)**: `feasible_slots` (75-84) accepts any
authenticated role via `get_execution_context` rather than `require_roles(RoleName.DRIVER)`. Grepped the
callee (`scheduling/feasibility.py:308-318`) to confirm this isn't an open scope hole — it does perform the
same `is_driver`/`driver_id` and `is_operator`/`facility_id` check server-side before returning options, so
the router's looser role gate is safe *because* the service re-derives scope. Flagging as **IMPROVE, not
FLAG**: this pattern (permissive router + strict service) works here but is fragile — the router's role gate
gives no defense-in-depth if the service check is ever refactored away. Since `scheduling/allocation.py` and
`scheduling/feasibility.py` are outside this pass's file list, a follow-up pass should confirm the same
discipline holds for `confirm_appointment`/`reject_appointment`/`expire_appointment` (planner/ops-only
mutations) — worth a dedicated review since that module carries the M6/M7 guarantees this whole design
depends on.

**FR mapping**: `find_feasible_slots`, `request_slot`, `cancel_appointment` (§7.5.4, FR-DRV-001/002/004);
`confirm_appointment`/`reject_appointment`/`expire_appointment` read like ops-side equivalents of
`confirm_request`/`reject_request` (§7.5.1) but under different names and without the planner catalog's
`snapshot_hash`/bulk semantics — worth reconciling naming once Phase 2.1 extends the planner catalog, so
there isn't a `confirm_appointment` REST route and a `confirm_request` tool doing overlapping jobs under two
names.

---

## 12. `api/v1/routers/shipments.py`

**IMPROVE — same raw-SQL-in-router pattern as §5**: `get_shipment` (21-60) and `current_appointment`
(63-116) execute `text()` queries directly in the router and perform scope checks inline
(`if ctx.is_driver: ... elif ctx.is_operator: ... elif not ctx.is_admin: raise`, lines 48-55 and 82-87) —
the exact `driver_reads.get_shipment_details` logic (§0's driver_reads read above) reimplemented a third
time. `create_eta_update` (119-153) is properly thin by contrast, delegating to `eta_service.record_eta_update`.
Fix: replace `get_shipment`'s body with a call to `driver_reads.get_shipment_details`, and extract
`current_appointment`'s query into a service (or reuse `driver_reads.get_current_appointment`, which already
exists and does the same join).

**FLAG — a real gap against FR-CAR-003, not just style.** `get_shipment` (21-60) has scope branches for
`is_driver`, `is_operator`, `is_admin` only. There is no branch for a carrier — but per §0 finding 1, there's
no `is_carrier` to branch on in the first place. The practical effect: a carrier-role caller (if one existed)
would fall through to `elif not ctx.is_admin: raise FORBIDDEN` and be denied outright, even for their own
fleet's shipment. FR-CAR-003 ("Open shipment detail — read-only; server validates carrier ownership,"
`REQUIREMENTS.md` line 257) has no implementation path through this endpoint or anywhere else in the
reviewed file set. This is the concrete, file-level evidence behind §0's headline finding 1: it isn't only
that `get_shipment_detail` (§7.5.6's name) doesn't exist — the nearest existing analogue actively can't
serve a carrier even if one were added to the role enum, without also adding the ownership-validation branch
this function is missing.

**FR mapping**: `get_current_appointment` (§7.5.4) for `current_appointment`; no §7.5.x name for
`get_shipment` (closest is the driver-side "profile reads... fold into the pre-fetched context block" note
in §7.5.4, or the missing `get_shipment_detail` for carrier — see above).

---

## 13. Cross-cutting patterns worth acting on before Phase 2 (`TASKS.md`)

1. **Extract one shared scope-assertion helper** and delete the four-way duplicated logic identified in
   §5/§6/§9/§12 (`operations.py:_resolve_facility`, `escalation_service.py`'s four inline copies,
   `shipments.py`/`driver_reads.py`'s three-branch inline checks, `eta_service.py`'s narrower version). This
   is the single highest-leverage cleanup in this file set for `NFR-020` compliance.
2. **Standardise on one idempotency mechanism** (`services/idempotency.py`) for every capacity-affecting
   write, and add the missing `Idempotency-Key` requirement to `dispatch.py` specifically.
3. **Reconcile the escalation-type vocabulary** (`escalation_service.ESCALATION_TYPES`) against §7.4's nine
   canonical reasons before Phase 3's sweeper or Phase 2.2's ops catalog work begins — both will need to
   raise reasons the current enum rejects.
4. **Decide the `TRANSPORT_MANAGER`/`REGIONAL_OPERATIONS_HEAD` read-vs-write question explicitly**
   (§0 finding 2) — either split `is_admin` into a genuine read-only bucket plus a separate
   write-authorised admin check, or update the `ROLE_PERMISSIONS`/docstring comments to stop calling these
   roles read-only if the intent really is full write access. Leaving the mismatch as-is is the kind of gap
   a security review would treat as a real finding, not a documentation nit.
5. **Add the carrier role and `carrier_id` field to `ExecutionContext`/`RoleName`** before any §7.5.6 work
   starts — every one of that catalog's five tools needs it, and `get_shipment_detail`'s ownership check
   can't be written without it.
6. **Fix or remove `report_vehicle_breakdown_or_incident`'s missing commit** — this is a live data-loss bug
   today, independent of any redesign work.
