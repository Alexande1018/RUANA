"""Servicio de transiciones financieras con auditoría e idempotencia (FASE 01)."""
from __future__ import annotations

import json
import sqlite3
from typing import Any, Dict, List, Optional

from core.financial.estados import EstadoFinanciero, EstadoTransferencia
from core.financial.mapeo_legacy import inferir_estado_financiero_desde_legacy
from core.financial.modelo import InvarianteFinancieraError, ModeloFinanciero
from core.financial.state_machine import (
    FinancialStateMachine,
    TransicionBloqueadaError,
    TransicionInvalidaError,
)
from core.repositories.financial_transaction_repo import FinancialTransactionRepo

_repo = FinancialTransactionRepo()
_sm = FinancialStateMachine()


def obtener_estado_financiero(db, contacto_id: int) -> Optional[EstadoFinanciero]:
    with db._lock:
        conn = None
        try:
            conn = db._connect()
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            row = _repo.select_contacto_financiero(cursor, contacto_id)
            if not row:
                return None
            contacto = dict(row)
            raw = (contacto.get("estado_financiero") or "").strip()
            if raw:
                try:
                    return EstadoFinanciero.from_value(raw)
                except ValueError:
                    pass
            return inferir_estado_financiero_desde_legacy(contacto)
        finally:
            if conn:
                conn.close()


def transicionar(
    db,
    contacto_id: int,
    estado_nuevo: EstadoFinanciero,
    *,
    actor_tipo: str = "sistema",
    actor_codigo: str = "",
    motivo: str = "",
    stripe_ref: str = "",
    forzar_desde_legacy: bool = False,
) -> Dict[str, Any]:
    """
    Ejecuta una transición financiera validada con auditoría.

    Usa UPDATE atómico para concurrencia (compare-and-swap sobre estado_financiero).
    """
    with db._lock:
        conn = None
        try:
            conn = db._connect()
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            result = _transicionar_en_cursor(
                db,
                cursor,
                contacto_id,
                estado_nuevo,
                actor_tipo=actor_tipo,
                actor_codigo=actor_codigo,
                motivo=motivo,
                stripe_ref=stripe_ref,
                forzar_desde_legacy=forzar_desde_legacy,
            )
            if result.get("status") == "success":
                conn.commit()
            else:
                conn.rollback()
            return result
        except (TransicionInvalidaError, TransicionBloqueadaError) as e:
            if conn:
                conn.rollback()
            return {"status": "error", "message": str(e)}
        except Exception as e:
            if conn:
                conn.rollback()
            return {"status": "error", "message": str(e)}
        finally:
            if conn:
                conn.close()


def _transicionar_en_cursor(
    db,
    cursor,
    contacto_id: int,
    estado_nuevo: EstadoFinanciero,
    *,
    actor_tipo: str = "sistema",
    actor_codigo: str = "",
    motivo: str = "",
    stripe_ref: str = "",
    forzar_desde_legacy: bool = False,
) -> Dict[str, Any]:
    row = _repo.select_contacto_financiero(cursor, contacto_id)
    if not row:
        return {"status": "error", "message": "Contacto no encontrado"}
    contacto = dict(row)

    estado_actual = _resolver_estado_actual(contacto, forzar_desde_legacy)
    conflicto_abierto = _repo.tiene_conflicto_abierto(cursor, contacto_id)
    ya_transferido = estado_actual == EstadoFinanciero.TRANSFERIDO
    desde_cancelado = estado_actual in (
        EstadoFinanciero.PAGO_CANCELADO,
        EstadoFinanciero.CANCELADO,
        EstadoFinanciero.REEMBOLSADO,
    )

    _sm.validar_transicion(
        estado_actual,
        estado_nuevo,
        conflicto_abierto=conflicto_abierto,
        ya_transferido=ya_transferido,
        desde_estado_cancelado=desde_cancelado,
    )

    estado_transferencia = _sm.estado_transferencia_para(estado_nuevo).value
    updated = _repo.actualizar_estado_financiero_atomico(
        cursor,
        contacto_id,
        estado_actual.value,
        estado_nuevo.value,
        estado_transferencia,
    )
    if updated != 1:
        return {
            "status": "error",
            "message": "Transición rechazada por concurrencia o estado desactualizado",
            "estado_esperado": estado_actual.value,
        }

    _registrar_auditoria(
        db,
        cursor,
        contacto_id,
        estado_actual,
        estado_nuevo,
        actor_tipo,
        actor_codigo,
        motivo,
        stripe_ref,
    )
    return {
        "status": "success",
        "contacto_id": contacto_id,
        "estado_anterior": estado_actual.value,
        "estado_nuevo": estado_nuevo.value,
        "estado_transferencia": estado_transferencia,
    }


def intentar_autorizar_liberacion(
    db,
    contacto_id: int,
    actor_codigo: str,
    motivo: str = "contratante confirmó trabajo",
) -> Dict[str, Any]:
    """
    Transición atómica ESPERANDO_CONFIRMACION → LIBERACION_AUTORIZADA.

    Protege contra doble autorización concurrente (TEST 10).
    """
    with db._lock:
        conn = None
        try:
            conn = db._connect()
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            row = _repo.select_contacto_financiero(cursor, contacto_id)
            if not row:
                return {"status": "error", "message": "Contacto no encontrado"}
            contacto = dict(row)
            conflicto_abierto = _repo.tiene_conflicto_abierto(cursor, contacto_id)
            if conflicto_abierto:
                return {
                    "status": "error",
                    "message": "INVARIANTE 7: conflicto abierto bloquea transferencia",
                }
            estado_actual = _resolver_estado_actual(contacto, False)
            if estado_actual != EstadoFinanciero.ESPERANDO_CONFIRMACION:
                return {
                    "status": "error",
                    "message": (
                        f"Transición rechazada por concurrencia o estado desactualizado "
                        f"(estado actual: {estado_actual.value})"
                    ),
                }
            estado_nuevo = EstadoFinanciero.LIBERACION_AUTORIZADA
            estado_transferencia = _sm.estado_transferencia_para(estado_nuevo).value
            updated = _repo.actualizar_estado_financiero_atomico(
                cursor,
                contacto_id,
                EstadoFinanciero.ESPERANDO_CONFIRMACION.value,
                estado_nuevo.value,
                estado_transferencia,
            )
            if updated != 1:
                return {
                    "status": "error",
                    "message": "Transición rechazada por concurrencia o estado desactualizado",
                    "estado_esperado": EstadoFinanciero.ESPERANDO_CONFIRMACION.value,
                }
            _registrar_auditoria(
                db, cursor, contacto_id, estado_actual, estado_nuevo,
                "aliado", actor_codigo, motivo, "",
            )
            conn.commit()
            return {
                "status": "success",
                "contacto_id": contacto_id,
                "estado_anterior": estado_actual.value,
                "estado_nuevo": estado_nuevo.value,
            }
        except Exception as e:
            if conn:
                conn.rollback()
            return {"status": "error", "message": str(e)}
        finally:
            if conn:
                conn.close()


def registrar_transferencia_pendiente(
    db,
    contacto_id: int,
    actor_codigo: str = "",
    cursor=None,
) -> Dict[str, Any]:
    """LIBERACION_AUTORIZADA → TRANSFERENCIA_PENDIENTE (FASE 03)."""
    estado_objetivo = EstadoFinanciero.TRANSFERENCIA_PENDIENTE
    if cursor is not None:
        return _transicionar_en_cursor(
            db, cursor, contacto_id, estado_objetivo,
            actor_tipo="sistema", actor_codigo=actor_codigo,
            motivo="inicio transferencia Stripe",
        )
    return transicionar(
        db, contacto_id, estado_objetivo,
        actor_tipo="sistema", actor_codigo=actor_codigo,
        motivo="inicio transferencia Stripe",
    )


def registrar_transferencia_enviada(
    db,
    contacto_id: int,
    stripe_transfer_id: str,
    actor_codigo: str = "",
    cursor=None,
) -> Dict[str, Any]:
    """
    Avanza hasta TRANSFERENCIA_ENVIADA sin marcar TRANSFERIDO (FASE 03).

    TRANSFERIDO solo vía webhook transfer.paid.
    """
    resultados: List[Dict[str, Any]] = []
    if cursor is not None:
        row = _repo.select_contacto_financiero(cursor, contacto_id)
    else:
        estado = obtener_estado_financiero(db, contacto_id)
        row = None
    estado_inicial = None
    if row:
        estado_inicial = _resolver_estado_actual(dict(row), False)
    elif cursor is None:
        estado_inicial = estado

    if estado_inicial == EstadoFinanciero.TRANSFERENCIA_ENVIADA:
        return {"status": "success", "idempotent": True, "estado_final": estado_inicial.value}
    if estado_inicial == EstadoFinanciero.TRANSFERIDO:
        return {"status": "success", "idempotent": True, "estado_final": estado_inicial.value}

    pasos: List[EstadoFinanciero] = []
    if estado_inicial == EstadoFinanciero.LIBERACION_AUTORIZADA:
        pasos.append(EstadoFinanciero.TRANSFERENCIA_PENDIENTE)
    if estado_inicial in (
        EstadoFinanciero.LIBERACION_AUTORIZADA,
        EstadoFinanciero.TRANSFERENCIA_PENDIENTE,
        None,
    ):
        pasos.append(EstadoFinanciero.TRANSFERENCIA_ENVIADA)

    for estado in pasos:
        if cursor is not None:
            res = _transicionar_en_cursor(
                db, cursor, contacto_id, estado,
                actor_tipo="sistema", actor_codigo=actor_codigo,
                motivo="transferencia Stripe creada",
                stripe_ref=stripe_transfer_id if estado == EstadoFinanciero.TRANSFERENCIA_ENVIADA else "",
            )
        else:
            res = transicionar(
                db, contacto_id, estado,
                actor_tipo="sistema", actor_codigo=actor_codigo,
                motivo="transferencia Stripe creada",
                stripe_ref=stripe_transfer_id if estado == EstadoFinanciero.TRANSFERENCIA_ENVIADA else "",
            )
        resultados.append(res)
        if res.get("status") != "success":
            return {
                "status": "error",
                "message": res.get("message", "fallo registrando transferencia enviada"),
                "pasos": resultados,
            }
    return {
        "status": "success",
        "pasos": resultados,
        "estado_final": EstadoFinanciero.TRANSFERENCIA_ENVIADA.value,
    }


def completar_ciclo_transferencia(
    db,
    contacto_id: int,
    stripe_transfer_id: str,
    actor_codigo: str = "",
    cursor=None,
) -> Dict[str, Any]:
    """
    Aplica la secuencia LIBERACION_AUTORIZADA → ... → TRANSFERIDO.

    Compatible con confirmar_trabajo_y_transferir existente.
    Si se pasa cursor, participa en la transacción del llamador (sin commit propio).
    """
    resultados: List[Dict[str, Any]] = []
    for estado in _sm.ruta_liberacion_completa():
        if cursor is not None:
            res = _transicionar_en_cursor(
                db,
                cursor,
                contacto_id,
                estado,
                actor_tipo="sistema" if estado != EstadoFinanciero.LIBERACION_AUTORIZADA else "aliado",
                actor_codigo=actor_codigo,
                motivo="transferencia Stripe completada",
                stripe_ref=stripe_transfer_id if estado == EstadoFinanciero.TRANSFERENCIA_ENVIADA else "",
            )
        else:
            res = transicionar(
                db,
                contacto_id,
                estado,
                actor_tipo="sistema" if estado != EstadoFinanciero.LIBERACION_AUTORIZADA else "aliado",
                actor_codigo=actor_codigo,
                motivo="transferencia Stripe completada",
                stripe_ref=stripe_transfer_id if estado == EstadoFinanciero.TRANSFERENCIA_ENVIADA else "",
            )
        resultados.append(res)
        if res.get("status") != "success":
            return {
                "status": "error",
                "message": res.get("message", "fallo en ciclo de transferencia"),
                "pasos": resultados,
            }
    return {"status": "success", "pasos": resultados, "estado_final": EstadoFinanciero.TRANSFERIDO.value}


def sincronizar_tras_activacion_stripe(db, contacto_id: int, actor_codigo: str = "") -> None:
    """Hook post-activar_pago_stripe_tras_acuerdo: establece PAGO_PENDIENTE."""
    sincronizar_estado_desde_legacy(db, contacto_id)
    estado = obtener_estado_financiero(db, contacto_id)
    if estado == EstadoFinanciero.PAGO_NO_INICIADO:
        transicionar(
            db, contacto_id, EstadoFinanciero.PAGO_PENDIENTE,
            actor_codigo=actor_codigo, motivo="pago Stripe activado",
        )


def sincronizar_tras_cobro_confirmado(db, contacto_id: int, stripe_ref: str = "") -> None:
    """Hook post-webhook cobro: PAGO_PENDIENTE → PAGO_CONFIRMADO → TRABAJO_EN_CURSO → ESPERANDO_CONFIRMACION."""
    estado = obtener_estado_financiero(db, contacto_id)
    if estado is None or estado == EstadoFinanciero.MIGRACION_PENDIENTE:
        sincronizar_estado_desde_legacy(db, contacto_id)
        estado = obtener_estado_financiero(db, contacto_id)
    if estado == EstadoFinanciero.PAGO_PENDIENTE:
        transicionar(
            db, contacto_id, EstadoFinanciero.PAGO_CONFIRMADO,
            motivo="cobro Stripe confirmado", stripe_ref=stripe_ref,
        )
        estado = EstadoFinanciero.PAGO_CONFIRMADO
    if estado == EstadoFinanciero.PAGO_CONFIRMADO:
        transicionar(db, contacto_id, EstadoFinanciero.TRABAJO_EN_CURSO, motivo="trabajo iniciado")
        estado = EstadoFinanciero.TRABAJO_EN_CURSO
    if estado == EstadoFinanciero.TRABAJO_EN_CURSO:
        transicionar(
            db, contacto_id, EstadoFinanciero.ESPERANDO_CONFIRMACION,
            motivo="esperando confirmación del contratante",
        )


def sincronizar_estado_desde_legacy(db, contacto_id: int) -> Dict[str, Any]:
    """Backfill o actualización del estado financiero desde campos legacy."""
    with db._lock:
        conn = None
        try:
            conn = db._connect()
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            row = _repo.select_contacto_financiero(cursor, contacto_id)
            if not row:
                return {"status": "error", "message": "Contacto no encontrado"}
            contacto = dict(row)
            inferido = inferir_estado_financiero_desde_legacy(contacto)
            actual_raw = (contacto.get("estado_financiero") or "").strip()
            if actual_raw:
                return {
                    "status": "ignored",
                    "estado_financiero": actual_raw,
                    "message": "ya tiene estado financiero",
                }
            estado_transferencia = _sm.estado_transferencia_para(inferido).value
            updated = _repo.backfill_estado_financiero(cursor, contacto_id, inferido.value)
            if updated and "estado_transferencia" in _repo.columnas_contacto(cursor):
                cursor.execute(
                    "UPDATE contactos_ruana SET estado_transferencia = ? WHERE id = ?",
                    (estado_transferencia, contacto_id),
                )
            conn.commit()
            return {
                "status": "success",
                "contacto_id": contacto_id,
                "estado_financiero": inferido.value,
                "estado_transferencia": estado_transferencia,
            }
        finally:
            if conn:
                conn.close()


def migrar_estados_financieros_pendientes(db, limit: int = 500) -> Dict[str, Any]:
    """Migra contactos sin estado_financiero asignado."""
    migrados = 0
    pendientes = 0
    with db._lock:
        conn = None
        try:
            conn = db._connect()
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            filas = _repo.listar_contactos_sin_estado_financiero(cursor, limit)
            for row in filas:
                contacto = dict(row) if hasattr(row, "keys") else {"id": row[0]}
                if not contacto.get("modo_pago") and len(row) > 1:
                    contacto = {
                        "id": row[0],
                        "modo_pago": row[1],
                        "estado": row[2],
                        "estado_pago": row[3],
                        "stripe_transfer_id": row[4],
                        "stripe_payment_intent_id": row[5],
                        "fecha_confirmacion_trabajo": row[6] if len(row) > 6 else None,
                    }
                inferido = inferir_estado_financiero_desde_legacy(contacto)
                if inferido == EstadoFinanciero.MIGRACION_PENDIENTE:
                    pendientes += 1
                else:
                    migrados += 1
                estado_transferencia = _sm.estado_transferencia_para(inferido).value
                _repo.establecer_estado_financiero(
                    cursor, int(contacto["id"]), inferido.value, estado_transferencia
                )
            conn.commit()
            return {"status": "success", "migrados": migrados, "migracion_pendiente": pendientes}
        finally:
            if conn:
                conn.close()


def validar_modelo_contacto(db, contacto_id: int) -> Dict[str, Any]:
    """Valida invariantes financieras de un contacto."""
    with db._lock:
        conn = None
        try:
            conn = db._connect()
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            row = _repo.select_contacto_financiero(cursor, contacto_id)
            if not row:
                return {"status": "error", "message": "Contacto no encontrado"}
            contacto = dict(row)
            conflicto_abierto = _repo.tiene_conflicto_abierto(cursor, contacto_id)
            modelo = ModeloFinanciero.desde_contacto(contacto)
            modelo_validacion = ModeloFinanciero(
                contacto_id=modelo.contacto_id,
                importe_bruto=modelo.importe_bruto,
                comision_ruana=modelo.comision_ruana,
                importe_profesional=modelo.importe_profesional,
                pago_confirmado=modelo.pago_confirmado,
                conflicto_abierto=conflicto_abierto,
                transferencia_valida_existente=modelo.transferencia_valida_existente,
            )
            return {
                "status": "success",
                "modelo": {
                    "importe_bruto": modelo_validacion.importe_bruto,
                    "comision_ruana": modelo_validacion.comision_ruana,
                    "importe_profesional": modelo_validacion.importe_profesional,
                },
                "puede_modificar_importe": modelo_validacion.puede_modificar_importe(),
                "conflicto_abierto": conflicto_abierto,
            }
        except InvarianteFinancieraError as e:
            return {"status": "error", "message": str(e)}
        finally:
            if conn:
                conn.close()


def _resolver_estado_actual(contacto: Dict[str, Any], forzar_desde_legacy: bool) -> EstadoFinanciero:
    raw = (contacto.get("estado_financiero") or "").strip()
    if raw and not forzar_desde_legacy:
        try:
            return EstadoFinanciero.from_value(raw)
        except ValueError:
            pass
    return inferir_estado_financiero_desde_legacy(contacto)


def _registrar_auditoria(
    db,
    cursor,
    contacto_id: int,
    estado_anterior: EstadoFinanciero,
    estado_nuevo: EstadoFinanciero,
    actor_tipo: str,
    actor_codigo: str,
    motivo: str,
    stripe_ref: str,
) -> None:
    detalles = json.dumps(
        {
            "estado_anterior": estado_anterior.value,
            "estado_nuevo": estado_nuevo.value,
            "motivo": motivo,
            "stripe_ref": stripe_ref or None,
        },
        ensure_ascii=False,
    )
    db._audit_log(
        cursor,
        "contacto",
        contacto_id,
        "financiero_transicion",
        actor_tipo,
        actor_codigo,
        detalles,
    )
