"""Difusión de avisos del admin por el centro de comunicación.

Capa aditiva: crea o reutiliza la conversación de aviso de cada aliado
activo y deja el mensaje como no leído, igual que una respuesta manual
del equipo (`tiene_no_leido_aliado = 1` y notificación in-app
`ruana_soporte`). No envía email ni push. No toca Score, pagos,
comisiones ni competencia.

Todo el envío real va en una sola transacción: si falla a mitad, no
queda a medio aplicar.
"""
from __future__ import annotations

import json
import logging
import sqlite3
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Sequence, Tuple

logger = logging.getLogger(__name__)

TEXTO_MAX = 2000
EXCERPT_LEN = 120
INTERVALO_SEGUNDOS = 3600
CODIGOS_MAX = 500
CATEGORIA_AVISO = "aviso"
TIPO_AVISO = "aviso"
TIPO_EVENTO = "difusion_centro_comunicacion"
ASUNTO_AVISO = "Mensaje del equipo RUANA"
# Solo aliados operativos. No hay flag genérico de «cuenta de prueba» en el
# código; se excluyen los estados no activos (sistema, expulsado, en espera,
# pendiente de validación, suspendido, etc.).
ESTADO_DESTINO = "activo"

_FILTROS = ("codigos", "grupo_id", "prefijo_cp")


def _ahora() -> datetime:
    return datetime.now(timezone.utc)


def _parse_ts(value) -> Optional[datetime]:
    if not value:
        return None
    if isinstance(value, datetime):
        dt = value
    elif isinstance(value, str):
        raw = value.strip()
        if not raw:
            return None
        normalized = raw.replace("Z", "+00:00")
        dt = None
        try:
            dt = datetime.fromisoformat(normalized)
        except ValueError:
            s = normalized.replace("T", " ")[:19]
            for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
                try:
                    dt = datetime.strptime(s, fmt)
                    break
                except ValueError:
                    continue
        if dt is None:
            return None
    else:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _dict(row: Any) -> Dict[str, Any]:
    if row is None:
        return {}
    return dict(row) if not isinstance(row, dict) else row


def _excerpt(texto: str) -> str:
    t = " ".join((texto or "").split())
    if len(t) <= EXCERPT_LEN:
        return t
    return t[: EXCERPT_LEN - 1].rstrip() + "…"


def _validar_entrada(data: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(data, dict):
        return {"status": "error", "http": 400, "message": "Cuerpo JSON requerido."}
    texto = str(data.get("texto") or "").strip()
    if not texto:
        return {"status": "error", "http": 400, "message": "El texto del aviso es obligatorio."}
    if len(texto) > TEXTO_MAX:
        return {
            "status": "error",
            "http": 400,
            "message": f"El texto no puede superar {TEXTO_MAX} caracteres.",
        }

    filtro_in = data.get("filtro") if isinstance(data.get("filtro"), dict) else {}
    raw = {
        "codigos": data.get("codigos", filtro_in.get("codigos")),
        "grupo_id": data.get("grupo_id", filtro_in.get("grupo_id")),
        "prefijo_cp": data.get("prefijo_cp", filtro_in.get("prefijo_cp")),
    }
    presentes = []
    for k, v in raw.items():
        if v is None:
            continue
        if k == "codigos":
            # Una lista vacía cuenta como filtro (error, no como "todos").
            presentes.append(k)
        elif v not in ("", [], ()):
            presentes.append(k)
    if len(presentes) > 1:
        return {
            "status": "error",
            "http": 400,
            "message": "Indica solo un filtro: codigos, grupo_id o prefijo_cp.",
        }

    filtro: Dict[str, Any] = {"tipo": "todos"}
    if "codigos" in presentes:
        brutos = raw["codigos"]
        if isinstance(brutos, str):
            brutos = [p.strip() for p in brutos.replace(";", ",").split(",")]
        if not isinstance(brutos, (list, tuple)):
            return {"status": "error", "http": 400, "message": "codigos debe ser una lista."}
        codigos = []
        vistos = set()
        for item in brutos:
            c = str(item or "").strip()
            if not c or c in vistos:
                continue
            vistos.add(c)
            codigos.append(c)
        if not codigos:
            return {"status": "error", "http": 400, "message": "Indica al menos un código de aliado."}
        if len(codigos) > CODIGOS_MAX:
            return {
                "status": "error",
                "http": 400,
                "message": f"Como máximo {CODIGOS_MAX} códigos por aviso.",
            }
        filtro = {"tipo": "codigos", "valor": codigos}
    elif "grupo_id" in presentes:
        try:
            gid = int(raw["grupo_id"])
        except (TypeError, ValueError):
            return {"status": "error", "http": 400, "message": "grupo_id no es válido."}
        if gid <= 0:
            return {"status": "error", "http": 400, "message": "grupo_id no es válido."}
        filtro = {"tipo": "grupo_id", "valor": gid}
    elif "prefijo_cp" in presentes:
        pref = str(raw["prefijo_cp"] or "").strip()
        if not pref.isdigit() or not (1 <= len(pref) <= 5):
            return {
                "status": "error",
                "http": 400,
                "message": "prefijo_cp debe ser de 1 a 5 dígitos.",
            }
        filtro = {"tipo": "prefijo_cp", "valor": pref}

    dry = data.get("dry_run", data.get("preview", False))
    if isinstance(dry, str):
        dry = dry.strip().lower() in ("1", "true", "yes", "si", "sí", "on")
    else:
        dry = bool(dry)
    return {"status": "ok", "texto": texto, "filtro": filtro, "dry_run": dry}


def _listar_destinatarios(cursor, filtro: Dict[str, Any]) -> Tuple[List[str], List[Dict[str, str]]]:
    omitidos: List[Dict[str, str]] = []
    base = (
        "SELECT codigo, estado FROM aliados WHERE LOWER(TRIM(COALESCE(estado, ''))) = ? "
    )
    params: List[Any] = [ESTADO_DESTINO]
    if filtro["tipo"] == "grupo_id":
        base += "AND grupo_id = ? "
        params.append(int(filtro["valor"]))
    elif filtro["tipo"] == "prefijo_cp":
        base += "AND TRIM(CAST(COALESCE(codigo_postal, '') AS TEXT)) LIKE ? "
        params.append(f"{filtro['valor']}%")
    elif filtro["tipo"] == "codigos":
        pedidos = list(filtro["valor"])
        placeholders = ",".join("?" * len(pedidos))
        cursor.execute(
            f"SELECT codigo, estado FROM aliados WHERE TRIM(CAST(codigo AS TEXT)) IN ({placeholders})",
            tuple(pedidos),
        )
        hallados = {_dict(r)["codigo"]: _dict(r) for r in cursor.fetchall() or []}
        dest: List[str] = []
        for c in pedidos:
            row = hallados.get(c)
            if not row:
                omitidos.append({"codigo": c, "motivo": "inexistente"})
                continue
            if str(row.get("estado") or "").strip().lower() != ESTADO_DESTINO:
                omitidos.append({"codigo": c, "motivo": "no_activo"})
                continue
            dest.append(c)
        dest = sorted(set(dest))
        return dest, omitidos

    base += "ORDER BY codigo"
    cursor.execute(base, tuple(params))
    dest = [str(_dict(r).get("codigo") or "").strip() for r in cursor.fetchall() or []]
    return [c for c in dest if c], omitidos


def _ultima_difusion(cursor) -> Optional[datetime]:
    cursor.execute(
        "SELECT creado_en FROM eventos_sistema WHERE tipo = ? ORDER BY creado_en DESC, id DESC LIMIT 1",
        (TIPO_EVENTO,),
    )
    row = cursor.fetchone()
    if not row:
        return None
    d = _dict(row)
    return _parse_ts(d.get("creado_en") if d else (row[0] if row else None))


def _segundos_de_espera(ultima: datetime) -> int:
    tope = ultima + timedelta(seconds=INTERVALO_SEGUNDOS)
    restante = int((tope - _ahora()).total_seconds())
    return max(1, restante)


def _buscar_conversacion_aviso(cursor, codigo: str) -> Optional[int]:
    cursor.execute(
        """
        SELECT id FROM ruana_soporte_conversaciones
        WHERE TRIM(CAST(aliado_codigo AS TEXT)) = ?
          AND LOWER(TRIM(COALESCE(categoria, ''))) = ?
          AND LOWER(TRIM(COALESCE(tipo, ''))) = ?
          AND COALESCE(eliminada_por_admin, 0) = 0
        ORDER BY id DESC
        LIMIT 1
        """,
        (codigo, CATEGORIA_AVISO, TIPO_AVISO),
    )
    row = cursor.fetchone()
    if not row:
        return None
    d = _dict(row)
    return int(d.get("id") or row[0])


def _crear_conversacion_aviso(cursor, codigo: str, preview: str) -> int:
    cursor.execute(
        """
        INSERT INTO ruana_soporte_conversaciones
            (aliado_codigo, asunto, categoria, estado, tipo, ultimo_mensaje_preview,
             tiene_no_leido_admin, tiene_no_leido_aliado)
        VALUES (?, ?, ?, 'respondido', ?, ?, 0, 1)
        """,
        (codigo, ASUNTO_AVISO, CATEGORIA_AVISO, TIPO_AVISO, preview),
    )
    return int(cursor.lastrowid)


def _anadir_mensaje_aviso(cursor, conv_id: int, admin_codigo: str, texto: str, preview: str) -> None:
    cursor.execute(
        """
        INSERT INTO ruana_soporte_mensajes
            (conversacion_id, emisor_tipo, emisor_codigo, mensaje, leido_por_aliado, leido_por_admin)
        VALUES (?, 'admin', ?, ?, 0, 1)
        """,
        (int(conv_id), admin_codigo, texto),
    )
    cursor.execute(
        """
        UPDATE ruana_soporte_conversaciones
        SET estado = CASE WHEN LOWER(TRIM(COALESCE(estado, ''))) = 'cerrado' THEN 'reabierto' ELSE 'respondido' END,
            ultimo_mensaje_preview = ?,
            ultimo_mensaje_en = CURRENT_TIMESTAMP,
            actualizado_en = CURRENT_TIMESTAMP,
            tiene_no_leido_aliado = 1,
            tiene_no_leido_admin = 0,
            eliminada_por_aliado = 0
        WHERE id = ?
        """,
        (preview, int(conv_id)),
    )
    cursor.execute(
        """
        INSERT INTO notificaciones_aliado (aliado_codigo, tipo, titulo, mensaje, metadata, leida)
        SELECT aliado_codigo, 'ruana_soporte', '📩 Mensaje del equipo RUANA', ?, ?, 0
        FROM ruana_soporte_conversaciones WHERE id = ?
        """,
        (
            "Tienes un aviso nuevo en tu centro de comunicación.",
            json.dumps(
                {"conversacion_id": int(conv_id), "origen": "difusion_centro", "estado": "respondido"},
                ensure_ascii=False,
            ),
            int(conv_id),
        ),
    )


def _registrar_evento(cursor, admin_codigo: str, filtro: Dict[str, Any], n: int, excerpt: str,
                      creadas: int, reutilizadas: int) -> None:
    filtro_log: Dict[str, Any] = {"tipo": filtro["tipo"]}
    if filtro["tipo"] == "codigos":
        filtro_log["n"] = len(filtro.get("valor") or [])
    elif filtro["tipo"] != "todos":
        filtro_log["valor"] = filtro.get("valor")
    desc = f"Aviso del centro de comunicación a {n} aliados (filtro: {filtro['tipo']}): «{excerpt}»"
    meta = json.dumps(
        {
            "filtro": filtro_log,
            "destinatarios": n,
            "excerpt": excerpt,
            "conversaciones_creadas": creadas,
            "conversaciones_reutilizadas": reutilizadas,
        },
        ensure_ascii=False,
    )
    cursor.execute(
        """
        INSERT INTO eventos_sistema (tipo, descripcion, actor_tipo, actor_codigo, metadata)
        VALUES (?, ?, 'admin', ?, ?)
        """,
        (TIPO_EVENTO, desc, (admin_codigo or "").strip() or None, meta),
    )


def difundir(db, admin_codigo: str, data: Dict[str, Any]) -> Dict[str, Any]:
    """Previsualiza o envía un aviso. dry_run no escribe ni consume la cuota horaria."""
    parsed = _validar_entrada(data or {})
    if parsed.get("status") != "ok":
        return parsed
    texto = parsed["texto"]
    filtro = parsed["filtro"]
    dry_run = parsed["dry_run"]
    preview = texto[:220]
    excerpt = _excerpt(texto)

    with db._lock:
        conn = None
        try:
            conn = db._connect()
            if not getattr(db, "backend", None) == "postgres":
                conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            dest, omitidos = _listar_destinatarios(cursor, filtro)
            base = {
                "status": "success",
                "dry_run": dry_run,
                "destinatarios": len(dest),
                "codigos": dest,
                "omitidos": omitidos,
                "filtro": filtro,
                "excerpt": excerpt,
            }
            if dry_run:
                return base
            if not dest:
                return {
                    "status": "error",
                    "http": 400,
                    "message": "No hay destinatarios activos para ese filtro.",
                    "destinatarios": 0,
                    "codigos": [],
                    "omitidos": omitidos,
                    "filtro": filtro,
                }
            ultima = _ultima_difusion(cursor)
            if ultima and (_ahora() - ultima).total_seconds() < INTERVALO_SEGUNDOS:
                espera = _segundos_de_espera(ultima)
                minutos = max(1, (espera + 59) // 60)
                return {
                    "status": "error",
                    "http": 429,
                    "message": (
                        f"Solo se puede enviar un aviso real por hora. "
                        f"Prueba de nuevo en {minutos} min."
                    ),
                    "reintentar_en_segundos": espera,
                }
            admin_code = (admin_codigo or "").strip() or "admin"
            creadas = 0
            reutilizadas = 0
            for codigo in dest:
                conv_id = _buscar_conversacion_aviso(cursor, codigo)
                if conv_id:
                    reutilizadas += 1
                else:
                    conv_id = _crear_conversacion_aviso(cursor, codigo, preview)
                    creadas += 1
                _anadir_mensaje_aviso(cursor, conv_id, admin_code, texto, preview)
            _registrar_evento(cursor, admin_code, filtro, len(dest), excerpt, creadas, reutilizadas)
            conn.commit()
            return {**base, "creadas": creadas, "reutilizadas": reutilizadas}
        except Exception as e:
            try:
                if conn:
                    conn.rollback()
            except Exception:
                pass
            logger.error(
                "Fallo al difundir aviso del centro de comunicación",
                extra={"admin_codigo": admin_codigo, "error": str(e)},
                exc_info=True,
            )
            return {"status": "error", "http": 500, "message": "No se pudo enviar el aviso."}
        finally:
            if conn:
                try:
                    conn.close()
                except Exception:
                    pass
