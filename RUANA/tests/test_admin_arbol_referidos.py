"""Tests del árbol genealógico admin (API raíces + hijos lazy)."""
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
    return db_module.DBManager(str(tmp_path / "ruana_admin_arbol.db"))


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


def test_admin_raices_muestra_padre_con_hijos(client, sqlite_db, monkeypatch):
    """Admin: /raices devuelve raíz; /hijos devuelve hijos al expandir."""
    monkeypatch.setattr(app_module, "get_db", lambda: sqlite_db)
    sqlite_db.obtener_o_crear_invitador_admin("RUANA-ADMIN")
    _crear_activo(sqlite_db, "11111", "Padre")
    _crear_activo(sqlite_db, "22222", "Hijo Uno")
    _crear_activo(sqlite_db, "33333", "Hijo Dos")
    sqlite_db.asignar_invitado_por("22222", "11111", "aliado")
    sqlite_db.asignar_invitado_por("33333", "11111", "aliado")

    headers = _admin_headers()
    raices = client.get("/api/admin/referidos/raices", headers=headers)
    assert raices.status_code == 200
    data = raices.get_json()
    assert data["status"] == "success"
    codigos_raiz = [r["codigo"] for r in data["raices"]]
    assert "RUANA-ADMIN" in codigos_raiz or "11111" in codigos_raiz

    hijos = client.get("/api/admin/referidos/hijos/11111", headers=headers)
    assert hijos.status_code == 200
    payload = hijos.get_json()
    assert len(payload["hijos"]) == 2


def test_admin_raices_fallback_si_grafo_vacio(client, sqlite_db, monkeypatch):
    """Si el grafo en memoria no encuentra raíces, el fallback SQL debe devolverlas."""
    monkeypatch.setattr(app_module, "get_db", lambda: sqlite_db)
    sqlite_db.obtener_o_crear_invitador_admin("RUANA-ADMIN")
    _crear_activo(sqlite_db, "11111", "Padre")
    _crear_activo(sqlite_db, "22222", "Hijo")
    sqlite_db.asignar_invitado_por("22222", "11111", "aliado")

    monkeypatch.setattr(
        referido_service,
        "_listar_raices_desde_grafo",
        lambda grafo: [],
    )

    headers = _admin_headers()
    resp = client.get("/api/admin/referidos/raices", headers=headers)
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["status"] == "success"
    assert len(data["raices"]) >= 1
    assert any(r["codigo"] in ("11111", "RUANA-ADMIN") for r in data["raices"])


def test_admin_arbol_bosque_con_hijos(client, sqlite_db, monkeypatch):
    """Endpoint /arbol sigue devolviendo bosque anidado para vista completa."""
    monkeypatch.setattr(app_module, "get_db", lambda: sqlite_db)
    sqlite_db.obtener_o_crear_invitador_admin("RUANA-ADMIN")
    _crear_activo(sqlite_db, "11111", "Padre")
    _crear_activo(sqlite_db, "22222", "Hijo")
    sqlite_db.asignar_invitado_por("22222", "11111", "aliado")

    headers = _admin_headers()
    resp = client.get("/api/admin/referidos/arbol?profundidad=10", headers=headers)
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["status"] == "success"
    assert data["total_nodos"] >= 2
    bosques = data.get("bosques") or []
    assert bosques

    def _walk(nodo):
        codigos = [nodo.get("codigo")]
        for h in nodo.get("referidos") or []:
            codigos.extend(_walk(h))
        return codigos

    todos = []
    for b in bosques:
        todos.extend(_walk(b))
    assert "11111" in todos
    assert "22222" in todos


def test_grafo_soporta_creado_en_datetime(sqlite_db):
    """PostgreSQL devuelve creado_en como datetime; el grafo no debe fallar con .strip()."""
    from datetime import datetime

    sqlite_db.obtener_o_crear_invitador_admin("RUANA-ADMIN")
    _crear_activo(sqlite_db, "11111", "Padre")
    _crear_activo(sqlite_db, "22222", "Hijo")
    sqlite_db.asignar_invitado_por("22222", "11111", "aliado")

    fake_rows = [
        {
            "codigo_referido": "22222",
            "codigo_invitador": "11111",
            "origen": "aliado",
            "creado_en": datetime(2026, 8, 16, 12, 30, 0),
        }
    ]

    original = referido_service._repo.listar_vinculos_referidos_grafo

    def _fake_vinculos(cursor):
        return fake_rows

    referido_service._repo.listar_vinculos_referidos_grafo = _fake_vinculos
    try:
        grafo = referido_service._cargar_grafo_referidos_red(
            sqlite_db, incluir_pendientes=True
        )
        assert grafo.get("aliados")
        assert grafo.get("referido_en", {}).get(("11111", "22222"))
        raices = referido_service._resolver_raices_referidos(
            sqlite_db, grafo, incluir_pendientes=True
        )
        assert raices
        nodos = referido_service.listar_nodos_raiz_referidos(
            sqlite_db, incluir_pendientes=True
        )
        assert nodos
        assert isinstance(nodos[0].get("creado_en"), str)
    finally:
        referido_service._repo.listar_vinculos_referidos_grafo = original
