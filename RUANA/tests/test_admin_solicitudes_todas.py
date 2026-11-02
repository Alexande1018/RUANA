"""Admin: todas las solicitudes (semanales + conexión) con detalle completo, solo lectura."""

from __future__ import annotations

import logging
from datetime import date, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest

from core import db_manager as db_module
from core.services import admin_solicitudes_service as svc
from core.services import solicitud_semanal_service, solicitud_service

WEB = Path(__file__).resolve().parents[1] / "web"


@pytest.fixture
def sqlite_db(tmp_path, monkeypatch):
    monkeypatch.setattr(
        db_module,
        "get_settings",
        lambda: SimpleNamespace(postgres_configured=False, database_url=""),
    )
    return db_module.DBManager(str(tmp_path / "ruana_admin_sol_todas.db"))


def _lunes(d: date) -> str:
    return (d - timedelta(days=d.weekday())).isoformat()


def _sql(db, sql, params=()):
    conn = db._connect()
    cur = conn.cursor()
    cur.execute(sql, params)
    rid = cur.lastrowid
    conn.commit()
    conn.close()
    return rid


def _query(db, sql, params=()):
    conn = db._connect()
    cur = conn.cursor()
    cur.execute(sql, params)
    rows = cur.fetchall()
    conn.close()
    return rows


def _escenario(db):
    gid = _sql(
        db,
        "INSERT INTO grupos (nombre, codigo_postal, estado) VALUES (?, ?, ?)",
        ("RUANA-D21ZELQU-RED", "03380", "activo"),
    )
    otro = _sql(
        db,
        "INSERT INTO grupos (nombre, codigo_postal, estado) VALUES (?, ?, ?)",
        ("Grupo Otro", "28100", "activo"),
    )
    for codigo, nombre, oficio, g in (
        ("26053", "Jesus Espinosa", "Carpintería de madera e interior", gid),
        ("MARTA", "Marta", "Electricidad", gid),
        ("LUIS", "Luis", "Fontanería", gid),
        ("ANA", "Ana", "Pintura", otro),
    ):
        _sql(
            db,
            """
            INSERT INTO aliados (codigo, nombre, oficio, codigo_postal, grupo_id, estado, telefono, email)
            VALUES (?, ?, ?, ?, ?, 'activo', ?, ?)
            """,
            (codigo, nombre, oficio, "03380", g, f"+34600{codigo}", f"{codigo}@example.com"),
        )
    texto = (
        "Necesito un electricista para revisar el cuadro de la cocina de un cliente; "
        "salta el diferencial cuando enciende el horno y la vitro a la vez. Urgente esta semana."
    )
    creada = solicitud_semanal_service.crear_solicitud_semanal(db, "26053", "Electricidad", texto, False)
    assert creada["status"] == "success", creada
    sem_id = creada["id"]
    assert solicitud_semanal_service.responder_no_puedo_ayudar(db, sem_id, "LUIS")["status"] == "success"
    assert solicitud_semanal_service.responder_puedo_ayudar(db, sem_id, "MARTA")["status"] == "success"

    # Semanal antigua (otra semana, ya caducada pero aún 'activa' en BD).
    vieja = _lunes(date.today() - timedelta(days=21))
    old_id = _sql(
        db,
        """
        INSERT INTO solicitudes_semanales
            (grupo_id, solicitante_codigo, solicitante_nombre, oficio, descripcion,
             es_oficio_personalizado, semana_inicio, estado, created_at, expira_at)
        VALUES (?, 'ANA', 'Ana', 'Pintura', 'Pintar un piso entero', 0, ?, 'activa', ?, ?)
        """,
        (otro, vieja, vieja + " 10:00:00", vieja),
    )
    # Solicitud de conexión con candidato propuesto.
    con_id = _sql(
        db,
        """
        INSERT INTO solicitudes
            (grupo_id, solicitante_codigo, solicitante_nombre, oficio, descripcion, estado,
             candidato_por_codigo, candidato_por_nombre, candidato_at)
        VALUES (?, '26053', 'Jesus Espinosa', 'Fontanería', 'Fuga en baño de un cliente',
                'candidato_pendiente', 'LUIS', 'Luis', CURRENT_TIMESTAMP)
        """,
        (gid,),
    )
    return SimpleNamespace(gid=gid, otro=otro, sem_id=sem_id, old_id=old_id, con_id=con_id, texto=texto, vieja=vieja)


# ---------------------------------------------------------------- servicio

def test_lista_une_semanales_y_conexion_de_todas_las_semanas(sqlite_db):
    e = _escenario(sqlite_db)
    r = svc.listar_todas(sqlite_db)
    assert r["status"] == "success"
    assert r["total"] == 3
    claves = {(i["tipo"], i["id"]) for i in r["items"]}
    assert claves == {("semanal", e.sem_id), ("semanal", e.old_id), ("conexion", e.con_id)}
    jesus = next(i for i in r["items"] if i["tipo"] == "semanal" and i["id"] == e.sem_id)
    assert jesus["descripcion"] == e.texto  # texto completo, sin recortar
    assert jesus["grupo_nombre"] == "RUANA-D21ZELQU-RED"
    assert jesus["pueden_ayudar_count"] == 1
    assert jesus["no_pueden_count"] == 1
    assert jesus["es_semana_actual"] is True
    assert "candidato_pendiente" in r["filtros_disponibles"]["estados"]
    assert r["avisos"] == []


def test_filtros_tipo_estado_grupo_semana_texto(sqlite_db):
    e = _escenario(sqlite_db)
    assert [i["id"] for i in svc.listar_todas(sqlite_db, tipo="conexion")["items"]] == [e.con_id]
    assert {i["id"] for i in svc.listar_todas(sqlite_db, tipo="semanal")["items"]} == {e.sem_id, e.old_id}
    assert [i["id"] for i in svc.listar_todas(sqlite_db, estado="candidato_pendiente")["items"]] == [e.con_id]
    por_grupo = svc.listar_todas(sqlite_db, grupo=str(e.otro))["items"]
    assert [i["id"] for i in por_grupo] == [e.old_id]
    por_nombre = svc.listar_todas(sqlite_db, grupo="d21zelqu")["items"]
    assert {i["id"] for i in por_nombre} == {e.sem_id, e.con_id}
    # cualquier día de la semana sirve
    semana = svc.listar_todas(sqlite_db, semana=(date.fromisoformat(e.vieja) + timedelta(days=3)).isoformat())
    assert [i["id"] for i in semana["items"]] == [e.old_id]
    assert [i["id"] for i in svc.listar_todas(sqlite_db, q="diferencial")["items"]] == [e.sem_id]
    assert svc.listar_todas(sqlite_db, tipo="otro")["status"] == "error"
    assert svc.listar_todas(sqlite_db, semana="no-fecha")["status"] == "error"


def test_paginacion(sqlite_db):
    _escenario(sqlite_db)
    p1 = svc.listar_todas(sqlite_db, limite=2, offset=0)
    p2 = svc.listar_todas(sqlite_db, limite=2, offset=2)
    assert p1["total"] == p2["total"] == 3
    assert len(p1["items"]) == 2 and len(p2["items"]) == 1
    vistos = {(i["tipo"], i["id"]) for i in p1["items"] + p2["items"]}
    assert len(vistos) == 3
    assert svc.listar_todas(sqlite_db, limite=10_000)["limit"] == svc.LIMITE_MAXIMO


def test_detalle_semanal_con_respuestas_y_candidatos(sqlite_db):
    e = _escenario(sqlite_db)
    d = svc.obtener_detalle(sqlite_db, "semanal", e.sem_id)
    assert d["status"] == "success"
    assert d["solicitud"]["descripcion"] == e.texto
    assert d["solicitud"]["grupo_nombre"] == "RUANA-D21ZELQU-RED"
    assert d["solicitante"]["nombre"] == "Jesus Espinosa"
    tipos = {r["aliado_codigo"]: r["tipo_respuesta"] for r in d["respuestas"]}
    assert tipos == {"LUIS": "no_puedo_ayudar", "MARTA": "puedo_ayudar"}
    assert [c["codigo"] for c in d["candidatos"]] == ["MARTA"]
    assert d["candidatos"][0]["oficio"] == "Electricidad"


def test_detalle_conexion_con_candidato(sqlite_db):
    e = _escenario(sqlite_db)
    d = svc.obtener_detalle(sqlite_db, "conexion", e.con_id)
    assert d["status"] == "success"
    assert d["solicitud"]["descripcion"] == "Fuga en baño de un cliente"
    assert d["solicitud"]["estado"] == "candidato_pendiente"
    assert [(c["origen"], c["codigo"]) for c in d["candidatos"]] == [("candidato", "LUIS")]
    assert d["respuestas"][0]["tipo_respuesta"] == "candidato"


def test_detalle_errores(sqlite_db):
    _escenario(sqlite_db)
    assert svc.obtener_detalle(sqlite_db, "semanal", 99999)["http"] == 404
    assert svc.obtener_detalle(sqlite_db, "xx", 1)["http"] == 400


def test_es_solo_lectura_no_expira_ni_cambia_nada(sqlite_db):
    e = _escenario(sqlite_db)
    tablas = ("solicitudes_semanales", "solicitudes_semanales_respuestas", "solicitudes", "aliados")
    antes = {t: [tuple(r) for r in _query(sqlite_db, f"SELECT * FROM {t} ORDER BY 1")] for t in tablas}
    svc.listar_todas(sqlite_db)
    svc.obtener_detalle(sqlite_db, "semanal", e.old_id)
    svc.obtener_detalle(sqlite_db, "conexion", e.con_id)
    despues = {t: [tuple(r) for r in _query(sqlite_db, f"SELECT * FROM {t} ORDER BY 1")] for t in tablas}
    assert antes == despues
    estado = _query(sqlite_db, "SELECT estado FROM solicitudes_semanales WHERE id = ?", (e.old_id,))[0][0]
    assert estado == "activa"


def test_una_fuente_rota_no_tapa_la_otra(sqlite_db, monkeypatch):
    e = _escenario(sqlite_db)

    def _boom(cursor):
        raise RuntimeError("tabla rota")

    monkeypatch.setattr(svc, "_leer_conexion", _boom)
    r = svc.listar_todas(sqlite_db)
    assert r["status"] == "success"
    assert {i["id"] for i in r["items"]} == {e.sem_id, e.old_id}
    assert r["avisos"] and "conexion" in r["avisos"][0]


def test_listado_antiguo_ya_no_traga_errores_en_silencio(sqlite_db, monkeypatch, caplog):
    _escenario(sqlite_db)
    assert len(solicitud_service.listar_solicitudes_admin_todas(sqlite_db)) == 1  # comportamiento igual

    def _boom(cursor):
        raise RuntimeError("fallo SQL")

    monkeypatch.setattr(solicitud_service._repo, "listar_admin_todas", _boom)
    with caplog.at_level(logging.ERROR):
        assert solicitud_service.listar_solicitudes_admin_todas(sqlite_db) == []
    assert "listar_solicitudes_admin_todas" in caplog.text


# ---------------------------------------------------------------- API

def test_api_requiere_admin_y_devuelve_lista_y_detalle(client, sqlite_db, monkeypatch, session_headers):
    from RUANA.web import app as app_module

    e = _escenario(sqlite_db)
    monkeypatch.setattr(app_module, "get_db", lambda: sqlite_db)

    assert client.get("/api/admin/solicitudes-todas").status_code == 401
    aliado = session_headers("aliado", "26053")
    assert client.get("/api/admin/solicitudes-todas", headers=aliado).status_code == 401
    assert client.get(f"/api/admin/solicitudes-todas/semanal/{e.sem_id}", headers=aliado).status_code == 401

    admin = session_headers("admin", "ADMIN1", permisos=["leer"])
    r = client.get("/api/admin/solicitudes-todas?tipo=semanal&limit=1", headers=admin)
    assert r.status_code == 200
    data = r.get_json()
    assert data["status"] == "success" and data["total"] == 2 and len(data["items"]) == 1

    d = client.get(f"/api/admin/solicitudes-todas/semanal/{e.sem_id}", headers=admin)
    assert d.status_code == 200
    assert d.get_json()["solicitud"]["descripcion"] == e.texto

    assert client.get("/api/admin/solicitudes-todas/semanal/99999", headers=admin).status_code == 404
    assert client.get("/api/admin/solicitudes-todas/otro/1", headers=admin).status_code == 400
    assert client.get("/api/admin/solicitudes-todas?tipo=xx", headers=admin).status_code == 400
    # solo GET
    assert client.post("/api/admin/solicitudes-todas", headers=admin).status_code == 405


# ---------------------------------------------------------------- frontend

def test_frontend_seccion_y_filas_clicables():
    html = (WEB / "admin.html").read_text(encoding="utf-8")
    assert 'id="solicitudes-todas-admin-wrap"' in html
    assert 'id="tbody-solicitudes-todas"' in html
    assert "/static/js/admin-solicitudes-detalle-module.js" in html
    # las secciones existentes siguen ahí
    assert 'id="solicitudes-semanales-admin-wrap"' in html
    assert 'id="solicitudes-admin-wrap"' in html

    mod = (WEB / "static" / "js" / "admin-solicitudes-detalle-module.js").read_text(encoding="utf-8")
    assert "/api/admin/solicitudes-todas" in mod
    assert "data-detalle-tipo" in mod
    assert "method: 'POST'" not in mod  # solo lectura

    sistema = (WEB / "static" / "js" / "admin-sistema-module.js").read_text(encoding="utf-8")
    assert "marcarFilaDetalle(tr, 'semanal', s.id)" in sistema
    assert "marcarFilaDetalle(tr, 'conexion', s.id)" in sistema

    shell = (WEB / "static" / "js" / "admin-shell.js").read_text(encoding="utf-8")
    assert "#solicitudes-todas-admin-wrap" in shell
