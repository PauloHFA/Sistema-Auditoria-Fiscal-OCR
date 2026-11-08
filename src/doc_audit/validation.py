import re
from decimal import Decimal, InvalidOperation


def digits_only(value: str) -> str:
    return re.sub(r"\D", "", value)


def is_valid_cpf(value: str) -> bool:
    digits = digits_only(value)
    if len(digits) != 11 or len(set(digits)) == 1:
        return False
    for length in (9, 10):
        checksum = sum(int(digits[index]) * (length + 1 - index) for index in range(length))
        digit = (checksum * 10) % 11
        if digit == 10:
            digit = 0
        if digit != int(digits[length]):
            return False
    return True


def is_valid_cnpj(value: str) -> bool:
    digits = digits_only(value)
    if len(digits) != 14 or len(set(digits)) == 1:
        return False
    for length, weights in (
        (12, (5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2)),
        (13, (6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2)),
    ):
        remainder = sum(int(digits[i]) * weights[i] for i in range(length)) % 11
        check_digit = 0 if remainder < 2 else 11 - remainder
        if check_digit != int(digits[length]):
            return False
    return True


def is_valid_access_key(value: str) -> bool:
    digits = digits_only(value)
    if len(digits) != 44:
        return False
    weighted_sum = sum(
        int(digit) * weight
        for digit, weight in zip(reversed(digits[:43]), (2, 3, 4, 5, 6, 7, 8, 9) * 6, strict=False)
    )
    remainder = weighted_sum % 11
    check_digit = 0 if remainder in (0, 1) else 11 - remainder
    return check_digit == int(digits[-1])


def normalize_amount(value: str) -> Decimal:
    normalized = re.sub(r"[^\d,.-]", "", value)
    if "," in normalized:
        normalized = normalized.replace(".", "").replace(",", ".")
    try:
        return Decimal(normalized).quantize(Decimal("0.01"))
    except InvalidOperation as exc:
        raise ValueError(f"Valor monetário inválido: {value!r}") from exc
