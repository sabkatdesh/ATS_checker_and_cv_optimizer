-- Maintenance functions.
-- claim_signup_bonus: the guard check and the grant happen in one transaction.
-- The profile row is locked first (so one user's claims serialise), then each
-- guard counter row is upserted, which row-locks it (so claims from different
-- users on the same IP or device serialise too). The ip bucket is counted per
-- UTC day; the device bucket uses the sentinel day 1970-01-01, a lifetime limit.

create or replace function public.claim_signup_bonus(
  p_user uuid, p_ip_bucket text, p_dev_bucket text,
  p_ip_max int, p_dev_max int, p_amount int)
returns text
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_verified timestamptz;
  v_granted timestamptz;
  v_review timestamptz;
  v_day date := (now() at time zone 'utc')::date;
  v_ip_count int;
  v_dev_count int := 0;
begin
  if p_user is null or p_ip_bucket is null or btrim(p_ip_bucket) = '' then
    raise exception 'INVALID_USER' using errcode = 'P0001';
  end if;

  select email_verified_at, bonus_granted_at, bonus_review_at
  into v_verified, v_granted, v_review
  from public.profiles where user_id = p_user for update;
  if not found then
    raise exception 'INVALID_USER' using errcode = 'P0001';
  end if;

  if v_granted is not null then
    return 'already_granted';
  end if;
  if v_verified is null then
    return 'email_not_verified';
  end if;
  if v_review is not null then
    return 'pending_review';
  end if;

  -- Always ip first, then device: a fixed lock order cannot deadlock.
  insert into public.signup_guards (bucket, day, count)
  values (p_ip_bucket, v_day, 0)
  on conflict (bucket, day) do update set count = public.signup_guards.count
  returning count into v_ip_count;

  if p_dev_bucket is not null and btrim(p_dev_bucket) <> '' then
    insert into public.signup_guards (bucket, day, count)
    values (p_dev_bucket, date '1970-01-01', 0)
    on conflict (bucket, day) do update set count = public.signup_guards.count
    returning count into v_dev_count;
  end if;

  if v_ip_count >= p_ip_max
     or (p_dev_bucket is not null and btrim(p_dev_bucket) <> '' and v_dev_count >= p_dev_max) then
    update public.profiles
    set bonus_review_at = coalesce(bonus_review_at, now())
    where user_id = p_user;
    return 'pending_review';
  end if;

  perform public.credits_grant(p_user, p_amount, 'signup_bonus', 'signup_bonus:' || p_user::text);

  update public.signup_guards
  set count = public.signup_guards.count + 1
  where bucket = p_ip_bucket and day = v_day;
  if p_dev_bucket is not null and btrim(p_dev_bucket) <> '' then
    update public.signup_guards
    set count = public.signup_guards.count + 1
    where bucket = p_dev_bucket and day = date '1970-01-01';
  end if;

  return 'granted';
end;
$$;

revoke execute on function public.claim_signup_bonus(uuid, text, text, int, int, int)
  from public, anon, authenticated;
grant execute on function public.claim_signup_bonus(uuid, text, text, int, int, int)
  to app_backend, service_role;
