"""Utilidades de imagen para subidas RUANA."""

from __future__ import annotations

from io import BytesIO

from PIL import Image, ImageOps

# Avatar en UI: ~120px; 1200px basta para pantallas retina.
MAX_FOTO_PERFIL_EDGE = 1200
# Por debajo del limite habitual de Supabase Storage (2 MB en muchos proyectos).
MAX_FOTO_PERFIL_OUTPUT_BYTES = 1_800_000
JPEG_QUALITY_START = 85
JPEG_QUALITY_MIN = 55


def prepare_foto_perfil(image_bytes: bytes) -> bytes:
    """Redimensiona y comprime una foto de perfil para almacenamiento web."""
    if not image_bytes:
        raise ValueError("La imagen esta vacia.")

    try:
        img = Image.open(BytesIO(image_bytes))
        img.load()
    except Exception as exc:
        raise ValueError(
            "No se pudo leer la imagen. Usa jpg, png, webp o gif."
        ) from exc

    img = ImageOps.exif_transpose(img)

    if getattr(img, "n_frames", 1) > 1:
        img.seek(0)

    if img.mode in ("RGBA", "LA", "P"):
        background = Image.new("RGB", img.size, (255, 255, 255))
        rgba = img.convert("RGBA")
        background.paste(rgba, mask=rgba.split()[-1])
        img = background
    elif img.mode != "RGB":
        img = img.convert("RGB")

    img.thumbnail((MAX_FOTO_PERFIL_EDGE, MAX_FOTO_PERFIL_EDGE), Image.Resampling.LANCZOS)

    quality = JPEG_QUALITY_START
    best_data: bytes | None = None
    while quality >= JPEG_QUALITY_MIN:
        out = BytesIO()
        img.save(out, format="JPEG", quality=quality, optimize=True)
        data = out.getvalue()
        best_data = data
        if len(data) <= MAX_FOTO_PERFIL_OUTPUT_BYTES:
            return data
        quality -= 10

    if best_data is not None:
        smaller = img.copy()
        smaller.thumbnail(
            (max(400, MAX_FOTO_PERFIL_EDGE // 2), max(400, MAX_FOTO_PERFIL_EDGE // 2)),
            Image.Resampling.LANCZOS,
        )
        out = BytesIO()
        smaller.save(out, format="JPEG", quality=JPEG_QUALITY_MIN, optimize=True)
        return out.getvalue()

    raise ValueError("No se pudo optimizar la imagen.")
