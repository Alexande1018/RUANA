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
    from pathlib import Path

    root = Path(__file__).resolve().parents[1] / "web"
    admin_html = (root / "admin.html").read_text(encoding="utf-8")
    host = (root / "static" / "js" / "admin-panel-host.js").read_text(encoding="utf-8")
    assert 'id="admin-change-password-btn"' in admin_html
    assert "/api/admin/cambiar-contraseña" in host
    assert 'id="adminLoginPassword"' in admin_html
