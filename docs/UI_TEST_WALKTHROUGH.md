# UI test walkthrough — 17 Aug presentation

Use this as the click-by-click script. Exact chat lines stay in [DEMO_MANUAL_RUNBOOK.md](DEMO_MANUAL_RUNBOOK.md). Passwords stay in `POC_TEAM_ACCOUNTS.local.md`.

**URLs (pick one path and stay on it)**

| Path | Driver login |
|---|---|
| Hosted | https://setuhaul-roan.vercel.app/driver/login |
| Local | http://localhost:5173/driver/login |

Ops: same host + `/ops/login`. Dispatch (optional): `/dispatch`.

**Before you start:** `python supabase/demo/reset_demo_day.py --mode cast --include-shp1017 --confirm`

Open **three browser profiles** (or Chrome profiles): A Ravi, B Amit, C Priya.

Frozen demo timestamps: always `2026-08-16T…+05:30`, even though the show is 17 Aug.

---

## 1. Ravi login + three shipments (2 min)

1. Profile A → `/driver/login`.
2. Email `ravi.kumar@setuhaul.com` + Driver password → Submit.
3. You should land on `/driver` chat, not Ops.
4. Rail: `USR001` / `DRV001` / `FAC-JAI-01`.
5. Appointment on the rail is **empty on purpose** (primary is `SHP-D16-RACE-A`; hero `SHP-D16-RAVI` also has no current slot so Phase B can `request_slot`). If a judge asks “where is his appointment?”, say the hero shipment has none yet, or type `Show my current appointment for SHP1017.` (`APT-A086CEB8CAB7` CONFIRMED on `SLOT-JAI-029`). Do not invent a slot_id.
6. Type: `Show my current shipments.`
7. Expect **three** actives: `SHP-D16-RACE-A`, `SHP-D16-RAVI`, `SHP1017`.
8. Type: `I need help with shipment SHP-D16-RAVI.` (do not let it guess).

**Pass:** JWT role, three shipments, context locked to RAVI.  
**Fail:** lands on Ops, or books/answers about RACE-A without asking.

Optional chips: **View appointment**, **Facility details**, **Update ETA** — they send canned chat; still name `SHP-D16-RAVI` after.

---

## 2. Delay + repair ≠ ETA (3 min) — PDF §8 report/clarify, §11.2 repair

1. `I will be late on SHP-D16-RAVI.`
2. Expect a question for **arrival time**, not a silent write.
3. `Repair will take 90 minutes.`
4. Expect **repair is not an ETA**; still asks for a timestamp **with timezone**.
5. `My new ETA for SHP-D16-RAVI is 2026-08-16T18:45:00+05:30 due to traffic.`
6. Yellow **Confirm exact ETA** banner appears — no DB write yet.
7. Click **Confirm & write ETA**.
8. Rail ETA should refresh.

**Pass:** preview then confirm. **Fail:** wrote from “90 minutes” or invented a time.

---

## 3. Options not reserved + pending ≠ confirmed (3 min) — PDF §8 options/choose/status

1. `Show feasible slots after 6 PM.`
2. Copy one real `slot_id` from the reply (e.g. `D16-SLT-…`). Never invent `SLT-1930`.
3. Expect language: **not reserved** / displayed options.
4. `Request slot <PASTE_SLOT_ID> for SHP-D16-RAVI.`
5. Expect `PENDING_CONFIRMATION`, not “confirmed”.
6. `Has the warehouse confirmed my new slot?`
7. Expect **pending ≠ warehouse confirmed**.

**Pass:** options informational; request pending.  
**Fail:** “your slot is booked/confirmed” or a made-up slot_id.

---

## 4. Same-slot race (3 min) — PDF §12.2 two requests, §11.2 two drivers

If Phase 3 already took `D16-SLT-RACE`, cancel that pending first, or race a **different** evening `slot_id` both can see.

1. Profile A still Ravi: `I need help with shipment SHP-D16-RACE-A.`
2. Profile B → `/driver/login` as `amit.singh@setuhaul.com`.
3. Amit: `I need help with shipment SHP-D16-RACE-B.`
4. Both: `Show feasible slots after 6 PM.`
5. **Together:**  
   Ravi: `Request slot D16-SLT-RACE for SHP-D16-RACE-A.`  
   Amit: `Request slot D16-SLT-RACE for SHP-D16-RACE-B.`
6. One winner pending; one conflict/refresh. **Not two winners.**

**Pass:** one active claim. **Fail:** both pending/confirmed on the same slot.

---

## 5. Vikas NOSLOT + two shipments (2 min) — PDF §8 fallback, §11.2 no slot + disambiguation

1. Profile A (or new window) logout → `vikas.sharma@setuhaul.com`.
2. `What are my active shipments?`
3. Expect `SHP-D16-NOSLOT` and `SHP-D16-MULTI-B`.
4. `Find feasible slots for SHP-D16-NOSLOT.`
5. Expect **zero options**, escalation language, **no invented slot**.
6. Optional: `Find slots for SHP-D16-MULTI-B.` — different result.

**Pass:** NOSLOT never fabricates capacity.

---

## 6. Ops human takeover (2 min) — PDF §12.1 Q12

1. Profile C → `/ops/login` as `priya.mehta@setuhaul.com`.
2. Dashboard loads (facility-scoped KPIs, exceptions).
3. **Escalation queue** shows the NOSLOT (or OPEN) row.
4. Click **Inspect & Take Decision** → add a note → resolve.
5. Click **Refresh** — freshness timestamp moves.

Warehouse **confirm** of a pending appointment is **not** a big Ops button. Chat already proved pending ≠ confirmed. If a judge wants confirm/reject: FastAPI `/docs` with an Ops token (`POST .../confirm` or `.../reject`).

**Pass:** Ops sees escalation and can decide. **Fail:** empty queue after Vikas NOSLOT, or calling a conflict “confirmed”.

---

## 7. Optional if time

| Test | Where | What to do |
|---|---|---|
| Cancel frees slot | Ravi chat | After a pending request: `Cancel my pending appointment request for SHP-D16-RAVI because plans changed.` Then search slots again. |
| Stale options | Ravi | Get options → change ETA (step 2 with a **different** evening time) → old `slot_id` must not silently book. |
| Dispatch | `/dispatch` | Create a shipment; auto-book uses a fresh `recommendation_id`. |
| Extra reads | Ravi | `What is my vehicle registration?` / `What are the safety rules at FAC-JAI-01?` |
| Admin RO | `/ops/login` `ananya.rao@setuhaul.com` | Wider/global numbers, still read-only. |
| 10×4 scarce | Do **not** click 10 UIs | Already proved by live pytest. Optional Locust Suite B after reset. |

---

## Do not spend UI time on

- GPS / maps / OR-Tools facility-wide engine (PDF §7.3 **optional**, we deferred)
- Mid-chat dock close (stress item; revalidation still blocks stale claims)
- Warehouse messaging channel
- Duplicate-message UI (the UI mints a new `client_message_id` each send; proof is API/idempotency)
- Tools-catalog PDF example IDs (`SHP1002`, `SHP-D16-RACE-B`, `SLT-1930`) — those 403 or fail for Ravi
