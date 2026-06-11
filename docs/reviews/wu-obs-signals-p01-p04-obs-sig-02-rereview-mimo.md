# WU-OBS-SIGNALS-01 / OBS-SIG-02 Fix Re-Review — AgentMiMo

## Scope

- Work unit: `WU-OBS-SIGNALS-01`
- Slice: `OBS-SIG-02` / P02 Tool Duration Signal
- Gate: fix re-review after controller adjudication
- Accepted finding: MIMO-F1 — failed / cancelled / governed-error result facts did not assert `tool_timing`
- Fix artifact: `docs/reviews/wu-obs-signals-p01-p04-obs-sig-02-fix-codex.md`
- Reviewer: AgentMiMo
- Re-review artifact: `docs/reviews/wu-obs-signals-p01-p04-obs-sig-02-rereview-mimo.md`

## 直接证据

Controller adjudication（`docs/reviews/wu-obs-signals-p01-p04-obs-sig-02-code-review-controller-adjudication.md`）接受 MIMO-F1：`test_failed_cancelled_and_governed_error_are_accepted_as_result_facts` 应对 failed / cancelled / governed-error 三个 accepted payload 断言 `tool_timing` 的 expected limited signal shape。

## Accepted Finding Recheck

### MIMO-F1: failed / cancelled / governed-error 的 `tool_timing` 断言

**验证状态：FIXED ✅**

**直接证据（`tests/host/test_toolruntime_accept_barrier.py` diff）：**

1. `_missing_tool_timing()` helper 函数新增（行 1535-1550），构造预期的 missing-meta limited signal shape：
   - `schema_version = 1`
   - `status = "missing_tool_result_meta"`
   - `started_at = None` / `finished_at = None` / `duration_ms = None` / `duration_source = None`

2. `test_failed_cancelled_and_governed_error_are_accepted_as_result_facts` 新增三行断言：
   - `assert payloads[0]["tool_timing"] == _missing_tool_timing()` — failed payload
   - `assert payloads[1]["tool_timing"] == _missing_tool_timing()` — cancelled payload
   - `assert payloads[2]["tool_timing"] == _missing_tool_timing()` — governed-error payload

3. 测试 fixture 辅助函数同步补全 `tool_timing` 参数：
   - `_completed_candidate()` 新增 `tool_timing=_missing_tool_timing()`
   - `_fact_kind_candidate()` 新增 `tool_timing=_missing_tool_timing()`
   - `test_tool_accept_result_rejects_payload_ref_digest_mismatch` 新增 `tool_timing=_missing_tool_timing()`

**结论：** 三个 accepted payload 的 `tool_timing` 均已断言，expected value 与 producer `_tool_timing_from_meta(None)` 在 missing meta 路径产生的 shape 完全一致。Fix 精确命中 controller adjudication 要求。

## New Findings

**无新 finding。**

- Fix 仅在测试文件中新增断言和 helper，未修改生产代码。
- 新增的 `_missing_tool_timing()` helper 与生产代码 `_tool_timing_from_meta(None)` 返回的 shape 语义一致，不存在断言与实现不同步的风险。
- 测试 fixture 补全 `tool_timing` 参数是 `ToolAcceptResult` dataclass 新增必填字段后的必要构造适配，不改变测试语义。

## Residual Risk

| 风险 | 状态 |
|---|---|
| Missing `ToolResultMeta` 的工具产生 `missing_tool_result_meta` limited signal | 不变；这是 intentional signal，analyzer 可据此报告 limited coverage |
| Analyzer latency aggregation（median/p99/distribution） | 不变；属于 WU-OBS-00，OBS-SIG-02 不实现 |
| P03 failure metadata / P04 partial tool-call signal | 不变；未实现，scope creep 评估通过 |

## Validation

```bash
source .venv/bin/activate && pytest tests/host/test_toolruntime_accept_barrier.py tests/host/test_tool_trace_projection.py tests/host/test_phase6_toolruntime_integration.py tests/host/test_toolruntime_executor.py -v
```

结果：**80 passed in 0.62s**

```bash
source .venv/bin/activate && pyright
```

结果：**0 errors, 0 warnings, 0 informations**

测试全部通过，pyright 零错误。Fix 为 test-only，未改变生产行为。

## Verdict

**PASS**

MIMO-F1 已修复。三个 accepted payload（failed / cancelled / governed-error）均断言 `tool_timing == _missing_tool_timing()`，与 producer 在 missing meta 路径产生的 limited signal shape 一致。Fix 为纯测试断言新增，未修改生产代码，未引入新问题。整体 OBS-SIG-02 仍严格限于 P02 范围，未实现 P03/P04/analyzer。等待 controller 裁决。
