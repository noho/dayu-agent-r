# Code Review

## Scope

- Mode: current changes
- Branch: `phaseflow/host-issues-control`
- Base: `08c2380a`
- Output file: `docs/reviews/wu-semantic-ownership-01-r02-web-owner-policy-s3-code-review-mimo.md`
- Included scope: `utils/diagnose_web_access.py`、`utils/smoke_web_ci.py`、`tests/tools/web/test_diagnose_web_access.py`、`tests/tools/web/test_smoke_web_ci.py`、`tests/README.md`；implementation artifact `docs/reviews/wu-semantic-ownership-01-r02-web-owner-policy-s3-implementation-codex.md`
- Excluded scope: `dayu/tools/web/*.py` production code（S1/S2 已 accepted）、`tests/runtime/test_config_loader.py`（未修改）、`dayu/config/README.md`/根 `README.md`（no-update-with-evidence）
- Parallel review coverage: 无

## Review Method

本次 review 按以下顺序执行：

1. 读取 AGENTS.md、plan §10-15、S3 implementation artifact、S3 controller validation、issues-implementation-control.md 当前 R02 状态
2. 审查 `git diff 08c2380a` 的全部 6 个 changed files
3. 沿真实代码路径逐行走读 `_resolve_explicit_storage_state_input`、`_build_single_diagnostic_payload`、`_build_requests_profile`、`_build_tool_fetch_profile`、`_build_playwright_profile`、`_run_local_typed_egress_deny_case`、`_filing_artifact_gap`
4. 执行 adversarial failure pass：lifecycle 残留、旧 CLI 残留、utility local defaults、兼容性代码、deferred scope 泄漏
5. 验证 tests、pyright、coverage、中文 docstring、README 触发

## Findings

未发现实质性问题。

### 详细验证证据

#### 1. Credential lifecycle 是否彻底删除且未迁移到 writer/smoke/adapter

**直接证据**：

- `_StorageStateLifecycle` class 完整删除（`utils/diagnose_web_access.py` 原 187-278 行）
- `_storage_state_owner_final_name` 删除（原 1788-1808 行）
- `_ensure_private_storage_directory` 删除（原 1810-1850 行）
- `_prepare_storage_state_lifecycle` 删除（原 1852-1920 行）
- `_reconcile_storage_state_directory` 删除（原 1922-1965 行）
- `_PRIVATE_DIRECTORY_MODE`/`_PRIVATE_FILE_MODE` 常量删除（原 121-122 行）
- `_STORAGE_STATE_*` 常量删除（原 117-120 行）
- lifecycle 字段 `output_enabled`/`output_label`/`ttl_seconds`/`published` 在 production utility 中零残留（grep 确认）
- `publish()`/`cleanup_failure()`/`_unlink_temp()` 方法删除
- `artifact_projection()` 从返回 5 字段缩减为只返回 `{"input_used": bool}`

**writer/smoke/adapter 迁移检查**：

- `_write_json`/`_write_jsonl`/summary writer 函数签名和实现零改动（diff 确认）
- `_run_local_typed_egress_deny_case` 只写入 `schema_version`/`case_kind`/`safe_url`/`provider_config`/`expected_error_code`/`observed_error_code`/`error_type`/`passed`，无 lifecycle 语义
- `_filing_artifact_gap` 只校验 `browser_executed`/`storage_state.input_used`/`rendered_html_length`/`rendered_text_length`/`network_event_count`，并扫描 `output_enabled`/`output_label`/`ttl_seconds`/`published` 禁止残留
- `_diagnostic_command` 不再添加 `--allow-private-network-url`，只转发 `--storage-state-in`

**结论**：lifecycle 完整删除，未迁移到任何下游。

#### 2. 显式 storage-state 只读输入是否合法自足

**直接证据**（`_resolve_explicit_storage_state_input`，新增 115-140 行）：

```python
def _resolve_explicit_storage_state_input(path_value: str) -> Path | None:
    if not path_value:
        return None
    path = Path(path_value).expanduser().resolve()
    if not path.is_file():
        raise ValueError(f"显式 storage state 输入必须是存在的常规文件：{path}")
    text = path.read_text(encoding="utf-8")
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"显式 storage state 输入 JSON 非法：{exc}") from exc
    if not isinstance(payload, dict):
        raise ValueError("显式 storage state 输入根值必须是 JSON object。")
    return path
```

**校验链**：路径存在 → 常规文件 → UTF-8 可读 → JSON 合法 → 根值为 object → 返回绝对路径。

**消费点**：`_build_single_diagnostic_payload` 和 `_build_playwright_profile` 只把 `storage_state_input` 传给 raw Playwright context option，不写入、不发布、不刷新。

**artifact 投影**：`profile["storage_state"] = {"input_used": storage_state_input is not None}`，只记录输入事实。

**结论**：合法自足，无副作用。

#### 3. Raw config 是否只由唯一 parser 形成 typed snapshot

**直接证据**（`_build_single_diagnostic_payload`，2406-2425 行）：

```python
provider_config = _provider_config(options)
web_config = _parse_config(provider_config)
diagnostic_resource_budget = web_config.resource_budgets.diagnostics
if options.max_network is not None:
    diagnostic_resource_budget = DiagnosticResourceBudget(
        error_chars=diagnostic_resource_budget.error_chars,
        events=options.max_network,
    )
egress_policy = WebEgressPolicy(
    allow_private_network=web_config.allow_private_network_url,
    allow_custom_port=web_config.allow_custom_port_url,
)
```

**传播链**：`_provider_config(options)` → raw mapping → 唯一 `_parse_config()` → `WebToolsConfig` immutable snapshot → `WebEgressPolicy`/`WebHttpTransportPolicy`/`browser_enabled`/`DiagnosticResourceBudget`。

**验证**：`_provider_config` 不再添加 `allow_private_network_url`（diff 确认删除该行）；`_parse_config` 只调用一次；所有下游都从 `web_config` snapshot 派生。

**结论**：唯一 parser，typed snapshot 正确传播。

#### 4. Private/custom-port/browser/transport/diagnostic budget 是否从 owner 正确传播且无 utility local defaults

**直接证据**：

- `WebEgressPolicy` 从 `web_config.allow_private_network_url`/`web_config.allow_custom_port_url` 构造（2416-2419 行）
- `WebHttpTransportPolicy` 从 `web_config.transport_policy` 直接使用（2438 行）
- `browser_enabled` 从 `web_config.browser_enabled` 消费（2448 行）
- `DiagnosticResourceBudget` 从 `web_config.resource_budgets.diagnostics` 派生（2410 行）
- `_DEFAULT_DIAGNOSTIC_ERROR_CHARS = 1_024` 常量删除（86 行）
- `--max-network` absent 时 `options.max_network` 为 `None`（175 行），不创建 fallback
- 显式 override 通过 `DiagnosticResourceBudget(error_chars=<typed>, events=<override>)` 形成（2412-2415 行）
- 所有 `max_error_chars` 消费点都改为 `diagnostic_resource_budget.error_chars`（10 处，diff 确认）
- `network_event_limit` 从 `options.max_network` 改为 `diagnostic_resource_budget.events`（4 处，diff 确认）

**utility local defaults 扫描**：`_DEFAULT_DIAGNOSTIC_ERROR_CHARS|1_024|default=80` 对 diagnostic utility 零命中（grep 确认）。

**结论**：budget 从 owner 正确传播，无 utility local defaults。

#### 5. 版本化真实财报 fixture、HTTP/Playwright hard gate、两路 typed deny 是否使用真实 assembly/callable 并能证明完整体量

**直接证据**：

- `_VERSIONED_FILING_FIXTURE` 指向 `tests/fins/fixtures/aapl_xbrl/fil_0000320193-24-000123/aapl-20240928.htm`（147-155 行）
- `_build_local_fixture_cases` 要求 `is_file()` 且 `read_bytes()`（927-930 行）
- `local-filing-http` 和 `local-filing-playwright` 两个 case 直接注册（1001-1030 行）
- `_filing_artifact_gap` 校验 `browser_executed=true`/`storage_state.input_used=true`/`rendered_html_length`/`rendered_text_length`/`network_event_count`（2921-2960 行）
- lifecycle 字段扫描禁止 `output_enabled`/`output_label`/`ttl_seconds`/`published`（2961-2975 行）
- `_run_local_typed_egress_deny_case` 通过 `_load_runtime_config_for_overlay` → `_discover_tools_by_name` → `ToolDefinition.callable` 正式链（2621-2695 行）
- private deny overlay：`allow_private_network_url=false` + `allow_custom_port_url=true`
- custom-port deny overlay：`allow_private_network_url=true` + `allow_custom_port_url=false`
- 两者都要求 `ToolFailedOutcome.result.error == "permission_denied"`

**Controller real smoke 验证**（controller validation §3.2）：

- 版本化 filing HTTP：1,503,780 bytes，completed
- 版本化 filing Playwright：origin body 1,503,780 bytes，DOM 1,515,212 chars，text 209,272 chars，6 network events，`browser_executed=true`，`storage_state.input_used=true`
- private deny：`permission_denied`
- custom-port deny：`permission_denied`
- 11 local passed，0 failure，0 skip

**结论**：真实 fixture、真实 assembly/callable、完整体量验证。

#### 6. Ordinary writers、diagnostics v2、challenge 与 retained security 是否保留

**直接证据**：

- `_write_json`/`_write_jsonl`/summary writer 函数零改动（diff 确认）
- `web_diagnostics.py` 零 diff（implementation artifact §2.1 第 4 项）
- `web_challenge_detection.py` 零 diff（implementation artifact §2.1 第 4 项）
- `_SCHEMA_VERSION`/`_SCHEMA_REVISION` 未改动
- v2/revision2/challenge/redaction retained tests 通过（implementation artifact §3.3：93 passed）

**retained security focused matrix**（implementation artifact §3.3）：

```
pytest tests/tools/web/test_web_tools_provider.py \
  -k 'private or custom_port or proxy or peer or redirect or browser or challenge or budget or dns or containment or symlink' -q -rs
=> 93 passed, 1 skipped, 81 deselected, exit 0
```

保留的 owner/security 包括：DNS/dangerous/mixed-address、redirect recheck、proxy allow/deny、proof+proxy conflict、numeric peer match/mismatch、HTTP/browser/diagnostic budgets、browser route/capability、challenge、containment/symlink。

**结论**：ordinary writers、diagnostics v2、challenge 与 retained security 完整保留。

#### 7. Issue 178、R03、统一 authorization 与其它 deferred scope 是否零偷带

**直接证据**：

- `authorization framework|policy DSL|capability token|storage state refresh|storage state retention` 对 production/tests/README 零新增（implementation artifact §7 deferred/no-code scan）
- Issue 178 replacement lifecycle 未实现：run-local 空 JSON 只是 deterministic smoke 的显式 read-input fixture（controller validation §4）
- R03 accepted-call/evidence projection 未实现（issues-implementation-control.md 第 223 行）
- 统一 tool authorization framework 未实现（controller validation §4）
- proxy credential schema 未新增（controller validation §4）

**issues-implementation-control.md 第 223 行**：

> Controller independently confirmed complete diagnostic credential lifecycle/CLI/local-default deletion...Verdict is PASS into dual complete code review; no Issue 178、R03、proxy credential schema或统一authorization实现被授权。

**结论**：deferred scope 零偷带。

#### 8. 测试、coverage、中文 docstring、README 触发是否充分

**测试**：

- aggregate：310 passed，1 skipped（implementation artifact §3.2）
- S3 focused：258 passed，1 skipped（implementation artifact §3.1）
- retained-security matrix：93 passed，1 skipped（implementation artifact §3.3）
- 唯一 skip 是既有 opt-in live browser cleanup smoke

**coverage**：

- `utils/diagnose_web_access.py`：887 statements，721 covered，81.29%（implementation artifact §4）
- `utils/smoke_web_ci.py`：1264 statements，1028 covered，81.33%（implementation artifact §4）
- AGENTS.md 明确 `utils/` 下的脚本默认无需测试、无覆盖率要求；但实际仍超过 80%

**pyright**：0 errors，0 warnings，0 informations（验证确认）

**中文 docstring**：added/signature-touched=38，issues=0（implementation artifact §8）

**README 触发**：

- `tests/README.md`：updated，职责内同步（diff 确认）
- `dayu/config/README.md`：no-update-with-evidence，schema/default 未变
- 根 `README.md`：no-update-with-evidence，零命中 diagnose_web_access/storage out/TTL/旧 private CLI

**结论**：测试、coverage、中文 docstring、README 触发充分。

## Open Questions

无。

## Residual Risk

1. **真实 external provider/browser credential lifecycle**：仍归 Issue 178；R02-S3 不持有该语义。
2. **既有 opt-in live browser cleanup smoke**：需要环境变量才运行，但本 slice 已用本地真实 Playwright hard gate 覆盖浏览器执行、输入读取、财报体量和 artifact contract。
3. **search provider diagnostic-only warnings**：来自保留的外部条件（测试 DNS / API key），不影响零 external fetch 的 deterministic local hard gate。
4. **版本化 fixture 文件稳定性**：依赖 `tests/fins/fixtures/aapl_xbrl/fil_0000320193-24-000123/aapl-20240928.htm` 存在且为常规文件；缺失时 hard fail。

## Verdict

**PASS**

R02-S3 implementation 达到 accepted commit 入口。所有 finding 为零；lifecycle 彻底删除、typed config 唯一 parser、budget owner 传播正确、版本化 fixture/HTTP/Playwright hard gate/typed deny 完整、ordinary writers/diagnostics v2/retained security 保留、deferred scope 零泄漏、测试/coverage/docstring/README 充分。等待 Controller 裁决。
