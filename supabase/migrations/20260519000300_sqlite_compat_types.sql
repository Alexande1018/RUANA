-- Match current Flask/SQLite value conventions while RUANA is ported to
-- Postgres. These can be normalized later behind a smaller DB API.

alter table if exists public.invitaciones
  alter column usado drop default,
  alter column usado type integer using case when usado then 1 else 0 end,
  alter column usado set default 0;

alter table if exists public.contactos_ruana
  alter column pendiente_resolucion drop default,
  alter column contacto_externo_habilitado drop default,
  alter column pendiente_pago drop default,
  alter column posponer_recordatorio drop default,
  alter column fraude_sospechado drop default,
  alter column fraude_confirmado drop default,
  alter column pendiente_resolucion type integer using case when pendiente_resolucion then 1 else 0 end,
  alter column pendiente_resolucion set default 1,
  alter column contacto_externo_habilitado type integer using case when contacto_externo_habilitado then 1 else 0 end,
  alter column contacto_externo_habilitado set default 0,
  alter column pendiente_pago type integer using case when pendiente_pago then 1 else 0 end,
  alter column pendiente_pago set default 0,
  alter column posponer_recordatorio type integer using case when posponer_recordatorio then 1 else 0 end,
  alter column posponer_recordatorio set default 0,
  alter column fraude_sospechado type integer using case when fraude_sospechado then 1 else 0 end,
  alter column fraude_sospechado set default 0,
  alter column fraude_confirmado type integer using case when fraude_confirmado then 1 else 0 end,
  alter column fraude_confirmado set default 0,
  alter column metadata type text using metadata::text,
  alter column metadata set default '{}';

alter table if exists public.notificaciones_aliado
  alter column leida drop default,
  alter column leida type integer using case when leida then 1 else 0 end,
  alter column leida set default 0,
  alter column metadata type text using metadata::text,
  alter column metadata set default '{}';

alter table if exists public.aliados
  alter column especializaciones type text using especializaciones::text,
  alter column especializaciones drop not null,
  alter column especializaciones set default '[]';

alter table if exists public.aliados
  add column if not exists especializacion text;

alter table if exists public.evaluaciones
  alter column razones type text using razones::text,
  alter column razones set default '[]';

alter table if exists public.eventos_sistema
  alter column metadata type text using metadata::text,
  alter column metadata set default '{}';

alter table if exists public.audit_log
  alter column detalles type text using detalles::text,
  alter column detalles set default '{}';
