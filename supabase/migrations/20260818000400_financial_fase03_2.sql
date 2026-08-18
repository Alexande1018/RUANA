-- FASE 03.2: reconciliación explícita transferencias

ALTER TABLE financial_transfers ADD COLUMN IF NOT EXISTS reconciliacion_estado TEXT;
ALTER TABLE financial_transfers ADD COLUMN IF NOT EXISTS stripe_snapshot_json TEXT;
ALTER TABLE financial_transfers ADD COLUMN IF NOT EXISTS efectos_post_transfer_aplicados INTEGER DEFAULT 0;
ALTER TABLE financial_transfers ADD COLUMN IF NOT EXISTS bloqueada INTEGER DEFAULT 0;

CREATE TABLE IF NOT EXISTS financial_transfer_snapshots (
    id BIGSERIAL PRIMARY KEY,
    contacto_id BIGINT NOT NULL REFERENCES contactos_ruana(id),
    stripe_transfer_id TEXT,
    stripe_event_id TEXT,
    event_type TEXT NOT NULL,
    snapshot_json JSONB NOT NULL,
    creado_en TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_fin_transfer_snapshots_contacto ON financial_transfer_snapshots(contacto_id, creado_en DESC);
