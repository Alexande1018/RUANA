"""Piloto reversible Red Centro (Madrid 28xxx + Toledo 45xxx).

Cubre: incorporación, reparto de encargos, notificaciones, aislamiento de
reglas (pagos, comisiones, competencia, negociación, score, exclusividad),
reversión exacta y el modal de bienvenida (API + contrato de frontend).
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
    solicitud_service,
)
from RUANA.web import app as app_module

WEB = Path(__file__).resolve().parents[1] / "web"
TABLAS_PILOTO = ("red_piloto", "red_piloto_miembros")


@pytest.fixture
def sqlite_db(tmp_path, monkeypatch):
    monkeypatch.setattr(
        db_module,
        "get_settings",
        lambda: SimpleNamespace(postgres_configured=False, database_url=""),
    )
    return db_module.DBManager(str(tmp_path / "ruana_red_centro.db"))


@pytest.fixture
def piloto_on(monkeypatch):
    monkeypatch.setenv("RED_CENTRO_ENABLED", "1")
    monkeypatch.delenv("RED_CENTRO_AVISO_ENABLED", raising=False)
    monkeypatch.delenv("RED_CENTRO_MAX_CANDIDATOS", raising=False)


@pytest.fixture
def piloto_off(monkeypatch):
    monkeypatch.delenv("RED_CENTRO_ENABLED", raising=False)


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


def _poblar_red(db):
    """Escenario parecido a producción (13 elegibles de 28/45) + no elegibles."""
    _crear(db, "20521", "Electricidad", "45500")
    _crear(db, "64990", "Riego automático", "45500")
    _crear(db, "86761", "Electricidad", "45007")
    _crear(db, "62318", "Climatización y calefacción", "45180")
    _crear(db, "75658", "Fontanería y fontanería-gas", "28770")
    _crear(db, "92979", "Fontanería y fontanería-gas", "28100")
    _crear(db, "54234", "Albañilería y obra", "28021")
    # No elegibles
    _crear(db, "26053", "Fontanería y fontanería-gas", "03380")  # Alicante
    _crear(db, "49854", "Fontanería y fontanería-gas", "19160")  # Guadalajara
    _crear(db, "45999", "Fontanería y fontanería-gas", "45600", estado="pendiente_validacion")


def _tipos(db, codigo):
    return [n.get("tipo") for n in notificacion_service.listar_notificaciones_aliado(db, codigo)]


def _dump_no_piloto(db):
    """Volcado de TODAS las tablas salvo las del piloto (para demostrar aislamiento)."""
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


# --- Flags -----------------------------------------------------------------------

def test_flag_apagado_por_defecto_no_hace_nada(sqlite_db, piloto_off):
    _poblar_red(sqlite_db)
    assert rc.piloto_habilitado() is False
    assert rc.aviso_habilitado() is False
    r = rc.activar(sqlite_db, "ADMIN")
    assert r["status"] == "error" and r["http"] == 409
    creada = solicitud_service.crear_solicitud_por_codigo(
        sqlite_db, "20521", "Fontanería", "Fuga en Torrijos"
    )
    assert creada["enrutamiento"] == "buscando_ayuda"
    assert rc.aviso_para_aliado(sqlite_db, "20521")["mostrar"] is False


def test_red_activa_en_bd_pero_flag_apagado_no_reparte(sqlite_db, piloto_on, monkeypatch):
    _poblar_red(sqlite_db)
    rc.activar(sqlite_db, "ADMIN")
    monkeypatch.delenv("RED_CENTRO_ENABLED")
    creada = solicitud_service.crear_solicitud_por_codigo(
        sqlite_db, "20521", "Fontanería", "Fuga en Torrijos"
    )
    assert creada["enrutamiento"] == "buscando_ayuda"


# --- Incorporación -------------------------------------------------------------------

def test_activar_incorpora_solo_elegibles_madrid_toledo(sqlite_db, piloto_on):
    _poblar_red(sqlite_db)
    r = rc.activar(sqlite_db, "ADMIN")
    assert r["status"] == "success" and r["ya_activa"] is False
    est = rc.estado(sqlite_db)
    esperados = sorted(["20521", "64990", "86761", "62318", "75658", "92979", "54234"])
    assert est["miembros"] == esperados
    assert est["elegibles"] == esperados
    for fuera in ("26053", "49854", "45999"):
        assert fuera not in est["miembros"]


def test_activar_es_idempotente_sin_duplicados(sqlite_db, piloto_on):
    _poblar_red(sqlite_db)
    rc.activar(sqlite_db, "ADMIN")
    r2 = rc.activar(sqlite_db, "ADMIN")
    assert r2["ya_activa"] is True and r2["nuevos"] == []
    conn = sqlite_db._connect()
    n = conn.execute("SELECT COUNT(*) FROM red_piloto_miembros").fetchone()[0]
    nd = conn.execute(
        "SELECT COUNT(*) FROM (SELECT aliado_codigo FROM red_piloto_miembros GROUP BY red_id, aliado_codigo HAVING COUNT(*) > 1)"
    ).fetchone()[0]
    redes = conn.execute("SELECT COUNT(*) FROM red_piloto WHERE estado = 'activa'").fetchone()[0]
    conn.close()
    assert n == 7 and nd == 0 and redes == 1


def test_nuevo_aliado_elegible_se_incorpora_automaticamente(sqlite_db, piloto_on):
    _poblar_red(sqlite_db)
    rc.activar(sqlite_db, "ADMIN")
    _crear(sqlite_db, "33091", "Electricidad", "28026")
    assert rc.incorporar_tras_alta(sqlite_db, "33091") is True
    assert rc.incorporar_tras_alta(sqlite_db, "33091") is True  # idempotente
    _crear(sqlite_db, "40001", "Electricidad", "08001")  # Barcelona: no
    assert rc.incorporar_tras_alta(sqlite_db, "40001") is False
    _crear(sqlite_db, "45111", "Electricidad", "45001", estado="pendiente_validacion")
    assert rc.incorporar_tras_alta(sqlite_db, "45111") is False
    miembros = rc.estado(sqlite_db)["miembros"]
    assert miembros.count("33091") == 1
    assert "40001" not in miembros and "45111" not in miembros


def test_aliado_validado_mas_tarde_entra_al_validarse(sqlite_db, piloto_on):
    _poblar_red(sqlite_db)
    rc.activar(sqlite_db, "ADMIN")
    assert "45999" not in rc.estado(sqlite_db)["miembros"]
    conn = sqlite_db._connect()
    grupo = conn.execute("SELECT grupo_id FROM aliados WHERE codigo='20521'").fetchone()[0]
    conn.execute("UPDATE aliados SET estado='activo', grupo_id=COALESCE(grupo_id, ?) WHERE codigo='45999'", (grupo,))
    conn.commit()
    conn.close()
    assert "45999" in rc.estado(sqlite_db)["miembros"]


# --- Reparto de encargos ------------------------------------------------------------

def test_toledo_sin_fontanero_recibe_fontanero_de_la_red(sqlite_db, piloto_on):
    _poblar_red(sqlite_db)
    rc.activar(sqlite_db, "ADMIN")
    creada = solicitud_service.crear_solicitud_por_codigo(
        sqlite_db, "20521", "Fontanería", "Fuga en Torrijos"
    )
    assert creada["status"] == "success"
    assert creada["enrutamiento"] == "proximidad"
    assert creada["proximidad"]["codigo"] in ("75658", "92979")
    assert creada["proximidad"]["etiqueta_proximidad"] == rc.ETIQUETA_PROXIMIDAD_RED
    assert creada["requiere_aprobacion_proximidad"] is True
    # Nadie recibe nada hasta que el solicitante acepta (no hay difusión).
    for cod in ("75658", "92979", "54234", "64990", "86761", "62318", "26053", "49854"):
        assert "proximidad_solicitud" not in _tipos(sqlite_db, cod)
        assert "solicitud_asignada" not in _tipos(sqlite_db, cod)
    acept = solicitud_service.aceptar_proximidad_solicitud(sqlite_db, creada["id"], "20521")
    assert acept["status"] == "success"
    elegido = creada["proximidad"]["codigo"]
    otro = "92979" if elegido == "75658" else "75658"
    assert "proximidad_solicitud" in _tipos(sqlite_db, elegido)
    assert "proximidad_solicitud" not in _tipos(sqlite_db, otro)
    for cod in ("54234", "86761", "62318", "26053", "49854", "45999"):
        assert "proximidad_solicitud" not in _tipos(sqlite_db, cod)


def test_oficio_en_el_grupo_tiene_prioridad_exclusividad_local(sqlite_db, piloto_on):
    _poblar_red(sqlite_db)
    rc.activar(sqlite_db, "ADMIN")
    # 20521 y 64990 comparten grupo 45500: el riego va al compañero de grupo.
    creada = solicitud_service.crear_solicitud_por_codigo(
        sqlite_db, "20521", "Riego automático", "Riego jardín"
    )
    assert creada["enrutamiento"] == "profesional_grupo"
    assert creada["profesional"]["codigo"] == "64990"


def test_proximidad_existente_gana_a_la_red(sqlite_db, piloto_on):
    _poblar_red(sqlite_db)
    rc.activar(sqlite_db, "ADMIN")
    # Madrid → Madrid ya es «misma ciudad» en la lógica actual.
    creada = solicitud_service.crear_solicitud_por_codigo(
        sqlite_db, "54234", "Fontanería", "Fuga en Madrid"
    )
    assert creada["enrutamiento"] == "proximidad"
    assert creada["proximidad"]["etiqueta_proximidad"] == "Misma ciudad"


def test_candidatos_red_por_oficio_proximidad_y_tope(sqlite_db, piloto_on, monkeypatch):
    _poblar_red(sqlite_db)
    _crear(sqlite_db, "45201", "Fontanería y fontanería-gas", "45200")
    _crear(sqlite_db, "45301", "Fontanería y fontanería-gas", "45300")
    rc.activar(sqlite_db, "ADMIN")

    def cands(n=None):
        return rc._con_conexion(
            sqlite_db, lambda conn, cur: rc.candidatos_red(sqlite_db, cur, "20521", "Fontanería", limite=n)
        )

    todos = cands(10)
    codigos = [c["codigo"] for c in todos]
    # Solo fontaneros de la red: ni Alicante, ni Guadalajara, ni no validados, ni otros oficios.
    assert set(codigos) == {"45201", "45301", "75658", "92979"}
    # Misma provincia primero (Toledo antes que Madrid).
    assert codigos[:2] == ["45301", "45201"] or codigos[:2] == ["45201", "45301"]
    assert set(codigos[2:]) == {"75658", "92979"}
    monkeypatch.setenv("RED_CENTRO_MAX_CANDIDATOS", "2")
    assert len(cands()) == 2
    assert all(c["red_centro"] and not c["mismo_grupo"] for c in todos)


def test_solicitante_fuera_de_la_red_no_usa_la_red(sqlite_db, piloto_on):
    _poblar_red(sqlite_db)
    _crear(sqlite_db, "03111", "Electricidad", "03111")
    rc.activar(sqlite_db, "ADMIN")
    creada = solicitud_service.crear_solicitud_por_codigo(
        sqlite_db, "03111", "Albañilería", "Obra en Alicante"
    )
    assert creada["enrutamiento"] == "buscando_ayuda"


def test_crear_solicitud_con_red_no_abre_conexion_anidada(sqlite_db, piloto_on):
    _poblar_red(sqlite_db)
    rc.activar(sqlite_db, "ADMIN")
    original = sqlite_db._connect
    opens = {"n": 0}

    def wrapped():
        opens["n"] += 1
        return original()

    sqlite_db._connect = wrapped
    try:
        creada = solicitud_service.crear_solicitud_por_codigo(
            sqlite_db, "20521", "Fontanería", "Fuga, conexión única"
        )
    finally:
        sqlite_db._connect = original
    assert creada["enrutamiento"] == "proximidad"
    assert opens["n"] == 1


def test_fallo_del_piloto_no_rompe_el_reparto(sqlite_db, piloto_on, monkeypatch):
    _poblar_red(sqlite_db)
    rc.activar(sqlite_db, "ADMIN")

    def boom(*a, **k):
        raise RuntimeError("fallo simulado")

    monkeypatch.setattr(rc, "_candidatos_red_impl", boom)
    creada = solicitud_service.crear_solicitud_por_codigo(
        sqlite_db, "20521", "Fontanería", "Fuga"
    )
    assert creada["status"] == "success"
    assert creada["enrutamiento"] == "buscando_ayuda"


# --- Notificaciones ------------------------------------------------------------------

def test_plantilla_notificacion_tono_y_botones_reales():
    p = rc.plantilla_notificacion()
    texto = (p["titulo"] + " " + p["mensaje"]).lower()
    assert "encargo" in texto
    for prohibida in ("gratis", "primeros", "arrancamos"):
        assert prohibida not in texto
    html = (WEB / "aliado.html").read_text(encoding="utf-8")
    js_sol = (WEB / "static/js/aliado-solicitudes-module.js").read_text(encoding="utf-8")
    # Los nombres que usa la plantilla existen de verdad en la app.
    assert "Nueva conexión" in p["mensaje"] and "Nueva conexión" in html
    assert "Ampliar mi red" in p["mensaje"] and "Ampliar mi red" in html
    assert "Conozco a alguien" in p["mensaje"] and "Conozco a alguien" in js_sol


def test_notificacion_solo_entregada_si_se_verifica(sqlite_db):
    _crear(sqlite_db, "20521", "Electricidad", "45500")
    r = rc.entregar_notificacion_verificada(sqlite_db, "20521")
    assert r["entregada"] is True and r["canal"] == "in_app"
    inbox = notificacion_service.listar_notificaciones_aliado(sqlite_db, "20521")
    assert any(n["id"] == r["notificacion_id"] and n["tipo"] == rc.TIPO_NOTIFICACION for n in inbox)
    assert all(int(n.get("leida") or 0) == 0 for n in inbox if n["tipo"] == rc.TIPO_NOTIFICACION)


def test_notificacion_fallida_no_se_marca_entregada(sqlite_db):
    _crear(sqlite_db, "20521", "Electricidad", "45500")
    conn = sqlite_db._connect()
    conn.execute("ALTER TABLE notificaciones_aliado RENAME TO notificaciones_aliado_x")
    conn.commit()
    conn.close()
    r = rc.entregar_notificacion_verificada(sqlite_db, "20521")
    assert r["entregada"] is False
    assert rc.entregar_notificacion_verificada(sqlite_db, "")["entregada"] is False


def test_activar_y_aviso_no_envian_notificaciones_masivas(sqlite_db, piloto_on):
    _poblar_red(sqlite_db)
    rc.activar(sqlite_db, "ADMIN")
    rc.aviso_para_aliado(sqlite_db, "20521")
    conn = sqlite_db._connect()
    n = conn.execute(
        "SELECT COUNT(*) FROM notificaciones_aliado WHERE tipo = ?", (rc.TIPO_NOTIFICACION,)
    ).fetchone()[0]
    conn.close()
    assert n == 0
    src = (Path(rc.__file__)).read_text(encoding="utf-8")
    bp = (WEB / "blueprints/red_centro_bp.py").read_text(encoding="utf-8")
    assert "entregar_notificacion_verificada" not in bp
    # Dentro del servicio solo se define, no se llama desde activar/aviso.
    assert src.count("entregar_notificacion_verificada(") == 1


# --- Aislamiento de reglas -------------------------------------------------------------

def test_piloto_solo_escribe_en_sus_tablas(sqlite_db, piloto_on):
    _poblar_red(sqlite_db)
    antes = _dump_no_piloto(sqlite_db)
    rc.activar(sqlite_db, "ADMIN")
    rc.estado(sqlite_db)
    rc.aviso_para_aliado(sqlite_db, "20521")
    rc.registrar_accion_aviso(sqlite_db, "20521", "invitar")
    rc._con_conexion(sqlite_db, lambda c, cur: rc.candidatos_red(sqlite_db, cur, "20521", "Fontanería"))
    rc.incorporar_tras_alta(sqlite_db, "86761")
    rc.revertir(sqlite_db, "ADMIN")
    assert _dump_no_piloto(sqlite_db) == antes


def test_reglas_economicas_score_y_competencia_no_cambian(sqlite_db, piloto_on, monkeypatch):
    from core.financial import money
    from core.services import encargo_externo_service, score_service

    reglas = json.loads((Path(rc.__file__).resolve().parents[2] / "config/ruana_reglas_v1.json").read_text())

    def foto():
        return {
            "apoyo_pct": reglas["apoyo_pct"],
            "comision": money.COMISION_RUANA_PCT,
            "externos": (encargo_externo_service.comision_activada(), encargo_externo_service.COMISION_PCT_POR_DEFECTO),
            "umbral": reglas["umbral_competencia"],
            "estados": [score_service.score_a_estado(s) for s in (0, 14, 15, 49, 50, 199, 200, 349, 350, 500)],
        }

    monkeypatch.delenv("RED_CENTRO_ENABLED")
    apagado = foto()
    monkeypatch.setenv("RED_CENTRO_ENABLED", "1")
    _poblar_red(sqlite_db)
    rc.activar(sqlite_db, "ADMIN")
    assert foto() == apagado
    assert apagado["comision"] == 5 and apagado["apoyo_pct"] == 5.0 and apagado["umbral"] == 15
    # Score, estado, grupo y CP de los miembros intactos tras activar y repartir.
    org0 = _org(sqlite_db)
    solicitud_service.crear_solicitud_por_codigo(sqlite_db, "20521", "Fontanería", "Fuga")
    assert _org(sqlite_db) == org0


def test_servicio_no_contiene_sql_de_escritura_fuera_de_su_capa():
    src = Path(rc.__file__).read_text(encoding="utf-8")
    escrituras = re.findall(r"(INSERT INTO|UPDATE|DELETE FROM)\s+(\w+)", src)
    tablas = {t for _, t in escrituras}
    assert tablas <= {"red_piloto", "red_piloto_miembros", "notificaciones_aliado"}, tablas
    for prohibida in ("aliados", "grupos", "contactos_ruana", "pagos", "competencia", "score_movimientos"):
        assert prohibida not in tablas


# --- Reversión ----------------------------------------------------------------------

def test_reversion_restaura_organizacion_y_conserva_actividad(sqlite_db, piloto_on):
    _poblar_red(sqlite_db)
    org_original = _org(sqlite_db)
    act = rc.activar(sqlite_db, "ADMIN")
    assert act["red"]["snapshot_sha256"] == rc.checksum(org_original)
    # Actividad durante el piloto: alta nueva + encargo por la red + aviso visto.
    _crear(sqlite_db, "33091", "Electricidad", "28026")
    rc.incorporar_tras_alta(sqlite_db, "33091")
    creada = solicitud_service.crear_solicitud_por_codigo(sqlite_db, "20521", "Fontanería", "Fuga")
    solicitud_service.aceptar_proximidad_solicitud(sqlite_db, creada["id"], "20521")
    rc.aviso_para_aliado(sqlite_db, "86761")
    rc.registrar_accion_aviso(sqlite_db, "86761", "aceptar")

    rev = rc.revertir(sqlite_db, "ADMIN")
    assert rev["status"] == "success"
    v = rev["verificacion"]
    assert v["identica"] is True, v["diferencias"]
    assert v["checksum_actual_subconjunto"] == v["checksum_original"] == rc.checksum(org_original)
    assert "33091" in v["altas_conservadas"]
    assert v["miembros_borrados"] == 8
    # Altas, encargos y actividad siguen ahí.
    assert sqlite_db.obtener_aliado_por_codigo("33091")
    propias = solicitud_service.listar_solicitudes_propias_por_codigo(sqlite_db, "20521")
    assert creada["id"] in {s["id"] for s in propias}
    assert "proximidad_solicitud" in _tipos(sqlite_db, creada["proximidad"]["codigo"])
    # Capa del piloto vacía y red marcada como revertida.
    conn = sqlite_db._connect()
    assert conn.execute("SELECT COUNT(*) FROM red_piloto_miembros").fetchone()[0] == 0
    assert conn.execute("SELECT estado FROM red_piloto").fetchone()[0] == "revertida"
    conn.close()
    # El reparto vuelve al comportamiento original y el aviso deja de salir.
    nueva = solicitud_service.crear_solicitud_por_codigo(sqlite_db, "86761", "Fontanería", "Otra")
    assert nueva["enrutamiento"] == "buscando_ayuda"
    assert rc.aviso_para_aliado(sqlite_db, "62318")["mostrar"] is False
    assert rc.revertir(sqlite_db, "ADMIN")["http"] == 404


def test_reversion_detecta_cambios_en_la_organizacion(sqlite_db, piloto_on):
    _poblar_red(sqlite_db)
    rc.activar(sqlite_db, "ADMIN")
    conn = sqlite_db._connect()
    conn.execute("UPDATE aliados SET codigo_postal = '45999' WHERE codigo = '20521'")
    conn.commit()
    conn.close()
    v = rc.revertir(sqlite_db, "ADMIN")["verificacion"]
    assert v["identica"] is False
    assert {"tipo": "aliado_campo", "codigo": "20521", "campo": "codigo_postal",
            "antes": "45500", "ahora": "45999"} in v["diferencias"]
    assert v["checksum_actual_subconjunto"] != v["checksum_original"]


def test_reversion_se_niega_si_la_instantanea_esta_alterada(sqlite_db, piloto_on):
    _poblar_red(sqlite_db)
    rc.activar(sqlite_db, "ADMIN")
    conn = sqlite_db._connect()
    conn.execute("UPDATE red_piloto SET snapshot_sha256 = 'x'")
    conn.commit()
    conn.close()
    r = rc.revertir(sqlite_db, "ADMIN")
    assert r["status"] == "error" and r["http"] == 409
    conn = sqlite_db._connect()
    assert conn.execute("SELECT COUNT(*) FROM red_piloto_miembros").fetchone()[0] == 7
    conn.close()


# --- Admin API -------------------------------------------------------------------------

def test_admin_api_estado_activar_revertir(client, sqlite_db, monkeypatch, session_headers, piloto_on):
    monkeypatch.setattr(app_module, "get_db", lambda: sqlite_db)
    _poblar_red(sqlite_db)
    lectura = session_headers("admin", "ADMIN001", permisos=["leer"])
    escritura = session_headers("admin", "ADMIN001", permisos=["leer", "escribir"])
    assert client.post("/api/admin/red-centro/activar", headers=lectura).status_code == 403
    r = client.post("/api/admin/red-centro/activar", headers=escritura)
    assert r.status_code == 200, r.get_json()
    est = client.get("/api/admin/red-centro", headers=lectura).get_json()
    assert est["operativa"] is True and len(est["miembros"]) == 7
    pl = client.get("/api/admin/red-centro/plantilla-notificacion", headers=lectura).get_json()
    assert pl["envio_masivo"] is False
    rv = client.post("/api/admin/red-centro/revertir", headers=escritura).get_json()
    assert rv["verificacion"]["identica"] is True
    sin_sesion = client.get("/api/admin/red-centro")
    assert sin_sesion.status_code in (401, 403)


# --- Modal de bienvenida (API) -----------------------------------------------------------

def test_modal_una_sola_vez_y_persistente_entre_sesiones(client, sqlite_db, monkeypatch, session_headers, piloto_on):
    monkeypatch.setattr(app_module, "get_db", lambda: sqlite_db)
    _poblar_red(sqlite_db)
    rc.activar(sqlite_db, "ADMIN")
    movil = session_headers("aliado", "20521")
    r = client.get("/api/aliado/red-centro/aviso", headers=movil).get_json()
    assert r["mostrar"] is True
    assert client.post("/api/aliado/red-centro/aviso", json={"accion": "cerrar"}, headers=movil).get_json()["registrado"] is True
    assert client.get("/api/aliado/red-centro/aviso", headers=movil).get_json()["mostrar"] is False
    # Otro dispositivo / nueva sesión: tampoco.
    escritorio = session_headers("aliado", "20521")
    assert client.get("/api/aliado/red-centro/aviso", headers=escritorio).get_json()["mostrar"] is False
    # Repetir la acción no reescribe la primera.
    assert client.post("/api/aliado/red-centro/aviso", json={"accion": "aceptar"}, headers=escritorio).get_json()["registrado"] is False
    conn = sqlite_db._connect()
    acc = conn.execute("SELECT aviso_red_centro_accion FROM red_piloto_miembros WHERE aliado_codigo='20521'").fetchone()[0]
    conn.close()
    assert acc == "cerrar"


@pytest.mark.parametrize("accion", ["aceptar", "recomendar", "invitar"])
def test_modal_acciones_marcan_visto(client, sqlite_db, monkeypatch, session_headers, piloto_on, accion):
    monkeypatch.setattr(app_module, "get_db", lambda: sqlite_db)
    _poblar_red(sqlite_db)
    rc.activar(sqlite_db, "ADMIN")
    h = session_headers("aliado", "86761")
    assert client.get("/api/aliado/red-centro/aviso", headers=h).get_json()["mostrar"] is True
    assert client.post("/api/aliado/red-centro/aviso", json={"accion": accion}, headers=h).get_json()["registrado"] is True
    assert client.get("/api/aliado/red-centro/aviso", headers=h).get_json()["mostrar"] is False


def test_modal_cerrar_no_cambia_estado_ni_permisos(client, sqlite_db, monkeypatch, session_headers, piloto_on):
    monkeypatch.setattr(app_module, "get_db", lambda: sqlite_db)
    _poblar_red(sqlite_db)
    rc.activar(sqlite_db, "ADMIN")
    antes = _dump_no_piloto(sqlite_db)
    h = session_headers("aliado", "62318")
    client.get("/api/aliado/red-centro/aviso", headers=h)
    client.post("/api/aliado/red-centro/aviso", json={"accion": "cerrar"}, headers=h)
    despues = _dump_no_piloto(sqlite_db)
    # Solo puede cambiar el registro de accesos/telemetría, nunca aliados ni grupos.
    for t in ("aliados", "grupos", "contactos_ruana", "solicitudes"):
        if t in antes:
            assert despues[t] == antes[t], t


def test_modal_nuevo_registrado_durante_piloto_lo_ve(client, sqlite_db, monkeypatch, session_headers, piloto_on):
    monkeypatch.setattr(app_module, "get_db", lambda: sqlite_db)
    _poblar_red(sqlite_db)
    rc.activar(sqlite_db, "ADMIN")
    _crear(sqlite_db, "36656", "Pintura y decoración", "28703")
    h = session_headers("aliado", "36656")
    assert client.get("/api/aliado/red-centro/aviso", headers=h).get_json()["mostrar"] is True
    assert "36656" in rc.estado(sqlite_db)["miembros"]


@pytest.mark.parametrize("codigo", ["26053", "49854", "45999"])
def test_modal_no_se_muestra_a_ajenos_ni_no_validados(client, sqlite_db, monkeypatch, session_headers, piloto_on, codigo):
    monkeypatch.setattr(app_module, "get_db", lambda: sqlite_db)
    _poblar_red(sqlite_db)
    rc.activar(sqlite_db, "ADMIN")
    h = session_headers("aliado", codigo)
    r = client.get("/api/aliado/red-centro/aviso", headers=h)
    if r.status_code == 200:
        assert r.get_json()["mostrar"] is False
    else:
        assert r.status_code in (401, 403)
    assert codigo not in rc.estado(sqlite_db)["miembros"]


def test_modal_flag_de_aviso_y_flag_maestro(client, sqlite_db, monkeypatch, session_headers, piloto_on):
    monkeypatch.setattr(app_module, "get_db", lambda: sqlite_db)
    _poblar_red(sqlite_db)
    rc.activar(sqlite_db, "ADMIN")
    h = session_headers("aliado", "20521")
    monkeypatch.setenv("RED_CENTRO_AVISO_ENABLED", "0")
    assert client.get("/api/aliado/red-centro/aviso", headers=h).get_json()["mostrar"] is False
    monkeypatch.setenv("RED_CENTRO_AVISO_ENABLED", "1")
    monkeypatch.setenv("RED_CENTRO_ENABLED", "0")
    assert client.get("/api/aliado/red-centro/aviso", headers=h).get_json()["mostrar"] is False


def test_modal_fail_open_si_falla_el_backend(client, sqlite_db, monkeypatch, session_headers, piloto_on):
    monkeypatch.setattr(app_module, "get_db", lambda: sqlite_db)
    _poblar_red(sqlite_db)
    rc.activar(sqlite_db, "ADMIN")

    def boom(*a, **k):
        raise RuntimeError("BD caída")

    monkeypatch.setattr(rc, "red_activa", boom)
    r = client.get("/api/aliado/red-centro/aviso", headers=session_headers("aliado", "20521"))
    assert r.status_code == 200 and r.get_json()["mostrar"] is False


def test_modal_accion_invalida_y_sin_sesion(client, sqlite_db, monkeypatch, session_headers, piloto_on):
    monkeypatch.setattr(app_module, "get_db", lambda: sqlite_db)
    _poblar_red(sqlite_db)
    rc.activar(sqlite_db, "ADMIN")
    h = session_headers("aliado", "20521")
    assert client.post("/api/aliado/red-centro/aviso", json={"accion": "borrar"}, headers=h).status_code == 400
    assert client.get("/api/aliado/red-centro/aviso").status_code in (401, 403)


# --- Modal de bienvenida (contrato de frontend) -------------------------------------------

TEXTO_EXACTO = [
    "🤝 ¡Juntos conseguimos más trabajo!",
    "¡Hola, aliado! 👋",
    "Tenemos una novedad en RUANA.",
    "Estamos conectando a los profesionales de Madrid y Toledo para que tengáis más oportunidades de conseguir trabajos.",
    "🔄 ¿Cómo funciona?",
    "Muy sencillo:",
    "Si te llega un trabajo que no puedes realizar porque es de otro oficio, recomiéndaselo a un compañero de RUANA.",
    "Y cuando a ese compañero le llegue un trabajo de tu especialidad, podrá recomendártelo a ti.",
    "<strong>Hoy recomiendas tú, mañana te recomiendan a ti.</strong>",
    "🚀 ¡Ayúdanos a hacer crecer la red!",
    "Dentro de RUANA tienes dos herramientas fundamentales:",
    "<strong>🔧 RECOMENDAR:</strong> comparte trabajos con otros aliados. No dejes perder una oportunidad porque no sea de tu oficio.",
    "<strong>👥 INVITAR:</strong> invita a profesionales de confianza, especialmente de otros oficios. Cuantos más aliados activos tengamos, más posibilidades habrá de recibir recomendaciones.",
    "<strong>No esperes solamente a que te lleguen trabajos. Participa, recomienda e invita.</strong>",
    "Tu oficio, tu zona y tus condiciones siguen siendo los mismos. Solo estamos ampliando temporalmente las oportunidades de colaboración.",
    "<strong>RUANA funciona cuando nos ayudamos entre todos. 💪</strong>",
]


def test_modal_frontend_texto_exacto_y_botones():
    js = (WEB / "static/js/aliado-red-centro-module.js").read_text(encoding="utf-8")
    for linea in TEXTO_EXACTO:
        assert linea in js, linea
    for etiqueta in ("Entendido, ¡vamos allá!", "Recomendar trabajo", "Invitar aliado", "✕"):
        assert etiqueta in js
    assert 'role="dialog"' in js and 'aria-modal="true"' in js
    # Fail-open: errores capturados, solo se muestra con mostrar === true.
    assert "d.mostrar === true" in js and ".catch(" in js


def test_modal_reutiliza_funciones_existentes():
    js = (WEB / "static/js/aliado-red-centro-module.js").read_text(encoding="utf-8")
    html = (WEB / "aliado.html").read_text(encoding="utf-8")
    assert "AliadoShell.show('conexiones')" in js
    assert 'data-aliado-goto="conexiones"' in html
    assert 'id="nueva-solicitud-oficio"' in html
    assert "btn-invitar-global" in js and 'id="btn-invitar-global"' in html
    assert 'data-action="invitar-aliado"' in html
    assert "/static/js/aliado-red-centro-module.js" in html
    assert "/static/css/aliado-red-centro.css" in html


def test_modal_css_responsive_y_scroll_interno():
    css = (WEB / "static/css/aliado-red-centro.css").read_text(encoding="utf-8")
    assert "overflow-y: auto" in css
    assert "@media (max-width: 560px)" in css
    assert "position: fixed" in css and "max-height" in css


# --- Script de instantánea (funciones puras; sin red) -------------------------------------

def _script():
    import importlib.util
    p = Path(__file__).resolve().parents[1] / "scripts" / "red_centro_snapshot.py"
    spec = importlib.util.spec_from_file_location("red_centro_snapshot", p)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_script_snapshot_elegibles_checksum_y_comparacion():
    s = _script()
    al = [
        {"codigo": "20521", "oficio": "Electricidad", "codigo_postal": "45500", "grupo_id": 12, "estado": "activo", "email": "x@y"},
        {"codigo": "26053", "oficio": "Carpintería", "codigo_postal": "03380", "grupo_id": 7, "estado": "activo"},
        {"codigo": "45999", "oficio": "Fontanería", "codigo_postal": "45600", "grupo_id": None, "estado": "pendiente_validacion"},
    ]
    gr = [{"id": 12, "codigo_postal": "45500", "estado": "activo"}]
    org = s.organizar(al, gr, [])
    assert "email" not in org["aliados"][0]
    assert s.elegibles(org) == ["20521"]
    assert s.sha(org) == s.sha(s.organizar(list(reversed(al)), gr, []))
    assert s.comparar(org, org) == []
    al2 = [dict(a) for a in al] + [{"codigo": "99999", "codigo_postal": "28001", "estado": "activo", "grupo_id": 1}]
    al2[0]["grupo_id"] = 99
    dif = s.comparar(org, s.organizar(al2, gr, []))
    assert dif == ["aliados:20521.grupo_id: 12 -> 99"]
