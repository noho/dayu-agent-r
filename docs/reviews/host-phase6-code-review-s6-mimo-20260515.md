# Host Phase 6 P6-S6 Code Review — AgentMiMo

- **审查日期**: 2026-05-15
- **审查范围**: 当前未提交改动（7 files, +352 / -25）
- **设计真源**: `docs/host/design.md` §18–§19
- **计划真源**: `docs/host/phase6-toolruntime-truncation-fetch-more-plan.md` P6-S6
- **实现说明**: `docs/reviews/host-phase6-implementation-s6-integration-gate-20260515.md`

## Verdict

**Accept** — 改动符合 P6 退出目标要求，无 blocking finding。

## Findings

### F1. Scope 扩展由 P6 退出目标支撑，不是 scope creep

P6 退出目标要求"真实本地 dispatch 路径使用 Host-governed ToolExecutor"。P6-S1 至 P6-S5 已完成 ToolRuntime 组件闭环，但 `HostDispatchScheduler._start_worker` 仍固定调用 `create_no_tool_run_input_builder`。若不修改 `dispatch.py`，Phase 6 只能算组件完成，不满足退出条件。

计划 P6-S6 allowed files 已同步新增 `dayu/host/api.py` 与 `dayu/host/dispatch.py`，objective 从 "Finish integration coverage, README sync and phase validation" 扩展为 "Finish integration coverage, real scheduler ToolRuntime wiring, README sync and phase validation"。

**结论**: scope 扩展有据可依，非 scope creep。

### F2. ToolRuntime handle 构造与同源 schema/executor 传递 — 正确

`dispatch.py:682-733` `_run_input_builder_for_dispatch` 实现：

1. 检查 `tooling_options is not None` 且 `policy_snapshot.agent_policy.allow_tool_calls is True`。
2. 通过 `DefaultToolRuntimeFactory(EffectiveToolBundleBuilder()).create_tool_runtime(ToolRuntimeBuildRequest(...))` 构造 ToolRuntime handle。
3. `ToolRuntimeBuildRequest` 使用 dispatch snapshot 的 `session_id`、`run_id`、`attempt_id`、`execution_id` 作为 `execution_scope`。
4. accept port 使用同一个 `self._transaction_runner` 与 `self._event_log_store`（即 Host durable accept barrier）。
5. 调用 `create_tool_enabled_run_input_builder(tool_runtime_handle=tool_runtime)` 将同源 `tool_schemas` 与 `tool_executor` 交给 worker。

**结论**: 满足设计 §18.1 attempt-local effective tool view 同源约束。

### F3. No-tool fallback 保持完整

`dispatch.py:692-700`：当 `tooling_options is None` 或 `not policy_snapshot.agent_policy.allow_tool_calls` 时，返回 `create_no_tool_run_input_builder`。

现有测试 `test_pending_waiting_dispatching_worker_accept_marks_running` 使用默认 `_open_scheduler`（无 `tooling_options`，`allow_tool_calls=False`），验证 no-tool 路径未被破坏。

**结论**: no-tool 行为完整保持。

### F4. ToolBundle 只在 construction/composition root 输入

`dayu/host/api.py:400`：`HostLocalExecutionOptions.tooling_options: _HostToolingOptions | None = None`。`_HostToolingOptions` 通过私有别名引用，不从 `dayu.host.api` 导出。

`tooling_options` 未进入 `StartRunRequest`、`SubmitFollowup`、per-run request 或 metadata。

**结论**: 满足 ToolBundle construction-time-only 约束。

### F5. Accept port 使用 Host durable accept barrier

`dispatch.py:723-726`：
```python
accept_port=DefaultHostToolFactAcceptPort(
    transaction_runner=self._transaction_runner,
    event_log_store=self._event_log_store,
)
```

使用与 scheduler 其余 durable 操作相同的 `transaction_runner` 与 `event_log_store`。`DefaultHostToolFactAcceptPort` 在同一事务中写入 `TOOL_CALL_REQUESTED`、`TOOL_CALL_GOVERNED`（如适用）与 `TOOL_RESULT_ACCEPTED`，并通过 idempotency primitive 保证幂等。

新测试 `test_scheduler_uses_toolruntime_when_tooling_is_configured` 验证工具执行后 EventLog 包含 `TOOL_CALL_REQUESTED` 与 `TOOL_RESULT_ACCEPTED`，且 `run_id` 正确。

**结论**: 工具结果先 accepted 才返回 Engine，满足设计 §18.2。

### F6. 未引入禁止特性

审查确认本次改动未引入：
- durable tool snapshot table
- Remote / WAITING / recovery
- P13 trace projection
- business tool discovery
- `dayu.fins` import
- Engine contract 修改
- 新 durable table

`dispatch.py` 无 `from dayu.host.(fins|service|ui|config)` 导入。`git diff --check` clean。

**结论**: 满足 non-goals 约束。

### F7. README / dayu README / tests README — 只记录当前事实

| 文件 | 变更内容 | 是否准确 |
|---|---|---|
| `dayu/host/README.md` | P6-S1–S5 → P6-S1–S6；新增 scheduler tool-enabled wiring 描述；移除 "真实 HostDispatchScheduler tool-enabled composition wiring" 从 "未实现" 列表 | 准确 |
| `dayu/README.md` | `TruncationManager` / `truncation cursor` / `scope_token` 术语修正为 Phase 6 run-scoped、short-lived、ToolRuntime-local 事实 | 准确 |
| `tests/README.md` | 新增 "真实 scheduler tool-enabled ToolRuntime wiring" 到测试覆盖描述 | 准确 |

三份 README 均只描述当前已实现行为，未声称 P7/P11/P13/P14 特性已实现。

**结论**: 文档同步准确。

### F8. 新测试验证真实 scheduler wiring

`test_scheduler_uses_toolruntime_when_tooling_is_configured`（`test_dispatch_scheduler.py:523-575`）：

1. 使用 `_FakeWorkerFactory` + `_CountingTool` 构造 tool-enabled scheduler。
2. 验证 `request.disable_tools is False` 且 `request.agent_policy.allow_tool_calls is True`。
3. 验证 `request.tool_schemas` 包含 `fake_dispatch_tool`。
4. 通过 `request.tool_executor.execute(...)` 执行工具，验证 `tool.call_count == 1`。
5. 验证 `tool_outcome.records[0].outcome` 为 `ToolCompletedOutcome`。
6. 验证 EventLog 包含 `TOOL_CALL_REQUESTED` 与 `TOOL_RESULT_ACCEPTED`，且 `run_id` 正确。

测试覆盖了完整 tool-enabled dispatch 路径：scheduler → ToolRuntime 构造 → RunInputBuilder → worker 接收 → 工具执行 → accept barrier → EventLog。

**结论**: 测试充分覆盖 P6-S6 核心行为。

### F9. `_policy_snapshot_digest` 作为诊断 digest — 合理

`dispatch.py:1147-1166`：仅包含 `policy_snapshot_ref`、`allow_tool_calls`、`max_iterations`、`continuation_max_attempts`、`tool_execution_timeout_seconds`。

实现说明明确标注为 "本地 policy snapshot 的诊断 digest，不是 durable attempt tool snapshot"。设计 §3.3 允许 `policy_snapshot_digest` 用于诊断、trace 和测试。

**结论**: 用法符合设计意图。

### F10. 每次 dispatch 构造新 ToolRuntime 实例

`_run_input_builder_for_dispatch` 每次 dispatch 创建新的 `DefaultToolRuntimeFactory` → `EffectiveToolBundleBuilder` → `ToolRuntimeHandle`。

这意味着每个 Attempt 有独立的 duplicate governance index、truncation manager 和 accept port 实例。符合设计 §3.3 "attempt-local runtime object" 定位和 §3.7 "run-local only" duplicate governance 约束。

**结论**: 生命周期正确。

## Validation

| 验证项 | 结果 |
|---|---|
| `pytest tests/host/test_dispatch_scheduler.py -q` | 15 passed, 0.35s |
| `pytest tests/host -q` | 348 passed, 4.46s |
| `pyright dayu/host/api.py dayu/host/dispatch.py` | 0 errors, 0 warnings, 0 informations |
| `pyright dayu/ tests/ utils/` | 0 errors, 0 warnings, 0 informations |
| `git diff --check` | clean |
| import boundary 检查 `dispatch.py` | 无 fins/service/ui/config 导入 |
| README 只记录当前事实 | 三份 README 均准确 |

## Residual Risks

1. **多 profile / per-scene tool profile**: `tooling_options` 当前是 construction-time 单 bundle 输入。多 profile 或 per-scene tool profile 仍归后续 ToolsDiscovery / policy provider owner（P12）。

2. **no-tool fallback 显式测试**: 新测试只覆盖 tool-enabled 路径。no-tool fallback 依赖现有 `test_pending_waiting_dispatching_worker_accept_marks_running`（使用默认无 tooling 配置）。如果后续 no-tool 路径逻辑变更，建议新增显式断言 `request.disable_tools is True` 的测试。

3. **Policy snapshot digest 字段选择**: 当前 digest 包含 5 个字段。如果 `AgentPolicy` 新增影响工具行为的字段，digest 需同步更新。当前无风险，但属于维护注意项。

4. **Phase 6 aggregate exit gate**: 本次改动完成 P6 退出目标的"真实本地 dispatch 路径使用 Host-governed ToolExecutor"。Phase 6 完整退出仍需确认：Engine 只消费 accepted 工具事实、`fetch_more` 仍是普通工具路径、无 WAITING / recovery / remote / durable cursor 越界。这些由 P6-S1 至 P6-S5 的已有 review 覆盖。
