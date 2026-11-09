import re
from datetime import datetime
from decimal import Decimal
from typing import TypedDict

from doc_audit.validation import digits_only, normalize_amount


class ParsedItem(TypedDict):
    description: str
    quantity: Decimal | None
    unit_price: Decimal | None
    total_price: Decimal


def _find_identifier(text: str, length: int) -> str | None:
    pattern = rf"(?<!\d)(?:\d[\s./-]?){{{length}}}(?!\d)"
    match = re.search(pattern, text)
    return digits_only(match.group()) if match else None


def _find_labeled_identifier(text: str, label: str, length: int) -> str | None:
    pattern = rf"\b{label}\b\s*[:#-]?\s*((?:\d[\s./-]?){length - 1}\d)"
    match = re.search(pattern, text, re.I)
    return digits_only(match.group(1)) if match else None


def parse_cnpj(text: str) -> str | None:
    return _find_labeled_identifier(text, "CNPJ", 14) or _find_identifier(text, 14)


def parse_cpf(text: str) -> str | None:
    return _find_labeled_identifier(text, "CPF", 11) or _find_identifier(text, 11)


def parse_access_key(text: str) -> str | None:
    match = re.search(
        r"\b(?:CHAVE(?:\s+DE)?\s+ACESSO|CHAVE)\b\s*[:#-]?\s*((?:\d[\s.-]?){43}\d)",
        text,
        re.I,
    )
    match = match or re.search(r"(?<!\d)(?:\d[\s.-]?){43}\d(?!\d)", text)
    return digits_only(match.group()) if match else None


def parse_issue_datetime(text: str) -> datetime | None:
    match = re.search(r"\b(\d{2})/(\d{2})/(\d{4})(?:\s+(\d{2}):(\d{2})(?::(\d{2}))?)?\b", text)
    if not match:
        return None
    day, month, year, hour, minute, second = match.groups()
    try:
        return datetime(
            int(year),
            int(month),
            int(day),
            int(hour or 0),
            int(minute or 0),
            int(second or 0),
        )
    except ValueError:
        return None


def parse_total(text: str) -> Decimal | None:
    money = r"(?:R\$\s*)?(\d{1,3}(?:\.\d{3})*,\d{2}|\d+,\d{2}|\d+\.\d{2})"
    candidates: list[tuple[int, int, Decimal]] = []
    for line_number, line in enumerate(text.splitlines()):
        if re.search(r"\bTOTAL\s+DE\s+(?:ITENS|PRODUTOS)\b", line, re.I):
            continue
        if re.search(r"\b(?:VALOR\s+A\s+PAGAR|TOTAL\s+A\s+PAGAR)\b", line, re.I):
            priority = 3
        elif re.search(r"\b(?:VALOR\s+TOTAL|TOTAL\s+GERAL|VALOR\s+DO\s+DOCUMENTO)\b", line, re.I):
            priority = 2
        elif re.search(r"\bTOTAL\b", line, re.I):
            priority = 1
        else:
            continue
        matches = list(re.finditer(money, line, re.I))
        if matches:
            candidates.append((priority, line_number, normalize_amount(matches[-1].group(1))))
    return max(
        candidates, default=(0, 0, None), key=lambda candidate: (candidate[0], candidate[1])
    )[2]


def parse_items(text: str) -> list[ParsedItem]:
    parsed: list[ParsedItem] = []
    money = r"(?:\d{1,3}(?:\.\d{3})*,\d{2}|\d+,\d{2}|\d+\.\d{2})"
    quantity = r"\d+(?:[,.]\d{1,3})?"
    units = r"(?:UN|KG|LT|PC|PCT|CX|FD|DZ|L|M)"
    inline_pattern = re.compile(
        rf"^\s*\d{{1,4}}\s+(.+?)\s+({quantity})\s*(?:{units})?\s*"
        rf"(?:X\s*)?({money})\s+({money})\s*$",
        re.I,
    )
    continuation_pattern = re.compile(
        rf"^\s*({quantity})\s*(?:{units})?\s*(?:X\s*)?({money})\s+({money})\s*$",
        re.I,
    )
    header_pattern = re.compile(r"^\s*\d{1,4}\s+(.+?)\s*$")

    def add_item(description: str, quantity_value: str, unit_price: str, total_price: str) -> None:
        parsed.append(
            {
                "description": description.strip()[:512],
                "quantity": Decimal(quantity_value.replace(",", ".")),
                "unit_price": normalize_amount(unit_price),
                "total_price": normalize_amount(total_price),
            }
        )

    pending_description: str | None = None
    for line in text.splitlines():
        inline = inline_pattern.match(line)
        if inline:
            description, quantity_value, unit_price, total_price = inline.groups()
            add_item(description, quantity_value, unit_price, total_price)
            pending_description = None
            continue
        continuation = continuation_pattern.match(line)
        if continuation and pending_description:
            quantity_value, unit_price, total_price = continuation.groups()
            add_item(pending_description, quantity_value, unit_price, total_price)
            pending_description = None
            continue
        if continuation:
            pending_description = None
            continue
        header = header_pattern.match(line)
        if header and re.search(r"[A-Za-z]", header.group(1)):
            pending_description = header.group(1).strip()
        elif line.strip():
            pending_description = None
    return parsed
