# Demo-day readiness vs FDE Challenge PDF

Source: `docs/SetuHaul_FDE_Challenge.pdf` §8, §11.2, §12.1–12.2, §13.1.  
Reassessed **2026-08-12 00:25 IST** after Sprint 3 exit gate close (lifecycle + stale + escalation + 10×4 live load + D16 cast smoke).

Legend: **SHOW** / **ANSWER** / **PARTIAL** / **NOT YET**

Demo day anchor: **2026-08-16** (`Asia/Kolkata`). Data: `supabase/demo/`. Cast: `supabase/demo/fixtures/stress_scenarios.json`.

Live volume after apply: facilities **6**, docks **25**, drivers **105**, slots **2934**, shipments **661**, Auth-mapped users **26**.

---

## UI test cast (use same 3 shared passwords; no resets)

| Who | Login email | Portal | What to demo |
|---|---|---|---|
| Ravi | `ravi.kumar@setuhaul.com` | `/driver/login` | Single-driver path on **`SHP-D16-RAVI`**; also has older `SHP1017` → disambiguation |
| Amit | `amit.singh@setuhaul.com` | `/driver/login` | Race loser/winner vs Ravi on **`D16-SLT-RACE`** (`SHP-D16-RACE-B`) |
| Vikas | `vikas.sharma@setuhaul.com` | `/driver/login` | **`SHP-D16-NOSLOT`** escalation + **`SHP-D16-MULTI-B`** disambiguation |
| Contention | `driver.drv004@setuhaul.com` … `driver.drv013@setuhaul.com` | `/driver/login` | `SHP-D16-CONTEND-01..10` scarce evening (4 open STANDARD 18:00–20:00 incl. race slot) |
| Ops | `priya.mehta@setuhaul.com` / `arvind.nair@setuhaul.com` | `/ops/login` | Dashboard + confirm pending appointments |
| Admin | `ananya.rao@setuhaul.com` | `/ops/login` | Global RO |

Passwords: Driver / Ops / Admin buckets in gitignored `POC_TEAM_ACCOUNTS.local.md` only.

---

## Best live UI script (run in this order)

**Full step-by-step with chat lines + pass/fail:** [DEMO_MANUAL_RUNBOOK.md](DEMO_MANUAL_RUNBOOK.md).

1. **Ravi login** → profile shows `USR001` / `DRV001` / `FAC-JAI-01`.
2. Ask which shipment if needed → choose **`SHP-D16-RAVI`** (not SHP1017).
3. “Stuck near Neemrana, about 90 minutes late” → clarify; if you say “repair 90 min” expect **not** ETA.
4. Give explicit ETA on 16 Aug evening with timezone → confirm write.
5. “Show later slots after 6 PM” → ranked options, **not reserved**.
6. “Take slot …” with exact `slot_id` → `PENDING_CONFIRMATION` via `request_slot`.
7. “Has warehouse confirmed?” → pending ≠ confirmed (`get_appointment_request_status`).
8. **Two browsers:** Ravi on `SHP-D16-RACE-A` and Amit on `SHP-D16-RACE-B` both request **`D16-SLT-RACE`** → one winner, one conflict refresh.
9. **Vikas:** ask slots for **`SHP-D16-NOSLOT`** → zero options + escalation language (no invented slot).
10. **Ops login** → escalations list; confirm/reject pending (REST/ops path).
11. Cancel a pending request as driver → slot frees for another search.

API already verified: Ravi `SHP-D16-RAVI` feasible **200** with options; Vikas `SHP-D16-NOSLOT` **200** with `options=[]` + `escalation`; cross-driver IDOR **403**. Sprint 3 gate live cast smoke (2026-08-12): options→request→status→stale reject→cancel frees; NOSLOT escalation persisted; ops reject/confirm PASS. Automated 10-driver / 4-slot load PASS (4 winners / 6 conflicts / zero double-books).

---

## §12.2 Expected demonstration

| Beat | Status | How to show |
|---|---|---|
| Delay + clarification | **SHOW** | [DEMO_MANUAL_RUNBOOK.md](DEMO_MANUAL_RUNBOOK.md) Phase A |
| Later possibilities / compare | **SHOW** | `find_feasible_slots` + ranking factors |
| Several requests same facility | **SHOW** | Contended evening data + 10×4 live load proof (zero double-books) |
| Optional facility-wide engine | **NOT YET** | Deferred (rule-based facility snapshot first → optional OR-Tools later) |
| Two requests same capacity | **SHOW** | Race A/B + live integration test |
| Option disappears / changes | **SHOW** | `REC-` recommendation versioning + `SLOT_OPTIONS_STALE` + ETA Redis stale mark; live cast stale rejection PASS |
| No feasible → escalation | **SHOW** | Payload + durable `escalation_queue` row + Ops escalation list |

---

## §12.1 Questions (judge answers)

| # | Status | Proof |
|---|---|---|
| 1 Info before options | **ANSWER** | ETA + shipment + compatibility via tools |
| 2 Connect conversation | **SHOW** | JWT → users → driver_id scope |
| 3 Revised arrival / uncertainty | **SHOW** | Confirm ETA flow |
| 4 Feasibility | **SHOW** | `feasibility.py` + constraints.json |
| 5 Available while considering | **SHOW** | Displayed not reserved; claim in transaction |
| 6 Hold / request / confirmed | **SHOW** | Pending via request; confirm/reject/expire ops paths implemented |
| 7 Simultaneous scarce capacity | **SHOW** | Ranking + unique indexes + race cast + 10×4 load |
| 8 Facility-wide recalculation | **NOT YET** | Optional extension (deferred design note in master plan) |
| 9 Stale / cancel / duplicates | **SHOW** | Dedupe + cancel frees capacity + stale recommendation rejection |
| 10 No feasible slot | **SHOW** | NOSLOT shipment + escalation payload + durable queue |
| 11 Preferred not granted | **SHOW** | Conflict refresh |
| 12 Human takeover | **SHOW** | Escalation queue + Ops dashboard escalation list |
| 13 Prove no double-book | **SHOW** | Indexes + concurrency test + race cast + 10×4 load |

---

## §8 Chat examples

| Type | Status |
|---|---|
| Report / clarify / options / choose / status | **SHOW** |
| Compare / facility dock fit / leave-by constraint | **PARTIAL** |
| Change mind (cancel) | **SHOW** (cancel tool/route landed) |
| Fallback no slot | **SHOW** (NOSLOT) |

---

## §11.2 Stress scenarios

| Scenario | Status |
|---|---|
| 10 drivers / 3–4 STANDARD evening slots | **SHOW** — cast data + live pytest 10×4 load PASS (2026-08-12); manual sample in [DEMO_MANUAL_RUNBOOK.md](DEMO_MANUAL_RUNBOOK.md) Phase G |
| Early/late/unloading/future snapshot | **SHOW data** (`SHP-D16-EARLY/LATE/UNDOCK/FUTURE`) |
| Two drivers same option | **SHOW** |
| Capacity cut after options | **NOT YET** (dock-close mid-conversation path thin; revalidation still blocks stale claims) |
| Cancellation frees slot | **SHOW** — cancel tool + runbook Phase E |
| Duplicate messages | **SHOW** |
| Multi-shipment disambiguation | **SHOW** (Ravi SHP1017+RAVI; Vikas NOSLOT+MULTI-B) |
| Repair ≠ ETA | **SHOW** |
| Higher priority later | **PARTIAL** |
| No same-day feasible | **SHOW** (NOSLOT) |
| Warehouse reply conflict | **NOT YET** (escalate type exists; no full warehouse messaging channel) |

---

## After Sprint 3 gate (manual + polish)

Sprint 3 exit gate is **COMPLETE** (2026-08-12). PDF chat/cast demo-hardening is **COMPLETE** (2026-08-13 21:39 IST). Remaining is rehearsal and optional polish, not product blockers:

1. **Do this:** run [DEMO_MANUAL_RUNBOOK.md](DEMO_MANUAL_RUNBOOK.md) end-to-end after `reset_demo_day.py --mode cast` (live `--confirm` of the new historical-appointment reset not yet run).
2. Optional: ranking collect-then-sort; wipe runtime `EXC-*` on cast reset; drop leftover `scheduling_capability_disabled` tool.
3. Optional formal Playwright E2E of the cast script.
4. Intentional **NOT YET** (do not claim): OR-Tools / facility-wide engine, dock-close mid-conversation UI, warehouse reply channel, GPS/maps. Hosted Locust / AgentCore = Sprint 4.

## Do not claim

- Live GPS / maps / OR-Tools as done
- Displayed options are reserved
- National network optimisation
- Password rotation (intentionally not done; same 3 shared passwords)

Success (PDF §13.1): exception → feasible, current plan with **zero conflict for another driver**.
