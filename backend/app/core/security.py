from __future__ import annotations

import time
from typing import Any

import httpx
import jwt
from jwt import PyJWKClient

from app.core.errors import AppError
from app.core.settings import Settings


class JwtVerifier:
    """Verify Supabase access tokens via JWKS (issuer, audience, expiry, subject)."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._jwks_client: PyJWKClient | None = None
        self._jwks_fetched_at: float = 0.0

    def _client(self) -> PyJWKClient:
        if self._jwks_client is None or (time.time() - self._jwks_fetched_at) > 3600:
            if not self._settings.supabase_url:
                raise AppError(
                    "Supabase URL is not configured.",
                    code="AUTH_MISCONFIGURED",
                    status_code=503,
                )
            self._jwks_client = PyJWKClient(self._settings.supabase_jwks_url)
            self._jwks_fetched_at = time.time()
        return self._jwks_client

    def verify_access_token(self, token: str) -> dict[str, Any]:
        try:
            signing_key = self._client().get_signing_key_from_jwt(token)
            claims = jwt.decode(
                token,
                signing_key.key,
                algorithms=["ES256", "RS256", "HS256"],
                audience=self._settings.supabase_jwt_audience,
                issuer=self._settings.supabase_issuer,
                leeway=300,
                options={"require": ["exp", "sub", "aud"]},
            )
        except AppError:
            raise
        except jwt.ExpiredSignatureError as exc:
            raise AppError("Token expired.", code="TOKEN_EXPIRED", status_code=401) from exc
        except jwt.InvalidTokenError as exc:
            raise AppError("Invalid access token.", code="TOKEN_INVALID", status_code=401) from exc
        except httpx.HTTPError as exc:
            raise AppError(
                "Unable to verify token signature.",
                code="JWKS_UNAVAILABLE",
                status_code=503,
            ) from exc
        except Exception as exc:
            # Malformed/forged tokens can raise PyJWKClientError or other decode failures.
            raise AppError("Invalid access token.", code="TOKEN_INVALID", status_code=401) from exc

        sub = claims.get("sub")
        if not sub or not isinstance(sub, str):
            raise AppError("Token subject missing.", code="TOKEN_INVALID", status_code=401)
        return claims
