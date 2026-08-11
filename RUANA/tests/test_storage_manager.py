from io import BytesIO
from pathlib import Path

import pytest


class _SettingsConfigured:
    supabase_configured = True


class _SettingsUnconfigured:
    supabase_configured = False


def _force_supabase(monkeypatch, storage_manager):
    monkeypatch.setattr(storage_manager, "get_settings", lambda: _SettingsConfigured())


def test_upload_ruana_file_rejects_files_over_2mb():
    from RUANA.core.storage_manager import MAX_UPLOAD_BYTES, upload_ruana_file

    oversized = BytesIO(b"x" * (MAX_UPLOAD_BYTES + 1))

    with pytest.raises(ValueError, match="2 MB"):
        upload_ruana_file(
            file_obj=oversized,
            original_filename="comprobante.png",
            bucket="ruana-comprobantes",
            folder="pagos_ruana",
            prefix="1",
            content_type="image/png",
        )


def test_upload_ruana_file_allows_larger_foto_perfil_limit(monkeypatch):
    from RUANA.core import storage_manager
    from RUANA.core.storage_manager import MAX_FOTO_PERFIL_BYTES, MAX_UPLOAD_BYTES

    class FakeBucket:
        def upload(self, path, data, file_options=None):
            return {"path": path}

        def get_public_url(self, path):
            return f"https://storage.example/{path}"

    class FakeStorage:
        def from_(self, bucket):
            return FakeBucket()

    class FakeClient:
        storage = FakeStorage()

    _force_supabase(monkeypatch, storage_manager)
    monkeypatch.setattr(storage_manager, "get_supabase_admin_client", lambda: FakeClient())

    payload = b"x" * (MAX_UPLOAD_BYTES + 1)
    result = storage_manager.upload_ruana_file(
        file_obj=BytesIO(payload),
        original_filename="selfie.jpg",
        bucket="ruana-public",
        folder="fotos_perfil",
        prefix="A0001",
        content_type="image/jpeg",
        max_bytes=MAX_FOTO_PERFIL_BYTES,
    )

    assert result["size"] == str(len(payload))
    assert result["bucket"] == "ruana-public"


def test_upload_ruana_file_rejects_foto_perfil_over_15mb():
    from RUANA.core.storage_manager import MAX_FOTO_PERFIL_BYTES, upload_ruana_file

    oversized = BytesIO(b"x" * (MAX_FOTO_PERFIL_BYTES + 1))

    with pytest.raises(ValueError, match="15 MB"):
        upload_ruana_file(
            file_obj=oversized,
            original_filename="selfie.jpg",
            bucket="ruana-public",
            folder="fotos_perfil",
            prefix="A0001",
            content_type="image/jpeg",
            max_bytes=MAX_FOTO_PERFIL_BYTES,
        )


def test_upload_foto_perfil_file_optimizes_before_storage(monkeypatch):
    from io import BytesIO

    from PIL import Image

    from RUANA.core import storage_manager

    uploads = []

    class FakeBucket:
        def upload(self, path, data, file_options=None):
            uploads.append(len(data))
            return {"path": path}

        def get_public_url(self, path):
            return f"https://storage.example/{path}"

    class FakeStorage:
        def from_(self, bucket):
            return FakeBucket()

    class FakeClient:
        storage = FakeStorage()

    _force_supabase(monkeypatch, storage_manager)
    monkeypatch.setattr(storage_manager, "get_supabase_admin_client", lambda: FakeClient())

    img = Image.new("RGB", (4000, 3000), color=(200, 100, 50))
    raw_io = BytesIO()
    img.save(raw_io, format="JPEG", quality=95)
    raw_io.seek(0)

    result = storage_manager.upload_foto_perfil_file(
        file_obj=raw_io,
        original_filename="selfie.jpg",
        prefix="A0001",
    )

    assert result["content_type"] == "image/jpeg"
    assert uploads
    assert uploads[0] <= 1_800_000


def test_upload_ruana_file_uses_supabase_storage(monkeypatch):
    from RUANA.core import storage_manager

    calls = []

    class FakeBucket:
        def upload(self, path, data, file_options=None):
            calls.append(("upload", path, data, file_options))
            return {"path": path}

        def get_public_url(self, path):
            calls.append(("get_public_url", path))
            return f"https://storage.example/{path}"

    class FakeStorage:
        def from_(self, bucket):
            calls.append(("from", bucket))
            return FakeBucket()

    class FakeClient:
        storage = FakeStorage()

    _force_supabase(monkeypatch, storage_manager)
    monkeypatch.setattr(storage_manager, "get_supabase_admin_client", lambda: FakeClient())

    result = storage_manager.upload_ruana_file(
        file_obj=BytesIO(b"hola"),
        original_filename="mi comprobante.png",
        bucket="ruana-comprobantes",
        folder="pagos_ruana",
        prefix="7",
        content_type="image/png",
    )

    assert result["bucket"] == "ruana-comprobantes"
    assert result["url"].startswith("https://storage.example/pagos_ruana/7_")
    assert calls[0] == ("from", "ruana-comprobantes")
    assert calls[1][0] == "upload"
    assert calls[1][2] == b"hola"
    assert calls[1][3]["content-type"] == "image/png"


def test_upload_ruana_file_falls_back_to_local_when_supabase_missing(monkeypatch, tmp_path):
    from RUANA.core import storage_manager

    monkeypatch.setattr(storage_manager, "get_settings", lambda: _SettingsUnconfigured())
    monkeypatch.setenv("RUANA_ALLOW_LOCAL_UPLOADS", "1")
    monkeypatch.setattr(storage_manager, "_web_static_root", lambda: tmp_path)

    result = storage_manager.upload_ruana_file(
        file_obj=BytesIO(b"comprobante-qa"),
        original_filename="comprobante.png",
        bucket="ruana-comprobantes",
        folder="pagos_ruana",
        prefix="9",
        content_type="image/png",
    )

    assert result["bucket"] == "local"
    assert result["url"].startswith("/static/uploads/pagos_ruana/")
    # Disco: web/static/uploads/... → aquí _web_static_root es tmp_path
    stored = tmp_path / "uploads" / "pagos_ruana" / Path(result["url"]).name
    assert stored.is_file()
    assert stored.read_bytes() == b"comprobante-qa"
    assert storage_manager.resolve_admin_document_access_url(result["url"]) == result["url"]


def test_upload_ruana_file_rejects_local_when_flag_disabled(monkeypatch):
    from RUANA.core import storage_manager

    monkeypatch.setattr(storage_manager, "get_settings", lambda: _SettingsUnconfigured())
    monkeypatch.setenv("RUANA_ALLOW_LOCAL_UPLOADS", "0")

    with pytest.raises(RuntimeError, match="Supabase is not configured"):
        storage_manager.upload_ruana_file(
            file_obj=BytesIO(b"x"),
            original_filename="comprobante.png",
            bucket="ruana-comprobantes",
            folder="pagos_ruana",
            prefix="1",
            content_type="image/png",
        )


def test_create_ruana_signed_url_uses_supabase_storage(monkeypatch):
    from RUANA.core import storage_manager

    calls = []

    class FakeBucket:
        def create_signed_url(self, path, expires_in):
            calls.append(("create_signed_url", path, expires_in))
            return {"signedURL": f"https://signed.example/{path}?token=abc"}

    class FakeStorage:
        def from_(self, bucket):
            calls.append(("from", bucket))
            return FakeBucket()

    class FakeClient:
        storage = FakeStorage()

    monkeypatch.setattr(storage_manager, "get_supabase_admin_client", lambda: FakeClient())

    signed = storage_manager.create_ruana_signed_url(
        bucket="ruana-comprobantes",
        object_path="pagos_ruana/7_file.png",
        expires_in=120,
    )

    assert signed == "https://signed.example/pagos_ruana/7_file.png?token=abc"
    assert calls[0] == ("from", "ruana-comprobantes")
    assert calls[1] == ("create_signed_url", "pagos_ruana/7_file.png", 120)
