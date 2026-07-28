"""Tests reglas de competencia: umbral 15, retador CP/en_espera, notificaciones y derrotas."""
from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest

from core import db_manager as db_module


@pytest.fixture
def sqlite_db(tmp_path, monkeypatch):
    monkeypatch.setattr(
        db_module,
        "get_settings",
        lambda: SimpleNamespace(postgres_configured=False, database_url=""),
    )
    return db_module.DBManager(str(tmp_path / "ruana_competencia.db"))


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


def _notifs(db, codigo):
    return db.listar_notificaciones_aliado(codigo, limite=20)


def test_umbral_competencia_es_15(sqlite_db):
    assert sqlite_db._get_umbral_competencia() == 15
    assert sqlite_db._get_score_reinicio_competencia() == 50


def test_buscar_retador_prioriza_en_espera(sqlite_db):
    g1 = sqlite_db.crear_grupo_en_cp("28055")
    g2 = sqlite_db.crear_grupo_en_cp("28055")
    _activo(sqlite_db, "50001", "Electricidad", "28055", score=10, grupo_id=g1["id"])
    _activo(sqlite_db, "50002", "Electricidad", "28055", score=80, grupo_id=g2["id"])
    _activo(sqlite_db, "50003", "Electricidad", "28055", score=50, estado="en_espera")

    retador = sqlite_db._buscar_retador("50001", g1["id"], "Electricidad", 10, "28055")
    assert retador is not None
    assert retador["codigo"] == "50003"


def test_iniciar_competencia_notifica_retador_y_avisos_cp(sqlite_db):
    g1 = sqlite_db.crear_grupo_en_cp("28066")
    g2 = sqlite_db.crear_grupo_en_cp("28066")
    _activo(sqlite_db, "50011", "Fontanería", "28066", score=12, grupo_id=g1["id"])
    _activo(sqlite_db, "50012", "Fontanería", "28066", score=70, grupo_id=g2["id"])

    result = sqlite_db._iniciar_competencia_si_procede("50011")
    assert result is not None

    notifs = _notifs(sqlite_db, "50012")
    assert any(n.get("tipo") == "competencia_inicio" for n in notifs)
    assert any("30 días" in (n.get("mensaje") or "") for n in notifs)

    avisos_g1 = sqlite_db.obtener_avisos_grupo(g1["id"], tipo="competencia")
    avisos_g2 = sqlite_db.obtener_avisos_grupo(g2["id"], tipo="competencia")
    assert avisos_g1
    assert avisos_g2
    assert "Fontanería" in avisos_g1[0]["texto"]


def test_iniciar_competencia_activa_suplente_en_espera(sqlite_db):
    g1 = sqlite_db.crear_grupo_en_cp("28077")
    _activo(sqlite_db, "50021", "Carpintería", "28077", score=8, grupo_id=g1["id"])
    _activo(sqlite_db, "50022", "Carpintería", "28077", score=50, estado="en_espera")

    result = sqlite_db._iniciar_competencia_si_procede("50021")
    assert result is not None

    aliado = sqlite_db.obtener_aliado_por_codigo("50022")
    assert aliado["estado"] == "activo"
    assert aliado["grupo_id"] == g1["id"]


def test_finalizar_competencia_perdedor_score_50_y_grupo_formacion(sqlite_db):
    g1 = sqlite_db.crear_grupo_en_cp("28088")
    g2 = sqlite_db.crear_grupo_en_cp("28088")
    sqlite_db.crear_grupo_en_cp("28088")  # tercer grupo vacío en el CP
    _activo(sqlite_db, "50031", "Pintura", "28088", score=5, grupo_id=g1["id"])
    _activo(sqlite_db, "50032", "Pintura", "28088", score=60, grupo_id=g2["id"])
    sqlite_db._iniciar_competencia_si_procede("50031")

    conn = sqlite_db._connect()
    cur = conn.cursor()
    cur.execute("SELECT id FROM competencia WHERE aliado_original_codigo = '50031'")
    cid = cur.fetchone()[0]
    cur.execute("UPDATE aliados SET score = 5 WHERE codigo = '50031'")
    cur.execute("UPDATE aliados SET score = 80 WHERE codigo = '50032'")
    cur.execute(
        "UPDATE competencia SET fecha_fin_prevista = ? WHERE id = ?",
        ((datetime.now() - timedelta(hours=1)).strftime("%Y-%m-%d %H:%M:%S"), cid),
    )
    conn.commit()
    conn.close()

    sqlite_db.finalizar_competencia_activas_vencidas()
    titular = sqlite_db.obtener_aliado_por_codigo("50031")
    assert titular["score"] == 50
    assert titular["derrotas_competencia"] == 1
    assert titular["estado"] == "activo"
    # Grupo con menos profesionales y plaza libre (g2 quedó vacío al mover retador a g1)
    assert titular["grupo_id"] == g2["id"]

    notifs = _notifs(sqlite_db, "50031")
    assert any(n.get("tipo") == "competencia_derrota" for n in notifs)


def test_segunda_derrota_expulsa_y_notifica(sqlite_db):
    g1 = sqlite_db.crear_grupo_en_cp("28099")
    g2 = sqlite_db.crear_grupo_en_cp("28099")
    _activo(sqlite_db, "50041", "Albañilería", "28099", score=5, grupo_id=g1["id"])
    _activo(sqlite_db, "50042", "Albañilería", "28099", score=70, grupo_id=g2["id"])

    conn = sqlite_db._connect()
    cur = conn.cursor()
    cur.execute("UPDATE aliados SET derrotas_competencia = 1 WHERE codigo = '50041'")
    conn.commit()
    conn.close()

    sqlite_db._iniciar_competencia_si_procede("50041")
    conn = sqlite_db._connect()
    cur = conn.cursor()
    cur.execute("SELECT id FROM competencia WHERE aliado_original_codigo = '50041'")
    cid = cur.fetchone()[0]
    cur.execute("UPDATE aliados SET score = 5 WHERE codigo = '50041'")
    cur.execute("UPDATE aliados SET score = 90 WHERE codigo = '50042'")
    cur.execute(
        "UPDATE competencia SET fecha_fin_prevista = ? WHERE id = ?",
        ((datetime.now() - timedelta(hours=1)).strftime("%Y-%m-%d %H:%M:%S"), cid),
    )
    conn.commit()
    conn.close()

    sqlite_db.finalizar_competencia_activas_vencidas()
    titular = sqlite_db.obtener_aliado_por_codigo("50041")
    assert titular["estado"] == "expulsado"
    assert titular["derrotas_competencia"] == 2

    notifs = _notifs(sqlite_db, "50041")
    assert any(n.get("tipo") == "competencia_expulsion" for n in notifs)
    assert any("código de invitación nuevo" in (n.get("mensaje") or "") for n in notifs)


def test_aplicar_cambio_score_dispara_competencia_al_cruzar_15(sqlite_db):
    g1 = sqlite_db.crear_grupo_en_cp("28100")
    g2 = sqlite_db.crear_grupo_en_cp("28100")
    _activo(sqlite_db, "50051", "Electricidad", "28100", score=20, grupo_id=g1["id"])
    _activo(sqlite_db, "50052", "Electricidad", "28100", score=55, grupo_id=g2["id"])

    r = sqlite_db.aplicar_cambio_score("50051", -6, "test cruce umbral")
    assert r["score_final"] == 14

    conn = sqlite_db._connect()
    cur = conn.cursor()
    cur.execute(
        "SELECT 1 FROM competencia WHERE aliado_original_codigo = '50051' AND estado = 'activa'"
    )
    assert cur.fetchone() is not None
    conn.close()
