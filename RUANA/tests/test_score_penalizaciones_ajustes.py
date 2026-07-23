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
    return db_module.DBManager(str(tmp_path / "ruana_score_penalizaciones.db"))


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


def test_no_concretado_resta_1_a_cada_uno(sqlite_db):
    _crear_activo(sqlite_db, "95001", "SolNC")
    _crear_activo(sqlite_db, "95002", "ProfNC")
    created = sqlite_db.crear_contacto_ruana("95001", "95002", "Servicio", "Motivo")
    cid = created["id"]
    assert sqlite_db.marcar_cerrado_no_concretado(cid, actor_codigo="95001")["status"] == "success"
    assert _score(sqlite_db, "95001") == 49
    assert _score(sqlite_db, "95002") == 49
    assert (-1, "contacto_cerrado_no_concretado") in _motivos(sqlite_db, "95001")
    assert (-1, "contacto_cerrado_no_concretado") in _motivos(sqlite_db, "95002")


def test_penalizacion_contacto_abierto_7d_y_21d(sqlite_db):
    """Confirma Regla/penalización #6: -2 a 7d y -5 a 21d, una vez cada una."""
    _crear_activo(sqlite_db, "96001", "SolAb")
    _crear_activo(sqlite_db, "96002", "ProfAb")
    created = sqlite_db.crear_contacto_ruana("96001", "96002", "Servicio", "Abierto")
    cid = created["id"]

    hace_8d = (datetime.now() - timedelta(days=8)).strftime("%Y-%m-%d %H:%M:%S")
    conn = sqlite_db._connect()
    cur = conn.cursor()
    cur.execute(
        "UPDATE contactos_ruana SET estado = 'iniciado', creado_en = ?, actualizado_en = ? WHERE id = ?",
        (hace_8d, hace_8d, cid),
    )
    conn.commit()
    conn.close()

    sqlite_db.aplicar_penalizaciones_contactos_abiertos("96001")
    assert (-2, "contacto_sin_cerrar_7d") in _motivos(sqlite_db, "96001")
    assert _score(sqlite_db, "96001") == 48
    # Idempotente: no vuelve a aplicar 7d
    sqlite_db.aplicar_penalizaciones_contactos_abiertos("96001")
    assert sum(1 for _, m in _motivos(sqlite_db, "96001") if m == "contacto_sin_cerrar_7d") == 1

    hace_22d = (datetime.now() - timedelta(days=22)).strftime("%Y-%m-%d %H:%M:%S")
    conn = sqlite_db._connect()
    cur = conn.cursor()
    cur.execute(
        "UPDATE contactos_ruana SET creado_en = ?, actualizado_en = ? WHERE id = ?",
        (hace_22d, hace_22d, cid),
    )
    conn.commit()
    conn.close()

    sqlite_db.aplicar_penalizaciones_contactos_abiertos("96001")
    assert (-5, "contacto_sin_cerrar_21d") in _motivos(sqlite_db, "96001")
    assert _score(sqlite_db, "96001") == 43  # 50 -2 -5
    sqlite_db.aplicar_penalizaciones_contactos_abiertos("96001")
    assert sum(1 for _, m in _motivos(sqlite_db, "96001") if m == "contacto_sin_cerrar_21d") == 1


def test_disputa_ya_no_resta_score_en_registrar_importe(sqlite_db):
    """Solo el solicitante declara; el cierre no aplica -1 de disputa (eliminado)."""
    _crear_activo(sqlite_db, "97001", "SolDisp")
    _crear_activo(sqlite_db, "97002", "ProfDisp")
    created = sqlite_db.crear_contacto_ruana("97001", "97002", "Servicio", "Disp")
    cid = created["id"]
    # Flujo actual: solo solicitante puede declarar → cierra sin disputa
    r = sqlite_db.registrar_importe_contacto(cid, "solicitante", 100.0, usuario="97001")
    assert r["status"] == "success"
    assert not any(m == "declaracion_discrepante" for _, m in _motivos(sqlite_db, "97001"))
    assert not any(m == "declaracion_discrepante" for _, m in _motivos(sqlite_db, "97002"))
