"""Agent runtime: execute, observe, recover (whitepaper §11–§13.2).

Wraps every agent execution in an ``AgentRun`` record with full
observability:

- status lifecycle  RUNNING → SUCCEEDED / FAILED / TIMEOUT
- heartbeat thread so crashed runs are detectable
- bounded retries with exponential backoff (runs must be idempotent — the
  service layer guards against duplicate side effects)
- token cost accounting via the LLM client's usage callback
- LangGraph checkpoint persistence (PostgresSaver) keyed by run id, so a
  retry resumes the graph instead of restarting from scratch

Cancellation model: cooperative. The LLM client carries the HTTP timeout and
``RunContext.check_deadline()`` lets graph nodes bail out between steps; a
crashed or hung process leaves a stale heartbeat behind and
``recover_stale_runs()`` (called on startup / by the scheduler) marks those
runs FAILED so the originating trigger can safely fire again.
"""

from __future__ import annotations

import threading
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import timedelta
from typing import Any

import structlog
from sqlalchemy import update

from app.agents.llm import LLMClient, LLMUsage
from app.core.config import settings
from app.core.database import SessionLocal
from app.core.events import utcnow
from app.core.model_config import get_llm_override
from app.models.agent import AgentRun, AgentRunStatus, AgentType

logger = structlog.get_logger("app.agents.runtime")


class AgentTimeoutError(RuntimeError):
    """Raised by graph nodes when the run deadline is exceeded (cooperative)."""


@dataclass(slots=True)
class UsageAccumulator:
    """Run-level token accounting fed by the LLM client callback."""

    prompt_tokens: int = 0
    completion_tokens: int = 0

    def add(self, usage: LLMUsage) -> None:
        self.prompt_tokens += usage.prompt_tokens
        self.completion_tokens += usage.completion_tokens

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens


@dataclass(slots=True)
class RunContext:
    """Everything an agent graph receives: identity, budget, LLM access."""

    run_id: str
    agent_type: AgentType
    subject_type: str
    subject_id: str | None
    user_id: str | None
    payload: dict[str, Any]
    llm: LLMClient
    deadline: float  # monotonic timestamp
    log: Any  # structlog bound logger
    attempt: int = 0  # retry number; >0 means a resumed (checkpointed) run

    @property
    def graph_config(self) -> dict[str, Any]:
        """LangGraph config; thread_id = run id so retries resume the checkpoint."""
        return {"configurable": {"thread_id": self.run_id}}

    def seconds_left(self) -> float:
        return max(0.0, self.deadline - time.monotonic())

    def check_deadline(self) -> None:
        """Cooperative deadline check for long graphs (call between steps)."""
        if self.seconds_left() <= 0:
            raise AgentTimeoutError(f"run exceeded {settings.agent_timeout_seconds}s budget")


@dataclass(slots=True)
class AgentResult:
    """Terminal state of one agent execution (retry failures included)."""

    status: AgentRunStatus
    run_id: uuid.UUID
    output: dict[str, Any] | None
    error: dict[str, Any] | None
    retry_count: int


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _error_dict(exc: BaseException) -> dict[str, str]:
    return {"type": type(exc).__name__, "message": str(exc)[:1000]}


def _heartbeat_loop(run_id: uuid.UUID, stop: threading.Event) -> None:
    """Keep the run's heartbeat fresh while its graph executes."""
    while not stop.wait(settings.agent_heartbeat_seconds):
        try:
            with SessionLocal() as db:
                db.execute(
                    update(AgentRun).where(AgentRun.id == run_id).values(heartbeat_at=utcnow())
                )
                db.commit()
        except Exception:
            # Best effort: a missed tick just makes the run look slower to
            # recover_stale_runs, never aborts the run itself.
            logger.debug("agent.heartbeat_failed", run_id=str(run_id))


_checkpointer: Any = None
_checkpointer_failed = False


def get_checkpointer() -> Any:
    """Process-wide LangGraph PostgresSaver for checkpoint persistence.

    Uses its own psycopg connection pool (independent from the app engine so
    checkpoints survive app-level transaction patterns). ``setup()`` creates
    the checkpoint tables once. Failure is memoized: without this, an
    unreachable DB would cost every graph build a full connection timeout.
    """
    global _checkpointer, _checkpointer_failed
    if _checkpointer is not None:
        return _checkpointer
    if _checkpointer_failed:
        raise RuntimeError("checkpointer unavailable (initial setup failed)")
    from langgraph.checkpoint.postgres import PostgresSaver
    from psycopg_pool import ConnectionPool

    try:
        dsn = settings.database_url.replace("postgresql+psycopg://", "postgresql://", 1)
        pool = ConnectionPool(conninfo=dsn, min_size=1, max_size=4, open=True, timeout=5)
        saver = PostgresSaver(pool)
        saver.setup()
    except Exception:
        _checkpointer_failed = True
        raise
    _checkpointer = saver
    logger.info("agent.checkpointer_ready")
    return _checkpointer


def recover_stale_runs() -> int:
    """Mark RUNNING runs with stale heartbeats as FAILED (crash recovery).

    Called on app startup and by the scheduler. Because runs are idempotent,
    the trigger that spawned a recovered run can safely fire again.
    """
    cutoff = utcnow() - timedelta(seconds=settings.agent_timeout_seconds * 3)
    with SessionLocal() as db:
        result = db.execute(
            update(AgentRun)
            .where(
                AgentRun.status == AgentRunStatus.RUNNING,
                AgentRun.heartbeat_at < cutoff,
            )
            .values(
                status=AgentRunStatus.FAILED,
                error={"type": "StaleHeartbeat", "message": "recovered by stale-run sweep"},
                finished_at=utcnow(),
            )
        )
        db.commit()
        count = result.rowcount or 0
    if count:
        logger.warning("agent.recovered_stale_runs", count=count)
    return count


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def run_agent(
    fn: Callable[[RunContext], dict[str, Any]],
    *,
    agent_type: AgentType,
    subject_type: str,
    subject_id: str | None = None,
    user_id: uuid.UUID | None = None,
    payload: dict[str, Any] | None = None,
    max_retries: int | None = None,
    timeout_seconds: int | None = None,
) -> AgentResult:
    """Execute one agent run with bookkeeping.

    ``fn`` receives a :class:`RunContext` and returns a JSON-serializable dict
    (the run's ``output``). Agents do their LLM work through ``ctx.llm`` and
    mutate business state only through the service layer.
    """
    retries = settings.agent_max_retries if max_retries is None else max_retries
    timeout = settings.agent_timeout_seconds if timeout_seconds is None else timeout_seconds

    with SessionLocal() as db:
        run = AgentRun(
            agent_type=agent_type,
            subject_type=subject_type,
            subject_id=subject_id,
            user_id=user_id,
            input_payload=payload or {},
            status=AgentRunStatus.RUNNING,
            started_at=utcnow(),
            heartbeat_at=utcnow(),
        )
        db.add(run)
        db.commit()
        run_id = run.id

    log = logger.bind(
        agent_type=agent_type.value,
        run_id=str(run_id),
        subject_type=subject_type,
        subject_id=str(subject_id) if subject_id else None,
    )
    usage = UsageAccumulator()
    # Honor a user-configured model (base_url / api_key / model) if one is set;
    # otherwise fall back to env defaults inside LLMClient.
    override = get_llm_override()
    ctx = RunContext(
        run_id=str(run_id),
        agent_type=agent_type,
        subject_type=subject_type,
        subject_id=subject_id,
        user_id=str(user_id) if user_id else None,
        payload=payload or {},
        llm=LLMClient(
            usage_callback=usage.add,
            model=override.get("model"),
            api_key=override.get("api_key"),
            base_url=override.get("base_url"),
        ),
        deadline=time.monotonic() + timeout,
        log=log,
    )

    stop = threading.Event()
    threading.Thread(
        target=_heartbeat_loop, args=(run_id, stop), daemon=True, name=f"agent-hb-{run_id}"
    ).start()

    started = time.monotonic()
    last_error: dict[str, str] | None = None
    try:
        for attempt in range(retries + 1):
            usage.prompt_tokens = usage.completion_tokens = 0
            ctx.attempt = attempt
            try:
                output = fn(ctx)
                if not isinstance(output, dict):
                    output = {"result": output}
                duration_ms = int((time.monotonic() - started) * 1000)
                with SessionLocal() as db:
                    db.execute(
                        update(AgentRun)
                        .where(AgentRun.id == run_id)
                        .values(
                            status=AgentRunStatus.SUCCEEDED,
                            output=output,
                            finished_at=utcnow(),
                            duration_ms=duration_ms,
                            cost_tokens=usage.total_tokens,
                            heartbeat_at=utcnow(),
                            retry_count=attempt,
                        )
                    )
                    db.commit()
                log.info(
                    "agent.run_succeeded",
                    attempt=attempt,
                    tokens=usage.total_tokens,
                    duration_ms=duration_ms,
                )
                return AgentResult(AgentRunStatus.SUCCEEDED, run_id, output, None, attempt)
            except AgentTimeoutError as exc:
                last_error = _error_dict(exc)
                _finalize(run_id, AgentRunStatus.TIMEOUT, usage, started, last_error, attempt)
                log.warning("agent.run_timeout", attempt=attempt)
                return AgentResult(AgentRunStatus.TIMEOUT, run_id, None, last_error, attempt)
            except Exception as exc:
                last_error = _error_dict(exc)
                log.warning("agent.run_failed", attempt=attempt, error=last_error["message"])
                if attempt < retries:
                    # Idempotency note: the service layer's duplicate guards
                    # make re-running fn safe; retry resumes the LangGraph
                    # thread (checkpointer keyed by run id).
                    time.sleep(min(60.0, settings.agent_retry_backoff_seconds * (2**attempt)))
        _finalize(run_id, AgentRunStatus.FAILED, usage, started, last_error, retries)
        log.error("agent.run_exhausted_retries", retries=retries)
        return AgentResult(AgentRunStatus.FAILED, run_id, None, last_error, retries)
    finally:
        stop.set()


def _finalize(
    run_id: uuid.UUID,
    status: AgentRunStatus,
    usage: UsageAccumulator,
    started: float,
    error: dict[str, str] | None,
    retry_count: int,
) -> None:
    with SessionLocal() as db:
        db.execute(
            update(AgentRun)
            .where(AgentRun.id == run_id)
            .values(
                status=status,
                error=error or {},
                finished_at=utcnow(),
                duration_ms=int((time.monotonic() - started) * 1000),
                cost_tokens=usage.total_tokens,
                heartbeat_at=utcnow(),
                retry_count=retry_count,
            )
        )
        db.commit()
