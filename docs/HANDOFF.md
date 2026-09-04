# Handoff — transferencia operativa RUANA

Documento para recibir el proyecto como **nuevo desarrollador**, **operador**, **auditor** o **comprador técnico**. Asume lectura previa del [`README.md`](../README.md).

| | |
|---|---|
| Fecha | 2026-09-04 |
| Estado producto | Pre-MVP avanzada (v0.9) — inferido de roadmap interno |
| Tests backend | Recuento del día: ver [`AUDITORIA_DOCUMENTAL_2026-09-04.md`](exports/AUDITORIA_DOCUMENTAL_2026-09-04.md). Histórico 2026-08-19: 784 passed, 11 skipped |

---

## 1. Qué es este sistema (30 segundos)

RUANA coordina redes locales de profesionales por código postal: plazas de oficio, score reputacional, encargos con negociación guiada, Apoyo económico a la red, panel admin y módulo financiero (Stripe + conflictos). Stack: **Flask monolito** en **Cloud Run**, BD **Supabase Postgres**, entrada **Firebase Hosting**.

---

## 2. Primer día — checklist

### Desarrollador

- [ ] Clonar repo y seguir [`SETUP.md`](SETUP.md)
- [ ] Copiar `.env.example` → `.env`; generar `FLASK_SECRET_KEY`
- [ ] Configurar credenciales admin locales (§3 SETUP)
- [ ] Ejecutar `python3 -m pytest RUANA/tests -q` — debe pasar (cifra vigente en el informe de auditoría del día)
- [ ] Arrancar app en `http://localhost:8080`
- [ ] Leer [`ARCHITECTURE.md`](ARCHITECTURE.md) y [`ENVIRONMENT_VARIABLES.md`](ENVIRONMENT_VARIABLES.md)
- [ ] Revisar regla Campamento Base en README §17 (extracción `DBManager` solo con test CI)

### Operador

- [ ] Acceso GCP proyecto `ruana-4293f` y Supabase project `qqlxgwbmtzcfrrobrfzy`
- [ ] Verificar secretos GitHub Actions listados en [`DEPLOYMENT.md`](DEPLOYMENT.md)
- [ ] Confirmar último deploy exitoso (`deploy-firebase.yml` en `main`)
- [ ] Smoke: `curl https://ruana-4293f.web.app/api/health`
- [ ] Revisar Cloud Run logs `[RUANA][BOOT]`
- [ ] Listar Cloud Scheduler jobs — **confirmación manual requerida**
- [ ] Revisar [`KNOWN_ISSUES.md`](KNOWN_ISSUES.md) ítems K-04, K-08

### Auditor

- [ ] Leer [`PROJECT_AUDIT.md`](PROJECT_AUDIT.md) completo
- [ ] Contrastar migraciones `supabase/migrations/` vs schema remoto
- [ ] Verificar auth: aliado **código + PIN**, admin JSON, cron secret **u OIDC**
- [ ] Revisar datos sensibles en `ruana_reglas_v1.json` (K-03)
- [ ] Confirmar modo Stripe prod (K-04)
- [ ] Ejecutar pytest localmente o revisar artefacto CI `ruana-qa-latest`

---

## 3. Mapa de documentación

| Necesidad | Documento |
|-----------|-----------|
| Visión producto + reglas negocio | [`/README.md`](../README.md) |
| Auditoría técnica | [`PROJECT_AUDIT.md`](PROJECT_AUDIT.md) |
| Arquitectura | [`ARCHITECTURE.md`](ARCHITECTURE.md) |
| Instalación | [`SETUP.md`](SETUP.md) |
| Deploy | [`DEPLOYMENT.md`](DEPLOYMENT.md) |
| Variables entorno | [`ENVIRONMENT_VARIABLES.md`](ENVIRONMENT_VARIABLES.md) |
| Issues conocidos | [`KNOWN_ISSUES.md`](KNOWN_ISSUES.md) |
| Flujos detallados | [`flujos/`](flujos/) |
| Seguridad | [`seguridad/`](seguridad/) |
| Cron | [`operaciones/cloud_scheduler_jobs.md`](operaciones/cloud_scheduler_jobs.md) |
| Roadmap | [`operaciones/roadmap.md`](operaciones/roadmap.md) |
| Histórico | [`archive/`](archive/) |

---

## 4. Puntos de entrada código

| Área | Ruta |
|------|------|
| App Flask | `RUANA/web/app.py` |
| API dominio | `RUANA/web/blueprints/` |
| Lógica negocio | `RUANA/core/services/` |
| SQL | `RUANA/core/repositories/` |
| Fachada legacy | `RUANA/core/db_manager.py` |
| Auth sesiones | `RUANA/core/auth_session.py` |
| PIN aliado | `RUANA/core/aliado_pin_auth.py`, `core/services/aliado_pin_service.py` |
| Finanzas | `RUANA/core/financial/`, `docs/flujos/financial-overview.md` |
| Config negocio | `RUANA/config/ruana_reglas_v1.json` |
| Tests | `RUANA/tests/` |
| E2E | `e2e/ruana-critical-flows.spec.js` |
| CI | `.github/workflows/` |
| Migraciones | `supabase/migrations/` |

---

## 5. Entornos y URLs

| Entorno | URL / servicio | Notas |
|---------|----------------|-------|
| Producción | `https://ruana-4293f.web.app` | Firebase → Cloud Run `ruana` |
| Preview | canal Firebase `dev` | Servicio `ruana-preview` — BD compartida **No verificada** |
| Local | `http://localhost:8080` o `:5000` | Ver K-13 |

---

## 6. Secretos y accesos (sin valores)

**No almacenar secretos en este documento.**

| Secreto | Ubicación esperada |
|---------|-------------------|
| `FLASK_SECRET_KEY` | GCP Secret Manager `ruana-flask-secret-key` |
| `DATABASE_URL` | GCP `ruana-database-url` |
| Supabase keys | GCP secrets + panel Supabase |
| Admin creds | GCP `ruana-admin-credentials` / GitHub `RUANA_ADMIN_CREDENTIALS_JSON` |
| SMTP | GitHub `RUANA_SMTP_PASSWORD` → GCP |
| Stripe | GitHub secrets → GCP |
| Cron | GitHub `RUANA_CRON_SECRET` → GCP |

Procedimiento admin: [`seguridad/credenciales-admin.md`](seguridad/credenciales-admin.md).

---

## 7. Operación recurrente

| Tarea | Frecuencia | Referencia |
|-------|------------|------------|
| Deploy prod | push `main` | DEPLOYMENT.md |
| Migraciones BD | bajo demanda | `npm run supabase:push` |
| Competencias vencidas | diario (si cron activo) | cloud_scheduler_jobs.md |
| Purga mensual | mensual | idem |
| Motor evaluación | semanal | idem |
| Automatización financiera | según config FASE 11 | `financial_automation_bp` |
| Rotación secretos | política equipo | No documentada en repo |

---

## 8. CI/CD resumen

```text
PR/push → ruana-qa.yml → pytest (gate)
push main/dev → ruana-qa.yml → pytest + Playwright (E2E no gate en PR)
push main → deploy-firebase.yml → Cloud Run + Hosting
```

Rama convención agentes Cursor: `cursor/<nombre>-dccf`.

---

## 9. Decisiones que no revertir sin plan

1. Negociación guiada sustituye chat libre (410).
2. Score 0–500 con tope ±10/día.
3. Plaza = oficio principal; máx. 5 grupos por CP.
4. Apoyo = `apoyo_pct` sobre importe (default 12%).
5. Autorización en API Flask, no confiar en RLS.
6. Extracción Campamento Base: test CI antes de mover código de `DBManager`.

---

## 10. Deuda priorizada post-handoff

Orden sugerido (derivado de [`KNOWN_ISSUES.md`](KNOWN_ISSUES.md)):

1. Confirmar/desplegar Cloud Scheduler (K-08)
2. Revisar Stripe live vs test (K-04)
3. Paridad migraciones Postgres (K-05)
4. Externalizar datos cobro JSON (K-03)
5. Store sesiones compartido (K-06)
6. Completar migración admin Firebase Auth (K-16) — si roadmap confirma

---

## 11. Responsables y contacto

**No verificado** — el repositorio no define owners ni contactos operativos.

| Rol | Contacto |
|-----|----------|
| Producto | *Confirmar manualmente* |
| Tech lead | *Confirmar manualmente* |
| Ops / GCP | *Confirmar manualmente* |
| Supabase | Cuenta asociada a project `qqlxgwbmtzcfrrobrfzy` |

Completar esta sección antes de cierre legal/comercial.

---

## 12. Licencia

**Ausente.** No hay archivo `LICENSE` en el repositorio. Tratar como **all rights reserved** hasta que el propietario publique una licencia explícita.

---

## 13. Comandos de verificación rápida

```bash
# Tests
python3 -m pytest RUANA/tests -q

# Health prod
curl -sS https://ruana-4293f.web.app/api/health

# Conteo blueprints (21 esperados)
grep -c register_blueprint RUANA/web/app.py

# Listar migraciones
ls supabase/migrations/*.sql | wc -l   # 28 esperado
```

---

## 14. Historial de entregas documentales

| Fecha | Entrega |
|-------|---------|
| 2026-08-15 | Auditoría documental (`docs/exports/AUDITORIA_DOCUMENTAL_2026-08-15.md`) |
| 2026-08-19 | Pack cierre operativo (este documento + PROJECT_AUDIT, ARCHITECTURE, SETUP, DEPLOYMENT, ENV, KNOWN_ISSUES) |

---

*Tras cualquier cambio funcional, actualizar README §17 y el doc afectado. El código gana sobre la documentación.*
