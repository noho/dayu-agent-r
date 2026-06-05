# WU-TOOLS-01 Slice S4 Code Review — AgentMiMo

**审查范围**: 当前未提交变更（S4 Fins Storage And Read Tools Provider implementation）
**审查日期**: 2026-06-06
**审查人**: AgentMiMo (mimo-v2.5-pro)

---

## 1. Findings（按严重度排序）

### F1 [High] `fins_tools.py` 工厂函数返回 `tuple[str, Any, Any]` — 违反 AGENTS.md 禁止 `Any` 约束

**文件**: `dayu/fins/tools/fins_tools.py:108`（及所有 9 个 `_create_*_tool` 函数）

所有 `_create_*_tool` 工厂函数返回类型为 `tuple[str, Any, Any]`，但实际返回值始终是 `(name: str, func: LegacySyncToolCallable, schema: ToolSchema)`。AGENTS.md 明确禁止 `Any`，应使用精确类型。

**建议**: 定义 `_ToolFactoryResult = tuple[str, LegacySyncToolCallable, ToolSchema]` type alias，所有工厂函数签名改用此类型。同时 import `LegacySyncToolCallable` from `dayu.tools._legacy_adapter.registry_collector`。

### F2 [High] `fins_tools.py` 工厂函数内部使用 `Optional` 而非 `X | None`，且 `_resolve_service` 参数 `Optional` 无意义

**文件**: `dayu/fins/tools/fins_tools.py:31-50, 57`

- `_resolve_service(*, service: Optional[FinsToolService])` 接受 `None` 但立即 raise，`Optional` 签名误导调用方。应直接 `service: FinsToolService`。
- 模块级 import `from typing import Any, Optional` — `Optional` 是旧式写法，项目其余代码已统一用 `X | None`。
- 同文件中工具闭包参数大量使用 `Optional[list[str]]` 等，应统一为 `list[str] | None`。

### F3 [Medium] `service_runtime.py` 导入未使用的 `FsDocumentBlobRepository` 和 `FsFilingMaintenanceRepository`

**文件**: `dayu/fins/service_runtime.py:18-19`

```python
from dayu.fins.storage import (
    ...
    FsDocumentBlobRepository,    # unused
    FsFilingMaintenanceRepository,  # unused
    ...
)
```

这两个类在 `service_runtime.py` 中未被引用。它们的存在增加了不必要的 import 耦合面。

**建议**: 移除未使用的导入。

### F4 [Medium] `fins_tools.py` `_resolve_service` docstring 声称"或新建"但实际不允许

**文件**: `dayu/fins/tools/fins_tools.py:31-50`

docstring 写"解析或新建 FinsToolService 实例"，但函数体在 `service is None` 时 raise，从不新建。docstring 与行为不一致。

**建议**: 改为"校验预构建的 FinsToolService 实例可用性"。

### F5 [Medium] import boundary test `test_fins_import_boundaries_do_not_reverse_depend` 使用字符串匹配而非 AST 解析

**文件**: `tests/fins/test_fins_storage_provider.py:342-352`

该测试用 `any(name in text for name in forbidden)` 做字符串子串匹配，可能误报（注释/docstring 中出现 `dayu.engine` 等文本）。同文件 `test_legacy_tool_adapter.py:644-659` 使用了更精确的 AST 解析方式。

**建议**: 统一使用 AST 解析 `ast.Import` / `ast.ImportFrom`，与 adapter import boundary test 保持一致。

### F6 [Medium] `register_fins_read_tools` 的 `timeout_budget` 参数被立即 `del`，属于无效接口

**文件**: `dayu/fins/tools/fins_tools.py:58, 94`

```python
def register_fins_read_tools(..., timeout_budget: float | None = None) -> None:
    ...
    del timeout_budget
```

S4 迁移原则是"迁移可靠 OLD code，不重写业务逻辑"，但保留一个被立即删除的参数不提供任何功能。如果 OLD code 有此参数，迁移时应移除；如果是预留，应在 docstring 中明确说明而非 `del`。

**建议**: 移除 `timeout_budget` 参数。如果调用方已传入，改为在 provider 层不传此参数。

### F7 [Low] `tool_discovery.json` 中 `workspace_root: null` 与 `_parse_workspace_root` 的 fail-fast 语义

**文件**: `dayu/config/tool_discovery.json:11`, `dayu/fins/tools/provider.py:122-128`

默认配置 `workspace_root` 为 `null`。`_parse_workspace_root` 在值不是非空字符串时 raise `ValueError`。由于 provider 默认 `enabled: false`，这段路径不会在默认配置下被执行——行为正确。

但这意味着如果有人在 workspace config 中 `enabled: true` 但忘记设置 `workspace_root`，会在 discovery 阶段而非配置加载阶段才报错。当前行为是 fail-fast 且安全的，仅标注为 low——延迟发现可能增加调试成本。

### F8 [Low] `tool_decorator.py` 装饰器签名 `Callable[P, object]` 中的 `object`

**文件**: `dayu/tools/_legacy_adapter/tool_decorator.py:93, 129`

```python
def tool(...) -> Callable[[Callable[P, object]], LegacySyncToolCallable]:
    def wrap(func: Callable[P, object]) -> LegacySyncToolCallable:
```

AGENTS.md 禁止 `object`、`Any` 和无类型参数。此处 `object` 作为返回类型注解——在 Python 类型系统中 `object` 是所有类型的超类，语义上比 `Any` 更安全（它告诉类型检查器返回值可以是任何类型但不做特殊行为抑制）。然而，在 `ParamSpec` + `Callable` 上下文中，`object` 会丢失实际返回类型信息（如 `ListDocumentsResult`）。

**评估**: 这是 decorator 模式在 Python 类型系统中的已知限制。`ParamSpec` + `Callable[P, R]` + `TypeVar("R")` 方案在此场景下更精确，但会让签名更复杂。当前使用 `object` 是可接受的折中——它至少提供了类型安全约束（不允许 `None` 返回以外的特殊处理）。建议保持现状，但添加行内注释说明为何选择 `object` 而非 `Any`。

---

## 2. Test Gaps

### T1 [High] 7/9 Fins read tools 未通过 `ToolRuntime accept path` 验证

**文件**: `tests/fins/test_fins_storage_provider.py`

当前通过 `runtime.tool_executor.execute()` 测试的工具只有：
- `list_documents` (line 180)
- `search_document` (line 211)
- `get_document_sections` (line 266，但走 `definition.callable` 直接调用而非 runtime accept path)

以下工具缺少通过 `ToolRuntime accept path` 的执行测试：
- `read_section`
- `list_tables`
- `get_table`
- `get_page_content`
- `get_financial_statement`
- `query_xbrl_facts`

这些工具的闭包、参数投影、outcome 映射和 truncation 声明仅通过声明级别验证（`test_fins_truncate_specs_use_current_contract`），未覆盖实际执行路径。

### T2 [Medium] `discover_tools` 的 `include_read_tools=False` 路径未测试

**文件**: `dayu/fins/tools/provider.py:78-84`

当 `include_read_tools=False` 时，provider 应返回空工具集。此路径无测试覆盖。

### T3 [Low] `_parse_limits` 和 `_parse_bool_default` 的边界未直接测试

provider 的 `_parse_limits`（limits 非 Mapping、字段非正整数）和 `_parse_bool_default`（非布尔值）错误路径依赖 ValueError 传播，但没有专门的 provider 配置解析边界测试。`test_fins_workspace_root_must_be_explicit_absolute_path` 只覆盖了 `_parse_workspace_root`。

---

## 3. Storage Boundary 验证

**结论: Storage boundary 真实有效。**

- `DefaultFinsRuntime.create()` (service_runtime.py:74) 通过 `build_fs_repository_set()` 构建仓储，传入 `workspace_root`。
- `FinsToolService.__init__()` 接收 `company_repository`、`source_repository`、`processed_repository` 三个协议实例。
- `fins_tools.py` 工具闭包只通过 `service.*` 方法访问数据，不直接读文件。
- provider 不使用 Host/Service objects 或 EventLog 构建 Fins service。
- import boundary tests 验证 Fins 不反向依赖 Host/Engine/Service/UI，Engine/runtime 不 import Fins。

---

## 4. Migration Principle 验证

| 约束 | 状态 |
|------|------|
| 迁移可靠 OLD code，不重写业务逻辑 | PASS — service.py/processors/storage 从 OLD 复制，仅调整 import |
| Fins document access 必须且只能通过 `dayu.fins.storage` | PASS — 所有数据访问经 repository protocol |
| 不迁移 OLD ToolRegistry / TruncationManager / fetch_more | PASS — collector 只收集声明，不创建 OLD registry |
| Provider 不得用 Host/Service objects / EventLog | PASS — `DefaultFinsRuntime` 只装配仓储和处理器 |
| dayu.runtime 不得 import Fins | PASS — import boundary test 验证 |
| Engine 仍不得 import Fins | PASS — import boundary test 验证 |
| Ingestion fail closed | PASS — `include_ingestion_tools=True` 时 raise ValueError |

---

## 5. Response Projection 验证

- 测试 `test_list_documents_executes_through_current_tool_runtime` (line 207) 断言 `"ok" not in value`，确认无 OLD ok/value 嵌套。
- 测试 `test_search_document_projection_and_failure_outcomes` (line 263) 断言 success outcome 无 `ok` 字段、failure outcome 使用 `error == "invalid_argument"`。
- `search_document` 闭包 (fins_tools.py:336) 主动 `pop("diagnostics", None)` 剥离内部信息。
- OLD `project_legacy_return` 和 `project_legacy_exception` 在 adapter test 中有完整覆盖。

---

## 6. Truncation 验证

- 所有 9 个 read tools 使用 `ToolTruncateSpec`（current contract），无 OLD mapping。
- `test_fins_truncate_specs_use_current_contract` 验证了 `LIST_ITEMS` 和 `TEXT_CHARS` 策略。
- `ToolTruncateSpec` 字段完整：`enabled`, `strategy`, `limits`, `target_field`, `field_path=None`, `ttl_seconds=None`。
- 无残留 OLD `continuation_hint` / `fetch_more_args` / projection 语义。

---

## 7. README 同步验证

| README | 状态 | 备注 |
|--------|------|------|
| `dayu/fins/README.md` | PASS | 准确描述 storage boundary、read path、current read tools、ingestion 状态 |
| `dayu/config/README.md` | PASS | 记录 financial-tools provider 配置、disabled 默认值、fail-closed 语义 |
| `tests/README.md` | PASS | 记录 tests/fins/ 覆盖范围 |

---

## 8. 总结

S4 实现整体质量良好。Storage boundary 真实有效，迁移原则被严格遵守，ingestion 正确 fail-closed，response projection 无 OLD 残留，truncation 使用 current contract。

**必须修复**:
- F1: `fins_tools.py` 工厂函数返回类型中的 `Any` → 定义精确 type alias

**建议修复**:
- F2: `_resolve_service` 参数签名和 `Optional` 写法统一
- F3: `service_runtime.py` 移除未使用导入
- F4: `_resolve_service` docstring 修正
- F5: import boundary test 改用 AST 解析
- F6: `timeout_budget` 参数移除

**测试缺口**:
- T1: 7/9 read tools 缺少 runtime accept path 执行测试（High）
- T2: `include_read_tools=False` 路径无测试（Medium）

**无阻塞项**: 当前 74 passed, pyright 0 errors, git diff clean — 可在修复 F1 和补充 T1 后进入 gate。
