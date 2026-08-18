"""Tests del árbol genealógico v2 — linaje, campañas, orgánicos, score, permisos."""
from types import SimpleNamespace

import pytest

from core import db_manager as db_module
from core.services import red_arbol_service, referido_service
from RUANA.web import app as app_module


@pytest.fixture
def sqlite_db(tmp_path, monkeypatch):
    monkeypatch.setattr(
        db_module,
        "get_settings",
        lambda: SimpleNamespace(postgres_configured=False, database_url=""),
    )
    return db_module.DBManager(str(tmp_path / "ruana_red_v2.db"))


def _session_headers(codigo, tipo="aliado"):
    session_id = app_module._ruana_session_create(
        tipo=tipo,
        codigo=codigo,
        expires_at=9999999999,
        permisos=["leer", "escribir"] if tipo == "admin" else None,
    )
    return {app_module.RUANA_SESSION_HEADER: session_id}


def _crear_activo(db, codigo, nombre, **kwargs):
    result = db.crear_aliado(
        codigo=codigo,
        nombre=nombre,
        marca=kwargs.get("marca", "Marca"),
        oficio=kwargs.get("oficio", "Electricidad"),
        codigo_postal=kwargs.get("codigo_postal", "28001"),
        email=kwargs.get("email", f"{codigo}@example.com"),
        telefono=kwargs.get("telefono", f"+34600{codigo}"),
        estado=kwargs.get("estado", "activo"),
        score=kwargs.get("score", 50),
        especializacion=kwargs.get("especializacion", "Averías y reparaciones eléctricas"),
    )
    assert result["status"] == "success"
    return result


def test_padre_hijo_directo(sqlite_db):
    sqlite_db.obtener_o_crear_invitador_admin("RUANA-ADMIN")
    _crear_activo(sqlite_db, "10001", "Padre")
    _crear_activo(sqlite_db, "10002", "Hijo")
    assert sqlite_db.asignar_invitado_por("10002", "10001", "ampliar_red")
    hijos = referido_service.listar_referidos_directos(sqlite_db, "10001")
    assert len(hijos) == 1
    assert hijos[0]["codigo"] == "10002"


def test_padre_hijo_nieto(sqlite_db):
    sqlite_db.obtener_o_crear_invitador_admin("RUANA-ADMIN")
    _crear_activo(sqlite_db, "20001", "Abuelo")
    _crear_activo(sqlite_db, "20002", "Padre")
    _crear_activo(sqlite_db, "20003", "Nieto")
    sqlite_db.asignar_invitado_por("20002", "20001", "ampliar_red")
    sqlite_db.asignar_invitado_por("20003", "20002", "ampliar_red")
    ancestros = sqlite_db.ancestros_referidos_para_score("20003", max_generaciones=2)
    assert ("20002", 1) in ancestros
    assert ("20001", 2) in ancestros


def test_cadena_cuatro_niveles(sqlite_db):
    sqlite_db.obtener_o_crear_invitador_admin("RUANA-ADMIN")
    for i, cod in enumerate(["30001", "30002", "30003", "30004"], start=1):
        _crear_activo(sqlite_db, cod, f"Nivel{i}")
    sqlite_db.asignar_invitado_por("30002", "30001", "ampliar_red")
    sqlite_db.asignar_invitado_por("30003", "30002", "ampliar_red")
    sqlite_db.asignar_invitado_por("30004", "30003", "ampliar_red")
    hijos = referido_service.listar_referidos_directos(sqlite_db, "30003")
    assert len(hijos) == 1
    assert hijos[0]["codigo"] == "30004"


def test_dos_hijos_directos(sqlite_db):
    sqlite_db.obtener_o_crear_invitador_admin("RUANA-ADMIN")
    _crear_activo(sqlite_db, "40001", "Padre")
    _crear_activo(sqlite_db, "40002", "Hijo A")
    _crear_activo(sqlite_db, "40003", "Hijo B")
    sqlite_db.asignar_invitado_por("40002", "40001", "ampliar_red")
    sqlite_db.asignar_invitado_por("40003", "40001", "yo_conozco_a_alguien")
    hijos = referido_service.listar_referidos_directos(sqlite_db, "40001")
    assert {h["codigo"] for h in hijos} == {"40002", "40003"}


def test_campana_sin_padre_aliado(sqlite_db):
    sqlite_db.obtener_o_crear_invitador_admin("RUANA-ADMIN")
    _crear_activo(sqlite_db, "50001", "Campana Aliado")
    sqlite_db.crear_campana_invitacion("MADRID2026", "Madrid", "28001", 10, "RUANA-ADMIN")
    sqlite_db.consumir_campana_invitacion("MADRID2026", "50001")
    conn = sqlite_db._connect()
    cur = conn.cursor()
    cur.execute(
        "SELECT invitado_por_codigo, invitado_origen FROM aliados WHERE codigo = ?",
        ("50001",),
    )
    row = cur.fetchone()
    conn.close()
    assert row[0] is None or str(row[0]).strip() == ""
    assert row[1] == "campana"


def test_organico_sin_padre(sqlite_db):
    sqlite_db.obtener_o_crear_invitador_admin("RUANA-ADMIN")
    _crear_activo(sqlite_db, "60001", "Organico")
    referido_service.sincronizar_referidos_huerfanos_admin(sqlite_db)
    conn = sqlite_db._connect()
    cur = conn.cursor()
    cur.execute(
        "SELECT invitado_por_codigo, invitado_origen FROM aliados WHERE codigo = ?",
        ("60001",),
    )
    row = cur.fetchone()
    conn.close()
    assert row[0] is None or str(row[0]).strip() == ""
    assert row[1] == "organico"


def test_segundo_codigo_no_cambia_padre(sqlite_db):
    sqlite_db.obtener_o_crear_invitador_admin("RUANA-ADMIN")
    _crear_activo(sqlite_db, "70001", "Pedro")
    _crear_activo(sqlite_db, "70002", "Juan")
    _crear_activo(sqlite_db, "70003", "Admin Camp")
    sqlite_db.asignar_invitado_por("70002", "70001", "ampliar_red")
    sqlite_db.crear_campana_invitacion("CAMP2X", "Camp", "28001", 5, "RUANA-ADMIN")
    sqlite_db.consumir_campana_invitacion("CAMP2X", "70002")
    conn = sqlite_db._connect()
    cur = conn.cursor()
    cur.execute("SELECT invitado_por_codigo FROM aliados WHERE codigo = ?", ("70002",))
    padre = cur.fetchone()[0]
    conn.close()
    assert padre == "70001"


def test_nodo_virtual_campana_admin(client, sqlite_db, monkeypatch):
    monkeypatch.setattr(app_module, "get_db", lambda: sqlite_db)
    sqlite_db.obtener_o_crear_invitador_admin("RUANA-ADMIN")
    sqlite_db.crear_campana_invitacion("QR2026", "QR", "28001", 5, "RUANA-ADMIN")
    _crear_activo(sqlite_db, "80001", "Aliado A")
    sqlite_db.consumir_campana_invitacion("QR2026", "80001")
    resp = client.get("/api/admin/referidos/raices", headers=_session_headers("RUANA-ADMIN", "admin"))
    assert resp.status_code == 200
    raices = resp.get_json()["raices"]
    virtual = [r for r in raices if r.get("virtual") and r.get("tipo_nodo") == "campana"]
    assert len(virtual) >= 1


def test_hijos_nodo_campana(client, sqlite_db, monkeypatch):
    monkeypatch.setattr(app_module, "get_db", lambda: sqlite_db)
    sqlite_db.obtener_o_crear_invitador_admin("RUANA-ADMIN")
    sqlite_db.crear_campana_invitacion("EVNT26", "Evento", "28001", 5, "RUANA-ADMIN")
    _crear_activo(sqlite_db, "81001", "Miembro")
    sqlite_db.consumir_campana_invitacion("EVNT26", "81001")
    codigo_nodo = red_arbol_service.codigo_nodo_campana("EVNT26")
    resp = client.get(
        f"/api/admin/referidos/hijos/{codigo_nodo}",
        headers=_session_headers("RUANA-ADMIN", "admin"),
    )
    assert resp.status_code == 200
    assert len(resp.get_json()["hijos"]) == 1


def test_aliado_no_accede_rama_ajena(client, sqlite_db, monkeypatch):
    monkeypatch.setattr(app_module, "get_db", lambda: sqlite_db)
    sqlite_db.obtener_o_crear_invitador_admin("RUANA-ADMIN")
    _crear_activo(sqlite_db, "90001", "Aliado A")
    _crear_activo(sqlite_db, "90002", "Aliado B")
    _crear_activo(sqlite_db, "90003", "Aliado C")
    sqlite_db.asignar_invitado_por("90002", "90001", "ampliar_red")
    resp = client.get(
        "/api/aliado/referidos/hijos/90001",
        headers=_session_headers("90003"),
    )
    assert resp.status_code == 403


def test_eliminado_conserva_linaje_hijos(sqlite_db):
    sqlite_db.obtener_o_crear_invitador_admin("RUANA-ADMIN")
    _crear_activo(sqlite_db, "91001", "Pedro")
    _crear_activo(sqlite_db, "91002", "Juan")
    _crear_activo(sqlite_db, "91003", "Carlos")
    sqlite_db.asignar_invitado_por("91002", "91001", "ampliar_red")
    sqlite_db.asignar_invitado_por("91003", "91002", "ampliar_red")
    sqlite_db.eliminar_perfil_aliado_admin("91002")
    conn = sqlite_db._connect()
    cur = conn.cursor()
    cur.execute("SELECT invitado_por_codigo FROM aliados WHERE codigo = ?", ("91003",))
    padre = cur.fetchone()[0]
    cur.execute("SELECT estado, nombre FROM aliados WHERE codigo = ?", ("91002",))
    estado, nombre = cur.fetchone()
    conn.close()
    assert padre == "91002"
    assert estado == "eliminado"
    assert "Juan" in nombre and "eliminado" in nombre.lower()

    bosques = red_arbol_service.obtener_bosque_arbol_admin_completo(sqlite_db, max_depth=8)
    codigos = set()
    for root in bosques:
        stack = [root]
        while stack:
            n = stack.pop()
            if n.get("codigo"):
                codigos.add(n["codigo"])
            stack.extend(n.get("referidos") or [])
    assert "91002" in codigos


def test_score_hijo_nieto_intacto(sqlite_db):
    sqlite_db.obtener_o_crear_invitador_admin("RUANA-ADMIN")
    _crear_activo(sqlite_db, "92001", "Abuelo")
    _crear_activo(sqlite_db, "92002", "Padre")
    _crear_activo(sqlite_db, "92003", "Nieto")
    sqlite_db.asignar_invitado_por("92002", "92001", "ampliar_red")
    sqlite_db.asignar_invitado_por("92003", "92002", "ampliar_red")
    ancestros = sqlite_db.ancestros_referidos_para_score("92003")
    assert ("92002", 1) in ancestros
    assert ("92001", 2) in ancestros


def test_diagnostico_linaje_endpoint(client, sqlite_db, monkeypatch):
    monkeypatch.setattr(app_module, "get_db", lambda: sqlite_db)
    sqlite_db.obtener_o_crear_invitador_admin("RUANA-ADMIN")
    _crear_activo(sqlite_db, "93001", "Diag")
    resp = client.get(
        "/api/admin/referidos/diagnostico",
        headers=_session_headers("RUANA-ADMIN", "admin"),
    )
    assert resp.status_code == 200
    diag = resp.get_json()["diagnostico"]
    assert diag["total_aliados"] >= 1


def test_detalle_aliado_panel(client, sqlite_db, monkeypatch):
    monkeypatch.setattr(app_module, "get_db", lambda: sqlite_db)
    sqlite_db.obtener_o_crear_invitador_admin("RUANA-ADMIN")
    _crear_activo(sqlite_db, "94001", "Panel")
    resp = client.get(
        "/api/admin/referidos/aliado/94001",
        headers=_session_headers("RUANA-ADMIN", "admin"),
    )
    assert resp.status_code == 200
    aliado = resp.get_json()["aliado"]
    assert aliado["codigo"] == "94001"
    assert "origen_label" in aliado


def test_bosque_completo_incluye_organico_sin_hijos(sqlite_db):
    sqlite_db.obtener_o_crear_invitador_admin("RUANA-ADMIN")
    _crear_activo(sqlite_db, "95001", "Organico Solo")
    referido_service.asignar_origen_sin_padre(sqlite_db, "95001", "organico")
    bosques = red_arbol_service.obtener_bosque_arbol_admin_completo(sqlite_db, max_depth=10)
    codigos = set()
    for root in bosques:
        stack = [root]
        while stack:
            n = stack.pop()
            if n and n.get("codigo"):
                codigos.add(n["codigo"])
            stack.extend(n.get("referidos") or [])
    assert "95001" in codigos


def test_admin_arbol_bosque_completo_endpoint(client, sqlite_db, monkeypatch):
    monkeypatch.setattr(app_module, "get_db", lambda: sqlite_db)
    sqlite_db.obtener_o_crear_invitador_admin("RUANA-ADMIN")
    _crear_activo(sqlite_db, "96001", "Padre")
    _crear_activo(sqlite_db, "96002", "Hijo")
    sqlite_db.asignar_invitado_por("96002", "96001", "ampliar_red")
    resp = client.get(
        "/api/admin/referidos/arbol?profundidad=20",
        headers=_session_headers("RUANA-ADMIN", "admin"),
    )
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["status"] == "success"
    assert data["modo"] == "bosque"
    assert len(data["bosques"]) >= 1
    assert data["total_nodos"] >= 2
