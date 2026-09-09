# Informe final: territorio directo por código postal

| | |
|---|---|
| Fecha | 2026-09-09 |
| Rama | `cursor/territorio-directo-cp-b288` |
| PR | https://github.com/Alexande1018/RUANA/pull/233 |
| Base | `main` (sin merge) |

---

## Decisión conservada

**Hasta 5 grupos territoriales independientes por código postal** (`MAX_GRUPOS_POR_CP = 5`). No se fusionan todos los aliados de un CP en un único grupo. Un aliado solo ve el directorio de **su** grupo. La proximidad recomienda un profesional cercano; no abre el directorio ajeno.

---

## Qué se eliminó

- Servicio y repositorio de Grupo Madre (`grupo_madre_service.py`, `grupo_madre_repo.py`).
- Alta en grupo madre, incubación, madurez (10 aliados / 3 encargos), independización, consolidación v2 real, aviso de bienvenida madre, directorio de ciudad compartido.
- Endpoints: `POST /api/aliado/grupo-madre/aviso-visto`, `GET /api/admin/grupos-madre`, `GET /api/admin/cp-madurez`, `GET /api/admin/cp-independencia/pendientes`, `POST .../aprobar`, `POST .../posponer`.
- KPIs admin `grupos_madre` y `cp_independencia_pendientes`.
- UI aliado: barras de madurez, modal de bienvenida, estado «Incubación».
- UI admin: tarjetas y tablas de madurez/independización.
- Constantes operativas `CP_MADUREZ_*`, `AVISO_GRUPO_MADRE` (ya no existen).
- Notificaciones nuevas de hitos de madurez / aliado nuevo en incubación.

## Qué se migró

- Aliados en grupo `tipo=madre` o CP `__MADRE__` → grupo territorial de su código postal.
- Backup en `migracion_territorio_backup` y casos en `migracion_territorio_informe`.
- Madres vacíos → `estado=disuelto` (no DELETE).
- Reverso: `territorio_migracion_service.revertir_migracion_territorio`.
- Arranque SQLite/Postgres: migración `territorio_directo_v1` (v2 consolidar es no-op).
- SQL no destructivo: `supabase/migrations/20260909000100_territorio_directo.sql`.

## Qué se conservó

- Perfiles, score, contratos, mensajes, acuerdos, pagos, invitaciones e historial.
- Columnas históricas `grupos.tipo`, `grupos.grupo_madre_id`, `cp_estado.*` (sin DROP).
- Auto-split de un **segundo** grupo territorial tras 10 elegibles en un CP **ya territorial**.
- Flujo de pagos y apoyo RUANA **12%** (sin cambios).
- Autenticación, competencia territorial, lista de espera por oficio ocupado.
- Formato de notificaciones históricas de madurez/independización en la cinta (solo lectura).

## Casos que requieren decisión manual

Registrados en `migracion_territorio_informe`, no se inventan datos:

| Caso | Acción |
|------|--------|
| `sin_codigo_postal` | Completar CP del aliado y reejecutar migración o asignar grupo a mano. |
| `ambiguedad_plaza` | Oficio ocupado en los 5 grupos del CP: plaza, nuevo grupo (si hay cupo) o suplente. |
| `grupo_madre_residual` | Quedan aliados en un grupo madre (los casos anteriores). No borrar el grupo. |

El administrador ve estos casos en `GET /api/admin/territorio/migracion-check`.

## Pruebas

Ejecutado: `python3 -m pytest RUANA/tests -q`

| Resultado | Detalle |
|-----------|---------|
| 1088 passed | Incluye pack territorial, proximidad, directorio, solicitud, cierre/pago 12%, admin, ausencia de lógica madre |
| 11 skipped | Ya existentes |
| 3 failed | `test_stripe_webhook_signature_http.py` — fallan en suite completa por contaminación de orden; **pasan en aislamiento** (4 passed). No están causados por este cambio. |

Pack Fase 3 (`test_territorio_directo.py` y tests reescritos de madre/auto-split/cinta/competencia/admin): **46 passed**.

## Riesgos que quedan

1. **Datos de producción:** la migración `territorio_directo_v1` corre al arrancar. Hacer backup de BD antes del despliegue. Es reversible vía tablas de backup; no ejecuta DROP.
2. **Aliados sin CP** no se mueven; hay que completar el dato.
3. **Varios grupos por CP:** un aliado no ve a profesionales del mismo CP en otro grupo; la proximidad cubre el oficio ausente.
4. **Solicitudes históricas** ligadas al grupo madre no se remapean (mezclaría CPs). Los aliados migrados operan en el nuevo grupo.
5. **Tests Stripe webhook** siguen siendo sensibles al orden de la suite; no forman parte de este cambio. CI de GitHub del PR (`03dfe30`) quedó **en verde** (2 comprobaciones).
6. **Verificación UI en navegador** no se ejecutó de punta a punta en este entorno; el contrato se cubrió con tests de API, HTML y módulos JS.

## Cómo revertir

```python
from core.services import territorio_migracion_service
territorio_migracion_service.revertir_migracion_territorio(db)
```

Restaura `grupo_id` de las filas `caso='migrado'` y reactiva el grupo anterior. No toca contratos ni pagos.
