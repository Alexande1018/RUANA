-- FASE 03.1: referencias Stripe Connect en transferencias blindadas

ALTER TABLE financial_transfers ADD COLUMN IF NOT EXISTS stripe_balance_transaction_id TEXT;
ALTER TABLE financial_transfers ADD COLUMN IF NOT EXISTS stripe_destination_payment_id TEXT;
