# WU-SEMANTIC-OWNERSHIP-01 Round 2 Batch A Re-Review - AgentMiMo

## Scope

- Mode: current changes (workspace diff against HEAD)
- Branch: `phaseflow/host-issues-control`
- Base: `HEAD` (commit `42140fa7`)
- Output file: `docs/reviews/wu-semantic-ownership-01-round2-batch-a-rereview-mimo.md`
- Included scope: Batch A only — review-fix 后的 workspace diff
- Excluded scope: Batch B/C/D/E
- Parallel review coverage: 无
- Reviewed artifacts:
  - `AGENTS.md`
  - `docs/reviews/wu-semantic-ownership-01-round2-batch-a-code-review-controller-adjudication.md`
  - `docs/reviews/wu-semantic-ownership-01-round2-batch-a-review-fix-codex.md`
  - `docs/reviews/wu-semantic-ownership-01-round2-batch-a-review-fix-controller-validation.md`
  - `docs/reviews/wu-semantic-ownership-01-round2-batch-a-code-review-ds.md`
  - `docs/reviews/wu-semantic-ownership-01-round2-batch-a-code-review-mimo.md`

## DS Finding Closure Verification

### DS-F01 — Playwright URL safety uses wrong exception type

**结论：已关闭。**

修复走读：

1. `web_playwright_backend.py` 新增 `_raise_if_playwright_url_blocked`，直接 `raise _FetchUrlSafetyError(url=url, reason=reason)`（从 `web_fetch_orchestrator` 导入）。
2. Playwright worker 子进程 `_playwright_process_entry` 新增 `except _FetchUrlSafetyError` 分支，将 `blocked_by_safety_policy=True`、`blocked_url`、`blocked_stage` 写入 result queue payload。
3. 父进程 `_run_playwright_worker_process` 检查 `payload.get("blocked_by_safety_policy") is True`，从 payload 重建 `_FetchUrlSafetyError` 后 raise。
4. `_fetch_and_convert_with_playwright` 新增 `except _FetchUrlSafetyError: raise`，不再被通用 `except Exception` 吞掉。
5. `web_tools._fetch_web_page_business` 的 `except _FetchUrlSafetyError` 分支（行 2078-2093）投影 `error_code="permission_denied"` + `blocked_by_safety_policy` + `blocked_url` + `blocked_stage`。
6. `_FetchContentConversionError` 包裹的 URL safety 拒绝（meta refresh 路径）也在 `except RuntimeError` 内通过 `isinstance(exc.original_error, _FetchUrlSafetyError)` 检查投影为 `permission_denied`（行 2129-2145）。

**验证点**：
- `_FetchUrlSafetyError` 继承 `RuntimeError`（`web_fetch_orchestrator.py:216`），`_maybe_warmup_playwright_page` 的 `except RuntimeError: return` 正确捕获并跳过 warmup（warmup 是 best-effort）。
- `test_playwright_url_safety_error_survives_worker_process`：验证 `_FetchUrlSafetyError` 穿越子进程后保留 `url`/`reason`。
- `test_fetch_playwright_url_safety_projects_permission_denied`：验证端到端投影为 `permission_denied`。
- `test_playwright_route_blocks_private_request_before_continue`：验证 route handler 对私网 URL 执行 `route.abort()`。

### DS-F02 — HTTP redirect hops not tracked in meta-refresh visited set

**结论：已关闭。**

修复走读：

1. `_request_with_safe_redirects` 返回值新增 `visited_urls: tuple[str, ...]`（行 697），在 redirect 循环中记录 `response_url` 和 `next_url`。
2. `_fetch_and_convert_content` 拿到 `redirect_visited_urls` 后执行 `visited_urls.update(redirect_visited_urls)`（行 1438-1439）。
3. `_resolve_meta_refresh_follow_target` 的 `visited_urls: Collection[str]` 参数现在包含 redirect 中间跳 URL。

**验证点**：
- `test_fetch_meta_refresh_treats_redirect_hop_as_visited`：A → 302 → B → HTML meta refresh → B，断言触发 `meta_refresh_requires_browser`（因 B 已在 visited_urls 中）。
- session.calls 只记录两次 GET（A 和 B），无多余循环。

### DS-F03 — Body-limit exception context may read unbounded response.content

**结论：已关闭。**

修复走读：

1. 新增 `_build_fetch_body_limit_runtime_context(response, body_excerpt=b"")`（行 785-810），不调用 `_build_fetch_content_runtime_context`。
2. 该函数从 `body_excerpt` 参数（已由调用方裁剪）解码 `response_excerpt` 和 `raw_content_text`，不读取 `response.content`。
3. `_append_limited_body_chunk` 在 wire limit 命中时调用 `_build_fetch_body_limit_runtime_context(response)`（无 body_excerpt，context 为空白）。
4. `_decompress_limited_response_body` 在 decompressed limit 命中时传入 `body_excerpt=decoded[:_FETCH_LIMIT_CONTEXT_EXCERPT_BYTES]`。

**验证点**：
- `test_fetch_body_limit_context_does_not_decode_unbounded_response`：monkeypatch `_decode_response_text` 记录调用，断言 `_read_limited_response_body` 触发 `_FetchBodyLimitExceeded` 时 `decode_calls == []`。
- `_build_fetch_body_limit_runtime_context` 的 docstring 明确说明"不会读取响应剩余 body"。

## New Material Issue Check

未发现新的实质性 correctness/security/semantic-ownership 问题。

逐项检查：

1. **`_FetchUrlSafetyError` 继承 `RuntimeError` 的影响**：所有 `except RuntimeError` 分支（warmup 跳过、通用异常处理）都能正确捕获 `_FetchUrlSafetyError`。warmup 路径跳过是正确行为；通用异常路径中，`_FetchContentConversionError` 包裹检查（`isinstance(exc.original_error, _FetchUrlSafetyError)`）确保最终投影为 `permission_denied`。无遗漏。

2. **`_request_with_safe_redirects` 返回 visited_urls 的去重**：使用 `tuple(dict.fromkeys(visited_urls))` 保持顺序去重，正确。

3. **`_build_fetch_body_limit_runtime_context` 的空 body_excerpt 处理**：`_decode_bounded_body_excerpt(b"")` 返回空字符串，`raw_content_text` 为空。无异常。

4. **`is_url_allowed` 谓词通过 `partial` 构造的一致性**：`_build_fetch_url_safety_predicate` 使用 `partial(_is_safe_public_url, allow_private_network_url=...)`，同一实例贯穿 warmup/probe/fetch/playwright 路径。无重复构造。

5. **测试覆盖**：118 passed, 1 skipped, pyright 0 errors。所有 DS accepted findings 均有对应测试验证。

## AGENTS.md 约束合规检查

| 约束 | 结果 |
|---|---|
| 函数完整中文 docstring（Args/Returns/Raises） | 通过 |
| 禁止 `object`/`Any`/无类型参数 | 通过：Protocol 类型替代 Any |
| 禁止魔法数字/字符串 | 通过：命名常量 |
| 禁止兼容性代码 | 通过 |
| 测试 owner-level 覆盖 | 通过 |

## Open Questions

无。

## Residual Risk

1. **Live browser smoke 未执行**：确定性 Playwright 进程/projection 测试覆盖了 URL safety 语义，无需真实浏览器。已在 controller validation 中记录。
2. **`_maybe_warmup_playwright_page` 中 `except RuntimeError: return` 捕获范围**：当前捕获 `_FetchUrlSafetyError`（因继承 `RuntimeError`）。若未来 `_FetchUrlSafetyError` 改为继承更具体的异常类型，warmup 中的 catch 需同步更新。当前无风险，但值得记录。

## Conclusion

**pass**。DS-F01、DS-F02、DS-F03 均已正确关闭。Playwright URL safety 使用 `_FetchUrlSafetyError` 统一异常类型，穿越子进程后保留结构化语义，端到端投影为 `permission_denied`；HTTP redirect 跳 URL 已纳入 meta-refresh 防环 visited set；body-limit 异常上下文不再读取未受限 body。未引入新的 material correctness/security/semantic-ownership 问题。测试 118 passed, pyright 0 errors。
