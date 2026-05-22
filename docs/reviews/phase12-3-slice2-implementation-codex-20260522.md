# Phase 12.3 Slice 2 Implementation - AgentCodex - 2026-05-22

## 结论

SLICE_COMPLETE

## 改动摘要

- 在 `dayu/host/context_budget.py` 增加 `UsageObservationDiagnostic` 与 `build_usage_observation_diagnostic`，用于生成 post-call usage observation 的稳定 digest、policy ref、estimator digest、估算输入 token、prompt token delta 与状态。
- 在 `dayu/host/engine_ingest.py` 扩展 `USAGE_REPORTED` projection signal payload，保留原有 `attempt_id`、`execution_id`、`iteration_id`、`prompt_tokens`、`completion_tokens`、`total_tokens`，新增 `session_id`、`run_id`、`provider_request_id=None`、`policy_ref`、`estimator_digest`、`estimated_input_tokens`、`usage_observation_status`、`usage_observation_digest` 与 `prompt_token_delta`。
- Host ingest 在有 `ContextBudgetPolicy` 且可读取 input event 时重建 conservative estimate；policy 缺失、input event 缺失、payload 不可读或估算失败时降级为 `estimate_unavailable`，projection 仍提交，Run / Attempt 状态不变。
- Host ingest 对异常 usage token 做 `usage_invalid` 诊断降级，projection 仍提交，不把异常 usage 升级为 Run 失败。
- 未修改 Engine `RunnerUsageRecordedData` / `UsageReportedData` 字段，未修改 Engine Agent loop，未新增 usage config override / `supports_usage`，未新增 Host public API、durable state machine schema 或 durable table。

## 测试更新

- 更新 `tests/host/test_context_budget.py` 覆盖 usage observation diagnostic helper：
  - 计算 `prompt_token_delta=prompt_tokens-estimated_input_tokens`。
  - 缺少估算时 `prompt_token_delta=None`。
  - helper 不调用或改变 `decide_context_budget` 的既有 decision。
- 更新 `tests/host/test_engine_ingest_mapping.py`：
  - `USAGE_REPORTED` projection signal 包含新增关联字段，且 Run / Attempt 保持 `RUNNING`。
  - 有 policy 和可读 input event 时 `policy_ref` / `estimator_digest` / `estimated_input_tokens` 非空。
  - 无 policy 时 `policy_ref="none"` 且 projection 成功。
  - input event 缺失或 payload 不可读时状态为 `estimate_unavailable` 且 projection 成功。
  - provider request id 缺失时写 `None`。
  - usage token 异常时状态为 `usage_invalid` 且不改变 Run / Attempt 状态。
- Engine OpenAI usage tests 未改生产 contract，仅作为 regression 验证。

## 验证结果

- `source .venv/bin/activate && pytest tests/host/test_engine_ingest_mapping.py tests/host/test_context_budget.py -q`
  - 结果：62 passed
- `source .venv/bin/activate && pytest tests/engine/runners/openai/test_stream_usage_capability_gating.py tests/engine/runners/openai/test_non_stream_response.py tests/engine/runners/openai/test_sse_usage_recorded.py -q`
  - 结果：11 passed
- `source .venv/bin/activate && python -m pyright dayu/host tests/host tests/engine/runners/openai`
  - 结果：0 errors, 0 warnings, 0 informations
- `git diff --check`
  - 结果：通过，无输出

## README 决策

- 已更新 `dayu/host/README.md` 的 Context Governance 说明，补齐 usage projection 是 post-call observation、缺失估算不影响 Run / Attempt 状态、不回改当前 dispatch decision 的稳定行为。
- 未更新 `dayu/engine/README.md`：现有 stream usage capability、usage event 与 malformed usage 说明仍准确，且本 slice 未改变 Engine 职责。
- 未更新 `tests/README.md`：本 slice 只增加 focused Host ingest/context budget 测试，不改变测试分层、运行方式或维护规则。

## Residual Risk

- `provider_request_id` 当前按设计写 `None`，因为 Engine usage event contract 不提供该字段；如后续需要真实 provider request id，必须进入单独 contract design gate。
- 当前 observation estimate 使用 Host ingest 可重建的当前 input event 与 context budget policy，未把 usage 写成 canonical fact，也不作为当前 dispatch decision 的回溯依据；后续 Context Governance consumer 若需要更完整的 dispatch-time RunInputBuilder 估算快照，应在后续 phase 明确 owner 与持久化边界。

## Fix Addendum - P12.3-S2-F1/F2/F3

### 修复点

- F1：`dayu/host/engine_ingest.py::_estimate_usage_observation_input` 的降级异常范围从 `Exception` 收窄为 `HostDurableError | TypeError | ValueError`，避免吞掉 `AttributeError`、`KeyError` 等编程错误。
- F2：`UsageObservation` 新增严格类型字段 `iteration_id: str`，并纳入 `build_usage_observation_diagnostic` 生成的 observation digest；invalid usage observation digest 同步纳入 `iteration_id`。`tests/host/test_context_budget.py` 增加同一 attempt 下不同 iteration 产生不同 digest 的断言。
- F3：修正 `_display_text_from_input_event` docstring，将实际异常类型标注为 `HostDurableError`。

### 验证结果

- `source .venv/bin/activate && pytest tests/host/test_engine_ingest_mapping.py tests/host/test_context_budget.py -q`
  - 结果：62 passed
- `source .venv/bin/activate && pytest tests/engine/runners/openai/test_stream_usage_capability_gating.py tests/engine/runners/openai/test_non_stream_response.py tests/engine/runners/openai/test_sse_usage_recorded.py -q`
  - 结果：11 passed
- `source .venv/bin/activate && python -m pyright dayu/host tests/host tests/engine/runners/openai`
  - 结果：0 errors, 0 warnings, 0 informations
- `git diff --check`
  - 结果：通过，无输出
