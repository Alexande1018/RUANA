"""Tests de nombres explícitos en la cinta (sin textos genéricos tipo 'Un aliado')."""
from types import SimpleNamespace

import pytest

from core import db_manager as db_module
from core.services import actividad_cinta_service, score_service


@pytest.fixture
def sqlite_db(tmp_path, monkeypatch):
    monkeypatch.setattr(
        db_module,
        "get_settings",
        lambda: SimpleNamespace(postgres_configured=False, database_url=""),
    )
    return db_module.DBManager(str(tmp_path / "ruana_cinta_nombres.db"))


def _setup_grupo(db):
    conn = db._connect()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO grupos (nombre, codigo_postal, estado) VALUES (?, ?, ?)",
        ("G1", "28001", "activo"),
    )
    gid = cur.lastrowid
    for cod, nom in (("A001", "Ana"), ("A002", "Luis")):
        cur.execute(
            """
            INSERT INTO aliados (codigo, nombre, oficio, codigo_postal, grupo_id, estado, score)
            VALUES (?, ?, ?, ?, ?, 'activo', 50)
            """,
            (cod, nom, "Electricidad", "28001", gid),
        )
    conn.commit()
    conn.close()
    return gid


def test_score_grupo_notifica_con_nombre(sqlite_db):
    _setup_grupo(sqlite_db)
    sqlite_db.aplicar_cambio_score("A001", 2, motivo="test_grupo")
    items = actividad_cinta_service.preparar_actividad_cinta(sqlite_db, "A002")
    textos = [it["texto"] for it in items]
    assert "El score de Ana acaba de cambiar" in textos
    assert not any("Un aliado" in t for t in textos)


def test_score_personal_no_aparece_en_cinta_propia(sqlite_db):
    _setup_grupo(sqlite_db)
    sqlite_db.aplicar_cambio_score("A001", 2, motivo="test_propio")
    items = actividad_cinta_service.preparar_actividad_cinta(sqlite_db, "A001")
    assert not any("score" in (it.get("texto") or "").lower() for it in items)


def test_sin_nombre_no_muestra_generico(sqlite_db):
    sqlite_db._crear_notificacion_aliado(
        "X001",
        "recomendacion",
        "T",
        "M",
        metadata={},
    )
    items = actividad_cinta_service.preparar_actividad_cinta(sqlite_db, "X001")
    assert items == []
