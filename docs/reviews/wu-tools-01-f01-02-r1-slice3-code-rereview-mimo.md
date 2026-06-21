# Re-Review — WU-TOOLS-01-F01-02-R1 Slice 3 Code Review Fix (AgentMiMo)

## Scope

- Mode: current changes
- Branch: `phase/wu-tools-01-f01-02-r1`
- Base: `81bc62b9` (Slice 3 checkpoint commit)
- Timestamp: 20260621-200752
- Output file: `docs/reviews/wu-tools-01-f01-02-r1-slice3-code-rereview-mimo.md`
- Included scope: Slice 3 implementation + code-review fix diff（`dayu/service/host_assembly.py`、`dayu/host/tooling.py`、`dayu/host/dispatch.py`、`tests/service/test_host_assembly.py`、`dayu/fins/ingestion/wait_adapter.py`、docs）
- Excluded scope: 已接受 Slice 1/2 commits；plan / control docs；另一路 reviewer artifact
- Input artifacts:
  - `docs/reviews/wu-tools-01-f01-02-r1-slice3-implementation-codex.md`
  - `docs/reviews/wu-tools-01-f01-02-r1-slice3-code-review-mimo.md`
  - `docs/reviews/wu-tools-01-f01-02-r1-slice3-code-review-ds.md`
  - `docs/reviews/wu-tools-01-f01-02-r1-slice3-code-review-controller-adjudication.md`
  - `docs/reviews/wu-tools-01-f01-02-r1-slice3-fix-codex.md`

## Findings

未发现实质性问题。

以下逐项验证 controller accepted findings S3-CR-F01 至 S3-CR-F05 的修复正确性。

## S3-CR-F01 验证：丢弃的 `build_fins_wait_adapter_registry` 调用已移除

- **修复前**: `_fins_wait_activation_registry_from_provider_configs` 调用 `build_fins_wait_adapter_registry(workspace_root, tool_names)` 但丢弃返回值，仅利用其内部校验副作用。
- **修复后**: 该函数现在调用 `_fins_awaiting_registry_inputs_from_provider_configs` 获取 `_FinsAwaitingRegistryInputs`（包含 `tool_names` 和 `workspace_root`），然后直接构造 `WaitActivationRegistry`，不再调用 `build_fins_wait_adapter_registry`。
- **等价校验保留**: workspace root 校验仍在 `_fins_awaiting_registry_inputs_from_provider_configs` 内通过 `_fins_workspace_root_from_provider_config` + `_single_fins_workspace_root` 完成；重复工具名校验通过 `_require_distinct_fins_awaiting_tool_names` 显式执行。
- **activation registry 行为不变**: 仍注册一个 `FinsIngestionWaitActivationAdapter`（使用共享 runtime）在 `FINS_INGESTION_WAIT_ADAPTER_KEY` 下。与原行为完全等价。
- **adapter registry 路径同样受益**: `_fins_wait_adapter_registry_from_provider_configs` 也改用同一 helper，两个 registry 构造路径的 provider 筛选逻辑现在单一来源。
- **结论**: ✅ 修复正确、最小、无回归。

## S3-CR-F02 验证：`_DisabledProviderCallable.__call__` 已改为 fail-fast sentinel

- **修复前**: `__call__` 包含完整 `ToolsDiscoveryProviderOutput` 构造实现，但 `discover_from_bindings` 在 `spec.enabled is False` 时跳过调用，该实现永不可达。
- **修复后**: `__call__` 方法体为 `del spec` + `raise RuntimeError("disabled tools discovery provider callable must not be invoked")`。
- **disabled provider reporting/discovery 不变**: `_tool_discovery_bindings` 仍为 disabled provider 创建 binding（保持 `ToolsDiscoveryProviderBinding` 强类型形状），`discover_from_bindings` 仍跳过 disabled spec。
- **docstring 明确意图**: 类 docstring 说明该 callable 只用于保持类型形状，`__call__` docstring 说明调用时会立即失败。
- **结论**: ✅ 修复正确，sentinel 意图显式，无行为变更。

## S3-CR-F03 验证：Fins awaiting provider 收集逻辑已通过小 helper 复用

- **新增 helper**: `_FinsAwaitingRegistryInputs`（dataclass，含 `tool_names` 和 `workspace_root`）+ `_fins_awaiting_registry_inputs_from_provider_configs(provider_configs, available_tool_names)`。
- **helper 范围精确**: 只做 enabled provider 过滤、Fins awaiting 工具名识别、available tool name 过滤、workspace root 收集和 single-root 校验。未引入通用平台化抽象。
- **两个消费方**: `_fins_wait_adapter_registry_from_provider_configs` 和 `_fins_wait_activation_registry_from_provider_configs` 均调用此 helper，消除原有约 15 行重复遍历/过滤/校验逻辑。
- **排序行为一致**: helper 内部使用 `sorted(provider_configs, key=lambda item: item.provider_id)`，与原两处逻辑完全一致。
- **结论**: ✅ 修复正确，提取范围最小，未引入过度抽象。

## S3-CR-F04 验证：`_tooling_options_from_discovery` 的 `fins_awaiting_runtime` 参数已显式化

- **修复前**: 签名为 `fins_awaiting_runtime: FinsObservationRuntime | None = None`，默认值暗示参数可选。
- **修复后**: 签名为 `fins_awaiting_runtime: FinsObservationRuntime | None`，无默认值，调用方必须显式传参。
- **生产调用方已正确传递**: `_compose_options` 中 `request.discovered_tools.fins_awaiting_runtime` 显式传入（line 791）。
- **no-Fins-awaiting 行为不变**: 显式传 `None` 时，`_fins_wait_adapter_registry_from_provider_configs` 和 `_fins_wait_activation_registry_from_provider_configs` 均在 `_fins_awaiting_registry_inputs_from_provider_configs` 返回 `None` 后短路返回 `None`。
- **测试已同步更新**: 所有不涉及 Fins awaiting provider 的测试用例均已添加 `fins_awaiting_runtime=None`。
- **结论**: ✅ 修复正确，契约显式化，无行为变更。

## S3-CR-F05 验证：standalone activation builder 已有 runtime-sharing guardrail

- **新增 docstring**: `build_fins_wait_activation_registry` 的 docstring 现在明确说明："生产 Service assembly 中，awaiting tool callable、poll adapter 与 activation adapter 必须共享同一个 `FinsIngestionRuntime` 实例；本 standalone builder 只适用于由调用方自行保证 runtime 一致性的独立装配场景。"
- **Service assembly 路径已有本地注释**: `_fins_wait_activation_registry_from_provider_configs` 中 line 1800-1801 注释说明 "生产路径中 awaiting tool callable、poll adapter 与 activation adapter 必须共享同一个 runtime"。
- **未新增 broad builder API**: standalone builder 签名未变，未引入新的公共生命周期平台。
- **结论**: ✅ 修复正确，guardrail 最小且到位。

## 测试与验证复核

- **Service test**: `tests/service/test_host_assembly.py` — `52 passed, 3 warnings`。新增 `test_service_fins_awaiting_wiring_uses_shared_runtime_for_activation` 覆盖了 `discover_service_tools` → `_tooling_options_from_discovery` → `FinsDownloadToolCallable` → `ToolAwaitingOutcome` → `activate_accepted_wait` → observation 离开 PENDING 的完整链路，使用 `is` identity 断言验证共享 runtime。
- **focused Host/Fins tests**: `159 passed, 3 warnings`。覆盖了 ToolRuntime executor、Phase 7 waiting integration、Fins ingestion tools、Fins ingestion runtime。
- **pyright**: `0 errors, 0 warnings, 0 informations`。
- **git diff --check**: passed。
- **测试未被改弱**: 现有测试的断言未被删除或放松；新增测试是纯增量覆盖。
- **无新 scope creep**: 修复只涉及 S3-CR-F01 至 S3-CR-F05 的必要变更，未引入新功能、新模块或新 API。

## Open Questions

- 无。

## Residual Risk

1. **完整 open-host dispatch → worker activation 端到端路径未在本 slice 测试覆盖**: 现有 focused Service test 绕过了 `open_host` → dispatch commit → worker accept → `_activate_accepted_wait` 的完整 wiring。这由 controller 在 adjudication 中已记录，不影响本 slice 结论。
2. **Production poller scheduling / retry / fencing 仍属于 GitHub Issue #90**。
3. **External provider physical cancel / revoke 仍属于 GitHub Issue #92**。
4. **`_FinsAwaitingProviderCallable.__call__` 使用 `del spec`**: 该 callable 不消费传入的 spec，直接使用构造期绑定的 metadata 和 runtime。当前 ToolsDiscovery contract 不要求 callable 消费 spec，属远期风险。

## Conclusion

**pass**

S3-CR-F01 至 S3-CR-F05 全部修复正确、最小、无回归。丢弃的 `build_fins_wait_adapter_registry` 调用已移除，等价校验通过 helper 保留；disabled provider callable 已改为显式 fail-fast sentinel；provider 收集逻辑通过 `_FinsAwaitingRegistryInputs` helper 复用；`fins_awaiting_runtime` 参数已显式化；standalone builder 已有 runtime-sharing guardrail。测试 52 passed，focused Host/Fins 159 passed，pyright 0 errors。未引入新 scope creep、过度设计或测试改弱。无 blocker。
