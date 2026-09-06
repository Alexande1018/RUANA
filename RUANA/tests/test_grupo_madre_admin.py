"""Admin e independización territorial del Grupo Madre."""
from types import SimpleNamespace

import pytest

from core import db_manager as db_module
from core.db_constants import CP_MADUREZ_MIN_ALIADOS, CP_MADUREZ_MIN_ENCARGOS
from core.services import grupo_madre_service


@pytest.fixture
def sqlite_db(tmp_path, monkeypatch):
    monkeypatch.setattr(
        db_module,
        "get_settings",
        lambda: SimpleNamespace(postgres_configured=False, database_url=""),
    )
    return db_module.DBManager(str(tmp_path / "ruana_madre_admin.db"))


def _crear(db, codigo, oficio="Electricidad", cp="03020"):
    r = db.crear_aliado(
        codigo=codigo,
        nombre=f"A {codigo}",
        marca="M",
        oficio=oficio,
        codigo_postal=cp,
        email=f"{codigo}@t.com",
        telefono=f"+34600{codigo}",
        estado="activo",
        score=50,
    )
    assert r["status"] == "success"
    conn = db._connect()
    conn.execute("UPDATE aliados SET estado = 'activo' WHERE codigo = ?", (codigo,))
    conn.commit()
    conn.close()


def test_listar_cp_madurez_admin(sqlite_db):
    _crear(sqlite_db, "72001", cp="03020")
    grupo_madre_service.actualizar_madurez_cp(sqlite_db, "03020")
    cps = grupo_madre_service.listar_cp_madurez_admin(sqlite_db, modo="incubacion")
    assert any(c.get("codigo_postal") == "03020" for c in cps)


def test_listar_grupos_madre_admin(sqlite_db):
    _crear(sqlite_db, "72010", cp="03021")
    grupos = grupo_madre_service.listar_grupos_madre_admin(sqlite_db)
    assert len(grupos) >= 1
    assert any((g.get("tipo") or "madre") == "madre" for g in grupos)


def test_aprobar_independencia_migra_y_limpia_competencia(sqlite_db):
    """Tras aprobar independización, el CP pasa a territorial y se limpian competencias."""
    cp = "03022"
    oficios = ["Electricidad", "Fontanería y fontanería-gas"]
    for i, ofi in enumerate(oficios):
        _crear(sqlite_db, f"721{i:02d}", oficio=ofi, cp=cp)

    grupo_madre_service.actualizar_madurez_cp(sqlite_db, cp)

    conn = sqlite_db._connect()
    cur = conn.cursor()
    cur.execute(
        "UPDATE cp_estado SET aliados_activos = ?, encargos_validos = ?, listo_independizar = 1 WHERE codigo_postal = ?",
        (CP_MADUREZ_MIN_ALIADOS, CP_MADUREZ_MIN_ENCARGOS, cp),
    )
    cur.execute(
        """
        INSERT INTO cp_independencia_solicitudes
        (codigo_postal, ciudad, aliados_activos, encargos_validos, estado)
        VALUES (?, 'Alicante', ?, ?, 'pendiente')
        """,
        (cp, CP_MADUREZ_MIN_ALIADOS, CP_MADUREZ_MIN_ENCARGOS),
    )
    cur.execute(
        """
        INSERT INTO competencia_pendiente (aliado_codigo, grupo_id, oficio, codigo_postal, score_al_crear, estado)
        SELECT codigo, grupo_id, oficio, ?, 10, 'pendiente' FROM aliados WHERE codigo = '72100' LIMIT 1
        """,
        (cp,),
    )
    conn.commit()
    conn.close()

    result = grupo_madre_service.aprobar_independencia_cp(sqlite_db, cp)
    assert result["status"] == "success"
    assert result.get("migrados")

    conn = sqlite_db._connect()
    cur = conn.cursor()
    cur.execute("SELECT modo FROM cp_estado WHERE codigo_postal = ?", (cp,))
    modo = cur.fetchone()[0]
    cur.execute(
        "SELECT COUNT(*) FROM competencia_pendiente WHERE codigo_postal = ? AND estado = 'pendiente'",
        (cp,),
    )
    pend = cur.fetchone()[0]
    conn.close()
    assert modo == "territorial"
    assert pend == 0
