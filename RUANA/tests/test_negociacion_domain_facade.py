"""Campamento Base: negociacion_domain es la fuente; negociacion_manager es fachada."""
from pathlib import Path

from core import negociacion_manager as neg_mgr
from core.services import negociacion_domain as neg_domain


def test_negociacion_manager_reexports_domain_symbols():
    """La fachada expone los mismos objetos públicos que el dominio."""
    for name in (
        "CAMPOS_ORDEN",
        "CAMPOS_LABELS",
        "ESTADO_PENDIENTE",
        "ESTADO_CONFIRMADO",
        "parse_negociacion",
        "estado_inicial",
        "proponer_campo",
        "aceptar_campo",
        "construir_payload",
        "resumen_acuerdo",
        "meta_negociacion",
        "serializar_negociacion",
        "parse_precio_catalogo",
        "accion_disponible",
    ):
        assert hasattr(neg_mgr, name), name
        assert getattr(neg_mgr, name) is getattr(neg_domain, name), name


def test_negociacion_domain_file_is_canonical_implementation():
    """El dominio vive en services; el manager es delgado (solo reexport)."""
    root = Path(__file__).resolve().parents[1]
    domain = (root / "core" / "services" / "negociacion_domain.py").read_text(encoding="utf-8")
    facade = (root / "core" / "negociacion_manager.py").read_text(encoding="utf-8")
    assert "def parse_negociacion" in domain
    assert "def proponer_campo" in domain
    assert "def construir_payload" in domain
    assert "from core.services.negociacion_domain import" in facade
    assert "def parse_negociacion" not in facade
    assert facade.count("\n") < 80


def test_negociacion_service_imports_domain_not_legacy_logic():
    """negociacion_service usa negociacion_domain (no lógica embebida legacy)."""
    root = Path(__file__).resolve().parents[1]
    svc = (root / "core" / "services" / "negociacion_service.py").read_text(encoding="utf-8")
    assert "from core.services import negociacion_domain as neg_mgr" in svc
    assert "negociacion_domain" in svc
