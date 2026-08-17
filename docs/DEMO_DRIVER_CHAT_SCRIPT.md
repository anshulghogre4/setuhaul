# Driver chat demo script (Ravi Kumar / DRV001)

**Full ordered manual demo (all roles + stress):** [DEMO_MANUAL_RUNBOOK.md](DEMO_MANUAL_RUNBOOK.md)  
**Judge checklist:** [DEMO_DAY_READINESS.md](DEMO_DAY_READINESS.md)

Use this after signing in at `http://localhost:5173/driver/login` as `ravi.kumar@setuhaul.com`.

**Verified identity (live):** `USR001` → `DRV001` → facility `FAC-JAI-01`.  
**Presentation: 17 Aug 2026.** Hero shipment still **`SHP-D16-RAVI`** (frozen 16 Aug data) — use this for slot search/request. Keep the `2026-08-16T…+05:30` ETA string below.  
**Older seed shipment:** `SHP1017` may still appear; if asked which shipment, pick `SHP-D16-RAVI`.  
**Seed note:** `users.full_name` is `Ravi Kumar` while `drivers.driver_name` for `DRV001` is `Rajesh Kumar`.

Passwords stay in gitignored `POC_TEAM_ACCOUNTS.local.md` only.

---

## 0. Demo-day scheduling (Sprint 3) — prefer these

| # | Type this | Expected tools / outcome |
|---|---|---|
| A | `I need help with shipment SHP-D16-RAVI.` | Locks context to demo hero shipment. **Zero writes** — must not create an escalation or any other write (see fix note below). |
| B | `Show feasible slots after 6 PM.` | `find_feasible_slots` → ranked options labeled **not reserved**. |
| C | `Request slot …` with an exact returned `slot_id` (or `D16-SLT-RACE`). | `request_slot` → `PENDING_CONFIRMATION` or conflict refresh. |
| D | `Has the warehouse confirmed my new slot?` | `get_appointment_request_status` → pending ≠ confirmed. |
| E | Second browser as Amit on `SHP-D16-RACE-B` → same `D16-SLT-RACE`. | One winner; loser conflict + refresh. |
| F | As Vikas: `Find slots for SHP-D16-NOSLOT`. | Zero options + escalation; no invented slot. |
| G | `Cancel my pending appointment request for SHP-D16-RAVI because plans changed.` | `cancel_appointment` when pending exists; capacity freed. |
| H | After cancel: `Show feasible slots after 6 PM.` | Freed slot can reappear. |

Multi-browser race, Ops takeover, and CONTEND sample: see [DEMO_MANUAL_RUNBOOK.md](DEMO_MANUAL_RUNBOOK.md) Phases C–G.

**Fix note (2026-08-17 06:35 IST, needs redeploy):** row A previously mis-triggered `escalate_exception` because `prompts.py` matched the bare word "help" instead of gating on `NO_FEASIBLE_SLOTS`/an explicit escalate ask. Fixed in code; not yet redeployed. A stray `ESC-53B8A6EA0A37` escalation for `SHP-D16-RAVI` may still show up in Ops until cleared.

---

## 1. Shipment and appointment (Sprint 2 reads)

| # | Type this | Expected tools / outcome |
|---|---|---|
| 1 | `Show my current shipment and appointment status.` | Context tools; may mention `SHP1017` and/or D16 shipments. |
| 2 | Click **View appointment** | Same intent as row 1 via quick action. |

---

## 2. Facility details (Sprint 2 reads)

| # | Type this | Expected tools / outcome |
|---|---|---|
| 3 | Click **Facility details** or type `What are my facility details?` | Facility `FAC-JAI-01` / Jaipur hours. |
| 4 | `Show me the warehouse contacts for facility FAC-JAI-01.` | Must call `get_facility_details`. Contacts use `facility_contacts.contact_role`. |

---

## 3. ETA update with clarification and confirmation (Sprint 2 write)

Prefer **`SHP-D16-RAVI`** for demo-day. `SHP1017` works for older-seed ETA demos.

| # | Type this | Expected tools / outcome |
|---|---|---|
| 5 | `I will be late.` | Clarification: ask for revised arrival time. |
| 6 | `Repair will take 45 minutes.` | Repair ≠ ETA; ask for explicit arrival timestamp with timezone. |
| 7 | `My new ETA for SHP-D16-RAVI is 2026-08-16T18:45:00+05:30 due to traffic.` | Confirmation preview; no write yet. |
| 8 | Confirm via UI **Confirm & write ETA** | `report_delay_or_update_eta` with `confirmed=true`; rail refreshes. |

---

## 4. Ambiguous shipment clarification

Ravi may have multiple actives (`SHP1017` + `SHP-D16-RAVI`). Vikas has `SHP-D16-NOSLOT` + `SHP-D16-MULTI-B`.

| # | Type this | Expected tools / outcome |
|---|---|---|
| 9 | `I will be late.` without naming a shipment | `CLARIFICATION_REQUIRED` with candidate `shipment_id`s when multiple actives. |

---

## 5. Duplicate / weak-connectivity retry

| # | Type this | Expected tools / outcome |
|---|---|---|
| 10 | Replay the **same** `client_message_id` (API/network retry) | Duplicate ignored; one business effect. UI usually mints a new id per send. |

---

## 6. Slot search, request, status, cancel, reschedule (Sprint 3)

Displayed options are **not reserved**.

| # | Type this | Expected tools / outcome |
|---|---|---|
| 11 | `Find feasible replacement slots for SHP-D16-RAVI.` | Ranked `DISPLAYED_NOT_RESERVED` or `NO_FEASIBLE_SLOTS` + escalation. Zero appointment writes on search. |
| 12 | `Request slot <exact slot_id> for SHP-D16-RAVI.` | `PENDING_CONFIRMATION` or conflict/stale refresh. Never claim confirmed booking. |
| 13 | `What is the status of my appointment request for SHP-D16-RAVI?` | Pending/confirmed/closed/no-request from Postgres. |
| 14 | `Cancel my pending appointment request for SHP-D16-RAVI because plans changed.` | Cancel + capacity release. |
| 15 | Reschedule: after a fresh search, ask to move to a **new** exact `slot_id` | `reschedule_appointment` → new pending (if enabled in chat). |

Ops **confirm / reject / expire** are ops/admin REST (not Driver chat). Use [DEMO_MANUAL_RUNBOOK.md](DEMO_MANUAL_RUNBOOK.md) Phase F.

---

## 7. Ops cross-check

1. Logout from driver portal.
2. Login at `/ops/login` as `priya.mehta@setuhaul.com`.
3. **Refresh** → matching exception/ETA and escalation list.
4. **Confirm** a pending appointment via the **Pending confirmations** panel button; reject via API `/docs` (no reject button yet).

---

## Quick-copy prompts

```
Show my current shipments.
I need help with shipment SHP-D16-RAVI.
I will be late on SHP-D16-RAVI.
Repair will take 90 minutes.
My new ETA for SHP-D16-RAVI is 2026-08-16T18:45:00+05:30 due to traffic.
Show feasible slots after 6 PM.
Request slot <PASTE_SLOT_ID> for SHP-D16-RAVI.
Has the warehouse confirmed my new slot?
Cancel my pending appointment request for SHP-D16-RAVI because plans changed.
Find feasible slots for SHP-D16-NOSLOT.
```

Constraint (FDE brief): drivers get **feasible options for their shipment**, not an unrestricted dump of every open facility slot. Shown options are informational until `request_slot`.
