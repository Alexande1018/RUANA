-- FASE 13A P0-4: inmutabilidad ledger POSTED (PostgreSQL)

CREATE OR REPLACE FUNCTION ruana_ledger_guard_tx_update()
RETURNS TRIGGER AS $$
BEGIN
  IF OLD.estado = 'POSTED' THEN
    IF NEW.estado = 'VOIDED' AND OLD.estado = 'POSTED' THEN
      RETURN NEW;
    END IF;
    RAISE EXCEPTION 'ledger_transactions POSTED es inmutable (solo POSTED→VOIDED)';
  END IF;
  IF OLD.estado = 'VOIDED' THEN
    RAISE EXCEPTION 'ledger_transactions VOIDED es inmutable';
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_ledger_tx_immutable ON ledger_transactions;
CREATE TRIGGER trg_ledger_tx_immutable
  BEFORE UPDATE ON ledger_transactions
  FOR EACH ROW
  EXECUTE FUNCTION ruana_ledger_guard_tx_update();

CREATE OR REPLACE FUNCTION ruana_ledger_guard_tx_delete()
RETURNS TRIGGER AS $$
BEGIN
  IF OLD.estado IN ('POSTED', 'VOIDED') THEN
    RAISE EXCEPTION 'No se puede eliminar ledger_transactions POSTED/VOIDED';
  END IF;
  RETURN OLD;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_ledger_tx_no_delete ON ledger_transactions;
CREATE TRIGGER trg_ledger_tx_no_delete
  BEFORE DELETE ON ledger_transactions
  FOR EACH ROW
  EXECUTE FUNCTION ruana_ledger_guard_tx_delete();

CREATE OR REPLACE FUNCTION ruana_ledger_guard_entry_mutate()
RETURNS TRIGGER AS $$
DECLARE
  tx_estado TEXT;
  tx_id INTEGER;
BEGIN
  IF TG_OP = 'DELETE' THEN
    tx_id := OLD.ledger_transaction_id;
  ELSE
    tx_id := NEW.ledger_transaction_id;
  END IF;
  SELECT estado INTO tx_estado FROM ledger_transactions WHERE id = tx_id;
  IF tx_estado IN ('POSTED', 'VOIDED') THEN
    RAISE EXCEPTION 'ledger_entries de transacciones POSTED/VOIDED son inmutables';
  END IF;
  IF TG_OP = 'DELETE' THEN
    RETURN OLD;
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_ledger_entry_no_update ON ledger_entries;
CREATE TRIGGER trg_ledger_entry_no_update
  BEFORE UPDATE ON ledger_entries
  FOR EACH ROW
  EXECUTE FUNCTION ruana_ledger_guard_entry_mutate();

DROP TRIGGER IF EXISTS trg_ledger_entry_no_delete ON ledger_entries;
CREATE TRIGGER trg_ledger_entry_no_delete
  BEFORE DELETE ON ledger_entries
  FOR EACH ROW
  EXECUTE FUNCTION ruana_ledger_guard_entry_mutate();
