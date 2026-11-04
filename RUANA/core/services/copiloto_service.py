"""Copiloto RUANA: el asistente que habla con los aliados dentro del panel.

Dos capas, un solo producto:

  1. MOTOR DETERMINISTA (siempre). Lee el contexto real del aliado, clasifica
     la intención y responde con datos de la BD. Gratis, instantáneo y exacto.
  2. LLM (si está configurado). Recibe el contexto y las reglas, y reescribe la
     respuesta con lenguaje natural. Su salida pasa por un validador de cifras:
     ningún número que no esté en el contexto llega al aliado.

Si el LLM falla, tarda o dice algo raro, se devuelve la respuesta determinista.
El aliado nunca ve un error.
"""

from __future__ import annotations

import json
import logging
import re
import threading
from datetime import date
from typing import Any, Dict, List, Optional, Tuple

from core.services import (
    copiloto_conocimiento as conocimiento,
    copiloto_contexto,
    copiloto_jugadas,
    copiloto_llm,
)

logger = logging.getLogger(__name__)

_MAX_HISTORIAL = 8

# Cuota en proceso. Gunicorn tiene varios workers, así que es aproximada:
# sirve para que un código filtrado no vacíe la factura, no como contabilidad.
_CUOTA: Dict[str, Dict[str, Any]] = {}
_CUOTA_LOCK = threading.Lock()


def _cuota_diaria() -> int:
    try:
        import os

        return max(0, int((os.environ.get("RUANA_AI_CUOTA_DIARIA") or "60").strip()))
    except (TypeError, ValueError):
        return 60


def _cuota_permite(codigo: str) -> bool:
    limite = _cuota_diaria()
    if limite <= 0:
        return False
    hoy = date.today().isoformat()
    with _CUOTA_LOCK:
        estado = _CUOTA.get(codigo)
        if not estado or estado.get("dia") != hoy:
            _CUOTA[codigo] = {"dia": hoy, "n": 0}
            estado = _CUOTA[codigo]
        if estado["n"] >= limite:
            return False
        estado["n"] += 1
        return True


def _cuota_restante(codigo: str) -> int:
    limite = _cuota_diaria()
    hoy = date.today().isoformat()
    with _CUOTA_LOCK:
        estado = _CUOTA.get(codigo) or {}
        usado = estado.get("n", 0) if estado.get("dia") == hoy else 0
    return max(0, limite - usado)


# ---------------------------------------------------------------------------
# Acciones que el copiloto puede ofrecer al frontend
# ---------------------------------------------------------------------------

def _accion_nav(destino: str, etiqueta: str) -> Dict[str, Any]:
    return {"tipo": "nav", "destino": destino, "etiqueta": etiqueta}


def _accion_invitar(oficio: str, etiqueta: str) -> Dict[str, Any]:
    return {"tipo": "invitar", "oficio": oficio or "", "etiqueta": etiqueta}


def _accion_soporte(etiqueta: str = "Escribir al equipo RUANA") -> Dict[str, Any]:
    return {"tipo": "soporte", "etiqueta": etiqueta}


def _accion_copiar(texto: str, etiqueta: str = "Copiar mensaje") -> Dict[str, Any]:
    return {"tipo": "copiar", "texto": texto, "etiqueta": etiqueta}


def _oficio_objetivo(contexto: Dict[str, Any]) -> str:
    grupo = contexto.get("grupo") or {}
    return conocimiento.elegir_oficio_para_invitar(
        list(grupo.get("oficios_faltantes") or []),
        contexto.get("demanda") or [],
    )


def _recompensas_restantes(contexto: Dict[str, Any]) -> int:
    grupo = contexto.get("grupo") or {}
    return max(
        0,
        int(grupo.get("recompensas_max") or 10) - int(grupo.get("recompensas_usadas") or 0),
    )


# ---------------------------------------------------------------------------
# Respuestas deterministas (siempre disponibles)
# ---------------------------------------------------------------------------

def _respuesta_determinista(
    contexto: Dict[str, Any], intencion: str, texto_usuario: str
) -> Tuple[str, Optional[Dict[str, Any]]]:
    nombre = (contexto.get("nombre") or "").split(" ")[0] or "hola"
    score = contexto.get("score") or {}
    grupo = contexto.get("grupo") or {}
    contactos = contexto.get("contactos") or {}
    perfil = contexto.get("perfil") or {}
    valor = score.get("score")
    banda = score.get("banda")

    if intencion == "saludo":
        lineas = [f"Hola, {nombre}. " + copiloto_jugadas.resumen_contexto(contexto)]
        jugadas = copiloto_jugadas.calcular_jugadas(contexto)
        if jugadas:
            lineas.append("Lo que más te conviene ahora: " + jugadas[0]["titulo"].lower() + ".")
        lineas.append("Pregúntame lo que quieras: cómo subir de estado, cómo invitar a alguien o cómo cerrar un encargo.")
        return " ".join(lineas), None

    if intencion == "que_es_ruana":
        return conocimiento.FAQ[0]["respuesta"], None

    if intencion == "apoyo_economico":
        return conocimiento.FAQ[1]["respuesta"], _accion_nav("solicitudes", "Ver mis encargos")

    if intencion == "invitar":
        objetivo = _oficio_objetivo(contexto)
        restantes = _recompensas_restantes(contexto)
        if contexto.get("grupo", {}).get("en_creacion") or int(grupo.get("num_aliados") or 0) <= 2:
            motivo = "Estáis empezando en tu zona."
        elif objetivo:
            motivo = f"A tu grupo le falta {objetivo.lower()}."
        else:
            motivo = "Tu grupo puede crecer."
        texto = (
            f"{motivo} Cada profesional que entra con tu código suma +3; si es de un oficio "
            f"que falta, +5, y te quedan {restantes} de {int(grupo.get('recompensas_max') or 10)}. "
            "Te abro el código y el mensaje listo para WhatsApp."
        )
        return texto, _accion_invitar(objetivo, "Invitar y compartir")

    if intencion == "redactar_invitacion":
        objetivo = _oficio_objetivo(contexto)
        mensaje = redactar_invitacion(contexto, objetivo)
        return (
            "Te he escrito el mensaje. Cópialo y mándalo por WhatsApp a la persona concreta, "
            "no como difusión: funciona mucho mejor.",
            _accion_copiar(mensaje, "Copiar mensaje"),
        )

    if intencion == "subir_score":
        sueltas = []
        if _recompensas_restantes(contexto) > 0:
            sueltas.append(
                f"invitar a un oficio que falta (+5, te quedan {_recompensas_restantes(contexto)})"
            )
        if int(contactos.get("total") or 0) == 0:
            sueltas.append("responder rápido a los primeros contactos que te lleguen (+3)")
        sueltas.append("cerrar los encargos abiertos y declarar el importe el mismo día (+2)")
        sueltas.append("entrar cada día para mantener la racha de 7 días (+3)")
        lista = "; ".join(sueltas)
        texto = (
            f"Estás en {banda} con {valor} puntos"
            + (
                f" y te faltan {score.get('puntos_al_siguiente')} para {score.get('siguiente_banda')}."
                if score.get("puntos_al_siguiente")
                else "."
            )
            + f" Lo que más mueve la aguja: {lista}. "
            f"Ojo: el score solo puede moverse {conocimiento.LIMITE_DIARIO} puntos al día, "
            "así que no hay atajos."
        )
        return texto, None

    if intencion == "por_que_baje":
        motivos = score.get("motivos_recientes") or []
        if motivos:
            partes = []
            for m in motivos[:3]:
                signo = "+" if int(m.get("delta") or 0) > 0 else ""
                partes.append(f"{signo}{m.get('delta')} por {m.get('etiqueta')}")
            texto = (
                "Tus últimos movimientos: " + "; ".join(partes) + ". "
                "Si alguno no te cuadra, escribe al equipo y lo revisan con el registro delante."
            )
            return texto, _accion_soporte("Revisar con el equipo")
        return (
            "No veo movimientos recientes en tu historial. Las bajadas habituales son dejar "
            "un mensaje sin responder 48 horas (-2), un comprobante sin subir en 3 días (-3) "
            "o dejar un contacto abierto más de una semana. Si crees que hay un error, "
            "escribe al equipo y lo revisan.",
            _accion_soporte("Revisar con el equipo"),
        )

    if intencion == "mi_estado":
        lineas = [
            f"Estás en {banda} con {valor} puntos.",
            f"Grupo: {int(grupo.get('num_aliados') or 0)} aliados"
            + (
                f", faltan {len(grupo.get('oficios_faltantes') or [])} oficios por cubrir."
                if grupo.get("tiene_grupo")
                else " (todavía sin grupo asignado)."
            ),
            f"Contactos abiertos: {int(contactos.get('total') or 0)}"
            + (
                f" ({int(contactos.get('negociacion_a_medias') or 0)} con el acuerdo a medias)."
                if int(contactos.get("negociacion_a_medias") or 0)
                else "."
            ),
        ]
        if score.get("delta_hoy"):
            lineas.append(f"Hoy te has movido {score.get('delta_hoy')} puntos.")
        return " ".join(lineas), None

    if intencion == "encargo_cerrar":
        abiertos = int(contactos.get("total") or 0)
        if abiertos:
            texto = (
                f"Ahora mismo tienes {abiertos} contacto(s) abierto(s). El orden es: acordáis "
                "servicio, fecha, hora, dirección y precio en la negociación guiada; cuando "
                "está completo, se declara el importe. Decláralo el mismo día: +2 si entras en "
                "las primeras 24 horas."
            )
            return texto, _accion_nav("solicitudes", "Abrir mis encargos")
        return (
            "Ahora no tienes encargos abiertos. Cuando entre uno, el recorrido es: llega el "
            "contacto, valoras, acordáis los cinco campos en la negociación guiada, se declara "
            "el importe y se sube el comprobante del Apoyo. Todo desde «Solicitudes».",
            _accion_nav("solicitudes", "Ver solicitudes"),
        )

    if intencion == "negociacion":
        return (
            "La negociación guiada cierra cinco campos: servicio, fecha, hora, dirección y "
            "precio final. Cada parte propone, la otra acepta o hace contraoferta, y cuando "
            "los cinco están aceptados el acuerdo queda registrado con su resumen. No se "
            "cierra nada a medias.",
            _accion_nav("solicitudes", "Ir a la negociación"),
        )

    if intencion == "grupo_zona":
        if not grupo.get("tiene_grupo"):
            return (
                "Todavía no tienes grupo asignado. Los grupos se crean por código postal y "
                "plaza de oficio; en cuanto haya sitio para tu oficio, entras. Mientras, "
                "puedes completar tu perfil para que te encuentren mejor.",
                _accion_nav("perfil", "Completar perfil"),
            )
        faltantes = list(grupo.get("oficios_faltantes") or [])
        ejemplo = ", ".join(str(f).lower() for f in faltantes[:5])
        texto = (
            f"Tu grupo ({grupo.get('nombre') or 'tu zona'}) tiene {int(grupo.get('num_aliados') or 0)} "
            f"aliados y {int(grupo.get('num_oficios') or 0)} oficios cubiertos."
        )
        if ejemplo:
            texto += f" Falta gente de: {ejemplo}."
        texto += " Cada oficio que se cubre son encargos que ya no se van fuera."
        return texto, _accion_invitar(_oficio_objetivo(contexto), "Invitar un oficio que falta")

    if intencion == "competencia":
        if contexto.get("competencia_activa"):
            return (
                "Sí, tienes una competencia en marcha por tu plaza. Durante el periodo gana "
                "quien sostenga mejor el score: responde rápido, cierra lo abierto y no dejes "
                "comprobantes sin subir. Todo lo que hagas ahora cuenta.",
                _accion_nav("inicio", "Ver mi situación"),
            )
        return (
            "La competencia se activa cuando el score baja del umbral de 15: otra persona "
            "puede disputar tu plaza. Hoy no tienes ninguna activa. Si quieres mantenerla "
            "lejos, el mejor seguro es no dejar contactos ni comprobantes colgados.",
            None,
        )

    if intencion == "pagos":
        return (
            f"Recibir contactos es gratis. Cuando un encargo se cierra se aplica el Apoyo "
            f"RUANA del {conocimiento.APOYO_PCT:g} % sobre el importe acordado, y la app te "
            "lo muestra antes de confirmar. El cobro se hace por Bizum, transferencia o QR, y "
            "el comprobante se sube desde el mismo encargo. Si se paga con Stripe, va "
            "directo, sin que tengas que subir nada.",
            _accion_nav("solicitudes", "Ver mis pagos"),
        )

    if intencion == "perfil_catalogo":
        piezas = []
        if not perfil.get("tiene_descripcion"):
            piezas.append("te falta la descripción de lo que haces")
        if int(perfil.get("num_servicios") or 0) == 0:
            piezas.append("no tienes servicios en el catálogo")
        if piezas:
            return (
                "En tu perfil " + " y ".join(piezas) + ". Es lo primero que lee quien te "
                "encuentra: sin eso, es difícil que te pasen un encargo que encaje contigo.",
                _accion_nav("perfil", "Completar mi perfil"),
            )
        return (
            "Tu perfil está completo. Si cambias de especialidad o añades un servicio, "
            "actualízalo: el catálogo es lo que ven los demás aliados al buscarte.",
            _accion_nav("perfil", "Ver mi perfil"),
        )

    if intencion == "soporte_humano":
        return (
            "Claro. Te abro el centro de comunicación para que escribas al equipo; si cuentas "
            "qué pasó y qué encargo es, lo revisan con el registro delante.",
            _accion_soporte(),
        )

    if intencion == "gracias":
        return "A mandar. Si te surge cualquier cosa, aquí estoy.", None

    # general
    jugadas = copiloto_jugadas.calcular_jugadas(contexto)
    pista = jugadas[0]["titulo"] if jugadas else "revisar tus encargos abiertos"
    return (
        "No estoy seguro de haber entendido. Puedo ayudarte con esto: cómo subir tu score, "
        "por qué se ha movido, cómo invitar a alguien de tu zona, cómo cerrar un encargo o "
        "cómo funciona el Apoyo. Si es otra cosa, escribe al equipo.\n\n"
        f"Mientras tanto: {pista}.",
        None,
    )


# ---------------------------------------------------------------------------
# Redacción de mensajes (invitación / derivación)
# ---------------------------------------------------------------------------

def redactar_invitacion(contexto: Dict[str, Any], oficio: str = "") -> str:
    """Mensaje de invitación para una persona concreta. Sin LLM también funciona."""
    nombre = (contexto.get("nombre") or "").split(" ")[0] or "Hola"
    zona = contexto.get("codigo_postal") or "mi zona"
    grupo = contexto.get("grupo") or {}
    oficio = (oficio or _oficio_objetivo(contexto) or "").strip()
    peticiones = 0
    for d in contexto.get("demanda") or []:
        if str(d.get("oficio") or "").lower() == oficio.lower():
            peticiones = int(d.get("peticiones") or 0)
            break

    if oficio and peticiones:
        gancho = (
            f"En mi zona ({zona}) hay {peticiones} persona(s) pidiendo {oficio.lower()} esta "
            f"semana y ahora mismo no hay nadie que lo cubra, así que se están quedando sin "
            f"salida."
        )
    elif oficio:
        gancho = (
            f"En mi grupo de RUANA ({zona}) falta {oficio.lower()}: hay trabajo entrando y "
            f"nadie que lo cubra."
        )
    elif int(grupo.get("num_aliados") or 0) <= 2:
        gancho = (
            f"Estamos empezando la red en mi zona ({zona}) y necesitamos cubrir los oficios "
            f"que la gente pide."
        )
    else:
        gancho = f"En mi grupo de RUANA ({zona}) hay encargos entrando que no puedo cubrir yo."

    texto = (
        f"{nombre}: {gancho} Te paso mi código de invitación: entra, mira si te encaja y, "
        f"si sí, la plaza es tuya. Recibir contactos no cuesta nada; solo se aporta un "
        f"{conocimiento.APOYO_PCT:g} % cuando el encargo se cierra."
    )
    return texto


# ---------------------------------------------------------------------------
# Validador de cifras
# ---------------------------------------------------------------------------

_NUMERO = re.compile(r"\d+(?:[.,]\d+)?")

# Los números del 1 al 12 son enumeraciones ("2 o 3 profesionales", "1 encargo"):
# no son una afirmación sobre la cuenta del aliado, así que no se validan. Lo
# que sí se valida son las cifras con peso: score, puntos, importes y plazos.
_ENUMERACIONES = {str(n) for n in range(1, 13)}


def numeros_de(texto: str) -> List[str]:
    return [m.group(0).replace(",", ".") for m in _NUMERO.finditer(texto or "")]


def cifras_permitidas(*fuentes: str) -> set:
    permitido = set(_ENUMERACIONES)
    for fuente in fuentes:
        for numero in numeros_de(fuente):
            permitido.add(numero)
            if "." in numero:
                permitido.add(numero.split(".")[0])
    return permitido


def cifras_no_permitidas(texto: str, permitido: set) -> List[str]:
    """Cifras del texto que no están respaldadas por ninguna fuente.

    Un decimal se compara entero («7,5 %» no pasa por tener un 7 permitido):
    el porcentaje es una afirmación, no una enumeración.
    """
    fuera: List[str] = []
    for numero in numeros_de(texto):
        if numero in permitido:
            continue
        fuera.append(numero)
    return fuera


def validar_cifras(texto: str, permitido: set) -> bool:
    """True si todas las cifras del texto aparecen en las fuentes."""
    return not cifras_no_permitidas(texto, permitido)


_PALABRA = re.compile(r"[a-záéíóúñü]{5,}")


def _palabras_relevantes(texto: str) -> set:
    return set(_PALABRA.findall((texto or "").lower()))


def cubre_la_base(candidata: str, base: str, umbral: float = 0.45) -> bool:
    """True si la respuesta del modelo conserva lo esencial de la base.

    El modelo tiende a responder con generalidades («estás en ESTABLE…») cuando
    la pregunta tiene una respuesta concreta (el 5 %, los pasos para invitar).
    Si no recoge al menos el `umbral` de las palabras significativas de la base,
    se descarta: mejor una respuesta seca y correcta que una florida y vacía.
    """
    base_palabras = _palabras_relevantes(base)
    if not base_palabras:
        return True
    candidata_palabras = _palabras_relevantes(candidata)
    cubiertas = base_palabras & candidata_palabras
    return (len(cubiertas) / len(base_palabras)) >= umbral


# ---------------------------------------------------------------------------
# Prompt del LLM
# ---------------------------------------------------------------------------

_SYSTEM = """Eres el copiloto de RUANA, una red de profesionales por código postal.
Hablas dentro del panel del aliado, en español de España, tuteando, con frases
cortas y sin jerga. Eres como un compañero de la red que conoce las reglas.

Lo que sabes hacer:
- Explicar qué es RUANA y cómo se usa la app. Si te preguntan qué es, usa la
  DEFINICIÓN OFICIAL que viene en el mensaje y no omitas estas tres ideas:
  (1) es una red de apoyo entre profesionales de la misma zona;
  (2) tú invitas de forma exclusiva, con tu código, a profesionales que
      conoces y en los que confías, y cada oficio tiene su plaza;
  (3) os pasáis los encargos entre vosotros, para que ninguno pierda un
      trabajo que no puede atender.
- Decir qué le conviene hacer ahora para cuidar su score.
- Ayudar a invitar a un profesional de un oficio que falta.
- Guiar el cierre de un encargo y el Apoyo RUANA.

Reglas que NO puedes saltarte:
- Usa SOLO las cifras que aparecen en DATOS y REGLAS. Si un número no está ahí,
  no lo escribas.
- Nunca prometas trabajo, clientes, ingresos ni puntos. Describe la regla:
  "según las reglas, +5", nunca "vas a ganar 5 puntos".
- Nunca inventes precios, plazas, nombres ni fechas.
- No hables de otros aliados ni de sus datos.
- Máximo 90 palabras. Texto plano: sin markdown, sin listas con guiones.
- Si no sabes algo o es un problema de su cuenta, dile que escriba al equipo
  RUANA desde el propio panel.
"""


def _prompt_usuario(
    contexto: Dict[str, Any], mensaje: str, intencion: str, respuesta_base: str = ""
) -> str:
    """Orden del prompt: primero la pregunta y la respuesta correcta.

    Con el bloque de datos delante, el modelo tendía a resumir el estado del
    aliado («estás en ESTABLE con 50 puntos…») e ignoraba la pregunta. Poniendo
    delante la pregunta y la base, la respeta y usa el resto como apoyo.
    """
    datos = copiloto_contexto.contexto_para_llm(contexto)
    bloques: List[str] = []

    bloques.append(f"EL ALIADO PREGUNTA: {mensaje}")
    bloques.append(f"INTENCIÓN DETECTADA: {intencion}")

    if intencion == "que_es_ruana":
        bloques.append(
            "DEFINICIÓN OFICIAL DE RUANA (úsala tal cual en lo esencial; no la "
            "sustituyas por otra):\n" + conocimiento.DEFINICION_RUANA
        )

    if respuesta_base:
        bloques.append(
            "RESPUESTA CORRECTA (está verificada; reescríbela con naturalidad, sin "
            "contradecirla ni omitir sus datos):\n" + respuesta_base
        )

    bloques.append(
        "DATOS DEL ALIADO (apóyate en ellos solo si vienen al caso; no los "
        "recites de pasada):\n" + json.dumps(datos, ensure_ascii=False, indent=1)
    )
    bloques.append("REGLAS VIGENTES:\n" + conocimiento.tabla_puntos_texto())
    bloques.append(conocimiento.ficha_producto())
    return "\n\n".join(bloques)


# ---------------------------------------------------------------------------
# API pública
# ---------------------------------------------------------------------------

def _limpiar_historial(historial: Any) -> List[Dict[str, str]]:
    salida: List[Dict[str, str]] = []
    if not isinstance(historial, list):
        return salida
    for item in historial[-_MAX_HISTORIAL:]:
        if not isinstance(item, dict):
            continue
        rol = str(item.get("rol") or item.get("role") or "").strip().lower()
        texto = str(item.get("texto") or item.get("content") or "").strip()
        if not texto:
            continue
        salida.append(
            {
                "role": "assistant" if rol in {"copiloto", "assistant", "bot"} else "user",
                "content": texto[:1500],
            }
        )
    return salida


def construir_contexto(db, codigo: str) -> Dict[str, Any]:
    return copiloto_contexto.construir_contexto(db, codigo)


def estado(db, codigo: str) -> Dict[str, Any]:
    """Saludo inicial + jugadas + capacidad de IA. Para abrir el panel."""
    contexto = copiloto_contexto.construir_contexto(db, codigo)
    jugadas = copiloto_jugadas.calcular_jugadas(contexto)
    info_ia = copiloto_llm.estado_publico()
    saludo = copiloto_jugadas.resumen_contexto(contexto)
    if jugadas:
        saludo += " " + jugadas[0]["titulo"] + "."
    return {
        "saludo": saludo,
        "jugadas": jugadas,
        "ia": info_ia,
        "mensajes_restantes_hoy": _cuota_restante(codigo) if info_ia.get("activa") else None,
        "sugerencias": _sugerencias(contexto),
    }


def _sugerencias(contexto: Dict[str, Any]) -> List[str]:
    base = ["¿Cómo subo mi score?", "¿Cómo invito a alguien?", "¿Cuánto cobra RUANA?"]
    if int((contexto.get("contactos") or {}).get("total") or 0) > 0:
        base.insert(0, "¿Cómo cierro un encargo?")
    if contexto.get("competencia_activa"):
        base.insert(0, "¿Qué pasa con mi plaza?")
    return base[:4]


def conversar(
    db,
    codigo: str,
    mensaje: str,
    historial: Any = None,
    contexto: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Un turno de conversación. Nunca lanza: siempre devuelve algo útil."""
    texto = (mensaje or "").strip()
    if not texto:
        return {
            "status": "error",
            "message": "Escribe una pregunta y te contesto.",
        }
    texto = texto[:600]

    contexto = contexto or copiloto_contexto.construir_contexto(db, codigo)
    if not contexto.get("ok"):
        return {
            "status": "error",
            "message": "No he podido cargar tu ficha. Recarga el panel y vuelve a intentarlo.",
        }

    intencion = conocimiento.clasificar(texto)
    respuesta, accion = _respuesta_determinista(contexto, intencion, texto)
    fuente = "reglas"

    # «Qué es RUANA» es copy de marca: se responde con la definición canónica y
    # no se deja reescribir al modelo. Probado con DeepSeek: aunque la definición
    # va la primera del prompt, la reformulaba a «red de profesionales por código
    # postal» y perdía la invitación exclusiva y el pasarse encargos.
    if intencion == "que_es_ruana":
        return {
            "status": "success",
            "texto": respuesta,
            "accion": None,
            "fuente": fuente,
            "intencion": intencion,
            "ia": copiloto_llm.estado_publico(),
            "mensajes_restantes_hoy": _cuota_restante(codigo),
        }

    if copiloto_llm.disponible() and _cuota_permite(codigo):
        permitido = cifras_permitidas(
            json.dumps(copiloto_contexto.contexto_para_llm(contexto), ensure_ascii=False),
            conocimiento.tabla_puntos_texto(),
            conocimiento.ficha_producto(),
            respuesta,
            texto,
        )
        candidata = copiloto_llm.responder(
            _SYSTEM,
            _limpiar_historial(historial)
            + [
                {
                    "role": "user",
                    "content": _prompt_usuario(contexto, texto, intencion, respuesta),
                }
            ],
        )
        if (
            candidata
            and validar_cifras(candidata, permitido)
            and cubre_la_base(candidata, respuesta)
        ):
            respuesta = candidata
            fuente = "ia"
        elif candidata:
            logger.info(
                "Copiloto: respuesta del modelo descartada por cifras no verificadas",
                extra={
                    "aliado_codigo": codigo,
                    "intencion": intencion,
                    "cifras_fuera": cifras_no_permitidas(candidata, permitido)[:6],
                    "cubre_base": cubre_la_base(candidata, respuesta),
                },
            )

    return {
        "status": "success",
        "texto": respuesta,
        "accion": accion,
        "fuente": fuente,
        "intencion": intencion,
        "ia": copiloto_llm.estado_publico(),
        "mensajes_restantes_hoy": _cuota_restante(codigo),
    }


def redactar(db, codigo: str, tipo: str, oficio: str = "", notas: str = "") -> Dict[str, Any]:
    """Redacta un texto listo para enviar. Devuelve siempre algo."""
    contexto = copiloto_contexto.construir_contexto(db, codigo)
    if not contexto.get("ok"):
        return {"status": "error", "message": "No he podido cargar tu ficha."}

    tipo = (tipo or "invitacion").strip().lower()

    if tipo == "invitacion":
        texto = redactar_invitacion(contexto, oficio)
        if copiloto_llm.disponible() and _cuota_permite(codigo):
            permitido = cifras_permitidas(
                json.dumps(copiloto_contexto.contexto_para_llm(contexto), ensure_ascii=False),
                conocimiento.tabla_puntos_texto(),
                conocimiento.ficha_producto(),
            )
            pulido = copiloto_llm.responder(
                _SYSTEM
                + "\nAhora tu tarea es escribir UN mensaje de WhatsApp para invitar a un "
                "profesional concreto. Máximo 60 palabras, natural, sin sonar a publicidad y "
                "sin emojis. Devuelve solo el mensaje.",
                [
                    {
                        "role": "user",
                        "content": (
                            f"Oficio a invitar: {oficio or 'el que falta en mi grupo'}\n"
                            f"Borrador: {texto}"
                        ),
                    }
                ],
            )
            if pulido and validar_cifras(pulido, permitido):
                texto = pulido
        return {"status": "success", "texto": texto, "tipo": tipo}

    if tipo == "derivacion":
        texto = (
            "Al final no puedo cogerlo, pero conozco a quien sí. Te paso con un compañero "
            "del grupo que hace justo eso; puedes cerrar con él las condiciones igual que "
            "harías conmigo. Si por lo que sea no sale, dímelo y te busco otra opción."
        )
        return {"status": "success", "texto": texto, "tipo": tipo}

    return {"status": "error", "message": "Tipo de texto no reconocido."}


def jugadas(db, codigo: str) -> Dict[str, Any]:
    contexto = copiloto_contexto.construir_contexto(db, codigo)
    return {
        "status": "success" if contexto.get("ok") else "error",
        "jugadas": copiloto_jugadas.calcular_jugadas(contexto),
    }
