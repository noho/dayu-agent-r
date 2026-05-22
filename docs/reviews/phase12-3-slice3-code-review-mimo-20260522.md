# Phase 12.3 Slice 3 Code Review - AgentMiMo - 2026-05-22

## Verdict

**BLOCKING FINDINGS PRESENT** — 需修复后重新审查。

## 审查范围

- 设计真源：`docs/host/design.md`
- Plan artifact：`docs/host/phase12-3-config-usage-governance-plan.md`
- Implementation artifact：`docs/reviews/phase12-3-slice3-implementation-codex-20260522.md`
- 未提交 diff 中属于 Phase 12.3 Slice 3 的改动（9 个文件，+672/-40 行）

## 检查清单

### 1. 默认 config 分档 ✅ PASS

`dayu/config/execution_profiles.json` 提供四个 profile：
- `standard-256k`（context_window_class=256k, min=262144）
- `standard-1m`（context_window_class=1m, min=1000000）
- `wechat-256k`（context_window_class=256k, min=262144）
- `wechat-1m`（context_window_class=1m, min=1000000）

`default_execution_profile_id` 为 `standard-256k`。每个 profile 内嵌完整 `agent_policy`。

### 2. 不保留 old standard profile alias ❌ BLOCKING

**发现 #1（Severity: HIGH）**：`tests/runtime/test_smoke_host_public_multiturn_assembly.py` 存在破坏性旧 `standard` profile id 残留。

**证据**：
- `tests/runtime/test_smoke_host_public_multiturn_assembly.py:127`：`execution_profile_id="standard"`
- `tests/runtime/test_smoke_host_public_multiturn_assembly.py:62`：`assert assembly.diagnostics.execution_profile_id == "standard"`
- 运行 `pytest tests/runtime/test_smoke_host_public_multiturn_assembly.py` 失败，错误：`RuntimeAssemblySelectionError: execution profile not found: standard`

**复现**：
```bash
source .venv/bin/activate && pytest tests/runtime/test_smoke_host_public_multiturn_assembly.py -q
```

输出：
```
E   dayu.runtime.assembly.RuntimeAssemblySelectionError: execution profile not found: standard
1 failed, 2 passed
```

**影响**：这是当前 Slice 3 必须修的破坏性残留。旧 `standard` profile 已被删除，但 smoke test 仍引用它。该测试不在 Slice 3 允许修改清单内，但属于 Slice 4 aggregate sweep 范围。

**建议**：该残留应明确转入 Slice 4 aggregate sweep。Implementation artifact 已识别此风险（Residual Risk 第2点），但 review 需确认这是可分类的已知风险而非遗漏。

**分类**：**可转入 Slice 4**。理由：
1. 该测试文件不在 Slice 3 allowed files 列表内
2. Implementation artifact 已明确记录此风险
3. Slice 4 scope 明确允许"修正 Slice 1-3 已触及文件中的遗漏"
4. 该测试失败不影响 Slice 3 生产代码正确性

### 3. context_window_class / min_context_window_tokens fail fast ✅ PASS

`dayu/runtime/config_loader.py`：
- `ExecutionProfileConfig` 新增 `context_window_class: str` 和 `min_context_window_tokens: int`（:344-345）
- `_parse_execution_profile` exact fields 包含这两个字段（:1210-1211）
- `_parse_execution_profile_context_window_class` 校验只允许 `256k` / `1m`（:1288-1305）
- `_require_positive_int_field` 校验正整数

测试覆盖：
- `test_execution_profile_context_window_class_is_closed_enum`：非法 class 被拒绝
- `test_execution_profile_min_context_window_tokens_must_be_positive`：0 和 -1 被拒绝

### 4. resolved profile 完整内嵌 agent_policy ✅ PASS

每个 execution profile 直接内嵌完整 `agent_policy` block，字段一比一对齐 `AgentPolicyConfig`。测试 `test_default_runtime_config_files_load_as_typed_views` 验证每个 profile 的 `agent_policy.continuation_prompt` 非空且 `max_consecutive_failed_tool_batches == 2`。

### 5. runtime compatibility helper 只校验和诊断 ✅ PASS

`dayu/runtime/assembly.py:363-405`：
- `validate_execution_profile_context_window` 只做 fail-fast 校验和诊断
- 不读取 catalog 默认 profile
- 不返回替代 profile id（`ExecutionProfileCompatibilityDiagnostic` 无 `alternative_profile_id` 字段）
- 不自动切换 profile
- 不 import Service / Host / Engine

测试 `test_execution_profile_compatibility_helper_does_not_rewrite_selection` 验证不改输入、不返回替代 id。

### 6. Service helper 不根据 model context 自动切换 ✅ PASS

`dayu/service/host_assembly.py`：
- `_select_execution_profile_id`（:516-531）只根据 `explicit_profile_id` 或 `config.execution_profiles.default_execution_profile_id` 选择
- 不读取 selected model 的 `context_window_tokens`

测试 `test_default_profile_does_not_auto_switch_for_1m_model` 验证默认 profile 使用 `default_execution_profile_id`，不按模型窗口自动切换。

### 7. 1m profile + 256K model fail fast ✅ PASS

`dayu/runtime/assembly.py:382-389`：当 `model.context_window_tokens < profile.min_context_window_tokens` 时抛 `RuntimeAssemblySelectionError`。

测试：
- `test_execution_profile_1m_and_256k_model_fails_fast`（runtime）
- `test_explicit_1m_profile_with_256k_model_fails_fast`（service）

### 8. 256k profile + 1M model 允许且 diagnostic conservative ✅ PASS

`dayu/runtime/assembly.py:623-643`：`_profile_context_window_status` 当 `profile_class == "256k"` 且 `model_context_window_tokens >= 1000000` 时返回 `"conservative"`。

测试：
- `test_execution_profile_256k_and_1m_model_is_conservative`（runtime）
- `test_default_profile_does_not_auto_switch_for_1m_model`（service，验证 `status == "conservative"`）

### 9. diagnostics 可见性 ✅ PASS

`ServiceOpenHostAssemblyDiagnostics` 新增：
- `ordinary_profile_compatibility: ExecutionProfileCompatibilityDiagnostic`
- `compactor_profile_compatibility: ExecutionProfileCompatibilityDiagnostic`

`ExecutionProfileCompatibilityDiagnostic` 包含：`profile_id`、`context_window_class`、`min_context_window_tokens`、`selected_model_id`、`model_context_window_tokens`、`status`。

测试 `test_compose_open_host_options_uses_runtime_tuning_from_config` 验证 diagnostics 中 profile id、selected model id 和 status 可见。

### 10. dayu.runtime import boundary ✅ PASS

运行 `pytest tests/runtime/test_import_boundary.py tests/runtime/test_weak_typing_guard.py` 通过（13 passed）。

新增的 `validate_execution_profile_context_window` 和 `ExecutionProfileCompatibilityDiagnostic` 位于 `dayu.runtime.assembly`，只 import `dayu.runtime.config_loader` 的类型，不 import Host / Engine / Service。

### 11. pyright ✅ PASS

```
python -m pyright dayu/runtime dayu/service tests/runtime tests/service
0 errors, 0 warnings, 0 informations
```

### 12. README 同步 ✅ PASS

- `dayu/config/README.md`：已更新 profile id 示例为 `standard-256k`，说明 `context_window_class` / `min_context_window_tokens`，说明 compatibility helper 只校验不切换
- `tests/README.md`：已更新 config loader 测试覆盖说明

### 13. whitespace ✅ PASS

`git diff --check` 无输出。

## Blocking Findings

### Finding #1：旧 `standard` profile id 残留导致 smoke test 失败

**Severity**: HIGH
**File**: `tests/runtime/test_smoke_host_public_multiturn_assembly.py:127, 62`
**Evidence**:
```python
# 第127行
execution_profile_id="standard",

# 第62行
assert assembly.diagnostics.execution_profile_id == "standard"
```

**Reproduction**:
```bash
source .venv/bin/activate && pytest tests/runtime/test_smoke_host_public_multiturn_assembly.py -q
# 输出：RuntimeAssemblySelectionError: execution profile not found: standard
```

**Root Cause**: Slice 3 删除了旧 `standard` profile id 并改为 `standard-256k`，但该 smoke test 文件不在 Slice 3 allowed files 内，因此未被修改。

**建议修复**：转入 Slice 4 aggregate sweep，将 `execution_profile_id="standard"` 改为 `execution_profile_id="standard-256k"`，并更新对应断言。

**Classification**: 可明确转入 Slice 4。Implementation artifact 已识别此风险（Residual Risk 第2点），Slice 4 scope 允许修正 Slice 1-3 已触及文件中的遗漏。

## 非阻塞观察

### Observation #1：四个 profile baseline 参数完全相同

`standard-256k`、`standard-1m`、`wechat-256k`、`wechat-1m` 的 `run_baseline`、`compactor_baseline`、`context_budget_policy`、`memory_projection_policy`、`tool_truncation_policy` 和 `agent_policy` 参数值完全相同（仅 `policy_ref` 不同）。

**评估**：符合 plan 预期。Plan 明确允许"wechat-* 可以与 standard-* 共享 baseline，但必须保留独立 profile id"。当前没有已确认的 WeChat 业务参数差异，因此不硬编码无来源的行为差异是正确的。

### Observation #2：conservative 判断逻辑可扩展性

`_profile_context_window_status` 当前只判断 `256k profile + 1M model -> conservative`，其余均为 `compatible`。未来若新增更多分档（如 `128k`、`2m`），需扩展此逻辑。

**评估**：当前实现符合设计文档要求，且逻辑清晰。未来扩展时修改范围可控。

## 验证结果汇总

| 验证项 | 结果 |
|--------|------|
| `pytest tests/runtime/test_config_loader.py tests/runtime/test_assembly_helpers.py tests/service/test_host_assembly.py` | 51 passed |
| `pytest tests/runtime/test_import_boundary.py tests/runtime/test_weak_typing_guard.py` | 13 passed |
| `pyright dayu/runtime dayu/service tests/runtime tests/service` | 0 errors |
| `git diff --check` | clean |
| `pytest tests/runtime/test_smoke_host_public_multiturn_assembly.py` | **1 failed**（已知残留） |

## 结论

Slice 3 生产代码实现正确，满足 plan 所有 acceptance criteria。唯一 blocking finding 是 `test_smoke_host_public_multiturn_assembly.py` 的旧 `standard` profile id 残留，该残留已由 implementation artifact 识别，可明确转入 Slice 4 aggregate sweep 修复。

**Verdict**: 需确认 Finding #1 分类后，Slice 3 可标记为 PASS_WITH_KNOWN_RESIDUAL。
