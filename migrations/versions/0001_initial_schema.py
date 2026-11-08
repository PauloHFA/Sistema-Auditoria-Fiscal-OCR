"""Create the document processing schema."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0001_initial_schema"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    uuid_type = sa.Uuid(as_uuid=True)
    json_type = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")
    op.create_table(
        "documents",
        sa.Column("id", uuid_type, primary_key=True),
        sa.Column("file_hash", sa.String(64), nullable=False, unique=True, index=True),
        sa.Column("original_name", sa.String(255), nullable=False),
        sa.Column("mime_type", sa.String(32), nullable=False),
        sa.Column("storage_path", sa.String(1024), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, index=True),
        sa.Column("error_message", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("processed_at", sa.DateTime(timezone=True)),
    )
    op.create_table(
        "extractions",
        sa.Column("id", uuid_type, primary_key=True),
        sa.Column(
            "document_id",
            uuid_type,
            sa.ForeignKey("documents.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column("cnpj", sa.String(18)),
        sa.Column("cpf", sa.String(14)),
        sa.Column("issue_datetime", sa.DateTime(timezone=True)),
        sa.Column("total_amount", sa.Numeric(12, 2)),
        sa.Column("access_key", sa.String(44)),
        sa.Column("ocr_engine_version", sa.String(64)),
        sa.Column("raw_text", sa.Text(), nullable=False),
        sa.Column("field_confidences", json_type, nullable=False),
        sa.Column("qr_payload", json_type),
    )
    op.create_table(
        "items",
        sa.Column("id", uuid_type, primary_key=True),
        sa.Column(
            "extraction_id",
            uuid_type,
            sa.ForeignKey("extractions.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("line_no", sa.Integer(), nullable=False),
        sa.Column("description", sa.String(512), nullable=False),
        sa.Column("quantity", sa.Numeric(12, 3)),
        sa.Column("unit_price", sa.Numeric(12, 2)),
        sa.Column("total_price", sa.Numeric(12, 2)),
    )
    op.create_table(
        "audits",
        sa.Column("id", uuid_type, primary_key=True),
        sa.Column(
            "extraction_id",
            uuid_type,
            sa.ForeignKey("extractions.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column("items_sum", sa.Numeric(12, 2)),
        sa.Column("total_amount", sa.Numeric(12, 2)),
        sa.Column("difference", sa.Numeric(12, 2)),
        sa.Column("arithmetic_ok", sa.Boolean()),
        sa.Column("cnpj_ok", sa.Boolean()),
        sa.Column("cpf_ok", sa.Boolean()),
        sa.Column("access_key_ok", sa.Boolean()),
        sa.Column("issues", json_type, nullable=False),
        sa.Column("verdict", sa.String(32), nullable=False),
    )
    op.create_table(
        "corrections",
        sa.Column("id", uuid_type, primary_key=True),
        sa.Column(
            "extraction_id",
            uuid_type,
            sa.ForeignKey("extractions.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("field", sa.String(64), nullable=False),
        sa.Column("original_value", sa.Text()),
        sa.Column("corrected_value", sa.Text(), nullable=False),
        sa.Column("corrected_by", sa.String(128)),
        sa.Column("corrected_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("corrections")
    op.drop_table("audits")
    op.drop_table("items")
    op.drop_table("extractions")
    op.drop_table("documents")
