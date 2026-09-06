"""
Tests cinta de actividad para Grupo Madre (incubación territorial).
"""
from datetime import datetime
from types import SimpleNamespace

import pytest

from core import db_manager as db_module
from core.db_constants import TIPO_GRUPO_MADRE
from core.services import actividad_cinta_service, grupo_madre_service


@pytest.fixture
def sqlite_db(tmp_path, monkeypatch):
    monkeypatch.setattr(
        db_module,
        "get_settings",
        lambda: SimpleNamespace(postgres_configured=False, database_url=""),
    )
    return db_module.DBManager(str(tmp_path / "ruana_cinta_madre.db"))


def _ahora():
    return datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")


def _crear(db, codigo, oficio="Electricidad", cp="03001", nombre=None):
    r = db.crear_aliado(
        codigo=codigo,
        nombre=nombre or f"Aliado {codigo}",
        marca="Marca",
        oficio=oficio,
        codigo_postal=cp,
        email=f"{codigo}@example.com",
        telefono=f"+34600{codigo}",
        estado="activo",
        score=50,
    )
    assert r.get("status") == "success"
    conn = db._connect()
    conn.execute("UPDATE aliados SET estado = 'activo' WHERE codigo = ?", (codigo,))
    conn.commit()
    conn.close()
    return r


def _textos(items):
    return [it["texto"] for it in items]


def _insert_notif(db, codigo, tipo, metadata=None):
    db._crear_notificacion_aliado(codigo, tipo, "T", "M", metadata=metadata or {})


def test_formateo_cp_independizado_en_cinta(sqlite_db):
    _crear(sqlite_db, "60001", cp="03001")
    _insert_notif(
        sqlite_db,
        "60001",
        "cp_independizado",
        {"codigo_postal": "03001"},
    )
    items = actividad_cinta_service.preparar_actividad_cinta(sqlite_db, "60001")
    assert any(
        "03001" in t and "Grupo RUANA territorial" in t for t in _textos(items)
    )


@pytest.mark.parametrize(
    "tipo,meta,fragmento",
    [
        (
            "madurez_encargo_progreso",
            {"codigo_postal": "03001", "encargos": 2, "encargos_requeridos": 3},
            "acumula 2 de 3 encargos válidos",
        ),
        (
            "madurez_aliado_progreso",
            {"codigo_postal": "03001", "aliados": 5, "aliados_requeridos": 10},
            "suma 5 de 10 aliados activos",
        ),
        (
            "madurez_listo_independizar",
            {"codigo_postal": "03001"},
            "cumple los requisitos para independizarse",
        ),
        (
            "aliado_nuevo_cercano",
            {
                "nombre": "Carlos",
                "codigo": "60002",
                "oficio": "Fontanería",
                "codigo_postal": "03001",
            },
            "Carlos (Fontanería) se ha unido a la red de incubación en 03001",
        ),
    ],
)
def test_formateo_notificaciones_madurez(sqlite_db, tipo, meta, fragmento):
    _crear(sqlite_db, "60010", cp="03001")
    _insert_notif(sqlite_db, "60010", tipo, meta)
    items = actividad_cinta_service.preparar_actividad_cinta(sqlite_db, "60010")
    assert any(fragmento in t for t in _textos(items)), f"tipo={tipo} textos={_textos(items)}"


def test_metricas_incubacion_en_grupo_madre(sqlite_db):
    _crear(sqlite_db, "60101", cp="03001")
    _crear(sqlite_db, "60102", oficio="Fontanería y fontanería-gas", cp="03001")
    grupo_madre_service.actualizar_madurez_cp(sqlite_db, "03001")
    items = actividad_cinta_service.preparar_actividad_cinta(sqlite_db, "60101")
    textos = _textos(items)
    assert any("red de incubación" in t.lower() for t in textos)
    assert any("aliados activos hacia la independencia" in t for t in textos)


def test_aliado_nuevo_mismo_cp_genera_notificacion_cercana(sqlite_db):
    _crear(sqlite_db, "60201", cp="03001", nombre="Primero")
    _crear(sqlite_db, "60202", oficio="Fontanería y fontanería-gas", cp="03001", nombre="Segundo")
    items = actividad_cinta_service.preparar_actividad_cinta(sqlite_db, "60201")
    assert any(
        "Segundo" in t and "red de incubación" in t for t in _textos(items)
    )


def test_emitir_hitos_madurez_cp_notifica_mismo_cp(sqlite_db):
    _crear(sqlite_db, "60301", cp="03002")
    aliado = sqlite_db.obtener_aliado_por_codigo("60301")
    grupo_id = aliado["grupo_id"]
    assert sqlite_db.obtener_grupo_por_id(grupo_id).get("tipo") == TIPO_GRUPO_MADRE

    actividad_cinta_service.emitir_hitos_madurez_cp(
        sqlite_db,
        "03002",
        int(grupo_id),
        prev_aliados=0,
        prev_encargos=0,
        prev_listo=False,
        n_aliados=1,
        n_encargos=0,
        listo=False,
    )

    conn = sqlite_db._connect()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT tipo FROM notificaciones_aliado
        WHERE aliado_codigo = ? AND tipo = 'madurez_aliado_progreso'
        """,
        ("60301",),
    )
    tipos = {r[0] for r in cur.fetchall()}
    conn.close()
    assert "madurez_aliado_progreso" in tipos


def test_contexto_aliado_grupo_madre_resuelve_cp_real(sqlite_db):
    import sqlite3

    _crear(sqlite_db, "60401", cp="03003")
    conn = sqlite_db._connect()
    conn.row_factory = sqlite3.Row
    from core.repositories.actividad_repo import ActividadRepo

    cur = conn.cursor()
    ctx = ActividadRepo().contexto_aliado(cur, "60401")
    conn.close()
    assert ctx is not None
    assert ctx.get("grupo_tipo") == TIPO_GRUPO_MADRE
    assert ctx.get("codigo_postal") == "03003"
    assert ctx.get("codigo_postal") != "__MADRE__"
