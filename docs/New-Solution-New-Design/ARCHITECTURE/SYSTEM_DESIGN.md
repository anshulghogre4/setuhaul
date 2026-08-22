# SetuHaul — system design

> Production architecture: service topology, module boundaries, transaction design, resilience, scaling,
> and regression handling. Companion to `TECH-STACK/TECH_STACK.md` (what we build *with*) and
> `REQUIREMENTS.md` (what it must *do*).
>
> **The headline decision contradicts the common default.** This system should **not** be built as
> microservices, and its frontend should **not** be micro-frontends. The reasoning is in §2 and §7, with
> sourced evidence rather than assertion — because a reviewer will push on exactly that.

---

## Decisions at a glance

| Concern | Decision |
|---|---|
| **Service topology** | **Modular monolith** — one codebase, 12 enforced module boundaries, one database; deployed to **two targets** (ECS Fargate for REST, AgentCore for driver chat) because AgentCore mounts only `/invocations` |
| **Frontend topology** | **Single React SPA**, route-based code splitting per surface, one shared design system |
| **Transaction boundary** | Capacity operations share **one transaction** — non-negotiable, this is M6 |
| **Extraction seam** | **Facility Sequencer** only — the one module that could later become a service |
| **Resilience** | Circuit breaker + bulkhead + timeout + retry-with-jitter on **external** dependencies |
| **Hard rule** | **Never circuit-break Postgres.** Correctness must fail loudly, not degrade |
| **Scaling** | Vertical first. Read replicas for carrier-portal reads. No horizontal split before evidence |

---

## 1 · What this system actually is

Architecture decisions are only defensible against real numbers, so they lead:

| Dimension | Reality | Source |
|---|---|---|
| Appointments/day | 190–240 across 6 facilities | §1.1 |
| Peak load | **20–35 exception requests in 30 minutes** | §7.3 |
| Concurrent operators | **5 coordinators** | §7.3 |
| Docks | 24–32 | §1.1 |
| Volume | 600–1,000 shipments across 7 days | §11.1 |
| Team | One small team | — |

**This is a low-volume, high-correctness system.** The hard part is never throughput — it is that
**capacity must never be double-promised** while several actors race for the same interval. That single
fact determines the topology.

---

## 2 · Topology — modular monolith, and why not microservices

### The decisive constraint

**M6**: *"Capacity can never be double-promised — DB-enforced (D1 exclusion constraint); 50-way race
yields exactly 1 winner."*

That is a **strictly consistent invariant**, enforced by a PostgreSQL GiST `EXCLUDE` constraint inside a
single transaction:

```sql
EXCLUDE USING gist (dock_id WITH =, window WITH &&)
  WHERE (state IN ('HELD','PENDING_CONFIRMATION','CONFIRMED','IN_PROGRESS'))
```

**Split Planner / Ops / Driver into services with separate databases and this constraint becomes
unrepresentable.** The standard fallback is the saga pattern — and current guidance is blunt about its
limits:

> *"Sagas accept eventual consistency. If your business requirement is true atomicity (all-or-nothing,
> visible to no one until complete), sagas cannot give you that… In those cases, design around
> **co-location (same database, same service)** rather than forcing sagas."*

A saga permits a double-booking to occur and then be **compensated**. That is precisely the broken promise
this product exists to prevent. **Microservices would trade away the product's headline correctness claim
to solve a scaling problem it does not have.**

### The supporting evidence

| Evidence | Implication here |
|---|---|
| ~**42%** of organisations that adopted microservices have **consolidated services back** — citing debugging complexity, operational overhead, network latency (CNCF 2025) | The default has already been re-litigated industry-wide |
| Teams spend ~**35% more time debugging** in microservices vs modular monoliths (DZone 2024) | Costly for a small team |
| Microservices "start paying for themselves once a team grows past roughly **30 engineers**" | Not this team |
| *"For domains with strong invariants or where ACID compliance is critical, a monolithic or modular monolithic architecture… remains the pragmatic choice"* (2026 consensus) | Describes this system exactly |
| Appendix A's **latency lever #1 is "remove a tool hop"** | Every service boundary **adds** a hop — microservices fight the SLO |

### The honest counter-case

Microservices would be right here if: independent teams needed to deploy on independent cadences · one
module had radically different scaling characteristics · the codebase outgrew what one team can reason
about. **None currently holds.** §5 names what would have to change.

---

## 3 · The 12 modules as enforced boundaries

§6's module map **is** the modulith's internal architecture — not a future microservice roadmap:

| # | Module | Owns |
|---|---|---|
| 1 | Driver Conversation | threads, intent, clarification, option presentation |
| 2 | Exception Intake | `driver_exceptions` — typed, deduped, severity |
| 3 | ETA Service | append-only `eta_updates`, effective ETA + confidence |
| 4 | Feasibility & Ranking | the 3-stage engine (§5) |
| 5 | Allocation & Promise Lifecycle | holds, requests, confirmations, cancellations |
| 6 | Facility Sequencer | facility-wide re-sequencing |
| 7 | Gate & Yard | check-in events, queue state, unload overrun |
| 8 | Capacity & Rules Admin | dock status events, `facility_rules`, policy weights |
| 9 | Escalation & Human Takeover | queue, SLA timers, ownership |
| 10 | Notification / Outbox | web push, email, delivery status |
| 11 | Observability & Audit | traces, decision receipts, KPI marts |
| 12 | Identity & RBAC | users, roles, scope |

### How boundaries are *enforced*, not merely documented

A modulith degrades into a big ball of mud when boundaries are conventions. Three mechanical rules:

| Rule | Enforcement |
|---|---|
| **Layering**: routers thin → services hold rules → repositories hold persistence | `AGENTS.md` already mandates this; enforce with import-linting in CI |
| **No cross-module table access** — a module never queries another module's tables directly; it calls that module's service interface | Table-ownership map + CI check on repository imports |
| **One module, one public interface** — internals are private | Package structure; lint rule forbidding deep imports |

**Why this matters beyond tidiness**: these are the same boundaries a future extraction would follow
(§5). A modulith with enforced seams can become services later; one without them cannot.

### Search is not a thirteenth module

`SOLUTION_DESIGN.md` §7.5.8 adds `search_records`, which reads across shipments (Module 2), appointments
(Module 5), drivers/carriers (Module 12), and facilities (Module 8). That looks, on first read, like
exactly the cross-module reach this section's "no cross-module table access" rule exists to stop.

**It doesn't violate the rule, because it never touches a table directly.** It calls each contributing
module's own existing read method — the same "routers stay thin, services hold the calls" layering already
enforced everywhere else — and composes the results at the API layer. Nothing new is owned; no new table
exists; there is nothing here that would need its own module boundary, because a boundary exists to protect
*data ownership*, and this capability owns none. Adding a thirteenth module for a capability that owns
nothing would be a boundary drawn around an empty room.

**The general rule this generalises to**: a read that spans modules is a composition question, answered at
the API layer by calling existing service interfaces. A read *or write* that needs its own persistent state
is a module question. `search_records` is the former; nothing currently proposed for this product is the
latter.

### One codebase, two deployment targets, three entry paths — not a contradiction

Two facts make the modulith look inconsistent on a first reading. Both are entry-protocol details, not
service boundaries.

**Fact one: AgentCore cannot host REST.** Verified against AWS's service-contract docs, AgentCore Runtime
mounts exactly `/invocations` (POST), `/ws` (optional), and `/ping` (GET) — on port 8080, **ARM64 only**.
There is no way to serve planner, ops, gate, carrier, or admin routes from it. So the same codebase deploys
twice:

| Target | Serves | Protocol |
|---|---|---|
| **AgentCore Runtime**, `ap-south-1` | Driver chat only | `/invocations`, SSE |
| **ECS Fargate**, `ap-south-1` | The five non-chat surfaces + BFF | Ordinary REST |

**Fact two: `TECH_STACK.md` §5 adds an EventBridge-triggered sweeper** — a third way in.

| | Path | Trigger |
|---|---|---|
| **Request path** | The same FastAPI application | HTTP from a surface (ECS) |
| **Chat path** | **The same FastAPI application** | AgentCore `/invocations` |
| **Scheduled path** | **The same FastAPI application** | EventBridge Scheduler → internal authenticated endpoint |

**One codebase, one database, one build artifact, one release.** Neither fact introduces a network call
between components, an independent release cycle, or a split schema — the three things that would actually
make this microservices. EventBridge is a *trigger*, not a service: it holds no state, owns no tables, and
ships in no separate build.

**The test that matters is M6.** A distributed design would have to coordinate `dock_occupancy` writes
across services and settle for eventual consistency. Here both targets open connections to the *same*
PostgreSQL instance and the *same* GiST exclusion constraint arbitrates every race (§4). **There is no
distributed transaction anywhere in this design** — which is precisely why the deployment split is safe.

The sweeper is therefore **not** an extraction candidate under §5; it is a scheduled entry point into
modules 5 (Allocation) and 10 (Outbox), and it must stay in-process precisely *because* its expiry
transition has to share a transaction with `confirm_request` (§4).

**Practical consequence**: ARM64 is not optional. AgentCore requires it, so the ECS task architecture
matches it to keep a single build rather than two. And the `agentcore/codezip/app/` staging directory that
looks like cruft is structural — it exists *because* the same code deploys to two runtimes
(`DEPLOYMENT.md` §2.2).

---

## 4 · The transaction boundary — what cannot be split

Three operations **must** share a single transaction. Each is a named race in §9.2:

| Operation | Why it cannot split |
|---|---|
| **`dock_occupancy` writes** (hold, request, confirm) | The GiST constraint *is* the concurrency control. Two transactions, two databases, or an application-level lock all weaken M6 |
| **Sweeper vs. `confirm_request`** | §9.2's "nastiest race" — the sweeper's expiry transition and the planner's confirm must take the row under the same transaction so **exactly one commits**; the loser gets `ALREADY_ACTIONED` with the winner named |
| **`bulk_confirm`'s predicate re-check** | §7.3: the rules *select* the batch, a human *presses the button*, and the server **re-checks the five safe-batch predicates at press time**. A client-side-only check is "auto-confirmation wearing a button" |

**Everything else may be asynchronous** — notifications (transactional outbox), traces, sequencer
proposals, KPI aggregation. The rule: *if it consumes capacity, it is synchronous and transactional; if it
observes or notifies, it is not.*

---

## 5 · Designated extraction seam

Pretending a modulith is permanent is dishonest; so is leaving extraction undefined. **Exactly one module
is a genuine candidate today.**

### Facility Sequencer (module 6) — the one that could leave

| Property | Why it qualifies |
|---|---|
| **Compute-bound** | Rule-based greedy now; OR-Tools CP-SAT later (D3) — a genuinely different resource profile from request-serving |
| **Asynchronous by design** | D5: *it proposes, a planner applies*. Propose → review → apply is already a multi-step, non-blocking flow |
| **Does not consume capacity** | It emits a `scheduling_runs` proposal. `apply_schedule_proposal` — a *planner* action — is what touches `dock_occupancy`. **The sequencer never participates in the capacity transaction** |
| **Already has a clean contract** | §7.5.3's three tools are its complete public interface |

### What would have to be true before extracting anything else

- A module needs **independent scaling** with evidence, not anticipation.
- Two teams need **independent deploy cadence** and are blocking each other.
- **The module does not participate in the capacity transaction** (§4). Modules 4 and 5 fail this test
  permanently — they *are* the invariant.

---

## 6 · Resilience architecture

### 6.1 The governing rule

> **Circuit breakers belong on external and optional dependencies. Never on the correctness path.**

A breaker that "degrades" the capacity path would let the system keep answering while unable to guarantee
M6 — **a failure mode strictly worse than an outage**, because it produces confident wrong promises.
Postgres failure must surface as failure. Redis may degrade; it is explicitly non-authoritative
(24 h TTL, never the source of truth).

### 6.2 Per-dependency failure matrix

Classification follows `auth-and-scoping.md`'s existing primary/secondary model (U84) rather than
inventing a parallel scheme.

| Dependency | Class | Failure mode | Response | User-visible effect |
|---|---|---|---|---|
| **PostgreSQL** | **Correctness path** | Unavailable / timeout | **Fail loudly.** No breaker, no fallback, no cache-serve | Honest error + retry; *"Nothing has changed"* (`components.md` §13) |
| **LLM provider** | Primary (conversation) | 429, 5xx, timeout, slow | Retry w/ backoff+jitter → **circuit breaker** → fallback provider | Degraded latency, then provider switch; conversation continues |
| **Redis** | Secondary | Unavailable | Serve from Postgres — *"freshness comes from the database, never from cache"* (§10 chaos-lite) | None; slower turn |
| **LangSmith** | Secondary | Unavailable / slow | Drop from bounded queue. **Never block a turn** | None |
| **Web push** | Secondary | Send failure | Outbox retry; in-app state remains truth | No push; state visible on next open |
| **SES email** | Secondary | Send failure | Outbox retry → `NOTIFICATION_FAILED` escalation (§7.4) | Ops sees an escalation — *"a confirmation nobody received is not a confirmation"* |
| **Ops co-pilot** | Secondary | Unavailable | Degrade per-action; console fully operable without it | Co-pilot actions unavailable; takeover unaffected |

### 6.3 Circuit breaker — LLM provider

Sized against measured reality: **~5% of LLM call spans error, and ~60% of those are rate limits**
(Feb 2026 traffic analysis). Rate limits are *transient and provider-specific* — exactly what a breaker
plus fallback handles well.

| State | Behaviour |
|---|---|
| **CLOSED** | Normal. Count failures in a rolling window |
| **OPEN** | Threshold breached → **fail fast to the fallback provider** (`TECH_STACK.md` §7's primary+fallback). No requests to the failing provider |
| **HALF-OPEN** | After a cooldown, allow limited probes. Success → CLOSED; failure → OPEN |

**Note the interaction**: switching providers invalidates prompt cache. A flapping breaker therefore costs
latency twice — once for the failover, once for the cold cache. Cooldown must be long enough that
recovery is real, not optimistic.

### 6.4 Bulkhead

**Cap concurrent in-flight LLM calls.** Without it, one slow provider consumes every worker, and *tool
execution starves* — meaning the deterministic engine (which is fast and healthy) stops being reachable
because the conversation layer exhausted the pool. Isolating the LLM call pool from the request pool keeps
a slow model from becoming a total outage.

### 6.5 Timeout budget — derived, not picked

Working backwards from the SLO rather than choosing a round number:

- Single-hop turn p95 **< 2.5 s** (`TECH_STACK.md`)
- A turn averages ~2.5 LLM calls (§ workload profile)
- Tool + DB work budgeted **< 50 ms** for feasibility, plus overhead

⇒ **Per-LLM-call timeout ceiling ≈ 800 ms–1 s** to keep p95 within budget, with the fallback path
accounting for the retry. A timeout longer than the SLO is not a timeout; it is a hang with extra steps.

### 6.6 Retry — safe only because idempotency already exists

Exponential backoff **with jitter** (unjittered retries synchronise and re-spike a recovering provider).

**This works only because the design already mandates idempotency keys** on every capacity-affecting
action (M9, U70). Retry-after-uncertain-failure is safe *because* a duplicate cannot double-act — and
`auth-and-scoping.md` already specifies the user-facing copy that says so: *"Try again — this won't
double-book you."* The resilience story and the correctness story are the same story.

---

## 7 · Frontend topology — single SPA, not micro-frontends

| Evidence | Implication |
|---|---|
| Documented case: initial load **1.8 s → 3.4 s**, **LCP regressed 40%** — four bundles resolving shared dependencies and mounting four React trees | Disqualifying against a TTFT p95 < 1.2 s target |
| *"Avoid micro-frontends when you have a small team (fewer than 3–4 frontend developers)"* | Not this team |
| Duplicate dependencies: *"four apps each shipping a 40 KB UI library… 280 KB of repeated JavaScript before product code"* | Directly attacks the driver PWA's low-end-Android constraint |
| *"Without a shared design system, five teams ship five slightly different buttons"* | The UI-UX phase spent **121 decisions** unifying exactly this — and **U23 has ops and planner sharing one queue component** |

**Decision**: one React SPA, **route-based code splitting per surface**. A gate officer downloads the gate
bundle, not the planner's Gantt. That delivers the only real benefit micro-frontends offered here — not
shipping unused code — without bundle duplication, runtime composition cost, or design-system drift.

---

## 8 · Scaling model

**Vertical first, and say so plainly.** At 240 appointments/day with 5 concurrent coordinators, horizontal
scaling would be complexity bought against a problem that does not exist.

| Load | Reality | Response |
|---|---|---|
| Exception spike | 20–35 requests / 30 min | Comfortably one instance |
| Concurrent operators | 5 | Trivial |
| Carrier portal reads | Read-only, cross-facility | **First real candidate for a read replica** — but only on evidence |
| Sequencer runs | One per facility, serialised (`RUN_ALREADY_ACTIVE`) | Already debounced by design |

**What actually breaks first, in order**: (1) the LLM provider's rate limit — mitigated by §6.3, not by
more instances; (2) DB connection exhaustion under a spike — mitigated by explicit pool sizing
(`TECH_STACK.md` §3), a failure this project has hit before; (3) nothing else at this scale.

**Anti-requirement, stated deliberately**: do **not** add horizontal scaling, sharding, or caching layers
before a measured bottleneck. Each would add a failure mode to a system whose value is that it does not
fail in a specific way.

---

## 9 · Failure, regression, and recovery

`TESTING_STRATEGY.md` covers **detection**. This section covers **recovery** — previously undocumented.

### 9.1 Regression gates (before a deploy ships)

| Gate | Source |
|---|---|
| §9.2's 19 named stress fixtures | `TESTING_STRATEGY.md` §1 |
| Four Locust concurrency races | §3a |
| Seven Playwright UI-race suites | §4 |
| **Determinism assertion** — byte-identical ranking on replay | §6 |
| **§10 invariant queries, run continuously in CI** — no overlapping `dock_occupancy` rows, no shipment with >1 active appointment, no confirmed appointment inside an outage window | `SOLUTION_DESIGN.md` §10 |

**The invariant queries are the regression tripwire that matters.** A code change that breaks M6 will not
necessarily fail a unit test — it will show up as an overlap the constraint should have prevented.

### 9.2 Recovery

| Concern | Approach |
|---|---|
| **Feature flags** | Ship risky changes dark. Especially: a new model provider, a policy-weight change, the sequencer |
| **Rollback** | Application: redeploy the prior artifact. **Database: forward-fix only** — a migration that adds the GiST constraint cannot be cleanly reversed once data depends on it |
| **Policy rollback** | Free — `policy_versions` is append-only and immutable (D7). Reverting is publishing the prior version, not mutating |
| **Blast-radius containment** | The four capacity-affecting actions are the risk surface; everything else is read or notify |

### 9.3 Disaster recovery — currently undefined

**RTO/RPO are not specified anywhere in the design.** For a system whose data is the business record of
committed capacity, this is a real gap, recorded rather than papered over. `GAP_ANALYSIS.md` Gap 5 carries
it; §9.3's step-1 backup (D16) is the only current recovery mechanism, and it is a migration safety net,
not a DR policy.

---

## 10 · Constitution Check

| `AGENTS.md` rule | Check |
|---|---|
| FastAPI routers thin; rules in services; persistence in repositories | ✅ §3 makes this the enforced module contract, not a convention |
| The LLM orchestrates typed tools, never executes SQL or mutates business tables | ✅ Reinforced — §4's transaction boundary is code-owned; §6.1 keeps the correctness path un-degradable |
| PostgreSQL is the business source of truth; Redis bounded/non-authoritative | ✅ §6.2 classifies them exactly this way |
| Scope derived server-side from verified tokens | ✅ Module 12 + `TECH_STACK.md` §4 |
| Material behaviour changes require proportional tests | ✅ §9.1 ties every gate to an existing suite |
| Do not broaden the build beyond the active slice | ✅ §8's explicit anti-requirement against premature scaling |

**No conflicts found.** One item worth naming: this document **declines** a topology (microservices) the
owner initially leaned toward. That is recorded as a reasoned recommendation with sourced evidence and an
explicit revisit-trigger list (§2, §5), not a silent override.

---

## 11 · Open items

| # | Item | Impact |
|---|---|---|
| 1 | **RTO/RPO undefined** (§9.3) | No stated recovery objective for the business record of committed capacity |
| 2 | **Rate limiting absent** — see `GAP_ANALYSIS.md` Gap 1/3 | Both an injection-defence hole and a cost-control hole |
| 3 | Import-linting for module boundaries (§3) not yet specified as a concrete CI check | Boundaries stay conventions until enforced |
| 4 | Circuit-breaker thresholds and cooldown not yet numeric | §6.3 gives the shape; tuning needs measured traffic |
| 5 | Bulkhead pool size not yet sized (§6.4) | **Unblocked 2026-08-21** — model chosen and measured: `gemini-3.7-flash` at ~1.5 s single-shot, ~7.4 s for a 4-hop turn (`TECH_STACK.md` §7). Size the pool against the **multi-hop** figure; sizing against the single-shot number would under-provision by ~5× |
| 6 | Read-replica trigger point undefined (§8) | Deliberate — "on evidence," but the evidence threshold isn't stated |
