# WU-SEMANTIC-OWNERSHIP-01 Round3 R3-E Slice S1 Code Review — AgentDS

## Review metadata

- **Reviewer**: AgentDS
- **Review type**: S1 implementation code review（不修改代码，不 stage/commit/push）
- **Plan (S1 only)**: `docs/host/wu-semantic-ownership-01-round3-r3-e-web-doc-egress-resource-plan.md` §6.1, §7 Slice 1
- **Implementation artifact**: `docs/reviews/wu-semantic-ownership-01-round3-r3-e-s1-implementation-codex.md`
- **Controller validation**: `docs/reviews/wu-semantic-ownership-01-round3-r3-e-s1-controller-validation.md`
- **Plan re-review controller adjudication**: `docs/reviews/wu-semantic-ownership-01-round3-r3-e-plan-rereview-controller-adjudication.md`
- **Changed files (7 tracked + 1 new)**:
  - `dayu/tools/web/web_egress_policy.py`（新增）
  - `dayu/tools/web/web_http_session.py`
  - `dayu/tools/web/web_fetch_orchestrator.py`
  - `dayu/tools/web/web_playwright_backend.py`
  - `dayu/tools/web/web_tools.py`
  - `utils/diagnose_web_access.py`
  - `tests/tools/web/test_web_tools_provider.py`
  - `tests/tools/web/test_diagnose_web_access.py`
- **Timestamp**: 20260713-131025

## Review scope

只 review S1 Web egress 与 response ownership。不审查 S2 resource budget/challenge/DuckDuckGo、S3 diagnostic schema/storage-state/smoke oracle、S4 Documents bounded source。重点维度：correctness、semantic ownership、resource lifetime、SSRF peer-proof、redirect/cancel response leak、Playwright safe-profile、diagnostic egress wiring、tests gaps、pyright/docstring/type issues。

## Positive observations

在进入 findings 之前，确认以下正确实现：

1. **`WebEgressPolicy` 单一语义 owner（`web_egress_policy.py:252-418`）** — URL 语法、userinfo/port 拒绝、DNS 解析、私网/链路本地/多播/保留地址拒绝、`198.18.0.0/15` 拒绝、IPv4-mapped IPv6 拒绝、混合公网/私网 fail closed 均由该模块统一裁决。无第二套 URL safety predicate。

2. **Target-bound transport（`web_http_session.py:47-511`）** — `_PinnedHTTPConnection`/`_PinnedHTTPSConnection` 只 override `_new_conn()`，按确定顺序连接 approved numeric addresses，`getpeername()` 在返回 socket 前验证 peer（含 IPv4-mapped IPv6 规范化）。pool `host` 保留原 IDNA hostname（line 309），保证 HTTP Host / TLS SNI / certificate hostname 均为原 hostname。peer mismatch 立即关闭 socket 并抛出 `NewConnectionError`（line 158-161），先于 TLS handshake / HTTP request bytes。

3. **Retry 安全（`web_http_session.py:123-168` + test lines 934-988）** — `_connect_to_approved_addresses` 对所有地址的连接重试只使用同一 immutable `approved_addresses` tuple。`test_egress_pinned_retry_uses_same_approved_addresses` 和 `test_egress_pinned_retry_exhaustion_has_no_fallback_dns` 验证了 retry 不重新 DNS、不 fallback hostname 解析。

4. **Redirect 重新授权（`web_fetch_orchestrator.py:702-736`）** — 每个 Location 通过 `_authorize_http_target(egress_policy, url=next_url, reason="http_redirect")` 创建新的 `AuthorizedHttpTarget`，不沿用旧 hop 的授权。

5. **Response lease exactly-once close（`web_fetch_orchestrator.py:717-730`）** — `transferred` flag 保证非 transfer 路径由 callee `finally` 关闭 lease，transfer 后由 caller 关闭。5 个 close matrix tests（transfer、cancel after request、response reject、location reject、too many redirects、HEAD probe）全部覆盖且断言 `close_count == 1`。

6. **Playwright safe-profile gate（`web_playwright_backend.py:1138-1143` + `web_tools.py:913-923`）** — 公网 Playwright direct 在 worker 入口 `allows_private_network=False` 时返回 `browser_egress_policy_unavailable`，不启动浏览器。`test_playwright_public_direct_reports_typed_egress_policy_unavailable` 验证 typed unavailable 且 worker 零调用。

7. **Diagnostic egress 复用（`utils/diagnose_web_access.py:1319-1356`）** — `_build_requests_profile` 改用 `_web_fetch_orchestrator._request_with_safe_redirects` + `AuthorizedResponseLease`，不复用 `allow_redirects=True`；`_build_playwright_profile` 使用 `egress_policy.authorize_http_target()` 和 `egress_policy.is_url_allowed()` 做 subrequest 路由。

8. **旧代码完全删除** — `_close_response_safely`、`_raise_if_url_blocked`、`_is_safe_public_url`、`_build_fetch_url_safety_predicate`、`_looks_like_public_hostname`、`_is_private_or_local_host`、`_validate_url_safety`、`_PRIVATE_HOST_PATTERNS`、`_FAKE_IP_NETWORKS`、`_is_public_ip`、`_is_fake_ip`、`_resolve_hostname_ips` 全部删除。`_FetchContentResult` 不再携带 `response: requests.Response`。无 `hasattr`/`getattr` 使用。无 `NotRequired` 残余。

9. **Pyright**: 0 errors, 0 warnings, 0 informations。

10. **Tests**: 87 passed, 1 skipped（全量）；38 passed (S1 filter)；5 passed (diagnostic S1 filter)。

## Findings

### F-01-未修复-低-`_build_requests_profile` 异常路径 `session.close()` 不可达

- **位置**: `utils/diagnose_web_access.py:1344-1356`
- **问题类型**: 资源生命周期 / 连接泄漏
- **当前写法**:
  ```python
  except (requests.RequestException, RuntimeError) as exc:
      profile["status"] = "request_exception"
      profile["error"] = str(exc)
      profile["result"] = {
          "ok": False,
          "status": "request_exception",
          "error_type": type(exc).__name__,
          "error_message": str(exc),
          "elapsed_seconds": _round_elapsed(started_at),
      }
      return profile           # line 1354 — 在此返回
      session.close()          # line 1355 — 不可达
      return profile           # line 1356 — 不可达
  ```
- **反例/失败场景**: `_request_with_safe_redirects` 抛出 `requests.RequestException`（如 `requests.Timeout`）时，`profile` 被正确构造并返回，但 `session`（line 1303: `session = requests.Session()`）未关闭。`requests.Session` 内部持有 urllib3 `ConnectionPool`，不关闭会导致 socket 和连接池资源延迟释放（依赖 GC `__del__`，且会触发 `ResourceWarning`）。
- **为什么有问题**: 该 `session` 是局部创建的（line 1303），不是共享的 `_get_web_session()`。正常完成路径在 line 1387 `finally: session.close()` 确保了关闭；`_FetchUrlSafetyError` 路径在 line 1342 `session.close()` 确保了关闭。但 `(requests.RequestException, RuntimeError)` 路径的 `session.close()` 被放在了 `return` 之后，导致不可达。这是明显的 typo-level bug——两行 `return profile` 中间的 `session.close()` 永远不执行。
- **直接证据**:
  - Line 1303: `session = requests.Session()` — 局部 session
  - Line 1342: `session.close()` — `_FetchUrlSafetyError` 路径正确关闭
  - Line 1354: `return profile` — 此路径未关闭 session
  - Line 1355: `session.close()` — 不可达（在 return 之后）
  - Line 1387: `finally: session.close()` — 成功路径正确关闭（但异常路径通过 return 离开，不经过此 finally）
- **影响**: 诊断脚本异常路径下 `requests.Session` 连接池泄漏。严重程度低因为：诊断脚本是 CLI 工具（用完即退出），且当前 producer 已在正确路径关闭。但在频繁诊断场景下可能累积连接。
- **建议改法和验证点**:
  ```python
  except (requests.RequestException, RuntimeError) as exc:
      profile["status"] = "request_exception"
      ...
      session.close()          # 移至 return 之前
      return profile
  ```
  删除 line 1355-1356 的不可达代码。验证：`test_diagnose_web_access.py` 中请求异常路径确认 session 已关闭（可通过 spy `session.close` 验证）。
- **修复风险**: 低（单行移动，无逻辑变更）
- **严重程度**: 低

## 特别核对项逐项报告

### target-bound urllib3 transport peer proof

**✓ 通过。** `_connect_to_approved_addresses` (web_http_session.py:123-168) 使用 `urllib3_connection.create_connection((address, port), ...)` 连接 approved numeric address，`getpeername()` 验证实际 peer，IPv4-mapped IPv6 规范化处理，peer mismatch 立即关闭 socket。`_new_conn()` 在 `_PinnedHTTPConnection`/`_PinnedHTTPSConnection` 中 override，urllib3 只在 `_new_conn()` 成功后才进入 TLS handshake / HTTP request。pool `host` 保留原 IDNA hostname（`_TargetBoundHTTPAdapter.get_connection_with_tls_context` line 309 检查 `pool.host != self._target.hostname`），保证 HTTP Host、TLS SNI 和 certificate hostname 均为原 hostname。

HTTPS integration test (`test_egress_target_bound_https_preserves_sni_certificate_and_host`, line 846) 使用自签证书的 `pinned.test` 域，通过 `set_servername_callback` 记录实际 SNI hostname，断言 TCP destination 是 `127.0.0.1` 且 Host header 包含 `pinned.test`。

### retry 复用同一 immutable approved set；redirect 重新 authorize

**✓ 通过。** Retry: `_connect_to_approved_addresses` 对所有地址尝试使用同一 `approved_addresses` tuple。测试 `test_egress_pinned_retry_uses_same_approved_addresses` (line 934) 验证首次 connect 失败后 retry 地址相同。`test_egress_pinned_retry_exhaustion_has_no_fallback_dns` (line 991) 验证所有 approved address 均失败后无 DNS fallback。

Redirect: `_request_with_safe_redirects` (line 702-736) 对每个 Location 调用 `_authorize_http_target(egress_policy, url=next_url, reason="http_redirect")` 创建新的 `AuthorizedHttpTarget`，不沿用旧 hop 的授权。`test_fetch_redirect_to_private_url_fails_closed` (line 2096) 验证 redirect 到私网 URL 被拒绝且 response close_count == 1。

### 所有非 transfer response paths close exactly once；异常 close 不掩盖原异常

**✓ 通过。** `AuthorizedResponseLease.close()` (web_http_session.py:384-407) 是幂等的（`_closed` flag），异常被 `try/except: pass` 吞掉不覆盖原业务异常。`_request_with_safe_redirects` 的 `transferred` flag + `finally` 保证非 transfer 路径全部关闭。

5 个 close matrix tests 覆盖：transfer（close_count 0 before transfer, 1 after）、cancel after request、response URL reject、location reject、too many redirects、HEAD probe success。全部断言 `close_count == 1`。

### diagnose raw requests 完全复用 shared policy/lease

**✓ 通过。** `_build_requests_profile` 改用 `_web_fetch_orchestrator._request_with_safe_redirects` + `AuthorizedResponseLease`，不复用 `allow_redirects=True`。`_build_playwright_profile` 使用 `egress_policy.authorize_http_target()` 做输入校验、`egress_policy.is_url_allowed()` 做 subrequest 路由。旧的自建 `_validate_url_safety`/`_is_private_or_local_host` 已删除。

**注**：F-01（不可达 `session.close()`）位于 diagnostic raw requests 路径的异常 handler，属于此核对项的范围。

### public Playwright direct fail closed；local/dev profile 不外推为公网安全证明

**✓ 通过。** `_playwright_sync_worker` (web_playwright_backend.py:1138-1143) 在 `allows_private_network=False` 时立即返回 `browser_egress_policy_unavailable`，不启动浏览器。`allows_private_network=True` 时（显式 local/dev profile），`_route_handler_abort_resources` 仍使用 `egress_policy.is_url_allowed()` 裁决每个 subrequest。`test_playwright_public_direct_reports_typed_egress_policy_unavailable` (line 2511) 验证 typed unavailable + worker 零调用。

`_try_playwright_fallback` (web_tools.py:913-923) 对 `reason == "browser_egress_policy_unavailable"` 投影为 `permission_denied` + typed `browser_egress_policy_unavailable` error_code，不伪装成功或静默跳过后端。

### 无第二套 URL safety predicate、fake-IP compatibility、downstream fallback、hasattr/getattr 逃逸

**✓ 通过。** 全量 audit：
- `_is_safe_public_url`、`_build_fetch_url_safety_predicate`、`_looks_like_public_hostname`、`_is_private_or_local_host`、`_validate_url_safety`、`_raise_if_url_blocked`、`_close_response_safely` — 全部删除，零命中。
- `_is_public_ip`、`_is_fake_ip`、`_resolve_hostname_ips`、`_PRIVATE_HOST_PATTERNS`、`_FAKE_IP_NETWORKS`、`_ALLOWED_SCHEMES` — 全部删除（web_tools.py diff tail shows removal）。
- `hasattr`/`getattr` — 修改文件中零命中（`_close_response_safely` 删除前包含 `getattr(response, "close", None)` — 该函数已删除）。
- fake-IP `198.18.0.0/15` — 仅在 `WebEgressPolicy` 中以 `_BENCHMARK_NETWORK` 拒绝（`_is_public_address` line 142-143），不再有兼容放行分支。

### 无新增 lambda/Any/object/无类型签名

**✓ 通过。** 新增代码全面使用 typed dataclass (`AuthorizedHttpTarget`)、typed class (`_PinnedHTTPConnection`、`_PinnedHTTPSConnection`、`AuthorizedResponseLease`)、typed function signatures。测试中的 lambda 均为测试替身（resolver、create_connection fake），符合项目惯例。

### README 触发遗漏

**✓ 未触发。** S1 不修改 provider config、不改变 `UI → Service → Host → Engine` 分层、不改变 CLI 入口或用户工作流。Plan §10 明确 S1-S4 全部 accepted 后再更新 `tests/README.md`。无遗漏。

## Cross-slice boundary check

S1 实现严格遵守 plan S1 scope boundary：

- **S2 边界**: `_send_authorized_request` 只在 S1 中定义并被 S1 consumer 使用。`web_search_providers.py` 中的固定 provider endpoint `requests.get/post` 未修改（留待 S2 search resource/parser owner 处理）。Implementation artifact §Propagation audit 已记录此 deferred 状态。
- **S3 边界**: `_build_requests_profile` 仍包含 `text_prefix`、`challenge_detected` 等字段，未迁移到 diagnostic v2 schema（属 S3 scope）。S1 只完成 egress 接线，不做 projection 变更。
- **S4 边界**: 无 Documents 文件修改。无 `dayu.documents` 或 `dayu.fins` 变更。

## Test coverage assessment (S1 only)

| Test | Coverage | Evidence |
|---|---|---|
| `test_egress_policy_rejects_unsafe_target_matrix` | 7-param matrix: userinfo, custom port, loopback, metadata, benchmark, link-local, IPv4-mapped | line 782 |
| `test_egress_policy_rejects_mixed_public_private_dns_answer` | 混合 A/AAAA fail closed | line 789 |
| `test_egress_transport_dependency_versions_are_locked` | requests/urllib3 version assertion | line 800 |
| `test_egress_target_bound_http_preserves_host_and_numeric_destination` | Real HTTP loopback + Host header verification | line 807 |
| `test_egress_target_bound_https_preserves_sni_certificate_and_host` | Real HTTPS + SNI callback + TLS retry + Host verification | line 846 |
| `test_egress_pinned_retry_uses_same_approved_addresses` | First connect RST → retry same IP | line 934 |
| `test_egress_pinned_retry_exhaustion_has_no_fallback_dns` | All addresses fail, no DNS fallback | line 991 |
| `test_egress_peer_mismatch_closes_socket_before_http_bytes` | Peer mismatch → socket closed → no HTTP bytes | line 1043 |
| `test_response_lease_transfers_final_response_and_closes_exactly_once` | Transfer → close_count 0→1, double-close safe | line 2129 |
| `test_response_lease_closes_when_cancelled_after_request` | Cancel after request → close_count 1 | line 2161 |
| `test_response_lease_closes_on_response_or_location_reject` | 2-param: response URL reject + missing Location | line 2221 |
| `test_response_lease_closes_on_too_many_redirects` | Redirect limit → close_count 1 | line 2255 |
| `test_response_lease_closes_head_probe_success` | HEAD success → close_count 1 | line 2284 |
| `test_playwright_public_direct_reports_typed_egress_policy_unavailable` | Public direct → typed unavailable, worker not called | line 2511 |
| `test_fetch_redirect_to_private_url_fails_closed` | Redirect to private → egress reject + close_count 1 | line 2096 |
| `test_fetch_meta_refresh_to_private_url_fails_closed` | Meta refresh to private → egress reject | line 2311 |

覆盖：egress policy matrix、HTTP/HTTPS loopback integration、retry safety、peer mismatch、response close matrix（6 scenarios）、Playwright safe-profile gate、diagnostic egress wiring、redirect/meta-refresh egress reject。**无关键测试缺口。**

计划中的 `test_egress_pinned_retry_uses_same_approved_addresses` 包含所有地址失败子测试（retry exhaustion test line 991）；retry SNI/cert host 验证包含在 HTTPS integration test line 846 的 `retrying_tls_create_connection` 中。

## Residual risks

| Risk | Owner | Status |
|---|---|---|
| urllib3 extension point version drift | Web transport owner | S1 locks `requests==2.33.1` / `urllib3==2.6.3`; `test_egress_transport_dependency_versions_are_locked` guards |
| Playwright public direct unavailable | Web egress policy owner | Documented product降级, deferred to deployment/browser proxy WU |
| Diagnostic `_build_requests_profile` exception-path session leak | F-01 in this review | Fix: move `session.close()` before `return profile` |
| `_FetchContentResult` no longer carries live response — downstream challenge detection | S2 challenge detection owner | S1 correctly passes `response_headers` + `http_status` to `_detect_bot_challenge`; S2 will refine |
| S2 search provider `requests.get/post` calls not using pinned transport | S2 search resource owner | Documented in implementation artifact §Propagation audit; S2 must audit |

## Code review conclusion

**Verdict: pass-with-findings**

理由：
- S1 正确实现了 plan §6.1 和 §7 Slice 1 的全部 contract：单一 egress policy owner、target-bound transport with peer proof、retry/redirect 安全语义、response lease exactly-once close、Playwright safe-profile gate、diagnostic egress 复用。
- 旧的双重 URL safety predicate、fake-IP compatibility、`hasattr`/`getattr` 逃逸全部删除。
- 15 个 S1-specific tests 覆盖 egress policy matrix、HTTP/HTTPS loopback integration、retry safety、peer mismatch、response close matrix、Playwright safe-profile、diagnostic egress wiring。
- pyright 0 errors。无新增 `Any`/`object`/无类型签名。
- 1 个 low-severity finding：`_build_requests_profile` 异常路径 `session.close()` 不可达（line 1355），导致局部 `requests.Session` 在 `RequestException`/`RuntimeError` 路径下未关闭。

**不阻塞 S1 acceptance**：F-01 是 typo-level fix（移动一行代码），修复风险低，可在进入 S2 前修复或在 S1 acceptance 时一并购入。S1 核心安全行为（peer proof、retry safety、redirect re-authorization、response close ownership、Playwright fail-closed）均正确且测试覆盖。

## Completion report

- **Verdict**: pass-with-findings
- **Artifact path**: `docs/reviews/wu-semantic-ownership-01-round3-r3-e-s1-code-review-ds.md`
- **Findings**: 1（low severity）
- **Blocking questions**: 0
- **S1 scope boundary**: 严格遵守
- **Cross-slice leakage**: 无
- **Old code removal**: 12 个已删除函数/常量，零残余
- **Tests**: 87 passed, 1 skipped
- **Pyright**: 0 errors, 0 warnings, 0 informations
