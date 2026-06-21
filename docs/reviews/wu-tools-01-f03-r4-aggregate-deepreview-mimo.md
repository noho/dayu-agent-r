# WU-TOOLS-01-F03-R4 Aggregate Deepreview

## Scope

- Mode: current changes (aggregate deepreview)
- Branch: `phase/wu-tools-01-f03-r4`
- Base: `main`
- Output file: `docs/reviews/wu-tools-01-f03-r4-aggregate-deepreview-mimo.md`
- Reviewed scope: 当前分支相对 main 的完整 WU diff，覆盖 commits `fe212365`, `c785f218`, `3f7fd44a`, `4514f550`, `ee5f2e19`, `d8db0b49`, `21751ec9`；plan、slice implementation、code review、fix、final validation artifacts；设计真源和总控文档。
- Excluded scope: 不修改代码、不做 push/PR/merge、不处理 web smoke 日志捕获问题。
- Parallel review coverage: 无（单 reviewer 覆盖全 WU 范围）。

## Commands Run

```bash
git diff --stat main..HEAD
git diff main..HEAD -- dayu/config/tool_discovery.json
git diff main..HEAD -- dayu/runtime/tools_discovery.py dayu/runtime/config_loader.py
git diff main..HEAD -- dayu/service/host_assembly.py
git diff main..HEAD -- dayu/fins/tools/provider.py dayu/fins/tools/upload_provider.py dayu/fins/tools/upload_tools.py dayu/tools/doc_provider.py
git diff main..HEAD -- tests/service/test_host_assembly.py
git diff main..HEAD -- tests/fins/test_fins_ingestion_tools.py
git diff main..HEAD -- tests/runtime/test_scene_prepare.py
git diff main..HEAD -- tests/tools/test_doc_tools_provider.py
git diff main..HEAD -- tests/fins/test_fins_storage_provider.py
git diff main..HEAD -- dayu/config/prompts/manifests/*.json
git diff main..HEAD -- docs/host/design.md

source .venv/bin/activate
pytest tests/runtime/test_config_loader.py tests/runtime/test_tools_discovery.py tests/runtime/test_tools_discovery_digest.py -q  # 60 passed
pytest tests/service/test_host_assembly.py tests/runtime/test_smoke_host_public_multiturn_assembly.py -q  # 58 passed, 3 warnings
pytest tests/fins/test_fins_storage_provider.py tests/fins/test_fins_ingestion_tools.py -q  # 70 passed, 3 warnings
pytest tests/runtime/test_scene_prepare.py tests/tools/test_doc_tools_provider.py tests/tools/test_combined_tools_acceptance.py -q  # 73 passed, 3 warnings
pytest tests/runtime tests/service tests/fins tests/tools -q --ignore=tests/tools/web/test_smoke_web_ci.py  # 866 passed, 1 skipped, 3 warnings
pyright dayu tests utils  # 0 errors, 0 warnings, 0 informations

rg -n "include_read_tools|allowed_upload_roots" dayu tests README.md
rg -n "workspace_root.*null" dayu/config/tool_discovery.json tests
rg -n "\"allow_empty\"|allow_empty" dayu/config dayu/runtime dayu/service dayu/fins dayu/tools tests README.md
```

## Findings

未发现实质性问题。

### 审查维度证据摘要

**1. provider-level allow_empty 删除完整性**

- `dayu/config/tool_discovery.json`: 所有 provider 记录已删除 `allow_empty` 字段。
- `dayu/runtime/config_loader.py:587-603`: `ToolDiscoveryProviderConfig` 已删除 `allow_empty` 字段；`_parse_tool_discovery_provider` 的 required fields 和构造调用已同步删除。
- `dayu/runtime/tools_discovery.py:95-106`: `ToolsDiscoveryProviderSpec` 已删除 `allow_empty` 字段；`_validate_provider_output` 空工具检查已改为无条件拒绝（行 539-541）。
- `dayu/service/host_assembly.py:934`: `_tool_discovery_specs` 已删除 `allow_empty=provider_config.allow_empty` 映射。
- 剩余 `allow_empty` 命中：scene `tool_selection.allow_empty`（独立语义）、`ToolBundle._allow_empty`（runtime 内部 no-tool bundle 构造）、`dayu/fins/direct_events.py`（字符串字段校验语义）、test_config_loader.py（旧字段拒绝测试）。均与本 WU provider-level 语义无关。

**2. financial-read-tools 删除 include_read_tools 完整性**

- `dayu/fins/tools/provider.py`: `_CONFIG_INCLUDE_READ_TOOLS_FIELD` 和 `_parse_bool_default(...)` 已删除。`discover_tools(...)` 现在始终解析 limits、解析 absolute workspace root、创建 `DefaultFinsRuntime` 并返回九个 read tool definitions。
- 测试确认：`test_fins_read_provider_requires_workspace_root_when_enabled` 验证 enabled provider without workspace_root raises ValueError。
- `rg -n "include_read_tools" dayu tests README.md`: 无生产/测试/README 命中。

**3. packaged Fins workspace_root 默认 workspace/ 和 Service 解析**

- `dayu/config/tool_discovery.json`: 四个 Fins providers 的 `workspace_root` 已从 `null` 改为 `"workspace/"`。
- `dayu/service/host_assembly.py:960-1017`: `_effective_fins_workspace_root_config_value(...)` 正确处理：非字符串 → ValueError、空字符串/全空白 → ValueError、绝对路径 → resolve、相对路径 → 与 runtime workspace_root 合成绝对路径、相对路径但无 runtime workspace_root → ValueError。
- 测试覆盖：`test_fins_tool_discovery_spec_resolves_relative_workspace_root` 验证 `"workspace/"` 解析为 `/path/to/project/workspace`；`test_fins_tool_discovery_spec_rejects_non_string_workspace_root`、`test_fins_tool_discovery_spec_rejects_empty_workspace_root`、`test_fins_tool_discovery_spec_rejects_relative_workspace_root_without_runtime_root` 覆盖错误边界。
- Wait adapter 使用同一 effective provider config tuple：`test_discover_service_tools_carries_effective_fins_config_into_compose` 验证 download provider 的 effective config 包含解析后的绝对路径。
- 原始 config 未被修改：`test_fins_tool_discovery_spec_resolves_relative_workspace_root` 断言 `provider.config["workspace_root"] == "workspace/"`。

**4. Doc/Fins limits 迁移到 packaged tool_discovery.json**

- `dayu/config/tool_discovery.json`: `doc-tools.config.limits` 和 `financial-read-tools.config.limits` 已显式写入 OLD 默认值。
- 测试覆盖：`test_doc_provider_explicit_limits_shape_schema_and_truncate_specs` 验证显式 Doc limits 投影到参数 schema maximum 和 truncate spec；`test_doc_provider_partial_limits_fall_back_to_defaults` 验证缺失 limits 回退到 dataclass 默认值；`test_fins_provider_explicit_limits_shape_truncate_specs` 验证显式 Fins limits 投影到 truncate spec，且 `processor_cache_max_entries` 不出现在任何 ToolDefinition 的 truncate.limits 中。
- ConfigLoader 不解析 provider-specific limits：config_loader 测试验证 limits 对象原样保留。

**5. upload provider/tool 删除 allowed_upload_roots**

- `dayu/fins/tools/upload_provider.py`: `parse_allowed_upload_roots_config(...)`、`_CONFIG_ALLOWED_UPLOAD_ROOTS_FIELD` 和相关 imports 已删除。`discover_tools(...)` 现在始终解析 workspace_root 并注册 `start_fins_upload`。
- `dayu/fins/tools/upload_tools.py`: `FinsUploadToolCallable` 不再持有 `allowed_upload_roots`；`build_fins_upload_tool(...)` 不再接受 `allowed_upload_roots`；`_resolve_upload_path(...)` 已重命名为 `_resolve_upload_file_path(...)`，只检查 existing file、non-empty size，不再做 allowlist containment。
- LLM-facing schema 已更新：`files.description` 从 "Paths must be under the configured upload roots" 改为 "Each path must point to an existing non-empty regular file"。
- 测试覆盖：`test_upload_provider_registers_upload_tool_without_local_file_roots` 验证无 allowlist 时仍注册 upload tool；`test_upload_tool_missing_file_returns_failed_outcome_before_observation_start` 和 `test_upload_tool_directory_returns_failed_outcome_before_observation_start` 验证文件校验。
- `rg -n "allowed_upload_roots" dayu tests README.md`: 只剩 `tests/runtime/test_config_loader.py` 的负向断言。

**6. 默认非 upload scene 不通过 broad fins tag 误选 start_fins_upload**

- 所有默认 manifest (`confirm`, `decision`, `fix`, `infer`, `interactive`, `prompt`, `regenerate`, `repair`, `wechat`, `write`) 已将 broad `"fins"` tag 替换为显式 Fins read/download/preprocess 工具名列表。`"ingestion"` tag 已从 interactive/prompt/wechat 中移除。
- 测试覆盖：`test_default_non_upload_scenes_do_not_select_upload_tool` 验证所有默认非 upload scene 不选择 `start_fins_upload`，且包含预期的 Fins read/download/preprocess 工具。
- `rg -n '"fins"|fins-upload|"ingestion"|start_fins_upload' dayu/config/prompts/manifests`: 无 broad tag 命中。

**7. Doc provider fail-fast 行为**

- `dayu/tools/doc_provider.py`: enabled provider + empty/missing `allowed_paths` 现在 raise `ValueError("doc provider config.allowed_paths must contain at least one path when doc-tools is enabled")`，而不是返回空 definitions。
- Packaged `doc-tools.enabled=false` 确保默认不触发 fail-fast；workspace overlay 启用 doc-tools 但未配置 paths 时会立即失败。
- 测试覆盖：`test_provider_enabled_without_allowed_paths_fails_fast` 参数化覆盖 `{}` 和 `{"limits": {}, "allowed_paths": []}`。

**8. README/design/tests/control doc 语义一致**

- `docs/host/design.md`: 已更新 ToolsDiscovery provider empty output 描述为"启用 provider 返回空工具集合是配置错误"；已删除 `allow_empty` 字段引用；已说明 scene `tool_selection.allow_empty` 是独立语义。
- `dayu/config/README.md`: 已更新 provider 字段表（无 `allow_empty`）、Fins `workspace_root: "workspace/"` 相对默认值和 Service 解析、Doc/Fins limits 默认值、`doc-tools.enabled=false`、无 `include_read_tools`/`allowed_upload_roots`、scene manifest 不再使用 broad Fins tag。
- `dayu/fins/README.md`: 已删除 `include_read_tools` 和 allowlist 描述；已说明四个 Fins providers 需要 effective absolute `workspace_root`；已说明 upload local source file authorization 不由 provider 管。
- `tests/README.md`: 已更新测试覆盖描述。

**9. 架构边界保持**

- `dayu.runtime` (ConfigLoader, ToolsDiscovery) 不 import `dayu.engine` / `dayu.host` / `dayu.service` / `dayu.fins`。
- Service / composition root 是唯一负责相对 workspace 路径解析的层；Fins provider 只接收 absolute path。
- Host / Engine public contract 未变更。
- Fins repository 写入边界未削弱：upload 工具只接受本地文件路径作为 source input，写入目标仍由 `FinsIngestionRuntime` / repository 协议控制。

## Web Smoke Residual Judgment

`tests/tools/web/test_smoke_web_ci.py::test_default_run_executes_local_html_pdf_and_browser_cases` 当前断言 `captured.out` 包含 `web smoke execution started`，但日志进入 pytest 的 `Captured log call` 而非 stdout。

**判断**：该失败非本 WU 引入。本 WU 未修改 `tests/tools/web/test_smoke_web_ci.py` 或 `utils/smoke_web_ci.py`；该问题在单独运行 `tests/tools/web` 时复现，属于 web smoke 日志捕获 / 测试期望边界问题。已分类为 `WU-TOOLS-01-F03-R4-WEB-SMOKE-R1`，owner 为 web smoke / CI owner，deferred-with-owner。

## Open Questions

无。

## Residual Risk

| ID | 状态 | Owner / Destination | 说明 |
|---|---|---|---|
| WU-TOOLS-01-F03-R4-WEB-SMOKE-R1 | deferred-with-owner | Web smoke / CI owner | `test_default_run_executes_local_html_pdf_and_browser_cases` stdout 日志断言失败，非本 WU 引入。 |
| Upload local file read authorization | deferred-with-owner | Future Host / policy design | 本 WU 删除 provider-local allowlist 是因为其不是系统权限真源。未来 Host / policy 设计应决定本地文件读取是否需要授权、审计或 sandbox。 |
| Provider dataclass defaults drift | low risk | Tests assert packaged defaults | Provider dataclass 默认值作为代码 fallback 保留；测试已断言 packaged defaults 以降低 drift 风险。 |

## Completion Status

Aggregate deepreview 完成。WU-TOOLS-01-F03-R4 的 Tools Discovery spec 语义清理实现完整、测试充分、架构边界未倒置、文档语义一致。未发现 blocking correctness / architecture / test gap。

### Verdict

**pass**
