-- FASE 08: ledger financiero interno (doble partida, append-only)

CREATE TABLE IF NOT EXISTS ledger_transactions (
    id BIGSERIAL PRIMARY KEY,
    transaction_key TEXT NOT NULL UNIQUE,
    contacto_id BIGINT REFERENCES contactos_ruana(id),
    tipo TEXT NOT NULL,
    moneda TEXT NOT NULL DEFAULT 'eur',
    estado TEXT NOT NULL DEFAULT 'DRAFT',
    actor_origen TEXT,
    evento_origen TEXT,
    referencia_stripe TEXT,
    idempotency_key TEXT NOT NULL UNIQUE,
    reversa_de_id BIGINT REFERENCES ledger_transactions(id),
    fecha_efectiva TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    fecha_publicacion TIMESTAMPTZ,
    metadata_json JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_ledger_tx_contacto ON ledger_transactions(contacto_id);
CREATE INDEX IF NOT EXISTS idx_ledger_tx_tipo ON ledger_transactions(tipo);
CREATE INDEX IF NOT EXISTS idx_ledger_tx_estado ON ledger_transactions(estado);
CREATE INDEX IF NOT EXISTS idx_ledger_tx_idem ON ledger_transactions(idempotency_key);

CREATE TABLE IF NOT EXISTS ledger_entries (
    id BIGSERIAL PRIMARY KEY,
    ledger_transaction_id BIGINT NOT NULL REFERENCES ledger_transactions(id),
    account_code TEXT NOT NULL,
    debit_cents BIGINT NOT NULL DEFAULT 0 CHECK (debit_cents >= 0),
    credit_cents BIGINT NOT NULL DEFAULT 0 CHECK (credit_cents >= 0),
    currency TEXT NOT NULL DEFAULT 'eur',
    descripcion TEXT,
    referencia TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CHECK (NOT (debit_cents > 0 AND credit_cents > 0)),
    CHECK (debit_cents + credit_cents > 0)
);

CREATE INDEX IF NOT EXISTS idx_ledger_entries_tx ON ledger_entries(ledger_transaction_id);
CREATE INDEX IF NOT EXISTS idx_ledger_entries_account ON ledger_entries(account_code);

CREATE TABLE IF NOT EXISTS ledger_event_links (
    id BIGSERIAL PRIMARY KEY,
    ledger_transaction_id BIGINT NOT NULL REFERENCES ledger_transactions(id),
    resource_type TEXT NOT NULL,
    resource_id TEXT NOT NULL,
    metadata_json JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (ledger_transaction_id, resource_type, resource_id)
);

CREATE INDEX IF NOT EXISTS idx_ledger_links_resource ON ledger_event_links(resource_type, resource_id);

CREATE TABLE IF NOT EXISTS ledger_account_balances (
    account_code TEXT NOT NULL,
    contacto_id BIGINT NOT NULL DEFAULT 0,
    currency TEXT NOT NULL DEFAULT 'eur',
    debit_total_cents BIGINT NOT NULL DEFAULT 0,
    credit_total_cents BIGINT NOT NULL DEFAULT 0,
    saldo_neto_cents BIGINT NOT NULL DEFAULT 0,
    actualizado_en TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (account_code, contacto_id, currency)
);
