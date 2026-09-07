"""
Servicio único de preparación de actividad para la cinta RUANA.

Agrega notificaciones reales, avisos de grupo, lecturas de actividad de negocio
y métricas agregadas. El panel solo muestra host.actividadCinta.
"""
from __future__ import annotations

import json
import logging
import sqlite3
from datetime import datetime
from typing import Any, Dict, List, Optional, Set, Tuple

from core.db_constants import (
    CP_MADUREZ_MIN_ALIADOS,
    CP_MADUREZ_MIN_ENCARGOS,
    TIPO_GRUPO_MADRE,
)
from core.repositories.actividad_repo import ActividadRepo
from core.repositories.notificacion_repo import NotificacionRepo

MAX_ACTIVIDAD_CINTA = 10

_notif_repo = NotificacionRepo()
_act_repo = ActividadRepo()

_CINTA_TIPOS_EXCLUIDOS = frozenset({
    "apoyo_ruana",
    "pago_aceptado",
    "pago_rechazado",
    "pago_stripe",
    "importe_impugnado",
    "prueba_conflicto_en_revision",
    "ruana_soporte",
    "ruana_soporte_estado",
    # Notificaciones personales de competencia (la cinta usa lecturas de grupo)
    "competencia_inicio",
    "competencia_titular",
    "competencia_victoria",
    "competencia_derrota",
    "competencia_expulsion",
    "competencia_perdida",
})

_PRIORIDAD_ALTA = 90
_PRIORIDAD_MEDIA = 60
_PRIORIDAD_BAJA = 30
_PRIORIDAD_METRICA = 15


def _parse_creado_en(valor: Any) -> float:
    if valor is None or valor == "":
        return 0.0
    if isinstance(valor, (int, float)):
        return float(valor)
    texto = str(valor).strip()
    if not texto:
        return 0.0
    normalizado = texto.replace("Z", "+00:00")
    if " " in normalizado and "T" not in normalizado:
        normalizado = normalizado.replace(" ", "T", 1)
    try:
        return datetime.fromisoformat(normalizado).timestamp()
    except Exception:
        return 0.0


def _metadata_dict(notif: Dict[str, Any]) -> Dict[str, Any]:
    meta = notif.get("metadata")
    if isinstance(meta, dict):
        return meta
    if isinstance(meta, str) and meta.strip():
        try:
            parsed = json.loads(meta)
            return parsed if isinstance(parsed, dict) else {}
        except Exception:
            return {}
    return {}


def _item(
    item_id: str,
    texto: str,
    creado_en: Any,
    tipo: str,
    fuente: str,
    prioridad: int,
    clave: Optional[str] = None,
) -> Dict[str, Any]:
    return {
        "id": item_id,
        "texto": texto,
        "creado_en": creado_en,
        "tipo": tipo,
        "fuente": fuente,
        "prioridad": prioridad,
        "clave": clave or item_id,
    }


def _nombre(valor: Any, fallback: Optional[str] = None) -> Optional[str]:
    texto = str(valor or "").strip()
    if texto:
        return texto
    return fallback


def _nombre_requerido(valor: Any) -> Optional[str]:
    return _nombre(valor, fallback=None)


def _lookup_nombre_aliado(cursor, codigo: Any) -> Optional[str]:
    cod = str(codigo or "").strip()
    if not cod or cursor is None:
        return None
    try:
        cursor.execute(
            "SELECT nombre FROM aliados WHERE TRIM(CAST(codigo AS TEXT)) = ?",
            (cod,),
        )
        row = cursor.fetchone()
        if not row:
            return None
        nombre = row[0] if not hasattr(row, "keys") else row["nombre"]
        return _nombre_requerido(nombre)
    except Exception:
        return None


def _resolver_nombre(
    meta: Dict[str, Any],
    nombre_key: str,
    codigo_key: str,
    cursor=None,
) -> Optional[str]:
    directo = _nombre_requerido(meta.get(nombre_key))
    if directo:
        return directo
    return _lookup_nombre_aliado(cursor, meta.get(codigo_key))


def _importe_eur(valor: Any) -> Optional[str]:
    try:
        num = float(valor)
    except (TypeError, ValueError):
        return None
    if num <= 0:
        return None
    if num == int(num):
        return f"{int(num)}"
    return f"{num:.2f}".rstrip("0").rstrip(".")


def _formatear_notificacion_cinta(
    notif: Dict[str, Any],
    viewer_codigo: str,
    cursor=None,
) -> Optional[Dict[str, Any]]:
    tipo = str(notif.get("tipo") or "").strip()
    if not tipo or tipo in _CINTA_TIPOS_EXCLUIDOS:
        return None

    meta = _metadata_dict(notif)
    notif_id = notif.get("id")
    creado = notif.get("creado_en")
    base_id = f"notif-{notif_id}" if notif_id is not None else f"notif-{tipo}"

    if tipo == "solicitud_semanal_nueva":
        nombre = _resolver_nombre(meta, "solicitante_nombre", "solicitante_codigo", cursor)
        if not nombre:
            return None
        return _item(
            base_id,
            f"Nueva solicitud publicada por {nombre} en el grupo",
            creado,
            tipo,
            "notificacion",
            _PRIORIDAD_ALTA,
            f"sol-sem:{meta.get('solicitud_semanal_id') or notif_id}",
        )

    if tipo == "solicitud_nueva":
        nombre = _resolver_nombre(meta, "solicitante_nombre", "solicitante_codigo", cursor)
        if not nombre:
            return None
        return _item(
            base_id,
            f"{nombre} ha publicado una nueva solicitud",
            creado,
            tipo,
            "notificacion",
            _PRIORIDAD_ALTA,
            f"sol-nueva:{meta.get('solicitud_id') or notif_id}",
        )

    if tipo == "solicitud_actualizada":
        nombre = _resolver_nombre(meta, "solicitante_nombre", "solicitante_codigo", cursor)
        if not nombre:
            return None
        return _item(
            base_id,
            f"{nombre} acaba de actualizar una solicitud",
            creado,
            tipo,
            "notificacion",
            _PRIORIDAD_MEDIA,
            f"sol-upd:{meta.get('solicitud_id') or notif_id}",
        )

    if tipo == "solicitud_asignada":
        return _item(
            base_id,
            "Una solicitud acaba de ser asignada",
            creado,
            tipo,
            "notificacion",
            _PRIORIDAD_ALTA,
            f"sol-asig:{meta.get('solicitud_id') or notif_id}",
        )

    if tipo == "solicitud_semanal_respuesta":
        nombre = _resolver_nombre(meta, "respondiente_nombre", "respondiente_codigo", cursor)
        if not nombre:
            return None
        return _item(
            base_id,
            f"{nombre} ya ha respondido a la solicitud semanal",
            creado,
            tipo,
            "notificacion",
            _PRIORIDAD_MEDIA,
            f"sol-sem-resp:{meta.get('solicitud_id') or notif_id}",
        )

    if tipo == "propuesta":
        proponente = _resolver_nombre(meta, "proponente_nombre", "proponente_codigo", cursor)
        propuesto = _resolver_nombre(meta, "propuesto_nombre", "propuesto_codigo", cursor) or "un profesional"
        if not proponente:
            return None
        return _item(
            base_id,
            f"{proponente} ha propuesto a {propuesto}",
            creado,
            tipo,
            "notificacion",
            _PRIORIDAD_ALTA,
            f"prop:{meta.get('solicitud_id') or notif_id}",
        )

    if tipo == "recomendacion":
        origen = _resolver_nombre(meta, "origen_nombre", "origen_codigo", cursor)
        destino = _resolver_nombre(meta, "destino_nombre", "destino_codigo", cursor)
        if not origen or not destino:
            return None
        return _item(
            base_id,
            f"{origen} acaba de recomendar a {destino}",
            creado,
            tipo,
            "notificacion",
            _PRIORIDAD_ALTA,
            f"rec:{meta.get('contacto_id') or notif_id}",
        )

    if tipo == "recomendacion_oficio":
        origen = _resolver_nombre(meta, "origen_nombre", "origen_codigo", cursor)
        destino = _resolver_nombre(meta, "destino_nombre", "destino_codigo", cursor)
        oficio = _nombre(meta.get("oficio")) or "profesional"
        if not origen or not destino:
            return None
        return _item(
            base_id,
            f"{origen} recomienda a {destino} para {oficio}",
            creado,
            tipo,
            "notificacion",
            _PRIORIDAD_ALTA,
            f"rec-of:{meta.get('contacto_id') or notif_id}",
        )

    if tipo == "recomendacion_encargo":
        return _item(
            base_id,
            "Una recomendación acaba de convertirse en un encargo",
            creado,
            tipo,
            "notificacion",
            95,
            f"rec-enc:{meta.get('contacto_id') or notif_id}",
        )

    if tipo == "acuerdo_cerrado":
        sol = _resolver_nombre(meta, "solicitante_nombre", "solicitante_codigo", cursor)
        pro = _resolver_nombre(meta, "profesional_nombre", "profesional_codigo", cursor)
        if not sol or not pro:
            return None
        importe = _importe_eur(meta.get("importe"))
        viewer = (viewer_codigo or "").strip()
        es_parte = viewer and viewer in {
            str(meta.get("solicitante_codigo") or "").strip(),
            str(meta.get("profesional_codigo") or "").strip(),
        }
        if es_parte and importe:
            texto = f"{sol} y {pro} han alcanzado un acuerdo de {importe} €"
        elif es_parte:
            texto = f"{sol} y {pro} han alcanzado un acuerdo"
        else:
            texto = "Se ha cerrado un acuerdo en tu grupo"
        return _item(
            base_id,
            texto,
            creado,
            tipo,
            "notificacion",
            100,
            f"acuerdo:{meta.get('contacto_id') or notif_id}",
        )

    if tipo == "aliado_nuevo_grupo":
        nombre = _resolver_nombre(meta, "nombre", "codigo", cursor)
        if not nombre:
            return None
        return _item(
            base_id,
            f"{nombre} acaba de entrar al grupo",
            creado,
            tipo,
            "notificacion",
            _PRIORIDAD_MEDIA,
            f"aliado-nuevo:{meta.get('codigo') or notif_id}",
        )

    if tipo == "invitacion":
        invitador = _resolver_nombre(meta, "invitador_nombre", "invitador_codigo", cursor)
        invitado = _resolver_nombre(meta, "invitado_nombre", "invitado_codigo", cursor)
        if not invitador or not invitado:
            return None
        return _item(
            base_id,
            f"{invitador} ha invitado a {invitado} a RUANA",
            creado,
            tipo,
            "notificacion",
            _PRIORIDAD_BAJA,
            f"inv:{meta.get('referido_codigo') or notif_id}",
        )

    if tipo == "invitacion_oficio":
        invitador = _resolver_nombre(meta, "invitador_nombre", "invitador_codigo", cursor)
        oficio = _nombre(meta.get("oficio")) or "profesional"
        if not invitador:
            return None
        return _item(
            base_id,
            f"{invitador} ha generado una invitación para {oficio}",
            creado,
            tipo,
            "notificacion",
            _PRIORIDAD_BAJA,
            f"inv-of:{meta.get('invitacion_codigo') or notif_id}",
        )

    if tipo == "catalogo_actualizado":
        nombre = _resolver_nombre(meta, "nombre", "codigo", cursor)
        if not nombre:
            return None
        return _item(
            base_id,
            f"{nombre} acaba de actualizar sus servicios",
            creado,
            tipo,
            "notificacion",
            _PRIORIDAD_BAJA,
            f"cat:{meta.get('codigo') or notif_id}",
        )

    if tipo == "foto_actualizada":
        nombre = _resolver_nombre(meta, "nombre", "codigo", cursor)
        if not nombre:
            return None
        return _item(
            base_id,
            f"{nombre} acaba de actualizar su foto",
            creado,
            tipo,
            "notificacion",
            _PRIORIDAD_BAJA,
            f"foto:{meta.get('codigo') or notif_id}",
        )

    if tipo == "grupo_nuevo_cp":
        return _item(
            base_id,
            "Nuevo grupo creado en tu código postal",
            creado,
            tipo,
            "notificacion",
            _PRIORIDAD_MEDIA,
            f"grupo-nuevo:{meta.get('grupo_id') or notif_id}",
        )

    if tipo == "plaza_disponible":
        oficio = _nombre(meta.get("oficio")) or "profesional"
        return _item(
            base_id,
            f"Nueva plaza de {oficio} disponible en tu zona",
            creado,
            tipo,
            "notificacion",
            _PRIORIDAD_MEDIA,
            f"plaza:{meta.get('grupo_id')}:{oficio}",
        )

    if tipo == "competencia_cp":
        nombre = _resolver_nombre(meta, "nombre", "codigo", cursor)
        if not nombre:
            return None
        return _item(
            base_id,
            f"{nombre}, aliado de tu CP, ha pasado a competencia",
            creado,
            tipo,
            "notificacion",
            _PRIORIDAD_MEDIA,
            f"comp-cp:{meta.get('codigo') or notif_id}",
        )

    if tipo == "score_change":
        nombre = _resolver_nombre(meta, "nombre", "codigo", cursor)
        if not nombre:
            return None
        sujeto = str(meta.get("codigo") or "").strip()
        if sujeto and sujeto == str(viewer_codigo or "").strip():
            return None
        return _item(
            base_id,
            f"El score de {nombre} acaba de cambiar",
            creado,
            tipo,
            "notificacion",
            _PRIORIDAD_MEDIA,
            f"score:{meta.get('movimiento_id') or notif_id}",
        )

    if tipo == "competencia_inicio":
        return _item(
            base_id,
            "Nueva competencia iniciada en tu grupo",
            creado,
            tipo,
            "notificacion",
            _PRIORIDAD_MEDIA,
            f"comp-ini:{meta.get('competencia_id') or notif_id}",
        )

    if tipo == "competencia_reto":
        retador = _resolver_nombre(meta, "retador_nombre", "retador_codigo", cursor)
        titular = _resolver_nombre(meta, "titular_nombre", "titular_codigo", cursor)
        if not retador or not titular:
            return None
        return _item(
            base_id,
            f"{retador} ha retado a {titular}",
            creado,
            tipo,
            "notificacion",
            _PRIORIDAD_MEDIA,
            f"comp-reto:{meta.get('competencia_id') or notif_id}",
        )

    if tipo == "competencia_victoria":
        ganador = _resolver_nombre(meta, "ganador_nombre", "ganador_codigo", cursor)
        if not ganador:
            return None
        return _item(
            base_id,
            f"{ganador} acaba de ganar una competencia",
            creado,
            tipo,
            "notificacion",
            _PRIORIDAD_MEDIA,
            f"comp-win:{meta.get('competencia_id') or notif_id}",
        )

    if tipo in ("competencia_derrota", "competencia_expulsion", "competencia_perdida"):
        perdedor = _resolver_nombre(meta, "perdedor_nombre", "perdedor_codigo", cursor)
        if not perdedor:
            return None
        return _item(
            base_id,
            f"{perdedor} ha perdido una competencia",
            creado,
            tipo,
            "notificacion",
            _PRIORIDAD_MEDIA,
            f"comp-loss:{meta.get('competencia_id') or notif_id}",
        )

    if tipo == "competencia_titular":
        return _item(
            base_id,
            "Nueva competencia iniciada en tu grupo",
            creado,
            tipo,
            "notificacion",
            _PRIORIDAD_MEDIA,
            f"comp-tit:{meta.get('competencia_id') or notif_id}",
        )

    if tipo == "cp_independizado":
        cp = _nombre(meta.get("codigo_postal")) or "tu zona"
        return _item(
            base_id,
            f"El código postal {cp} ya tiene su propio Grupo RUANA territorial",
            creado,
            tipo,
            "notificacion",
            _PRIORIDAD_ALTA,
            f"cp-indep:{cp}:{notif_id}",
        )

    if tipo == "madurez_encargo_progreso":
        cp = _nombre(meta.get("codigo_postal")) or "tu zona"
        n = int(meta.get("encargos") or 0)
        req = int(meta.get("encargos_requeridos") or CP_MADUREZ_MIN_ENCARGOS)
        return _item(
            base_id,
            f"Tu zona ({cp}) acumula {n} de {req} encargos válidos hacia la independencia",
            creado,
            tipo,
            "notificacion",
            _PRIORIDAD_MEDIA,
            f"mad-enc:{cp}:{n}",
        )

    if tipo == "madurez_aliado_progreso":
        cp = _nombre(meta.get("codigo_postal")) or "tu zona"
        n = int(meta.get("aliados") or 0)
        req = int(meta.get("aliados_requeridos") or CP_MADUREZ_MIN_ALIADOS)
        return _item(
            base_id,
            f"Tu zona ({cp}) suma {n} de {req} aliados activos hacia la independencia",
            creado,
            tipo,
            "notificacion",
            _PRIORIDAD_MEDIA,
            f"mad-ali:{cp}:{n}",
        )

    if tipo == "madurez_listo_independizar":
        cp = _nombre(meta.get("codigo_postal")) or "tu zona"
        return _item(
            base_id,
            f"El código postal {cp} ya cumple los requisitos para independizarse",
            creado,
            tipo,
            "notificacion",
            _PRIORIDAD_ALTA,
            f"mad-listo:{cp}",
        )

    if tipo == "aliado_nuevo_cercano":
        nombre = _resolver_nombre(meta, "nombre", "codigo", cursor)
        if not nombre:
            return None
        oficio = _nombre(meta.get("oficio")) or "profesional"
        cp = _nombre(meta.get("codigo_postal")) or "tu CP"
        return _item(
            base_id,
            f"{nombre} ({oficio}) se ha unido a la red de incubación en {cp}",
            creado,
            tipo,
            "notificacion",
            _PRIORIDAD_MEDIA,
            f"aliado-cercano:{meta.get('codigo') or notif_id}",
        )

    return None


def _formatear_aviso_grupo_cinta(aviso: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    texto = str(aviso.get("texto") or "").strip()
    if not texto:
        return None
    tipo = str(aviso.get("tipo") or "").strip().lower()
    aviso_id = aviso.get("id")
    if tipo == "competencia":
        return _item(
            f"aviso-{aviso_id}" if aviso_id else "aviso-comp",
            "Nueva competencia iniciada en tu grupo",
            aviso.get("creado_en"),
            "competencia_grupo",
            "aviso_grupo",
            _PRIORIDAD_MEDIA,
            f"aviso-comp:{aviso_id}",
        )
    return _item(
        f"aviso-{aviso_id}" if aviso_id else "aviso-gen",
        texto,
        aviso.get("creado_en"),
        tipo or "aviso_grupo",
        "aviso_grupo",
        _PRIORIDAD_MEDIA,
        f"aviso:{aviso_id}:{texto[:40]}",
    )


def _nombre_fila(
    cursor,
    row: Dict[str, Any],
    nombre_key: str,
    codigo_key: Optional[str] = None,
) -> Optional[str]:
    directo = _nombre_requerido(row.get(nombre_key))
    if directo:
        return directo
    if codigo_key:
        return _lookup_nombre_aliado(cursor, row.get(codigo_key))
    return None


def _recolectar_desde_tablas(
    cursor,
    viewer_codigo: str,
    grupo_id: Optional[int],
    codigo_postal: str,
    contexto: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, Any]]:
    items: List[Dict[str, Any]] = []
    if not grupo_id:
        return items

    grupo_tipo = str((contexto or {}).get("grupo_tipo") or "").strip()
    viewer_cp = str(codigo_postal or "").strip()

    cols_sol = _act_repo.columnas_tabla(cursor, "solicitudes")
    has_asignada = "asignada_a_codigo" in cols_sol
    has_candidato = "candidato_por_codigo" in cols_sol

    for row in _act_repo.listar_solicitudes_nuevas_grupo(cursor, grupo_id, viewer_codigo):
        if str(row.get("solicitante_codigo") or "").strip() == viewer_codigo:
            continue
        nombre = _nombre_fila(cursor, row, "solicitante_nombre", "solicitante_codigo")
        if not nombre:
            continue
        sid = row.get("id")
        items.append(
            _item(
                f"sol-nueva-{sid}",
                f"{nombre} ha publicado una nueva solicitud",
                row.get("creado_en"),
                "solicitud_nueva",
                "solicitud",
                _PRIORIDAD_ALTA,
                f"sol-nueva:{sid}",
            )
        )

    for row in _act_repo.listar_solicitudes_atendidas_grupo(cursor, grupo_id):
        nombre = _nombre_fila(cursor, row, "atendido_por_nombre", "atendido_por_codigo")
        if not nombre:
            continue
        sid = row.get("id")
        items.append(
            _item(
                f"sol-resp-{sid}",
                f"{nombre} ya ha respondido a la solicitud semanal",
                row.get("creado_en"),
                "solicitud_semanal_respuesta",
                "solicitud",
                _PRIORIDAD_MEDIA,
                f"sol-resp:{sid}",
            )
        )

    if has_asignada:
        for row in _act_repo.listar_solicitudes_asignadas_grupo(cursor, grupo_id):
            sid = row.get("id")
            items.append(
                _item(
                    f"sol-asig-{sid}",
                    "Una solicitud acaba de ser asignada",
                    row.get("creado_en"),
                    "solicitud_asignada",
                    "solicitud",
                    _PRIORIDAD_ALTA,
                    f"sol-asig:{sid}",
                )
            )

    if has_candidato:
        for row in _act_repo.listar_propuestas_grupo(cursor, grupo_id):
            proponente = _nombre_fila(cursor, row, "solicitante_nombre", "solicitante_codigo")
            propuesto = (
                _nombre_fila(cursor, row, "candidato_por_nombre", "candidato_por_codigo")
                or "un profesional"
            )
            if not proponente:
                continue
            sid = row.get("id")
            items.append(
                _item(
                    f"prop-{sid}",
                    f"{proponente} ha propuesto a {propuesto}",
                    row.get("creado_en"),
                    "propuesta",
                    "solicitud",
                    _PRIORIDAD_ALTA,
                    f"prop:{sid}",
                )
            )

    for row in _act_repo.listar_contactos_nuevos_grupo(cursor, grupo_id):
        cid = row.get("id")
        origen = _nombre_fila(cursor, row, "solicitante_nombre", "solicitante_codigo")
        destino = _nombre_fila(cursor, row, "profesional_nombre", "profesional_codigo")
        if not origen or not destino:
            continue
        oficio = str(row.get("servicio") or "").strip()
        if oficio:
            texto = f"{origen} recomienda a {destino} para {oficio}"
            tipo = "recomendacion_oficio"
            clave = f"rec-of:{cid}"
        else:
            texto = f"{origen} acaba de recomendar a {destino}"
            tipo = "recomendacion"
            clave = f"rec:{cid}"
        items.append(
            _item(
                f"contacto-{cid}",
                texto,
                row.get("creado_en"),
                tipo,
                "contacto",
                _PRIORIDAD_ALTA,
                clave,
            )
        )

    for row in _act_repo.listar_acuerdos_grupo(cursor, grupo_id):
        cid = row.get("id")
        sol = _nombre_fila(cursor, row, "solicitante_nombre", "solicitante_codigo")
        pro = _nombre_fila(cursor, row, "profesional_nombre", "profesional_codigo")
        if not sol or not pro:
            continue
        viewer = viewer_codigo.strip()
        es_parte = viewer in {
            str(row.get("solicitante_codigo") or "").strip(),
            str(row.get("profesional_codigo") or "").strip(),
        }
        importe = _importe_eur(row.get("importe_acordado"))
        if es_parte and importe:
            texto = f"{sol} y {pro} han alcanzado un acuerdo de {importe} €"
        elif es_parte:
            texto = f"{sol} y {pro} han alcanzado un acuerdo"
        else:
            texto = "Se ha cerrado un acuerdo en tu grupo"
        items.append(
            _item(
                f"acuerdo-{cid}",
                texto,
                row.get("creado_en"),
                "acuerdo_cerrado",
                "contacto",
                100,
                f"acuerdo:{cid}",
            )
        )

    for row in _act_repo.listar_encargos_cerrados_grupo(cursor, grupo_id):
        cid = row.get("id")
        items.append(
            _item(
                f"encargo-{cid}",
                "Una recomendación acaba de convertirse en un encargo",
                row.get("creado_en"),
                "recomendacion_encargo",
                "contacto",
                95,
                f"rec-enc:{cid}",
            )
        )

    for row in _act_repo.listar_aliados_nuevos_grupo(cursor, grupo_id, viewer_codigo):
        cod = row.get("codigo")
        nombre = _nombre_fila(cursor, row, "nombre", "codigo")
        if not nombre:
            continue
        aliado_cp = str(row.get("codigo_postal") or "").strip()
        oficio = str(row.get("oficio") or "").strip() or "profesional"
        if grupo_tipo == TIPO_GRUPO_MADRE and aliado_cp and viewer_cp and aliado_cp == viewer_cp:
            items.append(
                _item(
                    f"aliado-cercano-{cod}",
                    f"{nombre} ({oficio}) se ha unido a la red de incubación en {aliado_cp}",
                    row.get("creado_en"),
                    "aliado_nuevo_cercano",
                    "aliado",
                    _PRIORIDAD_MEDIA,
                    f"aliado-cercano:{cod}",
                )
            )
        else:
            items.append(
                _item(
                    f"aliado-{cod}",
                    f"{nombre} acaba de entrar al grupo",
                    row.get("creado_en"),
                    "aliado_nuevo_grupo",
                    "aliado",
                    _PRIORIDAD_MEDIA,
                    f"aliado-nuevo:{cod}",
                )
            )

    for row in _act_repo.listar_referidos_recientes_grupo(cursor, grupo_id):
        invitador = _nombre_requerido(row.get("invitador_nombre"))
        referido = _nombre_requerido(row.get("referido_nombre"))
        if not invitador or not referido:
            continue
        oficio = str(row.get("referido_oficio") or "").strip()
        creado = row.get("creado_en")
        items.append(
            _item(
                f"ref-{invitador}-{referido}",
                f"{invitador} ha invitado a {referido} a RUANA",
                creado,
                "invitacion",
                "referido",
                _PRIORIDAD_BAJA,
                f"inv:{referido}",
            )
        )
        if oficio:
            items.append(
                _item(
                    f"inv-of-{invitador}-{oficio}",
                    f"{invitador} ha generado una invitación para {oficio}",
                    creado,
                    "invitacion_oficio",
                    "referido",
                    _PRIORIDAD_BAJA,
                    f"inv-of:{referido}:{oficio}",
                )
            )

    for row in _act_repo.listar_catalogo_actualizado_grupo(cursor, grupo_id, viewer_codigo):
        cod = row.get("aliado_codigo")
        nombre = _nombre_fila(cursor, row, "nombre", "aliado_codigo")
        if not nombre:
            continue
        items.append(
            _item(
                f"cat-{cod}",
                f"{nombre} acaba de actualizar sus servicios",
                row.get("creado_en"),
                "catalogo_actualizado",
                "catalogo",
                _PRIORIDAD_BAJA,
                f"cat:{cod}",
            )
        )

    cols_aliados = _act_repo.columnas_tabla(cursor, "aliados")
    if "foto_perfil_url" in cols_aliados:
        for row in _act_repo.listar_foto_actualizada_grupo(cursor, grupo_id, viewer_codigo):
            cod = row.get("codigo")
            nombre = _nombre_fila(cursor, row, "nombre", "codigo")
            if not nombre:
                continue
            items.append(
                _item(
                    f"foto-{cod}",
                    f"{nombre} acaba de actualizar su foto",
                    row.get("creado_en"),
                    "foto_actualizada",
                    "aliado",
                    _PRIORIDAD_BAJA,
                    f"foto:{cod}",
                )
            )

    if codigo_postal:
        for row in _act_repo.listar_grupos_nuevos_cp(cursor, codigo_postal):
            gid = row.get("id")
            if int(gid or 0) == int(grupo_id):
                continue
            items.append(
                _item(
                    f"grupo-cp-{gid}",
                    "Nuevo grupo creado en tu código postal",
                    row.get("creado_en"),
                    "grupo_nuevo_cp",
                    "grupo",
                    _PRIORIDAD_MEDIA,
                    f"grupo-nuevo:{gid}",
                )
            )

        for row in _act_repo.listar_aliados_competencia_cp(cursor, codigo_postal):
            cod = row.get("codigo")
            if str(cod or "").strip() == viewer_codigo:
                continue
            nombre = _nombre_fila(cursor, row, "nombre", "codigo")
            if not nombre:
                continue
            items.append(
                _item(
                    f"comp-cp-{cod}",
                    f"{nombre}, aliado de tu CP, ha pasado a competencia",
                    row.get("creado_en"),
                    "competencia_cp",
                    "competencia",
                    _PRIORIDAD_MEDIA,
                    f"comp-cp:{cod}",
                )
            )

        for row in _act_repo.listar_plazas_disponibles_cp(cursor, codigo_postal):
            oficio = _nombre(row.get("oficio")) or "profesional"
            gid = row.get("grupo_id")
            items.append(
                _item(
                    f"plaza-{gid}-{oficio}",
                    f"Nueva plaza de {oficio} disponible en tu zona",
                    row.get("creado_en"),
                    "plaza_disponible",
                    "grupo",
                    _PRIORIDAD_MEDIA,
                    f"plaza:{gid}:{oficio}",
                )
            )

    for row in _act_repo.listar_competencias_grupo(cursor, grupo_id):
        cid = row.get("id")
        creado = row.get("creado_en")
        retador = _nombre_fila(cursor, row, "retador_nombre", "retador_codigo")
        titular = _nombre_fila(cursor, row, "titular_nombre", "aliado_original_codigo")
        if not retador or not titular:
            continue
        estado = str(row.get("estado") or "").strip().lower()
        items.append(
            _item(
                f"comp-ini-{cid}",
                "Nueva competencia iniciada en tu grupo",
                creado,
                "competencia_inicio",
                "competencia",
                _PRIORIDAD_MEDIA,
                f"comp-ini:{cid}",
            )
        )
        items.append(
            _item(
                f"comp-reto-{cid}",
                f"{retador} ha retado a {titular}",
                creado,
                "competencia_reto",
                "competencia",
                _PRIORIDAD_MEDIA,
                f"comp-reto:{cid}",
            )
        )
        if estado == "finalizada" and row.get("ganador_codigo"):
            ganador = _nombre_fila(cursor, row, "ganador_nombre", "ganador_codigo")
            if not ganador:
                continue
            items.append(
                _item(
                    f"comp-win-{cid}",
                    f"{ganador} acaba de ganar una competencia",
                    creado,
                    "competencia_victoria",
                    "competencia",
                    _PRIORIDAD_MEDIA,
                    f"comp-win:{cid}",
                )
            )
            perdedor_cod = (
                row.get("aliado_original_codigo")
                if str(row.get("ganador_codigo")) == str(row.get("retador_codigo"))
                else row.get("retador_codigo")
            )
            if str(perdedor_cod) == str(row.get("aliado_original_codigo")):
                perdedor = titular
            else:
                perdedor = retador
            if not perdedor:
                continue
            items.append(
                _item(
                    f"comp-loss-{cid}",
                    f"{perdedor} ha perdido una competencia",
                    creado,
                    "competencia_perdida",
                    "competencia",
                    _PRIORIDAD_MEDIA,
                    f"comp-loss:{cid}",
                )
            )

    for row in _act_repo.listar_score_cambios_grupo(cursor, grupo_id, viewer_codigo):
        sid = row.get("id")
        nombre = _nombre_fila(cursor, row, "nombre", "codigo_aliado")
        if not nombre:
            continue
        items.append(
            _item(
                f"score-{sid}",
                f"El score de {nombre} acaba de cambiar",
                row.get("creado_en"),
                "score_change",
                "score",
                _PRIORIDAD_MEDIA,
                f"score:{sid}",
            )
        )

    return items


def _recolectar_metricas_madre(
    cursor,
    grupo_id: Optional[int],
    codigo_postal: str,
    contexto: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, Any]]:
    if str((contexto or {}).get("grupo_tipo") or "") != TIPO_GRUPO_MADRE:
        return []
    cp = str(codigo_postal or "").strip()
    if not cp or not grupo_id:
        return []

    ahora = datetime.utcnow().isoformat(sep=" ", timespec="seconds")
    items: List[Dict[str, Any]] = []
    ciudad = str((contexto or {}).get("ciudad") or "").strip()

    estado = _act_repo.select_cp_estado(cursor, cp)
    if estado:
        n_a = int(estado.get("aliados_activos") or 0)
        n_e = int(estado.get("encargos_validos") or 0)
        if n_a > 0:
            items.append(
                _item(
                    f"metric-mad-aliados-{cp}",
                    (
                        f"Tu zona ({cp}) suma {n_a} de {CP_MADUREZ_MIN_ALIADOS} "
                        "aliados activos hacia la independencia territorial"
                    ),
                    ahora,
                    "metrica_madurez_aliados",
                    "metrica",
                    _PRIORIDAD_METRICA,
                    f"metric-mad-ali:{cp}",
                )
            )
        if n_e > 0:
            items.append(
                _item(
                    f"metric-mad-encargos-{cp}",
                    (
                        f"Tu zona ({cp}) acumula {n_e} de {CP_MADUREZ_MIN_ENCARGOS} "
                        "encargos válidos hacia la independencia territorial"
                    ),
                    ahora,
                    "metrica_madurez_encargos",
                    "metrica",
                    _PRIORIDAD_METRICA,
                    f"metric-mad-enc:{cp}",
                )
            )
        if estado.get("listo_independizar"):
            items.append(
                _item(
                    f"metric-mad-listo-{cp}",
                    f"El código postal {cp} ya cumple los requisitos para independizarse",
                    ahora,
                    "metrica_madurez_listo",
                    "metrica",
                    _PRIORIDAD_METRICA + 5,
                    f"metric-mad-listo:{cp}",
                )
            )

    n_ciudad = _act_repo.contar_aliados_activos_grupo(cursor, grupo_id)
    if n_ciudad > 0:
        etiqueta = ciudad or "tu ciudad"
        items.append(
            _item(
                "metric-mad-ciudad",
                f"La red de incubación de {etiqueta} suma {n_ciudad} profesionales activos",
                ahora,
                "metrica_incubacion_ciudad",
                "metrica",
                _PRIORIDAD_METRICA,
                "metric-mad-ciudad",
            )
        )

    anio_mes = datetime.utcnow().strftime("%Y-%m")
    n_nuevos_cp = _act_repo.contar_nuevos_aliados_mes_cp(cursor, cp, anio_mes)
    if n_nuevos_cp > 0:
        items.append(
            _item(
                f"metric-mad-nuevos-{anio_mes}",
                f"Este mes se han incorporado {n_nuevos_cp} profesionales a tu código postal",
                ahora,
                "metrica_nuevos_cp_madre",
                "metrica",
                _PRIORIDAD_METRICA,
                f"metric-mad-nuevos:{anio_mes}",
            )
        )

    return items


def _recolectar_metricas(
    cursor,
    grupo_id: Optional[int],
    codigo_postal: str,
    contexto: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, Any]]:
    cp = str(codigo_postal or "").strip()
    if not cp and not grupo_id:
        return []
    anio_mes = datetime.utcnow().strftime("%Y-%m")
    ahora = datetime.utcnow().isoformat(sep=" ", timespec="seconds")
    items: List[Dict[str, Any]] = []

    if cp:
        n_cp = _act_repo.contar_encargos_mes_cp(cursor, cp, anio_mes)
        n_grupo = (
            _act_repo.contar_encargos_mes_grupo(cursor, grupo_id, anio_mes)
            if grupo_id
            else 0
        )
        if n_cp > 0:
            items.append(
                _item(
                    f"metric-encargos-{anio_mes}",
                    f"RUANA ya ha gestionado {n_cp} encargos este mes · {n_grupo} en tu grupo",
                    ahora,
                    "metrica_encargos",
                    "metrica",
                    _PRIORIDAD_METRICA,
                    f"metric-enc:{anio_mes}",
                )
            )

        n_aliados = _act_repo.contar_aliados_activos_cp(cursor, cp)
        if n_aliados > 0:
            items.append(
                _item(
                    f"metric-aliados-cp",
                    f"Ya sois {n_aliados} aliados activos en tu código postal",
                    ahora,
                    "metrica_aliados_cp",
                    "metrica",
                    _PRIORIDAD_METRICA,
                    "metric-aliados-cp",
                )
            )

    if grupo_id:
        n_rec = _act_repo.contar_recomendaciones_contacto_mes_grupo(
            cursor, grupo_id, anio_mes
        )
        if n_rec > 0:
            items.append(
                _item(
                    f"metric-rec-{anio_mes}",
                    f"{n_rec} recomendaciones ya se han convertido en contactos reales este mes",
                    ahora,
                    "metrica_recomendaciones",
                    "metrica",
                    _PRIORIDAD_METRICA,
                    f"metric-rec:{anio_mes}",
                )
            )

        n_sol = _act_repo.contar_solicitudes_atendidas_mes_grupo(
            cursor, grupo_id, anio_mes
        )
        if n_sol > 0:
            items.append(
                _item(
                    f"metric-sol-{anio_mes}",
                    f"Tu grupo ya ha atendido {n_sol} solicitudes este mes",
                    ahora,
                    "metrica_solicitudes",
                    "metrica",
                    _PRIORIDAD_METRICA,
                    f"metric-sol:{anio_mes}",
                )
            )

        n_neg = _act_repo.contar_negociaciones_iniciadas_semana_grupo(cursor, grupo_id)
        if n_neg > 0:
            items.append(
                _item(
                    "metric-neg-semana",
                    f"Esta semana ya se han iniciado {n_neg} negociaciones en tu grupo",
                    ahora,
                    "metrica_negociaciones",
                    "metrica",
                    _PRIORIDAD_METRICA,
                    "metric-neg-semana",
                )
            )

        n_grupo_aliados = _act_repo.contar_aliados_activos_grupo(cursor, grupo_id)
        if n_grupo_aliados > 0:
            tiene_metrica_cp = any(
                it.get("tipo") == "metrica_aliados_cp" for it in items
            )
            if not tiene_metrica_cp:
                items.append(
                    _item(
                        "metric-aliados-grupo",
                        f"Tu grupo cuenta con {n_grupo_aliados} aliados activos",
                        ahora,
                        "metrica_aliados_grupo",
                        "metrica",
                        _PRIORIDAD_METRICA,
                        "metric-aliados-grupo",
                    )
                )

    if cp:
        n_nuevos_cp = _act_repo.contar_nuevos_aliados_mes_cp(cursor, cp, anio_mes)
        n_nuevos_total = _act_repo.contar_nuevos_aliados_mes_total(cursor, anio_mes)
        if n_nuevos_total > 0:
            items.append(
                _item(
                    f"metric-nuevos-{anio_mes}",
                    f"RUANA suma {n_nuevos_total} nuevos aliados este mes · {n_nuevos_cp} en tu CP",
                    ahora,
                    "metrica_nuevos_aliados",
                    "metrica",
                    _PRIORIDAD_METRICA,
                    f"metric-nuevos:{anio_mes}",
                )
            )

        top = _act_repo.ranking_actividad_grupos_cp(cursor, cp, grupo_id)
        if top:
            items.append(
                _item(
                    "metric-top-grupo",
                    "Tu grupo está entre los más activos de tu CP este mes",
                    ahora,
                    "metrica_grupo_activo",
                    "metrica",
                    _PRIORIDAD_METRICA,
                    "metric-top-grupo",
                )
            )

    try:
        items.extend(_recolectar_metricas_madre(cursor, grupo_id, cp, contexto))
    except Exception:
        logging.getLogger(__name__).exception(
            "Error métricas incubación actividad cinta"
        )

    return items


def _seleccionar_items(
    items: List[Dict[str, Any]], limite: int
) -> List[Dict[str, Any]]:
    if not items:
        return []

    ordenados = sorted(
        items,
        key=lambda it: (
            -_parse_creado_en(it.get("creado_en")),
            -int(it.get("prioridad") or 0),
        ),
    )

    vistos: Set[str] = set()
    unicos: List[Dict[str, Any]] = []
    for it in ordenados:
        clave = str(it.get("clave") or it.get("id") or it.get("texto") or "")
        if not clave or clave in vistos:
            continue
        vistos.add(clave)
        salida = {k: v for k, v in it.items() if k != "clave" and k != "prioridad"}
        unicos.append(salida)
        if len(unicos) >= limite:
            break
    return unicos


def _listar_notificaciones_cursor(
    cursor, codigo: str, limite: int = 50
) -> List[Dict[str, Any]]:
    codigo_norm = str(codigo or "").strip()
    if not codigo_norm:
        return []
    try:
        rows = _notif_repo.listar_por_aliado(
            cursor, codigo_norm, max(1, min(limite, 200))
        )
        out = []
        for item in rows:
            row = dict(item) if hasattr(item, "keys") else item
            if isinstance(row, dict) and row.get("metadata"):
                try:
                    row["metadata"] = json.loads(row["metadata"])
                except Exception:
                    pass
            out.append(row)
        return out
    except Exception:
        return []


def _listar_notificaciones(db, codigo: str, limite: int = 50) -> List[Dict[str, Any]]:
    codigo_norm = str(codigo or "").strip()
    if not codigo_norm:
        return []
    with db._lock:
        try:
            conn = db._connect()
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            rows = _notif_repo.listar_por_aliado(cursor, codigo_norm, max(1, min(limite, 200)))
            out = []
            for item in rows:
                if item.get("metadata"):
                    try:
                        item["metadata"] = json.loads(item["metadata"])
                    except Exception:
                        pass
                out.append(item)
            return out
        except Exception:
            return []
        finally:
            conn.close()


def preparar_actividad_cinta(
    db,
    aliado_codigo: str,
    avisos_grupo: Optional[List[Dict[str, Any]]] = None,
    limite: int = MAX_ACTIVIDAD_CINTA,
    _contexto: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, Any]]:
    """Fuente única de actividad para la cinta (máx. 10, más reciente primero)."""
    codigo_norm = str(aliado_codigo or "").strip()
    if not codigo_norm:
        return []

    limite_final = max(0, min(int(limite or MAX_ACTIVIDAD_CINTA), MAX_ACTIVIDAD_CINTA))
    if limite_final == 0:
        return []

    items: List[Dict[str, Any]] = []

    ctx = _contexto
    with db._lock:
        conn = None
        try:
            conn = db._connect()
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            if ctx is None:
                ctx = _act_repo.contexto_aliado(cursor, codigo_norm) or {}

            for notif in _listar_notificaciones_cursor(cursor, codigo_norm, limite=50):
                formateada = _formatear_notificacion_cinta(
                    notif, codigo_norm, cursor=cursor
                )
                if formateada:
                    items.append(formateada)

            for aviso in avisos_grupo or []:
                formateada = _formatear_aviso_grupo_cinta(aviso)
                if formateada:
                    items.append(formateada)

            grupo_id = ctx.get("grupo_id")
            cp = str(ctx.get("codigo_postal") or "").strip()

            try:
                items.extend(_recolectar_metricas(cursor, grupo_id, cp, ctx))
            except Exception:
                logging.getLogger(__name__).exception(
                    "Error métricas actividad cinta para %s", codigo_norm
                )

            try:
                items.extend(
                    _recolectar_desde_tablas(cursor, codigo_norm, grupo_id, cp, ctx)
                )
            except Exception:
                logging.getLogger(__name__).exception(
                    "Error tablas actividad cinta para %s", codigo_norm
                )
        except Exception:
            logging.getLogger(__name__).exception(
                "Error preparando actividad cinta para %s", codigo_norm
            )
        finally:
            if conn:
                conn.close()

    return _seleccionar_items(items, limite_final)


def preparar_actividad_cinta_para_aliado(
    db,
    aliado_codigo: str,
    limite: int = MAX_ACTIVIDAD_CINTA,
) -> List[Dict[str, Any]]:
    codigo_norm = str(aliado_codigo or "").strip()
    if not codigo_norm:
        return []

    avisos_grupo: List[Dict[str, Any]] = []
    ctx: Optional[Dict[str, Any]] = None
    with db._lock:
        conn = None
        try:
            conn = db._connect()
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            ctx = _act_repo.contexto_aliado(cursor, codigo_norm)
            if ctx and ctx.get("grupo_id"):
                avisos_grupo = db.obtener_avisos_grupo(ctx["grupo_id"])
        except Exception:
            avisos_grupo = []
        finally:
            if conn:
                conn.close()

    return preparar_actividad_cinta(
        db,
        codigo_norm,
        avisos_grupo=avisos_grupo,
        limite=limite,
        _contexto=ctx,
    )


def notificar_grupo_actividad(
    db,
    grupo_id: int,
    tipo: str,
    titulo: str,
    mensaje: str,
    metadata: Optional[Dict[str, Any]] = None,
    excluir_codigo: Optional[str] = None,
    cursor=None,
) -> None:
    """Emite notificación de actividad de grupo a todos los aliados activos del grupo."""
    if not grupo_id:
        return
    meta = dict(metadata or {})
    meta["grupo_id"] = int(grupo_id)
    excluir = (excluir_codigo or "").strip()

    def _fan_out(cur) -> None:
        cur.execute(
            """
            SELECT codigo FROM aliados
            WHERE grupo_id = ? AND estado = 'activo'
            """,
            (int(grupo_id),),
        )
        for row in cur.fetchall():
            codigo = str(row[0] if not hasattr(row, "keys") else row["codigo"]).strip()
            if not codigo or codigo == excluir:
                continue
            _notif_repo.insertar(
                cur,
                codigo,
                tipo,
                titulo,
                mensaje,
                json.dumps(meta, ensure_ascii=False),
            )

    if cursor is not None:
        _fan_out(cursor)
        return

    with db._lock:
        conn = None
        try:
            conn = db._connect()
            cur = conn.cursor()
            _fan_out(cur)
            conn.commit()
        except Exception:
            pass
        finally:
            if conn:
                conn.close()


def _notificar_aliados_cp_madre(
    cursor,
    grupo_id: int,
    codigo_postal: str,
    tipo: str,
    titulo: str,
    mensaje: str,
    metadata: Optional[Dict[str, Any]] = None,
    excluir_codigo: str = "",
) -> None:
    """Notifica a aliados activos del mismo CP dentro del grupo madre."""
    meta = dict(metadata or {})
    meta.setdefault("codigo_postal", codigo_postal)
    meta_json = json.dumps(meta, ensure_ascii=False)
    for codigo in _act_repo.listar_codigos_activos_cp_en_grupo(
        cursor, grupo_id, codigo_postal, excluir_codigo
    ):
        _notif_repo.insertar(cursor, codigo, tipo, titulo, mensaje, meta_json)


def emitir_hitos_madurez_cp(
    db,
    codigo_postal: str,
    grupo_madre_id: int,
    prev_aliados: int,
    prev_encargos: int,
    prev_listo: bool,
    n_aliados: int,
    n_encargos: int,
    listo: bool,
    cursor=None,
) -> None:
    """Emite notificaciones de hitos de madurez a aliados del CP en incubación."""
    cp = (codigo_postal or "").strip()
    if not cp or not grupo_madre_id:
        return

    def _emitir(cur) -> None:
        if n_encargos > prev_encargos:
            _notificar_aliados_cp_madre(
                cur,
                int(grupo_madre_id),
                cp,
                "madurez_encargo_progreso",
                "Progreso de madurez",
                (
                    f"Tu zona ({cp}) acumula {n_encargos} de {CP_MADUREZ_MIN_ENCARGOS} "
                    "encargos válidos hacia la independencia"
                ),
                metadata={
                    "codigo_postal": cp,
                    "encargos": n_encargos,
                    "encargos_requeridos": CP_MADUREZ_MIN_ENCARGOS,
                },
            )
        if n_aliados > prev_aliados:
            _notificar_aliados_cp_madre(
                cur,
                int(grupo_madre_id),
                cp,
                "madurez_aliado_progreso",
                "Progreso de madurez",
                (
                    f"Tu zona ({cp}) suma {n_aliados} de {CP_MADUREZ_MIN_ALIADOS} "
                    "aliados activos hacia la independencia"
                ),
                metadata={
                    "codigo_postal": cp,
                    "aliados": n_aliados,
                    "aliados_requeridos": CP_MADUREZ_MIN_ALIADOS,
                },
            )
        if listo and not prev_listo:
            _notificar_aliados_cp_madre(
                cur,
                int(grupo_madre_id),
                cp,
                "madurez_listo_independizar",
                "Zona lista para independizarse",
                f"El código postal {cp} ya cumple los requisitos para independizarse",
                metadata={"codigo_postal": cp},
            )

    if cursor is not None:
        _emitir(cursor)
        return

    with db._lock:
        conn = None
        try:
            conn = db._connect()
            cur = conn.cursor()
            _emitir(cur)
            conn.commit()
        except Exception:
            pass
        finally:
            if conn:
                conn.close()


def notificar_aliado_nuevo_en_madre(
    db,
    grupo_madre_id: int,
    codigo_postal: str,
    codigo_nuevo: str,
    nombre: str,
    oficio: str = "",
    cursor=None,
) -> None:
    """Notifica a aliados del mismo CP que un profesional se ha unido a la incubación."""
    cp = (codigo_postal or "").strip()
    cod = (codigo_nuevo or "").strip()
    if not cp or not cod or not grupo_madre_id:
        return
    nombre_n = (nombre or "").strip()
    if not nombre_n:
        return
    oficio_n = (oficio or "").strip() or "profesional"

    meta = {
        "codigo": cod,
        "nombre": nombre_n,
        "oficio": oficio_n,
        "codigo_postal": cp,
        "grupo_id": int(grupo_madre_id),
    }
    titulo = "Nuevo profesional en tu zona"
    mensaje = f"{nombre_n} ({oficio_n}) se ha unido a la red de incubación en {cp}"

    if cursor is not None:
        _notificar_aliados_cp_madre(
            cursor,
            int(grupo_madre_id),
            cp,
            "aliado_nuevo_cercano",
            titulo,
            mensaje,
            metadata=meta,
            excluir_codigo=cod,
        )
        return

    with db._lock:
        conn = None
        try:
            conn = db._connect()
            cur = conn.cursor()
            _notificar_aliados_cp_madre(
                cur,
                int(grupo_madre_id),
                cp,
                "aliado_nuevo_cercano",
                titulo,
                mensaje,
                metadata=meta,
                excluir_codigo=cod,
            )
            conn.commit()
        except Exception:
            pass
        finally:
            if conn:
                conn.close()
