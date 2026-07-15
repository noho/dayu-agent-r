# Code Review — WU-SEMANTIC-OWNERSHIP-01 / R04-S1

## Scope

- Mode: current changes
- Branch: `phaseflow/host-issues-control`
- Base: `a4ffd7641c8f114e987972d77572c2c2b4a8202f`
- Output file: `docs/reviews/wu-semantic-ownership-01-r04-s1-code-review-mimo.md`
- Included scope: accepted plan §4.1 allowlist 中全部 11 个生产/配置文件、11 个测试/smoke 文件、5 个 README 文件、Controller validation F01 修复授权的 4 个派生 consumer 文件，以及所有 review artifact。
- Excluded scope: Engine、Host public API/open_host、prompt assets、execution profiles、callback transport、R05 状态机、Issue 175/142/151/177/178、design/control 文档、allowlist 外生产文件。
- Parallel review coverage: 无 subagent；主 reviewer 直接逐文件走读。

## Findings

未发现实质性问题。

以下详细记录 review 路径与验证结论。

## Review Path

### 1. ConfigLoader typed boundary 验证

**审查目标**：`_parse_wait_poller_runtime_policy` 对 bool/数值/NaN/Infinity/exact-shape 的失败边界。

**验证结论**：

- `_require_bool_field` (config_loader.py:2615) 正确使用 `isinstance(value, bool)` 拒绝 int 1/0。
- `_require_int_field` (config_loader.py:2740) 先检查 `isinstance(value, bool)` 再检查 `isinstance(value, int)`，正确拒绝 bool 冒充 int。
- `_require_float_field` (config_loader.py:2631) 先检查 bool、再检查 `(int, float)`、再检查 `is_finite_number`。NaN 和 Infinity 被 `math.isfinite()` 正确拒绝。
- `_require_positive_float_field` (config_loader.py:2651) 在 `_require_float_field` 基础上叠加 `is_positive_finite_number` 检查，零值被 `value > 0` 正确拒绝。
- `_require_positive_int_field` (config_loader.py:2704) 在 `_require_int_field` 基础上叠加 `value <= 0` 检查。
- `_require_exact_fields` (config_loader.py:2429) 校验 allowed 字段集合，缺失和多余字段均 fail closed。
- `is_finite_number` (numeric.py:13) 正确处理 bool 返回 `False`、OverflowError 返回 `False`。
- `is_positive_finite_number` (numeric.py:29) 组合 `is_finite_number` 与 `value > 0`。

测试覆盖：`test_host_runtime_wait_poller_policy_fields_are_all_required` 覆盖 12 字段缺失；`test_host_runtime_wait_poller_policy_rejects_unknown_field` 覆盖多余字段；`test_host_runtime_wait_poller_policy_rejects_bool_numeric_substitution` 覆盖 4 个 bool 混淆 case（`claim_batch_size=True`、`max_outstanding_adapter_calls=False`、`poll_interval_seconds=True`、`enabled=1`）；`test_host_runtime_wait_poller_policy_rejects_non_positive_values` 覆盖 11 个数值字段 × 2 个值（0、-1）。

**无 finding**。ConfigLoader 的类型/数值/边界校验链完整且正确。

### 2. Provider mode owner 验证

**审查目标**：`AwaitingResolutionMode` enum/parser 是否严格闭集、无默认、无 fallback。

**验证结论**：

- `_ingestion_tool_helpers.py:27` 定义 `AwaitingResolutionMode(StrEnum)` 为 `poll/callback/manual` 三成员闭集。
- `parse_awaiting_resolution_mode` (同文件:36) 依次检查字段存在性 (`in config`)、类型 (`isinstance(value, str)`)、闭集 (`AwaitingResolutionMode(value)`)。缺失、null、非字符串、bool、空串、大小写变体（`"POLL"`）均失败。
- 三个 Fins 直接 provider (download/preprocess/upload) 在构造 runtime 前调用同一 parser。
- Service `_fins_awaiting_provider_metadata_from_configs` (host_assembly.py:1186) 对所有 provider configs（包括 disabled）执行 owner parse，disabled 合法 mode 不进入 active collection，disabled 非法 mode 仍然 fail fast。
- `_is_recognized_non_awaiting_provider_config` (host_assembly.py:2154) 只按字段存在性拒绝 Fins read/Web provider 的 `awaiting_resolution_mode` 误用，不读取 raw value。
- 未知第三方 provider 的同名字段不被解析，不发明新语义。

测试覆盖：`test_awaiting_resolution_mode_parser_accepts_closed_typed_modes` 覆盖三模式；`test_awaiting_resolution_mode_parser_rejects_missing_or_illegal_values` 覆盖 8 种非法输入（空 dict、null、int、bool、空串、大小写、空白、未知值）；`test_each_fins_awaiting_provider_validates_mode_before_runtime_creation` 覆盖三个 provider 的直接 discovery；`test_disabled_fins_provider_parses_legal_mode_before_active_filter` 和 `test_disabled_fins_provider_illegal_mode_fails_before_active_filter` 覆盖 disabled 边界；`test_recognized_non_awaiting_provider_rejects_mode_field_presence_only` 和 `test_unknown_third_party_provider_mode_field_remains_opaque` 覆盖 misuse/unknown 边界。

**无 finding**。Provider mode owner 完整且正确。

### 3. Host policy 无默认/无 fallback 验证

**审查目标**：`WaitPollerRuntimePolicy`、`WaitPoller`、`WaitPollerSupervisor` 是否删除了全部 deployment defaults。

**验证结论**：

- `WaitPollerRuntimePolicy` (wait_adapter.py:415) 12 个字段全部无默认值，`__post_init__` 增加了 `claim_batch_size` 的 bool 检查。
- `WaitPoller.__init__` (wait_adapter.py:931) `policy` 参数改为 required keyword（`WaitPollerRuntimePolicy`，无 `| None`），删除了 `resolved_policy = policy if policy is not None else WaitPollerRuntimePolicy()` fallback。
- `WaitPollerSupervisor.__init__` (wait_adapter.py:1608) 同样删除了 `| None` 默认和无参 fallback。
- 10 个旧部署默认常量（`_DEFAULT_CLAIM_BATCH_SIZE`、`_POLL_CLAIM_TTL_SECONDS` 等）已全部删除。

Source scan 确认：旧常量名、无参 `WaitPollerRuntimePolicy()` 和 `| None` 默认零命中。

**无 finding**。Host policy 无默认/无 fallback 完整落地。

### 4. Service typed composition 验证

**审查目标**：`_compose_options` 是否只消费 typed metadata、scene 是否不参与 policy 决策。

**验证结论**：

- `_compose_options` (host_assembly.py:781) 先从 `request.discovered_tools._fins_awaiting_providers` 取得 typed metadata，检查 callback 模式、构造 tooling_options、构造 wait_poller_policy，最后写入 `OpenHostOptions`。
- `_wait_poller_policy_for_composition` (host_assembly.py:875) 只检查 active metadata 中是否有 `POLL` 模式，有则一对一构造 Host policy，无则返回 `None`。
- `_wait_poller_runtime_policy_from_config` (host_assembly.py:920) 逐字段一对一投影，不加默认、不改值。
- `ServiceAssemblyOverrides.wait_poller_policy` 已删除。
- `with_entrypoint_wait_poller_policy`、`_scene_selects_fins_awaiting_tools` 已删除。
- `entrypoint_runtime.py` 不再调用 `with_entrypoint_wait_poller_policy`。

测试覆盖：`test_scene_tool_selection_does_not_own_wait_poller_composition` 覆盖 all/select/none 三种 scene 选择，证明同一 provider/runtime inputs 得到相同 policy；`test_compose_open_host_options_projects_complete_config_owned_wait_policy` 覆盖 12 字段一对一投影；`test_manual_mode_composes_binding_without_background_poller`、`test_poll_and_manual_modes_partition_runtime_composition`、`test_active_poll_with_disabled_runtime_policy_stays_disabled`、`test_callback_mode_fails_closed_before_open_host`、`test_no_provider_and_disabled_provider_do_not_compose_poller`、`test_enabled_poll_policy_with_missing_registry_fails_before_open_host` 覆盖完整 negative matrix。

**无 finding**。Service typed composition 完整且正确。

### 5. Callback pre-open fail-closed 验证

**审查目标**：任意 active callback 是否在 `open_host` 前无条件失败。

**验证结论**：

- `_compose_options` (host_assembly.py:782) 检查 `any(metadata.mode is AwaitingResolutionMode.CALLBACK for metadata in fins_awaiting_providers)`，为 True 时 raise `ValueError`。
- 该检查在 `tooling_options` 构造和 `wait_poller_policy` 构造之前执行，确保 callback 不会进入任何后续路径。
- 不降级为 poll 或 manual。
- 不新增 marker、protocol、facade 或 callable 绕过入口。

测试覆盖：`test_callback_mode_fails_closed_before_open_host` 直接验证。

**无 finding**。Callback pre-open fail-closed 完整且正确。

### 6. ServiceDiscoveredTools required construction invariant (F01 修复)

**审查目标**：F01 是否真正关闭、`_fins_awaiting_providers` 是否成为 required 构造不变量。

**验证结论**：

- `ServiceDiscoveredTools` (host_assembly.py:268) `fins_awaiting_runtime` 和 `_fins_awaiting_providers` 均无默认值。
- 全仓 Python scan 确认：`ServiceDiscoveredTools(...)` 直接构造只存在于 `discover_service_tools` (host_assembly.py:510)。
- 四个 authorized derived consumers (`test_combined_tools_acceptance.py`、`smoke_host_public_conversation_memory.py`、`smoke_host_public_conversation_memory_scenarios.py`、`smoke_host_public_multiturn.py`) 均使用 `dataclasses.replace(...)`。
- `test_replacing_discovered_bundle_preserves_host_wait_composition` (test_host_assembly.py:343) 在真实 packaged config discovery 上替换 tool bundle，比较原始与派生 discovery 的 Host policy、三个 Fins binding、activation adapter 和 poll adapter。
- Controller re-validation 已确认 pyright 对遗漏构造的 `reportCallIssue` 精确报错。

**无 finding**。F01 已在 owner boundary 正确关闭。

### 7. Typed metadata 构造/派生传播验证

**审查目标**：`_FinsAwaitingProviderMetadata` 是否保留 owner fact、是否在派生路径中丢失。

**验证结论**：

- `_FinsAwaitingProviderMetadata` (host_assembly.py:389) 包含 `spec_id`、`tool_name`、`provider_id`、`version_ref`、`source_id`、`workspace_root`、`mode`，全部 required。
- `_fins_awaiting_provider_metadata` (host_assembly.py:1347) 按 tool name 路由到具体 provider 构造，所有字段从 owner inputs 产生。
- `_fins_awaiting_provider_metadata_from_configs` (host_assembly.py:1186) 一次遍历全部 configs，先 parse mode、再按 enabled 过滤、再构造 metadata。
- `_active_fins_awaiting_provider_metadata` (host_assembly.py:1252) 按 `available_tool_names` 过滤实际可用工具。
- `_tool_discovery_bindings` (host_assembly.py:1279) 从 metadata 取得已解析的 provider 元数据，不重读 raw config。
- `_tooling_options_from_discovery` (host_assembly.py:1969) 改为接收 `fins_awaiting_providers` 而非 `provider_configs`。
- `_fins_wait_adapter_registry_from_provider_metadata`、`_fins_wait_activation_registry_from_provider_metadata`、`_fins_wait_poll_adapter_registry_from_provider_metadata` 均从 typed metadata 构造 registry，不重读 raw config。
- `_fins_awaiting_registry_inputs_from_provider_configs` 已删除。
- `_binding_for_tool_name` (fins_wait_adapter.py:339) 接收 `AwaitingResolutionMode` 并映射为 `WaitResumePolicy`。

**无 finding**。Typed metadata 构造/传播链完整。

### 8. `_operation_kind_from_tool_name` 结构映射保留

**审查目标**：observation handle 恢复所需的 stable `tool name -> FinsOperationKind` 映射是否被误作 resolution policy。

**验证结论**：

- `_operation_kind_from_tool_name` (fins_wait_adapter.py) 保持不变，返回 `FinsOperationKind.DOWNLOAD/PREPROCESS/UPLOAD`。
- `_binding_for_tool_name` 同时接收 `tool_name` 和 `mode`，使用 `_operation_kind_from_tool_name` 获取结构映射、使用 `_wait_resume_policy_from_mode` 获取 policy 映射。
- 测试 `test_fins_operation_kind_structural_mapping_remains_stable` 直接断言三个工具名到 operation kind 的映射。

**无 finding**。结构映射与 policy 映射正确分离。

### 9. LLM-facing 文本审查

**审查目标**：tool schema、prompt、Host/Service projection 是否符合 AGENTS.md LLM-facing 文本约束。

**验证结论**：

- 本次实现不修改任何 prompt assets（source scan 确认零命中）。
- 不修改 tool schema 的 name/description/参数说明。
- 不修改 Host/Engine/Tool 的 LLM-facing projection。
- `_fins_awaiting_provider_metadata` 中的 provider id/version/source 只用于 Host 内部 binding 和 registry，不进入 LLM-facing material。
- `awaiting_resolution_mode` 只存在于 provider config、Fins parser 和 Service composition，不进入 prompt/execution profile（source scan 确认零命中）。

**无 finding**。LLM-facing 文本约束未被违反。

### 10. 分层/依赖审查

**审查目标**：是否违反 `UI -> Service -> Host -> Engine` 分层、`dayu.runtime` 是否反向依赖。

**验证结论**：

- `dayu.runtime.config_loader` 新增 `WaitPollerRuntimePolicyConfig`，只依赖标准库和 `dayu.runtime.numeric`，不 import Host/Fins/Service/Engine。
- `dayu.fins.tools._ingestion_tool_helpers` 新增 `AwaitingResolutionMode` 和 `parse_awaiting_resolution_mode`，只依赖标准库和 `dayu.contracts.json_value`。
- `dayu.service.host_assembly` import `dayu.fins.tools._ingestion_tool_helpers` 和 `dayu.runtime.config_loader.WaitPollerRuntimePolicyConfig`，符合 `Service -> Fins/Host/Runtime` 方向。
- `dayu.service.fins_wait_adapter` import `dayu.fins.tools._ingestion_tool_helpers.AwaitingResolutionMode`，符合 `Service -> Fins` 方向。
- `dayu.host.wait_adapter` 无新增 import。
- Anchored runtime reverse-import scan 确认零命中。

**无 finding**。分层/依赖约束未被违反。

### 11. 配置严格性审查

**审查目标**：`host_runtime.json` 的 12 字段 required snapshot 是否完整、packaged values 是否正确。

**验证结论**：

- `host_runtime.json` 新增 `wait_poller_policy` block，包含 12 个字段，值为 `true, 1, 60, 100, 30, 2, 300, 1, 5, 30, 5, 8`，与计划 §2 一致。
- `tool_discovery.json` 三个 Fins awaiting provider 均新增 `"awaiting_resolution_mode": "poll"`。
- ConfigLoader `_require_exact_fields` 确保无多余字段、无缺失字段。
- 测试 `test_default_runtime_config_files_load_as_typed_views` 断言所有 12 个字段的精确值。

**无 finding**。配置严格性完整。

### 12. README 一致性审查

**审查目标**：5 个 README 更新是否与实现一致、是否属于各自职责范围。

**验证结论**：

- `dayu/config/README.md`：更新完整 12 字段描述、数值/bool 边界、packaged snapshot 与 Fins mode 配置契约。属于 ConfigLoader 读者职责。
- `dayu/host/README.md`：更新 config-owned 显式 policy 与 Host 无 deployment defaults。属于 Host 读者职责。
- `dayu/service/README.md`：更新 Service 私有并行 typed projection、typed composition 与 scene independence。属于 Service 读者职责。
- `dayu/fins/README.md`：更新 provider-owned 唯一 parser、三模式及 registry 行为。属于 Fins 读者职责。
- `tests/README.md`：更新 ConfigLoader/Fins/Service/Host 矩阵和真实 smoke 边界、derived discovery composition invariant。属于 tests 读者职责。
- 根 README 和 `dayu/README.md` 不触发，正确。

**无 finding**。README 更新一致且在各自职责范围内。

### 13. 测试有效性审查

**审查目标**：tests 是否覆盖关键行为、failure paths、boundary conditions。

**验证结论**：

- `test_fins_ingestion_tools.py`：新增 3 个 owner test（parser 正向、parser 反向 8 case、三个 provider 直接 discovery）。修改既有测试适配 `awaiting_resolution_mode` 字段。
- `test_config_loader.py`：新增 5 个 test（block required、12 字段缺失、未知字段、bool 混淆 4 case、非正数 22 case）。
- `test_host_assembly.py`：删除 3 个旧 scene/override test，新增 15+ test 覆盖 composition matrix、typed metadata、scene independence、derived discovery preservation。
- `test_fins_wait_adapter.py`：修改 binding test 适配 typed mode，新增 `_operation_kind_from_tool_name` 稳定性 test。
- `test_wait_adapter_polling.py`、`test_wait_observation_runner.py`、`test_wait_poller_runtime.py`、`test_open_host_runtime.py`：适配 required policy 构造。
- `test_combined_tools_acceptance.py`：改为 `dataclasses.replace`。
- Smoke files：适配 required constructor。
- 逐文件 coverage 全部 `>=80%`。
- 509 passed, 3 warnings, pyright 0 errors。

**无 finding**。测试覆盖完整且有效。

### 14. Security retention 审查

**审查目标**：现有安全机制（allowed_paths、Web 防御、containment/symlink、DNS/peer、resource budget、atomic write、process fencing）是否被删除或绕过。

**验证结论**：

- Deferred-scope added-line scan 确认：authorization、permission、process isolation、observation timeout、lost outcome 零新增。
- Source scan 确认：旧 entrypoint/scene helper、旧 Host deployment constants、prompt/execution profile 污染零命中。
- 不修改 Host public API/open_host、Engine、callback transport。
- 不删除任何现有安全机制。

**无 finding**。安全机制完整保留。

### 15. prior F01 关闭验证

**审查目标**：Controller validation finding R04-S1-CV-F01 是否真正关闭。

**验证结论**：

- `ServiceDiscoveredTools.fins_awaiting_runtime` 和 `_fins_awaiting_providers` 均无默认值。
- 四个 authorized consumers 均使用 `dataclasses.replace(...)`。
- Owner-level regression `test_replacing_discovered_bundle_preserves_host_wait_composition` 通过。
- Full pyright clean。
- Controller re-validation verdict: PASS。

**F01 已关闭**。

## Open Questions

无。

## Residual Risk

| residual / uncovered area | classification / owner |
|---|---|
| callback 正向 transport 尚不存在 | 既有 WU-WAIT-01 / #89 owner；R04 正确行为是 pre-open fail-closed |
| deterministic smoke 不访问真实外部 LLM/网络 | 本任务显式禁止；packaged local smoke 已覆盖 composition 路径 |
| Host 重启后跨进程 observation 恢复与 timeout/LOST 行为 | 后续既有 owner；R04 未改变状态机 |
| ConfigLoader float 字段缺少 NaN/Infinity 显式测试 | 实现正确拒绝（`math.isfinite`），但无显式测试覆盖；不影响生产正确性 |
| `_fins_awaiting_metadata_by_spec_id` 在 `_fins_awaiting_provider_metadata_from_configs` 中被调用仅为 validation，返回值丢弃；同一 dict 在 `_tool_discovery_bindings` 和各 registry builder 中重复构造 | 纯函数 idempotent，不影响正确性；轻微性能冗余 |

## Verdict

**PASS** — 未发现实质性问题。R04-S1 的 provider-owned typed mode、config-owned 完整 policy snapshot、Host 显式执行 policy、Service typed composition、callback pre-open fail-closed、ServiceDiscoveredTools required invariant (F01)、测试、README、scans 与 smoke 均已在同一 implementation pass 中正确完成。所有 residual 均有明确 owner。
