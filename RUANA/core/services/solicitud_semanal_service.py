"""Servicio de dominio solicitudes semanales (Campamento Base)."""

from __future__ import annotations

import sqlite3
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional

from core.repositories.solicitud_semanal_repo import SolicitudSemanalRepo
from core.services import catalogo_service, contacto_service, invitacion_service, notificacion_service

_repo = SolicitudSemanalRepo()


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
    return f"Esta semana {nombre} necesita un {oficio_txt}."


def _notificar_grupo_nueva_solicitud(
    db,
    codigos: List[str],
    solicitante_codigo: str,
    solicitante_nombre: str,
    oficio: str,
    solicitud_id: int,
    semana_inicio: str,
) -> None:
    """Avisa a aliados del grupo tras commit (transacción independiente por notificación)."""
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

            aliado = _repo.select_aliado_grupo_nombre(cursor, codigo)
            if not aliado:
                return {"status": "error", "message": "Aliado no encontrado"}
            grupo_id, nombre, _oficio = aliado
            oficios_catalogo = db.get_catalogo_oficios_ruana() or []
            if grupo_id is None:
                return {
                    "status": "success",
                    "semana_inicio": semana,
                    "oficios_grupo": [],
                    "oficios_catalogo": oficios_catalogo,
                    "propia": None,
                    "activas_grupo": [],
                    "historial": [],
                }

            oficios_grupo = _repo.listar_oficios_grupo_activos(cursor, grupo_id)
            propia = _json_safe_row(_repo.listar_propia_semana(cursor, codigo, semana))
            if propia and propia.get("estado") == "activa":
                propia["interesados_count"] = _repo.contar_interesados(
                    cursor, int(propia["id"])
                )
                propia["interesados"] = _json_safe_rows(
                    _repo.listar_respuestas_por_solicitud(
                        cursor, int(propia["id"]), "puedo_ayudar"
                    )
                )
            elif propia and propia.get("estado") != "activa":
                propia = None

            activas = _json_safe_rows(
                _repo.listar_activas_grupo(cursor, grupo_id, semana, codigo)
            )
            activas = _enriquecer_con_respuestas(db, cursor, activas, codigo)

            historial = _json_safe_rows(_repo.listar_historial_grupo(cursor, grupo_id, 30))

            conn.commit()
            return {
                "status": "success",
                "semana_inicio": semana,
                "oficios_grupo": oficios_grupo,
                "oficios_catalogo": oficios_catalogo,
                "propia": propia,
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

            existente = _repo.existe_activa_semana(cursor, codigo, semana_str)
            if existente:
                conn.commit()
                return {
                    "status": "success",
                    "ok": True,
                    "id": existente,
                    "already_existed": True,
                }

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
            return {"status": "success", "ok": True, "id": sid}
        except Exception as e:
            try:
                conn.rollback()
            except Exception:
                pass
            err = str(e)
            if "UNIQUE" in err.upper() or "unique" in err:
                return {
                    "status": "error",
                    "message": "Ya tienes una solicitud activa esta semana",
                }
            return {"status": "error", "message": err}
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


def _validar_acceso_solicitud(
    cursor, solicitud_id: int, codigo: str, permitir_solicitante: bool = False
) -> Optional[Dict[str, Any]]:
    sol = _repo.select_solicitud(cursor, int(solicitud_id))
    if not sol:
        return None
    if sol["estado"] != "activa":
        return None
    if sol["semana_inicio"] != _semana_inicio_str():
        return None
    aliado = _repo.select_aliado_grupo_nombre(cursor, codigo)
    if not aliado:
        return None
    grupo_id = aliado[0]
    if grupo_id != sol["grupo_id"]:
        return None
    if not permitir_solicitante and sol["solicitante_codigo"] == codigo:
        return None
    return sol


def responder_puedo_ayudar(
    db, solicitud_id: int, codigo: str
) -> Dict[str, Any]:
    codigo = (codigo or "").strip()
    with db._lock:
        try:
            conn = db._connect()
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            sol = _validar_acceso_solicitud(cursor, solicitud_id, codigo)
            if not sol:
                return {
                    "status": "error",
                    "message": "Solicitud no disponible o sin permiso",
                }

            existente = _repo.select_respuesta(cursor, int(solicitud_id), codigo)
            if existente and existente.get("tipo_respuesta") == "puedo_ayudar":
                cid = existente.get("contacto_id")
                return {
                    "status": "success",
                    "ok": True,
                    "contacto_id": cid,
                    "ya_registrado": True,
                }

            aliado = _repo.select_aliado_grupo_nombre(cursor, codigo)
            nombre_resp = aliado[1] if aliado else ""
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
                return {
                    "status": "error",
                    "message": contacto_result.get(
                        "message", "No se pudo abrir la negociación"
                    ),
                }
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
            return {
                "status": "success",
                "ok": True,
                "contacto_id": contacto_id,
                "solicitante_codigo": solicitante,
                "solicitante_nombre": sol["solicitante_nombre"],
                "oficio": oficio_txt,
            }
        except Exception as e:
            return {"status": "error", "message": str(e)}
        finally:
            conn.close()


def responder_no_puedo_ayudar(
    db, solicitud_id: int, codigo: str
) -> Dict[str, Any]:
    codigo = (codigo or "").strip()
    with db._lock:
        try:
            conn = db._connect()
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            sol = _validar_acceso_solicitud(cursor, solicitud_id, codigo)
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
    with db._lock:
        try:
            conn = db._connect()
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            sol = _validar_acceso_solicitud(cursor, solicitud_id, codigo)
            if not sol:
                return {
                    "status": "error",
                    "message": "Solicitud no disponible o sin permiso",
                }

            oficio_buscar = (sol["oficio"] or "").strip()
            grupo_id = sol["grupo_id"]
            if db.plaza_ocupada_en_grupo(grupo_id, oficio_buscar):
                return {
                    "status": "error",
                    "message": "Este profesional ya pertenece al grupo.",
                    "codigo": None,
                    "ya_en_grupo": True,
                }

            aliado_row = db.obtener_aliado_por_codigo(codigo)
            if not aliado_row:
                return {"status": "error", "message": "Aliado no encontrado"}
            aliado_id = aliado_row.get("id")
            if not aliado_id:
                return {"status": "error", "message": "Aliado inválido"}

            codigo_inv = generar_codigo_fn(db)
            invitacion_service._registrar_invitacion(db, codigo_inv, int(aliado_id))

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
            return {
                "status": "success",
                "ok": True,
                "codigo": codigo_inv,
            }
        except Exception as e:
            return {"status": "error", "message": str(e)}
        finally:
            conn.close()


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
