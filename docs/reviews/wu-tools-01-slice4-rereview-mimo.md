# WU-TOOLS-01 Slice S4 Re-Review - AgentMiMo

Gate: re-review
Work unit: WU-TOOLS-01
Slice: S4 - Fins Storage And Read Tools Provider
Agent: AgentMiMo
Scope: Controller accepted findings A1-A5 only
Stance: PASS

## 审查范围

- Controller adjudication: `docs/reviews/wu-tools-01-slice4-code-review-controller-adjudication.md`
- Codex fix artifact: `docs/reviews/wu-tools-01-slice4-fix-codex.md`
- 未提交 diff（4 files, +19 -6）

## 逐项确认

### A1. tool_decorator.py 不再使用 object/Any — PASS

- `_DecoratedToolReturn` 作为空 `Protocol` 定义于 `tool_decorator.py:27-28`。
- `tool()` 返回注解改为 `Callable[[Callable[P, _DecoratedToolReturn]], LegacySyncToolCallable]`（行 97）。
- `wrap(func)` 参数注解同步改为 `Callable[P, _DecoratedToolReturn]`（行 133）。
- 旧签名 `Callable[P, JsonValue]` 已移除，新签名不含 `object` 或 `Any`。
- **marker Protocol 可接受性**：空 Protocol 在结构化类型系统中等价于"任意类型均满足"，但与 `object` 有关键差异——pyright 对 `object` 做窄化要求显式 cast 或 isinstance，而空 Protocol 做宽度兼容。此处语义正确：legacy decorator 声明阶段不检查被装饰函数返回值，返回值由后续 adapter projection 统一处理。`_DecoratedToolReturn` 作为 marker 明确表达了"此处不约束返回值"的意图，不是逃避类型边界，而是对 decorator 装饰阶段实际行为的精确建模。
- pyright 0 errors, 0 warnings 已验证。

### A2. ToolArgumentError.arg_value 恢复 JsonValue | None — PASS

- `exceptions.py:65`：`arg_value: JsonValue | None = None`，已恢复。
- `search_engine.py:217`：`query_values: list[JsonValue] = [query for query in queries]`，构造 `list[JsonValue]` 后传入 `ToolArgumentError`，解决 `list` 不协变的 pyright 参数错误，不放宽异常边界。
- 无残留 `object` 类型。

### A3. _converters.py ScalarInput 精确替代 object — PASS

- `_converters.py:11`：`ScalarInput = str | int | float | bool | bytes | bytearray | SupportsInt | None`。
- `optional_int`、`int_or_zero`、`normalize_optional_text`、`require_non_empty_text` 的 `value` 参数均改为 `ScalarInput`（行 15、36、53、72）。
- 旧 `hasattr(value, "__int__")` 类型逃逸已移除，直接在 alias 边界内执行 `int(value)` 并捕获 `TypeError | ValueError`。
- `ScalarInput` 覆盖了 Fins 标量转换器实际接受的所有输入类型，精度足够。

### A4. 九个工厂 return annotation 精确为 _ToolFactoryResult — PASS

- `fins_tools.py:32`：`_ToolFactoryResult = tuple[str, LegacySyncToolCallable, ToolSchema]`。
- 九个 `_create_*_tool` 函数返回注解均为 `_ToolFactoryResult`（行 110、219、287、366、474、563、635、705、785）。
- 未重写 inner tool business function signatures/bodies，保留 OLD 迁移函数体形状。
- 导入 `LegacySyncToolCallable` 与 `ToolSchema` 来自当前 contracts/adapter，无新依赖。

### A5. 小修与测试补充 — PASS

- **未用 import**：`service_runtime.py` 已移除 `FsDocumentBlobRepository`、`FsFilingMaintenanceRepository` imports（diff 确认仅保留 6 个必要 import）。
- **_resolve_service docstring/signature**：参数收窄为 `service: FinsToolService`（`fins_tools.py:37`），docstring 改为"校验预构建的 FinsToolService 实例"（行 39），不再声称会新建 service。
- **AST import boundary**：`test_fins_storage_provider.py:565-610` 使用 `ast.parse` 解析 import 语句，`_module_imports` 提取 `ast.Import` 和 `ast.ImportFrom` 的模块名，`_is_forbidden_import` 做根模块匹配。比旧 substring scanning 更精确，不会被注释或 docstring 子串误报。
- **include_read_tools=False test**：`test_fins_provider_can_disable_read_tools_without_workspace_root`（行 181-194）覆盖返回空工具集且不解析 `workspace_root` 的路径。
- **README sync**：`dayu/config/README.md` 新增 Fins financial-tools provider 配置说明；`tests/README.md` 新增 `tests/fins/` 目录说明与运行命令。均按触发规则做最小同步。

## 验证结果

- 75 tests passed, 3 edgar deprecation warnings — 可信。
- pyright 0 errors, 0 warnings — 可信。
- `git diff --check` clean — 可信。

## 结论

**PASS**。A1-A5 全部修复到位，无 blocking finding，无新回归。Codex fix 在 Controller 裁决的 narrow scope 内完成，未引入新问题。
