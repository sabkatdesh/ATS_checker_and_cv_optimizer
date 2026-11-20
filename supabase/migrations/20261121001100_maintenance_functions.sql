-- Maintenance functions. guard_bump counts signup attempts per hashed
-- IP/device bucket and day; the app reads the counts and calls this to bump.

create or replace function public.guard_bump(p_buckets text[], p_day date)
returns void
language plpgsql
security definer
set search_path = ''
as $$
begin
  insert into public.signup_guards (bucket, day, count)
  select distinct b, p_day, 1
  from unnest(p_buckets) as b
  where b is not null and b <> ''
  on conflict (bucket, day) do update set count = public.signup_guards.count + 1;
end;
$$;

revoke execute on function public.guard_bump(text[], date) from public, anon, authenticated;
grant execute on function public.guard_bump(text[], date) to app_backend, service_role;
