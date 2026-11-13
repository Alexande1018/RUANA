# Piloto reversible «Red Centro» (Madrid + Toledo)

Objetivo: que los aliados de la Comunidad de Madrid (CP `28xxx`) y de la provincia
de Toledo (CP `45xxx`) se pasen encargos entre oficios aunque estén en grupos
territoriales distintos, sin tocar su organización original.

## Qué es (capa nueva y aislada)

| Pieza | Dónde |
|------|-------|
| Lógica | `RUANA/core/services/red_centro_service.py` |
| Rutas | `RUANA/web/blueprints/red_centro_bp.py` |
| Gancho de reparto | `proximidad_service._escanear_candidatos` (solo si la lógica actual no encuentra a nadie) |
| Gancho de alta | `aliado_bp.registrar_aliado` (best-effort, no bloquea) |
| Modal | `web/static/js/aliado-red-centro-module.js` + `web/static/css/aliado-red-centro.css` |
| Tablas nuevas | `red_piloto` (estado + instantánea + sha256), `red_piloto_miembros` (miembros + aviso visto) |
| Instantánea de producción (solo lectura) | `RUANA/scripts/red_centro_snapshot.py` |
| Tests | `RUANA/tests/test_red_centro_piloto.py` |

El piloto **solo escribe** en `red_piloto` y `red_piloto_miembros`. No modifica
`aliados`, `grupos`, plazas, score, competencia, pagos, comisiones, negociación
ni historial (hay tests que vuelcan todas las demás tablas antes y después).

## Flags

| Variable | Defecto | Efecto |
|----------|---------|--------|
| `RED_CENTRO_ENABLED` | `0` | Maestro. Apagado = no hay reparto por la red, no hay modal, `activar` responde 409. |
| `RED_CENTRO_AVISO_ENABLED` | `1` | Modal de bienvenida (solo si el maestro está encendido). |
| `RED_CENTRO_MAX_CANDIDATOS` | `3` | Tope de candidatos de la red que se consideran por encargo. |

## Elegibilidad

Aliado con `estado = 'activo'`, con grupo territorial `activo`/`en_competencia` y
CP que cumple `^(28|45)\d{3}$`. Quedan fuera `pendiente_validacion`, `en_espera`
(suplentes), sin grupo y cualquier otra provincia. La incorporación es idempotente
(`UNIQUE(red_id, aliado_codigo)`) y automática: al activar, al registrarse, al abrir
el panel (GET del aviso) y al consultar el estado admin.

## Reparto de encargos

1. Profesional del oficio **en el propio grupo** (sin cambios → exclusividad local intacta).
2. Profesional cercano según la lógica actual (mismo CP / misma ciudad).
3. **Solo si 1 y 2 no encuentran a nadie** y el solicitante es elegible: el aliado de
   Red Centro del **oficio pedido** más próximo (misma provincia primero, luego
   heurística de distancia entre CP), de entre como máximo `RED_CENTRO_MAX_CANDIDATOS`.

Se mantiene el flujo actual: el solicitante ve la recomendación y decide
(«Aceptar a …», «Pedir al grupo que recomienden a alguien», «Invita a alguien…»).
Nadie recibe nada hasta que acepta; entonces solo el elegido. Nunca se reparte a todos.
La búsqueda usa el cursor del llamador (sin conexión anidada) y en Postgres va en un
`SAVEPOINT`: si falla, devuelve vacío y el encargo sigue por el camino actual.

## Notificaciones (cómo funcionan de verdad)

* Canal real: **bandeja in-app** (`notificaciones_aliado`). No hay push. El email solo
  existe para bienvenida y «Encargos de RUANA» (SMTP, sin acuse de entrega).
* `notificacion_service.crear_notificacion_aliado` **traga excepciones y no devuelve
  nada**; `encargo_externo_service.notificar_aliado` marca `app=True` aunque la
  inserción haya fallado. No se ha cambiado (fuera de alcance), pero se documenta.
* El piloto trae `entregar_notificacion_verificada`, que solo devuelve
  `entregada=True` si la fila se puede leer de vuelta. **No está cableada a ninguna
  ruta ni cron**: no hay envío masivo. El canal principal es el modal.
* Plantilla: `GET /api/admin/red-centro/plantilla-notificacion`.

## Modal de bienvenida

* `GET /api/aliado/red-centro/aviso` → `{mostrar: bool}` (incorpora si es elegible).
* `POST /api/aliado/red-centro/aviso {accion: cerrar|aceptar|recomendar|invitar}` →
  guarda `aviso_red_centro_visto_at` + acción en `red_piloto_miembros` (solo la primera vez).
* Se ve una sola vez por aliado aunque cambie de dispositivo o cierre sesión.
* «Recomendar trabajo» abre «Nueva conexión» (`AliadoShell.show('conexiones')`).
  «Invitar aliado» pulsa el botón existente «Ampliar mi red» (`#btn-invitar-global`).
* Fail-open: cualquier error = no se muestra.

> Nota de nombres: en la app no hay botones literalmente llamados «Recomendar» ni
> «Invitar». Los reales son «Nueva conexión» / «Conozco a alguien» (recomendar un
> encargo) y «Ampliar mi red» / «Invitar a un profesional» (invitar).

## Operación

```bash
# 0. Instantánea de producción (solo lectura; NO versionar el fichero)
RUANA_ADMIN_PASSWORD=... python RUANA/scripts/red_centro_snapshot.py snapshot --out snap.json
# 1. Activar: RED_CENTRO_ENABLED=1 en Cloud Run y después
POST /api/admin/red-centro/activar        # admin con permiso escribir
GET  /api/admin/red-centro                # estado, elegibles, miembros
# 2. Revertir
POST /api/admin/red-centro/revertir       # borra SOLO miembros; verifica contra la instantánea
#    y poner RED_CENTRO_ENABLED=0
RUANA_ADMIN_PASSWORD=... python RUANA/scripts/red_centro_snapshot.py verify --snapshot snap.json
```

`revertir` comprueba primero que la instantánea guardada cuadra con su sha256
(si no, se niega). Devuelve `identica`, `diferencias`, `checksum_original`,
`checksum_actual_subconjunto` (igual al original si no ha cambiado nada) y las
altas nuevas conservadas. La fila de `red_piloto` se conserva como auditoría
(`estado = 'revertida'`). Altas, encargos, solicitudes y notificaciones generadas
durante el piloto no se tocan.
