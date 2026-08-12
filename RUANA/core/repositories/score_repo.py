"""
Repositorio de Score RUANA.

Acceso a datos de score_movimientos, score de aliados y notificaciones de score.
Sin reglas de negocio: solo lectura/escritura.
"""

from __future__ import annotations

import json
from typing import Any, List, Optional, Sequence


class ScoreRepo:
    """Operaciones de persistencia del dominio score."""

    def obtener_score(self, cursor, codigo_aliado: str) -> Optional[int]:
        cursor.execute("SELECT score FROM aliados WHERE codigo = ?", (codigo_aliado,))
        row = cursor.fetchone()
        if not row:
            return None
        return int(row[0]) if row[0] is not None else 0

    def delta_score_hoy(self, cursor, codigo_aliado: str) -> int:
        """Suma de deltas aplicados hoy al aliado (para límite ±10/día)."""
        cursor.execute(
            """
            SELECT COALESCE(SUM(delta), 0) FROM score_movimientos
            WHERE codigo_aliado = ? AND date(creado_en) = date('now', 'localtime')
            """,
            (codigo_aliado,),
        )
        row = cursor.fetchone()
        return int(row[0]) if row else 0

    def existe_movimiento_motivo(self, cursor, codigo_aliado: str, motivo: str) -> bool:
        """True si ya existe un movimiento con ese motivo exacto para el aliado."""
        cursor.execute(
            "SELECT 1 FROM score_movimientos WHERE codigo_aliado = ? AND motivo = ? LIMIT 1",
            (codigo_aliado, motivo),
        )
        return cursor.fetchone() is not None

    def listar_motivos_score_con_prefijo(
        self, cursor, codigo_aliado: str, prefijo: str
    ) -> List[str]:
        """Motivos de score_movimientos cuyo texto empieza por prefijo (LIKE prefijo%)."""
        cursor.execute(
            """
            SELECT motivo FROM score_movimientos
            WHERE codigo_aliado = ? AND motivo LIKE ?
            """,
            (codigo_aliado, prefijo + "%"),
        )
        out: List[str] = []
        for row in cursor.fetchall():
            motivo = row[0] if not isinstance(row, dict) else row.get("motivo")
            out.append(str(motivo or ""))
        return out

    def insertar_movimiento(
        self,
        cursor,
        codigo_aliado: str,
        delta_real: int,
        motivo: str,
    ) -> Any:
        cursor.execute(
            """
            INSERT INTO score_movimientos (codigo_aliado, delta, motivo)
            VALUES (?, ?, ?)
            """,
            (codigo_aliado, delta_real, motivo),
        )
        return cursor.lastrowid

    def existe_penalizacion_aplicada(self, cursor, contacto_id: int, tipo: str) -> bool:
        """True si ya hay registro en contacto_penalizaciones_aplicadas."""
        cursor.execute(
            """
            SELECT 1 FROM contacto_penalizaciones_aplicadas
            WHERE contacto_id = ? AND tipo = ?
            """,
            (int(contacto_id), tipo),
        )
        return cursor.fetchone() is not None

    def insertar_penalizacion_aplicada(self, cursor, contacto_id: int, tipo: str) -> None:
        """Registra (idempotente) una penalización aplicada a un contacto."""
        cursor.execute(
            """
            INSERT OR IGNORE INTO contacto_penalizaciones_aplicadas (contacto_id, tipo)
            VALUES (?, ?)
            """,
            (int(contacto_id), tipo),
        )

    def listar_dias_acceso(
        self,
        cursor,
        codigo_aliado: str,
        dias: Optional[Sequence[str]] = None,
        desde_dia: Optional[str] = None,
    ) -> List[str]:
        """
        Días de acceso del aliado en aliado_accesos_dia.
        Si `dias` se indica, filtra por esos valores (IN).
        Si `desde_dia` se indica, filtra dia >= desde_dia.
        """
        codigo_aliado = (codigo_aliado or "").strip()
        if not codigo_aliado:
            return []
        if dias is not None:
            dias_list = [str(d) for d in dias if d]
            if not dias_list:
                return []
            placeholders = ",".join("?" * len(dias_list))
            cursor.execute(
                f"""
                SELECT dia FROM aliado_accesos_dia
                WHERE codigo_aliado = ? AND dia IN ({placeholders})
                """,
                (codigo_aliado, *dias_list),
            )
        elif desde_dia:
            cursor.execute(
                """
                SELECT dia FROM aliado_accesos_dia
                WHERE codigo_aliado = ? AND dia >= ?
                ORDER BY dia
                """,
                (codigo_aliado, str(desde_dia)[:10]),
            )
        else:
            cursor.execute(
                """
                SELECT dia FROM aliado_accesos_dia
                WHERE codigo_aliado = ?
                ORDER BY dia
                """,
                (codigo_aliado,),
            )
        return [str(r[0]) for r in cursor.fetchall()]

    def actualizar_score_aliado(self, cursor, codigo_aliado: str, score_nuevo: int) -> None:
        cursor.execute(
            """
            UPDATE aliados SET score = ?, actualizado_en = CURRENT_TIMESTAMP
            WHERE codigo = ?
            """,
            (score_nuevo, codigo_aliado),
        )

    def registrar_notificacion_cambio_score(
        self,
        cursor,
        codigo_aliado: str,
        delta_real: int,
        score_nuevo: int,
        motivo: str,
        movimiento_id: Optional[int] = None,
    ) -> None:
        """Crea una notificación persistente por cada cambio real de score."""
        if not codigo_aliado or not delta_real:
            return
        try:
            direccion = "subió" if delta_real > 0 else "bajó"
            puntos = f"{delta_real:+d}"
            motivo_txt = (motivo or "actualización de reglas RUANA").strip()
            titulo = "Cambio en tu Score RUANA"
            mensaje = f"Tu score {direccion} {puntos} puntos. Motivo: {motivo_txt}."
            metadata = json.dumps(
                {
                    "delta": delta_real,
                    "score_final": int(score_nuevo),
                    "motivo": motivo_txt,
                    "movimiento_id": movimiento_id,
                },
                ensure_ascii=False,
            )
            cursor.execute(
                """
                INSERT INTO notificaciones_aliado (aliado_codigo, tipo, titulo, mensaje, metadata, leida)
                VALUES (?, 'score_change', ?, ?, ?, 0)
                """,
                (codigo_aliado, titulo, mensaje, metadata),
            )
        except Exception:
            # No romper el flujo principal de score si falla la notificación
            return
