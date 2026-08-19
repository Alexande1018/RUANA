# Política de retención de datos (borrador operativo)

**[BORRADOR — PENDIENTE DE REVISIÓN POR UN ABOGADO ANTES DE PUBLICAR]**

**[CONFIRMAR CON ASESOR FISCAL]** los plazos de documentación de facturación.

Titular actual: Carlos Alexander Acero, nombre comercial RUANA. Ámbito: España.
Versión alineada con los documentos públicos `v1-2026-08`.

Criterio general: conservar **solo el mínimo exigido por ley**. Donde el código no define un borrado automático, el plazo queda marcado como **[DECISIÓN PENDIENTE]**.

| Tipo de dato | Tabla / ubicación en BD | Dónde se guarda | Cuánto tiempo se conserva | Por qué |
| --- | --- | --- | --- | --- |
| Perfil de aliado (nombre, email, teléfono, CP, oficio, marca, foto, PIN hash) | `aliados` | Supabase Postgres (producción) / SQLite (dev). Foto: almacenamiento Supabase (`foto_perfil_url`). Región: `[REGION_SUPABASE_PENDIENTE_CONFIRMAR]` | Durante la relación con RUANA + el plazo mínimo legal aplicable. **[DECISIÓN PENDIENTE]** | Ejecución del contrato de uso de la plataforma; identificación del aliado |
| Consentimiento de alta (fecha/hora y versión del documento) | `consentimientos_aliado` | Misma BD | Durante la relación y el tiempo necesario para acreditar el cumplimiento. **[DECISIÓN PENDIENTE]** | Demostrar aceptación de Política de privacidad y Términos (`v1-2026-08`) |
| Catálogo de servicios del aliado | `catalogo_servicios_aliado` | Misma BD | Durante la relación + plazo mínimo legal. **[DECISIÓN PENDIENTE]** | Perfil profesional visible en directorio |
| Encargos / contactos RUANA (importes, estados, partes) | `contactos_ruana` | Misma BD | Durante la relación + plazo mínimo legal. Los datos de facturación asociados, 6 años. **[CONFIRMAR CON ASESOR FISCAL]** / resto **[DECISIÓN PENDIENTE]** | Gestión de encargos y comisión Apoyo RUANA |
| Comprobantes de pago / justificantes Apoyo RUANA | `contactos_ruana.comprobante_ruta` + bucket `ruana-comprobantes` | BD (ruta) y almacenamiento privado Supabase | 6 años desde el cierre del ejercicio (Código de Comercio art. 30 / LGT). **[CONFIRMAR CON ASESOR FISCAL]** | Obligación contable/fiscal de conservar documentación de facturación |
| Pruebas de conflicto de pago | `payment_conflicts` / bucket de conflictos | BD + almacenamiento Supabase | 6 años si documentan el cobro; en otro caso, relación + mínimo legal. **[CONFIRMAR CON ASESOR FISCAL]** / **[DECISIÓN PENDIENTE]** | Impugnación de importes y prevención de fraude |
| Datos de Stripe Connect (account id, payment intents, transferencias) | columnas Stripe en `aliados` y `contactos_ruana`; `stripe_webhook_events`; ledger financiero | BD RUANA + Stripe (encargado) | Pagos/facturación: 6 años. **[CONFIRMAR CON ASESOR FISCAL]**. Identificadores de cuenta: durante la relación + mínimo legal. **[DECISIÓN PENDIENTE]** | Cobro permanente en producción vía Stripe Connect |
| IBAN / Bizum / QR de pago del aliado | `aliados.iban` / `aliados.bizum_num` / `aliados.qr_paypal_path` (y métodos de pago de la plataforma en config) | BD / storage | Durante la relación + 6 años si forman parte de justificación de cobros. **[CONFIRMAR CON ASESOR FISCAL]** | Medio de cobro del Apoyo RUANA o del aliado |
| Mensajes de chat interno (legado) | `chat_mensajes` | Misma BD | Durante la relación + plazo mínimo legal. **[DECISIÓN PENDIENTE]** | Trazabilidad del encargo |
| Eventos de negociación guiada | `negociacion_eventos` (+ `contactos_ruana.negociacion_json`) | Misma BD | Durante la relación + plazo mínimo legal. **[DECISIÓN PENDIENTE]** | Acuerdo de precio y cierre del encargo |
| Centro de comunicación / soporte | `ruana_soporte_conversaciones`, `ruana_soporte_mensajes` | Misma BD | Durante la relación + plazo mínimo legal. **[DECISIÓN PENDIENTE]** | Canal de soporte y disconformidades (sin SLA) |
| Solicitudes de baja / borrado | `solicitudes_baja_aliado` | Misma BD | Hasta resolver la solicitud y el plazo mínimo para acreditar la gestión. **[DECISIÓN PENDIENTE]** | Derechos de supresión; no hay borrado automático por la conservación de facturación |
| Histórico de bajas / perfiles eliminados | `aliados_eliminados` | Misma BD | Plazo mínimo legal aplicable al archivo de auditoría. **[DECISIÓN PENDIENTE]** (los datos de facturación asociados siguen 6 años: **[CONFIRMAR CON ASESOR FISCAL]**) | Auditoría de eliminación definitiva; email/teléfono/código se liberan para un nuevo alta |
| Score y movimientos | `aliados.score`, `score_movimientos`, `evaluaciones`, `evaluaciones_historico` | Misma BD | Durante la relación + plazo mínimo legal. **[DECISIÓN PENDIENTE]** | Funcionamiento interno de plazas/competencia |
| Competencias por plaza | tablas de competencia / permanencia | Misma BD | Durante la relación + plazo mínimo legal. **[DECISIÓN PENDIENTE]** | Asignación de plazas (sin apelación automática) |
| Notificaciones al aliado | `notificaciones_aliado` | Misma BD | Durante la relación + plazo mínimo legal. **[DECISIÓN PENDIENTE]** | Avisos operativos (pagos, competencia, etc.) |
| Invitaciones y referidos | `invitaciones`, `referidos`, `invitacion_campanas` | Misma BD | Durante la relación + plazo mínimo legal. **[DECISIÓN PENDIENTE]** | Crecimiento de la red |
| Email de bienvenida | no se almacena el cuerpo; se envía por SMTP Gmail (`team.ruana@gmail.com`) | Gmail / Google (encargado) | Según política de Google / lo mínimo para el envío. **[DECISIÓN PENDIENTE]** | Comunicación operativa de alta |
| Sesión de acceso | JWT en `sessionStorage` del navegador (cabecera `X-Ruana-Session-Id`); store en memoria del servidor | Cliente + instancia Cloud Run | Hasta caducidad de la sesión (configurada, habitualmente 1 h) | Autenticación. No hay cookies de analítica/tracking |

## Notas

- Una solicitud de baja **no borra de inmediato** comprobantes ni asientos de facturación.
- Si la región de Supabase no es UE/EEE (`[REGION_SUPABASE_PENDIENTE_CONFIRMAR]`), hay que documentar la transferencia internacional **antes** de tratar datos de usuarios reales.
- No hay proceso automático de caducidad de filas en el código actual salvo lo descrito; los plazos de «resto de datos» están **[DECISIÓN PENDIENTE]**.
