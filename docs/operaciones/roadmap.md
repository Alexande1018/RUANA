# Roadmap operativo RUANA

> **Autoridad de producto/técnica:** [Manual Maestro §18](../../README.md#18-roadmap).  
> Histórico completo del roadmap de mayo 2026: [`docs/archive/ROADMAP_2026-05.md`](../archive/ROADMAP_2026-05.md).

Fecha de actualización: **2026-08-19** (FASE 14 cierre de pagos).

## Estado actual

RUANA está en fase **pre-MVP avanzada** (v0.9).

Infra base (Hito 1) desplegable: Docker → Cloud Run, Firebase Hosting rewrite, Supabase Postgres/Storage, SQLite fallback.

**Enfoque activo:** cerrar superficie crítica de seguridad/permisos (Hito 2), paridad migraciones Postgres, y consolidar operación.

## Hitos

| Hito | Estado | Notas |
|------|--------|-------|
| 1 — Auditoría e infra | Cerrado documentalmente | Supabase/Firebase/Cloud Run |
| 2 — Seguridad y permisos | Activo / parcial | 2A/2B con tests; endurecimientos pendientes |
| Invitaciones admin + campañas | Hecho en código | Specs/planes en archive |
| Métodos de pago + Storage | Hecho en código | QR Bizum/IBAN + Supabase Storage |
| Stripe Connect (pagos encargo) | FASE 14: Test en prod; **Live bloqueado** | Céntimos enteros + rate limit; ver `docs/operaciones/fase-14-stripe-live.md` |
| Impugnación cobros / alertas | Hecho en código | Plan en archive |
| Competencia automática por score | Hecho en main | Umbral 15, reinicio 50 |
| Campamento Base (modularización) | Avanzado | 16 services + 16 repos; fachada `DBManager` residual (~1.835 LOC) |
| 13 blueprints HTTP | Hecho en main | Rutas API extraídas de monolito `app.py` |
| Admin → Firebase Auth | Preparado, no implementado | Plan 2026-07-27 en archive |
| Purga mensual automatizada | Lógica + endpoint + auth cron | **Listo para Cloud Scheduler** — ver `docs/operaciones/cloud_scheduler_jobs.md` |
| Motor evaluación periódico | Motor v0.2 + `POST /api/admin/motor/evaluar-periodico` | **Listo para Cloud Scheduler** — ver `docs/operaciones/cloud_scheduler_jobs.md` |

## Método

1. Un hito activo a la vez.  
2. Cambios pequeños verificables.  
3. Tests antes de tocar permisos, datos personales o dinero.  
4. El **código** y el **Manual Maestro** son la verdad; el archive es evidencia.

## Referencias

- Auditoría documental 2026-08-15: [`docs/exports/AUDITORIA_DOCUMENTAL_2026-08-15.md`](../exports/AUDITORIA_DOCUMENTAL_2026-08-15.md)
- Roadmap antiguo citaba `HITOS_PROYECTO.md` y `AUDITORIA_RUANA_2026-05-19.md`, **ausentes** en el repositorio.
- Auditoría forense congelada: `docs/archive/AUDITORIA_FORENSE_RUANA.md`
