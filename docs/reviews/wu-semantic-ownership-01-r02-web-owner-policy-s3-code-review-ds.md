# WU-SEMANTIC-OWNERSHIP-01 / R02-S3 DS Code Review

## Gate 结论：PASS

R02-S3 implementation 通过本路完整 code review。未发现阻塞性 material finding。以下逐项提供直接代码/数据证据。

## Scope

- **Mode**: current changes（worktree diff）
- **Umbrella**: `WU-SEMANTIC-OWNERSHIP-01`
- **Slice**: `R02-S3`
- **Base**: `08c2380a`（`gateflow: enter R02-S3 implementation`）
- **Accepted S2 commit**: `d8d6e9d9`
- **Output file**: `docs/reviews/wu-semantic-ownership-01-r02-web-owner-policy-s3-code-review-ds.md`
- **Included scope**:
  - `utils/diagnose_web_access.py` — full diff + full file read
  - `utils/smoke_web_ci.py` — full diff + full file read
  - `tests/tools/web/test_diagnose_web_access.py` — full diff + full file read
  - `tests/tools/web/test_smoke_web_ci.py` — full diff + full file read
  - `tests/README.md` — diff
  - `docs/host/issues-implementation-control.md` — R02 section only
  - `docs/host/wu-semantic-ownership-01-r02-web-owner-policy-plan.md` — §§10–15
  - `docs/reviews/wu-semantic-ownership-01-r02-web-owner-policy-s3-implementation-codex.md` — full
  - `docs/reviews/wu-semantic-ownership-01-r02-web-owner-policy-s3-controller-validation.md` — full
  - 相关 retained-security owner files（`web_diagnostics.py`、`web_egress_policy.py`、`web_fetch_orchestrator.py`、`web_playwright_backend.py`、`web_resource_budget.py`）— 零 diff 确认
- **Excluded scope**: 无
- **Parallel review coverage**: 无（本路为 DS 单路完整走读）

## 审查方法

本 review 按以下顺序执行：

1. 完整读取 `AGENTS.md` 全部硬约束
2. 完整读取 plan §§10–15（S3 目标、逐文件删除/保留、gate commands、frozen budget、smoke、coverage、completion）
3. 完整读取 Codex implementation artifact 与 Controller validation artifact
4. 完整读取 `issues-implementation-control.md` 当前 R02 全部状态
5. `git diff 08c2380a --stat` 确认 changed files 均在 S3 allowlist 内
6. 逐文件完整读取四条 changed paths（两 production + 两 test）
7. 逐一执行 §10.4 全部 lifecycle/CLI/default/deferred/security/propagation scans
8. 沿 `_build_single_diagnostic_payload` 完整 owner chain 走读：
   `_provider_config → _parse_config → WebToolsConfig → DiagnosticResourceBudget → 所有 profile consumer`
9. 沿 `_run_local_cases` 完整 filing/deny/assembly execution chain 走读
10. 逐 AST qualified-name 审计 added/signature-touched 的中文 docstring
11. 复核测试覆盖、coverage、pyright、README 决策

## Findings

### R02-S3-DS-F01 — 无阻塞性 finding：lifecycle/旧 CLI/本地 defaults 彻底删除且零迁移

- **入口/函数**: 全仓 `rg` scan + `_build_argument_parser` / `_parse_options` / `_build_single_diagnostic_payload`
- **文件(行号)**: `utils/diagnose_web_access.py`（全文件）、`utils/smoke_web_ci.py`（全文件）
- **输入场景**: 对 production utility、smoke、batch script 执行全量 symbol scan
- **实际分支**: N/A（scan 验证缺失）
- **预期行为**: 全部删除 `_StorageStateLifecycle`、owner filename、TTL、权限（0700/0600）、`_prepare_storage_state_lifecycle`、`_reconcile_storage_state_directory`、`publish`、`cleanup_failure`、`_DEFAULT_DIAGNOSTIC_ERROR_CHARS`、`--max-network default=80`、`--allow-private-network-url`
- **实际行为**: 全部删除，零残留
- **直接证据**:
  1. `rg -n 'storage_state_out|storage-state-out|storage_state_ttl|storage-state-ttl|_StorageStateLifecycle|owner_final_name|_prepare_storage_state_lifecycle|_reconcile_storage_state_directory' utils/diagnose_web_access.py utils/smoke_web_ci.py utils/diag_web_batch.sh tests/tools/web` → **零命中**
  2. `rg -n '_DEFAULT_DIAGNOSTIC_ERROR_CHARS|1_024|default=80' utils/diagnose_web_access.py tests/tools/web/test_diagnose_web_access.py tests/README.md dayu/config/README.md` → **零命中**
  3. `rg -n '--allow-private-network-url' utils/diagnose_web_access.py utils/smoke_web_ci.py` → **零命中**（唯一 test 命中是 `assert "--allow-private-network-url" not in command` 的 negative assertion，line `tests/tools/web/test_smoke_web_ci.py:120`）
  4. `rg -n '0700|0600|chmod|fchmod' utils/diagnose_web_access.py tests/tools/web/test_diagnose_web_access.py` → **零命中**
  5. `rg -n 'class.*Lifecycle|publish|reconcile|cleanup.*storage' utils/diagnose_web_access.py` → **零命中**（smoke `_filing_artifact_gap:2963-2964` 的 `"published"`/`"reconcile"` 命中是 forbidden-field negative guard，正确行为）
  6. `_build_argument_parser()` (`utils/diagnose_web_access.py:1011-1058`)：无 `--allow-private-network-url`、无 `--storage-state-out`、无 `--storage-state-ttl`；`--max-network` 的 `default=None`
  7. `CliOptions` dataclass (`utils/diagnose_web_access.py:155-206`)：`max_network: int | None`（非 `int = 80`），无 `allow_private_network_url`、`storage_state_out`、`storage_state_ttl_seconds` 字段
  8. `_write_json` (`utils/diagnose_web_access.py:2489-2504`) 与 `_write_jsonl` (`utils/diagnose_web_access.py:2507-2525`)：与基线 `08c2380a` 完全一致，零语义改动
  9. `utils/smoke_web_ci.py` 的 `_write_json` (`line 1744`)：与基线完全一致
  10. `utils/diag_web_batch.sh`：零 diff（基线 HEAD 无 out/TTL usage，符合 plan §10.3 第 3 条"若当前无命中则保持无 diff"）
- **影响**: 无。lifecycle 语义未被迁移到 writer/smoke/adapter。
- **严重程度**: N/A（非 finding，为验证通过项）

### R02-S3-DS-F02 — 无阻塞性 finding：显式 storage-state 只读输入合法自足

- **入口/函数**: `_resolve_explicit_storage_state_input`
- **文件(行号)**: `utils/diagnose_web_access.py:1791-1816`
- **输入场景**: `--storage-state-in` 提供各种合法/非法路径值
- **实际分支**: 逐条件验证
- **预期行为**: 空字符串→`None`；路径不存在→`ValueError`；不是常规文件→`ValueError`；UTF-8 非法→`ValueError`（JSON 解析失败）；JSON 根值非 object→`ValueError`；合法常规文件 JSON object→返回 `Path`
- **实际行为**: 完全符合
- **直接证据**:
  1. Line 1805-1806: `if not path_value: return None` — 空输入正确跳过
  2. Line 1808-1809: `if not input_path.is_file(): raise ValueError("...必须指向存在的常规文件。")` — 缺失/目录均 fail fast
  3. Line 1811-1813: `json.loads(input_path.read_text(encoding="utf-8"))` + `except json.JSONDecodeError` — 严格 UTF-8 + JSON 解析
  4. Line 1814-1815: `if not isinstance(payload, Mapping): raise ValueError("...根值必须是 object。")` — 拒绝数组/字面量/null
  5. `_build_playwright_profile` (`line 2122-2123`): `if storage_state_input is not None: context_options["storage_state"] = str(storage_state_input)` — 只把已校验 path 传给 raw Playwright
  6. `--storage-state-dir` (`line 1429-1430`): `config["playwright_storage_state_dir"] = str(Path(options.storage_state_dir).expanduser().resolve())` — 只进入 provider resolver，不在 diagnostic 派生 host filename
  7. Artifact projection (`line 2093, 2109, 2204, 2220, 2236`): 所有路径统一投影 `{"input_used": storage_state_input is not None}`，不含 path value、credential content、TTL 或 permission
  8. Tests 覆盖: `test_explicit_storage_state_input_reads_valid_json_object`、`test_explicit_storage_state_input_rejects_missing_or_non_file[missing]`、`[directory]`、`test_explicit_storage_state_input_rejects_invalid_json_shape[{]`、`[[]]`、`[null]`、`test_diagnostic_artifact_only_projects_storage_state_input_fact`
- **影响**: 无。显式输入验证自足完整。
- **严重程度**: N/A

### R02-S3-DS-F03 — 无阻塞性 finding：raw config 只由唯一 parser 形成 typed snapshot

- **入口/函数**: `_build_single_diagnostic_payload`
- **文件(行号)**: `utils/diagnose_web_access.py:2392-2486`
- **输入场景**: 任意 CLI options
- **实际分支**: 单次 `_parse_config` 调用后全量分发
- **预期行为**: provider raw mapping 只经一次 `_parse_config` 形成 `WebToolsConfig` immutable snapshot；private/custom-port、browser capability、transport policy、`DiagnosticResourceBudget` 均从该 snapshot 分发
- **实际行为**: 完全符合
- **直接证据**:
  1. Line 2408-2409: `provider_config = _provider_config(options)` → `web_config = _parse_config(provider_config)` — 精确一次调用
  2. Line 2410: `diagnostic_resource_budget = web_config.resource_budgets.diagnostics` — 从 typed snapshot 读取
  3. Line 2411-2415: `if options.max_network is not None: diagnostic_resource_budget = DiagnosticResourceBudget(error_chars=diagnostic_resource_budget.error_chars, events=options.max_network)` — 显式 override 保留 typed `error_chars`，只替换 `events`，经过同一 `DiagnosticResourceBudget` positive-int 校验
  4. Line 2416-2419: `WebEgressPolicy(allow_private_network=web_config.allow_private_network_url, allow_custom_port=web_config.allow_custom_port_url)` — 从 typed snapshot 构造
  5. Line 2441: `transport_policy=web_config.transport_policy` — 从 typed snapshot 传递
  6. Line 2463: `if options.skip_playwright or not web_config.browser_enabled` — browser capability 从 typed snapshot 读取
  7. `rg -n 'getattr|hasattr' utils/diagnose_web_access.py utils/smoke_web_ci.py` → **零命中**
  8. `rg -n 'WebHttpTransportPolicy\s*\(' utils/diagnose_web_access.py` → **零命中**（utility 不自行构造 transport policy）
  9. `rg -n 'os\.environ|os\.getenv|getenv\(|environ\[' utils/diagnose_web_access.py` → **零命中**（不自行读取环境变量推断 policy）
- **影响**: 无。typed owner chain 完整闭合。
- **严重程度**: N/A

### R02-S3-DS-F04 — 无阻塞性 finding：private/custom-port/browser/transport/diagnostic budget 从 owner 正确传播

- **入口/函数**: `_build_single_diagnostic_payload` → 各 profile 函数
- **文件(行号)**: `utils/diagnose_web_access.py:2392-2486`（payload assembly）、`1293`（`_build_requests_profile` 签名）、`1600`（`_build_tool_fetch_profile` 签名）、`2057`（`_build_playwright_profile` 签名）
- **输入场景**: packaged default 与显式 deny overlay
- **实际分支**: 从 `WebToolsConfig` 单一 snapshot 全量分发
- **直接证据**:
  1. `_build_requests_profile` (`line 1287-1294`): 接收 `egress_policy: WebEgressPolicy`、`transport_policy: WebHttpTransportPolicy`、`diagnostic_resource_budget: DiagnosticResourceBudget` — 全部 mandatory typed 参数
  2. `_build_tool_fetch_profile` (`line 1595-1601`): 接收 `diagnostic_resource_budget: DiagnosticResourceBudget` — mandatory typed 参数
  3. `_build_playwright_profile` (`line 2051-2058`): 接收 `egress_policy: WebEgressPolicy`、`storage_state_input: Path | None`、`diagnostic_resource_budget: DiagnosticResourceBudget` — 全部 mandatory typed 参数
  4. `_append_bounded_network_event` (`line 1925-1930`): 接收 `diagnostic_resource_budget: DiagnosticResourceBudget` — 用于事件数上限和错误消息截断
  5. 所有 `failed_projection` 调用均使用 `max_error_chars=diagnostic_resource_budget.error_chars` — 无本地 fallback
  6. `_build_batch_child_command` (`line 2739-2740`): `if options.max_network is not None: command.extend(["--max-network", str(options.max_network)])` — 只在显式提供时转发，不传播本地默认
  7. `test_single_diagnostic_uses_typed_budget_default_and_run_override` (`test_diagnose_web_access.py:722-809`): parametrized `(max_network=None, expected_events=13)` 与 `(max_network=7, expected_events=7)` — 证明缺省使用 typed config events、显式 override 保留 typed error_chars
  8. `test_cli_max_network_absent_is_none_and_invalid_override_fails` (`test_diagnose_web_access.py:812-837`): `options.max_network is None` + `0/-1` → `ValueError("positive integer")`
- **影响**: 无。全部 budget/policy 从唯一 typed owner 传播。
- **严重程度**: N/A

### R02-S3-DS-F05 — 无阻塞性 finding：版本化真实财报 fixture、HTTP/Playwright hard gate、两路 typed deny 使用真实 assembly/callable

- **入口/函数**: `_run_local_cases` → `_build_local_fixture_cases` / `_run_local_typed_egress_deny_case` / `_filing_artifact_gap`
- **文件(行号)**: `utils/smoke_web_ci.py:150-158`（`_VERSIONED_FILING_FIXTURE`）、`911-1040`（`_build_local_fixture_cases`）、`3525-3613`（`_run_local_typed_egress_deny_case`）、`2924-2969`（`_filing_artifact_gap`）、`4009-4160`（`_run_local_cases`）
- **输入场景**: real smoke execution + test classification
- **实际分支**: 版本化 fixture bytes → ephemeral-port HTTP server → real diagnostic child process → artifact classification
- **直接证据**:
  1. `_VERSIONED_FILING_FIXTURE` (`line 150-158`): `Path(__file__).resolve().parents[1] / "tests" / "fins" / "fixtures" / "aapl_xbrl" / "fil_0000320193-24-000123" / "aapl-20240928.htm"` — 指向既有版本化 SEC AAPL HTML
  2. 文件存在且大小精确匹配: `ls -la` → `1503780 bytes`；与 Codex/Controller smoke 报告的 `1,503,780 bytes` 一致
  3. `_build_local_fixture_cases` (`line 928-929`): `if not _VERSIONED_FILING_FIXTURE.is_file(): raise ValueError(...)` → `filing_bytes = _VERSIONED_FILING_FIXTURE.read_bytes()` — hard fail on missing fixture
  4. `local-filing-http` case (`line 1004-1015`): `expected_backend="requests"`、`sample_playwright=False`、`skip_requests=False` — 通过 raw requests 路径
  5. `local-filing-playwright` case (`line 1016-1027`): `expected_backend="playwright"`、`sample_playwright=True`、`skip_requests=True` — 通过真实 Playwright 路径
  6. `_run_local_typed_egress_deny_case` (`line 3550-3553`): `_write_web_tool_discovery_overlay(workspace_config_dir, provider_config=provider_config)` → `config = _load_runtime_config_for_overlay(workspace_config_dir)` → `definitions = _discover_tools_by_name(config, workspace_root=diagnostics_dir)` → `outcome = asyncio.run(fetch_definition.callable(...))` — 完整真实 assembly chain: `ConfigLoader.load → assemble_effective_tool_provider_configs → discover_service_tools → ToolDefinition.callable`
  7. private deny: `provider_config = {"allow_private_network_url": False, "allow_custom_port_url": True}` — 只关闭 private，保留 custom-port 独立
  8. custom-port deny: `provider_config = {"allow_private_network_url": True, "allow_custom_port_url": False}` — 只关闭 custom-port，保留 private 独立
  9. `_filing_artifact_gap` (`line 2924-2969`): 校验 `browser_executed=true`、`storage_state.input_used=true`、`rendered_html_length`、`rendered_text_length`、`network_event_count`、零 lifecycle field 残留
  10. `_run_local_cases` (`line 4027-4031`): `filing_storage_state_input = filing_diagnostics_dir / "explicit-storage-state-input.json"` → `_write_json(filing_storage_state_input, {"cookies": [], "origins": []})` — 本 run 空 JSON 作为显式 read input；无 output path/TTL/publish/refresh/credential value
  11. Controller smoke 独立确认: `11 local passed, 0 failed, 0 skipped`；filing HTTP/Playwright 均 `completed`；private/custom-port deny 均 `permission_denied`
- **影响**: 无。版本化 fixture、hard gate 与 typed deny 均通过真实 assembly 证明完整体量。
- **严重程度**: N/A

### R02-S3-DS-F06 — 无阻塞性 finding：ordinary writers、diagnostics v2、challenge 与 retained security 保留

- **入口/函数**: 全量 retained contract scan
- **文件(行号)**: `utils/diagnose_web_access.py`（writers）、`dayu/tools/web/web_diagnostics.py`（零 diff）、`dayu/tools/web/web_challenge_detection.py`（零 diff）、`dayu/tools/web/web_egress_policy.py`（零 diff）、`dayu/tools/web/web_fetch_orchestrator.py`（零 diff）、`dayu/tools/web/web_playwright_backend.py`（零 diff）
- **输入场景**: retained security focused test matrix
- **实际分支**: 全部安全 owner 零 diff
- **直接证据**:
  1. Ordinary writers: `_write_json` (`utils/diagnose_web_access.py:2489-2504`) 与 `_write_jsonl` (`utils/diagnose_web_access.py:2507-2525`) — 与基线 `08c2380a` 逐行一致
  2. `_write_json` (`utils/smoke_web_ci.py:1744-1759`) — 与基线一致
  3. `web_diagnostics.py`: 零 diff；`WEB_DIAGNOSTIC_SCHEMA_VERSION = "web-diagnostics-v2"`、`WEB_DIAGNOSTIC_SCHEMA_REVISION = 2`、challenge fields 均保留
  4. `web_challenge_detection.py`: 零 diff
  5. `rg -n 'web-diagnostics-v2|revision.*2|WEB_DIAGNOSTIC_SCHEMA_REVISION|challenge' utils/diagnose_web_access.py` → 26 hits，全部为消费既有 owner 常量、调用 `detect_bot_challenge`、投影 `challenge_decision`/`challenge_signals`
  6. `rg -n 'redirect|approved_addresses|peer|multicast|unspecified|contain|symlink' dayu/tools/web/web_egress_policy.py dayu/tools/web/web_fetch_orchestrator.py dayu/tools/web/web_playwright_backend.py` → 全部命中既有 production owner，零删除
  7. Retained-security focused test matrix: `93 passed, 1 skipped, 81 deselected`（Codex §3.3）；唯一 skip 是既有 opt-in live browser cleanup smoke
- **影响**: 无。全部 retained contract 有 production owner 与 test 证据。
- **严重程度**: N/A

### R02-S3-DS-F07 — 无阻塞性 finding：Issue 178、R03、统一 authorization 与 deferred scope 零偷带

- **入口/函数**: 全仓 deferred scope scan
- **文件(行号)**: 全 changed files + `dayu/tools/web/web_diagnostics.py`
- **输入场景**: scan for Issue 178/R03/unified auth keywords
- **实际分支**: N/A（scan 验证缺失）
- **直接证据**:
  1. `rg -n 'Issue.*178|R03|unified.*auth' utils/diagnose_web_access.py utils/smoke_web_ci.py tests/tools/web/test_diagnose_web_access.py tests/tools/web/test_smoke_web_ci.py tests/README.md` → **零命中**
  2. `rg -n 'authorization framework|policy DSL|capability token|storage state refresh|storage state retention' utils/diagnose_web_access.py utils/smoke_web_ci.py tests/` → **零命中**（`dayu/tools/web/web_diagnostics.py` 的 `"authorization"` 命中是 redaction allowlist 关键字，属于既有敏感值脱敏 owner，不是新 auth framework）
  3. `dayu/tools/web/web_diagnostics.py`: 零 diff — challenge、redaction、v2/revision2 均保留
  4. `dayu/tools/web/web_challenge_detection.py`: 零 diff
  5. No new `authorization` / `capability` / `role` / `policy DSL` schema、module、import 或 class
  6. Run-local 空 JSON `{"cookies": [], "origins": []}` (`utils/smoke_web_ci.py:4028-4031`) 仅是 deterministic smoke 的显式 read-input fixture，不是 browser 生成/持久化/刷新/TTL/publish/cleanup authority
- **影响**: 无。deferred scope 零泄漏。
- **严重程度**: N/A

### R02-S3-DS-F08 — 无阻塞性 finding：测试、coverage、中文 docstring、README 充分

- **入口/函数**: Test suite + coverage report + docstring audit + README check
- **文件(行号)**: `tests/tools/web/test_diagnose_web_access.py`、`tests/tools/web/test_smoke_web_ci.py`、`tests/README.md`
- **输入场景**: S3 focused/full/aggregate test runs
- **实际分支**: 全部通过
- **直接证据**:
  1. **S3 focused tests**: `49 passed, 210 deselected`（Codex §3.1，Controller §3.1 独立确认）
  2. **S3 full tests**: `258 passed, 1 skipped`（Codex §3.1，Controller §3.1 独立确认；唯一 skip 是既有 opt-in live cleanup smoke）
  3. **Aggregate tests**: `310 passed, 1 skipped`（含 `test_config_loader.py` 52 passed；Codex §3.2，Controller §3.1 独立确认）
  4. **Coverage**: `utils/diagnose_web_access.py` 81.29%、`utils/smoke_web_ci.py` 81.33% — 均超过 80% 阈值（尽管 utils 按 AGENTS 免 coverage）
  5. **pyright**: `0 errors, 0 warnings, 0 informations`（Codex §7，Controller §3.1 独立确认）
  6. **`git diff --check`**: exit 0（Codex §7，Controller §3.1 独立确认）
  7. **中文 docstring**: 38 added/signature-touched qualified names 全部有中文 docstring，`issues=0`（Codex §8，逐 AST 审计）
  8. **S3 新增测试完整覆盖**:
     - Storage input validation: valid/missing/directory/invalid JSON/non-object（5 tests）
     - Artifact lifecycle field zero residual（1 test）
     - Packaged defaults private/custom-port true（1 test）
     - Independent typed private/custom-port deny（1 test, parametrized）
     - Typed diagnostic budget default/override（1 test, parametrized）
     - CLI max_network absent=None + invalid fail-fast（1 test）
     - Storage dir only to provider resolver（1 test）
     - Versioned filing fixture regular + registered（1 test）
     - Diagnostic command no old private CLI + explicit input forwarding（1 test）
     - Typed egress deny via overlay + callable（1 test, parametrized）
     - Filing HTTP/Playwright hard gate classification（1 test, parametrized）
  9. **S3 删除的旧测试**: owner filename、permissions、TTL、atomic publish、replace failure、cancel cleanup、orphan/expired reconciliation — 全部删除，零残留
  10. **README**: `tests/README.md` 已更新（typed diagnostic default/override、read-only explicit input、lifecycle deletion、filing/deny real smoke contract）；`dayu/config/README.md` 零 diff（schema/default 未变，已描述当前 config owner）；根 `README.md` 零 diff（零命中最终用户入口/工作流变化）
- **影响**: 无。测试充分，coverage 达标，docstring 完整，README 按触发规则更新。
- **严重程度**: N/A

## Open Questions

无。

## Residual Risk

| risk | owner / destination | basis |
|---|---|---|
| credential storage-state refresh/retention/concurrent publish/cleanup | GitHub Issue #178 / `WU-SEMANTIC-OWNERSHIP-01-WEB-STORAGE-R1` | R02 正确删除提前实现，只保留 read input；Issue 178 负责后续设计实现 |
| live DOM/event/error 规模变化 | Web config owner | 当前版本化 fixture 未命中冻结 ceiling；runtime 仍有界失败 |
| proxy 下无法证明 origin peer | Web HTTP transport/config owner | proof+active proxy 继续 typed fail closed |
| Playwright 无法提供 numeric peer proof | browser backend owner | proof-on browser 继续 typed unavailable/fail closed |
| external provider/challenge 波动 | Web diagnostics/smoke owner | deterministic local hard gate 为 11/11；external 只作 diagnostic-only |
| 统一 authorization 愿景 | Topic 9 future Controller decision | 当前 no-code，零偷带 |
| accepted-result / LLM projection | umbrella R03 | R02 未改，必须等待 R02 accepted 后另行进入 |
| 既有 opt-in live browser cleanup smoke 需环境变量 | 既有测试基础设施 | 本 slice 已用本地真实 Playwright hard gate 覆盖 browser execution |
| coverage 接近 80% 阈值（81.29%/81.33%） | S3 tests | 当前达标；utils 按 AGENTS 免 coverage，仅做观测 |

## Controller Discussion 一致性检查

逐项对照 `docs/reviews/wu-semantic-ownership-01-r02-web-owner-policy-s3-controller-validation.md` 的裁决：

1. **lifecycle/CLI/local-default 删除**: Controller 确认"修复发生在 owner boundary，没有把 lifecycle 搬到 writer、smoke fixture 或下游 adapter"（§2）— 本 review 独立验证一致
2. **typed config 消费**: Controller 确认"private/custom-port、browser capability、transport policy、diagnostic error_chars/events 均从该 snapshot 分发"（§2）— 本 review 独立验证一致
3. **显式 storage-state read input**: Controller 确认"只作为经过常规文件、UTF-8、JSON object 校验的 read input"（§2）— 本 review 独立验证一致
4. **ordinary writers 零 lifecycle**: Controller 确认"ordinary JSON / JSONL / summary writers 没有获得 credential lifecycle 语义"（§2）— 本 review 独立验证一致
5. **版本化 filing + real Playwright**: Controller 确认"11 local passed、zero failure/skip"（§3.2）— 本 review 独立确认 fixture 文件存在且大小精确匹配
6. **typed deny**: Controller 确认"private deny overlay 与 custom-port deny overlay 均经正式 assembly/callable 得到 permission_denied"（§3.2）— 本 review 独立验证 production code 使用真实 `ConfigLoader.load → assemble_effective_tool_provider_configs → discover_service_tools → ToolDefinition.callable`
7. **retained security**: Controller 确认"保留 DNS / redirect recheck / peer proof / proxy conflict / HTTP-browser-diagnostics budgets / browser route / challenge detection / redaction / filesystem containment / symlink"（§4）— 本 review 独立验证全部 security owner 零 diff
8. **deferred scope**: Controller 确认"未实现统一 tool authorization framework / Issue 178 replacement lifecycle"（§4）— 本 review 独立验证零泄漏

所有 Controller 裁决均得到独立代码证据验证，无冲突。

## 结论

**PASS**。R02-S3 implementation 满足 accepted plan §§10–15 的全部要求：

- credential storage-state lifecycle/旧 CLI/本地 defaults 彻底删除且零迁移
- 显式 storage-state 只读输入合法自足
- raw config 只由唯一 parser 形成 typed snapshot
- private/custom-port/browser/transport/diagnostic budget 从 owner 正确传播，零 utility local defaults
- 版本化真实财报 fixture（1,503,780 bytes 确认）、HTTP/Playwright hard gate、两路 typed deny 使用真实 assembly/callable
- ordinary writers、diagnostics v2、challenge 与 retained DNS/redirect/peer/proxy/budget/containment/symlink 安全保留
- Issue 178、R03、统一 authorization 与 deferred scope 零偷带
- 测试充分（258 passed S3 + 52 passed config_loader）、coverage 达标（81%+）、中文 docstring 完整（38 items, issues=0）、pyright 零错误、README 按触发规则更新

无阻塞性 material finding。等待 Controller 裁决。
