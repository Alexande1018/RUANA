#!/usr/bin/env python3
"""
RUANA Mapa — scanner exhaustivo (SOLO LECTURA).

Inventaria TODO lo detectable en el repo y produce graph.json.
- No inventa módulos ni relaciones.
- Diferencia HECHO / DETECCIÓN / INFERENCIA.
- Nada existente se omite: lo no clasificable va a «Sin clasificar».
"""
from __future__ import annotations

import ast
import json
import re
import subprocess
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

THIS = Path(__file__).resolve()
REPO = THIS.parents[2]
PKG = REPO / "RUANA"
OUT = THIS.parent / "graph.json"

SKIP_DIR = {
    "__pycache__", ".git", "node_modules", ".venv", "venv",
    "uploads",  # binarios de usuario
    "dev-tools",
}

# Dominios lógicos derivados de NOMBRES REALES del repo (hecho por evidencia de path).
# Orden importa: primera coincidencia gana.
DOMAIN_RULES: list[tuple[re.Pattern, str, str, str]] = [
    (re.compile(r"aliado", re.I), "aliados", "Aliados", "Nombre de archivo/carpeta/servicio contiene «aliado»."),
    (re.compile(r"admin", re.I), "administracion", "Administración", "Nombre contiene «admin»."),
    (re.compile(r"auth|register|invite|session|login", re.I), "autenticacion", "Autenticación", "Nombre relacionado con auth/registro/sesión."),
    (re.compile(r"chat|mensaje|comunicacion|alert.?hub", re.I), "chat", "Chat / Comunicación", "Nombre relacionado con chat/mensajes/comunicación."),
    (re.compile(r"pago|paypal", re.I), "pagos", "Pagos", "Nombre relacionado con pagos."),
    (re.compile(r"negociacion|acuerdo", re.I), "acuerdos", "Acuerdos / Negociación", "Nombre relacionado con negociación/acuerdos."),
    (re.compile(r"referido|linaje|captacion", re.I), "captacion", "Captación / Referidos", "Nombre relacionado con referidos/linaje."),
    (re.compile(r"notificacion|feedback", re.I), "notificaciones", "Notificaciones", "Nombre relacionado con notificaciones."),
    (re.compile(r"grupo|plaza|oficio", re.I), "grupos", "Grupos / Plaza", "Nombre relacionado con grupos/plaza."),
    (re.compile(r"score|elite", re.I), "score", "Score", "Nombre relacionado con score."),
    (re.compile(r"catalogo", re.I), "catalogo", "Catálogo", "Nombre relacionado con catálogo."),
    (re.compile(r"solicitud", re.I), "solicitudes", "Solicitudes", "Nombre relacionado con solicitudes."),
    (re.compile(r"invitacion", re.I), "invitaciones", "Invitaciones", "Nombre relacionado con invitaciones."),
    (re.compile(r"contacto", re.I), "contactos", "Contactos", "Nombre relacionado con contactos."),
    (re.compile(r"evaluacion", re.I), "evaluacion", "Evaluación", "Nombre relacionado con evaluación."),
    (re.compile(r"competencia", re.I), "competencia", "Competencia", "Nombre relacionado con competencia."),
    (re.compile(r"soporte", re.I), "soporte", "Soporte", "Nombre relacionado con soporte."),
    (re.compile(r"schema|supabase|migration|\.sql$", re.I), "base_datos", "Base de datos", "Migraciones SQL / schema."),
    (re.compile(r"test_|/tests/|/e2e/|playwright", re.I), "tests", "Tests", "Tests o e2e."),
    (re.compile(r"deploy|docker|firebase|cloudrun|scripts/|devops|\.yml$|\.yaml$", re.I), "infraestructura", "Infraestructura", "Deploy/scripts/CI."),
    (re.compile(r"engine|metric|event|orquest", re.I), "motores", "Motores / Eventos / Métricas", "engines/metrics/events/orquestador."),
    (re.compile(r"docs/|\.md$", re.I), "documentacion", "Documentación", "Documentación markdown."),
    (re.compile(r"static/css|\.css$", re.I), "estilos", "Estilos", "Hojas de estilo."),
    (re.compile(r"static/images|\.png$|\.svg$|\.jpg$|\.webp$", re.I), "assets", "Assets visuales", "Imágenes/iconos."),
]

KIND_BY_EXT = {
    ".py": "python", ".js": "javascript", ".html": "html", ".css": "css",
    ".sql": "sql", ".md": "markdown", ".json": "json", ".yml": "config",
    ".yaml": "config", ".sh": "script", ".ps1": "script", ".txt": "text",
    ".png": "image", ".svg": "image", ".jpg": "image", ".webp": "image",
    ".pdf": "document", ".docx": "document", ".db": "database_file",
    ".env": "env", ".example": "env_example",
}

JS_FUNC_RE = re.compile(r"^\s*function\s+([A-Za-z_$][\w$]*)\s*\(", re.M)
JS_CONST_FN_RE = re.compile(r"^\s*(?:const|let)\s+([A-Za-z_$][\w$]*)\s*=\s*(?:async\s*)?\(", re.M)
FETCH_RE = re.compile(r"fetch\(\s*(?:apiUrl\()?[`'\"]([^`'\"]+)[`'\"]")
SCRIPT_SRC_RE = re.compile(r'<script[^>]+src=["\']([^"\']+)["\']', re.I)
CREATE_TABLE_RE = re.compile(
    r"CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?(?:public\.)?[\"`]?([a-zA-Z_][a-zA-Z0-9_]*)[\"`]?",
    re.I,
)
SQL_MENTION_RE = re.compile(
    r"(?:FROM|INTO|UPDATE|JOIN)\s+[\"`]?([a-zA-Z_][a-zA-Z0-9_]*)[\"`]?",
    re.I,
)
LARGE_LOC = 800
LARGE_FN_LINES = 80


def rel(p: Path) -> str:
    return str(p.relative_to(REPO)).replace("\\", "/")


def classify_domain(path: str) -> tuple[str, str, str, str]:
    """Returns (domain_id, label, certainty, evidence). certainty: fact|inference."""
    for rx, did, label, evidence in DOMAIN_RULES:
        if rx.search(path):
            return did, label, "fact", evidence
    return "sin_clasificar", "Sin clasificar", "unknown", "No coincidió con reglas de nombre conocidas del repo."


DOMAIN_PURPOSE: dict[str, str] = {
    "aliados": "Ciclo de vida de aliados: registro, perfil, estado, grupos, plazas y directorio.",
    "administracion": "Operaciones de administración, panel y control del sistema.",
    "autenticacion": "Acceso, sesión, registro e invitaciones de entrada.",
    "chat": "Mensajería, comunicación entre aliados y alertas.",
    "pagos": "Pagos, apoyo RUANA, métodos de cobro y conflictos de importe.",
    "acuerdos": "Negociación y acuerdos entre aliados.",
    "captacion": "Referidos, linaje y captación de nuevos aliados.",
    "notificaciones": "Avisos y feedback al usuario.",
    "grupos": "Grupos territoriales, plazas y oficios.",
    "score": "Puntuación, élite y cambios de score.",
    "catalogo": "Catálogo oficial de oficios y especializaciones.",
    "solicitudes": "Solicitudes entre aliados o hacia el sistema.",
    "invitaciones": "Invitaciones a unirse a RUANA o a un grupo.",
    "contactos": "Contactos comerciales entre aliados.",
    "evaluacion": "Evaluaciones y valoraciones.",
    "competencia": "Competencia y reglas asociadas.",
    "soporte": "Soporte y centro de comunicación.",
    "base_datos": "Esquema, migraciones SQL y persistencia.",
    "tests": "Pruebas automáticas y e2e.",
    "infraestructura": "Deploy, CI, Docker y scripts operativos.",
    "motores": "Motores, eventos, métricas y orquestación.",
    "documentacion": "Documentación del proyecto.",
    "estilos": "Hojas de estilo y apariencia visual.",
    "assets": "Imágenes, iconos y recursos visuales.",
    "sin_clasificar": "Elementos reales del repo que aún no encajan en un dominio conocido.",
}


def first_paragraph(text: str, limit: int = 420) -> str:
    if not text:
        return ""
    parts = [p.strip() for p in re.split(r"\n\s*\n", text.strip()) if p.strip()]
    para = parts[0] if parts else text.strip()
    para = re.sub(r"\s+", " ", para).strip()
    if len(para) > limit:
        return para[: limit - 1].rstrip() + "…"
    return para


def first_line(text: str, limit: int = 180) -> str:
    if not text:
        return ""
    line = text.strip().split("\n", 1)[0].strip()
    line = re.sub(r"\s+", " ", line)
    if len(line) > limit:
        return line[: limit - 1].rstrip() + "…"
    return line


def infer_role(path: str, kind: str) -> dict[str, str]:
    """Rol funcional a partir de la ubicación/nombre real del archivo."""
    name = Path(path).name
    stem = Path(path).stem
    p = path.replace("\\", "/")
    low = p.lower()

    if kind == "route":
        return {
            "id": "route",
            "function": "Ruta HTTP",
            "what": f"Endpoint HTTP «{name}»: recibe peticiones y las despacha a un handler Flask.",
        }
    if kind == "table":
        return {
            "id": "table",
            "function": "Tabla de base de datos",
            "what": f"Tabla SQL «{name}»: almacena datos persistentes del dominio.",
        }
    if name == "db_manager.py" or stem == "db_manager":
        return {
            "id": "db_manager",
            "function": "Gestor central de base de datos",
            "what": "Fachada monolítica DBManager: API histórica de persistencia; parte ya delega a services/repos.",
        }
    if name == "app.py" and "/web/" in low:
        return {
            "id": "flask_app",
            "function": "Servidor web Flask",
            "what": "Punto de entrada del dashboard: setup Flask, middleware y registro de blueprints.",
        }
    if "/services/" in low or stem.endswith("_service"):
        dom = stem.replace("_service", "").replace("-", "_")
        return {
            "id": "service",
            "function": f"Servicio de dominio «{dom}»",
            "what": f"Servicio «{name}»: lógica de negocio, validaciones y orquestación del dominio {dom}.",
        }
    if "/repositories/" in low or stem.endswith("_repo"):
        dom = stem.replace("_repo", "").replace("-", "_")
        return {
            "id": "repository",
            "function": f"Repositorio «{dom}»",
            "what": f"Repositorio «{name}»: acceso a datos (SQL/lectura-escritura) sin reglas de negocio.",
        }
    if "/blueprints/" in low or stem.endswith("_bp"):
        dom = stem.replace("_bp", "").replace("-", "_")
        return {
            "id": "blueprint",
            "function": f"Blueprint HTTP «{dom}»",
            "what": f"Blueprint Flask «{name}»: rutas HTTP y handlers del área {dom}.",
        }
    if "/engines/" in low:
        return {
            "id": "engine",
            "function": f"Motor «{stem}»",
            "what": f"Motor/proceso «{name}»: lógica de ejecución o cálculo del sistema.",
        }
    if kind == "javascript":
        return {
            "id": "frontend_js",
            "function": "Script de interfaz",
            "what": f"JavaScript «{name}»: comportamiento de la interfaz (eventos, fetch, UI).",
        }
    if kind == "html":
        return {
            "id": "page",
            "function": "Página / plantilla",
            "what": f"HTML «{name}»: pantalla o plantilla que ve el usuario.",
        }
    if kind == "css":
        return {
            "id": "stylesheet",
            "function": "Hoja de estilos",
            "what": f"CSS «{name}»: apariencia visual de la interfaz.",
        }
    if kind == "sql":
        return {
            "id": "migration",
            "function": "Migración SQL",
            "what": f"SQL «{name}»: define o altera el esquema real de la base de datos.",
        }
    if kind == "markdown":
        return {
            "id": "docs",
            "function": "Documento",
            "what": f"Documento «{name}»: explicación o guía del proyecto.",
        }
    if kind in ("config", "json", "env", "env_example"):
        return {
            "id": "config",
            "function": "Configuración",
            "what": f"Configuración «{name}»: parámetros o metadatos del sistema.",
        }
    if kind == "script":
        return {
            "id": "ops_script",
            "function": "Script operativo",
            "what": f"Script «{name}»: automatización o operación del entorno.",
        }
    if kind == "image":
        return {
            "id": "asset",
            "function": "Recurso visual",
            "what": f"Imagen «{name}»: asset visual del producto.",
        }
    return {
        "id": "file",
        "function": f"Archivo {kind}",
        "what": f"Archivo «{name}» presente en el proyecto ({kind}).",
    }


def summarize_does(items: list[dict], limit: int = 10) -> str:
    if not items:
        return ""
    bits = []
    for it in items[:limit]:
        name = it.get("name") or ""
        doc = it.get("doc") or ""
        if doc:
            bits.append(f"{name}: {doc}")
        else:
            bits.append(name)
    return " · ".join(bits)


def build_human(
    *,
    path: str,
    kind: str,
    domain_label: str,
    domain_certainty: str,
    domain_evidence: str,
    module_doc: str = "",
    does: Optional[list] = None,
    extra_purpose: str = "",
) -> dict:
    role = infer_role(path, kind)
    does = does or []
    desc = first_paragraph(module_doc)
    certainty = "fact"
    evidence = path
    if desc:
        purpose = desc
    elif extra_purpose:
        purpose = extra_purpose
        certainty = "detection"
        evidence = domain_evidence or path
    else:
        does_txt = summarize_does(does, 8)
        if does_txt:
            purpose = f"Expone: {does_txt}"
            certainty = "detection"
            evidence = "Símbolos/funciones detectados en el archivo."
        else:
            purpose = f"Pertenece al dominio «{domain_label}»."
            certainty = domain_certainty
            evidence = domain_evidence
    return {
        "function": role["function"],
        "what": role["what"],
        "description": purpose,
        "where": path,
        "purpose": {"text": purpose, "certainty": certainty, "evidence": evidence},
        "does": does[:14],
        "role": role["id"],
        "module_doc": first_paragraph(module_doc, 600) if module_doc else "",
    }


def human_what(kind: str, path: str) -> str:
    return infer_role(path, kind)["what"]


def iter_all_files():
    roots = [REPO / "RUANA", REPO / "supabase", REPO / "scripts", REPO / "e2e", REPO / "docs", REPO / ".github"]
    extras = [REPO / "package.json", REPO / "playwright.config.js", REPO / "Dockerfile",
              REPO / "firebase.json", REPO / ".env.example", REPO / "README.md", REPO / "ROADMAP.md"]
    for root in roots:
        if not root.exists():
            continue
        for p in root.rglob("*"):
            if not p.is_file():
                continue
            if any(part in SKIP_DIR for part in p.relative_to(REPO).parts):
                continue
            yield p
    for p in extras:
        if p.is_file():
            yield p


def module_to_path(mod: str) -> Optional[str]:
    cand = PKG / Path(*mod.split("."))
    py = cand.with_suffix(".py")
    if py.is_file():
        return rel(py)
    init = cand / "__init__.py"
    if init.is_file():
        return rel(init)
    return None


def route_methods(call: ast.Call) -> list[str]:
    for kw in call.keywords:
        if kw.arg == "methods" and isinstance(kw.value, (ast.List, ast.Tuple)):
            out = []
            for elt in kw.value.elts:
                if isinstance(elt, ast.Constant) and isinstance(elt.value, str):
                    out.append(elt.value)
            return out or ["GET"]
    return ["GET"]


@dataclass
class Node:
    id: str
    label: str
    type: str
    kind: str
    path: Optional[str] = None
    folder: Optional[str] = None
    domain: str = "sin_clasificar"
    domain_label: str = "Sin clasificar"
    domain_certainty: str = "unknown"
    loc: int = 0
    classes: list = field(default_factory=list)
    functions: list = field(default_factory=list)
    routes: list = field(default_factory=list)
    symbols: list = field(default_factory=list)
    meta: dict = field(default_factory=dict)
    flags: list = field(default_factory=list)
    human: dict = field(default_factory=dict)


nodes: dict[str, Node] = {}
edges: list[dict] = []
edge_set: set = set()
raw_imports: dict[str, list[str]] = {}
file_sources: dict[str, str] = {}
all_tables: set[str] = set()


def add_node(n: Node):
    nodes[n.id] = n


def add_edge(src: str, tgt: str, etype: str, certainty: str = "fact"):
    key = (src, tgt, etype)
    if src == tgt or key in edge_set:
        return
    if src not in nodes or tgt not in nodes:
        return
    edge_set.add(key)
    edges.append({"source": src, "target": tgt, "type": etype, "certainty": certainty})


def scan_python(path: Path):
    r = rel(path)
    try:
        src = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return
    loc = src.count("\n") + 1
    did, dlab, dcert, evid = classify_domain(r)
    n = Node(
        id=r, label=path.name, type="file", kind="python", path=r,
        folder=str(Path(r).parent).replace("\\", "/"),
        domain=did, domain_label=dlab, domain_certainty=dcert, loc=loc,
        meta={"domain_evidence": evid},
    )
    if loc >= LARGE_LOC:
        n.flags.append({"code": "large_file", "level": "detection", "msg": f"Archivo grande: {loc} líneas (umbral {LARGE_LOC})."})
    try:
        tree = ast.parse(src, filename=r)
    except SyntaxError as e:
        n.flags.append({"code": "parse_error", "level": "fact", "msg": f"Error de sintaxis: {e}"})
        n.meta["parse_error"] = str(e)
        n.human = build_human(path=r, kind="python", domain_label=dlab, domain_certainty=dcert, domain_evidence=evid)
        add_node(n)
        return

    module_doc = ast.get_docstring(tree) or ""
    imports = []
    does: list[dict] = []

    for item in tree.body:
        if isinstance(item, ast.ClassDef):
            class_doc = first_line(ast.get_docstring(item) or "")
            methods_info = []
            for m in item.body:
                if isinstance(m, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    md = first_line(ast.get_docstring(m) or "")
                    methods_info.append({"name": m.name, "doc": md, "lineno": m.lineno})
            method_names = [m["name"] for m in methods_info]
            n.classes.append({"name": item.name, "methods": method_names, "doc": class_doc})
            n.symbols.append({
                "id": f"{r}::class::{item.name}", "kind": "class", "name": item.name,
                "methods": method_names, "doc": class_doc, "lineno": item.lineno,
            })
            does.append({"name": item.name, "doc": class_doc or f"Clase con {len(method_names)} métodos", "kind": "class"})
            for m in methods_info:
                n.symbols.append({
                    "id": f"{r}::method::{item.name}.{m['name']}", "kind": "method",
                    "name": f"{item.name}.{m['name']}", "parent": item.name,
                    "doc": m["doc"], "lineno": m["lineno"],
                })
                if m["doc"] and not m["name"].startswith("_"):
                    does.append({"name": f"{item.name}.{m['name']}", "doc": m["doc"], "kind": "method"})
        elif isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
            fn_doc = first_line(ast.get_docstring(item) or "")
            n.functions.append(item.name)
            n.symbols.append({
                "id": f"{r}::fn::{item.name}", "kind": "function", "name": item.name,
                "doc": fn_doc, "lineno": item.lineno,
            })
            if not item.name.startswith("_") or fn_doc:
                does.append({"name": item.name, "doc": fn_doc, "kind": "function"})
            span = getattr(item, "end_lineno", item.lineno) - item.lineno + 1
            if span >= LARGE_FN_LINES:
                n.flags.append({"code": "large_function", "level": "detection",
                                "msg": f"Función «{item.name}» con ~{span} líneas (umbral {LARGE_FN_LINES})."})

    for item in ast.walk(tree):
        if isinstance(item, ast.Import):
            for a in item.names:
                imports.append(a.name)
        elif isinstance(item, ast.ImportFrom):
            if item.module:
                imports.append(item.module)
                for a in item.names:
                    imports.append(f"{item.module}.{a.name}")

    route_defs = []
    for item in ast.walk(tree):
        if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for dec in item.decorator_list:
                if isinstance(dec, ast.Call) and isinstance(dec.func, ast.Attribute) and dec.func.attr == "route":
                    if dec.args and isinstance(dec.args[0], ast.Constant) and isinstance(dec.args[0].value, str):
                        route_defs.append({
                            "path": dec.args[0].value,
                            "methods": route_methods(dec),
                            "handler": item.name,
                            "doc": first_line(ast.get_docstring(item) or ""),
                        })
    n.routes = route_defs
    n.human = build_human(
        path=r, kind="python", domain_label=dlab, domain_certainty=dcert,
        domain_evidence=evid, module_doc=module_doc, does=does,
    )
    n.meta["module_doc"] = first_paragraph(module_doc, 600) if module_doc else ""
    add_node(n)
    raw_imports[r] = imports
    file_sources[r] = src


def scan_js(path: Path):
    r = rel(path)
    try:
        src = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return
    loc = src.count("\n") + 1
    did, dlab, dcert, evid = classify_domain(r)
    fns = sorted(set(JS_FUNC_RE.findall(src)) | set(JS_CONST_FN_RE.findall(src)))
    fetches = sorted(set(m for m in FETCH_RE.findall(src) if m.startswith("/")))
    # Comentario de cabecera /** ... */ o // líneas iniciales
    module_doc = ""
    m = re.match(r"^\s*/\*\*?([\s\S]*?)\*/", src)
    if m:
        module_doc = re.sub(r"^\s*\*\s?", "", m.group(1), flags=re.M).strip()
    else:
        heads = []
        for line in src.splitlines()[:12]:
            if line.strip().startswith("//"):
                heads.append(line.strip().lstrip("/").strip())
            elif line.strip():
                break
        module_doc = " ".join(heads)
    does = [{"name": f, "doc": "", "kind": "function"} for f in fns if not f.startswith("_")]
    n = Node(
        id=r, label=path.name, type="file", kind="javascript", path=r,
        folder=str(Path(r).parent).replace("\\", "/"),
        domain=did, domain_label=dlab, domain_certainty=dcert, loc=loc,
        functions=fns,
        symbols=[{"id": f"{r}::fn::{f}", "kind": "function", "name": f, "doc": ""} for f in fns],
        human=build_human(
            path=r, kind="javascript", domain_label=dlab, domain_certainty=dcert,
            domain_evidence=evid, module_doc=module_doc, does=does,
            extra_purpose=("Llama a: " + ", ".join(fetches[:8])) if fetches else "",
        ),
        meta={"fetch_paths": fetches, "domain_evidence": evid, "module_doc": first_paragraph(module_doc, 600)},
    )
    if loc >= LARGE_LOC:
        n.flags.append({"code": "large_file", "level": "detection", "msg": f"Archivo grande: {loc} líneas."})
    add_node(n)


def scan_html(path: Path):
    r = rel(path)
    try:
        src = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return
    loc = src.count("\n") + 1
    did, dlab, dcert, evid = classify_domain(r)
    srcs = SCRIPT_SRC_RE.findall(src)
    title_m = re.search(r"<title[^>]*>([^<]+)</title>", src, re.I)
    title = (title_m.group(1).strip() if title_m else "")
    desc_m = re.search(r'<meta[^>]+name=["\']description["\'][^>]+content=["\']([^"\']+)["\']', src, re.I)
    if not desc_m:
        desc_m = re.search(r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+name=["\']description["\']', src, re.I)
    meta_desc = desc_m.group(1).strip() if desc_m else ""
    module_doc = meta_desc or (f"Página titulada «{title}»." if title else "")
    n = Node(
        id=r, label=path.name, type="file", kind="html", path=r,
        folder=str(Path(r).parent).replace("\\", "/"),
        domain=did, domain_label=dlab, domain_certainty=dcert, loc=loc,
        human=build_human(
            path=r, kind="html", domain_label=dlab, domain_certainty=dcert,
            domain_evidence=evid, module_doc=module_doc,
            extra_purpose=f"Carga scripts: {', '.join(srcs[:6])}" if srcs else "",
        ),
        meta={"script_srcs": srcs, "domain_evidence": evid, "page_title": title},
    )
    add_node(n)


def scan_sql(path: Path):
    r = rel(path)
    try:
        src = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return
    loc = src.count("\n") + 1
    did, dlab, dcert, evid = classify_domain(r)
    tables = CREATE_TABLE_RE.findall(src)
    all_tables.update(tables)
    # Comentarios iniciales SQL
    heads = []
    for line in src.splitlines()[:20]:
        s = line.strip()
        if s.startswith("--"):
            heads.append(s.lstrip("-").strip())
        elif s:
            break
    module_doc = " ".join(heads)
    if tables and not module_doc:
        module_doc = f"Crea/altera tablas: {', '.join(tables[:12])}."
    n = Node(
        id=r, label=path.name, type="file", kind="sql", path=r,
        folder=str(Path(r).parent).replace("\\", "/"),
        domain=did, domain_label=dlab, domain_certainty=dcert, loc=loc,
        human=build_human(
            path=r, kind="sql", domain_label=dlab, domain_certainty=dcert,
            domain_evidence=evid, module_doc=module_doc,
            extra_purpose="Migración SQL real del proyecto.",
        ),
        meta={"creates_tables": tables, "domain_evidence": evid},
    )
    add_node(n)
    for t in tables:
        tid = f"table::{t}"
        if tid not in nodes:
            td, tl, tc, te = classify_domain(t)
            add_node(Node(
                id=tid, label=t, type="table", kind="table", path=None, folder="(base de datos)",
                domain=td if td != "sin_clasificar" else "base_datos",
                domain_label=tl if td != "sin_clasificar" else "Base de datos",
                domain_certainty="fact",
                human=build_human(
                    path=t, kind="table", domain_label=tl if td != "sin_clasificar" else "Base de datos",
                    domain_certainty="fact", domain_evidence=r,
                    module_doc=f"Tabla «{t}» creada en la migración {Path(r).name}.",
                    extra_purpose="Persistencia de datos del dominio.",
                ),
                meta={"defined_in": r},
            ))
        add_edge(r, tid, "db", "fact")


def scan_generic(path: Path):
    r = rel(path)
    if r in nodes:
        return
    ext = path.suffix.lower()
    kind = KIND_BY_EXT.get(ext, "other")
    loc = 0
    module_doc = ""
    try:
        if kind not in ("image", "document", "database_file") and path.stat().st_size < 2_000_000:
            text = path.read_text(encoding="utf-8", errors="replace")
            loc = text.count("\n") + 1
            if kind == "markdown":
                for line in text.splitlines()[:15]:
                    if line.startswith("#"):
                        module_doc = line.lstrip("#").strip()
                        break
                if not module_doc:
                    module_doc = first_paragraph(text, 240)
    except OSError:
        pass
    did, dlab, dcert, evid = classify_domain(r)
    n = Node(
        id=r, label=path.name, type="file", kind=kind, path=r,
        folder=str(Path(r).parent).replace("\\", "/"),
        domain=did, domain_label=dlab, domain_certainty=dcert, loc=loc,
        human=build_human(
            path=r, kind=kind, domain_label=dlab, domain_certainty=dcert,
            domain_evidence=evid, module_doc=module_doc,
            extra_purpose=("Elemento cuyo propósito no pudo determinarse automáticamente."
                           if dcert == "unknown" else ""),
        ),
        meta={"domain_evidence": evid, "size_bytes": path.stat().st_size if path.exists() else 0},
        flags=([{"code": "unclassified", "level": "unknown",
                 "msg": "Elemento cuyo propósito no pudo determinarse."}] if dcert == "unknown" else []),
    )
    add_node(n)


def find_cycles(adj: dict[str, list[str]]) -> list[list[str]]:
    WHITE, GRAY, BLACK = 0, 1, 2
    color = {n: WHITE for n in adj}
    for ts in adj.values():
        for t in ts:
            color.setdefault(t, WHITE)
    stack: list[str] = []
    on: dict[str, int] = {}
    found: list[list[str]] = []
    seen = set()

    def dfs(u: str):
        color[u] = GRAY
        stack.append(u)
        on[u] = len(stack) - 1
        for v in adj.get(u, []):
            if color.get(v, WHITE) == WHITE:
                dfs(v)
            elif color.get(v) == GRAY:
                cyc = stack[on[v]:] + [v]
                key = tuple(sorted(set(cyc)))
                if key not in seen:
                    seen.add(key)
                    found.append(cyc)
        stack.pop()
        del on[u]
        color[u] = BLACK

    for n in list(adj):
        if color.get(n, WHITE) == WHITE:
            dfs(n)
    return found[:50]


def name_clusters(labels: list[str]) -> list[dict]:
    """Detección heurística de nombres parecidos (INFERENCIA)."""
    from difflib import SequenceMatcher
    out = []
    # only file basenames without ext
    items = []
    for lab in labels:
        base = Path(lab).stem.lower().replace("-", "").replace("_", "")
        if len(base) >= 5:
            items.append((lab, base))
    used = set()
    for i, (a, ab) in enumerate(items):
        if a in used:
            continue
        group = [a]
        for j, (b, bb) in enumerate(items):
            if i >= j or b in used:
                continue
            if SequenceMatcher(None, ab, bb).ratio() >= 0.86 and ab != bb:
                group.append(b)
        if len(group) > 1:
            for g in group:
                used.add(g)
            out.append({
                "level": "inference",
                "code": "similar_names",
                "msg": "Nombres parecidos; podrían representar conceptos relacionados.",
                "items": group[:12],
            })
        if len(out) >= 40:
            break
    return out


def main():
    print("[mapa] inventariando proyecto real…")
    print(f"[mapa] repo root: {REPO}")

    counts = defaultdict(int)
    for p in iter_all_files():
        counts["files"] += 1
        suf = p.suffix.lower()
        if suf == ".py":
            scan_python(p); counts["py"] += 1
        elif suf == ".js":
            scan_js(p); counts["js"] += 1
        elif suf == ".html":
            scan_html(p); counts["html"] += 1
        elif suf == ".sql":
            scan_sql(p); counts["sql"] += 1
        else:
            scan_generic(p); counts[suf or "none"] += 1

    # resolve python imports
    unresolved = 0
    for src, mods in raw_imports.items():
        for mod in mods:
            if not (mod.startswith("core") or mod.startswith("web") or mod.startswith("engines")
                    or mod.startswith("utils") or mod.startswith("events") or mod.startswith("metrics")
                    or mod.startswith("RUANA")):
                continue
            target = module_to_path(mod.replace("RUANA.", ""))
            if target and target in nodes:
                add_edge(src, target, "import", "fact")
            else:
                unresolved += 1

    # routes as nodes
    for n in list(nodes.values()):
        if n.type != "file":
            continue
        for rdef in n.routes:
            for method in rdef.get("methods") or ["GET"]:
                rid = f"route::{method}::{rdef['path']}"
                if rid not in nodes:
                    handler = rdef.get("handler") or "?"
                    rdoc = rdef.get("doc") or ""
                    purpose = rdoc or f"Handler Flask «{handler}» en {Path(n.id).name}."
                    add_node(Node(
                        id=rid, label=f"{method} {rdef['path']}", type="route", kind="route",
                        domain=n.domain, domain_label=n.domain_label, domain_certainty=n.domain_certainty,
                        human=build_human(
                            path=f"{method} {rdef['path']}", kind="route",
                            domain_label=n.domain_label, domain_certainty="fact",
                            domain_evidence=n.id, module_doc=purpose,
                            does=[{"name": handler, "doc": rdoc, "kind": "handler"}],
                        ),
                        meta={"defined_in": n.id, "handler": handler, "doc": rdoc},
                    ))
                add_edge(n.id, rid, "defines", "fact")

    # html script src
    for n in list(nodes.values()):
        if n.kind != "html":
            continue
        for src_attr in n.meta.get("script_srcs", []):
            fname = src_attr.rstrip("/").split("/")[-1]
            for cand in nodes.values():
                if cand.kind == "javascript" and Path(cand.id).name == fname:
                    add_edge(n.id, cand.id, "script", "fact")
                    break

    # js fetch → routes
    path_to_routes: dict[str, list[str]] = {}
    for n in nodes.values():
        if n.type == "route":
            p = n.label.split(" ", 1)[1]
            path_to_routes.setdefault(p, []).append(n.id)
    for n in list(nodes.values()):
        if n.kind != "javascript":
            continue
        for fp in n.meta.get("fetch_paths", []):
            base = re.split(r"[\$`]", fp)[0].rstrip("/")
            matched = False
            if fp in path_to_routes:
                for rid in path_to_routes[fp]:
                    add_edge(n.id, rid, "fetch", "fact"); matched = True
            if not matched and base:
                for p, ids in path_to_routes.items():
                    if p == base or p.startswith(base + "/"):
                        for rid in ids:
                            add_edge(n.id, rid, "fetch", "detection")

    # sql mentions in python
    for nid, src in file_sources.items():
        if not nid.endswith(".py") or not all_tables:
            continue
        for t in set(SQL_MENTION_RE.findall(src)) & all_tables:
            add_edge(nid, f"table::{t}", "db", "detection")

    # degrees
    indeg = defaultdict(int)
    outdeg = defaultdict(int)
    deg = defaultdict(int)
    etypes = defaultdict(int)
    for e in edges:
        outdeg[e["source"]] += 1
        indeg[e["target"]] += 1
        deg[e["source"]] += 1
        deg[e["target"]] += 1
        etypes[e["type"]] += 1

    entry = {"RUANA/web/app.py", "RUANA/web/run.py"}
    imported = {e["target"] for e in edges if e["type"] == "import"}
    no_refs = []
    for n in nodes.values():
        if n.type != "file":
            continue
        d = deg[n.id]
        if d == 0:
            n.flags.append({"code": "no_refs_detected", "level": "detection",
                            "msg": "Sin referencias detectadas en el grafo estático (no implica que esté muerto)."})
            no_refs.append(n.id)
        if (n.kind == "python" and n.id not in imported and n.id not in entry
                and not n.routes and "/tests/" not in n.id and not Path(n.id).name.startswith("test_")
                and not n.id.endswith("__init__.py")):
            n.flags.append({"code": "unused_candidate", "level": "detection",
                            "msg": "Ningún otro módulo parece importarlo y no define rutas Flask."})

    # hot
    for n in nodes.values():
        if n.type == "file" and deg[n.id] >= 25:
            n.flags.append({"code": "high_degree", "level": "detection",
                            "msg": f"Dependencia elevada: grado {deg[n.id]}."})

    import_adj: dict[str, list[str]] = defaultdict(list)
    for e in edges:
        if e["type"] == "import":
            import_adj[e["source"]].append(e["target"])
    cycles = find_cycles(dict(import_adj))

    # domains summary (planet level) — ONLY from real classified nodes
    domains: dict[str, dict] = {}
    for n in nodes.values():
        d = domains.setdefault(n.domain, {
            "id": f"domain::{n.domain}",
            "label": n.domain_label,
            "domain": n.domain,
            "certainty": n.domain_certainty if n.domain != "sin_clasificar" else "unknown",
            "function": f"Dominio «{n.domain_label}»",
            "description": DOMAIN_PURPOSE.get(
                n.domain,
                "Área lógica agrupada por evidencia de nombres reales del proyecto.",
            ),
            "what": (
                f"Continente lógico «{n.domain_label}»: "
                + DOMAIN_PURPOSE.get(
                    n.domain,
                    "agrupa archivos y símbolos relacionados por nombre en el repo.",
                )
            ),
            "files": 0, "routes": 0, "tables": 0, "symbols": 0, "loc": 0, "no_refs": 0,
        })
        if n.type == "file":
            d["files"] += 1
            d["loc"] += n.loc
            d["symbols"] += len(n.symbols)
            if any(f["code"] == "no_refs_detected" for f in n.flags):
                d["no_refs"] += 1
        elif n.type == "route":
            d["routes"] += 1
        elif n.type == "table":
            d["tables"] += 1

    similar = name_clusters([n.id for n in nodes.values() if n.type == "file"])

    anomalies = []
    for n in nodes.values():
        for f in n.flags:
            anomalies.append({**f, "node": n.id, "label": n.label, "path": n.path})
    anomalies.extend(similar)
    for cyc in cycles:
        anomalies.append({"code": "cycle", "level": "detection", "msg": "Ciclo de imports detectado.", "items": cyc})

    try:
        commit = subprocess.run(["git", "-C", str(REPO), "rev-parse", "--short", "HEAD"],
                                capture_output=True, text=True, timeout=5).stdout.strip()
    except Exception:
        commit = "unknown"

    # physical folder tree (ids only)
    folders = sorted({n.folder for n in nodes.values() if n.folder})

    out = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "repo_commit": commit or "unknown",
        "schema_version": 3,
        "planet": {
            "name": "RUANA",
            "tagline": "Mapa completo del territorio real del proyecto",
            "domains": sorted(domains.values(), key=lambda d: (-d["files"], d["label"])),
        },
        "nodes": [
            {
                "id": n.id, "label": n.label, "type": n.type, "kind": n.kind,
                "path": n.path, "folder": n.folder,
                "domain": n.domain, "domain_label": n.domain_label,
                "domain_certainty": n.domain_certainty,
                "loc": n.loc,
                "degree": deg[n.id], "in_degree": indeg[n.id], "out_degree": outdeg[n.id],
                "classes": n.classes, "functions": n.functions, "routes": n.routes,
                "symbols": n.symbols, "flags": n.flags, "human": n.human, "meta": n.meta,
            }
            for n in nodes.values()
        ],
        "edges": edges,
        "folders": folders,
        "anomalies": anomalies,
        "health": {
            "cycles": cycles,
            "no_refs_detected": no_refs,
            "unused_candidates": [n.id for n in nodes.values()
                                  if any(f["code"] == "unused_candidate" for f in n.flags)],
            "hot_modules": sorted(
                [{"id": n.id, "label": n.label, "degree": deg[n.id]}
                 for n in nodes.values() if n.type == "file"],
                key=lambda x: -x["degree"],
            )[:15],
            "unresolved_internal_imports": unresolved,
            "orphans": [{"id": nid, "kind": "no_refs_detected"} for nid in no_refs],
            "isolated_files": no_refs,
        },
        "stats": {
            "total_nodes": len(nodes),
            "total_edges": len(edges),
            "files_scanned": counts["files"],
            "python_files": sum(1 for n in nodes.values() if n.kind == "python"),
            "js_files": sum(1 for n in nodes.values() if n.kind == "javascript"),
            "html_files": sum(1 for n in nodes.values() if n.kind == "html"),
            "css_files": sum(1 for n in nodes.values() if n.kind == "css"),
            "sql_files": sum(1 for n in nodes.values() if n.kind == "sql"),
            "routes": sum(1 for n in nodes.values() if n.type == "route"),
            "tables": sum(1 for n in nodes.values() if n.type == "table"),
            "symbols": sum(len(n.symbols) for n in nodes.values()),
            "domains": len(domains),
            "folders": len(folders),
            "total_loc": sum(n.loc for n in nodes.values() if n.type == "file"),
            "no_refs_detected": len(no_refs),
            "anomalies": len(anomalies),
            "edge_types": dict(etypes),
        },
        "legend_certainty": {
            "fact": "Hecho observable en el código o el sistema de archivos.",
            "detection": "Señal detectada por análisis estático; no es prueba absoluta.",
            "inference": "Hipótesis automática; requiere revisión humana.",
            "unknown": "Existe, pero no pudo clasificarse con las reglas actuales.",
        },
    }

    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"[mapa] escrito: {OUT}")
    print(f"[mapa] nodos={out['stats']['total_nodes']} aristas={out['stats']['total_edges']} "
          f"dominios={out['stats']['domains']} sin_refs={out['stats']['no_refs_detected']} "
          f"anomalias={out['stats']['anomalies']}")


if __name__ == "__main__":
    main()
