# WU-CTX-02 + WU-CTX-03 PR review controller adjudication

## 裁决结论

Draft PR #105 通过 PR review gate，结论为 **Accepted**。无 blocking findings，无需 PR fix / re-review。

PR URL: https://github.com/noho/dayu-agent-r/pull/105

## 输入证据

- PR review artifacts:
  - `docs/reviews/wu-ctx-02-03-pr-review-mimo-20260601.md`
  - `docs/reviews/wu-ctx-02-03-pr-review-ds-20260601.md`
- Aggregate controller adjudication:
  - `docs/reviews/wu-ctx-02-03-aggregate-controller-adjudication-20260601.md`
- Control doc:
  - `docs/host/host-core-followup-implementation-control.md`

## Findings 裁决

### PR-F1: `dayu/config/README.md` 可能残留旧默认值

- Reviewer: AgentMiMo
- Severity: Info
- Controller decision: **Checked / no fix**
- 证据：controller 使用 `rg` 核对 `dayu/config/README.md`，该文档没有硬编码
  `max_compaction_attempts_per_operation` 默认值，也没有旧 `conversation_compaction`
  默认模型 `mimo-v2.5-pro-thinking-plan`。现有示例模型为 `deepseek-v4-flash`，不与实现漂移。
- 裁决理由：README 触发规则要求检查是否残留旧术语或旧默认值；直接证据显示不存在旧默认值，因此不需要改文档。

### PR-F2: `_FALLBACK_ACTION_NOT_APPLICABLE` / fallback action 常量与 enum 未完全收敛

- Reviewer: AgentMiMo / AgentDS
- Severity: Info
- Controller decision: **Deferred with owner**
- Owner / destination: `WU-LAYER-02` shared helper consolidation
- 裁决理由：三处 `not_applicable` 私有常量值一致，`RecentWindowFallbackAction` 未完全替代字符串常量不影响
  EventLog payload correctness。当前 PR 不做无关重构；后续 helper / internal constant 清理时再统一。
- Tracking: `RR-CTX-SLICED-01` 已在总控文档中保持 `deferred-with-owner`，owner 为 `WU-LAYER-02`。

### PR-F3: `hard_threshold_before_dispatch` 无前置 `CONTEXT_COMPACTION_REQUESTED`

- Reviewer: AgentDS
- Severity: Info
- Controller decision: **Accepted as intentional behavior / no fix**
- 裁决理由：该路径是 pre-dispatch budget estimate hard block，不是已启动 compaction operation 的失败。
  `CONTEXT_COMPACTION_FAILED` payload 通过 `failure_reason=hard_threshold_before_dispatch`、
  `attempt_count=0` 与 synthetic `operation_id` 明确表达 precondition failure，不需要伪造 request fact。

### PR-F4: reactive fallback 是否进入 `RUN_RECOVERING`

- Reviewer: AgentMiMo
- Severity: Info
- Controller decision: **Rejected factual premise / no fix**
- 证据：`test_reactive_compactor_missing_fallback_dispatches_recovery_attempt` 断言事件序列包含
  `CONTEXT_COMPACTION_REQUESTED -> ATTEMPT_FAILED -> RUN_RECOVERING -> CONTEXT_COMPACTION_FAILED -> RUN_STARTED -> ATTEMPT_STARTED`。
  代码中 `_close_attempt_for_context_recovery` 明确写入 `RUN_RECOVERING`，随后 `_complete_reactive_recovery`
  启动新 Attempt，使最终 Run 状态回到 `RUNNING`。
- 裁决理由：最终 `RunStatus.RUNNING` 并不等于跳过 `RUN_RECOVERING` 事件；实现与 plan 的 reactive recovery
  状态机一致，不需要修复。

### PR-F5: 其它结构性 info 项

- Reviewer: AgentMiMo
- Severity: Info
- Controller decision: **Accepted as non-blocking / no fix**
- 范围：`_ProactiveCompactionExecutionResult` 两个可选字段的三态表达、proactive
  `REQUESTED -> FAILED` 序列、`EventLogContextFallbackProvider` 通过 `run_input.py` 组装入口暴露、
  `context_fallback.py` 不做包级 re-export、fallback rendering 对 current input anchor 的防御性校验。
- 裁决理由：这些项均不影响 correctness、durability、状态机或 public contract；当前实现更贴近既有模块 ownership，
  不应为风格偏好进入 PR fix。

## 验证要求

Controller 需要在本裁决后运行：

- `source .venv/bin/activate && pytest tests/host/test_context_policy.py tests/runtime/test_config_loader.py tests/runtime/test_scene_assets_migration.py tests/service/test_host_assembly.py tests/host/test_context_compact_events.py tests/host/test_run_input_builder.py tests/host/test_engine_ingest_mapping.py tests/host/test_dispatch_scheduler.py -q`
- `source .venv/bin/activate && python -m pyright dayu/ tests/ utils/`

验证通过后，创建 accepted PR review commit，push 到 PR 分支，并更新总控文档到 `draft-PR-pass`。
