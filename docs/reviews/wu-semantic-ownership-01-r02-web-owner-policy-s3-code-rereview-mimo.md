# R02-S3 Final Full-Slice Code Re-Review (MiMo)

## Scope

- Mode: current changes
- Branch: `phaseflow/host-issues-control`
- Base: `08c2380a`
- Output file: `docs/reviews/wu-semantic-ownership-01-r02-web-owner-policy-s3-code-rereview-mimo.md`
- Included scope: 与初始 review 相同的 6 个 changed files + 所有关联 artifact（implementation、controller validation、两份 code review、controller adjudication、zero-change fix record、zero-change controller validation）
- Excluded scope: `dayu/tools/web/*.py` production code（S1/S2 已 accepted）、`tests/runtime/test_config_loader.py`（未修改）、`dayu/config/README.md`/根 `README.md`（no-update-with-evidence）
- Parallel review coverage: 无

## Re-Review Method

本次 final full-slice re-review 按以下顺序执行：

1. 完整读取初始 MiMo review、DS review、Controller adjudication、zero-change fix record、zero-change Controller validation
2. 独立重算 11-path protected manifest aggregate SHA-256
3. 重新审查完整 `git diff 08c2380a` 的全部 6 个 changed files
4. 逐行走读 `_resolve_explicit_storage_state_input`、`_build_single_diagnostic_payload`、`_build_requests_profile`、`_build_tool_fetch_profile`、`_build_playwright_profile`、`_run_local_typed_egress_deny_case`、`_filing_artifact_gap`
5. 执行 adversarial failure pass：lifecycle 残留、旧 CLI 残留、utility local defaults、兼容性代码、deferred scope 泄漏
6. 验证 accepted finding=0、DS 八个 label 为 verification-only/no-fix
7. 挑战 lifecycle 是否变相迁移、typed config/budget owner chain、真实 filing/Playwright/typed deny、ordinary writers、retained security、deferred scope 和验证充分性

## Findings

未发现实质性问题。

## 详细验证证据

### 1. Protected Manifest Aggregate 独立重算

Controller validation 声明的 11 个 exact paths、逐路径 SHA-256 和 aggregate digest，我独立使用 `shasum -a 256` 逐文件重算：

| exact protected path | 独立 SHA-256 | Controller 声明 | 匹配 |
|---|---|---|---|
| `docs/host/wu-semantic-ownership-01-r02-web-owner-policy-plan.md` | `1257e0cf...1351` | `1257e0cf...1351` | ✓ |
| `docs/reviews/wu-semantic-ownership-01-r02-web-owner-policy-s3-code-review-controller-adjudication.md` | `c791ff23...74d8` | `c791ff23...74d8` | ✓ |
| `docs/reviews/wu-semantic-ownership-01-r02-web-owner-policy-s3-code-review-ds.md` | `c313d171...93e8` | `c313d171...93e8` | ✓ |
| `docs/reviews/wu-semantic-ownership-01-r02-web-owner-policy-s3-code-review-mimo.md` | `435a738d...152` | `435a738d...152` | ✓ |
| `docs/reviews/wu-semantic-ownership-01-r02-web-owner-policy-s3-controller-validation.md` | `e58b331c...5a` | `e58b331c...5a` | ✓ |
| `docs/reviews/wu-semantic-ownership-01-r02-web-owner-policy-s3-implementation-codex.md` | `2bb596ef...bfc` | `2bb596ef...bfc` | ✓ |
| `tests/README.md` | `4f5ffd80...356` | `4f5ffd80...356` | ✓ |
| `tests/tools/web/test_diagnose_web_access.py` | `2a1797be...b1ec` | `2a1797be...b1ec` | ✓ |
| `tests/tools/web/test_smoke_web_ci.py` | `a25ce40d...f56b` | `a25ce40d...f56b` | ✓ |
| `utils/diagnose_web_access.py` | `c03f004e...ce06` | `c03f004e...ce06` | ✓ |
| `utils/smoke_web_ci.py` | `18fa66f7...d08a` | `18fa66f7...d08a` | ✓ |

**独立 aggregate SHA-256**（按字典序拼接 11 条 manifest line 后再次 SHA-256）：

```text
d09778af09870fa8acaa04f7b4e6a699efb8d46d9529e520201ff6b6403544ed
```

与 Controller validation 声明的 `d09778af...544ed` **完全匹配**。protected target 未被任何 gate 改写。

### 2. Control Doc Digest

当前 control doc SHA-256 为 `85ea5454c26be34957d990d5f81ecf7ab1396107e10eb16e1ba387ba40e7da0c`，与 fix record 中记录的 `00cdb44bdff040febd02e0b1bc4a6086f0ba0c7bc99a48d43c18106233c8fd53` 不同。diff 确认差异仅为 Controller 在 fix record 之后合法推进 gate（`R02-S3 implementation` → `R02-S3 final dual full-slice code re-review`）和更新 `next entry point`/R02-S3 相关状态行。这不是 AgentCodex 篡改，而是 Controller 正常的 gate 推进行为。

### 3. Accepted Finding 与 DS Label 确认

- accepted finding = **0**
- DS `R02-S3-DS-F01..F08` 全部为 **verification-only / no-fix**，是正向通过证据，不是缺陷
- Controller adjudication 明确："AgentDS 使用了 `R02-S3-DS-F01..F08` 标题，但每一项在标题、影响和严重性中都明确写为'无阻塞性 finding / 无影响 / N/A'，本质是通过项而非缺陷"
- zero-change fix record 正确记录为 "defect finding=`0`；verification-only/no-fix item=`8`；fixed defect=`0`"

### 4. Lifecycle 是否彻底删除且未变相迁移

**直接证据**：

- `_StorageStateLifecycle` class、`publish()`、`cleanup_failure()`、`_unlink_temp()`、`artifact_projection()` 的 5 字段版本完整删除
- `_storage_state_owner_final_name`、`_resolve_storage_state_paths`、`_ensure_private_storage_directory`、`_prepare_storage_state_lifecycle`、`_reconcile_storage_state_directory` 全部删除
- `_STORAGE_STATE_*` 常量、`_PRIVATE_DIRECTORY_MODE`/`_PRIVATE_FILE_MODE` 常量删除
- `CliOptions` 不再有 `storage_state_out`、`storage_state_ttl_seconds`、`allow_private_network_url` 字段
- `max_network` 从 `int` 改为 `int | None`
- `_build_argument_parser` 不再有 `--storage-state-out`、`--storage-state-ttl-seconds`、`--allow-private-network-url`；`--max-network` 的 `default=None`
- `_parse_options` 中 `max_network` 正确传递 `None` 或 `int`
- `_provider_config` 不再添加 `allow_private_network_url`
- `_BrowserContextProtocol` 删除 `storage_state()` 方法

**迁移扫描**：

- `rg 'storage_state_out|storage-state-out|storage_state_ttl|storage-state-ttl|_StorageStateLifecycle|owner_final_name|_prepare_storage_state_lifecycle|_reconcile_storage_state_directory' utils/` → **零命中**
- `rg 'output_enabled|output_label|ttl_seconds|published' utils/diagnose_web_access.py` → **零命中**（smoke 的 `_filing_artifact_gap` 中的命中是 forbidden-field negative guard，正确行为）
- `rg '0700|0600|chmod|fchmod' utils/diagnose_web_access.py` → **零命中**
- `rg 'getattr|hasattr' utils/diagnose_web_access.py utils/smoke_web_ci.py` → **零命中**
- `rg '_DEFAULT_DIAGNOSTIC_ERROR_CHARS|1_024|default=80' utils/` → **零命中**

**结论**：lifecycle 完整删除，未变相迁移到 writer/smoke/adapter/测试夹具。

### 5. Typed Config/Budget Owner Chain

**直接证据**（`_build_single_diagnostic_payload`，2408-2415 行）：

1. `provider_config = _provider_config(options)` — 只形成 raw mapping
2. `web_config = _parse_config(provider_config)` — **精确一次调用**，唯一 raw parser
3. `diagnostic_resource_budget = web_config.resource_budgets.diagnostics` — 从 typed snapshot 读取
4. `if options.max_network is not None: diagnostic_resource_budget = DiagnosticResourceBudget(error_chars=diagnostic_resource_budget.error_chars, events=options.max_network)` — 显式 override 保留 typed `error_chars`，只替换 `events`
5. `egress_policy = WebEgressPolicy(allow_private_network=web_config.allow_private_network_url, allow_custom_port=web_config.allow_custom_port_url)` — 从 typed snapshot
6. `transport_policy=web_config.transport_policy` — 从 typed snapshot
7. `browser_enabled` from `web_config.browser_enabled` — 从 typed snapshot

所有下游 profile 函数（`_build_requests_profile`、`_build_tool_fetch_profile`、`_build_playwright_profile`）都接收 mandatory typed `DiagnosticResourceBudget` 参数，消费 `diagnostic_resource_budget.error_chars`，无本地 fallback。

**utility local defaults 扫描**：`_DEFAULT_DIAGNOSTIC_ERROR_CHARS|1_024|default=80` 对 diagnostic utility **零命中**。

**结论**：唯一 parser，typed snapshot 正确传播，无 utility local defaults。

### 6. 真实 Filing/Playwright/Typed Deny

**版本化 fixture**：

- `_VERSIONED_FILING_FIXTURE` 指向 `tests/fins/fixtures/aapl_xbrl/fil_0000320193-24-000123/aapl-20240928.htm`
- 文件存在，大小 `1,503,780 bytes`
- `_build_local_fixture_cases` 要求 `is_file()` 且 `read_bytes()`，缺失即 hard fail

**真实 assembly chain for typed deny**：

- `_run_local_typed_egress_deny_case` 通过 `_write_web_tool_discovery_overlay` → `_load_runtime_config_for_overlay` → `_discover_tools_by_name` → `ToolDefinition.callable` → `asyncio.run(fetch_definition.callable(...))` 完整链
- private deny: `allow_private_network_url=False, allow_custom_port_url=True`
- custom-port deny: `allow_private_network_url=True, allow_custom_port_url=False`
- 两者都要求 `ToolFailedOutcome.result.error == "permission_denied"`

**filing artifact gap 校验**：

- `_filing_artifact_gap` 校验 `browser_executed=true`、`storage_state.input_used=true`、`rendered_html_length`、`rendered_text_length`、`network_event_count`
- 禁止 `output_enabled`/`output_label`/`ttl_seconds`/`published`/`reconcile`/`cleanup` lifecycle 字段残留

**Controller real smoke**：11 local passed，0 failure，0 skip；filing HTTP/Playwright 均 `completed`；private/custom-port deny 均 `permission_denied`。

**结论**：真实 fixture、真实 assembly/callable、完整体量验证。

### 7. Ordinary Writers、Retained Security、Deferred Scope

**ordinary writers**：`_write_json`/`_write_jsonl`/summary writer 与基线 `08c2380a` 逐行一致，零语义改动。

**retained security**：

- `web_diagnostics.py`、`web_challenge_detection.py`、`web_egress_policy.py`、`web_fetch_orchestrator.py`、`web_playwright_backend.py`、`web_resource_budget.py` 全部零 diff
- retained-security focused matrix: 93 passed, 1 skipped, 81 deselected
- 保留 DNS/dangerous/mixed-address、redirect recheck、proxy allow/deny、proof+proxy conflict、numeric peer match/mismatch、HTTP/browser/diagnostic budgets、browser route/capability、challenge、containment/symlink

**deferred scope**：

- `rg 'Issue.*178|R03|unified.*auth' utils/ tests/tools/web/` → **零命中**
- `rg 'authorization framework|policy DSL|capability token|storage state refresh|storage state retention' utils/ tests/` → **零命中**
- run-local 空 JSON `{"cookies": [], "origins": []}` 只是 deterministic smoke 的显式 read-input fixture，不是 credential lifecycle

**结论**：ordinary writers、retained security、deferred scope 全部正确。

### 8. 测试、Coverage、中文 Docstring、README

- aggregate: 310 passed, 1 skipped
- S3 focused: 258 passed, 1 skipped
- retained-security matrix: 93 passed, 1 skipped
- coverage: `diagnose_web_access.py` 81.29%, `smoke_web_ci.py` 81.33%（均超 80%）
- pyright: 0 errors, 0 warnings, 0 informations
- 中文 docstring: 38 added/signature-touched, issues=0
- README: `tests/README.md` 已更新；`dayu/config/README.md` 和根 `README.md` no-update-with-evidence

**结论**：测试充分，coverage 达标，docstring 完整，README 正确。

## Open Questions

无。

## Residual Risk

与初始 review 和 DS review 记录的 residual owners 完全一致，无新增：

1. **credential storage-state refresh/retention/concurrent publish/cleanup**：仍归 Issue 178。
2. **live DOM/event/error 规模变化**：当前版本化 fixture 未命中冻结 ceiling。
3. **proxy 下无法证明 origin peer**：proof+active proxy 继续 typed fail closed。
4. **Playwright 无法提供 numeric peer proof**：proof-on browser 继续 typed unavailable/fail closed。
5. **external provider/challenge 波动**：deterministic local hard gate 为 11/11。
6. **统一 authorization 愿景**：当前 no-code，零偷带。
7. **accepted-result / LLM projection**：R03 未授权。
8. **既有 opt-in live browser cleanup smoke**：本 slice 已用本地真实 Playwright hard gate 覆盖。
9. **coverage 接近 80% 阈值**：当前达标；utils 按 AGENTS 免 coverage。

## Verdict

**PASS**

R02-S3 final full-slice re-review 确认：

- accepted finding = **0**
- DS 八个 label（`R02-S3-DS-F01..F08`）为 verification-only / no-fix，不是缺陷
- 11-path protected manifest aggregate SHA-256 = **`d09778af09870fa8acaa04f7b4e6a699efb8d46d9529e520201ff6b6403544ed`**，与 Controller validation 完全匹配
- control doc digest 变化为 Controller 合法推进 gate，非 AgentCodex 篡改
- lifecycle 彻底删除且未变相迁移
- typed config/budget owner chain 完整闭合
- 版本化 fixture、真实 HTTP/Playwright、两路 typed deny 使用真实 assembly/callable
- ordinary writers、retained security、deferred scope 全部正确
- 测试、coverage、docstring、README 充分
- 无新 material finding（无 `R02-S3-MIMO-RFnn`）

等待 Controller 最终裁决。
