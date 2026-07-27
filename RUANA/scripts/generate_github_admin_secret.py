#!/usr/bin/env python3
"""Genera el JSON (solo hashes) para el GitHub Secret RUANA_ADMIN_CREDENTIALS_JSON.

Uso (Cursor o local):
  python RUANA/scripts/generate_github_admin_secret.py --admin-id 7772735 --password '7772735'

Copia la salida en: GitHub → Settings → Secrets and variables → Actions → New repository secret
Nombre: RUANA_ADMIN_CREDENTIALS_JSON
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.admin_auth import _admin_record  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--admin-id", required=True, help="Identificador admin (ej. 7772735)")
    parser.add_argument("--password", required=True, help="Contraseña en claro (solo para generar el hash)")
    parser.add_argument("--nombre", default="", help="Nombre visible del administrador")
    parser.add_argument(
        "--permisos",
        default="leer,escribir,eliminar,configurar",
        help="Permisos separados por coma",
    )
    args = parser.parse_args()

    admin_id = args.admin_id.strip().upper()
    permisos = [p.strip() for p in args.permisos.split(",") if p.strip()]
    nombre = args.nombre.strip() or f"Admin {admin_id}"

    payload = {
        "version": 1,
        "admins": {
            admin_id: _admin_record(
                nombre=nombre,
                password=args.password,
                descripcion="Generado para GitHub Secret (solo hash en salida)",
                permisos=permisos,
            ),
        },
    }

    print(json.dumps(payload, ensure_ascii=False, separators=(",", ":")))
    print(
        "\n# Pegar en GitHub Secret: RUANA_ADMIN_CREDENTIALS_JSON",
        file=sys.stderr,
    )
    print("# La contraseña en claro NO está en el JSON de salida.", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
