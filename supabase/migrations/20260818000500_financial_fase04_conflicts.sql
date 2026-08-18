-- FASE 04: sistema formal de conflictos financieros

ALTER TABLE payment_conflicts ADD COLUMN IF NOT EXISTS estado_conflicto TEXT;
ALTER TABLE payment_conflicts ADD COLUMN IF NOT EXISTS tipo_conflicto TEXT;
ALTER TABLE payment_conflicts ADD COLUMN IF NOT EXISTS motivo TEXT;
ALTER TABLE payment_conflicts ADD COLUMN IF NOT EXISTS importe_reclamado_cents BIGINT;
ALTER TABLE payment_conflicts ADD COLUMN IF NOT EXISTS moneda TEXT DEFAULT 'eur';
ALTER TABLE payment_conflicts ADD COLUMN IF NOT EXISTS abierto_por TEXT;
ALTER TABLE payment_conflicts ADD COLUMN IF NOT EXISTS responsable_codigo TEXT;
ALTER TABLE payment_conflicts ADD COLUMN IF NOT EXISTS prioridad TEXT DEFAULT 'normal';
ALTER TABLE payment_conflicts ADD COLUMN IF NOT EXISTS fecha_apertura TIMESTAMPTZ;
ALTER TABLE payment_conflicts ADD COLUMN IF NOT EXISTS fecha_asignacion TIMESTAMPTZ;
ALTER TABLE payment_conflicts ADD COLUMN IF NOT EXISTS fecha_resolucion TIMESTAMPTZ;
ALTER TABLE payment_conflicts ADD COLUMN IF NOT EXISTS resolucion TEXT;
ALTER TABLE payment_conflicts ADD COLUMN IF NOT EXISTS importe_liberar_cents BIGINT;
ALTER TABLE payment_conflicts ADD COLUMN IF NOT EXISTS importe_reembolsar_cents BIGINT;
ALTER TABLE payment_conflicts ADD COLUMN IF NOT EXISTS importe_profesional_cents BIGINT;
ALTER TABLE payment_conflicts ADD COLUMN IF NOT EXISTS importe_contratante_cents BIGINT;
ALTER TABLE payment_conflicts ADD COLUMN IF NOT EXISTS bloqueo_financiero INTEGER DEFAULT 1;
ALTER TABLE payment_conflicts ADD COLUMN IF NOT EXISTS version INTEGER DEFAULT 1;
ALTER TABLE payment_conflicts ADD COLUMN IF NOT EXISTS idempotency_key_apertura TEXT;

CREATE UNIQUE INDEX IF NOT EXISTS idx_payment_conflicts_idempotency_apertura
    ON payment_conflicts(idempotency_key_apertura) WHERE idempotency_key_apertura IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_payment_conflicts_estado_conflicto ON payment_conflicts(estado_conflicto);
CREATE INDEX IF NOT EXISTS idx_payment_conflicts_bloqueo ON payment_conflicts(bloqueo_financiero);
CREATE INDEX IF NOT EXISTS idx_payment_conflicts_responsable ON payment_conflicts(responsable_codigo);
CREATE INDEX IF NOT EXISTS idx_payment_conflicts_trabajo_estado ON payment_conflicts(trabajo_id, estado_conflicto);

UPDATE payment_conflicts SET estado_conflicto = 'ABIERTO'
    WHERE estado_conflicto IS NULL AND estado = 'PENDIENTE_PRUEBA';
UPDATE payment_conflicts SET estado_conflicto = 'EN_INVESTIGACION'
    WHERE estado_conflicto IS NULL AND estado = 'EN_REVISION';
UPDATE payment_conflicts SET estado_conflicto = 'CERRADO', bloqueo_financiero = 0
    WHERE estado_conflicto IS NULL AND estado IN ('RESUELTO', 'RECHAZADO');
UPDATE payment_conflicts SET tipo_conflicto = 'IMPORTE_DISPUTADO'
    WHERE tipo_conflicto IS NULL AND tipo = 'importe_discrepante';
UPDATE payment_conflicts SET tipo_conflicto = 'PLAZO_DISPUTADO'
    WHERE tipo_conflicto IS NULL AND tipo = 'sin_confirmacion_trabajo';
UPDATE payment_conflicts SET bloqueo_financiero = 1
    WHERE bloqueo_financiero IS NULL AND estado_conflicto IN (
        'ABIERTO', 'EN_INVESTIGACION', 'PENDIENTE_DE_EVIDENCIA', 'ESCALADO'
    );

CREATE TABLE IF NOT EXISTS payment_conflict_evidence (
    id BIGSERIAL PRIMARY KEY,
    conflicto_id BIGINT NOT NULL REFERENCES payment_conflicts(id),
    tipo TEXT NOT NULL,
    nombre TEXT NOT NULL,
    referencia_segura TEXT NOT NULL,
    hash_sha256 TEXT,
    subido_por TEXT NOT NULL,
    creado_en TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    metadata_json JSONB,
    eliminado_en TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_pce_conflicto ON payment_conflict_evidence(conflicto_id, creado_en);

CREATE TABLE IF NOT EXISTS payment_conflict_comments (
    id BIGSERIAL PRIMARY KEY,
    conflicto_id BIGINT NOT NULL REFERENCES payment_conflicts(id),
    autor_codigo TEXT NOT NULL,
    texto TEXT NOT NULL,
    creado_en TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    visible_para_contratante INTEGER DEFAULT 1,
    visible_para_profesional INTEGER DEFAULT 1
);
CREATE INDEX IF NOT EXISTS idx_pcc_conflicto ON payment_conflict_comments(conflicto_id, creado_en);

CREATE TABLE IF NOT EXISTS payment_conflict_actions (
    id BIGSERIAL PRIMARY KEY,
    conflicto_id BIGINT NOT NULL REFERENCES payment_conflicts(id),
    operacion TEXT NOT NULL,
    idempotency_key TEXT NOT NULL,
    actor_codigo TEXT NOT NULL,
    resultado TEXT NOT NULL DEFAULT 'en_proceso',
    metadata_json JSONB,
    creado_en TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    actualizado_en TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(conflicto_id, operacion, idempotency_key)
);

CREATE TABLE IF NOT EXISTS payment_conflict_audit (
    id BIGSERIAL PRIMARY KEY,
    conflicto_id BIGINT NOT NULL REFERENCES payment_conflicts(id),
    accion TEXT NOT NULL,
    actor_codigo TEXT NOT NULL,
    estado_anterior TEXT,
    estado_nuevo TEXT,
    metadata_json JSONB,
    creado_en TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_pca_conflicto ON payment_conflict_audit(conflicto_id, creado_en DESC);
