# RLS en schema `public` (alerta `rls_disabled_in_public`)

**Estado:** migración lista, **no aplicada en producción**.  
**Migración:** `supabase/migrations/20260902000200_enable_rls_public_tables.sql`  
**Fecha inventario:** 2026-09-02

## 1. Conexión a producción

No se pudo listar el catálogo **en vivo**. La cuenta de servicio de este entorno (`ruana-cursor-agent@ruana-4293f.iam.gserviceaccount.com`) no tiene `secretmanager.versions.access` sobre `ruana-database-url`. No hay `DATABASE_URL` ni CLI `supabase` autenticada en el pod.

El inventario de abajo sale de:

- `supabase/migrations/` (qué tablas se crearon y cuáles ya tenían `ENABLE ROW LEVEL SECURITY`)
- `RUANA/core/services/schema_service.py` → `_init_postgres_schema` (tablas que Flask crea al arrancar en Postgres si no existen)
- búsqueda de usos en `RUANA/core`, blueprints y frontend

La migración **no asume esa lista**: activa RLS con un `DO` sobre `pg_class` (`relrowsecurity = false`). Al aplicarla, cubre también tablas que existan en prod y no estén en git.

Los helpers `current_aliado_codigo()` / `is_ruana_admin()` son fail-closed si no existe `public.profiles` (esquema nacido solo del boot Flask).

**Antes de aplicar**, ejecutar en SQL Editor de Supabase (solo lectura):

```sql
SELECT c.relname AS tabla,
       c.relrowsecurity AS rls,
       c.relforcerowsecurity AS force_rls,
       (SELECT count(*) FROM pg_policies p
        WHERE p.schemaname = 'public' AND p.tablename = c.relname) AS politicas
FROM pg_class c
JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE n.nspname = 'public' AND c.relkind = 'r'
ORDER BY c.relrowsecurity, c.relname;
```

## 2. Cómo se consulta hoy (todos los caminos)

| Camino | ¿Usa tablas `public`? | Rol Postgres |
| --- | --- | --- |
| Flask / Cloud Run (`DATABASE_URL` + psycopg) | Sí, **único camino de negocio** | Dueño / típico `postgres` → **elude RLS** si no hay `FORCE` |
| `supabase-py` service role | Solo **Storage** (`storage_manager.py`) | `service_role` elude RLS (K-02) |
| Frontend (HTML/JS) | No. Llama APIs Flask (`/api/...`) | — |
| supabase-js / PostgREST / anon key | **No hay usos en el repo** | `anon` vería todo **si RLS está off** |
| Cloud Functions | No hay funciones en el repo que consulten estas tablas | — |

Consecuencia: **activar RLS sin `FORCE` no rompe pagos ni Score en Flask.** Sí cierra el REST de la anon key.

Si se activara RLS **sin políticas** en una tabla: PostgREST/anon deja de devolver filas (o 401 si además se revoca GRANT). Flask sigue igual.

## 3. Tablas que en git ya tenían RLS

Migración init `20260519000100_init_ruana_clean.sql` (si se aplicó en ese proyecto):

`profiles`, `grupos`, `aliados`, `solicitudes`, `contactos_ruana`, `chat_mensajes`, `contacto_panel_oculto`, `contacto_penalizaciones_aplicadas`, `confirmaciones_trabajo`, `payment_conflicts`, `ingresos_ruana`, `score_movimientos`, `evaluaciones`, `evaluaciones_historico`, `invitaciones`, `referidos`, `invitaciones_oficio`, `notificaciones_aliado`, `competencia`, `avisos_grupo`, `grupo_oficio_cerrado`, `eventos_sistema`, `audit_log`.

Más tarde, solo `ENABLE` (sin políticas → deny REST):

`solicitudes_semanales`, `solicitudes_semanales_respuestas`, `ruana_metodos_pago_manual`, `ruana_pago_manual_aliados_habilitados`.

Si el proyecto se pobló **solo** con el boot de Flask, es posible que las tablas init **no** tengan RLS. El bucle dinámico las cubre.

## 4. Tablas que en git NO activaban RLS (candidatas de la alerta)

Sensibilidad y efecto de “RLS ON / cero políticas” (PostgREST cerrado; Flask intacto):

### Crítico (PII, dinero, secretos)

| Tabla | Qué hay | Dónde se usa | RLS ON sin políticas |
| --- | --- | --- | --- |
| `aliado_recuperacion_acceso` | OTP hash/salt, email | `aliado_repo` (PIN / recuperación) | Cierra filtrado de OTP por anon. Flask OK. |
| `ruana_metodos_pago_manual` | IBAN / Bizum / QR | `pago_repo` / `pago_service` | Cierra cobro manual. Flask OK. |
| `ruana_pago_manual_aliados_habilitados` | Allowlist de pago manual | `pago_repo` | Igual. |
| `stripe_webhook_events` | Ids de eventos Stripe | `stripe_webhook_repo`, webhooks | Cierra telemetría Stripe. Flask OK. |
| `financial_idempotency_keys` | Claves de idempotencia | schema + servicios financieros | Cierra replay metadata. Flask OK. |
| `ledger_*` | Libro mayor | `financial_ledger_repo` | Cierra contabilidad. Flask OK. |
| `financial_transfers*` / `refunds*` / `disputes*` / `reconciliation*` | Dinero y disputas | repos `financial_*` | Cierra backoffice financiero. Flask OK. |
| `stripe_refunds` / `stripe_disputes` | Espejo Stripe | webhook + refund/dispute services | Flask OK. |
| `aliados` / `aliados_eliminados` | Identidad, contacto | casi todo el backend | Si init no se aplicó: hoy estarían abiertas a anon. |
| `contactos_ruana` / `ingresos_ruana` | Encargos e importes | contacto/pago | Idem. |
| `consentimientos_aliado` / `solicitudes_baja_aliado` | RGPD | `aliado_repo` | Flask OK. |

### Alto (score, red, chat)

| Tabla | Qué hay | Uso | RLS ON sin políticas |
| --- | --- | --- | --- |
| `score_movimientos` / `evaluaciones*` | Score | `score_repo`, `evaluacion_repo` | No rompe el motor de Score (Flask). |
| `grupo_crecimiento_recompensas` | +score por invitación | `grupo_crecimiento_repo` | Flask OK. |
| `aliado_accesos_dia` | Racha de logins | `aliado_repo`, score regla 8 | Flask OK. |
| `negociacion_eventos` | Ofertas de cierre | `negociacion_repo` | Flask OK. |
| `chat_mensajes` / `ruana_soporte_*` | Mensajes | `chat_repo` | Flask OK. Realtime init está en DDL; **cliente Realtime no verificado**. |
| `catalogo_servicios_aliado` | Precios del aliado | `catalogo_repo` | Flask OK. |
| `invitacion_campanas` / `_usos` | Códigos de campaña | `invitacion_repo` | Flask OK. |
| `competencia_pendiente` | Cola de retos | `competencia_repo` | Flask OK. |
| `solicitudes_semanales*` | Encargos de la semana | `solicitud_semanal_*` | Ya tenían RLS en migración; se añaden políticas SELECT. |

### Admin / automatización

`financial_job_leases`, `financial_automation_runs`, `financial_alerts`, `financial_action_approvals`, `financial_audit_log`, `financial_admin_alert_actions`, `payment_conflict_*`, `migraciones`, `eventos_sistema`, `audit_log`.

Todas se tocan desde Flask (cron HTTP, panel admin). Ninguna desde el navegador contra PostgREST.

## 5. Decisiones (confirmar si no encajan)

1. **Sin `FORCE ROW LEVEL SECURITY`.** Con FORCE, el dueño de tabla (Flask) también quedaría sujeto a RLS y se romperían pagos y Score.
2. **Tablas de secreto (OTP, IBAN, webhooks, idempotency, `migraciones`): cero políticas.** Ni el JWT admin de un futuro Supabase Auth las lee por REST.
3. **Financiero / Stripe / ledger: solo `SELECT` si `is_ruana_admin()`.** Cero INSERT/UPDATE/DELETE por REST.
4. **Score: el aliado puede SELECT sus filas; no puede escribirlas por REST.**
5. **¿Un aliado debería ver por REST las solicitudes semanales de todo su grupo, no solo las suyas?** Hoy la política es “las mías o admin”. Si quieres visibilidad de grupo, dímelo antes de aplicar.

## 6. Cómo probarla antes de producción

### Staging / SQL Editor (recomendado)

1. Correr el `SELECT` de diagnóstico y guardar el resultado (tablas con `rls = false`).
2. Aplicar la migración en un **proyecto Supabase de staging** (o clone) que no sea prod.
3. Con la **anon key** de staging:

   ```bash
   curl -sS "$SUPABASE_URL/rest/v1/aliados?select=codigo&limit=1" \
     -H "apikey: $SUPABASE_ANON_KEY" \
     -H "Authorization: Bearer $SUPABASE_ANON_KEY"
   ```

   Esperado: `[]` o 401, **nunca** filas.
   Repetir con `contactos_ruana`, `score_movimientos`, `stripe_webhook_events`, `ruana_metodos_pago_manual`.

4. Arrancar la app Flask de staging contra esa BD (`DATABASE_URL` de staging).
5. Smoke:

   - login aliado + dashboard
   - un contacto con Stripe (test mode): checkout, webhook, score no se mueve salvo reglas reales
   - panel admin: listado aliados, conflictos, ledger si aplica
   - cron FASE 11 (`ejecutar-ciclo`) en staging

### Local

CI usa SQLite: esta migración **no se ejecuta** en pytest. El test de repo solo valida el SQL (no `FORCE`, deny anon, helpers).

Para Postgres local: `supabase start` (si se usa) y `supabase db reset` / aplicar migraciones en el stack local, luego el mismo `curl` con la anon key del stack.

## 7. Qué monitorizar tras aplicarla en prod

- Cloud Run: 5xx en `/api/pagos/*`, `/api/stripe/*`, webhooks, `/api/aliado/*`, `/api/admin/*`.
- **No** esperar 403 de Flask: Flask no habla PostgREST. Un 403 nuevo casi seguro es de sesión Flask, no de RLS.
- Logs Postgres / API de Supabase: `new row violates row-level security` — si aparece, alguien (o un job) está usando `anon`/`authenticated` en lugar de `DATABASE_URL`.
- Alertas Stripe: webhooks que dejan de marcarse procesados.
- Score: ciclos de evaluación y rachas (`aliado_accesos_dia`) siguen escribiendo.
- Dashboard Supabase: la alerta `rls_disabled_in_public` debe desaparecer cuando no quede ninguna tabla public con RLS off.

## 8. Cómo NO aplicarla

No pegar este SQL a ciegas en prod el mismo día del go-live Stripe sin el `curl` anon + smoke Flask en staging. No activar `FORCE ROW LEVEL SECURITY`.
