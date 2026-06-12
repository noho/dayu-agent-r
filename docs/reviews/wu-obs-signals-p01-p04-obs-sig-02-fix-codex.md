# WU-OBS-SIGNALS-01 / OBS-SIG-02 Fix Gate - AgentCodex

## Scope

- Work unit: `WU-OBS-SIGNALS-01`
- Slice: `OBS-SIG-02` / P02 Tool Duration Signal
- Gate: fix gate after controller adjudication
- Accepted finding fixed: `test_failed_cancelled_and_governed_error_are_accepted_as_result_facts` did not assert `tool_timing` on failed, cancelled, and governed-error result facts.
- Out of scope: production code changes, P03/P04 analyzer behavior, README expansion, commit, push, PR, and re-review.

## 直接证据

- Controller adjudication accepted only MIMO-F1: failed / cancelled / governed-error accepted payloads should assert the expected `tool_timing` limited signal.
- `tests/host/test_toolruntime_accept_barrier.py::test_failed_cancelled_and_governed_error_are_accepted_as_result_facts` already read accepted result payloads and asserted `tool_fact_kind` plus governed-error policy, but did not assert `payload["tool_timing"]`.
- Existing helper `_missing_tool_timing()` defines the expected limited signal shape:
  - `schema_version = 1`
  - `status = "missing_tool_result_meta"`
  - `started_at = None`
  - `finished_at = None`
  - `duration_ms = None`
  - `duration_source = None`

## 改动

- Updated `tests/host/test_toolruntime_accept_barrier.py::test_failed_cancelled_and_governed_error_are_accepted_as_result_facts`.
- Added focused assertions for all three accepted payloads:
  - failed payload `tool_timing == _missing_tool_timing()`
  - cancelled payload `tool_timing == _missing_tool_timing()`
  - governed-error payload `tool_timing == _missing_tool_timing()`
- Production code was not changed; the new assertions passed against the existing implementation.

## 验证

```bash
source .venv/bin/activate && pytest tests/host/test_toolruntime_accept_barrier.py tests/host/test_tool_trace_projection.py tests/host/test_phase6_toolruntime_integration.py tests/host/test_toolruntime_executor.py
```

Result: `80 passed in 0.62s`

```bash
source .venv/bin/activate && pyright
```

Result: `0 errors, 0 warnings, 0 informations`

Pyright also printed a version availability warning (`v1.1.409 -> v1.1.410`), which is not a type-check failure.

## README Decision

- `tests/README.md` was checked because `tests/` changed.
- No README update was needed: this fix only strengthens assertions inside an existing Host test and does not add a new test layer, command, fixture class, or maintenance convention.

## 风险 / 未覆盖项

- Remaining risk is unchanged from controller adjudication: tools that do not provide `ToolResultMeta` intentionally produce the limited `missing_tool_result_meta` signal.
- Analyzer latency aggregation remains out of scope for OBS-SIG-02 and owned by WU-OBS-00.
- This fix does not enter re-review and stops for controller adjudication as requested.
