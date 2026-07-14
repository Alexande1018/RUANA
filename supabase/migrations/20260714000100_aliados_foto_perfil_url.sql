-- Foto pública de perfil del aliado (URL en Supabase Storage, bucket ruana-public).
alter table if exists public.aliados
  add column if not exists foto_perfil_url text;
