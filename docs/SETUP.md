# Instalación y ejecución local

Guía operativa para levantar RUANA en una máquina de desarrollo. Comandos **Verificados** en entorno Linux (Python 3.12) salvo indicación contraria.

| | |
|---|---|
| Fecha | 2026-09-04 |
| Variables completas | [`ENVIRONMENT_VARIABLES.md`](ENVIRONMENT_VARIABLES.md) |
| Arquitectura | [`ARCHITECTURE.md`](ARCHITECTURE.md) |

---

## 1. Requisitos previos

| Requisito | Versión mínima | Obligatorio | Notas |
|-----------|----------------|-------------|-------|
| Python | 3.11+ | Sí | Dockerfile usa 3.13; CI pytest usa 3.11 |
| pip | reciente | Sí | |
| git | cualquiera | Sí | |
| Node.js + npm | 20+ | No | Solo E2E, deploy Firebase, scripts npm |
| Postgres / Supabase | — | No | SQLite suficiente para desarrollo y tests |
| gcloud / firebase CLI | — | No | Solo deploy manual |

---

## 2. Clonar e instalar

```bash
git clone <url-del-repositorio>
cd <repo>
cp .env.example .env
```

Editar `.env` como mínimo:

```bash
FLASK_SECRET_KEY=<cadena-aleatoria-min-24-chars>
```

Para desarrollo local **no** hace falta `DATABASE_URL`; la app usará SQLite en `RUANA/ruana.db` (generado en runtime, ignorado por git).

### Entorno virtual Python

```bash
cd RUANA/web
python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

Dependencias de test:

```bash
pip install -r requirements-dev.txt
```

### Dependencias Node (opcional)

Desde la raíz del repo:

```bash
npm ci
```

---

## 3. Credenciales de administrador (local)

Opciones documentadas en [`seguridad/credenciales-admin.md`](seguridad/credenciales-admin.md).

**Opción rápida para QA/E2E (Verificado):** el repo incluye `RUANA/config/admin_credentials.qa.json` usado por Playwright.

**Opción local recomendada:**

```bash
mkdir -p .local-secrets
python RUANA/scripts/bootstrap_admin_credentials.py \
  --legacy RUANA/config/admin_codes.json \
  --output .local-secrets/admin_credentials.json
```

En `.env`:

```bash
RUANA_ADMIN_CREDENTIALS_PATH=.local-secrets/admin_credentials.json
```

`.local-secrets/` está en `.gitignore`.

---

## 4. Arrancar el servidor

Desde el directorio `RUANA/` con `PYTHONPATH` apuntando al paquete:

```bash
cd RUANA
export PYTHONPATH=.
export FLASK_SECRET_KEY="dev-secret-key-minimum-24-chars"
export RUANA_ADMIN_CREDENTIALS_PATH="../.local-secrets/admin_credentials.json"  # si aplica

python3 -m flask --app web.app run --host 0.0.0.0 --port 8080
```

Abrir: `http://localhost:8080/`

### Alternativa E2E / demo (puerto 5000)

```bash
# Desde la raíz del repo
python3 RUANA/web/run.py
```

**Verificado** en `playwright.config.js` — usa puerto **5000** y `127.0.0.1`.

### Inconsistencia de puertos

| Método | Puerto | Archivo |
|--------|--------|---------|
| `flask run` (recomendado README) | 8080 | documentación |
| `app.py` `__main__` | 5000 | `web/app.py` |
| `run.py` | 5000 | `web/run.py` |
| Playwright webServer | 5000 | `playwright.config.js` |
| Docker / Cloud Run | 8080 | `Dockerfile`, `PORT` |

Usar **8080** para alinear con producción o **5000** para E2E.

---

## 5. Modo Postgres (opcional)

Si se dispone de proyecto Supabase:

```bash
# En .env
DATABASE_URL=postgresql://postgres.<ref>:<password>@<pooler-host>:6543/postgres
SUPABASE_URL=https://<ref>.supabase.co
SUPABASE_SERVICE_ROLE_KEY=<service-role>
SUPABASE_ANON_KEY=<anon>
```

Aplicar migraciones:

```bash
npm run supabase:link    # requiere supabase login
npm run supabase:push
```

**No verificado** en esta guía: estado del schema remoto tras push.

---

## 6. Uploads locales (sin Supabase)

```bash
RUANA_ALLOW_LOCAL_UPLOADS=1
```

Los ficheros se guardan bajo `RUANA/web/static/uploads/` (gitignored salvo `.gitkeep`).

---

## 7. Ejecutar tests

### pytest (backend)

Desde la raíz:

```bash
export FLASK_SECRET_KEY="pytest_flask_secret_key_24chars"
export RUANA_ENV=test
python3 -m pytest RUANA/tests -q
```

**Resultado histórico (2026-08-19):** `784 passed, 11 skipped` en ~9 min. Recuento vigente: [`AUDITORIA_DOCUMENTAL_2026-09-04.md`](exports/AUDITORIA_DOCUMENTAL_2026-09-04.md).

### Playwright (E2E)

```bash
export FLASK_SECRET_KEY=ruana_qa_secret_key
npx playwright install chromium
npm run qa:e2e
```

Variables útiles:

| Variable | Efecto |
|----------|--------|
| `RUANA_SKIP_WEBSERVER=1` | No arranca servidor; requiere app ya corriendo |
| `RUANA_BASE_URL` | URL base (default `http://127.0.0.1:5000`) |
| `RUANA_DB_PATH` | SQLite E2E |

Reporte HTML: `qa-artifacts/playwright-report/index.html`

---

## 8. Herramientas auxiliares

| Herramienta | Comando | Uso |
|-------------|---------|-----|
| Mapa de código | `dev-tools/code-map/generate.sh` | Grafo interactivo local |
| Verificar Supabase | `npm run verify:supabase` | Script Python en `RUANA/scripts/` |
| Generar secreto admin GitHub | `npm run admin:secret-json` | CI/CD |

---

## 9. Problemas frecuentes

| Síntoma | Causa probable | Solución |
|---------|----------------|----------|
| `[RUANA][BOOT] Configuración inválida` | Secretos débiles con `RUANA_ENV=production` | Usar dev o secretos fuertes |
| Puerto en uso | Conflicto 5000/8080 | Cambiar `--port` o matar proceso |
| Admin 401 | Sin `RUANA_ADMIN_CREDENTIALS_*` | Configurar credenciales (§3) |
| pytest lento | Suite grande (108 archivos `test_*.py`) | Normal; usar `-k` para filtrar |
| `python` no encontrado | Solo `python3` instalado | Usar `python3` explícitamente |

---

## 10. Siguiente paso

- Deploy: [`DEPLOYMENT.md`](DEPLOYMENT.md)
- Handoff: [`HANDOFF.md`](HANDOFF.md)
