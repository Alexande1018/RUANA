-- Flag de encargo urgente (Regla 6 score): solo al iniciar chat por el solicitante.
ALTER TABLE contactos_ruana
    ADD COLUMN IF NOT EXISTS es_urgente INTEGER DEFAULT 0;

ALTER TABLE contactos_ruana
    ADD COLUMN IF NOT EXISTS urgente_marcado_en TIMESTAMP;
