# Admin Crear Codigo Aliado Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an admin-only way to generate first-allied invitation codes.

**Architecture:** Add a small backend helper used by a new admin endpoint, then add a compact action in the existing admin panel. The generated code creates the same placeholder shape as the existing aliado invitation flow.

**Tech Stack:** Flask, pytest, vanilla HTML/JS.

---

### Task 1: Backend Endpoint

**Files:**
- Modify: `RUANA/web/app.py`
- Modify: `RUANA/tests/test_hito_2a_permissions.py`

- [x] **Step 1: Write the failing test**

Add a test that posts to `/api/admin/invitaciones/crear` with admin write headers and asserts a 201 response, a returned `codigo`, and a `crear_aliado` call using `estado="pendiente_completar"`.

- [x] **Step 2: Run the focused test**

Run: `python -m pytest RUANA/tests/test_hito_2a_permissions.py::test_admin_crear_invitacion_creates_placeholder -q`
Observed: FAIL with 404 because the endpoint did not exist.

- [x] **Step 3: Implement minimal backend**

Added a helper for placeholder creation and a `@require_admin_escritura` route at `/api/admin/invitaciones/crear`.

- [x] **Step 4: Run focused tests**

Run: `python -m pytest RUANA/tests/test_hito_2a_permissions.py -q`
Observed: PASS.

### Task 2: Admin UI

**Files:**
- Modify: `RUANA/web/admin.html`

- [x] **Step 1: Add a compact admin action**

Added `Crear Codigo Aliado` in the existing admin actions grid.

- [x] **Step 2: Wire fetch**

Calls `POST /api/admin/invitaciones/crear` with existing admin auth headers and displays the returned code with a copy button.

- [x] **Step 3: Verify manually**

Ran Flask locally, logged into `/admin`, generated a code, then entered it on `/` and confirmed navigation to `register.html`.

### Task 3: GitHub Prep

**Files:**
- Review all changed files.

- [ ] **Step 1: Run verification**

Run backend tests and a local smoke test.

- [ ] **Step 2: Commit and push after approval**

Commit only the scoped feature changes, then push/open PR when the user confirms.
