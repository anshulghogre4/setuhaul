# SetuHaul — functional and non-functional requirements

> **Derived in two directions, not one.** Top-down from `SOLUTION_DESIGN.md` §0.9's M1–M15 / S1–S8, **and
> bottom-up from all 46 named flows across the six UI-UX surfaces.** The bottom-up pass matters: M1–M15
> covers roughly a third of the functional surface. Requirements like *simulate policy weights before
> publish*, *draft a reply with the co-pilot*, *block a dock*, *shift start / end shift* and *add a
> constraint* exist **only** in the UI-UX work.
>
> **Granularity**: one FR per flow, with that flow's edge cases as **acceptance criteria** underneath —
> capturing all 57 edge-case behaviours without inflating to 100+ IDs nobody reads.
>
> **`NEW`** marks requirements identified in `GAP_ANALYSIS.md` that no existing document covers.

---

## ID namespaces

| Prefix | Source | Count |
|---|---|---:|
| `FR-SYS` | §0.9 M1–M15 (15) + S1–S8 (8) + gap-derived `NEW` (8) + §8 observability measures (11 — see §1's 2026-08-22 renumbering note) | 42 |
| `FR-X` | `00-foundations/` — cross-cutting, owned by no single surface (incl. 11 added 2026-08-22 for the sign-in/settings/notifications/search shared-shell screens) | 27 |
| `FR-DRV` | `01-driver-chat/` | 6 |
| `FR-OPS` | `02-ops-exception-console/` | 6 |
| `FR-PLN` | `03-planner-dock-board/` (incl. `FR-PLN-010`, added 2026-08-22) | 10 |
| `FR-GATE` | `04-gate-yard-kiosk/` | 10 |
| `FR-CAR` | `05-carrier-portal/` | 6 |
| `FR-ADM` | `06-admin-console/` (incl. `FR-ADM-010`, added 2026-08-22) | 10 |
| `NFR` | Non-functional, grouped by quality attribute (incl. 3 `NEW`) | 28 |

**Total: 117 functional · 28 non-functional.** All six UI-UX surfaces plus foundations represented, and
**all 13 of the brief's acceptance-criteria questions mapped** (§10) — both verifiable by grep. **Updated
2026-08-22** from 113 following a cross-document consistency sweep: an `FR-SYS-032`/`033` ID collision was
fixed by renumbering two rows to `041`/`042` (+2), and two genuinely missing load-bearing reads were added,
`FR-PLN-010` and `FR-ADM-010` (+2).

---

## 1 · System functional requirements (`FR-SYS`)

### MUST (from M1–M15)

| ID | Requirement | Origin |
|---|---|---|
| FR-SYS-001 | Identify the conversation's shipment, including when a driver has more than one; never guess; escalate after 2 failed clarifications | M1 |
| FR-SYS-002 | Establish an effective ETA from plan / driver declaration / gate-in, with a confidence value; gate-in overrides ETA; `LOW` confidence blocks silent commitment | M2 |
| FR-SYS-003 | Evaluate all hard feasibility constraints deterministically in code — **never** by the LLM | M3 |
| FR-SYS-004 | Rank deterministically with a reproducible decision receipt | M4 |
| FR-SYS-005 | Implement the four-state promise lifecycle (SHOWN / HELD / PENDING / CONFIRMED) as visually and semantically distinct states; no state below CONFIRMED may say "booked" | M5 |
| FR-SYS-006 | **Capacity can never be double-promised** — DB-enforced; a 50-way race yields exactly one winner | **M6** |
| FR-SYS-007 | Only a human transitions PENDING → CONFIRMED; no code path permits LLM or rules-based confirmation | M7, D6 |
| FR-SYS-008 | Pending expiry (15 min) releases capacity, notifies the driver, and raises an escalation | M8, D9 |
| FR-SYS-009 | Intake is idempotent — duplicates and retries cannot double-act | M9 |
| FR-SYS-010 | Stale options are refused with a refresh, never applied | M10 |
| FR-SYS-011 | Every §7.4 escalation reason raises an owned, SLA-tracked item | M11 |
| FR-SYS-012 | Ops takeover — a human joins the thread, the assistant stands down, the driver is told | M12 |
| FR-SYS-013 | Gate/yard truth is writable — gate-in, queue state, dock-in, unload start/end, gate-out | M13 |
| FR-SYS-014 | Every state change and agent action is reconstructable — who, what, when, which policy version, which tool call | M14 |
| FR-SYS-015 | RBAC with scope — driver sees own shipments, carrier own fleet, facility own docks | M15 |

### SHOULD (from S1–S8)

| ID | Requirement | Origin |
|---|---|---|
| FR-SYS-016 | Facility sequencer with proposal-and-approve | S1, D3/D5 |
| FR-SYS-017 | Planner bulk-confirm under the five safe-batch predicates | S2 |
| FR-SYS-018 | Counter-offer affordance | S3 |
| FR-SYS-019 | Capacity-incident batching — one incident, not N escalations | S4 |
| FR-SYS-020 | Outbound event notifications (expiry, withdrawal, dock down) | S5 |
| FR-SYS-021 | Carrier portal | S6 |
| FR-SYS-022 | KPI / analytics surface | S7 |
| FR-SYS-023 | Ops-side assistant co-pilot | S8 |

### `NEW` — from gap analysis

| ID | Requirement | Source |
|---|---|---|
| FR-SYS-024 `NEW` | **Rate limiting** — per-driver, per-thread, and global in-flight ceilings, with driver-facing copy that reads as a system state, not an accusation | Gap 1/3 |
| FR-SYS-025 `NEW` | **Maintain the prompt-injection blast-radius model** as a stated security property: the LLM cannot widen scope, confirm capacity, or alter ranking. Any change granting write authority or accepting client-supplied scope is a **security regression** | Gap 1 |
| FR-SYS-026 `NEW` | **Consent capture** at driver onboarding — purpose-specific, by clear affirmative action; blanket consent non-compliant | Gap 2 (DPDP) |
| FR-SYS-027 `NEW` | **Privacy notice** stating purposes, data categories, retention periods, and the withdrawal mechanism | Gap 2 |
| FR-SYS-028 `NEW` | **Erasure on consent withdrawal or purpose fulfilment**, against a documented personal-vs-operational data classification | Gap 2 |
| FR-SYS-029 `NEW` | **Minimum 1-year retention** of access logs and processing records | Gap 2 |
| FR-SYS-030 `NEW` | **LLM cost governance** — quantified loop-iteration cap, per-conversation token ceiling, defined behaviour at budget exhaustion | Gap 4 |
| FR-SYS-031 `NEW` | **Feature flags** for risky changes (model provider, policy weights, sequencer) | Gap 5 |

### Observability outputs (from §8)

`FR-SYS-022` names the analytics *surface*; these are the **nine measures it must produce**. §8 frames them
as the answer to the brief's closing challenge — *"explain not only what the system says, but how the
business can trust the allocation."*

| ID | Measure | Definition |
|---|---|---|
| FR-SYS-032 | Time to usable outcome | First `chat_messages.message_ts` → appointment reaching CONFIRMED |
| FR-SYS-033 | Automation coverage | Share of exceptions resolved without an `escalation_queue` entry |
| FR-SYS-034 | **Conflicting / duplicate allocations** | **Must be 0** — the headline correctness metric (see `NFR-006`) |
| FR-SYS-035 | Options later found infeasible | SHOWN options that failed revalidation at commit |
| FR-SYS-036 | No-feasible-slot escalations handled correctly | Escalations with an ops resolution inside SLA |
| FR-SYS-037 | Average driver wait after rescheduling | `dock_in_ts − gate_in_ts` from `facility_checkins` |
| FR-SYS-038 | Dock utilisation | Booked dock-minutes ÷ available dock-minutes |
| FR-SYS-039 | Priority-policy violations | Lower-priority load granted over a blocked higher-priority one |
| FR-SYS-040 | Driver clarification turns | Agent clarification messages per resolved exception |

Plus the two supporting layers §8 defines: **traces** (every turn — prompt, tool calls, latency, cost,
errors) and **decision receipts** (`allocation_decisions`, `scheduling_runs` — every promise
reconstructable with inputs, policy version, candidates, and why the winner won).

### Observability — the KPI mart (§8)

| ID | Requirement | Origin |
|---|---|---|
| FR-SYS-041 | **Emit the nine §13.1 KPI measures**: time to usable outcome · automation coverage · **conflicting/duplicate allocations (must be 0)** · options later found infeasible · no-feasible-slot escalations handled inside SLA · avg driver wait after rescheduling · dock utilisation · priority-policy violations · driver clarification turns | §8 |
| FR-SYS-042 | **Three observability layers**: traces (every turn — prompt, tool calls, latency, cost, errors) · decision receipts (`allocation_decisions`, `scheduling_runs` — every promise reconstructable) · KPI mart | §8 |

**Corrected 2026-08-22**: this table's two rows were originally numbered `FR-SYS-032`/`FR-SYS-033`,
colliding with the two IDs the "Observability outputs" table above already uses for different
requirements (time-to-usable-outcome and automation-coverage measures) — a genuine ID collision, not a
stylistic duplicate, found in a cross-document consistency sweep. Renumbered to the next free IDs after
the outputs table's own `FR-SYS-040`.

**Note on `FR-SYS-041`'s scope**: §0.9 splits KPI *ownership* — operational measures (queue depth,
time-to-confirm, expiry rate, escalations by reason) belong to the planner/ops consoles in v1; the
strategic set (cross-facility utilisation, priority-policy violations, carrier concentration) travels with
the deferred personas. **The measurement is required either way** — *"do not drop the measurement; only
the dedicated surface is deferred, so keep emitting the events."*

---

## 2 · Cross-cutting requirements (`FR-X`) — `00-foundations/`

Behaviour owned by no single surface. Without IDs these fall outside traceability entirely.

| ID | Requirement | Origin |
|---|---|---|
| FR-X-001 | Promise-state chip renders four **redundant** encodings (hue, icon, border style, text); colour is never the sole carrier. States **hard-swap**, never morph | U14, U75 |
| FR-X-002 | Countdown component: server-authoritative time, one shared 1 Hz interval app-wide, tabular numerals, discrete ticks, throttled announcements (50% / 20% / 10 s / expiry) | `components.md` §3 |
| FR-X-003 | Countdown supports an explicit **paused** state — value frozen and hidden, reason shown, one-shot | U67 |
| FR-X-004 | 5-second undo window replaces confirmation modals for Confirm/Reject; the delayed act is the **driver notification**, not the DB write. Reachable by keyboard shortcut, not toast-only | U41, U82 |
| FR-X-005 | Decision receipts render `score_terms` as structured data; a missing field renders a **gap, not a zero** | `components.md` §4 |
| FR-X-006 | Unavailability is four distinct states — Disabled / Inactive / Read-only / Hidden. **Scope-denied is always Hidden** | U83 |
| FR-X-007 | Announcement politeness matrix and focus-management contract for every live-updating region | U82 |
| FR-X-008 | Data formatting — `en-IN` digit grouping, two duration grammars, mid-truncated identifiers, and zero / unknown / scope-hidden rendered **distinctly** | U81 |
| FR-X-009 | Every empty, loading and error state names a cause and a next action; a failed write states *"Nothing has changed"* | U32 |
| FR-X-010 | Templated state messages, never generated; five reviewed refusal templates | `voice-and-tone.md`, U61 |
| FR-X-011 | **Option cards and decision receipts render as typed tool-call output — never as free text the model composed.** This is an *architectural* property, not a per-screen discipline: there is no code path where the model free-types what a slot looks like | U56, `ai-chat-primitives.md` |
| FR-X-012 | **Sort freezes while a row has focus** — "never move the target under the click." Arrivals accumulate behind a "N new · press R" affordance rather than reordering under a planner mid-decision | U19, README principle 6 |
| FR-X-013 | **Functional motion only** — every animation carries meaning, nothing decorative. In any live-updating view only the row currently changing animates; settled rows recede in contrast | U13, U76 |
| FR-X-014 | **`prefers-reduced-motion` is honoured by substitution, not deletion** — some motion here is informational, and removing it removes information (skeleton shimmer → static block; toast → instant with the same on-screen duration) | `motion.md` |
| FR-X-015 | **Session expiry differs per surface** — planner/ops idle-warn at 55 min and sign out at 60; **a driver is never signed out mid-exception**, because a login screen at a roadside with a lapsing hold is a product failure | `auth-and-scoping.md` |
| FR-X-016 | **Driver offline** — thread history, current promise state and confirmed appointment details stay readable; outbound text queues; **selecting an option is never queued for later**, because committing to capacity that cannot be validated at the moment of commit is the promise this system must not break | U68 |
| FR-X-017 | **One shared sign-in for all six roles**, never a per-role login page. Combined email-or-phone field; error copy is identical whether the email or the password was wrong ("Those details don't match"), never confirming which | `auth-and-scoping.md`, `UI-UX/00-foundations/stitch-prompts-shared-shell.md` prompt A |
| FR-X-018 | **Role picker** shown only to accounts with more than one role, between password submit and landing — a single-role account skips it entirely | Shared-shell prompt A |
| FR-X-019 | **Password reset**, two steps: email confirmation → new password after the emailed link. Response is identical whether or not the email matched an account. **Email-only for v1** — a phone-registered account (the driver role) has no self-service path; defensible since the driver session is already long-lived with silent refresh, so re-entering a password is rare, not routine | Shared-shell prompt B, `SOLUTION_DESIGN.md` §7.5.8 |
| FR-X-020 | **Explicitly not built**: "Remember me" (session length is already role-determined server-side, not user-chosen — a gate-kiosk device staying signed in longer would undermine its own device-bound model), SSO/social login (no third-party identity provider), self-service sign-up (accounts are admin-invited only) | Decided this session; recorded as a requirement *not* to build so it isn't re-proposed later |
| FR-X-021 | **User menu**: identity, role switcher (if >1 role), appearance toggle (client-only, no server round-trip), settings link, sign out, and sign-out-everywhere as one explicit second action — never collapsed into the same button as plain sign-out | Shared-shell prompt C, `SOLUTION_DESIGN.md` §7.5.8 |
| FR-X-022 | **Sign-out-everywhere's actual guarantee is stated honestly in its own copy**: it revokes refresh tokens on other devices; it does not instantly invalidate an access token already issued elsewhere, which remains valid until its own short expiry | `SOLUTION_DESIGN.md` §7.5.8 |
| FR-X-023 | **Notifications panel** (the feed) is a distinct requirement from notification **preferences** (what generates into that feed) — built as two separate pieces even though both were found missing at the same time, so neither gets confused for a duplicate of the other | Shared-shell prompt C |
| FR-X-024 | **Notification preferences use a grouped-category model** (a handful of categories × channel toggle), not per-event granularity — sized for ~5 concurrent internal users, not the noise-taming problem a larger product would have | Shared-shell prompt E, decided this session |
| FR-X-025 | **Account/settings page**: one scrolling page, no sub-navigation tabs. Personal info read-only (Supabase Auth is the identity source — no `update_account_profile` exists). No security section (MFA was evaluated and declined this session), no Danger Zone (account lifecycle is admin-managed, not self-service) | Shared-shell prompt E |
| FR-X-026 | **Search palette**, not a search-results page — a command-palette modal, results grouped by entity type, recent-searches on empty focus, a no-results state with a suggestion. **Facility-scoped by default for v1; no cross-facility toggle** — deferred, since it only applies to roles with cross-facility scope (ops exec/manager, admin) | Shared-shell prompt D, `SOLUTION_DESIGN.md` §7.5.8 |
| FR-X-027 | **Help is a contact link only** — never a self-serve help centre or article library. Protects U73 ("no FAQ surface exists in this product") rather than quietly reopening it | Shared-shell prompt C, U73 |

---

## 3 · Driver chat (`FR-DRV`) — `01-driver-chat/`

| ID | Requirement | Flow | Tools |
|---|---|---|---|
| FR-DRV-001 | **Report a delay** — free-text intake → typed exception → ETA → options → hold → request → **escalate if no feasible slot exists** (this flow's terminal branch, not a separate flow) | Flow 1 | `report_delay_or_update_eta`, `find_feasible_slots`, `request_slot`, `confirm_held_slot`, `escalate_exception`. **`escalate_exception` added 2026-08-22** — the tool already existed in §7.5.4 and the no-feasible-slot escalation is named in this flow's own acceptance criteria (row 10 below), but no requirement had cited the tool that performs it |
| FR-DRV-002 | **Ask for options without a problem** — browse-only; creates a thread and option set, **zero** `driver_exceptions` rows | Flow 2 | `find_feasible_slots` |
| FR-DRV-003 | **Check status** — answered in-thread, no navigation | Flow 3 | `get_appointment_request_status`, `get_current_appointment` |
| FR-DRV-004 | **Change mind / cancel** | Flow 4 | `cancel_appointment` |
| FR-DRV-005 | **Add a constraint** — leave-by / arrive-by capture with disambiguation | Flow 5 | `report_delay_or_update_eta` |
| FR-DRV-006 | **Facility question** — eligibility answered per-invariant; browse-only, no exception created | Flow 6 | `explain_slot_eligibility` |

**Acceptance criteria** (from 14 edge cases): hold lapses · pending expires · lost race (`SLOT_CONFLICT`) ·
option withdrawn mid-conversation · no same-day slot (not an escalation) · no feasible slot (escalation) ·
human takeover · ambiguous shipment · low-confidence ETA · **offline** (read-only cache, queued outbound
text, option cards disabled — selecting an option is **never** queued) · duplicate message · cancelled
shipment · §7.2 refusals · session/connection failure.

---

## 4 · Ops exception console (`FR-OPS`) — `02-ops-exception-console/`

| ID | Requirement | Flow | Tools |
|---|---|---|---|
| FR-OPS-001 | **Triage an escalation** — OPEN → ACKNOWLEDGED → IN_PROGRESS → RESOLVED, acknowledge claims ownership in one action | Flow 1 | `get_escalation_queue`, `acknowledge_escalation` |
| FR-OPS-002 | **Take over a thread**, post as `OPERATIONS`, hand back — driver told on both transitions | Flow 2 | `take_over_thread`, `hand_back_thread` |
| FR-OPS-003 | **Co-pilot draft-reply** — summarise / fetch-context / draft, with **two gates** (Approve → composer → Send); never auto-sends | Flow 3 | — (LLM-assisted, not a mutating tool) |
| FR-OPS-004 | **Triage a capacity incident** — one row, N shipments; request a sequencer proposal; planner applies | Flow 4 | `request_sequencer_proposal` |
| FR-OPS-005 | **Reassign an escalation** — owner changes, stepper and SLA clock unaffected | Flow 5 | `reassign_escalation` |
| FR-OPS-006 | **Resolve vs Cancel** — two terminal states, two driver consequences, each requiring a reason code | Flow 6 | `resolve_escalation`, `cancel_escalation` |

**Acceptance criteria** (11 edge cases): SLA breach while owned · **two coordinators acknowledge
simultaneously** (`ALREADY_ACTIONED`, assertive announcement if focused) · driver replies / goes silent
mid-takeover · stale co-pilot draft · co-pilot unavailable (console fully operable without it) ·
`NOTIFICATION_UNROUTABLE` vs `NOTIFICATION_FAILED` must not look alike · incident's affected set changes ·
hand-back on an unservable thread · shipment actioned elsewhere · `WAREHOUSE_REPLY_CONFLICT` never offers
auto-reconcile · **`SAFETY_OR_REGULATED` suppresses co-pilot draft-reply**.

---

## 5 · Planner dock board (`FR-PLN`) — `03-planner-dock-board/`

| ID | Requirement | Flow | Tools |
|---|---|---|---|
| FR-PLN-001 | **Confirm** a pending request within the 30-second row budget | Flow 1 | `confirm_request` |
| FR-PLN-002 | **Counter-offer** — pick a slot on the board, revalidated through Stage 1 before offering | Flow 2 | `counter_offer` |
| FR-PLN-003 | **Reject + typed reason** — preview the driver's exact message before sending | Flow 3 | `reject_request` |
| FR-PLN-004 | **Hold for information** — pauses the D9 clock exactly once | Flow 4 | `hold_for_information` |
| FR-PLN-005 | **Escalate** — hands the row to ops with the thread attached | Flow 5 | `escalate_request` |
| FR-PLN-006 | **Bulk confirm** — "Select all eligible (N)"; server re-evaluates all five predicates at press time | Flow 6 | `bulk_confirm` |
| FR-PLN-007 | **Block a dock** — form, not a drag gesture; names affected appointments **before** committing | Flow 7 | `block_dock` |
| FR-PLN-008 | **End a dock block** | Flow 8 | `end_dock_block` |
| FR-PLN-009 | **Review and apply a sequencer proposal** — before/after diff on the board, all-or-nothing apply | Flow 9 | `get_scheduling_run`, `apply_schedule_proposal` |
| FR-PLN-010 | **Load the pending queue and dock board** — the read every other row in this table presupposes. Added 2026-08-22, found in a cross-document consistency sweep: every other flow-bearing FR-* table in this document (e.g. `FR-CAR-001`) names its own load-bearing read tool; this one hadn't, even though `get_planner_queue` already exists in §7.5.1 | — | `get_planner_queue` |

**Acceptance criteria** (10 edge cases): **`confirm_request` vs D9 sweeper — the nastiest race**, exactly
one commits, loser gets `ALREADY_ACTIONED` **with the winning transition named** · `SNAPSHOT_STALE` ·
`DISPLACEMENT_DETECTED` · `RUN_ALREADY_ACTIVE` · `SNAPSHOT_DRIFT` / `PARTIALLY_INFEASIBLE` ·
`HOLD_ALREADY_USED` · bulk-confirm predicate drop (skipped row stays visible and named) · blocking a dock
with confirmed appointments inside the window · incident proposal arriving mid-triage · counter-offer
picker open when the request expires.

---

## 6 · Gate / yard kiosk (`FR-GATE`) — `04-gate-yard-kiosk/`

| ID | Requirement | Flow | Tools |
|---|---|---|---|
| FR-GATE-001 | **Shift start** — officer identity captured **once per shift**, stamped on every event | Flow 0 | — |
| FR-GATE-002 | **Search** by shipment ID or plate number (typed entry) | Flow 1 | — |
| FR-GATE-003 | **Truck found → one dominant action** derived from current `queue_state`; never a menu | Flow 2 | — |
| FR-GATE-004 | **Gate-in** — records arrival, returns computed `arrival_state` (EARLY/ON_TIME/LATE) | Flow 3 | `record_gate_in` |
| FR-GATE-005 | **Queue state update**, including call-to-dock | Flow 4 | `update_queue_state` |
| FR-GATE-006 | **Dock-in** — surfaces `DOCK_MISMATCH` as a **deviation, not an error** | Flow 5 | `record_dock_in` |
| FR-GATE-007 | **Unload start / end** — end returns the overrun delta against `expected_unload_min` | Flow 6 | `record_unload_start_end` |
| FR-GATE-008 | **Gate-out** — returns dwell time (`gate_out − gate_in`) | Flow 7 | `record_gate_out` |
| FR-GATE-009 | **Outcome → next truck** — every outcome named, one path forward | Flow 8 | — |
| FR-GATE-010 | **End shift** — clears session identity | Flow 9 | — |

**Acceptance criteria** (8 edge cases): `ALREADY_CHECKED_IN` · `NO_ACTIVE_APPOINTMENT` ·
`INVALID_TRANSITION` (re-fetch and re-render the now-correct action, never blind retry) · `DOCK_OCCUPIED` ·
**two devices racing the same truck** (server state machine is the coordination mechanism) · terminal truck
shows **no action button**, not a disabled one · offline (primary action goes Inactive with reason; retry
copy states it won't double-record) · wrong officer identity mid-shift.

---

## 7 · Carrier portal (`FR-CAR`) — `05-carrier-portal/`

| ID | Requirement | Flow | Tools |
|---|---|---|---|
| FR-CAR-001 | **Load dashboard** — overview, shipments, exceptions render independently | Flow 1 | `get_fleet_overview`, `get_carrier_on_time_performance`, `list_fleet_shipments`, `list_fleet_exceptions` |
| FR-CAR-002 | **Browse and filter shipments** — cross-facility, filter changes membership only | Flow 2 | `list_fleet_shipments` |
| FR-CAR-003 | **Open shipment detail** — read-only; server validates carrier ownership | Flow 3 | `get_shipment_detail` |
| FR-CAR-004 | **Open an exception's shipment** — same single detail destination | Flow 4 | `get_shipment_detail` |
| FR-CAR-005 | **Manual refresh** — no live-updating regions; explicit control beside "last updated" | Flow 5 | all four reads |
| FR-CAR-006 | **Empty states** distinguish "nothing right now" from "nothing yet" | Flow 6 | — |

**Acceptance criteria** (6 edge cases): out-of-scope shipment link **refused server-side**, never
confirming existence · state changes while detail is open (no live update, by design) · shipment appears in
both lists (not a bug) · overview stale relative to list (acceptable; "last updated" is the page-level
signal) · zero-history carrier · long identifier truncation.

**Scope invariant across all six**: never a cross-carrier comparison, benchmark, rank, or aggregate that
would permit inference (U28, M15).

---

## 8 · Admin console (`FR-ADM`) — `06-admin-console/`

| ID | Requirement | Flow | Tools |
|---|---|---|---|
| FR-ADM-001 | **Invite a user** — role **and** scope set in one submission, never a two-step gap | Flow 1 | `invite_user` |
| FR-ADM-002 | **Edit role or scope** | Flow 2 | `update_user` |
| FR-ADM-003 | **Deactivate / Reactivate** — reversible, Moderate friction | Flow 3 | `deactivate_user`, `reactivate_user` |
| FR-ADM-004 | **Remove a user** — High tier, typed confirmation; never offered on own account | Flow 4 | `remove_user` |
| FR-ADM-005 | **Create / edit a facility rule** — `rule_type` from the typed registry, never free text; intraday effectivity supported | Flow 5 | `list_facility_rules`, `create_facility_rule`, `update_facility_rule` |
| FR-ADM-006 | **Edit and simulate policy weights** — aggregate flip count **plus** example cases, before publish | Flow 6 | `simulate_policy_weights`, `publish_policy_version` |
| FR-ADM-007 | **Enable the fairness term** — Danger-zone gate with typed confirmation, distinct from routine tuning | Flow 7 | `publish_policy_version` |
| FR-ADM-008 | **Browse, filter and export the audit log** — export respects the active filter | Flow 8 | `get_audit_log`, `export_audit_log` |
| FR-ADM-009 | **Every write on this console is itself an audit entry** via the same M14 pipeline — no weaker path for admin's own actions | Flow 9 | all |
| FR-ADM-010 | **Browse and filter the user list** — the read every write in FR-ADM-001–004 operates against. Added 2026-08-22, found in a cross-document consistency sweep: `list_users` already existed in §7.5.7 but had never been cited by any requirement, the only load-bearing read in this table that wasn't | — | `list_users` |

**Acceptance criteria** (8 edge cases): removing an escalation owner (names the consequence, proceeds if
confirmed) · deactivating a user mid-kiosk-shift · **two admins publishing policy concurrently** (named
conflict, loser's simulation marked stale) · rule edit invalidating confirmed appointments (warns, does
**not** retroactively mutate) · empty audit export (export disabled, named empty state) · fairness enabled
then published without re-simulating (Publish disabled) · retired `rule_type` (read-only, not broken) ·
removed user not resurfacing in search (Audit is where their history lives).

---

## 9 · Non-functional requirements (`NFR`)

### Performance

| ID | Requirement | Source |
|---|---|---|
| NFR-001 | TTFT **p95 < 1.2 s** | Appendix A |
| NFR-002 | Single-hop turn **p95 < 2.5 s** | Appendix A |
| NFR-003 | `find_feasible_slots` **< 50 ms** | Appendix A |
| NFR-004 | **Hop count tracked as a first-class metric** — a rise is a latency regression no infrastructure tuning fixes | Appendix A |
| NFR-005 | Planner decision budget **≤ 30 s per row**, 7 fields legible without opening anything | §7.3 |

### Correctness

| ID | Requirement | Source |
|---|---|---|
| NFR-006 | **Zero double-booked capacity** — the headline metric; must be 0 | M6, §8 |
| NFR-007 | Determinism — same snapshot + policy version → **byte-identical** ranking and sequencer proposal | M4, §10 |
| NFR-008 | 50-way concurrent race → exactly 1 `HELD`, 49 `SLOT_CONFLICT`, **zero 5xx**, zero orphaned holds | §10 |
| NFR-009 | Idempotent replay — duplicate `dedupe_key` → 1 exception, 1 booking attempt, 1 notification | M9 |

### Availability & degradation

| ID | Requirement | Source |
|---|---|---|
| NFR-010 | Primary regions go **Inactive with a reason** on staleness; secondary regions **disappear** | U84 |
| NFR-011 | **Postgres failure fails loudly** — no circuit breaker, no cache-serve on the correctness path | `SYSTEM_DESIGN.md` §6.1 |
| NFR-012 | Redis loss is survivable — next turn answers correctly from Postgres | §10 chaos-lite |
| NFR-013 | LangSmith never blocks a turn — bounded queue, drop rather than block | Appendix A |
| NFR-014 | LLM provider failure trips a circuit breaker to the fallback provider | `SYSTEM_DESIGN.md` §6.3 |
| NFR-015 `NEW` | **RTO / RPO defined** for the committed-capacity record | Gap 5 |

### Scalability

| ID | Requirement | Source |
|---|---|---|
| NFR-016 | Sustain the §7.3 spike — 20–35 requests / 30 min, 5 concurrent coordinators | §7.3 |
| NFR-017 | 190–240 appointments/day across 6 facilities, 24–32 docks | §1.1 |
| NFR-018 | **Anti-requirement**: no horizontal scaling, sharding or caching layers before a measured bottleneck | `SYSTEM_DESIGN.md` §8 |

### Security & privacy

| ID | Requirement | Source |
|---|---|---|
| NFR-019 | Scope derived server-side from verified identity; **never** from a client-supplied id | M15 |
| NFR-020 | Scope enforced in the **repository layer**, not the router or tool schema | `TECH_STACK.md` §4 |
| NFR-021 | No aggregate or comparative figure that permits cross-tenant inference | `auth-and-scoping.md` |
| NFR-022 `NEW` | Rate limits — per-driver, per-thread, global | Gap 3 |
| NFR-023 `NEW` | DPDP compliance — consent, notice, erasure, 1-year log floor | Gap 2 |

### Auditability & observability

| ID | Requirement | Source |
|---|---|---|
| NFR-024 | Every state change and agent action reconstructable — actor, action, time, policy version, tool call | M14 |
| NFR-025 | LangSmith traces are **thread-scoped with nested LLM and tool spans**, keyed to `chat_threads.thread_id` | `TECH_STACK.md` §8 |
| NFR-026 | Invariant queries run **continuously in CI**, not only at release | §10 |

### Accessibility & i18n

| ID | Requirement | Source |
|---|---|---|
| NFR-027 | **WCAG 2.2 AA baseline**, with a deliberate AAA target-size overlay (56 px gate, 44 px driver) — stated as a self-imposed overlay, not a claim that AA requires it | U30 |
| NFR-028 | English UI, i18n-ready — copy externalised, ~30% expansion tolerance, locale-formatted dates and numbers | U31 |

---

## 10 · Traceability to the brief's acceptance criteria (§12.1)

**This is the axis that matters most, and it was missing from the first draft of this document.**
`SOLUTION_DESIGN.md` states plainly: *"the brief's own 13 questions are the acceptance criteria."* A
requirements document that doesn't map to them is missing its primary external validation.

| # | §12.1 question | Requirements |
|---:|---|---|
| 1 | What must be collected before options are shown? | `FR-SYS-001`, `FR-SYS-002`, `FR-DRV-001` |
| 2 | How is the conversation tied to driver / shipment / appointment? | `FR-SYS-001`, `FR-DRV-001` |
| 3 | How is revised arrival determined and uncertainty communicated? | `FR-SYS-002`, `FR-DRV-005` |
| 4 | What makes a slot feasible? | `FR-SYS-003`, `FR-DRV-006` |
| 5 | What does "available" mean while others are deciding? | `FR-SYS-005`, `FR-X-001`, `FR-X-002` |
| 6 | When does an option become hold / request / booking? | `FR-SYS-005`, `FR-SYS-007`, `FR-DRV-001` |
| 7 | How are simultaneous requests ordered? | `FR-SYS-004`, `FR-SYS-006`, `NFR-008` |
| 8 | When is a facility-wide schedule recalculated? | `FR-SYS-016`, `FR-PLN-009`, `FR-OPS-004` |
| 9 | Stale options, cancellations, duplicates, retries? | `FR-SYS-009`, `FR-SYS-010`, `FR-DRV-004` |
| 10 | What happens when there is no feasible slot? | `FR-SYS-011`, `FR-DRV-001` (Stage 0 next-day path before escalation) |
| 11 | What is explained when the preferred slot is not granted? | `FR-SYS-004`, `FR-X-005`, **`FR-X-011`** (narrated from the receipt, never invented) |
| 12 | Which decisions need human approval? | `FR-SYS-007`, `FR-SYS-012`, `FR-PLN-001`, `FR-ADM-006` |
| 13 | How do you prove no double-booking? | `FR-SYS-006`, `NFR-006`, `NFR-008`, `FR-SYS-034` |

**Every one of the 13 maps to at least one requirement, and every mapping names a surface that realises
it.** Question 11 is worth noting: it depends on `FR-X-011` (tool-call rendering, not free text) — the
architectural property that makes "narrated, not invented" enforceable rather than aspirational.

---

## 11 · Traceability to design and test

| Layer | Design | Test |
|---|---|---|
| `FR-SYS-006` (no double-booking) | `SYSTEM_DESIGN.md` §2, §4 | `TESTING_STRATEGY.md` §3a `same_interval_race`; §10 invariant queries |
| `FR-SYS-008` (pending expiry) | `TECH_STACK.md` §5 sweeper | §3a `pending_expiry_vs_planner_confirm` |
| `FR-SYS-009` (idempotency) | `SYSTEM_DESIGN.md` §6.6 | §10 idempotency replay |
| `FR-SYS-004` / `NFR-007` (determinism) | §5 engine | `TESTING_STRATEGY.md` §6 |
| `FR-DRV-001…006` | `01-driver-chat/flows-and-states.md` | §9.2 fixtures; Playwright suites |
| `FR-OPS-001…006` | `02-ops-exception-console/` | Playwright UI-race #3, #4 |
| `FR-PLN-001…009` | `03-planner-dock-board/` | Playwright UI-race #5; §3a race 3 |
| `FR-GATE-001…010` | `04-gate-yard-kiosk/` | Playwright UI-race #6 |
| `FR-CAR-001…006` | `05-carrier-portal/` | Scope-refusal test (`NFR-019`) |
| `FR-ADM-001…009` | `06-admin-console/` | Playwright UI-race #7 |
| `FR-X-001…016` | `00-foundations/` | Component tests + `TESTING_STRATEGY.md` §4 |
| `FR-X-017…027` | `00-foundations/mockup-shared-shell.html` (mockup-complete; **no spec markdown yet**, `UI-UX/README.md` U122) | **No test coverage** — the capabilities don't exist in code yet, and until U122's spec-markdown gap closes there isn't even a design doc to test against beyond the mockup itself |

**Corrected 2026-08-22**: this table's `FR-X` row previously stopped at `FR-X-010`, silently excluding
the pre-existing `FR-X-011…016` as well as the new `FR-X-017…027` — found in a cross-document consistency
sweep. Split into two rows above so the untested new batch is visible rather than folded into a row that
implied full coverage.

### Requirements with no test yet — visible gaps, not assumptions

`FR-SYS-024…031`, `FR-SYS-041…042` (renumbered 2026-08-22, see §1's correction note), `FR-X-017…027`,
`FR-PLN-010`, `FR-ADM-010`, and `NFR-015`, `NFR-022`, `NFR-023` are all **`NEW`** and have **no test
coverage**, because the capabilities they describe do not exist yet. Listing them here rather than omitting
them is
the point: a requirement absent from the traceability matrix is invisible; one present without a test is a
tracked gap.

---

## 12 · Open items

| # | Item |
|---|---|
| 1 | Personal-vs-operational data classification (`FR-SYS-028`) needs a decision, not a stated tension |
| 2 | Rate-limit thresholds (`FR-SYS-024`) unquantified. **No longer blocked on the model** — chosen and measured 2026-08-21 (`TECH_STACK.md` §7). Remaining decision is policy: acceptable per-driver request rate |
| 3 | RTO/RPO (`NFR-015`) is a business decision, not a technical default |
| 4 | Whether DPDP requirements are binding or documentation-only depends on whether this reaches production with real driver data — **state it explicitly rather than leaving it ambiguous** |
| 5 | `FR-SYS-022` (KPI/analytics surface) has no UI-UX surface — §2's deferred personas own it; operational metrics live on planner/ops today |
