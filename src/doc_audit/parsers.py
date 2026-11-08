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


def parse_cnpj(text: str) -> str | None:
    return _find_identifier(text, 14)


def parse_cpf(text: str) -> str | None:
    return _find_identifier(text, 11)


def parse_access_key(text: str) -> str | None:
    match = re.search(r"(?<!\d)(?:\d[\s.-]?){43}\d(?!\d)", text)
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
    candidates: list[tuple[int, Decimal]] = []
    for line_number, line in enumerate(text.splitlines()):
        if not re.search(r"\b(?:VALOR\s+TOTAL|VALOR\s+A\s+PAGAR|TOTAL\s+A\s+PAGAR)\b", line, re.I):
            continue
        matches = list(re.finditer(money, line, re.I))
        if matches:
            candidates.append((line_number, normalize_amount(matches[-1].group(1))))
    return max(candidates, default=(0, None), key=lambda candidate: candidate[0])[1]


def parse_items(text: str) -> list[ParsedItem]:
    parsed: list[ParsedItem] = []
    item_pattern = re.compile(
        r"^\s*\d{1,4}\s+(.+?)\s+(\d+(?:,\d{1,3})?)\s+"
        r"(?:UN|KG|LT|PC|CX|FD)?\s*"
        r"(\d{1,3}(?:\.\d{3})*,\d{2})\s+"
        r"(\d{1,3}(?:\.\d{3})*,\d{2})\s*$",
        re.I,
    )
    for line in text.splitlines():
        match = item_pattern.match(line)
        if match:
            description, quantity, unit_price, total_price = match.groups()
            parsed.append(
                {
                    "description": description.strip()[:512],
                    "quantity": Decimal(quantity.replace(",", ".")),
                    "unit_price": normalize_amount(unit_price),
                    "total_price": normalize_amount(total_price),
                }
            )
    return parsed
