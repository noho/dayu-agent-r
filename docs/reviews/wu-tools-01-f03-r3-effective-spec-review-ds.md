# WU-TOOLS-01-F03-R3 Effective Spec Assembly — Code Review (DS)

**范围**: 当前 workspace 未提交改动，聚焦 `dayu/service/host_assembly.py` effective provider config、Fins workspace_root 注入、wait adapter registry 一致性及周边文件。

**日期**: 2026-06-10

**审查人**: DS (DeepSeek)

---

## 概览

本次变更的核心目的是让 `discover_service_tools` / `compose_open_host_options` 能在 Fins provider 未显式配置 `workspace_root` 时，从运行时参数补齐 workspace root，并确保 tool discovery spec 与 wait adapter registry 使用同一套 effective config。

改动涉及 15 个文件，+2060 / -48 行。生产代码变更集中在 `host_assembly.py`（+110 行新增函数），测试新增 4 个用例、所有已有调用点更新签名。

---

## Findings

### F1 [HIGH · Correctness] 包级 `web-tools` 默认 `enabled: true` 变更所有场景默认工具暴露面

**文件**: `dayu/config/tool_discovery.json`

**问题**:
```json
- "enabled": false,
+ "enabled": true,
- "allow_empty": true,
+ "allow_empty": true,
```

web-tools provider 从 `enabled: false` 改为 `enabled: true`。由于 `allow_empty: true`，若 import path 不可解析，provider 被静默跳过——但若模块可导入，`search_web` / `fetch_web_page` 会进入所有未显式过滤工具列表的 scene 的工具目录。

**风险**:
1. 所有 scene 的 LLM 突然获得搜索和网页获取工具，可能改变行为。
2. `allow_empty: true` 意味着 import 失败时不报错，工具静默消失——运维无法察觉。
3. `search_web` / `fetch_web_page` 会产生网络出站请求和 provider API 调用，对无网络环境或未配置 API key 的场景可能有副作用。

**建议**: 评估是否应将这个变更作为独立 PR，还是至少与 scene tool_selection 默认过滤策略同步变更。如果默认启用是预期行为，需要 release note 明确说明。

---

### F2 [MEDIUM · Test Gap] `_is_fins_workspace_bound_provider_config` 无直接边界测试

**文件**: `dayu/service/host_assembly.py:870-886`, `tests/service/test_host_assembly.py`

**问题**: 新增函数 `_is_fins_workspace_bound_provider_config` 的匹配逻辑为 OR 型多字段匹配：
```python
if (
    provider_config.provider_id in _FINS_READ_PROVIDER_IDS
    or provider_config.import_path in _FINS_READ_IMPORT_PATHS
    or provider_config.source_id in _FINS_READ_SOURCE_IDS
):
    return True
return _fins_awaiting_tool_name_from_provider_config(provider_config) is not None
```

直接测试仅通过 `test_fins_tool_discovery_spec_injects_runtime_workspace_root` 和 `test_fins_tool_discovery_spec_preserves_explicit_workspace_root` 间接覆盖 happy path。缺失的边界测试：

1. **非 Fins provider 应返回 False** — 不测试的话，某天若常量集被污染，所有 provider 都被误判为 workspace-bound 而不会触发测试失败。
2. **部分字段匹配的交叉场景** — 例如 `provider_id` 匹配 download 但 `source_id` 为空，函数依赖 `_fins_awaiting_tool_name_from_provider_config` 的 OR 逻辑回退，路径正确性无直接验证。
3. **read provider 的 source_id 匹配** — `_FINS_READ_SOURCE_IDS` 检查 `{"dayu.fins.tools.provider"}`，当 provider 使用 entry_point 而非 import_path 时，此常量未被 `_fins_awaiting_tool_name_from_provider_config` 中的任何分支检查，仅 `_is_fins_workspace_bound_provider_config` 中的显式 `_FINS_READ_SOURCE_IDS` 捕获——但无测试证明这一点。

**建议**: 新增参数化测试覆盖：非 Fins provider（返回 False）、read provider（返回 True）、download/preprocess/upload provider（返回 True）、仅 entry_point 匹配的 provider、部分字段冲突的 provider。

---

### F3 [MEDIUM · Correctness / Architecture] `discover_service_tools` 不传 `workspace_root` 时 Fins provider 错误延迟到 `compose_open_host_options` 才暴露

**文件**: `dayu/service/host_assembly.py:269-302, 844-867`

**问题**: 调用链为:
1. `discover_service_tools(config)` — 不传 `workspace_root`，`_effective_tool_provider_config` 检测到 `workspace_root is None` → 不注入，返回原始 config（含 `workspace_root: None`）。
2. `compose_open_host_options(request)` — `_effective_tool_provider_configs` 检测到 `request.workspace_root` 有值 → 注入 workspace_root。
3. `_fins_wait_adapter_registry_from_provider_configs` → `_fins_workspace_root_from_provider_config` 取 config 中的 `workspace_root`。

当调用方：
- 步骤 1 不传 `workspace_root`
- 步骤 2 传 `request.workspace_root`

工具发现成功（因为 Fins read tools 可能容忍 `workspace_root=None` 并在运行时懒检查），但 wait adapter registry 在步骤 2 获得正确 workspace_root。这是目前**正确**的，因为 Service assembly 的调用者（如 `smoke_web_ci.py` 的 `_discover_tools_by_name`）只做步骤 1，不做步骤 2。

但若未来有调用者：
- 步骤 1 传 `workspace_root=tmp_path`
- 步骤 2 传 `request.workspace_root=prod_path`（不同值）

则 tool discovery spec 和 wait adapter registry 的 effective config 中 `workspace_root` 不一致。

**这是一个设计层面的一致性缺口**: `_effective_tool_provider_config` 被两个路径独立调用，输入值 (`workspace_root`) 依赖调用者自主保持一致，无编译期或运行时的一致性检查。

**建议**: 在 `compose_open_host_options` 中比较 `request.discovered_tools` 产生时使用的 workspace_root 与 `request.workspace_root`（可通过 `ServiceDiscoveredTools` 增加一个可选字段），若不一致则 fail fast。或者考虑把 effective config 从 `discover_service_tools` 的输出上抛给 `compose_open_host_options` 复用。

---

### F4 [MEDIUM · Test Gap] `compose_open_host_options` 路径缺少 "workspace_root 不传→Fins provider 缺少→compose 时失败" 的测试

**文件**: `tests/service/test_host_assembly.py`

**问题**: 现有测试 `test_fins_tool_discovery_spec_injects_runtime_workspace_root` 测试了 _tool_discovery_specs 层注入。`test_fins_awaiting_provider_missing_workspace_root_fails_before_open_host` 测试了 await adapter registry 层缺少 workspace_root 时 fail fast——但两个测试是独立路径。

缺少的端到端测试：完整的 `discover_service_tools → compose_open_host_options` 链路，其中 Fins awaiting provider 在 tool discovery 层使用了运行时注入的 workspace_root，然后在 compose 层到 wait adapter registry 也使用同一值。当前这个链路在测试中只被 smoke 脚本间接覆盖（非自动化）。

**建议**: 新增一个集成测试：在临时 workspace 中写入 Fins download provider overlay（无显式 workspace_root），调用 `discover_service_tools(config, workspace_root=tmp_path)` 发现工具，然后调用 `compose_open_host_options` 验证 `tooling_options.wait_adapter_registry` 不为 None 且 adapter key 正确。

---

### F5 [LOW · Type Safety] `_effective_tool_provider_configs` 依赖 identity 比较判定是否替换

**文件**: `dayu/service/host_assembly.py:857-867`

**问题**:
```python
if effective_config is provider_config.config:
    effective_configs.append(provider_config)
else:
    effective_configs.append(replace(provider_config, config=effective_config))
```

`effective_config is provider_config.config` 用 `is` (identity) 而非 `==` (value equality) 判断是否需要替换。未来若有人重构 `_effective_tool_provider_config` 使其即使无变更也返回新 dict（如防御性拷贝），此处的 identity 比较会永远为 False，导致无意义地创建大量 dataclass replace。

**当前状态**: 函数正确返回原始引用（无变更时）或新 dict（注入时），identity 比较准确。但这构成了两个私有函数之间的隐式约定，无法通过类型系统约束。

**建议**: 考虑在 `_effective_tool_provider_config` 的返回值中增加一个布尔标记 `injected: bool` 或返回 `tuple[Mapping, bool]`，显式传递"是否做了注入"信号。或者在 `_effective_tool_provider_configs` 中用 `==` 比较（对 Mapping[str, JsonValue] 代价可接受）。风险极小，仅标记以备未来重构。

---

### F6 [LOW · Maintainability] `test_config_loader_and_service_discover_web_tools_with_overlay_config` 耦合 Service assembly 测试到 Web 工具实现

**文件**: `tests/service/test_host_assembly.py:952-999`

**问题**:
```python
assert tool_names == ("search_web", "fetch_web_page")
assert discovered_tools.provider_reports == (
    "provider=web-tools,spec=web-tools,version=web-tools-provider-v1,tools=search_web,fetch_web_page",
)
```

这个测试在 `tests/service/` 下，却断言了 `dayu.tools.web` 模块导出的具体工具名和版本信息。如果 Web 工具改版（新增/删除工具、改版本号），这个 Service assembly 层的测试也会失败，即使 Assembly 本身逻辑完全正确。

**建议**: 将版本引用和具体工具名的断言移到 `tests/tools/web/` 下。在 Service assembly 测试中只断言 "至少有一个工具被发现" 和 "没有 Service 层错误"。或者保留此测试但明确注释其集成测试属性。

---

### F7 [LOW · Test Gap] `smoke_web_ci.py` 新增的搜索引擎诊断函数缺少关键边界测试

**文件**: `utils/smoke_web_ci.py`, `tests/tools/web/test_smoke_web_ci.py`

**问题**:
- `_classify_search_http_status`：无直接测试（如 401→auth_failure, 429→quota, 500→unavailable 等）。
- `_classify_search_error_text`：无直接测试（如多语言错误文本、"api_key 未配置" 匹配等）。
- `_run_search_provider_cases`：端到端测试通过 monkeypatch 覆盖了 happy path 和 failed outcome 路径，但未覆盖 ConfigLoader 异常、`discover_service_tools` 异常、`asyncio.run` 抛异常、ToolCompletedOutcome 但 `result_total == 0` 等分支。

现有 `test_search_provider_cases_are_typed_diagnostic_only` 只覆盖了 successful outcome 和 failed outcome 两个分支，未覆盖异常路径。对于分类函数（`_classify_*`），建议参数化测试覆盖所有枚举 HTTP 状态码和错误文本模式。

---

## 已验证为正确的设计点

以下关键路径经逐行确认，无问题：

1. **Effective config 一致性**: `_tool_discovery_specs` 与 `_effective_tool_provider_configs` 都调用 `_effective_tool_provider_config()` 生成 effective config，算法一致，当输入 `workspace_root` 相同时输出相同。两个路径不可互相看到对方的计算结果，但计算结果一致。✓

2. **Wait adapter registry 使用 effective config**: `_compose_options` → `_tooling_options_from_discovery` → `_fins_wait_adapter_registry_from_provider_configs` 接收的是 `_effective_tool_provider_configs` 的输出（已注入 workspace_root），最终从 `provider_config.config["workspace_root"]` 取值。✓

3. **Read tools 非 awaiting 的正确区分**: `_is_fins_workspace_bound_provider_config` 显式检查 fins-read-tools（需要 workspace_root 做文件读取，但不绑定 wait adapter），而 `_fins_awaiting_tool_name_from_provider_config` 只检查 download/preprocess/upload（需要 wait adapter）。两者的匹配常量和代码路径无重叠和遗漏。✓

4. **Raw config 不被污染**: `_effective_tool_provider_config` 在需要注入时创建新 `dict`，不修改 `provider_config.config` 原值。`test_fins_tool_discovery_spec_preserves_explicit_workspace_root` 验证了显式配置不被覆盖。✓

5. **向后兼容**: `workspace_root` 参数有默认值 `None`，不传时行为不变。3 个 smoke 脚本全部更新传递 workspace_root。✓

6. **类型安全**: 所有新增函数有完整类型标注，无 `Any`、无裸 `dict` 返回、无 unsafe cast。`JsonValue` 导入已添加。✓

---

## 结论

核心架构决策（effective config 在 tool discovery 和 wait adapter registry 双路径注入）正确。主要风险点是：

| 严重度 | 数量 | 关键发现 |
|--------|------|---------|
| HIGH | 1 | web-tools 默认 `enabled: true` 改变所有场景默认行为 |
| MEDIUM | 3 | 边界测试缺失、effective config 无一致性防护、延迟错误暴露 |
| LOW | 3 | 类型脆弱性、测试耦合、烟测分类函数无直接测试 |

F2/F3 建议在后续 PR 中补齐测试和一致性校验。F1 需确认是否为预期行为，如是则需要 release note。其余为维护改进，不阻塞合入。

---

*本 artifact 仅审查不变更代码。*
