# Roadmap operativo RUANA

> **Autoridad de producto/técnica:** [Manual Maestro §17](../../README.md#17-roadmap).  
> Histórico completo del roadmap de mayo 2026: [`docs/archive/ROADMAP_2026-05.md`](../archive/ROADMAP_2026-05.md).

Fecha de actualización: 2026-07-28.

## Estado actual

RUANA está en fase **pre-MVP avanzada** (v0.9).

Infra base (Hito 1) desplegable: Docker → Cloud Run, Firebase Hosting rewrite, Supabase Postgres/Storage, SQLite fallback.

**Enfoque activo:** cerrar superficie crítica de seguridad/permisos (Hito 2) y consolidar documentación/operación.

## Hitos

| Hito | Estado | Notas |
|------|--------|-------|
| 1 — Auditoría e infra | Cerrado documentalmente | Supabase/Firebase/Cloud Run |
| 2 — Seguridad y permisos | Activo / parcial | 2A cubierto con tests; quedan endurecimientos de endpoints públicos |
| Invitaciones admin + campañas | Hecho en código | Specs/planes en archive |
| Métodos de pago + Storage | Hecho en código | Plan en archive |
| Impugnación cobros / alertas | Hecho en código | Plan en archive |
| Competencia automática por score | Hecho en main | Umbral 15, reinicio 50 |
| Admin → Firebase Auth | Preparado, no implementado | Plan 2026-07-27 en archive |

## Método

1. Un hito activo a la vez.  
2. Cambios pequeños verificables.  
3. Tests antes de tocar permisos, datos personales o dinero.  
4. El **código** y el **Manual Maestro** son la verdad; el archive es evidencia.

## Referencias rotas del roadmap antiguo

El roadmap de mayo citaba `HITOS_PROYECTO.md` y `AUDITORIA_RUANA_2026-05-19.md`, **ausentes** en el repositorio. La auditoría forense vigente (congelada) está en `docs/archive/AUDITORIA_FORENSE_RUANA.md` y exports PDF/DOCX.
