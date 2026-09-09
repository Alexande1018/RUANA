"""Dry-run e inserción controlada de datos QA para madurez territorial."""
import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest

from core import db_manager as db_module
from core.db_constants import CP_MADUREZ_MIN_ALIADOS, CP_MADUREZ_MIN_ENCARGOS
from core.qa_madurez_territorial import (
    CONFIRM_TOKEN,
    CP_OBJETIVO_DEFAULT,
    ENV_APPLY,
    PREFIX,
    aplicar_plan,
    calcular_plan,
    dry_run,
    inspeccionar_cp,
)
from core.services import grupo_madre_service

OFICIOS_REALES = [
    "Electricidad",
    "Fontanería y fontanería-gas",
    "Pintura y decoración",
    "Carpintería de madera e interior",
    "Cerrajería",
]


@pytest.fixture
def sqlite_db(tmp_path, monkeypatch):
    monkeypatch.setattr(
        db_module,
        "get_settings",
        lambda: SimpleNamespace(postgres_configured=False, database_url=""),
    )
    monkeypatch.delenv(ENV_APPLY, raising=False)
    monkeypatch.delenv("RUANA_QA_MADUREZ_ALLOW_PRODUCTION", raising=False)
    return db_module.DBManager(str(tmp_path / "ruana_qa_madurez.db"))


def _crear(db, codigo, oficio, cp=CP_OBJETIVO_DEFAULT, nombre=None, marca="Marca real"):
    r = db.crear_aliado(
        codigo=codigo,
        nombre=nombre or f"Aliado real {codigo}",
        marca=marca,
        oficio=oficio,
        codigo_postal=cp,
        email=f"real-{codigo}@example.com",
        telefono=f"+34600{codigo}",
        estado="activo",
    )
    assert r["status"] == "success", r
    conn = db._connect()
    conn.execute("UPDATE aliados SET estado = 'activo' WHERE codigo = ?", (codigo,))
    conn.commit()
    conn.close()
    return r


def _estado_observado_produccion(db):
    """Replica el estado observado: 5 aliados activos y 1 encargo válido."""
    reales = []
    for i, oficio in enumerate(OFICIOS_REALES):
        codigo = f"8100{i + 1}"
        _crear(db, codigo, oficio)
        reales.append(codigo)
    creado = db.crear_contacto_ruana(
        reales[0], reales[1], servicio="Avería real", motivo_contacto="Encargo existente"
    )
    assert creado["status"] == "success"
    aceptado = db.aceptar_contacto_ruana(creado["id"], reales[1])
    assert aceptado["status"] == "success"
    return reales, creado["id"]


def test_dry_run_estado_observado_calcula_5_aliados_y_2_encargos(sqlite_db):
    reales, encargo_id = _estado_observado_produccion(sqlite_db)
    payload = dry_run(sqlite_db, CP_OBJETIVO_DEFAULT)
    estado = payload["estado_actual"]
    plan = payload["plan"]

    assert payload["insercion"] is False
    assert payload["regla_real"]["min_aliados_activos"] == CP_MADUREZ_MIN_ALIADOS
    assert payload["regla_real"]["min_encargos_aceptados"] == CP_MADUREZ_MIN_ENCARGOS
    assert estado["aliados_activos"] == 5
    assert estado["aliados_faltan"] == 5
    assert estado["encargos_validos"] == 1
    assert estado["encargos_faltan"] == 2
    assert set(estado["oficios_ocupados"]) == set(OFICIOS_REALES)
    assert len(plan["aliados_a_crear"]) == 5
    assert len(plan["encargos_a_crear"]) == 2
    oficios_nuevos = [a["oficio"] for a in plan["aliados_a_crear"]]
    assert len(oficios_nuevos) == len(set(oficios_nuevos))
    assert set(oficios_nuevos).isdisjoint(OFICIOS_REALES)
    for aliado in plan["aliados_a_crear"]:
        assert aliado["marca"] == PREFIX
        assert PREFIX in aliado["nombre"]
        assert aliado["email"].endswith("@ruana.invalid")
        assert aliado["codigo_postal"] == CP_OBJETIVO_DEFAULT
    codigos_qa = {a["codigo_propuesto"] for a in plan["aliados_a_crear"]}
    for enc in plan["encargos_a_crear"]:
        assert enc["solicitante_codigo"] in codigos_qa
        assert enc["profesional_codigo"] in codigos_qa
        assert enc["solicitante_codigo"] != enc["profesional_codigo"]
        assert enc["estado_objetivo"] == "aceptado"
        assert PREFIX in enc["motivo_contacto"]
    assert encargo_id in {e["id"] for e in estado["encargos"]}
    assert {a["codigo"] for a in estado["aliados"]} == set(reales)
    assert "DRY-RUN" in payload["reporte"]
    assert "BLOQUEADA" in payload["reporte"]


def test_dry_run_no_inserta(sqlite_db):
    _estado_observado_produccion(sqlite_db)
    before = inspeccionar_cp(sqlite_db)
    dry_run(sqlite_db)
    after = inspeccionar_cp(sqlite_db)
    assert after.n_aliados_activos == before.n_aliados_activos == 5
    assert after.n_encargos_validos == before.n_encargos_validos == 1
    assert [a.codigo for a in after.aliados_activos] == [a.codigo for a in before.aliados_activos]


def test_apply_sin_autorizacion_no_escribe(sqlite_db):
    _estado_observado_produccion(sqlite_db)
    resultado = aplicar_plan(sqlite_db, confirm_token=CONFIRM_TOKEN)
    assert resultado["status"] == "blocked"
    assert resultado["insercion"] is False
    assert inspeccionar_cp(sqlite_db).n_aliados_activos == 5


def test_apply_autorizado_sqlite_completa_faltantes_y_respeta_reales(sqlite_db, monkeypatch):
    monkeypatch.setenv(ENV_APPLY, "1")
    reales, encargo_real = _estado_observado_produccion(sqlite_db)
    scores_antes = {
        a.codigo: a.score for a in inspeccionar_cp(sqlite_db).aliados_activos if a.codigo in reales
    }
    terr_antes = grupo_madre_service.contar_grupos_territoriales_activos_por_cp(
        sqlite_db, CP_OBJETIVO_DEFAULT
    )

    resultado = aplicar_plan(sqlite_db, confirm_token=CONFIRM_TOKEN)
    assert resultado["status"] == "success", resultado
    assert resultado["integridad"]["ok"] is True
    creados = resultado["aliados_qa_creados"]
    encargos = resultado["encargos_ids"]
    assert len(creados) == 5
    assert len(encargos) == 2

    insp = inspeccionar_cp(sqlite_db)
    assert insp.n_aliados_activos == 10
    assert insp.n_encargos_validos == 3
    assert insp.aliados_faltan == 0
    assert insp.encargos_faltan == 0
    assert terr_antes == 0
    assert grupo_madre_service.contar_grupos_territoriales_activos_por_cp(
        sqlite_db, CP_OBJETIVO_DEFAULT
    ) == 0
    assert encargo_real in {e.id for e in insp.encargos_validos}

    oficios = [a.oficio for a in insp.aliados_activos]
    assert len(oficios) == len(set(oficios))
    for codigo in reales:
        aliado = sqlite_db.obtener_aliado_por_codigo(codigo)
        assert aliado["estado"] == "activo"
        assert aliado["codigo_postal"] == CP_OBJETIVO_DEFAULT
        assert aliado["score"] == scores_antes[codigo]
        assert PREFIX not in (aliado.get("nombre") or "")

    for codigo in creados:
        aliado = sqlite_db.obtener_aliado_por_codigo(codigo)
        assert aliado["estado"] == "activo"
        assert aliado["marca"] == PREFIX
        assert not aliado.get("stripe_account_id")

    for enc_id in encargos:
        enc = sqlite_db.obtener_contacto_por_id(enc_id)
        assert enc["estado"] == "aceptado"
        assert enc["solicitante_codigo"] in creados
        assert enc["profesional_codigo"] in creados

    segundo = dry_run(sqlite_db)
    assert segundo["estado_actual"]["aliados_faltan"] == 0
    assert segundo["estado_actual"]["encargos_faltan"] == 0
    assert segundo["plan"]["aliados_a_crear"] == []
    assert segundo["plan"]["encargos_a_crear"] == []


def test_no_planifica_si_cp_territorial(sqlite_db):
    sqlite_db.crear_grupo_en_cp(CP_OBJETIVO_DEFAULT, "Alicante", "Alicante")
    _crear(sqlite_db, "81101", "Electricidad")
    plan = calcular_plan(sqlite_db, inspeccionar_cp(sqlite_db))
    assert plan.bloqueos
    assert plan.aliados_a_crear == []
    assert plan.encargos_a_crear == []


def test_cli_dry_run_no_apply(sqlite_db, monkeypatch, capsys):
    script = Path(__file__).resolve().parents[1] / "scripts" / "qa_madurez_cp.py"
    spec = importlib.util.spec_from_file_location("qa_madurez_cp_cli", script)
    mod = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(mod)
    monkeypatch.setattr(mod, "get_db", lambda: sqlite_db)
    _estado_observado_produccion(sqlite_db)
    code = mod.main(["--cp", CP_OBJETIVO_DEFAULT, "--json"])
    captured = capsys.readouterr()
    assert code == 0
    assert '"aliados_faltan":5' in captured.out.replace(" ", "")
    blocked = mod.main(["--apply", "--confirm", CONFIRM_TOKEN])
    assert blocked == 2
    assert inspeccionar_cp(sqlite_db).n_aliados_activos == 5
