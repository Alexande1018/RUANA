# Plan QA Testing RUANA

Fecha: 2026-06-05

## Objetivo

Validar de extremo a extremo las funcionalidades criticas de RUANA y dejar evidencias reproducibles: resultados automatizados, trazas, capturas en fallo y videos de ejecucion. El plan cubre creacion de aliados, invitaciones, encargos/contactos, confirmaciones de trabajo, pagos, reclamaciones, panel de administracion, score, registros y metricas.

## Estrategia

La cobertura se divide en tres capas:

1. Pruebas unitarias y de contrato con `pytest`: validan reglas de negocio, permisos, endpoints Flask y persistencia SQLite/Supabase sin depender del navegador.
2. Pruebas E2E con Playwright: recorren pantallas reales como usuario humano, grabando video siempre en `qa-artifacts/test-results`. Las APIs quedan para precondiciones de datos o comprobaciones tecnicas finales cuando no sustituyen la accion visible.
3. Auditoria manual guiada: checklist para validar UX, roles y casos que requieren criterio humano, como textos, claridad de reclamaciones, estados visuales y lectura del panel admin.

## Ambientes

- Local QA: Flask en `http://127.0.0.1:5000` con SQLite aislado por ejecucion bajo `qa-artifacts/ruana-e2e-*.db`.
- Produccion/staging: ejecutar la misma suite con `RUANA_BASE_URL=https://...` y `RUANA_SKIP_WEBSERVER=1`.
- Credenciales QA: admin `ADMIN001` o `RUANA_QA_ADMIN_CODE`; aliados creados automaticamente por la suite.

## Comandos

```powershell
npm install
npx playwright install chromium
npm run qa:e2e
npm run qa:report
```

Para ejecutar contra una URL ya desplegada:

```powershell
$env:RUANA_BASE_URL='https://ruana-4293f.web.app'
$env:RUANA_SKIP_WEBSERVER='1'
npm run qa:e2e
```

## Ejecucion Manual Desde GitHub

El cliente puede ejecutar la suite sin descargar el repositorio:

1. Entrar en GitHub > `Actions`.
2. Abrir el workflow `RUANA QA manual`.
3. Pulsar `Run workflow`.
4. Elegir la rama que quiere validar, por ejemplo `dev`.
5. Al terminar, descargar el artefacto `ruana-qa-latest`.

El workflow ejecuta la rama seleccionada contra Flask local y una BBDD SQLite temporal vacia del runner. No usa produccion, no usa Supabase y el runner se destruye al finalizar, por lo que no quedan datos de prueba persistidos.

Para evitar acumulacion, antes de subir resultados borra artefactos anteriores llamados `ruana-qa-latest` y sube solo la ultima batida, con retencion de 1 dia. El ZIP contiene:

- `playwright-report/index.html`
- `test-results/**/video.webm`
- `results/qa-e2e-results.json`
- `results/pytest.log`
- `results/playwright-console.log`

## Evidencias

- Videos: `qa-artifacts/test-results/**/video.webm`
- Trazas en fallo: `qa-artifacts/test-results/**/trace.zip`
- Reporte HTML: `qa-artifacts/playwright-report/index.html`
- Resultados JSON: `qa-artifacts/results/qa-e2e-results.json`

## Lectura Humana De Resultados

La suite E2E muestra un panel fijo dentro del video con:

- Escenario en curso.
- Paso actual.
- Accion simulada por usuario o preparacion QA.
- Resultado esperado.
- Resultado observado con estado `PASS`.

El mismo texto se imprime en consola con prefijo `[QA]`, para que el resultado del comando tambien cuente que esta pasando. La velocidad del video puede ajustarse con:

```powershell
$env:RUANA_QA_VIDEO_PAUSE_MS='1500'
$env:RUANA_QA_ACTION_PAUSE_MS='800'
npm run qa:e2e
```

Los valores por defecto son `RUANA_QA_VIDEO_PAUSE_MS=1500` y `RUANA_QA_ACTION_PAUSE_MS=800`, para que el video deje tiempo suficiente a leer cada paso y entender que esta ocurriendo. El timeout por test es de 180 segundos porque los escenarios estan narrados y grabados a velocidad humana.

Los flujos priorizan acciones visibles de usuario cuando el UI lo permite. La suite mueve un cursor visual, hace scroll hasta la zona relevante, resalta controles y ejecuta clicks, formularios, selectores, chat bidireccional, confirmacion de importe, cierre sin trabajo, subida de comprobante, reclamacion y revision admin desde la interfaz. En encargos, pagos y reclamaciones se siguen usando APIs solo para crear precondiciones fragiles, como usuarios/contactos de prueba, y la validacion funcional se muestra despues en la UI.

## Matriz De Cobertura

| ID | Funcionalidad usuario | Validacion automatizada | Evidencia esperada |
| --- | --- | --- | --- |
| QA-01 | Admin inicia sesion y recorre dashboard operativo | E2E Playwright | Video con KPIs, registros, score, solicitudes, chats, pagos y conflictos |
| QA-02 | Usuario recibe invitacion, valida codigo y se registra | E2E Playwright | Video de `invite.html`, `register.html`, alta y codigo creado |
| QA-03 | Admin crea campana de invitacion desde UI | E2E Playwright | Modal admin, datos de campana y resultado visible |
| QA-04 | Invitacion de un uso queda agotada | E2E Playwright | Reintento desde `invite.html` con error visible |
| QA-05 | Aliado completa registro con oficio, especialidad, CP y condiciones | E2E Playwright | Formulario rellenado, selector y codigo final |
| QA-06 | Aliado accede al panel con sesion real | E2E Playwright | Panel con metricas, directorio, solicitudes y avisos |
| QA-07 | Admin revisa altas, metricas y salud de la red | E2E Playwright | Secciones admin recorridas con scroll y datos visibles |
| QA-08 | Aliado solicitante crea una solicitud desde su panel | E2E Playwright | Formulario de nueva solicitud y lista de solicitudes propias |
| QA-09 | Otro aliado compatible encuentra y atiende la solicitud | E2E Playwright | Lista de solicitudes disponibles y accion de conocer contacto |
| QA-10 | Codigo de contacto queda visible solo al usuario autorizado | E2E Playwright | Invitacion/contacto visible sin valor enmascarado |
| QA-11 | Se crea contacto aceptado y queda como trabajo en progreso | E2E con precondicion API y UI posterior | Aviso persistente visible en panel de ambos usuarios |
| QA-12 | Solicitante envia mensaje de chat | E2E Playwright | Modal de chat mostrando mensaje enviado |
| QA-13 | Profesional ve el mensaje y responde | E2E Playwright | Historial con mensajes de ambos participantes |
| QA-14 | Admin consulta la conversacion completa | E2E Playwright | Tabla de conversaciones y modal admin con ambos mensajes |
| QA-15 | Solicitante declara importe y cierra trabajo | E2E Playwright | Modal de importe, confirmacion y desaparicion del aviso |
| QA-16 | Ofertador/profesional intenta declarar importe | E2E Playwright | Bloqueo funcional actual con mensaje claro al profesional |
| QA-17 | Solicitante cierra contacto sin trabajo | E2E Playwright | Modal de no concretado y cierre del aviso |
| QA-18 | Se genera Apoyo RUANA tras cierre con importe | E2E Playwright | Bloque de pago pendiente en panel profesional |
| QA-19 | Profesional sube comprobante desde UI | E2E Playwright y contrato frontend | Selector de archivo, comentario, envio y aceptacion |
| QA-20 | Admin ve pago en revision | E2E Playwright | Tabla de pagos en revision con contacto esperado |
| QA-21 | Admin aprueba pago | E2E Playwright | Accion Aprobar pago y toast de actualizacion |
| QA-22 | Admin rechaza pago con motivo y profesional recibe notificacion | E2E Playwright | Modal de rechazo, toast admin y mensaje RUANA en panel profesional |
| QA-23 | Profesional impugna Apoyo RUANA | E2E Playwright | Boton Impugnar y dialogos de reclamacion |
| QA-24 | Admin ve conflicto de pago | E2E Playwright | Cola de conflictos con contacto reclamado |
| QA-25 | Score y evaluaciones se actualizan por cierres y disputas | pytest/API | Tests de reglas de negocio y endpoints de evaluacion |
| QA-26 | Eventos recientes y auditoria quedan trazados | E2E Playwright y pytest/API | Panel admin con eventos, mas contratos backend |
| QA-27 | Solicitudes y conversaciones aparecen en registros admin | E2E Playwright | Secciones admin de solicitudes y chats con datos visibles |
| QA-28 | Responsive y legibilidad en pantallas principales | Revision manual guiada | Checklist en movil y escritorio |
| QA-29 | Admin solo lectura no puede ejecutar acciones de escritura desde UI | E2E Playwright | Botones de crear campana/cambiar reglas deshabilitados |
| QA-30 | Seguridad de pagos, uploads y permisos backend sensibles | pytest/API y checklist | Contratos de permisos, extensiones y almacenamiento |

Nota de producto: en el comportamiento actual, la declaracion de importe queda reservada al solicitante. Por eso QA-16 valida que el ofertador/profesional no pueda cerrar con importe y que el mensaje sea claro. Si RUANA debe permitir cierre exitoso por ofertador, ese caso pasa de validacion de bloqueo a cambio funcional.

## Hallazgos De Los Subagentes QA

- Permisos admin: `forzar-suplencia` y `abrir-plaza` modifican estado pero estan protegidos con `require_admin`, no con `require_admin_escritura`. La UI puede ocultar acciones, pero falta defensa backend para admin solo lectura.
- Confirmacion de importes: la documentacion/comentarios hablan de doble declaracion, pero la implementacion actual cierra el trabajo con la declaracion del solicitante y rechaza declaracion de profesional. La suite E2E refleja el comportamiento actual y deja marcado el riesgo de producto.
- Pagos y pruebas: los comprobantes se guardan en `web/static/uploads`, no en buckets privados Supabase, lo que puede ser volatil en Cloud Run y exponerse como contenido estatico.
- Reclamaciones: la subida de prueba de conflicto no aplica allowlist de extensiones, a diferencia del comprobante de Apoyo RUANA.
- Conflictos: existen rutas nueva y legacy para resolver conflictos; deben dejar sincronizados contacto, `payment_conflicts`, ingresos, score, auditoria y notificaciones.
- Bug corregido durante QA: el modal UI de comprobante Apoyo RUANA enviaba el archivo sin cabeceras de sesion y devolvia `401`; ahora usa `getRuanaAuthHeaders()` y queda cubierto por contrato frontend.

## Checklist Manual

- Verificar que el panel admin oculta datos si no hay sesion.
- Comprobar que admin solo lectura no puede crear invitaciones, cambiar reglas, resolver pagos ni activar aliados.
- Comprobar explicitamente que admin solo lectura no puede forzar suplencia ni abrir plaza.
- Revisar que el flujo de invitacion no permite reutilizar campanas agotadas.
- Confirmar que los mensajes de error son comprensibles en registro, login, pagos y reclamaciones.
- Revisar que los pagos pendientes bloquean nuevos trabajos del profesional cuando corresponde.
- Revisar que las reclamaciones piden motivo y evidencias antes de llegar al admin.
- Verificar responsive en movil y escritorio para `invite.html`, `register.html`, `aliado.html` y `admin.html`.
- Revisar que los registros del admin tienen fechas, actores y estados coherentes.

## Riesgos Y Observaciones

- Playwright no estaba instalado inicialmente; se agrego `@playwright/test` como dependencia de desarrollo.
- La suite usa un SQLite aislado para evitar contaminar datos reales.
- La suite sube comprobante `.png` para validar el flujo feliz de pagos. Las extensiones rechazadas deben cubrirse en pytest/API.
- Para Supabase real, ejecutar primero `npm run verify:supabase` y usar un entorno staging con datos descartables.

## Cadencia Recomendada

- Smoke diario: `npm run qa:e2e -- --grep "admin|invitaciones"`
- Regresion por release: suite completa Playwright y `pytest`.
- Antes de cambios de negocio: ampliar casos de contrato en `RUANA/tests`.
- Antes de despliegue: adjuntar reporte HTML, videos relevantes y resumen de fallos al entregable QA.
