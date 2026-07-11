# Code Review — WU-SEMANTIC-OWNERSHIP-01 Round 2 Batch A

## Scope

- Mode: current changes (workspace diff against HEAD)
- Branch: `phaseflow/host-issues-control`
- Base: `HEAD`
- Output file: `docs/reviews/wu-semantic-ownership-01-round2-batch-a-code-review-ds.md`
- Included scope: Batch A only — Web/Doc/FMP/Retry per controller adjudication
- Excluded scope: Batches B/C/D/E, pre-existing code outside diff
- Parallel review coverage: 无（本 review 为主 reviewer 单人走读）
- Reviewed artifacts:
  - `AGENTS.md`
  - `docs/engine/design.md`
  - `docs/phaseflow-umbrella-optimization-control.md`
  - `docs/reviews/wu-semantic-ownership-01-fullrepo-round2-controller-adjudication.md`
  - `docs/reviews/wu-semantic-ownership-01-round2-batch-a-implementation-codex.md`
  - `docs/reviews/wu-semantic-ownership-01-round2-batch-a-controller-validation.md`

## Findings

### F-01-未修复-高-Playwright URL safety 抛出错误异常类型导致 permission_denied 投影缺失

- **入口/函数**: `_raise_if_playwright_url_blocked` (web_playwright_backend.py:999) → `_playwright_sync_worker` → `_try_playwright_fallback` → `_fetch_web_page_business`
- **文件(行号)**:
  - `dayu/tools/web/web_playwright_backend.py:1012-1018`（抛出 `RuntimeError`）
  - `dayu/tools/web/web_fetch_orchestrator.py:432-438`（抛出 `_FetchUrlSafetyError`）
  - `dayu/tools/web/web_tools.py:2080-2093`（只 catch `_FetchUrlSafetyError`）
  - `dayu/tools/web/web_tools.py:2111-2213`（catch 到 `RuntimeError` 后走通用路径）
- **输入场景**: Playwright 浏览器路径中，初始 URL、page.goto 后 page.url、settle 后 page.url、warmup home_url、或 browser request URL 被 `is_url_allowed` 谓词拒绝为私网地址。
- **实际分支**: `_raise_if_playwright_url_blocked` 抛出 `RuntimeError("URL is blocked by fetch safety policy during {reason}: {url}")`。该异常不被 `_try_playwright_fallback` 的 `except CancelledError` 捕获，向上传播到 `_fetch_web_page_business`。在 `_fetch_web_page_business` 中：
  - `except _FetchUrlSafetyError`（行 2080）——不匹配（异常类型是 `RuntimeError`）
  - `except _FetchBodyLimitExceeded`（行 2094）——不匹配
  - `except RuntimeError`（行 2111）——匹配，进入通用异常处理
  - `isinstance(exc, _FetchContentConversionError)`（行 2119）→ False
  - 最终落到 `_raise_fetch_failure(error_code="content_conversion_failed", ...)`（行 2202-2213）
- **预期行为**: Playwright 路径的 URL 安全违规应与 requests 路径产生相同的结构化失败投影：`error_code="permission_denied"`、`blocked_by_safety_policy: True`、明确的 `blocked_url` 和 `blocked_stage`。
- **实际行为**: Playwright 路径的 URL 安全违规被投影为 `error_code="content_conversion_failed"`，丢失了 `blocked_by_safety_policy` 语义，`blocked_url` 和 `blocked_stage` 不在 internal_diagnostics 中。错误消息是 raw `RuntimeError` 字符串。
- **直接证据**:
  - `web_playwright_backend.py:1016-1018`: `raise RuntimeError(f"URL is blocked by fetch safety policy during {reason}: {url}")` —— 使用通用 `RuntimeError`
  - `web_fetch_orchestrator.py:437`: `raise _FetchUrlSafetyError(url=url, reason=reason)` —— 使用专用异常类型
  - `web_tools.py:2080`: `except _FetchUrlSafetyError as exc:` —— 只匹配专用异常类型
  - `web_tools.py:2111`: `except RuntimeError as exc:` —— 通用异常路径，`conversion_failure_reason` 保持为 ""
  - `web_tools.py:2204`: `error_code="blocked" if challenge is not None ... else "content_conversion_failed"` —— 最终错误码不正确
- **影响**: 同一业务事实（URL 被安全策略拒绝）在不同传输路径（requests vs Playwright）下产生不同的 `error_code` 和 internal_diagnostics。LLM 看到 `content_conversion_failed` 而非 `permission_denied`，可能导致不同的恢复决策（例如重试而非切换数据源）。违反 semantic ownership：URL safety 违规的分类应被 Web fetch owner 统一处理，不应因传输路径而异。
- **建议改法和验证点**:
  1. `_raise_if_playwright_url_blocked` 应抛出 `_FetchUrlSafetyError`（从 `web_fetch_orchestrator` 导入或提至共享契约模块）
  2. 验证 Playwright goto/warmup/settle/route 各点的 URL 安全违规均产生 `error_code="permission_denied"`
  3. 补充测试：Playwright 路径私网 URL 产生 `ToolFailedOutcome(error="permission_denied")`
- **修复风险（中）**: `web_playwright_backend.py` 需要 import `_FetchUrlSafetyError`。当前 `_FetchUrlSafetyError` 定义在 `web_fetch_orchestrator.py`。直接从 `web_fetch_orchestrator` 导入到 `web_playwright_backend` 不创建循环依赖（二者都是 `web_tools` 下的同级模块），但需要确认 import 路径干净。更优方案是将 `_FetchUrlSafetyError` 提取到共享异常模块。
- **严重程度（高）**: 同一安全违规在不同传输路径产生不同的 LLM-facing 错误码，影响模型恢复决策准确性，且违反 semantic ownership 原则。

### F-02-未修复-中-meta refresh 安全校验依赖 visited_urls 不包含 HTTP redirect 中间跳

- **入口/函数**: `_fetch_and_convert_content`（web_fetch_orchestrator.py:1330-1388）
- **文件(行号)**:
  - `web_fetch_orchestrator.py:1330`: `visited_urls = {url}`
  - `web_fetch_orchestrator.py:1386`: `visited_urls.add(next_meta_refresh_url)`
  - `web_fetch_orchestrator.py:880`: `directive.target_url in visited_urls`（meta refresh 防环检查）
- **输入场景**: 请求 URL A → HTTP redirect B → HTTP redirect C → 最终页 HTML 包含 meta refresh 回 B。
- **实际分支**: `visited_urls` 只跟踪初始 URL 和 meta refresh 目标。HTTP redirect 中间跳 B、C 不加入 `visited_urls`。meta refresh 防环检查（行 880）不会命中 B（因为 B 不在 visited_urls 中）。
- **预期行为**: 对于已访问过的任意 URL（包括 HTTP redirect 中间跳），meta refresh 不应再跳回。
- **实际行为**: meta refresh 会跳回 HTTP redirect 中间跳 URL，产生一轮多余的 fetch。但由于 HTTP redirect 环在 `_request_with_safe_redirects` 内部已有 30 跳上限，且 meta refresh 有 3 跳上限，每次 meta refresh 后回到 `_request_with_safe_redirects` 时 HTTP redirect 计数器重置，理论上可产生 `3 * 30 = 90` 跳的冗余往返。每次跳都经过 URL 安全校验，不会导致私网绕过，但存在资源浪费。
- **直接证据**:
  - `web_fetch_orchestrator.py:1353`: `http_redirect_hops += current_redirect_hops` —— redirect 跳数被累加但跳转 URL 不被记录
  - `web_fetch_orchestrator.py:1330-1330`: `visited_urls = {url}` —— 只包含初始 URL
  - `web_fetch_orchestrator.py:1386`: `visited_urls.add(next_meta_refresh_url)` —— 只添加 meta refresh 目标
- **影响**: 极端场景下额外 90 跳冗余请求（均在 URL 安全校验防护内）和额外延迟。不影响安全性。
- **建议改法和验证点**:
  1. `_request_with_safe_redirects` 返回跳转 URL 列表，在 `_fetch_and_convert_content` 中将其加入 `visited_urls`
  2. 或更简单：在 `_request_with_safe_redirects` 中直接接受 `visited_urls` 集合并进行防环
- **修复风险（低）**: 纯逻辑增强，不改现有安全校验行为。
- **严重程度（中）**: 有界但非最优的防环逻辑，不影响安全性但可能造成不必要的网络请求。

### F-03-未修复-中-`_build_fetch_content_runtime_context` 在被 `_FetchBodyLimitExceeded` 调用时可读到未受限 body

- **入口/函数**: `_FetchBodyLimitExceeded.__init__` → `_build_fetch_content_runtime_context(response)` → `_decode_response_text(response)` → `response.content`
- **文件(行号)**:
  - `web_fetch_orchestrator.py:195`（`_FetchBodyLimitExceeded.__init__` 调用 `_build_fetch_content_runtime_context`）
  - `web_fetch_orchestrator.py:728-731`（`_build_fetch_content_runtime_context` 调用 `_decode_response_text`）
  - `web_http_encoding.py:240`（`_decode_response_text` 读取 `response.content`）
- **输入场景**: wire body 上限被命中（`_append_limited_body_chunk` 抛 `_FetchBodyLimitExceeded`），此时 `response.raw` 部分已读，`response._content` 未设置。
- **实际分支**: `_FetchBodyLimitExceeded.__init__` 在构造时立即调用 `_build_fetch_content_runtime_context(response)`（行 195）。`_build_fetch_content_runtime_context` 调用 `_decode_response_text(response)`（行 728-731），后者通过 `response.content` 属性读取。由于 `_content` 未设置且 `raw` 中还有未消费的 chunk，`response.content` 会继续从 `raw` 读取剩余 body，产生一次无上限的完整 body 读取。
- **预期行为**: body limit 被命中后，异常上下文的 `raw_content_text` 应从已读取的 chunks 派生，而非重新从 raw 读取不受限的完整 body。
- **实际行为**: `_FetchBodyLimitExceeded` 构造时的 `raw_content_text` 来自 `_decode_response_text` 的完整 body 读取（通过 `response.content`），绕过了 `_FETCH_MAX_WIRE_BODY_BYTES` 限制。但由于 `_build_fetch_content_runtime_context` 包裹在 try/except 中（行 728-731），读取失败会降级为空字符串，而不会让异常构造本身再抛异常。
- **直接证据**:
  - `web_fetch_orchestrator.py:195`: `response_context=_build_fetch_content_runtime_context(response)` —— 在 `_FetchBodyLimitExceeded.__init__` 中调用
  - `web_http_encoding.py:240`: `content = getattr(response, "content", b"") or b""` —— `response.content` 属性在 `_content` 未设置时会从 `raw` 读取
  - `web_fetch_orchestrator.py:728-731`: try/except 包裹，降级为空字符串
- **影响**: 对于命中 wire limit 的超大响应，`_FetchBodyLimitExceeded` 的 `response_context.raw_content_text` 可能包含超出限制的完整 body（如果 `response.raw` 读取成功）。这不影响安全性（body 不会被投影给外部），但造成不必要的内存和 I/O 消耗。上层 `_fetch_web_page_business` 的 `except _FetchBodyLimitExceeded` 不使用 `raw_content_text`（只使用 `response_excerpt` 和 `response_headers`），所以实际影响很小。
- **建议改法和验证点**:
  1. `_FetchBodyLimitExceeded` 的 `response_context` 参数中，`raw_content_text` 应置为空或从已读取 chunk 截取
  2. 或延迟构造 `response_context`（接受 factory 而非 eager 求值）
  3. 或 `_build_fetch_content_runtime_context` 接受 `max_bytes` 参数限制读取
- **修复风险（低）**: `raw_content_text` 字段仅用于内部诊断，修改不影响外部行为。可先确认 `_fetch_web_page_business` 的 body limit 处理路径是否真的消费该字段。
- **严重程度（中）**: 局部违反 body limit 设计意图，虽然 try/except 降级和上层不使用该字段限制了实际影响。

### F-04-未修复-低-OpenAI retry 策略变更不改变运行时行为

- **入口/函数**: `compute_retry_decision`（retry_policy.py:112-115）
- **文件(行号)**:
  - `dayu/engine/runners/openai/retry_policy.py:115`（条件变更）
  - `tests/engine/runners/openai/test_retry_backoff.py:196-209`（新增测试）
- **输入场景**: 任意 `max_retries` 值，任意 `attempt` 值。
- **实际分支**: 原条件 `attempt > max_retries`，新条件 `attempt >= max_retries + 1`。
- **预期行为**: 行为不变量——两个条件对整数参数在数学上等价。
- **实际行为**: 行为不变。`x > n` 与 `x >= n + 1` 对所有整数 x、n 等价。
- **直接证据**:
  - `retry_policy.py:115` 旧: `if attempt > max_retries:`
  - `retry_policy.py:115` 新: `if attempt >= max_retries + 1:`
  - 数学等价: ∀ x∈Z, n∈Z: x > n ⇔ x ≥ n+1
- **影响**: 无运行时行为变化。变更纯粹是语义澄清——让代码更明确地表达"`max_retries` 是首次失败后的重试次数"。新增测试 `test_compute_retry_decision_zero_max_retries_disables_retry` 是有效的契约测试，确认 `max_retries=0` 语义。
- **建议改法和验证点**: 无需修改。当前变更已正确。需要确认 Runner 调用侧传入的 `attempt` 值语义一致（1-based 失败次数），建议补一个集成级验证。
- **修复风险（低）**: 不存在修复需求。
- **严重程度（低）**: 不是缺陷，仅记录为澄清性变更。

### F-05-未修复-低-`_decompress_limited_response_body` 解压循环后存在冗余 size 检查

- **入口/函数**: `_decompress_limited_response_body`（web_fetch_orchestrator.py:565-612）
- **文件(行号)**:
  - `web_fetch_orchestrator.py:594-602`（循环内检查）
  - `web_fetch_orchestrator.py:603-611`（循环后检查，与循环内检查重复）
- **输入场景**: 响应 body 包含 `Content-Encoding` token。
- **实际分支**: 解压循环内每轮都检查 `len(decoded) > _FETCH_MAX_DECOMPRESSED_BODY_BYTES`。循环结束后又做一次完全相同的检查。
- **预期行为**: 循环后的检查仅对无编码（`identity` 或空 Content-Encoding）场景有实际作用（防御 wire limit 未捕获的边界情况）。对于有编码的场景，循环后的检查与循环内最后一次检查重复。
- **实际行为**: 功能正确，但代码存在无副作用重复。`identity` 和无编码时循环后的检查提供 defense-in-depth（wire body 等于 decompressed body，应已被 wire limit 捕获但在此兜底）。
- **直接证据**:
  - `web_fetch_orchestrator.py:594-602`: 循环内 `if len(decoded) > _FETCH_MAX_DECOMPRESSED_BODY_BYTES: raise ...`
  - `web_fetch_orchestrator.py:603-611`: 循环后完全相同检查
- **影响**: 无功能影响，仅轻微代码冗余。循环后检查为无编码场景提供 defense-in-depth。
- **建议改法和验证点**: 可选：将循环后检查范围缩小为仅覆盖无编码场景（`if not encoding_tokens and len(decoded) > ...`）；或保留作为 defense-in-depth 并添加注释说明意图。
- **修复风险（低）**: 仅代码清理，不改行为。
- **严重程度（低）**: 非缺陷，纯代码风格观察。

## Owner-Level Verification Summary

### Web redirect/meta refresh/Playwright 私网绕过（Finding 145711-01）

| 校验点 | 是否校验 | 位置 | 备注 |
|---|---|---|---|
| 初始请求 URL | ✓ | `_request_with_safe_redirects:685` (http_request) | |
| HTTP 响应 URL | ✓ | `_request_with_safe_redirects:697` (http_response) | belt-and-suspenders |
| HTTP redirect Location | ✓ | `_request_with_safe_redirects:707` (http_redirect) | |
| Meta refresh target | ✓ | `_resolve_meta_refresh_follow_target:888-899` (meta_refresh) | 异常被包装为 `_FetchContentConversionError` |
| Playwright goto URL | ✓ | `_playwright_sync_worker:1167-1171` (playwright_goto) | **但抛 `RuntimeError` 而非 `_FetchUrlSafetyError`，见 F-01** |
| Playwright page.url after goto | ✓ | `_playwright_sync_worker:1195-1199` (playwright_response) | **同上异常类型问题** |
| Playwright page.url after settle | ✓ | `_playwright_sync_worker:1218-1222` (playwright_settled_page) | **同上异常类型问题** |
| Playwright warmup home_url | ✓ | `_maybe_warmup_playwright_page:1063-1070` (playwright_warmup) | 被 except 捕获后 skip warmup |
| Playwright warmup response | ✓ | `_maybe_warmup_playwright_page:1078-1082` (playwright_warmup_response) | 被外层 except 捕获 |
| Playwright route request | ✓ | `_route_handler_abort_resources:916` | abort 私网请求 |

### Body limit 检查（Finding 145711-11）

| 检查点 | 是否覆盖 | 位置 | 备注 |
|---|---|---|---|
| Content-Length 预检 | ✓ | `_read_limited_response_body:629-643` | 声明值超限 → fail before read |
| Wire body chunk 读取 | ✓ | `_append_limited_body_chunk:467-479` | 逐 chunk 累计检查 |
| Decompressed body | ✓ | `_decompress_limited_response_body:594-602` | 每层解压后检查 |
| 无编码兜底 | ✓ | `_decompress_limited_response_body:603-611` | defense-in-depth |
| 转换前 body 已 bounded | ✓ | `_fetch_and_convert_content:1356` → `_materialize_response_body` | `_content` 写入后再进 HTML/Docling |
| 无未限制读取入口 | △ | 见 F-03 | `_FetchBodyLimitExceeded` 构造时 `_build_fetch_content_runtime_context` 可通过 `response.content` 读取未限制 body（有 try/except 降级） |

### Doc search symlink containment（Finding 145711-09）

| 检查点 | 是否覆盖 | 位置 | 备注 |
|---|---|---|---|
| 候选文件 resolved containment | ✓ | `_resolve_search_files_candidate:1544-1553` | `resolve(strict=True)` + `_is_relative_to` 逐 root 检查 |
| Resolve 后再 `is_file()` | ✓ | `_resolve_search_files_candidate:1551` | 防止 resolved 路径非普通文件 |
| Symlink 目录内文件 | ✓ | 隐式覆盖 | `rglob` 跟随目录 symlink，但每个文件独立 resolved |
| OSError 处理 | ✓ | `_resolve_search_files_candidate:1545-1547` | 无法 resolve → 跳过 |
| Processor 读 | ✓ | `_try_create_processor(resolved_file)` | 使用 resolved 路径 |
| Line scan 读 | ✓ | `_search_via_line_scan(resolved_file, ...)` | 使用 resolved 路径 |
| TOCTOU 窗口 | ○ | 非 exploitable | `resolve(strict=True)` 原子获取真实路径，后验证 containment |

### FMP exact-match identity（Finding 145711-10）

| 检查点 | 是否覆盖 | 位置 | 备注 |
|---|---|---|---|
| 模糊回退删除 | ✓ | `_select_symbol_result:297-299` | `return results[0]` → `raise FmpCompanyInfoResolutionError` |
| 精确匹配后两跳仍执行 | ✓ | `_select_symbol_result:295-296` | 仅 exact match 返回 `item` |
| 空结果 | ✓ | `_select_symbol_result:284-285` | 已有 len==0 检查保留 |
| 测试更新 | ✓ | `test_fmp_company_info_resolver.py:1139-1170` | 旧 test 改为 assert raise，验证单 call |
| README 同步 | ✓ | `dayu/fins/README.md:115` | "无精确 ticker 命中" 已加入错误条件 |
| Service 端语义 | ✓ | 无需修改 | Service 已有 ticker-only fallback |

### Retry max_retries=0（Finding 150304-05）

| 检查点 | 是否覆盖 | 位置 | 备注 |
|---|---|---|---|
| 条件等价性 | ✓ | `retry_policy.py:115` | 数学等价，行为不变 |
| max_retries=0 测试 | ✓ | `test_retry_backoff.py:196-209` | `attempt=1, max_retries=0` → `should_retry=False` |
| 其他 retry count 不破坏 | ✓ | 数学等价性保证 | 所有 `(attempt, max_retries)` 组合行为不变 |
| Runner 侧集成 | △ | 未在 diff 内 | 需确认 Runner 传入的 `attempt` 为 1-based 失败次数 |

## AGENTS.md 约束检查

- typing: 所有新增函数均有完整类型标注，无 `Any`/`object` 使用。`Protocol` 类正确使用。✓
- docstring: 所有新增函数均有中文 docstring，含参数、返回值、异常。✓
- 无新 `hasattr`/`getattr`: 新增代码未引入 `hasattr`/`getattr` 逃生口。✓（预存 `getattr(response, "url", "")` 在已有代码中，不在本次 diff 新增范围内）
- 无魔法数字: 新常量均命名（`_FETCH_MAX_WIRE_BODY_BYTES` 等）。✓
- 模块私有辅助函数: 新函数均为模块级私有（`_` 前缀）。✓
- 无兼容性代码: 未引入 re-export/wrapper/facade。✓

## Open Questions

1. **Playwright warmup URL 安全失败静默**: `_maybe_warmup_playwright_page:1069-1070` 在 warmup 被 `_raise_if_playwright_url_blocked` 拦截时 `except RuntimeError: return`，静默跳过 warmup。这是预期行为（warmup 是 best-effort），但需要确认调用的 `page.goto` 之前的新 URL 检查（行 1063-1070）使用的是 home_url 而非 target URL，home_url 被拒绝后 warmup 跳过——这正确。但如果在 warmup `page.goto(home_url)` 内部触发的导航重定向改变了 `page.url`，随后的 `page.url` 检查（行 1078-1082）应能捕获。确认 warmup 中 page.goto 是否会因服务端 redirect 到达非预期 URL。

2. **`_FetchUrlSafetyError` 作为内部异常应否暴露给 `web_tools.py` 外部**: 当前 `_FetchUrlSafetyError`（以及 `_FetchBodyLimitExceeded`）在 `web_tools.py` 中被 import 并用于 except 子句。这是内部模块间合理使用。但如果未来这两个异常需要被 Host/Service 层感知（例如用于 audit/trace），应考虑提升为公共契约异常。

3. **`_request_with_safe_redirects:697` 的 response_url 校验是否必要**: `allow_redirects=False` 时 `response.url` 等于请求 URL（`current_url`），而行 685 已校验过 `current_url`。这个校验是 belt-and-suspenders，无害但也不增加有效覆盖。可考虑降级为 debug assertion 或保留注释说明防御意图。

## Residual Risk

1. **Playwright 实时浏览器行为未经烟雾测试**: 测试覆盖了 route 级确定性回归（`test_playwright_route_blocks_private_request_before_continue`），但未执行真实浏览器 + 网络请求的烟雾测试。这是已知限制（implementation artifact 已记录），风险低——URL 安全校验路径是纯同步谓词，不受浏览器异步行为影响。

2. **Web body wire-byte 统计依赖 `requests` raw stream**: 生产路径使用 `response.raw.stream(amt, decode_content=False)`。测试使用 `urllib3.HTTPResponse(body=BytesIO(...), preload_content=False)`——包含真实 urllib3 raw stream 行为。但如果 `requests` 版本变更导致 `raw.stream` 行为变化（例如 chunk 大小语义），wire limit 检查可能受影响。风险低——`requests` API 稳定。

3. **Doc search 中的目录级 symlink**: `_resolve_search_files_candidate` 对 `rglob` 发现的每个文件独立 resolve，但 `rglob` 本身跟随目录 symlink。如果 allowed_root 内存在指向外部的目录 symlink，`rglob` 会遍历外部目录的文件，随后 `_resolve_search_files_candidate` 逐个拒绝。这正确但可能有性能影响（遍历外部大目录）。建议在后续增强中对 `dir_path` 本身也做 resolved containment 预检。

4. **`_decode_response_text` 未感知 body limit**: 如 F-03 所述，`_decode_response_text` 本身不执行 body limit，依赖调用方在调用前已执行 `_materialize_response_body`。当前所有正常路径（`_fetch_and_convert_content` 主线）满足此前提，但异常路径（`_build_fetch_content_runtime_context`）不满足。应在 `_build_fetch_content_runtime_context` 的 docstring 或调用方注释中标明此依赖。

5. **Cancellation 与 body 读取的交互**: `_request_with_safe_redirects` 在每跳前后检查取消，`_read_limited_response_body` 不在 chunk 循环内检查取消。如果 body 非常大且接近 limit，chunk 读取循环可能持续较长时间不响应取消。建议在 `_read_limited_response_body` 的 chunk 循环中增加定期取消检查。

6. **`_is_safe_public_url` DNS 解析的 TOCTOU**: DNS 解析与 HTTP 请求之间的时间窗口内，DNS 记录可能变化。这是 DNS-based 安全检查的固有局限，不是本次变更引入的新风险。已在 original implementation 中存在。

7. **Batch B/C/D/E 未开始**: 按 controller adjudication plan，后续 batch 的修复可能会触及共享接口（如 `_FetchUrlSafetyError` 定义位置、`web_playwright_backend` 接口签名）。建议在后续 batch 前先修复 F-01，避免异常类型定义位置成为后续变更的耦合点。
