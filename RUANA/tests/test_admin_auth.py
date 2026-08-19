import base64
import json
import os
from pathlib import Path
from urllib.error import HTTPError
from io import BytesIO

from RUANA.core import admin_auth as admin_auth_module
from RUANA.core.admin_auth import change_admin_password, verify_admin_login


def test_verify_admin_login_accepts_qa_credentials():
    result = verify_admin_login("ADMIN001", "ADMIN001")
    assert result is not None
    assert result["codigo"] == "ADMIN001"
    assert "escribir" in result["permisos"]


def test_verify_admin_login_rejects_invalid_password():
    assert verify_admin_login("ADMIN001", "wrong-password") is None


def test_validar_admin_legacy_single_field(client):
    response = client.post("/api/admin/validar", json={"codigo": "ADMIN001"})
    assert response.status_code == 200
    data = response.get_json()
    assert data["status"] == "success"
    assert data["session_id"]


def test_validar_admin_with_explicit_password(client):
    response = client.post(
        "/api/admin/validar",
        json={"codigo": "ADMIN001", "password": "ADMIN001"},
    )
    assert response.status_code == 200
    data = response.get_json()
    assert data["status"] == "success"


def test_validar_admin_rejects_invalid_credentials(client):
    response = client.post(
        "/api/admin/validar",
        json={"codigo": "ADMIN001", "password": "not-the-password"},
    )
    assert response.status_code == 401


def test_cambiar_contraseña_requires_authentication(client):
    response = client.post(
        "/api/admin/cambiar-contraseña",
        json={
            "contraseña_actual": "ADMIN001",
            "contraseña_nueva": "NuevaClaveSegura1",
        },
    )
    assert response.status_code == 401


def test_cambiar_contraseña_updates_password(client, session_headers):
    headers = session_headers(
        "admin",
        "ADMIN001",
        permisos=["leer", "escribir", "configurar"],
    )

    response = client.post(
        "/api/admin/cambiar-contraseña",
        headers=headers,
        json={
            "contraseña_actual": "ADMIN001",
            "contraseña_nueva": "NuevaClaveSegura1",
            "contraseña_confirmacion": "NuevaClaveSegura1",
        },
    )
    assert response.status_code == 200
    assert response.get_json()["status"] == "success"
    assert verify_admin_login("ADMIN001", "NuevaClaveSegura1") is not None
    assert verify_admin_login("ADMIN001", "ADMIN001") is None

    # Restaurar contraseña original para no afectar otras pruebas
    restore = change_admin_password("ADMIN001", "NuevaClaveSegura1", "ADMIN001")
    assert restore["status"] == "success"


def test_cambiar_contraseña_rejects_wrong_current_password(client, session_headers):
    headers = session_headers(
        "admin",
        "ADMIN001",
        permisos=["leer", "escribir", "configurar"],
    )

    response = client.post(
        "/api/admin/cambiar-contraseña",
        headers=headers,
        json={
            "contraseña_actual": "incorrecta",
            "contraseña_nueva": "OtraClaveSegura9",
        },
    )
    assert response.status_code == 400
    assert "no es correcta" in response.get_json()["message"]


def test_admin_html_exposes_change_password_ui():
    admin_html = Path(__file__).resolve().parents[1] / "web" / "admin.html"
    text = admin_html.read_text(encoding="utf-8")
    assert 'id="admin-change-password-btn"' in text
    assert "/api/admin/cambiar-contraseña" in text
    assert 'id="adminLoginPassword"' in text


def test_change_password_when_only_env_json_exists(tmp_path, monkeypatch):
    qa_path = Path(__file__).resolve().parents[1] / "config" / "admin_credentials.qa.json"
    qa = json.loads(qa_path.read_text(encoding="utf-8"))
    monkeypatch.setenv("RUANA_ADMIN_CREDENTIALS_PATH", str(tmp_path / "overlay.json"))
    monkeypatch.setenv("RUANA_ADMIN_CREDENTIALS_JSON", json.dumps(qa, ensure_ascii=False))
    monkeypatch.setenv("RUANA_ADMIN_USE_SECRET_MANAGER", "0")

    result = change_admin_password("ADMIN001", "ADMIN001", "NuevaClaveSegura1")
    assert result["status"] == "success"
    assert verify_admin_login("ADMIN001", "NuevaClaveSegura1") is not None
    assert verify_admin_login("ADMIN001", "ADMIN001") is None


def test_change_password_survives_env_json_reload(monkeypatch):
    credentials_path = Path(os.environ["RUANA_ADMIN_CREDENTIALS_PATH"])
    original = credentials_path.read_text(encoding="utf-8")
    original_hash = json.loads(original)["admins"]["ADMIN001"]["password_hash"]
    monkeypatch.setenv("RUANA_ADMIN_CREDENTIALS_JSON", json.dumps(json.loads(original)))

    result = change_admin_password("ADMIN001", "ADMIN001", "NuevaClaveSegura1")
    assert result["status"] == "success"
    assert verify_admin_login("ADMIN001", "NuevaClaveSegura1") is not None
    assert verify_admin_login("ADMIN001", "ADMIN001") is None

    env_after = json.loads(os.environ["RUANA_ADMIN_CREDENTIALS_JSON"])
    assert env_after["admins"]["ADMIN001"]["password_hash"] != original_hash

    restore = change_admin_password("ADMIN001", "NuevaClaveSegura1", "ADMIN001")
    assert restore["status"] == "success"


def test_production_does_not_bootstrap_qa_credentials(tmp_path, monkeypatch):
    monkeypatch.setenv("RUANA_ENV", "production")
    monkeypatch.setenv("K_SERVICE", "ruana")
    monkeypatch.setenv("RUANA_ADMIN_USE_SECRET_MANAGER", "0")
    monkeypatch.setenv("RUANA_ADMIN_CREDENTIALS_PATH", str(tmp_path / "missing-admin.json"))
    monkeypatch.delenv("RUANA_ADMIN_CREDENTIALS_JSON", raising=False)

    data = admin_auth_module.load_credentials(allow_bootstrap=True)
    assert data.get("admins") == {}


def _qa_credentials_payload() -> dict:
    path = Path(os.environ["RUANA_ADMIN_CREDENTIALS_PATH"])
    return json.loads(path.read_text(encoding="utf-8"))


def test_change_password_persists_to_secret_manager(monkeypatch):
    store = {"data": _qa_credentials_payload()}
    monkeypatch.setenv("RUANA_ADMIN_USE_SECRET_MANAGER", "1")
    monkeypatch.setattr(
        admin_auth_module,
        "try_secret_manager_access_latest",
        lambda: json.loads(json.dumps(store["data"])),
    )
    monkeypatch.setattr(
        admin_auth_module,
        "secret_manager_add_version",
        lambda data: store.update({"data": json.loads(json.dumps(data))}),
    )

    result = change_admin_password("ADMIN001", "ADMIN001", "NuevaClaveSegura1")
    assert result["status"] == "success"
    assert verify_admin_login("ADMIN001", "NuevaClaveSegura1") is not None
    assert verify_admin_login("ADMIN001", "ADMIN001") is None
    assert "NuevaClaveSegura1" not in json.dumps(store["data"])

    restore = change_admin_password("ADMIN001", "NuevaClaveSegura1", "ADMIN001")
    assert restore["status"] == "success"


def test_change_password_keeps_old_password_if_secret_manager_fails(monkeypatch):
    original = _qa_credentials_payload()
    monkeypatch.setenv("RUANA_ADMIN_USE_SECRET_MANAGER", "1")
    monkeypatch.setattr(
        admin_auth_module,
        "try_secret_manager_access_latest",
        lambda: json.loads(json.dumps(original)),
    )

    def boom(_data):
        raise RuntimeError("permission denied")

    monkeypatch.setattr(admin_auth_module, "secret_manager_add_version", boom)

    result = change_admin_password("ADMIN001", "ADMIN001", "NuevaClaveSegura1")
    assert result["status"] == "error"
    assert "Secret Manager" in result["message"]
    assert verify_admin_login("ADMIN001", "ADMIN001") is not None
    assert verify_admin_login("ADMIN001", "NuevaClaveSegura1") is None


class _FakeResponse:
    def __init__(self, payload: bytes, status: int = 200):
        self._payload = payload
        self.status = status

    def read(self) -> bytes:
        return self._payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


def test_secret_manager_add_version_posts_base64_payload(monkeypatch):
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "ruana-4293f")
    captured = {}

    def fake_urlopen(request, timeout=None):
        url = request.get_full_url()
        if "metadata.google.internal" in url:
            return _FakeResponse(b'{"access_token":"tok-test"}')
        captured["url"] = url
        captured["body"] = json.loads(request.data.decode("utf-8"))
        captured["authorization"] = request.headers.get("Authorization")
        return _FakeResponse(b'{"name":"projects/ruana-4293f/secrets/ruana-admin-credentials/versions/2"}')

    monkeypatch.setattr(admin_auth_module.urllib.request, "urlopen", fake_urlopen)
    payload = {"version": 1, "admins": {"7772735": {"password_hash": "hash"}}}
    admin_auth_module.secret_manager_add_version(payload)

    assert captured["url"].endswith("secrets/ruana-admin-credentials:addSecretVersion")
    assert captured["authorization"] == "Bearer tok-test"
    decoded = json.loads(base64.b64decode(captured["body"]["payload"]["data"]))
    assert decoded == payload


def test_secret_manager_access_latest_returns_none_on_http_error(monkeypatch):
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "ruana-4293f")

    def fake_urlopen(request, timeout=None):
        url = request.get_full_url()
        if "metadata.google.internal" in url:
            return _FakeResponse(b'{"access_token":"tok-test"}')
        raise HTTPError(url, 403, "Forbidden", hdrs=None, fp=BytesIO(b'{"error":"denied"}'))

    monkeypatch.setattr(admin_auth_module.urllib.request, "urlopen", fake_urlopen)
    assert admin_auth_module.try_secret_manager_access_latest() is None
