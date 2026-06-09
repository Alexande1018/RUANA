# Metodos Pago Storage Supabase Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move RUANA payment-related files away from local disk into Supabase Storage, cap uploads at 2 MB, and let admins edit Bizum, Revolut QR, and IBAN payment methods.

**Architecture:** Add a small backend storage adapter that uploads files to Supabase Storage and returns stable public URLs/paths for existing database fields. Keep payment method values in the existing `ruana_reglas_v1.json` configuration, surfaced through API endpoints for aliado and admin panels. Update the aliado payment modal to use Bizum, Revolut QR, and Transferencia tabs.

**Tech Stack:** Flask, Supabase Python client, existing JSON config, static HTML/JS contract tests, pytest.

---

### Task 1: Storage Adapter

**Files:**
- Create: `RUANA/RUANA/core/storage_manager.py`
- Test: `RUANA/RUANA/tests/test_storage_manager.py`

- [ ] Write tests for 2 MB upload limit and Supabase upload path.
- [ ] Implement `upload_ruana_file`.
- [ ] Run targeted storage tests.

### Task 2: Upload Endpoints

**Files:**
- Modify: `RUANA/RUANA/web/app.py`
- Test: `RUANA/RUANA/tests/test_storage_uploads.py`

- [ ] Test Apoyo RUANA comprobantes call the storage adapter and never save to `static/uploads`.
- [ ] Test conflict proofs use the same adapter.
- [ ] Replace local `file.save(...)` upload handling with `upload_ruana_file`.

### Task 3: Payment Methods API

**Files:**
- Modify: `RUANA/RUANA/core/db_manager.py`
- Modify: `RUANA/RUANA/web/app.py`
- Test: `RUANA/RUANA/tests/test_payment_methods_api.py`

- [ ] Add getters and updaters for `bizum_num`, `iban`, and `qr_revolut_path`.
- [ ] Add allied read endpoint and admin read/update/upload endpoints.
- [ ] Store uploaded QR files through Supabase Storage.

### Task 4: Frontend Contract

**Files:**
- Modify: `RUANA/RUANA/web/aliado.html`
- Modify: `RUANA/RUANA/web/admin.html`
- Test: `RUANA/RUANA/tests/test_aliado_payment_frontend_contract.py`
- Test: `RUANA/RUANA/tests/test_admin_frontend_contract.py`

- [ ] Update aliado modal tabs: Bizum, QR Revolut, Transferencia.
- [ ] Load payment method configuration from the backend.
- [ ] Add admin section/action to edit payment methods and upload QR.

### Task 5: Verification

**Files:**
- Verify changed tests and inline JS parsing.

- [ ] Run targeted pytest suite.
- [ ] Parse inline scripts with Node.
- [ ] Inspect final changed file list.
