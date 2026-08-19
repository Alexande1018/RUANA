# Documentación RUANA

## Fuente de verdad

El **Manual Maestro** es la entrada principal del proyecto:

- [`/README.md`](../README.md)

Si hay conflicto entre un documento secundario y el Manual Maestro, prevalece el Manual Maestro. Si el Manual diverge del **código**, prevalece el código.

---

## Pack de cierre operativo (2026-08-19)

Documentación para handoff, auditoría y continuidad operativa:

| Documento | Propósito |
|-----------|-----------|
| [`HANDOFF.md`](HANDOFF.md) | Checklist recepción, secretos, operación, contactos |
| [`PROJECT_AUDIT.md`](PROJECT_AUDIT.md) | Auditoría técnica exhaustiva del repositorio |
| [`ARCHITECTURE.md`](ARCHITECTURE.md) | Arquitectura verificada (capas, flujos, decisiones frágiles) |
| [`SETUP.md`](SETUP.md) | Instalación y ejecución local |
| [`DEPLOYMENT.md`](DEPLOYMENT.md) | CI/CD, Cloud Run, Firebase, cron |
| [`ENVIRONMENT_VARIABLES.md`](ENVIRONMENT_VARIABLES.md) | Referencia completa de variables de entorno |
| [`KNOWN_ISSUES.md`](KNOWN_ISSUES.md) | Problemas conocidos y limitaciones |

---

## Deep-dives por dominio

| Ruta | Contenido |
|------|-----------|
| [`seguridad/autenticacion-sesiones.md`](seguridad/autenticacion-sesiones.md) | Sesiones por pestaña y header `X-Ruana-Session-Id` |
| [`seguridad/credenciales-admin.md`](seguridad/credenciales-admin.md) | Credenciales admin en producción |
| [`flujos/registro-aliados.md`](flujos/registro-aliados.md) | Registro, plazas y suplentes |
| [`flujos/chat-y-alerta.md`](flujos/chat-y-alerta.md) | Mensajes de contacto y alertas (chat libre encargo → 410) |
| [`flujos/financial-*.md`](flujos/) | Máquina de estados, transferencias, webhooks financieros |
| [`operaciones/roadmap.md`](operaciones/roadmap.md) | Roadmap operativo |
| [`operaciones/cloud_scheduler_jobs.md`](operaciones/cloud_scheduler_jobs.md) | Jobs cron HTTP |
| [`qa/plan-testing.md`](qa/plan-testing.md) | Plan QA / Playwright |
| [`qa/solicitudes-flow.md`](qa/solicitudes-flow.md) | Nota QA solicitudes |

---

## Informes y reorganización

| Ruta | Contenido |
|------|-----------|
| [`exports/AUDITORIA_DOCUMENTAL_2026-08-15.md`](exports/AUDITORIA_DOCUMENTAL_2026-08-15.md) | Auditoría documental anterior |
| [`INFORME_REORGANIZACION_DOCS.md`](INFORME_REORGANIZACION_DOCS.md) | Informe reorganización documental |
| [`archive/`](archive/) | Documentación histórica (no borrar) |

Copia histórica del README extenso: [`archive/README_RUANA_COMPLETO.md`](archive/README_RUANA_COMPLETO.md).

---

## Herramientas locales

- Mapa interactivo del código: [`dev-tools/code-map/`](../dev-tools/code-map/)
