# AI engineering branch

## Runtime role

There is one role-adaptive SetuHaul assistant. It interprets natural language, asks minimal clarification, maintains thread context, selects curated typed tools, and explains **verified** business facts returned by FastAPI application services. It never queries the database directly and never owns feasibility, ranking, authorization, scheduling, or state-transition policy.

**Owner lock (2026-08-07):**

- Use LangChain **`ChatOpenAI`** with **`bind_tools(...)`** on a curated, role-scoped tool list.
- Run a **custom bounded `run_assistant` invoke loop**: `model.invoke` → if `tool_calls`, execute typed Pydantic tool functions that call FastAPI services → append `ToolMessage`s → final text response.
- This is **not** `create_agent`, `AgentExecutor`, `create_react_agent`, or any other agent framework entrypoint. `bind_tools` + a manual invoke loop ≠ `create_agent`.
- Never name private reference projects in SetuHaul docs.

## Tool catalogue and sprint placement

Authoritative matrix: `plans/implementation-master-plan.md` §5.2. **26** named capabilities; planning band **~18–25** (owner ~18–20 aligns with role-scoped subsets / excluding infra). Two rows are Sprint 2 **internal** services (not direct model registration).

| Sprint | What ships |
|---|---|
| **Sprint 1** | Application **services / REST** for observational reads only. **Do not** mount chat or register tools with the model. **Upstash not required.** |
| **Sprint 2** | Mount chat. Register POC role-scoped tools via `bind_tools`. Add ETA/exception capabilities. **Upstash required** for 24h conversation/session memory. |
| **Sprint 3** | Register scheduling/search/report tools. Feasibility + appointment mutations. |

Sprint 1 service contracts (build now, register in Sprint 2): `get_current_user_context`, `get_driver_operational_context`, `list_active_shipments`, `get_shipment_details`, `get_latest_eta`, `get_current_appointment`, `get_facility_details`, `get_facility_operational_status`, `get_dashboard_summary`.

Sprint 2 additions: `get_eta_history`, `report_delay_or_update_eta` (model-facing), `get_exception_status`; internals `record_eta_update`, `create_or_update_exception`.

## State model

Store only the conversational working set in Upstash Redis with a 24-hour TTL. PostgreSQL remains authoritative.

- **Sprint 1:** Upstash not required.
- **Sprint 2+:** load history/session before invoke; persist completed turn with TTL. If Redis is down, business REST continues; multi-turn memory degrades visibly.

## ChatOpenAI + bind_tools + manual loop

```text
FastAPI validates the request and injects ExecutionContext
  -> load bounded Upstash Redis history/session (Sprint 2+)
  -> llm = ChatOpenAI(...).bind_tools(role_scoped_tools)
  -> messages = system + history + user
  -> AIMessage = llm.invoke(messages)
  -> while tool_calls (bounded):
       run typed tool fns -> FastAPI application services only
       append ToolMessages
       AIMessage = llm.invoke(messages)
  -> persist turn (24h TTL) + return final text
```

```python
llm = ChatOpenAI(model=..., temperature=0).bind_tools(role_scoped_tools)

def run_assistant(payload):
    messages = build_messages(payload)  # system, history, user
    ai = llm.invoke(messages)
    for _ in range(MAX_TOOL_ROUNDS):
        if not ai.tool_calls:
            break
        for call in ai.tool_calls:
            result = execute_typed_tool(call, payload["execution_context"])
            messages.append(ToolMessage(content=result, tool_call_id=call["id"]))
        ai = llm.invoke(messages)
    save_turn(...)
    return {"thread_id": ..., "response": ai.content}
```

## Safety

- Role/channel allowlists deny by default. Sprint 1–2: scheduling mutations return `CAPABILITY_NOT_ENABLED` with zero appointment writes.
- Tools never contain SQL; PostgreSQL is SoT; LLM never invents operational facts.
- Sanitize LangSmith traces.

## Deferral

Do not build `create_agent` / `AgentExecutor` / `create_react_agent`, multi-agent orchestration, autonomous planning, RAG, predictive ETA, or AI ranking for the MVP. Add an optimizer later only as a deterministic service with auditable inputs and outputs.
