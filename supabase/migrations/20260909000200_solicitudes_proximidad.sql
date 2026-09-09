-- Enrutado de Nueva conexión: destino local, recomendación cercana o buscando ayuda.
ALTER TABLE public.solicitudes ADD COLUMN IF NOT EXISTS destino TEXT;
ALTER TABLE public.solicitudes ADD COLUMN IF NOT EXISTS proximidad_codigo TEXT;
ALTER TABLE public.solicitudes ADD COLUMN IF NOT EXISTS proximidad_nombre TEXT;
ALTER TABLE public.solicitudes ADD COLUMN IF NOT EXISTS proximidad_cp TEXT;
ALTER TABLE public.solicitudes ADD COLUMN IF NOT EXISTS proximidad_zona TEXT;
ALTER TABLE public.solicitudes ADD COLUMN IF NOT EXISTS proximidad_estado TEXT;
