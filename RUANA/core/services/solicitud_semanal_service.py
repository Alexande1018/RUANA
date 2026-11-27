"""Servicio de dominio solicitudes semanales (Campamento Base)."""

from __future__ import annotations

import logging
import sqlite3
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional

from core.repositories.solicitud_semanal_repo import SolicitudSemanalRepo
from core.services import catalogo_service, contacto_service, invitacion_service, notificacion_service

_repo = SolicitudSemanalRepo()
logger = logging.getLogger(__name__)


def _json_safe_value(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return value


def _json_safe_row(row: Any) -> Optional[Dict[str, Any]]:
    if not row:
        return None
    data = dict(row)
    return {key: _json_safe_value(val) for key, val in data.items()}


def _json_safe_rows(rows: List[Any]) -> List[Dict[str, Any]]:
    out = []
    for row in rows or []:
        item = _json_safe_row(row)
        if item:
            out.append(item)
    return out


def _semana_inicio_lunes(ref: Optional[date] = None) -> date:
    """Lunes de la semana de ref. date.weekday() es 0 en lunes."""
    d = ref or date.today()
    return d - timedelta(days=d.weekday())


def _semana_inicio_str(ref: Optional[date] = None) -> str:
    return _semana_inicio_lunes(ref).isoformat()


def _expira_at_str(semana_inicio: date) -> str:
    siguiente = semana_inicio + timedelta(days=7)
    return siguiente.isoformat()


def _mensaje_solicitud_semanal_grupo(nombre_solicitante: str, oficio: str) -> str:
    nombre = (nombre_solicitante or "Un aliado").strip()
    oficio_txt = (oficio or "profesional").strip()
    return f"Esta semana {nombre} necesita un profesional de {oficio_txt}."


def _notificar_grupo_nueva_solicitud(
    db,
    codigos: List[str],
    solicitante_codigo: str,
    solicitante_nombre: str,
    oficio: str,
    solicitud_id: int,
    semana_inicio: str,
    alcance: str = "grupo",
) -> None:
    """Avisa tras commit (transacción independiente por notificación).
    ``alcance``: 'grupo' (su grupo) o 'provincia' (resto de activos de la provincia)."""
    if not codigos:
        return
    titulo = "Solicitud de esta semana"
    mensaje = _mensaje_solicitud_semanal_grupo(solicitante_nombre, oficio)
    metadata = {
        "solicitud_semanal_id": int(solicitud_id),
        "oficio": oficio,
        "solicitante_nombre": solicitante_nombre,
        "solicitante_codigo": solicitante_codigo,
        "semana_inicio": semana_inicio,
        "origen": "solicitud_semanal",
        "alcance": alcance,
    }
    for codigo in codigos:
        notificacion_service.crear_notificacion_aliado(
            db,
            codigo,
            "solicitud_semanal_nueva",
            titulo,
            mensaje,
            metadata=metadata,
        )


def _asegurar_esquema_sol_sem(db, conn, cursor) -> None:
    """Asegura tablas de solicitudes semanales (SQLite y Postgres)."""
    try:
        db._migrar_solicitudes_semanales(conn, cursor)
    except Exception:
        try:
            conn.rollback()
        except Exception:
            pass


def _expirar_vencidas(db, cursor) -> None:
  semana = _semana_inicio_str()
  _repo.marcar_expiradas_antes(cursor, semana)


def _enriquecer_con_respuestas(
    db, cursor, solicitudes: List[Dict[str, Any]], codigo: str
) -> List[Dict[str, Any]]:
    out = []
    for s in solicitudes:
        item = dict(s)
        resp = _repo.select_respuesta(cursor, int(s["id"]), codigo)
        item["mi_respuesta"] = resp.get("tipo_respuesta") if resp else None
        item["interesados_count"] = _repo.contar_interesados(cursor, int(s["id"]))
        item["recomendaciones_count"] = _repo.contar_recomendaciones(
            cursor, int(s["id"])
        )
        out.append(item)
    return out


def obtener_panel_por_codigo(db, codigo: str) -> Dict[str, Any]:
    """Snapshot para panel: propia, activas del grupo, oficios, semana."""
    codigo = (codigo or "").strip()
    semana = _semana_inicio_str()
    with db._lock:
        try:
            conn = db._connect()
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            try:
                _asegurar_esquema_sol_sem(db, conn, cursor)
            except Exception:
                pass
            _expirar_vencidas(db, cursor)
            conn.commit()

            aliado = _repo.select_aliado_contexto(cursor, codigo)
            if not aliado:
                return {"status": "error", "message": "Aliado no encontrado"}
            grupo_id = aliado.get("grupo_id")
            oficio_aliado = aliado.get("oficio") or ""
            cp_aliado = (aliado.get("codigo_postal") or "").strip()
            estado_aliado = (aliado.get("estado") or "").strip()
            oficios_catalogo = db.get_catalogo_oficios_ruana() or []
            if grupo_id is None:
                return {
                    "status": "success",
                    "semana_inicio": semana,
                    "oficios_grupo": [],
                    "oficios_catalogo": oficios_catalogo,
                    "propia": None,
                    "propias": [],
                    "activas_grupo": [],
                    "historial": [],
                }

            oficios_grupo = _repo.listar_oficios_grupo_activos(cursor, grupo_id)
            propias = []
            for row in _repo.listar_propias_semana(cursor, codigo, semana):
                item = _json_safe_row(row)
                if not item or item.get("estado") != "activa":
                    continue
                item["interesados_count"] = _repo.contar_interesados(
                    cursor, int(item["id"])
                )
                item["interesados"] = _json_safe_rows(
                    _repo.listar_respuestas_por_solicitud(
                        cursor, int(item["id"]), "puedo_ayudar"
                    )
                )
                propias.append(item)
            propia = propias[0] if propias else None

            activas = _json_safe_rows(
                _repo.listar_activas_grupo(cursor, grupo_id, semana, codigo)
            )
            for item in activas:
                item["de_grupo_cercano"] = False
            if estado_aliado.lower() == "activo":
                if not cp_aliado:
                    cp_aliado = _repo.select_grupo_codigo_postal(cursor, grupo_id)
                extra = _listar_descubiertas_provincia(
                    db,
                    cursor,
                    codigo,
                    grupo_id,
                    oficio_aliado,
                    cp_aliado,
                    semana,
                )
                vistos = {int(x["id"]) for x in activas if x.get("id") is not None}
                for item in extra:
                    sid = item.get("id")
                    if sid is None or int(sid) in vistos:
                        continue
                    activas.append(item)
                    vistos.add(int(sid))
            activas = _enriquecer_con_respuestas(db, cursor, activas, codigo)

            historial = _json_safe_rows(_repo.listar_historial_grupo(cursor, grupo_id, 30))

            conn.commit()
            return {
                "status": "success",
                "semana_inicio": semana,
                "oficios_grupo": oficios_grupo,
                "oficios_catalogo": oficios_catalogo,
                "propia": propia,
                "propias": propias,
                "activas_grupo": activas,
                "historial": historial,
            }
        except Exception as e:
            try:
                conn.rollback()
            except Exception:
                pass
            return {"status": "error", "message": str(e)}
        finally:
            conn.close()


def crear_solicitud_semanal(
    db,
    codigo: str,
    oficio: str,
    descripcion: str = "",
    es_oficio_personalizado: bool = False,
) -> Dict[str, Any]:
    codigo = (codigo or "").strip()
    oficio = (oficio or "").strip()
    descripcion = (descripcion or "").strip()
    if not oficio:
        return {"status": "error", "message": "Oficio requerido"}
    if es_oficio_personalizado and len(oficio) < 3:
        return {
            "status": "error",
            "message": "Describe qué profesional necesitas (mínimo 3 caracteres)",
        }

    semana = _semana_inicio_lunes()
    semana_str = semana.isoformat()
    expira = _expira_at_str(semana)

    with db._lock:
        try:
            conn = db._connect()
            cursor = conn.cursor()
            try:
                _asegurar_esquema_sol_sem(db, conn, cursor)
            except Exception:
                pass
            _expirar_vencidas(db, cursor)

            aliado = _repo.select_aliado_grupo_nombre(cursor, codigo)
            if not aliado:
                return {"status": "error", "message": "Aliado no válido"}
            grupo_id, nombre, _ = aliado
            if grupo_id is None:
                return {"status": "error", "message": "No perteneces a un grupo"}

            catalogo = db.get_catalogo_oficios_ruana()
            permitidos = {str(o).strip() for o in catalogo if o}
            oficios_grupo = {
                str(o).strip()
                for o in _repo.listar_oficios_grupo_activos(cursor, grupo_id)
                if o
            }
            if not es_oficio_personalizado:
                canon = catalogo_service._resolver_en_conjunto_catalogo(db, oficio, permitidos)
                if not canon:
                    canon = catalogo_service._resolver_en_conjunto_catalogo(
                        db, oficio, oficios_grupo
                    )
                if canon:
                    oficio = canon
                elif oficio not in oficios_grupo:
                    return {
                        "status": "error",
                        "message": "Oficio no válido. Elige uno de la lista o usa «Otro profesional».",
                    }

            sid = _repo.insertar(
                cursor,
                grupo_id,
                codigo,
                nombre,
                oficio,
                descripcion,
                1 if es_oficio_personalizado else 0,
                semana_str,
                expira,
            )
            codigos_notificar = _repo.listar_codigos_activos_grupo(
                cursor, grupo_id, excluir_codigo=codigo
            )
            codigos_provincia: List[str] = []
            # Aviso provincial: todos los aliados activos (con grupo) de la
            # misma provincia que el solicitante, además de su grupo.
            try:
                cp_sol = _repo.select_cp_aliado(cursor, codigo) or _repo.select_grupo_codigo_postal(
                    cursor, grupo_id
                )
                prefijo = _prefijo_provincia(cp_sol or "")
                if prefijo:
                    vistos = set(codigos_notificar)
                    for c in _repo.listar_codigos_activos_provincia(cursor, prefijo, codigo):
                        if c not in vistos:
                            codigos_provincia.append(c)
                            vistos.add(c)
            except Exception:
                codigos_provincia = []
            conn.commit()
            _notificar_grupo_nueva_solicitud(
                db,
                codigos_notificar,
                codigo,
                nombre,
                oficio,
                int(sid),
                semana_str,
            )
            _notificar_grupo_nueva_solicitud(
                db,
                codigos_provincia,
                codigo,
                nombre,
                oficio,
                int(sid),
                semana_str,
                alcance="provincia",
            )
            return {"status": "success", "ok": True, "id": sid}
        except Exception as e:
            try:
                conn.rollback()
            except Exception:
                pass
            return {"status": "error", "message": str(e)}
        finally:
            conn.close()


def actualizar_solicitud_semanal(
    db,
    solicitud_id: int,
    codigo: str,
    oficio: str,
    descripcion: str = "",
    es_oficio_personalizado: bool = False,
) -> Dict[str, Any]:
    codigo = (codigo or "").strip()
    oficio = (oficio or "").strip()
    with db._lock:
        try:
            conn = db._connect()
            cursor = conn.cursor()
            sol = _repo.select_solicitud(cursor, int(solicitud_id))
            if not sol:
                return {"status": "error", "message": "Solicitud no encontrada"}
            if sol["solicitante_codigo"] != codigo:
                return {"status": "error", "message": "No puedes modificar esta solicitud"}
            if sol["estado"] != "activa":
                return {"status": "error", "message": "La solicitud ya no está activa"}
            if sol["semana_inicio"] != _semana_inicio_str():
                return {"status": "error", "message": "Solo puedes modificar la solicitud de esta semana"}

            if not es_oficio_personalizado and oficio:
                catalogo = db.get_catalogo_oficios_ruana()
                permitidos = {str(o).strip() for o in catalogo if o}
                canon = catalogo_service._resolver_en_conjunto_catalogo(db, oficio, permitidos)
                if not canon:
                    return {"status": "error", "message": "Oficio no válido"}
                oficio = canon

            rc = _repo.actualizar_oficio_descripcion(
                cursor,
                int(solicitud_id),
                oficio,
                descripcion or "",
                1 if es_oficio_personalizado else 0,
            )
            conn.commit()
            if rc == 0:
                return {"status": "error", "message": "No se pudo actualizar"}
            return {"status": "success", "ok": True}
        except Exception as e:
            return {"status": "error", "message": str(e)}
        finally:
            conn.close()


ETIQUETA_GRUPO_CERCANO = "De tu provincia"


def _prefijo_provincia(codigo_postal: str) -> str:
    """Provincia = los 2 primeros dígitos del CP (solo dígitos)."""
    digitos = "".join(ch for ch in str(codigo_postal or "") if ch.isdigit())
    return digitos[:2] if len(digitos) >= 2 else ""


def _mismo_grupo(a: Any, b: Any) -> bool:
    if a is None or b is None:
        return False
    return str(a) == str(b)


def _grupo_cubre_oficio(
    db,
    cursor,
    grupo_id: Any,
    oficio: str,
    excluir_codigo: str,
    cache: Optional[Dict[Any, bool]] = None,
) -> bool:
    """True si hay otro aliado activo del grupo cuyo oficio cubre el pedido."""
    clave = (grupo_id, oficio, excluir_codigo)
    if cache is not None and clave in cache:
        return cache[clave]
    oficios = _repo.listar_oficios_activos_grupo_excepto(
        cursor, grupo_id, excluir_codigo
    )
    cubre = any(
        catalogo_service.oficios_equivalentes(db, oficio, cand) for cand in oficios
    )
    if cache is not None:
        cache[clave] = cubre
    return cubre


def _cp_de_solicitud(sol: Dict[str, Any]) -> str:
    return (
        (sol.get("solicitante_cp") or "").strip()
        or (sol.get("grupo_cp") or "").strip()
    )


def _cumple_acceso_provincia_descubierta(
    db,
    cursor,
    sol: Dict[str, Any],
    oficio_aliado: str,
    prefijo_aliado: str,
    estado_aliado: str,
    codigo_aliado: str,
    cache: Optional[Dict[Any, bool]] = None,
) -> bool:
    """Visibilidad provincial (24 nov 2026): cualquier aliado activo de la misma
    provincia (prefijo de CP) ve la solicitud, sea cual sea su oficio y aunque el
    grupo del solicitante cubra el oficio. Así puede ofrecerse o recomendar a
    alguien («Conozco a alguien»). ``oficio_aliado`` y ``cache`` se mantienen
    por compatibilidad de firma."""
    if (estado_aliado or "").strip().lower() != "activo":
        return False
    if not prefijo_aliado:
        return False
    if (sol.get("solicitante_codigo") or "") == codigo_aliado:
        return False
    if _prefijo_provincia(_cp_de_solicitud(sol)) != prefijo_aliado:
        return False
    return True


def _listar_descubiertas_provincia(
    db,
    cursor,
    codigo: str,
    grupo_id: Any,
    oficio_aliado: str,
    cp_aliado: str,
    semana: str,
) -> List[Dict[str, Any]]:
    prefijo = _prefijo_provincia(cp_aliado)
    if not prefijo:
        return []
    rows = _repo.listar_activas_fuera_grupo(cursor, semana, grupo_id, codigo)
    cache: Dict[Any, bool] = {}
    out: List[Dict[str, Any]] = []
    for row in rows:
        item = dict(row)
        if not _cumple_acceso_provincia_descubierta(
            db,
            cursor,
            item,
            oficio_aliado,
            prefijo,
            "activo",
            codigo,
            cache,
        ):
            continue
        item.pop("solicitante_cp", None)
        item.pop("grupo_cp", None)
        item["de_grupo_cercano"] = True
        item["etiqueta"] = ETIQUETA_GRUPO_CERCANO
        out.append(item)
    return out


def _validar_acceso_solicitud(
    db,
    cursor,
    solicitud_id: int,
    codigo: str,
    permitir_solicitante: bool = False,
) -> Optional[Dict[str, Any]]:
    sol = _repo.select_solicitud(cursor, int(solicitud_id))
    if not sol:
        return None
    if sol["estado"] != "activa":
        return None
    if sol["semana_inicio"] != _semana_inicio_str():
        return None
    aliado = _repo.select_aliado_contexto(cursor, codigo)
    if not aliado:
        return None
    if _mismo_grupo(aliado.get("grupo_id"), sol["grupo_id"]):
        if not permitir_solicitante and sol["solicitante_codigo"] == codigo:
            return None
        return sol
    # Solo el caso provincial: oficio pedido (campo oficio) + misma provincia
    # + nadie activo del grupo puede cubrir ese oficio.
    solicitante = _repo.select_aliado_contexto(cursor, sol["solicitante_codigo"])
    item = dict(sol)
    item["solicitante_cp"] = (
        ((solicitante or {}).get("codigo_postal") or "").strip()
    )
    if not item["solicitante_cp"]:
        item["grupo_cp"] = _repo.select_grupo_codigo_postal(
            cursor, sol.get("grupo_id")
        )
    prefijo = _prefijo_provincia(
        (aliado.get("codigo_postal") or "").strip()
        or _repo.select_grupo_codigo_postal(cursor, aliado.get("grupo_id"))
    )
    if _cumple_acceso_provincia_descubierta(
        db,
        cursor,
        item,
        aliado.get("oficio") or "",
        prefijo,
        aliado.get("estado") or "",
        codigo,
    ):
        return sol
    return None



TIPO_AVISO_RESPUESTA = "solicitud_semanal_respuesta"
CLAVE_AVISO_RESPUESTA = "sol_sem_resp:{solicitud_id}:{respondente}"


def _nombre_visible(nombre: str) -> str:
    """Nombre de pantalla, como en el resto de avisos; nunca teléfono ni email."""
    return (nombre or "").strip() or "Un aliado"


def _url_publica_aliado(query: str = "", fragmento: str = "") -> str:
    from core.settings import get_settings

    base = (get_settings().public_app_url or "https://ruana-4293f.web.app").rstrip("/")
    url = f"{base}/aliado"
    if query:
        url += "?" + query.lstrip("?")
    if fragmento:
        url += fragmento if fragmento.startswith("#") else "#" + fragmento
    return url


def _enlace_aviso_respuesta(tipo_respuesta: str, contacto_id: Any) -> str:
    if tipo_respuesta == "puedo_ayudar" and contacto_id:
        return _url_publica_aliado(query=f"contacto_id={int(contacto_id)}")
    return _url_publica_aliado(fragmento="solicitudes")


def _textos_aviso_respuesta(
    nombre_respondente: str, oficio: str, tipo_respuesta: str, enlace: str
) -> Dict[str, str]:
    nombre = _nombre_visible(nombre_respondente)
    oficio_txt = (oficio or "profesional").strip() or "profesional"
    if tipo_respuesta == "conozco_alguien":
        mensaje = f"{nombre} conoce a alguien para tu solicitud de {oficio_txt}"
        titulo = "Alguien conoce a alguien para tu solicitud"
        asunto = "Alguien conoce a alguien para tu solicitud en RUANA"
        cuerpo = (
            f"{mensaje}.\n\n"
            "Entra en RUANA para ver tu solicitud de esta semana:\n"
            f"{enlace}\n\n"
            "El contacto se queda dentro de RUANA.\n\n"
            "Equipo RUANA."
        )
    else:
        mensaje = f"{nombre} puede ayudarte con tu solicitud de {oficio_txt}"
        titulo = "Alguien puede ayudarte con tu solicitud"
        asunto = "Alguien puede ayudarte con tu solicitud en RUANA"
        cuerpo = (
            f"{mensaje}.\n\n"
            "Abre el chat guiado en RUANA (el contacto se queda dentro de la app):\n"
            f"{enlace}\n\n"
            "Equipo RUANA."
        )
    return {
        "nombre": nombre,
        "oficio": oficio_txt,
        "mensaje": mensaje,
        "titulo": titulo,
        "asunto": asunto,
        "cuerpo": cuerpo,
    }


def _avisar_solicitante_respuesta(
    db,
    sol: Dict[str, Any],
    respondente_codigo: str,
    respondente_nombre: str,
    tipo_respuesta: str,
    contacto_id: Any = None,
) -> None:
    """Aviso in-app + email al autor. Un fallo no debe romper la respuesta."""
    try:
        if tipo_respuesta not in ("puedo_ayudar", "conozco_alguien"):
            return
        solicitante = (sol.get("solicitante_codigo") or "").strip()
        if not solicitante or solicitante == (respondente_codigo or "").strip():
            return
        try:
            schema_ok = getattr(db, "_migrar_notificaciones_clave_unica", None)
            if schema_ok:
                with db._lock:
                    conn = db._connect()
                    try:
                        db._migrar_notificaciones_clave_unica(conn, conn.cursor())
                        conn.commit()
                    finally:
                        conn.close()
        except Exception:
            logger.exception("[RUANA][SOL_SEM] No se pudo asegurar clave_unica")

        enlace = _enlace_aviso_respuesta(tipo_respuesta, contacto_id)
        textos = _textos_aviso_respuesta(
            respondente_nombre, sol.get("oficio") or "", tipo_respuesta, enlace
        )
        metadata = {
            "solicitud_semanal_id": int(sol["id"]),
            "tipo_respuesta": tipo_respuesta,
            "oficio": textos["oficio"],
            "respondente_nombre": textos["nombre"],
            "origen": "solicitud_semanal_respuesta",
            "enlace": enlace,
        }
        if contacto_id:
            metadata["contacto_id"] = int(contacto_id)
        clave = CLAVE_AVISO_RESPUESTA.format(
            solicitud_id=int(sol["id"]),
            respondente=(respondente_codigo or "").strip(),
        )
        estado = notificacion_service.crear_notificacion_aliado_unica(
            db,
            solicitante,
            TIPO_AVISO_RESPUESTA,
            textos["titulo"],
            textos["mensaje"],
            metadata=metadata,
            clave_unica=clave,
        )
        if estado != "created":
            return
        destinatario = db.obtener_aliado_por_codigo(solicitante) or {}
        email = (destinatario.get("email") or "").strip()
        if not email:
            return
        saludo = _nombre_visible(destinatario.get("nombre") or sol.get("solicitante_nombre") or "")
        cuerpo = f"Hola, {saludo}.\n\n" + textos["cuerpo"]
        from core import email_service

        email_service.enviar_correo_aliado(
            email,
            textos["asunto"],
            cuerpo,
            contexto="solicitud_semanal_respuesta",
        )
    except Exception:
        logger.exception(
            "[RUANA][SOL_SEM] Fallo avisando al solicitante (solicitud=%s, tipo=%s)",
            sol.get("id") if sol else None,
            tipo_respuesta,
        )


def responder_puedo_ayudar(
    db, solicitud_id: int, codigo: str
) -> Dict[str, Any]:
    codigo = (codigo or "").strip()
    resultado: Optional[Dict[str, Any]] = None
    aviso: Optional[Dict[str, Any]] = None
    conn = None
    with db._lock:
        try:
            conn = db._connect()
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            sol = _validar_acceso_solicitud(db, cursor, solicitud_id, codigo)
            if not sol:
                resultado = {
                    "status": "error",
                    "message": "Solicitud no disponible o sin permiso",
                }
            else:
                existente = _repo.select_respuesta(cursor, int(solicitud_id), codigo)
                aliado = _repo.select_aliado_grupo_nombre(cursor, codigo)
                nombre_resp = aliado[1] if aliado else ""
                if existente and existente.get("tipo_respuesta") == "puedo_ayudar":
                    cid = existente.get("contacto_id")
                    resultado = {
                        "status": "success",
                        "ok": True,
                        "contacto_id": cid,
                        "ya_registrado": True,
                    }
                    aviso = {
                        "sol": dict(sol),
                        "respondente_codigo": codigo,
                        "respondente_nombre": nombre_resp,
                        "tipo_respuesta": "puedo_ayudar",
                        "contacto_id": cid,
                    }
                else:
                    solicitante = sol["solicitante_codigo"]
                    oficio_txt = sol["oficio"] or "profesional"
                    motivo = f"Solicitud semanal: necesita {oficio_txt}"

                    contacto_result = contacto_service.crear_contacto_ruana(
                        db,
                        solicitante_codigo=solicitante,
                        profesional_codigo=codigo,
                        servicio=oficio_txt,
                        motivo_contacto=motivo,
                        es_urgente=False,
                    )
                    if contacto_result.get("status") != "success":
                        resultado = {
                            "status": "error",
                            "message": contacto_result.get(
                                "message", "No se pudo abrir la negociación"
                            ),
                        }
                    else:
                        contacto_id = int(contacto_result["id"])

                        if existente:
                            cursor.execute(
                                """
                                UPDATE solicitudes_semanales_respuestas
                                SET tipo_respuesta = 'puedo_ayudar', contacto_id = ?
                                WHERE id = ?
                                """,
                                (contacto_id, existente["id"]),
                            )
                        else:
                            _repo.insertar_respuesta(
                                cursor,
                                int(solicitud_id),
                                codigo,
                                nombre_resp,
                                "puedo_ayudar",
                                contacto_id=contacto_id,
                            )
                        conn.commit()
                        resultado = {
                            "status": "success",
                            "ok": True,
                            "contacto_id": contacto_id,
                            "solicitante_codigo": solicitante,
                            "solicitante_nombre": sol["solicitante_nombre"],
                            "oficio": oficio_txt,
                        }
                        aviso = {
                            "sol": dict(sol),
                            "respondente_codigo": codigo,
                            "respondente_nombre": nombre_resp,
                            "tipo_respuesta": "puedo_ayudar",
                            "contacto_id": contacto_id,
                        }
        except Exception as e:
            resultado = {"status": "error", "message": str(e)}
        finally:
            if conn is not None:
                conn.close()
    if aviso:
        _avisar_solicitante_respuesta(db, **aviso)
    return resultado or {"status": "error", "message": "No se pudo registrar la respuesta"}


def responder_no_puedo_ayudar(
    db, solicitud_id: int, codigo: str
) -> Dict[str, Any]:
    codigo = (codigo or "").strip()
    with db._lock:
        try:
            conn = db._connect()
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            sol = _validar_acceso_solicitud(db, cursor, solicitud_id, codigo)
            if not sol:
                return {
                    "status": "error",
                    "message": "Solicitud no disponible o sin permiso",
                }

            existente = _repo.select_respuesta(cursor, int(solicitud_id), codigo)
            aliado = _repo.select_aliado_grupo_nombre(cursor, codigo)
            nombre = aliado[1] if aliado else ""

            if existente:
                cursor.execute(
                    """
                    UPDATE solicitudes_semanales_respuestas
                    SET tipo_respuesta = 'no_puedo_ayudar', contacto_id = NULL,
                        invitacion_codigo = NULL
                    WHERE id = ?
                    """,
                    (existente["id"],),
                )
            else:
                _repo.insertar_respuesta(
                    cursor,
                    int(solicitud_id),
                    codigo,
                    nombre,
                    "no_puedo_ayudar",
                )
            conn.commit()
            return {"status": "success", "ok": True}
        except Exception as e:
            return {"status": "error", "message": str(e)}
        finally:
            conn.close()


def responder_conozco_alguien(
    db, solicitud_id: int, codigo: str, generar_codigo_fn
) -> Dict[str, Any]:
    """generar_codigo_fn(db) -> str único de invitación."""
    codigo = (codigo or "").strip()
    resultado: Optional[Dict[str, Any]] = None
    aviso: Optional[Dict[str, Any]] = None
    conn = None
    with db._lock:
        try:
            conn = db._connect()
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            sol = _validar_acceso_solicitud(db, cursor, solicitud_id, codigo)
            if not sol:
                resultado = {
                    "status": "error",
                    "message": "Solicitud no disponible o sin permiso",
                }
            else:
                oficio_buscar = (sol["oficio"] or "").strip()
                grupo_id = sol["grupo_id"]
                aliado_row = db.obtener_aliado_por_codigo(codigo)
                cp_aliado = (aliado_row.get("codigo_postal") or "") if aliado_row else ""
                from core.services import grupo_service
                if grupo_service.plaza_ocupada_contexto(
                    db, grupo_id, oficio_buscar, cp_aliado, cursor=cursor
                ):
                    resultado = {
                        "status": "error",
                        "message": "Este profesional ya pertenece al grupo.",
                        "codigo": None,
                        "ya_en_grupo": True,
                    }
                elif not aliado_row:
                    resultado = {"status": "error", "message": "Aliado no encontrado"}
                elif not aliado_row.get("id"):
                    resultado = {"status": "error", "message": "Aliado inválido"}
                else:
                    codigo_inv = generar_codigo_fn(db)
                    invitacion_service._registrar_invitacion(
                        db, codigo_inv, int(aliado_row["id"])
                    )

                    nombre = aliado_row.get("nombre") or ""
                    existente = _repo.select_respuesta(cursor, int(solicitud_id), codigo)
                    if existente:
                        cursor.execute(
                            """
                            UPDATE solicitudes_semanales_respuestas
                            SET tipo_respuesta = 'conozco_alguien', invitacion_codigo = ?,
                                contacto_id = NULL
                            WHERE id = ?
                            """,
                            (codigo_inv, existente["id"]),
                        )
                    else:
                        _repo.insertar_respuesta(
                            cursor,
                            int(solicitud_id),
                            codigo,
                            nombre,
                            "conozco_alguien",
                            invitacion_codigo=codigo_inv,
                        )
                    conn.commit()
                    resultado = {
                        "status": "success",
                        "ok": True,
                        "codigo": codigo_inv,
                    }
                    aviso = {
                        "sol": dict(sol),
                        "respondente_codigo": codigo,
                        "respondente_nombre": nombre,
                        "tipo_respuesta": "conozco_alguien",
                        "contacto_id": None,
                    }
        except Exception as e:
            resultado = {"status": "error", "message": str(e)}
        finally:
            if conn is not None:
                conn.close()
    if aviso:
        _avisar_solicitante_respuesta(db, **aviso)
    return resultado or {"status": "error", "message": "No se pudo registrar la respuesta"}


def listar_interesados(
    db, solicitud_id: int, codigo: str
) -> Dict[str, Any]:
    codigo = (codigo or "").strip()
    with db._lock:
        try:
            conn = db._connect()
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            sol = _repo.select_solicitud(cursor, int(solicitud_id))
            if not sol:
                return {"status": "error", "message": "Solicitud no encontrada"}
            if sol["solicitante_codigo"] != codigo:
                aliado = _repo.select_aliado_grupo_nombre(cursor, codigo)
                if not aliado or aliado[0] != sol["grupo_id"]:
                    return {"status": "error", "message": "Sin permiso"}
                return {"status": "error", "message": "Solo el solicitante puede ver interesados"}

            interesados = _repo.listar_respuestas_por_solicitud(
                cursor, int(solicitud_id), "puedo_ayudar"
            )
            return {
                "status": "success",
                "interesados": interesados,
                "total": len(interesados),
            }
        except Exception as e:
            return {"status": "error", "message": str(e)}
        finally:
            conn.close()


def listar_admin(db, limite: int = 300) -> Dict[str, Any]:
    """Listado global para el panel administrador."""
    semana = _semana_inicio_str()
    limite = max(1, min(int(limite or 300), 1000))
    with db._lock:
        try:
            conn = db._connect()
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            try:
                _asegurar_esquema_sol_sem(db, conn, cursor)
            except Exception:
                pass
            _expirar_vencidas(db, cursor)
            conn.commit()

            rows = _json_safe_rows(_repo.listar_todas_admin(cursor, limite))
            ids = [int(r["id"]) for r in rows if r.get("id") is not None]
            respuestas = _json_safe_rows(
                _repo.listar_respuestas_para_ids(cursor, ids)
            )
            por_solicitud: Dict[int, List[Dict[str, Any]]] = {}
            for resp in respuestas:
                sid = int(resp.get("solicitud_semanal_id") or 0)
                por_solicitud.setdefault(sid, []).append(resp)

            for item in rows:
                resps = por_solicitud.get(int(item["id"]), [])
                item["respuestas"] = resps
                item["interesados_count"] = sum(
                    1 for x in resps if x.get("tipo_respuesta") == "puedo_ayudar"
                )
                item["recomendaciones_count"] = sum(
                    1
                    for x in resps
                    if x.get("tipo_respuesta") == "conozco_alguien"
                )
                item["no_pueden_count"] = sum(
                    1
                    for x in resps
                    if x.get("tipo_respuesta") == "no_puedo_ayudar"
                )
                item["es_semana_actual"] = str(item.get("semana_inicio") or "") == semana

            activas_semana = [
                r
                for r in rows
                if r.get("estado") == "activa" and r.get("es_semana_actual")
            ]
            return {
                "status": "success",
                "semana_inicio": semana,
                "solicitudes": rows,
                "activas_semana_count": len(activas_semana),
            }
        except Exception as e:
            try:
                conn.rollback()
            except Exception:
                pass
            return {"status": "error", "message": str(e)}
        finally:
            conn.close()


def expirar_solicitudes_vencidas(db) -> Dict[str, Any]:
    """Marca solicitudes de semanas anteriores como expiradas (cron/manual)."""
    with db._lock:
        try:
            conn = db._connect()
            cursor = conn.cursor()
            try:
                _asegurar_esquema_sol_sem(db, conn, cursor)
            except Exception:
                pass
            semana = _semana_inicio_str()
            _repo.marcar_expiradas_antes(cursor, semana)
            conn.commit()
            return {"status": "success", "ok": True}
        except Exception as e:
            return {"status": "error", "message": str(e)}
        finally:
            conn.close()
