"""Misión Maestra: blueprints llaman services de dominio (no fachadas DBManager)."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from core.services import (
    admin_service,
    aliado_service,
    chat_service,
    contacto_service,
    evaluacion_service,
    invitacion_service,
    negociacion_service,
    notificacion_service,
    pago_service,
    referido_service,
    solicitud_service,
)
from web.blueprints import admin_bp as admin_bp_mod
from web.blueprints import aliado_bp as aliado_bp_mod
from web.blueprints import auth_bp as auth_bp_mod
from web.blueprints import contactos_bp as contactos_bp_mod
from web.blueprints import evaluacion_bp as evaluacion_bp_mod
from web.blueprints import invitacion_bp as invitacion_bp_mod
from web.blueprints import negociacion_bp as negociacion_bp_mod
from web.blueprints import pagos_bp as pagos_bp_mod
from web.blueprints import referidos_bp as referidos_bp_mod
from web.blueprints import solicitudes_bp as solicitudes_bp_mod
from web.blueprints import soporte_bp as soporte_bp_mod


BLUEPRINTS_DIR = Path(__file__).resolve().parents[1] / "web" / "blueprints"


def _source(name: str) -> str:
    return (BLUEPRINTS_DIR / name).read_text(encoding="utf-8")


def test_contactos_bp_importa_y_usa_contacto_service():
    src = _source("contactos_bp.py")
    assert "from core.services import" in src
    assert "contacto_service" in src
    assert "contacto_service.crear_contacto_ruana" in src
    assert "db.crear_contacto_ruana(" not in src
    assert hasattr(contactos_bp_mod, "contacto_service")
    assert contactos_bp_mod.contacto_service is contacto_service


def test_solicitudes_bp_importa_y_usa_solicitud_service():
    src = _source("solicitudes_bp.py")
    assert "solicitud_service" in src
    assert "solicitud_service.crear_solicitud_por_codigo" in src
    assert "db.crear_solicitud_por_codigo(" not in src
    assert hasattr(solicitudes_bp_mod, "solicitud_service")
    assert solicitudes_bp_mod.solicitud_service is solicitud_service


def test_evaluacion_bp_importa_y_usa_evaluacion_service():
    src = _source("evaluacion_bp.py")
    assert "evaluacion_service" in src
    assert "evaluacion_service.obtener_evaluacion" in src
    assert "db.obtener_evaluacion(" not in src
    assert hasattr(evaluacion_bp_mod, "evaluacion_service")
    assert evaluacion_bp_mod.evaluacion_service is evaluacion_service


def test_aliado_bp_notificaciones_usan_notificacion_service():
    src = _source("aliado_bp.py")
    assert "notificacion_service" in src
    assert "notificacion_service.listar_notificaciones_aliado" in src
    assert "notificacion_service.marcar_notificacion_leida" in src
    assert "db.listar_notificaciones_aliado(" not in src
    assert "db.marcar_notificacion_leida(" not in src
    assert hasattr(aliado_bp_mod, "notificacion_service")
    assert aliado_bp_mod.notificacion_service is notificacion_service


def test_contactos_bp_crear_contacto_llama_service(monkeypatch, session_headers, client):
    """Monkeypatch: POST /api/contactos debe invocar contacto_service, no db.crear_contacto_ruana."""
    called = {}

    def _fake_crear(db, **kwargs):
        called["ok"] = True
        called["db"] = db
        called["kwargs"] = kwargs
        return {
            "status": "success",
            "id": 99,
            "estado": "iniciado",
            "solicitante_codigo": kwargs.get("solicitante_codigo"),
            "profesional_codigo": kwargs.get("profesional_codigo"),
        }

    class _FakeDb:
        def crear_contacto_ruana(self, *a, **k):
            raise AssertionError("No debe usarse fachada DBManager.crear_contacto_ruana")

    monkeypatch.setattr(contactos_bp_mod, "get_db", lambda: _FakeDb())
    monkeypatch.setattr(contacto_service, "crear_contacto_ruana", _fake_crear)
    monkeypatch.setattr(contactos_bp_mod.contacto_service, "crear_contacto_ruana", _fake_crear)

    headers = session_headers("aliado", "81001")
    resp = client.post(
        "/api/contactos",
        headers=headers,
        json={
            "profesional_codigo": "81002",
            "servicio": "Fontanería",
            "motivo_contacto": "Presupuesto",
        },
    )
    data = resp.get_json()
    assert resp.status_code == 201, data
    assert called.get("ok") is True
    assert called["kwargs"]["profesional_codigo"] == "81002"
    assert data.get("id") == 99


def test_solicitudes_bp_crear_llama_service(monkeypatch, session_headers, client):
    called = {}

    def _fake_crear(db, codigo, oficio, descripcion):
        called["ok"] = True
        called["codigo"] = codigo
        called["oficio"] = oficio
        return {"status": "success", "id": 7}

    class _FakeDb:
        def crear_solicitud_por_codigo(self, *a, **k):
            raise AssertionError("No debe usarse fachada DBManager")

    monkeypatch.setattr(solicitudes_bp_mod, "get_db", lambda: _FakeDb())
    monkeypatch.setattr(
        solicitudes_bp_mod.solicitud_service, "crear_solicitud_por_codigo", _fake_crear
    )

    headers = session_headers("aliado", "81001")
    resp = client.post(
        "/api/solicitudes",
        headers=headers,
        json={"oficio": "Fontanería", "descripcion": "Necesito ayuda urgente"},
    )
    data = resp.get_json()
    assert resp.status_code == 200, data
    assert called.get("ok") is True
    assert data.get("id") == 7


def test_evaluacion_bp_obtener_llama_service(monkeypatch, session_headers, client):
    called = {}

    def _fake_obtener(db, codigo_aliado):
        called["ok"] = True
        called["codigo"] = codigo_aliado
        return {"codigo_aliado": codigo_aliado, "estado": "verde", "score": 100}

    class _FakeDb:
        def obtener_evaluacion(self, *a, **k):
            raise AssertionError("No debe usarse fachada DBManager")

    monkeypatch.setattr(evaluacion_bp_mod, "get_db", lambda: _FakeDb())
    monkeypatch.setattr(
        evaluacion_bp_mod.evaluacion_service, "obtener_evaluacion", _fake_obtener
    )

    headers = session_headers("aliado", "81001")
    resp = client.get("/api/evaluaciones/81001", headers=headers)
    data = resp.get_json()
    assert resp.status_code == 200, data
    assert called.get("ok") is True
    assert data["evaluacion"]["estado"] == "verde"


def test_negociacion_bp_importa_y_usa_negociacion_service():
    src = _source("negociacion_bp.py")
    assert "negociacion_service" in src
    assert "negociacion_service.obtener_negociacion_contacto" in src
    assert "db.obtener_negociacion_contacto(" not in src
    assert hasattr(negociacion_bp_mod, "negociacion_service")
    assert negociacion_bp_mod.negociacion_service is negociacion_service


def test_pagos_bp_importa_y_usa_pago_service():
    src = _source("pagos_bp.py")
    assert "pago_service" in src
    assert "pago_service.obtener_metodos_pago_ruana" in src
    assert "db.obtener_metodos_pago_ruana(" not in src
    assert hasattr(pagos_bp_mod, "pago_service")
    assert pagos_bp_mod.pago_service is pago_service


def test_referidos_bp_importa_y_usa_referido_service():
    src = _source("referidos_bp.py")
    assert "referido_service" in src
    assert "referido_service.obtener_arbol_referidos" in src
    assert "db.obtener_arbol_referidos(" not in src
    assert hasattr(referidos_bp_mod, "referido_service")
    assert referidos_bp_mod.referido_service is referido_service


def test_invitacion_bp_importa_y_usa_invitacion_service():
    src = _source("invitacion_bp.py")
    assert "invitacion_service" in src
    assert "invitacion_service.generar_invitacion_oficio" in src
    assert "db.generar_invitacion_oficio(" not in src
    assert hasattr(invitacion_bp_mod, "invitacion_service")
    assert invitacion_bp_mod.invitacion_service is invitacion_service


def test_soporte_bp_importa_y_usa_chat_y_admin_service():
    src = _source("soporte_bp.py")
    assert "chat_service" in src
    assert "admin_service" in src
    assert "chat_service.listar_mensajes_soporte_admin" in src
    assert "db.listar_mensajes_soporte_admin(" not in src
    assert hasattr(soporte_bp_mod, "chat_service")
    assert soporte_bp_mod.chat_service is chat_service


def test_auth_bp_importa_y_usa_aliado_e_invitacion_service():
    src = _source("auth_bp.py")
    assert "aliado_service" in src
    assert "invitacion_service" in src
    assert "aliado_service.obtener_aliado_por_codigo" in src
    assert "db.obtener_aliado_por_codigo(" not in src
    assert hasattr(auth_bp_mod, "aliado_service")
    assert auth_bp_mod.aliado_service is aliado_service


def test_admin_bp_usa_services_claros():
    src = _source("admin_bp.py")
    assert "admin_service" in src
    assert "admin_service.obtener_health_metrics_admin" in src
    assert "pago_service.listar_payment_conflicts_admin" in src
    assert "db.obtener_health_metrics_admin(" not in src
    assert hasattr(admin_bp_mod, "admin_service")
    assert admin_bp_mod.admin_service is admin_service


def test_blueprints_objetivo_sin_fachadas_dominio_en_ast():
    """AST: no deben quedar Attribute calls db.<metodo_dominio> en blueprints refactorizados."""
    forbidden_by_file = {
        "contactos_bp.py": {
            "crear_contacto_ruana",
            "aceptar_contacto_ruana",
            "ocultar_contacto_del_panel",
            "marcar_trabajo_en_progreso",
            "marcar_cerrado_no_concretado",
            "marcar_en_conversacion",
            "registrar_importe_contacto",
            "obtener_contactos_abiertos_por_codigo",
            "obtener_contacto_resumen",
            "obtener_metricas_contactos",
            "tiene_pagos_ruana_pendientes",
            "listar_contactos_pago_pendiente_profesional",
            "subir_comprobante_apoyo_ruana",
            "impugnar_apoyo_ruana",
        },
        "solicitudes_bp.py": {
            "listar_solicitudes_activas_por_codigo",
            "listar_solicitudes_propias_por_codigo",
            "listar_solicitudes_historial_grupo_por_codigo",
            "crear_solicitud_por_codigo",
            "atender_solicitud_por_id",
            "marcar_solicitud_atendida_por_admin",
        },
        "evaluacion_bp.py": {
            "obtener_evaluacion",
            "listar_evaluaciones",
            "obtener_historico_evaluaciones",
            "obtener_estadisticas_evaluaciones",
        },
        "negociacion_bp.py": {
            "obtener_negociacion_contacto",
            "proponer_negociacion",
            "proponer_propuesta_completa_negociacion",
            "aceptar_negociacion",
            "contraoferta_negociacion",
            "cerrar_negociacion",
            "dismiss_resumen_acuerdo",
            "listar_acuerdos_aliado",
            "listar_resumenes_acuerdo_visibles",
        },
        "pagos_bp.py": {
            "obtener_metodos_pago_ruana",
            "actualizar_metodos_pago_ruana",
            "resolver_payment_conflict_admin",
            "obtener_payment_conflict_por_trabajo",
            "subir_prueba_conflicto",
            "resolver_conflicto_pago",
            "actualizar_estado_pago_contacto",
        },
        "referidos_bp.py": {
            "obtener_arbol_referidos",
            "obtener_invitador_de",
            "obtener_bosques_referidos",
            "listar_nodos_raiz_referidos",
            "obtener_resumen_referidos_red",
            "obtener_nodo_referidos",
            "listar_referidos_directos",
            "obtener_ruta_referidos_hacia_arriba",
            "buscar_en_red_referidos",
            "aliado_puede_ver_nodo_referidos",
            "contar_referidos_por_codigo",
            "listar_referidos_desde",
            "obtener_linaje_aliado",
            "listar_hijos_directos_linaje",
        },
        "invitacion_bp.py": {
            "generar_invitacion_oficio",
            "crear_campana_invitacion",
            "desactivar_campana_invitacion",
            "_registrar_invitacion",
            "obtener_aliado_por_codigo",
            "obtener_o_crear_invitador_admin",
            "marcar_solicitud_candidato_pendiente",
        },
        "soporte_bp.py": {
            "listar_conversaciones_soporte_admin",
            "listar_mensajes_soporte_admin",
            "listar_conversaciones_soporte_aliado",
            "crear_conversacion_soporte_aliado",
            "listar_mensajes_soporte_aliado",
            "enviar_mensaje_soporte_aliado",
            "marcar_soporte_leido_aliado",
            "responder_soporte_admin",
            "actualizar_estado_soporte_admin",
            "eliminar_conversacion_soporte_admin",
        },
        "auth_bp.py": {
            "obtener_aliado_por_codigo",
            "registrar_acceso_login",
            "validar_invitacion_oficio",
            "validar_campana_invitacion",
            "obtener_campana_invitacion",
            "obtener_invitacion_pendiente",
        },
        "admin_bp.py": {
            "obtener_health_metrics_admin",
            "obtener_stats_24h_panel",
            "listar_invitaciones_recientes",
            "obtener_metricas_contactos",
            "listar_payment_conflicts_admin",
            "obtener_movimiento_24h",
            "obtener_metricas_salud",
            "purga_mensual",
            "eliminar_negociacion_admin",
        },
    }
    for filename, forbidden in forbidden_by_file.items():
        tree = ast.parse(_source(filename))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                if (
                    isinstance(node.func.value, ast.Name)
                    and node.func.value.id == "db"
                    and node.func.attr in forbidden
                ):
                    pytest.fail(f"{filename}: aún llama db.{node.func.attr}()")


def test_negociacion_bp_obtener_llama_service(monkeypatch, session_headers, client):
    called = {}

    def _fake(db, contacto_id, codigo):
        called["ok"] = True
        called["contacto_id"] = contacto_id
        return {"status": "success", "contacto_id": contacto_id}

    class _FakeDb:
        def obtener_negociacion_contacto(self, *a, **k):
            raise AssertionError("No debe usarse fachada DBManager")

    monkeypatch.setattr(negociacion_bp_mod, "get_db", lambda: _FakeDb())
    monkeypatch.setattr(
        negociacion_bp_mod.negociacion_service, "obtener_negociacion_contacto", _fake
    )

    headers = session_headers("aliado", "81001")
    resp = client.get("/api/contactos/1/negociacion", headers=headers)
    data = resp.get_json()
    assert resp.status_code == 200, data
    assert called.get("ok") is True


def test_pagos_bp_metodos_llama_service(monkeypatch, session_headers, client):
    called = {}

    def _fake(db):
        called["ok"] = True
        return {"bizum_num": "600000000", "iban": ""}

    class _FakeDb:
        def obtener_metodos_pago_ruana(self, *a, **k):
            raise AssertionError("No debe usarse fachada DBManager")

    monkeypatch.setattr(pagos_bp_mod, "get_db", lambda: _FakeDb())
    monkeypatch.setattr(pagos_bp_mod.pago_service, "obtener_metodos_pago_ruana", _fake)

    headers = session_headers("aliado", "81001")
    resp = client.get("/api/metodos-pago", headers=headers)
    data = resp.get_json()
    assert resp.status_code == 200, data
    assert called.get("ok") is True
    assert data["metodos"]["bizum_num"] == "600000000"


def test_services_exportados_disponibles():
    assert callable(contacto_service.crear_contacto_ruana)
    assert callable(solicitud_service.crear_solicitud_por_codigo)
    assert callable(evaluacion_service.obtener_evaluacion)
    assert callable(notificacion_service.listar_notificaciones_aliado)
    assert callable(pago_service.tiene_pagos_ruana_pendientes)
    assert callable(admin_service.obtener_metricas_contactos)
    assert callable(negociacion_service.obtener_negociacion_contacto)
    assert callable(referido_service.obtener_arbol_referidos)
    assert callable(invitacion_service.generar_invitacion_oficio)
    assert callable(chat_service.listar_mensajes_soporte_admin)
    assert callable(aliado_service.obtener_aliado_por_codigo)
