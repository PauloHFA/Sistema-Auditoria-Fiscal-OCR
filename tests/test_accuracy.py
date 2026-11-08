from doc_audit.accuracy import aggregate_accuracy, error_rate, evaluate_document


def test_error_rates_use_character_and_word_edit_distance() -> None:
    assert error_rate("nota fiscal", "nota fiscal") == 0
    assert error_rate("abc", "adc") == 1 / 3
    assert error_rate("one two", "one three", words=True) == 0.5


def test_field_accuracy_normalizes_identifiers_amounts_and_items() -> None:
    result = evaluate_document(
        {
            "cnpj": "11.222.333/0001-81",
            "total_amount": "1.234,50",
            "items": [
                {
                    "description": " ARROZ  ",
                    "quantity": "1.000",
                    "unit_price": "1.234,50",
                    "total_price": "1.234,50",
                }
            ],
        },
        {
            "cnpj": "11222333000181",
            "total_amount": "1234.50",
            "items": [
                {
                    "description": "arroz",
                    "quantity": 1,
                    "unit_price": "1234.50",
                    "total_price": "1234.50",
                }
            ],
        },
    )
    assert result["field_accuracy"] == {"cnpj": True, "total_amount": True, "items": True}


def test_aggregate_reports_false_approvals() -> None:
    document_result = evaluate_document(
        {"raw_text": "text", "should_review": True},
        {"raw_text": "text", "verdict": "APPROVED"},
    )

    summary = aggregate_accuracy([document_result])

    assert summary["false_approvals"] == 1
    assert summary["false_approval_rate"] == 1
