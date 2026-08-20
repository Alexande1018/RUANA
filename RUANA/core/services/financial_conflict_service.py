"""Servicio formal de conflictos financieros (FASE 04)."""
from __future__ import annotations

import sqlite3
from typing import Any, Dict, Optional, Tuple

from core.financial.conflict_estados import (
    EstadoConflicto,
    ResolucionConflicto,
    TipoConflicto,
    normalizar_estado_conflicto,
)
from core.financial.conflict_state_machine import ConflictStateMachine
from core.financial.estados import EstadoFinanciero
from core.financial.money import cents_a_importe_bd, importe_bd_a_cents
from core.financial.state_machine import TransicionBloqueadaError, TransicionInvalidaError
from core.repositories.financial_conflict_repo import FinancialConflictRepo
from core.repositories.financial_transaction_repo import FinancialTransactionRepo
from core.repositories.financial_transfer_repo import FinancialTransferRepo
from core.repositories.pago_repo import PagoRepo
from core.services import financial_transaction_service as fts

_repo = FinancialConflictRepo()
_pago_repo = PagoRepo()
_fin_repo = FinancialTransactionRepo()
_transfer_repo = FinancialTransferRepo()
_sm = ConflictStateMachine()


def bloquea_operaciones_financieras(db, contacto_id: int, cursor=None) -> Tuple[bool, str]:
    """
    Comprobación central única: ¿hay conflicto o disputa que bloquee operaciones?

    Returns:
        (bloquea, motivo)
    """
    from core.services import financial_dispute_service as fds

    if cursor is not None:
        if _repo.tiene_conflicto_bloqueante(cursor, contacto_id):
            return True, "conflicto_abierto"
        if fds.tiene_disputa_bloqueante(db, contacto_id, cursor=cursor):
            return True, "disputa_stripe"
        return False, ""

    with db._lock:
        conn = db._connect()
        try:
            cur = conn.cursor()
            if _repo.tiene_conflicto_bloqueante(cur, contacto_id):
                return True, "conflicto_abierto"
            if fds.tiene_disputa_bloqueante(db, contacto_id, cursor=cur):
                return True, "disputa_stripe"
            return False, ""
        finally:
            conn.close()


def abrir_conflicto(
    db,
    contacto_id: int,
    *,
    tipo: TipoConflicto,
    motivo: str,
    abierto_por: str,
    importe_reclamado_cents: int = 0,
    idempotency_key: str = "",
    sincronizar_estado_financiero: bool = True,
) -> Dict[str, Any]:
    """Abre conflicto formal. Idempotente por idempotency_key de apertura."""
    motivo = (motivo or "").strip()
    if not motivo:
        return {"status": "error", "message": "motivo obligatorio"}
    key = idempotency_key or f"abrir-conflicto-{contacto_id}-{tipo.value}"

    with db._lock:
        conn = None
        try:
            conn = db._connect()
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            existente = _repo.select_activo_por_contacto(cursor, contacto_id)
            if existente:
                ec = normalizar_estado_conflicto(
                    existente.get("estado_conflicto"), existente.get("estado")
                )
                if ec and EstadoConflicto.bloquea_financiero(ec):
                    return {
                        "status": "success", "idempotent": True,
                        "conflict_id": existente["id"], "estado_conflicto": ec.value,
                    }

            row = _pago_repo.select_contacto_stripe_por_id(cursor, contacto_id)
            if not row:
                row = _pago_repo.select_contacto_partes(cursor, contacto_id)
            if not row:
                return {"status": "error", "message": "Contacto no encontrado"}
            contacto = dict(row)
            sol_id = _pago_repo.select_aliado_id_por_codigo(
                cursor, str(contacto.get("solicitante_codigo") or "").strip()
            )
            prof_id = _pago_repo.select_aliado_id_por_codigo(
                cursor, str(contacto.get("profesional_codigo") or "").strip()
            )
            if sol_id is None or prof_id is None:
                return {"status": "error", "message": "Partes no identificadas"}

            imp_con = cents_a_importe_bd(
                importe_bd_a_cents(contacto.get("importe_final") or contacto.get("importe_acordado"))
            )
            imp_prof = cents_a_importe_bd(
                importe_bd_a_cents(contacto.get("importe_neto_profesional") or imp_con)
            )
            if not importe_reclamado_cents:
                importe_reclamado_cents = importe_bd_a_cents(
                    contacto.get("importe_neto_profesional") or contacto.get("importe_final") or imp_con
                )

            claim, conflicto = _repo.insertar_conflicto(
                cursor,
                contacto_id=contacto_id,
                contratante_id=sol_id,
                profesional_id=prof_id,
                tipo=tipo,
                motivo=motivo,
                abierto_por=abierto_por,
                importe_reclamado_cents=importe_reclamado_cents,
                importe_contratante=imp_con,
                importe_profesional=imp_prof,
                idempotency_key=key,
                stripe_payment_intent_id=str(contacto.get("stripe_payment_intent_id") or ""),
            )
            if not conflicto:
                return {"status": "error", "message": "No se pudo crear conflicto"}

            cid = conflicto["id"]
            _repo.registrar_auditoria(
                cursor, cid, accion="abrir", actor=abierto_por,
                estado_anterior="", estado_nuevo=EstadoConflicto.ABIERTO.value,
                metadata={"tipo": tipo.value, "idempotency_key": key},
            )
            _alertar_conflicto_durante_transferencia(db, cursor, contacto_id, cid, abierto_por)

            if sincronizar_estado_financiero:
                estado = fts.obtener_estado_financiero(db, contacto_id)
                if estado and estado != EstadoFinanciero.CONFLICTO_ABIERTO:
                    if estado not in (EstadoFinanciero.TRANSFERIDO, EstadoFinanciero.TRANSFERENCIA_REVERTIDA):
                        try:
                            fts._transicionar_en_cursor(
                                db, cursor, contacto_id, EstadoFinanciero.CONFLICTO_ABIERTO,
                                actor_tipo="conflicto", actor_codigo=abierto_por,
                                motivo=f"conflicto abierto: {tipo.value}",
                            )
                        except (TransicionInvalidaError, TransicionBloqueadaError):
                            pass

            conn.commit()
            return {
                "status": "success",
                "idempotent": claim == "existing",
                "conflict_id": cid,
                "estado_conflicto": EstadoConflicto.ABIERTO.value,
                "bloqueo_financiero": True,
            }
        except Exception as e:
            if conn:
                conn.rollback()
            return {"status": "error", "message": str(e)}
        finally:
            if conn:
                conn.close()


def _error_version() -> Dict[str, Any]:
    return {
        "status": "error",
        "code": "version_conflict",
        "message": "Conflicto modificado por otro proceso",
    }


def _validar_version_fila(row: Dict[str, Any], version_esperada: Optional[int]) -> Optional[Dict[str, Any]]:
    if version_esperada is None:
        return None
    actual = int(row.get("version") or 1)
    if int(version_esperada) != actual:
        return _error_version()
    return None


def listar_conflictos(
    db,
    *,
    estado: str = "",
    limite: int = 100,
    offset: int = 0,
) -> Dict[str, Any]:
    with db._lock:
        conn = db._connect()
        try:
            cursor = conn.cursor()
            items = _repo.listar_conflictos(cursor, estado=estado, limite=limite, offset=offset)
            return {"status": "success", "conflictos": items, "total": len(items)}
        finally:
            conn.close()


def obtener_detalle(db, conflict_id: int) -> Dict[str, Any]:
    with db._lock:
        conn = db._connect()
        try:
            cursor = conn.cursor()
            detalle = _repo.obtener_detalle_completo(cursor, conflict_id)
            if not detalle:
                return {"status": "error", "message": "Conflicto no encontrado"}
            return {"status": "success", "conflicto": detalle}
        finally:
            conn.close()


def listar_auditoria(db, conflict_id: int) -> Dict[str, Any]:
    with db._lock:
        conn = db._connect()
        try:
            cursor = conn.cursor()
            if not _repo.select_por_id(cursor, conflict_id):
                return {"status": "error", "message": "Conflicto no encontrado"}
            items = _repo.listar_auditoria(cursor, conflict_id)
            return {"status": "success", "auditoria": items, "total": len(items)}
        finally:
            conn.close()


def listar_acciones_financieras_pendientes(db, conflict_id: int) -> Dict[str, Any]:
    with db._lock:
        conn = db._connect()
        try:
            cursor = conn.cursor()
            if not _repo.select_por_id(cursor, conflict_id):
                return {"status": "error", "message": "Conflicto no encontrado"}
            items = _repo.listar_acciones_pendientes(cursor, conflict_id)
            return {"status": "success", "acciones": items, "total": len(items)}
        finally:
            conn.close()


def asignar_responsable(
    db,
    conflict_id: int,
    *,
    responsable_codigo: str,
    actor: str,
    idempotency_key: str = "",
    version_esperada: Optional[int] = None,
    permiso_usado: str = "",
) -> Dict[str, Any]:
    responsable = (responsable_codigo or "").strip()
    if not responsable:
        return {"status": "error", "message": "responsable_codigo obligatorio"}
    key = idempotency_key or f"asignar-{conflict_id}-{responsable}"
    with db._lock:
        conn = None
        try:
            conn = db._connect()
            cursor = conn.cursor()
            row = _repo.select_por_id(cursor, conflict_id)
            if not row:
                return {"status": "error", "message": "Conflicto no encontrado"}
            verr = _validar_version_fila(row, version_esperada)
            if verr:
                return verr
            claim, action_id = _repo.reclamar_accion(cursor, conflict_id, "asignar", key, actor)
            if claim == "duplicate":
                return {"status": "success", "idempotent": True, "conflict_id": conflict_id}
            actual = normalizar_estado_conflicto(row.get("estado_conflicto"), row.get("estado"))
            if not actual:
                return {"status": "error", "message": "Estado de conflicto inválido"}
            version = int(row.get("version") or 1)
            ok = _repo.asignar_responsable_cas(
                cursor, conflict_id,
                responsable_codigo=responsable,
                estado_esperado=actual.value,
                version_esperada=version,
            )
            if not ok:
                _repo.finalizar_accion(cursor, action_id, "conflicto_version", {})
                conn.commit()
                return _error_version()
            _repo.registrar_auditoria(
                cursor, conflict_id, accion="asignar_responsable", actor=actor,
                estado_anterior=actual.value, estado_nuevo=actual.value,
                metadata={
                    "responsable_codigo": responsable,
                    "permiso_usado": permiso_usado,
                },
            )
            _repo.finalizar_accion(cursor, action_id, "ok", {"responsable": responsable})
            conn.commit()
            return {
                "status": "success",
                "conflict_id": conflict_id,
                "responsable_codigo": responsable,
                "version": version + 1,
            }
        except Exception as e:
            if conn:
                conn.rollback()
            return {"status": "error", "message": str(e)}
        finally:
            if conn:
                conn.close()


def solicitar_evidencia(
    db,
    conflict_id: int,
    *,
    actor: str,
    idempotency_key: str = "",
    version_esperada: Optional[int] = None,
    permiso_usado: str = "",
    motivo: str = "",
) -> Dict[str, Any]:
    row_pre = None
    with db._lock:
        conn = db._connect()
        try:
            cursor = conn.cursor()
            row_pre = _repo.select_por_id(cursor, conflict_id)
        finally:
            conn.close()
    if not row_pre:
        return {"status": "error", "message": "Conflicto no encontrado"}
    verr = _validar_version_fila(row_pre, version_esperada)
    if verr:
        return verr
    result = transicionar_conflicto(
        db, conflict_id, EstadoConflicto.PENDIENTE_DE_EVIDENCIA,
        actor=actor, idempotency_key=idempotency_key or f"solicitar-evidencia-{conflict_id}",
    )
    if result.get("status") == "success":
        with db._lock:
            conn = db._connect()
            try:
                cursor = conn.cursor()
                _repo.registrar_auditoria(
                    cursor, conflict_id, accion="solicitar_evidencia", actor=actor,
                    estado_anterior=row_pre.get("estado_conflicto", ""),
                    estado_nuevo=EstadoConflicto.PENDIENTE_DE_EVIDENCIA.value,
                    metadata={"permiso_usado": permiso_usado, "motivo": (motivo or "")[:500]},
                )
                conn.commit()
            finally:
                conn.close()
    return result


def escalar_conflicto(
    db,
    conflict_id: int,
    *,
    actor: str,
    responsable_codigo: str,
    comentario: str,
    idempotency_key: str = "",
    version_esperada: Optional[int] = None,
    permiso_usado: str = "",
) -> Dict[str, Any]:
    row_pre = None
    with db._lock:
        conn = db._connect()
        try:
            cursor = conn.cursor()
            row_pre = _repo.select_por_id(cursor, conflict_id)
        finally:
            conn.close()
    if not row_pre:
        return {"status": "error", "message": "Conflicto no encontrado"}
    verr = _validar_version_fila(row_pre, version_esperada)
    if verr:
        return verr
    result = resolver_conflicto(
        db, conflict_id, ResolucionConflicto.ESCALAR_ADMIN,
        actor=actor,
        responsable_codigo=responsable_codigo,
        comentario=comentario,
        motivo=comentario,
        idempotency_key=idempotency_key or f"escalar-{conflict_id}",
    )
    if result.get("status") == "success":
        with db._lock:
            conn = db._connect()
            try:
                cursor = conn.cursor()
                _repo.registrar_auditoria(
                    cursor, conflict_id, accion="escalar", actor=actor,
                    estado_anterior=row_pre.get("estado_conflicto", ""),
                    estado_nuevo=EstadoConflicto.ESCALADO.value,
                    metadata={"permiso_usado": permiso_usado, "responsable_codigo": responsable_codigo},
                )
                conn.commit()
            finally:
                conn.close()
    return result


def transicionar_conflicto(
    db,
    conflict_id: int,
    nuevo_estado: EstadoConflicto,
    *,
    actor: str,
    idempotency_key: str = "",
    version_esperada: Optional[int] = None,
) -> Dict[str, Any]:
    key = idempotency_key or f"trans-{conflict_id}-{nuevo_estado.value}"
    with db._lock:
        conn = None
        try:
            conn = db._connect()
            cursor = conn.cursor()
            row = _repo.select_por_id(cursor, conflict_id)
            if not row:
                return {"status": "error", "message": "Conflicto no encontrado"}
            verr = _validar_version_fila(row, version_esperada)
            if verr:
                return verr
            actual = normalizar_estado_conflicto(row.get("estado_conflicto"), row.get("estado"))
            if not actual:
                return {"status": "error", "message": "Estado de conflicto inválido"}
            claim, action_id = _repo.reclamar_accion(cursor, conflict_id, "transicion", key, actor)
            if claim == "duplicate":
                return {"status": "success", "idempotent": True, "conflict_id": conflict_id}
            try:
                _sm.validar_transicion(actual, nuevo_estado)
            except Exception as e:
                _repo.finalizar_accion(cursor, action_id, "rechazado", {"error": str(e)})
                conn.commit()
                return {"status": "error", "message": str(e)}
            version = int(row.get("version") or 1)
            ok = _repo.transicionar_estado_cas(
                cursor, conflict_id, actual.value, nuevo_estado.value,
                responsable_codigo=actor if nuevo_estado == EstadoConflicto.ESCALADO else "",
                version_esperada=version,
            )
            if not ok:
                _repo.finalizar_accion(cursor, action_id, "conflicto_version", {})
                conn.commit()
                return _error_version()
            _repo.registrar_auditoria(
                cursor, conflict_id, accion="transicion", actor=actor,
                estado_anterior=actual.value, estado_nuevo=nuevo_estado.value,
            )
            _repo.finalizar_accion(cursor, action_id, "ok", {"estado": nuevo_estado.value})
            conn.commit()
            return {"status": "success", "conflict_id": conflict_id, "estado_conflicto": nuevo_estado.value}
        except Exception as e:
            if conn:
                conn.rollback()
            return {"status": "error", "message": str(e)}
        finally:
            if conn:
                conn.close()


def resolver_conflicto(
    db,
    conflict_id: int,
    resolucion: ResolucionConflicto,
    *,
    actor: str,
    idempotency_key: str = "",
    importe_liberar_cents: int = 0,
    importe_reembolsar_cents: int = 0,
    importe_profesional_cents: int = 0,
    importe_contratante_cents: int = 0,
    motivo: str = "",
    responsable_codigo: str = "",
    comentario: str = "",
    version_esperada: Optional[int] = None,
    permiso_usado: str = "",
) -> Dict[str, Any]:
    key = idempotency_key or f"resolver-{conflict_id}-{resolucion.value}"
    validacion = _validar_resolucion(
        resolucion,
        importe_liberar_cents=importe_liberar_cents,
        importe_reembolsar_cents=importe_reembolsar_cents,
        importe_profesional_cents=importe_profesional_cents,
        importe_contratante_cents=importe_contratante_cents,
        responsable_codigo=responsable_codigo,
        comentario=comentario,
        motivo=motivo,
    )
    if validacion:
        return validacion

    with db._lock:
        conn = None
        try:
            conn = db._connect()
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            row = _repo.select_por_id(cursor, conflict_id)
            if not row:
                return {"status": "error", "message": "Conflicto no encontrado"}
            verr = _validar_version_fila(row, version_esperada)
            if verr:
                return verr

            claim, action_id = _repo.reclamar_accion(cursor, conflict_id, "resolver", key, actor)
            if claim == "duplicate":
                row_now = _repo.select_por_id(cursor, conflict_id)
                ec = normalizar_estado_conflicto(
                    (row_now or {}).get("estado_conflicto"), (row_now or {}).get("estado")
                )
                if ec in (EstadoConflicto.RESUELTO, EstadoConflicto.CERRADO):
                    return {
                        "status": "success", "idempotent": True,
                        "conflict_id": conflict_id, "estado_conflicto": ec.value,
                    }
                return {"status": "success", "idempotent": True, "conflict_id": conflict_id}

            actual = normalizar_estado_conflicto(row.get("estado_conflicto"), row.get("estado"))
            if not actual or actual in (EstadoConflicto.CERRADO, EstadoConflicto.RESUELTO):
                _repo.finalizar_accion(cursor, action_id, "rechazado", {"error": "ya resuelto"})
                conn.commit()
                return {"status": "error", "message": "Conflicto ya resuelto o cerrado"}
            if actual not in (
                EstadoConflicto.ABIERTO, EstadoConflicto.EN_INVESTIGACION,
                EstadoConflicto.PENDIENTE_DE_EVIDENCIA, EstadoConflicto.ESCALADO,
            ):
                _repo.finalizar_accion(cursor, action_id, "rechazado", {"error": "estado invalido"})
                conn.commit()
                return {"status": "error", "message": "Estado no permite resolución"}

            contacto_id = int(row["trabajo_id"])
            val_importe = _validar_importes_resolucion(
                cursor, contacto_id, resolucion,
                importe_liberar_cents, importe_reembolsar_cents,
                importe_profesional_cents, importe_contratante_cents,
            )
            if val_importe:
                _repo.finalizar_accion(cursor, action_id, "rechazado", val_importe)
                conn.commit()
                return val_importe

            estado_res = _sm.estado_tras_resolucion(resolucion)
            version = int(row.get("version") or 1)
            ok = _repo.aplicar_resolucion_cas(
                cursor, conflict_id,
                estado_esperado=actual.value,
                estado_nuevo=estado_res.value,
                resolucion=resolucion.value,
                version_esperada=version,
                importe_liberar_cents=importe_liberar_cents,
                importe_reembolsar_cents=importe_reembolsar_cents,
                importe_profesional_cents=importe_profesional_cents,
                importe_contratante_cents=importe_contratante_cents,
                comentario=comentario or motivo,
            )
            if not ok:
                _repo.finalizar_accion(cursor, action_id, "conflicto_version", {})
                conn.commit()
                return _error_version()

            if resolucion == ResolucionConflicto.ESCALAR_ADMIN and responsable_codigo:
                _repo.transicionar_estado_cas(
                    cursor, conflict_id, EstadoConflicto.ESCALADO.value,
                    EstadoConflicto.ESCALADO.value,
                    responsable_codigo=responsable_codigo,
                    version_esperada=version + 1,
                )

            _repo.registrar_auditoria(
                cursor, conflict_id, accion="resolver", actor=actor,
                estado_anterior=actual.value, estado_nuevo=estado_res.value,
                metadata={
                    "resolucion": resolucion.value,
                    "importe_liberar_cents": importe_liberar_cents,
                    "importe_reembolsar_cents": importe_reembolsar_cents,
                    "orden_financiera_pendiente": True,
                    "permiso_usado": permiso_usado,
                    "motivo": (motivo or comentario or "")[:500],
                },
            )
            _repo.finalizar_accion(cursor, action_id, "ok", {"resolucion": resolucion.value})
            conn.commit()
            return {
                "status": "success",
                "conflict_id": conflict_id,
                "resolucion": resolucion.value,
                "estado_conflicto": estado_res.value,
                "orden_financiera_pendiente": True,
            }
        except Exception as e:
            if conn:
                conn.rollback()
            return {"status": "error", "message": str(e)}
        finally:
            if conn:
                conn.close()


def cerrar_conflicto(
    db, conflict_id: int, *, actor: str, idempotency_key: str = "",
    version_esperada: Optional[int] = None, permiso_usado: str = "",
) -> Dict[str, Any]:
    key = idempotency_key or f"cerrar-{conflict_id}"
    with db._lock:
        conn = None
        try:
            conn = db._connect()
            cursor = conn.cursor()
            row = _repo.select_por_id(cursor, conflict_id)
            if not row:
                return {"status": "error", "message": "Conflicto no encontrado"}
            verr = _validar_version_fila(row, version_esperada)
            if verr:
                return verr
            actual = normalizar_estado_conflicto(row.get("estado_conflicto"), row.get("estado"))
            if actual == EstadoConflicto.CERRADO:
                return {"status": "success", "idempotent": True, "conflict_id": conflict_id}
            if actual != EstadoConflicto.RESUELTO:
                return {"status": "error", "message": "Solo se puede cerrar un conflicto RESUELTO"}
            if not (row.get("resolucion") or "").strip():
                return {"status": "error", "message": "Resolución registrada obligatoria"}

            claim, action_id = _repo.reclamar_accion(cursor, conflict_id, "cerrar", key, actor)
            if claim == "duplicate":
                return {"status": "success", "idempotent": True}

            version = int(row.get("version") or 1)
            ok = _repo.cerrar_conflicto_cas(cursor, conflict_id, EstadoConflicto.RESUELTO.value, version)
            if not ok:
                conn.commit()
                return _error_version()
            _repo.registrar_auditoria(
                cursor, conflict_id, accion="cerrar", actor=actor,
                estado_anterior=EstadoConflicto.RESUELTO.value,
                estado_nuevo=EstadoConflicto.CERRADO.value,
                metadata={"permiso_usado": permiso_usado},
            )
            _repo.finalizar_accion(cursor, action_id, "ok", {})
            conn.commit()
            return {"status": "success", "conflict_id": conflict_id, "estado_conflicto": "CERRADO"}
        except Exception as e:
            if conn:
                conn.rollback()
            return {"status": "error", "message": str(e)}
        finally:
            if conn:
                conn.close()


def agregar_evidencia(
    db, conflict_id: int, *, tipo: str, nombre: str, referencia: str,
    subido_por: str, hash_val: str = "", permiso_usado: str = "",
) -> Dict[str, Any]:
    with db._lock:
        conn = db._connect()
        try:
            cursor = conn.cursor()
            row = _repo.select_por_id(cursor, conflict_id)
            if not row:
                return {"status": "error", "message": "Conflicto no encontrado"}
            eid = _repo.insertar_evidencia(
                cursor, conflict_id, tipo=tipo, nombre=nombre,
                referencia=referencia, subido_por=subido_por, hash_val=hash_val,
            )
            _repo.registrar_auditoria(
                cursor, conflict_id, accion="evidencia", actor=subido_por,
                estado_anterior=row.get("estado_conflicto", ""),
                estado_nuevo=row.get("estado_conflicto", ""),
                metadata={"evidence_id": eid, "tipo": tipo, "permiso_usado": permiso_usado},
            )
            conn.commit()
            return {"status": "success", "evidence_id": eid}
        finally:
            conn.close()


def agregar_comentario(
    db, conflict_id: int, *, autor: str, texto: str,
    visible_contratante: bool = True, visible_profesional: bool = True,
    permiso_usado: str = "",
) -> Dict[str, Any]:
    texto = (texto or "").strip()
    if not texto:
        return {"status": "error", "message": "texto obligatorio"}
    with db._lock:
        conn = db._connect()
        try:
            cursor = conn.cursor()
            row = _repo.select_por_id(cursor, conflict_id)
            if not row:
                return {"status": "error", "message": "Conflicto no encontrado"}
            cid = _repo.insertar_comentario(
                cursor, conflict_id, autor=autor, texto=texto,
                visible_contratante=visible_contratante, visible_profesional=visible_profesional,
            )
            _repo.registrar_auditoria(
                cursor, conflict_id, accion="comentario", actor=autor,
                estado_anterior=row.get("estado_conflicto", ""),
                estado_nuevo=row.get("estado_conflicto", ""),
                metadata={"comment_id": cid, "permiso_usado": permiso_usado},
            )
            conn.commit()
            return {"status": "success", "comment_id": cid}
        finally:
            conn.close()


def _validar_resolucion(
    resolucion: ResolucionConflicto, **kwargs,
) -> Optional[Dict[str, Any]]:
    texto_motivo = (kwargs.get("motivo") or kwargs.get("comentario") or "").strip()
    if resolucion != ResolucionConflicto.MANTENER_RETENIDO and not texto_motivo:
        return {"status": "error", "message": "motivo obligatorio"}
    if resolucion == ResolucionConflicto.ESCALAR_ADMIN:
        if not (kwargs.get("responsable_codigo") or "").strip():
            return {"status": "error", "message": "responsable_codigo obligatorio para ESCALAR_ADMIN"}
        if not (kwargs.get("comentario") or "").strip():
            return {"status": "error", "message": "comentario obligatorio para ESCALAR_ADMIN"}
    if resolucion == ResolucionConflicto.REEMBOLSAR_PARCIAL:
        texto = (kwargs.get("motivo") or kwargs.get("comentario") or "").strip()
        if not texto:
            return {"status": "error", "message": "motivo obligatorio para REEMBOLSAR_PARCIAL"}
    return None


def _validar_importes_resolucion(
    cursor, contacto_id: int, resolucion: ResolucionConflicto,
    liberar: int, reembolsar: int, prof: int, contr: int,
) -> Optional[Dict[str, Any]]:
    fin = _fin_repo.select_contacto_financiero(cursor, contacto_id)
    neto_cents = 0
    if fin:
        d = dict(fin) if hasattr(fin, "keys") else {}
        neto_cents = importe_bd_a_cents(d.get("importe_neto_profesional"))

    if resolucion == ResolucionConflicto.LIBERAR_PROFESIONAL:
        if liberar <= 0:
            return {"status": "error", "message": "importe_liberar_cents debe ser > 0"}
        if neto_cents and liberar > neto_cents:
            return {"status": "error", "message": "importe supera neto pendiente"}
        estado = (dict(fin).get("estado_financiero") if fin else "") or ""
        if estado == EstadoFinanciero.TRANSFERIDO.value:
            return {"status": "error", "message": "transferencia ya completada"}

    if resolucion == ResolucionConflicto.REEMBOLSAR_PARCIAL:
        if reembolsar <= 0:
            return {"status": "error", "message": "importe_reembolsar_cents debe ser > 0"}
        max_ref = neto_cents or int(1e12)
        if reembolsar > max_ref:
            return {"status": "error", "message": "importe reembolso supera máximo"}

    if resolucion == ResolucionConflicto.DIVIDIR_IMPORTE:
        if prof < 0 or contr < 0:
            return {"status": "error", "message": "importes no pueden ser negativos"}
        if neto_cents and prof + contr > neto_cents:
            return {"status": "error", "message": "suma importes supera disponible"}

    if resolucion == ResolucionConflicto.REEMBOLSAR_TOTAL:
        if reembolsar < 0:
            return {"status": "error", "message": "importe_reembolsar inválido"}
    return None


def _alertar_conflicto_durante_transferencia(
    db, cursor, contacto_id: int, conflict_id: int, actor: str,
) -> None:
    if not _transfer_repo.tabla_existe(cursor):
        return
    row = _transfer_repo.select_por_contacto(cursor, contacto_id)
    if not row:
        return
    ft = _transfer_repo._row_dict(row)
    estado_ft = (ft or {}).get("estado", "")
    estado_fin = fts.obtener_estado_financiero(db, contacto_id)
    critico = (
        estado_ft == "STRIPE_EN_PROCESO"
        or estado_fin == EstadoFinanciero.TRANSFERIDO
        or estado_fin == EstadoFinanciero.TRANSFERENCIA_ENVIADA
    )
    if critico:
        try:
            db._insert_evento_sistema(
                cursor,
                "conflicto_durante_transferencia",
                f"ALERTA: conflicto #{conflict_id} abierto durante transferencia en contacto #{contacto_id}",
                "sistema",
                None,
                {
                    "contacto_id": contacto_id,
                    "conflict_id": conflict_id,
                    "estado_financiero": estado_fin.value if estado_fin else None,
                    "estado_transfer": estado_ft,
                    "actor_apertura": actor,
                },
            )
        except Exception:
            pass
