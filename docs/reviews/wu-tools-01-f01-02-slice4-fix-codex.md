# WU-TOOLS-01-F01-02 Slice 4 Accepted Review Fix

## 改动摘要

- 修复 `read_section` 父标题查询 best-effort 降级块：新增 `ToolBusinessError` 专门分支，遇到 `code="tool_cancelled"` 时立即重新抛出，其它业务错误仍保持原有父标题缺失降级。
- 修复 `search_document` 语义增强 best-effort 降级块：新增 `ToolBusinessError` 专门分支，遇到 `code="tool_cancelled"` 时立即重新抛出，其它业务错误仍保持原有语义增强降级。
- 新增两个行为回归测试：
  - `test_read_section_parent_title_lookup_cancelled_error_is_not_swallowed`
  - `test_search_document_semantic_enrichment_cancelled_error_is_not_swallowed`

## 验证结果

- `source .venv/bin/activate && pytest tests/fins/test_fins_storage_provider.py -q`
  - 结果：`19 passed, 3 warnings`
- `source .venv/bin/activate && pytest tests/fins/test_fins_storage_provider.py tests/fins/test_fins_ingestion_tools.py tests/tools/test_combined_tools_acceptance.py -q`
  - 结果：`47 passed, 3 warnings`
- `source .venv/bin/activate && pyright`
  - 结果：`0 errors, 0 warnings, 0 informations`
- `git diff --check`
  - 结果：通过

## 未改项说明

- 未修改 Host / Engine contract。
- 未修改 tool schemas。
- 未修改 storage 边界。
- 未移动或新增其它 checkpoint 位置。
- 未处理 `search_engine` helper 重复问题。
- 未处理 unrelated type debt。
- 已检查 `dayu/fins/README.md` 与 `tests/README.md` 的更新约束；本次不改变稳定架构、capability 边界或测试分层，因此未更新 README。

## Remaining Risks

- `search_document` 仍保留语义增强 best-effort fallback；非取消异常会继续降级为无语义画像搜索，这是既有行为。
- `read_section` 父标题查询仍保留 best-effort fallback；非取消异常会继续返回无父标题语义，这是既有行为。
- 当前修复只覆盖 accepted findings S4-F1 / S4-F2，同类 broad-except 取消透传审计不在本次允许范围内。
