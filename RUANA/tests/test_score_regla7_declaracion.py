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
    return db_module.DBManager(str(tmp_path / "ruana_score_regla7.db"))


def _crear_activo(db, codigo, nombre, score=50):
    result = db.crear_aliado(
        codigo=codigo,
        nombre=nombre,
        marca="Marca",
        oficio="Fontanería",
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


def test_regla7_mas2_si_declara_antes_de_24h(sqlite_db):
    _crear_activo(sqlite_db, "90001", "SolicitanteR7")
    _crear_activo(sqlite_db, "90002", "ProfesionalR7")
    created = sqlite_db.crear_contacto_ruana(
        "90001", "90002", "Reparación", "Fuga en cocina"
    )
    cid = created["id"]

    result = sqlite_db.registrar_importe_contacto(
        contacto_id=cid,
        parte="solicitante",
        importe=120.0,
        usuario="90001",
    )
    assert result["status"] == "success"
    assert _score(sqlite_db, "90001") == 52
    assert (2, f"regla7_declaracion_24h_{cid}") in _motivos(sqlite_db, "90001")
    assert _score(sqlite_db, "90002") == 50
    assert not any(m.startswith("regla7_") for _, m in _motivos(sqlite_db, "90002"))


def test_regla7_no_aplica_si_pasa_24h(sqlite_db):
    _crear_activo(sqlite_db, "91001", "SolicitanteR7b")
    _crear_activo(sqlite_db, "91002", "ProfesionalR7b")
    created = sqlite_db.crear_contacto_ruana(
        "91001", "91002", "Reparación", "Desatasco"
    )
    cid = created["id"]
    hace_25h = (datetime.now() - timedelta(hours=25)).strftime("%Y-%m-%d %H:%M:%S")

    conn = sqlite_db._connect()
    cur = conn.cursor()
    cur.execute(
        "UPDATE contactos_ruana SET creado_en = ? WHERE id = ?",
        (hace_25h, cid),
    )
    conn.commit()
    conn.close()

    result = sqlite_db.registrar_importe_contacto(
        contacto_id=cid,
        parte="solicitante",
        importe=90.0,
        usuario="91001",
    )
    assert result["status"] == "success"
    assert sqlite_db.evaluar_regla7_declaracion_24h(cid) is None
    assert _score(sqlite_db, "91001") == 50
    assert not any(m.startswith("regla7_") for _, m in _motivos(sqlite_db, "91001"))


def test_regla7_idempotente(sqlite_db):
    _crear_activo(sqlite_db, "92001", "SolicitanteR7c")
    _crear_activo(sqlite_db, "92002", "ProfesionalR7c")
    created = sqlite_db.crear_contacto_ruana(
        "92001", "92002", "Reparación", "Cambio grifo"
    )
    cid = created["id"]

    assert sqlite_db.registrar_importe_contacto(
        contacto_id=cid, parte="solicitante", importe=50.0, usuario="92001"
    )["status"] == "success"
    assert sum(1 for _, m in _motivos(sqlite_db, "92001") if m.startswith("regla7_")) == 1
    assert _score(sqlite_db, "92001") == 52

    # Segunda evaluación: idempotente (no vuelve a proponer el hito)
    assert sqlite_db.evaluar_regla7_declaracion_24h(cid) is None


def test_regla7_limite_exacto_24h_no_aplica(sqlite_db):
    _crear_activo(sqlite_db, "93001", "SolicitanteR7d")
    _crear_activo(sqlite_db, "93002", "ProfesionalR7d")
    created = sqlite_db.crear_contacto_ruana(
        "93001", "93002", "Reparación", "Revisión"
    )
    cid = created["id"]
    inicio = datetime.now() - timedelta(hours=24)
    inicio_s = inicio.strftime("%Y-%m-%d %H:%M:%S")
    declaracion = inicio + timedelta(hours=24)

    conn = sqlite_db._connect()
    cur = conn.cursor()
    cur.execute(
        """
        UPDATE contactos_ruana
        SET creado_en = ?,
            importe_solicitante = 70,
            declarado_por_solicitante = '93001',
            fecha_declaracion_solicitante = ?
        WHERE id = ?
        """,
        (inicio_s, declaracion.strftime("%Y-%m-%d %H:%M:%S"), cid),
    )
    conn.commit()
    conn.close()

    assert sqlite_db.evaluar_regla7_declaracion_24h(cid) is None
