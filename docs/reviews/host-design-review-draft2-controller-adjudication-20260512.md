# Host Design Draft2 Review Controller Adjudication

## 元信息

- 日期：2026-05-12
- 范围：汇总并裁决三份 draft2 review artifact
- 输入：
  - `docs/reviews/host-design-review-mimo-draft2-20260512.md`
  - `docs/reviews/host-design-review-ds-draft2-20260512.md`
  - `docs/reviews/host-design-review-codex-draft2-20260512.md`
- 输出定位：Controller 裁决与 design-fix pass 写回依据

## 总体裁决

`docs/host/design.md` 的主体架构是成立的：Host 是治理真源、Engine 只执行单次 request、EventLog 是事实真源、SQLite + CAS 支撑单机多进程、Remote 不拥有 Host 状态，这些方向没有被推翻。

但三份 review 都指出：当前 draft 还不能直接进入 implementation-ready phase plan。原因不是“大方向错了”，而是若干关键路径没有闭合。简单说，设计已经有骨架，但几个承重连接点还需要补螺栓。

Controller 裁决：

- 不进入 phase plan。
- 先做一次 design-fix pass。
- design-fix pass 只补架构闭环，不展开实现细节。
- 下方“可直接回写的裁决”已写入 `design.md`。
- 下方“需要用户讨论的 open decisions”均已由用户确认并写入 `design.md`。

## 合并后的阻塞域

### 1. Run 生命周期闭环不足

来源：

- MiMo Finding 1、2、10
- DS Finding 1、2、4
- Codex Finding 1、7

裁决：接受，阻塞 phase planning。

浅显解释：

当前设计已经列了很多 Run / Attempt 状态，但有几条真实用户路径还没有明确结果。例如：

- Run 正在 `WAITING` 外部结果，用户点 cancel，应该直接取消还是等外部结果回来？
- queued Run 正要被 promotion，同时用户 cancel，谁赢？
- Run 已经 `SUCCEEDED`，又 replay，同一个 Run 是否允许从终态变回 `RUNNING`？
- recovery / retry / replay 是否有最大次数，还是可能无限循环？
- Attempt 创建后 worker 启动失败，算 `STARTING`、`RUNNING`、`FAILED` 还是 `LOST`？

这些不是实现小问题。实现 Agent 如果自己补，会直接影响用户可见行为、active slot、outbox 投递和审计链。

### 2. EventLog 真源与外移 payload 的耐久性不闭合

来源：

- Codex Finding 2、4
- DS Finding 8
- MiMo Finding 5

裁决：接受，阻塞 EventLog / Recovery / Truncation / RunInputBuilder phase planning。

浅显解释：

EventLog 说“工具事实已接受”，但大 payload、证据 chunk、`scope_token` descriptor 可能在别处。如果 EventLog 写成功了，payload 还没落盘就崩溃，重启后就会出现“事实说有，内容找不到”的状态。

财报 Agent 不能接受这种状态。因为工具证据是 answer 可信度的基础，不是普通展示附件。

### 3. Remote execution 与 ToolRuntime accept barrier 不闭合

来源：

- DS Finding 3
- Codex Finding 5、6
- MiMo Finding 6

裁决：接受，阻塞 Remote / ToolRuntime phase planning。

浅显解释：

远端执行不是只要“迟到事件不进 EventLog”就够了。远端可能已经执行了工具、消耗了 provider token，甚至触发了外部副作用，只是 Host 后来拒绝了它的事件。

更关键的是：如果远端 ToolRuntime 把工具结果先喂给 Engine，Host 还没 durable accept 这个工具事实，LLM 可能基于一个 Host 真源里不存在的证据继续推理。这会破坏“宿主强约束下的 LLM in the loop”。

### 4. 语义级重复工具调用治理缺少 ledger 边界

来源：

- MiMo Finding 3、8
- DS Finding 5

裁决：部分接受，原 session-scope ledger 判断过重。需求已收窄为同一个 Run 内、由于模型复读导致的重复工具调用治理；不阻塞整体 phase planning，但 ToolRuntime phase 必须写清 run-local in-memory duplicate index。

浅显解释：

重复工具调用治理的核心场景是：LLM 在同一个 Run 里复读，反复调用同一个工具、同一组参数或工具声明的同一 semantic key，造成 token 和工具执行浪费。不是同一 iteration / 同一轮内部正常调用同一个工具就需要治理。

正确方向是：ToolRuntime 在当前 Run 内维护内存索引；Host 不解析财报业务语义。跨 Run / 多年历史中的“是否已经查过类似证据”属于 memory / retrieval，而不是第一版重复工具调用治理。

### 5. Public API 的 actor/source/outbox intent 不够硬

来源：

- Codex Finding 3、8
- DS Finding 10

裁决：接受，阻塞 API / Audit / Outbox phase planning。

浅显解释：

Host 要做 audit 和 outbox，就必须知道“是谁通过哪个入口提交的请求，结果要投递到哪里”。如果这些字段只藏在 metadata 或从 Session slot 猜，后续审计和投递恢复都会不可靠。

认证可以在上层做，但 Host 公共接口必须接收上层已经解析好的调用上下文。

## 可直接回写的裁决

以下项不需要再讨论，可以按最佳实践直接写入 `design.md`。

### D1. `WAITING` Run 的 cancel 规则

裁决：

- `cancel_run` 命中 `WAITING` Run 时，Host 在同一事务里 append `CANCEL_REQUESTED`，标记 active wait record 为 cancelled，append `RUN_CANCELLED`，Run 进入 `CANCELLED`。
- 已经 `SUSPENDED` 的旧 Attempt 不重写。
- 外部 job 的实际取消是 adapter 的 best-effort 能力，不作为第一版保证。
- `cancel_run` 与 `resolve_wait` 并发时，先提交事务者赢；后到者发现 Run 已变更后只记录 diagnostic 或返回幂等冲突。

浅显解释：

等待外部结果时没有活跃 Engine 可取消，所以不要进入 `CANCELLING` 卡住。Host 只能取消“后续是否继续”，外部 job 能不能停是工具/adapter 能力。

### D2. queued cancel 与 promotion 竞态

裁决：

- 使用 CAS first-committer-wins。
- promotion 先提交：Run 变 `RUNNING` 并创建 Attempt；cancel 后到时走 active cancel 路径。
- cancel 先提交：Run 变 `CANCELLED`；promotion 后到时 CAS 失败，不创建 Attempt。
- promotion 和 cancel 的 WHERE 条件都必须包含当前状态，不能盲写。

浅显解释：

谁先抢到数据库事务谁赢。输的一方必须重新读状态，按新状态处理，不能继续用旧判断。

### D3. `ensure_session(scope, slot_key)` 并发安全

裁决：

- slot 表对 `(scope, slot_key)` 有唯一约束。
- Session 创建与 slot 绑定必须在同一事务内完成。
- 并发重复调用返回同一个绑定 Session。
- `ensure_session` 不需要 `client_request_id`，幂等键就是 `(scope, slot_key)`。

浅显解释：

这是“同一个微信身份 / CLI label 拿同一个会话”的数据库级保证。不能靠应用层先查再插，否则多进程会抢出重复 Session。

### D4. Event identity 分层

裁决：

必须拆开三类身份：

- client operation id：客户端重试同一个 API 调用时去重。
- remote event identity：远端重放同一个 Engine/Worker 事件时去重。
- canonical event identity：Host EventLog 中每条 canonical fact 的唯一身份。

一个 remote event 映射出多个 canonical events 时，canonical identity 必须能稳定派生，例如包含 `execution_id`、remote event id、canonical event type 和 sub-index。

浅显解释：

“用户重试请求”“远端重放事件”“Host 写入事实”是三件事。共用一个 id 会导致重复 terminal、漏记 attempt terminal 或无法测试去重。

### D5. 可恢复 payload / descriptor 的 co-durability

裁决：

- 会参与 resume、memory、audit、fetch_more、replay 的 payload/ref/descriptor，必须先 durable，再 append canonical EventLog。
- EventLog row 不应内嵌大 payload；canonical event 必须带 payload ref / descriptor 与 digest，或其它可校验 ref。
- 第一版可以采用 SQLite payload table 作为默认 durable payload store，使小型 / 中型可恢复 payload 与 EventLog 在同一 SQLite transaction 内提交。
- 超过 Host policy 阈值的 payload 必须外移到 artifact / blob / domain store，并在 artifact durable 且 digest verified 后才 append canonical EventLog。
- 如果 ref 缺失或 digest 不匹配，不能把该 fact 当作 accepted fact 使用。
- preview / diagnostic / display-only payload 可以降级丢失，但不能伪装成恢复必要事实。

浅显解释：

先把证据存稳，再宣布“证据已接受”。这不要求把所有大内容塞进 EventLog row；小 payload 可以走 SQLite 同事务，大 payload 走 durable artifact ref。关键是不允许 EventLog 已经说 accepted，但恢复必要内容还没有可靠落盘。

### D6. Outbox intent 必须有强真源

裁决：

- outbox wakeup marker 可以 optional。
- 但 outbox delivery intent 不能依赖 optional marker、内存通知或临时状态。
- delivery intent 的强真源是 terminal EventLog fact，例如 `RUN_SUCCEEDED` 及其 final answer / delivery context ref。
- terminal transaction 不同步写 outbox 表；把 Run 终态提交和投递 work queue 生成强绑定违反 Observer / Sink 边界。
- OutboxSink 按 `event_sequence` 扫描 terminal EventLog facts，并 upsert outbox delivery record；outbox 表是 projection / work queue，可由 EventLog 重建。
- delivery target 必须来自 HostCallContext / Session binding / explicit request field 的稳定来源，不能从 metadata 猜。

浅显解释：

“提醒投递 worker 醒来”可以丢；“Run 已经产出需要投递的 terminal answer”不能丢。这个投递意图来自 EventLog terminal fact。OutboxSink 崩溃后只要按 checkpoint 补扫 EventLog，就能补建 outbox record。

### D7. recovery / retry / replay 必须有收敛上限

裁决：

- 架构层必须声明 recovery、retry、replay、context compaction retry 都有 policy 上限。
- 默认次数、退避参数留到具体 phase。
- 超过上限必须进入明确终态，例如 `FAILED` 或 `LOST`，不能无限占用 active slot。

浅显解释：

生产系统不能无限重试。否则 provider 挂了、payload 坏了、compact 一直失败时，Session 会永远卡住并持续烧资源。

### D8. Run-local duplicate tool governance

裁决：

- 第一版重复工具调用治理只覆盖同一个 Run 内、模型复读导致的重复工具调用，目标是减少无意义 token 和工具执行浪费。
- ToolRuntime 维护 in-memory duplicate index，不需要 session-scope durable ledger。
- duplicate key 来自 tool name、normalized args digest，以及可选的 tool-provided semantic key。
- 命中重复时按 policy 处理：复用当前 Run / Attempt 内已有结果、拒绝、提示模型、继续执行但记录 trace，具体策略留到 ToolRuntime phase。
- Host 崩溃后新 Attempt 不继承该 in-memory index；如需避免重复，依赖 RunInputBuilder 把已接受工具事实放回 messages，让模型看到已经查过什么。
- 跨 Run、跨 Session、跨多年历史中的相似证据召回属于 Conversation Memory / retrieval，不属于第一版重复工具调用治理。

浅显解释：

这里治理的是同一个 Run 里模型复读、重复敲同一个工具造成浪费。用当前 Run 的内存索引就够，不要把它升级成长期 memory、session 历史查询系统，也不要把同一轮正常工具调用误判为需要治理的问题。

### D9. Dispatch startup 状态必须明确

裁决：

`STARTING` / `RUNNING` / `ATTEMPT_STARTED` 的边界要写硬。推荐：

- Attempt row 创建后是 `STARTING`。
- worker 明确接受 dispatch 后才进入 `RUNNING`。
- dispatch 失败、startup timeout、cancel during STARTING 都要有明确状态事实或 diagnostic path。

浅显解释：

“Host 准备发出去”和“worker 已经开始跑”不是一回事。中间失败必须可恢复、可审计。

## 需要用户讨论的 open decisions

O1 与 O2 均已由用户确认。其它 finding 可以按上面的裁决直接补设计。

### O1 已确认. `retry(run)` / `replay(run)` 创建关联的新 Run

为什么要讨论：

现在设计同时说 Run 终态不可变，又说 `retry_run` / `replay_run` 可以让同一个 Run 从 `FAILED` / `SUCCEEDED` 回到 `RUNNING`。这两句话冲突。

浅显例子：

用户拿到了一个 final answer，后来发现答案脏了，要 replay。如果同一个 Run 重新变成 `RUNNING`，那旧 answer 是否还算已成功？outbox 已经投递过的结果要不要撤回？排队中的下一个 Run 是否已经被 promotion？这些都会变复杂。

推荐方案：

- Run 终态保持不可变。
- 外部语义采用函数式操作：`retry(run)` / `replay(run)`。
- `retry(run)` / `replay(run)` 返回一个关联的新 Run，例如 `source_run_id` / `replay_of_run_id` 指向旧 Run。
- 不采用 `Run.retry` / `Run.replay` / `Run.relay` 这类像是在原 Run 上重开状态的对象方法语义。
- 新 Run 可以复用旧 Run 已接受的工具事实，避免重跑昂贵工具。
- UI / Session timeline 可以把 replay Run 标成“对某次回答的重放/修正”，并把最新 replay result 作为当前展示结果。

优点：

- 状态机简单。
- audit 清楚：旧回答是什么、新回答是什么、为什么重放，都保留。
- outbox 不需要撤销旧投递，只需要投递新版本或更新展示 projection。

代价：

- 用户视角要接受“同一问题的 replay 是一个关联 Run”，不是物理上重开原 Run。

用户确认：

- 采用“终态 Run 不可重开；`retry(run)` / `replay(run)` 创建关联新 Run”的方案。

### O2 已确认. Remote ToolRuntime 采用 Host-mediated accept barrier

为什么要讨论：

远端执行时，工具可能在远端机器上跑。关键问题是：工具结果什么时候可以返回给 Engine，让 LLM 继续推理？

两个方案：

方案 A：Host-mediated accept barrier（已确认）

- 远端 ToolRuntime 执行工具后，先把工具事实发给 Host。
- Host durable append EventLog 并返回 accepted ack。
- 远端 ToolRuntime 收到 ack 后，才把 tool result 返回给 Engine。

优点：

- 最符合“宿主强约束下的 LLM in the loop”。
- LLM 不会消费 Host 真源里不存在的工具事实。
- final answer 的证据链天然闭合。

语义要求：

- Proxy / Stub / EngineWorker 执行语义必须支持 tool fact accepted ack。
- 这不是额外代价，而是 Host-mediated ToolRuntime 的基本语义。LocalProxy 与 EngineWorker 之间也存在等价的函数调用语义；RemoteProxy 只是 transport substitution。
- `design.md` 只定义 remote semantic contract，不定义 RPC / ack frame / heartbeat / replay 等 wire protocol 细节。

方案 B：final answer accept barrier

- 远端 ToolRuntime 先把工具结果返回 Engine。
- Host 后续 ingest tool facts。
- final answer 到达时，Host 检查所有前置 tool facts 是否 durable accepted；不满足就拒绝 final answer 或让 Run 失败 / 恢复。

优点：

- 远端执行链路更简单。
- 对 read-only 工具成本较低。

代价：

- LLM 可能已经基于未 durable 的工具事实继续推理。
- 失败时要丢弃更多工作。
- 对生产级证据链更弱。

用户确认：

- 第一版 remote ToolRuntime 采用方案 A：Host-mediated accept barrier。
- 写入 `design.md` 时只写语义契约，不写 wire protocol 细节，避免污染 Remote phase。

## 当前不需要用户讨论但需要追踪的项

这些项不需要现在拍板，但后续 phase plan 必须覆盖：

- SQLite 多进程写并发策略：WAL、busy timeout、短事务、重试策略。
- `cancel_run` idempotency key：active / queued / waiting 路径都要定义。
- `FollowupSnapshot` 字段：API phase 定义即可。
- `SESSION_CLOSED` 后 `ensure_session` 行为：建议默认返回新 Session 或明确错误，放到 Session API phase。
- Outbox channel routing 字段：API / Outbox phase 定义。
- Context governance token estimator 精度降级：Context phase 定义。

## 当前状态

本裁决已写回 `docs/host/design.md`，三份 draft2 review 已补 Controller 状态标注。后续可以进入 phase 编排或选择第一个 phase；进入具体 phase plan 前仍需按 `docs/host/implementation-control.md` 先和用户讨论并细化对应设计章节。
