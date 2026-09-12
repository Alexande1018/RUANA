-- Art. 22 RGPD: apelación de expulsión automática (tipo, plazo y decisión).
ALTER TABLE public.ruana_soporte_conversaciones
  ADD COLUMN IF NOT EXISTS tipo TEXT DEFAULT 'consulta';
ALTER TABLE public.ruana_soporte_conversaciones
  ADD COLUMN IF NOT EXISTS fecha_limite_apelacion TIMESTAMP;
ALTER TABLE public.ruana_soporte_conversaciones
  ADD COLUMN IF NOT EXISTS apelacion_metadata TEXT;
ALTER TABLE public.ruana_soporte_conversaciones
  ADD COLUMN IF NOT EXISTS decision_apelacion TEXT;
ALTER TABLE public.ruana_soporte_conversaciones
  ADD COLUMN IF NOT EXISTS decision_admin_codigo TEXT;
ALTER TABLE public.ruana_soporte_conversaciones
  ADD COLUMN IF NOT EXISTS decision_motivo TEXT;

CREATE INDEX IF NOT EXISTS idx_soporte_conv_tipo
  ON public.ruana_soporte_conversaciones(tipo);
CREATE INDEX IF NOT EXISTS idx_soporte_conv_limite
  ON public.ruana_soporte_conversaciones(fecha_limite_apelacion);
