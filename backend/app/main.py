"""DoKnow — Know what to learn. Learn how to do.

FastAPI application entrypoint: boot, recover, automate, serve.

Boot sequence (lifespan):
1. configure logging;
2. recover agent runs whose heartbeats went stale (crash recovery, §11);
3. install the event-driven automation handlers (§11);
4. start the periodic scheduler: mark reviews due, expire overdue tasks,
   and run a Learning Manager cycle for idle goals (§6–§7) — the whitepaper
   explicitly rejects a 24/7 model loop in favor of events + schedules.
"""

from __future__ import annotations

import threading
import uuid
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.agents.runtime import recover_stale_runs
from app.core.config import settings
from app.core.logging import configure_logging, get_logger
from app.core.redis import get_cache, get_redis
from app.services import automation, goal_service, review_service, task_service

logger = get_logger("app")

SCHEDULER_TICK_SECONDS = 600  # every 10 minutes
IDLE_MANAGER_LOCK_SECONDS = 6 * 3600  # idle-goal cycles at most every 6h


def _scheduler_tick() -> None:
    """Time-based automation (§11): reviews due, task expiry, idle goals."""
    try:
        due = review_service.mark_due()
        expired = task_service.expire_overdue_tasks()
        recovered = recover_stale_runs()
        for goal in goal_service.list_active_goals():
            # Idle goals still deserve a periodic check-in (§7 proactive).
            # Separate throttle key from event-triggered cycles: a recent
            # event cycle must not silence the scheduler for 6 hours.
            try:
                locked = get_cache().acquire_lock(
                    f"trigger:manager_idle:{goal['id']}", IDLE_MANAGER_LOCK_SECONDS
                )
            except Exception:
                locked = True  # Redis down → proceed (idempotency still holds)
            if not locked:
                continue
            automation._run_manager_cycle(
                uuid.UUID(str(goal["id"])), uuid.UUID(str(goal["user_id"])), "scheduler"
            )
        if due or expired or recovered:
            logger.info(
                "scheduler.tick", reviews_due=due, tasks_expired=expired, recovered=recovered
            )
    except Exception:
        logger.exception("scheduler tick failed")


def _scheduler_loop(stop: threading.Event) -> None:
    while not stop.wait(SCHEDULER_TICK_SECONDS):
        _scheduler_tick()


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging()
    logger.info("Starting %s v%s", settings.app_name, settings.app_version)
    # Crash recovery: mark runs with stale heartbeats FAILED (§11 idempotency).
    try:
        recovered = recover_stale_runs()
        if recovered:
            logger.warning("startup.recovered_stale_runs", count=recovered)
    except Exception:
        logger.exception("startup recovery failed (DB unavailable?)")
    automation.install_event_handlers()
    stop = threading.Event()
    scheduler = threading.Thread(
        target=_scheduler_loop, args=(stop,), daemon=True, name="doknow-scheduler"
    )
    scheduler.start()
    yield
    stop.set()
    logger.info("%s stopped", settings.app_name)


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    lifespan=lifespan,
    docs_url="/docs" if settings.debug else None,
    redoc_url=None,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# API routers (§13.2) — imported after app creation to avoid import cycles.
from app.api import routers  # noqa: E402

app.include_router(routers.api_router)
routers.install_exception_handlers(app)


@app.get("/health", tags=["system"])
def health() -> dict[str, Any]:
    """Liveness + dependency health probe."""
    status: dict[str, Any] = {
        "status": "ok",
        "app": settings.app_name,
        "version": settings.app_version,
    }
    try:
        get_redis().ping()
        status["redis"] = "ok"
    except Exception:
        status["redis"] = "degraded"
    return status
