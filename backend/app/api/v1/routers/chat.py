from typing import Annotated, Any

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.assistant.run_assistant import run_assistant
from app.core.deps import get_db_session, get_request_id, get_settings_dep, require_roles
from app.core.envelope import ok
from app.core.execution_context import ExecutionContext, RoleName
from app.core.settings import Settings

router = APIRouter(prefix="/api/v1", tags=["chat"])


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    thread_id: str | None = None
    session_id: str | None = Field(default=None, max_length=128)
    client_message_id: str | None = None


@router.post("/chat")
async def chat(
    body: ChatRequest,
    request: Request,
    ctx: Annotated[ExecutionContext, Depends(require_roles(RoleName.DRIVER))],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    settings: Annotated[Settings, Depends(get_settings_dep)],
) -> dict[str, Any]:
    result = await run_assistant(
        session=session,
        ctx=ctx,
        settings=settings,
        message=body.message.strip(),
        thread_id=body.thread_id,
        session_id=body.session_id,
        client_message_id=body.client_message_id,
    )
    return ok(result, get_request_id(request), message="Assistant response ready.")
