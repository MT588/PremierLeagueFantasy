"""Supabase JWT verification for the API.

Supabase signs access tokens with a per-project asymmetric key (ES256) published
at /auth/v1/.well-known/jwks.json. Older projects use a shared HS256 secret
instead; set SUPABASE_JWT_SECRET to take that path.
"""

from functools import lru_cache
from typing import Annotated

import jwt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt import PyJWKClient

from app.config import settings

_bearer = HTTPBearer(auto_error=False)
_UNAUTHORIZED = {"WWW-Authenticate": "Bearer"}


@lru_cache(maxsize=1)
def _jwks_client() -> PyJWKClient:
    # Cached across requests so a warm serverless instance fetches the keys once.
    return PyJWKClient(
        f"{settings.supabase_url}/auth/v1/.well-known/jwks.json",
        cache_keys=True,
        lifespan=3600,
    )


def verify_token(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> dict:
    """Return the decoded claims of a valid Supabase access token, else 401."""
    if credentials is None:
        raise HTTPException(401, "missing bearer token", headers=_UNAUTHORIZED)
    if not settings.supabase_url:
        raise HTTPException(500, "SUPABASE_URL is not configured")

    issuer = f"{settings.supabase_url}/auth/v1"
    token = credentials.credentials
    try:
        if settings.supabase_jwt_secret:
            return jwt.decode(
                token,
                settings.supabase_jwt_secret,
                algorithms=["HS256"],
                audience="authenticated",
                issuer=issuer,
            )
        signing_key = _jwks_client().get_signing_key_from_jwt(token)
        return jwt.decode(
            token,
            signing_key.key,
            algorithms=["ES256", "RS256"],
            audience="authenticated",
            issuer=issuer,
        )
    except jwt.PyJWTError as exc:
        raise HTTPException(
            401, "invalid or expired token", headers=_UNAUTHORIZED
        ) from exc
