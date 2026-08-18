-- FASE 07: reconciliación financiera avanzada RUANA ↔ Stripe

CREATE TABLE IF NOT EXISTS financial_reconciliation_executions (
    id BIGSERIAL PRIMARY KEY,
    contacto_id BIGINT REFERENCES contactos_ruana(id),
    payment_intent_id TEXT,
    transfer_id TEXT,
    operacion TEXT NOT NULL,
    estado TEXT NOT NULL DEFAULT 'NOT_STARTED',
    reconciler_version TEXT NOT NULL DEFAULT 'fase07-1',
    idempotency_key TEXT UNIQUE,
    actor_codigo TEXT,
    permiso_usado TEXT,
    motivo TEXT,
    metricas_json JSONB,
    error_stripe TEXT,
    creado_en TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    actualizado_en TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    finalizado_en TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_fin_recon_exec_contacto ON financial_reconciliation_executions(contacto_id);
CREATE INDEX IF NOT EXISTS idx_fin_recon_exec_pi ON financial_reconciliation_executions(payment_intent_id);
CREATE INDEX IF NOT EXISTS idx_fin_recon_exec_transfer ON financial_reconciliation_executions(transfer_id);
CREATE INDEX IF NOT EXISTS idx_fin_recon_exec_estado ON financial_reconciliation_executions(estado);
CREATE INDEX IF NOT EXISTS idx_fin_recon_exec_idem ON financial_reconciliation_executions(idempotency_key);

CREATE TABLE IF NOT EXISTS financial_reconciliation_snapshots (
    id BIGSERIAL PRIMARY KEY,
    execution_id BIGINT NOT NULL REFERENCES financial_reconciliation_executions(id),
    contacto_id BIGINT NOT NULL REFERENCES contactos_ruana(id),
    payment_intent_id TEXT,
    charge_id TEXT,
    balance_transaction_id TEXT,
    transfer_id TEXT,
    connected_account_id TEXT,
    moneda TEXT NOT NULL DEFAULT 'eur',
    importe_bruto_cents BIGINT NOT NULL DEFAULT 0,
    importe_cobrado_cents BIGINT NOT NULL DEFAULT 0,
    fee_stripe_cents BIGINT NOT NULL DEFAULT 0,
    neto_ruana_cents BIGINT NOT NULL DEFAULT 0,
    importe_transferido_cents BIGINT NOT NULL DEFAULT 0,
    total_reembolsado_cents BIGINT NOT NULL DEFAULT 0,
    importe_disputado_cents BIGINT NOT NULL DEFAULT 0,
    comision_ruana_cents BIGINT NOT NULL DEFAULT 0,
    obligacion_profesional_cents BIGINT NOT NULL DEFAULT 0,
    estado_ruana TEXT,
    estado_stripe TEXT,
    origen TEXT NOT NULL DEFAULT 'stripe_api',
    reconciler_version TEXT NOT NULL DEFAULT 'fase07-1',
    snapshot_json JSONB NOT NULL,
    creado_en TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_fin_recon_snap_exec ON financial_reconciliation_snapshots(execution_id);
CREATE INDEX IF NOT EXISTS idx_fin_recon_snap_contacto ON financial_reconciliation_snapshots(contacto_id);

CREATE TABLE IF NOT EXISTS financial_reconciliation_resource_results (
    id BIGSERIAL PRIMARY KEY,
    execution_id BIGINT NOT NULL REFERENCES financial_reconciliation_executions(id),
    resource_type TEXT NOT NULL,
    resource_id TEXT,
    fetch_status TEXT NOT NULL,
    error_code TEXT,
    http_status INTEGER,
    metadata_json JSONB,
    creado_en TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_fin_recon_res_exec ON financial_reconciliation_resource_results(execution_id, resource_type);
