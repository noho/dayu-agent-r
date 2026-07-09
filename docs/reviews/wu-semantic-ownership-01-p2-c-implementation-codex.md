# WU-SEMANTIC-OWNERSHIP-01 P2-C Implementation - AgentCodex

## Scope

- Work unit: `WU-SEMANTIC-OWNERSHIP-01 P2-C`
- Gate: implementation
- Accepted plan: `docs/reviews/wu-semantic-ownership-01-p2-c-plan-codex.md`
- Accepted plan commit: `256cda50`
- Implementation decision: completed with classified residual test failures outside P2-C scope

本轮只实施 P2-C：删除 Engine `AgentPolicy` 的 LLM-facing prompt 文本默认值，迁移 runtime assembly 命名，补齐 production / tests / utils 中的显式 prompt 构造点。未处理 public compact smoke residual，未进入 deepreview / PR gate，未 commit / push，未改控制文档 gate 状态。

## First-principles Judgment

动机成立。`fallback_prompt` 与 `continuation_prompt` 是直接进入 Runner / LLM 上下文的文本。如果 Engine contract 和 execution profile / compactor scene 同时生产默认文案，同一业务事实就存在双真源。正确修复不是同步两处文案，而是让 Engine 只消费调用方已解析好的完整 `AgentPolicy`，并在构造期要求 prompt 显式传入。

## Owner Boundary

- 事实：Agent fallback / continuation prompt 文本。
- 产生：ordinary Run 由 `execution_profiles.json` 的 execution profile `agent_policy` 产生；compactor 由 `conversation_compaction` scene manifest required `agent_policy` 产生。
- 校验：ConfigLoader / ScenePrepare / Service compactor helper 校验配置与 scene policy 完整性；Engine `AgentPolicy.__post_init__` 只校验已传入 prompt 非空。
- 持久 / 冻结：Host opener ordinary baseline、compactor baseline 和 effective execution config projection 持有完整 typed `AgentPolicy`。
- 投影：Host RunInputBuilder / dispatch 将完整 `AgentPolicy` 放入 `AgentRunRequest`；Engine fallback / continuation 状态机只读取传入字段并追加 user message。

## Propagation Audit

- Ordinary path：`execution_profiles.json` -> `ConfigLoader.AgentPolicyConfig` -> `merge_agent_policy_config(...)` -> `ServiceOpenHostAssemblyResult.agent_policy_config` -> `OrdinaryRunExecutionBaseline.agent_policy` -> Host effective execution config -> `AgentRunRequest.agent_policy` -> Engine fallback / continuation user message。
- Per-run override path：ordinary baseline -> `ServiceRunOverrides` 覆盖允许字段；未覆盖的 `continuation_prompt` 和 `fallback_prompt` 继续来自 ordinary baseline，覆盖 `fallback_prompt` 时仍显式非空。
- Compactor path：execution profile `compactor_baseline.scene_id` -> `ScenePrepare` 读取 compactor scene -> `_compactor_agent_policy_from_scene_inputs(...)` required policy -> `CompactorRunnerBaseline.compactor_agent_policy` -> Host compaction run -> Engine。
- Durable restore path：`agent_policy_to_json(...)` / `agent_policy_from_json(...)` 读写完整 prompt 字段；未新增旧 JSON 兼容读取。

## Changed Files

- Production / docs:
  - `dayu/engine/contracts/agent_policy.py`
  - `dayu/runtime/assembly.py`
  - `dayu/service/host_assembly.py`
  - `dayu/engine/README.md`
- Tests / utils:
  - `tests/runtime/test_assembly_helpers.py`
  - `tests/service/test_host_assembly.py`
  - `tests/engine/contracts/test_agent_run.py`
  - `tests/engine/runners/openai/test_streaming_capability_and_content_type.py`
  - `tests/engine/test_agent_phase2.py`
  - `tests/engine/test_agent_phase3_tool_call.py`
  - `tests/engine/test_metadata_boundary.py`
  - `tests/host/public_smoke_support.py`
  - `tests/host/test_active_cancel_dispatch.py`
  - `tests/host/test_admission_multiprocess.py`
  - `tests/host/test_admission_queue.py`
  - `tests/host/test_command_handle.py`
  - `tests/host/test_compaction_operation.py`
  - `tests/host/test_dispatch_scheduler.py`
  - `tests/host/test_effective_execution_config.py`
  - `tests/host/test_engine_ingest_mapping.py`
  - `tests/host/test_host_activity_event_projection.py`
  - `tests/host/test_llm_compaction.py`
  - `tests/host/test_local_proxy_engine_ingest.py`
  - `tests/host/test_logging.py`
  - `tests/host/test_open_host_runtime.py`
  - `tests/host/test_per_run_tool_selection.py`
  - `tests/host/test_phase5_local_execution_integration.py`
  - `tests/host/test_phase6_toolruntime_integration.py`
  - `tests/host/test_phase7_waiting_integration.py`
  - `tests/host/test_projection_read_model.py`
  - `tests/host/test_public_compact_smoke.py`
  - `tests/host/test_public_contracts.py`
  - `tests/host/test_public_lifecycle_smoke.py`
  - `tests/host/test_public_open_host_multiturn_smoke.py`
  - `tests/host/test_public_open_host_options.py`
  - `tests/host/test_public_retry_replay.py`
  - `tests/host/test_public_session_api.py`
  - `tests/host/test_resolve_wait_command.py`
  - `tests/host/test_run_input_builder.py`
  - `tests/host/test_storage_maintenance.py`
  - `tests/host/test_storage_usage_report.py`
  - `tests/host/test_submit_followup_public_contract.py`
  - `tests/host/test_watch_session_events.py`
  - `utils/smoke_async_agent_providers.py`

## Implementation Notes

- 删除 `dayu/engine/contracts/agent_policy.py` 中 `_DEFAULT_FALLBACK_PROMPT` 与 `_DEFAULT_CONTINUATION_PROMPT`。
- 将 `AgentPolicy.fallback_prompt` 与 `AgentPolicy.continuation_prompt` 改为无默认必填字段；保留 `fallback_mode` 和 `max_consecutive_failed_tool_batches` 的非文本默认。
- Runtime assembly 完成 mandatory rename：
  - `AgentPolicyDefaults` -> `AgentPolicyBaseline`
  - `code_default` -> `base_policy`
  - `_SOURCE_CODE_DEFAULT` -> `_SOURCE_RUNTIME_BASE`
  - source 字符串 `"code_default"` -> `"runtime_base"`
  - `_agent_policy_defaults_from_config(...)` -> `_agent_policy_baseline_from_config(...)`
- `AgentPolicyBaseline` docstring 明确它是 runtime assembly baseline，不是 Engine contract default，也不是 LLM-facing prompt 文本真源。
- `tests/engine/test_agent_phase3_tool_call.py` 将原默认 prompt contract test 迁移为：
  - explicit prompt acceptance test；
  - 缺 `fallback_prompt` / 缺 `continuation_prompt` 的 deliberate `TypeError` negative test；
  - invalid value tests 显式传入非空 prompt，避免 `TypeError` 掩盖 `ValueError`。
- `tests/host/public_smoke_support.py` 与其它测试 / utils 构造点均显式传入 prompt，未新增跨测试导入的默认 prompt 真源。

## Validation

PASS:

```bash
source .venv/bin/activate && pytest tests/engine/test_agent_phase3_tool_call.py tests/engine/test_agent_phase2.py tests/engine/contracts/test_agent_run.py
```

Result: `110 passed in 0.34s`.

PASS:

```bash
source .venv/bin/activate && pytest tests/runtime/test_assembly_helpers.py tests/runtime/test_config_loader.py tests/service/test_host_assembly.py
```

Result: `124 passed, 3 warnings in 1.60s`. Warnings are existing `edgar` deprecation warnings.

PARTIAL / classified outside P2-C:

```bash
source .venv/bin/activate && pytest tests/engine tests/runtime tests/service/test_host_assembly.py tests/host
```

Result: `8 failed, 2584 passed, 1 skipped, 5 deselected, 3 warnings in 61.64s`.

Failures:

- `tests/engine/runners/openai/test_stream_idle.py::test_idle_heartbeat_emits_debug_log_and_does_not_drop_bytes`
- `tests/engine/test_engine_event_contract.py::test_iteration_started_runner_input_signal_fields_are_locked`
- `tests/engine/test_package_exports.py::test_engine_all_matches_expected_set`
- `tests/host/test_package_exports.py::test_host_all_matches_current_public_contracts`
- `tests/host/test_package_exports.py::test_api_all_stays_request_snapshot_boundary`
- `tests/host/test_phase7_waiting_integration.py::test_local_awaiting_tool_manual_resolve_resumes_run`
- `tests/host/test_public_compact_smoke.py::test_post_compaction_fact_reuse_uses_raw_accepted_tool_evidence`
- `tests/host/test_purge_session.py::test_purge_session_durable_rejects_non_terminal_runs[cancelling]`

Classification: these failures do not touch the P2-C changed production files or migrated `AgentPolicy` constructor semantics. The public compact smoke failure is explicitly outside this task's allowed scope. No fix was attempted for these residuals.

PASS:

```bash
source .venv/bin/activate && pyright
```

Result: `0 errors, 0 warnings, 0 informations`.

PASS:

```bash
git diff --check
```

Result: no output.

Scan:

```bash
rg -n "AgentPolicy\\(" dayu/ tests/ utils/ --glob '*.py'
```

Result: all non-negative `AgentPolicy(...)` construction sites are explicit according to pyright. The only intentionally missing prompt cases are `tests/engine/test_agent_phase3_tool_call.py` lines using `AgentPolicy(**without_fallback_prompt)` and `AgentPolicy(**without_continuation_prompt)` under `pytest.raises(TypeError)`.

Scan:

```bash
rg -n "_DEFAULT_FALLBACK_PROMPT|_DEFAULT_CONTINUATION_PROMPT" dayu/engine dayu/runtime tests
```

Result: no Engine contract prompt default remains. Remaining hits are `dayu/runtime/config_loader.py` config-layer fallback prompt defaults, which are the ordinary execution profile source and are expected to remain.

## README Decisions

- Updated `dayu/engine/README.md` because `dayu/engine/` contract behavior changed: `fallback_prompt` and `continuation_prompt` are caller-resolved required inputs and Engine has no LLM-facing prompt defaults.
- Checked `dayu/config/README.md`: no change needed. It already documents execution profile `agent_policy`, ordinary fallback prompt ownership, and compactor scene `agent_policy` ownership.
- Checked `tests/README.md`: no change needed. This implementation did not add shared cross-file fixtures or change test directory responsibilities.

## Residual Risks

- External callers that directly instantiate `AgentPolicy` without prompt fields now get `TypeError`. This is intended contract tightening and not compatibility-preserved.
- Broad suite currently has 8 residual failures classified outside P2-C; they require separate owner review if the next gate requires a fully green broad suite.
- Single-file coverage was not separately measured for every touched test file because the requested validation commands did not include per-file coverage. Pytest and pyright cover the changed behavior and constructor signature.

## Completion Status

Implementation artifact complete. Next entry point per task constraints: implementation review / re-review by controller, not deepreview / PR gate in this turn.
