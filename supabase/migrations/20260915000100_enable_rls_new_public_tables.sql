-- =============================================================================
-- RLS catch-all — tablas public creadas después del 2026-09-04.
--
-- Alerta Supabase 13 Sep 2026: rls_disabled_in_public (ruana APP).
-- La migración 20260902000200 cubrió 66 tablas. Luego Flask/SQL creó
-- competencia_pendiente, cp_*, aliado_avisos_vistos, migracion_territorio_*
-- y migraciones sin ENABLE ROW LEVEL SECURITY.
--
-- Sin FORCE ROW LEVEL SECURITY: Flask (DATABASE_URL, dueño) no se ve afectado.
-- Anon sin políticas = deny. El frontend no usa PostgREST.
-- =============================================================================

BEGIN;

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

SELECT public._ruana_policy_select(
  'competencia',
  'ruana_competencia_select_party_or_admin',
  $u$
    public.is_ruana_admin()
    OR aliado_original_codigo = public.current_aliado_codigo()
    OR retador_codigo = public.current_aliado_codigo()
    OR ganador_codigo = public.current_aliado_codigo()
  $u$
);

SELECT public._ruana_policy_select(
  'competencia_pendiente',
  'ruana_comp_pend_select_own_or_admin',
  'public.is_ruana_admin() OR aliado_codigo = public.current_aliado_codigo()'
);

SELECT public._ruana_policy_select(
  'aliado_avisos_vistos',
  'ruana_avisos_vistos_select_own_or_admin',
  'public.is_ruana_admin() OR aliado_codigo = public.current_aliado_codigo()'
);

SELECT public._ruana_policy_select(
  'cp_ciudad',
  'ruana_cp_ciudad_select_admin',
  'public.is_ruana_admin()'
);

SELECT public._ruana_policy_select(
  'cp_estado',
  'ruana_cp_estado_select_admin',
  'public.is_ruana_admin()'
);

SELECT public._ruana_policy_select(
  'cp_independencia_solicitudes',
  'ruana_cp_indep_select_admin',
  'public.is_ruana_admin()'
);

DROP FUNCTION public._ruana_policy_select(text, text, text);

CREATE OR REPLACE FUNCTION public.ruana_enable_rls_on_create_table()
RETURNS event_trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
  obj record;
BEGIN
  FOR obj IN
    SELECT *
    FROM pg_event_trigger_ddl_commands()
    WHERE command_tag = 'CREATE TABLE'
  LOOP
    IF obj.schema_name = 'public' AND obj.object_type IN ('table', 'partitioned table') THEN
      EXECUTE format('ALTER TABLE %s ENABLE ROW LEVEL SECURITY', obj.object_identity);
    END IF;
  END LOOP;
END;
$$;

DO $$
BEGIN
  EXECUTE 'DROP EVENT TRIGGER IF EXISTS ruana_enable_rls_on_create_table';
  EXECUTE $c$
    CREATE EVENT TRIGGER ruana_enable_rls_on_create_table
      ON ddl_command_end
      WHEN TAG IN ('CREATE TABLE')
      EXECUTE PROCEDURE public.ruana_enable_rls_on_create_table()
  $c$;
EXCEPTION WHEN OTHERS THEN
  RAISE NOTICE 'event trigger RLS skipped: %', SQLERRM;
END
$$;

COMMIT;
