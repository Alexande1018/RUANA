"""Motor de "siguiente jugada" del Copiloto RUANA.

Convierte las reglas del score en 1-3 acciones concretas, ordenadas por
urgencia. No usa IA generativa: es determinista y testeable, y es la fuente
que el LLM se limita a explicar con palabras.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from core.services import copiloto_conocimiento as conocimiento

_PESO_URGENCIA = {"alta": 3, "media": 2, "baja": 1}


def _jugada(
    ident: str,
    urgencia: str,
    titulo: str,
    detalle: str,
    impacto: str,
    accion: Dict[str, Any],
    cta: str,
) -> Dict[str, Any]:
    return {
        "id": ident,
        "urgencia": urgencia,
        "titulo": titulo,
        "detalle": detalle,
        "impacto": impacto,
        "accion": accion,
        "cta": cta,
    }


def _prioridad(jugada: Dict[str, Any]) -> int:
    return _PESO_URGENCIA.get(jugada.get("urgencia") or "baja", 1)


def _oficio_con_demanda(contexto: Dict[str, Any], faltantes: List[str]) -> Optional[Dict[str, Any]]:
    """Oficio que falta en el grupo Y que la zona ha pedido esta semana."""
    if not faltantes:
        return None
    porque = {str(d.get("oficio") or "").lower(): d for d in (contexto.get("demanda") or [])}
    mejor = None
    for oficio in faltantes:
        clave = str(oficio or "").lower()
        dato = porque.get(clave)
        if not dato:
            continue
        if mejor is None or int(dato.get("peticiones") or 0) > int(mejor[1].get("peticiones") or 0):
            mejor = (oficio, dato)
    if not mejor:
        return None
    return {"oficio": mejor[0], "peticiones": int(mejor[1].get("peticiones") or 0)}


def _primera_faltante(faltantes: List[str]) -> Optional[str]:
    """Oficio que mejor encaja para invitar (demanda primero, luego utilidad)."""
    elegido = conocimiento.elegir_oficio_para_invitar(faltantes, [])
    return elegido or None


def calcular_jugadas(contexto: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Devuelve hasta 3 jugadas ordenadas. Nunca lanza."""
    if not contexto or not contexto.get("ok"):
        return []

    jugadas: List[Dict[str, Any]] = []
    contactos = contexto.get("contactos") or {}
    grupo = contexto.get("grupo") or {}
    score = contexto.get("score") or {}
    perfil = contexto.get("perfil") or {}
    detalle = contactos.get("detalle") or []

    # 1. Un contacto abierto demasiado tiempo: es una penalización en marcha.
    antiguos = [c for c in detalle if int(c.get("dias_abierto") or 0) >= 7]
    if antiguos:
        peor = max(antiguos, key=lambda c: int(c.get("dias_abierto") or 0))
        dias = int(peor.get("dias_abierto") or 0)
        jugadas.append(
            _jugada(
                "contacto_abierto",
                "alta",
                f"Una conversación lleva {dias} días abierta",
                "Los contactos sin cerrar empiezan a restar puntos a partir de los 7 días. "
                "Abre la conversación y cierra el resultado, aunque sea para decir que no sale.",
                "Hasta -2 si se alarga",
                {"tipo": "nav", "destino": "solicitudes"},
                "Cerrar el resultado",
            )
        )

    # 2. Negociación a medias: falta un campo por acordar.
    a_medias = [c for c in detalle if not c.get("negociacion_completa")]
    if a_medias:
        paso = (a_medias[0].get("paso_pendiente") or "").strip()
        falta = f" Te falta «{paso}»." if paso else ""
        jugadas.append(
            _jugada(
                "negociacion_paso",
                "alta",
                "Tienes un acuerdo sin cerrar",
                f"La negociación guiada está a medias.{falta} Hasta que se acuerde el precio "
                "no se puede cerrar el encargo ni declarar el importe.",
                "Desbloquea el encargo",
                {"tipo": "nav", "destino": "solicitudes"},
                "Terminar el acuerdo",
            )
        )

    # 3. Encargo terminado sin declarar importe (solo el profesional).
    sin_importe = int(contactos.get("sin_importe") or 0)
    if sin_importe:
        jugadas.append(
            _jugada(
                "declarar_importe",
                "alta",
                "Te falta declarar el importe",
                "Tienes un encargo en marcha sin importe declarado. Declararlo en las primeras "
                "24 horas suma +2; dejarlo pasar te deja sin ese punto.",
                "+2 si declaras hoy",
                {"tipo": "nav", "destino": "solicitudes"},
                "Declarar ahora",
            )
        )

    # 4. Invitar al oficio que la zona está pidiendo y el grupo no cubre.
    faltantes = list(grupo.get("oficios_faltantes") or [])
    usadas = int(grupo.get("recompensas_usadas") or 0)
    maximo = int(grupo.get("recompensas_max") or 10)
    restantes = max(0, maximo - usadas)
    objetivo = _oficio_con_demanda(contexto, faltantes)
    if objetivo and restantes > 0:
        jugadas.append(
            _jugada(
                "invitar_demanda",
                "alta",
                f"Tu zona pide {objetivo['oficio'].lower()} y tu grupo no lo cubre",
                f"{objetivo['peticiones']} personas de tu zona pidieron "
                f"{objetivo['oficio'].lower()} esta semana. Si entra alguien de ese oficio, "
                "esos encargos se quedan dentro del grupo.",
                f"+5 de score · te quedan {restantes} recompensas",
                {"tipo": "invitar", "oficio": objetivo["oficio"]},
                "Invitar: " + str(objetivo["oficio"]),
            )
        )
    elif faltantes and restantes > 0:
        oficio = conocimiento.elegir_oficio_para_invitar(
            faltantes, contexto.get("demanda") or []
        )
        if oficio:
            jugadas.append(
                _jugada(
                    "invitar_oficio",
                    "media",
                    f"A tu grupo le falta {oficio.lower()}",
                    f"Tu grupo tiene {int(grupo.get('num_aliados') or 0)} aliados. "
                    f"Cada oficio que se cubre abre encargos nuevos para todos.",
                    f"+5 de score · te quedan {restantes} recompensas",
                    {"tipo": "invitar", "oficio": oficio},
                    "Invitar: " + str(oficio),
                )
            )

    # 5. Perfil que no vende: sin descripción o sin catálogo.
    if not perfil.get("tiene_descripcion") or int(perfil.get("num_servicios") or 0) == 0:
        falta = []
        if not perfil.get("tiene_descripcion"):
            falta.append("una descripción de lo que haces")
        if int(perfil.get("num_servicios") or 0) == 0:
            falta.append("servicios en el catálogo")
        jugadas.append(
            _jugada(
                "completar_perfil",
                "media",
                "Tu perfil todavía no explica lo que haces",
                "Te falta " + " y ".join(falta) + ". Es lo primero que lee quien te encuentra "
                "en el directorio, y lo que decide si te pasa un encargo.",
                "Más encargos que encajan",
                {"tipo": "nav", "destino": "perfil"},
                "Completar perfil",
            )
        )

    # 6. Competencia activa: lo más importante de todo.
    if contexto.get("competencia_activa"):
        jugadas.append(
            _jugada(
                "competencia_activa",
                "alta",
                "Tienes una competencia en marcha",
                "Alguien está disputando tu plaza. Gana quien sostenga mejor el score durante "
                "el periodo: responde rápido, cierra lo que tengas abierto y no dejes "
                "comprobantes pendientes.",
                "Tu plaza está en juego",
                {"tipo": "nav", "destino": "inicio"},
                "Ver mi situación",
            )
        )

    # 7. Red vacía o grupo empezando: la palanca es invitar.
    if grupo.get("tiene_grupo") and int(grupo.get("num_aliados") or 0) <= 2 and restantes > 0:
        jugadas.append(
            _jugada(
                "grupo_pequeno",
                "media",
                "Estáis muy pocos en tu zona",
                "Con un grupo pequeño, casi todo lo que entra se queda sin cubrir. "
                "Dos o tres profesionales de oficios distintos cambian la dinámica del grupo.",
                f"+5 por cada uno · hasta {maximo} veces",
                {"tipo": "invitar", "oficio": _primera_faltante(faltantes) or ""},
                "Ampliar mi red",
            )
        )

    # 8. Red de seguridad: si no hay nada urgente, la jugada barata del día.
    if not jugadas:
        jugadas.append(
            _jugada(
                "visita_diaria",
                "baja",
                "Estás al día",
                "No tienes contactos abiertos ni nada pendiente. Entrar cada día mantiene la "
                "racha de 7 días (+3) y evita el -1 por semana sin acceso.",
                "+3 con la racha de 7 días",
                {"tipo": "nav", "destino": "directorio"},
                "Ver mi zona",
            )
        )

    jugadas.sort(key=_prioridad, reverse=True)
    return jugadas[:3]


def resumen_contexto(contexto: Dict[str, Any]) -> str:
    """Una línea con el estado, para abrir el chat."""
    if not contexto or not contexto.get("ok"):
        return "No he podido cargar tu ficha. Prueba a recargar el panel."
    score = contexto.get("score") or {}
    nombre = (contexto.get("nombre") or "").split(" ")[0]
    return (
        f"{nombre}, estás en {contexto.get('estado_ruana')} con "
        f"{score.get('score')} puntos"
        + (
            f" y te faltan {score.get('puntos_al_siguiente')} para "
            f"{score.get('siguiente_banda')}."
            if score.get("puntos_al_siguiente")
            else "."
        )
    )
