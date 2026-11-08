from collections.abc import Generator
from datetime import datetime
from decimal import Decimal
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import doc_audit.api as api_module
from doc_audit.config import settings
from doc_audit.database import get_db
from doc_audit.main import app
from doc_audit.models import Base, Document, Extraction, Item


@pytest.fixture
def test_sessions() -> Generator[sessionmaker, None, None]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(engine, "connect")
    def enable_foreign_keys(connection, _record) -> None:
        cursor = connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(engine)
    test_sessions = sessionmaker(bind=engine, expire_on_commit=False)
    yield test_sessions
    engine.dispose()


@pytest.fixture
def client(tmp_path, monkeypatch, test_sessions) -> Generator[TestClient, None, None]:
    def override_get_db():
        with test_sessions() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    monkeypatch.setattr(settings, "upload_dir", str(tmp_path / "uploads"))
    monkeypatch.setattr(api_module.process_document, "delay", lambda *_args: None)
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def test_upload_returns_pending_and_duplicate_returns_original_id(client: TestClient) -> None:
    headers = {"X-API-Key": settings.api_key}
    content = b"\xff\xd8\xffsynthetic-jpeg"

    first = client.post(
        "/api/v1/documents",
        headers=headers,
        files={"file": ("receipt.jpg", content, "image/jpeg")},
    )
    assert first.status_code == 202
    document_id = first.json()["document_id"]
    assert first.json()["status"] == "PENDING"
    assert (
        client.get(f"/api/v1/documents/{document_id}", headers=headers).json()["status"]
        == "PENDING"
    )

    duplicate = client.post(
        "/api/v1/documents",
        headers=headers,
        files={"file": ("copy.jpg", content, "image/jpeg")},
    )
    assert duplicate.status_code == 409
    assert duplicate.json()["detail"]["document_id"] == document_id


def test_upload_rejects_executable_disguised_as_image(client: TestClient) -> None:
    response = client.post(
        "/api/v1/documents",
        headers={"X-API-Key": settings.api_key},
        files={"file": ("fake.jpg", b"MZ executable", "image/jpeg")},
    )
    assert response.status_code == 415


def test_document_routes_require_api_key(client: TestClient) -> None:
    response = client.get("/api/v1/documents")
    assert response.status_code == 401
    assert client.get("/health").status_code == 200


def test_manual_correction_preserves_original_and_reaudits(
    client: TestClient, test_sessions
) -> None:
    document_id = uuid4()
    extraction = Extraction(
        cnpj="00000000000000",
        issue_datetime=datetime(2026, 3, 14),
        total_amount=Decimal("10.00"),
        raw_text="OCR text",
        field_confidences={"cnpj": 40, "issue_datetime": 90, "total_amount": 90},
        items=[Item(line_no=1, description="ARROZ", total_price=Decimal("10.00"))],
    )
    with test_sessions() as db:
        db.add(
            Document(
                id=document_id,
                file_hash="b" * 64,
                original_name="receipt.jpg",
                mime_type="image/jpeg",
                storage_path="missing-test-file.img",
                status="NEEDS_REVIEW",
                extraction=extraction,
            )
        )
        db.commit()

    headers = {"X-API-Key": settings.api_key}
    response = client.patch(
        f"/api/v1/documents/{document_id}/fields",
        headers=headers,
        json={"cnpj": "11.222.333/0001-81"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "DONE"
    assert payload["audit"]["verdict"] == "APPROVED"
    assert payload["extraction"]["cnpj"] == "11222333000181"
    assert payload["extraction"]["corrections"][0]["original_value"] == "00000000000000"
    assert payload["extraction"]["corrections"][0]["corrected_value"] == "11.222.333/0001-81"

    listed = client.get("/api/v1/documents?cnpj=11222333000181", headers=headers).json()
    assert listed["items"][0]["extraction"]["cnpj"] == "11.222.***/****-81"
