"""Contexto del aliado para el Copiloto RUANA.

Construye el "paquete de estado" que alimenta tanto al motor determinista como
al LLM. Regla de oro: **este módulo es el único que lee la BD**; el LLM solo
recibe lo que salga de aquí, y el validador comprueba que no invente cifras.

Todas las consultas son defensivas: si una fuente falla, el contexto se
degrada y el copiloto sigue respondiendo con lo que haya.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from core.services import copiloto_conocimiento as conocimiento

logger = logging.getLogger(__name__)

_ESTADOS_ABIERTOS = {
    "iniciado",
    "aceptado",
    "trabajo_en_progreso",
    "importe_en_disputa",
    "en_conversacion",
    "acuerdo_alcanzado",
    "pendiente_de_pago",
}


def _safe_int(valor: Any, defecto: int = 0) -> int:
    try:
        return int(valor)
    except (TypeError, ValueError):
        return defecto


def _texto(valor: Any) -> str:
    return str(valor or "").strip()


def _leer_delta_hoy(db, codigo: str) -> int:
    """Movimiento de score de hoy. 0 si no se puede leer."""
    try:
        from core.repositories.score_repo import ScoreRepo

        with db._lock:
            conn = db._connect()
            try:
                cursor = conn.cursor()
                return _safe_int(ScoreRepo().delta_score_hoy(cursor, codigo))
            finally:
                conn.close()
    except Exception:
        logger.debug("Copiloto: no se pudo leer delta de score de hoy", exc_info=True)
        return 0


def _leer_motivos_recientes(db, codigo: str, limite: int = 3) -> List[Dict[str, Any]]:
    """Últimos movimientos de score con su motivo. Lista vacía si falla."""
    try:
        with db._lock:
            conn = db._connect()
            try:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT delta, motivo FROM score_movimientos "
                    "WHERE codigo_aliado = ? ORDER BY id DESC LIMIT ?",
                    (codigo, limite),
                )
                filas = cursor.fetchall()
            finally:
                conn.close()
    except Exception:
        logger.debug("Copiloto: no se pudieron leer motivos de score", exc_info=True)
        return []

    salida: List[Dict[str, Any]] = []
    for fila in filas or []:
        try:
            delta = _safe_int(fila["delta"])
            motivo = _texto(fila["motivo"])
        except Exception:
            try:
                delta = _safe_int(fila[0])
                motivo = _texto(fila[1])
            except Exception:
                continue
        salida.append({"delta": delta, "motivo": motivo, "etiqueta": _traducir_motivo(motivo)})
    return salida


def _traducir_motivo(motivo: str) -> str:
    """Motivo técnico del score → frase para el aliado."""
    clave = _texto(motivo)
    if not clave:
        return "actualización de las reglas de RUANA"
    tabla = [
        ("aliado_referido_registro_valido", "registro válido de un aliado que invitaste"),
        ("aliado_invitado_registrado", "un profesional que invitaste se registró"),
        ("invitacion_oficio_usada", "un profesional invitado por oficio se registró"),
        ("encargo_completado_apoyo_pagado", "encargo completado con el apoyo validado"),
        ("referido_encargo_completado", "un encargo cerrado por tu red de referidos"),
        ("regla4", "constancia de encargos completados en el mes"),
        ("regla5", "respuesta rápida a varios clientes"),
        ("regla6", "gestión de un encargo urgente el mismo día"),
        ("regla7", "declaración del cierre a tiempo"),
        ("regla8", "constancia entrando a la app"),
        ("contacto_cerrado_no_concretado", "un contacto se cerró sin concretarse"),
        ("contacto_sin_cerrar_7d", "un contacto lleva 7 días abierto"),
        ("contacto_sin_cerrar_21d", "un contacto lleva 21 días abierto"),
        ("descendiente_entra_competencia", "alguien de tu red entró en competencia"),
        ("chat_sin_respuesta_48h", "un mensaje estuvo 48 horas sin respuesta"),
        ("sin_acceso_7d", "una semana sin entrar a la app"),
        ("chat_agotado_sin_resultado", "una conversación se agotó sin cerrar el resultado"),
        ("disputa_perdida", "una disputa de importe se resolvió en contra"),
        ("comprobante_apoyo_3d", "el comprobante del apoyo llegó con retraso"),
    ]
    for prefijo, frase in tabla:
        if clave.startswith(prefijo):
            return frase
    return clave.replace("_", " ")


def _fecha_a_edad_dias(valor: Any) -> Optional[int]:
    """Días transcurridos desde un timestamp de BD. None si no se entiende."""
    if valor in (None, ""):
        return None
    if isinstance(valor, datetime):
        fecha = valor
    else:
        texto = _texto(valor)
        fecha = None
        for formato in ("%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
            try:
                fecha = datetime.strptime(texto, formato)
                break
            except ValueError:
                continue
        if fecha is None:
            try:
                fecha = datetime.fromisoformat(texto.replace("Z", "+00:00"))
            except ValueError:
                return None
    if fecha.tzinfo is None:
        fecha = fecha.replace(tzinfo=timezone.utc)
    delta = datetime.now(timezone.utc) - fecha
    return max(0, int(delta.total_seconds() // 86400))


def _leer_contactos(db, codigo: str) -> Dict[str, Any]:
    """Contactos abiertos del aliado, con antigüedad y qué falta."""
    try:
        contactos = db.obtener_contactos_abiertos_por_codigo(codigo) or []
    except Exception:
        logger.debug("Copiloto: fallo obteniendo contactos abiertos", exc_info=True)
        contactos = []

    detalle: List[Dict[str, Any]] = []
    for c in contactos:
        try:
            estado = _texto(c.get("estado")).lower()
            if estado and estado not in _ESTADOS_ABIERTOS:
                continue
            es_profesional = _texto(c.get("profesional_codigo")) == codigo
            edad = _fecha_a_edad_dias(
                c.get("fecha_actualizacion")
                or c.get("creado_en")
                or c.get("fecha_creacion")
            )
            neg_completa = bool(c.get("negociacion_completa"))
            ya_declaro = bool(c.get("ya_declaraste_importe"))
            paso = _texto(c.get("negociacion_paso_label"))
            detalle.append(
                {
                    "contacto_id": _safe_int(c.get("id")),
                    "rol": "profesional" if es_profesional else "solicitante",
                    "estado": estado,
                    "dias_abierto": edad,
                    "negociacion_completa": neg_completa,
                    "paso_pendiente": None if neg_completa else paso,
                    "declaro_importe": ya_declaro,
                    "es_urgente": bool(c.get("es_urgente")),
                }
            )
        except Exception:
            continue

    return {
        "total": len(detalle),
        "sin_importe": sum(
            1 for c in detalle if c["rol"] == "profesional" and not c["declaro_importe"]
        ),
        "negociacion_a_medias": sum(1 for c in detalle if not c["negociacion_completa"]),
        "antiguos": [c for c in detalle if (c["dias_abierto"] or 0) >= 7],
        "detalle": detalle,
    }


def _leer_grupo(db, aliado: Dict[str, Any], codigo: str) -> Dict[str, Any]:
    grupo_id = aliado.get("grupo_id")
    if not grupo_id:
        return {"tiene_grupo": False}
    try:
        info = db.info_grupo_para_panel(grupo_id, codigo) or {}
    except Exception:
        logger.debug("Copiloto: fallo leyendo info de grupo", exc_info=True)
        info = {}
    crecimiento = info.get("crecimiento") or {}
    return {
        "tiene_grupo": True,
        "nombre": _texto(info.get("nombre")),
        "num_aliados": _safe_int(info.get("num_aliados")),
        "num_oficios": _safe_int(info.get("num_oficios")),
        "oficios_faltantes": list(info.get("oficios_faltantes") or [])[:40],
        "en_creacion": bool(info.get("en_creacion")),
        "recompensas_usadas": _safe_int(crecimiento.get("recompensas_obtenidas")),
        "recompensas_max": _safe_int(
            crecimiento.get("recompensas_max"), conocimiento.MAX_RECOMPENSAS_CRECIMIENTO
        ),
        "puntos_crecimiento_ganados": _safe_int(crecimiento.get("score_obtenido")),
    }


def _leer_demanda(db, codigo: str) -> List[Dict[str, Any]]:
    """Qué oficios ha pedido la gente de la zona esta semana."""
    try:
        from core.services import solicitud_semanal_service

        panel = solicitud_semanal_service.obtener_panel_por_codigo(db, codigo) or {}
    except Exception:
        logger.debug("Copiloto: fallo leyendo solicitudes semanales", exc_info=True)
        return []
    if panel.get("status") != "success":
        return []
    cuenta: Dict[str, int] = {}
    for item in panel.get("activas_grupo") or []:
        try:
            oficio = _texto(item.get("oficio")).lower()
        except Exception:
            continue
        if oficio:
            cuenta[oficio] = cuenta.get(oficio, 0) + 1
    return [
        {"oficio": oficio, "peticiones": n}
        for oficio, n in sorted(cuenta.items(), key=lambda par: -par[1])
    ]


def _leer_perfil(db, codigo: str, aliado: Dict[str, Any]) -> Dict[str, Any]:
    try:
        catalogo = db.listar_catalogo_servicios_aliado(codigo) or []
    except Exception:
        catalogo = []
    servicios = []
    for item in catalogo:
        try:
            nombre = _texto(item.get("nombre") or item.get("servicio"))
        except Exception:
            nombre = ""
        if nombre:
            servicios.append(nombre)
    return {
        "tiene_descripcion": bool(_texto(aliado.get("descripcion_servicio"))),
        "num_servicios": len(servicios),
        "servicios": servicios[:6],
    }


def construir_contexto(db, codigo: str) -> Dict[str, Any]:
    """Paquete de estado completo del aliado. Nunca lanza."""
    codigo = _texto(codigo)
    base: Dict[str, Any] = {"ok": False, "codigo": codigo}
    if not codigo:
        return base

    try:
        aliado = db.obtener_aliado_por_codigo(codigo)
    except Exception:
        logger.warning("Copiloto: no se pudo cargar el aliado", exc_info=True)
        return base
    if not aliado:
        return base
    aliado = dict(aliado)

    score = _safe_int(aliado.get("score"), conocimiento.SCORE_INICIAL)
    banda = conocimiento.banda_de_score(score)
    banda["delta_hoy"] = _leer_delta_hoy(db, codigo)
    banda["motivos_recientes"] = _leer_motivos_recientes(db, codigo)

    try:
        estado_ruana = db.score_a_estado(score)
    except Exception:
        estado_ruana = banda["banda"]

    referidos = 0
    try:
        referidos = _safe_int(db.contar_referidos_por_codigo(codigo))
    except Exception:
        pass

    contexto = {
        "ok": True,
        "codigo": codigo,
        "nombre": _texto(aliado.get("nombre")) or "aliado",
        "oficio": _texto(aliado.get("oficio")),
        "codigo_postal": _texto(aliado.get("codigo_postal")),
        "estado": _texto(aliado.get("estado")) or "activo",
        "score": banda,
        "estado_ruana": _texto(estado_ruana) or banda["banda"],
        "grupo": _leer_grupo(db, aliado, codigo),
        "contactos": _leer_contactos(db, codigo),
        "red": {"referidos": referidos},
        "perfil": _leer_perfil(db, codigo, aliado),
        "demanda": _leer_demanda(db, codigo),
        "competencia_activa": bool(aliado.get("competencia_activa")),
        "limite_diario": conocimiento.LIMITE_DIARIO,
    }
    return contexto


# ---------------------------------------------------------------------------
# Versión reducida para el LLM
# ---------------------------------------------------------------------------

def contexto_para_llm(contexto: Dict[str, Any]) -> Dict[str, Any]:
    """Subconjunto sin datos personales de terceros ni identificadores internos."""
    if not contexto.get("ok"):
        return {"ok": False}
    score = contexto.get("score") or {}
    grupo = contexto.get("grupo") or {}
    contactos = contexto.get("contactos") or {}
    return {
        "nombre_pila": (contexto.get("nombre") or "").split(" ")[0],
        "oficio": contexto.get("oficio"),
        "estado_cuenta": contexto.get("estado"),
        "estado_ruana": contexto.get("estado_ruana"),
        "score": score.get("score"),
        "banda": score.get("banda"),
        "puntos_al_siguiente": score.get("puntos_al_siguiente"),
        "siguiente_banda": score.get("siguiente_banda"),
        "movimiento_hoy": score.get("delta_hoy"),
        "ultimos_cambios": [m.get("etiqueta") for m in (score.get("motivos_recientes") or [])][:3],
        "grupo": {
            "aliados": grupo.get("num_aliados"),
            "oficios_faltantes": (grupo.get("oficios_faltantes") or [])[:8],
            "recompensas_usadas": grupo.get("recompensas_usadas"),
            "recompensas_max": grupo.get("recompensas_max"),
        },
        "contactos_abiertos": contactos.get("total"),
        "contactos_sin_importe": contactos.get("sin_importe"),
        "negociaciones_a_medias": contactos.get("negociacion_a_medias"),
        "demanda_semana": (contexto.get("demanda") or [])[:5],
        "perfil": contexto.get("perfil"),
        "competencia_activa": contexto.get("competencia_activa"),
        "limite_diario_score": contexto.get("limite_diario"),
    }
