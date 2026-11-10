import asyncio
import uuid
from io import BytesIO

import httpx
from botocore.client import BaseClient
from botocore.exceptions import BotoCoreError, ClientError, EndpointConnectionError
from pydantic import BaseModel
from pypdf import PdfReader
from pypdf.errors import PdfReadError
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.onboarding import ExtractedItem
from app.core.config import get_settings
from app.core.logging import get_logger
from app.db.s3 import RESUME_BUCKET
from app.gateway.llm import LLMGatewayError
from app.gateway.structured import structured_completion
from app.models.user import User
from app.services.vault_service import create_items, list_items

log = get_logger(__name__)

MAX_RESUME_BYTES = 10 * 1024 * 1024
MAX_RESUME_CHARS = 20000
MIN_RESUME_CHARS = 40

RESUME_SYSTEM_PROMPT = """Extract the candidate's verifiable experience from this resume
text into structured vault items. Use only information present in the text. For each
project include their role, stack, and outcomes in details. Never invent items."""


class ResumeExtraction(BaseModel):
    items: list[ExtractedItem] = []


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


async def _dedupe_items(
    db: AsyncSession, user_id, items: list[ExtractedItem], source: str
) -> list[ExtractedItem]:
    existing = await list_items(db, user_id)
    seen = {
        (row.title.strip().lower(), (row.source or "").strip().lower())
        for row in existing
        if row.title
    }
    out: list[ExtractedItem] = []
    for item in items:
        key = (item.title.strip().lower(), source.strip().lower())
        if not item.title.strip() or key in seen:
            continue
        seen.add(key)
        out.append(item)
    return out


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
            async with httpx.AsyncClient(timeout=get_settings().llm_client_timeout) as client:
                extraction = await structured_completion(
                    client,
                    system=RESUME_SYSTEM_PROMPT,
                    user_payload={"resume_text": text},
                    schema=ResumeExtraction,
                    request_id=request_id,
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
        unique = await _dedupe_items(db, user.id, extraction.items, "resume")
        created = await create_items(db, user.id, unique, "resume") if unique else []
        return {
            "items_created": [
                {"id": str(i.id), "category": i.category, "title": i.title} for i in created
            ],
            "s3_key": key,
            "items_skipped": max(0, len(extraction.items) - len(created)),
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
    except LLMGatewayError:
        log.warning(
            "resume_upload_failed",
            stage=stage,
            error_class="llm_gateway",
            user_id=user_id,
            status=503,
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
