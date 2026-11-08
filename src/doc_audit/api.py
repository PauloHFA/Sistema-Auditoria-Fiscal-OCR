import csv
import hashlib
import io
import json
import logging
import re
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from doc_audit.auditing import audit_extraction
from doc_audit.config import settings
from doc_audit.database import get_db
from doc_audit.models import Audit, Correction, Document, Extraction
from doc_audit.security import require_api_key
from doc_audit.tasks import process_document
from doc_audit.validation import normalize_amount

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1", dependencies=[Depends(require_api_key)])

SUPPORTED_SIGNATURES = {
    "image/jpeg": lambda data: data.startswith(b"\xff\xd8\xff"),
    "image/png": lambda data: data.startswith(b"\x89PNG\r\n\x1a\n"),
    "application/pdf": lambda data: b"%PDF-" in data[:1024],
}


class FieldCorrections(BaseModel):
    model_config = ConfigDict(extra="forbid")

    cnpj: str | None = Field(default=None, max_length=18)
    cpf: str | None = Field(default=None, max_length=14)
    issue_datetime: str | None = Field(default=None, max_length=40)
    total_amount: str | None = Field(default=None, max_length=32)
    access_key: str | None = Field(default=None, max_length=44)

    @field_validator("total_amount")
    @classmethod
    def normalize_corrected_amount(cls, value: str | None) -> str | None:
        return str(normalize_amount(value)) if value is not None else None


def _safe_original_name(name: str | None) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", Path(name or "document").name)
    return cleaned[:255] or "document"


def _document_query():
    return select(Document).options(
        selectinload(Document.extraction).selectinload(Extraction.items),
        selectinload(Document.extraction).selectinload(Extraction.audit),
    )


def _serialize_document(document: Document, *, mask_cnpj: bool = False) -> dict:
    extraction = document.extraction
    result: dict[str, object] = {
        "document_id": str(document.id),
        "status": document.status,
        "original_name": document.original_name,
        "created_at": document.created_at.isoformat(),
        "error": document.error_message,
    }
    if extraction:
        result["extraction"] = {
            "cnpj": (
                f"{extraction.cnpj[:2]}.{extraction.cnpj[2:5]}.***/****-{extraction.cnpj[-2:]}"
                if mask_cnpj and extraction.cnpj and len(re.sub(r"\D", "", extraction.cnpj)) == 14
                else extraction.cnpj
            ),
            "cpf": extraction.cpf,
            "issue_datetime": extraction.issue_datetime.isoformat()
            if extraction.issue_datetime
            else None,
            "total_amount": str(extraction.total_amount)
            if extraction.total_amount is not None
            else None,
            "access_key": extraction.access_key,
            "field_confidences": extraction.field_confidences,
            "items": [
                {
                    "description": item.description,
                    "quantity": str(item.quantity) if item.quantity is not None else None,
                    "unit_price": str(item.unit_price) if item.unit_price is not None else None,
                    "total_price": str(item.total_price) if item.total_price is not None else None,
                }
                for item in extraction.items
            ],
            "corrections": [
                {
                    "field": correction.field,
                    "original_value": correction.original_value,
                    "corrected_value": correction.corrected_value,
                    "corrected_at": correction.corrected_at.isoformat(),
                }
                for correction in extraction.corrections
            ],
        }
        if extraction.audit:
            audit = extraction.audit
            result["audit"] = {
                "items_sum": str(audit.items_sum) if audit.items_sum is not None else None,
                "total_amount": str(audit.total_amount) if audit.total_amount is not None else None,
                "difference": str(audit.difference) if audit.difference is not None else None,
                "arithmetic_ok": audit.arithmetic_ok,
                "cnpj_ok": audit.cnpj_ok,
                "cpf_ok": audit.cpf_ok,
                "access_key_ok": audit.access_key_ok,
                "issues": audit.issues,
                "verdict": audit.verdict,
            }
    return result


@router.post("/documents", status_code=status.HTTP_202_ACCEPTED)
async def upload_document(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
) -> dict:
    content = await file.read(settings.max_upload_bytes + 1)
    if len(content) > settings.max_upload_bytes:
        raise HTTPException(status_code=413, detail="Arquivo excede o limite configurado")
    if not content:
        raise HTTPException(status_code=400, detail="Arquivo vazio")
    mime_type = next(
        (
            mime
            for mime, signature_check in SUPPORTED_SIGNATURES.items()
            if signature_check(content)
        ),
        None,
    )
    if mime_type is None:
        raise HTTPException(status_code=415, detail="Tipo de arquivo não suportado ou inválido")

    file_hash = hashlib.sha256(content).hexdigest()
    existing = db.scalar(select(Document).where(Document.file_hash == file_hash))
    if existing:
        raise HTTPException(
            status_code=409,
            detail={"message": "Documento duplicado", "document_id": str(existing.id)},
        )

    document_id = uuid4()
    directory = Path(settings.upload_dir)
    directory.mkdir(parents=True, exist_ok=True)
    storage_path = (
        directory / f"{document_id}{'.pdf' if mime_type == 'application/pdf' else '.img'}"
    )
    storage_path.write_bytes(content)
    document = Document(
        id=document_id,
        file_hash=file_hash,
        original_name=_safe_original_name(file.filename),
        mime_type=mime_type,
        storage_path=str(storage_path),
        status="PENDING",
    )
    try:
        db.add(document)
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        storage_path.unlink(missing_ok=True)
        existing = db.scalar(select(Document).where(Document.file_hash == file_hash))
        if existing:
            raise HTTPException(
                status_code=409,
                detail={"message": "Documento duplicado", "document_id": str(existing.id)},
            ) from exc
        raise
    except Exception:
        db.rollback()
        storage_path.unlink(missing_ok=True)
        raise

    try:
        process_document.delay(str(document_id))
    except Exception as exc:
        document.status = "FAILED"
        document.error_message = "Não foi possível enfileirar o processamento"
        db.commit()
        logger.exception("failed to enqueue document", extra={"document_id": str(document_id)})
        raise HTTPException(status_code=503, detail="Fila de processamento indisponível") from exc
    return {"document_id": str(document_id), "status": document.status}


@router.get("/documents")
def list_documents(
    status_filter: str | None = Query(default=None, alias="status"),
    cnpj: str | None = None,
    created_from: datetime | None = None,
    created_to: datetime | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
) -> dict:
    query = _document_query().order_by(Document.created_at.desc()).limit(limit).offset(offset)
    if status_filter:
        query = query.where(Document.status == status_filter.upper())
    if created_from:
        query = query.where(Document.created_at >= created_from)
    if created_to:
        query = query.where(Document.created_at <= created_to)
    if cnpj:
        query = query.join(Extraction).where(Extraction.cnpj == re.sub(r"\D", "", cnpj))
    documents = db.scalars(query).unique().all()
    return {
        "items": [_serialize_document(document, mask_cnpj=True) for document in documents],
        "limit": limit,
        "offset": offset,
    }


@router.get("/documents/export")
def export_documents(
    format: str = Query(default="json", pattern="^(json|csv)$"),
    db: Session = Depends(get_db),
) -> StreamingResponse:
    documents = db.scalars(_document_query().order_by(Document.created_at.desc())).unique().all()
    rows = [_serialize_document(document) for document in documents]
    if format == "json":
        content = json.dumps(rows, ensure_ascii=False)
        return StreamingResponse(iter([content]), media_type="application/json")
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(
        ["document_id", "status", "cnpj", "issue_datetime", "total_amount", "access_key"]
    )
    for row in rows:
        extraction = row.get("extraction", {})
        writer.writerow(
            [
                row["document_id"],
                row["status"],
                extraction.get("cnpj"),
                extraction.get("issue_datetime"),
                extraction.get("total_amount"),
                extraction.get("access_key"),
            ]
        )
    return StreamingResponse(iter([output.getvalue()]), media_type="text/csv")


@router.get("/documents/{document_id}")
def get_document(document_id: UUID, db: Session = Depends(get_db)) -> dict:
    document = db.scalar(_document_query().where(Document.id == document_id))
    if document is None:
        raise HTTPException(status_code=404, detail="Documento não encontrado")
    return _serialize_document(document)


@router.patch("/documents/{document_id}/fields")
def correct_fields(
    document_id: UUID,
    fields: FieldCorrections,
    db: Session = Depends(get_db),
) -> dict:
    document = db.scalar(_document_query().where(Document.id == document_id))
    if document is None:
        raise HTTPException(status_code=404, detail="Documento não encontrado")
    extraction = document.extraction
    if extraction is None:
        raise HTTPException(status_code=409, detail="Documento ainda não possui extração")
    updates = fields.model_dump(exclude_unset=True, exclude_none=True)
    if not updates:
        raise HTTPException(status_code=422, detail="Informe ao menos um campo para corrigir")
    for field, value in updates.items():
        original = getattr(extraction, field)
        corrected: object = value
        if field in {"cnpj", "cpf", "access_key"}:
            corrected = re.sub(r"\D", "", value)
        if field == "total_amount":
            corrected = Decimal(value)
        elif field == "issue_datetime":
            try:
                corrected = datetime.fromisoformat(value)
            except ValueError as exc:
                raise HTTPException(
                    status_code=422, detail="Data deve estar em formato ISO 8601"
                ) from exc
        setattr(extraction, field, corrected)
        extraction.field_confidences = {
            **extraction.field_confidences,
            field: 100.0,
        }
        extraction.corrections.append(
            Correction(
                field=field,
                original_value=str(original) if original is not None else None,
                corrected_value=value,
            )
        )
    audit_values = audit_extraction(
        cnpj=extraction.cnpj,
        cpf=extraction.cpf,
        issue_datetime=extraction.issue_datetime,
        total_amount=extraction.total_amount,
        access_key=extraction.access_key,
        item_totals=[item.total_price for item in extraction.items if item.total_price is not None],
        field_confidences=extraction.field_confidences,
        tolerance=Decimal(settings.audit_tolerance),
        minimum_confidence=settings.min_field_confidence,
    )
    if extraction.audit is None:
        extraction.audit = Audit(extraction_id=extraction.id, **audit_values)
    else:
        for field, value in audit_values.items():
            setattr(extraction.audit, field, value)
    document.status = "DONE" if audit_values["verdict"] == "APPROVED" else "NEEDS_REVIEW"
    db.commit()
    db.refresh(document)
    return _serialize_document(document)


@router.delete("/documents/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_document(document_id: UUID, db: Session = Depends(get_db)) -> None:
    document = db.get(Document, document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="Documento não encontrado")
    storage_path = Path(document.storage_path)
    db.delete(document)
    db.commit()
    storage_path.unlink(missing_ok=True)
    processed_path = Path(settings.processed_dir) / str(document_id)
    if processed_path.exists():
        import shutil

        shutil.rmtree(processed_path)
