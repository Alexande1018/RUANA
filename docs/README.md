# Documentación RUANA

## Fuente de verdad

El **Manual Maestro** es la entrada principal del proyecto:

- [`/README.md`](../README.md)

Si hay conflicto entre un documento secundario y el Manual Maestro, prevalece el Manual Maestro. Si el Manual diverge del **código**, prevalece el código.

Auditoría documental vigente: [`exports/AUDITORIA_DOCUMENTAL_2026-09-04.md`](exports/AUDITORIA_DOCUMENTAL_2026-09-04.md).  
Anterior (histórico, no borrar): [`exports/AUDITORIA_DOCUMENTAL_2026-08-15.md`](exports/AUDITORIA_DOCUMENTAL_2026-08-15.md).

---

## Pack de cierre operativo (2026-08-19, revisado 2026-09-04)

Documentación para handoff, auditoría y continuidad operativa. Las cifras de blueprints/services/tests de agosto se actualizaron el 2026-09-04.

| Documento | Propósito |
|-----------|-----------|
| [`HANDOFF.md`](HANDOFF.md) | Checklist recepción, secretos, operación, contactos |
| [`PROJECT_AUDIT.md`](PROJECT_AUDIT.md) | Auditoría técnica del repositorio (revisar junto al informe 2026-09-04) |
| [`ARCHITECTURE.md`](ARCHITECTURE.md) | Arquitectura verificada (capas, flujos, decisiones frágiles) |
| [`SETUP.md`](SETUP.md) | Instalación y ejecución local |
| [`DEPLOYMENT.md`](DEPLOYMENT.md) | CI/CD, Cloud Run, Firebase, cron |
| [`ENVIRONMENT_VARIABLES.md`](ENVIRONMENT_VARIABLES.md) | Referencia de variables de entorno |
| [`KNOWN_ISSUES.md`](KNOWN_ISSUES.md) | Problemas conocidos y limitaciones |

---

## Deep-dives por dominio

| Ruta | Contenido |
|------|-----------|
| [`seguridad/autenticacion-sesiones.md`](seguridad/autenticacion-sesiones.md) | Sesiones por pestaña + **login código+PIN** |
| [`seguridad/credenciales-admin.md`](seguridad/credenciales-admin.md) | Credenciales admin en producción (puente temporal) |
| [`legal/politica-retencion-datos.md`](legal/politica-retencion-datos.md) | Retención RGPD/LGT por tipo de dato (borrador interno) |
| [`flujos/registro-aliados.md`](flujos/registro-aliados.md) | Registro, plazas y suplentes |
| [`flujos/chat-y-alerta.md`](flujos/chat-y-alerta.md) | Mensajes de contacto y alertas (chat libre encargo → 410) |
| [`flujos/solicitudes-semanales.md`](flujos/solicitudes-semanales.md) | Tablero semanal (distinto de solicitudes de grupo) |
| [`flujos/grupo-crecimiento.md`](flujos/grupo-crecimiento.md) | Crecimiento orgánico de grupos en creación |
| [`flujos/pulse-centro-actividad.md`](flujos/pulse-centro-actividad.md) | Centro de Actividad (RUANA Pulse) |
| [`flujos/financial-overview.md`](flujos/financial-overview.md) | Subsistema financiero FASE 01–11 / 13A / 14 |
| [`flujos/financial-*.md`](flujos/) | Máquina de estados, transferencias, webhooks |
| [`operaciones/roadmap.md`](operaciones/roadmap.md) | Roadmap operativo vivo |
| [`operaciones/cloud_scheduler_jobs.md`](operaciones/cloud_scheduler_jobs.md) | Jobs cron HTTP (secreto + OIDC) |
| [`operaciones/fase-14-stripe-live.md`](operaciones/fase-14-stripe-live.md) | Resolución de modo Stripe (Live/Test) |
| [`qa/plan-testing.md`](qa/plan-testing.md) | Plan QA / Playwright |
| [`qa/solicitudes-flow.md`](qa/solicitudes-flow.md) | Nota QA solicitudes |

---

## Informes y reorganización

| Ruta | Contenido |
|------|-----------|
| [`exports/AUDITORIA_DOCUMENTAL_2026-09-04.md`](exports/AUDITORIA_DOCUMENTAL_2026-09-04.md) | Auditoría documental vigente |
| [`exports/AUDITORIA_DOCUMENTAL_2026-08-15.md`](exports/AUDITORIA_DOCUMENTAL_2026-08-15.md) | Auditoría anterior (histórico) |
| [`INFORME_REORGANIZACION_DOCS.md`](INFORME_REORGANIZACION_DOCS.md) | Informe reorganización documental |
| [`archive/`](archive/) | Documentación histórica (no borrar) |

Copia histórica del README extenso: [`archive/README_RUANA_COMPLETO.md`](archive/README_RUANA_COMPLETO.md).

---

## Herramientas locales

- Mapa interactivo del código: [`dev-tools/code-map/`](../dev-tools/code-map/)
