"""Almacenamiento y verificación segura de credenciales de administrador.

PUENTE TEMPORAL: sustituir por Firebase Authentication + tabla admin_users.
Ver docs/superpowers/plans/2026-07-27-admin-firebase-auth-migration.md

Las contraseñas nunca se guardan en texto plano. En producción el JSON
(hasheado) vive en GCP Secret Manager. Un cambio desde el panel añade una
nueva versión de ese secreto; el fichero local solo es caché de instancia.
"""

from __future__ import annotations

import base64
import json
import logging
import os
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Optional

from werkzeug.security import check_password_hash, generate_password_hash

_REPO_ROOT = Path(__file__).resolve().parents[2]
_DEFAULT_CREDENTIALS_PATH = _REPO_ROOT / ".local-secrets" / "admin_credentials.json"
_LEGACY_CODES_PATH = Path(__file__).resolve().parents[1] / "config" / "admin_codes.json"
_QA_CREDENTIALS_PATH = Path(__file__).resolve().parents[1] / "config" / "admin_credentials.qa.json"
_METADATA_TOKEN_URL = (
    "http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default/token"
)
_DEFAULT_ADMIN_SECRET_NAME = "ruana-admin-credentials"

logger = logging.getLogger(__name__)


def get_credentials_path() -> Path:
    custom = os.environ.get("RUANA_ADMIN_CREDENTIALS_PATH", "").strip()
    if custom:
        return Path(custom)
    return _DEFAULT_CREDENTIALS_PATH


def hash_password(password: str) -> str:
    return generate_password_hash(password)


def _admin_record(
    *,
    nombre: str,
    password: str,
    descripcion: str = "",
    activo: bool = True,
    creado: str = "",
    permisos: Optional[list[str]] = None,
) -> dict[str, Any]:
    return {
        "nombre": nombre,
        "descripcion": descripcion,
        "activo": activo,
        "creado": creado,
        "permisos": permisos or [],
        "password_hash": hash_password(password),
    }


def _migrate_from_legacy(legacy_path: Path) -> dict[str, Any]:
    with open(legacy_path, encoding="utf-8") as handle:
        legacy = json.load(handle)

    admins: dict[str, Any] = {}
    for code, info in legacy.get("admin_codes", {}).items():
        admin_id = str(code).strip().upper()
        if not admin_id:
            continue
        admins[admin_id] = _admin_record(
            nombre=info.get("nombre", admin_id),
            password=admin_id,
            descripcion=info.get("descripcion", ""),
            activo=info.get("activo", True),
            creado=info.get("creado", ""),
            permisos=info.get("permisos", []),
        )
    return {"version": 1, "admins": admins}


def _is_runtime_production() -> bool:
    try:
        from core.runtime_environment import is_production

        return is_production()
    except Exception:
        return bool((os.environ.get("K_SERVICE") or "").strip())


def _should_use_secret_manager() -> bool:
    flag = (os.environ.get("RUANA_ADMIN_USE_SECRET_MANAGER") or "").strip().lower()
    if flag in {"1", "true", "yes"}:
        return True
    if flag in {"0", "false", "no"}:
        return False
    return _is_runtime_production()


def _gcp_project_id() -> str:
    return (
        os.environ.get("GOOGLE_CLOUD_PROJECT", "").strip()
        or os.environ.get("GCLOUD_PROJECT", "").strip()
        or os.environ.get("FIREBASE_PROJECT_ID", "").strip()
    )


def _admin_secret_name() -> str:
    return (
        os.environ.get("RUANA_ADMIN_GCP_SECRET_NAME", "").strip()
        or _DEFAULT_ADMIN_SECRET_NAME
    )


def _credentials_to_json(data: dict[str, Any]) -> str:
    return json.dumps(data, indent=2, ensure_ascii=False) + "\n"


def _sync_env_overlay(data: dict[str, Any]) -> None:
    if os.environ.get("RUANA_ADMIN_CREDENTIALS_JSON", "").strip():
        os.environ["RUANA_ADMIN_CREDENTIALS_JSON"] = json.dumps(
            data, ensure_ascii=False, separators=(",", ":")
        )


def save_credentials(data: dict[str, Any], *, persist_remote: bool = False) -> None:
    path = get_credentials_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(_credentials_to_json(data), encoding="utf-8")
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass
    _sync_env_overlay(data)
    if persist_remote:
        secret_manager_add_version(data)


def _load_from_path(path: Path) -> Optional[dict[str, Any]]:
    if not path.exists():
        return None
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


def _metadata_access_token(timeout: float = 3.0) -> str:
    request = urllib.request.Request(
        _METADATA_TOKEN_URL,
        headers={"Metadata-Flavor": "Google"},
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        payload = json.loads(response.read().decode("utf-8"))
    token = str(payload.get("access_token") or "").strip()
    if not token:
        raise RuntimeError("El servidor de metadatos no devolvió access_token")
    return token


def _secret_manager_url(suffix: str) -> str:
    project = _gcp_project_id()
    if not project:
        raise RuntimeError("GOOGLE_CLOUD_PROJECT / FIREBASE_PROJECT_ID no configurado")
    secret = _admin_secret_name()
    return (
        "https://secretmanager.googleapis.com/v1/"
        f"projects/{project}/secrets/{secret}{suffix}"
    )


def secret_manager_add_version(data: dict[str, Any], timeout: float = 10.0) -> None:
    token = _metadata_access_token()
    payload = {
        "payload": {
            "data": base64.b64encode(_credentials_to_json(data).encode("utf-8")).decode("ascii"),
        }
    }
    body = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        _secret_manager_url(":addSecretVersion"),
        data=body,
        method="POST",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            if response.status not in (200, 201):
                raise RuntimeError(f"Secret Manager respondió HTTP {response.status}")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace") if exc.fp else str(exc)
        raise RuntimeError(f"No se pudo añadir versión en Secret Manager: {detail}") from exc


def try_secret_manager_access_latest(timeout: float = 10.0) -> Optional[dict[str, Any]]:
    try:
        token = _metadata_access_token()
        request = urllib.request.Request(
            _secret_manager_url("/versions/latest:access"),
            method="GET",
            headers={"Authorization": f"Bearer {token}"},
        )
        with urllib.request.urlopen(request, timeout=timeout) as response:
            envelope = json.loads(response.read().decode("utf-8"))
        raw = base64.b64decode(envelope["payload"]["data"])
        data = json.loads(raw.decode("utf-8"))
        if not isinstance(data, dict) or not isinstance(data.get("admins"), dict):
            raise RuntimeError("El secreto admin no tiene el formato esperado")
        return data
    except Exception as exc:
        logger.warning("No se pudieron leer credenciales admin desde Secret Manager: %s", exc)
        return None


def load_credentials(*, allow_bootstrap: bool = True) -> dict[str, Any]:
    if _should_use_secret_manager():
        remote = try_secret_manager_access_latest()
        if remote is not None:
            if allow_bootstrap:
                save_credentials(remote, persist_remote=False)
            return remote

    path = get_credentials_path()
    data = _load_from_path(path)
    if data is not None:
        return data

    env_json = os.environ.get("RUANA_ADMIN_CREDENTIALS_JSON", "").strip()
    if env_json:
        data = json.loads(env_json)
        if allow_bootstrap:
            save_credentials(data, persist_remote=False)
        return data

    production = _is_runtime_production()
    if allow_bootstrap and not production and _LEGACY_CODES_PATH.exists():
        data = _migrate_from_legacy(_LEGACY_CODES_PATH)
        save_credentials(data)
        return data

    if allow_bootstrap and not production and _QA_CREDENTIALS_PATH.exists():
        data = _load_from_path(_QA_CREDENTIALS_PATH)
        if data is not None:
            save_credentials(data)
            return data

    return {"version": 1, "admins": {}}


def verify_admin_login(admin_id: str, password: str) -> Optional[dict[str, Any]]:
    admin_id = (admin_id or "").strip().upper()
    password = password or ""
    if not admin_id or not password:
        return None

    data = load_credentials()
    admin = data.get("admins", {}).get(admin_id)
    if not admin or not admin.get("activo", True):
        return None

    stored_hash = admin.get("password_hash", "")
    if not stored_hash or not check_password_hash(stored_hash, password):
        return None

    return {
        "codigo": admin_id,
        "nombre": admin.get("nombre", admin_id),
        "permisos": admin.get("permisos", []),
    }


def change_admin_password(
    admin_id: str,
    current_password: str,
    new_password: str,
) -> dict[str, Any]:
    admin_id = (admin_id or "").strip().upper()
    current_password = current_password or ""
    new_password = new_password or ""

    if not admin_id:
        return {"status": "error", "message": "Identificador de administrador requerido"}
    if not current_password or not new_password:
        return {"status": "error", "message": "La contraseña actual y la nueva son obligatorias"}
    if len(new_password) < 8:
        return {"status": "error", "message": "La nueva contraseña debe tener al menos 8 caracteres"}
    if current_password == new_password:
        return {"status": "error", "message": "La nueva contraseña debe ser distinta a la actual"}

    use_secret_manager = _should_use_secret_manager()
    if use_secret_manager:
        data = try_secret_manager_access_latest()
        if data is None:
            return {
                "status": "error",
                "message": "No se pudieron leer las credenciales desde Secret Manager",
            }
    else:
        data = load_credentials(allow_bootstrap=False)

    admin = data.get("admins", {}).get(admin_id)
    if not admin:
        return {"status": "error", "message": "Administrador no encontrado"}
    if not admin.get("activo", True):
        return {"status": "error", "message": "Este administrador está desactivado"}

    stored_hash = admin.get("password_hash", "")
    if not stored_hash or not check_password_hash(stored_hash, current_password):
        return {"status": "error", "message": "La contraseña actual no es correcta"}

    pending = {
        **data,
        "admins": {
            **dict(data.get("admins") or {}),
            admin_id: {**admin, "password_hash": hash_password(new_password)},
        },
    }

    if use_secret_manager:
        try:
            secret_manager_add_version(pending)
        except Exception:
            logger.exception("Fallo al persistir credenciales admin en Secret Manager")
            return {
                "status": "error",
                "message": (
                    "No se pudo guardar la contraseña en Secret Manager. "
                    "Inténtalo de nuevo; la contraseña anterior sigue activa."
                ),
            }

    save_credentials(pending, persist_remote=False)
    return {"status": "success", "message": "Contraseña actualizada correctamente"}


def bootstrap_from_legacy(legacy_path: Optional[Path] = None, output_path: Optional[Path] = None) -> Path:
    source = legacy_path or _LEGACY_CODES_PATH
    if not source.exists():
        raise FileNotFoundError(f"No se encontró el archivo legado: {source}")

    data = _migrate_from_legacy(source)
    if output_path is not None:
        previous = os.environ.get("RUANA_ADMIN_CREDENTIALS_PATH")
        os.environ["RUANA_ADMIN_CREDENTIALS_PATH"] = str(output_path)
        try:
            save_credentials(data)
        finally:
            if previous is None:
                os.environ.pop("RUANA_ADMIN_CREDENTIALS_PATH", None)
            else:
                os.environ["RUANA_ADMIN_CREDENTIALS_PATH"] = previous
    else:
        save_credentials(data)
    return get_credentials_path()
