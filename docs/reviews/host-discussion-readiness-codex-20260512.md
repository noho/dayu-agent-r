# Host discussion-note pre-design readiness review

- **review gate**: pre-design readiness review
- **review target**: `docs/host/discussion-note.md`, `docs/host/implementation-control.md`
- **review role**: role-scoped adversarial review；未启动 Gateflow controller
- **证据边界**: 现有 `docs/host/design.md` 是即将删除并重写的旧文件，未作为本次 readiness 判断的设计真源；下文对 `design.md` 的引用仅指 `implementation-control.md` 中描述的“待生成的新设计文档”
- **artifact path**: `docs/reviews/host-discussion-readiness-codex-20260512.md`
- **结论**: `fail`

## 动机判断

本次 review 的动机成立，且严重性没有被高估。`discussion-note.md` 已覆盖 Host 的核心目标和大量正确方向，但它仍保留多处会影响设计真源的 material open question；`implementation-control.md` 又要求后续 phase plan 必须基于 `discussion-note.md`、`design.md` 和对应 phase 的范围、依赖、退出条件。当前两份文档还不足以直接生成新的权威 `docs/host/design.md` 并按 phase 推进，除非先收敛下列 blocking findings。

## Assumptions Tested

- Host 必须是治理真源，Engine / RemoteStub / EngineWorker 只能执行和回传事件。
- 单机多客户端 / 多进程不是附加性能目标，而是状态、幂等、恢复、stream、取消和投影设计的基本约束。
- 本地 Engine 与远程 Engine 并列执行要求 LocalProxy / RemoteProxy 语义等价，不允许远端隐式接管治理。
- 生产级买方财报分析 Agent 要求证据链、工具事实、memory、audit、trace 与恢复路径可解释、可重建、可测试。

## Controller 状态标注（2026-05-12）

本 pre-design readiness review 已归档。其 findings 已被新版 `docs/host/design.md`、`docs/host/discussion-note.md`、
`dayu/README.md` 与 `docs/host/implementation-control.md` 吸收或明确后移；不再作为进入 draft design commit 的 open blocker。
下方原始严重度、blocking/high 标记和修正建议保留为 review-time 记录；后续 plan / implementation 以本节状态为准。

| Finding | 状态 | 归属 / 说明 |
| --- | --- | --- |
| 1 取消治理未收敛 | 已吸收 | `design.md` 已补 cancel state paths、terminal/cancel/suspend 竞态、cancel timeout -> LOST / RECOVERING 边界。 |
| 2 多进程并发 owner / transaction 不变量缺失 | 已吸收 | `design.md` 已补 SQLite transaction、CAS、唯一约束、global `event_sequence`、dispatch record；明确不引入重 lease / fencing。 |
| 3 本地 / 远程 Engine 控制面契约缺失 | 已吸收 / 后移 wire detail | `design.md` 已补 LocalProxy / RemoteProxy semantic contract；RPC / ack / heartbeat 等 wire protocol 明确归 Remote phase。 |
| 4 implementation-control tracking 与 phase 编排 | 已处理到 draft 阶段 | tracking 已清理为真实后续活项；phase 编排仍是下一步，不阻塞 draft design checkpoint。 |
| 5 WAITING / resume 治理入口缺失 | 已吸收 | `design.md` 已补 `resolve_wait`、wait record、poll / callback / manual adapter 语义。 |
| 6 EventLog taxonomy 不足 | 已吸收 | `design.md` 已补 canonical event matrix、EngineEvent mapping、canonical / preview / projection 边界。 |
| 7 范围过宽风险 | 已吸收 | `design.md` 已拆核心治理、extension points、non-goals 和 plan-agent 硬约束。 |

## Findings

### 1-已归档-[严重]-取消治理仍是未收敛需求，不能作为 design.md 的固定真源

- **严重程度**: 严重
- **位置**: `docs/host/discussion-note.md:19`, `docs/host/discussion-note.md:586-596`, `docs/host/discussion-note.md:690-716`
- **当前写法**: 当前需求要求取消治理支持 watchdog、取消超时升级、结构化取消终态和 Runner / SSE / 工具等待 / 后台 job 资源收口；后文又在“取消治理需要继续讨论”下列出 queued run 是否直接取消、watchdog timeout、timeout 后 LOST / 强杀 / job reconcile 条件、RemoteProxy 控制消息携带哪些 id、取消路径事件事实等未决项。
- **为什么有问题**: 取消是 Host 强约束治理的核心，不是实现阶段可自由选择的细节。当前文本同时把它列为固定目标和待讨论问题，生成 `design.md` 时设计作者必须自行决定 watchdog 边界、终态规则、远端取消 fencing、后台 job reconcile 和 canonical event taxonomy，这违反“设计真源先收敛，再生成 phase plan”的前提。
- **影响**: 实施 Agent 可能把 cancel 当普通失败、把 late cancel 覆盖已提交 suspend / terminal fact、误伤新的 remote attempt，或让资源收口失败只停留在 trace 中，最终导致 Run 终态不可审计、不可恢复。
- **建议改法**: 在进入 `design.md` 前收敛取消治理决议：定义 queued / running / waiting / terminal 各状态下 cancel 的状态迁移；定义 watchdog lease / timeout / escalation policy；定义 RemoteProxy cancel control message 必须携带的 run_id、attempt_id、execution_id、owner / fencing token 或等价校验；定义 SSE、工具等待、后台 job 的取消观察事件与收口事件；定义超时后何时 `CANCELLED`、`LOST`、`FAILED` 或等待 reconcile。
- **是否阻塞 design.md 生成**: 是。至少要把上述决议写成 design.md 的规范化状态机输入，不能留给 phase plan 或 implementation agent 选择。

### 2-已归档-[严重]-多进程并发只写了语义目标，缺少 owner / lease / fencing / transaction 不变量

- **严重程度**: 严重
- **位置**: `docs/host/discussion-note.md:13`, `docs/host/discussion-note.md:57-68`, `docs/host/discussion-note.md:263-296`, `docs/host/discussion-note.md:347-365`
- **当前写法**: 文档要求支持单机多客户端 / 多进程，并定义同一 Session 最多一个 active Run、queued run durable accepted、EventLog append 与 Run / Attempt 状态更新在事务中完成。但没有定义跨进程 owner claim、lease、fencing token、session active slot 原子仲裁、attempt owner 续租、projection checkpoint claim 或 stale owner cleanup。
- **为什么有问题**: 多进程下，“最多一个 active Run”“最早 queued run 启动”“Attempt 关闭一次”“EventLog 去重 append”都不是靠状态枚举自然成立的，需要 durable compare-and-swap、唯一约束、owner lease 和 fencing 语义支撑。当前文本不足以保证两个 Host 进程不会同时启动同一 queued run、同时关闭 attempt、或让旧 owner 的迟到写污染新 attempt。
- **影响**: 生产环境会出现重复 Run、重复 Attempt、双 final answer、late terminal 覆盖、cancel 误投递、projection checkpoint 倒退等难恢复错误；这些错误会直接破坏买方财报分析场景的审计链和结果可信度。
- **建议改法**: 在 design.md 生成前补齐跨进程治理不变量：session slot 绑定唯一约束；run admission 原子状态迁移；attempt owner lease 与 fencing token；event ingest 的唯一键与状态 CAS；observer / sink checkpoint claim；stale owner 识别与 recovery 规则；每条共享资源写入必须说明由哪个 token 或 durable condition 拒绝旧 owner。
- **是否阻塞 design.md 生成**: 是。多进程是固定设计目标，不能只在实现 phase 中再发明并发控制。

### 3-已归档-[高]-本地 / 远程 Engine 并列执行缺少 transport、重放与控制面契约

- **严重程度**: 高
- **位置**: `docs/host/discussion-note.md:34-44`, `docs/host/discussion-note.md:626-638`, `docs/host/discussion-note.md:679-688`
- **当前写法**: 文档规定 LocalProxy 与 RemoteProxy 语义等价，远端只执行并回传带 run_id、attempt_id、execution_id、sequence / event id 的事件；Host 校验后 append canonical EventLog；Worker / RemoteStub 重发事件由 Host 去重。
- **为什么有问题**: 这些约束方向正确，但还不是可生成设计的契约。远程并列执行还需要定义事件序列的来源、单调范围、ack / retry / replay 语义、断线后 RemoteStub 是否重放、control channel 与 event channel 的 ordering、heartbeat / lease、版本协商、payload_ref 可达性、remote clock 不可信时 occurred_at 处理、以及远端如何证明事件属于当前 attempt。
- **影响**: RemoteProxy 可能被实现成“能跑通 happy path 的传输层”，但在断线、重连、重复投递、cancel 与 terminal 交错、远程 worker 延迟回包时无法保持与 LocalProxy 等价，最终把治理边界偷偷推给远端。
- **建议改法**: 在 design.md 前形成 WorkerProxy / RemoteStub protocol section：事件 envelope、event_id / sequence 生成规则、Host ack 和 RemoteStub replay 规则、control message fencing、heartbeat / lost detection、payload_ref 存取边界、late / duplicate / mismatched event 的诊断落点，以及 LocalProxy 必须模拟同一 envelope 的要求。
- **是否阻塞 design.md 生成**: 是。若 design.md 只写拓扑不写协议不变量，后续远程 phase 会被迫重新设计核心边界。

### 4-已归档-[高]-implementation-control 的 tracking 与 phase 编排尚未承载已知未决项

- **严重程度**: 高
- **位置**: `docs/host/implementation-control.md:5`, `docs/host/implementation-control.md:65-84`, `docs/host/implementation-control.md:97-115`, `docs/host/discussion-note.md:709-716`, `docs/host/discussion-note.md:801-812`, `docs/host/discussion-note.md:839-845`
- **当前写法**: 总控文档声明负责 phase 编排、进入 / 退出条件、交付物和验证要求；phase plan 必须基于对应 phase 的范围、依赖和退出条件；但追踪区写“当前暂无跨 phase open question、潜在影响或未覆盖项”，当前状态又说下一步才补充 phase 编排。与此同时，discussion-note 已明确列出取消治理待讨论、memory 参数留到实施阶段、evidence anchor 类型留到 memory 实施阶段等未决项。
- **为什么有问题**: 这使控制文档在 gate 上给出错误信号：它要求 phase plan 依赖 phase 范围和退出条件，但这些 phase 不存在；它要求 tracking 承载 deferred risk，却没有登记已知 deferred 项。后续 controller / planner 无法判断哪些是 blocking、哪些是 non-blocking、归属哪个 phase、退出条件是什么。
- **影响**: design.md 生成后会缺少可执行的 phase 切分，implementation-ready plan 可能把 cancel、remote、memory、context、truncation、projection 混成大 phase；review finding 也无法稳定裁决为 accepted / deferred，因为没有 owner / destination。
- **建议改法**: 在 readiness 通过前，至少补齐 phase topology 草案和 tracking 初始项：核心治理状态机、durable store / EventLog、WorkerProxy remote protocol、cancel / suspend / resume、stream / projection、ToolRuntime truncation、memory / context governance 等 phase 的依赖、进入条件、退出条件和验证信号；把 discussion-note 中已知未决项登记为 blocking 或 non-blocking，并指定归属 phase。
- **是否阻塞 design.md 生成**: 阻塞“生成后按 implementation-control 推进 phase”。如果只生成草稿 design.md 可不阻塞，但当前 gate 目标包含后续 phase 推进，因此应视为 blocking。

### 5-已归档-[高]-公共接口没有覆盖 WAITING / resume / wait record 的治理入口

- **严重程度**: 高
- **位置**: `docs/host/discussion-note.md:79-91`, `docs/host/discussion-note.md:298-345`, `docs/host/discussion-note.md:520-561`, `docs/host/discussion-note.md:640-677`
- **当前写法**: 第一版最小接口包含 create/get/close session、start/get/stream/cancel run、submit_followup。wait record 章节规定 Host 负责等待持久化、后续 resume 和资源治理；resume 章节规定 wait condition satisfied 后 Host append resume requested fact 并创建新 Attempt。
- **为什么有问题**: 设计没有说明 resume 的外部或内部触发入口：callback / poll / manual 如何进入 Host，谁有权 resolve wait record，resolve 输入如何幂等，resolve 与 cancel / terminal / expired wait 如何竞态，submit_followup 的 `behavior: queue | steer` 是否可作用于 `WAITING` Run。没有这个入口，WAITING 是可进入但不可规范退出的状态。
- **影响**: 工具等待、后台 job、人工审批或外部回调会在实现时各自绕过 Host 公共契约，导致 resume facts、audit actor、idempotency key、wait record terminal status 和 RunInputBuilder 输入重建不一致。
- **建议改法**: 在 design.md 前定义 wait / resume contract：例如内部 Host scheduler API、public `resolve_wait` / `submit_resume` 是否进入第一版、callback/poll/manual 三类 resume_policy 的入口、幂等键、actor / principal、允许状态、与 cancel / expiry / lost 的竞态规则，以及 resolved / failed / cancelled / lost wait record 到 Run / Attempt 的迁移表。
- **是否阻塞 design.md 生成**: 是。ToolAwaiting / WAITING 已被纳入第一版核心状态机，不能缺少退出治理入口。

### 6-已归档-[高]-EventLog taxonomy 不足以支撑恢复、审计和状态迁移验证

- **严重程度**: 高
- **位置**: `docs/host/discussion-note.md:353-365`, `docs/host/discussion-note.md:401-414`, `docs/host/discussion-note.md:417-472`, `docs/host/discussion-note.md:586-596`
- **当前写法**: EventLog 形态包含 event_id、session_id、run_id、attempt_id、execution_id、sequence、event_type、occurred_at、payload_json、payload_ref、payload_digest；canonical facts 最小分类包含 RUN_TERMINAL、ATTEMPT_EVENT_ACCEPTED、ATTEMPT_TERMINAL、TOOL_RESULT_ACCEPTED、TOOL_AWAITING、GUIDANCE_INSERTED 等。
- **为什么有问题**: taxonomy 还没有把状态迁移所需字段和 audit 字段变成事件契约。比如 RUN_TERMINAL 没有 terminal_reason / terminal_status 的强制形状；ATTEMPT_EVENT_ACCEPTED 与 TOOL_RESULT_ACCEPTED 的边界不清；GUIDANCE_INSERTED 是否 canonical 在后文仍写“需要明确”；cancel / suspend / steer 的竞态规则没有映射到具体 accepted / ignored / rejected event。仅有 event_type 列表不足以让 design.md 验证恢复重建和审计责任链。
- **影响**: 后续实现可能把关键状态藏进 payload_json 自由结构，导致 pyright 类型、状态机测试、EventLog replay、audit projection 和 memory projection 都无法稳定验证；也会让 Observer / Sink 过早依赖不稳定 payload。
- **建议改法**: 生成 design.md 前补一张 canonical event contract matrix：每个 event_type 的 required ids、actor/source、idempotency key、state precondition、state effect、payload required fields、是否参与 memory / audit / resume、重复事件处理、late event 处理。把 RUN_TERMINAL / ATTEMPT_TERMINAL / WAIT / CANCEL / STEER / GUIDANCE 的 payload shape 至少规范到可测试的层级。
- **是否阻塞 design.md 生成**: 是。EventLog 是 Host 真源，taxonomy 不收敛会让设计文档无法成为后续实现真源。

### 7-已归档-[中]-discussion-note 范围过宽，存在把第一版设计做成总线式大平台的风险

- **严重程度**: 中
- **位置**: `docs/host/discussion-note.md:21-32`, `docs/host/discussion-note.md:155-156`, `docs/host/discussion-note.md:367-373`, `docs/host/discussion-note.md:475-519`, `docs/host/discussion-note.md:814-845`
- **当前写法**: 已吸收主题同时包括取消治理、等待协作、截断续读、run-time guidance、follow-up/steer、多轮 memory、context governance、EventLog projection、长期 memory governance、弱信号证据链。文档又说 durable queue、wait record、memory snapshot、tool trace、audit、usage、outbox、projection checkpoint 都可以是表、投影或内部机制。
- **为什么有问题**: 这些能力大多合理，但放在同一个 pre-design 输入里会诱导新 `design.md` 一次性规范过多子系统，尤其是 memory / context / weak-signal evidence 与 Host 核心治理的成熟度不同。如果不先切出 design nucleus 与 deferred extension points，设计会在“Host 中立治理”和“财报证据治理”之间变成过宽抽象，难以 review、难以分 phase，也容易把业务语义推进 Host。
- **影响**: 后续 phase 会过粗，implementation agent 需要在多个未收敛子系统间自行取舍；ToolRuntime、memory、audit、trace、projection 可能被设计成业务逻辑总线，偏离 Host 只做治理真源的目标。
- **建议改法**: 把 design.md 分成核心强约束与扩展约束：核心必须先收敛 Session / Run / Attempt / EventLog、admission、worker protocol、cancel/suspend/resume、stream/replay；ToolRuntime truncation、guidance、memory/context、long-term memory、weak-signal evidence 只写 Host 边界和不可封死的 extension point，具体策略进入对应 phase。implementation-control 同步把这些能力拆成可 review phase。
- **是否阻塞 design.md 生成**: 条件性阻塞。若新 design.md 试图一次性规范所有主题，则阻塞；若先明确 design nucleus 与 deferred section，并登记 owner / phase，则可降为 residual risk。

## Open Questions

- `cancel` 超时后是否优先进入 `LOST`，还是允许强杀执行环境后进入 `CANCELLED`，具体取决于 Host 是否能证明 Engine 已停止且无 late write。
- `WAITING` Run 的 manual / callback / poll resume 是否需要第一版 public API，还是只暴露 internal scheduler API。
- RemoteStub 事件的 `event_id` / `sequence` 由远端生成还是 Host 分配 attempt-local range；两者对应的去重和 replay 成本不同。
- Memory / context governance 哪些内容属于第一版设计必须规范，哪些只作为后续 phase 的边界约束。

## Residual Risk

- discussion-note 的大方向基本符合“宿主强约束下的 LLM in the loop”：Host 是治理真源、Engine 不理解 Host 策略、远端不接管 Run 状态，这些方向应保留。
- 最大剩余风险不是方向错误，而是未决项进入 design.md 后被写成模糊原则，导致 phase plan 和 implementation agent 继续补设计。
- 如果要进入 design.md 生成，建议先把 blocking findings 1-6 作为 design.md 生成前置 checklist；finding 7 可通过 design nucleus / deferred phase 切分降级。

## Final Readiness Conclusion

当前不建议把 `discussion-note.md` 直接作为生成新的权威 `docs/host/design.md` 的 ready 输入，也不建议按当前 `implementation-control.md` 进入后续 phase。进入 design.md 的最低条件是：

1. 收敛取消、WAITING/resume、remote protocol、多进程 owner/fencing、EventLog contract 的 blocking 决策。
2. 在 implementation-control 中登记已知 open questions / deferred risks，并补齐 phase topology、依赖、进入 / 退出条件。
3. 明确 design.md 的第一版核心范围，避免把 memory、context、truncation、guidance、weak-signal evidence 全部做成同一批必须落地的 Host 平台能力。
