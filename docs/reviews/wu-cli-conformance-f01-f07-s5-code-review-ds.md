# Code Review — S5/F05: interactive fins-preprocess tag 移除

## Scope

- **Mode**: current changes (uncommitted)
- **Branch**: `codex/interactive-oracle`
- **Base**: `c556df2b`
- **Output file**: `docs/reviews/wu-cli-conformance-f01-f07-s5-code-review-ds.md`
- **Included scope**:
  - `dayu/config/prompts/manifests/interactive.json` — 唯一 production change
  - `tests/runtime/test_scene_assets_migration.py` — 拆分 interactive/wechat 断言
  - `tests/runtime/test_scene_prepare.py` — 新增 interactive 分支与 manifest 结构断言
  - `tests/service/test_entrypoint_runtime_interactive_path.py` — 更新端到端断言 + 新增全链路 schema 验证
  - `tests/tools/test_combined_tools_acceptance.py` — 新增 preprocess provider 独立 discoverable/callable 测试
- **Excluded scope**: 无 (所有 diff 文件均已审查)
- **Parallel review coverage**: 无 (scope 集中，单一 reviewer 逐文件走读)

## Verdict

**建议合入，未发现实质性问题。**

Production change 精确且最小：仅在 `interactive.json` 的 `tool_tags_any` 中删除 `"fins-preprocess"`，顺序 (`fins-read, fins-download, web, utils`) 与其余配置完全不变。全链路 manifest → discovery → Service → Host → Engine 验证通过：`start_fins_preprocess` 从 interactive effective schema 中正确排除，而 `download/list/read` 仍然存在。WeChat scene 未受影响，preprocess provider 与实现独立存活。4 个 test 文件的 diff 正确反映了新契约，7 个 focused tests 全部通过，pyright 零报错。

---

## Findings

未发现实质性问题。

---

## 验证证据链

### 1. 唯一 production change 验证

**diff**（`dayu/config/prompts/manifests/interactive.json`）:

```diff
     "tool_tags_any": [
       "fins-read",
       "fins-download",
-      "fins-preprocess",
       "web",
       "utils"
     ],
```

**验证结果**:
- 删除行数：1 行 (`"fins-preprocess",`)
- 其余字段完全不变：`schema_version`、`scene`、`version`、`description`、`capability_tags`、`extends`、`model`、`agent_policy`、`tool_selection.mode`、`tool_selection.tool_names`、`tool_selection.allow_empty`、`defaults`、`fragments`、`context_slots`
- `tool_tags_any` 顺序保持不变：`fins-read → fins-download → web → utils`（仅移除 `fins-preprocess`）
- 对比例证：`wechat.json:23` 仍保留 `"fins-preprocess"`

### 2. manifest → discovery → Service → Host → Engine 全链路验证

**链路追踪**:

| 环节 | 文件(行号) | 机制 | 证据 |
|---|---|---|---|
| Manifest 加载 | `scene_prepare.py:648-677` | `_load_manifest` → `_parse_manifest` → `_parse_tool_selection` | `tool_tags_any` 解析为 `frozenset({"fins-read", "fins-download", "web", "utils"})` |
| 工具选择 | `scene_prepare.py:1201-1227` | `_select_tools` → `catalog.names_for_any_tag(selection.tool_tags_any)` | 按 tag 交集匹配，`fins-preprocess` 不在请求标签中 → `start_fins_preprocess` 不被选中 |
| 输出 projection | `scene_prepare.py:458-469` | `PreparedSceneInputs.tool_selection.tool_names` | frozenset 不含 `start_fins_preprocess` |
| Service 传递 | `host_assembly.py:747-777` | `compose_submit_followup_request(tool_names=...)` | `tool_names` 作为 `SubmitFollowupRequest.tool_names` 传入 Host |
| Host 过滤 | `tool_runtime.py:2681-2704` | `_selected_business_definitions(bundle, selected_tool_names)` | 按 `selected_tool_names` 过滤 `ToolBundle.definitions` |
| Effective schema | `tool_runtime.py:2608-2610` | `definition.to_tool_schema()` | 过滤后的 definitions → `tool_schemas` → `AgentRunRequest.tool_schemas:102` |
| Engine 接收 | `agent_run.py:84,102` | `AgentRunRequest.tool_schemas` | LLM 可见的最终 schema 列表 |

**Host 层 tag-agnostic 确认**: 搜索 `dayu/host/` 下所有 `.py` 文件，`fins-preprocess` 和 `start_fins_preprocess` 命中次数为 0——Host 层不依赖任何工具 tag 或名称做过滤，完全由 ScenePrepare 输出的 `tool_names` frozenset 驱动。

### 3. interactive effective schema 内容验证

**端到端测试** `test_interactive_real_host_effective_schemas_exclude_preprocess`（`test_entrypoint_runtime_interactive_path.py:965-1000`）:

```python
schema_names = frozenset(
    schema.function.name for schema in worker_factory.requests[0].tool_schemas
)
assert _DEFAULT_PREPROCESS_TOOL_NAME not in schema_names
assert _DEFAULT_DOWNLOAD_TOOL_NAME in schema_names
assert _DEFAULT_LIST_TOOL_NAME in schema_names
assert _DEFAULT_READ_TOOL_NAME in schema_names
```

该测试经过真实 `CLI → Service → Host` 路径，`FinalAnswerWorkerFactory` 记录 `AgentRunRequest`（含 `tool_schemas`），断言直接验证 Engine 接收到的最终 schema：
- `start_fins_preprocess` **不在** schema 中
- `start_fins_download`、`list_documents`、`read_section` **在** schema 中

### 4. 测试非 mock name set 自证

**`test_scene_assets_migration.py:297-325`** — `_fake_tool_catalog()`:

```python
SceneToolInfo(name="start_fins_preprocess", tags=frozenset({"fins", "fins-preprocess"})),
```

测试使用 `SceneToolCatalog` + 真实 `SceneToolInfo`（含显式 tag），通过真实 `prepare_scene()` 函数驱动 tag → name 选择。断言验证的是 `selected`（tag 选择输出）和 `system_prompt`（条件块过滤输出），而非直接比对 mock name set。

**`test_scene_prepare.py:249-285`** — `_default_manifest_tool_catalog()`:

```python
SceneToolInfo(name=_START_FINS_PREPROCESS_TOOL_NAME, tags=frozenset({"fins", "fins-preprocess"})),
```

同上——工具 catalog 通过 tag 定义，prepare_scene 通过 tag 选择，断言验证选择结果。

**`test_entrypoint_runtime_interactive_path.py:965-1000`** — 端到端测试:

使用 `_RecordingHostOpener` 包装真实 `open_host()`，`FinalAnswerWorkerFactory` 记录真实 `AgentRunRequest.tool_schemas`。整个链路无 mock——manifest 从真实文件系统加载，discovery 使用真实 provider configs，Service/Host 使用真实 assembly 逻辑。

### 5. preprocess provider 独立性验证

**`test_combined_tools_acceptance.py:327-371`** — `test_preprocess_provider_remains_independently_discoverable_and_callable`:

```python
from dayu.fins.tools import preprocess_provider
...
output = preprocess_provider.discover_tools(ToolsDiscoveryProviderSpec(...))
assert tuple(definition.name for definition in output.definitions) == ("start_fins_preprocess",)
outcome = asyncio.run(output.definitions[0].callable(...))
assert isinstance(outcome, ToolAwaitingOutcome)
```

直接 import 并调用真实的 `preprocess_provider.discover_tools()`，验证：
- provider 仍返回 `start_fins_preprocess` 工具
- 工具 callable 可以正常调用并返回 `ToolAwaitingOutcome`

**实现文件存活确认**:
- `dayu/fins/tools/preprocess_provider.py` — 独立 provider，未被修改
- `dayu/fins/tools/preprocess_tools.py` — 工具实现，未被修改
- `dayu/fins/tools/preprocess_tools.py:172` — `tags=("fins", "fins-preprocess")`，tag 未变

**Service 层未删除 preprocess 支持**: `host_assembly.py:1498-1499`:

```python
if tool_name == FINS_PREPROCESS_AWAITING_TOOL_NAME:
    return build_fins_preprocess_tool(runtime)
```

### 6. WeChat scene 不受影响

**manifest 验证**: `wechat.json:20-26` — `tool_tags_any` 仍含 `"fins-preprocess"`

**测试验证**: `test_wechat_prepared_output_keeps_download_preprocess_guidance`（`test_scene_assets_migration.py:655-678`）:

```python
result = prepare_scene(ScenePrepareRequest(scene_id="wechat", ...))
assert "start_fins_preprocess" in selected
assert "start_fins_preprocess" in result.system_prompt
```

**其他 scene 验证**: `test_default_non_upload_scenes_do_not_select_upload_tool`（`test_scene_prepare.py:389-419`）对 10 个 scene 逐一验证——只有 `wechat` 和 `interactive` 有特殊分支，其余 scene 均不选中 download/preprocess。

### 7. 无下游按名称过滤、无实现删除

| 检查项 | 结果 |
|---|---|
| Host 层按 `start_fins_preprocess` 名称过滤 | 未发现——Host 层无任何 `fins-preprocess` 或 `start_fins_preprocess` 字符串引用 |
| Service 层按名称排除 preprocess provider | 未发现——`_active_fins_awaiting_provider_metadata` 按 `available_tool_names` 过滤，该集合来自 discovery 全量 bundle，preprocess 仍在其中 |
| preprocess 实现被删除 | 否——`preprocess_provider.py`、`preprocess_tools.py` 完整保留 |
| preprocess 工具定义被修改 | 否——tag `("fins", "fins-preprocess")` 未变 |

### 8. JSON/类型/测试断言脆弱性检查

**manifest 结构断言**（`test_scene_prepare.py:422-439`）:

```python
assert tool_selection == {
    "mode": "select",
    "tool_names": [],
    "tool_tags_any": ["fins-read", "fins-download", "web", "utils"],
    "allow_empty": False,
}
```

这是精确结构断言。其脆弱性可控：`ScenePrepare._parse_tool_selection` 通过 `_ALLOWED_TOOL_SELECTION_FIELDS`（`scene_prepare.py:72-74`）和 `_require_no_unknown_fields`（`scene_prepare.py:1384-1396`）对 manifest 做白名单校验，因此新增字段需要同步修改 parser 和测试——这是预期行为，非意外脆弱。

**条件块引用**（`test_scene_assets_migration.py:43`）:

```python
"<when_tool start_fins_preprocess>",
```

该常量 `_PREPARED_CONDITIONAL_MARKERS` 用于验证条件块 marker 不出现在渲染后的 system prompt 中。`start_fins_preprocess` marker 本身在 `base/tools.md:76` 中定义——如果该 fragment 被修改，测试会正确捕获。非脆弱。

**类型安全**: 所有测试新增代码使用 `frozenset`、`Final`、`cast` 等严格类型，pyright 零报错。

### 9. Focused tests 结果

```
tests/runtime/test_scene_assets_migration.py::test_interactive_prepared_output_keeps_download_without_preprocess_guidance PASSED
tests/runtime/test_scene_assets_migration.py::test_wechat_prepared_output_keeps_download_preprocess_guidance PASSED
tests/runtime/test_scene_prepare.py::test_default_non_upload_scenes_do_not_select_upload_tool PASSED
tests/runtime/test_scene_prepare.py::test_interactive_manifest_preserves_exact_non_preprocess_tool_selection PASSED
tests/service/test_entrypoint_runtime_interactive_path.py::test_interactive_runtime_uses_real_manifest_required_slots PASSED
tests/service/test_entrypoint_runtime_interactive_path.py::test_interactive_real_host_effective_schemas_exclude_preprocess PASSED
tests/tools/test_combined_tools_acceptance.py::test_preprocess_provider_remains_independently_discoverable_and_callable PASSED

7 passed in 1.30s
```

### 10. Pyright 结果

```
0 errors, 0 warnings, 0 informations
```

---

## Open Questions

无。

---

## Residual Risk

1. **preprocess awaiting 基础设施仍在运行**: `_active_fins_awaiting_provider_metadata`（`host_assembly.py:1336-1351`）按 discovery 全量 bundle 的 `available_tool_names` 过滤，preprocess provider 仍在 active set 中。wait poller 会为 `start_fins_preprocess` 注册 polling adapter，但 LLM 无法调用该工具（不在 effective schema 中），因此资源浪费但不产生错误行为。严重程度：低。

2. **`_DEFAULT_FINS_LONG_TRANSACTION_TOOL_NAMES` 常量语义过时**: `test_scene_prepare.py:50-55` 中该常量仍包含 `_START_FINS_PREPROCESS_TOOL_NAME`，但已不再描述 interactive scene 的"long transaction tools"。当前只在 wechat 分支使用（`test_scene_prepare.py:411`），语义上正确——但常量名暗示通用性，实际已变为 wechat-specific。建议后续重命名为 `_WECHAT_LONG_TRANSACTION_TOOL_NAMES` 或等效名称。严重程度：低（不影响正确性，仅影响可读性）。

3. **未覆盖的交互场景**: 若 interactive scene 中的 LLM 尝试使用 `read_section` 读取一个已下载但未预处理的新文档，行为取决于 `read_section` 对未预处理文档的处理方式——不在本次 change scope 内，属于已有产品行为。
