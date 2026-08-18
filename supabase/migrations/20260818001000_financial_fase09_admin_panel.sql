-- FASE 09: panel administrativo financiero — resoluciones de alertas

CREATE TABLE IF NOT EXISTS financial_admin_alert_actions (
    id BIGSERIAL PRIMARY KEY,
    alert_key TEXT NOT NULL,
    contacto_id BIGINT REFERENCES contactos_ruana(id),
    accion TEXT NOT NULL DEFAULT 'resolved',
    motivo TEXT NOT NULL,
    actor_codigo TEXT NOT NULL,
    permiso_usado TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (alert_key, accion)
);

CREATE INDEX IF NOT EXISTS idx_fin_admin_alert_key ON financial_admin_alert_actions(alert_key);
CREATE INDEX IF NOT EXISTS idx_fin_admin_alert_contacto ON financial_admin_alert_actions(contacto_id);

CREATE INDEX IF NOT EXISTS idx_contactos_stripe_estado ON contactos_ruana(modo_pago, estado_financiero);
