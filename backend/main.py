"""FastAPI entry point. Run: uvicorn backend.main:app --reload"""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from backend import __version__
from backend.config import Settings, load_settings
from backend.env_info import collect_env_info
from backend.logging_setup import setup_logging

log = logging.getLogger(__name__)


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or load_settings()

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        log_file = settings.logging.file
        setup_logging(
            settings.logging.level,
            settings.resolve_path(log_file) if log_file else None,
        )
        log.info("startup env=%s version=%s", settings.app.env, __version__)
        yield
        log.info("shutdown")

    app = FastAPI(title=settings.app.name, version=__version__, lifespan=lifespan)
    app.state.settings = settings

    @app.get("/health", tags=["system"])
    def health() -> dict:
        return {
            "status": "ok",
            "app": settings.app.name,
            "version": __version__,
            "env": settings.app.env,
            "radio_backend_preference": settings.radio.backend,
        }

    @app.get("/health/env", tags=["system"])
    def health_env() -> dict:
        return collect_env_info()

    return app


app = create_app()
