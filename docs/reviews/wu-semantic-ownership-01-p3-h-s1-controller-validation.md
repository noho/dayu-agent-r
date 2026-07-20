# WU-SEMANTIC-OWNERSHIP-01 P3-H S1 controller validation

## Scope

- Work unit: `WU-SEMANTIC-OWNERSHIP-01 P3-H - LLM-facing and UI-copy boundary cleanup`
- Slice: `S1 - Web search provider facts and Web tool projection text`
- Implementation artifact: `docs/reviews/wu-semantic-ownership-01-p3-h-s1-implementation-codex.md`
- Accepted plan commit: `ba607309`

## Controller Result

Controller validation passes for S1 pending independent code review.

## Changed Boundary

- `dayu/tools/web/web_search_providers.py` now owns provider facts through `SearchWebProviderResult`.
- `dayu/tools/web/web_search_projection.py` owns public `SearchWebOutput` and LLM-facing search guidance fields.
- `dayu/tools/web/web_tool_projection_text.py` owns Web cancellation/recovery text.
- `dayu/tools/web/web_tools.py` remains the tool declaration/outcome boundary and keeps `display_name` / `description` in `@tool(...)`.
- `dayu/tools/web/web_cancellation_text.py` is deleted with no compatibility re-export.

## Validation Commands

- `source .venv/bin/activate && pytest tests/tools/web/test_web_tools_provider.py tests/tools/test_combined_tools_acceptance.py -q`
  - Result: `44 passed, 1 skipped, 3 warnings`

- `source .venv/bin/activate && python -m pyright dayu/ tests/ utils/`
  - Result: `0 errors, 0 warnings, 0 informations`

- `git diff --check`
  - Result: passed

## Source Scans

- `rg -n "web_cancellation_text|from \\.web_cancellation_text|import .*web_cancellation_text" dayu tests utils`
  - Result: no matches.

- `rg -n "_build_search_web_preferred_summary|_build_search_web_hint|_build_search_web_next_action|_build_search_web_next_action_args|当前没有可直接抓取|优先抓取首选结果正文|未找到可直接抓取正文|首选结果|标题：|日期：|摘要：|preferred_result_summary|next_action|next_action_args|\\\"hint\\\"" dayu/tools/web/web_search_providers.py`
  - Result: no matches after controller changed a neutral provider docstring from "首选结果" to "首个可见结果" to avoid scan noise.

- `rg -n "SearchWebOutput|SearchWebProviderResult|build_search_web_output" dayu/tools/web tests/tools`
  - Result: `SearchWebProviderResult` remains in provider/tests; `SearchWebOutput` and `build_search_web_output(...)` are in projection/tool boundary.

- `rg -n "display_name=|description=" dayu/tools/web/web_tools.py dayu/tools/web/web_search_providers.py dayu/tools/web/web_search_projection.py dayu/tools/web/web_tool_projection_text.py`
  - Result: display and description hits remain only in `web_tools.py` declaration sites.

## Coverage Note

Attempted helper coverage with:

`source .venv/bin/activate && pytest tests/tools/web/test_web_tools_provider.py tests/tools/test_combined_tools_acceptance.py --cov=dayu.tools.web.web_search_projection --cov=dayu.tools.web.web_tool_projection_text --cov-fail-under=80 -q`

and a smaller three-test subset. Both failed during pytest collection before project tests ran because importing `pandas` / `numpy` raised `ImportError: cannot load module more than once per process`. The same tests pass without pytest-cov, and pyright passes. This is recorded as a local coverage tooling limitation for S1, not a code-path failure.

## README Decision

- No `dayu/tools/web/` README trigger exists.
- `tests/README.md` was checked by AgentCodex. S1 updates existing Web/combined tool tests and does not add a new testing layer or stable testing category; no README update is required.

## Propagation Audit

- Fact production: `search_public_web(...)` returns query/domain/result facts only.
- Projection owner: `web_search_projection.py` builds `preferred_result_summary`, `next_action`, `next_action_args`, and `hint`.
- Tool outcome: `web_tools._search_web_business(...)` projects provider facts before returning the completed tool value.
- Cancellation/recovery text: `web_tool_projection_text.py` owns shared Web cancellation and provider-unavailable guidance.
- Tool declaration: `display_name` and `description` remain in `@tool(...)` declaration sites.
- LLM-visible output: public `search_web` JSON shape remains stable; provider internals no longer own search guidance prose.

## Residual Risk

- Real external provider network behavior was not exercised in controller validation.
- Fetch failure recovery copy in `web_recovery.py` remains outside S1 except shared cancellation text.
