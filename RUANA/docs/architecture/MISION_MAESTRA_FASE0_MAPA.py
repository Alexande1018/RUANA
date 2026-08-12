"""
Mapa Fase 0 — Misión Maestra RUANA (auditoría 2026-08-12).

SOLO DOCUMENTACIÓN DE ESTADO. No es código ejecutable.
Actualizar tras cada dominio desmontado.
"""

# MONOLITOS INICIALES (relevantes)
#
# Backend:
#   db_manager.py     4331L  — 345 métodos; ~244 fachadas; ~100 reales (~2619L cuerpo)
#   app.py            3129L  — ~118 rutas negocio aún aquí
#   aliado_service    1359L  — SQL crudo + callbacks db.*
#   schema_service    1111L  — migraciones multi-dominio
#   admin_service     1079L  — SQL + mezcla
#   score_service     1072L  — SQL; score_repo parcial (97L)
#   competencia_svc   1053L  — SQL
#   negociacion_mgr    918L  — paralelo a negociacion_service (905L)
#   pago_service       873L  — SQL
#   referido_service   752L  — SQL
#   admin_bp           603L  — OK (lecturas); mutaciones aún en app.py
#
# Frontend:
#   aliado.html       7601L  — PrivatePanel ~4050L / 135 métodos
#   admin.html        5128L  — AdminPanel ~3077L / 102 métodos
#   admin-shell.js    1325L  — shell UI (OK como presentación)
#   negociacion-guiada 1128L — wizard (aceptable si no mezcla otros dominios)
#   referidos-module   725L  — HUÉRFANO (doc en header JS; no cablear sin DOM árbol)
#   FE módulos aliado: inicio/perfil/referidos(modal)/directorio/solicitudes/
#                      acuerdos/centroComunicacion (+ stubs conexiones)
#   FE módulos admin:  resumen (estado/movimiento/métricas); ops/red/sistema TBD
#
# Repos:
#   score_repo         97L   — ÚNICO real
#   12 stubs           11L   — Placeholder
#
# ORDEN DE DESMONTAJE (ajustado por dependencias reales):
#   1. score_repo completar (SQL score_* / penalizaciones score)
#   2. contacto (mayor resto real DBManager; sin service)
#   3. evaluacion + notificacion
#   4. aliado_repo (SQL desde aliado_service)
#   5. grupo/plaza repo
#   6. referido_repo
#   7. solicitud_repo
#   8. chat_repo
#   9. negociacion_repo (+ consolidar manager)
#  10. pago_repo
#  11. competencia_repo
#  12. admin mutaciones → admin_bp; vaciar app.py
#  13. frontend módulos PrivatePanel / AdminPanel
#  14. auditoría final cero monolitos relevantes
#
# CONSUMIDORES DBManager: ~80 archivos (43 prod + 37 test)
# PATRÓN OBJETIVO: Blueprint → Service → Repository → DB
# DESTINO GIT: solo `dev` hasta review humano → main
