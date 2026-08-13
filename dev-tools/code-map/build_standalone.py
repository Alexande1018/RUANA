#!/usr/bin/env python3
"""
Genera ruana-code-map.html autocontenido (graph.json embebido).
Atlas ya no depende de Sigma/WebGL: SVG nativo + JSON.
"""
from __future__ import annotations

from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE / "ruana-code-map.html"
ARTIFACT_OUT = Path("/opt/cursor/artifacts/ruana-code-map.html")


def main() -> None:
    index = (HERE / "index.html").read_text(encoding="utf-8")
    graph = (HERE / "graph.json").read_text(encoding="utf-8")

    marker = "<title>RUANA Atlas</title>"
    if marker not in index:
        raise SystemExit("No encontré el título RUANA Atlas en index.html")

    # Insertar JSON embebido justo después del title
    injection = (
        marker
        + '\n<script type="application/json" id="embedded-graph">'
        + graph
        + "</script>"
    )
    index = index.replace(marker, injection, 1)
    index = index.replace(
        "<title>RUANA Atlas</title>",
        "<title>RUANA Atlas (standalone)</title>",
        1,
    )

    OUT.write_text(index, encoding="utf-8")
    print(f"[code-map] standalone escrito: {OUT} ({OUT.stat().st_size:,} bytes)")
    try:
        ARTIFACT_OUT.parent.mkdir(parents=True, exist_ok=True)
        ARTIFACT_OUT.write_text(index, encoding="utf-8")
        print(f"[code-map] copia artefacto: {ARTIFACT_OUT}")
    except OSError as exc:
        print(f"[code-map] (aviso) artifacts: {exc}")


if __name__ == "__main__":
    main()
