# WU-SEMANTIC-OWNERSHIP-01 R02-S2 Implementation（Codex）

## 1. 状态、gate 与结论

状态：`IMPLEMENTATION CONTINUATION COMPLETE — WAITING CONTROLLER VALIDATION`。

本 artifact 是既有 `WU-SEMANTIC-OWNERSHIP-01 / R02-S2` implementation artifact 的最终 continuation 证据；不是新 WU、新 slice、implementation follow-up 或 S3 artifact。S2 base 仍为 accepted S1 commit `c7b01d82`，当前未提交 implementation diff 全程保留，未 reset、rollback、commit、push、更新 control 或启动 code review/S3/R03。

`R02-S2-DR-01` 已按 final plan 闭合：single-diagnostic orchestration 只生成一次既有 raw provider mapping，同一 mapping 同时交给既有 `provider._parse_config` 与 provider discovery；utility 只读取 parser owner 产生的 `WebToolsConfig.transport_policy`，并把该 mandatory typed snapshot 显式传给 `_build_requests_profile -> _request_with_safe_redirects`。没有在 utility 构造 `WebHttpTransportPolicy`、复制 transport bool 默认、解析 environment、增加 wrapper/facade、`getattr`、compatibility default 或 loose kwargs。

最终实现、测试、逐文件 coverage、完整 pyright、target-specific AST、docstring、source/allowlist/zero-diff、README trigger 与 §13 deterministic local Playwright/diagnostics smoke 均通过。下一 gate 只能是 Controller validation。

## 2. Plan-drift 链与 disposition

完整链如下：

1. 原 S2 implementation 收紧 `_request_with_safe_redirects(..., transport_policy=...)` 为无 default mandatory named contract；
2. 原 deterministic local smoke 的 `local-html-requests`、`local-pdf-requests`、`local-challenge-control` 在 artifact 生成前稳定抛出缺参 `TypeError`；
3. 本 artifact 的前一版按 stop rule 停止并保留未提交 diff；
4. `...-s2-plan-drift-controller-adjudication.md` 裁决 `R02-S2-DR-01=accepted / plan-fix-required`；
5. `...-s2-plan-drift-fix-codex.md` 把 direct caller/fake、direct/full diagnostic tests、smoke、signature/docstring/coverage/source gates精确写回 final plan；
6. `...-s2-plan-drift-controller-validation.md` 关闭 `R02-S2-DR-CV-F01` 的全局 `**kwargs` 假 blocker；
7. MiMo、DS 两路完整 plan-drift re-review 均 `PASS / 0 material finding`；
8. `...-s2-plan-drift-rereview-controller-adjudication.md` 最终裁决 `PLAN DRIFT RE-REVIEW PASS — RESUME SAME R02-S2 IMPLEMENTATION`；
9. 本 continuation 恢复同一个未提交 S2 diff并完成实现与全部 hard gates。

Controller notes disposition：

- `R02-S2-DR-01`：`closed-in-implementation`，typed snapshot 传播、direct/full tests与三个smoke artifact均闭合；
- `R02-S2-DR-CV-F01`：`fixed / re-reviewed-closed`；
- `R02-S2-RR-NOTE-01`：新增 direct node存在并通过，全部命令在 `.venv` 激活后执行；
- `R02-S2-RR-NOTE-02`：既有 utility `browser_egress_policy_unavailable` 断言仍通过且保持 S3-owned；
- `R02-S2-RR-NOTE-03`：100个 added/signature-touched definitions 已逐qualified name审计，issues=0；
- MiMo coverage residual：`web_tools.py=80.056179775280896%`，已按 JSON 精确值越过80%，不依赖四舍五入。

## 3. 第一性原理、root cause 与 owner

动机成立且严重性评估正确。缺陷不是网络、依赖、Playwright、预算或 smoke 分类问题；直接根因是 mandatory orchestrator contract 已收紧，而 existing diagnostic raw requests caller/fake仍使用旧签名。把 sender 参数加 default、跳过 raw diagnostics或在 utility 重建 policy都会制造第二owner并掩盖 half-migrated caller。

最终 owner 链：

```text
_provider_config(options) -> raw provider mapping（single diagnostic只生成一次）
  -> provider._parse_config(raw mapping) -> WebToolsConfig.transport_policy
  -> _build_requests_profile(..., transport_policy=typed snapshot)
  -> _request_with_safe_redirects(..., transport_policy=typed snapshot)

同一个 raw provider mapping
  -> _build_tool_fetch_profile(..., provider_config=raw mapping)
  -> _fetch_web_page_definition(provider_config)
  -> discover_tools(spec)
```

`provider._parse_config` 是 raw config parser owner；`WebHttpTransportPolicy` 的 type/attempt transport语义归 `web_http_session.py`；diagnostic utility与orchestrator都是显式consumer，不成为default/parser/transport owner。

## 4. Exact files 与变更

### 4.1 S2 production / utility

- `dayu/tools/web/web_http_session.py`：attempt-local标准/pinned transport、同次prepare/merge/select/send、proxy deny、proof+proxy typed fail、sanitized warning；补全新增 TypedDict/exception call contract docstring。
- `dayu/tools/web/web_fetch_orchestrator.py`：每跳mandatory transport传播，redirect authorization与body/budget语义保留。
- `dayu/tools/web/web_search_providers.py`：固定provider endpoint通过共享plain sender消费同一egress/transport owner；业务结果、credential、query/domain语义不变。
- `dayu/tools/web/web_playwright_backend.py`：browser/private解耦、proof gate在import/process start前fail closed、proxy环境继承/清理、route/navigation egress保留。
- `dayu/tools/web/web_tools.py`：typed snapshot唯一投影、真实browser capability、challenge事实与安全错误文本。
- `utils/diagnose_web_access.py`：只新增 `provider._parse_config` typed snapshot消费、raw requests mandatory参数，以及同一raw mapping继续进入provider discovery所需的显式参数传播；S3语义零变更。

实际 changed production `.py` 为上列五个 `dayu/tools/web/*.py`；`utils/**` 按 AGENTS 免coverage，但由direct/full diagnostic tests与真实smoke覆盖。

### 4.2 Tests

- `tests/tools/web/test_web_tools_provider.py`：HTTP proxy/proof、search sender、browser capability/proof/proxy、challenge、retained security/budget owner tests与全S2 touched-definition docstring闭合。
- `tests/tools/web/test_diagnose_web_access.py`：exact `_request_with_safe_redirects` fake新增无default typed `transport_policy`；固定node `test_requests_profile_forwards_provider_owned_transport_policy` 使用非默认raw config `dns_peer_proof_enabled=true / allow_environment_proxy=false`，证明parser-owned snapshot传播，并证明同一个raw mapping继续交给provider discovery；其余机械signature同步不改expectation。

### 4.3 README 与 gate artifacts

- `dayu/config/README.md`：进入continuation前的既有S2 diff，记录五bool当前transport/browser行为；本continuation未增加新README语义。
- `tests/README.md`：进入continuation前的既有S2 diff，记录owner/security matrix；本continuation未增加新README语义。
- `docs/host/wu-semantic-ownership-01-r02-web-owner-policy-plan.md`：final plan-drift target，进入continuation前已存在；本轮只读。
- `docs/host/issues-implementation-control.md`：Controller-owned gate状态，进入continuation前已存在；本轮只读，当前hash `c1df13bc25f73a8946ce59b407eeba8690f9a61e`。
- plan-drift adjudication/fix/validation/MiMo/DS/controller artifact均保留；只更新本文件，没有创建第二个 implementation follow-up artifact。

明确零diff：`dayu/tools/web/web_challenge_detection.py`、`utils/smoke_web_ci.py`、`utils/diag_web_batch.sh`、根 `README.md`、`web_egress_policy.py`、`web_recovery.py`。未修改 Issue 178、R03、proxy credential schema、统一authorization或其它deferred路径。

## 5. Tests 与 counts

所有命令均先执行 `source .venv/bin/activate`：

| gate | 结果 |
|---|---:|
| provider focused：`-k 'private or custom_port or proxy or peer or redirect or browser or challenge'` | `69 passed, 1 skipped, 105 deselected` |
| provider full | `174 passed, 1 skipped` |
| diagnostic direct node | `1 passed` |
| diagnostic full | `37 passed` |
| config-loader regression full | `52 passed` |
| final joint coverage run：provider full + diagnostic full | `211 passed, 1 skipped` |

唯一 pytest skip 是既有 opt-in/manual live browser cleanup smoke `DAYU_RUN_LIVE_BROWSER_CLEANUP_SMOKE`；它不是 §13 local hard gate。§13真实Playwright已独立执行且local零skip。

## 6. Changed production逐文件coverage

coverage data：`workspace/tmp/.coverage-r02-s2`；JSON：`workspace/tmp/coverage-r02-s2.json`。逐文件 `coverage report --include=<exact-file> --fail-under=80` 全部 exit 0。

| production file | percent_covered（JSON精确值） | covered / statements / missing |
|---|---:|---:|
| `dayu/tools/web/web_http_session.py` | `89.122807017543863%` | `254 / 285 / 31` |
| `dayu/tools/web/web_fetch_orchestrator.py` | `81.624758220502898%` | `422 / 517 / 95` |
| `dayu/tools/web/web_search_providers.py` | `87.457627118644069%` | `258 / 295 / 37` |
| `dayu/tools/web/web_playwright_backend.py` | `80.487804878048777%` | `429 / 533 / 104` |
| `dayu/tools/web/web_tools.py` | `80.056179775280896%` | `570 / 712 / 142` |

五文件均按精确JSON值 `>=80%`。特别是 `web_tools.py` 没有借coverage report的整数显示或四舍五入通过。

## 7. Added/signature-touched 中文docstring audit

方法：以 `c7b01d82` 为base，AST比较八个实际changed production/test Python文件的function/method/class signature；对每个added/signature-touched function/method/nested helper校验中文docstring存在并完整包含 `Args`、`Returns`、`Raises`，且逐参数名检查Args覆盖；对新增class/TypedDict检查职责、fields/attributes、call contract、Returns与Raises。

结果：`added/signature-touched=100 / issues=0`；其中新增class/TypedDict 2个，class contract issues=0。完整qualified names：

### Production / utility（27）

```text
dayu/tools/web/web_fetch_orchestrator.py:
  _request_with_safe_redirects
  _warmup_domain
  _probe_content_type
  _fetch_and_convert_content
dayu/tools/web/web_http_session.py:
  _MergedEnvironmentSettings
  ProxyPeerProofIncompatibleError
  ProxyPeerProofIncompatibleError.__init__
  _send_authorized_request
  _send_authorized_plain_request
  _send_authorized_request_attempt
dayu/tools/web/web_playwright_backend.py:
  _playwright_process_entry
  _clear_proxy_environment
  _run_playwright_worker_process
  _fetch_and_convert_with_playwright
dayu/tools/web/web_search_providers.py:
  search_public_web
  _search_with_tavily
  _search_with_serper
  _search_with_duckduckgo
dayu/tools/web/web_tools.py:
  _browser_fallback_available
  _try_playwright_fallback
  _warmup_domain
  _probe_content_type
  _fetch_and_convert_content
  _fetch_and_convert_with_playwright
utils/diagnose_web_access.py:
  _build_requests_profile
  _fetch_web_page_definition
  _build_tool_fetch_profile
```

### Provider tests（57）

```text
test_ordinary_fetch_failure_matrix_keeps_config_diagnostic_owner.fail_fetch
test_ordinary_fetch_failure_matrix_keeps_config_diagnostic_owner.controlled_browser_fallback
_queued_send_authorized_request
_plain_response_lease
_stable_owner_warmup
_stable_owner_probe
_process_entry_proxy_environment_worker
test_http_transport_proxy_allow_prepares_once_and_reuses_merged_settings
test_http_transport_proxy_allow_prepares_once_and_reuses_merged_settings.record_prepare
test_http_transport_proxy_allow_prepares_once_and_reuses_merged_settings.record_merge
test_http_transport_proxy_allow_prepares_once_and_reuses_merged_settings.record_select_proxy
test_http_transport_proxy_allow_prepares_once_and_reuses_merged_settings.record_send
test_http_transport_proxy_deny_ignores_environment_and_sends_direct
test_http_transport_proxy_deny_ignores_environment_and_sends_direct.record_direct_send
test_http_transport_proof_with_active_proxy_fails_typed_before_send
test_http_transport_proof_with_active_proxy_fails_typed_before_send.return_proxy_settings
test_http_transport_proof_with_active_proxy_fails_typed_before_send.select_active_proxy
test_http_transport_proof_with_active_proxy_fails_typed_before_send.reject_send
test_search_public_web_provider_result_excludes_llm_guidance.fake_search_with_duckduckgo
test_search_web_receives_execution_context_and_passes_cancellation_token.fake_search_public_web
test_search_web_cancelled_before_provider_returns_host_cancelled.fake_search_public_web
test_search_web_deep_cancel_message_is_sanitized.fake_search_public_web
test_search_web_cancelled_between_provider_attempts_stops_fallback.fake_search_with_tavily
test_search_web_cancelled_between_provider_attempts_stops_fallback.fake_search_with_duckduckgo
test_s2_owner_signatures_and_worker_payload_are_closed
test_playwright_budget_failure_projects_stable_tool_error
test_playwright_budget_failure_projects_stable_tool_error.fake_fetch_with_playwright
test_challenge_confirmed_http_500_uses_current_browser_capability
test_challenge_confirmed_http_500_uses_current_browser_capability.get_test_session
test_challenge_confirmed_http_500_uses_current_browser_capability.fake_playwright_fallback
test_tavily_provider_builds_typed_rows.fake_send
test_serper_provider_builds_typed_rows.fake_send
test_duckduckgo_provider_streams_budgeted_body_and_closes_response.fake_send
test_duckduckgo_plain_sender_retains_egress_and_challenge_semantics
test_duckduckgo_plain_sender_retains_egress_and_challenge_semantics.resolve_provider
test_duckduckgo_plain_sender_retains_egress_and_challenge_semantics.return_challenge_response
test_duckduckgo_plain_sender_retains_egress_and_challenge_semantics.record_challenge_detection
test_search_provider_forwards_proxy_and_peer_policy_to_plain_sender
test_search_provider_forwards_proxy_and_peer_policy_to_plain_sender.record_plain_sender
test_search_proxy_peer_incompatibility_is_not_provider_fallback
test_search_proxy_peer_incompatibility_is_not_provider_fallback.fail_plain_sender
test_search_proxy_peer_incompatibility_projects_safe_tool_failure
test_search_proxy_peer_incompatibility_projects_safe_tool_failure.fail_search_business
test_playwright_public_direct_runs_without_private_permission
test_playwright_public_direct_runs_without_private_permission.run_public_process
test_browser_disabled_with_private_permission_does_not_start_backend
test_browser_disabled_with_private_permission_does_not_start_backend.record_backend_call
test_browser_peer_proof_fails_before_process_with_safe_projection
test_browser_peer_proof_fails_before_process_with_safe_projection.record_process_call
test_playwright_process_wrapper_keeps_diagnostic_budget_out_of_worker_kwargs.fake_run_process
test_playwright_wrapper_retains_timeout_and_challenge_with_split_owners.challenge_process_result
test_playwright_process_entry_controls_proxy_environment
test_fetch_playwright_url_safety_projects_permission_denied.fake_fetch_and_convert_with_playwright
test_fetch_playwright_cancel_projects_to_host_cancelled.fake_fetch_and_convert_with_playwright
test_try_playwright_fallback_pre_cancel_does_not_start_playwright.fake_fetch_and_convert_with_playwright
test_fetch_playwright_fallback_receives_channel_and_storage_state_path.fake_fetch_and_convert_with_playwright
test_fetch_playwright_fallback_uses_empty_storage_state_when_dir_empty.fake_fetch_and_convert_with_playwright
```

### Diagnostic tests（16）

```text
_raise_diagnostic_request_exception
test_single_diagnostic_private_mode_preserves_local_custom_port.fake_build_requests_profile
test_requests_profile_forwards_provider_owned_transport_policy
test_requests_profile_forwards_provider_owned_transport_policy.fake_provider_config
test_requests_profile_forwards_provider_owned_transport_policy.fake_build_requests_profile
test_requests_profile_forwards_provider_owned_transport_policy.fake_build_tool_fetch_profile
test_requests_profile_records_raw_response_byte_length.fake_request_with_safe_redirects
test_current_fetch_adapter_completed_outcome_generates_ok_profile.fake_definition
test_docling_wrapper_records_invoked_true_and_restores_callable.fake_definition
test_html_fetch_profile_records_docling_invoked_false.fake_definition
test_pdf_fetch_success_without_docling_invocation_keeps_failure_evidence_for_smoke.fake_definition
test_docling_runtime_initialization_exception_becomes_skip_observed_item.fake_definition
test_generic_docling_conversion_exception_is_not_skip_observed_item.fake_definition
test_current_fetch_adapter_failed_outcome_generates_business_readable_profile.fake_definition
_fake_requests_profile
_fake_fetch_profile
```

既有 `_BrowserTypeProtocol.launch(**kwargs)` 与 `_BrowserProtocol.new_context(**kwargs)` 精确两处保留；它们镜像Playwright browser API，不是transport seam，且各自已有完整中文docstring。

## 8. Type、signature、diff、allowlist 与source scans

- 完整 `python -m pyright`：`0 errors, 0 warnings, 0 informations`；覆盖 `dayu/tests/utils`，无exclude或baseline waiver。
- target-specific AST：`transport_signature_audit=2 issues=0`；`_build_requests_profile`与`fake_request_with_safe_redirects`均有无default typed keyword-only `transport_policy`，均无loose `**kwargs`。
- utility transport零命中：无 `WebHttpTransportPolicy(...)` constructor、`dns_peer_proof_enabled`/`allow_environment_proxy` raw parsing、`getattr`、`os.environ`/`getenv`读取；utility只import type并消费parser返回snapshot。
- propagation scan明确命中：`_provider_config -> _parse_config -> transport_policy -> _build_requests_profile -> _request_with_safe_redirects`，以及exact fake/test owner assertion。
- `browser_egress_policy_unavailable`只剩 `test_diagnose_web_access.py` 的既有S3-owned utility断言；`browser_available=True` production零残留。
- `trust_env=false/proxies={}`唯一production命中归属显式proxy-deny或pinned proof adapter，不是unconditional standard path。
- S3 retained scan确认 `_StorageStateLifecycle`、storage-state CLI/TTL/owner filename/reconcile、`_DEFAULT_DIAGNOSTIC_ERROR_CHARS=1_024`、`--max-network default=80`仍保持，未被本slice提前删除或改写。
- challenge detector、smoke脚本、batch脚本、根README均 `git diff --exit-code` exit 0。
- allowed-file scan相对 `c7b01d82` 只包含final plan批准的五个Web production文件、diagnostic utility、两份Web tests、两份README、final plan/control与固定plan-drift/implementation artifacts；无新增allowlist drift。
- `git diff --check`：exit 0；新增本artifact另以 `git diff --no-index --check /dev/null <artifact>` 验证无whitespace issue（存在预期内容差异时no-index返回1）。

## 9. §13 deterministic local / real Playwright / diagnostics smoke

执行final plan原命令，`utils/smoke_web_ci.py`保持零diff：

```bash
python utils/smoke_web_ci.py \
  --output-dir workspace/tmp/r02-web-owner-policy-local \
  --external-limit 0 \
  --include-playwright \
  --request-timeout 20 \
  --tool-timeout-budget 60 \
  --run-label r02-web-owner-policy-local
```

结果：exit `0`，`status=passed`，`local_cases=7`，`failures=0`，`skips=0`，`search_cases=4 diagnostic_only`。summary：

- `workspace/tmp/r02-web-owner-policy-local/summary.json`
- `workspace/tmp/r02-web-owner-policy-local/summary.md`

三个原 `artifact_missing` case 全部生成v2/revision2 evidence并通过：

| case | artifact | outcome / metric | challenge |
|---|---|---|---|
| `local-html-requests` | `diagnostics/local/local-html-requests.json` | requests completed，HTTP 200，content 238 B | `none` |
| `local-pdf-requests` | `diagnostics/local/local-pdf-requests.json` | requests completed，HTTP 200，content 652 B | `none` |
| `local-challenge-control` | `diagnostics/local/local-challenge-control.json` | requests completed，HTTP 200，content 75 B | `confirmed` |

三者均为 `schema_version=diagnostic_schema_version=web-diagnostics-v2`、`diagnostic_schema_revision=2`，不再出现mandatory parameter `TypeError`。

真实Playwright证据：`diagnostics/local/local-browser-playwright.json`，Playwright sampled/completed、`browser_executed=true`、HTTP 200、response 367 B、rendered HTML 510 chars、rendered text 118 chars、network events 2、challenge=`none`、v2/revision2。`local-html-tool`、`local-pdf-tool`、`local-assembly-config`也均通过；未观察到冻结budget ceiling命中或由budget导致的业务失败。

四个search provider case只作为既有external diagnostic-only补充：3个`provider_unavailable`、1个`provider_key_missing`，不影响local hard gate且未触发policy/default改写。

## 10. README decision

- `dayu/config/README.md`：`updated-existing-S2-diff`；其职责覆盖Web config默认与transport/browser行为，内容与实现一致。本continuation不改变config/schema/default，无新增README修改需求。
- `tests/README.md`：`updated-existing-S2-diff`；其职责覆盖owner/security test matrix，内容与最终tests一致。本continuation的direct diagnostic node不改变用户工作流或S3预期，无新增README修改需求。
- 根 `README.md`：`no-update-with-evidence`；诊断CLI、安装、初始化、用户入口与工作流均未改变，且文件零diff。
- `dayu/README.md`及Host/Engine/Fins/UI README：`no-update-with-evidence`；层级、装配与对应模块contract未变。

`dayu/config/README.md`与`tests/README.md`没有独立 `Agent更新约束` 章节，因此按根 `AGENTS.md` 的trigger与读者职责复核；未机械扩写。

## 11. Retained contract、风险与handoff

Retained release-blocking contract均由tests/smoke覆盖：初始URL/redirect每跳重检、dangerous/unspecified/multicast/mixed DNS与private/custom-port deny、proof-on numeric peer match/mismatch、proxy deny与proof+proxy typed fail、browser route/navigation egress、HTTP/browser/diagnostic budgets、challenge facts、diagnostics v2/revision2、redaction、storage input/containment/symlink及ordinary writer/profile schema。

Residual risks均有owner：

- storage lifecycle/CLI/TTL/owner filename/publish/reconcile与utility-local `1_024/default=80`：S2按final plan原样保留，destination=`R02-S3`；不是本slice缺口。
- credential refresh/retention/concurrent publish/cleanup：destination=Issue #178；R02-S2未实施或预埋。
- external provider DNS/credential/站点波动：owner=external environment/provider diagnostics；local deterministic hard gate已通过，因此non-blocking。
- proxy下无法证明origin peer、Playwright无法提供numeric peer proof：分别由typed `proxy_peer_proof_incompatible` 与 `browser_peer_proof_unavailable` fail closed；无静默降级。

没有ownerless residual、unclassified risk、allowlist drift或新的产品问题。

Handoff：等待Controller validation；不得自行commit、push、修改control、启动code review、进入S3/R03或创建新的implementation artifact。
