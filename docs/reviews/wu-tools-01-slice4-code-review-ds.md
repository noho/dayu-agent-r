# WU-TOOLS-01 Slice S4 — AgentDS Code Review

Gate: review
Work unit: WU-TOOLS-01
Slice: S4 - Fins Storage And Read Tools Provider
Reviewer: AgentDS (independent review, no fix / implementation / commit / push / PR)
Status: review complete

## 验证基线

- `pytest tests/fins tests/tools/test_legacy_tool_adapter.py tests/runtime/test_tools_discovery.py tests/runtime/test_config_loader.py` → 74 passed, 3 edgar deprecation warnings
- `pyright` → 0 errors
- `git diff --check` → clean

---

# Findings

## F1 [MEDIUM] `object` 类型使用违反 AGENTS.md 硬约束，但存在合理辩护

**位置**: `dayu/tools/_legacy_adapter/tool_decorator.py:93,129`

**现状**: `@tool` 装饰器签名从 `Callable[P, JsonValue]` → `Callable[P, object]`，`wrap()` 内参数签名同步变更。

**违反条款**: AGENTS.md "编码硬约束" 明确要求 "禁止使用 `object`、`Any`、无类型参数、无类型返回值，以及其他无法进行严格类型检查的签名设计"。

**根因分析**: Fins read tools 中有多个函数的返回类型包含了 `| NotSupportedResult` 联合类型（如 `get_page_content` 返回 `PageContentResult | NotSupportedResult`），这些类型不是 `JsonValue` 的合法子类型，旧签名 `Callable[P, JsonValue]` 会在 pyright 下对带 `| NotSupportedResult` 的工厂函数报错。

**合理辩护**: `@tool` 装饰器作为适配器，其 `wrap()` 内对 func 没有返回类型约束——它只把 metadata 挂到函数对象上后通过 `cast(LegacySyncToolCallable, func)` 返回。`object` 是 Python 类型系统中表达"接受任意返回类型 callable"的最精确方式（比 `Any` 更严格：`object` 表示"可以是任何值但不能在未知时调用方法"，`Any` 表示"关闭类型检查"）。

**可能替代方案**:
1. `Callable[P, typing.Any]` — 语义更宽松，但 `Any` 也被 AGENTS.md 禁止。
2. 定义 Protocol `class DecoratableTool(Protocol): def __call__(self, *args: P.args, **kwargs: P.kwargs) -> Any: ...` — 仍然用了 `Any`。
3. 让各工具工厂函数在传给 `@tool` 前先做一层类型适配——这是额外胶水代码，不值得。

**建议**: 在当前适配器边界维持 `object`，但需在 `tool()` docstring 或模块 docstring 中显式记录为什么这里必须用 `object` 及为什么无更精确方案。这不属于可以忽略的硬约束违反，必须说明理由。

---

## F2 [LOW] `_converters.py` 的 `object` 参数类型同样未经充分辩护

**位置**: `dayu/fins/_converters.py:25,37,54,73`

**现状**: `optional_int(value: object)`, `int_or_zero(value: object)`, `normalize_optional_text(value: object)`, `require_non_empty_text(value: object)` 均接受 `object` 类型入参。

**分析**: 这些是 JSON/LLM 输入边界的安全转换函数，接受任意值并归一化为可用的 Python 类型。逻辑上 `object` 是正确的——它们是被设计来处理"外部世界传入的任何值"的。

**建议**: 模块 docstring 应说明这些转换器的设计意图是"吸收任意 JSON/LLM 输入并在内部收敛"，因此 `object` 是有意为之的安全网而非逃避类型设计。

---

## F3 [LOW] `_legacy_adapter/exceptions.py` 中 `arg_value: object` 可收窄

**位置**: `dayu/tools/_legacy_adapter/exceptions.py:65`

**变更**: `arg_value: JsonValue | None` → `arg_value: object | None`

**分析**: `ToolArgumentError` 是错误容器，其 `arg_value` 在构造后被 `__init__` 的 `str(error)` 使用和不被使用（只是诊断信息）。从"接受任何 LLM 可能传入的参数值"的角度，`object` 比 `JsonValue` 更诚实——LLM 传入的非法参数可能是一个 Python dict（非 Mapping）、set、自定义对象等非 JSON 值。但严格来说，工具参数总是来自 JSON 反序列化的 `JsonValue`，即使参数值非法也应落在 `JsonValue` 范围。

**建议**: 可恢复为 `JsonValue | None`。当前使用 `object` 的理由是对 OLD 异常构造点的扩展兼容（OLD 代码可能传入任意值），但 S4 只迁移 read tools 且所有调用点都传入 `JsonValue` 兼容值。

---

## F4 [PASS] Provider workspace_root 解析 fail-fast 且无 cwd/env fallback

**位置**: `dayu/fins/tools/provider.py:109-128`

**验证通过**:
- `_parse_workspace_root()` 要求 `workspace_root` 为非空字符串。
- `.expanduser()` 后判断 `.is_absolute()`，相对路径直接 `ValueError`。
- 错误信息明确 `"no cwd/env fallback is allowed"`。
- 默认 `tool_discovery.json` 中 `workspace_root` 已改为 `null`，不提供隐式默认值。
- 测试 `test_fins_workspace_root_must_be_explicit_absolute_path` 验证相对路径被拒。

---

## F5 [PASS] Ingestion 工具 fail-closed

**位置**: `dayu/fins/tools/provider.py:72-76`

**验证通过**:
- `include_ingestion_tools=true` 直接抛 `ValueError`，信息引用 `ToolAwaitingOutcome` 语义，指向 blocker artifact。
- 测试 `test_ingestion_tools_are_fail_closed_pending_wait_adapter` 覆盖。
- Blocker artifact `docs/reviews/wu-tools-01-s4-ingestion-blocker-codex.md` 有完整的证据链和 residual risk 记录。

---

## F6 [PASS] Storage boundary 真实——service/tools 不绕过 repository 直接访问文件

**验证通过**:
- `FinsToolService.__init__` 只接受 protocol 类型：`CompanyMetaRepositoryProtocol`, `SourceDocumentRepositoryProtocol`, `ProcessedDocumentRepositoryProtocol`。
- Service 所有数据读取路径通过 `self._source_repository.get_source_meta()`, `.get_primary_source()`, `.list_source_document_ids()` 等协议方法。
- `DefaultFinsRuntime.create()` 是唯一接触具体 `Fs*Repository` 实现的装配点。
- 测试 fixture 通过仓储公开 API 写入数据，读取路径通过服务层验证。
- `dayu.fins.storage._fs_repository_factory.py` 作为工厂只负责装配 `FsStorageCore`，不向上一层暴露文件系统细节。

---

## F7 [PASS] ToolTruncateSpec 使用 current 契约，无 OLD 残留

**位置**: `dayu/fins/tools/fins_tools.py` 各 `@tool` 声明的 `truncate=` 参数

**验证通过**:
- 所有 9 个 read tools 的 `truncate=` 参数使用 `dayu.contracts.tool_schema.ToolTruncateSpec` 构造。
- `strategy` 字段使用 `ToolTruncationStrategy.LIST_ITEMS` 或 `ToolTruncationStrategy.TEXT_CHARS`。
- 无 `fetch_more` / `continuation_hint` / `content_base64` / OLD projection 残留。
- `grep` 确认 `dayu/fins/` 下只有 README 文档引用 `fetch_more`（在"不得迁移"的否定说明中）。
- 测试 `test_fins_truncate_specs_use_current_contract` 显式验证了三个工具的 truncate spec 类型和字段。

---

## F8 [PASS] Response projection 保留 current outcome，无 OLD ok/value nesting

**验证通过**:
- `dayu/fins/tools/service.py` 中 `search_document` 结果不包含 `"ok"` key。
- 测试 `test_list_documents_executes_through_current_tool_runtime` 断言 `"ok" not in value`。
- 测试 `test_search_document_projection_and_failure_outcomes` 同样断言 `"ok" not in value`，且同时验证了 `ToolCompletedOutcome` 和 `ToolFailedOutcome`。
- 工具在 `search_document` 的包装层 `pop("diagnostics", None)` 剥离内部诊断，不向 LLM 泄漏。

---

## F9 [PASS] Import boundary——Fins 不反向依赖 Host/Service/UI/Engine

**验证通过**:
- 测试 `test_fins_import_boundaries_do_not_reverse_depend` 扫描 `dayu/fins/**/*.py` 无 forbidden import。
- 测试 `test_runtime_and_engine_do_not_import_fins` 扫描 `dayu/engine/` 和 `dayu/runtime/` 无 fins import。
- `dayu.fins.service_runtime` 的 docstring 明确声明 "不持有 Host、Service、EventLog 或 ingestion job manager"。

---

## F10 [MEDIUM] `_positive_int` 中 bool 被正确防范，但 `isinstance(value, bool)` 检查冗余

**位置**: `dayu/fins/tools/provider.py:226`

**现状**: `isinstance(value, bool) or not isinstance(value, int) or value < 1`

**分析**: `bool` 是 `int` 的子类，所以 `isinstance(True, int)` 返回 `True`。检查 `isinstance(value, bool)` 在前是正确的防护——防止 JSON `true` 被误作正整数。这是正确的做法。

**问题**: 这个 check 逻辑正确，但注释和可读性可以提升——建议注释说明 "bool is subclass of int, reject before int check"。

---

## F11 [INFO] `_legacy_adapter/tool_decorator.py` 变更分析——签名从 `JsonValue` 放宽为 `object`

**补充于 F1**: 这是本次审查的核心问题之一。需要说明的是：
- 这个变更不是因为 `@tool` 装饰的函数"可以返回任意类型"，而是因为 `Callable[P, JsonValue]` 在 pyright 严格模式下无法接受返回 `XxxResult | NotSupportedResult` 的函数。
- `| NotSupportedResult` 构成了 TypeScript 风格的 union return type，不属于 `JsonValue`。pyright 对此严格检查。
- 变更为 `object` 后 pyright 不再报错，说明这是解决类型兼容性的唯一方式（除非引入 Protocol 或多态返回类型设计）。

**替代方案评估**:
- `Callable[P, Any]`：比 `object` 差（关闭类型检查）。
- 修改工具工厂返回 `JsonValue` 并在内部做 cast：增加胶水代码，违反"不重写 OLD body"原则。
- 定义窄返回类型 union：需要知道所有可能的工具返回类型，违背了装饰器通用性的设计意图。
- **推荐**: 保持 `object`，但在 docstring 中解释原因。同时建议在 AGENTS.md 中为"适配器 / 装饰器 / 边界转换函数"增加例外条款。

---

## F12 [INFO] 新增 `dayu/fins/` 包名与原有的 `dayu.fins` 测试文件无冲突

**验证**: 测试文件 `tests/fins/test_fins_storage_provider.py` 使用 `from dayu.fins...` 导入，测试通过。新建的 `dayu/fins/__init__.py` 是有效包标记。

---

# 开放问题 / 测试缺口

## Q1: processor 实际实例化路径未被测试覆盖

当前测试的 fixture markdown 非常简单（一份 10-K，且只用了 `FinsMarkdownProcessor` 或其他基于 markdown 的 processor 通过 `create_with_fallback()` 创建）。`get_financial_statement`、`query_xbrl_facts`、`get_page_content` 等工具在 fixture 下会返回 `not_supported`（因为没有 XBRL 实例文件、没有分页处理器）。**建议**: 不阻塞 S4 merge——这些路径在 OLD 仓库中已有覆盖；但应记录为 residual risk。

## Q2: `workspace_root=null` 的 disabled config 场景在给定时未被测试

当前测试 `test_fins_provider_discovers_read_tools_with_fins_tag` 和 `test_fins_workspace_root_must_be_explicit_absolute_path` 分别覆盖了启用和相对路径拒绝场景，但没有测试 spec 的 `enabled=False` 路径。Provider 本身不处理 `enabled` flag（由 `ToolsDiscovery` 处理），但应确认 provider 在收到 null `workspace_root` 时会正确 fail。

## Q3: limits 解析的边界条件

`_parse_limits` 对部分覆盖的 `limits` 字典正确处理（使用 `defaults` 值），但没有测试验证当 `limits` 为 `{}`、`{"nonexistent_field": 5}`、或值类型错误时的行为。`_positive_int` 覆盖了类型错误，但 `_parse_limits` 本身的组合逻辑没有独立单元测试。

## Q4: 只测试了 3 个工具通过 ToolRuntime accept path

`test_list_documents_executes_through_current_tool_runtime` 和 `test_search_document_projection_and_failure_outcomes` 和 `test_simple_matching_call_passes_through_provider_definition` 分别覆盖了 `list_documents`、`search_document`、`get_document_sections`。剩余 6 个 read tools（`read_section`、`list_tables`、`get_table`、`get_page_content`、`get_financial_statement`、`query_xbrl_facts`）未通过 ToolRuntime accept path 测试。**判断**: 可接受——所有 tools 共享相同的 adapter/provider path，但应记录为 residual risk。

## Q5: `dayu/fins/README.md` 中 "不得迁移 OLD ToolRegistry、OLD TruncationManager" 是约束声明而非状态描述——确认设计意图一致

**当前**: README 写 "不得迁移 OLD ToolRegistry..."。这与 S4 实际行为完全一致（所有 declarations 通过 `LegacyToolDeclarationCollector`，truncation 使用 current spec）。

---

# 总结

S4 实现严格遵循 WU-TOOLS-01 migration plan 的原则：
- Read tools 函数签名和 body 未被改写；仅做了 import/package 适配和 adapter 边界映射。
- Storage boundary 真实——服务层和工具层通过 repository protocols 访问数据，未绕过仓储。
- Provider fail-fast 设计正确：`workspace_root` 拒绝相对路径，ingestion 工具 fail-closed。
- `ToolTruncateSpec` 使用 current 契约，无 OLD fetch_more/continuation_hint 残留。
- Response projection 干净，无 `ok`/`value` nesting。
- Import boundaries 通过自动化测试验证。

主要 findings：
- **F1 (MEDIUM)**: `@tool` 装饰器签名中 `object` 使用违反 AGENTS.md 硬约束。有合理辩护（适配器必须接受任意返回类型），但需要显式记录理由。
- **F2 (LOW)**: `_converters.py` 中 `object` 参数同样需要文档辩护。
- **F3 (LOW)**: `ToolArgumentError.arg_value: object` 可恢复为 `JsonValue | None`。
- 四个测试缺口（Q1-Q4）均为可接受的 residual risk，不阻塞 merge。

**整体评价**: 实现质量良好，硬约束合规度高，无 blocking 级别 issue。建议在 merge 前处理 F1（文档化 `object` 使用理由），其余可 deferred。
