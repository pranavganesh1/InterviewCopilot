"""Resume upload staged errors (stubbed LLM + storage; no network)."""

from __future__ import annotations

import uuid
from io import BytesIO

import httpx
import pytest
from pypdf import PdfWriter

from app.core.security import create_access_token
from app.db.sqlalchemy import SessionFactory
from app.gateway.llm import LLMGatewayError
from app.main import create_app
from app.models.user import User
from app.services.resume_service import MAX_RESUME_BYTES, ResumeUploadError


def make_pdf(text: str) -> bytes:
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


def make_encrypted_pdf() -> bytes:
    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    writer.encrypt("secret-password")
    buf = BytesIO()
    writer.write(buf)
    return buf.getvalue()


async def _user_token() -> tuple[User, str]:
    async with SessionFactory() as session:
        user = User(google_sub=f"sub-{uuid.uuid4()}", email=f"re-{uuid.uuid4()}@ex.com")
        session.add(user)
        await session.commit()
        await session.refresh(user)
    return user, create_access_token(str(user.id))


def _client(app):
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
    )


def _detail(resp) -> dict:
    body = resp.json()
    detail = body.get("detail")
    if isinstance(detail, dict):
        return detail
    return {"message": detail}


SAMPLE_TEXT = (
    "Python developer with FastAPI and Postgres projects. "
    "Built campus navigation and billing webhooks."
)


@pytest.fixture
def stub_storage_and_llm(monkeypatch):
    import app.services.resume_service as resume_svc
    from app.agents.onboarding import ExtractedItem
    from app.services.resume_service import ResumeExtraction

    store_calls: list[str] = []
    llm_calls: list[int] = []

    def fake_store(s3, *, user_id, filename, data):
        store_calls.append(filename)
        return f"{user_id}/stub-{filename}"

    async def fake_completion(client, **kwargs):
        llm_calls.append(1)
        return ResumeExtraction(
            items=[ExtractedItem(category="skill", title="Python", details={})]
        )

    monkeypatch.setattr(resume_svc, "store_resume_pdf", fake_store)
    monkeypatch.setattr(resume_svc, "structured_completion", fake_completion)
    return store_calls, llm_calls


@pytest.fixture
def readable_pdf_text(monkeypatch):
    """Minimal synthetic PDFs often yield no glyphs; stub extract for happy paths."""
    import app.services.resume_service as resume_svc

    monkeypatch.setattr(resume_svc, "extract_pdf_text", lambda _data: SAMPLE_TEXT)


@pytest.mark.asyncio
async def test_empty_file_422_no_store_or_llm(stub_storage_and_llm, clean_users_table):
    store_calls, llm_calls = stub_storage_and_llm
    _user, token = await _user_token()
    app = create_app()
    async with _client(app) as client:
        resp = await client.post(
            "/api/v1/vault/resume",
            files={"file": ("empty.pdf", b"", "application/pdf")},
            cookies={"ic_access": token},
        )
    assert resp.status_code == 422
    assert "empty" in _detail(resp)["message"].lower()
    assert store_calls == []
    assert llm_calls == []


@pytest.mark.asyncio
async def test_oversized_file_413_no_store_or_llm(
    stub_storage_and_llm, clean_users_table, monkeypatch
):
    import app.services.resume_service as resume_svc

    store_calls, llm_calls = stub_storage_and_llm
    monkeypatch.setattr(resume_svc, "MAX_RESUME_BYTES", 100)
    _user, token = await _user_token()
    app = create_app()
    async with _client(app) as client:
        resp = await client.post(
            "/api/v1/vault/resume",
            files={"file": ("big.pdf", b"x" * 150, "application/pdf")},
            cookies={"ic_access": token},
        )
    assert resp.status_code == 413
    assert "MB" in _detail(resp)["message"] or "exceeds" in _detail(resp)["message"].lower()
    assert store_calls == []
    assert llm_calls == []


@pytest.mark.asyncio
async def test_corrupted_pdf_422_no_store_or_llm(stub_storage_and_llm, clean_users_table):
    store_calls, llm_calls = stub_storage_and_llm
    _user, token = await _user_token()
    app = create_app()
    async with _client(app) as client:
        resp = await client.post(
            "/api/v1/vault/resume",
            files={"file": ("bad.pdf", b"%PDF-1.4\n%garbage", "application/pdf")},
            cookies={"ic_access": token},
        )
    assert resp.status_code == 422
    assert "couldn't read" in _detail(resp)["message"].lower()
    assert store_calls == []
    assert llm_calls == []


@pytest.mark.asyncio
async def test_encrypted_pdf_422_no_store_or_llm(stub_storage_and_llm, clean_users_table):
    store_calls, llm_calls = stub_storage_and_llm
    _user, token = await _user_token()
    app = create_app()
    async with _client(app) as client:
        resp = await client.post(
            "/api/v1/vault/resume",
            files={"file": ("locked.pdf", make_encrypted_pdf(), "application/pdf")},
            cookies={"ic_access": token},
        )
    assert resp.status_code == 422
    assert "password" in _detail(resp)["message"].lower()
    assert store_calls == []
    assert llm_calls == []


@pytest.mark.asyncio
async def test_no_text_pdf_422_no_store_or_llm(
    stub_storage_and_llm, clean_users_table, monkeypatch
):
    import app.services.resume_service as resume_svc

    store_calls, llm_calls = stub_storage_and_llm

    def blank(_data: bytes) -> str:
        return "   "

    monkeypatch.setattr(resume_svc, "extract_pdf_text", blank)
    _user, token = await _user_token()
    app = create_app()
    async with _client(app) as client:
        resp = await client.post(
            "/api/v1/vault/resume",
            files={"file": ("scan.pdf", make_pdf("ignored"), "application/pdf")},
            cookies={"ic_access": token},
        )
    assert resp.status_code == 422
    assert "no text" in _detail(resp)["message"].lower()
    assert store_calls == []
    assert llm_calls == []


@pytest.mark.asyncio
async def test_storage_error_503(
    stub_storage_and_llm, readable_pdf_text, clean_users_table, monkeypatch
):
    import app.services.resume_service as resume_svc

    _store_calls, llm_calls = stub_storage_and_llm

    def boom(*_a, **_k):
        raise ResumeUploadError(
            status=503,
            code="storage_unavailable",
            message="File storage is temporarily unavailable. Please retry in a minute.",
        )

    monkeypatch.setattr(resume_svc, "store_resume_pdf", boom)
    _user, token = await _user_token()
    app = create_app()
    async with _client(app) as client:
        resp = await client.post(
            "/api/v1/vault/resume",
            files={"file": ("ok.pdf", make_pdf("ok"), "application/pdf")},
            cookies={"ic_access": token},
        )
    assert resp.status_code == 503
    assert "storage" in _detail(resp)["message"].lower()
    assert llm_calls == []


@pytest.mark.asyncio
async def test_model_quota_503(
    stub_storage_and_llm, readable_pdf_text, clean_users_table, monkeypatch
):
    import app.services.resume_service as resume_svc

    store_calls, llm_calls = stub_storage_and_llm

    async def quota(*_a, **_k):
        raise LLMGatewayError("quota")

    monkeypatch.setattr(resume_svc, "structured_completion", quota)
    _user, token = await _user_token()
    app = create_app()
    async with _client(app) as client:
        resp = await client.post(
            "/api/v1/vault/resume",
            files={"file": ("ok.pdf", make_pdf("ok"), "application/pdf")},
            cookies={"ic_access": token},
        )
    assert resp.status_code == 503
    assert "retry" in _detail(resp)["message"].lower()
    assert store_calls  # storage happens before model
    assert llm_calls == []


@pytest.mark.asyncio
async def test_valid_pdf_success(
    stub_storage_and_llm, readable_pdf_text, clean_users_table
):
    store_calls, llm_calls = stub_storage_and_llm
    _user, token = await _user_token()
    app = create_app()
    async with _client(app) as client:
        resp = await client.post(
            "/api/v1/vault/resume",
            files={"file": ("ok.pdf", make_pdf("ok"), "application/pdf")},
            cookies={"ic_access": token},
        )
    assert resp.status_code == 200
    body = resp.json()
    assert body["items_created"][0]["title"] == "Python"
    assert store_calls and llm_calls


@pytest.mark.asyncio
async def test_reupload_does_not_duplicate(
    stub_storage_and_llm, readable_pdf_text, clean_users_table
):
    _user, token = await _user_token()
    app = create_app()
    pdf = make_pdf("ok")
    async with _client(app) as client:
        first = await client.post(
            "/api/v1/vault/resume",
            files={"file": ("ok.pdf", pdf, "application/pdf")},
            cookies={"ic_access": token},
        )
        second = await client.post(
            "/api/v1/vault/resume",
            files={"file": ("ok.pdf", pdf, "application/pdf")},
            cookies={"ic_access": token},
        )
    assert first.status_code == 200
    assert len(first.json()["items_created"]) == 1
    assert second.status_code == 200
    assert second.json()["items_created"] == []


@pytest.mark.asyncio
async def test_unexpected_500_has_correlation_id_no_internals(
    stub_storage_and_llm, readable_pdf_text, clean_users_table, monkeypatch
):
    import app.services.resume_service as resume_svc

    async def boom(*_a, **_k):
        raise RuntimeError("secret db password=hunter2 stacktrace")

    monkeypatch.setattr(resume_svc, "create_items", boom)
    _user, token = await _user_token()
    app = create_app()
    async with _client(app) as client:
        resp = await client.post(
            "/api/v1/vault/resume",
            files={"file": ("ok.pdf", make_pdf("ok"), "application/pdf")},
            cookies={"ic_access": token},
            headers={"x-request-id": "corr-test-1"},
        )
    assert resp.status_code == 500
    detail = _detail(resp)
    assert detail.get("correlation_id") == "corr-test-1"
    assert "hunter2" not in resp.text
    assert "stacktrace" not in resp.text.lower()
    assert "something went wrong" in detail["message"].lower()


@pytest.mark.asyncio
async def test_non_pdf_415(stub_storage_and_llm, clean_users_table):
    store_calls, llm_calls = stub_storage_and_llm
    _user, token = await _user_token()
    app = create_app()
    async with _client(app) as client:
        resp = await client.post(
            "/api/v1/vault/resume",
            files={"file": ("x.txt", b"plain", "text/plain")},
            cookies={"ic_access": token},
        )
    assert resp.status_code == 415
    assert store_calls == []
    assert llm_calls == []


def test_max_resume_bytes_constant():
    assert MAX_RESUME_BYTES == 10 * 1024 * 1024
