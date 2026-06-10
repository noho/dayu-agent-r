# WU-TOOLS-01-F03 Plan Review — AgentMiMo

## Reviewed Target

- 文件：`docs/host/wu-tools-01-f03-web-ci-smoke-plan.md`
- 依据：`docs/host/design.md`、`docs/engine/design.md`、`docs/host/issues-implementation-control.md`、`docs/reviews/wu-tools-01-f02-final-closeout-controller.md`、`utils/diagnose_web_access.py` 当前代码、`dayu/tools/web/web_fetch_orchestrator.py` 当前代码、`dayu/tools/web/web_tools.py` 当前代码、`tests/README.md`

## Overall Assessment

Plan 整体结构清晰，5 个 slice 的 objective / allowed files / exact changes / data flow / error handling / invariants / tests / stop condition 齐全，implementation agent 可以直接执行。diagnostics 真源强化方案合理，smoke 外壳正确消费 diagnostics 输出而非复制逻辑。但存在一个 critical finding：PDF Docling route evidence 的实现路径存在证据缺口，直接阻塞用户硬要求。

## Findings

### F-1 [Critical] PDF Docling route evidence 缺口：diagnostics payload 无法证明 Docling 被调用

**位置**：Plan "First-principles Judgment and Direct Code Evidence" 第 4 点、"Implementation Decisions" 第 4 点、Slice 1 "Exact changes" 最后一项、Slice 3 "PDF case pass 条件"

**问题**：Plan 正确识别了用户硬要求——"需要本地 web server 提供很小 PDF，验证 fetch_web_page 走 Docling convert 路径"。Plan 提出在 Slice 1 增加 `fetch_non_html_route_evidence` 字段，基于"raw response content-type / URL suffix + current fetch success + current code route"推导。

但直接代码证据显示，当前 diagnostics payload 缺少证明 Docling route 所需的关键数据：

1. `web_tools.py:1559-1564`：`fetch_web_page` 成功时返回给调用方的 payload 只含 `url/final_url/title/content/fetch_backend`，不含 `extraction_source`、`renderer_source`。
2. `web_tools.py:1566-1588`：`extraction_source` 和 `renderer_source` 只通过 `_log_fetch_diagnostics` 写入日志，不进入 `ToolCompletedOutcome.result.value`。
3. `diagnose_web_access.py:1283-1296`：`_build_tool_fetch_profile` 从 `ToolCompletedOutcome.result.value` 提取字段，只拿到 `title/final_url/fetch_backend/content_prefix/content_length`，同样没有 `extraction_source`。
4. `web_fetch_orchestrator.py:816`：`content_type` 从 probe 或 response headers 获取，但 orchestrator 返回的 result dict（`web_fetch_orchestrator.py:887-901`）不含 `content_type` 字段。

因此 Slice 1 的 `fetch_non_html_route_evidence` 字段没有数据源。smoke 只能知道 `fetch_backend="requests"` + fetch 成功，但无法区分 PDF response 走了 HTML pipeline 还是 Docling convert path。

Plan 自身在 Risks / Open Questions 中承认了这个问题（"当前 `fetch_web_page` success payload 不暴露 `extraction_source` / `renderer_source`"），并在 Slice 3 的 Stop condition 中设置了停止点。但这不应是"停止并裁决"的开放问题——它是 F03 核心目标的直接阻塞项，必须在 plan 中给出明确解决方案。

**证据**：
- `dayu/tools/web/web_tools.py:1559-1564` — success payload 定义
- `dayu/tools/web/web_tools.py:1566-1588` — diagnostics 只写日志
- `utils/diagnose_web_access.py:1283-1296` — fetch profile 字段
- `dayu/tools/web/web_fetch_orchestrator.py:816` — content_type 不在返回值中

**建议裁决**：accepted — Plan 必须在 Slice 1 中明确解决数据源问题，不能只留 Stop condition。可选方案：

- 方案 A（最小侵入）：在 `_build_tool_fetch_profile` 中增加对 `extraction_source` 的提取（从 `_log_fetch_diagnostics` 的日志路径无法拿到，需要从 tool success payload 中获取）。这要求 `web_tools.py` 的 success payload 增加 `extraction_source` 字段。Plan 声明不修改 production tool schema，但 `extraction_source` 是诊断字段，不属于 LLM-facing 公共语义，添加它不违反 F03 non-goal。
- 方案 B（纯 diagnostics 侧）：让 `_build_tool_fetch_profile` 通过 raw requests profile 的 response headers 提取 content-type，结合 `_infer_docling_stream_name` 的同源逻辑推导 Docling route。但这需要 smoke 或 diagnostics 重复 orchestrator 的路由逻辑，违反 plan 的"smoke 外壳不得复制诊断逻辑"原则。
- 方案 C（降级）：PDF smoke pass 条件降级为"fetch 成功 + content-type 是 PDF"，不验证 Docling 被实际调用。但这违反用户硬要求"验证 fetch_web_page 走 Docling convert 路径"。

### F-2 [High] skip-playwright + requests&fetch 成功的 bucket 缺失导致 HTML smoke 判定不可行

**位置**：Plan "Implementation Decisions" 第 3 点 "pass" 条件、`utils/diagnose_web_access.py:1811-1870`

**问题**：Plan 规定 HTML case pass 条件是 "`comparison_bucket` 是 `all_success` 或在 Playwright skipped 时等价的 requests + fetch success bucket"。但 `_classify_diagnostic_bucket` 没有处理"Playwright skipped + requests ok + fetch ok"的组合。

当前 bucket 分类逻辑（`diagnose_web_access.py:1842-1870`）：
- `all_success` 要求三个路径都 sampled 且 ok（`playwright_sampled and requests_sampled and fetch_sampled and ...`）
- 当 Playwright 被 skip 时，`playwright_sampled=False`，不会命中 `all_success`
- 其他 bucket 都不匹配"skip-playwright + requests ok + fetch ok"
- 最终落入 `partial_sample`（line 1868-1869）

Plan 说"或在 Playwright skipped 时等价的 requests + fetch success bucket"，但这个 bucket 在当前代码中不存在。Implementation agent 会面临：是修改 `_classify_diagnostic_bucket` 新增 bucket，还是在 smoke 中用非 bucket 字段判定？Plan 没有明确。

**证据**：
- `utils/diagnose_web_access.py:1844` — `all_success` 要求三路径都 sampled
- `utils/diagnose_web_access.py:1868-1869` — fallback 为 `partial_sample`
- Plan "Implementation Decisions" 第 3 点 — pass 条件引用了不存在的 bucket

**建议裁决**：accepted — Plan 应明确：(a) 在 `_classify_diagnostic_bucket` 中新增 `requests_and_fetch_success_playwright_skipped` bucket，或 (b) HTML case pass 条件改为直接检查 `requests_ok=True and fetch_ok=True` 而非依赖 bucket 名。选项 (b) 更简单，但需要在 Slice 2/3 的判定逻辑中明确。

### F-3 [Medium] Minimal PDF fixture 可能触发 empty_content 或 Docling 无法提取文本

**位置**：Plan "Risks / Open Questions" 第 1 点、Slice 3 "Exact changes"

**问题**：Plan 引用 `tests/fins/test_docling_upload_service_integration.py` 中的 `_MINIMAL_PDF`（`%PDF-1.4` 含一个空白 200x200 页面，无文本内容）。Plan 识别了"可能被判为无有效文本"的风险，但应对方案不完整：

1. `_MINIMAL_PDF` 不含任何文本流，Docling 可能返回空 markdown。
2. `web_fetch_orchestrator.py:886-886` 返回的 `content_stats` 会显示 `text_length=0`、`markdown_length=0`。
3. 如果 `fetch_web_page` 内部有 `empty_content` 检测，可能抛出 `ToolBusinessError`，导致 fetch profile 显示 `ok=False`。
4. Plan 说"需要调整 fixture PDF 为仍很小但含稳定文本的 PDF"，但没有明确谁来提供这个 fixture、在哪里定义、文本内容是什么。

**证据**：
- `tests/fins/test_docling_upload_service_integration.py:16-22` — `_MINIMAL_PDF` 定义
- Plan "Risks / Open Questions" 第 1 点 — 承认风险但未给出具体 fixture 定义

**建议裁决**：accepted — Plan 应在 Slice 3 中明确：(a) 不复用 `_MINIMAL_PDF`，而是新增一个含稳定短文本（如 "Hello PDF" 或 "Test Document"）的 `_SMOKE_PDF_FIXTURE` 常量；或 (b) 明确验证 `empty_content` 不是 `fetch_web_page` 的 error path，并在 smoke pass 条件中接受空内容但成功返回的 PDF。

### F-4 [Medium] `_build_batch_summary` 新增字段对已有 diagnostics 输出的向后兼容

**位置**：Plan "Implementation Decisions" 第 4 点、Slice 1 "Exact changes"

**问题**：Plan 在 `_build_batch_summary()` 追加 `failure_items`、`diagnostic_only_items`、`skip_items`、`suggested_next_steps` 等新字段。同时在 `_build_batch_result_row()` 追加 `primary_failure_bucket`、`evidence_path`、`failure_url` 等字段。

这些是 additive 字段，不删除 F02 已有字段。但 smoke 如果依赖这些新字段存在来判定（Plan 说"缺少新增字段时，smoke 应把它分类为 `diagnostic_schema_gap` failure"），则使用旧版 diagnostics 输出运行 smoke 会直接 fail。

这不是 bug，但是一个可维护性风险：如果 smoke 和 diagnostics 的版本不匹配，smoke 会误报。Plan 应明确 smoke 的 diagnostics schema version 检查逻辑。

**证据**：
- Plan Slice 1 "Error handling" — "缺少新增字段时，smoke 应把它分类为 `diagnostic_schema_gap` failure"
- Plan Slice 1 "Invariants" — "不删除 F02 已有字段"

**建议裁决**：accepted — Plan 应在 Slice 2 中增加 smoke 对 diagnostics schema version 的检查，并在 summary 中明确报告 version mismatch 而非静默 fail。

### F-5 [Low] Plan 行号引用范围偏大但代码证据有效

**位置**：Plan "Direct code evidence" 第 6 点

**问题**：Plan 引用 `web_fetch_orchestrator.py:818-879` 作为"非 HTML response 分支调用 `convert_non_html`"的证据。实际非 HTML 分支在 line 871-879（`else` 子句），line 818 是 `_should_route_response_to_html_pipeline` 的路由判断。引用范围偏大但代码证据确实存在。

**证据**：`dayu/tools/web/web_fetch_orchestrator.py:818`（路由判断）和 `871-879`（非 HTML 分支）

**建议裁决**：accepted — 修正为 `web_fetch_orchestrator.py:871-879`，或改为 `818-879` 并说明包含路由判断和非 HTML 分支。

### F-6 [Low] Smoke summary `status` 枚举值 `diagnostic_only` 与字段名冲突

**位置**：Plan "Implementation Decisions" 第 3 点、Slice 2 "Exact changes"

**问题**：Smoke summary 的 `status` 字段允许 `diagnostic_only`，但 summary 中同时有 `diagnostic_only` 列表字段。当 `status="diagnostic_only"` 时，语义是"只有 diagnostic-only 结果，无 local gate pass/fail"，但与同名列表字段容易混淆。

**建议裁决**：deferred-with-owner / implementation agent — 不阻塞，但建议将 status 值改为 `diagnostic_only_only` 或 `passed_with_diagnostic_gaps`，或在 plan 中明确两者的关系。

## Open Questions

1. **Q-1**：用户是否允许在 `fetch_web_page` success payload 中增加 `extraction_source` 字段？该字段已在 `_log_fetch_diagnostics` 中记录，属于诊断信息而非 LLM 推理依据，添加它不违反 Agent 语义约束。如果允许，F-1 的方案 A 是最干净的解决路径。如果不允许，Plan 需要采用方案 B（diagnostics 侧重复路由推导）并接受其维护风险。

2. **Q-2**：PDF smoke 的 pass 条件是否要求 Docling 被实际调用，还是只要求"PDF fetch 成功 + content-type 正确 + 代码路径可推导"？用户硬要求说"验证 fetch_web_page 走 Docling convert 路径"，但 Plan 的 Stop condition 暗示可以降级。

## Residual Risks

| 风险 | 严重性 | 说明 |
|---|---|---|
| Docling 版本 / 平台兼容性 | Medium | `_MINIMAL_PDF` 可能在某些 Docling 版本上无法解析。Plan 允许 skip，但需要明确 skip 判定逻辑（是 catch `DoclingRuntimeInitializationError` 还是 catch 所有 `RuntimeError`）。 |
| 外部 diagnostics 耗时 | Low | `--external-limit` 只限制 URL 数量，不限制单 URL 超时。如果个别站点 timeout 很长，外部 diagnostics 可能耗时远超预期。Plan 应明确 `--request-timeout` 对外部 URL 的适用性。 |
| Local HTTP server 端口冲突 | Very Low | Plan 使用随机可用端口，冲突概率极低。但 `finally` 关闭 server 的逻辑需要确保异常时也能清理。 |
| Smoke 与 diagnostics 版本不匹配 | Low | 新增字段后，旧版 diagnostics 输出 + 新版 smoke 会触发 `diagnostic_schema_gap` fail。Plan 应明确 version check。 |

## Final Recommendation

**pass-with-fixes**

Plan 整体设计合理，diagnostics 真源强化方向正确，5 个 slice 结构清晰可执行。但 F-1（PDF Docling route evidence 数据源缺口）是 critical finding，直接阻塞用户硬要求。Plan 必须在进入 implementation 前解决 F-1 的数据源问题，否则 Slice 3 会在 Stop condition 处卡住。

F-2（bucket 缺失）是 high finding，会导致 HTML smoke 判定不可行，需要在 plan 中明确解决路径。

F-3-F-6 为 medium/low，implementation agent 可以在执行过程中处理，不阻塞 plan approval。

建议用户对 F-1 做出裁决后，更新 plan 的 Slice 1 和 Slice 3，再进入 implementation。
