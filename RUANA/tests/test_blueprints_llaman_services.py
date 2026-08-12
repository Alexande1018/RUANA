"""Misión Maestra: blueprints llaman services de dominio (no fachadas DBManager)."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from core.services import (
    admin_service,
    contacto_service,
    evaluacion_service,
    notificacion_service,
    pago_service,
    solicitud_service,
)
from web.blueprints import aliado_bp as aliado_bp_mod
from web.blueprints import contactos_bp as contactos_bp_mod
from web.blueprints import evaluacion_bp as evaluacion_bp_mod
from web.blueprints import solicitudes_bp as solicitudes_bp_mod


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


def test_services_exportados_disponibles():
    assert callable(contacto_service.crear_contacto_ruana)
    assert callable(solicitud_service.crear_solicitud_por_codigo)
    assert callable(evaluacion_service.obtener_evaluacion)
    assert callable(notificacion_service.listar_notificaciones_aliado)
    assert callable(pago_service.tiene_pagos_ruana_pendientes)
    assert callable(admin_service.obtener_metricas_contactos)
