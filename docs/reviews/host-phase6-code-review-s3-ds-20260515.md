# Host Phase 6 P6-S3 Code Review

- **review mode**: Current Changes — P6-S3 uncommitted diff
- **branch**: `feat/host-phase-6-toolruntime`
- **base**: N/A (reviewing unstaged workspace diff only)
- **output file**: `docs/reviews/host-phase6-code-review-s3-ds-20260515.md`
- **review date**: 2026-05-15

## Scope

- **Included scope**: Unstaged diff in `dayu/host/tool_runtime.py`, `dayu/host/README.md`, `tests/README.md`, plus new untracked `tests/host/test_toolruntime_executor.py`, `tests/host/test_phase6_toolruntime_integration.py`
- **Excluded scope**: Staged changes, committed changes (P6-S1/P6-S2), `dayu/host/dispatch.py` (not modified), `dayu/host/local_proxy.py` (not modified)
- **Parallel review coverage**: 无 — 单 reviewer 全链路走读
- **Design sources of truth**: `docs/host/design.md`; `docs/host/implementation-control.md`; `docs/host/phase6-toolruntime-truncation-fetch-more-plan.md`

## Findings

### F1-未修复-中-P6-S3 dispatch/local_proxy wiring 未实施，HostDispatchScheduler 仍 no-tool only

- **入口/函数**: `HostDispatchScheduler._start_worker` → `create_no_tool_run_input_builder`
- **文件(行号)**: `dayu/host/dispatch.py:617`
- **输入场景**: 任意 dispatch attempt，无论是否应启用工具
- **实际分支**: `_start_worker` 无条件构造 `create_no_tool_run_input_builder(...)`，其中 `tool_executor_provider=NoToolExecutorProvider()`、`tool_schema_snapshot_provider=NoopToolSchemaSnapshotProvider()`、`tool_execution_mode=ToolExecutionMode.NO_TOOL_DISABLED`
- **预期行为**: P6-S3 plan exact changes（plan 文档 §6 P6-S3）要求 "Wire local dispatch / RunInputBuilder to use ToolRuntime executor for tool-enabled Attempts"，对应 allowed files 包括 `dayu/host/dispatch.py` 与 `dayu/host/local_proxy.py`
- **实际行为**: 两个文件均未修改；`dispatch.py` 中没有任何 `ToolRuntime`、`ToolRuntimeFactory`、`create_tool_enabled_run_input_builder` 引用；`local_proxy.py` 中也没有 ToolRuntime 导入或 executor 透传
- **直接证据**:
  - `dispatch.py:617`: `request = create_no_tool_run_input_builder(...)` — 唯一 RunInputBuilder 构造路径
  - `git diff HEAD -- dayu/host/dispatch.py dayu/host/local_proxy.py` — 空输出
  - `Grep "ToolRuntime|tool_executor|ToolExecutor" dayu/host/dispatch.py` — 无匹配
  - `AttemptDispatchSnapshot` (api.py:240-266) 明确声明 "工具 schema 与 ToolExecutor 必须由 RunInputBuilder 的 typed providers 在 build 时注入，不能重复塞入本快照"
- **影响**: 当前 `HostDispatchScheduler` 对任何 attempt 都只能产出 no-tool `AgentRunRequest`；即使业务 `ToolBundle` 已注入 Host construction、`ToolRuntimeExecutor` 已实现并通过单元/集成测试，生产 dispatch 路径仍然无法产出 tool-enabled request
- **分析**: 此为 deferred acceptable，非 blocking。理由如下：
  1. P6-S3 的核心交付物 `ToolRuntimeExecutor` 完整实现并通过全部 direct executor + integration 测试
  2. `create_tool_enabled_run_input_builder()` 已在 P6-S1 完成，集成测试（`test_engine_continues_only_after_toolruntime_host_accept`）直接使用它绕过 scheduler 验证了 Engine → ToolRuntime → Host accept barrier → Engine continuation 完整闭环
  3. dispatch wiring 本质是 composition root 变更：需要将 `ToolRuntimeFactory`（依赖 `EffectiveToolBundleBuilder` + 业务 `ToolBundle`）线程进入 `HostDispatchScheduler` 构造，并在 `_start_worker` 中根据 attempt 特征选择 tool-enabled / no-tool builder。这涉及 `HostCommandHandle` 对 scheduler 的装配变更，属于独立集成步骤
  4. `AttemptDispatchSnapshot` 不携带 `ToolExecutionMode`（api.py 明确不承载），意味着 wiring 仍需明确 mode selection 落在 scheduler construction 还是 builder construction 的哪个闭包——这是设计问题不是实现遗漏
  5. plan wording "Wire local dispatch / RunInputBuilder to use ToolRuntime executor" 中的 "wire" 未指定具体 composition 策略；当前 `create_tool_enabled_run_input_builder` 已可接收 `ToolRuntimeHandle` 并产出正确 `AgentRunRequest`，调度端缺少的是闭包装配而非 executor 逻辑
  6. P6-S5（duplicate governance）/ P6-S6（integration）仍可接受此 gap，只要在 P6 收口前补齐 dispatch construction wiring
- **建议改法和验证点**: 在 `HostDispatchScheduler.__init__` 注入 `ToolRuntimeFactory`（或直接注入 `create_tool_enabled_run_input_builder` 所需的闭包）；在 `_start_worker` 中根据 attempt 的 tool policy 选择构造路径；验证 `HostDispatchScheduler` 的集成测试能产出携带 tool schemas 与 `ToolRuntimeExecutor` 的 `AgentRunRequest`；确认 Phase 5 no-tool 集成测试继续通过
- **修复风险（中）**: 涉及调度器构造接口变更，需要同步更新 `HostCommandHandle` 装配与现有 no-tool 测试对调度器构造的断言
- **严重程度（中）**: 不影响 P6-S3 executor 的正确性验证，但若不在 P6 收口前补齐，真实 Host 路径将永远 no-tool

### F2-未修复-低-`_accept_with_retry` 中 `accept_tool_fact` 同步阻塞事件循环

- **入口/函数**: `ToolRuntimeExecutor._accept_with_retry`
- **文件(行号)**: `dayu/host/tool_runtime.py:1367`
- **输入场景**: 任何通过 accept barrier 的工具调用
- **实际分支**: `result = self._accept_port.accept_tool_fact(candidate)` — 同步调用，无 `await`
- **预期行为**: 在当前 Host 架构中 durable 操作均为同步，此行为与 `DefaultHostToolFactAcceptPort` 一致
- **实际行为**: SQLite 事务在 event loop 线程中同步执行；若 `busy_timeout` 较长且数据库争用，event loop 会被阻塞
- **直接证据**: `tool_runtime.py:1367` 对 `accept_tool_fact` 的调用无 `await`；`DefaultHostToolFactAcceptPort.accept_tool_fact` (line 904) 调用同步 `self._transaction_runner.run_write(...)`
- **影响**: 当前与既有 Host 架构一致（所有 durable 操作均同步），非新引入问题。但若未来引入 async accept port 或更长的 busy timeout，可能成为性能退化点
- **建议改法和验证点**: 当前可接受；若后续 `HostToolFactAcceptPort` 增加 async 实现，`_accept_with_retry` 需要同步调整为 `await`
- **修复风险（低）**: 当前无行为影响
- **严重程度（低）**: 与既有架构一致，非新引入问题

## Open Questions

1. **dispatch wiring 后续 slice 归属**：P6-S3 plan 写 "Wire local dispatch / RunInputBuilder"，但未实施。此 gap 应在哪个 slice 关闭？若放入 P6-S6（integration），需确保 scheduler construction 变更有足够测试覆盖。若放入独立 follow-up，需在 control doc 中记录。

2. **`_accept_with_retry` 是否需要在 `ToolFactRejectedAck` 后也 emit diagnostic**：当前 rejected ack 直接返回，不 emit diagnostic。plan 中 diagnostic 主要用于 timeout/rejected 路径。当前 `_accept_failure_outcome` 在 rejected 时使用 `result.message` 作为错误消息，不额外 emit，行为一致。

## Residual Risk

1. **无 dispatcher 异常非 TimeoutError 的测试覆盖**：当前 test 中 fake accept port 从不抛异常。若真实 `DefaultHostToolFactAcceptPort` 抛出未预期的 `HostDurableError`（非 `HostIdempotencyConflictError`/`HostPayloadReferenceError`），异常将穿透 `_accept_with_retry` 到达 Engine。这可能是正确的（不应静默吸收未知持久化错误），但行为未通过测试显式验证。

2. **PassThroughDuplicateGovernance 的 duplicate_key 未被 accept 路径的 reuse 矩阵验证**：P6-S3 只做 always-allow stub，产生的 `duplicate_key` 在 accept candidate 中记录但未产生 reuse 行为。P6-S5 需要验证此 key 在完整 duplicate matrix 中正确工作。

3. **集成测试不覆盖 rejected/timeout 路径**：`test_phase6_toolruntime_integration.py` 只覆盖正常 accepted 路径（Engine → ToolRuntime → Host accept → Engine continuation）。rejected ack / timeout 路径只在 unit test 中覆盖，未在真实 Engine loop 中验证 Engine 对 governed error 的响应。

4. **`tool_runtime.py` 模块体积**：当前 `tool_runtime.py` 约 2850 行，承载了 effective bundle、accept barrier、executor、policy、diagnostic 等多个 concern。后续 slice（P6-S4 truncation、P6-S5 duplicate matrix）继续追加可能造成单文件过大。非阻塞但建议在 P6-S6 考虑按 concern 拆分。

## Verification Results

```
source .venv/bin/activate && pytest tests/host/test_toolruntime_executor.py tests/host/test_phase6_toolruntime_integration.py tests/host/test_phase5_local_execution_integration.py -q
→ 17 passed in 0.34s

source .venv/bin/activate && python -m pyright dayu/host tests/host
→ 0 errors, 0 warnings, 0 informations

git diff --check
→ (clean, no whitespace errors)
```

## Verdict

**Conditional ship**：P6-S3 的核心交付物 `ToolRuntimeExecutor` 实现正确、类型纪律干净、测试覆盖充分（accepted ack、rejected ack、timeout retry、side-effect guard、awaiting guard、no-tool defense、mixed batch、Engine integration）。唯一重要 gap 是 dispatch/local_proxy wiring 未实施（F1），但因 integration test 已通过绕过 scheduler 的直接装配证明完整 Engine-ToolRuntime-Host accept 闭环，且 wiring 属于 composition root 变更而非 executor 逻辑缺失，裁决为 deferred acceptable — 要求在 P6 收口前补齐。

未发现其他 blocking finding。无 raw result 泄漏、无 `WAITING` 污染、无越界实现 `fetch_more`/Remote/durable cursor。README 同步与测试覆盖符合 P6-S3 plan 要求。
