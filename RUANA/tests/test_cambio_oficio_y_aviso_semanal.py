"""Cambio de oficio con plaza ocupada y texto del aviso de solicitud semanal."""

from datetime import date
from types import SimpleNamespace

import pytest

from core import db_manager as db_module
from core.services import solicitud_semanal_service
from core.services.solicitud_semanal_service import MENSAJE_SOLICITUD_SEMANA_USADA


OFICIO_A = "Electricidad"
OFICIO_B = "Fontanería y fontanería-gas"
OFICIO_C = "Pintura y decoración"
OFICIO_D = "Carpintería de madera e interior"
MENSAJE_PLAZA = (
    "En tu grupo ya hay un {oficio} titular. "
    "Si quieres, te apuntamos a la lista de espera de ese oficio en tu zona."
)


@pytest.fixture
def sqlite_db(tmp_path, monkeypatch):
    monkeypatch.setattr(
        db_module,
        "get_settings",
        lambda: SimpleNamespace(postgres_configured=False, database_url=""),
    )
    return db_module.DBManager(str(tmp_path / "ruana_oficio_aviso.db"))


def _crear(db, codigo, oficio, cp="28041"):
    return db.crear_aliado(
        codigo=codigo,
        nombre=f"Aliado {codigo}",
        marca="Marca",
        oficio=oficio,
        codigo_postal=cp,
        email=f"{codigo}@example.com",
        telefono=f"+34610{codigo}",
        estado="activo",
        score=50,
    )


def _oficio(db, codigo):
    aliado = db.obtener_aliado_por_codigo(codigo)
    return (aliado or {}).get("oficio")


def _grupo(db, codigo):
    aliado = db.obtener_aliado_por_codigo(codigo)
    return (aliado or {}).get("grupo_id")


def test_cambio_a_oficio_ocupado_se_rechaza(sqlite_db):
    alta_a = _crear(sqlite_db, "41001", OFICIO_A)
    alta_b = _crear(sqlite_db, "41002", OFICIO_B)
    assert alta_a["status"] == "success"
    assert alta_b["status"] == "success"
    assert _grupo(sqlite_db, "41001") == _grupo(sqlite_db, "41002")

    resultado = sqlite_db.actualizar_aliado("41002", oficio=OFICIO_A)

    assert resultado["status"] == "error"
    assert resultado["message"] == MENSAJE_PLAZA.format(oficio=OFICIO_A)
    assert _oficio(sqlite_db, "41002") == OFICIO_B
    assert _oficio(sqlite_db, "41001") == OFICIO_A


def test_cambio_a_oficio_libre_se_acepta(sqlite_db):
    _crear(sqlite_db, "41011", OFICIO_A)
    _crear(sqlite_db, "41012", OFICIO_B)

    resultado = sqlite_db.actualizar_aliado("41012", oficio=OFICIO_C)

    assert resultado["status"] == "success"
    assert _oficio(sqlite_db, "41012") == OFICIO_C
    assert _oficio(sqlite_db, "41011") == OFICIO_A


def test_sin_cambio_de_oficio_no_bloquea_ni_en_competencia(sqlite_db):
    """Dos activos del mismo oficio (competencia) no impiden guardar el oficio propio."""
    _crear(sqlite_db, "41021", OFICIO_A)
    _crear(sqlite_db, "41022", OFICIO_B)
    grupo_id = _grupo(sqlite_db, "41021")
    assert grupo_id == _grupo(sqlite_db, "41022")

    conn = sqlite_db._connect()
    conn.execute(
        "UPDATE aliados SET oficio = ?, estado = 'activo' WHERE codigo = ?",
        (OFICIO_A, "41022"),
    )
    conn.commit()
    conn.close()

    mismo = sqlite_db.actualizar_aliado("41021", nombre="Titular plaza", oficio=OFICIO_A)
    assert mismo["status"] == "success"
    aliado = sqlite_db.obtener_aliado_por_codigo("41021")
    assert aliado["nombre"] == "Titular plaza"
    assert aliado["oficio"] == OFICIO_A
    assert aliado["estado"] == "activo"
    assert sqlite_db.obtener_aliado_por_codigo("41022")["estado"] == "activo"
    assert sqlite_db.obtener_aliado_por_codigo("41022")["oficio"] == OFICIO_A

    solo_nombre = sqlite_db.actualizar_aliado("41022", nombre="Retador plaza")
    assert solo_nombre["status"] == "success"
    assert sqlite_db.obtener_aliado_por_codigo("41022")["oficio"] == OFICIO_A

    _crear(sqlite_db, "41023", OFICIO_C)
    assert _grupo(sqlite_db, "41023") == grupo_id
    bloqueado = sqlite_db.actualizar_aliado("41023", oficio=OFICIO_A)
    assert bloqueado["status"] == "error"
    assert bloqueado["message"] == MENSAJE_PLAZA.format(oficio=OFICIO_A)
    assert _oficio(sqlite_db, "41023") == OFICIO_C

    libre = sqlite_db.actualizar_aliado("41023", oficio=OFICIO_D)
    assert libre["status"] == "success"
    assert _oficio(sqlite_db, "41023") == OFICIO_D


def test_oficio_fuera_de_catalogo_no_sustituye_la_plaza(sqlite_db):
    _crear(sqlite_db, "41031", OFICIO_A)
    resultado = sqlite_db.actualizar_aliado("41031", oficio="Oficio inventado")
    assert resultado["status"] == "error"
    assert "catálogo" in resultado["message"]
    assert _oficio(sqlite_db, "41031") == OFICIO_A


def _grupo_semanal(db):
    conn = db._connect()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO grupos (nombre, codigo_postal, estado) VALUES (?, ?, ?)",
        ("Grupo aviso", "03041", "activo"),
    )
    grupo_id = cursor.lastrowid
    cursor.execute(
        """
        INSERT INTO aliados (codigo, nombre, oficio, codigo_postal, grupo_id, estado)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        ("42001", "Nuria", OFICIO_A, "03041", grupo_id, "activo"),
    )
    conn.commit()
    conn.close()
    return grupo_id


def test_aviso_semanal_si_la_primera_ya_no_esta_activa(sqlite_db):
    _grupo_semanal(sqlite_db)
    primera = solicitud_semanal_service.crear_solicitud_semanal(
        sqlite_db, "42001", OFICIO_B, "Primera", False
    )
    assert primera["status"] == "success"

    conn = sqlite_db._connect()
    conn.execute(
        "UPDATE solicitudes_semanales SET estado = 'expirada' WHERE id = ?",
        (primera["id"],),
    )
    conn.commit()
    conn.close()

    segunda = solicitud_semanal_service.crear_solicitud_semanal(
        sqlite_db, "42001", OFICIO_C, "Segunda", False
    )
    assert segunda["status"] == "error"
    assert segunda["message"] == MENSAJE_SOLICITUD_SEMANA_USADA
    assert "activa" not in segunda["message"].lower()
    assert "lunes" in segunda["message"]

    conn = sqlite_db._connect()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT COUNT(*) FROM solicitudes_semanales WHERE solicitante_codigo = ?",
        ("42001",),
    )
    assert cursor.fetchone()[0] == 1
    conn.close()


def test_solicitud_activa_de_la_semana_sigue_siendo_la_misma(sqlite_db):
    _grupo_semanal(sqlite_db)
    primera = solicitud_semanal_service.crear_solicitud_semanal(
        sqlite_db, "42001", OFICIO_B, "Primera", False
    )
    segunda = solicitud_semanal_service.crear_solicitud_semanal(
        sqlite_db, "42001", OFICIO_C, "Segunda", False
    )
    assert segunda["status"] == "success"
    assert segunda.get("already_existed") is True
    assert segunda["id"] == primera["id"]


def test_semana_de_solicitud_empieza_en_lunes():
    viernes = date(2026, 9, 25)
    lunes = solicitud_semanal_service._semana_inicio_lunes(viernes)
    assert lunes == date(2026, 9, 21)
    assert lunes.weekday() == 0
    assert "lunes" in MENSAJE_SOLICITUD_SEMANA_USADA
