# WU-SEMANTIC-OWNERSHIP-01 / R02-S2 Final-Slice Re-Review — AgentMiMo

## 1. Review 身份、base 与范围

- **umbrella**：既有 `WU-SEMANTIC-OWNERSHIP-01` overdesign remediation continuation；不是新 WU/新 slice。
- **slice**：`R02-S2` HTTP/proxy/peer proof/browser owner execution。
- **review base**：accepted S1 commit `c7b01d82`。
- **review target**：当前完整 worktree（`c7b01d82..worktree` 全部 production/utility/tests/README diff），不是 zero-change artifact。
- **review type**：既有 R02-S2 完整 final-slice re-review；第一路独立 re-review。
- **指定输入**：
  - `AGENTS.md` 语义所有权/LLM-facing/分层/类型/测试约束
  - R02 accepted plan §9（S2 owner/security tests）、§15（artifact 命名与 gate）
  - S2 implementation artifact：`docs/reviews/wu-semantic-ownership-01-r02-web-owner-policy-s2-implementation-codex.md`
  - Controller validation：`docs/reviews/wu-semantic-ownership-01-r02-web-owner-policy-s2-controller-validation.md`
  - 初始 MiMo code review：`docs/reviews/wu-semantic-ownership-01-r02-web-owner-policy-s2-code-review-mimo.md`
  - 初始 DS code review：`docs/reviews/wu-semantic-ownership-01-r02-web-owner-policy-s2-code-review-ds.md`
  - Controller code-review adjudication：`docs/reviews/wu-semantic-ownership-01-r02-web-owner-policy-s2-code-review-controller-adjudication.md`
  - zero-change fix artifact：`docs/reviews/wu-semantic-ownership-01-r02-web-owner-policy-s2-code-review-fix-codex.md`
  - control 当前状态：`docs/host/issues-implementation-control.md`
- **verdict**：**PASS — 0 new material finding / 3 原 finding disposition 复核通过**。

本 re-review 独立读取全部指定 artifacts、`c7b01d82..worktree` 全部 12 个 tracked changed 文件的完整 diff、关键 production source code 路径、以及 Controller validation/smoke 证据。不以 artifact 文字或测试通过作为 correctness 证明；所有结论基于直接代码路径证据。

## 2. 完整 diff 范围确认

`git diff --name-only c7b01d82` 精确报告 12 个 tracked changed 文件：

```
dayu/config/README.md
dayu/tools/web/web_fetch_orchestrator.py
dayu/tools/web/web_http_session.py
dayu/tools/web/web_playwright_backend.py
dayu/tools/web/web_search_providers.py
dayu/tools/web/web_tools.py
docs/host/issues-implementation-control.md
docs/host/wu-semantic-ownership-01-r02-web-owner-policy-plan.md
tests/README.md
tests/tools/web/test_diagnose_web_access.py
tests/tools/web/test_web_tools_provider.py
utils/diagnose_web_access.py
```

S2 保护文件零 diff 已确认：`web_challenge_detection.py`、`web_egress_policy.py`、`web_recovery.py`、`utils/smoke_web_ci.py`、`utils/diag_web_batch.sh`、根 `README.md`。

## 3. 逐项原 Finding Disposition 复核

### 3.1 R02-S2-MIMO-F01 — Controller: reclassified to S3 / no S2 fix

- **原 reviewer 主张**：`utils/diagnose_web_access.py:2719-2722` 把 diagnostic `allow_custom_port` 绑定到 `allow_private_network_url`。
- **Controller disposition**：reclassified as already-planned S3 observation。
- **代码直接证据复核**：
  - `utils/diagnose_web_access.py:2719-2722`：
    ```python
    egress_policy = WebEgressPolicy(
        allow_private_network=options.allow_private_network_url,
        allow_custom_port=options.allow_private_network_url,
    )
    ```
    `allow_custom_port` 确实复用 `allow_private_network_url` 值，不从 typed config 独立读取。
  - R02 accepted plan §10.3 明确将 "diagnostic utility 消费完整 typed Web config、删除旧 CLI coupling" 分配给 S3。
  - S2 plan-drift `R02-S2-DR-01` 只精确前移 `transport_policy` 传播，不授权修改 egress policy 构造方式。
- **时序一致性**：**正确**。该 coupling 是 pre-existing diagnostic CLI 行为，S1 五 bool 拆分时未同步更新 diagnostic utility 的 egress policy 构造（S3 scope）。在 S2 修改会违反 slice temporal boundary。
- **裁决**：Controller disposition 与代码、设计真源和 slice timing **一致**。

### 3.2 R02-S2-DS-F01 — Controller: rejected / no fix

- **原 reviewer 主张**：`_fetch_web_page_business` 的 `ProxyPeerProofIncompatibleError` 分支调用 `_raise_fetch_failure(...)` 后缺少显式控制流终止（`return`/独立 `except`/注释）。
- **Controller disposition**：rejected as current defect。
- **代码直接证据复核**：
  - `web_tools.py:2139-2150`：`except requests.RequestException` 分支中，`isinstance(exc, ProxyPeerProofIncompatibleError)` 为 True 时调用 `_raise_fetch_failure(...)`。
  - `_raise_fetch_failure`（`web_tools.py:1277-1298`）：docstring 写 "Returns: 无（始终抛出异常）"；实现末尾 line 1290 是 `raise ToolBusinessError(...)`，无条件路径，无 `return`，无 `if` guard。
  - 因此 `ProxyPeerProofIncompatibleError` 路径在 line 2150 之后确实不可达（dead code）。
  - 但同一模式在 `except requests.TooManyRedirects`（line 2113-2130）和 `except requests.Timeout`（line 2131-2138）中同样存在——它们各自调用 `_raise_fetch_failure` 后无 `return`，依赖 owner contract 的 always-raise 语义。
- **一致性判断**：reviewer 承认当前行为正确，只建议结构改善。Controller 以 "不为假设性未来 contract 变化在消费者处局部补偿" 为由拒绝，与共享 owner contract 的设计原则 **一致**。增加局部注释或 `return` 不修复当前业务事实。
- **裁决**：Controller disposition 与代码和设计真源 **一致**。

### 3.3 R02-S2-DS-F02 — Controller: rejected / no fix

- **原 reviewer 主张**：`_fetch_web_page_business` 中两处 `FAIL_BLOCKED` 分支（line 2209-2218 与 line 2366-2375）的 `_raise_fetch_failure` 调用可抽取为统一 helper。
- **Controller disposition**：rejected as current defect。
- **代码直接证据复核**：
  - **第一处**（line 2209-2218）：在 `except requests.RequestException` 块内，处理 HTTP 异常响应层面检测到的 challenge `FAIL_BLOCKED`。message 为 `"Page appears to be a bot challenge page or access gate; fetched content is unusable."`。到达条件：HTTP 请求抛出异常、response 存在、challenge detector 判定 confirmed/blocked、browser fallback 不可用。
  - **第二处**（line 2366-2375）：在 fetch 成功后的 post-hoc challenge check 中，处理内容层面检测到的 challenge `FAIL_BLOCKED`。message 为 `"Page appears to be a bot challenge page; fetched content is unusable."`（无 "or access gate"）。到达条件：fetch 成功返回内容、content-level challenge detection 判定 blocked、browser fallback 不可用。
  - 两处拥有不同输入事实（HTTP exception context vs 成功 materialization 后的内容判定）、不同到达条件、和略有差异的 LLM-facing message。
- **一致性判断**：Controller 以 "两个独立 stage 的 terminal projection，不是同一业务事实被不同 owner 重算" 为由拒绝，与代码中两处的 control flow 上下文差异 **一致**。抽取 helper 会增加参数化 glue 并可能抹平 stage-specific 语义。
- **裁决**：Controller disposition 与代码和设计真源 **一致**。

## 4. Adversarial re-challenge 逐项验证

### 4.1 attempt-local prepare/merge/select/send

**PASS — 真实同源，无变化。**

`_send_authorized_request_attempt`（`web_http_session.py:638-748`）：
1. 单个 `call_session` 创建（line 676），`trust_env` 按 `transport_policy.allow_environment_proxy` 设置（line 677）。
2. `call_session.proxies.clear()`（line 685）— 先清空再由 `merge_environment_settings` 重新读取。
3. adapter 按 `dns_peer_proof_enabled` 选择：proof-on 用 `_TargetBoundHTTPAdapter`（line 688），proof-off 用标准 `HTTPAdapter`（line 690）。
4. `prepare_request` 只一次（line 708），`merge_environment_settings` 只一次（line 710-718），`select_proxy` 只一次（line 722-724），`send` 只一次（line 733-737）。
5. 每 redirect hop 由 `_request_with_safe_redirects`（`web_fetch_orchestrator.py:797`）单独调用，每 hop 重新 egress authorization + transport decision + prepare/merge/select/send。

### 4.2 proxy allow/deny/proof conflict

**PASS — fail closed，无变化。**

- **proxy deny**（`allow_environment_proxy=false`）：`trust_env=false`，`proxies.clear()`，merge 后 `settings["proxies"]` 必须为空（line 720-721），否则 `RuntimeError` fail closed。
- **proxy allow**（`allow_environment_proxy=true`）：`trust_env=true`，merge 读取环境 proxy，warning 只记录 `_PROXY_WITHOUT_PEER_PROOF_WARNING_REASON` 稳定 reason（line 729-731），不含 URL/proxy URI/credential。
- **proof + active proxy**：`selected_proxy is not None and dns_peer_proof_enabled` 触发 `ProxyPeerProofIncompatibleError()`（line 726-727），不静默降级。

### 4.3 search provider egress

**PASS — 三个 provider 统一通过 `_send_authorized_plain_request`，无变化。**

- Tavily（`_search_with_tavily`）、Serper（`_search_with_serper`）、DuckDuckGo（`_search_with_duckduckgo`）均迁入 `_send_authorized_plain_request`（`web_http_session.py:583-635`）。
- 每个 endpoint 先 `egress_policy.authorize_http_target(url, stage="search_provider_request")`（line 617-619）。
- `ProxyPeerProofIncompatibleError` 在 `search_public_web` 中即时 re-raise（line 362-363），不触发 provider fallback。
- `allow_redirects=False` 保留（line 736）。

### 4.4 browser/private 解耦与 proof fail-close

**PASS — 双向独立，无变化。**

- `_playwright_sync_worker` 中旧的 `egress_policy.allows_private_network` 前置 return 已删除。
- `_fetch_and_convert_with_playwright`（`web_playwright_backend.py:1622-1627`）guard 改为 `transport_policy.dns_peer_proof_enabled`，proof-on 时 fail closed 返回 `browser_peer_proof_unavailable`，不启动 Playwright import/process start。
- `_browser_fallback_available`（`web_tools.py:915-931`）返回 `browser_enabled and not transport_policy.dns_peer_proof_enabled`，用于 challenge 决策。
- `_try_playwright_fallback`（line 977-978）先检查 `browser_enabled`。
- `_clear_proxy_environment`（`web_playwright_backend.py:600-615`）在 `allow_environment_proxy=False` 时删除全部 8 个标准 proxy 变量。
- browser route/navigation 继续逐 URL 应用 `WebEgressPolicy`（`_raise_if_playwright_url_blocked`）。

### 4.5 diagnostic typed snapshot 同源传播

**PASS — single parse，无第二 default/parser/environment inference，无变化。**

`_build_single_diagnostic_payload`（`utils/diagnose_web_access.py:2714-2755`）：
1. `provider_config = _provider_config(options)` — 一次 raw mapping（line 2717）。
2. `transport_policy = _parse_config(provider_config).transport_policy` — provider parser owner 产生 typed snapshot（line 2718）。
3. 同一 `provider_config` 传给 `_build_requests_profile(..., transport_policy=transport_policy)`（line 2737-2742）和 `_build_tool_fetch_profile(..., provider_config=provider_config)`（line 2751-2755）。

utility 中无：`WebHttpTransportPolicy(...)` constructor、`dns_peer_proof_enabled`/`allow_environment_proxy` raw bool 解析、`getattr`/`os.environ`/`getenv`、第二 parser/default/environment inference。

`_build_requests_profile`（line 1462-1513）把 `transport_policy` 原样传给 `_request_with_safe_redirects`（line 1510）。AST signature audit 通过：`transport_signature_audit=2 issues=0`。

### 4.6 challenge/LLM-facing 语义

**PASS — 无变化。**

| 常量 | 文本 | AGENTS.md 合规 |
|---|---|---|
| `_PROXY_PEER_PROOF_INCOMPATIBLE_MESSAGE` | "当前连接验证策略与已启用的网络代理不兼容。" | ✅ 无内部术语 |
| `_BROWSER_PEER_PROOF_UNAVAILABLE_MESSAGE` | "当前浏览器访问无法验证目标连接。" | ✅ 无内部术语 |
| proxy warning | `"environment_proxy_active=true reason=%s"` + 稳定 reason | ✅ 只含非敏感 bool 与稳定 reason |
| `ProxyPeerProofIncompatibleError.reason` | `"proxy_peer_proof_incompatible"` | ✅ 稳定 typed error code |

### 4.7 retained security

**PASS — 完整，无变化。**

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
- `web_challenge_detection.py` 零 diff。

### 4.8 S3/deferred/no-code 零泄漏

**PASS — 无变化。**

- `utils/smoke_web_ci.py`、`utils/diag_web_batch.sh`、根 `README.md` 均零 diff。
- `_DEFAULT_DIAGNOSTIC_ERROR_CHARS = 1_024`、`--max-network default=80` 未删除。
- S3 storage lifecycle/CLI/TTL/owner filename/publish/reconcile 未前移。
- Issue #178、R03、proxy credential schema、统一 tool authorization framework 零实施/预埋。
- Topic 8/9 no-code 裁决未重开。

## 5. Findings

未发现实质性问题。

R02-S2-MIMO-F01（diagnostic `allow_custom_port` 耦合）已被 Controller 正确 reclassify 为 S3-owned observation，与 accepted plan §10.3 和 S2 plan-drift `R02-S2-DR-01` 的 slice timing 一致。R02-S2-DS-F01（`ProxyPeerProofIncompatibleError` 后缺显式控制流终止）和 R02-S2-DS-F02（`FAIL_BLOCKED` 分支重复）均被 Controller 正确 rejected——前者依赖共享 owner contract 的 always-raise 语义且同一模式在其他 except 分支中一致存在，后者是两个独立 stage 的 terminal projection 而非同一业务事实的重复 owner。

本 re-review 在完整 code/test diff 走读中未发现新的 material finding。

## 6. Open Questions

无。

## 7. Residual Risk

| residual | 当前处理 | owner / destination |
|---|---|---|
| diagnostic egress policy `allow_custom_port` 耦合 | S2 保持 pre-existing 行为，R02-S2-MIMO-F01 记录 | R02-S3；utility 消费 typed config 时修复 |
| storage lifecycle/CLI/TTL/owner filename/publish/reconcile | S2 不前移 | R02-S3 |
| `_DEFAULT_DIAGNOSTIC_ERROR_CHARS=1_024` / `--max-network default=80` | S2 不删除 | R02-S3；由 typed `DiagnosticResourceBudget` 同源替换 |
| `web_tools.py` ~80.06%、`web_playwright_backend.py` ~80.49% coverage | 精确 JSON 值通过 80% 门槛 | R02-S3 逐文件 coverage gate |
| `ProxyPeerProofIncompatibleError` handler 后隐式 dead code | owner contract always-raise 保证正确；DS-F01 记录 | 若需 static typing never-return 表达，由独立任务评估 |
| challenge `FAIL_BLOCKED` 两处 message 微差 | 不同 stage 的合理语义差异；DS-F02 记录 | 不需要修复 |

## 8. 结论

R02-S2 implementation 在 attempt-local HTTP transport strategy、proxy/proof conflict fail-close、search provider egress 统一、browser/private 双向解耦、diagnostic transport policy 同源传播、challenge/LLM-facing 语义、retained security 机制完整性和 S3/deferred 零泄漏方面均通过 adversarial re-review。三项原 finding 的 Controller disposition 与代码、设计真源和 slice timing 一致。无新 material finding。

**verdict：PASS — 0 new material finding / 3 原 finding disposition 复核通过。**
