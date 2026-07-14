"""Centralized RUANA file storage.

Runtime uploads must not be written to the local filesystem. This module stores
files in Supabase Storage and returns stable URLs for existing DB fields.
"""

from __future__ import annotations

import mimetypes
import uuid
from pathlib import Path
from typing import BinaryIO, Dict, Optional

from werkzeug.utils import secure_filename

try:
    from .supabase_client import get_supabase_admin_client
except Exception:  # pragma: no cover - app.py also imports core as top-level
    from core.supabase_client import get_supabase_admin_client


MAX_UPLOAD_BYTES = 2 * 1024 * 1024
MAX_FOTO_PERFIL_BYTES = 15 * 1024 * 1024


def _format_max_mb(max_bytes: int) -> str:
    mb = max_bytes / (1024 * 1024)
    return str(int(mb)) if mb == int(mb) else f"{mb:.1f}"


def _read_limited(file_obj: BinaryIO, max_bytes: int = MAX_UPLOAD_BYTES) -> bytes:
    data = file_obj.read(max_bytes + 1)
    if len(data) > max_bytes:
        raise ValueError(f"El archivo supera el limite de {_format_max_mb(max_bytes)} MB.")
    return data


def upload_ruana_bytes(
    *,
    data: bytes,
    original_filename: str,
    bucket: str,
    folder: str,
    prefix: str,
    content_type: Optional[str] = None,
) -> Dict[str, str]:
    """Upload pre-read bytes to Supabase Storage."""
    safe_name = secure_filename(original_filename or "archivo") or "archivo"
    ext = (Path(safe_name).suffix or "").lower()
    generated = f"{prefix}_{uuid.uuid4().hex[:12]}_{safe_name}"[:120]
    object_path = f"{folder.strip('/')}/{generated}"
    guessed_type = content_type or mimetypes.guess_type(safe_name)[0] or "application/octet-stream"

    client = get_supabase_admin_client()
    storage_bucket = client.storage.from_(bucket)
    storage_bucket.upload(
        object_path,
        data,
        file_options={"content-type": guessed_type, "upsert": "true"},
    )
    public_url = storage_bucket.get_public_url(object_path)
    if isinstance(public_url, dict):
        public_url = public_url.get("publicUrl") or public_url.get("public_url") or ""

    return {
        "bucket": bucket,
        "path": object_path,
        "url": str(public_url),
        "filename": safe_name,
        "content_type": guessed_type,
        "size": str(len(data)),
        "extension": ext,
    }


def upload_ruana_file(
    *,
    file_obj: BinaryIO,
    original_filename: str,
    bucket: str,
    folder: str,
    prefix: str,
    content_type: Optional[str] = None,
    max_bytes: int = MAX_UPLOAD_BYTES,
) -> Dict[str, str]:
    """Upload a RUANA file to Supabase Storage and return its storage metadata."""
    safe_name = secure_filename(original_filename or "archivo") or "archivo"
    data = _read_limited(file_obj, max_bytes=max_bytes)
    guessed_type = content_type or mimetypes.guess_type(safe_name)[0] or "application/octet-stream"
    return upload_ruana_bytes(
        data=data,
        original_filename=safe_name,
        bucket=bucket,
        folder=folder,
        prefix=prefix,
        content_type=guessed_type,
    )


def upload_foto_perfil_file(
    *,
    file_obj: BinaryIO,
    original_filename: str,
    prefix: str,
) -> Dict[str, str]:
    """Lee, optimiza y sube una foto de perfil (acepta fotos grandes de movil)."""
    try:
        from .image_utils import prepare_foto_perfil
    except Exception:  # pragma: no cover - app.py also imports core as top-level
        from core.image_utils import prepare_foto_perfil

    raw = _read_limited(file_obj, max_bytes=MAX_FOTO_PERFIL_BYTES)
    optimized = prepare_foto_perfil(raw)
    stem = (Path(secure_filename(original_filename or "foto")).stem or "foto")[:40]
    return upload_ruana_bytes(
        data=optimized,
        original_filename=f"{stem}.jpg",
        bucket="ruana-public",
        folder="fotos_perfil",
        prefix=prefix,
        content_type="image/jpeg",
    )
