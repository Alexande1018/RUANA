"""Centralized RUANA file storage.

Prefer Supabase Storage in production. When Supabase is not configured
(local/CI QA), files can be stored under web/static/uploads/ if allowed.
"""

from __future__ import annotations

import mimetypes
import os
import re
import uuid
from pathlib import Path
from typing import BinaryIO, Dict, Optional, TypedDict
from urllib.parse import unquote, urlparse

from werkzeug.utils import secure_filename

try:
    from .supabase_client import get_supabase_admin_client
except Exception:  # pragma: no cover - app.py also imports core as top-level
    from core.supabase_client import get_supabase_admin_client

try:
    from .settings import get_settings
except Exception:  # pragma: no cover
    from core.settings import get_settings


MAX_UPLOAD_BYTES = 2 * 1024 * 1024
MAX_FOTO_PERFIL_BYTES = 15 * 1024 * 1024
SIGNED_URL_EXPIRES_SECONDS = 3600

ALLOWED_PRIVATE_BUCKETS = frozenset({"ruana-comprobantes", "ruana-conflictos", "ruana-public"})
_STORAGE_OBJECT_RE = re.compile(
    r"/storage/v1/object/(?:public|sign|authenticated)/([^/]+)/(.+?)(?:\?.*)?$"
)


class StorageLocation(TypedDict):
    kind: str
    bucket: str
    path: str


def _format_max_mb(max_bytes: int) -> str:
    mb = max_bytes / (1024 * 1024)
    return str(int(mb)) if mb == int(mb) else f"{mb:.1f}"


def _read_limited(file_obj: BinaryIO, max_bytes: int = MAX_UPLOAD_BYTES) -> bytes:
    data = file_obj.read(max_bytes + 1)
    if len(data) > max_bytes:
        raise ValueError(f"El archivo supera el limite de {_format_max_mb(max_bytes)} MB.")
    return data


def _local_uploads_allowed() -> bool:
    """Permitir disco local solo en QA/local sin Supabase (o flag explícito)."""
    flag = (os.environ.get("RUANA_ALLOW_LOCAL_UPLOADS") or "").strip().lower()
    if flag in {"1", "true", "yes", "on"}:
        return True
    if flag in {"0", "false", "no", "off"}:
        return False
    try:
        return not get_settings().supabase_configured
    except Exception:
        return True


def _web_static_root() -> Path:
    return Path(__file__).resolve().parent.parent / "web" / "static"


def _upload_ruana_bytes_local(
    *,
    data: bytes,
    original_filename: str,
    folder: str,
    prefix: str,
    content_type: Optional[str] = None,
) -> Dict[str, str]:
    safe_name = secure_filename(original_filename or "archivo") or "archivo"
    ext = (Path(safe_name).suffix or "").lower()
    generated = f"{prefix}_{uuid.uuid4().hex[:12]}_{safe_name}"[:120]
    rel_dir = Path("uploads") / folder.strip("/")
    abs_dir = _web_static_root() / rel_dir
    abs_dir.mkdir(parents=True, exist_ok=True)
    abs_path = abs_dir / generated
    abs_path.write_bytes(data)
    public_path = f"/static/{rel_dir.as_posix()}/{generated}"
    guessed_type = content_type or mimetypes.guess_type(safe_name)[0] or "application/octet-stream"
    return {
        "bucket": "local",
        "path": public_path.lstrip("/"),
        "url": public_path,
        "filename": safe_name,
        "content_type": guessed_type,
        "size": str(len(data)),
        "extension": ext,
    }


def _extract_signed_url(response: object) -> str:
    if isinstance(response, dict):
        return str(response.get("signedURL") or response.get("signedUrl") or "")
    signed = getattr(response, "signedURL", None) or getattr(response, "signedUrl", None)
    return str(signed or "")


def parse_storage_location(stored_url: str) -> Optional[StorageLocation]:
    """Resolve a stored RUANA file reference to a local path or Supabase object."""
    url = (stored_url or "").strip()
    if not url:
        return None

    if url.startswith("/static/uploads/"):
        return {"kind": "local", "bucket": "", "path": url.lstrip("/")}
    if url.startswith("static/uploads/"):
        return {"kind": "local", "bucket": "", "path": url}

    parsed = urlparse(url)
    match = _STORAGE_OBJECT_RE.search(parsed.path)
    if not match:
        return None

    bucket = match.group(1)
    object_path = unquote(match.group(2))
    if bucket not in ALLOWED_PRIVATE_BUCKETS:
        return None
    return {"kind": "supabase", "bucket": bucket, "path": object_path}


def create_ruana_signed_url(
    *,
    bucket: str,
    object_path: str,
    expires_in: int = SIGNED_URL_EXPIRES_SECONDS,
) -> str:
    """Create a short-lived signed URL for a private Supabase Storage object."""
    client = get_supabase_admin_client()
    storage_bucket = client.storage.from_(bucket)
    response = storage_bucket.create_signed_url(object_path, expires_in)
    signed_url = _extract_signed_url(response)
    if not signed_url:
        raise RuntimeError("No se pudo generar la URL firmada del documento.")
    return signed_url


def resolve_admin_document_access_url(stored_url: str) -> str:
    """Return a browser-openable URL for an admin reviewing ally-uploaded files."""
    location = parse_storage_location(stored_url)
    if not location:
        raise ValueError("La referencia del documento no es válida.")

    if location["kind"] == "local":
        local_path = location["path"]
        if not local_path.startswith("static/uploads/"):
            raise ValueError("La ruta local del documento no es válida.")
        return f"/{local_path.lstrip('/')}"

    return create_ruana_signed_url(
        bucket=location["bucket"],
        object_path=location["path"],
    )


def upload_ruana_bytes(
    *,
    data: bytes,
    original_filename: str,
    bucket: str,
    folder: str,
    prefix: str,
    content_type: Optional[str] = None,
) -> Dict[str, str]:
    """Upload pre-read bytes to Supabase Storage (or local QA fallback)."""
    safe_name = secure_filename(original_filename or "archivo") or "archivo"
    guessed_type = content_type or mimetypes.guess_type(safe_name)[0] or "application/octet-stream"

    try:
        settings = get_settings()
        supabase_ok = bool(settings.supabase_configured)
    except Exception:
        supabase_ok = False

    if not supabase_ok:
        if not _local_uploads_allowed():
            raise RuntimeError(
                "Supabase is not configured. Set SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY."
            )
        return _upload_ruana_bytes_local(
            data=data,
            original_filename=safe_name,
            folder=folder,
            prefix=prefix,
            content_type=guessed_type,
        )

    ext = (Path(safe_name).suffix or "").lower()
    generated = f"{prefix}_{uuid.uuid4().hex[:12]}_{safe_name}"[:120]
    object_path = f"{folder.strip('/')}/{generated}"

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
