# Phase 12.3 Slice 3 Code Review — AgentDS — 2026-05-22

## Verdict: PASS（含 2 个 Non-Blocking Findings、1 个 Deferred Risk）

本 Slice 3 实现符合 Phase 12.3 plan artifact 的 scope 与 acceptance criteria。所有 focused tests（51）、import boundary tests（13）、weak typing guard 全数通过，pyright 零新增报错，`git diff --check` 干净。

---

## 审查清单逐项验证

### 1. 默认 config 是否提供 standard-256k、standard-1m、wechat-256k、wechat-1m，且不保留 old standard profile alias

**PASS。**

证据：
- `dayu/config/execution_profiles.json:2` — `default_execution_profile_id` = `"standard-256k"`
- `dayu/config/execution_profiles.json:3-269` — 四个 profile `standard-256k` / `standard-1m` / `wechat-256k` / `wechat-1m` 均显式声明完整字段，无 `extends` 共享
- `rg -n '"standard"' dayu/config/execution_profiles.json` → 无输出（不存在名为 `"standard"` 的旧 profile alias）
- `tests/runtime/test_config_loader.py:286-293` — 断言四类 profile 存在且为 default config 子集

### 2. context_window_class / min_context_window_tokens schema 是否 fail fast

**PASS。**

证据：
- `dayu/runtime/config_loader.py:55-57` — `_EXECUTION_PROFILE_CONTEXT_WINDOW_CLASSES = frozenset({"256k", "1m"})`
- `dayu/runtime/config_loader.py:1209-1221` — `_parse_execution_profile` exact fields 包含 `context_window_class` 和 `min_context_window_tokens`
- `dayu/runtime/config_loader.py:1291-1306` — `_parse_execution_profile_context_window_class` 拒绝非 `256k` / `1m` 的值
- `dayu/runtime/config_loader.py:1235-1238` — `min_context_window_tokens` 使用 `_require_positive_int_field`
- `tests/runtime/test_config_loader.py:613-654` — `test_execution_profile_context_window_class_is_closed_enum` + `test_execution_profile_min_context_window_tokens_must_be_positive` 均覆盖

### 3. resolved profile 是否完整内嵌 agent_policy

**PASS。**

证据：
- `dayu/config/execution_profiles.json:59-68` 等处 — 每条 profile 均直接在 record 内写 `"agent_policy": {...}` 
- `dayu/runtime/config_loader.py:1220` — exact fields 要求 `"agent_policy"`
- `dayu/runtime/config_loader.py:1518-1557` — `_parse_agent_policy` 校验所有 8 个字段，fallback_mode 枚举门控
- `tests/runtime/test_config_loader.py:159-176` — `_agent_policy_record()` fixture 包含所有字段
- `tests/runtime/test_config_loader.py:296-306` — `test_default_runtime_config_files_load_as_typed_views` 断言 `agent_policy.max_iterations == 24` 及 continuation_prompt 非空

### 4. runtime compatibility helper 是否只校验和诊断，不读取 catalog、不返回替代 profile、不自动切换

**PASS。**

证据：
- `dayu/runtime/assembly.py:366-399` — `validate_execution_profile_context_window` 签名只接收 `profile` + `model`，不接收 catalog/config
- `dayu/runtime/assembly.py:389-398` — 返回 `ExecutionProfileCompatibilityDiagnostic`，不包含替代 profile id
- `tests/runtime/test_assembly_helpers.py:320-336` — `test_execution_profile_compatibility_helper_does_not_rewrite_selection` 确认 `"alternative_profile_id"` 不在 diagnostic fields 中
- `dayu/runtime/assembly.py:1-7` — 模块无 `dayu.engine` / `dayu.host` / `dayu.service` / `dayu.ui` / `dayu.fins` import

### 5. Service helper 是否仍只按 explicit override 或 default_execution_profile_id 选择 profile；不得根据 model context 自动切换

**PASS。**

证据：
- `dayu/service/host_assembly.py:509-527` — `_select_execution_profile_id` 逻辑：`explicit_profile_id or config.execution_profiles.default_execution_profile_id`
- 该函数不接收模型对象，不检查 `context_window_tokens`，不做任何窗口比较
- `tests/service/test_host_assembly.py:310-368` — `test_default_profile_does_not_auto_switch_for_1m_model` 断言：默认选择 `standard-256k`，即使模型为 1M class

### 6. 1m profile + 256K model 是否 fail fast；256k profile + 1M model 是否允许且 diagnostic conservative

**PASS。**

证据：
- `dayu/runtime/assembly.py:381-388` — `model.context_window_tokens < profile.min_context_window_tokens` 时 raise `RuntimeAssemblySelectionError`
- `dayu/runtime/assembly.py:626-642` — `_profile_context_window_status`：256k profile + >=1M model → `"conservative"`
- `tests/runtime/test_assembly_helpers.py:288-299` — `test_execution_profile_1m_and_256k_model_fails_fast`
- `tests/runtime/test_assembly_helpers.py:302-317` — `test_execution_profile_256k_and_1m_model_is_conservative`
- `tests/service/test_host_assembly.py:248-307` — `test_explicit_1m_profile_with_256k_model_fails_fast` 在 Service 层端到端验证

### 7. diagnostics 是否能看到 profile id、selected model id、window tokens 和 status

**PASS。**

证据：
- `dayu/runtime/assembly.py:141-158` — `ExecutionProfileCompatibilityDiagnostic` 字段：`profile_id`、`context_window_class`、`min_context_window_tokens`、`selected_model_id`、`model_context_window_tokens`、`status`
- `dayu/service/host_assembly.py:172-173` — `ServiceOpenHostAssemblyDiagnostics` 包含 `ordinary_profile_compatibility` 和 `compactor_profile_compatibility`，类型均为 `ExecutionProfileCompatibilityDiagnostic`
- `tests/service/test_host_assembly.py:109-120` — 断言 `diagnostics.ordinary_profile_compatibility.status == "conservative"`、`profile_id == "standard-256k"`、`selected_model_id == _MODEL_ID`

### 8. dayu.runtime import boundary 是否仍干净

**PASS。**

证据：
- `tests/runtime/test_import_boundary.py` 全数通过（13 passed）
- `dayu/runtime/assembly.py:17-30` — 仅 import `dayu.contracts`、`dayu.contracts.tool_schema`、`dayu.runtime.config_loader`、`dayu.runtime.scene_prepare`、`dayu.runtime.tool_truncation`
- `rg -n 'dayu.engine|dayu.host|dayu.service|dayu.ui|dayu.fins' dayu/runtime/assembly.py` → 无输出

### 9. 旧 schema 残留扫描

**PASS。**

证据：
- `rg -n 'agent_policy_profiles|agent_policy_profile_id' dayu/config/ dayu/runtime/ dayu/service/` → production code 无命中
- `rg -n '"max_tokens"' dayu/config/models.json dayu/config/execution_profiles.json` → 无输出
- `rg -n 'max_tokens' dayu/runtime/config_loader.py` → 无输出（`RunnerOptionHintConfig` 只包含 temperature/top_p/stream）
- `dayu/config/models.json` → `runner_option_hints` 字段只包含 `temperature`、`top_p`、`stream`
- `dayu/service/host_assembly.py:775` — `max_tokens=None`，Service 默认 path 唯一结果
- `tests/service/test_host_assembly.py:101-103` — 断言 ordinary 和 compactor `runner_options.max_tokens is None`

### 10. JSON 加载 smoke

**PASS。**

- `python -m json.tool dayu/config/models.json` — 不报错（已验证）
- `python -m json.tool dayu/config/execution_profiles.json` — 不报错（已验证）

---

## Finding 1 (Non-Blocking): `ExecutionProfileCompatibilityDiagnostic` 与 `validate_execution_profile_context_window` 未列入 `__all__`

- **严重性**: Low（无运行时影响，仅代码纪律）
- **File/Line**: `dayu/runtime/assembly.py:950-967`
- **证据**: `__all__` 列表在 Slice 1-2 时已有 16 个符号，Slice 3 新增 `ExecutionProfileCompatibilityDiagnostic` (line 141) 和 `validate_execution_profile_context_window` (line 366) 但未追加到 `__all__`。
- **影响**: `from dayu.runtime.assembly import *` 将无法暴露出这两个符号。当前所有调用方使用显式 import，功能不受影响。
- **建议修复**: 将两个符号追加到 `__all__` 列表中。

## Finding 2 (Non-Blocking): `context_window_class` 与 `min_context_window_tokens` 无交叉校验

- **严重性**: Low（per plan，`context_window_class` 仅为 metadata/诊断用途）
- **File/Line**: `dayu/runtime/config_loader.py:1196-1288`
- **证据**: `_parse_execution_profile` 独立校验 `context_window_class`（只允许 `256k`/`1m`）和 `min_context_window_tokens`（正整數），但不检查 `context_window_class="1m"` 时 `min_context_window_tokens >= 1000000` 或类似交叉一致性。
- **影响**: 恶意或错误配置可能导致 `context_window_class: "1m"` 但 `min_context_window_tokens: 262144`，此时 profile 标记为 1M 分档但实际窗口要求为 256K。当前 compatibility helper 以 `min_context_window_tokens` 为准做 fail-fast，因此实际 enforce 语义不受影响。
- **建议**: 可在后续版本增加交叉校验；当前不构成 blocker。

---

## Deferred Risk: `tests/runtime/test_smoke_host_public_multiturn_assembly.py` 旧 `"standard"` profile id 残留

- **Defer to**: Slice 4 Aggregate Sweep
- **证据**:
  1. `tests/runtime/test_smoke_host_public_multiturn_assembly.py:62` — 断言 `assembly.diagnostics.execution_profile_id == "standard"`
  2. `tests/runtime/test_smoke_host_public_multiturn_assembly.py:127` — 传参 `execution_profile_id="standard"`
  3. 运行该测试确认 **失败**: `RuntimeAssemblySelectionError: execution profile not found: standard`
  4. Phase 12.3 plan artifact Slice 3 allowed files/modules（plan:324-335）未包含 `tests/runtime/test_smoke_host_public_multiturn_assembly.py`
  5. Phase 12.3 plan artifact Slice 4（plan:416-417）明确写入 "只允许修正 Slice 1-3 已触及文件中的遗漏"，即 Slice 4 有权修正该文件
  6. Implementation artifact（line 31）已将此识别为 residual risk，标注转入 Slice 4

**判断**: 这是 Slice 3 因删除旧 `"standard"` profile id 导致的 **计划内已知残**留，按 plan artifact 的 Slice scope 分界明确可转入 Slice 4 aggregate sweep。Slice 4 执行 `rg -n "agent_policy_profiles|agent_policy_profile_id"` 旧字段扫描时，应额外检查 `"standard"` 字符串引用并迁移为 `"standard-256k"`。

---

## 验证结果汇总

| 验证项 | 命令 | 结果 |
|---|---|---|
| Focused tests | `pytest tests/runtime/test_config_loader.py tests/runtime/test_assembly_helpers.py tests/service/test_host_assembly.py -q` | **51 passed** |
| Import boundary | `pytest tests/runtime/test_import_boundary.py tests/runtime/test_weak_typing_guard.py -q` | **13 passed** |
| Pyright | `python -m pyright dayu/runtime dayu/service tests/runtime tests/service` | **0 errors, 0 warnings** |
| Whitespace | `git diff --check` | **通过** |
| Smoke test (旧 residue) | `pytest tests/runtime/test_smoke_host_public_multiturn_assembly.py` | **1 failed** (预期 → Slice 4) |
| 旧 schema 扫描 | `rg 'agent_policy_profiles\|agent_policy_profile_id\|runner_option_hints.*max_tokens' dayu/` | **production code 干净** |
| `__all__` 完整度 | manual inspection | **缺 2 符号** (非阻塞) |

---

## Residual Risk Summary

| Risk | Classification | Owner |
|---|---|---|
| `test_smoke_host_public_multiturn_assembly.py` 旧 `"standard"` id | Deferred to Slice 4 | AgentCodex (Slice 4 sweep) |
| `assembly.py` `__all__` 缺新符号 | Non-blocking, fix anytime | AgentCodex |
| `context_window_class` / `min_context_window_tokens` 无交叉校验 | Existing limitation, per plan | — |
| 全量测试未运行 | Per Slice 3 gate spec | AgentCodex (Slice 4 运行全量) |

---

## 是否触及禁止 Public Surface

**否。** 本次改动未修改 `OpenHostOptions`、`SubmitFollowupRequest`、Host public handle/command method、Engine event contract、`RunnerSpec`、`RunnerCallOptions.max_tokens`（仅默认值改为 `None`，public 字段与 explicit override 语义不变）。

---

## 结论

Slice 3 实现质量良好，符合 plan artifact 的各项 acceptance criteria 和 non-goals。无 blocking finding。建议 AgentCodex 在 Slice 4 中：

1. 修复 `tests/runtime/test_smoke_host_public_multiturn_assembly.py` 的 `"standard"` → `"standard-256k"` 迁移
2. 补充 `assembly.py` `__all__` 中的两个遗漏符号
3. 运行全量测试和旧字段扫描确认无其他残留
