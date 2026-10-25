# ClearCommit Teams — Scope

## Problem

Sales conversations contain the evidence a team needs to improve, but that
evidence is discarded or trapped in one person's notes. Managers get
summaries without proof; teams re-learn the same lessons; guidance lives in
someone's head rather than in a shared, reviewed artifact.

## What this project is

A Windows desktop workspace plus a shared team backend that turns finished
sales-conversation transcripts into **evidence-linked coaching**, and turns
the team's agreement about that coaching into a **manager-reviewed playbook**.

The loop: Discover → Learn → Align → Apply → Improve.

## In scope

### Local workspace (single user, offline)
- Import or type a finalized transcript; select the exact lines to analyze.
- Rule-based coaching that must cite the selected lines.
- Grounded question answering over the selected evidence.
- Playbook draft → reviewer + discovery questions → approval.
- Local persistence (SQLite) and team-level signal aggregates.
- Works with no network.

### Team workspace (networked)
- Accounts, organizations, invitations, memberships, roles
  (`owner`, `manager`, `sales_rep`, `marketing`).
- Conversations private by default; explicit share of a conversation or an
  insight.
- Review queue and approved playbook shared across clients.
- Approved-messaging drafts (marketing) and publishing (reviewers).
- Audit trail for sensitive actions.
- Live updates over an authenticated WebSocket.
- Honest offline state: writes disabled, unsaved changes never reported as
  saved.

## Out of scope (deliberately)

- Live audio capture, automatic transcription, machine translation.
- Individual performance scoring or employee ranking.
- CRM, Slack, or Teams integrations.
- Autonomous changes to company policy.
- Multi-agent orchestration, microservices, Kubernetes, Redis, brokers.
- Cloud object storage for recordings.

## Users

| Role | Needs |
| --- | --- |
| Sales rep | Learn from their own calls without being surveilled |
| Manager | Review proposed guidance; approve what the team will follow |
| Marketing | Keep approved product claims current; publish them |
| Owner | Control membership and access |

## Success criteria

1. Two independently authenticated clients in one organization complete
   insight → share → review → approval → shared playbook.
2. A user in another organization cannot read or write those records, even
   with valid ids.
3. A revoked member loses access immediately.
4. Raw conversations stay private until explicitly shared.
5. With the backend down, the client says it is unsynchronized and refuses to
   claim success.
6. Every claim in the README is reproducible from the documented commands.
