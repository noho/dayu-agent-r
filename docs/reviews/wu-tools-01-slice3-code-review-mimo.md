# WU-TOOLS-01 Slice S3 Code Review

Gate: code review
Work unit: WU-TOOLS-01
Slice: S3 - Doc Tools Provider
Agent: AgentMiMo
Status: review complete

## Findings

### CRITICAL: doc_tools.py 模块 docstring 错误暗示 ToolRegistry 负责路径安全

**文件**: `dayu/tools/doc_tools.py:1-22`

模块级 docstring 第 6 行写道："所有工具通过 ToolRegistry 的路径安全检查机制保护，无需手动验证路径"。第 16 行写道："自动安全检查：工具声明 file_path_params，由 ToolRegistry 自动验证路径"。

这两处直接违反迁移原则：Doc tools 迁移后不拥有路径安全机制，路径安全必须在外层 adapter/provider 边界完成。模块 docstring 是 LLM-facing 文本（tool description 来源之一），错误暗示会导致 LLM 认为函数体内部有安全检查，降低对路径白名单的信任。

**严重度**: CRITICAL
**建议**: 重写模块 docstring，明确说明路径安全由 provider/adapter 边界负责，Doc tool 函数体只做业务读取。

---

### CRITICAL: doc_tools.py:143-145 register_doc_tools 仍调用 registry.register_allowed_paths

**文件**: `dayu/tools/doc_tools.py:143-145`

```python
if allowed_paths:
    registry.register_allowed_paths(allowed_paths)
```

迁移计划 S3 明确要求："Do not pass path whitelist through `register_doc_tools(... allowed_paths=...)`; call that signature with `allowed_paths=None` and let the outer provider / adapter enforce paths through `ToolPathValidationPolicy`."

当前代码在 `allowed_paths` 非空时仍调用 `registry.register_allowed_paths()`。虽然 provider 当前传 `None` 跳过了该分支，但函数签名和代码路径保留了"通过 registry 注册路径白名单"的行为，与迁移原则矛盾。测试 `test_collector_allowed_paths_are_not_trusted` 还专门调用了 `register_doc_tools(collector, allowed_paths=[tmp_path])`，说明该路径仍被使用。

**严重度**: CRITICAL
**建议**: 移除 `register_doc_tools` 中对 `registry.register_allowed_paths()` 的调用。`allowed_paths` 参数应标记为 deprecated 或移除，provider 总是传 `None`。

---

### HIGH: doc_tools.py:135-137 示例代码使用 OLD ToolRegistry 模式

**文件**: `dayu/tools/doc_tools.py:135-137`

```python
Example:
    >>> registry = ToolRegistry()
    >>> limits = DocToolLimits(list_files_max=100)
    >>> register_doc_tools(registry, limits=limits, allowed_paths=[Path("workspace")])
```

示例代码使用 OLD `ToolRegistry()` 并传入 `allowed_paths`，与当前迁移后的使用方式（`LegacyToolDeclarationCollector` + provider `ToolPathValidationPolicy`）不一致。对维护者产生误导。

**严重度**: HIGH
**建议**: 更新示例代码为当前 provider/adapter 模式，或移除示例。

---

### HIGH: doc_tools.py 多处 docstring 引用 ToolRegistry 为路径/truncation owner

**文件**: `dayu/tools/doc_tools.py`

| 行号 | 内容 | 问题 |
|---|---|---|
| 125 | "调用 registry.register_allowed_paths() 注册路径白名单" | 暗示 registry 负责路径白名单 |
| 127 | "不传则不注册新路径（测试时可预先注册路径后直接调用）" | 暗示 registry 路径注册是安全机制 |
| 338-339 | "file_path: 文件路径（已由 ToolRegistry 解析为绝对路径）" | 路径解析由 adapter 完成，非 ToolRegistry |
| 860-861 | "截断机制通过 @tool 装饰器声明，由 ToolRegistry 自动处理" | truncation 由 ToolRuntime 处理，非 ToolRegistry |
| 978 | "file_path: 文件路径（已由 ToolRegistry 解析为绝对路径）" | 同 338-339 |

这些 docstring 是迁移时未清理的 OLD 描述，会误导维护者和 LLM。

**严重度**: HIGH
**建议**: 逐一更新 docstring，替换 ToolRegistry 引用为当前 adapter/ToolRuntime。

---

### HIGH: doc_tools.py tool description 中的错误安全暗示

**文件**: `dayu/tools/doc_tools.py`

tool description（LLM-facing）中有多处隐含路径安全由函数体处理的措辞：

- 第 214 行: `list_files` description 未提及路径安全由外部处理
- 第 320 行: `get_file_sections` description 未提及路径安全
- 第 629 行: `search_files` description 未提及路径安全
- 第 825 行: `read_file` description 未提及路径安全
- 第 952 行: `read_file_section` description 未提及路径安全

虽然 description 不需要详述安全机制，但当前完全没有提及路径白名单的存在，可能导致 LLM 在白名单外路径上尝试调用后收到 `permission_denied` 时感到困惑。

**严重度**: HIGH（边界线 MEDIUM）
**建议**: 至少在 description 中暗示路径需在配置允许范围内，或在 provider 配置文档中明确说明。

---

### HIGH: doc_tools.py 使用 `Any`、`Dict`、`List`、`Optional` 类型注解

**文件**: `dayu/tools/doc_tools.py`

多处函数签名使用了 AGENTS.md 禁止的类型注解：

- `Dict[str, Any]` 出现在: `list_files:227`、`get_file_sections:330`、`search_files:641`、`read_file:843`、`read_file_section:970`、`_sections_via_processor:399`、`_fallback_single_section:555`、`_search_via_processor:713`、`_search_via_line_scan:748`
- `Optional[List[str]]` 出现在: `search_files:639`
- `List[str]` / `List[Dict[str, Any]]` 出现在: `_read_file_lines:469`、`_extract_markdown_sections:489` 等

AGENTS.md 规定："禁止使用 `object`、`Any`、无类型参数、无类型返回值"。虽然这是迁移的 OLD 代码，但 AGENTS.md 编码约束没有区分新旧代码。

**严重度**: HIGH（迁移约束下可降级为 MEDIUM，因"OLD function signatures and bodies are not modified"）
**建议**: 在不修改 OLD 函数签名的前提下，这是一个已知的迁移约束风险。应记录为 residual risk，并在后续 cleanup 中处理。当前不应阻塞 slice。

---

### MEDIUM: _search_via_line_scan snippet 索引逻辑 bug

**文件**: `dayu/tools/doc_tools.py:778-789`

```python
snippet_idx = 0
for line_num, line in enumerate(lines, start=1):
    if query_lower in line.lower():
        snippet_text = snippets[snippet_idx] if snippet_idx < len(snippets) else line.strip()[:150]
        matches.append({...})
        snippet_idx += 1
```

`snippet_idx` 在每个匹配行都递增，但 `extract_query_anchored_snippets` 返回的 snippets 数量可能与匹配行数不同。如果 snippets 数量少于匹配行数，后续行会 fallback 到 `line.strip()[:150]`，这比 snippet 质量低。如果 snippets 数量多于匹配行数，多余的 snippets 被浪费。

这是迁移的 OLD 代码逻辑，不是 S3 新引入的问题。

**严重度**: MEDIUM
**建议**: 记录为 OLD code 已知问题。不阻塞 S3。

---

### MEDIUM: 缺少 `dayu.tools` import boundary test

**文件**: 缺失

迁移计划 S2 列出 "Add/update import-boundary tests for `dayu.tools`"，S3 测试验证中也提到 import boundary。当前测试文件中没有专门的 `dayu.tools` import boundary test（如 `tests/tools/test_import_boundary.py`），无法防止 `dayu.tools` 反向依赖 Engine、Host、Service、UI。

**严重度**: MEDIUM
**建议**: 补充 `tests/tools/test_import_boundary.py`，确认 `dayu.tools` 不导入 `dayu.engine`、`dayu.host`、`dayu.service`、`dayu.ui`。

---

### MEDIUM: test coverage 不足 — 缺少关键反例

**文件**: `tests/tools/test_doc_tools_provider.py`

当前测试覆盖了核心 happy path 和路径安全边界，但缺少以下反例：

1. **参数校验失败路径**: 没有测试 schema 校验失败（如 `read_file` 传入 `start_line` 为字符串）是否返回 `ToolFailedOutcome` 且不进入函数体。
2. **`list_files` 空目录**: 没有测试空目录返回空列表。
3. **`search_files` 无命中**: 没有测试搜索无结果时的响应形状。
4. **`read_file` 文件不存在**: 没有测试文件不存在时的 `file_not_found` 错误码。
5. **`read_file_section` 无效 ref**: 没有测试无效 ref 的 `invalid_argument` 错误码。
6. **并发执行序列化**: 没有测试 `SERIAL_PER_PROVIDER` 策略下多个 Doc tool 并发调用的序列化行为。

迁移计划 S3 expected assertions 要求 "Tests prove Doc function bodies are not responsible for path safety by using a spy/fixture callable or call counter"，该项已有 `test_path_validation_failure_does_not_enter_migrated_function_body` 覆盖。但 "Representative success and failure responses project to current outcomes" 要求更多失败路径覆盖。

**严重度**: MEDIUM
**建议**: 补充参数校验失败、文件不存在、无效 ref、空目录等反例测试。

---

### MEDIUM: _create_*_tool 工厂函数缺少返回值类型注解

**文件**: `dayu/tools/doc_tools.py:180`、`292`、`591`、`796`、`927`

五个 `_create_*_tool` 工厂函数均无返回值类型注解：

```python
def _create_list_files_tool(registry: LegacyToolDeclarationCollector, max_files: int):
```

应为 `-> tuple[str, LegacySyncToolCallable, ToolSchema]`。

**严重度**: MEDIUM
**建议**: 补充返回值类型注解。

---

### MEDIUM: doc_tools.py 中文 docstring 不完整

**文件**: `dayu/tools/doc_tools.py`

以下函数的 docstring 不符合"完整中文 docstring，至少包含参数、返回值、异常"的要求：

| 函数 | 行号 | 缺失 |
|---|---|---|
| `_try_create_processor` | 383 | 缺返回值类型说明 |
| `_count_file_lines` | 453 | 缺参数说明、返回值类型、异常说明 |
| `_read_file_lines` | 469 | 缺参数说明、返回值类型、异常说明 |
| `_extract_markdown_sections` | 489 | 缺参数说明、返回值类型、异常说明 |
| `_fallback_single_section` | 551 | 缺参数说明、异常说明 |
| `_search_via_processor` | 709 | 缺异常说明 |
| `_search_via_line_scan` | 743 | 缺异常说明 |
| `_get_section_children` | 1036 | 缺异常说明 |

**严重度**: MEDIUM
**建议**: 补齐 docstring。

---

### LOW: tool_contracts.py __all__ re-export ToolTruncateSpec / ToolTruncationStrategy

**文件**: `dayu/tools/_legacy_adapter/tool_contracts.py:202-207`

`__all__` 导出了 `ToolTruncateSpec` 和 `ToolTruncationStrategy`，它们是从 `dayu.contracts.tool_schema` import 后 re-export 的。这接近"兼容性 re-export"的定义。不过该模块是 `_legacy_adapter` 内部模块，不是公共包根，且 docstring 说明了它们是 current contracts 的引用而非 OLD copy。

**严重度**: LOW
**建议**: 保持现状，但注意不要从 `_legacy_adapter` 包根 re-export 这些符号。

---

### LOW: FileAccessError 三参构造形状仅服务于 OLD doc_tools.py

**文件**: `dayu/tools/_legacy_adapter/exceptions.py:98-118`

`FileAccessError.__init__` 的三参构造形状 `(path, filename, details)` 仅为保持 OLD `doc_tools.py` 中 `FileAccessError(directory, "", "路径不是目录")` 调用不改写。这不是问题，但增加了异常类的复杂度。

**严重度**: LOW
**建议**: 保持现状。迁移约束要求不改 OLD 函数体。

---

## 开放问题

1. **doc_tools.py 模块 docstring 中 "MODULE = 'ENGINE.DOC_TOOLS'"**: 第 39 行 `MODULE = "ENGINE.DOC_TOOLS"` 仍引用 OLD Engine 模块标识。Log adapter 使用该标识写入日志。虽不影响功能，但名称暗示仍在 Engine 内。是否需要改为 `"TOOLS.DOC_TOOLS"` 或 `"DOC_TOOLS"`？

2. **test_collector_allowed_paths_are_not_trusted 测试是否应存在**: 该测试调用 `register_doc_tools(collector, allowed_paths=[tmp_path])`，然后证明 collector 记录的路径不被信任。但如果 CRITICAL finding #2 被修复（移除 `register_allowed_paths` 调用），该测试需要相应调整。

3. **`_search_via_line_scan` snippet 质量**: `extract_query_anchored_snippets` 返回的 snippets 与行扫描匹配行之间的对应关系不精确，可能导致 snippet 质量不稳定。这是否需要在 S3 中修复，还是作为 OLD code residual 留给后续？

## 测试缺口

| 缺口 | 严重度 | 建议 |
|---|---|---|
| `dayu.tools` import boundary test | MEDIUM | 补充 `tests/tools/test_import_boundary.py` |
| 参数校验失败不进入函数体 | MEDIUM | 补充 schema validation 失败反例 |
| `read_file` 文件不存在 | MEDIUM | 补充 `file_not_found` 错误码测试 |
| `read_file_section` 无效 ref | MEDIUM | 补充 `invalid_argument` 错误码测试 |
| 空目录 / 无搜索结果 | LOW | 补充边界形状测试 |
| 并发序列化行为 | LOW | 补充 `SERIAL_PER_PROVIDER` 并发测试 |

## 总结

S3 实现整体架构正确：provider fail-closed、path validation 在 adapter 边界、file_path_params metadata 完整覆盖五个工具、current ToolTruncateSpec 声明正确、OLD fetch_more 未迁移、OLD ToolRegistry/TruncationManager 未导入、ToolRuntime accept barrier 集成测试通过。

主要问题是 **doc_tools.py 中残留大量 OLD ToolRegistry 引用**（模块 docstring、函数 docstring、tool description、示例代码、register_allowed_paths 调用），这些违反迁移原则中"路径安全必须在外层 adapter/provider 边界"的要求，且作为 LLM-facing 文本会误导推理器。其次是 **类型注解使用 `Any`/`Dict`/`List`** 违反 AGENTS.md 编码约束（但受迁移约束限制）。

建议优先修复 2 个 CRITICAL finding（模块 docstring 和 register_allowed_paths 调用），然后处理 HIGH 级 docstring 清理，MEDIUM 级测试缺口可在同一 slice 内补充。
