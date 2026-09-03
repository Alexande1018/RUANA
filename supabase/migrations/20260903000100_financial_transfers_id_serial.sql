-- Encargo #72 / liberar pago: tablas creadas por migraciones SQLite-compat pueden
-- tener id INTEGER PRIMARY KEY sin DEFAULT nextval. Reparación idempotente.

DO $$
DECLARE
    tbl text;
BEGIN
    FOREACH tbl IN ARRAY ARRAY[
        'payment_conflicts',
        'financial_transfers',
        'financial_transfer_attempts',
        'financial_transfer_snapshots',
        'financial_refunds',
        'financial_refund_attempts',
        'financial_disputes',
        'financial_dispute_evidence',
        'financial_dispute_attempts',
        'financial_reconciliation',
        'financial_reconciliation_executions',
        'financial_reconciliation_snapshots',
        'financial_reconciliation_resource_results',
        'ledger_transactions',
        'ledger_entries',
        'ledger_event_links',
        'financial_idempotency_keys',
        'financial_admin_alert_actions',
        'financial_action_approvals',
        'financial_audit_log',
        'financial_job_leases',
        'financial_automation_runs',
        'financial_alerts',
        'stripe_webhook_events'
    ]
    LOOP
        IF to_regclass('public.' || tbl) IS NULL THEN
            CONTINUE;
        END IF;
        IF EXISTS (
            SELECT 1
            FROM information_schema.columns
            WHERE table_schema = 'public'
              AND table_name = tbl
              AND column_name = 'id'
              AND (column_default IS NULL OR column_default NOT LIKE 'nextval%')
        ) THEN
            EXECUTE format('CREATE SEQUENCE IF NOT EXISTS %I', tbl || '_id_seq');
            EXECUTE format(
                'SELECT setval(%L, COALESCE((SELECT MAX(id) FROM %I), 0) + 1, false)',
                tbl || '_id_seq',
                tbl
            );
            EXECUTE format(
                'ALTER TABLE %I ALTER COLUMN id SET DEFAULT nextval(%L)',
                tbl,
                tbl || '_id_seq'
            );
            EXECUTE format(
                'ALTER SEQUENCE %I OWNED BY %I.id',
                tbl || '_id_seq',
                tbl
            );
        END IF;
    END LOOP;
END $$;
