-- FASE 06: disputas Stripe formales

CREATE TABLE IF NOT EXISTS financial_disputes (
    id BIGSERIAL PRIMARY KEY,
    contacto_id BIGINT NOT NULL REFERENCES contactos_ruana(id),
    stripe_dispute_id TEXT NOT NULL UNIQUE,
    charge_id TEXT,
    payment_intent_id TEXT,
    amount_cents BIGINT NOT NULL,
    currency TEXT NOT NULL DEFAULT 'eur',
    reason TEXT,
    status_stripe TEXT,
    estado_interno TEXT NOT NULL DEFAULT 'ABIERTO',
    evidence_due_by TIMESTAMPTZ,
    has_evidence BOOLEAN NOT NULL DEFAULT FALSE,
    evidence_submitted BOOLEAN NOT NULL DEFAULT FALSE,
    network_reason_code TEXT,
    balance_transaction_id TEXT,
    funds_withdrawn_cents BIGINT NOT NULL DEFAULT 0,
    funds_reinstated_cents BIGINT NOT NULL DEFAULT 0,
    resolution TEXT,
    resolution_reason TEXT,
    responsable_codigo TEXT,
    conflicto_id BIGINT REFERENCES payment_conflicts(id),
    idempotency_key TEXT UNIQUE,
    bloqueo_financiero BOOLEAN NOT NULL DEFAULT TRUE,
    estado_financiero_historico TEXT,
    metadata_json JSONB,
    creado_en TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    actualizado_en TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    cerrado_en TIMESTAMPTZ,
    CHECK (amount_cents >= 0),
    CHECK (funds_withdrawn_cents >= 0),
    CHECK (funds_reinstated_cents >= 0)
);

CREATE INDEX IF NOT EXISTS idx_financial_disputes_contacto ON financial_disputes(contacto_id);
CREATE INDEX IF NOT EXISTS idx_financial_disputes_stripe_id ON financial_disputes(stripe_dispute_id);
CREATE INDEX IF NOT EXISTS idx_financial_disputes_charge ON financial_disputes(charge_id);
CREATE INDEX IF NOT EXISTS idx_financial_disputes_pi ON financial_disputes(payment_intent_id);
CREATE INDEX IF NOT EXISTS idx_financial_disputes_estado ON financial_disputes(estado_interno);
CREATE INDEX IF NOT EXISTS idx_financial_disputes_due ON financial_disputes(evidence_due_by);
CREATE INDEX IF NOT EXISTS idx_financial_disputes_responsable ON financial_disputes(responsable_codigo);

CREATE TABLE IF NOT EXISTS financial_dispute_evidence (
    id BIGSERIAL PRIMARY KEY,
    dispute_id BIGINT NOT NULL REFERENCES financial_disputes(id),
    tipo TEXT NOT NULL,
    referencia TEXT,
    content_hash TEXT,
    autor_codigo TEXT NOT NULL,
    estado TEXT NOT NULL DEFAULT 'BORRADOR',
    enviada_a_stripe BOOLEAN NOT NULL DEFAULT FALSE,
    fecha_envio TIMESTAMPTZ,
    metadata_json JSONB,
    creado_en TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_financial_dispute_evidence_dispute ON financial_dispute_evidence(dispute_id, creado_en DESC);

CREATE TABLE IF NOT EXISTS financial_dispute_attempts (
    id BIGSERIAL PRIMARY KEY,
    dispute_id BIGINT NOT NULL REFERENCES financial_disputes(id),
    operacion TEXT NOT NULL,
    actor_codigo TEXT NOT NULL,
    permiso_usado TEXT,
    resultado TEXT NOT NULL,
    metadata_json JSONB,
    creado_en TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_financial_dispute_attempts_dispute ON financial_dispute_attempts(dispute_id, creado_en DESC);

ALTER TABLE stripe_disputes ADD COLUMN IF NOT EXISTS financial_dispute_id BIGINT REFERENCES financial_disputes(id);
ALTER TABLE stripe_disputes ADD COLUMN IF NOT EXISTS amount_cents BIGINT;
ALTER TABLE stripe_disputes ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ DEFAULT NOW();

CREATE INDEX IF NOT EXISTS idx_stripe_disputes_financial_dispute ON stripe_disputes(financial_dispute_id);
