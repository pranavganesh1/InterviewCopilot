import asyncio
import json
import uuid
from io import BytesIO
from typing import Any

import httpx
from botocore.client import BaseClient
from botocore.exceptions import BotoCoreError, ClientError, EndpointConnectionError
from pydantic import BaseModel, model_validator
from pypdf import PdfReader
from pypdf.errors import PdfReadError
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.onboarding import ITEM_CATEGORIES_SET, ExtractedItem
from app.core.config import get_settings
from app.core.logging import get_logger
from app.db.s3 import RESUME_BUCKET
from app.gateway.llm import LLMCause, LLMGatewayError
from app.gateway.structured import structured_completion
from app.models.user import User
from app.services.vault_service import sync_resume_items

log = get_logger(__name__)

MAX_RESUME_BYTES = 10 * 1024 * 1024
MAX_RESUME_CHARS = 20000
MIN_RESUME_CHARS = 40

# Map common LLM category labels onto the vault enum.
_CATEGORY_ALIASES = {
    "experience": "other",
    "work": "other",
    "work experience": "other",
    "job": "other",
    "employment": "other",
    "position": "other",
    "certification": "achievement",
    "certifications": "achievement",
    "award": "achievement",
    "awards": "achievement",
    "honor": "achievement",
    "course": "education",
    "courses": "education",
    "degree": "education",
    "school": "education",
    "university": "education",
    "technology": "skill",
    "technologies": "skill",
    "tech": "skill",
    "tools": "skill",
    "language": "skill",
    "languages": "skill",
    "programming": "skill",
    "research": "project",
    "personal project": "project",
    "open source": "project",
}

RESUME_SYSTEM_PROMPT = """Extract the candidate's verifiable experience from this resume
text into structured vault items. Use only information present in the text. Never invent items.

Rules for each item:
- category MUST be exactly one of: project, internship, skill, achievement, education, other
- title: short string (max 255 chars)
- details: object whose values are ALL strings (role, stack, outcomes, dates as strings)
For each project include role, stack, and outcomes in details."""


def _stringify_detail_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, (dict, list)):
        return json.dumps(value, separators=(",", ":"))
    return str(value)


def _normalize_category(raw: Any) -> str:
    cat = str(raw or "other").strip().lower()
    cat = _CATEGORY_ALIASES.get(cat, cat)
    if cat not in ITEM_CATEGORIES_SET:
        return "other"
    return cat


class ResumeExtraction(BaseModel):
    items: list[ExtractedItem] = []

    @model_validator(mode="before")
    @classmethod
    def coerce_items(cls, data: Any) -> Any:
        """Tolerate common LLM shape mistakes without inventing resume facts."""
        if not isinstance(data, dict):
            return data
        items = data.get("items")
        if not isinstance(items, list):
            return data
        fixed_items: list[dict] = []
        for item in items:
            # Already-validated models (e.g. test stubs) must not be dropped.
            if isinstance(item, ExtractedItem):
                fixed_items.append(item.model_dump())
                continue
            if isinstance(item, BaseModel):
                item = item.model_dump()
            if not isinstance(item, dict):
                continue
            fixed = dict(item)
            fixed["category"] = _normalize_category(fixed.get("category"))
            title = fixed.get("title")
            if title is None:
                continue
            if not isinstance(title, str):
                title = str(title)
            fixed["title"] = title.strip()[:255]
            if not fixed["title"]:
                continue
            details = fixed.get("details")
            if details is None:
                fixed["details"] = {}
            elif isinstance(details, dict):
                fixed["details"] = {
                    str(k): _stringify_detail_value(v) for k, v in details.items()
                }
            else:
                fixed["details"] = {"note": _stringify_detail_value(details)}
            fixed_items.append(fixed)
        return {**data, "items": fixed_items}


class ResumeUploadError(Exception):
    """User-safe resume upload failure with HTTP status + machine code."""

    def __init__(self, *, status: int, code: str, message: str):
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message


def extract_pdf_text(data: bytes) -> str:
    """Return concatenated page text, or raise ResumeUploadError for bad PDFs."""
    try:
        reader = PdfReader(BytesIO(data))
    except PdfReadError as exc:
        raise ResumeUploadError(
            status=422,
            code="pdf_unreadable",
            message=(
                "We couldn't read this PDF. Try exporting it again without a password."
            ),
        ) from exc
    except Exception as exc:
        # pypdf can raise other parse errors for truncated/corrupt files.
        raise ResumeUploadError(
            status=422,
            code="pdf_unreadable",
            message=(
                "We couldn't read this PDF. Try exporting it again without a password."
            ),
        ) from exc

    if getattr(reader, "is_encrypted", False):
        try:
            unlocked = reader.decrypt("")  # type: ignore[attr-defined]
        except Exception as exc:
            raise ResumeUploadError(
                status=422,
                code="pdf_encrypted",
                message=(
                    "We couldn't read this PDF. Try exporting it again without a password."
                ),
            ) from exc
        if not unlocked:
            raise ResumeUploadError(
                status=422,
                code="pdf_encrypted",
                message=(
                    "We couldn't read this PDF. Try exporting it again without a password."
                ),
            )

    try:
        return "\n".join((page.extract_text() or "") for page in reader.pages)
    except Exception as exc:
        raise ResumeUploadError(
            status=422,
            code="pdf_unreadable",
            message=(
                "We couldn't read this PDF. Try exporting it again without a password."
            ),
        ) from exc


def validate_resume_bytes(data: bytes, *, content_type: str | None) -> None:
    ctype = (content_type or "").split(";")[0].strip().lower()
    if ctype and ctype not in ("application/pdf", "application/x-pdf"):
        raise ResumeUploadError(
            status=415,
            code="unsupported_media_type",
            message="Only PDF resumes are supported",
        )
    if not data:
        raise ResumeUploadError(
            status=422,
            code="empty_file",
            message="This file is empty. Choose a PDF resume and try again.",
        )
    if len(data) > MAX_RESUME_BYTES:
        raise ResumeUploadError(
            status=413,
            code="file_too_large",
            message=f"Resume exceeds {MAX_RESUME_BYTES // (1024 * 1024)} MB",
        )


def store_resume_pdf(s3: BaseClient, *, user_id: str, filename: str, data: bytes) -> str:
    """Upload the PDF after extraction. Raises ResumeUploadError on storage failure."""
    from app.db.s3 import ensure_bucket

    key = f"{user_id}/{uuid.uuid4()}-{filename}"
    try:
        ensure_bucket(s3, RESUME_BUCKET)
        s3.put_object(
            Bucket=RESUME_BUCKET, Key=key, Body=data, ContentType="application/pdf"
        )
    except ResumeUploadError:
        raise
    except (EndpointConnectionError, BotoCoreError, ClientError, OSError) as exc:
        raise ResumeUploadError(
            status=503,
            code="storage_unavailable",
            message=(
                "File storage is temporarily unavailable. Please retry in a minute."
            ),
        ) from exc
    return key


async def process_resume(
    db: AsyncSession,
    s3: BaseClient,
    user: User,
    filename: str,
    data: bytes,
    *,
    content_type: str | None = "application/pdf",
    request_id: str | None = None,
) -> dict:
    """Validate + extract text first; only then store and call the model."""
    user_id = str(user.id)
    stage = "validate"
    try:
        validate_resume_bytes(data, content_type=content_type)

        stage = "extract"
        text = (await asyncio.to_thread(extract_pdf_text, data)).strip()
        if len(text) < MIN_RESUME_CHARS:
            raise ResumeUploadError(
                status=422,
                code="no_text",
                message="No text found in this PDF. Upload a text-based PDF.",
            )
        text = text[:MAX_RESUME_CHARS]

        stage = "store"
        key = await asyncio.to_thread(
            store_resume_pdf, s3, user_id=user_id, filename=filename, data=data
        )

        stage = "model"
        try:
            # Resume extraction is large structured JSON; pass an explicit budget
            # so the gateway does not apply the short interview-turn 9s primary cap.
            model_timeout = float(get_settings().llm_client_timeout)
            async with httpx.AsyncClient(timeout=model_timeout) as client:
                extraction = await structured_completion(
                    client,
                    system=RESUME_SYSTEM_PROMPT,
                    user_payload={"resume_text": text},
                    schema=ResumeExtraction,
                    request_id=request_id,
                    timeout_s=model_timeout,
                )
        except LLMGatewayError:
            raise
        except Exception as exc:
            raise ResumeUploadError(
                status=503,
                code="model_unavailable",
                message="The model is busy right now — retry in a minute.",
            ) from exc

        stage = "persist"
        # Profile Vault is the source of truth — incremental sync, not bulk insert.
        sync = await sync_resume_items(db, user.id, extraction.items)
        skipped_detail = list(sync.get("items_skipped") or [])
        return {
            **sync,
            "s3_key": key,
            "items_skipped_detail": skipped_detail,
            # Backward-compatible scalar for older clients.
            "items_skipped": int(sync.get("counts", {}).get("skipped") or 0),
            "mode": "incremental_sync",
        }
    except ResumeUploadError as exc:
        log.warning(
            "resume_upload_failed",
            stage=stage,
            error_class=exc.code,
            user_id=user_id,
            status=exc.status,
        )
        raise
    except LLMGatewayError as exc:
        cause = getattr(exc.cause, "value", str(getattr(exc, "cause", "unknown")))
        status = 422 if cause == LLMCause.schema_rejected.value else 503
        log.warning(
            "resume_upload_failed",
            stage=stage,
            error_class="llm_gateway",
            cause=cause,
            error=str(exc)[:200],
            user_id=user_id,
            status=status,
            request_id=request_id,
        )
        raise
    except Exception:
        log.exception(
            "resume_upload_failed",
            stage=stage,
            error_class="unexpected",
            user_id=user_id,
            status=500,
        )
        raise


def latest_resume_object_key(s3: BaseClient, *, user_id: str) -> str | None:
    """Return the most recent resume object key for this user, if any."""
    prefix = f"{user_id}/"
    try:
        resp = s3.list_objects_v2(Bucket=RESUME_BUCKET, Prefix=prefix)
    except (EndpointConnectionError, BotoCoreError, ClientError, OSError):
        return None
    contents = list(resp.get("Contents") or [])
    if not contents:
        return None
    contents.sort(key=lambda o: o.get("LastModified") or 0, reverse=True)
    key = contents[0].get("Key")
    return str(key) if key else None


async def reprocess_latest_resume(
    db: AsyncSession,
    s3: BaseClient,
    user: User,
    *,
    request_id: str | None = None,
) -> dict:
    """Re-run extraction on the latest stored PDF without requiring a re-upload."""
    user_id = str(user.id)
    key = await asyncio.to_thread(latest_resume_object_key, s3, user_id=user_id)
    if not key:
        raise ResumeUploadError(
            status=404,
            code="no_stored_resume",
            message="No stored resume found. Upload a PDF resume first.",
        )
    try:
        obj = await asyncio.to_thread(s3.get_object, Bucket=RESUME_BUCKET, Key=key)
        data = obj["Body"].read()
    except (EndpointConnectionError, BotoCoreError, ClientError, OSError, KeyError) as exc:
        raise ResumeUploadError(
            status=503,
            code="storage_unavailable",
            message="File storage is temporarily unavailable. Please retry in a minute.",
        ) from exc
    filename = key.rsplit("/", 1)[-1]
    # Skip re-storing: process_resume always stores. Use extract+sync path instead.
    stage = "extract"
    try:
        text = (await asyncio.to_thread(extract_pdf_text, data)).strip()
        if len(text) < MIN_RESUME_CHARS:
            raise ResumeUploadError(
                status=422,
                code="no_text",
                message="No text found in this PDF. Upload a text-based PDF.",
            )
        text = text[:MAX_RESUME_CHARS]
        stage = "model"
        model_timeout = float(get_settings().llm_client_timeout)
        async with httpx.AsyncClient(timeout=model_timeout) as client:
            extraction = await structured_completion(
                client,
                system=RESUME_SYSTEM_PROMPT,
                user_payload={"resume_text": text},
                schema=ResumeExtraction,
                request_id=request_id,
                timeout_s=model_timeout,
            )
        stage = "persist"
        sync = await sync_resume_items(db, user.id, extraction.items)
        skipped_detail = list(sync.get("items_skipped") or [])
        return {
            **sync,
            "s3_key": key,
            "items_skipped_detail": skipped_detail,
            "items_skipped": int(sync.get("counts", {}).get("skipped") or 0),
            "mode": "reprocess_incremental_sync",
            "reused_stored_resume": True,
        }
    except ResumeUploadError:
        raise
    except LLMGatewayError:
        raise
    except Exception:
        log.exception(
            "resume_reprocess_failed",
            stage=stage,
            error_class="unexpected",
            user_id=user_id,
            status=500,
        )
        raise
