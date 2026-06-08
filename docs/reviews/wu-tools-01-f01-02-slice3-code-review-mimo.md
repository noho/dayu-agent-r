# WU-TOOLS-01-F01-02 Slice 3 Code Review — AgentMiMo

## Metadata

| 字段 | 值 |
|---|---|
| Review target | WU-TOOLS-01-F01-02 Slice 3: Doc Tools Context Injection And Checkpoints |
| Plan 真源 | `docs/host/wu-tools-01-f01-02-cancellation-plan.md` §8 Slice 3 |
| Implementation artifact | `docs/reviews/wu-tools-01-f01-02-slice3-implementation-codex.md` |
| Design 真源 | `docs/host/design.md`、`docs/engine/design.md` |
| Reviewer | AgentMiMo |
| Review date | 2026-06-08 |
| Reviewed commit | uncommitted diff on branch `work/wu-tools-01-f01-02-cancellation` |
| Review scope | `dayu/tools/doc_tools.py`、`tests/tools/test_doc_tools_provider.py` |

## Reviewed Scope

本次 review 覆盖 uncommitted diff 中的两个生产/测试文件：

- `dayu/tools/doc_tools.py`：新增 `_resolve_doc_cancellation_token`、`_raise_if_doc_cancelled`、`_raise_doc_cancelled` 三个模块级 helper；五个 Doc tools（`list_files`、`get_file_sections`、`search_files`、`read_file`、`read_file_section`）全部声明 `execution_context_param_name="execution_context"` 并在业务入口接收 `execution_context: BatchToolExecutionContext | None`；按 plan 要求在各工具关键边界补齐协作式 checkpoint；`_sections_via_processor`、`_search_via_processor`、`_search_via_line_scan`、`_get_section_children` 四个 helper 新增 `cancellation_token` 传递参数。
- `tests/tools/test_doc_tools_provider.py`：新增 `_ManualCancellationToken` 测试替身、`_pre_cancel_arguments` 辅助函数、`_context` 改造支持可选 token 注入；新增四个测试覆盖五工具预取消、schema 不泄漏、search_files iteration stop、read_file fallback stop。

以下文件不在 correctness 审查范围内：`docs/host/issues-implementation-control.md`（controller 状态更新）、`docs/reviews/wu-tools-01-f01-02-slice3-implementation-codex.md`（实现报告）。

## Validation

| 命令 | 结果 |
|---|---|
| `pytest tests/tools/test_doc_tools_provider.py tests/tools/test_combined_tools_acceptance.py -q` | 30 passed, 3 warnings（第三方 edgar deprecation warning，非本次改动引入） |
| `pyright dayu/tools/doc_tools.py tests/tools/test_doc_tools_provider.py` | 0 errors, 0 warnings, 0 informations |

## Findings

### F1 — INFO — Pre-existing type debt: `_try_create_processor` 缺少返回类型注解

- **文件**: `dayu/tools/doc_tools.py:456`
- **证据**: `def _try_create_processor(path: Path):` — 无返回类型注解，pyright 推断为 `Unknown`。违反 AGENTS.md「禁止无类型返回值」约束。
- **严重性**: INFO（pre-existing，本 slice 未扩散；pyright 当前配置未报错）
- **本 slice 影响**: 无。本 slice 的新 helper 函数均有完整类型签名。
- **最小修复建议**: `def _try_create_processor(path: Path) -> "DocumentProcessor | None":`（需确认 processor 类型的实际导入路径）。

### F2 — INFO — Pre-existing type debt: `processor` 参数无类型注解

- **文件**: `dayu/tools/doc_tools.py:472-476`（`_sections_via_processor`）、`:809-813`（`_search_via_processor`）、`:1157-1161`（`_get_section_children`）
- **证据**: 三个 helper 的 `processor` 参数均无类型注解。违反 AGENTS.md「禁止无类型参数」约束。
- **严重性**: INFO（pre-existing，本 slice 未引入新的无类型参数）
- **本 slice 影响**: 无。本 slice 新增的 `cancellation_token: CancellationToken | None = None` 参数类型完整。
- **最小修复建议**: 为 `processor` 参数添加 `DocumentProcessor` 类型注解（需确认实际基类/协议）。

### F3 — INFO — Pre-existing type debt: 返回类型使用 `Dict[str, Any]` / `List[Dict[str, Any]]`

- **文件**: 多个工具函数和 helper（如 `list_files:287`、`get_file_sections:398`、`search_files:723`、`read_file:953`、`_sections_via_processor:477`、`_search_via_processor:814` 等）
- **证据**: 所有工具函数返回 `Dict[str, Any]`，helper 返回 `List[Dict[str, Any]]`。`Any` 违反 AGENTS.md 约束。
- **严重性**: INFO（pre-existing，本 slice 未新增 `Any` 类型使用）
- **本 slice 影响**: 无。本 slice 新增的三个 helper 返回类型分别为 `CancellationToken | None`、`None`、`NoReturn`，均不含 `Any`。

### F4 — OBSERVATION — `_sections_via_processor` 中 `list_tables` 异常处理未区分取消

- **文件**: `dayu/tools/doc_tools.py:495-501`
- **证据**:
  ```python
  try:
      for tbl in processor.list_tables():
          ...
  except Exception:
      pass  # 部分 processor 可能不支持 list_tables
  ```
  该 `except Exception: pass` 理论上会吞掉 `ToolBusinessError(code="tool_cancelled")`。
- **严重性**: OBSERVATION（当前不可触达：`processor.list_tables()` 不接收 `cancellation_token`，不会自行抛出 `ToolBusinessError`；且该 try 块前已有 `_raise_if_doc_cancelled` checkpoint，取消信号在进入此块前已被检查）
- **风险**: 若未来某 processor 实现在 `list_tables()` 内部检查取消并抛出 `ToolBusinessError`，该异常会被吞掉。
- **最小修复建议**: 可选地将 `except Exception: pass` 改为 re-raise `tool_cancelled` 的模式（与 `_search_via_processor` 和 `_get_section_children` 保持一致），但当前无 blocking 风险。

## 逐项审查结论

### 1. 五个 Doc tools 是否全部通过 execution_context_param_name 注入 context，且 execution_context 不进入 LLM-facing schema

**PASS**。

- 五个工具的 `@tool` decorator 均声明 `execution_context_param_name="execution_context"`（`:278`、`:391`、`:713`、`:937`、`:1071`）。
- 五个工具函数均接收 `execution_context: BatchToolExecutionContext | None = None`。
- 测试 `test_doc_tool_schemas_do_not_expose_execution_context` 遍历全部五个工具定义，断言 `execution_context` 不在 `properties` 中。
- legacy adapter 在 `definition_adapter.py:113-114` 通过 `execution_context_param_name` 注入 context，不把它加入 JSON schema。

### 2. CancellationToken 是否只从 BatchToolExecutionContext 读取；是否没有工具私有 cancel 状态

**PASS**。

- `_resolve_doc_cancellation_token` 唯一读取 `execution_context.cancellation_token`。
- 三个 helper 均为无状态模块级函数，不维护任何工具私有 cancel 状态。
- 取消信号仅通过 `CancellationToken.is_cancelled()` 观察，不修改 token 状态。
- `_raise_doc_cancelled` 读取 `cancel_reason()` 构造错误消息，但不写入任何状态。

### 3. checkpoint 是否覆盖 plan 要求；是否有异常处理吞掉 ToolBusinessError(code=tool_cancelled)

**PASS**。

| 工具 | Plan 要求 checkpoint | 实际 checkpoint 位置 | 结论 |
|---|---|---|---|
| `list_files` | before glob, inside iteration, before return | `:317` (before glob), `:325` (inside iteration), `:346` (before return) | 完全覆盖 |
| `get_file_sections` | before processor creation, after processor list, before fallback full read, before markdown extraction | `:423` (before processor), `:490` (after list_sections via helper), `:429` (before fallback read), `:438` (before markdown extraction) | 完全覆盖 |
| `search_files` | before rglob, inside iteration, before processor search/line scan, before return | `:754` (before rglob), `:756` (inside iteration), `:770`/`:783` (before processor/line_scan), `:797` (before return) | 完全覆盖 |
| `read_file` | before each encoding attempt, after readlines, before range extraction | `:983` (before each attempt), `:986` (after readlines), `:1000` (before range extraction) | 完全覆盖 |
| `read_file_section` | before processor creation, before read_section, before child traversal | `:1115` (before processor), `:1129` (before read_section), `:1140` (before child traversal) | 完全覆盖 |

异常处理审查：

- `_search_via_processor:830-832`：正确 re-raise `ToolBusinessError(code="tool_cancelled")`。
- `_get_section_children:1178-1180`：正确 re-raise `ToolBusinessError(code="tool_cancelled")`。
- `_count_file_lines:542-546` 和 `_read_file_lines:558-566`：catch `(UnicodeDecodeError, OSError)`，不含 `ToolBusinessError`，不会吞掉取消。
- `_sections_via_processor:495-501` `list_tables` 异常处理：见 F4 observation，当前不可触达。

### 4. Existing FileAccessError、ToolArgumentError、FileNotFoundError 行为是否未被破坏

**PASS**。

- `list_files:312-313`：`FileAccessError` 在 checkpoint 之前触发，不受取消影响。
- `search_files:749-750`：同上。
- `read_file:993-997`：`FileAccessError` 在编码循环全部失败后抛出，取消检查在循环内提前退出。
- `read_file_section:1118-1125`：`ToolArgumentError` 在 processor 为 None 时抛出，取消检查在前一行。
- `read_file_section:1132-1137`：`KeyError` → `ToolArgumentError`，catch 范围窄，不影响 `ToolBusinessError`。
- path validation 仍在 provider/adapter 层，tool function 内未新增路径策略。

### 5. 测试是否真正覆盖且无 brittle 或伪覆盖

**PASS**。

| 测试 | 覆盖目标 | 验证方式 | 结论 |
|---|---|---|---|
| `test_doc_tool_schemas_do_not_expose_execution_context` | schema 不泄漏 | 遍历五工具 definition，断言 properties 无 `execution_context` | 真实行为覆盖 |
| `test_doc_tools_cancelled_before_work_return_tool_cancelled` (parametrized × 5) | 五工具预取消 | token 预设取消 → 调用 callable → 断言 `ToolFailedOutcome(error="tool_cancelled")` | 真实行为覆盖 |
| `test_search_files_cancelled_during_iteration_stops_before_later_scan` | iteration stop | monkeypatch `_search_via_line_scan` 首文件触发取消 → 断言 `len(scanned_paths) == 1` | 真实行为覆盖，通过 monkeypatch 强制走 line scan 路径并验证迭代停止 |
| `test_read_file_cancelled_after_first_failed_encoding_stops_fallback` | fallback stop | monkeypatch `builtins.open` 在 utf-8 失败后设取消 → 断言 `attempted_encodings == ["utf-8"]` | 真实行为覆盖，验证取消后不尝试 fallback 编码 |

- `_ManualCancellationToken` 正确实现 `CancellationToken` Protocol 的三个方法。
- `_pre_cancel_arguments` 为每个工具构造最小合法参数，确保取消发生在业务逻辑前。
- `_context` 改造支持可选 `cancellation_token` 参数，默认使用 `_OpenCancellationToken`，向后兼容。
- 现有 chaining test（`test_list_and_search_return_paths_can_chain_to_read_tools`）仍通过，证明取消注入不破坏正常路径。

### 6. AGENTS.md 合规

**PASS（本 slice 未新增类型债）**。

- 新增函数的类型签名完整：`_resolve_doc_cancellation_token`、`_raise_if_doc_cancelled`、`_raise_doc_cancelled` 均有完整参数/返回值类型。
- 新增参数 `cancellation_token: CancellationToken | None = None` 类型完整。
- 中文 docstring：所有新增函数和修改的函数参数说明均为中文。
- 未新增 `Any`、`object`、无类型参数或返回值。
- 既有类型债（`_try_create_processor` 无返回类型、`processor` 参数无类型、`Dict[str, Any]` 返回类型）均未被扩散。

## Open Questions

无 blocking question。

## Conclusion

**PASS**。

本次 Slice 3 实现严格对齐 plan 要求：五个 Doc tools 全部通过 `execution_context_param_name` 注入 `BatchToolExecutionContext`，`execution_context` 不进入 LLM-facing schema；取消信号仅从 Host 注入的 `CancellationToken` 观察，无工具私有 cancel 状态；checkpoint 完整覆盖 plan 列出的所有边界；现有 `FileAccessError`/`ToolArgumentError` 行为未被破坏；测试真实覆盖五工具预取消、schema 不泄漏、iteration stop、fallback stop 四个行为维度；本 slice 未新增类型债。

三个 INFO-level 发现均为 pre-existing 类型债（`_try_create_processor` 缺返回类型、`processor` 参数无类型、`Dict[str, Any]` 返回类型），不影响本 slice correctness，建议后续独立清理。一个 OBSERVATION（`_sections_via_processor` 的 `list_tables` 异常处理）当前不可触达，可在后续 processor 接口演进时统一处理。
