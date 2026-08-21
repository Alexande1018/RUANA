# Capturas de landing RUANA

Set corporativo de 10 pantallas reales de producto, con el mismo viewport (1440x900 @2x), el mismo zoom y el mismo marco de navegador macOS.

No incluye login ni ajustes. Los PNG enmarcados son el entregable para la landing.

| # | Archivo | Vista |
|---|---------|-------|
| 1 | `01-dashboard-aliado.png` | Dashboard principal del aliado |
| 2 | `02-panel-admin.png` | Command Center de administracion |
| 3 | `03-negociacion-guiada.png` | Negociacion guiada en curso |
| 4 | `04-grupos-territorio.png` | Grupos, codigo postal y plazas |
| 5 | `05-score-operativo.png` | Score y estado operativo de la red |
| 6 | `06-pagos-apoyo.png` | Pagos / Apoyo RUANA / revision admin |
| 7 | `07-directorio-red.png` | Directorio de aliados del grupo |
| 8 | `08-perfil-aliado.png` | Perfil y catalogo de servicios |
| 9 | `09-notificaciones.png` | Centro de avisos |
| 10 | `10-competencia-suplencia.png` | Competencia activa (titular vs retador) |

Regenerar:

```bash
bash scripts/landing/run_landing_screenshots.sh
```

Los recortes internos sin marco se generan en `raw/` (ignorado por git).
