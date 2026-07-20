# WU-SEMANTIC-OWNERSHIP-01 / R02-S3 DS Final Full-Slice Code Re-Review

## Gate 结论：PASS

R02-S3 完整 product/test/README diff 经本路独立 full-slice re-review，未发现新 material finding。以下逐项提供直接代码/数据证据。

## Scope

- **Mode**: current changes（working tree diff）
- **Umbrella**: `WU-SEMANTIC-OWNERSHIP-01`
- **Slice**: `R02-S3`
- **Base**: `08c2380a`（`gateflow: enter R02-S3 implementation`）
- **Accepted S2 commit**: `d8d6e9d9`
- **Output file**: `docs/reviews/wu-semantic-ownership-01-r02-web-owner-policy-s3-code-rereview-ds.md`
- **Included scope**:
  - `utils/diagnose_web_access.py` — full file re-read
  - `utils/smoke_web_ci.py` — full file re-read
  - `tests/tools/web/test_diagnose_web_access.py` — full file re-read
  - `tests/tools/web/test_smoke_web_ci.py` — full file re-read
  - `tests/README.md` — diff re-read
  - `docs/host/issues-implementation-control.md` — R02 section re-read
  - `docs/host/wu-semantic-ownership-01-r02-web-owner-policy-plan.md` — §§10–15 re-read
  - 全部既有 S3 review/controller/fix artifact 完整重读
  - retained-security owner files（`web_diagnostics.py`、`web_egress_policy.py`、`web_fetch_orchestrator.py`、`web_playwright_backend.py`、`web_challenge_detection.py`、`web_resource_budget.py`）— 零 diff 确认
- **Excluded scope**: 无
- **Parallel review coverage**: 无（本路为 DS 单路完整独立 re-review）

## 审查方法

本 re-review 按以下顺序独立执行：

1. 完整重读 `AGENTS.md` 全部硬约束
2. 完整重读 accepted plan §§10–15（S3 原子目标、逐文件删除/保留、gate commands、frozen budget、smoke、coverage、completion）
3. 完整重读全部七份 S3 artifact：implementation、Controller validation、MiMo initial review、DS initial review、Controller adjudication、zero-change fix record、zero-change Controller validation
4. `git diff 08c2380a --stat` 确认 changed files 均在 S3 allowlist 内
5. 逐文件完整重新走读四条 changed paths（两 production + 两 test）
6. 独立重算 11-path protected manifest aggregate：逐文件 SHA-256 → manifest → 再次 SHA-256
7. 独立执行全部关键 scan：lifecycle residual、utility local defaults、old CLI、getattr/hasattr、permission、environment reads、second constructor、deferred scope
8. 独立验证 security owners 零 diff、versioned fixture 存在性/大小、pyright、`git diff --check`
9. 沿关键 owner chain 逐行走读：`_resolve_explicit_storage_state_input` → `_build_single_diagnostic_payload` → 三 profile 函数 → 各 writer
10. 沿 smoke execution chain 逐行走读：`_VERSIONED_FILING_FIXTURE` → `_build_local_fixture_cases` → `_run_local_cases` → `_filing_artifact_gap` → `_run_local_typed_egress_deny_case`
11. 对用户指定的七个 challenge 维度做独立 adversarial 复核

## 独立 immutable-target digest 重算

### 逐路径 SHA-256

| exact protected path | SHA-256 |
|---|---|
| `docs/host/wu-semantic-ownership-01-r02-web-owner-policy-plan.md` | `1257e0cf64e9e9865760b7b67176d18375a42eade918cba5f4aeb92891ae1351` |
| `docs/reviews/wu-semantic-ownership-01-r02-web-owner-policy-s3-code-review-controller-adjudication.md` | `c791ff235e0b14aa0892c8825f1b107da6e8507f0b138b96c48db4f766fc74d8` |
| `docs/reviews/wu-semantic-ownership-01-r02-web-owner-policy-s3-code-review-ds.md` | `c313d1716104db23e081afda2e0f64820031534d5fae3fbe2f10d189709d93e8` |
| `docs/reviews/wu-semantic-ownership-01-r02-web-owner-policy-s3-code-review-mimo.md` | `435a738dfddaea599d00ea3526eccda609ee313b632f182cf84c4916a01de152` |
| `docs/reviews/wu-semantic-ownership-01-r02-web-owner-policy-s3-controller-validation.md` | `e58b331c0516e73955177cb790732760c6fa2efab332ec0a7fecab3d2d4edf5a` |
| `docs/reviews/wu-semantic-ownership-01-r02-web-owner-policy-s3-implementation-codex.md` | `2bb596ef7c0cccbaef6bd8ad5606cce9fcdcfcd3d0a97356c2198c6014772bfc` |
| `tests/README.md` | `4f5ffd808682a1fb1ae322877a24f6beb4cf22ffe55397324224233f070fc356` |
| `tests/tools/web/test_diagnose_web_access.py` | `2a1797beeb2ff819734c3d4fd2cd10bb04f3bb8cf2b0492df2ca91d9183bb1ec` |
| `tests/tools/web/test_smoke_web_ci.py` | `a25ce40d3e6157d96b95d067b25ecb16a5119a14d94057f5e72971f58d5ff56b` |
| `utils/diagnose_web_access.py` | `c03f004e3e75a7b0390db97058de47d917a79e9ab868637fc8fd086ab782ce06` |
| `utils/smoke_web_ci.py` | `18fa66f7e13e2fab0c9e88c51168f32f0cd3bf79e70575d383177beb12cbd08a` |

### Manifest aggregate SHA-256

按字典序拼接 11 行 `"<sha256>  <path>\n"` 后计算：

```text
d09778af09870fa8acaa04f7b4e6a699efb8d46d9529e520201ff6b6403544ed
```

与 zero-change fix record §4.2 冻结值、zero-change Controller validation §2 独立重算值完全一致。**immutable review target 未被篡改。**

### Control 只读 digest

`docs/host/issues-implementation-control.md` 当前 SHA-256 为 `85ea5454c26be34957d990d5f81ecf7ab1396107e10eb16e1ba387ba40e7da0c`，与 fix record 记录的 `00cdb44bdff040febd02e0b1bc4a6086f0ba0c7bc99a48d43c18106233c8fd53` 不同。**这不是 AgentCodex 篡改**：control 在 fix record 之后由 Controller 合法推进 gate（状态从 "R02-S3 implementation" → "R02-S3 final dual full-slice code re-review"），其 diff 仅涉及 gate 状态字段和新增 S3 进度记录行，不改变产品/测试/README 授权边界。本 re-review 不将其视为 material finding。

## 独立 scans

| scan | 命令/范围 | 结果 |
|---|---|---|
| lifecycle 符号残留 | `rg -n 'storage_state_out\|storage-state-out\|storage_state_ttl\|storage-state-ttl\|_StorageStateLifecycle\|owner_final_name\|_prepare_storage_state_lifecycle\|_reconcile_storage_state_directory' utils/diagnose_web_access.py utils/smoke_web_ci.py utils/diag_web_batch.sh tests/tools/web/` | **零命中** |
| utility local diagnostic defaults | `rg -n '_DEFAULT_DIAGNOSTIC_ERROR_CHARS\|1_024\|default=80' utils/diagnose_web_access.py tests/tools/web/test_diagnose_web_access.py tests/README.md dayu/config/README.md` | **零命中** |
| 旧 private CLI flag | `rg -n -- '--allow-private-network-url' utils/diagnose_web_access.py utils/smoke_web_ci.py` | **零命中**（唯一 test 命中是 negative assertion `assert "--allow-private-network-url" not in command`） |
| getattr/hasattr | `rg -n 'getattr\|hasattr' utils/diagnose_web_access.py utils/smoke_web_ci.py` | **零命中** |
| 旧 permission 常量 | `rg -n '0700\|0600\|chmod\|fchmod' utils/diagnose_web_access.py tests/tools/web/test_diagnose_web_access.py` | **零命中** |
| environment 推断 | `rg -n 'os\.environ\|os\.getenv\|getenv\(\|environ\[' utils/diagnose_web_access.py` | **零命中** |
| 第二 transport constructor | `rg -n 'WebHttpTransportPolicy\s*\(' utils/diagnose_web_access.py` | **零命中** |
| deferred scope 泄漏 | `rg -n 'Issue.*178\|R03\|unified.*auth\|authorization framework\|policy DSL\|capability token\|storage state refresh\|storage state retention' utils/diagnose_web_access.py utils/smoke_web_ci.py tests/tools/web/test_diagnose_web_access.py tests/tools/web/test_smoke_web_ci.py tests/README.md` | **零命中** |
| security owner 零 diff | `git diff 08c2380a -- dayu/tools/web/web_diagnostics.py dayu/tools/web/web_challenge_detection.py dayu/tools/web/web_egress_policy.py dayu/tools/web/web_fetch_orchestrator.py dayu/tools/web/web_playwright_backend.py` | **零 diff** |
| versioned fixture | `ls -la tests/fins/fixtures/aapl_xbrl/fil_0000320193-24-000123/aapl-20240928.htm` | **1,503,780 bytes，常规文件存在** |
| pyright | `python -m pyright` | **0 errors, 0 warnings, 0 informations** |
| whitespace | `git diff --check` | **exit 0，无输出** |

## 逐维度 adversarial 复核

### 1. Lifecycle 是否变相迁移

**直接证据**：

- `_StorageStateLifecycle` class、`_prepare_storage_state_lifecycle`、`_reconcile_storage_state_directory`、`_ensure_private_storage_directory`、`_PRIVATE_DIRECTORY_MODE`/`_PRIVATE_FILE_MODE`、`_STORAGE_STATE_*` 常量 — 全部删除，全仓 scan 零命中。
- `_write_json` (`utils/diagnose_web_access.py:2489-2504`) 与 `_write_jsonl` (`utils/diagnose_web_access.py:2507-2525`)：与基线 `08c2380a` 逐行一致，零语义改动。
- `_write_json` (`utils/smoke_web_ci.py:1744-1759`)：与基线一致。
- smoke 的 `_run_local_cases` (`utils/smoke_web_ci.py:4027-4031`) 写入 run-local 空 JSON `{"cookies": [], "origins": []}` 仅作为真实 Playwright 的显式 read-input fixture；不含 credential value、不由 browser 生成、无 TTL/publish/cleanup contract。
- `_filing_artifact_gap` (`utils/smoke_web_ci.py:2959-2968`) 主动扫描 `output_enabled`/`output_label`/`ttl_seconds`/`published`/`reconcile`/`cleanup` 禁止残留。
- artifact projection (`utils/diagnose_web_access.py:2473-2475, 2093, 2109, 2204, 2220, 2236`) 只投影 `{"input_used": bool}`，不含 path value、credential content、TTL 或 permission。

**结论**：lifecycle 完整删除，未迁移到 writer、smoke fixture 或下游 adapter。零变相迁移。

### 2. Typed config / budget owner chain

**直接证据**：

- `_build_single_diagnostic_payload` (`utils/diagnose_web_access.py:2408-2409`)：`provider_config = _provider_config(options)` → `web_config = _parse_config(provider_config)` — 精确一次调用。
- Line 2410：`diagnostic_resource_budget = web_config.resource_budgets.diagnostics` — 从 typed snapshot 读取。
- Line 2411-2415：`if options.max_network is not None: diagnostic_resource_budget = DiagnosticResourceBudget(error_chars=diagnostic_resource_budget.error_chars, events=options.max_network)` — 显式 override 保留 typed `error_chars`，只替换 `events`，经同一 `DiagnosticResourceBudget` positive-int 校验。
- Line 2416-2419：`WebEgressPolicy(allow_private_network=web_config.allow_private_network_url, allow_custom_port=web_config.allow_custom_port_url)` — 从 typed snapshot 构造。
- Line 2441：`transport_policy=web_config.transport_policy` — 从 typed snapshot 传递。
- Line 2463：`if options.skip_playwright or not web_config.browser_enabled` — browser capability 从 typed snapshot 读取。
- `CliOptions.max_network: int | None` (`utils/diagnose_web_access.py:204`) — 缺省为 `None`，不是 `int = 80`。
- 三 profile 函数签名全部 mandatory typed `diagnostic_resource_budget: DiagnosticResourceBudget` 参数：`_build_requests_profile` (line 1293)、`_build_tool_fetch_profile` (line 1600)、`_build_playwright_profile` (line 2057)。
- 所有 `failed_projection` 调用均使用 `max_error_chars=diagnostic_resource_budget.error_chars` — 无本地 fallback。
- 零 `getattr`/`hasattr`、零 `os.environ`、零第二 `WebHttpTransportPolicy()` constructor。

**结论**：raw config 只由唯一 parser 形成 typed snapshot，全部 budget/policy 从该 snapshot 正确传播。owner chain 完整闭合。

### 3. 真实 filing / Playwright / typed deny

**直接证据**：

- `_VERSIONED_FILING_FIXTURE` (`utils/smoke_web_ci.py:150-158`)：指向 `tests/fins/fixtures/aapl_xbrl/fil_0000320193-24-000123/aapl-20240928.htm`，独立确认文件存在且大小为 1,503,780 bytes。
- `_build_local_fixture_cases` (`utils/smoke_web_ci.py:928-930`)：`if not _VERSIONED_FILING_FIXTURE.is_file(): raise ValueError(...)` → `filing_bytes = _VERSIONED_FILING_FIXTURE.read_bytes()` — hard fail on missing。
- `local-filing-http` (line 1004-1015)：`expected_backend="requests"`、`sample_playwright=False`、`skip_requests=False`。
- `local-filing-playwright` (line 1016-1027)：`expected_backend="playwright"`、`sample_playwright=True`、`skip_requests=True`。
- `_run_local_cases` (line 4072-4076)：仅 `local-filing-playwright` 接收显式 storage-state input，其他 case 传 `None`。
- `_run_local_typed_egress_deny_case` (`utils/smoke_web_ci.py:3558-3564`)：`config = _load_runtime_config_for_overlay(workspace_config_dir)` → `definitions = _discover_tools_by_name(config, workspace_root=diagnostics_dir)` → `outcome = asyncio.run(fetch_definition.callable(...))` — 完整真实 assembly chain。
- private deny：`allow_private_network_url=False, allow_custom_port_url=True`，只关闭 private，保留 custom-port 独立。
- custom-port deny：`allow_private_network_url=True, allow_custom_port_url=False`，只关闭 custom-port，保留 private 独立。
- Controller real smoke 独立确认 11 local passed、0 failed、0 skipped，filing HTTP/Playwright 均 completed，两路 deny 均 `permission_denied`。

**结论**：版本化 fixture、hard gate 与 typed deny 均通过真实 assembly 证明完整体量。

### 4. Ordinary writers

**直接证据**：

- `_write_json` (`utils/diagnose_web_access.py:2489-2504`)：`path.parent.mkdir(parents=True, exist_ok=True)` + `path.write_text(json.dumps(...))` — 与基线完全一致。
- `_write_jsonl` (`utils/diagnose_web_access.py:2507-2525`)：与基线完全一致。
- `_write_json` (`utils/smoke_web_ci.py:1744-1759`)：与基线完全一致。
- 无新增 writer helper、无 `write_text` 调用新增、无 credential lifecycle 语义注入。

**结论**：ordinary writers 零语义改动，未获得 credential lifecycle authority。

### 5. Retained security

**直接证据**：

- `dayu/tools/web/web_diagnostics.py`：零 diff。`WEB_DIAGNOSTIC_SCHEMA_VERSION = "web-diagnostics-v2"`、`WEB_DIAGNOSTIC_SCHEMA_REVISION = 2`、challenge fields 均保留。
- `dayu/tools/web/web_challenge_detection.py`：零 diff。
- `dayu/tools/web/web_egress_policy.py`：零 diff。DNS/dangerous/mixed-address、redirect recheck、peer proof、multicast、unspecified 均保留。
- `dayu/tools/web/web_fetch_orchestrator.py`：零 diff。
- `dayu/tools/web/web_playwright_backend.py`：零 diff。browser route、capability、containment、symlink 均保留。
- `dayu/tools/web/web_resource_budget.py`：零 diff。HTTP/browser/diagnostics budgets 均保留。
- retained-security focused test matrix 93 passed（Codex §3.3）。

**结论**：全部 security owner 零 diff，retained contract 完整保留。

### 6. Deferred scope

**直接证据**：

- `Issue.*178|R03|unified.*auth|authorization framework|policy DSL|capability token|storage state refresh|storage state retention` 对 production/tests/README 零新增命中。
- 无新增 `authorization`/`capability`/`role`/`policy DSL` schema、module、import 或 class。
- run-local 空 JSON 仅是 deterministic smoke 的 read-input fixture，不是 Issue 178 replacement lifecycle。
- R03 accepted-call/evidence projection 未实现。
- 统一 tool authorization framework 未实现。
- proxy credential schema 未新增。

**结论**：deferred scope 零泄漏。

### 7. 验证充分性

**直接证据**：

- **aggregate tests**: 310 passed, 1 skipped（唯一 skip 是既有 opt-in live browser cleanup smoke，需 `DAYU_RUN_LIVE_BROWSER_CLEANUP_SMOKE=1`）。
- **S3 focused tests**: 49 passed, 210 deselected。
- **S3 full tests**: 258 passed, 1 skipped。
- **Coverage**: `utils/diagnose_web_access.py` 81.29%、`utils/smoke_web_ci.py` 81.33% — 均超 80%（utils 按 AGENTS 免 coverage）。
- **pyright**: 0 errors, 0 warnings, 0 informations。
- **`git diff --check`**: exit 0。
- **中文 docstring**: 38 added/signature-touched qualified names，全部有中文 docstring，issues=0（Codex §8）。
- **S3 新增测试覆盖**: storage input validation (5 tests)、artifact lifecycle zero residual (1 test)、packaged defaults (1 test)、independent typed deny (1 test, parametrized)、typed diagnostic budget default/override (1 test, parametrized)、CLI absent None + invalid fail-fast (1 test)、storage dir only to provider resolver (1 test)、versioned filing fixture (1 test)、diagnostic command no old CLI (1 test)、typed egress deny via overlay + callable (1 test, parametrized)、filing hard gate classification (1 test, parametrized)。
- **S3 删除的旧测试**: owner filename、permissions、TTL、atomic publish、replace failure、cancel cleanup、orphan/expired reconciliation — 全部删除，零残留。
- **README**: `tests/README.md` 已更新；`dayu/config/README.md` 零 diff（schema/default 未变）；根 `README.md` 零 diff（零命中最终用户入口/工作流变化）。

**结论**：测试充分，coverage 达标，docstring 完整，README 按触发规则更新。

## Findings

未发现实质性问题。

### DS initial review F01..F08 状态

DS initial review（`s3-code-review-ds.md`）使用了 `R02-S3-DS-F01..F08` 标签，但每项均明确为"无阻塞性 finding / 无影响 / N/A"。Controller adjudication 已将其全部裁决为 `verification-only / no-fix`。本 re-review 独立复核确认：

| label | 核实结论 |
|---|---|
| `R02-S3-DS-F01` — lifecycle/旧 CLI/本地 defaults 删除 | 仍成立。lifecycle 符号零残留，writers 零迁移。 |
| `R02-S3-DS-F02` — 显式 storage-state read input | 仍成立。校验链完整（路径→常规文件→UTF-8→JSON object→绝对路径返回）。 |
| `R02-S3-DS-F03` — 单次 parser typed snapshot | 仍成立。`_parse_config` 精确调用一次，全量从 snapshot 分发。 |
| `R02-S3-DS-F04` — budget/policy typed propagation | 仍成立。三 profile 全部 mandatory typed 参数，零 utility local default。 |
| `R02-S3-DS-F05` — 版本化 filing / HTTP+Playwright / typed deny | 仍成立。fixture 1,503,780 bytes 确认，真实 assembly chain，独立 deny overlays。 |
| `R02-S3-DS-F06` — writers / diagnostics v2 / retained security | 仍成立。writers 零改动，v2/revision2 保留，全部 security owner 零 diff。 |
| `R02-S3-DS-F07` — Issue 178 / R03 / deferred scope | 仍成立。全部 deferred scope scan 零命中。 |
| `R02-S3-DS-F08` — tests / coverage / docstring / README | 仍成立。310 passed，81%+，pyright 零错误，docstring 完整，README 按触发规则。 |

以上八项均保持 `verification-only / no-fix`。**无新增 `R02-S3-DS-RFnn`。**

### Accepted finding 计数

```text
accepted finding = 0
verification-only / no-fix item = 8
new material finding (R02-S3-DS-RFnn) = 0
```

## Controller Discussion 一致性检查

逐项对照 Controller adjudication 的裁决：

1. **lifecycle 删除发生在 owner boundary** — 本 review 独立验证一致
2. **typed config 从唯一 snapshot 分发** — 本 review 独立验证一致
3. **显式 storage-state 只作为 read input** — 本 review 独立验证一致
4. **ordinary writers 零 lifecycle 语义** — 本 review 独立验证一致
5. **版本化 filing + real Playwright 11/11 passed** — 本 review 独立确认 fixture 文件存在且大小精确匹配
6. **typed deny 经正式 assembly/callable** — 本 review 独立验证 production code 使用真实链
7. **retained security 零 diff** — 本 review 独立验证全部 security owner
8. **deferred scope 零泄漏** — 本 review 独立验证

所有 Controller 裁决均得到独立代码证据验证，无冲突。

## Open Questions

无。

## Residual Risk

| risk | owner / destination | basis |
|---|---|---|
| credential storage-state refresh/retention/concurrent publish/cleanup | GitHub Issue #178 / `WU-SEMANTIC-OWNERSHIP-01-WEB-STORAGE-R1` | R02 正确删除提前实现，只保留 read input |
| live DOM/event/error 规模变化 | Web config owner | 当前版本化 fixture 未命中冻结 ceiling；runtime 仍有界失败 |
| proxy 下无法证明 origin peer | Web HTTP transport/config owner | proof+active proxy 继续 typed fail closed |
| Playwright 无法提供 numeric peer proof | browser backend owner | proof-on browser 继续 typed unavailable/fail closed |
| external provider/challenge 波动 | Web diagnostics/smoke owner | deterministic local hard gate 为 11/11；external 只作 diagnostic-only |
| 统一 authorization 愿景 | Topic 9 future Controller decision | 当前 no-code，零偷带 |
| accepted-result / LLM projection | umbrella R03 | R02 未改，必须等待 R02 accepted 后另行进入 |
| 既有 opt-in live browser cleanup smoke 需环境变量 | 既有测试基础设施 | 本 slice 已用本地真实 Playwright hard gate 覆盖 browser execution |
| coverage 接近 80% 阈值（81.29%/81.33%） | S3 tests | 当前达标；utils 按 AGENTS 免 coverage，仅做观测 |

## 结论

**PASS**。R02-S3 implementation 经本路独立 full-slice re-review，结论如下：

- **accepted finding = 0**：DS initial review 的八个 `R02-S3-DS-F01..F08` label 均为 verification-only/no-fix positive evidence，不是缺陷。
- **无新 material finding**：本 re-review 未产生任何 `R02-S3-DS-RFnn`。
- **immutable target digest 匹配**：独立重算 11-path protected manifest aggregate 为 `d09778af09870fa8acaa04f7b4e6a699efb8d46d9529e520201ff6b6403544ed`，与 fix record 冻结值完全一致。
- **control digest 变化**：为 Controller 合法 gate 推进结果，不是 AgentCodex 篡改。
- **七个 challenge 维度全部通过**：lifecycle 零变相迁移、typed config/budget owner chain 完整闭合、真实 filing/Playwright/typed deny 完整体量证明、ordinary writers 零语义改动、retained security 完整保留、deferred scope 零泄漏、验证充分。

等待 Controller 最终裁决。
