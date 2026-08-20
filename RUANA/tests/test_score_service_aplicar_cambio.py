"""
Tests del núcleo Score extraído (service + repo) vía fachada DBManager
y llamadas directas al service.
"""
from types import SimpleNamespace

import pytest

from core import db_manager as db_module
from core.repositories.score_repo import ScoreRepo
from core.services import score_service


@pytest.fixture
def sqlite_db(tmp_path, monkeypatch):
    monkeypatch.setattr(
        db_module,
        "get_settings",
        lambda: SimpleNamespace(postgres_configured=False, database_url=""),
    )
    return db_module.DBManager(str(tmp_path / "ruana_score_service.db"))


def _crear_activo(db, codigo, nombre="AliadoScore", score=50):
    result = db.crear_aliado(
        codigo=codigo,
        nombre=nombre,
        marca="Marca",
        oficio="Electricidad",
        codigo_postal="28001",
        email=f"{codigo}@example.com",
        telefono=f"+34600{codigo[-5:]}",
        estado="activo",
        score=score,
        especializacion="Averías",
    )
    assert result["status"] == "success"
    return result


def _score(db, codigo):
    return int(db.obtener_aliado_por_codigo(codigo)["score"])


def _motivos(db, codigo):
    conn = db._connect()
    cur = conn.cursor()
    cur.execute(
        "SELECT delta, motivo FROM score_movimientos WHERE codigo_aliado = ? ORDER BY id",
        (codigo,),
    )
    rows = cur.fetchall()
    conn.close()
    return [(int(r[0]), r[1]) for r in rows]


def test_andamiaje_imports():
    import core.services  # noqa: F401
    import core.repositories  # noqa: F401
    import web.blueprints  # noqa: F401


def test_calcular_delta_aplicar_tope_diario():
    assert score_service.calcular_delta_aplicar(5, 0) == 5
    assert score_service.calcular_delta_aplicar(8, 5) == 5
    assert score_service.calcular_delta_aplicar(3, 10) == 0
    assert score_service.calcular_delta_aplicar(-5, 0) == -5
    assert score_service.calcular_delta_aplicar(-8, -5) == -5
    assert score_service.calcular_delta_aplicar(-3, -10) == 0


def test_calcular_score_nuevo_clamp():
    assert score_service.calcular_score_nuevo(498, 5) == (500, 2)
    assert score_service.calcular_score_nuevo(2, -5) == (0, -2)
    assert score_service.calcular_score_nuevo(50, 3) == (53, 3)


def test_fachada_aplicar_cambio_score_basico(sqlite_db):
    _crear_activo(sqlite_db, "81001", score=50)
    r = sqlite_db.aplicar_cambio_score("81001", 3, motivo="test_nucleo")
    assert r["status"] == "success"
    assert r["aplicado"] == 3
    assert r["score_final"] == 53
    assert _score(sqlite_db, "81001") == 53
    assert (3, "test_nucleo") in _motivos(sqlite_db, "81001")


def test_fachada_delta_cero_y_aliado_inexistente(sqlite_db):
    _crear_activo(sqlite_db, "81002", score=40)
    r0 = sqlite_db.aplicar_cambio_score("81002", 0, motivo="noop")
    assert r0 == {"status": "success", "aplicado": 0, "score_final": None}

    r_err = sqlite_db.aplicar_cambio_score("NOEXISTE", 2, motivo="x")
    assert r_err["status"] == "error"
    assert "NOEXISTE" in r_err["message"]


def test_fachada_tope_diario_y_clamp(sqlite_db):
    _crear_activo(sqlite_db, "81003", score=495)
    assert sqlite_db.aplicar_cambio_score("81003", 10, motivo="a")["aplicado"] == 5
    assert _score(sqlite_db, "81003") == 500
    # Ya en tope de día (+5 aplicado; pedir más no aplica)
    r2 = sqlite_db.aplicar_cambio_score("81003", 5, motivo="b")
    assert r2["status"] == "success"
    assert r2["aplicado"] == 0
    assert r2["score_final"] == 500


def test_service_directo_en_cursor(sqlite_db):
    _crear_activo(sqlite_db, "81004", score=20)
    conn = sqlite_db._connect()
    cur = conn.cursor()
    result = score_service.aplicar_cambio_score(
        cur,
        codigo_aliado="81004",
        delta=-4,
        motivo="service_directo",
        repo=ScoreRepo(),
    )
    conn.commit()
    conn.close()
    assert result["status"] == "success"
    assert result["aplicado"] == -4
    assert result["score_final"] == 16
    assert result["score_anterior"] == 20
    assert _score(sqlite_db, "81004") == 16
    assert (-4, "service_directo") in _motivos(sqlite_db, "81004")


def test_notificacion_score_change(sqlite_db):
    _crear_activo(sqlite_db, "81005", score=30)
    assert sqlite_db.aplicar_cambio_score("81005", 2, motivo="notif_test")["aplicado"] == 2
    conn = sqlite_db._connect()
    cur = conn.cursor()
    cur.execute(
        "SELECT tipo, titulo FROM notificaciones_aliado WHERE aliado_codigo = ?",
        ("81005",),
    )
    rows = cur.fetchall()
    conn.close()
    assert any(r[0] == "score_change" for r in rows)


def test_score_repo_existe_movimiento_y_motivos_prefijo(sqlite_db):
    _crear_activo(sqlite_db, "81006", score=40)
    assert sqlite_db.aplicar_cambio_score("81006", 2, motivo="regla8_racha_7dias_2026-08-10")["aplicado"] == 2
    assert sqlite_db.aplicar_cambio_score("81006", 1, motivo="otro_motivo")["aplicado"] == 1

    repo = ScoreRepo()
    conn = sqlite_db._connect()
    cur = conn.cursor()
    assert repo.existe_movimiento_motivo(cur, "81006", "regla8_racha_7dias_2026-08-10") is True
    assert repo.existe_movimiento_motivo(cur, "81006", "no_existe") is False
    motivos = repo.listar_motivos_score_con_prefijo(cur, "81006", "regla8_racha_7dias_")
    conn.close()
    assert "regla8_racha_7dias_2026-08-10" in motivos
    assert "otro_motivo" not in motivos


def test_score_repo_penalizacion_aplicada(sqlite_db):
    _crear_activo(sqlite_db, "81007", score=50)
    _crear_activo(sqlite_db, "81008", score=50)
    creado = sqlite_db.crear_contacto_ruana("81007", "81008", "Electricidad", "Avería")
    assert creado["status"] == "success"
    cid = int(creado["id"])

    repo = ScoreRepo()
    conn = sqlite_db._connect()
    cur = conn.cursor()
    assert repo.existe_penalizacion_aplicada(cur, cid, "chat_48h") is False
    repo.insertar_penalizacion_aplicada(cur, cid, "chat_48h")
    conn.commit()
    assert repo.existe_penalizacion_aplicada(cur, cid, "chat_48h") is True
    # Idempotente
    repo.insertar_penalizacion_aplicada(cur, cid, "chat_48h")
    conn.commit()
    assert repo.existe_penalizacion_aplicada(cur, cid, "7d") is False
    conn.close()


def test_score_repo_listar_dias_acceso(sqlite_db):
    _crear_activo(sqlite_db, "81009", score=50)
    conn = sqlite_db._connect()
    cur = conn.cursor()
    for dia in ("2026-08-08", "2026-08-09", "2026-08-11"):
        cur.execute(
            "INSERT OR IGNORE INTO aliado_accesos_dia (codigo_aliado, dia) VALUES (?, ?)",
            ("81009", dia),
        )
    conn.commit()

    repo = ScoreRepo()
    presentes = repo.listar_dias_acceso(
        cur, "81009", dias=["2026-08-08", "2026-08-09", "2026-08-10"]
    )
    assert set(presentes) == {"2026-08-08", "2026-08-09"}
    desde = repo.listar_dias_acceso(cur, "81009", desde_dia="2026-08-09")
    conn.close()
    assert desde == ["2026-08-09", "2026-08-11"]


@pytest.mark.parametrize(
    "score,esperado",
    [
        (500, "ÉLITE"),
        (350, "ÉLITE"),
        (349, "DESTACADO"),
        (200, "DESTACADO"),
        (199, "ESTABLE"),
        (50, "ESTABLE"),
        (49, "EN RIESGO"),
        (15, "EN RIESGO"),
        (14, "COMPETENCIA"),
        (0, "COMPETENCIA"),
        (None, "COMPETENCIA"),
        ("abc", "COMPETENCIA"),
    ],
)
def test_score_a_estado_bandas_oficiales(score, esperado):
    """Motor RUANA: ÉLITE 350-500, DESTACADO 200-349, ESTABLE 50-199, EN RIESGO 15-49, COMPETENCIA 0-14."""
    assert score_service.score_a_estado(score) == esperado
    from core.db_manager import DBManager

    assert DBManager.score_a_estado(score) == esperado


def test_ya_aplicado_motivo_score_via_repo(sqlite_db):
    _crear_activo(sqlite_db, "81010", score=45)
    assert sqlite_db._ya_aplicado_motivo_score("81010", "motivo_unico_x") is False
    assert sqlite_db.aplicar_cambio_score("81010", 1, motivo="motivo_unico_x")["aplicado"] == 1
    assert sqlite_db._ya_aplicado_motivo_score("81010", "motivo_unico_x") is True
    assert sqlite_db._ya_aplicado_motivo_score("81010", "") is True
    assert sqlite_db._ya_aplicado_motivo_score("", "x") is True
