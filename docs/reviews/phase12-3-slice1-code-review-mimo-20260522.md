# Phase 12.3 Slice 1 Code Review

- Gate：Phase 12.3 Slice 1 code review
- Review agent：AgentMiMo
- Implementation artifact：`docs/reviews/phase12-3-slice1-implementation-codex-20260522.md`
- Plan artifact：`docs/host/phase12-3-config-usage-governance-plan.md`

## Verdict

**PASS**

无 blocking finding。

## Blocking Findings

无。

## Non-blocking Observations

### 1. `_parse_agent_policy` 不再解析 `extends` 字段

旧 `_parse_agent_policy_profile` 的 `allowed` frozenset 包含 `"extends"`，且通过 `_resolve_record_map` 在 profile map 层级处理继承。新 `_parse_agent_policy` 的 `allowed` frozenset 不包含 `"extends"`——这是正确行为，因为 agent policy 现在内嵌于 execution profile record 内部，不再有独立的 agent policy catalog 需要解析继承链。execution profile 本身的 `extends` 继承仍在 `_resolve_record_map` 中处理。

测试 fixture `_agent_policy_record()` 同步删除了 `"extends": None`，保持一致。

**结论**：行为正确，无需修改。

### 2. `_agent_policy_defaults_from_config` 语义

`_agent_policy_defaults_from_config` 将内嵌 `AgentPolicyConfig` 投影为 `AgentPolicyDefaults`，随后传入 `merge_agent_policy_config` 的 `code_default` 参数。函数名与 docstring 已从 `_agent_policy_defaults_from_profile` 更新为 `_agent_policy_defaults_from_config`，语义准确。

**结论**：无问题。

### 3. `ServiceOpenHostAssemblyDiagnostics` 删除 `agent_policy_profile_id`

diagnostics dataclass 删除了 `agent_policy_profile_id: str` 字段，只保留 `agent_policy_sources: tuple[str, ...]`。测试中 `_write_execution_profile_overlay` fixture 已同步删除该字段。diagnostics 不是 Host public contract，变更在允许范围内。

**结论**：无问题。

## Verification Results

| 检查项 | 结果 |
|---|---|
| `rg -n '"max_tokens"' dayu/config/models.json` | 0 命中 |
| `rg agent_policy_profiles\|agent_policy_profile_id dayu/runtime` | 0 命中 |
| `rg agent_policy_profiles\|agent_policy_profile_id dayu/service` | 0 命中 |
| `rg agent_policy_profile_id tests/` | 仅 negative test (`test_old_agent_policy_profile_id_fails_fast`) |
| `rg agent_policy_profiles tests/` | 仅 negative test (`test_old_agent_policy_profiles_catalog_fails_fast`) |
| `jq empty dayu/config/models.json dayu/config/execution_profiles.json` | passed |
| `pytest tests/runtime/test_config_loader.py tests/runtime/test_assembly_helpers.py tests/service/test_host_assembly.py tests/engine/test_config_models.py -q` | 46 passed |
| `pytest tests/runtime/test_import_boundary.py tests/runtime/test_weak_typing_guard.py -q` | 13 passed |
| `pyright dayu/runtime dayu/service tests/runtime tests/service tests/engine/test_config_models.py` | 0 errors |
| `git diff --check` | clean |

## Key Contract Verification

| 合约 | 验证 |
|---|---|
| `RunnerOptionHintConfig` 不含 `max_tokens` 字段 | `config_loader.py:93-104` — dataclass 只有 `temperature`、`top_p`、`stream` |
| `_parse_runner_option_hint` 对旧 `max_tokens` fail fast | `config_loader.py:1150-1152` — `allowed` frozenset 不含 `"max_tokens"`；`test_old_runner_hint_max_tokens_fails_fast` 覆盖 |
| `RunnerCallOptions.max_tokens` public contract 保留 | `runner_spec.py:330` — `max_tokens: int \| None` 字段未修改 |
| Service 默认 path `max_tokens=None` | `host_assembly.py:751-753` — `_runner_options_from_hint` 硬编码 `max_tokens=None`；`test_host_assembly.py` 断言 `max_tokens is None` |
| 显式 `max_tokens` override 测试仍通过 | `tests/engine/runners/openai/test_payload_build.py:337-343` — `RunnerCallOptions(max_tokens=100)` 写入 payload 通过 |
| `ExecutionProfilesConfig` 不含 `agent_policy_profiles` | `config_loader.py:370-379` — 只有 `default_execution_profile_id` 和 `execution_profiles` |
| `ExecutionProfileConfig` 内嵌 `agent_policy` | `config_loader.py:325-343` — `agent_policy: AgentPolicyConfig` |
| `ConfigLoader.load_execution_profiles` map_fields 只含 `execution_profiles` | `config_loader.py:648` |
| `dayu.runtime` 不 import Host / Engine / Service | `config_loader.py` 只 import `dayu.contracts`；`assembly.py` 只 import `dayu.contracts` 和 `dayu.runtime` 子模块 |
| README 只写当前稳定行为 | `dayu/config/README.md` 已更新为内嵌 `agent_policy`、无 `max_tokens` 默认 hint |

## Test Coverage Assessment

| 测试 | 覆盖场景 |
|---|---|
| `test_default_runtime_config_files_load_as_typed_views` | 默认 config 加载、`RunnerOptionHintConfig` 无 `max_tokens` 字段、内嵌 `agent_policy.max_iterations` |
| `test_default_models_expose_runner_option_hints_without_output_cap` | 默认 config 不携带输出 token cap |
| `test_old_runner_hint_max_tokens_fails_fast` | 旧 `max_tokens` 字段被拒绝 |
| `test_old_agent_policy_profile_id_fails_fast` | 旧 `agent_policy_profile_id` 字段被拒绝 |
| `test_old_agent_policy_profiles_catalog_fails_fast` | 旧顶层 `agent_policy_profiles` catalog 被拒绝 |
| `test_agent_policy_missing_field_fails_fast` | 内嵌 agent_policy 缺必填字段 fail fast |
| `test_agent_policy_field_type_fails_fast` | 内嵌 agent_policy 字段类型非法 fail fast |
| `test_agent_fallback_mode_is_closed_enum` | fallback mode 枚举校验 |
| `test_compose_open_host_options_uses_runtime_tuning_from_config` | Service assembly `max_tokens is None`、agent policy 来自内嵌配置 |
| `test_merge_agent_policy_config_*` | agent policy 合并优先级、field sources、runtime immutability |
| `test_old_execution_profile_fields_fail_fast` | 旧 `runner_options_profiles` / `runner_hints` / `agent_hints` 被拒绝 |

## Residual Risks

无 blocking residual risk。Slice 2（usage observation consumer）和 Slice 3（execution profile 分档）按 plan 留在后续 slice。
