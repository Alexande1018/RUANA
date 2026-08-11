# Informes descargables RUANA

## Manual Maestro (fuente de verdad)

| Archivo | Formato | Descripción |
|---|---|---|
| [README_RUANA_COMPLETO.docx](./README_RUANA_COMPLETO.docx) | Microsoft Word | Export del Manual Maestro (generado desde `/README.md`) |
| [README_RUANA_COMPLETO.pdf](./README_RUANA_COMPLETO.pdf) | PDF | Export del Manual Maestro (generado desde `/README.md`) |
| [`../../README.md`](../../README.md) | Markdown | Fuente única del Manual Maestro |

Regenerar:

```bash
pip install python-docx fpdf2
python scripts/generate_manual_maestro_documents.py
```

## Auditoría forense (foto congelada — 26 jul 2026)

| Archivo | Formato | Descripción |
|---|---|---|
| [AUDITORIA_FORENSE_RUANA.pdf](./AUDITORIA_FORENSE_RUANA.pdf) | PDF | Informe completo |
| [AUDITORIA_FORENSE_RUANA.docx](./AUDITORIA_FORENSE_RUANA.docx) | Microsoft Word | Editable |

Fuente Markdown archivada: [`docs/archive/AUDITORIA_FORENSE_RUANA.md`](../archive/AUDITORIA_FORENSE_RUANA.md).

> La verdad actual del producto está en el [Manual Maestro](../../README.md).
