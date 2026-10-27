
-- ClearCommit Teams — commitments
--
-- A commitment is a promise someone accepted responsibility for. It is not an
-- idea and not a decision, and its owner is confirmed by a person rather than
-- inferred by a model. Evidence points back at the line it came from.

create table if not exists public.commitments (
    id                    text primary key,
    org_id                text not null references public.organizations(id) on delete cascade,
    conversation_id       text references public.conversations(id) on delete set null,
    owner_id              text not null references public.profiles(id),
    created_by            text not null references public.profiles(id),
    title                 text not null,
    evidence_quote        text,
    evidence_utterance_id text,
    due_on                text,
    status                text not null default 'awaiting_confirmation'
                          check (status in ('awaiting_confirmation', 'open', 'blocked', 'done', 'cancelled')),
    visibility            text not null default 'team' check (visibility in ('private', 'team')),
    completed_at          timestamptz,
    created_at            timestamptz not null default now(),
    updated_at            timestamptz not null default now()
);

create index if not exists ix_commitments_org_status on public.commitments(org_id, status);
create index if not exists ix_commitments_owner on public.commitments(owner_id);

alter table public.commitments enable row level security;

-- The owner and the creator can read it; other members see team-visible ones.
drop policy if exists commitments_read on public.commitments;
create policy commitments_read on public.commitments
    for select using (
        (owner_id = public.current_user_id() or created_by = public.current_user_id())
        or (visibility = 'team' and public.is_member(org_id))
    );

-- Only a member may create one, and only for themselves or a teammate.
drop policy if exists commitments_insert on public.commitments;
create policy commitments_insert on public.commitments
    for insert with check (public.is_member(org_id));

-- The owner updates progress; the creator may correct details.
drop policy if exists commitments_update on public.commitments;
create policy commitments_update on public.commitments
    for update using (
        owner_id = public.current_user_id()
        or created_by = public.current_user_id()
        or public.has_role(org_id, array['owner', 'manager'])
    );
