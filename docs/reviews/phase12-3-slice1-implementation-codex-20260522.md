# Phase 12.3 Slice 1 Implementation Artifact

- Gate：Phase 12.3 Slice 1 implementation
- Work unit：Config Schema Cleanup
- Agent: AgentCodex
- Approved plan：`docs/host/phase12-3-config-usage-governance-plan.md`
- Plan accepted commit：`3ecbfad`
- Stop status：`SLICE_COMPLETE`

## Changed Files

- `dayu/config/models.json`
- `dayu/config/execution_profiles.json`
- `dayu/config/README.md`
- `dayu/runtime/config_loader.py`
- `dayu/runtime/assembly.py`
- `dayu/service/host_assembly.py`
- `tests/runtime/test_config_loader.py`
- `tests/runtime/test_assembly_helpers.py`
- `tests/service/test_host_assembly.py`
- `tests/engine/test_config_models.py`
- `tests/README.md`
- `docs/reviews/phase12-3-slice1-implementation-codex-20260522.md`

## Implemented Plan Items

- 删除 `dayu/config/models.json` runner option hints 中所有默认 `max_tokens`。
- 删除 `RunnerOptionHintConfig.max_tokens`；`_parse_runner_option_hint` 现在只接受 `temperature`、`top_p`、`stream`，旧 `max_tokens` 会以 unknown field fail fast。
- 删除顶层 `agent_policy_profiles` catalog 和 `execution_profiles[*].agent_policy_profile_id`。
- 新增内嵌 `ExecutionProfileConfig.agent_policy: AgentPolicyConfig`。
- 更新 `load_execution_profiles`：顶层只接受 `default_execution_profile_id` 和 `execution_profiles`，overlay map fields 只包含 `execution_profiles`。
- 删除旧 agent policy catalog 解析与引用校验。
- 更新 runtime assembly：从内嵌 `AgentPolicyConfig` 合并 baseline，并保持 runtime 层中立。
- 更新 Service host assembly：直接使用 `execution_profile.agent_policy` 作为 baseline，默认 `RunnerCallOptions.max_tokens` 为 `None`。
- 更新测试：覆盖旧 schema fail-fast、内嵌 agent policy 解析、默认 config 无输出 cap、Service `max_tokens=None`、scene agent policy override 优先级。

## Tests And Pyright Results

- `source .venv/bin/activate && pytest tests/runtime/test_config_loader.py tests/runtime/test_assembly_helpers.py tests/service/test_host_assembly.py tests/engine/test_config_models.py -q`
  - Result：passed, `46 passed in 0.96s`.
- `source .venv/bin/activate && pytest tests/runtime/test_import_boundary.py tests/runtime/test_weak_typing_guard.py -q`
  - Result：passed, `13 passed in 0.86s`.
- `source .venv/bin/activate && python -m pyright dayu/runtime dayu/service tests/runtime tests/service tests/engine/test_config_models.py`
  - Result：passed, `0 errors, 0 warnings, 0 informations`.
- `git diff --check`
  - Result：passed.
- Additional checks：
  - `rg -n '"max_tokens"' dayu/config/models.json` 无命中。
  - `jq empty dayu/config/models.json dayu/config/execution_profiles.json` passed。

## README Decision

- 已更新 `dayu/config/README.md`，因为本 slice 改变了 `models.json` 与 `execution_profiles.json` 的配置 schema 语义。
- 已更新 `tests/README.md`，因为 runtime config loader 测试覆盖新增旧 runner hint `max_tokens` fail-fast。
- 未更新根目录 `README.md`、`dayu/README.md`、Host README 或 Engine README；本 slice 未改变项目级工作流、分层关系、Host public contract 或 Engine public contract。

## Residual Risks

- Slice 1 无已知 blocking residual risk。
- Slice 2 usage observation consumer 与 Slice 3 execution profile 分档仍按 plan 留在后续 slice，不在本次范围内。
- 显式 `RunnerCallOptions.max_tokens` override 仍是 public contract 行为；本 slice 只移除默认 config 来源。
