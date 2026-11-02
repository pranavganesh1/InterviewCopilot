import uuid
from io import BytesIO

import httpx
from botocore.client import BaseClient
from pydantic import BaseModel
from pypdf import PdfReader
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.onboarding import ExtractedItem
from app.core.config import get_settings
from app.db.s3 import RESUME_BUCKET
from app.gateway.structured import structured_completion
from app.models.user import User
from app.services.vault_service import create_items

MAX_RESUME_BYTES = 10 * 1024 * 1024
MAX_RESUME_CHARS = 20000

RESUME_SYSTEM_PROMPT = """Extract the candidate's verifiable experience from this resume
text into structured vault items. Use only information present in the text. For each
project include their role, stack, and outcomes in details. Never invent items."""


class ResumeExtraction(BaseModel):
    items: list[ExtractedItem] = []


def extract_pdf_text(data: bytes) -> str:
    reader = PdfReader(BytesIO(data))
    return "\n".join((page.extract_text() or "") for page in reader.pages)


async def process_resume(
    db: AsyncSession,
    s3: BaseClient,
    user: User,
    filename: str,
    data: bytes,
    request_id: str | None = None,
) -> dict:
    key = f"{user.id}/{uuid.uuid4()}-{filename}"
    s3.put_object(Bucket=RESUME_BUCKET, Key=key, Body=data, ContentType="application/pdf")

    text = extract_pdf_text(data)[:MAX_RESUME_CHARS]
    async with httpx.AsyncClient(timeout=get_settings().llm_client_timeout) as client:
        extraction = await structured_completion(
            client,
            system=RESUME_SYSTEM_PROMPT,
            user_payload={"resume_text": text},
            schema=ResumeExtraction,
            request_id=request_id,
        )
    created = await create_items(db, user.id, extraction.items, "resume")
    return {
        "items_created": [
            {"id": str(i.id), "category": i.category, "title": i.title} for i in created
        ],
        "s3_key": key,
    }
