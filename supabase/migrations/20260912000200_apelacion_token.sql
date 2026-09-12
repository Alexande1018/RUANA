-- Token público de apelación (hash, no el valor en claro).
ALTER TABLE public.ruana_soporte_conversaciones
  ADD COLUMN IF NOT EXISTS apelacion_token_hash TEXT;
ALTER TABLE public.ruana_soporte_conversaciones
  ADD COLUMN IF NOT EXISTS token_usado_en TIMESTAMP;

CREATE INDEX IF NOT EXISTS idx_soporte_conv_token
  ON public.ruana_soporte_conversaciones(apelacion_token_hash);
