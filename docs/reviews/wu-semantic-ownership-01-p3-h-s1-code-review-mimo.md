# Code Review

## Scope

- Mode: current changes
- Branch: `phaseflow/host-issues-control`
- Base: `ba607309` (accepted P3-H plan commit)
- Output file: `docs/reviews/wu-semantic-ownership-01-p3-h-s1-code-review-mimo.md`
- Included scope: S1 changed production files (`dayu/tools/web/web_search_providers.py`, `dayu/tools/web/web_tools.py`, `dayu/tools/web/web_search_projection.py`, `dayu/tools/web/web_tool_projection_text.py`, deleted `dayu/tools/web/web_cancellation_text.py`) and tests (`tests/tools/web/test_web_tools_provider.py`, `tests/tools/test_combined_tools_acceptance.py`)
- Excluded scope: unrelated untracked docs (`docs/cli_ci*`, `docs/reviews/code-review-*`), S2/S3 files, `docs/host/issues-implementation-control.md`
- Parallel review coverage: 无

## Findings

未发现实质性问题。

## Evidence Summary

### Provider facts boundary

- `SearchWebProviderResult` 在 `web_search_providers.py:69-76` 定义，只包含 `query`、`domains`、`total`、`preferred_result`、`results`。
- `search_public_web(...)` 返回类型已改为 `SearchWebProviderResult`（`web_search_providers.py:188`）。
- 旧 provider 内的 `_build_search_web_preferred_summary`、`_build_search_web_next_action`、`_build_search_web_next_action_args`、`_build_search_web_hint` 已全部删除（diff 行 810-925 删除）。
- `_SEARCH_WEB_NEXT_ACTION_FETCH_PAGE`、`_SEARCH_WEB_NEXT_ACTION_REFINE_QUERY`、`_SEARCH_WEB_SNIPPET_PREVIEW_CHARS` 已从 provider 删除。
- `WebSearchCancelledError` 不再携带 `hint` 参数（`web_search_providers.py:87-96`），只保留中性 `message`。
- 测试 `test_search_public_web_provider_result_excludes_llm_guidance` 直接断言 provider result 键集合不含 `hint`/`next_action`/`next_action_args`/`preferred_result_summary`。

### Projection owner

- `SearchWebOutput` 已迁移到 `web_search_projection.py:22-33`。
- `build_search_web_output(provider_result: SearchWebProviderResult) -> SearchWebOutput` 在 `web_search_projection.py:36-63` 实现。
- 投影函数从 `web_tool_projection_text.py` 导入搜索指导常量（`SEARCH_WEB_NEXT_ACTION_FETCH_PAGE`、`SEARCH_WEB_NEXT_ACTION_REFINE_QUERY`、`SEARCH_WEB_NO_RESULT_HINT`、`SEARCH_WEB_NO_RESULT_SUMMARY`）。
- `_search_web_business(...)` 在 `web_tools.py:1516-1532` 先取得 `SearchWebProviderResult`，再调用 `build_search_web_output(...)` 返回 `SearchWebOutput`。

### Cancellation/recovery text owner

- `web_cancellation_text.py` 已删除，文件不存在。
- 源码扫描确认 `dayu`、`tests`、`utils` 中无 `web_cancellation_text` 引用。
- `WEB_CANCELLED_HINT`、`WEB_SEARCH_CANCELLED_MESSAGE`、`WEB_FETCH_CANCELLED_MESSAGE`、`WEB_SEARCH_PROVIDER_UNAVAILABLE_HINT` 定义在 `web_tool_projection_text.py:12-25`。
- `web_tools.py` 从 `web_tool_projection_text.py` 导入这四个常量（`web_tools.py:112-117`）。
- 所有取消 outcome 路径使用投影文本常量而非本地字面量。

### display_name/description owner

- `display_name="联网搜索"` 和 `display_name="抓取网页"` 保留在 `web_tools.py:1191` 和 `web_tools.py:1230` 的 `@tool(...)` 声明处。
- `description` 保留在 `web_tools.py:1188` 和 `web_tools.py:1225`。
- 源码扫描确认 `web_search_providers.py`、`web_search_projection.py`、`web_tool_projection_text.py` 中无 `display_name=` 或 `description=` 命中。
- 测试 `test_web_tool_display_and_description_stay_at_declaration_boundary` 直接断言声明边界。

### Type migration

- `SearchWebOutput` 仅定义在 `web_search_projection.py:22`，`web_search_providers.py` 中无残留。
- `SearchWebProviderResult` 仅定义在 `web_search_providers.py:69`。
- 无兼容性 re-export 或 wrapper alias。
- 测试 fixture 返回类型已改为 `SearchWebProviderResult`。

### Validation

- `pytest tests/tools/web/test_web_tools_provider.py tests/tools/test_combined_tools_acceptance.py -q`：44 passed, 1 skipped, 3 warnings
- `pyright dayu/tools/web/web_search_providers.py dayu/tools/web/web_tools.py dayu/tools/web/web_search_projection.py dayu/tools/web/web_tool_projection_text.py`：0 errors, 0 warnings, 0 informations
- `git diff --check ba607309`：passed

### Source scans

- `rg -n "web_cancellation_text" dayu tests utils`：no matches
- `rg -n "_build_search_web_preferred_summary|_build_search_web_hint|_build_search_web_next_action|_build_search_web_next_action_args" dayu/tools/web/web_search_providers.py tests/tools/web`：no matches
- `rg -n "preferred_result_summary|next_action|next_action_args|\"hint\"" dayu/tools/web/web_search_providers.py`：no matches
- `rg -n "WEB_CANCELLED_HINT|WEB_SEARCH_CANCELLED_MESSAGE|WEB_FETCH_CANCELLED_MESSAGE|WEB_SEARCH_PROVIDER_UNAVAILABLE_HINT" dayu/tools/web tests/tools/web`：常量定义在 `web_tool_projection_text.py`；生产消费者从 `web_tools.py` 导入/使用；测试断言来自 helper
- `rg -n "display_name=|description=" dayu/tools/web/web_tools.py dayu/tools/web/web_search_providers.py dayu/tools/web/web_search_projection.py dayu/tools/web/web_tool_projection_text.py`：命中仅在 `web_tools.py` 声明处

## Open Questions

- 无。

## Residual Risk

- `build_search_web_output(...)` 无直接单元测试；当前通过工具边界测试间接覆盖（有结果和无结果两条路径）。`web_search_projection.py` 和 `web_tool_projection_text.py` 的 pytest-cov 覆盖率因 `pandas`/`numpy` 重复导入问题未能采集（controller validation 已记录为本地工具限制）。
- `web_search_projection.py` 自带 `_normalize_whitespace`（`web_search_projection.py:66-79`），与 `web_tools.py` 中的 `_normalize_whitespace` 语义相同但实现独立。当前无行为差异，但若未来空白规整策略变化需同步两处。
- 真实外部 provider 网络行为未被覆盖；覆盖依赖 monkeypatch 测试和 process-backed 测试。
