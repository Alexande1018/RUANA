"""Redes provinciales (24 nov 2026): una por prefijo de CP, sin tocar Red Centro."""
from types import SimpleNamespace

import pytest

from core import db_manager as db_module
from core.services import red_regional_service as rr


def test_cubre_todas_las_provincias_salvo_centro():
    prefijos = sorted(p for cfg in rr.REDES.values() for p in cfg.prefijos_cp)
    esperados = sorted(f"{i:02d}" for i in range(1, 53) if i not in (28, 45))
    assert prefijos == esperados


@pytest.mark.parametrize("cp,slug", [
    ("41003", "red_sevilla"), ("46009", "red_valencia"), ("08001", "red_barcelona"),
    ("29130", "red_malaga"), ("50014", "red_zaragoza"), ("03380", "red_alicante"),
    ("19160", "red_guadalajara"), ("22260", "red_huesca"),
])
def test_redes_para_cp(cp, slug):
    assert [c.slug for c in rr.redes_para_cp(cp)] == [slug]


@pytest.mark.parametrize("cp", ["28012", "45500", "460003", "", None, "4100"])
def test_cp_de_centro_o_mal_escrito_sin_red(cp):
    assert rr.redes_para_cp(cp) == []


def test_flag_provincial_encendido_por_defecto_y_apagable(monkeypatch):
    sev = rr.red_por_slug("red_sevilla")
    monkeypatch.delenv("RED_SEVILLA_ENABLED", raising=False)
    assert rr.piloto_habilitado(sev) is True
    monkeypatch.setenv("RED_SEVILLA_ENABLED", "0")
    assert rr.piloto_habilitado(sev) is False
    monkeypatch.delenv("RED_HUESCA_ENABLED", raising=False)
    assert rr.piloto_habilitado(rr.RED_HUESCA) is False


@pytest.fixture
def sqlite_db(tmp_path, monkeypatch):
    monkeypatch.setattr(
        db_module, "get_settings",
        lambda: SimpleNamespace(postgres_configured=False, database_url=""),
    )
    return db_module.DBManager(str(tmp_path / "ruana_prov.db"))


def test_activar_sevilla_no_crea_nada_hasta_activar_y_revertir(sqlite_db):
    sev = rr.red_por_slug("red_sevilla")
    st = rr.estado(sqlite_db, sev)
    assert st["operativa"] is False and st["miembros"] == []
    r = rr.activar(sqlite_db, "ADMIN", sev)
    assert r["status"] == "success"
    assert rr.estado(sqlite_db, sev)["operativa"] is True
    rv = rr.revertir(sqlite_db, "ADMIN", sev)
    assert rv["status"] == "success"
    assert rr.estado(sqlite_db, sev)["operativa"] is False
