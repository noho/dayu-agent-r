# PR 67 Phase 12.3 Post-Push Review — DS — 2026-05-22

## Verdict: PASS

无 blocking finding。PR 67 head commit `a3d36e8` 通过所有 P12.3 校验标准。

## 1. Post-Push Pyright Fix 验证

**结果：PASS**

- `python -m pyright utils/smoke_host_public_multiturn.py` → 0 errors, 0 warnings, 0 informations
- `pytest tests/runtime/test_smoke_host_public_multiturn_assembly.py -q` → 4 passed
- 修复仅删除 `utils/smoke_host_public_multiturn.py:704` 一行 `agent_policy_profile:{diagnostics.agent_policy_profile_id}`，新增 `test_assembly_diagnostics_output_uses_current_agent_policy_sources` 负向断言。无旧 schema 回退、无兼容性 re-export。

## 2. Schema 旧字段残留扫描

### 2.1 agent_policy_profiles / agent_policy_profile_id (PASS)

| 范围 | 结果 |
|---|---|
| `dayu/` 生产代码 (`*.py`) | 零命中 |
| `dayu/config/` (`*.json`) | 零命中 |
| `tests/` (`*.py`) | 仅 `test_config_loader.py:594,600,713,725` — 均为 plan-mandated negative test |
| `utils/` (`*.py`) | 零命中 |

### 2.2 max_tokens 在默认 config (PASS)

- `rg '"max_tokens"' dayu/config/models.json dayu/config/execution_profiles.json` → 无输出
- Service assembly `_runner_options_from_hint` (`dayu/service/host_assembly.py:775`) 唯一路径返回 `max_tokens=None`
- `RunnerCallOptions.max_tokens` public contract 保留，explicit override 测试 `tests/engine/test_config_models.py` 仍通过

### 2.3 usage 配置 override (PASS)

- `usage_enabled` / `collect_usage` / `include_usage` / `supports_usage` 在 `dayu/config/`、`dayu/runtime/`、`dayu/service/`、`dayu/host/` 的 `*.py` 文件中零命中
- `include_usage` 仅出现在 `dayu/engine/runners/openai/payload.py:357`，受 `stream=True` + `supports_stream_usage=True` 门控 — 正确

## 3. P12.3 关键决策验证

### 3.1 Execution Profile 显式选择 (PASS)

- `_select_execution_profile_id` (`dayu/service/host_assembly.py:509-527`) 仅使用 explicit override 或 `default_execution_profile_id`，不读取 `model.context_window_tokens`
- `validate_execution_profile_context_window` (`dayu/runtime/assembly.py`) 只做校验和 diagnostic，不返回替代 profile id

### 3.2 supports_stream_usage 门控 (PASS)

- `dayu/engine/runners/openai/payload.py:357`: `if options.stream and spec.supports_stream_usage` — 正确
- `stream=True` 且 `supports_stream_usage=False` 时不写 `stream_options` — 已验证 `tests/engine/runners/openai/test_stream_usage_capability_gating.py` 通过

### 3.3 OpenHostOptions public surface (PASS)

- `dayu/host/api.py:968` — `OpenHostOptions` field set 未变更
- `context_budget_policy` 从绝对 token-based 迁移到 ratio-first（`soft_threshold_context_ratio`），属于 accepted typed policy shape change
- `DEFAULT_MINIMUM_PROTECTION_TOKENS` 已完全替换为 `DEFAULT_SOFT_THRESHOLD_CONTEXT_RATIO`，生产代码和测试代码均零残留
- `dayu/host/__init__.py` public exports 未变更

### 3.4 Usage Observation 实现 (PASS)

- `UsageObservationDiagnostic` (`dayu/host/context_budget.py:293`) 字段类型严格：`observation_digest: str`、`estimator_digest: str | None`、`policy_ref: str`、`estimated_input_tokens: int | None`、`prompt_token_delta: int | None`、`status: str`
- `build_usage_observation_diagnostic` (`dayu/host/context_budget.py:345`) 只产生校准/diagnostic data，不调用 `decide_context_budget`
- `USAGE_REPORTED` projection signal payload (`dayu/host/engine_ingest.py:2059-2075`) 包含全部必需字段：`session_id`、`run_id`、`attempt_id`、`execution_id`、`iteration_id`、`prompt_tokens`、`completion_tokens`、`total_tokens`、`provider_request_id: None`、`policy_ref`、`estimator_digest`、`estimated_input_tokens`、`usage_observation_status`、`usage_observation_digest`、`prompt_token_delta`
- `provider_request_id` 硬编码为 `None`（当前 Engine usage event contract 不提供）— 符合 plan
- `_usage_observation_diagnostic` 估算失败降级为 estimate_unavailable，不抛错、不改变 Run/Attempt 状态

## 4. Import Boundary

| 检查项 | 结果 |
|---|---|
| `tests/runtime/test_import_boundary.py` | 通过 |
| `tests/runtime/test_weak_typing_guard.py` | 通过 |
| `tests/host/test_import_boundary.py` | 通过 |
| `tests/engine/test_import_boundary.py` | 通过 |
| `dayu.runtime` import 边界（无 Engine/Host/Service/Fins/UI） | 通过 |

## 5. 测试结果汇总

| 测试范围 | 结果 |
|---|---|
| `tests/runtime/test_config_loader.py` + `test_assembly_helpers.py` + `tests/service/test_host_assembly.py` | 115 passed |
| `tests/host/test_engine_ingest_mapping.py` + `tests/host/test_context_budget.py` | 通过（含在 host suite） |
| `tests/engine/test_config_models.py` + Engine OpenAI usage tests | 15 passed |
| `tests/runtime/test_import_boundary.py` + weak_typing + host/engine import boundary | 29 passed |
| `tests/host/` full suite | 806 passed |
| `tests/contracts/test_tool_schema.py` + `test_import_boundary.py` | 14 passed |
| `tests/host/test_public_contracts.py` + `test_open_host_runtime.py` | 47 passed |

## 6. Pyright

| 目标 | 结果 |
|---|---|
| `dayu/runtime` + `dayu/service` + `dayu/host` | 0 errors, 0 warnings, 0 informations |
| `dayu/engine` | 0 errors, 0 warnings, 0 informations |
| `utils/smoke_host_public_multiturn.py` | 0 errors, 0 warnings, 0 informations |
| `tests/runtime/test_smoke_host_public_multiturn_assembly.py` | 0 errors, 0 warnings, 0 informations |

## 7. 其他检查

| 检查项 | 结果 |
|---|---|
| `git diff --check` | clean |
| `python -m json.tool dayu/config/models.json` | 有效 JSON |
| `python -m json.tool dayu/config/execution_profiles.json` | 有效 JSON |
| Execution profiles 四档 (`standard-256k`, `standard-1m`, `wechat-256k`, `wechat-1m`) | 均有完整 `agent_policy` 内嵌 |
| `default_execution_profile_id` | `standard-256k`（匹配当前默认模型 256K class） |
| `context_window_class` + `min_context_window_tokens` | 256k→262144, 1m→1000000 |

## 8. 非阻塞观测项

1. **Smoke 脚本 `policy_refs=` 行命名**: 旧 `agent_policy_profile` 删除后，该行现含 `context_budget` 与 `tool_truncation` 两个字段，命名 "policy_refs" 略显宽泛。这是既有 smoke 格式约定，不属于 P12.3 scope。未来若只剩一个字段可考虑重命名或合并到其他 diagnostics 行。

2. **Execution profiles `wechat-*` 与 `standard-*` policy 一致**: 四档 profile 的 `agent_policy`、`context_budget_policy`、`memory_projection_policy`、`tool_truncation_policy` 完全相同。当前 baseline 统一是合理起点；独立 profile id 确保 Service 未来可按业务差异分化而不依赖隐式切换。

3. **`tests/runtime/test_config_loader.py:594` `test_old_agent_policy_profile_id_fails_fast`**: 该测试确保旧 `agent_policy_profile_id` 字段被拒绝。当前 fixture 为旧 schema 字段出现在执行 profile record 内；若未来还要测顶层 `agent_policy_profiles` catalog 拒绝，`test_old_agent_policy_profiles_catalog_fails_fast` (`line 713`) 已覆盖。

## 9. 项目指令合规检查

| 指令 | 状态 |
|---|---|
| 禁止兼容性代码（re-export/wrapper/facade） | PASS — 无旧 schema alias，无兼容读取路径 |
| 禁止把显式参数放进 extra payload | PASS |
| bug fix 禁止局部止血 | PASS — 直接删除残留引用，root cause 是 schema 清理后遗漏 |
| 禁止 God object/function/dataclass | PASS |
| `dayu.runtime` 不得 import 业务层 | PASS — import boundary tests 通过 |
| 分层架构 (UI→Service→Host→Engine) | PASS — 无反向依赖 |
| `RunnerCallOptions.max_tokens` 保留 explicit override 语义 | PASS — contract 未删除，默认 path 写 None |
