# Plan de reset pre-producción RUANA

**Estado:** PLAN. No se ha ejecutado ningún reset, backup, DELETE, TRUNCATE, DROP ni comando contra producción.

**Fecha de auditoría:** 2026-09-10  
**Alcance:** código en `main` (revisión de modelos, `schema_service.py`, migraciones Supabase, repositorios, servicios, `DBManager`, endpoints, Storage, Auth, Stripe).  
**Limitación:** este entorno de auditoría **no tenía `DATABASE_URL`**. No se ha consultado el Postgres real. Los nombres de tablas salen del código y de `supabase/migrations/`. Los conteos de filas son **obligatorios en el futuro `--dry-run` contra la BD objetivo**.

---

## A. Resumen ejecutivo

**¿Es seguro realizar el reset con la arquitectura actual?** Sí, **si** se respeta la clasificación conservar/vaciar de este documento, se usa `TRUNCATE` (no `DELETE` fila a fila) para el ledger, se hace backup restaurable y se congela preview + cron. RUANA **arranca con tablas operativas vacías**: el catálogo de oficios y las reglas viven en ficheros; el admin del panel vive fuera de Postgres (Secret Manager), no es un aliado.

**Todos los aliados se borran. Cero excepciones.** No se conserva `RUANA-ADMIN`, ni seeds, ni placeholders, ni bajas, ni nadie “de sistema”. Tras el reset, `COUNT(*) FROM aliados` debe ser **0**. El login `/admin` sigue funcionando porque no usa esa tabla. Un grupo territorial solo nacerá cuando se registre el **primer aliado real**. El sintético `RUANA-ADMIN` **no forma parte del reset**: si más adelante el panel crea una invitación, la app puede insertarlo sola; el script no debe dejar ni recrear ningún aliado.

**No es seguro** un wipe genérico de `public.*`. Eso destruiría `migraciones` (el arranque reaplicaría lógicas one-shot) y `ruana_metodos_pago_manual` (IBAN/Bizum/QR reales de cobro).

**No existe** un flag fiable `is_qa` / `demo` / `e2e` en las filas de producción. Preview (`ruana-preview`) y producción (`ruana`) **comparten el mismo proyecto Supabase** `qqlxgwbmtzcfrrobrfzy` y la misma `DATABASE_URL`. El reset tiene que ser **wipe operativo completo**, no un borrado selectivo de “datos test”.

**Esta auditoría no ha tocado datos.** El siguiente paso permitido es implementar el script en modo dry-run; la ejecución destructiva queda fuera de esta tarea.

---

## B. Datos que se eliminarían

Todo lo generado por QA, E2E, seeds, registro de prueba, encargos, pagos test, linaje, score, chats y archivos de aliados.

**Regla de aliados:** `TRUNCATE aliados` (tras vaciar hijas). Sin `WHERE`. Sin allowlist de códigos. Incluye *todos* los estados (`activo`, `en_espera`, `pendiente_completar`, `pendiente_validacion`, `expulsado`, `rechazado`, `eliminado`, `suspendido_temporal`, `sistema`, …).

### B.1 Tablas Postgres a vaciar (categoría A)

| Tabla | Qué contiene | Por qué vaciar |
|-------|----------------|----------------|
| `aliados` | **Todas** las filas: perfiles QA, PIN, Stripe Connect, foto, score, grupo, linaje. Incluye placeholders, seeds `ALFA01`–`DELTA04`, bajas blandas y el sintético `RUANA-ADMIN` (`estado=sistema`). | No hay aliado estructural. El panel admin no es esta tabla. **Objetivo: 0 filas.** El script no debe reinsertar `RUANA-ADMIN` ni ningún seed. |
| `aliados_eliminados` | Archivo de bajas admin | Residuo QA |
| `profiles` | Espejo futuro Supabase Auth (`aliado_codigo` / `admin_codigo`) | Filas de prueba si existen. **Hoy el login Flask no las usa.** |
| `auth.users` | Usuarios Supabase Auth | Solo si `aliados.auth_user_id` apunta a alguno. El login actual es código+PIN, no Auth. |
| `grupos` | Grupos territoriales creados en runtime (`RUANA-{8}-{SUFIJO}`) | No son catálogo maestro. Se recrean al registrar. |
| `grupo_oficio_cerrado` | Plazas cerradas por admin | Estado de grupos de prueba |
| `avisos_grupo` | Avisos (p. ej. competencia) | Operativo |
| `aliado_avisos_vistos` | Avisos ya vistos por aliado | Operativo |
| `cp_estado` | Modo CP + contadores (`aliados_activos`, `encargos_validos`, `aliados_desde_ultimo_grupo`) | Contadores quedarían mentira si se borran aliados. Se regenera en `territorio_repo` con `modo='territorial'`. |
| `cp_independencia_solicitudes` | Solicitudes históricas de independencia (Grupo Madre) | Residuo territorial de prueba |
| `migracion_territorio_backup` | Backup de la migración territorio directo | Datos de aliados/grupos QA |
| `migracion_territorio_informe` | Informe de esa migración | Igual |
| `solicitudes` | Nueva conexión / recomendaciones proximidad | Operativo |
| `solicitudes_semanales` | Encuestas semanales | Operativo |
| `solicitudes_semanales_respuestas` | Respuestas | Operativo |
| `contactos_ruana` | Encargos, negociación JSON, Stripe IDs, comprobantes, importes, Apoyo | Hub operativo |
| `chat_mensajes` | Mensajes del encargo | Operativo |
| `negociacion_eventos` | Ofertas / contraofertas | Operativo |
| `contacto_panel_oculto` | Encargos ocultos en panel | Operativo |
| `contacto_penalizaciones_aplicadas` | Penalizaciones 7d/21d | Operativo |
| `confirmaciones_trabajo` | Confirmaciones de importe | Operativo |
| `ingresos_ruana` | Apoyo RUANA consolidado | Operativo |
| `invitaciones` | Códigos peer (usados y no usados) | Incluye invitaciones QA no usadas |
| `invitaciones_oficio` | Códigos `RUANA-{grupo}-{OFICIO}-{4}` | Operativo |
| `invitacion_campanas` | Campañas QR admin (p. ej. `RUANA-QA*`) | Config operativa de prueba, no catálogo |
| `invitacion_campana_usos` | Usos de campaña | Operativo |
| `referidos` | Árbol invitador→invitado | Operativo |
| `grupo_crecimiento_recompensas` | +5 score por invitar al grupo en creación | Operativo |
| `notificaciones_aliado` | Inbox aliado | Operativo |
| `score_movimientos` | Historial Score RUANA | Operativo |
| `evaluaciones` | Estado motor evaluación | Operativo |
| `evaluaciones_historico` | Histórico de cambios de estado | Operativo |
| `aliado_accesos_dia` | Actividad / accesos diarios | Operativo |
| `eventos_sistema` | Eventos de sistema | Operativo |
| `audit_log` | Auditoría genérica del panel | Residuo QA |
| `competencia` | Competencias de plaza | Operativo |
| `competencia_pendiente` | Cola de retadores | Operativo |
| `catalogo_servicios_aliado` | Hasta 10 servicios **del aliado** (no el catálogo maestro) | Perfil de prueba |
| `ruana_soporte_conversaciones` | Tickets soporte | Operativo |
| `ruana_soporte_mensajes` | Mensajes soporte | Operativo |
| `aliado_recuperacion_acceso` | OTP de recuperación PIN | Operativo |
| `consentimientos_aliado` | Consentimiento RGPD al alta | Ligado a aliados de prueba |
| `solicitudes_baja_aliado` | Solicitudes GDPR | Operativo |
| `ruana_pago_manual_aliados_habilitados` | Allowlist de quién ve IBAN/Bizum | Códigos de aliados QA |
| `payment_conflicts` | Conflictos de importe | Operativo |
| `payment_conflict_evidence` | Evidencias | Operativo |
| `payment_conflict_comments` | Comentarios | Operativo |
| `payment_conflict_actions` | Acciones | Operativo |
| `payment_conflict_audit` | Auditoría conflicto | Operativo |
| `stripe_webhook_events` | Eventos Stripe ingeridos | Test mode |
| `financial_idempotency_keys` | Idempotencia financiera | Operativo |
| `stripe_refunds` | Espejo reembolsos Stripe | Test |
| `stripe_disputes` | Espejo disputas Stripe | Test |
| `financial_reconciliation` | Discrepancias | Operativo |
| `financial_transfers` | Transferencias Connect | Test |
| `financial_transfer_attempts` | Intentos | Operativo |
| `financial_transfer_snapshots` | Snapshots | Operativo |
| `financial_refunds` | Reembolsos internos | Operativo |
| `financial_refund_attempts` | Intentos | Operativo |
| `financial_disputes` | Disputas internas | Operativo |
| `financial_dispute_evidence` | Evidencia disputa | Operativo |
| `financial_dispute_attempts` | Intentos | Operativo |
| `financial_reconciliation_executions` | Ejecuciones de conciliación | Operativo |
| `financial_reconciliation_snapshots` | Snapshots conciliación | Operativo |
| `financial_reconciliation_resource_results` | Resultados por recurso | Operativo |
| `ledger_transactions` | Asientos (POSTED/VOIDED **inmutables por trigger**) | Test. Ver §F y §G |
| `ledger_entries` | Líneas de asiento | Test |
| `ledger_event_links` | Vínculos evento↔asiento | Test |
| `ledger_account_balances` | Saldos | Test |
| `financial_admin_alert_actions` | Acciones de alerta admin | Operativo |
| `financial_action_approvals` | Aprobaciones duales | Operativo |
| `financial_audit_log` | Audit trail financiero | Operativo |
| `financial_job_leases` | Leases de jobs | Operativo |
| `financial_automation_runs` | Runs de automatización | Operativo |
| `financial_alerts` | Alertas financieras | Operativo |

### B.2 Fuera de Postgres (eliminar en una fase posterior coordinada; no en el primer `--execute` de Stripe)

| Recurso | Qué borrar | Cuándo |
|---------|------------|--------|
| Supabase Storage `ruana-public` | Fotos de perfil, QR Revolut de prueba en `fotos_perfil/`, `metodos_pago/` **salvo** el QR de plataforma que siga referenciado por `ruana_metodos_pago_manual.qr_revolut_path` | Con el reset de BD, con allowlist del QR de cobro |
| Supabase Storage `ruana-comprobantes` | `pagos_ruana/`, `conflictos/` | Con el reset |
| Supabase Storage `ruana-conflictos` | Si tiene objetos (el código actual sube conflictos a `ruana-comprobantes/conflictos/`) | Con el reset |
| Disco local `RUANA/web/static/uploads/` | Solo máquinas de desarrollo; no Cloud Run típico | Local |
| JWT de sesión | No hay store persistente; caducan solas. Reciclar instancias Cloud Run tras el reset | Post-reset |
| Stripe Test (Connect `acct_*`, PaymentIntents, Transfers, Checkout) | **No borrar en esta fase** (petición explícita). Quedarán huérfanos respecto a la BD | Fase Stripe posterior |

---

## C. Datos que sobrevivirían

### C.1 Postgres — no vaciar

| Tabla / objeto | Qué contiene | Por qué conservar |
|----------------|--------------|-------------------|
| **Esquema** (tablas, columnas, índices, RLS, policies, funciones, triggers, publications realtime) | DDL | El reset no toca esquema. Prohibido `DROP TABLE`. |
| `migraciones` | Registro de one-shots (`territorio_directo_v1`, `purgar_placeholders_control_v1`, etc.) | Si se vacía, el boot de `schema_service` puede reejecutar lógicas pensadas para “una vez”. **Bloqueo crítico si se trunca.** |
| `ruana_metodos_pago_manual` | IBAN, Bizum, `qr_revolut_path` de la plataforma | Configuración real de cobro manual. No está en el repo (`docs/seguridad/pago-manual-allowlist.md`). **Bloqueo crítico si se trunca.** |
| `cp_ciudad` | Caché CP→ciudad/provincia | Referencia. Se puede rehidratar desde `RUANA/config/cp_ciudad_es.json`, pero conviene conservarla: no es dato de aliado. |
| `storage.buckets` | Definición de buckets | Infra, no objetos |

### C.2 Ficheros y secretos (fuera de BD)

| Recurso | Ubicación | Notas |
|---------|-----------|--------|
| Catálogo maestro de oficios | `RUANA/config/oficios_ruana.json` | Leído desde disco. **No hay tabla de oficios.** |
| Catálogo CP España | `RUANA/config/cp_ciudad_es.json` | Fuente de `territorio_service` |
| Reglas Score / Apoyo / competencia | `RUANA/config/ruana_reglas_v1.json` | `apoyo_pct` 12, umbral competencia 15, score reinicio 50, etc. El admin puede persistir cambios **en el fichero**, no en una tabla de parámetros. En Cloud Run el fichero es el de la imagen: cambios en runtime **no sobreviven a un redeploy**. Verificar antes del reset si hay reglas “solo en memoria”. |
| Credenciales admin | GCP Secret Manager `ruana-admin-credentials` | **No están en Postgres.** Conservar. QA `ADMIN001`/`0000` solo en `admin_credentials.qa.json` (no se copia a Docker). |
| Stripe keys, modo, webhook secret | Secret Manager / env | Conservar. Hoy el default operativo es **test**. |
| `FLASK_SECRET_KEY`, `RUANA_CRON_SECRET`, SMTP, Supabase keys | Secretos | Conservar |
| Extensiones PG | `pgcrypto`, `citext` | Conservar |

### C.3 Lo que NO hay que “conservar” porque no es maestro

- **Grupos / plazas ocupadas:** se derivan de aliados. Vaciar.
- **Ciudades en `grupos.ciudad`:** se rellenan al crear grupo desde el catálogo CP.
- **Feature flags:** no existe tabla ni sistema de flags. El comportamiento lo marcan env vars (`RUANA_STRIPE_PAYMENTS_ENABLED`, etc.).
- **Ningún aliado.** Ni `RUANA-ADMIN` ni `estado=sistema`. El acceso al panel es Secret Manager (`RUANA_ADMIN_CREDENTIALS_JSON`), independiente de `aliados`.
- **No reseedar** `seed_aliados.py` (ALFA01…) ni `FIRST_RUN` tras el reset.

---

## D. Dependencias

### D.1 Mapa FK (simplificado)

```
auth.users
  ← profiles.id (ON DELETE CASCADE)
  ← aliados.auth_user_id (ON DELETE SET NULL)

grupos
  ← aliados.grupo_id (SET NULL)
  ← grupos.grupo_madre_id (self)
  ← cp_estado.grupo_madre_id
  ← solicitudes.grupo_id (RESTRICT en init PG)
  ← solicitudes_semanales.grupo_id
  ← invitaciones.grupo_id (SET NULL)
  ← invitaciones_oficio.grupo_id (CASCADE)
  ← competencia.grupo_id (CASCADE)
  ← competencia_pendiente.grupo_id
  ← avisos_grupo.grupo_id (CASCADE)
  ← grupo_oficio_cerrado.grupo_id (CASCADE)
  ← grupo_crecimiento_recompensas.grupo_id (SET NULL)

aliados.codigo / aliados.id
  ← contactos_ruana.solicitante_codigo / profesional_codigo (RESTRICT)
  ← chat_mensajes.emisor_codigo (RESTRICT)
  ← solicitudes.*_codigo
  ← invitaciones.invitador_aliado_id (CASCADE)
  ← referidos (CASCADE)
  ← score_movimientos (CASCADE)
  ← evaluaciones / historico (CASCADE)
  ← notificaciones_aliado (CASCADE)
  ← catalogo_servicios_aliado (CASCADE)
  ← competencia códigos (RESTRICT / SET NULL ganador)
  ← payment_conflicts contratante_id / profesional_id (RESTRICT)
  ← confirmaciones_trabajo.aliado_id (CASCADE)
  ← aliado_accesos_dia
  ← invitacion_campana_usos
  ← grupo_crecimiento_recompensas (CASCADE)

contactos_ruana
  ← chat_mensajes (CASCADE)
  ← negociacion_eventos
  ← contacto_panel_oculto (CASCADE)
  ← contacto_penalizaciones_aplicadas (CASCADE)
  ← confirmaciones_trabajo (CASCADE)
  ← ingresos_ruana (CASCADE)
  ← payment_conflicts.trabajo_id (CASCADE)
  ← stripe_webhook_events, financial_*, stripe_refunds/disputes
  ← financial_transfers (UNIQUE contacto_id)
  ← ledger_transactions.contacto_id

payment_conflicts
  ← payment_conflict_* (evidence/comments/actions/audit)
  ← financial_refunds.conflicto_id
  ← financial_disputes.conflicto_id

financial_refunds ← financial_refund_attempts
financial_disputes ← evidence / attempts
financial_transfers ← attempts
financial_reconciliation_executions ← snapshots / resource_results
ledger_transactions ← ledger_entries / ledger_event_links / reversa_de_id
invitacion_campanas ← invitacion_campana_usos
ruana_soporte_conversaciones ← ruana_soporte_mensajes
solicitudes_semanales ← solicitudes_semanales_respuestas
```

**Triggers relevantes**

| Trigger | Tabla | Efecto en reset |
|---------|-------|-----------------|
| `set_updated_at` | `profiles`, `aliados`, `contactos_ruana`, `evaluaciones`, `payment_conflicts` | Irrelevante al vaciar |
| `trg_ledger_tx_no_delete` | `ledger_transactions` | **`DELETE` de filas POSTED/VOIDED aborta** |
| `trg_ledger_entry_no_delete` | `ledger_entries` | Igual si el padre está POSTED/VOIDED |
| `trg_ledger_tx_immutable` | updates | No aplica a vaciado |

PostgreSQL: **`TRUNCATE` no dispara triggers `BEFORE DELETE`**. Por eso el script debe vaciar el ledger con `TRUNCATE … RESTART IDENTITY`, no con `DELETE FROM`.

SQLite (solo local): FKs a menudo sin `ON DELETE`; no es el objetivo del reset de lanzamiento.

### D.2 Orden seguro de vaciado (Postgres)

No usar el orden conceptual “mensajes → chats → …” si se puede hacer un `TRUNCATE` conjunto. Orden recomendado:

**Opción preferida (una transacción):** listar **explícitamente** todas las tablas de §B.1 (excepto `auth.users` / `profiles`, que van al final y con cuidado) en un único:

```sql
TRUNCATE TABLE
  ledger_entries,
  ledger_event_links,
  ledger_account_balances,
  ledger_transactions,
  -- …resto de tablas A, incluyendo aliados y grupos…
RESTART IDENTITY;
```

Sin `CASCADE` genérico sobre `public`, para no arrastrar `migraciones` ni `ruana_metodos_pago_manual`.

Si el motor exige resolver FKs, el orden **de hojas a raíces** es:

1. Ledger entries / links / balances → `ledger_transactions`
2. `financial_*` hijos (attempts, evidence, snapshots, resource_results, alerts, approvals, audit, leases, runs)
3. `stripe_refunds`, `stripe_disputes`, `stripe_webhook_events`, `financial_idempotency_keys`, `financial_reconciliation`, `financial_transfers*`
4. `payment_conflict_*` → `payment_conflicts`
5. `chat_mensajes`, `negociacion_eventos`, `contacto_*`, `confirmaciones_trabajo`, `ingresos_ruana`
6. `contactos_ruana`
7. Solicitudes semanales respuestas → semanales → `solicitudes`
8. Soporte mensajes → conversaciones
9. Score, evaluaciones, notificaciones, accesos, catálogo aliado, consentimientos, OTP, bajas
10. Competencia / pendiente
11. Referidos, invitaciones, campañas usos → campañas, oficio, crecimiento
12. Allowlist pago manual
13. `aliados_eliminados`, avisos, oficio cerrado, independencia, backups migración
14. `cp_estado` (antes o junto a `grupos` por `grupo_madre_id`)
15. `aliados` (después de todo lo que referencia `codigo`/`id` con RESTRICT)
16. `grupos`
17. `profiles` → `auth.users` (solo IDs que fueran de aliados; **no** tocar usuarios de servicio de Supabase)

`cp_ciudad` y `migraciones` y `ruana_metodos_pago_manual` **fuera de esta lista**.

### D.3 Huérfanos y duplicación

| Riesgo | Detalle |
|--------|---------|
| Storage sin FK | URLs en `foto_perfil_url`, `comprobante_ruta`, `prueba_url`, `qr_paypal_path` no borran objetos |
| Stripe sin FK | `stripe_account_id` en aliados; objetos siguen en Dashboard Test |
| `purga_datos_aliado` incompleta | El borrado admin **no** limpia ledger, webhooks, refunds, disputes, Storage. Un reset “aliado a aliado” dejaría basura financiera. Por eso el wipe es por tablas, no por `eliminar_aliado`. |
| Soft-delete | `aliados.estado='eliminado'` sigue ocupando fila; hay que `TRUNCATE aliados`, no filtrar por estado |
| Códigos liberados | `liberado+{codigo}@ruana.invalid` — desaparecen con el truncate |
| Nombres de grupo | Unicidad global incluye disueltos; al vaciar, los nombres quedan libres (irrelevante: se generan aleatorios) |

---

## E. Servicios externos

| Servicio | ¿Hay datos de aliados? | Reset |
|----------|------------------------|--------|
| **Supabase Postgres** | Sí — fuente de verdad | Objetivo del script |
| **Supabase Auth** (`auth.users`) | Esquema preparado; **login Flask no escribe aquí** | Comprobar conteo en dry-run; borrar solo si hay filas ligadas |
| **Supabase Storage** | Sí — fotos, comprobantes, QR, pruebas | Vaciar objetos de prueba; **conservar** el objeto del QR de plataforma si `qr_revolut_path` de métodos manuales lo usa |
| **Supabase Realtime** | Publicación de `chat_mensajes`, `notificaciones_aliado`, `contactos_ruana` | No hay cola persistente que limpiar |
| **Firebase** | Solo Hosting (rewrite a Cloud Run). **Sin Firestore, sin RTDB, sin Auth en uso** | No tocar |
| **GCP Secret Manager** | Admin, Stripe, DB URL, SMTP, cron | **Conservar** |
| **Cloud Run** | `ruana` y `ruana-preview` | Pausar preview y cron durante el reset; reciclar instancias después (JWT) |
| **Cloud Scheduler** | 4 jobs que **escriben** (competencia, purga mensual, motor evaluación, ciclo financiero) | **Pausar** antes; reanudar después |
| **Stripe** | Connect + Checkout Test (default). No hay `stripe_customer_id` en BD; checkout usa `customer_email` | **No eliminar** clientes/pagos/cuentas en esta fase |
| **SMTP / Gmail** | Correos de bienvenida enviados; no hay tabla de outbox | No hay nada que truncar; la bandeja de Gmail no se limpia |
| **Redis** | No existe | N/A |
| **Rate limit / sesiones** | Memoria de proceso + JWT | Reciclar Cloud Run |
| **SQLite `ruana.db`** | Dev local | Irrelevante para el lanzamiento; no es producción |

**Preview = producción de datos.** `.github/workflows/deploy-firebase-preview.yml` monta la misma `DATABASE_URL` y las mismas keys Stripe/Supabase. Un usuario en preview escribe en la BD que se va a resetear y en la que nacerán usuarios reales.

---

## F. Riesgos detectados

### CRÍTICO

| ID | Riesgo | Mitigación en el plan |
|----|--------|------------------------|
| C1 | Vaciar `ruana_metodos_pago_manual` → se pierde IBAN/Bizum/QR de cobro | Allowlist KEEP absoluta + assert post-reset `COUNT(*)>=1` o dump previo de esa fila |
| C2 | Vaciar `migraciones` → el boot reejecuta one-shots | KEEP absoluta + assert nombres conocidos siguen |
| C3 | `DELETE` en ledger POSTED → excepción, transacción aborta a medias si no hay cuidado | Solo `TRUNCATE` (no dispara el trigger DELETE) |
| C4 | Preview y prod comparten Postgres | Ventana: pausar `ruana-preview`, Scheduler y deploys |
| C5 | No hay marca QA vs usuario real | El negocio afirma que **todo** es prueba. Si hay un aliado real, se borra igual. Confirmación humana `RESET-RUANA-PREPRODUCTION` |
| C6 | `TRUNCATE … CASCADE` amplio puede llevarse tablas KEEP por FK | Lista explícita, **sin** CASCADE hacia `migraciones` / métodos de pago / `cp_ciudad` |
| C7 | Stripe Test huérfano + futuro flip a Live con cuentas viejas | No borrar Stripe ahora; fase posterior **antes** del primer cobro Live |

### ALTO

| ID | Riesgo | Mitigación |
|----|--------|------------|
| A1 | Drift SQLite↔Postgres (K-05): tablas creadas solo en boot | Dry-run: `information_schema.tables` vs inventario; abortar si hay tabla `public` no clasificada |
| A2 | Storage: borrar el QR de plataforma junto a fotos QA | Allowlist de paths presentes en `ruana_metodos_pago_manual` |
| A3 | Contadores `cp_estado` obsoletos si se conservara la tabla sin reset | Vaciar `cp_estado` |
| A4 | Jobs cron escribiendo durante el truncate | Pausar Scheduler |
| A5 | Pooler Supabase (puerto 6543) y DDL/TRUNCATE | Usar conexión **directa** (5432) o session mode, no transaction pooler, para TRUNCATE en transacción |
| A6 | RLS: irrelevante para el rol de `DATABASE_URL` (owner, sin FORCE RLS). Un script vía anon key **fallaría** | Solo `DATABASE_URL` / postgres |

### MEDIO

| ID | Riesgo | Mitigación |
|----|--------|------------|
| M1 | `RUANA-ADMIN` ausente tras el wipe | **Correcto y obligatorio.** No recrearlo en el script. Solo si más tarde un admin genera invitaciones, `obtener_o_crear_invitador_admin` podrá insertarlo; eso ya es operación post-lanzamiento, no el reset. |
| M2 | `ruana_reglas_v1.json` en imagen Cloud Run vs cambios runtime | Verificar reglas en el artefacto desplegado |
| M3 | Secuencias financieras ya tuvieron un arreglo (`*_id_seq`) | `RESTART IDENTITY` en TRUNCATE |
| M4 | Consentimientos QA se borran (correcto); no hay usuarios reales aún | OK si C5 se confirma |
| M5 | `is_production()` es true en **cualquier** Cloud Run (`K_SERVICE`) | El script **no debe negarse** a correr en prod: prod **es** el objetivo. Debe gritar el host y exigir el token |

### BAJO

| ID | Riesgo | Mitigación |
|----|--------|------------|
| B1 | JWT vivos hasta TTL (~1 h) | Reciclar revisiones Cloud Run |
| B2 | Rate limiter in-memory | Se pierde solo al reciclar |
| B3 | E2E/CI usan SQLite aislado; no pisan prod | No acción |
| B4 | Tabla `profiles` vacía | Truncate no-op |

---

## G. Diseño del reset (`prelaunch_reset.py`)

**No implementar en esta tarea.** Ubicación coherente con el repo:

- Preferida: `RUANA/scripts/prelaunch_reset.py` (junto a `purga_mensual.py`, `verify_supabase.py`, `seed_aliados.py`)
- Alias opcional: `tools/prelaunch_reset.py` que reenvíe al script anterior (el usuario pidió `tools/`)

**No** hay carpeta `tools/` hoy. **No** añadir botón en `admin_bp` ni en el panel.

### G.1 Modos

```bash
# Solo lectura. Obligatorio antes de cualquier execute.
python RUANA/scripts/prelaunch_reset.py --dry-run

# Destructivo. Abortar si falta alguno de los flags.
python RUANA/scripts/prelaunch_reset.py \
  --execute \
  --confirm RESET-RUANA-PREPRODUCTION
```

Cualquier otra cadena de confirmación → exit 2, sin abrir transacción de escritura.

Flags adicionales recomendados:

| Flag | Función |
|------|---------|
| `--allow-production` | Obligatorio si `RUANA_ENV=production` o `K_SERVICE` o el host es el pooler/proyecto `qqlxgwbmtzcfrrobrfzy` |
| `--skip-storage` | Por defecto **no** borrar Storage en v1 (o al revés: Storage opt-in `--purge-storage`) |
| `--skip-auth-users` | Por defecto no tocar `auth.users` salvo conteo > 0 y flag |
| `--backup-dir` | Ruta del dump exigido (ver §H) |
| `--require-backup` | Default true en `--execute` |

### G.2 Dry-run debe imprimir (sin secretos)

- Host y nombre de BD (nunca password/user en claro si van en la URL: redactar)
- `RUANA_ENV`, `K_SERVICE`, `RUANA_STRIPE_MODE`, `postgres` vs `sqlite`
- Si es SQLite → **abortar execute**; dry-run puede listar el fichero
- Tabla \| filas actuales \| acción KEEP/WIPE \| filas que se eliminarían
- Tablas KEEP con su `COUNT(*)`
- Tablas `public` no inventariadas → **WARNING / abort execute**
- Storage: buckets y recuento de objetos (si hay service role)
- Stripe: **solo detectar** modo y número de `stripe_account_id` en `aliados`; no llamar API de borrado
- Advertencias C1–C7, A1–A6
- Log a fichero `prelaunch_reset-YYYYMMDD-HHMMSS.log` (sin secrets)

### G.3 Execute

1. Revalidar dry-run (conteos frescos).
2. Exigir backup verificado (§H).
3. Comprobar que Scheduler/preview están pausados (check manual documentado; opcional probe HTTP).
4. Conexión directa Postgres.
5. `BEGIN`
6. Assert KEEP: `migraciones` tiene filas; `ruana_metodos_pago_manual` se lee a memoria y se re-verifica al final.
7. `TRUNCATE` lista A + `RESTART IDENTITY`. **Incluye `aliados` completo.** Prohibido `DELETE FROM aliados WHERE …` que deje `sistema` o códigos concretos.
8. Asserts estado cero (§I) **dentro de la misma transacción**, en particular `COUNT(*) FROM aliados = 0`.
9. **No** llamar a `obtener_o_crear_invitador_admin`, `crear_aliado_seed` ni `seed_aliados.py`.
10. `COMMIT` o `ROLLBACK` ante cualquier error (`SET` abort on error).
11. Storage opt-in **después** del commit (no transaccional con PG).
12. No `DROP`, no `ALTER`, no tocar ficheros de migración, no escribir reglas.

### G.4 Protecciones

- Detectar producción y exigir `--allow-production` + frase exacta
- Imprimir host/BD
- No ejecutar si `RUANA_STRIPE_MODE=live` **y** hay filas financieras (cinturón: el lanzamiento público con Live ya no debería usar este script)
- No imprimir `DATABASE_URL` completa, service role, admin JSON, PIN hashes
- Log local, no a una tabla nueva
- Prohibido endpoint HTTP admin
- Prohibido leave-behind de aliados (`estado=sistema`, códigos fijos, seeds)

---

## H. Backup y rollback

**Todavía no ejecutar.**

La rama `proyecto_original` es **backup de código**, no de datos. Antes de implementar el script se puede actualizar esa rama o etiquetar `prelaunch-reset-baseline`; **no forma parte de esta tarea** y **no se toca `proyecto_original` aquí**.

### H.1 Qué respaldar (inmediatamente antes del `--execute`)

| Pieza | Cómo | Dónde |
|-------|------|--------|
| Postgres completo | `pg_dump --format=custom --no-owner --no-acl -d "$DATABASE_URL_DIRECTA" -f ruana-prelaunch-$(date -u +%Y%m%dT%H%M%SZ).dump` | Bucket GCS privado `gs://…/prelaunch-backups/` o disco cifrado del operador; **no** el repo git |
| Solo KEEP (opcional extra) | `COPY migraciones`, `COPY ruana_metodos_pago_manual`, `COPY cp_ciudad` a CSV | Mismo sitio |
| Storage inventario | `list` de los 3 buckets (path, size, updated) | JSON junto al dump |
| Storage objetos (recomendado) | `supabase storage` / API download o `rclone` | Tarball en el mismo bucket |
| Stripe | No exportar ni borrar; anotar `RUANA_STRIPE_MODE` y recuento de `acct_` en BD | Log del dry-run |
| Código | Tag git `prelaunch-db-reset-<fecha>` en el commit del script | GitHub |

### H.2 Comprobar que el backup es válido

```bash
pg_restore --list ruana-prelaunch-….dump | head
# Debe listar tablas aliados, contactos_ruana, migraciones, ruana_metodos_pago_manual, ledger_*, grupos, …
# Comparar número de TOC entries con un dump de prueba previo en staging/local.

# Restauración de prueba a una BD *aparte* (nunca sobre prod):
createdb ruana_restore_test
pg_restore --verbose --exit-on-error -d ruana_restore_test ruana-prelaunch-….dump
psql -d ruana_restore_test -c "SELECT COUNT(*) FROM aliados;"
# El COUNT debe coincidir con el dry-run pre-reset.
dropdb ruana_restore_test
```

Sin esta prueba, **no** correr `--execute`.

### H.3 Restauración si el reset sale mal

1. Poner Cloud Run en revisión anterior o `min-instances=0` + mensaje de mantenimiento.
2. **No** re-ejecutar el reset.
3. Restaurar dump sobre la BD (o BD nueva + cambiar `DATABASE_URL`):

```bash
# Opción A: restore in-place (destructivo sobre el estado post-reset)
pg_restore --clean --if-exists --exit-on-error -d "$DATABASE_URL_DIRECTA" ruana-prelaunch-….dump

# Opción B (más segura): nueva BD Supabase, restore, apuntar Cloud Run al nuevo URL
```

4. Re-subir objetos Storage desde el tarball si se habían borrado.
5. Dry-run de conteos vs log pre-reset.
6. Reanudar Scheduler y preview solo cuando los conteos coincidan.

Stripe no se habrá tocado: no hay rollback Stripe.

---

## I. Verificación posterior (estado cero)

Tras el reset, RUANA debe poder:

1. Servir `/api/health` y `/api/catalogo/oficios` (catálogo de fichero).
2. Login admin con Secret Manager (no depende de `aliados`). **0 aliados en BD.**
3. El script **no** llama a `obtener_o_crear_invitador_admin`. Queda `aliados` vacío.
4. Un aliado **nuevo real** se registra **sin** invitación (`POST /api/aliados/registrar`) con CP + oficio de catálogo → se crea el primer grupo territorial y `cp_estado`.

### I.1 Queries de certificación (objetivo)

```sql
SELECT 'aliados' AS t, COUNT(*) FROM aliados
UNION ALL SELECT 'solicitudes', COUNT(*) FROM solicitudes
UNION ALL SELECT 'contactos_ruana', COUNT(*) FROM contactos_ruana
UNION ALL SELECT 'chat_mensajes', COUNT(*) FROM chat_mensajes
UNION ALL SELECT 'negociacion_eventos', COUNT(*) FROM negociacion_eventos
UNION ALL SELECT 'invitaciones', COUNT(*) FROM invitaciones
UNION ALL SELECT 'invitacion_campanas', COUNT(*) FROM invitacion_campanas
UNION ALL SELECT 'referidos', COUNT(*) FROM referidos
UNION ALL SELECT 'notificaciones_aliado', COUNT(*) FROM notificaciones_aliado
UNION ALL SELECT 'score_movimientos', COUNT(*) FROM score_movimientos
UNION ALL SELECT 'evaluaciones', COUNT(*) FROM evaluaciones
UNION ALL SELECT 'grupos', COUNT(*) FROM grupos
UNION ALL SELECT 'competencia', COUNT(*) FROM competencia
UNION ALL SELECT 'payment_conflicts', COUNT(*) FROM payment_conflicts
UNION ALL SELECT 'financial_transfers', COUNT(*) FROM financial_transfers
UNION ALL SELECT 'ledger_transactions', COUNT(*) FROM ledger_transactions
UNION ALL SELECT 'stripe_webhook_events', COUNT(*) FROM stripe_webhook_events
UNION ALL SELECT 'aliados_sistema', COUNT(*) FROM aliados WHERE estado = 'sistema'
UNION ALL SELECT 'placeholders', COUNT(*) FROM aliados WHERE estado = 'pendiente_completar'
UNION ALL SELECT 'aliados_eliminados', COUNT(*) FROM aliados_eliminados
UNION ALL SELECT 'ruana_pago_manual_allowlist', COUNT(*) FROM ruana_pago_manual_aliados_habilitados;
-- todos 0

SELECT 'migraciones' AS t, COUNT(*) FROM migraciones;           -- > 0
SELECT COUNT(*) FROM ruana_metodos_pago_manual;                 -- conservar filas previas
SELECT COUNT(*) FROM cp_ciudad;                                 -- >= conteo pre-reset
```

Mapeo a los indicadores pedidos:

| Indicador | Query / criterio |
|-----------|------------------|
| Aliados: 0 | `COUNT(*) FROM aliados` — **todas** las filas, incluido `sistema` / `RUANA-ADMIN` |
| Aliados sistema: 0 | `COUNT(*) FROM aliados WHERE estado = 'sistema'` |
| Solicitudes: 0 | `solicitudes` + `solicitudes_semanales` |
| Chats: 0 | no hay tabla `chats`; el chat es `chat_mensajes` (y el encargo es `contactos_ruana`) |
| Mensajes: 0 | `chat_mensajes` + `ruana_soporte_mensajes` + `negociacion_eventos` |
| Negociaciones activas: 0 | `contactos_ruana` (estado no cerrado) y `negociacion_eventos` |
| Acuerdos: 0 | `contactos_ruana` |
| Pagos: 0 | `estado_pago` en contactos + `financial_transfers` + `ingresos_ruana` |
| Invitaciones de prueba: 0 | `invitaciones` + `invitaciones_oficio` + `invitacion_campanas` |
| Notificaciones: 0 | `notificaciones_aliado` |
| Eventos de score: 0 | `score_movimientos` |
| Referidos: 0 | `referidos` |
| Placeholders: 0 | `aliados.estado='pendiente_completar'` |

### I.2 Secuencias e IDs (§9)

| Identificador | Comportamiento | ¿Reiniciar? |
|---------------|----------------|-------------|
| `aliados.id`, `grupos.id`, `contactos_ruana.id`, etc. (IDENTITY/BIGSERIAL) | Surrogates | **Sí**, vía `TRUNCATE … RESTART IDENTITY` |
| Secuencias financieras `{tabla}_id_seq` (reparadas en `20260903000100`) | Igual | **Sí** |
| Código de aliado (5 dígitos aleatorios) | No es sequence | **No** hay nada que reiniciar; el espacio 10000–99999 queda libre al vaciar |
| Códigos legado `A0001`, seeds `ALFA01` | Dejan de existir | No reutilizar a propósito |
| Nombre de grupo `RUANA-{8}-{SUFIJO}` | Aleatorio | No |
| Invitación oficio `RUANA-{grupo_id}-…` | Depende de `grupos.id` | Tras RESTART IDENTITY, `grupo_id` volverá a 1, 2, … — **aceptable** en lanzamiento |
| Números de acuerdo/solicitud | Son el `id` IDENTITY | Quedarán desde 1. **Sí conviene** para un producto que “empieza” |
| `invitaciones.codigo` | 5 dígitos aleatorios | No sequence |

**No** reiniciar nada en esta tarea.

---

## J. Archivos que habría que crear o modificar

**No modificados en esta tarea** (salvo este plan).

| Archivo | Acción futura |
|---------|----------------|
| `RUANA/scripts/prelaunch_reset.py` | **Crear.** CLI dry-run/execute, inventario KEEP/WIPE, TRUNCATE, asserts, log |
| `tools/prelaunch_reset.py` | **Crear opcional.** Wrapper de una línea |
| `RUANA/tests/test_prelaunch_reset.py` | **Crear.** SQLite o Postgres de test: dry-run no escribe; execute exige token; KEEP intacto; WIPE a 0; aborta sin confirmación; aborta en SQLite si `--execute` |
| `docs/operaciones/PRELAUNCH_RESET.md` | Runbook de ejecución (ventana, pausa cron, backup, comandos) |
| `docs/README.md` | Enlace al plan / runbook |
| `RUANA/scripts/verify_supabase.py` | Posible reutilización para listar buckets en dry-run (importar, no duplicar secrets) |
| Panel admin / `admin_bp.py` | **No tocar.** Prohibido botón “borrar todo” |

No tocar: migraciones SQL existentes, `schema_service.py` DDL, `proyecto_original`, workflows de deploy (salvo, en el runbook, “pausar preview”).

---

## K. Veredicto

### READY TO IMPLEMENT RESET

**Motivo:** el modelo de datos permite un wipe operativo dejando intactos esquema, `migraciones`, catálogos en fichero, `cp_ciudad`, métodos de cobro manual y secretos. **Ningún aliado se conserva.** La app no exige un grupo ni un aliado preexistentes para arrancar. El admin del panel no vive en Postgres. No hay Redis ni Firestore con estado de aliados.

**No significa “listo para `--execute` hoy”.** Antes de la primera ejecución real hace falta:

1. Implementar el script con las protecciones de §G.
2. `--dry-run` contra el Postgres real (este informe **no** tiene conteos).
3. Backup `pg_dump` verificado con restore de prueba (§H).
4. Congelar `ruana-preview` y Cloud Scheduler.
5. Confirmación de producto de que no hay ni un usuario/pago real (C5).
6. Decisión explícita sobre Storage (v1 puede dejar objetos huérfanos y limpiarlos después).
7. Stripe Test **intocado** hasta una fase dedicada, **antes** del flip Live.

**Bloqueos críticos de diseño (ya resueltos en el plan, fatales si se ignoran):** C1 KEEP métodos de pago, C2 KEEP migraciones, C3 TRUNCATE ledger, C6 no `CASCADE` ciego.

---

## Anexo 1 — Cómo se identifican (o no) datos QA

| Mecanismo | ¿Sirve para borrar solo test en prod? |
|-----------|----------------------------------------|
| `aliados.estado='pendiente_completar'` | Solo placeholders legacy; **no** cubre aliados QA activos |
| Seeds `ALFA01`–`DELTA04`, emails `@ruana.local` | Heurística incompleta |
| E2E `Aliado QA *`, campañas `RUANA-QA*` | Playwright usa **SQLite propio**, no prod |
| `RUANA_ENV` / `is_test_context()` | Entorno de proceso, **no** columna |
| `RUANA_STRIPE_MODE=test` | Todo el proyecto está en test; no distingue filas |
| Columna `is_qa` / `demo` | **No existe** |
| `invitaciones.usado` | No implica QA |

**Conclusión:** no hay forma fiable de borrar “solo test data” en el Postgres compartido. El reset es all-or-nothing sobre tablas A.

---

## Anexo 2 — Inventario compacto (A vaciar / B conservar)

| Tabla / recurso | Contenido | ¿Datos prueba? | Conservar | Vaciar | Dependencias | Riesgo |
|-----------------|-----------|----------------|-----------|--------|--------------|--------|
| Esquema PG + RLS + triggers | DDL | No | Sí | No | — | C2/C6 si DROP |
| `migraciones` | One-shots aplicados | No | Sí | No | Boot `schema_service` | **C2 CRÍTICO** |
| `ruana_metodos_pago_manual` | IBAN/Bizum/QR plataforma | Config real | Sí | No | Storage QR | **C1 CRÍTICO** |
| `cp_ciudad` | CP→ciudad | Referencia | Sí | No | JSON `cp_ciudad_es.json` | Bajo |
| `cp_estado` | Contadores territoriales | Sí (sesgados) | Estructura | Sí | `grupos` | A3 |
| `grupos` | Grupos runtime | Sí | Estructura | Sí | Muchas FK | Medio |
| `aliados` | **Todos** los perfiles (QA, seeds, `sistema`, bajas) | Sí — todos | Solo la tabla vacía | **Todas las filas** | Raíz operativa | C5 |
| `profiles` / `auth.users` | Auth futuro | Posible | Estructura | Sí si hay filas | `aliados.auth_user_id` | Medio |
| `solicitudes*` | Conexiones / semanales | Sí | Estructura | Sí | `grupos`, `aliados` | Bajo |
| `contactos_ruana` | Encargos/pagos/negociación | Sí | Estructura | Sí | Hub FK | Alto (RESTRICT) |
| `chat_mensajes` | Chat | Sí | Estructura | Sí | `contactos` CASCADE | Bajo |
| `negociacion_eventos` | Ofertas | Sí | Estructura | Sí | `contactos` | Bajo |
| `invitaciones*` / `referidos` / campañas | Red | Sí | Estructura | Sí | `aliados` | Medio |
| Score / evaluaciones / notificaciones / actividad | Operativo | Sí | Estructura | Sí | `aliados` CASCADE | Bajo |
| `competencia*` | Plazas | Sí | Estructura | Sí | `grupos`/`aliados` | Medio |
| `catalogo_servicios_aliado` | Servicios del aliado | Sí | Estructura | Sí | `aliados` | No confundir con `oficios_ruana.json` |
| `oficios_ruana.json` | Catálogo maestro | No | Sí | No | Disco | — |
| `ruana_reglas_v1.json` | Parámetros Score/Apoyo | No | Sí | No | Disco / imagen | M2 |
| Admin Secret Manager | Login panel | No | Sí | No | Fuera de BD | — |
| `ruana_pago_manual_aliados_habilitados` | Allowlist | Sí | Estructura | Sí | códigos aliado | Bajo |
| Stack `financial_*` / `stripe_*` / `ledger_*` | Pagos test | Sí | Estructura + triggers | Sí (TRUNCATE) | `contactos` | **C3 CRÍTICO** |
| `payment_conflicts*` | Impugnaciones | Sí | Estructura | Sí | `contactos`/`aliados` | Medio |
| Soporte / OTP / consentimientos / bajas | PII QA | Sí | Estructura | Sí | `aliados` | Bajo |
| `audit_log` / `eventos_sistema` / `financial_audit_log` | Trazas | Sí | Estructura | Sí | — | Bajo |
| `migracion_territorio_*` | Informe migración | Sí | Estructura | Sí | — | Bajo |
| Storage objetos | Ficheros | Sí | Buckets | Objetos (fase) | URLs en BD | A2 |
| Stripe Dashboard | acct_/pi_/tr_ | Test | Cuentas plataforma | No en esta fase | IDs en BD | C7 |
| Firebase Hosting | Estático | No | Sí | No | — | — |
| Redis | N/A | — | — | — | — | — |
| Env vars / feature flags | Config proceso | No | Sí | No | Cloud Run | — |

---

## Anexo 3 — Arranque tras estado cero (comprobado en código)

- `DBManager` abre Postgres y `_init_postgres_schema()` hace `CREATE TABLE IF NOT EXISTS` + parches. No inserta aliados.
- `obtener_o_crear_grupo` crea el primer grupo del CP al registrar.
- `territorio_repo` inserta `cp_estado` con `modo='territorial'`.
- Registro **no exige** invitación.
- Catálogo: `catalogo_service.get_catalogo_oficios_ruana` lee JSON.
- Login aliado falla con 0 aliados (esperado). Login admin no usa `aliados`.

---

*Fin del plan. Ningún dato ha sido modificado.*
