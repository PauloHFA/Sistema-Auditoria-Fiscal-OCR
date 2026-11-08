import logging
import time
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from uuid import UUID

import pymupdf as fitz
import pytesseract
from celery import Task
from numpy import ndarray
from sqlalchemy import select

from doc_audit.auditing import audit_extraction
from doc_audit.config import settings
from doc_audit.database import SessionLocal
from doc_audit.models import Audit, Document, Extraction, Item
from doc_audit.ocr import read_qr_code, run_ocr
from doc_audit.parsers import (
    parse_access_key,
    parse_cnpj,
    parse_cpf,
    parse_issue_datetime,
    parse_items,
    parse_total,
)
from doc_audit.preprocessing import decode_image, preprocess_image
from doc_audit.worker import celery_app

logger = logging.getLogger(__name__)


def _log_stage(document_id: str, stage: str, started_at: float, page: int | None = None) -> None:
    context: dict[str, object] = {
        "document_id": document_id,
        "stage": stage,
        "duration_ms": round((time.perf_counter() - started_at) * 1000, 2),
    }
    if page is not None:
        context["page"] = page
    logger.info("document processing stage completed", extra=context)


def _document_pages(document: Document) -> Iterator[ndarray]:
    content = Path(document.storage_path).read_bytes()
    if document.mime_type == "application/pdf":
        pdf = fitz.open(stream=content, filetype="pdf")
        try:
            if len(pdf) > settings.max_pdf_pages:
                raise ValueError(f"PDF excede o limite de {settings.max_pdf_pages} páginas")
            for page_number in range(len(pdf)):
                page = pdf.load_page(page_number)
                pixmap = page.get_pixmap(matrix=fitz.Matrix(300 / 72, 300 / 72), alpha=False)
                yield decode_image(pixmap.tobytes("png"))
        finally:
            pdf.close()
    else:
        yield decode_image(content)


@celery_app.task(
    bind=True,
    name="doc_audit.process_document",
    max_retries=3,
    default_retry_delay=5,
    acks_late=True,
)
def process_document(self: Task, document_id: str) -> None:
    with SessionLocal() as db:
        document = db.scalar(select(Document).where(Document.id == UUID(document_id)))
        if document is None:
            logger.error(
                "document job references missing record", extra={"document_id": document_id}
            )
            return
        document.status = "PROCESSING"
        document.error_message = None
        db.commit()
        try:
            pages = _document_pages(document)
            raw_text_parts: list[str] = []
            ocr_results = []
            qr_payloads: list[str] = []
            processed_images = []
            engine_version = str(pytesseract.get_tesseract_version())
            render_started = time.perf_counter()
            for page_number, image in enumerate(pages, start=1):
                _log_stage(document_id, "document_render", render_started, page_number)
                stage_started = time.perf_counter()
                prepared = preprocess_image(image)
                _log_stage(document_id, "preprocessing", stage_started, page_number)
                stage_started = time.perf_counter()
                result = run_ocr(prepared)
                raw_text_parts.append(result.text)
                ocr_results.append(result)
                _log_stage(document_id, "ocr", stage_started, page_number)
                stage_started = time.perf_counter()
                qr_value = read_qr_code(image)
                if qr_value:
                    qr_payloads.append(qr_value)
                _log_stage(document_id, "qr", stage_started, page_number)
                if settings.save_preprocessed:
                    processed_images.append((page_number, prepared))
                render_started = time.perf_counter()

            stage_started = time.perf_counter()
            raw_text = "\n".join(raw_text_parts)
            cnpj = parse_cnpj(raw_text)
            cpf = parse_cpf(raw_text)
            issue_datetime = parse_issue_datetime(raw_text)
            total = parse_total(raw_text)
            access_key = parse_access_key(raw_text)
            qr_payload = {"raw": "\n".join(qr_payloads)} if qr_payloads else None
            qr_key = None
            if qr_payloads:
                qr_key = parse_access_key("\n".join(qr_payloads))
                if qr_key:
                    if access_key and access_key != qr_key:
                        logger.warning(
                            "QR code access key differs from OCR",
                            extra={"document_id": document_id},
                        )
                    access_key = qr_key

            items = parse_items(raw_text)
            lines = [
                (line, confidence)
                for result in ocr_results
                for line, confidence in result.line_confidences.items()
            ]

            def confidence_for(value: object) -> float:
                import re

                normalized = re.sub(r"\D", "", str(value))
                for line, confidence in lines:
                    if normalized and normalized in re.sub(r"\D", "", line):
                        return confidence
                return 0.0

            extraction = Extraction(
                document_id=document.id,
                cnpj=cnpj,
                cpf=cpf,
                issue_datetime=issue_datetime,
                total_amount=total,
                access_key=access_key,
                ocr_engine_version=engine_version,
                raw_text=raw_text,
                qr_payload=qr_payload,
                field_confidences={
                    "cnpj": confidence_for(cnpj) if cnpj else 0,
                    "cpf": confidence_for(cpf) if cpf else 0,
                    "issue_datetime": confidence_for(issue_datetime.strftime("%d%m%Y"))
                    if issue_datetime
                    else 0,
                    "total_amount": confidence_for(total) if total is not None else 0,
                    "access_key": 100.0
                    if qr_key
                    else confidence_for(access_key)
                    if access_key
                    else 0,
                },
            )
            _log_stage(document_id, "parsing", stage_started)
            db.add(extraction)
            db.flush()
            db.add_all(
                [
                    Item(
                        extraction_id=extraction.id,
                        line_no=line_no,
                        description=item["description"],
                        quantity=item["quantity"],
                        unit_price=item["unit_price"],
                        total_price=item["total_price"],
                    )
                    for line_no, item in enumerate(items, start=1)
                ]
            )

            stage_started = time.perf_counter()
            audit_values = audit_extraction(
                cnpj=cnpj,
                cpf=cpf,
                issue_datetime=issue_datetime,
                total_amount=total,
                access_key=access_key,
                item_totals=[item["total_price"] for item in items],
                field_confidences=extraction.field_confidences,
                tolerance=Decimal(settings.audit_tolerance),
                minimum_confidence=settings.min_field_confidence,
            )
            _log_stage(document_id, "audit", stage_started)
            db.add(
                Audit(
                    extraction_id=extraction.id,
                    **audit_values,
                )
            )
            if settings.save_preprocessed and processed_images:
                destination = Path(settings.processed_dir) / document_id
                destination.mkdir(parents=True, exist_ok=True)
                for page_number, image in processed_images:
                    import cv2

                    if not cv2.imwrite(str(destination / f"page-{page_number}.png"), image):
                        raise OSError("Falha ao salvar imagem pré-processada")
            document.status = "DONE" if audit_values["verdict"] == "APPROVED" else "NEEDS_REVIEW"
            document.processed_at = datetime.now(UTC)
            stage_started = time.perf_counter()
            db.commit()
            _log_stage(document_id, "persistence", stage_started)
        except Exception as exc:
            db.rollback()
            document = db.get(Document, UUID(document_id))
            if document is None:
                raise
            retries = self.request.retries
            if retries < self.max_retries:
                document.status = "PENDING"
                document.error_message = (
                    f"Falha temporária no processamento (tentativa {retries + 1})"
                )
                db.commit()
                self.retry(exc=exc, countdown=2**retries)
            document.status = "FAILED"
            document.error_message = str(exc)[:2000]
            document.processed_at = datetime.now(UTC)
            db.commit()
            logger.exception("document processing failed", extra={"document_id": document_id})


@celery_app.task(name="doc_audit.purge_expired_documents")
def purge_expired_documents() -> int:
    cutoff = datetime.now(UTC) - timedelta(days=settings.retention_days)
    with SessionLocal() as db:
        expired = db.scalars(select(Document).where(Document.created_at < cutoff)).all()
        expired_files = [(document.storage_path, document.id) for document in expired]
        for document in expired:
            db.delete(document)
        db.commit()
        for storage_path, document_id in expired_files:
            Path(storage_path).unlink(missing_ok=True)
            processed_path = Path(settings.processed_dir) / str(document_id)
            if processed_path.exists():
                import shutil

                shutil.rmtree(processed_path)
        return len(expired)
