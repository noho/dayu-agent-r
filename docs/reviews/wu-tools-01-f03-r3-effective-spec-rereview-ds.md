# WU-TOOLS-01-F03-R3 Effective Spec Follow-Up Fix — Re-Review (DS)

**范围**: 只审查 Controller adjudication 接受的 findings 修复结果与周边代码，不改文件。

**日期**: 2026-06-10

**审查人**: DS (DeepSeek)

**参考**:
- `wu-tools-01-f03-r3-effective-spec-review-ds.md` (原始 DS review)
- `wu-tools-01-f03-r3-effective-spec-review-controller-adjudication.md` (Controller 裁决)
- `wu-tools-01-f03-r3-fix-codex.md` (Codex fix artifact)
- `wu-tools-01-f03-r3-rereview-ds.md` (前次 DS re-review — MiMo F1/F2/F4)

---

## 审查范围

按用户指定，本轮重点核对四个维度：

1. Controller 对 DS F1 的裁决是否基于代码证据成立
2. `ServiceDiscoveredTools.effective_provider_configs` 后 compose 链是否正确复用
3. 新增 tests 是否覆盖 Fins workspace-bound provider 边界、discovery→compose 链路、search provider hard/diagnostic 边界
4. 是否有新的 correctness/type/layering 问题

---

## 1. Controller 对 DS F1 的裁决验证

### 裁决原文

> 不接受原 finding。ToolDiscovery 只产生候选工具，ScenePrepare/Host per-run tool_names 决定实际工具可见性，allow_empty 不吞 import failure。

### 代码证据逐条核验

**1a. ScenePrepare `_select_tools` 按 mode 计算工具白名单**

`dayu/runtime/scene_prepare.py:1080-1106`:

```python
def _select_tools(*, selection: SceneToolSelection, catalog: SceneToolCatalog) -> SceneToolSelectionResult:
    if selection.mode == SceneToolSelectionMode.ALL:
        return SceneToolSelectionResult(mode=selection.mode, tool_names=None)  # None = 全量
    if selection.mode == SceneToolSelectionMode.NONE:
        return SceneToolSelectionResult(mode=selection.mode, tool_names=frozenset())  # 空 = 禁用
    # mode=select: tool_names + tag 命中
    ...
    selected = frozenset((*selection.tool_names, *selected_by_tag))
    return SceneToolSelectionResult(mode=selection.mode, tool_names=selected)
```

**验证结论**: mode 三个分支语义精确: ALL → None（全量）, NONE → 空集合, SELECT → 显式 union。ToolDiscovery 产出的全量工具集在 mode=NONE 和 mode=SELECT 时都会被进一步过滤，不会被直接暴露给 LLM。

**1b. Host `_selected_business_definitions` 按 per-run tool_names 过滤**

`dayu/host/tool_runtime.py:2040-2063`:

```python
def _selected_business_definitions(
    bundle: ToolBundle, selected_tool_names: frozenset[str] | None
) -> tuple[ToolDefinition, ...]:
    if selected_tool_names is None:
        return bundle.definitions  # 全量
    ...
    return tuple(definition for definition in bundle.definitions if definition.name in selected_tool_names)
```

**验证结论**: `None` → 全量, 非空 → 按名过滤。只有 ScenePrepare 输出 `tool_names=None`（来自 mode=ALL）且 Service/UI 调用点直接传 `tool_names=None` 到 Host 时，construction-time 全量工具才会暴露。

**1c. 当前 scene manifest 无 mode=all**

全局搜索 `dayu/config/prompts/manifests/*.json` 的 `tool_selection.mode`:

| scene | mode |
|-------|------|
| prompt.json | select (tags: web, fins, ingestion) |
| overview.json | none |
| audit.json | none |
| conversation_compaction.json | none |
| 其余 12 个 scene | select |

**验证结论**: 无任何 scene 使用 `mode=all`。`web-tools.enabled=true` 使 Web tools 进入 construction-time discovery 候选集，但实际 per-run 可见性由 scene manifest 的 `tool_selection` 决定。

**旁注**: `prompt.json` 使用 `tool_tags_any: ["web"]`，而 `search_web` / `fetch_web_page` 携带 `tags=("web",)` (`dayu/tools/web/web_tools.py:1058,1163`)。这意味着 prompt scene 确实会选择 Web tools — 但这是 scene 显式 opt-in，不是 `enabled=true` 的副作用。

**1d. `allow_empty` 不吞 import failure**

`dayu/runtime/tools_discovery.py:309-329`:

```python
def _resolve_import_path(import_path: str) -> ToolsDiscoveryProviderCallable:
    module_name, separator, attribute_path = import_path.partition(_IMPORT_PATH_SEPARATOR)
    ...
    try:
        module = importlib.import_module(module_name)
    except ModuleNotFoundError as exc:
        raise ToolsDiscoveryError(...) from exc
```

而 `allow_empty` 仅在 provider 成功 import 但返回空工具集时生效 (`tools_discovery.py:544`):

```python
if not output.definitions and not spec.allow_empty:
    raise ToolsDiscoveryError(f"provider {provider_id} returned empty tools")
```

**验证结论**: `allow_empty` 与 import 解析路径正交 — import 失败抛 `ToolsDiscoveryError` 不会被 `allow_empty` 静默吞掉。

### 1. 裁决综合结论

**Controller DS F1 裁决成立，基于充分代码证据**。Web tools 的可见性由 ScenePrepare `_select_tools` + Host `_selected_business_definitions` 两层过滤共同决定；`enabled=true` 只影响 construction-time 候选集大小，不绕过 per-run 工具选择。

---

## 2. effective_provider_configs compose 链验证

### 2a. 数据流全链路追踪

```
discover_service_tools(config, workspace_root)
  → _effective_tool_provider_configs(raw_providers, workspace_root)
    → for each: _effective_tool_provider_config(provider_config, workspace_root)
      → 若 Fins workspace-bound 且 config 无显式 workspace_root 且 workspace_root 非 None
        → 新建 dict 注入 workspace_root
      → 否则返回原 config
    → 产出 tuple[ToolDiscoveryProviderConfig, ...]（注入后的 provider configs）
  → ServiceDiscoveredTools(effective_provider_configs=...)
  → ToolsDiscovery().discover(_tool_discovery_specs(effective_provider_configs))

compose_open_host_options(request)
  → _compose_options(...)
    → _tooling_options_from_discovery(
        provider_configs=request.discovered_tools.effective_provider_configs,  ← 复用
        ...
      )
      → _fins_wait_adapter_registry_from_provider_configs(provider_configs)
        → 从 provider_config.config["workspace_root"] 取值  ← 来自 effective config
```

**关键代码点**:

- `host_assembly.py:287-289`: `discover_service_tools` 调用 `_effective_tool_provider_configs` 产出 effective provider configs
- `host_assembly.py:306`: 存入 `ServiceDiscoveredTools.effective_provider_configs`
- `host_assembly.py:523`: `_compose_options` 传递 `request.discovered_tools.effective_provider_configs` 给 `_tooling_options_from_discovery`
- `host_assembly.py:1183-1185`: `_fins_wait_adapter_registry_from_provider_configs` 从 effective config 中取 workspace_root

### 2b. 算法一致性验证

`_tool_discovery_specs` (discovery 路径) 与 `_effective_tool_provider_configs` (compose 路径) 都调用同一个 `_effective_tool_provider_config()` 算法:

- `host_assembly.py:810-813`: `_tool_discovery_specs` → `_effective_tool_provider_config(provider_config, workspace_root=workspace_root)`
- `host_assembly.py:861-863`: `_effective_tool_provider_configs` → `_effective_tool_provider_config(provider_config, workspace_root=workspace_root)`

两个路径使用同一算法、同一 `workspace_root` 参数时产出相同结果。

### 2c. 已有测试证据

`test_discover_service_tools_carries_effective_fins_config_into_compose` (`tests/service/test_host_assembly.py:1028-1107`):

1. 构造 Fins download provider overlay（`workspace_root: None`）
2. 调用 `discover_service_tools(config, workspace_root=fins_workspace)`
3. 断言 `effective_provider_configs[0].config["workspace_root"] == str(fins_workspace)` — discovery 阶段注入了 workspace root
4. 将 raw config **污染**为相对路径: `config={"workspace_root": "relative/fins-workspace"}`
5. 调用 `compose_open_host_options` 传入被污染的 config
6. 断言 `wait_adapter_registry` 不为 None，且 adapter key 正确

**这个测试直接证明了 compose 阶段不回读 raw config** — raw config 被污染为相对路径后，若 compose 回读 raw config，会在 `_fins_workspace_root_from_provider_config` 中因非绝对路径而 fail。但测试通过，说明 compose 使用的是 discovery 阶段注入后的 effective config。

### 2. 综合结论

**compose 链正确复用了 discovery 阶段的 effective provider configs**。Fins tool closure 与 wait adapter registry 不再独立重算，一致性由 `_effective_tool_provider_config()` 的单算法 + `ServiceDiscoveredTools.effective_provider_configs` 的单真源保证。

---

## 3. 新增测试覆盖验证

### 3a. Fins workspace-bound provider 边界

`test_fins_workspace_bound_provider_detection_boundaries` (line 953-1025):

| 标签 | 测试场景 | 预期 | 实际覆盖 |
|------|---------|------|---------|
| ordinary-doc | 非 Fins provider (doc-tools) | False | provider_id/import_path/source_id 无匹配，且 `_fins_awaiting_tool_name_from_provider_config` 返回 None → False |
| read-entry-source | read provider 通过 source_id + entry_point | True | `source_id="dayu.fins.tools.provider"` 命中 `_FINS_READ_SOURCE_IDS` |
| download-import | download 通过 import_path | True | `import_path="dayu.fins.tools.download_provider:discover_tools"` 命中 `_FINS_READ_IMPORT_PATHS` |
| preprocess-source | preprocess 通过 source_id | True | `source_id="dayu.fins.tools.preprocess_provider"` → `_fins_awaiting_tool_name_from_provider_config` → `FINS_PREPROCESS_AWAITING_TOOL_NAME` |
| upload-id | upload 通过 provider_id | True | `provider_id="financial-upload-tools"` → `_fins_awaiting_tool_name_from_provider_config` → `FINS_UPLOAD_AWAITING_TOOL_NAME` |

**覆盖评估**: 覆盖了 OR 型匹配的所有路径 — provider_id、import_path、source_id 各至少一个命中 case，以及 `_fins_awaiting_tool_name_from_provider_config` 的 download/preprocess/upload 三个分支。还覆盖了 entry_point-only provider 场景（read-entry-source 使用 entry_point 而非 import_path）。

### 3b. Discovery→compose 链路

`test_discover_service_tools_carries_effective_fins_config_into_compose` (line 1028-1107): 已在 2c 中详细分析。覆盖了:
- config overlay + ConfigLoader + discover_service_tools 完整链路
- 运行时注入的 workspace_root 进入 effective_provider_configs
- raw config 污染后 compose 仍使用 effective config
- wait_adapter_registry 构造成功

### 3c. Search provider hard/diagnostic 边界

| 测试 | 覆盖 |
|------|------|
| `test_search_http_status_classifier` (parametrized: 401,403,429,500) | HTTP 状态码 → bucket 映射: auth_failure, quota/rate-limit, unavailable |
| `test_search_error_text_classifier` (parametrized: 8 cases) | 错误文本 + provider + api_key_present → bucket, 覆盖 key_missing, auth, quota, network, parse, unavailable, execution_error |
| `test_single_search_provider_case_reports_loader_failure` | ConfigLoader 失败 → hard failure, exit_code=2, bucket=web_config_loader_failure |
| `test_single_search_provider_case_reports_discovery_failure` | discovery 失败 → hard failure, exit_code=2, bucket=web_assembly_discovery_failure |
| `test_single_search_provider_case_classifies_callable_timeout` | callable timeout → diagnostic-only, exit_code=0, bucket=provider_network_failure |
| `test_single_search_provider_case_classifies_empty_results` | 成功但空结果 → diagnostic-only, exit_code=0, bucket=provider_no_results |
| `test_search_provider_cases_are_typed_diagnostic_only` | typed search_cases 不混入 external_cases, Tavily key missing → provider_key_missing, artifact 不含 secret 值 |

**覆盖评估**: hard 边界（ConfigLoader/discovery 失败 → non-zero exit_code）与 diagnostic 边界（外部 provider 失败 → exit_code=0）均被覆盖。HTTP 状态码分类与错误文本分类均为参数化测试，覆盖关键枚举值。

### 3. 综合结论

新增测试覆盖满足需求: Fins workspace-bound provider 边界的 OR 匹配路径全覆盖, discovery→compose 链有端到端集成测试, search provider hard/diagnostic 边界有参数化分类测试与 fail-fast 测试。

---

## 4. 新的 correctness/type/layering 问题检查

### 4a. Correctness

无新 correctness 问题。已发现的已知接受项:

- `_effective_tool_provider_configs:865` 的 identity 比较 (`effective_config is provider_config.config`) — Controller 拒绝修复, 风险微小（两函数为同模块私有 helper）
- `_classify_search_error_text` 中文错误文本 heuristic — Controller 拒绝修复, 作为 secondary classifier 可接受

### 4b. Type Safety

- `host_assembly.py` 全部新增函数有完整类型标注: `_effective_tool_provider_config` → `Mapping[str, JsonValue]`, `_effective_tool_provider_configs` → `tuple[ToolDiscoveryProviderConfig, ...]`, `_is_fins_workspace_bound_provider_config` → `bool`
- `ServiceDiscoveredTools.effective_provider_configs: tuple[ToolDiscoveryProviderConfig, ...]` 有明确类型
- `test_smoke_web_ci.py:163` `discovered_configs: list[smoke.RuntimeConfig]` — 已从 `list[object]` 修正
- pyright: 0 errors, 0 warnings

### 4c. Layering

- `host_assembly.py` 依赖 `dayu.runtime.*` / `dayu.host.*` / `dayu.fins.ingestion` / `dayu.engine.*` / `dayu.contracts.*` — Service 层允许向下的 Host/Engine/runtime contracts 依赖, 不依赖 UI, 不修改 Host public API
- `dayu.runtime` 无新增 import 上层模块
- 测试文件分层正确: Service assembly 测试在 `tests/service/`, smoke 测试在 `tests/tools/web/`

### 4d. 回归检查

| 检查项 | 结论 |
|--------|------|
| Search assembly failure 不被吞 | 通过 — `hard_gate_cases = local_cases + search_cases` |
| External URL cases 在 blocker 分支跳过 | 通过 — `external_cases=()` |
| Secret 泄漏 | 通过 — artifact 只写 `api_key_env`/`api_key_present`, 不写值 |
| pyright 无新增报错 | 通过 — 0 errors, 0 warnings |
| pytest 确定性测试 | 通过 — 77 passed, 3 warnings (均来自 edgar 依赖) |
| Git diff --check | 通过 — 已在 fix gate 中验证 |
| 分层约束 | 通过 — 无 `dayu.runtime` 向上 import, 无 Service import UI |

### 4. 综合结论

无新的 correctness/type/layering 问题。

---

## 总体结论

| 审查维度 | 结论 |
|----------|------|
| 1. Controller DS F1 裁决 | **成立** — 代码证据充分, ToolDiscovery → ScenePrepare → Host 三层过滤确保 `enabled:true` 不绕过 per-run 工具选择, `allow_empty` 不吞 import failure |
| 2. effective_provider_configs compose 链 | **正确** — discovery 阶段 effective config 进入 `ServiceDiscoveredTools`, compose 阶段复用, Fins wait adapter registry 不再独立重算, 有集成测试证明 raw config 污染不会影响 compose |
| 3. 新增测试覆盖 | **充分** — Fins workspace-bound provider 5 边界, discovery→compose 端到端链路, search provider 7 项 hard/diagnostic 边界 + 2 参数化分类器 |
| 4. 新的 correctness/type/layering 问题 | **无** — pyright 0/0, pytest 77 passed, 分层未违反, 无 secret 泄漏 |

**Verdict: pass** — effective spec follow-up fix 正确实施, Controller 裁决基于代码证据成立, compose 链一致性得到保证, 测试覆盖充分, 无新问题引入。

---

*本 artifact 仅审查不变更代码。*
