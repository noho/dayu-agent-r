# WU-CTX-02 + WU-CTX-03 compact failure / overflow implementation plan

## 1. Goal / Motivation / Success Signal

### Goal

补齐 Host Context Governance 在 compact failure、deterministic recent-window fallback 和连续 reactive overflow dispatch-loop 下的实现与测试闭环，使实现对齐 `docs/host/design.md` 第 1 节和第 25 节，以及 `docs/host/host-core-followup-implementation-control.md` 中 WU-CTX-02 / WU-CTX-03 的验收信号。

### Motivation

动机成立。Host 是 Session / Run / Attempt / EventLog / context governance 的治理真源，Engine 只执行单次 `AgentRunRequest`。当前代码已经有 bounded compaction repair、reactive identity 校验和 ingest-level reactive 上限，但仍存在设计真源已明确、代码未完全落地的缺口：

- 默认 `max_compaction_attempts_per_operation` 未对齐设计要求的 5。
- execution profile 默认值、Host fallback 默认值和 compactor scene 默认 model 不一致。
- compact failure 后没有 deterministic recent-window fallback。
- `CONTEXT_COMPACTION_FAILED` payload 缺少设计要求的 attempt count、retry / repair budget exhausted 和 fallback 诊断字段。
- 缺连续 reactive overflow 通过 scheduler / worker dispatch-loop 到上限 fail closed 的 E2E。

### Success Signal

- Host fallback 默认值与 packaged `execution_profiles.json` 的 `max_compaction_attempts_per_operation` 均为 5。
- `conversation_compaction` scene packaged default model 与默认 execution profile compactor model 一致，默认使用 flash-tier；高规格 compactor 只能由 profile 显式选择。
- `CONTEXT_COMPACTION_FAILED` payload / validator / tests 覆盖 operation id、attempt count、budget exhausted、fallback decision、fallback input window / digest、fallback budget result 与 fallback action。
- Proactive compact failure 可按 policy 走 deterministic recent-window fallback：预算通过则创建 Attempt，不写 `CONTEXT_COMPACTED`，不写 memory projection；预算失败则 fail closed，且 Run 不进入 `RECOVERING`。
- Reactive compact failure 可按 policy 走 deterministic recent-window fallback：旧 Attempt 已关闭，Run 保持 recovery 路径；预算通过则创建新的 recovery Attempt，不写 `CONTEXT_COMPACTED`，不写 memory projection；预算失败则 `RUN_FAILED`，不得 `RUN_LOST`。
- 连续 reactive overflow E2E 可观察 Attempt 数、`CONTEXT_COMPACTION_REQUESTED` / `CONTEXT_COMPACTED` / `CONTEXT_COMPACTION_FAILED` 事件数和最终 `RUN_FAILED`，且不依赖不可控 sleep 或 race。

## 2. Non-goals / Scope Boundary / Stop Conditions

### Non-goals

- 不引入 provider tokenizer adapter。
- 不把 overflow retry 放进 Engine。
- 不重写 memory projection、evidence-backed fact、compact candidate accept barrier 或 evidence anchor 语义。
- 不让 fallback 生成 episode summary、minimum preserve、pinned state patch、`evidence_backed_fact` 或 durable memory projection。
- 不做旧 schema、旧 profile、旧 payload 或旧 public interface 兼容逻辑。
- 不重做 recovery / positive orphan proof；`LOST` 仍只属于 Phase 11 recovery owner。
- 不重复扩大 ingest 层已覆盖的单点计数测试；WU-CTX-03 只补 dispatch-loop 组合路径。
- 不改变 scene inheritance semantics；当前 WU 只要求 `conversation_compaction` scene default model 与默认 execution profile compactor model 对齐，不新增“不得继承 conversation_compaction”的配置约束或防御性测试。

### Scope Boundary

当前 WU 只允许处理以下行为：

- 默认 attempt budget 与 compactor model 默认来源对齐。
- `CONTEXT_COMPACTION_FAILED` 诊断 payload 补足。
- deterministic recent-window fallback 的内部选择、预算重估、diagnostic 和一次性 dispatch 输入视图。
- proactive / reactive failure E2E。
- 连续 reactive overflow dispatch-loop E2E。
- 与上述代码变化直接相关的 tests、pyright 和 README sync。

### Stop Conditions

- 若实现需要新增或改变 `open_host(options)`、`SubmitFollowupRequest`、`ContextBudgetPolicy` public 字段、execution profile schema 字段或 Service-facing API，停止并交回 controller 更新设计真源。
- 若 fallback 需要写 `CONTEXT_COMPACTED`、写 memory table / projection、生成 stable facts 或把 refs 提升为 facts，停止。
- 若 reactive compact failure 会进入 `LOST`，或 proactive failure 会进入 `RECOVERING`，停止。
- 若连续 overflow E2E 只能依赖 sleep、时间竞态或不可控 worker timing 才能通过，停止并先补确定性测试同步点。
- 若为了保旧配置 / 旧 payload 需要兼容读取路径，停止；本 WU 按全新设计处理。

## 3. 直接证据摘要

### 动机成立的证据

- `docs/host/design.md` 第 1 节要求 Host 是 context governance 与 durable truth 真源，Engine 不拥有 Host 生命周期。
- `docs/host/design.md` 第 25 节要求 Context Governance 属于 Host，Engine 不做 Host-side compact retry；compact repair / retry 必须 bounded；budget 耗尽后只能写一个最终 `CONTEXT_COMPACTION_FAILED`。
- `docs/host/design.md` 第 25 节要求默认 `max_compaction_attempts_per_operation` packaged policy 为 5，且代码 fallback 默认值与 execution profile 默认值一致。
- `docs/host/design.md` 第 25 节要求 deterministic recent-window fallback 不是 compact 成功，不得写 `CONTEXT_COMPACTED`、不得写 memory projection、不得伪造 stable facts，且必须记录 fallback decision、fallback input window / digest 和预算重估结果。
- `docs/host/host-core-followup-implementation-control.md` WU-CTX-02 要求建立 compact failure 策略矩阵、补齐 proactive / reactive compact failure E2E、默认 retry budget 为 5、默认 compact model 使用 flash-tier、fallback 后重新估算预算。
- `docs/host/host-core-followup-implementation-control.md` WU-CTX-03 要求连续 overflow 不无限循环，并通过 dispatch-loop E2E 观察 Attempt 数、compact events 与最终 Run terminal。
- `docs/reviews/wu-ctx-02-03-discussion-code-inspection-20260601.md` 直接核对当前代码：`dayu/host/context_policy.py` 默认 attempt budget 为 2；`dayu/config/execution_profiles.json` packaged profiles 为 3；`conversation_compaction` scene model 为 high-spec；`dispatch.py` / `engine_ingest.py` compact failure 当前直接 fail closed；`context_events.py` failed payload 缺少设计要求字段；scheduler 只有单次 reactive recovery E2E。
- `docs/reviews/wu-ctx-02-03-discussion-controller-adjudication-20260601.md` 已裁决 DISC-01 到 DISC-05 为 accepted，并明确 provider tokenizer adapter、Engine overflow retry、memory projection redesign、旧 schema/profile 兼容均不纳入当前 WU。

### 已覆盖风险，不重复做

- Host-owned semantic repair bounded loop 已由 `dayu/host/compaction_operation.py` 和 `tests/host/test_compaction_operation.py` 覆盖。
- 首轮 proposal failure、quality rejection、hard-threshold-after-compact 可 repair 已有 operation 层测试。
- reactive compact 后不使用估算 hard threshold 阻断 recovery dispatch 已覆盖。
- reactive attempt / execution identity 校验已有 ingest 测试。
- reactive compact failure 不进入 `LOST` 已有 ingest 测试。
- reactive compact count limit 的 ingest-level fail closed 已有测试。
- reactive multi-pass 中间失败不提交 partial `CONTEXT_COMPACTED` 已有 operation 层测试。
- proactive compact failure 当前不创建 Attempt、不进 `RECOVERING` 已有测试；本 WU 只在 fallback 预算通过时允许创建 Attempt。

## 4. Affected Files / Modules

### Allowed production files for implementation phase

- `dayu/host/context_policy.py`
- `dayu/host/context_events.py`
- `dayu/host/context_fallback.py`，新增 Host 内部模块，仅承载 deterministic recent-window fallback 选择、digest、预算重估输入和 payload field 构造 helper。
- `dayu/host/run_input.py`
- `dayu/host/dispatch.py`
- `dayu/host/engine_ingest.py`
- `dayu/config/execution_profiles.json`
- `dayu/config/prompts/manifests/conversation_compaction.json`
- `dayu/service/host_assembly.py`，仅允许补配置一致性诊断 / test 支撑；不得改变 public request shape。

默认不允许修改 `dayu/host/durable/run_transition.py`、SQLite durable transition 结构或 `RUN_STARTED` required payload。reactive fallback 接线必须优先在 `dayu/host/engine_ingest.py`、`dayu/host/run_input.py` 与 fallback provider 内完成。若 implementation 发现不修改 durable transition 或 required payload 就无法实现，必须停止并交回 controller 裁决。

### Allowed test files

- `tests/host/test_context_policy.py`
- `tests/host/test_context_compact_events.py`
- `tests/host/test_dispatch_scheduler.py`
- `tests/host/test_engine_ingest_mapping.py`
- `tests/host/test_run_input_builder.py`
- `tests/runtime/test_config_loader.py`
- `tests/runtime/test_scene_assets_migration.py` 或新增同层配置一致性测试文件。
- `tests/service/test_host_assembly.py`

### Allowed docs after implementation

- `dayu/host/README.md`
- `dayu/config/README.md`
- `tests/README.md`

当前 plan gate 只允许写入本文件：`docs/host/wu-ctx-02-03-compact-failure-overflow-plan.md`。

## 5. Contract / Schema / State-machine / Public-interface Changes

### Public interface

不新增 Service-facing public API，不改变 `open_host(options)`、`SubmitFollowupRequest`、Host handle method、Engine `AgentRunRequest` 或 execution profile schema。fallback policy 第一版使用 Host 内部默认与现有 `MemoryProjectionPolicy.recent_raw_turns_floor` / material block 边界派生，不新增 public `ContextBudgetPolicy` 字段。

Blocking Questions For Controller: none。

若 implementation agent 发现必须新增 public policy 字段，例如 `allow_recent_window_fallback`、fallback window N/M 或 per-profile fallback mode，必须停止并交回 controller；不得通过 raw metadata、extra payload 或 config patch 绕过设计真源。

fallback “最新 N 轮”不是 public config，也不是可任意调整的内部魔法常量。N 是预算驱动选择算法的输出：在 hard budget 约束下，先固定必须保留的 anchor / stable / compact represented context / floor，再按确定性 reverse chronological material block 顺序尽可能追加最近 raw turn blocks，最终成功选中的 raw turn 数量即为本次 N。若必保留集合本身已超过 hard budget，则 fallback estimate 结果为 over-budget 并 fail closed，不通过降低 floor 偷偷 dispatch。

### EventLog payload contract

需要补齐设计已规定的 `CONTEXT_COMPACTION_FAILED` payload 字段。这是对既有设计真源的落地，不是新增架构决策。

目标字段：

- `operation_id: str`
- `failure_reason: str`
- `policy_decision: str`
- `retryable: bool`
- `attempt_count: int`
- `retry_repair_budget_exhausted: bool`
- `diagnostic_refs: list[str]`
- `budget_after_attempted_compact: int | null`
- `fallback_policy_decision: str | null`
- `fallback_input_window: object | null`
- `fallback_input_digest: str | null`
- `fallback_budget_result: object | null`
- `fallback_action: "dispatch" | "fail_closed" | "not_applicable"`

`fallback_input_window` 必须是结构化诊断，不是 raw prompt。建议包含 `selected_block_ids`、`dropped_block_ids`、`current_input_ref`、`source_refs`、`recent_raw_turns_floor`、`trigger_source`、`policy_ref`。不得包含 API key、headers、完整 provider payload 或无界 raw text。

### Durable schema

不改 SQLite 表结构，不做 migration，不做旧 payload 兼容读取。测试库按新代码起库。

### State-machine

- Proactive fallback 成功：`RUN_ACCEPTED|RUN_QUEUED -> CONTEXT_COMPACTION_REQUESTED -> CONTEXT_COMPACTION_FAILED(fallback_action=dispatch) -> RUN_STARTED(start_reason=initial|queue_promotion) -> ATTEMPT_STARTED -> dispatch`。不得进入 `RECOVERING`。
- Proactive fallback 失败：`... -> CONTEXT_COMPACTION_FAILED(fallback_action=fail_closed) -> RUN_FAILED`。不得创建 Attempt。
- Reactive fallback 成功：`RUNNING/Attempt RUNNING -> CONTEXT_COMPACTION_REQUESTED(trigger_source=reactive) -> ATTEMPT_FAILED -> RUN_RECOVERING -> CONTEXT_COMPACTION_FAILED(fallback_action=dispatch) -> RUN_STARTED(start_reason=recovery) -> ATTEMPT_STARTED -> dispatch`。不得写 `CONTEXT_COMPACTED`。
- Reactive fallback 失败：`... -> CONTEXT_COMPACTION_FAILED(fallback_action=fail_closed) -> RUN_FAILED`。不得 `RUN_LOST`。
- 连续 reactive overflow 达到 `max_reactive_compactions_per_run`：写最终 `CONTEXT_COMPACTION_FAILED(failure_reason=reactive_compact_limit_reached, fallback_action=fail_closed 或 not_applicable)`，Run `FAILED`，不再创建新 Attempt。

## 6. Implementation Decisions

- 默认 attempts 对齐为 5：`DEFAULT_MAX_COMPACTION_ATTEMPTS_PER_OPERATION` 改为 5；所有 packaged execution profiles 的 `context_budget_policy.max_compaction_attempts_per_operation` 改为 5；配置加载与 Service assembly 测试断言默认一致。
- Execution profiles 与 Host fallback 一致：`dayu/service/host_assembly.py` 保持从 execution profile 显式传入 policy；测试证明默认 profile、Host `default_context_budget_policy` 和 assembled `OpenHostOptions.context_budget_policy` 都是 5。
- Scene/profile compactor default model 对齐：`conversation_compaction` scene manifest 的 `model.default_model_id` 改为 `deepseek-v4-flash`，与 packaged execution profile `compactor_baseline.model_id` 一致；不改变其它普通 scene 的 high-spec default。
- `CONTEXT_COMPACTION_FAILED` payload 诊断补足：所有 append helper 都必须传 `operation_id`、`attempt_count`、`retry_repair_budget_exhausted`；没有外部 LLM attempt 的 precondition failure 使用 `attempt_count=0`、`retry_repair_budget_exhausted=false`；repair 耗尽使用实际 `len(rejected_attempts)` 或 operation result 的 attempt count，且 exhausted 为 true。
- Deterministic recent-window fallback：新增内部 helper 从 ordinary material blocks / frozen reactive material blocks 中确定性选择 fallback 输入窗口。选择必须先保留 current input anchor、required stable / compact represented context 和 `MemoryProjectionPolicy.recent_raw_turns_floor` 下限内的最近 raw turn blocks；随后按确定性 reverse chronological material block order 追加最近 raw turn blocks，直到下一 block 会超过 hard budget 或 material 耗尽。若必保留集合本身已超过 hard budget，则 fallback budget result 为 over-budget 并 fail closed。按 material block id 和 source refs 生成 digest；不得生成 compact artifact 或 stable facts。这里的“最新 N 轮”由预算驱动选择结果确定，不新增 public config，不定义任意 internal max 常量。
- Fallback budget re-estimate：Slice C 开始 fallback dispatch 实现前必须先核对现有 conservative estimator 能接受 fallback-selected `message_fragments` 子集。fallback selection 生成后必须调用现有 conservative estimator，使用 selected material block text 与 current input anchor 作为 `BudgetEstimateInput.message_fragments`。预算通过才 dispatch；预算仍超 hard threshold fail closed。若 estimator 不兼容 selected subset shape，只允许增加最小 typed adapter 以转换输入形状，不改变估算算法、不新增 provider tokenizer、不新增 public policy field。
- Proactive failure E2E：覆盖 compactor missing、repair exhausted、fallback dispatch、fallback over-budget fail closed，断言无 `CONTEXT_COMPACTED`、无 memory projection 物化、Run 状态正确。
- Reactive failure E2E：覆盖 compactor missing / repair exhausted 后 fallback dispatch、fallback over-budget fail closed，断言旧 Attempt 关闭、Run 不进入 `LOST`、fallback dispatch 使用新 Attempt / execution id。
- Continuous reactive overflow dispatch-loop E2E：使用确定性 fake worker factory，每次 worker 接收 dispatch 后同步 emit context overflow，直到 reactive 上限。测试通过 scheduler drain / explicit wait helper 观察状态，不使用不可控 sleep；断言 Attempt 数为初始 Attempt + 允许的 recovery attempts，不超过上限。

## 7. Small Implementation Slices

### Slice A: 默认 policy / config / model 对齐

- Objective: 对齐 default attempts 为 5，并让 compactor scene default model 与 execution profile 默认一致。
- Allowed files/modules: `dayu/host/context_policy.py`、`dayu/config/execution_profiles.json`、`dayu/config/prompts/manifests/conversation_compaction.json`、`tests/host/test_context_policy.py`、`tests/runtime/test_config_loader.py`、`tests/runtime/test_scene_assets_migration.py`、`tests/service/test_host_assembly.py`。
- Exact allowed changes: 只改默认常量、packaged profile 字段、conversation compaction scene model；新增/更新断言，不改变 schema。
- Functions/classes/types: `DEFAULT_MAX_COMPACTION_ATTEMPTS_PER_OPERATION`、`default_context_budget_policy`、ConfigLoader loaded `ExecutionProfile` view、`build_open_host_options` 的 existing mapping。
- Data flow: packaged config -> ConfigLoader typed view -> Service host assembly -> `default_context_budget_policy` -> Host options。
- State transition: 无。
- Error handling: 配置不一致测试 fail fast；不新增运行时兼容分支。
- Invariants: Host fallback 默认、execution profile 默认、assembled Host policy 默认全部为 5；default compactor model 为 flash-tier。
- Tests/validation: 更新 `tests/host/test_context_policy.py` 断言常量为 5；配置测试遍历 packaged profiles；Service assembly 测试断言 assembled policy 为 5；scene asset 测试断言 `conversation_compaction.model.default_model_id == compactor_baseline.model_id`。
- Non-goals: 不改普通 scene 默认模型；不新增 high-spec allow-list。
- Completion signal: 配置与 Host 默认一致性测试失败前、修改后通过。
- Stop condition: 若发现需要新增 config schema 字段表达 compactor default precedence，停止。

### Slice B: `CONTEXT_COMPACTION_FAILED` payload 诊断补足

- Objective: 落地设计要求的 failed payload 字段，为后续 fallback 与 overflow E2E 提供可观察诊断。
- Allowed files/modules: `dayu/host/context_events.py`、`dayu/host/dispatch.py`、`dayu/host/engine_ingest.py`、`tests/host/test_context_compact_events.py`、`tests/host/test_dispatch_scheduler.py`、`tests/host/test_engine_ingest_mapping.py`。
- Exact allowed changes: 扩展 builder / validator 参数和 required fields；更新 proactive / reactive failed append helper；更新现有测试 payload 断言。
- Functions/classes/types: `build_context_compaction_failed_payload`、`validate_context_compaction_failed_payload`、`_append_compaction_failed_event`、`_append_reactive_compaction_failed_event`。
- Data flow: compaction request event id -> operation id；operation result rejected attempts -> attempt count / exhausted；estimate digest -> diagnostic refs；fallback fields 初始为 `null` / `not_applicable`。
- State transition: 不改变状态机，只改变 diagnostic payload。
- Error handling: precondition / missing compactor failure 使用 `attempt_count=0`；operation failure 使用 rejected attempt count；stale result不得被标记为 retry budget exhausted，除非 operation result 已明确耗尽。
- Invariants: 每个 final failed payload 均可解释 operation、尝试次数、是否 budget exhausted；无 fallback 时 `fallback_action="not_applicable"`。
- Tests/validation: builder 单测覆盖无 fallback、fallback dispatch、fallback fail closed、非法负数/非法 action；现有 proactive/reactive failed 测试更新断言。
- Non-goals: 不加入 raw provider payload；不把 attempt rejected event 合并进 failed event。
- Completion signal: 所有 `CONTEXT_COMPACTION_FAILED` append 调用编译通过且 payload validator 单测覆盖新增字段。
- Stop condition: 若需要读取旧 failed payload 才能让现有路径通过，停止。

### Slice C: Proactive deterministic recent-window fallback

- Objective: proactive compact failure 后按内部 deterministic fallback policy 重建一次 bounded input view，预算通过才 dispatch。
- Allowed files/modules: `dayu/host/context_fallback.py`、`dayu/host/run_input.py`、`dayu/host/dispatch.py`、`tests/host/test_run_input_builder.py`、`tests/host/test_dispatch_scheduler.py`。
- Prerequisite check: 在接线 proactive dispatch 前，先用最小单元测试或现有 estimator 调用点验证 conservative estimator 能接受 fallback-selected `message_fragments` 子集；覆盖 normal、empty stable input、over-budget 三类 fallback estimate。若不兼容，只允许增加最小 typed adapter，不改估算算法、不新增 provider tokenizer、不新增 public policy field。
- Exact allowed changes: 新增内部 fallback selection / digest helper；selection algorithm 不接受 public N 配置、不定义任意 max-N 常量；它先固定 current input anchor、required stable / compact represented context 和 `recent_raw_turns_floor` 下限，再按确定性 reverse chronological material block order 追加最近 raw turn blocks，直到下一 block 会超过 hard budget 或 material 耗尽；给 `RunInputBuilder` 增加可选内部 `ContextFallbackProvider`，默认 no-op；dispatch proactive failure 时构造 fallback selection、重估预算、写 failed payload，再按结果 start 或 fail closed。
- Functions/classes/types: 新增 `RecentWindowFallbackSelection`、`RecentWindowFallbackBudgetResult`、`RecentWindowFallbackAction`、`build_recent_window_fallback_selection`、`estimate_recent_window_fallback_budget`、`EventLogContextFallbackProvider`；更新 `RunInputBuilder.build` 只在 provider 返回 active fallback 时替换 memory / compact / continuity messages 为 fallback bounded messages。
- Data flow: proactive material blocks -> fallback selection -> budget estimate -> `CONTEXT_COMPACTION_FAILED` payload -> `RUN_STARTED` / `ATTEMPT_STARTED` -> `RunInputBuilder` 读取 failed fallback view -> Engine request messages。
- State transition: fallback dispatch 仍是 proactive pre-dispatch governance；Run 从 accepted/queued 直接进入 running，不进入 recovering。
- Error handling: fallback selection 或预算估算失败写 failed payload并 fail closed；stale run 状态不启动 Attempt；fallback over-budget fail closed；若 current input anchor、required stable / compact represented context 和 floor raw turns 已超过 hard budget，不裁剪 floor dispatch，直接记录 over-budget。
- Invariants: fallback 不写 `CONTEXT_COMPACTED`；不写 compact artifact；不触发 memory catch-up 到 failed event；不改变 historical EventLog facts；selected block ids / digest 对相同 input cursor / material list 确定；selected raw turn 数量不少于 `recent_raw_turns_floor`，除非可用 material 本身不足；selection 不超过 hard budget 可容纳结果。
- Tests/validation: proactive compactor missing + fallback budget pass creates one Attempt and no compacted event；fallback budget fail keeps zero Attempt and Run failed；RunInputBuilder fallback test 断言只包含 selected recent window / current input，不包含 dropped older raw turn；fallback selection 单测断言同一 input cursor / material list 输出稳定、selected raw turn 数量不少于 floor、不会选择使 estimate 超过 hard budget 的下一 block；fallback estimate 单测覆盖 normal、empty stable input、over-budget；memory projection test 或 scheduler assertion 断言无 stable fact 物化。
- Non-goals: 不实现 provider tokenizer；不改变 ordinary build path。
- Completion signal: proactive failure E2E 覆盖 fallback dispatch 与 fail closed 两条路径。
- Stop condition: 如果 `RunInputBuilder` 需要 public request 参数才能知道 fallback view，停止。

### Slice D: Reactive fallback recovery path

- Objective: reactive compact failure 后按 deterministic fallback policy 决定创建新 recovery Attempt 或 fail closed。
- Allowed files/modules: `dayu/host/context_fallback.py`、`dayu/host/run_input.py`、`dayu/host/engine_ingest.py`、`tests/host/test_engine_ingest_mapping.py`、`tests/host/test_dispatch_scheduler.py`。默认不允许修改 `dayu/host/durable/run_transition.py`。
- Exact allowed changes: reactive failure 分支复用 frozen material blocks 构造 fallback selection；预算通过时写 `CONTEXT_COMPACTION_FAILED(fallback_action=dispatch)`，随后优先通过 `engine_ingest.py` 内部 recovery flow、`run_input.py` fallback provider 与现有 recovery start transition 创建新 Attempt；预算失败时写 failed 并 `_fail_recovering_run`。不得新增或修改 `RUN_STARTED` required payload，不得修改 durable table schema。
- Functions/classes/types: `_execute_reactive_compaction`、新增 `_complete_reactive_recovery_after_fallback` 优先于泛化 compact success 路径；fallback diagnostic ref 通过 failed payload 与 fallback provider 关联，不通过扩展 `RUN_STARTED` required payload 传递。
- Data flow: Engine overflow candidate -> frozen material blocks -> compaction request -> operation failure -> fallback selection -> failed payload -> recovery start -> scheduler wake dispatch -> RunInputBuilder fallback provider。
- State transition: old Attempt terminal by policy；Run `RECOVERING`；fallback dispatch creates new Attempt with new `attempt_id` / `execution_id`; no old Attempt resume。
- Error handling: missing compactor/artifact store、repair exhausted、stale result 分别保留 failure reason；fallback over-budget fail closed；reactive count limit failure不得启动 fallback dispatch，除非 implementation 明确证明 policy 允许且不突破上限，默认计划为 fail closed。
- Invariants: reactive compact failure 不进入 `LOST`；fallback 不写 `CONTEXT_COMPACTED`；fallback successful recovery does not call memory projection catch-up for compacted event；new Attempt count bounded by reactive limit。
- Tests/validation: reactive compactor missing + fallback budget pass creates second Attempt with new ids；reactive fallback over-budget writes `RUN_FAILED` and `RUN_LOST` count 0；failed payload contains fallback window / digest / budget result。
- Non-goals: 不改变 EngineEvent schema；不让 Engine 自己 retry。
- Completion signal: reactive failure E2E 能证明 fallback dispatch 与 fail closed 两条路径。
- Stop condition: 若 recovery transition 必须把 `context_compacted_event_id` 伪造成 non-null 才能启动，停止；若实现必须修改 `dayu/host/durable/run_transition.py`、SQLite durable transition、`RUN_STARTED` payload validator required field 集合或 public typed payload required 字段，停止并交回 controller。

### Slice E: Continuous reactive overflow dispatch-loop E2E and docs sync

- Objective: 补齐 WU-CTX-03 dispatch-loop E2E，并同步稳定 README。
- Allowed files/modules: `tests/host/test_dispatch_scheduler.py`、`dayu/host/README.md`、`dayu/config/README.md`、`tests/README.md`。
- Exact allowed changes: 新增确定性 fake worker factory，按 dispatch 次序 emit overflow；新增测试断言 compact request / compacted / failed / Attempt / terminal 数；README 只更新与当前代码一致的稳定说明。
- Functions/classes/types: 测试内新增 `_RepeatedOverflowWorkerFactory` 或复用现有 fake worker helper；不得新增生产测试 seam。
- Data flow: scheduler wake -> worker accepts attempt 1 -> EngineEvent overflow -> reactive compact -> recovery attempt -> worker overflow again -> limit reached -> final failed。
- State transition: attempts 不超过 `1 + max_reactive_compactions_per_run`；最后 `RUN_FAILED`；`RUN_LOST` 为 0。
- Error handling: 测试通过 explicit scheduler drain / active task wait helper 收敛；禁止裸 sleep 等待。
- Invariants: 连续 overflow 不无限循环；terminal diagnostic 说明 compact count / last failure reason / fail closed。
- Tests/validation: 新增 `test_reactive_repeated_overflow_dispatch_loop_fails_closed_at_limit`；运行 `pytest tests/host/test_dispatch_scheduler.py -q`。
- Non-goals: 不重复 ingest count unit test；不扩大为 stress / soak。
- Completion signal: E2E 在本地稳定通过，并且 README sync 决策完成。
- Stop condition: 若测试只能通过竞态时间等待观察状态，停止并先补确定性同步 helper。

## 8. Tests / Validation Commands

实施完成后必须先激活虚拟环境：

```bash
source .venv/bin/activate
```

受影响测试建议按 slice 递增运行：

```bash
pytest tests/host/test_context_policy.py tests/runtime/test_config_loader.py tests/runtime/test_scene_assets_migration.py tests/service/test_host_assembly.py -q
pytest tests/host/test_context_compact_events.py tests/host/test_run_input_builder.py -q
pytest tests/host/test_engine_ingest_mapping.py -q
pytest tests/host/test_dispatch_scheduler.py -q
```

最终验证：

```bash
python -m pyright dayu/ tests/ utils/
```

README/doc sync 决策：

- 本 plan gate 不改 README。
- implementation 完成并通过测试后，根据 AGENTS.md 触发规则检查并按需更新 `dayu/host/README.md`、`dayu/config/README.md`、`tests/README.md`。
- 若 README 当前已准确描述新增行为，则记录“检查后无需修改”；不得机械更新时间敏感记录。

## 9. Docs Decision

预计需要检查：

- `dayu/host/README.md`：实现触及 `dayu/host/` 且新增 deterministic recent-window fallback、failed payload 诊断、reactive dispatch-loop 收口说明。若 README 未描述 fallback 不是 compact 成功、不得 memory materialize、reactive fail closed 上限，则必须更新。
- `dayu/config/README.md`：实现触及 `dayu/config/` 且默认 attempts / compactor model 默认发生变化。若 README 示例或说明含默认 attempts、默认 compactor model 或 scene/profile 默认关系，必须更新。
- `tests/README.md`：实现触及 `tests/` 且新增 compact failure fallback / continuous overflow E2E 覆盖。若测试手册覆盖矩阵未包含这些路径，必须更新。

不更新：

- 根目录 `README.md`，除非 implementation 改变用户命令、配置入口或 CLI 使用方式。
- `dayu/README.md`，除非 implementation 改变分层关系或装配边界；本 plan 不允许。

## 10. Review Gates

Plan review 应重点检查：

- 是否误引入 public fallback policy contract。
- Slice 是否过粗，是否把 fallback、payload、配置和 E2E 混成不可 review 的大改。
- fallback 是否可能伪造 compact success、stable facts 或 memory projection。
- reactive / proactive 状态路径是否与设计真源一致。
- 连续 overflow E2E 是否确定性、可重复、无 sleep race。

Code review 应重点检查：

- `CONTEXT_COMPACTION_FAILED` payload 所有路径字段完整且不含敏感 raw payload。
- fallback selection 对同一 input cursor / material list deterministic。
- fallback budget re-estimate 使用现有 conservative estimator，不引入 provider tokenizer。
- proactive failure 不进入 `RECOVERING`；reactive failure 不进入 `LOST`。
- reactive fallback dispatch 创建新 Attempt / execution id，旧 Attempt 不 resume。
- 无旧 schema / 旧 profile 兼容逻辑。
- pyright 无新增错误，中文 docstring 完整，签名无 `Any` / `object`。

Aggregate deepreview 应重点检查：

- Context Governance ownership 未越界到 Engine / Service。
- EventLog payload schema 与 tests / README 一致。
- fallback 没有被 RunInputBuilder 当作 compact artifact 或 memory projection。
- continuous overflow 不存在无限 loop 或 flakiness。

## 11. Risks / Residual Risk Owner

| Risk | 状态 | Owner / Destination | 处理 |
|---|---|---|---|
| RR-CTX-PLAN-01 fallback policy public contract 边界 | resolved-by-plan | WU-CTX-02 implementation owner | 第一版使用 Host 内部默认和现有 memory policy 派生；若实现发现必须新增 public field，按 stop condition 交回 controller。 |
| RR-CTX-PLAN-02 post-compact estimator failure 独立路径 | covered-by-slices | WU-CTX-02 Slice C/D | Slice C 前置核对 conservative estimator 对 fallback-selected `message_fragments` 子集的兼容性；fallback 后强制重估；normal、empty stable input、over-budget 测试覆盖不 silent overflow。 |
| RR-CTX-PLAN-03 连续 overflow E2E 稳定性 | covered-by-slice | WU-CTX-03 Slice E | 使用确定性 fake worker / scheduler helper；禁止 sleep / race。 |
| fallback message rendering 可能遗漏必要上下文 | current WU risk | WU-CTX-02 implementation + code review | 通过 selected block ids、digest、budget result、RunInputBuilder 测试约束；fallback 是降级 dispatch，不承诺语义等价 compact。 |
| EventLog failed payload 字段增补影响现有 read model / outbox | current WU risk | WU-CTX-02 implementation + aggregate review | 只增结构化字段，不删除旧语义字段；不做旧 payload 兼容；受影响 projection 测试必须更新。 |
| README 与实现漂移 | current WU risk | implementation owner | 测试通过后按触发规则检查 README，只写稳定事实。 |

## 12. Completion Report Format

Implementation agent 完成每个 slice 后必须输出 durable artifact，并按以下格式报告：

```markdown
## WU-CTX-02 + WU-CTX-03 implementation report

- Gate:
- Slice:
- Approved plan:
- Allowed files/modules:
- Changed files:
- Implemented plan items:
- State-machine / payload changes:
- Tests:
- Pyright:
- Docs decision:
- Invariants checked:
- Residual risks:
- Stop status:
- Artifact path:
```

最终 closeout 给 controller 的摘要必须包含：

- 改了什么。
- 验证了什么。
- README 是否检查 / 更新。
- 是否存在 Blocking Questions For Controller。
- residual risks 及 owner。
- 建议下一 gate 入口。

## 13. Handoff Readiness

Blocking Questions For Controller: none。

建议 implementation slices 数：5。

本 plan 是 handoff-ready / code-generation-ready，前提是 implementation agent 严格按 slice 执行，不扩大到 public contract、Engine retry、provider tokenizer、memory projection redesign 或旧兼容路径。
