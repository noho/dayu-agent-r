# WU-OBS-SIGNALS-01 / OBS-SIG-02 Code Review Controller Adjudication

## Scope

- Work unit: `WU-OBS-SIGNALS-01`
- Slice: `OBS-SIG-02` / P02 Tool Duration Signal
- Implementation artifact: `docs/reviews/wu-obs-signals-p01-p04-obs-sig-02-implementation-codex.md`
- Code review artifacts:
  - `docs/reviews/wu-obs-signals-p01-p04-obs-sig-02-code-review-mimo.md`
  - `docs/reviews/wu-obs-signals-p01-p04-obs-sig-02-code-review-ds.md`

## Verdict

Code review completed with one accepted low-risk test coverage finding. A fix gate is required before accepting the slice.

## Accepted Findings

### MIMO-F1: Failed / cancelled result facts do not assert `tool_timing`

- Source: AgentMiMo code review.
- Severity: minor / low.
- Finding: `test_failed_cancelled_and_governed_error_are_accepted_as_result_facts` verifies result fact kind and governed-error policy, but does not assert that the failed, cancelled, and governed-error accepted payloads contain the expected `tool_timing` limited signal.
- Direct evidence: `tests/host/test_toolruntime_accept_barrier.py` reads the accepted result payloads but only checks `tool_fact_kind` and `policy_decision`.
- Adjudication: accepted.
- Reason: OBS-SIG-02 explicitly covers completed / failed / cancelled terminal outcomes. Although the production path is unified, tests should follow the producer boundary and assert that non-completed result facts also carry the additive timing signal.
- Required fix: add focused assertions for `tool_timing` on failed, cancelled, and governed-error payloads. The expected value should match the existing missing-meta limited signal shape.

## Non-Blocking Observations

- DS observation about producer/consumer validation duplication is not accepted as a current fix. The two layers intentionally have different error contracts (`ValueError` vs `HostDurableError`) and the current shape is small.
- DS observation about validation-only helper return values is not accepted as a current fix. The pattern is consistent with existing required-field helpers and does not affect behavior.
- Defensive `ToolAwaitingOutcome` and negative-duration guards remain intentionally present.

## Fix Gate Instructions

AgentCodex should only add the accepted test assertions and update the fix artifact:

- Production code should not change unless the new assertion exposes a real implementation defect.
- Suggested target test: `tests/host/test_toolruntime_accept_barrier.py::test_failed_cancelled_and_governed_error_are_accepted_as_result_facts`.
- Suggested validation:
  - `source .venv/bin/activate && pytest tests/host/test_toolruntime_accept_barrier.py tests/host/test_tool_trace_projection.py tests/host/test_phase6_toolruntime_integration.py tests/host/test_toolruntime_executor.py`
  - `source .venv/bin/activate && pyright`

The fix artifact should be written to `docs/reviews/wu-obs-signals-p01-p04-obs-sig-02-fix-codex.md`.

## Residual Risk

- `missing_tool_result_meta` remains an intentional limited signal for tools that do not provide `ToolResultMeta`.
- Analyzer latency aggregation remains owned by WU-OBS-00 and is out of scope for this slice.
