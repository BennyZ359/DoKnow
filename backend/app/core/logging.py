"""Structured logging configuration (structlog).

Uses JSON logging in production and a readable console formatter in debug.
All third-party noisy loggers (uvicorn, alembic, httpx, sqlalchemy) are
brought to a sane level.
"""

from __future__ import annotations

import logging
import sys

import structlog

from app.core.config import settings

_PROCESSORS = [
    structlog.contextvars.merge_contextvars,
    structlog.processors.add_log_level,
    structlog.processors.TimeStamper(fmt="iso"),
    structlog.processors.StackInfoRenderer(),
    structlog.processors.format_exc_info,
]


def configure_logging() -> None:
    """Configure root + structlog loggers once at startup."""
    level = (
        logging.DEBUG
        if settings.debug
        else getattr(logging, settings.log_level.upper(), logging.INFO)
    )

    logging.basicConfig(format="%(message)s", stream=sys.stdout, level=level)
    for name in (
        "uvicorn",
        "uvicorn.error",
        "uvicorn.access",
        "alembic",
        "httpx",
        "sqlalchemy.engine",
    ):
        logging.getLogger(name).setLevel(level)

    if settings.debug:
        renderer = structlog.dev.ConsoleRenderer()
    else:
        renderer = structlog.processors.JSONRenderer(ensure_ascii=False)

    structlog.configure(
        processors=[*_PROCESSORS, renderer],
        wrapper_class=structlog.make_filtering_bound_logger(level),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str = "app") -> structlog.stdlib.BoundLogger:
    """Return a bound structlog logger."""
    return structlog.get_logger(name)
