"""Operaciones admin no destructivas sobre un aliado (24 nov 2026).

* ``corregir_codigo_postal``: cambia solo el CP (5 dígitos) y resincroniza redes.
* ``dar_de_baja``: estado -> 'inactivo' (no borra datos ni libera código), lo saca
  de las redes (Red Centro y regionales) y marca su solicitud de baja como completada.
* ``reactivar``: deshace la baja (solo desde 'inactivo').
"""
from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

_CP_RE = re.compile(r"^\d{5}$")
ESTADO_BAJA = "inactivo"


def _ahora() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _sincronizar_redes(db, codigo: str) -> None:
    for mod_name in ("red_centro_service", "red_regional_service"):
        try:
            mod = __import__(f"core.services.{mod_name}", fromlist=["x"])
            mod.incorporar_tras_alta(db, codigo)
        except Exception:
            logger.exception("[RUANA][ADMIN_ESTADO] Fallo resincronizando %s", mod_name)


def _estado(cursor, codigo: str) -> Optional[str]:
    cursor.execute(
        "SELECT estado FROM aliados WHERE TRIM(CAST(codigo AS TEXT)) = ?", (codigo,)
    )
    row = cursor.fetchone()
    if not row:
        return None
    return str((row[0] if not hasattr(row, "keys") else row["estado"]) or "").strip().lower()


def _evento(db, cursor, tipo: str, descripcion: str, admin_codigo: Optional[str], meta: Dict[str, Any]) -> None:
    try:
        db._insert_evento_sistema(
            cursor, tipo=tipo, descripcion=descripcion, actor_tipo="admin",
            actor_codigo=admin_codigo, metadata=meta,
        )
    except Exception:
        logger.warning("[RUANA][ADMIN_ESTADO] No se pudo registrar el evento %s", tipo, exc_info=True)


def corregir_codigo_postal(db, codigo: str, codigo_postal: str, admin_codigo: Optional[str] = None) -> Dict[str, Any]:
    codigo = (codigo or "").strip()
    cp = (codigo_postal or "").strip()
    if not codigo:
        return {"status": "error", "message": "Código de aliado obligatorio"}
    if not _CP_RE.match(cp):
        return {"status": "error", "message": "El código postal debe tener 5 dígitos"}
    with db._lock:
        conn = db._connect()
        try:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT codigo_postal FROM aliados WHERE TRIM(CAST(codigo AS TEXT)) = ?", (codigo,)
            )
            row = cursor.fetchone()
            if not row:
                return {"status": "error", "message": f"Aliado {codigo} no encontrado"}
            anterior = str(row[0] or "")
            cursor.execute(
                "UPDATE aliados SET codigo_postal = ? WHERE TRIM(CAST(codigo AS TEXT)) = ?",
                (cp, codigo),
            )
            _evento(db, cursor, "aliado_cp_corregido",
                    f"CP de {codigo} corregido de {anterior} a {cp}", admin_codigo,
                    {"codigo_aliado": codigo, "cp_anterior": anterior, "cp_nuevo": cp})
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()
    _sincronizar_redes(db, codigo)
    return {"status": "success", "codigo": codigo, "cp_anterior": anterior, "codigo_postal": cp}


def dar_de_baja(db, codigo: str, motivo: str = "", admin_codigo: Optional[str] = None) -> Dict[str, Any]:
    codigo = (codigo or "").strip()
    if not codigo:
        return {"status": "error", "message": "Código de aliado obligatorio"}
    with db._lock:
        conn = db._connect()
        try:
            cursor = conn.cursor()
            estado = _estado(cursor, codigo)
            if estado is None:
                return {"status": "error", "message": f"Aliado {codigo} no encontrado"}
            if estado == "sistema":
                return {"status": "error", "message": "No se puede dar de baja un aliado del sistema"}
            cursor.execute(
                "UPDATE aliados SET estado = ? WHERE TRIM(CAST(codigo AS TEXT)) = ?",
                (ESTADO_BAJA, codigo),
            )
            # Sin SAVEPOINT: en producción el adaptador Postgres no los admite aquí.
            # Ambas tablas existen siempre (esquema de Red Centro y de bajas).
            cursor.execute(
                "DELETE FROM red_piloto_miembros WHERE TRIM(CAST(aliado_codigo AS TEXT)) = ?", (codigo,)
            )
            redes_borradas = int(getattr(cursor, "rowcount", 0) or 0)
            cursor.execute(
                "UPDATE solicitudes_baja_aliado SET estado = 'completada', "
                "actualizado_en = CURRENT_TIMESTAMP, admin_codigo = ? "
                "WHERE TRIM(CAST(codigo_aliado AS TEXT)) = ? AND estado IN ('pendiente', 'en_revision')",
                ((admin_codigo or None), codigo),
            )
            solicitudes = int(getattr(cursor, "rowcount", 0) or 0)
            _evento(db, cursor, "aliado_baja",
                    f"Aliado {codigo} dado de baja por admin", admin_codigo,
                    {"codigo_aliado": codigo, "estado_anterior": estado, "motivo": (motivo or "").strip()})
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()
    return {"status": "success", "codigo": codigo, "estado_anterior": estado, "estado": ESTADO_BAJA,
            "redes_miembro_borradas": redes_borradas, "solicitudes_baja_completadas": solicitudes}


def reactivar(db, codigo: str, admin_codigo: Optional[str] = None) -> Dict[str, Any]:
    codigo = (codigo or "").strip()
    with db._lock:
        conn = db._connect()
        try:
            cursor = conn.cursor()
            estado = _estado(cursor, codigo)
            if estado is None:
                return {"status": "error", "message": f"Aliado {codigo} no encontrado"}
            if estado != ESTADO_BAJA:
                return {"status": "error", "message": f"Solo se reactiva desde '{ESTADO_BAJA}' (está en '{estado}')"}
            cursor.execute(
                "UPDATE aliados SET estado = 'activo' WHERE TRIM(CAST(codigo AS TEXT)) = ?", (codigo,)
            )
            _evento(db, cursor, "aliado_reactivado", f"Aliado {codigo} reactivado por admin",
                    admin_codigo, {"codigo_aliado": codigo})
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()
    _sincronizar_redes(db, codigo)
    return {"status": "success", "codigo": codigo, "estado": "activo"}
