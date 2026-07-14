#!/usr/bin/env python3
"""Prueba E2E de foto de perfil contra un despliegue RUANA (preview o prod)."""

from __future__ import annotations

import json
import sys
from io import BytesIO
from pathlib import Path
from urllib import error, request

from PIL import Image


def _http_json(url: str, *, method: str = "GET", headers: dict | None = None, data: bytes | None = None, content_type: str | None = None):
    hdrs = dict(headers or {})
    if data is not None and content_type:
        hdrs["Content-Type"] = content_type
    req = request.Request(url, data=data, headers=hdrs, method=method)
    with request.urlopen(req, timeout=60) as resp:
        body = resp.read().decode("utf-8")
        return resp.status, json.loads(body) if body else {}


def _multipart_body(field_name: str, filename: str, file_bytes: bytes, content_type: str) -> tuple[bytes, str]:
    boundary = "----ruana-foto-e2e"
    parts = [
        f"--{boundary}\r\n".encode(),
        f'Content-Disposition: form-data; name="{field_name}"; filename="{filename}"\r\n'.encode(),
        f"Content-Type: {content_type}\r\n\r\n".encode(),
        file_bytes,
        b"\r\n",
        f"--{boundary}--\r\n".encode(),
    ]
    body = b"".join(parts)
    return body, f"multipart/form-data; boundary={boundary}"


def main() -> int:
    base = (sys.argv[1] if len(sys.argv) > 1 else "https://ruana-preview-dqehtgjjea-ew.a.run.app").rstrip("/")
    codigo = sys.argv[2] if len(sys.argv) > 2 else "53100"

    img = Image.new("RGB", (1600, 1200), color=(90, 130, 210))
    buf = BytesIO()
    img.save(buf, format="JPEG", quality=92)
    foto_bytes = buf.getvalue()

    try:
        _, login = _http_json(
            f"{base}/api/aliado/login",
            method="POST",
            data=json.dumps({"codigo": codigo}).encode(),
            content_type="application/json",
        )
    except error.HTTPError as exc:
        print(f"login_failed: HTTP {exc.code}")
        return 1

    if login.get("status") != "success" or not login.get("session_id"):
        print("login_failed:", login)
        return 1

    session_id = login["session_id"]
    body, ctype = _multipart_body("archivo", "selfie.jpg", foto_bytes, "image/jpeg")

    try:
        status, upload = _http_json(
            f"{base}/api/aliados/{codigo}/foto-perfil",
            method="POST",
            headers={"X-Ruana-Session-Id": session_id},
            data=body,
            content_type=ctype,
        )
    except error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        print(f"upload_failed: HTTP {exc.code} {detail[:500]}")
        return 1

    if upload.get("status") != "success" or not upload.get("foto_perfil_url"):
        print("upload_failed:", upload)
        return 1

    foto_url = upload["foto_perfil_url"]
    print("upload_ok:", foto_url)

    _, datos = _http_json(
        f"{base}/api/aliado/datos",
        headers={"X-Ruana-Session-Id": session_id},
    )
    aliado = (datos or {}).get("aliado") or {}
    persisted = aliado.get("foto_perfil_url")
    if not persisted:
        print("persist_failed: foto_perfil_url vacío en /api/aliado/datos", datos)
        return 1
    print("persist_ok:", persisted)

    try:
        with request.urlopen(foto_url, timeout=30) as img_resp:
            if img_resp.status != 200:
                print(f"image_fetch_failed: HTTP {img_resp.status}")
                return 1
            content = img_resp.read(16)
    except Exception as exc:
        print(f"image_fetch_failed: {exc}")
        return 1

    if not content.startswith(b"\xff\xd8\xff"):
        print("image_fetch_failed: no parece JPEG")
        return 1

    print("image_ok: bytes", len(content), "+...")
    print("e2e_ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
