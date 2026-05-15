# Host Phase 6 P6-S5 Implementation: Duplicate Governance And Diagnostic Emitter

## 范围

本 slice 按 `docs/host/phase6-toolruntime-truncation-fetch-more-plan.md` 的 P6-S5 执行，目标是把 P6-S3 的 always-allow duplicate stub 替换为 ToolRuntime 实例内 run-local duplicate governance，并补齐最小 diagnostic emitter interface。

## 修改

- `dayu/host/tool_runtime.py`
  - 新增 `DuplicateGovernancePolicy`、`DuplicateGovernanceRequest`、`DuplicateAcceptedRecord` 与 `InMemoryRunLocalDuplicateGovernance`。
  - duplicate key 基于工具身份 digest、normalized arguments digest 与可选 semantic duplicate key，排除 `index_in_iteration`。
  - `ToolRuntimeExecutor` 在 dispatch 前执行 duplicate governance；`allow` 继续执行 callable，`reuse` 走 accept barrier 的 reuse fact，`hint` / `require_justification` / `hard_stop` 转为 governed error。
  - accepted ack 后才把 accepted refs 与 outcome 记入当前 ToolRuntime 实例内 duplicate index；新 ToolRuntime 实例不继承旧索引。
  - 新增 `ToolTraceDiagnosticEmitter` protocol、确定性 no-op / deterministic / in-memory 实现，duplicate governed、accept rejected 与 accept timeout 路径均产生 diagnostic refs。
- `tests/host/test_toolruntime_duplicate_governance.py`
  - 覆盖参数规范化、排除 `index_in_iteration`、`allow`、`reuse`、`hint` / `require_justification` / `hard_stop` matrix、ToolRuntime 实例生命周期边界。
- `tests/host/test_toolruntime_diagnostics.py`
  - 覆盖 no-op / in-memory emitter、duplicate governed candidate / ack refs、accept rejected / timeout diagnostic refs。
- `dayu/host/README.md`、`tests/README.md`
  - 同步 P6-S5 当前事实和测试命令。

## 验证

- `source .venv/bin/activate && pytest tests/host/test_toolruntime_duplicate_governance.py tests/host/test_toolruntime_diagnostics.py tests/host/test_toolruntime_accept_barrier.py -q`
  - 19 passed
- `source .venv/bin/activate && pytest tests/host/test_toolruntime_executor.py tests/host/test_toolruntime_truncation_fetch_more.py tests/host/test_toolruntime_effective_bundle.py tests/host/test_phase6_toolruntime_integration.py tests/host/test_toolruntime_accept_barrier.py tests/host/test_toolruntime_duplicate_governance.py tests/host/test_toolruntime_diagnostics.py -q`
  - 41 passed
- `source .venv/bin/activate && python -m pyright dayu/host tests/host`
  - 0 errors, 0 warnings, 0 informations
- `git diff --check`
  - clean

## Non-goals

- 不引入 durable duplicate ledger。
- 不引入 Memory retrieval 或跨 Run / 跨 Session 复用。
- 不写 audit / trace projection。
- 不修改 Engine 工具协议语义。
- 不接线真实 `HostDispatchScheduler` tool-enabled composition wiring，该项仍归 P6-S6 integration。

## 残余风险

- 默认 duplicate policy 仍为 `allow`，因此未显式配置策略时不会改变既有执行行为；生产策略 provider resolution 仍未实现。
- `ToolTraceDiagnosticEmitter` 当前只提供 typed refs，不落 durable trace projection；durable trace 归 Phase 13。
- `semantic_duplicate_key_argument_name` 是 Host 内部 policy 字段，默认关闭；后续 policy provider 若启用它，必须明确其与 normalized arguments digest 的关系，不能把它升级成跨 Run 召回能力。
