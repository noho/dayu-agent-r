# Phase 12.3 Slice 1 Code Review — AgentDS

- Gate：Phase 12.3 Slice 1 code review
- Reviewer：AgentDS（独立审查，不修复、不 commit、不 push）
- Design source：`docs/host/design.md`
- Control doc：`docs/host/implementation-control.md`
- Plan artifact：`docs/host/phase12-3-config-usage-governance-plan.md`
- Implementation artifact：`docs/reviews/phase12-3-slice1-implementation-codex-20260522.md`
- Reviewed diff：working tree vs HEAD on branch `docs/phase12-design-discussion`
- Final verdict：**PASS**
- Date: 2026-05-22

## 1. Executive Summary

Phase 12.3 Slice 1（Config Schema Cleanup）实现质量良好，所有 plan-mandated acceptance criteria 均满足。未发现 blocking finding。代码干净地删除了旧 `agent_policy_profiles`/`agent_policy_profile_id` 间接引用和默认 `max_tokens` schema，ConfigLoader exact field validation 正确 fail-closed，Service assembly 默认 `RunnerCallOptions.max_tokens=None`，`RunnerCallOptions.max_tokens` public explicit override contract 完整保留。

## 2. Verification Evidence

### 2.1 默认 config runner option hints max_tokens 删除

- `rg -n '"max_tokens"' dayu/config/models.json` 无输出，证实所有模型的所有 hint 均已删除 `max_tokens` 字段。
- `git diff` 验证所有 79 个模型的 8 个 hint (write/overview/audit/decision/interactive/prompt/infer/conversation_compaction) 中 `max_tokens` 均被删除，无遗漏。

### 2.2 ConfigLoader 对旧 max_tokens fail fast

- `dayu/runtime/config_loader.py:1149-1158`：`_parse_runner_option_hint` exact fields 现为 `frozenset({"temperature", "top_p", "stream"})`。任何包含 `max_tokens` 的 hint record 会在 `_require_exact_fields` 处以 `"unknown fields"` fail fast。
- `tests/runtime/test_config_loader.py:559-574`：`test_old_runner_hint_max_tokens_fails_fast` 明确覆盖此路径。

### 2.3 RunnerCallOptions.max_tokens public contract 保留

- `dayu/engine/contracts/runner_spec.py:330`：`max_tokens: int | None` 字段仍然存在，docstring 明确 "为 None 表示沿用默认"。
- `dayu/service/host_assembly.py:751-756`：`_runner_options_from_hint` 返回 `max_tokens=None`（默认 config path 的唯一结果）。
- `dayu/engine/runners/openai/payload.py:350-351`：仅当 `options.max_tokens is not None` 时才写入 provider payload，explicit override 行为不受影响。
- `tests/engine/runners/openai/test_payload_build.py:337-343`：`max_tokens=100` explicit override 测试通过，证实 public contract 未被误删。

### 2.4 execution_profiles.json schema 迁移

- 顶层 `agent_policy_profiles` catalog 已删除，替换为每个 profile 内嵌 `agent_policy` block。
- 所有 profile 的 `agent_policy_profile_id` 字段已删除。
- `dayu/runtime/config_loader.py:1478-1517`：`_parse_agent_policy`（原 `_parse_agent_policy_profile`）不再注入 `agent_policy_profile_id`、不再调用 `_require_no_forbidden_id_fields`。
- `dayu/runtime/config_loader.py:645-668`：`load_execution_profiles` 只接受 `default_execution_profile_id` + `execution_profiles`；`map_fields` 只含 `execution_profiles`。
- 旧 `_parse_agent_policy_profile_map`、`_validate_execution_profile_references` 均已物理删除。

### 2.5 Service assembly 只依赖新 schema

- `dayu/service/host_assembly.py:271-278`：直接使用 `execution_profile.agent_policy` 作为 baseline，不再查 `agent_policy_profiles`。
- `dayu/service/host_assembly.py:759-780`：`_agent_policy_defaults_from_config`（原 `_agent_policy_defaults_from_profile`）接受 `AgentPolicyConfig` 类型。
- `dayu/service/host_assembly.py:751-756`：默认 `RunnerCallOptions.max_tokens=None`。
- `dayu/service/host_assembly.py:161`：`ServiceOpenHostAssemblyDiagnostics.agent_policy_profile_id` 已删除。

### 2.6 dayu.runtime import boundary

- `rg 'import dayu\.(engine|host|service|ui|fins)' dayu/runtime/` 无命中（除 `__init__.py` 中禁止性文档字符串外）。
- `pytest tests/runtime/test_import_boundary.py tests/runtime/test_weak_typing_guard.py -q`：13 passed。
- `python -m pyright dayu/runtime dayu/service tests/runtime tests/service tests/engine/test_config_models.py`：0 errors, 0 warnings, 0 informations.

### 2.7 测试覆盖

- 默认 config 加载内嵌 agent policy：`test_default_runtime_config_files_load_as_typed_views` 断言 `agent_policy.max_iterations == 24` 和 `"max_tokens" not in {field.name for field in fields(RunnerOptionHintConfig)}`。
- 旧 runner hint `max_tokens` fail fast：`test_old_runner_hint_max_tokens_fails_fast`。
- 旧 `agent_policy_profile_id` fail fast：`test_old_agent_policy_profile_id_fails_fast`。
- 旧顶层 `agent_policy_profiles` fail fast：`test_old_agent_policy_profiles_catalog_fails_fast`。
- 内嵌 agent_policy 缺字段 fail fast：`test_agent_policy_missing_field_fails_fast`。
- 内嵌 agent_policy 字段类型非法 fail fast：`test_agent_policy_field_type_fails_fast`。
- Service 默认 `max_tokens=None`：`test_compose_open_host_options_uses_runtime_tuning_from_config` 断言 ordinary/compactor `max_tokens is None`。
- Agent policy merge 优先级：`test_merge_agent_policy_config_uses_typed_allowlist_precedence` 使用新 schema 内嵌 `agent_policy`。

### 2.8 README 更新

- `dayu/config/README.md`：删除了 `max_tokens` hint 说明、`agent_policy_profiles` 表项、示例中的 `max_tokens` 字段；新增 inline `agent_policy` 说明和旧字段 fail-fast 声明。
- `tests/README.md`：config loader 行更新为 "旧 execution profile 字段与旧 runner hint `max_tokens` fail fast"。
- 未触及根 `README.md`、`dayu/README.md`、Host README、Engine README，符合 plan README sync 判断。

## 3. Findings

### 3.1 Non-Blocking Observations

**OBS-001: Slice 1 execution_profiles.json 仅有单个 profile**

`dayu/config/execution_profiles.json` 当前仅含 `standard` profile。Plan Slice 3 将新增 `standard-256k`/`standard-1m`/`wechat-256k`/`wechat-1m` 等多 profile。当前单 profile 在 Slice 1 范围内属计划内，非问题。

**OBS-002: ServiceOpenHostAssemblyDiagnostics 移除 agent_policy_profile_id 后未新增替代字段**

`ServiceOpenHostAssemblyDiagnostics.agent_policy_profile_id` 被移除后未新增 `agent_policy_source: str` 或等价字段。Plan Section 7 对此场景给出 "或只保留 `agent_policy_sources`" 选项，因此不构成 plan 违反。若 future Slice 或下游 consumer 需要快速识别 agent policy 来源，可在 Slice 3 新增 diagnostics 字段。

## 4. Validation Command Results

| Command | Result |
|---------|--------|
| `pytest tests/runtime/test_config_loader.py tests/runtime/test_assembly_helpers.py tests/service/test_host_assembly.py tests/engine/test_config_models.py -q` | 46 passed |
| `pytest tests/runtime/test_import_boundary.py tests/runtime/test_weak_typing_guard.py -q` | 13 passed |
| `python -m pyright dayu/runtime dayu/service tests/runtime tests/service tests/engine/test_config_models.py` | 0 errors, 0 warnings, 0 informations |
| `git diff --check` | clean |
| `rg -n '"max_tokens"' dayu/config/models.json` | no hits |
| `rg -n 'agent_policy_profiles\|agent_policy_profile_id' dayu/runtime dayu/service` | no hits (production) |
| `rg -n 'AgentPolicyProfileConfig' dayu/runtime dayu/service` | no hits |
| `rg 'import dayu\.(engine\|host\|service\|ui\|fins)' dayu/runtime/` | no hits (excl. docstring) |
| `python -m json.tool dayu/config/models.json dayu/config/execution_profiles.json` | valid JSON |

## 5. Plan Compliance Checklist

| Requirement | Status | Evidence |
|------------|--------|----------|
| 删除 models.json 中所有默认 max_tokens | PASS | `rg -n '"max_tokens"' dayu/config/models.json` 无输出 |
| RunnerOptionHintConfig 删除 max_tokens | PASS | `config_loader.py:94-104`；字段为 temperature/top_p/stream |
| _parse_runner_option_hint exact fields 无 max_tokens | PASS | `config_loader.py:1150-1152`；frozenset{"temperature","top_p","stream"} |
| 旧 max_tokens fail fast | PASS | `test_old_runner_hint_max_tokens_fails_fast` + exact fields 校验 |
| 删除 AgentPolicyProfileConfig.agent_policy_profile_id + catalog | PASS | 类型重命名为 AgentPolicyConfig，旧字段不存在 |
| ExecutionProfileConfig 删除 agent_policy_profile_id，新增 agent_policy | PASS | `config_loader.py:340-350` |
| ExecutionProfilesConfig 删除 agent_policy_profiles | PASS | `config_loader.py:373-379` |
| load_execution_profiles map_fields 只含 execution_profiles | PASS | `config_loader.py:647-648` |
| _parse_execution_profile exact fields 含 agent_policy | PASS | `config_loader.py:1204-1213` |
| 删除旧 catalog 解析与引用校验 | PASS | _parse_agent_policy_profile_map/_validate_execution_profile_references 已删除 |
| Service assembly 直接使用内嵌 agent_policy | PASS | `host_assembly.py:271-275` |
| _runner_options_from_hint 返回 max_tokens=None | PASS | `host_assembly.py:751-756` |
| 删除 Diagnostics.agent_policy_profile_id | PASS | `host_assembly.py:161`；字段已删除 |
| _agent_policy_defaults_from_profile 重命名 | PASS | 已重命名为 _agent_policy_defaults_from_config |
| RunnerCallOptions.max_tokens public contract 保留 | PASS | `runner_spec.py:330`；explicit override test 通过 |
| dayu.runtime import boundary | PASS | 13 tests passed, pyright clean |
| README 更新 | PASS | config/README.md + tests/README.md 已同步 |

## 6. Residual Risks

- Slice 2（Usage Observation Consumer）与 Slice 3（Execution Profile 分档与 Compatibility Diagnostics）仍按 plan 留在后续 slice，不在本次范围内。当前 Slice 1 仅完成 config schema cleanup。
- Slice 3 将引入 extends-based 多 profile，当前单 profile 的 extends 路径覆盖有限，但属计划内渐进交付。

## 7. Conclusion

Phase 12.3 Slice 1 实现**无 blocking finding**，可推进至下一 gate。所有 plan-mandated schema cleanup、fail-fast validation、import boundary、README sync 均已正确完成。`RunnerCallOptions.max_tokens` public explicit override contract 完整保留，OpenAI payload 映射行为不变。
