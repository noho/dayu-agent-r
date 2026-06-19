# Implementation Artifact: Compact Rejected Attempt Diagnostic Artifact

- **Gate**: implementation
- **Work unit**: Conversation Memory compact rejected attempt diagnostics
- **Design doc**: `docs/host/conversation-memory-smoke-compact-followup.md`
- **Plan**: `docs/reviews/wu-cm-compact-rejected-diagnostic-plan-20260619-124435.md`
- **Plan review follow-up artifacts**:
  - `docs/reviews/plan-review-20260619-131234.md`
  - `docs/reviews/plan-review-20260619-131325.md`
- **Timestamp**: 20260619-143551

## Scope Implemented

Implemented a Host-only observability path for compact rejected attempts:

- `run_compaction_operation()` now builds an in-memory `CompactionRejectedAttemptDiagnostic` for proposal/material projection failures without changing compact accept/reject/fallback decisions.
- Rejected-attempt diagnostics can be written as content-addressed JSON artifacts through `LocalArtifactStore.write_artifact_bytes()` and linked through `PayloadStore.write_payload_descriptor_for_artifact()`.
- Proactive dispatch and reactive Engine ingest write the diagnostic artifact in the same SQLite transaction as the associated `CONTEXT_COMPACTION_ATTEMPT_REJECTED` EventLog row when a diagnostic is present.
- EventLog canonical payload carries only small structured fields: diagnostic artifact ref/digest, failure stage, diagnostic suffix, parser/validator, exception class/message, offending block locator, text digest/length, and material pack digest.
- Raw `REFERENCE_CONTINUITY` block text is stored only inside the Host diagnostic artifact JSON.

## Changed Files

- `dayu/host/compaction_operation.py`
- `dayu/host/context_events.py`
- `dayu/host/dispatch.py`
- `dayu/host/engine_ingest.py`
- `tests/host/test_compaction_operation.py`
- `tests/host/test_context_compact_events.py`
- `dayu/host/README.md`
- `tests/README.md`

## Plan Review Findings Addressed

- **AgentMiMo F1 / AgentDS F2: missing tests**: fixed by adding payload validator tests and a durable artifact readback test for `previous_compacted_view` parse failure with `proposal_manifest_ref=None`.
- **AgentDS F1: reactive diagnostic wiring in wrong method**: fixed by moving diagnostic artifact write from `_append_reactive_compaction_requested_event()` to `_append_reactive_compaction_attempt_rejected_event()`.
- **Non-blocking helper duplication**: left in place for this slice. The duplicated helpers are small projection helpers local to dispatch and reactive ingest; extracting them would create a wider public helper surface without changing behavior. Classify as residual risk assigned to code review gate.

## Validation

Commands run after implementation:

```bash
source .venv/bin/activate && pytest tests/host/test_context_compact_events.py tests/host/test_compaction_operation.py
```

Result: `87 passed`.

```bash
source .venv/bin/activate && pyright
```

Result: `0 errors, 0 warnings, 0 informations`.

```bash
git diff --check
```

Result: no output.

## Docs Decision

- `dayu/host/README.md` updated because `dayu/host/` behavior changed and the Host developer manual owns compact diagnostic artifact boundaries.
- `tests/README.md` updated because test coverage facts changed.
- Root `README.md` not updated: this change adds Host internal durable diagnostics, not a new end-user command, CLI flag, or user-visible workflow.

## Residual Risks

- **Production compact root cause**: assigned to later work unit. This slice does not fix `previous reference continuity text is invalid`, parser strictness, accept barrier, fallback tier, memory projection semantics, or production compact behavior.
- **Diagnostic helper duplication**: assigned to code review gate. If deepreview classifies it as material maintainability risk, fix in the review loop.
- **Artifact file orphan after SQL rollback**: tracked by existing artifact maintenance model. Descriptor and EventLog share the same transaction; a file-only orphan remains possible after artifact publish followed by SQL rollback, and storage maintenance handles orphan artifact candidates.

## Completion Status

Implementation slice complete and ready for code review gate.
