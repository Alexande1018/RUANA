#!/usr/bin/env python3
"""Generate PDF and DOCX exports from README_RUANA_COMPLETO.md (Manual Maestro)."""

from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "README_RUANA_COMPLETO.md"
OUT_DIR = ROOT / "docs" / "exports"


def main() -> None:
    if not SOURCE.exists():
        # Fallback: identical Manual Maestro
        source = ROOT / "README.md"
    else:
        source = SOURCE

    spec = importlib.util.spec_from_file_location(
        "gen_aud", ROOT / "scripts" / "generate_auditoria_documents.py"
    )
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)

    lines = source.read_text(encoding="utf-8").splitlines()
    blocks = mod.parse_blocks(lines)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    docx_path = OUT_DIR / "README_RUANA_COMPLETO.docx"
    pdf_path = OUT_DIR / "README_RUANA_COMPLETO.pdf"
    mod.build_docx(blocks, docx_path)
    mod.build_pdf(blocks, pdf_path)
    print(f"DOCX: {docx_path} ({docx_path.stat().st_size:,} bytes)")
    print(f"PDF:  {pdf_path} ({pdf_path.stat().st_size:,} bytes)")


if __name__ == "__main__":
    main()
