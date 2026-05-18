# Phase 10 Slice 6 Production Composition Integration Implementation

## 修改摘要

- `HostCommandHandleOptions` 增加 Context Governance production composition 输入：必填 `context_window_size`、必填 `reserved_output_tokens`、可选 `context_budget_hard_threshold_tokens` 与 `context_budget_minimum_protection_tokens`，并在构造期校验这些字段可组成合法 `ContextBudgetPolicy`。
- `dayu.host.command.compose_host_local_execution_options(...)` 新增 production composition helper：从 command options 构造 typed `ContextBudgetPolicy`，覆盖 `HostLocalExecutionOptions.context_budget_policy`，并将 command artifact root 作为 compact artifact root 注入本地执行配置。
- 保持 memory projection policy 与 context budget policy 分离：composition helper 只改 context policy / compact artifact root，不改 memory projection policy。
- `test_public_contracts.py` 增加 context budget option 校验、composition helper wiring、以及 per-run request / metadata 不承载 budget 参数的断言；review fix 后所有 `HostCommandHandleOptions(...)` 构造点均显式传入 window / reserved。
- `test_dispatch_scheduler.py` 增加 multi-turn aggregate integration：多轮 accepted Run 经真实 scheduler gate dispatch，后续 Run 先观察 recent raw turn，随后小 budget 触发 proactive compact，当前 RunInputBuilder 暴露 compact artifact message，下一轮 Engine request 观察到 compact 后 pinned state、episode summary 与 recent raw turn 顺序。
- README 同步 Host composition 当前行为与测试分层说明。

## Composition Data Flow

`Service / composition root -> HostCommandHandleOptions.context_window_size / reserved_output_tokens -> compose_host_local_execution_options(...) -> HostLocalExecutionOptions.context_budget_policy -> HostDispatchScheduler proactive gate / EngineEventIngestor reactive recovery -> RunInputBuilder durable memory + compact providers -> Engine request`

预算参数只来自 composition typed options；不会从 Engine runner spec、per-run request metadata、caller payload 或 provider overflow event 读取。`context_window_size` 与 `reserved_output_tokens` 没有生产默认值，composition root 必须显式传入。`HostLocalExecutionOptions.context_budget_policy` 仍是 scheduler / tests 可直接显式注入的 typed policy 边界；command composition helper 负责 production command options 到 local execution options 的归一化。

## Integration Coverage And Limits

- S4/S5 scheduler integration 已继续覆盖 proactive pre-start compact 与 reactive overflow recovery；S6 增加 public composition wiring 的 contract-level 覆盖，确认 production options 能生成 scheduler 使用的 typed policy，且缺少显式 window / reserved 时不能成功构造 command options。
- Existing memory projection / RunInputBuilder tests 覆盖 accepted `CONTEXT_COMPACTED` 进入 memory projection，以及后续 RunInputBuilder 可看到 pinned state、episode summary、verified facts 和 raw turn budget 顺序。
- 已新增 scheduler-level multi-turn aggregate integration，覆盖 proactive compact -> `CONTEXT_COMPACTED` -> memory projection catch-up -> subsequent Engine request 的真实链路；完整业务工具 verified fact 端到端仍由既有 ToolRuntime / memory projection / RunInputBuilder 分层测试覆盖。
- Fake compactor 仍只在 tests / local dev 显式注入；production composition helper 不 import 或默认使用 fake compactor。

## Tests / Validation Results

- `source .venv/bin/activate && pytest tests/host/test_context_budget.py`：20 passed。
- `source .venv/bin/activate && pytest tests/host/test_compaction_contract.py tests/host/test_compact_artifact_store.py`：17 passed。
- `source .venv/bin/activate && pytest tests/host/test_context_compact_events.py`：15 passed。
- `source .venv/bin/activate && pytest tests/host/test_memory_projection.py tests/host/test_run_input_builder.py`：64 passed。
- `source .venv/bin/activate && pytest tests/host/test_public_contracts.py tests/host/test_phase5_local_execution_integration.py tests/host/test_dispatch_scheduler.py -q`：81 passed。
- `source .venv/bin/activate && pytest tests/host/test_context_budget.py tests/host/test_compaction_contract.py tests/host/test_compact_artifact_store.py tests/host/test_context_compact_events.py tests/host/test_memory_projection.py tests/host/test_run_input_builder.py tests/host/test_engine_ingest_mapping.py tests/host/test_run_attempt_transitions.py -q`：180 passed。
- `source .venv/bin/activate && pyright`：0 errors。
- `git diff --check`：通过。

## README Decisions

- 已更新 `dayu/host/README.md`：记录 `HostCommandHandleOptions` 必填 context window / reserved output fields、`compose_host_local_execution_options(...)` data flow、artifact root wiring、以及 budget policy / memory projection policy 分离。
- 已更新 `tests/README.md`：增加 `test_context_compact_events.py` 运行入口，并显式标注 `test_context_budget.py`、`test_compaction_contract.py`、`test_compact_artifact_store.py`、`test_context_compact_events.py` 对应覆盖类别；review fix 后补充 public budget composition 与 multi-turn proactive compact coverage。
- 未更新 `dayu/README.md`：本次未改变 UI / Service / Host / Engine 分层边界，只补 Host package 内 production composition wiring。

## Residual Risks / Owners

- Full multi-turn aggregate integration 已补入 scheduler harness；业务工具 verified fact 的完整 public fake-worker 链路仍未在该单测内串起，当前由 ToolRuntime accepted fact、memory projection verified fact、RunInputBuilder verified fact message 的分层测试覆盖。
- Production helper 不默认注入 compactor；未配置 compactor 且触发 compact 时仍按 S4/S5 fail closed。真实 production compactor adapter 归后续 explicit composition owner。
- Provider-specific tokenizer、长期 retrieval、public memory edit/reset/forget、Phase 11 startup recovery / positive orphan proof 均不在 Slice 6 范围。
