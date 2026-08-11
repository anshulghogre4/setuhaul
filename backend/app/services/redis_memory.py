from __future__ import annotations

import json
import logging
import re
from typing import Any

from app.core.settings import Settings
from app.core.tls import use_system_trust_store

logger = logging.getLogger(__name__)

TTL_SECONDS = 24 * 60 * 60
HISTORY_LIMIT = 40
DEFAULT_SESSION_ID = "default"
_SAFE_KEY_PART = re.compile(r"[^A-Za-z0-9_.-]+")


def normalize_memory_id(value: str | None, *, fallback: str = DEFAULT_SESSION_ID) -> str:
    """Return a Redis-safe bounded key segment.

    The value is only a namespace for ephemeral memory. It never grants access.
    """
    raw = (value or "").strip()
    if not raw:
        raw = fallback
    safe = _SAFE_KEY_PART.sub("-", raw)[:96].strip(".-")
    return safe or fallback


class ConversationMemory:
    """Upstash Redis 24h non-authoritative conversation/session memory."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._client = None
        self.degraded = False
        self.degrade_reason: str | None = None
        url = (settings.upstash_redis_rest_url or "").strip()
        token = (settings.upstash_redis_rest_token or "").strip()
        if not url or not token:
            self.degraded = True
            self.degrade_reason = "UPSTASH_NOT_CONFIGURED"
            return
        try:
            use_system_trust_store()
            from upstash_redis import Redis

            self._client = Redis(url=url, token=token)
        except Exception as exc:  # noqa: BLE001
            self.degraded = True
            self.degrade_reason = f"UPSTASH_INIT_FAILED:{type(exc).__name__}"
            logger.warning("Upstash init failed: %s", type(exc).__name__)

    def _scope(self, *, user_id: str, thread_id: str, session_id: str | None = None) -> tuple[str, str, str]:
        return (
            normalize_memory_id(user_id, fallback="unknown-user"),
            normalize_memory_id(session_id),
            normalize_memory_id(thread_id, fallback="unknown-thread"),
        )

    def _history_key(self, user_id: str, thread_id: str, session_id: str | None = None) -> str:
        uid, sid, tid = self._scope(user_id=user_id, session_id=session_id, thread_id=thread_id)
        return f"setuhaul:chat:{uid}:session:{sid}:thread:{tid}:history"

    def _session_key(self, user_id: str, thread_id: str, session_id: str | None = None) -> str:
        uid, sid, tid = self._scope(user_id=user_id, session_id=session_id, thread_id=thread_id)
        return f"setuhaul:chat:{uid}:session:{sid}:thread:{tid}:state"

    def load_history(
        self, *, user_id: str, thread_id: str, session_id: str | None = None
    ) -> list[dict[str, Any]]:
        if self._client is None:
            return []
        try:
            raw = self._client.lrange(
                self._history_key(user_id, thread_id, session_id), -HISTORY_LIMIT, -1
            )
            out: list[dict[str, Any]] = []
            for item in raw or []:
                if isinstance(item, str):
                    out.append(json.loads(item))
                elif isinstance(item, dict):
                    out.append(item)
            self.degraded = False
            self.degrade_reason = None
            return out
        except Exception as exc:  # noqa: BLE001
            self.degraded = True
            self.degrade_reason = f"UPSTASH_READ_FAILED:{type(exc).__name__}"
            logger.warning("Upstash read failed: %s", type(exc).__name__)
            return []

    def load_session(
        self, *, user_id: str, thread_id: str, session_id: str | None = None
    ) -> dict[str, Any]:
        if self._client is None:
            return {}
        try:
            raw = self._client.get(self._session_key(user_id, thread_id, session_id))
            if not raw:
                return {}
            if isinstance(raw, dict):
                return raw
            return json.loads(raw)
        except Exception as exc:  # noqa: BLE001
            self.degraded = True
            self.degrade_reason = f"UPSTASH_SESSION_READ_FAILED:{type(exc).__name__}"
            return {}

    def append_turn(
        self,
        *,
        user_id: str,
        thread_id: str,
        session_id: str | None = None,
        user_message: str,
        assistant_message: str,
        session: dict[str, Any] | None = None,
        client_message_id: str | None = None,
    ) -> None:
        if self._client is None:
            return
        try:
            hkey = self._history_key(user_id, thread_id, session_id)
            user_payload = {
                "role": "user",
                "content": user_message,
                "client_message_id": client_message_id,
                "session_id": normalize_memory_id(session_id),
            }
            asst_payload = {
                "role": "assistant",
                "content": assistant_message,
                "session_id": normalize_memory_id(session_id),
            }
            self._client.rpush(hkey, json.dumps(user_payload), json.dumps(asst_payload))
            self._client.ltrim(hkey, -HISTORY_LIMIT, -1)
            self._client.expire(hkey, TTL_SECONDS)
            if session is not None:
                skey = self._session_key(user_id, thread_id, session_id)
                self._client.set(skey, json.dumps(session), ex=TTL_SECONDS)
            self.degraded = False
            self.degrade_reason = None
        except Exception as exc:  # noqa: BLE001
            self.degraded = True
            self.degrade_reason = f"UPSTASH_WRITE_FAILED:{type(exc).__name__}"
            logger.warning("Upstash write failed: %s", type(exc).__name__)

    def seen_client_message(
        self,
        *,
        user_id: str,
        thread_id: str,
        client_message_id: str,
        session_id: str | None = None,
    ) -> bool:
        history = self.load_history(user_id=user_id, thread_id=thread_id, session_id=session_id)
        return any(m.get("client_message_id") == client_message_id for m in history)

    def snapshot(
        self,
        *,
        user_id: str,
        thread_id: str,
        session_id: str | None = None,
        include_recent_messages: bool = True,
        recent_limit: int = 8,
    ) -> dict[str, Any]:
        safe_session_id = normalize_memory_id(session_id)
        if self._client is None:
            return {
                "code": "REDIS_MEMORY_UNAVAILABLE",
                "source": "upstash_redis",
                "freshness": "unavailable",
                "thread_id": thread_id,
                "session_id": safe_session_id,
                "history_count": 0,
                "recent_messages": [],
                "session": {},
                "ttl_seconds": TTL_SECONDS,
                "non_authoritative": True,
                "degraded": True,
                "degrade_reason": self.degrade_reason or "UPSTASH_NOT_CONFIGURED",
            }

        history = self.load_history(user_id=user_id, thread_id=thread_id, session_id=safe_session_id)
        session = self.load_session(user_id=user_id, thread_id=thread_id, session_id=safe_session_id)
        recent = history[-max(1, min(recent_limit, HISTORY_LIMIT)) :] if include_recent_messages else []
        return {
            "code": "REDIS_MEMORY_LOADED",
            "source": "upstash_redis",
            "freshness": "ephemeral_24h",
            "thread_id": thread_id,
            "session_id": safe_session_id,
            "history_count": len(history),
            "recent_messages": [
                {
                    "role": item.get("role"),
                    "content": str(item.get("content") or "")[:500],
                    "client_message_id": item.get("client_message_id"),
                }
                for item in recent
            ],
            "session": session,
            "ttl_seconds": TTL_SECONDS,
            "non_authoritative": True,
            "degraded": self.degraded,
            "degrade_reason": self.degrade_reason,
        }
