"""Campamento Base: DBManager debe permanecer como fachada delgada hacia services."""
from pathlib import Path
import ast


ROOT = Path(__file__).resolve().parents[1]
DB_MANAGER = ROOT / "core" / "db_manager.py"


def _method_bodies():
    tree = ast.parse(DB_MANAGER.read_text(encoding="utf-8"))
    class_def = next(
        n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "DBManager"
    )
    for node in class_def.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            yield node


def test_db_manager_methods_are_mostly_service_facades():
    """Casi todos los métodos de instancia delegan a *_service (fachada Campamento Base)."""
    facade_like = 0
    init_or_connect = 0
    other = []
    for node in _method_bodies():
        name = node.name
        src = ast.get_source_segment(DB_MANAGER.read_text(encoding="utf-8"), node) or ""
        if name in {"__init__", "_connect"}:
            init_or_connect += 1
            continue
        if "_service." in src or "Repo()" in src or "return " in src and "service" in src:
            facade_like += 1
            continue
        # Métodos auxiliares mínimos permitidos (sin lógica de dominio nueva)
        if name.startswith("_") and ("Repo" in src) and src.count("\n") <= 25:
            facade_like += 1
            continue
        other.append(name)

    assert facade_like >= 300, f"demasiados métodos no-fachada: {other[:20]}"
    assert init_or_connect == 2
    assert len(other) <= 5, f"métodos no fachada inesperados: {other}"


def test_db_manager_does_not_reintroduce_negociacion_manager_logic():
    text = DB_MANAGER.read_text(encoding="utf-8")
    assert "def parse_negociacion" not in text
    assert "def proponer_campo" not in text
    assert "from core import negociacion_manager" not in text


def test_negociacion_domain_is_under_services_map():
    domain = ROOT / "core" / "services" / "negociacion_domain.py"
    assert domain.is_file()
    assert "def construir_payload" in domain.read_text(encoding="utf-8")
