# Roadmap operativo RUANA

> **Autoridad de producto/técnica:** [Manual Maestro §18](../../README.md#18-roadmap).  
> Histórico completo del roadmap de mayo 2026: [`docs/archive/ROADMAP_2026-05.md`](../archive/ROADMAP_2026-05.md).

Fecha de actualización: **2026-09-04** (auditoría documental completa).

Pack documentación: [`docs/HANDOFF.md`](../HANDOFF.md) · [`docs/PROJECT_AUDIT.md`](../PROJECT_AUDIT.md) · [`docs/exports/AUDITORIA_DOCUMENTAL_2026-09-04.md`](../exports/AUDITORIA_DOCUMENTAL_2026-09-04.md).

## Estado actual

RUANA está en fase **pre-MVP avanzada** (v0.9).

Infra base (Hito 1) desplegable: Docker → Cloud Run, Firebase Hosting rewrite, Supabase Postgres/Storage, SQLite fallback.

**Enfoque activo:** cerrar superficie crítica de seguridad/permisos (Hito 2), paridad migraciones Postgres, confirmar cron en GCP, CORS allowlist, y consolidar operación post-handoff.

**Métricas verificadas (2026-09-04):** 21 blueprints, 37 services, 31 repos, 29 migraciones PG, **1007 tests** pytest passed (11 skipped).

## Hitos

| Hito | Estado | Notas |
|------|--------|-------|
| 1 — Auditoría e infra | Cerrado documentalmente | Supabase/Firebase/Cloud Run |
| 2 — Seguridad y permisos | Activo / parcial | 2A/2B con tests; PIN aliado hecho; CORS allowlist en PR |
| Invitaciones admin + campañas | Hecho en código | Specs/planes en archive |
| Métodos de pago + Storage | Hecho en código | QR Bizum/IBAN + Supabase Storage |
| Stripe Connect (pagos encargo) | FASE 14: Test en prod; **Live bloqueado** | Céntimos enteros + rate limit; ver `docs/operaciones/fase-14-stripe-live.md` |
| Impugnación cobros / alertas | Hecho en código | Plan en archive |
| Módulo financiero admin (FASE 02–13) | Hecho en código | 7 blueprints `financial_*` + 14 services/repos financieros |
| Crecimiento orgánico de grupo | Hecho en código | Migración `20260819000100`; tests verdes |
| Solicitudes semanales | Hecho en código | Migración `20260819000200`; blueprint dedicado |
| Competencia automática por score | Hecho en main | Umbral 15, reinicio 50 |
| Campamento Base (modularización) | Avanzado | 37 services + 31 repos; fachada `DBManager` (~1.969 LOC) |
| 21 blueprints HTTP | Hecho en main | ~315 rutas API únicas + 34 HTML en `app.py` |
| Login aliado PIN + recuperación | Hecho en código | Código + PIN; rate limit; bloqueo; OTP email |
| Admin → Firebase Auth | Preparado, no implementado | Plan 2026-07-27 en archive |
| Purga mensual automatizada | Lógica + endpoint + auth cron | **Listo para Cloud Scheduler** — despliegue GCP **no verificado** |
| Motor evaluación periódico | Motor v0.2 + endpoint cron | **Listo para Cloud Scheduler** — despliegue GCP **no verificado** |
| Automatización financiera FASE 11 | Hecho en código | Endpoint cron documentado; despliegue GCP **no verificado** |
| Pack documentación cierre | Hecho 2026-08-19 | HANDOFF, PROJECT_AUDIT, ARCHITECTURE, etc. |
| Auditoría documental 2026-09-04 | Hecho | Informe en `docs/exports/` |
| CORS allowlist pagos manuales | **PR abierto** | Rama `cursor/cors-pago-manual-allowlist-2cc1` — no en `main` |
| Serial `financial_transfers.id` | Hecho en código | Migración `20260903000100`; PRs relacionados en ramas `cursor/financial-transfers-serial-*` |

## PRs abiertos relevantes (2026-09-04)

| Rama | Tema | Estado en `main` |
|------|------|------------------|
| `cursor/cors-pago-manual-allowlist-2cc1` | CORS allowlist | **No mergeado** |
| `cursor/financial-transfers-serial-2cc1` | Serial financial_transfers | **No mergeado** |
| `cursor/encargo-72-stripe-webhook-2cc1` | Ops encargo 72 / webhook | **No mergeado** |

> Lista obtenida de `git branch -r` en commit `7ea0fa1`. Estado de merge puede cambiar.

## Método

1. Un hito activo a la vez.  
2. Cambios pequeños verificables.  
3. Tests antes de tocar permisos, datos personales o dinero.  
4. El **código** y el **Manual Maestro** son la verdad; el archive es evidencia.

## Referencias

- Auditoría documental 2026-09-04: [`docs/exports/AUDITORIA_DOCUMENTAL_2026-09-04.md`](../exports/AUDITORIA_DOCUMENTAL_2026-09-04.md)
- Auditoría documental 2026-08-15: [`docs/exports/AUDITORIA_DOCUMENTAL_2026-08-15.md`](../exports/AUDITORIA_DOCUMENTAL_2026-08-15.md)
- Cron jobs: [`cloud_scheduler_jobs.md`](cloud_scheduler_jobs.md)
- Roadmap antiguo citaba `HITOS_PROYECTO.md` y `AUDITORIA_RUANA_2026-05-19.md`, **ausentes** en el repositorio.
- Auditoría forense congelada: `docs/archive/AUDITORIA_FORENSE_RUANA.md`
