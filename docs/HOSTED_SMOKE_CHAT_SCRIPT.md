# Hosted smoke chat script (Vercel → ECS BFF → AgentCore)

Purpose-built subset of [DEMO_MANUAL_RUNBOOK.md](DEMO_MANUAL_RUNBOOK.md) for testing **only the
hosted path**. Three things are pending hosted browser verification: the 2026-08-17 05:35 IST
infra fixes (async event-loop entrypoint, Upstash migrated to `us-east-1` + Redis call batching,
Supavisor session-mode pooler, escalation `resolution_note` persistence — verified only via
`agentcore.cmd invoke` CLI so far); the Ops **Pending confirmations** dashboard panel with a
one-click **Confirm** button (local-verified only: backend units + frontend build); and a
2026-08-17 06:35 IST prompt fix for a live-caught bug where the standard context-lock line
("I need help with shipment X") mis-triggered `escalate_exception` (code fixed, not yet
redeployed). That's the gap this script closes. See [[handoff]] / [[current-state]] for the full
fix writeup.

Hosted and local share the **same** Supabase Postgres and Upstash Redis — this is not a separate
environment's data, so runbook cast IDs and demo-day state still apply.

Passwords: gitignored `POC_TEAM_ACCOUNTS.local.md` only — never paste them here.

---

## 0. Prep

- [ ] Hosted SPA: `https://setuhaul-roan.vercel.app/driver/login`
- [ ] BFF health: `https://se-e5cad5d30b1a4f22b9aeea032827f81b.ecs.us-east-1.on.aws/health/live` → expect `200`
- [ ] Have CloudWatch (AgentCore Runtime log group) and LangSmith (`setuhaul.chat` project) open in another tab to watch traces live
- [ ] Fallback if AgentCore 503s: local `uvicorn` `:8000` + Vite `:5173` (leave `AGENTCORE_RUNTIME_ARN` blank) — do **not** treat a 503 as a hosted PASS
- [ ] Do **not** run `reset_demo_day.py` against this data unless the owner asks — it mutates the same shared demo cast local testing also depends on

---

## 1. Login + read-path smoke (proves the event-loop + pooler fix live)

**Who:** `/driver/login` → `ravi.kumar@setuhaul.com`

| Step | Type exactly | Expect | Proves |
|---|---|---|---|
| 1 | *(after login)* Check profile rail | `USR001` / `DRV001` / `FAC-JAI-01` | Auth path healthy |
| 2 | `Show my current shipments.` | Three actives: `SHP-D16-RACE-A`, `SHP-D16-RAVI`, `SHP1017`. No 500/503, no `DuplicatePreparedStatementError` in the reply. | `get_driver_operational_context` — the exact tool that hit the live Postgres pooler bug |
| 3 | `I need help with shipment SHP-D16-RAVI.` | Context locks cleanly, **zero writes** | Repeats the same tool path on a second turn (catches "fails once, retry succeeds" pooler symptoms) |
| 4 | `What is my current exception status?` | Clean status reply, no error | `get_exception_status` — the other tool that hit the bug |

**Fail signal:** any 5xx, a reply that surfaces a raw exception string, or the *first* message failing while a retry succeeds (classic stale-event-loop-connection symptom). **Also fail** if step 3 creates an escalation instead of just locking context — that was a live bug (`prompts.py` matched the bare word "help") fixed 2026-08-17 06:35 IST but not yet redeployed; a stray `ESC-53B8A6EA0A37` for `SHP-D16-RAVI` may already be sitting in the Ops queue from before the fix.

---

## 2. ETA write path (proves the write side, not just reads)

Continue as Ravi.

| Step | Type exactly | Expect |
|---|---|---|
| 5 | `I will be late on SHP-D16-RAVI.` | Asks for revised arrival time |
| 6 | `Repair will take 90 minutes.` | Repair ≠ ETA; asks for explicit timestamp with timezone |
| 7 | `My new ETA for SHP-D16-RAVI is 2026-08-16T18:45:00+05:30 due to traffic.` | Confirmation preview; no write yet |
| 8 | Confirm via UI **Confirm & write ETA** | `report_delay_or_update_eta` succeeds; rail ETA refreshes |

---

## 3. Escalation resolution-note round trip (proves the second 04:35/04:10 IST fix live)

The `resolution_note` column/threading was migration-applied and code-verified but not yet
clicked through end to end in the browser.

**Who:** Ops — `/ops/login` → `priya.mehta@setuhaul.com`

| Step | Action | Expect |
|---|---|---|
| 9 | Open Operations dashboard → escalation/exception list | Loads without error |
| 10 | Pick an open escalation/exception, **Mark Resolved** with a remark, e.g. `Rebooked driver into evening slot.` | Resolve call succeeds |
| 11 | Back in Ravi's chat (or the same shipment's exception owner): `What is my current exception status?` | Reply now surfaces the resolution note text, not just a bare "resolved" status |

**Fail signal:** resolve succeeds in Ops but the note never appears back through `get_exception_status` — that's the exact gap the 04:10 IST entry flagged as fixed at the DB/code level but not yet browser-verified.

---

## 4. Ops appointment-confirm UI (brand new — no hosted verification yet)

A **Pending confirmations** panel with a one-click **Confirm** button was just added to the Ops
dashboard (`GET /api/v1/operations/pending-confirmations` + `POST
/api/v1/shipments/{shipment_id}/appointments/{appointment_id}/confirm`, facility-scoped,
idempotency-keyed). Local backend units (86 passed, incl. 2 new tests) and `npm run build` pass,
but this has **not been clicked through on the hosted URL** — it goes through the same ECS
BFF → Postgres path the pooler fix touched, so it's worth hitting here too. **Reject still has
no UI button** — that stays REST/`/docs`-only.

**Who:** Ops — `/ops/login` → `priya.mehta@setuhaul.com` (Jaipur facility)

| Step | Action | Expect |
|---|---|---|
| 12 | First create a fresh pending appointment: as Ravi, run section 5 below through `Request slot <PASTE_SLOT_ID> for SHP-D16-RAVI.` | Appointment status `PENDING_CONFIRMATION` |
| 13 | Back in Ops, refresh the dashboard | New row appears in **Pending confirmations** for `SHP-D16-RAVI` |
| 14 | Click **Confirm** on that row | Button shows "Confirming…", row disappears/list refreshes, no error alert |
| 15 | Back in Ravi's chat: `Has the warehouse confirmed my new slot?` | `get_appointment_request_status` now reports **confirmed** |

**Fail signal:** the row never appears (facility-scope query broken hosted), the Confirm click alerts an error, or the driver-side status still reads pending after a confirmed click.

---

## 5. Multi-tool-call stress (Phase B happy path — exercises several tool calls in one AgentCore session)

| Step | Type exactly | Expect |
|---|---|---|
| 16 | `Show feasible slots after 6 PM.` | Ranked options, **DISPLAYED_NOT_RESERVED**, `REC-…` |
| 17 | Copy one exact `slot_id` from the reply | — |
| 18 | `Request slot <PASTE_SLOT_ID> for SHP-D16-RAVI.` | `PENDING_CONFIRMATION` or conflict refresh with fresh options — never "confirmed" |
| 19 | `Has the warehouse confirmed my new slot?` | Pending ≠ confirmed (until section 4 is run against this same request) |

---

## 6. Timing check (Redis batching win — not yet numerically confirmed)

For each chat turn above, note wall-clock reply time. Prior hosted baseline before batching:
**28.6s** for a `list_active_shipments`-class turn (2026-08-16 21:05 IST, pre-fix). After Redis
call batching (~10 sequential Upstash round trips → ~2), turns should be visibly faster, but this
has not been re-measured via a fresh CloudWatch trace. Pull one during this run if possible —
that closes the one still-open item from the 05:35 IST fix entry.

---

## Sign-off

| Check | Result | Notes |
|---|---|---|
| Hosted read-path (event-loop/pooler fix) | ☐ PASS ☐ FAIL | |
| Hosted write-path (ETA) | ☐ PASS ☐ FAIL | |
| Resolution-note round trip | ☐ PASS ☐ FAIL | |
| Ops confirm-button round trip (new, hosted-untested) | ☐ PASS ☐ FAIL | |
| Multi-tool scheduling turn | ☐ PASS ☐ FAIL | |
| Latency vs 28.6s baseline | ☐ Faster ☐ Same ☐ Slower ☐ Not measured | |
| AgentCore 503 encountered | ☐ Yes (fell back to local) ☐ No | |

---

## Quick-copy prompts

```
Show my current shipments.
I need help with shipment SHP-D16-RAVI.
What is my current exception status?
I will be late on SHP-D16-RAVI.
Repair will take 90 minutes.
My new ETA for SHP-D16-RAVI is 2026-08-16T18:45:00+05:30 due to traffic.
Show feasible slots after 6 PM.
Request slot <PASTE_SLOT_ID> for SHP-D16-RAVI.
Has the warehouse confirmed my new slot?
```

(Send the last two lines once before section 4 — to create the pending appointment the Ops
Confirm button needs — then repeat `Has the warehouse confirmed my new slot?` after clicking
Confirm to see it flip to confirmed.)

Full stress phases (race, NOSLOT, cancel/stale, CONTEND, reschedule) are unaffected by these
hosted infra fixes — run them from [DEMO_MANUAL_RUNBOOK.md](DEMO_MANUAL_RUNBOOK.md) directly
against the hosted URL if a fuller hosted pass is wanted, using the same login accounts.
