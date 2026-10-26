-- ClearCommit Teams — organization join codes
--
-- A short, human-typeable code replaces the invitation UUID for the normal
-- join flow: a manager shares one code, and an employee enters it. The code
-- only identifies the organization; the role still comes from the manager,
-- and joining is validated server-side against the verified account email.
--
-- Additive and safe to re-run.

alter table public.organizations
    add column if not exists join_code text;

create unique index if not exists uq_organizations_join_code
    on public.organizations (join_code)
    where join_code is not null;

-- Personal workspaces are never joined by code.
update public.organizations
set join_code = null
where is_personal;
