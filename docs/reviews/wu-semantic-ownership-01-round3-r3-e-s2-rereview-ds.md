# Code Re-Review — AgentDS

## Scope

- **Mode**: current changes (R3-E S2 code-review fix diff only)
- **Branch**: `phaseflow/host-issues-control`
- **Base**: `main`
- **Output file**: `docs/reviews/wu-semantic-ownership-01-round3-r3-e-s2-rereview-ds.md`
- **Artifact timestamp**: 20260713-143411
- **Reviewed fix artifacts**:
  - `docs/reviews/wu-semantic-ownership-01-round3-r3-e-s2-code-review-mimo.md` (MiMo initial review)
  - `docs/reviews/wu-semantic-ownership-01-round3-r3-e-s2-code-review-ds.md` (DS initial review)
  - `docs/reviews/wu-semantic-ownership-01-round3-r3-e-s2-code-review-controller-adjudication.md` (controller adjudication)
  - `docs/reviews/wu-semantic-ownership-01-round3-r3-e-s2-code-review-fix-codex.md` (Codex fix)
  - `docs/reviews/wu-semantic-ownership-01-round3-r3-e-s2-code-review-fix-controller-validation.md` (controller fix validation)
- **Re-review scope**:
  - `R3-E-S2-CR-F01`（identity/no-encoding decoded-cap exact and limit-plus-one owner test）
  - `R3-E-S2-CR-F02`（full-text evaluate exception owner-local debug 可观测性）
  - `R3-E-S2-CR-F03`（browser budget failure reason 单一模块级真源）
  - `R3-E-S2-CR-F04/F05/F06`（rejected/deferred，验证未改未越界）
  - 相关 S2 dirty files: `dayu/tools/web/web_playwright_backend.py`、`tests/tools/web/test_web_tools_provider.py`、`dayu/tools/web/web_fetch_orchestrator.py`、`dayu/tools/web/web_challenge_detection.py`
- **Excluded scope**: S3 diagnostic schema/storage/smoke、S4 Documents bounded source、Host/Engine/Fins、aggregate gates

## Findings

未发现实质性问题。

以下逐项说明复审结论。

---

## F01 — identity/no-encoding decoded-cap exact and limit-plus-one owner test

**最终状态：已修复。**

### 测试本体

`test_identity_body_exact_decoded_limit_and_limit_plus_one`（`tests/tools/web/test_web_tools_provider.py:2904-2944`）：

- 构造不含 `Content-Encoding` header 的 response（`_raw_response` 不带 `headers` 参数，`web_fetch_orchestrator.py` 的 encoding extraction 返回空列表，进入 identity 路径）。
- `wire_body_bytes=1024` 远超 body 长度，确保 wire cap 不先于 decoded cap 触发。
- **Exact limit 用例**：`len(exact_body) == decoded_body_bytes`（均为 13），调用 `_read_limited_response_body` 返回原始 body。断言 `== exact_body`，证明 identity body 在 decoded cap 边界内正确通过。
- **Limit-plus-one 用例**：`overflow_body = exact_body + b"!"`（14 字节），decoded cap 仍为 13。断言 `pytest.raises(_FetchBodyLimitExceeded)`，并验证 `exc_info.value.limit_kind == "decompressed"` 和 `exc_info.value.observed_bytes == 14`。证明 unencoded body 超 decoded cap 时，失败由 decoded cap owner 拥有，而非 wire cap。

### 生产代码未修改

`_read_limited_response_body`、`_decompress_limited_response_body`、`_bounded_identity_layer` 均未变更。`web_fetch_orchestrator.py` 的 unstaged diff 仅包含原始 S2 实现（移除旧常量 `_MEBIBYTE_BYTES` 等，引入 `WebResourceBudget`），不含任何为适配本次测试而做的生产逻辑调整。

### 裁决

测试充分覆盖 identity 路径的 exact 与 limit-plus-one 边界，断言位于 owner contract 层级（`limit_kind` + `observed_bytes`），生产逻辑未被修改。**F01 已修复。**

---

## F02 — full-text evaluate exception owner-local debug 可观测性

**最终状态：已修复。**

### 生产代码

`_materialize_bounded_page_projection`（`dayu/tools/web/web_playwright_backend.py:1286-1297`）：

```python
    try:
        raw_page_text = page.evaluate(_FULL_PAGE_TEXT_SCRIPT)
        page_text = raw_page_text if isinstance(raw_page_text, str) else html
    except Exception:
        Log.debug(
            "Playwright 页面全文本提取失败，回退到 HTML。",
            module=MODULE,
        )
        page_text = html
```

逐项检查：

- **Owner-local debug**：日志由 `_materialize_bounded_page_projection` 自身记录，`module=MODULE`（`ENGINE.WEB_PLAYWRIGHT`），不依赖下游 logger 配置。✅
- **不泄露敏感信息**：日志消息仅包含静态中文描述文本，不含 URL、HTML 片段、response headers、异常原文（`exc` 未被引用）。✅
- **Fallback 行为不变**：`page_text = html` 与原实现完全一致。✅
- **无 S3 schema/payload/storage/smoke 新增**：未引入 diagnostic marker、`internal_diagnostics` dict、public payload field 或持久化状态字段。确认 diff 中 `web_playwright_backend.py` 不包含任何 `diagnostic_`、`internal_`、`smoke` 等 S3 相关字符串（除已在 S2 初始实现的 `WebResourceBudget` 字段传递外）。✅
- **控制流不变**：`raw_page_text` 类型检查（`isinstance(raw_page_text, str)`）保持不变，正常路径返回 `page_text`，异常路径 fallback 到 `html`，后续 `len(page_text) > resource_budget.browser_text_chars` 检查不变。✅

### 测试

`test_playwright_full_text_failure_logs_debug_and_falls_back_to_html`（`tests/tools/web/test_web_tools_provider.py:3146-3190`）：

- 通过 `_BudgetProbePage(page_text_error=RuntimeError(...))` 注入 full-text evaluate 异常。
- 断言 `projection.html == "<p>fallback</p>"`（HTML 原样传递）。
- 断言 `projection.page_text == projection.html`（fallback 到 HTML）。
- 断言 `len(page.evaluate_calls) == 2`（preflight + full-text 两次调用均发生）。
- 断言 caplog 中存在对应 logger name、`DEBUG` 级别和匹配消息文本的 record。
- `_BudgetProbePage` 是纯测试替身，`evaluate()` 方法根据 `arg is not None` 区分 preflight 与 full-text 调用——不修改生产代码。✅

### 裁决

Owner-local debug 可观测性已加入，日志不含敏感信息，fallback 行为完全不变，无 S3 字段新增，测试通过 test double 注入验证了日志记录和 fallback 路径。**F02 已修复。**

---

## F03 — browser budget failure reason 单一模块级真源

**最终状态：已修复。**

### 模块级真源

`dayu/tools/web/web_playwright_backend.py:216-223`：

```python
_BROWSER_DOM_TOO_LARGE_REASON: Final[str] = "browser_dom_too_large"
_BROWSER_TEXT_TOO_LARGE_REASON: Final[str] = "browser_text_too_large"
_BROWSER_RESOURCE_BUDGET_FAILURE_REASONS: Final[frozenset[str]] = frozenset(
    {
        _BROWSER_DOM_TOO_LARGE_REASON,
        _BROWSER_TEXT_TOO_LARGE_REASON,
    }
)
```

### 所有 call sites 复用验证

| 位置 | 行号 | 使用方式 | 真源 |
|---|---|---|---|
| `_BrowserResourceBudgetExceeded.__init__` | 242 | `if reason not in _BROWSER_RESOURCE_BUDGET_FAILURE_REASONS` | frozenset |
| `_materialize_bounded_page_projection` (DOM preflight) | 1276 | `_BrowserResourceBudgetExceeded(_BROWSER_DOM_TOO_LARGE_REASON)` | 成员常量 |
| `_materialize_bounded_page_projection` (text preflight) | 1281 | `_BrowserResourceBudgetExceeded(_BROWSER_TEXT_TOO_LARGE_REASON)` | 成员常量 |
| `_materialize_bounded_page_projection` (DOM 实际长度复核) | 1285 | `_BrowserResourceBudgetExceeded(_BROWSER_DOM_TOO_LARGE_REASON)` | 成员常量 |
| `_materialize_bounded_page_projection` (text 实际长度复核) | 1296 | `_BrowserResourceBudgetExceeded(_BROWSER_TEXT_TOO_LARGE_REASON)` | 成员常量 |
| `_browser_budget_failure` (入参校验) | 1313 | `if reason not in _BROWSER_RESOURCE_BUDGET_FAILURE_REASONS` | frozenset |
| `_playwright_sync_worker` (Markdown 长度 check) | 1494 | `_browser_budget_failure(_BROWSER_TEXT_TOO_LARGE_REASON)` | 成员常量 |

共 7 个 call site，全部复用 `_BROWSER_DOM_TOO_LARGE_REASON`、`_BROWSER_TEXT_TOO_LARGE_REASON` 或 `_BROWSER_RESOURCE_BUDGET_FAILURE_REASONS`。无任何地方使用裸字符串字面量 `"browser_dom_too_large"` 或 `"browser_text_too_large"`。

### 稳定性验证

稳定 reason 值不变：`"browser_dom_too_large"` 与 `"browser_text_too_large"`。`_browser_budget_failure` 返回的 `WebPayload` 结构不变（`{"ok": False, "availability": "unprocessable", "reason": reason}`）。测试 `test_playwright_budget_failure_projects_stable_tool_error`（`tests/tools/web/test_web_tools_provider.py:3193`）对两个 reason 值做参数化断言，确认对外投影稳定。

### 裁决

单一模块级 `Final` 真源，所有 7 个 call site 复用同一组常量，稳定 reason 值不变，无硬编码字符串字面量残留。**F03 已修复。**

---

## F04/F05/F06 — rejected/deferred 越界检查

### F04（challenge infra-only signals → SUSPECTED）

**状态：未改，未越界。**

- `decide_bot_challenge`（`web_challenge_detection.py:164-206`）决策逻辑与初始 S2 实现一致。
- Infra-only signals（如 `server:cloudflare` + 200 OK）流经全部 CONFIRMED 规则无一命中，最终落入 `return BotChallengeDecision.SUSPECTED`（line 206）。
- `_classify_evidence`（line 265）仍将 infra signals 标记为 `INFRASTRUCTURE_HEADER`，此分类不进入 decision 逻辑。
- `challenge_fallback_action`（line 227）对 `SUSPECTED` 和 `NONE` 返回相同 `CONTINUE`，行为一致。
- 测试 `test_challenge_broad_text_and_header_single_signals_are_only_suspected` 仍断言 infra/header 单信号为 `SUSPECTED`。

无修改，无越界。

### F05（probe GET body 未消费）

**状态：未改，未越界。**

- `_probe_content_type` 的 GET fallback 路径仍使用 `stream=True`，只读 headers，`with lease:` 退出时关闭 response。
- docstring 仍说明 "probe 只读 response headers 并立即关闭 lease，因此不消费其 body budget"。

无修改，无越界。

### F06（diagnostic budget fixture owner）

**状态：未改，未越界。**

- `_resource_budget` fixture（`test_web_tools_provider.py:471-472`）仍硬编码 `diagnostic_error_chars=128, diagnostic_events=8`。
- `_resource_budget_json` fixture（line 506-507）相同。
- 无 S3 diagnostic projection 代码新增。

无修改，无越界。

---

## Validation 可信度验证

Controller fix validation 声称的结果独立复现：

| 验证项 | Controller 声称 | 独立复现 |
|---|---|---|
| `pytest -k "identity or playwright or body or decompress or resource_budget"` | 44 passed, 2 skipped | **44 passed, 2 skipped** ✅ |
| `pytest tests/tools/web/test_web_tools_provider.py -q` | 118 passed, 2 skipped | **118 passed, 2 skipped** ✅ |
| `pyright` | 0 errors, 0 warnings, 0 informations | **0 errors, 0 warnings, 0 informations** ✅ |
| `git diff --check` | pass | **pass** ✅ |

所有验证结果可信，可独立复现。

---

## Open Questions

无。

## Residual Risk

1. **Chromium 内部内存峰值不受 budget 控制**：与初始 DS review 一致，TreeWalker preflight 在浏览器进程内消耗 CPU 和内存；二次长度检查只阻止超限完整投影跨进程返回。Owner: Web Playwright backend；destination: 后续 browser sandbox/resource-lane WU。

2. **DuckDuckGo HTML contract 外部性**：严格 fail-closed，provider HTML 改版时短期降级。不做 loose parse 是正确的 owner 选择，需持续监控。

3. **brotli unsupported 且不主动协商**：`Accept-Encoding: gzip, deflate` 不声明 br。若未来依赖提供 bounded streaming API，应由 Web codec owner 新增并重新走 review。

4. **S3 diagnostic 字段已预留但未消费**：`diagnostic_error_chars` 与 `diagnostic_events` 在 budget config 和测试 fixture 中已存在（F06 deferred），消费属于 S3，由对应 slice owner 处理。

以上均为初始 DS review 已记录的 residual risk，本轮修复未引入新风险。

---

## Completion Report

- **Re-review result**: **PASS**
- **F01 最终状态**: 已修复 — identity decoded-cap exact 与 limit-plus-one owner test 充分，生产逻辑未修改。
- **F02 最终状态**: 已修复 — owner-local debug 可观测性已加入，fallback 行为不变，无敏感信息泄露，无 S3 新增。
- **F03 最终状态**: 已修复 — browser budget failure reason 由单一模块级 `Final` 真源拥有，全部 7 个 call site 复用，稳定 reason 值不变。
- **F04/F05/F06**: 均保持未改、未越界。
- **Validation**: 所有 controller 声称验证结果独立复现，可信。
- **新增 material defect**: 无。
- **Artifact path**: `docs/reviews/wu-semantic-ownership-01-round3-r3-e-s2-rereview-ds.md`
