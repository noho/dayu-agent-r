# WU-SEMANTIC-OWNERSHIP-01 / R02-S1 第一路完整 Code Re-Review — AgentMiMo

## Scope

- **Mode**: current changes (不是新 WU，不实施、不 commit)
- **Branch**: `phaseflow/host-issues-control`
- **Base**: `70ffc917`（R02-S1 entry commit）
- **Output file**: `docs/reviews/wu-semantic-ownership-01-r02-web-owner-policy-s1-code-rereview-mimo.md`
- **Review date**: 2026-07-15 01:16
- **Included scope**: 全部 changed production (9)、config (1)、utility (1)、tests (3)、README (2)，共 16 个 tracked files；以及 `AGENTS.md`、R02 plan (`docs/host/wu-semantic-ownership-01-r02-web-owner-policy-plan.md`)、Controller validation artifact、implementation codex、controller adjudication、fix codex、fix controller validation，两路初始 code review artifacts
- **Excluded scope**: 无（Controller-owned `docs/host/issues-implementation-control.md` dirty path 为进入本轮前已存在的只读文件，不在审查范围内）
- **Parallel review coverage**: 无（单路完整走读）

## Review Baseline Context

- Accepted plan truth: `2d42ceb6` + `docs/host/wu-semantic-ownership-01-r02-web-owner-policy-plan.md` (946 lines)
- Controller validation: `docs/reviews/wu-semantic-ownership-01-r02-web-owner-policy-s1-controller-validation.md` — 4 findings (F01–F04) all closed
- Controller code review adjudication: `docs/reviews/wu-semantic-ownership-01-r02-web-owner-policy-s1-code-review-controller-adjudication.md` — 3 accepted findings (R02-S1-CR-F01..F03)
- AgentCodex fix artifact: `docs/reviews/wu-semantic-ownership-01-r02-web-owner-policy-s1-code-review-fix-codex.md`
- Controller fix validation: `docs/reviews/wu-semantic-ownership-01-r02-web-owner-policy-s1-code-review-fix-controller-validation.md` — FAIL → correction required
- Controller correction re-validation: same file §5 — PASS, signature_touched=132 issues=0
- Implementation artifact: `docs/reviews/wu-semantic-ownership-01-r02-web-owner-policy-s1-implementation-codex.md`
- Controller final evidence: 249 passed, 1 skipped; pyright 0; 9-file coverage 80%–100% 总 84%; signature_touched=132 issues=0

---

## 核心 Finding 验证

### R02-S1-CR-F01 — 顶层 12-field unknown fail-fast — **VERIFIED CLOSED**

**验证路径**:

1. `provider.py:41-56` 定义 `_CONFIG_FIELDS: Final[frozenset[str]]` 精确包含 12 个合法顶层字段：`provider`、`request_timeout_seconds`、`max_search_results`、`fetch_truncate_chars`、`allow_private_network_url`、`allow_custom_port_url`、`dns_peer_proof_enabled`、`allow_environment_proxy`、`browser_enabled`、`playwright_channel`、`playwright_storage_state_dir`、`resource_budget`。
2. `provider.py:109-114` 在读取任何字段前计算 `unknown_fields = set(config) - _CONFIG_FIELDS`；存在未知 key 时选择稳定字段名（`min(unknown_fields)`）并抛出 `ValueError(f"web provider config.{unknown_field} is not a supported field")`。
3. 实际验证：`_parse_config({"allow_prvate_network_url": False})` 抛出 `ValueError: web provider config.allow_prvate_network_url is not a supported field`。
4. 实际验证：`_parse_config({"provider": "duckduckgo", "resource_budget": {"http": {"wire_body_bytes": 17}}})` 成功，`provider="duckduckgo"`、`allow_private_network_url=True`（typed default）、`resource_budgets.http.wire_body_bytes=17`。
5. `_bool_default` (line 298-303) 从 `config.get()` + `if value is None` 改为 `if field_name not in config` + `config[field_name]`。这意味着 `null` 值现在会被 `isinstance(value, bool)` 检查拒绝（`null` 不是 `bool`），而非静默回退到 default。这符合 plan §4.1 "bool-as-null fail fast" 要求。
6. ConfigLoader record-replace contract 未修改：现有 `test_default_runtime_config_files_load_as_typed_views` 和 `test_config_loader_record_replace_does_not_deep_merge` 继续通过。
7. `_resource_budgets_default` (line 179-196) 保持 `web_resource_budgets_from_json({})` 全部补 typed default 的行为；未知 group/field 由 `web_resource_budget.py:_parse_group` (line 210-239) 精确拒绝。

**Owner 正确性**: 是。`_parse_config` 是唯一 raw JSON parser owner；`_CONFIG_FIELDS` 是 parser 自有的闭集；拒绝发生在 parser boundary，在读取任何字段之前。不破坏合法 partial record 或 ConfigLoader record-replace。

**结论**: closed，无遗留风险。

### R02-S1-CR-F02 — added-definition 与 signature-touched docs — **VERIFIED CLOSED**

**验证路径**:

1. Fix artifact 报告 `added_definitions=89 issues=0`（从初始 fix 的 86 增加到 89，因 docstring 修复改变了 diff hunk 对齐）。
2. Controller correction CV-F01 要求将闭集从 "added definitions" 扩展为 "signature span 与 current diff added lines 相交的 definitions"。
3. 最终扫描结果：`signature_touched=132 issues=0`。
4. 走读 diff 中新增的 docstring 覆盖：
   - `provider.py:_parse_config`、`_resource_budgets_default`：完整中文 Args/Returns/Raises。
   - `web_resource_budget.py` 全部新 class/function：完整中文 Args/Returns/Raises。
   - `web_diagnostics.py:project_error_message`：Args 更新为 `max_chars: 投影最大字符数，必须为正整数`。
   - `web_tools.py:_raise_fetch_failure`：新增 `diagnostic_error_chars` 参数说明。
   - `web_fetch_orchestrator.py:_fetch_and_convert_content`、`_warmup_domain`、`_materialize_response_body`、`_read_limited_response_body`、`_decompress_limited_response_body`：全部新增/更新 Args。
   - `web_playwright_backend.py:_fetch_and_convert_with_playwright`、`_playwright_sync_worker`、`_playwright_process_entry`、`_run_playwright_worker_process`、`_read_budgeted_dom_metrics`、`_materialize_bounded_page_projection`：全部新增/更新 Args。
   - `web_search_providers.py:search_public_web`、`_search_with_tavily`、`_search_with_serper`、`_search_with_duckduckgo`、`_materialize_bounded_search_response`、`_filter_visible_results`：全部更新 Args。
   - test files 中的新增 test doubles、nested fakes 和 test functions。
5. Added-line loose callable scan: `lambda`=`0`、`**kwargs`=`0`、`type: ignore`=`0`、`hasattr/getattr`=`0`。

**Test helper 模块级提取**: Fix artifact 报告 `closure_free_added_nested_helpers=0`。确实需要捕获 case-local state 的 nested fake 保留嵌套。未引入 god fixture/builder/loose kwargs。行为未改变。

**结论**: closed，无遗留风险。test helper 提取未改变行为或形成过耦合。

### R02-S1-CR-F03 — cap=1/14/15 marker 有界且显式 — **VERIFIED CLOSED**

**验证路径**:

1. `web_diagnostics.py:34` 新增 `_MINIMAL_ERROR_TRUNCATION_MARKER: Final[str] = "…"`（U+2026 HORIZONTAL ELLIPSIS，`len`=1）。
2. `web_diagnostics.py:436-444`: `max_chars == 1` 时：
   - 先用空 suffix 调用 `truncate_diagnostic_text`，如果未截断（`single_char_projection == projected`）直接返回；
   - 否则返回 `_MINIMAL_ERROR_TRUNCATION_MARKER`（单字符 "…"）。
3. `web_diagnostics.py:445-448`: `max_chars > len(_ERROR_TRUNCATION_SUFFIX)`（即 > 14）时使用完整 `...<truncated>` suffix；否则使用 `_MINIMAL_ERROR_TRUNCATION_MARKER`。
4. 实际验证：
   - `project_error_message("xx", max_chars=1)` → `"…"`
   - `project_error_message("x" * 15, max_chars=14)` → `"xxxxxxxxxxxxx…"`（13 + 1 = 14）
   - `project_error_message("x" * 16, max_chars=15)` → `"x...<truncated>"`（1 + 14 = 15）
   - `project_error_message("short", max_chars=14)` → `"short"`（未超限，原样返回）
5. `_ERROR_TRUNCATION_SUFFIX = "...<truncated>"` 长度确认为 14。
6. `dayu.runtime.diagnostic_text.truncate_diagnostic_text` 公共 contract 零 diff。
7. `WEB_DIAGNOSTIC_SCHEMA_VERSION="web-diagnostics-v2"`、revision `2`、redaction、safe URL、payload shape 均未修改。

**Owner 正确性**: 是。修复落在 `web_diagnostics.project_error_message` owner boundary；runtime primitive contract 未改变。

**结论**: closed，无遗留风险。schema/revision/redaction/runtime primitive 未改变。

### R02-S1-CR-CV-F01 — signature-touched definitions — **VERIFIED CLOSED**

14 个 precise definitions 的 docstring 修复已通过 Controller re-validation。最终 `signature_touched=132 issues=0`。签名、函数体、test flow 与 owner placement 未变。

**结论**: closed。

---

## 旧 Finding 最终状态汇总

| Finding | 来源 | 最终状态 |
|---|---|---|
| R02-S1-CR-F01 — 顶层 unknown fail-fast | MiMo 01 | **closed** |
| R02-S1-CR-F02 — added-definition docs | DS 01 + Controller 扩展 | **closed** |
| R02-S1-CR-F03 — cap marker 有界 | DS 02 | **closed** |
| R02-S1-CR-CV-F01 — signature-touched docs | Controller correction | **closed** |
| MiMo 02 — utility S1 private→custom-port 投影 | MiMo 02 | **accepted observation / no fix**（S1→S3 临时状态正确） |
| MiMo 03 — 极小 cap 行为 | MiMo 03 | **superseded by F03** |
| DS — test docstring 合规 | DS 01 | **closed by F02** |
| DS — cap suffix 可观测性 | DS 02 | **closed by F03** |

---

## Adversarial Pass 逐项结论

### 1. 旧 `WebResourceBudget` 是否零残留

**结论：是。** `grep -rn "WebResourceBudget\b" dayu/ tests/ utils/ --include="*.py" | grep -v "WebResourceBudgets"` 零命中。旧七字段 class、旧 `web_resource_budget_from_json`、旧 `_RESOURCE_BUDGET_FIELDS` 闭集均已删除。

### 2. 全局 fallback 是否删除

**结论：是。** `grep -rn "_DEFAULT_WEB_DIAGNOSTIC_ERROR_CHARS" dayu/tools/web/web_tools.py` 零命中。`web_tools.py` 不再 import 或读取全局 diagnostic error cap。所有 `_raise_fetch_failure` call site（15 处）均显式传入 `diagnostic_error_chars`，无 default。

### 3. Diagnostic owner propagation 是否完整

**结论：是。** `_raise_fetch_failure` 签名 `diagnostic_error_chars: int` 无 default（`inspect.Signature.empty`）。`_fetch_web_page_business:1962` 从 `resource_budgets.diagnostics.error_chars` 取得唯一真源。`_try_playwright_fallback:970,983` 从 `diagnostic_resource_budget.error_chars` 取得。Browser process wrapper `_playwright_process_entry:539` 从 `diagnostic_resource_budget.error_chars` 取得。

### 4. custom-port 与 private 是否独立

**结论：是。** `WebEgressPolicy.__init__` 接受独立的 `allow_private_network` 和 `allow_custom_port` 参数。`authorize_http_target:331` 检查 `self._allow_custom_port`，`authorize_http_target:333` 检查 `self._allow_private_network`，两个独立 `if` 分支。`_search_web_business:1665-1668` 和 `_fetch_web_page_business:1965-1968` 均从 `config.allow_private_network_url` 和 `config.allow_custom_port_url` 独立投影。

### 5. 五 bool/三 child budgets 的 parser/default/propagation

**结论：完整一致。**

- Parser: `provider._parse_config` 逐字段解析五 bool（`_bool_default`），缺失补 typed default，非 bool fail fast。
- Snapshot: `WebToolsConfig` 全字段无 default，由 parser 唯一构造。
- Packaged ↔ typed: `tool_discovery.json` 的五 bool 和三 budget groups 与 typed constants 完全一致。`test_config_loader.py` 断言 `allow_private_network_url=True`、`allow_custom_port_url=True`、`dns_peer_proof_enabled=False`、`allow_environment_proxy=True`、`browser_enabled=True`。
- Propagation: `tool_discovery.json → _parse_config → WebToolsConfig → exact child consumer`，下游不重读 raw config。

### 6. 安全机制是否误删

**结论：未误删。** 以下安全机制全部保留：

- `web_egress_policy.py:331-386`: dangerous/unspecified/multicast 始终拒绝、mixed DNS fail closed、numeric pin/peer proof。
- `web_http_session.py:470-533`: `_send_authorized_request` 仍无 `transport_policy` 参数，`trust_env=False`、`proxies={}`。
- `web_fetch_orchestrator.py`: redirect 逐 hop re-authorization、response lease 保留。
- `web_search_providers.py:638,723,800`: 三处模块级 raw `requests.get/post`。
- `web_playwright_backend.py:1411,1598`: 两处 `allows_private_network` browser/private coupling。
- header/cookie/URL/query redaction、containment/symlink 防御。
- `web_challenge_detection.py`: 零 diff。

### 7. 是否越入 S2/S3/Issue 178/R03/统一 authorization

**结论：无越界。**

- `transport_policy` production 消费只在 provider 构造与 `WebToolsConfig` snapshot；sender 仍无该参数。
- `web_search_providers.py` 仍精确保留三处 raw sender。
- `web_playwright_backend.py` 仍精确保留两处 `allows_private_network` browser/private coupling。
- `utils/diagnose_web_access.py` 的 `_DEFAULT_DIAGNOSTIC_ERROR_CHARS = 1_024` 和 `--max-network default=80` 保持。
- storage lifecycle/CLI/profile/writer 符号仍存在。
- `web_challenge_detection.py`、根 README、Host/Engine/Fins README 零 diff。
- `authorization framework|policy DSL|capability token|Issue #178|R03` 扫描零命中。

### 8. utility S1 private→custom-port 投影

**结论：正确且未形成新 owner。** `utils/diagnose_web_access.py:2705-2707` 将 `allow_private_network_url` 同时投影给 `allow_private_network` 和 `allow_custom_port`。这是 F02 的精确 retained-behavior 修复：旧 `WebEgressPolicy` 将 custom-port 检查耦合在 `allow_private_network` 分支内，S1 拆分后 utility 在 policy construction boundary 将现有开关同时投影给两者。S3 将从 typed config 同源读取两个独立值。未新增 raw config parser、CLI 字段、S2 transport 或 S3 lifecycle。

### 9. README 是否准确表达 snapshot-only 时序

**结论：是。** `dayu/config/README.md` 明确写："当前 S1 只把 `dns_peer_proof_enabled`、`allow_environment_proxy` 与 `browser_enabled` 保存为不可变 typed snapshot；HTTP sender 仍保持既有 numeric pin / no-proxy 行为，browser backend 也保持既有 private-policy coupling。" `tests/README.md` 明确记录 S1 新增的 owner contract tests 和 retained S1 行为。

### 10. test quality / coverage gaming

**结论：无 coverage gaming。**

- 249 passed, 1 skipped（既有条件式 smoke）。
- 九文件逐文件 coverage: provider 93%、resource_budget 100%、egress 86%、http_session 87%、web_tools 80%、diagnostics 92%、search_providers 87%、fetch_orchestrator 82%、playwright_backend 80%。
- 三个文件恰为 80% 门槛值，但所有文件均经过独立 `coverage report --include=<exact-file> --fail-under=80` 验证。
- 新增 tests 覆盖 S1 实际改变的 owner contract 路径，不是无意义的 line coverage padding。
- CV-F04 指出的四个无关 grouped helper tests 已删除。

---

## Observations（非 blocking）

### Obs-1 — provider 顶层 config null 值行为变化（non-blocking）

`_bool_default` 从 `config.get()` + `if value is None` 改为 `if field_name not in config` + `config[field_name]`。这意味着 JSON `null` 值现在会被 `isinstance(value, bool)` 检查拒绝，而非静默回退到 default。这符合 plan "bool-as-null fail fast" 要求，但构成微妙的行为变化。风险低：`tool_discovery.json` 为项目自控，不预期出现 `null` 值。

### Obs-2 — 三文件 coverage 在门槛值 80%（non-blocking）

`web_tools.py`（80%）、`web_fetch_orchestrator.py`（82%）、`web_playwright_backend.py`（80%）均在最低线。S2 修改这些文件时必须重新逐文件验证覆盖率。

### Obs-3 — pre-existing test lambda 债务（non-blocking）

`test_web_tools_provider.py` 中仍有大量既有 lambda（如 line 3213-3215 等），这是 baseline 债务，非 S1 回归。

### Obs-4 — utility `_DEFAULT_DIAGNOSTIC_ERROR_CHARS = 1_024` 独立常量（non-blocking）

`utils/diagnose_web_access.py` 的 `_DEFAULT_DIAGNOSTIC_ERROR_CHARS = 1_024` 仍然独立于 `DEFAULT_DIAGNOSTIC_RESOURCE_BUDGET.error_chars = 8_192`。这是已登记的 S1→S3 transitional 状态，S3 将同源到 typed diagnostic config。

---

## Open Questions

无。

## Residual Risk

- S2 将引入 transport policy 到 sender、proxy/proof 分支、browser/private 解耦——这些是后续 slice 的增量风险，不在 S1 scope。
- S3 将删除 utility-local `1_024/default=80` 和 credential lifecycle——这些是后续 slice 的增量风险，不在 S1 scope。
- `web_tools.py` 与 `web_playwright_backend.py` coverage 均为门槛值 80%；后续 slice 修改仍须重新逐文件验证。
- Pre-existing test lambda 债务（非 S1 回归，可独立跟踪）。

---

## Verdict

**PASS**

S1 implementation 正确完成了 config owner 与 typed policy split。所有 4 个 Controller validation findings (F01–F04) 和 3 个 code review findings (R02-S1-CR-F01–F03) 以及 Controller correction (R02-S1-CR-CV-F01) 均已关闭。旧 `WebResourceBudget` 零残留。五 bool 独立解析、三 child budgets typed owner 分离、`_raise_fetch_failure` 消费当前 Diagnostic owner、search visibility 使用同一 typed egress policy、diagnostic utility S1 临时投影正确保留行为、browser/private coupling 未被提前删除、安全机制全部保留。无 S2/S3/Issue 178/R03 越界实现。

本轮 re-review 未发现新 material findings。四个 observations 均为 non-blocking，不阻塞进入 Controller accepted-slice commit 流程。

**停止等待 Controller。不得自行 commit、push、进入 R02-S2/S3、Issue 178、R03 或统一 authorization。**
