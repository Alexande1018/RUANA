"""Copiloto del panel de administración.

Misma idea que el copiloto del aliado, con otro contexto: aquí el usuario es el
administrador y las preguntas son sobre la red (altas, soporte, conflictos,
riesgo, territorio), no sobre su propio score.

Reutiliza del copiloto del aliado el cliente de modelo, el validador de cifras,
la cuota y el recorte de historial. Lo propio es el contexto, las jugadas y las
respuestas.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional, Tuple

from core.services import (
    copiloto_conocimiento as conocimiento,
    copiloto_contexto,
    copiloto_llm,
    copiloto_service,
)
from core.services import admin_service, aliado_service, pago_service

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Contexto de la red
# ---------------------------------------------------------------------------

def _bloque(nombre: str, fn, *args, **kwargs) -> Optional[Dict[str, Any]]:
    """Ejecuta un bloque de métricas. None si falla: no se inventa un 0."""
    try:
        datos = fn(*args, **kwargs)
        return datos if isinstance(datos, dict) else None
    except Exception:
        logger.debug("Copiloto admin: fallo en el bloque %s", nombre, exc_info=True)
        return None


def _contar_por_estado(aliados: List[Dict[str, Any]]) -> Dict[str, int]:
    cuenta: Dict[str, int] = {}
    for a in aliados or []:
        try:
            estado = str(a.get("estado") or "").strip().lower()
        except Exception:
            continue
        if estado:
            cuenta[estado] = cuenta.get(estado, 0) + 1
    return cuenta


def construir_contexto(db) -> Dict[str, Any]:
    """Foto de la red para el copiloto del admin. Nunca lanza."""
    contexto: Dict[str, Any] = {"ok": True}

    try:
        from core.services import admin_dashboard_service

        resumen, _aliados = admin_dashboard_service.build_dashboard_summary(db)
        contexto["red"] = resumen
    except Exception:
        logger.warning("Copiloto admin: sin resumen de red", exc_info=True)
        contexto["red"] = None

    contexto["trafico_24h"] = _bloque("trafico", admin_service.obtener_stats_24h_panel, db)
    contexto["salud"] = _bloque("salud", admin_service.obtener_metricas_salud, db)
    contexto["contactos"] = _bloque("contactos", admin_service.obtener_metricas_contactos, db)

    # Altas pendientes de validación y listas de espera.
    altas: Dict[str, Any] = {}
    try:
        pendientes = aliado_service.listar_aliados_pendiente_validacion(db) or []
        altas["pendientes_validacion"] = len(pendientes)
        altas["nombres_pendientes"] = [
            str(p.get("nombre") or p.get("codigo") or "")[:40] for p in pendientes[:3]
        ]
    except Exception:
        logger.debug("Copiloto admin: sin altas pendientes", exc_info=True)

    # Soporte: conversaciones esperando respuesta.
    try:
        sin_leer = admin_service.listar_conversaciones_soporte_admin(
            db, solo_no_leidas=True, limite=100
        ) or []
        altas["soporte_sin_leer"] = len(sin_leer)
        abiertas = admin_service.listar_conversaciones_soporte_admin(db, limite=200) or []
        altas["soporte_abiertas"] = len(abiertas)
    except Exception:
        logger.debug("Copiloto admin: sin datos de soporte", exc_info=True)

    # Conflictos de pago abiertos.
    try:
        conflictos = pago_service.listar_payment_conflicts_admin(db) or []
        altas["conflictos_pago"] = len(conflictos)
    except Exception:
        logger.debug("Copiloto admin: sin conflictos", exc_info=True)

    contexto["pendientes"] = altas or None
    return contexto


# ---------------------------------------------------------------------------
# Jugadas del admin
# ---------------------------------------------------------------------------

def _jugada(ident, urgencia, titulo, detalle, accion, cta) -> Dict[str, Any]:
    return {
        "id": ident,
        "urgencia": urgencia,
        "titulo": titulo,
        "detalle": detalle,
        "impacto": "",
        "accion": accion,
        "cta": cta,
    }


def _nav(destino: str) -> Dict[str, Any]:
    return {"tipo": "nav_admin", "destino": destino}


_PESO = {"alta": 3, "media": 2, "baja": 1}


def calcular_jugadas(contexto: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Hasta 3 acciones para el admin, por urgencia. Nunca lanza."""
    if not contexto or not contexto.get("ok"):
        return []

    jugadas: List[Dict[str, Any]] = []
    red = contexto.get("red") or {}
    pend = contexto.get("pendientes") or {}
    contactos = contexto.get("contactos") or {}
    trafico = contexto.get("trafico_24h") or {}

    soporte = int(pend.get("soporte_sin_leer") or 0)
    if soporte:
        jugadas.append(
            _jugada(
                "soporte_sin_leer",
                "alta",
                f"{soporte} conversación{'es' if soporte != 1 else ''} sin responder",
                "Hay mensajes de aliados esperando. Cuanto más tardes, más se enfría la "
                "conversación y peor se siente el aliado.",
                _nav("centro-comunicacion"),
                "Abrir comunicaciones",
            )
        )

    conflictos = int(pend.get("conflictos_pago") or 0)
    if conflictos:
        jugadas.append(
            _jugada(
                "conflictos_pago",
                "alta",
                f"{conflictos} conflicto{'s' if conflictos != 1 else ''} de pago abierto",
                "Un conflicto sin resolver bloquea el apoyo de ese encargo y deja al "
                "profesional sin cobrar.",
                _nav("conflictos"),
                "Revisar conflictos",
            )
        )

    altas = int(pend.get("pendientes_validacion") or 0)
    if altas:
        jugadas.append(
            _jugada(
                "altas_pendientes",
                "alta" if altas >= 5 else "media",
                f"{altas} alta{'s' if altas != 1 else ''} esperando validación",
                "Son registros con un oficio fuera de catálogo. Hasta que los valides no "
                "pueden entrar al panel ni generar encargos.",
                _nav("pendientes"),
                "Validar altas",
            )
        )

    en_riesgo = int(red.get("en_riesgo") or 0)
    if en_riesgo:
        jugadas.append(
            _jugada(
                "aliados_riesgo",
                "media",
                f"{en_riesgo} aliado{'s' if en_riesgo != 1 else ''} en riesgo",
                "Están por debajo de 50 puntos. Un empujón a tiempo evita que caigan a "
                "competencia y que la red pierda la plaza.",
                _nav("aliados"),
                "Ver aliados",
            )
        )

    abiertos = int(contactos.get("contactos_abiertos") or 0)
    solicitudes = int((trafico.get("solicitudes") or {}).get("nuevas") or 0)
    hay_datos = contexto.get("contactos") is not None and contexto.get("trafico_24h") is not None
    if hay_datos and abiertos == 0 and solicitudes == 0:
        jugadas.append(
            _jugada(
                "red_parada",
                "media",
                "La red no se mueve en las últimas 24 h",
                "Sin solicitudes nuevas ni encargos abiertos. Es el momento de activar a "
                "los aliados con más score o lanzar una campaña de invitación en la zona "
                "con más demanda.",
                _nav("overview"),
                "Ver el panel",
            )
        )

    suplentes = int(red.get("suplentes") or 0)
    if suplentes and len(jugadas) < 3:
        jugadas.append(
            _jugada(
                "suplentes_espera",
                "baja",
                f"{suplentes} profesional{'es' if suplentes != 1 else ''} en lista de espera",
                "Hay gente esperando plaza. Mira si alguna zona puede abrir un grupo "
                "(máximo 5 por código postal).",
                _nav("suplentes"),
                "Ver suplentes",
            )
        )

    jugadas.sort(key=lambda j: _PESO.get(j["urgencia"], 1), reverse=True)
    return jugadas[:3]


# ---------------------------------------------------------------------------
# Intenciones del admin
# ---------------------------------------------------------------------------

_INTENCIONES = [
    ("soporte", [r"\bsoporte\b", r"\bmensajes?\b.*\b(sin|espera|responder)\b", r"\bcomunicaci"]),
    ("conflictos", [r"\bconflictos?\b", r"\bimpugna", r"\bdisputa"]),
    ("altas", [r"\bpendientes?\b", r"\bvalidar?\b", r"\baltas?\b", r"\bregistros?\b"]),
    ("riesgo", [r"\briesgo\b", r"\bcompetencia\b", r"\bsuplentes?\b", r"\bba(j|j)a"]),
    ("encargos", [r"\bencargos?\b", r"\bcontactos?\b", r"\btrabajos?\b", r"\bcierres?\b"]),
    ("crecimiento", [r"\binvitaci", r"\bcrecimiento\b", r"\bcaptaci", r"\bcampa"]),
    ("territorio", [r"\bgrupos?\b", r"\bzonas?\b", r"\bc[oó]digo postal\b", r"\bterritorio\b"]),
    ("salud", [r"\bsalud\b", r"\bratio", r"\bretenci[oó]n\b", r"\bm[eé]tricas?\b"]),
    ("resumen", [r"\bc[oó]mo va\b", r"\bresumen\b", r"\bestado\b", r"\bc[oó]mo vamos\b"]),
]


def clasificar(texto: str) -> str:
    import re

    limpio = (texto or "").strip().lower()
    if not limpio:
        return "resumen"
    for ident, patrones in _INTENCIONES:
        for patron in patrones:
            try:
                if re.search(patron, limpio):
                    return ident
            except re.error:
                continue
    return "general"


# ---------------------------------------------------------------------------
# Respuestas deterministas
# ---------------------------------------------------------------------------

def _n(valor: Any, defecto: str = "sin dato") -> str:
    return str(int(valor)) if isinstance(valor, (int, float)) else defecto


def responder_determinista(
    contexto: Dict[str, Any], intencion: str, texto_usuario: str
) -> Tuple[str, Optional[Dict[str, Any]]]:
    red = contexto.get("red") or {}
    pend = contexto.get("pendientes") or {}
    contactos = contexto.get("contactos") or {}
    trafico = contexto.get("trafico_24h") or {}
    salud = contexto.get("salud") or {}

    if intencion == "resumen":
        partes = [
            f"Red: {_n(red.get('active_users'))} aliados activos de {_n(red.get('total_users'))}",
            f"{_n(red.get('grupos'))} grupos",
            f"{_n(red.get('en_riesgo'))} en riesgo",
            f"{_n(pend.get('pendientes_validacion'))} altas por validar",
            f"{_n(pend.get('soporte_sin_leer'))} mensajes sin responder",
            f"{_n(pend.get('conflictos_pago'))} conflictos de pago",
        ]
        texto = " · ".join(partes) + "."
        if red.get("estado_sistema"):
            texto += f" Estado del sistema: {red.get('estado_sistema')}."
        return texto, _nav("overview")

    if intencion == "soporte":
        sin_leer = pend.get("soporte_sin_leer")
        abiertas = pend.get("soporte_abiertas")
        if sin_leer is None:
            return (
                "No he podido leer el centro de comunicación ahora mismo. Ábrelo desde "
                "el panel y lo ves ahí.",
                _nav("centro-comunicacion"),
            )
        return (
            f"Tienes {_n(sin_leer)} conversaciones con mensajes sin leer de un total de "
            f"{_n(abiertas)} abiertas. Se atienden desde «Centro de comunicación».",
            _nav("centro-comunicacion"),
        )

    if intencion == "conflictos":
        conflictos = pend.get("conflictos_pago")
        if conflictos is None:
            return (
                "No he podido leer los conflictos de pago. Están en «Conflictos de pago».",
                _nav("conflictos"),
            )
        if not conflictos:
            return "No hay conflictos de pago abiertos ahora mismo.", _nav("conflictos")
        return (
            f"Hay {_n(conflictos)} conflictos de pago abiertos. Mientras no se resuelvan, "
            "ese apoyo no se puede dar por bueno.",
            _nav("conflictos"),
        )

    if intencion == "altas":
        altas = pend.get("pendientes_validacion")
        nombres = pend.get("nombres_pendientes") or []
        if altas is None:
            return (
                "No he podido contar las altas pendientes. Están en «Pendientes validación».",
                _nav("pendientes"),
            )
        if not altas:
            return "No hay altas pendientes de validación.", _nav("pendientes")
        detalle = f" Empiezan por: {', '.join(nombres)}." if nombres else ""
        return (
            f"Hay {_n(altas)} altas esperando validación.{detalle} Hasta que las valides "
            "no pueden entrar ni recibir encargos.",
            _nav("pendientes"),
        )

    if intencion == "riesgo":
        en_riesgo = red.get("en_riesgo")
        suplentes = red.get("suplentes")
        return (
            f"{_n(en_riesgo)} aliados en riesgo (por debajo de 50 puntos) y "
            f"{_n(suplentes)} en lista de espera. Por debajo de 15 se abre la competencia "
            "por la plaza.",
            _nav("aliados"),
        )

    if intencion == "encargos":
        return (
            f"{_n(contactos.get('contactos_abiertos'))} encargos abiertos, "
            f"{_n(contactos.get('contactos_en_disputa'))} con el importe en disputa. "
            f"En las últimas 24 h entraron {_n((trafico.get('solicitudes') or {}).get('nuevas'))} "
            "solicitudes.",
            _nav("chats"),
        )

    if intencion == "crecimiento":
        inv = trafico.get("invitaciones") or {}
        top = trafico.get("top_invitadores") or []
        lider = f" El que más ha invitado: {top[0].get('nombre')} con {top[0].get('total')}." if top else ""
        return (
            f"En 24 h se generaron {_n(inv.get('generadas'))} invitaciones y se usaron "
            f"{_n(inv.get('usadas'))}. Hay {_n(inv.get('expiradas'))} caducadas sin usar.{lider}",
            _nav("overview"),
        )

    if intencion == "territorio":
        return (
            f"{_n(red.get('grupos'))} grupos ({_n(red.get('grupos_activos'))} activos, "
            f"{_n(red.get('grupos_en_competencia'))} en competencia). "
            f"{_n(red.get('aliados_sin_grupo_territorial'))} aliados sin grupo territorial.",
            _nav("grupos-overview"),
        )

    if intencion == "salud":
        return (
            f"Retención: {_n(salud.get('tasa_retencion'))} % de aliados con al menos un "
            f"trabajo. Ratio invitación → registro: {_n(salud.get('ratio_invitacion_registro'))}. "
            f"Zona con más demanda: {salud.get('zona_mayor_demanda') or 'sin dato'}.",
            _nav("salud"),
        )

    return (
        "Puedo contarte cómo va la red, qué altas esperan validación, qué mensajes hay "
        "sin responder, los conflictos de pago abiertos o el estado del territorio. "
        "Si es otra cosa, ábrela en el panel.",
        None,
    )


# ---------------------------------------------------------------------------
# Prompt y conversación
# ---------------------------------------------------------------------------

_SYSTEM = """Eres el copiloto del panel de administración de RUANA, una red de
profesionales organizada por código postal. Hablas con el administrador, no con
un aliado: tus respuestas son sobre la red, no sobre el score de una persona.

Puedes:
- Resumir el estado de la red y sus pendientes.
- Decir qué requiere atención: soporte sin responder, altas por validar,
  conflictos de pago, aliados en riesgo, plazas en espera.
- Explicar cómo funciona una parte del panel y llevar a la pantalla correcta.

Reglas que NO puedes saltarte:
- Usa SOLO las cifras que aparecen en DATOS y REGLAS. Si un dato dice "sin
  dato" o no está, di que no lo tienes; no lo estimes.
- No inventes nombres, importes ni códigos.
- No prometas resultados de negocio.
- Máximo 100 palabras. Texto plano, sin markdown.
- Responde en español de España, tuteando, en frases cortas.
"""


def _prompt(contexto: Dict[str, Any], mensaje: str, intencion: str) -> str:
    datos = {
        "red": contexto.get("red"),
        "pendientes": contexto.get("pendientes"),
        "contactos": contexto.get("contactos"),
        "trafico_24h": contexto.get("trafico_24h"),
        "salud": contexto.get("salud"),
    }
    return (
        "DATOS DE LA RED (lo único que puedes dar por cierto):\n"
        + json.dumps(datos, ensure_ascii=False, indent=1, default=str)
        + "\n\nREGLAS DE SCORE VIGENTES:\n"
        + conocimiento.tabla_puntos_texto()
        + "\n\n"
        + conocimiento.ficha_producto()
        + f"\n\nINTENCIÓN DETECTADA: {intencion}"
        + f"\n\nPREGUNTA DEL ADMINISTRADOR: {mensaje}"
    )


def estado(db) -> Dict[str, Any]:
    contexto = construir_contexto(db)
    jugadas = calcular_jugadas(contexto)
    info_ia = copiloto_llm.estado_publico()
    red = contexto.get("red") or {}
    saludo = (
        f"Red: {_n(red.get('active_users'))} aliados activos, {_n(red.get('grupos'))} grupos"
    )
    pend = contexto.get("pendientes") or {}
    pendientes_total = sum(
        int(pend.get(k) or 0)
        for k in ("pendientes_validacion", "soporte_sin_leer", "conflictos_pago")
    )
    if pendientes_total:
        saludo += f", {pendientes_total} cosas esperando tu decisión."
    else:
        saludo += " y nada urgente pendiente."
    return {
        "saludo": saludo,
        "jugadas": jugadas,
        "ia": info_ia,
        "sugerencias": [
            "¿Cómo va la red?",
            "¿Qué tengo pendiente?",
            "¿Cuántos conflictos de pago hay?",
            "¿Cómo va el crecimiento?",
        ],
        "mensajes_restantes_hoy": copiloto_service._cuota_restante("admin"),
    }


def conversar(db, mensaje: str, historial: Any = None) -> Dict[str, Any]:
    texto = (mensaje or "").strip()
    if not texto:
        return {"status": "error", "message": "Escribe una pregunta y te contesto."}
    texto = texto[:600]

    contexto = construir_contexto(db)
    intencion = clasificar(texto)
    respuesta, accion = responder_determinista(contexto, intencion, texto)
    fuente = "reglas"

    if copiloto_llm.disponible() and copiloto_service._cuota_permite("admin"):
        permitido = copiloto_service.cifras_permitidas(
            json.dumps(contexto, ensure_ascii=False, default=str),
            conocimiento.tabla_puntos_texto(),
            conocimiento.ficha_producto(),
            respuesta,
            texto,
        )
        candidata = copiloto_llm.responder(
            _SYSTEM,
            copiloto_service._limpiar_historial(historial)
            + [{"role": "user", "content": _prompt(contexto, texto, intencion)}],
        )
        if candidata and copiloto_service.validar_cifras(candidata, permitido):
            respuesta = candidata
            fuente = "ia"
        elif candidata:
            logger.info(
                "Copiloto admin: respuesta descartada por cifras no verificadas",
                extra={
                    "intencion": intencion,
                    "cifras_fuera": copiloto_service.cifras_no_permitidas(candidata, permitido)[:6],
                },
            )

    return {
        "status": "success",
        "texto": respuesta,
        "accion": accion,
        "fuente": fuente,
        "intencion": intencion,
        "ia": copiloto_llm.estado_publico(),
        "mensajes_restantes_hoy": copiloto_service._cuota_restante("admin"),
    }
