-- =============================================================================
-- RLS en schema public — aplicada en producción (2026-09-04, workflow security-ops).
--
-- Alerta Supabase: rls_disabled_in_public (anon key puede leer tablas sin RLS).
--
-- Arquitectura actual (verificada en código, 2026-09-02):
--   * Flask habla con Postgres vía DATABASE_URL (psycopg). Ese rol suele ser
--     dueño de las tablas o superuser → RLS NO se aplica a Flask
--     mientras NO se use FORCE ROW LEVEL SECURITY.
--   * El cliente supabase-py solo se usa para Storage (service_role).
--   * El frontend NO consulta PostgREST ni supabase-js.
--   * service_role elude RLS (K-02). Esta migración cierra el agujero de la
--     anon key; NO sustituye la autorización Flask.
--
-- Esta migración:
--   1) Activa RLS en TODA tabla public que aún no lo tenga (bucle dinámico).
--   2) NO usa FORCE ROW LEVEL SECURITY (rompería Flask / dueño de tabla).
--   3) Añade políticas para el rol `authenticated` (JWT Supabase + profiles).
--      Hoy el login no rellena profiles/auth.uid(); esas políticas son la
--      red para PostgREST, no el camino Flask.
--   4) No crea políticas para `anon` → deny por defecto.
--   5) Tablas de secretos (OTP, IBAN, webhooks Stripe, ledger, idempotency):
--      RLS ON y CERO políticas → nadie vía anon/authenticated. Solo Flask.
--
-- Diagnóstico previo (SQL Editor, solo lectura):
--   SELECT c.relname AS tabla, c.relrowsecurity AS rls, c.relforcerowsecurity AS force_rls
--   FROM pg_class c
--   JOIN pg_namespace n ON n.oid = c.relnamespace
--   WHERE n.nspname = 'public' AND c.relkind = 'r'
--   ORDER BY c.relrowsecurity, c.relname;
-- =============================================================================

BEGIN;

-- Helpers de rol (idempotentes). Dependen de public.profiles + auth.uid().
-- Si profiles no existe aún, las funciones siguen siendo válidas: al ejecutarse
-- devolverán NULL/false y las políticas denegarán (fail-closed).

CREATE OR REPLACE FUNCTION public.current_aliado_codigo()
RETURNS text
LANGUAGE plpgsql
STABLE
SECURITY DEFINER
SET search_path = public
AS $$
BEGIN
  IF to_regclass('public.profiles') IS NULL THEN
    RETURN NULL;
  END IF;
  RETURN (
    SELECT p.aliado_codigo
    FROM public.profiles p
    WHERE p.id = auth.uid()
    LIMIT 1
  );
END;
$$;

CREATE OR REPLACE FUNCTION public.is_ruana_admin()
RETURNS boolean
LANGUAGE plpgsql
STABLE
SECURITY DEFINER
SET search_path = public
AS $$
BEGIN
  IF to_regclass('public.profiles') IS NULL THEN
    RETURN false;
  END IF;
  RETURN EXISTS (
    SELECT 1
    FROM public.profiles p
    WHERE p.id = auth.uid()
      AND p.role = 'admin'
  );
END;
$$;

-- 1) Activar RLS en cualquier tabla public que aún lo tenga apagado.
DO $$
DECLARE
  r record;
BEGIN
  FOR r IN
    SELECT c.relname
    FROM pg_class c
    JOIN pg_namespace n ON n.oid = c.relnamespace
    WHERE n.nspname = 'public'
      AND c.relkind = 'r'
      AND c.relrowsecurity = false
    ORDER BY c.relname
  LOOP
    EXECUTE format('ALTER TABLE public.%I ENABLE ROW LEVEL SECURITY', r.relname);
    RAISE NOTICE 'RLS enabled on public.%', r.relname;
  END LOOP;
END
$$;

-- Defensa extra: la anon key no debe tener GRANT sobre tablas de negocio.
-- Storage vive en schema storage; no se toca. Si el rol no puede REVOKE,
-- RLS enable sigue siendo la barrera (fail-closed para anon sin políticas).
DO $$
BEGIN
  REVOKE ALL ON ALL TABLES IN SCHEMA public FROM anon;
  REVOKE ALL ON ALL SEQUENCES IN SCHEMA public FROM anon;
EXCEPTION WHEN OTHERS THEN
  RAISE NOTICE 'REVOKE anon skipped: %', SQLERRM;
END
$$;

DO $$
BEGIN
  ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE ALL ON TABLES FROM anon;
  ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE ALL ON SEQUENCES FROM anon;
EXCEPTION WHEN OTHERS THEN
  RAISE NOTICE 'ALTER DEFAULT PRIVILEGES anon skipped: %', SQLERRM;
END
$$;

-- Helper: crea una política SELECT authenticated si la tabla existe y la
-- política no está ya creada (compatible con políticas de la migración init).
CREATE OR REPLACE FUNCTION public._ruana_policy_select(
  p_table text,
  p_name text,
  p_using text
) RETURNS void
LANGUAGE plpgsql
AS $$
BEGIN
  IF to_regclass('public.' || p_table) IS NULL THEN
    RETURN;
  END IF;
  IF EXISTS (
    SELECT 1 FROM pg_policies
    WHERE schemaname = 'public'
      AND tablename = p_table
      AND policyname = p_name
  ) THEN
    RETURN;
  END IF;
  EXECUTE format(
    'CREATE POLICY %I ON public.%I FOR SELECT TO authenticated USING (%s)',
    p_name, p_table, p_using
  );
END;
$$;

-- ---------------------------------------------------------------------------
-- Políticas SELECT (authenticated). Sin INSERT/UPDATE/DELETE: las mutaciones
-- siguen siendo solo Flask. Prioridad: no abrir pagos ni Score por REST.
-- ---------------------------------------------------------------------------

-- Aliado ve/edita lo suyo vía API Flask; aquí solo lectura REST futura.
SELECT public._ruana_policy_select(
  'catalogo_servicios_aliado',
  'ruana_catalogo_select_own_or_admin',
  'public.is_ruana_admin() OR aliado_codigo = public.current_aliado_codigo()'
);

SELECT public._ruana_policy_select(
  'consentimientos_aliado',
  'ruana_consentimientos_select_own_or_admin',
  'public.is_ruana_admin() OR codigo_aliado = public.current_aliado_codigo()'
);

SELECT public._ruana_policy_select(
  'solicitudes_baja_aliado',
  'ruana_baja_select_own_or_admin',
  'public.is_ruana_admin() OR codigo_aliado = public.current_aliado_codigo()'
);

SELECT public._ruana_policy_select(
  'aliado_accesos_dia',
  'ruana_accesos_select_own_or_admin',
  'public.is_ruana_admin() OR codigo_aliado = public.current_aliado_codigo()'
);

SELECT public._ruana_policy_select(
  'grupo_crecimiento_recompensas',
  'ruana_crecimiento_select_party_or_admin',
  'public.is_ruana_admin() OR invitador_codigo = public.current_aliado_codigo() OR invitado_codigo = public.current_aliado_codigo()'
);

SELECT public._ruana_policy_select(
  'competencia_pendiente',
  'ruana_comp_pend_select_own_or_admin',
  'public.is_ruana_admin() OR aliado_codigo = public.current_aliado_codigo()'
);

SELECT public._ruana_policy_select(
  'invitacion_campana_usos',
  'ruana_campana_usos_select_own_or_admin',
  'public.is_ruana_admin() OR codigo_aliado = public.current_aliado_codigo()'
);

-- Campañas (códigos de alta masiva): solo admin.
SELECT public._ruana_policy_select(
  'invitacion_campanas',
  'ruana_campanas_select_admin',
  'public.is_ruana_admin()'
);

-- PII de bajas: solo admin.
SELECT public._ruana_policy_select(
  'aliados_eliminados',
  'ruana_eliminados_select_admin',
  'public.is_ruana_admin()'
);

SELECT public._ruana_policy_select(
  'ruana_soporte_conversaciones',
  'ruana_soporte_conv_select_own_or_admin',
  'public.is_ruana_admin() OR aliado_codigo = public.current_aliado_codigo()'
);

SELECT public._ruana_policy_select(
  'ruana_soporte_mensajes',
  'ruana_soporte_msg_select_own_or_admin',
  $u$
    public.is_ruana_admin()
    OR EXISTS (
      SELECT 1 FROM public.ruana_soporte_conversaciones c
      WHERE c.id = ruana_soporte_mensajes.conversacion_id
        AND c.aliado_codigo = public.current_aliado_codigo()
    )
  $u$
);

SELECT public._ruana_policy_select(
  'negociacion_eventos',
  'ruana_neg_eventos_select_party_or_admin',
  $u$
    public.is_ruana_admin()
    OR EXISTS (
      SELECT 1 FROM public.contactos_ruana c
      WHERE c.id = negociacion_eventos.contacto_id
        AND public.current_aliado_codigo() IN (c.solicitante_codigo, c.profesional_codigo)
    )
  $u$
);

SELECT public._ruana_policy_select(
  'solicitudes_semanales',
  'ruana_sol_sem_select_own_or_admin',
  'public.is_ruana_admin() OR solicitante_codigo = public.current_aliado_codigo()'
);

SELECT public._ruana_policy_select(
  'solicitudes_semanales_respuestas',
  'ruana_sol_sem_resp_select_own_or_admin',
  'public.is_ruana_admin() OR aliado_codigo = public.current_aliado_codigo()'
);

-- Conflictos de pago (hijas): solo admin por REST. Los aliados las ven vía Flask.
SELECT public._ruana_policy_select(
  'payment_conflict_evidence',
  'ruana_pc_evidence_select_admin',
  'public.is_ruana_admin()'
);

SELECT public._ruana_policy_select(
  'payment_conflict_comments',
  'ruana_pc_comments_select_admin',
  'public.is_ruana_admin()'
);

SELECT public._ruana_policy_select(
  'payment_conflict_actions',
  'ruana_pc_actions_select_admin',
  'public.is_ruana_admin()'
);

SELECT public._ruana_policy_select(
  'payment_conflict_audit',
  'ruana_pc_audit_select_admin',
  'public.is_ruana_admin()'
);

-- Score: el aliado puede VER su propio historial; no puede escribirlo por REST.
SELECT public._ruana_policy_select(
  'score_movimientos',
  'ruana_score_mov_select_own_or_admin',
  'public.is_ruana_admin() OR codigo_aliado = public.current_aliado_codigo()'
);

SELECT public._ruana_policy_select(
  'evaluaciones',
  'ruana_eval_select_own_or_admin',
  'public.is_ruana_admin() OR codigo_aliado = public.current_aliado_codigo()'
);

SELECT public._ruana_policy_select(
  'evaluaciones_historico',
  'ruana_eval_hist_select_own_or_admin',
  'public.is_ruana_admin() OR codigo_aliado = public.current_aliado_codigo()'
);

-- Tablas financieras / Stripe / ledger: SOLO admin SELECT. Cero escrituras REST.
-- Flask (DATABASE_URL) no usa estas políticas.
DO $$
DECLARE
  t text;
BEGIN
  FOREACH t IN ARRAY ARRAY[
    'financial_job_leases',
    'financial_automation_runs',
    'financial_alerts',
    'financial_action_approvals',
    'financial_audit_log',
    'financial_admin_alert_actions',
    'ledger_transactions',
    'ledger_entries',
    'ledger_event_links',
    'ledger_account_balances',
    'financial_reconciliation_executions',
    'financial_reconciliation_snapshots',
    'financial_reconciliation_resource_results',
    'financial_disputes',
    'financial_dispute_evidence',
    'financial_dispute_attempts',
    'financial_refunds',
    'financial_refund_attempts',
    'financial_transfer_snapshots',
    'financial_transfers',
    'financial_transfer_attempts',
    'financial_reconciliation',
    'stripe_refunds',
    'stripe_disputes'
  ]
  LOOP
    PERFORM public._ruana_policy_select(t, 'ruana_' || t || '_select_admin', 'public.is_ruana_admin()');
  END LOOP;
END
$$;

-- ---------------------------------------------------------------------------
-- SIN políticas (deny anon + deny authenticated) a propósito:
--   aliado_recuperacion_acceso  — hashes OTP / salts
--   ruana_metodos_pago_manual   — IBAN / Bizum
--   ruana_pago_manual_aliados_habilitados
--   stripe_webhook_events       — payloads / ids Stripe
--   financial_idempotency_keys
--   migraciones
-- Solo Flask (DATABASE_URL) las toca.
-- ---------------------------------------------------------------------------

DROP FUNCTION public._ruana_policy_select(text, text, text);

COMMIT;
