"""Cinta de actividad: notificaciones históricas se muestran; no hay métricas de incubación."""
from datetime import datetime
from types import SimpleNamespace

import pytest

from core import db_manager as db_module
from core.services import actividad_cinta_service


@pytest.fixture
def sqlite_db(tmp_path, monkeypatch):
    monkeypatch.setattr(
        db_module,
        "get_settings",
        lambda: SimpleNamespace(postgres_configured=False, database_url=""),
    )
    return db_module.DBManager(str(tmp_path / "ruana_cinta_madre.db"))


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


def test_formateo_cp_independizado_historico_en_cinta(sqlite_db):
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
            "Carlos (Fontanería) se ha unido a la red en 03001",
        ),
        (
            "proximidad_solicitud",
            {"oficio": "Fontanería", "solicitante_codigo": "60003"},
            "busca un profesional de Fontanería",
        ),
    ],
)
def test_formateo_notificaciones_historicas(sqlite_db, tipo, meta, fragmento):
    _crear(sqlite_db, "60010", cp="03001")
    _insert_notif(sqlite_db, "60010", tipo, meta)
    items = actividad_cinta_service.preparar_actividad_cinta(sqlite_db, "60010")
    assert any(fragmento in t for t in _textos(items)), f"tipo={tipo} textos={_textos(items)}"


def test_cinta_territorial_no_emite_metricas_incubacion(sqlite_db):
    _crear(sqlite_db, "60101", cp="03001")
    conn = sqlite_db._connect()
    cur = conn.cursor()
    cur.execute(
        """
        INSERT OR REPLACE INTO cp_estado
        (codigo_postal, ciudad, modo, aliados_activos, encargos_validos, listo_independizar)
        VALUES ('03001', 'Alicante', 'incubacion', 2, 0, 0)
        """
    )
    conn.commit()
    conn.close()
    items = actividad_cinta_service.preparar_actividad_cinta(sqlite_db, "60101")
    textos = " ".join(_textos(items)).lower()
    assert "incubación" not in textos
    assert "independencia territorial" not in textos
    assert not hasattr(actividad_cinta_service, "emitir_hitos_madurez_cp")
    assert not hasattr(actividad_cinta_service, "notificar_aliado_nuevo_en_madre")
