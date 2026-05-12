# Host design.md Adversarial Review

- Reviewer: MiMo
- Date: 2026-05-12
- Target: `docs/host/design.md`
- Context: `docs/host/discussion-note.md`, `docs/host/implementation-control.md`
- Codebase: `dayu/engine/` contracts (existing), `dayu/host/` (empty), `dayu/contracts/` (shared)

## 总结

design.md 覆盖了 Session / Run / Attempt / EventLog 四个一等对象的状态机、admission、cancel / steer / resume / replay 路径、ToolRuntime、memory / context governance、remote boundary、Observer / Sink 等核心治理面。文档整体结构清晰，与 discussion-note.md 的决议对齐度高，与现有 Engine contracts 的兼容性良好。

但存在 **2 个 blocking finding** 和 **7 个 non-blocking finding**。blocking findings 会导致 phase plan agent 必须自行补设计，违反 implementation-control.md 中"不得让 planning / implementation agent 自行选择会影响架构、公共接口、状态机、schema、持久化"的约束。

建议：修正 2 个 blocking findings 后，design.md 可作为 plan 真源进入 phase 编排。

---

## Controller 状态标注（2026-05-12）

本 review 的 findings 已按当前 `docs/host/design.md` / `dayu/README.md` / `docs/host/implementation-control.md` 重新裁决：
下方原始严重度、blocking/high 标记和修正建议保留为 review-time 记录；后续 plan / implementation 以本节状态为准。

| Finding | 状态 | 归属 / 说明 |
| --- | --- | --- |
| 1 EventLog sequence 语义未定义 | 已处理 | 已选择全局单调 `event_sequence`；远端 sequence 仅作 diagnostics，不能替代 Host sequence。 |
| 2 Host handle / context 未定义 | 已处理 | `design.md` 已补 Host Handle / Composition Root，列出最小依赖边界并禁止 God object / service locator。 |
| 3 RECOVERING 状态缺少退出转移 | 已处理 | `design.md` 已补 `RECOVERING -> RUNNING / CANCELLED / LOST`，并补已接受 prompt 的 recovery 语义。 |
| 4 EventLog payload “建议”表述 | 已处理 | `design.md` 已用 EventLog shape、全局 `event_sequence` 与 canonical contract matrix 表达架构契约；具体字段类型留到 phase。 |
| 5 Durable queue 调度触发和优先级规则未定义 | 已处理 | 已补 per-session FIFO、promotion trigger、CAS 抢 active slot 和 promotion 事务边界。 |
| 6 recovery scan 触发条件和扫描范围未完整定义 | 已处理到架构级 | 已补 Host startup recovery scan 行为、dispatch record 和 accepted prompt recovery；具体 SQL / batch 策略留到 recovery phase。 |
| 7 Observer / Sink dispatch 机制未定义 | 已处理到架构级 | 已补 sink 不反压、checkpoint 追平、notification 只是 wakeup、第一版不引入重消息系统。 |
| 8 steer 与 terminal event 竞态规则 | 已处理 | 已补 terminal / steer 竞态规则。 |
| 9 `FollowupSnapshot` 未定义 | 已处理到架构级 | 已补 Snapshot 最小语义；具体 dataclass 字段留到 API phase。 |
| 10 EngineEvent 缺少 `attempt_id` / `execution_id` 对齐说明 | 已处理 | WorkerProxy / ingest 边界已明确 Host dispatch context 提供 `attempt_id + execution_id` 校验，Engine 不拥有这些 Host 状态。 |
| 11 `GUIDANCE_INSERTED` 语义未定义 | 已处理到架构级 | 已补 event matrix 与 ToolRuntime governance hint 路径；具体 guidance policy 留到对应 phase。 |

## Finding 1 — EventLog sequence 语义未定义

- **严重程度**: blocking
- **位置**: §12 EventLog, "建议事件形态" 表, `sequence` 字段
- **当前写法**: "sequence 必须提供稳定排序。具体采用 global sequence、per-session sequence、per-run sequence 或组合，由 implementation phase 决定"
- **为什么有问题**: `sequence` 是 EventLog 的核心排序字段，直接影响：
  1. `stream_run_events(run_id, cursor)` 的 cursor 语义和补读逻辑
  2. EventLog 去重策略（event_id 去重 vs sequence 去重）
  3. SQLite schema 设计（索引、唯一约束）
  4. recovery scan 的事件排序
  5. Observer / Sink 的 checkpoint 语义

  将此决策推迟到 implementation phase，等于让 plan agent 自行决定 EventLog 的数据模型，这正是 implementation-control.md 明确禁止的。
- **影响**: plan agent 需要在 SQLite schema phase 自行选择 sequence 策略，可能导致 cursor 语义不一致、去重逻辑错误、或 recovery 行为不确定。
- **建议改法**: 在 §12 明确选择 sequence 策略。推荐：`global_sequence`（monotonic INTEGER）用于稳定排序和 cursor，`event_id`（UUID）用于去重。理由：`stream_run_events(run_id, cursor)` 需要跨 run 的稳定排序来支持 EventLog 补读；per-run sequence 无法表达跨 run 的全局追平语义。
- **是否阻塞**: 是。阻塞 SQLite schema phase 和 EventLog append / cursor 逻辑。

---

## Finding 2 — Host handle / context 未定义

- **严重程度**: blocking
- **位置**: §10 Host 公共接口
- **当前写法**: "公共函数接收明确的 Host handle / context 与 request，返回稳定 snapshot 或 event stream"
- **为什么有问题**: `host` 参数出现在所有公共接口签名中（`create_session(host, request)`、`start_run(host, request)` 等），但 design.md 从未定义：
  1. `host` 的类型或结构
  2. `host` 持有哪些依赖（durable store、ToolRuntime factory、EventLog、cancellation factory 等）
  3. `host` 的构造方式和生命周期
  4. 测试时如何构造 mock host

  这是所有公共接口的入口参数，也是依赖注入的核心。plan agent 必须自行设计 host 结构，否则无法写出可测试的实现。
- **影响**: 影响所有公共接口的实现、测试策略、依赖注入方式。如果 host 设计不当，可能导致 God object 或全局隐式单例。
- **建议改法**: 在 §10 或新增 §10.1 定义 Host handle 的最小结构：
  ```text
  HostHandle:
    durable_store: DurableStore          # SQLite
    event_log: EventLog                  # append-only
    tool_runtime_factory: ToolRuntimeFactory
    cancellation_factory: CancellationTokenFactory
    observer_bus: ObserverBus            # committed event notification
    config: HostConfig
  ```
  不需要定义每个组件的完整接口，但需要明确 host 持有哪些依赖以及它们的来源。
- **是否阻塞**: 是。阻塞所有公共接口的实现和测试设计。

---

## Finding 3 — RECOVERING 状态缺少退出转移

- **严重程度**: high
- **位置**: §6 Run 生命周期, §26 Host Lifecycle / Recovery
- **当前写法**: "RECOVERING：Host 已确认旧 Attempt 丢失，但用户请求和必要 canonical facts 仍可恢复；Host 正在或等待创建新 Attempt 继续同一 Run"
- **为什么有问题**: RECOVERING 被列为 active Run 状态（§8），但 design.md 未定义其退出转移：
  1. RECOVERING -> RUNNING：新 Attempt 创建成功
  2. RECOVERING -> FAILED：新 Attempt 创建失败（如 EngineWorker 不可用）
  3. RECOVERING -> LOST：recovery 超时或 policy 放弃
  4. RECOVERING 是否有超时？

  Section 26 描述了 recovery scan 的触发条件，但未描述 recovery 过程的完成条件。plan agent 需要自行设计 RECOVERING 的生命周期。
- **影响**: RECOVERING 可能成为"悬挂"状态，没有明确的超时或失败路径。在多进程环境下，如果 recovery 过程卡住，该 session 的 active slot 将被永久占用。
- **建议改法**: 在 §6 补充 RECOVERING 的退出转移规则：
  ```text
  RECOVERING -> RUNNING: new Attempt created and dispatched
  RECOVERING -> FAILED: new Attempt creation failed after retry limit
  RECOVERING -> LOST: recovery timeout or policy abandon
  ```
  并在 §26 补充 recovery timeout 语义（可由 implementation phase 决定具体值）。
- **是否阻塞**: 建议阻塞。如果不修正，plan agent 需要自行定义 RECOVERING 生命周期，可能导致 session slot 泄漏。

---

## Finding 4 — EventLog payload 建议形态标注为"建议"

- **严重程度**: medium
- **位置**: §12 EventLog, "建议事件形态"
- **当前写法**: "建议事件形态"
- **为什么有问题**: EventLog 的字段定义是 SQLite schema 的直接输入。使用"建议"一词暗示这不是最终设计，plan agent 可能需要调整。但实际上这些字段（event_id, session_id, run_id, attempt_id, execution_id, sequence, event_type, occurred_at, actor, source, request_id, policy_decision, reason, payload_json, payload_ref, payload_digest）已经是经过 discussion-note.md 和 design.md 两轮确认的设计。
- **影响**: plan agent 可能对是否需要调整 schema 产生困惑。
- **建议改法**: 将"建议事件形态"改为"EventLog 最小字段集"，明确这是 implementation 必须覆盖的字段。可以注明具体字段的类型和约束由 implementation phase 决定。
- **是否阻塞**: 不阻塞，但建议修正以消除歧义。

---

## Finding 5 — Durable queue 调度触发和优先级规则未定义

- **严重程度**: medium
- **位置**: §8 Admission 与多进程并发
- **当前写法**: "queue：当前 Session 有 active Run 时，输入进入 durable queue，成为后续 Run"；§26 "QUEUED Run 保持 QUEUED，等待调度"
- **为什么有问题**: design.md 定义了 queue 的入队语义，但未定义：
  1. 谁触发 queued run 的调度？（poll / event-driven / explicit scheduler）
  2. 调度优先级是什么？（FIFO / per-session FIFO / priority）
  3. 多进程环境下，谁负责调度？（所有进程竞争 / leader election / explicit scheduler process）
  4. 调度频率或延迟 SLA？

  implementation-control.md 的追踪区明确列出"durable queue 调度触发和优先级规则"为 design.md 生成时需规范化的事项。
- **影响**: plan agent 需要自行设计调度机制。如果设计不当，可能导致 queued run 饥饿或多个进程同时尝试调度同一个 queued run。
- **建议改法**: 在 §8 补充最小调度规则：
  ```text
  Durable queue 调度：
  - 触发点：active Run 终态提交后，Host 在同一事务或后续任务中检查同 session 的 QUEUED Run。
  - 优先级：per-session FIFO（同 session 内按 creation order）。
  - 多进程：依赖 SQLite CAS 保证同一 QUEUED Run 只被一个进程 promotion。
  - 不引入独立 scheduler 进程或 service。
  ```
- **是否阻塞**: 不阻塞，但建议补充。implementation phase 可以在此基础上细化。

---

## Finding 6 — recovery scan 触发条件和扫描范围未完整定义

- **严重程度**: medium
- **位置**: §26 Host Lifecycle / Recovery
- **当前写法**: 列出了 QUEUED / WAITING / RUNNING / CANCELLING Run 的恢复行为
- **为什么有问题**: implementation-control.md 的追踪区明确列出"Host startup recovery scan 触发条件和扫描范围"为 design.md 生成时需规范化的事项。当前 §26 描述了各状态的恢复行为，但缺少：
  1. scan 的触发条件：仅 Host 启动时？还是 periodic？
  2. scan 的范围：全表扫描？还是按状态过滤？
  3. scan 的性能边界：大量 QUEUED / WAITING Run 时的处理策略
  4. 多进程环境下，多个 Host 实例同时启动时的 scan 竞争
- **影响**: plan agent 需要自行设计 scan 策略。如果全表扫描，在大量历史 Run 时可能影响启动速度。
- **建议改法**: 在 §26 补充：
  ```text
  Recovery scan：
  - 触发：Host 启动时执行一次。
  - 范围：SELECT * FROM runs WHERE status IN (QUEUED, WAITING, RUNNING, CANCELLING, RECOVERING)。
  - 多进程：依赖 SQLite CAS 保证同一 Run 不被多个进程同时 recovery。
  - 不引入 periodic scan；运行期状态异常由各治理路径（cancel timeout, wait deadline）单独处理。
  ```
- **是否阻塞**: 不阻塞，但建议补充。

---

## Finding 7 — Observer / Sink dispatch 机制未定义

- **严重程度**: medium
- **位置**: §13 Observer / Sink / Projection
- **当前写法**: "committed event notification -> Observer / Sink dispatch"
- **为什么有问题**: design.md 定义了 Observer / Sink 的消费语义（幂等、不回滚 EventLog、checkpoint），但未定义 dispatch 机制：
  1. 通知是同步还是异步？
  2. 如果是异步，使用什么机制？（asyncio.Queue / callback / polling）
  3. 背压如何处理？（bounded queue / drop / block）
  4. Host 进程内还是跨进程？

  这影响 EventLog append 的延迟和 Sink 的可靠性。
- **影响**: plan agent 需要自行设计 dispatch 机制。如果设计不当，可能影响 EventLog append 性能或 Sink 可靠性。
- **建议改法**: 在 §13 补充最小 dispatch 语义：
  ```text
  Dispatch 机制：
  - EventLog append commit 后，Host 通过进程内 asyncio.Queue 通知注册的 Observer / Sink。
  - Queue bounded；满时丢弃通知，Sink 通过 checkpoint + poll EventLog 追平。
  - 不引入跨进程消息系统。
  - 第一版不引入重型消息系统；SQLite EventLog + projection checkpoint + 本地后台 worker / 任务循环足够表达可靠追平语义。
  ```
- **是否阻塞**: 不阻塞。design.md 已有"第一版不需要引入重型消息系统"的约束，implementation phase 可以在此基础上选择具体机制。

---

## Finding 8 — steer 与 terminal event 竞态的精确规则

- **严重程度**: medium
- **位置**: §11 Follow-up 与 Steer, discussion-note.md "Terminal / Cancel / Steer 竞态规则"
- **当前写法**: design.md §11 "steer 必须带 active run precondition。没有 active Run、目标 Run 不匹配、或当前 Run 已不可 steer 时，Host 拒绝 steer"
- **为什么有问题**: discussion-note.md 有明确的竞态规则："terminal 已提交后，steer 降级为普通 query / follow-up"、"如果当前 attempt 已接近终态，Host 需要定义 steer 与 terminal event 的竞态规则"。但 design.md §11 只说了"已不可 steer 时拒绝"，没有定义：
  1. "已不可 steer"的判定条件是什么？（Run 已有 terminal fact？Attempt 已有 terminal fact？）
  2. steer 请求到达时 Attempt 正在收口（terminal event 已 append 但 Run 状态未更新）的处理
  3. 拒绝 steer 时返回什么错误？（`invalid_state`？`conflict`？）
- **影响**: plan agent 需要自行定义竞态边界。如果定义不当，可能导致 steer 覆盖已提交的 terminal fact。
- **建议改法**: 在 §11 补充竞态规则：
  ```text
  Steer 竞态规则：
  - Run 已有 terminal fact（SUCCEEDED / FAILED / CANCELLED / LOST）时，steer 拒绝，返回 invalid_state。
  - Attempt 正在收口（terminal event 已 append 但 Run 状态未更新）时，steer 等待 Run 状态更新后判断。
  - steer 拒绝不创建新 Run；caller 按普通 start_run 处理。
  ```
- **是否阻塞**: 不阻塞。竞态规则在 discussion-note.md 中已有讨论，design.md 可以直接规范化。

---

## Finding 9 — `submit_followup` 返回类型 `FollowupSnapshot` 未定义

- **严重程度**: low
- **位置**: §10 Host 公共接口
- **当前写法**: `submit_followup(host, session_id, request) -> FollowupSnapshot`
- **为什么有问题**: `FollowupSnapshot` 在整个 design.md 中只出现一次，未定义其字段。`SessionSnapshot`、`RunSnapshot` 也未定义，但它们的语义可以从名字推断。`FollowupSnapshot` 的语义不明确：它是返回新创建的 Run？还是返回排队状态？还是返回 active Run？
- **影响**: plan agent 需要自行定义 FollowupSnapshot。如果定义不当，可能导致 API 语义不一致。
- **建议改法**: 在 §10 补充 FollowupSnapshot 的语义：
  ```text
  FollowupSnapshot:
    mode: queued | started | steered
    run_id: str              # queued 或 started 的 run_id
    active_run_id?: str      # steer 模式下的 active run_id
  ```
  或者直接改为返回 `RunSnapshot`，简化接口。
- **是否阻塞**: 不阻塞。

---

## Finding 10 — EngineEvent 缺少 `attempt_id` / `execution_id` 的对齐说明

- **严重程度**: low
- **位置**: §12.3 EngineEvent 映射, 与现有 `dayu/engine/contracts/engine_events.py` 的对齐
- **当前写法**: EventLog 建议形态包含 `attempt_id` 和 `execution_id`，但现有 `EngineEvent` 只有 `session_id` 和 `run_id`
- **为什么有问题**: design.md 定义了 Host 在 ingest 时校验 `attempt_id + execution_id`（§16），但未明确说明 `attempt_id` 和 `execution_id` 从哪里来。现有 `EngineEvent` 不包含这些字段。plan agent 需要理解：Host 在 dispatch Attempt 时已经知道 `attempt_id` 和 `execution_id`，ingest 时通过 dispatch context 关联，而非从 `EngineEvent` 中提取。
- **影响**: 不影响设计正确性，但可能导致 plan agent 对 ingest 逻辑产生困惑。
- **建议改法**: 在 §16 或 §12.3 补充一句说明："Host ingest 通过 dispatch context（attempt_id, execution_id）关联 EngineEvent，不依赖 EngineEvent 自身携带这些字段。"
- **是否阻塞**: 不阻塞。

---

## Finding 11 — `GUIDANCE_INSERTED` 事件语义未定义

- **严重程度**: low
- **位置**: §12.2 Canonical Event 最小集合
- **当前写法**: `GUIDANCE_INSERTED` 出现在事件列表中
- **为什么有问题**: discussion-note.md 有"Run-time Guidance 讨论入口"章节，但 design.md 只在事件列表中列出了 `GUIDANCE_INSERTED`，未定义其触发条件、payload、与 `CONTEXT_COMPACTION_REQUESTED` 的关系。plan agent 需要自行设计 guidance 的 EventLog 表达。
- **影响**: 不影响核心治理，但 guidance 是 Host 控制模型行为的重要机制。
- **建议改法**: 在 §12.2 或新增 §12.4 补充 `GUIDANCE_INSERTED` 的最小语义：
  ```text
  GUIDANCE_INSERTED:
    - 触发：Host / ToolRuntime 在工具结果被接受后，根据治理策略插入引导消息
    - payload：{ guidance_type, content, trigger_tool_call_id, reason }
    - 约束：guidance 不是 verified fact，不进入 memory stable layer
  ```
- **是否阻塞**: 不阻塞。guidance 的 EventLog 表达可以在 guidance phase 详细设计。

---

## Engine 兼容性验证

与现有 Engine contracts 的对齐情况：

| 设计要求 | Engine 现状 | 对齐状态 |
|---|---|---|
| Engine 不拥有 Session / Run 生命周期 | `run_agent_messages` / `run_agent_and_wait` 是 run-scoped 函数 | 对齐 |
| Engine 只消费 ToolExecutor protocol | `AgentRunRequest.tool_executor: ToolExecutor` | 对齐 |
| Engine 只观察 CancellationToken | `AgentRunRequest.cancellation_token: CancellationToken` (read-only Protocol) | 对齐 |
| Engine 不理解 Host 状态 / memory / steer | Engine 无 Host 相关 import | 对齐 |
| EngineEvent 终态类型 | `FINAL_ANSWER / RUN_FAILED / RUN_CANCELLED / RUN_SUSPENDED` | 对齐 |
| 工具等待路径 | `ToolAwaitingOutcome -> tool_awaiting -> run_suspended` | 对齐 |
| AgentRunRequest 包含 session_id / run_id | `AgentRunRequest.session_id / run_id` | 对齐 |
| fetch_more 走普通 ToolExecutor | design 要求 fetch_more 作为普通 @tool 注册 | 待实现（无冲突） |

---

## 剩余风险

1. **SQLite schema 细节**：design.md 定义了事务不变量和 CAS-style 转移，但未给出 schema 骨架。这是有意为之（留给 implementation phase），但 plan agent 需要将不变量转化为具体 schema。风险可控，前提是 blocking findings 中的 sequence 语义已修正。

2. **Memory projection 触发频率**：design.md 说 memory projection 只消费 canonical facts，但未定义触发频率（每个 terminal event？每个 canonical fact？periodic？）。implementation phase 需要定义。

3. **Token estimator 精度**：design.md 说 token estimator 只能作为 Host 预算治理估算。在没有 provider tokenizer adapter 的情况下，预算分配可能不准确。风险可控，因为 design.md 已明确这是估算。

4. **多进程 SQLite 并发**：design.md 说使用 WAL + busy timeout，但未定义具体的 busy timeout 值和重试策略。implementation phase 需要结合测试确定。

---

## 结论

design.md 整体质量高，覆盖了 Host 治理的核心面。修正 Finding 1（EventLog sequence 语义）和 Finding 2（Host handle 结构）后，可作为 plan 真源进入 phase 编排。Finding 3（RECOVERING 退出转移）建议同步修正，避免 session slot 泄漏风险。其余 findings 可在对应 phase discussion 中解决。

**建议进入 phase 编排的条件**：
1. 修正 Finding 1 和 Finding 2
2. 建议修正 Finding 3
3. 其余 findings 记录为 implementation-control.md 追踪区的 working assumption
