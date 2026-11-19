"""FastAPI dependencies: DB session, authenticated actor, coarse role checks."""

from __future__ import annotations

from typing import Iterator, Optional

from fastapi import Depends, Request
from fastapi.security import OAuth2PasswordBearer

from app.config import Settings
from app.errors import AuthenticationError
from app.security.authentication import decode_access_token
from app.security.authorization import Action, Actor, ensure_allowed
from app.services.auth_service import AuthService
from app.storage.repository import Repository

# auto_error=False so that missing credentials go through our unified 401 handler.
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login", auto_error=False)


def get_settings(request: Request) -> Settings:
    return request.app.state.settings


def get_repository(request: Request) -> Iterator[Repository]:
    session = request.app.state.session_factory()
    try:
        yield Repository(session)
    finally:
        session.close()


def get_current_actor(token: Optional[str] = Depends(oauth2_scheme),
                      settings: Settings = Depends(get_settings),
                      repo: Repository = Depends(get_repository)) -> Actor:
    """401 unless the bearer token is valid; the role is read from the database."""
    if not token:
        raise AuthenticationError("Not authenticated")
    user_id = decode_access_token(token, settings)
    return AuthService(repo).actor_for(user_id)


def require_dealer_for_creation(actor: Actor = Depends(get_current_actor)) -> Actor:
    """Coarse, resource-independent role check (403 for participants)."""
    ensure_allowed(Action.CREATE_SHARING, actor)
    return actor
