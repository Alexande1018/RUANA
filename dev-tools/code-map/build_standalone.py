#!/usr/bin/env python3
"""Genera ruana-code-map.html con graph.json embebido (mapa Earth, SVG nativo)."""
from __future__ import annotations
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE / "ruana-code-map.html"
ARTIFACT = Path("/opt/cursor/artifacts/ruana-code-map.html")


def main() -> None:
    html = (HERE / "index.html").read_text(encoding="utf-8")
    graph = (HERE / "graph.json").read_text(encoding="utf-8")
    marker = "<title>RUANA — Mapa del territorio</title>"
    if marker not in html:
        raise SystemExit("título no encontrado")
    html = html.replace(
        marker,
        marker + '\n<script type="application/json" id="embedded-graph">' + graph + "</script>",
        1,
    )
    html = html.replace(marker, "<title>RUANA — Mapa (standalone)</title>", 1)
    OUT.write_text(html, encoding="utf-8")
    print(f"[mapa] standalone: {OUT} ({OUT.stat().st_size:,} bytes)")
    try:
        ARTIFACT.parent.mkdir(parents=True, exist_ok=True)
        ARTIFACT.write_text(html, encoding="utf-8")
        print(f"[mapa] artifact: {ARTIFACT}")
    except OSError as e:
        print("[mapa] artifact skip:", e)


if __name__ == "__main__":
    main()
