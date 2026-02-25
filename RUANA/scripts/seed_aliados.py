#!/usr/bin/env python3
"""
Script de datos semilla para RUANA.

Objetivo:
- Insertar EXACTAMENTE 4 aliados reales en SQLite, usando el mismo gestor de BD
  que el sistema (`core.db_manager.DBManager`), sin SQL crudo.
- Los códigos de acceso deben ser:
    - ALFA01
    - BETA02
    - GAMA03
    - DELTA04

Reglas:
- Si el aliado ya existe (mismo código) → no crear duplicado.
- El script puede ejecutarse múltiples veces sin romper nada (idempotente).
"""

from __future__ import annotations

import sys
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

from core.db_manager import get_db  # noqa: E402


ALIADOS_SEED = [
    {
        "codigo": "ALFA01",
        "nombre": "Aliado Alfa",
        "marca": "Servicios Alfa",
        "oficio": "Electricidad",
        "codigo_postal": "080001",
        "email": "alfa01@ruana.local",
        "telefono": "+34 600 100 001",
        "estado": "activo",
        "score": 78,
    },
    {
        "codigo": "BETA02",
        "nombre": "Aliado Beta",
        "marca": "Reformas Beta",
        "oficio": "Plomería",
        "codigo_postal": "080002",
        "email": "beta02@ruana.local",
        "telefono": "+34 600 100 002",
        "estado": "activo",
        "score": 72,
    },
    {
        "codigo": "GAMA03",
        "nombre": "Aliado Gama",
        "marca": "Carpintería Gama",
        "oficio": "Carpintería",
        "codigo_postal": "080003",
        "email": "gama03@ruana.local",
        "telefono": "+34 600 100 003",
        "estado": "activo",
        "score": 80,
    },
    {
        "codigo": "DELTA04",
        "nombre": "Aliado Delta",
        "marca": "Pinturas Delta",
        "oficio": "Pintura",
        "codigo_postal": "080004",
        "email": "delta04@ruana.local",
        "telefono": "+34 600 100 004",
        "estado": "activo",
        "score": 69,
    },
]


def seed_aliado(db, cfg: dict) -> None:
    """
    Inserta un aliado de semilla si no existe.

    Estrategia:
    - Buscar por código en SQLite.
    - Si existe → no hacer nada.
    - Si no existe → crear usando DBManager.crear_aliado_seed().
    """
    codigo = cfg["codigo"]

    existente = db.obtener_aliado_por_codigo(codigo)
    if existente:
        print(f"[SKIP] Aliado {codigo} ya existe (id={existente.get('id')})")
        return

    if not hasattr(db, "crear_aliado_seed"):
        raise SystemExit(
            "DBManager.crear_aliado_seed no existe. "
            "Asegúrate de haber actualizado core/db_manager.py."
        )

    resultado = db.crear_aliado_seed(
        codigo=codigo,
        nombre=cfg["nombre"],
        marca=cfg.get("marca", ""),
        oficio=cfg.get("oficio", ""),
        codigo_postal=cfg.get("codigo_postal", ""),
        email=cfg.get("email", ""),
        telefono=cfg.get("telefono", ""),
        estado=cfg.get("estado", "activo"),
        score=cfg.get("score", 0),
    )

    if resultado.get("status") != "success":
        print(f"[ERROR] No se pudo crear aliado {codigo}: {resultado.get('message')}")
        return

        msg_id = resultado.get('id')
        msg_score = resultado.get('score')
        print(f"[OK] Aliado {codigo} creado (id={msg_id}, score={msg_score})")


def main() -> None:
    db = get_db()
    print("=== RUANA Seed Aliados ===")
    for cfg in ALIADOS_SEED:
        seed_aliado(db, cfg)
    print("=== Fin seed aliados ===")


if __name__ == "__main__":
    main()
