# WU-TOOLS-01-F01-02 Slice 5 Closeout Review — AgentMiMo

## Metadata

- Review target: Slice 5 audit matrix / validation closeout
- Plan reference: `docs/host/wu-tools-01-f01-02-cancellation-plan.md` Section 8 Slice 5 and Section 9 validation
- Closeout artifact under review: `docs/reviews/wu-tools-01-f01-02-slice5-closeout-codex.md`
- Reviewer: AgentMiMo
- Date: 2026-06-08

## Validation

### Uncommitted diff scope

`git diff --stat` 确认变更仅包含：

- `tests/fins/test_fins_ingestion_tools.py` — 新增 source-level guard 测试与辅助函数
- `tests/fins/test_fins_storage_provider.py` — 新增 schema 隔离断言
- `tests/tools/test_doc_tools_provider.py` — 新增 declaration 注入断言与 schema 隔离补强
- `tests/tools/web/test_web_tools_provider.py` — 新增 audit matrix 注入+schema 断言
- `docs/host/issues-implementation-control.md` — gate 状态 bookkeeping 更新
- `docs/reviews/wu-tools-01-f01-02-slice5-closeout-codex.md` — closeout artifact（untracked）

无生产代码变更。符合预期。

### Test execution

| 命令 | 结果 |
|---|---|
| `pytest tests/fins/test_fins_ingestion_tools.py tests/fins/test_fins_ingestion_runtime.py tests/fins/test_fins_storage_provider.py -q` | 69 passed |
| `pytest tests/tools/web/test_web_tools_provider.py tests/tools/test_doc_tools_provider.py tests/tools/test_combined_tools_acceptance.py -q` | 44 passed |
| `pytest` 6 个定向 audit matrix 测试 | 6 passed |
| `pyright` | 0 errors / 0 warnings / 0 informations |
| `git diff --check` | 无输出，exit 0 |

### Source-level verification

独立 Agent 验证生产代码：

- `download_tools.py`: `del context` 已移除，`cancellation_token` 通过 `start_download(..., cancellation_token=cancellation_token)` 传入 runtime。PASS。
- `preprocess_tools.py`: `del context` 已移除，`cancellation_token` 通过 `start_preprocess(..., cancellation_token=cancellation_token)` 传入 runtime。PASS。
- 17 个工具（Web 2 + Doc 5 + Fins read 9 + Fins awaiting 2）的 LLM-facing schema 均不暴露 `execution_context` 或 `cancellation_token`。PASS。

## Findings

### F1: `_is_runtime_start_call` TypeGuard 语义不精确（Non-blocking）

`tests/fins/test_fins_ingestion_tools.py:1256` 使用 `TypeGuard[ast.Call]`，但函数内部还检查 `node.func` 是 `ast.Attribute` 且 `node.func.attr == start_method`。`TypeGuard` 只窄化到 `ast.Call`，不反映完整的运行时形状。

**裁决**：Non-blocking。该函数仅在测试内部使用，唯一调用点 `_assert_context_token_bridge` 不依赖超出 `ast.Call` 的类型窄化。不影响正确性，属于风格瑕疵。后续可改为返回 `bool` 或使用 `TypeIs`。

### 无其他 Finding

- Audit matrix 覆盖完整：Web search/fetch、Doc 五工具、Fins read 九工具、Fins awaiting download/preprocess 全部在矩阵中。
- 新增测试只断言当前期望行为（context 注入、schema 隔离、token 桥接），不恢复旧 no-context 行为。
- Source-level guard 仅用于 behavior test 难以直接观察的 `del context` 与 runtime keyword bridge 边界，符合 plan 要求。
- LLM-facing schema 无 `execution_context` / `cancellation_token` 污染。
- README decision 符合 AGENTS.md 与 README 自身更新约束：本 slice 未修改 `dayu/fins/` 生产代码，测试新增不改变目录/层级/运行方式。
- Remaining risks R1/R2/R3 均有明确 owner/destination。
- 测试辅助函数中文 docstring 完整，类型签名严格，无 `object`/`Any`。

## Conclusion

**PASS**。Slice 5 closeout artifact 准确反映了审计结论，验证命令全部通过，无 blocking finding。唯一的 non-blocking finding（F1 TypeGuard 语义）不影响测试正确性，可作为后续清理项。
