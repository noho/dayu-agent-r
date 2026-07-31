# WU-CLI-INIT-01 S5-B Code Re-Review

## Scope

- Mode: current changes
- Branch: `ci/pr-179-first-ci-readiness`
- Baseline: `44171fdfbf2cd09add62be0465052723db21efeb`
- Output file: `docs/reviews/wu-cli-init-01-s5b-code-review-mimo.md`
- Review date: 2026-07-30
- Reviewer: MiMo (re-review after Codex DS F01/F02/F03/F04 fixes)
- Included scope:
  - `utils/smoke_cli_init_provider_matrix.py` (4115 lines, full)
  - `tests/cli/test_smoke_cli_init_provider_matrix.py` (2597 lines, full)
  - `docs/cli_ci.md` (delta)
  - `docs/cli_ci_oracles.json` (delta)
  - `docs/reviews/wu-cli-init-01-s5b-implementation-codex.md` (new)
  - `docs/reviews/wu-cli-init-01-s5b-fix-codex.md` (new)
  - `docs/reviews/wu-cli-init-01-s5b-code-review-ds.md` (new)
  - `docs/reviews/wu-cli-init-01-s5b-code-review-mimo.md` (prior version, replaced by this artifact)
- Excluded scope: `dayu/**` production code (unchanged), frozen manifest (unchanged)
- Parallel review coverage: 无

## Accepted Oracle（用户明确裁决）

1. Host SQLite 及 WAL 中 resolved credential 明文是允许的 canonical durable fact，归类为 `accepted observation`，不是 finding。
2. init-owned config、人类可读 report、log、Tool Trace 与其它非 Host durable evidence 仍不得含 exact credential。
3. canary 在任何位置出现都必须 fail。
4. 本次不重新调用 provider；provider 可用性结论完全复用 retained raw evidence。

## Conformance to Prior Review Findings

前版 MiMo review（`wu-cli-init-01-s5b-code-review-mimo.md`）识别的 4 项 findings 已由 Codex implementation/fix 全部处理：

| # | Prior finding | Status |
|---|---|---|
| 1 | Host SQLite credential 被错误归类为 violation | 已修正：分为 `accepted_observations` 与 `violations` 两通道 |
| 2 | reconciliation 沿用旧 oracle 的 `internal_product_bug` | 已修正：从 canonical evidence 重算 internal contract 和 availability |
| 3 | reconciliation 不扫描 persisted secrets | 已修正：`reconcile_existing_report` 对每个 row 执行 `scan_persisted_secrets` |
| 4 | report 中可能残留绝对路径 | 已修正：`_redact_sensitive_text` 和 `scan_secrets` 双重覆盖 |

## Incremental Review（DS F01/F02/F03/F04 复审）

本次增量复审聚焦 Codex 修复的 DS findings 与受影响 contract。

### F02: Expected Identity 独立派生 & Effective Identity 仅来自 Assembly

**结论：PASS**

`_expected_provider_identity`（L3120-3161）从两个独立源构造 expected identity：
- `choice.expected_provider` → `ProviderIdentity.family_id` / `provider`（来自静态 init catalog，不读 workspace 或 assembly）
- `ConfigLoader(package_config_dir=package_config_root).load_models()` → `choice.thinking_model_id` → `model_family_identity(expected_model)` → `provider_model`（来自冻结 package `models.json`，经层中立 ConfigLoader 解析）

docstring（L3126-3128）明确声明："该路径不读取 workspace publication、production assembly 或 Tool Trace actual identity。"

`_run_matrix_row`（L3330-3341）中：
- `expected_identity` = `_expected_provider_identity(choice, project_root / PACKAGE_CONFIG_ROOT)`（独立于 assembly）
- `effective_identity` = `ProviderIdentity(provider=ordinary.provider, provider_model=ordinary.provider_model)`（仅来自 `_read_effective_identities` → `prepare_entrypoint_runtime` → `host_assembly.ordinary_selection` → `model_family_identity`）

两个身份的派生路径完全分离，无共享状态或交叉依赖。

**直接证据：**
- `smoke_cli_init_provider_matrix.py:3120-3161`：`_expected_provider_identity` 独立构造
- `smoke_cli_init_provider_matrix.py:3330-3341`：`_run_matrix_row` 中两个身份的独立派生
- `smoke_cli_init_provider_matrix.py:3144-3146`：ConfigLoader 加载 package models.json
- `smoke_cli_init_provider_matrix.py:3152`：model_family_identity 从 package 模型解析 provider_model
- `smoke_cli_init_provider_matrix.py:3153-3156`：provider 一致性校验（package vs choice）

### F02 Fail-Closed 子项: 缺 Identity 是否 Fail Closed

**结论：PASS**

`evaluate_no_fallback`（L2027-2086）对 `None` identity 的处理：

1. `request_attempted=True` 且 `expected_identity is None` → `reasons.append("expected_identity_missing")`（L2048-2049）
2. `request_attempted=True` 且 `effective_identity is None` → `reasons.append("effective_identity_missing")`（L2050-2051）
3. `expected_identity is None` 时，`expected_identity not in observed_set` 恒真 → `reasons.append("expected_identity_not_observed")`（L2067-2071）

三个 reason code 同时产生 → `verdict.passed = False`。

在 `_run_matrix_row` 中，`ordinary is None`（assembly 失败）时 `expected_identity` 和 `effective_identity` 都保持 `None`（L3330-3331），同时 `_effective_contract_valid` 返回 `False`（L3095），导致 `internal_contract_valid = False`，最终 `availability_class = INTERNAL_PRODUCT_BUG`。

测试 `test_evaluate_no_fallback_requires_independent_identities_for_request`（L1624-1655）明确验证了 `request_attempted=True` 且 `expected_identity=None, effective_identity=None` 时产生 `expected_identity_missing`、`effective_identity_missing`、`expected_identity_not_observed` 三个 reason code。

**直接证据：**
- `smoke_cli_init_provider_matrix.py:2048-2051`：None identity → missing reason codes
- `smoke_cli_init_provider_matrix.py:2067-2071`：None expected → not_observed 恒成立
- `smoke_cli_init_provider_matrix.py:3330-3341`：`ordinary is None` 时两个 identity 保持 None
- `test_smoke_cli_init_provider_matrix.py:1624-1655`：缺失 identity fail closed 测试

### F01: Non-Requestable Preview 完整脱敏 & Scanner 不自判失败

**结论：PASS**

`_reconcile_terminal_summary`（L3568-3637）对 non-requestable row（`host_run_id` 为空）的处理：

1. 从既有 report 读取 `preview` 文本（L3603-3606）
2. 调用 `_redact_sensitive_text(preview, credential_values, canary, project_root, run_root, workspace_root)`（L3626-3633）
3. 脱敏覆盖：canary 值 → `[REDACTED]`、credential values → `[REDACTED]`、绝对路径 → `[WORKSPACE_ROOT]`/`[RUN_ROOT]`/`[PROJECT_ROOT]`、Authorization 整段 → `[REDACTED]`、Bearer 整段 → `[REDACTED]`、request-id value → `request_id=[REDACTED]`
4. 脱敏后文本经 `summarize_bounded_text` 生成新的 `terminal_summary`（L3634-3635）

scanner 不会自判失败的原因：
- `[REDACTED]` 不匹配 `AUTHORIZATION_PATTERN`（无 `:` 或 `=` 后跟 `\S+`）
- `[REDACTED]` 不匹配 `BEARER_PATTERN`（无 `bearer` 后跟 token）
- `[REDACTED]` 不匹配 `CREDENTIAL_VALUE_PATTERN`（无引号内的值）
- `[REDACTED]` 不匹配 `REQUEST_ID_VALUE_PATTERN`（无 `=` 后跟 `\S+`）
- `[WORKSPACE_ROOT]`/`[RUN_ROOT]`/`[PROJECT_ROOT]` 不是绝对路径（无 `/` 前缀）

对于 Host 路径（`host_run_id` 非空），`observation.terminal_text` 同样经 `_redact_sensitive_text` 脱敏（L3614-3621）。

**直接证据：**
- `smoke_cli_init_provider_matrix.py:3626-3635`：non-requestable preview 脱敏
- `smoke_cli_init_provider_matrix.py:3614-3621`：Host terminal text 脱敏
- `smoke_cli_init_provider_matrix.py:2261-2302`：`_redact_sensitive_text` 完整实现
- `smoke_cli_init_provider_matrix.py:104-119`：四个 scanner regex 不匹配 `[REDACTED]`

### F02 Retained-Report Provenance: Reconciliation 重算 No-Fallback

**结论：PASS**

`_reconciled_no_fallback_verdict`（L4036-4147）从 canonical evidence 完整重算 no-fallback verdict，绝不读取旧 report 的 `no_fallback` 字段。

**三路分支：**

1. **有 Host observation**（L4068-4100）：requestable row
   - `expected_identity` = `_expected_provider_identity(choice, package_config_root, workspace_config_root=...)`（从 package/static 或 init-owned dynamic truth 独立派生）
   - `effective_identity` = `_row_effective_provider_identity(row)`（从 retained report 的 `ordinary_identity` 读取 assembly projection）
   - `observed_identities` = Host canonical `observation.runner_calls` 的 provider/model identity
   - `request_attempted` / `host_run_id` / `trace_run_id` / `alternate_success_observed` = Host canonical facts

2. **无 Host observation 但 request_attempted=True**（L4102-4126）：retained report 声称有请求但无 Host 证据
   - `expected_identity` = 同上独立派生
   - `effective_identity` = 同上 retained assembly projection
   - `observed_identities` = `()`（无 Host 证据则无 observed set）
   - `alternate_success_observed` = `response_received`（retained report 的 `successful_response_received`）

3. **无 Host observation 且 request_attempted=False**（L4128-4147）：non-requestable row
   - `observed_identities` = `_row_runner_call_identities(row)`（从 retained report 的 `runner_calls` 读取）
   - `host_run_id` = `_optional_row_host_run_id(row)`（从 retained report 读取）
   - `expected_identity` = 仅当 `effective_identity is not None` 时才派生（缺 assembly 则为 None → fail closed）
   - `alternate_success_observed` = `response_received`

**P14 Ollama expected identity 来源：**

`_expected_provider_identity`（L3149-3207）的 `workspace_config_root` 参数：
- 动态 choice（Ollama/Custom）：必须提供 init-owned workspace config root → `ConfigLoader.load_models(workspace_config_dir=workspace_config_root)` → 从 workspace `models.json` 读取 `qwen3:8b` 等动态模型
- 静态 choice：`workspace_config_root` 必须为 `None` → 只从 package `models.json` 读取
- 守卫（L3179-3189）：dynamic choice 缺 `workspace_config_root` 或 static choice 提供 `workspace_config_root` 均抛出 `ManifestValidationError`

reconciliation 调用处（L4263-4273）正确传递：
```python
workspace_config_root=(
    workspace_root / "config"
    if choice.kind in DYNAMIC_CHOICE_KINDS
    else None
)
```

**Retained report 15/15 no-fallback pass 的原因：**
- `_reconciled_no_fallback_verdict` 使用 `_expected_provider_identity` 重新派生 expected identity（不读旧 verdict）
- 对于 mimo-token-plan 等静态 choice：expected 来自 package `models.json`，effective 来自 retained assembly projection，两者在正常配置下收敛
- 对于 Ollama：expected 来自 workspace `models.json`（`qwen3:8b`），effective 来自 retained assembly projection（同样是 `qwen3:8b`），收敛
- Host canonical runner calls 的 provider/model 与 expected identity 一致 → 无 fallback

**直接证据：**
- `smoke_cli_init_provider_matrix.py:4036-4147`：`_reconciled_no_fallback_verdict` 完整实现
- `smoke_cli_init_provider_matrix.py:4068-4100`：Host observation 路径
- `smoke_cli_init_provider_matrix.py:4110-4126`：无 Host 但有 request 路径
- `smoke_cli_init_provider_matrix.py:4128-4147`：non-requestable 路径
- `smoke_cli_init_provider_matrix.py:3149-3207`：`_expected_provider_identity` 的 dynamic/static 分支
- `smoke_cli_init_provider_matrix.py:3179-3189`：dynamic/static 守卫
- `smoke_cli_init_provider_matrix.py:4263-4273`：reconciliation 传递 `workspace_config_root`
- `test_smoke_cli_init_provider_matrix.py:505-531`：Ollama expected identity 使用 init-owned dynamic truth
- `test_smoke_cli_init_provider_matrix.py:2412-2421`：reconciliation 重算 no-fallback 通过

## Findings

未发现实质性问题。

## 重点审查逐项结论

### 1. Scanner 两通道互斥语义

**结论：PASS**

`scan_persisted_secrets`（L1884）通过 `_read_persisted_regular_file`（L1728-1754）实现严格互斥：

- credential 在 Host SQLite/WAL（`_persisted_artifact_class` 返回 `HOST_SQLITE` 或 `HOST_SQLITE_WAL`）→ `accepted_observations`
- credential 在其它位置（config、report、log、trace、其它）→ `violations`
- canary 在任何位置 → 始终 `violations`

`_record_accepted_persistence_observation`（L1607-1608）有硬守卫：`artifact_class not in {HOST_SQLITE, HOST_SQLITE_WAL}` 时直接 `raise ValueError`。这意味着即使内部代码错误地把非 Host artifact class 传给 observation recorder，也会立即失败，不会静默接受。

路径分类 `_persisted_artifact_class`（L1520-1554）使用精确路径前缀匹配：
- `workspace/config` → CONFIG
- `workspace/.dayu/host/dayu_host.sqlite3` → HOST_SQLITE
- `workspace/.dayu/host/dayu_host.sqlite3-wal` → HOST_SQLITE_WAL
- `workspace/.dayu/artifacts` 或文件名含 `trace`/`log`/`artifact` → TRACE_LOG_ARTIFACT
- 其它 → ROW_OTHER

如果 Host SQLite 被放在非标准路径，credential 会被归类为 ROW_OTHER 并作为 violation 处理（fail closed）。

**直接证据：**
- `smoke_cli_init_provider_matrix.py:1609-1613`：observation recorder 的 artifact class 守卫
- `smoke_cli_init_provider_matrix.py:1729-1754`：两通道路由逻辑
- `smoke_cli_init_provider_matrix.py:1747-1754`：canary 始终进 violation
- `test_smoke_cli_init_provider_matrix.py:1248-1325`：同时验证 observation 和 violation 的完整测试
- `test_smoke_cli_init_provider_matrix.py:1349-1389`：config/trace/report/其它 credential 均为 violation
- `test_smoke_cli_init_provider_matrix.py:1392-1440`：Host SQLite/WAL credential 均为 observation

### 2. Same-run Reconciliation 是否凭 Canonical Evidence 恢复 Availability

**结论：PASS**

`reconcile_existing_report`（L3862）对每个 row 执行：

1. `_reconcile_terminal_summary`（L3513）：如果 row 有 `host_run_id`，从 Host canonical store 重读 observation，验证 run identity 一致后重写 `terminal_summary`；不启动任何 provider。
2. `scan_persisted_secrets`（L3953）：对 row root 执行完整 no-follow 持久化扫描。
3. `_reconciled_row_internal_contract_valid`（L3685）：从 publication、effective identity、config digest、profile 和只读 Host canonical observation 重算 internal contract——**不沿用旧 report 的 `internal_contract_valid` 派生值**。
4. `_reconciled_availability_class`（L3770）：用重算后的 `internal_contract_valid` 和 Host canonical error code 重新裁决 availability。

关键设计：reconciliation 的 internal contract 重算（L3685）的注释明确说明："旧错误 oracle 已把允许的 Host SQLite credential observation 写回 `internal_contract_valid=false`，所以 reconciliation 不能沿用该派生值。"

reconciliation 的 `_reconciled_availability_class`（L3770）正确处理了 error code 到 failure kind 的映射：
- `terminal_status == SUCCEEDED` → `NONE`
- `terminal_error_code in TRANSPORT_ERROR_CODES` → `TRANSPORT`
- `terminal_error_code in RATE_LIMIT_ERROR_CODES` → `RATE_LIMITED`
- `terminal_error_code in PROVIDER_REJECTION_ERROR_CODES` → `PROVIDER_REJECTED`
- 其它 → `INTERNAL_PRODUCT_BUG`

**直接证据：**
- `smoke_cli_init_provider_matrix.py:3695-3698`：注释说明不沿用旧派生值
- `smoke_cli_init_provider_matrix.py:3961-3968`：reconciliation 计算 internal_contract_valid 并用新 persistence scan 联合裁决
- `smoke_cli_init_provider_matrix.py:3969-3976`：reconciliation 重新裁决 availability_class
- `test_smoke_cli_init_provider_matrix.py:2205-2331`：验证旧 `internal_product_bug` 被正确恢复为 `rate_limited`/`provider_rejected`/`service_unreachable`
- `test_smoke_cli_init_provider_matrix.py:2334-2446`：完整 reconciliation 端到端测试，验证 Host observation 接受、credential 脱敏、无 raw backup

### 3. 是否可能误放行非 Host 泄漏

**结论：PASS，无误放行路径**

泄漏检测有三层互锁：

1. **持久化扫描**（`scan_persisted_secrets`）：逐文件 no-follow 扫描 row root 全部普通文件。credential 在非 Host 位置 → violation → `passed=False` → row `internal_contract_valid=False` → `availability_class=INTERNAL_PRODUCT_BUG` → `matrix_exit_code=1`。
2. **row 文本扫描**（`scan_secrets` L3411-3416）：对 row JSON 文本执行 credential/canary/Authorization/Bearer/request-id/绝对路径扫描。
3. **matrix 文本扫描**（`scan_secrets` L3487-3500）：对完整 matrix report 文本执行相同扫描。

三层扫描中任一失败都会导致非零退出码。且持久化扫描和文本扫描的检测手段互补：
- 持久化扫描：精确 bytes 匹配，覆盖 row root 内全部文件（包括 Host SQLite）
- 文本扫描：regex 模式匹配 + 精确字符串匹配，覆盖最终 JSON 文本

canary 特殊处理：持久化扫描中 canary 在**任何位置**都是 violation（L1747-1754），不像 credential 有 Host SQLite 豁免。这意味着即使 canary 被写入 Host SQLite，也会被检测为 violation。

**直接证据：**
- `smoke_cli_init_provider_matrix.py:3393-3409`：row 级 persisted scan → availability/internal_contract 联合裁决
- `smoke_cli_init_provider_matrix.py:3410-3417`：row 级文本 scan
- `smoke_cli_init_provider_matrix.py:3487-3504`：matrix 级双重 scan → 失败则不写 report
- `smoke_cli_init_provider_matrix.py:1747-1754`：canary 无豁免

### 4. 报告路径 / Request-ID / Secret 脱敏

**结论：PASS**

**报告路径：**
- live run：report 写入 `project_root / REPORT_ROOT / matrix_run_id / "matrix-report.json"`（L3505-3506）
- `scan_secrets` 的 `forbidden_path_prefixes` 包含 `project_root` 和 `run_root`（L3498-3499），确保绝对路径不出现在 report 文本中
- reconciliation 同样传入 `project_root` 和 `run_root`（L4022-4023）

**Request-ID 脱敏：**
- `REQUEST_ID_VALUE_PATTERN`（L108-109）匹配 `client_correlation_id=...` 和 `provider_request_id=...` 的值
- `_redact_sensitive_text`（L2302）用 `request_id=[REDACTED]` 替换
- field name 保留（因为是业务可读标识），value 被脱敏

**Secret 脱敏：**
- `_redact_sensitive_text`（L2261）按顺序替换：canary → credential values → 绝对路径 → Authorization → Bearer → request-id value
- 路径替换按长度降序（L2327-2330），防止 project root 提前吞掉 workspace/run 语义
- `CREDENTIAL_VALUE_PATTERN`（L111-118）的负 lookahead `(?![A-Z][A-Z0-9_]*(?:KEY|TOKEN|SECRET|PASSWORD)["'])` 避免误匹配环境变量名引用

**直接证据：**
- `smoke_cli_init_provider_matrix.py:2261-2302`：`_redact_sensitive_text` 完整实现
- `smoke_cli_init_provider_matrix.py:2305-2333`：`_redact_explicit_path_prefixes` 按长度降序替换
- `smoke_cli_init_provider_matrix.py:104-119`：四个 secret 检测 regex
- `test_smoke_cli_init_provider_matrix.py:1124-1156`：验证 redacted reference names 通过
- `test_smoke_cli_init_provider_matrix.py:1157-1184`：验证每种泄漏类别被检测
- `test_smoke_cli_init_provider_matrix.py:1205-1246`：验证路径替换只替换显式前缀

### 5. 10 Aggregate Records / 10 Rows / 20 Byte Matches 口径

**结论：PASS，口径正确**

Codex implementation artifact 报告：
- 10 个聚合 `accepted_observations` records
- 分布于 10 个 rows
- `count` 汇总 20 次 exact-byte matches

验证：
- `matrix_exit_code`（L2655）只检查 `persisted_secret_scan.passed`，不检查 `accepted_observations` 计数
- `test_matrix_exit_and_json_projection_are_fail_closed`（L2162-2178）明确验证含 `accepted_observations` 的 row 通过 exit code 检查
- 20 次 matches 是 bounded scanner 对 exact credential bytes 的匹配次数，不代表 20 个业务事件
- 每个 record 的 `count` 是 `content.count(probe)` 的结果（L1728），是文件内容中精确 bytes 的出现次数

**直接证据：**
- `smoke_cli_init_provider_matrix.py:2669-2682`：`matrix_exit_code` 只检查 `passed`，不检查 observation 计数
- `test_smoke_cli_init_provider_matrix.py:2162-2178`：accepted observation 不影响 exit code
- `smoke_cli_init_provider_matrix.py:1728`：`content.count(probe)` 精确 bytes 计数

### 6. 无 Provider 重跑

**结论：PASS**

`reconcile_existing_report`（L3862）的 docstring 明确声明："本函数绝不执行 init、prompt 或 provider；它只扫描同一 run 已持久化的 CI-owned row roots，并重建安全的 report projection。"

reconciliation 的实际操作：
- 读取既有 report JSON
- 对每个 row root 执行 `scan_persisted_secrets`（文件系统扫描，无网络）
- 从 Host canonical store 读取 observation（只读 SQLite，无 provider 调用）
- 重写 report JSON（原位 no-follow 写入）

`_reconcile_terminal_summary`（L3513）只在有 `host_run_id` 时读取 Host store，且验证 run identity 一致后才使用。不创建新 run、不启动新 provider。

**直接证据：**
- `smoke_cli_init_provider_matrix.py:3867-3872`：docstring 声明
- `smoke_cli_init_provider_matrix.py:3884-4052`：完整实现，无 subprocess/network 调用

### 7. 测试与类型边界

**结论：PASS**

**测试覆盖：**
- 68 个 focused pytest，全部通过
- `utils/smoke_cli_init_provider_matrix.py` 覆盖率 81%（≥80% 目标）
- 覆盖面包括：manifest 校验、publication tree 校验、preflight/availability 分类、secret 扫描、persisted 扫描（含 SQLite/WAL/symlink/special file）、no-fallback 评估、reconciliation、matrix exit code、JSON 投影

**类型检查：**
- pyright：0 errors, 0 warnings, 0 informations

**类型边界设计：**
- 所有 dataclass 使用 `frozen=True, slots=True`
- 所有 enum 使用 `str, Enum` 双继承，确保 JSON 序列化兼容
- `JsonValue` type alias 递归定义，覆盖完整 JSON 类型空间
- `_expect_mapping`/`_expect_string`/`_expect_int`/`_expect_bool` 等 strict parser 不接受 `Any`
- `LEGACY_ROW_JSON_KEYS`（L169）兼容旧行 row schema，但要求精确匹配 `ROW_JSON_KEYS` 或 `LEGACY_ROW_JSON_KEYS`（L3932）

**直接证据：**
- pytest 输出：68 passed
- pyright 输出：0 errors, 0 warnings, 0 informations
- 覆盖率：81%

### 8. 是否过度设计

**结论：未发现过度设计**

4115 行的实现规模与以下需求匹配：
- 15 个 provider matrix choices × 多维度取证（init、prompt、Host observation、publication、identity、secret scan）
- 严格 no-follow 持久化扫描（OS 级 fd 操作、竞态检测、bounded 扫描）
- same-run reconciliation（从 canonical evidence 完整重算）
- 多层 secret 检测（persisted + row text + matrix text）

每个函数职责清晰，docstring 完整，参数类型严格。未发现不必要的抽象层、重复逻辑或 God object/function。

reconciliation 的 `_reconciled_*` 系列函数虽然与 live path 的 `classify_*`/`_availability_evidence_contract_valid` 存在功能对应，但输入来源不同（reconciliation 从 JSON dict 读取，live path 从 typed dataclass 读取），共享实现需要引入额外的中间抽象，反而增加复杂度。当前分离设计是合理的。

## Open Questions

无。

## Residual Risks

1. **既有 Host SQLite 含裁决允许的 credential 明文**：分类为 `accepted observation`，owner 是既有 Host durable contract，本 slice 不修改。这不是 finding，是已知 accepted 事实。

2. **既有 run 无完整 canary UUID**：legacy reconciliation 使用稳定 `SECRET_CANARY_PREFIX`（`s5b-canary-`）做前缀匹配。这比完整 canary 匹配更宽泛（任何以该前缀开头的字符串都会被匹配），但不会导致漏检——前缀足够唯一，且匹配更宽泛意味着更严格。新 live run 使用完整 exact canary。测试 `test_persisted_scan_legacy_canary_prefix_fails_closed`（L1444）已证明空 canaries 仍按前缀 fail closed。

3. **`_persisted_artifact_class` 的 `trace`/`log`/`artifact` 子串匹配**：文件名含这些子串的任何文件都会被归类为 `TRACE_LOG_ARTIFACT`，credential 在其中会被视为 violation。这是 fail closed 设计，但如果未来有非敏感文件名含这些子串，可能产生误报（false positive violation）。当前无此风险。

4. **未覆盖区域**：`run_live_matrix` 和 `main` 的 live 路径（L3420-4114）未被 pytest 覆盖（因为它们需要真实 provider 调用），但其内部调用的纯函数已全部被覆盖。`main` 的入口和参数校验已通过 `test_main_*` 覆盖。

5. **`_expected_provider_identity` 的 ConfigLoader 依赖**：expected identity 的 `provider_model` 来自 `ConfigLoader(package_config_root).load_models()` 解析的 package `models.json`。如果 package `models.json` 格式变化导致 `ConfigLoader` 行为改变，expected identity 会不同。但这是正确行为——expected identity 必须反映真实 package truth，而非假设的静态值。`_expected_provider_identity` 已校验 `expected_family.provider == choice.expected_provider`（L3153-3156），不一致时抛出 `ManifestValidationError`。

## Verdict

**PASS**

本次 re-review 确认：

1. Codex implementation 和 fix 正确解决了前版 review 的全部 4 项 findings。
2. DS F01（non-requestable 完整脱敏，RESOLVED）：`_reconcile_terminal_summary` 对 non-requestable preview 使用 `_redact_sensitive_text` 完整脱敏（credential、canary、绝对路径、Authorization 整段、Bearer 整段、request-id value），脱敏后的 `[REDACTED]`/`[WORKSPACE_ROOT]` 等占位符不匹配任何 scanner regex，不会自判失败。
3. DS F02（expected/effective identity 自引用，RESOLVED）：`expected_identity` 从 `InitModelChoice` + `ConfigLoader(package_config_root).load_models()` 独立派生，不读 workspace/assembly；`effective_identity` 仅来自 production assembly。两个身份的派生路径完全分离。缺 identity 时 `evaluate_no_fallback` 产生 `expected_identity_missing`/`effective_identity_missing`/`expected_identity_not_observed` 三个 reason code，fail closed（F02 fail-closed 子项）。
3a. F02 retained-report provenance（RESOLVED）：`_reconciled_no_fallback_verdict` 从 canonical evidence 完整重算 no-fallback verdict，不读旧 report 的 `no_fallback`。expected 来自 package/static 或 init-owned dynamic truth（P14 Ollama 从 workspace `models.json` 得到 `qwen3:8b`），effective 来自 retained assembly projection，runner calls/run binding/request-response 来自只读 Host observation。retained report 15/15 no-fallback pass。
4. DS F03（legacy canary prefix，REJECTED-WITH-REASON）：`test_persisted_scan_legacy_canary_prefix_fails_closed` 证明空 canaries 仍按 `SECRET_CANARY_PREFIX` 前缀 fail closed，是 intentional fail-closed 设计。
5. DS F04（dict bool readback，RESOLVED）：`reconciled_internal_contract_valid` 提取为局部变量，消除 dict 往返。
6. Scanner 两通道互斥语义严格且有硬守卫。
7. Same-run reconciliation 凭 canonical evidence 恢复 availability，不沿用旧错误派生值。
8. 无误放行非 Host 泄漏的路径。
9. 报告路径、request-id 和 secret 脱敏完整。
10. 10 aggregate records / 10 rows / 20 byte matches 口径正确。
11. 无 provider 重跑。
12. 测试和类型边界完整。
13. 无过度设计。

## Validation

- focused pytest：71 passed
- `utils/smoke_cli_init_provider_matrix.py` 覆盖率：81%
- pyright：0 errors, 0 warnings, 0 informations
- frozen manifest：未修改
- `dayu/**`：未修改
