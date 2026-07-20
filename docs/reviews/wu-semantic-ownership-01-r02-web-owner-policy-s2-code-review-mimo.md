# WU-SEMANTIC-OWNERSHIP-01 / R02-S2 Code Review — AgentMiMo

## 1. Review 身份、base 与范围

- **umbrella**：既有 `WU-SEMANTIC-OWNERSHIP-01` overdesign remediation continuation。
- **slice**：`R02-S2` HTTP/proxy/peer proof/browser owner execution。
- **review base**：accepted S1 commit `c7b01d82`。
- **review target**：当前完整 worktree（`c7b01d82`..worktree 全部 R02-S2 production/utility/tests/README diff）。
- **implementation artifact**：`docs/reviews/wu-semantic-ownership-01-r02-web-owner-policy-s2-implementation-codex.md`。
- **controller validation**：`docs/reviews/wu-semantic-ownership-01-r02-web-owner-policy-s2-controller-validation.md`。
- **verdict**：**PASS — 0 blocking finding / 1 accepted-candidate observation**。

本 review 独立读取 final plan、plan-drift 裁决链、controller validation、implementation artifact、全部 production/utility/test diff、关键 owner source code 与 README。不以 artifact 或测试通过作为 correctness 证明；所有结论基于直接代码路径证据。

## 2. Adversarial review 逐项裁决

### 2.1 attempt-local HTTP standard/proof strategy：一次 prepare/merge/select/send 是否真实同源

**结论：PASS — 真实同源。**

`_send_authorized_request_attempt`（`web_http_session.py:638`）是所有 HTTP send 的唯一核心路径：

1. 一个 `call_session` 被创建（line 676）。
2. `call_session.trust_env = transport_policy.allow_environment_proxy`（line 677）。
3. `call_session.proxies.clear()`（line 685）。
4. 根据 `transport_policy.dns_peer_proof_enabled` 选择 adapter：proof-on 使用 `_TargetBoundHTTPAdapter`（line 688），proof-off 使用标准 `HTTPAdapter`（line 690）。
5. `request = requests.Request(...)`（line 701）。
6. `prepared = call_session.prepare_request(request)`（line 708）— 只 prepare 一次。
7. `settings = call_session.merge_environment_settings(prepared.url, {}, stream, verify, cert)`（line 710-718）— 只 merge 一次。
8. `selected_proxy = requests.utils.select_proxy(prepared.url, settings["proxies"])`（line 722-724）— 只 select 一次。
9. `response = call_session.send(prepared, timeout=timeout, allow_redirects=False, **settings)`（line 733-737）— 只 send 一次，且 `allow_redirects=False`。

每个 redirect hop 由 `_request_with_safe_redirects`（`web_fetch_orchestrator.py:797`）单独调用 `_send_authorized_request`，每 hop 重新执行 egress authorization + transport decision + prepare/merge/select/send。不存在跨 hop 的 stale session/settings/adapter 复用。

### 2.2 proxy allow/deny、retry/cookie/TLS/redirect 是否正确

**结论：PASS。**

- **proxy allow**（`allow_environment_proxy=true`）：`trust_env=true`，`merge_environment_settings` 读取环境变量，`select_proxy` 得到当前 URL 的 selected proxy。warning 只记录 `_PROXY_WITHOUT_PEER_PROOF_WARNING_REASON` 稳定 reason（line 729-731），不含 URL、proxy URI、credential、headers 或 cookies。
- **proxy deny**（`allow_environment_proxy=false`）：`trust_env=false`，`proxies.clear()`，merge 后检查 `settings["proxies"]` 为空（line 720-721），`select_proxy` 返回 `None`。
- **proof + active proxy**：`selected_proxy is not None and transport_policy.dns_peer_proof_enabled` 触发 `ProxyPeerProofIncompatibleError()`（line 726-727），fail closed。
- **retry**：per-call session 从 source session（`_create_no_retry_session`，line 621）继承 headers/cookies/verify/cert/max_redirects，但 adapter 使用独立 no-retry 配置。
- **cookie**：source session 的 cookies 通过 `call_session.cookies.update(source_session.cookies)` 继承（line 680），response cookies 通过 `source_session.cookies.update(call_session.cookies)` 回写（line 739）。
- **TLS**：verify/cert 从 source session 继承（line 682-683）。
- **redirect**：`_request_with_safe_redirects` 每 hop 调用 `egress_policy.authorize_http_target` 重新检查 scheme/host/port/DNS/address，然后重新执行 transport decision。

### 2.3 search provider 首次 egress/DNS/custom-port/peer proof、credential、redirect、resource budget、fallback/challenge 语义

**结论：PASS。**

三个固定 endpoint（`_TAVILY_ENDPOINT`、`_SERPER_ENDPOINT`、`_DUCKDUCKGO_ENDPOINT`）均通过 `_send_authorized_plain_request`（`web_http_session.py:583`）发送：

1. `egress_policy.authorize_http_target(url, stage="search_provider_request")` 执行 DNS/address/custom-port authorization（line 617-619）。
2. `_send_authorized_request_attempt` 使用同一个 transport policy 执行 proxy/proof decision。
3. `allow_redirects=False`，不跟随 redirect。
4. API key 进入 request body/params/headers，不进入 warning/diagnostic。
5. `ProxyPeerProofIncompatibleError` 在 `search_public_web` 中被即时 re-raise（line 362-363），不触发 provider fallback。
6. `HttpResourceBudget` 只传递给 response materialization，与 browser/diagnostic budget 独立。
7. `_filter_visible_results` 消费 caller 构造的 typed `WebEgressPolicy`，由其 `is_url_allowed` 决定 private/custom-port visibility。

### 2.4 browser_enabled/private 权限双向解耦、proof fail-close、proxy 环境、route/navigation egress、challenge facts

**结论：PASS。**

- **browser/private 解耦**：`_playwright_sync_worker` 中旧的 `egress_policy.allows_private_network` 前置 return 已删除（diff line 1436 删除 6 行）。`_fetch_and_convert_with_playwright` 的 guard 改为 `transport_policy.dns_peer_proof_enabled`（line 1622），不再耦合 private permission。
- **proof fail-close**：`_browser_fallback_available`（`web_tools.py:915`）返回 `browser_enabled and not transport_policy.dns_peer_proof_enabled`。proof-on 时在 `_fetch_and_convert_with_playwright`（line 1622-1627）fail closed，不启动 Playwright import/process start。LLM-facing message 为 `_BROWSER_PEER_PROOF_UNAVAILABLE_MESSAGE = "当前浏览器访问无法验证目标连接"`，不含 Playwright、socket、Host/runtime 术语。
- **proxy 环境**：`_playwright_process_entry`（line 554-555）在 `allow_environment_proxy=False` 时调用 `_clear_proxy_environment()`，删除 `_PROXY_ENVIRONMENT_NAMES` 中的全部 8 个标准 proxy 变量，再调用 `enter_new_process_session_if_supported()`。
- **route/navigation egress**：browser route/navigation 继续逐 URL 应用 `WebEgressPolicy`（`_raise_if_playwright_url_blocked`）。
- **challenge facts**：challenge detector 零 diff。challenge availability 不再硬编码 `browser_available=True`，而是消费 `_browser_fallback_available` 的实际 capability 与 proof compatibility。browser failure 不回写 HTTP/challenge 事实。

### 2.5 diagnostic utility 是否只消费 provider parser 同一 raw mapping 的 typed snapshot

**结论：PASS — 同源 single parse，无第二 default/parser/environment inference。**

`_build_single_diagnostic_payload`（`utils/diagnose_web_access.py:2714`）：

1. `provider_config = _provider_config(options)` — 生成一次 raw mapping（line 2717）。
2. `transport_policy = _parse_config(provider_config).transport_policy` — 由 provider parser owner 产生 typed snapshot（line 2718）。
3. 同一个 `provider_config` 传给 `_build_requests_profile(..., transport_policy=transport_policy)`（line 2738）和 `_build_tool_fetch_profile(..., provider_config=provider_config)`（line 2748-2752）。
4. `_build_requests_profile` 把 `transport_policy` 传给 `_request_with_safe_redirects`（line 1510）。
5. `_build_tool_fetch_profile` 把 `provider_config` 传给 `_fetch_web_page_definition(provider_config)`，后者直接用于 `discover_tools(spec)`（line 1626）。

utility 中没有：
- `WebHttpTransportPolicy(...)` constructor — 只 import type 并消费 parser 返回 snapshot。
- `dns_peer_proof_enabled` / `allow_environment_proxy` raw bool parsing。
- `getattr` / `os.environ` / `getenv` 读取或推断。
- 第二 parser / default / environment inference / compatibility default / wrapper / facade。
- `**kwargs` — `_build_requests_profile` 与 exact fake 均为 typed keyword-only，无 loose kwargs。

### 2.6 LLM-facing 错误文本、安全 redaction 与 AGENTS.md 约束

**结论：PASS。**

| 常量 | 文本 | 是否符合 AGENTS.md |
|---|---|---|
| `_PROXY_PEER_PROOF_INCOMPATIBLE_MESSAGE` | "当前连接验证策略与已启用的网络代理不兼容。" | ✅ 不含 Playwright、socket、Host/runtime 术语 |
| `_BROWSER_PEER_PROOF_UNAVAILABLE_MESSAGE` | "当前浏览器访问无法验证目标连接。" | ✅ 不含 Playwright、socket、Host/runtime 术语 |
| proxy warning | `"environment_proxy_active=true reason=%s"` + 稳定 reason | ✅ 只含非敏感 bool 与稳定 reason |
| `ProxyPeerProofIncompatibleError.reason` | `"proxy_peer_proof_incompatible"` | ✅ 稳定 typed error code |

- `_PROXY_PEER_PROOF_INCOMPATIBLE_REASON`（`web_http_session.py`）不含 URL、proxy URI、credential、headers 或 cookies。
- `_BROWSER_PEER_PROOF_UNAVAILABLE_REASON`（`web_playwright_backend.py`）不含 Playwright、socket、peer/proof 或 Host/runtime 术语。
- 搜索结果中 proxy warning 只记录 reason 字符串，不记录 proxy 值、URL/query、userinfo、headers、cookies 或 storage path。

### 2.7 大幅 tests/docstring diff 是否锁定真正 owner contract

**结论：PASS — 锁定 owner contract，未用 fake 固化偶然行为。**

- `test_requests_profile_forwards_provider_owned_transport_policy`（`test_diagnose_web_access.py:699`）使用非默认 raw config `dns_peer_proof_enabled=True / allow_environment_proxy=False`，证明 parser-owned snapshot 传播，证明同一个 raw mapping 继续交给 provider discovery。
- `_fake_requests_profile` 接收 typed `transport_policy` 参数并记录值，不提供 default。
- `_fake_fetch_profile` 接收 `provider_config` 参数并记录同一 raw mapping。
- `provider_config_calls == 1` 断言 `_provider_config` 只调用一次。
- `observed_discovery_configs[0] is raw_provider_config` 断言同一对象引用（同源 identity）。
- `test_s2_owner_signatures_and_worker_payload_are_closed` 验证 `_send_authorized_request` 的 `transport_policy` 无 default，`_send_authorized_plain_request` 存在且正确 typed。
- 100 个 added/signature-touched definitions 已逐 qualified name 审计，issues=0。

### 2.8 retained security 机制完整；R02-S3、Issue 178、R03、proxy credential schema、统一 tool authorization framework 没有偷带

**结论：PASS。**

retained security：
- 初始 URL 与 redirect 每 hop 的 scheme/host/port/DNS/address 重检。
- dangerous、unspecified、multicast、显式 private deny、显式 custom-port deny。
- mixed DNS fail closed。
- peer proof 开启时 numeric target/actual peer verification 与 mismatch fail closed。
- proxy 禁用时不读 environment；proxy+proof 不兼容时 typed fail closed。
- HTTP wire/decoded、browser warmup/DOM/text、diagnostic error/event budgets。
- challenge detection、HTTP→browser fallback 的 challenge reason、diagnostics v2/revision 2。
- `browser_enabled` 与 private permission 的双向独立性。
- header/cookie/URL/proxy credential redaction、diagnostic containment。
- 显式 storage-state path/dir read input。

未偷带：
- `utils/smoke_web_ci.py`、`utils/diag_web_batch.sh`、根 `README.md` 均 `git diff --exit-code` exit 0。
- `dayu/tools/web/web_challenge_detection.py` 零 diff。
- S3 storage lifecycle/CLI/TTL/owner filename/publish/reconcile 未前移。
- `_DEFAULT_DIAGNOSTIC_ERROR_CHARS = 1_024`、`--max-network default=80` 未删除。
- Issue #178、R03、proxy credential schema、统一 tool authorization framework 零实施/预埋。

## 3. Findings

### R02-S2-MIMO-F01 — accepted-candidate / observation — 低 — diagnostic egress policy 的 `allow_custom_port` 语义耦合

- **入口/函数**：`utils/diagnose_web_access.py:_build_single_diagnostic_payload`
- **文件(行号)**：`utils/diagnose_web_access.py:2720-2723`
- **输入场景**：任意 single diagnostic CLI 调用。
- **实际分支**：`egress_policy = WebEgressPolicy(allow_private_network=options.allow_private_network_url, allow_custom_port=options.allow_private_network_url, ...)` — `allow_custom_port` 复用 `allow_private_network_url` 值。
- **预期行为**：按 final plan §4.3，`allow_custom_port_url` 是独立 bool config field，应独立于 `allow_private_network_url`。
- **实际行为**：diagnostic utility 的 egress policy 把 custom-port decision 绑定到 private-network option，而非从 typed config 独立读取。
- **直接证据**：`utils/diagnose_web_access.py:2720-2723`。`options.allow_private_network_url` 同时赋值给 `allow_private_network` 和 `allow_custom_port`。
- **影响**：diagnostic 执行时 egress policy 的 custom-port decision 与 typed config 的独立 `allow_custom_port_url` 不完全同源。当 `allow_private_network_url=false` 时，合法非标准端口 URL 在 diagnostic 中也会被拒绝，而生产 typed config 可能允许。不阻塞当前 S2 的 mandatory transport policy 传播。
- **root cause**：pre-existing diagnostic egress policy 构造方式未随 S1 五 bool 拆分同步更新。S2 plan-drift adjudication 只精确前移了 transport policy 传播，不授权修改 egress policy 构造。
- **owner-boundary 修复要求**：S3 在 utility 消费 typed Web config 时，应从 typed `WebToolsConfig` 独立读取 `allow_custom_port_url`，或直接构造 `WebEgressPolicy` 使用 parser 产生的 typed values。
- **测试缺口**：当前 `test_single_diagnostic_private_mode_preserves_local_custom_port` 断言 custom-port 在 `allow_private_network_url=true` 时允许，但未测试 `allow_private_network_url=false` 时 custom-port 是否应独立允许。
- **severity**：低 — pre-existing 语义、S2 不阻塞、S3 scope 内。
- **修复风险**：低。

## 4. Open Questions

无。

## 5. Residual Risk

| residual | 当前处理 | owner / destination |
|---|---|---|
| diagnostic egress policy `allow_custom_port` 耦合 | S2 保持 pre-existing 行为，观察记录 | R02-S3；utility 消费 typed config 时修复 |
| storage lifecycle/CLI/TTL/owner filename/publish/reconcile | S2 不前移 | R02-S3 |
| `_DEFAULT_DIAGNOSTIC_ERROR_CHARS=1_024` / `--max-network default=80` | S2 不删除 | R02-S3；由 typed `DiagnosticResourceBudget.error_chars/events` 同源替换 |
| `web_tools.py` 覆盖率 ~80.06% | 精确 JSON 值通过 80% 门槛 | 进入 code review 时继续验证 |
| external provider DNS/credential/站点波动 | local deterministic hard gate 已通过 | external diagnostics；non-blocking |
| credential refresh/retention/concurrent publish/cleanup | R02 删除提前实现 | Issue #178 |

## 6. 结论

R02-S2 implementation 在 attempt-local HTTP transport strategy、proxy/proof/browser 解耦、search provider egress 统一、diagnostic transport policy 同源传播、LLM-facing 安全文本、retained security 机制与测试覆盖方面均通过 adversarial review。唯一 accepted-candidate observation（diagnostic egress policy 的 `allow_custom_port` 语义耦合）是 pre-existing 行为、severity 低、S3 scope 内，不阻塞 S2 accepted gate。

**verdict：PASS — 0 blocking finding / 1 accepted-candidate observation。**
