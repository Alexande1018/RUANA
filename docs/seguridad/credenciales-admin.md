# Credenciales admin en producción (puente temporal)

> **Autoridad:** [Manual Maestro §11–12](../../README.md#11-seguridad).  
> **Estado:** solución puente hasta migrar el panel admin a Firebase Authentication.  
> **Plan destino:** [Migración admin → Firebase Auth](../archive/superpowers/plans/2026-07-27-admin-firebase-auth-migration.md)

## Cómo funciona (sin gcloud manual)

```
Cursor genera JSON con hashes
        ↓
GitHub Secret: RUANA_ADMIN_CREDENTIALS_JSON  (bootstrap / rotación forzada)
        ↓
Primer deploy → GitHub Actions crea el secreto GCP si no existe
        ↓
Secret Manager (ruana-admin-credentials)  ← fuente de verdad en runtime
        ↓
Cloud Run monta RUANA_ADMIN_CREDENTIALS_JSON
        ↓
Login / cambio de contraseña en /admin
        ↓
El panel añade una nueva versión en Secret Manager
```

El JSON de GitHub **no se vuelve a copiar** a Secret Manager en cada deploy. Así un cambio de contraseña desde el panel sobrevive al siguiente push a `main`.

## Configuración única (≈2 minutos)

### 1. Generar el JSON (Cursor o local)

```bash
python RUANA/scripts/generate_github_admin_secret.py \
  --admin-id 7772735 \
  --password 'TU_CONTRASEÑA'
```

La salida es **solo hashes** (seguro para pegar en GitHub).

### 2. Crear el secret en GitHub

1. Repositorio → **Settings** → **Secrets and variables** → **Actions**
2. **New repository secret**
3. Nombre: `RUANA_ADMIN_CREDENTIALS_JSON`
4. Valor: pegar el JSON completo (una línea)

### 3. Desplegar

Haz push a `main` o ejecuta el workflow **Deploy to Firebase** manualmente.

El paso `Sync admin credentials to Secret Manager`:

- crea el secreto GCP si aún no existe;
- concede `secretAccessor` y `secretVersionAdder` a `ruana-runner`;
- **no** pisa un secreto ya existente (salvo rotación forzada).

## Desarrollo local

```bash
python RUANA/scripts/bootstrap_admin_credentials.py --legacy <archivo-legado.json>
# o
export RUANA_ADMIN_CREDENTIALS_PATH=.local-secrets/admin_credentials.json
```

`RUANA/config/admin_credentials.qa.json` (ADMIN001 / 0000) es **solo QA/CI**. No se copia a la imagen Docker y no se usa como fallback en producción.

## Limitaciones del puente (importante)

| Acción | Producción (puente) |
|--------|---------------------|
| Login admin | ✅ |
| Cambiar contraseña desde panel | ✅ Persiste en Secret Manager |
| Añadir otro admin | ❌ Editar JSON + rotación forzada, o nuevo deploy con secreto nuevo |
| Contratar moderador/soporte | ❌ Incómodo |

Por eso el destino es **Firebase Auth + roles en base de datos**.

Instancias Cloud Run ya arrancadas siguen con el JSON inyectado al nacer hasta reciclarse; el proceso que ejecutó el cambio actualiza también su caché local y el env. Las instancias nuevas leen `:latest` de Secret Manager.

## Rotar contraseña

### Desde el panel (recomendado)

En `/admin` → cambiar contraseña. Se añade una versión nueva en Secret Manager.

### Desde GitHub (recuperación / bootstrap)

1. Regenerar JSON con `generate_github_admin_secret.py`
2. Actualizar el secret `RUANA_ADMIN_CREDENTIALS_JSON` en GitHub
3. Ejecutar **Deploy to Firebase** con `force_admin_credentials_sync = true`

## Verificación

Tras el deploy:

```bash
curl -s https://ruana-4293f.web.app/api/health
```

Login en `https://ruana-4293f.web.app/admin` con identificador y contraseña configurados.
