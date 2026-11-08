from collections.abc import Generator
from decimal import Decimal
from uuid import uuid4

import numpy as np
import pymupdf
import pytest
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import doc_audit.tasks as tasks_module
from doc_audit.models import Base, Document, Extraction
from doc_audit.ocr import OCRResult


@pytest.fixture
def task_sessions() -> Generator[sessionmaker, None, None]:
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
    yield sessionmaker(bind=engine, expire_on_commit=False)
    engine.dispose()


def test_process_document_persists_extraction_and_audit(
    task_sessions, monkeypatch, tmp_path
) -> None:
    document_id = uuid4()
    with task_sessions() as db:
        db.add(
            Document(
                id=document_id,
                file_hash="a" * 64,
                original_name="receipt.jpg",
                mime_type="image/jpeg",
                storage_path=str(tmp_path / "receipt.jpg"),
                status="PENDING",
            )
        )
        db.commit()

    monkeypatch.setattr(tasks_module, "SessionLocal", task_sessions)
    monkeypatch.setattr(tasks_module, "_document_pages", lambda _document: [np.zeros((2, 2, 3))])
    monkeypatch.setattr(tasks_module, "preprocess_image", lambda image: image)
    monkeypatch.setattr(
        tasks_module,
        "run_ocr",
        lambda _image: OCRResult(
            text=(
                "CNPJ 11.222.333/0001-81\n"
                "Emissão 14/03/2026\n"
                "VALOR TOTAL R$ 10,00\n"
                "001 ARROZ 1,000 UN 10,00 10,00"
            ),
            confidence=90,
            engine_version="5.4.0",
            line_confidences={
                "CNPJ 11.222.333/0001-81": 90,
                "Emissão 14/03/2026": 90,
                "VALOR TOTAL R$ 10,00": 90,
            },
        ),
    )
    monkeypatch.setattr(tasks_module, "read_qr_code", lambda _image: None)
    monkeypatch.setattr(tasks_module.pytesseract, "get_tesseract_version", lambda: "5.4.0")

    tasks_module.process_document.run(str(document_id))

    with task_sessions() as db:
        document = db.get(Document, document_id)
        extraction = db.scalar(select(Extraction).where(Extraction.document_id == document_id))
        assert document is not None
        assert document.status == "DONE"
        assert extraction is not None
        assert extraction.total_amount == Decimal("10.00")
        assert extraction.audit is not None
        assert extraction.audit.arithmetic_ok is True
        assert extraction.audit.verdict == "APPROVED"


def test_pdf_page_is_rendered_at_300_dpi(tmp_path) -> None:
    pdf_path = tmp_path / "one-page.pdf"
    pdf = pymupdf.open()
    pdf.new_page(width=72, height=72).insert_text((10, 20), "Fiscal document")
    pdf.save(pdf_path)
    pdf.close()
    document = Document(
        file_hash="c" * 64,
        original_name="one-page.pdf",
        mime_type="application/pdf",
        storage_path=str(pdf_path),
        status="PENDING",
    )

    pages = list(tasks_module._document_pages(document))

    assert len(pages) == 1
    assert pages[0].shape[:2] == (300, 300)
