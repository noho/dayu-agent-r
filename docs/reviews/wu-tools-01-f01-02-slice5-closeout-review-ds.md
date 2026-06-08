# WU-TOOLS-01-F01-02 Slice 5 Closeout Review — AgentDS

**执行者**：AgentDS
**日期**：2026-06-08
**审查类型**：Slice 5 audit matrix / validation closeout review
**审查目标**：`docs/host/wu-tools-01-f01-02-cancellation-plan.md` Slice 5 章节
**被审查 closeout artifact**：`docs/reviews/wu-tools-01-f01-02-slice5-closeout-codex.md`

## Metadata

- **审查对象**：Slice 5 新增测试 diff（4 个测试文件，共 +190 行）
- **审查基底**：`bc919866`（Slice 4 accepted commit）
- **uncommitted diff**：`docs/host/issues-implementation-control.md`(状态更新) + 4 个测试文件 + `docs/reviews/wu-tools-01-f01-02-slice5-closeout-codex.md`（Codex closeout artifact）
- **未修改任何生产代码**：符合 Slice 5 预期
- **遗留风险文档**：`docs/host/issues-implementation-control.md` 中 `WU-TOOLS-01-F01-02` 行已追加 Slice 5 closeout artifact 引用

## Validation

### 验证命令 1 — Fins 测试套件

```bash
source .venv/bin/activate && pytest tests/fins/test_fins_ingestion_tools.py tests/fins/test_fins_ingestion_runtime.py tests/fins/test_fins_storage_provider.py -q
```

**PASS** — 69 passed，仅 `edgar` 第三方 deprecation warnings。

关键新增测试全部通过：

- `test_download_tool_cancelled_before_start_returns_cancelled_without_job`
- `test_preprocess_tool_cancelled_before_start_returns_cancelled_without_job`
- `test_awaiting_tool_callables_consume_context_and_bridge_token_to_runtime`
- `test_ingestion_tool_schemas_hide_host_internal_fields`
- `test_fins_read_declarations_request_execution_context_injection`
- `test_fins_read_tool_schemas_do_not_expose_execution_context`
- `test_list_documents_pre_cancel_returns_tool_cancelled`
- `test_search_document_cancellation_during_search_stops_before_all_candidates`
- `test_read_section_cancelled_before_processor_read_returns_tool_cancelled`
- `test_query_xbrl_facts_cancellation_during_filtering_stops_promptly`

### 验证命令 2 — Web/Doc 测试套件

```bash
source .venv/bin/activate && pytest tests/tools/web/test_web_tools_provider.py tests/tools/test_doc_tools_provider.py tests/tools/test_combined_tools_acceptance.py -q
```

**PASS** — 44 passed，仅 `edgar` 第三方 deprecation warnings。

关键新增测试全部通过：

- `test_web_audit_matrix_context_injection_and_schema_no_leak`
- `test_doc_tool_schemas_do_not_expose_execution_context`（扩展后包含 required 检查）
- `test_doc_declarations_request_execution_context_injection`
- `test_doc_tools_cancelled_before_work_return_tool_cancelled`
- `test_search_files_cancelled_during_iteration_stops_before_later_files`
- `test_read_file_cancelled_before_fallback_encoding_returns_tool_cancelled`

### 验证命令 3 — Pyright 类型检查

```bash
source .venv/bin/activate && pyright
```

**PASS** — 0 errors, 0 warnings, 0 informations。pyright 版本 1.1.409，提示新版 1.1.410 可用，不影响验证结果。

### 验证命令 4 — `git diff --check`

**PASS** — 无输出，无空白符违规。

## Findings

### F1 (Audit Matrix Coverage) — PASS，一处 minor gap

| 区域 | 工具数 | 声明注入覆盖 | Schema 不泄漏 | 行为测试覆盖 |
|---|---|---|---|---|
| Web | 2 (`search_web`, `fetch_web_page`) | PASS — `test_web_audit_matrix_context_injection_and_schema_no_leak` | PASS — 同前 | PASS — 已有前序 Slice 测试 |
| Doc | 5 (`list_files`, `get_file_sections`, `search_files`, `read_file`, `read_file_section`) | PASS — `test_doc_declarations_request_execution_context_injection` | PASS — `test_doc_tool_schemas_do_not_expose_execution_context` | PASS — pre-cancel + iteration + fallback 覆盖 |
| Fins read | 9 (`list_documents`, `get_document_sections`, `read_section`, `search_document`, `list_tables`, `get_table`, `get_page_content`, `get_financial_statement`, `query_xbrl_facts`) | PASS — `test_fins_read_declarations_request_execution_context_injection` | PASS — `test_fins_read_tool_schemas_do_not_expose_execution_context` | PASS — pre-cancel + search loop + processor + XBRL filtering |
| Fins awaiting | 2 (`start_fins_download`, `start_fins_preprocess`) | PASS — `test_awaiting_tool_callables_consume_context_and_bridge_token_to_runtime` | **minor gap** — 见下方详情 | PASS — start 前取消 + create/submit 间取消 |

**Minor gap — Fins awaiting schema 检查精确度不足（非阻塞）**

`tests/fins/test_fins_ingestion_tools.py:485` 的 `test_ingestion_tool_schemas_hide_host_internal_fields` 通过检查 `schema_text` JSON 字符串断言不含 `"tool_call_id"`、`"digest"`、`"cursor"`、`"raw job record"`、`"Host"` 等 Host 内部治理字段。但该测试未显式断言 `parameters.properties` 中不含 `"execution_context"` 和 `"cancellation_token"`——这一点与 Web、Doc、Fins read 三组工具的 schema 测试风格不一致。

**分析**：Fins awaiting callable 是 direct tool（非 legacy adapter），`execution_context` 由 ToolRuntime 投影，不经过 JSON schema 参数声明。当前的 `schema_text` 全文检查已提供间接防御，但不具备显式 property 级别断言。若未来 schema 定义方式变更，缺少 property 级别断言可能导致治理字段泄漏不被检测。

**影响**：低。当前 `schema_text` 检查已覆盖 JSON 全文，若 `execution_context` 出现在 schema 中会被字符串匹配捕获（"execution_context" 字符串出现在 schema 则会出现在 `schema_text` 中）。标记为 non-blocking improvement，不要求本 slice 修复。

**建议**（在 `test_ingestion_tool_schemas_hide_host_internal_fields` 中增加显式 property 检查）：
```python
for definition in definitions:
    properties = definition.schema.function.parameters.properties
    assert "execution_context" not in properties
    assert "cancellation_token" not in properties
```

**裁决**：non-blocking finding；可在后续 review gate 或 controller 裁决时决定是否修复。当前不阻塞 closeout。

### F2 (测试不恢复旧 no-context 行为) — PASS

- 全文搜索 `tests/` 目录：不存在 `no_context`、`no-context`、`旧行为`、`old behavior`、`兼容` 等旧行为断言标记。
- 新增测试只断言当前期望：cancellation token bridge 成功、cancel 前不创建 job、schema 无污染、声明有注入。
- Source-level guard `_assert_context_token_bridge`（`tests/fins/test_fins_ingestion_tools.py:1162`）仅用于 `del context` 与 `runtime.start_*(..., cancellation_token=...)` keyword bridge 两个行为测试无法直接观察的边界。使用方式符合 plan 中"source-level guard 只用于 behavior test 难以直接观察的边界"的约束。

### F3 (LLM-facing schema 无 execution_context/cancellation_token 污染) — PASS

- 生产代码：所有工具使用 `execution_context_param_name="execution_context"` 作为 legacy adapter 元数据，该字段不进入 `ToolDefinition.schema.function.parameters` JSON schema。
- Web / Doc / Fins read 三组工具的 schema 测试均显式断言 `parameters.properties` 和 `parameters.required` 中不含 `"execution_context"` 和 `"cancellation_token"`。
- Fins awaiting 工具的 `test_ingestion_tool_schemas_hide_host_internal_fields` 通过全文检查提供间接防御（见 F1 minor gap）。
- 生产代码 review 中的 web_tools.py、doc_tools.py、fins_tools.py、download_tools.py、preprocess_tools.py 均使用 `execution_context: BatchToolExecutionContext | None = None` 作为 Python 函数参数（不暴露给 LLM），cancellation token 通过 private helper 解析后内部传递。

### F4 (README decision 合规) — PASS

- **`dayu/fins/README.md`**：Slice 5 不修改 `dayu/fins/` 生产代码，仅增补测试和 closeout artifact。Fins README 的 `Agent更新约束` 限定的写入范围是"当前代码已实现的 capability 定位、对外接口、公共契约、架构边界"——测试增量不属于该范围。不更新：正确。
- **`tests/README.md`**：Slice 5 新增测试属于同层级矩阵式断言（同一 `tests/fins/`、`tests/tools/` 目录，同一测试运行方式），不新增测试目录、测试层级或运行方式。不更新：正确。
- **`dayu/README.md`**：未触及分层关系、装配方式、Host/Engine public contract 或公共 schema 边界。不更新：正确。
- **design docs**：无 schema 变更，无 contract 变更。不更新：正确。

### F5 (Remaining risks owner/destination) — PASS

Codex closeout artifact 记录的 3 个剩余风险：

| ID | Risk | Owner/Destination 明确性 |
|---|---|---|
| R1 | Awaiting accept 前 orphan job 窗口 | **明确**：controller 转入 WU-WAIT-03 或独立 follow-up；需先在 `docs/host/design.md` / `docs/engine/design.md` 设计 Host awaiting accepted activation contract |
| R2 | 同步 I/O/processor 内部长阻塞无法被 token 抢占中断 | **明确**：accepted residual limitation；后续 provider-specific runtime owner 或 WU-WAIT-03 |
| R3 | Legacy adapter `tool_cancelled` 投影为 failed outcome | **明确**：deferred 至独立 tool adapter cancellation contract WU |

Plan 中的 R4（Fins read runtime 内部 search/XBRL helper checkpoint 深度）已由 Slice 4 实现落地，行为测试覆盖了 search loop 和 XBRL filtering 取消，不在 Slice 5 closeout 中作为 active risk 出现，合理。

三个 residual risk 均有明确的 owner、destination 和收口前提条件。两阶段启动明确 deferred，不默认为当前 WU 责任。

### F6 (验证命令完整并通过) — PASS

见上方 Validation 章节。全部三项 plan 要求的验证命令均已运行并通过。

### F7 (测试和辅助函数合规) — PASS

逐个检查 `tests/fins/test_fins_ingestion_tools.py` 新增代码：

| 函数/符号 | 中文 docstring | 参数/返回/异常说明 | 类型签名 | 无 Any/object |
|---|---|---|---|---|
| `test_awaiting_tool_callables_consume_context_and_bridge_token_to_runtime` | 有 | N/A | `-> None` | PASS |
| `_assert_context_token_bridge` | 有 | Args/Returns/Raises 完整 | 有类型标注 | PASS |
| `_find_class` | 有 | Args/Returns/Raises 完整 | `ast.Module -> ast.ClassDef` | PASS |
| `_find_method` | 有 | Args/Returns/Raises 完整 | `ast.ClassDef -> Union[ast.FunctionDef, ast.AsyncFunctionDef]` | PASS |
| `_is_runtime_start_call` | 有 | Args/Returns/Raises（Returns 含 `True` 说明） | `TypeGuard[ast.Call]` | PASS |
| `TypeGuard` import | N/A | N/A | `from typing import TypeGuard` | PASS — 从 typing 导入，用法正确 |
| `ast` import | N/A | N/A | `import ast` | PASS |

`test_ingestion_tool_schemas_hide_host_internal_fields` 使用 `_schema_text` helper 做字符串级检查——该 helper 原型在文件较早位置定义，方法正确。

`test_doc_tool_schemas_do_not_expose_execution_context` 扩展：新增 `required` 字段检查（`"execution_context" not in required`、`"cancellation_token" not in required`）——与 Web 和 Fins read 的 schema 测试保持一致。

`test_web_audit_matrix_context_injection_and_schema_no_leak`：按名称为 audit matrix 而设，覆盖声明注入和 schema 隔离两项。新增的 `LegacyToolDeclarationCollector` import 路径正确。

## Conclusion

### Overall: PASS

Slice 5 审计矩阵覆盖完整（Web 2 + Doc 5 + Fins read 9 + Fins awaiting 2，共覆盖 18 个工具/入口），新测试只断言当前 cancellation propagation 期望，LLM-facing schema 无治理字段污染，残留风险 owner/destination 明确，验证命令全部通过，类型与 docstring 合规。

**1 个 non-blocking finding**：`test_ingestion_tool_schemas_hide_host_internal_fields`（`tests/fins/test_fins_ingestion_tools.py:485`）仅通过 `schema_text` 全文检查间接防御 schema 污染，未像 Web/Doc/Fins read 测试那样显式断言 `parameters.properties` 不含 `execution_context` 和 `cancellation_token`。建议补充显式 property 级别断言，但当前不阻塞 closeout。

### 未覆盖项

- 无。

### 建议的下一动作

1. Controller 裁决 F1 minor gap 是否需在本 gate 修复或转入后续 WU。
2. Controller 确认 closeout 后推进到下一 gate。
