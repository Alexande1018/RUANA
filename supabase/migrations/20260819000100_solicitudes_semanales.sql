-- Solicitudes para esta semana (aislado de solicitudes de grupo)

CREATE TABLE IF NOT EXISTS solicitudes_semanales (
    id BIGSERIAL PRIMARY KEY,
    grupo_id BIGINT NOT NULL REFERENCES grupos(id),
    solicitante_codigo TEXT NOT NULL,
    solicitante_nombre TEXT NOT NULL,
    oficio TEXT NOT NULL,
    descripcion TEXT DEFAULT '',
    es_oficio_personalizado INTEGER NOT NULL DEFAULT 0,
    semana_inicio DATE NOT NULL,
    estado TEXT NOT NULL DEFAULT 'activa',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    expira_at DATE
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_sol_sem_solicitante_semana
    ON solicitudes_semanales(solicitante_codigo, semana_inicio);

CREATE INDEX IF NOT EXISTS idx_sol_sem_grupo_semana
    ON solicitudes_semanales(grupo_id, semana_inicio, estado);

CREATE TABLE IF NOT EXISTS solicitudes_semanales_respuestas (
    id BIGSERIAL PRIMARY KEY,
    solicitud_semanal_id BIGINT NOT NULL REFERENCES solicitudes_semanales(id),
    aliado_codigo TEXT NOT NULL,
    aliado_nombre TEXT NOT NULL,
    tipo_respuesta TEXT NOT NULL,
    contacto_id BIGINT,
    invitacion_codigo TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(solicitud_semanal_id, aliado_codigo)
);

CREATE INDEX IF NOT EXISTS idx_sol_sem_resp_solicitud
    ON solicitudes_semanales_respuestas(solicitud_semanal_id);

ALTER TABLE solicitudes_semanales ENABLE ROW LEVEL SECURITY;
ALTER TABLE solicitudes_semanales_respuestas ENABLE ROW LEVEL SECURITY;
