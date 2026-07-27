-- Elimina aliados placeholder del control de aliados.
-- Conserva filas en invitaciones (el código sigue siendo válido para registro).

WITH placeholders AS (
  SELECT codigo
  FROM public.aliados
  WHERE LOWER(TRIM(COALESCE(estado, ''))) = 'pendiente_completar'
)
DELETE FROM public.referidos
WHERE codigo_referido IN (SELECT codigo FROM placeholders)
   OR codigo_invitador IN (SELECT codigo FROM placeholders);

WITH placeholders AS (
  SELECT codigo
  FROM public.aliados
  WHERE LOWER(TRIM(COALESCE(estado, ''))) = 'pendiente_completar'
)
UPDATE public.aliados
SET invitado_por_codigo = NULL,
    invitado_origen = ''
WHERE invitado_por_codigo IN (SELECT codigo FROM placeholders);

DELETE FROM public.aliados
WHERE LOWER(TRIM(COALESCE(estado, ''))) = 'pendiente_completar';
