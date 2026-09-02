# SetuHaul — tech stack

> Roadmap step 3 of 5: SOLUTION_DESIGN (done) → UI/UX (done, six surfaces) → **tech stack** → deployment →
> apply to existing project. Part of the candidate-redesign workspace (`docs/New-Solution-New-Design/`) —
> not yet applied to the live system.
>
> **Primary input**: `SOLUTION_DESIGN.md` **Appendix A** — D4 deferred the stack but preserved a full
> latency architecture there, marked provisional. Most of it survives verification. One finding *resolves*
> its largest open risk and reverses its topology recommendation; one *supersedes* its regional assumption.
> Both are called out in place.

---

## Decisions at a glance

| Layer | Decision | Status |
|---|---|---|
| **Agent runtime** | AWS AgentCore Runtime, `ap-south-1`, **ARM64** — driver chat only, via `/invocations` | Decided |
| **API** | FastAPI (Python 3.12+) on **ECS Fargate, `ap-south-1`** — the five non-chat surfaces | Decided |
| **Deployment shape** | **One codebase, two deployment targets, one region** — AgentCore cannot host REST | Decided |
| **Agent loop** | LangChain `bind_tools` + bounded manual loop — **no agent executor** | Decided |
| **Database** | Supabase PostgreSQL, `ap-south-1` | Decided |
| **Session/cache** | Upstash Redis, `ap-south-1`, **native protocol over persistent connection** | Decided |
| **Identity** | Supabase Auth (user) + AgentCore Identity (workload); scope from `user_scopes`, enforced in the repository | Decided |
| **Background jobs** | EventBridge scheduled rule → API destination → FastAPI internal endpoint (1-min) — expiry sweeper + outbox drain *(Correction 2026-09-02, #111: EventBridge **Scheduler** cannot target an HTTPS API destination -- its targets are templated AWS services + the AWS-SDK universal target only. The built shape is an EventBridge **scheduled rule** (default bus, `rate(1 minute)`) -> connection (API_KEY header) -> API destination -> the FastAPI route via CloudFront. Same 1-minute floor, same route; artifacts in `deploy/eventbridge-scheduler/`.)* | Decided |
| **Notifications** | Web push (VAPID) + SES email. **SMS dropped** — not free, DLT registration required | Decided |
| **Observability** | LangSmith — thread-scoped nested traces, background flush | Decided |
| **Frontend** | React 19 + Vite + TypeScript + Tailwind; driver = PWA | Decided |
| **Streaming** | SSE, PWA → `ap-south-1` **directly** (no CDN proxy hop); AgentCore supports SSE on `/invocations` | Decided |
| **LLM** | **`gemini-3.7-flash` on Vertex AI `asia-south1`** — in-region, `thinking_level: high` | Decided |
| **LLM SDK** | **`langchain-google-genai` ≥ 4.x** (wraps `google-genai`). 2.x **breaks the tool loop** — see §7 | Decided |

**Performance target** (from Appendix A, adopted): **TTFT p95 < 1.2 s · single-hop turn p95 < 2.5 s.**

---

## 1 · Technical Context

The seven fields from spec-kit's Technical Context skeleton (see the UI-UX README's "Spec-kit evaluation"
note — the tool isn't installed, only this document shape is borrowed).

| Field | Value |
|---|---|
| **Language / version** | Python 3.12+ (backend, agent) · TypeScript 5.x (frontend) |
| **Primary dependencies** | FastAPI · SQLAlchemy (async) · **`langchain-google-genai` ≥ 4.x** (`bind_tools` only; wraps `google-genai`) · **`langchain-core` ≥ 1.x** · `redis-py` · LangSmith SDK · React 19 · Vite · Tailwind · shadcn/ui · assistant-ui · Kibo UI Gantt |
| **Storage layer** | Supabase PostgreSQL (business source of truth) · Upstash Redis (bounded, non-authoritative session/conversation state, 24 h TTL) |
| **Testing framework** | pytest (backend, incl. the §9.2 named stress tests) · Vitest + Playwright (frontend/E2E) |
| **Target platform** | **ARM64** throughout — AgentCore Runtime *requires* it, so ECS Fargate matches it to keep **one build artifact**. AgentCore `ap-south-1` (driver chat) · ECS Fargate `ap-south-1` (REST) · **static frontend host unsettled** (Cloudflare Pages or Vercel) · driver surface is an installable PWA |
| **Performance goals** | TTFT p95 < 1.2 s · single-hop turn p95 < 2.5 s · `find_feasible_slots` < 50 ms · hop count tracked as a first-class metric |
| **Scale / scope** | 6 facilities · 24–32 docks · 190–240 appointments/day · 20–35 exception requests inside a 30-min disruption spike · 5 concurrent coordinators |

---

## 2 · Agent runtime

| Concern | Decision | Why |
|---|---|---|
| Runtime | **AgentCore Runtime, `ap-south-1`, ARM64** | Owner constraint; AWS credits cover hosting |
| Loop location | **Inside AgentCore** — but *only* the driver-chat loop | See the topology note below. AgentCore serves `/invocations`, `/ws`, `/ping` and **nothing else** |
| REST surfaces | **ECS Fargate, `ap-south-1`** | The other five surfaces need ordinary REST routes, which AgentCore cannot mount |
| Loop implementation | LangChain `bind_tools` + bounded manual loop | Owner constraint. Also keeps hop count controllable, which is latency lever #1 |
| Agent framework | **None** — no executor, no LangGraph | The scheduling decision is deterministic and lives in code (§5); the LLM only calls typed tools and narrates receipts (§7.2b) |

### The topology reversal — read this before assuming it's an error

Appendix A named one risk as **"the largest single"**: whether AgentCore is offered in `ap-south-1`. It
recommended **topology (B)** — loop in FastAPI, AgentCore for identity/memory/gateway only — but that
recommendation was **explicitly conditional** on AgentCore *not* being in Mumbai, because otherwise every
tool call would cross regions to reach the database.

**AgentCore is now available in `ap-south-1`** (Runtime, Identity, Memory, Gateway, Observability).
The condition behind topology B therefore no longer holds.

Running the loop **inside AgentCore** now satisfies Appendix A's actual underlying rule —

> *"Compute, Postgres and Redis go in one region. Only the model may be remote."*

— with **zero cross-region tool hops**, because AgentCore, Supabase and Upstash are all in `ap-south-1`.
This reconciles the owner's hard AgentCore constraint with the latency architecture instead of trading one
against the other. The principle Appendix A stated to survive exactly this kind of change still governs:
**co-locate with the data, not with the user.**

### The correction — AgentCore is not a general REST host

An earlier draft of this section read as though *the whole modulith* moves inside AgentCore. It does not.
Verified against AWS's service-contract and HTTP-protocol-contract docs, AgentCore Runtime mounts exactly
three paths:

| Property | Value |
|---|---|
| **Mount paths** | **`/invocations` (POST) · `/ws` (optional) · `/ping` (GET)** — nothing else |
| Port / host | 8080 / `0.0.0.0` |
| **Platform** | **ARM64 required** |
| Streaming | **SSE supported on `/invocations`** — the streaming decision holds |

There is no way to serve `/api/appointments` or any other planner/ops/gate/carrier/admin route from it.

**The corrected shape — one codebase, two deployment targets, one region:**

| Target | Serves |
|---|---|
| **AgentCore Runtime** | Driver chat only, via `/invocations` (SSE) |
| **ECS Fargate** | REST for the five non-chat surfaces + BFF |

Both run in `ap-south-1`, both hold their own DB and Redis connections, both are in-region. **The modulith
claim survives intact** — one codebase, one database, enforced module boundaries; deployed twice to serve
two entry protocols. Two deployment targets is not two services: there is no network call between them, no
independent release cycle, and no split of the schema. **That is not microservices**, and M6's
single-database exclusion constraint is untouched.

This also explains a structure that looks accidental: `agentcore/codezip/app/` exists **because the same
code deploys to two runtimes**. See `DEPLOYMENT.md` §2.2 — it is structural, not cruft.

---

## 3 · Data layer

| Concern | Decision | Why |
|---|---|---|
| Database | Supabase PostgreSQL, `ap-south-1` | Business source of truth (D1's `dock_occupancy` + GiST exclusion constraint) |
| Connection | SQLAlchemy async pool on a **direct connection**; explicit `pool_size`/`max_overflow` | Long-lived containers hold the pool. If routed through Supavisor in transaction mode, **disable prepared statements** |
| Session/cache | Upstash Redis, `ap-south-1` | Bounded, non-authoritative, 24 h TTL — never the source of truth |
| Redis transport | **Native Redis protocol over a persistent connection — not the REST/HTTP API** | Per-call TLS setup costs tens of ms *twice per turn* (read at turn start, write at turn end) |
| Tool reads | **Batched** — one query returning driver + shipment + appointment + latest ETA | Four sequential 5 ms round trips are serial *inside* the tool, so they stack |
| Feasibility query | Budgeted **< 50 ms** | The GiST index backing D1's exclusion constraint serves the overlap query directly — this should never be the bottleneck |

---

## 4 · Identity and scope

M15 makes scope **foundational architecture, not an auth requirement** — *"scope is derived from the
authenticated identity and enforced in the repository layer, never accepted from a client-supplied id."*
Two identity systems are in play and they do different jobs; conflating them is the failure mode.

| Concern | Decision | Why |
|---|---|---|
| **User identity** | **Supabase Auth** — issues the JWT a driver/planner/admin carries | Already the project's auth provider; `AGENTS.md` mandates permissions derived server-side from verified tokens |
| **Scope resolution** | FastAPI validates the JWT, then resolves scope from **`user_scopes`** (facility / carrier / driver) **server-side** | M15. No tool accepts a `facility_id` or `carrier_id` that decides *what the caller may see* — where an id appears it selects *within* scope and is validated against it (§7.5's opening principle) |
| **Workload identity** | **AgentCore Identity** — inbound authorization to the Runtime, and the agent's own credentials for calling AWS services | A different concern from user identity: it answers *"may this caller invoke the agent"* and *"what may the agent itself access"*, not *"which shipments belong to this driver"* |
| **Enforcement point** | **Repository layer**, not the router and not the tool schema | Retrofitting tenant scoping is called out in §0.9 as *"one of the most expensive rewrites in this class of application"* |

**The boundary, stated plainly**: Supabase Auth answers *who the human is*. AgentCore Identity answers
*who the workload is*. `user_scopes` answers *what that human may see*. The agent never derives scope from
anything the model produced — the model cannot widen its own access by emitting a different `facility_id`,
because the repository ignores it.

---

## 5 · Background jobs — the expiry sweeper

D2 requires it (*"lazy expiry + sweeper"*) and §9.2's nastiest race is **defined** by it. AgentCore Runtime
is request-driven, so this needs its own mechanism.

### What must run

| Job | Cadence | Effect |
|---|---|---|
| **HELD expiry** (D2, 90 s TTL) | Periodic | Transition lapsed `HELD` rows to `EXPIRED` |
| **PENDING expiry** (D9, 15-min TTL) | Periodic | Release the interval · raise `PENDING_EXPIRED_UNACTIONED` (§7.4) · notify the driver |
| **Outbox drain** (§6) | Periodic | Deliver queued notifications |

### The granularity question, and why it isn't a problem

EventBridge Scheduler's floor is **1 minute** — uniformly, in every region including `ap-south-1`. The
naive reading is that a 90-second hold therefore needs sub-minute machinery (Step Functions wait-loops,
SQS message timers). **It does not**, and the reason is in D2's own design:

> *"Expiry is lazy plus swept. Every read filters `state='HELD' AND expires_at > now()`; a sweeper
> transitions stale rows to `EXPIRED`. **Never depend on the sweeper for correctness — only for hygiene.**"*

A lapsed-but-unswept `HELD` row is **never trusted by any read**, so sweep lag cannot cause a wrong
booking. The sweeper tidies; the read filter is what's load-bearing. A 1-minute cadence is therefore
adequate for the 90-second hold, and comfortably so for D9's 15-minute pending — where the sweeper *does*
have real side effects (escalation + driver notification) but a 15-minute TTL tolerates ≤1 minute of lag.

**Do not build sub-minute scheduling for this.** It would be complexity bought against a problem the
architecture already solved.

### Decision

| Concern | Decision | Why |
|---|---|---|
| Trigger | **EventBridge scheduled rule → API destination, 1-minute rate**, `ap-south-1` (corrected 2026-09-02, #111 -- see §1's note) | Native, no infrastructure to run, adequate per the reasoning above |
| Target | An **authenticated internal endpoint on the FastAPI service** — not a separate Lambda | Reuses the existing connection pool and stays inside the co-located tier; a Lambda would need its own VPC config, cold starts, and a second DB connection path |
| Transactionality | The sweeper's transition and `confirm_request` **take the row under the same transaction** — exactly one commits, loser gets `ALREADY_ACTIONED` with the winning transition named | §7.5.1's stated resolution to §9.2's nastiest race. **This is the correctness requirement**, not the cadence |
| Clock | Uses the **injectable clock** threaded through the engine, TTL sweepers and sequencer (§9.1) | Makes `pending_expiry_vs_planner_confirm` reproducible on demand rather than by timing luck |

---

## 6 · Notifications and the outbox

§6's module 10 requires warehouse email and driver notification; `notification_outbox` implements the
**transactional outbox** pattern so *"a booking and its notification cannot diverge."*

### Channels

| Channel | Mechanism | Cost |
|---|---|---|
| **Driver — web push** | Web Push API with **VAPID** keys, direct to the installed PWA | **Free** — no vendor, no per-message charge |
| **Driver — in-app** | Rendered in the thread on next open | Free |
| **Warehouse — email** | AWS SES, `ap-south-1` | Effectively free at this volume |
| ~~Driver — SMS~~ | **Dropped from v1** — see below | — |

### Why SMS was dropped

Not a cost-trimming preference — three separate blockers:

1. **Per-message charges** — not free at any volume.
2. **DLT registration is mandatory in India.** Commercial SMS requires registering the brand as a
   principal entity with TRAI via a DLT portal, yielding an Entity ID and Template ID that must accompany
   every send. Process is: register with TRAI, *then* file an AWS Support request.
3. **Lead time** — that registration is a multi-step regulatory process, not a config flag.

*(Noted for completeness: AWS End User Messaging supports India local routes **only** through `ap-south-1`
/ `ap-south-2` — which is where we are. So the region was never the obstacle; cost and registration are.)*

**The honest consequence**: a driver who has not granted push permission — or is on iOS without adding the
PWA to their home screen — receives **no proactive alert** for a critical event. Nothing is *lost*: the
thread list shows current promise state on next open (`01-driver-chat/screens.md`). But it is not *pushed*.
This is a real, accepted limitation, recorded rather than glossed.

### A convergence worth noting

DLT would have *required* pre-registered message templates — you cannot send arbitrary SMS text in India.
`voice-and-tone.md` already mandates templated (not generated) state messages, for correctness reasons
entirely unrelated to telecom regulation. Had SMS stayed, the product's existing discipline would have
satisfied a regulatory constraint for free. Worth remembering if SMS is ever revisited.

### Outbox drain

Same mechanism as §5's sweeper — an EventBridge scheduled rule → API destination → the FastAPI service (corrected 2026-09-02, #111). The outbox row is written
**in the same transaction** as the business change; delivery is a separate, retryable step. Delivery status
lands in `operational_messages`, and a `FAILED` send raises `NOTIFICATION_FAILED` (§7.4) — *"a confirmation
nobody received is not a confirmation."*

---

## 7 · Model layer — `gemini-3.7-flash` on Vertex AI `asia-south1`

**Decision (D-4)**: `gemini-3.7-flash`, served from **Vertex AI `asia-south1` (Mumbai)**, called through
**`langchain-google-genai` ≥ 4.x**, which wraps the consolidated `google-genai` SDK.

**Decision (D-4a)**: `thinking_level` pinned **`high`**. This **deliberately declines lever #6** of §10
("lower effort for routine turns") — recorded so a later reader does not "fix" it as an oversight. The
rationale is in *The effort lever* below.

**Naming note, added 2026-08-25 (E4.1/issue #31), does not change D-4**: Google announced "Vertex AI" as
renamed/absorbed into the **Gemini Enterprise Agent Platform** at Cloud Next 2026 (2026-04-22), bundling
Agent Studio/ADK/Agent Engine/200+ models under one brand — Vertex AI genuinely is now marketed as an agent
*hosting* platform, not just a model-serving API, which is worth stating plainly rather than leaving this
section's older framing to imply otherwise. Two things are unaffected by the rebrand: (1) the REST endpoint
this integration actually calls, `aiplatform.googleapis.com`, is unchanged — it predates the "Vertex AI"
name itself; (2) the SDK choice this section already made, `langchain-google-genai` (wrapping `google-genai`)
over `langchain-google-vertexai`/`ChatVertexAI`, turns out to be the forward-compatible side of this exact
transition — the *older* Vertex AI SDK (what `ChatVertexAI` wraps) is the one being deprecated, with updates
stopping 2026-06-24; `google-genai` is not. This project deliberately still does not use any Agent
Engine/Agent Builder surface — the integration below is a plain model-inference call (`ChatGoogleGenerativeAI`
in Vertex mode), and AWS AgentCore remains the agent-hosting runtime per the owner's explicit AWS-credit
constraint (§2, "Owner constraint; AWS credits cover hosting") — a cost decision, not a capability gap this
rebrand fills. If that constraint is ever revisited, Gemini Enterprise Agent Platform's own Agent Engine
would be the thing to evaluate against AgentCore, but that is a new decision, not implied by this rebrand.

This section previously recorded an open three-way bake-off between Nova Lite, OpenAI, and Groq/Cerebras
open-weights. **That bake-off is closed**, superseded by two findings: an in-region inference path that
none of those candidates could offer, and a spike that settled the tool-calling gate empirically.

### The regional finding — superseding "no India-resident option"

An earlier draft of this section stated: *"There is no India-resident inference option… the model hop is
cross-region no matter what we choose."* **That is true only for Bedrock.** It was written from Bedrock's
constraints and over-generalised to all providers.

Vertex AI serves Gemini from **`asia-south1` with guaranteed in-region ML processing**:

| Path | Routing | Model hop | Residency |
|---|---|---|---|
| Claude on Bedrock | `global.anthropic.*` → US | ~200–250 ms | ❌ leaves India |
| Amazon Nova on Bedrock | APAC cross-region profiles | ~50–70 ms | ⚠️ APAC, not India |
| OpenAI | US-hosted | ~200–250 ms | ❌ leaves India |
| **Gemini on Vertex `asia-south1`** | **in-region** | **~5–15 ms** | ✅ **stays in India** |
| Bedrock latency-optimised inference | US regions only | — | Unusable from India |

This removes **~200 ms from the only remote hop left in the design** and resolves the residency concern
previously recorded as "accepted, unavoidable" (§11, `GAP_ANALYSIS.md` Gap 2). Note this *raises* the
relative value of lever 4 (region choice) that the superseded text had discounted.

### ⚠️ The API-key trap that would silently forfeit both benefits

`genai.Client(vertexai=True, api_key=...)` is the shortest path to working code, and it is the wrong one.
A reported issue states that **Vertex with API-key auth ignores `GOOGLE_CLOUD_LOCATION` and uses the global
endpoint**. Google's own docs warn: *"do not use the global endpoint if you have ML processing requirements
— you can't control or know which region your requests are sent to."*

**Required configuration: ADC with explicit `project` and `location="asia-south1"`.** Not the API-key path.

The failure mode is the dangerous kind — it *works*, returns correct answers, and silently costs both the
in-region latency and the residency guarantee that are the entire reason for choosing Vertex. **Assert the
resolved endpoint region at startup** rather than trusting configuration.

### The pre-commit spike — run 2026-08-21, results recorded

Executed against `gemini-3.7-flash` via the Gemini Developer API (a `GOOGLE_API_KEY`, not Vertex
credentials — see the limitation below). Throwaway scripts, not repo code.

| # | Check | Result |
|---|---|---|
| 1 | Model string resolves | ✅ `models/gemini-3.7-flash` visible among 37 models |
| 2 | Bare call via `ChatGoogleGenerativeAI` | ✅ 1.86 s |
| 3 | `.bind_tools()` single-shot | ✅ correct tool + well-formed args |
| 4 | **Gate 1 — 12-tool driver allowlist** | ✅ **see analysis below**, mean 1.53 s |
| 5 | **Multi-turn tool loop** | ❌ **at 2.1.12** · ✅ **at 4.3.5** — the deciding result |
| 6 | `thinking_level` settable | ❌ at 2.1.12 · ✅ **native at 4.3.5** (lowercase values) |
| 7 | Raw `google-genai` SDK loop (fallback path) | ✅ 4 inferences, 4 hops, 8.61 s |
| — | `location="asia-south1"` pinning | ⛔ **not tested** — needs GCP project + ADC |

**The deciding result is #5.** At the installed `langchain-google-genai 2.1.12` the bounded manual loop
fails on the second inference:

> `400 Function call is missing a thought_signature in functionCall parts. This is required for tools to
> work correctly, and missing thought_signature may lead to degraded model performance.`

`gemini-3.7-flash` requires the model's own turn to be echoed back **verbatim**, carrying an opaque
`thought_signature`, before tool results are appended. LangChain 2.1.12 reconstructs the assistant turn and
drops it. Single-shot tool calling still works, which makes this trap easy to miss — **a spike that stopped
at check 3 would have passed the model and shipped a broken loop.**

At `langchain-google-genai 4.3.5` the same loop passes: **4 inferences, 4 tool hops, 7.40 s**.

**Gate 1 nuance.** The scored run was 5/8. The three non-matches were re-read and are **test-expectation
errors, not model failures** — the model gathered context before acting (defensible), never guessed a
shipment ID on the ambiguous prompt, and never called `confirm_held_slot` on the refusal probe. All three
are the behaviour §7.2b and D6 require. Gate 1 **passes**.

### Dependency consequence — the upgrade is a prerequisite, not an option

`langchain-google-genai` 4.x requires `langchain-core` **1.x**. At first reading that looks like a major
migration imposed by one integration. It is closer to the reverse: the environment inspected on 2026-08-21
already had **14 packages pinned against `langchain-core >= 1.x`** — `langgraph` 1.2.0,
`langchain-community` 0.4.1, `langchain-classic` 1.0.7, `langchain-google-vertexai` 3.2.3 and others —
while core sat at 0.3.86, so `pip check` reported 14 conflicts *before* any change.

Moving to core 1.x **resolves** those rather than creating new ones. `langchain-openai` 0.3.35 → 1.x rides
along; that line exists (1.6.0 current).

Two honest caveats: this was the global site-packages, **not** the uv-locked backend environment, which was
not read; and the 4.x message-content shape differs (content blocks, not a plain string), so any code
reading `.content` directly needs checking.

**Package choice**: `langchain-google-genai`, **not** `langchain-google-vertexai`. `ChatVertexAI` is being
superseded, and 4.x wraps the same `google-genai` SDK the owner's own sample uses — the two align rather
than compete.

### The fallback, and why it was kept viable

If the core 1.x upgrade proves too disruptive against the real `uv.lock`, **the raw `google-genai` SDK path
is proven working** (check 7). It honours the constraint's spirit — no agent framework, bounded manual
loop, typed tools bound to the LLM — and drops only the LangChain dependency. The one line that matters:

```python
# CRITICAL: append the model's turn back verbatim — this carries thought_signature
contents.append(cand.content)
```

This is a genuine fork in the road, not a formality. **Decide it against `backend/uv.lock`, not against
the global environment measured above.**

### The effort lever — D-4a's cost, measured rather than assumed

`thinking_level` is §10's lever #6. Pinning it `high` looks like it contradicts the latency goal. The
non-obvious interaction is that **hop count is lever #1**, and one wrong tool call costs a full extra round
trip — *two* inferences. A higher effort level that reduces mis-selection can be **net faster** despite
each call being slower.

The spike measured full turns at 7.40 s for a 4-hop turn, against `NFR-002`'s 2.5 s single-hop budget. That
gap is **hop count, not effort level** — which is exactly why §10 orders prefetch first. D-4a stands.

⚠️ Still unmeasured: TTFT and hop count at `low` / `medium` / `high` head-to-head. Recorded as an open item
rather than asserted either way.

### Provider abstraction (retained)

Tools bind through **one interface** with a **second provider behind an env flag** — primary plus one
documented fallback. This mirrors what the live system already does and means running out of credit
mid-demo has an escape hatch. The OpenAI fallback **leaves India** (§11).

### Credit scope — do not assume

The available GCP credit reads *"Trial credit for GenAI App Builder"*, usage scope *"Certain usage."* It is
**product-scoped**. Whether it covers raw Vertex AI inference **needs confirming against the offer terms**
— open item, not an assumption.

### Multimodal — a capability filter, not a v1 feature

The model must be **capable** of image input; **v1 does not use it.** This reverses nothing:
`ai-chat-primitives.md`'s "file attachments not adopted for v1" stands, the driver chat gains no
attachment affordance, and `SOLUTION_DESIGN.md` needs no change. Per that file's own wording, actually
using it *"is a new product requirement first, a UI primitive second."*

---

## 8 · Observability — LangSmith

**Trace *shape* and trace *timing* are two separate requirements.** Specifying only the second is what
made an earlier draft incomplete.

### Shape — thread-scoped, fully nested

- **One trace per driver turn**, grouped into a **conversation thread** so an exchange is reviewable as a
  unit rather than as scattered one-off runs.
- **The thread key maps to the schema's existing `chat_threads.thread_id`** — no new identifier invented.
  A LangSmith thread and a SetuHaul thread are the same thing when debugging.
- **Every step inside a turn is a child span**, in execution order: each LLM inference *and* each tool
  call, nested under the turn's parent run.

### Why the nesting earns its keep beyond debugging

- **It is audit evidence for the product's central correctness rule.** §7.2b requires the LLM to narrate
  decision receipts and never invent reasoning. A trace showing `find_feasible_slots` → its typed result →
  the narration *proves* the rule held on that turn.
- **It makes hop count directly observable.** Appendix A names hop count as latency lever #1 and warns
  that a rise in average hops per turn *"will show up as a latency regression that no amount of
  infrastructure tuning will fix."* Nested spans make it measured rather than inferred.

### Timing — never in the request path

Full capture, **background flush**: fire-and-forget, bounded queue, **drop rather than block**. LangSmith
is hosted outside India; awaiting a flush adds a cross-region round trip to *every* turn.

**Rich capture and async flush are compatible** — there is no trade-off between them. Sample in production
if volume grows; trace everything in development.

---

## 9 · Frontend

| Concern | Decision | Why |
|---|---|---|
| Framework | React 19 + Vite + TypeScript + Tailwind | Locked during the UI/UX phase |
| Primitives | shadcn/ui (Radix-backed), consumed through our tokens | U51 |
| Dock board | Kibo UI Gantt (MIT), installed as source | U52 — zoom presets + virtualisation still unverified |
| Chat rendering | assistant-ui | U56 |
| Driver surface | Installable **PWA** | Roadside use, poor connectivity, cheap Android |
| Design tokens | Three-tier grammar, prose tables | `tokens.md` (U85). DTCG JSON is the path *if* machine-readable tokens are ever needed |

### assistant-ui runtime adapter — the deferral this document resolves

`ai-chat-primitives.md` explicitly deferred the runtime/adapter choice (LangGraph / Vercel AI SDK /
custom) to this document, stating it *"names the fit, not the backend."*

**Decision: a custom runtime adapter** (`ExternalStoreRuntime`-style) pointing at our own FastAPI SSE
endpoint. Rationale: the LangGraph adapter assumes a graph-based agent we deliberately don't have (no
executor, per §2), and the Vercel AI SDK adapter assumes the model call happens in a Vercel function —
which would move inference *away* from the co-located tier and add exactly the proxy hop §6's latency
rules eliminate.

### Frontend latency decisions

| Decision | Why |
|---|---|
| **SSE token streaming**, not WebSocket | Only server→client streaming is needed; SSE traverses CDNs/proxies cleanly and has native `EventSource` support |
| **Driver PWA calls the `ap-south-1` origin directly** — not proxied through a CDN function | A proxy adds a full hop for zero benefit. This matters more for chat than for REST: SSE through an edge function risks buffering, which destroys TTFT |
| Static assets CDN-global (**Cloudflare Pages or Vercel — unsettled**, `DEPLOYMENT.md` open item 7) | Assets are region-agnostic; the API is not. **Both are sub-100 ms in India, so this choice is not a latency decision** — it turns on licensing. No edge functions are used, so there is nothing to region-pin either way |
| Skeletons over spinners; render the shell before data | Already specified in `00-foundations/components.md` §13 |

---

## 10 · Latency levers — ordered checklist

Appendix A's own priority order. **The ordering matters**: one tool hop costs *two* LLM inferences (the
call that decides to use the tool, and the call that writes the answer), so a three-hop turn costs four.

- [ ] **1. Delete the first tool call.** Pre-fetch `get_driver_operational_context` at session open and
      inject it into the prompt. Removes an entire LLM round trip from the common path — *"worth more than
      any region tuning."*
- [ ] **2. Shrink the tool surface.** Driver allowlist of ~8–12 tools, not all 23. Schemas are input tokens
      on *every* call **and** degrade selection accuracy, which causes extra hops.
- [ ] **3. Stream the final response.** TTFT is what a driver at a roadside actually experiences.
- [ ] **4. Prompt-cache the stable prefix.** Order is `tools` → `system` → **breakpoint** → volatile
      context → history → user message. Caching is a **prefix match** — any byte change invalidates
      everything after it.
- [ ] **5. Verify the cache is actually hitting.** Check cached-token counts across repeated turns; zero
      means something volatile (a timestamp, an unsorted `json.dumps`, a varying tool list) leaked into the
      prefix.
- [ ] ~~**6. Lower reasoning effort for routine turns.**~~ **Declined — D-4a pins `thinking_level: high`.**
      Left visible rather than deleted so nobody re-proposes it as an oversight. The counter-argument:
      hop count is lever **#1**, one mis-selected tool costs a full extra round trip (*two* inferences),
      so higher effort can be net faster. **Reasoned, not yet measured** — open item 1c.
- [ ] **7. Return all parallel tool results in a single message.** Splitting them across messages silently
      teaches the model to stop calling tools in parallel — converting parallel work into sequential hops.
- [ ] **8. Keep LangSmith off the request path.** (§5)
- [ ] **9. Batch tool reads; use the native Redis protocol.** (§3)

### What to measure

TTFT p50/p95 · **hop-count distribution per turn** · per-tool DB latency · LLM latency split into network
vs inference · cache hit rate · Redis RTT.

---

## 11 · Data residency — what actually crosses

Stated precisely rather than as a vague "offshore" caveat.

**Stays in `ap-south-1`**: PostgreSQL (the business source of truth — every shipment, appointment, dock,
ETA, audit record) · Redis session state · all compute · all tool execution.

**Crosses the region boundary on the primary path**: **nothing.** Vertex AI `asia-south1` serves
`gemini-3.7-flash` with guaranteed in-region ML processing, so the conversation text and tool results of
the turn being processed stay in India too.

**This supersedes an earlier claim in this section** that *"no India-resident inference option exists."*
That was true of Bedrock and was over-generalised to every provider.

**What this does and does not do for `GAP_ANALYSIS.md` Gap 2 (DPDP Act 2023).** It **strengthens** the
posture — chat text containing personal data no longer crosses a border, so cross-border-transfer exposure
on the primary path drops to nothing. It **does not close Gap 2**, which is about consent, erasure, and the
M14-vs-erasure tension. Those are unaffected by where inference runs.

Two conditions the guarantee depends on, both of which can fail silently:

1. **ADC with explicit `location="asia-south1"`** — not API-key auth, which may route to the global
   endpoint and forfeit both residency and the ~200 ms saving (§7).
2. **The fallback provider still leaves India.** If the env flag flips to the OpenAI path (§7, Provider
   abstraction), conversation text crosses to the US. The fallback is a residency decision, not just an
   availability one — **treat flipping it as a deliberate act, not an automatic failover.**

Appendix A's co-location rule allowed the model to be remote. On the primary path it no longer needs to be.

---

## 12 · Constitution Check

Per the habit adopted from `02-ops-exception-console/` onward — new decisions checked against
`AGENTS.md`'s Delivery rules.

| Rule | Check |
|---|---|
| React 19 is the frontend | ✅ Unchanged (§6) |
| FastAPI routers stay thin; rules in services, persistence in repositories | ✅ Unchanged — the agent loop calls typed tools, which call services |
| The LLM orchestrates typed tools and never executes SQL or mutates business tables | ✅ Reinforced — no executor, no SQL tool, and §5's nested traces make violations visible |
| PostgreSQL is the business source of truth; Redis is bounded/non-authoritative with 24 h TTL | ✅ Unchanged (§3) |
| Scope/permissions derived server-side from verified tokens | ✅ Unchanged — every §7.5 tool derives scope from identity, never from an argument |
| Never commit secrets, tokens, or credentials | ✅ Provider keys via environment/SSM; none in this document |
| Material behaviour changes require proportional tests and docs | ✅ §1 names the test stack; §7's spike is itself a gated verification, **run rather than asserted** |

**No conflicts found.** Two items worth naming explicitly:

**1.** Running the driver-chat loop **inside** AgentCore (§2) reverses a *provisional* recommendation in
`SOLUTION_DESIGN.md` Appendix A — but Appendix A is marked non-binding by D4, and the reversal follows that
appendix's own stated principle once its region condition is satisfied. This is a resolution, not a
contradiction.

**2.** Deploying to **two targets** (§2) does not breach the modulith decision. One codebase, one database,
one release, enforced module boundaries — split only by entry protocol, because AgentCore mounts three
fixed paths and cannot serve REST. **M6's single-database exclusion constraint is untouched**, which is the
test that actually matters: there is no distributed transaction anywhere in the design.

---

## 13 · Open items — verify, don't assume

| # | Item | Why it matters |
|---|---|---|
| 1 | ~~**The model bake-off**~~ | **Closed 2026-08-21** — `gemini-3.7-flash` on Vertex `asia-south1` (§7), with Gate 1 passed and the tool loop verified by spike |
| 1a | **Does `location="asia-south1"` actually pin in-region?** — **same open item as `DEPLOYMENT.md` §11 item 2a**, cross-referenced 2026-08-22 after a consistency sweep found the two stated independently with no link between them | **The single largest latency variable left** — ~5–15 ms in-region vs ~200 ms to a global endpoint, plus the residency guarantee. Untestable in the spike (needs a GCP project + ADC). **Assert the resolved region at startup rather than trusting config**. Resolving it here resolves it there too — update both, or neither |
| 1b | **Which LangChain path against the real `uv.lock`** | 4.x + `langchain-core` 1.x, or the proven raw `google-genai` SDK fallback. The global env showed 14 pre-existing conflicts that the upgrade *resolves*, but `backend/uv.lock` was not read — **decide against the lockfile, not the global env** (§7) |
| 1c | **`thinking_level` head-to-head at `low`/`medium`/`high`** | D-4a pins `high` on the argument that fewer mis-selected tools beats faster individual calls. That argument is reasoned, **not measured**. Measure TTFT *and hop count* together — hop count is lever #1 |
| 2 | **Does the GCP credit cover Vertex inference?** — **same open item as `DEPLOYMENT.md` §11 item 2b**, cross-referenced 2026-08-22 | Reads *"Trial credit for GenAI App Builder"*, scope *"Certain usage"* — **product-scoped**. Confirm against the offer terms; it almost certainly will not fund compute (§7). Resolving it here resolves it there too — update both, or neither |
| 2a | **OpenAI's current model naming and pricing** (fallback path only) | Research returned a Sol/Terra/Luna lineup and did *not* find "gpt-5-mini"/"gpt-4o-mini" pricing. **Confirm against OpenAI's own pricing page before writing a model ID into code** — do not commit on the strength of a search snippet |
| 3 | ~~**Is Supabase actually in `ap-south-1`?**~~ | ✅ **CONFIRMED 2026-08-21** via Supabase MCP — project `setuhaul`, `ap-south-1`, `ACTIVE_HEALTHY`, PostgreSQL 17.6.1. The co-location argument in §2–§3 now rests on verified fact |
| 4 | ~~**Is Upstash actually in `ap-south-1`?**~~ | ✅ **CONFIRMED 2026-08-21** via the Upstash console — AWS Mumbai (`ap-south-1`), Free Tier, **Global** replication. ⚠️ Global mode adds read replicas outside India: a residency surface (§11), bounded by the 24 h TTL and non-authoritative status but worth an explicit decision |
| 4a | **Is the Upstash database named "langsmith test" the right one?** | It is Free Tier and carries a scratch-sounding name. Confirm it is SetuHaul's actual store before a production path depends on it (`TASKS.md` Phase 0) |
| 5 | **LangSmith's exact thread-grouping metadata key** | `session_id` / `thread_id` / `conversation_id` — more than one is accepted; check the docs rather than guess (§5) |
| 6 | **How `bind_tools` child runs surface in a manual loop** | We have no executor, so nesting (§5) may need explicit run-tree construction rather than coming free |
| 7 | **AgentCore Evaluations and Policy are absent in `ap-south-1`** | Fine for this build — named so it isn't discovered at deploy time |
| 8 | **Kibo UI Gantt zoom presets + virtualisation** | Carried from U52, still unverified; the dock board's usability at scale depends on it |
