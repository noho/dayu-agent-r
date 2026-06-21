# WU-CM-13 Unified Compact Pipeline Plan

## 1. Plan Gate Verdict

WU-CM-13 的动机仍成立，严重性评估正确；本次 plan fix 后，实施边界收窄为 Host 内部 compact 语义 helper 收敛，而不是新增一个厚 pipeline coordinator。

第一性原理判断：compact 是 Host governance。Engine 只在 provider context overflow 时产出 `context_compaction_requested` 并以 `context_compaction_required` 收口；是否 compact、如何构造 material、如何写 accepted / failed compact event、如何 fallback、如何恢复 dispatch 都属于 Host。当前代码已经把部分 material helper 共享到 `compact_material.py`、`context_fallback.py` 与 `compaction_operation.py`，但 `CompactionRequest` 构造、tier 1-3 recovery request 构造、fallback payload input、ordinary post-compaction protected raw-tail selection 仍分散在 proactive dispatch、reactive ingest 和 RunInputBuilder 中。

不成立的动机：不需要补 reactive outer lifecycle sequencing。当前代码已有 reactive Engine ingest recovery sequencing、active attempt 校验、取消 token 传递、事务外 compact 后 caller-side commit guard、accepted compact 后 recovery Attempt，以及 fallback dispatch / fail-closed ordering。WU-CM-13 不合并 proactive / reactive outer lifecycle，不新增 reactive-only lifecycle 实现。

修正后的 code-generation-ready 目标：新增一个薄的 `dayu/host/compact_pipeline.py` helper owner，仅承载 pure / near-pure material-to-request、recovery-request、fallback-decision-input、payload-input 与 WU-CM-14 raw-tail selection helper。它不控制 `compaction_operation` loop，不写 EventLog，不创建 artifact，不推进 Run / Attempt 状态，不创建 recovery Attempt，不拥有 dispatch lifecycle 或 engine ingest lifecycle。

## 2. Direct Evidence

设计真源证据：

- `docs/host/design.md:52-54` 定义 RunInputBuilder、Conversation Memory 与 Context Governance 的 owner：RunInputBuilder 构造 Engine messages；Conversation Memory 只消费 committed EventLog facts 与 accepted compact projection；Context Governance 负责预算、compact 编排与 compact 事件收口。
- `docs/host/design.md:3193-3265` 固定 tier 0-5 都是同一套 `assemble(...)` material 语义；tier 1-3 可提交 `CONTEXT_COMPACTED` 并生成五类 Session Semantic Memory，dispatch fallback 不提交 compact、不 materialize memory，只影响本次 RunInput rendering 且必须有 failed diagnostic。
- `docs/host/design.md:3282-3308` 固定 compact request 输入为 `ConversationCompactInputVNext`，selection 候选为 `post_compact_delta_material`，current input anchor 与 protected recent floor 必须保留，LLM-facing material 不得暴露裸 event id / payload ref / digest / cursor。
- `docs/host/design.md:3331-3383` 固定 proactive / reactive 触发 envelope 不同，但 compact 是 Host governance；reactive 必须校验 active attempt、关闭当前 Attempt、compact 后 recovery dispatch 或 failed / fallback 收口。
- `docs/engine/design.md:487-503` 明确 Engine 不做上下文压缩、预算或 retry；provider overflow 只交给 Host compact / recovery。

当前已共享的 helper / owner：

- `dayu/host/compact_material.py:209-545` 定义 `RunInputMaterialBlock`、`PreDispatchCompactMaterialView` 与 `build_pre_dispatch_compact_material_view(...)`，从 EventLog durable truth 构造 latest accepted compacted view、post-compact delta material、current input boundary 和 budget fragments。
- `dayu/host/compact_material.py:885-1079` 共享 `select_compact_segment(...)`、`degrade_previous_compacted_view_for_recovery(...)` 与 `build_compact_material_pack(...)`。
- `dayu/host/compact_material.py:1658-1765` 共享 protected recent floor 的 turn-group selection 和 exclusion reason。
- `dayu/host/compact_material.py:2037-2335` 共享 post-compact delta source：只读 `USER_INPUT_ACCEPTED`、`RUN_SUCCEEDED`、`TOOL_RESULT_ACCEPTED`，并把 user、assistant final answer、accepted tool evidence 映射为 material blocks。
- `dayu/host/context_fallback.py:481-620` 共享 recent-window fallback selection 与 fallback budget estimate。
- `dayu/host/compaction_operation.py:567-620` 共享事务外 compactor proposal / retry / cancellation loop，模块 docstring 明确 EventLog 写入、artifact 写入、memory projection 与 durable recheck 仍由调用方治理路径负责。

仍分散的 material-to-request / payload-input / fallback-input owner：

- Proactive 在 `dayu/host/dispatch.py:1502-1620` 自己构造 tier 1-3 recovery requests。
- Proactive 在 `dayu/host/dispatch.py:1829-1897` 自己构造 normal `CompactionRequest`。
- Proactive 在 `dayu/host/dispatch.py:2079-2228` 自己构造 fallback selection、估算 fallback budget、组装 failed payload input，并决定 dispatch / fail-closed。
- Reactive 在 `dayu/host/engine_ingest.py:3780-3918` 自己构造 root request、multi-pass pass queue 和 fallback decision。
- Reactive 在 `dayu/host/engine_ingest.py:1880-2055` 自己组装 accepted / failed compact payload input。
- `dayu/host/run_input.py:1891-2088` 的 ordinary RunInput branch 直接拼 `memory.messages + compact.messages + protected_recent_raw_tail.messages + continuity.messages`；fallback branch 另走 `_fallback_context_messages(...)`。
- WU-CM-14 新增 `dayu/host/run_input.py:557-576`、`1369-1505` 的 protected recent raw-tail provider，内部再次读取 `build_pre_dispatch_compact_material_view(...)` 并独立做 floor selection，是必须纳入 WU-CM-13 audit 的 RunInput-only 旁路。
- `dayu/host/compaction_evidence.py:1-8` 声称服务 proactive / reactive request material 输入，但生产代码无 import，仅 `tests/host/test_compaction_operation.py` 仍调用 `collect_selected_compaction_request_evidence_inputs(...)`。这是无生产 caller 的 shadow material owner。

## 3. Root Cause

Root cause 不是 reactive lifecycle 缺口，也不是 WU-CM-14 未修完整。WU-CM-14 已修复 protected recent floor 的关键行为，但为了最小边界保留了 EventLog second-read raw-tail provider，并把完整 pipeline 收敛留给 WU-CM-13。

真实 root cause 是 compact 语义 owner 被拆散：

- material source owner 在 `compact_material.py`。
- compact request construction 分散在 `dispatch.py` 与 `engine_ingest.py`。
- tier 1-3 recovery request construction 分散在 `dispatch.py` 与 `engine_ingest.py`。
- fallback selection helper 在 `context_fallback.py`，但 fallback payload input 与后续动作仍分散在 proactive / reactive caller。
- ordinary protected raw-tail selection 在 `run_input.py`，未与 fallback / compact selection 共享同一个 helper。
- `compaction_evidence.py` 还保留一套已脱离生产 caller 的旧 evidence/history/fact material reader。

这些 owner 分散会造成四类漂移：

1. 五类 Session Semantic Memory 漂移：accepted `CONTEXT_COMPACTED` 的 candidate 是 Conversation Memory 投影源；如果 proactive / reactive 对 `previous_compacted_view`、selected blocks、label mapping refs、accepted evidence refs 的构造不同，同一语义会投影出不同 session summary、evidence facts、answer anchors、forward intents 和 reference continuity。
2. `assemble(...)` rendering 漂移：ordinary RunInput、compact input 和 fallback RunInput 都应来自同一 material view / selection 语义；现在 ordinary raw tail、fallback renderer 与 compact request construction 彼此独立。
3. fallback 漂移：本 WU 只统一现有 recent-window/floor fallback 的 selection 和 payload-input semantics；dispatch / recovery Attempt creation 仍属于 caller。若 selection/source refs/digest 与 RunInputBuilder 验证逻辑不同源，fallback dispatch 可能和实际渲染不一致。
4. WU-CM-14 preservation 漂移：protected recent raw-tail provider 是 post-compaction ordinary RunInput 的 second-read provider；若不把 selection eligibility 迁入 shared helper，后续 proactive-only / reactive-only / RunInput-only 例外会继续扩散。

## 4. Minimal Implementation Boundary

Allowed production files:

- `dayu/host/compact_pipeline.py`：新增薄 shared helper owner，目标小于 500 行；只暴露本计划列出的 dataclass 与函数。
- `dayu/host/compact_material.py`：仅允许复用 / 暴露已有 material helper，或迁入 `compaction_evidence.py` 中仍需的 private material reader；不得新增 public API。
- `dayu/host/context_fallback.py`：保留 fallback selection / active fallback hydration helper；必要时让 `compact_pipeline.py` 调用它，不把 lifecycle action 放进去。
- `dayu/host/dispatch.py`：proactive caller 改为调用薄 helper；保留 admission、precondition、commit guard、EventLog append、dispatch start。
- `dayu/host/engine_ingest.py`：reactive caller 改为调用薄 helper；保留 Engine event validation、Attempt closeout、`RUN_RECOVERING`、commit guard、EventLog append、recovery Attempt scheduling。
- `dayu/host/run_input.py`：ordinary protected raw-tail provider 调用 `compact_pipeline.py` 的 shared selection/provider helper；fallback branch继续消费 `ActiveRecentWindowFallback` / fallback material view。
- `dayu/host/compaction_evidence.py`：删除，或迁移仍需能力到 `compact_material.py` / `compact_pipeline.py` 后删除该 shadow module。

Allowed test files:

- `tests/host/test_compact_pipeline.py` 新增 focused helper tests。
- `tests/host/test_compact_material.py`
- `tests/host/test_context_fallback.py` 如存在或需要新增。
- `tests/host/test_dispatch_scheduler.py`
- `tests/host/test_engine_ingest.py`
- `tests/host/test_run_input_builder.py`
- `tests/host/test_compaction_operation.py` 只迁移 `compaction_evidence.py` 相关 tests，不扩大 operation owner。
- `tests/host/test_memory_projection.py`

明确不触碰：

- 不改 `dayu.host` public exports。
- 不改 public request / response dataclass、`open_host(options)` 字段、`SubmitFollowupRequest` 字段。
- 不改 EventLog event type、canonical fact 名称或 durable schema。
- 不新增 `fallback_tier` payload 字段。
- 不改 compact artifact schema / payload schema。
- 不改 Engine provider contract、EngineEvent contract 或 LLM compactor provider contract。
- 不改 smoke 脚本，不降低断言，不绕过真实 Host path。

## 5. Thin Shared Helper Contracts

`dayu/host/compact_pipeline.py` 是 thin helper owner，不是 coordinator。它可以 import `compact_material.py`、`context_fallback.py`、`context_budget.py`、`context_policy.py`、`memory.py` 与 `compaction.py` 的 typed contracts；不得 import dispatch scheduler、engine ingest class、durable state transition helpers 或 worker/lifecycle owner。

### 5.1 Dataclass Contracts

Implementation 必须按以下字段表实现；字段名和类型应保持稳定，除非直接代码证据显示某字段不可用，届时先更新 plan/review。

```python
@dataclass(frozen=True, slots=True)
class CompactPipelineSourceSnapshot:
    session_id: str
    run_id: str
    trigger_source: ContextCompactionTriggerSource
    current_input_ref: str
    current_input_text: str
    input_event_sequence: int
    material_blocks: tuple[RunInputMaterialBlock, ...]
    previous_compacted_view: tuple[CompactMaterialBlock, ...]
    source_boundary: CompactMaterialSourceBoundary
    material_view_digest: str
    material_source_refs: tuple[str, ...]
```

语义：这是 compact helper 的 source snapshot，不是 lifecycle guard。它不包含 `expected_run_status`、`attempt_status`、dispatch record status 或 session active slot 字段。`dispatch.py` 与 `engine_ingest.py` 各自用自己的 lifecycle facts 做 commit guard。

```python
@dataclass(frozen=True, slots=True)
class CompactPipelineRequestPlan:
    request: CompactionRequest
    selected_segment: CompactSegmentSelection
    selected_evidence_refs: tuple[str, ...]
    selected_raw_turn_refs: tuple[str, ...]
    selected_source_refs: tuple[str, ...]
    source_snapshot: CompactPipelineSourceSnapshot
```

语义：normal compact request 或单个 recovery request 的 plan。不包含 operation loop、accepted result、EventLog row 或 lifecycle action。

```python
@dataclass(frozen=True, slots=True)
class CompactPipelineRecoveryRequestPlan:
    tier_name: str
    request_plan: CompactPipelineRequestPlan
```

允许 `tier_name`：`tier_1_fallback_caps`、`tier_2_section_degrade`、`tier_3_delta_only`。本 WU 不新增 tier 5。

```python
@dataclass(frozen=True, slots=True)
class CompactPipelinePassQueuePlan:
    root_request_plan: CompactPipelineRequestPlan
    pass_requests: tuple[CompactionRequest, ...]
```

语义：reactive multi-pass request queue 的纯构造结果；operation loop 仍由 caller 调 `run_compaction_operation(...)`。

```python
@dataclass(frozen=True, slots=True)
class CompactPipelineAcceptedPayloadInput:
    request: CompactionRequest
    candidate: ConversationCompactOutputVNext
    quality: CompactQualityCheckResultVNext
    budget_after_compact: int
    accepted_attempt_number: int
    accepted_proposal_manifest_ref: str | None
    accepted_proposal_manifest_digest: str | None
    prompt_local_label_mapping_refs: tuple[str, ...]
    source_boundary_refs: tuple[str, ...]
    accepted_evidence_mapping_refs: tuple[str, ...]
```

语义：给 caller 构造 `CONTEXT_COMPACTED` payload 的字段输入。Event id、actor/source、occurred_at、attempt_id / execution_id、artifact write 和 EventLog append 仍由 caller 控制。

```python
@dataclass(frozen=True, slots=True)
class CompactPipelineFailedPayloadInput:
    operation_id: str
    failure_reason: str
    attempt_count: int
    retry_repair_budget_exhausted: bool
    budget_after_attempted_compact: int | None
    fallback_policy_decision: str | None
    fallback_input_window: Mapping[str, JsonValue] | None
    fallback_input_digest: str | None
    fallback_budget_result: Mapping[str, JsonValue] | None
    fallback_action: str
```

语义：给 caller 构造 `CONTEXT_COMPACTION_FAILED` payload 的字段输入。不得新增 `fallback_tier`。

```python
@dataclass(frozen=True, slots=True)
class CompactPipelineFallbackSelectedMaterialHandoff:
    selected_block_ids: tuple[str, ...]
    material_blocks: tuple[RunInputMaterialBlock, ...]
    source_refs: tuple[str, ...]
    fallback_input_digest: str
    selected_material_view_digest: str
    selected_recent_window_turn_floor: int
    selected_raw_turn_count: int
```

语义：只服务 production fallback branch 的 selected material 校验/渲染，由 `build_fallback_decision_input(...)` 构造并挂到 `CompactPipelineFallbackDecisionInput.fallback_handoff`。它不替代 ordinary raw-tail handoff，也不持久化为新的 payload schema 字段。

```python
@dataclass(frozen=True, slots=True)
class CompactPipelineFallbackDecisionInput:
    selection: RecentWindowFallbackSelection | None
    budget_result: RecentWindowFallbackBudgetResult | None
    failed_payload_input: CompactPipelineFailedPayloadInput
    fallback_handoff: CompactPipelineFallbackSelectedMaterialHandoff | None
    action_hint: str
```

语义：shared helper 只给出 selection / payload input / fallback selected-material handoff / `dispatch` 或 `fail_closed` action hint。`fallback_handoff` 是 production fallback branch 消费的 selected material view；当 `selection is None` 时为 `None`。proactive caller 决定是否 start dispatch；reactive caller 决定是否 create recovery Attempt 或 fail recovering Run。

```python
@dataclass(frozen=True, slots=True)
class CompactPipelineOrdinaryRawTailHandoff:
    messages: tuple[AgentMessage, ...]
    material_blocks: tuple[RunInputMaterialBlock, ...]
    source_refs: tuple[str, ...]
    material_view_digest: str
    selected_recent_window_turn_floor: int
```

语义：只服务 ordinary post-compaction RunInput raw-tail provider。它不包含 fallback selected blocks。

### 5.2 Function Signatures

Source snapshot builder：

```python
def compact_pipeline_source_snapshot_from_pre_dispatch_view(
    *,
    trigger_source: ContextCompactionTriggerSource,
    run: RunRow,
    material_view: PreDispatchCompactMaterialView,
) -> CompactPipelineSourceSnapshot: ...
```

用途：把 caller 已冻结的 `RunRow` lifecycle facts 与 `PreDispatchCompactMaterialView` material facts 收敛成 shared helper source snapshot。字段来源必须固定如下：

- `session_id`、`run_id`、`current_input_ref`、`input_event_sequence` 来自 `run`。
- `trigger_source` 来自 caller 显式参数。
- `current_input_text`、`material_blocks`、`previous_compacted_view`、`source_boundary` 来自 `material_view`。
- `material_view_digest` 使用现有 `selected_material_view_digest(material_view.material_blocks)` 计算，表示完整 material view digest，不是 policy digest。
- `material_source_refs` 使用现有 `selected_material_source_refs(material_blocks=material_view.material_blocks, selected_block_ids=tuple(block.block_id for block in material_view.material_blocks))` 计算，表示完整 material view 覆盖的 canonical source refs。

该函数不得读取 EventLog、不得做 lifecycle status 判断。若 `run.input_event_sequence` 与 `material_view.source_boundary.current_input_event_sequence` 不一致，应抛出 typed validation error，由 caller 按现有 guard/fail-closed 语义处理。

Normal compact request builder：

```python
def build_normal_compact_request_plan(
    *,
    source_snapshot: CompactPipelineSourceSnapshot,
    selection_policy_digest: str,
    budget_before_compact: BudgetEstimate,
    selected_recent_window_turn_floor: int,
    attempt_id: str | None = None,
    execution_id: str | None = None,
) -> CompactPipelineRequestPlan: ...
```

用途：替代 `dispatch.py` normal proactive request construction 和 `engine_ingest.py` reactive root request construction。`selection_policy_digest` 表示 selection policy/config digest，必须由同一个 `MemoryProjectionPolicy` 调 `digest_memory_projection_policy(memory_policy)` 得到；它不是 `BudgetEstimate.estimator_digest`，也不是 `source_snapshot.material_view_digest`。`trigger_source` 从 `source_snapshot.trigger_source` 进入 `CompactionRequest.trigger_source`；reactive caller 传 `attempt_id/execution_id`，proactive caller 传 `None`。

Tier recovery request builder：

```python
def build_tier_recovery_request_plans(
    *,
    source_snapshot: CompactPipelineSourceSnapshot,
    root_request_plan: CompactPipelineRequestPlan,
    memory_policy: MemoryProjectionPolicy,
) -> tuple[CompactPipelineRecoveryRequestPlan, ...]: ...
```

用途：替代 proactive `_proactive_compaction_recovery_attempts(...)`，并为 reactive 使用同一 recovery request 语义提供 focused helper tests。该函数只构造 tier 1/2/3 request plans，不调用 compactor。每个 tier 必须调用/复用 `build_compact_material_pack(...)` 构造完整 `CompactionRequest.material_pack`，再返回含完整 `CompactionRequest` 的 `CompactPipelineRequestPlan`；§5 允许 import `compact_material.py` 已覆盖该依赖。

Reactive pass queue builder：

```python
def build_reactive_pass_queue_plan(
    *,
    source_snapshot: CompactPipelineSourceSnapshot,
    root_request_plan: CompactPipelineRequestPlan,
) -> CompactPipelinePassQueuePlan: ...
```

用途：替代 `_reactive_compaction_pass_queue(...)` 的纯构造部分。

Accepted payload input builder：

```python
def build_compacted_payload_input(
    *,
    request: CompactionRequest,
    candidate: ConversationCompactOutputVNext,
    quality: CompactQualityCheckResultVNext,
    budget_after_compact: int,
    accepted_attempt_number: int,
    accepted_proposal_manifest_ref: str | None,
    accepted_proposal_manifest_digest: str | None,
) -> CompactPipelineAcceptedPayloadInput: ...
```

用途：统一 proactive / reactive accepted payload input 的 semantic fields。caller 仍负责 artifact write 和 EventLog append。

Failed / fallback decision input builder：

```python
def build_fallback_decision_input(
    *,
    source_snapshot: CompactPipelineSourceSnapshot,
    context_policy: ContextBudgetPolicy,
    memory_policy: MemoryProjectionPolicy,
    operation_id: str,
    failure_reason: str,
    attempt_count: int,
    retry_repair_budget_exhausted: bool,
    budget_after_attempted_compact: int | None,
) -> CompactPipelineFallbackDecisionInput: ...
```

用途：统一当前已存在的 recent-window/floor fallback selection、budget、failed payload input 与 action hint。该函数不实现 current-input-only tier 5，不创建 Attempt，不 fail Run。

Ordinary protected raw-tail selector / provider hook：

```python
def select_ordinary_protected_raw_tail(
    *,
    source_snapshot: CompactPipelineSourceSnapshot,
    selected_recent_window_turn_floor: int,
    memory: MemorySnapshotView,
) -> CompactPipelineOrdinaryRawTailHandoff: ...
```

用途：让 WU-CM-14 protected raw-tail selection eligibility 由 shared helper 控制。`run_input.py` 的 second-read provider 仍可存在，但必须调用该 helper，不得自己计算 protected groups。

Pipeline-owned audited second-read provider hook：

```python
class CompactPipelineProtectedRawTailProvider(Protocol):
    def load_ordinary_raw_tail(
        self,
        snapshot: AttemptDispatchSnapshot,
        current_facts: CurrentRunFacts,
        memory: MemorySnapshotView,
        compact: CompactArtifactView,
    ) -> CompactPipelineOrdinaryRawTailHandoff: ...
```

本 WU 选择 `pipeline-owned audited second-read provider`，不做 durable handoff 消除。实现可放在 `compact_pipeline.py`，或保留在 `run_input.py` 但必须只作为 adapter 调用 `compact_pipeline.py` helper。它仍允许 EventLog second read，但必须：

- 校验 compact artifact 是 current run、current attempt start cursor 前的 latest accepted compact event。
- 用 same read transaction 构造 `CompactPipelineSourceSnapshot`。
- 校验 `source_snapshot.input_event_sequence == current_facts.run.input_event_sequence`。
- 校验 `source_snapshot.source_boundary.current_input_event_sequence == current_facts.user_input_event.event_sequence`。
- 校验 `source_snapshot.material_view_digest` 与 provider 选择 handoff 使用的 digest 一致。
- 调用 `select_ordinary_protected_raw_tail(...)` 选择 raw tail。

这不是 durable handoff 消除；WU-CM-13 只把 selection/render eligibility 收归 shared helper owner。

## 6. Caller Wiring Pseudocode

### 6.1 Proactive Dispatch Caller

```python
material_view = build_pre_dispatch_compact_material_view(...)
source_snapshot = compact_pipeline_source_snapshot_from_pre_dispatch_view(
    trigger_source=ContextCompactionTriggerSource.PROACTIVE,
    run=run,
    material_view=material_view,
)
selection_policy_digest = digest_memory_projection_policy(memory_policy)
request_plan = build_normal_compact_request_plan(
    source_snapshot=source_snapshot,
    selection_policy_digest=selection_policy_digest,
    budget_before_compact=estimate,
    selected_recent_window_turn_floor=memory_policy.selected_recent_window_turn_floor,
)
operation_result = await run_compaction_operation(
    request=request_plan.request,
    pass_queue=(),
    ...
)
if operation_result.accepted:
    payload_input = build_compacted_payload_input(...)
    # dispatch.py writes artifact, appends CONTEXT_COMPACTED, and starts same Run.
else:
    fallback_input = build_fallback_decision_input(...)
    fallback_handoff = fallback_input.fallback_handoff
    # dispatch.py uses fallback_handoff only to validate/render selected fallback material
    # and populate existing fallback payload input fields; it does not persist a new field.
    # dispatch.py appends CONTEXT_COMPACTION_FAILED.
    # dispatch.py starts dispatch only when action_hint == "dispatch"; otherwise fail-unstarted.
```

### 6.2 Reactive Engine Ingest Caller

```python
material_view = build_pre_dispatch_compact_material_view(...)
source_snapshot = compact_pipeline_source_snapshot_from_pre_dispatch_view(
    trigger_source=ContextCompactionTriggerSource.REACTIVE,
    run=context.run,
    material_view=material_view,
)
selection_policy_digest = digest_memory_projection_policy(memory_policy)
root_plan = build_normal_compact_request_plan(
    source_snapshot=source_snapshot,
    selection_policy_digest=selection_policy_digest,
    budget_before_compact=estimate,
    selected_recent_window_turn_floor=memory_policy.selected_recent_window_turn_floor,
    attempt_id=context.attempt.attempt_id,
    execution_id=context.attempt.execution_id,
)
pass_queue = build_reactive_pass_queue_plan(
    source_snapshot=source_snapshot,
    root_request_plan=root_plan,
).pass_requests
# engine_ingest.py appends CONTEXT_COMPACTION_REQUESTED, closes Attempt, RUN_RECOVERING.
operation_result = await run_compaction_operation(
    request=root_plan.request,
    pass_queue=pass_queue,
    cancellation_token=context.candidate.envelope.cancellation_token,
    ...
)
# engine_ingest.py performs its own RECOVERING/input cursor/execution guard.
if operation_result.accepted:
    payload_input = build_compacted_payload_input(...)
    # engine_ingest.py writes artifact, appends CONTEXT_COMPACTED, creates recovery Attempt.
else:
    fallback_input = build_fallback_decision_input(...)
    fallback_handoff = fallback_input.fallback_handoff
    # engine_ingest.py uses fallback_handoff only to validate/render selected fallback material
    # and populate existing fallback payload input fields; it does not persist a new field.
    # engine_ingest.py appends CONTEXT_COMPACTION_FAILED.
    # engine_ingest.py creates recovery Attempt only when action_hint == "dispatch"; otherwise fail recovering Run.
```

### 6.3 RunInputBuilder Ordinary Branch

```python
fallback = context_fallback_provider.load_context_fallback(...)
if fallback is None:
    raw_tail = (
        protected_raw_tail_provider.load_ordinary_raw_tail(...)
        if compact.compact_artifact_ref is not None
        else empty_raw_tail
    )
    bounded_context_messages = (
        *memory.messages,
        *compact.messages,
        *raw_tail.messages,
        *continuity.messages,
    )
else:
    fallback_material_blocks = (
        fallback.material_blocks
        if fallback.material_blocks is not None
        else build_run_input_material_blocks(...)
    )
    bounded_context_messages = _fallback_context_messages(
        fallback=fallback,
        material_blocks=fallback_material_blocks,
    )
```

说明：ordinary branch 消费 `CompactPipelineOrdinaryRawTailHandoff`，替代当前 `_ProtectedRecentRawTailView` 的 selection owner；fallback branch 仍消费 `ActiveRecentWindowFallback` 和 fallback material blocks，不消费 ordinary raw-tail handoff，避免 double render。fallback branch 的 selected material 语义来自 `build_fallback_decision_input(...).fallback_handoff` 写入/校验过的现有 fallback window fields，RunInputBuilder 不接收新的 durable handoff 字段。

### 6.4 Fallback Branch Handoff

`CompactPipelineFallbackSelectedMaterialHandoff` 是 production fallback decision input 的一部分，不是 test-only type。`build_fallback_decision_input(...)` 必须在 fallback selection 存在时构造它，并通过 `CompactPipelineFallbackDecisionInput.fallback_handoff` 返回；proactive / reactive caller 用它校验 selected material digest/source refs，并把等价语义填入现有 `fallback_input_window` / `fallback_input_digest` / `source_refs` / `selected_material_view_digest` 字段。它不进入 ordinary branch，不新增 durable payload 字段，不替代 `ActiveRecentWindowFallback` 的读取模型。

## 7. Commit Guard Boundary

`compact_pipeline.py` 不输出 `expected_run_status`、`expected_attempt_status`、dispatch record status 或 session active slot 字段。

Shared helper 只输出或携带：

- `CompactPipelineSourceSnapshot.input_event_sequence`
- `CompactPipelineSourceSnapshot.material_view_digest`
- `CompactPipelineSourceSnapshot.material_source_refs`
- `CompactPipelineSourceSnapshot.source_boundary`
- `operation_id`
- request / selection digest
- accepted proposal manifest refs

Proactive guard remains in `dispatch.py`:

- Run/session still allows proactive compaction.
- input cursor still matches caller-frozen facts.
- unstarted Run can still be dispatched or failed.

Reactive guard remains in `engine_ingest.py`:

- Engine candidate still matches active attempt / execution.
- after transaction-outside operation, Run is still `RECOVERING`.
- source Attempt has terminal event.
- `run.input_event_sequence` still matches caller-frozen input cursor.
- execution was not replaced.

Stale result handling remains caller-owned. Shared helper must not commit or discard EventLog facts.

## 8. Fallback Scope Decision

本 WU 不新增未实现的 tier 5 current-input-only fallback，也不新增 `fallback_tier` payload 字段。

当前实现已有的是 recent-window/floor fallback selection：

- `build_recent_window_fallback_selection(...)` 固定 current input anchor 与 protected recent floor，并按 caps / hard budget 追加 recent material。
- `CONTEXT_COMPACTION_FAILED` payload 记录 fallback window、digest、budget result 和 action。

WU-CM-13 只收敛这套现有 fallback behavior 的 selection / payload-input semantics，让 proactive / reactive 共享 `build_fallback_decision_input(...)`。Design 中 tier 5 current-input-only fallback 是 deferred future owner。若后续要实现，必须单独进入 design / plan gate，先裁决 payload schema 是否需要 `fallback_tier` 或等价字段。

测试计划不得要求 tier 5；只验证 existing recent-window/floor fallback 的 dispatch/fail-closed 行为。

## 9. WU-CM-14 Preservation Audit

本 WU 明确选择 `pipeline-owned audited second-read provider`。

原因：消除 EventLog second read 需要把 frozen `PreDispatchCompactMaterialView` 或 material handoff durable / in-memory 传到 RunInputBuilder，会扩大 schema / lifecycle handoff 设计，不符合本 WU 的最小边界。当前 WU 只把 selection/render eligibility 收进 shared helper，并强化校验。

Implementation requirements:

- `_DurableProtectedRecentRawTailProvider` 不得继续自己计算 protected group ids。
- Provider 必须调用 `CompactPipelineProtectedRawTailProvider.load_ordinary_raw_tail(...)` 或直接调用 `select_ordinary_protected_raw_tail(...)`。
- Provider second read 必须校验 current-run compact event、input cursor、source boundary 与 material digest。
- Ordinary raw tail 与 fallback selected material 都必须复用 `_fallback_message_from_material_block(...)` 或等价 shared renderer，继续过滤内部 refs。
- 不能只把 provider 文件位置挪到 `compact_pipeline.py` 而保留独立 selection 逻辑。

Acceptance signal：proactive compact-success、reactive compact-success、proactive fallback、reactive fallback 的 protected recent user / assistant final answer / accepted readable evidence selection 均由 shared helper 测试覆盖。

## 10. `compaction_evidence.py` 收口策略

首选策略：删除 `dayu/host/compaction_evidence.py`，迁移测试到 `compact_material.py` / `compact_pipeline.py`。备选策略仅允许迁移仍需能力后删除原模块；不得留下无生产 caller 的 shadow owner。

测试迁移 mapping：

| 当前测试 | 当前覆盖 | 裁决 |
|---|---|---|
| `test_selected_compaction_request_evidence_inputs_read_only_selected_refs` | 只读取 selected session 内 refs，不读跨 session ref | 迁移到 `test_compact_pipeline.py`，用 source snapshot/request plan selected refs 断言只含 selected material |
| `test_evidence_input_reads_raw_tool_result_descriptor_not_envelope_preview` | 从 descriptor raw payload 读取，不读 envelope preview | 迁移到 `test_compact_material.py`，断言 `build_pre_dispatch_compact_material_view(...)` 的 accepted evidence block raw text / payload refs |
| `test_evidence_input_prefers_semantic_query_from_tool_request_atom` | query text 优先 durable semantic query | 迁移到 `test_compact_material.py` accepted evidence material block readable query |
| `test_evidence_input_semantic_query_text_is_not_truncated` | semantic query 不按旧长度截断 | 迁移到 `test_compact_material.py` |
| `test_evidence_input_missing_tool_request_atom_emits_limited_signal` | 缺 request atom 时 LLM-facing query 为 limited signal 且不泄漏 ids | 迁移到 `test_compact_material.py` 与 RunInput LLM-facing negative assertion |
| `test_evidence_block_shares_durable_query_text_without_chunking` | 长 evidence 不 chunk，单 block 共享 query text | 迁移到 `test_compact_material.py` 或删除 chunk 相关旧断言；保留 no unexpected chunk labels 断言 |
| `test_missing_or_digest_mismatch_raw_evidence_fails_closed` | 缺 raw payload / descriptor digest mismatch fail closed | 迁移到 `test_compact_material.py` source material fail-closed tests |
| `test_no_result_preview_field_is_read_or_rendered` | 旧 result_preview 不读不渲染 | 迁移到 `test_compact_material.py` |
| `test_selected_compaction_request_evidence_inputs_allow_empty_without_envelope` | 无 envelope 时空 evidence 输入 | 迁移到 `test_compact_material.py`，断言无 evidence block |
| `test_compaction_request_evidence_inputs_reject_malformed_envelope` | malformed envelope fail closed | 迁移到 `test_compact_material.py` |
| `test_compaction_request_evidence_inputs_reject_missing_raw_tool_outcome` | missing raw outcome fail closed | 迁移到 `test_compact_material.py` |
| `test_compaction_request_evidence_inputs_reject_envelope_producer_mismatch` | producer ref mismatch fail closed | 迁移到 `test_compact_material.py` |
| `test_compaction_request_evidence_inputs_reject_malformed_compacted_payload` | malformed compacted payload fact refs fail closed | 迁移到 `test_compact_pipeline.py` request plan / accepted fact refs helper tests |
| `test_compaction_request_evidence_inputs_deduplicate_accepted_evidence_ids` | accepted evidence ids 去重 | 迁移到 `test_compact_pipeline.py` request plan selected evidence refs |
| `test_compaction_request_evidence_inputs_collect_run_succeeded_raw_context` | `RUN_SUCCEEDED.final_answer` 进入 assistant material | 迁移到 `test_compact_material.py` post-compact delta material |
| `test_compaction_request_evidence_inputs_collect_terminal_content` | terminal artifact content 优先 | 迁移到 `test_compact_material.py` |
| `test_compaction_request_evidence_inputs_ignore_summary_only_run_succeeded` | summary-only terminal 不生成 answer material | 迁移到 `test_compact_material.py` |
| `test_compaction_request_evidence_inputs_use_stable_derived_fact_refs` | accepted compact facts 派生 stable memory item refs | 迁移到 `test_compact_pipeline.py` 或 `test_memory_projection.py`，以 accepted compact candidate refs 为准 |

迁移后验证：

```bash
source .venv/bin/activate
pytest tests/host/test_compact_material.py tests/host/test_compact_pipeline.py tests/host/test_compaction_operation.py -q
rg -n "compaction_evidence|collect_selected_compaction_request_evidence_inputs|SelectedEvidenceBlockRef" dayu tests
```

`rg` 必须无结果。若 `tests/host/test_compaction_operation.py` 仍保留 operation loop tests，它不得 import `compaction_evidence.py`。

## 11. Memory Equivalence Standard

五类 Session Semantic Memory 等价标准：

- 对同一个 `ConversationCompactOutputVNext.accepted_candidate` 和同一 policy，proactive / reactive `CONTEXT_COMPACTED` 投影后，以下 semantic projection fields 必须逐字段等价：
  - `session_summary_memory.summary_text`
  - `evidence_fact_memory.evidence_backed_facts[*].claim_text`
  - `evidence_fact_memory.evidence_backed_facts[*].evidence_kind`
  - `answer_anchor_memory.anchors[*].anchor_title`
  - `answer_anchor_memory.anchors[*].anchor_items[*].ordinal`
  - `answer_anchor_memory.anchors[*].anchor_items[*].display_text`
  - `forward_intent_memory.intents[*].intent_type`
  - `forward_intent_memory.intents[*].status`
  - `forward_intent_memory.intents[*].text`
  - `trace_memory.reference_continuity_items[*].reason`
  - `trace_memory.reference_continuity_items[*].text`
- Lifecycle-only fields may differ and must not be used as equivalence basis: `attempt_id`、`execution_id`、trigger envelope、operation id、event id、event sequence、occurred_at、artifact payload ref。
- Tests should compare normalized semantic tuples, not raw EventLog rows.
- Fallback dispatch does not submit `CONTEXT_COMPACTED` and must not alter these five memory sections.

## 12. Implementation Slices

Slice 1：thin helper contracts and `compaction_evidence.py` cleanup。

- Add `dayu/host/compact_pipeline.py` with only contracts / functions listed in §5.
- Add focused `tests/host/test_compact_pipeline.py`.
- Migrate or delete `compaction_evidence.py` tests per §10.
- Do not wire dispatch / engine ingest yet except helper imports if needed for tests.
- Stop condition: helper tests pass, evidence module references removed, no public/schema/EventLog changes.

Slice 2a：wire proactive dispatch。

- Replace `dispatch.py` normal request construction with `build_normal_compact_request_plan(...)`.
- Replace proactive tier 1-3 recovery request construction with `build_tier_recovery_request_plans(...)`.
- Replace proactive fallback selection/payload-input construction with `build_fallback_decision_input(...)`.
- Keep EventLog append, artifact write, fail-unstarted and dispatch start in `dispatch.py`.

Slice 2b：wire reactive ingest。

- Replace `_reactive_compaction_request(...)` with `build_normal_compact_request_plan(...)`.
- Replace `_reactive_compaction_pass_queue(...)` with `build_reactive_pass_queue_plan(...)`.
- Replace `_reactive_fallback_decision(...)` selection/payload-input with `build_fallback_decision_input(...)`.
- Keep `CONTEXT_COMPACTION_REQUESTED` append, Attempt closeout, `RUN_RECOVERING`, commit guard, EventLog append and recovery Attempt creation in `engine_ingest.py`.

Slice 2c：wire RunInput protected raw tail。

- Replace RunInput-only protected raw-tail selection with the pipeline-owned audited second-read provider/hook.
- Ordinary branch consumes `CompactPipelineOrdinaryRawTailHandoff`.
- Fallback branch remains separate and continues `_fallback_context_messages(...)`.

## 13. Test Plan

Required tests:

1. Normal compact request helper:
   - Proactive and reactive source snapshots with the same material produce equivalent selected semantic material when attempt/execution fields are ignored.
   - current input anchor is protected and not selected as older material.

2. Tier 1/2/3 recovery helper:
   - tier 1 uses fallback selected recent caps.
   - tier 2 uses degraded previous compacted view with whole-section drop.
   - tier 3 uses empty previous view.
   - no helper calls compactor or writes EventLog.

3. Reactive multi-pass helper:
   - multiple selected blocks produce pass requests with one block per pass.
   - same source snapshot / current input anchor / operation material digest is preserved.

4. Fallback decision input:
   - proactive and reactive callers get identical selection / window / digest / budget payload for same source snapshot and policies.
   - action hint is `dispatch` when current recent-window/floor fallback hard budget passes, `fail_closed` when it does not.
   - no tier 5 or `fallback_tier` assertion.

5. Caller-side commit guard:
   - proactive stale input cursor / stale Run state cannot append accepted compact.
   - reactive execution mismatch / cursor mismatch / stale recovery proposal cannot append accepted compact.
   - tests live in dispatch / engine_ingest files because lifecycle guard remains caller-owned.

6. Cancellation:
   - proactive still uses durable Run observation token path.
   - reactive still passes Engine envelope cancellation token to `run_compaction_operation(...)`.
   - helper functions do not observe or swallow cancellation.

7. Accepted compact payload input:
   - proactive / reactive use `build_compacted_payload_input(...)` and produce equivalent semantic payload fields.
   - caller-specific lifecycle fields are excluded from semantic equivalence assertions.

8. Five Session Semantic Memory kinds:
   - accepted compact projects equivalent semantic fields per §11.
   - fallback dispatch does not produce compact memory.

9. WU-CM-14 protected recent raw tail:
   - ordinary post-compaction proactive and reactive RunInput include protected recent user, assistant final answer and accepted readable evidence.
   - selection helper owns protected group decision.
   - second-read provider validates current-run compact event/input cursor/source boundary/material digest.
   - current input appears exactly once and remains final user message.

10. LLM-facing boundary:
    - ordinary / compact / fallback messages do not expose `tool_call_id`、裸 event id、payload ref、digest、cursor、attempt id、execution id、fallback diagnostic refs、Host governance state or Engine state.

11. `compaction_evidence.py` cleanup:
    - mapping in §10 is completed.
    - `rg` verifies no module/function references.

12. Smoke hard gate:
    - `utils/smoke_host_public_conversation_memory_scenarios.py` must truly succeed.
    - This smoke verifies public Host conversation memory behavior does not regress; helper convergence itself is verified by focused unit/integration tests above.
    - Do not modify the smoke, lower coverage, bypass scenarios, relax assertions or use test doubles to cheat.

## 14. README Trigger Judgment

Plan gate only edits `docs/host/host-issues/wu-cm-13-unified-compact-pipeline-plan.md`; no README update.

Future implementation touches `dayu/host/` and `tests/`, so it must first read:

- `dayu/host/README.md` Agent update constraints.
- `tests/README.md` Agent update constraints.

Expected implementation likely changes internal Host behavior and tests but not user-facing CLI / Web / WeChat workflow, install steps, public commands, public schema, or root README scope.

## 15. Validation Commands

Plan gate validation:

```bash
git diff --check -- docs/host/host-issues/wu-cm-13-unified-compact-pipeline-plan.md
git diff --check --no-index /dev/null docs/host/host-issues/wu-cm-13-unified-compact-pipeline-plan.md
```

Implementation validation:

```bash
source .venv/bin/activate
pytest tests/host/test_compact_pipeline.py tests/host/test_compact_material.py tests/host/test_compaction_operation.py tests/host/test_dispatch_scheduler.py tests/host/test_engine_ingest.py tests/host/test_run_input_builder.py tests/host/test_memory_projection.py -q
python -m pyright dayu/ tests/ utils/
utils/smoke_host_public_conversation_memory_scenarios.py
git diff --check
```

If `tests/host/test_context_fallback.py` exists or is added, include it in the focused pytest command.

## 16. Blocking Questions

No blocking question for plan fix gate.

Implementation must stop and ask the user if any of the following becomes necessary:

- Public API / `open_host(options)` / `SubmitFollowupRequest` changes.
- Durable schema migration.
- EventLog event type changes.
- New `CONTEXT_COMPACTED` / `CONTEXT_COMPACTION_FAILED` payload fields or changed payload semantics.
- Compact artifact schema or provider contract changes.
- EngineEvent / Engine provider contract changes.
- A plan to merge proactive and reactive outer lifecycle into one state machine.
- Implementing tier 5 current-input-only fallback in this WU.

Deferred future owner：design 中 tier 5 current-input-only fallback remains not implemented in current code and is out of WU-CM-13 scope. It requires a separate work unit to decide schema / payload diagnostics and tests.
