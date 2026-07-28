# Auditoría forense del repositorio RUANA

**Fecha:** 26 de julio de 2026  
**Alcance:** 149 archivos analizados (excl. `.git/`, `__pycache__/`, `node_modules/`)  
**Método:** análisis estático de imports, referencias textuales, rutas Flask, CI/CD, Docker, configuración y dependencias pip/npm  
**Restricción aplicada:** no se modificó ningún archivo del código fuente durante la auditoría  

---

## Tabla de contenidos

1. [Resumen ejecutivo](#1-resumen-ejecutivo)
2. [Tabla completa de archivos](#2-tabla-completa-de-archivos)
3. [Árbol de dependencias](#3-árbol-de-dependencias)
4. [Lista de archivos eliminables](#4-lista-de-archivos-eliminables-riesgo-prácticamente-nulo)
5. [Lista de archivos dudosos](#5-lista-de-archivos-dudosos)
6. [Código muerto](#6-código-muerto-lista-completa-verificada)
7. [Dependencias antiguas / sin uso](#7-dependencias-antiguas--sin-uso)
8. [Plan de limpieza paso a paso](#8-plan-de-limpieza-paso-a-paso)
9. [Hallazgos sobre AceroTradefinal](#9-hallazgos-clave-sobre-acerotradefinal)
10. [Apéndice: búsqueda de términos trading](#10-apéndice-búsqueda-de-términos-trading)

---

## 1. Resumen ejecutivo

### 1.1 Estado del repositorio

RUANA es una **plataforma web de gestión de aliados/oficios** (Flask + SQLite/Postgres/Supabase), con frontend HTML/JS, tests pytest (31 archivos) y E2E Playwright.

**Entry point de producción:**

```dockerfile
# Dockerfile, línea 17
CMD ["sh", "-c", "exec gunicorn --bind :${PORT:-8080} --workers 1 --threads 8 --timeout 0 web.app:app"]
```

**No quedan módulos ejecutables de trading** (Binance, MetaTrader, MT5, backtesting, bots, TradingView, websockets activos). Búsqueda exhaustiva en código fuente: **0 coincidencias** para esos términos en `.py`, `.html`, `.js`, `.sql`.

### 1.2 Restos de AceroTradefinal identificados

| Tipo de resto | Evidencia |
|---|---|
| Comentarios de procedencia | `orquestador.py:5`, `preflight_validator.py:5`, `logger.py:5` |
| Variables stub de trading | `orquestador.py:53-66` (`ctrader_connected`, `capital_inicial`, `trades_ganadores`, `pnl_total`) |
| Claves de config con semántica trading | `ruana_reglas_v1.json:3-4` (`capital`, `risk_per_trade_pct`) — solo usadas por el orquestador en logs/stubs |
| Email legacy | `aliado.html:4242` — fallback `acerotrade.signal@gmail.com` |
| Documentación de stubs ya eliminados | `MAPA_MENTAL_RUANA.md:487` menciona `risk_engine.py`, `executor.py`, `calculator.py` que **no existen en el repo** |

### 1.3 Riesgos identificados

| Riesgo | Severidad | Evidencia |
|---|---|---|
| Rutas Flask a HTML inexistentes | Media | `app.py:312-337` → `test_panel.html`, `diagnostico-panel.html`, `test-simple.html`, `panel-test.html` **no existen** |
| Referencia a JS inexistente | Media | `private-panel*.html:11` → `/static/js/motor-ruana.js` **no existe** |
| Frontend duplicado/huérfano | Baja | `referidos-module.js` (724 líneas) nunca cargado; lógica inline en `aliado.html`/`admin.html` |
| Subsistema batch desconectado del web | Baja | `orquestador.py` no importado por `app.py`; solo CLI batch |
| Artefactos locales en repo | Baja | `ruana.db`, logs, uploads de prueba, `preflight_report.json` |
| Credencial/email AceroTrade en producción | Media | Fallback PayPal con email `acerotrade.signal@gmail.com` |

### 1.4 Nivel de limpieza

| Métrica | Valor |
|---|---|
| Archivos esenciales runtime web | ~35 |
| Archivos esenciales batch/ops | ~15 |
| Tests/CI/docs/deploy | ~70 |
| **Eliminables con riesgo ~0** (demostrado) | **12 archivos** |
| **Dudosos** (requieren decisión manual) | **~25 archivos** |
| Código AceroTrade ejecutable restante | **0 archivos** |
| Herencia AceroTrade en nombres/comentarios/config | **~6 puntos** (no archivos enteros) |

**Conclusión:** el repositorio está **funcionalmente migrado a RUANA**. La deuda es principalmente **código muerto, paneles legacy y nomenclatura heredada**, no un segundo sistema de trading coexistiendo.

### 1.5 Leyenda de categorías

- 🟢 **ESENCIAL PARA RUANA** — se utiliza actualmente; eliminarlo rompería funcionalidad
- 🟡 **DUDOSO** — referencias parciales; requiere revisión manual
- 🔴 **HEREDADO / ELIMINABLE** — sin imports, sin referencias de ejecución, sin dependientes (demostrado)

---

## 2. Tabla completa de archivos

### 2.1 Raíz del repositorio

| Archivo | Categoría | ¿Se importa? | ¿Quién lo usa? | Riesgo al eliminar | Acción recomendada |
|---|---|---|---|---|---|
| `README.md` | 🟡 | No | Documentación | Ninguno funcional | Mantener |
| `ROADMAP.md` | 🟡 | No | Documentación | Ninguno | Mantener |
| `Dockerfile` | 🟢 | No (CI) | Build Cloud Run L10-17 | **Alto** — rompe deploy | Mantener |
| `.dockerignore` | 🟢 | No | Docker build L16-17 excluye `ruana.db` | Medio | Mantener |
| `.gcloudignore` | 🟢 | No | GCP deploy | Medio | Mantener |
| `.gitignore` | 🟢 | No | Git | Bajo | Mantener |
| `.env.example` | 🟢 | No | `settings.py` carga vars; docs | Medio | Mantener |
| `.firebaserc` | 🟢 | No | Firebase CLI | Medio — rompe hosting | Mantener |
| `firebase.json` | 🟢 | No | Rewrites → Cloud Run L10-17 | **Alto** | Mantener |
| `firebase-public/.gitkeep` | 🟢 | No | Placeholder hosting | Bajo | Mantener |
| `package.json` | 🟢 | No | CI `npm ci`, scripts deploy/QA | **Alto** | Mantener |
| `package-lock.json` | 🟢 | No | `npm ci` | **Alto** | Mantener |
| `playwright.config.js` | 🟢 | No | E2E `npm run qa:e2e` | Alto en CI | Mantener |

### 2.2 `.github/workflows/`

| Archivo | Categoría | ¿Se importa? | ¿Quién lo usa? | Riesgo | Acción |
|---|---|---|---|---|---|
| `ruana-qa.yml` | 🟢 | No | CI: pytest + Playwright L68-78 | Alto | Mantener |
| `deploy-firebase.yml` | 🟢 | No | Deploy prod | Alto | Mantener |
| `deploy-firebase-preview.yml` | 🟢 | No | Deploy preview | Alto | Mantener |
| `trigger-preview-deploy.yml` | 🟢 | No | Trigger preview | Alto | Mantener |

### 2.3 `scripts/` (deploy GCP/Firebase)

| Archivo | Categoría | ¿Se importa? | ¿Quién lo usa? | Riesgo | Acción |
|---|---|---|---|---|---|
| `deploy_cloudrun.ps1` | 🟢 | No | `package.json` → `cloudrun:deploy` | Alto en deploy | Mantener |
| `deploy_firebase_hosting.ps1` | 🟢 | No | `package.json` → `deploy:hosting` | Alto | Mantener |
| `set_gcp_secrets.ps1` | 🟢 | No | `package.json` → `gcp:secrets` | Alto | Mantener |
| `allow_dev_branch_wif.ps1` | 🟢 | No | `package.json` → `gcp:allow-dev-wif` | Medio | Mantener |
| `ruana_env.ps1` | 🟢 | No | Invocado por otros `.ps1` | Medio | Mantener |
| `verify_runtime.ps1` | 🟢 | No | `package.json` → `verify:runtime` | Medio | Mantener |

### 2.4 `e2e/`

| Archivo | Categoría | ¿Se importa? | ¿Quién lo usa? | Riesgo | Acción |
|---|---|---|---|---|---|
| `ruana-critical-flows.spec.js` | 🟢 | No | CI `playwright test` | Alto en QA | Mantener |
| `utils/ruana-fixtures.js` | 🟢 | require | `ruana-critical-flows.spec.js` | Alto en QA | Mantener |
| `utils/qa-narrator.js` | 🟢 | require | spec E2E | Alto en QA | Mantener |

### 2.5 `docs/`

| Archivo | Categoría | ¿Se importa? | ¿Quién lo usa? | Riesgo | Acción |
|---|---|---|---|---|---|
| 10 archivos `.md` en `docs/` | 🟡 | No | Documentación diseño/QA | Ninguno runtime | Mantener |

### 2.6 `supabase/migrations/` (7 archivos SQL)

| Archivo | Categoría | ¿Se importa? | ¿Quién lo usa? | Riesgo | Acción |
|---|---|---|---|---|---|
| `20260519000100_init_ruana_clean.sql` | 🟢 | No | `supabase db push`, schema Postgres | **Alto** | Mantener |
| `20260519000200_sqlite_compat_names.sql` | 🟢 | No | Migración secuencial | Alto | Mantener |
| `20260519000300_sqlite_compat_types.sql` | 🟢 | No | Migración secuencial | Alto | Mantener |
| `20260714000100_aliados_foto_perfil_url.sql` | 🟢 | No | Test `test_postgres_foto_perfil_migration.py` | Alto | Mantener |
| `20260722000100_aliados_invitado_por_linaje.sql` | 🟢 | No | Schema linaje/referidos | Alto | Mantener |
| `20260723000100_contactos_es_urgente.sql` | 🟢 | No | Score regla 6 | Alto | Mantener |
| `20260723000200_aliado_accesos_dia.sql` | 🟢 | No | Schema accesos | Alto | Mantener |

---

### 2.7 `RUANA/core/` — núcleo backend

| Archivo | Categoría | ¿Se importa? | ¿Quién lo usa? | Riesgo | Acción |
|---|---|---|---|---|---|
| `__init__.py` | 🟡 | No directo | Paquete; 18 tests importan submódulos | Bajo | Mantener |
| `db_manager.py` | 🟢 | **Sí** | `app.py:29`, `motor_evaluacion.py:12`, 31 tests, scripts | **Crítico** | Mantener |
| `settings.py` | 🟢 | **Sí** | `app.py:30`, `db_manager.py:17`, `supabase_client.py:13` | **Crítico** | Mantener |
| `postgres_compat.py` | 🟢 | **Sí** | `db_manager.py:16`, `test_payment_dispute_state_machine.py:7` | Alto | Mantener |
| `storage_manager.py` | 🟢 | **Sí** | `app.py:31`, tests foto/storage | Alto | Mantener |
| `supabase_client.py` | 🟢 | **Sí** | `storage_manager.py:17-19`, `verify_supabase.py:15` | Alto | Mantener |
| `image_utils.py` | 🟢 | **Sí** | `storage_manager.py:108-110`, `test_image_utils.py:6` | Alto | Mantener |
| `orquestador.py` | 🟡 | **Sí** | `INTEGRATION_EXAMPLES.py:121` (doc); `__main__` CLI batch. **No** importado por `app.py` | Medio — solo batch | Mantener; limpiar stubs AceroTrade |
| `preflight_validator.py` | 🟡 | **Sí** | `orquestador.py:19,102`; `__main__` | Medio | Mantener |

**Herencia AceroTrade en `orquestador.py` (líneas 53-66):**

```python
self.ctrader_connected = False
self.capital_inicial = self.config.get("capital", 1000.0)
self.equity_actual = self.capital_inicial
self.equity_max = self.capital_inicial
self.trades_ganadores = 0
self.trades_perdedores = 0
self.pnl_total = 0.0
```

Estas variables **no son leídas** por `app.py` ni por tests. Solo se inicializan y loguean.

---

### 2.8 `RUANA/engines/`, `events/`, `metrics/`, `utils/`

| Archivo | Categoría | ¿Se importa? | ¿Quién lo usa? | Riesgo | Acción |
|---|---|---|---|---|---|
| `engines/motor_evaluacion.py` | 🟢 | **Sí** | `app.py:2714-2716` (API evaluaciones), `orquestador.py:21` | **Alto** | Mantener |
| `engines/__init__.py` | 🟡 | No | Paquete vacío | Bajo | Mantener |
| `events/event_bus.py` | 🟡 | **Sí** | `orquestador.py:23,46`; escribe `logs/eventos_ruana.jsonl` | Medio (solo batch) | Mantener |
| `events/__init__.py` | 🟡 | No | Re-export `EventBus` — **nadie importa `from events import`** | Bajo | Mantener o fusionar |
| `metrics/collector.py` | 🟡 | **Sí** | `orquestador.py:22,49` | Medio (solo batch) | Mantener |
| `metrics/__init__.py` | 🟡 | No | Paquete vacío | Bajo | Mantener |
| `utils/logger.py` | 🟡 | **Sí** | `orquestador.py:18`, `preflight_validator.py:18` | Medio | Mantener |
| `utils/__init__.py` | 🟡 | No | Paquete vacío | Bajo | Mantener |

---

### 2.9 `RUANA/config/`

| Archivo | Categoría | ¿Se importa? | ¿Quién lo usa? | Riesgo | Acción |
|---|---|---|---|---|---|
| `admin_codes.json` | 🟢 | No (lectura JSON) | `app.py:3144-3158` POST `/api/admin/validar` | **Alto** | Mantener |
| `oficios_ruana.json` | 🟢 | No (lectura JSON) | `app.py:1093`, `db_manager.py:1588+` (catálogo 77 oficios) | **Alto** | Mantener |
| `ruana_reglas_v1.json` | 🟢 | No (lectura JSON) | `db_manager.py` (≥10 lecturas), `orquestador.py:41`, `preflight_validator.py:77` | **Alto** | Mantener |
| Claves `capital`, `risk_per_trade_pct` | 🔴 (datos) | N/A | Solo `orquestador.py:59,75` — **no usadas por web ni motor** | Ninguno | Eliminar claves en fase 2 |

---

### 2.10 `RUANA/web/` — runtime principal

| Archivo | Categoría | ¿Se importa? | ¿Quién lo usa? | Riesgo | Acción |
|---|---|---|---|---|---|
| `app.py` | 🟢 | gunicorn | Entry prod; 18 tests importan `RUANA.web.app` | **Crítico** | Mantener |
| `run.py` | 🟡 | No | Dev local `python run.py` → `from app import app` L199 | Bajo en prod | Mantener |
| `requirements.txt` | 🟢 | No | Docker L10, pip install | **Crítico** | Mantener |
| `requirements-dev.txt` | 🟢 | No | CI `ruana-qa.yml:61` | Alto en QA | Mantener |
| `__init__.py` | 🟡 | **Sí** | 18 tests: `from RUANA.web import app` | Medio | Mantener |
| `index.html` | 🟢 | No | `app.py:290` ruta `/` | Alto | Mantener |
| `register.html` | 🟢 | No | `app.py:297`, E2E | Alto | Mantener |
| `invite.html` | 🟢 | No | `app.py:986`, E2E | Alto | Mantener |
| `aliado.html` | 🟢 | No | `app.py:357,309,993` (panel principal) | **Crítico** | Mantener |
| `admin.html` | 🟢 | No | `app.py:350` | **Crítico** | Mantener |
| `dashboard.html` | 🟡 | No | `app.py:999`; solo redirige a `aliado.html` L11 | Bajo | Mantener (redirect activo) |
| `private-panel.html` | 🔴 | No | Ruta `/private-panel` sirve **`aliado.html`** L993, no este archivo | **Ninguno** | Eliminar |
| `private-panel-new.html` | 🔴 | No | Sin ruta Flask; 0 servido | Ninguno | Eliminar |
| `VERIFICACION_FLUJO.html` | 🔴 | No | Sin ruta Flask; solo README | Ninguno | Eliminar |
| `install.sh` / `install.bat` | 🟡 | No | Referenciados en `QUICKSTART.py`, `STATS.py` | Bajo | Mantener |
| `FIRST_RUN.py` | 🟡 | No | Onboarding dev; referenciado solo en `STATS.py` | Ninguno prod | Mantener o archivar |
| `QUICKSTART.py` | 🟡 | No | Onboarding dev | Ninguno prod | Mantener o archivar |
| `INTEGRATION_EXAMPLES.py` | 🟡 | No | Documentación código; importa orquestador L121 | Ninguno prod | Mantener o archivar |
| `STATS.py` | 🔴 | No | **0 referencias** en todo el repo | Ninguno | Eliminar |

### 2.11 `RUANA/web/static/`

| Archivo | Categoría | ¿Se importa? | ¿Quién lo usa? | Riesgo | Acción |
|---|---|---|---|---|---|
| `css/styles.css` | 🟢 | No | 7 HTML activos (`href`) | Alto | Mantener |
| `css/panel-premium.css` | 🟢 | No | `aliado.html:1581` | Alto | Mantener |
| `css/config.css` | 🔴 | No | **0 `<link>` en HTML**; solo docs | Ninguno | Eliminar |
| `css/referidos-tree.css` | 🔴 | No | **0 referencias** | Ninguno | Eliminar |
| `js/ruana-ui.js` | 🟢 | No | `register.html`, `invite.html`, `admin.html`, `aliado.html` | Alto | Mantener |
| `js/dashboard.js` | 🔴 | No | **0 `<script src>`** en HTML activo | Ninguno | Eliminar |
| `js/referidos-module.js` | 🔴 | No | **0 referencias**; clase `RuanaReferidosTree` no cargada | Ninguno | Eliminar |
| `images/ruana-logo.svg` | 🟢 | No | `index.html`, `admin.html`, `aliado.html` | Alto | Mantener |
| `images/PayPal.png` | 🟢 | No | `aliado.html:2063`, `ruana_reglas_v1.json:17` | Alto | Mantener |
| `uploads/pagos_ruana/*.png` (7) | 🟡 | No | Datos de prueba locales; URLs dinámicas posibles en BD | Bajo | Revisar BD antes de borrar |

### 2.12 `RUANA/scripts/`

| Archivo | Categoría | ¿Se importa? | ¿Quién lo usa? | Riesgo | Acción |
|---|---|---|---|---|---|
| `purga_mensual.py` | 🟢 | No | Cron; `db.purga_mensual()`; test permisos | Medio-alto | Mantener |
| `seed_aliados.py` | 🟡 | No | README dev; CLI manual | Bajo | Mantener |
| `verify_supabase.py` | 🟢 | No | `package.json` → `verify:supabase` | Medio | Mantener |
| `test_foto_perfil_e2e.py` | 🟡 | No | Script manual E2E | Bajo | Mantener |
| `cron_purga_mensual.txt` | 🟡 | No | Plantilla cron (ruta Mac hardcodeada) | Ninguno | Mantener/actualizar |

### 2.13 `RUANA/tests/` (31 tests + conftest)

| Archivo | Categoría | ¿Se importa? | ¿Quién lo usa? | Riesgo | Acción |
|---|---|---|---|---|---|
| `conftest.py` + 31 `test_*.py` | 🟢 | pytest | CI `ruana-qa.yml:72` | Alto en QA | Mantener todos |

### 2.14 Tests manuales raíz `RUANA/`

| Archivo | Categoría | ¿Se importa? | ¿Quién lo usa? | Riesgo | Acción |
|---|---|---|---|---|---|
| `test_competencia_automatica.py` | 🟡 | No | CLI manual; **no en CI** | Ninguno | Mantener o mover a `tests/` |
| `test_solicitud_grupo.py` | 🟡 | No | CLI manual con `requests` (no en requirements) | Ninguno | Mantener o integrar en CI |

### 2.15 Artefactos y otros

| Archivo | Categoría | ¿Se importa? | ¿Quién lo usa? | Riesgo | Acción |
|---|---|---|---|---|---|
| `ruana.db` | 🟡 | No | `db_manager.py:38`; excluido de Docker | Bajo — dato local | No commitear; .gitignore |
| `logs/eventos_ruana.jsonl` | 🟡 | No | Escrito por `event_bus.py:32` en batch | Bajo | Mantener como output |
| `logs/preflight_validator_20260212.log` | 🔴 | No | **0 referencias** | Ninguno | Eliminar |
| `preflight_report.json` | 🟡 | No | Generado por `preflight_validator.py:195`; en `.dockerignore` | Ninguno | Eliminar del repo |
| `PayPal.png` (raíz `RUANA/`) | 🔴 | No | Duplicado; runtime usa `web/static/images/PayPal.png` | Ninguno | Eliminar |
| `publish-to-github.sh` | 🔴 | No | **0 referencias**; ruta Mac `/Users/alex/Desktop/RUANA` | Ninguno | Eliminar |
| `__init__.py` | 🟡 | No | Paquete | Bajo | Mantener |
| `README.md`, `MAPA_MENTAL_RUANA.md` | 🟡 | No | Documentación | Ninguno | Mantener |
| `docs/*.md` (3 en `RUANA/docs/`) | 🟡 | No | Documentación RUANA | Ninguno | Mantener |

---

## 3. Árbol de dependencias

### 3.1 Runtime web (producción)

```
gunicorn web.app:app
        │
        ▼
   web/app.py ─────────────────────────────────────────┐
        │                                                │
        ├── core/db_manager.py                           │
        │       ├── core/postgres_compat.py              │
        │       ├── core/settings.py                     │
        │       └── config/*.json (lectura)              │
        │                                                │
        ├── core/storage_manager.py                      │
        │       ├── core/supabase_client.py              │
        │       │       └── core/settings.py             │
        │       └── core/image_utils.py                  │
        │                                                │
        └── engines/motor_evaluacion.py                  │
                └── core/db_manager.py                   │
                                                         │
   HTML servidos por app.py:                             │
   index / register / invite / aliado / admin              │
        │                                                │
        ├── static/css/styles.css                        │
        ├── static/css/panel-premium.css (solo aliado)   │
        └── static/js/ruana-ui.js                        │
```

**Impacto:** eliminar `db_manager.py` rompe **todo** (app → 120+ endpoints → BD).  
Eliminar `motor_evaluacion.py` rompe `/api/admin/evaluaciones/<codigo>` (app.py L2714-2728).

### 3.2 Subsistema batch (desconectado del web)

```
python core/orquestador.py
        │
        ▼
core/orquestador.py
        ├── utils/logger.py
        ├── core/preflight_validator.py
        │       └── utils/logger.py
        ├── core/db_manager.py
        ├── engines/motor_evaluacion.py
        ├── metrics/collector.py
        └── events/event_bus.py
                └── logs/eventos_ruana.jsonl (escritura)
```

**Impacto:** eliminar `orquestador.py` **no rompe el servidor web**, pero rompe `python core/orquestador.py` y el pipeline batch documentado.

### 3.3 CI/QA

```
.github/workflows/ruana-qa.yml
        ├── python -m pytest RUANA/tests
        │       ├── RUANA.web.app
        │       └── core.db_manager
        └── npm run qa:e2e (playwright)
                └── invite.html, register.html
```

### 3.4 Imports estáticos de `app.py`

```python
from flask import Flask, render_template, jsonify, send_from_directory, request, session, redirect, url_for
from core.db_manager import get_db, DB_PATH, RUANA_CODIGO_INVITACION_REGEX
from core.settings import get_settings
from core.storage_manager import upload_ruana_file, upload_foto_perfil_file
from engines.motor_evaluacion import MotorEvaluacion  # también lazy en L2714
```

### 3.5 Imports estáticos de `orquestador.py`

```python
from utils.logger import setup_logger
from core.preflight_validator import run_preflight
from core.db_manager import get_db
from engines.motor_evaluacion import MotorEvaluacion
from metrics.collector import MetricsCollector
from events.event_bus import EventBus
```

### 3.6 Rutas HTML servidas por Flask

| Ruta Flask | Archivo servido |
|---|---|
| `/`, `/dashboard` | `index.html` |
| `/register`, `/register.html` | `register.html` |
| `/aliado`, `/aliado.html`, `/panel`, `/private-panel` | `aliado.html` |
| `/admin` | `admin.html` |
| `/invite`, `/invite.html` | `invite.html` |
| `/dashboard.html` | `dashboard.html` (redirige a aliado) |
| `/static/<path>` | `web/static/*` |

---

## 4. Lista de archivos eliminables (riesgo prácticamente nulo)

Verificación aplicada a cada uno: **0 imports Python, 0 referencias en HTML/JS activo, 0 rutas Flask que los sirvan, 0 tests, 0 CI.**

| # | Archivo | Por qué es eliminable | Evidencia |
|---|---|---|---|
| 1 | `RUANA/web/STATS.py` | Script informativo huérfano | 0 referencias en repo |
| 2 | `RUANA/web/static/js/referidos-module.js` | JS nunca cargado | 0 `<script src>`; 0 grep en `.html` |
| 3 | `RUANA/web/static/css/referidos-tree.css` | CSS nunca cargado | 0 `<link href>` |
| 4 | `RUANA/web/static/js/dashboard.js` | JS nunca cargado | `dashboard.html` solo redirige; 0 `<script>` |
| 5 | `RUANA/web/static/css/config.css` | CSS nunca cargado | 0 `<link>` en páginas activas |
| 6 | `RUANA/web/private-panel.html` | No servido | `app.py:993` sirve `aliado.html` |
| 7 | `RUANA/web/private-panel-new.html` | Sin ruta ni servicio | Sin `@app.route` |
| 8 | `RUANA/web/VERIFICACION_FLUJO.html` | Sin ruta Flask | Solo mención en README |
| 9 | `RUANA/PayPal.png` | Duplicado no referenciado | Runtime usa `web/static/images/PayPal.png` |
| 10 | `RUANA/publish-to-github.sh` | Script local Mac huérfano | 0 referencias; path `/Users/alex/Desktop/` |
| 11 | `RUANA/logs/preflight_validator_20260212.log` | Log histórico | 0 referencias |
| 12 | `RUANA/preflight_report.json` | Artefacto generado | Regenerable vía `preflight_validator.py:195`; en `.dockerignore` |

**Total: 12 archivos (~8% del repositorio).**

---

## 5. Lista de archivos dudosos

| Archivo / elemento | Qué falta comprobar | Referencias parciales |
|---|---|---|
| `orquestador.py` + subsistema batch | ¿Se ejecuta en cron/prod fuera de Cloud Run? | Usado solo por CLI; no por web |
| `events/event_bus.py`, `metrics/collector.py` | ¿Se necesita el JSONL de eventos en operación? | Solo vía orquestador |
| `dashboard.html` | ¿Algún bookmark externo usa `/dashboard.html`? | Ruta activa L999; solo redirect JS |
| `FIRST_RUN.py`, `QUICKSTART.py`, `INTEGRATION_EXAMPLES.py` | ¿Onboarding aún útil para el equipo? | Solo auto-referencias |
| `install.sh`, `install.bat` | ¿Usados en algún entorno? | Solo docs |
| `test_competencia_automatica.py`, `test_solicitud_grupo.py` | ¿Deben entrar en CI? | Fuera de `RUANA/tests/` |
| `ruana.db` | ¿Contiene datos reales o solo dev? | En repo; excluido de Docker |
| `static/uploads/pagos_ruana/*.png` | ¿URLs en BD de prod apuntan aquí? | Datos runtime |
| Rutas `app.py:312-337` | ¿Alguien accede a `/test-panel` etc.? | Apuntan a HTML **inexistentes** |
| `motor-ruana.js` (referenciado, no existe) | ¿Era dependencia de panel legacy? | `private-panel*.html` — archivos eliminables |
| Claves `capital`, `risk_per_trade_pct` en config | ¿Algún proceso externo las lee? | Solo orquestador stub |
| `SUPABASE_ANON_KEY` en `settings.py` | ¿Se usará en frontend futuro? | Definida L35,63; **nunca leída** en Python |
| Email `acerotrade.signal@gmail.com` | ¿Sigue siendo el PayPal operativo? | `aliado.html:4242` fallback activo |
| `README.md` L540 menciona `executors/`, `risk/`, `api_server.py` | Confirmar que nunca existieron en esta rama | No encontrados en filesystem |

---

## 6. Código muerto (lista completa verificada)

### 6.1 Imports muertos

| Ubicación | Símbolo | Evidencia |
|---|---|---|
| `app.py:7` | `render_template` | Importado; **0 llamadas** en 3988 líneas |

### 6.2 Rutas Flask a recursos inexistentes

| Ruta | Línea | Archivo esperado | Estado |
|---|---|---|---|
| `/test-panel` | `app.py:315` | `RUANA/test_panel.html` | **No existe** |
| `/diagnostico-panel` | `app.py:322` | `RUANA/diagnostico-panel.html` | **No existe** |
| `/test-simple` | `app.py:329` | `RUANA/test-simple.html` | **No existe** |
| `/panel-test` | `app.py:336` | `RUANA/panel-test.html` | **No existe** |

### 6.3 Referencias a assets inexistentes

| Referencia | Archivo | Línea |
|---|---|---|
| `/static/js/motor-ruana.js` | `private-panel.html` | 11 |
| `/static/js/motor-ruana.js` | `private-panel-new.html` | 8 |

### 6.4 Módulos JS/CSS huérfanos (archivos existentes, no cargados)

- `referidos-module.js` — 724 líneas, clase `RuanaReferidosTree` exportada L723; **0 carga**
- `dashboard.js` — 510 líneas, clase `RAUANADashboard`; **0 carga**
- `config.css`, `referidos-tree.css` — **0 carga**

### 6.5 Variables/config heredadas sin consumidor

| Elemento | Definido en | Consumido por | Estado |
|---|---|---|---|
| `capital` | `ruana_reglas_v1.json:3` | `orquestador.py:59` (solo log) | Muerto funcional |
| `risk_per_trade_pct` | `ruana_reglas_v1.json:4` | **Nadie** | Muerto |
| `ctrader_connected` | `orquestador.py:53` | **Nadie** | Muerto |
| `trades_ganadores/perdedores`, `pnl_total` | `orquestador.py:64-66` | **Nadie** | Muerto |
| `supabase_anon_key` | `settings.py:35` | **Nadie en Python** | Muerto (solo deploy env) |

### 6.6 Paquetes `__init__.py` sin consumidores

- `events/__init__.py` — re-export no importado (`from events import` = 0 resultados)
- `engines/__init__.py`, `metrics/__init__.py`, `utils/__init__.py` — paquetes vacíos

### 6.7 Código de ejemplo no ejecutable

- `INTEGRATION_EXAMPLES.py:431` — `from apscheduler...` (librería **no en requirements**)
- `INTEGRATION_EXAMPLES.py:334,354,371` — `from core.motor_evaluacion` (**ruta incorrecta**; el módulo real es `engines.motor_evaluacion`)

### 6.8 Funciones del motor usadas solo vía API

| Función | Archivo | Llamada desde |
|---|---|---|
| `MotorEvaluacion._evaluar_aliado` | `motor_evaluacion.py` | `app.py:2716` (lazy import) |
| `MotorEvaluacion._incorporar_persistencia` | `motor_evaluacion.py` | `app.py:2717` |
| `MotorEvaluacion.evaluate_all` | `motor_evaluacion.py` | `orquestador.py` (batch) |

---

## 7. Dependencias antiguas / sin uso

### 7.1 Python (`RUANA/web/requirements.txt`)

| Paquete | ¿Usado? | Evidencia |
|---|---|---|
| `Flask==2.3.3` | ✅ | `app.py`, `run.py` |
| `Flask-Cors==4.0.0` | ✅ | `app.py:21-50` |
| `Werkzeug==2.3.7` | ✅ | `storage_manager.py:14` |
| `PyJWT==2.8.0` | ✅ | `app.py:16,72,111,174,3177` |
| `gunicorn` | ✅ | `Dockerfile:17` (runtime, no import Python) |
| `python-dotenv` | ✅ | `settings.py:15-26` |
| `psycopg[binary,pool]` | ✅ | `postgres_compat.py:15`, `verify_supabase.py:11` |
| `supabase==2.16.0` | ✅ | `supabase_client.py:11` |
| `Pillow` | ✅ | `image_utils.py:7`, 4 tests |

**Resultado: ninguna dependencia pip declarada está sin uso en runtime/CI.**

### 7.2 Imports Python NO declarados en requirements (uso puntual)

| Módulo | Archivo | En requirements |
|---|---|---|
| `requests` | `test_solicitud_grupo.py:9` | ❌ |
| `apscheduler` | `INTEGRATION_EXAMPLES.py:431` (ejemplo) | ❌ |

### 7.3 npm (`package.json`)

| Paquete | ¿Usado? |
|---|---|
| `@playwright/test` | ✅ CI E2E |
| `firebase-tools` | ✅ deploy hosting |
| `supabase` | ✅ `supabase:push` script |

### 7.4 Variables de entorno

| Variable | Usada en código | Estado |
|---|---|---|
| `FLASK_SECRET_KEY` | ✅ `settings.py:38` | Activa |
| `DATABASE_URL` | ✅ `settings.py`, `postgres_compat.py` | Activa |
| `SUPABASE_URL` | ✅ `settings.py`, `supabase_client.py` | Activa |
| `SUPABASE_SERVICE_ROLE_KEY` | ✅ `supabase_client.py:23` | Activa |
| `SUPABASE_ANON_KEY` | ⚠️ Solo definida en `settings.py` | **No consumida** |
| `RUANA_DB_PATH` | ✅ `settings.py`, CI QA | Activa |
| `RUANA_ADMIN_SESSION_EXPIRES` | ✅ `app.py:53`, Dockerfile | Activa |
| `RUANA_ALIADO_SESSION_EXPIRES` | ✅ `app.py:56`, Dockerfile | Activa |

---

## 8. Plan de limpieza paso a paso

> **Nota:** este plan es recomendación documental. No se ejecutó durante la auditoría.

### Fase 0 — Baseline (antes de tocar nada)

1. Ejecutar `python -m pytest RUANA/tests -q` → guardar log.
2. Ejecutar `npm run qa:e2e` con servidor local.
3. Verificar `curl http://localhost:8080/api/health`.

### Fase 1 — Eliminación de archivos huérfanos (riesgo ~0)

| Paso | Eliminar | Por qué | Verificar después |
|---|---|---|---|
| 1.1 | `RUANA/web/STATS.py` | 0 referencias | pytest + arranque Flask |
| 1.2 | `referidos-module.js`, `referidos-tree.css` | 0 carga HTML | Panel referidos en `aliado.html` y `admin.html` |
| 1.3 | `dashboard.js`, `config.css` | 0 carga HTML | Navegación `/`, `/admin`, `/aliado` |
| 1.4 | `private-panel.html`, `private-panel-new.html`, `VERIFICACION_FLUJO.html` | No servidos | `GET /private-panel` sigue sirviendo `aliado.html` |
| 1.5 | `RUANA/PayPal.png` | Duplicado | Pagos en `aliado.html` (imagen en `static/images/`) |
| 1.6 | `publish-to-github.sh` | Script Mac obsoleto | Nada |
| 1.7 | `logs/preflight_validator_20260212.log`, `preflight_report.json` | Artefactos | `python core/preflight_validator.py` regenera report |

**Verificación RUANA:** pytest verde + smoke manual login aliado/admin + flujo invitación E2E.

### Fase 2 — Limpieza de código muerto (requiere edición)

| Paso | Qué | Por qué | Verificar |
|---|---|---|---|
| 2.1 | Eliminar rutas L312-337 en `app.py` | Apuntan a HTML inexistentes | 404 esperado en esas URLs o eliminar rutas |
| 2.2 | Quitar `render_template` de imports | Import muerto | Lint + pytest |
| 2.3 | Renombrar/eliminar stubs en `orquestador.py` L53-66 | Herencia AceroTrade | `python core/orquestador.py` |
| 2.4 | Eliminar claves `capital`, `risk_per_trade_pct` de config | No consumidas por RUANA web | Tests score/reglas |
| 2.5 | Reemplazar email `acerotrade.signal@gmail.com` | Herencia AceroTrade en UI | Flujo pago aliado |

### Fase 3 — Consolidación (dudosos)

| Paso | Qué | Comprobar |
|---|---|---|
| 3.1 | Decidir si batch (`orquestador.py`) sigue en prod | Logs operativos, cron jobs |
| 3.2 | Mover `test_*.py` raíz → `RUANA/tests/` | CI los recoja |
| 3.3 | Añadir `requests` a dev-requirements o eliminar `test_solicitud_grupo.py` | Consistencia deps |
| 3.4 | Cablear `referidos-module.js` **o** confirmar borrado (Fase 1) | Árbol referidos admin/aliado |
| 3.5 | Sacar `ruana.db` del control de versiones | `.gitignore` + `RUANA_DB_PATH` |

### Fase 4 — Verificación final

```bash
python -m pytest RUANA/tests -q
npm run qa:e2e
curl -s http://127.0.0.1:8080/api/health
python RUANA/scripts/verify_supabase.py   # si hay Supabase configurado
```

---

## 9. Hallazgos clave sobre AceroTradefinal

1. **No hay archivos ejecutables de trading** en el repositorio actual.
2. Los stubs de AceroTrade **ya fueron eliminados** (`risk_engine.py`, `executor.py`, `calculator.py` — solo mencionados en documentación).
3. La herencia restante es **estructural y nominal** (orquestador, claves config, un email, comentarios).
4. El sistema productivo RUANA gira en torno a: `app.py` → `db_manager.py` → HTML `aliado/admin` + APIs REST + Supabase Storage.
5. Hay **12 archivos demostrablemente eliminables** sin impacto en runtime; el resto de la deuda está en **código/rutas muertas dentro de archivos esenciales** (especialmente `app.py` y `orquestador.py`).

### Referencias textuales a AceroTradefinal en código

| Archivo | Línea | Contenido |
|---|---|---|
| `RUANA/core/orquestador.py` | 5 | `Estructura adaptada desde AceroTradefinal (sin lógica de trading)` |
| `RUANA/core/preflight_validator.py` | 5 | `Estructura adaptada desde AceroTradefinal` |
| `RUANA/utils/logger.py` | 5 | `Adaptado desde AceroTradefinal` |
| `RUANA/web/aliado.html` | 4242 | Fallback email `acerotrade.signal@gmail.com` |
| `RUANA/MAPA_MENTAL_RUANA.md` | 487 | Mención de stubs `risk_engine.py / executor.py / calculator.py` |

---

## 10. Apéndice: búsqueda de términos trading

Términos buscados en todo el repositorio (`.py`, `.html`, `.js`, `.css`, `.json`, `.md`, `.sql`, `.yml`):

| Término | Resultado en código RUANA |
|---|---|
| AceroTrade / AceroTradefinal | 4 coincidencias (comentarios + email + doc) |
| Binance | **0** |
| MetaTrader / MT5 | **0** (solo en hashes binarios de PNG) |
| forex | **0** |
| crypto (trading) | **0** (solo `pgcrypto` en SQL y paquetes npm) |
| backtest | **0** |
| telegram | **0** |
| TradingView | **0** |
| WebSocket (activo) | **0** (1 comentario futuro en `INTEGRATION_EXAMPLES.py:166`) |
| ctrader | 1 (`orquestador.py:53` stub) |
| capital | config + orquestador stub |
| risk_per_trade | config (sin consumidor) |
| EMA / RSI / MACD | **0** en código de aplicación |
| Stop Loss / Take Profit | **0** |
| velas / candle | **0** |
| posiciones / órdenes (trading) | **0** |
| bots | **0** |

---

## Metodología aplicada

Para cada archivo se verificó:

1. **¿Se importa?** — búsqueda de `import` y `from ... import` en los 63 archivos `.py`
2. **¿Quién lo utiliza?** — referencias a funciones, clases, constantes y rutas
3. **¿Se ejecuta indirectamente?** — registro en Flask, Blueprints, `__init__.py`, `app.py`, imports dinámicos, configuración, CI/CD, Docker
4. **Dependencias** — árbol de imports transitivos desde `app.py` y `orquestador.py`
5. **Clasificación** — 🟢 / 🟡 / 🔴 según evidencia demostrable
6. **Verificación de eliminabilidad** — solo 🔴 cuando: sin imports, sin referencias, sin llamadas, sin config, sin tests, sin ejecución indirecta

---

*Informe generado automáticamente como parte de la auditoría forense del repositorio RUANA.*
