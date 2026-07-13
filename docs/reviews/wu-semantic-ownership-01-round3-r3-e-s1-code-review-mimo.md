# WU-SEMANTIC-OWNERSHIP-01 Round3 R3-E Slice S1 Code Review — AgentMiMo

## Review Metadata

- **Reviewer**: AgentMiMo
- **Review type**: implementation code review
- **Timestamp**: `20260713-130847`
- **Scope**: S1 Web egress 与 response ownership
- **Plan reference**: `docs/host/wu-semantic-ownership-01-round3-r3-e-web-doc-egress-resource-plan.md` §6.1, §7 S1
- **Implementation artifact**: `docs/reviews/wu-semantic-ownership-01-round3-r3-e-s1-implementation-codex.md`
- **Controller validation**: `docs/reviews/wu-semantic-ownership-01-round3-r3-e-s1-controller-validation.md`

## Changed Files

| File | Change |
|---|---|
| `dayu/tools/web/web_egress_policy.py` | 新增：URL 授权策略、DNS 解析、地址分类、AuthorizedHttpTarget |
| `dayu/tools/web/web_http_session.py` | 修改：target-bound transport、response lease、send_authorized_request |
| `dayu/tools/web/web_fetch_orchestrator.py` | 修改：redirect/cancel 用 lease、response URL 验证、meta refresh egress wiring |
| `dayu/tools/web/web_playwright_backend.py` | 修改：public typed unavailable、route handler egress policy |
| `dayu/tools/web/web_tools.py` | 修改：删除旧 predicate、egress policy 接线、search result filter |
| `utils/diagnose_web_access.py` | 修改：复用 shared policy、删除自建 predicate、raw requests 用 lease |
| `tests/tools/web/test_web_tools_provider.py` | 修改：新增 egress/peer/retry/lease/close matrix 测试 |
| `tests/tools/web/test_diagnose_web_access.py` | 修改：egress policy rejection、public browser typed unavailable |

## Findings

### 01-未修复-低-diagnostic session 成功路径 session.close() 位置不明显

- **位置**: `utils/diagnose_web_access.py:1352` — `_build_requests_profile` 成功路径
- **问题类型**: 代码可读性
- **当前写法**: `session.close()` 位于 `except` 块之后、`with lease:` 块之前。成功路径先关闭 diagnostic source session，再进入 lease context 处理 response。
- **反例/失败场景**: 无功能问题。session 在所有路径均被关闭：异常路径由各 `except` 块显式关闭；成功路径由 `session.close()` 显式关闭。
- **为什么有问题**: 不影响正确性。`session.close()` 位置正确但位于 `except` 块之后的 fallthrough 路径，阅读时容易误以为只在异常路径关闭。
- **直接证据**: `diagnose_web_access.py:1342`（_FetchUrlSafetyError 关闭）、`:1352`（RuntimeError 关闭）、`:1355`（成功路径关闭）、`:1383`（`finally: session.close()` 兜底）
- **影响**: 无功能影响。session 在所有路径均被正确关闭。
- **建议改法和验证点**: 可选优化：将成功路径的 `session.close()` 移入 `finally` 块（但需避免与 `with lease` 的嵌套关系复杂化）。当前实现已正确，仅影响可读性。
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低

**以上为唯一 finding。其余所有验证点均通过，详见下方逐项核对。**

## 逐项核对

### SSRF peer-proof：target-bound urllib3 transport

- ✓ `_PinnedHTTPConnection` / `_PinnedHTTPSConnection` 只 override `_new_conn()`，调用 `_connect_to_approved_addresses`。
- ✓ `_connect_to_approved_addresses`（`web_http_session.py:119-165`）按确定顺序遍历 `approved_addresses`，用 `urllib3_connection.create_connection((address, port), ...)` 建立直连 socket。
- ✓ `getpeername()` 在 socket 返回前验证 peer 属于 approved set（IPv4-mapped IPv6 规范化后比较）。
- ✓ peer mismatch → `sock.close()` + continue 到下一个 address。
- ✓ 所有 address 失败 → `NewConnectionError`，不 fallback DNS。
- ✓ pool `host` 保持原 IDNA hostname → HTTP Host / TLS SNI / cert hostname 不被 IP 替换（测试 `test_egress_target_bound_https_preserves_sni_certificate_and_host` 用本地 CA 证书验证）。
- ✓ requests==2.33.1 / urllib3==2.6.3 版本由测试 `test_egress_transport_dependency_versions_are_locked` 锁定。

### Retry 复用同一 immutable approved set

- ✓ 测试 `test_egress_pinned_retry_uses_same_approved_addresses`：第一次 connect 模拟 RST，第二次成功；断言 `attempted_addresses == ["127.0.0.1", "127.0.0.1"]`，resolver 只调用一次。
- ✓ 测试 `test_egress_pinned_retry_exhaustion_has_no_fallback_dns`：所有 approved address 失败；断言 `attempted_addresses == ["127.0.0.1"] * 4`（connect=3 + 1），resolver 只调用一次。
- ✓ `_send_authorized_request` 中 `Retry` 从 source session 复制，retry 只在同一 pool 内重建 socket。

### Redirect 重新 authorize

- ✓ `_request_with_safe_redirects`（`web_fetch_orchestrator.py:692-754`）：每个 Location 先 `_resolve_redirect_target` 再 `_authorize_http_target(egress_policy, url=next_url, reason="http_redirect")` 创建新 target。
- ✓ 测试 `test_fetch_redirect_to_private_url_fails_closed`：302 → 127.0.0.1 被 `_FetchUrlSafetyError` 拒绝，当前 response `close_count == 1`。

### Response close exactly once

- ✓ `AuthorizedResponseLease.close()`（`web_http_session.py:349-368`）：`_closed` flag 保证幂等；response.close() + session.close() 异常被吞掉。
- ✓ `_request_with_safe_redirects`：`transferred` flag + `finally` 块保证未 transfer 的 response 在 redirect/reject/cancel 路径关闭。
- ✓ 测试矩阵：transfer（`close_count == 0` → `lease.close()` → `close_count == 1`）、cancel after request（`close_count == 1`）、response URL reject（`close_count == 1`）、Location reject（`close_count == 1`）、too many redirects（`close_count == 1`）、HEAD probe success（`close_count == 1`）。
- ✓ `lease.close()` 两次调用：`close_count == 1`（幂等）。

### Playwright safe-profile gate

- ✓ `_playwright_sync_worker`（`web_playwright_backend.py:1138-1144`）：`not egress_policy.allows_private_network` → 返回 `browser_egress_policy_unavailable`，worker 进程不启动。
- ✓ `_fetch_and_convert_with_playwright`（`web_playwright_backend.py:1314-1320`）：同上，外层也 typed fail closed。
- ✓ 测试 `test_playwright_public_direct_reports_typed_egress_policy_unavailable`：`_public_test_policy()` → `browser_egress_policy_unavailable`，`worker_calls == []`。
- ✓ `_route_handler_abort_resources`（`web_playwright_backend.py:928-934`）：`not egress_policy.is_url_allowed(route.request.url)` → `route.abort()`。
- ✓ local/dev profile（`allows_private_network=True`）：browser 可启动，但仅用于调用方已授权的 local fixture 场景。

### Diagnostic egress wiring

- ✓ `diagnose_web_access.py`：删除 `_is_private_or_local_host`、`_validate_url_safety`。
- ✓ `_build_requests_profile`：复用 `_request_with_safe_redirects` + shared `egress_policy`；不再用 `allow_redirects=True`。
- ✓ `_build_playwright_profile`：复用 `egress_policy.authorize_http_target`；public profile → `browser_egress_policy_unavailable`。
- ✓ `_route_diagnostic_browser_request`：用 `egress_policy.is_url_allowed` 裁决 subrequest。
- ✓ 测试 `test_diagnostic_requests_egress_rejection_uses_shared_policy`：私网 → `blocked_by_web_egress_policy`。
- ✓ 测试 `test_diagnostic_playwright_public_egress_is_typed_unavailable`：公网 → `browser_egress_policy_unavailable`。

### 无第二套 URL safety predicate

- ✓ `_is_safe_public_url`、`_looks_like_public_hostname`、`_is_fake_ip`、`_resolve_hostname_ips`、`_is_public_ip` 全部从 `web_tools.py` 删除。
- ✓ `_is_private_or_local_host`、`_validate_url_safety` 从 `diagnose_web_access.py` 删除。
- ✓ `_build_fetch_url_safety_predicate` 替换为 `_is_search_result_url_allowed`（投影到 `WebEgressPolicy.is_url_allowed`）。
- ✓ `grep -rn "_is_safe_public_url|_looks_like_public_hostname|_is_fake_ip" dayu/tools/web/ utils/diagnose_web_access.py` → CLEAN。

### 无 fake-IP compatibility

- ✓ `_is_public_address`（`web_egress_policy.py:128-151`）：198.18.0.0/15 → `_BENCHMARK_NETWORK` → `return False`。无 `_looks_like_public_hostname` 放行逻辑。

### 无 hasattr/getattr 逃逸

- ✓ `web_egress_policy.py`、`web_http_session.py`：零 `getattr`/`hasattr`。
- ✓ `web_fetch_orchestrator.py`、`web_tools.py`：`getattr` 全部为 pre-existing（异常链遍历、response 属性读取），无新增。

### 无 lambda/Any/object/无类型签名

- ✓ `web_egress_policy.py`：lambda 仅用于排序 key（`sorted(..., key=lambda ...)`）。
- ✓ `web_http_session.py`：所有函数签名有完整类型注解。
- ✓ 无 `Any`、无 `object` 参数、无无类型返回值。

### 无 downstream fallback

- ✓ `web_search_providers.py` 仍有 3 个固定 endpoint 的 `requests.get/post` — 已记录为 S2 scope，非 S1 URL safety predicate。
- ✓ `_FetchContentResult` 删除 `response` 字段；challenge detector 改为消费 `response_headers` + `http_status`。

### README trigger

- ✓ S1 不修改 `dayu/config/`、`tests/README.md`、根 `README.md` 或 `dayu/README.md`。plan §10 明确 S1-S4 aggregate accepted 后再更新。

## Architecture Boundary Verification

- ✓ `web_egress_policy.py` 只依赖标准库（`ipaddress`、`socket`、`urllib.parse`）。不 import `dayu.runtime`、Host、Engine、Fins。
- ✓ `web_http_session.py` import `web_egress_policy.AuthorizedHttpTarget`（同包依赖）。不 import Host、Engine。
- ✓ `web_fetch_orchestrator.py` import `web_egress_policy` + `web_http_session`（同包依赖）。
- ✓ `diagnose_web_access.py` import `web_egress_policy` + `web_fetch_orchestrator`（utils → tools 方向，符合架构）。
- ✓ 无反向依赖（tools → runtime 除外，runtime 是层中立基础包）。

## Pyright / Tests

- Controller validation 确认 pyright 0 errors（含 `normalized_url` possibly-unbound 修复）。
- 87 passed, 1 skipped（全量 Web + diagnostic 测试）。
- 38 passed（S1 指定验证）。

## Residual Risks

| Risk | Status |
|---|---|
| urllib3 扩展点版本飘移 | 已锁定 2.33.1/2.6.3，测试覆盖 |
| 公网 Playwright direct 不可用 | 明确产品降级，typed outcome |
| S2 search provider 固定 endpoint | S2 scope，非 S1 安全漏洞 |
| `web_search_providers.py` 3 个 raw requests 调用 | S2 scope，当前 `stream=False` 不泄漏 connection |

## Code Review Conclusion

**pass**

S1 实现正确闭合了 plan §6.1 定义的 Web egress 与 response ownership contract：

1. Target-bound urllib3 transport 在发送 HTTP request bytes 前只连接 approved numeric address，Host/SNI/cert hostname 保持原 host。
2. Retry 复用同一 immutable approved set；redirect 重新 authorize。
3. 所有非 transfer response 路径 close exactly once；异常 close 不掩盖原异常。
4. Diagnostic raw requests 完全复用 shared policy/lease。
5. Public Playwright direct fail closed；local/dev profile 没有被外推为公网安全证明。
6. 无第二套 URL safety predicate、fake-IP compatibility、downstream fallback、hasattr/getattr 逃逸。
7. 无新增 lambda/Any/object/无类型签名。
8. 架构边界正确，无反向依赖。

**Verdict**: pass | Findings: 1 (low, cosmetic) | Blocking: 0 | Residual risks: 4 (all tracked)
