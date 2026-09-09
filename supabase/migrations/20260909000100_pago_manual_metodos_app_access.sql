-- El rol de Flask (DATABASE_URL) debe poder persistir Bizum/IBAN.
-- Anon y authenticated siguen sin política: PostgREST deniega.
-- Sin FORCE ROW LEVEL SECURITY.

REVOKE ALL ON TABLE public.ruana_metodos_pago_manual FROM PUBLIC;
REVOKE ALL ON TABLE public.ruana_metodos_pago_manual FROM anon;
REVOKE ALL ON TABLE public.ruana_metodos_pago_manual FROM authenticated;

GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE public.ruana_metodos_pago_manual TO postgres;
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE public.ruana_metodos_pago_manual TO service_role;

DO $$
DECLARE
  seq text;
BEGIN
  seq := pg_get_serial_sequence('public.ruana_metodos_pago_manual', 'id');
  IF seq IS NOT NULL THEN
    EXECUTE format('GRANT USAGE, SELECT ON SEQUENCE %s TO postgres', seq);
    EXECUTE format('GRANT USAGE, SELECT ON SEQUENCE %s TO service_role', seq);
  END IF;
END $$;

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_policies
    WHERE schemaname = 'public'
      AND tablename = 'ruana_metodos_pago_manual'
      AND policyname = 'ruana_metodos_pago_manual_app'
  ) THEN
    CREATE POLICY ruana_metodos_pago_manual_app
      ON public.ruana_metodos_pago_manual
      FOR ALL TO CURRENT_USER
      USING (true)
      WITH CHECK (true);
  END IF;
END $$;
