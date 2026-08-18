"""Blueprint REST de conflictos financieros formales (FASE 04.1).

Todas las rutas delegan en financial_conflict_service.
Autorización granular deny-by-default vía require_conflict_permission.
"""
from __future__ import annotations

from typing import Any, Dict, Optional, Tuple

from flask import Blueprint, jsonify, request

from core import db_manager as db_manager_mod
from core.conflict_authorization import (
    CONFLICT_ADD_EVIDENCE,
    CONFLICT_CLOSE,
    CONFLICT_COMMENT,
    CONFLICT_ESCALATE,
    CONFLICT_INVESTIGATE,
    CONFLICT_REQUEST_EVIDENCE,
    CONFLICT_RESOLVE,
    CONFLICT_VIEW,
)
from core.financial.conflict_estados import EstadoConflicto, ResolucionConflicto, TipoConflicto
from core.services import financial_conflict_service as fcs
from web.auth_decorators import _admin_codigo, require_conflict_permission

financial_conflicts_bp = Blueprint("financial_conflicts", __name__)


def get_db():
    import sys
    for key in ("RUANA.web.app", "web.app"):
        mod = sys.modules.get(key)
        if mod is not None:
            fn = getattr(mod, "get_db", None)
            if callable(fn):
                return fn()
    return db_manager_mod.get_db()


def _json_body() -> Dict[str, Any]:
    return request.get_json(silent=True) or {}


def _idempotency_key(data: Dict[str, Any]) -> str:
    header = (request.headers.get("Idempotency-Key") or "").strip()
    body = (data.get("idempotency_key") or "").strip()
    return header or body


def _version(data: Dict[str, Any]) -> Optional[int]:
    raw = data.get("version")
    if raw is None:
        return None
    try:
        return int(raw)
    except (TypeError, ValueError):
        return -1


def _http_from_result(result: Dict[str, Any], *, default_ok: int = 200) -> Tuple[Any, int]:
    if result.get("status") == "success":
        return jsonify(result), default_ok
    if result.get("code") == "version_conflict":
        return jsonify(result), 409
    msg = (result.get("message") or "").lower()
    if "modificado por otro proceso" in msg or "concurrencia" in msg:
        return jsonify(result), 409
    return jsonify(result), 400


@financial_conflicts_bp.route("/api/admin/financial-conflicts/bp-health", methods=["GET"])
def financial_conflicts_bp_health():
    return jsonify({"status": "ok", "dominio": "financial_conflicts"})


@financial_conflicts_bp.route("/api/admin/financial-conflicts", methods=["GET"])
@require_conflict_permission(CONFLICT_VIEW)
def listar_conflictos():
  """GET /api/admin/financial-conflicts — lista conflictos formales."""
  try:
    estado = (request.args.get("estado") or "").strip()
    limite = min(int(request.args.get("limite", 100)), 500)
    offset = max(int(request.args.get("offset", 0)), 0)
    result = fcs.listar_conflictos(get_db(), estado=estado, limite=limite, offset=offset)
    return jsonify(result), 200 if result.get("status") == "success" else 400
  except Exception as e:
    return jsonify({"status": "error", "message": str(e)}), 500


@financial_conflicts_bp.route("/api/admin/financial-conflicts/<int:conflict_id>", methods=["GET"])
@require_conflict_permission(CONFLICT_VIEW)
def detalle_conflicto(conflict_id: int):
  """GET /api/admin/financial-conflicts/<id> — detalle completo."""
  try:
    result = fcs.obtener_detalle(get_db(), conflict_id)
    if result.get("status") == "error" and "no encontrado" in (result.get("message") or "").lower():
      return jsonify(result), 404
    return jsonify(result), 200 if result.get("status") == "success" else 400
  except Exception as e:
    return jsonify({"status": "error", "message": str(e)}), 500


@financial_conflicts_bp.route("/api/admin/financial-conflicts", methods=["POST"])
@require_conflict_permission(CONFLICT_INVESTIGATE)
def abrir_conflicto():
  """POST /api/admin/financial-conflicts — abre conflicto formal."""
  data = _json_body()
  contacto_id = data.get("contacto_id")
  tipo_raw = (data.get("tipo") or TipoConflicto.IMPORTE_DISPUTADO.value).strip().upper()
  motivo = (data.get("motivo") or "").strip()
  if not contacto_id:
    return jsonify({"status": "error", "message": "contacto_id obligatorio"}), 400
  try:
    tipo = TipoConflicto(tipo_raw)
  except ValueError:
    return jsonify({"status": "error", "message": f"tipo inválido: {tipo_raw}"}), 400
  try:
    importe = int(data.get("importe_reclamado_cents") or 0)
  except (TypeError, ValueError):
    return jsonify({"status": "error", "message": "importe_reclamado_cents inválido"}), 400
  actor = _admin_codigo()
  result = fcs.abrir_conflicto(
    get_db(), int(contacto_id),
    tipo=tipo, motivo=motivo, abierto_por=actor,
    importe_reclamado_cents=importe,
    idempotency_key=_idempotency_key(data),
  )
  body, code = _http_from_result(result, default_ok=201)
  return body, code if code != 200 else (201 if result.get("status") == "success" else 400)


@financial_conflicts_bp.route(
  "/api/admin/financial-conflicts/<int:conflict_id>/asignar", methods=["POST"],
)
@require_conflict_permission(CONFLICT_INVESTIGATE)
def asignar_responsable(conflict_id: int):
  data = _json_body()
  version = _version(data)
  if version == -1:
    return jsonify({"status": "error", "message": "version inválida"}), 400
  result = fcs.asignar_responsable(
    get_db(), conflict_id,
    responsable_codigo=(data.get("responsable_codigo") or "").strip(),
    actor=_admin_codigo(),
    idempotency_key=_idempotency_key(data),
    version_esperada=version,
    permiso_usado=CONFLICT_INVESTIGATE,
  )
  return _http_from_result(result)


@financial_conflicts_bp.route(
  "/api/admin/financial-conflicts/<int:conflict_id>/investigar", methods=["POST"],
)
@require_conflict_permission(CONFLICT_INVESTIGATE)
def pasar_en_investigacion(conflict_id: int):
  data = _json_body()
  version = _version(data)
  if version == -1:
    return jsonify({"status": "error", "message": "version inválida"}), 400
  result = fcs.transicionar_conflicto(
    get_db(), conflict_id, EstadoConflicto.EN_INVESTIGACION,
    actor=_admin_codigo(),
    idempotency_key=_idempotency_key(data) or f"investigar-{conflict_id}",
    version_esperada=version,
  )
  return _http_from_result(result)


@financial_conflicts_bp.route(
  "/api/admin/financial-conflicts/<int:conflict_id>/solicitar-evidencia", methods=["POST"],
)
@require_conflict_permission(CONFLICT_REQUEST_EVIDENCE)
def solicitar_evidencia(conflict_id: int):
  data = _json_body()
  version = _version(data)
  if version == -1:
    return jsonify({"status": "error", "message": "version inválida"}), 400
  result = fcs.solicitar_evidencia(
    get_db(), conflict_id,
    actor=_admin_codigo(),
    idempotency_key=_idempotency_key(data),
    version_esperada=version,
    permiso_usado=CONFLICT_REQUEST_EVIDENCE,
    motivo=(data.get("motivo") or "").strip(),
  )
  return _http_from_result(result)


@financial_conflicts_bp.route(
  "/api/admin/financial-conflicts/<int:conflict_id>/evidencias", methods=["POST"],
)
@require_conflict_permission(CONFLICT_ADD_EVIDENCE)
def anadir_evidencia(conflict_id: int):
  data = _json_body()
  tipo = (data.get("tipo") or "").strip()
  nombre = (data.get("nombre") or "").strip()
  referencia = (data.get("referencia") or data.get("referencia_segura") or "").strip()
  if not tipo or not nombre or not referencia:
    return jsonify({
      "status": "error",
      "message": "tipo, nombre y referencia son obligatorios",
    }), 400
  result = fcs.agregar_evidencia(
    get_db(), conflict_id,
    tipo=tipo, nombre=nombre, referencia=referencia,
    subido_por=_admin_codigo(),
    hash_val=(data.get("hash_sha256") or "").strip(),
    permiso_usado=CONFLICT_ADD_EVIDENCE,
  )
  return _http_from_result(result, default_ok=201)


@financial_conflicts_bp.route(
  "/api/admin/financial-conflicts/<int:conflict_id>/comentarios", methods=["POST"],
)
@require_conflict_permission(CONFLICT_COMMENT)
def anadir_comentario(conflict_id: int):
  data = _json_body()
  texto = (data.get("texto") or "").strip()
  if not texto:
    return jsonify({"status": "error", "message": "texto obligatorio"}), 400
  result = fcs.agregar_comentario(
    get_db(), conflict_id,
    autor=_admin_codigo(), texto=texto,
    visible_contratante=bool(data.get("visible_contratante", True)),
    visible_profesional=bool(data.get("visible_profesional", True)),
    permiso_usado=CONFLICT_COMMENT,
  )
  return _http_from_result(result, default_ok=201)


@financial_conflicts_bp.route(
  "/api/admin/financial-conflicts/<int:conflict_id>/resolver", methods=["POST"],
)
@require_conflict_permission(CONFLICT_RESOLVE)
def resolver_conflicto(conflict_id: int):
  data = _json_body()
  resolucion_raw = (data.get("resolucion") or "").strip().upper()
  if not resolucion_raw:
    return jsonify({"status": "error", "message": "resolucion obligatoria"}), 400
  try:
    resolucion = ResolucionConflicto(resolucion_raw)
  except ValueError:
    return jsonify({"status": "error", "message": f"resolucion inválida: {resolucion_raw}"}), 400
  version = _version(data)
  if version == -1:
    return jsonify({"status": "error", "message": "version inválida"}), 400
  ints = {}
  for field in (
    "importe_liberar_cents", "importe_reembolsar_cents",
    "importe_profesional_cents", "importe_contratante_cents",
  ):
    if field in data and data[field] is not None:
      try:
        ints[field] = int(data[field])
      except (TypeError, ValueError):
        return jsonify({"status": "error", "message": f"{field} inválido"}), 400
  result = fcs.resolver_conflicto(
    get_db(), conflict_id, resolucion,
    actor=_admin_codigo(),
    idempotency_key=_idempotency_key(data),
    motivo=(data.get("motivo") or "").strip(),
    comentario=(data.get("comentario") or "").strip(),
    responsable_codigo=(data.get("responsable_codigo") or "").strip(),
    version_esperada=version,
    permiso_usado=CONFLICT_RESOLVE,
    **ints,
  )
  return _http_from_result(result)


@financial_conflicts_bp.route(
  "/api/admin/financial-conflicts/<int:conflict_id>/escalar", methods=["POST"],
)
@require_conflict_permission(CONFLICT_ESCALATE)
def escalar_conflicto(conflict_id: int):
  data = _json_body()
  version = _version(data)
  if version == -1:
    return jsonify({"status": "error", "message": "version inválida"}), 400
  result = fcs.escalar_conflicto(
    get_db(), conflict_id,
    actor=_admin_codigo(),
    responsable_codigo=(data.get("responsable_codigo") or "").strip(),
    comentario=(data.get("comentario") or "").strip(),
    idempotency_key=_idempotency_key(data),
    version_esperada=version,
    permiso_usado=CONFLICT_ESCALATE,
  )
  return _http_from_result(result)


@financial_conflicts_bp.route(
  "/api/admin/financial-conflicts/<int:conflict_id>/cerrar", methods=["POST"],
)
@require_conflict_permission(CONFLICT_CLOSE)
def cerrar_conflicto(conflict_id: int):
  data = _json_body()
  version = _version(data)
  if version == -1:
    return jsonify({"status": "error", "message": "version inválida"}), 400
  result = fcs.cerrar_conflicto(
    get_db(), conflict_id,
    actor=_admin_codigo(),
    idempotency_key=_idempotency_key(data),
    version_esperada=version,
    permiso_usado=CONFLICT_CLOSE,
  )
  return _http_from_result(result)


@financial_conflicts_bp.route(
  "/api/admin/financial-conflicts/<int:conflict_id>/auditoria", methods=["GET"],
)
@require_conflict_permission(CONFLICT_VIEW)
def auditoria_conflicto(conflict_id: int):
  try:
    result = fcs.listar_auditoria(get_db(), conflict_id)
    if result.get("status") == "error" and "no encontrado" in (result.get("message") or "").lower():
      return jsonify(result), 404
    return jsonify(result), 200 if result.get("status") == "success" else 400
  except Exception as e:
    return jsonify({"status": "error", "message": str(e)}), 500


@financial_conflicts_bp.route(
  "/api/admin/financial-conflicts/<int:conflict_id>/acciones-pendientes", methods=["GET"],
)
@require_conflict_permission(CONFLICT_VIEW)
def acciones_pendientes(conflict_id: int):
  try:
    result = fcs.listar_acciones_financieras_pendientes(get_db(), conflict_id)
    if result.get("status") == "error" and "no encontrado" in (result.get("message") or "").lower():
      return jsonify(result), 404
    return jsonify(result), 200 if result.get("status") == "success" else 400
  except Exception as e:
    return jsonify({"status": "error", "message": str(e)}), 500
