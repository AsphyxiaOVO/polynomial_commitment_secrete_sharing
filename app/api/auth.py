from __future__ import annotations

from fastapi import APIRouter, Depends
from fastapi.security import OAuth2PasswordRequestForm

from app.config import Settings
from app.schemas.auth import TokenResponse, UserOut
from app.security.authentication import create_access_token
from app.security.authorization import Actor
from app.services.auth_service import AuthService
from app.storage.repository import Repository

from .deps import get_current_actor, get_repository, get_settings

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


@router.post("/login", response_model=TokenResponse, summary="OAuth2 password flow login")
def login(form: OAuth2PasswordRequestForm = Depends(),
          repo: Repository = Depends(get_repository),
          settings: Settings = Depends(get_settings)) -> TokenResponse:
    """Form fields ``username`` / ``password`` (application/x-www-form-urlencoded)."""
    actor = AuthService(repo).authenticate(form.username, form.password)
    return TokenResponse(access_token=create_access_token(actor.user_id, settings),
                         expires_in=settings.access_token_expire_minutes * 60,
                         user=UserOut(user_id=actor.user_id, role=actor.role.value))


@router.get("/me", response_model=UserOut, summary="Current user (role from the database)")
def me(actor: Actor = Depends(get_current_actor)) -> UserOut:
    return UserOut(user_id=actor.user_id, role=actor.role.value)
