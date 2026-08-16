# SetuHaul presentation checklist — 17 Aug 2026

Presentation day: **Monday 2026-08-17** (`Asia/Kolkata`).  
Demo data remains a **frozen 16 Aug scenario** (`SHP-D16-*`, ETAs `2026-08-16T…+05:30`). Feasibility compares slots to the shipment ETA, not wall-clock “now”, so 16 Aug slots still work on 17 Aug. Keep using the **16 Aug** timestamps in chat. Do not invent 17 Aug ETAs unless the live SQL is regenerated.

Judge sheet: [DEMO_DAY_READINESS.md](DEMO_DAY_READINESS.md).  
Ordered live script: [DEMO_MANUAL_RUNBOOK.md](DEMO_MANUAL_RUNBOOK.md).  
Ravi prompt list: [DEMO_DRIVER_CHAT_SCRIPT.md](DEMO_DRIVER_CHAT_SCRIPT.md).  
Passwords: gitignored `POC_TEAM_ACCOUNTS.local.md` only.

---

## 0. What to say in one minute

SetuHaul turns a messy driver delay into a **feasible, current dock plan** without double-booking another driver.

- Drivers talk in chat. Operations watch a dashboard. Dispatch can auto-book a first slot.
- The LLM **orchestrates typed tools**. It never runs SQL and never invents a slot.
- PostgreSQL is the source of truth. Unique indexes are the last line of defence.
- Ranked options are **displayed, not reserved**. A claim is revalidated in one transaction as `PENDING_CONFIRMATION`. Warehouse confirm is Ops, not the driver.

Success line (PDF §13.1): exception → current plan, **zero conflict for another driver**.

---

## 1. Night before (16 Aug)

- [ ] Confirm hosted SPA: https://setuhaul-roan.vercel.app/driver/login
- [ ] Confirm BFF: `https://se-e5cad5d30b1a4f22b9aeea032827f81b.ecs.us-east-1.on.aws/health/live` → 200
- [ ] Confirm local fallback: `uvicorn` `:8000` + Vite `:5173` still start (ARN blank = in-process chat)
- [ ] Open `POC_TEAM_ACCOUNTS.local.md` on the demo laptop (never project / paste passwords)
- [ ] Cast reset dry-run: `python supabase/demo/reset_demo_day.py --mode cast --include-shp1017 --dry-run`
- [ ] Print or keep this file + runbook Phases A–F on a second screen
- [ ] Create **three browser profiles**: A Ravi, B Amit, C Priya
- [ ] Bookmark `/driver/login`, `/ops/login`, `/dispatch`, API `/docs`
- [ ] Laptop DNS: if `*.on.aws` NXDOMAIN, use 8.8.8.8 or the Vercel SPA (it already points at the BFF)
- [ ] Decide live path: **hosted (AgentCore)** vs **local** if AWS/Vercel wobbles
- [ ] Know the honest “do not claim” list (section 6)

---

## 2. Morning of (17 Aug, before the room)

- [ ] `GET /health/live` 200 on the BFF you will actually use
- [ ] Cast reset for real:

```powershell
python supabase/demo/reset_demo_day.py --mode cast --include-shp1017 --confirm
```

- [ ] Ravi password-grant + `/api/v1/auth/me` → `USR001` / `DRIVER` / `DRV001`
- [ ] Open Ravi chat, send `Show my current shipments.` — expect **three** actives: `SHP-D16-RACE-A`, `SHP-D16-RAVI`, `SHP1017`. Rail appointment is empty until you name a shipment. Next line: `I need help with shipment SHP-D16-RAVI.`
- [ ] Confirm Ops login as Priya loads dashboard + escalation list
- [ ] Confirm a second browser can open Amit without sharing Ravi’s session
- [ ] If hosted chat 503s: fall back to local Vite + uvicorn (leave `AGENTCORE_RUNTIME_ARN` blank)

---

## 3. Live demo order (target ~12–15 min)

Use **exact** runbook lines. Prefer `SHP-D16-RAVI` over older `SHP1017`.

| Min | Beat | Who | Prove |
|---|---|---|---|
| 0–1 | Login + profile rail | Ravi `/driver/login` | JWT role. **3 active shipments**, no rail appointment (primary is `SHP-D16-RACE-A`). Immediately lock `SHP-D16-RAVI`. |
| 1–3 | Delay + repair ≠ ETA | Phase A | Clarifies; **Confirm & write ETA** only after `2026-08-16T18:45:00+05:30` |
| 3–5 | Options not reserved | Phase B | `find_feasible_slots` → ranked, **not reserved**, `REC-…` |
| 5–6 | Request ≠ confirmed | Phase B | `request_slot` → `PENDING_CONFIRMATION`; “Has warehouse confirmed?” → pending |
| 6–8 | Same-slot race | Phase C, two browsers | Ravi `SHP-D16-RACE-A` vs Amit `SHP-D16-RACE-B` on `D16-SLT-RACE` — **one winner** |
| 8–10 | No slot invented | Phase D, Vikas | `SHP-D16-NOSLOT` → zero options + escalation |
| 10–12 | Human takeover | Phase F, Priya `/ops` | Escalation queue + Inspect & Take Decision |
| Optional | Cancel frees slot | Phase E | Cancel pending → search again |
| Optional | Dispatch | `/dispatch` | New shipment auto-book with fresh `recommendation_id` |
| Optional | Extra tools | Ravi chat | Vehicle/carrier, gate/queue, facility rules, dock alerts |

If time is short: **A → B → C → D → F**. Skip G (10×4 already proved by live pytest).

---

## 4. Accounts (emails only)

| Who | Email | Portal | Use |
|---|---|---|---|
| Ravi | `ravi.kumar@setuhaul.com` | `/driver/login` | Hero path `SHP-D16-RAVI`, race A |
| Amit | `amit.singh@setuhaul.com` | `/driver/login` | Race B |
| Vikas | `vikas.sharma@setuhaul.com` | `/driver/login` | NOSLOT + multi-shipment |
| Priya | `priya.mehta@setuhaul.com` | `/ops/login` | Jaipur ops + escalations |
| Ananya | `ananya.rao@setuhaul.com` | `/ops/login` | Admin global read-only (optional) |

Cast IDs: `SHP-D16-RAVI`, `SHP-D16-RACE-A/B`, `D16-SLT-RACE`, `SHP-D16-NOSLOT`, `SHP-D16-MULTI-B`.

---

## 5. Architecture talking points (if asked)

1. **Two portals, one identity.** `/driver` vs `/ops`; FastAPI verifies the JWT and maps `auth_user_id` → `users` / role / driver / facility.
2. **`bind_tools` + manual loop, not `create_agent`.** `run_assistant` invokes the model, runs Pydantic tools against services, appends `ToolMessage`s, then answers.
3. **Postgres decides booking.** `request_slot` row-locks, revalidates, writes `PENDING_CONFIRMATION`; unique partial indexes reject a second active claim.
4. **Redis is memory, not truth.** 24h Upstash history + rolling summaries. Operational facts always re-read from PostgreSQL.
5. **Hosted path (Sprint 4, gate still open):** Vercel SPA → ECS Express BFF → Bedrock AgentCore Runtime. SPA never holds the Runtime ARN.

---

## 6. Do not claim

- Displayed options are reserved or “your slot is confirmed” after `request_slot`
- Facility-wide OR-Tools / national optimisation / live GPS / maps
- Locust Suite B (not run). Suite A had 1× Amit C2 **503** — hosting not fully clean
- Sprint 4 exit gate complete
- Password rotation / session revocation
- Warehouse messaging channel
- `scheduling_capability_disabled` as a product feature (leftover stub; driver still cannot confirm)

---

## 7. Recovery if something breaks

| Symptom | Do this |
|---|---|
| Hosted chat 503 / AgentCore | Local Vite + uvicorn, ARN blank |
| Ravi `invalid_credentials` | Use Driver bucket from `POC_TEAM_ACCOUNTS.local.md`; do not rotate all passwords mid-demo |
| `ACTIVE_APPOINTMENT_EXISTS` on Phase B | Re-run cast reset (`D16-APT-RAVI-OLD` must be historical CANCELLED) |
| Race slot already taken | Cancel that pending first, or race a different open evening `slot_id` both can see |
| Assistant invents a slot_id | Stop; copy an exact id from `find_feasible_slots` only |
| `*.on.aws` NXDOMAIN on laptop | Use Vercel SPA or public DNS 8.8.8.8 |

---

## 8. Slide outline (if you have slides)

1. Problem: phone/email exceptions vs scarce docks  
2. Users: Driver chat, Ops dashboard, Dispatch  
3. Split of responsibility: LLM vs deterministic services vs Postgres  
4. Live: delay → options → pending → race → NOSLOT → ops  
5. Proof: unique indexes + live 10×4 (4 winners / 6 conflicts / zero double-books)  
6. Honest remaining: OR-Tools optional, Locust Suite B, Express Mode cost after demo  
