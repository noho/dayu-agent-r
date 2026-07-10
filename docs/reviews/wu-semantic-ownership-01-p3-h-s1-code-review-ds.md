# WU-SEMANTIC-OWNERSHIP-01 P3-H S1 Code Review (AgentDS)

## Scope

- Mode: current changes
- Branch: `phaseflow/host-issues-control`
- Base: `ba607309` (accepted plan commit)
- Output file: `docs/reviews/wu-semantic-ownership-01-p3-h-s1-code-review-ds.md`
- Included scope: S1 Web search provider facts and Web tool projection text implementation only
- Excluded scope:
  - Unrelated untracked docs (`docs/cli_ci*`, prior `code-review-*` artifacts)
  - `docs/host/issues-implementation-control.md` (control doc, not S1 production code)
  - S2 (Fins direct/wait) and S3 (SEC downloader) — not yet implemented
  - `dayu/fins/`, `dayu/tools/web/web_recovery.py` (outside S1 except shared cancellation text)
- Parallel review coverage: 无（单一 reviewer 全量走读）

## Review Method Summary

1. 阅读 plan (`docs/host/wu-semantic-ownership-01-p3-h-llm-ui-copy-boundary-plan.md`) 确认 S1 的 exact allowed changes 与 stop condition。
2. 阅读 implementation artifact 与 controller validation 确认声称的变更与验证结果。
3. 完整走读 6 个 changed/new/deleted 生产文件与 2 个测试文件。
4. 沿 `search_public_web → _search_web_business → build_search_web_output → completed_outcome` 完整链路逐行走读。
5. 沿取消链路 `_raise_if_search_cancelled → WebSearchCancelledError → _call_search_web → host_cancelled_outcome` 逐行走读。
6. 沿 fetch 取消链路 `_raise_if_host_cancelled → _raise_fetch_cancelled → WebToolCancelledError → _call_fetch_web_page → host_cancelled_outcome` 逐行走读。
7. 执行 adversarial failure pass 与 semantic ownership drift pass。
8. 验证 source scans、pyright、pytest、git diff --check。

## Findings

未发现实质性问题。

S1 实现的语义所有权边界与 plan 完全对齐：

- **Provider boundary**: `SearchWebProviderResult` 仅包含 `query`, `domains`, `total`, `preferred_result`, `results` 五个 provider 事实字段，不含 `hint`, `next_action`, `next_action_args`, `preferred_result_summary`。`search_public_web` 返回类型与 docstring 均已更新。（`web_search_providers.py:69-76`, `:172-188`, `:277-283`）
- **Projection boundary**: `SearchWebOutput` 与 `build_search_web_output` 位于 `web_search_projection.py`，独占地从 provider 事实构建 LLM-facing guidance 字段。（`web_search_projection.py:22-63`）
- **Cancellation text owner**: `web_tool_projection_text.py` 拥有 `WEB_SEARCH_CANCELLED_MESSAGE`, `WEB_FETCH_CANCELLED_MESSAGE`, `WEB_CANCELLED_HINT`, `WEB_SEARCH_PROVIDER_UNAVAILABLE_HINT` 以及 search guidance 常量。`web_cancellation_text.py` 已删除，source scan 确认无剩余引用。
- **Tool declaration boundary**: `display_name` 与 `description` 保持在 `@tool(...)` 声明处。（`web_tools.py:1188,1191,1225-1227,1230`）
- **Tool outcome boundary**: `_call_search_web` 和 `_call_fetch_web_page` 正确消费 projection text 常量构造 cancelled/failed outcome；provider 的 `WebSearchCancelledError.message`（中性取消说明 "工具调用已取消"）不会被投影到 LLM。（`web_tools.py:1338-1339,1370-1377,1437-1438,1458-1464`）

### 逐链路验证

**成功路径**:
```
search_public_web(...) → SearchWebProviderResult (仅 provider 事实)
  → _search_web_business(...) 调用 build_search_web_output(provider_result)
    → SearchWebOutput (含 guidance 字段)
      → completed_outcome(...) → LLM 可见
```
- Provider 不生成 LLM guidance（`web_search_providers.py:277-283`）
- Projection 是 guidance 唯一真源（`web_search_projection.py:36-63`）
- 公共 JSON shape 保持稳定（`web_search_projection.py:22-33`）

**搜索取消路径**:
```
cancellation_token.is_cancelled() → True
  → _raise_if_search_cancelled(...) 抛出 WebSearchCancelledError("工具调用已取消")
    → _call_search_web 捕获 → host_cancelled_outcome(
        message=WEB_SEARCH_CANCELLED_MESSAGE,
        hint=WEB_CANCELLED_HINT)
```
- `WebSearchCancelledError.message` 被丢弃，替换为 projection 常量（`web_tools.py:1370-1377`）
- 深层取消携带治理字段时 message/hint 仍使用 sanitized 常量（`web_tools.py:1230-1233` 测试验证）

**抓取取消路径**:
```
cancellation_token.is_cancelled() → True
  → _raise_if_host_cancelled → _raise_fetch_cancelled()
    → WebToolCancelledError(WEB_FETCH_CANCELLED_MESSAGE, WEB_CANCELLED_HINT)
      → _call_fetch_web_page 捕获 → host_cancelled_outcome(...)
```
- `WebToolCancelledError` 直接使用 projection 常量构造（`web_tools.py:741-744`）

**Process target 取消防御路径**:
```
_WebProcessCancellationToken (永不取消) → 正常路径不触发取消
  若因代码 bug 触发 → 转为 execution_error failed envelope
```
- 防御代码正确 fail-closed（`web_tools.py:504-509`）

### Adversarial Failure Pass

逐项检查以下风险面，均未发现 S1 引入的新缺陷：

| 风险面 | 检查结果 |
|---|---|
| 参数缺失/类型错误 | `validate_and_project_arguments` 在 adapter 边界处理；测试覆盖（`web_tools.py:1321-1331`） |
| 空 query | provider `search_public_web` 抛出 `ValueError`（`web_search_providers.py:216-217`） |
| 取消竞态 | provider lock 前后双重检查 token（`web_tools.py:1334-1339,1352-1358`） |
| 深层取消治理字段泄漏 | provider 抛出携带治理字段的 `WebSearchCancelledError` 时，outcome 使用 projection 常量覆盖（测试：`test_web_tools_provider.py:1158-1233`） |
| provider 全部不可用 | 投影为 `search_provider_unavailable` failed outcome + `WEB_SEARCH_PROVIDER_UNAVAILABLE_HINT`（`web_tools.py:1378-1386`） |
| 空结果投影 | `preferred_result=None` → `next_action=refine_query`, `next_action_args={}`, hint 建议改写 query（`web_search_projection.py:134-136,155-156,176-177`） |
| 旧模块残留引用 | source scan 确认 `web_cancellation_text` 无任何残留 import |
| 兼容性 re-export | 不存在；旧模块直接删除 |
| Provider 内部 LLM prose 残留 | source scan 确认 provider 内无 `preferred_result_summary`, `next_action`, `next_action_args`, `hint` 字段生成 |
| display_name/description owner 漂移 | source scan 确认仅在 `@tool(...)` 声明处 |

### Semantic Ownership Drift Pass

| 语义事实 | 正确 owner | 实际 owner | 漂移？ |
|---|---|---|---|
| 搜索结果行 (title/url/snippet/date) | `web_search_providers.SearchResultRow` | 同左 | 否 |
| 首选结果选择 | `web_search_providers._build_search_web_preferred_result` | 同左 | 否 |
| 首选结果摘要 ("首选结果；标题：...") | `web_search_projection._build_search_web_preferred_summary` | 同左 | 否 |
| 下一步动作 (fetch_web_page/refine_query) | `web_search_projection._build_search_web_next_action` | 同左 | 否 |
| 成功 hint ("优先抓取首选结果正文...") | `web_search_projection._build_search_web_hint` | 同左 | 否 |
| 取消 message ("网页搜索工具调用已停止。") | `web_tool_projection_text.WEB_SEARCH_CANCELLED_MESSAGE` | 同左 | 否 |
| 取消 hint ("当前工具调用已停止...") | `web_tool_projection_text.WEB_CANCELLED_HINT` | 同左 | 否 |
| provider unavailable hint | `web_tool_projection_text.WEB_SEARCH_PROVIDER_UNAVAILABLE_HINT` | 同左 | 否 |
| search guidance 常量 | `web_tool_projection_text` | 同左 | 否 |
| display_name ("联网搜索"/"抓取网页") | `web_tools.py` `@tool(...)` 声明处 | 同左 | 否 |
| description | `web_tools.py` `@tool(...)` 声明处 | 同左 | 否 |

### Overcoupling Check

- `web_search_projection.py` → `web_search_providers.py`（import `SearchResultRow`, `SearchWebProviderResult`）：**正确耦合**，projection 依赖 provider 事实类型
- `web_search_projection.py` → `web_tool_projection_text.py`（import 文本常量）：**正确耦合**，projection 依赖共享文案
- `web_tools.py` → 三个模块：**正确耦合**，工具边界是集成点
- 无反向依赖、无循环依赖、无跨层穿透

### Test Coverage Assessment

| 测试 | 覆盖内容 | 评估 |
|---|---|---|
| `test_search_public_web_provider_result_excludes_llm_guidance` | provider 输出不含 guidance 字段 | 精确覆盖 provider 边界 |
| `test_search_web_projects_optional_arguments_and_success` | 有首选结果时的完整投影链路（summary/next_action/next_args/hint） | 覆盖成功投影主路径 |
| `test_web_tool_display_and_description_stay_at_declaration_boundary` | display_name/description 在声明处 | 覆盖声明边界 |
| `test_search_web_cancelled_before_provider_returns_host_cancelled` | 搜索 pre-cancel 路径，验证 message/hint 来自 projection text | 覆盖取消路径 + text owner |
| `test_search_web_deep_cancel_message_is_sanitized` | 深层取消携带治理字段时的 sanitization | 覆盖治理字段泄漏防御 |
| `test_fetch_web_page_cancelled_before_work_returns_safe_host_cancelled` | 抓取 pre-cancel 路径 | 覆盖抓取取消路径 |
| `test_fetch_web_page_deep_runtime_cancel_message_is_sanitized` | 抓取深层取消 sanitization | 覆盖抓取消治理字段泄漏防御 |
| `test_fetch_playwright_cancel_projects_to_host_cancelled` | Playwright fallback 取消投影 | 覆盖 Playwright 取消路径 |
| `test_search_provider_unavailable_projects_to_stable_business_failure` | provider 全部耗尽时的失败投影 | 覆盖 provider unavailable 路径 |
| `test_search_web_cancelled_between_provider_attempts_stops_fallback` | provider attempt 间取消停止 fallback | 覆盖取消竞态 |
| Combined ToolRuntime tests | 真实 discovery + ToolRuntime 集成 | 覆盖集成路径 |

测试薄弱点：
- `build_search_web_output` 无隔离单元测试（当前通过 `_search_web_business` 间接覆盖两个分支）
- `_build_search_web_hint` 有首选结果时的完整 hint 格式仅做了子串断言（`"fetch_web_page" in str(value["hint"])`），未断言精确文案

这两个薄弱点不构成 S1 ship blocker：`build_search_web_output` 是简单的字典构造 + 分支选择，两个分支均已通过集成测试覆盖；hint 文案是 LLM-facing guidance，子串断言已覆盖关键语义（提及 `fetch_web_page` 工具名）。

## Open Questions

无。

## Residual Risk

- 真实外部 provider 网络行为未被 S1 测试覆盖（由 monkeypatch 测试和 process-backed ToolRuntime 测试覆盖；与 S1 变更前一致）
- `web_recovery.py` 中的 fetch failure recovery 文案仍保留在原模块（不在 S1 scope）；其取消相关常量已迁移至 `web_tool_projection_text.py`
- Controller validation 记录的 pytest-cov 工具链限制（pandas/numpy ImportError）导致无法测量新 helper 模块的行覆盖率；测试自身通过且手动走读确认两个 helper 模块的核心路径均被间接覆盖
- `_build_search_web_hint` 的精确文案未被断言（仅子串断言）；若未来有人改动 hint 文案格式，现有测试不会失败
