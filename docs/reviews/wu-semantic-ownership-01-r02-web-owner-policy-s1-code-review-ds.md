# WU-SEMANTIC-OWNERSHIP-01 / R02-S1 第二路完整 Code Review — AgentDS

## Scope

- **Mode**: current changes (not a new WU, not authorized to implement or commit)
- **Branch**: `phaseflow/host-issues-control`
- **Base**: `70ffc917`（R02-S1 entry commit）
- **Output file**: `docs/reviews/wu-semantic-ownership-01-r02-web-owner-policy-s1-code-review-ds.md`
- **Review date**: 2026-07-15
- **Included scope**: 全部 changed production (9)、config (1)、utility (1)、tests (3)、README (2)，共 16 个 tracked files；以及 `AGENTS.md`、R02 plan、Controller validation artifact、implementation codex、controller discussion Topic 2/9
- **Excluded scope**: 无（Controller-owned `docs/host/issues-implementation-control.md` dirty path 和 Controller validation artifact 为进入本轮前已存在的只读文件，不在审查范围内）
- **Parallel review coverage**: 无（单路完整走读）

## Verdict

**PASS-WITH-RISKS** — 无 blocking finding。S1 owner contract 拆分完整、parser/default/propagation 链路一致、所有 ordinary/browser failure 均消费当前 Diagnostic owner、security/egress/redirect/challenge 防御机制完整保留、无 S2/S3/Issue178/R03 越界实现。存在两个 non-blocking observation 涉及测试 docstring 合规和小额 cap suffix 可观测性，不阻塞进入双路 code review gate。

---

## Findings

### R02-S1-DS-F01 — LOW — 测试新增嵌套函数缺少完整中文 docstring（non-blocking observation）

- **入口/函数**: `test_ordinary_fetch_failure_matrix_keeps_config_diagnostic_owner` 内的 `fail_fetch`、`controlled_browser_fallback`；`test_fetch_http_budget_success_paths_keep_html_and_non_html_semantics` 内的 `unexpected_non_html`、`unexpected_html`、`convert_pdf`；`test_http_child_budget_owns_declared_length_and_bounded_codec_failures` 内的 `missing_optional_module`
- **文件(行号)**:
  - `tests/tools/web/test_web_tools_provider.py:355-430`（`fail_fetch`、`controlled_browser_fallback` 虽有 docstring 但 `controlled_browser_fallback` 的 Args 节不完整：声明了 12 个参数但只描述了行为意图，未逐参数说明）
  - `tests/tools/web/test_web_tools_provider.py:3748-3752`（`unexpected_non_html`：仅一行 "拒绝 HTML case 意外进入 non-HTML converter。"，缺 Args/Returns/Raises）
  - `tests/tools/web/test_web_tools_provider.py:3757-3762`（`unexpected_html`：仅一行，缺 Args/Returns/Raises）
  - `tests/tools/web/test_web_tools_provider.py:3767-3771`（`convert_pdf`：仅一行 "返回确定性 non-HTML owner conversion 结果。"，缺 Args/Returns/Raises）
  - `tests/tools/web/test_web_tools_provider.py:4184-4188`（`missing_optional_module`：仅一行 "模拟缺少可执行有界解码的 optional codec。"，缺 Args/Returns/Raises）
  - `tests/tools/web/test_diagnose_web_access.py:616-622`（`fake_build_requests_profile`：仅一行 "在 utility policy construction boundary 验证 custom-port 授权。"，缺 Args/Returns/Raises）
- **输入场景**: 无特定触发输入；静态代码审查即可发现。
- **实际分支**: 不适用（文档合规问题，非运行时分支）。
- **预期行为**: `AGENTS.md` 编码硬约束要求 "函数必须提供完整中文 docstring，至少包含参数、返回值、异常"。
- **实际行为**: 上述 7 个嵌套函数/方法仅有一行摘要式 docstring，未逐参数、返回值、异常说明。
- **直接证据**: 上述行号处直接可见的 docstring 文本。
- **影响**: 不影响运行时正确性。影响代码可维护性和 `AGENTS.md` 合规。测试代码虽为辅助性质，但 `AGENTS.md` 的 docstring 硬约束未对测试代码设豁免。
- **建议改法和验证点**:
  1. 为上述 7 个函数补全 Args/Returns/Raises 中文 docstring。
  2. 对语义简单的拒绝型 helper（如 `unexpected_non_html`、`unexpected_html`、`missing_optional_module`），可缩减为模块级私有函数以同时消除嵌套函数问题。
  3. 验证：`rg -n "^    def " tests/tools/web/test_web_tools_provider.py tests/tools/web/test_diagnose_web_access.py` 全部新增嵌套函数均有完整中文 docstring。
- **修复风险（低）**: 机械补文档零风险；缩减嵌套函数为模块级需确保闭包捕获的状态（如 `active_browser_escalation`）有等价传递方式。
- **严重程度（低）**: 不阻塞 S1 gate；测试正确性不受影响。

### R02-S1-DS-F02 — LOW — `project_error_message` 极小正整数 cap 静默省略 suffix，降低诊断可观测性（non-blocking observation）

- **入口/函数**: `project_error_message` → `truncate_diagnostic_text`
- **文件(行号)**: `dayu/tools/web/web_diagnostics.py:435-444`
- **输入场景**: 当 config `diagnostics.error_chars` 设置为 ≤ `len(_ERROR_TRUNCATION_SUFFIX)`（即 ≤ 15）的正整数时，例如 `error_chars=5`。
- **实际分支**: 第 437-439 行的三元表达式 `_ERROR_TRUNCATION_SUFFIX if max_chars > len(_ERROR_TRUNCATION_SUFFIX) else ""` 在 `max_chars <= 15` 时返回空 `truncated_suffix`，`truncate_diagnostic_text` 收到空 suffix 后执行截断但不附加任何截断标记。
- **预期行为**: 任何有界截断都应产生可观测的截断标记，使下游（日志、diagnostics artifact 消费者）能区分"完整错误文本"和"已被截断"。
- **实际行为**: 当 cap 在 [1, 15] 范围内且实际错误文本超过 cap 时，`error_message` 被静默截断——消费者无法从消息本身判断它是完整文本还是被截断。cap ≥ 16 时行为正常（附加 `...<truncated>`）。
- **直接证据**: `web_diagnostics.py:437-439`：`truncated_suffix = _ERROR_TRUNCATION_SUFFIX if max_chars > len(_ERROR_TRUNCATION_SUFFIX) else ""`；`_ERROR_TRUNCATION_SUFFIX = "...<truncated>"`（长度 15）。
- **影响**: 低。极小正整数 cap 是极端配置场景（`error_chars=5` 主要出现在测试中），生产 packaged default 为 8192，且截断本身仍然正确执行（错误文本不超 cap）。仅诊断 artifact 的可读性受影响。
- **建议改法和验证点**:
  1. 将 suffix 行为改为：只要 `max_chars >= 1` 就附加至少一个可区分的截断标记（如 `…` 单字符），或始终让 `truncate_diagnostic_text` 自行决定是否附加其内置标记。
  2. 添加 owner-level test：`project_error_message("a" * 100, max_chars=5)` 返回的字符串长度 ≤ 5 且包含可观测的截断标记。
- **修复风险（低）**: 仅改变 suffix 的附加条件；`truncate_diagnostic_text` 的截断契约不变。
- **严重程度（低）**: 不阻塞 S1 gate。当前实现已满足 F01 的 owner-level 要求（parser 接受任意正整数，producer 不抛错）。本 observation 仅涉及截断可观测性边界改善。

---

## Adversarial Pass 逐项结论

### 巨幅 test diff 是否真正锁定 S1 owner contract / 是否仍有 coverage gaming/过耦合

**结论：S1 owner contract 已被有效锁定，无 coverage gaming。**

- 新增的 3217 行 test diff 在 F04 cleanup 后删除了四个无关 grouped helper 测试（storage/URL/scalar、meta-refresh internals、routing/stream-name heuristics、Playwright channel/storage/warmup），剩余新增 test functions 直接断言 owner 级 contract。
- 关键 S1 owner tests 包括：
  - `test_ordinary_fetch_failure_consumes_config_diagnostic_error_cap`（`error_chars=5` 控制 ordinary failure）
  - `test_ordinary_fetch_failure_matrix_keeps_config_diagnostic_owner`（7 种 failure + 1 种 success + 3 种 browser success 全部消费同一 Diagnostic cap）
  - `test_s1_budget_owner_signatures_and_worker_payload_are_closed`（`WebResourceBudgets` 无 default、`WebToolsConfig` 无 default、worker kwargs 只含 Browser、process wrapper 独立接 Diagnostic）
  - `test_packaged_web_config_matches_typed_policy_and_budget_defaults`（packaged JSON ↔ typed defaults 逐字段同源）
  - `test_web_policy_config_defaults_and_overrides_are_independent`（五 bool 独立解析，单 override 不影响其余四个 typed defaults）
  - `test_playwright_process_wrapper_keeps_diagnostic_budget_out_of_worker_kwargs`（Diagnostic budget 不进 worker kwargs）
  - `test_search_visibility_consumes_same_private_and_custom_port_policy`（search visibility 同源消费 typed egress policy）
  - `test_http_child_budget_owns_declared_length_and_bounded_codec_failures`（HttpResourceBudget 拥有 declared/decoded/codec bounds）
  - `test_playwright_worker_success_consumes_only_browser_budget`（Browser worker 只接 Browser budget）
  - `test_egress_custom_port_policy_is_independent_from_private_network_policy`（custom-port 与 private 独立决策）
- 三个文件 coverage 恰为 80%（`web_tools.py`、`web_fetch_orchestrator.py`、`web_playwright_backend.py`）。80% 门槛值属巧合，但所有 80% 文件均经过逐文件独立 `coverage report --include=<exact-file> --fail-under=80` 验证。新增 tests 覆盖的是 S1 实际改变的 child budget propagation 和 Diagnostic owner 路径，不是无意义的 line coverage padding。
- 新增 callables 全部使用精确 typed signature；added-line `lambda` / `**kwargs` / `type: ignore` / `hasattr` / `getattr` 扫描均为零。

**Residual risk**: `web_tools.py` 和 `web_playwright_backend.py` 在 80% 阈值线，S2 修改这些文件时必须重新逐文件验证覆盖率。

### web_diagnostics 的极小正整数 cap/suffix 行为

见 [R02-S1-DS-F02](#r02-s1-ds-f02---low----project_error_message-极小正整数-cap-静默省略-suffix降低诊断可观测性non-blocking-observation)。

### diagnostic utility 在 S1 临时把 private 投影到 custom-port

**结论：精确保留行为，未形成新 owner。**

- `utils/diagnose_web_access.py:2705-2707`：唯一新增的 policy construction 处：
  ```python
  egress_policy = WebEgressPolicy(
      allow_private_network=options.allow_private_network_url,
      allow_custom_port=options.allow_private_network_url,
  )
  ```
- pre-S1 行为：`WebEgressPolicy(allow_private_network=True)` 在 constructor default `allow_custom_port=False` 下会拒绝 custom port。但实际上 diagnostic utility 原本就传 `allow_private_network=options.allow_private_network_url` ，而 `WebEgressPolicy` 的旧实现将 custom-port 检查耦合在 `allow_private_network` 分支内——`allow_private_network=True` 时 custom-port 检查被跳过。因此 pre-S1 的实际行为是：private=true → custom-port 也允许。
- S1 新 `WebEgressPolicy` 拆分 private/custom-port 为独立字段后，若 utility 只传 `allow_private_network=True` 且不传 `allow_custom_port`（默认 `False`），custom-port 将被拒绝——这是 F02 发现的回归。
- F02 fix 将 `allow_custom_port` 也设为其 `allow_private_network_url` 同值，精确恢复了 pre-S1 行为：private=true → custom=true。
- 未新增 raw config parser、未新增 CLI 字段、未引入 S2 transport 或 S3 lifecycle。
- `test_single_diagnostic_private_mode_preserves_local_custom_port` 使用 `http://127.0.0.1:43117/fixture.pdf` 直接断言 port=43117 通过授权。

**Residual risk**: S1 期间 custom-port 无法在 diagnostic utility 中独立于 private 做差异化配置（必须同为 true 或同为 false）。这是 F02 fix 的设计意图（保留 pre-S1 行为），不是缺陷。S3 消费 typed Web config 时，utility 会直接读取 `config.allow_custom_port_url` 且不再需要此投影。

### 五 bool/三 child budgets 的 parser/default/propagation

**结论：链路完整一致。**

- **Parser（唯一 raw config owner）**: `provider._parse_config` 逐字段解析五 bool，缺失补 typed default，非 bool fail fast。`_resource_budgets_default` → `web_resource_budgets_from_json` 按 group/field 局部补 child owner default 且拒绝 unknown/invalid。
- **Snapshot**: `WebToolsConfig` 全字段无 default（F03），由 parser 唯一构造；transport_policy 保存 `WebHttpTransportPolicy(dns_peer_proof_enabled, allow_environment_proxy)`，resource_budgets 保存 `WebResourceBudgets` 纯组合。
- **Projection**: `_fetch_web_page_business` 只从 `config.resource_budgets.diagnostics.error_chars` 取得 diagnostic cap；`config.resource_budgets.http` → fetch/search body；`config.resource_budgets.browser` → warmup/browser worker。aggregate 不进入执行器。
- **Packaged ↔ typed conformance**: `test_packaged_web_config_matches_typed_policy_and_budget_defaults` 逐字段断言同源。

**无缺陷。**

### 所有 ordinary/browser failure 是否使用当前 Diagnostic owner

**结论：全部使用，全局 fallback 已删除。**

- `_raise_fetch_failure` 的 `diagnostic_error_chars` 参数无 default（`inspect.Signature.empty`），test 确认（`test_raise_fetch_failure_accepts_only_owner_projection_inputs:203-204`）。
- 所有 15 处 `_raise_fetch_failure` call site（包括 URL normalization、redirect、timeout、HTTP/TLS、challenge、body limit、conversion、empty-content、browser terminal failure）均传入 `diagnostic_error_chars`。
- `_fetch_web_page_business:1962`：`diagnostic_error_chars = resource_budgets.diagnostics.error_chars` 从当前 config snapshot 取唯一真源。
- `_try_playwright_fallback:970,983` 的两处 browser failure 直接传入 `diagnostic_resource_budget.error_chars`。
- `web_tools.py` 内无 `_DEFAULT_WEB_DIAGNOSTIC_ERROR_CHARS` 或 `DEFAULT_DIAGNOSTIC_RESOURCE_BUDGET` 引用。

**无缺陷。**

### custom-port 与 private 是否独立

**结论：在 typed owner 边界独立，消费者正确使用独立字段。**

- `WebEgressPolicy.__init__` 接受独立的 `allow_private_network: bool` 和 `allow_custom_port: bool`。
- `authorize_http_target:331-332`：两个独立 `if` 分支分别检查 `self._allow_custom_port` 和 `self._allow_private_network`，不存在耦合。
- `is_url_allowed` 复用 `authorize_http_target`，同源。
- 生产调用处：`_search_web_business:1665-1668` 和 `_fetch_web_page_business:1965-1968` 均从 `config.allow_private_network_url` 和 `config.allow_custom_port_url` 独立投影。
- `test_egress_custom_port_policy_is_independent_from_private_network_policy` 使用独立 resolver 证明 custom-port deny 不影响 private allow 路径，反之亦然。

**无缺陷。**

### 是否越入 S2/S3/Issue 178/R03/统一 authorization

**结论：无越界。**

- `_send_authorized_request` 仍无 `transport_policy` 参数，继续 `trust_env=False`、`proxies={}`、numeric pin/no-proxy。
- `web_search_providers.py` 仍使用三处模块级原始 `requests.post` / `requests.get`。
- `web_playwright_backend.py:1411,1597` 的两个 `allows_private_network` 前置 return 仍在，browser/private coupling 保留。
- `utils/diagnose_web_access.py` 的 lifecycle/reconcile/publish/permission 全链未删除（S3），`_DEFAULT_DIAGNOSTIC_ERROR_CHARS = 1_024` 和 `--max-network default=80` 保留。
- `web_challenge_detection.py` 零 diff。
- `authorization framework|policy DSL|capability token|Issue #178|R03` 对 `dayu utils tests README` 扫描零命中。

**无缺陷。**

### README 是否准确表达 snapshot-only 时序

**结论：准确。**

- `dayu/config/README.md` 明确写："当前 S1 只把 `dns_peer_proof_enabled`、`allow_environment_proxy` 与 `browser_enabled` 保存为不可变 typed snapshot；HTTP sender 仍保持既有 numeric pin / no-proxy 行为，browser backend 也保持既有 private-policy coupling。配置文档因此不把这些新字段描述成已经生效的 transport 或 browser 执行分支。"
- `tests/README.md` 明确写："S1 还锁定 sender 继续使用既有 numeric pin / no-proxy、search providers 继续使用模块级 raw `requests.get/post`、browser/private coupling 不变"。
- 读者不会误以为五 bool 已在 S1 全部生效为执行分支。

### 安全机制是否误删

**结论：未误删任何安全机制。**

- URL/scheme/host/port/DNS resolution 的 dangerous/unspecified/multicast/private deny 均在 `WebEgressPolicy.authorize_http_target` 保留。
- mixed DNS fail closed 保留（`authorize_http_target:353-370`：逐个地址按 profile 检查，任一不通过整组拒绝）。
- numeric pin/peer proof 在 `_send_authorized_request` 仍然生效（S1 未改签名）。
- redirect 逐 hop re-authorization 保留（`web_fetch_orchestrator.py` 无 S1 diff 改变 redirect 逻辑）。
- response lease/transport cleanup 保留。
- header/cookie/URL/query redaction 和 containment/symlink 防御保留。
- `web_challenge_detection.py` 零 diff。

---

## Open Questions

1. **Coverage 阈值的可持续性**：`web_tools.py`（80%）、`web_fetch_orchestrator.py`（82%）、`web_playwright_backend.py`（80%）均在最低线。这三个文件是 S2 的主要修改目标——S2 新增 transport policy threading、browser/private decoupling、proxy/proof 分支时，需要额外新增 owner-level tests 才能维持 ≥80%。当前无证据表明 S2 的 coverage 会自然达标。不是 S1 缺陷，但建议在 S2 plan 中预估所需测试的体量。

2. **Diagnostic utility 的 `_DIAGNOSTIC_HTTP_RESOURCE_BUDGET` / `_DIAGNOSTIC_BROWSER_RESOURCE_BUDGET` 常量**：在 `utils/diagnose_web_access.py` 中，S1 将这两个常量改为直接引用 `DEFAULT_HTTP_RESOURCE_BUDGET` / `DEFAULT_BROWSER_RESOURCE_BUDGET`（`is` 同源已在 test 中断言）。但 `_DEFAULT_DIAGNOSTIC_ERROR_CHARS = 1_024` 仍然是独立本地常量，值为 `1_024`，而 `DEFAULT_DIAGNOSTIC_RESOURCE_BUDGET.error_chars = 8_192`。S3 计划将此值同源到 typed diagnostic config——这是已登记的时序，不是 S1 缺陷。

---

## Residual Risk

1. **test_ordinary_fetch_failure_matrix 的脆弱性**：该测试使用 `queued_results.pop(0)` 按顺序消费 11 个预设结果，依赖 `_fetch_web_page_business` 内部 warmup→probe→fetch→post-fetch challenge→empty-content 的精确执行顺序。若 S2 重构 fetch pipeline 阶段顺序，此测试的预设队列需要对应更新，但它在 S1 作为 owner contract 锁定测试的价值大于其脆弱性成本。

2. **Synthetic Playwright test doubles 的规模**：新增了 `_SyntheticPlaywrightResponse`、`_SyntheticPlaywrightPage`（~140 行）、`_SyntheticPlaywrightContext`、`_SyntheticPlaywrightBrowser`、`_SyntheticHtmlPipelineResult`、`_SyntheticProcessPlaywrightWorker` 共六个 test double 类，用于覆盖 browser worker success/failure/budget/projection 路径。这些 double 精确实现 Playwright Protocol 的子集，但若 Playwright API 升级导致 Protocol 变化，需同步更新。当前 double 覆盖的是 S1 的 Browser/Diagnostic budget 传播，不是 browser 内部行为——耦合风险可控。

3. **`web_tools.py:80%` 阈值下未覆盖路径的可能面积**：80% 意味着 ~400 行（文件约 2000 行）未被测试覆盖。这些未覆盖区域主要是哪些？若包含 challenge detection 内部路径、Docling wrapper、或 SEC-specific header builder，它们属于 S2/S3 范围，在 S1 不覆盖是合理的。但建议在 S2 entry 前做一次 uncovered-line audit 确认无 S1 owner contract 遗漏。
