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


def _read_limited(file_obj: BinaryIO) -> bytes:
    data = file_obj.read(MAX_UPLOAD_BYTES + 1)
    if len(data) > MAX_UPLOAD_BYTES:
        raise ValueError("El archivo supera el limite de 2 MB.")
    return data


def upload_ruana_file(
    *,
    file_obj: BinaryIO,
    original_filename: str,
    bucket: str,
    folder: str,
    prefix: str,
    content_type: Optional[str] = None,
) -> Dict[str, str]:
    """Upload a RUANA file to Supabase Storage and return its storage metadata."""
    safe_name = secure_filename(original_filename or "archivo") or "archivo"
    ext = (Path(safe_name).suffix or "").lower()
    generated = f"{prefix}_{uuid.uuid4().hex[:12]}_{safe_name}"[:120]
    object_path = f"{folder.strip('/')}/{generated}"
    data = _read_limited(file_obj)
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
