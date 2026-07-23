-- Días con login de aliado (Regla 8: racha de 7 días consecutivos).
CREATE TABLE IF NOT EXISTS aliado_accesos_dia (
    codigo_aliado TEXT NOT NULL REFERENCES aliados(codigo),
    dia TEXT NOT NULL,
    creado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (codigo_aliado, dia)
);

CREATE INDEX IF NOT EXISTS idx_aliado_accesos_dia_codigo ON aliado_accesos_dia(codigo_aliado);
CREATE INDEX IF NOT EXISTS idx_aliado_accesos_dia_dia ON aliado_accesos_dia(dia);
