-- ClearCommit Teams — personal conversation records (Phase 4a)
--
-- Makes `conversations.org_id` nullable so an individual without an
-- organization can hold a cloud record. Organization records keep every
-- existing constraint; only personal records use a NULL org.
--
-- Additive and reversible: no column is dropped, no data is deleted.

alter table public.conversations
    alter column org_id drop not null;

-- Personal records are authorized by ownership alone. Organization access
-- still requires membership (see the existing policies from 0001).
drop policy if exists conversations_owner_or_shared on public.conversations;

create policy conversations_owner_or_shared on public.conversations
    for select using (
        owner_id = public.current_user_id()
        or (
            org_id is not null
            and visibility = 'shared'
            and public.is_member(org_id)
        )
    );

-- Writes: the owner always, and only within an organization they belong to
-- when the record is organization-scoped.
drop policy if exists conversations_owner_write on public.conversations;

create policy conversations_owner_write on public.conversations
    for all
    using (
        owner_id = public.current_user_id()
        and (org_id is null or public.is_member(org_id))
    )
    with check (
        owner_id = public.current_user_id()
        and (org_id is null or public.is_member(org_id))
    );

-- Utterances follow the parent conversation, including personal ones.
drop policy if exists utterances_follow_conversation on public.utterances;

create policy utterances_follow_conversation on public.utterances
    for select using (
        exists (
            select 1 from public.conversations c
            where c.id = utterances.conversation_id
              and (
                  c.owner_id = public.current_user_id()
                  or (
                      c.org_id is not null
                      and c.visibility = 'shared'
                      and public.is_member(c.org_id)
                  )
              )
        )
    );

drop policy if exists utterances_owner_write on public.utterances;

create policy utterances_owner_write on public.utterances
    for all
    using (
        exists (
            select 1 from public.conversations c
            where c.id = utterances.conversation_id
              and c.owner_id = public.current_user_id()
        )
    )
    with check (
        exists (
            select 1 from public.conversations c
            where c.id = utterances.conversation_id
              and c.owner_id = public.current_user_id()
        )
    );

-- Track where a personal record came from and how far it got, without
-- inventing processing that did not happen.
alter table public.conversations
    add column if not exists source text not null default 'manual';

alter table public.conversations
    add column if not exists client_ref text;

create index if not exists ix_conversations_owner_client_ref
    on public.conversations(owner_id, client_ref);

-- A personal workspace is an organization of one, so membership, audit and
-- every existing policy keep working. It is flagged so the UI can hide it from
-- the organization list, and one owner may have at most one.
alter table public.organizations
    add column if not exists is_personal boolean not null default false;

create unique index if not exists uq_personal_org_per_owner
    on public.organizations(created_by)
    where is_personal;