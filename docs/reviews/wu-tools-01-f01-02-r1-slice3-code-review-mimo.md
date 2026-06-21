# Code Review

## Scope

- Mode: current changes
- Branch: `phase/wu-tools-01-f01-02-r1`
- Base: `81bc62b9` (Slice 3 checkpoint commit)
- Output file: `docs/reviews/wu-tools-01-f01-02-r1-slice3-code-review-mimo.md`
- Included scope: 8 files changed (uncommitted diff since `81bc62b9`): `dayu/service/host_assembly.py`, `dayu/host/tooling.py`, `dayu/host/dispatch.py`, `tests/service/test_host_assembly.py`, `docs/host/design.md`, `dayu/host/README.md`, `dayu/fins/README.md`, `docs/host/issues-implementation-control.md`
- Excluded scope: 已接受 Slice 1 commit `e10f2e99`、Slice 2 commit `4f45f8de`；`docs/host/issues-implementation-control.md` 仅作状态上下文
- Parallel review coverage: 无

## Findings

### 001-未修复-中-`_fins_wait_activation_registry_from_provider_configs` 中 `build_fins_wait_adapter_registry` 返回值被丢弃

- **入口/函数**: `_fins_wait_activation_registry_from_provider_configs` (`dayu/service/host_assembly.py:1819`)
- **文件(行号)**: `dayu/service/host_assembly.py:1819-1822`
- **输入场景**: 任何启用 Fins awaiting provider 的 Service assembly
- **实际分支**: 执行到 line 1819 时，`build_fins_wait_adapter_registry(workspace_root, tool_names)` 被调用，返回值未赋值给任何变量
- **预期行为**: 若目的是校验 tool_names 合法性，应直接调用 `_deterministic_tool_names(tool_names)` 或 `_require_absolute_workspace_root(workspace_root)`；若目的是复用 wait adapter registry，应保留返回值
- **实际行为**: `build_fins_wait_adapter_registry` 创建了一个完整的 `WaitAdapterRegistry` 对象（包含 `WaitAdapterBinding` 元组），随后立即被 GC。该函数内部还会调用 `_require_absolute_workspace_root` 和 `_deterministic_tool_names` 做校验，但这些校验在 `_fins_wait_adapter_registry_from_provider_configs`（同文件 line 1742，紧接在本函数之前被 `_tooling_options_from_discovery` 调用）中已经执行过
- **直接证据**: `dayu/service/host_assembly.py:1819` — `build_fins_wait_adapter_registry(workspace_root=workspace_root, tool_names=tuple(tool_names))` 无赋值目标；`dayu/service/host_assembly.py:1718-1723` — `_fins_wait_adapter_registry_from_provider_configs` 已对相同输入做过完全相同的校验
- **影响**: 不影响正确性；但调用一个构造完整对象的函数仅为了 side-effect validation 是代码异味，且与 CLAUDE.md "禁止胶水 seam" 约束精神不符。如果 `build_fins_wait_adapter_registry` 未来增加副作用（如日志、metrics），此处会产生意外行为
- **建议改法和验证点**: 删除 line 1819-1822 的 `build_fins_wait_adapter_registry` 调用。若需要独立校验 tool_names，改为直接调用 `_deterministic_tool_names(tool_names)`（该函数已存在于 `dayu/fins/ingestion/wait_adapter.py:266`）。验证点：运行 `tests/service/test_host_assembly.py` 确认 52 passed
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 中

### 002-未修复-低-`_DisabledProviderCallable.__call__` 是死代码

- **入口/函数**: `_DisabledProviderCallable.__call__` (`dayu/service/host_assembly.py:431-453`)
- **文件(行号)**: `dayu/service/host_assembly.py:431-453`
- **输入场景**: 任何 disabled provider config
- **实际分支**: `_tool_discovery_bindings` 为 disabled provider 创建 binding 时附加 `_DisabledProviderCallable()`（line 1109）；但 `discover_from_bindings` 在 `spec.enabled is False` 时直接 `continue`（`dayu/runtime/tools_discovery.py:234`），永不调用该 callable
- **预期行为**: 若 callable 永不被调用，`__call__` 方法体应为 `...` 或 `pass`，或使用 Protocol sentinel
- **实际行为**: `__call__` 包含完整实现（构造 `ToolsDiscoveryProviderOutput`），但永远不会执行
- **直接证据**: `dayu/runtime/tools_discovery.py:233-236` — `if not binding.spec.enabled: continue` 在 `output = binding.provider(binding.spec)` 之前
- **影响**: 不影响正确性；但完整实现的死代码会误导读者认为该路径有实际作用
- **建议改法和验证点**: 将 `__call__` 方法体简化为 `raise NotImplementedError("disabled provider callable must not be invoked")` 或保持类型占位但删除实现体。验证点：运行 `tests/service/test_host_assembly.py` 确认无回归
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低

### 003-未修复-低-`_fins_wait_adapter_registry_from_provider_configs` 与 `_fins_wait_activation_registry_from_provider_configs` 存在结构重复

- **入口/函数**: `_fins_wait_adapter_registry_from_provider_configs` 和 `_fins_wait_activation_registry_from_provider_configs` (`dayu/service/host_assembly.py:1742-1832`)
- **文件(行号)**: `dayu/service/host_assembly.py:1742-1832`
- **输入场景**: 所有启用 Fins awaiting provider 的 Service assembly
- **实际分支**: 两个函数各自独立遍历 `provider_configs`，执行相同的 enabled 检查、`_fins_awaiting_tool_name_from_provider_config` 调用、`available_tool_names` 过滤、`_fins_workspace_root_from_provider_config` 收集、`_single_fins_workspace_root` 校验
- **预期行为**: 共享的 provider config 遍历和校验逻辑应抽取为私有辅助函数
- **实际行为**: 约 15 行相同的遍历/过滤/校验逻辑在两个函数中各出现一次
- **直接证据**: `dayu/service/host_assembly.py:1756-1772` vs `dayu/service/host_assembly.py:1797-1813` — 逐行对比结构完全相同
- **影响**: 不影响正确性；但增加维护成本，修改校验逻辑时需要同步两处
- **建议改法和验证点**: 抽取 `_collect_fins_awaiting_provider_info(provider_configs, available_tool_names) -> tuple[tuple[str, ...], pathlib.Path] | None` 辅助函数。验证点：运行 `tests/service/test_host_assembly.py` 确认无回归
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低

## Open Questions

- 无。

## Residual Risk

1. **Poll adapter 未在生产路径装配**: `WaitPollAdapterRegistry` 和 `WaitPoller` 仅在测试中构造，未进入 `host_assembly.py` 的生产装配路径。当前 Slice 3 的目标是 "prepare + activate" 两阶段，不包含 poll；但如果后续需要 poll-based resume，需要额外 wiring。这不是 Slice 3 的 defect，但应作为 follow-up 记录。

2. **activation adapter 的 `_operation_kind_from_tool_name` 依赖隐式映射**: `FinsIngestionWaitActivationAdapter.activate_accepted_wait` 调用 `_operation_kind_from_tool_name(request.tool_name)` 将工具名映射为 `FinsOperationKind`。该映射在 `dayu/fins/ingestion/wait_adapter.py` 内部定义，如果新增 Fins awaiting 工具但未更新映射，activation 会抛出 `ValueError`。当前三个工具（download/preprocess/upload）已覆盖，风险可控。

3. **测试 `_wait_until_observation_leaves_pending` 使用轮询**: 测试中的 `_wait_until_observation_leaves_pending` 辅助函数使用 `asyncio.sleep(0.01)` 轮询 100 次（共 1 秒）。这在 CI 环境中可能因系统负载而偶尔超时。当前 timeout 设为 1 秒，对 `activate_observation` 这种同步操作足够，但在慢 CI 上可能需要放宽。

4. **`ServiceDiscoveredTools.fins_awaiting_runtime` 类型为 `FinsObservationRuntime | None`**: 该字段类型是 `FinsObservationRuntime`（Protocol），但 `_fins_wait_activation_registry_from_provider_configs` 使用 `isinstance(fins_awaiting_runtime, FinsIngestionRuntime)` 做运行时类型检查。如果未来有其他 `FinsObservationRuntime` 实现，该检查会拒绝它。当前只有 `FinsIngestionRuntime` 一个实现，风险可控。

## Conclusion

**pass**

Slice 3 实现正确完成了 Service wiring：`HostToolingOptions.wait_activation_registry` 通过 dispatch 正确传递到 `ToolRuntimeBuildRequest`，再到 `ToolRuntimeExecutor`，最终在 `_activate_accepted_wait_best_effort` 中使用。Fins awaiting tool callable 与 activation adapter 共享同一个 `FinsIngestionRuntime` 实例（测试通过 `is` identity 断言验证）。disabled provider 语义未改变。docs 更新必要且最小，无 Engine public contract / LLM-facing schema 变化。测试 52 passed，pyright 0 errors。

存在一个中等严重度 finding（`build_fins_wait_adapter_registry` 返回值被丢弃）和两个低严重度 finding（dead code、结构重复），均不影响正确性。无 blocker。
