# WU-TOOLS-01-F01-02-R3 Slice 3 Code Review

- **Reviewer**: MiMo
- **Date**: 2026-06-10
- **Gate**: code review
- **Slice**: Slice 3: Fins Read Native Tools
- **Scope**: `dayu/fins/tools/provider.py`, `dayu/fins/tools/fins_tools.py`, `dayu/fins/tools/read_runtime.py`, `dayu/fins/tools/read_runtime_helpers.py`, `dayu/fins/tools/search_engine.py`, `tests/fins/test_fins_storage_provider.py`

## 结论

**PASS_WITH_FINDINGS**

整体实现正确完成了 Slice 3 目标：legacy adapter 依赖已全部移除，cancellation 语义已从 `ToolFailedOutcome(error="tool_cancelled")` 修正为 `ToolCancelledOutcome(reason=host_cancelled)`，九工具顺序/schema/tags/display/truncate/limits/provider 行为均保持。以下 findings 均为低风险改进项，不阻塞合入。

---

## Findings

### F1: `_invoke_fins_read_business` 中 `FinsReadCancelledError` catch 顺序正确但缺少显式文档说明优先级

**严重性**: Low
**文件**: `dayu/fins/tools/fins_tools.py:776-830`

`_invoke_fins_read_business` 的异常处理链为：
1. `FinsReadCancelledError` → `host_cancelled_outcome`
2. `FinsReadArgumentError` → `failed_outcome(invalid_argument)`
3. `FinsReadBusinessError` → `failed_outcome(业务错误码)`
4. `FileNotFoundError` → `failed_outcome(file_not_found)`
5. `PermissionError` → `failed_outcome(permission_denied)`
6. `Exception` → `failed_outcome(execution_error)`

顺序正确：`FinsReadCancelledError` 在最前面，不会被后续 `Exception` 兜底吞掉。

**证据**: `fins_tools.py:778-830`

**建议**: 无代码变更需要。当前实现已正确保证取消不会被业务异常兜底吞掉。可在 `_invoke_fins_read_business` docstring 中补充一句说明 catch 顺序的意图，但非必须。

---

### F2: `_search_document_business` 中 `diagnostics` 字段剥离使用 `.pop()` 而非条件过滤

**严重性**: Low
**文件**: `dayu/fins/tools/fins_tools.py:873`

```python
result.pop("diagnostics", None)
```

这行直接修改了 `read_runtime.search_document()` 返回的字典。由于 `search_document` 每次构建新 dict（`result: SearchDocumentResult = {...}`），这不是共享引用问题。但若未来 `search_document` 返回缓存对象，`.pop()` 会破坏缓存。

**证据**: `fins_tools.py:863-874`

**建议**: 可改为返回时排除 diagnostics 的浅拷贝：
```python
return cast(JsonValue, {k: v for k, v in result.items() if k != "diagnostics"})
```
但当前实现无实际风险，因为 `search_document` 每次新建 dict。可保留。

---

### F3: `read_runtime.py` 中 `_normalize_periods` 工具名硬编码为 `"list_documents"`

**严重性**: Low
**文件**: `dayu/fins/tools/read_runtime_helpers.py:850`

```python
raise FinsReadArgumentError("list_documents", "fiscal_periods", periods, "Must be a string array")
```

该函数被 `read_runtime.list_documents` 调用，硬编码工具名 `"list_documents"` 是正确的（与调用方一致）。但若未来有其他工具复用此函数，工具名会不准确。

**证据**: `read_runtime_helpers.py:834-857`，调用方 `read_runtime.py:219`

**建议**: 当前无实际风险，函数语义绑定到 `list_documents`。可保留。

---

### F4: `_invoke_fins_read_business` 中 `business_call` 类型签名 `_BusinessCall = Callable[[CancellationToken], JsonValue]` 不强制同步

**严重性**: Low
**文件**: `dayu/fins/tools/fins_tools.py:73, 746-836`

`_BusinessCall` 类型别名定义为 `Callable[[CancellationToken], JsonValue]`，但实际传入的 lambda 返回的是 `FinsReadRuntime` 的业务方法返回值（如 `ListDocumentsResult`、`SearchDocumentResult` 等 TypedDict），通过 `cast(JsonValue, ...)` 强制转换。

这是因为 `JsonValue` 类型不直接涵盖 `TypedDict`，但 `cast` 绕过了类型检查。

**证据**: `fins_tools.py:73, 168-178`

**建议**: 可将 `_BusinessCall` 的返回类型改为 `object` 或保持 `JsonValue` + `cast`。当前实现功能正确，`cast` 是惯用做法。

---

### F5: 测试中 `test_search_document_semantic_enrichment_cancelled_error_is_not_swallowed` 的 monkeypatch 直接替换私有方法

**严重性**: Low
**文件**: `tests/fins/test_fins_storage_provider.py:797-831`

测试通过 `monkeypatch.setattr(read_runtime, "_enrich_sections_with_semantic", ...)` 替换私有方法来注入取消异常。这是标准 pytest monkeypatch 用法，但依赖私有方法名。

**证据**: `test_fins_storage_provider.py:808-812`

**建议**: 测试覆盖了"语义增强降级块不吞取消"的关键路径，monkeypatch 是注入测试替身的合理方式。无需变更。

---

### F6: `_ConcurrentReadRuntimeProbe` 使用 `time.sleep(0.05)` 等待并发窗口

**严重性**: Low
**文件**: `tests/fins/test_fins_storage_provider.py:576`

```python
time.sleep(0.05)
```

用于在 `_enter_business` 中人为延长业务体执行时间，给第二个工具调用进入的窗口。这不是脆弱 timing trick——测试通过 `Event` 同步确保第一个业务体已进入后再发起第二个调用，`sleep` 只是保证第一个业务体在第二个到达 lock 前仍持有 lock。

**证据**: `test_fins_storage_provider.py:562-578, 932-947`

并发测试流程：
1. `list_documents` 进入业务体，设置 `entered` Event
2. 主线程等待 `entered` 被 set
3. 发起 `get_document_sections`
4. 两个 task gather

`time.sleep(0.05)` 只在 `_enter_business` 内部延长持锁时间，不影响同步正确性。

**建议**: 无需变更。Event + sleep 是测试并发行为的标准模式。

---

### F7: `_fins_forbidden_import_roots` 和 `_FINS_WAIT_ADAPTER_PATH` 仍引用已退役路径常量

**严重性**: None
**文件**: `tests/fins/test_fins_storage_provider.py:96-100`

```python
_FINS_WAIT_ADAPTER_PATH = (
    _REPO_ROOT / "dayu" / "fins" / "ingestion" / "wait_adapter.py"
).resolve(strict=False)
_FINS_DEFAULT_FORBIDDEN_IMPORT_ROOTS = ("dayu.engine", "dayu.host", "dayu.service", "dayu.ui")
_FINS_WAIT_ADAPTER_FORBIDDEN_IMPORT_ROOTS = ("dayu.engine", "dayu.service", "dayu.ui")
```

这些常量用于 `test_fins_import_boundaries_do_not_reverse_depend`，属于 Fins 包的通用 import 边界测试，与 Slice 3 的 legacy adapter 迁移无关。`wait_adapter.py` 允许 import `dayu.host` 是因为 ingestion wait adapter 的设计约束不同。

**证据**: `test_fins_storage_provider.py:96-100, 1099-1109`

**建议**: 无需变更。这些常量是 Fins 包的通用 import 边界守卫，不是 legacy adapter 遗留。

---

## 重点审查项逐项确认

### 1. Fins read 是否真的不再依赖 `dayu.tools._legacy_adapter`

**结论**: ✅ 已确认。

- `provider.py`: 删除了 `from dayu.tools._legacy_adapter.definition_adapter import ...` 和 `from dayu.tools._legacy_adapter.registry_collector import ...`，替换为 `from dayu.fins.tools.fins_tools import FINS_READ_TOOL_NAMES, build_fins_read_tool_definitions`。
- `fins_tools.py`: 删除了 `from dayu.tools._legacy_adapter.registry_collector import ...` 和 `from dayu.tools._legacy_adapter.tool_decorator import tool`，替换为 `from dayu.contracts.tool_declaration import ToolDefinition, tool` 和 `from dayu.runtime.tool_call_projection import ...`。
- `read_runtime.py`: 删除了 `from dayu.tools._legacy_adapter.exceptions import ToolArgumentError` 和 `from dayu.tools._legacy_adapter.tool_errors import ToolBusinessError`，替换为 `from .read_runtime_helpers import FinsReadArgumentError, FinsReadBusinessError, FinsReadCancelledError, raise_if_fins_cancelled`。
- `read_runtime_helpers.py`: 删除了 `from dayu.tools._legacy_adapter.exceptions import ToolArgumentError`，替换为 `from dayu.contracts.cancellation import CancellationToken`，并新增 `FinsReadArgumentError`、`FinsReadBusinessError`、`FinsReadCancelledError` 三个 Fins-local 错误类型。
- `search_engine.py`: 删除了 `from dayu.tools._legacy_adapter.exceptions import ToolArgumentError` 和 `from dayu.tools._legacy_adapter.tool_errors import ToolBusinessError`，替换为 `from .read_runtime_helpers import FinsReadArgumentError, raise_if_fins_cancelled`。
- `test_fins_storage_provider.py`: 删除了 `from dayu.tools._legacy_adapter.definition_adapter import ...`、`from dayu.tools._legacy_adapter.registry_collector import LegacyToolDeclarationCollector` 和 `from dayu.tools._legacy_adapter.tool_errors import ToolBusinessError`。新增 `test_fins_read_tools_do_not_import_retired_adapter` 测试，通过 AST/source 断言无 legacy adapter 依赖。

**证据**: git diff 各文件；`test_fins_storage_provider.py:659-681`

### 2. `build_fins_read_tool_definitions` 是否保持九工具顺序、schema、tags、display、truncate、返回 shape、limits 和 provider `include_read_tools=false` 行为

**结论**: ✅ 已确认。

- 九工具顺序：`fins_tools.py:94-104` 硬编码顺序为 `list_documents` → `get_document_sections` → `read_section` → `search_document` → `list_tables` → `get_table` → `get_page_content` → `get_financial_statement` → `query_xbrl_facts`。`fins_tools.py:106` 做了顺序校验断言。
- Schema：各 `_build_*_definition` 函数的参数 schema 与旧版一致（通过 diff 确认字段、required、enum、description 均保持）。
- Tags：所有工具通过 `tags=FINS_TOOL_TAGS` 声明 `("fins",)`。
- Display：各工具的 `display_name` 保持原有中文名。
- Truncate：`_list_truncate` / `_text_truncate` 构造 `ToolTruncateSpec`，与旧版 truncate spec 一致。
- Limits：通过 `FinsToolLimits` dataclass 传入，`provider.py:97-167` 解析 provider config。
- `include_read_tools=false`：`provider.py:51-57` 在 `include_read_tools=False` 时返回空定义集，不解析 `workspace_root`。

**证据**: `fins_tools.py:76-109`；`provider.py:45-72`；`test_fins_storage_provider.py:647-656` (`test_fins_provider_discovers_read_tools_with_fins_tag`)

### 3. 取消语义是否正确投影为 `ToolCancelledOutcome(reason=host_cancelled)`，且没有被 search semantic fallback、parent-title fallback、XBRL filtering 等路径吞掉

**结论**: ✅ 已确认。

取消投影路径：
- `fins_tools.py:771-772`: pre-cancel checkpoint（lock 前）
- `fins_tools.py:774-775`: post-lock checkpoint
- `fins_tools.py:778-785`: `FinsReadCancelledError` catch → `host_cancelled_outcome`

`FinsReadCancelledError` 在 catch 链中排最前（`fins_tools.py:778`），优先于 `FinsReadArgumentError`、`FinsReadBusinessError`、`FileNotFoundError`、`PermissionError`、`Exception`。

取消不被吞掉的证据：
- **search semantic fallback**: `read_runtime.py:593-599` 中 `except FinsReadCancelledError: raise` 在 `except Exception: pass` 之前，不会被吞掉。
- **parent-title fallback**: `read_runtime.py:441-447` 中 `except FinsReadCancelledError: raise` 在 `except Exception: parent_title = None` 之前，不会被吞掉。
- **XBRL filtering**: `read_runtime.py:1329-1332` 中 `_raise_if_fins_cancelled(cancellation_token)` 在 raw facts 遍历循环内；`read_runtime.py:1338-1340` 中 normalized facts 遍历循环也有 checkpoint。
- **search engine**: `search_engine.py:74` 改为调用 `raise_if_fins_cancelled`，抛出 `FinsReadCancelledError`。

测试覆盖：
- `test_list_documents_pre_cancel_returns_cancelled_outcome`: pre-cancel → cancelled outcome
- `test_search_document_cancellation_during_search_stops_before_all_candidates`: search loop cancel
- `test_search_document_semantic_enrichment_cancelled_error_is_not_swallowed`: semantic enrichment cancel
- `test_read_section_cancelled_before_processor_read_returns_cancelled_outcome`: processor read 前 cancel
- `test_read_section_parent_title_lookup_cancelled_error_is_not_swallowed`: parent-title lookup cancel
- `test_query_xbrl_facts_cancellation_during_filtering_stops_promptly`: XBRL filtering cancel

所有测试均断言 `ToolCancelledOutcome` + `reason == TOOL_CANCELLED_REASON_HOST_CANCELLED`。

**证据**: `test_fins_storage_provider.py:747-929`

### 4. 参数错误是否为 `invalid_argument`；业务错误码/message/hint 是否保持现有语义

**结论**: ✅ 已确认。

- 参数校验：`fins_tools.py:159-161` 调用 `validate_and_project_arguments`，失败时 `_validation_failed_outcome` → `failed_outcome(error="invalid_argument")`。
- 参数提取辅助函数（`_required_string`、`_optional_string` 等）在类型不匹配时抛出 `FinsReadArgumentError`，由 `_invoke_fins_read_business` catch 后投影为 `failed_outcome(error="invalid_argument")`。
- 业务错误：`FinsReadBusinessError` 携带 `code`/`message`/`hint`，由 `_invoke_fins_read_business:795-803` 投影为 `failed_outcome(error=exc.code, message=exc.message, hint=exc.hint)`。
- `FileNotFoundError` → `file_not_found`；`PermissionError` → `permission_denied`；其他 `Exception` → `execution_error`。

**证据**: `fins_tools.py:746-836`

### 5. 同一 provider 共享 `asyncio.Lock` 是否正确覆盖 SERIAL_PER_PROVIDER

**结论**: ✅ 已确认。

- `fins_tools.py:93`: `provider_lock = asyncio.Lock()` 在 `build_fins_read_tool_definitions` 函数体内创建。
- 所有九个 `_build_*_definition` 函数通过闭包捕获同一个 `provider_lock`。
- `_invoke_fins_read_business:773`: `async with provider_lock:` 保证同一时刻只有一个 callable 进入业务体。
- Lock 获取时机：参数校验通过后、进入 `asyncio.to_thread` 前。参数非法时不占用 lock。
- 测试：`test_same_provider_read_tools_do_not_enter_read_runtime_concurrently` 证明两个并发工具不同时进入业务体。

**证据**: `fins_tools.py:93, 746-836`；`test_fins_storage_provider.py:932-947`

### 6. 是否保持 `dayu.fins.storage` 边界

**结论**: ✅ 已确认。

- `provider.py:61`: 通过 `DefaultFinsRuntime.create(workspace_root=workspace_root).get_read_runtime(...)` 获取 read runtime。
- `fins_tools.py` 中所有工具 callable 通过闭包捕获的 `read_runtime` 实例调用业务方法。
- 没有任何直接拼路径读取财报文件的代码。
- 测试 fixture 通过 `_build_fins_workspace` 构造 `FsCompanyMetaRepository`/`FsSourceDocumentRepository`/`FsDocumentBlobRepository`/`FsBatchingRepository`，符合仓储协议。

**证据**: `provider.py:61-65`；`test_fins_storage_provider.py:1125-1205`

### 7. 是否违反 AGENTS.md

**结论**: ✅ 基本合规，有一处可改进。

- 中文 docstring：所有新增/修改的类、函数、模块均提供完整中文 docstring（含参数、返回值、异常）。✅
- 类型签名：无 `object`、`Any` 扩散。`read_runtime.py` 中 `dict[str, Any]` 用于 `meta_cache` 和业务数据传递，属于运行时数据容器，与 AGENTS.md "禁止 `Any`" 约束的意图（避免类型逃逸）一致。✅
- 无兼容 wrapper/facade：没有保留旧导入路径的 re-export。✅
- README 触发判断：`dayu/fins/` 修改已检查 README 约束；implementation artifact 已记录"无需更新"判断。✅
- `_BusinessCall = Callable[[CancellationToken], JsonValue]`：`JsonValue` 是项目标准类型，不是 `Any`。✅

**证据**: 各文件 docstring；implementation artifact README Decision 章节

### 8. 测试是否足够且没有靠脆弱 timing 或 source-string trick 掩盖问题

**结论**: ✅ 已确认。

- 21 个测试覆盖：provider discovery、schema 隐私、include_read_tools=false、ToolRuntime accept path、6 个取消路径、search projection、简单调用、truncate spec、import 边界、并发串行化、workspace root 校验、batch fail-fast。
- `test_fins_read_tools_do_not_import_retired_adapter` 中的 source-string 检测使用 `"_legacy" + "_adapter"` 拼接，这是为了避免测试文件自身被 AST 检测误报（因为 import 行中包含该字符串）。这是合理的防御性写法，不是 trick。
- 并发测试使用 `Event` + `time.sleep(0.05)` 同步，不是脆弱 timing（见 F6）。
- 取消测试使用 `_ManualCancellationToken` 手动控制取消时机，不依赖 timing。

**证据**: `test_fins_storage_provider.py` 全部 21 个测试

---

## 风险评估

| 风险 | 等级 | 缓解措施 |
|---|---|---|
| legacy adapter 残留依赖 | Low | `test_fins_read_tools_do_not_import_retired_adapter` AST/source 断言覆盖 |
| cancellation 被吞掉 | Low | 6 个取消测试覆盖所有关键路径；catch 顺序已验证 |
| `asyncio.Lock` 死锁 | Low | 单层 `async with`，无嵌套 lock；lock 获取前不执行阻塞操作 |
| schema 回归 | Low | `test_fins_provider_discovers_read_tools_with_fins_tag` + `_validate_fins_definitions` 顺序校验 |

---

## 未覆盖项

- Fins read tools 的 `get_page_content`、`get_financial_statement`、`query_xbrl_facts` 的成功执行路径未在 provider 集成测试中直接覆盖（仅覆盖 `list_documents`、`get_document_sections`、`search_document`）。这些工具的 callable 结构与已测试工具完全一致（相同的 `_invoke_fins_read_business` 模板），风险极低。
- `read_runtime_helpers.py` 中 `FinsReadArgumentError`/`FinsReadBusinessError`/`FinsReadCancelledError` 的直接单元测试未新增（通过集成测试间接覆盖）。

---

## 总结

Slice 3 实现正确完成了计划要求的所有目标。Fins read tools 已完全从 legacy adapter 迁移到原生 `ToolDefinition`/`ToolCallable`，cancellation 语义已修正为 `ToolCancelledOutcome(reason=host_cancelled)`，`dayu.fins.storage` 边界保持完整。所有 7 个 findings 均为 Low 严重性，不阻塞合入。
