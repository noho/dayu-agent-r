# Code Review — AgentDS

## Scope

- **Mode**: current changes (S2 uncommitted diff only)
- **Branch**: `phaseflow/host-issues-control`
- **Base**: `main` (design docs as truth sources)
- **Output file**: `docs/reviews/wu-semantic-ownership-01-round3-r3-e-s2-code-review-ds.md`
- **Included scope**:
  - `dayu/tools/web/web_resource_budget.py`（新增）
  - `dayu/tools/web/provider.py`
  - `dayu/tools/web/web_fetch_orchestrator.py`
  - `dayu/tools/web/web_playwright_backend.py`
  - `dayu/tools/web/web_challenge_detection.py`
  - `dayu/tools/web/web_search_providers.py`
  - `dayu/tools/web/web_tool_projection_text.py`
  - `dayu/tools/web/web_tools.py`
  - `utils/diagnose_web_access.py`（challenge v1 boolean 从 `BotChallengeDecision.CONFIRMED` 派生的窄幅 propagation only）
  - `dayu/config/README.md`
  - `tests/tools/web/test_web_tools_provider.py`
  - S2 artifacts: implementation-codex, controller-validation, plan
- **Excluded scope**: S3 diagnostic schema/storage/smoke；S4 Documents bounded source；Host/Engine/Fins；tool-security；aggregate gates
- **Parallel review coverage**: 无（单 reviewer 逐文件走读）
- **Design truth sources**: `docs/host/design.md`，`docs/engine/design.md`
- **Control documents**: `docs/host/issues-implementation-control.md`，`docs/phaseflow-umbrella-optimization-control.md`

## Summary

本次 S2 diff 在 Web 工具层建立了七个独立的 semantic owner：
`WebResourceBudget`（资源上限）、provider config parser（JSON 到 typed budget 的边界）、
`web_fetch_orchestrator`（wire/codec/warmup 消费）、`web_playwright_backend`（browser DOM/text cap）、
`web_challenge_detection`（challenge decision/fallback）、`web_search_providers`（固定 search endpoint + DuckDuckGo shape parser）、
`web_tools`（LLM-facing error 投影）。

整体实现质量高。所有 9 项重点审查维度均通过 owner contract 检查，未发现严重或高危缺陷。以下 6 个 finding 按 severity 排序，其中 4 个为低优先级（test gap / maintainability / 语义细微偏差），2 个为中优先级（edge case coverage）。

---

## Findings

### 1-未修复-中-`_bounded_identity_layer` 无独立测试覆盖，uncompressed body 超过 decoded cap 的路径未被断言

- **入口/函数**: `_bounded_identity_layer` (web_fetch_orchestrator.py:638-670) → `_decompress_limited_response_body` (line 673-729) → `_read_limited_response_body` (line 732-781)
- **文件(行号)**: `dayu/tools/web/web_fetch_orchestrator.py:638-670`（定义），`tests/tools/web/test_web_tools_provider.py`（测试）
- **输入场景**: HTTP response 不含 `Content-Encoding` header，wire body 在 `wire_body_bytes` 预算内，但 body 长度超过 `decoded_body_bytes` 预算。
- **实际分支**: `_decompress_limited_response_body` 的 encoding loop 仅命中 `identity`（跳过），然后进入 `_bounded_identity_layer(response, decoded, limit_bytes=resource_budget.decoded_body_bytes)`。若 `len(decoded) > limit_bytes`，应 raise `_FetchBodyLimitExceeded`。
- **预期行为**: `_bounded_identity_layer` 拒绝超过 decoded cap 的未压缩 body，抛出 `_FetchBodyLimitExceeded` 且 `limit_kind="decompressed"`。
- **实际行为**: 现有测试 `test_fetch_body_limit_maps_to_structured_tool_failure` 使用 `wire_body_bytes=4, decoded_body_bytes=4` 与 10 字节 body，wire cap 先于 identity layer 触发。`test_decompress_incremental_codec_exact_limit_and_limit_plus_one` 覆盖了 gzip/deflate/raw-deflate 的有界解码，但均含 Content-Encoding。无测试覆盖"wire 预算内、无编码、decoded 预算不足"的路径。
- **直接证据**: 
  - wire cap 检查在 `_read_limited_response_body:756`（`declared_length > resource_budget.wire_body_bytes`）和 chunk loop `line 769-776`
  - identity layer 仅在 encoding loop 全部 skip 后于 `line 725-729` 调用
  - 测试文件检索 `_bounded_identity_layer` 或 `identity`：无命中
- **影响**: identity layer 的边界行为（exact limit、limit+1、空 body）未被回归保护。未来若有人修改 `_decompress_limited_response_body` 的 encoding loop 结构（如改变 decoded cap 消费顺序），identity 分支可能被遗漏。
- **建议改法和验证点**: 新增参数化测试：构造不含 Content-Encoding 的 response，wire_body_bytes=1024，decoded_body_bytes 分别设为 len(body)、len(body)-1，验证 exact 通过、over 被 `_FetchBodyLimitExceeded` 拒绝且 `limit_kind="decompressed"`。
- **修复风险（低）**: 纯测试补充，不改生产代码。
- **严重程度（中）**: 测试 gap；不影响生产行为正确性，但 owner contract 边界未被完整断言。

---

### 2-未修复-中-`_FULL_PAGE_TEXT_SCRIPT` 的 `page.evaluate` 失败被静默吞掉，text 提取失败不可观测

- **入口/函数**: `_materialize_bounded_page_projection` → `page.evaluate(_FULL_PAGE_TEXT_SCRIPT)` (web_playwright_backend.py:1276-1280)
- **文件(行号)**: `dayu/tools/web/web_playwright_backend.py:1276-1280`
- **输入场景**: Playwright 页面加载成功，DOM preflight 与完整 HTML 投影均通过，但 `page.evaluate("() => document.body ? document.body.innerText : ''")` 因浏览器内部错误（如页面卸载、context 被意外 destroy）抛出异常。
- **实际分支**: `except Exception: page_text = html` — 任何 evaluate 异常都被静默捕获，`page_text` fallback 为完整 HTML。
- **预期行为**: evaluate 失败意味着无法提取页面文本。fallback 到 HTML 是合理的防御策略，但当前实现缺少日志记录，且后续 `len(page_text) > resource_budget.browser_text_chars` 检查使用 HTML 长度与 text budget 比较，若恰好通过（HTML 长度在 text budget 内），下游 `build_text_excerpt(page_text)` 会将 HTML 片段作为"页面文本摘录"写入成功 payload。
- **实际行为**: 
  - 若 `len(html) > browser_text_chars`：正确 reject 为 `browser_text_too_large`，但错误原因与实际情况不符（实际是 evaluate 失败，不是 text truly too large）。
  - 若 `len(html) <= browser_text_chars`：静默成功，`response_excerpt` 包含 HTML 而非页面文本，LLM 可能看到 HTML tag 片段而不是可读的页面内容摘录。
- **直接证据**: `web_playwright_backend.py:1276-1280` 的 bare `except Exception` 不包含任何日志；`_FULL_PAGE_TEXT_SCRIPT` 的定义在 `line 416`；`build_text_excerpt(page_text)` 在 `_playwright_sync_worker:1493` 直接消费 fallback 后的值。
- **影响**: 生产环境难以排查"为什么 fetch_web_page 返回的 excerpt 是 HTML 片段"；若 evaluate 因特定页面模式反复失败，会形成静默降级。
- **建议改法和验证点**: 在 `except Exception` 分支中添加 `Log.debug("Playwright page.evaluate for full text failed, falling back to HTML", module=MODULE)`，并考虑引入内部 diagnostic marker（如 `internal_diagnostics["text_extraction_failed"] = True`）供 S3 diagnostic schema 消费。
- **修复风险（低）**: 仅增加日志和可选 diagnostic marker，不改变控制流。
- **严重程度（中）**: 诊断可观测性 gap；不影响核心 Markdown 输出（Markdown 来自 `convert_html_to_markdown(html)` 而非 `page_text`），但 excerpt 质量静默下降。

---

### 3-未修复-低-`_BrowserResourceBudgetExceeded` 与 `_browser_budget_failure` 重复校验同一个封闭 reason 集合

- **入口/函数**: `_BrowserResourceBudgetExceeded.__init__` (web_playwright_backend.py:219-235) 与 `_browser_budget_failure` (web_playwright_backend.py:1286-1305)
- **文件(行号)**: `dayu/tools/web/web_playwright_backend.py:232` 和 `dayu/tools/web/web_playwright_backend.py:1299`
- **输入场景**: 需要新增第三种 browser budget failure reason（如 `browser_markdown_too_large`）时，两个校验点必须同步更新。
- **实际分支**: 两处均执行 `if reason not in {"browser_dom_too_large", "browser_text_too_large"}: raise ValueError(...)`。
- **预期行为**: reason 集合的 truth source 应只有一处。
- **实际行为**: 集合在两个函数中各自字面量重复。当前已有一处消费点（`_playwright_sync_worker:1479-1480`）在 `_browser_budget_failure` 之外直接用 `resource_budget.browser_text_chars` 比较 markdown 长度并调用 `_browser_budget_failure("browser_text_too_large")`——这个 reason 字符串硬编码在 worker 中，不在任何 shared constant 中。三处（`_BrowserResourceBudgetExceeded`、`_browser_budget_failure`、worker body）共同持有同一组封闭值。
- **直接证据**: 
  - `line 232`: `if reason not in {"browser_dom_too_large", "browser_text_too_large"}`
  - `line 1299`: `if reason not in {"browser_dom_too_large", "browser_text_too_large"}`
  - `line 1479`: `len(pipeline_result.markdown) > resource_budget.browser_text_chars` 然后 `return _browser_budget_failure("browser_text_too_large")`
  - 模块内无 `_BROWSER_BUDGET_FAILURE_REASONS` 常量
- **影响**: 新增 reason 时需改三处，遗漏任一处会导致运行时 ValueError 或语义不一致。当前仅两个 reason 值，实际风险低。
- **建议改法和验证点**: 提取模块级 `frozenset`（如 `_BROWSER_BUDGET_FAILURE_REASONS`），两处校验和 worker body 的字符串字面量均引用该常量或其成员。
- **修复风险（低）**: 纯重构，行为不变。
- **严重程度（低）**: maintainability；当前仅两个值，不构成正确性风险。

---

### 4-未修复-低-`decide_bot_challenge` 中 `_CHALLENGE_INFRA_SIGNALS` 收集但未参与 decision 逻辑

- **入口/函数**: `decide_bot_challenge` (web_challenge_detection.py:164-206)
- **文件(行号)**: `dayu/tools/web/web_challenge_detection.py:164-206`
- **输入场景**: 响应仅包含 infra signal（如 `server:cloudflare` 或 `header:cf-ray`），不含任何 content signal、vendor header 或 cookie signal，状态码为 200。
- **实际分支**: `signal_set` 非空（包含 infra signal），进入 decision 逻辑。无 content_signals（infra signals 不以 `content:` 开头）、无 vendor_gate_headers、无 cookie_signals、`has_error_status=False`。遍历所有 CONFIRMED 规则后无一命中，fall through 到 `return BotChallengeDecision.SUSPECTED` (line 206)。
- **预期行为**: infra signal 单独出现时不应触发 CONFIRMED，当前行为正确返回 SUSPECTED。
- **实际行为**: infra signals 通过 `_collect_bot_challenge_signals` 被收集，通过 `_classify_evidence` 被正确归类为 `INFRASTRUCTURE_HEADER`，但在 `decide_bot_challenge` 中它们只作为 `signal_set` 的非空成员存在，使决策从 `NONE` 变为 `SUSPECTED`——但实际上没有任何 CONFIRMED 规则消费它们。旧的 `should_treat_as_bot_challenge` 逻辑曾显式减去 infra signals 后再做判断（`non_infra_signals = signal_set - _CHALLENGE_INFRA_SIGNALS`），新逻辑不再需要这个减法（因为新规则已通过组合条件隐式排除），但 infra signals 单独出现时从旧逻辑的 `False` 变为新逻辑的 `SUSPECTED`，这是一个行为变化。
- **直接证据**:
  - `_collect_bot_challenge_signals` (line 274-326) 收集 `header:cf-ray`、`server:cloudflare`、`server:akamai`
  - `decide_bot_challenge` (line 164-206) 不显式引用 `_CHALLENGE_INFRA_SIGNALS`
  - 旧逻辑在 `web_challenge_detection.py` 原 `should_treat_as_bot_challenge` 中使用 `non_infra_signals = signal_set - _CHALLENGE_INFRA_SIGNALS`，该减法现已删除
  - 测试 `test_challenge_broad_text_and_header_single_signals_are_only_suspected` 的 infrastructure_header case 使用 `cf-ray` header + 200 状态码，断言 `SUSPECTED`，确认了此行为
- **影响**: 仅 infra signal 的页面（如经过 Cloudflare 但无 challenge 的普通页面）会被标记为 SUSPECTED 而非旧逻辑的 `False`/`NONE`。由于 `challenge_fallback_action` 对 `SUSPECTED` 和 `NONE` 返回相同的 `CONTINUE`，实际 fallback 行为不受影响。但 `BotChallengeDetectionResult.evidence_classes` 中会包含 `INFRASTRUCTURE_HEADER`，这可能影响 S3 diagnostic 中的判定。
- **建议改法和验证点**: 确认 `SUSPECTED` 对 infra-only 信号的语义是预期行为。若预期保持旧行为（infra-only 不改变 decision），可在 `decide_bot_challenge` 开头从 `signal_set` 中排除纯 infra signals 或将 infra-only 场景显式返回 `NONE`。当前测试已接受该行为，若改需同步更新测试。
- **修复风险（低）**: 仅影响 decision 枚举值，不影响 fallback action。
- **严重程度（低）**: `SUSPECTED` 与 `NONE` 在 fallback 行为上等价；仅 evidence 分类与旧行为存在细微语义差异。

---

### 5-未修复-低-`_probe_content_type` 的 HEAD fallback GET 使用 `stream=True` 但不消费 body，response lease 在 `with lease:` 块退出时直接关闭，body 未被耗尽

- **入口/函数**: `_probe_content_type` (web_fetch_orchestrator.py:1355-1447)，GET fallback 路径 (lines 1410-1422)
- **文件(行号)**: `dayu/tools/web/web_fetch_orchestrator.py:1412-1423`
- **输入场景**: HEAD probe 失败（如服务器返回 405 Method Not Allowed），降级到 GET probe。
- **实际分支**: GET 请求使用 `stream=True`（line 1420），在 `with lease:` 块内只读取 response headers（`Content-Type`、`status_code`、`url`），不调用 `_consume_warmup_response_body` 或 `_materialize_response_body`。退出 `with lease:` 时 `lease.close()` 被调用。
- **预期行为**: GET probe 只读 headers 后应立即关闭连接，不消费 body。`lease.close()` 会关闭底层 response，符合预期。
- **实际行为**: `stream=True` 的 response 在 close 时，urllib3 可能尝试读取剩余 body 以归还连接到 connection pool。若 body 较大且未消费，close 可能触发隐式读取。但 `AuthorizedResponseLease.close()` 调用 `response.close()`，这在 requests + urllib3 中会释放连接而不强制消费 body。行为正确。
- **直接证据**: `web_fetch_orchestrator.py:1412-1422` GET 分支；`web_http_session.py` 的 `AuthorizedResponseLease.close()`
- **影响**: 无明显功能影响。body 不被消费即可关闭，符合 probe 只读 headers 的语义。
- **建议改法和验证点**: 无需修改。已在 `_probe_content_type` docstring（line 1372-1373）中明确说明："probe 只读 response headers 并立即关闭 lease，因此不消费其 body budget"。
- **修复风险（不适用）**: 无改动。
- **严重程度（低）**: 文档已说明，行为正确；仅作为 review traversal 记录。

---

### 6-未修复-低-`_resource_budget_json` 测试 fixture 硬编码 `diagnostic_error_chars=128, diagnostic_events=8`，但这两个字段在 `_resource_budget` fixture 中亦硬编码相同值；若 `WebResourceBudget` 默认值变更，fixture 不会自动跟随

- **入口/函数**: `_resource_budget` 与 `_resource_budget_json` 测试辅助函数 (test_web_tools_provider.py:436-503)
- **文件(行号)**: `tests/tools/web/test_web_tools_provider.py:466-467` 和 `tests/tools/web/test_web_tools_provider.py:501-502`
- **输入场景**: 若 `WebResourceBudget` 的默认 `diagnostic_error_chars` 或 `diagnostic_events` 发生变更（如从 1024→2048，80→160），测试 fixture 不会自动反映新默认值。
- **实际分支**: 不适用（测试 fixture 设计问题）。
- **预期行为**: 测试 fixture 应从 `WebResourceBudget()` 默认值派生 S3 字段，或至少显式注释说明这些值的目的。
- **实际行为**: `_resource_budget` 硬编码 `diagnostic_error_chars=128, diagnostic_events=8`；`_resource_budget_json` 硬编码相同值。这两个值小于生产默认值（1024 和 80），且不同于 fixture 其他字段（其他字段接受参数覆盖）。测试中只有 `test_resource_budget_provider_config_complete_object_and_default` 显式断言了 `WebResourceBudget()` 的完整默认值。
- **直接证据**: `test_web_tools_provider.py:466-467`、`501-502`
- **影响**: 若默认值变更，使用 `_resource_budget()` 的测试仍使用旧的硬编码诊断值，但不会引起测试失败（因为测试不直接断言诊断字段的值）。仅当 S3 实现消费这些字段时，fixture 值与生产默认值不一致可能导致测试与生产行为偏差。
- **建议改法和验证点**: 可保留当前 fixture（S3 字段尚未被生产消费），在 S3 实现时为 `_resource_budget` 的 `diagnostic_error_chars` 和 `diagnostic_events` 增加参数覆盖能力（与其他字段对齐），或直接从 `WebResourceBudget()` 派生默认值。
- **修复风险（低）**: fixture 重构，不影响生产行为。
- **严重程度（低）**: 仅在 S3 实现后才可能成为问题；当前无影响。

---

## Review Dimensions — 逐项判定

### 1. WebResourceBudget typed owner

**PASS。** `WebResourceBudget` (`web_resource_budget.py:18-72`) 是完整的 frozen dataclass，`__post_init__` 拒绝 bool、非 int 和非正整数。`web_resource_budget_from_json` (`line 88-139`) 强制七字段完整性、拒绝未知字段，与 `_RESOURCE_BUDGET_FIELDS` 的 frozenset 比较。`provider.py:_resource_budget_default` (`line 117-136`) 在 object 整体缺失时返回完整默认，否则委托 `web_resource_budget_from_json` fail fast。测试覆盖了每个字段缺失 (`test_resource_budget_provider_config_rejects_partial_object`)、bool/零/负数 (`test_resource_budget_constructor_rejects_bool_and_non_positive_integer`)、未知字段 (`test_resource_budget_provider_config_rejects_unknown_and_invalid_values`) 和非 object 类型。

### 2. HTTP fetch/search 无界解压 / wire/decoded/warmup cap 同源 / 异常路径关闭

**PASS。** Wire 读取通过 `_append_limited_body_chunk` (`web_fetch_orchestrator.py:451-490`) 按 chunk 累计计数。Gzip/deflate/raw-deflate 使用 `zlib.decompressobj` 的 `max_length` 参数 (`_decode_zlib_layer:532-585`)，每次调用上限为 `remaining_bytes + 1`。Zstd 使用 `stream_reader.read(size)` (`_decode_zstd_layer:588-635`)。Brotli 因缺少 bounded output API 而显式 unsupported (`_UnsupportedBoundedContentEncoding`)。每层解码后及最终 identity body 均经 `_bounded_identity_layer` (`line 638-670`) 校验 decoded cap。三处 cap（wire/decoded/warmup）均从同一 `WebResourceBudget` 实例派生。异常路径：warmup、probe、main fetch 均使用 `with lease:` 上下文的 `AuthorizedResponseLease`；search 固定 endpoint 使用 `with response:`。`_decode_zstd_layer` 的 `reader.close()` 在 `finally` 块中执行。测试覆盖了 `_FetchBodyLimitExceeded` 对 wire cap、decoded cap、多层编码、压缩炸弹、以及 brotli unsupported 的拒绝，以及 warmup/lease/response 的 close counting。

### 3. Tavily/Serper/DuckDuckGo 固定 endpoint stream/redirect/body owner

**PASS。** 三个 provider 均使用 `stream=True`、`allow_redirects=False`、共享 `_materialize_bounded_search_response` → `_materialize_response_body` （同一 wire/codec owner）。`_raise_for_search_provider_status` (`web_search_providers.py:875-896`) 显式拒绝 3xx redirect 并调用 `raise_for_status()`。无第二套 redirect/egress 语义。测试 `test_tavily_provider_builds_typed_rows` 和 `test_serper_provider_builds_typed_rows` 断言 `stream=True`、`allow_redirects=False`、`Accept-Encoding: gzip, deflate` 及 response close。

### 4. Playwright bounded TreeWalker preflight / 完整投影二次复核

**PASS。** Preflight script `_BUDGETED_DOM_METRICS_SCRIPT` (`web_playwright_backend.py:373-415`) 仅使用 `document.createTreeWalker`、手动计数器和无 `break` 提前退出，不包含 `page.content()`、`outerHTML`、`innerHTML`、`textContent`、`innerText`。`_materialize_bounded_page_projection` (`line 1239-1283`) 先 preflight → 检查超限 → `page.content()` → 二次长度复核 → `page.evaluate(_FULL_PAGE_TEXT_SCRIPT)` → 二次 text 长度复核。`_FULL_PAGE_TEXT_SCRIPT` 使用 `document.body.innerText`，但仅在 preflight 通过后执行（符合要求：preflight 不使用，完整投影可以使用）。测试 `test_playwright_budget_preflight_uses_only_tree_walker_before_projection` 验证 preflight 在 content() 之前失败时不调用 content()，且 preflight script 不含 forbidden tokens。`test_playwright_budget_rechecks_dynamic_full_projection_lengths` 验证 preflight 通过但实际投影超限时被二次检查拒绝。

### 5. Challenge 判定由 BotChallengeDecision/challenge_fallback_action 唯一拥有

**PASS。** `BotChallengeDecision` 枚举（NONE/SUSPECTED/CONFIRMED）和 `challenge_fallback_action` (`web_challenge_detection.py:209-231`) 是 challenge decision 与 fallback 的唯一 owner。旧 `challenge_detected: bool` 字段已删除；旧 caller 中 `challenge_detected and http_status in {401, 403, 429, 503}` 的双真源已替换为统一的 `challenge.decision is BotChallengeDecision.CONFIRMED` 加上 `challenge_fallback_action(decision=..., browser_available=...)` 的三态判定。`ChallengeFallbackAction` 枚举（CONTINUE/TRY_BROWSER/FAIL_BLOCKED）由 `challenge_fallback_action` 独占产生，caller 不再自行组合 decision 与 http_status。测试 `test_challenge_strong_vendor_signal_is_confirmed_for_all_statuses` 参数化覆盖 200/401/403/429/500/503，验证强 vendor signal 在所有状态码下均为 CONFIRMED。`test_challenge_confirmed_http_500_invokes_fallback_once` 验证 CONFIRMED + HTTP 500 只调用一次 browser fallback。

### 6. DuckDuckGo parser fail closed

**PASS。** `_parse_duckduckgo_html` (`web_search_providers.py:899-987`) 先通过共享 challenge detector 检查 → `_duckduckgo_has_login_or_anomaly_shape` 检查 → 检查 `div.result` container。无 container 时检查唯一 `.no-results` 元素且文本在 `_DUCKDUCKGO_NO_RESULTS_TEXT` frozenset 中才返回空列表。解析每条结果时累积 `malformed_count`，最后检查 `not results or malformed_count * 2 > container_count` 时 fail closed。Challenge/login shape 优先于 result/no-results。测试覆盖：已知 shape + 50% malformed (`test_duckduckgo_known_shape_and_exact_half_malformed_are_valid`)、精确 no-results 文本 (`test_duckduckgo_explicit_no_results_allowlist`)、未知 HTML/未知 empty marker/>50%/100% malformed (`test_duckduckgo_shape_drift_and_malformed_threshold_fail_closed`)、challenge/login shape 覆盖 result/no-results (`test_duckduckgo_challenge_or_login_shape_overrides_results_and_empty`)、shape drift 投影到稳定工具失败 (`test_duckduckgo_shape_drift_projects_typed_search_failure`)。

### 7. LLM-facing/tool error 投影稳定且业务可读

**PASS。** `web_tool_projection_text.py` 定义了三个新的 LLM-facing 常量：`WEB_SEARCH_PROVIDER_RESPONSE_INVALID_HINT`、`WEB_SEARCH_RESPONSE_BODY_TOO_LARGE_HINT`，均以 `[change_source]` action tag 开头并提供业务可读的换源指示。`web_tools.py` 对应的 error code 为 `search_provider_response_invalid` 和 `response_body_too_large`（复用已有常量 `_RESPONSE_BODY_TOO_LARGE_ERROR`）。两个新异常类型（`WebSearchProviderResponseError`、`WebSearchProviderResourceError`）的 `message` 字段为中性诊断说明，不暴露内部治理信息。异常到 outcome 的投影在 `_call_search_web`（line 1461-1478）和 `_WebProcessTarget.__call__`（line 503-513）中一致。

### 8. 测试断言 owner contract，不复制生产派生逻辑

**PASS。** 测试断言 owner 级行为而非实现细节：
- Resource budget tests 断言 constructor 和 parser 的 ValueError（不以内部字段顺序或错误消息精确文本为 contract）
- Challenge tests 使用 `is` identity check 断言 decision enum 成员，不复制 `decide_bot_challenge` 的条件组合
- DuckDuckGo tests 对每种 shape 使用独立 HTML fixture，不断言内部 parser 的中间状态
- Browser preflight tests 通过 `_BudgetProbePage` 测试替身验证调用顺序和脚本内容，不复制 TreeWalker 逻辑
- Codec tests 验证 `observed_bytes` 值（owner contract：limit+1 时 fail），不验证内部 chunk 拼接方式
- 测试 fixture（`_resource_budget`、`_resource_budget_json`）显式构造完整预算，不依赖 `WebResourceBudget()` 默认值（除 S3 字段外）

Docstrings 满足 AGENTS 要求：所有新增/修改的公开函数均有完整中文 docstring，包含 Args/Returns/Raises。

### 9. 无工具安全实现或 S3/S4 越界

**PASS。** 无新增安全工具。`diagnostic_error_chars` 与 `diagnostic_events` 存在于 typed budget config 中但消费属于 S3，当前未越界实施。`utils/diagnose_web_access.py` 的修改严格限定在 challenge v1 boolean 从 `BotChallengeDecision.CONFIRMED` 派生的窄幅 propagation（两行，见 controller validation 澄清）。无 Host/Engine/Fins 文件修改。

---

## Open Questions

1. `decide_bot_challenge` 对 infra-only signals（如 `server:cloudflare` + 200 OK）返回 `SUSPECTED`，旧逻辑返回 `False`/`NONE`。测试 `test_challenge_broad_text_and_header_single_signals_are_only_suspected` 已接受此行为。请 controller 确认这是否为预期语义变更（详见 Finding 4）。

---

## Residual Risk

1. **Chromium 内部内存峰值不受 budget 控制**：TreeWalker preflight 在浏览器进程内消耗 CPU 和内存；即使 preflight 提前退出，浏览器可能已经为渲染分配了大量内部数据结构。二次长度检查只阻止超限值跨进程投影。Owner: Web Playwright backend；destination: 后续 browser sandbox/resource-lane WU。

2. **DuckDuckGo HTML contract 外部性**：parser 严格 fail closed，provider HTML 改版时会短期降级到下一个 provider（通常仍成功）。不做 loose parse 是正确的 owner 选择，但需持续监控。

3. **brotli 不支持且不主动协商**：`Accept-Encoding: gzip, deflate` 不声明 br。若未来依赖提供 bounded streaming API，应由 Web codec owner 新增并重新走 review。

4. **S3 diagnostic 字段已预留但未消费**：`diagnostic_error_chars` 与 `diagnostic_events` 在 budget config 和测试 fixture 中已存在，但生产消费路径属于 S3，当前不会生效。S3 实现时必须沿用同一 `WebResourceBudget` 实例，不得创建第二套上限来源。

---

## Completion Report

- **Review result**: **PASS with findings**（6 个 finding，0 个严重/高危，2 个中优先级，4 个低优先级）
- **Reviewed files**: 11（9 生产 + 1 测试 + 1 README）
- **Lines reviewed**: ~4,300（diff 总行数）
- **Tests verified**: 116 passed, 2 skipped（完整 `test_web_tools_provider.py`）
- **pyright**: 0 errors, 0 warnings, 0 informations（by implementation-codex report）
- **Artifact path**: `docs/reviews/wu-semantic-ownership-01-round3-r3-e-s2-code-review-ds.md`
- **Artifact timestamp**: 20260713-141626
