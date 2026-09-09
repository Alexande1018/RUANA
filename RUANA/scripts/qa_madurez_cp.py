#!/usr/bin/env python3
"""Inspección / dry-run (fase 1) de madurez territorial QA para un CP.

Por defecto NO inserta datos. La inserción exige autorización explícita y
sigue bloqueada en producción.

Uso:
  PYTHONPATH=RUANA python RUANA/scripts/qa_madurez_cp.py
  PYTHONPATH=RUANA python RUANA/scripts/qa_madurez_cp.py --cp 03001 --json
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

from core.db_manager import get_db  # noqa: E402
from core.qa_madurez_territorial import (  # noqa: E402
    CONFIRM_TOKEN,
    CP_OBJETIVO_DEFAULT,
    aplicar_plan,
    dry_run,
)


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description=(
            "Inspecciona el CP y muestra el dry-run de datos QA faltantes "
            "para la prueba de madurez territorial. No escribe nada por defecto."
        )
    )
    p.add_argument("--cp", default=CP_OBJETIVO_DEFAULT, help="Código postal objetivo")
    p.add_argument("--json", action="store_true", help="Salida JSON en lugar de texto")
    p.add_argument(
        "--apply",
        action="store_true",
        help="Insertar datos (BLOQUEADO salvo autorización explícita)",
    )
    p.add_argument(
        "--confirm",
        default="",
        help=f"Token de confirmación requerido para --apply ({CONFIRM_TOKEN})",
    )
    return p


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    db = get_db()

    if args.apply:
        resultado = aplicar_plan(db, args.cp, confirm_token=args.confirm)
        if args.json:
            print(json.dumps(resultado, ensure_ascii=False, indent=2, default=str))
        else:
            print(json.dumps(resultado, ensure_ascii=False, indent=2, default=str))
        if resultado.get("status") in ("blocked", "error", "integrity_error"):
            return 2
        return 0

    payload = dry_run(db, args.cp)
    if args.json:
        printable = dict(payload)
        printable.pop("reporte", None)
        print(json.dumps(printable, ensure_ascii=False, indent=2, default=str))
    else:
        print(payload["reporte"])
    if payload.get("bloqueos"):
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
