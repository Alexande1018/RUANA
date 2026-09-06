"""
Tests auto-split de grupos por CP: bootstrap madre + acumulación de 10 elegibles.
"""
from types import SimpleNamespace

import pytest

from core import db_manager as db_module
from core.db_constants import TIPO_GRUPO_TERRITORIAL
from core.services import grupo_madre_service


@pytest.fixture
def sqlite_db(tmp_path, monkeypatch):
    monkeypatch.setattr(
        db_module,
        "get_settings",
        lambda: SimpleNamespace(postgres_configured=False, database_url=""),
    )
    return db_module.DBManager(str(tmp_path / "ruana_auto_split.db"))


OFICIOS = [
    "Electricidad",
    "Fontanería y fontanería-gas",
    "Albañilería y obra",
    "Carpintería de madera e interior",
    "Pintura y decoración",
    "Cerrajería",
    "Climatización y calefacción",
    "Jardinería y mantenimiento exterior",
    "Limpieza y acabados",
    "Cristalería y espejos",
    "Manitas / Reparaciones generales",
]


def _crear(db, codigo, oficio="Electricidad", cp="03001", estado="activo"):
    return db.crear_aliado(
        codigo=codigo,
        nombre=f"Aliado {codigo}",
        marca="Marca",
        oficio=oficio,
        codigo_postal=cp,
        email=f"{codigo}@example.com",
        telefono=f"+34600{codigo}",
        estado=estado,
        score=50,
    )


def _set_activo(db, codigo):
    conn = db._connect()
    conn.execute("UPDATE aliados SET estado = 'activo' WHERE codigo = ?", (codigo,))
    conn.commit()
    conn.close()


def _grupo_tipo(db, grupo_id):
    g = db.obtener_grupo_por_id(grupo_id)
    return (g or {}).get("tipo")


def test_bootstrap_madre_crea_primer_grupo_territorial(sqlite_db):
    """CP sin grupo → Grupo Madre crea primer grupo territorial (no tipo madre)."""
    r = _crear(sqlite_db, "60001", cp="03001")
    assert r["status"] == "success"
    _set_activo(sqlite_db, "60001")
    aliado = sqlite_db.obtener_aliado_por_codigo("60001")
    assert aliado.get("grupo_id") is not None
    assert _grupo_tipo(sqlite_db, aliado["grupo_id"]) == TIPO_GRUPO_TERRITORIAL
    assert grupo_madre_service.cp_en_modo_territorial(sqlite_db, "03001") is True


def test_segundo_mismo_oficio_va_a_espera(sqlite_db):
    """Con grupo existente, mismo oficio sin plaza → en_espera (no nuevo grupo)."""
    r1 = _crear(sqlite_db, "60002", oficio="Electricidad", cp="03002")
    assert r1["status"] == "success"
    _set_activo(sqlite_db, "60002")

    r2 = _crear(sqlite_db, "60003", oficio="Electricidad", cp="03002")
    assert r2["status"] == "success"
    aliado2 = sqlite_db.obtener_aliado_por_codigo("60003")
    assert aliado2["estado"] == "en_espera"
    assert grupo_madre_service.contar_grupos_territoriales_activos_por_cp(sqlite_db, "03002") == 1


def test_acumulacion_10_elegibles_crea_segundo_grupo(sqlite_db):
    """Tras 10 elegibles nuevos desde el último grupo → se crea Grupo CP #2."""
    cp = "03004"
    # 1 bootstrap + 10 nuevos elegibles
    for i, oficio in enumerate(OFICIOS[:11]):
        codigo = f"61{i:03d}"
        r = _crear(sqlite_db, codigo, oficio=oficio, cp=cp)
        assert r["status"] == "success"
        _set_activo(sqlite_db, codigo)

    assert grupo_madre_service.contar_grupos_territoriales_activos_por_cp(sqlite_db, cp) == 2

    r12 = _crear(sqlite_db, "61011", oficio="Electricidad", cp=cp)
    assert r12["status"] == "success"
    _set_activo(sqlite_db, "61011")
    aliado12 = sqlite_db.obtener_aliado_por_codigo("61011")
    assert aliado12.get("grupo_id") is not None
    g1 = sqlite_db.obtener_aliado_por_codigo("61000").get("grupo_id")
    g12 = aliado12.get("grupo_id")
    assert g1 != g12
