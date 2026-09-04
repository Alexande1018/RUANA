# Informe interno de auditoría documental RUANA

> **HISTÓRICO.** Sustituido por [`AUDITORIA_DOCUMENTAL_2026-09-04.md`](AUDITORIA_DOCUMENTAL_2026-09-04.md).  
> Conservar como evidencia. No usar cifras de este informe (13 blueprints, 16 services, login solo-código, 12 migraciones, 383 tests) como descripción del código actual.

**Fecha:** 2026-08-15  
**Alcance:** repositorio completo (`/workspace`)  
**Método:** inventario documental + inspección de código, configuración, migraciones y tests  
**Principio:** el código y la configuración actuales son la fuente de verdad  

---

## 1. Estado actual (resumen objetivo)

RUANA es una aplicación web **Flask 2.3** con frontend **HTML/CSS/JS vanilla**, desplegada en **Google Cloud Run** (`europe-west1`) con entrada pública vía **Firebase Hosting** (`ruana-4293f.web.app`). La persistencia es **dual**: Postgres (Supabase) en producción cuando `DATABASE_URL` está definida, o **SQLite** en local/CI.

El dominio de negocio está organizado en **16 services** y **16 repositories** bajo `RUANA/core/`, con `DBManager` (~1.835 líneas) actuando como **fachada de compatibilidad** que delega en services. El enrutado HTTP está repartido en **13 blueprints** (~166 rutas) más ~27 rutas en `app.py` (HTML, estáticos, auth admin legacy).

**Roles:** aliado (login por código de 5 dígitos, sin contraseña), administrador (ID + contraseña hasheada en JSON/Secret Manager). Sesiones por pestaña vía JWT + `X-Ruana-Session-Id` + `sessionStorage`.

**Flujos centrales verificados:** registro territorial (grupos/CP/plazas), solicitudes de grupo, contactos/encargos, negociación guiada (sustituye chat libre en UI), Apoyo RUANA manual y opcionalmente Stripe Connect, score 0–500, competencia automática por umbral, invitaciones/referidos/campañas, panel admin operativo.

**Tests:** 383 tests pytest pasando en esta auditoría (`python3 -m pytest RUANA/tests -q`). CI automático en push/PR a `main`/`dev`.

---

## 2. Arquitectura real

```text
Navegador (HTML/JS vanilla, RUANA/web/)
        │
        ▼
Firebase Hosting → rewrite ** → Cloud Run "ruana"
        │
        ▼
gunicorn → web.app:app (455 líneas)
        ├── Middleware /api/admin/* (excepto login/logout/health)
        ├── Rutas HTML (~20) + estáticos
        ├── POST /api/admin/validar|logout|cambiar-contraseña
        └── 13 Blueprints (~166 rutas API)
              ├── auth_decorators (require_aliado / require_admin / require_admin_escritura)
              └── get_db() → DBManager (fachada)
                    └── core/services/<dominio>_service.py
                          └── core/repositories/<dominio>_repo.py
                                └── SQLite | Postgres (postgres_compat.py)
        │
        ├── Supabase Storage (fotos, comprobantes, QR)
        ├── SMTP (email bienvenida)
        └── Stripe Connect (opcional, RUANA_STRIPE_PAYMENTS_ENABLED)
```

| Componente | Ubicación | Notas |
|------------|-----------|-------|
| Blueprints | `RUANA/web/blueprints/` (13) | admin, aliado, auth, catalogo, contactos, evaluacion, invitacion, negociacion, pagos, referidos, solicitudes, soporte, stripe_webhook |
| Services | `RUANA/core/services/` (16) | Lógica de negocio |
| Repositories | `RUANA/core/repositories/` (16) | SQL real (74–768 líneas/archivo) |
| Motores | `RUANA/engines/motor_evaluacion.py` | v0.2; umbrales hardcodeados + deltas desde JSON |
| Orquestador | `RUANA/core/orquestador.py` | CLI demo; **no cableado a Flask** |
| Eventos / métricas | `RUANA/events/`, `RUANA/metrics/` | Infraestructura presente; uso productivo limitado |
| Migraciones PG | `supabase/migrations/` (12 archivos) | RLS, storage buckets, compat SQLite |
| Schema runtime | `schema_service.py` | Init SQLite completo + parches Postgres parciales |

---

## 3. Funcionalidades verificadas

| Dominio | Evidencia |
|---------|-----------|
| Registro aliados | `aliado_service`, `POST /api/aliados/registrar`, `register.html` |
| Login aliado/admin | `auth_session.py`, `auth_bp`, `app.py` |
| Grupos / CP / plazas | `grupo_service`, `MAX_GRUPOS_POR_CP=5`, `db_constants.py` |
| Suplentes `en_espera` | `aliado_service`, `admin_bp` suplentes-espera |
| Solicitudes | `solicitud_service`, `solicitudes_bp` |
| Contactos / encargos | `contacto_service`, `contactos_bp` |
| Negociación guiada | `negociacion_service`, `negociacion_bp`, UI `negociacion-guiada.js` |
| Chat mensajes (legado) | `chat_service` + tablas; rutas globales legacy → **410** |
| Apoyo RUANA manual | `pago_service`, `apoyo_pct=12.0` en `ruana_reglas_v1.json` |
| Stripe Connect | `stripe_client.py`, `pagos_bp`, `stripe_webhook_bp`, tests `test_stripe_*` |
| Score 0–500, ±10/día | `score_service`, `score_repo` |
| Competencia automática | `competencia_service.procesar_competencia_automatica` |
| Purga mensual | `competencia_service.purga_mensual`, `POST /api/purga/mensual` |
| Invitaciones / campañas / referidos | `invitacion_service`, `referido_service` |
| Notificaciones | `notificacion_service` |
| Centro comunicación (soporte) | `soporte_bp` |
| Panel admin | `admin_bp` (51 rutas) |
| Motor evaluación (consulta) | `GET /api/admin/evaluaciones/<codigo>` calcula vía motor si no hay fila |
| Deploy CI/CD | `.github/workflows/deploy-firebase.yml`, `ruana-qa.yml` |
| Catálogo 39 oficios | `oficios_ruana.json` |

---

## 4. Funcionalidades documentadas pero no verificadas

| Afirmación en docs | Estado |
|--------------------|--------|
| Firebase Authentication para admin | Plan en archive; **no implementado** en código Python |
| Supabase Realtime en cliente web | Publication en migración; **uso en frontend no verificado** |
| Purga mensual ejecutándose en producción | Lógica + endpoint existen; **cron operativo no verificado** (`scripts/cron_purga_mensual.txt` es plantilla) |
| `profiles` / `auth.users` en login Flask | Tabla en migración PG; **login no usa Supabase Auth** |
| Motor evaluación como proceso automático periódico | Motor existe; **no hay job/cron HTTP verificado** (solo consulta admin + CLI orquestador) |
| Rollback Cloud Run documentado como procedimiento | **No verificado** en repo más allá de redeploy |
| Email PayPal operativo (`acerotrade.signal@gmail.com`) | Mención solo en archive forense |

---

## 5. Funcionalidades implementadas pero poco o mal documentadas

| Funcionalidad | Evidencia |
|---------------|-----------|
| 13 blueprints (no 2) | `RUANA/web/blueprints/*.py` |
| Stripe Connect completo | `pagos_bp`, webhook, onboarding aliado |
| Repositories con SQL real (16) | Todos los `*_repo.py` tienen consultas sustanciales |
| `competencia_pendiente` (cola retadores) | `competencia_service`, schema SQLite |
| Negociación como flujo principal de encargo | UI + API; chat libre devuelve 410 |
| E2E actualizado a negociación | `e2e/ruana-critical-flows.spec.js` usa `#modal-negociacion-guiada` |
| Variables Stripe en `.env.example` | Líneas 45–51 |
| Aliado Stripe onboarding | `POST /api/aliado/stripe/onboarding` |
| Conflictos pago Stripe | `payment_conflicts` + resolución admin |
| `aliados_eliminados` archivo | Migración + admin API |
| Catálogo servicios aliado (10 posiciones) | `catalogo_servicios_aliado` |
| Urgencia en contactos | `es_urgente`, `urgente_marcado_en` |

---

## 6. Contradicciones importantes (doc anterior vs código)

| ID | Documentación anterior | Código actual | Clasificación |
|----|------------------------|---------------|---------------|
| C1 | README: solo 2 blueprints (`catalogo`, `negociacion`) | 13 blueprints registrados en `app.py` | **OBSOLETO** |
| C2 | README: `app.py` ~170 rutas, ~4.331 LOC `db_manager` | `app.py` 455 líneas; `db_manager` 1.835 líneas | **OBSOLETO** |
| C3 | README: repos casi todos stub; solo `score_repo` con SQL | 16 repos con 74–768 líneas de SQL cada uno | **INCORRECTO** |
| C4 | README: Stripe / pasarela API «no integrado» | Stripe Connect implementado; flag `RUANA_STRIPE_PAYMENTS_ENABLED` | **INCORRECTO** |
| C5 | README: E2E desfasado (selectores chat) | E2E usa negociación guiada (`#modal-negociacion-guiada`) | **OBSOLETO** |
| C6 | README: admin con permisos vacíos obtiene conjunto completo | `require_admin` no filtra por permisos; `require_admin_escritura` exige `escribir`/`configurar` → vacío = lectura sin escritura | **INCORRECTO** (matiz) |
| C7 | `chat-y-alerta.md`: APIs chat activas sin matiz | Rutas legacy `/api/chat_enviar` etc. → **410** en `negociacion_bp` | **AMBIGUO** → corregido |
| C8 | Schema: `comision_porcentaje DEFAULT 0.05` | Runtime usa `apoyo_pct/100` (= 0.12 con config actual) | **DISCREPANCIA** schema vs runtime |
| C9 | PG migración `ingresos_ruana.apoyo_ruana_2pct` vs `contactos_ruana.apoyo_ruana` | Nombres distintos en tablas | **DUPLICADO / inconsistente** |
| C10 | `competencia.suplente_*` vs `retador_*` | Migración renombra; código tiene compat | **OBSOLETO** en docs que digan suplente |
| C11 | `referidos.origen` en backfill PG | Columna creada en SQLite runtime, no en migración Supabase | **DISCREPANCIA** SQLite/PG |
| C12 | README auditoría 2026-08-11 | Estado cambió (blueprints, repos, Stripe) | **OBSOLETO** |

---

## 7. Información obsoleta

- `docs/archive/README_RUANA_COMPLETO.md` — describe arquitectura pre-blueprints masivos.
- `docs/archive/RUANA/LOGICA_CHAT_Y_ALERTA.md` — límite 5 mensajes (corregido a 30 en código).
- `RUANA/docs/*.md` (excepto README punteros) — redirigen a `docs/` o archive.
- README sección «Blueprints parciales (solo 2)».
- README «repos stub».
- README «Stripe no integrado».
- Afirmación E2E desfasado por chat.
- `RUANA/ruana.db` commiteado — snapshot antiguo (25 tablas, columnas legacy).

---

## 8. Riesgos

### Críticos

| Riesgo | Ubicación | Impacto |
|--------|-----------|---------|
| Login aliado = código único (sin 2FA) | `auth_bp` | Compromiso de código = acceso total |
| Service role Supabase bypasea RLS | Backend Flask | Autorización depende 100% de la API |
| Datos de cobro en repo versionado | `ruana_reglas_v1.json` (bizum, IBAN) | Exposición de datos operativos |
| Cloud Run acceso público | `deploy-firebase.yml` | Superficie expuesta; auth solo aplicación |

### Importantes

| Riesgo | Ubicación | Impacto |
|--------|-----------|---------|
| Drift SQLite ↔ Postgres | `schema_service` vs `supabase/migrations/` | Tablas/columnas pueden faltar en PG sin `_init_postgres_schema` |
| Revocación sesión en memoria | `auth_session.py` | Multi-instancia: revoke no global |
| Admin credenciales JSON puente | `admin_auth.py` | Rotación manual; cambio contraseña panel no persistente en Cloud Run |
| Motor evaluación no automatizado | Sin cron | Evaluaciones persistidas solo si se invoca motor |
| `bundled ruana.db` desactualizado | `RUANA/ruana.db` | Confusión en desarrollo si se usa sin init |
| Permisos admin: lectura sin restricción | `require_admin` | Cualquier admin autenticado lee todo el panel |

---

## 9. Documentación que debe modificarse

| Archivo | Cambio |
|---------|--------|
| `/README.md` | Actualizar arquitectura, blueprints, repos, Stripe, métricas LOC, permisos admin, E2E, fecha auditoría |
| `docs/flujos/chat-y-alerta.md` | Aclarar 410 en rutas legacy; negociación como flujo principal |
| `docs/flujos/registro-aliados.md` | Referencias a services (no `app.py`/`db_manager` monolito) |
| `docs/qa/plan-testing.md` | 383 tests, CI automático, E2E negociación |
| `docs/operaciones/roadmap.md` | Stripe hecho, Campamento Base avanzado |
| `docs/README.md` | Enlace a este informe |

---

## 10. Documentación que debe eliminarse

**Ninguna.** El archive se conserva como evidencia histórica con punteros a versiones vigentes. Los stubs en `RUANA/docs/` ya redirigen correctamente.

---

## 11. Documentación que debería crearse

| Necesidad | Justificación |
|-----------|---------------|
| `docs/referencia/api-endpoints.md` (opcional futuro) | 193 rutas; hoy no existe índice machine-readable. **No creado en esta auditoría** para evitar duplicar README + riesgo de desactualización rápida. |
| Procedimiento operativo purga/cron | Existe lógica pero no runbook verificado. **Pendiente decisión humana.** |

---

## 12. Valores críticos verificados

| Parámetro | Valor | Fuente |
|-----------|------:|--------|
| `MAX_GRUPOS_POR_CP` | 5 | `db_constants.py` |
| Score inicial registro | 50 | `aliado_service` |
| Score rango | 0–500, tope ±10/día | `score_service` |
| Umbral competencia | 15 | `ruana_reglas_v1.json` |
| Reinicio score tras derrota | 50 | `ruana_reglas_v1.json` |
| Duración competencia | 30 días | `ruana_reglas_v1.json` |
| `apoyo_pct` | 12.0 % | `ruana_reglas_v1.json` |
| `posponer_horas` | 24 | `ruana_reglas_v1.json` |
| Purga: meses sin ganar | 3 | `ruana_reglas_v1.json` |
| Purga: score bajo | 40 | `ruana_reglas_v1.json` |
| Chat max mensajes | 30 | `db_manager.CHAT_MAX_MENSAJES_TOTAL` |
| Chat vigencia | 48 h | `db_manager.CHAT_HORAS_VIGENCIA` |
| Oficios catálogo | 39 | `oficios_ruana.json` |
| Motor: tasa_respuesta mín | 0.70 | `motor_evaluacion.py` (hardcoded) |
| Motor: tasa_confirmacion mín | 0.80 | `motor_evaluacion.py` (hardcoded) |
| Motor: meses_sin_trabajo máx | 6 | `motor_evaluacion.py` (hardcoded) |
| `comision_porcentaje` DDL default | 0.05 | `schema_service.py` |
| `comision_porcentaje` en runtime cierre | `apoyo_pct/100` (=0.12) | `contacto_service.py` |

---

## 13. Automatización verificada

| Regla | Disparador | Componente | Automático |
|-------|------------|------------|------------|
| Competencia por score bajo | Cambio score / procesamiento | `competencia_service.procesar_competencia_automatica` | Sí (en flujos que lo invocan) |
| Cola competencia pendiente | Plaza libre + retador | `competencia_service._procesar_competencias_pendientes` | Sí |
| Finalizar competencias vencidas | Endpoint admin / manual | `finalizar_competencia_activas_vencidas` | Manual vía API |
| Purga mensual | `POST /api/purga/mensual` | `competencia_service.purga_mensual` | Manual (no cron verificado) |
| Apoyo al cerrar importe coincidente | Declaración importe | `contacto_service` | Sí |
| Penalizaciones score | Eventos contacto/chat | `score_service` | Sí (reglas 3–8 con tests) |
| Motor evaluación persistencia | `evaluate_all()` | `motor_evaluacion.py` | Solo si se invoca (no cron) |
| Stripe webhook cobros | Evento Stripe | `stripe_webhook_bp` | Sí (si habilitado) |
| Email bienvenida | Registro | `email_service` | Sí (si SMTP configurado) |

---

## 14. Decisiones pendientes (humanas)

1. ¿Activar `RUANA_STRIPE_PAYMENTS_ENABLED` en producción de forma permanente?
2. ¿Migrar admin a Firebase Auth (plan existe desde 2026-07)?
3. ¿Sincronizar completamente migraciones Supabase con `schema_service` SQLite?
4. ¿Programar purga mensual y motor evaluación vía Cloud Scheduler?
5. ¿Retirar `RUANA/ruana.db` del repo o regenerarlo en CI?
6. ¿Eliminar datos de cobro reales de `ruana_reglas_v1.json` del repositorio?
7. ¿Documentar API como OpenAPI o mantener README como índice?

---

## 15. Segunda pasada de consistencia

Verificada coherencia post-actualización entre:
- README ↔ blueprints count ↔ LOC reales
- README ↔ Stripe integrado ↔ `.env.example`
- README ↔ 383 tests ↔ `ruana-qa.yml`
- chat-y-alerta ↔ 410 legacy ↔ negociación vigente
- apoyo_pct 12 % ↔ runtime ↔ tests (`comision_porcentaje == 0.12`)
- score bandas ↔ `score_service.score_a_estado`
- E2E ↔ negociación (no chat modal)

Pendiente de reconciliar sin decisión humana:
- `comision_porcentaje` DDL default 0.05 vs runtime 0.12
- Drift tablas PG-only vs SQLite-only
- Nombre columna `apoyo_ruana` vs `apoyo_ruana_2pct` en `ingresos_ruana`

---

*Fin del informe interno. Las actualizaciones documentales derivadas están en el commit asociado a esta auditoría.*
