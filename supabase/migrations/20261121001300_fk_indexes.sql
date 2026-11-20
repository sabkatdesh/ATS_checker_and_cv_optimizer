-- Indexes for foreign-key columns that had none (or only a partial one), so cascades,
-- set-null actions and per-user lookups do not scan the referencing table.
create index if not exists cv_sessions_master_profile_id_idx on public.cv_sessions (master_profile_id);
create index if not exists cv_sessions_current_render_id_idx on public.cv_sessions (current_render_id);
-- master_profiles_one_default_idx is partial (where is_default), so it does not cover user_id.
create index if not exists master_profiles_user_id_idx on public.master_profiles (user_id);
create index if not exists master_profiles_photo_id_idx on public.master_profiles (photo_id);
create index if not exists credit_reservations_session_id_idx on public.credit_reservations (session_id);
create index if not exists jobs_reservation_id_idx on public.jobs (reservation_id);
create index if not exists payment_intents_user_id_idx on public.payment_intents (user_id);
create index if not exists llm_calls_user_id_idx on public.llm_calls (user_id);
create index if not exists audit_log_actor_idx on public.audit_log (actor);
