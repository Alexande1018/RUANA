# Impugnacion Cobros Alertas Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix the Apoyo RUANA dispute and payment confirmation flow so alerts, payment blocks, and admin decisions clear or activate consistently.

**Architecture:** Treat the flow as an explicit state machine across `contactos_ruana`, `payment_conflicts`, `notificaciones_aliado`, and frontend alert lists. Add regression tests for each transition before changing code, then normalize backend state transitions and refresh frontend state after each action.

**Tech Stack:** Flask endpoints, `DBManager`, SQLite/Postgres-compatible SQL, `aliado.html`, `admin.html`, pytest contract/unit tests.

---

### Task 1: Reproduce Current Broken Flow

**Files:**
- Test: `RUANA/RUANA/tests/test_payment_dispute_state_machine.py`

- [ ] Create fixtures for two allies, one closed contact, one pending Apoyo RUANA charge.
- [ ] Assert current impugnation creates a `payment_conflicts` row and notifies the contractor.
- [ ] Assert the current admin-resolution path leaves stale alerts or mismatched blocking state.

### Task 2: Define Expected State Matrix

**Files:**
- Modify: `RUANA/RUANA/core/db_manager.py`
- Test: `RUANA/RUANA/tests/test_payment_dispute_state_machine.py`

- [ ] Pending Apoyo generated: professional has `estado_pago='pendiente_pago'`, `pendiente_pago=1`, cannot accept new jobs; contractor has no payment block.
- [ ] Professional impugns Apoyo: contact moves to `importe_en_disputa`, payment block is removed while dispute is open, contractor gets proof request notification.
- [ ] Contractor uploads proof: conflict moves to `EN_REVISION`; contractor proof alert should stop asking for upload and become "waiting for admin".
- [ ] Admin resolves in favor of contractor: contact returns to `trabajo_cerrado`, valid amount is applied, professional gets a fresh Apoyo payment alert, contractor alerts clear.
- [ ] Admin resolves in favor of professional or rejects proof: contact/charge reflects the admin decision, no stale proof/payment alert remains for the wrong party.
- [ ] Admin accepts professional payment proof: `estado_pago='pagado'`, `pendiente_pago=0`, professional alert/list disappears and job acceptance is unblocked.
- [ ] Admin rejects professional payment proof: `estado_pago='pendiente_pago'`, `pendiente_pago=1`, comprobante cleared and professional sees the rejection reason.

### Task 3: Backend State Transition Fixes

**Files:**
- Modify: `RUANA/RUANA/core/db_manager.py`
- Modify: `RUANA/RUANA/web/app.py`
- Test: `RUANA/RUANA/tests/test_payment_dispute_state_machine.py`

- [ ] Update impugnation to mark related old payment notifications read for the professional when the charge is disputed.
- [ ] Update contractor proof upload to create/update a waiting-for-admin notification state rather than leaving the same upload request active.
- [ ] Update admin conflict resolution to clear contractor dispute notifications and close/resolve `payment_conflicts`.
- [ ] Ensure admin payment validation marks all payment-related notifications for that contact as read when paid.
- [ ] Ensure `tiene_pagos_ruana_pendientes` only blocks when `estado_pago='pendiente_pago'`.

### Task 4: Frontend Alert Refresh and Copy

**Files:**
- Modify: `RUANA/RUANA/web/aliado.html`
- Modify: `RUANA/RUANA/web/admin.html`
- Test: `RUANA/RUANA/tests/test_aliado_payment_frontend_contract.py`
- Test: `RUANA/RUANA/tests/test_admin_frontend_contract.py`

- [ ] After impugning, refresh payment alerts, contact alerts, notifications, and pending contact list.
- [ ] After contractor uploads proof, replace the prompt with "documentacion enviada, pendiente de revision".
- [ ] After admin accepts/rejects/resolves, force the affected lists to reload and remove stale rows.
- [ ] Rename unclear admin actions so "Marcar pagado", "Rechazar comprobante", and "Resolver disputa" are visibly different.

### Task 5: End-to-End QA Scenarios

**Files:**
- Modify: `RUANA/e2e/ruana-critical-flows.spec.js`
- Test: `RUANA/e2e/ruana-critical-flows.spec.js`

- [ ] Add E2E for happy path: both agree, professional pays, admin accepts, alert disappears.
- [ ] Add E2E for impugnation: professional disputes, contractor uploads proof, admin resolves, stale alert disappears.
- [ ] Add E2E for payment proof rejected: professional sees rejection reason and remains blocked.

### Task 6: Verification

**Files:**
- Verify changed tests and browser behavior.

- [ ] Run `python -m pytest RUANA/RUANA/tests -q`.
- [ ] Run focused E2E for payment/dispute flows.
- [ ] Parse inline JS in `aliado.html` and `admin.html`.
- [ ] Capture screenshots of professional, contractor, and admin states before/after resolution.
