-- Plaza por oficio principal: eliminar especializaciones y renombrar columnas de competencia a retador.

-- 1. Añadir estado en_espera a aliados (ya permitido como texto libre; documentado aquí)
--    y eliminar columnas de especializacion que ya no se usan.

ALTER TABLE public.aliados
  DROP COLUMN IF EXISTS especializacion,
  DROP COLUMN IF EXISTS especializaciones;

-- 2. Renombrar columnas de competencia: suplente → retador
ALTER TABLE public.competencia
  RENAME COLUMN suplente_codigo TO retador_codigo;

ALTER TABLE public.competencia
  RENAME COLUMN suplente_grupo_anterior_id TO retador_grupo_anterior_id;

ALTER TABLE public.competencia
  RENAME COLUMN score_suplente_inicio TO score_retador_inicio;

ALTER TABLE public.competencia
  RENAME COLUMN score_suplente_actual TO score_retador_actual;

-- 3. Migración de datos: resolver conflictos de oficio dentro de un grupo.
--    Si hay varios aliados activos con el mismo oficio_principal en el mismo grupo,
--    conservar el de mayor score (o más antiguo en empate) y poner los demás en en_espera.
WITH ranked AS (
  SELECT
    id,
    grupo_id,
    oficio_principal,
    score,
    creado_en,
    ROW_NUMBER() OVER (
      PARTITION BY grupo_id, oficio_principal
      ORDER BY score DESC NULLS LAST, creado_en ASC NULLS LAST
    ) AS rn
  FROM public.aliados
  WHERE estado = 'activo'
    AND grupo_id IS NOT NULL
    AND oficio_principal IS NOT NULL
)
UPDATE public.aliados
SET estado = 'en_espera',
    grupo_id = NULL
WHERE id IN (
  SELECT id FROM ranked WHERE rn > 1
);
