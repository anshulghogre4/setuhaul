# Manual FDE demo + stress runbook

Ordered manual test script against `docs/SetuHaul_FDE_Challenge.pdf` (§8 chat types, §11.2 stress, §12.1–12.2 demo beats).

**Primary runbook** for humans. Judge status sheet: [DEMO_DAY_READINESS.md](DEMO_DAY_READINESS.md).  
Quick Ravi prompt list: [DEMO_DRIVER_CHAT_SCRIPT.md](DEMO_DRIVER_CHAT_SCRIPT.md).  
Cast IDs: [../supabase/demo/fixtures/stress_scenarios.json](../supabase/demo/fixtures/stress_scenarios.json).

Demo-day anchor: **2026-08-16** (`Asia/Kolkata`). Sprint 1–3 exit gates are **COMPLETE**.

Passwords: gitignored `POC_TEAM_ACCOUNTS.local.md` only — never paste them here.

---

## Prep (do this first)

### Reset (shared Ravi demos)

Re-apply of demo SQL is additive and will **not** undo prior ETA/slot/chat
mutations. Between demos (or before a fresh Ravi show):

```powershell
python supabase/demo/reset_demo_day.py --mode cast --include-shp1017 --confirm
```

Dry-run first if unsure: add `--dry-run` (no `--confirm` needed). Details:
[../supabase/demo/README.md](../supabase/demo/README.md). Does not change Auth
passwords.

### Servers

```bash
# Terminal 1 — backend
cd backend
# activate venv, then:
uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload

# Terminal 2 — frontend
cd frontend
npm run dev
```

- UI: `http://localhost:5173`
- API docs: `http://127.0.0.1:8000/docs`
- Health: `http://127.0.0.1:8000/health/live`

### Browsers (recommended)

| Profile | Who | Login |
|---|---|---|
| A | Ravi Kumar | `/driver/login` → `ravi.kumar@setuhaul.com` |
| B | Amit Singh | `/driver/login` → `amit.singh@setuhaul.com` |
| C | Ops (Priya) | `/ops/login` → `priya.mehta@setuhaul.com` |

Optional later: Vikas (`vikas.sharma@setuhaul.com`), contention drivers `driver.drv004@setuhaul.com` … `drv013@`.

### Cast cheat-sheet

| ID | Role in demo |
|---|---|
| `SHP-D16-RAVI` | Ravi happy-path scheduling (prefer over older `SHP1017`) |
| `SHP-D16-RACE-A` / `SHP-D16-RACE-B` | Same-slot race on `D16-SLT-RACE` |
| `D16-SLT-RACE` | Contested evening STANDARD slot |
| `SHP-D16-NOSLOT` | Zero feasible → escalation |
| `SHP-D16-MULTI-B` | Vikas second shipment (disambiguation) |
| `SHP-D16-CONTEND-01..10` | Scarce evening contention cast |
| `SHP1017` | Older seed read-path only (optional) |

### Global pass rules

- [ ] Options always labeled **not reserved** / not a confirmed booking
- [ ] Pending request ≠ warehouse confirmed
- [ ] No invented slots when NOSLOT
- [ ] Cross-driver shipment IDs fail closed (403 / out of scope)

---

## Phase A — Sprint 2 ETA + clarification

**PDF:** §8 report/clarify · §11.2 repair≠ETA · §12.2 delay+clarification · §12.1 Q3

**Who:** Browser A — Ravi at `/driver/login`

| Step | Type exactly | Expect |
|---|---|---|
| A1 | *(after login)* Check profile rail | `USR001` / `DRV001` / `FAC-JAI-01` |
| A2 | `Show my current shipments.` | Lists active work; if both `SHP1017` and `SHP-D16-RAVI` appear, you will pick D16 next |
| A3 | `I will be late on SHP-D16-RAVI.` | Asks for revised **arrival** time (not just “late”) |
| A4 | `Repair will take 90 minutes.` | Repair ≠ ETA; asks for explicit timestamp **with timezone** |
| A5 | `My new ETA for SHP-D16-RAVI is 2026-08-16T18:45:00+05:30 due to traffic.` | Confirmation preview of exact display ETA; **no write yet** |
| A6 | Confirm via UI **Confirm & write ETA** (or explicit chat confirm) | `report_delay_or_update_eta` succeeds; context rail ETA refreshes |

**Pass / fail**

- [ ] PASS — repair rejected as ETA; confirmed write only after exact ETA confirmation
- [ ] FAIL — wrote ETA from “repair 90 min” or invented a time

---

## Phase B — Ravi happy-path scheduling (D16)

**PDF:** §8 options/choose/status · §12.2 later possibilities · §12.1 Q1,Q4,Q5,Q6

**Who:** Browser A — Ravi (continue same session)

After `--mode cast` reset, `D16-APT-RAVI-OLD` is **historical** (`CANCELLED` / not current). `SHP-D16-RAVI` has **no** current appointment, so Phase B can use bare `request_slot`. `APT1017` on `SHP1017` stays CONFIRMED for disambiguation.

| Step | Type exactly | Expect |
|---|---|---|
| B1 | `I need help with shipment SHP-D16-RAVI.` | Locks context to demo hero shipment |
| B2 | `Show feasible slots after 6 PM.` | `find_feasible_slots` → ranked options, **DISPLAYED_NOT_RESERVED**, includes `REC-…` / policy version if shown |
| B3 | Copy one exact `slot_id` from the reply (do not invent) | Keep it for B4 |
| B4 | `Request slot <PASTE_SLOT_ID> for SHP-D16-RAVI.` | `request_slot` → `PENDING_CONFIRMATION` **or** conflict refresh with new options |
| B5 | `Has the warehouse confirmed my new slot?` | `get_appointment_request_status` → **pending ≠ confirmed** |

**Pass / fail**

- [ ] PASS — options not reserved; request creates pending only; status truthful
- [ ] FAIL — assistant claims “confirmed” or books without an exact `slot_id`

---

## Phase C — Same-slot race (two browsers)

**PDF:** §11.2 two drivers same option · §12.2 two requests same capacity · §12.1 Q11,Q13

**Prep:** Prefer a fresh race slot. If `D16-SLT-RACE` is already taken from Phase B, either cancel that pending first, or race on another open evening `slot_id` both drivers can see.

| Browser | Login | Shipment |
|---|---|---|
| A | Ravi | `SHP-D16-RACE-A` |
| B | Amit | `SHP-D16-RACE-B` |

| Step | Who | Type exactly | Expect |
|---|---|---|---|
| C1 | A | `I need help with shipment SHP-D16-RACE-A.` | Context locked |
| C2 | B | `I need help with shipment SHP-D16-RACE-B.` | Context locked |
| C3 | A | `Show feasible slots after 6 PM.` | Options include race slot if free |
| C4 | B | `Show feasible slots after 6 PM.` | Same |
| C5 | A+B **nearly together** | `Request slot D16-SLT-RACE for SHP-D16-RACE-A.` / `Request slot D16-SLT-RACE for SHP-D16-RACE-B.` | **One** winner → `PENDING_CONFIRMATION`; **one** loser → conflict / refresh; **no double-book** |

**Pass / fail**

- [ ] PASS — exactly one active claim on the raced slot
- [ ] FAIL — both claim confirmed/pending on the same slot

---

## Phase D — Vikas NOSLOT + multi-shipment

**PDF:** §8 fallback no slot · §11.2 no same-day feasible + multi-shipment · §12.2 no feasible→escalation · §12.1 Q10,Q12

**Who:** Browser A (or new window) — Vikas at `/driver/login` → `vikas.sharma@setuhaul.com`

| Step | Type exactly | Expect |
|---|---|---|
| D1 | `I have two shipments — help me.` or `What are my active shipments?` | Mentions `SHP-D16-NOSLOT` and `SHP-D16-MULTI-B` (disambiguation) |
| D2 | `Find feasible slots for SHP-D16-NOSLOT.` | **Zero options**; escalation language; **no invented slot** |
| D3 | Optional: `Escalate this no-slot case for SHP-D16-NOSLOT.` | Durable escalation / queue language if tool fires |
| D4 | `Find slots for SHP-D16-MULTI-B.` | Different result than NOSLOT (disambiguation works) |

**Pass / fail**

- [ ] PASS — NOSLOT never invents capacity; multi-shipment not silently mixed
- [ ] FAIL — invents a same-day slot or books NOSLOT

---

## Phase E — Stale options + cancel frees capacity

**PDF:** §11.2 cancel frees slot · stale/change mind · §12.2 option disappears · §12.1 Q9

**Who:** Browser A — Ravi

| Step | Type exactly | Expect |
|---|---|---|
| E1 | `I need help with shipment SHP-D16-RAVI.` | Context lock |
| E2 | `Show feasible slots after 6 PM.` | Fresh options + recommendation |
| E3 | *(Stale path)* Change ETA first: repeat Phase A5–A6 with a **different** evening ETA, **or** try requesting a slot_id from an **old** option list after ETA change | Stale / refresh / revalidation — must **not** silently book a dead option |
| E4 | Get a **fresh** list, then `Request slot <PASTE_SLOT_ID> for SHP-D16-RAVI.` | Pending if free |
| E5 | `Cancel my pending appointment request for SHP-D16-RAVI because plans changed.` | `cancel_appointment` → cancelled; capacity released |
| E6 | `Show feasible slots after 6 PM.` | Freed slot can appear again among options |

**Pass / fail**

- [ ] PASS — stale path fails safe; cancel releases; later search can see capacity
- [ ] FAIL — books after ETA change without revalidation, or cancel leaves slot unusable incorrectly

---

## Phase F — Ops takeover

**PDF:** §12.1 Q12 human takeover · §12.2 escalation · confirm lifecycle

**Who:** Browser C — Ops at `/ops/login` → `priya.mehta@setuhaul.com` (Jaipur facility)

| Step | Action | Expect |
|---|---|---|
| F1 | Open Operations dashboard | Facility-scoped summary loads |
| F2 | Click **Refresh** | Freshness timestamp updates |
| F3 | Find **escalation / exception** list | Open NOSLOT escalation from Phase D visible (or open exceptions) |
| F4 | Confirm path: use API `/docs` or available ops UI to **confirm** a `PENDING_CONFIRMATION` with warehouse ref | Status → `CONFIRMED`; never label conflict as confirmed |
| F5 | Optional reject: reject another pending with reason | Status → `REJECTED`; slot freed |

**Note:** Warehouse **confirm/reject/expire** are ops/admin REST paths (not Driver chat tools). Use Swagger at `/docs` with an Ops bearer token if the UI has no confirm button yet.

**Pass / fail**

- [ ] PASS — Ops sees escalation; confirm/reject truthful; no false “confirmed”
- [ ] FAIL — Ops cannot see NOSLOT escalation or marks conflict confirmed

---

## Phase G — Optional CONTEND sample (scarce evening)

**PDF:** §11.2 ten drivers / 3–4 slots · §12.1 Q7

Full **10×4** concurrency is already proven by live pytest (`SETUHAUL_RUN_LIVE_DB_TESTS=1` + `tests/integration/test_live_demo_day_load.py`). Manual sample is enough for demo day.

| Step | Action | Expect |
|---|---|---|
| G1 | Login as `driver.drv004@setuhaul.com` (CONTEND-01) | Driver chat |
| G2 | `I need help with shipment SHP-D16-CONTEND-01.` then `Show feasible slots after 6 PM.` | Evening STANDARD options |
| G3 | Request an exact evening `slot_id` | Pending or conflict refresh |
| G4 | Repeat with `driver.drv005@…` / `SHP-D16-CONTEND-02` on the **same** slot if possible | At most one active claim on that slot |

**Pass / fail**

- [ ] PASS — no double-book on sampled slot
- [ ] FAIL — two actives on one slot

Hosted Locust (laptop → BFF): [`loadtests/README.md`](../loadtests/README.md). Suite A = Phases A–D chat prompts. Suite B = this CONTEND cast via REST (10 users, zero double-books). From **repo root**:

```powershell
# Suite A — web UI at http://127.0.0.1:8089 (then Start: 5 users / 1 per second)
uv run --with locust locust -f loadtests/locust_runbook_chat.py --web-host 127.0.0.1 --web-port 8089

# Suite A — headless (LLM; keep short)
uv run --with locust locust -f loadtests/locust_runbook_chat.py --headless -u 5 -r 1 -t 3m

# Suite B — reset first; 409 = pass; two winners on one slot = fail
python supabase/demo/reset_demo_day.py --mode cast --include-shp1017 --confirm
uv run --with locust locust -f loadtests/locust_slot_contention.py --headless -u 10 -r 10 -t 90s
```

### How to score pass / fail (do not mix scorecards)

The **Sign-off** table below is the runbook verdict. Tick a phase **PASS** only when the **Expect** column is true (read the assistant reply, and for C/G check the slot has one active claim). Locust HTTP 200 is **not** that verdict.

| Scorecard | PASS | FAIL |
|---|---|---|
| **This runbook (Phases A–G)** | Reply matches Expect (repair≠ETA, options not reserved, pending≠confirmed, NOSLOT invents nothing, one winner on a raced slot) | Opposite of that phase’s FAIL line |
| **Locust Suite A** (hosted chat up) | `auth_me` + chat rows ~0% fail; Locust exit 0 | Any `http_5xx` / `success_false` (example: 2026-08-14 C2 **503** → Suite A not clean) |
| **Locust Suite B** (Phase G) | Prints `PASS_zero_double_books`; exit 0 | Prints `FAIL_double_book`; exit 1 |

Suite A does **not** read reply text and does **not** run C5/B4/E5 unless `SETUHAUL_LOCUST_MUTATE=1`. Phase F is Ops UI only. For a judge demo, walk this file in the browser; use Locust for hosted load + zero double-books.

---

## Optional extras (if time)

| Demo | How |
|---|---|
| Facility contacts | Ravi: `Show me the warehouse contacts for facility FAC-JAI-01.` |
| Duplicate message | Replay same `client_message_id` via API (UI usually mints a new id) |
| Admin global RO | `/ops/login` as `ananya.rao@setuhaul.com` → network-wide read |
| Early/late snapshot data | Ops/API observation of `SHP-D16-EARLY` / `LATE` / `UNDOCK` / `FUTURE` |

---

## PDF coverage map (this runbook)

| PDF beat | Phase |
|---|---|
| Delay + clarification / repair≠ETA | A |
| Feasible options / compare / not reserved | B |
| Request pending ≠ confirmed | B, F |
| Same-slot race / preferred not granted | C |
| No feasible → escalation / human takeover | D, F |
| Stale options / cancel frees capacity | E |
| Scarce capacity / no double-book | C, G (+ automated load proof) |
| Multi-shipment disambiguation | D |

---

## Out of scope — do not claim

- Facility-wide OR-Tools / `propose_facility_schedule` (deferred)
- Live GPS / maps / messaging channels
- Displayed options are **reserved**
- Password rotation (same 3 shared role buckets until after demo)
- Warehouse-reply conflict automation (lightweight escalate path exists; not a full warehouse messaging channel)

---

## Quick-copy prompts

```
Show my current shipments.
I will be late on SHP-D16-RAVI.
Repair will take 90 minutes.
My new ETA for SHP-D16-RAVI is 2026-08-16T18:45:00+05:30 due to traffic.
I need help with shipment SHP-D16-RAVI.
Show feasible slots after 6 PM.
Request slot <PASTE_SLOT_ID> for SHP-D16-RAVI.
Has the warehouse confirmed my new slot?
I need help with shipment SHP-D16-RACE-A.
I need help with shipment SHP-D16-RACE-B.
Request slot D16-SLT-RACE for SHP-D16-RACE-A.
Request slot D16-SLT-RACE for SHP-D16-RACE-B.
What are my active shipments?
Escalate this no-slot case for SHP-D16-NOSLOT.
Cancel my pending appointment request for SHP-D16-RAVI because plans changed.
Find feasible slots for SHP-D16-NOSLOT.
Find slots for SHP-D16-MULTI-B.
I need help with shipment SHP-D16-CONTEND-01.
```

---

## Sign-off

| Phase | Result | Notes |
|---|---|---|
| Prep | ☐ PASS ☐ FAIL | |
| A ETA | ☐ PASS ☐ FAIL | |
| B Happy path | ☐ PASS ☐ FAIL | |
| C Race | ☐ PASS ☐ FAIL | |
| D NOSLOT | ☐ PASS ☐ FAIL | |
| E Stale/cancel | ☐ PASS ☐ FAIL | |
| F Ops | ☐ PASS ☐ FAIL | |
| G CONTEND sample | ☐ PASS ☐ SKIP ☐ FAIL | |
