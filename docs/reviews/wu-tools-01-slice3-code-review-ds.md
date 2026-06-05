# WU-TOOLS-01 Slice S3 Code Review (AgentDS)

Gate: review
Work unit: WU-TOOLS-01
Slice: S3 - Doc Tools Provider
Reviewer: AgentDS
Status: review complete; not entering fix / re-review / commit

## 审查范围

当前未提交变更，即 Slice S3 Doc Tools Provider implementation。重点文件：

- `dayu/tools/doc_tools.py`
- `dayu/tools/doc_provider.py`
- `dayu/tools/_legacy_adapter/exceptions.py`
- `dayu/tools/_legacy_adapter/registry_collector.py`
- `tests/tools/test_doc_tools_provider.py`
- `tests/tools/fixtures/documents/*`
- `dayu/config/README.md`
- `tests/README.md`
- `docs/reviews/wu-tools-01-slice3-implementation-codex.md`

## 测试与类型检查基线

```
pytest tests/tools/test_doc_tools_provider.py tests/documents -q → 19 passed
pyright → 0 errors, 0 warnings, 0 informations
```

---

## 审查发现

### 1. [MEDIUM] `list_files` 返回相对路径与其他工具组合失败

**文件**: `dayu/tools/doc_tools.py:268`

`list_files` 返回的文件路径是相对路径：
```python
"path": str(file_path.relative_to(dir_path)),
```

同时 `read_file` 的 LLM-facing 参数描述明确引导模型这样做：
```python
# line 804
"description": "文件路径。优先使用 list_files 返回的 files[].path。..."
```

但 adapter 的路径解析使用 `Path(value).expanduser().resolve(strict=False)`（`definition_adapter.py:454`），对相对路径会相对于 CWD 解析，而非相对于 `list_files` 的搜索根目录。

**实测验证**：`list_files` 返回 `"subdir/test.md"`，将其传给 `read_file` → `file_not_found`（因为 `$CWD/subdir/test.md` 不在 allowed_roots 下且不存在）。

**影响**：LLM 被引导的"list_files → read_file/read_file_section"基本组合流在 CWD 与 allowed_roots 不一致时不可用。这是 OLD 行为的延续（OLD ToolRegistry 同样用 `Path(value).resolve()`），但当前测试套件完全未覆盖此组合路径。

**建议**：不在 S3 修复（非回归），但应在 S6 集成测试或后续 work unit 中明确处理（例如 adapter 内用 allowed_roots 作为相对路径基准解析，或在 LLM-facing 描述中明确要求传绝对路径）。至少应在此 slice 的测试中加一条反例记录当前行为。

### 2. [MEDIUM] 测试只覆盖绝对路径输入，未覆盖相对路径组合

**文件**: `tests/tools/test_doc_tools_provider.py`

全部测试（`test_path_args_are_projected_to_validated_absolute_paths`、`test_markdown_and_docling_fixtures_support_sections_search_and_read` 等）都传入绝对路径。没有任何测试验证：
- `list_files` 返回的相对路径能直接传给 `read_file` / `get_file_sections` / `read_file_section`
- `search_files` 返回的相对路径能直接传给 `read_file_section`

这与 Finding 1 是同一个根因的两面：路径组合流未被测试。

**建议**：至少添加一条测试记录当前行为（即使结果是预期的 `file_not_found`），为后续修复提供基线。

### 3. [LOW] 模块与函数 docstring 引用不存在的 ToolRegistry

**文件**: `dayu/tools/doc_tools.py`

| 行号 | 文本 | 问题 |
|------|------|------|
| 5 | `所有工具通过 ToolRegistry 的路径安全检查机制保护` | ToolRegistry 不存在；安全由 adapter/provider 边界承担 |
| 15 | `工具声明 file_path_params，由 ToolRegistry 自动验证路径` | 同上 |
| 338 | `文件路径（已由 ToolRegistry 解析为绝对路径）` | 实际由 `_project_paths` 解析 |
| 860 | `截断机制通过 @tool 装饰器声明，由 ToolRegistry 自动处理` | 截断由 Host ToolRuntime 处理 |
| 978 | `文件路径（已由 ToolRegistry 解析为绝对路径）` | 同 338 |

**影响**：这些是函数 docstring（非 LLM-facing tool description），不直接影响模型行为。但违反"文档反映当前代码"原则，且可能误导后续开发者。

**建议**：将"ToolRegistry"替换为"provider/adapter 路径安全边界"或等价当前术语。

### 4. [LOW] `get_file_sections` 降级路径中的编码覆盖不一致

**文件**: `dayu/tools/doc_tools.py:469-486` vs `dayu/tools/doc_tools.py:866-877`

`_read_file_lines`（被 `get_file_sections` fallback 使用）尝试 `utf-8` 和 `gbk` 两种编码。
`read_file` 函数体尝试 `utf-8`, `gbk`, `latin1`, `cp1252` 四种编码。

当文件是 `latin1` 或 `cp1252` 编码时，`read_file` 可以成功读取，但 `get_file_sections` 的 fallback 路径会返回 `None`（导致 fallback 到 single section）。

**影响**：`get_file_sections` 对非 utf-8/gbk 编码的纯文本文件会退化为单节 fallback，而非报错。这是 OLD 行为延续，非 S3 引入。但对于 S3 迁移来说，这是一个值得记录的行为差异点。

### 5. [LOW] `read_file` 函数体中 `used_encoding` 未使用（dead store）

**文件**: `dayu/tools/doc_tools.py:868,874`

```python
used_encoding = None    # line 868
...
used_encoding = encoding # line 874 (仅在此被赋值，后续不再读取)
```

`used_encoding` 被赋值后从未读取。这是 OLD 代码保留的 dead store。

### 6. [LOW] `_read_file_lines` 对 OSError 静默返回 None

**文件**: `dayu/tools/doc_tools.py:484`

```python
except OSError:
    return None
```

权限错误等非解码异常被静默吞掉，与 `read_file` 函数体中抛出 `FileAccessError` 的行为不一致。这也是 OLD 行为延续。

### 7. [INFO] `_validate_doc_declarations` 校验时机在注册之后

**文件**: `dayu/tools/doc_provider.py:73-82`

```python
register_doc_tools(collector, ...)
declarations = collector.collected_tools()
_validate_doc_declarations(declarations)
```

校验（检查 file_path_params 完整性）发生在 `register_doc_tools` 完成之后。当前实现中 `register_doc_tools` 只做声明收集（无副作用），所以这是安全的。但如果 register 函数未来产生副作用，这个顺序会变得脆弱。

**建议**：不影响 S3 接受。但可考虑将校验内聚到 `register_doc_tools` 末尾，或至少在 `_validate_doc_declarations` 上方加注释说明"注册无副作用，校验仅验证声明完整性"。

---

## 用户硬约束逐项确认

### 迁移原则遵守

| 约束 | 状态 | 证据 |
|------|------|------|
| 迁移可靠 OLD code，不重写 | ✅ PASS | OLD 函数体保留；仅 import/package 适配、decorator 参数类型适配、truncation strategy enum 改写 |
| 只允许 import/package、最小 @tool adapter、最小 provider/entrypoint adapter | ✅ PASS | doc_provider.py ~275 行；adapter 修改局限在 exceptions.py(三参支持)、registry_collector.py(协议标注) |
| 旧 Doc tools 不负责安全机制；路径安全在外层 adapter/provider 边界 | ✅ PASS | Tool description 不含路径安全声明；adapter `_project_paths` 承担全部路径校验 |
| 不迁移 OLD ToolRegistry / TruncationManager / fetch_more | ✅ PASS | AST 扫描与 import 清单确认 |
| tools 按当前 ToolTruncateSpec 声明 | ✅ PASS | read_file/read_file_section 使用 `ToolTruncateSpec(enabled=True, strategy=ToolTruncationStrategy.TEXT_CHARS, ...)` |
| query/input 进入函数前投影正确 | ✅ PASS | adapter `project_tool_call_arguments` → `_project_paths` 先校验后投影 |
| 函数返回投影到 current outcome 正确 | ✅ PASS | plain dict → `ToolCompletedOutcome`；异常 → `ToolFailedOutcome` |
| 不迁移 write tools | ✅ PASS | 五个工具均为只读 |

### 路径安全

| 约束 | 状态 | 证据 |
|------|------|------|
| provider enabled 无 allowed_paths → fail closed | ✅ PASS | `_parse_allowed_paths` 空→空元组→`discover_tools` 返回空 definitions |
| 不信任 collector.register_allowed_paths | ✅ PASS | collector 仅记录调用事实；`_adapt_doc_declarations` 显式构造 `ToolPathValidationPolicy(allowed_roots=allowed_roots)` |
| path params 先校验白名单并投影到 absolute path | ✅ PASS | adapter `_project_paths:454-473`：resolve → exists check → allowed_roots check → `str(candidate)` |
| file_path_params metadata 完整覆盖五个工具 | ✅ PASS | list_files/read_file/read_file_section/get_file_sections/search_files 均声明 |
| file_path_params 缺失时 fail closed | ✅ PASS | `_validate_doc_declarations:214-215` raise ValueError |

### Truncation

| 约束 | 状态 | 证据 |
|------|------|------|
| read_file/read_file_section 使用当前 ToolTruncateSpec | ✅ PASS | 测试 `test_read_tools_expose_current_truncate_spec_and_no_old_imports` |
| 无 OLD fetch_more business tool | ✅ PASS | 测试 `test_no_old_fetch_more_business_tool` |
| 无 OLD TruncationManager/fetch_more 导入 | ✅ PASS | AST 扫描确认 |

### AGENTS.md 约束

| 约束 | 状态 | 证据 |
|------|------|------|
| 中文 docstring（新代码） | ✅ PASS | doc_provider.py, adapter 模块均为中文 docstring |
| 禁止 Any/object（新代码） | ✅ PASS | doc_provider.py 和 adapter 无 Any/object 签名 |
| OLD 代码弱类型 | ⚠️ KNOWN | `Dict[str, Any]` 返回类型为迁移约束保留；已在 plan 中标记为 residual risk |
| README 同步 | ✅ PASS | config/README.md 和 tests/README.md 已更新 |
| LLM-facing 语义无内部术语 | ✅ PASS | tool description/参数描述均不含 ToolRegistry/TruncationManager/Engine/Host |

---

## 开放问题与测试缺口

1. **list_files → read_file 组合流未测试**（见 Finding 1/2）。当前测试中 list_files 的输出路径从不同其他工具联调。S6 集成测试可能覆盖此路径，但 S3 尚无基线。

2. **`list_files` 与 `search_files` 的 `directory` 参数**在 adapter 中都有 `must_exist=True` 的路径策略。这意味着这些参数的路径必须已经存在。但 `read_file` 和 `get_file_sections` 的 `file_path` 也有 `must_exist=True`。`read_file_section` 同样。一致性正确。

3. **`_is_relative_to` 的手动实现**（`definition_adapter.py:477-486`）未覆盖非 normalized 根的边界情况——但 `_project_paths:442` 已对 roots 做 `expanduser().resolve()`，所以此边界已被上游封闭。

4. **Fixtures 覆盖度**：当前只有 Markdown (.md) 和 Docling JSON (.json) 两种 fixture。缺少 HTML fixture 的场景测试，但 tool description 中 `_SUPPORTED_FORMATS_DESCRIPTION` (line 42) 明确列出了 `html, htm`。当前 `get_file_sections` 和 `read_file_section` 对 HTML 文件的处理器路径未被测试。

5. **并发策略**：Doc provider 使用 `SERIAL_PER_PROVIDER` 并发策略（`doc_provider.py:245`），所有五个 Doc tools 共享一个 `asyncio.Lock`。策略选择有文档说明，但无测试证明此选择是必要的（vs. `SERIAL_PER_TOOL` 或 `CONCURRENT_AFTER_EVIDENCE`）。当前测试使用 `asyncio.run` 单线程执行，不会触发并发冲突。

6. **`search_files` 的大目录性能**：`search_files` 对 `dir_path.rglob("*")` 无深度或文件数限制，对每个文件尝试创建 processor 并搜索。大量文件时可能超出 timeout budget。这是 OLD 行为延续，但当前 `register_doc_tools` 声明了 `timeout_budget` 参数却 `del timeout_budget`（line 139），timeout 治理完全依赖 Host。

---

## 总结

S3 Doc Tools Provider 实现整体质量扎实。核心架构决策——路径安全在 adapter 边界、fail-closed 白名单、current truncation spec、adapter 投影链——全部正确落地且有目标测试覆盖。LLM-facing tool description 干净，无 OLD ToolRegistry/TruncationManager 语义泄漏。

主要发现是 `list_files` 的相对路径输出与 adapter 的 CWD-relative 解析之间的组合摩擦（Finding 1/2），这是 OLD 行为延续而非 S3 回归，但测试套件未覆盖此路径。其余发现为 docstring 术语陈旧、编码覆盖不一致等低严重度问题。

**建议**：接受当前实现，在 S6 集成测试或后续 work unit 中处理 `list_files → read_file` 相对路径组合问题。修正 docstring 中残留的 "ToolRegistry" 术语。
