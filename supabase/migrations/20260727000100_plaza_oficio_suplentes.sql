-- Plaza por oficio principal: eliminar especializaciones y renombrar columnas de competencia a retador.

-- 1. Eliminar columnas de especializacion que ya no se usan.
ALTER TABLE public.aliados
  DROP COLUMN IF EXISTS especializacion,
  DROP COLUMN IF EXISTS especializaciones;

-- 2. Renombrar columnas de competencia: suplente → retador
DO $$
BEGIN
  IF EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_schema = 'public' AND table_name = 'competencia' AND column_name = 'suplente_codigo'
  ) THEN
    ALTER TABLE public.competencia RENAME COLUMN suplente_codigo TO retador_codigo;
  END IF;
  IF EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_schema = 'public' AND table_name = 'competencia' AND column_name = 'suplente_grupo_anterior_id'
  ) THEN
    ALTER TABLE public.competencia RENAME COLUMN suplente_grupo_anterior_id TO retador_grupo_anterior_id;
  END IF;
  IF EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_schema = 'public' AND table_name = 'competencia' AND column_name = 'score_suplente_inicio'
  ) THEN
    ALTER TABLE public.competencia RENAME COLUMN score_suplente_inicio TO score_retador_inicio;
  END IF;
  IF EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_schema = 'public' AND table_name = 'competencia' AND column_name = 'score_suplente_actual'
  ) THEN
    ALTER TABLE public.competencia RENAME COLUMN score_suplente_actual TO score_retador_actual;
  END IF;
END $$;

-- 3. Migración de datos: resolver conflictos de oficio dentro de un grupo.
--    Conservar el de mayor score (o más antiguo en empate); el resto → en_espera.
WITH ranked AS (
  SELECT
    id,
    grupo_id,
    oficio,
    score,
    creado_en,
    ROW_NUMBER() OVER (
      PARTITION BY grupo_id, oficio
      ORDER BY score DESC NULLS LAST, creado_en ASC NULLS LAST
    ) AS rn
  FROM public.aliados
  WHERE estado = 'activo'
    AND grupo_id IS NOT NULL
    AND oficio IS NOT NULL
    AND oficio <> ''
)
UPDATE public.aliados
SET estado = 'en_espera',
    grupo_id = NULL
WHERE id IN (
  SELECT id FROM ranked WHERE rn > 1
);
