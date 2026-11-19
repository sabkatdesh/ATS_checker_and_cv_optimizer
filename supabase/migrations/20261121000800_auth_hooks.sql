-- Auth hooks: create the profile and zero balance on signup, mirror email
-- verification onto the profile, and expose a backend-only verification lookup.

create or replace function public.handle_new_user()
returns trigger
language plpgsql
security definer
set search_path = ''
as $$
begin
  insert into public.profiles (user_id, email_verified_at)
  values (new.id, new.email_confirmed_at)
  on conflict (user_id) do nothing;

  insert into public.credit_balances (user_id, balance, held)
  values (new.id, 0, 0)
  on conflict (user_id) do nothing;

  return new;
end;
$$;

create or replace function public.handle_user_verified()
returns trigger
language plpgsql
security definer
set search_path = ''
as $$
begin
  update public.profiles
  set email_verified_at = new.email_confirmed_at
  where user_id = new.id;
  return new;
end;
$$;

create or replace function public.user_email_verified(p_user uuid)
returns timestamptz
language sql
stable
security definer
set search_path = ''
as $$
  select p.email_verified_at from public.profiles p where p.user_id = p_user;
$$;

revoke execute on function public.handle_new_user() from public, anon, authenticated;
revoke execute on function public.handle_user_verified() from public, anon, authenticated;
revoke execute on function public.user_email_verified(uuid) from public, anon, authenticated;
grant execute on function public.user_email_verified(uuid) to app_backend;

drop trigger if exists on_auth_user_created on auth.users;
create trigger on_auth_user_created
  after insert on auth.users
  for each row execute function public.handle_new_user();

drop trigger if exists on_auth_user_verified on auth.users;
create trigger on_auth_user_verified
  after update of email_confirmed_at on auth.users
  for each row
  when (old.email_confirmed_at is distinct from new.email_confirmed_at)
  execute function public.handle_user_verified();
