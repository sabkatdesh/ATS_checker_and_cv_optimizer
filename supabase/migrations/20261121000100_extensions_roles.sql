-- Extensions, the private lg schema, the backend role and shared helpers.
create schema if not exists extensions;
create extension if not exists pgcrypto with schema extensions;
create extension if not exists pg_trgm with schema extensions;
create extension if not exists vector with schema extensions;

create schema if not exists lg;

-- No password here; it is set out of band when the backend is wired up.
do $$
begin
  if not exists (select 1 from pg_roles where rolname = 'app_backend') then
    create role app_backend nologin noinherit bypassrls;
  end if;
end
$$;

grant usage on schema public, lg to app_backend;
revoke all on schema lg from public, anon, authenticated;

create or replace function public.set_updated_at()
returns trigger
language plpgsql
set search_path = ''
as $$
begin
  new.updated_at = now();
  return new;
end;
$$;
