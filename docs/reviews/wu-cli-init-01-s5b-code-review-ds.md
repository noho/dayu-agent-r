# Code Review — WU-CLI-INIT-01 S5-B (Re-Review, DS)

## Scope

- **Mode**: current changes (unstaged workspace changes)
- **Branch**: `ci/pr-179-first-ci-readiness`
- **Base**: `44171fdfbf2cd09add62be0465052723db21efeb` (S5-A acceptance)
- **Review round**: 第 3 轮（final follow-up: F02 retained-report no_fallback provenance + Ollama expected identity）
- **Output file**: `docs/reviews/wu-cli-init-01-s5b-code-review-ds.md`
- **Included scope**:
  - `utils/smoke_cli_init_provider_matrix.py`（完整走读，~4115 行）
  - `tests/cli/test_smoke_cli_init_provider_matrix.py`（完整走读，~2505 行）
  - `docs/cli_ci.md`（diff）
  - `docs/cli_ci_oracles.json`（diff）
- **Accepted oracle**（user-confirmed，不变）:
  - Host SQLite 及 WAL 中 resolved credential 明文允许 → 只记 `accepted observation`
  - init-owned config、人类可读 report、log、Tool Trace 与其它非 Host durable evidence 仍不得含 exact credential
  - canary 任何位置都失败
- **Validation**: 70 tests passed | pyright 0 errors, 0 warnings, 0 informations

---

## Verdict: **PASS**

第 1 轮 review 的 4 个 findings 处置如下：

| Finding | 严重度 | 处置 | 理由 |
|---------|--------|------|------|
| F01 — reconciliation 非 requestable 行终端脱敏缺 credential/canary 重扫 | 中 | **RESOLVED** | `_reconcile_terminal_summary:3626-3633` 现调用 `_redact_sensitive_text` 做完整脱敏 |
| F02 — live run effective_identity 自引用导致 no-fallback 盲区 | 中 | **RESOLVED** | `_expected_provider_identity:3120-3161` 从 ConfigLoader 独立派生 expected；effective 仅来自 assembly；缺 identity → fail closed |
| F03 — 空 canary 探针前缀回退可能误报 | 中 | **REJECTED-WITH-REASON** | `test_persisted_scan_legacy_canary_prefix_fails_closed` 证明 intentional fail-closed |
| F04 — `_reconciled_availability_class` 冗余读回 | 低 | **RESOLVED** | `reconciled_internal_contract_valid` 提取为局部变量，消除 dict 往返 |

**无新增 findings。无 blocking findings。**

---

## F01 处置详情：RESOLVED

**原 finding**: `_reconcile_terminal_summary` 在无 `host_run_id` 分支（non-requestable rows）只调用 `_redact_explicit_path_prefixes` 做路径脱敏，不做 credential/canary 脱敏。

**Fix**: line 3626-3633 已将路径脱敏替换为完整 `_redact_sensitive_text` 调用：

```python
# line 3626-3633（修复后）
safe_preview = _redact_sensitive_text(
    preview,
    credential_values=credential_values,
    canary="legacy-canary-value-unavailable",
    project_root=project_root,
    run_root=run_root,
    workspace_root=workspace_root,
)
```

**验证**:
- 原 `preview` 文本现在经过完整脱敏流水线：canary → credential values（长优先）→ 绝对路径前缀（具体优先）→ Authorization pattern → Bearer pattern → request-id pattern
- `credential_values` 通过函数参数从 `reconcile_existing_report:3921`（`_known_credential_values(process_env)`）传入，与调用方已知 credential 同源
- canary 参数 `"legacy-canary-value-unavailable"` 与有 `host_run_id` 分支一致（line 3617），明确标记未知 canary
- 脱敏后的 `safe_preview` 进入 `summarize_bounded_text` → `_bounded_summary_json` → 写入 `row["terminal_summary"]`
- 后续 `row_scan = scan_secrets(row_text, ...)`（line 4045-4053）仍对输出做 secondary scan，双重防护

**owner contract 验证**: 即使脱敏步骤因未知 credential（已轮换）未完全清除旧值，scanner 的 `scan_secrets` 仍用 `canaries=(SECRET_CANARY_PREFIX,)` + `credential_values=credential_values` 做闭合检测，fail closed。

---

## F02 处置详情：RESOLVED

**原 finding**: live run 中 `effective_identity = expected_identity`（同一对象引用），`evaluate_no_fallback` 的 `effective_identity_mismatch` 原因码永远不触发。

### Fix 架构

修复引入了独立的 identity 派生路径：

```
expected_identity                           effective_identity
       │                                            │
       ▼                                            ▼
_expected_provider_identity()              ProviderIdentity(
    │                                        family_id=ordinary.provider,
    ├─ ConfigLoader(                         provider=ordinary.provider,
    │   package_config_dir                    provider_model=ordinary.provider_model,
    │  ).load_models()                       )
    │  → models.models[thinking_model_id]        │
    │  → model_family_identity()                 │
    │                                            ▼
    └─ ProviderIdentity(                 来自 production assembly
         family_id=choice.expected_provider,  (_read_effective_identities
         provider=choice.expected_provider,   → entrypoint_runtime
         provider_model=expected_family       → host_assembly
           .provider_model,                   → ordinary_selection.model
       )                                      → model_family_identity)
```

### 数据同源证明

**`_expected_provider_identity`（line 3120-3161）的独立性**：

1. 参数只接收 `choice: InitModelChoice` 和 `package_config_root: Path`
2. `ConfigLoader(package_config_dir=package_config_root).load_models()` **不传** `workspace_config_dir`（line 3144-3146），确保只读冻结 package models，不读 workspace publication
3. `expected_family = model_family_identity(expected_model)`（line 3152）— 与 production assembly 使用同一 `model_family_identity` 纯函数，但输入来自不同数据源（package models vs assembly selection）
4. 额外守卫：`expected_family.provider != choice.expected_provider` → `ManifestValidationError`（line 3153-3156），防止 package models 与 init catalog 不一致

**`effective_identity`（line 3337-3341）的独立性**：

```python
effective_identity = ProviderIdentity(
    family_id=ordinary.provider,
    provider=ordinary.provider,
    provider_model=ordinary.provider_model,
)
```

- `ordinary` 来自 `_read_effective_identities` → `prepare_entrypoint_runtime` → `host_assembly.ordinary_selection.model`
- 这个路径是 production Service assembly 的完整链路，不经过 ConfigLoader 或 package models
- 当 `ordinary is None`（assembly 失败），`effective_identity` 也为 `None`

**缺 identity 的 fail-closed 行为**（`evaluate_no_fallback:2047-2071`）：

```
request_attempted=True:
  ├─ expected_identity is None → "expected_identity_missing"
  ├─ effective_identity is None → "effective_identity_missing"
  ├─ effective_identity != expected_identity → "effective_identity_mismatch"
  ├─ observed_set - {expected_identity} nonempty → "alternate_identity_observed"
  └─ expected_identity not in observed_set → "expected_identity_not_observed"
```

- 新增 test `test_evaluate_no_fallback_requires_independent_identities_for_request`（test:1624）验证：`request_attempted=True` + 两个 identity 均为 `None` → `reason_codes = {"effective_identity_missing", "expected_identity_missing", "expected_identity_not_observed"}` → `passed=False`
- 新增 test `test_evaluate_no_fallback_accepts_clean_preflight_failure`（test:1595）验证：`request_attempted=False` + identity 均为 `None` → `passed=True`（无请求则无 fallback 可检测）
- 新增断言（test:2077-2078）：`choice.thinking_model_id != expected.provider_model`，证明 expected identity 的 `provider_model` 字段来自 package models 解析（`"gpt-5.4"`），与 `choice.thinking_model_id`（`"gpt-5.4-thinking"`）是不同的语义层
- 新增断言（test:2083-2087）：`expected == ProviderIdentity(family_id=ordinary.provider, ...)`，证明 expected（从 package models）与 effective（从 assembly）在正常配置下收敛——这是**验证收敛**，不是**构造等价**

### 关键验证：`effective_identity_mismatch` 不再死代码

在修复前：
```python
effective_identity = expected_identity  # 永真
evaluate_no_fallback 中 effective_identity != expected_identity 永假
```

在修复后：
```python
expected_identity = _expected_provider_identity(choice, package_config_root)  # ConfigLoader
effective_identity = ProviderIdentity(family_id=ordinary.provider, ...)       # Assembly
```

如果 production assembly 因任何原因（配置损坏、fallback、版本漂移）使用了与 package models 不同的 provider/model，`effective_identity_mismatch` 会触发。**原因码不再是死代码**。

---

## F03 处置详情：REJECTED-WITH-REASON

**原 finding**: 空 canary 探针回退到 `SECRET_CANARY_PREFIX`（`"s5b-canary-"`）可能导致合法文件中出现该前缀时误报。

**Controller 裁决**: REJECTED-WITH-REASON — 这是 intentional fail-closed 设计。

**证明**:

新增测试 `test_persisted_scan_legacy_canary_prefix_fails_closed`（test:1444-1481）：

```python
row_root = (tmp_path / "row").resolve()
artifact = row_root / "workspace/config/models.json"
artifact.parent.mkdir(parents=True)
artifact.write_text(
    '{"probe":"s5b-canary-legacy-value"}',
    encoding="utf-8",
)

report = scan_persisted_secrets(
    row_root,
    credential_values=(),
    canaries=(),  # 空 → 回退到 SECRET_CANARY_PREFIX
)

assert not report.passed
assert report.violations == (
    PersistedSecretViolation(
        violation_code="persisted_secret_canary",
        artifact_class=PersistedArtifactClass.CONFIG,
        count=1,
    ),
)
```

该测试明确证明：
1. 空 `canaries=()` 不会禁用 canary 检测——它回退到前缀扫描
2. 任何包含 `"s5b-canary-"` 前缀的内容都被检测为 `persisted_secret_canary` violation
3. 这是**有意的 fail-closed 设计**：不知道确切 canary 时宁可误报，不可漏检

**拒绝理由的充分性**:
- 前缀 `"s5b-canary-"` 出现在 CI-owned row root artifact 中的概率极低（row root 下主要是 init publication JSON 和 Host SQLite/WAL binary）
- CI 文档 (`docs/cli_ci.md`) 已明确约束扫描行为，CI 维护者知道不应在 CI artifact 中使用该前缀
- 如果未来有合法 artifact 需要包含该前缀，解决方案是在该 row 的 live run 中保留确切 canary UUID（而非 reconciliation 的空 canaries），或通过 accepted oracle 明确声明特定 artifact class 豁免

---

## F04 处置详情：RESOLVED

**原 finding**: `reconcile_existing_report` 中 `row["internal_contract_valid"]` 写入 dict 后立即从 dict 读回传入 `_reconciled_availability_class`，冗余的 dict 读写往返。

**Fix**: line 4021-4029 提取了局部变量：

```python
# line 4021-4024（修复后）
reconciled_internal_contract_valid = (
    internal_contract_valid and persisted_scan.passed
)
row["internal_contract_valid"] = reconciled_internal_contract_valid
row["availability_class"] = _reconciled_availability_class(
    row,
    internal_contract_valid=reconciled_internal_contract_valid,  # 局部变量
    observation=observation,
).value
```

- `reconciled_internal_contract_valid` 作为局部变量，直接传入 `_reconciled_availability_class`
- 不再通过 `row.get("internal_contract_valid")` 读回
- `row["internal_contract_valid"] = reconciled_internal_contract_valid` 仍写入 dict（JSON 序列化需要），但函数调用不再依赖这个 dict key

---

## 补充验证

### 非 requestable preview 脱敏后不会被 scanner 自判失败

验证链路（`_reconcile_terminal_summary` → `scan_secrets`）：

1. **脱敏阶段**（line 3626-3633）：`_redact_sensitive_text` 的参数 `credential_values=credential_values` 使用 `reconcile_existing_report` 作用域中的同一 `credential_values`（来自 `_known_credential_values(process_env)`，line 3976）
2. **扫描阶段**（line 4045-4053）：`scan_secrets(row_text, canaries=(SECRET_CANARY_PREFIX,), credential_values=credential_values, ...)` 使用同样的 `credential_values`
3. **闭合性**：如果脱敏成功移除了所有 credential value，扫描不会命中 `credential_value` finding code。如果脱敏未覆盖某个值（如 credential 中嵌入了 request-id pattern），扫描的 regex patterns（`AUTHORIZATION_PATTERN`、`BEARER_PATTERN`、`CREDENTIAL_VALUE_PATTERN`、`REQUEST_ID_VALUE_PATTERN`）会兜底检测
4. **canary 边界**：脱敏使用 `canary="legacy-canary-value-unavailable"`（不知道确切旧 canary），故不能移除旧 canary。但扫描使用 `canaries=(SECRET_CANARY_PREFIX,)`，会检测到任何 `"s5b-canary-"` 前缀 → fail closed（与 F03 的 intentional design 一致）
5. **路径边界**：脱敏和扫描都使用同一组 `forbidden_path_prefixes=(project_root, run_root, workspace_root)`。脱敏做精确替换，扫描做子串检测——如果脱敏遗漏了某个 root，扫描会捕获

**结论**: 脱敏与扫描共享同一 credential/probe 来源，扫描是脱敏的闭合验证。不会出现"脱敏后的 canonical redacted output 被 scanner 自判失败"的矛盾——scanner 只会因脱敏未覆盖的残留而失败，这正是期望的 fail-closed 行为。

### `_expected_provider_identity` 的 ConfigLoader 独立性

- `ConfigLoader(package_config_dir=package_config_root).load_models()` 未传 `workspace_config_dir` 参数
- `load_models` 的 `workspace_config_dir=None` 默认值时，函数仅从 `package_config_dir / "models.json"` 读取（line 745-748 of `config_loader.py`）
- 不读取 workspace publication、不依赖 init 结果、不涉及 Host runtime state
- `model_family_identity(expected_model)` 是 `dayu.runtime.assembly` 的纯函数，仅做 typed field projection，无 side effect

**结论**: `_expected_provider_identity` 是真正的独立派生路径，与 production assembly 路径无共享可变状态。

### `alternate_success_observed` 的 expected_identity None 守卫

修复后的 `_run_matrix_row:3359-3366`：
```python
alternate_success_observed=(
    response_received
    and expected_identity is not None
    and any(
        identity != expected_identity
        for identity in observed_identities
    )
),
```

- 增加了 `expected_identity is not None` 守卫（line 3361）
- 当 assembly 失败导致 `ordinary is None` → `expected_identity = None` 时，`alternate_success_observed` 恒为 False
- 避免了 `None != identity` 的比较（在 Python 中合法但语义错误——不应在不知道 expected identity 时推断 alternative success）

---

## Final Disposition Summary

| ID | Severity | Status | Evidence |
|----|----------|--------|----------|
| F01 | 中 | RESOLVED | `_reconcile_terminal_summary:3626-3633` — `_redact_sensitive_text` replaces `_redact_explicit_path_prefixes` |
| F02 | 中 | RESOLVED | `_expected_provider_identity:3120-3161` — ConfigLoader-derived expected ≠ assembly-derived effective; None → fail closed |
| F03 | 中 | REJECTED-WITH-REASON | `test_persisted_scan_legacy_canary_prefix_fails_closed:1444` — intentional fail-closed |
| F04 | 低 | RESOLVED | `reconcile_existing_report:4021-4029` — local variable eliminates dict round-trip |

**70 tests passed. pyright 0 errors, 0 warnings, 0 informations.**

---

## 第 3 轮 Follow-up：F02 Retained-Report No-Fallback Provenance

Controller 补齐了 reconciliation 路径的 no-fallback 重算：reconciliation 现忽略旧 `no_fallback` verdict，按 canonical evidence 独立重算并覆盖。本轮只复审该增量。

### 增量范围

- `_reconciled_no_fallback_verdict`（新函数，line 4036-4147）
- `_row_effective_provider_identity`（新函数，line 3943-3973）
- `_row_runner_call_identities`（新函数，line 3976-4012）
- `_optional_row_host_run_id`（新函数，line 4015-4029+）
- `_expected_provider_identity` 增加 `workspace_config_root` 参数（line 3149-3207）
- `DYNAMIC_CHOICE_KINDS`（新常量，line 91-96）
- `reconcile_existing_report` 调用 `_reconciled_no_fallback_verdict` 替代旧读取（line 4263-4274）
- `_run_matrix_row` 同步使用 `DYNAMIC_CHOICE_KINDS` 分支（line 3379-3387）
- 测试：`test_ollama_expected_identity_uses_init_owned_dynamic_truth`（test:505）、`test_reconciliation_recomputes_contract_from_owner_evidence` 增强（test:2318）

### 结论：**PASS。无新增 findings。** 71 tests passed. pyright 0 errors.

### 1. Reconciliation 忽略旧 no_fallback — 验证通过

**证明**: `_reconciled_no_fallback_verdict` 函数体（line 4036-4147）中**没有任何**对 `row["no_fallback"]` 或 `row.get("no_fallback")` 的读取。唯一读取的 row 字段为：
- `row["ordinary_identity"]` → `_row_effective_provider_identity`（effective identity）
- `row["runner_calls"]` → `_row_runner_call_identities`（仅在无 Host observation 分支）
- `row["host_run_id"]` → `_optional_row_host_run_id`（仅在无 Host observation 分支）
- `row["request_attempted"]`、`row["successful_response_received"]` → 布尔守卫

旧 verdict 被完全忽略，新 verdict 通过 `row["no_fallback"] = _no_fallback_json(no_fallback)`（line 4274）覆盖写入。

**测试验证**（test:2318-2462）：构造了一个 `no_fallback=NoFallbackVerdict(passed=False, fallback_observed=True, reason_codes=("stale_old_live_verdict",))` 的旧 row，`_reconciled_no_fallback_verdict` 返回 `passed=True, fallback_observed=False, reason_codes=()` ——证明旧 verdict 被完全忽略且 canonical evidence 正确恢复了正确裁决。

### 2. Expected Identity 三源派生 — 验证通过

`_expected_provider_identity` 现根据 choice kind 选择 expected model 的数据源：

| Choice kind | `workspace_config_root` | ConfigLoader 行为 | 示例 |
|------------|------------------------|-------------------|------|
| Static（大部分） | `None` | 仅读 `package_config_dir / "models.json"` | P01 mimo-token-plan → provider_model from package |
| Dynamic（Ollama, custom-openai） | `workspace_root / "config"` | 先读 package 再 layer workspace override | P14 ollama → `qwen3:8b` from init-owned config |

**入口守卫**（line 3179-3189）：
```python
dynamic_choice = choice.kind in DYNAMIC_CHOICE_KINDS
if dynamic_choice:
    if workspace_config_root is None or not workspace_config_root.is_absolute():
        raise ManifestValidationError(...)
elif workspace_config_root is not None:
    raise ManifestValidationError("static choice 不得读取 workspace expected truth")
```

- Static choice 传入 `workspace_config_root` → **直接拒绝**，防止 static choice 意外从 workspace 读取 expected truth
- Dynamic choice 不传 `workspace_config_root` → **直接拒绝**，防止 dynamic choice 回退到 package placeholder

**ConfigLoader 层叠行为**: `ConfigLoader.load_models(workspace_config_dir=workspace_config_root)` 在 `workspace_config_dir` 非 None 时，先加载 package models 作为 base，再用 workspace models 覆盖。Ollama 的 package `models.json` 中 `ollama` entry 是 `provider: "ollama"` 的 template（model_name 为 placeholder），workspace `models.json` 中 `ollama` entry 的 `model` 字段被 init 替换为 `"qwen3:8b"`。`model_family_identity` 从覆盖后的 `ModelConfig` 提取 `provider_model`。

**测试验证**（test:505-531）：
```python
expected = _expected_provider_identity(
    find_init_model_choice("ollama"),
    PACKAGE_CONFIG_ROOT,
    workspace_config_root=ollama_publication_tree / "config",
)
assert expected == ProviderIdentity(
    family_id="ollama", provider="ollama", provider_model="qwen3:8b",
)
```
验证 Ollama expected `provider_model` 来自 init publication (`qwen3:8b`)，不是 package template placeholder，也不是 assembly actual。

### 3. Effective Identity 来源 — 验证通过

`_row_effective_provider_identity`（line 3943-3973）从 retained row 的 `ordinary_identity` 投影读取：

```python
ordinary_value = row.get("ordinary_identity")
if ordinary_value is None:
    return None
ordinary = _expect_mapping(ordinary_value, "row.ordinary_identity")
provider = _expect_string(ordinary.get("provider"), ...)
return ProviderIdentity(
    family_id=provider,
    provider=provider,
    provider_model=_expect_string(ordinary.get("provider_model"), ...),
)
```

- 来源是 row JSON 中 retained 的 assembly projection（由原始 live run 的 `_read_effective_identities` → `production assembly` 产生并写入）
- Reconciliation **不重新调用** `_read_effective_identities` 或任何 assembly——这是 retained evidence，不是 re-derived evidence
- 当 `ordinary_identity` 为 null（assembly 未发生）→ 返回 `None` → `evaluate_no_fallback` 的 `effective_identity_missing` 触发

### 4. Reconciliation No-Fallback 三分支覆盖

`_reconciled_no_fallback_verdict` 的三个分支及其证据来源：

| 分支 | 条件 | expected 来源 | effective 来源 | runner calls 来源 | run binding 来源 | request/response 来源 |
|------|------|-------------|---------------|-------------------|-----------------|---------------------|
| **A: Host evidence** | `observation is not None` | `_expected_provider_identity`（package 或 package+workspace） | `_row_effective_provider_identity`（retained assembly） | `observation.runner_calls`（Host canonical） | `observation.host_run_id`（Host canonical） | `observation.request_attempted` / `observation.successful_response_received`（Host canonical） |
| **B: request_attempted, no Host** | `observation is None` + `request_attempted=True` | `_expected_provider_identity` | `_row_effective_provider_identity` | 空（`()`） | `None`（缺失 → `run_binding_mismatch`） | row retained |
| **C: no request** | `observation is None` + `request_attempted=False` | `_expected_provider_identity`（仅当 effective_identity 非 None 时） | `_row_effective_provider_identity` | `_row_runner_call_identities`（row retained） | `_optional_row_host_run_id`（row retained） | row retained |

- **分支 A** 是正常路径：Host canonical evidence 完整，从 Host 读取 runner calls、run binding、request/response facts
- **分支 B** 是异常路径：row 声称有请求但 Host 不可用 → 缺失 Host evidence → `run_binding_mismatch` + `expected_identity_not_observed` → fail closed
- **分支 C** 是 non-requestable 路径：检查 retained facts 无矛盾（无 request 但不应有 run binding/observed identities）→ 通过

### 5. Live Run 与 Reconciliation 的 DYNAMIC_CHOICE_KINDS 同源

两处调用使用完全一致的分支条件：

```python
# Live run (_run_matrix_row:3382-3386)
workspace_config_root=(
    workspace_root / "config"
    if choice.kind in DYNAMIC_CHOICE_KINDS
    else None
),

# Reconciliation (reconcile_existing_report:4267-4270)
workspace_config_root=(
    workspace_root / "config"
    if choice.kind in DYNAMIC_CHOICE_KINDS
    else None
),
```

两者对 `DYNAMIC_CHOICE_KINDS = frozenset({OLLAMA, CUSTOM_OPENAI})` 的解释一致，确保同一种 choice 在 live run 和 reconciliation 中使用相同的 expected identity 派生路径。

### 6. Residual Note: `_row_runner_call_identities` 仅用于分支 C

`_row_runner_call_identities` 的 docstring（line 3976-3983）明确：
> 该投影只用于无 Host observation 的 non-requestable contradiction 检查；requestable reconciliation 必须使用 Host canonical runner calls。

分支 A（有 Host observation）使用 `observation.runner_calls`（Host canonical），分支 B（request_attempted 无 Host）使用空 tuple → 触发 `expected_identity_not_observed`。分支 C（无 request）使用 `_row_runner_call_identities` 作为 contradiction 检查——如果 retained row 中有 runner calls 但声称无 request → `identity_observed_without_request` → fail closed。

**结论**: `_row_runner_call_identities` 的使用范围被严格限制在 non-requestable contradiction 检查，不会与 Host canonical runner calls 混淆。

---

## Final Disposition Summary（第 3 轮更新）

| ID | Severity | Status | Round | Evidence |
|----|----------|--------|-------|----------|
| F01 | 中 | RESOLVED | 2 | `_reconcile_terminal_summary:3626-3633` — `_redact_sensitive_text` replaces `_redact_explicit_path_prefixes` |
| F02 | 中 | RESOLVED | 2+3 | R2: `_expected_provider_identity` — ConfigLoader-derived expected ≠ assembly-derived effective; None → fail closed. R3: `_reconciled_no_fallback_verdict` — ignores old verdict, recomputes from canonical evidence; Ollama expected from init-owned workspace config |
| F03 | 中 | REJECTED-WITH-REASON | 2 | `test_persisted_scan_legacy_canary_prefix_fails_closed` — intentional fail-closed |
| F04 | 低 | RESOLVED | 2 | `reconcile_existing_report:4021-4029` — local variable eliminates dict round-trip |

**71 tests passed. pyright 0 errors, 0 warnings, 0 informations.**

**最终 verdict: PASS. 无 blocking findings. 无新增 findings.**
