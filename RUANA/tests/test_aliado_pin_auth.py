"""Tests del sistema de PIN personal y recuperación de acceso aliado."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

import pytest

from core import db_manager as db_module
from core.aliado_pin_auth import hash_pin, verificar_pin
from core.repositories.aliado_repo import AliadoRepo
from core.services import aliado_pin_service
from RUANA.web import app as app_module
from web.limiter import limiter

_repo = AliadoRepo()


@pytest.fixture(autouse=True)
def disable_rate_limit_for_pin_tests():
    previous = limiter.enabled
    limiter.enabled = False
    yield
    limiter.enabled = previous


@pytest.fixture
def sqlite_db(tmp_path, monkeypatch):
    monkeypatch.setattr(
        db_module,
        "get_settings",
        lambda: SimpleNamespace(postgres_configured=False, database_url=""),
    )
    db = db_module.DBManager(str(tmp_path / "pin_auth.db"))
    monkeypatch.setattr(app_module, "get_db", lambda: db)
    monkeypatch.setattr(db_module, "get_db", lambda: db)
    return db


def _crear_aliado(db, codigo: str, email: str | None = None):
    email = email or f"{codigo}@test.ruana"
    result = db.crear_aliado(
        codigo=codigo,
        nombre=f"Aliado {codigo}",
        marca="Marca",
        oficio="Electricidad",
        codigo_postal="28001",
        email=email,
        telefono=f"+346000{codigo}",
        estado="activo",
        score=50,
    )
    assert result["status"] == "success"
    conn = db._connect()
    conn.execute("UPDATE aliados SET estado = 'activo' WHERE codigo = ?", (codigo,))
    conn.commit()
    conn.close()
    return codigo


def _set_pin(db, codigo: str, pin: str):
    conn = db._connect()
    cursor = conn.cursor()
    _repo.update_pin_hash(cursor, codigo, hash_pin(pin))
    conn.commit()
    conn.close()


def _get_recovery_row(db, token_id: int):
    conn = db._connect()
    cursor = conn.cursor()
    row = _repo.select_recuperacion_por_id(cursor, token_id)
    conn.close()
    return dict(row) if row else None


def test_primer_login_sin_pin_requiere_configuracion(client, sqlite_db):
    codigo = _crear_aliado(sqlite_db, "71001")
    resp = client.post("/api/aliado/login", json={"codigo": codigo})
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["pin_setup_required"] is True
    assert data.get("setup_token")
    assert "session_id" not in data


def test_crear_pin_y_login(client, sqlite_db):
    codigo = _crear_aliado(sqlite_db, "71002")
    login = client.post("/api/aliado/login", json={"codigo": codigo}).get_json()
    crear = client.post(
        "/api/aliado/pin/crear",
        json={"setup_token": login["setup_token"], "pin": "1234", "pin_confirmacion": "1234"},
    )
    assert crear.status_code == 200
    data = crear.get_json()
    assert data["status"] == "success"
    assert data.get("session_id")

    ok = client.post("/api/aliado/login", json={"codigo": codigo, "pin": "1234"})
    assert ok.status_code == 200
    assert ok.get_json().get("session_id")


def test_login_pin_incorrecto_mensaje_generico(client, sqlite_db):
    codigo = _crear_aliado(sqlite_db, "71003")
    _set_pin(sqlite_db, codigo, "4321")
    resp = client.post("/api/aliado/login", json={"codigo": codigo, "pin": "9999"})
    assert resp.status_code == 401
    assert resp.get_json()["message"] == "Credenciales incorrectas"


def test_login_codigo_incorrecto_mensaje_generico(client, sqlite_db):
    resp = client.post("/api/aliado/login", json={"codigo": "99998", "pin": "1234"})
    assert resp.status_code == 401
    assert resp.get_json()["message"] == "Credenciales incorrectas"


def test_cambiar_pin_con_sesion(client, sqlite_db, session_headers):
    codigo = _crear_aliado(sqlite_db, "71004")
    _set_pin(sqlite_db, codigo, "1111")
    headers = session_headers("aliado", codigo)
    resp = client.post(
        "/api/aliado/pin/cambiar",
        json={"pin_actual": "1111", "pin_nuevo": "2222", "pin_confirmacion": "2222"},
        headers=headers,
    )
    assert resp.status_code == 200
    login_old = client.post("/api/aliado/login", json={"codigo": codigo, "pin": "1111"})
    assert login_old.status_code == 401
    login_new = client.post("/api/aliado/login", json={"codigo": codigo, "pin": "2222"})
    assert login_new.status_code == 200


@patch("core.email_service.enviar_correo_recuperacion_acceso", return_value=True)
def test_recuperacion_pin(mock_email, client, sqlite_db):
    codigo = _crear_aliado(sqlite_db, "71005", email="recupera@test.ruana")
    _set_pin(sqlite_db, codigo, "5555")

    sol = client.post("/api/aliado/recuperacion/solicitar", json={"tipo": "pin", "codigo": codigo})
    assert sol.status_code == 200
    token_id = sol.get_json()["recovery_token"]

    with patch("core.services.aliado_pin_service._generar_otp", return_value="654321"):
        sol2 = client.post("/api/aliado/recuperacion/solicitar", json={"tipo": "pin", "codigo": codigo})
        token_id = sol2.get_json()["recovery_token"]

    ver = client.post(
        "/api/aliado/recuperacion/verificar",
        json={"recovery_token": token_id, "codigo_temporal": "654321"},
    )
    assert ver.status_code == 200

    pin = client.post(
        "/api/aliado/recuperacion/pin",
        json={"recovery_token": token_id, "pin": "8888", "pin_confirmacion": "8888"},
    )
    assert pin.status_code == 200

    login = client.post("/api/aliado/login", json={"codigo": codigo, "pin": "8888"})
    assert login.status_code == 200


@patch("core.email_service.enviar_correo_recuperacion_acceso", return_value=True)
def test_recuperacion_codigo(mock_email, client, sqlite_db):
    codigo = _crear_aliado(sqlite_db, "71006", email="codigo@test.ruana")

    with patch("core.services.aliado_pin_service._generar_otp", return_value="112233"):
        sol = client.post(
            "/api/aliado/recuperacion/solicitar",
            json={"tipo": "codigo", "email": "codigo@test.ruana"},
        )
    token_id = sol.get_json()["recovery_token"]

    ver = client.post(
        "/api/aliado/recuperacion/verificar",
        json={"recovery_token": token_id, "codigo_temporal": "112233"},
    )
    assert ver.status_code == 200
    assert ver.get_json()["codigo"] == codigo

    ver2 = client.post(
        "/api/aliado/recuperacion/verificar",
        json={"recovery_token": token_id, "codigo_temporal": "112233"},
    )
    assert ver2.status_code == 400


@patch("core.email_service.enviar_correo_recuperacion_acceso", return_value=True)
def test_recuperacion_ambos(mock_email, client, sqlite_db):
    codigo = _crear_aliado(sqlite_db, "71007", email="ambos@test.ruana")
    _set_pin(sqlite_db, codigo, "3333")

    with patch("core.services.aliado_pin_service._generar_otp", return_value="445566"):
        sol = client.post(
            "/api/aliado/recuperacion/solicitar",
            json={"tipo": "ambos", "email": "ambos@test.ruana"},
        )
    token_id = sol.get_json()["recovery_token"]

    ver = client.post(
        "/api/aliado/recuperacion/verificar",
        json={"recovery_token": token_id, "codigo_temporal": "445566"},
    )
    assert ver.get_json()["codigo"] == codigo

    pin = client.post(
        "/api/aliado/recuperacion/pin",
        json={"recovery_token": token_id, "pin": "7777", "pin_confirmacion": "7777"},
    )
    assert pin.status_code == 200
    assert client.post("/api/aliado/login", json={"codigo": codigo, "pin": "7777"}).status_code == 200


def test_codigo_permanente_tras_cambiar_pin(client, sqlite_db, session_headers):
    codigo = _crear_aliado(sqlite_db, "71008")
    _set_pin(sqlite_db, codigo, "1212")
    headers = session_headers("aliado", codigo)
    client.post(
        "/api/aliado/pin/cambiar",
        json={"pin_actual": "1212", "pin_nuevo": "3434", "pin_confirmacion": "3434"},
        headers=headers,
    )
    aliado = sqlite_db.obtener_aliado_por_codigo(codigo)
    assert aliado["codigo"] == codigo


def test_usuario_existente_sin_pin_no_bloqueado(client, sqlite_db):
    codigo = _crear_aliado(sqlite_db, "71009")
    resp = client.post("/api/aliado/login", json={"codigo": codigo})
    assert resp.status_code == 200
    assert resp.get_json().get("pin_setup_required") is True


def test_pin_hash_no_texto_plano(sqlite_db):
    codigo = _crear_aliado(sqlite_db, "71010")
    _set_pin(sqlite_db, codigo, "9090")
    aliado = sqlite_db.obtener_aliado_por_codigo(codigo)
    assert aliado["pin_hash"] != "9090"
    assert verificar_pin("9090", aliado["pin_hash"])


@patch("core.email_service.enviar_correo_recuperacion_acceso", return_value=True)
def test_recuperacion_otp_caducado(mock_email, client, sqlite_db, monkeypatch):
    codigo = _crear_aliado(sqlite_db, "71011", email="caduca@test.ruana")
    with patch("core.services.aliado_pin_service._generar_otp", return_value="101010"):
        sol = client.post(
            "/api/aliado/recuperacion/solicitar",
            json={"tipo": "codigo", "email": "caduca@test.ruana"},
        )
    token_id = sol.get_json()["recovery_token"]

    conn = sqlite_db._connect()
    conn.execute(
        "UPDATE aliado_recuperacion_acceso SET expira_en = '2000-01-01T00:00:00+00:00' WHERE id = ?",
        (token_id,),
    )
    conn.commit()
    conn.close()

    ver = client.post(
        "/api/aliado/recuperacion/verificar",
        json={"recovery_token": token_id, "codigo_temporal": "101010"},
    )
    assert ver.status_code == 400


def test_multiples_intentos_pin_fallidos(client, sqlite_db, monkeypatch):
    monkeypatch.setattr(aliado_pin_service, "PIN_MAX_INTENTOS", 3)
    codigo = _crear_aliado(sqlite_db, "71012")
    _set_pin(sqlite_db, codigo, "2468")
    for _ in range(3):
        client.post("/api/aliado/login", json={"codigo": codigo, "pin": "0000"})
    bloqueado = client.post("/api/aliado/login", json={"codigo": codigo, "pin": "2468"})
    assert bloqueado.status_code == 401


def test_logout_y_sesion_posterior(client, sqlite_db, session_headers):
    codigo = _crear_aliado(sqlite_db, "71013")
    _set_pin(sqlite_db, codigo, "1357")
    login = client.post("/api/aliado/login", json={"codigo": codigo, "pin": "1357"})
    sid = login.get_json()["session_id"]
    headers = {app_module.RUANA_SESSION_HEADER: sid}
    assert client.get("/api/aliado/sesion", headers=headers).status_code == 200
    client.post("/api/aliado/logout", headers=headers)
    assert client.get("/api/aliado/sesion", headers=headers).status_code == 401
    login2 = client.post("/api/aliado/login", json={"codigo": codigo, "pin": "1357"})
    assert login2.status_code == 200
