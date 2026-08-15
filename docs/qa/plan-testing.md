# Plan QA Testing RUANA

> **Autoridad:** [Manual Maestro §12–13](../../README.md#12-desarrollo-local).  
> Copia histórica íntegra: [`docs/archive/qa/QA_TESTING_PLAN_RUANA.md`](../archive/qa/QA_TESTING_PLAN_RUANA.md).

Fecha del plan original: 2026-06-05.  
Última verificación contra código: **2026-08-15**.

Herramienta E2E: Playwright (`e2e/ruana-critical-flows.spec.js`), base `http://127.0.0.1:5000`, SQLite aislado.

## Objetivo

Validar de extremo a extremo funcionalidades críticas y dejar evidencias reproducibles: resultados automatizados, trazas, capturas en fallo y videos.

## Cobertura verificada

### Pytest (`RUANA/tests/`)

- **383 tests** pasando (verificado 2026-08-15 en entorno local con SQLite).
- Dominios cubiertos: admin, aliado, auth/permisos (Hito 2A/2B), invitaciones/campañas, referidos, grupos/plazas/competencia, contactos, negociación, chat timestamps, pagos/Stripe, score (reglas 3–8), storage, catálogo, blueprints/services.

### Playwright E2E (`e2e/`)

10 escenarios en `ruana-critical-flows.spec.js`:

- Admin login, resumen, registros, score, solicitudes y pagos
- Invitaciones y creación de aliado
- Campañas admin + permisos solo lectura
- Solicitudes de grupo (QA-08/09)
- **Negociación guiada** (QA-12/13/14) — usa `#modal-negociacion-guiada` (no chat libre)
- Cierre de importe y restricciones ofertador
- Aprobación/rechazo de pagos admin
- Encargo, confirmación, pago y revisión
- Impugnación y conflictos

## CI (`.github/workflows/ruana-qa.yml`)

| Trigger | Job pytest | Job E2E |
|---------|------------|---------|
| push `main`/`dev` | ✅ | ✅ (tras pytest) |
| pull_request `main`/`dev` | ✅ | ❌ |
| `workflow_dispatch` | ✅ | ✅ |

## Cómo ejecutar

```bash
pip install -r RUANA/web/requirements-dev.txt
PYTHONPATH=RUANA RUANA_DB_PATH=/tmp/ruana_test.db FLASK_SECRET_KEY=test_key \
  python3 -m pytest RUANA/tests -q

npm ci
npx playwright install --with-deps chromium
npm run qa:e2e
```

## Nota de coherencia

Al interpretar resultados, usar reglas del Manual Maestro y valores verificados en código:

- `apoyo_pct = 12.0` → `comision_porcentaje = 0.12` en runtime
- Chat mensajes: máx. **30** totales, vigencia **48 h**
- Flujo de encargo: **negociación guiada**, no chat libre global (rutas legacy → 410)

No usar valores de docs archivados (p. ej. límite de 5 mensajes, chat como flujo principal).
