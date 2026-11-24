# Piloto reversible «Red Huesca» (CP 22xxx)

Objetivo: que Amaury (84957, Grañén 22260) e Ionut (51724, Sariñena 22200) se
pasen encargos entre oficios aunque estén en grupos territoriales distintos,
sin mover su `grupo_id`. Es el mismo mecanismo que Red Centro, parametrizado
por una lista de prefijos de CP.

## Qué es (capa nueva y aislada)

| Pieza | Dónde |
|------|-------|
| Config + lógica | `RUANA/core/services/red_regional_service.py` (`REDES`, hoy solo `red_huesca` con prefijos `['22']`) |
| Rutas | `RUANA/web/blueprints/red_regional_bp.py` (`/api/admin/red-huesca/*`, `/api/aliado/red-huesca/aviso` y el aviso genérico `/api/aliado/red-regional/aviso`) |
| Gancho de reparto | `proximidad_service._escanear_candidatos` (después de la lógica actual y de Red Centro; solo si no hay nadie) |
| Gancho de alta | `aliado_bp.registrar_aliado` (best-effort, no bloquea) |
| Modal | `web/static/js/aliado-red-regional-module.js` (reutiliza el CSS de Red Centro) |
| Tablas | las mismas `red_piloto` / `red_piloto_miembros`, aisladas por `slug = red_huesca` |
| Instantánea (solo lectura) | `RUANA/scripts/red_regional_snapshot.py --slug red_huesca` |
| Tests | `RUANA/tests/test_red_huesca_piloto.py` |

**No modifica** `aliados`, `grupos`, plazas, score, competencia, pagos, comisiones,
negociación ni historial. **No toca Red Centro** (sigue con su servicio, flag,
rutas y 13 miembros). Zaragoza (50xxx) queda fuera de este PR.

## Flags

| Variable | Defecto | Efecto |
|----------|---------|--------|
| `RED_HUESCA_ENABLED` | `0` | Maestro. Apagado = no hay reparto por la red, no hay modal, `activar` responde 409. |
| `RED_HUESCA_AVISO_ENABLED` | `1` | Modal de bienvenida (solo si el maestro está encendido). |
| `RED_HUESCA_MAX_CANDIDATOS` | `3` | Tope de candidatos de la red que se consideran por encargo. |

## Elegibilidad

Aliado con `estado = 'activo'`, grupo territorial `activo`/`en_competencia` y CP
que cumple `22xxx (cinco dígitos que empiezan por 22)`. Hoy: 84957 y 51724. Quedan fuera otras provincias
(Madrid, Toledo, Zaragoza, etc.), `pendiente_validacion`, `en_espera`, sin
grupo. La incorporación es idempotente y automática: al activar, al registrarse,
al abrir el panel (GET del aviso) y al consultar el estado admin.

## Reparto de encargos

1. Profesional del oficio **en el propio grupo**.
2. Profesional cercano según la lógica actual (mismo CP / misma ciudad).
3. **Solo si 1 y 2 no encuentran a nadie** y el solicitante es elegible: el aliado
   de Red Huesca del **oficio pedido** más próximo, de entre como máximo
   `RED_HUESCA_MAX_CANDIDATOS`.

El solicitante ve la recomendación y decide. Nadie recibe nada hasta que acepta.
Nunca se reparte a todos. Fail-closed (en Postgres, `SAVEPOINT`).

## Operación (activar / revertir)

```bash
# 0. Instantánea de producción (solo lectura; NO versionar el fichero)
RUANA_ADMIN_PASSWORD=... python RUANA/scripts/red_regional_snapshot.py snapshot --slug red_huesca --out snap-huesca.json
# 1. Desplegar con el flag apagado, luego poner RED_HUESCA_ENABLED=1 en Cloud Run y:
POST /api/admin/red-huesca/activar        # admin con permiso escribir
GET  /api/admin/red-huesca                # estado, elegibles, miembros, operativa
# 2. Revertir
POST /api/admin/red-huesca/revertir       # borra SOLO miembros de red_huesca; verifica contra la instantánea
#    y poner RED_HUESCA_ENABLED=0
RUANA_ADMIN_PASSWORD=... python RUANA/scripts/red_regional_snapshot.py verify --snapshot snap-huesca.json
```

`revertir` comprueba primero que la instantánea guardada cuadra con su sha256
(si no, se niega). La fila de `red_piloto` se conserva como auditoría
(`estado = 'revertida'`). Altas, encargos y notificaciones generadas durante el
piloto no se tocan. Red Centro no se modifica.

Tras activar, 84957 sigue en el grupo 21 e 51724 en el 22; ambos aparecen como
miembros de Red Huesca con `operativa: true`.

## Añadir la próxima provincia (solo configuración)

En `RUANA/core/services/red_regional_service.py`, añade una entrada a `REDES`
(slug, nombre, `prefijos_cp`, zona y nombres de flags). Las rutas
`/api/admin/red-<slug>/*`, el modal genérico y los ganchos de alta/reparto
la recogen solos. El flag nuevo queda apagado hasta que se active. No hace falta
otro servicio. **En este PR solo está habilitado el prefijo 22.**

Red Centro no se ha migrado a este registro: está en producción y el
refactor solo se haría si se puede garantizar cero cambio de comportamiento
con la batería actual en verde.

## Redes provinciales (24 nov 2026)

`PROVINCIAS` en `red_regional_service.py` registra una red por provincia
(prefijo de CP = código INE), salvo 28/45 (Red Centro) y 22 (Red Huesca).
Slug `red_<provincia>` (p. ej. `red_sevilla`, rutas `/api/admin/red-sevilla/*`).
Su flag `RED_<PROVINCIA>_ENABLED` está **encendido si la variable no existe**
(`habilitada_por_defecto=True`), para no depender de editar el workflow; aun así
no hacen nada hasta `POST /api/admin/red-<provincia>/activar`. `POST .../revertir`
las neutraliza (sin red activa no hay reparto, ni alta, ni modal) aunque el flag
siga a 1. Para apagar del todo: añadir `RED_<PROVINCIA>_ENABLED=0` al deploy.
Los ganchos genéricos (alta, aviso, reparto) solo miran la red del CP del aliado.
