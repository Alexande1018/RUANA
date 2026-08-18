-- FASE 02: estado financiero, webhooks, reconciliación (PostgreSQL/Supabase)

ALTER TABLE contactos_ruana ADD COLUMN IF NOT EXISTS estado_financiero TEXT;
ALTER TABLE contactos_ruana ADD COLUMN IF NOT EXISTS estado_transferencia TEXT DEFAULT 'NO_APLICA';
ALTER TABLE contactos_ruana ADD COLUMN IF NOT EXISTS stripe_charge_id TEXT;
ALTER TABLE contactos_ruana ADD COLUMN IF NOT EXISTS stripe_refund_id TEXT;
ALTER TABLE contactos_ruana ADD COLUMN IF NOT EXISTS stripe_refund_amount NUMERIC(12,2) DEFAULT 0;
ALTER TABLE contactos_ruana ADD COLUMN IF NOT EXISTS stripe_dispute_id TEXT;
ALTER TABLE contactos_ruana ADD COLUMN IF NOT EXISTS stripe_dispute_amount NUMERIC(12,2);
ALTER TABLE contactos_ruana ADD COLUMN IF NOT EXISTS stripe_dispute_reason TEXT;
ALTER TABLE contactos_ruana ADD COLUMN IF NOT EXISTS stripe_dispute_status TEXT;
ALTER TABLE contactos_ruana ADD COLUMN IF NOT EXISTS stripe_dispute_evidence_due TIMESTAMPTZ;
ALTER TABLE contactos_ruana ADD COLUMN IF NOT EXISTS reembolsos_acumulados NUMERIC(12,2) DEFAULT 0;

CREATE TABLE IF NOT EXISTS financial_idempotency_keys (
    id BIGSERIAL PRIMARY KEY,
    clave TEXT NOT NULL UNIQUE,
    contacto_id BIGINT NOT NULL REFERENCES contactos_ruana(id),
    operacion TEXT NOT NULL,
    creado_en TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_financial_idempotency_contacto ON financial_idempotency_keys(contacto_id);

ALTER TABLE stripe_webhook_events ADD COLUMN IF NOT EXISTS object_id TEXT;
ALTER TABLE stripe_webhook_events ADD COLUMN IF NOT EXISTS estado_anterior TEXT;
ALTER TABLE stripe_webhook_events ADD COLUMN IF NOT EXISTS estado_nuevo TEXT;
ALTER TABLE stripe_webhook_events ADD COLUMN IF NOT EXISTS error_message TEXT;
ALTER TABLE stripe_webhook_events ADD COLUMN IF NOT EXISTS estado_procesamiento TEXT DEFAULT 'completed';

CREATE TABLE IF NOT EXISTS stripe_refunds (
    id BIGSERIAL PRIMARY KEY,
    contacto_id BIGINT NOT NULL REFERENCES contactos_ruana(id),
    stripe_refund_id TEXT NOT NULL UNIQUE,
    stripe_charge_id TEXT,
    amount NUMERIC(12,2) NOT NULL,
    currency TEXT DEFAULT 'eur',
    stripe_event_id TEXT,
    es_total BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_stripe_refunds_contacto ON stripe_refunds(contacto_id);

CREATE TABLE IF NOT EXISTS stripe_disputes (
    id BIGSERIAL PRIMARY KEY,
    contacto_id BIGINT NOT NULL REFERENCES contactos_ruana(id),
    stripe_dispute_id TEXT NOT NULL UNIQUE,
    stripe_charge_id TEXT,
    amount NUMERIC(12,2),
    currency TEXT DEFAULT 'eur',
    reason TEXT,
    status TEXT,
    evidence_due_by TIMESTAMPTZ,
    stripe_event_id TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_stripe_disputes_contacto ON stripe_disputes(contacto_id);

CREATE TABLE IF NOT EXISTS financial_reconciliation (
    id BIGSERIAL PRIMARY KEY,
    contacto_id BIGINT NOT NULL REFERENCES contactos_ruana(id),
    stripe_payment_intent_id TEXT,
    stripe_transfer_id TEXT,
    ruana_estado TEXT,
    stripe_estado TEXT,
    tipo_discrepancia TEXT NOT NULL,
    importe_ruana NUMERIC(12,2),
    importe_stripe NUMERIC(12,2),
    estado_reconciliacion TEXT DEFAULT 'open',
    detected_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    resolved_at TIMESTAMPTZ,
    resolution TEXT,
    metadata JSONB
);
CREATE INDEX IF NOT EXISTS idx_fin_recon_contacto ON financial_reconciliation(contacto_id);
CREATE INDEX IF NOT EXISTS idx_fin_recon_abierta ON financial_reconciliation(contacto_id, tipo_discrepancia, estado_reconciliacion);
