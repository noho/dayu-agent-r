# WU-TOOLS-01-F01-02 Slice 5 S5-F1 Re-Review

## Metadata

- Work unit: `WU-TOOLS-01-F01-02`
- Gate: Slice 5 closeout S5-F1 re-review
- Reviewer: AgentDS
- Design sources: `docs/host/wu-tools-01-f01-02-cancellation-plan.md`, `docs/host/design.md`
- Reviewed artifacts:
  - `docs/reviews/wu-tools-01-f01-02-slice5-closeout-review-controller-adjudication.md`
  - `docs/reviews/wu-tools-01-f01-02-slice5-fix-codex.md`
- Review target: `tests/fins/test_fins_ingestion_tools.py` (unstaged diff from HEAD `84f6dca6`)
- Date: 2026-06-08

## Validation

| Command | Result | Notes |
|---|---|---|
| `pytest tests/fins/test_fins_ingestion_tools.py tests/fins/test_fins_ingestion_runtime.py tests/fins/test_fins_storage_provider.py -q` | 69 passed | 仅第三方 edgar deprecation warnings |
| `pytest tests/tools/web/test_web_tools_provider.py tests/tools/test_doc_tools_provider.py tests/tools/test_combined_tools_acceptance.py -q` | 44 passed | 仅第三方 edgar deprecation warnings |
| `pyright` | 0 errors, 0 warnings, 0 informations | 版本 1.1.409 |
| `git diff --check` | clean | 无 whitespace 错误 |

所有验证结果与 `docs/reviews/wu-tools-01-f01-02-slice5-fix-codex.md` 报告一致。

## Findings

### Finding 1 — S5-F1-FIX-CORRECT (PASS)

**断言**: S5-F1 已被正确修复。

**证据**:

`test_ingestion_tool_schemas_hide_host_internal_fields` (lines 506-519) 的 for 循环体内新增：

```python
properties = definition.schema.function.parameters.properties
required = definition.schema.function.parameters.required
assert "execution_context" not in properties
assert "cancellation_token" not in properties
assert "execution_context" not in required
assert "cancellation_token" not in required
```

这四条断言在 `schema_text = _schema_text(definition)` 之前执行，覆盖了 controller adjudication 要求的全部四个 guard 点：

- `execution_context` 不在 `properties` 中
- `cancellation_token` 不在 `properties` 中
- `execution_context` 不在 `required` 中
- `cancellation_token` 不在 `required` 中

原有 `schema_text` 全文检查（`tool_call_id`、`digest`、`cursor`、`raw job record`、`Host`）完整保留在第 514-519 行。

**裁决**: PASS。S5-F1 需求已精确满足。

### Finding 2 — S5-F1-SCOPE-DRIFT (WARNING)

**断言**: 修复中包含了超出 controller adjudication 范围的额外改动。

**证据**:

Controller adjudication 仅要求对 `test_ingestion_tool_schemas_hide_host_internal_fields` 补充显式 `properties`/`required` 断言。实际 diff 额外引入了：

| 新增内容 | 说明 |
|---|---|
| `import ast` | 新 import |
| `TypeGuard` (from typing) | 新 import |
| `_REPO_ROOT`, `_DOWNLOAD_TOOLS_PATH`, `_PREPROCESS_TOOLS_PATH` | 三个模块级常量 |
| `test_awaiting_tool_callables_consume_context_and_bridge_token_to_runtime` | 全新测试函数 |
| `_assert_context_token_bridge` | 私有辅助函数 |
| `_find_class` | 私有辅助函数 |
| `_find_method` | 私有辅助函数 |
| `_is_runtime_start_call` | 私有辅助函数（TypeGuard） |

这些额外改动共约 110 行，占本次 diff（136 行新增）的 ~80%。

**分析**:

新增的 AST 级 guard test 实现的是 Slice 5 plan 中已规划但未在 closeout 前完成的检查项："Fins awaiting: direct callables consume context and do not `del context`"（plan Section 8 Slice 5）。该检查属于 plan 建议的 source-level guard test 范畴——当行为测试无法直接观察边界时使用，而 `del context` 正属于此类：如果 token 在 delete 前已被提取，行为测试仍能通过但代码防御力下降。

该测试不修改生产代码，不触及 control doc 或其他测试文件，所有验证通过。

**裁决**: WARNING（非阻塞）。S5-F1 核心修复正确，额外改动虽不在 controller 指定范围内，但均在 `tests/fins/test_fins_ingestion_tools.py` 内，不触碰生产代码，且补齐了 Slice 5 plan 已规划的 audit 覆盖。建议 controller 确认接受此 scope 扩展或要求回退无关部分。

### Finding 3 — FIX-ARTIFACT-UNDERREPORT (INFO)

**断言**: `docs/reviews/wu-tools-01-f01-02-slice5-fix-codex.md` 未完整描述实际改动。

**证据**:

Fix artifact 的 Changes 节仅声明了 `test_ingestion_tool_schemas_hide_host_internal_fields` 的修改，未提及 Finding 2 中列出的新增 import、常量、测试函数和辅助函数。

其 Validation 节和 Remaining Risks 节的结论与独立验证一致，无事实性错误。

**裁决**: INFO（非阻塞）。artifact 的验证结论准确，但 Changes 描述不完备。

### Finding 4 — NO-PRODUCTION-DRIFT (PASS)

**断言**: 修复未触及生产代码或 control doc。

**证据**:

`git diff --stat` 仅涉及 `tests/fins/test_fins_ingestion_tools.py` 一个文件。未修改 `dayu/fins/`、`dayu/tools/`、`dayu/host/`、`dayu/engine/` 下的任何生产代码。未修改 control doc 或其他 review artifact。

**裁决**: PASS。

### Finding 5 — LLM-SCHEMA-GUARD (PASS)

**断言**: 修复符合 CLAUDE.md Agent 语义约束：Host 内部治理字段不得暴露给模型 schema。

**证据**:

新增断言直接锁定 LLM-facing JSON Schema 的两个入口：
- `parameters.properties` — 模型可见的参数定义
- `parameters.required` — 模型可见的必填字段列表

`execution_context` 和 `cancellation_token` 是 adapter 注入 metadata，经由 `execution_context_param_name` 配置注入工具调用，而非模型参数。新增断言确保这两个字段不会意外泄漏到 LLM-facing schema，与 Web、Doc、Fins read 族已有的同类 guard 对齐。

原有 `schema_text` 全文检查继续覆盖 `tool_call_id`、`digest`、`cursor` 等 Host 内部标识。

**裁决**: PASS。

## Conclusion

**PASS** — 无 blocking finding。

S5-F1 核心修复（`properties`/`required` 显式断言）正确、完整，所有验证通过。额外引入的 AST 级 source guard test 属于 Slice 5 plan 已规划的 audit 覆盖，不触及生产代码，但超出 controller adjudication 的窄修复范围。建议 controller 知悉 Finding 2 (SCOPE-DRIFT) 和 Finding 3 (ARTIFACT-UNDERREPORT)，决定是否接受当前完整 diff 或要求回退至仅 S5-F1 修复。

LLM-facing schema 语义约束维持有效。未引入新的 residual risk。
