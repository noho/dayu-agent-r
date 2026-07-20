# WU-SEMANTIC-OWNERSHIP-01 Round 2 Batch A Code Review - AgentMiMo

## Scope

- Mode: current changes
- Branch: `phaseflow/host-issues-control`
- Base: `HEAD` (commit `42140fa7`)
- Output file: `docs/reviews/wu-semantic-ownership-01-round2-batch-a-code-review-mimo.md`
- Included scope: Batch A accepted findings implementation diff
- Excluded scope: Batch B/C/D/E, unrelated docs/cli_ci changes
- Parallel review coverage: 无

## Reviewed Artifacts

- `docs/reviews/wu-semantic-ownership-01-fullrepo-round2-controller-adjudication.md`
- `docs/reviews/wu-semantic-ownership-01-round2-batch-a-implementation-codex.md`
- `docs/reviews/wu-semantic-ownership-01-round2-batch-a-controller-validation.md`
- `AGENTS.md`, `docs/engine/design.md`, `docs/phaseflow-umbrella-optimization-control.md`

## Changed Files

| 文件 | 变更类型 |
|---|---|
| `dayu/tools/web/web_fetch_orchestrator.py` | 重定向逐跳安全校验、body 有界读取、meta refresh 校验 |
| `dayu/tools/web/web_playwright_backend.py` | Playwright route/navigation/request URL 安全校验 |
| `dayu/tools/web/web_tools.py` | 构造 `is_url_allowed` 谓词、传递到全链路 |
| `dayu/tools/doc_tools.py` | `search_files` symlink 解析后 containment 校验 |
| `dayu/fins/resolver/fmp_company_info.py` | 删除模糊 first-result fallback |
| `dayu/engine/runners/openai/retry_policy.py` | `max_retries` 语义对齐为重试次数 |
| `tests/tools/web/test_web_tools_provider.py` | redirect/meta/body/route 测试 |
| `tests/tools/test_doc_tools_provider.py` | symlink escape 测试 |
| `tests/fins/test_fmp_company_info_resolver.py` | exact ticker 要求测试 |
| `tests/engine/runners/openai/test_retry_backoff.py` | max_retries=0 测试 |

## Findings

未发现实质性问题。

以下是对五个 accepted findings 修复的逐项 correctness/security/semantic-ownership 验证：

### 1. Web redirect/meta refresh/Playwright navigation 私网绕过

**验证结果：通过。**

实现沿真实代码路径走读：

1. **HTTP redirect 逐跳校验** (`_request_with_safe_redirects`, `web_fetch_orchestrator.py:648-712`)：`allow_redirects=False` 禁止 requests 自动跟随，改为手动循环。每跳执行 `_raise_if_url_blocked` 三次：请求前校验 `current_url`、响应后校验 `response_url`、下一跳前校验 `next_url`（从 `Location` 头解析）。redirect 上限 `_MAX_HTTP_REDIRECT_HOPS=30` 防无限循环。每一跳关闭前一响应防止资源泄漏。

2. **meta refresh 校验** (`_resolve_meta_refresh_follow_target`, `web_fetch_orchestrator.py:830-900`)：解析 HTML `<meta http-equiv="refresh">` 的 `target_url` 后，在进入下一 fetch 循环前调用 `_raise_if_url_blocked`。被拒绝时抛出 `_FetchContentConversionError(failure_reason="blocked_by_safety_policy")`，与 `web_tools.py` 的 `_FetchUrlSafetyError` 处理分支对齐。

3. **Playwright 三层校验** (`web_playwright_backend.py`):
   - `page.route("**/*", partial(_route_handler_abort_resources, is_url_allowed=...))` 拦截所有浏览器网络请求（含 XHR/fetch/image/font/media），对不安全 URL 执行 `route.abort()` (L912-914)。
   - `page.goto()` 前 `_raise_if_playwright_url_blocked(url=url, ...)` 校验初始 URL (L1167-1171)。
   - `page.goto()` 后 `_raise_if_playwright_url_blocked(url=page.url, ...)` 校验最终落地 URL (L1195-1199)。
   - settle 后再次校验 `page.url` (L1218-1222)。
   - warmup 导航前后各校验一次 (L1005-1011, L1023-1027)。

4. **谓词构造一致性** (`_build_fetch_url_safety_predicate`, `web_tools.py:732-750`)：基于 `partial(_is_safe_public_url, allow_private_network_url=...)` 构造，所有网络阶段（warmup/probe/fetch/playwright）共享同一谓词实例。

5. **`_is_safe_public_url` 本身** (`web_tools.py:2903-2945`)：scheme 白名单、hostname 空值、私网 IP 模式、`ipaddress.ip_address` 属性检查、DNS 解析后 IP 验证、fake-ip 兼容——逐层 fail-closed。

**语义 ownership**：Web URL safety 由 `web_tools._is_safe_public_url` 作为唯一谓词真源，`web_fetch_orchestrator` 和 `web_playwright_backend` 在各自网络边界消费同一谓词。无 fallback、无重复实现、无下游补偿。

### 2. `search_files` symlink containment 绕过

**验证结果：通过。**

`doc_tools.py:1527-1559` 新增 `_resolve_search_files_candidate`：
- `file_path.resolve(strict=True)` 解析 symlink 到真实路径（`strict=True` 要求目标存在）。
- `_is_relative_to(resolved_file, root)` 校验真实路径是否在 `allowed_roots` 内。
- `resolved_file.is_file()` 确认是文件而非目录。
- 三项任一失败返回 `None`，调用方 `continue` 跳过。

`_search_files_business` (L1486-1492) 在 `rglob` 得到候选路径后、processor/line-scan 读取前调用 `_resolve_search_files_candidate`。`allowed_roots` 由 `_route_doc_business` 从 `_execute_doc_business_value` 传入，沿业务 owner 边界向下传递。

**测试覆盖** (`test_search_files_does_not_read_symlink_escape`)：allowed root 内 symlink → outside root 的 secret.txt，搜索 query 命中 secret.txt 内容，断言 `matches == []`。

**语义 ownership**：doc 文件访问安全由 `doc_tools` 模块在 `search_files` 业务入口处负责。`allowed_roots` 从 Host 注入的配置真源派生，不在工具内部重新计算。

### 3. FMP fuzzy first-result identity injection

**验证结果：通过。**

`fmp_company_info.py:276-299` `_select_symbol_result`：
- 遍历 `search-symbol` 结果，规范化后精确匹配 `canonical_ticker`。
- 无精确匹配时 `raise FmpCompanyInfoResolutionError`，不再 `return results[0]`。
- 空结果仍抛出同一异常类型（L289-292）。

controller adjudication 确认 Service 层已有 `FmpCompanyInfoResolutionError` 的 ticker-only fallback，因此 resolver 侧删除 first-result 不会破坏 Service 语义。

**测试覆盖** (`test_resolve_company_info_requires_exact_symbol_match`)：
- `V` ticker 搜索返回 `V.BA`（无精确匹配），断言 `pytest.raises(FmpCompanyInfoResolutionError, match="精确 ticker")`。
- 断言只发起 1 次请求（`search-symbol`），不发起 `search-name`。

**语义 ownership**：公司身份精确匹配由 `FmpCompanyInfoResolver._select_symbol_result` 负责。Service 层的 ticker-only fallback 是 Service 的降级策略，不在 resolver 内实现。

### 4. Web fetch pre-conversion body limits

**验证结果：通过。**

实现链路：

1. `_request_with_safe_redirects(..., stream=True)` 确保 requests 不预读 body。
2. `_materialize_response_body(response)` (L629-645) 调用 `_read_limited_response_body`。
3. `_read_limited_response_body` (L585-626)：
   - Content-Length 声明超限提前失败 (L599-613)。
   - `_iter_raw_response_chunks` 按 64KiB chunk 读取 wire bytes，`_append_limited_body_chunk` 逐 chunk 累计并校验 `_FETCH_MAX_WIRE_BODY_BYTES` (25 MiB)。
4. `_decompress_limited_response_body` (L535-582)：按 `Content-Encoding` 逆序逐层解压（gzip/deflate/br/zstd），每层解压后校验 `_FETCH_MAX_DECOMPRESSED_BODY_BYTES` (50 MiB)。
5. 解码后字节通过 `setattr(response, "_content", decoded_body)` 写回 response，后续 `_extract_html_response_text` / `_decode_response_text` 读取 `response.content` 获取已解码字节。
6. 超限异常 `_FetchBodyLimitExceeded` 由 `_fetch_web_page_business` 捕获并投影为结构化 `ToolBusinessError(error_code="response_body_too_large")` (web_tools.py L2077-2113)。

**测试覆盖** (`test_fetch_body_limit_maps_to_structured_tool_failure`)：monkeypatch 缩小限制至 4 字节，断言 `ToolFailedOutcome(error="response_body_too_large")`。

**语义 ownership**：body 大小限制由 `web_fetch_orchestrator` 的 `_read_limited_response_body` / `_decompress_limited_response_body` 在转换前强制执行。限制值为模块级常量，不在 tool schema 或调用参数中暴露（schema 例外允许字面量字符串，此处常量更合适）。

### 5. OpenAI retry off-by-one

**验证结果：通过。**

`retry_policy.py:115`：`if attempt >= max_retries + 1` 替换旧 `if attempt > max_retries`。

语义验证：
- `max_retries=0, attempt=1`：`1 >= 1` → 不重试。正确。
- `max_retries=1, attempt=1`：`1 >= 2` → 重试。正确（首败后允许 1 次重试）。
- `max_retries=1, attempt=2`：`2 >= 2` → 不重试。正确（重试次数已耗尽）。

新旧代码对 `attempt > max_retries` 与 `attempt >= max_retries + 1` 数学等价，变更本质是 docstring 语义对齐（`max_retries` 明确为"首败后重试次数"）和可读性改进。

**测试覆盖**：
- `test_compute_retry_decision_exhausted_after_retry_count_used`：`max_retries=1, attempt=2` → 不重试。
- `test_compute_retry_decision_zero_max_retries_disables_retry`：`max_retries=0, attempt=1` → 不重试。

**语义 ownership**：重试语义由 `retry_policy.compute_retry_decision` 负责。`RunnerSpec.max_retries` 是配置输入，`compute_retry_decision` 是决策真源。

### AGENTS.md 约束合规检查

| 约束 | 结果 |
|---|---|
| 函数完整中文 docstring（Args/Returns/Raises） | 通过：所有新增函数/类均有完整 docstring |
| 禁止 `object`/`Any`/无类型参数 | 通过：新增 Protocol 类型 `_BytesDecompressorModule` / `_ZstandardDecompressor` / `_ZstandardModule` 替代 Any |
| 禁止魔法数字/字符串 | 通过：`_MEBIBYTE_BYTES`, `_FETCH_BODY_CHUNK_BYTES`, `_FETCH_MAX_WIRE_BODY_BYTES` 等均为命名常量 |
| 禁止兼容性代码 | 通过：无兼容性 re-export / wrapper |
| 测试 owner-level 覆盖 | 通过：测试断言安全谓词拒绝行为、异常类型、错误码，不依赖实现细节 |

## Open Questions

无。

## Residual Risk

1. **DNS rebinding TOCTOU**（pre-existing，非本次引入）：`_is_safe_public_url` 在请求前解析 DNS 验证 IP，实际 HTTP 请求可能使用不同 DNS 结果。当前窗口极小（校验与请求紧密相邻），但理论上可被高精度竞态利用。若需彻底消除，需在 TCP 建连后验证 peer IP（例如 `urllib3` 的 `source_address` hook 或自定义 connector）。

2. **Playwright HTTP 层 redirect 与 route handler 的交互**：Playwright route handler 在 CDP 级别拦截网络请求，对 HTTP redirect 的每一跳目标均执行 `request.url` 校验。但若浏览器对 redirect 有内部优化路径（如 service worker redirect），可能绕过 route handler。当前测试使用 deterministic route-level mock，未覆盖 live browser 行为。controller validation 已记录此 residual。

3. **多层编码解压内存峰值**：`_decompress_limited_response_body` 逐层解压，每层独立受 50 MiB 限制。极端场景（3 层编码 × 50 MiB/层 + 25 MiB wire）理论峰值 ~175 MiB。当前 HTTP 实践中多层编码罕见，且每层有独立上限，风险可控。

4. **Batch B/C/D/E 未开始**：当前只完成了 Batch A。Host wait/dispatch/cancellation、Engine/Host public contract、Fins storage/data-loss、Fins typing 等高风险修复尚待后续 batch。

## Conclusion

**pass**。Batch A 五个 accepted findings 的实现均通过 correctness / security / semantic ownership 验证。Web URL safety 谓词在网络每一跳边界一致应用；body limits 在转换前强制执行；doc search 对每个派生文件做 resolved containment；FMP resolver 删除模糊 first-result fallback；retry 语义对齐为重试次数。tests 以 owner-level contract 行为断言，不依赖实现细节。未发现实质性问题。
