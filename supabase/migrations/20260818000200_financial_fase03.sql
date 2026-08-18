-- FASE 03: transferencias blindadas (PostgreSQL/Supabase)

CREATE TABLE IF NOT EXISTS financial_transfers (
    id BIGSERIAL PRIMARY KEY,
    contacto_id BIGINT NOT NULL UNIQUE REFERENCES contactos_ruana(id),
    idempotency_key TEXT NOT NULL UNIQUE,
    stripe_transfer_id TEXT UNIQUE,
    amount_cents INTEGER NOT NULL,
    currency TEXT NOT NULL DEFAULT 'eur',
    destination_account_id TEXT NOT NULL,
    professional_codigo TEXT NOT NULL,
    stripe_payment_intent_id TEXT,
    estado TEXT NOT NULL DEFAULT 'RECLAMADA',
    actor_codigo TEXT,
    error_message TEXT,
    creado_en TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    actualizado_en TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_fin_transfers_stripe_id ON financial_transfers(stripe_transfer_id);

CREATE TABLE IF NOT EXISTS financial_transfer_attempts (
    id BIGSERIAL PRIMARY KEY,
    contacto_id BIGINT NOT NULL REFERENCES contactos_ruana(id),
    financial_transfer_id BIGINT REFERENCES financial_transfers(id),
    actor_codigo TEXT,
    resultado TEXT NOT NULL,
    motivo_bloqueo TEXT,
    estado_anterior TEXT,
    estado_nuevo TEXT,
    stripe_transfer_id TEXT,
    metadata JSONB,
    creado_en TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_fin_transfer_attempts_contacto ON financial_transfer_attempts(contacto_id);
