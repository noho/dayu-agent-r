# WU-TOOLS-01-F03-R3 Effective Spec Follow-up Fix Re-Review

**日期**: 2026-06-10

**审查人**: AgentMiMo

**范围**: Controller 裁决后的 follow-up fix re-review，验证四项修复是否基于代码证据成立。

---

## 1. Controller 对 DS F1 裁决验证：web-tools 默认启用不会让所有 scene 暴露 Web tools

### 裁决内容

Controller 认为 DS F1 不成立，理由：
- `scene_prepare._select_tools` 按 scene manifest 的 `tool_selection` 计算 per-run 工具白名单
- `mode=none` 返回空集合，`mode=select` 只返回显式工具名或 tag 命中的工具，只有 `mode=all` 才返回 `None` 表示全量
- `tool_runtime._selected_business_definitions` 按 `SubmitFollowupRequest.tool_names` 过滤；`None` 才表示全量
- `allow_empty=true` 只允许 provider 成功返回空工具集合；`resolve_provider_callable` 的 import path 解析失败仍抛 `ToolsDiscoveryError`

### 代码证据验证

**证据 1**: `dayu/runtime/scene_prepare.py:1080-1106`

```python
def _select_tools(*, selection: SceneToolSelection, catalog: SceneToolCatalog) -> SceneToolSelectionResult:
    if selection.mode == SceneToolSelectionMode.ALL:
        return SceneToolSelectionResult(mode=selection.mode, tool_names=None)  # None = 全量
    if selection.mode == SceneToolSelectionMode.NONE:
        return SceneToolSelectionResult(mode=selection.mode, tool_names=frozenset())  # 空集合
    # select 模式：按 tool_names + tool_tags_any 计算
```

确认：只有 `mode=ALL` 才返回 `tool_names=None`（全量），其他模式都有明确过滤。

**证据 2**: `dayu/host/tool_runtime.py:2040-2063`

```python
def _selected_business_definitions(
    bundle: ToolBundle, selected_tool_names: frozenset[str] | None
) -> tuple[ToolDefinition, ...]:
    if selected_tool_names is None:
        return bundle.definitions  # 全量
    # 否则按 selected_tool_names 过滤
```

确认：`None` 才表示全量，非空集合只启用指定工具。

**证据 3**: `dayu/runtime/tools_discovery.py:290-306, 322-323`

```python
def resolve_provider_callable(spec: ToolsDiscoveryProviderSpec) -> ToolsDiscoveryProviderCallable:
    # ...
    module = importlib.import_module(module_name)
    # ModuleNotFoundError 被捕获并转换为 ToolsDiscoveryError
```

确认：import path 解析失败抛 `ToolsDiscoveryError`，不被 `allow_empty` 静默吞掉。

**证据 4**: `dayu/runtime/tools_discovery.py:544-545`

```python
if not output.definitions and not spec.allow_empty:
    raise ToolsDiscoveryError(f"provider {provider_id} returned empty tools")
```

确认：`allow_empty` 只控制空工具集合是否允许，不控制 import 失败。

### 结论

**裁决成立**。Controller 基于直接代码证据正确判断：web-tools 默认 `enabled: true` 不会让所有 scene 暴露 Web tools，因为 scene manifest 的 `tool_selection` 机制会按场景过滤工具。只有 `mode=all` 的 scene 才会暴露 construction-time 全量工具，这不是 `web-tools.enabled=true` 的 root cause。

---

## 2. ServiceDiscoveredTools.effective_provider_configs 复用验证

### 裁决内容

Controller 要求修复 discovery 与 wait adapter registry effective config 一致性问题，方案：
- `ServiceDiscoveredTools` 新增 `effective_provider_configs`
- `compose_open_host_options` 复用 `request.discovered_tools.effective_provider_configs`，不再从 raw config 独立重算

### 代码证据验证

**证据 1**: `dayu/service/host_assembly.py:147-155` (ServiceDiscoveredTools 新增字段)

```python
@dataclass(frozen=True, slots=True)
class ServiceDiscoveredTools:
    tool_bundle: ToolBundle
    source_refs: tuple[ToolBundleSourceRef, ...]
    provider_reports: tuple[str, ...]
    effective_provider_configs: tuple[ToolDiscoveryProviderConfig, ...]  # 新增
```

确认：字段已新增。

**证据 2**: `dayu/service/host_assembly.py:269-303` (discover_service_tools 计算并保存 effective config)

```python
def discover_service_tools(config: RuntimeConfig, *, workspace_root: pathlib.Path | None = None) -> ServiceDiscoveredTools:
    effective_provider_configs = _effective_tool_provider_configs(
        tuple(config.tool_discovery.providers.values()),
        workspace_root=workspace_root,
    )
    discovery_result = ToolsDiscovery().discover(_tool_discovery_specs(effective_provider_configs))
    return ServiceDiscoveredTools(
        tool_bundle=discovery_result.tool_bundle,
        source_refs=discovery_result.source_refs,
        provider_reports=...,
        effective_provider_configs=effective_provider_configs,  # 保存
    )
```

确认：discovery 阶段计算的 effective config 被保存到返回值。

**证据 3**: `dayu/service/host_assembly.py:520-524` (compose 复用 effective config)

```python
tooling_options=_tooling_options_from_discovery(
    tool_bundle=effective_tool_bundle,
    source_refs=request.discovered_tools.source_refs,
    provider_configs=request.discovered_tools.effective_provider_configs,  # 复用
    ...
)
```

确认：compose 阶段从 `request.discovered_tools.effective_provider_configs` 取 provider configs，不再从 `request.config.tool_discovery.providers` 独立重算。

**证据 4**: `tests/service/test_host_assembly.py` (集成测试验证)

`test_discover_service_tools_carries_effective_fins_config_into_compose` 测试：
1. 创建 Fins download provider overlay，`workspace_root=None`
2. 调用 `discover_service_tools(config, workspace_root=fins_workspace)` 发现工具
3. 验证 `discovered_provider.config["workspace_root"] == str(fins_workspace)`
4. **关键**：将 raw config 污染为相对路径 `"relative/fins-workspace"`
5. 调用 `compose_open_host_options` 使用被污染的 config
6. 验证 `tooling_options.wait_adapter_registry` 能正确 resolve binding

确认：测试证明 compose 阶段不会回读 raw config，即使 raw config 被污染。

### 结论

**修复正确**。discovery 阶段的 effective config 通过 `ServiceDiscoveredTools.effective_provider_configs` 传递给 compose 阶段，Fins tool closure 与 wait adapter registry 不再独立重算。集成测试验证了即使 raw config 被污染，compose 仍使用 discovery 阶段的 effective config。

---

## 3. 新增测试覆盖验证

### 3.1 Fins workspace-bound provider 边界测试

**测试**: `test_fins_workspace_bound_provider_detection_boundaries`

覆盖的边界：
| Case | provider_id | import_path | source_id | 预期 |
|------|-------------|-------------|-----------|------|
| ordinary-doc | doc-tools | dayu.tools.doc_provider:discover_tools | dayu.tools.doc_provider | False |
| read-entry-source | custom-read | (None, entry_point) | dayu.fins.tools.provider | True |
| download-import | custom-download | dayu.fins.tools.download_provider:discover_tools | custom.download | True |
| preprocess-source | custom-preprocess | custom.preprocess:discover_tools | dayu.fins.tools.preprocess_provider | True |
| upload-id | financial-upload-tools | custom.upload:discover_tools | custom.upload | True |

**验证**: 覆盖了 DS F2 要求的所有边界：非 Fins provider（返回 False）、read provider source id + entry point、download import path、preprocess source id、upload provider id。

### 3.2 discovery->compose 链路测试

**测试**: `test_discover_service_tools_carries_effective_fins_config_into_compose`

覆盖的场景：
1. discovery 阶段注入 Fins workspace config
2. compose 阶段复用 discovery 阶段的 effective config
3. raw config 被污染后 compose 不会回读

**验证**: 覆盖了 MiMo F1 / DS F3 / DS F4 要求的 discovery->compose 链路一致性。

### 3.3 search provider 分类 hard/diagnostic 边界测试

**测试集**:
- `test_search_http_status_classifier`: 覆盖 HTTP status 分类（401→auth_failure, 403→auth_failure, 429→quota, 500→unavailable）
- `test_search_error_text_classifier`: 覆盖错误文本分类（8 种模式）
- `test_single_search_provider_case_reports_loader_failure`: ConfigLoader hard failure → exit_code=2
- `test_single_search_provider_case_reports_discovery_failure`: discovery hard failure → exit_code=2
- `test_single_search_provider_case_classifies_callable_timeout`: timeout → diagnostic_only, exit_code=0
- `test_single_search_provider_case_classifies_empty_results`: empty results → diagnostic_only, exit_code=0

**验证**: 覆盖了 DS F7 要求的所有分类边界。hard failure（ConfigLoader/discovery 失败）映射为 `_EXIT_SCHEMA_OR_INFRA_FAILURE`，diagnostic-only（外部 provider 波动）映射为 `_EXIT_OK`。

### 结论

**测试覆盖完整**。所有 Controller 裁决要求修复的边界都已被新增测试覆盖。

---

## 4. 新增 correctness/type/layering 问题检查

### 4.1 类型安全

- `_effective_tool_provider_config` 返回 `Mapping[str, JsonValue]`，使用 `is` 比较判断是否需要替换。DS F5 指出这是隐式约定，Controller 决定不修复。
- 当前代码正确：函数返回原始 mapping（无变更时）或新 dict（注入时），identity 比较准确。
- **无新增类型问题**。

### 4.2 分层约束

- `smoke_web_ci.py` 新增对 `dayu.service.host_assembly.discover_service_tools` 的依赖，但 smoke 脚本在 `utils/` 目录，无分层约束。
- `tests/service/test_host_assembly.py` 新增对 `_is_fins_workspace_bound_provider_config` 的导入测试，但这是私有函数的白盒测试，可接受。
- **无新增 layering 问题**。

### 4.3 search_cases 进入 hard gate

从 `_summary_from_cases` 的改动：
```python
hard_gate_cases = tuple(local_cases) + tuple(search_cases)
if any(case.exit_code == _EXIT_SCHEMA_OR_INFRA_FAILURE for case in hard_gate_cases):
    local_exit_code = _EXIT_SCHEMA_OR_INFRA_FAILURE
```

search provider 的 ConfigLoader 或 discovery 失败（`_EXIT_SCHEMA_OR_INFRA_FAILURE`）会影响 smoke 整体 exit code。这是正确的行为：配置装配失败是 local blocker，不是外部 provider 波动。

**无 correctness 问题**。

### 4.4 _FINS_READ_* 常量补齐

新增常量：
- `_FINS_READ_PROVIDER_IDS = frozenset({"financial-read-tools"})`
- `_FINS_READ_IMPORT_PATHS = frozenset({"dayu.fins.tools.provider:discover_tools"})`
- `_FINS_READ_SOURCE_IDS = frozenset({"dayu.fins.tools.provider"})`

与 `_FINS_DOWNLOAD_*`、`_FINS_PREPROCESS_*`、`_FINS_UPLOAD_*` 对称，覆盖了 read provider 的三重匹配。

**无遗漏**。

### 结论

**无新增 correctness/type/layering 问题**。

---

## 总结

| 验证项 | 结论 |
|--------|------|
| Controller 对 DS F1 裁决 | 基于代码证据成立 |
| effective_provider_configs 复用 | 修复正确，discovery->compose 链路一致 |
| 测试覆盖 | 完整覆盖所有要求边界 |
| 新增问题 | 无 correctness/type/layering 问题 |

**Re-Review 结论**: Pass。所有 accepted findings 已正确修复，无新增 blocking issues。
