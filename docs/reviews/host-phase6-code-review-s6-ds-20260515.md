# Host Phase 6 P6-S6 Adversarial Code Review (AgentDS)

- **review target**: P6-S6 uncommitted changes (f836ab9..HEAD on `feat/host-phase-6-toolruntime`)
- **review date**: 2026-05-15
- **review type**: independent adversarial deep review
- **result**: APPROVED with 2 advisories, 0 blockers

## Verdict

P6-S6 implementation correctly closes the real `HostDispatchScheduler` no-tool exit blocker. ToolRuntime construction params are valid, tool-enabled request uses the same `ToolRuntimeHandle` for schema projection and executor dispatch, no-tool fallback is preserved, and tests exercise the real scheduler → ToolRuntime → Host accept barrier → canonical tool facts path. No `Any`/`object`, no reverse dependency, no God object, no README future-tense misrepresentation detected. All 348 tests pass; pyright reports 0 errors across `dayu/`, `tests/`, `utils/`.

## Findings

### F1. `HostToolingOptions` 私有别名接入 `HostLocalExecutionOptions` — 边界受控

`dayu/host/api.py:28` 以私有别名 `_HostToolingOptions` 导入 `dayu.host.tooling.HostToolingOptions`，仅在 `HostLocalExecutionOptions.tooling_options` 字段用作类型标注（line 400）与 `__post_init__` 校验（line 470-475）。

**审查结论**：边界未破坏。
- `api.py` 的 `__all__` 不含 `HostToolingOptions`，不重新导出 tooling 类型。
- `dayu/host/__init__.py` 对 `HostToolingOptions` 的导出来自 `dayu.host.tooling`（line 74），是 P6-S1 即已存在的直接导出，不由本次变更引入。
- 私有别名 `_HostToolingOptions` 在 `api.py` 模块作用域内不可被外部 import，符合 "不导出 tooling 类型" 的 gate 要求。
- 运行时验证：`"HostToolingOptions" in dayu.host.api.__all__` 返回 `False`。

**Advisory**：`api.py` 模块 docstring 宣称 "不实现 command path、durable store、EventLog、dispatch、policy provider 或 Engine 调用路径"，但未提及对 `tooling.py` 的构造期依赖。建议在 docstring 中补充 "构造期通过私有别名引用 `_HostToolingOptions` 以支持 composition root 装配" 或等效说明，防止未来维护者误判模块依赖图。此项为非阻塞建议。

### F2. Scheduler 构造 ToolRuntime 参数完整性 — 正确

`HostDispatchScheduler._run_input_builder_for_dispatch`（dispatch.py:682-733）的构造参数逐项验证：

| 参数 | 来源 | 验证 |
|------|------|------|
| `execution_scope.session_id` | `snapshot.session_id` | 来自 durable `AttemptDispatchSnapshot` |
| `execution_scope.run_id` | `snapshot.run_id` | 同上 |
| `execution_scope.attempt_id` | `snapshot.attempt_id` | 同上 |
| `execution_scope.execution_id` | `snapshot.execution_id` | 同上 |
| `execution_scope.allow_tool_calls` | `policy_snapshot.agent_policy.allow_tool_calls` | 与 policy 一致 |
| `policy_snapshot_digest` | `_policy_snapshot_digest(policy_snapshot)` | 诊断 digest，非 durable snapshot |
| `accept_port` | `DefaultHostToolFactAcceptPort(transaction_runner, event_log_store)` | 同源 transaction runner 与 EventLog store |

所有 identity 字段来自同一个 dispatch snapshot，accept_port 使用与 scheduler 相同的 `transaction_runner` 和 `event_log_store`（`HostDispatchScheduler.open()` 在 line 378 创建并传入）。正确。

### F3. 同源 ToolRuntimeHandle 投影 schema 与 executor — 正确且有多重防护

`create_tool_enabled_run_input_builder`（run_input.py:883-912）使用同一个 `StaticToolRuntimeHandleProvider` 实例分别构造 `ToolRuntimeSchemaSnapshotProvider` 与 `ToolRuntimeExecutorProvider`：

```python
handle_provider = StaticToolRuntimeHandleProvider(tool_runtime_handle)
# ...
tool_schema_snapshot_provider=ToolRuntimeSchemaSnapshotProvider(handle_provider),
tool_executor_provider=ToolRuntimeExecutorProvider(handle_provider),
```

`ToolRuntimeSchemaSnapshotProvider.load_tool_schema_snapshot` 返回 `handle.tool_schemas`（line 646），`ToolRuntimeExecutorProvider.load_tool_executor` 返回 `handle.tool_executor`（line 675）。

`_validate_tool_enabled_snapshot`（run_input.py:1182-1209）额外做 identity 检查：
```python
if tool_snapshot.tool_runtime_handle.tool_schemas != tool_snapshot.tool_schemas:
    raise HostDurableError(...)
if tool_snapshot.tool_runtime_handle.tool_executor is not tool_executor:
    raise HostDurableError(...)
```

`ToolRuntimeHandle.__post_init__`（tool_runtime.py:2361-2371）也校验 `tool_schemas == effective_bundle.tool_schemas`。三层防护，无绕过可能。

### F4. No-tool fallback 兼容性 — 保持

`_run_input_builder_for_dispatch` 的 guard（dispatch.py:692-700）：
```python
if tooling_options is None or not policy_snapshot.agent_policy.allow_tool_calls:
    return create_no_tool_run_input_builder(...)
```

- `tooling_options` 默认为 `None`（`HostLocalExecutionOptions` field default），所有现有 no-tool 路径不受影响。
- `agent_policy.allow_tool_calls=False` 时即使提供了 `tooling_options` 也走 no-tool builder。
- 既有测试 `test_pending_waiting_dispatching_worker_accept_marks_running` 使用默认 no-tool policy，断言 `disable_tools is True`，通过（15/15 passed）。
- 测试 `test_scheduler_uses_toolruntime_when_tooling_is_configured` 使用 `allow_tool_calls=True` + `tooling_options`，断言 `disable_tools is False`，通过。

### F5. 测试通过真实 scheduler path 执行 tool_executor 并写 canonical tool facts — 确认

`test_scheduler_uses_toolruntime_when_tooling_is_configured`（test_dispatch_scheduler.py:523-575）的执行路径：

1. `HostDispatchScheduler.open()` → 真实 durable store + lane controller
2. `_seed_current_run()` → 真实 Run/Attempt/dispatch_record 写入 SQLite
3. `scheduler.wake_dispatch()` + `scheduler.drain_once()` → 完整 dispatch 闭环
4. `factory.accepted_requests[0]` → worker 收到的 `AgentRunRequest`
5. `request.tool_executor.execute(...)` → 真实 `ToolRuntimeExecutor.execute()`，走 dispatcher → policy → truncation → accept barrier
6. `assert tool.call_count == 1` → 业务 callable 被真实调用
7. `_read_event_by_type(..., "TOOL_CALL_REQUESTED")` → EventLog 中有 canonical 工具调用请求事实
8. `_read_event_by_type(..., "TOOL_RESULT_ACCEPTED")` → EventLog 中有 canonical 工具结果接受事实

这不是组件测试——`tool_executor` 来自 scheduler 构造的 `ToolRuntime`，经过 `DefaultToolRuntimeFactory` → `ToolRuntimeExecutor` → `DefaultToolDispatcher` → `DefaultToolRuntimePolicyPort` → `InMemoryRunLocalDuplicateGovernance` → `TruncationManager` → `DefaultHostToolFactAcceptPort` 全链路。两个 canonical fact 事件通过 accept barrier 的 transaction runner 写入同一个 SQLite durable store。

**Advisory**：测试创建 `TruncationManager`（因为 `enable_truncation_manager=True` 是默认值），但 `FrameworkToolPolicyView.enabled_framework_tools` 为空，因此 `fetch_more` 不会注入。测试未覆盖 `enable_truncation_manager=False` 路径。非阻塞——truncation manager 是 Phase 6 S4 已验证的能力，此处仅确认 wiring 正确。

### F6. 过度耦合 / God object / 反向依赖 / Any/object / 无类型签名 / docstring — 未发现

- **God object**: `HostDispatchScheduler` 行数增加但职责未扩散——`_run_input_builder_for_dispatch` 将 ToolRuntime 构造封装为单个私有方法，不改动 scheduler 的核心调度状态机。
- **反向依赖**: `dispatch.py` → `tool_runtime.py` 是 `Host` 内部依赖，不违反 `UI → Service → Host → Engine` 分层。`tool_runtime.py` 不 import `dispatch.py`。
- **`Any`/`object`**: 新增代码无 `Any`/`object`。`_policy_snapshot_digest` 返回 `str`，所有 dataclass 字段有完整类型标注。
- **Docstring**: 所有新增函数/方法有中文 docstring（`_run_input_builder_for_dispatch` line 682-689，`_policy_snapshot_digest` line 1147-1152）。
- **`__init__.py` 导出**: `dayu/host/__init__.py` 不新增导出，不改动 P6-S1 已有的 `HostToolingOptions`/`ToolBundleSourceRef` 等 tooling 直接导出。
- **README 未来化**: `dayu/host/README.md` 明确写入 "当前本地 `HostDispatchScheduler` 已接入 tool-enabled composition wiring"，从 "尚未实现" 更新为 "已实现"，未出现 "将来会支持" 的未来化描述。`dayu/README.md` truncation cursor / scope_token 术语从 "必须可由 durable descriptor 恢复" 修正为 "Phase 6 第一版是 Run-scoped、short-lived、ToolRuntime-local capability"，准确反映当前事实。

## Validation

| 验证项 | 命令 | 结果 |
|--------|------|------|
| Host 测试全量 | `pytest tests/host -q` | 348 passed |
| Dispatch scheduler 测试 | `pytest tests/host/test_dispatch_scheduler.py -q` | 15 passed（含 1 个新增） |
| Pyright 全量 | `pyright dayu/ tests/ utils/` | 0 errors, 0 warnings, 0 informations |
| Diff whitespace | `git diff --check` | clean |
| api.py 不导出 tooling 类型 | `"HostToolingOptions" in api.__all__` | False |
| No-tool 回归 | `test_pending_waiting_dispatching_worker_accept_marks_running` | passed, `disable_tools is True` |
| Tool-enabled 新路径 | `test_scheduler_uses_toolruntime_when_tooling_is_configured` | passed, tool executed, TOOL_CALL_REQUESTED + TOOL_RESULT_ACCEPTED written |

## Residual Risks

1. **Duplicate index 是 per-attempt 而非 per-run**：`_run_input_builder_for_dispatch` 每次 dispatch 创建新的 `DefaultToolRuntimeFactory`，导致 `InMemoryRunLocalDuplicateGovernance` 索引仅存活于单个 Attempt 的 ToolRuntime 实例。若同一 Run 有多个 Attempt（如 steer 路径），跨 Attempt 的重复工具调用不会命中 duplicate index。Phase 6 设计文档明确要求 "同 Run、run-local deterministic duplicate key"；当前实现为 per-attempt，需在后续 slice 或 aggregate review 中判定是否满足 P6 退出条件。Host README 已如实记录 "ToolRuntime 实例内 duplicate index 生命周期"。

2. **`enable_truncation_manager=True` 为默认值**：`HostLocalExecutionOptions.enable_truncation_manager` 默认为 `True`，意味着提供 `tooling_options` 时总是创建 `TruncationManager`（即使业务工具未声明 `ToolTruncateSpec`）。当前行为无害——未声明 truncate_spec 的工具不会被截断；`fetch_more` 只在 `FrameworkToolPolicyView.enabled_framework_tools` 显式包含 `FETCH_MORE` 时注入。但如果未来 `TruncationManager` 初始化成本增大，此默认值需要重新评估。

3. **`_policy_snapshot_digest` 覆盖字段有限**：当前 digest 只覆盖 `policy_snapshot_ref`、`allow_tool_calls`、`max_iterations`、`continuation_max_attempts`、`tool_execution_timeout_seconds` 五个字段。若 `AgentPolicy` 新增字段而未更新此函数，digest 将不反映完整 policy 状态。但 plan 明确声明 policy_snapshot_digest 是 "诊断 digest，不表达 durable attempt tool snapshot"，因此此风险归入后续 policy provider resolution owner。

4. **`api.py` 对 `tooling.py` 的构造期依赖**：见 Finding F1 advisory。

## Non-goals 确认

P6-S6 未引入以下禁止项：
- Durable tool snapshot table: 无
- Remote transport: 无
- P7 wait record / `resolve_wait`: 无
- P13 durable tool trace projection: 无
- Business tool discovery: Host 只接收外部 composition root 传入的 `ToolBundle`
- `WAITING` / recovery / durable cursor 越界: 无
- `dayu.fins` / `dayu.service` / `dayu.ui` import: 无
- `Any` / `object` / 无类型签名: 无
- 兼容性 re-export / wrapper / facade: 无
