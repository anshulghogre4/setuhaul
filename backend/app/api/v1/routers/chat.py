from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.assistant.agentcore_runtime import invoke_agentcore
from app.assistant.run_assistant import run_assistant
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
