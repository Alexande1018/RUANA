-- FASE 05: reembolsos Stripe seguros, idempotentes y auditables

CREATE TABLE IF NOT EXISTS financial_refunds (
    id BIGSERIAL PRIMARY KEY,
    contacto_id BIGINT NOT NULL REFERENCES contactos_ruana(id),
    conflicto_id BIGINT REFERENCES payment_conflicts(id),
    payment_intent_id TEXT,
    charge_id TEXT,
    stripe_refund_id TEXT UNIQUE,
    importe_solicitado_cents BIGINT NOT NULL,
    importe_confirmado_cents BIGINT NOT NULL DEFAULT 0,
    moneda TEXT NOT NULL DEFAULT 'eur',
    estado TEXT NOT NULL DEFAULT 'REQUESTED',
    motivo_stripe TEXT,
    causa_ruana TEXT NOT NULL,
    comision_total_cents BIGINT NOT NULL DEFAULT 0,
    comision_conservada_cents BIGINT NOT NULL DEFAULT 0,
    comision_devuelta_cents BIGINT NOT NULL DEFAULT 0,
    parte_ejecutada_cents BIGINT NOT NULL DEFAULT 0,
    parte_no_ejecutada_cents BIGINT NOT NULL DEFAULT 0,
    actor_codigo TEXT NOT NULL,
    permiso_usado TEXT,
    idempotency_key TEXT NOT NULL UNIQUE,
    error_stripe TEXT,
    metadata_json JSONB,
    creado_en TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    actualizado_en TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CHECK (importe_solicitado_cents > 0),
    CHECK (importe_confirmado_cents >= 0),
    CHECK (comision_total_cents >= 0),
    CHECK (comision_conservada_cents >= 0),
    CHECK (comision_devuelta_cents >= 0),
    CHECK (comision_conservada_cents + comision_devuelta_cents <= comision_total_cents + 1)
);

CREATE INDEX IF NOT EXISTS idx_financial_refunds_contacto ON financial_refunds(contacto_id);
CREATE INDEX IF NOT EXISTS idx_financial_refunds_conflicto ON financial_refunds(conflicto_id);
CREATE INDEX IF NOT EXISTS idx_financial_refunds_estado ON financial_refunds(estado);
CREATE INDEX IF NOT EXISTS idx_financial_refunds_pi ON financial_refunds(payment_intent_id);

CREATE TABLE IF NOT EXISTS financial_refund_attempts (
    id BIGSERIAL PRIMARY KEY,
    refund_id BIGINT NOT NULL REFERENCES financial_refunds(id),
    operacion TEXT NOT NULL,
    actor_codigo TEXT NOT NULL,
    resultado TEXT NOT NULL,
    metadata_json JSONB,
    creado_en TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_financial_refund_attempts_refund ON financial_refund_attempts(refund_id, creado_en DESC);

-- Ampliación incremental de stripe_refunds (auditoría webhook, sin floats nuevos)
ALTER TABLE stripe_refunds ADD COLUMN IF NOT EXISTS financial_refund_id BIGINT REFERENCES financial_refunds(id);
ALTER TABLE stripe_refunds ADD COLUMN IF NOT EXISTS amount_cents BIGINT;
ALTER TABLE stripe_refunds ADD COLUMN IF NOT EXISTS payment_intent_id TEXT;
ALTER TABLE stripe_refunds ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ DEFAULT NOW();

CREATE INDEX IF NOT EXISTS idx_stripe_refunds_financial_refund ON stripe_refunds(financial_refund_id);
