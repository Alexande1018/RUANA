#!/usr/bin/env python3
"""Eleva scores de aliados demo para capturas premium de landing."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent / "RUANA"
sys.path.insert(0, str(ROOT))

from core.db_manager import get_db  # noqa: E402

MANIFEST = Path(os.environ.get("RUANA_LANDING_MANIFEST", "/opt/cursor/artifacts/landing-demo-manifest.json"))
TARGET_SCORES = {
    "hero": 92,
    "ana": 78,
    "miguel": 88,
    "laura": 84,
    "javier": 76,
    "elena": 81,
    "retador": 85,
}


def _set_score_direct(db, codigo: str, score: int) -> None:
    conn = db._connect()
    try:
        conn.execute("UPDATE aliados SET score = ? WHERE codigo = ?", (score, codigo))
        conn.commit()
    finally:
        conn.close()


def main() -> None:
    if not MANIFEST.exists():
        raise SystemExit(f"Manifest no encontrado: {MANIFEST}")
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    db = get_db()
    for key, score in TARGET_SCORES.items():
        codigo = (manifest.get("allies", {}).get(key, {}) or {}).get("codigo")
        if not codigo:
            continue
        aliado = db.obtener_aliado_por_codigo(codigo)
        if not aliado:
            continue
        _set_score_direct(db, codigo, score)
        print(f"  {codigo} ({key}) -> objetivo {score}")
    print("Scores actualizados.")


if __name__ == "__main__":
    main()
