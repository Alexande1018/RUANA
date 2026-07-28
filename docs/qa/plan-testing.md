# Plan QA Testing RUANA

> **Autoridad:** [Manual Maestro §15](../../README.md#15-despliegue-y-operaciones).  
> Copia histórica íntegra: [`docs/archive/qa/QA_TESTING_PLAN_RUANA.md`](../archive/qa/QA_TESTING_PLAN_RUANA.md).

Fecha del plan original: 2026-06-05.  
Herramienta: Playwright (`e2e/ruana-critical-flows.spec.js`), base `http://127.0.0.1:5000`, SQLite aislado.

## Objetivo

Validar de extremo a extremo funcionalidades críticas y dejar evidencias reproducibles: resultados automatizados, trazas, capturas en fallo y videos.

## Alcance cubierto por E2E

- Admin login y permisos  
- Invitaciones y campañas  
- Solicitudes de grupo  
- Chat y cierre de contactos  
- Pagos / Apoyo / impugnación  

## Cómo ejecutar

```bash
npm install
npx playwright test
# o scripts definidos en package.json
```

Pytest (backend):

```bash
pip install -r RUANA/web/requirements-dev.txt
pytest RUANA/tests
```

## Nota de coherencia

Al interpretar resultados, usar reglas del Manual Maestro (p. ej. `apoyo_pct=12`, chat 30 msgs, importe solo solicitante), no valores de docs archivados.
