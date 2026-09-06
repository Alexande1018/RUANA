# Pago manual (IBAN / Bizum / QR)

Los datos de cobro **no viven en el repositorio** ni en `config/ruana_reglas_v1.json`.

| Dónde | Qué |
|---|---|
| Tabla `ruana_metodos_pago_manual` | `bizum_num`, `iban`, `qr_revolut_path` (una fila lógica). Los edita un admin con escritura desde el panel. Guardarlos **no** activa el pago manual. |
| Tabla `ruana_pago_manual_aliados_habilitados` | Allowlist explícita. Un aliado **presente** ve el pago manual; **ausente** no lo ve, sin excepción. |

Por defecto el pago manual está **apagado para todo el mundo**. Stripe es el único método visible salvo para los códigos listados por admin.

API aliado: `GET /api/metodos-pago` (sesión aliado) solo devuelve datos reales si ese aliado está en la allowlist; si no, `habilitado=false` y campos nulos.

**Rotación:** el IBAN/Bizum antiguos siguen en el historial de git. Hay que rotar los datos reales y purgar el historial (`git filter-repo` / BFG) **fuera** de este cambio de código.
