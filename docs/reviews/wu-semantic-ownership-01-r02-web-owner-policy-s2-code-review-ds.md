# WU-SEMANTIC-OWNERSHIP-01 / R02-S2 AgentDS 独立完整 Code Review

## Scope

- **Mode**: current changes (deepreview skill, Adversarial DS route)
- **Umbrella**: 既有 `WU-SEMANTIC-OWNERSHIP-01` overdesign remediation continuation
- **Internal slice**: `R02-S2` HTTP / proxy / peer proof / browser owner execution
- **Review base**: accepted S1 commit `c7b01d82`
- **Target**: 当前完整 worktree（未提交 R02-S2 implementation diff）
- **Output file**: `docs/reviews/wu-semantic-ownership-01-r02-web-owner-policy-s2-code-review-ds.md`
- **Review date**: 2026-07-15

### Included scope

完整读取了全部 8 份指定 artifact，并独立走读了 `c7b01d82..worktree` 的以下实际 changed files：

- `dayu/tools/web/web_http_session.py` — attempt-local transport 选择、proxy/proof 分支、sanitized warning
- `dayu/tools/web/web_fetch_orchestrator.py` — 每跳 mandatory transport 传播、redirect 重检
- `dayu/tools/web/web_search_providers.py` — 固定 provider endpoint 迁入 plain sender、egress/proof 保留
- `dayu/tools/web/web_playwright_backend.py` — browser/private 解耦、proof gate、proxy 环境清理
- `dayu/tools/web/web_tools.py` — typed snapshot 唯一投影、browser capability、challenge facts、LLM-facing 错误文本
- `utils/diagnose_web_access.py` — raw requests direct caller 的 typed transport 传播
- `tests/tools/web/test_web_tools_provider.py` — 大幅 proxy/proof/browser/challenge/retained-security owner tests
- `tests/tools/web/test_diagnose_web_access.py` — exact fake + direct owner assertion
- `dayu/config/README.md`、`tests/README.md` — S2 diff 确认

### Excluded scope

- `dayu/tools/web/web_challenge_detection.py` — 零 diff，已确认
- `utils/smoke_web_ci.py`、`utils/diag_web_batch.sh`、根 `README.md` — 零 diff，已确认
- `web_egress_policy.py`、`web_recovery.py` — 零 diff，已确认
- 未修改的 `dayu/tools/web/web_diagnostics.py` — schema/revision 已确认保留
- R02-S1 baseline 代码（`web_resource_budget.py`、`provider.py`、`dayu/config/tool_discovery.json`）— 只读验证 S1 contract，不做二次 review
- Issue 178、R03、proxy credential schema、统一 authorization framework — 已确认零泄漏

### 与 Controller validation 的关系

Controller validation artifact（`...-s2-controller-validation.md`）已独立确认 tests、coverage、pyright、smoke 全部通过。本 review 不重复这些验证，而是按 deepreview 要求做 adversarial failure pass、semantic ownership drift pass、LLM-facing 文本审查与 owner contract boundary 审查。

---

## Findings

### R02-S2-DS-F01 — 低 — `_fetch_web_page_business` ProxyPeerProofIncompatibleError 处理后缺少显式控制流终止

- **入口/函数**: `dayu/tools/web/web_tools.py::_fetch_web_page_business`
- **文件(行号)**: `dayu/tools/web/web_tools.py:2139-2150`
- **输入场景**: `ProxyPeerProofIncompatibleError` 被抛出（proof on + active proxy），在 `except requests.RequestException` 分支中被捕获。
- **实际分支**: `isinstance(exc, ProxyPeerProofIncompatibleError)` 为 True，进入 line 2142-2150 调用 `_raise_fetch_failure(...)`。
- **预期行为**: `_raise_fetch_failure` 始终 raise `ToolBusinessError`（line 1290），执行流在此终止。其后 line 2151-2238 的任何代码（challenge detection、browser fallback、`_raise_fetch_failure` second call）对 `ProxyPeerProofIncompatibleError` 路径均不可达。
- **实际行为**: 代码行为正确——`_raise_fetch_failure` 始终抛出，不会 fall through。但调用点（line 2142-2150）之后没有 `return`、没有 `raise` 守卫、也没有 `else:` 分支将后续代码明确标记为"仅 non-ProxyPeerProofIncompatibleError 路径"。读代码时需追踪 `_raise_fetch_failure` → `ToolBusinessError` 的完整调用链才能确认 line 2151-2238 的 dead-code 属性。
- **直接证据**:
  - `_raise_fetch_failure` line 1277-1298：始终以 `raise ToolBusinessError(...)` 终止，docstring 写"Returns: 无（始终抛出异常）"。
  - line 2142-2150：`_raise_fetch_failure(...)` 调用后，line 2151 `challenge_hint = ""` 及后续行被解释器视为可达（无显式控制流终止）。
  - line 2182 `_detect_bot_challenge(response=response, ...)`：`response` 在 line 2140 赋值为 `exc.response`，对于 `ProxyPeerProofIncompatibleError` 该值为 `None`（该异常未关联 HTTP response），如该路径可达则会产生 `None` response 传入 challenge detector。
  - 同一模式在 `except requests.TooManyRedirects` 和 `except requests.Timeout` 分支中不存在——它们各自在 `_raise_fetch_failure` 之前已有显式 `browser_result = _try_playwright_fallback(...)` 路径和 `return` 守卫。
- **影响**: 纯维护性风险——当前行为正确，但如果 `_raise_fetch_failure` 未来被修改为条件性抛出，或有人在该 except 块中增加 `ProxyPeerProofIncompatibleError` 特有处理而未加 `return`，则会静默 fall through 到不相关的 challenge/browser/http_status 逻辑。
- **建议改法和验证点**: 在 line 2142-2150 的 `_raise_fetch_failure(...)` 调用后增加 `# ProxyPeerProofIncompatibleError 路径在此终止，后续代码仅处理其他 RequestException` 注释；或将该 check 提前为独立的 `except ProxyPeerProofIncompatibleError` 子句（置于 `except requests.RequestException` 之前）。验证：确保现有 proxy+proof incompatibility 测试仍通过，且 line 2151-2238 不被该路径执行。
- **修复风险（低）**: 纯结构调整，不改变行为语义。
- **严重程度（低）**: 行为正确，仅结构性可读性缺陷。

### R02-S2-DS-F02 — 低 — `_fetch_web_page_business` challenge 成功路径存在 `FAIL_BLOCKED` 分支重复

- **入口/函数**: `dayu/tools/web/web_tools.py::_fetch_web_page_business`
- **文件(行号)**: `dayu/tools/web/web_tools.py:2209-2218` 与 `dayu/tools/web/web_tools.py:2366-2375`
- **输入场景**: challenge detection 判定 `FAIL_BLOCKED`，且 browser fallback 不可用（`browser_fallback_available == False` 或 fallback 已尝试但失败）。
- **实际分支**: 两处 `if challenge_action is ChallengeFallbackAction.FAIL_BLOCKED:` 分支产生完全相同的 `_raise_fetch_failure` 调用——相同 error_code (`"blocked"`)、相同 message（仅"or access gate" vs 无此短语的微小差异）、相同 hint、相同 next_action。
- **预期行为**: challenge `FAIL_BLOCKED` 应统一映射到一次 `_raise_fetch_failure`。
- **实际行为**: 两处独立调用，message 字符串略有不同（line 2203 `"...or access gate; fetched content is unusable."` vs line 2369 `"...fetched content is unusable."`），但功能等价。这不是行为 bug——每处都在其独有的 control flow 上下文中（一处是 `requests.RequestException` except 块内，另一处是 fetch 成功后的 post-hoc challenge check），各自都有合理的到达条件。
- **直接证据**:
  - line 2209-2218：在 `except requests.RequestException` 块内，处理 HTTP 响应层面检测到的 challenge `FAIL_BLOCKED`。
  - line 2366-2375：在 fetch 成功后，处理内容层面检测到的 challenge `FAIL_BLOCKED`（`response=None` 路径）。
  - 两处 message 字符串差异仅为 `"or access gate; "` 短语的有无。
- **影响**: 低——LLM-facing message 的微小差异可能被 LLM 误读为不同错误类别；operator 排查时可能需查两处才能确认"blocked"的来源。
- **建议改法和验证点**: 抽取一个 `_raise_challenge_blocked(url, http_status, diagnostic_error_chars)` helper，统一两处的 error_code/message/hint/next_action。验证：现有 challenge confirmed 测试仍通过。
- **修复风险（低）**: 抽取 helper 不改变语义；需确保 LLM-facing message 统一后不引入 regression。
- **严重程度（低）**: 功能正确，仅字符串重复和微小的 message 不一致。

---

## Observations（非 finding，不需要 fix）

### R02-S2-DS-O01 — diagnostic utility egress_policy 仍将 custom_port 耦合到 private_network_url

- **位置**: `utils/diagnose_web_access.py:2719-2722`
- **证据**: `WebEgressPolicy(allow_private_network=options.allow_private_network_url, allow_custom_port=options.allow_private_network_url)` — `allow_custom_port` 与 `allow_private_network` 使用同一个 CLI option 值。
- **判定**: 这是 plan §10.3 明确分配给 S3 的已知状态——S3 会删除 `--allow-private-network-url` CLI option 并使 diagnostic utility 消费 typed Web config。当前行为不改变 S2 产品语义（产品路径走 `config.allow_private_network_url` 和 `config.allow_custom_port_url` 两个独立 typed 字段）。不是 S2 defect，不阻塞 S2 accepted。

### R02-S2-DS-O02 — `_send_authorized_plain_request` 在 proxy+proof 冲突时 source session 的 finally close 行为

- **位置**: `dayu/tools/web/web_http_session.py:617-635`
- **证据**: `_send_authorized_plain_request` 在 `try` 块中调用 `_send_authorized_request_attempt`，并在 `finally` 中 close source session。当 `_send_authorized_request_attempt` 抛出 `ProxyPeerProofIncompatibleError` 时，`call_session` 已在 line 746-747 被 close（在 `_send_authorized_request_attempt` 的 except 块中），而 `source_session` 由外层 `finally` 正常 close。
- **判定**: source 和 call 两个 session 各自有独立的 close 责任且都会被正确关闭。无 resource leak。记录为 observation 以供 future 审计。

### R02-S2-DS-O03 — `web_tools.py` 和 `web_playwright_backend.py` coverage 接近阈值

- **位置**: `dayu/tools/web/web_tools.py` (80.056%)、`dayu/tools/web/web_playwright_backend.py` (80.488%)
- **证据**: Controller validation 独立重跑确认两个文件 coverage 均按 JSON 精确值 ≥80%。略高于阈值，依赖当前测试矩阵的精确行覆盖。
- **判定**: 这不是 S2 defect——gate 已通过。但两者接近阈值意味着新增代码路径可能在后续 slice 中将 coverage 拉低到 80% 以下。记录为 observation 供 R02-S3 和 future reviewer 注意。

### R02-S2-DS-O04 — 三个 search provider 的 `_send_authorized_plain_request` 调用均正确保留了 `allow_redirects=False`

- **位置**: `dayu/tools/web/web_search_providers.py` 中 `_search_with_tavily`、`_search_with_serper`、`_search_with_duckduckgo`
- **证据**: 三个 provider 都从原始 `requests.get/post(..., allow_redirects=False)` 迁移到 `_send_authorized_plain_request(...)` ，后者通过 `_send_authorized_request_attempt` → `call_session.send(..., allow_redirects=False, ...)` 保留了禁止 redirect 语义。
- **判定**: 迁移正确，前端 egress check（`egress_policy.authorize_http_target`）为新增安全层。记录为 positive observation。

### R02-S2-DS-O05 — `_clear_proxy_environment` 覆盖了大小写双写 proxy 变量名

- **位置**: `dayu/tools/web/web_playwright_backend.py:227-237` 与 `_clear_proxy_environment` 函数
- **证据**: `_PROXY_ENVIRONMENT_NAMES` 包含 `HTTP_PROXY, HTTPS_PROXY, ALL_PROXY, NO_PROXY, http_proxy, https_proxy, all_proxy, no_proxy` 共 8 个变量名，覆盖了常见的大小写双写惯例。
- **判定**: 覆盖合理。Playwright/Chromium 在不同平台对大小写的敏感度不同，双写是防御性的。记录为 positive observation。

---

## 关键 adversarial review 结果

### 1. attempt-local HTTP standard/proof strategy — 一次 prepare/merge/select/send 同源验证

**PASS**。`_send_authorized_request_attempt`（line 701-738）在单次 attempt 内：
1. 只调用一次 `call_session.prepare_request(request)`（line 708）
2. 只调用一次 `call_session.merge_environment_settings(...)`（line 710-718）
3. 只调用一次 `requests.utils.select_proxy(...)`（line 722-725）
4. 把同一个 `settings` 对象原样传给 `call_session.send(..., **settings)`（line 733-738）

Test `test_http_transport_proxy_allow_prepares_once_and_reuses_merged_settings` 用 identity check（`is`）验证 merge/select/send 消费同一对象。

proxy deny 路径（line 720-721）验证 `settings["proxies"]` 为空，并在非空时抛出 `RuntimeError`（fail closed）。

proof+proxy incompatibility（line 726-727）在 `selected_proxy is not None and dns_peer_proof_enabled` 时抛出 typed `ProxyPeerProofIncompatibleError`，不静默降级。

### 2. search provider 首次 egress/DNS/custom-port/peer proof

**PASS**。`_send_authorized_plain_request`（line 583-635）对每个固定 provider endpoint：
1. 先调用 `egress_policy.authorize_http_target(url, stage="search_provider_request")`（line 617-620）
2. 使用 `_create_no_retry_session()`（无自动 retry 干扰 proof timing）
3. 通过 `_send_authorized_request_attempt` 执行同一次 prepare/merge/select/send
4. `allow_redirects=False` 保留（line 736）

Tavily、Serper、DuckDuckGo 三个 provider 均迁入此路径，API key、query、result 业务语义不变。

Test `test_duckduckgo_plain_sender_retains_egress_and_challenge_semantics` 验证固定 endpoint 的 egress check 和 challenge detection 均保留。

### 3. browser_enabled/private 权限双向解耦、proof fail-close

**PASS**。
- `_playwright_sync_worker` 中的旧 `if not egress_policy.allows_private_network: return browser_egress_policy_unavailable` 前置 return 已删除（playwright_backend diff line 162-167）。
- `_fetch_and_convert_with_playwright`（line 1622-1627）在 Playwright import 和 `process.start()` 之前检查 `transport_policy.dns_peer_proof_enabled`，返回 `browser_peer_proof_unavailable`。
- `_try_playwright_fallback`（line 977-978）先检查 `browser_enabled`，再调用 `_fetch_and_convert_with_playwright`。
- `_browser_fallback_available`（line 912-927）用于 challenge 决策：`browser_enabled and not transport_policy.dns_peer_proof_enabled`。

Test `test_playwright_public_direct_runs_without_private_permission` 验证公网 browser + private=false 可运行。Test `test_browser_disabled_with_private_permission_does_not_start_backend` 验证 private=true 不反向启用 browser。Test `test_browser_peer_proof_fails_before_process_with_safe_projection` 验证 proof=true 时 `_run_playwright_worker_process` 零调用、LLM-facing message 无 Playwright/socket/peer/proof 术语。

### 4. diagnostic utility 只消费 provider parser 同一 raw mapping 的 typed snapshot

**PASS**。
- `_build_single_diagnostic_payload`（line 2717-2718）调用 `_provider_config(options)` 一次生成 raw mapping，然后调用 `_parse_config(provider_config).transport_policy` 取得 typed snapshot。
- 同一 `provider_config` 传给 `_build_tool_fetch_profile`（line 2751-2755）用于 provider discovery。
- 无第二 `WebHttpTransportPolicy(...)` constructor、无 `dns_peer_proof_enabled`/`allow_environment_proxy` raw field 解析、无 `os.environ`/`os.getenv` 读取、无 `getattr` 兼容 default。
- 仅 import `WebHttpTransportPolicy` type（用于 annotation），不 import transport 行为。

Test `test_requests_profile_forwards_provider_owned_transport_policy` 验证：
- `_provider_config` 只调用一次
- fake 收到的 `transport_policy` 等于 `provider._parse_config(raw_config).transport_policy`
- 同一 `raw_provider_config` 对象引用传给 provider discovery
- 非默认 bool 组合（`dns_peer_proof_enabled=True, allow_environment_proxy=False`）可观测

### 5. LLM-facing 错误文本、安全 redaction 与 AGENTS.md 约束

**PASS**。
- `_BROWSER_PEER_PROOF_UNAVAILABLE_MESSAGE = "当前浏览器访问无法验证目标连接。"` — 无 Playwright/socket/Host/runtime 术语。
- `_PROXY_PEER_PROOF_INCOMPATIBLE_MESSAGE = "当前连接验证策略与已启用的网络代理不兼容。"` — 无内部治理术语。
- proxy warning（line 729-731）只含稳定 reason 常量 `"environment_proxy_active_without_peer_proof"` 和 `environment_proxy_active=true`，不含 URL、proxy URI、credential、headers、cookies。
- `Header redaction` 保留：`_sanitize_response_headers` 中 Set-Cookie 只保留 cookie name，其他 header value 截断至 200 chars。
- `ProxyPeerProofIncompatibleError.__init__` 只传递稳定 reason 字符串给父类，不暴露敏感数据。
- LLM-facing message 均无内部模块名（`web_http_session`、`web_playwright_backend`）、无 Host 状态、无 Agent/Engine 治理术语。

Test `test_browser_peer_proof_fails_before_process_with_safe_projection` 明确断言 LLM-facing text 不含 `"Playwright"`、`"socket"`、`"peer"`、`"proof"`。

### 6. 大幅 tests/docstring diff 是否锁定真正 owner contract

**PASS**。
- 100 个 added/signature-touched definitions 全部完成中文 docstring audit（`Args`/`Returns`/`Raises`），2 个新增 class/TypedDict 包含 fields/attributes 与 call contract。
- Test fakes 精确匹配生产签名（keyword-only `transport_policy` 无 default、无 `**kwargs`、无 loose typing）。
- `test_requests_profile_forwards_provider_owned_transport_policy` 用 identity check 和对象等值检查验证 parser → consumer 的完整传播链。
- 既有 browser Protocol `launch(**kwargs)` 与 `new_context(**kwargs)` 精确两处保留，不属于 transport seam。
- 没有 fake/mock/fixture 固化偶然行为——每个 fake 都显式接收并验证 typed contract。

### 7. retained security 机制完整

**PASS**。以下 retained release-blocking contracts 均有 test/smoke 覆盖：
- 初始 URL / 每 redirect hop 重检：`_request_with_safe_redirects` 每跳调用 `egress_policy.authorize_http_target`
- dangerous/unspecified/multicast deny：`WebEgressPolicy` 无条件拒绝，无 diff
- mixed DNS fail closed：`WebEgressPolicy` 保留，无 diff
- proof-on numeric target/peer verify：`_TargetBoundHTTPAdapter` + `_connect_to_approved_addresses` 保留
- proof mismatch fail closed：`_connect_to_approved_addresses` peer comparison 保留
- proxy+proof typed fail：`ProxyPeerProofIncompatibleError` 在发送前抛出
- browser route/navigation egress：`_raise_if_playwright_url_blocked` 保留
- HTTP/browser/diagnostic budgets：三 child budget 各自独立校验
- challenge detection + diagnostics v2/revision2：`web_challenge_detection.py` 零 diff
- redaction：`_sanitize_response_headers` 保留
- containment/symlink：pre-existing，无 diff

### 8. R02-S3、Issue 178、R03、proxy credential schema、统一 tool authorization framework 零泄漏

**PASS**。
- `_StorageStateLifecycle`、`_DEFAULT_DIAGNOSTIC_ERROR_CHARS=1_024`、`--max-network default=80`、storage-state CLI/TTL/owner filename/reconcile 均保持（S3-owned）。
- `utils/smoke_web_ci.py`、`utils/diag_web_batch.sh`、根 `README.md` 均零 diff。
- Issue 178 credential lifecycle、R03 accepted-result/LLM projection、proxy credential schema、统一 tool authorization framework 均未实施、未预埋。
- `web_challenge_detection.py` 零 diff。

### Topic 8/9 no-code 裁决确认

Topic 8（Engine 240 chars）和 Topic 9（unified authorization no-code）的裁决未被重开。当前实现没有引入新的 Host authorization framework、policy DSL、capability token、sandbox 或 permission schema。

---

## Open Questions

无。

所有关键路径均沿真实代码追踪并基于直接证据验证。没有需要用户裁决或 controller 介入的 ambiguous case。

---

## Residual Risk

| risk | 当前处理 | owner/destination |
|---|---|---|
| `web_tools.py` (80.056%) 和 `web_playwright_backend.py` (80.488%) coverage 接近阈值 | 当前 ≥80% gate 已通过；新增代码路径可能在后继 slice 中拉低覆盖率 | R02-S3 逐文件 coverage gate |
| diagnostic utility `egress_policy` custom_port 仍耦合 private_network_url | plan §10.3 分配给 S3 | R02-S3 |
| `ProxyPeerProofIncompatibleError` handler 后缺显式控制流终止 | R02-S2-DS-F01 记录为低严重度 maintainability finding | 本 slice 或 S3 可修复 |
| challenge `FAIL_BLOCKED` 分支在两处重复 | R02-S2-DS-F02 记录为低严重度 | 本 slice 或 S3 可抽取 helper |

无 ownerless residual、无 unclassified risk、无新的产品问题。

---

## Verdict

**PASS — READY FOR CONTROLLER ADJUDICATION**。

R02-S2 implementation 满足 final plan 的全部 owner contract 要求：
- attempt-local HTTP transport 选择（standard/pinned、proxy/proof）正确实现
- search provider 首次 egress/DNS/peer proof 保留
- browser_enabled/private 双向解耦、proof fail-close 正确
- diagnostic utility 只消费 provider parser 同一 raw mapping 的 typed snapshot
- LLM-facing 错误文本满足 AGENTS.md 约束
- retained security 机制完整
- R02-S3/Issue 178/R03/统一 authorization 零泄漏

两个低严重度 finding（R02-S2-DS-F01、R02-S2-DS-F02）均为 maintainability 性质，不阻塞 S2 accepted。五个 observation 均为已知状态或 positive confirmation，不需要 fix。

等待 Controller 裁决。
