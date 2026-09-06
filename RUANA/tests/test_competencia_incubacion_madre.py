"""Competencia en incubación (Grupo Madre): CP efectivo, retador mismo CP y cierre."""
from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest

from core import db_manager as db_module
from core.db_constants import TIPO_GRUPO_MADRE


@pytest.fixture
def sqlite_db(tmp_path, monkeypatch):
    monkeypatch.setattr(
        db_module,
        "get_settings",
        lambda: SimpleNamespace(postgres_configured=False, database_url=""),
    )
    return db_module.DBManager(str(tmp_path / "ruana_comp_madre.db"))


def _activo(db, codigo, oficio, cp, score=50, estado="activo", grupo_id=None):
    r = db.crear_aliado(
        codigo=codigo,
        nombre=f"Aliado {codigo}",
        marca="M",
        oficio=oficio,
        codigo_postal=cp,
        email=f"{codigo}@t.com",
        telefono=f"+346000{codigo[-4:]}",
        estado=estado,
        score=score,
    )
    assert r.get("status") == "success", r
    conn = db._connect()
    cur = conn.cursor()
    cur.execute("UPDATE aliados SET estado = ? WHERE codigo = ?", (estado, codigo))
    if grupo_id is not None:
        cur.execute("UPDATE aliados SET grupo_id = ? WHERE codigo = ?", (grupo_id, codigo))
    conn.commit()
    conn.close()


def _madre_grupo_id(db, codigo):
    a = db.obtener_aliado_por_codigo(codigo)
    gid = a.get("grupo_id")
    g = db.obtener_grupo_por_id(gid)
    if (g or {}).get("tipo") != TIPO_GRUPO_MADRE:
        from core.services import grupo_madre_service
        madre = grupo_madre_service.obtener_o_crear_grupo_madre(db, "Alicante", "Alicante")
        conn = db._connect()
        cur = conn.cursor()
        cur.execute("UPDATE aliados SET grupo_id = ? WHERE codigo = ?", (madre["id"], codigo))
        conn.commit()
        conn.close()
        gid = madre["id"]
    assert db.obtener_grupo_por_id(gid).get("tipo") == TIPO_GRUPO_MADRE
    return gid


def test_buscar_retador_madre_prioriza_en_espera_mismo_cp(sqlite_db):
    _activo(sqlite_db, "71001", "Electricidad", "03010", score=10)
    gid = _madre_grupo_id(sqlite_db, "71001")
    _activo(sqlite_db, "71002", "Electricidad", "03010", score=50, estado="en_espera")

    retador = sqlite_db._buscar_retador("71001", gid, "Electricidad", 10, "03010")
    assert retador is not None
    assert retador["codigo"] == "71002"


def test_iniciar_competencia_madre_usa_cp_aliado_y_avisa_grupo(sqlite_db):
    _activo(sqlite_db, "71011", "Electricidad", "03011", score=12)
    gid = _madre_grupo_id(sqlite_db, "71011")
    _activo(sqlite_db, "71012", "Electricidad", "03011", score=60, estado="en_espera")

    result = sqlite_db._iniciar_competencia_si_procede("71011")
    assert result is not None

    conn = sqlite_db._connect()
    cur = conn.cursor()
    cur.execute(
        "SELECT codigo_postal FROM competencia_pendiente WHERE aliado_codigo = '71011'"
    )
    assert cur.fetchone() is None
    avisos = sqlite_db.obtener_avisos_grupo(gid, tipo="competencia")
    conn.close()
    assert avisos
    assert "Electricidad" in avisos[0]["texto"]


def test_finalizar_competencia_madre_perdedor_pasa_a_en_espera(sqlite_db):
    _activo(sqlite_db, "71021", "Electricidad", "03012", score=5)
    gid = _madre_grupo_id(sqlite_db, "71021")
    _activo(sqlite_db, "71022", "Electricidad", "03012", score=70, estado="en_espera")

    sqlite_db._iniciar_competencia_si_procede("71021")
    conn = sqlite_db._connect()
    cur = conn.cursor()
    cur.execute("SELECT id FROM competencia WHERE aliado_original_codigo = '71021'")
    cid = cur.fetchone()[0]
    cur.execute("UPDATE aliados SET score = 5 WHERE codigo = '71021'")
    cur.execute("UPDATE aliados SET score = 90 WHERE codigo = '71022'")
    cur.execute(
        "UPDATE competencia SET fecha_fin_prevista = ? WHERE id = ?",
        ((datetime.now() - timedelta(hours=1)).strftime("%Y-%m-%d %H:%M:%S"), cid),
    )
    conn.commit()
    conn.close()

    sqlite_db.finalizar_competencia_activas_vencidas()
    perdedor = sqlite_db.obtener_aliado_por_codigo("71021")
    assert perdedor["estado"] == "en_espera"
    assert perdedor["score"] == 50
    assert perdedor.get("grupo_id") is None


def test_competencia_pendiente_guarda_cp_real_no_sentinel(sqlite_db):
    _activo(sqlite_db, "71031", "Electricidad", "03013", score=8)
    sqlite_db._registrar_competencia_pendiente("71031")

    conn = sqlite_db._connect()
    cur = conn.cursor()
    cur.execute(
        "SELECT codigo_postal FROM competencia_pendiente WHERE aliado_codigo = '71031'"
    )
    row = cur.fetchone()
    conn.close()
    assert row is not None
    assert row[0] == "03013"
    assert row[0] != "__MADRE__"
