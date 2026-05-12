# Host Design Review — 2026-05-12 (DS)

## 审查元信息

- **Gate**: design review
- **审查目标**: `docs/host/design.md`
- **审查问题**: design.md 是否足够作为后续 handoff implementation-ready phase plan 的主真源；是否仍有猜测空间；是否存在错误架构、边界松动、路径不硬、过度设计或冗余设计
- **辅助参考**: `docs/host/discussion-note.md`, `docs/host/implementation-control.md`
- **审查者**: AgentDS（adversarial review，独立于 design.md 生成者）
- **约束**: 只产出本 review artifact；不修改 design.md；不启动 Gateflow；不写 implementation plan；不 commit/push/PR
- **前序 review 参考**: `docs/reviews/host-discussion-readiness-ds-20260512.md`（discussion-note readiness review，其中 blocking Finding 1（cancel watchdog 6项）已在 design.md Section 21 中方向性收束）

---

## 总评

design.md 是一份高质量的设计真源。核心对象（Session/Run/Attempt/EventLog）的边界清晰，状态机定义完整，关键不变量表述精确，admission/并发/EventLog/Observer-Sink/ToolRuntime/Remote 边界的硬约束足够硬。与 discussion-note.md 相比，design.md 在以下几个关键维度上有显著提升：

- Cancel 状态机：明确了完整的取消路径（QUEUED→CANCELLED 短路、CANCELLING→CANCELLED vs timeout→LOST→RECOVERING），并将 watchdog 强化显式标记为后续工作。
- EventLog canonical event taxonomy：用具体终态事件（RUN_SUCCEEDED/FAILED/CANCELLED/LOST）替换了 discussion-note 中的 `RUN_TERMINAL` 泛型，符合 "不使用模糊事件类型" 的约束。
- EngineEvent mapping：Section 12.3 提供了完整的 EngineEvent→Host EventLog 映射表，并明确区分 canonical/preview/usage projection 三层，plan agent 不需要重新发明此边界。
- RunInputBuilder 边界：明确了 "应进入 messages" 和 "不应进入 messages" 的事实分类清单。
- Plan agent 硬约束：Section 28 的九条禁止项有效防止 plan agent 在关键边界上自行发挥。

然而，存在 **2 个 blocking finding** 和 **7 个 high finding**。Blocking 集中在 canonical event contract matrix 缺失和 EventLog sequence 语义悬空——两者都不是"实现细节"，而是会影响多个子系统的架构决策。High finding 集中在边界定义的不完整、歧义和缺失，会导致 plan agent 在无指引的情况下自行补设计。

**结论**: design.md 在概念层和约束层已经很强，但在"可被 plan agent 直接翻译为 typed code and tests"（如 Section 12.3 末句所要求的）这一标准上仍有差距。建议先收束 blocking finding，再进入 phase plan 生成。

---

## Controller 状态标注（2026-05-12）

本 review 的 findings 已按当前 `docs/host/design.md` / `dayu/README.md` / `docs/host/implementation-control.md` 重新裁决：
下方原始严重度、blocking/high 标记和修正建议保留为 review-time 记录；后续 plan / implementation 以本节状态为准。

| Finding | 状态 | 归属 / 说明 |
| --- | --- | --- |
| 1 Canonical event contract matrix 缺失 | 已处理 | `design.md` 已补 canonical event contract matrix；typed dataclass / validation tests 留到 EventLog phase。 |
| 2 EventLog sequence 语义悬空 | 已处理 | 已选择全局单调 `event_sequence`，作为 Host event stream cursor、projection checkpoint、outbox、audit replay 和 recovery scan 主 cursor。 |
| 3 Steer-terminal 竞态降级路径缺失 | 已处理 | `design.md` 已补 terminal / steer 竞态规则，terminal fact 已提交时不得改写 terminal，并按 policy 降级 queued follow-up / new Run 或返回 `invalid_state`。 |
| 4 `ATTEMPT_EVENT_ACCEPTED` 语义未定义 | 已处理 | 泛型事件已移除；EngineEvent ingest 必须落到具体 canonical / preview / diagnostic，不能用模糊 accepted event 掩盖事实类型。 |
| 5 `GUIDANCE_INSERTED` 触发源和映射缺失 | 已处理到架构级 | `design.md` 已补 event matrix 与 ToolRuntime governance hint 路径；具体 guidance policy 留到对应 phase。 |
| 6 Durable queue 调度触发和优先级规则缺失 | 已处理 | `design.md` 已补 per-session FIFO、promotion trigger、CAS 与事务边界。 |
| 7 Wait record 恢复路径不完全 | 已处理 | `design.md` 已补 wait record、`resolve_wait` pipeline、poll / callback / manual adapter 边界与 atomic close/resume 语义。 |
| 8 TruncationManager 远程进程归属模糊 | 已处理 | `design.md` 已补 Host-owned ToolRuntime、远端可执行但不能写 Host truth、cursor / `scope_token` durable descriptor 与 remote cache optimization。 |
| 9 Memory snapshot / projection checkpoint 一致性未声明 | 已处理 | `design.md` 已声明 snapshot 与 checkpoint 同事务或 atomic marker，一致性失败不得推进 checkpoint。 |
| 10 `create_session.metadata` 语义未定义 | 延后到 API/schema phase | 当前 draft 保留 `metadata` 但未规范字段；进入 Session API phase 前必须决定保留、结构化或删除。 |
| 11 `RunSnapshot` / `SessionSnapshot` 字段未结构化 | 已处理到架构级 | `design.md` 已给 Snapshot 最小语义；具体 dataclass 字段留到 API phase。 |
| 12 Context compaction 保真检查未定义 | 部分处理 | `design.md` 已补 compact events、quality check result、preserved / dropped refs；保真检查算法和默认阈值留到 memory/context phase。 |
| 13 Host public error taxonomy 未映射到具体方法 | 延后到 API phase | `design.md` 已列公共错误分类；逐方法映射属于 public API handoff plan。 |
| 14 RunInputBuilder facts-to-messages 顺序未指定 | 已处理 | `design.md` 已补输入列表、`USER_INPUT_ACCEPTED` 唯一事实入口和 messages 构造顺序。 |

## Finding 1 [BLOCKING] — Canonical event contract matrix 缺失

**严重程度**: BLOCKING

**位置**: design.md Section 12.2（L407-446）

**当前写法**:

Section 12.2 列出了 canonical event 名称清单（29 个 event type），Section 12.3 给出了 EngineEvent→Host EventLog 的映射方向。但 design.md 没有为任何一个 canonical event 定义其 **event contract**：哪些字段是必需的、该 event 触发什么状态迁移、在 recovery/resume/memory/audit 中扮演什么角色。

**为什么有问题**:

1. **Event payload schema 完全空白**。例如 `TOOL_CALL_REQUESTED`——需要携带 tool_call_id? tool_name? arguments? 截断后的 arguments? 如果 plan agent 自行决定，可能与 ToolRuntime 的 tool trace 投影需求不兼容。
2. **状态迁移触发关系未形式化**。例如 `ATTEMPT_SUCCEEDED` append 后，Attempt→SUCCEEDED 和 Run→SUCCEEDED 的原子迁移——是同一事务的两个 CAS update，还是 `ATTEMPT_SUCCEEDED` 的 append 副作用？Section 9 说了 "Attempt terminal fact 提交与 Attempt 终态更新必须原子"，但没有指定哪个 event type 是哪个状态的 "terminal fact"。
3. **Recovery input 分类缺失**。Section 22 列举了"应进入 messages"的事实类型，但没有与 canonical event type 做精确映射。例如 `TOOL_RESULT_ACCEPTED` 进入 messages，但 `TOOL_TERMINAL_RESULT` 也进入——两者的 messages 角色是否相同？`TOOL_AWAITING` 呢？
4. **Plan agent 将被追加上千行 schema 定义**。如果每个 event type 需要 typed dataclass，29 个 event types 对应 29 个 payload schema。这属于设计层应明确的契约，不是实现细节。

**影响**: Plan agent 必须自行发明 29 个 event payload schema、event-to-state-transition 映射和 event-to-recovery-role 分类。这些决策会影响持久化 schema、状态机实现、恢复正确性和 memory projection 正确性。

**建议改法**:

在 design.md 中增加一个 event contract 表格（不要求 implementation-ready JSON Schema，但要求结构化描述）：

| Event Type | Required Fields | Triggers State Transition | Role in Recovery | Role in Memory | Role in Audit |
|---|---|---|---|---|---|
| SESSION_CREATED | session_id, scope, slot_key, occurred_at | Session→OPEN | 恢复 session 存在性 | 否 | 是 |
| RUN_ACCEPTED | run_id, session_id, client_request_id, input_digest, occurred_at | Run→QUEUED/RUNNING | 恢复用户输入 | 读取 input | 是 |
| TOOL_CALL_REQUESTED | run_id, attempt_id, execution_id, tool_call_id, tool_name, arguments_digest, occurred_at | 无直接迁移 | 否 | 否 | 是 |
| ... | ... | ... | ... | ... | ... |

或等效的结构化规格。至少覆盖：每个 event 的 required fields、state transition 副作用、是否参与 recovery messages 重建、是否被 memory projection 消费。

**是否阻塞 design.md 作为 plan 真源**: **是**。Section 12.3 末句要求 "Implementation plan must turn this mapping into typed code and tests; plan agent 不得重新发明 canonical / preview 边界"，但当前 design.md 本身没有给出足够将 mapping turn into typed code 的信息。

---

## Finding 2 [BLOCKING] — EventLog `sequence` 语义悬空，直接阻塞 `stream_run_events` 的 cursor 设计

**严重程度**: BLOCKING

**位置**: design.md Section 12 (L394-395)

**当前写法**:

```
`sequence` 必须提供稳定排序。具体采用 global sequence、per-session sequence、
per-run sequence 或组合，由 implementation phase 决定，但 `stream_run_events(run_id, cursor)`
必须能稳定补读。
```

**为什么有问题**:

1. **Cursor 类型取决于 sequence 方案**。如果 sequence 是 global，cursor 是全局递增整数；如果 sequence 是 per-run，cursor 是 `(run_id, seq_in_run)` 对。`stream_run_events(run_id, cursor)` 的 cursor 参数类型无法在不做此决定的情况下定义——plan agent 必须自行选择。
2. **并发 append 的排序保证取决于 sequence 方案**。多进程并发 append EventLog 时，global sequence 需要跨进程序列化（例如 SQLite autoincrement rowid），per-run sequence 只需 run 内有序（跨 run 之间无排序保证）。两种方案对 `stream_run_events` 的"稳定补读"语义影响不同：per-run sequence 下，`stream_run_events` 只能保证 run 内有序，跨 run 时间线无法从 cursor 推导。
3. **Recovery scan 依赖 sequence**。Section 26 的启动恢复扫描需要判断 "哪些事实在 crash 前已提交"——如果 sequence 方案未定，恢复扫描的起始点无法确定。
4. **这不是实现细节**。Sequence 方案决定了 EventLog 的排序模型、cursor 的 API 类型、并发写入的隔离级别和恢复扫描的起始点语义。它是架构决策。

**影响**: Plan agent 必须自行选择 sequence 方案并定义 cursor 类型，这将影响 `stream_run_events` 的 API 签名、EventLog 表 schema 和恢复扫描逻辑。如果选错（例如选了 global sequence 但对 per-run 补读性能不佳），后期修改成本高。

**建议改法**:

design.md 必须在这两种方案中选择其一（或明确声明兼容方案），不能延迟到 implementation phase：

- **推荐 per-run sequence + global event_id**：`sequence` 字段为 per-run 递增（保证 `stream_run_events(run_id, cursor)` 的 cursor 是 run-scoped 序号），同时 `event_id` 为全局唯一标识（用于跨 run 审计和 Sink 幂等消费）。这兼顾了 stream 补读的 simplicity 和跨 run 消费的需求。
- 或明确声明另一种方案并给出理由。

无论选哪种，必须明确：`stream_run_events` 的 cursor 类型、cursor 在 `RunSnapshot` 中的暴露方式（参见 Finding 11）、以及跨 run 的事件排序保证。

**是否阻塞 design.md 作为 plan 真源**: **是**。Cursor API 类型和排序保证是公共接口契约的一部分。

---

## Finding 3 [HIGH] — Steer-terminal 竞态中 steer input 的降级路径缺失

**严重程度**: HIGH

**位置**: design.md Section 11 (L349-358)

**当前写法**:

steer 路径中描述：
```
current Attempt closes as STEERED or terminal race result
```

Section 11 末句：
```
steer 必须带 active run precondition。没有 active Run、目标 Run 不匹配、
或当前 Run 已不可 steer 时，Host 拒绝 steer，不隐式创建新 Run。
```

**为什么有问题**:

design.md 只覆盖了 "请求 steer 时 Run 已经不可 steer" 的前置条件拒绝场景，但没有覆盖讨论札记中已确认的竞态降级场景。discussion-note.md L673 明确写了：

> "terminal 永远优先。Run terminal fact 一旦提交，后续 steer 输入不能改写该 Run；它应作为普通 query / follow-up 进入 admission。"

以及 L679：

> "terminal 已提交时 steer 降级为普通 query / follow-up。"

design.md 删除了这个降级路径。在 steer 路径中，"terminal race result" 暗示 terminal 可能赢得竞态，但赢得之后 steer input 去哪里了？design.md 没有回答。

竞争窗口：
1. 用户发起 steer，Host append `STEER_REQUESTED`。
2. Host 向 EngineWorker 发送 cancel signal。
3. 在 cancel signal 到达前，Engine emit `final_answer`。
4. Host 收到 `final_answer`——此时 `STEER_REQUESTED` 已经 append，但 terminal fact 即将 append。

Host ingest 顺序裁决（Section 21 末句）可以判定谁先 append。但如果 `final_answer` 先到达 Host ingest 并 append terminal fact，`STEER_REQUESTED` 随后到达——此时 steer 应该被拒还是降级？design.md 没有给出规则。

**影响**: Plan agent 在处理 steer-terminal 竞态时没有明确的降级语义指引，可能实现出不一致的行为（例如直接丢弃 steer input，或拒绝 steer 但不告知用户 input 去向）。

**建议改法**:

在 Section 11 steer 路径中补充竞态规则：

```
steer 与 terminal 竞态：
  - 若 STEER_REQUESTED 先于 terminal fact 进入 EventLog → steer 正常执行，terminal 被拒绝（execution_id 不匹配）。
  - 若 terminal fact 先于 STEER_REQUESTED 进入 EventLog → steer 降级为 queued follow-up，
    Host append FOLLOWUP_QUEUED 并使用户可见 follow-up run_id。
```

或等效的 Host ingest 顺序裁决规则。关键是 steer input 不能无声消失。

**是否阻塞 design.md 作为 plan 真源**: **不阻塞**（Section 21 的 "Host ingest 顺序是分布式竞态裁决真源" 原则已覆盖裁决机制），但 steer 降级语义的缺失会增加 plan agent 的猜测空间。

---

## Finding 4 [HIGH] — `ATTEMPT_EVENT_ACCEPTED` canonical event 语义未定义

**严重程度**: HIGH

**位置**: design.md Section 12.2 (L424)

**当前写法**:

`ATTEMPT_EVENT_ACCEPTED` 出现在 canonical event 最小集合中，但：

1. Section 12.3 的 EngineEvent 映射表中，没有任何 EngineEvent 映射到 `ATTEMPT_EVENT_ACCEPTED`。
2. 全文没有解释 `ATTEMPT_EVENT_ACCEPTED` 的语义：它是 Engine 事件的通用 passthrough envelope？还是特定 Engine 事件的 canonical 化？还是 Host 内部 ingest 确认标记？

**为什么有问题**:

`ATTEMPT_EVENT_ACCEPTED` 与 mapping 表中明确列出的 `TOOL_CALL_REQUESTED`、`TOOL_RESULT_ACCEPTED` 等具体事件的关系不清晰：

- 如果 `TOOL_CALL_REQUESTED` 等具体事件本身就是 canonical event，那 `ATTEMPT_EVENT_ACCEPTED` 承载什么？
- 如果 `ATTEMPT_EVENT_ACCEPTED` 是一个通用 envelope，那它与具体 canonical events 是什么关系？一对多？层级？
- discussion-note.md 曾以 `ATTEMPT_EVENT_ACCEPTED` 作为一些 Engine 事件的 canonical 化入口，但 design.md 已经将多个 EngineEvent 显式映射到具体 canonical event types——此时 `ATTEMPT_EVENT_ACCEPTED` 的存在理由需要重新说明。

**影响**: Plan agent 不知道如何映射 `ATTEMPT_EVENT_ACCEPTED`——它是否会与现有的具体 canonical events 产生重复/冲突？如果有 EngineEvent 不匹配任何具体映射，是 fallback 到 `ATTEMPT_EVENT_ACCEPTED` 还是丢弃？

**建议改法**:

两种收束方向：

A. 如果 `ATTEMPT_EVENT_ACCEPTED` 是未匹配 EngineEvent 的通用 fallback canonical envelope：在 Section 12.3 补充说明，明确它与具体映射的关系（"EngineEvent 优先匹配具体映射；未匹配的 Engine 诊断事件通过 ATTEMPT_EVENT_ACCEPTED 进入 EventLog，携带原始 EngineEvent type 作为 payload 字段"）。

B. 如果 `ATTEMPT_EVENT_ACCEPTED` 是残留概念（discussion-note 中的泛型事件已被 design.md 拆分为具体类型）：从 canonical event 列表中移除，避免歧义。

推荐 B——当前映射表已经足够详细，不需要一个语义模糊的 fallback envelope。

**是否阻塞 design.md 作为 plan 真源**: **不阻塞**，但 plan agent 会在 EventLog ingest 实现中遇到 "收到未映射 EngineEvent 时怎么办" 的决策真空。

---

## Finding 5 [HIGH] — `GUIDANCE_INSERTED` event 的触发源和映射缺失

**严重程度**: HIGH

**位置**: design.md Section 12.2 (L443), Section 12.3 (映射表)

**当前写法**:

`GUIDANCE_INSERTED` 在 Section 12.2 中被列为 canonical event。Section 12.3 的 EngineEvent 映射表中没有 `GUIDANCE_INSERTED` 的对应映射（这是正确的——guidance 是 Host 内部产生的，不是 Engine 事件）。但 design.md 没有说明：

1. **谁来 append `GUIDANCE_INSERTED`**？ToolRuntime？Host context governance？RunInputBuilder？
2. **什么时候 append**？在 tool result accepted 后？在 context compaction 后？在下一轮 messages 构造时？
3. **`GUIDANCE_INSERTED` 的 payload 是什么**？guidance text？target tool_call_id？governance policy reference？
4. **与 RunInputBuilder 的关系**？Section 22 说 `GUIDANCE_INSERTED` 如果影响后续 iteration 应进入 messages。但 guidance 如何从 EventLog 进入 messages？是通过 RunInputBuilder 读取 `GUIDANCE_INSERTED` fact，还是 guidance 直接在构造 messages 时注入而不经过 EventLog？

**为什么有问题**:

discussion-note.md 对 guidance 有更详细的描述（"tool result accepted → Host / ToolRuntime evaluates guidance policy → optional guidance message appended to current run input sequence"），但 design.md 收束为更 gating 的表述后，丢失了操作路径。

如果 guidance 不经过 EventLog 而直接进入 messages，那么：
- guidance 不可审计（违反 Section 14 "audit 重点记录治理动作和责任链"）。
- guidance 不参与 recovery messages 重建（resume 后的新 Attempt 丢失 guidance）。
- guidance 不在 tool trace 中可见。

如果 guidance 经过 EventLog，需要定义 append 时机（ingest 路径中的哪个节点）和与 messages 构造的关系。

**影响**: Plan agent 对 guidance 的 EventLog 路径有两种完全不同的实现选择，且两种选择对审计和恢复的影响截然不同。

**建议改法**:

在 Section 12.3 后或 Section 22 中补充 guidance 的 EventLog 路径：

```
guidance 路径：
  tool result accepted
    -> ToolRuntime / context governance evaluates guidance policy
    -> Host appends GUIDANCE_INSERTED (canonical, payload: guidance text, policy ref)
    -> RunInputBuilder 在构造下一次 messages 时读取 GUIDANCE_INSERTED fact
    -> guidance 进入后续 AgentRunRequest.messages
```

这明确 guidance 经过 EventLog（可审计、可恢复），且由 RunInputBuilder 统一消费。

**是否阻塞 design.md 作为 plan 真源**: **不阻塞**，但 guidance 的实现路径会出现两种不可调和的方案，plan agent 需要明确指引。

---

## Finding 6 [HIGH] — Durable queue 调度触发和优先级规则缺失

**严重程度**: HIGH

**位置**: design.md Section 8 (L220-253)

**当前写法**:

Section 8 定义了 queued run 的持久化语义、新输入 admission 的四种模式（queue/reject/attach_active/steer），以及 "queued run promotion 到 RUNNING 与 Attempt 创建必须原子"。但以下关键维度完全缺失：

1. **谁触发 promotion**？当前 active Run 进入终态时自动触发？Host 内部 scheduler 定时扫描？`start_run` 调用方显式触发？
2. **Promotion 的排序规则**？queued runs 之间的执行顺序是什么——FIFO？priority？按 `queue_policy` 字段？
3. **Promotion 失败怎么办**？如果 promotion 事务失败（例如 CAS 冲突），是重试？跳过该 queued run？阻塞队列？
4. **`SubmitFollowupRequest` 的 queue 行为与普通 `start_run` 的 queue 行为**是否共享同一 durable queue？

**为什么有问题**:

discussion-note.md 有更详细的 queued run 语义描述（"如果同一 Session 没有 active Run，Host 可以把最早可执行的 QUEUED Run 迁移为 RUNNING"），但 design.md 删除了 "最早可执行"（暗示 FIFO 或某种顺序），同时没有给出替代的排序规则。

implementation-control.md 的追踪区明确将 "Durable queue 调度触发和优先级规则" 列为 "当前仍需在 design.md 生成时规范化的事项"——但 design.md 没有规范化此项。

**影响**: Plan agent 凭空发明 Host scheduler 组件、queue promotion 触发机制和排序规则。这些决策会影响 admission 行为、用户可见的 follow-up 执行顺序和恢复扫描逻辑。

**建议改法**:

在 Section 8 中补充最小调度语义：

```
queued run promotion:
  - 当 active Run 进入终态（SUCCEEDED/FAILED/CANCELLED/LOST）时，Host 在同一事务内
    或紧接事务后，从 durable queue 中选取下一个 queued Run 并 promote 为 RUNNING。
  - 第一版排序规则：按 durable queue 的插入顺序（FIFO）。
  - promotion 与 Attempt 创建的原子性已在 Section 9 定义。
  - promotion 失败（CAS 冲突）时重试；连续失败超过阈值时 queued Run 进入 LOST
    并记录诊断。
```

第一版不需要复杂优先级——FIFO 足够。关键是明确触发时机和排序规则。

**是否阻塞 design.md 作为 plan 真源**: **不阻塞**（promotion 的触发是 Host 内部实现），但缺失会导致 plan agent 发明 scheduler 组件的完整生命周期。

---

## Finding 7 [HIGH] — Wait record 恢复路径不完全

**严重程度**: HIGH

**位置**: design.md Section 26 (L957-961), Section 19 (L698-756)

**当前写法**:

Section 26 启动恢复扫描：
```
WAITING Run 保持 WAITING，等待 wait record resolution。
```

Section 19 定义 wait record 语义和 resume_policy（poll/callback/manual），但没有定义 wait record 本身的恢复行为：
- `poll` policy 的 wait record：恢复后 Host scheduler 是否自动恢复轮询？
- `callback` policy 的 wait record：callback 注册信息（如 webhook URL）是否 durable？恢复后是否重新注册？
- `manual` policy 的 wait record：恢复后是否需要 UI 重新触发？Host 如何通知上层 "有待处理的 waiting run"？

**为什么有问题**:

Wait record 是 Host durable 状态（Section 19: "wait record 是 Host durable 状态，不是 remote worker 状态"）。但 durability 只是 "不会丢失"，不代表 "自动恢复活性"。

- 如果 `WAITING` Run 的 wait record 是 poll policy，Host crash 后，poll loop 需要被重新启动。谁来启动？启动恢复扫描时一并启动 pending polls？还是 scheduler 独立管理？
- 如果外部 job 在 Host crash 期间完成了，poll 恢复后如何检测 "job 已完成但 wait record 仍 waiting"？需要 `external_job_id` 的状态查询不变量。

**影响**: Plan agent 需要为 wait record 的恢复行为定义 scheduler 组件和 poll restart 逻辑，这可能引入新的内部组件设计。

**建议改法**:

在 Section 26 中补充 wait record 恢复语义：

```
WAITING Run 恢复：
  - Host recovery scan 发现 WAITING Run 后，检查关联 wait record。
  - poll policy：Host scheduler 恢复对该 wait record 的轮询；
    如果 external_job_id 存在，首次轮询前先查询 job 当前状态。
  - callback policy：第一版 callback 未实现，wait record 保持 waiting；
    上层可通过 resolve_wait 手动 resolve。
  - manual policy：wait record 保持 waiting；上层通过 resolve_wait 手动 resolve。
```

**是否阻塞 design.md 作为 plan 真源**: **不阻塞**（可延迟到 tool awaiting phase），但该 phase 的 plan agent 需要此指引。

---

## Finding 8 [MEDIUM] — ToolRuntime TruncationManager 在远程执行场景下的进程归属模糊

**严重程度**: MEDIUM

**位置**: design.md Section 18 (L661-694)

**当前写法**:

```
ToolExecutor executes ToolCallable
  -> TruncationManager applies declared ToolTruncateSpec
  -> ToolExecutor returns normal tool result with truncation hint when needed
```

**为什么有问题**:

1. Section 17 说 ToolRuntime 是 ToolExecutor，Engine 只看见 ToolExecutor protocol。在远程执行场景中，EngineWorker 在远端执行，ToolExecutor（即 ToolRuntime）也在远端。
2. 按照 Section 18 的执行路径，TruncationManager 拦截在 ToolExecutor 执行路径内——所以 TruncationManager 也在远端。
3. 但 TruncationManager 需要管理 cursor 状态（Section 18 末句："cursor 生命周期、TTL、读取 limit...属于 TruncationManager / ToolRuntime policy"）。
4. 如果 TruncationManager 在远端，其 cursor 状态在 EngineWorker crash 时丢失。这与 Host 作为 durable truth source 的定位矛盾——cursor 状态是工具治理状态，按 Section 17 定位应 "来自 Host attempt snapshot"。

这个矛盾源于：design.md 没有明确 TruncationManager 的进程归属。它被描述为 ToolRuntime 的一部分（Section 17），但 ToolRuntime 本身被描述为可部署在远端（Section 17: "可以随 EngineWorker 部署在本地或远端执行环境"）。

**影响**: 如果 TruncationManager 在远端丢失 cursor 状态，截断后的 fetch_more 续读将不可恢复。Plan agent 在两个合理方案之间没有指引：方案 A（TruncationManager 在 Host 侧，ToolExecutor 将原始结果回传 Host 截断后再交给 Engine）vs 方案 B（TruncationManager 在远端，但 cursor 状态通过 durable store 或 attempt snapshot 持久化）。

**建议改法**:

在 Section 18 中明确 TruncationManager 的进程归属和 cursor durability：

推荐方案 A（TruncationManager 在 Host 侧）：
```
TruncationManager 运行在 Host 进程内，是 Host/ToolRuntime 的内部组件。
ToolExecutor（在 EngineWorker 侧）返回原始工具结果；
TruncationManager 在 Host 侧应用 ToolTruncateSpec 后，
将截断结果作为 tool result 交予 Engine 消费。
cursor 状态由 Host durable store 管理，不依赖远端进程存活。
```

这符合 "远端执行环境不拥有 Host 状态" 的核心原则。

**是否阻塞 design.md 作为 plan 真源**: **不阻塞**，但 plan agent 会在 TruncationManager 实现时遇到远程场景下的 cursor 持久化问题。

---

## Finding 9 [MEDIUM] — Memory snapshot-projection checkpoint 一致性未声明

**严重程度**: MEDIUM

**位置**: design.md Section 23 (L908-916), Section 13 (L483-517)

**当前写法**:

Section 23 说 "memory snapshot 是 read model，可重建、可修复，不是事实真源"。Section 13 说 Sink 消费已提交 EventLog，按 event_id 幂等消费。

但没有声明 snapshot 写入与 projection checkpoint 推进之间的一致性要求。

**为什么有问题**:

discussion-note.md L863-864 明确指出了这个风险：

> "snapshot 写入与 projection checkpoint 应具备同事务或等价一致性；checkpoint 已推进但 snapshot 未写入会造成恢复洞。"

design.md 删除了这个一致性要求。恢复洞的具体机制：
1. Memory projection Sink 消费 event 并写入 snapshot。
2. Projection checkpoint 推进到 event_id=N。
3. Host crash 在 snapshot 写入和 checkpoint 推进之间。
4. 恢复后，checkpoint=K（K < N），但 snapshot 实际已包含到 N 的状态——或者反过来，checkpoint=N 但 snapshot 只有到 K 的状态。

无论哪种，RunInputBuilder 基于 snapshot + EventLog 重建 messages 时可能出现重复或缺失。

**影响**: Memory snapshot 的恢复可能产生不一致的 messages 重建。这是一个 data consistency bug 的潜在来源。

**建议改法**:

在 Section 23 中恢复 discussion-note 的一致性声明：

```
snapshot 写入与 projection checkpoint 推进应在同一 SQLite transaction 内完成，
或具备等价原子性。checkpoint 不得先于对应 snapshot 写入提交。
snapshot 缺失时应能从 EventLog 完整重建。
```

**是否阻塞 design.md 作为 plan 真源**: **不阻塞**，但 memory phase 的 plan agent 需要这个约束。

---

## Finding 10 [MEDIUM] — `create_session.metadata` 字段语义完全未定义

**严重程度**: MEDIUM

**位置**: design.md Section 5 (L93-98)

**当前写法**:

```
CreateSessionRequest:
  scope
  slot_key
  create_policy: reuse | new
  metadata
```

**为什么有问题**:

`metadata` 字段出现在 request 中，但 design.md 全文没有任何地方说明：
- metadata 的用途（存储什么信息？用于什么场景？）。
- metadata 的类型（任意 dict? 有 schema 约束的 key-value?）。
- metadata 是否持久化到 Session 表。
- metadata 是否可后续修改（`close_session` request 是否接受 metadata 更新？）。
- metadata 是否进入 EventLog（`SESSION_CREATED` payload 是否包含 metadata）。

**影响**: Plan agent 需要决定 metadata 的持久化位置、schema 和生命周期。如果 metadata 设计不当（例如允许 unbounded 大小），可能导致 Session 表膨胀或 EventLog payload 溢出。

**建议改法**:

在 Section 5 中补充 metadata 语义：

```
metadata：调用方附加的非治理关键信息（如 UI label、入口标识），
持久化到 Session 表，不进入 EventLog canonical fact。
metadata 不影响 Host 状态机、admission 或恢复逻辑。
```

或明确 metadata 进入 `SESSION_CREATED` payload。

**是否阻塞 design.md 作为 plan 真源**: **不阻塞**（metadata 不参与核心治理），但会引入不必要的实现歧义。

---

## Finding 11 [MEDIUM] — `RunSnapshot` 和 `SessionSnapshot` 的字段未结构化定义

**严重程度**: MEDIUM

**位置**: design.md Section 15 (L550-558)

**当前写法**:

```
get_run(run_id)
  -> RunSnapshot(status, terminal summary, active attempt, cursors)

get_session(session_id)
  -> SessionSnapshot(session status, active run, queued runs, timeline summary)
```

**为什么有问题**:

这些是 prose 描述而非结构化字段定义。关键缺失：

1. `RunSnapshot.cursors` 是什么类型？单个 cursor？还是多个 cursor（event cursor + attempt cursor 等）？
2. `RunSnapshot` 是否包含 `run_id`？`session_id`？（调用方已知但 snapshot 作为返回值可能被独立持有）。
3. `SessionSnapshot` 中的 `active run` 是 `run_id` 还是完整 `RunSnapshot` 的子集？
4. `timeline summary` 包含什么——最近 N 个事件的摘要？最近的 run 列表？

discussion-note 的 "Read Model / Stream 边界" 节有更详细的描述（如 `RunSnapshot -> status, terminal result summary, active attempt, cursors`），但同样不是结构化定义。

**影响**: Plan agent 必须为 `RunSnapshot` 和 `SessionSnapshot` 定义 dataclass。如果字段定义与 `stream_run_events` 的 cursor 不兼容（参见 Finding 2），会导致 API 不一致。

**建议改法**:

在 Section 15 中给出 Snapshot 的最小字段定义（伪代码即可）：

```
RunSnapshot:
  run_id: str
  session_id: str
  status: RunStatus
  active_attempt: AttemptSnapshot | None
  event_cursor: str  # for stream_run_events(run_id, cursor)
  terminal_summary: str | None  # final answer 摘要，仅终态时非空
```

**是否阻塞 design.md 作为 plan 真源**: **不阻塞**，但增加 plan agent 的字段发明工作。

---

## Finding 12 [MEDIUM] — Context compaction "保真检查" 未定义

**严重程度**: MEDIUM

**位置**: design.md Section 24 (L919-936)

**当前写法**:

```
Host 负责：
  - compact 触发。
  - LLM episode summary compaction。
  - pinned_state patch。
  - compact 后保真检查。
  - failure closeout。
  - context overflow retry。
```

**为什么有问题**:

"保真检查"是一个关键的质量闸门——如果 compaction 产生幻觉或丢失关键信息，会影响后续所有 iteration 的正确性。但 design.md 没有定义：
1. 保真检查的机制是什么（例如：要求 LLM 在 summary 中保留关键实体列表？事后验证 summary 包含原 episode 中的某类信息？）。
2. 保真检查失败后怎么办（reject summary 并重试？降低 compact 比例？终止 Run？）。
3. 保真检查的结果是否进入 audit projection（discussion-note 明确说 "compact 质量与丢弃原因必须可审计"，但 design.md 未明确）。

**影响**: Plan agent 需要定义保真检查机制——这是一个涉及 LLM 调用质量保证的架构决策。如果没有设计指引，实现可能过于简单（例如不做检查）或过于复杂（引入新的验证 LLM 调用）。

**建议改法**:

在 Section 24 中补充保真检查的最小约束：

```
compact 后保真检查：
  - 检查 compact 后的 messages 是否仍包含 pinned_state 全部字段。
  - 检查 compact 后的 summary 是否保留所有 TOOL_RESULT_ACCEPTED 的 evidence ref/digest。
  - 保真检查失败时，减小 compact scope 并重试；连续失败时终止 compact 并以 degraded
    context 继续，记录 CONTEXT_COMPACTION_DEGRADED 诊断事件。
```

第一版可使用规则化检查而非 LLM 检查——关键是给出方向。

**是否阻塞 design.md 作为 plan 真源**: **不阻塞**，但 context governance phase 的 plan agent 需要此指引。

---

## Finding 13 [LOW] — Host public error taxonomy 未映射到具体方法

**严重程度**: LOW

**位置**: design.md Section 10 (L316-323)

**当前写法**:

```
公共错误分类至少包括：
  - not_found
  - invalid_state
  - conflict
  - idempotency_conflict
  - permission_denied
  - internal_error
```

**为什么有问题**:

implementation-control.md 追踪区将 "Host public error taxonomy" 列为设计生成时需要规范化的事项。但 design.md 只列出了错误类别名称，没有映射到具体方法。例如：
- `start_run` 可能返回哪些错误？
- `conflict` vs `idempotency_conflict` 的区别在哪些方法中体现？
- `cancel_run` 当 Run 已终态时返回 `invalid_state` 还是 `conflict`？

**影响**: Plan agent 需要自行决定每个 method 的错误返回集合——这影响 API contract 的完整性和调用方的错误处理逻辑。

**建议改法**:

在 Section 10 中为每个 public method 标注可能的错误类别（不需要穷举，但至少给出主要错误路径）。

**是否阻塞 design.md 作为 plan 真源**: **不阻塞**。

---

## Finding 14 [LOW] — `RunInputBuilder` facts-to-messages 顺序未指定

**严重程度**: LOW

**位置**: design.md Section 22 (L850-870)

**当前写法**:

Section 22 列举了 "应进入 messages" 和 "不应进入 messages" 的事实类型，但没有指定这些事实在 messages 中的拼接顺序。

**为什么有问题**:

Messages 的顺序直接影响模型行为。在 resume/steer/replay 场景中，RunInputBuilder 重建 messages 时的顺序如果与原始 run 不同，模型可能产生不同的理解。

例如：system prompt → memory block → user input → tool results → assistant conclusions 是否应该按照这个顺序？还是 memory block → system prompt → user input → ...？

**影响**: Plan agent 自行决定 messages 拼接顺序。如果顺序选择不当（例如 tool results 在 user input 之前），模型在 resume 时可能产生错误的上下文理解。

**建议改法**:

在 Section 22 中补充 messages 拼接顺序方向：

```
messages 拼接顺序（概念级）：
  [system messages] -> [Host memory block (pinned_state + stable facts)]
  -> [user input / steer input / resume input]
  -> [alternating assistant + tool messages from canonical facts]
  -> [GUIDANCE_INSERTED if applicable]
```

**是否阻塞 design.md 作为 plan 真源**: **不阻塞**。

---

## 过度收敛评估

对 design.md 中可能 "过度收敛、限制后续最佳实现" 的检查：

| 检查项 | 评估 |
|--------|------|
| SQLite 方案过早锁定 | **否**。Section 8-9 的 SQLite 选型方向明确但没有过约束（"SQLite 应使用 WAL 与明确 busy timeout；具体参数由实现 phase 决定"）。 |
| EventLog payload 外移边界过早量化 | **否**。Section 12.1 使用定性描述（"canonical 小 payload 内联"、"大工具结果...外移"），为 implementation phase 留下了合理的量化空间。 |
| memory 参数硬编码 | **否**。Section 24 显式将参数默认值推迟到 "memory / context phase 决策"。 |
| WorkerProxy interface 过早定义 | **否**。Section 16 只定义了语义契约和不可变约束（"不 append EventLog，不关闭 Attempt，不更新 Run"），不定义 wire protocol。 |
| Observer/Sink 通知机制过约束 | **否**。Section 13 只描述了路径框架，没有指定具体的通知机制。 |
| TruncationManager cursor TTL 硬编码 | **否**。Section 18 将 cursor 生命周期推迟到 "TruncationManager / ToolRuntime policy"。 |
| Canonical event 列表过于详尽 | **边缘**。29 个 event types 在第一版是合理的，但其中 `CONTEXT_COMPACTION_REQUESTED` 和 `PROVIDER_PROTOCOL_ERROR` 的 payload 契约与 Engine 事件模型的耦合可能需要后续调整。这不算过度收敛，但 phase plan 应在实现这两个 event 时保留调整空间。 |

**结论**: 没有发现过度收敛问题。design.md 在被要求的维度上设定硬边界，在应由实现决定的维度上保留灵活性。

---

## 对比 discussion-note.md 的关键改进点（正向确认）

以下 discussion-note readiness review 中的 finding 在 design.md 中已得到良好解决：

| DS Readiness Review Finding | design.md 处理 | 评估 |
|---|---|---|
| F1 (BLOCKING) — cancel watchdog 6项 | Section 21: 完整取消路径、QUEUED→CANCELLED 短路、CANCELLING→LOST→RECOVERING 升级链、cancel control message 携带 run_id+attempt_id+execution_id、watchdog 强化显式标记为后续工作 | **已解决** |
| F2 (HIGH) — 存储方案 | Section 8-9: 明确 SQLite durable store、WAL + busy timeout、事务不变量、CAS-style state transition | **已解决** |
| F3 (HIGH) — 多进程协调 | Section 8: SQLite 事务 + 唯一约束 + CAS + event id/sequence 去重，明确不引入重 lease/fencing | **已解决** |
| F4 (HIGH) — ToolRuntime 边界 | Section 17: Host-owned, implements ToolExecutor, Engine 只看到 ToolExecutor protocol | **已解决**（但远程场景下 TruncationManager 进程归属仍有歧义，见 Finding 8） |
| F5 (HIGH) — resume_policy | Section 19: 第一版优先 internal/manual resolve + poll adapter, callback 预留 | **已解决** |
| F6 (HIGH) — RunInputBuilder | Section 22: 明确为 Host 内部组件，给出完整的进入/不进入 messages 事实分类 | **已解决** |
| F10 (MEDIUM) — cancel/suspend 竞态 | Section 21: "Host ingest 顺序是分布式竞态裁决真源" | **已解决** |
| R7 — RUN_TERMINAL/ATTEMPT_TERMINAL 泛型 | Section 12.2: 替换为具体终态事件（RUN_SUCCEEDED/FAILED/CANCELLED/LOST） | **已解决** |

---

## 剩余风险评估

即使 blocking finding 被解决，进入 phase plan 生成时仍存在以下 residual risk：

| # | 风险 | 影响范围 | 缓解措施 |
|---|------|---------|---------|
| R1 | Canonical event contract 的细节（per-event fields, state transition rules, recovery role）如果在 plan 阶段才补充，可能导致 plan 和 design 之间的往返修正 | EventLog schema, state machine, recovery | 建议在进入 phase plan 前，在 design.md 中至少补充核心 event 的 contract（SESSION_CREATED, RUN_ACCEPTED, RUN_SUCCEEDED, TOOL_CALL_REQUESTED, TOOL_RESULT_ACCEPTED, USER_INPUT_ACCEPTED） |
| R2 | Remote wire protocol 完全延迟到 "Remote phase discussion"——第一版可能只需要 LocalProxy，但如果第一版就做 remote，plan agent 需要定义 EngineEvent 的回传 envelope | RemoteProxy, EventLog ingest | 如果第一版不做 remote execution，明确声明；如果做，至少定义 EngineEvent 的 wire envelope 最小要求（run_id + attempt_id + execution_id + sequence + event_type + payload） |
| R3 | Host lifecycle (graceful shutdown, startup recovery) 的描述是 prose 级别，plan agent 需要将其翻译为具体的恢复算法 | Host 启动流程，crash recovery | Section 26 的恢复扫描逻辑需要更精确的伪代码或状态迁移图 |
| R4 | Context governance 的 compact policy（触发条件、保真检查、失败收口）全在 Host 责任范围但细节完全延迟 | Context governance phase | Context governance phase 的 plan 需要额外的前置讨论 |
| R5 | Outbox delivery 的投递目标（WeChat/Web/CLI）和投递协议完全未定义 | Outbox delivery phase | 如果第一版不做 outbox（只做本地 stream fanout），建议在 Section 27 non-goals 中明确 |
| R6 | `CONVERSATION_MEMORY_SNAPSHOT` 或等价的 memory checkpoint event 不是 canonical event——memory snapshot 如何与 EventLog 的某个 point-in-time 关联？ | Memory projection 恢复 | 见 Finding 9，补充 checkpoint 一致性约束 |
| R7 | Section 12.1 中 payload 外移的 "canonical 小 payload" vs "大内容" 边界未量化（discussion-note readiness review R6 同样指出此风险） | EventLog 膨胀或恢复信息缺失 | 建议给出 rough guideline（例如 inline < 4KB, external ref >= 4KB），implementation phase 可调整 |

---

## 进入 Phase Plan 生成的条件

### 必须满足（blocking）

1. **收束 canonical event contract matrix**（Finding 1）：至少为核心 event（SESSION_CREATED, RUN_ACCEPTED, RUN_SUCCEEDED, TOOL_CALL_REQUESTED, TOOL_RESULT_ACCEPTED, USER_INPUT_ACCEPTED, ATTEMPT_STARTED, CANCEL_REQUESTED）定义 required fields 和 state transition 触发关系。

2. **收束 EventLog `sequence` 语义**（Finding 2）：明确 sequence 方案（推荐 per-run sequence + global event_id），定义 cursor 类型和 `stream_run_events` 的 cursor API。

### 建议满足（high）

3. **补充 steer-terminal 竞态降级路径**（Finding 3）：明确 steer input 在 terminal 赢得竞态后的降级行为（降级为 queued follow-up）。

4. **收束 `ATTEMPT_EVENT_ACCEPTED` 语义或移除**（Finding 4）：推荐移除，当前具体 canonical event 映射已经足够。

5. **补充 `GUIDANCE_INSERTED` 的触发源和 EventLog 路径**（Finding 5）。

6. **补充 durable queue promotion 触发规则**（Finding 6）：至少明确 "active Run 终态时自动 FIFO promotion"。

7. **补充 wait record 恢复行为**（Finding 7）：至少覆盖 poll policy 的恢复语义。

### 可在对应 phase 的 plan 前解决（medium/low）

Finding 8-14 及 R1-R7 可在进入具体 phase 的 plan 生成前，通过更新 design.md 对应章节来解决，不阻塞整体 phase 编排。

---

## design.md 的优势（防御性确认）

以下方面 design.md 做得很好，应在后续 plan 和 implementation 中保持：

1. **Run/Attempt 双状态机映射清晰**：Section 6-7 的 9 个 Run 状态 + 8 个 Attempt 状态 + 明确的映射规则（Attempt SUSPENDED→Run WAITING, Run CANCELLING→Attempt CANCELLED/LOST→Run CANCELLED/RECOVERING/LOST），没有任何状态迁移的歧义。

2. **LOST vs FAILED 的区分精确**：Section 6 明确 "LOST 不是 FAILED。FAILED 表示已确认失败；LOST 表示治理无法恢复或无法确认，不能伪装成普通失败。" 这对审计和质量追溯至关重要。

3. **EventLog→Projection 的真源关系不可逆**：Section 12-15 多处重复强调 "projection/audit/memory 不得反向成为 EventLog 真源"，这是架构中最关键的防偏约束。

4. **Assistant final answer 不自动成为 verified fact**：Section 23 明确 "final_answer 绝不能自动升级为 verified fact。verified fact 只接受工具事实。" 这是反幻觉的核心机制。

5. **Remote boundary 的硬约束足够硬**：Section 16 的 7 条远程执行不变量覆盖了所有常见错误（远端 append EventLog、关闭 Attempt、更新 Run、takeover、迟到事件污染等）。

6. **ToolRuntime 的 Engine 隔离正确**：Section 17 明确 "Engine 只看见 ToolExecutor protocol。Engine 不知道 @tool、ToolDefinition、TruncationManager、fetch_more 或业务工具实现。" 这防止了 Engine 对工具治理的泄漏。

7. **fetch_more 的普通 tool 约束必要且正确**：Section 18 的 6 条硬约束防止了 `fetch_more` 成为特化路径。

8. **Plan agent 硬约束（Section 28）的 9 条禁止项精确覆盖了最常见的越界风险**。

---

## 审查总结

design.md 作为 Host 架构真源，在概念建模、状态机、不变量和硬约束维度已达到高质量水平。两个 blocking finding（event contract matrix 缺失、EventLog sequence 语义悬空）都是"可被 plan agent 直接翻译为 typed code and tests"这一标准下的具体差距，而非根本性设计缺陷。收束后，design.md 即可作为后续 phase plan 的可靠主真源。

其余 12 个 finding 严重程度分布在 HIGH/LOW，多数是关于边界定义的收束——当前 design.md 在 "不该做什么" 上非常强硬，在 "具体怎么做" 上有意留白，而留白处恰好是 plan agent 需要设计指引的地方。建议在进入第一个 phase plan 生成前，按 "必要条件" 清单收束 blocking finding，并逐项 review high finding 以决定哪些在进入前处理、哪些在对应 phase 的 plan 前处理。

**最终判定**: 当前 design.md 在正确性上没有错误；在完备性上有两个 concrete blocking gap。收束后即可进入 phase 编排。
