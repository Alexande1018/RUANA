from io import BytesIO

import pytest
from PIL import Image

from RUANA.core.image_utils import (
    MAX_FOTO_PERFIL_OUTPUT_BYTES,
    prepare_foto_perfil,
)


def _make_test_jpeg(width: int, height: int, quality: int = 95) -> bytes:
    img = Image.new("RGB", (width, height), color=(120, 80, 200))
    out = BytesIO()
    img.save(out, format="JPEG", quality=quality)
    return out.getvalue()


def test_prepare_foto_perfil_reduces_large_mobile_photo():
    raw = _make_test_jpeg(4000, 3000, quality=95)
    assert len(raw) > 100_000

    optimized = prepare_foto_perfil(raw)

    assert len(optimized) <= MAX_FOTO_PERFIL_OUTPUT_BYTES
    assert optimized.startswith(b"\xff\xd8\xff")


def test_prepare_foto_perfil_rejects_invalid_bytes():
    with pytest.raises(ValueError, match="No se pudo leer la imagen"):
        prepare_foto_perfil(b"no-es-una-imagen")
