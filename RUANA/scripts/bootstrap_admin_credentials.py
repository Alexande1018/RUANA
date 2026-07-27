#!/usr/bin/env python3
"""Migra credenciales admin legibles desde admin_codes.json a un archivo con hashes."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.admin_auth import bootstrap_from_legacy, get_credentials_path  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--legacy",
        type=Path,
        default=ROOT / "config" / "admin_codes.json",
        help="Ruta al archivo legado con códigos en texto plano",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Ruta de salida (por defecto .local-secrets/admin_credentials.json)",
    )
    args = parser.parse_args()

    try:
        output = bootstrap_from_legacy(args.legacy, args.output)
    except FileNotFoundError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    print(f"Credenciales migradas a: {output}")
    print("Elimina o conserva fuera del repositorio el archivo legado con contraseñas en texto plano.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
