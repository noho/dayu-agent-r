# Host Design V2 Review - AgentCodex - 2026-05-13

## 元信息

- Review gate: draft design v2 review。
- Reviewer persona: AgentCodex。
- Review target:
  - `docs/host/design.md`
  - `dayu/README.md`
  - `docs/host/implementation-control.md` 仅用于确认 gate 状态和流程约束。
- 架构与术语真源:
  - `docs/host/design.md`
  - `dayu/README.md`
- 明确未参考:
  - discussion-note、旧 design、旧 issue、archive、旧代码实现、历史 review。
- 当前状态证据:
  - `docs/host/implementation-control.md:175-181` 说明当前为 draft design v2 完成，Host 代码尚未开始；若 review 通过且无阻断项，后续才进入 phase 编排。
- Review 判断口径:
  - 本轮不要求 SQL schema、wire protocol、完整 dataclass 或完整测试矩阵。
  - 重点判断 design v2 是否足以作为 phase 编排真源，避免后续 phase agent 自行猜架构边界、状态机、公共 API 或持久化语义。

## 结论

**当前结论: fail。**

design v2 的总体方向成立：`UI -> Service -> Host -> Engine` 分层、Host 作为 Session / Run / Attempt / EventLog 治理真源、Engine 只执行单次 `AgentRunRequest`、ToolRuntime accept barrier、projection 非真源、final answer 不自动成为 verified fact，这些主轴在 `docs/host/design.md` 与 `dayu/README.md` 中基本一致。

但当前存在 1 个 blocker：多进程 recovery scan 语义会让新启动的 Host 进程把另一个仍存活进程控制的 active Attempt 误判为 `LOST`。这会破坏 design 自己的多进程目标，并可能制造重复 Attempt / 重复远程执行 / 迟到事件污染诊断的问题。该问题属于架构语义缺口，不是 SQL schema 或 wire protocol 细节。

因此 **design v2 暂不应进入 phase 编排**。先修复 blocker 后，可以重新评估是否进入 phase 编排；high / medium findings 至少应在对应 phase discussion 或 phase plan 前收敛为明确设计约束。

## Findings

### Blocker

#### C1-未修复-[严重]-多进程 recovery scan 会误杀其它存活进程的 active Attempt

- **位置**:
  - `docs/host/design.md` 1. 设计目标: `docs/host/design.md:5-10`
  - `docs/host/design.md` 8. Admission 与多进程并发: `docs/host/design.md:273-281`
  - `docs/host/design.md` 26. Host Lifecycle / Recovery: `docs/host/design.md:1679-1707`
  - `docs/host/design.md` dispatch record 语义: `docs/host/design.md:1742-1757`
- **问题类型**: 架构边界 / 并发恢复风险 / missing semantic contract / phase-readiness blocker
- **当前写法**:
  - 设计目标要求支持“单机多客户端 / 多进程”，并支持本地 Engine 与远程 Engine 并列执行。
  - 多进程一致性依赖 SQLite transaction、唯一约束、CAS-style transition、`event_id` / `event_sequence`，且明确“不引入重 lease / fencing 系统”。
  - recovery scan 在 Host 启动时读取 Run / Attempt indexes 并分类每个 non-terminal Run；对 `RUNNING` / `CANCELLING` Run，如果“没有可确认的本进程 dispatch record 与可用执行通道”或“不存在当前 Host 可确认控制的 dispatch record”，旧 Attempt 进入 `LOST`，Run 进入 `RECOVERING` 或 `LOST`。
  - dispatch record 明确不是 lease / fencing token，只帮助 Host 判断旧 Attempt 是否仍能被当前进程确认控制。
- **反例/失败场景**:
  - 进程 A 已经通过 SQLite 事务创建 Run / Attempt，并正在本地或远程执行 Attempt。
  - 进程 B 随后启动，同样连接共享 SQLite durable store，并按设计执行 startup recovery scan。
  - B 能读取 A 的 `RUNNING` Attempt，但无法确认“本进程 dispatch record 与可用执行通道”，也无法控制 A 的 LocalProxy / RemoteProxy channel。
  - 按当前文档，B 会把 A 的旧 Attempt 标为 `LOST`，再让 Run 进入 `RECOVERING` 并可能创建新 Attempt。
  - A 仍可能继续运行并回传事件；这些事件会变成迟到 / stale event，或被拒绝为 diagnostic，同时新 Attempt 已经启动。
- **为什么有问题**:
  - 这是对“单机多进程共享同一 Host 真源”的直接破坏。多进程下，“当前进程不能确认控制”不等于“旧 Attempt 已丢失”。
  - design 禁止旧 Attempt takeover 是正确的，但不能把“不 takeover”简化成“其它进程看不见控制通道就标 LOST”。
  - 若 phase agent 按当前文档实现 startup recovery scan，会把正常 live work 误分类成 orphaned work，制造重复执行和不可解释的事件拒绝。
- **直接证据**:
  - `docs/host/design.md:9-10` 设定支持单机多客户端 / 多进程和本地 / 远程 Engine 并列执行。
  - `docs/host/design.md:275-279` 规定第一版用 SQLite 支撑单机多进程真源，不引入重 lease / fencing，不做旧 Attempt takeover。
  - `docs/host/design.md:1679-1685` 要求 Host 启动时执行 recovery scan，并把没有本进程可确认 dispatch record / 通道的 active Attempt 标为 `LOST`。
  - `docs/host/design.md:1691-1698` 写明 startup scan 会 classify each non-terminal Run 并 append `ATTEMPT_LOST` / `RUN_RECOVERING` / `RUN_LOST`。
  - `docs/host/design.md:1705-1706` 用“当前 Host 可确认控制”作为继续观察与标 `LOST` 的分界。
  - `docs/host/design.md:1755-1757` 又说明 dispatch record 不是 lease / fencing token，只判断当前进程是否可确认控制。
- **影响**:
  - 多进程启动或重启时误杀 live Attempt。
  - 同一 Run 产生并列 Attempt，破坏 active Run / Attempt 语义。
  - 远端或本地工具可能重复执行，外部副作用只能靠工具级 idempotency 做有限兜底。
  - EventLog 中出现人工制造的 `ATTEMPT_LOST` / `RUN_RECOVERING`，后续 audit、outbox、memory 和 trace 难以解释。
  - 后续 recovery phase agent 必须自行发明 liveness / orphan 判定，违背 design 作为架构真源的目标。
- **建议改法和验证点**:
  - 在 `design.md` 中先明确 recovery scan authority：多进程场景下，startup scan 不得仅因“当前进程无法确认控制通道”就把其它进程的 active Attempt 标为 `LOST`。
  - 明确定义可接受的 orphan proof / recovery eligibility，例如单一 recovery authority、轻量 dispatch liveness marker + CAS、显式 owner death proof，或把 startup scan 限定为当前进程可证明拥有且已失去控制的 dispatch records。
  - 同时保留“不 takeover 旧 Attempt”的硬约束：不能接管其它进程 Attempt；只能在证明旧 Attempt orphan 后通过 CAS 标 `LOST` 并创建新 Attempt。
  - 验证点至少覆盖：进程 A 正在执行 Attempt 时，进程 B 启动 recovery scan，B 不得 append `ATTEMPT_LOST`，不得创建新 Attempt，不得释放或抢占 active slot。
- **修复风险（低/中/高）**: 高
- **严重程度（低/中/高/严重）**: 严重

### High

#### H1-未修复-[高]-`HostCallContext.client_request_id` 与 `ensure_session` / adapter idempotency 语义冲突

- **位置**:
  - `docs/host/design.md` 5. Session Slot: `docs/host/design.md:117-143`
  - `docs/host/design.md` 10. Host 公共接口: `docs/host/design.md:490-505`
  - `docs/host/design.md` request fragments: `docs/host/design.md:530-602`
  - `dayu/README.md` 术语约定: `dayu/README.md:46-47`、`dayu/README.md:65`
- **问题类型**: public API / typed provider-port boundary / missing semantic contract
- **当前写法**:
  - `ensure_session(scope, slot_key)` 明确按 `(scope, slot_key)` 幂等，且“不需要 `client_request_id`”。
  - 所有会 append EventLog `canonical_fact` 或影响 outbox / audit 的 mutating request 又必须携带 `HostCallContext`，其中 `client_request_id` 被定义为客户端操作幂等 id。
  - 文档还说 request fragment 中出现的 `client_request_id` 与 `HostCallContext.client_request_id` 是同一个字段，不是两份独立 id。
  - `ResolveWaitRequest` 使用 `idempotency_key`，而不是 `client_request_id`。
- **反例/失败场景**:
  - `ensure_session` 在 slot 不存在时会创建并绑定 Session，这会产生 canonical fact / audit，因此属于 mutating request。
  - 如果实现严格要求所有 mutating request 都有 `HostCallContext.client_request_id`，则 `ensure_session` 被迫引入 `client_request_id`，违背 `(scope, slot_key)` 幂等和 README 术语真源。
  - 如果实现为了保留 `ensure_session` 的无 `client_request_id` 语义而跳过 `HostCallContext`，又会丢失 actor / source / request id / authorization claims 等 audit 与 policy 输入。
  - wait adapter / callback 实现也可能在 `idempotency_key` 与 `client_request_id` 之间自行映射，导致 idempotency scope 不一致。
- **为什么有问题**:
  - 这是公共 API envelope 与操作级 idempotency 的边界混淆。`client_request_id` 不是所有 mutating command 的唯一幂等来源；`ensure_session` 和 `resolve_wait` 已经定义了不同幂等范围。
  - 后续 phase agent 会被迫自行决定 HostCallContext 是否强制携带 `client_request_id`、是否允许 optional、或是否拆分 audit context 与 idempotency key。
- **直接证据**:
  - `docs/host/design.md:137` 明确 `ensure_session` 不需要 `client_request_id`。
  - `docs/host/design.md:490-505` 要求所有 mutating request 携带 HostCallContext，并把 `client_request_id` 定义为客户端操作幂等 id。
  - `docs/host/design.md:530-535` 的 `EnsureSessionRequest` 没有 `client_request_id`。
  - `docs/host/design.md:595-602` 的 `ResolveWaitRequest` 使用 `idempotency_key`。
  - `dayu/README.md:46-47` 与 design 一致区分 `ensure_session` 和 `create_session` 的幂等语义。
- **影响**:
  - 公共 API dataclass / protocol 容易设计错误。
  - audit / authorization fields 可能被塞进 metadata 或被遗漏。
  - 幂等冲突处理不可预测，尤其是 `ensure_session` 并发创建和 wait callback 重放。
- **建议改法和验证点**:
  - 把“调用责任上下文”和“操作幂等键”拆开：例如定义 `HostCallContext` 只承载 actor / source / request_id / authorization / delivery hints，操作级 request 单独定义 idempotency scope。
  - 或明确 `HostCallContext.client_request_id` 是 operation-specific optional field；`ensure_session` 使用 `(scope, slot_key)`，`resolve_wait` 使用 `(wait_id, idempotency_key)`，其它客户端命令使用 `client_request_id`。
  - 验证点：`ensure_session` 无 `client_request_id` 仍能记录 actor/source/request id；重复 `(scope, slot_key)` 返回同一 Session；不同 caller request id 不改变复用结果。
- **修复风险（低/中/高）**: 中
- **严重程度（低/中/高/严重）**: 高

#### H2-未修复-[高]-`RUN_CANCELLING` 被列为 canonical event，但 cancel 迁移没有要求 append 它

- **位置**:
  - `docs/host/design.md` 8.1 状态迁移契约: `docs/host/design.md:309-324`
  - `docs/host/design.md` 12.2 Canonical Event 最小集合: `docs/host/design.md:804-850`
  - `docs/host/design.md` 12.3 Canonical Event Contract Matrix: `docs/host/design.md:860-878`
  - `docs/host/design.md` 21. Cancel: `docs/host/design.md:1445-1477`
- **问题类型**: 状态机漏洞 / canonical event contract 缺失 / 不可直接实施
- **当前写法**:
  - `RUN_CANCELLING` 在 canonical event 最小集合中存在。
  - `cancel_run` on active running 的目标状态是 Run `CANCELLING`，但必须追加的 canonical facts 只有 `CANCEL_REQUESTED` 和后续 terminal fact。
  - Cancel 初始路径也写成 append `CANCEL_REQUESTED` 后直接 `Run -> CANCELLING`，没有 append `RUN_CANCELLING`。
  - canonical matrix 没有给 `RUN_CANCELLING` 单独或合并的 contract row。
- **反例/失败场景**:
  - 实现 Agent 按状态迁移表实现 active cancel：append `CANCEL_REQUESTED`，直接更新 Run row 为 `CANCELLING`。
  - EventLog replay / audit 只看到 cancel intent，看不到 Run status 已进入 `CANCELLING` 的 canonical fact。
  - 另一个实现 Agent 按 event 最小集合实现 `RUN_CANCELLING`，会与表驱动实现产生不同 EventLog 序列和测试期望。
- **为什么有问题**:
  - design 明确只有 `canonical_fact` 可以驱动 Run / Attempt 状态迁移。Run 进入 `CANCELLING` 是治理状态变化，不能只存在于状态索引。
  - 当前写法让 `RUN_CANCELLING` 的存在意义不清：要么它是必需状态事实，要么应从最小集合移除并明确 `CANCEL_REQUESTED` 本身承担状态副作用。
- **直接证据**:
  - `docs/host/design.md:321` active cancel 的 required canonical facts 未包含 `RUN_CANCELLING`。
  - `docs/host/design.md:816` 把 `RUN_CANCELLING` 列入 canonical event 最小集合。
  - `docs/host/design.md:864-866` 的 Run status matrix 覆盖 `RUN_STARTED`、`RUN_WAITING`、`RUN_RECOVERING`、terminal events，但未覆盖 `RUN_CANCELLING`。
  - `docs/host/design.md:1451-1461` Cancel path 也没有 append `RUN_CANCELLING`。
- **影响**:
  - EventLog replay 与 Run row state 可能不同源。
  - cancel race、recovery scan、audit 和 Host event stream 对 `CANCELLING` 的解释不一致。
  - 后续 phase plan 无法基于单一 matrix 生成状态机 tests。
- **建议改法和验证点**:
  - 选择一种语义并写硬：推荐 active cancel 在同一事务 append `CANCEL_REQUESTED` + `RUN_CANCELLING`，并更新 Run status。
  - 同步补齐 canonical matrix 中 `RUN_CANCELLING` 的 required scope、payload、状态副作用、resume / audit 语义。
  - 如果决定由 `CANCEL_REQUESTED` 直接承担状态副作用，则删除 `RUN_CANCELLING` 或明确它不是第一版 event，避免双真源。
  - 验证点：从 EventLog replay 能准确恢复 active cancel 已进入 `CANCELLING`，而不是只从 Run row 推断。
- **修复风险（低/中/高）**: 中
- **严重程度（低/中/高/严重）**: 高

### Medium

#### M1-未修复-[中]-`WAITING` steer 的 wait record 与 Run 状态事实未硬化

- **位置**:
  - `docs/host/design.md` 8.1 状态迁移契约: `docs/host/design.md:317-318`
  - `docs/host/design.md` 11. Follow-up 与 Steer: `docs/host/design.md:665-719`
  - `docs/host/design.md` 19. Tool Awaiting / Wait Record: `docs/host/design.md:1328-1351`
- **问题类型**: 状态机漏洞 / missing semantic contract / phase slicing readiness
- **当前写法**:
  - `resolve_wait` 从 `WAITING` 到 `RUNNING` 明确 append `RESUME_REQUESTED`、tool terminal/result fact、`RUN_STARTED`、`ATTEMPT_STARTED`。
  - `submit_followup(steer)` 允许 target Run 为 `RUNNING` 或 `WAITING`，目标状态是同一 Run `RUNNING`，但 required canonical facts 只有 `STEER_REQUESTED`、旧 Attempt terminal when `RUNNING`、`ATTEMPT_STARTED`。
  - `WAITING` steer path 写明 active wait record 被标记为 abandoned for resume purposes；但 wait record 状态集合只有 `waiting`、`resolved`、`failed`、`cancelled`、`lost`，没有 `abandoned`。
- **反例/失败场景**:
  - `WAITING` Run 被 steer，Host 需要释放原 wait record 的 resume 权限并创建新 Attempt。
  - 一个实现把 wait record 标为 `cancelled`；另一个实现新增 `abandoned`；第三个实现只在 `STEER_REQUESTED` payload 放一个 flag。
  - 如果没有 `RUN_STARTED` 或等价 Run state canonical fact，EventLog replay 无法稳定解释 Run 从 `WAITING` 回到 `RUNNING` 的状态变化。
- **为什么有问题**:
  - `WAITING` steer 与普通 `resolve_wait` 一样会改变 Run 状态并停用 wait record，但当前文档没有给出同等级别的 canonical fact 序列。
  - 后续 Follow-up / Steer phase plan 会被迫自行选择 wait record terminal status 和 Run status event。
- **直接证据**:
  - `docs/host/design.md:317` 的 `resolve_wait` 明确包含 `RUN_STARTED`。
  - `docs/host/design.md:318` 的 `submit_followup(steer)` 未包含 `RUN_STARTED`，也未命名 wait record 状态事实。
  - `docs/host/design.md:689-700` 写 `WAITING` steer 会标记 wait record abandoned 并创建新 Attempt。
  - `docs/host/design.md:1345-1351` 的 wait record 状态集合未定义 `abandoned`。
- **影响**:
  - Follow-up / Steer phase 不够 implementation-ready。
  - EventLog replay、late wait result 拒绝、audit 和 tool trace 对同一场景可能不一致。
  - phase agent 可能新增未设计的 wait 状态或把状态塞进无结构 payload。
- **建议改法和验证点**:
  - 明确 `WAITING` steer 的 canonical sequence：至少定义 wait record 从 `waiting` 进入哪个终态或 sub-state，并明确是否 append `RUN_STARTED` 表达 Run 回到 `RUNNING`。
  - 明确 `RUNNING` steer 的旧 Attempt terminal event 是 `ATTEMPT_STEERED`，以及 terminal race 发生时 `STEER_REQUESTED` 是否进入后续新 Run / queued follow-up。
  - 验证点：late wait callback 在 `WAITING` steer 后只能进入 diagnostic / tool trace，且 EventLog replay 能恢复 Run `WAITING -> RUNNING`。
- **修复风险（低/中/高）**: 中
- **严重程度（低/中/高/严重）**: 中

#### M2-未修复-[中]-wait poller 同时被描述为 background runtime 和 canonical command trigger，边界需要硬化

- **位置**:
  - `docs/host/design.md` 9.1 Host Handle / Composition Root: `docs/host/design.md:383-424`
  - `docs/host/design.md` 19. Tool Awaiting / Wait Record: `docs/host/design.md:1353-1378`
  - `dayu/README.md` 术语约定: `dayu/README.md:84-85`、`dayu/README.md:96-97`
- **问题类型**: 架构边界 / over-coupling risk / missing semantic contract
- **当前写法**:
  - background runtime supervisor 可以持有 `wait poller`。
  - background runtime 不 append canonical facts，不更新 Run / Attempt governance state。
  - wait signal source 的 `poll | callback | manual` 又必须进入 common Host `resolve_wait` pipeline，该 pipeline 会 append tool terminal/result fact、创建 new Attempt、resume Run。
- **反例/失败场景**:
  - phase agent 把 wait poller 当作普通 Sink / projection worker，实现为直接 append EventLog 或更新 wait record。
  - 另一个 phase agent 严格遵守 background runtime 不写 truth，于是 poll 完成后不敢调用 `resolve_wait`，导致 `WAITING` Run 永远不 resume。
- **为什么有问题**:
  - 当前文档表达了正确方向：所有 wait resolution 必须走 `resolve_wait`。但没有明确 wait poller 的身份是“background trigger 调用 command path”，而不是 Sink 自己写 truth。
  - 这个边界如果不硬化，后续 Tool Awaiting phase 很容易把 command path 与 projection runtime 混在一起。
- **直接证据**:
  - `docs/host/design.md:402-409` 把 wait poller 放在 background runtime supervisor。
  - `docs/host/design.md:424` 规定 background runtime 不 append canonical facts、不更新 Run / Attempt governance state。
  - `docs/host/design.md:1355-1363` 规定 poll / callback / manual 都进入 resolve_wait pipeline，并 append tool terminal/result fact、创建 new Attempt。
  - `dayu/README.md:84-85` 对 command path 与 background runtime 的术语也有同样区分。
- **影响**:
  - Tool Awaiting / Wait Adapter phase 的 ownership 容易被实现错。
  - 后续测试可能只能通过大集成链路证明，而无法对 command path / background trigger 分层验证。
- **建议改法和验证点**:
  - 在 design 中明确：wait poller 是 background runtime 中的 trigger / adapter；它观察 wait record 与外部 job，但只能通过公共或内部 `resolve_wait` command path 提交结果。
  - 明确 wait poller 自身不得持有 EventLog appender，不得直接更新 Run / Attempt / wait record terminal state。
  - 验证点：poller unit test 只断言调用 `resolve_wait` port；`resolve_wait` command path test 断言 canonical facts 与 Attempt 创建。
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 中

### Low

#### L1-未修复-[低]-`dayu/README.md` 的文档职责声明与当前术语真源用途有轻微冲突

- **位置**:
  - `dayu/README.md` Agent 更新约束: `dayu/README.md:5-8`
  - `dayu/README.md` 术语约定: `dayu/README.md:38-42`
  - `docs/host/implementation-control.md` 真源层级与当前状态: `docs/host/implementation-control.md:20-44`、`docs/host/implementation-control.md:175-181`
- **问题类型**: README 术语一致性 / process contract
- **当前写法**:
  - `dayu/README.md` 自称只写“当前代码已实现”的整体架构、设计意图、稳定边界、扩展入口、代码阅读顺序。
  - 同一 README 的术语约定又被定义为后续 Host / Engine / Service phase discussion、phase plan、implementation、review、fix 与 re-review 的项目级术语真源。
  - implementation-control 明确 Host 代码尚未开始，但 `dayu/README.md` 已是项目级术语真源。
- **反例/失败场景**:
  - 后续文档同步或 review agent 严格遵守 README 自身职责，认为未实现 Host v2 术语不应出现在 `dayu/README.md`。
  - 另一个 agent 按 implementation-control 把 README 当 phase 术语真源，继续扩展术语。
- **为什么有问题**:
  - 这不是 Host 架构 blocker，但会导致 README 更新规则与 Gateflow 真源层级冲突。
  - 当前用户明确把 `dayu/README.md` 作为设计和术语真源，因此职责声明最好与此一致，避免后续 agent 机械清理“未实现术语”。
- **直接证据**:
  - `dayu/README.md:7` 说只写当前代码已实现内容。
  - `dayu/README.md:40-42` 说术语表是后续 phase / implementation / review 的项目级术语真源。
  - `docs/host/implementation-control.md:177-181` 说 Host 代码尚未开始，review 通过后才进入 phase 编排。
- **影响**:
  - 文档同步阶段可能出现无谓争议。
  - README 术语真源地位可能被后续 agent 误削弱。
- **建议改法和验证点**:
  - 在后续文档整理中明确 README 可承载“已被采纳的稳定架构与术语真源”，而不是只限已经落地的代码事实；或把未实现 Host v2 术语范围显式标为已采纳设计真源。
  - 验证点：后续 README review 不再把 Host v2 术语因为“代码尚未开始”而判为越界。
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低

## Over-coupling / Overengineering Check

- **Over-coupling**:
  - 发现 1 个 blocker：recovery scan 把“当前进程可确认控制 dispatch”与“Attempt 是否仍存活”耦合，无法支撑多进程共享 Host 真源。
  - 发现 1 个 medium：wait poller 同时出现在 background runtime 与 `resolve_wait` canonical command path 周边，需硬化 trigger-vs-writer 边界。
  - ToolRuntime accept barrier 与 Host EventLog 的耦合是有动机的：它服务“工具事实先 durable accepted 后才能返回给 Engine”的核心目标，不单独判为过度耦合。
- **Overengineering**:
  - 当前设计范围很大，但主要复杂度来自已声明目标：durable facts、多进程、本地 / 远程 Engine、cancel / resume / retry / replay、ToolRuntime governance、context governance、projection / outbox 分离。
  - `HostPolicyProviderSet`、typed policy view、RunInputBuilder provider protocols、ToolRuntime ports 的方向符合避免 god object / service locator 的项目约束；未发现必须在 draft design v2 阶段删除的过度抽象。
  - 风险在于 phase slicing：各 phase 必须只实现对应治理闭环，不能因为设计全量存在而一次性铺开所有 sink、policy provider 或远程 transport。

## Phase-Readiness Verdict

**Verdict: fail。**

design v2 目前 **不足以进入 phase 编排**，原因是 blocker C1 会让 Recovery / Admission / WorkerProxy / RemoteProxy phase 的基础假设错误。这个问题必须在 `docs/host/design.md` 中先收敛为明确语义，再进入 phase 编排。

若 C1 修复，design v2 的剩余问题更适合进入 phase discussion / phase plan gate：

- H1 应在 Public API / Host Handle / Session phase 前修复或明确。
- H2 应在 State Transition / Cancel phase 前修复或明确。
- M1 应在 Follow-up / Steer / Wait Record phase 前修复或明确。
- M2 应在 Tool Awaiting / Wait Adapter phase 前修复或明确。
- L1 可在后续 README 同步时修复，不阻塞架构判断。

## Open Questions

- 多进程恢复应由哪个 authority 执行：所有 Host 进程都可 scan、单一 recovery supervisor scan，还是只由持有某种轻量 liveness proof 的进程 scan？
- 在不引入重 lease / fencing 的前提下，design 接受哪种 orphan proof 判定 active Attempt 已不可确认？
- `RUN_CANCELLING` 的最终语义是独立 canonical state fact，还是由 `CANCEL_REQUESTED` 承担状态副作用？
- `WAITING` steer 停用 wait record 时，wait record 应进入 `cancelled`、新增 `abandoned`，还是保留状态并使用 typed inactive reason？

## Residual Risks

- 本轮未要求也未检查 SQL schema、wire protocol、完整 dataclass 或完整测试矩阵；这些仍需在后续 phase design / phase plan 中补齐。
- Context Governance 与 ToolRuntime 细节很宽，虽然当前没有判为 blocker，但后续 phase plan 必须避免把多个 sink、policy、remote transport 和 memory projection 合并成过粗 slice。
- Remote transport 的 heartbeat / connection keepalive 被定义为 wire detail，但 C1 修复可能需要把“liveness proof 的语义边界”提升到 Host design；需要小心不把它滑向重 lease / fencing。

