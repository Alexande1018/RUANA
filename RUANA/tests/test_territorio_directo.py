"""
Fase 3: migración territorial, directorio, proximidad, flujos y ausencia de Grupo Madre.
"""
from pathlib import Path
from types import SimpleNamespace

import pytest

from core import db_manager as db_module
from core.db_constants import TIPO_GRUPO_MADRE
from core.services import (
    notificacion_service,
    proximidad_service,
    solicitud_service,
    territorio_migracion_service,
)
from RUANA.web import app as app_module


ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def sqlite_db(tmp_path, monkeypatch):
    monkeypatch.setattr(
        db_module,
        "get_settings",
        lambda: SimpleNamespace(postgres_configured=False, database_url=""),
    )
    return db_module.DBManager(str(tmp_path / "ruana_territorio_directo.db"))


def _crear(db, codigo, oficio="Electricidad", cp="03001", estado="activo"):
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
    return r


def _insertar_grupo_madre(db, ciudad="Alicante"):
    conn = db._connect()
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO grupos (nombre, codigo_postal, ciudad, provincia, estado, tipo)
        VALUES (?, '__MADRE__', ?, ?, 'activo', 'madre')
        """,
        (f"Grupo Madre {ciudad}", ciudad, ciudad),
    )
    gid = cur.lastrowid
    conn.commit()
    conn.close()
    return gid


def _forzar_grupo(db, codigo, grupo_id, codigo_postal=None):
    conn = db._connect()
    if codigo_postal is None:
        conn.execute("UPDATE aliados SET grupo_id = ? WHERE codigo = ?", (grupo_id, codigo))
    else:
        conn.execute(
            "UPDATE aliados SET grupo_id = ?, codigo_postal = ? WHERE codigo = ?",
            (grupo_id, codigo_postal, codigo),
        )
    conn.commit()
    conn.close()


def test_aliado_antiguo_en_madre_migra_a_territorial_de_su_cp(sqlite_db):
    madre_id = _insertar_grupo_madre(sqlite_db)
    _crear(sqlite_db, "80001", oficio="Electricidad", cp="03001")
    score_antes = sqlite_db.obtener_aliado_por_codigo("80001")["score"]
    _forzar_grupo(sqlite_db, "80001", madre_id)
    assert sqlite_db.obtener_grupo_por_id(
        sqlite_db.obtener_aliado_por_codigo("80001")["grupo_id"]
    )["tipo"] == TIPO_GRUPO_MADRE

    result = territorio_migracion_service.migrar_madre_a_territorial(sqlite_db)
    assert result["status"] == "ok"
    assert result["migrados"] >= 1

    aliado = sqlite_db.obtener_aliado_por_codigo("80001")
    grupo = sqlite_db.obtener_grupo_por_id(aliado["grupo_id"])
    assert grupo["tipo"] == "territorial"
    assert grupo["codigo_postal"] == "03001"
    assert aliado["score"] == score_antes
    assert aliado["codigo"] == "80001"

    check = territorio_migracion_service.comprobar_migracion(sqlite_db)
    assert all(a.get("codigo") != "80001" for a in check["sin_grupo_territorial_valido"])


def test_aliado_sin_codigo_postal_no_se_inventa_destino(sqlite_db):
    madre_id = _insertar_grupo_madre(sqlite_db)
    _crear(sqlite_db, "80002", cp="03001")
    _forzar_grupo(sqlite_db, "80002", madre_id, codigo_postal="")

    result = territorio_migracion_service.migrar_madre_a_territorial(sqlite_db)
    assert result["sin_codigo_postal"] >= 1

    aliado = sqlite_db.obtener_aliado_por_codigo("80002")
    assert aliado["grupo_id"] == madre_id
    informe = territorio_migracion_service.comprobar_migracion(sqlite_db)
    casos = {row.get("codigo"): row.get("caso") for row in informe.get("informe") or []}
    assert casos.get("80002") == "sin_codigo_postal"


def test_migracion_reversible_restaura_grupo_madre(sqlite_db):
    madre_id = _insertar_grupo_madre(sqlite_db)
    _crear(sqlite_db, "80003", cp="03001")
    _forzar_grupo(sqlite_db, "80003", madre_id)
    territorio_migracion_service.migrar_madre_a_territorial(sqlite_db)
    revert = territorio_migracion_service.revertir_migracion_territorio(sqlite_db)
    assert revert["status"] == "ok"
    assert revert["restaurados"] >= 1
    aliado = sqlite_db.obtener_aliado_por_codigo("80003")
    assert aliado["grupo_id"] == madre_id


def test_directorio_limitado_al_grupo_territorial(sqlite_db):
    _crear(sqlite_db, "81001", oficio="Electricidad", cp="03001")
    _crear(sqlite_db, "81002", oficio="Cerrajería", cp="03001")
    _crear(sqlite_db, "81003", oficio="Fontanería y fontanería-gas", cp="03003")

    dir_a = {a["codigo"] for a in sqlite_db.listar_aliados_directorio_grupo("81001")}
    assert "81002" in dir_a
    assert "81003" not in dir_a
    dir_b = {a["codigo"] for a in sqlite_db.listar_aliados_directorio_grupo("81003")}
    assert "81001" not in dir_b


def test_recomendacion_por_proximidad_y_notificacion(sqlite_db):
    _crear(sqlite_db, "82001", oficio="Electricidad", cp="03001")
    _crear(sqlite_db, "82002", oficio="Fontanería y fontanería-gas", cp="03003")

    rec = proximidad_service.recomendar_profesional(
        sqlite_db, "82001", "Fontanería y fontanería-gas"
    )
    assert rec is not None
    assert rec["codigo"] == "82002"
    assert rec["mismo_grupo"] is False

    result = proximidad_service.solicitar_contacto_proximidad(
        sqlite_db, "82001", "Fontanería y fontanería-gas", "82002"
    )
    assert result["status"] == "success"
    assert result["notificado"] is True
    notifs = notificacion_service.listar_notificaciones_aliado(sqlite_db, "82002")
    tipos = {n.get("tipo") for n in notifs}
    assert "proximidad_solicitud" in tipos


def test_solicitud_entre_aliados_y_proximidad_si_falta_oficio(sqlite_db):
    _crear(sqlite_db, "83001", oficio="Electricidad", cp="03001")
    _crear(sqlite_db, "83002", oficio="Fontanería y fontanería-gas", cp="03003")
    creada = solicitud_service.crear_solicitud_por_codigo(
        sqlite_db, "83001", "Fontanería y fontanería-gas", "Fuga en cocina"
    )
    assert creada["status"] == "success"
    assert creada.get("id")
    assert creada.get("proximidad", {}).get("codigo") == "83002"

    pendientes = solicitud_service.obtener_solicitudes_operativas(sqlite_db, "83001")
    ids = {s.get("id") for s in pendientes}
    assert creada["id"] in ids


def test_cierre_encargo_confirmacion_pago_12_y_mensajes(sqlite_db):
    _crear(sqlite_db, "84001", oficio="Electricidad", cp="03001")
    _crear(sqlite_db, "84002", oficio="Cerrajería", cp="03001")
    creado = sqlite_db.crear_contacto_ruana(
        "84001", "84002", servicio="Cerradura", motivo_contacto="Test"
    )
    assert creado["status"] == "success"
    cid = creado["id"]
    aceptado = sqlite_db.aceptar_contacto_ruana(cid, "84002")
    assert aceptado["status"] == "success"

    msg = sqlite_db.enviar_mensaje_chat(cid, "84001", "Hola, ¿puedes venir?")
    assert msg["status"] == "success"

    cerrado = sqlite_db.registrar_importe_contacto(
        cid, "solicitante", 100.0, usuario="84001"
    )
    assert cerrado["status"] == "success"
    contacto = sqlite_db.obtener_contacto_por_id(cid)
    assert contacto["apoyo_ruana"] == 12.0
    assert contacto["comision_porcentaje"] == 0.12

    notifs = notificacion_service.listar_notificaciones_aliado(sqlite_db, "84002")
    assert isinstance(notifs, list)


def test_ausencia_total_de_logica_grupo_madre():
    assert not (ROOT / "core/services/grupo_madre_service.py").exists()
    assert not (ROOT / "core/repositories/grupo_madre_repo.py").exists()
    prohibidos = (
        "obtener_o_crear_grupo_madre",
        "aprobar_independencia_cp",
        "actualizar_madurez_cp",
        "consolidar_territoriales_en_madre",
        "emitir_hitos_madurez_cp",
    )
    textos = []
    for rel in (
        "core/services/grupo_service.py",
        "core/services/aliado_service.py",
        "core/services/solicitud_service.py",
        "core/services/competencia_service.py",
        "core/services/actividad_cinta_service.py",
        "core/db_manager.py",
        "web/blueprints/aliado_bp.py",
        "web/blueprints/admin_bp.py",
    ):
        textos.append((rel, (ROOT / rel).read_text(encoding="utf-8")))
    for nombre in prohibidos:
        for rel, src in textos:
            assert nombre not in src, f"{nombre} sigue en {rel}"
    html_aliado = (ROOT / "web/aliado.html").read_text(encoding="utf-8")
    html_admin = (ROOT / "web/admin.html").read_text(encoding="utf-8")
    assert "Grupo Madre" not in html_aliado
    assert "grupo-madurez-wrap" not in html_aliado
    assert "Grupo Madre" not in html_admin
    assert "tbody-cp-madurez" not in html_admin


def test_proximidad_api_aliado(client, sqlite_db, monkeypatch):
    monkeypatch.setattr(app_module, "get_db", lambda: sqlite_db)
    _crear(sqlite_db, "85001", oficio="Electricidad", cp="03001")
    _crear(sqlite_db, "85002", oficio="Fontanería y fontanería-gas", cp="03003")
    session_id = app_module._ruana_session_create(
        tipo="aliado",
        codigo="85001",
        expires_at=9999999999,
    )
    headers = {app_module.RUANA_SESSION_HEADER: session_id}
    resp = client.get(
        "/api/aliado/proximidad?oficio=Fontanería%20y%20fontanería-gas",
        headers=headers,
    )
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["status"] == "success"
    assert data["proximidad"]["codigo"] == "85002"

    resp2 = client.post(
        "/api/aliado/proximidad/solicitar",
        json={"oficio": "Fontanería y fontanería-gas", "profesional_codigo": "85002"},
        headers=headers,
    )
    assert resp2.status_code == 200
    assert resp2.get_json().get("notificado") is True
