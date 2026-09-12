# Política de retención de datos (borrador operativo)

Borrador operativo del piloto. No sustituye un dictamen profesional. Alineado con los documentos públicos `v1-2026-09`.

Titular actual: Carlos Alexander Acero, nombre comercial RUANA. Ámbito: España.

Criterio aplicado el 12 de septiembre de 2026:

- Documentos con trascendencia fiscal o contable (comprobantes, encargos con importe, comisión Apoyo RUANA, identificativos ligados a facturación): **6 años desde el cierre del ejercicio** en que termina la relación o se documentó el cobro (Código de Comercio art. 30 y obligación de conservación de la LGT).
- Datos de perfil sin trascendencia fiscal (foto, descripción, catálogo de servicios, score, mensajes operativos): **durante la relación con RUANA + 12 meses tras la baja**, salvo que una obligación legal exija más.

El código no borra filas al vencer esos plazos. Los plazos siguientes son la regla de conservación que RUANA aplica al gestionar bajas y archivos; no hay caducidad automática en base de datos.

| Tipo de dato | Tabla / ubicación en BD | Dónde se guarda | Cuánto tiempo se conserva | Por qué |
| --- | --- | --- | --- | --- |
| Perfil de aliado (nombre, email, teléfono, CP, oficio, marca, foto, PIN hash) | `aliados` | Supabase Postgres (producción) / SQLite (dev), región **eu-west-1** (Irlanda, UE). Foto: almacenamiento Supabase (`foto_perfil_url`). | Foto, marca y resto de perfil sin trascendencia fiscal: durante la relación + 12 meses tras la baja. Nombre, email, teléfono y código si están ligados a facturación: 6 años desde el cierre del ejercicio. | Ejecución del contrato; identificación del aliado; conservación mercantil de identificativos de cobro |
| Consentimiento de alta (fecha/hora y versión del documento) | `consentimientos_aliado` | Misma BD | Durante la relación y 6 años tras la baja | Acreditar aceptación de Política de privacidad y Términos (`v1-2026-09`) (arts. 5.2 y 7.1 RGPD) |
| Catálogo de servicios del aliado | `catalogo_servicios_aliado` | Misma BD | Durante la relación + 12 meses tras la baja | Perfil profesional visible en directorio; sin trascendencia fiscal propia |
| Encargos / contactos RUANA (importes, estados, partes) | `contactos_ruana` | Misma BD | Importes, comisión y estados de cobro: 6 años desde el cierre del ejercicio. Resto operativo sin importe: durante la relación + 12 meses tras la baja | Gestión de encargos y comisión Apoyo RUANA |
| Comprobantes de pago / justificantes Apoyo RUANA | `contactos_ruana.comprobante_ruta` + bucket `ruana-comprobantes` | BD (ruta) y almacenamiento privado Supabase | 6 años desde el cierre del ejercicio (Código de Comercio art. 30 / LGT) | Obligación contable/fiscal de conservar documentación de facturación |
| Pruebas de conflicto de pago | `payment_conflicts` / bucket de conflictos | BD + almacenamiento Supabase | 6 años desde el cierre del ejercicio si documentan el cobro; en otro caso, durante la relación + 12 meses tras la baja | Impugnación de importes y prevención de fraude |
| Datos de Stripe Connect (account id, payment intents, transferencias) | columnas Stripe en `aliados` y `contactos_ruana`; `stripe_webhook_events`; ledger financiero | BD RUANA + Stripe (encargado) | Pagos, transferencias e identificadores necesarios para el rastro de cobro: 6 años desde el cierre del ejercicio. Identificadores de cuenta sin movimiento de cobro: durante la relación + 12 meses tras la baja | Cobro permanente en producción vía Stripe Connect |
| IBAN / Bizum / QR de pago del aliado | `aliados.iban` / `aliados.bizum_num` / `aliados.qr_paypal_path` (y métodos de pago de la plataforma en config) | BD / storage | Durante la relación + 6 años desde el cierre del ejercicio si formaron parte de la justificación de cobros; si no se usaron para un cobro, durante la relación + 12 meses tras la baja | Medio de cobro del Apoyo RUANA o del aliado |
| Mensajes de chat interno (legado) | `chat_mensajes` | Misma BD | Durante la relación + 12 meses tras la baja | Trazabilidad operativa del encargo, sin trascendencia fiscal propia |
| Eventos de negociación guiada | `negociacion_eventos` (+ `contactos_ruana.negociacion_json`) | Misma BD | Si documentan un encargo cerrado con importe: 6 años desde el cierre del ejercicio. Resto: durante la relación + 12 meses tras la baja | Acuerdo de precio y cierre del encargo |
| Centro de comunicación / soporte | `ruana_soporte_conversaciones`, `ruana_soporte_mensajes` | Misma BD | Hasta resolver + 12 meses. Si hay reclamación con trascendencia legal o fiscal: 6 años desde el cierre del ejercicio | Canal de soporte y disconformidades (sin SLA) |
| Solicitudes de baja / borrado | `solicitudes_baja_aliado` | Misma BD | Hasta resolver la solicitud + 12 meses (acreditar la gestión del derecho). Los datos de facturación asociados siguen 6 años | Derechos de supresión; no hay borrado automático por la conservación de facturación |
| Histórico de bajas / perfiles eliminados | `aliados_eliminados` | Misma BD | Archivo de perfil: 12 meses tras la baja. Datos de facturación asociados: 6 años desde el cierre del ejercicio | Auditoría de eliminación; email/teléfono/código se liberan para un nuevo alta |
| Score y movimientos | `aliados.score`, `score_movimientos`, `evaluaciones`, `evaluaciones_historico` | Misma BD | Durante la relación + 12 meses tras la baja | Funcionamiento interno de plazas/competencia |
| Competencias por plaza | tablas de competencia / permanencia | Misma BD | Durante la relación + 12 meses tras la baja | Asignación de plazas (sin apelación automática) |
| Notificaciones al aliado | `notificaciones_aliado` | Misma BD | Durante la relación + 12 meses tras la baja | Avisos operativos (pagos, competencia, etc.) |
| Invitaciones y referidos | `invitaciones`, `referidos`, `invitacion_campanas` | Misma BD | Durante la relación + 12 meses tras la baja | Crecimiento de la red |
| Email de bienvenida | no se almacena el cuerpo; se envía por SMTP Gmail (`team.ruana@gmail.com`) | Gmail de consumidor (sin DPA de encargado) | RUANA no conserva el cuerpo. El envío queda en Gmail según la política de Google. Registro de intento de envío en RUANA: durante la relación + 12 meses tras la baja | Comunicación operativa de alta |
| Sesión de acceso | JWT en `sessionStorage` del navegador (cabecera `X-Ruana-Session-Id`); store en memoria del servidor | Cliente + instancia Cloud Run | Hasta caducidad de la sesión (configurada, habitualmente 1 h) | Autenticación. No hay cookies de analítica/tracking |

## Encargados de tratamiento y DPA

Verificación realizada el 12 de septiembre de 2026. No se inventa un clic de aceptación que no se haya podido ejecutar.

| Encargado | Qué trata | DPA / base contractual | Fecha y cómo se verificó | Enlace |
| --- | --- | --- | --- | --- |
| **Supabase Pte. Ltd.** | Postgres y almacenamiento del proyecto «ruana APP» (ref. `qqlxgwbmtzcfrrobrfzy`), región **eu-west-1** (Irlanda, UE) | El Data Processing Addendum forma parte de los Terms of Service. Supabase retiró en 2026 el flujo de firma separada (PandaDoc). No existe un endpoint de Management API para aceptar un DPA distinto del contrato. | Proyecto creado el **19 de mayo de 2026** (fecha de alta del encargo). Región y estado `ACTIVE_HEALTHY` confirmados el **12 de septiembre de 2026** con `GET https://api.supabase.com/v1/projects` (token de Management API). El token es de alcance de proyecto: no da acceso a documentos de organización. | https://supabase.com/legal/customer-resources/data-processing-addendum |
| **Stripe** | Stripe Connect: cuentas, payment intents, transferencias, webhooks | El Data Processing Agreement (versión de 18 de noviembre de 2025) forma parte del Stripe Services Agreement. No hay un acto de aceptación adicional distinto de usar Stripe. | **12 de septiembre de 2026**: se consultó el DPA público. Este entorno no tiene credenciales de Stripe Dashboard (`STRIPE_SECRET_KEY` no inyectada); no se pudo abrir el panel ni pulsar un botón de aceptación. | https://stripe.com/legal/dpa — transferencias: https://stripe.com/legal/dta |
| **Google Cloud / Firebase** | Cloud Run (`europe-west1`) y Firebase Hosting | El Cloud Data Processing Addendum se incorpora al contrato de Google Cloud y cubre Cloud Run y Firebase Hosting. | **12 de septiembre de 2026**: se verificó el texto público del Addendum. El alojamiento en `europe-west1` está documentado en `.env.example` y en los workflows de deploy. | https://cloud.google.com/terms/data-processing-addendum |
| **Gmail de consumidor** (`team.ruana@gmail.com` vía SMTP) | Envío del email de bienvenida | **No hay DPA de encargado.** Google no ofrece Data Processing Agreement para Gmail de consumidor. Este canal no está cubierto por el Cloud DPA ni por Google Workspace. | **12 de septiembre de 2026**: confirmado que la cuenta documentada es Gmail de consumidor (`smtp.gmail.com`), no Google Workspace. No existe un DPA que se pueda aceptar para esa cuenta. Limitación conocida del piloto. | Condiciones de Gmail de consumidor; no hay DPA de Workspace |

## Notas

- Una solicitud de baja **no borra de inmediato** comprobantes ni asientos de facturación (se conservan 6 años).
- La región de Supabase **eu-west-1** está en la UE. No hace falta documentar una transferencia internacional para la base de datos ni el almacenamiento de Supabase.
- Stripe puede tratar fuera del EEE: se ampara en su DPA y en el Data Transfers Addendum (cláusulas contractuales tipo).
- Gmail de consumidor puede implicar tratamiento en EE. UU. **sin** DPA de encargado. RUANA no afirma que ese canal cumpla por sí solo el capítulo V del RGPD.
- No hay proceso automático de caducidad de filas en el código actual. Los plazos de esta tabla son la regla que debe aplicar quien gestione una baja o un archivo.
