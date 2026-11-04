"""Conocimiento del Copiloto RUANA: reglas del score, preguntas frecuentes e
intenciones del aliado.

Fuente de verdad: las constantes reales de `db_manager` / `db_constants` /
`score_service`. Si una regla cambia en el motor, se cambia aquí y los tests
avisan. Nada de este módulo depende de Flask ni de red.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

# ---------------------------------------------------------------------------
# Reglas del score (leídas del motor)
# ---------------------------------------------------------------------------

BANDAS = [
    (350, 500, "ÉLITE"),
    (200, 349, "DESTACADO"),
    (50, 199, "ESTABLE"),
    (15, 49, "EN RIESGO"),
    (0, 14, "COMPETENCIA"),
]

# (id, puntos, título, cuándo se gana)
REGLAS_SUBEN: List[Dict[str, Any]] = [
    {
        "id": "invitar_oficio",
        "puntos": 5,
        "titulo": "Invitar a un profesional de un oficio que falta en tu grupo",
        "detalle": "Hasta 10 recompensas por aliado. Es lo que más puntos da.",
    },
    {
        "id": "invitacion_oficio_usada",
        "puntos": 5,
        "titulo": "Que se registre alguien con tu invitación por oficio",
        "detalle": "Se suma al anterior: invitas y entra.",
    },
    {
        "id": "referido_registro",
        "puntos": 3,
        "titulo": "Que se registre alguien con tu código de invitación",
        "detalle": "Invitación normal (ampliar red).",
    },
    {
        "id": "encargos_mes",
        "puntos": 3,
        "titulo": "4 encargos pagados y limpios en el mes",
        "detalle": "Sin conflictos de pago abiertos.",
    },
    {
        "id": "respuesta_rapida",
        "puntos": 3,
        "titulo": "Responder en menos de 1 hora a 3 clientes distintos",
        "detalle": "El primero deja el mensaje y tú contestas antes de 1 hora.",
    },
    {
        "id": "urgente_mismo_dia",
        "puntos": 3,
        "titulo": "Gestionar un encargo urgente el mismo día",
        "detalle": "El contacto marcado como urgente se cierra sin dejar pasar el día.",
    },
    {
        "id": "declaracion_24h",
        "puntos": 2,
        "titulo": "Declarar el cierre del trabajo en 24 horas",
        "detalle": "A veces vale más no perder los 2 que ganarlos.",
    },
    {
        "id": "racha_7dias",
        "puntos": 3,
        "titulo": "Entrar a la app 7 días seguidos",
        "detalle": "La constancia cuenta: mira tus encargos cada día.",
    },
]

# (id, puntos, título, cuándo se pierde)
REGLAS_BAJAN: List[Dict[str, Any]] = [
    {"id": "contacto_no_concretado", "puntos": -1, "titulo": "Cerrar un contacto sin que salga el trabajo"},
    {"id": "descendiente_competencia", "puntos": -2, "titulo": "Que alguien a quien invitaste caiga a competencia"},
    {"id": "comprobante_3d", "puntos": -3, "titulo": "No subir el comprobante del Apoyo en 3 días"},
    {"id": "chat_48h", "puntos": -2, "titulo": "Dejar un mensaje sin responder 48 horas"},
    {"id": "chat_agotado", "puntos": -2, "titulo": "Agotar una conversación sin cerrar el resultado"},
    {"id": "disputa_perdida", "puntos": -3, "titulo": "Perder una disputa de importe"},
    {"id": "sin_acceso_7d", "puntos": -1, "titulo": "No entrar a la app en toda la semana"},
    {"id": "contacto_abierto", "puntos": -2, "titulo": "Dejar un contacto abierto 7 o 21 días"},
]

LIMITE_DIARIO = 10
SCORE_MIN = 0
SCORE_MAX = 500
SCORE_INICIAL = 50
APOYO_PCT = 5.0
MAX_GRUPOS_POR_CP = 5
MAX_RECOMPENSAS_CRECIMIENTO = 10


def banda_de_score(score: Any) -> Dict[str, Any]:
    """Banda y distancia al siguiente escalón, sin tocar la BD."""
    try:
        valor = int(score)
    except (TypeError, ValueError):
        valor = 0
    for minimo, maximo, nombre in BANDAS:
        if minimo <= valor <= maximo:
            siguientes = [(b[0], b[2]) for b in BANDAS if b[0] > maximo]
            siguiente = min(siguientes) if siguientes else None
            return {
                "score": valor,
                "banda": nombre,
                "minimo": minimo,
                "maximo": maximo,
                "puntos_al_siguiente": (siguiente[0] - valor) if siguiente else 0,
                "siguiente_banda": siguiente[1] if siguiente else None,
            }
    return {
        "score": valor,
        "banda": "COMPETENCIA",
        "minimo": 0,
        "maximo": 14,
        "puntos_al_siguiente": max(0, 15 - valor),
        "siguiente_banda": "EN RIESGO",
    }


def tabla_puntos_texto() -> str:
    lineas = ["Lo que suma puntos:"]
    for r in REGLAS_SUBEN:
        detalle = f" ({r['detalle']})" if r.get("detalle") else ""
        lineas.append(f"  +{r['puntos']} · {r['titulo']}{detalle}")
    lineas.append("Lo que resta:")
    for r in REGLAS_BAJAN:
        lineas.append(f"  {r['puntos']} · {r['titulo']}")
    lineas.append(
        f"El score va de {SCORE_MIN} a {SCORE_MAX} y solo puede moverse "
        f"{LIMITE_DIARIO} puntos al día."
    )
    lineas.append(
        "No confundirlas: la invitación POR OFICIO da +5 al invitar y otros +5 "
        "cuando esa persona se registra con ella. La invitación normal (ampliar "
        "red) da +3 al registrarse. No son intercambiables."
    )
    return "\n".join(lineas)


def ficha_producto() -> str:
    """Datos institucionales que el copiloto puede afirmar sin mirar la BD.

    Si un dato no está aquí ni en el contexto del aliado, el copiloto no debe
    decirlo: tiene que remitir al equipo. Es la lista blanca de hechos.
    """
    return "\n".join(
        [
            "FICHA DEL PRODUCTO:",
            "- Recibir un contacto no cuesta nada.",
            f"- Solo al cerrar un encargo se aporta el Apoyo RUANA: {APOYO_PCT:g} % del "
            "importe acordado. La app muestra el importe antes de confirmar y el "
            "porcentaje guardado con cada encargo no se recalcula después.",
            "- El cobro se hace por Bizum, transferencia o QR, y el comprobante se sube "
            "desde el propio encargo. Con Stripe Connect el pago va directo.",
            f"- El score va de {SCORE_MIN} a {SCORE_MAX} y solo puede moverse "
            f"{LIMITE_DIARIO} puntos al día.",
            "- Bandas: ÉLITE 350-500, DESTACADO 200-349, ESTABLE 50-199, "
            "EN RIESGO 15-49, COMPETENCIA 0-14 (por debajo de 15 se puede disputar la plaza).",
            "- La plaza es por oficio principal dentro del grupo de tu código postal.",
            f"- Como máximo {MAX_GRUPOS_POR_CP} grupos activos por código postal.",
            "- Se exige mayoría de edad y aceptar privacidad y términos para registrarse.",
            "- Inactividad: sin entrar una semana resta puntos; el comprobante tiene "
            "3 días; la declaración del cierre, 24 horas; un mensaje sin responder "
            "48 horas empieza a restar.",
        ]
    )


# ---------------------------------------------------------------------------
# Intenciones
# ---------------------------------------------------------------------------

# Orden importa: la primera coincidencia gana.
_INTENCIONES: List[Dict[str, Any]] = [
    {
        "id": "soporte_humano",
        "patrones": [
            r"\bhablar con (una persona|alguien|el equipo|un humano)\b",
            r"\bpersona real\b",
            r"\bno me (entiendes|ayudas)\b",
            r"\breclam(aci[oó]n|ar)\b",
            r"\bqueja\b",
            r"\bincidencia\b",
        ],
    },
    {
        "id": "redactar_invitacion",
        "patrones": [
            r"\bescr[ií]beme\b.*\binvitaci[oó]n\b",
            r"\bred[aá]ctame\b",
            r"\bmensaje\b.*\b(invitar|invitaci[oó]n|whatsapp)\b",
            r"\btexto para invitar\b",
        ],
    },
    {
        "id": "por_que_baje",
        "patrones": [
            r"\bpor qu[eé] (baj[eé]|he bajado|baj[oó]|me han quitado)\b",
            r"\bme han (quitado|restado|penalizado)\b",
            r"\bpenalizaci[oó]n\b",
            r"\bsancion",
            r"\bhe perdido puntos\b",
        ],
    },
    {
        "id": "subir_score",
        "patrones": [
            r"\bsubir (el |mi )?score\b",
            r"\bganar (puntos|score)\b",
            r"\bc[oó]mo (gano|subo|mejoro)\b",
            r"\bmejorar (mi )?(score|puntuaci[oó]n)\b",
            r"\bpuntos\b",
        ],
    },
    {
        "id": "mi_estado",
        "patrones": [
            r"\bc[oó]mo voy\b",
            r"\bmi (estado|score|puntuaci[oó]n|situaci[oó]n)\b",
            r"\bqu[eé] tal voy\b",
            r"\bc[oó]mo estoy\b",
        ],
    },
    {
        "id": "invitar",
        "patrones": [
            r"\binvit(o|as|ar|a|e|en|aría|amos)\b",
            r"\binvitaci[oó]n\b",
            r"\bc[oó]digo\b.*\b(invit|compart|pasar)\b",
            r"\bampliar (mi )?red\b",
            r"\btraer (gente|aliados|profesionales)\b",
            r"\breferir\b",
        ],
    },
    {
        "id": "apoyo_economico",
        "patrones": [
            r"\bcu[aá]nto (cobra|cobr[aá]is|se lleva|me quitan|cuesta)\b",
            r"\bcomisi[oó]n\b",
            r"\bapoyo\b.*\b(5|porcentaje|pct|%)?\b",
            r"\bporcentaje\b",
            r"\bqu[eé] es el apoyo\b",
            r"\bcuota\b",
        ],
    },
    {
        "id": "encargo_cerrar",
        "patrones": [
            r"\bcerrar (un |el )?(encargo|contacto|trabajo)\b",
            r"\bdeclarar\b.*\b(importe|cierre|trabajo)\b",
            r"\bimporte\b",
            r"\bc[oó]mo cierro\b",
        ],
    },
    {
        "id": "negociacion",
        "patrones": [
            r"\bnegociaci[oó]n\b",
            r"\bpropuesta\b",
            r"\bcontraoferta\b",
            r"\bpresupuesto\b",
            r"\bacuerdo\b",
        ],
    },
    {
        "id": "grupo_zona",
        "patrones": [
            r"\bmi grupo\b",
            r"\bmi zona\b",
            r"\bsin grupo\b",
            r"\bc[oó]digo postal\b",
            r"\bvecinos?\b",
            r"\btodav[ií]a no hay\b",
        ],
    },
    {
        "id": "competencia",
        "patrones": [
            r"\bcompetencia\b",
            r"\bme (van a|quieren) retar\b",
            r"\bretador\b",
            r"\bsuplente\b",
            r"\bme van a echar\b",
            r"\bexpulsi[oó]n\b",
        ],
    },
    {
        "id": "pagos",
        "patrones": [
            r"\bbizum\b",
            r"\biban\b",
            r"\btransferencia\b",
            r"\bstripe\b",
            r"\bcobrar\b",
            r"\bcobro\b",
            r"\bcomprobante\b",
            r"\bfactura\b",
            r"\bqr\b",
        ],
    },
    {
        "id": "perfil_catalogo",
        "patrones": [
            r"\bmi perfil\b",
            r"\bcat[aá]logo\b",
            r"\bdescripci[oó]n\b",
            r"\bmi foto\b",
            r"\bme falta(n)? datos\b",
        ],
    },
    {
        "id": "que_es_ruana",
        "patrones": [
            r"\bqu[eé] es ruana\b",
            r"\bc[oó]mo funciona (ruana|esto|la app)\b",
            r"\bpara qu[eé] sirve\b",
            r"\bno entiendo (ruana|esto|la app)\b",
        ],
    },
    {
        "id": "gracias",
        "patrones": [r"\bgracias\b", r"\bgenial\b", r"\bperfecto\b", r"\bvale\b"],
    },
    {
        "id": "saludo",
        "patrones": [r"^\s*(hola|buenas|hey|qu[eé] tal|buenos d[ií]as)\b"],
    },
]

_compiladas = [
    (item["id"], [re.compile(p, re.IGNORECASE) for p in item["patrones"]])
    for item in _INTENCIONES
]


def clasificar(texto: str) -> str:
    """Intención determinista del mensaje. Nunca lanza."""
    limpio = (texto or "").strip()
    if not limpio:
        return "saludo"
    if len(limpio) <= 3:
        return "saludo"
    for ident, patrones in _compiladas:
        for patron in patrones:
            try:
                if patron.search(limpio):
                    return ident
            except re.error:  # pragma: no cover - patrones son constantes
                continue
    return "general"


# ---------------------------------------------------------------------------
# Preguntas frecuentes (respuesta canónica, sin IA)
# ---------------------------------------------------------------------------

FAQ: List[Dict[str, Any]] = [
    {
        "intencion": "que_es_ruana",
        "pregunta": "¿Qué es RUANA?",
        "respuesta": (
            "RUANA es una red de profesionales organizada por código postal. "
            "La idea es simple: el encargo que tú no haces se lo pasas a alguien "
            "de tu zona que sí sabe, y cuando a esa persona le sobra algo que es "
            "tuyo, te lo pasa a ti. Todo queda registrado: contactos, importes y "
            "cumplimiento."
        ),
    },
    {
        "intencion": "apoyo_economico",
        "pregunta": "¿Cuánto cobra RUANA?",
        "respuesta": (
            f"Recibir un contacto no cuesta nada. Solo cuando un encargo se cierra "
            f"se aplica el Apoyo RUANA: un {APOYO_PCT:g} % del importe acordado. "
            f"La app te muestra el importe del apoyo antes de que confirmes el cierre, "
            f"y el porcentaje que se guardó con ese encargo no se recalcula después."
        ),
    },
    {
        "intencion": "invitar",
        "pregunta": "¿Cómo invito a alguien?",
        "respuesta": (
            "Desde «Ampliar mi red» generas tu código y compartes el enlace. "
            "Si la persona entra con tu código, ganas +3 de score. Si además es de "
            "un oficio que falta en tu grupo y usas la invitación por oficio, ganas "
            f"+5, hasta {MAX_RECOMPENSAS_CRECIMIENTO} veces."
        ),
    },
    {
        "intencion": "encargo_cerrar",
        "pregunta": "¿Cómo cierro un encargo?",
        "respuesta": (
            "El encargo se cierra en dos pasos: primero el acuerdo (servicio, fecha, "
            "hora, dirección y precio, que se confirma en la negociación guiada) y "
            "después la declaración del importe. Declara el cierre en las primeras "
            "24 horas: si lo dejas pasar, pierdes los +2 de esa regla."
        ),
    },
]


def faq_para(intencion: str) -> Optional[Dict[str, Any]]:
    for item in FAQ:
        if item["intencion"] == intencion:
            return item
    return None


# ---------------------------------------------------------------------------
# Qué oficio merece la pena invitar primero
# ---------------------------------------------------------------------------

# Orden de utilidad real para una red de encargos domésticos: los oficios que
# más se piden en una zona y que más "arrastran" a los demás.
_OFICIOS_PRIORITARIOS = (
    "electricidad",
    "fontaner",
    "albañil",
    "cerrajer",
    "manitas",
    "limpieza",
    "pintura",
    "climatiz",
    "carpinter",
    "impermeabiliz",
    "mudanza",
    "electrodom",
    "cristaler",
    "jardiner",
    "persiana",
    "tejad",
)


def _normalizar(texto: str) -> str:
    return (
        str(texto or "")
        .lower()
        .replace("á", "a")
        .replace("é", "e")
        .replace("í", "i")
        .replace("ó", "o")
        .replace("ú", "u")
        .replace("ñ", "n")
    )


def prioridad_oficio(oficio: str) -> int:
    """Menor es mejor. Los oficios sin prioridad van al final."""
    clave = _normalizar(oficio)
    for posicion, fragmento in enumerate(_OFICIOS_PRIORITARIOS):
        if fragmento in clave:
            return posicion
    return len(_OFICIOS_PRIORITARIOS) + 1


def elegir_oficio_para_invitar(
    faltantes: List[str], demanda: Optional[List[Dict[str, Any]]] = None
) -> str:
    """El oficio que más conviene invitar: primero por demanda, luego por utilidad."""
    limpios = [str(o).strip() for o in (faltantes or []) if str(o or "").strip()]
    if not limpios:
        return ""
    peticiones = {
        _normalizar(d.get("oficio")): int(d.get("peticiones") or 0)
        for d in (demanda or [])
        if isinstance(d, dict)
    }
    return min(
        limpios,
        key=lambda oficio: (
            -peticiones.get(_normalizar(oficio), 0),
            prioridad_oficio(oficio),
            _normalizar(oficio),
        ),
    )
