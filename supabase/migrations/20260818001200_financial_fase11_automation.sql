-- FASE 11: automatización y monitorización financiera (leases, ejecuciones, alertas persistidas)

CREATE TABLE IF NOT EXISTS financial_job_leases (
    job_name TEXT PRIMARY KEY,
    holder TEXT NOT NULL,
    acquired_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at TIMESTAMPTZ NOT NULL,
    metadata_json TEXT
);

CREATE TABLE IF NOT EXISTS financial_automation_runs (
    id BIGSERIAL PRIMARY KEY,
    run_id TEXT NOT NULL UNIQUE,
    job_name TEXT NOT NULL,
    estado TEXT NOT NULL DEFAULT 'RUNNING',
    actor TEXT NOT NULL,
    iniciado_en TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    finalizado_en TIMESTAMPTZ,
    metricas_json TEXT,
    errores_json TEXT,
    alertas_nuevas INTEGER NOT NULL DEFAULT 0,
    alertas_actualizadas INTEGER NOT NULL DEFAULT 0,
    detalle_json TEXT
);

CREATE INDEX IF NOT EXISTS idx_fin_auto_runs_job ON financial_automation_runs(job_name, iniciado_en DESC);
CREATE INDEX IF NOT EXISTS idx_fin_auto_runs_estado ON financial_automation_runs(estado);

CREATE TABLE IF NOT EXISTS financial_alerts (
    id BIGSERIAL PRIMARY KEY,
    alert_key TEXT NOT NULL UNIQUE,
    tipo TEXT NOT NULL,
    severidad TEXT NOT NULL,
    contacto_id BIGINT,
    estado TEXT NOT NULL DEFAULT 'OPEN',
    fecha_primera_deteccion TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    fecha_ultima_deteccion TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    antiguedad_horas INTEGER,
    accion_recomendada TEXT,
    accion_disponible TEXT,
    fuente TEXT,
    metadata_json TEXT,
    run_id_primera TEXT,
    run_id_ultima TEXT,
    resuelto_en TIMESTAMPTZ,
    resuelto_por TEXT
);

CREATE INDEX IF NOT EXISTS idx_fin_alerts_estado ON financial_alerts(estado, severidad);
CREATE INDEX IF NOT EXISTS idx_fin_alerts_tipo ON financial_alerts(tipo);
CREATE INDEX IF NOT EXISTS idx_fin_alerts_contacto ON financial_alerts(contacto_id);
