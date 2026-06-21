# Code Review — WU-TOOLS-01-F01-02-R1 Slice 3 (AgentDS)

## Scope

- **Mode**: current changes
- **Branch**: `phase/wu-tools-01-f01-02-r1`
- **Base**: Slice 3 checkpoint commit `81bc62b9`（已接受 Slice 1 `e10f2e99`、Slice 2 `4f45f8de`）
- **Output file**: `docs/reviews/wu-tools-01-f01-02-r1-slice3-code-review-ds.md`
- **Timestamp**: 20260621-194810
- **Included scope**: `dayu/service/host_assembly.py`、`dayu/host/tooling.py`、`dayu/host/dispatch.py`、`tests/service/test_host_assembly.py`、`docs/host/design.md`、`dayu/host/README.md`、`dayu/fins/README.md` 中自 checkpoint 以来的未提交 diff
- **Excluded scope**: 已提交 Slice 1/2；`docs/host/issues-implementation-control.md`（仅作状态上下文）；`docs/reviews/wu-tools-01-f01-02-r1-slice3-implementation-codex.md`（Codex 实现 artifact，不作为 review 目标）
- **Parallel review coverage**: 无 subagent；本 review 单路覆盖所有重点文件
- **Validation baseline**: `pytest tests/service/test_host_assembly.py -q` 52 passed；`pyright` 0 errors, 0 warnings, 0 informations

## Findings

### 1-未修复-中-`_fins_wait_activation_registry_from_provider_configs` 中 `build_fins_wait_adapter_registry()` 调用丢弃返回值，仅作副作用校验

- **入口/函数**: `_fins_wait_activation_registry_from_provider_configs`
- **文件(行号)**: `dayu/service/host_assembly.py:1819-1822`
- **输入场景**: 任何启用 Fins awaiting provider 的 Service assembly
- **实际分支**: `if not tool_names: return None` 之后的正常返回路径
- **预期行为**: 构造 `WaitActivationRegistry` 前完成 workspace_root 与 tool_names 合法性校验
- **实际行为**: 调用了 `build_fins_wait_adapter_registry(workspace_root=..., tool_names=...)` 但完全丢弃其返回值。该函数构造的是 `WaitAdapterRegistry`（用于 Host poller 的 wait adapter binding），而非本函数需要产出的 `WaitActivationRegistry`。该调用仅利用其内部的 `_require_absolute_workspace_root` 和 `_deterministic_tool_names` 校验副作用。
- **直接证据**:
  - Line 1819-1822: `build_fins_wait_adapter_registry(workspace_root=workspace_root, tool_names=tuple(tool_names))` — 返回值未被赋值
  - Line 1823-1832: 实际返回的是直接构造的 `WaitActivationRegistry`，与 `build_fins_wait_adapter_registry` 的返回值类型无关
  - 同一文件 line 1773-1776: `_fins_wait_adapter_registry_from_provider_configs` 已独立调用 `build_fins_wait_adapter_registry` 并正确使用其返回值
- **影响**: 不产生运行时错误，但具有维护误导性。未来维护者阅读此函数时会困惑为什么在构造 `WaitActivationRegistry` 时需要创建一个被丢弃的 `WaitAdapterRegistry`。如果 `build_fins_wait_adapter_registry` 未来产生副作用（如创建 Fins runtime 或其他资源），这里会引入隐蔽的资源泄漏或双重初始化。
- **建议改法和验证点**: 将校验逻辑抽取为独立的 `_validate_fins_wait_adapter_tool_names(tool_names)` 和已有的 `_require_absolute_workspace_root` 调用，直接在本函数内完成校验，删除对 `build_fins_wait_adapter_registry` 的误导性调用。验证：确认现有 Fins workspace root / duplicate binding 测试仍然通过。
- **修复风险（低）**: 纯重构，不改变行为。
- **严重程度（中）**: 维护期误导风险，不属于 correctness bug。

### 2-未修复-低-`_fins_wait_activation_registry_from_provider_configs` 与 `_fins_wait_adapter_registry_from_provider_configs` 共享大量重复的 provider 筛选与 workspace 收集逻辑

- **入口/函数**: `_fins_wait_activation_registry_from_provider_configs`、`_fins_wait_adapter_registry_from_provider_configs`
- **文件(行号)**: `dayu/service/host_assembly.py:1742-1776` vs `1779-1832`
- **输入场景**: 同一 `_tooling_options_from_discovery` 调用中对两个 registry 分别构造
- **实际分支**: 两个函数独立执行相同的迭代-筛选-收集逻辑
- **预期行为**: 对 provider_configs 的迭代、enabled 检查、`_fins_awaiting_tool_name_from_provider_config` 识别、`available_tool_names` 过滤、`_fins_workspace_root_from_provider_config` 提取和 `_single_fins_workspace_root` 校验在各函数内独立执行一次
- **实际行为**: 逻辑完全重复，但当前行为一致（相同的排序键、相同的过滤条件、相同的校验）。两个函数的差异仅在于最终构造的 registry 类型不同（`WaitAdapterRegistry` vs `WaitActivationRegistry`）。
- **直接证据**:
  - Lines 1756-1776: adapter registry 的筛选-收集逻辑
  - Lines 1797-1822: activation registry 的筛选-收集逻辑 — 除注释和最终返回类型外，前面的逻辑逐行相同
- **影响**: 当前不产生行为错误（因为两边逻辑相同），但未来若需要调整 Fins awaiting provider 筛选规则（如新增 tool 类型、改变识别方式），需要在两处同步修改，容易引入漂移。
- **建议改法和验证点**: 抽取共享的 `_collect_fins_awaiting_tool_names_and_workspace_root(provider_configs, available_tool_names)` 辅助函数，返回 `(tool_names, workspace_root)`，两个 registry 构造函数各自消费。验证：现有全集测试通过。
- **修复风险（低）**: 纯提取重构。
- **严重程度（低）**: 维护负担，非 correctness bug。

### 3-未修复-低-`_tooling_options_from_discovery` 的 `fins_awaiting_runtime` 参数默认值为 `None` 且仅有文档约束

- **入口/函数**: `_tooling_options_from_discovery`
- **文件(行号)**: `dayu/service/host_assembly.py:1699`
- **输入场景**: 调用方未传递 `fins_awaiting_runtime` 但有 Fins awaiting provider 需要 activation
- **实际分支**: `fins_awaiting_runtime=None` 进入 `_fins_wait_activation_registry_from_provider_configs`，在 line 1814-1815 触发 `ValueError`
- **预期行为**: fail-fast 并给出清晰错误
- **实际行为**: 确实会 fail-fast——`_fins_wait_activation_registry_from_provider_configs` 在 line 1814-1815 检查了 `fins_awaiting_runtime is None` 并抛出 `ValueError("Fins wait activation registry requires shared runtime")`。但该防护仅当存在需要 activation 的 provider 时生效；若无 Fins awaiting provider，参数被静默忽略。当前唯一调用方 `compose_open_host_options` 正确传递了该参数。
- **直接证据**: line 1699 `fins_awaiting_runtime: FinsObservationRuntime | None = None`；line 1814-1815 的 None 检查
- **影响**: 当前无实际风险（调用方正确传递），但默认值 `None` 暗示该参数"可选"，而实际上当存在 Fins awaiting provider 时它是必需的。如果未来新增调用方，容易因默认值误导而遗漏传参。
- **建议改法和验证点**: 移除默认值，要求调用方显式传参；或将参数拆分为独立构造步骤，使 wait_activation_registry 的构造与 `_tooling_options_from_discovery` 解耦，避免混合可选/必选语义。验证：当前测试不变。
- **修复风险（低）**: 接口微调，唯一调用方已正确传参。
- **严重程度（低）**: 设计偏好，非 correctness bug。

## Open Questions

1. `build_fins_wait_activation_registry`（`dayu/fins/ingestion/wait_adapter.py:226-251`）通过 `FinsIngestionWaitActivationAdapter.from_workspace_root()` 创建独立的 `FinsIngestionRuntime`，而非使用共享 runtime。该函数在当前 Slice 3 Service assembly 路径中未被调用（Service 路径直接构造 `FinsIngestionWaitActivationAdapter(runtime=shared_runtime)`），但其存在于公共 API 中。未来调用方若使用 `build_fins_wait_activation_registry` 而非 Service assembly 路径，会导致 activation adapter 持有与 tool callable 不同的 runtime 实例，observation 将无法被激活。是否需要为该公共函数补充文档说明其与共享 runtime 路径的关系？

## Residual Risk

1. **Production poller/activation 不在本 Slice 范围内**: 当前 activation 仅在 process-local 内存 observation registry 中生效；生产 poller scheduling、backoff、fencing、retry 和跨进程/跨重启恢复仍属于 GitHub Issue #90/#92。本 Slice 未引入 durable prepared status 或 lifecycle supervisor。
2. **测试不覆盖 `compose_open_host_options` 的完整 Fins awaiting activation 端到端路径**: `test_service_fins_awaiting_wiring_uses_shared_runtime_for_activation` 直接调用 `discover_service_tools` + `_tooling_options_from_discovery`，绕过了 `compose_open_host_options` → dispatch → `ToolRuntimeBuildRequest` 的完整 wiring。完整端到端 activation 路径（`open_host` → dispatch commit → worker accept → `_activate_accepted_wait`）未被测试覆盖。
3. **`_FinsAwaitingProviderCallable.__call__` 忽略 `spec` 参数（line 402 `del spec`）**: 该 callable 不消费 ToolsDiscovery 传入的 provider spec，直接使用构造期绑定的 metadata 和 runtime。如果未来 ToolsDiscovery 在 spec 上附加运行时上下文（如 per-call config override），该 callable 将静默忽略。当前 ToolsDiscovery contract 不要求 callable 消费 spec，故属远期风险。
4. **Workspace root 跨 provider 一致性的校验时机**: `_single_fins_workspace_root` 在 `_shared_fins_awaiting_runtime_from_provider_configs`、`_fins_wait_adapter_registry_from_provider_configs` 和 `_fins_wait_activation_registry_from_provider_configs` 中各自独立调用。三次调用校验相同的一致性约束，但分布在三个独立函数中，不存在结构保证它们必然全部执行。

## Conclusion

**Pass** — 无阻断性问题。

核心 wiring 正确：`HostToolingOptions.wait_activation_registry` → `ToolRuntimeBuildRequest.wait_activation_registry` → `ToolRuntimeExecutor._wait_activation_registry` → `_activate_accepted_wait()` 链路完整且参数逐层传递一致。Fins awaiting tool callable 与 activation adapter 共享同一个 `FinsIngestionRuntime` 实例，经测试 `is` 身份验证确认和实际 `activate_observation` 行为验证通过。Service discovery 特化未改变 disabled provider、普通 provider discovery 或 provider config reporting 语义。文档更新必要且最小，无 Engine public contract / LLM-facing schema 变化，无 scope creep。测试覆盖了 accepted activation 路径的关键行为，pyright 和测试均通过。

3 个 findings 均为中/低严重度的代码组织与维护性问题，不构成 merge blocker。5 个 residual risks/open questions 已记录以供后续关注。
