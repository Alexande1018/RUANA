-- Encargos externos («Encargo de RUANA»): clientes de anuncios externos que el
-- admin asigna a un aliado. Flujo aparte: sin Stripe, sin comisión (gancho
-- comision_activada/comision_pct preparado y apagado) y sin puntos de reputación.
-- Flask también crea la tabla al primer uso (encargo_externo_service).

CREATE TABLE IF NOT EXISTS encargos_externos (
    id BIGSERIAL PRIMARY KEY,
    aliado_codigo TEXT NOT NULL,
    cliente_nombre TEXT NOT NULL,
    cliente_telefono TEXT,
    cliente_email TEXT,
    codigo_postal TEXT NOT NULL,
    descripcion TEXT NOT NULL,
    origen_anuncio TEXT DEFAULT '',
    precio_orientativo NUMERIC(10,2),
    estado TEXT NOT NULL DEFAULT 'creado',
    motivo_rechazo TEXT,
    comision_activada INTEGER NOT NULL DEFAULT 0,
    comision_pct NUMERIC(5,2) NOT NULL DEFAULT 5.0,
    creado_por TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    aceptado_at TIMESTAMPTZ,
    rechazado_at TIMESTAMPTZ,
    hecho_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_encargos_externos_aliado
    ON encargos_externos(aliado_codigo, estado);

CREATE INDEX IF NOT EXISTS idx_encargos_externos_estado
    ON encargos_externos(estado, created_at);

-- Sin FORCE: Flask (dueño) no se ve afectado; anon sin políticas = denegado.
ALTER TABLE encargos_externos ENABLE ROW LEVEL SECURITY;
