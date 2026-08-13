#!/usr/bin/env python3
"""
Genera ruana-code-map.html: un solo archivo autocontenido (libs + graph.json)
que se puede abrir en Brave/Chrome con doble clic (file://), sin servidor.
"""
from __future__ import annotations

from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE / "ruana-code-map.html"
ARTIFACT_OUT = Path("/opt/cursor/artifacts/ruana-code-map.html")


def main() -> None:
    index = (HERE / "index.html").read_text(encoding="utf-8")
    libs = (HERE / "vendor" / "code-map-libs.js").read_text(encoding="utf-8")
    graph = (HERE / "graph.json").read_text(encoding="utf-8")

    old_script = '<script src="vendor/code-map-libs.js"></script>'
    if old_script not in index:
        raise SystemExit("No encontré la etiqueta vendor/code-map-libs.js en index.html")

    # Bundle + JSON embebido (loadGraph de index.html ya lo lee si existe #embedded-graph)
    replacement = (
        "<script>\n" + libs + "\n</script>\n"
        '<script type="application/json" id="embedded-graph">'
        + graph
        + "</script>"
    )
    index = index.replace(old_script, replacement, 1)
    index = index.replace(
        "<title>RUANA Code Map</title>",
        "<title>RUANA Code Map (standalone)</title>",
        1,
    )

    OUT.write_text(index, encoding="utf-8")
    print(f"[code-map] standalone escrito: {OUT} ({OUT.stat().st_size:,} bytes)")

    try:
        ARTIFACT_OUT.parent.mkdir(parents=True, exist_ok=True)
        ARTIFACT_OUT.write_text(index, encoding="utf-8")
        print(f"[code-map] copia artefacto: {ARTIFACT_OUT}")
    except OSError as exc:
        print(f"[code-map] (aviso) no se pudo copiar a artifacts: {exc}")


if __name__ == "__main__":
    main()
