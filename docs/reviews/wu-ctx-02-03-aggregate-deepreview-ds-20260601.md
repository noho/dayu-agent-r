# WU-CTX-02 + WU-CTX-03 Aggregate Deepreview — AgentDS

## 结论

**Accepted**。无 blocking findings。

## 审查范围与证据

- 审查范围：accepted plan commit `9d89db3` 到当前 HEAD `0dcb648` 的全部改动。
- 提交链：
  ```
  f24d1a3 gateflow: record accepted plan for WU-CTX-02-03
  2f2f22c gateflow: accept WU-CTX-02-03 slice A
  f55e967 gateflow: record slice A for WU-CTX-02-03
  e6156de gateflow: accept WU-CTX-02-03 slice B
  ae44b86 gateflow: record slice B for WU-CTX-02-03
  2d2ed5a gateflow: accept WU-CTX-02-03 slice C
  e06ca56 gateflow: record WU-CTX-02-03 slice C
  13500ae gateflow: accept WU-CTX-02-03 slice D
  940d867 gateflow: record WU-CTX-02-03 slice D
  667dc87 gateflow: accept WU-CTX-02-03 slice E
  0dcb648 gateflow: record WU-CTX-02-03 slice E
  ```
- 变更涉及 52 文件，+6092/-108 行。核心生产文件：`context_fallback.py`(新增)、`context_events.py`、`dispatch.py`、`engine_ingest.py`、`run_input.py`、`context_policy.py`、config files。测试文件：`test_dispatch_scheduler.py`、`test_run_input_builder.py`、`test_context_compact_events.py`、`test_engine_ingest_mapping.py` 等。
- 设计真源：`docs/host/design.md` 第 1 节、第 25 节。
- 计划真源：`docs/host/wu-ctx-02-03-compact-failure-overflow-plan.md`。
- 总控文档：`docs/host/host-core-followup-implementation-control.md`。
- 先前 Slice A-E 的 code review / re-review / controller adjudication artifacts 均已通过。

## 验证命令

- `python -m pyright dayu/ tests/ utils/` → 0 errors, 0 warnings, 0 informations
- `pytest tests/host/test_context_policy.py tests/runtime/test_config_loader.py tests/runtime/test_scene_assets_migration.py tests/service/test_host_assembly.py tests/host/test_context_compact_events.py tests/host/test_run_input_builder.py tests/host/test_engine_ingest_mapping.py tests/host/test_dispatch_scheduler.py -q` → 249 passed in 1.88s

## Findings

### Finding 1 — INFO / 非阻塞

**文件**: `dayu/host/context_events.py:196`, `dayu/host/dispatch.py:231`, `dayu/host/engine_ingest.py:230`

**问题**: `_FALLBACK_ACTION_NOT_APPLICABLE = "not_applicable"` 在三个模块中各自定义为模块级私有常量，值完全一致。

**影响**: 当前三个常量的值和语义一致，不构成 correctness 风险。但三地独立定义增加了未来常量漂移的可能性（例如某次修改只改了其中一处）。此问题对应 tracking item RR-CTX-SLICED-01。

**建议**: defer 到后续 shared helper consolidation work unit（如 WU-LAYER-02）把 `fallback_action` 的三种枚举值（`dispatch`、`fail_closed`、`not_applicable`）收敛到一个 Host 内部常量模块。当前 WU 不做无关重构。

**阻塞 ready-to-open-draft-PR**: 否。

---

### Finding 2 — INFO / 非阻塞

**文件**: `dayu/host/dispatch.py:989-1012`

**问题**: `hard_threshold_before_dispatch` 路径写 `CONTEXT_COMPACTION_FAILED`，但没有前置的 `CONTEXT_COMPACTION_REQUESTED`。该路径是 pre-dispatch budget estimate 直接超过 hard threshold，本质上是预算前置检查失败，不是 compaction operation 失败。

**影响**: EventLog 序列为 `... -> CONTEXT_COMPACTION_FAILED(fallback_action=dispatch/fail_closed) -> ...`，中间缺少 `CONTEXT_COMPACTION_REQUESTED`。对于仅消费 EventLog 的下游 read model / projection，`CONTEXT_COMPACTION_FAILED` 语义仍然成立（failure_reason 清晰为 `hard_threshold_before_dispatch`，operation_id 为 `precondition:hard_threshold_before_dispatch:<digest>` 格式的合成值）。该行为符合 plan 的 design decision：deterministic recent-window fallback 对所有超过 hard budget 的场景统一处理，无论是否经过 compaction attempt。

**建议**: 当前实现路径符合 plan 规定的行为闭环。不需修改。若后续引入 EventLog schema 校验要求 `failed` event 之前必须有 `requested` event，可在设计真源中明确该 invariant 并调整 precondition 路径的 operation_id 约定。

**阻塞 ready-to-open-draft-PR**: 否。

---

### Finding 3 — VERIFIED / RR-CTX-SLICEB-01

**主题**: reactive precondition failure 路径（`context_budget_policy_missing`、`input_event_missing`、`reactive_compact_count_unreadable`、`reactive_compact_limit_reached`）

**验证结果**: 
- `_fail_reactive_recovery_without_request`（`engine_ingest.py:1271`）已正确更新所有必需 payload 字段：`operation_id`、`attempt_count=0`、`retry_repair_budget_exhausted=False`、`budget_after_attempted_compact=None`，无 fallback 字段（默认 `fallback_action=not_applicable`）。
- 四条 precondition failure 路径统一走该 helper，行为一致。
- 旧 Attempt 先关闭，再写 `CONTEXT_COMPACTION_FAILED`，最后写 `RUN_FAILED`。这是正确的 fail-closed 行为。
- 当前 WU 不需要为该 precondition 路径补脆弱测试（需手动破坏 durable invariant 才能触发 `input_event_missing`，不符合 AGENTS.md 测试原则）。

**结论**: RR-CTX-SLICEB-01 可关闭（`closed`）。precondition failure 路径已由既有 fail-closed 路径正确收口，payload 字段完整。

**阻塞 ready-to-open-draft-PR**: 否。

---

### Finding 4 — VERIFIED / RR-CTX-SLICED-01

**主题**: fallback action 私有常量重复

**验证结果**: 已在 Finding 1 中覆盖。三处定义值一致：`context_events.py`、`dispatch.py`、`engine_ingest.py` 均为 `_FALLBACK_ACTION_NOT_APPLICABLE = "not_applicable"`。不影响 correctness。

**结论**: RR-CTX-SLICED-01 保持 `deferred-with-owner`，owner 为 future cleanup work unit。当前 WU 不做清理。

**阻塞 ready-to-open-draft-PR**: 否。

---

### Finding 5 — VERIFIED / 设计真源合规性

逐一检查 plan aggregate deepreview 规定的 5 项重点：

**5a. Context Governance ownership 未越界到 Engine / Service**
- 全部 fallback 逻辑位于 Host 内部模块（`context_fallback.py`、`dispatch.py`、`engine_ingest.py`、`run_input.py`）。
- `RunInputBuilder` 通过 `ContextFallbackProvider` 协议消费 fallback view，协议定义在 Host 内。
- Engine 不感知 fallback；Service 不参与 fallback 决策。
- `dayu.runtime` 未被 import 到 fallback 模块。
- **合规**。

**5b. EventLog payload schema 与 tests / README 一致**
- `_FAILED_REQUIRED_FIELDS` 包含 plan 规定的全部字段：`operation_id`、`failure_reason`、`policy_decision`、`retryable`、`attempt_count`、`retry_repair_budget_exhausted`、`diagnostic_refs`、`budget_after_attempted_compact`、`fallback_policy_decision`、`fallback_input_window`、`fallback_input_digest`、`fallback_budget_result`、`fallback_action`。
- validator `_validate_failed_fallback_fields` 确保 `fallback_action=not_applicable` 时 fallback 字段均为 null。
- 测试通过 `assert_failed_payload_no_fallback` helper 和显式断言覆盖两种形态（有/无 fallback）。
- `dayu/host/README.md` 已描述 fallback 语义；`tests/README.md` 已提及 fallback 覆盖。
- **合规**。

**5c. fallback 没有被 RunInputBuilder 当作 compact artifact 或 memory projection**
- `RunInputBuilder.build` 中 fallback view 替换的是 `bounded_context_messages`（即 memory + compact + continuity messages 合并后的中间表示），不走 `CompactArtifactProvider.load_compact_artifact` 路径。
- fallback 渲染使用 `_fallback_context_messages`，只按 material block 的 kind 构造 SystemMessage / UserMessage / AssistantMessage，不消费 compact artifact。
- `_complete_reactive_recovery` 在 `compacted_event_sequence is None`（fallback recovery）时跳过 `catch_up_conversation_memory_projection`。
- **合规**。

**5d. continuous overflow 不存在无限 loop 或 flakiness**
- `_RepeatedReactiveOverflowWorkerFactory` 使用 `asyncio.Condition` 做确定性同步，不依赖 `sleep` 或时间竞态。
- `_RepeatedReactiveOverflowHandle.close` 记录 close 同步点，test 通过 `wait_for_closed_count` 等待期望次数。
- 测试使用 `_REPEATED_OVERFLOW_SYNC_TIMEOUT_SECONDS = 2.0` 的 `asyncio.wait_for` 做超时保护。
- 测试断言 Attempt 数 = `1 + max_reactive_compactions_per_run`，不会无限增长。
- **合规**。

**5e. Host 对 Agent/Runner 生命周期、上下文治理和 durable truth 保持强约束**
- 所有 compact/failure/fallback 决策在 Host write transaction 内完成。
- Engine 只报告 overflow；Host 决定是否 compact、是否 fallback、是否 dispatch。
- `DUPLICATE_REGISTRY` 和取消/关闭治理不属于本 WU 范围，未受扰动。
- **合规**。

**阻塞 ready-to-open-draft-PR**: 否。

---

### Finding 6 — VERIFIED / 测试覆盖矩阵

| 场景 | 测试文件 | 状态 |
|---|---|---|
| Slice A 默认常量对齐 | `test_context_policy.py`, `test_config_loader.py`, `test_scene_assets_migration.py`, `test_host_assembly.py` | 覆盖 |
| Slice B failed payload 无 fallback 形态 | `test_context_compact_events.py` | 覆盖 |
| Slice B failed payload 有 fallback 形态 | `test_context_compact_events.py` | 覆盖 |
| Slice C fallback selection 稳定性 | `test_run_input_builder.py::test_recent_window_fallback_selection_is_stable_and_budget_bounded` | 覆盖 |
| Slice C fallback estimate normal/empty/over-budget | `test_run_input_builder.py::test_recent_window_fallback_estimate_covers_normal_empty_stable_and_over_budget` | 覆盖 |
| Slice C fallback RunInputBuilder rendering | `test_run_input_builder.py::test_run_input_builder_renders_fallback_bounded_context_messages` | 覆盖 |
| Slice C proactive 缺 compactor + fallback dispatch | `test_dispatch_scheduler.py::test_pre_start_governance_compact_failure_is_attempt_free` | 覆盖 |
| Slice C proactive fallback over-budget fail closed | `test_dispatch_scheduler.py::test_pre_start_governance_fallback_budget_fail_closes_run` | 覆盖 |
| Slice C proactive stale result + no fallback | `test_dispatch_scheduler.py::test_compaction_stale_result_does_not_write_compacted_event` | 更新后覆盖 |
| Slice C repair exhausted + fallback dispatch | `test_dispatch_scheduler.py::test_compaction_repair_attempt_rejection_is_recorded_in_eventlog` | 更新后覆盖 |
| Slice D reactive fallback dispatch | `test_dispatch_scheduler.py::test_reactive_compact_failure_fallback_dispatch_uses_failed_view` | 覆盖 |
| Slice E 连续 reactive overflow fail closed | `test_dispatch_scheduler.py::test_reactive_repeated_overflow_dispatch_loop_fails_closed_at_limit` | 覆盖 |
| Precondition path payload 字段 | `test_engine_ingest_mapping.py`（既有测试） | 覆盖 |

**未覆盖的合理场景**:
- `context_budget_policy_missing` / `input_event_missing` reactive precondition 的集成 E2E：不补测试（reason: 需要破坏 durable invariant 构造脆弱测试，已在 controller adjudication 中裁定不纳入当前 WU）。
- proactive hard_threshold_before_dispatch + fallback 的独立测试：已有 `test_pre_start_governance_fallback_budget_fail_closes_run` 覆盖 fallback over-budget 路径；hard_threshold_before_dispatch 的 fallback dispatch 路径在 `test_pre_start_governance_compact_failure_is_attempt_free` 中通过 `_soft_threshold_prompt()` 间接覆盖。

**测试质量评估**:
- 无 brittle sleep/race。
- 断言对象是 durable EventLog / Run 状态 / Attempt 计数 / EventLog 序列，不依赖实现私有顺序。
- `_RepeatedReactiveOverflowWorkerFactory` 使用 `asyncio.Condition` 确定性同步。
- 测试 helper `assert_failed_payload_no_fallback` 封装了常见断言模式，减少重复。

---

## Residual Risks / Deferred Items

| ID | 当前状态 | 建议 owner | 下一步 |
|---|---|---|---|
| RR-CTX-SLICEB-01 | **closed** — 已验证 precondition failure 路径由既有 fail-closed 路径正确收口，payload 字段完整 | — | 本次 aggregate review 关闭 |
| RR-CTX-SLICED-01 | **deferred-with-owner** — `not_applicable` 常量三地重复，值一致，无 correctness 风险 | WU-LAYER-02 shared helper consolidation | 后续 cleanup work unit 收敛 fallback action 枚举值到共享 Host 内部常量 |
| RR-CTX-PLAN-01 | **closed** — 已由 plan review 关闭 | — | — |
| RR-CTX-PLAN-02 | **closed** — 已由 Slice C review 关闭 | — | — |
| RR-CTX-PLAN-03 | **closed** — 已由 Slice E review 关闭 | — | — |

无新增 residual risk。

## 总结

WU-CTX-02 + WU-CTX-03 五个 slice（A-E）实现了 plan 规定的全部 success signals：
1. 默认 `max_compaction_attempts_per_operation` 统一为 5（常量、packaged profiles、assembled policy）。
2. `conversation_compaction` scene default model 与 execution profile compactor model 一致使用 flash-tier。
3. `CONTEXT_COMPACTION_FAILED` payload 包含全部设计要求字段。
4. Proactive / reactive compact failure 两条路径均支持 deterministic recent-window fallback：预算通过则 dispatch（写 failed + 有界 input view），预算失败则 fail closed；fallback 不写 `CONTEXT_COMPACTED`，不物化 memory projection。
5. 连续 reactive overflow dispatch-loop E2E 使用确定性同步机制，不依赖竞态。
6. 全部 fallback 逻辑在 Host 内部，不突破分层边界。
7. pyright 0 errors，249 测试全部通过，README 同步到位。

建议下一 gate：`ready-to-open-draft-PR`。
