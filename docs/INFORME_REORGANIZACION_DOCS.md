# Informe final — Reorganización de documentación RUANA

**Fecha:** 2026-07-28  
**Rama:** `cursor/reorg-documentacion-ruana-1c5e`  
**Alcance:** Fases 1–6 (análisis, auditoría, reorganización, Manual Maestro, docs secundarios, validación).

---

## 1. Archivos creados

| Archivo | Descripción |
|---------|-------------|
| `README.md` (raíz) | Manual Maestro — única fuente de verdad |
| `README_RUANA_COMPLETO.md` | Copia idéntica del Manual Maestro |
| `/home/ubuntu/Desktop/README_RUANA_COMPLETO.md` | Copia de consulta fuera del repositorio |
| `docs/README.md` | Índice del árbol `docs/` |
| `docs/INFORME_REORGANIZACION_DOCS.md` | Este informe |
| `docs/archive/README.md` | Inventario del archivo histórico |
| `docs/seguridad/autenticacion-sesiones.md` | Deep-dive auth vigente |
| `docs/flujos/chat-y-alerta.md` | Deep-dive chat/alerta alineado a código |
| `docs/flujos/registro-aliados.md` | Deep-dive registro/plazas alineado a código |
| `docs/operaciones/roadmap.md` | Roadmap operativo vivo |
| `docs/qa/plan-testing.md` | Plan QA vigente (puntero + resumen) |
| `docs/qa/solicitudes-flow.md` | Nota QA solicitudes |
| `RUANA/docs/README.md` | Punteros desde carpeta de código |

## 2. Archivos modificados

| Archivo | Cambio |
|---------|--------|
| `RUANA/README.md` | Sustituido por puntero al Manual Maestro |
| `RUANA/MAPA_MENTAL_RUANA.md` | Stub → archive |
| `RUANA/docs/LOGICA_CHAT_Y_ALERTA.md` | Stub → archive + flujo vigente |
| `RUANA/docs/AUTENTICACION_SESIONES_SEGURAS.md` | Stub → archive + seguridad vigente |
| `RUANA/docs/FLUJO_REGISTRO_ALIADOS_OFICIOS.md` | Stub → archive + flujo vigente |
| `ROADMAP.md` | Stub → roadmap operativo |
| `docs/exports/README.md` | Enlaces a archive + Manual Maestro |
| `docs/seguridad/credenciales-admin.md` | Rutas de plan Firebase actualizadas (movido desde `ADMIN_CREDENTIALS_SETUP.md`) |

## 3. Archivos archivados (contenido íntegro conservado)

Bajo `docs/archive/`:

- `RUANA/README_oficial_anterior.md`
- `RUANA/MAPA_MENTAL_RUANA.md`
- `RUANA/LOGICA_CHAT_Y_ALERTA.md`
- `RUANA/AUTENTICACION_SESIONES_SEGURAS.md`
- `RUANA/FLUJO_REGISTRO_ALIADOS_OFICIOS.md`
- `ROADMAP_2026-05.md`
- `AUDITORIA_FORENSE_RUANA.md`
- `qa/QA_TESTING_PLAN_RUANA.md`, `qa/solicitudes-flow-qa.md`
- `ideas/codigos-invitacion-admin-masivos.md`
- `superpowers/plans/*`, `superpowers/specs/*`
- `exports/*` (respaldo)

Ningún documento histórico se eliminó.

## 4. Información fusionada

- Narrativa de producto, score, grupos, contactos y API del antiguo `RUANA/README.md` → Manual Maestro (corregida).
- Detalle de sesiones del doc de autenticación → `docs/seguridad/autenticacion-sesiones.md` + §11 del Manual.
- Flujo de registro → `docs/flujos/registro-aliados.md` (plaza por oficio principal).
- Chat/alerta → `docs/flujos/chat-y-alerta.md` (límite 30).
- Roadmap mayo → archive; estado julio → `docs/operaciones/roadmap.md` + §17.
- Credenciales admin → `docs/seguridad/credenciales-admin.md`.

## 5. Inconsistencias encontradas (resueltas a favor del código)

| Tema | Antes (docs) | Después (Manual / código) |
|------|--------------|---------------------------|
| Persistencia | SQLite única | Postgres/Supabase prod + SQLite fallback |
| `apoyo_pct` | 15 % / 5 % / 2 % | **12.0** |
| Chat | 5 msgs/usuario | **30 totales** |
| Reinicio competencia | 75 | **50** |
| Declaración importe | Ambas partes | **Solo solicitante** |
| Admin auth | admin_codes claros | Hashes + secrets |
| Plaza | Por especialización | **Oficio principal** |
| Firebase JS | Implícito | Solo Hosting→Cloud Run |
| Campañas | Idea futura | Implementadas |
| HITOS / auditoría may-19 | Citados | Ausentes; nota en roadmap |
| Puerto | 5050 | **5000** |
| Multi-fuente de verdad | README + ROADMAP + auditoría | **Solo Manual Maestro** |

## 6. Decisiones tomadas

1. El Manual Maestro vive en la **raíz** (`README.md`), no solo en `RUANA/`, para que sea lo primero que vea un desarrollador o inversor.
2. Se mantiene `README_RUANA_COMPLETO.md` idéntico byte-a-byte y una copia en el Escritorio del entorno.
3. Los deep-dives secundarios **no duplican** el Manual: amplían un tema y enlazan la sección canónica.
4. Los planes `superpowers/` se archivan (muchos checkboxes abiertos pese a código ya implementado).
5. La auditoría forense se trata como **foto congelada**, no como doc vivo.
6. No se inventaron funcionalidades: API y reglas se extrajeron de `app.py` y `db_manager.py`.

## 7. Validación

- [x] Contenido histórico conservado en `docs/archive/`
- [x] `README.md` ≡ `README_RUANA_COMPLETO.md` (cmp)
- [x] Copia Desktop ≡ Manual Maestro (cmp)
- [x] Enlaces internos principales verificados (ver script de validación en commit)
- [x] Documentación alineada a constantes de código (`apoyo_pct`, chat, reinicio, plaza)

## 8. Auditoría previa de docs (Fase 2 — resumen)

| Documento | Vigente | Incompleto | Duplicado | Actualizar | Fusionar | Archivar |
|-----------|---------|------------|-----------|------------|----------|----------|
| `RUANA/README.md` (antiguo) | Parcial | Infra/auth | Con mapa | Sí → Manual | Sí | Copia en archive |
| `MAPA_MENTAL` | No | Sí | Con README | — | — | Sí |
| `LOGICA_CHAT` | Parcial | Límite erróneo | Con README | → flujo | Sí | Sí |
| `AUTENTICACION_*` | Sí | — | Parcial | Deep-dive | Parcial | Original sí |
| `FLUJO_REGISTRO_*` | Parcial | Plaza | — | → flujo | Sí | Sí |
| `ROADMAP.md` | Parcial | Refs rotas | — | → ops | — | Histórico sí |
| `AUDITORIA_FORENSE` | Congelada | — | — | No | — | Sí (foto) |
| `QA_*` | Sí | — | — | Puntero | — | Copia sí |
| `ideas/campañas` | Obsoleto como idea | — | — | — | — | Sí |
| `superpowers/*` | Histórico | Checkboxes | — | No | — | Sí |
| `ADMIN_CREDENTIALS` | Sí | — | — | Rutas | — | No (movido a seguridad) |
| Root `README.md` | Placeholder | Total | — | Reescrito | — | N/A |
