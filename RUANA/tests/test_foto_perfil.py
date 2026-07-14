import io

import pytest

from RUANA.web import app as app_module


class FotoPerfilFakeDB:
    def __init__(self):
        self.calls = []

    def actualizar_aliado(self, codigo, **kwargs):
        if not kwargs:
            return {"status": "error", "message": "No fields to update"}
        self.calls.append(("actualizar_aliado", codigo, kwargs))
        return {"status": "success", "message": "Aliado actualizado"}


@pytest.fixture(autouse=True)
def clear_ruana_sessions():
    previous_testing = app_module.app.config.get("TESTING")
    with app_module._RUANA_SESSION_LOCK:
        app_module._RUANA_SESSION_STORE.clear()
    app_module.app.config.update(TESTING=True)
    yield
    with app_module._RUANA_SESSION_LOCK:
        app_module._RUANA_SESSION_STORE.clear()
    app_module.app.config.update(TESTING=previous_testing)


@pytest.fixture
def fake_db(monkeypatch):
    db = FotoPerfilFakeDB()
    monkeypatch.setattr(app_module, "get_db", lambda: db)
    return db


@pytest.fixture
def client():
    return app_module.app.test_client()


def _session_headers(codigo="A0001"):
    expires_at = __import__("time").time() + 3600
    session_id = app_module._ruana_session_create("aliado", codigo, expires_at)
    return {"X-Ruana-Session-Id": session_id}


def test_subir_foto_perfil_solo_propietario(client, fake_db, monkeypatch):
    uploads = []

    def fake_upload(**kwargs):
        uploads.append(kwargs)
        return {"url": "https://example.com/foto.jpg"}

    monkeypatch.setattr(app_module, "upload_foto_perfil_file", fake_upload)

    denied = client.post(
        "/api/aliados/B0002/foto-perfil",
        data={"archivo": (io.BytesIO(b"fake"), "foto.jpg")},
        headers=_session_headers("A0001"),
        content_type="multipart/form-data",
    )
    assert denied.status_code == 403

    ok = client.post(
        "/api/aliados/A0001/foto-perfil",
        data={"archivo": (io.BytesIO(b"fake"), "foto.jpg")},
        headers=_session_headers("A0001"),
        content_type="multipart/form-data",
    )
    assert ok.status_code == 200
    data = ok.get_json()
    assert data["status"] == "success"
    assert data["foto_perfil_url"] == "https://example.com/foto.jpg"
    assert fake_db.calls == [("actualizar_aliado", "A0001", {"foto_perfil_url": "https://example.com/foto.jpg"})]
    assert uploads[0]["prefix"] == "A0001"
    assert uploads[0]["original_filename"] == "foto.jpg"


def test_eliminar_foto_perfil_solo_propietario(client, fake_db):
    denied = client.delete("/api/aliados/B0002/foto-perfil", headers=_session_headers("A0001"))
    assert denied.status_code == 403

    ok = client.delete("/api/aliados/A0001/foto-perfil", headers=_session_headers("A0001"))
    assert ok.status_code == 200
    assert fake_db.calls == [("actualizar_aliado", "A0001", {"foto_perfil_url": None})]


def test_subir_foto_perfil_optimiza_antes_de_subir(client, fake_db, monkeypatch):
    from io import BytesIO

    from PIL import Image

    import core.storage_manager as storage_manager

    uploads = []

    class FakeBucket:
        def upload(self, path, data, file_options=None):
            uploads.append({
                "path": path,
                "size": len(data),
                "content_type": file_options.get("content-type"),
            })
            return {"path": path}

        def get_public_url(self, path):
            return f"https://storage.example/{path}"

    class FakeStorage:
        def from_(self, bucket):
            return FakeBucket()

    class FakeClient:
        storage = FakeStorage()

    monkeypatch.setattr(storage_manager, "get_supabase_admin_client", lambda: FakeClient())

    img = Image.new("RGB", (3200, 2400), color=(90, 140, 210))
    out = BytesIO()
    img.save(out, format="JPEG", quality=95)
    raw = out.getvalue()

    resp = client.post(
        "/api/aliados/A0001/foto-perfil",
        data={"archivo": (io.BytesIO(raw), "selfie.jpg")},
        headers=_session_headers("A0001"),
        content_type="multipart/form-data",
    )
    assert resp.status_code == 200
    assert uploads
    assert uploads[0]["size"] < len(raw)
    assert uploads[0]["size"] <= 1_800_000
    assert uploads[0]["content_type"] == "image/jpeg"


def test_put_no_permite_foto_perfil_url(client, fake_db):
    resp = client.put(
        "/api/aliados/A0001",
        json={"foto_perfil_url": "https://evil.example/x.jpg"},
        headers={**_session_headers("A0001"), "Content-Type": "application/json"},
    )
    assert resp.status_code == 400
    assert fake_db.calls == []
