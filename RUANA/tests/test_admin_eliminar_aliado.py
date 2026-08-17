from types import SimpleNamespace

import pytest

from core import db_manager as db_module
from RUANA.web import app as app_module


@pytest.fixture
def sqlite_db(tmp_path, monkeypatch):
    monkeypatch.setattr(
        db_module,
        "get_settings",
        lambda: SimpleNamespace(postgres_configured=False, database_url=""),
    )
    return db_module.DBManager(str(tmp_path / "ruana_eliminar_aliado.db"))


def _admin_headers(permisos=None):
    session_id = app_module._ruana_session_create(
        tipo="admin",
        codigo="ADMIN001",
        expires_at=9999999999,
        permisos=permisos or ["leer", "escribir"],
    )
    return {app_module.RUANA_SESSION_HEADER: session_id}


def _crear_activo(db, codigo, nombre):
    result = db.crear_aliado(
        codigo=codigo,
        nombre=nombre,
        marca="Marca",
        oficio="Electricidad",
        codigo_postal="28001",
        email=f"{codigo}@example.com",
        telefono=f"+34600{codigo}",
        estado="activo",
        score=50,
        especializacion="Averías y reparaciones eléctricas",
    )
    assert result["status"] == "success"
    return result


def test_eliminar_perfil_activo_borra_definitivamente(sqlite_db):
    _crear_activo(sqlite_db, "90001", "Aliado Activo")

    result = sqlite_db.eliminar_perfil_aliado_admin("90001", motivo="Prueba admin")
    assert result["status"] == "success"
    assert result["accion"] == "eliminado"

    assert sqlite_db.obtener_aliado_por_codigo("90001") is None

    conn = sqlite_db._connect()
    cur = conn.cursor()
    cur.execute("SELECT nombre FROM aliados WHERE codigo = ?", ("90001",))
    nombre_bd = cur.fetchone()[0]
    conn.close()
    assert "Aliado Activo" in nombre_bd and "eliminado" in nombre_bd.lower()

    eliminados = sqlite_db.listar_aliados_eliminados()
    assert len(eliminados) == 1
    assert eliminados[0]["codigo"] == "90001"
    assert eliminados[0]["estado_anterior"] == "activo"
    assert eliminados[0]["motivo"] == "Prueba admin"


def test_listar_aliados_excluye_eliminados(sqlite_db):
    _crear_activo(sqlite_db, "90010", "Visible")
    _crear_activo(sqlite_db, "90011", "A Borrar")
    sqlite_db.eliminar_perfil_aliado_admin("90011")
    codigos = {a["codigo"] for a in sqlite_db.listar_aliados()}
    assert "90010" in codigos
    assert "90011" not in codigos


def test_eliminar_perfil_libera_email_y_telefono(sqlite_db):
    _crear_activo(sqlite_db, "90001", "Aliado Uno")
    sqlite_db.eliminar_perfil_aliado_admin("90001")

    result = sqlite_db.crear_aliado(
        codigo="90002",
        nombre="Aliado Nuevo",
        marca="Marca",
        oficio="Electricidad",
        codigo_postal="28001",
        email="90001@example.com",
        telefono="+3460090001",
        estado="activo",
        score=50,
        especializacion="Averías y reparaciones eléctricas",
    )
    assert result["status"] == "success"


def test_eliminar_perfil_pendiente_validacion_borra_definitivamente(sqlite_db):
    sqlite_db.crear_aliado(
        codigo="90002",
        nombre="Pendiente",
        marca="Marca",
        oficio="Fontanería",
        codigo_postal="28001",
        email="90002@example.com",
        telefono="+3460090002",
        estado="pendiente_validacion",
        score=50,
        especializacion="Reparaciones de fontanería",
    )

    result = sqlite_db.eliminar_perfil_aliado_admin("90002")
    assert result["status"] == "success"
    assert result["accion"] == "eliminado"
    assert sqlite_db.obtener_aliado_por_codigo("90002") is None

    eliminados = sqlite_db.listar_aliados_eliminados()
    assert len(eliminados) == 1
    assert eliminados[0]["estado_anterior"] == "pendiente_validacion"


def test_eliminar_perfil_bloquea_sistema(sqlite_db):
    sqlite_db.obtener_o_crear_invitador_admin("RUANA-ADMIN")

    result = sqlite_db.eliminar_perfil_aliado_admin("RUANA-ADMIN")
    assert result["status"] == "error"
    assert "sistema" in result["message"].lower()


def test_eliminar_perfil_purga_datos_relacionados(sqlite_db):
    _crear_activo(sqlite_db, "90005", "Con Datos")
    sqlite_db.aplicar_cambio_score("90005", 5, motivo="test")

    conn = sqlite_db._connect()
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO notificaciones_aliado (aliado_codigo, tipo, titulo, mensaje)
        VALUES (?, 'info', 'Test', 'Notificación de prueba')
        """,
        ("90005",),
    )
    conn.commit()
    conn.close()

    result = sqlite_db.eliminar_perfil_aliado_admin("90005")
    assert result["status"] == "success"

    conn = sqlite_db._connect()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM score_movimientos WHERE codigo_aliado = ?", ("90005",))
    assert cursor.fetchone()[0] == 0
    cursor.execute("SELECT COUNT(*) FROM notificaciones_aliado WHERE aliado_codigo = ?", ("90005",))
    assert cursor.fetchone()[0] == 0
    conn.close()


def test_admin_eliminar_aliado_endpoint(client, sqlite_db, monkeypatch):
    monkeypatch.setattr(app_module, "get_db", lambda: sqlite_db)
    _crear_activo(sqlite_db, "90003", "Endpoint Aliado")

    resp = client.post(
        "/api/admin/eliminar-aliado",
        headers=_admin_headers(),
        json={"codigo": "90003", "motivo": "Test endpoint"},
    )
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["status"] == "success"
    assert sqlite_db.obtener_aliado_por_codigo("90003") is None


def test_admin_eliminar_aliado_invalida_sesion(client, sqlite_db, monkeypatch):
    monkeypatch.setattr(app_module, "get_db", lambda: sqlite_db)
    _crear_activo(sqlite_db, "90006", "Sesion Aliado")

    session_id = app_module._ruana_session_create("aliado", "90006", expires_at=9999999999)

    resp = client.post(
        "/api/admin/eliminar-aliado",
        headers=_admin_headers(),
        json={"codigo": "90006"},
    )
    assert resp.status_code == 200
    assert session_id in app_module._RUANA_SESSION_REVOKED


def test_admin_listar_aliados_eliminados_endpoint(client, sqlite_db, monkeypatch):
    monkeypatch.setattr(app_module, "get_db", lambda: sqlite_db)
    _crear_activo(sqlite_db, "90007", "Listado")
    sqlite_db.eliminar_perfil_aliado_admin("90007", motivo="Archivo")

    resp = client.get("/api/admin/aliados-eliminados", headers=_admin_headers())
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["status"] == "success"
    assert len(data["aliados"]) == 1
    assert data["aliados"][0]["codigo"] == "90007"


def test_admin_eliminar_aliado_rechaza_solo_lectura(client, sqlite_db, monkeypatch):
    monkeypatch.setattr(app_module, "get_db", lambda: sqlite_db)
    _crear_activo(sqlite_db, "90004", "Solo Lectura")

    resp = client.post(
        "/api/admin/eliminar-aliado",
        headers=_admin_headers(permisos=["leer"]),
        json={"codigo": "90004"},
    )
    assert resp.status_code == 403
    assert sqlite_db.obtener_aliado_por_codigo("90004")["estado"] == "activo"
