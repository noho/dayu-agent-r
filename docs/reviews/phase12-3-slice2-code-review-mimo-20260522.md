# Phase 12.3 Slice 2 Code Review - AgentMiMo - 2026-05-22

## Verdict

**PASS** — 无 blocking finding。

## 审查范围

未提交 diff 中属于 Phase 12.3 Slice 2 的改动（5 files, +637 / -3）：

- `dayu/host/context_budget.py` — 新增 `UsageObservationDiagnostic`、`build_usage_observation_diagnostic`、`_usage_observation_digest`、`_require_int`，新增状态常量
- `dayu/host/engine_ingest.py` — 扩展 `USAGE_REPORTED` projection signal payload，新增 `_usage_observation_diagnostic`、`_estimate_usage_observation_input`、`_invalid_usage_observation_digest`
- `tests/host/test_context_budget.py` — 新增 usage observation diagnostic 测试
- `tests/host/test_engine_ingest_mapping.py` — 新增 5 个 usage projection 场景测试
- `dayu/host/README.md` — 补齐 usage post-call observation 行为说明

## 逐项检查结果

### 1. Engine RunnerUsageRecordedData / UsageReportedData contract 不变

**PASS**。`git diff HEAD -- dayu/engine/` 无输出。`UsageReportedData` 仍为 `iteration_id / prompt_tokens / completion_tokens / total_tokens` 四字段（`dayu/engine/contracts/engine_events.py:274-286`）。`RunnerUsageRecordedData` 仍为 `prompt_tokens / completion_tokens / total_tokens` 三字段（`dayu/engine/contracts/runner_events.py:134-144`）。未引入 `provider_request_id` 或 usage config override。

### 2. USAGE_REPORTED 仍为 PROJECTION_SIGNAL，不改 Run / Attempt 状态

**PASS**。`engine_ingest.py:2057` 写 `event_class=EventClass.PROJECTION_SIGNAL`。所有 6 个 usage 相关测试均断言 `RunStatus.RUNNING` + `AttemptStatus.RUNNING` 不变。

### 3. payload 保留原字段并新增字段

**PASS**。`engine_ingest.py:2059-2074` payload 包含：
- 原字段：`attempt_id`、`execution_id`、`iteration_id`、`prompt_tokens`、`completion_tokens`、`total_tokens` ✓
- 新增字段：`session_id`、`run_id`、`policy_ref`、`estimator_digest`、`estimated_input_tokens`、`usage_observation_status`、`usage_observation_digest`、`prompt_token_delta`、`provider_request_id=None` ✓

### 4. 降级逻辑：policy 缺失 / input event 缺失 / 估算失败 / usage token 异常

**PASS**。四个降级路径均有测试覆盖且 projection 仍提交：

| 场景 | 状态 | 测试 |
|------|------|------|
| 无 policy | `estimate_unavailable`, `policy_ref="none"` | `test_usage_reported_without_policy_keeps_projection_non_failing` |
| input event 缺失 | `estimate_unavailable` | `test_usage_reported_missing_input_event_keeps_projection_non_failing` |
| payload 不可读 | `estimate_unavailable` | `test_usage_reported_unreadable_input_event_keeps_projection_non_failing` |
| usage token 异常 | `usage_invalid` | `test_usage_reported_invalid_tokens_keeps_projection_non_failing` |

Run / Attempt 状态在所有场景中保持 `RUNNING`。

### 5. diagnostic helper 设计

**PASS**。
- `UsageObservationDiagnostic` 是 frozen dataclass，严格类型，无 `Any`、无 extra payload bag ✓
- `build_usage_observation_diagnostic` 不调用 `decide_context_budget`，不修改 `BudgetEstimate` ✓
- 只计算 post-call diagnostic / calibration data ✓

### 6. 异常处理宽度

**无 blocker**。

- `engine_ingest.py:2129` — `_usage_observation_diagnostic` 捕获 `(TypeError, ValueError)`，这是 `UsageObservation.__post_init__` 和 `build_usage_observation_diagnostic` 的精确异常类型，宽度合理。
- `engine_ingest.py:2191` — `_estimate_usage_observation_input` 使用 `except Exception`，覆盖 `_display_text_from_input_event`（可能抛 `ValueError`）、`estimate_context_budget`（可能抛 `TypeError`/`ValueError`）以及 `_estimate_json_tokens` 内部的 `canonical_json_dumps` 异常。此路径只用于 diagnostic 估算重建，不修改任何状态，返回 `None` 后降级为 `estimate_unavailable`。过宽的 catch 在此上下文中可接受，因为：(a) 不影响 Run 状态；(b) 任何失败都正确降级；(c) `exc_info=True` 保留了 debug 信息。建议后续可收窄为具体异常类型，但非 blocking。

### 7. digest 稳定性

**PASS**。`_usage_observation_digest`（`context_budget.py:596-632`）使用 `sha256_digest_json` 计算，输入包含 observation 和 diagnostic 的确定性字段，使用 `observed_at.isoformat()` 序列化时间。`_invalid_usage_observation_digest`（`engine_ingest.py:3095-3133`）结构一致，确保 invalid 场景也有稳定 digest。

### 8. README

**PASS**。`dayu/host/README.md` 新增段落准确描述 Host usage projection 行为：post-call observation、不改变 Run/Attempt 状态、不回改 dispatch decision。未把 Host governance 写进 Engine 职责。

## 验证结果

- `pytest tests/host/test_engine_ingest_mapping.py tests/host/test_context_budget.py -q` — 62 passed ✓
- `pytest tests/engine/runners/openai/test_stream_usage_capability_gating.py tests/engine/runners/openai/test_non_stream_response.py tests/engine/runners/openai/test_sse_usage_recorded.py -q` — 11 passed ✓
- `pyright dayu/host tests/host tests/engine/runners/openai` — 0 errors, 0 warnings, 0 informations ✓
- `git diff --check` — 通过，无输出 ✓

## Non-blocking 建议

1. **`_estimate_usage_observation_input` 的 `except Exception`**（`engine_ingest.py:2191`）：当前可接受，但建议后续收窄为 `(TypeError, ValueError, KeyError, AttributeError)` 以提高可观测性。不属于本 phase scope。

## Residual Risk 确认

Implementation artifact 中列出的 residual risk 与审查结论一致：
- `provider_request_id` 按设计写 `None`，需单独 contract design gate 才能获取真实值。
- observation estimate 使用当前 input event 与 policy，未写为 canonical fact，不作为 dispatch decision 回溯依据。
