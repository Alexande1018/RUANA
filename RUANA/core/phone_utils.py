"""Utilidades compartidas para teléfonos internacionales."""

from __future__ import annotations

import re


def normalize_phone(raw: str) -> str:
    """Normaliza un teléfono a formato internacional +<dígitos>."""
    digits = re.sub(r"\D", "", (raw or "").strip())
    if not digits:
        return ""
    return f"+{digits}"


def phone_digit_count(raw: str) -> int:
    return len(re.sub(r"\D", "", raw or ""))
