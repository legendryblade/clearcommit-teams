-- ClearCommit Teams — initial schema (Supabase / PostgreSQL 15+)
--
-- Apply with:  psql "$CLEARCOMMIT_DATABASE_URL" -f supabase/migrations/0001_init.sql
-- or paste into the Supabase SQL editor. Safe to re-run.
--
-- Tenant isolation is enforced twice:
--   1. The FastAPI service verifies membership for every request.
--   2. Row-level security below denies direct client access unless the caller
--      is an active member of the record's organization. Policies key off
--      auth.uid() (Supabase Auth) for direct PostgREST access, and off
--      app.user_id for service connections that choose to set it.

create extension if not exists "pgcrypto";

-- ---------------------------------------------------------------------------
-- Tables
-- ---------------------------------------------------------------------------

create table if not exists public.profiles (
    id            text primary key,
    email         text not null unique,
    display_name  text not null,
    password_hash text,
    created_at    timestamptz not null default now()
);

create table if not exists public.organizations (
    id         text primary key,
    name       text not null,
    created_by text not null references public.profiles(id),
    created_at timestamptz not null default now()
);

create table if not exists public.memberships (
    id         text primary key,
    org_id     text not null references public.organizations(id) on delete cascade,
    user_id    text not null references public.profiles(id) on delete cascade,
    role       text not null check (role in ('owner', 'manager', 'sales_rep', 'marketing')),
    status     text not null default 'active' check (status in ('active', 'revoked')),
    created_at timestamptz not null default now(),
    revoked_at timestamptz,
    constraint uq_membership_org_user unique (org_id, user_id)
);
create index if not exists ix_memberships_user on public.memberships(user_id);

create table if not exists public.invitations (
    id          text primary key,
    org_id      text not null references public.organizations(id) on delete cascade,
    email       text not null,
    role        text not null check (role in ('manager', 'sales_rep', 'marketing')),
    status      text not null default 'pending' check (status in ('pending', 'accepted', 'revoked')),
    invited_by  text not null references public.profiles(id),
    created_at  timestamptz not null default now(),
    accepted_by text references public.profiles(id),
    accepted_at timestamptz
);
create index if not exists ix_invitations_org_status on public.invitations(org_id, status);

create table if not exists public.conversations (
    id         text primary key,
    org_id     text not null references public.organizations(id) on delete cascade,
    owner_id   text not null references public.profiles(id),
    title      text not null,
    language   text not null default 'en',
    visibility text not null default 'private' check (visibility in ('private', 'shared')),
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);
create index if not exists ix_conversations_org_owner on public.conversations(org_id, owner_id);

create table if not exists public.utterances (
    id              text primary key,
    conversation_id text not null references public.conversations(id) on delete cascade,
    seq             integer not null,
    speaker         text not null,
    lang            text not null default 'en',
    content         text not null,
    translation     text,
    created_at      timestamptz not null default now(),
    constraint uq_utterance_conversation_seq unique (conversation_id, seq)
);

create table if not exists public.coaching_insights (
    id                    text primary key,
    org_id                text not null references public.organizations(id) on delete cascade,
    conversation_id       text not null references public.conversations(id) on delete cascade,
    owner_id              text not null references public.profiles(id),
    title                 text not null,
    observed_issue        text not null,
    suggested_alternative text not null,
    recommended_action    text,
    uncertainty           text,
    evidence_json         text not null default '[]',
    visibility            text not null default 'private' check (visibility in ('private', 'shared')),
    created_at            timestamptz not null default now(),
    updated_at            timestamptz not null default now()
);
create index if not exists ix_insights_org_visibility on public.coaching_insights(org_id, visibility);

create table if not exists public.playbook_entries (
    id             text primary key,
    org_id         text not null references public.organizations(id) on delete cascade,
    insight_id     text references public.coaching_insights(id) on delete set null,
    title          text not null,
    scenario       text not null,
    response       text not null,
    discovery_json text not null default '[]',
    status         text not null default 'draft' check (status in ('draft', 'approved')),
    version        integer not null default 1,
    created_by     text not null references public.profiles(id),
    approved_by    text references public.profiles(id),
    approved_at    timestamptz,
    created_at     timestamptz not null default now(),
    updated_at     timestamptz not null default now()
);
create index if not exists ix_playbook_org_status on public.playbook_entries(org_id, status);

create table if not exists public.approved_messaging (
    id           text primary key,
    org_id       text not null references public.organizations(id) on delete cascade,
    title        text not null,
    claim_text   text not null,
    status       text not null default 'draft' check (status in ('draft', 'published')),
    created_by   text not null references public.profiles(id),
    published_by text references public.profiles(id),
    published_at timestamptz,
    created_at   timestamptz not null default now(),
    updated_at   timestamptz not null default now()
);
create index if not exists ix_messaging_org_status on public.approved_messaging(org_id, status);

create table if not exists public.audit_events (
    id            text primary key,
    org_id        text not null references public.organizations(id) on delete cascade,
    actor_id      text not null references public.profiles(id),
    action        text not null,
    resource_type text not null,
    resource_id   text not null,
    detail_json   text,
    created_at    timestamptz not null default now()
);
create index if not exists ix_audit_org_created on public.audit_events(org_id, created_at);

create table if not exists public.idempotency_records (
    id            text primary key,
    user_id       text not null references public.profiles(id) on delete cascade,
    scope         text not null,
    key_digest    text not null,
    response_json text not null,
    created_at    timestamptz not null default now(),
    constraint uq_idempotency_user_scope_key unique (user_id, scope, key_digest)
);

-- ---------------------------------------------------------------------------
-- Authorization helpers
-- ---------------------------------------------------------------------------

-- Supabase provides the auth schema and these functions. On plain PostgreSQL
-- minimal stand-ins are installed so the policies compile unchanged. A real
-- Supabase installation is never overridden.
do $$
begin
    if not exists (select 1 from pg_namespace where nspname = 'auth') then
        create schema auth;
    end if;
    if not exists (
        select 1 from pg_proc p join pg_namespace n on n.oid = p.pronamespace
        where n.nspname = 'auth' and p.proname = 'uid'
    ) then
        create function auth.uid() returns uuid
        language sql stable as $fn$
            select nullif(current_setting('request.jwt.claim.sub', true), '')::uuid;
        $fn$;
    end if;
    if not exists (
        select 1 from pg_proc p join pg_namespace n on n.oid = p.pronamespace
        where n.nspname = 'auth' and p.proname = 'jwt'
    ) then
        create function auth.jwt() returns jsonb
        language sql stable as $fn$
            select coalesce(
                nullif(current_setting('request.jwt.claims', true), '')::jsonb,
                '{}'::jsonb
            );
        $fn$;
    end if;
end
$$;

create or replace function public.current_user_id()
returns text
language sql
stable
as $$
    select coalesce(
        nullif(current_setting('app.user_id', true), ''),
        nullif(auth.uid()::text, '')
    );
$$;

create or replace function public.is_member(target_org text)
returns boolean
language sql
stable
security definer
set search_path = public
as $$
    select exists (
        select 1 from public.memberships m
        where m.org_id = target_org
          and m.user_id = public.current_user_id()
          and m.status = 'active'
    );
$$;

create or replace function public.has_role(target_org text, roles text[])
returns boolean
language sql
stable
security definer
set search_path = public
as $$
    select exists (
        select 1 from public.memberships m
        where m.org_id = target_org
          and m.user_id = public.current_user_id()
          and m.status = 'active'
          and m.role = any(roles)
    );
$$;

-- ---------------------------------------------------------------------------
-- Row-level security
-- ---------------------------------------------------------------------------

alter table public.profiles            enable row level security;
alter table public.organizations       enable row level security;
alter table public.memberships         enable row level security;
alter table public.invitations         enable row level security;
alter table public.conversations       enable row level security;
alter table public.utterances          enable row level security;
alter table public.coaching_insights   enable row level security;
alter table public.playbook_entries    enable row level security;
alter table public.approved_messaging  enable row level security;
alter table public.audit_events        enable row level security;
alter table public.idempotency_records enable row level security;

-- profiles: yourself, plus teammates sharing an active organization
drop policy if exists profiles_self_read on public.profiles;
create policy profiles_self_read on public.profiles
    for select using (
        id = public.current_user_id()
        or exists (
            select 1 from public.memberships mine
            join public.memberships theirs on theirs.org_id = mine.org_id
            where mine.user_id = public.current_user_id() and mine.status = 'active'
              and theirs.user_id = profiles.id and theirs.status = 'active'
        )
    );

-- organizations: members only
drop policy if exists organizations_member_read on public.organizations;
create policy organizations_member_read on public.organizations
    for select using (public.is_member(id));

drop policy if exists organizations_owner_write on public.organizations;
create policy organizations_owner_write on public.organizations
    for update using (public.has_role(id, array['owner']));

-- memberships: your own rows and your org's rows
drop policy if exists memberships_read on public.memberships;
create policy memberships_read on public.memberships
    for select using (user_id = public.current_user_id() or public.is_member(org_id));

drop policy if exists memberships_owner_manage on public.memberships;
create policy memberships_owner_manage on public.memberships
    for all using (public.has_role(org_id, array['owner']))
    with check (public.has_role(org_id, array['owner']));

-- invitations: reviewers in the org, plus the invitee by verified email
drop policy if exists invitations_reviewer_read on public.invitations;
create policy invitations_reviewer_read on public.invitations
    for select using (
        public.has_role(org_id, array['owner', 'manager'])
        or lower(email) = lower(coalesce(auth.jwt() ->> 'email', ''))
    );

drop policy if exists invitations_reviewer_write on public.invitations;
create policy invitations_reviewer_write on public.invitations
    for all using (public.has_role(org_id, array['owner', 'manager']))
    with check (public.has_role(org_id, array['owner', 'manager']));

-- conversations: owner always; other members only when shared
drop policy if exists conversations_owner_or_shared on public.conversations;
create policy conversations_owner_or_shared on public.conversations
    for select using (
        owner_id = public.current_user_id()
        or (visibility = 'shared' and public.is_member(org_id))
    );

drop policy if exists conversations_owner_write on public.conversations;
create policy conversations_owner_write on public.conversations
    for all using (owner_id = public.current_user_id() and public.is_member(org_id))
    with check (owner_id = public.current_user_id() and public.is_member(org_id));

-- utterances: inherit the parent conversation's access exactly
drop policy if exists utterances_follow_conversation on public.utterances;
create policy utterances_follow_conversation on public.utterances
    for select using (
        exists (
            select 1 from public.conversations c
            where c.id = utterances.conversation_id
              and (
                  c.owner_id = public.current_user_id()
                  or (c.visibility = 'shared' and public.is_member(c.org_id))
              )
        )
    );

drop policy if exists utterances_owner_write on public.utterances;
create policy utterances_owner_write on public.utterances
    for all using (
        exists (
            select 1 from public.conversations c
            where c.id = utterances.conversation_id and c.owner_id = public.current_user_id()
        )
    )
    with check (
        exists (
            select 1 from public.conversations c
            where c.id = utterances.conversation_id and c.owner_id = public.current_user_id()
        )
    );

-- insights: author always; other members when shared
drop policy if exists insights_owner_or_shared on public.coaching_insights;
create policy insights_owner_or_shared on public.coaching_insights
    for select using (
        owner_id = public.current_user_id()
        or (visibility = 'shared' and public.is_member(org_id))
    );

drop policy if exists insights_author_write on public.coaching_insights;
create policy insights_author_write on public.coaching_insights
    for all using (owner_id = public.current_user_id() and public.is_member(org_id))
    with check (owner_id = public.current_user_id() and public.is_member(org_id));

-- playbook: members read; members draft; reviewers or draft authors update
drop policy if exists playbook_member_read on public.playbook_entries;
create policy playbook_member_read on public.playbook_entries
    for select using (public.is_member(org_id));

drop policy if exists playbook_member_insert on public.playbook_entries;
create policy playbook_member_insert on public.playbook_entries
    for insert with check (public.is_member(org_id));

drop policy if exists playbook_reviewer_update on public.playbook_entries;
create policy playbook_reviewer_update on public.playbook_entries
    for update using (
        public.has_role(org_id, array['owner', 'manager'])
        or (created_by = public.current_user_id() and status = 'draft')
    );

-- approved messaging: members read published; authoring roles read drafts
drop policy if exists messaging_read on public.approved_messaging;
create policy messaging_read on public.approved_messaging
    for select using (
        public.is_member(org_id)
        and (
            status = 'published'
            or public.has_role(org_id, array['owner', 'manager', 'marketing'])
        )
    );

drop policy if exists messaging_author_insert on public.approved_messaging;
create policy messaging_author_insert on public.approved_messaging
    for insert with check (public.has_role(org_id, array['owner', 'manager', 'marketing']));

drop policy if exists messaging_reviewer_publish on public.approved_messaging;
create policy messaging_reviewer_publish on public.approved_messaging
    for update using (public.has_role(org_id, array['owner', 'manager']));

-- audit events: reviewers read; no direct client writes
drop policy if exists audit_reviewer_read on public.audit_events;
create policy audit_reviewer_read on public.audit_events
    for select using (public.has_role(org_id, array['owner', 'manager']));

-- idempotency records: only your own
drop policy if exists idempotency_owner_read on public.idempotency_records;
create policy idempotency_owner_read on public.idempotency_records
    for select using (user_id = public.current_user_id());

-- ---------------------------------------------------------------------------
-- Grants (Supabase roles exist only on Supabase)
-- ---------------------------------------------------------------------------

do $$
begin
    if exists (select 1 from pg_roles where rolname = 'authenticated') then
        grant usage on schema public to authenticated;
        grant select, insert, update, delete on all tables in schema public to authenticated;
        if exists (select 1 from pg_roles where rolname = 'anon') then
            revoke all on public.profiles from anon;
        end if;
    end if;
end
$$;

-- The service connection used by the FastAPI backend must not bypass the
-- application's own authorization. Create it without superuser or bypassrls:
--
--   create role clearcommit_service login password '...' nosuperuser nobypassrls;
--   grant usage on schema public to clearcommit_service;
--   grant select, insert, update, delete on all tables in schema public to clearcommit_service;
--
-- Then point CLEARCOMMIT_DATABASE_URL at that role.
