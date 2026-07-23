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
    return db_module.DBManager(str(tmp_path / "ruana_score_regla8.db"))


def _crear_activo(db, codigo, nombre, score=50):
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


def _dias_acceso(db, codigo):
    conn = db._connect()
    cur = conn.cursor()
    cur.execute(
        "SELECT dia FROM aliado_accesos_dia WHERE codigo_aliado = ? ORDER BY dia",
        (codigo,),
    )
    rows = [r[0] for r in cur.fetchall()]
    conn.close()
    return rows


def test_regla8_mas3_tras_7_dias_consecutivos(sqlite_db):
    _crear_activo(sqlite_db, "94001", "AliadoR8a")
    fin = datetime(2026, 7, 22)
    for i in range(6):
        dia = (fin - timedelta(days=6 - i)).strftime("%Y-%m-%d")
        r = sqlite_db.registrar_acceso_login("94001", dia=dia)
        assert r["status"] == "success"
        assert r["regla8_aplicada"] is False

    assert _score(sqlite_db, "94001") == 50
    dia_fin = fin.strftime("%Y-%m-%d")
    r = sqlite_db.registrar_acceso_login("94001", dia=dia_fin)
    assert r["status"] == "success"
    assert r["regla8_aplicada"] is True
    assert r["motivo"] == f"regla8_racha_7dias_{dia_fin}"
    assert _score(sqlite_db, "94001") == 53
    assert (3, f"regla8_racha_7dias_{dia_fin}") in _motivos(sqlite_db, "94001")


def test_regla8_no_aplica_si_falta_un_dia(sqlite_db):
    _crear_activo(sqlite_db, "94101", "AliadoR8b")
    fin = datetime(2026, 7, 22)
    # Días 0,1,2,4,5,6 (falta el 3)
    for i in (0, 1, 2, 4, 5, 6):
        dia = (fin - timedelta(days=6 - i)).strftime("%Y-%m-%d")
        sqlite_db.registrar_acceso_login("94101", dia=dia)
    assert sqlite_db.evaluar_regla8_racha_7dias("94101", dia_fin=fin.strftime("%Y-%m-%d")) is None
    assert _score(sqlite_db, "94101") == 50
    assert not any(m.startswith("regla8_") for _, m in _motivos(sqlite_db, "94101"))


def test_regla8_no_premia_cada_dia_tras_la_racha(sqlite_db):
    _crear_activo(sqlite_db, "94201", "AliadoR8c")
    inicio = datetime(2026, 7, 1)
    for i in range(7):
        sqlite_db.registrar_acceso_login(
            "94201", dia=(inicio + timedelta(days=i)).strftime("%Y-%m-%d")
        )
    assert _score(sqlite_db, "94201") == 53

    # Día 8 de racha continua: no debe sumar otro +3
    dia8 = (inicio + timedelta(days=7)).strftime("%Y-%m-%d")
    r = sqlite_db.registrar_acceso_login("94201", dia=dia8)
    assert r["regla8_aplicada"] is False
    assert _score(sqlite_db, "94201") == 53
    assert sum(1 for _, m in _motivos(sqlite_db, "94201") if m.startswith("regla8_")) == 1


def test_regla8_repetible_tras_otra_semana(sqlite_db):
    _crear_activo(sqlite_db, "94301", "AliadoR8d")
    inicio = datetime(2026, 7, 1)
    for i in range(14):
        sqlite_db.registrar_acceso_login(
            "94301", dia=(inicio + timedelta(days=i)).strftime("%Y-%m-%d")
        )
    motivos_r8 = [m for _, m in _motivos(sqlite_db, "94301") if m.startswith("regla8_")]
    assert len(motivos_r8) == 2
    assert motivos_r8[0] == "regla8_racha_7dias_2026-07-07"
    assert motivos_r8[1] == "regla8_racha_7dias_2026-07-14"
    assert _score(sqlite_db, "94301") == 56


def test_regla8_mismo_dia_una_sola_fila(sqlite_db):
    _crear_activo(sqlite_db, "94401", "AliadoR8e")
    dia = "2026-07-10"
    assert sqlite_db.registrar_acceso_login("94401", dia=dia)["status"] == "success"
    assert sqlite_db.registrar_acceso_login("94401", dia=dia)["status"] == "success"
    assert _dias_acceso(sqlite_db, "94401") == [dia]
    assert _score(sqlite_db, "94401") == 50
