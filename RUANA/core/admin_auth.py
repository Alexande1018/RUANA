"""Almacenamiento y verificación segura de credenciales de administrador.

Las contraseñas nunca se guardan en texto plano. El archivo de credenciales
vive fuera del repositorio (por defecto en .local-secrets/).
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Optional

from werkzeug.security import check_password_hash, generate_password_hash

_REPO_ROOT = Path(__file__).resolve().parents[2]
_DEFAULT_CREDENTIALS_PATH = _REPO_ROOT / ".local-secrets" / "admin_credentials.json"
_LEGACY_CODES_PATH = Path(__file__).resolve().parents[1] / "config" / "admin_codes.json"
_QA_CREDENTIALS_PATH = Path(__file__).resolve().parents[1] / "config" / "admin_credentials.qa.json"


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


def save_credentials(data: dict[str, Any]) -> None:
    path = get_credentials_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass


def _load_from_path(path: Path) -> Optional[dict[str, Any]]:
    if not path.exists():
        return None
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


def load_credentials(*, allow_bootstrap: bool = True) -> dict[str, Any]:
    env_json = os.environ.get("RUANA_ADMIN_CREDENTIALS_JSON", "").strip()
    if env_json:
        data = json.loads(env_json)
        if allow_bootstrap:
            save_credentials(data)
        return data

    path = get_credentials_path()
    data = _load_from_path(path)
    if data is not None:
        return data

    if allow_bootstrap and _LEGACY_CODES_PATH.exists():
        data = _migrate_from_legacy(_LEGACY_CODES_PATH)
        save_credentials(data)
        return data

    if allow_bootstrap and _QA_CREDENTIALS_PATH.exists():
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

    data = load_credentials(allow_bootstrap=False)
    admin = data.get("admins", {}).get(admin_id)
    if not admin:
        return {"status": "error", "message": "Administrador no encontrado"}
    if not admin.get("activo", True):
        return {"status": "error", "message": "Este administrador está desactivado"}

    stored_hash = admin.get("password_hash", "")
    if not stored_hash or not check_password_hash(stored_hash, current_password):
        return {"status": "error", "message": "La contraseña actual no es correcta"}

    admin["password_hash"] = hash_password(new_password)
    save_credentials(data)
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
