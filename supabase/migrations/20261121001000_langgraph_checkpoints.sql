-- LangGraph checkpoint tables (ADR-007), copied from the pinned
-- langgraph-checkpoint-postgres 3.2.1 MIGRATIONS list (versions 0..9) and
-- qualified to the private lg schema. The app never runs setup(): every
-- version is recorded below, so the library finds nothing to apply.
-- The index statements drop CONCURRENTLY: migrations run in a transaction and
-- the tables are empty here. Version 5 is the library's no-op `SELECT 1`.
-- Bump this file whenever the pinned library adds a migration.

-- v0
create table if not exists lg.checkpoint_migrations (
  v integer primary key
);

-- v1
create table if not exists lg.checkpoints (
  thread_id text not null,
  checkpoint_ns text not null default '',
  checkpoint_id text not null,
  parent_checkpoint_id text,
  type text,
  checkpoint jsonb not null,
  metadata jsonb not null default '{}',
  primary key (thread_id, checkpoint_ns, checkpoint_id)
);

-- v2
create table if not exists lg.checkpoint_blobs (
  thread_id text not null,
  checkpoint_ns text not null default '',
  channel text not null,
  version text not null,
  type text not null,
  blob bytea,
  primary key (thread_id, checkpoint_ns, channel, version)
);

-- v3
create table if not exists lg.checkpoint_writes (
  thread_id text not null,
  checkpoint_ns text not null default '',
  checkpoint_id text not null,
  task_id text not null,
  idx integer not null,
  channel text not null,
  type text,
  blob bytea not null,
  primary key (thread_id, checkpoint_ns, checkpoint_id, task_id, idx)
);

-- v4
alter table lg.checkpoint_blobs alter column blob drop not null;

-- v6..v8
create index if not exists checkpoints_thread_id_idx on lg.checkpoints(thread_id);
create index if not exists checkpoint_blobs_thread_id_idx on lg.checkpoint_blobs(thread_id);
create index if not exists checkpoint_writes_thread_id_idx on lg.checkpoint_writes(thread_id);

-- v9
alter table lg.checkpoint_writes add column if not exists task_path text not null default '';

insert into lg.checkpoint_migrations (v)
select generate_series(0, 9)
on conflict (v) do nothing;

-- Backend only: RLS on with no policies, and nothing for client roles.
alter table lg.checkpoint_migrations enable row level security;
alter table lg.checkpoints enable row level security;
alter table lg.checkpoint_blobs enable row level security;
alter table lg.checkpoint_writes enable row level security;

revoke all on lg.checkpoint_migrations from public, anon, authenticated;
revoke all on lg.checkpoints from public, anon, authenticated;
revoke all on lg.checkpoint_blobs from public, anon, authenticated;
revoke all on lg.checkpoint_writes from public, anon, authenticated;

grant select, insert, update, delete
  on lg.checkpoint_migrations, lg.checkpoints, lg.checkpoint_blobs, lg.checkpoint_writes
  to app_backend;
