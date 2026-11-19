-- Deny-by-default RLS: read-own policies for clients, least-privilege grants.
-- Every table already has RLS enabled; tables with no policy stay fully denied
-- to anon and authenticated. No write policies exist for client roles.

-- Read-own policies (authenticated only).
create policy profiles_select_own on public.profiles for select to authenticated
  using (user_id = (select auth.uid()));
create policy master_profiles_select_own on public.master_profiles for select to authenticated
  using (user_id = (select auth.uid()));
create policy photos_select_own on public.photos for select to authenticated
  using (user_id = (select auth.uid()));
create policy cv_sessions_select_own on public.cv_sessions for select to authenticated
  using (user_id = (select auth.uid()));
create policy jobs_select_own on public.jobs for select to authenticated
  using (user_id = (select auth.uid()));
create policy renders_select_own on public.renders for select to authenticated
  using (user_id = (select auth.uid()));
create policy credit_balances_select_own on public.credit_balances for select to authenticated
  using (user_id = (select auth.uid()));
create policy credit_ledger_select_own on public.credit_ledger for select to authenticated
  using (user_id = (select auth.uid()));
create policy credit_reservations_select_own on public.credit_reservations for select to authenticated
  using (user_id = (select auth.uid()));

create policy job_events_select_own on public.job_events for select to authenticated
  using (exists (select 1 from public.jobs j where j.id = job_id and j.user_id = (select auth.uid())));

create policy templates_select_active on public.templates for select to anon, authenticated
  using (is_active);

-- Grants: start from nothing for client roles, then add select where a policy exists.
revoke all on all tables in schema public from anon, authenticated;
alter default privileges in schema public revoke all on tables from anon, authenticated;
alter default privileges in schema public revoke all on sequences from anon, authenticated;
alter default privileges in schema public revoke all on functions from public, anon, authenticated;

-- Credit tables: no direct DML for anyone but the owner/definer functions, and
-- no TRUNCATE (it bypasses the append-only row trigger on the ledger).
revoke all on public.credit_balances from public, anon, authenticated;
revoke all on public.credit_reservations from public, anon, authenticated;
revoke all on public.credit_ledger from public, anon, authenticated;
revoke truncate on public.credit_ledger from public, anon, authenticated, app_backend;

grant select on public.profiles to authenticated;
grant select on public.master_profiles to authenticated;
grant select on public.photos to authenticated;
grant select on public.cv_sessions to authenticated;
grant select on public.jobs to authenticated;
grant select on public.job_events to authenticated;
grant select on public.renders to authenticated;
grant select on public.credit_balances to authenticated;
grant select on public.credit_ledger to authenticated;
grant select on public.credit_reservations to authenticated;
grant select on public.templates to anon, authenticated;

-- Backend role: scoped DML on app tables; credit tables are written only via functions.
grant select, insert, update, delete on public.profiles to app_backend;
grant select, insert, update, delete on public.master_profiles to app_backend;
grant select, insert, update, delete on public.photos to app_backend;
grant select, insert, update, delete on public.cv_sessions to app_backend;
grant select, insert, update, delete on public.jobs to app_backend;
grant select, insert, update, delete on public.job_events to app_backend;
grant select, insert, update, delete on public.renders to app_backend;
grant select, insert, update, delete on public.templates to app_backend;
grant select, insert, update, delete on public.llm_calls to app_backend;
grant select, insert, update, delete on public.signup_guards to app_backend;
grant select, insert, update, delete on public.idempotency_keys to app_backend;
grant select, insert, update, delete on public.payment_intents to app_backend;
grant select, insert, update, delete on public.payment_events to app_backend;
grant select, insert, update, delete on public.audit_log to app_backend;
grant select, insert, update, delete on public.feature_flags to app_backend;
grant select on public.credit_balances to app_backend;
grant select on public.credit_ledger to app_backend;
grant select on public.credit_reservations to app_backend;
