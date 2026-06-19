# Code Review Adjudication: Compact Rejected Attempt Diagnostic Artifact

- **Gate**: code review fix/adjudication
- **Work unit**: Conversation Memory compact rejected attempt diagnostics
- **Reviewed artifacts**:
  - `docs/reviews/code-review-20260619-143711.md`
  - `docs/reviews/code-review-20260619-143853.md`
- **Timestamp**: 20260619-144111

## Finding Status

### AgentMiMo 1 - Recovery tier rejected attempts not written to EventLog

- **Decision**: `deferred-with-owner`
- **Status**: `未修复`
- **Owner / destination**: later recovery-tier compact audit diagnostics work unit.
- **Reason**: The finding is evidence-based for the broader branch, but it is outside this narrow slice. Fixing it safely requires defining cross-tier attempt numbering, failed payload `attempt_count` semantics, stale-result handling, and tests for recovery tier success/failure/cancellation. That crosses from rejected-attempt diagnostic artifact wiring into recovery-tier audit semantics. Current slice remains limited to diagnostic artifact generation and EventLog small-field projection for attempts already emitted as rejected events.

### AgentMiMo 2 - Recovery tier missing tests

- **Decision**: `deferred-with-owner`
- **Status**: `未修复`
- **Owner / destination**: same later recovery-tier compact audit diagnostics work unit.
- **Reason**: The missing tests are real for the broader recovery-tier path. They are not required to prove the current artifact path, which is covered by `test_rejected_attempt_diagnostic_captures_invalid_previous_reference`.

### AgentMiMo 3 - Session stale recovery result protection

- **Decision**: `deferred-with-owner`
- **Status**: `未修复`
- **Owner / destination**: same later recovery-tier compact audit diagnostics work unit.
- **Reason**: Same ownership as Finding 1. The current slice does not change recovery-tier execution or stale-result state transition.

### AgentMiMo 4 - Completed attempt count readability

- **Decision**: `deferred-with-owner`
- **Status**: `未修复`
- **Owner / destination**: same later recovery-tier compact audit diagnostics work unit.
- **Reason**: This is a readability/testability risk in recovery-tier attempt numbering, not a current diagnostic artifact defect.

### AgentMiMo 5 - Recovery tier operation_id attribution

- **Decision**: `deferred-with-owner`
- **Status**: `未修复`
- **Owner / destination**: same later recovery-tier compact audit diagnostics work unit.
- **Reason**: Needs to be decided together with cross-tier rejected EventLog emission and attempt numbering.

### AgentDS 1 - Artifact file orphan after SQL rollback

- **Decision**: `deferred-with-owner`
- **Status**: `未修复`
- **Owner / destination**: existing storage maintenance / artifact orphan model.
- **Reason**: This was explicitly identified and accepted in the plan as a residual risk. The current design keeps descriptor and EventLog writes in the same SQLite transaction, avoiding descriptor-without-event. File-only artifact orphan after publish-then-rollback is already the artifact storage lifecycle tradeoff and not specific to this diagnostic artifact.

### AgentDS 2 - Duplicated diagnostic offending helper functions

- **Decision**: `rejected-with-reason`
- **Status**: `未修复`
- **Reason**: The duplication is small and local to two Host entrypoints. Extracting it would either create a public projection helper for six trivial field accesses or introduce a new private cross-module helper solely for one slice. That increases API surface more than it reduces current risk. Revisit only if a third caller appears or code review finds behavior drift.

### AgentDS 3 - Offending block ordinal boundary guard

- **Decision**: `accepted`
- **Status**: `已修复`
- **Fix**: `_offending_block_artifact_json()` now returns `None` when `block_ordinal` is negative or outside `previous_blocks`, preventing Python negative indexing and out-of-range diagnostic construction failure.

## Validation After Fix

```bash
source .venv/bin/activate && pytest tests/host/test_context_compact_events.py tests/host/test_compaction_operation.py
```

Result: `87 passed`.

```bash
source .venv/bin/activate && pyright
```

Result: `0 errors, 0 warnings, 0 informations`.

## Residual Risks

- Recovery-tier rejected-attempt EventLog coverage is assigned to a later recovery-tier audit diagnostics work unit.
- Artifact file-only orphan after SQL rollback remains assigned to existing artifact maintenance ownership.
- Production compact root cause for invalid previous reference continuity remains assigned to the separate production memory compact failure work unit.

## Completion Status

Ready for code review re-review gate.
