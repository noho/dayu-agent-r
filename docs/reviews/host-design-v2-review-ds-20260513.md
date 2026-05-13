# Host Design v2 Review — AgentDS

## 元信息

- **Review persona**: AgentDS (分布式系统、本地多进程一致性、SQLite durable truth、EventLog、状态机、幂等、恢复、Remote semantic contract、Outbox/Sink 边界与 failure semantics)
- **Review target**:
  - `docs/host/design.md` (v2, 架构真源)
  - `dayu/README.md` (术语真源)
- **参考**: `docs/host/implementation-control.md` (仅确认 gate 状态与流程约束)
- **日期**: 2026-05-13
- **Gate**: draft design v2 review

## 结论

Design v2 在分布式一致性、状态机、EventLog 真源、幂等、恢复语义和远程执行边界方面达到了较高的设计完整性。核心架构决策（SQLite + WAL + CAS、append-only EventLog、execution_id 拒绝迟到事件、新 Attempt 语义、Outbox 与 EventLog 分离、ToolRuntime accept barrier）自洽且可行。

存在 **0 个 blocker**。发现 4 个 high findings、4 个 medium findings、3 个 low findings。所有 findings 均为规格细化不足或语义缺口，可在 phase discussion/plan 阶段解决，不构成架构级阻断。

## Findings

### High

#### H1. Wait record adapter recovery bootstrap 未定义

- **证据**: `design.md` Section 26 Recovery scan 规定 `WAITING` Run 保持 `WAITING`，"只恢复 wait adapter observation"；Section 19 定义 `resume_policy: callback | poll | manual`，但未指定 Host 重启后如何根据 wait record 恢复正确的 adapter。
- **问题**: wait record 携带 `resume_policy` 字段，但 adapter 实现与 wait record 类型的绑定关系未被定义。Host 重启时，background runtime supervisor 中的 wait poller 如何知道哪个 adapter 负责哪个 wait record？如果 poll adapter 依赖进程内状态（如 HTTP client session、认证 token），重启后如何重建？
- **影响**: Tool Awaiting / Wait Adapter phase 的 implementation agent 可能自行猜测 adapter 注册与恢复机制，导致 adapter 与 Host 生命周期耦合不当。
- **建议**: 在 design.md Section 19 或 Section 26 中明确 adapter registry/lookup 的最小语义，以及 adapter 初始化所需的最小 durable state（如 `await_spec` 中应包含足以重建 adapter 连接的 ref）。

#### H2. Memory projection 的 atomic commit marker 未定义

- **证据**: `design.md` Section 23 要求 "memory snapshot 与 projection checkpoint 必须同事务提交，或使用等价的 atomic commit marker"；Section 9 要求 "projection checkpoint 不得先于对应 projection 持久化结果提交"。
- **问题**: 若 memory projection 存储在 SQLite EventLog 数据库之外（如独立文件、独立 SQLite），则无法与 EventLog transaction 共享同一 SQLite 事务。"等价 atomic commit marker" 的具体语义未定义——是两阶段提交？是 write-ahead marker？是 commit timestamp 对齐？如果 marker 机制不可靠，可能出现 checkpoint 已推进但 snapshot 未持久化的窗口，导致 RunInputBuilder 消费到不完整或过期的 memory snapshot。
- **影响**: Memory projection phase 的实现可能选择不可靠的 "先写 snapshot 再写 checkpoint" 顺序（或相反），在 crash 时产生不一致。
- **建议**: 在 design.md Section 23 中明确 atomic commit marker 的最小契约（如 "checkpoint 必须在 snapshot 持久化并 fsync 后才能更新，且 checkpoint 更新失败时必须能通过 EventLog replay 重建 snapshot"），或明确第一版将 memory projection 放在与 EventLog 相同的 SQLite database 中。

#### H3. Tool fact accept barrier 的 ack 丢失语义有歧义

- **证据**: `design.md` Section 17 规定 ToolRuntime 必须等待 Host accept ack 后才能将 tool result 返回给 Engine；"若 ack rejected 或 timeout，ToolRuntime 不得把对应工具结果返回给 Engine；它必须返回受治理的工具错误、awaiting / suspend，或让 Host policy 将 Attempt 收口为 failed / recoverable"。
- **问题**: 在 RemoteProxy 场景下，可能出现 Host 已 durable accept tool fact 并 commit，但 ack 响应在网络中丢失。此时 ToolRuntime 按 timeout 处理，将 tool result 报告为错误，而 Host EventLog 中已有该 tool fact。这导致：
  - 工具事实已在真源中存在但 Engine 认为工具执行失败。
  - Resume/replay 时 RunInputBuilder 从 EventLog 重建 messages 会包含该 tool result，但当前 Attempt 的模型上下文不包含。
  - ToolRuntime 是否应重试 accept 请求？如果是，幂等键是什么？设计未明确 accept 请求的幂等模型。
- **影响**: RemoteProxy 实现的 agent 可能自行设计 ack retry 或 timeout 策略，与 Host 幂等语义不一致。
- **建议**: 在 Section 17 中明确 accept 请求的幂等键（建议由 `execution_id + tool_call_id + result_digest` 派生），以及 ToolRuntime 在 ack timeout 时应重试 accept（而非直接返回错误），重试由 Host 幂等保证安全。

#### H4. "可确认控制" 的 dispatch record 判断标准缺失

- **证据**: `design.md` Section 26 Recovery scan 规定：若 active Attempt "不存在当前 Host 可确认控制的 dispatch record"，旧 Attempt → `LOST`。dispatch record 字段包含 `host_instance_id`、`connection_state?`，但 `host_instance_id` 被明确说明 "不是 lease、不是 fencing token"。
- **问题**: Recovery scan 需要判断 dispatch record 是否仍可被当前进程确认控制，但判断标准未定义。对于 LocalProxy，可能检查子进程是否存活；对于 RemoteProxy，可能检查连接状态。`connection_state?` 字段是可选的，且其语义未定义。如果判断逻辑不精确，可能导致：
  - 误将仍可控制的 Attempt 标记为 `LOST`（过于激进）。
  - 误将已不可控的 Attempt 保留为 `RUNNING`（过于保守，阻塞 Session active slot）。
- **影响**: Recovery phase 的实现 agent 需要自行定义判断标准，可能与设计意图偏离。
- **建议**: 在 Section 26 或 dispatch record 定义处明确判断标准的最小契约：至少包括 worker_kind 的分支逻辑，以及 `connection_state` 的取值和含义。

### Medium

#### M1. Proactive context compaction 的迭代终止条件未定义

- **证据**: `design.md` Section 24.1 proactive trigger 描述为 "Host/RunInputBuilder 在 dispatch Attempt 前根据 provider-aware budget 判断...". 实际路径是 RunInputBuilder 构建 messages → budget check → 若超阈值则 compact → 重新构建 messages。
- **问题**: 若 compaction 后 messages 仍超过 budget threshold（例如 pinned_state 本身就很大），可能进入无限 compact-retry 循环。设计未定义最大 compact 次数、降级策略（如强制丢弃 history pool、仅保留 system + pinned_state + 当前 input）、或失败收口。
- **建议**: 在 Section 24.1 中明确 compact 迭代的上限与降级策略，或明确 `CONTEXT_COMPACTION_FAILED` 可在此场景触发，Run 进入 `FAILED`。

#### M2. Replay Run 的工具调用约束不可执行

- **证据**: `design.md` Section 20 规定 "replay messages 必须约束模型只做结构修复，不引入新事实，不调用工具，不改变 evidence anchors"。
- **问题**: 该约束通过 system messages 实现，但 LLM 可能仍然 emit tool calls。设计未定义 Host 在 replay Attempt 中收到 tool call 时的行为——是拒绝并 hard_stop？是映射为 TOOL_CALL_GOVERNED + hard_stop？是允许只读工具？
- **建议**: 在 Section 20 或 ToolRuntime Section 17 中明确 replay Attempt 中工具调用的治理策略（建议默认 hard_stop，并 append GUIDANCE_INSERTED 提醒模型约束）。

#### M3. Sink 幂等消费要求未显式声明为必须

- **证据**: `design.md` Section 13 规定 Sink 必须 "按 canonical event_id 幂等消费"，但未将其列为 Sink 的基础契约要求。
- **问题**: Sink checkpoint 可能与 Sink 实际处理状态不一致（如 checkpoint 更新后 crash，重放时 Sink 部分处理了某些事件）。目前设计依赖 "按 event_id 幂等消费"，但没有显式声明：所有 Sink 的实现必须满足幂等消费，否则 checkpoint 恢复后会产生重复副作用（如 outbox 重复投递）。
- **建议**: 在 Section 13 Sink semantic contract 中显式声明 "每个 Sink 必须是幂等消费者：重复消费同一 canonical event_id 不得产生重复副作用或违反投递语义"。

#### M4. Session close 与 active Run 的交互未定义

- **证据**: `design.md` Section 4 规定 `close_session` 将 Session 标为 `CLOSED`，"已有 Run 不因 close 被删除或改写"。Section 5 Session 状态只有 `OPEN` 和 `CLOSED`。
- **问题**: 若 Session 有 active Run（`RUNNING`/`WAITING`/`CANCELLING`/`RECOVERING`）时调用 `close_session`：
  - active Run 是否继续执行到终态？
  - Recovery scan 是否仍能为 `RECOVERING` Run 创建新 Attempt？
  - 新的 queue promotion 是否仍发生？
  - 设计没有明确说明 `CLOSED` 对 active Run 治理路径的影响范围。
- **建议**: 在 Section 4 中明确 `CLOSED` Session 下 active Run、queue promotion、recovery 和 steer 的行为。

### Low

#### L1. Payload digest 规范化算法未指定

- **证据**: `design.md` Section 12.1 要求 digest 基于 "确定性序列化 / canonicalization 计算".
- **问题**: 未指定具体算法（如 JSON Canonicalization Scheme RFC 8785、sorted-key JSON、或其他）。工具事实的 digest 用于幂等和去重，算法选择影响跨语言/跨版本兼容性。
- **建议**: 在 phase plan 中选定算法并写入 design.md 或实现规范。

#### L2. RunSnapshot 缺少 source_run_id / replay_of_run_id

- **证据**: `design.md` Section 10 定义 `RunSnapshot` 包含 `run_id`、`session_id`、status、current attempt、terminal result summary、event_sequence cursor、outbox status summary。
- **问题**: `retry_run` 和 `replay_run` 创建关联的新 Run，但 RunSnapshot 未包含与源 Run 的关联字段（`source_run_id` 或 `replay_of_run_id`）。Session timeline 需要展示 retry/replay 链，调用方也需要追踪新 Run 的溯源。
- **建议**: 在 RunSnapshot 中增加可选的 `source_run_id` 和 `source_run_relation` 字段。

#### L3. Tool trace 冷热分离边界不精确

- **证据**: `design.md` Section 13.1 描述热数据包含 "tool_call_id、tool name、normalized args digest、result digest、evidence anchors、truncate info、await info、policy decision、error code、duration、attempt refs"，冷数据包含 "长参数摘要、长结果摘要、provider / tool raw diagnostic refs...".
- **问题**: "长"的阈值（多少字节/字符算长）未定义；`truncate info` 放在热数据中，但 `截断诊断` 放在冷数据中——二者的边界模糊。实现 agent 可能将过多数据放入热存储导致热查询性能下降。
- **建议**: 在 tool trace phase plan 中明确冷热分离的 size threshold 或字段边界规则。

## Over-coupling / Overengineering Check

**结论: 未发现显著的过度耦合或过度工程化。**

- 分层边界（UI → Service → Host → Engine）清晰，反向依赖被显式禁止且有具体例子。
- Host 内部模块边界（Public API、Admission、EventLog、Dispatch、Ingest、RunInputBuilder、Context Governance、ToolRuntime、Observer/Sink、Recovery）各有明确 ownership，不互相绕过。
- ToolRuntime 的 8 个 port 拆分是合理的关注点分离，不是过度工程化。但实现时需警惕这些 port 不要退化为一个 god object 的不同方法。
- 第一版 non-goals（无重型消息系统、无重 lease/fencing、无长期 memory public API）是务实的范围控制。
- Context Governance 定位为 orchestrator 而非 god object，通过 typed ports 调用 compactor、budget estimator、RunInputBuilder——这是正确的解耦设计。
- `HostPolicyProviderSet` 的设计（typed providers → typed policy views → subsystems）避免了 service locator 反模式。

**需关注的潜在耦合点**:
- ToolRuntime 同时持有 tool registry、dispatcher、policy、truncation、awaiting、duplicate governance、accept、trace 8 个 port。实现时建议每个 port 有独立 interface/class，ToolRuntime 只做 composition root，避免成为一个大而全的 god object。
- RunInputBuilder 依赖 7 个 typed input provider，需确保每个 provider 的 contract 足够窄，避免 RunInputBuilder 成为事实上的 integration god。

## Phase-readiness Verdict

**可通过，可进入 phase 编排。**

Design v2 具备进入 phase 编排的条件：
- 核心架构决策自洽：SQLite + WAL + CAS 实现本地多进程一致性；append-only EventLog 作为治理真源；execution_id 拒绝迟到事件；新 Attempt 永不 takeover 旧 Attempt。
- 状态机（Session/Run/Attempt）完整：状态集合、终态、迁移表、竞态规则均已定义。
- 幂等语义逐操作定义（ensure_session、create_session、start_run、cancel_run、retry_run、replay_run、resolve_wait）。
- Remote semantic contract 明确：远端不拥有 Host 状态、不 append EventLog、不关闭 Attempt、不更新 Run。
- EventLog → Observer/Sink → Outbox 的派生链完整，Sink 失败不回滚 EventLog。
- 4 个 high findings 均可在对应 phase discussion 中解决，不阻断 phase 编排本身。

## Residual Risks

1. **SQLite 多进程写入竞争的实际表现**: 设计依赖 SQLite WAL + busy timeout + 显式重试。在写入密集场景（多客户端同时 start_run 到不同 Session），SQLite 的单写入者模型可能成为瓶颈。当前设计不引入重 lease/fencing 是正确的，但需要在 Host storage policy phase 中定义 busy timeout 与重试策略的具体参数，并以多进程并发测试验证。

2. **Remote worker 孤儿执行**: 设计承认 Host 不保证 exactly-once 远程物理执行，依赖 execution_id 拒绝迟到事件。在 RemoteProxy 场景下，dispatch 后 Host crash，远端 worker 可能继续执行并产生外部副作用（如付费 API 调用）。工具级幂等性是缓解措施，但不是所有工具都具备。这个风险是第一版明确接受的 tradeoff（Section 27 non-goals 包括"强制终止远程执行环境和复杂 job reconcile"），但需在 RemoteProxy phase 的测试设计中覆盖此场景。

3. **EventLog 无限增长的存储压力**: append-only EventLog 没有定义 retention/archival 策略。对于长期运行的 Session，EventLog 会持续增长。虽然 preview/diagnostic events 可以降级丢失，但 canonical_fact 不能删除。需要在后续 phase 中考虑 EventLog archiving 或 partition 策略。

4. **跨层测试的复杂性**: Host 的治理路径涉及 durable transaction → dispatch → remote execution → event ingest → terminal transaction 的完整链路。端到端测试需要模拟 crash、网络分区、超时等场景。每个 phase 的测试设计需要明确定义 mock/fake 边界和集成测试范围。
