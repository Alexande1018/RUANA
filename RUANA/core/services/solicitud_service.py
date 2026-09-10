"""Servicio de dominio solicitud (Campamento Base).

Extracción progresiva desde DBManager. Las fachadas permanecen en DBManager.
SQL de solicitudes vía SolicitudRepo.
"""
from __future__ import annotations

import os
import sqlite3
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from core.repositories.invitacion_repo import InvitacionRepo
from core.repositories.solicitud_repo import SolicitudRepo
from core.services import catalogo_service, notificacion_service

_repo = SolicitudRepo()
_inv_repo = InvitacionRepo()

DESTINO_PROFESIONAL_GRUPO = "profesional_grupo"
DESTINO_PROXIMIDAD = "proximidad"
DESTINO_BUSCANDO_AYUDA = "buscando_ayuda"
PROXIMIDAD_PENDIENTE = "pendiente_aprobacion"
PROXIMIDAD_ACEPTADA = "aceptada"
PROXIMIDAD_RECHAZADA = "rechazada"

_OFICIO_PERSONA = {
    "fontaneria": "fontanero",
    "electricidad": "electricista",
    "cerrajeria": "cerrajero",
    "carpinteria": "carpintero",
    "pintura": "pintor",
    "albanileria": "albañil",
    "jardineria": "jardinero",
}

CANDIDATO_INVITACION_HORAS = max(
    1, int(os.environ.get("RUANA_CANDIDATO_INVITACION_HORAS", "24"))
)


def _json_safe_value(value: Any) -> Any:
    """Fechas Postgres → ISO para que el panel aliado pinte created_at/atendido_at."""
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return value


def _json_safe_row(row: Any) -> Dict[str, Any]:
    data = dict(row) if row is not None else {}
    return {key: _json_safe_value(val) for key, val in data.items()}


def _json_safe_rows(rows: List[Any]) -> List[Dict[str, Any]]:
    return [_json_safe_row(row) for row in (rows or [])]


def _extra_cols_candidato_asignada(cols: List[str]) -> str:
    extra = ""
    if "candidato_por_codigo" in cols:
        extra += ", candidato_por_codigo, candidato_por_nombre, candidato_at"
    if "asignada_a_codigo" in cols:
        extra += ", asignada_a_codigo, asignada_a_nombre"
    if "destino" in cols:
        extra += (
            ", destino, proximidad_codigo, proximidad_nombre, proximidad_cp, "
            "proximidad_zona, proximidad_estado"
        )
    return extra


def _asegurar_migraciones_candidato(db, conn, cursor) -> None:
    try:
        db._migrar_solicitudes_candidato(conn, cursor)
        db._migrar_solicitudes_proximidad(conn, cursor)
        db._migrar_invitaciones_revocada(conn, cursor)
    except Exception:
        pass


def _etiqueta_oficio_humano(oficio: str) -> str:
    txt = (oficio or "profesional").strip()
    if " y " in txt:
        txt = txt.split(" y ", 1)[0].strip()
    clave = catalogo_service._normalizar_texto_catalogo(txt)
    return _OFICIO_PERSONA.get(clave, txt.lower() or "profesional")


def _oficios_equivalentes(db, solicitado: str, candidato: str) -> bool:
    return catalogo_service.oficios_equivalentes(db, solicitado, candidato)


def resolver_oficio_conexion(db, oficio: str) -> str:
    """Resuelve el oficio pedido al nombre de catálogo cuando existe equivalencia."""
    oficio = (oficio or "").strip()
    if not oficio:
        return oficio
    catalogo = {str(o).strip() for o in (db.get_catalogo_oficios_ruana() or []) if o}
    canon = catalogo_service._resolver_en_conjunto_catalogo(db, oficio, catalogo)
    if canon:
        return canon
    objetivo = catalogo_service._normalizar_texto_catalogo(oficio)
    candidatos = []
    for item in catalogo:
        normalizado = catalogo_service._normalizar_texto_catalogo(item)
        if (
            normalizado == objetivo
            or normalizado.startswith(objetivo)
            or objetivo in normalizado
        ):
            candidatos.append((len(normalizado), item))
    if candidatos:
        candidatos.sort()
        return candidatos[0][1]
    return oficio


def _zona_proximidad(rec: Dict[str, Any]) -> str:
    cp = (rec.get("codigo_postal") or "").strip()
    etiqueta = (rec.get("etiqueta_proximidad") or "").strip()
    if cp and etiqueta:
        return f"{cp} ({etiqueta})"
    return cp or etiqueta or "una zona cercana"


def mensaje_recomendacion_proximidad(oficio: str, rec: Dict[str, Any]) -> str:
    oficio_h = _etiqueta_oficio_humano(oficio)
    nombre = (rec.get("nombre") or "un profesional").strip()
    zona = _zona_proximidad(rec)
    return (
        f"No hay {oficio_h} en tu grupo. Te recomendamos a {nombre}, "
        f"el más cercano a tu código postal · {zona}."
    )


def _pack_proximidad(row: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    codigo = (row.get("proximidad_codigo") or "").strip()
    if not codigo:
        return None
    return {
        "codigo": codigo,
        "nombre": row.get("proximidad_nombre") or "",
        "codigo_postal": row.get("proximidad_cp") or "",
        "etiqueta_proximidad": row.get("proximidad_zona") or "",
        "estado": row.get("proximidad_estado") or "",
        "mismo_grupo": False,
    }


def _enriquecer_propia(row: Dict[str, Any]) -> Dict[str, Any]:
    item = dict(row)
    prox = _pack_proximidad(item)
    if prox:
        item["proximidad"] = prox
    destino = (item.get("destino") or "").strip()
    estado = (item.get("estado") or "").strip().lower()
    if destino == DESTINO_BUSCANDO_AYUDA and estado == "pendiente":
        item["etiqueta_busqueda"] = "Buscando ayuda"
        item["mensaje_solicitante"] = (
            "Buscando ayuda. Tu grupo puede recomendar a alguien que entre al grupo."
        )
    elif (
        destino == DESTINO_PROXIMIDAD
        and (item.get("proximidad_estado") or "") == PROXIMIDAD_PENDIENTE
        and prox
    ):
        item["mensaje_solicitante"] = mensaje_recomendacion_proximidad(
            item.get("oficio") or "", prox
        )
        item["requiere_aprobacion_proximidad"] = True
        item["opciones_solicitante"] = {
            "aceptar_proximidad": True,
            "pedir_recomendacion_grupo": True,
        }
    elif destino == DESTINO_PROFESIONAL_GRUPO and item.get("asignada_a_nombre"):
        item["mensaje_solicitante"] = (
            f"Solicitud enviada a {item.get('asignada_a_nombre')}."
        )
    elif destino == DESTINO_PROXIMIDAD and (item.get("proximidad_estado") or "") == PROXIMIDAD_ACEPTADA:
        nombre = item.get("asignada_a_nombre") or (prox or {}).get("nombre") or "el profesional"
        item["mensaje_solicitante"] = f"Contactaste a {nombre}."
    return item


def _pack_profesional(row: Dict[str, Any], oficio: str, mismo_grupo: bool) -> Dict[str, Any]:
    return {
        "codigo": str(row.get("codigo") or "").strip(),
        "nombre": row.get("nombre") or "",
        "oficio": row.get("oficio") or oficio,
        "codigo_postal": row.get("codigo_postal") or "",
        "mismo_grupo": mismo_grupo,
    }


def _primer_profesional_oficio(
    db, rows: List[Any], oficio: str, prefer_grupo_id: Any = None
) -> Optional[Dict[str, Any]]:
    matches: List[Dict[str, Any]] = []
    for raw in rows or []:
        row = dict(raw) if not isinstance(raw, dict) else raw
        if _oficios_equivalentes(db, oficio, row.get("oficio") or ""):
            matches.append(row)
    if not matches:
        return None
    if prefer_grupo_id is not None:
        prefer = str(prefer_grupo_id)
        for row in matches:
            if str(row.get("grupo_id") or "") == prefer:
                return _pack_profesional(row, oficio, True)
    mismo = prefer_grupo_id is not None and str(matches[0].get("grupo_id") or "") == str(prefer_grupo_id)
    return _pack_profesional(matches[0], oficio, mismo)


def _buscar_profesional_grupo(
    db, cursor, grupo_id: Any, oficio: str, excluir_codigo: str
) -> Optional[Dict[str, Any]]:
    return _primer_profesional_oficio(
        db,
        _repo.select_profesional_grupo_oficio(cursor, grupo_id, excluir_codigo),
        oficio,
        prefer_grupo_id=grupo_id,
    )


def _notificar_profesional_solicitud(
    db,
    codigo_dest: str,
    solicitante_nombre: str,
    oficio: str,
    solicitud_id: int,
) -> None:
    oficio_h = _etiqueta_oficio_humano(oficio)
    notificacion_service.crear_notificacion_aliado(
        db,
        codigo_dest,
        "solicitud_asignada",
        "Nueva solicitud para ti",
        f"{solicitante_nombre} te ha enviado una solicitud de {oficio_h}.",
        metadata={
            "solicitud_id": int(solicitud_id),
            "oficio": oficio,
            "solicitante_nombre": solicitante_nombre,
            "origen": "nueva_conexion",
        },
    )


def _notificar_grupo_buscando_ayuda(
    db,
    grupo_id: Any,
    solicitante_codigo: str,
    solicitante_nombre: str,
    oficio: str,
    solicitud_id: int,
) -> None:
    oficio_h = _etiqueta_oficio_humano(oficio)
    notificacion_service.notificar_grupo_actividad(
        db,
        int(grupo_id),
        "solicitud_buscando_ayuda",
        "Buscando ayuda",
        f"{solicitante_nombre} busca un {oficio_h} y no hay ninguno cerca. "
        f"¿Puedes recomendar a alguien?",
        metadata={
            "solicitud_id": int(solicitud_id),
            "oficio": oficio,
            "solicitante_codigo": solicitante_codigo,
            "solicitante_nombre": solicitante_nombre,
            "origen": "nueva_conexion",
        },
        excluir_codigo=solicitante_codigo,
    )


def _notificar_grupo_profesional_contactado(
    db,
    grupo_id: Any,
    solicitante_codigo: str,
    solicitante_nombre: str,
    profesional_codigo: str,
    profesional_nombre: str,
    oficio: str,
    solicitud_id: int,
) -> None:
    notificacion_service.notificar_grupo_actividad(
        db,
        int(grupo_id),
        "proximidad_contactada",
        "Profesional contactado",
        f"{profesional_nombre} ha sido contactado para un encargo por {solicitante_nombre}.",
        metadata={
            "solicitud_id": int(solicitud_id),
            "oficio": oficio,
            "solicitante_codigo": solicitante_codigo,
            "solicitante_nombre": solicitante_nombre,
            "profesional_codigo": profesional_codigo,
            "profesional_nombre": profesional_nombre,
            "origen": "nueva_conexion",
        },
        excluir_codigo=solicitante_codigo,
    )


def calcular_expiracion_candidato(desde: Optional[datetime] = None) -> str:
    """ISO timestamp de caducidad del código «Conozco a alguien»."""
    base = desde or datetime.now(timezone.utc).replace(tzinfo=None)
    return (base + timedelta(hours=CANDIDATO_INVITACION_HORAS)).replace(microsecond=0).isoformat() + "Z"


def _expirar_candidatos_vencidos(db, cursor) -> int:
    """
    Revoca invitaciones «Conozco a alguien» vencidas y reabre solicitudes a pendiente.
    Retorna cuántas solicitudes se reactivaron.
    """
    ids = _repo.listar_ids_candidatos_vencidos(cursor, CANDIDATO_INVITACION_HORAS)
    reactivadas = 0
    for sid in ids:
        _inv_repo.revocar_invitacion_conozco_por_solicitud(cursor, sid)
        reactivadas += _repo.revertir_candidato_a_pendiente(cursor, sid)
    return reactivadas


def _expirar_candidatos_vencidos_lazy(db, conn, cursor) -> int:
    _asegurar_migraciones_candidato(db, conn, cursor)
    return _expirar_candidatos_vencidos(db, cursor)


def _try_expirar_candidatos(db, conn, cursor) -> None:
    """La caducidad no puede tumbar el listado (bandeja vacía si Postgres rechaza el SQL)."""
    try:
        _expirar_candidatos_vencidos_lazy(db, conn, cursor)
        conn.commit()
    except Exception as exc:
        print(f"Error expirando candidatos pendientes: {exc}")
        try:
            conn.rollback()
        except Exception:
            pass


def expirar_candidatos_pendientes_vencidos(db) -> Dict[str, Any]:
    """Cron/lazy: caduca candidatos «Conozco a alguien» sin registro en plazo."""
    with db._lock:
        conn = None
        try:
            conn = db._connect()
            cursor = conn.cursor()
            n = _expirar_candidatos_vencidos_lazy(db, conn, cursor)
            conn.commit()
            return {"status": "success", "ok": True, "expiradas": n}
        except Exception as e:
            if conn:
                try:
                    conn.rollback()
                except Exception:
                    pass
            return {"status": "error", "message": str(e)}
        finally:
            if conn:
                conn.close()


def marcar_solicitud_candidato_pendiente(db, solicitud_id: int, codigo_proponente: str) -> Dict[str, Any]:
    """
    «Conozco a alguien»: la solicitud no se cierra; pasa a candidato_pendiente
    mientras el invitado no se registre.
    """
    with db._lock:
        try:
            conn = db._connect()
            cursor = conn.cursor()
            try:
                db._migrar_solicitudes_candidato(conn, cursor)
            except Exception:
                pass
            row = _repo.select_grupo_estado(cursor, int(solicitud_id))
            if not row:
                return {'status': 'error', 'message': 'Solicitud no encontrada'}
            grupo_id, estado = row[0], (row[1] or '').strip().lower()
            if estado != 'pendiente':
                return {
                    'status': 'error',
                    'message': 'La solicitud ya no está pendiente de candidato',
                }
            r2 = _repo.select_aliado_grupo_nombre(cursor, codigo_proponente.strip())
            if not r2:
                return {'status': 'error', 'message': 'Aliado no encontrado'}
            if r2[0] != grupo_id:
                return {
                    'status': 'error',
                    'message': 'Solo un aliado del mismo grupo puede proponer candidato',
                }
            nombre = r2[1] or ''
            rowcount = _repo.update_candidato_pendiente(
                cursor, int(solicitud_id), codigo_proponente.strip(), nombre
            )
            conn.commit()
            if rowcount == 0:
                return {
                    'status': 'error',
                    'message': 'La solicitud ya no está pendiente de candidato',
                }
            return {'status': 'success', 'ok': True, 'estado': 'candidato_pendiente'}
        except Exception as e:
            return {'status': 'error', 'message': str(e)}
        finally:
            try:
                conn.close()
            except Exception:
                pass


def vincular_solicitud_a_aliado_incorporado(db,
    codigo_invitacion: str,
    nuevo_aliado_codigo: str,
) -> Dict[str, Any]:
    """
    Tras registrarse con el código de «Conozco a alguien», vincula la solicitud
    al nuevo aliado, la deja disponible (pendiente) y le notifica.
    """
    codigo_invitacion = (codigo_invitacion or '').strip()
    nuevo_aliado_codigo = (nuevo_aliado_codigo or '').strip()
    if not codigo_invitacion or not nuevo_aliado_codigo:
        return {'status': 'error', 'message': 'Código requerido'}

    notif_payload = None
    with db._lock:
        conn = None
        try:
            conn = db._connect()
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            try:
                db._migrar_invitaciones_solicitud_id(conn, cursor)
                db._migrar_solicitudes_candidato(conn, cursor)
            except Exception:
                pass
            inv = _repo.select_invitacion_solicitud_id(cursor, codigo_invitacion)
            if not inv:
                return {'status': 'error', 'message': 'Invitación no encontrada'}
            solicitud_id = inv['solicitud_id'] if hasattr(inv, 'keys') else inv[0]
            if solicitud_id is None:
                return {'status': 'success', 'ok': True, 'vinculada': False}
            aliado = _repo.select_aliado_codigo_nombre(cursor, nuevo_aliado_codigo)
            if not aliado:
                return {'status': 'error', 'message': 'Aliado no encontrado'}
            nombre_nuevo = aliado['nombre'] if hasattr(aliado, 'keys') else aliado[1]
            sol = _repo.select_solicitud_basica(cursor, int(solicitud_id))
            if not sol:
                return {'status': 'error', 'message': 'Solicitud no encontrada'}
            estado = (sol['estado'] if hasattr(sol, 'keys') else sol[3] or '').strip().lower()
            oficio = (sol['oficio'] if hasattr(sol, 'keys') else sol[1]) or ''
            descripcion = (sol['descripcion'] if hasattr(sol, 'keys') else sol[2]) or ''
            if estado in ('candidato_pendiente', 'pendiente'):
                _repo.update_asignar_y_pendiente(
                    cursor, int(solicitud_id), nuevo_aliado_codigo, nombre_nuevo or ''
                )
            else:
                _repo.update_asignar_si_vacio(
                    cursor, int(solicitud_id), nuevo_aliado_codigo, nombre_nuevo or ''
                )
            conn.commit()
            oficio_txt = oficio.strip() or 'una solicitud'
            desc_corta = (descripcion or '').strip()
            if len(desc_corta) > 120:
                desc_corta = desc_corta[:117] + '…'
            mensaje = (
                f"Tienes una solicitud disponible para atender"
                f"{(' · ' + oficio_txt) if oficio_txt else ''}."
            )
            if desc_corta:
                mensaje += f" {desc_corta}"
            notif_payload = {
                'codigo': nuevo_aliado_codigo,
                'mensaje': mensaje,
                'solicitud_id': int(solicitud_id),
                'oficio': oficio,
            }
        except Exception as e:
            return {'status': 'error', 'message': str(e)}
        finally:
            if conn:
                conn.close()

    if notif_payload:
        db._crear_notificacion_aliado(
            notif_payload['codigo'],
            'solicitud_asignada',
            'Solicitud disponible',
            notif_payload['mensaje'],
            metadata={
                'solicitud_id': notif_payload['solicitud_id'],
                'oficio': notif_payload['oficio'],
                'origen': 'conozco_alguien',
            },
        )
        return {
            'status': 'success',
            'ok': True,
            'vinculada': True,
            'solicitud_id': notif_payload['solicitud_id'],
        }
    return {'status': 'success', 'ok': True, 'vinculada': False}


def crear_solicitud_por_codigo(db, codigo: str, oficio: str, descripcion: str) -> Dict[str, Any]:
    """
    Nueva conexión: primero el profesional del oficio en el grupo actual;
    si no hay, un único profesional más cercano al CP (pendiente de que el
    solicitante acepte o pida al grupo que recomiende a alguien);
    si no hay nadie, queda como «Buscando ayuda» y se avisa solo al grupo.
    Nunca se envía la solicitud a todos los aliados.
    """
    from core.services import proximidad_service

    notif_after: Optional[Dict[str, Any]] = None
    result: Optional[Dict[str, Any]] = None
    with db._lock:
        conn = None
        try:
            conn = db._connect()
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            _asegurar_migraciones_candidato(db, conn, cursor)
            conn.commit()
            ctx = _repo.select_aliado_contexto(cursor, codigo.strip())
            if not ctx:
                return {'status': 'error', 'message': 'Aliado no válido'}
            grupo_id, nombre = ctx["grupo_id"], ctx["nombre"]
            if grupo_id is None:
                return {'status': 'error', 'message': 'No perteneces a un grupo'}
            oficio = resolver_oficio_conexion(db, (oficio or '').strip())
            descripcion = (descripcion or '').strip()
            if not oficio:
                return {'status': 'error', 'message': 'Oficio requerido'}
            cols = _repo.columnas_solicitudes(cursor)
            if 'solicitante_codigo' not in cols:
                return {'status': 'error', 'message': 'Tabla solicitudes no migrada'}

            local = _buscar_profesional_grupo(
                db, cursor, grupo_id, oficio, codigo.strip()
            )
            if local and local.get("codigo"):
                sid = _repo.insertar_pendiente(
                    cursor,
                    grupo_id,
                    codigo.strip(),
                    nombre,
                    oficio,
                    descripcion,
                    asignada_a_codigo=local["codigo"],
                    asignada_a_nombre=local.get("nombre") or "",
                    destino=DESTINO_PROFESIONAL_GRUPO,
                )
                conn.commit()
                if not sid:
                    return {'status': 'error', 'message': 'No se pudo crear la solicitud'}
                sid = int(sid)
                notif_after = {
                    "kind": "profesional_grupo",
                    "codigo": local["codigo"],
                    "nombre_sol": nombre,
                    "oficio": oficio,
                    "sid": sid,
                }
                result = {
                    "status": "success",
                    "ok": True,
                    "id": sid,
                    "enrutamiento": DESTINO_PROFESIONAL_GRUPO,
                    "profesional": local,
                    "proximidad": None,
                    "proximidad_notificado": False,
                    "mensaje": f"Solicitud enviada a {local.get('nombre') or local['codigo']}.",
                }
            else:
                rec = proximidad_service.recomendar_profesional(
                    db,
                    codigo.strip(),
                    oficio,
                    cursor=cursor,
                    aliado={
                        "grupo_id": grupo_id,
                        "codigo_postal": ctx.get("codigo_postal") or "",
                    },
                )
                if rec and rec.get("codigo"):
                    sid = _repo.insertar_pendiente(
                        cursor,
                        grupo_id,
                        codigo.strip(),
                        nombre,
                        oficio,
                        descripcion,
                        destino=DESTINO_PROXIMIDAD,
                        proximidad_codigo=rec.get("codigo"),
                        proximidad_nombre=rec.get("nombre") or "",
                        proximidad_cp=rec.get("codigo_postal") or "",
                        proximidad_zona=rec.get("etiqueta_proximidad") or "",
                        proximidad_estado=PROXIMIDAD_PENDIENTE,
                    )
                    conn.commit()
                    result = {
                        "status": "success",
                        "ok": True,
                        "id": sid,
                        "enrutamiento": DESTINO_PROXIMIDAD,
                        "profesional": None,
                        "proximidad": rec,
                        "proximidad_notificado": False,
                        "requiere_aprobacion_proximidad": True,
                        "opciones_solicitante": {
                            "aceptar_proximidad": True,
                            "pedir_recomendacion_grupo": True,
                        },
                        "mensaje": mensaje_recomendacion_proximidad(oficio, rec),
                    }
                else:
                    sid = _repo.insertar_pendiente(
                        cursor,
                        grupo_id,
                        codigo.strip(),
                        nombre,
                        oficio,
                        descripcion,
                        destino=DESTINO_BUSCANDO_AYUDA,
                    )
                    conn.commit()
                    notif_after = {
                        "kind": "buscando",
                        "grupo_id": int(grupo_id),
                        "codigo": codigo.strip(),
                        "nombre_sol": nombre,
                        "oficio": oficio,
                        "sid": int(sid),
                    }
                    result = {
                        "status": "success",
                        "ok": True,
                        "id": sid,
                        "enrutamiento": DESTINO_BUSCANDO_AYUDA,
                        "profesional": None,
                        "proximidad": None,
                        "proximidad_notificado": False,
                        "mensaje": (
                            f"No hay {_etiqueta_oficio_humano(oficio)} en tu grupo ni cerca. "
                            "Tu solicitud queda como Buscando ayuda."
                        ),
                    }
        except Exception as e:
            return {'status': 'error', 'message': str(e)}
        finally:
            if conn:
                conn.close()

    if notif_after:
        if notif_after["kind"] == "profesional_grupo":
            _notificar_profesional_solicitud(
                db,
                notif_after["codigo"],
                notif_after["nombre_sol"],
                notif_after["oficio"],
                notif_after["sid"],
            )
        elif notif_after["kind"] == "buscando":
            _notificar_grupo_buscando_ayuda(
                db,
                notif_after["grupo_id"],
                notif_after["codigo"],
                notif_after["nombre_sol"],
                notif_after["oficio"],
                notif_after["sid"],
            )
    return result or {"status": "error", "message": "No se pudo crear la solicitud"}


def aceptar_proximidad_solicitud(db, solicitud_id: int, codigo: str) -> Dict[str, Any]:
    """El solicitante acepta al profesional cercano recomendado."""
    from core.services import proximidad_service

    notif_after: Optional[Dict[str, Any]] = None
    result: Optional[Dict[str, Any]] = None
    with db._lock:
        conn = None
        try:
            conn = db._connect()
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            _asegurar_migraciones_candidato(db, conn, cursor)
            sol = _repo.select_enrutamiento(cursor, int(solicitud_id))
            if not sol:
                return {"status": "error", "message": "Solicitud no encontrada"}
            if (sol.get("solicitante_codigo") or "").strip() != (codigo or "").strip():
                return {"status": "error", "message": "Solo el solicitante puede aceptar esta recomendación"}
            if (sol.get("estado") or "") != "pendiente":
                return {"status": "error", "message": "La solicitud ya no está pendiente"}
            if (sol.get("proximidad_estado") or "") != PROXIMIDAD_PENDIENTE:
                return {"status": "error", "message": "No hay un profesional cercano pendiente de aprobación"}
            prof_codigo = (sol.get("proximidad_codigo") or "").strip()
            prof_nombre = (sol.get("proximidad_nombre") or "").strip()
            if not prof_codigo:
                return {"status": "error", "message": "Recomendación no válida"}
            rc = _repo.aceptar_proximidad(cursor, int(solicitud_id), prof_codigo, prof_nombre)
            if rc == 0:
                return {"status": "error", "message": "No se pudo aceptar la recomendación"}
            conn.commit()
            notif_after = {
                "grupo_id": int(sol["grupo_id"]),
                "solicitante_codigo": (codigo or "").strip(),
                "solicitante_nombre": sol.get("solicitante_nombre") or "",
                "profesional_codigo": prof_codigo,
                "profesional_nombre": prof_nombre,
                "oficio": sol.get("oficio") or "",
                "sid": int(solicitud_id),
            }
            result = {
                "status": "success",
                "ok": True,
                "id": int(solicitud_id),
                "enrutamiento": DESTINO_PROXIMIDAD,
                "proximidad_notificado": True,
                "profesional": {
                    "codigo": prof_codigo,
                    "nombre": prof_nombre,
                    "mismo_grupo": False,
                },
                "mensaje": f"Contactaste a {prof_nombre or prof_codigo}.",
            }
        except Exception as e:
            return {"status": "error", "message": str(e)}
        finally:
            if conn:
                conn.close()

    if notif_after:
        of = notif_after["oficio"]
        prox = proximidad_service.solicitar_contacto_proximidad(
            db,
            notif_after["solicitante_codigo"],
            of,
            notif_after["profesional_codigo"],
        )
        if result is not None:
            result["proximidad_notificado"] = bool(prox.get("notificado"))
            result["proximidad"] = prox.get("proximidad")
        _notificar_grupo_profesional_contactado(
            db,
            notif_after["grupo_id"],
            notif_after["solicitante_codigo"],
            notif_after["solicitante_nombre"],
            notif_after["profesional_codigo"],
            notif_after["profesional_nombre"],
            of,
            notif_after["sid"],
        )
    return result or {"status": "error", "message": "No se pudo aceptar la recomendación"}


def pedir_recomendacion_grupo_solicitud(db, solicitud_id: int, codigo: str) -> Dict[str, Any]:
    """El solicitante rechaza al cercano y pide recomendación al grupo (Conozco a alguien)."""
    notif_after: Optional[Dict[str, Any]] = None
    result: Optional[Dict[str, Any]] = None
    with db._lock:
        conn = None
        try:
            conn = db._connect()
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            _asegurar_migraciones_candidato(db, conn, cursor)
            sol = _repo.select_enrutamiento(cursor, int(solicitud_id))
            if not sol:
                return {"status": "error", "message": "Solicitud no encontrada"}
            if (sol.get("solicitante_codigo") or "").strip() != (codigo or "").strip():
                return {"status": "error", "message": "Solo el solicitante puede pedir recomendación al grupo"}
            if (sol.get("estado") or "") != "pendiente":
                return {"status": "error", "message": "La solicitud ya no está pendiente"}
            if (sol.get("proximidad_estado") or "") != PROXIMIDAD_PENDIENTE:
                return {"status": "error", "message": "Esta solicitud no tiene una recomendación pendiente"}
            rc = _repo.pedir_recomendacion_grupo(cursor, int(solicitud_id))
            if rc == 0:
                return {"status": "error", "message": "No se pudo pedir recomendación al grupo"}
            conn.commit()
            notif_after = {
                "grupo_id": int(sol["grupo_id"]),
                "codigo": (codigo or "").strip(),
                "nombre_sol": sol.get("solicitante_nombre") or "",
                "oficio": sol.get("oficio") or "",
                "sid": int(solicitud_id),
            }
            result = {
                "status": "success",
                "ok": True,
                "id": int(solicitud_id),
                "enrutamiento": DESTINO_BUSCANDO_AYUDA,
                "mensaje": (
                    "Buscando ayuda. Tu grupo puede recomendar a alguien que entre al grupo."
                ),
            }
        except Exception as e:
            return {"status": "error", "message": str(e)}
        finally:
            if conn:
                conn.close()

    if notif_after:
        _notificar_grupo_buscando_ayuda(
            db,
            notif_after["grupo_id"],
            notif_after["codigo"],
            notif_after["nombre_sol"],
            notif_after["oficio"],
            notif_after["sid"],
        )
    return result or {"status": "error", "message": "No se pudo pedir recomendación al grupo"}


def listar_solicitudes_activas_por_codigo(db, codigo: str) -> List[Dict[str, Any]]:
    """Solo mismo grupo, estado pendiente, excluye las propias. GET /api/solicitudes?codigo=.
    También incluye solicitudes pendientes asignadas a este aliado (p. ej. tras «Conozco a alguien»).
    """
    with db._lock:
        try:
            conn = db._connect()
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            codigo = str(codigo or "").strip()
            _try_expirar_candidatos(db, conn, cursor)
            aliado = _repo.select_aliado_grupo_nombre(cursor, codigo)
            if not aliado:
                return []
            grupo_id = aliado[0]
            cols = _repo.columnas_solicitudes(cursor)
            if 'solicitante_codigo' not in cols:
                return []
            has_asignada = 'asignada_a_codigo' in cols
            if grupo_id is None and not has_asignada:
                return []
            if grupo_id is not None and has_asignada:
                return _json_safe_rows(_repo.listar_activas_grupo_o_asignada(cursor, codigo, grupo_id))
            elif grupo_id is not None:
                return _json_safe_rows(_repo.listar_activas_grupo(cursor, codigo, grupo_id))
            else:
                return _json_safe_rows(_repo.listar_activas_asignadas(cursor, codigo))
        except Exception as e:
            print(f"Error listar_solicitudes_activas_por_codigo: {e}")
            return []
        finally:
            conn.close()


def listar_solicitudes_propias_por_codigo(db, codigo: str) -> List[Dict[str, Any]]:
    """Solicitudes creadas por el aliado (sus propias solicitudes). Mismo grupo, cualquier estado (pendiente/atendida)."""
    with db._lock:
        try:
            conn = db._connect()
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            _try_expirar_candidatos(db, conn, cursor)
            aliado = _repo.select_aliado_grupo_nombre(cursor, str(codigo or "").strip())
            if not aliado or aliado[0] is None:
                return []
            grupo_id = aliado[0]
            cols = _repo.columnas_solicitudes(cursor)
            if 'solicitante_codigo' not in cols:
                return []
            extra = _extra_cols_candidato_asignada(cols)
            return [_enriquecer_propia(r) for r in _json_safe_rows(_repo.listar_propias(cursor, grupo_id, str(codigo or "").strip(), extra))]
        except Exception as e:
            print(f"Error listar_solicitudes_propias_por_codigo: {e}")
            return []
        finally:
            conn.close()


def listar_solicitudes_historial_grupo_por_codigo(db, codigo: str, limite: int = 50) -> List[Dict[str, Any]]:
    """Historial del grupo: atendidas, candidato pendiente y estados cerrados (sin pendientes activas)."""
    with db._lock:
        try:
            conn = db._connect()
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            _try_expirar_candidatos(db, conn, cursor)
            aliado = _repo.select_aliado_grupo_nombre(cursor, str(codigo or "").strip())
            if not aliado or aliado[0] is None:
                return []
            grupo_id = aliado[0]
            cols = _repo.columnas_solicitudes(cursor)
            if 'solicitante_codigo' not in cols:
                return []
            extra = _extra_cols_candidato_asignada(cols)
            return _json_safe_rows(_repo.listar_historial_grupo(cursor, grupo_id, limite, extra))
        except Exception as e:
            print(f"Error listar_solicitudes_historial_grupo_por_codigo: {e}")
            return []
        finally:
            conn.close()


def obtener_solicitudes_grupo(db, codigo_postal: str) -> List[Dict[str, Any]]:
    """Obtiene solicitudes pendientes de todos los grupos territoriales activos en el CP."""
    if not codigo_postal or not str(codigo_postal).strip():
        return []
    with db._lock:
        try:
            conn = db._connect()
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            _try_expirar_candidatos(db, conn, cursor)
            cols = _repo.columnas_solicitudes(cursor)
            if 'solicitante_codigo' not in cols:
                return []
            return _json_safe_rows(_repo.listar_pendientes_por_cp(cursor, codigo_postal.strip()))
        except Exception as e:
            return []
        finally:
            conn.close()


def obtener_solicitudes_operativas(db, codigo_aliado: str) -> List[Dict[str, Any]]:
    """Solicitudes visibles del código postal del aliado (grupo territorial)."""
    aliado = db.obtener_aliado_por_codigo((codigo_aliado or '').strip())
    if not aliado:
        return []
    cp = (aliado.get('codigo_postal') or '').strip()
    return obtener_solicitudes_grupo(db, cp)


def atender_solicitud_por_id(db, solicitud_id: int, codigo: str) -> Dict[str, Any]:
    """Marca solicitud como atendida. Mismo grupo o profesional asignado (p. ej. proximidad)."""
    with db._lock:
        try:
            conn = db._connect()
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            _asegurar_migraciones_candidato(db, conn, cursor)
            sol = _repo.select_enrutamiento(cursor, solicitud_id)
            if not sol:
                return {'status': 'error', 'message': 'Solicitud no encontrada'}
            grupo_id, estado = sol.get("grupo_id"), sol.get("estado")
            if estado != 'pendiente':
                return {'status': 'error', 'message': 'La solicitud ya fue atendida'}
            r2 = _repo.select_aliado_grupo_nombre(cursor, codigo.strip())
            if not r2:
                return {'status': 'error', 'message': 'Aliado no encontrado'}
            asignada = (sol.get("asignada_a_codigo") or "").strip()
            mismo_grupo = r2[0] == grupo_id
            es_asignado = asignada == codigo.strip()
            if not mismo_grupo and not es_asignado:
                return {'status': 'error', 'message': 'Solo el profesional asignado o un aliado del grupo puede atender'}
            if asignada and not es_asignado and (sol.get("destino") or "") != DESTINO_BUSCANDO_AYUDA:
                return {'status': 'error', 'message': 'Esta solicitud ya está asignada a otro profesional'}
            nombre_atendido = r2[1] or ''
            rowcount = _repo.update_atendida(
                cursor, solicitud_id, codigo.strip(), nombre_atendido
            )
            conn.commit()
            if rowcount == 0:
                return {'status': 'error', 'message': 'La solicitud ya fue atendida'}
            return {'status': 'success', 'ok': True}
        except Exception as e:
            return {'status': 'error', 'message': str(e)}
        finally:
            conn.close()


def marcar_solicitud_atendida_por_admin(db, solicitud_id: int, admin_codigo: str) -> Dict[str, Any]:
    """Marca la solicitud como atendida y registra al admin como 'Atendido por' y 'Atendido at'. Si ya estaba atendida pero con columnas vacías, las rellena."""
    with db._lock:
        try:
            conn = db._connect()
            cursor = conn.cursor()
            cols = _repo.columnas_solicitudes(cursor)
            if 'atendido_por_codigo' not in cols or 'atendido_at' not in cols:
                return {'status': 'error', 'message': 'Tabla solicitudes sin columnas atendido_por/atendido_at'}
            row = _repo.select_atendido_info(cursor, solicitud_id)
            if not row:
                return {'status': 'error', 'message': 'Solicitud no encontrada'}
            estado = row[1]
            atendido_por = row[2]
            atendido_at = row[3]
            nombre_admin = (admin_codigo or '').strip() or 'Admin'
            codigo_str = (admin_codigo or '').strip()
            if estado == 'pendiente':
                _repo.update_atendida_admin(cursor, solicitud_id, codigo_str, nombre_admin)
            elif not atendido_por and not atendido_at:
                _repo.update_rellenar_atendido_admin(cursor, solicitud_id, codigo_str, nombre_admin)
            else:
                return {'status': 'success', 'ok': True}
            conn.commit()
            return {'status': 'success', 'ok': True}
        except Exception as e:
            return {'status': 'error', 'message': str(e)}
        finally:
            conn.close()


def marcar_solicitud_contestada(db, solicitud_id: int, invitador_aliado_id: Optional[int] = None) -> None:
    """Marca la solicitud como atendida/contestada (p. ej. desde 'Conozco a alguien'). Opcional: invitador_aliado_id para registrar quién contestó."""
    with db._lock:
        try:
            conn = db._connect()
            cursor = conn.cursor()
            cols = _repo.columnas_solicitudes(cursor)
            if 'solicitante_codigo' not in cols:
                return
            codigo_atendido = None
            nombre_atendido = None
            if invitador_aliado_id is not None:
                row = _repo.select_aliado_codigo_nombre_por_id(cursor, int(invitador_aliado_id))
                if row:
                    codigo_atendido, nombre_atendido = row[0], row[1] or ''
            if codigo_atendido is None:
                codigo_atendido = ''
                nombre_atendido = ''
            _repo.update_atendida(cursor, solicitud_id, codigo_atendido, nombre_atendido)
            conn.commit()
        except Exception:
            pass
        finally:
            conn.close()


def listar_solicitudes_admin_todas(db) -> List[Dict[str, Any]]:
    """Todas las solicitudes para el panel admin. Orden created_at DESC."""
    with db._lock:
        try:
            conn = db._connect()
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cols = _repo.columnas_solicitudes(cursor)
            if 'solicitante_codigo' not in cols:
                return []
            return _json_safe_rows(_repo.listar_admin_todas(cursor))
        except Exception as e:
            return []
        finally:
            conn.close()


def contar_solicitudes_activas(db) -> int:
    """Cuenta solicitudes en estado pendiente (activas)."""
    with db._lock:
        try:
            conn = db._connect()
            cursor = conn.cursor()
            return _repo.contar_pendientes(cursor)
        except Exception:
            return 0
        finally:
            conn.close()


def contar_solicitudes_enviadas_contestadas(db, codigo: str) -> int:
    """Cuenta solicitudes enviadas por el aliado (solicitante) que fueron atendidas/contestadas."""
    if not codigo or not str(codigo).strip():
        return 0
    with db._lock:
        try:
            conn = db._connect()
            cursor = conn.cursor()
            cols = _repo.columnas_solicitudes(cursor)
            if 'solicitante_codigo' not in cols:
                return 0
            estado_atendida = "atendida" if 'atendido_por_codigo' in cols else "contestada"
            return _repo.contar_enviadas_por_estado(cursor, codigo.strip(), estado_atendida)
        except Exception:
            return 0
        finally:
            conn.close()
