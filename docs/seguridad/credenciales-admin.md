# Credenciales admin en producción (puente temporal)

> **Autoridad:** [Manual Maestro §11–12](../../README.md#11-seguridad).  
> **Estado:** solución puente hasta migrar el panel admin a Firebase Authentication.  
> **Plan destino:** [Migración admin → Firebase Auth](../archive/superpowers/plans/2026-07-27-admin-firebase-auth-migration.md)

## Cómo funciona (sin gcloud manual)

```
Cursor genera JSON con hashes
        ↓
GitHub Secret: RUANA_ADMIN_CREDENTIALS_JSON  (una sola vez)
        ↓
Push a main → GitHub Actions
        ↓
Sincroniza Secret Manager (ruana-admin-credentials)
        ↓
Cloud Run monta RUANA_ADMIN_CREDENTIALS_JSON
        ↓
Login en /admin
```

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

El paso `Sync admin credentials to Secret Manager` actualizará GCP automáticamente.

## Desarrollo local

```bash
python RUANA/scripts/bootstrap_admin_credentials.py --legacy <archivo-legado.json>
# o
export RUANA_ADMIN_CREDENTIALS_PATH=.local-secrets/admin_credentials.json
```

## Limitaciones del puente (importante)

| Acción | Producción (puente) |
|--------|---------------------|
| Login admin | ✅ |
| Añadir otro admin | ❌ Editar JSON + nuevo deploy |
| Cambiar contraseña desde panel | ⚠️ No persiste de forma fiable en Cloud Run |
| Contratar moderador/soporte | ❌ Incómodo |

Por eso el destino es **Firebase Auth + roles en base de datos**.

## Rotar contraseña (mientras dure el puente)

1. Regenerar JSON con `generate_github_admin_secret.py`
2. Actualizar el secret `RUANA_ADMIN_CREDENTIALS_JSON` en GitHub
3. Push a `main` o re-ejecutar deploy

## Verificación

Tras el deploy:

```bash
curl -s https://ruana-4293f.web.app/api/health
```

Login en `https://ruana-4293f.web.app/admin` con identificador y contraseña configurados.
