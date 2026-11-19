"""Username / password authentication against the user table."""

from __future__ import annotations

import logging

from app.errors import AuthenticationError
from app.security.authorization import Actor, Role
from app.security.passwords import DUMMY_HASH, verify_password
from app.storage.repository import Repository

logger = logging.getLogger("app.auth")

INVALID_CREDENTIALS = "Incorrect username or password"


class AuthService:
    def __init__(self, repo: Repository):
        self.repo = repo

    def authenticate(self, user_id: str, password: str) -> Actor:
        user = self.repo.get_user(user_id)
        if user is None:
            verify_password(password, DUMMY_HASH)          # equalise timing
            logger.info("login failed (unknown user)")
            raise AuthenticationError(INVALID_CREDENTIALS)
        if not verify_password(password, user.password_hash) or not user.is_active:
            logger.info("login failed user=%s", user_id)
            raise AuthenticationError(INVALID_CREDENTIALS)
        logger.info("login ok user=%s", user_id)
        return Actor(user_id=user.id, role=Role(user.role))

    def actor_for(self, user_id: str) -> Actor:
        """Resolve the role from the database for an already-authenticated user id."""
        user = self.repo.get_user(user_id)
        if user is None or not user.is_active:
            raise AuthenticationError("Invalid access token")
        return Actor(user_id=user.id, role=Role(user.role))
