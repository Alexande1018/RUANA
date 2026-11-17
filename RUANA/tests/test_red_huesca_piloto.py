"""Piloto reversible Red Huesca (CP 22xxx), sobre la capa genérica de redes regionales.

Cubre: incorporación (Amaury 84957 + Ionut 51724), un CP que no es 22 no entra,
reparto cruzado cuando el oficio no está en el grupo propio, aislamiento de
tablas / score / comisiones / pagos / competencia, reversión, convivencia con
Red Centro, API admin, modal y el script de instantánea.
"""
import json
import re
from pathlib import Path
from types import SimpleNamespace

import pytest

from core import db_manager as db_module
from core.services import (
    notificacion_service,
    red_centro_service as rc,
    red_regional_service as rr,
    solicitud_service,
)
from RUANA.web import app as app_module

WEB = Path(__file__).resolve().parents[1] / "web"
TABLAS_PILOTO = ("red_piloto", "red_piloto_miembros")
HUESCA = rr.RED_HUESCA

# Caso real del brief (17 nov 2026).
AMAURY = "84957"
IONUT = "51724"
OFICIO_AMAURY = "Carpintería de madera e interior"
OFICIO_IONUT = "Albañilería y obra"
CP_AMAURY = "22260"  # Grañén
CP_IONUT = "22200"   # Sariñena


@pytest.fixture
def sqlite_db(tmp_path, monkeypatch):
    monkeypatch.setattr(
        db_module,
        "get_settings",
        lambda: SimpleNamespace(postgres_configured=False, database_url=""),
    )
    return db_module.DBManager(str(tmp_path / "ruana_red_huesca.db"))


@pytest.fixture
def huesca_on(monkeypatch):
    monkeypatch.setenv("RED_HUESCA_ENABLED", "1")
    monkeypatch.delenv("RED_HUESCA_AVISO_ENABLED", raising=False)
    monkeypatch.delenv("RED_HUESCA_MAX_CANDIDATOS", raising=False)


@pytest.fixture
def huesca_off(monkeypatch):
    monkeypatch.delenv("RED_HUESCA_ENABLED", raising=False)


@pytest.fixture
def centro_on(monkeypatch):
    monkeypatch.setenv("RED_CENTRO_ENABLED", "1")
    monkeypatch.delenv("RED_CENTRO_AVISO_ENABLED", raising=False)
    monkeypatch.delenv("RED_CENTRO_MAX_CANDIDATOS", raising=False)


def _crear(db, codigo, oficio, cp, estado="activo"):
    r = db.crear_aliado(
        codigo=codigo,
        nombre=f"Aliado {codigo}",
        marca="Marca",
        oficio=oficio,
        codigo_postal=cp,
        email=f"{codigo}@example.com",
        telefono=f"+34600{codigo}",
        estado=estado,
        score=50,
    )
    assert r.get("status") == "success", r
    conn = db._connect()
    conn.execute("UPDATE aliados SET estado = ? WHERE codigo = ?", (estado, codigo))
    conn.commit()
    conn.close()


def _poblar_huesca(db):
    """Amaury + Ionut (elegibles) y no elegibles de otras provincias."""
    _crear(db, AMAURY, OFICIO_AMAURY, CP_AMAURY)
    _crear(db, IONUT, OFICIO_IONUT, CP_IONUT)
    _crear(db, "99692", "Fontanería y fontanería-gas", "50001")  # Zaragoza: no
    _crear(db, "20521", "Electricidad", "45500")  # Toledo / Red Centro: no
    _crear(db, "26053", "Fontanería y fontanería-gas", "03380")  # Alicante: no
    _crear(db, "22999", "Pintura y decoración", "22001", estado="pendiente_validacion")


def _tipos(db, codigo):
    return [n.get("tipo") for n in notificacion_service.listar_notificaciones_aliado(db, codigo)]


def _dump_no_piloto(db):
    conn = db._connect()
    try:
        cur = conn.cursor()
        cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")
        tablas = sorted(r[0] for r in cur.fetchall() if r[0] not in TABLAS_PILOTO)
        out = {}
        for t in tablas:
            cur.execute(f'SELECT * FROM "{t}"')
            out[t] = sorted(json.dumps(list(r), default=str) for r in cur.fetchall())
        return out
    finally:
        conn.close()


def _org(db):
    return rc._con_conexion(db, lambda conn, cur: rc.capturar_organizacion(db, cur))


def _grupo_id(db, codigo):
    conn = db._connect()
    try:
        return conn.execute("SELECT grupo_id FROM aliados WHERE codigo = ?", (codigo,)).fetchone()[0]
    finally:
        conn.close()


# --- Configuración ----------------------------------------------------------------

def test_registro_solo_tiene_huesca_con_prefijo_22():
    assert list(rr.REDES) == ["red_huesca"]
    assert HUESCA.prefijos_cp == ("22",)
    assert rr.cp_elegible("22260", HUESCA) is True
    assert rr.cp_elegible("22200", HUESCA) is True
    for cp in ("28001", "45500", "50001", "03380", "22", "2226", "222600", "", None):
        assert rr.cp_elegible(cp, HUESCA) is False


def test_flag_apagado_por_defecto_no_hace_nada(sqlite_db, huesca_off):
    _poblar_huesca(sqlite_db)
    assert rr.piloto_habilitado(HUESCA) is False
    assert rr.aviso_habilitado(HUESCA) is False
    r = rr.activar(sqlite_db, "ADMIN", HUESCA)
    assert r["status"] == "error" and r["http"] == 409
    creada = solicitud_service.crear_solicitud_por_codigo(
        sqlite_db, AMAURY, "Albañilería", "Obra en Sariñena"
    )
    assert creada["enrutamiento"] == "buscando_ayuda"
    assert rr.aviso_para_aliado(sqlite_db, AMAURY, HUESCA)["mostrar"] is False


def test_red_activa_en_bd_pero_flag_apagado_no_reparte(sqlite_db, huesca_on, monkeypatch):
    _poblar_huesca(sqlite_db)
    rr.activar(sqlite_db, "ADMIN", HUESCA)
    monkeypatch.delenv("RED_HUESCA_ENABLED")
    creada = solicitud_service.crear_solicitud_por_codigo(
        sqlite_db, AMAURY, "Albañilería", "Obra en Sariñena"
    )
    assert creada["enrutamiento"] == "buscando_ayuda"


# --- Incorporación -------------------------------------------------------------------

def test_activar_incorpora_solo_elegibles_cp_22(sqlite_db, huesca_on):
    _poblar_huesca(sqlite_db)
    r = rr.activar(sqlite_db, "ADMIN", HUESCA)
    assert r["status"] == "success" and r["ya_activa"] is False
    est = rr.estado(sqlite_db, HUESCA)
    assert est["operativa"] is True
    assert est["prefijos_cp"] == ["22"]
    assert est["miembros"] == sorted([AMAURY, IONUT])
    assert est["elegibles"] == sorted([AMAURY, IONUT])
    for fuera in ("99692", "20521", "26053", "22999"):
        assert fuera not in est["miembros"]
    # No se mueve de grupo territorial.
    assert _grupo_id(sqlite_db, AMAURY) != _grupo_id(sqlite_db, IONUT)


def test_activar_es_idempotente_sin_duplicados(sqlite_db, huesca_on):
    _poblar_huesca(sqlite_db)
    rr.activar(sqlite_db, "ADMIN", HUESCA)
    r2 = rr.activar(sqlite_db, "ADMIN", HUESCA)
    assert r2["ya_activa"] is True and r2["nuevos"] == []
    conn = sqlite_db._connect()
    n = conn.execute(
        "SELECT COUNT(*) FROM red_piloto_miembros m JOIN red_piloto r ON r.id = m.red_id WHERE r.slug = ?",
        ("red_huesca",),
    ).fetchone()[0]
    redes = conn.execute("SELECT COUNT(*) FROM red_piloto WHERE slug='red_huesca' AND estado='activa'").fetchone()[0]
    conn.close()
    assert n == 2 and redes == 1


def test_nuevo_aliado_elegible_se_incorpora_automaticamente(sqlite_db, huesca_on):
    _poblar_huesca(sqlite_db)
    rr.activar(sqlite_db, "ADMIN", HUESCA)
    _crear(sqlite_db, "22001", "Electricidad", "22004")
    assert rr.incorporar_tras_alta(sqlite_db, "22001") is True
    assert rr.incorporar_tras_alta(sqlite_db, "22001") is True
    _crear(sqlite_db, "50002", "Electricidad", "50002")
    assert rr.incorporar_tras_alta(sqlite_db, "50002") is False
    miembros = rr.estado(sqlite_db, HUESCA)["miembros"]
    assert miembros.count("22001") == 1
    assert "50002" not in miembros


def test_aliado_validado_mas_tarde_entra_al_validarse(sqlite_db, huesca_on):
    _poblar_huesca(sqlite_db)
    rr.activar(sqlite_db, "ADMIN", HUESCA)
    assert "22999" not in rr.estado(sqlite_db, HUESCA)["miembros"]
    conn = sqlite_db._connect()
    grupo = conn.execute("SELECT grupo_id FROM aliados WHERE codigo=?", (AMAURY,)).fetchone()[0]
    conn.execute(
        "UPDATE aliados SET estado='activo', grupo_id=COALESCE(grupo_id, ?) WHERE codigo='22999'",
        (grupo,),
    )
    conn.commit()
    conn.close()
    assert "22999" in rr.estado(sqlite_db, HUESCA)["miembros"]


# --- Reparto de encargos ------------------------------------------------------------

def test_amaury_e_ionut_se_ven_cruzados_si_el_oficio_no_esta_en_el_grupo(sqlite_db, huesca_on):
    _poblar_huesca(sqlite_db)
    rr.activar(sqlite_db, "ADMIN", HUESCA)
    # Amaury (carpintero, grupo propio sin albañil) pide albañilería → Ionut.
    creada = solicitud_service.crear_solicitud_por_codigo(
        sqlite_db, AMAURY, "Albañilería", "Obra en Grañén"
    )
    assert creada["status"] == "success"
    assert creada["enrutamiento"] == "proximidad"
    assert creada["proximidad"]["codigo"] == IONUT
    assert creada["proximidad"]["etiqueta_proximidad"] == HUESCA.etiqueta_proximidad
    assert creada["requiere_aprobacion_proximidad"] is True
    for cod in (IONUT, "99692", "20521", "26053"):
        assert "proximidad_solicitud" not in _tipos(sqlite_db, cod)
    acept = solicitud_service.aceptar_proximidad_solicitud(sqlite_db, creada["id"], AMAURY)
    assert acept["status"] == "success"
    assert "proximidad_solicitud" in _tipos(sqlite_db, IONUT)
    # Al revés: Ionut pide carpintería → Amaury.
    otra = solicitud_service.crear_solicitud_por_codigo(
        sqlite_db, IONUT, "Carpintería", "Mueble en Sariñena"
    )
    assert otra["enrutamiento"] == "proximidad"
    assert otra["proximidad"]["codigo"] == AMAURY
    assert otra["proximidad"]["etiqueta_proximidad"] == HUESCA.etiqueta_proximidad


def test_oficio_en_el_grupo_de_amaury_gana_a_la_red(sqlite_db, huesca_on):
    """Si el grupo de Amaury ya tiene un albañil, Ionut no entra por la red."""
    _poblar_huesca(sqlite_db)
    _crear(sqlite_db, "84959", "Albañilería y obra", CP_AMAURY)
    rr.activar(sqlite_db, "ADMIN", HUESCA)
    creada = solicitud_service.crear_solicitud_por_codigo(
        sqlite_db, AMAURY, "Albañilería", "Obra en el pueblo"
    )
    assert creada["enrutamiento"] == "profesional_grupo"
    assert creada["profesional"]["codigo"] == "84959"


def test_solicitante_fuera_de_huesca_no_usa_la_red(sqlite_db, huesca_on):
    _poblar_huesca(sqlite_db)
    rr.activar(sqlite_db, "ADMIN", HUESCA)
    creada = solicitud_service.crear_solicitud_por_codigo(
        sqlite_db, "99692", "Albañilería", "Obra en Zaragoza"
    )
    assert creada["enrutamiento"] == "buscando_ayuda"
    # Un madrileño / toledano tampoco.
    creada2 = solicitud_service.crear_solicitud_por_codigo(
        sqlite_db, "20521", "Albañilería", "Obra en Toledo"
    )
    assert creada2["enrutamiento"] == "buscando_ayuda"


def test_candidatos_red_solo_oficio_y_cp_22(sqlite_db, huesca_on, monkeypatch):
    _poblar_huesca(sqlite_db)
    _crear(sqlite_db, "22101", "Albañilería y obra", "22100")
    rr.activar(sqlite_db, "ADMIN", HUESCA)

    def cands(n=None):
        return rr._con_conexion(
            sqlite_db,
            lambda conn, cur: rr.candidatos_red(sqlite_db, cur, AMAURY, "Albañilería", HUESCA, limite=n),
        )

    todos = cands(10)
    codigos = [c["codigo"] for c in todos]
    assert set(codigos) == {IONUT, "22101"}
    assert all(c["red_regional"] and c["red_slug"] == "red_huesca" and not c["mismo_grupo"] for c in todos)
    monkeypatch.setenv("RED_HUESCA_MAX_CANDIDATOS", "1")
    assert len(cands()) == 1


def test_fallo_del_piloto_no_rompe_el_reparto(sqlite_db, huesca_on, monkeypatch):
    _poblar_huesca(sqlite_db)
    rr.activar(sqlite_db, "ADMIN", HUESCA)

    def boom(*a, **k):
        raise RuntimeError("fallo simulado")

    monkeypatch.setattr(rr, "_candidatos_red_impl", boom)
    creada = solicitud_service.crear_solicitud_por_codigo(
        sqlite_db, AMAURY, "Albañilería", "Obra"
    )
    assert creada["status"] == "success"
    assert creada["enrutamiento"] == "buscando_ayuda"


def test_crear_solicitud_con_red_no_abre_conexion_anidada(sqlite_db, huesca_on):
    _poblar_huesca(sqlite_db)
    rr.activar(sqlite_db, "ADMIN", HUESCA)
    original = sqlite_db._connect
    opens = {"n": 0}

    def wrapped():
        opens["n"] += 1
        return original()

    sqlite_db._connect = wrapped
    try:
        creada = solicitud_service.crear_solicitud_por_codigo(
            sqlite_db, AMAURY, "Albañilería", "Obra, conexión única"
        )
    finally:
        sqlite_db._connect = original
    assert creada["enrutamiento"] == "proximidad"
    assert opens["n"] == 1


# --- Convivencia con Red Centro -----------------------------------------------------

def test_huesca_no_mezcla_miembros_ni_reparto_con_red_centro(sqlite_db, huesca_on, centro_on):
    _poblar_huesca(sqlite_db)
    # 20521 ya está en _poblar_huesca; añadimos el fontanero de Madrid y el riego de Toledo.
    if not sqlite_db.obtener_aliado_por_codigo("64990"):
        _crear(sqlite_db, "64990", "Riego automático", "45500")
    if not sqlite_db.obtener_aliado_por_codigo("75658"):
        _crear(sqlite_db, "75658", "Fontanería y fontanería-gas", "28770")
    rc.activar(sqlite_db, "ADMIN")
    rr.activar(sqlite_db, "ADMIN", HUESCA)

    est_h = rr.estado(sqlite_db, HUESCA)
    est_c = rc.estado(sqlite_db)
    assert set(est_h["miembros"]) == {AMAURY, IONUT}
    assert AMAURY not in est_c["miembros"] and IONUT not in est_c["miembros"]
    assert "20521" in est_c["miembros"] and "75658" in est_c["miembros"]
    assert "20521" not in est_h["miembros"]

    # Huesca no recibe fontaneros de Madrid.
    desde_huesca = solicitud_service.crear_solicitud_por_codigo(
        sqlite_db, AMAURY, "Fontanería", "Fuga en Grañén"
    )
    assert desde_huesca["enrutamiento"] == "buscando_ayuda"

    # Toledo sigue pudiendo usar Red Centro (fontanero de Madrid).
    desde_toledo = solicitud_service.crear_solicitud_por_codigo(
        sqlite_db, "20521", "Fontanería", "Fuga en Torrijos"
    )
    assert desde_toledo["enrutamiento"] == "proximidad"
    assert desde_toledo["proximidad"]["codigo"] == "75658"
    assert desde_toledo["proximidad"]["etiqueta_proximidad"] == rc.ETIQUETA_PROXIMIDAD_RED

    # Revertir Huesca no toca los miembros de Red Centro.
    rev = rr.revertir(sqlite_db, "ADMIN", HUESCA)
    assert rev["status"] == "success"
    assert rc.estado(sqlite_db)["miembros"] == est_c["miembros"]
    assert rr.estado(sqlite_db, HUESCA)["miembros"] == []
    assert rc.estado(sqlite_db)["operativa"] is True


# --- Notificaciones ------------------------------------------------------------------

def test_plantilla_notificacion_tono_y_botones_reales():
    p = rr.plantilla_notificacion(HUESCA)
    texto = (p["titulo"] + " " + p["mensaje"]).lower()
    assert "huesca" in texto and "encargo" in texto
    for prohibida in ("gratis", "primeros", "arrancamos", "zaragoza"):
        assert prohibida not in texto
    html = (WEB / "aliado.html").read_text(encoding="utf-8")
    js_sol = (WEB / "static/js/aliado-solicitudes-module.js").read_text(encoding="utf-8")
    assert "Nueva conexión" in p["mensaje"] and "Nueva conexión" in html
    assert "Ampliar mi red" in p["mensaje"] and "Ampliar mi red" in html
    assert "Conozco a alguien" in p["mensaje"] and "Conozco a alguien" in js_sol


def test_activar_y_aviso_no_envian_notificaciones_masivas(sqlite_db, huesca_on):
    _poblar_huesca(sqlite_db)
    rr.activar(sqlite_db, "ADMIN", HUESCA)
    rr.aviso_para_aliado(sqlite_db, AMAURY, HUESCA)
    conn = sqlite_db._connect()
    n = conn.execute(
        "SELECT COUNT(*) FROM notificaciones_aliado WHERE tipo = ?", (HUESCA.tipo_notificacion,)
    ).fetchone()[0]
    conn.close()
    assert n == 0
    src = Path(rr.__file__).read_text(encoding="utf-8")
    bp = (WEB / "blueprints/red_regional_bp.py").read_text(encoding="utf-8")
    assert "entregar_notificacion_verificada" not in bp
    assert src.count("entregar_notificacion_verificada(") == 1


def test_notificacion_solo_entregada_si_se_verifica(sqlite_db):
    _crear(sqlite_db, AMAURY, OFICIO_AMAURY, CP_AMAURY)
    r = rr.entregar_notificacion_verificada(sqlite_db, AMAURY, HUESCA)
    assert r["entregada"] is True and r["canal"] == "in_app"
    inbox = notificacion_service.listar_notificaciones_aliado(sqlite_db, AMAURY)
    assert any(n["id"] == r["notificacion_id"] and n["tipo"] == HUESCA.tipo_notificacion for n in inbox)


# --- Aislamiento de reglas -------------------------------------------------------------

def test_piloto_solo_escribe_en_sus_tablas(sqlite_db, huesca_on):
    _poblar_huesca(sqlite_db)
    antes = _dump_no_piloto(sqlite_db)
    rr.activar(sqlite_db, "ADMIN", HUESCA)
    rr.estado(sqlite_db, HUESCA)
    rr.aviso_para_aliado(sqlite_db, AMAURY, HUESCA)
    rr.registrar_accion_aviso(sqlite_db, AMAURY, "invitar", HUESCA)
    rr._con_conexion(
        sqlite_db, lambda c, cur: rr.candidatos_red(sqlite_db, cur, AMAURY, "Albañilería", HUESCA)
    )
    rr.incorporar_tras_alta(sqlite_db, IONUT)
    rr.revertir(sqlite_db, "ADMIN", HUESCA)
    assert _dump_no_piloto(sqlite_db) == antes


def test_reglas_economicas_score_y_competencia_no_cambian(sqlite_db, huesca_on, monkeypatch):
    from core.financial import money
    from core.services import encargo_externo_service, score_service

    reglas = json.loads((Path(rr.__file__).resolve().parents[2] / "config/ruana_reglas_v1.json").read_text())

    def foto():
        return {
            "apoyo_pct": reglas["apoyo_pct"],
            "comision": money.COMISION_RUANA_PCT,
            "externos": (encargo_externo_service.comision_activada(), encargo_externo_service.COMISION_PCT_POR_DEFECTO),
            "umbral": reglas["umbral_competencia"],
            "estados": [score_service.score_a_estado(s) for s in (0, 14, 15, 49, 50, 199, 200, 349, 350, 500)],
        }

    monkeypatch.delenv("RED_HUESCA_ENABLED")
    apagado = foto()
    monkeypatch.setenv("RED_HUESCA_ENABLED", "1")
    _poblar_huesca(sqlite_db)
    rr.activar(sqlite_db, "ADMIN", HUESCA)
    assert foto() == apagado
    assert apagado["comision"] == 5 and apagado["apoyo_pct"] == 5.0 and apagado["umbral"] == 15
    org0 = _org(sqlite_db)
    solicitud_service.crear_solicitud_por_codigo(sqlite_db, AMAURY, "Albañilería", "Obra")
    assert _org(sqlite_db) == org0


def test_servicio_no_contiene_sql_de_escritura_fuera_de_su_capa():
    src = Path(rr.__file__).read_text(encoding="utf-8")
    escrituras = re.findall(r"(INSERT INTO|UPDATE|DELETE FROM)\s+(\w+)", src)
    tablas = {t for _, t in escrituras}
    assert tablas <= {"red_piloto", "red_piloto_miembros", "notificaciones_aliado"}, tablas
    for prohibida in ("aliados", "grupos", "contactos_ruana", "pagos", "competencia", "score_movimientos"):
        assert prohibida not in tablas


def test_activar_no_cambia_grupo_id(sqlite_db, huesca_on):
    _poblar_huesca(sqlite_db)
    g_a = _grupo_id(sqlite_db, AMAURY)
    g_i = _grupo_id(sqlite_db, IONUT)
    assert g_a and g_i and g_a != g_i
    rr.activar(sqlite_db, "ADMIN", HUESCA)
    solicitud_service.crear_solicitud_por_codigo(sqlite_db, AMAURY, "Albañilería", "Obra")
    assert _grupo_id(sqlite_db, AMAURY) == g_a
    assert _grupo_id(sqlite_db, IONUT) == g_i


# --- Reversión ----------------------------------------------------------------------

def test_reversion_restaura_organizacion_y_conserva_actividad(sqlite_db, huesca_on):
    _poblar_huesca(sqlite_db)
    org_original = _org(sqlite_db)
    act = rr.activar(sqlite_db, "ADMIN", HUESCA)
    assert act["red"]["snapshot_sha256"] == rc.checksum(org_original)
    _crear(sqlite_db, "22001", "Electricidad", "22004")
    rr.incorporar_tras_alta(sqlite_db, "22001")
    creada = solicitud_service.crear_solicitud_por_codigo(sqlite_db, AMAURY, "Albañilería", "Obra")
    solicitud_service.aceptar_proximidad_solicitud(sqlite_db, creada["id"], AMAURY)
    rr.aviso_para_aliado(sqlite_db, IONUT, HUESCA)
    rr.registrar_accion_aviso(sqlite_db, IONUT, "aceptar", HUESCA)

    rev = rr.revertir(sqlite_db, "ADMIN", HUESCA)
    assert rev["status"] == "success"
    v = rev["verificacion"]
    assert v["identica"] is True, v["diferencias"]
    assert v["checksum_actual_subconjunto"] == v["checksum_original"] == rc.checksum(org_original)
    assert "22001" in v["altas_conservadas"]
    assert v["miembros_borrados"] == 3
    assert sqlite_db.obtener_aliado_por_codigo("22001")
    propias = solicitud_service.listar_solicitudes_propias_por_codigo(sqlite_db, AMAURY)
    assert creada["id"] in {s["id"] for s in propias}
    assert "proximidad_solicitud" in _tipos(sqlite_db, IONUT)
    conn = sqlite_db._connect()
    assert conn.execute(
        "SELECT COUNT(*) FROM red_piloto_miembros m JOIN red_piloto r ON r.id=m.red_id WHERE r.slug='red_huesca'"
    ).fetchone()[0] == 0
    assert conn.execute("SELECT estado FROM red_piloto WHERE slug='red_huesca'").fetchone()[0] == "revertida"
    conn.close()
    nueva = solicitud_service.crear_solicitud_por_codigo(sqlite_db, AMAURY, "Albañilería", "Otra")
    assert nueva["enrutamiento"] == "buscando_ayuda"
    assert rr.aviso_para_aliado(sqlite_db, IONUT, HUESCA)["mostrar"] is False
    assert rr.revertir(sqlite_db, "ADMIN", HUESCA)["http"] == 404


def test_reversion_detecta_cambios_en_la_organizacion(sqlite_db, huesca_on):
    _poblar_huesca(sqlite_db)
    rr.activar(sqlite_db, "ADMIN", HUESCA)
    conn = sqlite_db._connect()
    conn.execute("UPDATE aliados SET codigo_postal = '50001' WHERE codigo = ?", (AMAURY,))
    conn.commit()
    conn.close()
    v = rr.revertir(sqlite_db, "ADMIN", HUESCA)["verificacion"]
    assert v["identica"] is False
    assert {"tipo": "aliado_campo", "codigo": AMAURY, "campo": "codigo_postal",
            "antes": CP_AMAURY, "ahora": "50001"} in v["diferencias"]


def test_reversion_se_niega_si_la_instantanea_esta_alterada(sqlite_db, huesca_on):
    _poblar_huesca(sqlite_db)
    rr.activar(sqlite_db, "ADMIN", HUESCA)
    conn = sqlite_db._connect()
    conn.execute("UPDATE red_piloto SET snapshot_sha256 = 'x' WHERE slug='red_huesca'")
    conn.commit()
    conn.close()
    r = rr.revertir(sqlite_db, "ADMIN", HUESCA)
    assert r["status"] == "error" and r["http"] == 409
    conn = sqlite_db._connect()
    assert conn.execute(
        "SELECT COUNT(*) FROM red_piloto_miembros m JOIN red_piloto r ON r.id=m.red_id WHERE r.slug='red_huesca'"
    ).fetchone()[0] == 2
    conn.close()


# --- Admin API -------------------------------------------------------------------------

def test_admin_api_estado_activar_revertir(client, sqlite_db, monkeypatch, session_headers, huesca_on):
    monkeypatch.setattr(app_module, "get_db", lambda: sqlite_db)
    _poblar_huesca(sqlite_db)
    lectura = session_headers("admin", "ADMIN001", permisos=["leer"])
    escritura = session_headers("admin", "ADMIN001", permisos=["leer", "escribir"])
    assert client.post("/api/admin/red-huesca/activar", headers=lectura).status_code == 403
    r = client.post("/api/admin/red-huesca/activar", headers=escritura)
    assert r.status_code == 200, r.get_json()
    est = client.get("/api/admin/red-huesca", headers=lectura).get_json()
    assert est["operativa"] is True and set(est["miembros"]) == {AMAURY, IONUT}
    assert est["prefijos_cp"] == ["22"]
    pl = client.get("/api/admin/red-huesca/plantilla-notificacion", headers=lectura).get_json()
    assert pl["envio_masivo"] is False
    lista = client.get("/api/admin/redes-regionales", headers=lectura).get_json()
    assert lista["status"] == "success" and any(x["slug"] == "red_huesca" for x in lista["redes"])
    rv = client.post("/api/admin/red-huesca/revertir", headers=escritura).get_json()
    assert rv["verificacion"]["identica"] is True
    assert client.get("/api/admin/red-huesca").status_code in (401, 403)


# --- Modal de bienvenida (API) -----------------------------------------------------------

def test_modal_una_sola_vez_y_persistente_entre_sesiones(client, sqlite_db, monkeypatch, session_headers, huesca_on):
    monkeypatch.setattr(app_module, "get_db", lambda: sqlite_db)
    _poblar_huesca(sqlite_db)
    rr.activar(sqlite_db, "ADMIN", HUESCA)
    movil = session_headers("aliado", AMAURY)
    r = client.get("/api/aliado/red-huesca/aviso", headers=movil).get_json()
    assert r["mostrar"] is True and r["zona"] == "Huesca" and r["slug"] == "red_huesca"
    gen = client.get("/api/aliado/red-regional/aviso", headers=movil).get_json()
    assert gen["mostrar"] is True and gen["zona"] == "Huesca"
    assert client.post(
        "/api/aliado/red-regional/aviso", json={"accion": "cerrar", "slug": "red_huesca"}, headers=movil
    ).get_json()["registrado"] is True
    assert client.get("/api/aliado/red-huesca/aviso", headers=movil).get_json()["mostrar"] is False
    escritorio = session_headers("aliado", AMAURY)
    assert client.get("/api/aliado/red-regional/aviso", headers=escritorio).get_json()["mostrar"] is False
    assert client.post(
        "/api/aliado/red-huesca/aviso", json={"accion": "aceptar"}, headers=escritorio
    ).get_json()["registrado"] is False
    conn = sqlite_db._connect()
    acc = conn.execute(
        "SELECT aviso_red_centro_accion FROM red_piloto_miembros WHERE aliado_codigo=?", (AMAURY,)
    ).fetchone()[0]
    conn.close()
    assert acc == "cerrar"


@pytest.mark.parametrize("accion", ["aceptar", "recomendar", "invitar"])
def test_modal_acciones_marcan_visto(client, sqlite_db, monkeypatch, session_headers, huesca_on, accion):
    monkeypatch.setattr(app_module, "get_db", lambda: sqlite_db)
    _poblar_huesca(sqlite_db)
    rr.activar(sqlite_db, "ADMIN", HUESCA)
    h = session_headers("aliado", IONUT)
    assert client.get("/api/aliado/red-huesca/aviso", headers=h).get_json()["mostrar"] is True
    assert client.post("/api/aliado/red-huesca/aviso", json={"accion": accion}, headers=h).get_json()["registrado"] is True
    assert client.get("/api/aliado/red-huesca/aviso", headers=h).get_json()["mostrar"] is False


@pytest.mark.parametrize("codigo", ["99692", "20521", "26053", "22999"])
def test_modal_no_se_muestra_a_ajenos_ni_no_validados(client, sqlite_db, monkeypatch, session_headers, huesca_on, codigo):
    monkeypatch.setattr(app_module, "get_db", lambda: sqlite_db)
    _poblar_huesca(sqlite_db)
    rr.activar(sqlite_db, "ADMIN", HUESCA)
    h = session_headers("aliado", codigo)
    r = client.get("/api/aliado/red-huesca/aviso", headers=h)
    if r.status_code == 200:
        assert r.get_json()["mostrar"] is False
    else:
        assert r.status_code in (401, 403)
    assert codigo not in rr.estado(sqlite_db, HUESCA)["miembros"]


def test_modal_flag_de_aviso_y_flag_maestro(client, sqlite_db, monkeypatch, session_headers, huesca_on):
    monkeypatch.setattr(app_module, "get_db", lambda: sqlite_db)
    _poblar_huesca(sqlite_db)
    rr.activar(sqlite_db, "ADMIN", HUESCA)
    h = session_headers("aliado", AMAURY)
    monkeypatch.setenv("RED_HUESCA_AVISO_ENABLED", "0")
    assert client.get("/api/aliado/red-huesca/aviso", headers=h).get_json()["mostrar"] is False
    monkeypatch.setenv("RED_HUESCA_AVISO_ENABLED", "1")
    monkeypatch.setenv("RED_HUESCA_ENABLED", "0")
    assert client.get("/api/aliado/red-regional/aviso", headers=h).get_json()["mostrar"] is False


def test_modal_fail_open_si_falla_el_backend(client, sqlite_db, monkeypatch, session_headers, huesca_on):
    monkeypatch.setattr(app_module, "get_db", lambda: sqlite_db)
    _poblar_huesca(sqlite_db)
    rr.activar(sqlite_db, "ADMIN", HUESCA)

    def boom(*a, **k):
        raise RuntimeError("BD caída")

    monkeypatch.setattr(rr, "red_activa", boom)
    r = client.get("/api/aliado/red-huesca/aviso", headers=session_headers("aliado", AMAURY))
    assert r.status_code == 200 and r.get_json()["mostrar"] is False


def test_modal_accion_invalida_y_sin_sesion(client, sqlite_db, monkeypatch, session_headers, huesca_on):
    monkeypatch.setattr(app_module, "get_db", lambda: sqlite_db)
    _poblar_huesca(sqlite_db)
    rr.activar(sqlite_db, "ADMIN", HUESCA)
    h = session_headers("aliado", AMAURY)
    assert client.post("/api/aliado/red-huesca/aviso", json={"accion": "borrar"}, headers=h).status_code == 400
    assert client.get("/api/aliado/red-huesca/aviso").status_code in (401, 403)


# --- Modal de bienvenida (contrato de frontend) -------------------------------------------

def test_modal_frontend_texto_zona_y_botones():
    js = (WEB / "static/js/aliado-red-regional-module.js").read_text(encoding="utf-8")
    assert "Estamos conectando a los profesionales de " in js
    assert "d.mostrar === true" in js and ".catch(" in js
    assert 'role="dialog"' in js and 'aria-modal="true"' in js
    for etiqueta in ("Entendido, ¡vamos allá!", "Recomendar trabajo", "Invitar aliado", "✕"):
        assert etiqueta in js
    assert "AliadoShell.show('conexiones')" in js
    assert "btn-invitar-global" in js
    assert "/api/aliado/red-regional/aviso" in js
    html = (WEB / "aliado.html").read_text(encoding="utf-8")
    assert "/static/js/aliado-red-regional-module.js" in html
    assert "/static/css/aliado-red-centro.css" in html


# --- Script de instantánea --------------------------------------------------------------

def _script():
    import importlib.util
    p = Path(__file__).resolve().parents[1] / "scripts" / "red_regional_snapshot.py"
    spec = importlib.util.spec_from_file_location("red_regional_snapshot", p)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_script_snapshot_elegibles_checksum_y_comparacion():
    s = _script()
    al = [
        {"codigo": AMAURY, "oficio": OFICIO_AMAURY, "codigo_postal": CP_AMAURY, "grupo_id": 21, "estado": "activo", "email": "x@y"},
        {"codigo": IONUT, "oficio": OFICIO_IONUT, "codigo_postal": CP_IONUT, "grupo_id": 22, "estado": "activo"},
        {"codigo": "99692", "oficio": "Fontanería", "codigo_postal": "50001", "grupo_id": 30, "estado": "activo"},
        {"codigo": "20521", "oficio": "Electricidad", "codigo_postal": "45500", "grupo_id": 12, "estado": "activo"},
    ]
    gr = [{"id": 21, "codigo_postal": CP_AMAURY, "estado": "activo"}]
    org = s.organizar(al, gr, [])
    assert "email" not in org["aliados"][0]
    assert s.elegibles(org, ("22",)) == sorted([AMAURY, IONUT])
    assert s.sha(org) == s.sha(s.organizar(list(reversed(al)), gr, []))
    assert s.comparar(org, org) == []
    al2 = [dict(a) for a in al]
    al2[0]["grupo_id"] = 99
    dif = s.comparar(org, s.organizar(al2, gr, []))
    assert dif == [f"aliados:{AMAURY}.grupo_id: 21 -> 99"]
    slug, prefs, nombre = s._cargar_red("red_huesca")
    assert slug == "red_huesca" and prefs == ("22",) and "Huesca" in nombre
