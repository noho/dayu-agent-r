# WU-TOOLS-01-F03-R4 Tools Discovery Spec Semantics Cleanup Plan

## Goal / Motivation / Success Signal

目标：清理 Tools Discovery provider spec 的混杂语义，使 `tool_discovery.json`、`ConfigLoader` typed view、`ToolsDiscovery`、Service effective assembly、Fins / Doc providers 与文档说明回到同一套职责边界。

动机判断：问题真实存在，且不是单个字段命名问题。直接证据显示当前配置同时存在 provider-level `allow_empty`、Fins read provider 内部 `include_read_tools`、Fins workspace `null` 默认、upload provider 本地文件 allowlist、以及 packaged limits 空 object。这些字段让“provider 是否启用”“provider 返回空工具是否允许”“workspace 路径由谁解析”“本地文件权限由谁治理”“默认 limits 真源在哪里”混在一起。按设计真源，`ConfigLoader` 只原样读取 typed config view，`ToolsDiscovery` 只聚合显式 provider callable，Service / composition root 负责把配置映射成 effective typed input，Host / Engine 不读取配置、不发现工具、不理解 Fins 业务规则。

成功信号：

- `dayu/config/tool_discovery.json` 不再包含 provider-level `allow_empty`、`financial-read-tools.config.include_read_tools` 或 `financial-upload-tools.config.allowed_upload_roots`。
- Fins packaged `workspace_root` 默认值从 `null` 改为显式 `"workspace/"`；ConfigLoader 保留原始字符串，Service effective assembly 将相对路径解析成绝对路径后再传给 Fins providers。
- `doc-tools.config.limits` 与 `financial-read-tools.config.limits` 显式承载 OLD 默认值；provider dataclass 默认值只作为代码 fallback / 测试构造便利。
- `ToolsDiscoveryProviderSpec` 不再有 `allow_empty`；启用 provider 返回空工具统一 fail fast。真正可空的业务 provider 必须由 provider 自身业务配置决定不暴露工具，或通过 `enabled=false` 禁用 provider。
- `financial-read-tools` 是独立 provider，是否启用只由 provider-level `enabled` 表达，不再有 `include_read_tools` 二级开关。
- `financial-upload-tools` 默认注册 `start_fins_upload`；上传工具不再做本地文件 allowlist 授权，但仍校验上传动作、文件存在、普通文件、非空文件，并继续通过 Fins repository 写入。
- 受影响 pytest 通过，`pyright dayu tests utils` 无新增或扩散错误，相关 README / design docs 按触发规则更新。

## Non-goals / Scope Boundary

- 不实现 Host 统一权限系统、文件访问策略、sandbox、capability token 或 per-tool authorization policy。
- 不把工具发现、业务工具注册、provider lifecycle 或 Fins workspace 推断放进 Host / Engine。
- 不保留旧 schema 兼容读取；按全新 `tool_discovery.json` schema 起库。
- 不修改 scene manifest 的 `tool_selection.allow_empty`。它属于 scene 工具选择空匹配语义，不属于 ToolsDiscovery provider 空输出语义。
- 不改变 Host public request / response dataclass、Engine `AgentRunRequest`、ToolRuntime callable dispatch 或 framework tool 注入契约。
- 不实现 SEC/Fins CI pipeline、CN/HK Docling CI pipeline、Web smoke 扩展或 GitHub Issue #121 / #122 范围。
- 不重新设计 upload ingestion workflow、Docling upload conversion、Fins repository schema 或 DocumentRepository 存储布局。
- 不允许实现阶段修改 controller 总控文档；controller 另行更新 `docs/host/issues-implementation-control.md`。

## Design Document Alignment

`docs/host/design.md` 对齐点：

- `dayu.runtime` 是层中立基础设施，不得 import `dayu.engine` / `dayu.host` / `dayu.service` / `dayu.ui` / `dayu.fins`。
- `ToolsDiscovery` 位于 `dayu.runtime`，只加载显式 provider callable 或 entry point，聚合 provider 输出，生成 `ToolBundle`、source refs 与 digest；Host 不做工具发现、模块扫描或注册生命周期管理。
- `ConfigLoader` 位于 `dayu.runtime`，只负责读取、overlay、typed validation 与输出层中立 config view；不构造 Host，不创建 provider client，不解析业务工具，不读取 Fins storage。
- Service / composition root 是 ConfigLoader、ScenePrepare、ToolsDiscovery 输出进入 Host 的唯一映射方；映射失败必须在调用 Host 前失败。
- Host 不知道 scene manifest、config 文件或 tool provider，不扫描业务工具，不拼 prompt，不接收 raw `ToolBundle` 作为 per-run request。
- 现有设计中“provider 返回空工具集合可由 `allow_empty=true` 允许”的段落需要本 WU 同步修订为新语义：启用 provider 空输出默认是配置错误；需要业务上不暴露工具时通过 provider 自身配置 fail fast 或 provider-level `enabled=false` 表达。

`docs/engine/design.md` 对齐点：

- Engine 不读取配置文件，也不从 `ToolExecutor` 查询 schema；`tool_schemas` 是本次 run 模型可见工具的唯一输入快照。
- 工具声明与工具执行治理不属于 Engine；Host / ToolRuntime 持有 `ToolDefinition` / `ToolCallable` 并在自身治理边界包装为 `ToolExecutor`。
- 财报文档存取不属于 Engine 能力面；涉及财报文档的工具必须在 Engine 外部执行环境内遵守 `dayu.fins.storage` 仓储约束。

## First-principles Judgment And Direct Code Evidence

第一性原理判断：

- `enabled` 已经足以表达 provider 是否参与发现；再用 runtime-level `allow_empty` 授权空输出，会让 provider 的业务配置错误被通用 runtime 布尔开关掩盖。
- Fins read tools 已是独立 provider；`include_read_tools` 是 provider 内二级启停开关，职责与 `enabled` 重复，还允许“启用 provider 但不要求 workspace_root”的特例，削弱 fail fast。
- `workspace_root` 是 Fins provider 的业务输入，但相对路径如何定位属于 Service / composition root 装配上下文。ConfigLoader 原样读取，Fins provider 只接受 absolute path，职责清晰。
- 本地文件读取权限不是 Fins upload provider 能独立治理的全局权限问题。当前 allowlist 只能覆盖上传工具的一处本地路径读取，无法成为系统权限真源。删除它不等于放开仓储写入边界，上传写入仍由 Fins repository 和 ingestion workflow 控制。
- Packaged 默认配置应自解释。把 limits 只留在 provider dataclass 默认值里，会让复制出来的 `workspace/config/tool_discovery.json` 不能表达真实默认行为。

直接代码证据：

- `dayu/config/tool_discovery.json` 当前所有 providers 都有 `allow_empty`；Fins `workspace_root` 为 `null`；read provider 有 `include_read_tools`；Doc / Fins read `limits` 为 `{}`；upload provider 有 `allowed_upload_roots: []`。
- `dayu/runtime/config_loader.py` 的 `ToolDiscoveryProviderConfig`、`_parse_tool_discovery_provider(...)` 当前要求并保存 `allow_empty`。
- `dayu/runtime/tools_discovery.py` 的 `ToolsDiscoveryProviderSpec` 当前包含 `allow_empty`；空 provider 输出校验依赖该字段。
- `dayu/service/host_assembly.py` 当前在 `_tool_discovery_specs(...)` 中把 `allow_empty` 映射到 `ToolsDiscoveryProviderSpec`；`_effective_tool_provider_config(...)` 只在 Fins `workspace_root is None` 且传入 runtime workspace root 时注入绝对路径，不解析显式相对路径。
- `dayu/service/host_assembly.py` 的 `_fins_wait_adapter_registry_from_provider_configs(...)` 当前从 provider configs 读取 Fins awaiting provider 的 `workspace_root` 并要求绝对路径；如果 packaged config 改为相对 `"workspace/"` 但 wait adapter 仍消费 raw configs，Host tooling assembly 会在 wait adapter 构造阶段失败。
- `dayu/fins/tools/provider.py` 当前在 `include_read_tools=false` 时返回空工具集并跳过 `workspace_root` 解析。
- `dayu/fins/tools/upload_provider.py` 当前在 `allowed_upload_roots` 为空时返回空工具集。
- `dayu/fins/tools/upload_tools.py` 当前保存 `allowed_upload_roots`，schema 文案要求路径位于 configured upload roots，`_resolve_upload_path(...)` 会拒绝 allowlist 外路径。
- `dayu/tools/doc_provider.py` 当前在 enabled 且 `allowed_paths` 缺失或为空时返回空 definitions；删除 provider-level `allow_empty` 后，这必须变成业务明确的 fail-fast，而不是依赖 ToolsDiscovery 的通用空输出报错。
- Web provider 入口是 packaged import path `dayu.tools.web:discover_tools`，由 `dayu/tools/web/__init__.py` 转发到 `dayu/tools/web/provider.py`。`discover_tools(...)` 总是调用 `build_web_tool_definitions(...)`，随后 `_validate_web_definitions(...)` 要求工具名精确为 `("search_web", "fetch_web_page")`，不存在返回空 definitions 的正常路径。
- `dayu/fins/tools/download_provider.py` 在有效绝对 `workspace_root` 下总是返回 `(build_fins_download_tool(...),)`；`dayu/fins/tools/preprocess_provider.py` 在有效绝对 `workspace_root` 下总是返回 `(build_fins_preprocess_tool(...),)`，两者没有空 definitions 分支。
- `dayu/config/prompts/manifests/*.json` 当前没有 `mode="all"`；但多个默认 scene 使用 `tool_tags_any` 匹配 `"fins"`。`ScenePrepare` 对显式 `tool_names` 与 `tool_tags_any` 命中结果取并集，且没有排除字段。`start_fins_upload` 当前标签为 `("fins", "fins-upload")`，因此 upload 默认注册后会被这些默认 scene 通过 `"fins"` tag 意外选中。
- OLD `/Users/leo/workspace/dayu-agent/dayu/config/run.json` 的 `doc_tool_limits` 与 `fins_tool_limits` 给出默认值；OLD `/Users/leo/workspace/dayu-agent/dayu/contracts/tool_configs.py` 中 dataclass 默认值与当前 `DocToolLimits` / `FinsToolLimits` 基本一致。
- `dayu.fins.storage` 写入边界已通过 `DefaultFinsRuntime.create(workspace_root=...)` 装配 repository set，upload path 进入 `FinsIngestionRuntime` 后由 upload runner / `DoclingUploadService` / repository 协议写入 source/blob/processed 等目标；工具 caller 不能指定仓储写入目录。

## Affected Files / Modules

Production/config:

- `dayu/config/tool_discovery.json`
- `dayu/runtime/config_loader.py`
- `dayu/runtime/tools_discovery.py`
- `dayu/service/host_assembly.py`
- `dayu/fins/tools/provider.py`
- `dayu/fins/tools/upload_provider.py`
- `dayu/fins/tools/upload_tools.py`
- `dayu/config/prompts/manifests/*.json`

Likely unchanged but must be checked:

- `dayu/fins/tools/fins_limits.py`
- `dayu/tools/doc_tools.py`
- `dayu/fins/storage/*`

Tests:

- `tests/runtime/test_config_loader.py`
- `tests/runtime/test_tools_discovery.py`
- `tests/runtime/test_tools_discovery_digest.py`
- `tests/runtime/test_smoke_host_public_multiturn_assembly.py`
- `tests/service/test_host_assembly.py`
- `tests/fins/test_fins_storage_provider.py`
- `tests/fins/test_fins_ingestion_tools.py`
- `tests/tools/test_doc_tools_provider.py`
- `tests/tools/test_combined_tools_acceptance.py`
- related weak typing / import boundary tests under `tests/runtime`, `tests/service`, `tests/fins`, `tests/tools`

Docs:

- `docs/host/design.md`
- `dayu/config/README.md`
- `dayu/fins/README.md`
- `tests/README.md`
- `dayu/README.md` only if implementation changes cross-package boundary wording already summarized there.
- root `README.md` only if user-visible CLI / workflow / config instructions change.

## Contract / Schema / State-machine / Public-interface Changes

Schema changes:

- Remove required `allow_empty` from `tool_discovery.providers.<provider_id>`.
- Remove `financial-read-tools.config.include_read_tools`.
- Change packaged Fins provider `config.workspace_root` default from `null` to `"workspace/"`.
- Add explicit limits objects:
  - `doc-tools.config.limits`: `list_files_max=200`, `get_sections_max=200`, `search_files_max_results=50`, `read_file_max_chars=80000`, `read_file_section_max_chars=50000`.
  - `financial-read-tools.config.limits`: `processor_cache_max_entries=128`, `list_documents_max_items=300`, `get_document_sections_max_items=1200`, `search_document_max_items=20`, `list_tables_max_items=50`, `read_section_max_chars=80000`, `get_page_content_max_chars=80000`, `get_table_max_items=800`, `get_financial_statement_max_items=1200`, `query_xbrl_facts_max_items=1200`.
- Remove `financial-upload-tools.config.allowed_upload_roots`.

Typed contract changes:

- `ToolDiscoveryProviderConfig` removes `allow_empty`.
- `ToolsDiscoveryProviderSpec` removes `allow_empty`.
- Provider callable protocol remains `ToolsDiscoveryProviderCallable(spec) -> ToolsDiscoveryProviderOutput`.
- Host public contract, Engine public contract, ToolRuntime callable dispatch contract and framework tool injection contract do not change.

State-machine changes:

- No Host / Engine state-machine change.
- ToolsDiscovery provider aggregation invariant changes to: enabled provider returning zero definitions is always a discovery error, except the whole discovered bundle can still be empty when no provider is enabled.
- Scene `tool_selection.allow_empty` state/selection semantics remain unchanged. Default scene manifests may change `tool_names` / `tool_tags_any` selection inputs only to prevent newly registered upload tooling from being selected by broad `"fins"` tag matching.

Public-interface changes:

- Runtime Python API changes for internal typed config/spec constructors. Tests and internal call sites must update.
- No user-facing CLI command argument change unless root README currently mentions provider-level allowlist or config fields; verify before editing root README.

## Exact Implementation Decisions

1. Delete `allow_empty` from config schema and typed specs, not just packaged JSON. ConfigLoader must reject old provider records containing `allow_empty` because `_require_required_and_optional_fields(...)` should no longer allow it.
2. Keep `enabled` as the sole generic provider participation switch. Disabled providers remain skipped and may yield an empty final bundle if all providers are disabled.
3. Keep ToolsDiscovery empty output fail fast for every called provider. Delete tests that assert `allow_empty=True` succeeds; replace with tests for disabled provider skip and empty provider failure.
4. Delete Fins read `include_read_tools` parsing and helper. Read provider always parses `workspace_root`, constructs `DefaultFinsRuntime`, and returns the nine read tools when enabled.
5. Resolve Fins relative `workspace_root` only in Service effective assembly:
   - If provider is Fins workspace-bound and `config.workspace_root` is a non-empty string:
     - expand `~`;
     - if absolute, resolve with `strict=False`;
     - if relative, resolve against Service request/runtime `workspace_root` with the same containment semantics as `_resolve_project_path(...)`. The packaged `"workspace/"` value means: when Service receives `workspace_root=/path/to/project`, the effective Fins `workspace_root` is `/path/to/project/workspace`.
     - if relative and Service request/runtime `workspace_root` is `None`, fail fast in Service assembly with a precise message because the relative value has no valid base.
   - If provider is Fins workspace-bound and `config.workspace_root` is `None` or missing, inject runtime `workspace_root` if provided; otherwise leave it for provider / wait adapter fail fast.
   - If field exists but is not `None` or string, fail fast in Service assembly with a precise message; do not coerce.
6. Preserve Fins provider invariant: provider sees only absolute `workspace_root`; provider does not guess cwd/env/workspace.
7. `discover_service_tools(...)` and Host tooling wait adapter assembly must consume the same effective provider config tuple. Assemble effective configs once in `assemble_effective_tool_provider_configs(...)`, pass that tuple through `ServiceDiscoveredTools.effective_provider_configs`, and use it when building `HostToolingOptions`. `_fins_wait_adapter_registry_from_provider_configs(...)` must receive configs after `_effective_tool_provider_config(...)` has resolved relative Fins workspace roots to absolute paths; it must not read raw packaged `"workspace/"`.
8. Remove upload local file allowlist from provider and callable:
   - `upload_provider.discover_tools(...)` always parses `workspace_root` and registers `start_fins_upload`.
   - Delete `parse_allowed_upload_roots_config(...)`.
   - `build_fins_upload_tool(runtime)` no longer accepts `allowed_upload_roots`.
   - `FinsUploadToolCallable` stores only `runtime`.
   - `_upload_files_from_arguments(...)` validates action/file count and calls a path resolver that checks existing ordinary non-empty files, without allowlist containment.
   - Update LLM-facing schema description for `files` so it no longer says “under configured upload roots”; keep “local file paths to upload” and action constraints.
9. Do not change Fins repository write path APIs. If tests need to prove boundary, assert upload still goes through `FinsIngestionRuntime` / repository-backed runtime and no tool argument can specify destination directory.
10. Keep Doc provider `allowed_paths` unchanged but remove the empty-output branch. The single accepted path is:
   - packaged `doc-tools.enabled=false` by default;
   - if a workspace overlay enables `doc-tools` with missing or empty `allowed_paths`, `dayu.tools.doc_provider.discover_tools(...)` must fail fast with a business-specific error such as `doc provider config.allowed_paths must contain at least one path when doc-tools is enabled`;
   - do not let implementation choose between `enabled=false` and provider fail-fast; both are required.
11. For `web-tools`, keep enabled default. Direct code evidence from `dayu/tools/web/provider.py` shows the provider validates that definitions are exactly `("search_web", "fetch_web_page")`; there is no normal empty-output path.
12. For `financial-download-tools` and `financial-preprocess-tools`, keep enabled defaults. Direct code evidence shows each provider parses effective absolute `workspace_root` and returns exactly one awaiting tool definition under valid config.
13. Upload default registration would otherwise expose `start_fins_upload` through default scene manifests that match `"fins"`. Current manifest evidence shows no default scene explicitly names `start_fins_upload` or selects the `fins-upload` tag, so all current default scenes are treated as non-upload scenes in this WU. Update default scene manifest selection inputs so they no longer select upload via broad `"fins"` tag matching. Use explicit `tool_names` for `list_documents`, `get_document_sections`, `read_section`, `search_document`, `list_tables`, `get_table`, `get_page_content`, `get_financial_statement`, `query_xbrl_facts`, `start_fins_download` and `start_fins_preprocess`; keep existing `"web"` tag selection where applicable; do not change scene `tool_selection.allow_empty` semantics.
14. Do not introduce compatibility wrappers, re-export aliases, or old-field fallback.

## Implementation Slices

### Slice 1: Packaged schema and generic provider spec cleanup

Objective: remove provider-level `allow_empty` from the config contract, runtime provider spec and Service mapping in one independently verifiable slice, while making packaged `tool_discovery.json` self-explanatory for workspace roots and limits.

Allowed files:

- `dayu/config/tool_discovery.json`
- `dayu/runtime/config_loader.py`
- `dayu/runtime/tools_discovery.py`
- `dayu/service/host_assembly.py`
- `tests/runtime/test_config_loader.py`
- `tests/runtime/test_tools_discovery.py`
- `tests/runtime/test_tools_discovery_digest.py`
- `tests/service/test_host_assembly.py`
- `tests/tools/test_combined_tools_acceptance.py`
- `tests/runtime/test_smoke_host_public_multiturn_assembly.py`
- other tests that construct `ToolDiscoveryProviderConfig` or `ToolsDiscoveryProviderSpec`

Exact changes:

- Delete `allow_empty` from every provider record in packaged and test fixture `tool_discovery.json`.
- Change Fins provider packaged `workspace_root` from `null` to `"workspace/"`.
- Delete `include_read_tools` from `financial-read-tools.config`.
- Delete `allowed_upload_roots` from `financial-upload-tools.config`.
- Fill `financial-read-tools.config.limits` and `doc-tools.config.limits` with OLD default values.
- Set packaged `doc-tools.enabled=false`.
- Remove `allow_empty` field and docstring from `ToolDiscoveryProviderConfig`.
- Remove `allow_empty` field and docstring from `ToolsDiscoveryProviderSpec`.
- Remove `allow_empty=provider_config.allow_empty` mapping in `host_assembly.py::_tool_discovery_specs(...)`.
- Update `_parse_tool_discovery_provider(...)` required fields and return construction.
- Update ToolsDiscovery empty-output check to always reject empty `definitions` for called providers.
- Preserve final empty `ToolBundle(..., _allow_empty=True)` only when no enabled provider contributed definitions because no provider was called or all providers were disabled.
- Update tests and helper constructors to stop passing/asserting `allow_empty`; replace `allow_empty=True` success tests with disabled-provider skip and empty-provider failure assertions.

Data flow / state transitions / error handling / invariants:

- ConfigLoader still reads provider `config` as raw JSON object and does not parse provider-specific fields.
- Unknown `allow_empty` in workspace overlay must fail fast as an invalid field.
- `workspace_root` remains a string in typed config view; no absolute path resolution in ConfigLoader.
- The codebase must remain importable and Service tool discovery callable after this slice; there must be no intermediate state where `ToolsDiscoveryProviderSpec` no longer accepts `allow_empty` but `host_assembly.py` still passes it.
- Provider callable protocol remains unchanged.

Non-goals:

- Do not parse Fins limits into `FinsToolLimits` in ConfigLoader.
- Do not add compatibility for old `allow_empty`.
- Do not make ToolsDiscovery understand provider-specific config keys.
- Do not scan modules or add provider lifecycle.

Tests / validation:

- `pytest tests/runtime/test_config_loader.py -q`
- `pytest tests/runtime/test_tools_discovery.py tests/runtime/test_tools_discovery_digest.py -q`
- `pytest tests/service/test_host_assembly.py tests/runtime/test_smoke_host_public_multiturn_assembly.py -q`
- Include assertions that packaged `financial-read-tools.config["workspace_root"] == "workspace/"`, no `include_read_tools`, no provider has `allow_empty`, upload config has no `allowed_upload_roots`, and limits objects equal OLD defaults.
- Include assertions that `ToolDiscoveryProviderConfig` and `ToolsDiscoveryProviderSpec` constructors no longer accept `allow_empty`, enabled empty provider raises, disabled provider skips, and Service `_tool_discovery_specs(...)` no longer maps `allow_empty`.

Completion signal:

- ConfigLoader loads new packaged config and rejects old provider `allow_empty` fixtures; no production or test code references `ToolDiscoveryProviderConfig.allow_empty` or `ToolsDiscoveryProviderSpec.allow_empty`.

### Slice 2: Service effective Fins workspace path resolution

Objective: move relative Fins workspace resolution into Service / composition root while preserving Fins provider absolute-only contract.

Allowed files:

- `dayu/service/host_assembly.py`
- `tests/service/test_host_assembly.py`
- `tests/tools/test_combined_tools_acceptance.py`
- `tests/runtime/test_smoke_host_public_multiturn_assembly.py`

Exact changes:

- Update `_effective_tool_provider_config(...)`:
  - for non-Fins provider, return config unchanged;
  - for Fins provider with relative string `workspace_root`, replace with absolute path under Service request/runtime `workspace_root`;
  - for Fins provider with absolute string, normalize to absolute resolved string;
  - for Fins provider with `None` or missing `workspace_root`, preserve existing fallback behavior: inject runtime workspace root if provided, otherwise leave for fail fast.
- Add a private helper such as `_effective_fins_workspace_root_config_value(...)` if needed; keep it module-level and typed.
- Route wait adapter construction through the same effective provider config tuple used for discovery. `assemble_effective_tool_provider_configs(...)` produces effective configs once, `discover_service_tools(...)` stores them in `ServiceDiscoveredTools.effective_provider_configs`, and `_tooling_options(...)` / `_fins_wait_adapter_registry_from_provider_configs(...)` consumes that effective tuple.
- Update wait adapter tests so packaged relative `"workspace/"` becomes the same absolute Fins workspace across download / preprocess / upload awaiting providers.
- Update old tests that expected relative Fins provider config to fail before open_host: distinguish raw provider config passed directly to wait adapter from Service effective config. Service effective config should resolve relative; raw corrupted config used directly in compose should still fail where applicable.

Data flow / state transitions / error handling / invariants:

- ConfigLoader output remains raw.
- `discover_service_tools(...)` receives effective provider configs only after `assemble_effective_tool_provider_configs(...)`.
- Fins providers and `_fins_wait_adapter_registry_from_provider_configs(...)` only receive absolute strings.
- If multiple Fins awaiting providers resolve to different absolute roots, current mismatch error remains.
- Packaged `"workspace/"` always resolves relative to Service request/runtime `workspace_root`; for `workspace_root=/path/to/project`, effective Fins `workspace_root` must be `/path/to/project/workspace`.

Non-goals:

- Do not let Fins providers infer cwd/env.
- Do not move Fins workspace logic into Host / Engine.

Tests / validation:

- `pytest tests/service/test_host_assembly.py -q`
- Include an assertion that packaged relative `"workspace/"` resolves to `/path/to/project/workspace` when Service request/runtime `workspace_root` is `/path/to/project`, and raw config is not mutated.
- Include an assertion that wait adapter registry construction uses the same effective absolute workspace root and no longer sees raw relative `"workspace/"`.

Completion signal:

- Service discovery and Host assembly work with packaged `workspace/` defaults; Fins provider direct tests still reject relative `workspace_root`.

### Slice 3: Fins read provider independent-provider semantics

Objective: remove `include_read_tools` and make `financial-read-tools.enabled` the only read provider participation switch.

Allowed files:

- `dayu/fins/tools/provider.py`
- `tests/fins/test_fins_storage_provider.py`
- `tests/fins/test_fins_ingestion_tools.py`
- `tests/tools/test_combined_tools_acceptance.py`

Exact changes:

- Delete `_CONFIG_INCLUDE_READ_TOOLS_FIELD` and `_parse_bool_default(...)`.
- `discover_tools(...)` always parses limits, parses absolute workspace root, creates `DefaultFinsRuntime`, and returns the nine read definitions.
- Update tests:
  - remove `test_fins_provider_can_disable_read_tools_without_workspace_root`;
  - update `_spec(...)` helpers to omit `include_read_tools`;
  - keep `test_fins_workspace_root_must_be_explicit_absolute_path` and direct-provider relative path failure.

Data flow / state transitions / error handling / invariants:

- Provider enabled path requires valid absolute `workspace_root`.
- Provider never returns empty definitions under normal config.
- Limits parsing remains provider-owned and uses packaged values when present.

Non-goals:

- Do not merge read/download/preprocess/upload providers.
- Do not change read tool names or LLM-facing schemas except indirectly through limits where already supported.

Tests / validation:

- `pytest tests/fins/test_fins_storage_provider.py tests/fins/test_fins_ingestion_tools.py tests/tools/test_combined_tools_acceptance.py -q`

Completion signal:

- No production or test code references `include_read_tools`.

### Slice 4: Fins upload provider and local-file allowlist removal

Objective: delete upload provider local file allowlist restriction while preserving upload request validation and repository write boundary.

Allowed files:

- `dayu/fins/tools/upload_provider.py`
- `dayu/fins/tools/upload_tools.py`
- `dayu/config/prompts/manifests/*.json`
- `tests/fins/test_fins_ingestion_tools.py`
- `tests/runtime/test_scene_prepare.py`
- `tests/tools/test_combined_tools_acceptance.py`
- storage-boundary tests only if needed under `tests/fins`

Exact changes:

- In `upload_provider.py`, delete `parse_allowed_upload_roots_config(...)`, `_CONFIG_ALLOWED_UPLOAD_ROOTS_FIELD`, `Path` / `Mapping` / `JsonValue` imports if unused, and `__all__` export for parser.
- `discover_tools(...)` parses `workspace_root`, creates runtime and always returns `build_fins_upload_tool(ingestion_runtime)`.
- In default scene manifests under `dayu/config/prompts/manifests/`, prevent `start_fins_upload` from being selected by broad `"fins"` tag matching. Because current manifests do not explicitly name `start_fins_upload` or `fins-upload`, treat all current default manifests as non-upload scenes. Because `ScenePrepare` unions `tool_names` and tag matches and has no exclude list, replace broad `"fins"` tag selection with explicit `tool_names` for Fins read / download / preprocess tools, and keep `tool_tags_any` for `"web"` where needed.
- Do not change scene `tool_selection.allow_empty`.
- In `upload_tools.py`:
  - remove `allowed_upload_roots` from `FinsUploadToolCallable`;
  - remove `allowed_upload_roots` from `build_fins_upload_tool(...)`;
  - update `_upload_request_from_arguments(...)` and `_upload_files_from_arguments(...)` signatures;
  - replace `_normalize_allowed_upload_roots(...)` and `_resolve_upload_path(..., allowed_upload_roots=...)` with a simple `_resolve_upload_file_path(raw_path: str) -> Path` that expands, resolves, checks `is_file()` and non-empty size;
  - update schema `files.description` to remove configured roots wording.
- Update tests:
  - remove tests expecting empty upload provider when allowlist missing;
  - remove tests expecting relative `allowed_upload_roots` rejection;
  - update direct callable construction;
  - replace “outside allowed upload roots” failure test with “missing file / directory / empty file” validation tests;
  - add/keep success test proving a local file outside workspace can be accepted as source input while repository writes still land under the Fins workspace.
  - add scene manifest / ScenePrepare assertion that default non-upload scenes no longer select `start_fins_upload` after upload provider registers, while selected read/download/preprocess/web tools remain available as intended.

Data flow / state transitions / error handling / invariants:

- Delete action still forbids files.
- Auto/create/update still require at least one file.
- File paths are source input paths only; output / repository destination remains determined by Fins upload request, upload runner and repository implementation.
- LLM-facing tool schema must not imply provider-level authorization.
- Default scene manifests must not rely on a provider-local allowlist to hide upload. This WU handles default exposure by scene selection inputs only.

Non-goals:

- Do not add Host policy or sandbox.
- Do not change upload ingestion workflow, document id generation, Docling conversion or repository layout.

Tests / validation:

- `pytest tests/fins/test_fins_ingestion_tools.py -q`
- `pytest tests/runtime/test_scene_prepare.py tests/runtime/test_smoke_host_public_multiturn_assembly.py -q`
- Relevant storage/provider tests proving source/blob writes still use repository protocols.
- Explicit manifest check: with a catalog containing Fins read tools, `start_fins_download`, `start_fins_preprocess`, `start_fins_upload`, `search_web` and `fetch_web_page`, no current default scene selects `start_fins_upload`; scenes that previously selected Fins tools still select the explicit read/download/preprocess tools intended by their manifest.

Completion signal:

- No production or test code references `allowed_upload_roots`; default scene tool selection no longer exposes `start_fins_upload` through broad `"fins"` tag matching.

### Slice 5: Doc provider fail-fast and limits default assertions

Objective: make enabled Doc provider with empty `allowed_paths` fail fast with a business-specific error, and prove packaged config carries Doc/Fins limits consumed by providers.

Allowed files:

- `dayu/config/tool_discovery.json`
- `dayu/tools/doc_provider.py`
- `tests/runtime/test_config_loader.py`
- `tests/tools/test_doc_tools_provider.py`
- `tests/fins/test_fins_storage_provider.py`
- `tests/tools/test_combined_tools_acceptance.py`

Exact changes:

- In `doc_provider.py`, replace the enabled + empty `allowed_paths` empty-output branch with `ValueError` carrying a Doc-specific message. This is required even though packaged `doc-tools.enabled=false`, so workspace overlays that enable doc tools without paths fail at the business boundary.
- Add/adjust assertions for packaged limits in ConfigLoader tests.
- Add/adjust provider tests that pass explicit config limits from packaged-like fixtures and assert resulting tool definitions/truncate specs reflect those values where applicable.
- Add/adjust Doc provider test that enabled provider with missing or empty `allowed_paths` raises the Doc-specific error instead of returning empty definitions.
- Keep provider dataclass defaults unchanged unless tests or pyright reveal a need for docstring update; they remain fallback / test convenience.

Data flow / state transitions / error handling / invariants:

- ConfigLoader does not parse limits.
- Provider-specific `_parse_limits(...)` remains owner of limit coercion and positive-int validation.
- Missing individual limit fields still fall back to dataclass defaults for test construction convenience.

Non-goals:

- Do not create shared limits schema in runtime.
- Do not import Fins/Doc into ConfigLoader.

Tests / validation:

- `pytest tests/runtime/test_config_loader.py tests/tools/test_doc_tools_provider.py tests/fins/test_fins_storage_provider.py -q`

Completion signal:

- Packaged config default limits are asserted, explicit limits still alter provider output as before, and Doc provider has no enabled empty-output path.

### Slice 6: Documentation and design synchronization

Objective: make design and README text match the implemented schema and boundaries.

Allowed files:

- `docs/host/design.md`
- `dayu/config/README.md`
- `dayu/fins/README.md`
- `tests/README.md`
- `dayu/README.md` only if current text becomes materially stale
- `README.md` only if user-visible config/workflow text becomes materially stale

Exact changes:

- `docs/host/design.md`:
  - replace `tool_discovery.json` field list to remove `allow_empty`;
  - revise ToolsDiscovery empty provider paragraph to say enabled provider empty output is configuration error; disabling provider uses `enabled=false`; scene `tool_selection.allow_empty` remains separate.
  - keep Host / Engine non-ownership wording unchanged.
- `dayu/config/README.md`:
  - update provider fields table to remove `allow_empty`;
  - document Fins `workspace_root: "workspace/"` packaged relative default and Service effective absolute resolution;
  - remove `include_read_tools` and `allowed_upload_roots`;
  - document explicit Doc/Fins read limits defaults in packaged config;
  - document packaged `doc-tools.enabled=false`.
  - document default scene manifest selection no longer uses broad Fins tag matching where that would expose upload unintentionally.
- `dayu/fins/README.md`:
  - remove read provider `include_read_tools=false` behavior;
  - remove upload allowlist behavior;
  - state all four Fins providers require effective absolute `workspace_root`;
  - state upload local source file authorization is not provider-owned in this WU, while repository writes remain under `dayu.fins.storage`.
- `tests/README.md`:
  - update config loader / tools discovery / service / Fins awaiting assembly coverage descriptions.
- `dayu/README.md`:
  - update only if its high-level stable boundary text contradicts new provider/workspace/default semantics.
- root `README.md`:
  - update only if user-visible config examples or workflow text mention old provider allowlist / limits fields. Do not add internal architecture detail.
- `dayu/config/prompts/manifests/*.json` are LLM-facing config inputs; if changed in Slice 4, ensure their `tool_selection` remains self-explanatory and does not rely on implicit provider behavior.

Data flow / state transitions / error handling / invariants:

- Docs must describe implemented facts only, not future Host policy.
- LLM-facing tool schema/doc text must be self-explanatory and must not expose internal governance labels as business facts.

Non-goals:

- Do not update controller total state in `docs/host/issues-implementation-control.md`.
- Do not write review or PR process status into README.

Tests / validation:

- Documentation is validated by grep/manual check plus full pytest/pyright.

Completion signal:

- No docs mention old `allow_empty`, `include_read_tools` or upload `allowed_upload_roots` except when explicitly saying removed in design history is not needed.

### Slice 7: Final validation and cleanup

Objective: run focused tests first, then broad affected suite and pyright.

Allowed files:

- No production changes expected. Only fix files already touched by earlier slices if validation finds issues.

Exact changes:

- Run focused tests after each slice.
- Run combined affected suite.
- Run pyright.
- Search for removed fields and confirm no production stale references remain.

Data flow / state transitions / error handling / invariants:

- Failures caused by old tests should be fixed by updating tests to the new contract, not by adding compatibility logic.
- Pyright errors in touched boundaries must be fixed.

Non-goals:

- Do not broaden into unrelated CI pipeline or web smoke work.

Tests / validation:

- Commands listed in the next section.

Completion signal:

- Tests pass, pyright passes, stale-field grep is clean or only this plan/control docs mention removed fields as historical context.

## Tests / Validation Commands And Expected Assertions

Run in Python 3.11 virtualenv:

```bash
source .venv/bin/activate
pytest tests/runtime/test_config_loader.py tests/runtime/test_tools_discovery.py tests/runtime/test_tools_discovery_digest.py -q
pytest tests/service/test_host_assembly.py tests/runtime/test_smoke_host_public_multiturn_assembly.py -q
pytest tests/fins/test_fins_storage_provider.py tests/fins/test_fins_ingestion_tools.py -q
pytest tests/runtime/test_scene_prepare.py -q
pytest tests/tools/test_doc_tools_provider.py tests/tools/test_combined_tools_acceptance.py -q
pytest tests/runtime tests/service tests/fins tests/tools -q
pyright dayu tests utils
```

Expected assertions:

- ConfigLoader accepts new packaged `tool_discovery.json`; old provider records with `allow_empty` fail fast.
- `ToolDiscoveryProviderConfig` and `ToolsDiscoveryProviderSpec` construction no longer accepts `allow_empty`.
- Enabled provider returning empty definitions raises `ToolsDiscoveryError`.
- Disabled provider is skipped and can result in empty discovered bundle.
- Fins relative packaged `workspace/` becomes `/path/to/project/workspace` in Service effective provider configs when Service request/runtime `workspace_root` is `/path/to/project`.
- Fins wait adapter registry construction consumes effective provider configs and does not see raw relative `"workspace/"`.
- Direct Fins providers still reject relative `workspace_root`.
- Fins read provider no longer supports `include_read_tools`; enabled read provider returns nine tools.
- Web provider remains enabled and returns `search_web` / `fetch_web_page` under valid config.
- Fins download / preprocess providers remain enabled and each returns one awaiting tool under valid effective config.
- Upload provider registers `start_fins_upload` without `allowed_upload_roots`.
- Upload callable accepts existing non-empty local files without allowlist containment check and still rejects missing, directory, empty, and delete-with-files cases.
- Default scene manifests do not select `start_fins_upload` after upload provider registers; scene `tool_selection.allow_empty` semantics are unchanged.
- Repository write boundary remains through `dayu.fins.storage` repository protocols and workspace-rooted implementation.
- Enabled Doc provider with missing or empty `allowed_paths` raises a Doc-specific fail-fast error.
- Doc/Fins limits in packaged config match OLD defaults and are consumed by providers.
- No pyright errors are added or spread.

Additional grep checks:

```bash
rg -n "\"allow_empty\"|allow_empty|include_read_tools|allowed_upload_roots" dayu tests docs README.md
rg -n "workspace_root\": null" dayu/config/tool_discovery.json tests
```

Expected grep result:

- No production references to removed fields.
- Tests may mention removed fields only in explicit fail-fast assertions.
- Design/control/plan docs may mention removed fields only to describe this WU or historical cleanup.

## README / Docs Update Decision

AGENTS README trigger decision:

- `dayu/config/` changes require checking and likely updating `dayu/config/README.md`: yes, because `tool_discovery.json` schema/defaults change.
- `dayu/fins/` changes require checking and likely updating `dayu/fins/README.md`: yes, because Fins provider workspace/read/upload semantics change.
- `tests/` changes require checking and likely updating `tests/README.md`: yes, because runtime/service/Fins tool test coverage descriptions mention old semantics.
- `dayu/README.md`: check because cross-package Service/runtime/Fins boundary summary may mention provider config semantics. Update only if current text contradicts the new implemented boundary.
- Root `README.md`: check because user-visible config/workflow instructions mention tool config and upload behavior. Update only if it mentions removed provider fields or changed user-visible workflow. Do not add internal architecture detail.
- `docs/host/design.md`: update required because design truth currently mentions `tool_discovery.json` provider `allow_empty` and ToolsDiscovery provider empty-output allowance.
- `docs/engine/design.md`: likely no update needed because it already states Engine does not own tool declaration/execution/storage; update only if exact wording becomes contradictory.
- `docs/host/issues-implementation-control.md`: do not modify in implementation; controller owns total state.

README constraints already checked:

- `dayu/config/README.md` only documents current default config, workspace overlay and prompts.
- `dayu/fins/README.md` only documents implemented Fins package capability, boundaries, state machines and extension points.
- `tests/README.md` only documents current tests facts and maintenance rules.
- `dayu/README.md` only documents current cross-package design and stable boundaries.
- root `README.md` is final-user manual only.

## Risks / Open Questions / Residual Risks

Resolved plan-review risks:

- Doc provider default is no longer a fork: packaged `doc-tools.enabled=false`, and enabled Doc provider with missing or empty `allowed_paths` must raise a Doc-specific fail-fast error.
- Relative `workspace/` resolution base is fixed: Service request/runtime `workspace_root=/path/to/project` resolves packaged Fins `workspace_root: "workspace/"` to `/path/to/project/workspace`.
- Wait adapter construction must use the same effective provider config tuple as discovery, so raw relative packaged `"workspace/"` cannot reach `_fins_wait_adapter_registry_from_provider_configs(...)`.
- Web provider empty-output risk is resolved by direct code evidence: `dayu/tools/web/provider.py` validates exact `search_web` / `fetch_web_page` definitions.
- Fins download / preprocess empty-output risk is resolved by direct code evidence: each provider returns one awaiting tool under valid effective absolute `workspace_root`.
- Upload scene exposure risk is handled in this WU: current default scenes are treated as non-upload scenes and must use explicit Fins tool names instead of broad `"fins"` tag matching.

Implementation notes:

- Grep checks may show old fields in archived docs or this plan/control docs. Implementation should not churn historical artifacts unless they are current design/README truth.

Controller / docs owner:

- `docs/host/issues-implementation-control.md` must be updated after implementation/review by controller, not by implementation Agent in this WU.
- GitHub Issue #133 status/comment update is outside this plan artifact unless controller requests it.

Future Host / policy owner:

- Upload local file read authorization remains unresolved by design. This WU removes provider-local allowlist because it is not a sound system permission boundary. A future Host / policy design should decide whether and how local file reads are authorized, audited or sandboxed.

Residual risks:

- Removing `allow_empty` can surface latent empty provider configs in user workspaces. This is intended fail-fast under new schema, but rollout notes may be needed outside code.
- Upload tool schema wording must stay LLM-facing and self-explanatory. It must not say local file reads are globally safe; it should say upload local files the user asked to ingest and rely on future Host policy for authorization.
- Provider dataclass defaults remaining as fallback could drift from packaged defaults later. Tests should assert packaged defaults to reduce drift.

## Completion Report Format

Implementation closeout should report:

- Changed:
  - schema/config fields removed or added;
  - Service effective workspace resolution behavior;
  - Fins read/upload provider behavior;
  - docs/README updates.
- Validation:
  - exact pytest commands and pass/fail counts;
  - `pyright dayu tests utils` result;
  - stale-field grep summary.
- Risks / not covered:
  - upload local file permission remains future Host / policy work;
  - any skipped tests or known external dependency gaps;
  - any README intentionally not updated and why.

## Why This Is Not Over-designed

The plan removes generic knobs instead of adding new policy layers. It keeps each responsibility at the existing boundary:

- ConfigLoader reads and validates only the generic provider spec.
- Service resolves paths because only Service has runtime workspace context.
- ToolsDiscovery stays a small provider-callable aggregator.
- Fins providers keep only Fins business config and absolute workspace consumption.
- Host / Engine public contracts remain unchanged.
- Upload authorization is not papered over with another provider-local allowlist; it is explicitly left for a future Host / policy design where a real system permission boundary can exist.

No new registry, lifecycle manager, compatibility reader, permission framework, callback factory, profile system or storage abstraction is introduced. The implementation is a schema and assembly semantics cleanup with tests and docs following the changed contract.
