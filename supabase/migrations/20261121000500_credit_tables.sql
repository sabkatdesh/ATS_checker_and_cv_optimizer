-- Credit balances, reservations, the append-only ledger and payment intents.
create table public.credit_balances (
  user_id uuid primary key references public.profiles (user_id) on delete cascade,
  balance int not null default 0 check (balance >= 0),
  held int not null default 0 check (held >= 0 and held <= balance),
  updated_at timestamptz not null default now()
);
alter table public.credit_balances enable row level security;

create table public.credit_reservations (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references public.profiles (user_id) on delete cascade,
  session_id uuid references public.cv_sessions (id) on delete set null,
  amount int not null check (amount >= 0),
  captured int not null default 0,
  status text not null default 'held' check (status in ('held', 'captured', 'released', 'partial')),
  created_at timestamptz not null default now(),
  settled_at timestamptz
);
alter table public.credit_reservations enable row level security;
create index credit_reservations_user_id_idx on public.credit_reservations (user_id);

alter table public.jobs
  add constraint jobs_reservation_fk
  foreign key (reservation_id) references public.credit_reservations (id) on delete set null;

create table public.credit_ledger (
  id bigserial primary key,
  user_id uuid references public.profiles (user_id) on delete set null,
  kind text not null check (kind in (
    'signup_bonus', 'reserve', 'capture', 'release', 'tier_upgrade',
    'purchase', 'refund_admin', 'adjustment')),
  delta_balance int not null default 0,
  delta_held int not null default 0,
  reservation_id uuid,
  session_id uuid,
  idempotency_key text unique,
  reason text,
  actor uuid,
  created_at timestamptz not null default now()
);
alter table public.credit_ledger enable row level security;
create index credit_ledger_user_id_idx on public.credit_ledger (user_id);

-- Append-only: DELETE always fails; UPDATE is allowed only to anonymise
-- (user_id -> NULL) with every other column unchanged.
create or replace function public.credit_ledger_append_only()
returns trigger
language plpgsql
set search_path = ''
as $$
begin
  if tg_op = 'UPDATE'
     and new.user_id is null
     and old.user_id is not null
     and (to_jsonb(new) - 'user_id') = (to_jsonb(old) - 'user_id') then
    return new;
  end if;
  raise exception 'LEDGER_IMMUTABLE' using errcode = 'P0001';
end;
$$;

create trigger credit_ledger_append_only
  before update or delete on public.credit_ledger
  for each row execute function public.credit_ledger_append_only();

create table public.payment_intents (
  id uuid primary key default gen_random_uuid(),
  user_id uuid references public.profiles (user_id) on delete set null,
  provider text not null,
  amount_minor int not null,
  currency text not null default 'BDT',
  credits int not null,
  status text not null default 'created',
  provider_ref text,
  idempotency_key text unique,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
alter table public.payment_intents enable row level security;
create trigger payment_intents_set_updated_at before update on public.payment_intents
  for each row execute function public.set_updated_at();
