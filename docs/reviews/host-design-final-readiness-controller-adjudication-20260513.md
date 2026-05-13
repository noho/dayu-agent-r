# Host 设计最终就绪总控裁决

- 日期：2026-05-13
- 范围：`docs/host/design.md`、`docs/host/implementation-control.md`
- 术语真源：`dayu/README.md`
- 评审输入：
  - `docs/reviews/host-design-final-readiness-mimo-20260513.md`
  - `docs/reviews/host-design-final-readiness-ds-20260513.md`
  - `docs/reviews/host-design-final-readiness-codex-20260513.md`

## 总体裁决

Host 设计 v2 通过最终就绪评审，所有问题均为非阻塞项。

当前设计可以进入 phase 编排，但不能直接进入大块 Host 实施。下一步应先在 `docs/host/implementation-control.md` 中补齐 phase 清单、依赖顺序、进入条件、退出条件和验证要求。

没有问题要求重写架构或推翻当前 Host 设计方向。

## 总控原则

- `docs/host/design.md` 是 Host 架构真源。
- `dayu/README.md` 是项目级术语真源。
- 下列裁决默认是对应 phase 的进入条件或追踪项。
- 写回 `design.md` 时只写最终架构结论，不写 review 过程、历史讨论或裁决来源。
- 后续实施 Agent 不得自行改写下列语义。若 phase discussion 得出更优设计，必须先更新 `design.md` 和 `dayu/README.md`，再更新 `implementation-control.md`。

## A1. Phase 清单必须先于 Phase 计划

状态：接受。

严重性：对工作流是高优先级；不阻塞设计就绪。

裁决：

在任何可交付实施的 phase plan 开始前，`docs/host/implementation-control.md` 必须先补齐 phase 清单。phase 清单是编排元数据，不是新的架构语义。

phase 清单最小字段：

- phase 名称。
- 目标。
- 对应 design 章节。
- 进入条件。
- 退出条件。
- 允许修改范围。
- 明确不做项。
- 前置依赖。
- 必须验证的类型。
- 必须解决或继续追踪的事项。

推荐第一轮编排顺序：

```text
Engine Context Event Cleanup
  -> Host Storage / Durable Store
  -> EventLog / Canonical Event Contract
  -> Session / Run / Attempt State Machine
  -> Public API / Admission
  -> WorkerProxy / Attempt Dispatch
  -> ToolRuntime / Tool Awaiting / Truncation
  -> Observer / Sink / Projection / Outbox
  -> Recovery
  -> RunInputBuilder / Memory / Context Governance
  -> RemoteProxy / RemoteStub hardening
  -> Integration / Cross-layer validation
```

依赖说明：

- Engine Context Event Cleanup 必须先于 Context Governance phase plan；Host 不得把 Engine 的 `0/0/0` budget 占位当作真实预算事实。
- Storage / Durable Store 是 EventLog、State Machine、Public API、Recovery、Projection、Outbox 的前置。
- EventLog / Canonical Event Contract 是 State Machine、ToolRuntime accept barrier、Recovery、Memory、Outbox 的前置。
- Public API / Admission 是 Service / UI 用户可见行为，以及 `start_run`、`submit_followup`、`cancel_run`、`retry_run`、`replay_run`、`purge_session` 实施的前置。
- WorkerProxy / Attempt Dispatch 与 ToolRuntime 必须先统一 attempt identity、`execution_id`、取消传播和 tool fact accept ack，再进入 RemoteProxy hardening。

## A2. 工具事实的 Canonical 写入所有者

状态：接受。

严重性：高。

裁决：

ToolRuntime 的 Host accept path 是工具事实的唯一 canonical owner。

canonical 写入路径：

```text
Engine calls ToolExecutor.execute(...)
  -> ToolRuntime applies policy / truncation / duplicate governance
  -> ToolRuntime executes tool or creates awaiting / reuse outcome
  -> ToolRuntime submits tool fact candidate to Host accept path
  -> Host validates attempt_id + execution_id + accept idempotency key
  -> Host appends TOOL_* canonical fact or rejects candidate
  -> Host returns accepted ack with canonical event refs
  -> ToolRuntime returns result / awaiting response to Engine only after accepted ack
```

EngineEvent ingest 不允许为同一个工具 outcome 追加第二条 `TOOL_RESULT_ACCEPTED`、`TOOL_AWAITING`、`TOOL_TERMINAL_RESULT` 或等价工具 canonical fact。

需要写回的语义：

- Engine 若发出描述已接受工具结果的事件，必须携带 accepted event refs 或 accepted tool fact ids。
- accepted refs 与 Host 真源匹配时，EngineEvent ingest 只记录 preview / diagnostic / trace。
- accepted refs 缺失或与 Host 真源不匹配时，EngineEvent ingest 将其视为 protocol violation 或 diagnostic，不写 canonical fact。
- EngineEvent stream 重放、remote resend、ack retry 都不得追加重复工具事实。

远端规则：

- RemoteProxy / RemoteStub 必须支持 tool fact accept ack 往返。
- 这不是可选 transport 优化。
- 远端延迟只能在不绕过 accept barrier 的前提下优化。
- batching 只有在每条工具事实都先 durable accepted、再让 LLM 消费对应工具结果时才允许。

必须验证：

- 本地工具结果只 accepted 一次。
- 远端工具结果只 accepted 一次。
- ack timeout 后重试返回同一组 accepted refs。
- accepted ack 后 EngineEvent resend 对 canonical facts 是 diagnostic / no-op。
- stale `execution_id` 不能 accept tool fact。
- 同一 accept idempotency key 搭配不同 digest 时返回 conflict / rejection。

## A3. Cancel / Suspend 竞态

状态：接受。

严重性：高。

裁决：

Host ingest 顺序是确定性排序真源。cancel request 已经 accepted 后，后续 suspend / awaiting candidate 不得让 Run 长期停在 `WAITING`。

规则：

1. terminal fact 已提交时，terminal 胜过后续 cancel。
2. suspend / awaiting 先提交时，Run 进入 `WAITING`；后续 cancel 走既有 `WAITING -> CANCELLED` 路径。
3. cancel 先提交时，后续 suspend / awaiting candidate 不得把 Run 推入 `WAITING`。

cancel-first 路径：

```text
Host commits CANCEL_REQUESTED + RUN_CANCELLING
  -> current Attempt later reports TOOL_AWAITING / run_suspended
  -> Host must not create an active wait record
  -> Host records awaiting details only as diagnostic / tool trace if useful
  -> Host closes the Attempt as cancelled or cancellation-superseded
  -> Host appends RUN_CANCELLED
  -> late external job result can only enter diagnostic / tool trace
```

suspend-first 路径：

```text
Host commits TOOL_AWAITING + RUN_WAITING + ATTEMPT_SUSPENDED
  -> client later calls cancel_run
  -> Host appends CANCEL_REQUESTED
  -> Host marks wait record cancelled
  -> Host appends RUN_CANCELLED
  -> external job cancel remains adapter best-effort
```

该规则同时保持两个原则：

- cancel 不改写已经 canonical accepted 的事实。
- accepted cancel 会阻止后续工作继续占用 Session active slot。

必须验证：

- cancel-first / suspend-late。
- suspend-first / cancel-late。
- `CANCELLING` 状态下重复 cancel。
- `RUN_CANCELLED` 后迟到 callback / poll result。
- active Run 取消后 queued Run promotion。

## A4. Steer Lost 竞态

状态：接受。

严重性：对 Steer phase 是高优先级；不阻塞 phase 编排。

裁决：

`STEER_REQUESTED` 是目标 active Run 的 canonical control intent。如果目标 Attempt 在 steer 生效前先到达 terminal，terminal 胜出，steer 不改写已经 terminal 的 Run。

steer-lost 路径：

```text
Host appends STEER_REQUESTED
  -> old Attempt terminal fact wins race
  -> Host commits terminal Run state
  -> Host records STEER_LOST as diagnostic or projection_signal
  -> steer input does not enter the terminal Run's messages
  -> Host does not silently create a new Run
```

`STEER_LOST` 必须包含：

- 原 `STEER_REQUESTED` event ref。
- 目标 `run_id`。
- 赢得竞态的 terminal event ref。
- reason code，例如 `target_terminal_before_steer`。
- 调用方可见的状态提示。

`STEER_LOST` 不是 canonical fact，因为它不能驱动 recovery、memory、resume 或 Run 状态迁移。它只用于 UI 反馈、audit 解释、tool trace / diagnostic 可见性。

调用方行为：

- 聊天界面的普通输入入口应统一是 `submit_followup`，不应先读取 active Run 再在 `start_run` / `submit_followup` 之间做客户端侧选择。
- steer 不能像 queue 一样自然吸收 active Run 竞态，因为 steer 的语义是作用于指定的当前执行。它必须携带 `target_run_id` 或等价 expected active Run precondition。
- steer 模式下，UI / Service 调用 `submit_followup(behavior=steer, target_run_id=...)`，`target_run_id` 表示调用方认为正在被 steer 的 Run。
- 如果 `target_run_id` 仍是当前 active 且状态可 steer，Host 在事务内接受 steer。
- 如果目标 Run 已 terminal、没有 active Run、active Run 已切换或目标状态不可 steer，Host 返回 `invalid_state` / `conflict`，不得自动换目标。
- 聊天 UI 的默认 fallback 是用同一条用户输入重新调用 `submit_followup(behavior=queue)`，让 Host admission 决定立即启动还是排队。
- 控制型 UI 可以选择只提示用户 steer 已失效，不自动重交。
- Host 不自动把 steer 降级成 queue / start_run / replay。
- 如果 terminal 在 steer request validation 前已经提交，Host 返回 `invalid_state`，由调用方选择下一步。

## A5. Resolve Wait / Resume Canonical 序列

状态：接受。

严重性：对 Wait / Resume phase 是高优先级。

裁决：

架构层不新增 `RUN_RESUMED`。复用 `RUN_STARTED`，但必须带明确 `start_reason`。

`RUN_STARTED` 的语义是“这个 Run 正在进入 active Attempt lifecycle”，不只表示首次用户启动。

WAITING resume 路径：

```text
resolve_wait(wait_id, outcome)
  -> Host validates wait record and idempotency
  -> Host appends RESUME_REQUESTED
  -> Host appends TOOL_TERMINAL_RESULT or equivalent resolved tool result fact
  -> Host appends RUN_STARTED(start_reason=resume)
  -> Host creates Attempt(status=STARTING)
  -> Host appends ATTEMPT_STARTED
  -> commit
  -> Host dispatches after commit
```

wait resolution 失败路径：

```text
resolve_wait(wait_id, failed)
  -> Host appends RESUME_REQUESTED
  -> Host appends TOOL_TERMINAL_RESULT(status=failed) or structured failure fact
  -> Host applies policy:
       -> RUN_FAILED
       -> RUN_RECOVERING
       -> retry path, if explicitly requested later
```

后续写回要求：

- `RUN_STARTED` payload 必须区分 `start_reason=initial | queue_promotion | resume | steer | recovery`。
- `RESUME_REQUESTED` 表达为什么要构造新的 Attempt。
- `ATTEMPT_STARTED` 表达新的执行尝试。

## A6. Recovery 成功路径 Canonical 序列

状态：接受。

严重性：对 Recovery phase 是高优先级。

裁决：

Recovery 成功必须使用与普通执行一致的 Attempt start contract，并设置 `start_reason=recovery`。

Recovery 路径：

```text
Host startup / recovery scan
  -> positive orphan proof established
  -> Host CAS old active Attempt to LOST
  -> Host appends ATTEMPT_LOST
  -> if recoverable:
       -> Host appends RUN_RECOVERING
       -> Host rebuilds messages from canonical facts
       -> Host appends RUN_STARTED(start_reason=recovery)
       -> Host creates Attempt(status=STARTING)
       -> Host appends ATTEMPT_STARTED
       -> commit
       -> dispatch after commit
  -> if unrecoverable:
       -> Host appends RUN_LOST
```

v1 不需要新增 `RUN_RECOVERED` event。

`RUN_RECOVERING` 表示 recovery governance 已启动。`RUN_STARTED(start_reason=recovery)` 表示 Run 已用新 Attempt 重新进入 active lifecycle。`ATTEMPT_STARTED` 表示 dispatch intent。

必须验证：

- 用户输入已 accepted 但 final answer 未返回时崩溃。
- `ATTEMPT_STARTED` 后、`ATTEMPT_RUNNING` 前崩溃。
- 旧 worker 可能仍运行时崩溃。
- positive orphan proof 不成立时，不写 `ATTEMPT_LOST`，不创建新 Attempt。
- recovery attempt 成功后，final answer 可通过 read path / Outbox 补达。

## A7. `submit_followup(queue)` 的执行目标

状态：接受。

严重性：对 Public API phase 是高优先级。

裁决：

聊天界面的普通 prompt 入口统一是 `submit_followup`，不是由调用方先检查 active Run 后再选择 `start_run` 或 `submit_followup`。调用方表达用户意图，Host 在 admission transaction 内决定该输入立即启动、排队还是作为 steer 被接受。

`submit_followup(behavior=queue)` 仍是用户输入 API，不增加开放式 policy knobs。

queued follow-up 需要变成 Run 时，Host 通过 Host policy 解析 execution target，并把归一化后的 execution target 持久化到 accepted Run / queued Run payload。

规则：

- `start_run` 表达显式新建独立 Run 目标，不是聊天 UI 每次发送普通 prompt 的默认入口。
- `submit_followup(queue)` 必须由 Host 在同一个 admission transaction 内自然吸收 active Run 竞态。
- `submit_followup(queue)` 可在有 active Run 或无 active Run 时调用；active 检查必须在 Host admission transaction 内完成。
- 有 active Run 时，`submit_followup(queue)` 创建 queued Run。
- 无 active Run 时，`submit_followup(queue)` 创建并启动新 Run。
- 调用方需要显式新独立目标、非会话延续输入或特殊执行目标时，应调用 `start_run`。
- `submit_followup(queue)` 不绕过 WorkerSelectionPolicy。
- 无 active Run 且 `submit_followup(queue)` 被接受为普通 Run 输入时，Host 使用与 `start_run` 相同的归一化 policy path 选择 target。
- 选定的 target 必须在 dispatch 前持久化，queue promotion 不得依赖 UI 临时状态。
- `submit_followup(queue)` 的 `invalid_state` / `conflict` 不应表示 active Run 竞态；它应表示 Session closed、幂等冲突、权限不满足、输入不合法等真实错误。

聊天 UI 推荐路径：

```text
用户输入 prompt
  -> submit_followup(session_id, input, behavior=queue | steer, target_run_id?)

behavior=queue:
  -> Host admission:
       -> active exists: queued
       -> no active: started

behavior=steer:
  -> Host validates target_run_id as expected active Run
  -> if accepted: steered
  -> if invalid_state / conflict:
       -> UI may resubmit same input as submit_followup(queue)
```

Public API phase 需要确定 request 字段：

- 不加字段，只使用 policy-only target resolution；或
- 增加可选 `execution_target_hint`，由 Host policy 校验和归一化。

v1 默认建议：不加字段，使用 policy-only target resolution；除非出现明确 UI workflow 需要 target hint。

## A8. Retry / Replay 前置条件

状态：接受。

严重性：中。

裁决：

`replay_run` 和 `retry_run` 都是公开 Host control API，由调用方主动调用。Host 不自动 replay / retry，也不把 replay 当作 terminal 输出失败后的内部隐式修复策略。

`replay_run` 和 `retry_run` 都创建关联新 Run，不重开源 Run。调用方必须显式传入源 `run_id`、`client_request_id` 和原因；Host 负责校验源 Run 状态、幂等键、语义输入 digest 和 policy。

默认前置条件矩阵：

| 源 Run 状态 | retry_run | replay_run |
| --- | --- | --- |
| `SUCCEEDED` | 默认拒绝；除非显式 retry policy 支持重跑成功 Run | 仅在格式 / schema / 结构修复场景接受 |
| `FAILED` | retry policy 允许时接受 | 拒绝 |
| `LOST` | 仅当 policy 判断 durable facts 足够支持创建新 Run 重试时接受 | 拒绝 |
| `RECOVERING` | `invalid_state` | `invalid_state` |
| `RUNNING` / `WAITING` / `CANCELLING` | `invalid_state` | `invalid_state` |
| `QUEUED` | `invalid_state` | `invalid_state` |
| `CANCELLED` | 默认拒绝；未来 policy 可支持显式 rerun | 拒绝 |

Replay 仍然是调用方主动发起的 no-tool 结构修复。它适用于 final answer 的格式、schema、结构或输出 envelope 脏数据；幻觉、事实错误、证据不足、归因错误不属于 replay 场景。

## A9. Memory Snapshot 原子性

状态：接受。

严重性：对 Memory phase 是高优先级；不阻塞 phase 编排。

裁决：

v1 Memory projection 应默认使用同一 SQLite durable store transaction 提交 snapshot + checkpoint。

v1 默认路径：

```text
consume EventLog up to event_sequence N
  -> build memory snapshot
  -> write snapshot row / payload ref
  -> write projection checkpoint N
  -> commit in one SQLite transaction
```

跨存储 atomic commit marker 不进入 v1 默认实现。它作为未来 memory storage split 的 deferred capability。

如果 phase 提议 v1 使用跨存储 memory artifact，必须明确说明：

- 为什么同 SQLite transaction 不够。
- digest 校验如何工作。
- checkpoint rollback / replay 如何工作。
- RunInputBuilder 如何避免消费缺失或 digest 不匹配的 snapshot。

## A10. ToolRuntime Accept Barrier 延迟

状态：接受。

严重性：对 Remote / ToolRuntime phase 是高优先级。

裁决：

远端延迟不是绕过 Host accept barrier 的理由。

允许的优化：

- 在下一次模型 iteration 前 batch 多个并行 tool fact candidate。
- 压缩 accept payload，但保留 digest 和 refs。
- transport request pipelining，但 ToolRuntime 仍必须阻止 LLM 消费未 accepted 的结果。
- 通过 accept idempotency key 重试 ack。

禁止的优化：

- Host accepted ack 前把工具结果返回给 Engine。
- 让远端 ToolRuntime append EventLog。
- 让 EngineEvent ingest 成为工具事实的主写入路径。
- 信任远端内存作为 durable accept state。

RemoteProxy phase 必须把这条作为不可妥协约束。

补充语义：

- RemoteProxy 与 LocalProxy 的治理语义相同；区别只是 LocalProxy 通过本地函数调用表达，RemoteProxy 通过远程调用表达。
- 远端 tool 执行本质上等价于把 LocalProxy 下的 tool execution / Host accept 调用改成远程调用。
- 因此远端网络延迟、序列化成本或额外 round trip 不是放松 Host accept barrier 的理由。
- 如果远端延迟成为性能问题，只能在保持“LLM 消费前必须 Host durable accepted”的前提下做 batching / pipelining / payload compression，不能改变治理顺序。

## A11. `purge_session` 是 Append-Only 例外

状态：接受。

严重性：中。

裁决：

`purge_session` 是 v1 对正常 EventLog append-only retention 的唯一 destructive exception，只能在严格前置条件成立后执行。

purge tombstone 必须保留足够支持 audit 和幂等重试的信息：

- `session_id`。
- purge `client_request_id`。
- semantic request digest。
- 来自 `HostCallContext` 的 actor / source / request refs。
- reason。
- purge timestamp。
- precondition digest，包括所有 Run 已终态、Session 已 `CLOSED` 的证明。
- 按数据类别统计的 deleted counts / digest。
- tombstone id / record id。

purge 后：

- 同一 request id + 同一 semantic digest 返回既有 purge result / tombstone。
- 同一 request id + 不同 semantic digest 返回 `idempotency_conflict`。
- 读取已 purge Session 返回 `gone` / tombstone snapshot 或 `not_found`，由 Public API phase 决定。
- 不再支持 recovery、retry、replay、timeline replay 或 final answer 恢复。

Storage phase 必须定义 tombstone table / file 位置，以及共享 artifact ref check。

## A12. `close_session` 与 Queued Promotion

状态：接受。

严重性：中。

裁决：

`close_session` 只关闭新输入入口，不取消已 accepted queued Runs。

规则：

- `ensure_session(scope, slot_key)` 返回当前 closed Session snapshot，不自动创建新 Session。
- close 后继续对话必须显式调用 `create_session(bind_slot=true, scope, slot_key)`。
- close 前 accepted 的 queued Runs 保持 durable。
- active slot 释放后，即使 Session 已 `CLOSED`，queued Runs 仍可 promotion。
- 调用方如果不希望有后续工作，必须先 cancel queued Runs，或通过 UI / Service 提供 “cancel all queued then close” 的复合操作。

这保持了 close 不是 cancel、close 不改写已 accepted 工作的原则。

## A13. Event Type 必要性审核

状态：接受。

严重性：中。

裁决：

EventLog phase 实施前必须做一次 canonical event type 必要性审核。

审核规则：

每个 canonical event type 至少必须回答一个不同问题：

- recovery 问题。
- 状态迁移问题。
- audit 责任问题。
- RunInputBuilder / memory input 问题。
- 用户可见 terminal / timeline 问题。

如果两个 event type 回答同一组问题，且只是 payload shape 不同，优先合并为一个 event type，用结构化 payload 区分。

不得把不同治理事实塌缩成含糊事件名，例如 generic `RUN_TERMINAL` 或 `ATTEMPT_EVENT_ACCEPTED`。

## A14. EngineEvent Stream 非正常终止

状态：接受。

严重性：中。

裁决：

WorkerProxy phase 必须定义 stream close-without-terminal 行为。

必要语义：

```text
EngineEvent stream EOF / error / transport close / worker crash
  AND no terminal event accepted for active Attempt
  -> Host records diagnostic
  -> Host evaluates Attempt as lost / recoverable according to policy
  -> Host must not leave Run indefinitely RUNNING solely waiting for restart scan
```

这不是 lease / fencing 系统，只是 Host 对自己执行流异常终止的本地治理。

远端 worker orphan execution 仍然是已接受的残余风险；未来 stale event 仍按 `execution_id` 拒绝。

## A15. Provider Tokenizer Adapter Gap

状态：接受。

严重性：对 Context Governance phase 是低到中。

裁决：

provider-specific token counting 第一版不做，作为追踪项保留。

v1 默认策略：

- 使用 conservative estimator + provider-aware configured limits + safety margin。
- Engine overflow 仍只是 fallback signal，不是主要 compaction trigger。
- provider-specific tokenizer adapter 作为后续 Context Governance 能力追踪，不进入第一版 scope。

必须验证：

- estimator undercount。
- estimator overcount。
- proactive compaction 后仍发生 provider overflow。
- repeated compaction cap。

## A16. Payload 存储阈值

状态：接受。

严重性：对 Storage / Payload phase 是中。

裁决：

Storage / Payload phase 必须定义可注入 payload policy。

必要 policy output：

- inline SQLite payload。
- durable local artifact / blob。
- domain repository reference。
- diagnostic-only trace payload。
- rejected / truncated payload。

phase 必须选择默认阈值。建议起点：

- 小型 text / JSON payload inline。
- 中型 payload 只有低于配置化 SQLite payload threshold 时才 inline。
- 大型工具输出外移，保留 digest 和 descriptor。

具体字节阈值属于 implementation policy，不属于架构层。但它必须是命名常量 / config value，不能是魔法数字。

## A17. RunInputBuilder Provider 粒度

状态：接受。

严重性：低，属于过度设计风险控制。

裁决：

设计中的语义 provider 边界是正确的。v1 物理实现可以在多个 provider 共享同一个 EventLog reader 时合并接口。

允许的 v1 简化：

```text
EventLogFactProvider
MemorySnapshotProvider
SceneParameterProvider
ToolSchemaSnapshotProvider
PolicySnapshotProvider
```

或等价小集合，只要 RunInputBuilder 不读取上游内部结构，且所有输入保持 typed。

禁止：

- RunInputBuilder 直接读取 UI text。
- RunInputBuilder 把 Session timeline 当真源。
- RunInputBuilder 查询全局 policy service locator。
- RunInputBuilder 消费 untyped metadata bags。

## A18. ToolRuntime Port 粒度

状态：接受。

严重性：低，属于过度设计风险控制。

裁决：

ToolRuntime 的语义 port 边界是正确的。v1 可以在一个模块或类中实现多个 port，但 public boundary 和测试必须保持语义分离。

v1 最小分组可以是：

- registry + dispatcher。
- policy + duplicate governance。
- truncation + fetch_more。
- Host accept + trace emission。
- awaiting / wait adapter integration。

禁止：

- 用一个 god function 混合 schema lookup、execution、truncation、policy、Host accept、tracing、wait handling，且没有 typed internal boundaries。
- remote ToolRuntime 写 Host truth。
- 对 `fetch_more` 做 Host / Engine 特化分支。

## A19. Policy Provider 边界

状态：接受。

严重性：中，属于实施边界风险。

裁决：

`HostPolicyProviderSet` 只能存在于 composition root / command path。子系统只能接收 resolved typed policy views 或 immutable policy snapshot refs。

禁止：

- 把 ProviderSet 传给 RunInputBuilder、ToolRuntime、WorkerProxy、OutboxSink 或 Memory projection。
- 下层子系统按字符串 key 查 policy。
- UI / Service request 字段未经 Host policy 校验就覆盖 Host policy。

如果保留 public request 中的 `execution_target` / `queue_policy`，它们只能解释为调用方 intent / hint。Host policy 拥有归一化、拒绝和最终决策权。

## A20. Outbox 身份与去重

状态：接受。

严重性：低；当前设计已基本覆盖。

裁决：

Outbox phase 必须定义确定性 item identity。

推荐幂等 key：

```text
outbox_item_key = hash("outbox-terminal-v1", terminal_event_id, run_id, result_digest)
```

具体 hash 算法属于 implementation policy，但输入必须包含稳定 terminal event identity 和 result digest。UI / Service 必须按 terminal identity / event_sequence 去重，不按文本去重。

## A21. 取消后编辑再发送的聊天语义

状态：接受。

严重性：中，属于 Public API / Session Timeline / UI projection 边界。

裁决：

用户已经发送的 prompt 一旦被 Host accepted，就成为 `USER_INPUT_ACCEPTED` canonical fact。Host 不支持原地修改、覆盖或删除已 accepted prompt。

聊天界面中“发送 prompt，未收到 final answer 前取消，编辑 prompt 后再发送”的语义是：

```text
prompt A accepted
  -> Run A running / cancelling
  -> user cancels Run A
  -> Run A becomes CANCELLED
  -> user sends edited prompt B
  -> Host accepts prompt B as a new user input / new Run
```

Host 真源必须保留两条输入事实：

```text
USER_INPUT_ACCEPTED(prompt A) -> Run A -> CANCELLED
USER_INPUT_ACCEPTED(prompt B) -> Run B -> RUNNING / SUCCEEDED / other terminal
```

聊天 UI 推荐路径：

- 用户取消当前 Run：调用 `cancel_run(run_id, request)`。
- 用户编辑后发送新 prompt：调用 `submit_followup(behavior=queue)`。
- 如果旧 Run 已取消完成且没有 active Run，Host admission 直接启动新 Run。
- 如果旧 Run 仍在 `CANCELLING`，Host admission 先把新输入排队，旧 Run 释放 active slot 后再 promotion。

Session timeline / UI projection 语义：

- 默认 timeline 应能表达两条 user input：prompt A 标记为 cancelled，prompt B 是新的输入。
- 聊天友好 UI 可以折叠 prompt A，或以弱化样式显示“已取消输入”。
- 折叠 / 隐藏 cancelled prompt A 只是 UI projection，不得改变 Host EventLog、RunInputBuilder、audit、memory 或 recovery 事实。
- prompt B 不得被建模为 prompt A 的 edit；它是新的 `USER_INPUT_ACCEPTED`。

后续同步到 `design.md` 时，应写入 Public API / Follow-up / Session timeline 相关章节。

## A22. 已有追踪项继续保留

状态：接受。

`docs/host/implementation-control.md` 中以下追踪项继续有效：

- Engine Context Compaction Event 语义前置。
- External Job Cancel Adapter 能力追踪。
- Tool Trace / Provider Request 排错追踪。
- SQLite 多进程写入正确性验证。
- Remote 物理执行 exactly-once 非目标。
- Session Purge / Archive 追踪。
- Host 跨层测试策略追踪。
- UI / Service Outbox 去重边界追踪。

## A23. 写回分类

状态：接受。

本裁决文档中的事项不得全部写成“追踪项”。这里区分三类：

1. 必须写回 `docs/host/design.md` 的最终设计语义。
2. 必须写入 `docs/host/implementation-control.md` phase 清单 / phase 进入条件 / phase 退出条件的实施编排约束。
3. 第一版不做、后续作为单独 issue / 后续 phase 追踪的真正追踪项。

需要写回 `design.md` 的设计语义：

- Tool fact canonical owner。
- cancel / suspend race 确定性排序。
- steer-lost diagnostic event。
- resolve_wait / recovery 的 `RUN_STARTED(start_reason=...)` 约定。
- submit_followup queue target 归一化。
- Remote ToolRuntime accept barrier 不可绕过。
- purge append-only exception 和 tombstone 幂等字段。
- EngineEvent stream 非正常终止的 Host 收口语义。
- PolicyProviderSet 只存在于 composition root 的边界。
- 取消后编辑再发送的聊天语义与 timeline projection。
- retry_run / replay_run 公开 API 与调用方主动发起语义。
- Outbox terminal identity / dedupe 语义。

需要写入 `implementation-control.md` phase 编排的进入条件或退出条件：

- phase 清单和依赖图。
- canonical event type 必要性审核。
- payload storage threshold policy。
- RunInputBuilder provider v1 粒度。
- ToolRuntime port v1 粒度。
- memory v1 same-SQLite atomicity。
- Remote ToolRuntime accept barrier 延迟与允许的优化。
- Engine cleanup 必须先于 Context Governance phase。

真正追踪项，也就是第一版不做、后续作为单独 issue / 后续 phase 处理：

- provider-specific token counting / provider tokenizer adapter。
- cross-store memory atomic commit marker。
- `archive_session`。
- 更强的 external job physical cancel / revoke / resource cleanup。
- exactly-once remote physical execution。

## 最终总控决定

更新 `docs/host/design.md` 写回设计语义，并更新 `docs/host/implementation-control.md` 补齐 phase 清单、phase 进入 / 退出条件和真正 deferred tracking 后，可以进入 phase 编排。

当前仍不得进入实施。

修改 Engine 代码前必须停下来让用户确认。

后续 phase Agent 不得重新解释以上已裁决语义。如果 phase discussion 发现 materially better design，必须先更新 `docs/host/design.md` 和 `dayu/README.md`，再更新 `implementation-control.md`。
