-- User-owned tables: profiles, master_profiles, photos.
create table public.profiles (
  user_id uuid primary key references auth.users (id) on delete cascade,
  display_name text,
  locale text not null default 'en',
  email_verified_at timestamptz,
  bonus_granted_at timestamptz,
  bonus_review_at timestamptz,
  never_paid boolean not null default true,
  preferences jsonb not null default '{}'::jsonb,
  deleted_at timestamptz,
  delete_after timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
alter table public.profiles enable row level security;
create trigger profiles_set_updated_at before update on public.profiles
  for each row execute function public.set_updated_at();

create table public.photos (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references public.profiles (user_id) on delete cascade,
  storage_path text not null,
  width int,
  height int,
  sha256 text,
  created_at timestamptz not null default now()
);
alter table public.photos enable row level security;
create index photos_user_id_idx on public.photos (user_id);

create table public.master_profiles (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references public.profiles (user_id) on delete cascade,
  name text not null default 'Main profile',
  is_default boolean not null default false,
  cv_data jsonb not null default '{}'::jsonb,
  photo_id uuid references public.photos (id) on delete set null,
  domain text,
  completeness smallint not null default 0 check (completeness between 0 and 100),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
alter table public.master_profiles enable row level security;
create unique index master_profiles_one_default_idx
  on public.master_profiles (user_id) where is_default;
create trigger master_profiles_set_updated_at before update on public.master_profiles
  for each row execute function public.set_updated_at();
