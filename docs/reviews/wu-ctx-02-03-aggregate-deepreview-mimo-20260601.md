# WU-CTX-02 + WU-CTX-03 Aggregate Deepreview (AgentMiMo)

## 结论

**Accepted**。无 blocking findings。

## 审查范围

- 分支：`feat/host-ctx-compact-failure-overflow`
- 审查区间：`9d89db3` (accepted plan) 到 `0dcb648` (HEAD)
- 包含：Slice A/B/C/D/E 的 implementation、review、fix、re-review 全部 accepted commits
- 生产代码变更：`context_policy.py`、`context_events.py`、`context_fallback.py`（新增）、`dispatch.py`、`engine_ingest.py`、`run_input.py`、`execution_profiles.json`、`conversation_compaction.json`、`dayu/host/README.md`、`dayu/config/README.md`、`tests/README.md`
- 测试代码变更：`test_context_policy.py`、`test_context_compact_events.py`、`test_dispatch_scheduler.py`、`test_engine_ingest_mapping.py`、`test_run_input_builder.py`、`test_config_loader.py`、`test_scene_assets_migration.py`、`test_host_assembly.py`、`_context_compaction_assertions.py`（新增）

## 验证命令

```bash
source .venv/bin/activate
python -m pyright dayu/ tests/ utils/    # 0 errors, 0 warnings, 0 informations
pytest tests/host/test_context_compact_events.py tests/host/test_context_policy.py \
  tests/host/test_dispatch_scheduler.py tests/host/test_engine_ingest_mapping.py \
  tests/host/test_run_input_builder.py tests/runtime/test_config_loader.py \
  tests/runtime/test_scene_assets_migration.py tests/service/test_host_assembly.py -q
# 249 passed in 1.86s
```

## 审查证据摘要

### 1. Host 强治理约束对齐 (design.md 第 1/25 节)

**结论：满足。**

- Context Governance 仍在 Host 内部，未下沉到 Engine。`context_fallback.py` 是 Host 内部模块，只做 deterministic selection / budget re-estimate / payload 构造，不写 EventLog、不写 memory projection、不写 compact artifact。
- `dispatch.py` 的 `_append_compaction_failed_with_proactive_fallback` 在写 `CONTEXT_COMPACTION_FAILED` 后，只有 budget 通过时才调用 `_start_governed_in_transaction` 创建 Attempt，不伪造 `CONTEXT_COMPACTED`。
- `engine_ingest.py` 的 `_reactive_fallback_decision` 和 `_complete_reactive_recovery` 在 fallback recovery 时不调用 `catch_up_conversation_memory_projection`（当 `compacted_event_sequence is None` 时跳过），不物化 memory projection。
- `_ReactiveRecoveryAccepted` 的 `compacted_event_id` 和 `compacted_event_sequence` 在 fallback 路径下为 `None`，区分了 compact-accepted recovery 和 fallback recovery。
- proactive fallback 成功路径：`RUN_ACCEPTED -> CONTEXT_COMPACTION_REQUESTED -> CONTEXT_COMPACTION_FAILED(fallback_action=dispatch) -> RUN_STARTED -> ATTEMPT_STARTED`，不进入 `RECOVERING`。
- reactive fallback 成功路径：`CONTEXT_COMPACTION_REQUESTED -> ATTEMPT_FAILED -> RUN_RECOVERING -> CONTEXT_COMPACTION_FAILED(fallback_action=dispatch) -> RUN_STARTED(recovery) -> ATTEMPT_STARTED`，旧 Attempt 已关闭、Run 处于 `RECOVERING`。
- 连续 reactive overflow 达上限：写最终 `CONTEXT_COMPACTION_FAILED(failure_reason=reactive_compact_limit_reached, fallback_action=fail_closed)`，Run `FAILED`，不写 `RUN_LOST`。

### 2. Plan Success Signals 对齐

**结论：全部满足。**

| Success Signal | 状态 | 证据 |
|---|---|---|
| Host fallback 默认值与 packaged profile 的 `max_compaction_attempts_per_operation` 均为 5 | 满足 | `context_policy.py` DEFAULT=5，`execution_profiles.json` 全部 profile 改为 5，`test_context_policy.py`、`test_config_loader.py`、`test_host_assembly.py` 断言一致 |
| `conversation_compaction` scene default model 与默认 profile compactor model 一致 (flash-tier) | 满足 | `conversation_compaction.json` 改为 `deepseek-v4-flash`，`test_scene_assets_migration.py` 断言一致 |
| `CONTEXT_COMPACTION_FAILED` payload 覆盖所有设计要求字段 | 满足 | `context_events.py` 扩展了 `operation_id`、`attempt_count`、`retry_repair_budget_exhausted`、`fallback_policy_decision`、`fallback_input_window`、`fallback_input_digest`、`fallback_budget_result`、`fallback_action`，validator 完整校验 |
| Proactive fallback：预算通过创建 Attempt、不写 `CONTEXT_COMPACTED`、不写 memory projection；预算失败 fail closed | 满足 | `dispatch.py` `_append_compaction_failed_with_proactive_fallback` 和 `_start_governed_in_transaction`；`test_dispatch_scheduler.py::test_pre_start_governance_compact_failure_is_attempt_free` 和 `test_pre_start_governance_fallback_budget_fail_closes_run` |
| Reactive fallback：旧 Attempt 关闭、Run `RECOVERING`、新 Attempt 创建、不写 `CONTEXT_COMPACTED`；预算失败 `RUN_FAILED`、不 `RUN_LOST` | 满足 | `engine_ingest.py` `_execute_reactive_compaction` 和 `_complete_reactive_recovery`；`test_engine_ingest_mapping.py::test_reactive_compactor_missing_fallback_dispatches_recovery_attempt` 和 `test_reactive_fallback_over_budget_fails_closed_without_lost` |
| 连续 reactive overflow dispatch-loop 达上限 fail closed、不依赖不可控 sleep | 满足 | `test_dispatch_scheduler.py::test_reactive_repeated_overflow_dispatch_loop_fails_closed_at_limit` 使用确定性 `_RepeatedReactiveOverflowWorkerFactory` + `asyncio.Condition` 同步 |

### 3. Proactive / Reactive 语义一致性

**结论：一致但不过度抽象。**

两条路径共用 `context_fallback.py` 的 `build_recent_window_fallback_selection`、`estimate_recent_window_fallback_budget`、`RecentWindowFallbackSelection`、`RecentWindowFallbackBudgetResult` 等核心 helper。这是合理的共享，因为 fallback selection 算法本身是 deterministic budget-driven，与 trigger source 无关。

差异点合理：
- proactive 路径在 `dispatch.py` 内通过 `_append_compaction_failed_with_proactive_fallback` 一次性完成 failed payload 写入 + fallback 选择 + budget re-estimate + 可选 dispatch start。
- reactive 路径在 `engine_ingest.py` 内通过 `_reactive_fallback_decision` 构造 fallback 决策后写入 failed payload，再通过 `_complete_reactive_recovery` 创建新 Attempt。
- 两条路径的 fallback 常量（`FALLBACK_ACTION_DISPATCH`、`FALLBACK_ACTION_FAIL_CLOSED` 等）从 `context_fallback.py` 统一导入，语义一致。

错误路径均 fail closed：
- selection 异常 -> `FALLBACK_POLICY_DECISION_SELECTION_FAILED` + `FALLBACK_ACTION_FAIL_CLOSED`
- budget 仍超 hard threshold -> `FALLBACK_ACTION_FAIL_CLOSED`
- reactive count limit -> `failure_reason=reactive_compact_limit_reached` + `FALLBACK_ACTION_FAIL_CLOSED`

### 4. Tests 覆盖矩阵

**结论：覆盖充分，无 brittle sleep/race，无弱断言。**

关键测试矩阵：

| 场景 | 测试 | 行为断言 |
|---|---|---|
| proactive compactor missing + fallback budget pass | `test_pre_start_governance_compact_failure_is_attempt_free` | 1 Attempt, Run RUNNING, no CONTEXT_COMPACTED, fallback_action=dispatch |
| proactive fallback over-budget | `test_pre_start_governance_fallback_budget_fail_closes_run` | 0 Attempt, Run FAILED, fallback_action=fail_closed |
| proactive repair exhausted + fallback dispatch | `test_compaction_repair_attempt_rejection_is_recorded_in_eventlog` | attempt_count=2, exhausted=True, fallback_action=dispatch, 1 Attempt |
| proactive stale result | `test_compaction_stale_result_does_not_write_compacted_event` | failed payload 有 operation_id/attempt_count |
| proactive count limit | `test_pre_start_governance_proactive_count_limit_blocks_second_compact` | no fallback (not_applicable) |
| proactive corrupted count | `test_pre_start_governance_corrupted_compact_count_fails_closed` | no fallback (not_applicable) |
| reactive compactor missing + fallback dispatch | `test_reactive_compactor_missing_fallback_dispatches_recovery_attempt` | 2 Attempts, Run RUNNING, no RUN_LOST, fallback_action=dispatch |
| reactive fallback over-budget | `test_reactive_fallback_over_budget_fails_closed_without_lost` | 1 Attempt, Run FAILED, no RUN_LOST, fallback_action=fail_closed |
| reactive count limit | `test_reactive_compact_count_limit_fails_closed_without_second_attempt` | no fallback (not_applicable) |
| reactive repeated overflow dispatch-loop | `test_reactive_repeated_overflow_dispatch_loop_fails_closed_at_limit` | 1+max_reactive Attempts, Run FAILED, no RUN_LOST, no infinite loop |
| reactive stale input | `test_reactive_compaction_rejects_stale_input_sequence` | no fallback (not_applicable) |
| fallback selection stability | `test_recent_window_fallback_selection_is_stable_and_budget_bounded` | 同输入确定性输出, floor 保留, budget-bounded |
| fallback estimate normal/empty/over | `test_recent_window_fallback_estimate_covers_normal_empty_stable_and_over_budget` | 三种路径断言 |
| RunInputBuilder fallback rendering | `test_fallback_provider_renders_only_selected_window_and_current_input` | 只渲染 selected blocks, 不渲染 dropped |
| payload builder 全矩阵 | 6 个 payload 测试 | no fallback / dispatch / fail_closed / negative count / invalid action / not_applicable 携带 fallback 字段 |

同步机制：
- `_RepeatedReactiveOverflowWorkerFactory` 使用 `asyncio.Condition` + `wait_for_accepted_count` / `wait_for_closed_count` 确定性同步，不依赖 `asyncio.sleep`。
- `_ReactiveRecoveryWorkerFactory` 使用已有的 `_ReactiveRecoveryWorker` 模式。
- `test_reactive_repeated_overflow_dispatch_loop_fails_closed_at_limit` 有 2.0 秒 timeout，仅作外层兜底，不控制测试节奏。

### 5. 类型、Docstring、README 同步

**结论：满足。**

- pyright 0 errors。
- 全部新增/修改函数有中文 docstring，包含参数、返回值、异常。
- `RecentWindowFallbackSelection`、`RecentWindowFallbackBudgetResult`、`ActiveRecentWindowFallback`、`RecentWindowFallbackAction`、`EventLogContextFallbackProvider` 等新类型均有完整类型签名。
- 未使用 `Any`、`object` 或无类型参数。
- `dayu/host/README.md` 更新了 proactive/reactive compaction 路径说明，新增 deterministic recent-window fallback 段落。
- `tests/README.md` 更新了 Context Governance 和 RunInputBuilder 覆盖矩阵。
- `dayu/config/README.md` 无需修改（默认 attempts 变化不影响 README 现有描述）。

### 6. Residual Risk 复查

#### RR-CTX-SLICEB-01：reactive `context_budget_policy_missing` / `input_event_missing` precondition failure 集成覆盖

**状态：deferred-with-owner，不阻塞当前 gate。**

`engine_ingest.py` 的 `_fail_reactive_recovery_without_request`（第 1271 行）在 precondition failure 时仍然使用 `_append_reactive_compaction_failed_event` 并传入新参数（`operation_id`、`attempt_count=0`、`retry_repair_budget_exhausted=False`），随后 `_fail_recovering_run` 将 Run 收口为 `FAILED`。该路径未进入 fallback dispatch（因为 precondition failure 时没有可用的 frozen material blocks 或 policy），仍由既有 fail-closed 收口。

未新增 precondition 路径的集成测试是因为构造该场景需要破坏 `input_event` 的 durable invariant，属于脆弱测试。不阻塞当前 gate，建议后续在 hardening work unit 中通过 fault injection 覆盖。

#### RR-CTX-SLICED-01：fallback action 私有常量重复

**状态：deferred-with-owner，INFO 级别。**

`_FALLBACK_ACTION_NOT_APPLICABLE = "not_applicable"` 在三个文件中各定义一次：
- `dayu/host/context_events.py:196`
- `dayu/host/engine_ingest.py:230`
- `dayu/host/dispatch.py:231`

值一致（都是 `"not_applicable"`），且各处定义为模块私有（`_` 前缀），不进入 public API。`context_fallback.py` 的 `FALLBACK_ACTION_DISPATCH` 和 `FALLBACK_ACTION_FAIL_CLOSED` 已作为模块级常量统一导出，`dispatch.py` 和 `engine_ingest.py` 均从 `context_fallback.py` 导入这两个常量。`not_applicable` 仅用于 `_append_compaction_failed_event` 和 `_append_reactive_compaction_failed_event` 的默认参数，不影响 runtime 行为。

不影响 correctness，不阻塞当前 gate。未来可在 shared Host internal constants 清理时收敛。

## Findings

### F-01 [INFO] `_FALLBACK_ACTION_NOT_APPLICABLE` 常量三处私有定义

- **文件**：`dayu/host/context_events.py:196`、`dayu/host/engine_ingest.py:230`、`dayu/host/dispatch.py:231`
- **问题**：同一字符串常量 `_FALLBACK_ACTION_NOT_APPLICABLE = "not_applicable"` 在三个模块中各定义一次。
- **影响**：不影响运行时正确性。值一致，且均为模块私有。但违反 DRY 原则，未来修改时需同步三处。
- **建议修复**：后续 Host internal constants 清理时，将 `not_applicable` 收敛到 `context_fallback.py` 统一导出。
- **阻塞 ready-to-open-draft-PR**：否。

### F-02 [INFO] reactive precondition failure 路径未新增集成测试

- **文件**：`dayu/host/engine_ingest.py:1271` (`_fail_reactive_recovery_without_request`)
- **问题**：`context_budget_policy_missing` 和 `input_event_missing` 两个 precondition failure 路径在 Slice D 实现中未新增覆盖测试。Slice D review 已确认该路径仍由既有 `_fail_reactive_recovery_without_request` fail-closed 收口，且新参数已正确传入。
- **影响**：不影响 correctness。该路径的 fail-closed 行为已被既有 ingest 测试间接覆盖。
- **建议修复**：后续 hardening work unit 中通过 fault injection 覆盖。
- **阻塞 ready-to-open-draft-PR**：否。

### F-03 [INFO] `_reactive_fallback_decision` 的 broad `except Exception` catch

- **文件**：`dayu/host/engine_ingest.py:3254` (约)
- **问题**：`_reactive_fallback_decision` 在 `build_recent_window_fallback_selection` 和 `estimate_recent_window_fallback_budget` 外层使用 `except Exception as error` 捕获所有异常。
- **影响**：设计意图正确（fallback selection/estimate 异常时 fail closed），但 broad catch 可能掩盖编程错误（如 `TypeError`、`AttributeError`）。
- **建议修复**：可考虑缩小为 `except (ValueError, HostDurableError)` 或在 catch 内增加 `logging.exception` 提高可观测性。当前已有 `_LOGGER.error(..., exc_info=True)` 记录，可观测性已满足。
- **阻塞 ready-to-open-draft-PR**：否。

## Residual Risks / Deferred Items 建议 Owner

| ID | 描述 | 建议 Owner |
|---|---|---|
| RR-CTX-SLICEB-01 | reactive precondition failure 集成覆盖 | WU-CTX hardening / future fault injection work unit |
| RR-CTX-SLICED-01 | `_FALLBACK_ACTION_NOT_APPLICABLE` 常量收敛 | WU-LAYER-02 shared helper consolidation |
| F-03 | `_reactive_fallback_decision` broad catch 收窄 | 未来 Host ingest hardening |

## 总结

WU-CTX-02 + WU-CTX-03 全部 5 个 implementation slices 已通过 code review、fix 和 re-review。本次 aggregate deepreview 确认：

1. **Host 强治理约束未被破坏**：Context Governance 仍在 Host 内部，fallback 不伪造 compact success / stable facts / memory projection，proactive 不进入 RECOVERING，reactive 不进入 LOST。
2. **Plan success signals 全部满足**：默认 attempts 为 5、flash-tier compactor、完整 failed payload 诊断、proactive/reactive fallback dispatch/fail-closed 两条路径、连续 overflow dispatch-loop 确定性收口。
3. **测试覆盖充分**：249 tests passed，关键矩阵全覆盖，确定性同步无 sleep race。
4. **类型和文档同步**：pyright 0 errors，README 已更新。
5. **无 blocking findings**。三条 INFO 级 finding 均不阻塞 ready-to-open-draft-PR。

建议下一 gate：**ready-to-open-draft-PR**。
