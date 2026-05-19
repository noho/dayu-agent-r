# Phase 10 Context Governance / Compaction Implementation Plan

## Gate

当前 gate：Phase 10 implementation-ready handoff plan。

本 artifact 只给 implementation agent 使用，不实现代码、不修改生产代码、不 commit、不 push、不创建 PR、不进入 plan review 或 implementation gate。

## Goal

实现 Host proactive context budget governance、Host-owned typed compactor port、compact canonical event、compact artifact、P9 memory projection 对 accepted compact output 的消费、reactive Engine overflow recovery 与 RunInputBuilder compact provider。

P10 完成后，多轮会话主体必须可工作：Host 在预算压力下可以生成 accepted episode summary / pinned state patch candidate，经 `CONTEXT_COMPACTED` canonical fact、compact artifact 和 P9 memory projection 进入后续 RunInputBuilder memory messages。后续 Run 的输入必须能解释 recent raw turns、older raw turns、episode summaries、pinned state 与 verified facts 的来源。

## Motivation

问题真实存在且严重性成立。

当前 Engine 已能把 provider context overflow 提升为 `context_compaction_requested` / recoverable `run_failed(context_compaction_required)`，但 Host 端仍把该路径按 unsupported recovery 失败收口，不能恢复。当前 RunInputBuilder 已预留 `CompactArtifactProvider`，但 production wiring 只注入 no-op provider，compact artifact 不会进入 messages。当前 P9 memory projection 已有 episode summary continuity 结构，但消费的是旧的 `EPISODE_SUMMARY_ACCEPTED` event type，不消费 P10 设计真源要求的 accepted `CONTEXT_COMPACTED` compact output，也没有 pinned state patch candidate 的字段级物化。

因此 P10 不是表面预算裁剪，而是补齐 Host 拥有的上下文预算、compactor 接口、canonical compact fact、artifact、memory projection consumption、pre-dispatch orchestration 与 reactive recovery 状态机。

## Non-goals

- 不实现 provider-specific tokenizer adapter。
- 不实现长期 memory retrieval。
- 不实现 public memory edit / reset / forget API。
- 不实现 Phase 11 startup crash recovery、positive orphan proof 或通用 recovery scan。
- 不实现 Phase 13 Audit / Tool Trace / Outbox sinks。
- 不让 Engine 做 proactive compaction。
- 不直接写 memory snapshot、memory table、audit、trace、outbox 或 RunInputBuilder 私有 message 缓存。
- 不从 Engine 反查模型窗口，不从 per-run metadata 或 extra payload 读取预算参数，不把 provider overflow event 当作预算真源。
- 不为旧 event type 或旧 tests 保留兼容 wrapper / re-export。P10 后 compact truth 是 `CONTEXT_COMPACTION_REQUESTED`、`CONTEXT_COMPACTED`、`CONTEXT_COMPACTION_FAILED`。

## Truth Sources

- `docs/host/design.md` §13.3：canonical event matrix 规定 `CONTEXT_COMPACTION_REQUESTED`、`CONTEXT_COMPACTED`、`CONTEXT_COMPACTION_FAILED` 的 scope、payload、状态副作用与 memory consumption。
- `docs/host/design.md` §23：RunInputBuilder 必须通过 typed providers 聚合 memory、compact artifact、policy、scene 与 tool schemas，输出必须能由 fact refs、memory cursor、compact artifact refs 与 policy snapshot 解释。
- `docs/host/design.md` §24：Conversation Memory 是 EventLog read model；verified facts 只来自 `TOOL_RESULT_ACCEPTED`；episode summary 只做 continuity / navigation，不能替代 evidence anchor。
- `docs/host/design.md` §25：Context Governance 是 Host orchestrator；预算参数是 typed policy input；LLM compactor 只能提出候选，Host 负责 quality check、accept 与写 canonical compact event / artifact。
- `docs/host/design.md` §25.1：proactive compact 在 dispatch Attempt 前；reactive compact 必须校验 `attempt_id + execution_id`，关闭当前 Attempt，让 Run 进入 `RECOVERING` 后创建新 Attempt。
- `docs/host/implementation-control.md` Phase 10：范围、slice、验证要求与已确认 design decisions。

## Direct Evidence From Current Code

- `dayu/host/run_input.py:338` 已定义 `CompactArtifactProvider` typed protocol，`dayu/host/run_input.py:888` 已有 `NoopCompactArtifactProvider`。但 `create_no_tool_run_input_builder` 与 `create_tool_enabled_run_input_builder` 在 `dayu/host/run_input.py:1267`、`dayu/host/run_input.py:1303` 均硬接 no-op compact provider，production path 不可能消费 compact artifact。
- `dayu/host/run_input.py:1209` 的 message 顺序为 scene、memory、compact、continuity、current user prompt，说明 compact provider 已有稳定插槽，可以在 P10 替换为 durable provider，不需要绕过 RunInputBuilder。
- `dayu/host/run_input.py:603` 的 `DurableMemorySnapshotProvider` 只读 memory snapshot 与 EventLog delta；它不写 memory projection，符合 P10 不直接写 memory table 的边界。
- `dayu/host/memory.py:313` 已有 `PinnedStateView`，`dayu/host/memory.py:572` 已有 `MemoryProjectionPolicy`，`dayu/host/memory.py:997` 的 `project_conversation_memory_event` 已是 P9 pure projection 真源。
- `dayu/host/memory.py:1049` 与 `dayu/host/durable/memory.py:73` 显示 memory projection 当前消费 `_EVENT_TYPE_EPISODE_SUMMARY_ACCEPTED`，不是 P10 canonical `CONTEXT_COMPACTED`。这需要替换为对 accepted compact output 的消费。
- `dayu/host/durable/memory.py:111` 的 `ConversationMemoryProjectionConsumer` 只消费 committed canonical fact filter，适合扩展为消费 `CONTEXT_COMPACTED`，不应让 Context Governance 直接写 memory snapshot。
- `dayu/host/engine_ingest.py:513` 处理 Engine `CONTEXT_COMPACTION_REQUESTED` 时只写 `ENGINE_EVENT_DIAGNOSTIC`，并用 `_unsupported_recovery_plan` 失败收口。`tests/host/test_engine_ingest_mapping.py:287` 固化了 “context_compaction_requested accepts none budget and fails” 的旧期望。
- `dayu/host/engine_ingest.py:549` 与 `tests/host/test_engine_ingest_mapping.py:622` 显示 `USAGE_REPORTED` 当前是 projection signal，不改 Run / Attempt 状态。P10 应保持 usage 为 observation / diagnostics，不让 usage 动态改 policy。
- `dayu/host/dispatch.py:798` 的 `_run_input_builder_for_dispatch` 当前只把 `DurableMemorySnapshotProvider` 注入 RunInputBuilder，未注入 context policy、context governance 或 durable compact provider。
- `dayu/host/dispatch.py:720` 在 worker 创建前追平 memory projection并构造 Engine request；这是 proactive gate 和 compact 后 rebuild 的自然接入点，但当前 dispatch record 已经来自 `ATTEMPT_STARTED`。
- `dayu/host/durable/run_transition.py:679` 的 `create_running_run_with_starting_attempt_in_transaction` 在接受 direct start 时同事务创建 `RUN_STARTED`、`ATTEMPT_STARTED` 与 dispatch record。该结构与 P10 “proactive compact failure 不得创建 Attempt” 冲突，必须引入 pre-start governance gate。
- `dayu/host/api.py:265` 注释说明 `RECOVERING` 尚不由当前生产转换写入；`dayu/host/durable/state.py` 已在 schema 和 active-run index 中允许 `recovering`，但缺少 reactive compact 所需的 transition helper。
- `dayu/host/command.py:719` 已把 `HostCommandHandleOptions.artifact_root` 装配进 durable payload policy；`dayu/host/durable/artifact.py` 与 `dayu/host/durable/payload.py` 已有 local artifact 和 payload descriptor primitive，P10 compact artifact store 应复用这些基础设施。

## Cross-cutting Contracts

### Context Policy And Budget Estimator

Owner files:

- `dayu/host/context_policy.py` 新增。
- `dayu/host/context_budget.py` 新增。
- `dayu/host/durable/event_log.py` 扩展 committed compact event count reader。
- `dayu/host/api.py` 扩展 production options。
- `tests/host/test_context_budget.py` 新增。

Required typed contracts:

- `ContextBudgetPolicy`：字段至少包括 `context_window_size`、`reserved_output_tokens`、`safety_margin_ratio`、`hard_threshold_tokens`、`minimum_protection_tokens`、`max_proactive_compactions_per_run`、`max_reactive_compactions_per_run`、`policy_ref`。
- `ContextBudgetProvider` Protocol：按 Host composition root 显式提供 policy，不读取 Engine、metadata 或 payload bag。
- `BudgetEstimateInput`：包含 session/run refs、memory snapshot cursor、compact artifact refs、message refs、scene/tool schema size summary 与 current prompt refs。
- `BudgetEstimate`：包含 estimated input tokens、input budget、soft threshold、hard threshold、overage reason、estimator digest。
- `ContextBudgetDecision` enum：`ALLOW_DISPATCH`、`COMPACT_SOFT_THRESHOLD`、`BLOCK_HARD_THRESHOLD`。
- `UsageObservation`：只记录 post-call prompt/completion/total tokens、provider request id、attempt/execution refs 与 estimator snapshot ref，不参与当前 Run 动态 threshold 调整。

Threshold decisions:

- 校验 `context_window_size > 0`、`reserved_output_tokens > 0`、`reserved_output_tokens < context_window_size`。
- `input_budget_tokens = context_window_size - reserved_output_tokens`。
- 默认 safety margin 为 20%，soft threshold 为 `input_budget_tokens * 0.8`。实现中用命名常量，不散落 magic number。
- hard threshold 优先使用 policy provider 显式值；否则按 `input_budget_tokens - minimum_protection_tokens`。
- proactive / reactive 每个 Run 第一版各最多 compact 一次，计数来自 committed `CONTEXT_COMPACTION_REQUESTED` facts，不用内存 flag。

Estimator:

- 第一版使用 conservative estimator，不接 provider tokenizer adapter。
- estimator 必须只依赖 typed message/content/tool schema/artifact metadata view。允许采用保守 char-to-token 上界、JSON byte size 上界和固定 per-message overhead，但所有系数必须是 `dayu/host/context_budget.py` 模块级命名常量或 `ContextBudgetPolicy` typed 字段，禁止散落 magic number。第一版常量示例：
  - `DEFAULT_CONTEXT_SAFETY_MARGIN_RATIO = 0.2`
  - `DEFAULT_INPUT_SOFT_THRESHOLD_RATIO = 0.8`
  - `DEFAULT_ESTIMATOR_CHARS_PER_TOKEN = 3`
  - `DEFAULT_ESTIMATOR_JSON_BYTES_PER_TOKEN = 3`
  - `DEFAULT_ESTIMATOR_MESSAGE_OVERHEAD_TOKENS = 12`
  - `DEFAULT_ESTIMATOR_TOOL_SCHEMA_OVERHEAD_TOKENS = 16`
  - `DEFAULT_MINIMUM_PROTECTION_TOKENS = 256`
- estimator 输出必须可记录 digest/ref，供 `CONTEXT_COMPACTION_REQUESTED` payload 与 diagnostics 引用。

Compact count:

- 新增 transaction-scoped EventLog reader helper，例如 `count_committed_events_by_run_and_type(transaction, *, run_id: str, event_type: str, trigger_source: ContextCompactionTriggerSource | None) -> int`，推荐放在 `dayu/host/durable/event_log.py` 或同层 durable reader 模块。
- proactive / reactive compact 次数查询必须与 append `CONTEXT_COMPACTION_REQUESTED` 的决策处于同一个 Host write transaction 内：先按 run_id + event_type + trigger_source 统计已 committed/requested facts，再决定是否 append 新 request fact。
- 查询失败、payload 损坏或 trigger_source 无法验证时必须 fail-closed：不得继续 dispatch，不得用内存 flag 兜底；proactive path append `CONTEXT_COMPACTION_FAILED` 并按 accepted/queued pre-start failure 收口，reactive path在当前 Attempt 按 policy 关闭后让 Run `FAILED`。

### Compactor Typed Contracts

Owner files:

- `dayu/host/compaction.py` 新增。
- `dayu/host/context_governance.py` 新增。
- `tests/host/test_compaction_contract.py` 新增。

Required typed contracts:

- `ContextCompactor` Protocol：输入 `CompactionRequest`，输出 `CompactionCandidate`。
- `CompactionRequest`：包含 trigger source、session/run refs、可选 attempt/execution refs、input event refs、memory snapshot cursor、current messages summary、tool fact refs、verified fact refs、recent raw turn refs、older raw turn refs、existing episode summary refs、budget before compact。
- `EpisodeSummaryCandidate`：字段包括 episode title、goal、completed actions、confirmed fact refs/summaries、user constraints、open questions、next step、tool finding refs、source event refs。
- `PinnedStatePatchCandidate`：字段级三态 patch，覆盖 `current_goal`、`confirmed_subjects`、`user_constraints`、`open_questions`。未出现表示不修改，空值表示显式清空，非空值表示替换。
- `PreservationEvidence`：为每条 summary / patch candidate 关联 input event refs、tool fact refs、memory cursor 或 compact input range。
- `CompactQualityCheckResult`：记录 current user input、accepted tool fact refs、evidence anchors、open questions / assumptions refs 是否保留，以及 dropped / summarized ranges。
- `FakeContextCompactor`：测试用 deterministic compactor，位于 `tests/host/fake_compaction.py`，只能由测试显式注入；生产代码不得导入 tests helper。

Quality check:

- Host quality checker 必须拒绝丢失当前 `USER_INPUT_ACCEPTED`、丢失 accepted tool fact refs、把 episode summary 当 verified fact、缺 preservation evidence、pinned patch 字段类型不合法或 patch 引用不存在输入 evidence 的候选。
- LLM compactor output 只能是 candidate。只有 quality check accept 后才能写 `CONTEXT_COMPACTED` canonical fact 和 artifact。

### Compact Artifact Store

Owner files:

- `dayu/host/compact_artifact.py` 新增。
- `dayu/host/durable/payload.py` 只在需要补小 helper 时修改。
- `tests/host/test_compact_artifact_store.py` 新增。

Implementation direction:

- 复用 `LocalArtifactStore` 和 `PayloadStore.write_payload_descriptor_for_artifact`。
- Artifact 内容使用 canonical JSON bytes，包含 compaction request digest、accepted candidate、quality result、budget before/after、input snapshot refs、dropped/summarized ranges、preserved fact refs、policy digest。
- EventLog 只保存 artifact ref、digest、必要小 payload 字段和 typed refs，不把长 compact 内容塞进 hot EventLog。
- artifact 写文件发生在 DB transaction 前；DB transaction 内写 payload descriptor 与 compact canonical event。若 DB transaction 失败，孤立 artifact 文件只作为冷文件残留，不作为 truth。

### Canonical Compact Events

Owner files:

- `dayu/host/context_events.py` 新增，集中 payload validation 与 append request builder。
- `dayu/host/durable/event_log.py` 不改通用 primitive，除非需要更强 typed append helper。
- `tests/host/test_context_compact_events.py` 新增。

Event types:

- `CONTEXT_COMPACTION_REQUESTED`
- `CONTEXT_COMPACTED`
- `CONTEXT_COMPACTION_FAILED`

Required payload validation:

- Requested payload：`trigger_source`、`budget_reason`、`budget_snapshot_ref`、`input_snapshot_cursor`、`estimator_digest`、`policy_ref`、`provider_request_id`、`provider_error_ref`、`attempt_id`、`execution_id`。Reactive trigger 必须带 attempt/execution；proactive 可以不带。
- Compacted payload：`compact_artifact_ref`、`compact_artifact_digest`、`episode_summary_candidate`、`pinned_state_patch_candidate`、`preserved_fact_refs`、`dropped_ranges`、`summarized_ranges`、`evidence_anchors_retained`、`quality_check_result`、`budget_after_compact`。
- Failed payload：`failure_reason`、`policy_decision`、`retryable`、`diagnostic_refs`、`budget_after_attempted_compact`。

Validation tests must reject missing required fields, untyped metadata use for required fields, reactive event without attempt/execution, compacted payload without artifact ref/digest pair, and summary / pinned patch without preservation evidence.

## State Machine And Public Interface Changes

### Pre-start Governance Gate

Current direct start creates Attempt too early for proactive failure. P10 must add a pre-start state so `RUN_ACCEPTED` can exist before `RUN_STARTED` / `ATTEMPT_STARTED`.

Required changes:

- Add `RunStatus.ACCEPTED = "accepted"` to `dayu/host/api.py` and `host_runs.status` schema check in `dayu/host/durable/schema.py`。This is not a compatibility shim; it is the missing canonical `RUN_ACCEPTED` state.
- `ACCEPTED` is non-terminal and has no `current_attempt_id`、no dispatch record、no `started_event_id`。
- Active-run unique index should continue to cover `running`、`waiting`、`cancelling`、`recovering` only. `accepted` is pre-active, but it is a start-blocking Run for admission. Add a separate fresh-schema partial uniqueness guard for one pre-start candidate per session if needed, for example `host_runs_one_accepted_per_session WHERE status = 'accepted'`；do not redefine active lifecycle semantics by folding `accepted` into the active-run index.
- P10 schema CHECK / index changes follow this repository's fresh-schema convention: update bootstrap DDL and tests for new databases only; do not add old database compatibility reads, migration tests, wrapper code or legacy schema upgrade logic unless a later task explicitly requests it.
- `submit/start` command should append `USER_INPUT_ACCEPTED` and `RUN_ACCEPTED` first. If an active or start-blocking `ACCEPTED` Run exists, policy handling is:
  - `REJECT` returns conflict and creates no new Run.
  - `ATTACH_ACTIVE` must not attach to `ACCEPTED` because there is no Attempt / dispatch record; it returns conflict with a pending-start reason, not a fake active attachment.
  - `QUEUE` creates a `QUEUED` Run behind the active/start-blocking Run.
  - `submit_followup(queue)` also queues behind `ACCEPTED` when no active Run exists but a pre-start Run is pending governance.
- If no active/start-blocking Run exists, `start_run` leaves the new Run status as `ACCEPTED` and wakes the pre-start governance path.
- Accepted-but-not-started cancel path: `cancel_run` must handle `RunStatus.ACCEPTED` explicitly by appending `RUN_CANCELLED` terminal closeout and marking the Run `CANCELLED` without creating Attempt, dispatch record, `ATTEMPT_CANCELLED` or active worker target. Idempotent replay of the cancel should behave like other terminal replay paths.
- Add transition helper `start_accepted_run_with_starting_attempt_in_transaction` that accepts an existing status=`ACCEPTED` Run and its already committed `RUN_ACCEPTED` event, appends `RUN_STARTED(start_reason=initial)`、`ATTEMPT_STARTED` and creates dispatch record only after proactive governance allows dispatch. It must not append a second `RUN_ACCEPTED`。
- Add transition helper `fail_accepted_run_before_attempt_in_transaction` that appends `RUN_FAILED` after `CONTEXT_COMPACTION_FAILED` and leaves no Attempt row.
- `create_running_run_with_starting_attempt_in_transaction` currently creates `RUN_ACCEPTED` + `RUN_STARTED` + `ATTEMPT_STARTED` atomically. After P10, `start_run` / follow-up direct start must stop calling it for production local execution. Either delete it if no tests or production paths still need the old combined semantics, or keep it as an internal test-only helper with call sites migrated away; do not leave a production bypass around context governance.
- Queued promotion implementation choice: do not transition `QUEUED -> ACCEPTED` as a durable intermediate state. The same pre-start governance gate accepts a typed `StartGovernanceCandidate` with `origin=accepted | queued`; for queued candidates it always selects the earliest queued Run by existing FIFO order while no active/start-blocking Run exists, evaluates budget/compact in-place, then starts it with a new `start_queued_run_with_starting_attempt_after_governance_in_transaction` helper that replaces production use of old `promote_queued_run_in_transaction`。This avoids inventing a second accepted canonical event and preserves `RUN_STARTED(start_reason=queue_promotion)` semantics.
- Old `promote_queued_run_in_transaction` must not be called directly by `_PromoteNextQueuedRunOperation` after P10. It should be replaced or refactored so queue promotion cannot create Attempt / dispatch before proactive governance completes.
- FIFO is preserved by selecting only `read_earliest_queued_run` under the governance write transaction. Single-start arbitration is preserved by checking no active Run and no `ACCEPTED` start-blocking Run in the same transaction before compact/start. Active-run uniqueness remains enforced by the existing active partial index once `RUN_STARTED` moves the Run to `RUNNING`。

Pre-start governance wakeup:

- Add a dedicated pre-start governance wakeup path, separate from the current dispatch scheduler's pending dispatch record loop. Recommended shape:
  - `PreStartGovernanceWakeupPort.wakeup_start_governance(session_id: str)` for admission / terminal promotion to signal eligible `ACCEPTED` or `QUEUED` work.
  - `HostPreStartGovernanceScheduler` or an explicitly named governance loop owned by Host local execution composition.
  - The governance loop scans `ACCEPTED` first, otherwise earliest eligible `QUEUED` when no active/start-blocking Run exists.
  - Only after governance allows start does it create `RUN_STARTED` / `ATTEMPT_STARTED` / pending dispatch record and then wake the existing dispatch scheduler.
- The existing `HostDispatchScheduler` remains the consumer of pending dispatch records. It must not poll `ACCEPTED` directly as if they were dispatch records, and no placeholder dispatch record may be created before governance.
- If process crashes after `RUN_ACCEPTED` / status `ACCEPTED` but before governance wakeup, Phase 11 owns startup recovery scan. P10 only needs same-process wakeup and tests for normal after-commit wakeup.

Stop condition:

- If adding public `RunStatus.ACCEPTED` is rejected by controller, implementation must stop. Using a pre-created STARTING Attempt for proactive failure violates the confirmed P10 decision.

### Reactive RECOVERING Path

Required changes:

- Add state helper to close current Attempt as `FAILED` because of context compaction requirement while moving Run `RUNNING -> RECOVERING` through `RUN_RECOVERING` canonical fact.
- Add `RunStartReason.RECOVERY` definitively; current code does not have it. Do not add `RunStartReason.STEER` in P10; steer start semantics belong to the steer phase owner.
- Add transition helper `start_recovery_attempt_in_transaction` that appends `RUN_STARTED(start_reason=recovery)`、creates new `attempt_id` / `execution_id` / dispatch record, appends `ATTEMPT_STARTED`, and moves Run `RECOVERING -> RUNNING` with `current_attempt_id` set to new Attempt.
- Old Attempt must never resume/takeover. Engine events from stale old `attempt_id + execution_id` after recovery start must be rejected as stale diagnostics by existing identity guard.
- Reactive compact failure after current Attempt closeout appends `CONTEXT_COMPACTION_FAILED` and `RUN_FAILED`；never `RUN_LOST`。

## Slice 1: Context Budget Policy, Estimator, Usage Observation

Allowed files / modules:

- `dayu/host/context_policy.py`
- `dayu/host/context_budget.py`
- `dayu/host/api.py`
- `dayu/host/engine_ingest.py`
- `dayu/host/durable/event_log.py`
- `tests/host/test_context_budget.py`
- `tests/host/test_public_contracts.py`
- `tests/host/test_engine_ingest_mapping.py`

Exact changes:

- Add typed `ContextBudgetPolicy` and default factory.
- Add `HostLocalExecutionOptions.context_budget_policy` or `context_budget_provider` as explicit composition input. It must require `context_window_size` and `reserved_output_tokens` from Service / composition root.
- Add conservative estimator and decision function.
- Do not extend `USAGE_REPORTED` EventLog payload in P10. `UsageObservation` is a Context Governance internal diagnostic/calibration input derived from existing usage projection signal fields and typed Host policy refs; it must not become a new canonical state input.
- Do not let usage update threshold decisions dynamically.

Data flow:

`HostLocalExecutionOptions.context_budget_policy -> ContextGovernance -> BudgetEstimator -> ContextBudgetDecision`。

State transitions:

- None in this slice.

Tests:

- Valid policy computes input budget, soft threshold at 80%, hard threshold by explicit value or minimum protection.
- Invalid zero/negative/oversized reserved output values fail construction.
- Budget estimator over soft returns compact decision; over hard returns block decision.
- Usage observation remains projection signal and does not alter Run / Attempt status.
- Provider overflow with `budget_state=None` still does not become Host budget truth.

Stop condition:

- Stop if any path reads context budget from Engine spec, per-run metadata, extra payload or provider overflow error instead of typed Host policy.

## Slice 2: Compactor Contracts, Fake Compactor, Quality Check, Artifact Store

Allowed files / modules:

- `dayu/host/compaction.py`
- `tests/host/fake_compaction.py`
- `dayu/host/context_governance.py`
- `dayu/host/compact_artifact.py`
- `dayu/host/durable/artifact.py`
- `dayu/host/durable/payload.py`
- `tests/host/test_compaction_contract.py`
- `tests/host/test_compact_artifact_store.py`

Exact changes:

- Add all typed compactor request/candidate/result dataclasses and protocols.
- Add fake compactor with deterministic candidates for tests.
- Add Host quality checker and rejection reasons.
- Add artifact writer that emits canonical JSON artifact and descriptor refs.
- Keep LLM scene adapter as a typed port boundary. If a real LLM adapter is not yet wired in production, production can use an explicitly injected compactor port; tests use fake compactor.

Data flow:

`ContextGovernance` builds `CompactionRequest` from EventLog/memory/message refs, calls `ContextCompactor`, validates `CompactionCandidate`, writes artifact, then returns accepted compact output for event append.

State transitions:

- None in this slice unless invoked by later orchestration.

Tests:

- Fake compactor produces episode summary candidate, pinned patch candidate and preservation evidence.
- Quality check rejects missing current input, missing tool fact refs, missing evidence anchor retention, invalid pinned patch tri-state, and summary pretending to create verified fact.
- Artifact store writes deterministic descriptor with digest; corrupted digest is rejected by existing artifact validation.

Stop condition:

- Stop if compactor output is untyped JSON bag or if Host accepts a candidate without quality check.

## Slice 3: Canonical Compact Events And P9 Memory Projection Consumption

Allowed files / modules:

- `dayu/host/context_events.py`
- `dayu/host/memory.py`
- `dayu/host/durable/memory.py`
- `dayu/host/run_input.py`
- `tests/host/test_context_compact_events.py`
- `tests/host/test_memory_projection.py`
- `tests/host/test_run_input_builder.py`

Exact changes:

- Add typed builders / validators for `CONTEXT_COMPACTION_REQUESTED`、`CONTEXT_COMPACTED`、`CONTEXT_COMPACTION_FAILED`。
- Replace P9 memory projection compact-summary source from `EPISODE_SUMMARY_ACCEPTED` to `CONTEXT_COMPACTED` accepted output.
- `ConversationMemoryProjectionConsumer.event_filter` must include `CONTEXT_COMPACTED` canonical facts.
- `project_conversation_memory_event` must parse `CONTEXT_COMPACTED` payload:
  - Add `_EVENT_TYPE_CONTEXT_COMPACTED = "CONTEXT_COMPACTED"` and remove `EPISODE_SUMMARY_ACCEPTED` from the memory projection compact truth path after verifying no remaining non-test consumers.
  - Add helper `_compact_episode_summary_from_projection_event(event, policy)` rather than reusing `_episode_summary_from_projection_event` unchanged, because `CONTEXT_COMPACTED` nests the summary under `episode_summary_candidate` instead of top-level `summary_text`。
  - `_compact_episode_summary_from_projection_event` reads `episode_summary_candidate.summary_text` or a deterministic join of typed candidate fields (`title`、`goal`、`completed_actions`、`open_questions`、`next_step`) and creates a `ConversationContinuityItem` with `item_kind=ConversationContinuityKind.EPISODE_SUMMARY`、`producer_kind=MemoryProducerKind.HOST_PROJECTION`、`claim_status=MemoryClaimStatus.ASSUMPTION`、source event id/sequence from the `CONTEXT_COMPACTED` event and bounded size via existing `_bounded_summary_text`。
  - Add helper `_apply_pinned_state_patch_candidate(pinned_state, event, policy)` that parses `pinned_state_patch_candidate` and returns a new `PinnedStateView`。
  - Apply accepted pinned state patch candidate to `PinnedStateView` with field-level tri-state semantics: missing field means keep old field; field present with `null` / empty list means clear the field; field present with non-empty value means replace the full field with the candidate value after validation and policy bounding.
  - `confirmed_subjects` patch values must parse through existing opaque ref JSON helpers or a new private helper using `OpaqueMemoryRef` / `HostNeutralRefKind` validation; free-form business strings must not be accepted as confirmed subject refs.
  - Preserve `verified_facts` rule: no new verified fact from summary; confirmed facts in summary may only reference existing tool fact refs.
- `CONTEXT_COMPACTION_FAILED` is not consumed by memory projection and must not appear in `ConversationMemoryProjectionConsumer.event_filter`。
- Remove or update tests that seed `EPISODE_SUMMARY_ACCEPTED` as canonical compact truth. New tests seed `CONTEXT_COMPACTED`。
- Update RunInputBuilder tests to assert memory messages include pinned state and episode summary derived from `CONTEXT_COMPACTED` after projection catch-up.

Data flow:

`CONTEXT_COMPACTED canonical fact -> ConversationMemoryProjectionConsumer -> project_conversation_memory_event -> memory snapshot -> DurableMemorySnapshotProvider -> RunInputBuilder memory messages`。

Projection pseudo-flow:

```text
if event.event_type == CONTEXT_COMPACTED:
    item = _compact_episode_summary_from_projection_event(event, policy)
    continuity_items = _replace_item_by_id(continuity_items, item)
    pinned_state = _apply_pinned_state_patch_candidate(
        pinned_state, event, policy=policy
    )
```

State transitions:

- `CONTEXT_COMPACTED` event payload itself does not encode Run / Attempt status mutation. Proactive / reactive orchestration may append it in the same write transaction sequence as `RUN_STARTED` / `ATTEMPT_STARTED` or `RUN_FAILED`; those Run / Attempt facts are the only state mutation facts.

Tests:

- `CONTEXT_COMPACTED` with accepted episode summary becomes continuity item.
- Accepted pinned patch updates current goal, confirmed subjects, constraints and open questions according to tri-state semantics.
- Empty patch field clears only the intended field; omitted field leaves previous state unchanged.
- Summary with tool fact refs does not create verified facts.
- Existing `TOOL_RESULT_ACCEPTED` remains the only verified fact source.
- Memory projection consumer consumes committed canonical `CONTEXT_COMPACTED` and writes snapshot/checkpoint in one transaction.
- `CONTEXT_COMPACTION_FAILED` is ignored by memory projection except for unsupported-event diagnostic if explicitly fed to the pure builder in a unit test; production consumer filter must not select it.

Stop condition:

- Stop if memory projection requires Context Governance to directly write memory snapshot/table.

## Slice 4: Proactive Pre-dispatch Orchestration And RunInputBuilder Compact Provider Rebuild

Allowed files / modules:

- `dayu/host/admission.py`
- `dayu/host/dispatch.py`
- `dayu/host/durable/run_transition.py`
- `dayu/host/durable/state.py`
- `dayu/host/durable/event_log.py`
- `dayu/host/durable/schema.py`
- `dayu/host/context_governance.py`
- `dayu/host/run_input.py`
- `dayu/host/api.py`
- `tests/host/test_run_attempt_transitions.py`
- `tests/host/test_admission_queue.py`
- `tests/host/test_dispatch_scheduler.py`
- `tests/host/test_phase5_local_execution_integration.py`
- `tests/host/test_run_input_builder.py`

Exact changes:

- Introduce `RunStatus.ACCEPTED` pre-start state and schema support, as described above.
- Add pre-start governance worker/path in Host dispatch/admission orchestration:
  - Read earliest startable `ACCEPTED` Run, or queued Run when no active Run exists.
  - Treat `ACCEPTED` as a start-blocking admission state: `REJECT` conflicts, `ATTACH_ACTIVE` conflicts because no Attempt exists, and `QUEUE` / `submit_followup(queue)` queue behind it.
  - Allow `cancel_run` for `ACCEPTED` before governance starts; cancellation appends `RUN_CANCELLED` and creates no Attempt / dispatch row.
  - Build a pre-start budget input from durable `USER_INPUT_ACCEPTED`、session memory snapshot at accepted cursor、scenario/policy/tool schema summaries and existing compact artifacts.
  - If under soft threshold, start Run by appending `RUN_STARTED` / `ATTEMPT_STARTED` and dispatch as today.
  - If over soft threshold, append `CONTEXT_COMPACTION_REQUESTED(trigger_source=proactive)`，run compactor once, append `CONTEXT_COMPACTED` or `CONTEXT_COMPACTION_FAILED`。
  - After accepted compact, catch up memory projection through `CONTEXT_COMPACTED`, then start Attempt and RunInputBuilder rebuilds complete messages.
  - If compact fails or compacted estimate remains over hard threshold, append `CONTEXT_COMPACTION_FAILED` and `RUN_FAILED` with no Attempt row.
- Implement `DurableCompactArtifactProvider` in `dayu/host/run_input.py`:
  - Reads accepted compact artifact refs up to the current Attempt cursor.
  - Renders bounded system messages describing compact artifact ref/digest and accepted summary navigation only when needed. Message semantics:
    - role is `SystemMessage`。
    - header is stable, for example `Accepted context compact artifact:`。
    - content includes `compact_artifact_ref`、`compact_artifact_digest`、`compacted_event_id`、`compacted_event_sequence`、`preserved_fact_refs` and a bounded `episode_summary` navigation text.
    - content must not include dropped raw ranges, hidden full artifact JSON or pinned state patch internals; pinned state materialization belongs to memory projection.
    - provider may emit no messages when memory snapshot already materialized the accepted summary and policy decides artifact refs are not needed in model context, but it must still expose `compact_artifact_ref` / digest in `CompactArtifactView` for explainability.
  - Does not cache private messages or read memory projection internals.
- Extend RunInputBuilder factories to accept optional `compact_artifact_provider` and production dispatch to inject durable provider.

Data flow:

`ACCEPTED/QUEUED Run -> ContextGovernance proactive evaluate -> compact canonical events/artifact -> memory catch-up -> RUN_STARTED/ATTEMPT_STARTED -> RunInputBuilder rebuild(messages from EventLog + memory + compact provider) -> Engine dispatch`。

State transitions:

- No compact needed: `ACCEPTED/QUEUED -> RUNNING` with new Attempt / dispatch record.
- Proactive compact accepted: `ACCEPTED/QUEUED -> RUNNING` after `CONTEXT_COMPACTED` and memory catch-up.
- Proactive compact failed: `ACCEPTED/QUEUED -> FAILED`，no Attempt, no dispatch record, no `RECOVERING`。

Tests:

- Proactive soft threshold triggers one compact before any Attempt row exists.
- Proactive compact failure produces `CONTEXT_COMPACTION_FAILED` and `RUN_FAILED` with zero Attempt rows.
- Proactive compact accepted creates `CONTEXT_COMPACTED` before `RUN_STARTED` / `ATTEMPT_STARTED`。
- `cancel_run` on `ACCEPTED` appends `RUN_CANCELLED` and does not create Attempt, dispatch record or active worker cancel target.
- `start_run(REJECT)` with an existing `ACCEPTED` Run returns conflict; `start_run(ATTACH_ACTIVE)` with an existing `ACCEPTED` Run returns conflict rather than attaching; `start_run(QUEUE)` and `submit_followup(queue)` queue behind the `ACCEPTED` Run.
- Queued promotion does not call old direct promotion helper; earliest queued Run is evaluated by the same governance gate before any `RUN_STARTED` / `ATTEMPT_STARTED` event.
- RunInputBuilder called after compact includes memory messages from accepted pinned patch / episode summary and current prompt remains last user message.
- Per-Run proactive trigger count prevents second proactive compact loop.
- Corrupted or unreadable committed compact-count facts fail closed before dispatch.
- Existing queued promotion still preserves FIFO and active-run uniqueness.

Stop condition:

- Stop if implementation cannot keep proactive compact failure attempt-free. Do not reinterpret “pre-dispatch” as “after STARTING Attempt but before worker accept” for this phase.

## Slice 5: Reactive Engine Overflow To RECOVERING To New Attempt

Allowed files / modules:

- `dayu/host/engine_ingest.py`
- `dayu/host/context_governance.py`
- `dayu/host/durable/run_transition.py`
- `dayu/host/durable/state.py`
- `dayu/host/durable/event_log.py`
- `dayu/host/dispatch.py`
- `dayu/host/api.py`
- `tests/host/test_engine_ingest_mapping.py`
- `tests/host/test_run_attempt_transitions.py`
- `tests/host/test_dispatch_scheduler.py`
- `tests/host/test_phase5_local_execution_integration.py`

Exact changes:

- Replace unsupported recovery handling for `EngineEventType.CONTEXT_COMPACTION_REQUESTED` with P10 reactive path:
  - Durable identity guard continues to validate envelope `attempt_id + execution_id`。
  - Append `CONTEXT_COMPACTION_REQUESTED(trigger_source=reactive)` canonical fact with provider request id and budget snapshot refs. Use Host estimator even when Engine `budget_state` is `None`。
  - Close current Attempt according to policy and append `RUN_RECOVERING` to move Run `RUNNING -> RECOVERING`。
  - Run ContextGovernance reactive compact at most once for this Run.
  - On accepted compact, append `CONTEXT_COMPACTED` / artifact, catch up memory projection, append `RUN_STARTED(start_reason=recovery)` and create new Attempt with new `attempt_id` / `execution_id` / dispatch record.
  - On compact failure, append `CONTEXT_COMPACTION_FAILED` and `RUN_FAILED`。
- Handle subsequent recoverable `run_failed(context_compaction_required)` from same old Attempt as idempotent/duplicate close confirmation if the context request already drove recovery. It must not create another recovery attempt or fail the new Attempt.
- Old Attempt events after recovery start remain stale if execution id no longer matches current active Attempt.

Data flow:

`EngineEvent.context_compaction_requested -> EngineEventIngestor validated envelope -> ContextGovernance reactive compact -> canonical compact event/artifact -> memory catch-up -> recovery RUN_STARTED/ATTEMPT_STARTED -> scheduler dispatches new Attempt`。

State transitions:

- Reactive accepted: `RUNNING / Attempt RUNNING -> Attempt FAILED + RUN_RECOVERING -> RECOVERING -> RUNNING / new Attempt STARTING`。
- Reactive failed: `RUNNING / Attempt RUNNING -> Attempt FAILED + RUN_RECOVERING -> FAILED`。
- No `LOST` transition in P10 compact failure.

Tests:

- Reactive overflow with `budget_state=None` still uses Host estimator and produces `CONTEXT_COMPACTION_REQUESTED` with Host budget refs.
- Mismatched stale `attempt_id + execution_id` is rejected and does not compact.
- Accepted reactive compact creates new attempt id and new execution id.
- Old Attempt is not resumed or taken over.
- Reactive compact failure fails Run after current Attempt is closed and never marks `LOST`。
- Per-Run reactive trigger count prevents compact loop.
- Corrupted or unreadable committed reactive compact-count facts fail closed after current Attempt close policy; no second recovery Attempt is created.
- Existing usage projection signal remains non-state-changing.

Stop condition:

- Stop if reactive path cannot distinguish current active attempt identity from stale Engine events.

## Slice 6: Production Composition Wiring, Multi-turn Integration, Docs Sync

Allowed files / modules:

- `dayu/host/api.py`
- `dayu/host/command.py`
- `dayu/host/dispatch.py`
- `dayu/host/README.md`
- `dayu/README.md` only if public layering / composition boundary text changes materially.
- `tests/host/test_public_contracts.py`
- `tests/host/test_phase5_local_execution_integration.py`
- `tests/host/test_dispatch_scheduler.py`
- `tests/README.md`

Exact changes:

- Add production composition fields:
  - `HostCommandHandleOptions.context_window_size: int`
  - `HostCommandHandleOptions.reserved_output_tokens: int`
  - optional `HostCommandHandleOptions.context_budget_hard_threshold_tokens: int | None`
  - optional `HostCommandHandleOptions.context_budget_minimum_protection_tokens: int | None`
  - `HostLocalExecutionOptions.context_budget_policy: ContextBudgetPolicy`
  - context budget provider only when an existing composition root already uses provider-style construction; otherwise prefer passing the typed `ContextBudgetPolicy` value.
  - context governance orchestrator factory or typed options
  - `context_compactor: ContextCompactor`
  - compact artifact store root via existing durable artifact root
  - compact provider injected into RunInputBuilder
- Command handle wiring must pass `context_window_size` and `reserved_output_tokens` explicitly from Service / composition root options into Host context policy provider:
  - Service / composition root supplies the two positive integers to `HostCommandHandleOptions`。
  - `dayu/host/command.py` constructs `ContextBudgetPolicy` from those options when opening local execution, alongside existing durable `artifact_root` / payload policy wiring.
  - `HostLocalExecutionOptions` receives the already typed `ContextBudgetPolicy` and exposes it to pre-start governance, reactive governance and RunInputBuilder compact provider construction.
  - No per-run request metadata, caller payload, Engine runner spec or provider overflow event may override these values.
- Local execution wiring must keep memory projection policy and context policy separate. Memory policy controls memory view; context policy controls budget / compact decisions.
- Add deterministic fake compactor wiring under `tests/host/fake_compaction.py` for tests that need stable low-level compaction injection.
- Production code must not import `tests.host.fake_compaction.FakeContextCompactor`; production paths must use explicit composition injection of a real `ContextCompactor`.
- Update docs only after tests:
  - `dayu/host/README.md` because Host state machine, RunInputBuilder provider, Engine ingest recovery and local execution composition change.
  - `dayu/README.md` only if the UI / Service / Host / Engine boundary description needs context policy provider wording.
  - `tests/README.md` because test coverage categories will add context governance / compaction；explicitly mention `test_context_budget`、`test_compaction_contract`、`test_compact_artifact_store` and `test_context_compact_events`。
  - Root `README.md` only if CLI/config user-facing options for context window / reserved output are exposed.

Data flow:

`Service/composition root options -> HostLocalExecutionOptions/command options -> ContextBudgetProvider + ContextGovernance + Compactor + ArtifactStore -> proactive/reactive orchestration -> RunInputBuilder durable memory + compact providers -> Engine request`。

Tests:

- End-to-end local fake worker scenario:
  - Run 1 creates raw turns and tool verified fact.
  - Follow-up Run under budget includes recent raw turns and verified fact.
  - Later Run over soft threshold triggers proactive compact.
  - `CONTEXT_COMPACTED` is consumed by memory projection.
  - Subsequent Run messages contain pinned state, verified facts, recent raw turns floor and episode summaries in P9/P10 order.
- Reactive fake worker emits `context_compaction_requested`; Host recovers with new Attempt and final fake worker succeeds.
- Public contract tests assert `HostCommandHandleOptions` / `HostLocalExecutionOptions` require valid `context_window_size` and `reserved_output_tokens`，reject invalid values, and no budget parameter is read from metadata / Engine spec / provider overflow.

Stop condition:

- Stop if production composition cannot provide explicit context policy input without reaching into Engine or metadata.

## Validation Commands

Implementation agent must run after each slice or before handoff, using project Python 3.11 venv:

```bash
source .venv/bin/activate
pytest tests/host/test_context_budget.py
pytest tests/host/test_compaction_contract.py tests/host/test_compact_artifact_store.py
pytest tests/host/test_context_compact_events.py
pytest tests/host/test_memory_projection.py tests/host/test_run_input_builder.py
pytest tests/host/test_engine_ingest_mapping.py tests/host/test_run_attempt_transitions.py
pytest tests/host/test_dispatch_scheduler.py tests/host/test_phase5_local_execution_integration.py
pytest tests/host/test_public_contracts.py
pyright
```

Expected assertions:

- No new or expanded pyright errors.
- `CONTEXT_COMPACTED` is canonical memory input; `EPISODE_SUMMARY_ACCEPTED` is not required as compact truth.
- Proactive failure has no Attempt row and no dispatch record.
- Reactive success has old Attempt closed, Run `RECOVERING` event, new Attempt id, new execution id and successful dispatch.
- Verified facts still only come from `TOOL_RESULT_ACCEPTED`。
- Usage remains diagnostic / projection input only.

## Docs Update Decision

P10 implementation touches `dayu/host/`、tests and likely Host local execution public options. Therefore update:

- `dayu/host/README.md` for Host context governance, compact canonical events, reactive recovery and RunInputBuilder compact provider.
- `tests/README.md` for new context governance test categories.
- `dayu/README.md` if composition / layering docs mention context policy provider or the Host-owned context governance boundary.
- Root `README.md` only if user-facing CLI/config options are added for `context_window_size` / `reserved_output_tokens`。

Do not update docs with future design. Only document implemented behavior after tests pass.

## Blocking Questions For Controller

None currently. This plan makes one explicit implementation decision from design evidence: add `RunStatus.ACCEPTED` as the missing pre-start status required to satisfy “proactive compact failure before dispatch must not create Attempt”。If controller rejects that public state-machine/schema change, Slice 4 must stop before implementation.

## Residual Risks

- Owner: Phase 10 implementation. Destination: Slice 4. Risk: adding `RunStatus.ACCEPTED` changes public Run status behavior and may require broad test updates. This is necessary to satisfy no-Attempt proactive failure; avoid hiding it behind queued semantics.
- Owner: Phase 10 implementation. Destination: Slice 5. Risk: Engine may emit both `context_compaction_requested` and recoverable `run_failed`; idempotency must prevent duplicate recovery attempts.
- Owner: Phase 10 implementation. Destination: Slice 2 / Slice 6. Risk: real LLM compactor scene adapter may not be production-ready. Fake compactor can validate Host governance, but production must still wire an explicit compactor port or fail closed.
- Owner: Phase 13. Destination: Audit / Tool Trace / Outbox phase. Risk: P10 can only write typed refs and diagnostics for later sinks; rich audit/tool trace materialization remains deferred.
- Owner: Phase 11. Destination: Recovery phase. Risk: crash between artifact file write and DB event append can leave orphan artifact files; they are not truth. Startup recovery / cleanup is out of P10.
- Owner: future tokenizer adapter phase. Destination: Provider-specific tokenizer. Risk: conservative estimator may trigger more compact than necessary, but must never use provider overflow as budget truth.
