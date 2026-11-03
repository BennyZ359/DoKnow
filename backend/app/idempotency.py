"""Durable request receipts, committed atomically with learning evidence.

A short, separately committed lease avoids holding a SQLite writer lock during
model requests. The final owner check and receipt share the business transaction.
An abandoned lease can be reclaimed; the old worker can no longer commit.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import json
import re
from uuid import uuid4

from fastapi import HTTPException, Request
from fastapi.routing import APIRoute
from sqlalchemy import DateTime, Integer, String, Text, delete, update
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm import Mapped, Session, mapped_column
from starlette.concurrency import run_in_threadpool
from starlette.datastructures import UploadFile
from starlette.responses import JSONResponse, Response

from .database import Base
from .models import Unit

LEASE_SECONDS = 120
DEFER_COMMIT = "idempotency_defer_commit"


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class RequestReceipt(Base):
    __tablename__ = "request_receipts"

    key: Mapped[str] = mapped_column(String(128), primary_key=True)
    fingerprint: Mapped[str] = mapped_column(String(64))
    owner_token: Mapped[str] = mapped_column(String(36))
    status: Mapped[str] = mapped_column(String(16))
    lease_until: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    response_status: Mapped[int | None] = mapped_column(Integer)
    response_body: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    resource_scope: Mapped[str | None] = mapped_column(String(80))


@dataclass(frozen=True)
class Claim:
    key: str
    owner_token: str


class ReceiptError(Exception):
    def __init__(self, status: int, code: str, detail: str, retry: bool = False):
        self.status = status
        self.code = code
        self.detail = detail
        self.retry = retry

    def response(self) -> JSONResponse:
        return JSONResponse(
            {"detail": self.detail, "code": self.code}, status_code=self.status,
            headers={"Retry-After": "2"} if self.retry else None,
        )


def busy() -> ReceiptError:
    return ReceiptError(409, "idempotency_in_progress", "这次提交仍在处理，请稍后使用同一次提交重试。", True)


async def request_fingerprint(request: Request) -> str:
    """Ignore JSON formatting and multipart boundaries, never store raw inputs."""
    if request.headers.get("content-type", "").lower().startswith("multipart/form-data"):
        parts = []
        form = await request.form()
        for name, value in form.multi_items():
            if isinstance(value, UploadFile):
                data = await value.read(10 * 1024 * 1024 + 1)
                await value.seek(0)
                if len(data) > 10 * 1024 * 1024:
                    raise HTTPException(413, "资料不能超过 10 MB。")
                filename = (value.filename or "document").replace("\\", "/").rsplit("/", 1)[-1]
                parts.append((name, "file", filename, sha256(data).hexdigest()))
            else:
                parts.append((name, "field", str(value)))
        payload = json.dumps(sorted(parts), ensure_ascii=True, separators=(",", ":"))
    else:
        data = await request.body()
        # The largest accepted JSON input is a million-character note. This also
        # allows JSON's six-byte escaped Unicode representation plus metadata.
        if len(data) > 8 * 1024 * 1024:
            raise HTTPException(413, "提交内容过大，请拆分后重试。")
        try:
            payload = json.dumps(json.loads(data), sort_keys=True, ensure_ascii=True, separators=(",", ":"))
        except (ValueError, UnicodeDecodeError):
            # Normal FastAPI validation still reports malformed JSON, without
            # writing a receipt or exposing the rejected input.
            payload = sha256(data).hexdigest()
    value = json.dumps([request.method, request.url.path, payload], ensure_ascii=True, separators=(",", ":"))
    return sha256(value.encode("utf-8")).hexdigest()


def acquire(factory, key: str, fingerprint: str) -> Claim | Response:
    """Claim one request across processes, or return its committed response."""
    owner = str(uuid4())
    for _ in range(3):
        now = utc_now()
        with factory() as db:
            existing = db.get(RequestReceipt, key)
            if existing is not None:
                if existing.fingerprint != fingerprint:
                    raise ReceiptError(409, "idempotency_conflict", "提交标识已用于其他内容，请先核对已保存记录。")
                if existing.status == "deleted":
                    raise ReceiptError(410, "idempotency_resource_deleted", "这次提交对应的学习目标或笔记已删除，不能恢复旧内容。")
                if existing.status == "complete":
                    return Response(existing.response_body, status_code=existing.response_status,
                                    media_type="application/json", headers={"Idempotency-Replayed": "true"})
                deadline = existing.lease_until
                if deadline.tzinfo is None:
                    deadline = deadline.replace(tzinfo=timezone.utc)
                if deadline > now:
                    raise busy()
                claimed = db.execute(update(RequestReceipt).where(
                    RequestReceipt.key == key, RequestReceipt.status == "pending",
                    RequestReceipt.owner_token == existing.owner_token, RequestReceipt.lease_until <= now,
                ).values(owner_token=owner, lease_until=now + timedelta(seconds=LEASE_SECONDS))
                    .execution_options(synchronize_session=False))
                db.commit()
                if claimed.rowcount == 1:
                    return Claim(key, owner)
                continue
            db.add(RequestReceipt(
                key=key, fingerprint=fingerprint, owner_token=owner, status="pending",
                lease_until=now + timedelta(seconds=LEASE_SECONDS), created_at=now,
            ))
            try:
                db.commit()
                return Claim(key, owner)
            except IntegrityError:
                # Another process won the unique key. Re-read its outcome.
                db.rollback()
    raise busy()


def release(factory, claim: Claim):
    with factory() as db:
        db.execute(delete(RequestReceipt).where(
            RequestReceipt.key == claim.key, RequestReceipt.owner_token == claim.owner_token,
            RequestReceipt.status == "pending",
        ))
        db.commit()


def finish(db: Session, claim: Claim, response: Response, resource_scope: str | None = None):
    """The receipt and every business mutation either commit together or neither."""
    completed = db.execute(update(RequestReceipt).where(
        RequestReceipt.key == claim.key, RequestReceipt.owner_token == claim.owner_token,
        RequestReceipt.status == "pending",
    ).values(status="complete", response_status=response.status_code,
             response_body=response.body.decode("utf-8"), completed_at=utc_now(), resource_scope=resource_scope))
    if completed.rowcount != 1:
        raise ReceiptError(409, "idempotency_expired_owner", "这次提交已由恢复请求接管，请同步记录后重试。", True)
    db.commit()


def erase_receipts(db: Session, resource_scope: str):
    """Delete retained response content, keeping a tombstone against recreation."""
    db.execute(update(RequestReceipt).where(
        RequestReceipt.resource_scope == resource_scope, RequestReceipt.status == "complete",
    ).values(status="deleted", response_body=None, response_status=410))


def response_scope(request: Request, db: Session, response: Response) -> str:
    unit_id = request.path_params.get("unit_id")
    if unit_id:
        unit = db.get(Unit, unit_id)
        return f"goal:{unit.goal_id}"
    if "goal_id" in request.path_params:
        return f"goal:{request.path_params['goal_id']}"
    result = json.loads(response.body)
    kind = "goal" if request.url.path == "/api/goals" or "goal_id" in request.path_params else "knowledge"
    return f"{kind}:{result['id']}"


class IdempotentRoute(APIRoute):
    def get_route_handler(self):
        original = super().get_route_handler()
        protected = (self.path in {"/api/goals", "/api/knowledge", "/api/knowledge/import",
                                   "/api/goals/{goal_id}", "/api/knowledge/{entry_id}"}
                     or self.path.startswith(("/api/units/", "/api/goals/")))

        async def handler(request: Request) -> Response:
            keys = request.headers.getlist("Idempotency-Key")
            if not protected or request.method not in {"POST", "PATCH"} or not keys:
                return await original(request)
            if len(keys) != 1 or not re.fullmatch(r"[A-Za-z0-9._:-]{8,128}", keys[0]):
                return ReceiptError(422, "idempotency_invalid_key", "提交标识格式无效，请重新发起操作。").response()
            factory = request.app.state.session_factory
            claim = None
            committed = False
            try:
                fingerprint = await request_fingerprint(request)
                claim = await run_in_threadpool(acquire, factory, keys[0], fingerprint)
                if isinstance(claim, Response):
                    return claim
                with factory() as db:
                    db.info[DEFER_COMMIT] = True
                    request.state.idempotency_session = db
                    try:
                        response = await original(request)
                        if 200 <= response.status_code < 300:
                            scope = await run_in_threadpool(response_scope, request, db, response)
                            await run_in_threadpool(finish, db, claim, response, scope)
                            committed = True
                            response.headers["Idempotency-Replayed"] = "false"
                        return response
                    finally:
                        # rollback after a successful commit is a no-op. On any
                        # exception it precedes removal of this worker's lease.
                        db.rollback()
                        del request.state.idempotency_session
            except ReceiptError as error:
                return error.response()
            except OperationalError:
                return ReceiptError(503, "idempotency_storage_busy", "学习记录暂时忙碌，请稍后使用同一次提交重试。", True).response()
            finally:
                try:
                    if isinstance(claim, Claim) and not committed:
                        try:
                            await run_in_threadpool(release, factory, claim)
                        except OperationalError:
                            # A process/network failure may prevent cleanup. The
                            # bounded lease permits retry instead of a permanent lock.
                            pass
                finally:
                    # Replays and fingerprint errors skip FastAPI's normal form
                    # exit stack. Close any spooled upload on those paths too.
                    await request.close()

        return handler
