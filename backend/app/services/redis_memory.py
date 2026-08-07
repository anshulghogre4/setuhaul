from __future__ import annotations

import json
import logging
from typing import Any

from app.core.settings import Settings

logger = logging.getLogger(__name__)

TTL_SECONDS = 24 * 60 * 60
HISTORY_LIMIT = 40


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
            from upstash_redis import Redis

            self._client = Redis(url=url, token=token)
        except Exception as exc:  # noqa: BLE001
            self.degraded = True
            self.degrade_reason = f"UPSTASH_INIT_FAILED:{type(exc).__name__}"
            logger.warning("Upstash init failed: %s", type(exc).__name__)

    def _history_key(self, user_id: str, thread_id: str) -> str:
        return f"setuhaul:chat:{user_id}:{thread_id}:history"

    def _session_key(self, user_id: str, thread_id: str) -> str:
        return f"setuhaul:chat:{user_id}:{thread_id}:session"

    def load_history(self, *, user_id: str, thread_id: str) -> list[dict[str, Any]]:
        if self._client is None:
            return []
        try:
            raw = self._client.lrange(self._history_key(user_id, thread_id), -HISTORY_LIMIT, -1)
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

    def load_session(self, *, user_id: str, thread_id: str) -> dict[str, Any]:
        if self._client is None:
            return {}
        try:
            raw = self._client.get(self._session_key(user_id, thread_id))
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
        user_message: str,
        assistant_message: str,
        session: dict[str, Any] | None = None,
        client_message_id: str | None = None,
    ) -> None:
        if self._client is None:
            return
        try:
            hkey = self._history_key(user_id, thread_id)
            user_payload = {
                "role": "user",
                "content": user_message,
                "client_message_id": client_message_id,
            }
            asst_payload = {"role": "assistant", "content": assistant_message}
            self._client.rpush(hkey, json.dumps(user_payload), json.dumps(asst_payload))
            self._client.ltrim(hkey, -HISTORY_LIMIT, -1)
            self._client.expire(hkey, TTL_SECONDS)
            if session is not None:
                skey = self._session_key(user_id, thread_id)
                self._client.set(skey, json.dumps(session), ex=TTL_SECONDS)
            self.degraded = False
            self.degrade_reason = None
        except Exception as exc:  # noqa: BLE001
            self.degraded = True
            self.degrade_reason = f"UPSTASH_WRITE_FAILED:{type(exc).__name__}"
            logger.warning("Upstash write failed: %s", type(exc).__name__)

    def seen_client_message(self, *, user_id: str, thread_id: str, client_message_id: str) -> bool:
        history = self.load_history(user_id=user_id, thread_id=thread_id)
        return any(m.get("client_message_id") == client_message_id for m in history)
