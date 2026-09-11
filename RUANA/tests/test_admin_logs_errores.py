from datetime import datetime, timezone
from types import SimpleNamespace

from web.blueprints.admin_bp import cloud_logging_service as cls


def _entrada_score():
    return SimpleNamespace(
        timestamp=datetime(2026, 9, 11, 12, 0, tzinfo=timezone.utc),
        severity="ERROR",
        payload={
            "message": "Fallo al aplicar cambio de score",
            "extra": {
                "aliado_codigo": "A1001",
                "contacto_id": 44,
                "admin_codigo": "ADMIN001",
                "error": "boom",
            },
            "logger": "core.services.score_service",
            "exc_info": "Traceback (most recent call last):\n  File x\nValueError: boom",
        },
        logger="core.services.score_service",
        insert_id="insert-abc",
    )


def test_parsear_entrada_extra_sin_stack_por_defecto():
    item = cls.parsear_entrada(_entrada_score(), incluir_stack=False)
    assert item["mensaje"] == "Fallo al aplicar cambio de score"
    assert item["severity"] == "ERROR"
    assert item["logger"] == "core.services.score_service"
    assert item["extra"]["aliado_codigo"] == "A1001"
    assert item["extra"]["contacto_id"] == 44
    assert item["insert_id"] == "insert-abc"
    assert "stack" not in item


def test_parsear_entrada_incluye_stack_si_se_pide():
    item = cls.parsear_entrada(_entrada_score(), incluir_stack=True)
    assert "Traceback" in (item.get("stack") or "")


def test_construir_filtro_busca_extra_y_severity():
    filtro = cls.construir_filtro(
        severity="ERROR",
        horas=24,
        aliado_codigo="A1001",
        ahora=datetime(2026, 9, 11, 12, 0, tzinfo=timezone.utc),
    )
    assert 'resource.type="cloud_run_revision"' in filtro
    assert 'resource.labels.service_name="ruana"' in filtro
    assert "severity>=ERROR" in filtro
    assert 'jsonPayload.extra.aliado_codigo="A1001"' in filtro


def test_logs_errores_requiere_admin(client):
    resp = client.get("/api/admin/logs/errores")
    assert resp.status_code == 401
    assert resp.get_json()["status"] == "error"


def test_logs_errores_parsea_extra_desde_cloud_logging(client, session_headers, monkeypatch):
    def fake_listar(*, project_id, filtro, page_size, page_token):
        assert project_id == "ruana-4293f"
        assert 'service_name="ruana"' in filtro
        return [_entrada_score()], "next-token"

    monkeypatch.setattr(cls, "listar_entradas", fake_listar)

    headers = session_headers("admin", "ADMIN001", permisos=["leer"])
    resp = client.get("/api/admin/logs/errores?severity=ERROR&horas=24", headers=headers)
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["status"] == "success"
    assert data["next_page_token"] == "next-token"
    item = data["entradas"][0]
    assert item["extra"]["aliado_codigo"] == "A1001"
    assert item["extra"]["contacto_id"] == 44
    assert item["extra"]["admin_codigo"] == "ADMIN001"
    assert "stack" not in item


def test_pagina_desde_iterador_acepta_generador_sin_pages():
    """google-cloud-logging 3.x devuelve un generator, no un pager con .pages."""
    def gen():
        yield _entrada_score()
        yield _entrada_score()

    entradas, token = cls.pagina_desde_iterador(gen(), page_size=1)
    assert len(entradas) == 1
    assert token is None


def test_pagina_desde_iterador_usa_pages_si_existen():
    class Pager:
        next_page_token = "tok-2"

        @property
        def pages(self):
            yield [_entrada_score(), _entrada_score()]

    entradas, token = cls.pagina_desde_iterador(Pager(), page_size=50)
    assert len(entradas) == 2
    assert token == "tok-2"


def test_parsear_entrada_json_payload_estilo_gapic():
    entry = SimpleNamespace(
        timestamp=datetime(2026, 9, 11, 12, 0, tzinfo=timezone.utc),
        severity=SimpleNamespace(name="ERROR"),
        json_payload={
            "message": "Fallo al aplicar cambio de score",
            "extra": {"aliado_codigo": "A1001", "contacto_id": 44},
            "logger": "core.services.score_service",
        },
        text_payload="",
        insert_id="gapic-1",
        log_name="projects/ruana-4293f/logs/python",
        payload=None,
        logger=None,
    )
    item = cls.parsear_entrada(entry, incluir_stack=False)
    assert item["mensaje"] == "Fallo al aplicar cambio de score"
    assert item["severity"] == "ERROR"
    assert item["extra"]["aliado_codigo"] == "A1001"
    assert item["insert_id"] == "gapic-1"
    assert item["logger"] == "core.services.score_service"


def test_logs_errores_permiso_logging_viewer(client, session_headers, monkeypatch):
    class PermissionDenied(Exception):
        pass

    def boom(**_kwargs):
        raise PermissionDenied("403 PERMISSION_DENIED")

    monkeypatch.setattr(cls, "listar_entradas", boom)

    headers = session_headers("admin", "ADMIN001", permisos=["leer"])
    resp = client.get("/api/admin/logs/errores", headers=headers)
    assert resp.status_code == 503
    data = resp.get_json()
    assert data["code"] == "logging_viewer_missing"
    assert "logging.viewer" in data["message"]
