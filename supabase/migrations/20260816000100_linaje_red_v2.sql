-- Linaje v2: padre real vs origen; campañas y orgánicos sin padre aliado inventado
-- Idempotente: solo corrige filas con origen huerfano/campana bajo admin ficticio

UPDATE aliados
SET invitado_por_codigo = NULL,
    invitado_origen = 'campana'
WHERE codigo IN (SELECT codigo_aliado FROM invitacion_campana_usos)
  AND (
    invitado_por_codigo IS NULL
    OR invitado_por_codigo IN (SELECT codigo FROM aliados WHERE estado = 'sistema')
    OR COALESCE(invitado_origen, '') IN ('huerfano', 'campana', '')
  );

UPDATE aliados
SET invitado_por_codigo = NULL,
    invitado_origen = 'organico'
WHERE invitado_por_codigo IN (SELECT codigo FROM aliados WHERE estado = 'sistema')
  AND COALESCE(invitado_origen, '') IN ('huerfano', '')
  AND codigo NOT IN (SELECT codigo_aliado FROM invitacion_campana_usos);
