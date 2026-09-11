"""Lector de errores/warnings desde Google Cloud Logging (visor admin).

No escribe logs ni persiste nada en Postgres. Solo consulta el proyecto GCP.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from itertools import islice
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from core.settings import get_settings

_SEVERIDADES = frozenset({"ERROR", "WARNING", "ALL"})
_HORAS_DEFAULT = 24
_HORAS_MAX = 168
_LIMITE_DEFAULT = 50
_LIMITE_MAX = 100
_SERVICE_DEFAULT = "ruana"

_PAYLOAD_RESERVADO = frozenset({
    "message",
    "msg",
    "severity",
    "logger",
    "loggerName",
    "python_logger",
    "exc_info",
    "exception",
    "stack_trace",
    "traceback",
    "time",
    "timestamp",
})

_MENSAJE_SIN_VIEWER = (
    "No se pueden leer los logs: falta el permiso logging.viewer "
    "(roles/logging.viewer) en la cuenta de servicio de Cloud Run."
)

ListEntriesFn = Callable[..., Tuple[Sequence[Any], Optional[str]]]


class CloudLoggingPermissionError(Exception):
    """Cloud Logging rechazó la consulta por IAM o credenciales."""


class CloudLoggingQueryError(Exception):
    """La API de Cloud Logging falló por un motivo distinto a permisos."""


def _ahora_utc() -> datetime:
    return datetime.now(timezone.utc)


def _escape_filter_value(value: str) -> str:
    return (value or "").replace("\\", "\\\\").replace('"', '\\"')


def _truthy(raw: Any) -> bool:
    if raw is True:
        return True
    return str(raw or "").strip().lower() in {"1", "true", "yes", "si", "sí"}


def normalizar_params(
    severity: Optional[str] = None,
    horas: Any = None,
    limite: Any = None,
    aliado_codigo: Optional[str] = None,
    contacto_id: Optional[str] = None,
    admin_codigo: Optional[str] = None,
    identificador: Optional[str] = None,
    page_token: Optional[str] = None,
    insert_id: Optional[str] = None,
    incluir_stack: Any = None,
) -> Dict[str, Any]:
    sev = (severity or "ERROR").strip().upper()
    if sev not in _SEVERIDADES:
        raise ValueError("severity debe ser ERROR, WARNING o ALL")
    try:
        horas_n = int(horas if horas not in (None, "") else _HORAS_DEFAULT)
    except (TypeError, ValueError) as exc:
        raise ValueError("horas debe ser un entero") from exc
    if horas_n < 1 or horas_n > _HORAS_MAX:
        raise ValueError(f"horas debe estar entre 1 y {_HORAS_MAX}")
    try:
        limite_n = int(limite if limite not in (None, "") else _LIMITE_DEFAULT)
    except (TypeError, ValueError) as exc:
        raise ValueError("limite debe ser un entero") from exc
    if limite_n < 1 or limite_n > _LIMITE_MAX:
        raise ValueError(f"limite debe estar entre 1 y {_LIMITE_MAX}")

    aliado = (aliado_codigo or "").strip()
    contacto = (contacto_id or "").strip()
    admin = (admin_codigo or "").strip()
    ident = (identificador or "").strip()
    if ident and not (aliado or contacto or admin):
        if ident.isdigit():
            contacto = ident
        elif "ADMIN" in ident.upper():
            admin = ident
        else:
            aliado = ident

    return {
        "severity": sev,
        "horas": horas_n,
        "limite": limite_n,
        "aliado_codigo": aliado,
        "contacto_id": contacto,
        "admin_codigo": admin,
        "page_token": (page_token or "").strip() or None,
        "insert_id": (insert_id or "").strip() or None,
        "incluir_stack": _truthy(incluir_stack),
    }


def construir_filtro(
    *,
    severity: str,
    horas: int,
    service_name: str = _SERVICE_DEFAULT,
    aliado_codigo: str = "",
    contacto_id: str = "",
    admin_codigo: str = "",
    insert_id: Optional[str] = None,
    ahora: Optional[datetime] = None,
) -> str:
    since = (ahora or _ahora_utc()) - timedelta(hours=horas)
    since_rfc = since.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    if severity == "ERROR":
        sev_clause = "severity>=ERROR"
    elif severity == "WARNING":
        sev_clause = "severity=WARNING"
    else:
        sev_clause = "severity>=WARNING"
    parts = [
        'resource.type="cloud_run_revision"',
        f'resource.labels.service_name="{_escape_filter_value(service_name)}"',
        sev_clause,
        f'timestamp>="{since_rfc}"',
    ]
    if insert_id:
        parts.append(f'insertId="{_escape_filter_value(insert_id)}"')
    for field, value in (
        ("aliado_codigo", aliado_codigo),
        ("contacto_id", contacto_id),
        ("admin_codigo", admin_codigo),
    ):
        if not value:
            continue
        safe = _escape_filter_value(str(value))
        parts.append(
            f'(jsonPayload.{field}="{safe}" OR jsonPayload.extra.{field}="{safe}" '
            f'OR labels.{field}="{safe}")'
        )
    return " AND ".join(parts)


def _como_dict(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, dict):
        return {str(k): _como_dict(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_como_dict(v) for v in value]
    items = getattr(value, "items", None)
    if callable(items):
        try:
            return {str(k): _como_dict(v) for k, v in items()}
        except Exception:
            pass
    return value


def _payload_de(entry: Any) -> Any:
    if isinstance(entry, dict):
        if "payload" in entry:
            return entry.get("payload")
        if "jsonPayload" in entry:
            return _como_dict(entry.get("jsonPayload"))
        return entry
    payload = getattr(entry, "payload", None)
    if payload is not None:
        return _como_dict(payload) if not isinstance(payload, str) else payload
    json_payload = getattr(entry, "json_payload", None)
    if json_payload:
        return _como_dict(json_payload)
    text = getattr(entry, "text_payload", None)
    if text:
        return text
    return None


def extra_desde_payload(payload: Any) -> Dict[str, Any]:
    if not isinstance(payload, dict):
        if isinstance(payload, str):
            text = payload.strip()
            if text.startswith("{") and text.endswith("}"):
                try:
                    import json
                    parsed = json.loads(text)
                except Exception:
                    return {}
                if isinstance(parsed, dict):
                    return extra_desde_payload(parsed)
        return {}
    nested = payload.get("extra")
    if isinstance(nested, dict):
        return dict(nested)
    extra: Dict[str, Any] = {}
    for key, value in payload.items():
        if key in _PAYLOAD_RESERVADO or str(key).startswith("logging.googleapis.com"):
            continue
        extra[key] = value
    return extra


def _stack_desde_payload(payload: Any, text_payload: str = "") -> Optional[str]:
    if isinstance(payload, dict):
        for key in ("stack_trace", "exc_info", "exception", "traceback"):
            val = payload.get(key)
            if val:
                return str(val)
    text = text_payload or (payload if isinstance(payload, str) else "")
    if "Traceback (most recent call last)" in str(text):
        return str(text)
    return None


def _logger_desde_entry(entry: Any, payload: Any) -> str:
    if isinstance(payload, dict):
        for key in ("logger", "loggerName", "python_logger", "name"):
            val = payload.get(key)
            if val:
                return str(val)
    if isinstance(entry, dict):
        raw = entry.get("logger") or entry.get("logName") or entry.get("log_name") or ""
        return str(getattr(raw, "name", raw) or "")
    logger_obj = getattr(entry, "logger", None)
    if logger_obj:
        return str(getattr(logger_obj, "name", logger_obj) or "")
    log_name = getattr(entry, "log_name", None) or getattr(entry, "logName", None)
    if log_name:
        name = str(log_name)
        if "/logs/" in name:
            name = name.rsplit("/logs/", 1)[-1]
        return name
    return ""


def _timestamp_iso(entry: Any) -> str:
    raw = entry.get("timestamp") if isinstance(entry, dict) else getattr(entry, "timestamp", None)
    if raw is None:
        return ""
    to_dt = getattr(raw, "ToDatetime", None) or getattr(raw, "to_datetime", None)
    if callable(to_dt):
        raw = to_dt()
    if isinstance(raw, datetime):
        if raw.tzinfo is None:
            raw = raw.replace(tzinfo=timezone.utc)
        return raw.astimezone(timezone.utc).isoformat()
    return str(raw)


def _severity_de(entry: Any, payload: Any) -> str:
    raw = None
    if isinstance(entry, dict):
        raw = entry.get("severity")
    else:
        raw = getattr(entry, "severity", None)
    if raw is not None and raw != "":
        name = getattr(raw, "name", None)
        text = str(name or raw)
        if "." in text:
            text = text.rsplit(".", 1)[-1]
        text = text.upper()
        if text and text != "SEVERITY_UNSPECIFIED":
            return text
    if isinstance(payload, dict) and payload.get("severity"):
        return str(payload.get("severity")).upper()
    return ""


def _mensaje_de(payload: Any) -> str:
    if isinstance(payload, dict):
        for key in ("message", "msg"):
            if payload.get(key):
                return str(payload.get(key))
        return ""
    if payload is None:
        return ""
    return str(payload)


def parsear_entrada(entry: Any, incluir_stack: bool = False) -> Dict[str, Any]:
    payload = _payload_de(entry)
    extra = extra_desde_payload(payload)
    text_payload = ""
    if isinstance(entry, dict):
        text_payload = str(entry.get("textPayload") or entry.get("text_payload") or "")
    else:
        text_payload = str(getattr(entry, "text_payload", "") or "")
        if not text_payload and isinstance(payload, str):
            text_payload = payload
    mensaje = _mensaje_de(payload) or text_payload.split("\n", 1)[0]
    item = {
        "timestamp": _timestamp_iso(entry),
        "severity": _severity_de(entry, payload),
        "mensaje": mensaje,
        "extra": extra,
        "logger": _logger_desde_entry(entry, payload),
        "insert_id": (
            (entry.get("insert_id") or entry.get("insertId") or "")
            if isinstance(entry, dict)
            else str(getattr(entry, "insert_id", "") or "")
        ),
    }
    if incluir_stack:
        item["stack"] = _stack_desde_payload(payload, text_payload)
    return item


def _es_error_permiso(exc: BaseException) -> bool:
    name = type(exc).__name__
    if name in {
        "PermissionDenied",
        "Forbidden",
        "Unauthenticated",
        "DefaultCredentialsError",
        "RefreshError",
    }:
        return True
    text = str(exc).lower()
    return any(
        token in text
        for token in (
            "permission denied",
            "permission_denied",
            "403",
            "logging.viewer",
            "default credentials",
            "could not automatically determine credentials",
            "reauthentication is needed",
        )
    )


def pagina_desde_iterador(iterator: Any, page_size: int) -> Tuple[List[Any], Optional[str]]:
    """Lee una página tanto de pagers GAPIC (.pages) como de generadores planos."""
    pages = getattr(iterator, "pages", None)
    if pages is not None:
        page = next(pages, None)
        entries = list(page) if page is not None else []
        token = getattr(iterator, "next_page_token", None) or None
        return entries, token or None
    entries = list(islice(iterator, page_size))
    token = getattr(iterator, "next_page_token", None) or None
    return entries, token or None


def listar_entradas(
    *,
    project_id: str,
    filtro: str,
    page_size: int,
    page_token: Optional[str] = None,
) -> Tuple[List[Any], Optional[str]]:
    from google.cloud.logging_v2.services.logging_service_v2 import LoggingServiceV2Client
    from google.cloud.logging_v2.types.logging import ListLogEntriesRequest

    client = LoggingServiceV2Client()
    request = ListLogEntriesRequest(
        resource_names=[f"projects/{project_id}"],
        filter=filtro,
        order_by="timestamp desc",
        page_size=page_size,
        page_token=page_token or "",
    )
    iterator = client.list_log_entries(request=request)
    return pagina_desde_iterador(iterator, page_size)


def consultar_logs_errores(
    *,
    severity: Optional[str] = None,
    horas: Any = None,
    limite: Any = None,
    aliado_codigo: Optional[str] = None,
    contacto_id: Optional[str] = None,
    admin_codigo: Optional[str] = None,
    identificador: Optional[str] = None,
    page_token: Optional[str] = None,
    insert_id: Optional[str] = None,
    incluir_stack: Any = None,
    list_entries_fn: Optional[ListEntriesFn] = None,
    project_id: Optional[str] = None,
    service_name: Optional[str] = None,
) -> Dict[str, Any]:
    params = normalizar_params(
        severity=severity,
        horas=horas,
        limite=limite,
        aliado_codigo=aliado_codigo,
        contacto_id=contacto_id,
        admin_codigo=admin_codigo,
        identificador=identificador,
        page_token=page_token,
        insert_id=insert_id,
        incluir_stack=incluir_stack,
    )
    settings = get_settings()
    project = (project_id or "").strip() or getattr(settings, "firebase_project_id", None) or "ruana-4293f"
    service = (service_name or "").strip() or _SERVICE_DEFAULT
    filtro = construir_filtro(
        severity=params["severity"],
        horas=params["horas"],
        service_name=service,
        aliado_codigo=params["aliado_codigo"],
        contacto_id=params["contacto_id"],
        admin_codigo=params["admin_codigo"],
        insert_id=params["insert_id"],
    )
    fn = list_entries_fn or listar_entradas
    try:
        entries, next_token = fn(
            project_id=project,
            filtro=filtro,
            page_size=params["limite"],
            page_token=params["page_token"],
        )
    except CloudLoggingPermissionError:
        raise
    except CloudLoggingQueryError:
        raise
    except Exception as exc:
        if _es_error_permiso(exc):
            raise CloudLoggingPermissionError(_MENSAJE_SIN_VIEWER) from exc
        raise CloudLoggingQueryError(str(exc) or "Error al consultar Cloud Logging") from exc

    return {
        "status": "success",
        "entradas": [parsear_entrada(entry, incluir_stack=params["incluir_stack"]) for entry in entries],
        "next_page_token": next_token or None,
        "filtro": {
            "severity": params["severity"],
            "horas": params["horas"],
            "limite": params["limite"],
            "aliado_codigo": params["aliado_codigo"] or None,
            "contacto_id": params["contacto_id"] or None,
            "admin_codigo": params["admin_codigo"] or None,
        },
    }
