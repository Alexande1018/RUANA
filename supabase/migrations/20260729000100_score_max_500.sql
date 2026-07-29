-- Amplía el límite permitido para score de aliados: 0..500
alter table public.aliados
  drop constraint if exists aliados_score_check;

alter table public.aliados
  add constraint aliados_score_check check (score >= 0 and score <= 500);
