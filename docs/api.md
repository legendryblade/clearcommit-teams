# ClearCommit Teams API

Base URL: `http://127.0.0.1:8770` (configurable). Interactive docs: `/api/docs`.

All responses use one envelope:

```json
{ "ok": true, "data": { } }
{ "ok": false, "error": { "code": "not_found", "message": "…", "retryable": false, "request_id": "…" } }
```

Authentication: `Authorization: Bearer <token>`. Every protected route resolves organization membership server-side.

Cross-organization access returns **404** (never reveals existence). Insufficient role inside your own organization returns **403**.

## Health

| Method | Path | Notes |
| --- | --- | --- |
| GET | `/health` | Liveness; no dependencies |
| GET | `/ready` | Database + auth provider reachability; 503 when not ready |

## Authentication

| Method | Path | Body |
| --- | --- | --- |
| POST | `/api/auth/demo/sign-up` | `{email, display_name, password}` — demo mode only |
| POST | `/api/auth/demo/sign-in` | `{email, password}` — demo mode only |
| GET | `/api/auth/me` | Profile, mode, organizations with roles |

## Organizations and membership

| Method | Path | Role |
| --- | --- | --- |
| POST | `/api/orgs` | any (creator becomes `owner`) |
| GET | `/api/orgs` | any |
| GET | `/api/orgs/{org_id}` | member |
| POST | `/api/orgs/{org_id}/invitations` | owner, manager |
| GET | `/api/orgs/{org_id}/invitations` | owner, manager |
| DELETE | `/api/orgs/{org_id}/invitations/{id}` | owner, manager |
| GET | `/api/invitations/mine` | any (by verified email) |
| POST | `/api/invitations/accept` | invitee only |
| DELETE | `/api/orgs/{org_id}/members/{user_id}` | owner |

Roles: `owner`, `manager`, `sales_rep`, `marketing`. The last active owner cannot be revoked.

## Conversations

| Method | Path | Role |
| --- | --- | --- |
| POST | `/api/orgs/{org_id}/conversations` | member |
| GET | `/api/orgs/{org_id}/conversations` | member (own + shared) |
| GET | `/api/orgs/{org_id}/conversations/{id}` | owner, or member if shared |
| POST | `/api/orgs/{org_id}/conversations/{id}/utterances` | owner |
| POST | `/api/orgs/{org_id}/conversations/{id}/share` | owner |

## Insights

| Method | Path | Role |
| --- | --- | --- |
| POST | `/api/orgs/{org_id}/insights` | member; evidence must belong to the conversation |
| GET | `/api/orgs/{org_id}/insights?scope=mine\|shared` | member |
| GET | `/api/insights/{id}` | author, or member if shared |
| POST | `/api/insights/{id}/share` | author only; idempotent |

## Playbook

| Method | Path | Role |
| --- | --- | --- |
| POST | `/api/orgs/{org_id}/playbook` | member |
| GET | `/api/orgs/{org_id}/playbook?status=draft\|approved` | member |
| GET | `/api/playbook/{id}` | member |
| POST | `/api/playbook/{id}/approve` | owner, manager; requires ≥1 discovery question |
| PATCH | `/api/playbook/{id}` | author/reviewer on drafts; reviewer on approved (creates v+1 draft) |

The approver is always the verified caller. `status`/`approved_by` supplied by a client are ignored.

## Approved messaging

| Method | Path | Role |
| --- | --- | --- |
| POST | `/api/orgs/{org_id}/messaging` | owner, manager, marketing |
| GET | `/api/orgs/{org_id}/messaging` | member (drafts only for authoring roles) |
| PATCH | `/api/messaging/{id}` | owner, manager, marketing (drafts only) |
| POST | `/api/messaging/{id}/publish` | owner, manager |
| POST | `/api/orgs/{org_id}/messaging/check-claims` | member |

`check-claims` is a term-overlap heuristic and says so in its response; it never rewrites a claim.

## Audit

| Method | Path | Role |
| --- | --- | --- |
| GET | `/api/orgs/{org_id}/audit?limit=50` | owner, manager |

## Real-time

`WS /ws?token=<jwt>`

- Token verified before accept; invalid → close `4401`.
- Subscribes to every organization the verified user is an active member of. The client cannot choose an organization.
- `{"type":"subscribed","orgs":[…],"user_id":"…"}` on connect.
- Events: `{id, seq, type, resource, resource_id, org_id, actor_id}` — no content.
- `ping` → `{"type":"pong","orgs":[…],"changed":bool}`; reconnect when `changed`.

Event types: `insight.shared`, `conversation.shared`, `playbook.drafted`, `playbook.updated`, `playbook.approved`, `messaging.drafted`, `messaging.published`, `member.joined`, `member.revoked`, `org.created`.

Clients treat events as invalidations and refetch. Duplicate or missed events are harmless.
