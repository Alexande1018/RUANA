#!/usr/bin/env python3
"""
Script para ejecutar la purga mensual de RUANA (cron).

- Finaliza competencias vencidas.
- Aplica reglas de pool: aliados en segunda oportunidad que no ganan en N meses
  o con score bajo → expulsión temporal (suspendido_temporal).

Ejecutar el primer día de cada mes, por ejemplo vía cron:
  0 2 1 * * /usr/bin/env python3 /ruta/a/RUANA/scripts/purga_mensual.py >> /ruta/a/RUANA/logs/purga_mensual.log 2>&1
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

from core.db_manager import get_db  # noqa: E402


def main() -> int:
    db = get_db()
    resultado = db.purga_mensual()
    print(json.dumps(resultado, ensure_ascii=False, indent=2))
    return 0 if resultado.get("status") == "ok" else 1


if __name__ == "__main__":
    sys.exit(main())
