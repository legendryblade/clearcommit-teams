# Engineering decision records

Concise, reviewable records. Each states the problem, the evidence, the decision,
the alternatives rejected, and how the result is verified. Records are appended,
never edited after the fact — a later record supersedes an earlier one.

---

## DR-0001 — Phase A scope: build the execution control plane on the existing repository

**Date:** 2026-10-27
**Status:** accepted

### Problem

ClearCommit Enterprise requires an execution control plane that the existing
ClearCommit Teams repository does not have. The build plan also requires that
success be established from independent evidence, that approvals be bound to
an immutable scope, and that `Running`, `Verifying`, `Succeeded` and `Unknown`
never collapse into a generic "done" flag.

### Evidence (observed)

- `server/` exposes five transactional resource routers (`orgs`,
  `conversations`, `insights`, `playbook`, `messaging`, `commitments`). There
  is no execution, step, approval or verification entity.
- `supabase/migrations/0001…0005` create profiles, organizations, memberships,
  invitations, conversations, utterances, coaching_insights, playbook_entries,
  approved_messaging, audit_events, idempotency_records, commitments and
  commitment_events. No workflow tables.
- The reusable mechanics the build plan names already exist and pass tests:
  404-not-403 tenant policy (`server/dependencies.py:70`), token-only identity
  (`server/security.py`), append-only audit (`server/audit.py`),
  idempotency (`server/idempotency.py`), RLS context (`server/db.py`).
- Baseline before this work: 190 pytest + 12 node tests passing at `344b631`.

### Decision

Build Phase A — the execution control plane — as new modules on the existing
FastAPI + SQLAlchemy service, reusing the tenancy, identity, audit and
idempotency mechanics unchanged. No new stack, no new deployment, no external
integration. Phase B (a real business-system integration) is deferred until a
concrete free-tier target exists.

### Alternatives rejected

1. **Rewrite on React + TypeScript + Temporal** (build plan §9 default). Rejected:
   discards ~13,000 lines of verified tenancy and auth mechanics, and needs
   infrastructure the $50 credit cannot carry. The plan explicitly permits
   adapting to a sound existing architecture (§9, final paragraph).
2. **Breadth-first UI shells for all divisions.** Rejected: the directive forbids
   decorative UI over absent backend behaviour (§12, "A UI without working
   backend behaviour is not a complete feature"). It would also make the
   product appear more capable than it is.
3. **Voice-first.** Rejected for this phase: telephony is not free beyond trial
   minutes, and the build plan itself says voice must not be the foundation of
   the control plane (§5.I).

### Invariants introduced

- Execution states are a closed set; transitions are validated by code, not by
  model output.
- An approval names an exact `action_digest`. A decision is valid only for that
  digest; changing the action requires a new approval.
- A step cannot be marked succeeded without at least one passing verification
  run whose postcondition matches the step's declared postcondition.
- Cancellation stops eligible future work and never implies rollback.

### Security and operational implications

- Every new table carries `org_id` and mirrors the existing RLS policies.
- Cross-tenant reads return 404, consistent with every existing route.
- No new secret, no new external dependency, no new environment variable.

### Verification

Unit tests for the state machine (legal and illegal transitions), API tests for
tenant isolation, approval-scope reuse, and false-success rejection. Acceptance
is the full existing suite plus the new tests passing together.

### Uncertainty and reversal

The state machine's exact state set may evolve once a real workflow exists.
Reversal is deletion of `0006_execution_control.sql` and the new modules; no
existing table or route is modified, so the change is additive and reversible.

---

## DR-0002 � A conclusion needs every expected postcondition to have a result

**Date:** 2026-10-27
**Status:** accepted
**Supersedes:** the verification-completeness rule in DR-0001's implementation

### Problem

The first implementation derived an outcome from every verification run recorded
so far. Two failures followed, both found by tests before release:

1. A single passing read-back concluded `succeeded` while other expected checks
   had simply not been recorded yet. That is the false-success claim the product
   exists to prevent.
2. An `unknown` result was permanent. Once recorded, `unknown == 0` could never
   hold again, so a later real read-back could not close the run.

### Evidence (observed)

Both were reproduced at the HTTP boundary before the fix
(`tests/server/test_executions.py`), returning `succeeded` and a permanently
stuck `verifying` respectively.

### Decision

- Group runs **by postcondition** and keep only the newest result per
  postcondition. Later evidence supersedes earlier evidence about the same
  question.
- The expected set is the postconditions declared on the execution's steps, or
  the single postcondition the caller names when no step declares one.
- A **failure** is conclusive immediately: one unmet postcondition falsifies the
  claim regardless of other passes.
- **Success**, **partially_verified** and an all-unknown result are applied only
  when every expected postcondition has a result.
- Once an execution is terminal it stays terminal; a later read-back cannot
  retroactively promote it (409).

### Alternatives rejected

1. **Derive from all runs, never supersede.** Rejected: a resolved unknown would
   block a genuinely verified outcome forever.
2. **Let the last run decide.** Rejected: one late pass would erase an earlier
   failure, which is precisely how false success is reported.

### Verification

`tests/server/test_executions.py::test_one_failed_check_makes_the_outcome_failed_even_after_passes`
and `::test_partial_verification_is_not_success` pin both directions. Full suite
at time of record: 275 pytest + 12 node, all passing.

### Known uncertainty

The mapping from steps to expected postconditions assumes one postcondition per
concern. A real workflow may need several checks against one postcondition; that
will need an explicit cardinality, not a further heuristic.
