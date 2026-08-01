# QA Solicitudes de Grupo

Fecha: 2026-06-09

## Objetivo

Validar el flujo de solicitudes de grupo en el panel de aliado:

- Crear una solicitud dentro del grupo.
- Verla como propia para el aliado solicitante.
- Verla como entrante para otro aliado del mismo grupo.
- Atenderla desde el segundo aliado.
- Verla en historial como atendida para ambos perfiles.

## Datos usados

- Solicitante: `64156` Sandra Julieth Castaño Reina
- Receptor: `84791` Valeria Caicedo Redondo
- Marcador QA: `QA-SOL-1781001172270`
- Oficio: `QA Carpinteria QA-SOL-1781001172270`

## Pruebas automatizadas

- `RUANA/tests/test_solicitudes_qa_flow.py`

Caso cubierto:

- `test_qa_solicitudes_crear_entrantes_propias_e_historial`

## Evidencia visual

Capturas en:

- `output/playwright/qa-solicitudes/01-creador-mis-solicitudes.png`
- `output/playwright/qa-solicitudes/02-creador-historial-pendiente.png`
- `output/playwright/qa-solicitudes/03-receptor-entrantes.png`
- `output/playwright/qa-solicitudes/04-receptor-atiende-modal-invitacion.png`
- `output/playwright/qa-solicitudes/05-receptor-historial-atendida.png`
- `output/playwright/qa-solicitudes/06-creador-historial-atendida.png`

Resultado automático:

- `output/playwright/qa-solicitudes/qa-solicitudes-result.json`

## Resultado

El flujo queda validado:

- La solicitud creada aparece en `Mis solicitudes`.
- La misma solicitud aparece en `Historial` del creador.
- El otro aliado del grupo la ve en `Solicitudes entrantes al grupo`.
- Al atenderla, se abre el modal de invitación.
- Tras refrescar, el historial muestra estado `Atendida` y el aliado que la atendió.
