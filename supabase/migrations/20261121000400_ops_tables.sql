-- Operational tables: templates, llm_calls, flags, guards, idempotency, audit, webhooks.
create table public.templates (
  id text primary key,
  version int not null default 1,
  name text not null,
  description text,
  tier text not null default 'standard',
  ats_safe boolean not null default true,
  columns int not null default 1,
  photo boolean not null default false,
  recommended_domains text[] not null default '{}',
  manifest jsonb not null default '{}'::jsonb,
  is_active boolean not null default true
);
alter table public.templates enable row level security;

create table public.llm_calls (
  id uuid primary key default gen_random_uuid(),
  user_id uuid references public.profiles (user_id) on delete set null,
  session_id uuid,
  job_id uuid,
  step text,
  provider text,
  model text,
  prompt_version text,
  input_tokens int,
  output_tokens int,
  cache_read_tokens int,
  cache_write_tokens int,
  latency_ms int,
  cost_usd numeric(10, 6),
  status text,
  error_code text,
  created_at timestamptz not null default now()
);
alter table public.llm_calls enable row level security;
create index llm_calls_session_id_idx on public.llm_calls (session_id);

create table public.feature_flags (
  key text primary key,
  enabled boolean not null default false,
  rules jsonb not null default '{}'::jsonb
);
alter table public.feature_flags enable row level security;

create table public.signup_guards (
  bucket text not null,
  day date not null,
  count int not null default 0,
  primary key (bucket, day)
);
alter table public.signup_guards enable row level security;

create table public.idempotency_keys (
  user_id uuid not null references public.profiles (user_id) on delete cascade,
  key text not null,
  route text,
  request_hash text,
  response jsonb,
  status_code int,
  created_at timestamptz not null default now(),
  primary key (user_id, key)
);
alter table public.idempotency_keys enable row level security;

create table public.audit_log (
  id bigserial primary key,
  actor uuid references auth.users (id) on delete set null,
  action text not null,
  target text,
  meta jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);
alter table public.audit_log enable row level security;

create table public.payment_events (
  id bigserial primary key,
  provider text not null,
  event_id text not null unique,
  payload jsonb not null default '{}'::jsonb,
  received_at timestamptz not null default now(),
  processed_at timestamptz
);
alter table public.payment_events enable row level security;
