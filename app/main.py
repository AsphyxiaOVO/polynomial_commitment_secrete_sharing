"""Application factory.

Run (development)::

    uvicorn app.main:create_app --factory --reload

``create_app`` reads :class:`app.config.Settings` from the environment unless
settings are passed explicitly (tests do that).
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import AsyncIterator, Optional

from fastapi import FastAPI

from app.config import Settings
from app.storage.database import init_db, make_engine, make_session_factory

from .api import auth, recovery, sharing, verification
from .api.errors import register_exception_handlers

DESCRIPTION = """
Polynomial secret sharing + evaluation-consistency proofs + JWT/RBAC.

**Research / teaching prototype** – not production cryptography. See README
"Security limitations".
"""


def _configure_logging() -> None:
    """Application log lines (ids, sizes, outcomes only - never secrets) on stderr."""
    logger = logging.getLogger("app")
    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter("%(levelname)s:     %(name)s - %(message)s"))
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)


def create_app(settings: Optional[Settings] = None) -> FastAPI:
    settings = settings or Settings.from_env()
    _configure_logging()
    engine = make_engine(settings.database_url)
    init_db(engine)

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        yield
        engine.dispose()            # close pooled SQLite connections on shutdown

    app = FastAPI(title="pcss-service", version="0.3.0", description=DESCRIPTION, lifespan=lifespan)
    app.state.settings = settings
    app.state.engine = engine
    app.state.session_factory = make_session_factory(engine)

    register_exception_handlers(app)
    for module in (auth, sharing, verification, recovery):
        app.include_router(module.router)

    @app.get("/health", tags=["meta"])
    def health() -> dict:
        return {"status": "ok"}

    logging.getLogger("app").info("application started (%r)", settings)
    return app
