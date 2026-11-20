-- Remove the never-used legacy schema so the CLI migrations start clean. Dropping the tables also drops their triggers, and
-- "drop trigger if exists ... on <table>" errors when the table is missing.
drop table if exists public.coin_transactions cascade;
drop table if exists public.coin_balance cascade;
drop table if exists public.user_settings cascade;
drop table if exists public.cv_templates cascade;
drop table if exists public.cv_sessions cascade;
drop table if exists public.cv_profiles cascade;

drop function if exists public.update_updated_at() cascade;
