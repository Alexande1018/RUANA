#!/usr/bin/env python3
"""
RUANA Code Map — scanner.py
============================
Lee el código REAL del repositorio (no genera datos de ejemplo) y produce
`graph.json`: el grafo de nodos (archivos, rutas Flask, tablas de Supabase)
y aristas (imports, plantilla->JS, JS->ruta API, archivo->tabla) que consume
`index.html`.

Este script es SOLO LECTURA. No modifica ningún archivo del proyecto.

Uso:
    python3 dev-tools/code-map/scanner.py
    (o el wrapper: bash dev-tools/code-map/generate.sh)

Se ejecuta desde la raíz del repo (detecta la raíz automáticamente si se
invoca desde dentro de dev-tools/code-map/).
"""
from __future__ import annotations

import ast
import json
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

# ---------------------------------------------------------------------------
# Localización del repo
# ---------------------------------------------------------------------------

THIS_FILE = Path(__file__).resolve()
REPO_ROOT = THIS_FILE.parents[2]          # dev-tools/code-map/scanner.py -> repo root
PKG_ROOT = REPO_ROOT / "RUANA"            # paquete Python real (core.*, web.*, engines.* resuelven aquí)
OUT_FILE = THIS_FILE.parent / "graph.json"

# Carpetas que NO son código a mapear (cache, binarios, dependencias, uploads)
EXCLUDE_DIR_NAMES = {
    "__pycache__", ".git", "node_modules", ".venv", "venv",
    "uploads", "images", "css",  # RUANA/web/static/{images,css,uploads}: no son grafo de dependencias
    "dev-tools",  # la propia herramienta no es parte del grafo de RUANA
}

AREA_BY_PREFIX = [
    # (prefijo relativo a REPO_ROOT, area)
    ("RUANA/core", "core"),
    ("RUANA/engines", "engines"),
    ("RUANA/events", "events"),
    ("RUANA/metrics", "metrics"),
    ("RUANA/utils", "utils"),
    ("RUANA/web/static/js", "frontend"),
    ("RUANA/web", "backend"),          # app.py, run.py, *.html quedan aquí si no cayeron arriba
    ("RUANA/tests", "tests"),
    ("RUANA/scripts", "devops"),
    ("scripts", "devops"),
    ("e2e", "tests"),
    ("supabase/migrations", "database"),
]


def area_for(rel_path: str) -> str:
    fname = rel_path.rsplit("/", 1)[-1]
    if fname.startswith("test_") or fname.endswith("_test.py"):
        return "tests"
    for prefix, area in AREA_BY_PREFIX:
        if rel_path == prefix or rel_path.startswith(prefix + "/"):
            return area
    if rel_path.startswith("RUANA/") and rel_path.count("/") == 1:
        return "backend"  # ej. RUANA/__init__.py
    return "other"


# ---------------------------------------------------------------------------
# Modelo del grafo
# ---------------------------------------------------------------------------

@dataclass
class Node:
    id: str
    label: str
    type: str          # "file" | "route" | "table"
    group: str
    path: Optional[str] = None
    loc: int = 0
    classes: list = field(default_factory=list)
    functions: list = field(default_factory=list)
    routes: list = field(default_factory=list)
    meta: dict = field(default_factory=dict)


@dataclass
class Edge:
    source: str
    target: str
    type: str           # "import" | "script" | "fetch" | "defines" | "db"


nodes: dict[str, Node] = {}
edges: list[tuple] = []
edge_set: set = set()


def add_node(n: Node):
    nodes[n.id] = n


def add_edge(source: str, target: str, etype: str):
    key = (source, target, etype)
    if source == target or key in edge_set:
        return
    if source not in nodes or target not in nodes:
        return
    edge_set.add(key)
    edges.append(Edge(source, target, etype))


def iter_files(root: Path, suffixes: set[str]):
    for p in root.rglob("*"):
        if not p.is_file():
            continue
        if p.suffix not in suffixes:
            continue
        if any(part in EXCLUDE_DIR_NAMES for part in p.relative_to(REPO_ROOT).parts):
            continue
        yield p


# ---------------------------------------------------------------------------
# 1) Escaneo de archivos Python (AST real: imports, clases, funciones, rutas)
# ---------------------------------------------------------------------------

def module_name_to_relpath(mod: str) -> Optional[str]:
    """'core.db_manager' -> 'RUANA/core/db_manager.py' si existe en el repo."""
    candidate = PKG_ROOT / Path(*mod.split("."))
    py_file = candidate.with_suffix(".py")
    if py_file.is_file():
        return str(py_file.relative_to(REPO_ROOT))
    init_file = candidate / "__init__.py"
    if init_file.is_file():
        return str(init_file.relative_to(REPO_ROOT))
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


def scan_python_file(path: Path):
    rel = str(path.relative_to(REPO_ROOT))
    try:
        src = path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return
    loc = src.count("\n") + 1
    try:
        tree = ast.parse(src, filename=rel)
    except SyntaxError as e:
        node = Node(id=rel, label=path.name, type="file", group=area_for(rel), path=rel, loc=loc)
        node.meta["parse_error"] = str(e)
        add_node(node)
        return

    node = Node(id=rel, label=path.name, type="file", group=area_for(rel), path=rel, loc=loc)

    import_targets: list[str] = []
    route_defs: list[dict] = []

    for item in ast.walk(tree):
        if isinstance(item, ast.ClassDef):
            methods = [n.name for n in item.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
            node.classes.append({"name": item.name, "methods": methods})
        elif isinstance(item, ast.FunctionDef) or isinstance(item, ast.AsyncFunctionDef):
            # solo funciones de nivel de módulo (no métodos, ya capturados arriba)
            pass
        elif isinstance(item, ast.Import):
            for alias in item.names:
                import_targets.append(alias.name)
        elif isinstance(item, ast.ImportFrom):
            if item.module:
                import_targets.append(item.module)
                # cubre el patrón `from paquete import submodulo` (ej. `from core import
                # negociacion_manager as neg_mgr`), donde lo importado es un archivo, no un símbolo
                for alias in item.names:
                    import_targets.append(f"{item.module}.{alias.name}")

    # funciones top-level (no anidadas en clases)
    for item in tree.body:
        if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
            node.functions.append(item.name)

    # rutas Flask: decoradores tipo @app.route(...) / @bp.route(...) en cualquier función
    for item in ast.walk(tree):
        if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for dec in item.decorator_list:
                if isinstance(dec, ast.Call) and isinstance(dec.func, ast.Attribute) and dec.func.attr == "route":
                    if dec.args and isinstance(dec.args[0], ast.Constant) and isinstance(dec.args[0].value, str):
                        route_defs.append({
                            "path": dec.args[0].value,
                            "methods": route_methods(dec),
                            "handler": item.name,
                        })

    node.routes = route_defs
    add_node(node)

    # guardamos temporalmente para resolver edges en una segunda pasada
    node.meta["_raw_imports"] = import_targets
    node.meta["_src"] = src  # se usa para detectar tablas SQL; se elimina antes de exportar


# ---------------------------------------------------------------------------
# 2) Escaneo de archivos JS (regex: funciones top-level + llamadas fetch())
# ---------------------------------------------------------------------------

JS_FUNC_RE = re.compile(r"^\s*function\s+([A-Za-z_$][\w$]*)\s*\(", re.MULTILINE)
JS_CONST_FN_RE = re.compile(r"^\s*(?:const|let)\s+([A-Za-z_$][\w$]*)\s*=\s*(?:async\s*)?\(", re.MULTILINE)
FETCH_RE = re.compile(r"fetch\(\s*(?:apiUrl\()?[`'\"]([^`'\"]+)[`'\"]")


def scan_js_file(path: Path):
    rel = str(path.relative_to(REPO_ROOT))
    try:
        src = path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return
    loc = src.count("\n") + 1
    node = Node(id=rel, label=path.name, type="file", group=area_for(rel), path=rel, loc=loc)
    node.functions = sorted(set(JS_FUNC_RE.findall(src)) | set(JS_CONST_FN_RE.findall(src)))
    fetch_paths = sorted(set(m for m in FETCH_RE.findall(src) if m.startswith("/")))
    node.meta["fetch_paths"] = fetch_paths
    add_node(node)


# ---------------------------------------------------------------------------
# 3) Escaneo de plantillas HTML (regex: <script src="...">)
# ---------------------------------------------------------------------------

SCRIPT_SRC_RE = re.compile(r'<script[^>]+src=["\']([^"\']+)["\']')


def scan_html_file(path: Path):
    rel = str(path.relative_to(REPO_ROOT))
    try:
        src = path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return
    loc = src.count("\n") + 1
    node = Node(id=rel, label=path.name, type="file", group=area_for(rel), path=rel, loc=loc)
    srcs = SCRIPT_SRC_RE.findall(src)
    node.meta["script_srcs"] = srcs
    add_node(node)


# ---------------------------------------------------------------------------
# 4) Escaneo de migraciones SQL (CREATE TABLE reales -> nodos "table")
# ---------------------------------------------------------------------------

CREATE_TABLE_RE = re.compile(
    r"CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?(?:public\.)?[\"`]?([a-zA-Z_][a-zA-Z0-9_]*)[\"`]?",
    re.IGNORECASE,
)


def scan_sql_file(path: Path, all_tables: set[str]):
    rel = str(path.relative_to(REPO_ROOT))
    try:
        src = path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return
    loc = src.count("\n") + 1
    tables_here = sorted(set(CREATE_TABLE_RE.findall(src)))
    node = Node(id=rel, label=path.name, type="file", group="database", path=rel, loc=loc)
    node.meta["creates_tables"] = tables_here
    add_node(node)
    for t in tables_here:
        all_tables.add(t)
        tid = f"table::{t}"
        if tid not in nodes:
            add_node(Node(id=tid, label=t, type="table", group="database"))
        add_edge(rel, tid, "db")


SQL_TABLE_MENTION_RE = re.compile(
    r"(?:FROM|INTO|UPDATE|JOIN|TABLE)\s+[\"`]?([a-zA-Z_][a-zA-Z0-9_]*)[\"`]?",
    re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# Orquestación
# ---------------------------------------------------------------------------

def main():
    print(f"[code-map] repo root: {REPO_ROOT}")
    if not PKG_ROOT.is_dir():
        print("ERROR: no se encontró RUANA/ en la raíz del repo. Aborta.", file=sys.stderr)
        sys.exit(1)

    py_files = list(iter_files(REPO_ROOT, {".py"}))
    js_files = list(iter_files(REPO_ROOT, {".js"}))
    html_files = list(iter_files(REPO_ROOT, {".html"}))
    sql_files = list(iter_files(REPO_ROOT / "supabase" / "migrations", {".sql"})) \
        if (REPO_ROOT / "supabase" / "migrations").is_dir() else []

    print(f"[code-map] archivos Python: {len(py_files)} | JS: {len(js_files)} | "
          f"HTML: {len(html_files)} | migraciones SQL: {len(sql_files)}")

    for f in py_files:
        scan_python_file(f)
    for f in js_files:
        scan_js_file(f)
    for f in html_files:
        scan_html_file(f)

    all_tables: set[str] = set()
    for f in sql_files:
        scan_sql_file(f, all_tables)

    # --- Edges 1: imports Python resueltos dentro del paquete ---
    unresolved_imports = 0
    for n in list(nodes.values()):
        if n.type != "file" or not n.id.endswith(".py"):
            continue
        raw = n.meta.pop("_raw_imports", [])
        for mod in raw:
            target = module_name_to_relpath(mod)
            if target and target in nodes:
                add_edge(n.id, target, "import")
            elif mod.split(".")[0] in ("core", "web", "engines", "utils", "events", "metrics"):
                unresolved_imports += 1

    # --- Edges 2: rutas Flask -> nodo "route", con arista "defines" ---
    for n in list(nodes.values()):
        if n.type != "file" or not n.routes:
            continue
        for r in n.routes:
            for method in r["methods"]:
                rid = f"route::{method}::{r['path']}"
                if rid not in nodes:
                    add_node(Node(
                        id=rid, label=f"{method} {r['path']}", type="route", group="api",
                        meta={"defined_in": n.id, "handler": r["handler"]},
                    ))
                add_edge(n.id, rid, "defines")

    # --- Edges 3: HTML -> JS (<script src>) ---
    for n in list(nodes.values()):
        if n.type != "file" or not n.id.endswith(".html"):
            continue
        for src_attr in n.meta.get("script_srcs", []):
            fname = src_attr.rstrip("/").split("/")[-1]
            for cand_id, cand in nodes.items():
                if cand.type == "file" and cand.id.endswith(".js") and Path(cand.id).name == fname:
                    add_edge(n.id, cand_id, "script")
                    break

    # --- Edges 4: JS fetch('/api/...') -> nodo route (match por path exacto o prefijo) ---
    # index por path (sin método) para matching
    path_to_route_ids: dict[str, list[str]] = {}
    for n in nodes.values():
        if n.type == "route":
            p = n.label.split(" ", 1)[1]
            path_to_route_ids.setdefault(p, []).append(n.id)

    for n in list(nodes.values()):
        if n.type != "file" or not n.id.endswith(".js"):
            continue
        for fp in n.meta.get("fetch_paths", []):
            # normaliza plantillas `${var}` a comodín simple para intentar match por prefijo
            base = re.split(r"[\$`]", fp)[0].rstrip("/")
            matched = False
            if fp in path_to_route_ids:
                for rid in path_to_route_ids[fp]:
                    add_edge(n.id, rid, "fetch")
                    matched = True
            if not matched and base:
                for p, ids in path_to_route_ids.items():
                    if p == base or p.startswith(base + "/"):
                        for rid in ids:
                            add_edge(n.id, rid, "fetch")

    # --- Edges 5: archivos .py que mencionan tablas reales (SQL crudo) -> nodo table ---
    if all_tables:
        for n in list(nodes.values()):
            if n.type != "file" or not n.id.endswith(".py"):
                continue
            src = n.meta.pop("_src", "")
            if not src:
                continue
            mentioned = set(SQL_TABLE_MENTION_RE.findall(src)) & all_tables
            for t in mentioned:
                add_edge(n.id, f"table::{t}", "db")
    else:
        for n in nodes.values():
            n.meta.pop("_src", None)

    # limpieza final de metadatos internos
    for n in nodes.values():
        n.meta.pop("_raw_imports", None)
        n.meta.pop("_src", None)

    # --- degree (para tamaño de nodo) ---
    degree = {nid: 0 for nid in nodes}
    for e in edges:
        degree[e.source] = degree.get(e.source, 0) + 1
        degree[e.target] = degree.get(e.target, 0) + 1

    # --- Health: ciclos de imports (grafo dirigido, solo aristas "import") ---
    import_adj: dict[str, list[str]] = {}
    for e in edges:
        if e.type == "import":
            import_adj.setdefault(e.source, []).append(e.target)

    cycles = find_cycles(import_adj)

    # --- Health: nodos aislados (sin ninguna arista) ---
    isolated = [nid for nid, d in degree.items() if d == 0 and nodes[nid].type == "file"]

    # --- Health: candidatos a no usados (archivo .py que nadie importa y no define rutas) ---
    imported_targets = {e.target for e in edges if e.type == "import"}
    entry_points = {"RUANA/web/app.py", "RUANA/web/run.py"}
    unused_candidates = [
        nid for nid, n in nodes.items()
        if n.type == "file" and nid.endswith(".py")
        and nid not in imported_targets
        and nid not in entry_points
        and not n.routes
        and "/tests/" not in nid and not Path(nid).name.startswith("test_")
        and not nid.endswith("__init__.py")
    ]

    # --- Health: módulos muy conectados (top 10 por grado) ---
    hot_modules = sorted(
        ({"id": nid, "label": nodes[nid].label, "degree": d} for nid, d in degree.items() if nodes[nid].type == "file"),
        key=lambda x: -x["degree"],
    )[:10]

    try:
        commit = subprocess.run(["git", "-C", str(REPO_ROOT), "rev-parse", "--short", "HEAD"],
                                 capture_output=True, text=True, timeout=5).stdout.strip()
    except Exception:
        commit = "unknown"

    out = {
        "generated_at": __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat(),
        "repo_commit": commit or "unknown",
        "nodes": [
            {
                "id": n.id, "label": n.label, "type": n.type, "group": n.group,
                "path": n.path, "loc": n.loc, "degree": degree.get(n.id, 0),
                "classes": n.classes, "functions": n.functions, "routes": n.routes,
                "meta": n.meta,
            }
            for n in nodes.values()
        ],
        "edges": [{"source": e.source, "target": e.target, "type": e.type} for e in edges],
        "health": {
            "cycles": cycles,
            "isolated_files": isolated,
            "unused_candidates": unused_candidates,
            "hot_modules": hot_modules,
            "unresolved_internal_imports": unresolved_imports,
        },
        "stats": {
            "total_nodes": len(nodes),
            "total_edges": len(edges),
            "python_files": sum(1 for n in nodes.values() if n.id.endswith(".py")),
            "js_files": sum(1 for n in nodes.values() if n.id.endswith(".js")),
            "html_files": sum(1 for n in nodes.values() if n.id.endswith(".html")),
            "routes": sum(1 for n in nodes.values() if n.type == "route"),
            "tables": sum(1 for n in nodes.values() if n.type == "table"),
            "total_loc": sum(n.loc for n in nodes.values() if n.type == "file"),
        },
    }

    OUT_FILE.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"[code-map] escrito: {OUT_FILE}")
    print(f"[code-map] nodos={out['stats']['total_nodes']} aristas={len(edges)} "
          f"ciclos={len(cycles)} aislados={len(isolated)} candidatos_sin_uso={len(unused_candidates)}")


def find_cycles(adj: dict[str, list[str]]) -> list[list[str]]:
    """DFS con pila para detectar ciclos simples en el grafo de imports."""
    WHITE, GRAY, BLACK = 0, 1, 2
    color = {n: WHITE for n in adj}
    for targets in adj.values():
        for t in targets:
            color.setdefault(t, WHITE)
    stack: list[str] = []
    on_stack_idx: dict[str, int] = {}
    found: list[list[str]] = []
    seen_cycle_keys = set()

    def dfs(u: str):
        color[u] = GRAY
        stack.append(u)
        on_stack_idx[u] = len(stack) - 1
        for v in adj.get(u, []):
            if color.get(v, WHITE) == WHITE:
                dfs(v)
            elif color.get(v) == GRAY:
                idx = on_stack_idx[v]
                cyc = stack[idx:] + [v]
                key = tuple(sorted(set(cyc)))
                if key not in seen_cycle_keys:
                    seen_cycle_keys.add(key)
                    found.append(cyc)
        stack.pop()
        del on_stack_idx[u]
        color[u] = BLACK

    for node in list(adj.keys()):
        if color.get(node, WHITE) == WHITE:
            dfs(node)
    return found[:50]  # límite de seguridad


if __name__ == "__main__":
    main()
