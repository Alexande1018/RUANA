# Hito 2A Seguridad y Permisos Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Block anonymous writes to the first three critical business-state endpoints and prove the permission behavior with reproducible pytest tests.

**Architecture:** Keep the current Flask app and session model. Add focused pytest coverage around the affected routes using Flask's test client, monkeypatched DB fakes, and direct `X-Ruana-Session-Id` session creation. Then apply the smallest route-level authorization changes in `RUANA/web/app.py`.

**Tech Stack:** Python 3, Flask 2.3, pytest, monkeypatch fixtures, RUANA server-side session store.

---

## File Structure

- Create `RUANA/tests/conftest.py`: shared Flask test client, session cleanup, session-header helpers, and fake DB classes.
- Create `RUANA/tests/test_hito_2a_permissions.py`: route-level permission tests for invitations, competition finalization, and monthly purge.
- Create `RUANA/web/requirements-dev.txt`: development/test dependencies that include runtime requirements plus pytest.
- Modify `RUANA/web/app.py`: add route decorators and make invitation creation resolve the inviter from the authenticated aliado session.
- Modify `ROADMAP.md`: update only the resume block after verification so the next session knows Hito 2A status.

Do not modify unrelated dirty files. The repo currently has pre-existing uncommitted changes, so every `git add` command below stages only files owned by this plan.

---

### Task 1: Add Test Harness And Failing Permission Tests

**Files:**
- Create: `RUANA/tests/conftest.py`
- Create: `RUANA/tests/test_hito_2a_permissions.py`
- Create: `RUANA/web/requirements-dev.txt`

- [ ] **Step 1: Add test dependency file**

Create `RUANA/web/requirements-dev.txt`:

```text
-r requirements.txt
pytest>=8.0.0,<9.0.0
```

- [ ] **Step 2: Add shared pytest fixtures**

Create `RUANA/tests/conftest.py`:

```python
import time

import pytest

from RUANA.web import app as app_module


class Hito2AFakeDB:
    def __init__(self):
        self.calls = []

    def codigo_existe(self, codigo):
        self.calls.append(("codigo_existe", codigo))
        return False

    def obtener_aliado_por_codigo(self, codigo):
        self.calls.append(("obtener_aliado_por_codigo", codigo))
        return {"id": 42, "codigo": codigo, "estado": "activo"}

    def crear_aliado(self, **kwargs):
        self.calls.append(("crear_aliado", kwargs))
        return {"status": "success"}

    def _registrar_invitacion(self, codigo, aliado_id):
        self.calls.append(("_registrar_invitacion", codigo, aliado_id))

    def marcar_solicitud_contestada(self, solicitud_id, invitador_aliado_id=None):
        self.calls.append(("marcar_solicitud_contestada", solicitud_id, invitador_aliado_id))

    def finalizar_competencia_activas_vencidas(self):
        self.calls.append(("finalizar_competencia_activas_vencidas",))
        return [{"grupo_id": 1, "resultado": "finalizada"}]

    def purga_mensual(self):
        self.calls.append(("purga_mensual",))
        return {"status": "success", "procesados": 1}


@pytest.fixture(autouse=True)
def clear_ruana_sessions():
    app_module._RUANA_SESSION_STORE.clear()
    app_module.app.config.update(TESTING=True)
    yield
    app_module._RUANA_SESSION_STORE.clear()


@pytest.fixture
def client():
    return app_module.app.test_client()


@pytest.fixture
def fake_db(monkeypatch):
    db = Hito2AFakeDB()
    monkeypatch.setattr(app_module, "get_db", lambda: db)
    return db


def make_session_headers(tipo, codigo, permisos=None):
    session_id = app_module._ruana_session_create(
        tipo=tipo,
        codigo=codigo,
        expires_at=time.time() + 3600,
        permisos=permisos or [],
    )
    return {app_module.RUANA_SESSION_HEADER: session_id}
```

- [ ] **Step 3: Add permission tests**

Create `RUANA/tests/test_hito_2a_permissions.py`:

```python
from RUANA.tests.conftest import make_session_headers


def test_crear_invitacion_rejects_anonymous_request_without_touching_db(client, fake_db):
    response = client.post(
        "/api/invitaciones/crear",
        json={"zona": "08001", "aliado_id": 999},
    )

    assert response.status_code == 401
    assert fake_db.calls == []


def test_finalizar_competencia_rejects_anonymous_request_without_touching_db(client, fake_db):
    response = client.post("/api/competencia/finalizar-vencidas")

    assert response.status_code == 401
    assert fake_db.calls == []


def test_purga_mensual_rejects_anonymous_request_without_touching_db(client, fake_db):
    response = client.post("/api/purga/mensual")

    assert response.status_code == 401
    assert fake_db.calls == []


def test_finalizar_competencia_rejects_read_only_admin_without_touching_db(client, fake_db):
    headers = make_session_headers("admin", "0000", permisos=["leer"])

    response = client.post("/api/competencia/finalizar-vencidas", headers=headers)

    assert response.status_code == 403
    assert fake_db.calls == []


def test_purga_mensual_rejects_read_only_admin_without_touching_db(client, fake_db):
    headers = make_session_headers("admin", "0000", permisos=["leer"])

    response = client.post("/api/purga/mensual", headers=headers)

    assert response.status_code == 403
    assert fake_db.calls == []


def test_crear_invitacion_authenticated_aliado_uses_session_inviter(client, fake_db):
    headers = make_session_headers("aliado", "A0001")

    response = client.post(
        "/api/invitaciones/crear",
        json={"zona": "08001", "aliado_id": 999},
        headers=headers,
    )

    assert response.status_code == 201
    data = response.get_json()
    assert data["status"] == "success"
    assert data["tipo"] == "invitacion"
    assert ("obtener_aliado_por_codigo", "A0001") in fake_db.calls
    assert any(call[0] == "_registrar_invitacion" and call[2] == 42 for call in fake_db.calls)


def test_finalizar_competencia_allows_write_admin(client, fake_db):
    headers = make_session_headers("admin", "ADMIN001", permisos=["leer", "escribir"])

    response = client.post("/api/competencia/finalizar-vencidas", headers=headers)

    assert response.status_code == 200
    data = response.get_json()
    assert data["status"] == "success"
    assert data["finalizadas"] == 1
    assert ("finalizar_competencia_activas_vencidas",) in fake_db.calls


def test_purga_mensual_allows_write_admin(client, fake_db):
    headers = make_session_headers("admin", "ADMIN001", permisos=["leer", "escribir"])

    response = client.post("/api/purga/mensual", headers=headers)

    assert response.status_code == 200
    data = response.get_json()
    assert data["status"] == "success"
    assert data["procesados"] == 1
    assert ("purga_mensual",) in fake_db.calls
```

- [ ] **Step 4: Install development test dependencies if pytest is missing**

Run:

```powershell
python -m pip install -r RUANA/web/requirements-dev.txt
```

Expected:

```text
Successfully installed pytest...
```

If pytest is already installed, pip may report the requirements as already satisfied; that is acceptable.

- [ ] **Step 5: Run the new tests and verify RED**

Run:

```powershell
python -m pytest RUANA/tests/test_hito_2a_permissions.py -v
```

Expected before implementation:

```text
FAILED test_crear_invitacion_rejects_anonymous_request_without_touching_db
FAILED test_finalizar_competencia_rejects_anonymous_request_without_touching_db
FAILED test_purga_mensual_rejects_anonymous_request_without_touching_db
FAILED test_finalizar_competencia_rejects_read_only_admin_without_touching_db
FAILED test_purga_mensual_rejects_read_only_admin_without_touching_db
```

The authenticated positive tests may already pass because the underlying business path exists. The RED gate for this task is the permission failure set above.

- [ ] **Step 6: Commit the RED tests**

```powershell
git add -- RUANA/tests/conftest.py RUANA/tests/test_hito_2a_permissions.py RUANA/web/requirements-dev.txt
git -c user.name='Codex' -c user.email='codex@local' commit -m "test: cover hito 2a critical endpoint permissions"
```

---

### Task 2: Protect The Critical Routes

**Files:**
- Modify: `RUANA/web/app.py`
- Test: `RUANA/tests/test_hito_2a_permissions.py`

- [ ] **Step 1: Add `@require_aliado` to invitation creation**

In `RUANA/web/app.py`, change the invitation route header from:

```python
@app.route('/api/invitaciones/crear', methods=['POST'])
def crear_invitacion():
```

to:

```python
@app.route('/api/invitaciones/crear', methods=['POST'])
@require_aliado
def crear_invitacion():
```

- [ ] **Step 2: Resolve invitation ownership from session**

In `crear_invitacion`, replace this block:

```python
        # Extraer datos (aliado_id: quien genera la invitaciÃ³n; fallback desde sesiÃ³n si no viene en body)
        aliado_invitador_id = data.get('aliado_id')
        if aliado_invitador_id is None:
            codigo_sesion = _aliado_codigo()
            if codigo_sesion:
                aliado_sesion = db.obtener_aliado_por_codigo(codigo_sesion)
                if aliado_sesion:
                    aliado_invitador_id = aliado_sesion.get('id')
        zona = data.get('zona', '').strip()
        solicitud_id = data.get('solicitud_id')
```

with:

```python
        # La identidad del invitador sale siempre de la sesion de aliado.
        codigo_sesion = _aliado_codigo()
        aliado_sesion = db.obtener_aliado_por_codigo(codigo_sesion) if codigo_sesion else None
        if not aliado_sesion:
            return jsonify({'status': 'error', 'message': 'Aliado invitador no encontrado'}), 403

        aliado_invitador_id = aliado_sesion.get('id')
        zona = data.get('zona', '').strip()
        solicitud_id = data.get('solicitud_id')
```

- [ ] **Step 3: Add admin-write decorators to cron-like endpoints**

In `RUANA/web/app.py`, change:

```python
@app.route('/api/competencia/finalizar-vencidas', methods=['POST'])
def finalizar_competencia_vencidas():
```

to:

```python
@app.route('/api/competencia/finalizar-vencidas', methods=['POST'])
@require_admin_escritura
def finalizar_competencia_vencidas():
```

Then change:

```python
@app.route('/api/purga/mensual', methods=['POST'])
def purga_mensual():
```

to:

```python
@app.route('/api/purga/mensual', methods=['POST'])
@require_admin_escritura
def purga_mensual():
```

- [ ] **Step 4: Run Hito 2A tests and verify GREEN**

Run:

```powershell
python -m pytest RUANA/tests/test_hito_2a_permissions.py -v
```

Expected:

```text
8 passed
```

- [ ] **Step 5: Commit protected routes**

```powershell
git add -- RUANA/web/app.py
git -c user.name='Codex' -c user.email='codex@local' commit -m "fix: protect hito 2a critical endpoints"
```

---

### Task 3: Run Focused Regression Checks

**Files:**
- Read only unless a failure points to a Hito 2A regression.

- [ ] **Step 1: Run the Hito 2A permission suite again**

```powershell
python -m pytest RUANA/tests/test_hito_2a_permissions.py -v
```

Expected:

```text
8 passed
```

- [ ] **Step 2: Run existing lightweight Python tests if pytest can collect them safely**

Run:

```powershell
python -m pytest RUANA/tests -v
```

Expected:

```text
8 passed
```

If pytest reports only the Hito 2A tests, that is acceptable because `RUANA/tests` currently contains no other test modules.

- [ ] **Step 3: Inspect route decorators statically**

Run:

```powershell
rg -n -C 2 "/api/invitaciones/crear|/api/competencia/finalizar-vencidas|/api/purga/mensual|def crear_invitacion|def finalizar_competencia_vencidas|def purga_mensual" RUANA/web/app.py
```

Expected snippets include:

```text
@app.route('/api/invitaciones/crear', methods=['POST'])
@require_aliado
def crear_invitacion():

@app.route('/api/competencia/finalizar-vencidas', methods=['POST'])
@require_admin_escritura
def finalizar_competencia_vencidas():

@app.route('/api/purga/mensual', methods=['POST'])
@require_admin_escritura
def purga_mensual():
```

---

### Task 4: Update Resume Notes And Final Commit

**Files:**
- Modify: `ROADMAP.md`

- [ ] **Step 1: Update the roadmap resume block**

In `ROADMAP.md`, replace the current `## 7. Estado para reanudar` bullet list with:

```markdown
## 7. Estado para reanudar

- Hito activo: Hito 2 - Cierre de superficie critica.
- Tarea terminada: Hito 2A protege `POST /api/invitaciones/crear`, `POST /api/competencia/finalizar-vencidas` y `POST /api/purga/mensual` con pruebas pytest de permisos.
- Verificacion ejecutada: `python -m pytest RUANA/tests/test_hito_2a_permissions.py -v` y `python -m pytest RUANA/tests -v`.
- Siguiente tarea: Hito 2B, cerrar lectura publica de datos personales en `/api/aliados*`.
- Bloqueos: ninguno documentado.
```

- [ ] **Step 2: Run final verification**

Run:

```powershell
python -m pytest RUANA/tests/test_hito_2a_permissions.py -v
python -m pytest RUANA/tests -v
```

Expected:

```text
8 passed
8 passed
```

- [ ] **Step 3: Review only planned diffs**

Run:

```powershell
git diff -- RUANA/web/app.py RUANA/tests/conftest.py RUANA/tests/test_hito_2a_permissions.py RUANA/web/requirements-dev.txt ROADMAP.md
```

Expected:

```text
Only Hito 2A test harness, route protection, dev test dependency, and roadmap resume changes appear.
```

- [ ] **Step 4: Commit roadmap update**

```powershell
git add -- ROADMAP.md
git -c user.name='Codex' -c user.email='codex@local' commit -m "docs: record hito 2a security progress"
```

- [ ] **Step 5: Report final status**

Include:

```text
Implemented Hito 2A.
Protected routes:
- POST /api/invitaciones/crear -> aliado session
- POST /api/competencia/finalizar-vencidas -> admin write permission
- POST /api/purga/mensual -> admin write permission

Verification:
- python -m pytest RUANA/tests/test_hito_2a_permissions.py -v
- python -m pytest RUANA/tests -v

Next recommended task:
- Hito 2B: close public PII reads in /api/aliados*
```

---

## Self-Review

Spec coverage:

- Tests for critical permission behavior are covered in Task 1.
- `POST /api/invitaciones/crear` requiring aliado session is covered in Task 2.
- `POST /api/competencia/finalizar-vencidas` requiring admin write permission is covered in Task 2.
- `POST /api/purga/mensual` requiring admin write permission is covered in Task 2.
- Anonymous and read-only admin rejection are covered in Task 1 tests.
- Reproducible no-real-DB testing is covered by the monkeypatched fake DB in `conftest.py`.
- Closing documentation is covered in Task 4.

Placeholder scan:

- No placeholder markers or unspecified implementation steps remain.

Type consistency:

- Tests patch `app_module.get_db`, which is the function referenced by the route handlers.
- Tests use the existing `_ruana_session_create`, `_RUANA_SESSION_STORE`, and `RUANA_SESSION_HEADER` names from `RUANA/web/app.py`.
- Fake DB method names match the methods called by the affected routes.
