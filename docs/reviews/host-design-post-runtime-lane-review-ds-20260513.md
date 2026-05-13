# Host Design Post-Runtime-Lane Readiness Review

- 日期：2026-05-13
- 评审范围：`docs/host/design.md`、`docs/host/implementation-control.md`
- 术语真源：`dayu/README.md`
- 评审阶段：draft design v2 精化后，进入 phase 编排前的最终架构设计评审
- 前置评审：`docs/reviews/host-design-final-readiness-controller-adjudication-20260513.md`（已裁决，P0 全部关闭）

---

## 总体评估

当前 design.md v2 精化后，架构边界、状态机、EventLog、admission、cancel、recovery、remote execution、ToolRuntime accept barrier 的核心语义已经稳固。上一轮最终就绪评审的 22 条裁决项（A1–A23）已写回 design.md，关键矛盾已消除。

本轮评审发现 **0 个 P0**、**5 个 P1**、**6 个 P2**。P1 集中在状态机边界 case 的精确性、幂等原子性边界和 no-tool replay 的执行机制归属；P2 主要是契约精化与实现粒度问题。

所有 P1 均可在对应 phase 的 discussion 阶段解决，不需要回退 architecture 重写。

---

## Findings

### P0 — 阻塞项

无。

---

### P1 — 高优先级，必须在对应 phase plan 前澄清

#### P1-1. `CONTEXT_COMPACTION_REQUESTED` 的 `attempt_id`/`execution_id` optional 与 reactive path 校验要求矛盾

- **文件/章节**：`design.md` §13.3 Canonical Event Contract Matrix 行 `CONTEXT_COMPACTION_REQUESTED` 标记 `attempt_id?`、`execution_id?`；§25.1 规定 reactive path "Host 必须先按 `attempt_id + execution_id` 校验 `context_compaction_requested` 是否来自当前 active Attempt"。
- **问题**：proactive trigger（Host 在 dispatch 前判定超预算）确实没有 active Attempt 上下文，此时 `attempt_id`/`execution_id` 为空是合理的。但 reactive trigger（Engine 回报 context_length_exceeded）必须有这两个字段才能做来源校验。当前 schema 用 optional 统一两种场景，未在 event contract 中区分，可能导致实现时 reactive path 收到空字段无法校验、或 proactive path 被误填无效值。
- **影响**：若 reactive path 收到不带 attempt_id 的 compaction_requested，Host 无法确认事件来自当前 active Attempt，可能对已终态 Attempt 的迟到事件误触发 compact recovery。
- **建议修正**：
  1. 在 §13.3 的 contract matrix 中将 `CONTEXT_COMPACTION_REQUESTED` 拆为两条规则：proactive trigger 场景下 `attempt_id`/`execution_id` 可为空，reactive trigger 场景下为 required。
  2. 或在 event payload 中增加 `trigger_source: proactive | reactive` 字段，并在 contract 中显式写：`trigger_source=reactive` 时 `attempt_id`/`execution_id` 必须非空且可校验。
  3. §25.1 的 reactive path 校验逻辑应显式引用该字段。

#### P1-2. `cancel_run`/`cancel_session_runs` 对 `RECOVERING` 状态 Run 的路径有语义漏洞

- **文件/章节**：`design.md` §9.1 状态迁移表将 `cancel_run` on active 的前置状态列为 `RUNNING / CANCELLING / RECOVERING`，路径统一为 `Run CANCELLING` → 等待 Attempt 收口 → `CANCELLED`。§22 的 `cancel_session_runs` 也将 `RECOVERING` 列入作用范围。
- **问题**：`RECOVERING` 的定义是"Host 已确认旧 Attempt 丢失，但用户请求和必要 canonical facts 仍可恢复；Host 正在或等待创建新 Attempt"。在此状态下，旧 Attempt 已通过 positive orphan proof 标为 `LOST`，新 Attempt 尚未创建。没有 active Attempt 需要等待收口。走 `CANCELLING`（表示"等待 active Attempt 收口或超时升级"）是一个语义空转——没有东西可以 cancel，也没有东西需要等待。
- **影响**：实现可能为 cancel RECOVERING Run 创建一个假性 CANCELLING 中间态，然后因为"没有 active Attempt 可 cancel"而卡住或超时升级。正确的路径应该是 `RECOVERING → CANCELLED` 直通，不经过 `CANCELLING`。
- **建议修正**：
  1. §9.1 状态迁移表应将 `RECOVERING` 从"active cancel"组中拆出，单独一行：`cancel_run` on `RECOVERING` → 直接 `CANCELLED`，append `CANCEL_REQUESTED` + `RUN_CANCELLED`，不创建 Attempt，不进入 `CANCELLING`。
  2. 若 recovery 已 dispatch（新 Attempt 已创建为 `STARTING`），则 Run 状态应先变为 `RUNNING`，cancel 走正常 active cancel 路径——但这要求在 recovery dispatch 事务中把 Run 从 `RECOVERING` 推进到 `RUNNING`。当前 §9.1 的 recovery dispatch 行写的是 `RECOVERING → RUNNING`，确认语义一致。
  3. §22 的 cancel_session_runs 对 RECOVERING 的描述也应拆为"尚未 dispatch 时直接 CANCELLED，已 dispatch 时走普通 active cancel"。

#### P1-3. `replay_run` 的 no-tool 约束在 RunInputBuilder 与 ToolRuntime 两个层面的责任归属不明确

- **文件/章节**：`design.md` §21 规定 replay 是 no-tool 结构修复，"RunInputBuilder 构造 no-tool `AgentRunRequest.messages`"，同时规定"如果 replay 执行期间模型仍发起 tool call，Host / ToolRuntime 必须按 replay policy 拒绝"。
- **问题**：两个机制同时存在但主路径不明确：
  - 如果 RunInputBuilder 从 effective `ToolBundle` 中排除了所有 tool schema（不向 Engine 暴露任何 tool），模型理论不会发起 tool call——这是主防线。
  - 如果 RunInputBuilder 仍暴露了 tool schema（例如为了某种诊断或其他原因），ToolRuntime 的"拒绝"是第二道防线。
  - 两道防线的失败模式不同：前者是 Engine 收到的 `AgentRunRequest` 不含 tools，模型 tool_call 会在 Engine/Runner 层失败；后者是 Engine 正常发出 tool_call，ToolRuntime 在执行时拦截。
  - 当前文本没有明确主路径，phase plan agent 可能实现其中之一或两者，导致行为不一致。
- **影响**：如果在 replay 中模型仍然发起 tool call 且 ToolRuntime 未正确拦截，可能导致 replay 越权执行工具、污染 evidence anchor。
- **建议修正**：
  1. §21 明确：主防线是 RunInputBuilder 为 replay Attempt 构造的 `AgentRunRequest` 不含 tool schemas（effective ToolBundle 对 replay 为空的 tool schema 列表）。ToolRuntime 层面的拒绝只是 defense-in-depth。
  2. §18.2 的 ToolRuntime boundary 应增加 replay policy 的 tool call rejection 作为明确的 port 行为。
  3. 或者反过来明确：replay 的 `AgentRunRequest` 仍携带 tool schemas（供模型理解上下文），但 ToolRuntime 的 replay policy interceptor 在 tool dispatch 前拦截——如果选这条路，需说明为什么保留 tool schemas。

#### P1-4. `resolve_wait` 幂等返回的范围定义不够精确，与 resume chain 的原子性边界存在歧义

- **文件/章节**：`design.md` §20 规定 `resolve_wait` 幂等范围为 `(wait_id, idempotency_key)`，"同一幂等键 + 同一 outcome 重试时，Host 返回既有 accepted resolution result，不追加第二份 canonical fact"。
- **问题**：`resolve_wait` 的完整路径包括：append `RESUME_REQUESTED` → append tool terminal/result fact → append `RUN_STARTED(start_reason=resume)` → create Attempt → append `ATTEMPT_STARTED` → commit。当前文本的"既有 accepted resolution result"未明确这个范围：
  - 仅指 wait record 的状态和 tool terminal/result fact 的 accepted ack？
  - 还是包括整条 resume chain（RESUME_REQUESTED + RUN_STARTED + ATTEMPT_STARTED）？
  - 如果首次 `resolve_wait` 成功 append 了 `RESUME_REQUESTED` 和 tool result，但 commit 前崩溃，重试时是幂等返回 tool result accepted ack 后继续创建新 Attempt，还是因为 wait record 已 resolved 而拒绝？
  - §20 规定"已 `resolved` 的 wait record 只允许幂等重放既有结果，不允许第二次 resolution"——但如果首次 resolution 的事务实际上没有 commit，durable store 中 wait record 仍是 `waiting`，重试应该被接受。
- **影响**：崩溃恢复场景下，如果幂等语义过于激进（认为已 resolved），可能丢失 resume；如果过于宽松（允许重复 resolution），可能创建重复 Attempt。
- **建议修正**：
  1. §20 显式定义 `resolve_wait` 的幂等返回包含什么：wait record resolution + tool terminal/result fact 的 canonical event refs。如果首次调用只完成了部分事务（未 commit），重试应完整重放。
  2. wait record 的 `resolved` 状态变更、`RESUME_REQUESTED`、tool result fact、`RUN_STARTED`、Attempt 创建和 `ATTEMPT_STARTED` 必须在同一事务或等价原子流程中收口（§20 已有此要求，但需强调"幂等重试的观察对象是 committed state"）。
  3. 在 Wait/Resume phase 的测试要求中增加：`resolve_wait` 事务提交前崩溃 → 重试 → 完整 resume chain 只产生一份 canonical facts。

#### P1-5. `close_session` 与 `RECOVERING` Run 的交互缺失

- **文件/章节**：`design.md` §5 Session 生命周期列出 CLOSED Session 下允许的操作包括 `cancel_run`、`resolve_wait`、`get_session`、`get_run`、`stream_run_events`，并规定"close 前已 durable accepted 的 QUEUED Run 继续保留，并可在 active slot 释放后 promotion"。但未提及 `RECOVERING` Run。
- **问题**：`RECOVERING` Run 是在 close 前已经 durable accepted 的工作（`USER_INPUT_ACCEPTED` 已提交，旧 Attempt 已 LOST）。按照"close 不等于 cancel"的原则，Host recovery scan 或在 close 前已启动的 recovery dispatch 是否应在 Session CLOSED 后继续完成？
  - 如果 recovery dispatch 在 close 后触发，相当于在已关闭的 Session 中创建新 Attempt、启动新执行——这与 `CLOSED` Session "只读"的直观语义有张力，但与"close 不取消已有工作"的原则一致。
  - 当前 §5 未将 RECOVERING 列入允许继续的 Run 状态。
- **影响**：模糊性可能导致实现时错误地阻止 RECOVERING Run 的恢复 dispatch，或错误地允许。
- **建议修正**：
  1. §5 在 CLOSED Session 允许操作列表中增加 `RECOVERING` 状态：Hos recovery scan 或已在进行的 recovery dispatch 不得因 Session CLOSED 而中断；recovery dispatch 创建新 Attempt 是"close 前已接受工作的继续"，符合 close 不等于 cancel 的原则。
  2. 或者在 §5 增加一条总则：close 前已 durable accepted 的非终态 Run（QUEUED、WAITING、RECOVERING）的后续 promotion / resume / recovery dispatch 不受 close 影响；close 只阻止新的 `start_run` 和 `submit_followup`。

---

### P2 — 中低优先级，建议在对应 phase discussion 中精化

#### P2-1. `GUIDANCE_INSERTED` 进入 messages 的判定条件过于模糊

- **文件/章节**：`design.md` §13.2 Canonical Event 最小集合列出 `GUIDANCE_INSERTED`；§23 RunInputBuilder 规定"`GUIDANCE_INSERTED`，如果影响后续 iteration"应进入 messages。
- **问题**："如果影响后续 iteration"不是一个可实现的判定规则。Guidance 是否影响后续 iteration 取决于其内容——但由谁判断？RunInputBuilder 不理解 guidance 语义；ToolRuntime/DuplicateGovernance 知道为什么插入 guidance 但不知道 RunInputBuilder 的 messages 构造逻辑。
- **建议修正**：在 §13.3 的 contract matrix 中为 `GUIDANCE_INSERTED` 增加 `affects_messages: bool` 字段，由插入方（ToolRuntime policy decision port）在 append 时显式标记。RunInputBuilder 根据该字段决定是否纳入 messages，不做语义推断。

#### P2-2. Recovery scan 处理多种非终态 Run 的顺序未定义

- **文件/章节**：`design.md` §27 Recovery scan 描述了各类 Run 的恢复行为，但未定义处理顺序。
- **问题**：QUEUED promotion、WAITING adapter recovery、RECOVERING dispatch 都会竞争 Session active slot。如果 recovery scan 先处理 RECOVERING dispatch 占据 active slot，同 Session 的 QUEUED Run 就无法 promotion。反之亦然。处理顺序影响用户可感知的响应顺序。
- **建议修正**：§27 增加处理顺序规则。推荐：先处理 RECOVERING Run（因为用户已经在等待答案），再处理 WAITING adapter recovery，最后 promotion QUEUED Run。或者明确"恢复阶段不 promotion，等 recovery scan 全部完成后统一 promotion"。

#### P2-3. Canonical event 的 `payload_json` vs `payload_ref` 缺少 event type 级别的选择规则

- **文件/章节**：`design.md` §13 EventLog 事件形态同时包含 `payload_json` 和 `payload_ref?` 字段；§13.1 Payload 存储描述了按大小阈值的存储策略，但未定义 EventLog row 层面哪个字段承载数据。
- **问题**：对于小型 payload，是放入 `payload_json`（inline）还是 `payload_ref`（外移但仍在 SQLite payload table）？两者都在 SQLite 内，选择标准不明确。对于必须外移（超过阈值）的 payload，`payload_json` 是否应该留空还是放 summary？
- **建议修正**：§13.1 增加规则：canonical event 的 `payload_json` 承载治理必需的 typed 字段（状态机、幂等、恢复所需），`payload_ref` 指向外移的大块数据（工具结果正文、长文本等）。或者干脆合并为一种方案：EventLog row 只存 ref + digest，payload 一律走 payload table / artifact。

#### P2-4. `HostPolicyProviderSet` 的 typed views 只有名字，缺少最小字段契约

- **文件/章节**：`design.md` §10.1 列出了 `AdmissionPolicyView`、`WorkerSelectionPolicyView`、`ToolGovernancePolicyView`、`ContextBudgetPolicyView`、`OutboxPolicyView` 等 typed policy view 的名字，但未定义每个 view 的最小字段或方法契约。
- **问题**：phase plan agent 在 Storage/Policy phase 需要自行发明每个 view 的字段——这增加了不同 phase agent 之间契约不一致的风险。
- **建议修正**：在 §10.1 或独立 policy 章节中为每个 policy view 给出最小必要字段。不需要穷举所有参数，但需要给出该 view 要回答的问题（例如 `AdmissionPolicyView` 回答"有 active Run 时新输入是 queue/reject/attach_active"）和最小输出类型。

#### P2-5. Tool fact accept idempotency key 的派生算法留白

- **文件/章节**：`design.md` §17 规定 accept idempotency key "必须能由 attempt identity、tool call identity、tool fact kind、result digest / awaiting digest 等确定性输入派生"，但未给出具体派生顺序和格式。
- **问题**：不同 ToolRuntime port 实现可能产生不同格式的 key，导致同一 tool result 在不同 Attempt 下产生冲突或不同 retry 路径下被认为不同。虽然具体的 hash 算法属于 implementation policy，但 key 的组成部分和顺序是跨组件契约。
- **建议修正**：§17 或 §18.2 明确定义 accept idempotency key 的组成部分：`(execution_id, tool_call_id, fact_kind, result_digest)` 的稳定序列化，并规定 fact_kind 的枚举值。

#### P2-6. Outbox 在线→离线客户端转换的 seen cursor 窗口未覆盖

- **文件/章节**：`design.md` §16 定义了在线路径（Host event stream）和离线路径（Outbox + seen cursor），以及"客户端在线已展示 final answer 后离线重连，从 Outbox 读取增量时不会重复显示同一 terminal answer"的去重规则。
- **问题**：在线→离线转换的边界未覆盖：客户端在通过 Host event stream 看到 `RUN_SUCCEEDED` event 但未来得及持久化 `last_seen_terminal_event_sequence` 就断开时，重连后 Service 的 seen cursor 可能落后于实际已展示的 terminal event。此时从 Outbox 读取增量会重新投递该 terminal item。去重规则依赖 UI 端按 terminal_event_id upsert，但如果 UI 本地存储也已丢失（例如 Web 刷新），重复显示不可避免。
- **影响**：低——`terminal_event_id` upsert 在 UI 有本地状态时有效；完全无状态客户端重连后看到重复 terminal answer 的体验降级是可接受的 v1 行为。
- **建议修正**：§16 显式记录这一已知窗口，作为 Outbox/Service phase 的 non-goal 或 deferred improvement。v1 接受无状态客户端重连可能看到重复 terminal 的体验，后续可通过 Service 端持久化 seen cursor 改进。

---

## 架构边界与过度设计检查

### 硬架构边界

以下边界在 design.md 中已明确且一致：

- **UI → Service → Host → Engine** 分层依赖方向：清晰，无反向依赖。
- **dayu.runtime** 层中立：§3 约束完整，`lane`、`filelock`、`ToolsDiscovery`、`ScenePrepare` 的语义边界已足够指导 phase plan。
- **ToolRuntime canonical owner**：§18.2 accept barrier 路径不可绕过，EngineEvent ingest 不得重复写入——已在 §13.4 的映射表中落实。
- **WorkerProxy/RemoteStub 无治理状态**：§17 远程执行不变量完整。
- **Projection 不能反向成为 EventLog 真源**：§14 Sink semantic contract 清晰，§15 Audit 边界明确。
- **EventLog append-only**：唯一例外 `purge_session` 在 §5、§13 中已完整定义。

**无新增架构边界违规。**

### 过度耦合检查

- ToolRuntime ↔ EngineEvent ingest 的职责分离：当前 design.md §13.4 明确 EngineEvent 中 `tool_result_accepted → preview / diagnostic / no-op`，canonical owner 是 ToolRuntime accept path。无耦合。
- RunInputBuilder ↔ Memory projection ↔ Context Governance：RunInputBuilder 消费 memory snapshot（read model），Context Governance 通过 typed ports 调用 compactor/budget estimator，不直接写 memory。边界正确。
- PolicyProviderSet ↔ subsystem：§10.1 规定子系统只接收 typed policy view，不持有 ProviderSet。边界清晰。

**无新增过度耦合。**

### 过度设计检查

上一轮评审标记的过度设计项（OE1 RunInputBuilder 7 providers、OE2 Memory cross-store atomic commit marker、OE3 三层 policy resolution）已在 final readiness adjudication 中处理：
- OE1 → 裁决 A17：v1 可合并共享 EventLog reader 的 provider
- OE2 → 裁决 A9：v1 使用同 SQLite transaction，cross-store deferred
- OE3 → 裁决 A19：保持 typed view 边界

design.md 当前版本已反映上述裁决。**无新增过度设计。**

---

## 实施总控（implementation-control.md）检查

### 已有防护

implementation-control.md 的强制约束列表（§强制约束，共 15 条禁止项）覆盖了关键架构边界：
- 不修改 Engine 代码（未经用户确认）
- Engine 不理解 Host 状态/memory/guidance/steer/fetch_more/tool governance
- projection/timeline/audit/trace/outbox 不作为事实真源
- 不复用旧 Attempt resume/takeover
- RemoteStub 不 append EventLog/关闭 Attempt/更新 Run
- 不引入重 lease/fencing 替代 admission + SQLite transaction + CAS
- 远端 sequence 不替代 Host 分配的 event_sequence
- assistant final answer 不自动升级为 verified fact
- fetch_more 不走 Host/Engine 特化分支
- 语义级重复工具调用治理不进 Engine
- sink 失败不影响 EventLog append 或 Run terminal

这些禁止项覆盖面足够，每条都有明确的架构理由。

### 缺失防护

1. **缺少 phase plan 的跨 phase 一致性校验规则**：当前文档只定义了单个 phase 的约束，但没有规定 phase B 的 plan 如何校验 phase A 已落实的公共契约（例如 ToolRuntime phase 的 plan 必须校验 EventLog phase 已确定的 canonical event 类型和 accept idempotency key 格式）。建议在追踪区或强制约束中增加一条：每个 phase plan 必须显式列出它依赖的前置 phase 的公共契约，并说明如何校验一致性。

2. **缺少 phase 间 shared test fixtures 的策略**：多个 phase（EventLog、State Machine、Public API、ToolRuntime、Recovery）都需要同一套 SQLite durable store 和 EventLog 基础。当前追踪区有跨层测试策略追踪但没有跨 phase 共享 fixture 的管理策略。建议增加：phase plan 应标识哪些 test fixtures 预期被后续 phase 复用，避免每个 phase 重新发明 SQLite schema 和 EventLog API。

---

## Residual Risks

### 已有追踪（implementation-control.md 追踪区已覆盖）

所有 8 项既有追踪项均被核实为当前且准确：
- Engine Context Compaction Event 语义前置
- External Job Cancel Adapter 能力追踪
- Tool Trace / Provider Request 排错追踪
- SQLite 多进程写入正确性验证
- Remote 物理执行 exactly-once 非目标
- Session Purge / Archive 追踪
- Host 跨层测试策略追踪
- UI / Service Outbox 去重边界追踪

### 建议新增追踪项

#### RR-NEW-1. `cancel_session_runs` 对 RECOVERING 状态的精确路径

- **风险**：见 P1-2。
- **归属**：Public API / Cancel phase。
- **处置**：phase discussion 中裁决 RECOVERING 的 cancel 路径（直接 CANCELLED vs 走 CANCELLING），写回 design.md §9.1 和 §22。

#### RR-NEW-2. `replay_run` no-tool 执行的主防线

- **风险**：见 P1-3。
- **归属**：RunInputBuilder / Replay phase。
- **处置**：phase discussion 中裁决主防线是 RunInputBuilder 排除 tool schemas 还是 ToolRuntime interceptor，写回 design.md §21。

#### RR-NEW-3. `resolve_wait` 幂等范围与 resume chain 原子性

- **风险**：见 P1-4。
- **归属**：Wait / Resume phase。
- **处置**：phase discussion 中定义 commit 失败后重试的完整幂等行为，明确"committed state"为幂等判断依据。

#### RR-NEW-4. `CONTEXT_COMPACTION_REQUESTED` trigger source 区分

- **风险**：见 P1-1。
- **归属**：EventLog / Context Governance phase。
- **处置**：在 EventLog canonical event contract 或 Context Governance 章节中区分 proactive vs reactive trigger 的 required fields。

#### RR-NEW-5. Recovery scan 处理顺序

- **风险**：见 P2-2。
- **归属**：Recovery phase。
- **处置**：phase discussion 中确定 RECOVERING dispatch / WAITING adapter recovery / QUEUED promotion 的顺序。

---

## Verdict

**READY WITH P1 FINDINGS**

当前 design.md 和 implementation-control.md 足够支撑进入 phase 编排。所有 5 个 P1 发现均可在对应 phase 的 discussion 阶段解决，不构成架构级阻塞。

进入 phase 编排前不需要再修改 design.md，但建议在 phase 清单中将本评审的 5 个 P1 标记为对应 phase 的 discussion 议题。

具体 phase 映射：

| P1 | 对应 Phase |
|---|---|
| P1-1 (CONTEXT_COMPACTION_REQUESTED trigger source) | EventLog / Context Governance |
| P1-2 (cancel RECOVERING 路径) | State Machine / Public API |
| P1-3 (replay no-tool 主防线) | RunInputBuilder / Replay |
| P1-4 (resolve_wait 幂等原子性) | Wait / Resume |
| P1-5 (close_session + RECOVERING) | Session / State Machine |

P2 各项可在对应 phase 的 design discussion 中一并精化，不需要独立追踪。
