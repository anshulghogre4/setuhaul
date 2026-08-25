import json
from typing import Annotated, Any, AsyncIterator

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.assistant.agentcore_runtime import invoke_agentcore
from app.assistant.run_assistant import run_assistant, stream_assistant_turn
from app.core.deps import get_db_session, get_request_id, get_settings_dep, require_roles
from app.core.envelope import ok
from app.core.execution_context import ExecutionContext, RoleName
from app.core.settings import Settings
from app.services.redis_memory import ConversationMemory

router = APIRouter(prefix="/api/v1", tags=["chat"])


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    thread_id: str | None = None
    session_id: str | None = Field(default=None, max_length=128)
    client_message_id: str | None = None


@router.get("/chat/history")
async def chat_history(
    request: Request,
    ctx: Annotated[ExecutionContext, Depends(require_roles(RoleName.DRIVER))],
    settings: Annotated[Settings, Depends(get_settings_dep)],
    thread_id: Annotated[str | None, Query(max_length=128)] = None,
    session_id: Annotated[str | None, Query(max_length=128)] = None,
) -> dict[str, Any]:
    """Restore bounded Redis chat bubbles for the authenticated driver (24h TTL)."""
    memory = ConversationMemory(settings)
    data = memory.load_conversation_for_restore(
        user_id=ctx.user_id,
        thread_id=thread_id,
        session_id=session_id,
    )
    return ok(data, get_request_id(request), message="Chat history loaded.")


async def _driver_chat(
    body: ChatRequest,
    request: Request,
    ctx: ExecutionContext,
    session: AsyncSession,
    settings: Settings,
) -> dict[str, Any]:
    message = body.message.strip()
    if settings.agentcore_enabled:
        result = await invoke_agentcore(
            settings=settings,
            ctx=ctx,
            message=message,
            thread_id=body.thread_id,
            session_id=body.session_id,
            client_message_id=body.client_message_id,
        )
    else:
        result = await run_assistant(
            session=session,
            ctx=ctx,
            settings=settings,
            message=message,
            thread_id=body.thread_id,
            session_id=body.session_id,
            client_message_id=body.client_message_id,
        )
    return ok(result, get_request_id(request), message="Assistant response ready.")


@router.post("/chat")
async def chat(
    body: ChatRequest,
    request: Request,
    ctx: Annotated[ExecutionContext, Depends(require_roles(RoleName.DRIVER))],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    settings: Annotated[Settings, Depends(get_settings_dep)],
) -> dict[str, Any]:
    return await _driver_chat(body, request, ctx, session, settings)


@router.post("/chat/message")
async def chat_message(
    body: ChatRequest,
    request: Request,
    ctx: Annotated[ExecutionContext, Depends(require_roles(RoleName.DRIVER))],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    settings: Annotated[Settings, Depends(get_settings_dep)],
) -> dict[str, Any]:
    """Alias for DriverHome.tsx which posts /api/v1/chat/message."""
    return await _driver_chat(body, request, ctx, session, settings)


async def _sse_frames(events: AsyncIterator[dict[str, Any]]) -> AsyncIterator[str]:
    async for evt in events:
        yield f"event: {evt['event']}\ndata: {json.dumps(evt['data'], default=str)}\n\n"


async def _agentcore_as_single_frame(
    *, settings: Settings, ctx: ExecutionContext, body: ChatRequest,
) -> AsyncIterator[dict[str, Any]]:
    """E4.3 lever 3 (issue #33): true incremental passthrough for the AgentCore path needs
    `agentcore_runtime.invoke_agentcore` restructured to stream chunks off the boto3 response
    instead of buffering the whole body (it currently requests `accept: application/json`, not
    `text/event-stream`) -- separate, larger scope than this pass, deferred rather than silently
    left unstreamed with no explanation. Until then, the hosted path still gets a working
    `/chat/stream` response, just as one `done` frame instead of incremental tokens.
    """
    result = await invoke_agentcore(
        settings=settings, ctx=ctx, message=body.message.strip(), thread_id=body.thread_id,
        session_id=body.session_id, client_message_id=body.client_message_id,
    )
    yield {"event": "start", "data": {"thread_id": result.get("thread_id"), "session_id": result.get("session_id")}}
    yield {"event": "done", "data": result}


@router.post("/chat/stream")
async def chat_stream(
    body: ChatRequest,
    ctx: Annotated[ExecutionContext, Depends(require_roles(RoleName.DRIVER))],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    settings: Annotated[Settings, Depends(get_settings_dep)],
) -> StreamingResponse:
    """E4.3 lever 3 (issue #33): additive SSE endpoint, alongside `/chat`/`/chat/message`, not a
    replacement -- per the issue's own rollback note, the existing non-streaming path is
    untouched, so a revert of this endpoint alone cannot break the frontend mid-flight.
    """
    message = body.message.strip()
    if settings.agentcore_enabled:
        events = _agentcore_as_single_frame(settings=settings, ctx=ctx, body=body)
    else:
        events = stream_assistant_turn(
            session=session, ctx=ctx, settings=settings, message=message,
            thread_id=body.thread_id, session_id=body.session_id,
            client_message_id=body.client_message_id,
        )
    return StreamingResponse(
        _sse_frames(events),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
