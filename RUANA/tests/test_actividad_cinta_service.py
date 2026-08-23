"""
Tests de la cinta de actividad RUANA (notificacion_service.preparar_actividad_cinta).
"""
from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest

from core import db_manager as db_module
from core.services import notificacion_service


@pytest.fixture
def sqlite_db(tmp_path, monkeypatch):
    monkeypatch.setattr(
        db_module,
        "get_settings",
        lambda: SimpleNamespace(postgres_configured=False, database_url=""),
    )
    return db_module.DBManager(str(tmp_path / "ruana_actividad_cinta.db"))


def _insert_notif(db, codigo, tipo, titulo, mensaje, metadata=None, creado_en=None):
    db._crear_notificacion_aliado(codigo, tipo, titulo, mensaje, metadata=metadata or {})
    if creado_en is None:
        return
    conn = db._connect()
    cur = conn.cursor()
    cur.execute(
        """
        UPDATE notificaciones_aliado
        SET creado_en = ?
        WHERE id = (SELECT MAX(id) FROM notificaciones_aliado WHERE aliado_codigo = ?)
        """,
        (creado_en, codigo),
    )
    conn.commit()
    conn.close()


def test_preparar_actividad_cinta_vacio(sqlite_db):
    assert notificacion_service.preparar_actividad_cinta(sqlite_db, "") == []
    assert notificacion_service.preparar_actividad_cinta(sqlite_db, "94001") == []


def test_preparar_actividad_cinta_excluye_tipos_operativos(sqlite_db):
    codigo = "94002"
    _insert_notif(sqlite_db, codigo, "apoyo_ruana", "Apoyo", "Paga el apoyo")
    _insert_notif(sqlite_db, codigo, "pago_rechazado", "Rechazado", "Comprobante rechazado")
    _insert_notif(sqlite_db, codigo, "ruana_soporte", "Soporte", "Ticket abierto")
    assert notificacion_service.preparar_actividad_cinta(sqlite_db, codigo) == []


def test_preparar_actividad_cinta_incluye_score_change(sqlite_db):
    codigo = "94002b"
    _insert_notif(
        sqlite_db,
        codigo,
        "score_change",
        "Score",
        "Cambio de score",
        metadata={"nombre": "Pedro"},
    )
    items = notificacion_service.preparar_actividad_cinta(sqlite_db, codigo)
    assert len(items) == 1
    assert items[0]["texto"] == "El score de Pedro acaba de cambiar"


def test_preparar_actividad_cinta_formatea_solicitud_semanal(sqlite_db):
    codigo = "94003"
    _insert_notif(
        sqlite_db,
        codigo,
        "solicitud_semanal_nueva",
        "Solicitud de esta semana",
        "Esta semana Ana necesita un Fontanero.",
        metadata={"solicitante_nombre": "Ana", "oficio": "Fontanero"},
    )
    items = notificacion_service.preparar_actividad_cinta(sqlite_db, codigo)
    assert len(items) == 1
    assert items[0]["texto"] == "Nueva solicitud publicada por Ana en el grupo"
    assert items[0]["fuente"] == "notificacion"


def test_preparar_actividad_cinta_incluye_avisos_grupo(sqlite_db):
    codigo = "94004"
    avisos = [
        {
            "id": 1,
            "tipo": "competencia",
            "texto": "El profesional de Electricidad está en competencia en este código postal.",
            "creado_en": "2026-08-23 10:00:00",
        }
    ]
    items = notificacion_service.preparar_actividad_cinta(sqlite_db, codigo, avisos_grupo=avisos)
    assert len(items) == 1
    assert items[0]["texto"] == "Nueva competencia iniciada en tu grupo"
    assert items[0]["fuente"] == "aviso_grupo"


def test_preparar_actividad_cinta_orden_mas_reciente_primero(sqlite_db):
    codigo = "94005"
    base = datetime(2026, 8, 23, 12, 0, 0)
    _insert_notif(
        sqlite_db,
        codigo,
        "solicitud_semanal_nueva",
        "A",
        "msg",
        metadata={"solicitante_nombre": "Antigua"},
        creado_en=(base - timedelta(hours=2)).strftime("%Y-%m-%d %H:%M:%S"),
    )
    _insert_notif(
        sqlite_db,
        codigo,
        "solicitud_asignada",
        "B",
        "msg",
        metadata={"solicitud_id": 99},
        creado_en=base.strftime("%Y-%m-%d %H:%M:%S"),
    )
    items = notificacion_service.preparar_actividad_cinta(sqlite_db, codigo)
    assert len(items) == 2
    assert items[0]["texto"] == "Una solicitud acaba de ser asignada"
    assert items[1]["texto"] == "Nueva solicitud publicada por Antigua en el grupo"


def test_preparar_actividad_cinta_maximo_diez(sqlite_db):
    codigo = "94006"
    base = datetime(2026, 8, 23, 8, 0, 0)
    for i in range(11):
        _insert_notif(
            sqlite_db,
            codigo,
            "solicitud_nueva",
            f"T{i}",
            "msg",
            metadata={"solicitante_nombre": f"Aliado{i}", "solicitud_id": i},
            creado_en=(base + timedelta(minutes=i)).strftime("%Y-%m-%d %H:%M:%S"),
        )
    items = notificacion_service.preparar_actividad_cinta(sqlite_db, codigo)
    assert len(items) == 10
    assert items[0]["texto"] == "Aliado10 ha publicado una nueva solicitud"
    assert items[-1]["texto"] == "Aliado1 ha publicado una nueva solicitud"
    assert not any("Aliado0 ha publicado" in x["texto"] for x in items)


def test_preparar_actividad_cinta_nunca_mas_de_diez_con_limite(sqlite_db):
    codigo = "94007"
    for i in range(5):
        _insert_notif(
            sqlite_db,
            codigo,
            "solicitud_nueva",
            f"T{i}",
            "msg",
            metadata={"solicitante_nombre": f"O{i}", "solicitud_id": i},
        )
    items = notificacion_service.preparar_actividad_cinta(sqlite_db, codigo, limite=3)
    assert len(items) == 3


def test_preparar_actividad_cinta_constante_max(sqlite_db):
    assert notificacion_service.MAX_ACTIVIDAD_CINTA == 10


def test_preparar_actividad_cinta_para_aliado_con_aviso_grupo(sqlite_db):
    codigo = "94008"
    items = notificacion_service.preparar_actividad_cinta_para_aliado(sqlite_db, codigo)
    assert items == []

