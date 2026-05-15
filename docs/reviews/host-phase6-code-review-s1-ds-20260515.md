# Host Phase 6 P6-S1 Code Review

- **review gate**: P6-S1 code review
- **target**: current workspace diff for P6-S1 (branch `feat/host-phase-6-toolruntime`)
- **approved plan**: `docs/host/phase6-toolruntime-truncation-fetch-more-plan.md`, slice P6-S1
- **implementation artifact**: `docs/reviews/host-phase6-implementation-s1-effective-toolbundle-20260515.md`
- **design source**: `docs/host/design.md` §18 / §19
- **control doc**: `docs/host/implementation-control.md` Phase 6
- **review lens**: correctness, scope, design conformance, type discipline, test quality
- **review date**: 2026-05-15

## 1. Scope Compliance

### DS-S1-PASS-01-无越界实现

审计确认以下能力均未在 P6-S1 中实现：

- Host accept barrier / `HostToolFactAcceptPort` 真源实现
- 真实工具 callable 执行（`ToolDispatcher` 仅为 Protocol，无实现）
- `fetch_more` callable 实现
- 截断（`TruncationPort` 仅为 Protocol，无实现）
- 重复治理（`DuplicateGovernancePort` 仅为 Protocol，无实现）
- `wait record` / `WAITING` / `resolve_wait`
- durable cursor descriptor
- Remote wire protocol
- Engine governance 变更
- business tool scanning / `dayu.fins` imports
- EventLog 变更（无新增 event type 写入）

`ToolRuntimeUnsupportedExecutor` 是明确的 P6-S1 stub，它对所有工具调用返回 `ToolFailedOutcome`，不执行、不截断、不 accept、不治理。

## 2. Design Conformance

### DS-S1-PASS-02-同源约束正确

`ToolRuntimeHandle.__post_init__` 强制 `tool_schemas == effective_bundle.tool_schemas`，`DefaultToolRuntimeFactory.create_tool_runtime` 保证 schema 与 executor 来自同一 `effective_bundle` 对象。

RunInputBuilder 的 `_validate_tool_enabled_snapshot` 进一步做 identity check：`tool_snapshot.tool_runtime_handle.tool_executor is not tool_executor`，确保 provider 链路未绕过 handle。`ToolRuntimeSchemaSnapshotProvider` 与 `ToolRuntimeExecutorProvider` 共享同一 `handle_provider`，工具模式构造 `create_tool_enabled_run_input_builder` 中 provider 注入链正确。

### DS-S1-PASS-03-no-tool-replay-防线保持

`create_no_tool_run_input_builder` 对 `NO_TOOL_REPLAY` 与 `NO_TOOL_DISABLED` 均使用 `NoopToolSchemaSnapshotProvider`（返回空 schema）和 `NoToolExecutorProvider`，`_validate_no_tool_snapshot` 要求 `disable_tools=True`、空 schema、`allow_tool_calls=False`、无 handle。replay 防线未弱化。

### DS-S1-PASS-04-PolicySnapshot-拆分正确

`PolicySnapshot.__post_init__` 不再将 `allow_tool_calls=True` 视为构造期错误，仅校验 `policy_snapshot_ref` 非空。工具模式校验交由 RunInputBuilder 的 `_validate_tool_mode_snapshot` 按 `ToolExecutionMode` 分发。拆分正确，未残留 Phase 5 硬编码拒绝。

### DS-S1-PASS-05-Scene-message-工具状态按模式

`_tools_scene_line` 对 `TOOL_ENABLED` 返回 `"tools=enabled"`，对其他模式返回 `"tools=disabled"`。`DefaultSceneParameterProvider.build_scene_messages` 显式接收 `tool_execution_mode` 参数，不再硬编码 `"tools=disabled"`。

## 3. Type Discipline

### DS-S1-PASS-06-无-Any-object-无类型签名

`dayu/host/tool_runtime.py` 和 `dayu/host/run_input.py` 新增代码中未发现 `Any`、`object`、无类型参数或无类型返回值。所有 dataclass 使用 `slots=True` 和显式类型标注。

### DS-S1-PASS-07-中文-docstring-完整

`dayu/host/tool_runtime.py` 模块级、所有类（含 dataclass 和 Protocol）、所有函数均有中文 docstring，覆盖参数、返回值、异常。

`dayu/host/run_input.py` 新增的 `ToolExecutionMode`、`ToolRuntimeHandleProvider`、`StaticToolRuntimeHandleProvider`、`ToolRuntimeSchemaSnapshotProvider`、`ToolRuntimeExecutorProvider`、`_validate_tool_mode_snapshot`、`_validate_tool_enabled_snapshot`、`_tools_scene_line`、`create_tool_enabled_run_input_builder` 均有完整中文 docstring。

## 4. Tests

### DS-S1-F1-已修复-低-test-fetch-more-名称冲突测试使用-str-补丁

- **位置**: `tests/host/test_toolruntime_effective_bundle.py:92-107`（`test_business_bundle_defining_fetch_more_is_rejected`）
- **问题类型**: 测试使用字符串 `"fetch_more"` 作为 match pattern，依赖 `_definition` 中用 `FrameworkToolName.FETCH_MORE.value`。当前实际匹配生产代码 `_validate_reserved_name_conflicts` 中 `definition.name in reserved` 的错误消息。测试通过，但 match pattern 使用字符串字面量而非枚举引用，若枚举值未来变更，测试仍会通过（因生产错误消息也同步变化），但这不是当前切片问题。
- **直接证据**: 测试 `pytest.raises(ValueError, match="fetch_more")` 与生产代码 `f"business ToolBundle contains reserved framework tool name: {definition.name}"` 匹配。
- **影响**: 无当前影响。仅作为风格提示。
- **建议修复**: 无需修复；此发现降级为观察记录，不构成缺陷。

### DS-S1-PASS-08-测试覆盖计划需求

逐一核对 plan §6 P6-S1 tests：

| 计划需求 | 测试函数 | 状态 |
|---|---|---|
| 普通业务工具同源 schema/callable | `test_business_bundle_projects_schema_and_callable_from_same_bundle` | PASS |
| 业务 fetch_more 被拒绝 | `test_business_bundle_defining_fetch_more_is_rejected` | PASS |
| 未启用 framework tool 不注入 fetch_more | `test_disabled_framework_tools_do_not_inject_fetch_more` | PASS |
| PolicySnapshot(allow_tool_calls=True) 构造成功 | `test_policy_snapshot_allows_tool_policy_for_tool_enabled` | PASS |
| tool-enabled RunInputBuilder 暴露 schema/executor | `test_tool_enabled_request_uses_toolruntime_handle` | PASS |
| tool-enabled scene 不含 tools=disabled | `test_tool_enabled_request_uses_toolruntime_handle` 子断言 | PASS |
| replay/no-tool 无 schema 且 allow_tool_calls=False | `test_replay_no_tool_request_keeps_tools_disabled` | PASS |
| replay/no-tool scene 仍表达 tools=disabled | `test_replay_no_tool_request_keeps_tools_disabled` 子断言 | PASS |
| pyright 无 Any/object | pyright 0 errors | PASS |

### DS-S1-F2-未修复-低-缺少-create_no_tool-TOOL_ENABLED-拒绝测试

- **位置**: `dayu/host/run_input.py:866-867`
- **问题类型**: 测试缺口——防御性 guard 未被覆盖。
- **直接证据**: `create_no_tool_run_input_builder` 有显式 guard `if tool_execution_mode == ToolExecutionMode.TOOL_ENABLED: raise ValueError(...)`，但测试文件中无任何测试传入 `TOOL_ENABLED` 并断言 `ValueError`。
- **影响**: 低。该 guard 由调用方 dispatch 层保证不会被误用（当前 dispatch 仍然只构造 no-tool 路径）。但在 dispatch 接入 tool-enabled 路径时（P6-S3），若错误传入 `TOOL_ENABLED` 到此 factory 而未在 dispatch 层报错，则此 guard 成为最后防线。缺少测试意味着回归保护不足。
- **建议修复**: 在 `tests/host/test_run_input_builder.py` 增加测试：传入 `tool_execution_mode=ToolExecutionMode.TOOL_ENABLED` 到 `create_no_tool_run_input_builder`，断言 `ValueError`。无需 durable store。

### DS-S1-F3-未修复-低-EffectiveToolBundleBuildRequest-缺少-TruncationManager-类型占位

- **位置**: `dayu/host/tool_runtime.py:266-279`（`EffectiveToolBundleBuildRequest`）
- **问题类型**: 类型契约与 plan §3.2 不完全一致。
- **直接证据**: Plan §3.2 规定 `EffectiveToolBundleBuilder` 输入包含 `TruncationManager | None`，但 `EffectiveToolBundleBuildRequest` 仅有 `business_tool_bundle`、`source_refs`、`framework_tool_policy`、`policy_snapshot_digest` 四个字段。P6-S4 实现 TruncationManager 时，必须修改此 dataclass 结构。
- **影响**: 低。不影响当前切片正确性（P6-S1 明确不实现 TruncationManager）。但 plan §6 P6-S1 要求"Add dayu/host/tool_runtime.py with module docstring and typed dataclasses/protocols listed in §3.2 / §3.3"——若按字面解释，类型占位应在 S1 到位。实际 S1 选择了推迟，P6-S4 需承担此类型契约变更。
- **建议修复**: 两种选择：① P6-S1 不修复，在 P6-S4 实施 artifact 中明确记录本次推迟；② P6-S1 增加 `truncation_manager: TruncationManager | None = None` 字段作为占位（不连线逻辑）。建议选择①，因为无用字段增加噪声。

### DS-S1-PASS-09-测试有意义且非表面

`test_business_bundle_projects_schema_and_callable_from_same_bundle` 不仅检查 schema 名称，还验证 `definitions_by_name` 中的 callable 绑定与 `ToolRuntimeUnsupportedExecutor.effective_bundle` 同源引用，以及 digest 前缀格式。`test_disabled_framework_tools_do_not_inject_fetch_more` 对注入名称、definitions_by_name 缺失、schema 列表三者做了交叉验证。两个 RunInputBuilder 集成测试通过 durable store 验证全链路。

## 5. Code Quality Observations

### DS-S1-OBS-01-duplicate-effective-tool-name-未测试

- **位置**: `dayu/host/tool_runtime.py:510-525`（`_definitions_by_name`）
- **观察**: `_definitions_by_name` 在发现重复工具名时抛出 `ValueError`。当前无直接测试触发此路径——业务 `ToolBundle` 已做去重，framework tool 注入名不与业务冲突（受 `_validate_reserved_name_conflicts` 保护），因此当前此路径基本不可达。作为 defense-in-depth 可接受。

### DS-S1-OBS-02-validate_no_tool_snapshot-handle-拒绝未直接测试

- **位置**: `dayu/host/run_input.py:1178-1179`
- **观察**: `_validate_no_tool_snapshot` 新增的 `if tool_snapshot.tool_runtime_handle is not None: raise ...` 未单独测试。当前所有 no-tool provider 返回 `None`，故不可触发。作为 defense-in-depth 可接受。

## 6. Verification

- `source .venv/bin/activate && pytest tests/host/test_toolruntime_effective_bundle.py tests/host/test_run_input_builder.py tests/host/test_tooling_options.py tests/host/test_package_exports.py -q` → **28 passed in 0.20s**
- `source .venv/bin/activate && python -m pyright dayu/host tests/host` → **0 errors, 0 warnings, 0 informations**
- `git diff --check` → **passed, no output**

## 7. Conclusion

P6-S1 正确实现了 `EffectiveToolBundle`、`ToolRuntimeHandle`、`ToolExecutionMode`、RunInputBuilder 工具模式验证拆分、scene message 工具状态按模式输出。同源约束、no-tool/replay 防线、PolicySnapshot 拆分均符合设计。类型安全，中文 docstring 完整。测试覆盖计划需求的 9 项中的 9 项。

**Verdict**: PASS（无阻塞项）

**Finding count**: 3 (0 blocking, 2 未修复低严重度, 1 已修复/降级为观察)

**Residual risks**:
- `ToolRuntimeUnsupportedExecutor` 为 P6-S1 stub，P6-S3 替换为真源 executor 时需重新验证同源约束和 RunInputBuilder 验证链路
- `EffectiveToolBundleBuildRequest` 需在 P6-S4 增加 `TruncationManager | None` 字段
- `create_no_tool_run_input_builder` 的 TOOL_ENABLED guard 测试缺口可在 P6-S3 补齐

**Artifact path**: `docs/reviews/host-phase6-code-review-s1-ds-20260515.md`

**Validation note**: 本次审查为只读审查，未修改任何代码、文档、commit 或分支状态。
