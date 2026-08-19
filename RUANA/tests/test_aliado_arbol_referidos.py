"""Tests del árbol genealógico del aliado (API + linaje unificado)."""
from types import SimpleNamespace

import pytest

from core import db_manager as db_module
from core.services import referido_service
from RUANA.web import app as app_module


@pytest.fixture
def sqlite_db(tmp_path, monkeypatch):
    monkeypatch.setattr(
        db_module,
        "get_settings",
        lambda: SimpleNamespace(postgres_configured=False, database_url=""),
    )
    return db_module.DBManager(str(tmp_path / "ruana_aliado_arbol.db"))


def _session_headers(codigo):
    session_id = app_module._ruana_session_create(
        tipo="aliado",
        codigo=codigo,
        expires_at=9999999999,
    )
    return {app_module.RUANA_SESSION_HEADER: session_id}


def _admin_headers():
    session_id = app_module._ruana_session_create(
        tipo="admin",
        codigo="ADMIN001",
        expires_at=9999999999,
        permisos=["leer", "escribir"],
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


def test_padre_con_dos_hijos_directos(client, sqlite_db, monkeypatch):
    """TEST 1: padre con 2 hijos → API hijos devuelve 2."""
    monkeypatch.setattr(app_module, "get_db", lambda: sqlite_db)
    _crear_activo(sqlite_db, "11111", "Padre")
    _crear_activo(sqlite_db, "22222", "Hijo Uno")
    _crear_activo(sqlite_db, "33333", "Hijo Dos")
    sqlite_db.asignar_invitado_por("22222", "11111", "aliado")
    sqlite_db.asignar_invitado_por("33333", "11111", "aliado")

    resp = client.get(
        "/api/aliado/referidos/hijos/11111",
        headers=_session_headers("11111"),
    )
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["status"] == "success"
    assert len(data["hijos"]) == 2
    assert data["nodo"]["referidos_count"] == 2


def test_hijo_con_nieto_expandible(client, sqlite_db, monkeypatch):
    """TEST 2: padre → hijo → nieto en dos niveles."""
    monkeypatch.setattr(app_module, "get_db", lambda: sqlite_db)
    _crear_activo(sqlite_db, "11111", "Padre")
    _crear_activo(sqlite_db, "22222", "Hijo")
    _crear_activo(sqlite_db, "33333", "Nieto")
    sqlite_db.asignar_invitado_por("22222", "11111", "aliado")
    sqlite_db.asignar_invitado_por("33333", "22222", "aliado")

    hijos = client.get(
        "/api/aliado/referidos/hijos/11111",
        headers=_session_headers("11111"),
    ).get_json()
    assert len(hijos["hijos"]) == 1
    assert hijos["hijos"][0]["codigo"] == "22222"

    nietos = client.get(
        "/api/aliado/referidos/hijos/22222",
        headers=_session_headers("11111"),
    ).get_json()
    assert len(nietos["hijos"]) == 1
    assert nietos["hijos"][0]["codigo"] == "33333"


def test_usuario_sin_hijos_estado_vacio(client, sqlite_db, monkeypatch):
    """TEST 3: sin hijos → lista vacía y contador 0."""
    monkeypatch.setattr(app_module, "get_db", lambda: sqlite_db)
    _crear_activo(sqlite_db, "44444", "Solitario")

    raiz = client.get(
        "/api/aliado/referidos/raiz",
        headers=_session_headers("44444"),
    ).get_json()
    assert raiz["nodo"]["referidos_count"] == 0
    assert raiz["total_descendientes_directos"] == 0

    hijos = client.get(
        "/api/aliado/referidos/hijos/44444",
        headers=_session_headers("44444"),
    ).get_json()
    assert hijos["hijos"] == []


def test_referidos_sin_invitado_por_backfill_y_listado(client, sqlite_db, monkeypatch):
    """TEST 4: fila en referidos sin invitado_por → aparece tras sync."""
    monkeypatch.setattr(app_module, "get_db", lambda: sqlite_db)
    _crear_activo(sqlite_db, "11111", "Padre")
    _crear_activo(sqlite_db, "22222", "Hijo Legacy")

    conn = sqlite_db._connect()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO referidos (codigo_referido, codigo_invitador, origen) VALUES (?, ?, ?)",
        ("22222", "11111", "aliado"),
    )
    cur.execute(
        "UPDATE aliados SET invitado_por_codigo = NULL, invitado_origen = '' WHERE codigo = '22222'"
    )
    conn.commit()
    conn.close()

    hijos = referido_service.listar_referidos_directos(sqlite_db, "11111")
    assert len(hijos) == 1
    assert hijos[0]["codigo"] == "22222"

    resp = client.get(
        "/api/aliado/linaje/hijos",
        headers=_session_headers("11111"),
    )
    assert resp.status_code == 200
    assert len(resp.get_json()["hijos"]) == 1


def test_solo_invitado_por_sin_referidos(client, sqlite_db, monkeypatch):
    """TEST 5: invitado_por_codigo basta aunque falte fila en referidos."""
    monkeypatch.setattr(app_module, "get_db", lambda: sqlite_db)
    _crear_activo(sqlite_db, "11111", "Padre")
    _crear_activo(sqlite_db, "22222", "Hijo Linaje")
    sqlite_db.asignar_invitado_por("22222", "11111", "aliado")

    conn = sqlite_db._connect()
    cur = conn.cursor()
    cur.execute("DELETE FROM referidos WHERE codigo_referido = '22222'")
    conn.commit()
    conn.close()

    hijos = referido_service.listar_referidos_directos(sqlite_db, "11111")
    assert len(hijos) == 1
    assert hijos[0]["codigo"] == "22222"


def test_403_arbol_ajeno(client, sqlite_db, monkeypatch):
    """TEST 6: aliado no puede ver hijos de otro sin descendencia."""
    monkeypatch.setattr(app_module, "get_db", lambda: sqlite_db)
    _crear_activo(sqlite_db, "11111", "Aliado A")
    _crear_activo(sqlite_db, "22222", "Aliado B")
    _crear_activo(sqlite_db, "33333", "Hijo de B")
    sqlite_db.asignar_invitado_por("33333", "22222", "aliado")

    resp = client.get(
        "/api/aliado/referidos/hijos/22222",
        headers=_session_headers("11111"),
    )
    assert resp.status_code == 403


def test_cuatro_niveles_linaje(client, sqlite_db, monkeypatch):
    """TEST 7: padre → hijo → nieto → bisnieto."""
    monkeypatch.setattr(app_module, "get_db", lambda: sqlite_db)
    codigos = ["10001", "10002", "10003", "10004"]
    nombres = ["Abuelo", "Padre", "Hijo", "Bisnieto"]
    for c, n in zip(codigos, nombres):
        _crear_activo(sqlite_db, c, n)
    for i in range(1, len(codigos)):
        sqlite_db.asignar_invitado_por(codigos[i], codigos[i - 1], "aliado")

    headers = _session_headers("10001")
    assert len(client.get(f"/api/aliado/referidos/hijos/10001", headers=headers).get_json()["hijos"]) == 1
    assert len(client.get(f"/api/aliado/referidos/hijos/10002", headers=headers).get_json()["hijos"]) == 1
    assert len(client.get(f"/api/aliado/referidos/hijos/10003", headers=headers).get_json()["hijos"]) == 1
    assert len(client.get(f"/api/aliado/referidos/hijos/10004", headers=headers).get_json()["hijos"]) == 0


def test_registro_invitacion_aparece_en_arbol(client, sqlite_db, monkeypatch):
    """TEST 8: registro con código de invitación → hijo visible en árbol del padre."""
    monkeypatch.setattr(app_module, "get_db", lambda: sqlite_db)
    sqlite_db.obtener_o_crear_invitador_admin("RUANA-ADMIN")
    _crear_activo(sqlite_db, "11111", "Invitador")

    create_inv = client.post(
        "/api/invitaciones/crear",
        headers=_session_headers("11111"),
        json={"zona": "28001"},
    )
    assert create_inv.status_code == 201
    codigo_inv = create_inv.get_json()["codigo"]

    register = client.post(
        "/api/aliados/registrar",
        json={
            "nombre": "Nuevo Referido",
            "marca": "NR",
            "oficio": "Electricidad",
            "oficio_principal": "Electricidad",
            "especializacion": "Averias y reparaciones electricas",
            "codigo_postal": "28001",
            "email": "nuevo@example.com",
            "telefono": "+34600999111",
            "codigo_invitacion": codigo_inv,
            "acepta_privacidad_y_terminos": True,
        },
    )
    assert register.status_code == 201
    codigo_hijo = register.get_json()["codigo"]

    hijos = client.get(
        "/api/aliado/referidos/hijos/11111",
        headers=_session_headers("11111"),
    ).get_json()
    codigos_hijos = [h["codigo"] for h in hijos["hijos"]]
    assert codigo_hijo in codigos_hijos

    conn = sqlite_db._connect()
    cur = conn.cursor()
    cur.execute("SELECT invitado_por_codigo FROM aliados WHERE codigo = ?", (codigo_hijo,))
    row = cur.fetchone()
    conn.close()
    assert row[0] == "11111"
