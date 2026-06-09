from io import BytesIO

import pytest


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
