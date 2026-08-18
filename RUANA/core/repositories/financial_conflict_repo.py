"""Repositorio formal de conflictos financieros (FASE 04)."""
from __future__ import annotations

import json
from typing import Any, Dict, List, Optional, Tuple

from core.financial.conflict_estados import (
    EstadoConflicto,
    TipoConflicto,
    normalizar_estado_conflicto,
)


class FinancialConflictRepo:
    """Persistencia de payment_conflicts evolucionado + evidencias + comentarios."""

    _ESTADOS_BLOQUEO_SQL = (
        "ABIERTO", "EN_INVESTIGACION", "PENDIENTE_DE_EVIDENCIA", "ESCALADO",
        "PENDIENTE_PRUEBA", "EN_REVISION",
    )

    def tabla_existe(self, cursor) -> bool:
        cursor.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='payment_conflicts' LIMIT 1"
        )
        return cursor.fetchone() is not None

    def _columnas(self, cursor, tabla: str = "payment_conflicts") -> set:
        cursor.execute(f"PRAGMA table_info({tabla})")
        return {row[1] for row in cursor.fetchall()}

    def tiene_conflicto_bloqueante(self, cursor, contacto_id: int) -> bool:
        if not self.tabla_existe(cursor):
            return self._legacy_disputa_contacto(cursor, contacto_id)
        columnas = self._columnas(cursor)
        if "estado_conflicto" in columnas:
            cursor.execute(
                """
                SELECT estado_conflicto, estado, bloqueo_financiero
                FROM payment_conflicts WHERE trabajo_id = ?
                ORDER BY id DESC
                """,
                (contacto_id,),
            )
            for row in cursor.fetchall():
                if hasattr(row, "keys"):
                    ec_raw, leg, bf = row["estado_conflicto"], row["estado"], row["bloqueo_financiero"]
                else:
                    ec_raw, leg, bf = row[0], row[1], row[2]
                ec = normalizar_estado_conflicto(ec_raw, leg)
                if ec and EstadoConflicto.bloquea_financiero(ec):
                    return True
                if ec in (EstadoConflicto.RESUELTO, EstadoConflicto.CERRADO):
                    continue
                if (leg or "").upper() in ("PENDIENTE_PRUEBA", "EN_REVISION"):
                    return True
        else:
            cursor.execute(
                """
                SELECT 1 FROM payment_conflicts
                WHERE trabajo_id = ? AND estado IN ('PENDIENTE_PRUEBA', 'EN_REVISION')
                LIMIT 1
                """,
                (contacto_id,),
            )
            if cursor.fetchone():
                return True
        return self._legacy_disputa_contacto(cursor, contacto_id)

    def _legacy_disputa_contacto(self, cursor, contacto_id: int) -> bool:
        cursor.execute("SELECT estado, estado_financiero FROM contactos_ruana WHERE id = ?", (contacto_id,))
        row = cursor.fetchone()
        if not row:
            return False
        if hasattr(row, "keys"):
            estado_raw, ef_raw = row["estado"], row["estado_financiero"]
        else:
            estado_raw, ef_raw = row[0], row[1]
        estado = (estado_raw or "").strip().lower()
        ef = (ef_raw or "").strip().upper()
        return estado == "importe_en_disputa" or ef == "CONFLICTO_ABIERTO"

    def select_activo_por_contacto(self, cursor, contacto_id: int) -> Optional[Dict[str, Any]]:
        if not self.tabla_existe(cursor):
            return None
        columnas = self._columnas(cursor)
        extra = [c for c in (
            "estado_conflicto", "tipo_conflicto", "motivo", "importe_reclamado_cents", "moneda",
            "abierto_por", "responsable_codigo", "prioridad", "fecha_apertura", "fecha_asignacion",
            "fecha_resolucion", "resolucion", "importe_liberar_cents", "importe_reembolsar_cents",
            "importe_profesional_cents", "importe_contratante_cents", "bloqueo_financiero",
            "version", "tipo", "stripe_payment_intent_id",
        ) if c in columnas]
        extra_sql = (", " + ", ".join(extra)) if extra else ""
        cursor.execute(
            f"""
            SELECT id, trabajo_id, contratante_id, profesional_id,
                   importe_contratante, importe_profesional, estado,
                   prueba_url, comentario_admin, created_at, updated_at{extra_sql}
            FROM payment_conflicts
            WHERE trabajo_id = ?
              AND (
                estado_conflicto IN ('ABIERTO','EN_INVESTIGACION','PENDIENTE_DE_EVIDENCIA','ESCALADO','RESUELTO')
                OR estado IN ('PENDIENTE_PRUEBA','EN_REVISION','RESUELTO')
              )
            ORDER BY id DESC LIMIT 1
            """,
            (contacto_id,),
        )
        row = cursor.fetchone()
        return self._fetch_dict(cursor, row) if row else None

    def _fetch_dict(self, cursor, row) -> Dict[str, Any]:
        if row is None:
            return {}
        if hasattr(row, "keys"):
            d = dict(row)
        else:
            names = [col[0] for col in cursor.description]
            d = {names[i]: row[i] for i in range(len(row))}
        ec = normalizar_estado_conflicto(d.get("estado_conflicto"), d.get("estado"))
        if ec:
            d["estado_conflicto"] = ec.value
            d["bloqueo_financiero_activo"] = (
                ec.value in (
                    EstadoConflicto.ABIERTO.value, EstadoConflicto.EN_INVESTIGACION.value,
                    EstadoConflicto.PENDIENTE_DE_EVIDENCIA.value, EstadoConflicto.ESCALADO.value,
                ) or d.get("bloqueo_financiero", 1)
            )
        return d

    def select_por_id(self, cursor, conflict_id: int) -> Optional[Dict[str, Any]]:
        if not self.tabla_existe(cursor):
            return None
        cursor.execute("SELECT * FROM payment_conflicts WHERE id = ?", (conflict_id,))
        row = cursor.fetchone()
        return self._fetch_dict(cursor, row) if row else None

    def insertar_conflicto(
        self,
        cursor,
        *,
        contacto_id: int,
        contratante_id: int,
        profesional_id: int,
        tipo: TipoConflicto,
        motivo: str,
        abierto_por: str,
        importe_reclamado_cents: int = 0,
        moneda: str = "eur",
        idempotency_key: str = "",
        legacy_estado: str = "PENDIENTE_PRUEBA",
        importe_contratante: float = 0,
        importe_profesional: float = 0,
        stripe_payment_intent_id: str = "",
        legacy_tipo: str = "",
    ) -> Tuple[str, Optional[Dict[str, Any]]]:
        columnas = self._columnas(cursor)
        tipo_legacy = legacy_tipo or tipo.value.lower()
        if "estado_conflicto" in columnas:
            cursor.execute(
                """
                INSERT OR IGNORE INTO payment_conflicts (
                    trabajo_id, contratante_id, profesional_id,
                    importe_contratante, importe_profesional,
                    estado, tipo, estado_conflicto, tipo_conflicto, motivo,
                    importe_reclamado_cents, moneda, abierto_por,
                    bloqueo_financiero, version, fecha_apertura,
                    stripe_payment_intent_id, idempotency_key_apertura
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, 1, CURRENT_TIMESTAMP, ?, ?)
                """,
                (
                    contacto_id, contratante_id, profesional_id,
                    importe_contratante, importe_profesional,
                    legacy_estado, tipo_legacy, EstadoConflicto.ABIERTO.value, tipo.value,
                    motivo[:2000], importe_reclamado_cents, moneda, abierto_por,
                    stripe_payment_intent_id or None, idempotency_key or None,
                ),
            )
        else:
            cursor.execute(
                """
                INSERT OR IGNORE INTO payment_conflicts (
                    trabajo_id, contratante_id, profesional_id,
                    importe_contratante, importe_profesional, estado, tipo, comentario_admin
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    contacto_id, contratante_id, profesional_id,
                    importe_contratante, importe_profesional,
                    legacy_estado, tipo_legacy, motivo[:2000],
                ),
            )
        if cursor.rowcount > 0:
            return "created", self.select_activo_por_contacto(cursor, contacto_id)
        self._formalizar_existente(
            cursor, contacto_id, tipo, motivo, abierto_por,
            importe_reclamado_cents, moneda,
        )
        return "existing", self.select_activo_por_contacto(cursor, contacto_id)

    def _formalizar_existente(
        self, cursor, contacto_id: int, tipo: TipoConflicto, motivo: str,
        abierto_por: str, importe_reclamado_cents: int, moneda: str,
    ) -> None:
        columnas = self._columnas(cursor)
        if "estado_conflicto" not in columnas:
            return
        sets = [
            "estado_conflicto = COALESCE(estado_conflicto, ?)",
            "tipo_conflicto = COALESCE(tipo_conflicto, ?)",
            "motivo = COALESCE(motivo, ?)",
            "abierto_por = COALESCE(abierto_por, ?)",
            "bloqueo_financiero = 1",
            "updated_at = CURRENT_TIMESTAMP",
        ]
        params = [EstadoConflicto.ABIERTO.value, tipo.value, motivo[:2000], abierto_por]
        if "importe_reclamado_cents" in columnas and importe_reclamado_cents:
            sets.append("importe_reclamado_cents = COALESCE(importe_reclamado_cents, ?)")
            params.append(importe_reclamado_cents)
        if "moneda" in columnas:
            sets.append("moneda = COALESCE(moneda, ?)")
            params.append(moneda)
        if "fecha_apertura" in columnas:
            sets.append("fecha_apertura = COALESCE(fecha_apertura, CURRENT_TIMESTAMP)")
        params.append(contacto_id)
        cursor.execute(
            f"UPDATE payment_conflicts SET {', '.join(sets)} WHERE trabajo_id = ?",
            params,
        )

    def transicionar_estado_cas(
        self,
        cursor,
        conflict_id: int,
        estado_esperado: str,
        estado_nuevo: str,
        *,
        responsable_codigo: str = "",
        version_esperada: int = 0,
    ) -> bool:
        columnas = self._columnas(cursor)
        sets = ["estado_conflicto = ?", "updated_at = CURRENT_TIMESTAMP"]
        params: list = [estado_nuevo]
        legacy = {"ABIERTO": "PENDIENTE_PRUEBA", "EN_INVESTIGACION": "EN_REVISION",
                  "PENDIENTE_DE_EVIDENCIA": "PENDIENTE_PRUEBA", "ESCALADO": "EN_REVISION",
                  "RESUELTO": "RESUELTO", "CERRADO": "RESUELTO"}
        if "estado" in columnas and estado_nuevo in legacy:
            sets.append("estado = ?")
            params.append(legacy[estado_nuevo])
        if responsable_codigo and "responsable_codigo" in columnas:
            sets.append("responsable_codigo = ?")
            sets.append("fecha_asignacion = CURRENT_TIMESTAMP")
            params.append(responsable_codigo)
        bloquea = estado_nuevo in (
            EstadoConflicto.ABIERTO.value, EstadoConflicto.EN_INVESTIGACION.value,
            EstadoConflicto.PENDIENTE_DE_EVIDENCIA.value, EstadoConflicto.ESCALADO.value,
        )
        if "bloqueo_financiero" in columnas:
            sets.append("bloqueo_financiero = ?")
            params.append(1 if bloquea else 0)
        if "version" in columnas:
            sets.append("version = version + 1")
        params.extend([conflict_id, estado_esperado])
        where = "id = ? AND estado_conflicto = ?"
        if "version" in columnas and version_esperada:
            where += " AND version = ?"
            params.append(version_esperada)
        cursor.execute(
            f"UPDATE payment_conflicts SET {', '.join(sets)} WHERE {where}",
            params,
        )
        return cursor.rowcount == 1

    def aplicar_resolucion_cas(
        self,
        cursor,
        conflict_id: int,
        *,
        estado_esperado: str,
        estado_nuevo: str,
        resolucion: str,
        version_esperada: int,
        importe_liberar_cents: int = 0,
        importe_reembolsar_cents: int = 0,
        importe_profesional_cents: int = 0,
        importe_contratante_cents: int = 0,
        comentario: str = "",
    ) -> bool:
        columnas = self._columnas(cursor)
        sets = [
            "estado_conflicto = ?", "resolucion = ?", "fecha_resolucion = CURRENT_TIMESTAMP",
            "updated_at = CURRENT_TIMESTAMP", "estado = 'RESUELTO'",
        ]
        params: list = [estado_nuevo, resolucion]
        for col, val in (
            ("importe_liberar_cents", importe_liberar_cents),
            ("importe_reembolsar_cents", importe_reembolsar_cents),
            ("importe_profesional_cents", importe_profesional_cents),
            ("importe_contratante_cents", importe_contratante_cents),
        ):
            if col in columnas:
                sets.append(f"{col} = ?")
                params.append(val)
        if comentario and "comentario_admin" in columnas:
            sets.append("comentario_admin = ?")
            params.append(comentario[:2000])
        bloquea = estado_nuevo not in (EstadoConflicto.CERRADO.value, EstadoConflicto.RESUELTO.value)
        if "bloqueo_financiero" in columnas:
            sets.append("bloqueo_financiero = ?")
            params.append(1 if bloquea else 0)
        if "version" in columnas:
            sets.append("version = version + 1")
        params.extend([conflict_id, estado_esperado, version_esperada])
        cursor.execute(
            f"""
            UPDATE payment_conflicts SET {', '.join(sets)}
            WHERE id = ? AND estado_conflicto = ? AND version = ?
            """,
            params,
        )
        return cursor.rowcount == 1

    def cerrar_conflicto_cas(
        self, cursor, conflict_id: int, estado_esperado: str, version_esperada: int,
    ) -> bool:
        return self.transicionar_estado_cas(
            cursor, conflict_id, estado_esperado, EstadoConflicto.CERRADO.value,
            version_esperada=version_esperada,
        ) and self._set_bloqueo(cursor, conflict_id, 0)

    def _set_bloqueo(self, cursor, conflict_id: int, valor: int) -> bool:
        columnas = self._columnas(cursor)
        if "bloqueo_financiero" not in columnas:
            return True
        cursor.execute(
            "UPDATE payment_conflicts SET bloqueo_financiero = ? WHERE id = ?",
            (valor, conflict_id),
        )
        return cursor.rowcount == 1

    def reclamar_accion(
        self, cursor, conflict_id: int, operacion: str, idempotency_key: str, actor: str,
    ) -> Tuple[str, Optional[int]]:
        cursor.execute(
            """
            INSERT OR IGNORE INTO payment_conflict_actions (
                conflicto_id, operacion, idempotency_key, actor_codigo, resultado
            ) VALUES (?, ?, ?, ?, 'en_proceso')
            """,
            (conflict_id, operacion, idempotency_key, actor),
        )
        if cursor.rowcount > 0:
            return "claimed", cursor.lastrowid
        cursor.execute(
            """
            SELECT id, resultado FROM payment_conflict_actions
            WHERE conflicto_id = ? AND operacion = ? AND idempotency_key = ?
            """,
            (conflict_id, operacion, idempotency_key),
        )
        row = cursor.fetchone()
        if row:
            rid = row[0] if not hasattr(row, "keys") else row["id"]
            return "duplicate", rid
        return "error", None

    def finalizar_accion(self, cursor, action_id: int, resultado: str, metadata: Optional[Dict] = None) -> None:
        cursor.execute(
            """
            UPDATE payment_conflict_actions
            SET resultado = ?, metadata_json = ?, actualizado_en = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (resultado, json.dumps(metadata or {}, ensure_ascii=False), action_id),
        )

    def insertar_evidencia(
        self,
        cursor,
        conflict_id: int,
        *,
        tipo: str,
        nombre: str,
        referencia: str,
        subido_por: str,
        hash_val: str = "",
        metadata: Optional[Dict] = None,
    ) -> int:
        cursor.execute(
            """
            INSERT INTO payment_conflict_evidence (
                conflicto_id, tipo, nombre, referencia_segura, hash_sha256,
                subido_por, metadata_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                conflict_id, tipo, nombre[:500], referencia[:2000], hash_val[:128],
                subido_por, json.dumps(metadata or {}, ensure_ascii=False),
            ),
        )
        return cursor.lastrowid

    def listar_evidencias(self, cursor, conflict_id: int) -> List[Dict[str, Any]]:
        cursor.execute(
            """
            SELECT id, conflicto_id, tipo, nombre, referencia_segura, hash_sha256,
                   subido_por, creado_en, metadata_json
            FROM payment_conflict_evidence
            WHERE conflicto_id = ? AND eliminado_en IS NULL
            ORDER BY id ASC
            """,
            (conflict_id,),
        )
        return [self._row_dict(r) for r in cursor.fetchall()]

    def insertar_comentario(
        self,
        cursor,
        conflict_id: int,
        *,
        autor: str,
        texto: str,
        visible_contratante: bool = True,
        visible_profesional: bool = True,
    ) -> int:
        cursor.execute(
            """
            INSERT INTO payment_conflict_comments (
                conflicto_id, autor_codigo, texto,
                visible_para_contratante, visible_para_profesional
            ) VALUES (?, ?, ?, ?, ?)
            """,
            (conflict_id, autor, texto[:4000], int(visible_contratante), int(visible_profesional)),
        )
        return cursor.lastrowid

    def listar_comentarios(self, cursor, conflict_id: int) -> List[Dict[str, Any]]:
        cursor.execute(
            """
            SELECT id, conflicto_id, autor_codigo, texto, creado_en,
                   visible_para_contratante, visible_para_profesional
            FROM payment_conflict_comments
            WHERE conflicto_id = ?
            ORDER BY id ASC
            """,
            (conflict_id,),
        )
        return [self._row_dict(r) for r in cursor.fetchall()]

    def listar_auditoria(self, cursor, conflict_id: int) -> List[Dict[str, Any]]:
        cursor.execute(
            """
            SELECT id, conflicto_id, accion, actor_codigo, estado_anterior, estado_nuevo,
                   metadata_json, creado_en
            FROM payment_conflict_audit
            WHERE conflicto_id = ?
            ORDER BY id DESC
            """,
            (conflict_id,),
        )
        return [self._row_dict(r) for r in cursor.fetchall()]

    def listar_conflictos(
        self,
        cursor,
        *,
        estado: str = "",
        limite: int = 100,
        offset: int = 0,
    ) -> List[Dict[str, Any]]:
        if not self.tabla_existe(cursor):
            return []
        where = ""
        params: list = []
        if estado:
            where = "WHERE pc.estado_conflicto = ?"
            params.append(estado.strip().upper())
        params.extend([limite, offset])
        cursor.execute(
            f"""
            SELECT pc.*,
                   ac.nombre AS contratante_nombre,
                   ap.nombre AS profesional_nombre,
                   ac.codigo AS contratante_codigo,
                   ap.codigo AS profesional_codigo
            FROM payment_conflicts pc
            LEFT JOIN aliados ac ON ac.id = pc.contratante_id
            LEFT JOIN aliados ap ON ap.id = pc.profesional_id
            {where}
            ORDER BY pc.created_at DESC, pc.id DESC
            LIMIT ? OFFSET ?
            """,
            params,
        )
        rows = []
        for r in cursor.fetchall():
            d = self._fetch_dict(cursor, r)
            rows.append(d)
        return rows

    def obtener_detalle_completo(self, cursor, conflict_id: int) -> Optional[Dict[str, Any]]:
        base = self.select_por_id(cursor, conflict_id)
        if not base:
            return None
        cursor.execute(
            """
            SELECT ac.nombre AS contratante_nombre, ap.nombre AS profesional_nombre,
                   ac.codigo AS contratante_codigo, ap.codigo AS profesional_codigo
            FROM payment_conflicts pc
            LEFT JOIN aliados ac ON ac.id = pc.contratante_id
            LEFT JOIN aliados ap ON ap.id = pc.profesional_id
            WHERE pc.id = ?
            """,
            (conflict_id,),
        )
        row = cursor.fetchone()
        if row:
            if hasattr(row, "keys"):
                base.update({k: row[k] for k in row.keys()})
            else:
                names = [c[0] for c in cursor.description]
                base.update({names[i]: row[i] for i in range(len(row))})
        base["evidencias"] = self.listar_evidencias(cursor, conflict_id)
        base["comentarios"] = self.listar_comentarios(cursor, conflict_id)
        return base

    def asignar_responsable_cas(
        self,
        cursor,
        conflict_id: int,
        *,
        responsable_codigo: str,
        estado_esperado: str,
        version_esperada: int,
    ) -> bool:
        columnas = self._columnas(cursor)
        if "responsable_codigo" not in columnas:
            return False
        sets = [
            "responsable_codigo = ?",
            "fecha_asignacion = CURRENT_TIMESTAMP",
            "updated_at = CURRENT_TIMESTAMP",
        ]
        params: list = [responsable_codigo]
        if "version" in columnas:
            sets.append("version = version + 1")
        params.extend([conflict_id, estado_esperado, version_esperada])
        where = "id = ? AND estado_conflicto = ? AND version = ?"
        cursor.execute(
            f"UPDATE payment_conflicts SET {', '.join(sets)} WHERE {where}",
            params,
        )
        return cursor.rowcount == 1

    def listar_acciones_pendientes(self, cursor, conflict_id: int) -> List[Dict[str, Any]]:
        row = self.select_por_id(cursor, conflict_id)
        if not row:
            return []
        resolucion = (row.get("resolucion") or "").strip()
        if not resolucion:
            return []
        if resolucion in ("MANTENER_RETENIDO", "ESCALAR_ADMIN"):
            return []
        ec = normalizar_estado_conflicto(row.get("estado_conflicto"), row.get("estado"))
        if not ec or ec not in (EstadoConflicto.RESUELTO, EstadoConflicto.CERRADO):
            return []
        return [{
            "conflicto_id": conflict_id,
            "tipo": resolucion,
            "importe_liberar_cents": int(row.get("importe_liberar_cents") or 0),
            "importe_reembolsar_cents": int(row.get("importe_reembolsar_cents") or 0),
            "importe_profesional_cents": int(row.get("importe_profesional_cents") or 0),
            "importe_contratante_cents": int(row.get("importe_contratante_cents") or 0),
            "moneda": (row.get("moneda") or "eur").lower(),
            "estado": "pendiente_ejecucion",
            "orden_financiera_pendiente": True,
        }]

    def registrar_auditoria(
        self,
        cursor,
        conflict_id: int,
        *,
        accion: str,
        actor: str,
        estado_anterior: str,
        estado_nuevo: str,
        metadata: Optional[Dict] = None,
    ) -> None:
        cursor.execute(
            """
            INSERT INTO payment_conflict_audit (
                conflicto_id, accion, actor_codigo, estado_anterior, estado_nuevo, metadata_json
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                conflict_id, accion, actor, estado_anterior, estado_nuevo,
                json.dumps(metadata or {}, ensure_ascii=False),
            ),
        )

    def _row_dict(self, row, columnas: Optional[set] = None) -> Dict[str, Any]:
        if row is None:
            return {}
        if hasattr(row, "keys"):
            d = dict(row)
        else:
            names = list(columnas or [])
            d = {names[i]: row[i] for i in range(min(len(row), len(names)))}
        ec = normalizar_estado_conflicto(d.get("estado_conflicto"), d.get("estado"))
        if ec:
            d["estado_conflicto"] = ec.value
            d["bloqueo_financiero_activo"] = (
                ec.value in (
                    EstadoConflicto.ABIERTO.value, EstadoConflicto.EN_INVESTIGACION.value,
                    EstadoConflicto.PENDIENTE_DE_EVIDENCIA.value, EstadoConflicto.ESCALADO.value,
                ) or d.get("bloqueo_financiero", 1)
            )
        return d
