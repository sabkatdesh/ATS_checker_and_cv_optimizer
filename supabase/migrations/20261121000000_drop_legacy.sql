-- Remove the never-used legacy schema so the CLI migrations start clean.
drop trigger if exists trg_cv_profiles_updated_at on public.cv_profiles;
drop trigger if exists trg_cv_sessions_updated_at on public.cv_sessions;
drop trigger if exists trg_user_settings_updated_at on public.user_settings;
drop trigger if exists trg_coin_balance_updated_at on public.coin_balance;

drop table if exists public.coin_transactions cascade;
drop table if exists public.coin_balance cascade;
drop table if exists public.user_settings cascade;
drop table if exists public.cv_templates cascade;
drop table if exists public.cv_sessions cascade;
drop table if exists public.cv_profiles cascade;

drop function if exists public.update_updated_at() cascade;
