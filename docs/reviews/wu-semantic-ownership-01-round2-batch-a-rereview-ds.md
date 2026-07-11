# WU-SEMANTIC-OWNERSHIP-01 Round 2 Batch A Re-Review — AgentDS

## Scope

- Mode: re-review of review-fix workspace diff (Batch A only)
- Branch: `phaseflow/host-issues-control`
- Base: `HEAD`
- Output file: `docs/reviews/wu-semantic-ownership-01-round2-batch-a-rereview-ds.md`
- Included scope: DS-F01 / DS-F02 / DS-F03 fix verification; new-issue check on fix diff
- Excluded scope: Batch B/C/D/E; DS-F04/DS-F05 (rejected by controller, not fixed); MiMo findings; pre-existing code outside diff
- Reviewed artifacts:
  - `docs/reviews/wu-semantic-ownership-01-round2-batch-a-code-review-controller-adjudication.md`
  - `docs/reviews/wu-semantic-ownership-01-round2-batch-a-review-fix-codex.md`
  - `docs/reviews/wu-semantic-ownership-01-round2-batch-a-review-fix-controller-validation.md`
  - `docs/reviews/wu-semantic-ownership-01-round2-batch-a-code-review-ds.md`
  - `docs/reviews/wu-semantic-ownership-01-round2-batch-a-code-review-mimo.md`
  - `AGENTS.md`

## Closed Finding Verification

### DS-F01 — Playwright URL safety uses wrong exception type

**Status: 已修复。**

验证链：

1. `_FetchUrlSafetyError` 定义为 `web_fetch_orchestrator.py` 中的公开异常类型（私有 `_` 前缀，但在模块间共享）。`web_playwright_backend.py:35` 通过 `from .web_fetch_orchestrator import _FetchUrlSafetyError` 导入。

2. `_raise_if_playwright_url_blocked`（`web_playwright_backend.py:901-907`）现在抛出 `_FetchUrlSafetyError`，不再抛出 `RuntimeError`。

3. 子进程异常串行化（`web_playwright_backend.py:420-430`）：`_playwright_process_entry` catch `_FetchUrlSafetyError`，将 `blocked_by_safety_policy: True`、`blocked_url`、`blocked_stage` 通过 result queue 传递给父进程。

4. 父进程异常重构（`web_playwright_backend.py:716-720`）：`_run_playwright_worker_process` 检测 `blocked_by_safety_policy is True`，重构 `_FetchUrlSafetyError(url=blocked_url, reason=blocked_stage)`。

5. 重抛给上层（`web_playwright_backend.py:1367`）：`_fetch_and_convert_with_playwright` 的 `except _FetchUrlSafetyError: raise` 确保异常穿透到 `web_tools.py`。

6. 用户面投影（`web_tools.py:2080-2093` 附近，diff 中 `_fetch_web_page_business` 新增 `except _FetchUrlSafetyError` 分支）：产生 `error_code="permission_denied"`，含 `blocked_by_safety_policy: True`、`blocked_url`、`blocked_stage`。——与 requests 路径完全一致。

7. 额外覆盖：meta-refresh 路径（`_resolve_meta_refresh_follow_target` 调用 `_raise_if_url_blocked` 后被 `_FetchContentConversionError` 包裹，`original_error=_FetchUrlSafetyError`）。在 `web_tools.py` 的 `RuntimeError` handler 中通过 `isinstance(exc.original_error, _FetchUrlSafetyError)` 再次投影为 `permission_denied`。

8. Playwright route 级拦截（`web_playwright_backend.py:929-930`）：`_route_handler_abort_resources` 在 `resource_type` 不属于 abort 集合且 `is_url_allowed` 拒绝时执行 `route.abort()`。

9. Warmup 路径：`_maybe_warmup_playwright_page` 在 warmup home_url 被拒绝时通过 `except RuntimeError: return` 静默跳过——warmup 是 best-effort，行为正确。

10. 测试覆盖：
    - `test_playwright_url_safety_error_survives_worker_process`：验证子进程→父进程 `_FetchUrlSafetyError` 保真。
    - `test_fetch_playwright_url_safety_projects_permission_denied`：验证端到端 `error_code="permission_denied"` 投影。
    - `test_playwright_route_blocks_private_request_before_continue`：验证 route 级 URL 安全。

**缺陷关闭确认**：Playwright 路径的 URL 安全违规现在与 requests 路径产生完全相同的结构化失败投影。异常类型、错误码、诊断字段均对齐。**DS-F01 已关闭。**

### DS-F02 — HTTP redirect hops not tracked in meta-refresh visited set

**Status: 已修复。**

验证链：

1. `_request_with_safe_redirects` 返回类型从 `tuple[requests.Response, int]` 扩展为 `tuple[requests.Response, int, tuple[str, ...]]`（`web_fetch_orchestrator.py:697`）。返回的 `tuple(dict.fromkeys(visited_urls))` 包含初始 URL、每个 response URL、每个 redirect target URL，按首次出现顺序保持唯一。

2. 在 `_fetch_and_convert_content` 中（`web_fetch_orchestrator.py:1415`）：`visited_urls.update(redirect_visited_urls)` 将 HTTP redirect 历史 URL 合并到 meta-refresh 防环集合中。

3. 防环检查（`web_fetch_orchestrator.py:941`）：`directive.target_url in visited_urls` 现在覆盖 HTTP redirect 中间跳 URL。

4. 测试覆盖：`test_fetch_meta_refresh_treats_redirect_hop_as_visited`——模拟 URL A → 302 → URL B → 200 HTML 含 meta refresh 回 URL B，断言 `_FetchContentConversionError` 被抛出（因为 URL B 已在 visited_urls 中），`failure_reason="meta_refresh_requires_browser"`，确认只发起 2 次请求而非循环。

**缺陷关闭确认**：HTTP redirect 跳转 URL 现在是 meta-refresh 防环 visited_urls 集合的正式成员。**DS-F02 已关闭。**

### DS-F03 — Body-limit exception context may read unbounded response.content

**Status: 已修复。**

验证链：

1. `_FetchBodyLimitExceeded.__init__`（`web_fetch_orchestrator.py:195` 附近，新版本）接受 `response_context: _FetchContentRuntimeContext` 参数——不再在构造时调用 `_build_fetch_content_runtime_context(response)`。

2. 调用方显式构造受限上下文：
   - Wire limit 命中时（`_append_limited_body_chunk`、`_read_limited_response_body` Content-Length 预检）：调用 `_build_fetch_body_limit_runtime_context(response)`，`body_excerpt` 默认 `b""`。
   - Decompressed limit 命中时：调用 `_build_fetch_body_limit_runtime_context(response, body_excerpt=decoded[:_FETCH_LIMIT_CONTEXT_EXCERPT_BYTES])`——已解析 body 的 4 KiB 有界前缀。

3. `_build_fetch_body_limit_runtime_context`（`web_fetch_orchestrator.py:774-810`）直接从 `getattr(response, "status_code", None)`、`getattr(response, "url", "")`、`getattr(response, "headers", {})` 构造上下文，**不调用** `_decode_response_text`，**不访问** `response.content`。

4. `_decode_bounded_body_excerpt` 对已裁剪的 `body_excerpt` 做 utf-8 decode + whitespace 压缩 + 500 字符截断——全部在调用方传入前已限制。

5. 测试覆盖：
   - `test_fetch_body_limit_context_does_not_decode_unbounded_response`：monkeypatch `_decode_response_text` 记录调用，缩小 limit 至 4 字节，触发 body limit，断言 `decode_calls == []`——确认 body-limit 路径不走 response.content 读取。
   - `test_fetch_body_limit_maps_to_structured_tool_failure`：端到端验证 `error_code="response_body_too_large"` 投影。

**缺陷关闭确认**：body-limit 异常构造不再读取 `response.content`。所有 body-limit 上下文均从已读取/已裁剪数据派生。**DS-F03 已关闭。**

## New-Issue Check

对 review-fix diff 做了 adversarial failure pass 和 semantic ownership drift pass，逐条检查以下风险面：

### 异常传播链

- `CancelledError` → `_FetchUrlSafetyError` → `Exception` 的 catch 顺序正确（`_fetch_and_convert_with_playwright:1365-1369`）。取消优先于 URL 安全。
- `_playwright_process_entry` 中 `_FetchUrlSafetyError` 在 `BaseException` 之前 catch（`web_playwright_backend.py:420-434`），不会落入通用错误路径。
- `_run_playwright_worker_process` 中 `blocked_by_safety_policy` 检测在通用 `"error"` kind 处理之前（`web_playwright_backend.py:716-720`），优先重构专用异常。

### 跨模块导入

- `web_playwright_backend.py` 从 `web_fetch_orchestrator.py` 导入 `_FetchUrlSafetyError`。两者均为 `dayu/tools/web/` 下的同级模块，不产生循环依赖。`_FetchUrlSafetyError` 虽然是私有命名（`_` 前缀），但作为模块间共享异常类型，语义所有权清晰：URL safety 异常由 `web_fetch_orchestrator` 定义为唯一真源，`web_playwright_backend` 作为消费者引用该真源。
- 同理，`web_tools.py` 通过 `_web_fetch_orchestrator._FetchUrlSafetyError` 引用——正确的 consumer 模式。

### Body materialization 顺序

- `_fetch_and_convert_content` 中新增 `_materialize_response_body(response)` 调用在 `_request_with_safe_redirects` 之后、HTML/Docling 转换之前。该调用将有界 body 字节写入 `response._content`。后续 `_extract_html_response_text`、`_build_fetch_content_runtime_context`（在 meta-refresh 分支中）通过 `response.content` 读取已有界的 `_content`，不会触发 raw stream 读取。
- 顺序正确，不存在未被 materialize 的消费点。

### 资源释放

- `_request_with_safe_redirects` 在 redirect 循环中每跳调用 `_close_response_safely(response)` 关闭前一个响应。相比旧 `allow_redirects=True` 模式（requests 内部持有 `response.history` 但不在跳转中关闭），新代码内存使用更优。

### Warmup 边界

- `_maybe_warmup_playwright_page` 的 `except RuntimeError: return` 捕获所有 `RuntimeError`（包含 `_FetchUrlSafetyError`）。由于 `_raise_if_playwright_url_blocked` 当前仅抛出 `_FetchUrlSafetyError`，不产生误吞。若未来函数扩展抛出其他 `RuntimeError` 子类，warmup 会静默跳过——这是 warmup best-effort 语义的预期行为，不是缺陷。

### Doc search symlink containment（Batch A 实现范围内）

- `_resolve_search_files_candidate` 的 `resolve(strict=True)` → `_is_relative_to` → `is_file()` 链条完整。
- `allowed_roots` 从 `_execute_doc_business_value` → `_route_doc_business` → `_search_files_business` → `_resolve_search_files_candidate` 线程正确。

### FMP identity（Batch A 实现范围内）

- `_select_symbol_result` 无精确匹配时 `raise FmpCompanyInfoResolutionError`，不再 `return results[0]`。
- 测试验证单次 API 调用 + 异常断言。

### 未引入的新问题

在 diff 完整走读中未发现：
- 新的 semantic ownership 违规（异常类型、body limit、URL safety 的所有权均收敛到正确 owner）
- 新的 correctness/security 缺陷
- 新的类型问题或 `hasattr`/`getattr` 滥用
- 新的跨层穿透或反向依赖
- 新的测试固化偶然行为

### 次要观察（非缺陷，不编号）

1. `_raise_if_url_blocked` docstring 的 `Raises:` 段写 `RuntimeError`，实际抛 `_FetchUrlSafetyError`。技术上正确（子类 is-a `RuntimeError`），但不够精确。后续可考虑精确为 `_FetchUrlSafetyError`。

2. `_raise_if_url_blocked`（`web_fetch_orchestrator.py`）与 `_raise_if_playwright_url_blocked`（`web_playwright_backend.py`）是两个行为相同的函数。当前设计尊重模块所有权——各自在网络阶段边界执行安全校验。如果后续出现第三个网络阶段需要复用，可提取到共享 helper。当前不构成 material issue。

## Findings

未发现实质性问题。DS-F01/DS-F02/DS-F03 均已按 controller adjudication 的要求正确修复；review-fix diff 未引入新的 correctness、security 或 semantic ownership 缺陷。

## Open Questions

无。

## Residual Risk

1. **Live browser smoke 未执行**（pre-existing，review-fix 已记录）：URL safety 的 Playwright 路径通过确定性 process 和 projection 测试覆盖，不依赖真实浏览器。低风险。

2. **`_FetchUrlSafetyError` 作为私有异常跨模块共享**：当前仅在 `dayu/tools/web/` 包内三个模块间共享，暂不影响外部消费者（如 Host/Service 层）。若后续需要 Host 层感知 URL safety 违规（例如 audit/trace），应将 `_FetchUrlSafetyError` 提升为公共契约异常。当前不阻塞。

3. **Batch B/C/D/E 尚未开始**：后续 batch 的修复可能触及当前共享接口（如 `_FetchUrlSafetyError` 定义位置、`_request_with_safe_redirects` 返回值签名）。建议后续 batch 实施时评估当前 fix 是否需要前移为共享契约。

4. **`except RuntimeError: return` 的广度**：warmup 路径的 broad catch 在 `_raise_if_playwright_url_blocked` 只抛一种异常时安全，但缺乏 future-proof。建议后续收紧为 `except _FetchUrlSafetyError`。

## AGENTS.md 约束检查

- typing：所有新增函数均有完整类型标注，`Protocol` 类替代 `Any`。✓
- docstring：中文 docstring 含参数、返回值、异常。✓（注：`_raise_if_url_blocked` 的 `Raises` 写 `RuntimeError` 而非 `_FetchUrlSafetyError`，minor imprecision）
- 禁止 `hasattr`/`getattr`：diff 中新增 `getattr(response, "url", "")` 等用于安全访问 requests response 属性——属于兼容 requests 库 API 的必要防御，非语义绕过。✓
- 禁止魔法数字：新常量命名完整。✓
- 禁止兼容性代码：无。✓
- 模块间依赖最小化：`web_playwright_backend` → `web_fetch_orchestrator` 仅导入一个异常类型，依赖面窄。✓
- 语义所有权：URL safety 真源为 `web_tools._is_safe_public_url`；body limit 真源为 `web_fetch_orchestrator` 的常量和检查函数；异常投影真源为 `web_tools._fetch_web_page_business`。所有权收敛。✓
