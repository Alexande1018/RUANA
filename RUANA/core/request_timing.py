"""Timings de hot paths de entrada a paneles (Fase 0).

Añade Server-Timing y un log estructurado. No altera cuerpos ni auth.
"""

from __future__ import annotations

import logging
import time

from flask import Flask, g, request

logger = logging.getLogger("ruana.timing")

HOT_PATHS = frozenset({
    "/admin",
    "/aliado",
    "/aliado.html",
    "/api/aliado/datos",
    "/api/admin/dashboard-summary",
    "/api/aliados/listar",
    "/api/stats",
})


def normalize_path(path: str) -> str:
    raw = (path or "").strip() or "/"
    if raw != "/" and raw.endswith("/"):
        return raw.rstrip("/")
    return raw


def is_hot_path(path: str) -> bool:
    return normalize_path(path) in HOT_PATHS


def register_request_timing(app: Flask) -> None:
    @app.before_request
    def _ruana_timing_start():
        g.ruana_req_start = time.perf_counter()

    @app.after_request
    def _ruana_timing_emit(response):
        start = getattr(g, "ruana_req_start", None)
        if start is None:
            return response
        path = request.path or ""
        if not is_hot_path(path):
            return response
        dur_ms = (time.perf_counter() - start) * 1000.0
        response.headers["Server-Timing"] = f"app;dur={dur_ms:.1f}"
        logger.info(
            "ruana.timing path=%s status=%s dur_ms=%.1f",
            normalize_path(path),
            response.status_code,
            dur_ms,
        )
        return response
