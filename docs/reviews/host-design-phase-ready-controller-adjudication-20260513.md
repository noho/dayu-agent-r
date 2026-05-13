# Host Design Phase-Ready Review Controller Adjudication

## 元信息

- 日期：2026-05-13
- 范围：裁决三份 phase-ready design review artifact
- 输入：
  - `docs/reviews/host-design-review-mimo-phase-ready-20260513.md`
  - `docs/reviews/host-design-review-ds-phase-ready-20260513.md`
  - `docs/reviews/host-design-review-codex-phase-ready-20260513.md`
- 设计真源：
  - `docs/host/design.md`
  - `dayu/README.md`
- 输出定位：进入下一阶段 phase design / phase plan 前的 controller 裁决与写回依据

## 总体裁决

三份 review 对主架构方向没有提出推翻性 finding。Host 作为治理真源、Engine 只执行单次 request、Remote 不拥有 Host 状态、EventLog canonical facts 驱动恢复、Projection / Sink / Outbox / Memory 不反向成为真源，这些主体设计成立。

Controller verdict：

- 不需要重新讨论整体架构。
- 可以进入下一阶段 phase design 的准备状态。
- 但在把 `docs/host/design.md` 和 `dayu/README.md` 作为 phase plan 唯一真源前，应先做一次小范围 design cleanup pass。
- cleanup pass 只补语义合同、状态边界和术语一致性，不展开 SQL schema、wire protocol、具体 dataclass 或测试矩阵。

## 裁决分级

- **P0 / 写回前置**：必须先写回 `design.md` 或 `dayu/README.md`，否则 phase design / phase plan 容易出现错误分叉。
- **P1 / phase design 前置**：不阻塞总体推进，但对应 phase 进入 implementation-ready plan 前必须细化。
- **P2 / phase-local**：属于对应 phase 的正常细化内容，不需要污染架构级 design。
- **Rejected / 已覆盖**：review concern 不成立，或现有设计已覆盖。

## P0 写回前置

### A1. README 与 design 的 Attempt `STARTING` 术语对齐

- 来源：DS-001，Codex F-005
- 裁决：接受，P0。
- 写回目标：`dayu/README.md`
- 写回口径：`STARTING` 是正式 Attempt status，表示 Host 已 durable 创建 Attempt / dispatch intent，但 worker 尚未 accepted。`ATTEMPT_STARTED` 与 `ATTEMPT_RUNNING` 不能合并。

### A2. `host_instance_id` 语义

- 来源：DS-002
- 裁决：接受，P0。
- 写回目标：`docs/host/design.md`
- 写回口径：`host_instance_id` 是 Host 每次启动生成的 instance id，只用于判断 dispatch record 是否仍可由当前 Host 进程确认控制。它不是 lease、fencing token 或远端 ownership。不能单靠相同 id 接管旧 Attempt；无法确认控制时旧 Attempt 仍进入 `LOST`。

### A3. `steer` 必须有目标 Run 前置条件

- 来源：Codex F-001，DS-003
- 裁决：接受，P0。
- 写回目标：`docs/host/design.md`
- 写回口径：`submit_followup(behavior=steer)` 必须携带 `target_run_id` 或等价 expected active Run precondition。Host 只允许 steer 命中“当前 active 且 steerable”的目标 Run。`RUNNING` 与 `WAITING` 是 steerable；`CANCELLING`、`RECOVERING` 与所有 terminal 状态不是 steerable。
- 前置失败语义：
  - `target_run_id` 不是当前 Session 的 active Run，说明 active Run 已切换或目标已退出 active slot，返回 `conflict`。
  - `target_run_id` 是当前 active Run 但状态不是 steerable，返回 `invalid_state`。
  - `target_run_id` 已 terminal，返回 `invalid_state` 或等价 terminal conflict。
  - Host 不能隐式 steer 当前 Session 的另一个 Run。
- 调用者语义：Host 不替调用者猜测降级行为。前置条件失败时，调用者应按 UI / Service policy 决定下一步：
  - 用户原意只是继续追问：改调用 `submit_followup(behavior=queue)` 或 `start_run`，创建新 Run。
  - 用户明确要修正已 terminal 的回答：调用 `replay_run(source_run_id, repair_instruction)`。
  - 用户想取消后续执行：调用 `cancel_run`；但 terminal Run 不能被取消。
  - 当前已有新的 active Run，且用户确认要干预新的 active Run：用新的 `target_run_id` 重新发 steer。
- 错误返回建议：`conflict` / `invalid_state` 应携带当前 active Run / target Run 状态摘要，便于调用者决定 queue、start_run、replay 或重新 steer。自动降级若存在，应发生在 UI / Service policy 层，并对用户可见。

### A4. `WAITING` Run 的 steer 行为

- 来源：DS-003
- 裁决：接受问题，但不采纳“直接拒绝”作为唯一语义。
- 写回目标：`docs/host/design.md`
- 写回口径：`WAITING` Run 可以被 steer，但语义不是停止 running Attempt。Host 应 append `STEER_REQUESTED`，取消 / abandon active wait record，迟到 wait result 只能进入 diagnostic / tool trace，然后为同一 Run 创建新 Attempt。旧 Attempt 保持 `SUSPENDED`，不重写历史。
- 理由：`WAITING` 仍占 Session active slot。生产级交互中，用户应能在等待外部 job 时改变当前 Run 方向；否则只能 cancel 整个 Run，交互语义过重。

### A5. `resolve_wait` 非 `waiting` 状态与幂等语义

- 来源：DS-004，DS-005
- 裁决：接受，P0。
- 写回目标：`docs/host/design.md`
- 写回口径：
  - 幂等 scope 是 `(wait_id, idempotency_key)`。
  - 同一 key + 同一 outcome 重试返回已接受结果。
  - 同一 key + 不同 outcome 返回 `idempotency_conflict`。
  - wait record 已 `cancelled` / `lost` 时，迟到 resolution 不得进入 EventLog `canonical_fact`，返回 `invalid_state` / `conflict` 并记录 diagnostic。
  - 已 `resolved` 的 wait record 只允许幂等重放，不允许第二次 resolution。

### A6. `RECOVERING` 退出路径补全

- 来源：DS-007，DS-011，DS-022
- 裁决：接受，P0。
- 写回目标：`docs/host/design.md`
- 写回口径：
  - `RECOVERING -> RUNNING`：成功创建新 Attempt。
  - `RECOVERING -> FAILED`：恢复 Attempt 已确认 non-recoverable failure。
  - `RECOVERING -> LOST`：必要 facts 缺失、超出 recovery policy、或 Host 无法确认治理状态。
  - `RECOVERING -> CANCELLED`：用户取消且没有新的 terminal fact。
  - `CANCELLING -> RECOVERING / LOST` 复用同一事实完整性和 policy 判定。

### A7. Dispatch startup 失败路径

- 来源：DS-010
- 裁决：接受，P0。
- 写回目标：`docs/host/design.md`
- 写回口径：`STARTING` Attempt 被 worker reject、startup timeout 或 dispatch failure 收口为明确 Attempt terminal fact。Run 按 Host policy 进入 `FAILED`、`RECOVERING` 或 `LOST`，不得把“dispatch intent 已提交”和“worker 已开始执行”混成一个状态。

### A8. Event contract 中 run scope 必填性

- 来源：DS-008，DS-018
- 裁决：接受，P0。
- 写回目标：`docs/host/design.md`
- 写回口径：
  - `STEER_REQUESTED` 的 `run_id` required。
  - `FOLLOWUP_QUEUED` 应绑定到明确 queued / created Run，`run_id` required。
  - `RETRY_REQUESTED` / `REPLAY_REQUESTED` 的 `run_id` 指源 Run；新 Run 通过后续 `RUN_ACCEPTED` 的 `source_run_id` / `source_run_relation` 建立关系。

### A9. Outbox delivery target 冻结

- 来源：Mimo F-09，DS-016，DS C-006，Codex F-003
- 裁决：接受，P0。
- 写回目标：`docs/host/design.md`
- 写回口径：
  - delivery target 必须是 typed stable target，不得从 metadata 猜。
  - target 解析优先级应写明：explicit request / HostCallContext typed field 优先，其次 Session binding default。
  - resolved delivery target 必须由 Host 在 Run acceptance command transaction 中冻结；可以写入 `RUN_ACCEPTED` canonical payload，或写入与 `RUN_ACCEPTED` 同事务更新的 Run durable state。
  - resume / wait resolution 不重新解析 target；terminal outbox intent 使用 Run 已冻结 target。
  - 没有 target 时，OutboxSink 不创建 delivery record，但 Run terminal 不受影响。
- Run acceptance 路径：
  ```text
  start_run / submit_followup accepted
    -> Host resolves delivery target from explicit request / HostCallContext / Session binding
    -> append USER_INPUT_ACCEPTED
    -> append RUN_ACCEPTED(payload includes delivery_target_ref or delivery_context_ref)
    -> optionally update Run durable row with resolved delivery target in the same transaction
    -> commit
  ```
- Terminal / OutboxSink 路径：
  ```text
  RUN_SUCCEEDED / RUN_FAILED / RUN_CANCELLED terminal fact committed
    -> OutboxSink scans committed terminal facts by event_sequence checkpoint
    -> OutboxSink reads terminal fact + frozen delivery target from RUN_ACCEPTED / Run durable state
    -> OutboxSink upserts outbox delivery record / work queue
    -> OutboxSink advances its projection checkpoint
  ```
- 边界约束：OutboxSink 只能读取 EventLog / Run durable state 并写 outbox projection / work queue；它不能 append、update 或补写 EventLog，不能改 Run / Attempt 状态。

### A10. Memory snapshot freshness barrier

- 来源：Mimo F-03，Codex F-006
- 裁决：接受，P0。
- 写回目标：`docs/host/design.md`
- 写回口径：memory snapshot 是 durable projection / read model。RunInputBuilder 可以消费它，但必须校验 snapshot cursor 覆盖当前构造所需的 EventLog cursor；若 stale / missing，必须从 EventLog canonical facts 重建所需 stable layer，或进入结构化 context governance / recovery path。projection lag 不能改变同一 EventLog + policy 下的 messages。

### A11. Replay 的 dirty final answer 隔离

- 来源：Codex F-004，DS-012
- 裁决：接受，P0。
- 写回目标：`docs/host/design.md`
- 写回口径：`replay(run)` 的源 Run 必须是已 terminal Run；“output dirty”是 replay reason，不是 Run 状态。
- 适用范围：replay 只用于 final answer 的格式 / schema / 结构脏数据修复，例如 JSON schema invalid、字段缺失、输出 envelope 不合规、引用格式错误、输出 policy 的结构性失败。replay 的目标是在不重复昂贵工具调用的前提下，基于已接受工具事实重新生成合规输出。
- 非适用范围：事实内容脏、幻觉、业务归因错误、证据不足或证据冲突不是 replay 场景。此类问题不能靠无工具“默默再生成”修复，应进入新分析 / follow-up / retry / evidence retrieval / 补工具事实路径，由 Host 明确创建新的用户可见目标或受控补证据流程。
- RunInputBuilder 规则：replay 的源 final answer 不得作为普通 assistant conclusion 注入 messages。对于格式 / schema / 结构修复，可以把源 final answer 作为 `rejected_candidate` / repair context 注入，并同时提供 validation errors / repair instruction；模型必须被约束为只修复输出结构、不新增事实、不调用工具。accepted tool facts / evidence anchors 可复用。

### A12. Remote ToolRuntime accept barrier 语义

- 来源：Mimo F-01，Mimo F-04，DS C-001，DS C-002
- 裁决：接受，P0 语义写回；wire protocol 仍留到 Remote phase。
- 写回目标：`docs/host/design.md`
- 写回口径：
  - LocalProxy 下 accept barrier 是函数调用语义。
  - RemoteProxy 下 accept barrier 是同等语义的 request / ack contract。
  - ToolRuntime 提交 tool fact candidate 后，Engine 不能消费对应 tool result，直到 Host durable accepted ack 返回。
  - ack rejected / timeout 时，ToolRuntime 不得把结果交给 Engine；应返回 governed tool error、suspend、或让 Attempt 按 Host policy failed / recoverable。
  - RemoteProxy 只承载 accept contract 的传输，不拥有治理状态；不需要在架构级定义 wire frame。

### A13. Policy snapshot ownership

- 来源：Mimo F-C3，Codex F-007，DS C-005，SMELL-HOST-007
- 裁决：接受，P0。
- 写回目标：`docs/host/design.md`
- 写回口径：HostPolicyProviderSet 只存在于 composition root / acceptance command path。Attempt snapshot 不传整个 provider set；只传执行所需的 immutable typed policy subset / policy snapshot refs。ToolRuntime、RunInputBuilder、OutboxSink、Context Governance、Sink 不得回查 HostPolicyProviderSet 全量对象，只能接收自己的 typed policy view / refs。
- 设计细化：
  ```text
  HostPolicyProviderSet at composition root
    -> command path resolves policy decisions / snapshots at acceptance or dispatch boundary
    -> each subsystem receives only its typed policy view or immutable policy snapshot refs
    -> subsystem executes with that view/ref
    -> audit / trace records policy decision id/ref needed to explain behavior
  ```
- typed policy view 示例：
  - `AdmissionPolicyView`：只给 admission / queue promotion 使用。
  - `WorkerSelectionPolicyView`：只给 Attempt dispatch 使用。
  - `ToolGovernancePolicyView`：只给 ToolRuntime / ToolPolicyEvaluator 使用。
  - `ContextBudgetPolicyView`：只给 Context Governance / RunInputBuilder budget coordination 使用。
  - `OutboxPolicyView`：只给 Outbox projection / dispatcher 使用。
- 禁止边界：不得把 `HostPolicyProviderSet` 当 service locator 传进 ToolRuntime、RunInputBuilder、Sink、OutboxSink 或 RemoteStub；不得让子系统运行中按字符串 key 自行拉取 unrelated policy。
- 理由：policy 是治理语义的一部分，需要可审计、可重放、可解释。子系统拿全量 provider set 会把 policy ownership 扩散成隐式依赖，后续 phase 无法判断“当时使用的是哪版 policy”。

### A14. Host command handle 与 background supervisor facet 分离

- 来源：SMELL-HOST-001，Codex F-009
- 裁决：接受，P0。
- 写回目标：`docs/host/design.md`
- 写回口径：Host composition root 可以拥有 command path 与 background runtime 两类能力，但公共 mutating API 接收的 Host command handle 不得暴露 Sink runner / Outbox dispatcher / projection supervisor 的直接能力。command handle 只持有 transaction runner、EventLog appender / reader、state services、RunInputBuilder / ToolRuntime / WorkerProxy factories、policy views、clock / id generator 和 after-commit wakeup port。Observer / Sink runner、Outbox dispatcher、projection workers 属于 background supervisor facet。
- 概念定义：
  - command path：处理 Service / UI / adapter 发来的同步治理命令，例如 `start_run`、`submit_followup`、`cancel_run`、`resolve_wait`、`retry_run`、`replay_run`。它负责校验 request / context、开启事务、append EventLog canonical facts、更新 Session / Run / Attempt / wait record 等治理状态、commit、发 after-commit wakeup。它是写 Host 真源的链路。
  - background runtime：提交后的后台追平、派生和投递能力，例如 Observer / Sink runner、audit / usage / tool trace / memory projection、outbox dispatcher、stream fanout、wait poller。它读取 committed EventLog，按 `event_sequence` checkpoint 追平，生成 projection / delivery work queue / diagnostic artifacts。它是读 Host 真源并生成派生视图或外部投递的链路。
- 禁止边界：
  - command path 不能直接跑 projection、不能直接投递 outbox、不能直接调用 sink worker、不能等待 slow sink 完成。
  - background runtime 不能 append EventLog canonical facts、不能更新 Run / Attempt 治理状态、不能决定 command transaction 是否成功。
  - `start_run` / `cancel_run` / `resolve_wait` 等公共操作最多通过 after-commit wakeup port 通知后台追平，不直接持有后台 worker 能力。
- 路径约束：
  ```text
  Host mutating command
    -> durable transaction
    -> append EventLog / update state indexes
    -> commit
    -> after-commit wakeup port signals background supervisor
    -> supervisor runs Sink / Outbox / projection catch-up by event_sequence checkpoint
  ```
- 理由：这不是单纯实现风格问题。如果 public command handle 直接持有 dispatcher / sink runner，implementation agent 很容易把 terminal transaction 与 projection / delivery 强耦合，破坏 EventLog 真源和 Sink lag 不影响 command path 的原则。

## P1 phase design 前置

### B1. HostCallContext typed schema

- 来源：Mimo F-02
- 裁决：接受，P1。
- 要求：API phase design 必须定义 required / optional 字段、actor/source 类型、anonymous / system actor 规则、authorization claims envelope、request id 与 client_request_id 的关系。

### B2. Snapshot 类型语义

- 来源：Mimo F-07，DS-014
- 裁决：接受，P1。
- 要求：API phase design 明确 snapshot 是只读值对象，定义嵌套 / ref 粒度、cursor 字段、terminal summary 边界。架构级 design 不需要完整字段表。

### B3. Truncation descriptor lifecycle

- 来源：Mimo F-05
- 裁决：接受，P1。
- 要求：Truncation phase design 必须把 descriptor lifecycle 写成可执行语义路径，避免 implementation agent 把 cursor 只存在远端内存。
- 指导语义：
  ```text
  tool result is truncated by TruncationManager
    -> generate cursor / scope_token / descriptor metadata
    -> submit descriptor with tool fact candidate
    -> Host validates and durably accepts descriptor with TOOL_RESULT_ACCEPTED / TOOL_TERMINAL_RESULT
    -> only accepted cursor / scope_token may be exposed in model-visible tool result
    -> fetch_more validates cursor + scope_token against Host-governed descriptor
    -> return next chunk or ordinary tool error
    -> descriptor expires / is revoked / is cleaned up by policy
  ```
- 真源约束：远端 ToolRuntime 可以持有 attempt-local cache 或 short-lived cursor acceleration，但这只是性能优化。Host durable descriptor / artifact ref / digest / scope binding 才是 recovery、resume、steer、replay 后 `fetch_more` 的真源。
- Phase design 必须明确：descriptor 创建时机、Host accept 时持久化、TTL / retention、Run / Attempt / tool result 绑定关系、`fetch_more` 后 cursor 递进或复用策略、scope_token 是否一次性或可重复、artifact digest mismatch / expired / revoked 时返回普通工具错误。

### B4. Duplicate governance reuse 的 model-visible response

- 来源：Codex F-002
- 裁决：接受，P1。
- 要求：ToolRuntime phase design 必须定义 `reuse` 的 canonical 表达。推荐：`TOOL_CALL_GOVERNED(action=reuse)` 记录 current `tool_call_id`、prior result refs、digest / evidence anchors、model-facing reused response ref / digest；不伪造新的 evidence fact，但保证恢复时可重建模型看到的 tool response。

### B5. Duplicate index 在 steer / resume 新 Attempt 中的种子

- 来源：DS-009
- 裁决：接受，P1。
- 要求：ToolRuntime phase design 明确 duplicate index 是 run-local execution optimization，不是 durable ledger。新 Attempt 可从当前 Run 已接受工具事实 / duplicate keys 的 attempt snapshot 重新 seed；Host crash 后也不需要单独恢复内存索引。

### B6. Context Governance proactive budget threshold 与 compact 关联

- 来源：DS-013，DS-015
- 裁决：接受，P1。
- 子系统归属：这是 Host Context Governance，不是 Conversation Memory 子系统。Memory 提供 stable layer / history pool / summaries 等素材；Context Governance 决定 provider-aware budget、compact 触发、compact artifact、RunInputBuilder 重建和新 Attempt 创建。
- 要求：Context Governance phase design 明确 proactive threshold compaction 与 provider overflow reactive fallback 两条路径。
- Proactive 路径：
  ```text
  Host ingests usage_reported / iteration_completed / accepted tool result / memory update boundary
    -> Host estimates next AgentRunRequest.messages budget with provider-aware policy
    -> below soft threshold: continue
    -> above threshold: append CONTEXT_COMPACTION_REQUESTED(trigger=proactive_threshold)
    -> close or pause current continuation boundary by Host policy
    -> Run -> RECOVERING when compact is needed before next LLM call
    -> compact inputs / memory / evidence summaries
    -> append CONTEXT_COMPACTED or CONTEXT_COMPACTION_FAILED
    -> RunInputBuilder rebuilds messages
    -> create new Attempt with new execution_id
  ```
- Reactive fallback：Engine 识别 provider `context_length_exceeded` 后 emit `context_compaction_requested`，Host 校验 `attempt_id + execution_id` 后走同一 Context Governance pipeline。该路径是最后防线，不是生产级主要触发策略。
- 要求：Context Governance phase design 明确 compact failed 后 `RECOVERING` / `FAILED` 分支、retry 上限、proactive compact 与后续 Attempt 的 `context_snapshot_ref` / compact version 关联。
- 边界：Engine 只上报 `usage_reported`、`iteration_completed` 和 provider overflow fallback；阈值比例、token estimator、哪些事实可压缩、如何重建 messages、是否 retry 都由 Host policy 决定。百分比不在架构级写死，可由 provider-aware policy 配置，例如 soft / hard threshold。

### B7. RunInputBuilder 聚合输入 Provider Protocol

- 来源：Mimo F-C2，DS C-003，Codex F-008，SMELL-HOST-002
- 裁决：接受，P1。
- 要求：RunInputBuilder phase design 不应直接依赖 memory / compact / EventLog row / tool registry / policy config 的内部结构。RunInputBuilder 应聚合一组 typed input Provider Protocol，并主动调用它们生成 message-ready blocks；这不是 callback / event listener 机制。
- Provider Protocol 示例：canonical fact projector、memory block provider、compact artifact provider、tool schema snapshot provider、scene message provider。
- 边界：Provider Protocol 对 RunInputBuilder 暴露稳定 message-ready 输出和解释 refs；memory snapshot、compact artifact、EventLog schema、tool registry、policy source 的内部结构由各自 provider 屏蔽。RunInputBuilder 只负责排序、预算协调和最终 `AgentRunRequest.messages` 装配。RunInputBuilder 可以 emit diagnostic / projection_signal，但不得依赖 tool trace projection。

### B8. EventLog consumer contract

- 来源：DS C-004，Mimo F-C6，SMELL-HOST-003
- 裁决：接受，P1。
- 要求：EventLog phase design 定义 per-consumer typed contract，而不只是全局 event matrix。至少包括 StateTransitionConsumer、RunInputFactProjector、MemoryProjectionInput、OutboxIntentProjector、AuditEventProjector、ToolTraceProjector、HostEventStreamProjector。每个 contract 必须声明 allowed event_class、allowed event_type、typed payload view、must-ignore 列表和 cursor / checkpoint 语义。
- 设计细化：全局 EventLog matrix 定义“事实是什么”；per-consumer contract 定义“某个消费者允许看什么、必须忽略什么、输出什么”。实施 Agent 不应让每个 consumer 直接遍历全量 event matrix 并自行判断。
- contract 示例：
  ```text
  RunInputFactProjector
    allowed: USER_INPUT_ACCEPTED, TOOL_RESULT_ACCEPTED, TOOL_TERMINAL_RESULT,
             GUIDANCE_INSERTED, selected assistant conclusion events
    must-ignore: preview, diagnostic, usage-only, projection checkpoint
    output: message-ready fact blocks + source event refs

  OutboxIntentProjector
    allowed: RUN_SUCCEEDED terminal facts + frozen delivery target refs
    must-ignore: preview, non-terminal run state, usage/tool trace events
    output: outbox delivery intent + idempotency key

  MemoryProjectionInput
    allowed: user turns, tool-verified facts, assumptions/open questions events
    must-ignore: assistant final answer as verified fact, preview/reasoning deltas
    output: memory patch input / snapshot update intent
  ```
- 禁止边界：consumer 不得把 `event_class=preview`、`diagnostic` 或 unrelated canonical event 当成自己的输入；新增 event_type 时必须明确影响哪些 consumer contract，而不是默认所有 consumer 都可读。

### B9. Host handle facets

- 来源：Codex F-009，SMELL-HOST-001
- 裁决：并入 A14，P0 写回。
- 要求：phase design 应以 A14 为约束，不再把 background runner / dispatcher 放入 public command handle。

### B10. ToolRuntime internal slicing

- 来源：Mimo F-C5，SMELL-HOST-004
- 裁决：接受，P1。
- 要求：ToolRuntime phase design 先拆 internal ports，再实现 `ToolExecutor` 编排层。建议 port：ToolRegistryView、ToolDispatchPort、ToolPolicyEvaluator、DuplicateGovernance、TruncationService、AwaitingOutcomePort、ToolFactAcceptPort、TraceDiagnosticEmitter、CleanupPolicy。各 port 输入输出必须是 typed value，不共享 god context；`ToolRuntime.execute` 只编排 typed outcomes。
- 设计细化：ToolRuntime 是 Engine 看到的 `ToolExecutor` facade，但内部不能是一个大 `execute` 函数。推荐路径：
  ```text
  ToolRuntime.execute(batch request)
    -> ToolRegistryView resolves tool definitions / callable refs
    -> ToolPolicyEvaluator returns allow / deny / require_justification / idempotency decision
    -> DuplicateGovernance returns allow / reuse / hint / hard_stop
    -> ToolDispatchPort executes or produces awaiting outcome
    -> TruncationService applies ToolTruncateSpec and creates descriptor metadata
    -> ToolFactAcceptPort submits candidate to Host accept barrier
    -> TraceDiagnosticEmitter emits diagnostic / projection_signal refs
    -> CleanupPolicy releases attempt-local resources at terminal
  ```
- port ownership：
  - `ToolFactAcceptPort` is the only path from ToolRuntime to Host durable acceptance.
  - `TruncationService` owns cursor / scope_token validation logic but Host durable descriptor is truth.
  - `DuplicateGovernance` owns run-local duplicate decisions but not long-term memory / retrieval.
  - `TraceDiagnosticEmitter` emits committed diagnostic inputs; it does not call tool trace projection storage directly.
- 禁止边界：不得让 ToolRuntime 同时直接写 EventLog、直接改 Run / Attempt、直接写 tool trace projection、直接读取 HostPolicyProviderSet 全量对象，或把所有 port 状态塞进一个 untyped runtime context。

### B11. Context Governance orchestrator 边界

- 来源：SMELL-HOST-005，B6 延伸
- 裁决：接受，P1。
- 要求：Context Governance phase design 必须把 Context Governance 定义为 orchestrator，不直接读写 memory projection、trace projection 或 audit projection。建议依赖 BudgetEstimator、CompactInputProvider、CompactionExecutor、CompactArtifactStore、MemoryPatchProposalPort、AfterCommitDiagnosticPort。Memory 是否吸收 compact summary 由 Memory projection policy 决定；trace / audit 只从 compact canonical events 或 projection_signal 派生。
- 设计细化：Context Governance 负责“是否需要 compact、compact 什么、产出什么 compact artifact、如何让 RunInputBuilder 用新 artifact 重建 messages”，但不拥有 memory 真源、不直接写 trace/audit projection、不直接拼最终 messages。
- 推荐路径：
  ```text
  ContextGovernance.evaluate(boundary)
    -> BudgetEstimator estimates provider-aware next-call budget
    -> CompactInputProvider returns compactable inputs / retained anchors / non-droppable facts
    -> if threshold not reached: return continue decision
    -> append CONTEXT_COMPACTION_REQUESTED through Host command path
    -> CompactionExecutor creates summaries / retained fact refs / dropped ranges
    -> CompactArtifactStore durably stores compact artifact and digest
    -> append CONTEXT_COMPACTED or CONTEXT_COMPACTION_FAILED
    -> MemoryPatchProposalPort emits optional proposal for Memory projection policy
    -> AfterCommitDiagnosticPort emits diagnostic / projection_signal refs
    -> RunInputBuilder provider later reads compact artifact as message-ready block
  ```
- port ownership：
  - `BudgetEstimator` owns token / budget estimation; it does not decide which facts are verified.
  - `CompactInputProvider` owns selection of candidate input ranges and non-droppable anchors; it reads through typed providers, not raw projection internals.
  - `CompactionExecutor` owns summarization / compression work; its output is an artifact, not a replacement for EventLog facts.
  - `CompactArtifactStore` owns durable artifact refs / digest / retention.
  - `MemoryPatchProposalPort` may propose pinned_state / summary updates, but Memory projection policy decides whether and how to apply them.
  - `AfterCommitDiagnosticPort` records trace / audit inputs through EventLog diagnostic / projection_signal or committed refs; it does not call trace / audit storage directly.
- 禁止边界：Context Governance 不得直接 update memory snapshot、不得直接 write audit / tool trace projection、不得 erase EventLog facts、不得让 compact summary 替代 evidence anchor、不得 reuse failed provider request payload 作为下一 Attempt input。
- 写回注意：`design.md` 若保留 `pinned_state patch` / `trace / audit projection` 等表述，应明确它们是 proposal / event source，不是 command path 直接写 projection。

## P2 phase-local / 不写回架构级 design

### C1. SQLite schema

- 来源：Mimo F-13
- 裁决：P2。
- 理由：架构级 design 已明确 durable truth、transaction、CAS、payload co-durability。表结构、索引、外键、SQL 细节属于 Storage phase design。

### C2. Policy 默认值量化

- 来源：Mimo F-06，Mimo F-12
- 裁决：P2。
- 理由：架构必须声明有默认值且可显式注入；具体 retry/recovery/compact 次数与退避参数属于 policy phase。

### C3. Session-level event stream

- 来源：DS-020
- 裁决：P2 / non-goal。
- 理由：当前最小公共接口只需要 `stream_run_events` 和 `get_session` timeline summary。Session-level stream 可作为 read-model API 扩展，不阻塞 Host phase。

### C4. Queue promotion after recovery / resolve_wait

- 来源：DS-019，DS-021
- 裁决：已覆盖，P2。
- 理由：`RECOVERING` 与 `WAITING` 都是 active Run 状态，不释放 active slot；promotion check 由 active Run 进入终态后触发。phase design 可补注释，无需架构改动。

### C5. EngineEvent 映射跨层契约

- 来源：Mimo F-C4
- 裁决：P2。
- 理由：这是 Host / Engine 的必要 shared contract，不是过度耦合。后续 EngineEvent 变更必须同步 Host mapping tests。

## Rejected / 降级

### R1. “设计存在系统性过度设计或职责泄漏”

- 来源：三份 review 均未支持该判断。
- 裁决：拒绝。
- 理由：EventLog 被多个消费者读取、Host composition root 持有多个依赖、RunInputBuilder 汇总多源输入，都是该架构范式下的必要耦合。需要通过 typed facets / adapters 控制耦合，但不构成系统性过度设计。

### R2. “Remote accept barrier 必须在架构级定义 wire protocol”

- 来源：DS C-001 / C-002 的潜在解读。
- 裁决：拒绝。
- 理由：架构级只定义 semantic contract。wire frame、ack envelope、heartbeat、replay、batch 是否支持属于 Remote phase design。架构必须写硬的是：ToolRuntime 不得让 Engine 消费 Host 未 durable accepted 的 tool fact。

### R3. “steer on WAITING 应直接拒绝”

- 来源：DS-003 recommended option A。
- 裁决：不采纳。
- 理由：`WAITING` 仍是 active Run。生产级交互中用户应能改变等待中的当前 Run 方向。采用 wait abandonment + new Attempt 更符合 “Host strong governance” 和 steer 语义；迟到 wait result 被拒绝进入 canonical facts。

## 写回顺序建议

1. 先更新 `dayu/README.md`：补 `STARTING`，统一 canonical event / `canonical_fact` 术语。
2. 更新 `docs/host/design.md` 状态机小缺口：`host_instance_id`、steer target、WAITING steer、resolve_wait 非 waiting、RECOVERING exits、dispatch startup failure。
3. 更新 `docs/host/design.md` 事实链与投递边界：retry/replay source relation、Outbox target freeze、memory freshness、dirty replay exclusion。
4. 更新 `docs/host/design.md` composition / command path 边界：Host command handle 与 background supervisor facet 分离，command path 只能通过 after-commit wakeup port 通知 Sink / Outbox / projection 后台追平。
5. 更新 `docs/host/design.md` 远端 / ToolRuntime / policy 边界：accept barrier semantic、policy snapshot ownership、duplicate reuse / seed 的 phase 前置说明。

以上写回完成后，`docs/host/design.md` 和 `dayu/README.md` 可以作为下一阶段 phase design / phase plan 的稳定真源。 remaining P1 / P2 项应进入对应 phase design 的 entry checklist，而不是继续扩大架构级文档。
