"""Runtime settings, read from environment variables (never hard-coded secrets).

Variables
---------
PCSS_JWT_SECRET                  required for the API; >= 32 characters, e.g.
                                 ``python -c "import secrets; print(secrets.token_urlsafe(48))"``
PCSS_DATABASE_URL                default ``sqlite:///./pcss_demo.db``
PCSS_ACCESS_TOKEN_EXPIRE_MINUTES default 30
"""

from __future__ import annotations

import os
from dataclasses import dataclass

MIN_SECRET_LENGTH = 32
DEFAULT_DATABASE_URL = "sqlite:///./pcss_demo.db"


class ConfigurationError(RuntimeError):
    """Raised at start-up when required configuration is missing or unsafe."""


@dataclass(frozen=True)
class Settings:
    jwt_secret: str
    database_url: str = DEFAULT_DATABASE_URL
    jwt_algorithm: str = "HS256"
    jwt_issuer: str = "pcss-demo"
    access_token_expire_minutes: int = 30

    def __post_init__(self) -> None:
        if len(self.jwt_secret) < MIN_SECRET_LENGTH:
            raise ConfigurationError(
                f"PCSS_JWT_SECRET must be at least {MIN_SECRET_LENGTH} characters long")
        if self.access_token_expire_minutes <= 0:
            raise ConfigurationError("access token lifetime must be positive")

    def __repr__(self) -> str:  # never print the secret
        return (f"Settings(database_url={self.database_url!r}, jwt_algorithm={self.jwt_algorithm!r}, "
                f"access_token_expire_minutes={self.access_token_expire_minutes})")

    @classmethod
    def from_env(cls) -> "Settings":
        secret = os.environ.get("PCSS_JWT_SECRET")
        if not secret:
            raise ConfigurationError(
                "PCSS_JWT_SECRET is not set. Generate one with: "
                "python -c \"import secrets; print(secrets.token_urlsafe(48))\"")
        try:
            minutes = int(os.environ.get("PCSS_ACCESS_TOKEN_EXPIRE_MINUTES", "30"))
        except ValueError as exc:
            raise ConfigurationError("PCSS_ACCESS_TOKEN_EXPIRE_MINUTES must be an integer") from exc
        return cls(jwt_secret=secret, database_url=database_url_from_env(),
                   access_token_expire_minutes=minutes)


def database_url_from_env() -> str:
    return os.environ.get("PCSS_DATABASE_URL", DEFAULT_DATABASE_URL)
