# WU-AUDIT-01 Planning Handoff

## Gate

- Workflow: phaseflow / gateflow
- Current gate: planning
- Work unit: WU-AUDIT-01 Purge Audit Cross-medium Orphan Reconciliation
- Design source: docs/host/design.md
- Control document: docs/host/host-core-followup-implementation-control.md
- Required plan artifact: docs/host/wu-audit-01-purge-audit-reconciliation-plan.md

## Controller Role Boundary

You are the planning specialist. Produce a handoff-ready, code-generation-ready plan only.
Do not edit source code, tests, README, schema, or control document.
Do not commit, push, create PR, or enter implementation.

## Motivation And Direct Evidence

The work unit remains real. Current code does not implement the design source's started / completed / failed purge audit model.

Direct evidence:

- docs/host/design.md states purge audit JSONL is destructive operation flow, not purge completion truth. It requires purge_started before destructive attempt, purge_completed only after SQLite tombstone commit, and audit analyze / query to treat started-only without tombstone as incomplete.
- dayu/host/durable/purge.py currently calls request.audit_recorder.record_purge_tombstone_audit inside _insert_tombstone_and_idempotency before insert_purge_tombstone and before the SQLite transaction commits.
- dayu/host/audit.py currently writes a single line kind purge_tombstone with source_eventlog_facts_purged=True.
- tests/host/test_purge_session.py covers audit append failure before tombstone success, but does not cover audit JSONL append success followed by SQLite tombstone insert or commit failure.
- There is no production audit analyze/query path found for classifying started-only, completed-with-tombstone, or failed purge attempts.

Root problem:

Audit JSONL append and SQLite tombstone commit are different durable media. A JSONL line can be appended and then SQLite tombstone insert/commit can fail, leaving an orphan audit line that currently looks like purge completion.

## Design Constraints

Use these constraints from docs/host/design.md and the control document:

- Host durable store remains the purge completion truth.
- Audit JSONL must not become Host durable truth.
- Projection, audit, tool trace, read model, outbox, and memory must not reverse-depend into EventLog truth.
- purge_session remains the only destructive exception to EventLog retention.
- Do not broaden this into a generic audit pipeline redesign.
- Do not introduce compatibility code for old schema or old audit names unless the current work unit explicitly needs a fresh schema change.
- Public contracts, durable schema, and state-machine effects require explicit plan decisions and tests.

## Required Plan Content

The plan must be code-generation-ready and include:

- Goal, non-goals, and why the motivation is still valid.
- Affected files and modules with allowed changes.
- Exact contract decisions for purge_started, purge_completed, and optional purge_failed, including field names, digest/ref semantics, and how completed references tombstone id and digest.
- Durable schema decision: whether host_purge_tombstones needs new fields, or whether completed line can be written after commit without tombstone schema mutation. Explain the tradeoff.
- Transaction and failure ordering: where started, SQLite tombstone commit, completed, and failed are emitted; what happens if completed append fails after tombstone commit.
- Analyze/query/diagnostic scope: define the smallest production API/helper needed to classify started-only, completed-with-tombstone, and failed without making JSONL truth.
- Implementation slices small enough for one implementation pass and one review pass each.
- Tests and validation commands, including a failure-injection test where started audit append succeeds but SQLite tombstone insert or commit fails, and assertions that purge is not reported completed.
- README/doc sync decision for dayu/host/README.md and tests/README.md if touched.
- Stop conditions and blocking open questions, if any.

## Expected Output

Write the plan to docs/host/wu-audit-01-purge-audit-reconciliation-plan.md.

Completion report should include:

- Plan artifact path.
- Whether the plan is handoff-ready.
- Any blocking open questions.
- Any residual risks that must be assigned before implementation.
