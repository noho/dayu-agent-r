# WU-TOOL-01 Slice 3 Code Re-review Controller Adjudication

## Gate

- Work unit: WU-TOOL-01 Duplicate Governance Concurrency and Cross-attempt Semantics
- Slice: Slice 3 - Governed Event / Diagnostic / Trace Scope
- Gate: code re-review
- Controller role: adjudication only；不直接实施 specialist code change。

## Inputs

- Approved plan: `docs/host/wu-tool-01-attempt-scoped-duplicate-governance-plan.md`
- Implementation report: `docs/reviews/wu-tool-01-implementation-slice3-codex-20260601.md`
- First review:
  - `docs/reviews/wu-tool-01-code-review-slice3-mimo-20260601.md`
  - `docs/reviews/wu-tool-01-code-review-slice3-ds-20260601.md`
- Controller first review adjudication: `docs/reviews/wu-tool-01-code-review-slice3-controller-adjudication-20260601.md`
- Fix report: `docs/reviews/wu-tool-01-fix-slice3-codex-20260601.md`
- Re-review:
  - `docs/reviews/wu-tool-01-code-rereview-slice3-mimo-20260601.md`
  - `docs/reviews/wu-tool-01-code-rereview-slice3-ds-20260601.md`

## Adjudication

CR3-1 and CR3-2 are closed. Slice 3 code re-review passes.

- CR3-1 closed: `_diagnostic_refs_for_duplicate()` uses `duplicate_decision.diagnostic_message`, preserving `policy.messages.attempt_scope_diagnostic` for duplicate diagnostics.
- CR3-2 closed: `test_candidate_and_ack_carry_duplicate_diagnostic_refs` separately configures hard-stop action message and `attempt_scope_diagnostic`, then asserts policy decision / governed failure outcome use the action message while diagnostic record uses the diagnostic message.
- `tool_trace.py` duplicate scope projection is accepted: `duplicate_scope` is preserved from canonical payload into `trace_summary`, with hot/cold trace assertions.
- Accept barrier and duplicate governance tests cover attempt scope and same attempt prior refs without EventLog duplicate reconstruction.

## Non-blocking Notes

- Fix artifact originally listed `dayu/host/tool_runtime.py` as a changed file even though the final diff has no net change there; the artifact now records that the working-tree regression was restored to accepted behavior and the file has no final net diff.
- `ToolTraceDiagnosticRecord` still has no structured metadata; this remains accepted because machine-readable duplicate scope is carried by `TOOL_CALL_GOVERNED.payload.duplicate_scope` and tool trace summary.

## Controller Verification

Controller ran:

```bash
source .venv/bin/activate && python -m pytest tests/host/test_toolruntime_diagnostics.py tests/host/test_toolruntime_accept_barrier.py tests/host/test_tool_trace_projection.py tests/host/test_toolruntime_duplicate_governance.py
source .venv/bin/activate && pyright
```

Result:

- `tests/host/test_toolruntime_diagnostics.py` + `tests/host/test_toolruntime_accept_barrier.py` + `tests/host/test_tool_trace_projection.py` + `tests/host/test_toolruntime_duplicate_governance.py`: 52 passed
- `pyright`: 0 errors, 0 warnings, 0 informations

## Decision

Slice 3 reaches accepted checkpoint and may be committed.
