-- Pago manual RUANA: datos de cobro (fila lógica única) + allowlist por aliado.

CREATE TABLE IF NOT EXISTS ruana_metodos_pago_manual (
    id BIGSERIAL PRIMARY KEY,
    bizum_num TEXT,
    iban TEXT,
    qr_revolut_path TEXT,
    actualizado_por TEXT,
    actualizado_en TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS ruana_pago_manual_aliados_habilitados (
    id BIGSERIAL PRIMARY KEY,
    aliado_codigo TEXT NOT NULL UNIQUE,
    habilitado_por TEXT,
    habilitado_en TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_pago_manual_aliados_codigo
    ON ruana_pago_manual_aliados_habilitados(aliado_codigo);

ALTER TABLE ruana_metodos_pago_manual ENABLE ROW LEVEL SECURITY;
ALTER TABLE ruana_pago_manual_aliados_habilitados ENABLE ROW LEVEL SECURITY;
