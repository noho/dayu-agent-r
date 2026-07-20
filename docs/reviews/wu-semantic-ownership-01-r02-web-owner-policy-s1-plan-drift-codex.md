# WU-SEMANTIC-OWNERSHIP-01 / R02-S1 plan/slice allowlist drift evidence — Codex

## 1. 身份、基线与结论

- umbrella：既有 `WU-SEMANTIC-OWNERSHIP-01`。
- remediation sub-WU：`R02`；本轮是同一 R02 的 S1 plan gate drift follow-up，不是新 WU、feature、issue 或 implementation。
- accepted plan commit：`6e2a76b3`。
- 当前 control/base：`4d2df7036367ec51891d893dcba42a468e3a921d`。
- 审计范围：当前仓库中 `dayu/`、`utils/`、`tests/` 对 `WebResourceBudget` 的全部直接 source/test 引用，以及删除旧类型后的 import、signature、typed payload 与测试传播链。
- 结论：Controller 判定的 material drift 成立，而且最小 drift 比最初两文件证据更大。若 S1 删除 `WebResourceBudget` 并要求旧符号零残留、无 dual schema、完整 pyright，则除 accepted S1 已列文件外，还必须把三个 source 文件和一个 test 文件的**纯 budget-type migration**同步移入 S1：
  - `dayu/tools/web/web_fetch_orchestrator.py`
  - `dayu/tools/web/web_playwright_backend.py`
  - `utils/diagnose_web_access.py`
  - `tests/tools/web/test_diagnose_web_access.py`
- 上述四文件的 S1 授权只能覆盖 typed budget 参数拆分、field projection、直接测试签名同步；不能授权 S2 proxy/peer/browser capability 行为或 S3 lifecycle/CLI/storage cleanup。
- 状态：**PLAN GATE BLOCKED / READ-ONLY AUDIT COMPLETE / NO IMPLEMENTATION**。

## 2. 审计方法与全仓直接引用闭集

执行 `rg -l '\bWebResourceBudget\b' dayu tests utils | sort` 得到九个文件，构成当前直接引用闭集：

| 分类 | 文件 | 旧符号命中数 | 审计判定 |
|---|---|---:|---|
| owner | `dayu/tools/web/web_resource_budget.py` | 4 | S1 删除旧 owner，建立三个 child type、typed defaults 与纯 aggregate |
| parser | `dayu/tools/web/provider.py` | 3 | accepted S1；改为 nested typed defaults/parser，返回 aggregate snapshot |
| source consumer | `dayu/tools/web/web_tools.py` | 13 | accepted S1；aggregate 只在 config snapshot，向每个 consumer 投影 child type |
| source consumer | `dayu/tools/web/web_search_providers.py` | 6 | accepted S1；全部只接 `HttpResourceBudget` |
| source consumer | `dayu/tools/web/web_fetch_orchestrator.py` | 7 | **S1 drift 新增**；HTTP body 与 warmup 分属两个 child owner |
| source consumer | `dayu/tools/web/web_playwright_backend.py` | 7 | **S1 drift 新增**；browser materialization 与 diagnostic projection 必须拆参 |
| script consumer | `utils/diagnose_web_access.py` | 4 | **S1 drift 新增**；pyright 明确包含 `utils`，不能留到 S3 |
| direct test consumer | `tests/tools/web/test_web_tools_provider.py` | 26 | accepted S1；所有 helper/fake/call signature 必须同步 |
| direct test consumer | `tests/tools/web/test_diagnose_web_access.py` | 2 | **S1 drift 新增**；直接 import/constructor 会在 collection/pyright 失败 |

`pyrightconfig.json` 的 `include` 同时包含 `dayu`、`tests`、`utils`。因此，即使 S1 targeted pytest 不执行 diagnostic 测试，保留 `utils/diagnose_web_access.py` 或 `tests/tools/web/test_diagnose_web_access.py` 的旧 import 仍会使完整 pyright 和旧符号零残留终态失败，不能以“后续 S3 才运行”规避。

`dayu/tools/web/web_diagnostics.py` 没有 import 或接收 `WebResourceBudget`；它当前接显式 `max_error_chars` 等 owner fields。仅为删除旧类型，不要求该文件产生 diff。若 Controller 另行要求它改为接 `DiagnosticResourceBudget`，那是额外 API 设计裁决，不应从本次直接 consumer audit 自动推导。

## 3. Source consumer 的最小 typed migration

### 3.1 `dayu/tools/web/provider.py` — aggregate parser owner（既有 S1）

| 当前符号 | 当前输入/输出 | S1 最小终态 |
|---|---|---|
| `_parse_config` | 构造 `WebToolsConfig(resource_budget=WebResourceBudget)` | 解析 nested groups，构造 `WebResourceBudgets(http, browser, diagnostics)` |
| `_resource_budget_default` | 整个 flat complete object 或 whole-object default | 替换为 group/field local typed parser；缺失项取 child typed default，存在项 exact validate |

该文件不应把 aggregate 再拆平，也不修改 ConfigLoader record replacement。

### 3.2 `dayu/tools/web/web_tools.py` — typed snapshot 与唯一 projection owner（既有 S1）

| 当前符号/结构 | 当前旧消费 | 应接的小类型 |
|---|---|---|
| `_DEFAULT_WEB_DIAGNOSTIC_ERROR_CHARS` | `WebResourceBudget().diagnostic_error_chars` | 从 typed diagnostic default 的 `error_chars` 派生；不得保留第二 literal |
| `WebToolsConfig.resource_budget` | 七字段对象 | `WebResourceBudgets` 纯 aggregate；aggregate 只停留在 immutable config snapshot |
| `_PlaywrightFallbackKwargs` | 单一 `resource_budget` | 分为 `browser_resource_budget: BrowserResourceBudget` 与 `diagnostic_resource_budget: DiagnosticResourceBudget` |
| `_StageFetchKwargs` | warmup/probe 共用单一 `resource_budget` | 不再共用。warmup kwargs 接 `BrowserResourceBudget`；probe kwargs不接 budget |
| `_FetchConvertKwargs` | 单一 `resource_budget` | `http_resource_budget: HttpResourceBudget` |
| `_try_playwright_fallback` | 单一七字段参数 | 显式接 `BrowserResourceBudget` + `DiagnosticResourceBudget` |
| `_warmup_domain` wrapper | 读取/转交 `warmup_body_bytes` | `BrowserResourceBudget`，使用 `warmup_body_bytes` |
| `_probe_content_type` wrapper | 接收但完全不读取 budget | 删除 budget 参数；不能为接口对称继续传无语义参数 |
| `_search_web_business` | 把 aggregate 传给 search provider | 只传 `config.resource_budgets.http`；visibility policy 的 private/custom-port 改造仍按 accepted S1 独立执行 |
| `_fetch_web_page_business` | 一份对象进入 warmup、probe、fetch、browser | warmup=`browser`；probe=无 budget；fetch=`http`；browser fallback=`browser + diagnostics` |
| `_fetch_and_convert_content` wrapper | 单一七字段参数 | `HttpResourceBudget` |
| `_playwright_sync_worker` wrapper | 单一七字段参数 | `BrowserResourceBudget` |
| `_fetch_and_convert_with_playwright` wrapper | 单一七字段参数 | `BrowserResourceBudget` + `DiagnosticResourceBudget` |

这是唯一允许拆解 aggregate 的 projection point；下游 consumer 不应接 aggregate，也不应自行从 raw config 重建 child values。

### 3.3 `dayu/tools/web/web_search_providers.py` — HTTP-only consumer（既有 S1）

以下所有符号只消费 wire/decoded body，统一接 `HttpResourceBudget`，字段名保持 `wire_body_bytes` / `decoded_body_bytes`：

- `search_public_web`
- `_search_with_tavily`
- `_search_with_serper`
- `_search_with_duckduckgo`
- `_materialize_bounded_search_response`

`search_public_web` 到三个 provider sender 的参数名应收窄为 `http_resource_budget`，不保留 generic `resource_budget`。本迁移不改三个模块级 `requests.get/post`、endpoint、redirect、credential、provider fallback、challenge 或结果语义；这些 transport 行为仍属于 S2。

### 3.4 `dayu/tools/web/web_fetch_orchestrator.py` — HTTP + warmup consumer（S1 drift 新增）

| 当前符号 | 实际读取字段 | 应接的小类型 |
|---|---|---|
| `_decompress_limited_response_body` | `decoded_body_bytes` | `HttpResourceBudget` |
| `_read_limited_response_body` | `wire_body_bytes`、`decoded_body_bytes` | `HttpResourceBudget` |
| `_materialize_response_body` | 透传 HTTP wire/decoded budget | `HttpResourceBudget` |
| `_fetch_and_convert_content` | 透传 HTTP body budget | `HttpResourceBudget` |
| `_warmup_domain` | `warmup_body_bytes` | `BrowserResourceBudget`（字段 owner 由 accepted nested schema 的 browser group 冻结） |
| `_probe_content_type` | 不读取任何 budget 字段 | 删除 budget 参数，不接任何 child type |

该文件在 S1 只允许 import、annotation、parameter name、docstring、typed forwarding 与无效 probe 参数删除。以下保持逐字/逐行为不变：`_send_authorized_request` 调用签名、numeric pin、no-proxy、redirect 每 hop authorization、mixed DNS、response lease、timeout/cancellation 与 body materialization 算法。

### 3.5 `dayu/tools/web/web_playwright_backend.py` — Browser + Diagnostic consumer（S1 drift 新增）

| 当前符号/结构 | 实际读取字段 | 应接的小类型 |
|---|---|---|
| `_read_budgeted_dom_metrics` | `browser_dom_chars`、`browser_text_chars` | `BrowserResourceBudget.dom_chars/text_chars` |
| `_materialize_bounded_page_projection` | DOM/text limits | `BrowserResourceBudget` |
| `_playwright_sync_worker` | DOM/text/markdown limits | `BrowserResourceBudget` |
| `_PlaywrightWorkerProtocol` | worker 的 single budget 参数 | 只接 `BrowserResourceBudget` |
| `_playwright_process_entry` | `diagnostic_error_chars` | `DiagnosticResourceBudget.error_chars` |
| `_fetch_and_convert_with_playwright` | browser limits + failure projection error limit | 显式接 `BrowserResourceBudget` + `DiagnosticResourceBudget` |
| `_WorkerKwargs` | 同一 key 同时代签 browser + diagnostic | 必须拆成 browser worker kwargs 与 process diagnostic input，或等价的两个显式 typed fields；不得把 diagnostic budget作为 worker不使用的 extra kwarg splat进去 |

建议的最小结构是：worker callable kwargs 只包含 browser budget；process wrapper 另有显式 diagnostic budget，并在调用 worker 时逐字段构造参数。这样 browser producer 与 diagnostic producer 各自只看到自己的 owner type。

该文件进入 S1 不授权删除 `allows_private_network` 前置 return、不授权 `browser_enabled` gate、不授权 `browser_peer_proof_unavailable`、proxy env 处理、Playwright import/process start 时序或 route/navigation 行为变化；这些全部仍属 S2。

### 3.6 `utils/diagnose_web_access.py` — diagnostic script 内的 HTTP + Browser consumer（S1 drift 新增）

当前 `_DIAGNOSTIC_RESOURCE_BUDGET: WebResourceBudget` 被三条不同路径共用，必须按实际消费拆开：

| 当前调用/符号 | 实际读取字段 | 应接的小类型 |
|---|---|---|
| requests profile -> `_web_fetch_orchestrator._materialize_response_body` | wire/decoded body | `HttpResourceBudget` |
| Playwright profile -> `_web_playwright_backend._materialize_bounded_page_projection` | DOM/text | `BrowserResourceBudget` |
| `_read_bounded_playwright_response_body` | `decoded_body_bytes` | `HttpResourceBudget` |

最小 S1 type-only migration 必须完整包含：

- import 从 `WebResourceBudget` 改为 `HttpResourceBudget` 与 `BrowserResourceBudget`；本文件没有旧类型承载的 direct diagnostic consumer，因此不能仅为对称性额外引入 `DiagnosticResourceBudget`。
- `_DIAGNOSTIC_RESOURCE_BUDGET` 拆为两个带 `Final` 精确注解的 child 常量：HTTP 常量由 `HttpResourceBudget` typed default 构造，Browser 常量由 `BrowserResourceBudget` typed default 构造；不得保留 aggregate、旧七字段 bag 或本地数值 default。
- requests profile 调 `_materialize_response_body` 时只传 HTTP 常量；Playwright profile 调 `_materialize_bounded_page_projection` 时只传 Browser 常量。
- `_read_bounded_playwright_response_body` 的 `resource_budget` 参数改为 `HttpResourceBudget`，其调用只传 HTTP 常量；helper 的 declared/actual bytes early/post check 算法与异常类型不变。

除此之外不改 CLI、storage-state lifecycle、writer、network event cap、browser availability或 profile schema。

相邻但不应静默混入的事实：该脚本另有 `_DEFAULT_DIAGNOSTIC_ERROR_CHARS = 1024`，它不是 `WebResourceBudget` 直接依赖。若 Controller 认定 S1 的“backend 无第二 default”已覆盖 utility，则需另行明确授权它改由 `DiagnosticResourceBudget.error_chars` 派生；否则保持到 S3 由 utility 消费新 config 时处理。`DiagnosticResourceBudget.events` 当前在 `dayu/tools/web` 生产路径中没有直接字段 consumer，network event 数量仍由 diagnostic utility 的现有 CLI/profile owner 控制；是否前移到 S1 同样需要 plan 裁决，不能在 type-only drift fix 中自行改变。

## 4. 最小 S1 文件闭集修正

### 4.1 已在 accepted S1 中、必须继续修改的 budget 相关文件

- `dayu/tools/web/web_resource_budget.py`
- `dayu/tools/web/provider.py`
- `dayu/tools/web/web_tools.py`
- `dayu/tools/web/web_search_providers.py`
- `tests/tools/web/test_web_tools_provider.py`
- `tests/runtime/test_config_loader.py`（packaged nested config exact assertions；不是旧类型 direct consumer）

`dayu/config/tool_discovery.json` 与 README 属 accepted S1 config/docs diff，但不是 Python direct consumer；本 artifact 不重新裁决它们。

### 4.2 必须移入 S1 的最小 drift 增量

| 文件 | 当前 slice | 必须移入 S1 的精确边界 |
|---|---|---|
| `dayu/tools/web/web_fetch_orchestrator.py` | S2 | 只做 Http/Browser budget type、parameter 与 forwarding 拆分；probe 删除无语义 budget 参数 |
| `dayu/tools/web/web_playwright_backend.py` | S2 | 只做 Browser/Diagnostic budget type、worker/process typed payload 与 forwarding 拆分 |
| `utils/diagnose_web_access.py` | S3 | 只做旧 budget import/constant/call split；不碰 lifecycle/CLI/writer/profile behavior |
| `tests/tools/web/test_diagnose_web_access.py` | S3 | 只把 direct old constructor/call改为 `HttpResourceBudget` 对应测试输入 |

没有第五个 direct source/test file 需要为“删除旧类且完整 pyright”产生 diff。

## 5. 现有 tests 的断裂面

### 5.1 必须同步编辑的直接 test consumers

#### `tests/tools/web/test_web_tools_provider.py`（accepted S1）

模块顶层直接 import `WebResourceBudget`；不更新会在 collection 与 pyright 直接失败。支持代码必须拆分：

- `_DEFAULT_RESOURCE_BUDGET` -> typed HTTP / Browser / Diagnostic defaults（需要 aggregate 时显式组合）。
- `_resource_budget` -> 按 owner 拆为 HTTP、Browser、Diagnostic helper；不得继续返回七字段 bag。
- `_resource_budget_json` -> nested `http` / `browser` / `diagnostics` JSON helper。
- `_SyntheticNestedPlaywrightWorker.__call__`、`_LiveBrowserLongRunningWorker.__call__`、`_BlockedPlaywrightWorker.__call__` -> worker只接 Browser budget；process diagnostic budget由 typed process kwargs独立提供。
- 各测试内 fake search/fetch/playwright callable 的签名与 production 同步，不能用 `**kwargs` 或 loose typing 掩盖 owner contract。

现有 node 按断裂类型分组如下。

**Config/constructor 直接断裂：**

- `test_resource_budget_constructor_rejects_bool_and_non_positive_integer`
- `test_resource_budget_provider_config_complete_object_and_default`
- `test_resource_budget_provider_config_rejects_partial_object`
- `test_resource_budget_provider_config_rejects_unknown_and_invalid_values`
- `test_search_web_receives_provider_config`

这些测试应迁移为三个 child constructor 的独立正整数校验、nested group/field local default/invalid/unknown 校验，以及 packaged/typed conformance；不得保留 complete flat object expectation。

**HttpResourceBudget 直接签名/call 断裂：**

- `test_search_public_web_provider_result_excludes_llm_guidance`
- `test_search_web_receives_execution_context_and_passes_cancellation_token`
- `test_search_web_cancelled_before_provider_returns_host_cancelled`
- `test_search_web_deep_cancel_message_is_sanitized`
- `test_search_web_cancelled_between_provider_attempts_stops_fallback`
- `test_tavily_provider_builds_typed_rows`
- `test_serper_provider_builds_typed_rows`
- `test_duckduckgo_provider_streams_budgeted_body_and_closes_response`
- `test_fetch_body_limit_maps_to_structured_tool_failure`
- `test_fetch_body_limit_context_does_not_decode_unbounded_response`
- `test_fetch_http_error_body_is_bounded_before_status_projection`
- `test_decompress_incremental_codec_exact_limit_and_limit_plus_one`
- `test_identity_body_exact_decoded_limit_and_limit_plus_one`
- `test_decompress_incremental_multi_layer_and_compression_bomb`
- `test_decompress_brotli_without_bounded_output_api_is_unsupported`
- `test_decompress_zstd_streaming_when_dependency_available`
- `test_fetch_redirect_to_private_url_fails_closed`
- `test_fetch_meta_refresh_to_private_url_fails_closed`
- `test_fetch_meta_refresh_treats_redirect_hop_as_visited`

redirect/meta-refresh tests的网络行为断言不变；这里只同步 HTTP budget 参数。

**BrowserResourceBudget 直接签名/call 断裂：**

- `test_warmup_streams_only_budgeted_body_and_closes_response`
- `test_playwright_budget_preflight_uses_only_tree_walker_before_projection`
- `test_playwright_budget_rechecks_dynamic_full_projection_lengths`
- `test_playwright_full_text_failure_logs_debug_and_falls_back_to_html`

**Browser + Diagnostic 双参数/worker payload 断裂：**

- `test_playwright_budget_failure_projects_stable_tool_error`
- `test_challenge_confirmed_http_500_invokes_fallback_once`
- `test_playwright_public_direct_reports_typed_egress_policy_unavailable`
- `test_playwright_url_safety_error_survives_worker_process`
- `test_fetch_playwright_url_safety_projects_permission_denied`
- `test_fetch_playwright_cancel_projects_to_host_cancelled`
- `test_try_playwright_fallback_pre_cancel_does_not_start_playwright`
- `test_playwright_unpicklable_worker_fails_closed`
- `test_playwright_worker_process_cleanup_kills_synthetic_nested_child_on_posix`
- `test_playwright_worker_process_cleanup_supports_running_event_loop`
- `test_playwright_live_browser_cleanup_smoke_is_manual_and_best_effort`
- `test_fetch_playwright_fallback_receives_channel_and_storage_state_path`
- `test_fetch_playwright_fallback_uses_empty_storage_state_when_dir_empty`

这些 node 只同步 typed parameters / `_WorkerKwargs` shape。现有 private-browser coupling、process cleanup、cancellation、channel/storage-state 和 availability assertions在 S1保持原样；不得借签名更新改写成 S2 expected behavior。

#### `tests/tools/web/test_diagnose_web_access.py`（S1 drift 新增）

- 模块顶层 `from ...web_resource_budget import WebResourceBudget` 会直接 import 失败。
- import 必须改为 `HttpResourceBudget`；不得保留旧符号 alias/re-export，也不需要导入 Browser/Diagnostic 类型。
- `test_playwright_response_body_projection_uses_exact_bytes_and_budget` 当前构造 `WebResourceBudget(decoded_body_bytes=4)` 并传给 `_read_bounded_playwright_response_body`；应改为显式完整测试值 `HttpResourceBudget(wire_body_bytes=4, decoded_body_bytes=4)`，三次调用仍以同一个 typed HTTP budget 验证 exact bytes、declared 超限与 actual 超限。
- 除这一个 direct budget test 与 import 外，不授权修改 lifecycle、storage-state、CLI 或 diagnostic artifact tests。

## 6. 纯 S1 budget-type migration 与禁止提前的行为边界

| 允许在修正后 S1 执行 | 必须留在 S2/S3 |
|---|---|
| 删除旧 import/type annotation/flat helper | `_send_authorized_request` 新增 transport policy 参数 |
| aggregate 只存在于 `WebToolsConfig` snapshot | standard vs pinned transport 分支 |
| projection 为 Http / Browser / Diagnostic 显式参数 | `trust_env`、environment proxy selection/warning |
| HTTP body helper 只接 `HttpResourceBudget` | proxy + peer-proof incompatibility |
| warmup/DOM/text 只接 `BrowserResourceBudget` | search provider raw `requests` sender迁移 |
| diagnostic error projection 只接 `DiagnosticResourceBudget` 或其显式 `error_chars` | 删除 browser/private coupling |
| probe 删除未使用的 budget 参数 | `browser_enabled` capability gate |
| worker/process typed payload拆开 browser 与 diagnostic | `browser_peer_proof_unavailable` 与 process-start gate |
| tests仅同步类型、参数、nested schema与既有行为断言 | browser proxy env、route/navigation行为修改 |
| utility 只拆旧 budget direct usages | S3 storage lifecycle/CLI/writer/profile schema删除或改造 |

必须冻结的 S1 非行为不变量：

- `_send_authorized_request` 的签名与 pinned/no-proxy 行为完全不变；
- `web_search_providers.py` 的三个模块级 `requests.get/post` 完全不变；
- `web_playwright_backend.py` 的 `allows_private_network` 前置 return、Playwright import、process start、route/nav 与 error reasons完全不变；
- `utils/diagnose_web_access.py` 的 storage lifecycle、CLI、ordinary writer 与 diagnostics schema完全不变；
- redirect、mixed DNS、dangerous/private/custom policy、challenge detection、cancellation 与 resource-limit算法不因类型拆分改变。

## 7. 对 Controller 的 plan gate 裁决请求

建议 Controller 重新打开 accepted plan gate，并精确修正 S1 allowlist/changed-file table：

1. 把 §4.2 / §8.1 的“删除旧类型、所有 consumer 同步、无 dual schema”保持不变；不要推迟删除或引入 compatibility facade。
2. 把 §4.2-§4.3、§6.1-§6.3、§8.2-§8.4、§14.1 与 tests/coverage commands 对齐到本 artifact 的四文件最小 drift 增量。
3. 为 `web_fetch_orchestrator.py`、`web_playwright_backend.py` 明确 S1 只授权 budget type migration，S2 行为仍禁止。
4. 为 `utils/diagnose_web_access.py`、`test_diagnose_web_access.py` 明确 S1 只授权 direct old-type removal；S3 lifecycle/CLI仍禁止。
5. 明确裁决 `_DEFAULT_DIAGNOSTIC_ERROR_CHARS=1024` 与 `DiagnosticResourceBudget.events` 的时序：是作为 S1 backend-default 同源要求前移，还是明确保留到 S3。不得让 implementation agent自行推导。
6. plan fix 后重新执行两路完整 plan re-review，再产生新的 accepted-plan commit；当前 `6e2a76b3` 不再是可直接实施的 S1 truth。

## 8. 本轮 diff、命令证据与 handoff

### 8.1 AgentCodex authored diff

唯一 authored 文件：

- `docs/reviews/wu-semantic-ownership-01-r02-web-owner-policy-s1-plan-drift-codex.md`

先前临时写入的 `...-implementation-s1-codex.md` 已删除且不沿用。AgentCodex 未修改 accepted plan、control、产品、测试、README 或既有 artifact。

工作区中的 `docs/host/issues-implementation-control.md` gate/next-entry diff 是 Controller 在本 follow-up 期间写入的既有外部变更；本文只读核对，未修改或回退。

### 8.2 已执行的 read-only 命令与结果

| 命令 | 结果 |
|---|---|
| `git branch --show-current` | `phaseflow/host-issues-control` |
| `git rev-parse HEAD` | `4d2df7036367ec51891d893dcba42a468e3a921d` |
| `git diff --name-only 6e2a76b3..4d2df703 --` | 仅 accepted-plan 后的 control entry commit，无产品代码 drift |
| `rg -l '\bWebResourceBudget\b' dayu tests utils | sort` | 精确九文件闭集，见 §2 |
| `rg -n '\.(wire_body_bytes\|decoded_body_bytes\|warmup_body_bytes\|browser_dom_chars\|browser_text_chars\|diagnostic_error_chars\|diagnostic_events)\b' dayu tests utils` | 直接字段读取只落在 owner、fetch orchestrator、Playwright backend、web_tools diagnostic default 与 diagnostic utility decoded body |
| 逐符号 `nl -ba` / `rg` 审计 | 确认 §3/§5 列出的 signatures、TypedDict payload、field reads 与 tests |
| `pyrightconfig.json` 读取 | `include = ["dayu", "tests", "utils"]`，证明 utility/test 不能延迟到 S3 |
| `git diff --no-index --stat /dev/null <artifact>` | 仅本 evidence artifact 的新增 diff；退出码 1 是 no-index 检测到差异的预期语义 |
| `git diff --no-index --check /dev/null <artifact>` | 无输出；artifact 无 whitespace error（退出码 1 仅表示存在新增 diff） |
| `git diff --check` | 退出码 0、无输出 |
| `git status --short` | 仅 Controller-owned control diff 与本 evidence artifact；无产品、测试、README、accepted plan 或既有 artifact diff |

本轮不运行 pytest、coverage 或 pyright：没有实施代码，运行旧 baseline 不能验证修正后的 slice；Controller 已要求退回 plan gate。artifact 完成后只执行 whitespace、唯一 authored path 与 final status 检查。

### 8.3 Handoff

等待 Controller 重新裁决 plan gate。不得基于本文直接实施、commit、更新 control、开始 code review 或进入 S2；必须先由 Controller 修正 plan，再完成两路完整 re-review 与新的 accepted-plan commit。
