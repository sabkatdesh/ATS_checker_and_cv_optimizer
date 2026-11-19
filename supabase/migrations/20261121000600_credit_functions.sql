-- Credit functions. All writes to the credit tables go through these
-- SECURITY DEFINER functions: ledger insert first (idempotent), then the
-- per-user balance row is locked, invariants are checked, and balance +
-- reservation are updated in the same transaction.

create or replace function public.credits_grant(
  p_user uuid, p_amount int, p_kind text, p_idem text)
returns int
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_inserted bigint;
  v_balance int;
begin
  if p_amount is null or p_amount <= 0
     or p_kind is null
     or p_kind not in ('signup_bonus', 'purchase', 'adjustment', 'refund_admin') then
    raise exception 'INVALID_AMOUNT' using errcode = 'P0001';
  end if;

  insert into public.credit_ledger (user_id, kind, delta_balance, delta_held, idempotency_key)
  values (p_user, p_kind, p_amount, 0, p_idem)
  on conflict (idempotency_key) do nothing
  returning id into v_inserted;

  if v_inserted is null then
    select b.balance into v_balance from public.credit_balances b where b.user_id = p_user;
    return coalesce(v_balance, 0);
  end if;

  insert into public.credit_balances (user_id, balance, held)
  values (p_user, 0, 0)
  on conflict (user_id) do nothing;

  perform 1 from public.credit_balances b where b.user_id = p_user for update;

  update public.credit_balances
  set balance = balance + p_amount, updated_at = now()
  where user_id = p_user
  returning balance into v_balance;

  if p_kind = 'signup_bonus' then
    update public.profiles
    set bonus_granted_at = coalesce(bonus_granted_at, now())
    where user_id = p_user;
  end if;

  return v_balance;
end;
$$;

create or replace function public.credits_reserve(
  p_user uuid, p_session uuid, p_amount int, p_idem text)
returns uuid
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_res uuid := gen_random_uuid();
  v_inserted bigint;
  v_balance int;
  v_held int;
begin
  if p_amount is null or p_amount <= 0 then
    raise exception 'INVALID_AMOUNT' using errcode = 'P0001';
  end if;

  insert into public.credit_ledger
    (user_id, kind, delta_balance, delta_held, reservation_id, session_id, idempotency_key)
  values (p_user, 'reserve', 0, p_amount, v_res, p_session, p_idem)
  on conflict (idempotency_key) do nothing
  returning id into v_inserted;

  if v_inserted is null then
    select l.reservation_id into v_res
    from public.credit_ledger l where l.idempotency_key = p_idem;
    return v_res;
  end if;

  select b.balance, b.held into v_balance, v_held
  from public.credit_balances b where b.user_id = p_user for update;

  if not found or v_balance - v_held < p_amount then
    raise exception 'INSUFFICIENT_CREDITS' using errcode = 'P0001';
  end if;

  insert into public.credit_reservations (id, user_id, session_id, amount)
  values (v_res, p_user, p_session, p_amount);

  update public.credit_balances
  set held = held + p_amount, updated_at = now()
  where user_id = p_user;

  return v_res;
end;
$$;

create or replace function public.credits_settle(
  p_reservation uuid, p_capture int, p_idem text)
returns void
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_user uuid;
  v_amount int;
  v_status text;
  v_session uuid;
  v_inserted bigint;
begin
  if p_capture is null or p_capture < 0 then
    raise exception 'INVALID_AMOUNT' using errcode = 'P0001';
  end if;

  select r.user_id, r.session_id into v_user, v_session
  from public.credit_reservations r where r.id = p_reservation;
  if not found then
    raise exception 'RESERVATION_NOT_FOUND' using errcode = 'P0001';
  end if;

  insert into public.credit_ledger
    (user_id, kind, delta_balance, delta_held, reservation_id, session_id, idempotency_key)
  values (v_user, 'capture', -p_capture, -p_capture, p_reservation, v_session, p_idem || ':capture')
  on conflict (idempotency_key) do nothing
  returning id into v_inserted;

  if v_inserted is null then
    return;
  end if;

  perform 1 from public.credit_balances b where b.user_id = v_user for update;

  select r.amount, r.status into v_amount, v_status
  from public.credit_reservations r where r.id = p_reservation for update;

  if v_status <> 'held' then
    raise exception 'RESERVATION_SETTLED' using errcode = 'P0001';
  end if;
  if p_capture > v_amount then
    raise exception 'INVALID_AMOUNT' using errcode = 'P0001';
  end if;

  insert into public.credit_ledger
    (user_id, kind, delta_balance, delta_held, reservation_id, session_id, idempotency_key)
  values (v_user, 'release', 0, -(v_amount - p_capture), p_reservation, v_session, p_idem || ':release')
  on conflict (idempotency_key) do nothing;

  update public.credit_balances
  set balance = balance - p_capture, held = held - v_amount, updated_at = now()
  where user_id = v_user;

  update public.credit_reservations
  set captured = p_capture,
      status = case when p_capture = v_amount then 'captured'
                    when p_capture = 0 then 'released'
                    else 'partial' end,
      settled_at = now()
  where id = p_reservation;
end;
$$;

create or replace function public.credits_tier_upgrade(
  p_user uuid, p_session uuid, p_from text, p_to text, p_amount int, p_idem text)
returns int
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_inserted bigint;
  v_balance int;
  v_held int;
begin
  if p_amount is null or p_amount <= 0 then
    raise exception 'INVALID_AMOUNT' using errcode = 'P0001';
  end if;

  insert into public.credit_ledger
    (user_id, kind, delta_balance, delta_held, session_id, idempotency_key, reason)
  values (p_user, 'tier_upgrade', -p_amount, 0, p_session, p_idem, p_from || '->' || p_to)
  on conflict (idempotency_key) do nothing
  returning id into v_inserted;

  if v_inserted is null then
    select b.balance into v_balance from public.credit_balances b where b.user_id = p_user;
    return coalesce(v_balance, 0);
  end if;

  select b.balance, b.held into v_balance, v_held
  from public.credit_balances b where b.user_id = p_user for update;

  if not found or v_balance - v_held < p_amount then
    raise exception 'INSUFFICIENT_CREDITS' using errcode = 'P0001';
  end if;

  update public.credit_balances
  set balance = balance - p_amount, updated_at = now()
  where user_id = p_user
  returning balance into v_balance;

  return v_balance;
end;
$$;

revoke execute on function public.credits_grant(uuid, int, text, text) from public, anon, authenticated;
revoke execute on function public.credits_reserve(uuid, uuid, int, text) from public, anon, authenticated;
revoke execute on function public.credits_settle(uuid, int, text) from public, anon, authenticated;
revoke execute on function public.credits_tier_upgrade(uuid, uuid, text, text, int, text)
  from public, anon, authenticated;
grant execute on function public.credits_grant(uuid, int, text, text) to app_backend, service_role;
grant execute on function public.credits_reserve(uuid, uuid, int, text) to app_backend, service_role;
grant execute on function public.credits_settle(uuid, int, text) to app_backend, service_role;
grant execute on function public.credits_tier_upgrade(uuid, uuid, text, text, int, text)
  to app_backend, service_role;
