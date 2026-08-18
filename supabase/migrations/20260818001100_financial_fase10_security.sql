-- FASE 10: seguridad financiera — aprobaciones y auditoría unificada

CREATE TABLE IF NOT EXISTS financial_action_approvals (
    id BIGSERIAL PRIMARY KEY,
    action_id TEXT NOT NULL,
    action_type TEXT NOT NULL,
    contacto_id BIGINT REFERENCES contactos_ruana(id),
    actor_solicitante TEXT NOT NULL,
    actor_autorizador TEXT,
    importe_cents BIGINT NOT NULL DEFAULT 0,
    currency TEXT NOT NULL DEFAULT 'eur',
    motivo TEXT NOT NULL,
    estado TEXT NOT NULL DEFAULT 'REQUESTED',
    version INTEGER NOT NULL DEFAULT 1,
    idempotency_key TEXT NOT NULL,
    expires_at TIMESTAMPTZ,
    metadata_json JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    approved_at TIMESTAMPTZ,
    executed_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (action_id, estado)
);

CREATE INDEX IF NOT EXISTS idx_fin_approval_estado ON financial_action_approvals(estado);
CREATE INDEX IF NOT EXISTS idx_fin_approval_contacto ON financial_action_approvals(contacto_id);
CREATE INDEX IF NOT EXISTS idx_fin_approval_idem ON financial_action_approvals(idempotency_key);

CREATE TABLE IF NOT EXISTS financial_audit_log (
    id BIGSERIAL PRIMARY KEY,
    request_id TEXT NOT NULL,
    actor_codigo TEXT NOT NULL,
    permiso_usado TEXT,
    rol_capacidad TEXT,
    accion TEXT NOT NULL,
    recurso_tipo TEXT NOT NULL,
    recurso_id TEXT NOT NULL,
    importe_cents BIGINT,
    moneda TEXT DEFAULT 'eur',
    version_recursos INTEGER,
    idempotency_key TEXT,
    motivo TEXT,
    resultado TEXT NOT NULL DEFAULT 'success',
    error_sanitizado TEXT,
    metadata_json JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_fin_audit_actor ON financial_audit_log(actor_codigo);
CREATE INDEX IF NOT EXISTS idx_fin_audit_recurso ON financial_audit_log(recurso_tipo, recurso_id);
CREATE INDEX IF NOT EXISTS idx_fin_audit_created ON financial_audit_log(created_at DESC);
