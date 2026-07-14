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

    monkeypatch.setattr(app_module, "upload_ruana_file", fake_upload)

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
    assert uploads[0]["bucket"] == "ruana-public"
    assert uploads[0]["folder"] == "fotos_perfil"


def test_eliminar_foto_perfil_solo_propietario(client, fake_db):
    denied = client.delete("/api/aliados/B0002/foto-perfil", headers=_session_headers("A0001"))
    assert denied.status_code == 403

    ok = client.delete("/api/aliados/A0001/foto-perfil", headers=_session_headers("A0001"))
    assert ok.status_code == 200
    assert fake_db.calls == [("actualizar_aliado", "A0001", {"foto_perfil_url": None})]


def test_subir_foto_perfil_acepta_imagen_grande(client, fake_db, monkeypatch):
    from RUANA.core.storage_manager import MAX_UPLOAD_BYTES

    uploads = []

    def fake_upload(**kwargs):
        uploads.append(kwargs)
        return {"url": "https://example.com/foto-grande.jpg"}

    monkeypatch.setattr(app_module, "upload_ruana_file", fake_upload)

    payload = b"x" * (MAX_UPLOAD_BYTES + 1)
    resp = client.post(
        "/api/aliados/A0001/foto-perfil",
        data={"archivo": (io.BytesIO(payload), "selfie.jpg")},
        headers=_session_headers("A0001"),
        content_type="multipart/form-data",
    )
    assert resp.status_code == 200
    assert uploads[0]["max_bytes"] == 15 * 1024 * 1024


def test_put_no_permite_foto_perfil_url(client, fake_db):
    resp = client.put(
        "/api/aliados/A0001",
        json={"foto_perfil_url": "https://evil.example/x.jpg"},
        headers={**_session_headers("A0001"), "Content-Type": "application/json"},
    )
    assert resp.status_code == 400
    assert fake_db.calls == []
