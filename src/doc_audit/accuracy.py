import json
import re
from collections.abc import Mapping, Sequence
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import NotRequired, TypedDict

from doc_audit.validation import digits_only, normalize_amount

ACCURACY_FIELDS = ("cnpj", "cpf", "issue_datetime", "total_amount", "access_key", "items")


class EvaluationResult(TypedDict):
    cer: float
    wer: float
    field_accuracy: dict[str, bool]
    should_review: bool
    approved: bool
    document_id: NotRequired[str]


def _edit_distance(reference: Sequence[str], hypothesis: Sequence[str]) -> int:
    previous = list(range(len(hypothesis) + 1))
    for row, expected in enumerate(reference, start=1):
        current = [row]
        for column, actual in enumerate(hypothesis, start=1):
            current.append(
                min(
                    current[-1] + 1,
                    previous[column] + 1,
                    previous[column - 1] + (expected != actual),
                )
            )
        previous = current
    return previous[-1]


def error_rate(reference: str, hypothesis: str, *, words: bool = False) -> float:
    reference_tokens = reference.lower().split() if words else list(reference.lower())
    hypothesis_tokens = hypothesis.lower().split() if words else list(hypothesis.lower())
    if not reference_tokens:
        return 0.0 if not hypothesis_tokens else 1.0
    return _edit_distance(reference_tokens, hypothesis_tokens) / len(reference_tokens)


def _normalize_field(field: str, value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if field in {"cnpj", "cpf", "access_key"}:
        return digits_only(text)
    if field == "total_amount":
        try:
            return str(normalize_amount(text))
        except ValueError:
            return text
    if field == "issue_datetime":
        try:
            return datetime.fromisoformat(text).isoformat()
        except ValueError:
            return text
    if field == "items":
        if not isinstance(value, list):
            return text
        normalized_items: list[str | dict[str, str]] = []
        for item in value:
            if not isinstance(item, Mapping):
                normalized_items.append(str(item))
                continue
            normalized_item: dict[str, str] = {
                "description": re.sub(r"\s+", " ", str(item.get("description", "")))
                .strip()
                .casefold(),
            }
            if item.get("quantity") is not None:
                try:
                    quantity = Decimal(str(item["quantity"])).normalize()
                    normalized_item["quantity"] = format(quantity, "f")
                except (InvalidOperation, ValueError):
                    normalized_item["quantity"] = str(item["quantity"])
            for key in ("unit_price", "total_price"):
                if item.get(key) is not None:
                    try:
                        normalized_item[key] = str(normalize_amount(str(item[key])))
                    except ValueError:
                        normalized_item[key] = str(item[key])
            normalized_items.append(normalized_item)
        return json.dumps(normalized_items, ensure_ascii=False, sort_keys=True)
    return re.sub(r"\s+", " ", text).casefold()


def evaluate_document(
    expected: Mapping[str, object], actual: Mapping[str, object]
) -> EvaluationResult:
    expected_text = str(expected.get("raw_text", ""))
    actual_text = str(actual.get("raw_text", ""))
    fields = {
        field: _normalize_field(field, expected[field])
        == _normalize_field(field, actual.get(field))
        for field in ACCURACY_FIELDS
        if field in expected and expected[field] is not None
    }
    return {
        "cer": error_rate(expected_text, actual_text),
        "wer": error_rate(expected_text, actual_text, words=True),
        "field_accuracy": fields,
        "should_review": bool(expected.get("should_review", False)),
        "approved": actual.get("verdict") == "APPROVED",
    }


def aggregate_accuracy(results: list[EvaluationResult]) -> dict[str, object]:
    field_totals = {field: [0, 0] for field in ACCURACY_FIELDS}
    for result in results:
        for field, correct in result["field_accuracy"].items():
            field_totals[field][0] += int(correct)
            field_totals[field][1] += 1
    review_documents = [result for result in results if result["should_review"]]
    false_approvals = sum(result["approved"] for result in review_documents)
    return {
        "documents": len(results),
        "cer": sum(result["cer"] for result in results) / len(results) if results else 0.0,
        "wer": sum(result["wer"] for result in results) / len(results) if results else 0.0,
        "field_accuracy": {
            field: correct / total if total else None
            for field, (correct, total) in field_totals.items()
        },
        "false_approvals": false_approvals,
        "known_review_documents": len(review_documents),
        "false_approval_rate": false_approvals / len(review_documents)
        if review_documents
        else None,
    }
