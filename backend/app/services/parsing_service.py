"""Document parsing service (whitepaper §10.1) — Docling / MinerU.

Ingests the learner's reference materials (PDF/DOCX/PPTX/Markdown/HTML) into
structured text that feeds knowledge-system building. Backends are optional
extras (``pip install .[docling]`` / ``.[mineru]``): imports are lazy and a
missing backend produces a clear, actionable error instead of an import
crash. Parsing runs in background threads — uploads return immediately and
the source's status (UPLOADED → PARSING → PARSED/FAILED) is polled.

Both backends normalize to the same shape::

    {"text": str, "blocks": [...], "parser": "docling"|"mineru", "warnings": [...]}

Content quality applies to parsing too (§10.2): parse failures are recorded
as quality reports, so a bad document is visible before it misleads the
Knowledge Builder.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import threading
import uuid

import structlog
from sqlalchemy import select, update

from app.core.config import settings
from app.core.database import SessionLocal
from app.services import quality_service

logger = structlog.get_logger("app.services.parsing")

SUPPORTED_SUFFIXES = {".pdf", ".docx", ".pptx", ".md", ".markdown", ".html", ".htm", ".txt"}
MAX_UPLOAD_BYTES = 25 * 1024 * 1024  # 25 MB


class ParsingServiceError(Exception):
    pass


class UnsupportedFileTypeError(ParsingServiceError):
    pass


class FileTooLargeError(ParsingServiceError):
    pass


class BackendUnavailableError(ParsingServiceError):
    pass


# ---------------------------------------------------------------------------
# Ingestion (upload → parse pipeline)
# ---------------------------------------------------------------------------


def ingest_upload(
    *,
    goal_id: uuid.UUID,
    user_id: uuid.UUID,
    filename: str,
    data: bytes,
    backend: str | None = None,
) -> dict:
    """Store the upload, register the source, and parse in the background."""
    suffix = os.path.splitext(filename)[1].lower()
    if suffix not in SUPPORTED_SUFFIXES:
        raise UnsupportedFileTypeError(f"不支持的文件类型 {suffix or '(无后缀)'}")
    if len(data) > MAX_UPLOAD_BYTES:
        raise FileTooLargeError(f"文件超过 {MAX_UPLOAD_BYTES // (1024 * 1024)}MB 限制")

    upload_dir = os.path.abspath(settings.upload_dir)
    os.makedirs(upload_dir, exist_ok=True)
    storage_key = f"{uuid.uuid4().hex}{suffix}"
    storage_path = os.path.join(upload_dir, storage_key)
    with open(storage_path, "wb") as fh:
        fh.write(data)

    from app.models.content import ContentSource, SourceStatus, SourceType

    source_type = {
        ".pdf": "PDF",
        ".docx": "DOCX",
        ".pptx": "PPTX",
        ".md": "MARKDOWN",
        ".markdown": "MARKDOWN",
        ".html": "HTML",
        ".htm": "HTML",
        ".txt": "MARKDOWN",
    }.get(suffix, "PDF")
    with SessionLocal() as db:
        source = ContentSource(
            goal_id=goal_id,
            user_id=user_id,
            source_type=SourceType(source_type),
            status=SourceStatus.UPLOADED,
            filename=filename,
            storage_key=storage_key,
            mime_type=f"application/{'octet-stream' if suffix != '.pdf' else 'pdf'}",
            size_bytes=len(data),
            parser_backend=backend or settings.parser_backend,
        )
        db.add(source)
        db.commit()
        source_id = source.id
    threading.Thread(
        target=_parse_async,
        args=(source_id, storage_path, backend or settings.parser_backend),
        daemon=True,
    ).start()
    return {
        "source_id": str(source_id),
        "status": "UPLOADED",
        "parser": backend or settings.parser_backend,
    }


def list_sources(goal_id: uuid.UUID) -> list[dict]:
    from app.models.content import ContentSource

    with SessionLocal() as db:
        rows = db.scalars(
            select(ContentSource)
            .where(ContentSource.goal_id == goal_id, ContentSource.is_active.is_(True))
            .order_by(ContentSource.created_at.desc())
        ).all()
        return [
            {
                "id": str(r.id),
                "filename": r.filename,
                "source_type": r.source_type.value if r.source_type else None,
                "status": r.status.value if r.status else None,
                "parser_backend": r.parser_backend,
                "size_bytes": r.size_bytes,
                "error": r.parse_error or None,
                "excerpt": ((r.parsed_content or {}).get("text") or "")[:200],
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in rows
        ]


# ---------------------------------------------------------------------------
# Background parsing
# ---------------------------------------------------------------------------


def _parse_async(source_id: uuid.UUID, storage_path: str, backend: str) -> None:
    from app.models.content import ContentSource, SourceStatus

    with SessionLocal() as db:
        db.execute(
            update(ContentSource)
            .where(ContentSource.id == source_id)
            .values(status=SourceStatus.PARSING)
        )
        db.commit()
    try:
        parsed = parse_file(storage_path, backend=backend)
    except Exception as exc:
        logger.warning("parsing.failed", source_id=str(source_id), error=str(exc)[:300])
        with SessionLocal() as db:
            db.execute(
                update(ContentSource)
                .where(ContentSource.id == source_id)
                .values(
                    status=SourceStatus.FAILED,
                    parse_error={"type": type(exc).__name__, "message": str(exc)[:1000]},
                )
            )
            db.commit()
        quality_service.record_report(
            subject_type="ContentSource",
            subject_id=source_id,
            stage="PARSE",
            status="FAILED",
            findings=[{"category": "accuracy", "severity": "HIGH", "description": str(exc)[:500]}],
            recommendation="检查文件是否损坏/扫描件；或切换解析后端（docling/mineru）",
        )
        return
    with SessionLocal() as db:
        db.execute(
            update(ContentSource)
            .where(ContentSource.id == source_id)
            .values(status=SourceStatus.PARSED, parsed_content=parsed)
        )
        db.commit()
    logger.info("parsing.done", source_id=str(source_id), chars=len(parsed.get("text") or ""))


# ---------------------------------------------------------------------------
# Backends
# ---------------------------------------------------------------------------


def parse_file(path: str, *, backend: str | None = None) -> dict:
    """Parse one file with the selected backend. Returns the normalized shape."""
    backend = (backend or settings.parser_backend).lower()
    if backend == "mineru":
        return _parse_with_mineru(path)
    return _parse_with_docling(path)


def _parse_with_docling(path: str) -> dict:
    try:
        from docling.document_converter import DocumentConverter
    except ImportError as exc:
        raise BackendUnavailableError(
            "docling 未安装：pip install '.[docling]'（或设置 PARSER_BACKEND=mineru）"
        ) from exc
    converter = DocumentConverter()
    result = converter.convert(path)
    text = result.document.export_to_markdown()
    warnings: list[str] = []
    return {
        "text": text,
        "blocks": [{"kind": "markdown", "count": text.count("\n\n") + 1}],
        "parser": "docling",
        "warnings": warnings,
    }


def _parse_with_mineru(path: str) -> dict:
    """MinerU via its CLI (GPU-pipeline heavy; keep it out of the API process)."""
    if shutil.which("mineru") is None and shutil.which("magic-pdf") is None:
        raise BackendUnavailableError(
            "mineru 未安装：pip install '.[mineru]' 后再设置 PARSER_BACKEND=mineru"
        )
    binary = "mineru" if shutil.which("mineru") else "magic-pdf"
    with tempfile.TemporaryDirectory(prefix="doknow-mineru-") as out_dir:
        proc = subprocess.run(
            [binary, "-p", path, "-o", out_dir],
            capture_output=True,
            text=True,
            timeout=600,
            check=False,
        )
        if proc.returncode != 0:
            raise ParsingServiceError(f"mineru 解析失败：{proc.stderr[-500:]}")
        # MinerU writes markdown next to the parsed layout; pick the largest .md.
        md_files = []
        for root, _dirs, files in os.walk(out_dir):
            md_files.extend(os.path.join(root, f) for f in files if f.endswith(".md"))
        if not md_files:
            raise ParsingServiceError("mineru 未产出 markdown 文件")
        best = max(md_files, key=lambda f: os.path.getsize(f))
        with open(best, encoding="utf-8") as fh:
            text = fh.read()
    return {
        "text": text,
        "blocks": [{"kind": "markdown", "count": text.count("\n\n") + 1}],
        "parser": "mineru",
        "warnings": [],
    }
