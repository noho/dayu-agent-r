# WU-SEMANTIC-OWNERSHIP-01 P3-H S1 implementation

## Scope

- Slice: `S1 - Web search provider facts and Web tool projection text`
- Agent: `AgentCodex`
- Accepted plan commit: `ba607309`
- Plan: `docs/host/wu-semantic-ownership-01-p3-h-llm-ui-copy-boundary-plan.md`
- Controller adjudication: `docs/reviews/wu-semantic-ownership-01-p3-h-plan-rereview-controller-adjudication.md`

## First-principles judgment

S1 的动机成立。直接证据是 `dayu/tools/web/web_search_providers.py` 原先在 provider 返回结构中生成
`preferred_result_summary`、`next_action`、`next_action_args` 和 `hint`，并从取消文案模块读取
`WEB_CANCELLED_HINT`。这些字段是给 LLM 使用的工具投影语义，不是搜索 provider 首次产生的检索事实。

本 slice 的 owner boundary：

- `web_search_providers.py`：产生并校验 provider 检索事实，包括 query、domains、total、preferred_result、results。
- `web_search_projection.py`：把 provider facts 投影为 `search_web` public success JSON 中的 LLM-facing guidance。
- `web_tool_projection_text.py`：拥有 Web 工具取消、搜索恢复和 provider unavailable 的 LLM-facing 文案。
- `web_tools.py`：工具声明和工具 outcome 边界，负责调用 provider、投影 success JSON、投影取消/失败 outcome。

## Changed files

- `dayu/tools/web/web_search_providers.py`
  - 将 provider-owned `SearchWebOutput` 替换为 `SearchWebProviderResult`。
  - `search_public_web(...)` 只返回 `query`、`domains`、`total`、`preferred_result`、`results`。
  - 删除 provider 内的 search guidance builder：preferred summary、next action、next args、hint。
  - `WebSearchCancelledError` 改为只携带中性取消说明，不携带恢复 hint。

- `dayu/tools/web/web_search_projection.py`
  - 新增 public `SearchWebOutput`。
  - 新增 `build_search_web_output(provider_result: SearchWebProviderResult) -> SearchWebOutput`。
  - 负责生成 `preferred_result_summary`、`next_action`、`next_action_args`、`hint`，保持 public success JSON shape 不变。

- `dayu/tools/web/web_tool_projection_text.py`
  - 新增 Web 工具投影文案真源。
  - 移入 `WEB_CANCELLED_HINT`、`WEB_SEARCH_CANCELLED_MESSAGE`、`WEB_FETCH_CANCELLED_MESSAGE`。
  - 移入 `WEB_SEARCH_PROVIDER_UNAVAILABLE_HINT` 和 search guidance 常量。

- `dayu/tools/web/web_tools.py`
  - 从 provider 导入 `SearchWebProviderResult`，从 projection 导入 `SearchWebOutput` / `build_search_web_output`。
  - `_search_web_business(...)` 先取得 provider facts，再投影为 public `SearchWebOutput`。
  - 取消和 provider unavailable recovery 文案改为从 `web_tool_projection_text.py` 获取。
  - `@tool(...)` declaration 中的 `display_name` 与 `description` 保持原地不变。

- `dayu/tools/web/web_cancellation_text.py`
  - 删除，无 compatibility re-export。

- `tests/tools/web/test_web_tools_provider.py`
  - provider fixture 改为返回 provider facts。
  - 新增 provider boundary 测试，断言 provider result 无 `hint` / `next_action` / `next_action_args` / `preferred_result_summary`。
  - 增强 completed tool outcome 断言，确认 public success JSON 仍包含 guidance 字段。
  - 增强取消 outcome 断言，确认 message/hint 来自 `web_tool_projection_text.py`。
  - 新增 display/description declaration boundary 断言。

- `tests/tools/test_combined_tools_acceptance.py`
  - combined Web provider fixture 改为返回 provider facts，继续通过真实工具边界投影 success JSON。

## Validation

- `source .venv/bin/activate && pytest tests/tools/web/test_web_tools_provider.py tests/tools/test_combined_tools_acceptance.py -q`
  - Result: `44 passed, 1 skipped, 3 warnings`

- `source .venv/bin/activate && python -m pyright dayu/ tests/ utils/`
  - Result: `0 errors, 0 warnings, 0 informations`

- `git diff --check`
  - Result: passed

## Source scans

- `rg -n "web_cancellation_text" dayu tests utils`
  - Result: no matches

- `rg -n "class SearchWebOutput|preferred_result_summary|next_action|next_action_args|hint|_build_search_web_(preferred_summary|next_action|next_action_args|hint)" dayu/tools/web/web_search_providers.py dayu/tools/web/web_search_projection.py`
  - Result: matches only in `dayu/tools/web/web_search_projection.py`

- `rg -n "WEB_CANCELLED_HINT|WEB_SEARCH_CANCELLED_MESSAGE|WEB_FETCH_CANCELLED_MESSAGE|WEB_SEARCH_PROVIDER_UNAVAILABLE_HINT" dayu/tools/web tests/tools/web/test_web_tools_provider.py`
  - Result: constants defined in `web_tool_projection_text.py`; production consumers import/use from `web_tools.py`; tests assert helper-sourced text.

- `rg -n "display_name=|description=" dayu/tools/web/web_tools.py dayu/tools/web/web_search_providers.py dayu/tools/web/web_search_projection.py dayu/tools/web/web_tool_projection_text.py`
  - Result: Web tool `description` / `display_name` remain in `dayu/tools/web/web_tools.py` declaration sites.

## README decision

- `dayu/tools/web/` has no README trigger in the project rule.
- `tests/` changed, so `tests/README.md` was checked. Its update boundary requires syncing when a new test layer is added. This slice only updated existing Web/combined tool tests and added assertions within the same layer, so no README update was made.

## Propagation audit

1. Fact production:
   - `search_public_web(...)` normalizes query/domains, runs the selected provider, filters visible URLs, selects `preferred_result`, and returns `SearchWebProviderResult`.
   - Provider output contains no LLM-facing `hint`, `next_action`, `next_action_args`, or `preferred_result_summary`.

2. Tool projection:
   - `web_tools._search_web_business(...)` receives `SearchWebProviderResult` and immediately calls `build_search_web_output(...)`.
   - `web_search_projection.py` is the single source for search success guidance fields in the public tool value.

3. Cancellation and recovery projection:
   - Provider cancellation raises `WebSearchCancelledError` with neutral message only.
   - `web_tools.py` converts search/fetch cancellation to Host cancelled outcomes using `WEB_SEARCH_CANCELLED_MESSAGE`, `WEB_FETCH_CANCELLED_MESSAGE`, and `WEB_CANCELLED_HINT` from `web_tool_projection_text.py`.
   - Provider unavailable recovery hint also comes from `web_tool_projection_text.py`.

4. LLM-visible output:
   - Completed `search_web` tool value still exposes the same public JSON fields as before.
   - Tool declaration `display_name` and `description` remain at the `@tool(...)` boundary.
   - No durable schema, Host EventLog, memory, trace, Engine, Fins, SEC, CLI, or README path changed in S1.

## Residual risks

- Real external provider network behavior was not exercised; coverage is by focused monkeypatch tests and existing process-backed/tool-runtime tests.
- Existing fetch failure recovery copy in `web_recovery.py` and fetch business error construction remains outside S1 except for shared cancellation text.
- Pre-existing dirty/untracked docs outside S1 were not touched, including `docs/host/issues-implementation-control.md`.
