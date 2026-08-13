#!/usr/bin/env python3
"""
RUANA Code Map — servidor local con acceso al código fuente.

Sirve el visor en / y expone GET /api/src?path=RUANA/... para leer archivos
del repo (solo lectura, sin path traversal).

Uso:
    python3 dev-tools/code-map/serve.py
    # http://127.0.0.1:8842
"""
from __future__ import annotations

import json
import mimetypes
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[1]
HOST = "127.0.0.1"
PORT = 8842


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(HERE), **kwargs)

    def log_message(self, fmt, *args):
        sys_stderr = __import__("sys").stderr
        sys_stderr.write("[code-map] %s - %s\n" % (self.address_string(), fmt % args))

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/api/src":
            return self._serve_source(parsed.query)
        if parsed.path == "/api/health":
            return self._json({"ok": True, "repo_root": str(REPO_ROOT)})
        return super().do_GET()

    def _json(self, payload, status=200):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _serve_source(self, query: str):
        qs = parse_qs(query)
        rel = unquote((qs.get("path") or [""])[0]).lstrip("/")
        if not rel or ".." in Path(rel).parts:
            return self._json({"error": "path inválido"}, 400)
        target = (REPO_ROOT / rel).resolve()
        try:
            target.relative_to(REPO_ROOT.resolve())
        except ValueError:
            return self._json({"error": "fuera del repo"}, 403)
        if not target.is_file():
            return self._json({"error": "no existe"}, 404)
        try:
            text = target.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            return self._json({"error": str(exc)}, 500)
        # límite de seguridad para el visor
        max_chars = 200_000
        truncated = len(text) > max_chars
        if truncated:
            text = text[:max_chars]
        mime = mimetypes.guess_type(str(target))[0] or "text/plain"
        return self._json({
            "path": rel,
            "mime": mime,
            "truncated": truncated,
            "lines": text.count("\n") + 1,
            "content": text,
        })


def main():
    httpd = ThreadingHTTPServer((HOST, PORT), Handler)
    print(f"[code-map] sirviendo {HERE}")
    print(f"[code-map] repo root: {REPO_ROOT}")
    print(f"[code-map] abre http://{HOST}:{PORT}/")
    print(f"[code-map] standalone: http://{HOST}:{PORT}/ruana-code-map.html")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n[code-map] detenido")


if __name__ == "__main__":
    main()
