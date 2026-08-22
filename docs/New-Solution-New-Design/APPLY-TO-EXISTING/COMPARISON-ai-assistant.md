# Comparison — AI assistant / agentic loop (Phase 0 of TASKS.md)

> Scope: `SOLUTION_DESIGN.md` §7.2b/§7.5.4, `TECH_STACK.md` §7/§8, `DEPLOYMENT.md` §2 against the live
> `backend/app/assistant/{agentcore_main,agentcore_runtime,llm,observability,prompts,run_assistant,tools}.py`,
> `backend/app/api/v1/routers/chat.py`, `backend/pyproject.toml`/`backend/uv.lock`, and the
> `agentcore/codezip/app/` staged copy, as read on this pass (2026-08-22). Comparison only — nothing under
> `backend/` was edited. Every version/behavior claim below was checked against current external sources
> (PyPI, GitHub issues, LangSmith docs) rather than asserted from memory — sources cited inline.

Tags used per finding: **Keep** (matches the locked decision or is defensible) · **Fix** (diverges from
`TECH_STACK.md` §7 / current verified behavior, with a concrete remedy) · **FR/NFR** (requirement mapping,
or "none yet") · **⚠️ Flag** (the `thought_signature`-class trap — passes a shallow check, breaks the real
loop — or effort spent on something the "no agent framework" constraint rules out).

---

## 0. The version question, answered first — it decides almost everything else

`backend/pyproject.toml` line 18: `"langchain-google-genai>=2.0.0,<3.0.0"`. `backend/uv.lock` resolves this
to **`langchain-google-genai==2.1.12`** (lines 872-873). The identical pin ships to AgentCore:
`agentcore/codezip/requirements.txt` line 12 and `agentcore/codezip/pyproject.toml` line 22 both carry the
same `>=2.0.0,<3.0.0` constraint. There is no `langgraph` and no `google-genai` (the consolidated Vertex
SDK) anywhere in `backend/uv.lock` — only `google-ai-generativelanguage` (the AI-Studio/API-key wire
format), pulled in as `langchain-google-genai`'s own dependency (uv.lock lines 872-880).

**This is exactly the version `TECH_STACK.md` §7's own spike names as broken for multi-turn tool loops**:
"at the installed `langchain-google-genai 2.1.12` the bounded manual loop fails on the second inference"
with `400 Function call is missing a thought_signature`. Current external sources confirm this is real and
still an open upstream issue for `create_react_agent`/LangGraph paths as of this check
([langchain-ai/langchain-google#1364](https://github.com/langchain-ai/langchain-google/issues/1364)), and
confirm the fix line: **the Python integration was patched at `langchain-google-genai >= 3.1.0`** (signatures
now surface via `additional_kwargs["__gemini_function_call_thought_signatures__"]` and are preserved by
passing the full returned `AIMessage` back into the next call rather than reconstructing it). PyPI's current
listing (checked live) shows **`langchain-google-genai` latest is `4.3.5`, released 2026-08-20** — i.e. the
exact version the project's own spike verified as working, one day before the spike ran. `TECH_STACK.md`'s
"≥4.x" decision is current, not stale.

**Verdict: the live code is pinned to the broken major line, in both the FastAPI process and the AgentCore
codezip snapshot.** Any driver-chat turn that reaches a second LLM inference after a tool call — i.e. every
turn beyond the trivial single-tool case — is exposed to this failure today, subject to §0a below.

- **Fix**: raise the constraint to `langchain-google-genai>=4.0.0,<5.0.0` (or at minimum `>=3.1.0`) in both
  `backend/pyproject.toml` and `agentcore/codezip/pyproject.toml`/`requirements.txt`, re-`uv lock`, and
  re-run the multi-turn spike against the real `uv.lock` per `TECH_STACK.md` §13 item 1b — this was
  explicitly left open ("decide against the lockfile, not the global env") and this pass answers it: the
  lockfile is on 2.1.12, so the decision is "upgrade," not "already fine."
- **FR/NFR**: `NFR-002` (single-hop turn p95 < 2.5 s) and `NFR-004` (hop count as a first-class metric) are
  both unmeasurable while every multi-hop turn is one tool call away from a hard 400.
- **⚠️ Flag — thought_signature-class trap, present in the wild here.** A shallow check (`bind_tools()`
  single-shot call works, per `TECH_STACK.md` check 3) would pass this exact codebase. Only a real multi-turn
  tool call surfaces it. This is not hypothetical risk language — it is the literal installed version.

### 0a. Why this may not be firing today — and why that is not reassurance

`backend/app/assistant/llm.py` does not use Gemini as configured by `TECH_STACK.md` §7 at all (see §1
below): it calls `ChatGoogleGenerativeAI` with an **AI-Studio `google_api_key`**, and Gemini is the
**last-priority** fallback in `AUTO_ORDER` (`llm.py` line 24), behind OpenAI and OpenRouter. If an
`OPENAI_API_KEY` is set — plausible for a POC — every turn silently runs on `ChatOpenAI` instead, and the
`thought_signature` bug never fires because Gemini is never invoked. That is **not** the loop working; it is
the loop routing around Gemini by accident of key precedence. The day someone unsets the OpenAI key (or the
design's own residency requirement is enforced and OpenAI is removed as primary), the exact failure
`TECH_STACK.md` §7 documents starts reproducing on the second inference of any multi-hop driver turn — with
`deploy`/`status` still green, the same "works until it doesn't, silently" shape as the codezip incident in
§7 below.

---

## 1. Model/provider layer vs. `TECH_STACK.md` §7 (D-4/D-4a) — total divergence

`backend/app/assistant/llm.py`:

| §7 decision | Live code | Evidence |
|---|---|---|
| `gemini-3.7-flash` on **Vertex AI** `asia-south1` | `DEFAULT_MODELS["gemini"] = "gemini-flash-latest"` | `llm.py` line 21 |
| **ADC + explicit `project`/`location="asia-south1"`**, never API-key auth (§7's "the API-key trap") | `ChatGoogleGenerativeAI(model=..., google_api_key=resolved.api_key)` — an AI-Studio key, validated to start with `AIza` | `llm.py` lines 51-61, 126-131 |
| `thinking_level: high` (D-4a) | Not set anywhere; `grep` for `thinking_level`/`asia-south1`/`vertexai`/`GOOGLE_CLOUD_LOCATION`/`ChatVertexAI` across `backend/app/` returns **zero matches** | (search performed this pass) |
| Gemini primary, OpenAI documented fallback **behind an explicit flag**, "residency decision, not availability" (§7, §11) | `AUTO_ORDER = ("openai", "openrouter", "gemini")` — Gemini is tried **last**, and any of the three silently wins by whichever key is present, not by an explicit residency-aware flag | `llm.py` line 24 |

**None of §7's actual decision is implemented.** The live code is 100% on the Gemini **Developer API**
(API-key) surface if Gemini runs at all, and OpenAI-primary by default — the exact configuration §7 calls
"the shortest path to working code, and it is the wrong one," and §11 calls "a residency decision, not just
an availability one." Per §11, if the auto-order ever resolves to OpenAI (which it does by default whenever
an `OPENAI_API_KEY` is present), conversation text containing driver PII leaves India on every turn — this
is not a hypothetical fallback path, it is the **default** path in `AUTO_ORDER`.

- **Keep**: the multi-provider abstraction *shape* itself (`ResolvedLLM`, one `build_chat_model` factory) —
  §7's "provider abstraction (retained)" calls for exactly this: one interface, a second provider behind a
  flag.
- **Fix**: (a) reorder `AUTO_ORDER` to Gemini-first with OpenAI as the explicit, deliberately-flagged
  fallback per §11 ("treat flipping it as a deliberate act, not an automatic failover") rather than
  key-presence roulette; (b) switch the Gemini branch to Vertex AI with ADC and `location="asia-south1"`
  (`ChatGoogleGenerativeAI(..., google_api_key=None)` won't do this — per current LangChain docs this needs
  either `ChatVertexAI`-style ADC config or the `vertexai=True` init path the ≥4.x `google-genai`-backed
  integration exposes); (c) set `thinking_level="high"` once the ≥4.x upgrade (§0) makes it natively
  settable — `TECH_STACK.md` §7 records it as `❌ at 2.1.12`; (d) assert the resolved endpoint region at
  startup, per §7's explicit instruction ("Assert the resolved endpoint region at startup rather than
  trusting configuration") — there is currently no such assertion anywhere in `llm.py`.
- **FR/NFR**: `NFR-014` (LLM provider failure trips a circuit breaker **to the fallback**) has no code
  counterpart — `AUTO_ORDER` is a static preference list evaluated once at model-build time, not a
  runtime circuit breaker reacting to failure. §11's residency guarantee (no FR/NFR ID assigned yet) is
  presently false in the default configuration.
- **⚠️ Flag**: this is the model-layer twin of the `thought_signature` trap — `resolve_llm` "works," returns
  a `ResolvedLLM`, the assistant answers questions correctly, and *silently* forfeits both the in-region
  latency (~200 ms/turn) and the DPDP residency guarantee that are §7's entire stated reason for choosing
  Vertex. A shallow smoke test ("does chat answer?") passes; nothing here is Vertex, ADC, or `asia-south1`.

---

## 2. Loop shape vs. the locked "no agent framework" constraint

`run_assistant.py` line 61's own docstring: `"""Bounded ChatOpenAI.bind_tools invoke loop (NOT create_agent
/ AgentExecutor)."""` — and it is exactly that: a `for round_idx in range(MAX_TOOL_ROUNDS)` loop
(`MAX_TOOL_ROUNDS = 6`, line 33) around `llm.ainvoke(messages, ...)` and manual tool dispatch via a
`tool_map`. `backend/uv.lock` confirms no `langgraph` package is installed at all — there is nothing to
import even if the code wanted an executor.

- **Keep**: this matches the locked decision verbatim (`TECH_STACK.md` §2: "LangChain `bind_tools` +
  bounded manual loop — no agent executor... Agent framework: **None** — no executor, no LangGraph"). It is
  also consistent with current external guidance for this scale: 2026 LangChain guidance is that
  `AgentExecutor` is deprecated/maintenance-mode and LangGraph is recommended when an agent needs branching,
  checkpointing, interrupts, or resume — none of which SetuHaul's driver loop needs, because the scheduling
  decision is deterministic and lives in code (§7.2b), not in the model. For "truly minimal scenarios
  without state management needs" (the 2026 guidance's own phrasing), a manual loop is the documented
  correct choice, not a shortcut. No LangGraph dependency, no executor dependency — the constraint is
  actually honored, not just claimed.
- **The message-echo mechanics — the part that decides whether §0's bug fires.** Line 170,
  `messages.append(ai)`, appends the **returned `AIMessage` object itself** — not a reconstructed
  `AIMessage(content=ai.content)` — before appending `ToolMessage` results. This is the correct
  "echo the model's turn back verbatim" shape `TECH_STACK.md` §7 says the raw-SDK fallback proves
  (`contents.append(cand.content)`), and current LangChain guidance for the fix agrees: "pass the full
  `AIMessage` back to the model... don't reconstruct messages manually." **The loop's message-passing shape
  is not the bug.** The bug is purely the pinned package version (§0) — `langchain_google_genai` 2.1.12's
  internal conversion of that `AIMessage` back into the Gemini wire format drops the signature regardless of
  how the caller assembled the message list. Upgrading the package (§0's fix) is the entire remedy; no
  change to `run_assistant.py`'s loop structure is needed for this specific defect.
- **FR/NFR**: none named specifically for loop shape; `SOLUTION_DESIGN.md` §7.2b's requirement that "the LLM
  orchestrates typed tools and never reasons about ranking itself" is upheld — no ranking/scoring logic
  appears in `run_assistant.py` or `tools.py`; ranking stays in `app.scheduling.feasibility`.
- **Missed latency lever, §10 item 1.** `TECH_STACK.md` §10's ordered checklist item 1 — "Delete the first
  tool call. Pre-fetch `get_driver_operational_context` at session open and inject it into the prompt...
  worth more than any region tuning" — is **not implemented**. `run_assistant.py`'s message list (lines
  114-142) seeds `SYSTEM_PROMPT`, Redis summaries, and session context, but never calls
  `driver_reads.get_driver_operational_context` up front; the model must spend its first tool-call hop
  fetching it on essentially every turn. `tools.py`'s own tool description even documents the intended
  design ("pre-fetched at session open, so usually zero calls," `SOLUTION_DESIGN.md` §7.5.4) as something
  that is not actually happening in `run_assistant.py`.
  - **Fix**: call `driver_reads.get_driver_operational_context` once before the first `llm.ainvoke` and
    inject its JSON as a `SystemMessage`, the same way `session_ctx`/`summaries` are already injected.
  - **FR/NFR**: `NFR-004` (hop count as a first-class metric), `NFR-002` (single-hop turn p95 < 2.5 s).
  - **⚠️ Flag**: this is effort spent in the wrong place, not a functional bug — the tool exists and works,
    the loop bound (`MAX_TOOL_ROUNDS = 6`) is generous enough to hide the missing prefetch in testing, but
    it costs a full extra round trip (two inferences, per §10's own stated arithmetic) on real traffic.

---

## 3. Tool catalog vs. `SOLUTION_DESIGN.md` §7.5.4's 12-tool driver allowlist — not implemented

`build_driver_tools` in `tools.py` (lines 671-838) registers **23 `StructuredTool`s** for the driver role:
`get_current_user_context`, `get_conversation_memory`, `get_driver_operational_context`,
`list_active_shipments`, `get_shipment_details`, `get_latest_eta`, `get_eta_history`,
`get_current_appointment`, `get_facility_details`, `get_exception_status`, `report_delay_or_update_eta`,
`find_feasible_slots`, `request_slot`, `get_appointment_request_status`, `cancel_appointment`,
`reschedule_appointment`, `escalate_exception`, `get_vehicle_and_carrier_details`,
`get_gate_and_queue_status`, `get_facility_rules_and_restrictions`,
`report_vehicle_breakdown_or_incident`, `get_dock_maintenance_alerts`, `scheduling_capability_disabled`.

§7.5.4's exact allowlist is 12: `get_driver_operational_context`, `list_active_shipments`,
`get_latest_eta`, `get_current_appointment`, `report_delay_or_update_eta`, `find_feasible_slots`,
`request_slot`, **`confirm_held_slot`**, `get_appointment_request_status`, **`explain_slot_eligibility`**,
`cancel_appointment`, `escalate_exception`. §7.5.4 is explicit that the other 11 of 23 "either fold into the
pre-fetched context block or are rare enough to justify a second-tier catalog loaded on demand," and that
`reschedule_appointment` should **collapse into cancel + request** under D1.

Comparing sets directly:

- **11 tools present that §7.5.4 says should not be in the driver's live surface**: `get_current_user_context`,
  `get_conversation_memory`, `get_shipment_details`, `get_eta_history`, `get_facility_details`,
  `get_exception_status`, `get_vehicle_and_carrier_details`, `get_gate_and_queue_status`,
  `get_facility_rules_and_restrictions`, `report_vehicle_breakdown_or_incident`,
  `get_dock_maintenance_alerts` — every one of them schema-cost on every single call, exactly the mechanism
  §7.5.4/Appendix A name as degrading selection accuracy.
- **`reschedule_appointment` present** despite §7.5.4 saying it should not exist as a standalone tool post-D1
  (collapse into `cancel_appointment` + `request_slot`).
- **Two named tools that are load-bearing per §7.5.4 do not exist at all**: `confirm_held_slot` and
  `explain_slot_eligibility`. Neither has any implementation anywhere in `tools.py`, `driver_reads.py`
  (checked by name), or the scheduling services this file calls into.
- **A stub that contradicts a real tool in the same list**: `scheduling_capability_disabled` (lines
  632-645) returns `CAPABILITY_NOT_ENABLED` for "rescheduling and appointment confirmation," while
  `reschedule_appointment_tool` (lines 529-557) is registered as a fully working tool three entries later in
  the same list. Both are bound to the LLM simultaneously — the model has two contradictory tools available
  for the same intent, one asserting the capability doesn't exist.

This is not a minor trim — it is the full multi-role catalog (the design's own count of "23" total tools
across every persona) bound onto one role with no allowlist logic anywhere in `build_driver_tools`.

- **Fix**: build the 12-tool allowlist named in §7.5.4 exactly; implement `confirm_held_slot` (the HELD→
  driver-confirms→PENDING_CONFIRMATION transition — see §5 below, this is currently missing at the state
  level, not just the tool level) and `explain_slot_eligibility` (backs `FR-DRV-006`, currently entirely
  unimplemented — see §5's requirement-mapping); fold the 11 extra reads into the `get_driver_operational_context`
  pre-fetch payload or a second-tier on-demand catalog per §7.5.4's own stated resolution; remove
  `reschedule_appointment` and `scheduling_capability_disabled` per D1's collapse decision (pick one
  behavior — either reschedule is enabled via cancel+request, or it explicitly is not — not both bound to
  the model at once).
- **FR/NFR**: `FR-DRV-006` ("Facility question — eligibility answered per-invariant... browse-only, no
  exception created," backed by `explain_slot_eligibility` per `ARCHITECTURE/REQUIREMENTS.md` line 174) has
  **no implementation** — the tool it depends on does not exist. `NFR-004`/§10 item 2 ("shrink the tool
  surface... degrades selection accuracy") is directly contradicted by the 23-tool binding.
- **⚠️ Flag**: binding the full catalog "works" in a demo — every tool still functions, nothing throws — so
  a shallow check passes. The cost (worse selection accuracy, more input tokens every single call, on the
  provider currently reachable via the slowest/most expensive fallback path per §1) only shows up as an
  aggregate latency/accuracy regression across real traffic, which is exactly the failure mode
  `TECH_STACK.md` §10 warns will "show up as a latency regression that no amount of infrastructure tuning
  will fix."

---

## 4. Conversation design vs. `SOLUTION_DESIGN.md` §7.2b — the governing rule is not enforced in code

§7.2b's governing rule: *"lifecycle transitions emit deterministic templates. The LLM writes the glue
around them."* Four state templates are specified verbatim (SHOWN, HELD, PENDING_CONFIRMATION, CONFIRMED),
plus eight negative-path templates, plus a banned-phrasings list ("booked"/"reserved"/"you have" below
CONFIRMED; bare "OK"/"Done"; any time without dock+date).

`prompts.py`'s `SYSTEM_PROMPT` (the only place driver-facing wording is governed) contains **no template
text at all** for any of the four states or eight negative paths. It instead gives the model instructions
in its own words to paraphrase — e.g. line 10: *"Explain that returned options are DISPLAYED_NOT_RESERVED
informational possibilities... not a confirmed booking"* — which tells the model **what fact to convey**,
not a business-reviewed sentence to reproduce. There is no code path anywhere in `run_assistant.py` or
`tools.py` that inserts a fixed template string for SHOWN/HELD/PENDING_CONFIRMATION/CONFIRMED; the closest
approximation is the small set of hardcoded fallback sentences in `run_assistant.py` lines 263-288 (e.g.
`f"ETA update for {shipment_id} ({eta_ts}) has been confirmed and saved successfully."`), which only fire
when the model's own `content` is empty — i.e. they are a fallback for no-answer, not the primary mechanism,
and they don't cover SHOWN/HELD/PENDING at all.

- **Fix**: either (a) generate the four state announcements from fixed, parameterized template strings in
  code (the way `run_assistant.py`'s empty-content fallback already does for PERSISTED/CONFIRMATION_REQUIRED,
  but as the primary path, not the fallback), with the LLM only composing the surrounding "glue" text §7.2b
  describes, or (b) if the team accepts model-generated state language for the POC, record that as a
  deliberate, documented deviation from §7.2b rather than an unnoticed gap — §7.2b calls the alternative "a
  broken promise in the business sense, not a wording nit."
- **FR/NFR**: no FR/NFR ID currently names this rule directly in `ARCHITECTURE/REQUIREMENTS.md`'s table (a
  gap worth raising there too), but it is the correctness backbone `FR-DRV-001`'s hold/request/booking
  transitions and `NFR-006` (zero double-booked capacity, driver-communication side) both depend on.
- **⚠️ Flag**: a model that "sounds right" in a demo — describing DISPLAYED_NOT_RESERVED accurately most of
  the time — passes a shallow read. The banned-phrasing failure mode (the model says "you're booked" for a
  HELD slot on one unlucky generation) is a low-probability-per-turn, high-consequence bug that a few manual
  test conversations will not surface.

### 4a. The HELD state does not exist in the live code — a bigger gap than wording

§7.2b's four-state lifecycle is SHOWN → **HELD** (90 s, D2) → PENDING_CONFIRMATION → CONFIRMED. In
`tools.py`, `find_feasible_slots_tool` returns SHOWN-equivalent options (`DISPLAYED_NOT_RESERVED`), and
`request_slot_tool` calls `app.scheduling.allocation.request_slot`, which — per its own tool description in
`tools.py` line 760 — "creates `PENDING_CONFIRMATION` only." There is no tool, and no call anywhere in
`tools.py`, that creates or reads a `HELD` state, and the missing `confirm_held_slot` tool (§3 above) is
exactly the tool that would drive HELD → PENDING_CONFIRMATION. The live flow appears to go **SHOWN directly
to PENDING_CONFIRMATION**, skipping the 90-second hold entirely. This is a state-model gap, not a
conversation-design gap — the finding belongs to both §3 (missing tool) and here (missing lifecycle state),
recorded once to avoid double-charging it.

- **FR/NFR**: `FR-DRV-001` (hold/request/booking transition), `NFR-008` (50-way concurrent race →
  exactly 1 `HELD`...) — `NFR-008`'s stated invariant references a `HELD` state that has no code path to
  reach via the driver-chat tool surface as currently built.

---

## 5. Streaming — the SSE decision has no implementation anywhere in this loop

`TECH_STACK.md` §2/§9 and `DEPLOYMENT.md` §2.1 both state SSE streaming on `/invocations` is load-bearing for
TTFT (`NFR-001`, p95 < 1.2 s). Tracing the actual call path:

- `backend/app/api/v1/routers/chat.py`'s `/api/v1/chat` and `/api/v1/chat/message` are plain
  `async def` handlers returning a single JSON envelope (`ok(result, ...)`) — no `StreamingResponse`,
  no `EventSourceResponse`, no `text/event-stream` media type anywhere in the file.
- `run_assistant.py` calls `await llm.ainvoke(messages, ...)` (line 156) and again inside the tool loop
  (line 252) — never `.astream()`/`.astream_events()`. The full response is assembled before the function
  returns.
- `agentcore_runtime.py::invoke_agentcore` calls `client.invoke_agent_runtime(...)` and then either
  `stream.read()` or `b"".join(stream or [])` (lines 87-90) — **reading the entire response body into
  memory before parsing it as one JSON object**, even if the underlying AgentCore call returned a streamed
  body.
- `agentcore_main.py`'s `@app.entrypoint async def invoke_agent(...)` returns one `dict` (line 121) — the
  `bedrock_agentcore` SDK's entrypoint decorator can support streaming responses per `DEPLOYMENT.md` §2.1,
  but this handler does not use that path; it awaits `_run_turn` fully and returns.

**Verdict: nothing in the current driver-chat path streams a token before the full turn — including every
tool-loop round — has completed.** Given `TECH_STACK.md` §7's own measured full-turn latency (7.40 s for a
4-hop turn against `NFR-002`'s 2.5 s single-hop budget, explicitly attributed to hop count rather than
effort level), the driver currently waits for the entire multi-second turn with no progressive feedback,
which is precisely what §9's "skeletons over spinners... TTFT is what a driver at a roadside actually
experiences" (§10 item 3) is meant to prevent.

- **Fix**: implement `/api/v1/chat` (and the AgentCore `/invocations` entrypoint) as SSE, streaming
  `llm.astream_events()` output token-by-token and emitting each tool call/result as an SSE event, matching
  `TECH_STACK.md` §9's "custom runtime adapter (`ExternalStoreRuntime`-style)" decision for the frontend.
- **FR/NFR**: `NFR-001` (TTFT p95 < 1.2 s) is not just unmet, it is architecturally unreachable in the
  current shape — TTFT and full-turn time are currently the same number.
- **⚠️ Flag**: this is the largest "spent effort in the wrong place" gap found in this pass relative to the
  `thought_signature`-class failure mode — the code correctly implements `bind_tools` mechanics (§2) but has
  built nothing of the streaming architecture §9 spent real design effort resolving (the LangGraph-vs-Vercel-
  AI-SDK adapter deferral, the CDN-hop analysis). None of that has a corresponding line of code yet.

---

## 6. Observability vs. `TECH_STACK.md` §8 — shape present, nesting mechanism unverified, timing plausible

`observability.py` + `run_assistant.py`'s `chat_turn_trace`/`child_invoke_config`:

- **Thread-scoped, one trace per turn**: `chat_turn_trace` opens one `langsmith.trace(name="setuhaul.chat",
  run_type="chain", ...)` per call to `run_assistant`, with `thread_id`/`session_id` stamped into metadata
  (`observe_input`, lines 95-119) — mapping onto `chat_threads.thread_id` as §8 requires, via the caller's
  own `tid` (`run_assistant.py` line 72). **Keep** — this matches §8's shape requirement.
- **Nested child spans for every LLM inference and tool call**: `invoke_config`/`child_invoke_config` are
  passed into every `llm.ainvoke(...)` and `tool.ainvoke(...)` call (lines 156, 187, 252) so metadata/tags
  propagate, but neither function attaches an explicit LangSmith `run_tree`/callback handler — nesting
  depends entirely on LangChain's own tracer picking up the `langsmith.trace()` context-manager's active run
  via Python `contextvars`. Current LangSmith documentation confirms this propagation is automatic by
  design (child functions/runs nest under an active parent run via contextvars, whether invoked through
  `@traceable` or the `trace()` context manager) — so the mechanism this code relies on is a real, current
  capability, not a dead end. **This remains the exact open item `TECH_STACK.md` §13 item 6 names** ("How
  `bind_tools` child runs surface in a manual loop... may need explicit run-tree construction rather than
  coming free") — plausible per current docs, but this pass did not execute a real turn against a LangSmith
  project to confirm the child LLM/tool spans actually land nested rather than as sibling top-level runs.
  **Flag as unverified, not as broken** — do not claim either outcome without inspecting an actual trace.
- **Background flush, never blocking the request path** (§8's separate timing requirement): the code sets
  no explicit async/batch flush configuration — it relies on the LangSmith SDK's own default client
  behavior, which batches and ships traces on a background thread rather than the request's own coroutine.
  This is consistent with §8's requirement but is, again, a property of the dependency's defaults rather
  than something this code affirmatively guarantees (no bounded-queue/drop-rather-than-block configuration
  is visible in `_configure_langsmith` or elsewhere).
- **`sanitize_for_trace`** (lines 52-64) redacts secret-shaped keys before anything reaches LangSmith or
  CloudWatch — a real, correctly-scoped safeguard matching `AGENTS.md`'s "never commit secrets" intent
  extended to telemetry.

- **FR/NFR**: `NFR-025` (thread-scoped, nested LLM/tool spans keyed to `chat_threads.thread_id`) — shape
  present, nesting **unverified**; `NFR-013` (LangSmith never blocks a turn) — plausibly met via SDK
  defaults, not explicitly configured in this code.
- **⚠️ Flag**: none — this is the one area of the assistant code where effort is proportionate to the open
  question, and the open question is correctly still open rather than asserted either way.

---

## 7. AgentCore host contract and the codezip staging drift — confirmed live, not resolved

### 7.1 Runtime contract shape

`agentcore_main.py` uses `from bedrock_agentcore.runtime import BedrockAgentCoreApp` and `@app.entrypoint`
(lines 29-31, 120), which is the SDK-mediated option `DEPLOYMENT.md` §2.1 names as valid ("implement `POST
/invocations` and `GET /ping` directly, **or** use `@app.entrypoint`"). No `/ws` handler is present, which
is fine — §2.1 marks `/ws` optional. **Keep** — this matches the contract as documented.

### 7.2 Region defaults are wrong, silently, in the same shape as §7's API-key trap

`backend/app/core/settings.py` line 48: `aws_region: str = "us-east-1"`. `agentcore_main.py`'s
`_hydrate_ssm_into_env` (line 47) independently falls back to `"us-east-1"` if `AWS_REGION`/
`AWS_DEFAULT_REGION` are unset when reading SSM parameters. Every region decision in `TECH_STACK.md` and
`DEPLOYMENT.md` is `ap-south-1`. If the runtime environment does not explicitly set the region variable,
these defaults silently point at `us-east-1` — the same class of failure `TECH_STACK.md` §7 warns about for
the Vertex API-key trap: "it *works*... and silently costs" the co-location guarantee the whole design rests
on (§2's topology reversal, §11's residency argument).

- **Fix**: default `aws_region` to `"ap-south-1"` (fail toward the decided region, not AWS's historical
  default region), and assert it at startup the same way §7 asks for endpoint-region assertion.
- **FR/NFR**: none directly, but it undermines the co-location premise behind `NFR-001`/`NFR-002`.

### 7.3 The codezip staging drift is real, today, and matches the named incident pattern exactly

`diff -rq backend/app/assistant/ agentcore/codezip/app/assistant/` shows **`run_assistant.py` and
`observability.py` differ** between the live source and the staged copy AgentCore actually deploys. Diffing
them directly: the staged copy (dated 2026-08-17/2026-08-14 by filesystem timestamp) is missing the entire
`chat_turn_trace`/`child_invoke_config` thread-scoped tracing feature added to `backend/app/assistant/` on
2026-08-20 — the staged `observe_input` call has no `thread_id`/`session_id` parameters, and the staged loop
has no `with chat_turn_trace(...)` block at all. `tools.py`, `llm.py`, and `prompts.py` are byte-identical
between the two trees (confirmed via `diff -rq`) — only the observability upgrade has drifted.

This is precisely the `AGENTS.md`/`DEPLOYMENT.md` §2.2 "codezip footgun": **`agentcore.cmd deploy` would
currently ship pre-2026-08-20 observability code** — no thread-scoped nesting, no per-turn LangSmith parent
run — while `deploy`/`status` report success, because nothing about the deploy mechanism inspects content
drift. `stage_agentcore_codezip.py` was evidently not re-run after the 2026-08-20 observability change before
this pass found the diff.

- **Fix**: run `python docs/scripts/stage_agentcore_codezip.py` before the next AgentCore deploy (per
  `AGENTS.md`'s standing rule — this finding is exactly the situation that rule exists to prevent, caught
  before a deploy rather than after one, this time). Longer-term, `DEPLOYMENT.md` §2.2's own preferred fix
  (make staging part of the deploy command, or add a post-deploy artifact assertion) remains unimplemented
  — this drift is evidence the "human remembers to run the script" mitigation alone is already failing in
  practice for a second time.
- **⚠️ Flag**: this is the deployment-pipeline sibling of the `thought_signature` trap — `agentcore.cmd
  status` reports success regardless of which code is actually running, so nothing short of diffing the
  staged tree (as done in this pass) or inspecting a live LangSmith trace would surface it.

---

## 8. Summary table

| # | Area | Tag | One-line finding |
|---|---|---|---|
| 1 | `langchain-google-genai` pin | Fix / ⚠️ Flag | Locked at `2.1.12` (broken multi-turn) in both `backend/` and `agentcore/codezip/`; fix verified current at `>=3.1.0`, project's own target `4.3.5` confirmed still latest on PyPI |
| 2 | Model/provider (`llm.py`) | Fix / ⚠️ Flag | AI-Studio API key, not Vertex ADC; `gemini-flash-latest`, not `gemini-3.7-flash`; Gemini last in `AUTO_ORDER`, not primary; no `thinking_level`, no region assertion |
| 3 | Loop shape (`run_assistant.py`) | Keep | Bounded manual loop, no LangGraph/executor, `ai` object appended verbatim before tool results — correct per current guidance and per the project's own spike |
| 4 | Missing prefetch (`run_assistant.py`) | Fix | §10 lever 1 (`get_driver_operational_context` prefetch) not implemented — costs a hop on most turns |
| 5 | Tool catalog (`tools.py`) | Fix / ⚠️ Flag | 23 tools bound, not the 12-tool §7.5.4 allowlist; `confirm_held_slot`/`explain_slot_eligibility` missing entirely; `reschedule_appointment` present despite D1 collapse; contradicts its own `scheduling_capability_disabled` stub |
| 6 | State templates (`prompts.py`) | Fix | §7.2b's "templated, not generated" governing rule has no code counterpart; model free-generates state language |
| 7 | HELD state | Fix | No tool/state reaches `HELD`; flow appears SHOWN → PENDING_CONFIRMATION directly |
| 8 | Streaming (`chat.py`, `run_assistant.py`, `agentcore_runtime.py`) | Fix / ⚠️ Flag | No SSE anywhere; full JSON blob after full turn; TTFT and full-turn time are currently identical |
| 9 | Observability nesting | Unverified (not Fix, not Keep) | Shape correct; contextvar-based nesting is plausible per current LangSmith docs but not confirmed against a real trace in this codebase |
| 10 | AWS region defaults | Fix | `aws_region` and SSM-hydration fallback both default to `us-east-1`, not `ap-south-1` |
| 11 | Codezip staging drift | Fix / ⚠️ Flag | Confirmed live: staged AgentCore copy is missing the 2026-08-20 LangSmith tracing upgrade; exact incident pattern `AGENTS.md`/`DEPLOYMENT.md` §2.2 already names |

**Net read**: the one piece of `TECH_STACK.md` §7 this codebase gets right by construction — the bounded
manual loop with verbatim-echoed assistant turns — is also the one piece that was never actually exercised
against Gemini in a way that would have exposed the version-pin bug, because the model/provider layer (§1)
routes around Gemini by default. Everything downstream of "which model actually answers this turn" —
tool surface, state templates, streaming, region — has drifted from the design independently of the
`thought_signature` question, which means fixing §0/§1 alone would not make this assistant match
`SOLUTION_DESIGN.md`/`TECH_STACK.md`; it would only make it possible to discover how badly it doesn't, on
the correct model.

---

## Sources consulted this pass

- [langchain-ai/langchain-google #1364 — thought_signature missing, Gemini 3 + create_react_agent](https://github.com/langchain-ai/langchain-google/issues/1364)
- [PyPI — langchain-google-genai (latest 4.3.5, released 2026-08-20)](https://pypi.org/project/langchain-google-genai/)
- [LangChain docs — ChatGoogleGenerativeAI integration, thought_signature handling in AIMessage](https://docs.langchain.com/oss/python/integrations/chat/google_generative_ai)
- [LangChain/LangGraph 2026 comparison — AgentExecutor deprecated, manual loop viable for minimal/no-checkpoint agents](https://www.digitalapplied.com/blog/langchain-vs-langgraph-comparison-2026)
- [LangSmith docs — trace() context manager and contextvar-based automatic run nesting](https://docs.langchain.com/langsmith/nest-traces)
