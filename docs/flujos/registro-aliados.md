# Registro de aliados, oficios y plazas

> **Autoridad:** [Manual Maestro §5.4–5.5 y §6.2](../../README.md#54-grupos-y-plazas).  
> Original histórico (plaza por especialización): [`docs/archive/RUANA/FLUJO_REGISTRO_ALIADOS_OFICIOS.md`](../archive/RUANA/FLUJO_REGISTRO_ALIADOS_OFICIOS.md).

## Catálogo

- Archivo: `RUANA/config/oficios_ruana.json`.
- API: `GET /api/catalogo/oficios`, `/api/catalogo/oficios-raw`.
- El registro pide **oficio principal** obligatorio; las especializaciones pueden enviarse por compatibilidad de UI pero **no ocupan plaza**.

## Regla de plaza (código vigente)

**Una plaza = un oficio principal por grupo.**  
Comentario explícito en `aliado_service` / `grupo_service`: especializaciones ignoradas para la lógica de plaza.

`GET /api/grupos/especializaciones-disponibles` permanece como endpoint **deprecado** respecto a la plaza.

## Algoritmo al registrar (`POST /api/aliados/registrar` → `aliado_service`)

1. Validar nombre, email, teléfono (F07) y unicidad.
2. Generar código numérico de 5 dígitos; score inicial **50**.
3. Si oficio **fuera de catálogo** → `pendiente_validacion` (sin grupo).
4. Si oficio en catálogo:
   - Buscar grupo activo del CP con esa plaza libre → asignar `activo`.
   - Si no hay plaza pero hay &lt;5 grupos en el CP → crear grupo nuevo.
   - Si hay 5 grupos y el oficio está ocupado en todos → **`en_espera`** (suplente).
5. Consumir invitación si aplica (simple / oficio / campaña / crecimiento de grupo) y aplicar score/linaje.
6. El aliado recién creado **no tiene PIN**. El primer `POST /api/aliado/login` con solo código responde `pin_setup_required` + `setup_token`. Ver [`autenticacion-sesiones.md`](../seguridad/autenticacion-sesiones.md).

## Suplentes

- Estado `en_espera`: sin acceso al panel (login 403).
- Admin: `GET /api/admin/suplentes-espera`, `POST …/incorporar`.

## Validaciones F07

- `nombre`: obligatorio, ≥3 caracteres.
- `email`: obligatorio, con `@` y dominio con `.`.
- `telefono`: obligatorio, ≥7 dígitos.
- Email y teléfono únicos en `aliados`.
