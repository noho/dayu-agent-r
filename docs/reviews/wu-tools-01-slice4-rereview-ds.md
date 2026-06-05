# WU-TOOLS-01 Slice S4 Re-Review — AgentDS

Gate: re-review (controller accepted findings fix verification)
Work unit: WU-TOOLS-01
Slice: S4 — Fins Storage And Read Tools Provider
Reviewer: AgentDS
Status: PASS

## Inputs

- Controller adjudication: `docs/reviews/wu-tools-01-slice4-code-review-controller-adjudication.md`
- AgentCodex fix report: `docs/reviews/wu-tools-01-slice4-fix-codex.md`
- Current uncommitted diff (staged + unstaged + untracked `dayu/fins/` / `tests/fins/`)

## Verification Evidence

- `pytest tests/fins tests/tools/test_legacy_tool_adapter.py tests/runtime/test_tools_discovery.py tests/runtime/test_config_loader.py` → 75 passed, 3 edgar deprecation warnings
- `pyright` → 0 errors, 0 warnings
- `git diff --check` → clean

## Findings by Accepted Item

### A1. `_DecoratedToolReturn` Protocol — PASS

`dayu/tools/_legacy_adapter/tool_decorator.py:27-28`

```python
class _DecoratedToolReturn(Protocol):
    """被 legacy decorator 接受但不在声明阶段检查的工具返回值标记。"""
```

- 装饰器返回注解从 `Callable[P, object]` 改为 `Callable[[Callable[P, _DecoratedToolReturn]], LegacySyncToolCallable]`（第 97 行）。
- `wrap(func)` 参数注解同步改为 `Callable[P, _DecoratedToolReturn]`（第 133 行）。
- `cast(LegacySyncToolCallable, func)` 保留在最内层，作为 legacy callable 协议的最终投影。
- pyright 接受 Fins TypedDict 返回值（如 `ListDocumentsResult`）与 Doc / legacy `JsonValue` 返回值通过该 marker Protocol。

**评估**：`_DecoratedToolReturn` 是一个 marker Protocol，不包含任何方法签名，本质上是 `object` 的类型安全替代。它表达了清晰的语义——legacy decorator 在声明阶段不检查返回值类型，实际类型由后续 adapter projection 层统一处理。这不是逃避类型边界，而是将类型检查责任前移到正确的抽象层。方案合理，不引入 `object`/`Any`。

### A2. `ToolArgumentError.arg_value` 恢复 `JsonValue | None` — PASS

`dayu/tools/_legacy_adapter/exceptions.py:65`

```python
arg_value: JsonValue | None = None,
```

已从 `object | None` 收窄回 `JsonValue | None`。

`dayu/fins/tools/search_engine.py:217-222` 对 `queries: list[str]` 构造 `list[JsonValue]` 后传入：

```python
query_values: list[JsonValue] = [query for query in queries]
raise ToolArgumentError(
    "search_document",
    "queries",
    query_values,
    ...
)
```

Python `list` 不协变的问题通过在调用侧做显式类型投影解决，没有放宽异常边界。其余调用点（如第 122 行 `mode`、第 176 行 `query/queries`）的 `arg_value` 均为 `str` / `None`，属于 `JsonValue | None` 合法子类型。

**评估**：修复精确，未扩散类型放宽。

### A3. Fins converter helper `ScalarInput` — PASS

`dayu/fins/_converters.py:11`

```python
ScalarInput = str | int | float | bool | bytes | bytearray | SupportsInt | None
```

- `optional_int`、`int_or_zero`、`normalize_optional_text`、`require_non_empty_text` 的 `value` 参数均改为 `ScalarInput`。
- 移除了 `hasattr(value, "__int__")` 类型逃逸，改为在 alias 边界内执行 `int(value)` 并 catch `TypeError`/`ValueError`（第 31 行）。
- `SupportsInt` 的引入是为了兼容 `numpy.integer` 等实现了 `__int__` 的第三方类型，是合法的实用主义选择。

**评估**：`ScalarInput` 足够精确，覆盖了财报数据清洗中常见的标量输入类型。不再使用 `object`/`hasattr` 逃逸类型系统。

### A4. Fins tool factory 返回类型 — PASS

`dayu/fins/tools/fins_tools.py:32`

```python
_ToolFactoryResult = tuple[str, LegacySyncToolCallable, ToolSchema]
```

- 导入了 `LegacySyncToolCallable`（第 10-13 行）与 `ToolSchema`（第 7 行）。
- 九个 `_create_*_tool` 工厂返回注解全部改为 `_ToolFactoryResult`：
  - `_create_list_documents_tool` → `_ToolFactoryResult`（第 110 行）
  - `_create_get_document_sections_tool` → `_ToolFactoryResult`（第 219 行）
  - `_create_read_section_tool` → `_ToolFactoryResult`（第 287 行）
  - `_create_search_document_tool` → `_ToolFactoryResult`（第 366 行）
  - `_create_list_tables_tool` → `_ToolFactoryResult`（第 474 行）
  - `_create_get_table_tool` → `_ToolFactoryResult`（第 563 行）
  - `_create_get_page_content_tool` → `_ToolFactoryResult`（第 635 行）
  - `_create_get_financial_statement_tool` → `_ToolFactoryResult`（第 705 行）
  - `_create_query_xbrl_facts_tool` → `_ToolFactoryResult`（第 785 行）
- Inner tool business function signatures/bodies 未重写，保持 OLD 迁移函数体形状。

**评估**：类型精确，未扩散到业务函数内部。

### A5. 小修与测试补充 — PASS

逐一检查：

1. **未使用 import 移除**：`dayu/fins/service_runtime.py` 不再 import `FsDocumentBlobRepository` 与 `FsFilingMaintenanceRepository`。当前 import 列表（第 15-23 行）均为实际使用的符号。

2. **`_resolve_service` docstring/signature**：`dayu/fins/tools/fins_tools.py:35-52`
   - 参数收窄为 `service: FinsToolService`（第 38 行）。
   - docstring 改为 "校验预构建的 FinsToolService 实例"，不再声称会新建 service（第 39-41 行）。
   - 调用侧 `register_fins_read_tools` 仍通过 `_resolve_service(service=service)` 透传（第 79 行），未影响 OLD 调用形状。

3. **AST import boundary 检查**：`tests/fins/test_fins_storage_provider.py:565-590`
   - `_module_imports()` 使用 `ast.parse` / `ast.walk` 做结构化 import 解析。
   - `test_fins_import_boundaries_do_not_reverse_depend()`（第 359-369 行）与 `test_runtime_and_engine_do_not_import_fins()`（第 372-382 行）均基于 AST 解析。
   - 不再依赖子串扫描，避免了注释/docstring 误报。

4. **`include_read_tools=False` 测试**：`tests/fins/test_fins_storage_provider.py:181-194`
   - `test_fins_provider_can_disable_read_tools_without_workspace_root()` 设置 `include_read_tools=False` 且 `workspace_root=None`。
   - 断言 `result.definitions == ()`，覆盖返回空工具集且不解析 workspace_root 的路径。

5. **README 同步**：
   - `dayu/config/README.md`：新增 Fins provider 的 `financial-tools` 默认配置说明（enabled/allow_empty/include_read_tools/include_ingestion_tools/workspace_root/limits），与当前 provider 行为一致。
   - `tests/README.md`：新增 `tests/fins/` 目录说明、常用命令中加入 `tests/fins`、Fins 与 Doc 的单包运行命令拆分。
   - `dayu/fins/README.md`：已存在于 untracked `dayu/fins/` 目录中，按 CLAUDE.md 触发规则完成最小同步。

## Non-Blocking Observations

以下内容属于 Controller 明确 rejected/deferred 范围，不升级为 blocking：

- OLD Fins `Optional[...]` / `Any` 重写：Controller rejected。
- 移除 `register_fins_read_tools(timeout_budget=...)`：Controller rejected。
- 所有 9 个工具的 ToolRuntime accept path 补齐：Controller deferred 到后续 work unit / aggregate review。
- Processor / XBRL 深层 parity：Controller deferred。

以上项目未在本次 fix 中引入新回归。

## Stance

**PASS** — 所有五个 Controller accepted finding 的 fix 均正确实施，未引入新回归。pyright 0 errors/0 warnings，75 tests passed，diff clean。Controller rejected/deferred 内容未被不当升级为 blocking。

Artifact path: `docs/reviews/wu-tools-01-slice4-rereview-ds.md`
