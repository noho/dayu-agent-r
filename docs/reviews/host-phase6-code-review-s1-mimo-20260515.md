# Host Phase 6 P6-S1 Code Review

- **gate**: Phase 6 P6-S1 code review
- **reviewed target**: workspace diff for P6-S1 (`feat/host-phase-6-toolruntime`)
- **approved plan**: `docs/host/phase6-toolruntime-truncation-fetch-more-plan.md`, slice P6-S1
- **implementation artifact**: `docs/reviews/host-phase6-implementation-s1-effective-toolbundle-20260515.md`
- **design source**: `docs/host/design.md` §18 / §19
- **control doc**: `docs/host/implementation-control.md` Phase 6
- **review date**: 2026-05-15
- **reviewer**: MIMO

## 审查结论

**PASS** — 无 blocking findings，0 non-blocking findings。

P6-S1 正确实现了 EffectiveToolBundle、ToolRuntimeHandle、ToolExecutionMode、RunInputBuilder tool-enabled/no-tool 验证与 scene message 工具状态。实现严格遵守了 P6-S1 的 scope 约束，未引入 accept barrier、真实工具执行、fetch_more callable、截断、重复治理、wait record、WAITING、resolve_wait、Remote wire protocol、Engine 治理、业务工具扫描或 `dayu.fins` 导入。

## 审查范围

### 变更文件

| 文件 | 状态 | 属于 P6-S1 allowed files |
|---|---|---|
| `dayu/host/tool_runtime.py` | new | 是 |
| `dayu/host/run_input.py` | modified | 是 |
| `tests/host/test_toolruntime_effective_bundle.py` | new | 是 |
| `tests/host/test_run_input_builder.py` | modified | 是 |
| `docs/reviews/host-phase6-implementation-s1-effective-toolbundle-20260515.md` | new | 是 |

### 未变更的 P6-S1 allowed files

| 文件 | 说明 |
|---|---|
| `dayu/host/tooling.py` | 未变更，无 P6-S1 需要的修改 |
| `dayu/host/command.py` | 未变更，P6-S1 不修改 command path |
| `dayu/host/api.py` | 未变更，`ToolExecutionMode` 未放入 `AttemptDispatchSnapshot` |
| `dayu/host/__init__.py` | 未变更，P6-S1 无新增公共 Host options |
| `tests/host/test_tooling_options.py` | 未变更 |
| `tests/host/test_package_exports.py` | 未变更 |

## Findings

无 findings。

## 审查详情

### 1. Correctness

#### 1.1 EffectiveToolBundle

- `EffectiveToolBundle` dataclass 字段完整，包含 plan §3.3 要求的全部字段：`business_bundle`、`definitions_by_name`、`tool_schemas`、`truncate_specs_by_name`、`source_refs`、`enabled_framework_tools`、`injected_framework_tool_names`、`business_bundle_digest`、`effective_schema_digest`、`policy_snapshot_digest`。
- `definitions_by_name` 使用 `MappingProxyType` 保证不可变。
- `truncate_specs_by_name` 使用 `MappingProxyType` 保证不可变。
- digest 使用 `dayu.host.durable.codec.sha256_digest_json`，实现确定性。

#### 1.2 EffectiveToolBundleBuilder

- `build()` 方法：校验 `source_refs` 非空、校验 reserved name 冲突、注入 framework tool、构造 `definitions_by_name`、投影 `tool_schemas`、收集 `truncate_specs`、计算 digest。
- `_validate_reserved_name_conflicts()`：正确校验业务工具名不占用 `FrameworkToolPolicyView.reserved_framework_tool_names` 中的预留名。
- `_inject_framework_definitions()`：按 `enabled_framework_tools` 注入，校验 hook 返回的工具名与请求名称一致。
- `_definitions_by_name()`：正确拒绝重复工具名。

#### 1.3 ToolRuntimeHandle

- `__post_init__` 正确校验 `tool_schemas` 必须是 `effective_bundle.tool_schemas` 的引用。
- 保证了 schema 与 executor 来自同一个 effective bundle 的设计约束。

#### 1.4 ToolRuntimeUnsupportedExecutor

- 正确实现 `ToolExecutor` Protocol（`execute` 方法签名匹配）。
- `effective_bundle` 字段为额外诊断字段，不违反 Protocol。
- 返回与输入 calls 严格双射的 `ToolFailedOutcome`，使用 `tool_runtime_not_connected` error code。

#### 1.5 RunInputBuilder

- `ToolExecutionMode` 枚举正确定义了三种模式：`TOOL_ENABLED`、`NO_TOOL_REPLAY`、`NO_TOOL_DISABLED`。
- `PolicySnapshot.__post_init__` 已移除 `allow_tool_calls` 拒绝，只保留 `policy_snapshot_ref` 非空校验。
- `_validate_tool_mode_snapshot()` 按模式分发验证：
  - `TOOL_ENABLED`：校验 `disable_tools=False`、`allow_tool_calls=True`、handle 非空、schema 来自同一 handle、executor 来自同一 handle。
  - `NO_TOOL_REPLAY` / `NO_TOOL_DISABLED`：校验 `disable_tools=True`、schema 为空、`allow_tool_calls=False`、handle 为 `None`。
- `DefaultSceneParameterProvider.build_scene_messages()` 正确接收 `tool_execution_mode` 参数，`TOOL_ENABLED` 输出 `tools=enabled`，其余输出 `tools=disabled`。
- `create_no_tool_run_input_builder()` 正确拒绝 `TOOL_ENABLED` 模式。
- `create_tool_enabled_run_input_builder()` 正确使用 `ToolRuntimeSchemaSnapshotProvider` 和 `ToolRuntimeExecutorProvider` 从同一 handle 投影 schema 和 executor。
- `ToolRuntimeSchemaSnapshotProvider` 和 `ToolRuntimeExecutorProvider` 都通过 `ToolRuntimeHandleProvider` 获取 handle，保证同源。

#### 1.6 Scene message 工具状态

- `TOOL_ENABLED` 模式：`tools=enabled`。
- `NO_TOOL_REPLAY` / `NO_TOOL_DISABLED` 模式：`tools=disabled`。

### 2. Scope 约束

确认以下内容**未被实现**：

- accept barrier（`HostToolFactAcceptPort` 只有 Protocol 定义，无实现）
- 真实工具执行（`ToolRuntimeUnsupportedExecutor` 返回 failure）
- fetch_more callable（只有 `FrameworkToolName` 引用，无注入实现）
- 截断（`TruncationPort` 只有 Protocol 定义）
- 重复治理（`DuplicateGovernancePort` 只有 Protocol 定义）
- wait record / WAITING / resolve_wait
- Remote wire protocol
- Engine 治理
- 业务工具扫描
- `dayu.fins` 导入

Protocol 定义（`ToolDispatcher`、`ToolRuntimePolicyPort`、`TruncationPort`、`DuplicateGovernancePort`、`HostToolFactAcceptPort`、`ToolTraceDiagnosticEmitter`）以及对应的 dataclass（`ToolPolicyDecision`、`DuplicateDecision`、`TruncationAppliedOutcome`、`ToolTraceDiagnosticRecord`、`ToolTraceDiagnosticRef`）属于 P6-S1 "ToolRuntime ports" 定义，为后续 slice 提供稳定 typed contract，不违反 scope。

### 3. Design Conformance

- **schema 与 executor 同源**：`ToolRuntimeHandle.__post_init__` 校验 `tool_schemas == effective_bundle.tool_schemas`；`_validate_tool_enabled_snapshot` 校验 `handle.tool_schemas == snapshot.tool_schemas` 和 `handle.tool_executor is tool_executor`。测试 `test_tool_enabled_request_uses_toolruntime_handle` 断言 `request.tool_schemas == tool_runtime_handle.tool_schemas` 和 `request.tool_executor is tool_runtime_handle.tool_executor`。
- **no-tool / replay 保持空 schema + NoToolExecutor + allow_tool_calls=False**：`NoopToolSchemaSnapshotProvider` 返回空 schema 和 `disable_tools=True`；`NoToolExecutorProvider` 返回 `NoToolExecutor`；验证逻辑要求 `allow_tool_calls=False`。测试 `test_no_tool_request_fields_are_disabled` 和 `test_replay_no_tool_request_keeps_tools_disabled` 覆盖。
- **ToolExecutionMode 显式传入**：`RunInputBuilder.__init__` 接收 `tool_execution_mode: ToolExecutionMode`，不通过 provider 反推。

### 4. Type Discipline

- 无 `Any`、`object`、无类型参数、无类型返回值。
- 所有新增类、模块、函数均有中文 docstring，包含参数、返回值、异常说明。
- `MappingProxyType` 用于不可变映射暴露。
- Protocol 类使用标准 `Protocol` 定义。

### 5. 测试验证

#### 5.1 测试结果

```text
tests/host/test_toolruntime_effective_bundle.py: 3 passed
tests/host/test_run_input_builder.py: 12 passed (含 3 个 parametrize)
tests/host/test_tooling_options.py: 8 passed
tests/host/test_package_exports.py: 5 passed
合计: 28 passed, 0 failed
```

```text
pyright: 0 errors, 0 warnings, 0 informations
```

```text
git diff --check: 无输出
```

#### 5.2 Plan 要求测试覆盖

| Plan 测试要求 | 覆盖测试 |
|---|---|
| 业务 ToolBundle 正常工具 schema 与 callable 同源 | `test_business_bundle_projects_schema_and_callable_from_same_bundle` |
| 业务 ToolBundle 定义 fetch_more 被拒绝 | `test_business_bundle_defining_fetch_more_is_rejected` |
| 禁用 framework tool 不注入 fetch_more | `test_disabled_framework_tools_do_not_inject_fetch_more` |
| PolicySnapshot(allow_tool_calls=True) 构造成功 | `test_policy_snapshot_allows_tool_policy_for_tool_enabled` |
| tool-enabled RunInputBuilder 暴露同一 handle 的 schema/executor | `test_tool_enabled_request_uses_toolruntime_handle` |
| tool-enabled scene 不含 tools=disabled | `test_tool_enabled_request_uses_toolruntime_handle`（断言 `"tools=disabled" not in`） |
| replay/no-tool 暴露空 schema + allow_tool_calls=False | `test_replay_no_tool_request_keeps_tools_disabled` + `test_no_tool_request_fields_are_disabled` |
| replay/no-tool scene 表达工具禁用 | `test_replay_no_tool_request_keeps_tools_disabled`（断言 `"tools=disabled" in`） |
| Pyright 无 Any/object | pyright 0 errors |

#### 5.3 测试质量

测试不是表面断言，而是验证了关键行为：

- 同源性：schema 和 executor 从同一个 `ToolRuntimeHandle` 投影，且 `is` 同一对象。
- 约束验证：tool-enabled 和 no-tool 模式通过 `_validate_tool_mode_snapshot` 正确分叉。
- scene message：模式感知的工具状态行。
- durable fact 来源：用户消息来自 durable EventLog，不受 transient 修改影响。
- 确定性：同一 EventLog + policy 多次 build 输出稳定。
- 状态约束：非 dispatchable 状态的 Run/Attempt/DispatchRecord 被正确拒绝。

## Validation Note

- `git diff --check` 通过。
- pyright 0 errors。
- 28 tests passed。
- 变更文件全部在 P6-S1 allowed files 范围内。
- 未变更的 P6-S1 allowed files 无需修改。

## 总结

| 项目 | 值 |
|---|---|
| Finding 总数 | 0 |
| Blocking 数 | 0 |
| 结论 | PASS |
| Artifact 路径 | `docs/reviews/host-phase6-code-review-s1-mimo-20260515.md` |
| 验证状态 | pyright 0 errors, 28 tests passed, git diff --check clean |
