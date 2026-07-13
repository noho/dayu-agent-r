# R3-E S2 Code Review — AgentMiMo

## Scope

- Mode: current changes
- Branch: `phaseflow/host-issues-control`
- Base: `main`
- Output file: `docs/reviews/wu-semantic-ownership-01-round3-r3-e-s2-code-review-mimo.md`
- Included scope:
  - `dayu/tools/web/web_resource_budget.py`（新增）
  - `dayu/tools/web/provider.py`
  - `dayu/tools/web/web_fetch_orchestrator.py`
  - `dayu/tools/web/web_playwright_backend.py`
  - `dayu/tools/web/web_challenge_detection.py`
  - `dayu/tools/web/web_search_providers.py`
  - `dayu/tools/web/web_tool_projection_text.py`
  - `dayu/tools/web/web_tools.py`
  - `utils/diagnose_web_access.py`（仅 challenge v1 boolean 从 `BotChallengeDecision.CONFIRMED` 派生的窄幅 propagation）
  - `dayu/config/README.md`
  - `tests/tools/web/test_web_tools_provider.py`
  - S2 artifacts：`docs/reviews/wu-semantic-ownership-01-round3-r3-e-s2-implementation-codex.md`、`docs/reviews/wu-semantic-ownership-01-round3-r3-e-s2-controller-validation.md`
- Excluded scope: S3 diagnostic schema/storage/smoke、S4 Documents bounded source、Host/Engine/Fins/tool-security
- Parallel review coverage: 7 个 subagent 分别覆盖 WebResourceBudget ownership、HTTP response bounds、fixed endpoints/redirect、Playwright preflight、challenge detection ownership、DuckDuckGo parser fail-closed、LLM-facing projection/tests。主 reviewer 对全部 findings 做了交叉验证与去重。

## Findings

未发现实质性问题。

以下逐项说明审查结论：

### 1. WebResourceBudget typed owner

- `web_resource_budget.py:18-72`：frozen dataclass，`__post_init__` 校验全部 7 字段为非 bool 正整数。
- `web_resource_budget.py:88-139`：`web_resource_budget_from_json` 校验完整字段集，缺字段/未知字段/bool/非正整数均 fail fast。
- `provider.py:117-136`：`_resource_budget_default` 仅在整个 `resource_budget` 缺失时返回完整默认；object 存在时委托 `web_resource_budget_from_json`。
- 消费路径（`web_fetch_orchestrator.py`、`web_search_providers.py`、`web_playwright_backend.py`）均从同一 `WebResourceBudget` 实例读取上限，无第二套常量。

### 2. HTTP fetch/search response bounds

- `web_fetch_orchestrator.py:493-506`：wire body 通过 `response.raw.stream(64*1024, decode_content=False)` 逐 chunk 读取。
- `web_fetch_orchestrator.py:451-490`：`_append_limited_body_chunk` 在 append 前检查 `next_size > limit_bytes`。
- `web_fetch_orchestrator.py:532-585`：`_decode_zlib_layer` 使用 `decompressobj.decompress(pending, remaining_bytes + 1)` 增量解码，超限在物化前可判定。
- `web_fetch_orchestrator.py:588-635`：`_decode_zstd_layer` 使用 `stream_reader.read(min(CHUNK, remaining_bytes + 1))` 有界读取。
- `web_fetch_orchestrator.py:732-781`：`_read_limited_response_body` 同时执行 wire 和 decoded cap。
- 异常路径：所有 response 均在 `with lease:` 或 `with response:` context manager 内消费，正常/异常/取消路径均关闭。

### 3. Fixed endpoints stream/redirect/egress

- `web_search_providers.py:654-665`（Tavily）、`:739-754`（Serper）、`:816-830`（DuckDuckGo）：均 `stream=True`、`allow_redirects=False`。
- 三个 provider 均在 `with response:` 内调用 `_materialize_bounded_search_response`（`:845-872`），复用同一 wire/decoded materialization owner。
- `web_search_providers.py:875-896`：`_raise_for_search_provider_status` 拒绝 3xx redirect 并对 error status 使用 `response.raise_for_status()`。
- 无第二套 redirect/egress 语义。

### 4. Playwright bounded TreeWalker preflight

- `web_playwright_backend.py:373-415`：`_BUDGETED_DOM_METRICS_SCRIPT` 仅使用 `document.createTreeWalker()` 和有界 counters，不包含 `page.content()`、`outerHTML`、`innerHTML`、`textContent`、`innerText`。
- `web_playwright_backend.py:1189-1236`：`_read_budgeted_dom_metrics` 调用 `page.evaluate(_BUDGETED_DOM_METRICS_SCRIPT, limits)` 并校验返回 shape。
- `web_playwright_backend.py:1239-1283`：`_materialize_bounded_page_projection` 先 preflight，超限立即拒绝；通过后才调用 `page.content()` 和 `_FULL_PAGE_TEXT_SCRIPT`（`:416`），并二次复核实际长度。
- 测试 `test_playwright_budget_preflight_uses_only_tree_walker_before_projection`（`:3012-3048`）断言：`page.content_calls == 0`、script 含 `document.createTreeWalker`、不含 forbidden tokens。
- 测试 `test_playwright_budget_rechecks_dynamic_full_projection_lengths`（`:3051-3091`）断言：预检通过但动态变大时二次拒绝。

### 5. Challenge detection ownership

- `web_challenge_detection.py:84-89`：`BotChallengeDecision` 封闭枚举（`none`/`suspected`/`confirmed`）。
- `web_challenge_detection.py:209-231`：`challenge_fallback_action` 是唯一 fallback 决策源。
- `web_tools.py:2100-2134`、`:2231-2245`、`:2314-2348`：所有 challenge 处理均通过 `challenge_fallback_action(decision=challenge.decision, browser_available=...)`。
- `_BOT_CHALLENGE_HTTP_STATUS`（`web_challenge_detection.py:64`）仅在 detector 内部用于信号分类（`:197`、`:269`、`:321-324`），未导出给 caller 做独立 status gating。
- `web_tools.py:2135-2142` 的 `_should_escalate_http_status_to_browser` 和 `http_status == 403` 检查是 HTTP error 独立 fallback，不是 challenge decision 的第二真源。Challenge 已在 `:2100-2134` 处理完毕，该路径仅在 challenge 非 confirmed 时执行。
- `utils/diagnose_web_access.py:1380-1381`、`:2099-2100`：v1 `challenge_detected` 布尔从 `challenge.decision is BotChallengeDecision.CONFIRMED` 派生，无兼容 property 或 `getattr` fallback。

### 6. DuckDuckGo parser fail-closed

- `web_search_providers.py:938-950`：已知 result shape（`div.result` + `a.result__a` + 有效 href）正常解析。
- `web_search_providers.py:939-950`：explicit no-results 仅在唯一 `.no-results` 元素且文本精确命中 `_DUCKDUCKGO_NO_RESULTS_TEXT` 时返回空。
- `web_search_providers.py:923-936`：challenge/login shape（通过 `_duckduckgo_has_login_or_anomaly_shape`）覆盖 result/no-results。
- `web_search_providers.py:952-987`：全部 container 检查后，有效项为 0 或 `malformed_count * 2 > container_count` 时抛 `WebSearchProviderResponseError(reason="response_shape_changed")`。
- 无 loose parse 或 try/except 吞异常掩盖 shape drift。

### 7. LLM-facing/tool error projection

- `web_tool_projection_text.py`：稳定 `Final[str]` 常量，业务可读，不含内部实现术语。
- `web_tools.py:162-164`：稳定 error codes（`search_provider_unavailable`、`search_provider_response_invalid`、`response_body_too_large`）。
- `web_search_providers.py:140-200`：`WebSearchProviderResponseError` 和 `WebSearchProviderResourceError` 分别投影为 `search_provider_response_invalid` 和 `response_body_too_large`。

### 8. Tests owner contract coverage

- `test_resource_budget_constructor_rejects_bool_and_non_positive_integer`（`:2787`）：断言 owner 拒绝非法值。
- `test_resource_budget_provider_config_rejects_partial_object`（`:2823`）：断言缺任一字段 fail fast。
- `test_resource_budget_provider_config_rejects_unknown_and_invalid_values`（`:2836`）：断言未知字段/bool/非正整数 fail fast。
- `test_decompress_incremental_codec_exact_limit_and_limit_plus_one`（`:2860`）：断言 limit+1 在物化前失败。
- `test_challenge_confirmed_http_500_invokes_fallback_once`（`:3251`）：断言 confirmed + HTTP 500 只调用一次 fallback。
- `test_duckduckgo_shape_drift_projects_typed_search_failure`（`:3473`）：断言 shape drift 投影 `search_provider_response_invalid`。
- 测试不复制生产派生逻辑，断言 owner contract 行为。
- docstrings 完整中文，type hints 无 `Any`、无 `object`、无无类型参数。

### 9. S3/S4 边界

- 未修改 diagnostic schema、storage-state lifecycle、smoke oracle 或 Documents bounded source。
- `utils/diagnose_web_access.py` 的修改仅限 challenge v1 boolean 从 `BotChallengeDecision.CONFIRMED` 派生的窄幅 propagation，controller 已明确授权。

## Open Questions

无。

## Residual Risk

1. Chromium 在 preflight 前已构造内部 DOM；TreeWalker 消耗 CPU，动态页面可在 preflight 后变大。二次长度检查只阻止超限值跨进程投影，不能消除浏览器内部峰值。Owner: Web Playwright backend；destination: 后续 browser sandbox/resource-lane WU。
2. DuckDuckGo 是外部 HTML contract；严格 fail closed 会在 provider 改版时短期降级。Owner: Web search provider；destination: 后续 provider selector/shape 更新，不允许 loose parse。
3. brotli 当前明确 unsupported 且不主动协商；如果未来依赖提供可限制单次输出的 streaming API，应由 Web codec owner 新增并重新走 review，不得恢复整包解压。
4. `diagnostic_error_chars` / `diagnostic_events` 已进入完整 typed config，但实际 diagnostic projection 消费属于 S3，当前未越界实施。
