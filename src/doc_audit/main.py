from fastapi import Depends, FastAPI
from sqlalchemy import select
from sqlalchemy.orm import Session

from doc_audit.api import router
from doc_audit.database import get_db
from doc_audit.models import Document
from doc_audit.structured_logging import configure_json_logging

configure_json_logging()

app = FastAPI(
    title="DocAudit-OCR",
    description="Extração e auditoria local de documentos fiscais digitalizados",
    version="0.1.0",
)
app.include_router(router)


@app.get("/health", tags=["operations"])
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/metrics", tags=["operations"])
def metrics(db: Session = Depends(get_db)) -> dict:
    documents = db.scalars(select(Document)).all()
    durations = [
        (document.processed_at - document.created_at).total_seconds()
        for document in documents
        if document.processed_at and document.created_at
    ]
    return {
        "documents_by_status": {
            state: sum(document.status == state for document in documents)
            for state in ("PENDING", "PROCESSING", "DONE", "FAILED", "NEEDS_REVIEW")
        },
        "processing_failures": sum(document.status == "FAILED" for document in documents),
        "average_processing_time_seconds": sum(durations) / len(durations) if durations else 0.0,
    }
