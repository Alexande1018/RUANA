from RUANA.core.phone_utils import normalize_phone, phone_digit_count


def test_normalize_phone_strips_formatting():
    assert normalize_phone("+34 600 123 456") == "+34600123456"
    assert normalize_phone("600123456") == "+600123456"


def test_phone_digit_count_ignores_symbols():
    assert phone_digit_count("+34 600 123 456") == 11
