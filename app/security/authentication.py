"""JWT access tokens (HS256 via PyJWT).

The token only carries the user id (``sub``) plus standard time claims.  The
role is deliberately NOT trusted from the token or from request bodies: it is
re-read from the database for every request (see ``app.api.deps``).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import jwt

from app.config import Settings
from app.errors import AuthenticationError

TOKEN_TYPE = "access"


def create_access_token(user_id: str, settings: Settings) -> str:
    now = datetime.now(timezone.utc)
    claims = {
        "sub": user_id,
        "iat": now,
        "nbf": now,
        "exp": now + timedelta(minutes=settings.access_token_expire_minutes),
        "iss": settings.jwt_issuer,
        "type": TOKEN_TYPE,
    }
    return jwt.encode(claims, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str, settings: Settings) -> str:
    """Verify signature, expiry, issuer and type; return the user id."""
    try:
        claims = jwt.decode(
            token, settings.jwt_secret, algorithms=[settings.jwt_algorithm],
            issuer=settings.jwt_issuer, options={"require": ["exp", "iat", "sub", "iss"]})
    except jwt.ExpiredSignatureError as exc:
        raise AuthenticationError("Access token has expired") from exc
    except jwt.PyJWTError as exc:
        raise AuthenticationError("Invalid access token") from exc
    if claims.get("type") != TOKEN_TYPE or not isinstance(claims.get("sub"), str):
        raise AuthenticationError("Invalid access token")
    return claims["sub"]
