
-- ClearCommit Teams — commitment history and supersession
--
-- A changed promise never overwrites the original. The replacement points at
-- what it supersedes, and every status change is written to a history table so
-- the life of a commitment can be read back.

alter table public.commitments
    add column if not exists supersedes_id text references public.commitments(id) on delete set null;

create table if not exists public.commitment_events (
    id            text primary key,
    commitment_id text not null references public.commitments(id) on delete cascade,
    org_id        text not null references public.organizations(id) on delete cascade,
    actor_id      text not null references public.profiles(id),
    action        text not null,
    from_status   text,
    to_status     text,
    detail_json   text,
    created_at    timestamptz not null default now()
);

create index if not exists ix_commitment_events_commitment
    on public.commitment_events(commitment_id);

alter table public.commitment_events enable row level security;

drop policy if exists commitment_events_read on public.commitment_events;
create policy commitment_events_read on public.commitment_events
    for select using (public.is_member(org_id));

drop policy if exists commitment_events_insert on public.commitment_events;
create policy commitment_events_insert on public.commitment_events
    for insert with check (public.is_member(org_id));
