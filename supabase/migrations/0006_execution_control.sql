-- ClearCommit Teams - execution control plane
--
-- Executions are runs of controlled work: a goal becoming verified action.
-- The states are a closed set enforced here as well as in server code. In
-- particular 'succeeded', 'partially_verified', 'failed', 'unknown' and
-- 'cancelled' are distinct: collapsing them into one "done" flag is the exact
-- failure mode this schema exists to prevent.
--
-- Verification runs are the only evidence of success. A row in
-- verification_runs is a recorded check; a model's assertion is not.

create table if not exists public.executions (
    id             text primary key,
    org_id         text not null references public.organizations(id) on delete cascade,
    goal           text not null,
    status         text not null default 'running'
                   check (status in ('running', 'waiting_approval', 'blocked',
                                     'verifying', 'succeeded', 'partially_verified',
                                     'failed', 'unknown', 'cancelled')),
    created_by     text not null references public.profiles(id),
    outcome_detail text,
    cancelled_by   text references public.profiles(id),
    created_at     timestamptz not null default now(),
    updated_at     timestamptz not null default now(),
    closed_at      timestamptz
);

create index if not exists ix_executions_org_status on public.executions(org_id, status);
create index if not exists ix_executions_org_created on public.executions(org_id, created_at);

create table if not exists public.execution_steps (
    id            text primary key,
    execution_id  text not null references public.executions(id) on delete cascade,
    org_id        text not null references public.organizations(id) on delete cascade,
    seq           integer not null,
    title         text not null,
    kind          text not null default 'read'
                  check (kind in ('read', 'write', 'notify', 'approve')),
    status        text not null default 'pending',
    assignee_id   text references public.profiles(id),
    postcondition text,
    detail_json   text,
    created_at    timestamptz not null default now(),
    updated_at    timestamptz not null default now(),
    unique (execution_id, seq)
);

create index if not exists ix_steps_execution on public.execution_steps(execution_id);

-- An approval authorises one exact action. action_digest is a hash over the
-- action's identity, target and parameters; a materially different action has
-- a different digest and cannot reuse this decision.
create table if not exists public.approvals (
    id             text primary key,
    org_id         text not null references public.organizations(id) on delete cascade,
    execution_id   text not null references public.executions(id) on delete cascade,
    step_id        text references public.execution_steps(id) on delete cascade,
    requested_by   text not null references public.profiles(id),
    summary        text not null,
    action_digest  text not null,
    risk           text not null default 'medium'
                   check (risk in ('low', 'medium', 'high', 'critical')),
    status         text not null default 'pending'
                   check (status in ('pending', 'approved', 'rejected', 'expired', 'used')),
    decided_by     text references public.profiles(id),
    decided_at     timestamptz,
    decision_note  text,
    expires_at     timestamptz,
    created_at     timestamptz not null default now()
);

create index if not exists ix_approvals_org_status on public.approvals(org_id, status);
create index if not exists ix_approvals_execution on public.approvals(execution_id);

-- The postcondition is copied into the run so a later edit to the step cannot
-- retroactively make a past check appear to have tested something else.
create table if not exists public.verification_runs (
    id            text primary key,
    org_id        text not null references public.organizations(id) on delete cascade,
    execution_id  text not null references public.executions(id) on delete cascade,
    step_id       text references public.execution_steps(id) on delete cascade,
    postcondition text not null,
    result        text not null check (result in ('passed', 'failed', 'unknown')),
    source        text not null,
    evidence_json text,
    checked_by    text not null references public.profiles(id),
    created_at    timestamptz not null default now()
);

create index if not exists ix_verification_execution on public.verification_runs(execution_id);

create table if not exists public.execution_events (
    id           text primary key,
    execution_id text not null references public.executions(id) on delete cascade,
    org_id       text not null references public.organizations(id) on delete cascade,
    actor_id     text not null references public.profiles(id),
    action       text not null,
    from_status  text,
    to_status    text,
    detail_json  text,
    created_at   timestamptz not null default now()
);

create index if not exists ix_execution_events_execution on public.execution_events(execution_id);

-- Row-level security: every table is org-scoped, consistent with 0001-0005.
alter table public.executions enable row level security;
alter table public.execution_steps enable row level security;
alter table public.approvals enable row level security;
alter table public.verification_runs enable row level security;
alter table public.execution_events enable row level security;

drop policy if exists executions_read on public.executions;
create policy executions_read on public.executions
    for select using (public.is_member(org_id));

drop policy if exists executions_insert on public.executions;
create policy executions_insert on public.executions
    for insert with check (public.is_member(org_id));

drop policy if exists executions_update on public.executions;
create policy executions_update on public.executions
    for update using (public.is_member(org_id));

drop policy if exists steps_read on public.execution_steps;
create policy steps_read on public.execution_steps
    for select using (public.is_member(org_id));

drop policy if exists steps_insert on public.execution_steps;
create policy steps_insert on public.execution_steps
    for insert with check (public.is_member(org_id));

drop policy if exists steps_update on public.execution_steps;
create policy steps_update on public.execution_steps
    for update using (public.is_member(org_id));

-- Only a reviewer may see an approval; requesting one is open to members.
drop policy if exists approvals_read on public.approvals;
create policy approvals_read on public.approvals
    for select using (
        requested_by = public.current_user_id()
        or public.has_role(org_id, array['owner', 'manager'])
    );

drop policy if exists approvals_insert on public.approvals;
create policy approvals_insert on public.approvals
    for insert with check (public.is_member(org_id));

-- Only a reviewer may decide. The API enforces the digest match as well.
drop policy if exists approvals_update on public.approvals;
create policy approvals_update on public.approvals
    for update using (public.has_role(org_id, array['owner', 'manager']));

drop policy if exists verification_read on public.verification_runs;
create policy verification_read on public.verification_runs
    for select using (public.is_member(org_id));

drop policy if exists verification_insert on public.verification_runs;
create policy verification_insert on public.verification_runs
    for insert with check (public.is_member(org_id));

drop policy if exists execution_events_read on public.execution_events;
create policy execution_events_read on public.execution_events
    for select using (public.is_member(org_id));

drop policy if exists execution_events_insert on public.execution_events;
create policy execution_events_insert on public.execution_events
    for insert with check (public.is_member(org_id));
