from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.types import JSON, Uuid


def utc_now() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    pass


json_type = JSON().with_variant(JSONB, "postgresql")


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    file_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    original_name: Mapped[str] = mapped_column(String(255))
    mime_type: Mapped[str] = mapped_column(String(32))
    storage_path: Mapped[str] = mapped_column(String(1024))
    status: Mapped[str] = mapped_column(String(32), index=True, default="PENDING")
    error_message: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    extraction: Mapped["Extraction | None"] = relationship(
        back_populates="document", cascade="all, delete-orphan", uselist=False
    )


class Extraction(Base):
    __tablename__ = "extractions"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    document_id: Mapped[UUID] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), unique=True
    )
    cnpj: Mapped[str | None] = mapped_column(String(18))
    cpf: Mapped[str | None] = mapped_column(String(14))
    issue_datetime: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    total_amount: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    access_key: Mapped[str | None] = mapped_column(String(44))
    ocr_engine_version: Mapped[str | None] = mapped_column(String(64))
    raw_text: Mapped[str] = mapped_column(Text)
    field_confidences: Mapped[dict[str, float]] = mapped_column(json_type, default=dict)
    qr_payload: Mapped[dict[str, str] | None] = mapped_column(json_type)
    document: Mapped[Document] = relationship(back_populates="extraction")
    items: Mapped[list["Item"]] = relationship(cascade="all, delete-orphan")
    audit: Mapped["Audit | None"] = relationship(cascade="all, delete-orphan", uselist=False)
    corrections: Mapped[list["Correction"]] = relationship(cascade="all, delete-orphan")


class Item(Base):
    __tablename__ = "items"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    extraction_id: Mapped[UUID] = mapped_column(ForeignKey("extractions.id", ondelete="CASCADE"))
    line_no: Mapped[int] = mapped_column(Integer)
    description: Mapped[str] = mapped_column(String(512))
    quantity: Mapped[Decimal | None] = mapped_column(Numeric(12, 3))
    unit_price: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    total_price: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))


class Audit(Base):
    __tablename__ = "audits"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    extraction_id: Mapped[UUID] = mapped_column(
        ForeignKey("extractions.id", ondelete="CASCADE"), unique=True
    )
    items_sum: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    total_amount: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    difference: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    arithmetic_ok: Mapped[bool | None] = mapped_column(Boolean)
    cnpj_ok: Mapped[bool | None] = mapped_column(Boolean)
    cpf_ok: Mapped[bool | None] = mapped_column(Boolean)
    access_key_ok: Mapped[bool | None] = mapped_column(Boolean)
    issues: Mapped[list[str]] = mapped_column(json_type, default=list)
    verdict: Mapped[str] = mapped_column(String(32))


class Correction(Base):
    __tablename__ = "corrections"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    extraction_id: Mapped[UUID] = mapped_column(ForeignKey("extractions.id", ondelete="CASCADE"))
    field: Mapped[str] = mapped_column(String(64))
    original_value: Mapped[str | None] = mapped_column(Text)
    corrected_value: Mapped[str] = mapped_column(Text)
    corrected_by: Mapped[str | None] = mapped_column(String(128))
    corrected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    extraction: Mapped[Extraction] = relationship(back_populates="corrections")
