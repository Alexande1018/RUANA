"""
Servicio único de preparación de actividad para la cinta RUANA.

Agrega notificaciones reales, avisos de grupo, lecturas de actividad de negocio
y métricas agregadas. El panel solo muestra host.actividadCinta.
"""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from typing import Any, Dict, List, Optional, Set, Tuple

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


def _nombre(valor: Any, fallback: str = "Un aliado") -> str:
    texto = str(valor or "").strip()
    return texto if texto else fallback


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


def _formatear_notificacion_cinta(notif: Dict[str, Any], viewer_codigo: str) -> Optional[Dict[str, Any]]:
    tipo = str(notif.get("tipo") or "").strip()
    if not tipo or tipo in _CINTA_TIPOS_EXCLUIDOS:
        return None

    meta = _metadata_dict(notif)
    notif_id = notif.get("id")
    creado = notif.get("creado_en")
    base_id = f"notif-{notif_id}" if notif_id is not None else f"notif-{tipo}"

    if tipo == "solicitud_semanal_nueva":
        nombre = _nombre(meta.get("solicitante_nombre"))
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
        nombre = _nombre(meta.get("solicitante_nombre"))
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
        nombre = _nombre(meta.get("solicitante_nombre"))
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
        nombre = _nombre(meta.get("respondiente_nombre"))
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
        proponente = _nombre(meta.get("proponente_nombre"))
        propuesto = _nombre(meta.get("propuesto_nombre"), "un profesional")
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
        origen = _nombre(meta.get("origen_nombre"))
        destino = _nombre(meta.get("destino_nombre"))
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
        origen = _nombre(meta.get("origen_nombre"))
        destino = _nombre(meta.get("destino_nombre"))
        oficio = _nombre(meta.get("oficio"), "profesional")
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
        sol = _nombre(meta.get("solicitante_nombre"))
        pro = _nombre(meta.get("profesional_nombre"))
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
        nombre = _nombre(meta.get("nombre"))
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
        invitador = _nombre(meta.get("invitador_nombre"))
        invitado = _nombre(meta.get("invitado_nombre"))
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
        invitador = _nombre(meta.get("invitador_nombre"))
        oficio = _nombre(meta.get("oficio"), "profesional")
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
        nombre = _nombre(meta.get("nombre"))
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
        nombre = _nombre(meta.get("nombre"))
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
        oficio = _nombre(meta.get("oficio"), "profesional")
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
        nombre = _nombre(meta.get("nombre"))
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
        nombre = _nombre(meta.get("nombre"))
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
        retador = _nombre(meta.get("retador_nombre"))
        titular = _nombre(meta.get("titular_nombre"))
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
        retador = _nombre(meta.get("retador_nombre"))
        titular = _nombre(meta.get("titular_nombre"))
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
        ganador = _nombre(meta.get("ganador_nombre"))
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
        perdedor = _nombre(meta.get("perdedor_nombre"))
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


def _recolectar_desde_tablas(
    cursor,
    viewer_codigo: str,
    grupo_id: Optional[int],
    codigo_postal: str,
) -> List[Dict[str, Any]]:
    items: List[Dict[str, Any]] = []
    if not grupo_id:
        return items

    cols_sol = _act_repo.columnas_tabla(cursor, "solicitudes")
    has_asignada = "asignada_a_codigo" in cols_sol
    has_candidato = "candidato_por_codigo" in cols_sol

    for row in _act_repo.listar_solicitudes_nuevas_grupo(cursor, grupo_id, viewer_codigo):
        if str(row.get("solicitante_codigo") or "").strip() == viewer_codigo:
            continue
        nombre = _nombre(row.get("solicitante_nombre"))
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
        nombre = _nombre(row.get("atendido_por_nombre"))
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
            proponente = _nombre(row.get("solicitante_nombre"))
            propuesto = _nombre(row.get("candidato_por_nombre"), "un profesional")
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
        origen = _nombre(row.get("solicitante_nombre"))
        destino = _nombre(row.get("profesional_nombre"))
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
        sol = _nombre(row.get("solicitante_nombre"))
        pro = _nombre(row.get("profesional_nombre"))
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
        nombre = _nombre(row.get("nombre"))
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
        invitador = _nombre(row.get("invitador_nombre"))
        referido = _nombre(row.get("referido_nombre"))
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
        nombre = _nombre(row.get("nombre"))
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
            nombre = _nombre(row.get("nombre"))
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
            nombre = _nombre(row.get("nombre"))
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
            oficio = _nombre(row.get("oficio"), "profesional")
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
        retador = _nombre(row.get("retador_nombre"))
        titular = _nombre(row.get("titular_nombre"))
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
            ganador = _nombre(row.get("ganador_nombre"))
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
        nombre = _nombre(row.get("nombre"))
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


def _recolectar_metricas(
    cursor,
    grupo_id: Optional[int],
    codigo_postal: str,
) -> List[Dict[str, Any]]:
    if not codigo_postal:
        return []
    anio_mes = datetime.utcnow().strftime("%Y-%m")
    ahora = datetime.utcnow().isoformat(sep=" ", timespec="seconds")
    items: List[Dict[str, Any]] = []

    n_cp = _act_repo.contar_encargos_mes_cp(cursor, codigo_postal, anio_mes)
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

    n_aliados = _act_repo.contar_aliados_activos_cp(cursor, codigo_postal)
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

    n_nuevos_cp = _act_repo.contar_nuevos_aliados_mes_cp(cursor, codigo_postal, anio_mes)
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

    top = _act_repo.ranking_actividad_grupos_cp(cursor, codigo_postal, grupo_id)
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

    for notif in _listar_notificaciones(db, codigo_norm, limite=50):
        formateada = _formatear_notificacion_cinta(notif, codigo_norm)
        if formateada:
            items.append(formateada)

    for aviso in avisos_grupo or []:
        formateada = _formatear_aviso_grupo_cinta(aviso)
        if formateada:
            items.append(formateada)

    ctx = _contexto
    with db._lock:
        conn = None
        try:
            conn = db._connect()
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            if ctx is None:
                ctx = _act_repo.contexto_aliado(cursor, codigo_norm) or {}
            grupo_id = ctx.get("grupo_id")
            cp = str(ctx.get("codigo_postal") or "").strip()

            items.extend(
                _recolectar_desde_tablas(cursor, codigo_norm, grupo_id, cp)
            )
            items.extend(_recolectar_metricas(cursor, grupo_id, cp))
        except Exception:
            pass
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
