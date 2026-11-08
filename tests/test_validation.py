from decimal import Decimal

import pytest

from doc_audit.validation import (
    is_valid_access_key,
    is_valid_cnpj,
    is_valid_cpf,
    normalize_amount,
)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("529.982.247-25", True),
        ("111.111.111-11", False),
        ("123", False),
    ],
)
def test_is_valid_cpf(value: str, expected: bool) -> None:
    assert is_valid_cpf(value) is expected


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("11.222.333/0001-81", True),
        ("11.111.111/1111-11", False),
        ("123", False),
    ],
)
def test_is_valid_cnpj(value: str, expected: bool) -> None:
    assert is_valid_cnpj(value) is expected


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("1.234,56", Decimal("1234.56")),
        ("87,90", Decimal("87.90")),
        ("87.90", Decimal("87.90")),
    ],
)
def test_normalize_amount(value: str, expected: Decimal) -> None:
    assert normalize_amount(value) == expected


def test_access_key_rejects_wrong_length() -> None:
    assert not is_valid_access_key("123")


def test_access_key_validates_modulo_11_digit() -> None:
    first_43_digits = "3526031234567800019565001000000001100000001"
    weights = (2, 3, 4, 5, 6, 7, 8, 9) * 6
    weighted_sum = sum(
        int(digit) * weight
        for digit, weight in zip(reversed(first_43_digits), weights, strict=False)
    )
    remainder = weighted_sum % 11
    check_digit = 0 if remainder in (0, 1) else 11 - remainder
    key = f"{first_43_digits}{check_digit}"
    assert len(key) == 44
    assert is_valid_access_key(key)
    assert not is_valid_access_key(f"{first_43_digits}{(check_digit + 1) % 10}")
