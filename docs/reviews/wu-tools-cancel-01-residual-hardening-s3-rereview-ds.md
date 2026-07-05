# Code Review — WU-TOOLS-CANCEL-01 S3 Rereview

## Scope

- **Mode**: current changes (against HEAD since commit `4f9df113`)
- **Branch**: `phase/wu-tools-cancel-01`
- **Base**: `4f9df113` (WU-TOOLS-CANCEL-01: accept residual hardening S2B)
- **Output file**: `docs/reviews/wu-tools-cancel-01-residual-hardening-s3-rereview-ds.md`
- **Review type**: targeted re-review of DS-02 and DS-03 fixes, DS-01 rejection rationale, and regression check
- **Prior artifacts**:
  - Original MiMo review: PASS
  - Original DS review: `docs/reviews/wu-tools-cancel-01-residual-hardening-s3-code-review-ds.md` (PASS_WITH_FINDINGS, 3 findings)
- **Included scope**: `dayu/tools/web/web_tools.py`, `tests/fins/test_fins_storage_provider.py` (DS-02/DS-03 fix surfaces); light re-read of `dayu/tools/doc_tools.py` for DS-01 rejection rationale confirmation
- **Excluded scope**: files unchanged since prior DS review (fins_tools.py, doc_tools_provider tests, web_tools_provider tests except as regression)
- **Parallel review coverage**: 无

## Findings

未发现实质性问题。

### 修复验证

#### DS-02 — `_build_fins_aapl_xbrl_workspace` company_meta 写入在批事务外

- **状态**: ✅ 已关闭。
- **证据**: `tests/fins/test_fins_storage_provider.py:1654-1709`。当前代码中 `begin_batch("AAPL")` 在第 1654 行，`try:` 在第 1655 行，`company_repository.upsert_company_meta(...)` 在第 1656 行（已移入 try 块内），`commit_batch(token)` 在第 1706 行，`except Exception: rollback_batch(token)` 在第 1707-1708 行。所有仓储写入操作（company_meta upsert、source_document create、blob store、source_document update）均在同一批事务 try/rollback 窗口内。

#### DS-03 — `_web_process_failed_envelope` 中 `cast(WebPayload, ...)` 绕过类型检查

- **状态**: ✅ 已关闭。
- **证据**: `dayu/tools/web/web_tools.py:1628-1652`。`_web_process_failed_envelope` 返回类型已从 `WebPayload` 改为 `JsonValue`，函数体直接 `return process_tool_failed_envelope(...)`，不再使用 `cast(WebPayload, ...)`。`cast` 导入（第 35 行）仍在 `_build_playwright_success_payload`、`_build_stage_result_internal_diagnostics`、`convert_html_to_markdown` 等多处使用，未产生 unused import。
  - 调用方兼容性：三个调用点（第 494/500/506 行）位于 `_WebProcessTarget.__call__` 内部，该函数返回 `JsonValue`；`_web_process_failed_envelope` 现在也返回 `JsonValue`，类型一致，无隐式 narrowing 风险。

#### DS-01 — Doc 通用 Exception handler 未携带 hint（controller rejected）

- **状态**: ✅ rejection rationale 成立，无需当前修复。
- **证据链**:
  1. `process_tool_failed_envelope` 签名：`hint: str | None = None`——hint 在合约层是可选字段（`dayu/contracts/tool_execution.py:99-101`）。
  2. `ProcessToolFailedEnvelope.hint` 类型：`str | None`（`dayu/contracts/tool_execution.py:52`）。
  3. `ToolResultFailure.hint` 类型：`str | None`——Host 层同样将 hint 视为可选。
  4. 当 `hint=None` 时，`process_tool_failed_envelope` 不将 hint 写入信封（`dayu/contracts/tool_execution.py:120-121`），Host parser 将其归一为 `None`（`dayu/contracts/tool_execution.py:200`）。整个链路对缺失 hint 的语义一致。
  5. Doc 通用 `except Exception` 捕获的是未知非业务异常；在此场景下不存在可操作的具体 recovery action，省略 hint 是合理的退化行为。
  6. 该不对称（Doc 无 hint、Fins 有 `_UNEXPECTED_FAILURE_HINT`）在 S3 之前已存在，S3 未引入或恶化。

### 回归检查

- **Envelope 迁移完整性**: 与上轮 DS 审查一致——`_DOC_PROCESS_*` / `_FINS_PROCESS_*` / `_WEB_PROCESS_*` 零残留；无 `Hint:` 拼接回潮。
- **测试**: `114 passed, 1 skipped`；3 warnings 均为 edgartools 弃用警告，与 S3 无关。
- **类型**: `pyright 0 errors, 0 warnings`（仅 version upgrade notice）。
- **架构边界**: 无新增跨层 import 或反向依赖；Host 仍不 import concrete tools；runtime 仍不依赖上层。
- **`cast` 导入**: `from typing import ... cast` 在 web_tools.py 中仍有 6 处使用（line 587/1406/1592/1902/2197/2288/2566），移除 `_web_process_failed_envelope` 中的 cast 未导致 unused import。

## Open Questions

- 无。

## Residual Risk

- 无新增风险。S3 已知 residual risk（XBRL fixture `source_meta` 字段冗余、Doc/Fins hint 不对称）仍与上轮 DS 审查记录一致，未因本次 fix 放大或缩小。

## 结论

**PASS**

DS-02 和 DS-03 均已正确修复，DS-01 rejection rationale 经合约链路验证成立。无新增 correctness、architecture、type、test 或 fixture 问题。
