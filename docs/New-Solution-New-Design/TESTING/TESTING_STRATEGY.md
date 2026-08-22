# SetuHaul — testing strategy

> Companion to `TECH-STACK/TECH_STACK.md`, which names the test *frameworks*; this specifies the
> *strategy*. Part of the candidate-redesign workspace (`docs/New-Solution-New-Design/`).
>
> **Nothing here is invented.** `SOLUTION_DESIGN.md` §9.2 already names 19 stress fixtures and 4
> concurrency races with asserted outcomes; the six UI-UX surface `edge-cases.md` files already name 7
> interface-level races. This document maps what exists to tooling — and connects two halves of the same
> problem that had never been connected.

---

## Decisions at a glance

| Concern | Tool | Why |
|---|---|---|
| **Load / throughput** | **Locust** | Owner-mandated; Python-first, stateful VUs, demo-friendly web UI |
| **Backend concurrency** | **Locust** | Proves the *invariant* — exactly one winner, zero 5xx |
| **UI concurrency** | **Playwright multi-context** | Proves the *loser is told correctly* — Locust cannot see a screen |
| **E2E flows** | Playwright | Already in the stack |
| **Unit / integration** | pytest | §9.2's 19 named fixtures |
| **Determinism** | pytest | Byte-identical ranking on replay |

---

## 1 · Test pyramid for this product

| Layer | Scope | Tool |
|---|---|---|
| **Unit** | The deterministic engine — Stage 1 constraints, Stage 2 scoring, Stage 4 sequencer. No LLM, no network. | pytest |
| **Integration** | §9.2's 19 named stress fixtures, each replayed against seeded data with an asserted outcome | pytest |
| **Concurrency** | Two layers — see §2. This is the layer most products skip and this one cannot. | Locust + Playwright |
| **Load** | §7.3's spike and §11.1's volume, against the SLO | Locust |
| **E2E** | Per-surface happy paths and the negative paths the UI-UX docs specify | Playwright |

**Why concurrency gets its own layer rather than folding into integration**: M6 — *"capacity can never be
double-promised"* — is the product's headline correctness claim, and it is only observable under genuine
simultaneity. A sequential test cannot fail it.

---

## 2 · The two-layer concurrency model

**Several races in this product are the same race seen from two sides.** `SOLUTION_DESIGN.md` §9.2 defines
*the invariant that must hold*. The surface `edge-cases.md` files define *what the loser is shown*. These
are different assertions requiring different tools, and **neither substitutes for the other**.

| | Proves | Tool | Example |
|---|---|---|---|
| **Backend race** | The invariant holds | Locust | 50 simultaneous requests → exactly 1 `HELD`, 49 `SLOT_CONFLICT`, **zero 5xx** |
| **UI race** | The loser is told correctly | Playwright multi-context | `ALREADY_ACTIONED` **with the winning transition named** — not a bare error, not a silent refresh |

A passing Locust run tells you capacity wasn't double-promised. It tells you nothing about whether the
losing planner saw a useful explanation or a spinner that never resolved. That gap is why the UI layer
needs its own concurrency testing.

### Why Playwright answers "is there an application for this"

Each `browser.newContext()` is a **fully isolated user** — its own cookies, localStorage, sessionStorage,
IndexedDB, cache and service workers, behaving as separate incognito windows that cannot see each other's
auth or state. Two contexts in one test **are** two planners. This is standard Playwright, not a plugin:
the technique is already available given Playwright is in the stack (`TECH_STACK.md` §1).

> ⚠️ **Pitfall to avoid, documented because it silently invalidates results**: sharing `storageState`
> across roles causes the files to overwrite each other, creating a race **inside the test suite itself**.
> Use distinct storage paths per role. A concurrency suite with its own race condition proves nothing.

---

## 3 · Locust — backend concurrency and load

### 3a · The four named races (§9.2)

| Suite | Setup | Must produce |
|---|---|---|
| `same_interval_race` | 50 simultaneous requests on one interval | Exactly **1** `HELD` · **49** `SLOT_CONFLICT_REFRESH_REQUIRED` · **zero 5xx** |
| `hold_expiry_vs_confirm` | 90-second hold lapses in the same millisecond as confirm | Exactly one outcome. **Never both** a lapse notice and a pending appointment |
| `pending_expiry_vs_planner_confirm` | D9 sweeper fires as the planner clicks Confirm | Exactly one wins. **The audit log must show which and why** — §9.2 calls this *"the nastiest race in the design, because both actors believe they acted"* |
| `ordinal_staleness` | Driver replies against a `recommendation_id` that has since been re-ranked | Rejected and re-presented. **Never applied to the new list** |

**Zero 5xx is an assertion, not a hope.** A race that resolves correctly but throws 500s at 49 drivers has
failed — the refusal must be a typed, explainable outcome, not a crash.

### 3b · Load profiles (from the spec's own numbers)

| Profile | Shape | Source |
|---|---|---|
| **Disruption spike** | 20–35 exception requests inside 30 minutes, 5 coordinators — ~1 decision per 5 min per coordinator, each under a 15-min D9 deadline | §7.3 |
| **Steady state** | 190–240 appointments/day, 6 facilities, 24–32 docks | §1.1 |
| **Volume** | 600–1,000 shipments across 7 days | §11.1 |

### 3c · SLO under load

**TTFT p95 < 1.2 s · single-hop turn p95 < 2.5 s · `find_feasible_slots` < 50 ms** (`TECH_STACK.md`).

The spike profile is the binding one: §7.3's whole design rests on a planner decision taking under 30
seconds, and that budget assumes the queue is responsive while 35 requests are in flight.

### 3d · Why Locust, stated rather than assumed

Owner-mandated, and a good fit on the merits: Python-first (matches the backend), models virtual users as
coroutines so multi-step stateful driver journeys are natural to express, and its web UI makes spike
behaviour demonstrable to stakeholders. **k6** generates more load per instance (~5,000 VUs vs ~2,000 on
comparable hardware) — recorded as the alternative if volume ever outgrows Locust, not as a reason to
switch at this scale.

---

## 4 · Playwright multi-context — UI concurrency

Seven races, each traceable to the surface `edge-cases.md` entry that specifies it. **The test and the
spec must stay pointing at each other** — if one changes, the other is wrong.

| # | Surface | Race | The loser must see |
|---|---|---|---|
| 1 | `01-driver-chat` #2 | Hold expires as the driver taps confirm | Exactly one outcome — never both a lapse notice and a booking *(backend half: §9.2 #2)* |
| 2 | `01-driver-chat` #3 | Lost the slot to another driver | `SLOT_CONFLICT` copy from `voice-and-tone.md` · **no haptic penalty pattern** — losing a race is not the driver's error *(backend half: §9.2 #1)* |
| 3 | `02-ops-exception-console` #2 | Two coordinators acknowledge the same escalation | `ALREADY_ACTIONED` naming the **winning owner** · `assertive` announcement if focused on that row · row updates **in place**, never removed and re-inserted |
| 4 | `02-ops-exception-console` #9 | Shipment confirmed by another planner mid-triage | New fact surfaced inline · escalation does **not** auto-resolve · coordinator still chooses Resolve or Cancel deliberately |
| 5 | `03-planner-dock-board` #1 | Confirm vs the D9 sweeper | `ALREADY_ACTIONED` **with the winning transition named** · row updates in place so the planner keeps their place in a 35-row spike *(backend half: §9.2 #3)* |
| 6 | `04-gate-yard-kiosk` #5 | Gate booth and yard tablet act on the same truck | `INVALID_TRANSITION` → re-fetch and re-render the **now-correct** one valid action — never a blind retry of the rejected one |
| 7 | `06-admin-console` #3 | Two admins publish policy weights concurrently | **Named conflict, not a silent overwrite** · loser's simulation marked stale · must re-simulate against the new baseline before publishing |

### What makes these tests non-trivial

Three of the seven assert something about **where focus and position go**, not just what text appears —
row updates in place, planner keeps their place, `assertive` announcement only when focused. Those are
`accessibility-behaviour.md`'s focus-management contract under race conditions, and they are exactly the
behaviours that break first when a developer "fixes" a race by refetching the whole list.

---

## 5 · The cross-layer test — two drivers, one slot

The product's signature failure path, and the only race worth testing through both layers in a single
test.

**Setup**: two Playwright contexts, each an authenticated driver PWA, both holding the same option set.
Both tap the same slot within milliseconds.

**Assert, backend**: exactly one `HELD` (M6's invariant, DB-enforced by D1's exclusion constraint).
**Assert, UI**: the winner sees the `HELD` state with its 90-second countdown; the loser sees the
`SLOT_CONFLICT` treatment — correct copy, no haptic penalty, and a fresh option set offered rather than a
dead end.

**Why this one earns end-to-end treatment**: it is simultaneously M6 (the headline correctness claim) and
the driver-facing moment where a broken promise would be most visible. Testing only the API proves
capacity is safe while leaving the driver's actual experience of losing a race unverified.

---

## 6 · Determinism assertion (§9.2)

> Same snapshot + same `policy_version` → **byte-identical** ranking and **byte-identical** sequencer
> proposal, run twice.

Run as a standard pytest case, not a concurrency test. **Any drift means randomness leaked into an engine
that promised none** — which would invalidate every decision receipt the product renders, since §7.2b's
whole contract is that the assistant narrates a deterministic result rather than reasoning about it.

---

## 7 · What gets measured under load

| Metric | Why |
|---|---|
| **TTFT p50 / p95** | What a driver at a roadside actually experiences |
| **Hop-count distribution per turn** | Latency lever #1. Appendix A: a rise in average hops *"will show up as a latency regression that no amount of infrastructure tuning will fix"* |
| Per-tool DB latency | Isolates a slow tool from a slow model |
| LLM latency, split network vs inference | Distinguishes a routing problem from a model problem |
| Prompt-cache hit rate | Zero across repeated turns means something volatile leaked into the cached prefix |
| Redis RTT | Confirms the native-protocol decision is actually paying off |

---

## 8 · Constitution Check

| `AGENTS.md` rule | Check |
|---|---|
| Material behaviour changes require proportional tests | ✅ This document is that proportionality, made explicit |
| Do not mark tests as passing unless they were run | ✅ Every suite here is **specified, not claimed** — none has been executed |
| Database changes require relevant database tests | ✅ §3a's races are precisely the D1 exclusion-constraint tests |
| Never invent operational data | ✅ Every fixture traces to a seeded case in §9.2; no test data invented here |

**No conflicts found.**

---

## 9 · Open items — verify, don't assume

| # | Item | Why it matters |
|---|---|---|
| 1 | **Nothing in this document has been run.** | It is a specification. No suite here has an execution record, and none should be reported as passing until it does |
| 2 | **Achieving true simultaneity in Locust** for `same_interval_race` | Ramping 50 VUs is not the same as 50 requests landing together; the suite needs an explicit barrier/sync mechanism or it tests something weaker than it claims |
| 3 | **Forcing the sweeper-vs-confirm race deterministically** (§9.2 #3) | The nastiest race is also the hardest to reproduce on demand — likely needs an injectable clock (which §9.1 already requires for other reasons) rather than timing luck |
| 4 | **Playwright against a PWA with a service worker** | Service-worker caching can mask or distort a race; confirm context isolation behaves as expected with the driver surface's offline layer (U68) |
| 5 | **Where load tests run** | Against local, or the hosted `ap-south-1` deployment? Only the latter validates the SLO, since the SLO is regional — but it spends real quota |
