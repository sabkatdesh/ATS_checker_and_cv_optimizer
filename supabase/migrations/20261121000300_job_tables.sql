-- Session, job and render tables.
create table public.cv_sessions (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references public.profiles (user_id) on delete cascade,
  master_profile_id uuid references public.master_profiles (id) on delete set null,
  source_cv jsonb,
  status text not null default 'draft' check (status in (
    'draft', 'queued', 'running', 'awaiting_input', 'succeeded',
    'failed', 'cancelled', 'expired', 'ineligible')),
  awaiting_kind text,
  pipeline_summary jsonb,
  jd_text text check (char_length(jd_text) <= 15000),
  jd_title text,
  jd_company text,
  jd_domain text,
  template_id text,
  template_version int,
  paid_tier text,
  accent text,
  locale text,
  options jsonb not null default '{}'::jsonb,
  score_before int,
  score_after int,
  score_breakdown jsonb,
  tailored_cv jsonb,
  accepted_changes jsonb,
  trust_report jsonb,
  cover_letter_text text,
  current_render_id uuid,
  price_credits int,
  cost_usd numeric(10, 6),
  search_tsv tsvector generated always as (
    to_tsvector('simple',
      coalesce(jd_title, '') || ' ' || coalesce(jd_company, '') || ' ' || coalesce(jd_text, ''))
  ) stored,
  jd_embedding extensions.vector(512),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
alter table public.cv_sessions enable row level security;
create index cv_sessions_user_created_idx on public.cv_sessions (user_id, created_at desc);
create index cv_sessions_search_tsv_idx on public.cv_sessions using gin (search_tsv);
create index cv_sessions_jd_title_trgm_idx
  on public.cv_sessions using gin (jd_title extensions.gin_trgm_ops);
create index cv_sessions_jd_company_trgm_idx
  on public.cv_sessions using gin (jd_company extensions.gin_trgm_ops);
create trigger cv_sessions_set_updated_at before update on public.cv_sessions
  for each row execute function public.set_updated_at();

create table public.jobs (
  id uuid primary key default gen_random_uuid(),
  session_id uuid not null references public.cv_sessions (id) on delete cascade,
  user_id uuid not null references public.profiles (user_id) on delete cascade,
  kind text not null check (kind in ('generate', 'render', 'cover_letter', 'import_profile')),
  status text not null default 'queued' check (status in (
    'queued', 'running', 'awaiting_input', 'cancelling', 'succeeded',
    'failed', 'cancelled', 'expired')),
  stage text,
  attempt int not null default 0,
  heartbeat_at timestamptz,
  cancel_requested_at timestamptz,
  expires_at timestamptz,
  error_code text,
  reservation_id uuid,
  idempotency_key text,
  started_at timestamptz,
  finished_at timestamptz,
  created_at timestamptz not null default now(),
  unique (user_id, idempotency_key)
);
alter table public.jobs enable row level security;
create index jobs_status_heartbeat_idx on public.jobs (status, heartbeat_at);
create index jobs_user_active_idx on public.jobs (user_id)
  where status in ('queued', 'running', 'awaiting_input', 'cancelling');
create index jobs_session_id_idx on public.jobs (session_id);

create table public.job_events (
  id bigserial primary key,
  job_id uuid not null references public.jobs (id) on delete cascade,
  seq int not null,
  type text not null,
  payload jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  unique (job_id, seq)
);
alter table public.job_events enable row level security;

create table public.renders (
  id uuid primary key default gen_random_uuid(),
  session_id uuid not null references public.cv_sessions (id) on delete cascade,
  user_id uuid not null references public.profiles (user_id) on delete cascade,
  content_hash text not null unique,
  template_id text,
  template_version int,
  pdf_path text,
  pages jsonb,
  thumbnail_path text,
  page_count int,
  render_ms int,
  warnings jsonb,
  created_at timestamptz not null default now()
);
alter table public.renders enable row level security;
create index renders_session_id_idx on public.renders (session_id);
create index renders_user_id_idx on public.renders (user_id);

alter table public.cv_sessions
  add constraint cv_sessions_current_render_fk
  foreign key (current_render_id) references public.renders (id) on delete set null;
