# Code Review — WU-CLI-SMOKE-01 util time + tag-only selection

## Scope

- Mode: current changes (unstaged + untracked)
- Branch: `phase/host-issues-control`
- Base: `main` (committed changes on this branch already reviewed in prior artifacts)
- Output file: `docs/reviews/wu-cli-smoke-01-util-time-tag-selection-review-ds.md`
- Included scope:
  - `dayu/tools/utils/` (新增 provider + `__init__`)
  - `dayu/config/tool_discovery.json` (新增 `utils-tools` provider 默认启用)
  - `dayu/config/prompts/base/tools.md` (`get_current_time` 指引更新)
  - `dayu/config/prompts/manifests/*.json` (10 个 packaged scene manifest 改为 tag-only `tool_selection`)
  - `dayu/fins/tools/fins_tools.py` (`FINS_TOOL_TAGS` 增加 `fins-read`)
  - `dayu/config/README.md`、`dayu/fins/README.md` (文档更新)
  - `tests/tools/test_utils_tools_provider.py` (新增)
  - `tests/tools/test_combined_tools_acceptance.py` (扩展)
  - `tests/runtime/test_scene_assets_migration.py` (扩展)
  - `tests/service/test_entrypoint_runtime_prompt_path.py` (扩展)
  - `tests/service/test_entrypoint_runtime_interactive_path.py` (扩展)
  - `tests/cli/test_prompt_command.py` (扩展)
  - `tests/fins/test_fins_storage_provider.py` (扩展)
  - `tests/runtime/test_config_loader.py` (扩展)
- Excluded scope: committed changes on `phase/host-issues-control` (prior WU-CLI-SMOKE-01 slices，已在之前的 review artifacts 中覆盖)；`__pycache__/` 目录
- Parallel review coverage: 无（单 reviewer 全量走读）
- Design sources of truth: `docs/host/design.md`、`docs/engine/design.md`
- Implementation artifact: `docs/reviews/wu-cli-smoke-01-util-time-tag-selection-implementation-codex.md`

## Findings

### 1-未修复-中-infer.json manifest tag-only 迁移丢失 fins-download 和 fins-preprocess 工具

- **入口/函数**: `dayu/config/prompts/manifests/infer.json` `tool_selection.tool_tags_any`
- **文件(行号)**: `dayu/config/prompts/manifests/infer.json:19-23`
- **输入场景**: 使用 `infer` scene（公司业务类型与关键约束判断场景）运行 prompt 时，模型需要下载或预处理财报文档。
- **实际分支**: 新 manifest `tool_tags_any` 仅为 `["fins-read", "utils"]`，未包含 `fins-download` 或 `fins-preprocess`。
- **预期行为**: 旧 manifest 的 `tool_names` 显式包含 `start_fins_download` 和 `start_fins_preprocess`（见 diff `infer.json` 删除行），infer scene 原可调用下载和预处理工具。若 tag-only 迁移应保持等价工具暴露面，则应包含 `fins-download` 和 `fins-preprocess` tags。
- **实际行为**: `ScenePrepare._select_tools` 通过 `catalog.names_for_any_tag({"fins-read", "utils"})` 选择工具，结果不包含 `start_fins_download`（tag=`fins-download`）和 `start_fins_preprocess`（tag=`fins-preprocess`）。infer scene 的模型将无法发起下载或预处理操作。
- **直接证据**:
  - 旧 `infer.json` 的 `tool_names` 包含 `start_fins_download`、`start_fins_preprocess`（见 `git diff -- dayu/config/prompts/manifests/infer.json` 删除行）
  - 新 `infer.json` 的 `tool_tags_any` 仅为 `["fins-read", "utils"]`，不含 `fins-download`、`fins-preprocess`
  - 其他 9 个 scene manifest（prompt/interactive/confirm/decision/fix/regenerate/repair/wechat/write）的 `tool_tags_any` 均为 `["fins-read", "fins-download", "fins-preprocess", "web", "utils"]`，只有 infer 例外
  - `download_tools.py:179` — `tags=("fins", "fins-download")`
  - `preprocess_tools.py:177` — `tags=("fins", "fins-preprocess")`
- **影响**: 若 infer scene 需要下载或预处理财报文档（例如判断公司业务类型前需先下载财报），模型将无法调用这些工具；可能通过 fins-read 间接解决，但不等价于旧行为。
- **建议改法和验证点**:
  1. 确认 infer scene 的设计意图：是否为纯只读判断场景，不需要下载/预处理能力。
  2. 若应保持旧暴露面：在 infer.json 的 `tool_tags_any` 中增加 `"fins-download"` 和 `"fins-preprocess"`。
  3. 若有意缩小暴露面：在设计文档或 commit message 中记录该决策，并验证 infer scene 的 prompt fragment 不会引导模型使用下载/预处理工具。
- **修复风险（低）**: 仅改一个 JSON 数组，不涉及代码逻辑。
- **严重程度（中）**: 行为变更，可能影响 infer scene 的工具可用性；但 infer scene 描述为"判断场景"，纯只读可能是有意设计。

### 2-未修复-低-_timezone_argument 对非字符串类型值产生不精确的错误消息

- **入口/函数**: `_timezone_argument` → `get_current_time`
- **文件(行号)**: `dayu/tools/utils/provider.py:158-170`（`_timezone_argument`），`dayu/tools/utils/provider.py:98-103`（调用点）
- **输入场景**: LLM 因 schema 理解偏差传入非字符串类型 timezone（例如 `{"timezone": 8}` 或 `{"timezone": ["Asia/Shanghai"]}`），虽然 schema 声明了 `"type": "string"` 和 `"enum": ["Asia/Shanghai"]`，但 LLM 偶尔会违反 schema。
- **实际分支**: `isinstance(value, str)` 为 False → 返回 `""` → `"" not in _SUPPORTED_TIMEZONES` → 进入 `_failed_outcome` 分支，错误消息为 `"不支持的时区: ，当前仅支持 Asia/Shanghai。"`（`{timezone}` 展开为空字符串）。
- **预期行为**: 错误消息应区分"类型错误"与"不支持的时区值"。当前 "不支持的时区: " 后接空字符串，对 LLM 可读性差且不提示正确修复方向。
- **实际行为**: 返回 `ToolFailedOutcome`，`error="invalid_argument"`，`message` 中 timezone 部分为空字符串，`hint` 仍为 `"timezone 只能省略或填写 Asia/Shanghai；不要使用其它时区名称。"`。hint 对非字符串类型同样适用，但 message 的前半段缺失关键信息。
- **直接证据**: `provider.py:163-164` — `isinstance(value, str)` 返回 False 时直接 `return ""`；`provider.py:98-100` — `timezone not in _SUPPORTED_TIMEZONES` 对 `""` 为 True，message f-string 中 `{timezone}` 展开为 `""`。
- **影响**: LLM 收到 `"不支持的时区: "` 后空字符串可能困惑，但 hint 仍提供正确指导；不影响系统正确性。
- **建议改法和验证点**: 在 `_timezone_argument` 中区分 `None`/缺省、非字符串类型、空字符串三种情况，对非字符串类型返回专用错误标识（例如 `_ERROR_INVALID_ARGUMENT_TYPE`）并在 message 中明确说明"timezone 参数必须为字符串"。
- **修复风险（低）**: 仅改 helper 函数和错误消息字符串。
- **严重程度（低）**: 不影响正确性，LLM 仍能通过 hint 恢复；边缘情况，LLM 违反 schema 的概率低。

## 架构边界合规检查

以下逐项按用户指定的五个重点检查维度报告：

### 1. Engine 不拥有工具注册、ToolsDiscovery provider 显式发现

- **通过**。`dayu.tools.utils.provider` 不 import `dayu.engine`、`dayu.host`、`dayu.service`、`dayu.ui`。
- `discover_tools` 是标准 `ToolsDiscoveryProviderSpec → ToolsDiscoveryProviderOutput` callable，由 `dayu/config/tool_discovery.json` 中 `"utils-tools"` provider 的 `import_path: "dayu.tools.utils:discover_tools"` 显式声明并默认启用。
- `dayu.runtime.tools_discovery` 的 `ToolsDiscovery` 负责 import provider callable、调用 `discover_tools(spec)`、聚合 `ToolBundle` 和计算 digest。边界与 `docs/host/design.md:71` 和 `docs/engine/design.md:3` 一致。

### 2. get_current_time callable 参数校验、ToolCompletedOutcome/ToolFailedOutcome、JSON value 类型、LLM-facing schema/description

- **通过**。参数校验链：`_timezone_argument` 读 `call.arguments` → None 时默认 `DEFAULT_TIMEZONE` → 非字符串返回 `""`（见 Finding 2）→ 不在 `_SUPPORTED_TIMEZONES` 时返回 `ToolFailedOutcome(error="invalid_argument")`。
- 成功路径返回 `ToolCompletedOutcome`，`result.value` 为 `dict[str, JsonValue]`，字段 `time`（str）、`timezone`（str）、`weekday`（str）、`iso`（str），均为合法 `JsonValue`。
- LLM-facing schema（`_get_current_time_parameters`）：`type: "object"`，`properties.timezone` 声明 `type: "string"`、`enum: ["Asia/Shanghai"]`、`default: "Asia/Shanghai"`，`required: ()`，`additionalProperties: false`。所有字段自足说明，不引用内部类型名。
- `@tool` description: `"获取当前日期和时间。仅支持 timezone=Asia/Shanghai；返回 time、timezone、weekday、iso。"` — 自足说明动作、参数约束和返回字段。
- `base/tools.md` 的 `<when_tool get_current_time>` 指引与真实工具一致：用途、参数、返回字段、禁止用途均在 LLM-facing 文本中自足说明。

### 3. tag-only manifests 保持原默认工具暴露面

- **通过**（除 Finding 1 中 `infer.json` 的行为变更需确认）。
- 9 个 scene（prompt/interactive/confirm/decision/fix/regenerate/repair/wechat/write）的 `tool_tags_any` 为 `["fins-read", "fins-download", "fins-preprocess", "web", "utils"]`。对照旧 `tool_names`：
  - 旧 9 个 Fins read tools → `fins-read` tag（`FINS_TOOL_TAGS = ("fins", "fins-read")`）✓
  - `start_fins_download` → `fins-download` tag（`download_tools.py:179`）✓
  - `start_fins_preprocess` → `fins-preprocess` tag（`preprocess_tools.py:177`）✓
  - `search_web`、`fetch_web_page` → `web` tag（web provider）✓
  - `get_current_time` → `utils` tag（`provider.py` 中 `UTILS_TOOL_TAG = "utils"`）✓（新增）
- `start_fins_upload` 不会被选中：`upload_tools.py:167` tags=`("fins", "fins-upload")`，所有 manifest 的 `tool_tags_any` 均不含 `fins-upload`，也没有使用 broad `fins` tag。✓
- `conversation_compaction.json` 使用 `mode: "none"`，不受影响。✓
- `ScenePrepare._select_tools`（`scene_prepare.py:1080-1106`）正确联合 `tool_names` 和 `tool_tags_any` 的结果，公共代码语义未修改。workspace 自定义 scene 仍可使用 `tool_names`。✓

### 4. 测试覆盖

- **通过**。测试覆盖了完整链路：
  - Provider 层：`test_utils_tools_provider.py` — discovery、成功执行、失败执行（3 个测试）
  - Combined discovery：`test_combined_tools_acceptance.py` — 验证 utils 工具进入 combined bundle、source_refs 计数更新、scene prepare tag 选择（含 upload 排除断言）
  - Scene assets migration：`test_scene_assets_migration.py` — `_fake_tool_catalog` 更新为新 tag 体系、新增 `test_packaged_select_manifests_use_tag_only_tool_selection` 结构性断言
  - Config loader：`test_config_loader.py` — 验证 `utils-tools` provider 正确加载
  - Service entrypoint：`test_entrypoint_runtime_prompt_path.py` / `test_entrypoint_runtime_interactive_path.py` — 验证真实 manifest 装配后 `tool_names` 包含 `get_current_time`、排除 `start_fins_upload`
  - CLI：`test_prompt_command.py` — 验证 `submit_request.tool_names` 包含 `get_current_time`、排除 `start_fins_upload`
  - Fins：`test_fins_storage_provider.py` — 验证 read tools 同时具有 `fins` 和 `fins-read` tags
- 未削弱的断言：
  - `test_packaged_select_manifests_use_tag_only_tool_selection` 对每个 select manifest 断言 `tool_names == []` 且 `tool_tags_any` 非空 — 防止回退到显式工具名。
  - entrypoint 和 CLI 测试新增 `assert _EXCLUDED_UPLOAD_TOOL_NAME not in ...` — 精确验证 upload 排除。
  - `test_scene_prepare_tags_select_doc_fins_web_and_utils_tools` 新增 `assert "start_fins_upload" not in selected` — 精确验证 tag 选择不泄露 upload。
- 缺失覆盖（记录为 Residual Risk）：
  - `_timezone_argument` 的非字符串输入路径无直接测试。
  - `get_current_time` 以 `timezone="Asia/Shanghai"` 显式传入的成功路径无测试（当前只测了空参数）。
  - 没有针对 `infer` manifest 工具选择的专项 entrypoint 测试（无法在 CI 中捕获 Finding 1）。

### 5. README/LLM-facing 文本

- **通过**。`dayu/config/README.md` 更新了 `utils-tools` provider 说明和 scene manifest tool_selection 语义描述。`dayu/fins/README.md` 更新了 Fins workspace 规则中的标签选择说明。两处变更均为事实性更新，与代码行为一致。
- `base/tools.md` 的 `get_current_time` 指引符合 LLM-facing 文本约束：不引用内部模块名；在 prompt 内自足说明参数、返回字段和禁止用途。

## Open Questions

1. **infer.json 的下载/预处理工具移除是否为有意设计？** 旧 manifest 包含 `start_fins_download` 和 `start_fins_preprocess`，新 manifest 仅 `fins-read` + `utils`。infer scene 描述为"公司业务类型与关键约束判断场景"，纯只读判断可能合理，但需确认设计意图。其他 9 个 scene 均保留了 download/preprocess 标签。
2. **是否需要为 `conversation_compaction.json` 验证其 `mode: "none"` 不受 tag-only 迁移影响？** 当前已验证 `mode: "none"` 且 `_select_tools` 对其直接返回空集（`scene_prepare.py:1091-1094`），但 `test_packaged_select_manifests_use_tag_only_tool_selection` 只检查 `mode == "select"` 的 manifest，未显式断言 compaction manifest 的 mode 仍为 `"none"`。

## Residual Risk

1. **`_timezone_argument` 非字符串路径无测试**：当前 `test_get_current_time_rejects_unsupported_timezone` 只测了 `"UTC"`（合法字符串但不受支持），未覆盖非字符串类型（int、list、dict）的输入。风险低，因为 schema 的 `"type": "string"` 约束已向 LLM 声明。
2. **`get_current_time` 显式传入 `"Asia/Shanghai"` 的成功路径无测试**：当前成功测试只传空 `{}`。风险低，因为 `_timezone_argument` 对 `"Asia/Shanghai"` 和 `None`/缺省走同一成功路径，且 `_SUPPORTED_TIMEZONES` 检查覆盖了值域验证。
3. **infer scene 无专项 entrypoint 测试**：CI 中没有针对 infer scene 的 entrypoint 测试来验证工具选择结果。其他 scene（prompt、interactive）有 entrypoint 测试。风险低，但若 Finding 1 确认为非有意行为变更，需补齐。
4. **`ZoneInfoNotFoundError` catch 在当前实现中是防御性死代码**：`_SUPPORTED_TIMEZONES` 检查确保只有 `"Asia/Shanghai"` 能到达 `ZoneInfo(timezone)` 调用行；仅在系统缺少 IANA 时区数据时可能触发。风险极低，作为防御代码可保留。
5. **测试 `_FakeSearchWebCallable` 重构**：`test_combined_tools_acceptance.py` 将原来基于 `monkeypatch` 的 web tool fake 替换为 `@dataclass` + `_with_fake_search_web` helper，不再依赖 `monkeypatch.setattr`。该重构将 web search fake 从模块级函数替换内联为 bundle 级 `ToolDefinition` 替换，使测试更自足且不依赖全局模块状态。风险低，测试断言未削弱（`search_calls` 参数记录和 `search_tokens` 记录语义一致）。

## 验证

以下由实现 artifact 记录的验证结果（未在本 review 中重新执行）：

- `pytest tests/tools/test_utils_tools_provider.py tests/tools/test_combined_tools_acceptance.py tests/runtime/test_scene_assets_migration.py tests/runtime/test_config_loader.py tests/runtime/test_scene_tool_selection.py tests/service/test_entrypoint_runtime_prompt_path.py tests/service/test_entrypoint_runtime_interactive_path.py tests/cli/test_prompt_command.py tests/fins/test_fins_storage_provider.py -q` → `156 passed`
- `python -m pyright dayu/ tests/ utils/` → `0 errors, 0 warnings, 0 informations`
- 真实 CLI smoke（`dayu-cli prompt --ticker AAPL "等待10秒后输出现在是什么时间"`）→ 通过了完整工具调用闭环
- `git diff --check` → passed
