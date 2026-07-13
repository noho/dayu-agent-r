# WU-SEMANTIC-OWNERSHIP-01 Round3 R3-E S2 code re-review — AgentMiMo

## Scope

- Gate: R3-E Slice S2 code-review fix re-review.
- Review artifacts:
  - Initial MiMo review: `docs/reviews/wu-semantic-ownership-01-round3-r3-e-s2-code-review-mimo.md`
  - Initial DS review: `docs/reviews/wu-semantic-ownership-01-round3-r3-e-s2-code-review-ds.md`
  - Controller adjudication: `docs/reviews/wu-semantic-ownership-01-round3-r3-e-s2-code-review-controller-adjudication.md`
  - Fix artifact: `docs/reviews/wu-semantic-ownership-01-round3-r3-e-s2-code-review-fix-codex.md`
  - Fix controller validation: `docs/reviews/wu-semantic-ownership-01-round3-r3-e-s2-code-review-fix-controller-validation.md`
- Fix scope: `R3-E-S2-CR-F01`、`R3-E-S2-CR-F02`、`R3-E-S2-CR-F03`。
- Re-review 范围：仅审 fix diff 与相关 S2 dirty files；不扩大到 S3/S4。

## Re-review 方法

1. 读取 controller adjudication 确认 accepted findings 的 required action。
2. 读取 fix artifact 确认修复声明与 changed files。
3. 读取 fix controller validation 确认 controller 已验证通过。
4. 读取实际 workspace diff（`git diff`），逐项验证 F01/F02/F03 修复实现。
5. 运行 required validation 验证测试与类型检查通过。
6. 检查 rejected/deferred findings（F04/F05/F06）是否保持未改。

## Finding 裁决

### R3-E-S2-CR-F01：identity/no-encoding decoded-cap exact and limit-plus-one owner test

**裁决：已修复，充分。**

直接证据：

- `tests/tools/web/test_web_tools_provider.py::test_identity_body_exact_decoded_limit_and_limit_plus_one`：
  - Response 不含 `Content-Encoding` header。
  - `wire_body_bytes=1024`（足够高，确保 wire cap 不会先于 decoded cap 触发）。
  - `decoded_body_bytes=len(exact_body)` 用于 exact limit 测试。
  - Exact limit 测试：`_read_limited_response_body` 返回原 body。
  - Limit-plus-one 测试：`_read_limited_response_body` 抛 `_FetchBodyLimitExceeded`。
  - 断言 `limit_kind == "decompressed"` 和 `observed_bytes == len(exact_body) + 1`。
- 生产代码 `_bounded_identity_layer`、`_decompress_limited_response_body`、`_read_limited_response_body` 未被修改。
- 测试通过 `_raw_response` 构造 response，使用 `urllib3.HTTPResponse` 作为 `response.raw`，不依赖外部服务。

未为测试改写生产逻辑：测试仅验证 owner contract 行为（exact 通过、over 被拒绝且 `limit_kind`/`observed_bytes` 正确），不复制内部实现。

### R3-E-S2-CR-F02：full-text evaluate exception 有 owner-local debug 可观测性

**裁决：已修复，充分。**

直接证据：

- `dayu/tools/web/web_playwright_backend.py::_materialize_bounded_page_projection`：
  - `page.evaluate(_FULL_PAGE_TEXT_SCRIPT)` 异常分支现在记录 `Log.debug("Playwright 页面全文本提取失败，回退到 HTML。", module=MODULE)`。
  - 日志不包含 URL、HTML、headers、异常正文或其它敏感信息。
  - Fallback 行为不变：`page_text = html`。
- `tests/tools/web/test_web_tools_provider.py::test_playwright_full_text_failure_logs_debug_and_falls_back_to_html`：
  - 注入 `page_text_error=RuntimeError("synthetic full text extraction failure")`。
  - 断言 `projection.html == "<p>fallback</p>"` 和 `projection.page_text == projection.html`。
  - 断言 `len(page.evaluate_calls) == 2`（preflight + full-text evaluate）。
  - 断言 debug log record 包含预期消息。
- 未新增 S3 schema、durable payload marker、storage-state 或 smoke oracle 字段。

可观测性已补齐：owner-local debug 日志在 fallback 分支记录，不含敏感信息，fallback 行为不变。

### R3-E-S2-CR-F03：browser budget failure reason 由单一模块级真源拥有

**裁决：已修复，充分。**

直接证据：

- `dayu/tools/web/web_playwright_backend.py`：
  - 定义 `_BROWSER_DOM_TOO_LARGE_REASON: Final[str] = "browser_dom_too_large"`。
  - 定义 `_BROWSER_TEXT_TOO_LARGE_REASON: Final[str] = "browser_text_too_large"`。
  - 定义 `_BROWSER_RESOURCE_BUDGET_FAILURE_REASONS: Final[frozenset[str]] = frozenset({_BROWSER_DOM_TOO_LARGE_REASON, _BROWSER_TEXT_TOO_LARGE_REASON})`。
- `_BrowserResourceBudgetExceeded.__init__`：`if reason not in _BROWSER_RESOURCE_BUDGET_FAILURE_REASONS: raise ValueError(...)`。
- `_browser_budget_failure`：`if reason not in _BROWSER_RESOURCE_BUDGET_FAILURE_REASONS: raise ValueError(...)`。
- `_materialize_bounded_page_projection`：所有 `_BrowserResourceBudgetExceeded` 调用使用 `_BROWSER_DOM_TOO_LARGE_REASON` 或 `_BROWSER_TEXT_TOO_LARGE_REASON`。
- `_playwright_sync_worker`：markdown 长度检查使用 `_browser_budget_failure(_BROWSER_TEXT_TOO_LARGE_REASON)`。
- 稳定 reason 值不变：`browser_dom_too_large` 和 `browser_text_too_large`。

所有当前 call sites 复用同一模块级真源，无重复字符串字面量。

### Rejected/deferred findings 保持状态

- `R3-E-S2-CR-F04`（rejected-with-reason）：challenge lattice 未修改。`web_challenge_detection.py` 的变更是 S2 实现（`BotChallengeDecision` 枚举、`challenge_fallback_action`），不是 fix 变更。infra-only signals 继续返回 `SUSPECTED`。
- `R3-E-S2-CR-F05`（rejected-with-reason）：probe GET 继续只读 headers 后关闭 lease，不消费 body。
- `R3-E-S2-CR-F06`（deferred-with-owner）：diagnostic fixture 硬编码值（`diagnostic_error_chars=128, diagnostic_events=8`）未修改，仍由 S3 处理。

### Required validation 结果

- `source .venv/bin/activate && pytest tests/tools/web/test_web_tools_provider.py -q`：`118 passed, 2 skipped`。
- `source .venv/bin/activate && pyright`：`0 errors, 0 warnings, 0 informations`。
- `source .venv/bin/activate && git diff --check`：通过，无 whitespace error。

## Open Questions

无。

## Residual Risk

无新增 residual risk。Fix 仅补齐 owner-level tests、owner-local debug 日志和模块级常量提取，不引入新行为或新依赖。

## Completion Report

**PASS — R3-E S2 code-review fix re-review。**

- `R3-E-S2-CR-F01`：已修复。identity decoded-cap exact/limit-plus-one owner test 充分，未为测试改写生产逻辑。
- `R3-E-S2-CR-F02`：已修复。owner-local debug 可观测性已补齐，fallback 行为不变，未泄露敏感信息，未新增 S3 schema/payload/storage/smoke。
- `R3-E-S2-CR-F03`：已修复。browser budget failure reason 已由单一模块级真源拥有，所有 call sites 复用，稳定 reason 值不变。
- `R3-E-S2-CR-F04`：保持 rejected，未改。
- `R3-E-S2-CR-F05`：保持 rejected，未改。
- `R3-E-S2-CR-F06`：保持 deferred，未改。
- 未新增 material finding。
- Artifact path：`docs/reviews/wu-semantic-ownership-01-round3-r3-e-s2-rereview-mimo.md`。
