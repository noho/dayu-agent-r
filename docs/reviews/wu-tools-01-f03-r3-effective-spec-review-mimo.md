# WU-TOOLS-01-F03-R3 Effective Spec Assembly Review

## Review Scope

审查 `wu-tools-01-f03` 分支当前未提交改动中与 effective spec assembly 相关的变更。重点：

1. `dayu/service/host_assembly.py` 中 `_effective_tool_provider_config` / `_effective_tool_provider_configs` / `_is_fins_workspace_bound_provider_config` 的正确性。
2. `discover_service_tools(config, workspace_root=...)` 与 `_tool_discovery_specs` 使用的 effective config 是否和 `compose_open_host_options` 中 wait adapter registry 使用的 effective config 一致。
3. `tests/service/test_host_assembly.py`、`utils/smoke_web_ci.py`、README、`docs/host/issues-implementation-control.md` 的一致性。

## 变更摘要

### `dayu/service/host_assembly.py`

- `discover_service_tools` 新增 `workspace_root` keyword-only 参数。
- `_tool_discovery_specs` 新增 `workspace_root` 参数，对每个 provider 调用 `_effective_tool_provider_config` 生成 effective config 后传入 `ToolsDiscoveryProviderSpec.config`。
- 新增 `_effective_tool_provider_config(provider_config, workspace_root=...)`：判断 provider 是否为 Fins workspace-bound；若是且 raw config 中 `workspace_root` 为 `None` 且 runtime `workspace_root` 非 `None`，则注入 resolved absolute workspace root。
- 新增 `_effective_tool_provider_configs(provider_configs, workspace_root=...)`：对每个 provider 调用同一 helper，返回 `tuple[ToolDiscoveryProviderConfig, ...]`。
- 新增 `_is_fins_workspace_bound_provider_config(provider_config)`：三重匹配（provider_id / import_path / source_id）判断是否为 Fins workspace-bound provider。
- `_compose_options` 中 `_tooling_options_from_discovery` 的 `provider_configs` 参数从原始 `request.config.tool_discovery.providers.values()` 改为 `_effective_tool_provider_configs(...)` 输出。
- 新增 `_FINS_READ_PROVIDER_IDS`、`_FINS_READ_IMPORT_PATHS`、`_FINS_READ_SOURCE_IDS` 常量。

### `dayu/config/tool_discovery.json`

- `web-tools` 从 `enabled: false` 改为 `enabled: true`。
- `web-tools.config` 新增 `provider: "auto"`、`fetch_truncate_chars: 80000`、`playwright_channel: "chrome"`、`playwright_storage_state_dir: "workspace/.dayu/web_tools_storage_states"`。

### `tests/service/test_host_assembly.py`

- 4 处 `discover_service_tools(config)` 改为 `discover_service_tools(config, workspace_root=tmp_path)`。
- 新增 4 个测试：`test_web_tool_discovery_config_survives_service_mapping`、`test_fins_tool_discovery_spec_injects_runtime_workspace_root`、`test_fins_tool_discovery_spec_preserves_explicit_workspace_root`、`test_config_loader_and_service_discover_web_tools_with_overlay_config`。

### `utils/smoke_web_ci.py`

- 新增 `_run_local_assembly_config_case`：走生产式 `ConfigLoader.load() -> discover_service_tools() -> ToolDefinition.callable`，验证 Web overlay config 与 `truncate_max_chars`。
- 新增 `_run_search_provider_cases`：覆盖 `auto` / `tavily` / `serper` / `duckduckgo` 四个 search provider diagnostic-only cases。
- `SmokeSummary` 新增 `search_cases` 字段，`_summary_from_cases` 将 search_cases 纳入 exit code hard gate。

### README / docs

- `dayu/config/README.md`：更新 web-tools 默认 `enabled=true`，新增 `playwright_storage_state_dir` 说明，更新 Fins workspace root 注入说明。
- `dayu/service/README.md`：更新 `discover_service_tools` 签名，新增 provider effective spec 职责说明。
- `tests/README.md`：更新 web tools provider 测试描述、Web smoke 描述。
- `docs/host/issues-implementation-control.md`：新增 R3 复核结论、follow-up 方案、plan/implementation/code review gate 记录。

## Findings

### F1 [LOW] 集成测试缺口：discover_service_tools 与 wait adapter registry 使用同一 effective config 未被直接验证

**位置**: `tests/service/test_host_assembly.py`

**描述**: `_tool_discovery_specs`（用于 `discover_service_tools`）和 `_effective_tool_provider_configs`（用于 `_tooling_options_from_discovery` 中的 wait adapter registry）都调用 `_effective_tool_provider_config`。两个路径使用同一 helper，逻辑一致。但现有测试只分别验证了：

- `_tool_discovery_specs` 的 workspace_root 注入（`test_fins_tool_discovery_spec_injects_runtime_workspace_root`）
- wait adapter registry 的绑定（`test_tooling_options_binds_fins_wait_adapter_registry_for_enabled_awaiting_providers`）

没有一个集成测试走完整 `discover_service_tools` -> `compose_open_host_options` 路径，使用启用的 Fins provider，并验证 wait adapter registry 收到的 effective config 中 `workspace_root` 和 discovery 阶段一致。

**影响**: 当前代码正确（同一 helper），但如果未来有人修改 `_tooling_options_from_discovery` 直接使用原始 config 而非 effective config，现有测试不会捕获。

**建议**: 考虑增加一个端到端测试，使用 Fins provider overlay，验证 `compose_open_host_options` 输出的 `tooling_options.wait_adapter_registry` 能正确 resolve binding。

### F2 [LOW] `_is_fins_workspace_bound_provider_config` 三重匹配的维护风险

**位置**: `dayu/service/host_assembly.py:870-886`

**描述**: 函数通过 `provider_id in frozenset` / `import_path in frozenset` / `source_id in frozenset` 三重匹配判断是否为 Fins workspace-bound provider。这种方式覆盖面广（允许用户用自定义 provider_id 但保留标准 import_path），但常量集合（`_FINS_READ_*`、`_FINS_DOWNLOAD_*` 等）需要和 `tool_discovery.json` 及 Fins provider 实现保持同步。

新增 `_FINS_READ_*` 常量正确补齐了 read provider 的识别。当前所有 Fins provider 的三组标识符都已在常量中声明。

**影响**: 低。如果新增 Fins provider 类型但忘记更新常量，workspace_root 不会被注入，provider 会在运行时因缺少 workspace_root 而报错（有 fail-fast），不会静默出错。

**建议**: 现有防御足够。如果后续 Fins provider 增长到 5+ 个，可考虑从 provider 注册表自动生成常量集合。

### F3 [INFO] tool_discovery.json web-tools 默认启用是行为变更

**位置**: `dayu/config/tool_discovery.json`

**描述**: `web-tools` 从 `enabled: false` 改为 `enabled: true`。这意味着不使用 workspace overlay 的默认配置现在会自动发现 `search_web` 和 `fetch_web_page`。

`docs/host/issues-implementation-control.md` 的 R3 复核结论已记录此变更意图。`dayu/config/README.md` 已更新为 `enabled=true`。

**影响**: 不使用 workspace overlay 的用户现在会自动获得 Web tools。对于纯财报分析场景，这增加了不必要的工具暴露面。但 `allow_empty=true` 保证即使 Web provider 初始化失败也不会阻断 scene 装配。

**建议**: 无需修改，但应在 PR description 中明确此行为变更。

### F4 [INFO] Smoke summary exit code 将 search_cases 纳入 hard gate

**位置**: `utils/smoke_web_ci.py` `_summary_from_cases`

**描述**: `hard_gate_cases = tuple(local_cases) + tuple(search_cases)`。search provider diagnostic-only cases 的 exit code 现在会影响 smoke 整体 exit code。

如果 search provider 的 `_run_single_search_provider_case` 在 ConfigLoader 或 discover_tools 阶段失败（`_EXIT_SCHEMA_OR_INFRA_FAILURE`），smoke 整体会返回非零 exit code。这是正确的行为：配置装配失败是 local blocker，不是外部 provider 波动。

外部 provider 的 auth/quota/network 失败被映射为 `_STATUS_DIAGNOSTIC_ONLY`，exit code 为 `_EXIT_OK`，不影响 smoke 整体结果。

**影响**: 无负面影响。设计意图正确。

### F5 [INFO] README 一致性确认

- `dayu/config/README.md`：已更新 web-tools 默认值、Fins workspace root 注入语义、Doc provider fail closed 措辞。
- `dayu/service/README.md`：已更新 `discover_service_tools` 签名和 effective spec 职责说明。
- `tests/README.md`：已更新 web tools provider 测试和 Web smoke 描述。
- `docs/host/issues-implementation-control.md`：R3 复核、plan、implementation、code review、fix、re-review gate 记录完整。

所有 README 变更与代码变更一致，无遗漏。

### F6 [INFO] 类型安全确认

- `_effective_tool_provider_config` 返回 `Mapping[str, JsonValue]`。当需要注入 workspace_root 时返回 `dict[str, JsonValue]`（mutable），否则返回原始 `provider_config.config`（可能是 frozen mapping）。调用方只读取返回值，不依赖 mutability，类型安全。
- `_effective_tool_provider_configs` 使用 `dataclasses.replace` 创建新 `ToolDiscoveryProviderConfig`，正确保持 frozen dataclass 语义。
- `smoke_web_ci.py` 中 `_discover_tools_by_name` 返回 `Mapping[str, ToolDefinition]`，与 smoke test 的 type annotation 一致。

## 结论

**Pass**。无 correctness blocking findings。

Effective config 的两条路径（discovery 和 wait adapter registry）使用同一 `_effective_tool_provider_config` helper，逻辑一致。F1/F2 是低优先级的防御性建议，不阻塞当前 PR。README 和 docs 与代码变更一致。类型安全无新增问题。
