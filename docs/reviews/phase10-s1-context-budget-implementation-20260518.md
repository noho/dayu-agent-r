# Phase 10 Slice 1 Context Budget Implementation

- Date: 2026-05-18
- Work unit: Phase 10 Context Governance / Compaction
- Slice: Slice 1 Context Budget Policy, Estimator, Usage Observation
- Accepted plan commit: 31615df

## 修改摘要

- 新增 `dayu/host/context_policy.py`：
  - 定义 `ContextBudgetPolicy`、`ContextBudgetProvider`、`StaticContextBudgetProvider`、`ContextCompactionTriggerSource` 与 `default_context_budget_policy`。
  - `context_window_size` 与 `reserved_output_tokens` 只能通过 typed policy 显式传入；policy 构造期校验窗口、输出预留、hard threshold、最小保护量、per-run compact 上限与 `policy_ref`。

- 新增 `dayu/host/context_budget.py`：
  - 定义 conservative estimator 输入/输出类型、`ContextBudgetDecision`、`UsageObservation`。
  - 实现 `input_budget_tokens = context_window_size - reserved_output_tokens`。
  - 默认 safety margin 20%，soft threshold 80%，默认 hard threshold 为 `input_budget_tokens - minimum_protection_tokens`，显式 hard threshold 优先。
  - 估算器只消费 typed text / JSON / tool schema fragment view，不读取 Engine、metadata、extra payload 或 provider overflow。
  - `UsageObservation` 只作为 internal observation 类型，不参与阈值动态调整。

- 更新 `dayu/host/api.py`：
  - `HostLocalExecutionOptions` 新增可选 `context_budget_policy: ContextBudgetPolicy | None` typed 接收点。
  - Slice 1 只暴露 composition boundary，未接入 production orchestration。

- 更新 `dayu/host/durable/event_log.py`：
  - 新增 `count_committed_events_by_run_and_type(...)` 及 `EventLogStore` 同名方法。
  - 支持在同一 transaction 内按 `run_id + event_type + trigger_source` 统计 committed canonical facts。
  - 传入 `trigger_source` 时解析并校验 payload，payload 损坏或 trigger_source 非法时 fail-closed。

- 更新测试：
  - 新增 `tests/host/test_context_budget.py` 覆盖有效 policy、无效 policy、soft/hard threshold、显式 hard threshold、usage observation 不动态调整阈值、EventLog per-run trigger count。
  - 更新 `tests/host/test_public_contracts.py` 覆盖 `HostLocalExecutionOptions.context_budget_policy` typed 接收与拒绝错误类型。
  - 更新 `tests/host/test_engine_ingest_mapping.py` 明确 `USAGE_REPORTED` payload 未扩展，provider overflow `budget_state=None` 不成为 Host budget truth。

## 验证结果

- `source .venv/bin/activate && pytest tests/host/test_context_budget.py tests/host/test_public_contracts.py tests/host/test_engine_ingest_mapping.py -q`
  - 结果：73 passed。
- `source .venv/bin/activate && pyright`
  - 结果：0 errors, 0 warnings, 0 informations。
- `git diff --check`
  - 结果：通过，无 whitespace error。

## README 决策

本 slice 未更新 README。

原因：

- 本 slice 只新增 Phase 10 后续 orchestration 依赖的 Host typed policy / estimator / durable helper，并未改变当前用户可执行 workflow、CLI 命令、配置入口或 production dispatch 行为。
- `HostLocalExecutionOptions.context_budget_policy` 当前是可选 typed composition boundary；production Context Governance 尚未接入，不写未来设计到 README。

## 风险与未覆盖项

- Slice 1 未实现 Context Governance orchestration、pre-start compact、reactive recovery、compactor contract、compact artifact 或 `CONTEXT_COMPACTED` memory projection consumption。
- Conservative estimator 第一版不是 provider tokenizer；估算偏保守，后续 tokenizer adapter 需要作为独立能力接入，且不能改变本 slice 的 Host policy 真源边界。
- `HostLocalExecutionOptions.context_budget_policy` 目前只做 typed 接收与校验；后续 slice 接入 production path 时必须在 dispatch 前 fail-closed 校验 policy 存在，不能从 Engine overflow 或 metadata 回填预算。
