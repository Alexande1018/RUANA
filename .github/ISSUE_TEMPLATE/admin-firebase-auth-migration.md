---
name: Epic — Migrar admin a Firebase Auth
about: Seguimiento de la migración del panel administrador a Firebase Authentication
title: "[Epic] Migrar panel admin a Firebase Authentication + roles en BD"
labels: security, admin, firebase
assignees: ''
---

## Contexto

El puente actual (GitHub Secret bootstrap → GCP Secret Manager → Cloud Run) resuelve la exposición de contraseñas en el repo. El panel ya puede persistir el cambio de contraseña en Secret Manager; sigue sin escalar para equipos ni roles.

**Plan completo:** `docs/superpowers/plans/2026-07-27-admin-firebase-auth-migration.md`

## Objetivo

- Login admin vía Firebase Authentication
- Permisos en tabla `admin_users` (Postgres/Supabase)
- Eliminar JSON de credenciales y secret `RUANA_ADMIN_CREDENTIALS_JSON`
- Cambio de contraseña instantáneo (Firebase), sin deploy

## Fases

- [ ] **A** — Infra: tabla `admin_users`, Firebase Admin SDK, script bootstrap
- [ ] **B** — Backend dual (`legacy` | `firebase`) con feature flag
- [ ] **C** — Frontend `/admin` con Firebase JS SDK
- [ ] **D** — Corte en producción y limpieza del puente

## Criterios de done

- [ ] Cero contraseñas admin en GitHub/GCP como JSON permanente
- [ ] Añadir moderador = usuario Firebase + fila en BD
- [ ] Tests CI + e2e con cuenta QA Firebase
- [ ] Documentación de alta/baja de admins

## Referencias

- Puente actual: `docs/seguridad/credenciales-admin.md`
- Código puente: `RUANA/core/admin_auth.py` (marcado como temporal)
