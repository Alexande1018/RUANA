-- Linaje en Control de Aliados: padre directo en aliados
alter table public.aliados
  add column if not exists invitado_por_codigo text;

alter table public.aliados
  add column if not exists invitado_origen text default '';

create index if not exists idx_aliados_invitado_por
  on public.aliados(invitado_por_codigo);

-- Backfill desde referidos (si existen)
update public.aliados a
set invitado_por_codigo = r.codigo_invitador,
    invitado_origen = coalesce(nullif(r.origen, ''), a.invitado_origen)
from public.referidos r
where r.codigo_referido = a.codigo
  and (a.invitado_por_codigo is null or btrim(a.invitado_por_codigo) = '');
