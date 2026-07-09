# Code Review

## Scope

- Mode: current changes
- Branch: phase/host-issues-control
- Base: main
- Output file: docs/reviews/wu-cli-smoke-01-util-time-tag-selection-review-mimo.md
- Included scope:
  - `dayu/tools/utils/` 新增 get_current_time ToolsDiscovery provider
  - `dayu/config/tool_discovery.json` 默认启用 utils-tools
  - `dayu/config/prompts/base/tools.md` get_current_time LLM-facing 指引
  - `dayu/config/prompts/manifests/*.json` packaged scene manifests 改为 tag-only tool_selection
  - `dayu/fins/tools/fins_tools.py` read tools 增加 fins-read 窄 tag
  - `dayu/config/README.md`、`dayu/fins/README.md` 更新
  - 相关 tests: test_utils_tools_provider, test_combined_tools_acceptance, test_scene_assets_migration, test_config_loader, test_entrypoint_runtime_prompt_path, test_entrypoint_runtime_interactive_path, test_prompt_command, test_fins_storage_provider
- Excluded scope: `dayu/runtime/scene_prepare.py`、`dayu/runtime/scene_tool_catalog.py` 公共代码语义未改，不在 review 修改范围
- Parallel review coverage: 无

## Findings

### 1-未修复-低-`_timezone_argument` 非字符串输入的错误消息不精确

- **入口/函数**: `_timezone_argument` (provider.py:182)
- **文件(行号)**: `dayu/tools/utils/provider.py:198-199`
- **输入场景**: LLM 传入 `timezone` 参数值为非字符串类型（如 int、bool、null）
- **实际分支**: `not isinstance(value, str)` 为 True，返回空字符串 `""`
- **预期行为**: 应返回能让下游 `_SUPPORTED_TIMEZONES` 校验产生清晰错误的值，或直接在此处产生精确错误
- **实际行为**: 返回空字符串 `""`，下游 `_SUPPORTED_TIMEZONES` 校验失败后产生 `"不支持的时区: ，当前仅支持 Asia/Shanghai。"`，错误消息中时区名为空，对 LLM 恢复提示不够清晰
- **直接证据**: provider.py:199 `return ""`，provider.py:130 `f"不支持的时区: {timezone}，当前仅支持 {DEFAULT_TIMEZONE}。"`
- **影响**: LLM 收到的错误消息中时区名为空，可能导致 LLM 重试时仍传入错误类型；不影响系统正确性，仅影响 LLM 恢复效率
- **建议改法和验证点**: 将非字符串输入的返回值改为 `"<non-string>"` 或类似可读占位符，使错误消息对 LLM 可操作；或在 `_timezone_argument` 中直接返回 `None` 并在调用方处理
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低

### 2-未修复-低-`ZoneInfoNotFoundError` 异常处理为不可达代码

- **入口/函数**: `get_current_time` callable (provider.py:105)
- **文件(行号)**: `dayu/tools/utils/provider.py:135-141`
- **输入场景**: 任何合法调用
- **实际分支**: `_SUPPORTED_TIMEZONES = frozenset({"Asia/Shanghai"})`，通过 L126 校验的 timezone 必定是 `"Asia/Shanghai"`；`ZoneInfo("Asia/Shanghai")` 不会抛出 `ZoneInfoNotFoundError`
- **预期行为**: 异常处理应覆盖真实可达的失败路径
- **实际行为**: `except ZoneInfoNotFoundError` 分支在当前实现下不可达
- **直接证据**: provider.py:49 `_SUPPORTED_TIMEZONES: Final[frozenset[str]] = frozenset({DEFAULT_TIMEZONE})`，provider.py:126 `if timezone not in _SUPPORTED_TIMEZONES` 在 L135 之前已拦截所有非 `"Asia/Shanghai"` 值
- **影响**: 不影响正确性；若未来扩展 `_SUPPORTED_TIMEZONES` 但忘记更新异常处理逻辑，此 dead code 可能误导维护者认为已有覆盖
- **建议改法和验证点**: 可保留为防御性代码但补充行内注释说明当前不可达原因；或移除并在扩展时按需添加
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低

### 3-未修复-低-test diff 混入大量格式化改动

- **入口/函数**: N/A
- **文件(行号)**: `tests/cli/test_prompt_command.py`、`tests/fins/test_fins_storage_provider.py`、`tests/runtime/test_scene_assets_migration.py`、`tests/service/test_entrypoint_runtime_interactive_path.py`、`tests/service/test_entrypoint_runtime_prompt_path.py`、`tests/tools/test_combined_tools_acceptance.py`
- **输入场景**: N/A
- **实际分支**: N/A
- **预期行为**: 功能性改动与格式化改动分离，减少 review noise
- **实际行为**: 多个测试文件的 diff 中混入了将多行函数调用折叠为单行、调整括号位置等纯格式化改动，与本次 tag-only selection 功能改动无关
- **直接证据**: test_prompt_command.py L997-999 将三行 `cli_main.main(...)` 折叠为单行；test_fins_storage_provider.py L108-112 将四行 Path 拼接折叠为单行；test_combined_tools_acceptance.py 多处类似改动
- **影响**: 增加 review 负担，使功能性改动更难定位；不影响正确性
- **建议改法和验证点**: 将格式化改动拆入独立 commit 或由 formatter 工具统一处理
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低

## Open Questions

- 无。

## Residual Risk

- `ScenePrepare` 公共语义未改，workspace 自定义 scene 仍可使用 `tool_names`；本轮只通过 packaged manifest 测试约束包内默认资产。若 workspace 自定义 scene 使用 broad `"fins"` tag，`start_fins_upload` 仍会被选中——这是 by design，但需在 workspace scene 编写指引中明确。
- `get_current_time` 当前只支持 `Asia/Shanghai`，`_SUPPORTED_TIMEZONES` 为单元素 frozenset。扩展时需同步更新 `_SUPPORTED_TIMEZONES`、`_get_current_time_parameters` 的 enum 列表、`base/tools.md` 指引和 `_timezone_argument` 校验逻辑。
- 真实 CLI smoke 验证使用本地可用 provider 凭据和当前时间，结果是一次真实环境 smoke，不替代长期 CI 中的 provider mock / contract 测试。
- `test_scene_assets_migration.py` 的 fake tool catalog 中 `start_fins_download` 标记为 `fins-download`、`start_fins_preprocess` 标记为 `fins-preprocess`，与真实实现一致；但 fake catalog 中没有 `start_fins_upload`（仅有 `fake_ingestion`），不影响当前测试正确性。
- `infer.json` 的 `tool_tags_any` 为 `["fins-read", "utils"]`，不包含 `fins-download`/`fins-preprocess`/`web`，与原 `infer` 场景只暴露 read 工具 + get_current_time 的设计意图一致。

## 验证/已覆盖

- 架构边界：ToolsDiscovery provider 在 `dayu.tools.utils`，通过 `dayu/config/tool_discovery.json` 显式发现，Engine 不拥有工具注册——符合设计。
- `get_current_time` callable 签名符合 `ToolCallable` 协议（async、ToolCallRequest + BatchToolExecutionContext → ToolExecutionOutcome）。
- 参数校验：timezone schema 有 enum 约束和 default 值；运行时 `_timezone_argument` + `_SUPPORTED_TIMEZONES` 双层校验。
- 返回值类型：ToolCompletedOutcome/ToolFailedOutcome 均正确构造，JSON value 类型为 str。
- tag-only manifests：10 个 packaged select manifest 均已改为 `tool_names=[]` + `tool_tags_any=[...]`，tag-based 选择覆盖原默认工具暴露面，`start_fins_upload` 不会被非上传 scene 选中。
- 测试覆盖：provider 单元测试（定义发现、成功返回、非法时区拒绝）、config loader 默认配置验证、scene prepare tag 选择验证、CLI/Service entrypoint tool_names 断言（含 get_current_time 在场 + start_fins_upload 不在场）、combined tools 接受度测试。
- README/LLM-facing 文本更新符合 `AGENTS.md` LLM-facing 文本约束。
