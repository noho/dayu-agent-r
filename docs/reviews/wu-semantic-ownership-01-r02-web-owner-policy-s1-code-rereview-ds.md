# WU-SEMANTIC-OWNERSHIP-01 / R02-S1 第二路完整 Code Re-Review — AgentDS

## Scope

- **Mode**: current changes（不是新 WU，不实施、不 commit）
- **Branch**: `phaseflow/host-issues-control`
- **Base**: `70ffc917`（R02-S1 entry commit）→ 当前 final working tree（含两轮 Controller validation 和 AgentCodex fix）
- **Output file**: `docs/reviews/wu-semantic-ownership-01-r02-web-owner-policy-s1-code-rereview-ds.md`
- **Review date**: 2026-07-15
- **Included scope**: 全部 changed production（9）、config（1）、utility（1）、tests（3）、README（2），共 16 个 tracked files；以及 AGENTS.md、accepted R02 plan、MiMo/DS initial code reviews、Controller adjudication、AgentCodex fix artifact、两轮 Controller validation artifacts、implementation artifact
- **Excluded scope**: Controller-owned `docs/host/issues-implementation-control.md` dirty path（只读）；plan drift artifacts（R02-S1 早期 gate，不在当前 re-review scope）
- **Parallel review coverage**: 无（单路完整走读，但使用 Explore subagent 对 4278 行 test diff 做结构化提取后逐项复核）

## Verdict

**PASS** — 无 blocking finding。`R02-S1-CR-F01`（顶层 12-field unknown fail-fast）、`R02-S1-CR-F02`（added-definition 与 signature-touched docstring 闭合）、`R02-S1-CR-F03`（cap=1/14/15 有界显式 marker）与 `R02-S1-CR-CV-F01`（14 个 signature-touched definitions 补齐文档）均已关闭且经本 re-review 独立逐行验证。Owner propagation 全链路正确、test quality 无 coverage gaming、全部 retained DNS/redirect/peer/containment/challenge 安全机制完好、S2/S3/Issue 178/R03/统一 authorization 边界未越界。

Controller final evidence（249 passed, 1 skipped、九文件 80%-100% 总 84%、pyright 0、signature_touched=132 issues=0）与本 re-review 独立走读结论一致：当前 working tree 可以进入 Controller accepted-slice commit 流程。

---

## 旧 Finding 最终状态

| Finding ID | 来源 | 状态 | 验证证据 |
|---|---|---|---|
| R02-S1-CR-F01 | Controller adjudication (accepted) | **closed** | `_CONFIG_FIELDS` 精确 12-field frozenset（`provider.py:41-56`）；unknown field 在读取任何字段前通过 `min(unknown_fields)` 拒绝并报 `web provider config.<field>` 精确路径（`provider.py:109-114`）；legal partial `{"provider": "duckduckgo", "resource_budget": {"http": {"wire_body_bytes": 17}}}` 正确补全 11 个 missing field/group 的 typed defaults（test line 4563-4582）；ConfigLoader record-replace 既有 tests 不变 |
| R02-S1-CR-F02 | Controller adjudication (accepted) | **closed** | 最终 added-definition AST scan: 89 definitions / 0 issues；Controller follow-up 将闭集扩展为 signature-touched: 132 definitions / 0 issues；14 个 CV-F01 缺口已逐项补齐中文 Args/Returns/Raises；closure-free nested helpers=0（全部提升为模块级）；added-line `lambda`/`**kwargs`/`type: ignore`/`hasattr`/`getattr` 扫描零命中 |
| R02-S1-CR-F03 | Controller adjudication (accepted) | **closed** | `project_error_message` owner boundary 修复（`web_diagnostics.py:436-454`）：cap=1 且截断→`…`；cap=2..14→`…` minimal marker；cap>14→完整 `...<truncated>`；未超限文本原样返回；`dayu.runtime.diagnostic_text.truncate_diagnostic_text` 公共 contract 零 diff；schema `web-diagnostics-v2`/revision 2/redaction/payload 零 diff；direct tests 锁定 cap=1/14/15 与未超限无误报（test line 228-248） |
| R02-S1-CR-CV-F01 | Controller fix validation (accepted) | **closed** | 14 个 precise signature-touched definitions（`_fetch_and_convert_content`×3、`_fetch_and_convert_with_playwright`、`test_playwright_budget_failure_projects_stable_tool_error`、`_SyntheticNestedPlaywrightWorker.__call__`、`_LiveBrowserLongRunningWorker.__call__`、`_BlockedPlaywrightWorker.__call__`、`_SyntheticProcessPlaywrightWorker.__call__`、`unexpected_worker`、`fake_fetch_and_convert_with_playwright`×3、`fake_worker`、browser fallback fakes×2）只补参数/返回值/异常文档；签名、行为、test flow、owner placement 未变；final scan signature_touched=132 issues=0 |

MiMo Finding 02（design confirmation / no fix）与 MiMo Finding 03（positive-cap 不抛错结论保留但"无 suffix 也正确"的 disposition 被 F03 覆盖）：**维持 Controller adjudication 原判**。

Accepted observations（coverage 位于 80% 门槛、S2/S3 增量风险、S1 utility 临时投影、测试队列顺序与 synthetic doubles 规模）：**仍为 observation，无需 product fix**。Provider 顶层 unknown 不授权 schema DSL 或跨 provider framework。

---

## 新 Material Findings

**无新 material finding。** 以下为 observations（非 defect，不阻塞 gate）：

### OBS-01 — 顶层 unknown field 与 nested group unknown fields 的报错颗粒度不一致（observation）

- **入口/函数**: `provider._parse_config` vs `web_resource_budget._parse_group`
- **文件(行号)**: `provider.py:109-114` vs `web_resource_budget.py:223-230`
- **输入场景**: config 同时包含多个拼写错误的顶层字段，或 nested group 同时包含多个非法字段
- **实际分支**: 顶层使用 `min(unknown_fields)` 只报第一个（按字母序），nested group 使用 `sorted(actual_fields - allowed_fields)` 报全部
- **预期行为**: 两处均为 unknown/invalid fail fast，行为正确
- **实际行为**: 顶层只报一个字段，nested group 报全部字段；操作者修复第一个 typo 后才看到第二个，多一轮迭代
- **直接证据**: `provider.py:111`: `unknown_field = min(unknown_fields)` → 单字段报错；`web_resource_budget.py:228`: `unknown_fields = sorted(...)` → 全字段报错
- **影响**: 极低。config 为项目自控，typo 数量有限；迭代修复成本可忽略
- **严重程度**: observation（非 defect）
- **建议**: 后续 slice 可将顶层也改为 `sorted()` 统一风格；当前不必修

### OBS-02 — `_bool_default` 与 `_positive_float`/`_positive_int` 在 `field_name not in config` guard 后取值方式不一致（observation）

- **入口/函数**: `provider._bool_default` vs `provider._positive_float` / `provider._positive_int`
- **文件(行号)**: `provider.py:298-303` vs `provider.py:243-248` / `provider.py:270-275`
- **输入场景**: 无特定触发输入；静态审查
- **实际分支**: `_bool_default` 在 guard 后使用 `config[field_name]`（直接键访问）；`_positive_float` 和 `_positive_int` 在 guard 后使用 `config.get(field_name)`（带 None fallback 的 `.get`）
- **预期行为**: 两种写法在 guard 确保 key 存在后语义等价
- **实际行为**: 语义等价，仅风格不一致
- **直接证据**: `provider.py:300`: `value = config[field_name]`；`provider.py:245`: `value = config.get(field_name)`；`provider.py:272`: `value = config.get(field_name)`
- **影响**: 无运行时影响；仅代码阅读时产生轻微不一致感
- **严重程度**: observation（非 defect）
- **建议**: 后续 slice 统一为 `config[field_name]`（更精确表达"key 一定存在"的语义）；当前不必修

### OBS-03 — `_bool_default`/`_positive_float`/`_positive_int` 对显式 JSON `null` 的行为变更（observation）

- **入口/函数**: `provider._bool_default` / `provider._positive_float` / `provider._positive_int`
- **文件(行号)**: `provider.py:278-303` / `provider.py:224-248` / `provider.py:251-275`
- **输入场景**: workspace overlay 中显式写入 `"allow_private_network_url": null`
- **实际分支**: 旧实现 `config.get(field_name); if value is None: return default` → null 被当作缺失，静默返回 default；新实现 `if field_name not in config: return default` → null 触发 key 存在但值非 bool/int/float，raise `ValueError`
- **预期行为**: 按 plan §8.2 "present values exact validate"，显式 null 应 fail fast 而非静默默认
- **实际行为**: 新行为正确（null 不是 bool，应被拒绝）；`test_web_policy_config_rejects_non_boolean_values` 已覆盖 `None` 作为非法输入
- **直接证据**: old `provider.py` at `70ffc917:238-240` → new `provider.py:298-303`
- **影响**: 无。packaged config 不含 null；test 已覆盖 null 拒绝；workspace overlay 中使用 null 表示"用默认"本就不是推荐做法
- **严重程度**: observation（非 defect）
- **建议**: 无需修改；若担忧向后兼容，可在 README 中说明 null 不等于缺失——但 packaged config 和现有 overlay 均无此模式，当前不必

---

## Adversarial Pass 逐项结论

### F01 — 顶层 12-field unknown fail-fast：owner 是否正确、是否破坏合法 partial/ConfigLoader record-replace

**结论：owner 正确，不破坏合法 partial 与 ConfigLoader record-replace。**

- `provider._parse_config` 是 final Web provider record 的唯一 raw JSON parser owner。`_CONFIG_FIELDS` 精确包含 12 个字段：4 个既有 scalar（`provider`、`request_timeout_seconds`、`max_search_results`、`fetch_truncate_chars`）、5 个 S1 bool（`allow_private_network_url`、`allow_custom_port_url`、`dns_peer_proof_enabled`、`allow_environment_proxy`、`browser_enabled`）、2 个 Playwright 字段（`playwright_channel`、`playwright_storage_state_dir`）和 nested `resource_budget`。
- Unknown 检测发生在读取任何字段之前（`provider.py:109-114`），不存在"读到一半才发现 unknown"的 partial state 问题。
- 每个 field parser（`_bool_default`、`_positive_float`、`_positive_int`、`_optional_text_default`、`_text_default`、`_parse_provider`、`_resource_budgets_default`）都独立处理 `field_name not in config → return default` 逻辑，因此合法 partial record 中缺失的字段会逐个按 typed default 补齐，已提供 sibling 保持不变。
- `_resource_budgets_default` 在 `resource_budget` key 缺失时传入空 dict `{}` 给 `web_resource_budgets_from_json`，后者按 group/field 两级局部补 child owner default。
- ConfigLoader record-replace 既有 tests 未修改（`tests/runtime/test_config_loader.py` 只新增了 5 bool 和 nested budget 的 packaged value assertion，record-replace 路径零 diff）。
- typo direct test（`test_web_provider_config_rejects_unknown_typo_and_keeps_partial_defaults`）同时验证：精确 12-field frozenset、typo 精确路径拒绝、合法 partial 补全 11 个 defaults。

**无缺陷。**

### F02 — added-definition 与 signature-touched current owner docs：是否真实闭合，test helper 模块级提取是否未改变行为/形成过耦合

**结论：真实闭合，模块级提取未改变行为且未形成过耦合。**

- **Added-definition 闭集**：最终 scan 89 definitions / 0 issues。每个新增 function/method/nested fake/test function 均有中文 docstring 并包含参数、返回值、异常说明。AST 逐项校验显式参数具有类型注解、在 docstring 中出现、返回类型存在。
- **Signature-touched 闭集**：Controller CV-F01 用 AST 将 `git diff -U0 70ffc917` 的 added lines 与 function signature span 相交，得到 132 个 signature-touched definitions。14 个缺口（3 个 production `_fetch_and_convert_content`/`_fetch_and_convert_with_playwright` + 11 个 test fake/worker）已补完整中文文档，只补文档不改变签名/行为/test flow/owner placement。最终 scan signature_touched=132 issues=0。
- **模块级提取**：所有无状态且不捕获 closure 的新增 nested helper 已提升为模块级私有 helper。本 re-review 独立统计确认 closure_free_added_nested_helpers=0。捕获 case-local queue、recorder、browser 或 budget 的 nested fake 保留嵌套（如 `fail_fetch` 在 `test_ordinary_fetch_failure_matrix_keeps_config_diagnostic_owner` 内捕获 `queued_results`）。
- **过耦合检查**：提取出的模块级 helpers（如 `_stable_owner_warmup`、`_stable_owner_probe`、`_convert_expected_fetch_html`、`_reject_non_html_conversion`、`_convert_expected_pdf`、`_raise_missing_optional_zstd`、`_import_identity_zstd` 等 22 个）每个都是精确窄类型的独立工厂，不共享可变状态、不依赖 fixture、不引入 god builder。
- **Added-line 扫描**：lambda=0、`**kwargs`=0、无注解参数/返回=0、`type: ignore`/`hasattr`/`getattr`=0。
- 未触及 baseline 旧 docstring/lambda 债务。

**无缺陷。**

### F03 — cap=1/14/15 marker：是否有界、显式且不改 schema/revision/redaction/runtime primitive

**结论：有界、显式、未改 schema/revision/redaction/runtime primitive。**

- `project_error_message` owner boundary 修复（`web_diagnostics.py:436-454`）：
  - `max_chars == 1` 且截断 → 返回 `_MINIMAL_ERROR_TRUNCATION_MARKER = "…"`（单字符明确标记）
  - `max_chars == 1` 且未截断 → 返回原 single char
  - `1 < max_chars <= 14` → 使用 `"…"` minimal marker，由 `truncate_diagnostic_text` runtime primitive 保证有界
  - `max_chars > 14` → 使用完整 `"...<truncated>"`（length 14），保持既有 behavior
  - 脱敏先完整执行（line 428-435）
- `dayu/runtime/diagnostic_text.truncate_diagnostic_text` 公共 contract 零 diff（本 re-review 独立读取 `dayu/runtime/diagnostic_text.py:75-96` 确认）。
- Schema/revision/redaction/payload 零 diff（`WEB_DIAGNOSTIC_SCHEMA_VERSION = "web-diagnostics-v2"`、`WEB_DIAGNOSTIC_SCHEMA_REVISION = 2`、`_ERROR_REDACTION_MARKER` 均未变）。
- Direct tests 锁定：
  - cap=1: `project_error_message("xx", max_chars=1) == "…"`（test line 241）
  - cap=14: `project_error_message("x" * 15, max_chars=14) == "x" * 13 + "…"`（line 242-244）
  - cap=15: `project_error_message("x" * 16, max_chars=15) == "x...<truncated>"`（line 245-247）
  - 未超限: `project_error_message("short", max_chars=14) == "short"`（line 248）

**无缺陷。**

### R02-S1-CR-CV-F01 — signature-touched definitions 文档补齐闭合状态

**结论：已闭合。** 14 个 precise definitions 只补中文 Args/Returns/Raises 与当前 HTTP/Browser/Diagnostic/cancellation 参数说明；签名/函数体/test flow/owner placement 未变。Controller independent re-validation 确认 signature_touched=132 issues=0。本 re-review 独立抽查了 `_fetch_and_convert_content`（`web_fetch_orchestrator.py`）、`_SyntheticProcessPlaywrightWorker.__call__`（test line ~7500+）、`fake_fetch_and_convert_with_playwright`（test 三处），均已有完整文档。

**无缺陷。**

### Owner propagation 全链路

**结论：全链路正确，无断裂。**

- **Parser → Snapshot**: `tool_discovery.json → provider._parse_config → WebToolsConfig` 唯一构造链。`WebToolsConfig` 全字段无 default（F03），parser 是唯一构造 owner。`WebResourceBudgets` 无 default、无 `__post_init__`、无 flattened property。Production `WebToolsConfig(` 扫描只命中 `provider._parse_config` 一处。
- **Snapshot → Execution**: `_fetch_web_page_business` 从 `config.resource_budgets.diagnostics.error_chars` 取 diagnostic cap；`config.resource_budgets.http` → `_FetchConvertKwargs.http_resource_budget`；`config.resource_budgets.browser` → `_WarmupFetchKwargs.browser_resource_budget` 和 `_PlaywrightFallbackKwargs.browser_resource_budget`。aggregate `WebResourceBudgets` 不进入执行器。
- **Failure projection**: `_raise_fetch_failure` 的 `diagnostic_error_chars: int` 无 default（`inspect.Signature.empty` 已在 test 断言，line ~203-204）。全部 15 个 call site（URL normalization、redirect、timeout、HTTP/TLS、challenge、body limit、conversion、empty-content、browser terminal failure）显式传入当前 owner field。
- **Probe 无 budget**: `_probe_content_type` 签名已移除 `resource_budget`（`web_tools.py:1167-1198`），probe 只读 headers 不消费 body budget。
- **Browser worker**: worker kwargs（`_WorkerKwargs`）只含 `browser_resource_budget: BrowserResourceBudget`，不含 `diagnostic_resource_budget`。`_run_playwright_worker_process` 独立接收 `diagnostic_resource_budget: DiagnosticResourceBudget` 用于 process/failure 投影。
- **Search**: `_search_web_business` 直接构造 `WebEgressPolicy(allow_private_network=..., allow_custom_port=...)` 传入 `search_public_web`；搜索 provider 内部使用 `http_resource_budget` 做 wire/codec 限制。
- **Utility**: `utils/diagnose_web_access.py` 的 `_DIAGNOSTIC_HTTP_RESOURCE_BUDGET` 和 `_DIAGNOSTIC_BROWSER_RESOURCE_BUDGET` 通过 `is` 同源于 `DEFAULT_HTTP_RESOURCE_BUDGET` / `DEFAULT_BROWSER_RESOURCE_BUDGET`（已在 test 中断言，line ~836-837）。

**无缺陷。**

### Test quality / coverage gaming

**结论：无 coverage gaming。新增 tests 直接锁定 S1 owner contracts。**

- 20 个新增 test functions 全部直接断言 owner 级 contract：F01 的 unknown typo + partial defaults、F03 的 cap=1/14/15、budget owner signatures 闭包检查、HTTP child declared/codec bounds、browser worker success 只消费 browser budget、process wrapper 独立 diagnostic budget、egress custom-port vs private 独立决策、ordinary failure matrix 全部消费同一 config diagnostic cap 等。
- 三个 80% 门槛文件（`web_tools.py`、`web_fetch_orchestrator.py`、`web_playwright_backend.py`）的覆盖率均经过逐文件独立 `coverage report --include=<exact-file> --fail-under=80` 验证。新增覆盖的是 S1 实际改变的 child budget propagation 和 Diagnostic owner 路径，不是无意义的 line coverage padding。
- 无 `lambda` padding、无 `**kwargs` catch-all、无 `type: ignore` 绕过、无 `hasattr`/`getattr` 松解析。
- F04 cleanup 删除了四个无关 grouped helper tests（storage/URL/scalar、meta-refresh internals、routing/stream-name heuristics、Playwright channel/storage/warmup）。四个 Controller 指定的无注解 lambda 已替换为窄 typed helper（`_preserve_materialized_response_body`、`_private_loopback_resolver`、`_picklable_worker_predicate`、`_process_session_noop`）。
- Synthetic test doubles（`_SyntheticPlaywrightPage` ~140 行、`_SyntheticPlaywrightContext`、`_SyntheticPlaywrightBrowser`、`_SyntheticHtmlPipelineResult`、`_SyntheticProcessPlaywrightWorker`）精确实现 Playwright Protocol 的子集，覆盖 S1 的 Browser/Diagnostic budget 传播路径，不是 browser 内部行为。耦合风险可控。
- `test_ordinary_fetch_failure_matrix` 使用 `queued_results.pop(0)` 按顺序消费 11 个预设结果的模式有脆弱性（依赖 `_fetch_web_page_business` 内部执行顺序），但这在 S1 作为 owner contract 锁定测试的价值大于脆弱性成本。

**无缺陷。Observation: 80% 门槛文件的未覆盖面积需在 S2 entry 前做 uncovered-line audit（已在 DS initial review 中登记为 Residual Risk）。**

### Retained DNS/redirect/peer/containment/challenge 安全

**结论：全部安全机制保留，无误删。**

逐项本 re-review 独立确认：
- URL scheme/host/port 的 dangerous/unspecified/multicast deny: `WebEgressPolicy.authorize_http_target` 保留（`web_egress_policy.py:328-370`）
- Custom port 独立于 private network: `authorize_http_target:328` 检查 `self._allow_custom_port`，`authorize_http_target:331` 检查 `self._allow_private_network`，两个独立 `if` 分支
- Mixed DNS fail closed: `authorize_http_target:353-370` 逐地址按 profile 检查，任一不通过整组拒绝
- Numeric pin/peer proof: `_send_authorized_request` 签名未变（`web_http_session.py`），S1 未改此路径
- Redirect 逐 hop re-authorization: `web_fetch_orchestrator.py` redirect 逻辑零 S1 diff
- Response lease/transport cleanup: 保留
- Header/cookie/URL/query redaction: `web_diagnostics.py` redaction path 保留
- Containment/symlink defense: 保留
- Challenge detection/evidence: `web_challenge_detection.py` 零 diff
- Browser/private coupling: 两个既有 `allows_private_network` 前置 return 仍在（`web_playwright_backend.py`）

**无缺陷。**

### S2/S3/Issue 178/R03/统一 authorization 边界

**结论：无越界。**

逐项本 re-review 独立确认：
- `transport_policy` production 消费只在 `WebToolsConfig` snapshot 构造（`provider.py:145-148`）；`_send_authorized_request` 仍无该参数，sender 仍 `trust_env=False` / `proxies={}` / numeric pin
- `web_search_providers.py` 仍精确保留三处模块级 raw sender：两处 `requests.post`、一处 `requests.get`
- `web_playwright_backend.py` 仍精确保留两处 `allows_private_network` 前置 return
- `utils/diagnose_web_access.py` 的 storage lifecycle/reconcile/publish/permission、CLI、profile schema 保持；`_DEFAULT_DIAGNOSTIC_ERROR_CHARS = 1_024` 与 `--max-network default=80` 保持
- `authorization framework|policy DSL|capability token|storage state refresh|storage state retention|Issue #178|R03` 对 `dayu utils tests README` 扫描零命中

**无缺陷。**

### Custom-port 与 private 独立性

**结论：在 typed owner boundary 完全独立，消费者使用独立字段。**

- `WebEgressPolicy.__init__` 接受独立的 `allow_private_network: bool` 和 `allow_custom_port: bool`（`web_egress_policy.py:256-274`）
- `authorize_http_target` 两个独立 `if` 分支（line 328, 331）
- `is_url_allowed` 复用 `authorize_http_target`，同源
- 生产调用处（`_search_web_business:1662-1668`、`_fetch_web_page_business:1962-1968`）均从 `config.allow_private_network_url` 和 `config.allow_custom_port_url` 独立投影
- `test_egress_custom_port_policy_is_independent_from_private_network_policy` 使用独立 resolver 证明 custom-port deny 不影响 private allow 路径，反之亦然

**无缺陷。**

### Diagnostic utility S1 临时 private→custom-port 投影

**结论：精确保留行为，未形成新 owner。**

- `utils/diagnose_web_access.py:2705-2707`：`WebEgressPolicy(allow_private_network=options.allow_private_network_url, allow_custom_port=options.allow_private_network_url)` — 将既有 private/local 开关同时投影给两者
- 无新增 raw config parser、CLI 字段、S2 transport 或 S3 lifecycle
- `test_single_diagnostic_private_mode_preserves_local_custom_port` 用 `http://127.0.0.1:43117/fixture.pdf` 断言 port=43117 通过授权
- S3 从 typed config 消费两个独立值后此投影可删除

**无缺陷。**

### README 准确性

**结论：准确表达 snapshot-only 时序。**

- `dayu/config/README.md`：明确写 "当前 S1 只把 `dns_peer_proof_enabled`、`allow_environment_proxy` 与 `browser_enabled` 保存为不可变 typed snapshot；HTTP sender 仍保持既有 numeric pin / no-proxy 行为，browser backend 也保持既有 private-policy coupling"；五 bool 表格标注 "当前配置事实" 列说明 S1 执行状态；ConfigLoader record-replace 与顶层 unknown 精确拒绝关系已说明
- `tests/README.md`：同步记录 F01 typo direct test、F03 cap=1/14/15 owner contract、S1 sender/search/browser 时序保留
- 根 README、分层 README 正确 no-update（用户可见入口、分层装配未变）

**无缺陷。**

---

## Open Questions

无。

---

## Residual Risk

1. **80% 覆盖率门槛文件的 S2 可持续性**：`web_tools.py`（80%）、`web_fetch_orchestrator.py`（82%）、`web_playwright_backend.py`（80%）均在最低线。S2 新增 transport policy threading、browser/private decoupling、proxy/proof 分支时需要额外 owner-level tests 维持 ≥80%。建议在 S2 plan 中预估所需测试体量。

2. **Synthetic Playwright test doubles 的 Playwright API 耦合**：6 个 synthetic double 类（~200 行）精确实现 Playwright Protocol 子集。若 Playwright API 升级导致 Protocol 变化，需同步更新。当前 double 覆盖的是 S1 的 Browser/Diagnostic budget 传播，不是 browser 内部行为——耦合风险可控。

3. **`test_ordinary_fetch_failure_matrix` 的队列顺序依赖**：11 个 `queued_results.pop(0)` 依赖 `_fetch_web_page_business` 内部 warmup→probe→fetch→post-fetch challenge→empty-content 的精确执行顺序。S2 重构 fetch pipeline 阶段顺序时需对应更新此测试。

4. **`web_tools.py` 80% 未覆盖面积**：约 400 行未覆盖。若包含 challenge detection 内部路径、Docling wrapper 或 SEC-specific header builder，属于 S2/S3 范围；但建议在 S2 entry 前做一次 uncovered-line audit 确认无 S1 owner contract 遗漏。

5. **顶层 unknown field 报错只报一个字段**：OBS-01 记录的不一致。若操作者同时引入多个 typo，需多轮迭代修复。风险极低（config 为项目自控）。

---

## 验证证据汇总

| 项目 | 结果 |
|---|---|
| 完整允许三文件 suite | 249 passed, 1 skipped（唯一 skip 为既有条件式 smoke） |
| 九文件逐文件 coverage | provider 93%、diagnostics 92%、egress 86%、fetch orchestrator 82%、HTTP session 87%、Playwright backend 80%、resource budget 100%、search providers 87%、Web tools 80%；总计 84% |
| 完整 pyright | 0 errors, 0 warnings, 0 informations |
| `git diff --check` | 通过 |
| Added-definition AST scan | 89 definitions / 0 issues |
| Signature-touched AST scan | 132 definitions / 0 issues |
| Added-line loose callable scan | lambda=0、`**kwargs`=0、`type: ignore`=0、`hasattr`/`getattr`=0 |
| Legacy owner scan | `WebResourceBudget` 与七个 flat fields 零命中 |
| `_CONFIG_FIELDS` 闭集 | 12 field frozenset 精确匹配 |
| F01 typo direct test | `allow_prvate_network_url` → ValueError with exact path |
| F01 partial/default direct test | `{"provider": "duckduckgo", "resource_budget": {"http": {"wire_body_bytes": 17}}}` → 11 defaults filled |
| F03 cap=1 test | `project_error_message("xx", max_chars=1) == "…"` |
| F03 cap=14 test | `project_error_message("x" * 15, max_chars=14) == "x" * 13 + "…"` |
| F03 cap=15 test | `project_error_message("x" * 16, max_chars=15) == "x...<truncated>"` |
| F03 untruncated test | `project_error_message("short", max_chars=14) == "short"` |
| Runtime primitive diff | `dayu/runtime/diagnostic_text.py` 零 diff |
| Diagnostics schema diff | v2/revision 2/redaction/payload 零 diff |
| Challenge detector diff | `web_challenge_detection.py` 零 diff |
| S2 sender diff | `_send_authorized_request` 签名零 diff；sender 仍 trust_env=False/proxies={} |
| S2 search sender diff | 三处 raw `requests.get/post` 保留 |
| S2 browser/private coupling | 两处 `allows_private_network` 前置 return 保留 |
| S3 lifecycle diff | storage lifecycle/CLI/profile/writer 零 diff |
| Deferred scope scan | authorization framework/policy DSL/capability token/Issue #178/R03 零命中 |
| Closure-free nested helpers | 0（全部提升为模块级） |
