# Comparison — latency (Phase 0 of TASKS.md)

> Scope: `SOLUTION_DESIGN.md` **Appendix A** (read in full) + `TECH_STACK.md` **§10** (read in full, plus
> §1/§2/§3/§7/§8/§9/§11/§13) against the live request path for one driver turn:
> `backend/app/api/v1/routers/chat.py` → `assistant/run_assistant.py` → `assistant/{llm,tools,observability,
> agentcore_runtime,agentcore_main}.py` → `services/{driver_reads,redis_memory}.py` →
> `scheduling/feasibility.py` → `core/{deps,security,settings}.py` → `db/session.py`, plus
> `supabase/migrations/`, `backend/pyproject.toml`/`uv.lock`, and the installed packages in
> `backend/.venv/`. Read on 2026-08-22. **Comparison only — nothing under `backend/`, `frontend/`, or
> `supabase/` was edited.**
>
> Builds on the five prior passes rather than re-deriving them. Where a prior pass established a fact
> (no SSE, no Vertex, `AWS_REGION=us-east-1`, no prefetch, 23 tools, no `dock_occupancy` GiST index,
> four-way duplicated scope checks), it is cited and its **latency consequence** is formalised here — not
> re-discovered.

**Tags** (per the brief): **✅ Meets the target** · **⚠️ Needs improvement** · **📋 FR/NFR mapping** ·
**🚩 Wrong-optimisation flag**.

---

## 0. Method, stated honestly up front

There is no running system to profile in this pass. Every number below is one of two kinds, and they are
labelled:

- **Counted** — sequential `await`s, DB round trips, HTTP round trips, LLM inferences, tool hops. These are
  read directly off the code path and are exact.
- **Estimated from shape** — wall-clock milliseconds. These are derived from the round-trip counts and the
  project's own measured figures (`TECH_STACK.md` §7's spike: bare Gemini call 1.86 s; 4-hop LangChain turn
  7.40 s; raw-SDK 4-hop turn 8.61 s). They are **not** measurements and are never presented as such.

Every behavioural claim about a third-party library was verified this pass against either the installed
package source in `backend/.venv/` or current vendor documentation — sources listed at the end. Nothing
about connection-pool semantics, SSE patterns, prompt caching, boto3 client cost, or Vertex region pinning
is asserted from memory.

**One correction to the brief's own citation**: the `find_feasible_slots` < 50 ms budget is **`NFR-003`**,
not `NFR-002` (`ARCHITECTURE/REQUIREMENTS.md:305`). `NFR-002` is the single-hop-turn p95 < 2.5 s budget
(line 303). Both are used below with their correct IDs.

---

## 1. Headline — four structural facts, before any lever

1. **TTFT does not exist as a separate quantity in this codebase.** Confirmed by the AI-assistant pass and
   re-verified here: `grep` across `backend/app/` for `astream`, `StreamingResponse`, `EventSourceResponse`,
   `text/event-stream` returns **zero matches**. `NFR-001` (TTFT p95 < 1.2 s) is not merely unmet — there is
   no code path on which it could be measured. `chat.py:70` returns one `ok(result, ...)` envelope after the
   entire loop completes.
2. **The turn's critical path contains three *synchronous, event-loop-blocking* network calls inside `async
   def` handlers** — a JWKS fetch, every Upstash call, and (in AgentCore mode) the entire AgentCore
   invocation. This is a concurrency finding with a direct latency consequence: under the `NFR-016` spike
   these do not just cost their own latency, they serialise every other in-flight turn on the same worker.
   No prior pass covered this. Details in §4.2.
3. **One pooled Postgres connection is held, idle-in-transaction, for the entire multi-second LLM turn** —
   including in AgentCore mode, where the FastAPI process issues exactly one query and then does nothing
   with the connection for the rest of the turn. With `pool_size=3, max_overflow=2` (`db/session.py:54-55`)
   the sixth concurrent driver turn queues behind an LLM call, not behind a query. Details in §4.3.
4. **Every lever `TECH_STACK.md` §10 orders 1, 2, 3, 5, 8, 9 is violated; levers 4 and 7 are met; lever 6 is
   correctly declined.** The two that are met (prefix ordering, parallel-result batching) are met *by
   construction* rather than by intent — there is no comment anywhere indicating either was a decision.

---

## 2. The traced turn — counted, not estimated

**Scenario**: an authenticated driver posts *"Running 40 minutes late on SHP1017 — what slots can I get?"*
to `POST /api/v1/chat/message`. In-process mode (`AGENTCORE_RUNTIME_ARN` unset, `settings.py:59-60`). This
is a realistic two-tool-hop turn, and it is the shape `TECH_STACK.md` §10's arithmetic is written about.

| # | Step | Evidence | Blocks event loop? | Round trips |
|---|---|---|---|---|
| 1 | `RequestIdMiddleware` | `core/middleware.py` | no | 0 |
| 2 | `get_jwt_verifier` constructs a **new** `JwtVerifier` per request | `core/deps.py:69-70` | — | 0 |
| 3 | `verify_access_token` → **new `PyJWKClient`** → `urllib.request.urlopen(JWKS)` | `core/security.py:24-38`; `.venv/.../jwt/jwks_client.py:118` | **YES** — blocking `urllib` | **1 HTTPS, full TLS handshake, every single request** |
| 4 | `users ⋈ roles` identity lookup | `core/deps.py:97-111` | await | 1 DB (+1 more for `pool_pre_ping=True`, `db/session.py:29`) — **connection checked out and transaction autobegun here, released only at response** |
| 5 | `ConversationMemory(settings)` → `truststore.inject_into_ssl()` + new `upstash_redis.Redis` + new `httpx.Client` | `services/redis_memory.py:74-77`; `.venv/.../upstash_redis/http.py:54` | — | 0 (but a fresh connection pool → TLS on its first call) |
| 6 | `load_turn_context` — history + summaries + session in **one pipeline** | `services/redis_memory.py:272-276` | **YES** — sync `httpx.Client.post` | 1 HTTPS to the Upstash **REST** API |
| 7 | `build_driver_tools` → **23** `StructuredTool`s | `assistant/tools.py:671-838` | — | 0 |
| 8 | `build_chat_model` → **new** `ChatOpenAI`/`ChatGoogleGenerativeAI` per turn | `assistant/llm.py:119-140`, called at `run_assistant.py:111` | — | 0 (new SDK client → new pool → TLS on first call) |
| 9 | **LLM inference #1** — 23 tool schemas + system + summaries + session + history + message | `run_assistant.py:156` | await | 1 LLM (US-hosted: `AUTO_ORDER = ("openai", "openrouter", "gemini")`, `llm.py:24`) |
| 10 | **Tool hop 1** — `get_driver_operational_context` (the tool lever #1 exists to delete) | `tools.py`; `services/driver_reads.py:22-126` | await | **5 sequential DB round trips** (`driver_reads.py:29, 43, 66, 83, 94`) |
| 11 | **LLM inference #2** | `run_assistant.py:252` | await | 1 LLM |
| 12 | **Tool hop 2** — `find_feasible_slots` | `scheduling/feasibility.py:321-422` | await | **4 sequential DB round trips** (`feasibility.py:332, 361, 377, 397`) |
| 13 | **LLM inference #3** — writes the answer | `run_assistant.py:252` | await | 1 LLM |
| 14 | `append_turn` — one pipeline | `redis_memory.py:336-344` | **YES** | 1 HTTPS Upstash REST |
| 15 | `maybe_summarize_history` — fires once history ≥ 10 messages | `run_assistant.py:312`; `redis_memory.py:463-497` | await LLM; sync Redis blocks | **1 extra LLM inference + 6 un-pipelined HTTPS round trips** |
| 16 | `observe_output` → `MeterProvider.force_flush()` | `observability.py:157-167` | **YES** — synchronous OTLP export, 10 s default deadline | 1 OTLP |
| 17 | JSON envelope returned. No SSE. | `chat.py:70` | — | 0 |

**Counted totals for this one turn**: **3 LLM inferences** (4 on a summarising turn) · **2 tool hops** ·
**9 sequential DB round trips** (+1 pre-ping) · **3 Upstash HTTPS round trips** (9 on a summarising turn) ·
**1 blocking JWKS fetch** · **1 blocking OTLP flush** · **0 bytes streamed**.

**The arithmetic §10 opens with, applied to this turn**: hop 1 is precisely the hop lever #1 says to delete.
Deleting it removes one hop = **two inferences** by §10's own accounting — from 3 inferences down to 2 on
the identical turn, before any other change. That is a ~33% reduction in the dominant cost, achieved by a
prefetch that the tool's own description in `tools.py` already claims is happening.

---

## 3. `TECH_STACK.md` §10 — lever by lever, in the document's own order

| # | Lever | Live state | Verdict |
|---|---|---|---|
| 1 | Prefetch `get_driver_operational_context` at session open | Not implemented. `run_assistant.py:114-142` seeds system prompt + Redis summaries + session state and nothing else | ⚠️ |
| 2 | Shrink the tool surface to the ~8–12 driver allowlist | **23** tools bound (`tools.py:671-838`); `SOLUTION_DESIGN.md` §7.5.4's allowlist is 12 | ⚠️ |
| 3 | Stream the final response | No SSE anywhere; `accept="application/json"` even on the AgentCore call (`agentcore_runtime.py:83`) | ⚠️ |
| 4 | Prompt-cache the stable prefix: `tools → system → breakpoint → volatile → history → message` | **Order is exactly right.** Tools bound first (`run_assistant.py:112`), stable `SYSTEM_PROMPT` module constant first message (`:114`), volatile summaries/session after (`:119-134`), history then user message (`:135-142`). No tool description is an f-string (verified across `tools.py`) so the schema block is byte-stable turn to turn | ✅ (see caveat) |
| 5 | Verify the cache is actually hitting | Nothing reads `cached_tokens` / `usage_metadata` anywhere — `grep` for `cache_read`, `cached_token`, `cache_control` across `backend/app/` returns zero | ⚠️ |
| 6 | Lower reasoning effort — **deliberately declined**, D-4a pins `thinking_level: high` | Not set in `llm.py` at all, which is a *different* gap (the parameter is absent, not set low). Per `TECH_STACK.md` §7 it is `❌` at the pinned `2.1.12` anyway | ✅ decision honoured / not flagged, per brief |
| 7 | Return all parallel tool results in a single message | **Correct.** The inner `for call in tool_calls` loop (`run_assistant.py:172-242`) appends **every** `ToolMessage` to `messages` before the next `llm.ainvoke` at `:252`. Results are never split across separate inference turns | ✅ |
| 8 | Keep telemetry off the request path | LangSmith: plausibly fine (SDK background batching, per the AI-assistant pass). **OTEL: violated** — `MeterProvider.force_flush()` is called synchronously before the response returns | ⚠️ |
| 9 | Batch tool reads; native Redis protocol, not REST | Redis: **REST** (`upstash_redis`, HTTP). DB reads: **not batched** — 5 sequential queries where §3 names "one query returning driver + shipment + appointment + latest ETA" | ⚠️ |

**Levers met: 4 and 7 (plus 6, correctly declined). Levers violated: 1, 2, 3, 5, 8, 9.** The violated set
includes all three of the top-three-payoff levers.

---

## 4. Findings — four-tag format

### F1 — Lever #1: the prefetch hop is not deleted, and the tool's own description says it is

- **⚠️ Needs improvement.** `run_assistant.py:114-142` builds the message list without ever calling
  `driver_reads.get_driver_operational_context`. Meanwhile the tool description registered at
  `tools.py:690-693` and `SOLUTION_DESIGN.md` §7.5.4 both describe it as *"pre-fetched at session open, so
  usually zero calls."* The model therefore spends its first hop fetching context that the design says
  should already be in the prompt — and, per §2's trace, that hop is 2 of the turn's 3 inferences plus
  5 sequential DB round trips.
- **Fix**: call `await driver_reads.get_driver_operational_context(session, ctx)` once before the first
  `llm.ainvoke` and inject it as a `SystemMessage` **after** the `SYSTEM_PROMPT` message — i.e. at position
  1, alongside the existing summaries/session blocks at `run_assistant.py:119-134`, not before them.
  Appendix A is explicit on the ordering constraint: *"volatile driver context must sit after the cache
  breakpoint, or it invalidates the cached tools+system prefix every turn"* (`SOLUTION_DESIGN.md:1808-1814`).
  The live code's existing insertion point already satisfies this — the fix slots into a correct structure.
- **📋 FR/NFR**: `NFR-002` (single-hop turn p95 < 2.5 s — this turn is three-inference, not single-hop),
  `NFR-004` (hop count as a first-class metric).
- **🚩 Wrong-optimisation flag**: `MAX_TOOL_ROUNDS = 6` (`run_assistant.py:33`) is generous enough that the
  missing prefetch never fails a test — it just costs a hop forever. This is the exact shape §10 warns
  about: *"a rise in average hops per turn will show up as a latency regression that no amount of
  infrastructure tuning will fix."*

### F2 — Lever #2: 23 tool schemas on every inference, not 12

- **⚠️ Needs improvement.** Confirmed by the AI-assistant pass (`COMPARISON-ai-assistant.md` §3); the
  latency consequence formalised here. 23 schemas (`tools.py:671-838`) are input tokens on **every** LLM
  call in the turn — with 3 inferences in the §2 trace, the surplus 11 schemas are paid **three times per
  turn**. §10's second cost is the one that compounds: a larger surface *"degrades selection accuracy,
  which causes extra hops"*, and each extra hop is two more inferences at full schema cost.
- **Interaction with lever #4, worth stating precisely**: the tool block sits in the cacheable prefix, so on
  a cache hit the *token cost* of the surplus schemas is discounted. The *selection-accuracy* cost is not
  discounted by anything. Shrinking the surface is therefore justified on hop count even if caching is
  working perfectly — which is the ordering §10 already encodes by putting lever 2 above lever 4.
- **Fix**: build the 12-tool allowlist from `SOLUTION_DESIGN.md` §7.5.4 in `build_driver_tools`; fold the 11
  extra reads into the F1 prefetch payload (which is where §7.5.4 says most of them belong) or a second-tier
  on-demand catalog.
- **📋 FR/NFR**: `NFR-004`; `NFR-002` transitively via hop count.
- **🚩 Wrong-optimisation flag**: `scheduling_capability_disabled` (`tools.py:632-645`) is bound alongside a
  fully working `reschedule_appointment_tool` — a schema whose entire purpose is to tell the model a
  capability doesn't exist, competing for selection against the tool that implements it. That is schema
  cost with negative accuracy value.

### F3 — Lever #3: no streaming anywhere, and the AgentCore caller opts *out* of it

- **⚠️ Needs improvement.** The AI-assistant pass confirmed the absence of SSE in `chat.py`,
  `run_assistant.py` and `agentcore_runtime.py`. This pass adds one thing that pass did not:
  `agentcore_runtime.py:83` passes **`accept="application/json"`** to `invoke_agent_runtime`. Even if
  `agentcore_main.py`'s entrypoint were changed to stream, the BFF caller has explicitly requested a
  non-streamed body, and then `agentcore_runtime.py:87-91` reads the whole body into memory
  (`stream.read()` / `b"".join(...)`) before `json.loads`. The streaming decision is negated at the
  transport layer as well as the handler layer — two independent changes are required, not one.
- **Fix**: (a) `run_assistant` grows a streaming variant using `llm.astream(...)` on the final inference
  and emitting explicit SSE events at tool-call boundaries — `astream_events` (`v2`, still the current
  default per LangChain's reference; `v3` is beta) is also available on any `Runnable`, but with no graph
  to introspect, `astream()` plus hand-emitted tool events is the smaller change for a bounded manual loop.
  (b) `chat.py` returns FastAPI's `EventSourceResponse` — now documented first-party in FastAPI's SSE
  reference rather than requiring `sse-starlette` directly. (c) `agentcore_runtime.py:83` switches to
  `accept="text/event-stream"` and re-emits chunks rather than joining them.
- **📋 FR/NFR**: `NFR-001` (TTFT p95 < 1.2 s) — **architecturally unreachable today**, since TTFT and
  full-turn time are the same number. `TECH_STACK.md` §9's frontend decision (SSE, PWA → `ap-south-1`
  directly, no CDN proxy) has no backend to talk to.
- **🚩 Wrong-optimisation flag**: `TECH_STACK.md` §9 spent real design effort resolving the assistant-ui
  runtime-adapter deferral and analysing the CDN-buffering risk to SSE. None of that has a line of code —
  while `DriverHome.tsx` invested in a bespoke `renderFormattedText` markdown parser (per
  `COMPARISON-frontend.md`) for a transcript that arrives all at once anyway.

### F4 — Lever #4: the cacheable prefix ordering is correct — a genuine ✅

- **✅ Meets the target.** This is the one lever the live code satisfies on the merits. Verified in
  `run_assistant.py`:
  - Tools are bound before any message is constructed (`:112`), so tool schemas lead the rendered prompt.
  - `SYSTEM_PROMPT` (`prompts.py:1-31`, a module-level constant, ~5,075 chars ≈ 1.2k tokens) is message 0
    and contains **no interpolation** — byte-identical every turn.
  - No tool description is an f-string (checked across all 23 registrations in `tools.py:671-838`), so the
    schema block is byte-stable too.
  - Volatile content starts at `:119` (summaries), `:128` (session context), then history, then the user
    message. That is `tools → system → [breakpoint] → volatile → history → message`, exactly §10 item 4.
- **The `json.dumps` at `:132` is *not* a defect, and this is worth stating so nobody "fixes" it.**
  `json.dumps(session_ctx, default=str)` has no `sort_keys=True`, and §10 item 5 names "an unsorted
  `json.dumps`" as a cache-killer by name. But it sits **after** the stable prefix, in the volatile zone,
  where the content changes every turn regardless. Caching is a prefix match; a volatile byte in the
  volatile section invalidates only what already changes. Adding `sort_keys=True` here would buy nothing.
  The rule is about position, not about the function.
- **Caveat (why this is ✅ and not "done")**: no explicit `cache_control` breakpoint exists anywhere. On the
  provider `AUTO_ORDER` actually selects today (OpenAI first, `llm.py:24`), that is fine — OpenAI's prompt
  caching is **automatic** with a 1,024-token minimum and best-effort prefix reuse on pre-GPT-5.6 models,
  no code changes required, and this prompt (23 schemas + 1.2k-token system message) clears that minimum
  comfortably. On a provider requiring manual breakpoints, the breakpoint must be inserted at the position
  the code already establishes.
- **📋 FR/NFR**: no NFR names prompt caching directly; it serves `NFR-001`/`NFR-002`.

### F5 — Lever #5: cache hit rate is never observed, so lever 4's ✅ is unverifiable in production

- **⚠️ Needs improvement.** `grep` across `backend/app/` for `cached_token`, `cache_read`, `usage_metadata`,
  `cache_control` → zero hits. `observability.py` records exactly two histograms — messages loaded and
  response length (`:26-39`) — neither of which is on §10's "What to measure" list (TTFT p50/p95,
  hop-count distribution, per-tool DB latency, LLM network-vs-inference split, cache hit rate, Redis RTT).
  **Not one of the six is instrumented.**
- **Fix**: read `response.usage_metadata` (LangChain surfaces the provider's
  `prompt_tokens_details.cached_tokens` / `input_tokens_details.cached_tokens` through it) after each
  `ainvoke` and record it, alongside a hop counter and a per-`ainvoke` wall-clock timer, into the metadata
  already being attached at `run_assistant.py:248-251`.
- **📋 FR/NFR**: `NFR-004` (**hop count tracked as a first-class metric**) is *stated* as a requirement and
  has **no implementation** — `tool_outcome_metadata` (`observability.py:67-92`) records tool *names* but
  never a count, a duration, or a round index. `NFR-025` (nested spans keyed to `chat_threads.thread_id`) is
  shape-present/nesting-unverified per the AI-assistant pass.
- **🚩 Wrong-optimisation flag**: `observability.py` measures `response_length` — characters returned — and
  `messages_loaded`. Neither is a latency signal. Effort went into instrumenting two quantities nobody has
  a budget for, while all six quantities §10 explicitly names as *"what to measure"* are unmeasured. This is
  the clearest case in this pass of optimising the measurable rather than measuring the important.

### F6 — Lever #6: `thinking_level: high` — recorded decision, not flagged

- **✅ Per the brief, and per `TECH_STACK.md` D-4a, this is not an oversight and is not flagged.** For
  completeness: the parameter is absent from `llm.py:127-131` entirely, which is a *different* condition
  from "set low" — and per `TECH_STACK.md` §7's spike table, `thinking_level` is `❌` at the pinned
  `langchain-google-genai 2.1.12` and `✅ native at 4.3.5`. So the D-4a decision is currently unimplementable
  rather than unimplemented, and it becomes settable as a side effect of the version fix the AI-assistant
  pass already owns (`COMPARISON-ai-assistant.md` §0). No separate action here.
- **📋 FR/NFR**: `TECH_STACK.md` §13 open item 1c (`thinking_level` head-to-head, unmeasured) remains open.

### F7 — Lever #7: parallel tool results returned in one message — a genuine ✅

- **✅ Meets the target.** `run_assistant.py:172-242` iterates every entry in `tool_calls` and appends each
  `ToolMessage` to `messages` inside that loop; the next `llm.ainvoke(messages, ...)` at `:252` happens only
  after the loop completes. All results from one parallel round are therefore present in a single
  continuation, never split across separate inference turns — which is the failure §10 item 7 describes
  (*"splitting them across messages silently teaches the model to stop calling tools in parallel"*).
- **One real deviation, worth naming**: `should_break_after_round` (`:229, 232, 238`) can be set mid-loop by
  one tool's result code, but the `break` is deferred to `:244-245` — after all sibling results have been
  appended. So even the early-exit path does not truncate a parallel round. That is correct and looks
  deliberate.
- **📋 FR/NFR**: `NFR-004` (hop count) — this lever protects it.

### F8 — Lever #8: telemetry **is** in the request path, and it blocks

- **⚠️ Needs improvement — this is the most concrete, most fixable per-turn cost found in this pass.**
  `observability.py:157-167`:

  ```python
  def observe_output(response_text: str) -> None:
      if response_length_metric is None:
          return
      response_length_metric.record(len(str(response_text)), COMMON_ATTRIBUTES)
      if metrics is not None:
          provider = metrics.get_meter_provider()
          if hasattr(provider, "force_flush"):
              try:
                  provider.force_flush()
  ```

  Called at `run_assistant.py:320` — after the answer is fully composed, **before** the `return` at `:322`.
  Verified against the vendored SDK source in this repo
  (`agentcore/.cache/SetuHaulAgent/staging/opentelemetry/sdk/metrics/_internal/__init__.py:584-598`):
  `force_flush(timeout_millis=10_000)` is a **synchronous loop over every metric reader**, calling each
  reader's own `force_flush` with the remaining deadline — a real collect-and-export, i.e. an OTLP network
  call, on the calling thread. It is a plain `def` invoked from a coroutine, so it blocks the event loop for
  every other in-flight request too.
- **Why this is the dangerous kind of defect, in this project's own taxonomy**: it is a **no-op in
  development and live in production.** The `try: from opentelemetry import metrics` at
  `observability.py:22-39` sets `response_length_metric = None` when the OTEL distro is absent — which is
  local uvicorn. The distro ships under the `agentcore` optional extra (`pyproject.toml`, `[project
  .optional-dependencies] agentcore`), i.e. exactly the AgentCore Runtime where driver chat actually runs.
  Same shape as `TECH_STACK.md` §7's API-key trap: *it works*, and silently costs.
- **Fix**: delete the `force_flush()` block. `PeriodicExportingMetricReader` already exports on its own
  interval; a per-turn forced flush buys nothing a 60-second export interval doesn't. If a flush is genuinely
  needed, do it on process shutdown, not per turn.
- **📋 FR/NFR**: `NFR-013` (*LangSmith never blocks a turn — bounded queue, drop rather than block*). The
  NFR names LangSmith specifically; LangSmith is plausibly compliant here via SDK background batching (per
  `COMPARISON-ai-assistant.md` §6). **The OTEL/CloudWatch path is the one violating the NFR's actual
  intent, and no NFR names it.** Recommend widening `NFR-013` to "no telemetry backend blocks a turn."
- **🚩 Wrong-optimisation flag**: this is effort spent making a *metric* reliable at the cost of the
  *product's* latency budget — flushing a response-length histogram (see F5: not a latency signal) with a
  10-second blocking ceiling on a path with a 2.5-second budget.
- **Second-order effect on measurement**: `chat_turn_trace`'s `with` block closes at `run_assistant.py:259`
  — **before** `append_turn` (`:300`), `maybe_summarize_history` (`:312`) and `observe_output` (`:320`). So
  the three most expensive tail operations, including an entire extra LLM inference (F9), fall **outside**
  the per-turn LangSmith parent run. Hop count as observed in LangSmith (`NFR-004`, `NFR-025`) will
  systematically undercount. Fix: move the tail work inside the context manager, or close the trace last.

### F9 — The summariser: a full extra LLM inference on the driver's request path

- **⚠️ Needs improvement — not covered by any prior pass, and larger than most levers.**
  `run_assistant.py:312-318` **awaits** `memory.maybe_summarize_history(...)` after the answer is composed
  but before it is returned. Inside (`redis_memory.py:463-497`), once `known_message_count >=
  RAW_MESSAGE_LIMIT` (10, `:18`), it performs:
  - `lrange` — 1 Upstash HTTPS round trip (`:472`),
  - `await llm.ainvoke([...])` — **a full extra LLM inference** (`:481-486`),
  - `rpush`, `ltrim`, `expire`, `ltrim`, `expire` — **5 more, un-pipelined**, HTTPS round trips
    (`:492-497`), in a file that elsewhere correctly pipelines (`:272-276`, `:336-344`).

  History is trimmed to 5 (`SUMMARY_CHUNK_SIZE`) each time it crosses 10, and each turn appends 2 messages,
  so this fires roughly **every third turn** once a conversation is established. On that turn the driver
  waits for a 4th inference and 6 extra Upstash round trips **after their answer already exists in memory**.
- **Estimated from shape, not measured**: using the project's own spike figure of 1.86 s for a bare
  `ChatGoogleGenerativeAI` call, a summarising turn adds roughly **+1.9 s** to a budget (`NFR-002`) of
  2.5 s — i.e. the housekeeping alone can consume ~75% of the whole-turn budget on one turn in three.
- **Fix**: three changes, in order of payoff. (1) Do not await it — dispatch with
  `asyncio.create_task(...)`, or better, move it out of the request entirely (it is pure memory hygiene,
  not part of the answer). (2) Pipeline the five trailing writes the way `append_turn` already does. (3)
  Consider whether a 40-message-capped, 24-hour-TTL history needs LLM summarisation at all at this scale —
  `HISTORY_LIMIT = 40` (`:14`) already bounds the context; `RAW_CONTEXT_SIZE = 5` (`:19`) means only the
  last 5 turns reach the prompt anyway (`run_assistant.py:99`).
- **📋 FR/NFR**: `NFR-002` directly. `NFR-004` — this inference is invisible to hop count both because it
  is not a tool hop and because it falls outside the trace (F8).
- **🚩 Wrong-optimisation flag**: the summariser exists to control context-window cost. But
  `run_assistant.py:99` already slices history to the last **5** messages before building the prompt, and
  `:126` truncates the summary block to 3,000 chars. The token saving is therefore small and bounded — a
  handful of messages — while the cost is a full extra inference on the roadside driver's critical path.
  This is the clearest instance in the codebase of optimising token cost against the wrong budget: `NFR-002`
  is a *latency* NFR, and there is no token-cost NFR anywhere in `REQUIREMENTS.md` to trade it against.

### F10 — Lever #9a: Upstash over REST/HTTP, not the native protocol

- **⚠️ Needs improvement.** Verified from the installed package, not from memory. `redis_memory.py:75-77`
  imports `from upstash_redis import Redis`. The installed class's own docstring
  (`.venv/Lib/site-packages/upstash_redis/client.py:16-19`) reads: *"A Redis client that uses the Upstash
  **REST API**."* Its transport (`upstash_redis/http.py:42-95`) is `httpx.Client.post` per command batch.
  `backend/uv.lock:2629-2637` confirms `upstash-redis 1.7.0` with an `httpx` dependency; **`redis-py` is
  not in the lockfile at all**, despite `TECH_STACK.md` §1 naming `redis-py` as a primary dependency and
  §3/Decisions-at-a-glance specifying *"native protocol over persistent connection"*.
- **The cost is worse than the doc's estimate, for a reason the doc didn't anticipate.** Appendix A budgets
  *"per-call TLS setup … tens of milliseconds on every turn — twice, since you read at turn start and write
  at turn end"* (`SOLUTION_DESIGN.md:1818-1820`). `SyncHttpClient.__init__` does create a persistent
  `httpx.Client` (`http.py:54`), which would amortise TLS across calls — **but `ConversationMemory` is
  constructed fresh on every turn** (`run_assistant.py:74`, and again per request in `chat.py:34`), so a new
  `Redis` → new `SyncHttpClient` → new `httpx.Client` → new connection pool is built each time. The TLS
  handshake is paid on the first call of every turn regardless. Appendix A's "twice per turn" estimate holds
  in practice, by accident of object lifetime rather than by transport design.
- **Two further verified defects in the same object**: (a) `httpx.Client(timeout=None)` (`http.py:54`) —
  **no timeout at all**. A hung Upstash connection blocks the driver's turn indefinitely; the careful
  `degraded`/`degrade_reason` fallback in `redis_memory.py` only fires on an *exception*, and with
  `timeout=None` there is none to fire. (b) The **synchronous** client is used inside `async def
  run_assistant` with no `await` and no threadpool, so each call blocks the whole event loop — and
  `upstash_redis.asyncio.Redis` (`AsyncHttpClient`, `http.py:112-166`) exists and is not used.
- **Fix**, in order: (1) switch to `redis-py` (`redis.asyncio`) against Upstash's native TLS endpoint with a
  module-level, process-lifetime client — this closes the transport, the per-turn handshake and the
  event-loop blocking in one change; (2) failing that, at minimum move to `upstash_redis.asyncio.Redis`,
  hoist the client to module scope so it outlives a turn, and set a real timeout.
- **📋 FR/NFR**: `NFR-012` (Redis loss is survivable — next turn answers correctly from Postgres) is
  **weakened by `timeout=None`**: the degradation path is unreachable for a hang, only for a reset.
  `NFR-016` (sustain the spike, 5 concurrent coordinators) is threatened by the event-loop blocking.
- **✅ Genuinely good, and worth keeping**: the pipelining in `load_turn_context` (`:272-276`) and
  `append_turn` (`:336-344`), and the `known_message_count` parameter (`:448, 464-468`) that avoids a
  separate `LLEN` round trip. Those comments (`run_assistant.py:76-77, 309-311`) show someone already
  counted round trips deliberately. That instinct is right; it was applied to the wrong layer, because the
  transport underneath is still HTTP.

### F11 — Lever #9b: tool DB reads are not batched — the exact anti-pattern §3 names

- **⚠️ Needs improvement.** `TECH_STACK.md` §3 specifies: *"Tool reads: **Batched** — one query returning
  driver + shipment + appointment + latest ETA … Four sequential 5 ms round trips are serial inside the
  tool, so they stack."* `driver_reads.get_driver_operational_context` issues **five** sequential
  `await session.execute(...)` calls — drivers (`:29`), shipments (`:43`), appointment (`:66`), facility
  (`:83`), latest ETA (`:94`). The last three are mutually independent and each depends only on
  `primary["shipment_id"]` / `primary["destination_facility_id"]`, already in hand. This is the doc's own
  worked example, present in code, one query worse than the version the doc warns about.
- **The N+1 shape repeats across the driver tool surface**: `get_latest_eta` (`:163`), `get_eta_history`
  (`:190`), `get_current_appointment` (`:217`), `get_gate_and_queue_status` (`:387`),
  `get_facility_rules_and_restrictions` (`:419`), `report_vehicle_breakdown_or_incident` (`:486`) each open
  with `await get_shipment_details(...)` purely as a **scope check** — a full 23-column `SELECT` on
  `shipments` (`:133-148`) before the query the tool actually wants. Every one of those tools therefore
  costs **2+ sequential round trips minimum**, one of which returns data that is thrown away.
- **This is the latency face of the routers/services pass's finding.** `COMPARISON-backend-routers-services.md`
  §5 identified scope-checking duplicated four ways. Two of those four cost a redundant round trip:
  (a) the `get_shipment_details`-as-scope-guard pattern above, and (b) `driver.py:20-127`'s `/driver/context`
  endpoint re-executing `driver_reads.get_driver_operational_context`'s four queries inline instead of
  calling the service — same five round trips, second copy, so any batching fix must be applied twice or the
  duplication removed first. Recommendation: **fix the duplication first (routers/services pass), then
  batch once.**
- **Fix**: replace the five queries with one statement using `LEFT JOIN LATERAL` for the per-shipment
  appointment and latest-ETA sub-selects. **Do not use `asyncio.gather` on the shared session** — verified
  against current SQLAlchemy docs, *"a single instance of `AsyncSession` is not safe for use in multiple,
  concurrent tasks"*, and concurrent tasks require a separate session each. With `pool_size=3` (F12) opening
  extra sessions to parallelise is actively harmful. Batching into one statement is both the doc's
  prescription and the only safe option here.
- **📋 FR/NFR**: `NFR-002`; `NFR-020` (scope enforced in the repository layer) — a shared
  `assert_shipment_scope(ctx, row)` helper is what removes the redundant `SELECT`, so the `NFR-020` cleanup
  and the latency fix are the same change.
- **🚩 Wrong-optimisation flag**: none — this is under-built, not over-built. The instinct is visible
  elsewhere (`redis_memory`'s pipelining, F10) and simply was not applied to Postgres.

### F12 — Connection pooling: correct sizing, wrong hold duration — it hurts the per-turn picture

The core/scheduling/db pass marked `db/session.py` **Keep as-is** and was right about what it examined —
`pool_size=3, max_overflow=2` and `statement_cache_size=0` are evidence-based responses to two reproduced
incidents (`db/session.py:30-53`). The per-turn *latency* question that pass did not ask has a different
answer.

- **✅ Where pooling helps**: connections survive across turns, so a driver turn does **not** pay a Postgres
  TCP+TLS handshake. Given a Supavisor session-mode connection, that is a real saving on every turn and it
  is correctly implemented. Keep.
- **⚠️ Where it hurts, precisely**: `get_db_session` (`deps.py:73-81`) is a bare `async with
  db.session_factory() as session: yield session` with **no commit and no rollback**. Verified against
  current SQLAlchemy documentation: a `Session` acquires a connection *when it first needs to communicate
  with the database*, autobegins a transaction on a plain `SELECT`, and holds that connection *"throughout
  the active transaction"* until commit/rollback/close. The first query on a driver turn is the identity
  lookup at `deps.py:97-111`. Nothing in the chat path ever commits (confirmed by the routers/services
  pass). Therefore: **one pooled connection is checked out and one Postgres backend sits idle-in-transaction
  for the full duration of the LLM turn** — 7.40 s on the project's own measured 4-hop figure.
- **The concrete consequence**: with `pool_size=3, max_overflow=2` = 5 connections per process, the **sixth
  concurrent driver turn blocks on `pool_timeout` (SQLAlchemy default 30 s)** — waiting not on a query but
  on somebody else's LLM inference. `NFR-016` requires sustaining 20–35 requests in a 30-minute spike with
  5 concurrent coordinators; `NFR-017` is 190–240 appointments/day. The pool is sized for *query*
  concurrency and is being consumed at *LLM* concurrency.
- **It is worse in AgentCore mode.** When `agentcore_enabled` (`settings.py:59-60`), `chat.py:52` routes to
  `invoke_agentcore` and the FastAPI-side session is used for **exactly one query** (the identity lookup)
  and then held, unused and idle-in-transaction, for the entire remote turn. A scarce connection is burned
  for nothing.
- **Fix** (none of which touches the sizing, which is correct): (a) make `get_db_session` `await
  session.rollback()` in a `finally` — or better, restructure so read-only paths close the transaction as
  soon as the identity lookup completes, releasing the connection before the LLM call; (b) in AgentCore
  mode, do not hold a session across `invoke_agentcore` at all — resolve the `ExecutionContext`, release,
  then invoke; (c) note `pool_pre_ping=True` (`:29`) costs one extra round trip per checkout, which is the
  right trade when a checkout serves a whole turn, and would be the wrong trade if (a) makes checkouts
  short and frequent — revisit it *after*, not before.
- **📋 FR/NFR**: `NFR-016`, `NFR-017`; `NFR-011` (Postgres fails loudly) is unaffected.
- **🚩 Wrong-optimisation flag**: pool sizing was tuned against a *connection-budget* incident (correct) and
  has never been examined against *hold duration* (the actual per-turn constraint). Tuning `pool_size` up
  would reproduce the 2026-08-17 `EMAXCONNSESSION` incident the comment describes; the fix is to shorten the
  hold, not to widen the pool. Stating this explicitly so a future reader does not "fix" the queueing by
  raising `pool_size`.

### F13 — A blocking JWKS fetch on every single authenticated request

- **⚠️ Needs improvement — not covered by any prior pass.** `deps.py:69-70` constructs a **new**
  `JwtVerifier(settings)` per request (a plain function dependency; FastAPI's dependency cache is
  per-request only). `JwtVerifier.__init__` (`security.py:18-21`) sets `self._jwks_client = None`, so the
  1-hour freshness guard at `security.py:24` can never be satisfied — a fresh `PyJWKClient` is built on
  every request (`:32`). Verified from the installed library: `PyJWKClient`'s JWK-Set cache is a
  **per-instance** `JWKSetCache` (`.venv/.../jwt/jwks_client.py:84-98`) and `fetch_data` uses
  **`urllib.request.urlopen`** (`:118`) — a blocking, synchronous HTTPS request with no connection reuse.
- **Counted cost**: **one full HTTPS round trip with a fresh TLS handshake, blocking the event loop, on
  every authenticated request**, before any application work begins. **Estimated from shape**: ~30–80 ms
  in-region; ~200 ms+ if compute is not co-located with Supabase (see F14). This is pure, avoidable,
  100%-of-turns cost sitting ahead of the whole budget.
- **Fix**: make the verifier process-scoped — `@lru_cache` on `get_jwt_verifier` (it takes only `Settings`,
  which is itself already `lru_cache`d), or a module-level singleton. The 1-hour rotation logic already
  written at `security.py:24` then starts working as intended, and `PyJWKClient`'s own 300-second
  `cache_jwk_set` TTL begins to apply. One-line change, removes a network round trip from every request.
- **📋 FR/NFR**: `NFR-001`, `NFR-002` (fixed overhead on every turn); `NFR-016` (event-loop blocking under
  concurrency).
- **🚩 Wrong-optimisation flag**: `security.py:24` implements a careful hourly JWKS-refresh policy with an
  explicit `_jwks_fetched_at` timestamp — real thought about key rotation — that is **dead code**, because
  the object holding the timestamp never survives a request. Effort spent on cache-invalidation correctness
  for a cache that never has a hit.

### F14 — Co-location: the region argument the whole budget rests on is not implemented anywhere

Consolidating what prior passes established, with the latency consequence stated:

| Component | `TECH_STACK.md` decision | Live state | Evidence |
|---|---|---|---|
| Supabase Postgres | `ap-south-1` | **✅ Confirmed** `ap-south-1` | §13 item 3, verified 2026-08-21 via Supabase MCP |
| Upstash Redis | `ap-south-1`, native protocol | Region ✅ `ap-south-1` (§13 item 4, **Global replication** flagged); transport ❌ REST (F10) | §13 item 4 |
| Compute (AWS) | `ap-south-1` | ❌ `aws_region: str = "us-east-1"` | `core/settings.py:48`; `agentcore_main.py:47` independently defaults to `"us-east-1"` |
| Model | Vertex AI `asia-south1`, ADC + explicit `location` | ❌ **Never reaches Vertex.** AI-Studio API key, no `location`, no ADC, and Gemini is **last** in `AUTO_ORDER` | `assistant/llm.py:24, 127-131` |

- **⚠️ Needs improvement.** Appendix A's rule — *"Compute, Postgres and Redis go in one region. Only the
  model may be remote"* (`SOLUTION_DESIGN.md:1727`) — is currently inverted in the worst possible way: if
  `AWS_REGION` is not explicitly set, **compute defaults to `us-east-1` while Postgres and Redis are in
  `ap-south-1`**, so the *chatty* tier is split across regions and the model hop is remote too. Appendix A's
  own arithmetic: tool→DB is many round trips, LLM is one per iteration; splitting the chatty tier is the
  single most expensive mistake available. Applied to the §2 trace: **9 sequential DB round trips + 3 Upstash
  round trips at a ~200 ms Mumbai↔Virginia RTT ≈ 2.4 s of pure network per turn**, against `NFR-002`'s 2.5 s
  whole-turn budget — the budget is consumed before a single token is generated. (Estimated from counted
  round trips × the RTT figure in `TECH_STACK.md` §7's own table, not measured.)
- **On the Vertex region question specifically** (`TECH_STACK.md` §13 item 1a, *"the single largest latency
  variable left"*): this pass confirms Google's own published guidance that §7 cites — *"don't use the
  global endpoint if you have ML processing requirements, because you can't control or know which region
  your ML processing requests are sent to."* So §7's premise holds. This pass did **not** independently
  confirm that `asia-south1` is a supported Gemini regional endpoint serving in-region ML processing — the
  documentation page for that was not retrievable in this pass, and one search result raised a caveat that
  Google's formal ML-data-location commitment is scoped to US and EU locations. **Recording that as an open
  question rather than answering it.** It does not change the finding, because the live code takes neither
  path: `llm.py:127-131` calls `ChatGoogleGenerativeAI(..., google_api_key=...)` — the Gemini **Developer
  API**, not Vertex at all — and only if no OpenAI key is present.
- **Fix**: default `aws_region` to `"ap-south-1"` in `settings.py:48` and `agentcore_main.py:47` (fail toward
  the decided region, not AWS's historical default), and **assert the resolved endpoint region at startup**,
  which §7 explicitly instructs and which no code does. Resolve §13 item 1a before writing the Vertex path.
- **📋 FR/NFR**: `NFR-001`, `NFR-002`. Note that **no `NFR-*` states the co-location requirement itself** —
  it is stated only as prose in Appendix A and `TECH_STACK.md` §2/§11. Recommend a new NFR: *"compute,
  Postgres and Redis resolve to the same region; asserted at startup."* Without one there is nothing for a
  test to fail on.
- **🚩 Wrong-optimisation flag**: `redis_memory.py`'s pipelining (F10) shaves 3–4 Upstash round trips per
  turn — real, careful work. If compute is in `us-east-1`, that saving is ~600 ms of a ~2.4 s network bill
  that a one-line region default would remove entirely. Micro-optimising round-trip *count* while the
  round-trip *distance* is wrong by a continent is the textbook version of this flag.

### F15 — Event-loop blocking makes `NFR-016` unmeetable independent of any per-turn number

- **⚠️ Needs improvement.** Three blocking calls sit inside `async def` handlers with no `await` and no
  threadpool offload:
  1. `urllib.request.urlopen` for JWKS — **every request** (F13).
  2. `httpx.Client.post` for **every** Upstash command — 3 per turn, 9 on a summarising turn (F10).
  3. `MeterProvider.force_flush()` — every turn, up to a 10-second deadline (F8).
  4. **And, in AgentCore mode, the whole turn**: `client.invoke_agent_runtime(...)`
     (`agentcore_runtime.py:78-85`) is a synchronous botocore call, awaited by nothing, inside `async def
     invoke_agentcore`. With `read_timeout=180` (`:75`), a single driver turn can block the event loop for
     up to **three minutes**. In this mode the BFF process serves **one driver at a time**, regardless of
     worker count.
- **📋 FR/NFR**: `NFR-016` (20–35 requests / 30 min, 5 concurrent coordinators) — not reachable on a single
  worker while (4) holds. `NFR-018` (anti-requirement: no horizontal scaling before a measured bottleneck)
  is relevant here in the *right* direction: the correct fix is to unblock the loop, **not** to add workers
  to paper over it.
- **Fix**: `redis.asyncio` (F10); process-scoped verifier plus an async JWKS fetch or a threadpool offload
  (F13); delete the flush (F8); and for AgentCore either `aioboto3`/`asyncio.to_thread` or — better —
  `accept="text/event-stream"` with an async streaming read (F3), which fixes streaming and blocking with
  one change.
- **🚩 Wrong-optimisation flag**: `agentcore_runtime.py:72-76` also constructs a **new boto3 client per
  turn**. Verified against current AWS guidance: clients are thread-safe to *use* but expensive to *create*
  and are meant to be reused; instantiation is the part that is not thread-safe. Each construction also
  builds a new connection pool → a fresh TLS handshake to the AgentCore endpoint every turn. Hoist to module
  scope. Note the same file gets one thing exactly right: `retries={"max_attempts": 0}` (`:75`) means no
  hidden retry multiplication — **keep that**.

### F16 — `find_feasible_slots` and `NFR-003`: the < 50 ms budget is structurally unmeetable, not merely unoptimised

This is the finding the brief asked to be cross-referenced with the core/scheduling/db pass's confirmation
that `dock_occupancy` and its GiST index do not exist. The situation is worse than "the index isn't there
yet."

- **⚠️ Needs improvement.** `feasibility.py:396-422` is the candidate query. Its predicate and its sort are
  both **structurally un-indexable as written**:

  ```sql
  WHERE sl.facility_id = :facility_id
    AND CAST(sl.slot_end_ts AS timestamptz) > :eta_ts
  ORDER BY CAST(sl.slot_start_ts AS timestamptz), sl.slot_id
  LIMIT 200
  ```

  - `appointment_slots.slot_start_ts` / `slot_end_ts` are **`TEXT`**
    (`supabase/migrations/20260805201923_setuhaul_baseline.sql:143-144`), confirmed unchanged by the
    core/db pass.
  - The only relevant index is `ix_slots_facility_time ON appointment_slots(facility_id, slot_start_ts,
    slot_end_ts)` (`:443-444`) — a b-tree over **text**. It can serve `facility_id =`; it **cannot** serve
    `CAST(slot_end_ts AS timestamptz) > :param`, because that is an expression, not a column.
  - Nor can the cast be dropped to use the index: migration
    `20260811233000_fix_v_latest_eta_timestamptz_order.sql` documents the reason in its own header — *"Seed
    uses +05:30; app writes often use +00:00 UTC. Text DESC picks the wrong row when dates collide."*
    Lexicographic text ordering is **not** chronological ordering in this data.
  - Nor can an expression index rescue it: verified against Postgres guidance, index expressions must be
    `IMMUTABLE`, and a `text → timestamptz` cast is not — it depends on the session `TimeZone` setting.
    `CREATE INDEX ... ON appointment_slots (CAST(slot_end_ts AS timestamptz))` will be **rejected by
    Postgres**.

  So the query must sort every candidate row for the facility on each call, and no index can be added to
  prevent it **while the columns remain `TEXT`**. `TASKS.md` Phase 1.4 (`text → timestamptz`) is therefore
  not only a correctness prerequisite for D1 — it is the precondition for `NFR-003` being *achievable at
  all*, not just for it being fast.
- **Plus 3 sequential round trips before the candidate query even runs**: shipment ⋈ `v_latest_eta`
  (`:332`), facility (`:361`), current appointment (`:377`). All three are independent lookups that a single
  statement could return. Same batching prescription as F11.
- **Honest sizing, so this is not overstated**: at today's seeded volume (a few hundred slots per facility)
  the sort is small and `NFR-003` is very likely met by accident of data size. At D8's target of 2,000–3,000
  slots it degrades, and — the load-bearing point — it degrades with **no indexing remedy available**. The
  correct framing is "currently passing for a reason that will stop being true, with the fix blocked behind
  Phase 1," not "currently failing."
- **📋 FR/NFR**: **`NFR-003`** (`find_feasible_slots` < 50 ms — note: the brief cited this as `NFR-002`;
  the correct ID is `NFR-003`, `REQUIREMENTS.md:305`). `NFR-006`/`NFR-008` depend on the same Phase 1
  migration for correctness, per the core/db pass.
- **🚩 Wrong-optimisation flag** — this is the one worth being blunt about. The core/db pass flagged the
  *"200-row candidate cap with an in-Python loop"* as the `NFR-003` risk. On the latency evidence that is
  the wrong target: 200 rows of Python `datetime` parsing and arithmetic is a low-single-digit-millisecond
  cost. The real costs are (a) the un-indexable cast above and (b) the 4 sequential round trips. And all
  three of those, together, are a **rounding error against the 3 LLM inferences in the same turn** (§2).
  Optimising the feasibility engine before deleting a tool hop (lever #1) would be exactly the inversion
  §10's ordering exists to prevent. `NFR-003` should be fixed **because Phase 1 has to happen anyway**, not
  because it is the bottleneck. It is not the bottleneck.

### F17 — No timeout ceiling anywhere on the LLM path, and no wall-clock bound on the turn

- **⚠️ Needs improvement.** `llm.py:127-140` passes **no** `timeout` and **no** `max_retries` to either
  provider. Verified from the installed SDK: `openai._constants.DEFAULT_TIMEOUT =
  httpx.Timeout(timeout=600, connect=5.0)` and `DEFAULT_MAX_RETRIES = 2`, and
  `langchain_openai.ChatOpenAI` leaves `request_timeout`/`max_retries` unset by default
  (`.venv/.../langchain_openai/chat_models/base.py:468, 487`) so the SDK defaults apply. So a single
  inference can consume up to ~600 s × 3 attempts, and `MAX_TOOL_ROUNDS = 6` (`run_assistant.py:33`) permits
  up to **7 inferences per turn**. There is no wall-clock budget check anywhere in the loop.
- The core/db pass found `core/middleware.py` empty relative to `SYSTEM_DESIGN.md` §6's breaker/bulkhead/
  timeout/retry requirements and asked the `app/assistant/` owner to confirm whether that machinery lives
  elsewhere. **Answer, for the record: it does not.** There is no circuit breaker, no bulkhead, no
  concurrency cap and no derived timeout in `app/assistant/` either. §6.5's ~800 ms–1 s per-call ceiling has
  no counterpart in code.
- **Fix**: set an explicit `timeout` on the model client sized against `NFR-002` (a per-call ceiling in the
  1–2 s range, per §6.5), set `max_retries=0` or 1 with jitter, and add a turn-level deadline that breaks
  the loop and returns a typed degraded response rather than running to `MAX_TOOL_ROUNDS`.
- **📋 FR/NFR**: `NFR-002` (a turn with no ceiling cannot have a p95 guarantee), `NFR-014` (LLM provider
  failure trips a circuit breaker to the fallback — no breaker exists; `AUTO_ORDER` is evaluated once at
  model-build time, not at failure time, per the AI-assistant pass).

---

## 5. NFR coverage — latency and load

| NFR | Requirement | Live state | Blocking cause |
|---|---|---|---|
| `NFR-001` | TTFT p95 < 1.2 s | **Unreachable** | No SSE anywhere (F3); TTFT ≡ full-turn time |
| `NFR-002` | Single-hop turn p95 < 2.5 s | **Not met, and the turn is not single-hop** | F1 (missing prefetch), F9 (extra inference), F13/F14 (fixed overhead), F17 (no ceiling) |
| `NFR-003` | `find_feasible_slots` < 50 ms | Probably met today by data size; **structurally unfixable when it stops being met** | F16 (TEXT columns → un-indexable cast); blocked behind `TASKS.md` Phase 1.4 |
| `NFR-004` | Hop count tracked as a first-class metric | **No implementation** | F5 — nothing counts hops; F8 — the trace closes before the tail work |
| `NFR-012` | Redis loss survivable | Partially — degradation path exists but is unreachable for a hang | F10 (`timeout=None`) |
| `NFR-013` | Telemetry never blocks a turn | **Violated by the OTEL path** (NFR names LangSmith only) | F8 |
| `NFR-014` | LLM failure trips a breaker to the fallback | **No implementation** | F17 |
| `NFR-016` | Spike: 20–35 req / 30 min, 5 concurrent | **Not reachable on one worker** | F15 (event-loop blocking), F12 (pool held at LLM duration) |
| `NFR-017` | 190–240 appointments/day | Not the binding constraint at this scale | — |
| `NFR-018` | Anti-requirement: no scaling before a measured bottleneck | ✅ respected — and it argues *for* the fixes here, against adding workers | — |
| `NFR-025` | Thread-scoped nested spans on `chat_threads.thread_id` | Shape present, nesting unverified (AI-assistant pass); **tail work falls outside the trace** | F8 |
| — | **Co-location of compute + Postgres + Redis** | ❌ Compute defaults to `us-east-1` | **No NFR exists — recommend creating one** (F14) |

---

## 6. Remediation order — by payoff, not by file

Ordered the way §10 orders levers: cost of the fix against inferences and round trips removed per turn.

| # | Change | Removes per turn | Effort |
|---|---|---|---|
| 1 | Default `aws_region` to `ap-south-1` + assert resolved region at startup (F14) | Up to ~2.4 s of network, estimated, if compute is currently mis-regioned | 2 lines + an assertion |
| 2 | Delete `provider.force_flush()` (F8) | 1 blocking OTLP export, up to a 10 s ceiling | Delete 6 lines |
| 3 | Process-scope `JwtVerifier` (F13) | 1 blocking HTTPS + TLS handshake, **every request** | 1 decorator |
| 4 | Stop awaiting `maybe_summarize_history` (F9) | 1 full LLM inference + 6 HTTPS round trips, on ~1 turn in 3 | 1 line (`create_task`) |
| 5 | Prefetch `get_driver_operational_context` (F1) | **1 tool hop = 2 LLM inferences** + 5 DB round trips | ~10 lines |
| 6 | Shrink the tool surface to 12 (F2) | Schema tokens × every inference; fewer mis-selections → fewer hops | Filter one list |
| 7 | Batch `get_driver_operational_context` into one statement (F11) | 4 of 5 sequential DB round trips | One SQL rewrite (after the routers/services de-duplication) |
| 8 | Release the DB session before the LLM call / in AgentCore mode (F12) | Unblocks concurrency; no per-turn latency change | Restructure one dependency |
| 9 | `redis-py` async, module-scoped client (F10) | Per-turn TLS handshake ×1; unblocks the event loop | Dependency swap |
| 10 | SSE end-to-end (F3) | Does not reduce total time; **makes `NFR-001` exist at all** | Largest change here |
| 11 | Explicit LLM timeout + turn deadline (F17) | Bounds the tail; no p50 change | Config + one check |
| 12 | Instrument §10's six measurements (F5) | Nothing — **but nothing above can be verified without it** | Moderate |

Items 1–4 are, together, roughly a dozen lines of code and remove more per-turn latency than every other
item on the list. None of them appears in any prior pass's findings, because none of them is a correctness
or architecture defect — they are only visible when the axis is latency.

---

## Sources consulted this pass

Verified rather than recalled. Installed-package citations are to files in this repository.

- Installed `upstash_redis` 1.7.0 — `backend/.venv/Lib/site-packages/upstash_redis/client.py:16-19`
  (*"uses the Upstash REST API"*), `.../upstash_redis/http.py:42-95, 112-166` (sync/async `httpx`
  transport, `timeout=None`)
- Installed `PyJWT` — `backend/.venv/Lib/site-packages/jwt/jwks_client.py:18-98, 106-118`
  (per-instance `JWKSetCache`, `urllib.request.urlopen`)
- Installed `openai` — `backend/.venv/Lib/site-packages/openai/_constants.py:9-10`
  (`DEFAULT_TIMEOUT=600s`, `DEFAULT_MAX_RETRIES=2`); installed `langchain_openai`
  `chat_models/base.py:468, 487`
- Vendored OpenTelemetry SDK — `agentcore/.cache/SetuHaulAgent/staging/opentelemetry/sdk/metrics/_internal/__init__.py:584-598`
  (`force_flush` is a synchronous per-reader loop, default 10,000 ms)
- [SQLAlchemy 2.0 — Session Basics: connection acquired on first use, held for the active transaction](https://docs.sqlalchemy.org/en/20/orm/session_basics.html)
- [SQLAlchemy 2.0 — asyncio extension: `AsyncSession` is not safe for concurrent tasks; use one session per task](https://docs.sqlalchemy.org/en/20/orm/extensions/asyncio.html)
- [OpenAI — Prompt caching: automatic, 1,024-token minimum, exact prefix match, `cached_tokens` in usage; static content first, variable content last](https://developers.openai.com/api/docs/guides/prompt-caching)
- [FastAPI — Custom Response / StreamingResponse, and first-party `EventSourceResponse` / `ServerSentEvent` SSE reference](https://fastapi.tiangolo.com/advanced/custom-response/)
- [LangChain reference — `Runnable.astream_events`: `v2` is the default; `v3` is beta](https://reference.langchain.com/python/langchain-core/runnables/base/Runnable/astream_events)
- [Google Cloud — Vertex AI locations / data residency: the global endpoint does not support data-residency requirements; *"don't use the global endpoint if you have ML processing requirements"*](https://docs.cloud.google.com/vertex-ai/generative-ai/docs/learn/data-residency)
- [boto3 — low-level clients: clients are thread-safe to use but expensive to create; reuse rather than re-instantiate](https://boto3.amazonaws.com/v1/documentation/api/1.19.0/guide/clients.html)
- [PostgreSQL — index expressions must be `IMMUTABLE`; timezone-dependent casts are not](https://www.postgresql.org/message-id/1012707.1621880687@sss.pgh.pa.us)

Prior passes built on rather than re-derived: `COMPARISON-architecture.md`,
`COMPARISON-backend-routers-services.md`, `COMPARISON-backend-core-scheduling-db.md`,
`COMPARISON-frontend.md`, `COMPARISON-ai-assistant.md`.

---

*Compiled 2026-08-22. No files under `backend/`, `frontend/`, or `supabase/` were modified. Per the
`AGENTS.md` exemption for `docs/New-Solution-New-Design/`, no `CHANGELOG.md`/`wiki/` writeback accompanies
this document.*
