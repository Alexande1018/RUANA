-- Permite reutilizar email/teléfono tras expulsión o rechazo (contacto liberado en app).
alter table public.aliados drop constraint if exists aliados_email_key;
alter table public.aliados drop constraint if exists aliados_telefono_key;

create unique index if not exists aliados_email_activo_unique
  on public.aliados (email)
  where lower(trim(coalesce(estado, ''))) not in ('expulsado', 'rechazado');

create unique index if not exists aliados_telefono_activo_unique
  on public.aliados (telefono)
  where lower(trim(coalesce(estado, ''))) not in ('expulsado', 'rechazado')
    and telefono is not null;
