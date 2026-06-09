# WU-TOOLS-01-F01-02 Slice 4 Narrow Re-Review

## Metadata

| 项目 | 值 |
|---|---|
| work unit | WU-TOOLS-01-F01-02 |
| gate | Slice 4 narrow re-review |
| slice | Slice 4 - Fins Read Tools Context Injection And Checkpoints |
| plan | `docs/host/wu-tools-01-f01-02-cancellation-plan.md` |
| controller adjudication | `docs/reviews/wu-tools-01-f01-02-slice4-code-review-controller-adjudication.md` |
| fix artifact | `docs/reviews/wu-tools-01-f01-02-slice4-fix-codex.md` |
| re-review target | Accepted findings S4-F1, S4-F2 |
| reviewer | AgentMiMo |
| date | 2026-06-08 |

## Scope

本次 re-review 仅验证 S4-F1 和 S4-F2 两个 accepted findings 是否已正确关闭，以及 fix 是否越界。不覆盖 Slice 4 整体实现质量。

## Validation

### 代码级验证

**S4-F1: read_section parent-title lookup broad except**

- 位置: `dayu/fins/tools/read_runtime.py:466-476`
- 修复前: `except Exception: parent_title = None` 直接吞掉所有异常，包括 `ToolBusinessError(code="tool_cancelled")`。
- 修复后: 在 `except Exception` 之前新增 `except ToolBusinessError as exc` 分支，当 `exc.code == _TOOL_CANCELLED_ERROR_CODE` 时立即 `raise`，其它业务错误仍降级为 `parent_title = None`。
- 验证: 代码逻辑正确。取消异常通过显式分支拦截并重新抛出，非取消业务错误保持原有 best-effort fallback。`_raise_if_fins_cancelled` checkpoint 位于 `get_section_title` 调用前后，确保取消信号在进入降级块前已被观察。

**S4-F2: search_document semantic enrichment broad except**

- 位置: `dayu/fins/tools/read_runtime.py:607-629`（原 `except Exception: pass` 块）
- 修复前: `except Exception: pass` 吞掉所有语义增强异常，包括取消。
- 修复后: 在 `except Exception` 之前新增 `except ToolBusinessError as exc` 分支，当 `exc.code == _TOOL_CANCELLED_ERROR_CODE` 时立即 `raise`，其它异常继续走 `pass` 降级。
- 验证: 代码逻辑正确。与 S4-F1 同根同构的修复模式。

### 测试级验证

**S4-F1 测试: `test_read_section_parent_title_lookup_cancelled_error_is_not_swallowed`**

- 使用 `_ParentTitleLookupCancellingProcessor`，其 `get_section_title` 在被调用时触发 `token.cancel()`。
- 断言: `outcome` 为 `ToolFailedOutcome`，`error == "tool_cancelled"`，`get_section_title_calls == 1`。
- 验证: 测试正确覆盖了父标题查询期间取消被透传的场景。

**S4-F2 测试: `test_search_document_semantic_enrichment_cancelled_error_is_not_swallowed`**

- 使用 monkeypatch 将 `_enrich_sections_with_semantic` 替换为直接抛出 `ToolBusinessError(code="tool_cancelled")` 的 `_raise_tool_cancelled_during_semantic_enrichment`。
- 断言: `outcome` 为 `ToolFailedOutcome`，`error == "tool_cancelled"`，`processor.search_calls == []`（搜索未执行）。
- 验证: 测试正确覆盖了语义增强块内取消被透传的场景。

### 验证结果

| 验证项 | 结果 |
|---|---|
| `pytest tests/fins/test_fins_storage_provider.py tests/fins/test_fins_ingestion_tools.py tests/tools/test_combined_tools_acceptance.py -q` | **47 passed, 3 warnings** |
| `pyright` | **0 errors, 0 warnings, 0 informations** |
| `git diff --check` | **通过** |

## Finding Status

| Finding | 状态 | 依据 |
|---|---|---|
| S4-F1: read_section parent-title lookup broad except | **已关闭** | `except ToolBusinessError` + `exc.code == "tool_cancelled"` → `raise`，位于 `except Exception` 之前；测试覆盖取消透传场景 |
| S4-F2: search_document semantic enrichment broad except | **已关闭** | 同构修复；测试覆盖语义增强块内取消透传场景 |

## 越界检查

| 检查项 | 结果 |
|---|---|
| Host/Engine contract 变更 | 未变更 |
| tool schema 变更 | 未变更（`execution_context` 未暴露到 LLM-facing properties） |
| storage 边界变更 | 未变更 |
| 其它 checkpoint 位置变更 | 未变更（仅在已有 broad-except 块内增加 ToolBusinessError 分支） |
| unrelated type debt | 未处理（符合预期） |
| 允许范围外的文件修改 | 无。仅修改 `fins_tools.py`、`read_runtime.py`、`search_engine.py` 及对应测试 |

## Conclusion

**PASS**

S4-F1 和 S4-F2 均已正确关闭。修复模式一致（在 broad `except Exception` 之前插入 `except ToolBusinessError` + 取消码检查 + re-raise），测试覆盖了取消透传的关键路径。修复未越界，未引入新风险。
