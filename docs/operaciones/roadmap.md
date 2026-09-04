# Roadmap operativo RUANA

> **Autoridad de producto/técnica:** [Manual Maestro §18](../../README.md#18-roadmap).  
> Histórico completo del roadmap de mayo 2026: [`docs/archive/ROADMAP_2026-05.md`](../archive/ROADMAP_2026-05.md).

Fecha de actualización: **2026-09-04** (auditoría documental vs código).

Pack documentación: [`docs/HANDOFF.md`](../HANDOFF.md) · [`docs/PROJECT_AUDIT.md`](../PROJECT_AUDIT.md) · [`docs/exports/AUDITORIA_DOCUMENTAL_2026-09-04.md`](../exports/AUDITORIA_DOCUMENTAL_2026-09-04.md).

## Estado actual

RUANA está en fase **pre-MVP avanzada** (v0.9).

Infra base (Hito 1) desplegable: Docker → Cloud Run, Firebase Hosting rewrite, Supabase Postgres/Storage, SQLite fallback.

**Enfoque activo (inferido de PRs abiertos y commits recientes):** endurecer CORS/RLS (PRs #195, #196, no fusionados), pulir Pulse/Centro de Actividad, operación Stripe (SERIAL, webhooks, modo Live), Hito 2 de permisos.

**Métricas verificadas (2026-09-04):** 21 blueprints, **326** rutas en blueprints + 34 en `app.py`, **37** services, **31** repos, **29** migraciones, 108 archivos `test_*.py`. Recuento de casos pytest: ver informe de auditoría del día. `DBManager` 1969 LOC; `app.py` 546 LOC.

## Hitos

| Hito | Estado | Notas |
|------|--------|-------|
| 1 — Auditoría e infra | Cerrado documentalmente | Supabase/Firebase/Cloud Run |
| 2 — Seguridad y permisos | Activo / parcial | 2A/2B con tests; CORS allowlist y RLS extra **en PRs abiertos**, no en `main` |
| Invitaciones admin + campañas | Hecho en código | Specs/planes en archive |
| Métodos de pago + Storage | Hecho en código | QR Bizum/IBAN + Supabase Storage. Datos de cobro **siguen en repo** (K-03/K-26) |
| Stripe Connect (pagos encargo) | Código hecho; modo prod **NO VERIFICADO** | Pipeline resuelve `RUANA_STRIPE_MODE` (ya no hardcode `test`). Ver `fase-14-stripe-live.md` |
| Impugnación cobros / alertas | Hecho en código | Plan en archive |
| Módulo financiero admin (FASE 01–11, 13A, 14) | Hecho en código | 7 blueprints `financial_*` + webhook + `pagos_bp`. **No existe FASE 12.** Hotfix SERIAL 2026-09-03 |
| Competencia automática por score | Hecho en main | Umbral 15, reinicio 50 |
| Crecimiento orgánico de grupos | Hecho en código | Migración 2026-08-19; máx. 10 recompensas × 5 score |
| Solicitudes semanales | Hecho en código | Blueprint + panel admin; RLS sin políticas |
| Centro de Actividad (Pulse) | Hecho en `main` (PRs #206/#208/#209) | PR #207 abierto (detalle Apoyo) |
| PIN aliado (código + PIN) | Hecho en código | Rate limit, bloqueo, recuperación email. Adopción prod **NO VERIFICADO** |
| Campamento Base (modularización) | Avanzado | 37 services + 31 repos; fachada `DBManager` (1969 LOC) |
| 21 blueprints HTTP | Hecho en main | 326 rutas API en blueprints |
| Admin → Firebase Auth | Preparado, no implementado | Plan 2026-07-27 en archive |
| Purga mensual automatizada | Lógica + endpoint + auth cron/OIDC | **Listo para Cloud Scheduler** — despliegue GCP **NO VERIFICADO** |
| Motor evaluación periódico | Motor v0.2 + endpoint cron | Umbrales ahora en JSON; cron GCP **NO VERIFICADO** |
| Pack documentación cierre | Hecho 2026-08-19; **revisado 2026-09-04** | Nueva auditoría documental |

## PRs abiertos relevantes (2026-09-04, `gh pr list`)

| PR | Rama | Título |
|----|------|--------|
| #207 | `cursor/fix-e2e-pulse-overlay-d659` | fix(pulse): detalle de Apoyo RUANA con la firma correcta del panel |
| #196 | `cursor/rls-public-tables-2cc1` | fix(security): RLS en tablas public (anon key) — no aplicar en prod aún |
| #195 | `cursor/cors-pago-manual-allowlist-2cc1` | fix(security): CORS explícito y pago manual por allowlist admin |

## Método

1. Un hito activo a la vez.  
2. Cambios pequeños verificables.  
3. Tests antes de tocar permisos, datos personales o dinero.  
4. El **código** y el **Manual Maestro** son la verdad; el archive es evidencia.

## Referencias

- Auditoría documental 2026-09-04: [`AUDITORIA_DOCUMENTAL_2026-09-04.md`](../exports/AUDITORIA_DOCUMENTAL_2026-09-04.md)
- Pack cierre 2026-08-19: [`docs/HANDOFF.md`](../HANDOFF.md), [`docs/PROJECT_AUDIT.md`](../PROJECT_AUDIT.md)
- Cron jobs: [`cloud_scheduler_jobs.md`](cloud_scheduler_jobs.md)
- Finanzas: [`../flujos/financial-overview.md`](../flujos/financial-overview.md)
- Histórico mayo 2026: `docs/archive/ROADMAP_2026-05.md`
- Auditoría forense congelada: `docs/archive/AUDITORIA_FORENSE_RUANA.md`
