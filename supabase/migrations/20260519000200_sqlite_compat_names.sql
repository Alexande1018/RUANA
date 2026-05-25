-- Keep the first Postgres schema compatible with the current SQLite-oriented
-- Flask backend while the code is migrated endpoint by endpoint.

create or replace function public.set_actualizado_en()
returns trigger
language plpgsql
as $$
begin
  new.actualizado_en = now();
  return new;
end;
$$;

alter table if exists public.grupos rename column created_at to fecha_creacion;

drop trigger if exists aliados_set_updated_at on public.aliados;
alter table if exists public.aliados rename column created_at to creado_en;
alter table if exists public.aliados rename column updated_at to actualizado_en;
create trigger aliados_set_actualizado_en
before update on public.aliados
for each row execute function public.set_actualizado_en();

drop trigger if exists contactos_ruana_set_updated_at on public.contactos_ruana;
alter table if exists public.contactos_ruana rename column created_at to creado_en;
alter table if exists public.contactos_ruana rename column updated_at to actualizado_en;
create trigger contactos_ruana_set_actualizado_en
before update on public.contactos_ruana
for each row execute function public.set_actualizado_en();

alter table if exists public.chat_mensajes rename column created_at to creado_en;
alter table if exists public.contacto_panel_oculto rename column created_at to creado_en;
alter table if exists public.confirmaciones_trabajo rename column created_at to fecha;

alter table if exists public.ingresos_ruana rename column created_at to fecha;
alter table if exists public.ingresos_ruana rename column apoyo_ruana to apoyo_ruana_2pct;

alter table if exists public.score_movimientos rename column created_at to creado_en;

drop trigger if exists evaluaciones_set_updated_at on public.evaluaciones;
alter table if exists public.evaluaciones rename column evaluated_at to evaluado_en;
alter table if exists public.evaluaciones rename column updated_at to actualizado_en;
create trigger evaluaciones_set_actualizado_en
before update on public.evaluaciones
for each row execute function public.set_actualizado_en();

alter table if exists public.evaluaciones_historico rename column created_at to registrado_en;
alter table if exists public.invitaciones rename column created_at to creado_en;
alter table if exists public.referidos rename column created_at to creado_en;
alter table if exists public.invitaciones_oficio rename column created_at to fecha_creacion;
alter table if exists public.notificaciones_aliado rename column created_at to creado_en;
alter table if exists public.competencia rename column created_at to creado_en;
alter table if exists public.avisos_grupo rename column created_at to creado_en;
alter table if exists public.eventos_sistema rename column created_at to creado_en;
alter table if exists public.audit_log rename column created_at to creado_en;

drop index if exists public.idx_grupos_cp_estado;
create index if not exists idx_grupos_cp_estado on public.grupos(codigo_postal, estado);

drop index if exists public.idx_chat_mensajes_created;
create index if not exists idx_chat_mensajes_creado on public.chat_mensajes(creado_en desc);

drop index if exists public.idx_score_movimientos_created;
create index if not exists idx_score_movimientos_creado on public.score_movimientos(creado_en);

drop index if exists public.idx_notificaciones_aliado_created;
create index if not exists idx_notificaciones_aliado_creado on public.notificaciones_aliado(creado_en desc);

drop index if exists public.idx_eventos_sistema_created;
create index if not exists idx_eventos_sistema_creado on public.eventos_sistema(creado_en desc);
