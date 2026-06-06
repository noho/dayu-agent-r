# WU-TOOLS-01 Slice S3 Implementation

Gate: implementation
Work unit: WU-TOOLS-01
Slice: S3 - Doc Tools Provider
Agent: AgentCodex
Status: implementation complete; stopped before review / fix / re-review / commit / push / PR

## 实现摘要

- 新增 `dayu/tools/doc_tools.py`，以 OLD `/Users/leo/workspace/dayu-agent/dayu/engine/tools/doc_tools.py` 为源迁移五个只读 Doc tools：`list_files`、`get_file_sections`、`search_files`、`read_file`、`read_file_section`。
- 新增 `dayu/tools/doc_provider.py`，通过当前 `ToolsDiscoveryProviderSpec.config` 解析 `limits` 与 `allowed_paths`，并把收集到的 OLD 风格声明适配为当前 `ToolDefinition`。
- Provider enabled 但 `allowed_paths` 缺失或为空时返回空 definitions，fail closed，不注册可执行 Doc tools。
- Provider 注册声明时调用 `register_doc_tools(..., allowed_paths=None, allow_file_write=False, allowed_write_paths=None, timeout_budget=None)`；路径白名单只由 provider/adapter 的 `ToolPathValidationPolicy` 提供。
- 扩展 `_legacy_adapter` 的窄内部契约：`FileAccessError` 支持 OLD Doc 函数体已有的三参构造形状；`LegacySyncToolCallable` 标注 decorator 写入的 `__tool_name__` / `__tool_schema__` metadata。
- 新增 `tests/tools/test_doc_tools_provider.py` 与 `tests/tools/fixtures/documents/` 下 Markdown / Docling JSON 确定性 fixture。
- 同步更新 `dayu/config/README.md` 与 `tests/README.md`。

## Import Closure Inventory

源文件：`/Users/leo/workspace/dayu-agent/dayu/engine/tools/doc_tools.py`

直接 import 分类：

| OLD import | 分类 | 处理 |
|---|---|---|
| `re` / `datetime` / `pathlib.Path` / `typing` | included | 标准库依赖保留。 |
| `..processors._doc_processor_factory.create_doc_file_processor` | included | 指向已迁移共享基础 `dayu.documents.processors._doc_processor_factory`。 |
| `..processors.search_utils.extract_query_anchored_snippets` | included | 指向已迁移共享基础 `dayu.documents.processors.search_utils`。 |
| `..tool_registry.ToolRegistry` | excluded-with-reason | 不迁移 OLD ToolRegistry；仅把声明收集参数类型改为 `LegacyToolDeclarationCollector`。 |
| `..exceptions.ToolArgumentError` / `FileAccessError` | included | 使用 `_legacy_adapter.exceptions` 的窄异常类型，供 response projection 分类。 |
| `dayu.log.Log` | excluded-with-reason | 不迁移 OLD logging facade；迁移模块内用极窄 `Log` 适配到 stdlib logger，以保留 OLD 函数体调用形状。 |
| `..tool_contracts.ToolTruncateSpec` | excluded-with-reason | 不迁移 OLD truncate contract；声明现场改用当前 `dayu.contracts.tool_schema.ToolTruncateSpec` 与 `ToolTruncationStrategy`。 |
| `.base.tool` | included | 使用 `_legacy_adapter.tool_decorator.tool` 收集 OLD decorator metadata。 |
| `dayu.contracts.tool_configs.DocToolLimits` | included | 迁移为 `dayu.tools.doc_tools.DocToolLimits`，仅保留 Doc tools 当前需要的 limits dataclass。 |

`utils_tools.py` 分类：

- `utils_tools.py` 不在 OLD `doc_tools.py` 的 import closure 中。
- 分类：excluded-with-reason。
- 原因：该文件只提供 `get_current_time` 通用工具，与 S3 Doc tools provider 无关；迁移它会扩大 scope。

发现的 OLD helper 分类：

- `engine/processors/*`：included via existing `dayu.documents` foundation from prior slice；S3 只复用，不重新迁移。
- `engine/tools/base.py`：included via `_legacy_adapter.tool_decorator`；只保留声明 metadata，不迁移执行 registry。
- `engine/exceptions.py`：included via `_legacy_adapter.exceptions`；只保留 adapter 需要的错误分类。
- `engine/tool_contracts.py`：excluded-with-reason；truncate 声明映射到 current contracts。
- `engine/tool_registry.py`：excluded-with-reason；路径安全、执行、OLD truncation、OLD fetch_more 均不迁移。
- OLD `TruncationManager` / `fetch_more` / projection：excluded-with-reason；当前 Host ToolRuntime 是 owner。

Blocker: none. import closure 不需要 OLD ToolRegistry、OLD TruncationManager、OLD fetch_more/projection 或未分类 helper。

## 迁移原则遵守说明

- 旧 Doc tool inner function signatures and bodies 基本保留；业务读取、章节、搜索、fallback 逻辑未重写。
- 必要变更仅限 import/package 适配、类型注解从 OLD Registry 改为 collector、`tags={"doc"}` 改为 tuple 以满足当前 decorator 类型、`ToolTruncateSpec.strategy` 改为 current enum，并补齐 current `field_path=None` / `ttl_seconds=None`。
- `FileAccessError` 三参支持是为了保持 OLD Doc 函数体中已有 `FileAccessError(directory, "", "路径不是目录")` 调用不改写；root cause 是 OLD exception 构造形状与 S2 adapter 内部异常形状不同。
- 未迁移 write-file tools。
- 未迁移 OLD ToolRegistry、OLD TruncationManager、OLD fetch_more 或 OLD truncate/fetch_more 投影。

## 路径安全边界说明

- Doc tool 函数体不拥有路径安全机制。
- `doc_provider.discover_tools()` 从 `spec.config["allowed_paths"]` 解析显式白名单，并归一化为 absolute roots。
- 白名单为空时 provider 返回空 definitions，fail closed。
- `file_path_params` metadata 从 OLD decorators 收集；provider 为每个声明构造 `ToolPathValidationPolicy`，覆盖声明中的 path params。
- adapter 在调用迁移函数前执行路径验证与绝对路径投影；失败返回 current `ToolFailedOutcome`，不会进入迁移函数体。
- `LegacyToolDeclarationCollector.register_allowed_paths(...)` 只记录 OLD 注册调用事实，不作为可信路径安全源。

## TruncateSpec 映射说明

- `read_file` 与 `read_file_section` 使用当前 `dayu.contracts.tool_schema.ToolTruncateSpec`。
- OLD `strategy="text_chars"` 映射为 `ToolTruncationStrategy.TEXT_CHARS`。
- limits 保留为 `{"max_chars": <provider limit>}`。
- `target_field="content"` 保留；`field_path=None`，`ttl_seconds=None`。
- 当前 Host ToolRuntime 负责实际 truncation 与 framework `fetch_more`，provider 不暴露 OLD fetch_more business tool。

## 输入/响应投影说明

- 输入：adapter 先按当前 schema 校验字段、required、默认值、类型、枚举和数值边界；path args 额外通过 provider path policy 验证并投影为 absolute path；non-path args 校验/coercion 后直传。
- 成功响应：plain dict/list/string 等 JSON 值直接成为 current `ToolCompletedOutcome.result.value`；OLD `{"ok": true, "value": ...}` envelope 会由 shared adapter 解包，但 Doc tools 本身返回 plain dict。
- 失败响应：adapter validation/path failures 与迁移函数异常映射为 current `ToolFailedOutcome`；路径拒绝为 `permission_denied`，缺失文件为 `file_not_found`，参数错误为 `invalid_argument`，未知异常为 `execution_error`。
- 测试确认代表性成功响应不包含 OLD `ok/value` envelope。

## 测试 / Pyright / Diff Check 结果

- `source .venv/bin/activate && pytest tests/tools/test_doc_tools_provider.py -q`
  - 结果：13 passed。
- `source .venv/bin/activate && pytest tests/tools/test_doc_tools_provider.py tests/documents`
  - 结果：19 passed。
- `source .venv/bin/activate && pyright`
  - 结果：0 errors, 0 warnings, 0 informations。
- `git diff --check`
  - 结果：通过，无 whitespace error。

## README 同步说明

- `dayu/config/README.md`：补充 `doc-tools` provider 的默认 disabled 配置、`allowed_paths` 显式白名单、fail-closed 行为和 limits 字段。
- `tests/README.md`：补充 Doc tools provider 测试职责与 `tests/tools/fixtures/documents/` fixture 约定。
- `dayu/README.md`、`dayu/engine/README.md`、`dayu/host/README.md` 未更新：本 slice 未改变分层关系、Host/Engine 公共契约或状态机。

## 残余风险

- fixed in current slice：Doc provider 路径白名单 fail-closed、path projection、current outcome projection、current truncate declaration、ToolRuntime accept-barrier execution均有目标测试覆盖。
- covered by later approved slice：Fins / Web providers 仍待后续 slice 迁移；它们不属于 S3。
- assigned to later work unit：如果后续需要把 Doc tools 默认启用于用户工作区，需要由配置/产品入口明确提供 `allowed_paths`，不能在 Doc provider 内猜路径。
- tracked by existing issue：WU-TOOLS-01 后续 slices 继续承接 Fins / Web 迁移与总体 deepreview。

## 完成状态

Implementation complete for Slice S3. 本轮按用户要求停在 implementation；未进入 review / fix / re-review / commit / push / PR gate。
