import uuid

import httpx
import pytest

from app.core.security import create_access_token
from app.db.sqlalchemy import SessionFactory
from app.main import create_app
from app.models.user import User


def make_pdf(text: str) -> bytes:
    """Build a minimal valid one-page PDF with correct xref offsets."""
    stream = f"BT /F1 24 Tf 100 700 Td ({text}) Tj ET".encode()
    objects = [
        b"<</Type/Catalog/Pages 2 0 R>>",
        b"<</Type/Pages/Kids[3 0 R]/Count 1>>",
        b"<</Type/Page/Parent 2 0 R/MediaBox[0 0 612 792]/Contents 4 0 R"
        b"/Resources<</Font<</F1 5 0 R>>>>>>",
        b"<</Length " + str(len(stream)).encode() + b">>stream\n" + stream + b"\nendstream",
        b"<</Type/Font/Subtype/Type1/BaseFont/Helvetica>>",
    ]
    out = b"%PDF-1.4\n"
    offsets = []
    for i, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += f"{i} 0 obj".encode() + body + b"endobj\n"
    xref_pos = len(out)
    out += b"xref\n0 " + str(len(objects) + 1).encode() + b"\n0000000000 65535 f \n"
    for off in offsets:
        out += f"{off:010d} 00000 n \n".encode()
    out += (
        b"trailer<</Size "
        + str(len(objects) + 1).encode()
        + b"/Root 1 0 R>>\nstartxref\n"
        + str(xref_pos).encode()
        + b"\n%%EOF"
    )
    return out


async def _create_user() -> tuple[User, str]:
    async with SessionFactory() as session:
        user = User(google_sub=f"sub-{uuid.uuid4()}", email=f"r-{uuid.uuid4()}@example.com")
        session.add(user)
        await session.commit()
        await session.refresh(user)
    return user, create_access_token(str(user.id))


@pytest.mark.asyncio
async def test_resume_upload_creates_vault_items(monkeypatch, clean_users_table):
    from sqlalchemy import select

    from app.agents.onboarding import ExtractedItem
    from app.models.vault import VaultItem
    from app.services.resume_service import ResumeExtraction

    user, token = await _create_user()

    extraction = ResumeExtraction(
        items=[ExtractedItem(category="skill", title="C++", details={"level": "advanced"})]
    )

    async def fake_completion(client, **kwargs):
        return extraction

    import app.services.resume_service as resume_svc

    monkeypatch.setattr(resume_svc, "structured_completion", fake_completion)

    app = create_app()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/api/v1/vault/resume",
            files={"file": ("resume.pdf", make_pdf("Hello Resume"), "application/pdf")},
            cookies={"ic_access": token},
        )
    assert resp.status_code == 200
    body = resp.json()
    assert body["items_created"][0]["title"] == "C++"
    assert body["s3_key"].startswith(f"{user.id}/")

    async with SessionFactory() as session:
        items = (
            (await session.execute(select(VaultItem).where(VaultItem.user_id == user.id)))
            .scalars()
            .all()
        )
        assert len(items) == 1 and items[0].source == "resume"


@pytest.mark.asyncio
async def test_resume_rejects_non_pdf(clean_users_table):
    user, token = await _create_user()
    app = create_app()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/api/v1/vault/resume",
            files={"file": ("x.txt", b"plain text", "text/plain")},
            cookies={"ic_access": token},
        )
    assert resp.status_code in (400, 415)
