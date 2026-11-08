from datetime import datetime
from decimal import Decimal

from doc_audit.parsers import (
    parse_access_key,
    parse_cnpj,
    parse_cpf,
    parse_issue_datetime,
    parse_items,
    parse_total,
)


def test_parses_identifiers_and_date() -> None:
    text = (
        "CNPJ: 11.222.333/0001-81\n"
        "CPF: 529.982.247-25\n"
        "Emissão: 08/11/2026 18:25:00\n"
        "Chave de acesso: 35260312345678000195650010000000011000000011"
    )
    assert parse_cnpj(text) == "11222333000181"
    assert parse_cpf(text) == "52998224725"
    assert parse_issue_datetime(text) == datetime(2026, 11, 8, 18, 25)
    assert parse_access_key(text) == "35260312345678000195650010000000011000000011"


def test_total_prefers_value_to_pay_not_item_count() -> None:
    text = "TOTAL DE ITENS 4\nVALOR TOTAL R$ 87,90\nVALOR A PAGAR R$ 82,90"
    assert parse_total(text) == Decimal("82.90")


def test_parses_common_item_line() -> None:
    items = parse_items("001 ARROZ TIPO 1 5,000 KG 6,50 32,50")
    assert len(items) == 1
    assert items[0]["description"] == "ARROZ TIPO 1"
    assert items[0]["quantity"] == Decimal("5.000")
    assert items[0]["total_price"] == Decimal("32.50")
