# WU-SEMANTIC-OWNERSHIP-01 / R02-S3 implementation（Codex）

## 1. Gate 与结论

- umbrella：`WU-SEMANTIC-OWNERSHIP-01`
- slice：`R02-S3`
- accepted S2 commit：`d8d6e9d9`
- implementation transition HEAD / diff base：`08c2380a`
- 当前结论：S3 implementation 已完成；未触发 §13/§15 stop condition，等待 Controller validation。
- 本轮未创建新 WU/feature/issue，未修改 control、既有 review/controller artifact，未 commit/push，未启动 code review，未进入 R03。

第一性原理与直接代码证据确认：credential lifecycle authority 原先完整存在于 `utils/diagnose_web_access.py`，包括 CLI、owner filename、权限、TTL、publish/reconcile/cleanup 与 artifact projection；正确修复边界就是删除该 owner，而不是在 writer、smoke、adapter 或测试夹具中补偿。raw Web config 的唯一 parser owner 仍是 `dayu.tools.web.provider._parse_config`；S3 utility 只消费其 `WebToolsConfig` typed snapshot。显式 storage-state file 是 read input，production storage-state directory resolver 是另一项既有 read owner，二者均不属于待删 lifecycle。

## 2. Exact diff

### 2.1 Production / utility

1. `utils/diagnose_web_access.py`
   - `CliOptions`、parser、batch child command 删除 storage-state output/TTL 与 `--allow-private-network-url`。
   - 删除 `_StorageStateLifecycle`、owner filename、private permission、prepare、publish、failure/cancel cleanup、startup reconciliation 全链。
   - 新增 `_resolve_explicit_storage_state_input`：只接受显式常规文件，读取 UTF-8、严格解析 JSON object；缺失、目录、非法 JSON、非 object 均 fail fast。
   - `--storage-state-dir` 只进入 `_provider_config` 的 production resolver 配置；raw Playwright 不再从目录推导 host filename。
   - 删除 `_DEFAULT_DIAGNOSTIC_ERROR_CHARS = 1_024`；`--max-network` 未提供态为 `None`。
   - `_build_single_diagnostic_payload` 对同一 raw mapping 只调用一次 `_parse_config`，由完整 typed snapshot 分发 private/custom-port、browser capability、transport policy 与 `DiagnosticResourceBudget`。
   - 未提供 `--max-network` 时直接使用 typed `events`；显式值通过 `DiagnosticResourceBudget(error_chars=<typed>, events=<override>)` 的同一 positive-int owner validation 形成 run-local typed value。
   - requests/tool/Playwright/network failure projection 全部消费 typed `error_chars`；Playwright network cap 消费 typed `events`。
   - raw Playwright 只收到已校验的显式 input path；artifact 只保留 `storage_state.input_used`，不含 lifecycle fields。
   - `_write_json`、`_write_jsonl`、summary/markdown writer 零语义改动。

2. `utils/smoke_web_ci.py`
   - 删除 child command 对旧 private CLI 的依赖；assembly packaged-default case 不再注入 private allow overlay。
   - 模块级私有 `_VERSIONED_FILING_FIXTURE` 直接指向既有版本化 SEC AAPL HTML；`_build_local_fixture_cases` 要求该路径存在且为常规文件，并直接把 exact bytes 注册为 `LocalFixtureCase`。
   - 新增 `local-filing-http` 与 `local-filing-playwright`；分别通过 HTTP 与真实 Playwright 执行，artifact 固定写入 `diagnostics/filing/`。
   - filing Playwright 使用本 run 空 storage-state JSON 作为显式 read input；没有 output path、TTL、publish、refresh 或 credential value。
   - 新增 `local-private-deny` / `local-custom-port-deny`：两个独立 typed provider overlay 均经过 `ConfigLoader.load -> assemble_effective_tool_provider_configs -> discover_service_tools -> ToolDefinition.callable`，要求 `permission_denied`。
   - filing hard gate 校验 exact bytes、browser execution、storage input、DOM/text/network metrics与 artifact lifecycle field 零残留。
   - 复用既有 `_write_json` 与 summary writer；没有新增 fixture CLI/path authority或 credential writer。

3. `utils/diag_web_batch.sh`
   - 零 diff。HEAD 只有 `--storage-state-dir` read input forwarding，没有 out/TTL usage，符合“有命中才改”。

4. `dayu/tools/web/web_diagnostics.py`
   - 零 diff。`web-diagnostics-v2`、revision 2、challenge fields与 redaction owner保持。

### 2.2 Tests

1. `tests/tools/web/test_diagnose_web_access.py`
   - 删除 owner filename、权限、TTL、atomic publish、replace failure、cancel cleanup、orphan/expired reconciliation tests及 lifecycle fake。
   - 新增 storage directory 只流向 provider resolver、显式 file valid/missing/directory/invalid JSON/non-object、artifact 无 lifecycle fields。
   - 新增 packaged private/custom-port default、两个独立 typed deny、typed diagnostic default/override、CLI absent `None`、非正 override fail-fast。
   - 同步 requests/tool/Playwright exact fake 的 mandatory typed diagnostic budget/input signature；保留 v2、challenge、redaction、proxy/peer/transport、body budget tests。

2. `tests/tools/web/test_smoke_web_ci.py`
   - 新增版本化 fixture 常规文件/direct registration、HTTP/Playwright hard-gate artifact、显式 input command、旧 private CLI 零依赖、typed private/custom deny assembly/callable tests。

3. `tests/tools/web/test_web_tools_provider.py`
   - 零 diff；作为完整 owner/retained-security regression target执行。

### 2.3 README

- `tests/README.md`：updated。职责内同步 typed diagnostic default/override、read-only explicit input、lifecycle deletion、filing/deny real smoke contract。
- `dayu/config/README.md`：no-update-with-evidence。其职责内已完整描述 packaged 五 bool、private/custom 独立与 diagnostics typed budget owner；S3未改变 config schema/default。
- 根 `README.md`：no-update-with-evidence。零命中 `diagnose_web_access`、storage out/TTL或旧 private developer CLI；用户安装/初始化/入口/工作流未变。
- `dayu/README.md` 与 Host/Engine/Fins/UI README：no update；分层与装配边界未变且不在 S3 allowlist。

## 3. Tests 与 counts

### 3.1 §10.4 focused/full

```text
pytest tests/tools/web/test_diagnose_web_access.py tests/tools/web/test_smoke_web_ci.py tests/tools/web/test_web_tools_provider.py -k 'diagnostic or storage_state or challenge' -q
=> 49 passed, 210 deselected, 3 dependency deprecation warnings, exit 0

pytest tests/tools/web/test_diagnose_web_access.py tests/tools/web/test_smoke_web_ci.py tests/tools/web/test_web_tools_provider.py -q
=> 258 passed, 1 skipped, 3 dependency deprecation warnings, exit 0
```

唯一 skip 是既有 opt-in live cleanup smoke：`tests/tools/web/test_web_tools_provider.py:8485`，需要 `DAYU_RUN_LIVE_BROWSER_CLEANUP_SMOKE=1`；它不属于本地 hard gate。§13 实际 Playwright smoke 为零 skip。

### 3.2 §14 aggregate

```text
pytest tests/tools/web/test_web_tools_provider.py \
  tests/tools/web/test_diagnose_web_access.py \
  tests/tools/web/test_smoke_web_ci.py \
  tests/runtime/test_config_loader.py -q
=> 310 passed, 1 skipped, 3 dependency deprecation warnings, exit 0
```

`tests/runtime/test_config_loader.py` 未修改、未删除、未缩窄；完整加入 aggregate target。

### 3.3 Retained-security focused matrix

```text
pytest tests/tools/web/test_web_tools_provider.py \
  -k 'private or custom_port or proxy or peer or redirect or browser or challenge or budget or dns or containment or symlink' -q -rs
=> 93 passed, 1 skipped, 81 deselected, exit 0
```

该矩阵保留 DNS/dangerous/mixed-address、redirect recheck、proxy allow/deny、proof+proxy conflict、numeric peer match/mismatch、HTTP/browser/diagnostic budgets、browser route/capability、challenge、containment/symlink contract。skip 原因同上；真实本地 Playwright 另见 §5。

## 4. Coverage

固定 artifact：`workspace/tmp/coverage-r02-s3.json`，coverage data：`workspace/tmp/.coverage-r02-s3`。

```text
coverage run --data-file=workspace/tmp/.coverage-r02-s3 -m pytest <三份S3 tests> -q
=> 258 passed, 1 skipped, exit 0

coverage json --data-file=workspace/tmp/.coverage-r02-s3 -o workspace/tmp/coverage-r02-s3.json
=> exit 0
```

S3 changed production `.py` 只有 `utils/**`，按 AGENTS 明确免 coverage；没有 `dayu/tools/web/*.py` production diff需要伪造覆盖率。尽管豁免，实际逐文件仍超过 80%，且没有跳过 tests/smoke：

| changed utility | statements | covered | percent |
|---|---:|---:|---:|
| `utils/diagnose_web_access.py` | 887 | 721 | 81.2852% |
| `utils/smoke_web_ci.py` | 1264 | 1028 | 81.3291% |

两条 `coverage report --include=<exact-file> --fail-under=80` 均 exit 0（显示 81%）。

## 5. §13 deterministic local + real Playwright smoke

命令：

```text
python utils/smoke_web_ci.py \
  --output-dir workspace/tmp/r02-web-owner-policy-local \
  --external-limit 0 \
  --include-playwright \
  --request-timeout 20 \
  --tool-timeout-budget 60 \
  --run-label r02-web-owner-policy-local
```

结果：exit 0；summary status=`passed`；11 local passed、0 failed、0 skipped；4 search-provider diagnostic-only、0 external fetch case。summary：

- `workspace/tmp/r02-web-owner-policy-local/summary.json`
- `workspace/tmp/r02-web-owner-policy-local/summary.md`

关键 artifacts：

- filing HTTP：`workspace/tmp/r02-web-owner-policy-local/diagnostics/filing/local-filing-http.json`
- filing Playwright：`workspace/tmp/r02-web-owner-policy-local/diagnostics/filing/local-filing-playwright.json`
- explicit read input：`workspace/tmp/r02-web-owner-policy-local/diagnostics/filing/explicit-storage-state-input.json`，只含空 `cookies`/`origins` schema，无 credential value。
- private deny：`workspace/tmp/r02-web-owner-policy-local/diagnostics/local/local-private-deny.json`
- custom-port deny：`workspace/tmp/r02-web-owner-policy-local/diagnostics/local/local-custom-port-deny.json`
- challenge control：`workspace/tmp/r02-web-owner-policy-local/diagnostics/local/local-challenge-control.json`
- ordinary browser：`workspace/tmp/r02-web-owner-policy-local/diagnostics/local/local-browser-playwright.json`

版本化 filing metrics 与冻结值：

| metric | observed | frozen ceiling / interpretation |
|---|---:|---:|
| source / local HTTP `Content-Length` | 1,503,780 bytes | exact registered fixture bytes |
| HTTP wire bytes | 1,503,780 bytes | 134,217,728；local server无 content encoding，因此 wire/decoded同值 |
| HTTP decoded bytes | 1,503,780 bytes | 268,435,456 |
| Playwright origin response body | 1,503,780 bytes | HTTP decoded child ceiling内 |
| rendered DOM | 1,515,212 chars | 16,777,216 |
| rendered text | 209,272 chars | 8,388,608 |
| network events | 6 | typed diagnostics `events=512` |
| diagnostic error chars | 0 | typed diagnostics `error_chars=8192` |
| production browser warmup | 本 raw diagnostic case不执行 tool warmup | owner test覆盖 1,048,576 bytes bounded-consume/close；S3未改变该路径 |

所有直接 observed values均未命中/超过对应冻结 ceiling，没有 ceiling-induced failure，因此没有触发 stop。filing HTTP与Playwright均 `completed`，schema=`web-diagnostics-v2`、revision=`2`；Playwright `browser_executed=true`、`storage_state.input_used=true`。filing challenge evidence为 `suspected`，独立 challenge control为 `confirmed` 且包含 `content:bot challenge` / `content:verify you are human` signals。ordinary browser为 `completed`、`browser_executed=true`、2 network events。

private/custom-port 两个 artifacts分别保存独立 typed overlay；两者都经正式 assembly/callable 得到 `permission_denied`。filing diagnostic artifacts对 `cookies|authorization|proxy credential|dayu_smoke_token|完整storage input path` 的扫描零命中；lifecycle fields扫描零命中。

## 6. Typed owner / propagation

唯一链：

```text
CliOptions
  -> _provider_config（只形成 provider raw mapping）
  -> provider._parse_config（唯一 raw parser/default owner）
  -> WebToolsConfig immutable snapshot
       -> WebEgressPolicy(allow_private_network_url, allow_custom_port_url)
       -> WebHttpTransportPolicy
       -> browser_enabled
       -> resource_budgets.diagnostics
  -> DiagnosticResourceBudget.error_chars/events
       -> requests/tool/Playwright failure projection
       -> network event cap
```

`--max-network` absent=`None`；没有 `80` fallback。显式 positive override保留 typed `error_chars`并只替换同一 run 的 `events`；0/-1由 `DiagnosticResourceBudget` owner拒绝。packaged config仍是 private/custom=true、peer-proof=false、environment-proxy=true、browser=true；HTTP/browser/diagnostics frozen values未修改。

storage read链：

```text
--storage-state-in -> 常规文件/UTF-8/JSON object校验 -> raw Playwright context option
--storage-state-dir -> provider config -> production web_playwright_backend resolver
```

不存在 diagnostic host filename推导、output、TTL、permission、publish、reconcile或 cleanup。

## 7. Scans 与静态验证

- 全仓 `python -m pyright`：`0 errors, 0 warnings, 0 informations`，exit 0。
- `git diff --check`：零输出，exit 0。
- allowed-file：implementation diff只含 `utils/diagnose_web_access.py`、`utils/smoke_web_ci.py`、两份对应 tests、`tests/README.md`与本固定 implementation artifact；全部在 S3 allowlist。`utils/diag_web_batch.sh`、`dayu/config/README.md`、根 README、control、既有 review artifacts零 diff。
- `web_diagnostics.py`、`web_challenge_detection.py`：零 diff；v2/revision2/challenge/redaction retained tests通过。
- lifecycle/CLI/default production residual：`storage_state_out|storage-state-out|storage_state_ttl|storage-state-ttl|_StorageStateLifecycle|owner_final_name|_prepare_storage_state_lifecycle|_reconcile_storage_state_directory|_DEFAULT_DIAGNOSTIC_ERROR_CHARS|default=80` 对 diagnostic utility/batch 零命中。
- `--allow-private-network-url` 对 production utility/smoke/batch零命中；唯一 test命中是“命令不得包含旧 flag”的 negative assertion。
- lifecycle field broad scan的 S3-owned命中只在 smoke/test negative guards（`output_enabled/output_label/published/reconcile`）；没有字段 producer、parser、state或 artifact value。其它 `published_date`、Host/Fins `orphan/reconcile` 命中属于无关业务词。
- `0700|0600|chmod|fchmod` 对 diagnostic utility与其 test零命中。
- utility-local `_DEFAULT_DIAGNOSTIC_ERROR_CHARS|1_024|default=80` scan零命中。
- typed owner scan确认 `DiagnosticResourceBudget` mandatory parameters、`error_chars/events/max_network` propagation；没有 utility raw bool parser、environment读取、`getattr/hasattr`或第二 `WebHttpTransportPolicy` constructor。
- transport signature retained：`launch(**kwargs)` / `new_context(**kwargs)`精确两处，只属于既有 Playwright Protocol；不是 compatibility seam。
- retained security scan与 93-pass focused matrix共同证明 redirect、approved addresses、peer、multicast、unspecified、containment、symlink仍有 production owner与 tests。
- deferred/no-code scan：`authorization framework|policy DSL|capability token|storage state refresh|storage state retention` 只命中 accepted plan的非目标说明；production/tests/README零新增。
- ordinary writer additions scan：diagnostic utility新增行中没有 `_write_json`、`_write_jsonl`、summary writer或 `write_text`；旧 writer实现未改。
- compatibility scan：production新增行没有 compatibility shim/default/wrapper、`getattr/hasattr`、loose parser或 lifecycle-to-writer迁移。

## 8. Added/signature-touched 中文 docstring audit

逐 AST qualified-name audit：`added/signature-touched=38 issues=0`。每项均有中文职责/语义，并完整包含 `Args`、`Returns`、`Raises`：

### 8.1 Production / utility（10）

1. `utils/diagnose_web_access.py:CliOptions`
2. `utils/diagnose_web_access.py:_BrowserContextProtocol`
3. `utils/diagnose_web_access.py:_build_requests_profile`
4. `utils/diagnose_web_access.py:_build_tool_fetch_profile`
5. `utils/diagnose_web_access.py:_resolve_explicit_storage_state_input`
6. `utils/diagnose_web_access.py:_append_bounded_network_event`
7. `utils/diagnose_web_access.py:_build_playwright_profile`
8. `utils/smoke_web_ci.py:_filing_artifact_gap`
9. `utils/smoke_web_ci.py:_diagnostic_command`
10. `utils/smoke_web_ci.py:_run_local_typed_egress_deny_case`

### 8.2 `test_diagnose_web_access.py`（21）

1. `test_storage_state_dir_only_flows_to_provider_config`
2. `test_explicit_storage_state_input_reads_valid_json_object`
3. `test_explicit_storage_state_input_rejects_missing_or_non_file`
4. `test_explicit_storage_state_input_rejects_invalid_json_shape`
5. `test_diagnostic_artifact_only_projects_storage_state_input_fact`
6. `test_single_diagnostic_packaged_defaults_allow_private_custom_port`
7. `test_single_diagnostic_packaged_defaults_allow_private_custom_port.fake_build_requests_profile`
8. `test_single_diagnostic_private_and_custom_port_denies_are_independent`
9. `test_single_diagnostic_private_and_custom_port_denies_are_independent.fake_provider_config`
10. `test_single_diagnostic_private_and_custom_port_denies_are_independent.authorize_in_requests_profile`
11. `test_requests_profile_forwards_provider_owned_transport_policy.fake_build_requests_profile`
12. `test_requests_profile_forwards_provider_owned_transport_policy.fake_build_tool_fetch_profile`
13. `test_single_diagnostic_uses_typed_budget_default_and_run_override`
14. `test_single_diagnostic_uses_typed_budget_default_and_run_override.fake_provider_config`
15. `test_single_diagnostic_uses_typed_budget_default_and_run_override.capture_requests_profile`
16. `test_cli_max_network_absent_is_none_and_invalid_override_fails`
17. `test_diagnostic_playwright_private_egress_rejection_precedes_browser`
18. `_options`
19. `_fake_requests_profile`
20. `_fake_fetch_profile`
21. `_fake_playwright_profile`

### 8.3 `test_smoke_web_ci.py`（7）

1. `test_versioned_filing_fixture_is_regular_and_registered_directly`
2. `test_diagnostic_command_has_no_private_cli_and_forwards_explicit_input`
3. `test_typed_egress_deny_cases_use_provider_overlay_and_callable`
4. `test_typed_egress_deny_cases_use_provider_overlay_and_callable.denied_fetch_callable`
5. `test_typed_egress_deny_cases_use_provider_overlay_and_callable.fake_load_runtime_config`
6. `test_typed_egress_deny_cases_use_provider_overlay_and_callable.fake_discover_tools`
7. `test_versioned_filing_http_and_playwright_execution_are_hard_gates`

## 9. Residual owners

| residual | owner / destination | non-blocking basis |
|---|---|---|
| credential refresh/retention/concurrent publish/cleanup | GitHub Issue #178 / `WU-SEMANTIC-OWNERSHIP-01-WEB-STORAGE-R1` | R02明确删除提前实现，只保留read input |
| live DOM/event/error规模变化 | Web config owner | 当前版本化fixture未命中冻结 ceiling；runtime仍有界失败，不在 backend/CLI复制默认 |
| filing raw diagnostic不执行 production warmup | browser budget owner与既有 exact/+1 owner tests | S3只改diagnostic comparator；warmup production path零 diff且 retained matrix通过 |
| proxy下无法证明 origin peer | Web HTTP transport/config owner | proof+active proxy继续 typed fail closed；未发明 proxy credential/schema |
| Playwright无法提供 numeric peer proof | browser backend owner | proof-on browser继续 typed unavailable/fail closed；未绕过 |
| external provider/challenge波动 | Web diagnostics/smoke owner | deterministic local hard gate为11/11；external/search只作 diagnostic-only |
| unified authorization愿景 | Topic 9 future Controller decision | 当前 no-code，scan仅命中plan非目标说明 |
| accepted-result / LLM projection | umbrella R03 | R02未改，无依赖；必须等待R02 accepted后另行进入 |

## 10. Handoff

等待 Controller。不得自行 commit、push、更新 `issues-implementation-control.md`、启动 code review/deepreview或进入 R03。
