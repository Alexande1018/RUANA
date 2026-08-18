"""Servicio de transferencias Stripe blindadas (FASE 03)."""
from __future__ import annotations

import json
import sqlite3
from typing import Any, Dict, Optional, Tuple

from core import stripe_client
from core.financial.estados import EstadoFinanciero, EstadoTransferencia
from core.financial.state_machine import FinancialStateMachine
from core.repositories.financial_transaction_repo import FinancialTransactionRepo
from core.repositories.financial_transfer_repo import FinancialTransferRepo
from core.repositories.pago_repo import PagoRepo
from core.services import financial_transaction_service as fts

_pago_repo = PagoRepo()
_fin_repo = FinancialTransactionRepo()
_transfer_repo = FinancialTransferRepo()
_sm = FinancialStateMachine()

IDEMPOTENCY_PREFIX = "transfer-contacto-"


def ejecutar_liberacion_y_transferencia(
    db, contacto_id: int, contratante_codigo: str
) -> Dict[str, Any]:
    """
    Flujo blindado: validar → autorizar liberación → reclamar slot BD →
    crear transferencia Stripe → registrar TRANSFERENCIA_ENVIADA (no TRANSFERIDO).
    """
    codigo = (contratante_codigo or "").strip()
    if not codigo:
        return {"status": "error", "message": "Código de aliado obligatorio"}

    neto_val = 0.0
    amount_cents = 0
    account_id = ""
    prof_codigo = ""
    idempotency_key = f"{IDEMPOTENCY_PREFIX}{contacto_id}"
    transfer_row: Optional[Dict[str, Any]] = None

    with db._lock:
        conn = None
        try:
            conn = db._connect()
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            validacion = _validar_precondiciones(db, cursor, contacto_id, codigo)
            if validacion.get("status") != "ok":
                _auditar_intento(
                    db, cursor, contacto_id, codigo, validacion,
                    estado_anterior=validacion.get("estado_financiero", ""),
                )
                conn.commit()
                return {
                    "status": "error",
                    "message": validacion.get("message", "Validación fallida"),
                    "bloqueo": validacion.get("bloqueo"),
                }

            contacto = validacion["contacto"]
            estado_actual = validacion["estado_financiero"]
            neto_val = validacion["neto_val"]
            amount_cents = validacion["amount_cents"]
            account_id = validacion["account_id"]
            prof_codigo = validacion["prof_codigo"]

            idempotent = _respuesta_idempotente_si_aplica(
                db, cursor, contacto_id, codigo, estado_actual, contacto
            )
            if idempotent:
                conn.commit()
                return idempotent

            if estado_actual == EstadoFinanciero.ESPERANDO_CONFIRMACION:
                fin_lib = fts._transicionar_en_cursor(
                    db,
                    cursor,
                    contacto_id,
                    EstadoFinanciero.LIBERACION_AUTORIZADA,
                    actor_tipo="aliado",
                    actor_codigo=codigo,
                    motivo="contratante confirmó trabajo",
                )
                if fin_lib.get("status") != "success":
                    _auditar_intento(
                        db, cursor, contacto_id, codigo,
                        {"resultado": "bloqueado", "message": fin_lib.get("message")},
                        estado_anterior=estado_actual.value,
                    )
                    conn.rollback()
                    return {
                        "status": "error",
                        "message": fin_lib.get("message", "No se pudo autorizar la liberación"),
                    }
                estado_actual = EstadoFinanciero.LIBERACION_AUTORIZADA

            _pago_repo.marcar_confirmacion_trabajo_contratante(cursor, contacto_id)

            claim, transfer_row = _transfer_repo.reclamar_transferencia(
                cursor,
                contacto_id,
                idempotency_key,
                amount_cents,
                "eur",
                account_id,
                prof_codigo,
                validacion["payment_intent_id"],
                codigo,
            )

            if claim == "existing":
                mismatch = _validar_coherencia_reclamo(transfer_row, validacion)
                if mismatch:
                    _auditar_intento(db, cursor, contacto_id, codigo, mismatch)
                    conn.commit()
                    return {
                        "status": "error",
                        "message": mismatch.get("message"),
                        "bloqueo": mismatch.get("bloqueo"),
                    }
                existente = _manejar_reclamo_existente(
                    db, cursor, contacto_id, codigo, transfer_row, estado_actual
                )
                if existente:
                    conn.commit()
                    return existente
                _transfer_repo.intentar_reintentar_stripe(cursor, contacto_id)
                puede_ejecutar = _transfer_repo.intentar_ejecutar_stripe(cursor, contacto_id)
            else:
                puede_ejecutar = _transfer_repo.intentar_ejecutar_stripe(cursor, contacto_id)

            if not puede_ejecutar:
                conn.commit()
                return {
                    "status": "success",
                    "contacto_id": contacto_id,
                    "estado": "transferencia_en_proceso",
                    "estado_financiero": estado_actual.value,
                    "idempotent": True,
                    "message": "Transferencia ya en curso",
                }

            stripe_transfer_id = (transfer_row or {}).get("stripe_transfer_id")
            if stripe_transfer_id:
                resultado = _sincronizar_transferencia_registrada(
                    db, cursor, contacto_id, codigo, stripe_transfer_id, neto_val, prof_codigo
                )
                conn.commit()
                return resultado

            res_pendiente = fts.registrar_transferencia_pendiente(
                db, contacto_id, codigo, cursor=cursor
            )
            if res_pendiente.get("status") != "success":
                conn.rollback()
                return {
                    "status": "error",
                    "message": res_pendiente.get("message", "No se pudo iniciar transferencia"),
                }

            conn.commit()
        except Exception as e:
            if conn:
                conn.rollback()
            return {"status": "error", "message": str(e)}
        finally:
            if conn:
                conn.close()

    transfer_id, stripe_error = _crear_o_recuperar_transferencia_stripe(
        contacto_id=contacto_id,
        amount_cents=amount_cents,
        account_id=account_id,
        idempotency_key=idempotency_key,
    )

    with db._lock:
        conn = None
        try:
            conn = db._connect()
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            if stripe_error and not transfer_id:
                _transfer_repo.marcar_fallida(cursor, contacto_id, stripe_error)
                _auditar_intento(
                    db, cursor, contacto_id, codigo,
                    {"resultado": "error_stripe", "message": stripe_error},
                    financial_transfer_id=(transfer_row or {}).get("id"),
                )
                conn.commit()
                return {"status": "error", "message": stripe_error}

            if not transfer_id:
                return {"status": "error", "message": "Stripe no devolvió transferencia"}

            _transfer_repo.marcar_stripe_creada(cursor, contacto_id, transfer_id)
            _pago_repo.marcar_transfer_stripe_registrada(cursor, contacto_id, transfer_id)

            res_enviada = fts.registrar_transferencia_enviada(
                db, contacto_id, transfer_id, codigo, cursor=cursor
            )
            if res_enviada.get("status") != "success":
                conn.rollback()
                return {
                    "status": "error",
                    "message": res_enviada.get("message", "Error registrando transferencia enviada"),
                }

            db._audit_log(
                cursor, "contacto", contacto_id, "stripe_transfer_creada",
                "aliado", codigo, f"transfer={transfer_id} neto={neto_val}",
            )
            _auditar_intento(
                db, cursor, contacto_id, codigo,
                {"resultado": "stripe_creada", "message": "transferencia enviada a Stripe"},
                financial_transfer_id=(transfer_row or {}).get("id"),
                estado_anterior=EstadoFinanciero.LIBERACION_AUTORIZADA.value,
                estado_nuevo=EstadoFinanciero.TRANSFERENCIA_ENVIADA.value,
                stripe_transfer_id=transfer_id,
                metadata={"amount_cents": amount_cents, "account_id": account_id},
            )
            conn.commit()

            return {
                "status": "success",
                "contacto_id": contacto_id,
                "estado": "transferencia_enviada",
                "estado_pago": "cobro_confirmado",
                "estado_financiero": EstadoFinanciero.TRANSFERENCIA_ENVIADA.value,
                "estado_transferencia": EstadoTransferencia.ENVIADA.value,
                "stripe_transfer_id": transfer_id,
                "importe_neto_profesional": neto_val,
                "idempotent": False,
            }
        except Exception as e:
            if conn:
                conn.rollback()
            return {"status": "error", "message": str(e)}
        finally:
            if conn:
                conn.close()


def finalizar_transferencia_completada(
    db, contacto_id: int, transfer_id: str, origen: str = "webhook"
) -> Dict[str, Any]:
    """
    Marca TRANSFERIDO tras confirmación Stripe (transfer.paid).
    Actualiza legacy, notificaciones y score.
    """
    from core.services import pago_service

    with db._lock:
        conn = None
        try:
            conn = db._connect()
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            row = _pago_repo.select_contacto_stripe_por_id(cursor, contacto_id)
            if not row:
                return {"status": "error", "message": "Contacto no encontrado"}
            contacto = dict(row)
            fin_row = _fin_repo.select_contacto_financiero(cursor, contacto_id)
            if fin_row:
                for k, v in dict(fin_row).items():
                    contacto.setdefault(k, v)

            estado = _resolver_estado(contacto)
            if estado == EstadoFinanciero.TRANSFERIDO:
                _transfer_repo.marcar_completada(cursor, contacto_id)
                conn.commit()
                return {"status": "success", "idempotent": True, "contacto_id": contacto_id}

            for objetivo in (
                EstadoFinanciero.LIBERACION_AUTORIZADA,
                EstadoFinanciero.TRANSFERENCIA_PENDIENTE,
                EstadoFinanciero.TRANSFERENCIA_ENVIADA,
            ):
                fin_row = _fin_repo.select_contacto_financiero(cursor, contacto_id)
                est = _resolver_estado(dict(fin_row) if fin_row else contacto)
                if est == objetivo or est == EstadoFinanciero.TRANSFERIDO:
                    continue
                if _sm.puede_transicionar(est, objetivo):
                    res = fts._transicionar_en_cursor(
                        db, cursor, contacto_id, objetivo,
                        actor_tipo=origen, motivo=f"recuperación antes de TRANSFERIDO ({origen})",
                        stripe_ref=transfer_id,
                    )
                    if res.get("status") != "success":
                        break

            res = fts._transicionar_en_cursor(
                db, cursor, contacto_id, EstadoFinanciero.TRANSFERIDO,
                actor_tipo=origen, motivo="transfer.paid", stripe_ref=transfer_id,
            )
            if res.get("status") != "success" and estado != EstadoFinanciero.TRANSFERIDO:
                conn.rollback()
                return res

            _fin_repo.actualizar_solo_estado_transferencia(
                cursor, contacto_id, EstadoTransferencia.COMPLETADA.value
            )
            _transfer_repo.marcar_completada(cursor, contacto_id)
            _pago_repo.marcar_transfer_stripe_completado(cursor, contacto_id, transfer_id)

            neto_val = float(contacto.get("importe_neto_profesional") or 0)
            prof_codigo = str(contacto.get("profesional_codigo") or "").strip()
            solicitante = str(contacto.get("solicitante_codigo") or "").strip()

            mensaje_prof = (
                f"El contratante confirmó el trabajo del encargo #{contacto_id}. "
                f"RUANA ha transferido {neto_val:g} € a tu cuenta."
            )
            meta = json.dumps(
                {"contacto_id": contacto_id, "importe_neto": neto_val, "transfer_id": transfer_id},
                ensure_ascii=False,
            )
            _pago_repo.insertar_notif_pago_stripe(
                cursor, prof_codigo, "Pago transferido", mensaje_prof, meta
            )
            db._audit_log(
                cursor, "contacto", contacto_id, "stripe_transfer_completado",
                origen, "", f"transfer={transfer_id} neto={neto_val}",
            )
            conn.commit()

            pago_service._aplicar_score_tras_transfer(db, contacto_id, solicitante, prof_codigo)
            return {
                "status": "success",
                "contacto_id": contacto_id,
                "estado_pago": "transferido",
                "estado_financiero": EstadoFinanciero.TRANSFERIDO.value,
            }
        except Exception as e:
            if conn:
                conn.rollback()
            return {"status": "error", "message": str(e)}
        finally:
            if conn:
                conn.close()


def _validar_coherencia_reclamo(
    transfer_row: Optional[Dict[str, Any]], validacion: Dict[str, Any]
) -> Optional[Dict[str, Any]]:
    if not transfer_row:
        return None
    if transfer_row.get("professional_codigo") != validacion["prof_codigo"]:
        return {
            "status": "error",
            "message": "Profesional no coincide con la transferencia registrada",
            "bloqueo": "profesional",
        }
    if transfer_row.get("destination_account_id") != validacion["account_id"]:
        return {
            "status": "error",
            "message": "Cuenta Connect no coincide con la transferencia registrada",
            "bloqueo": "connect",
        }
    if int(transfer_row.get("amount_cents") or 0) != int(validacion["amount_cents"]):
        return {
            "status": "error",
            "message": "Importe no coincide con la transferencia registrada",
            "bloqueo": "importe",
        }
    return None


def _validar_precondiciones(
    db, cursor, contacto_id: int, contratante_codigo: str
) -> Dict[str, Any]:
    row = _pago_repo.select_contacto_stripe_por_id(cursor, contacto_id)
    if not row:
        return {"status": "error", "message": "Contacto no encontrado", "bloqueo": "operacion"}

    contacto = dict(row)
    fin_row = _fin_repo.select_contacto_financiero(cursor, contacto_id)
    if fin_row:
        for k, v in dict(fin_row).items():
            contacto.setdefault(k, v)

    if str(contacto.get("solicitante_codigo") or "").strip() != contratante_codigo:
        return {
            "status": "error",
            "message": "Solo el aliado que contrató el encargo puede confirmar que el trabajo se realizó",
            "bloqueo": "autorizacion",
        }

    if contacto.get("modo_pago") != "stripe":
        return {"status": "error", "message": "Este contacto no usa pago Stripe", "bloqueo": "operacion"}

    estado_pago = (contacto.get("estado_pago") or "").strip()
    if estado_pago in ("transferido",):
        return {"status": "error", "message": "La transferencia al profesional ya se realizó", "bloqueo": "ya_transferido"}

    if estado_pago not in ("cobro_confirmado",):
        return {
            "status": "error",
            "message": "El pago del cliente aún no está confirmado o ya se transfirió al profesional",
            "bloqueo": "pago",
        }

    payment_intent_id = (contacto.get("stripe_payment_intent_id") or "").strip()
    if not payment_intent_id:
        return {
            "status": "error",
            "message": "PaymentIntent Stripe no registrado",
            "bloqueo": "pago",
        }

    if _fin_repo.tiene_conflicto_abierto(cursor, contacto_id):
        return {
            "status": "error",
            "message": "INVARIANTE 7: conflicto abierto bloquea transferencia",
            "bloqueo": "conflicto",
        }

    estado_servicio = (contacto.get("estado") or "").strip().lower()
    if estado_servicio in ("cancelado", "no_concretado", "cerrado_no_concretado", "trabajo_cerrado"):
        return {
            "status": "error",
            "message": "Operación en estado incompatible para liberación",
            "bloqueo": "operacion",
        }

    prof_codigo = str(contacto.get("profesional_codigo") or "").strip()
    if not prof_codigo:
        return {"status": "error", "message": "Profesional no asignado", "bloqueo": "profesional"}

    aliado_row = _pago_repo.select_aliado_stripe(cursor, prof_codigo)
    if not aliado_row:
        return {"status": "error", "message": "Profesional no encontrado", "bloqueo": "profesional"}

    aliado = dict(aliado_row) if hasattr(aliado_row, "keys") else {
        "stripe_account_id": aliado_row[3],
        "stripe_charges_enabled": aliado_row[4],
        "stripe_payouts_enabled": aliado_row[5] if len(aliado_row) > 5 else 0,
    }
    account_id = (aliado.get("stripe_account_id") or "").strip()
    if not account_id:
        return {
            "status": "error",
            "message": "El profesional no tiene cuenta Stripe Connect activa",
            "bloqueo": "connect",
        }
    if not aliado.get("stripe_charges_enabled"):
        return {
            "status": "error",
            "message": "La cuenta Connect del profesional no está habilitada para cobros",
            "bloqueo": "connect",
        }

    neto = contacto.get("importe_neto_profesional")
    importe_bruto = float(contacto.get("importe_final") or contacto.get("importe_acordado") or 0)
    if neto is None and importe_bruto > 0:
        from core.services.pago_service import _calcular_importes_stripe
        _, _, neto, _ = _calcular_importes_stripe(importe_bruto, db)
    neto_val = round(float(neto or 0), 2)
    if neto_val <= 0:
        return {"status": "error", "message": "Importe neto del profesional no válido", "bloqueo": "importe"}

    amount_cents = int(round(neto_val * 100))
    if amount_cents <= 0:
        return {"status": "error", "message": "Importe en céntimos no válido", "bloqueo": "importe"}

    estado_actual = _resolver_estado(contacto)
    if estado_actual in (
        EstadoFinanciero.PAGO_CANCELADO,
        EstadoFinanciero.CANCELADO,
        EstadoFinanciero.REEMBOLSADO,
        EstadoFinanciero.DISPUTA_STRIPE,
        EstadoFinanciero.CONFLICTO_ABIERTO,
        EstadoFinanciero.TRANSFERENCIA_FALLIDA,
    ):
        return {
            "status": "error",
            "message": f"Estado financiero incompatible: {estado_actual.value}",
            "bloqueo": "estado_financiero",
        }

    if estado_actual not in (
        EstadoFinanciero.ESPERANDO_CONFIRMACION,
        EstadoFinanciero.LIBERACION_AUTORIZADA,
        EstadoFinanciero.TRANSFERENCIA_PENDIENTE,
        EstadoFinanciero.TRANSFERENCIA_ENVIADA,
        EstadoFinanciero.TRANSFERIDO,
        EstadoFinanciero.TRABAJO_EN_CURSO,
        EstadoFinanciero.PAGO_CONFIRMADO,
    ):
        return {
            "status": "error",
            "message": f"Estado financiero no apto para liberación: {estado_actual.value}",
            "bloqueo": "estado_financiero",
        }

    existing_tid = (contacto.get("stripe_transfer_id") or "").strip()
    if existing_tid and estado_actual == EstadoFinanciero.TRANSFERIDO:
        return {
            "status": "error",
            "message": "La transferencia al profesional ya se realizó",
            "bloqueo": "ya_transferido",
        }

    return {
        "status": "ok",
        "contacto": contacto,
        "estado_financiero": estado_actual,
        "neto_val": neto_val,
        "amount_cents": amount_cents,
        "account_id": account_id,
        "prof_codigo": prof_codigo,
        "payment_intent_id": payment_intent_id,
    }


def _resolver_estado(contacto: Dict[str, Any]) -> EstadoFinanciero:
    raw = (contacto.get("estado_financiero") or "").strip()
    if raw:
        try:
            return EstadoFinanciero.from_value(raw)
        except ValueError:
            pass
    from core.financial.mapeo_legacy import inferir_estado_financiero_desde_legacy
    return inferir_estado_financiero_desde_legacy(contacto)


def _respuesta_idempotente_si_aplica(
    db, cursor, contacto_id: int, codigo: str,
    estado_actual: EstadoFinanciero, contacto: Dict[str, Any],
) -> Optional[Dict[str, Any]]:
    if estado_actual == EstadoFinanciero.TRANSFERIDO:
        return _build_idempotent_success(contacto_id, contacto, transferido=True)

    transfer_row = _transfer_repo.select_por_contacto(cursor, contacto_id)
    if transfer_row:
        row = _transfer_repo._row_dict(transfer_row)
        tid = (row or {}).get("stripe_transfer_id")
        if tid and estado_actual in (
            EstadoFinanciero.TRANSFERENCIA_ENVIADA,
            EstadoFinanciero.TRANSFERENCIA_PENDIENTE,
            EstadoFinanciero.LIBERACION_AUTORIZADA,
        ):
            return _sincronizar_transferencia_registrada(
                db, cursor, contacto_id, codigo, tid,
                float(contacto.get("importe_neto_profesional") or 0),
                str(contacto.get("profesional_codigo") or ""),
            )
        if tid and estado_actual == EstadoFinanciero.TRANSFERIDO:
            return _build_idempotent_success(contacto_id, contacto, transferido=True, transfer_id=tid)

    stripe_tid = (contacto.get("stripe_transfer_id") or "").strip()
    if stripe_tid and estado_actual in (
        EstadoFinanciero.TRANSFERENCIA_ENVIADA,
        EstadoFinanciero.TRANSFERENCIA_PENDIENTE,
    ):
        return _build_idempotent_success(
            contacto_id, contacto, transferido=False, transfer_id=stripe_tid
        )
    return None


def _manejar_reclamo_existente(
    db, cursor, contacto_id: int, codigo: str,
    transfer_row: Optional[Dict[str, Any]], estado_actual: EstadoFinanciero,
) -> Optional[Dict[str, Any]]:
    if not transfer_row:
        return None

    tid = (transfer_row.get("stripe_transfer_id") or "").strip()
    if tid:
        row = _pago_repo.select_contacto_stripe_por_id(cursor, contacto_id)
        contacto = dict(row) if row else {}
        return _sincronizar_transferencia_registrada(
            db, cursor, contacto_id, codigo, tid,
            float(contacto.get("importe_neto_profesional") or 0),
            str(contacto.get("profesional_codigo") or ""),
        )

    # Sin stripe_transfer_id: reanudar ejecución (p. ej. tras timeout o reinicio)
    return None


def _sincronizar_transferencia_registrada(
    db, cursor, contacto_id: int, codigo: str, transfer_id: str,
    neto_val: float, prof_codigo: str,
) -> Dict[str, Any]:
    fin_row = _fin_repo.select_contacto_financiero(cursor, contacto_id)
    estado = _resolver_estado(dict(fin_row) if fin_row else {})
    if estado not in (
        EstadoFinanciero.TRANSFERENCIA_ENVIADA,
        EstadoFinanciero.TRANSFERIDO,
    ):
        fts.registrar_transferencia_enviada(
            db, contacto_id, transfer_id, codigo, cursor=cursor
        )
    _pago_repo.marcar_transfer_stripe_registrada(cursor, contacto_id, transfer_id)
    return _build_idempotent_success(
        contacto_id,
        {"importe_neto_profesional": neto_val, "profesional_codigo": prof_codigo},
        transferido=estado == EstadoFinanciero.TRANSFERIDO,
        transfer_id=transfer_id,
    )


def _build_idempotent_success(
    contacto_id: int, contacto: Dict[str, Any], *,
    transferido: bool, transfer_id: str = "",
) -> Dict[str, Any]:
    tid = transfer_id or (contacto.get("stripe_transfer_id") or "")
    return {
        "status": "success",
        "contacto_id": contacto_id,
        "estado": "trabajo_cerrado" if transferido else "transferencia_enviada",
        "estado_pago": "transferido" if transferido else "cobro_confirmado",
        "estado_financiero": (
            EstadoFinanciero.TRANSFERIDO.value if transferido
            else EstadoFinanciero.TRANSFERENCIA_ENVIADA.value
        ),
        "stripe_transfer_id": tid,
        "importe_neto_profesional": float(contacto.get("importe_neto_profesional") or 0),
        "idempotent": True,
    }


def _crear_o_recuperar_transferencia_stripe(
    *,
    contacto_id: int,
    amount_cents: int,
    account_id: str,
    idempotency_key: str,
) -> Tuple[str, str]:
    """Crea transferencia en Stripe o recupera la existente vía idempotency key."""
    try:
        transfer = stripe_client.create_transfer(
            amount_cents=amount_cents,
            currency="eur",
            destination_account_id=account_id,
            contacto_id=contacto_id,
            idempotency_key=idempotency_key,
        )
        transfer_id = str(transfer.get("id") or "")
        return transfer_id, ""
    except Exception as e:
        err = str(e)
        try:
            recovered = stripe_client.retrieve_transfer_by_idempotency_metadata(
                contacto_id=contacto_id,
                idempotency_key=idempotency_key,
                amount_cents=amount_cents,
                destination_account_id=account_id,
            )
            if recovered and recovered.get("id"):
                return str(recovered["id"]), ""
        except Exception:
            pass
        return "", err


def _auditar_intento(
    db, cursor, contacto_id: int, actor_codigo: str,
    info: Dict[str, Any], *,
    financial_transfer_id: Optional[int] = None,
    estado_anterior: str = "",
    estado_nuevo: str = "",
    stripe_transfer_id: str = "",
    metadata: Optional[Dict[str, Any]] = None,
) -> None:
    if not _transfer_repo.tabla_existe(cursor):
        return
    _transfer_repo.registrar_intento(
        cursor,
        contacto_id,
        financial_transfer_id=financial_transfer_id,
        actor_codigo=actor_codigo,
        resultado=info.get("resultado") or info.get("status", "unknown"),
        motivo_bloqueo=info.get("bloqueo") or info.get("message", ""),
        estado_anterior=estado_anterior,
        estado_nuevo=estado_nuevo,
        stripe_transfer_id=stripe_transfer_id,
        metadata=metadata,
    )


def validar_invariante_una_transferencia(db, contacto_id: int) -> Dict[str, Any]:
    """Comprueba: una operación → máximo una transferencia Stripe válida."""
    with db._lock:
        conn = db._connect()
        cursor = conn.cursor()
        count = 0
        if _transfer_repo.tabla_existe(cursor):
            count = _transfer_repo.contar_transferencias_contacto(cursor, contacto_id)
        conn.close()
    return {
        "status": "success" if count <= 1 else "error",
        "transferencias_registradas": count,
        "invariante_ok": count <= 1,
    }
