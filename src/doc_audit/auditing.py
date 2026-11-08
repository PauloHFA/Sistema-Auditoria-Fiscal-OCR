from datetime import UTC, datetime
from decimal import Decimal

from doc_audit.validation import is_valid_access_key, is_valid_cnpj, is_valid_cpf


def audit_extraction(
    *,
    cnpj: str | None,
    cpf: str | None,
    issue_datetime: datetime | None,
    total_amount: Decimal | None,
    access_key: str | None,
    item_totals: list[Decimal],
    field_confidences: dict[str, float],
    tolerance: Decimal,
    minimum_confidence: float,
) -> dict:
    items_sum = sum(item_totals, Decimal("0.00")) if item_totals else None
    difference = (
        abs(items_sum - total_amount)
        if items_sum is not None and total_amount is not None
        else None
    )
    arithmetic_ok = difference <= tolerance if difference is not None else None
    cnpj_ok = is_valid_cnpj(cnpj) if cnpj else None
    cpf_ok = is_valid_cpf(cpf) if cpf else None
    access_key_ok = is_valid_access_key(access_key) if access_key else None
    issues: list[str] = []
    if not cnpj:
        issues.append("CNPJ ausente")
    elif not cnpj_ok:
        issues.append("CNPJ inválido")
    if not issue_datetime:
        issues.append("Data de emissão ausente ou inválida")
    else:
        now = datetime.now(UTC) if issue_datetime.tzinfo else datetime.now()
        if issue_datetime.year < 2000 or issue_datetime > now:
            issues.append("Data de emissão fora do intervalo permitido")
    if total_amount is None:
        issues.append("Valor total ausente")
    if cpf and not cpf_ok:
        issues.append("CPF inválido")
    if access_key and not access_key_ok:
        issues.append("Chave de acesso inválida")
    if access_key and cnpj and len(access_key) == 44:
        if access_key[6:20] != "".join(character for character in cnpj if character.isdigit()):
            issues.append("CNPJ da chave diverge do CNPJ do emitente")
    if arithmetic_ok is False:
        issues.append("Soma dos itens diverge do valor total")
    confidence_fields = {
        "cnpj": cnpj,
        "issue_datetime": issue_datetime,
        "total_amount": total_amount,
        "access_key": access_key,
        "cpf": cpf,
    }
    for field, value in confidence_fields.items():
        if value is not None and field_confidences.get(field, 0) < minimum_confidence:
            issues.append(f"Confiança de {field} abaixo do limite")
    return {
        "items_sum": items_sum,
        "total_amount": total_amount,
        "difference": difference,
        "arithmetic_ok": arithmetic_ok,
        "cnpj_ok": cnpj_ok,
        "cpf_ok": cpf_ok,
        "access_key_ok": access_key_ok,
        "issues": issues,
        "verdict": "APPROVED" if not issues and arithmetic_ok is True else "NEEDS_REVIEW",
    }
