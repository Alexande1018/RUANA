#!/usr/bin/env python3
"""Extrae métodos de DBManager a core/services/<domain>_service.py dejando fachadas."""
from __future__ import annotations

import argparse
import ast
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DB_PATH = ROOT / "core" / "db_manager.py"


def extract(domain: str, methods: list[str], imports: str) -> None:
    src = DB_PATH.read_text(encoding="utf-8")
    tree = ast.parse(src)
    lines = src.splitlines(keepends=True)

    cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "DBManager")
    funcs = {
        item.name: item
        for item in cls.body
        if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    missing = [n for n in methods if n not in funcs]
    if missing:
        raise SystemExit(f"[{domain}] missing methods: {missing}")

    # Ensure import of service in db_manager
    import_line = f"from core.services import {domain}_service\n"
    if f"{domain}_service" not in src.split("from core.services import score_service")[0] + src:
        # add after score_service import if present
        if "from core.services import score_service\n" in src:
            src = src.replace(
                "from core.services import score_service\n",
                "from core.services import score_service\n" + import_line,
                1,
            )
            lines = src.splitlines(keepends=True)
            tree = ast.parse(src)
            cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "DBManager")
            funcs = {
                item.name: item
                for item in cls.body
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef))
            }
        else:
            # insert after negociacion_manager import
            needle = "from core import negociacion_manager as neg_mgr\n"
            if needle in src:
                src = src.replace(needle, needle + import_line, 1)
                lines = src.splitlines(keepends=True)
                tree = ast.parse(src)
                cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "DBManager")
                funcs = {
                    item.name: item
                    for item in cls.body
                    if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef))
                }

    extracted_blocks = []
    replacements = []

    for name in methods:
        node = funcs[name]
        start = node.lineno - 1
        if node.decorator_list:
            start = min(d.lineno for d in node.decorator_list) - 1
        end = node.end_lineno

        block_lines = lines[start:end]
        while block_lines and block_lines[0].lstrip().startswith("@"):
            # keep only non-staticmethod for now; drop decorators in service copy
            dec = block_lines[0].lstrip()
            if dec.startswith("@staticmethod"):
                block_lines = block_lines[1:]
                continue
            block_lines = block_lines[1:]

        dedented = []
        for l in block_lines:
            dedented.append(l[4:] if l.startswith("    ") else l)
        text_body = "".join(dedented)

        is_staticmethod = any(
            isinstance(d, ast.Name) and d.id == "staticmethod" for d in node.decorator_list
        )

        if is_staticmethod:
            service_fn = text_body
            # rebuild facade from original signature
            sig_start = node.lineno - 1
            sig_end = sig_start
            for k in range(sig_start, end):
                if lines[k].rstrip().endswith(":"):
                    sig_end = k
                    break
            # staticmethod with original args
            args = [a.arg for a in node.args.args]
            call = ", ".join(args)
            facade = "    @staticmethod\n" + "".join(lines[sig_start : sig_end + 1])
            if not facade.endswith("\n"):
                facade += "\n"
            facade += f'        """Fachada Campamento Base → {domain}_service.{name}."""\n'
            facade += f"        return {domain}_service.{name}({call})\n\n"
        else:
            text_body2 = re.sub(
                rf"def {re.escape(name)}\(\s*self\b",
                f"def {name}(db",
                text_body,
                count=1,
            )
            text_body2 = re.sub(r"\bself\b", "db", text_body2)
            service_fn = text_body2

            sig_start = node.lineno - 1
            sig_end = sig_start
            for k in range(sig_start, end):
                if lines[k].rstrip().endswith(":"):
                    sig_end = k
                    break
            sig = "".join(lines[sig_start : sig_end + 1])
            call_parts = ["self"]
            for a in node.args.args[1:]:
                call_parts.append(a.arg)
            if node.args.vararg:
                call_parts.append("*" + node.args.vararg.arg)
            for a in node.args.kwonlyargs:
                call_parts.append(f"{a.arg}={a.arg}")
            if node.args.kwarg:
                call_parts.append("**" + node.args.kwarg.arg)
            call = ", ".join(call_parts)
            facade = sig if sig.endswith("\n") else sig + "\n"
            facade += f'        """Fachada Campamento Base → {domain}_service.{name}."""\n'
            facade += f"        return {domain}_service.{name}({call})\n\n"

        extracted_blocks.append((node.lineno, name, service_fn))
        replacements.append((start, end, facade))

    replacements.sort(key=lambda x: x[0], reverse=True)
    new_lines = lines[:]
    for start, end, facade in replacements:
        new_lines[start:end] = [facade]

    DB_PATH.write_text("".join(new_lines), encoding="utf-8")

    svc_path = ROOT / "core" / "services" / f"{domain}_service.py"
    if svc_path.exists():
        existing = svc_path.read_text(encoding="utf-8").rstrip() + "\n"
    else:
        existing = (
            f'"""Servicio de dominio {domain} (Campamento Base).\n\n'
            f"Extracción progresiva desde DBManager. Las fachadas permanecen en DBManager.\n"
            f'"""\n'
            f"from __future__ import annotations\n\n"
            f"{imports}\n"
        )

    extracted_blocks.sort(key=lambda x: x[0])
    addon = [f"\n# --- Extraído de DBManager ({domain}) ---\n"]
    for _, _name, fn in extracted_blocks:
        addon.append("\n")
        addon.append(fn.rstrip() + "\n")
    svc_path.write_text(existing.rstrip() + "".join(addon) + "\n", encoding="utf-8")

    # Ensure import exists after rewrite
    final = DB_PATH.read_text(encoding="utf-8")
    if f"from core.services import {domain}_service" not in final:
        if "from core.services import score_service\n" in final:
            final = final.replace(
                "from core.services import score_service\n",
                "from core.services import score_service\n"
                f"from core.services import {domain}_service\n",
                1,
            )
        else:
            final = final.replace(
                "from core import negociacion_manager as neg_mgr\n",
                "from core import negociacion_manager as neg_mgr\n"
                f"from core.services import {domain}_service\n",
                1,
            )
        DB_PATH.write_text(final, encoding="utf-8")

    print(
        f"[{domain}] extracted {len(methods)} methods; "
        f"db_manager={len(final.splitlines())} "
        f"service={len(svc_path.read_text().splitlines())}"
    )


def main():
    # domains configured inline for this run
    extract(
        "negociacion",
        [
            "_iniciar_negociacion_en_cursor",
            "_insertar_evento_negociacion",
            "_cargar_contacto_negociacion",
            "listar_eventos_negociacion",
            "obtener_negociacion_contacto",
            "proponer_negociacion",
            "proponer_propuesta_completa_negociacion",
            "contraoferta_negociacion",
            "_precio_valor_desde_contacto",
            "_construir_acuerdo_resumen_json",
            "aceptar_negociacion",
            "cerrar_negociacion",
            "dismiss_resumen_acuerdo",
            "listar_negociaciones_admin",
            "eliminar_negociacion_admin",
        ],
        "import json\nimport sqlite3\nfrom typing import Any, Dict, List, Optional\n\n"
        "from core import negociacion_manager as neg_mgr\n",
    )


if __name__ == "__main__":
    main()
