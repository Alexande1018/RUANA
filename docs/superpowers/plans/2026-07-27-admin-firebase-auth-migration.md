# Plan: migrar autenticación del panel admin a Firebase Auth

**Estado:** preparado (no implementado)  
**Reemplaza:** `RUANA/core/admin_auth.py` + GitHub Secret `RUANA_ADMIN_CREDENTIALS_JSON`  
**Fecha:** 2026-07-27

## Objetivo

Unificar identidad del panel administrador con **Firebase Authentication** y permisos en **Postgres/Supabase**, eliminando:

- Archivos JSON de credenciales
- GitHub Secrets de contraseñas admin
- Redeploy para cambiar contraseña
- Sistema de auth paralelo al resto del producto

## Arquitectura destino

```
Firebase Authentication (email/contraseña o proveedor)
        │
        ▼
  ID Token (JWT Firebase)
        │
        ▼
Flask /api/admin/*  valida token con Firebase Admin SDK
        │
        ▼
Postgres: admin_users
  firebase_uid, email, rol, permisos[], activo
        │
        ▼
Panel /admin (sin admin_codes ni secrets)
```

## Qué NO cambia

- Rutas y contratos de `/api/admin/*` (mismas respuestas JSON)
- Permisos actuales: `leer`, `escribir`, `eliminar`, `configurar`
- Sesiones por pestaña (`X-Ruana-Session-Id`) — opcional mantener como capa UX tras login Firebase
- Autenticación de **aliados** (código RUANA) — fuera de alcance inicial
- Lógica de negocio en `db_manager.py`, pagos, invitaciones, etc.

## Esquema propuesto (Postgres)

```sql
CREATE TABLE admin_users (
    id              BIGSERIAL PRIMARY KEY,
    firebase_uid    TEXT NOT NULL UNIQUE,
    email           TEXT NOT NULL UNIQUE,
    nombre          TEXT NOT NULL DEFAULT '',
    rol             TEXT NOT NULL DEFAULT 'admin',
    permisos        JSONB NOT NULL DEFAULT '["leer"]',
    activo          BOOLEAN NOT NULL DEFAULT TRUE,
    creado_en       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    actualizado_en  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_admin_users_firebase_uid ON admin_users(firebase_uid);
CREATE INDEX idx_admin_users_activo ON admin_users(activo) WHERE activo = TRUE;
```

Roles futuros (`moderador`, `soporte`) = filas con distintos `permisos`, sin tocar infra.

## Fases de implementación

### Fase A — Infra y bootstrap (1 PR)

- [ ] Habilitar Email/Password en Firebase Console (si no está)
- [ ] Migración SQL `admin_users`
- [ ] `firebase-admin` en backend; validar ID tokens
- [ ] Script `bootstrap_admin_firebase.py`: crea usuario Firebase + fila en BD
- [ ] Variables: `FIREBASE_PROJECT_ID` (ya existe), credenciales de servicio vía secret GCP

### Fase B — Backend dual (1 PR, feature flag)

- [ ] `RUANA_ADMIN_AUTH_MODE=firebase|legacy` (default `legacy` en transición)
- [ ] Nuevo endpoint `POST /api/admin/validar-firebase` { id_token }
- [ ] `_admin_session_valid()` acepta sesión legacy O Firebase
- [ ] Tests con tokens mock

### Fase C — Frontend admin (1 PR)

- [ ] Login `/admin` con Firebase JS SDK
- [ ] Eliminar campos identificador/contraseña legacy del modal
- [ ] Cambio de contraseña vía `sendPasswordResetEmail` o Firebase `updatePassword`
- [ ] Retirar “Cambiar contraseña” que escribe en archivo local

### Fase D — Corte y limpieza (1 PR)

- [ ] `RUANA_ADMIN_AUTH_MODE=firebase` en producción
- [ ] Eliminar `admin_auth.py`, GitHub Secret, paso sync en CI
- [ ] Eliminar `generate_github_admin_secret.py` y docs del puente
- [ ] Documentar alta de moderadores en Firebase Console + INSERT en `admin_users`

## Criterios de aceptación

1. Login admin en producción sin `RUANA_ADMIN_CREDENTIALS_JSON`
2. Cambiar contraseña desde Firebase o panel sin redeploy
3. Añadir moderador = usuario Firebase + fila BD (sin editar secrets)
4. Tests CI verdes; e2e admin con cuenta QA Firebase
5. Cero contraseñas en repositorio

## Riesgos y mitigación

| Riesgo | Mitigación |
|--------|------------|
| Bloqueo si Firebase cae | Mantener modo dual hasta validar en prod |
| Pérdida de acceso al migrar | Bootstrap script + usuario de emergencia en Firebase |
| Complejidad tokens en Flask | Librería oficial `firebase-admin` |

## Issue de seguimiento

Título sugerido: **Migrar panel admin a Firebase Authentication + roles en BD**

Etiquetas: `security`, `admin`, `firebase`, `epic`
