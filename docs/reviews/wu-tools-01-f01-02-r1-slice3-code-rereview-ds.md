# WU-TOOLS-01-F01-02-R1 Slice 3 Code Re-Review (AgentDS)

## Scope

- **Mode**: current changes — Slice 3 code-review fix re-review
- **Branch**: `phase/wu-tools-01-f01-02-r1`
- **Base**: original Slice 3 checkpoint `81bc62b9`; this re-review covers the fix diff on top of the initial Slice 3 implementation
- **Timestamp**: 20260621-200925
- **Output file**: `docs/reviews/wu-tools-01-f01-02-r1-slice3-code-rereview-ds.md`
- **Input artifacts**:
  - Implementation: `docs/reviews/wu-tools-01-f01-02-r1-slice3-implementation-codex.md`
  - Code review (MiMo): `docs/reviews/wu-tools-01-f01-02-r1-slice3-code-review-mimo.md`
  - Code review (DS): `docs/reviews/wu-tools-01-f01-02-r1-slice3-code-review-ds.md`
  - Controller adjudication: `docs/reviews/wu-tools-01-f01-02-r1-slice3-code-review-controller-adjudication.md`
  - Fix artifact: `docs/reviews/wu-tools-01-f01-02-r1-slice3-fix-codex.md`
- **Included scope**: 修改的源码文件 `dayu/service/host_assembly.py`、`dayu/fins/ingestion/wait_adapter.py`、`tests/service/test_host_assembly.py`、`dayu/host/tooling.py`、`dayu/host/dispatch.py` 的完整 fix diff
- **Excluded scope**: README/design doc 变更；已接受 Slice 1/2 commits
- **Parallel review coverage**: 无 subagent；本 re-review 单路覆盖所有 fix 点

## Validation Baseline

- `pytest tests/service/test_host_assembly.py -q`: **52 passed**, 3 warnings（均为 edgar 第三方弃用警告）
- `pytest tests/host/test_toolruntime_executor.py tests/host/test_phase7_waiting_integration.py tests/fins/test_fins_ingestion_tools.py tests/fins/test_fins_ingestion_runtime.py -q`: **159 passed**, 3 warnings（同上）
- `pyright`: **0 errors, 0 warnings, 0 informations**
- `git diff --check`: **passed**

## Findings

### R1-已修复-低-`_tool_discovery_specs` 是死生产代码

- **入口/函数**: `_tool_discovery_specs`（`dayu/service/host_assembly.py:1045`）
- **文件(行号)**: `dayu/service/host_assembly.py:1045-1055`
- **输入场景**: 无——该函数不被任何生产路径调用
- **实际分支**: N/A——该函数不存在于任何生产调用链中
- **预期行为**: 生产代码中不应保留已被替换的旧函数
- **实际行为**: `_tool_discovery_specs` 仅在测试文件中被引用（`tests/service/test_host_assembly.py:94` 导入，多处测试函数调用），生产路径已切换为 `_tool_discovery_bindings` → 循环调用 `_tool_discovery_spec`（单数形式）。`_tool_discovery_specs` 的函数体仅转发到 `_tool_discovery_spec`：`return tuple(_tool_discovery_spec(provider_config) for provider_config in provider_configs)`
- **直接证据**:
  - `grep -rn "_tool_discovery_specs" dayu/` 仅命中 line 1045 定义行
  - `discover_service_tools` (line 459) 已改为调用 `_tool_discovery_bindings` 而非 `_tool_discovery_specs`
  - 测试文件 `tests/service/test_host_assembly.py` 中 7 个测试函数直接调用 `_tool_discovery_specs`，但测试目标是被替换的旧接口
- **影响**: 死代码违反 CLAUDE.md "禁止兼容性代码" 约束。保留该函数会误导维护者认为它仍是生产路径的一部分。测试覆盖了正确的逻辑但测试目标错误——应改为测试 `_tool_discovery_spec`（单数）或通过 `_tool_discovery_bindings` 间接测试
- **建议改法和验证点**: 删除 `_tool_discovery_specs`；将调用它的测试迁移为测试 `_tool_discovery_spec` 或 `_tool_discovery_bindings`。该清理不属于本次 fix gate 的必要范围，但应在下一轮清理中处理
- **修复风险（低）**: 纯删除 + 测试迁移，不改变生产行为
- **严重程度（低）**: 死代码维护负担，非 correctness bug。注意本 finding 不属于当前 fix gate 的 blocking scope

## Verified Fix Points

### S3-CR-F01 ✅：`build_fins_wait_adapter_registry` 调用已移除，校验保持直接等价

- **入口/函数**: `_fins_wait_activation_registry_from_provider_configs` (line 1771)
- **验证点**:
  - 废弃的 `build_fins_wait_adapter_registry(...)` 调用已完全从函数体中移除
  - 等价的校验链路：`_fins_awaiting_registry_inputs_from_provider_configs` 提供 workspace_root 校验（经 `_fins_workspace_root_from_provider_config` 验证绝对路径 + `_single_fins_workspace_root` 验证一致性）+ `_require_distinct_fins_awaiting_tool_names` 直接验证无重复工具名
  - workspace_root 绝对路径校验由 `_fins_workspace_root_from_provider_config` (line 1896) 通过 `workspace_root.is_absolute()` 和 `resolve(strict=False)` 保证——与旧代码中 `_require_absolute_workspace_root` 等价
  - 工具名合法性校验由 `_fins_awaiting_tool_name_from_provider_config`（仅返回三个已知常量名）+ `available_tool_names` 过滤隐式保证——旧代码中 `_deterministic_tool_names` 的 supported-name check 在此路径下冗余
  - `WaitActivationRegistry` 构造行为不变：仍注册一个 `FinsIngestionWaitActivationAdapter` 在 `FINS_INGESTION_WAIT_ADAPTER_KEY` 下

### S3-CR-F02 ✅：`_DisabledProviderCallable.__call__` 是明确的 fail-fast sentinel

- **入口/函数**: `_DisabledProviderCallable.__call__` (line 443)
- **验证点**:
  - 函数体现在 `raise RuntimeError("disabled tools discovery provider callable must not be invoked")`——不再是构造 `ToolsDiscoveryProviderOutput` 的死代码
  - `ToolsDiscovery.discover_from_bindings` (line 233: `if not binding.spec.enabled: continue`) 在 provider 调用前跳过 disabled spec——RuntimeError 仅在框架契约被破坏时触发
  - Disabled provider 的 discovery reporting 行为不变——disabled spec 不进入 discover_from_bindings 的 provider 调用循环，不产生 provider report

### S3-CR-F03 ✅：Fins awaiting provider 收集已小 helper 复用

- **入口/函数**: `_fins_awaiting_registry_inputs_from_provider_configs` (line 1814)
- **验证点**:
  - 新增 `_FinsAwaitingRegistryInputs` frozen dataclass 和 `_fins_awaiting_registry_inputs_from_provider_configs` 私有辅助函数
  - Helper 仅集中了 Slice 3 中重复的 provider 筛选（enabled 检查、`_fins_awaiting_tool_name_from_provider_config` 识别、`available_tool_names` 过滤、workspace_root 收集、`_single_fins_workspace_root` 校验）
  - `_fins_wait_adapter_registry_from_provider_configs` 和 `_fins_wait_activation_registry_from_provider_configs` 均通过 `registry_inputs = _fins_awaiting_registry_inputs_from_provider_configs(...)` 消费
  - 未引入通用平台化抽象——helper 返回结构体仅包含 `tool_names` 和 `workspace_root` 两个字段，函数签名为模块级私有
  - 两个 registry 构造函数中消费 helper 的逻辑：adapter registry 直接使用 `registry_inputs.workspace_root` 和 `registry_inputs.tool_names`；activation registry 额外检查 `fins_awaiting_runtime` 的 None/isinstance，并调用 `_require_distinct_fins_awaiting_tool_names`——差异合理且符合各 registry 的语义需要

### S3-CR-F04 ✅：`_tooling_options_from_discovery` 的 `fins_awaiting_runtime` 参数已显式化

- **入口/函数**: `_tooling_options_from_discovery` (line 1697)
- **验证点**:
  - `fins_awaiting_runtime` 参数签名从 `FinsObservationRuntime | None = None` 改为 `FinsObservationRuntime | None`（无默认值，调用方必须显式传参）
  - Docstring 明确说明："没有 Fins awaiting provider 时显式传 ``None``"
  - 所有现有调用方已验证正确传参：`_compose_options` (line 788) 传 `request.discovered_tools.fins_awaiting_runtime`；全部 no-Fins-awaiting 测试传 `fins_awaiting_runtime=None`
  - No-Fins-awaiting 行为不变：显式 `None` 经 `_fins_wait_activation_registry_from_provider_configs` 的 `registry_inputs is None` 早期返回仍产生 `wait_activation_registry=None`

### S3-CR-F05 ✅：Standalone activation builder 已有 runtime-sharing guardrail

- **入口/函数**: `build_fins_wait_activation_registry` (`dayu/fins/ingestion/wait_adapter.py:226`)
- **验证点**:
  - Docstring 新增 guardrail：`"生产 Service assembly 中，awaiting tool callable、poll adapter 与 activation adapter 必须共享同一个 FinsIngestionRuntime 实例；本 standalone builder 只适用于由调用方自行保证 runtime 一致性的独立装配场景。"`——位置在 docstring 第二段，显眼且明确
  - 生产 Service assembly 路径（`_fins_wait_activation_registry_from_provider_configs` line 1806）直接构造 `FinsIngestionWaitActivationAdapter(runtime=fins_awaiting_runtime)`，使用共享 runtime——与 standalone builder 的 `from_workspace_root()` 路径隔离
  - 测试 `test_service_fins_awaiting_wiring_uses_shared_runtime_for_activation` 通过 `is` identity 断言验证 `activation_adapter.runtime is callable_.runtime`——确保生产路径使用同一 runtime 实例
  - 未新增 broad builder API 或生命周期平台——guardrail 仅为 docstring 注释

## Test Verification

### Service tests（tests/service/test_host_assembly.py）

- 全部 **52 passed**，包含：
  - 原有的 `_tool_discovery_specs` 测试（7 个）——测试逻辑仍有效但测试目标函数已死
  - 原有 `_tooling_options_from_discovery` 测试——所有 no-Fins-awaiting 用例已添加显式 `fins_awaiting_runtime=None` 传参
  - 原有 Fins workshop root / duplicate binding 校验测试——全部更新了新增的 `fins_awaiting_runtime` 参数并额外断言 `wait_activation_registry is None`
  - 新增 `test_service_fins_awaiting_wiring_uses_shared_runtime_for_activation`——验证完整 Service discovery → HostToolingOptions → shared runtime → tool callable → activation adapter 链路，含 observation PENDING → activated 状态转换

### Focused Host/Fins tests

- 全部 **159 passed**，覆盖 `test_toolruntime_executor`、`test_phase7_waiting_integration`、`test_fins_ingestion_tools`、`test_fins_ingestion_runtime`
- 测试计数与 fix artifact 声明一致（159 passed, 3 warnings）

### pyright

- **0 errors, 0 warnings, 0 informations**——所有新增类型声明（`_FinsAwaitingRegistryInputs`、`_FinsAwaitingProviderMetadata`、`_FinsAwaitingProviderCallable`、`WaitActivationRegistry` 等）通过严格类型检查

### git diff --check

- **passed**——无空白问题

## Regression Check

### 无行为回归

- **Disabled provider**: behavior unchanged——`_DisabledProviderCallable` 仍通过 `ToolsDiscoveryProviderBinding` 传递，`discover_from_bindings` 跳过 disabled spec 后不调用 provider
- **Non-Fins provider discovery**: behavior unchanged——`_tool_discovery_bindings` 的 else 分支（line 1121-1126）为所有非 Fins awaiting 的启用 provider 调用 `resolve_provider_callable(spec)`
- **Wait adapter registry**: behavior unchanged——`_fins_wait_adapter_registry_from_provider_configs` 仍通过 `build_fins_wait_adapter_registry` 构造 `WaitAdapterRegistry`；其内部的 `_deterministic_tool_names` 校验（含 strip、supported-name check、duplicate check）未被修改
- **Activation registry**: behavior unchanged——`_fins_wait_activation_registry_from_provider_configs` 新增了 `fins_awaiting_runtime is None` 和 `isinstance` 的 fail-fast 守卫（相较于旧代码无此检查时更安全），但生产路径（Service assembly 传共享 runtime）的正常行为完全相同

### 无 scope creep

- 所有新增类型和函数均为模块级私有（`_` 前缀）
- `_FinsAwaitingRegistryInputs` 仅包含 2 个字段（`tool_names`、`workspace_root`），不承载治理标识
- `_FinsAwaitingProviderMetadata` 仅包含 4 个字段（`tool_name`、`provider_id`、`version_ref`、`source_id`），为 Fins awaiting 专有
- 未触及 Engine public contract、LLM-facing schema、durable wait record 格式、EventLog canonical fact、或跨 provider 生命周期抽象

### 测试未被改弱

- 原有测试仅在参数列表中添加显式 `fins_awaiting_runtime=None` 传参——无 assertion 移除或弱化
- `test_tooling_options_without_fins_awaiting_providers_has_no_wait_adapter_registry` 和 `test_tooling_options_skips_wait_adapter_for_missing_awaiting_tool_definition` 新增 `wait_activation_registry is None` 断言——加强了测试覆盖
- 新增 `test_service_fins_awaiting_wiring_uses_shared_runtime_for_activation` 添加了 identity 断言和行为断言——增强了测试覆盖

## Open Questions

1. **`_tool_discovery_specs` 死代码清理时机**：该函数仅被测试调用，不进入任何生产路径。是否在本次 slice 的 scope 内清理？当前 re-review 将其标记为低严重度 finding（R1），建议在后续清理 pass 中处理，不阻塞本次 fix gate closeout。

## Residual Risk

1. 与原始 Slice 3 review 一致：production poller scheduling、backoff、fencing、retry（GitHub Issue #90）和 external provider physical cancel/revoke（GitHub Issue #92）仍在本 Slice 范围外，本次 fix 未扩展这些能力
2. 与原始 Slice 3 review 一致：`compose_open_host_options` → dispatch → `ToolRuntimeBuildRequest` → `ToolRuntimeExecutor._activate_accepted_wait` 的完整端到端 dispatch worker activation 路径未被测试覆盖；当前聚焦测试验证了 Service discovery → HostToolingOptions → shared runtime → activation adapter 链路
3. Standalone `build_fins_wait_activation_registry` 的 runtime 不一致风险仅通过 docstring guardrail 文档化，未在类型系统或运行时强制校验；当前无生产调用方使用该 standalone builder

## Conclusion

**pass** — 无阻断性问题。

五项 controller accepted findings (S3-CR-F01 至 S3-CR-F05) 均已被正确、最小地修复：
- S3-CR-F01：废弃的 `build_fins_wait_adapter_registry` 调用已移除，校验链路等价且显式
- S3-CR-F02：`_DisabledProviderCallable.__call__` 为明确的 fail-fast sentinel
- S3-CR-F03：provider 收集逻辑已小 helper 复用，未引入通用平台化抽象
- S3-CR-F04：`fins_awaiting_runtime` 参数已显式化，消除默认 None 误导
- S3-CR-F05：standalone builder 和 production path 均有 runtime-sharing guardrail 文档说明

所有测试通过（Service 52 passed + Host/Fins 159 passed），pyright 0 errors，diff check passed。无行为回归，无 scope creep，无测试弱化。发现一个低严重度新 finding（`_tool_discovery_specs` 死生产代码），建议在后续清理中处理，不阻塞本次 fix gate closeout。
