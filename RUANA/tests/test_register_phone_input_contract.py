from pathlib import Path


def _read(relative_path: str) -> str:
    return (Path(__file__).resolve().parents[1] / relative_path).read_text(encoding="utf-8")


def test_register_page_includes_phone_country_selector():
    html = _read("web/register.html")
    countries_js = _read("web/static/js/phone-countries.js")
    phone_input_js = _read("web/static/js/phone-input.js")

    assert "/static/js/phone-countries.js" in html
    assert "/static/js/phone-input.js" in html
    assert 'id="telefono-nacional"' in html
    assert 'id="phone-country-trigger"' in html
    assert 'id="phone-country-dropdown"' in html
    assert "RuanaPhoneInput" in html
    assert "initPhoneInput" in html
    assert "RUANA_PHONE_COUNTRIES" in countries_js
    assert "ruanaCountryFlag" in countries_js
    assert "class RuanaPhoneInput" in phone_input_js
    assert "getFullNumber" in phone_input_js


def test_register_phone_validation_uses_digit_count():
    html = _read("web/register.html")
    assert "this.phoneInput.isValid()" in html
    assert "al menos 7 dígitos" in html
