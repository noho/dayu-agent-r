# WU-TOOLS-01 Slice S4 Fix - AgentCodex

Gate: fix
Work unit: WU-TOOLS-01
Slice: S4 - Fins Storage And Read Tools Provider
Agent: AgentCodex
Scope: Controller accepted findings A1-A5 only
Status: fix complete, pending external re-review

## 修复摘要

### A1. Legacy tool decorator 不再使用 object 签名

- `dayu/tools/_legacy_adapter/tool_decorator.py` 增加私有 marker Protocol `_DecoratedToolReturn`。
- `tool(...)` 返回注解改为 `Callable[[Callable[P, _DecoratedToolReturn]], LegacySyncToolCallable]`。
- `wrap(func)` 参数注解改为 `Callable[P, _DecoratedToolReturn]`。
- 该 marker 明确表达 legacy decorator 声明阶段不检查被装饰函数返回值；返回值由后续 adapter projection 统一处理。
- 保留 `cast(LegacySyncToolCallable, func)`，因为 metadata 挂载后仍要通过 legacy callable 协议返回给 collector。

### A2. ToolArgumentError.arg_value 收窄回 JsonValue

- `dayu/tools/_legacy_adapter/exceptions.py` 将 `arg_value` 恢复为 `JsonValue | None`。
- `dayu/fins/tools/search_engine.py` 对 `queries: list[str]` 构造 `list[JsonValue]` 后再传入 `ToolArgumentError`，解决 Python `list` 不协变导致的 pyright 参数错误，不放宽异常边界。

### A3. Fins converter helper 不再使用 object 输入签名

- `dayu/fins/_converters.py` 新增 `ScalarInput = str | int | float | bool | bytes | bytearray | SupportsInt | None`。
- `optional_int`、`int_or_zero`、`normalize_optional_text`、`require_non_empty_text` 的 `value` 参数改为 `ScalarInput`。
- 移除 `hasattr(value, "__int__")` 类型逃逸，直接在 alias 边界内执行 `int(value)` 并捕获转换失败。

### A4. Fins read tool 工厂返回类型精确化

- `dayu/fins/tools/fins_tools.py` 新增 `_ToolFactoryResult = tuple[str, LegacySyncToolCallable, ToolSchema]`。
- 导入 `LegacySyncToolCallable` 与 `ToolSchema`。
- 九个 `_create_*_tool` 工厂返回注解均改为 `_ToolFactoryResult`。
- 未重写 inner tool business function signatures/bodies，保留 OLD 迁移函数体形状。

### A5. 小修与测试补充

- `dayu/fins/service_runtime.py` 移除未使用的 `FsDocumentBlobRepository`、`FsFilingMaintenanceRepository` imports。
- `_resolve_service` 参数收窄为 `FinsToolService`，docstring 改为校验预构建 service，不再声称会新建 service。
- `tests/fins/test_fins_storage_provider.py` 的 Fins import-boundary 检查改为 AST import 扫描，避免注释或 docstring 子串误报。
- 新增 `include_read_tools=False` provider 测试，覆盖返回空工具集且不解析 `workspace_root` 的路径。
- `dayu/fins/README.md` 与 `tests/README.md` 已按触发规则做最小同步。

## 迁移原则说明

- 本轮只修 Controller 接受的 narrow findings，不扩大到 rejected/deferred 项。
- Fins read tools 仍通过 `dayu.fins.storage` 仓储协议与 `FinsToolService` 读取数据，未绕过 storage boundary。
- `register_fins_read_tools(timeout_budget=...)` 保留为 ignored legacy registration parameter。
- 未机械重写 OLD Fins 工具闭包里的 `Optional[...]`、`Any` 或业务函数体，避免把类型风格修复扩大成迁移逻辑改写。
- Provider 仍只暴露 read tools；ingestion tools 保持 fail-closed。

## 验证结果

- `source .venv/bin/activate && pytest tests/fins tests/tools/test_legacy_tool_adapter.py tests/runtime/test_tools_discovery.py tests/runtime/test_config_loader.py`
  - 结果：75 passed, 3 edgar deprecation warnings。
- `source .venv/bin/activate && pyright`
  - 结果：0 errors, 0 warnings。
  - follow-up：A1 从单次出现的 `TypeVar R` 改为 `_DecoratedToolReturn` marker Protocol；pyright 已确认该方案接受 Fins TypedDict 返回值与 Doc / legacy JsonValue 返回值。
- `git diff --check`
  - 结果：clean。

## 未处理 residual

- Broad OLD Fins `Optional[...]` / `Any` 重写：Controller 明确 rejected，不在本轮处理。
- 移除 `register_fins_read_tools(timeout_budget=...)`：Controller 明确 rejected，不在本轮处理。
- 所有 9 个工具的 ToolRuntime accept path 补齐：Controller 判定 S4 当前覆盖足够，剩余路径作为 later work unit / aggregate review residual。
- Processor / XBRL / financial statement 深层 parity：Controller 明确 deferred 到后续 work unit 或 aggregate review。
- A1 pyright warning：已在 follow-up 中修复，当前 pyright 为 0 errors, 0 warnings。

Artifact path: `docs/reviews/wu-tools-01-slice4-fix-codex.md`
