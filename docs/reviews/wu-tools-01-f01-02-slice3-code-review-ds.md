# WU-TOOLS-01-F01-02 Slice 3 Code Review — AgentDS

## Metadata

- **Review type**: code-review（只读，不修改生产代码）
- **Reviewer**: AgentDS
- **Target**: WU-TOOLS-01-F01-02 Slice 3 — Doc Tools Context Injection And Checkpoints
- **Plan source**: `docs/host/wu-tools-01-f01-02-cancellation-plan.md` Slice 3 (lines 240–284)
- **Design sources**: `docs/host/design.md`, `docs/engine/design.md`
- **Implementation artifact**: `docs/reviews/wu-tools-01-f01-02-slice3-implementation-codex.md`
- **Control doc**: `docs/host/issues-implementation-control.md`
- **Date**: 2026-06-08

## Reviewed scope

- `dayu/tools/doc_tools.py` — 五个 Doc tools 的 context 注入、cancel helpers、checkpoint 植入
- `tests/tools/test_doc_tools_provider.py` — 新增 4 个测试函数 + 2 个辅助类/函数
- `docs/reviews/wu-tools-01-f01-02-slice3-implementation-codex.md` — 实现报告
- `docs/host/issues-implementation-control.md` — controller 状态更新（不作为 correctness 审查重点）

## Validation

### 测试

```
source .venv/bin/activate && pytest tests/tools/test_doc_tools_provider.py tests/tools/test_combined_tools_acceptance.py -q
→ 30 passed, 3 warnings
```

warnings 全部来自第三方 `edgar` deprecation，非本次改动引入。

### 类型检查

```
source .venv/bin/activate && pyright
→ 0 errors, 0 warnings, 0 informations
```

### 已有测试回归

全部 30 个测试通过，包括既有 chaining 测试 (`test_list_and_search_return_paths_can_chain_to_read_tools`)、路径校验测试、envelope 测试、fixture 兼容测试、truncate spec 测试和 ToolRuntime 集成测试。

---

## Findings

### Finding 1 — PASS: 五个 Doc tools 全部通过 execution_context_param_name 注入 context

**证据**:

| 工具 | decorator 声明 | 函数参数 |
|---|---|---|
| `list_files` | `doc_tools.py:278` `execution_context_param_name="execution_context"` | `doc_tools.py:287` `execution_context: BatchToolExecutionContext \| None = None` |
| `get_file_sections` | `doc_tools.py:391` | `doc_tools.py:397` |
| `search_files` | `doc_tools.py:713` | `doc_tools.py:722` |
| `read_file` | `doc_tools.py:937` | `doc_tools.py:952` |
| `read_file_section` | `doc_tools.py:1071` | `doc_tools.py:1085` |

adapter 注入路径（`definition_adapter.py:113-114`）:
```python
if self.declaration.execution_context_param_name is not None:
    keyword_arguments[self.declaration.execution_context_param_name] = context
```

**结论**: 五个工具均声明了 `execution_context_param_name`，业务函数均接收 `BatchToolExecutionContext | None`。✅

### Finding 2 — PASS: execution_context 不进入 LLM-facing schema

**证据**:

- `test_doc_tool_schemas_do_not_expose_execution_context` (`test_doc_tools_provider.py:204-211`) 验证了所有 tool definition 的 `schema.function.parameters.properties` 中不含 `"execution_context"`。
- `execution_context_param_name` 是 `CollectedLegacyTool` 的 metadata 字段，不写入 `@tool(...)` 的 `parameters` dict。adapter 只在 callable 调用时按参数名注入 context，不影响 JSON schema。

**结论**: LLM-facing schema 零泄漏。✅

### Finding 3 — PASS: CancellationToken 只从 BatchToolExecutionContext 读取，无工具私有 cancel 状态

**证据**:

- `_resolve_doc_cancellation_token` (`doc_tools.py:115-132`): 唯一读取路径是 `execution_context.cancellation_token`。
- 五个工具函数均通过 `cancellation_token = _resolve_doc_cancellation_token(execution_context)` 解析 token，解析后的局部变量 `cancellation_token: CancellationToken | None` 只在当前调用内使用。
- 不在模块级、类实例或闭包中存储 cancel 状态。
- `_raise_if_doc_cancelled` (`doc_tools.py:135-150`) 和 `_raise_doc_cancelled` (`doc_tools.py:153-174`) 只观察 `is_cancelled()` 和 `cancel_reason()`，不修改 token。
- 无工具私有 `_cancelled` flag、无工具级 cancel 状态机。

**结论**: Host 取消真源未被替代或绕过。✅

### Finding 4 — PASS: checkpoint 覆盖 plan 要求的全部边界

**Plan 要求 vs 实现对照**:

| Plan checkpoint 要求 | 实现位置 | 状态 |
|---|---|---|
| `list_files`: glob 前 | `doc_tools.py:317` `_raise_if_doc_cancelled` 在 `rglob`/`glob` 前 | ✅ |
| `list_files`: 文件迭代内 | `doc_tools.py:325` 在 `for file_path in all_files` 循环体首行 | ✅ |
| `list_files`: return 前 | `doc_tools.py:346` 在 `return` 前 | ✅ |
| `get_file_sections`: processor 创建前 | `doc_tools.py:423` | ✅ |
| `get_file_sections`: processor list 后 | `doc_tools.py:490` 在 `_sections_via_processor` 内 `list_sections()` 后 | ✅ |
| `get_file_sections`: fallback 全量读取前 | `doc_tools.py:429` | ✅ |
| `get_file_sections`: Markdown 提取前 | `doc_tools.py:438` | ✅ |
| `search_files`: rglob 前 | `doc_tools.py:755` | ✅ |
| `search_files`: 每个文件迭代内 | `doc_tools.py:756` 循环体首行 | ✅ |
| `search_files`: processor search 前 | `doc_tools.py:770` 在 `_search_via_processor` 调用前；`doc_tools.py:827` 在 `_search_via_processor` 内部 | ✅ |
| `search_files`: line scan 前 | `doc_tools.py:783` 在 `_search_via_line_scan` 调用前；`doc_tools.py:871` 在 `_search_via_line_scan` 内部 | ✅ |
| `search_files`: return 前 | `doc_tools.py:797` | ✅ |
| `read_file`: 每个 encoding attempt 前 | `doc_tools.py:983` 在 `for encoding in encodings` 循环内 | ✅ |
| `read_file`: readlines 后 | `doc_tools.py:986` | ✅ |
| `read_file`: 行范围处理前 | `doc_tools.py:1000` | ✅ |
| `read_file_section`: processor 创建前 | `doc_tools.py:1115` | ✅ |
| `read_file_section`: processor.read_section 前 | `doc_tools.py:1129` | ✅ |
| `read_file_section`: 子章节遍历前 | `doc_tools.py:1176` 在 `_get_section_children` 内 `list_sections()` 前；`doc_tools.py:1184` 在子节点遍历循环内 | ✅ |

**额外发现 — `_get_section_children` 和 `_search_via_processor` 的 `tool_cancelled` 重抛出**:

- `_get_section_children` (`doc_tools.py:1178-1180`): 原先 `except Exception:` 会吞掉 `ToolBusinessError`，现在显式重抛出 `tool_cancelled`。
- `_search_via_processor` (`doc_tools.py:830-831`): 同上。
- `_search_via_line_scan` (`doc_tools.py:874`): `except (UnicodeDecodeError, OSError)` 不会捕获 `ToolBusinessError`，无需额外处理。

**结论**: checkpoint 覆盖完整，取消异常不被吞掉。✅

### Finding 5 — PASS: 已有异常行为未被破坏

**证据**:

- `FileAccessError`: `doc_tools.py:313` (list_files is_dir), `doc_tools.py:750` (search_files is_dir), `doc_tools.py:993` (read_file encoding exhausted) — 抛出路径和条件均未改变。
- `ToolArgumentError`: `doc_tools.py:1010` (start_line < 1), `doc_tools.py:1012` (end_line < start_line), `doc_tools.py:1118` (unsupported format), `doc_tools.py:1132` (invalid ref) — 抛出路径和条件均未改变。
- `FileNotFoundError`: 不在 `doc_tools.py` 中直接抛出，由 `Path` 操作自然产生。
- 路径校验: 仍在 `definition_adapter.py` 的 `project_tool_call_arguments` → `ToolPathValidationPolicy` 中完成，未在工具函数体内新增 policy。
- 测试 `test_path_validation_failure_does_not_enter_migrated_function_body` 通过，验证路径校验失败不进入函数体。
- 测试 `test_disallowed_path_returns_failed_outcome` 通过。

**结论**: 现有错误处理行为完整保留。✅

### Finding 6 — PASS: 测试覆盖五工具 pre-cancel、schema 不泄漏、search_files iteration stop、read_file fallback stop

**测试矩阵**:

| 测试 | 覆盖范围 | 质量评估 |
|---|---|---|
| `test_doc_tools_cancelled_before_work_return_tool_cancelled` (parametrized × 5) | 五个工具 pre-cancel → `tool_cancelled` | 真实路径，通过 `ToolDefinition.callable` + `BatchToolExecutionContext` 执行，非 source-only |
| `test_doc_tool_schemas_do_not_expose_execution_context` | 所有工具 schema 不含 `execution_context` | 通过 `definition.schema.function.parameters.properties` 断言 |
| `test_search_files_cancelled_during_iteration_stops_before_later_scan` | search_files 遍历中取消，不扫描后续文件 | monkeypatch `_try_create_processor` + `_search_via_line_scan`，真实 `_raise_if_doc_cancelled` 触发 |
| `test_read_file_cancelled_after_first_failed_encoding_stops_fallback` | read_file 首个编码失败触发取消，不尝试 fallback | monkeypatch `builtins.open`，真实 encoding loop checkpoint |

**brittle 风险评估**:

- `test_search_files_cancelled_during_iteration_stops_before_later_scan`: monkeypatch 目标是模块级私有函数 `doc_tools._try_create_processor` 和 `doc_tools._search_via_line_scan`。这些是稳定内部 API，变更风险低。`len(scanned_paths) == 1` 断言结合 `outcome.result.error == "tool_cancelled"` 可有效证明停止行为。
- `test_read_file_cancelled_after_first_failed_encoding_stops_fallback`: monkeypatch `builtins.open` 风险较高（全局影响），但 `fake_open` 对非目标文件转发到 `original_open`，隔离充分。`attempted_encodings == ["utf-8"]` 直接证明 fallback 未执行。
- 无 source-only 断言（如检查源码字符串），全部通过行为验证。

**结论**: 测试覆盖真实、无伪覆盖。✅

### Finding 7 — INFO: `_sections_via_processor` 中预存 `except Exception: pass` 模式

**位置**: `doc_tools.py:500`

```python
try:
    for tbl in processor.list_tables():
        sec_ref = tbl.get("section_ref")
        if sec_ref:
            section_table_map.setdefault(sec_ref, []).append(tbl.get("table_ref", ""))
except Exception:
    pass  # 部分 processor 可能不支持 list_tables
```

**分析**: 此 `except Exception: pass` 是 Slice 3 之前的既有代码。当前 checkpoint 在该 try 块前后（`doc_tools.py:490` 和后续），不在 try 块内部。因此 `ToolBusinessError` 不会在此处被吞掉。但如果未来有人在 `processor.list_tables()` 循环内部加 checkpoint，`_raise_if_doc_cancelled` 抛出的 `ToolBusinessError` 会被静默吞掉。

**严重性**: 低（预存模式，非本次引入；当前 checkpoint 布局安全）

**建议**: 后续可收紧为 `except Exception as exc: if isinstance(exc, ToolBusinessError) and exc.code == "tool_cancelled": raise`（与 `_get_section_children` / `_search_via_processor` 的重抛出模式一致）。但这是 defensive hardening，非本 Slice scope。

### Finding 8 — INFO: `_try_create_processor` 返回类型未标注

**位置**: `doc_tools.py:456`

```python
def _try_create_processor(path: Path):
```

**分析**: 函数体 `return create_doc_file_processor(path)` 或 `return None`，返回类型应为 `DocumentProcessor | None`（或 Protocol）。此函数是 Slice 3 之前已有的，本次未修改其签名，因此不算是本 Slice 扩散类型债。但该函数在 `_search_via_processor`、`_search_via_line_scan`、`_sections_via_processor`、`_get_section_children` 等 helpers 的 `processor` 参数上形成连锁的 untyped 传播。

**严重性**: 低（预存类型债，pyright 0 errors）

**建议**: 后续独立清理 PR 中补充 `processor` 参数类型。

### Finding 9 — INFO: 无 `get_file_sections` fallback 路径取消专项测试

**分析**: Plan Slice 3 要求 "pre-cancel each tool returns tool_cancelled" 已通过 parametrized 测试覆盖。`get_file_sections` 的 fallback 路径（processor 创建失败 → `_read_file_lines` → Markdown extraction）有 checkpoint（`doc_tools.py:429`, `doc_tools.py:438`），但没有专项测试验证 processor 创建成功后、在 `list_sections()` 与 `list_tables()` 之间取消的行为。

**严重性**: 低（pre-cancel 覆盖了入口取消；fallback 路径的 checkpoint 位置明确、逻辑简单，回归风险低）

### Finding 10 — INFO: `list_files` pre-cancel 对不存在目录返回 `tool_cancelled` 而非 `FileAccessError`

**位置**: `doc_tools.py:317` checkpoint 在 `is_dir()` 检查（`doc_tools.py:313`）之前。

**分析**: 若 token 已取消且目录不存在，`list_files` 返回 `tool_cancelled` 而非 `FileAccessError`。这是正确的优先级：Host 已取消操作，返回取消状态比返回参数校验错误更准确。与 Engine cancellation commit boundary 语义一致（`docs/engine/design.md` 第 409-421 行）。但行为变更值得在实现报告中记录。

**严重性**: 信息级

---

## Open questions

1. **`_sections_via_processor` 中 `except Exception: pass` 是否需要在当前 Slice 中修复？** → 不需要。预存模式，当前 checkpoint 布局安全。可作为后续 defensive hardening。

2. **`_try_create_processor` 和 helpers 的 `processor` 参数类型注解是否需要在当前 Slice 补齐？** → 不需要。预存类型债，非本 Slice 引入或扩散。pyright 当前 0 errors。

3. **是否需要为 `get_file_sections` fallback 取消路径补充测试？** → Plan 未要求，但可作为后续测试增强。当前 pre-cancel 测试已覆盖入口取消。

---

## Conclusion

**PASS** — 无 blocking finding。

Slice 3 实现完整满足 plan 全部要求：

- 五个 Doc tools 均通过 `execution_context_param_name` 注入 `BatchToolExecutionContext`，execution_context 不进入 LLM-facing schema。
- `CancellationToken` 只从 `BatchToolExecutionContext` 读取，无工具私有 cancel 状态，Host cancel 真源未被替代。
- checkpoint 覆盖 plan 要求的全部边界：glob/迭代/return、processor 创建/读取、encoding fallback、子章节遍历。取消异常不被 `except Exception` 吞掉。
- `FileAccessError`、`ToolArgumentError`、`FileNotFoundError` 行为未破坏；路径校验仍在 provider/adapter 层。
- 测试覆盖五工具 pre-cancel、schema 不泄漏、search_files iteration stop、read_file fallback stop，无 brittle 伪覆盖。
- AGENTS.md 合规：中文 docstring，类型签名无新增 `Any`/`object`/无类型参数，pyright 0 errors。
- 三个 INFO 级发现均为预存模式或覆盖增强建议，非 blocking。
