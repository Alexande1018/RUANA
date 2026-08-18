"""Repositorio de automatización financiera: leases, ejecuciones y alertas (FASE 11)."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple


class FinancialAutomationRepo:
    MAX_LIMIT = 200

    def tabla_existe(self, cursor, nombre: str) -> bool:
        cursor.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=? LIMIT 1",
            (nombre,),
        )
        return cursor.fetchone() is not None

    def _now_iso(self) -> str:
        return datetime.now(timezone.utc).replace(microsecond=0).isoformat()

    def adquirir_lease(
        self,
        cursor,
        *,
        job_name: str,
        holder: str,
        ttl_seconds: int,
    ) -> bool:
        now = self._now_iso()
        expires = datetime.now(timezone.utc).timestamp() + max(30, int(ttl_seconds))
        expires_iso = datetime.fromtimestamp(expires, tz=timezone.utc).replace(microsecond=0).isoformat()
        cursor.execute(
            "DELETE FROM financial_job_leases WHERE job_name = ? AND expires_at < ?",
            (job_name, now),
        )
        cursor.execute(
            "SELECT holder, expires_at FROM financial_job_leases WHERE job_name = ?",
            (job_name,),
        )
        row = cursor.fetchone()
        if row:
            exp = row[1] if not hasattr(row, "keys") else row["expires_at"]
            if exp and str(exp) >= now:
                return False
            cursor.execute("DELETE FROM financial_job_leases WHERE job_name = ?", (job_name,))
        cursor.execute(
            """
            INSERT INTO financial_job_leases (job_name, holder, acquired_at, expires_at)
            VALUES (?, ?, ?, ?)
            """,
            (job_name, holder, now, expires_iso),
        )
        return cursor.rowcount == 1

    def liberar_lease(self, cursor, *, job_name: str, holder: str) -> bool:
        cursor.execute(
            "DELETE FROM financial_job_leases WHERE job_name = ? AND holder = ?",
            (job_name, holder),
        )
        return cursor.rowcount >= 0

    def insertar_run(
        self,
        cursor,
        *,
        run_id: str,
        job_name: str,
        actor: str,
    ) -> int:
        cursor.execute(
            """
            INSERT INTO financial_automation_runs (run_id, job_name, estado, actor)
            VALUES (?, ?, 'RUNNING', ?)
            """,
            (run_id, job_name, actor),
        )
        return int(cursor.lastrowid or 0)

    def finalizar_run(
        self,
        cursor,
        run_id: str,
        *,
        estado: str,
        metricas: Optional[Dict[str, Any]] = None,
        errores: Optional[List[str]] = None,
        alertas_nuevas: int = 0,
        alertas_actualizadas: int = 0,
        detalle: Optional[Dict[str, Any]] = None,
    ) -> None:
        cursor.execute(
            """
            UPDATE financial_automation_runs
            SET estado = ?, finalizado_en = CURRENT_TIMESTAMP,
                metricas_json = ?, errores_json = ?,
                alertas_nuevas = ?, alertas_actualizadas = ?,
                detalle_json = ?
            WHERE run_id = ?
            """,
            (
                estado,
                json.dumps(metricas or {}, ensure_ascii=False),
                json.dumps(errores or [], ensure_ascii=False),
                int(alertas_nuevas),
                int(alertas_actualizadas),
                json.dumps(detalle or {}, ensure_ascii=False),
                run_id,
            ),
        )

    def select_run(self, cursor, run_id: str) -> Optional[Dict[str, Any]]:
        cursor.execute("SELECT * FROM financial_automation_runs WHERE run_id = ?", (run_id,))
        return self._row(cursor.fetchone(), cursor)

    def listar_runs(self, cursor, *, limit: int = 50, offset: int = 0) -> List[Dict[str, Any]]:
        lim = max(1, min(int(limit), self.MAX_LIMIT))
        off = max(0, int(offset))
        cursor.execute(
            """
            SELECT * FROM financial_automation_runs
            ORDER BY id DESC LIMIT ? OFFSET ?
            """,
            (lim, off),
        )
        return [self._row(r, cursor) for r in cursor.fetchall() if r]

    def ultimo_run(self, cursor, job_name: str = "") -> Optional[Dict[str, Any]]:
        if job_name:
            cursor.execute(
                """
                SELECT * FROM financial_automation_runs
                WHERE job_name = ? ORDER BY id DESC LIMIT 1
                """,
                (job_name,),
            )
        else:
            cursor.execute(
                "SELECT * FROM financial_automation_runs ORDER BY id DESC LIMIT 1"
            )
        return self._row(cursor.fetchone(), cursor)

    def upsert_alerta(
        self,
        cursor,
        *,
        alert_key: str,
        tipo: str,
        severidad: str,
        contacto_id: Optional[int],
        accion_recomendada: str,
        accion_disponible: Optional[str],
        fuente: str,
        run_id: str,
        metadata: Optional[Dict[str, Any]] = None,
        fecha_evento: Optional[str] = None,
    ) -> Tuple[bool, int]:
        """Inserta o actualiza alerta. Devuelve (es_nueva, antiguedad_horas)."""
        now = fecha_evento or self._now_iso()
        meta = json.dumps(metadata or {}, ensure_ascii=False)
        cursor.execute("SELECT id, estado, fecha_primera_deteccion FROM financial_alerts WHERE alert_key = ?", (alert_key,))
        row = cursor.fetchone()
        if row:
            rid = row[0] if not hasattr(row, "keys") else row["id"]
            estado = row[1] if not hasattr(row, "keys") else row["estado"]
            primera = row[2] if not hasattr(row, "keys") else row["fecha_primera_deteccion"]
            if estado == "RESOLVED":
                return False, 0
            antig = self._horas_entre(primera, now)
            cursor.execute(
                """
                UPDATE financial_alerts
                SET fecha_ultima_deteccion = ?, antiguedad_horas = ?,
                    severidad = ?, run_id_ultima = ?, metadata_json = ?,
                    accion_recomendada = ?, accion_disponible = ?, contacto_id = COALESCE(?, contacto_id)
                WHERE alert_key = ? AND estado = 'OPEN'
                """,
                (now, antig, severidad, run_id, meta, accion_recomendada, accion_disponible, contacto_id, alert_key),
            )
            return False, antig
        antig = 0
        cursor.execute(
            """
            INSERT INTO financial_alerts (
                alert_key, tipo, severidad, contacto_id, estado,
                fecha_primera_deteccion, fecha_ultima_deteccion, antiguedad_horas,
                accion_recomendada, accion_disponible, fuente, metadata_json,
                run_id_primera, run_id_ultima
            ) VALUES (?, ?, ?, ?, 'OPEN', ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                alert_key, tipo, severidad, contacto_id,
                now, now, antig,
                accion_recomendada, accion_disponible, fuente, meta,
                run_id, run_id,
            ),
        )
        return True, antig

    def marcar_alerta_resuelta(self, cursor, alert_key: str, *, actor: str) -> bool:
        cursor.execute(
            """
            UPDATE financial_alerts
            SET estado = 'RESOLVED', resuelto_en = CURRENT_TIMESTAMP, resuelto_por = ?
            WHERE alert_key = ? AND estado = 'OPEN'
            """,
            (actor, alert_key),
        )
        return cursor.rowcount == 1

    def alerta_abierta(self, cursor, alert_key: str) -> bool:
        cursor.execute(
            "SELECT 1 FROM financial_alerts WHERE alert_key = ? AND estado = 'OPEN' LIMIT 1",
            (alert_key,),
        )
        return cursor.fetchone() is not None

    def listar_alertas_abiertas(self, cursor, *, limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
        lim = max(1, min(int(limit), self.MAX_LIMIT))
        off = max(0, int(offset))
        cursor.execute(
            """
            SELECT alert_key, tipo, severidad, contacto_id, estado,
                   fecha_primera_deteccion AS fecha, fecha_ultima_deteccion,
                   antiguedad_horas, accion_recomendada, accion_disponible, fuente,
                   metadata_json
            FROM financial_alerts
            WHERE estado = 'OPEN'
            ORDER BY
              CASE severidad WHEN 'critical' THEN 0 WHEN 'high' THEN 1 WHEN 'medium' THEN 2 ELSE 3 END,
              fecha_ultima_deteccion ASC
            LIMIT ? OFFSET ?
            """,
            (lim, off),
        )
        items = []
        for r in self._rows(cursor):
            meta = {}
            try:
                meta = json.loads(r.pop("metadata_json") or "{}")
            except (TypeError, json.JSONDecodeError):
                meta = {}
            r["alert_key"] = r.get("alert_key")
            if meta.get("deadline"):
                r["deadline"] = meta["deadline"]
            if meta.get("object_id"):
                r["object_id"] = meta["object_id"]
            items.append(r)
        return items

    def contar_alertas_abiertas(self, cursor) -> Dict[str, int]:
        cursor.execute(
            """
            SELECT severidad, COUNT(*) FROM financial_alerts
            WHERE estado = 'OPEN' GROUP BY severidad
            """
        )
        out = {"critical": 0, "high": 0, "medium": 0, "low": 0, "total": 0}
        for row in cursor.fetchall():
            sev = row[0] if not hasattr(row, "keys") else row["severidad"]
            cnt = int(row[1] if not hasattr(row, "keys") else row[1])
            key = str(sev or "low").lower()
            if key in out:
                out[key] = cnt
            out["total"] += cnt
        return out

    def _horas_entre(self, inicio: Any, fin: Any) -> int:
        try:
            a = datetime.fromisoformat(str(inicio).replace("Z", "+00:00"))
            b = datetime.fromisoformat(str(fin).replace("Z", "+00:00"))
            if a.tzinfo is None:
                a = a.replace(tzinfo=timezone.utc)
            if b.tzinfo is None:
                b = b.replace(tzinfo=timezone.utc)
            return max(0, int((b - a).total_seconds() // 3600))
        except (TypeError, ValueError):
            return 0

    def _rows(self, cursor) -> List[Dict[str, Any]]:
        return [self._row(r, cursor) for r in cursor.fetchall() if r]

    def _row(self, row, cursor) -> Optional[Dict[str, Any]]:
        if row is None:
            return None
        if hasattr(row, "keys"):
            return dict(row)
        names = [c[0] for c in cursor.description]
        return {names[i]: row[i] for i in range(len(row))}
