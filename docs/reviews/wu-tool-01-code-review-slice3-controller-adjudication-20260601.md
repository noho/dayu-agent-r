# WU-TOOL-01 Slice 3 Code Review Controller Adjudication

## Gate

- Work unit: WU-TOOL-01 Duplicate Governance Concurrency and Cross-attempt Semantics
- Slice: Slice 3 - Governed Event / Diagnostic / Trace Scope
- Gate: code review
- Controller role: adjudication only；不直接实施 specialist code change。

## Inputs

- Approved plan: `docs/host/wu-tool-01-attempt-scoped-duplicate-governance-plan.md`
- Accepted Slice 1 commit: `bd782be`
- Accepted Slice 2 commit: `5f09506`
- Implementation report: `docs/reviews/wu-tool-01-implementation-slice3-codex-20260601.md`
- Code review:
  - `docs/reviews/wu-tool-01-code-review-slice3-mimo-20260601.md`
  - `docs/reviews/wu-tool-01-code-review-slice3-ds-20260601.md`

## Accepted Blocking Findings

CR3-1 and CR3-2 are accepted as blocking findings.

- CR3-1: `ToolRuntimeExecutor._diagnostic_refs_for_duplicate()` uses `duplicate_decision.message` instead of `duplicate_decision.diagnostic_message`. This violates approved plan section 7.11, which requires duplicate diagnostic emitter message to use `policy.messages.attempt_scope_diagnostic`.
- CR3-2: `tests/host/test_toolruntime_diagnostics.py::test_candidate_and_ack_carry_duplicate_diagnostic_refs` asserts the diagnostic record message equals the hard-stop action message. The test must instead configure and assert `attempt_scope_diagnostic` for the diagnostic record while keeping policy decision / governed failure outcome assertions on the hard-stop message.

## Accepted Non-blocking Findings

- The null guard in `_diagnostic_refs_for_duplicate()` should be corrected together with CR3-1 so it checks `diagnostic_message`.
- `_duplicate_decision_json()` retaining `diagnostic_message` is acceptable and should not be removed.

## Passed Areas

- `TOOL_CALL_GOVERNED` payload already carries machine-readable `duplicate_scope`.
- `tool_trace.py` preserves `duplicate_scope` into `trace_summary`, and hot/cold trace tests cover it.
- Accept barrier tests cover governed payload duplicate scope and same attempt prior refs.
- No durable duplicate ledger, EventLog duplicate reconstruction, schema change, compatibility wrapper/re-export, untyped signatures, or README scope expansion was found.

## Required Fix

The fix must be narrow:

- `dayu/host/tool_runtime.py`: restore `_diagnostic_refs_for_duplicate()` to require and emit `duplicate_decision.diagnostic_message`.
- `tests/host/test_toolruntime_diagnostics.py`: configure both a hard-stop message and an `attempt_scope_diagnostic`; assert policy decision / governed failure outcome use hard-stop message, and diagnostic record uses `attempt_scope_diagnostic`.
- Update or add a fix artifact at `docs/reviews/wu-tool-01-fix-slice3-codex-20260601.md`.

## Decision

Slice 3 does not pass code review yet. Enter fix loop for CR3-1 and CR3-2 only.
