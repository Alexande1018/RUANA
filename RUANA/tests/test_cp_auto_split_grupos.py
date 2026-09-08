"""
Tests auto-split de grupos por CP: bootstrap madre + acumulación de 10 elegibles.
"""
from types import SimpleNamespace

import pytest

from core import db_manager as db_module
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


def test_bootstrap_madre_asigna_al_grupo_madre(sqlite_db):
    """CP sin grupo territorial → el aliado entra en el Grupo Madre (tipo madre)."""
    r = _crear(sqlite_db, "60001", cp="03001")
    assert r["status"] == "success"
    _set_activo(sqlite_db, "60001")
    aliado = sqlite_db.obtener_aliado_por_codigo("60001")
    assert aliado.get("grupo_id") is not None
    assert _grupo_tipo(sqlite_db, aliado["grupo_id"]) == "madre"
    assert grupo_madre_service.cp_en_modo_territorial(sqlite_db, "03001") is False


def test_segundo_mismo_oficio_va_a_espera(sqlite_db):
    """Con grupo existente, mismo oficio sin plaza → en_espera (no nuevo grupo)."""
    r1 = _crear(sqlite_db, "60002", oficio="Electricidad", cp="03002")
    assert r1["status"] == "success"
    _set_activo(sqlite_db, "60002")

    r2 = _crear(sqlite_db, "60003", oficio="Electricidad", cp="03002")
    assert r2["status"] == "success"
    aliado2 = sqlite_db.obtener_aliado_por_codigo("60003")
    assert aliado2["estado"] == "en_espera"
    assert grupo_madre_service.contar_grupos_territoriales_activos_por_cp(sqlite_db, "03002") == 0


def test_incubacion_no_crea_grupos_territoriales_por_acumulacion(sqlite_db):
    """En incubación, 11 oficios del mismo CP siguen en un único Grupo Madre."""
    cp = "03004"
    ids = []
    for i, oficio in enumerate(OFICIOS[:11]):
        codigo = f"61{i:03d}"
        r = _crear(sqlite_db, codigo, oficio=oficio, cp=cp)
        assert r["status"] == "success"
        _set_activo(sqlite_db, codigo)
        ids.append(sqlite_db.obtener_aliado_por_codigo(codigo).get("grupo_id"))

    assert grupo_madre_service.contar_grupos_territoriales_activos_por_cp(sqlite_db, cp) == 0
    assert len(set(ids)) == 1
    assert _grupo_tipo(sqlite_db, ids[0]) == "madre"


def test_acumulacion_10_elegibles_crea_segundo_grupo_si_ya_territorial(sqlite_db):
    """Si el CP ya es territorial, 10 elegibles nuevos abren el grupo #2."""
    cp = "03004"
    creado = sqlite_db.crear_grupo_en_cp(cp, "Alicante", "Alicante")
    assert isinstance(creado, dict) and creado.get("id")

    for i, oficio in enumerate(OFICIOS[:10]):
        codigo = f"62{i:03d}"
        r = _crear(sqlite_db, codigo, oficio=oficio, cp=cp)
        assert r["status"] == "success"
        _set_activo(sqlite_db, codigo)

    assert grupo_madre_service.contar_grupos_territoriales_activos_por_cp(sqlite_db, cp) == 2
