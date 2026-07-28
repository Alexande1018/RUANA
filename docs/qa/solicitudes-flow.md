# QA — Flujo de solicitudes de grupo

> Copia histórica: [`docs/archive/qa/solicitudes-flow-qa.md`](../archive/qa/solicitudes-flow-qa.md).  
> Reglas: [Manual Maestro §5.8](../../README.md#58-solicitudes-de-grupo).

## Objetivo

Validar el flujo de solicitudes de grupo en el panel de aliado:

1. Crear solicitud (`POST /api/solicitudes`).
2. Listar pendientes del grupo.
3. Atender (`POST /api/solicitudes/<id>/atender`).
4. Visibilidad admin (`GET /api/admin/solicitudes`).

Estados: `pendiente` → `atendida`.
