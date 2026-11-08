from datetime import datetime
from decimal import Decimal

from doc_audit.auditing import audit_extraction


def test_approves_consistent_extraction_within_tolerance() -> None:
    result = audit_extraction(
        cnpj="11222333000181",
        cpf=None,
        issue_datetime=datetime(2026, 3, 14),
        total_amount=Decimal("10.00"),
        access_key=None,
        item_totals=[Decimal("9.95")],
        field_confidences={"cnpj": 90, "issue_datetime": 90, "total_amount": 90},
        tolerance=Decimal("0.05"),
        minimum_confidence=60,
    )
    assert result["arithmetic_ok"] is True
    assert result["verdict"] == "APPROVED"


def test_routes_arithmetic_mismatch_to_review() -> None:
    result = audit_extraction(
        cnpj="11222333000181",
        cpf=None,
        issue_datetime=datetime(2026, 3, 14),
        total_amount=Decimal("10.06"),
        access_key=None,
        item_totals=[Decimal("10.00")],
        field_confidences={"cnpj": 90, "issue_datetime": 90, "total_amount": 90},
        tolerance=Decimal("0.05"),
        minimum_confidence=60,
    )
    assert result["arithmetic_ok"] is False
    assert result["verdict"] == "NEEDS_REVIEW"


def test_routes_low_confidence_critical_field_to_review() -> None:
    result = audit_extraction(
        cnpj="11222333000181",
        cpf=None,
        issue_datetime=datetime(2026, 3, 14),
        total_amount=Decimal("10.00"),
        access_key=None,
        item_totals=[Decimal("10.00")],
        field_confidences={"cnpj": 40, "issue_datetime": 90, "total_amount": 90},
        tolerance=Decimal("0.05"),
        minimum_confidence=60,
    )
    assert result["verdict"] == "NEEDS_REVIEW"
    assert "Confiança de cnpj abaixo do limite" in result["issues"]
