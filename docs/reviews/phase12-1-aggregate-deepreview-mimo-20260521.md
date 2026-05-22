# Phase 12.1 Aggregate Deep Review - AgentMiMo - 2026-05-21

## Verdict

**PASS** — blocking count = 0。

Phase 12.1 全部 6 个 slice 的实现、review、fix 与 acceptance 已完成。Aggregate deepreview 确认：所有 plan 成功信号已达成，runtime assembly schema / public contract mismatch 已修正，residual risks 有明确 owner。

## Review Scope

完整 Phase 12.1 工作单元，base commit `9d99fee`，HEAD `bf2bb0e`。

变更统计：107 files changed, +12761 / -1961。

关键模块：

- `dayu/runtime/` — config_loader, location, scene_prepare, assembly, tool_truncation
- `dayu/engine/` — provider_extensions
- `dayu/host/` — context_policy, context_budget, memory, tool_runtime, open_host, api
- `dayu/config/` — models.json, execution_profiles.json, host_runtime.json, runtime_lanes.json, tool_discovery.json, prompts/
- `utils/smoke_host_public_multiturn.py`
- `tests/` — runtime, engine, host
- `docs/` — design, implementation-control, reviews

## Aggregate Review Criteria

### 1. Host public surface 未越界

**结论：PASS。**

- `OpenHostOptions` 字段名保持不变：`context_budget_policy`、`memory_projection_policy`、`compactor_runner_baseline` 等。
- 没有新增 Host request / response 字段。
- `ContextBudgetPolicy` 改为 ratio-first shape（`context_window_size` + `soft_threshold_context_ratio` + `hard_threshold_context_ratio`），移除旧 `reserved_output_tokens`、`safety_margin_ratio`、`hard_threshold_tokens`、`minimum_protection_tokens`。字段名保持 `context_window_size` 不变。
- `MemoryProjectionPolicy` 改为 ratio/floor/cap shape（`context_window_size` + 各层 ratio/floor/cap），移除旧固定 size units。字段名保持不变。
- `open_host.py` 内部派生逻辑使用 `_internal_reserved_output_tokens_for_policy` 满足既有 command options validation，不改变 Host public surface。
- `HostCommandHandleOptions` 保持 `context_window_size` + `reserved_output_tokens` 字段名，内部映射为 ratio-first policy。

**直接证据：**

- `git diff 9d99fee...HEAD -- dayu/host/api.py | grep -E "class OpenHostOptions" — 字段列表未变
- `git diff 9d99fee...HEAD -- dayu/host/context_policy.py` — ratio-first shape，字段名一致
- `git diff 9d99fee...HEAD -- dayu/host/memory.py` — ratio/floor/cap shape，字段名一致

### 2. dayu.runtime import boundary 保持干净

**结论：PASS。**

自动化 AST 扫描确认 `dayu/runtime/` 下所有 `.py` 文件没有 import `dayu.engine`、`dayu.host`、`dayu.service`、`dayu.ui`、`dayu.fins` 或其子模块。

**直接证据：**

```python
# AST boundary scan result
IMPORT BOUNDARY: CLEAN
```

- `tests/runtime/test_import_boundary.py` 显式覆盖所有 runtime 模块
- `dayu/runtime/assembly.py` 只 import `dayu.contracts`、`dayu.runtime.config_loader`、`dayu.runtime.scene_prepare`、`dayu.runtime.tool_truncation`
- `dayu/runtime/__init__.py` 只 import stdlib

### 3. ConfigLoader 新 schema 是 fail-fast

**结论：PASS。**

- map-key id 是 canonical：`_FORBIDDEN_RECORD_ID_FIELDS` 包含 `runtime_id`、`host_runtime_id`、`model_id`、`profile_id`、`execution_profile_id`、`provider_id`；`_inject_id_and_check_no_duplicate` 在 JSON record 内出现这些字段时 fail fast。
- 旧 `llm_models.json` / `run.json` 不读取：`_LEGACY_CONFIG_FILES` 包含这两个文件名；`ConfigLoader.load()` 不加载它们。
- `runtime_lanes` / `tool_discovery` / `models` / `execution_profiles` / `host_runtime` 五类 typed view 对齐设计：`RuntimeConfig` dataclass 包含这五个字段。
- `execution_profiles.json` 顶层使用 `default_execution_profile_id` 与 `execution_profiles`；旧 `runner_options_profiles`、`runner_hints`、`agent_hints` 出现时 fail fast。
- `host_runtime.json` 顶层使用 `default_host_runtime_id`；旧 `worker_factory_kind`、`prompt_asset_root`、`scene_manifest_root` fallback 字段已删除。
- `runtime_lanes.json` 拥有 coordinator DB 路径和 lane catalog；`host_runtime.host_execution_lane_name` 必须引用已存在 lane。

**直接证据：**

- `dayu/runtime/config_loader.py:25-51` — `_FORBIDDEN_RECORD_ID_FIELDS`、`_LEGACY_CONFIG_FILES` 定义
- `tests/runtime/test_config_loader.py` — 477 行测试覆盖 fail-fast 场景

### 4. ScenePrepare schema 是 scene-only

**结论：PASS。**

- Scene manifest allowed top-level fields 固定为 `schema_version`、`scene`、`version`、`description`、`capability_tags`、`extends`、`model`、`agent_policy`、`tool_selection`、`defaults`、`fragments`、`context_slots`。
- `conversation` 与泛化 `runtime` 解析已删除；这些字段出现 fail fast（`_ALLOWED_MANIFEST_FIELDS` 不包含它们）。
- `model.default_name` 改为 `model.default_model_id`；`model.temperature_profile` 改为 `model.runner_option_hint_id`。
- `agent_policy` 是可选顶层 typed override block，只允许 8 个字段；未知字段 fail fast。
- `PreparedSceneInputs` 输出使用 `model_hints` 与 `agent_policy_override`，不包含旧 `runtime_hints` / `conversation_hint`。
- `prompt_mt` 不再作为独立 scene；`prompt_mt.json` / `prompt_mt.md` 已删除。

**直接证据：**

- `dayu/runtime/scene_prepare.py:31-82` — `_ALLOWED_*_FIELDS` 定义
- `git diff 9d99fee...HEAD -- dayu/config/prompts/manifests/` — `prompt_mt.json` 删除，新增 `smoke_host_public_multiturn.json`

### 5. ToolsDiscovery / tool bundle selection 正确

**结论：PASS。**

- per-run scene 只从已发现 bundle 内选择工具子集（`SceneToolCatalog.from_tool_bundle`）。
- 没有 raw ToolBundle stuffed into per-run request 或 metadata。
- `smoke_host_public_multiturn` scene 使用 `tool_selection.mode=select` 与 `tool_tags_any` 在 bundle 内选择。

**直接证据：**

- `dayu/runtime/scene_prepare.py:229-280` — `SceneToolCatalog.from_tool_bundle`
- `dayu/config/prompts/manifests/smoke_host_public_multiturn.json` — `tool_selection` 使用 `select` mode

### 6. Engine provider extension helper 是 fail-closed

**结论：PASS。**

- `dayu/engine/provider_extensions.py` 位于 Engine 层，import Engine `ProviderRequestExtension` union。
- 未知 `type` 值 fail closed：`raise ProviderExtensionConfigError(...)`.
- 未知字段 fail closed：`_require_exact_fields` 检查。
- 枚举值非法 fail closed：`_parse_enum` 检查。
- `dayu.runtime` 不 import Engine contracts：AST boundary scan 确认。

**直接证据：**

- `dayu/engine/provider_extensions.py:60-93` — `provider_request_extension_from_json` fail-closed 逻辑
- `tests/engine/test_provider_extension_config_adapter.py` — 172 行测试覆盖 fail-closed 场景

### 7. Tool truncation declaration / effective split 正确

**结论：PASS。**

- `ToolTruncateSpec` declaration 允许 enabled 且有 strategy 时 `limits` 缺对应 key，允许 `ttl_seconds=None`。
- `effective_tool_truncate_spec` helper 输入 declaration spec + policy default limit/ttl，输出 complete typed spec。
- helper 放在 `dayu.runtime.tool_truncation`，不在 Engine。

**直接证据：**

- `dayu/contracts/tool_schema.py` — `ToolTruncateSpec` validation 逻辑
- `dayu/runtime/tool_truncation.py` — `effective_tool_truncate_spec`
- `tests/host/test_toolruntime_truncation_fetch_more.py` — 截断测试通过

### 8. smoke 是真正的 Service-like assembly smoke

**结论：PASS。**

- `utils/smoke_host_public_multiturn.py` 使用 runtime location resolver、ConfigLoader、ToolsDiscovery、ScenePrepare、runtime assembly helper、Engine provider extension helper。
- 没有 manual / 硬编码装配模式：旧 `_DEEPSEEK_*`、`_CONTEXT_WINDOW_SIZE`、`_RESERVED_OUTPUT_TOKENS` 等硬编码常量已删除。
- 配置、scene、工具发现或 provider extension 映射缺口必须在调用 Host 前暴露：`_prepare_runtime_assembly` 在各步骤 fail fast。
- 调用 Host 前输出 assembly diagnostics：`AssemblyDiagnostics` dataclass 包含 config overlay、prompt root、scene manifest root、host runtime id、execution profile id、model id、runner option hint id、lane name、tool provider report、tool selection、policy refs、provider extension DSL 映射状态和 suggested helper names。
- 没有在 smoke 中用业务默认值补齐缺失 schema 字段。

**直接证据：**

- `utils/smoke_host_public_multiturn.py:526-630` — `_prepare_runtime_assembly` 使用真实 assembly 路径
- `utils/smoke_host_public_multiturn.py:633-700` — `_compose_open_host_options` 从 assembly 结果映射

### 9. README / test docs 匹配代码事实

**结论：PASS。**

- 根 `README.md`：更新配置文件职责表（新增 `runtime_lanes.json`）、smoke 使用说明、`--label` 文档移除 `prompt_mt` 引用、模型配置示例使用 `runtime_hints.runner_option_hints`。
- `dayu/README.md`：更新 `dayu.runtime` 边界描述（新增 `location`、`assembly`、`tool_truncation`）、新增 provider request extension DSL 扩展入口。
- `dayu/config/README.md`：完整重写，对齐新 schema（map-key canonical id、`runtime_lanes.json`、scene-only manifest、ratio/floor/cap policy）。
- `dayu/host/README.md`：新增 policy typed shape 说明。
- `dayu/engine/README.md`：新增 provider extension helper 边界。
- `tests/README.md`：更新 import boundary 覆盖列表。

**直接证据：**

- `git diff 9d99fee...HEAD -- README.md dayu/README.md dayu/config/README.md dayu/host/README.md dayu/engine/README.md tests/README.md`

### 10. Residual risks 有 owner

**结论：PASS。**

| Residual Risk | Owner |
|---|---|
| 真实 Service / CLI / Web / GUI workflow 接入 | 后续 Service / UI / workflow work unit |
| Provider model catalog 时效性 | 后续 execution profile / model catalog maintenance |
| Financial tool provider 与财报 scene 内容 | 后续 Service / Fins / 配置 work unit |
| Tool truncation policy 与具体工具 declaration 覆盖度 | 后续 tool provider hardening |
| Service/composition helper 正式归属 | 后续 Service assembly work unit |

## Validation Results

### 测试通过

```
tests/runtime:           208 passed
tests/engine:             11 passed
tests/host:               83 passed
Total:                   302 passed
```

### Pyright 类型检查

```
0 errors, 0 warnings, 0 informations
```

### Git whitespace check

```
docs/reviews/ 下旧文件有 trailing whitespace（非本次变更核心代码）
核心代码无 whitespace 问题
```

## Blocking Findings

无。

## Non-blocking Findings

### Finding 1: docs/reviews 旧文件 trailing whitespace

**Severity:** non-blocking

**Description:** `docs/reviews/phase12-1-slice1-implementation-codex-20260521.md` 等旧 review artifact 有 trailing whitespace。

**Recommendation:** 后续统一清理，不阻塞 Phase 12.1 acceptance。

### Finding 2: smoke 硬编码少量 Host construction 参数

**Severity:** non-blocking

**Description:** `utils/smoke_host_public_multiturn.py` 仍硬编码 `_SQLITE_WRITE_BUSY_RETRY_COUNT`、`_SQLITE_WRITE_RETRY_INITIAL_DELAY_SECONDS`、`_PAYLOAD_INLINE_THRESHOLD_BYTES` 等 Host construction 参数。

**Assessment:** 这些参数属于 Host construction-time 基础设施调优，不属于 runtime config schema 范畴；当前 Host runtime config 不表达这些参数。Phase 12.1 scope 不包含 Host construction 参数全量配置化。

**Recommendation:** 后续 Service / Host runtime config work unit 可按需将这些参数纳入 `host_runtime.json`。

### Finding 3: smoke smoke_fact_tool 是 mock 而非真实业务工具

**Severity:** non-blocking

**Description:** `SmokeFactTool` 是 mock business tool，不是真实财报工具。

**Assessment:** Phase 12.1 scope 不包含真实财报工具接入；smoke 目的是验证 runtime assembly 路径，不是验证财报业务逻辑。`ToolsDiscovery` 从 `tool_discovery.json` 配置的 provider 获取工具；当前默认配置没有启用真实业务工具 provider。

**Recommendation:** 后续 Fins / tool provider work unit 配置真实业务工具 provider 后，smoke 可自动发现并使用。

## Architecture Assessment

Phase 12.1 正确实现了 plan 定义的所有成功信号：

1. **Runtime assembly schema 统一**：ConfigLoader、ScenePrepare、ToolsDiscovery 与 assembly helper 能在不写脚本业务默认值的前提下，从配置、scene、工具发现结果和显式调用方 override 装配出 `open_host(options)` 与每 Run typed input。

2. **Host public contract 稳定**：Host command path、handle methods、`open_host(options)` option 字段名、public request / response dataclass 字段名、`dayu.host` public exports 未变。

3. **Runtime import boundary clean**：`dayu.runtime` 不 import `dayu.engine` / `dayu.host` / `dayu.service` / `dayu.ui` / `dayu.fins`。

4. **Schema fail-fast**：旧字段、未知字段、非法引用均 fail fast；不提供 compatibility reader。

5. **Provider extension fail-closed**：Engine helper 对未知 DSL type、未知字段、非法枚举值均 fail closed。

6. **Smoke 真实暴露 schema gap**：smoke 使用真实 runtime assembly 路径，配置缺口在调用 Host 前暴露。

## Conclusion

Phase 12.1 工作单元已通过 aggregate deepreview。所有 plan 成功信号已达成，blocking findings 为 0，residual risks 有明确 owner。建议进入 `ready-to-open-draft-PR`。
