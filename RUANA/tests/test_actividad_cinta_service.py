"""
Tests de la cinta de actividad RUANA (notificacion_service.preparar_actividad_cinta).
"""
import json
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


def test_preparar_actividad_cinta_excluye_score_change_personal(sqlite_db):
    codigo = "94002b"
    _insert_notif(
        sqlite_db,
        codigo,
        "score_change",
        "Score",
        "Tu score cambió",
        metadata={"delta": 2, "codigo": codigo},
    )
    assert notificacion_service.preparar_actividad_cinta(sqlite_db, codigo) == []


def test_preparar_actividad_cinta_incluye_score_change_grupo(sqlite_db):
    codigo = "94002b"
    _insert_notif(
        sqlite_db,
        codigo,
        "score_change",
        "Score",
        "Cambio de score en el grupo",
        metadata={"nombre": "Pedro", "codigo": "94099", "movimiento_id": 1},
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



class _CursorContador:
    """Cursor mínimo que cuenta consultas y resuelve nombres."""

    def __init__(self, nombres):
        self.consultas = 0
        self._nombres = nombres

    def execute(self, sql, params=()):
        self.consultas += 1
        self._ultimo = params[0] if params else ""

    def fetchone(self):
        nombre = self._nombres.get(self._ultimo)
        return {"nombre": nombre} if nombre else None


def test_lookup_nombre_reutiliza_la_cache(monkeypatch):
    """Regresión: la cinta hacía una consulta por notificación (~5 s de panel)."""
    from core.services import actividad_cinta_service as servicio

    servicio.limpiar_cache_nombres_cinta()
    cursor = _CursorContador({"A1": "Marta", "A2": "Diego"})

    for _ in range(6):
        assert servicio._lookup_nombre_aliado(cursor, "A1") == "Marta"

    assert cursor.consultas == 1, "el mismo código debe resolverse una sola vez"
    assert servicio._lookup_nombre_aliado(cursor, "A2") == "Diego"
    assert cursor.consultas == 2


def test_lookup_nombre_cachea_tambien_los_fallos(monkeypatch):
    from core.services import actividad_cinta_service as servicio

    servicio.limpiar_cache_nombres_cinta()
    cursor = _CursorContador({})

    for _ in range(4):
        assert servicio._lookup_nombre_aliado(cursor, "NADIE") is None

    assert cursor.consultas == 1


class _CursorPrecarga:
    def __init__(self):
        self.consultas = 0
        self._filas = []

    def execute(self, sql, params=()):
        self.consultas += 1
        self._filas = [{"nombre": "Nombre " + c, "codigo": c} for c in params]

    def fetchall(self):
        return self._filas


def test_precarga_resuelve_todos_los_nombres_en_una_consulta():
    """Regresión: 50 avisos = 50 consultas de nombre."""
    from core.services import actividad_cinta_service as servicio

    servicio.limpiar_cache_nombres_cinta()
    cursor = _CursorPrecarga()
    avisos = [
        {"metadata": json.dumps({"solicitante_codigo": f"A{i}", "profesional_codigo": "P1"})}
        for i in range(20)
    ]

    servicio._precargar_nombres(cursor, avisos)

    assert cursor.consultas == 1
    assert servicio._lookup_nombre_aliado(cursor, "A7") == "Nombre A7"
    assert cursor.consultas == 1, "ya precargado, no debe volver a consultar"
