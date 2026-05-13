# Findings

### P0-未修复-严重-`implementation-control.md` 尚未提供可执行的 phase 编排，不能进入 phase orchestration
- **位置**: `docs/host/implementation-control.md` 文档职责与真源层级（第 3-8、20-45 行）、phase plan 输入要求（第 64-82 行）、强制约束（第 84-104 行）、当前状态（第 253-258 行）
- **问题类型**: 不可直接实施 / 切片过粗 / open question 未收敛 / 测试缺口
- **当前写法**: 文档声明自己负责记录 phase 编排、phase 进入 / 退出条件、交付物和验证要求，但正文只给出通用工作流、强制约束和追踪区；没有实际 phase 清单、phase 顺序、依赖关系、每个 phase 的 scope boundary、entry / exit criteria、交付物和验证矩阵。
- **反例/失败场景**: 下一步如果直接进入 phase orchestration，不同 planning agent 会自行把 `design.md` 的 28 个章节切成不同 phase：有人可能先做 Public API，有人先做 Durable Store，有人先做 ToolRuntime / lane dispatch。由于没有总控 phase 边界，后续计划可能提前实现 future-slice 能力、遗漏前置 contract，或把跨层修改夹带进 Host phase。
- **为什么有问题**: 当前 gate 是“准备进入 phase orchestration”，不是单纯确认 `design.md` 是否内容丰富。`implementation-control.md` 第 5 行明确承担 phase 编排职责，第 64-68 行又要求每个 phase plan 基于“本文档中对应 phase 的范围、依赖和退出条件”。这些对应 phase 目前不存在，phase plan 没有稳定输入。
- **直接证据**: `implementation-control.md` 第 5 行声明职责；第 64-68 行要求 phase plan 基于对应 phase 范围、依赖和退出条件；第 253-258 行仍停留在 draft design v2 收口，并说明进入任何 phase plan 前仍需讨论设计章节，但没有列出将要讨论的 phase。
- **影响**: 实施 Agent 跑偏 / phase plan 不可验收 / 设计问题被推迟到实现中重新发现 / review 无法判断 phase 是否越界 / 后续返工。
- **建议改法和验证点**: 在进入 phase orchestration 前，为 `implementation-control.md` 增加一张最小 phase map。每个 phase 至少包含：目标与 success signal、覆盖的 `design.md` 章节、明确 non-goals、前置依赖、entry criteria、exit criteria、交付物、必须验证的测试类型、README 触发项、必须先解决或可后置追踪的 open questions。建议至少显式覆盖 Public API / contracts、Durable Store + EventLog + state transition、Admission + queue + cancel、WorkerProxy + lane dispatch、ToolRuntime + ToolBundle + accept barrier、Tool Awaiting / wait record、Projection / Audit / Outbox、Memory / Context Governance、Recovery 等边界。
- **修复风险（低/中/高）**: 中。主要是文档编排工作，但会暴露 phase 依赖和部分设计缺口。
- **严重程度**: P0

### P0-未修复-严重-`TOOL_AWAITING` 与 `run_suspended` 的 canonical owner 冲突，WAITING 状态机不可安全实现
- **位置**: `docs/host/design.md` 状态迁移表（第 368 行）、Canonical Event Contract Matrix（第 1015-1016 行）、EngineEvent 映射（第 1038-1040、1054、1060 行）、Tool Awaiting 路径（第 1588-1600 行）、Tool fact accept barrier（第 1456-1471 行）
- **问题类型**: 状态机漏洞 / 契约缺失 / 并发恢复风险 / 架构边界
- **当前写法**: 状态迁移表把 Engine suspended 映射为同时追加 `TOOL_AWAITING`、`RUN_WAITING`、`ATTEMPT_SUSPENDED`；Canonical Event Matrix 又写 `TOOL_AWAITING` 会创建 wait record 并让 Run -> `WAITING`；但 EngineEvent 映射写 `tool_awaiting` 只是 preview / diagnostic / no-op，`run_suspended` 才映射为 `RUN_WAITING + ATTEMPT_SUSPENDED`。第 20 节路径则先让 ToolRuntime accept `TOOL_AWAITING`，再等待 Engine emit `run_suspended` 才关闭 Attempt、标记 Run `WAITING`、持久化 wait record。
- **反例/失败场景**: ToolRuntime 已把 `ToolAwaitingOutcome` 提交给 Host 并收到 accepted ack，随后本地进程或远程连接在 Engine emit `run_suspended` 前崩溃。此时 Host 可能已经有 `TOOL_AWAITING` canonical fact，但 Run / Attempt / wait record 是否已经进入 `WAITING` 没有唯一答案。后续 callback / poll / cancel / recovery 可能找不到 active wait record，或重复接受同一个等待事实，或把应该等待的 Run 判为 `RUNNING` / `RECOVERING`。
- **为什么有问题**: Host 设计要求 EventLog append 与必要 Run / Attempt 状态索引更新在同一事务内完成，ToolRuntime accept barrier 又要求工具事实先被 Host durable accepted 后才能影响 Engine 继续推理。当前写法把同一个 suspend/waiting 事实分摊给 ToolRuntime accept path 和 Engine `run_suspended` ingest path，导致 canonical ownership 不唯一，也让 Engine 事件有机会成为 Host wait 状态的实际 owner。
- **直接证据**: `design.md` 第 1456-1471 行要求工具事实必须先走 Host accept barrier；第 1016 行写 `TOOL_AWAITING` 的状态副作用是创建 wait record、Run -> `WAITING`；第 1054 行又说 Engine `tool_awaiting` 不是 canonical owner；第 1060 行把 `run_suspended` 映射为 `RUN_WAITING + ATTEMPT_SUSPENDED`；第 1591-1599 行把这些步骤串成非原子先后链。
- **影响**: 状态不一致 / WAITING cancel 与 resolve race 无法证明 / recovery 误判 / 迟到事件污染 canonical facts / implementation agent 需要重新设计核心状态机。
- **建议改法和验证点**: 先选定唯一 canonical owner。推荐方案：`ToolAwaitingOutcome` 的 Host accept transaction 原子追加 `TOOL_AWAITING`、`RUN_WAITING`、`ATTEMPT_SUSPENDED`，创建 wait record，更新 Run / Attempt 状态；Engine 后续 `tool_awaiting` / `run_suspended` 只能携带 accepted refs，作为 preview / diagnostic / idempotent confirmation，不再驱动状态迁移。若反向选择 Engine `run_suspended` 做 canonical owner，则 `TOOL_AWAITING` 不能先创建 wait record，且必须补充 ack 后崩溃、callback 先到、cancel 先到的恢复语义。无论选哪种，都要同步更新状态迁移表、Canonical Event Matrix、EngineEvent 映射、第 20 节路径，并要求 phase plan 覆盖 ack 丢失、run_suspended 丢失、cancel / resolve race、Host restart 的测试。
- **修复风险（低/中/高）**: 高。它会影响 ToolRuntime、EngineEvent ingest、wait record、cancel 和 recovery 的 phase 边界。
- **严重程度**: P0

### P1-未修复-高-主动 context compaction 复用了 recovery 语义，但没有定义 pre-dispatch 状态迁移
- **位置**: `docs/host/design.md` Run / recovery 语义（第 224-236、382-389 行）、Canonical Event Matrix（第 1018-1019 行）、Context Governance（第 1938-1955、1966-1977 行）；`docs/host/implementation-control.md` Engine compaction 追踪（第 120-143 行）
- **问题类型**: 状态机漏洞 / 契约缺失 / 过度耦合
- **当前写法**: Context Governance 同时支持 proactive trigger 和 reactive trigger。第 1940-1941 行写 proactive trigger 在 dispatch Attempt 前由 Host / RunInputBuilder 判断；第 1946-1955 行的统一响应路径又写 append `CONTEXT_COMPACTION_REQUESTED`、reactive 时关闭当前 Attempt、Run -> `RECOVERING`、compact 后创建新 Attempt。文档没有说明 proactive trigger 发生在 `RUN_STARTED / ATTEMPT_STARTED` 之前还是之后，也没有定义没有失败 Attempt 时为何进入 `RECOVERING`。
- **反例/失败场景**: 新 Run 已 durable accepted，RunInputBuilder 在派发前发现预算超限。实现者可能先创建 `ATTEMPT_STARTED` 再做 compact，然后把 Run 标为 `RECOVERING`；也可能在没有 Attempt 的情况下追加 attempt-scoped compact event；还可能把 compact 当作普通 projection 写入，导致 replay / audit 无法解释输入如何变化。
- **为什么有问题**: `RECOVERING` 在设计中主要表示旧 Attempt 丢失、失败或可恢复路径的治理状态。主动 pre-dispatch compaction 是计划内输入治理，不是旧 Attempt orphan / provider overflow recovery。二者混用会让 admission、active slot、queue promotion、cancel 和 recovery scan 的状态机边界变得不可判定。
- **直接证据**: `design.md` 第 228 行定义 `RECOVERING` 为 Host 确认旧 Attempt 丢失后继续同一 Run；第 382-389 行描述 `RECOVERING` 的退出；第 1940 行把 proactive trigger 放在 dispatch 前；第 1949 行又在统一路径中写 Run -> `RECOVERING`。
- **影响**: 生成错误状态机 / active slot 长时间占用 / compact event validator 无法落地 / recovery 与 context governance phase 互相污染 / 后续测试只能覆盖 happy path。
- **建议改法和验证点**: 把 proactive 和 reactive compaction 拆成两个明确契约。proactive 路径应定义为 pre-dispatch input governance：在创建或派发 Attempt 前，以 run-scoped canonical events 记录 `CONTEXT_COMPACTION_REQUESTED(proactive)` 和 `CONTEXT_COMPACTED`，再创建 `ATTEMPT_STARTED`；或者显式增加一个有界的 active input-preparation 状态，但不能复用 orphan recovery 语义。reactive provider overflow 才走关闭当前 Attempt、`RECOVERING`、新 Attempt 的路径。验证点包括：proactive compact 无 Attempt、reactive compact 有 Attempt、compact 失败、compact 后仍超 budget、cancel 与 proactive compact 竞争。
- **修复风险（低/中/高）**: 中。
- **严重程度**: P1

### P1-未修复-高-`ToolBundle` / effective `ToolBundle` 的注入边界未进入公共 request contract
- **位置**: `docs/host/design.md` runtime 装配组件（第 65-72 行）、Host 公共接口 request 片段（第 643-715 行）、attempt snapshot（第 1359-1365 行）、ToolBundle flow（第 1382-1415 行）、RunInputBuilder 输入（第 1816-1819 行）
- **问题类型**: 架构边界 / 契约缺失 / 过度耦合 / 不可直接实施
- **当前写法**: 文档多处要求 Host 不做工具发现，外部装配生成业务 `ToolBundle` 并作为显式参数传给 Host；Host 冻结 attempt-local snapshot，ToolRuntime factory 注入 `fetch_more` 形成 effective `ToolBundle`。但 `StartRunRequest`、`SubmitFollowupRequest`、`RetryRunRequest`、`ReplayRunRequest` 等公共 request 片段都没有 `ToolBundle`、`tool_bundle_ref`、scene/tool profile 或等价 typed execution input 字段。
- **反例/失败场景**: 一个 implementation agent 可能把 `ToolBundle` 放进 Host handle 的全局 options，导致不同 scene / Service 入口无法按 Run 选择工具；另一个可能把它塞进 `metadata`，违反 required fields 不能放入无结构 payload 的约束；还有人可能让 Host 自己扫描业务工具，直接破坏 Host 不 import 业务工具的边界。retry / replay / resume 时也会不清楚应复用源 Run snapshot 还是读取当前工具目录。
- **为什么有问题**: `ToolBundle` 是 Engine 可见 tool schema、ToolRuntime callable binding、truncate spec、`fetch_more` 注入和工具事实 accept barrier 的共同输入。如果它不在公共契约中显式建模，attempt-local effective ToolBundle 就没有可审计、可恢复、可重放的来源。
- **直接证据**: `design.md` 第 69 行写 ToolsDiscovery 生成业务 `ToolBundle` 并作为显式参数传给 Host；第 1386-1397 行给出 Host receives `ToolBundle` -> attempt-local snapshot -> effective `ToolBundle` 的路径；第 643-715 行的 request 片段没有对应字段；第 1412-1414 行要求 attempt-local snapshot 与 Engine tool schema / ToolRuntime callable 来自同一个 effective `ToolBundle`。
- **影响**: Host 与业务工具发现过度耦合 / per-run 工具快照不可恢复 / replay 和 retry 行为不一致 / `fetch_more` schema 与 callable binding 可能漂移 / 工具治理测试边界不稳定。
- **建议改法和验证点**: 在 Public API / ToolRuntime phase 前补充一个 typed `RunExecutionInputs` 或 `ToolBundleBinding` 契约，并明确它是在 start/follow-up acceptance request 中传入，还是由 Host handle 绑定的 immutable profile 解析而来。若支持多 scene，应优先按 Run / Attempt 显式传入 bundle ref + digest + policy binding refs，并在 `RUN_ACCEPTED` 或 `ATTEMPT_STARTED` payload 中记录 snapshot refs。retry / replay / resume 必须说明复用源 Run accepted snapshot、重新解析当前 bundle，还是由 policy 决定。验证点包括不同 scene 工具集、工具目录变更不影响已创建 Attempt、`fetch_more` 注入后 Engine schema 与 callable binding 一致、metadata 不承载显式契约字段。
- **修复风险（低/中/高）**: 中。
- **严重程度**: P1

### P1-未修复-高-lane waiting / pre-dispatch cancellation 的状态收口不完整
- **位置**: `docs/host/design.md` runtime lane 约束（第 67 行）、Attempt startup 边界（第 391-396 行）、Worker dispatch semantic contract（第 1323-1345 行）、Cancel（第 1756-1788 行）
- **问题类型**: 并发恢复风险 / 状态机漏洞 / 契约缺失
- **当前写法**: dispatch record 可以在 `ATTEMPT_STARTED` 后等待 LLM lane；lane acquire 成功后 recheck durable state，失败则 release lane 且不 dispatch。Cancel 章节写 `RUNNING` / Attempt `STARTING` 场景进入 `CANCELLING` 并传播 cancel；但 `cancel_session_runs` 又写 Attempt `STARTING` 且尚未 dispatch / 正在 waiting-for-lane 时直接取消，不通知 EngineWorker。文档没有定义单个 `cancel_run` 命中 waiting-for-lane Attempt 时的 terminal facts、dispatch record 状态、lane waiter 取消和 queue promotion 触发。
- **反例/失败场景**: Attempt 已 `STARTING`，dispatch worker 正在等待 lane。用户调用 `cancel_run`。如果只把 Run 置为 `CANCELLING`，但没有 worker 可通知，lane waiter 又没有被 command path 唤醒或取消，Run 可能长期占用 active slot。即使 dispatch worker后来醒来 recheck 失败，也没有明确谁 append `ATTEMPT_CANCELLED / RUN_CANCELLED` 并触发 queue promotion。
- **为什么有问题**: lane 不是 Host truth，但 waiting-for-lane 是 Attempt dispatch 的真实中间态。取消最小收口是 Host 核心目标之一；pre-dispatch cancel 如果没有原子 terminal 路径，就会把“未启动 EngineWorker”的 Attempt 当成“已运行需等待 Engine cancel”的 Attempt，造成不必要的悬挂和恢复歧义。
- **直接证据**: `design.md` 第 1329-1334 行定义 waiting lane 与 recheck；第 1343-1345 行要求 cancel / shutdown release 或 cancel lane wait；第 1760 行把 Attempt `STARTING` 归入需等待 Attempt 收口的 active cancel 场景；第 1780 行对 session-scope cancel 又要求 waiting-for-lane 直接取消。
- **影响**: cancel 后 active slot 不释放 / queued Run promotion 被阻塞 / recovery scan 误把可本地取消的 Attempt 当 LOST / 多进程 dispatch worker 行为不一致。
- **建议改法和验证点**: 增加 pre-dispatch cancellation 契约：当 Attempt 为 `STARTING` 且 dispatch record 为 `pending` / `waiting_for_lane` / 未 `dispatching` 时，`cancel_run` 和 `cancel_session_runs` 都应在同一 transaction 内 append `CANCEL_REQUESTED`、`ATTEMPT_CANCELLED`、`RUN_CANCELLED`，标记 dispatch record cancelled，释放 active slot，并触发 queue promotion；lane waiter 通过 cancellation source / wakeup 退出，若迟到醒来也只能 recheck 后 no-op。只有 dispatch record 已进入 `dispatching` 或 `ATTEMPT_RUNNING` 后，才走 `RUN_CANCELLING` + WorkerProxy cancel。phase plan 必须覆盖 lane wait cancel、lane acquired 后 cancel 先提交、dispatching 后 cancel、shutdown cancel 的测试。
- **修复风险（低/中/高）**: 中。
- **严重程度**: P1

### P2

未发现需要单独列为 P2 finding 的低严重度问题。低于 P1 的未覆盖项已放入 residual risks，不应阻塞设计修正，但需要后续 phase plan 追踪。

# Reviewed Targets And Scope

- Reviewed target: `docs/host/design.md`
- Reviewed target: `docs/host/implementation-control.md`
- Review stage: architecture / design-stage readiness review for entering phase orchestration.
- Excluded source: 未使用 `docs/host/discussion-note.md`。
- Review posture: adversarial plan/design readiness review, not implementation completeness review.

# Assumptions Tested

- Host 是 Session / Run / Attempt / EventLog / admission / cancel / resume / retry / replay / memory / tool governance 的治理真源。
- Engine 只执行单次 `AgentRunRequest`，不拥有 Host 状态，不恢复旧 Agent / Runner。
- `dayu.runtime.lane` 与 `dayu.runtime.filelock` 是层中立基础设施，不能替代 Host durable truth、admission、SQLite transaction、CAS 或 EventLog ordering。
- ToolRuntime 可以物理部署在本地或远端，但工具事实必须先经 Host accept barrier durable accepted，LLM 才能消费。
- Projection、audit、tool trace、outbox、memory snapshot 都是 read model / projection，不能反向成为 EventLog 真源。
- phase orchestration 的输入必须足够约束后续 phase plan，不应让 implementation agent 在计划阶段重新发明架构边界。

# Open Questions

- `ToolAwaitingOutcome` 的 canonical owner 是否确定为 ToolRuntime Host accept path？如果不是，必须明确 Engine `run_suspended` 成为 canonical owner 时的 ack 丢失与 crash recovery 语义。
- `ToolBundle` 是 per Run / Attempt 的显式输入，还是 Host composition root 的 immutable execution profile？如果两者都支持，需要定义优先级、snapshot 与 retry / replay 行为。
- proactive context compaction 是 pre-dispatch input preparation，还是一个占用 active slot 的独立治理阶段？当前设计不应默认复用 `RECOVERING`。
- phase map 的第一阶段是否先收敛 contracts / state-machine / storage，还是先按模块推进？当前 `implementation-control.md` 尚未裁决。

# Residual Risks

- 本次只审阅设计 artifact，未验证现有代码、测试和 README 是否已经偏离这些设计约束。
- SQLite 多进程正确性虽然有追踪项，但具体 busy timeout、短事务、错误分类、重试退避和 crash 测试仍需 Storage phase 证明。
- Remote 物理执行 exactly-once 是明确 non-goal；外部副作用风险必须在 ToolRuntime / tool schema / adapter policy phase 用 idempotency key、best-effort cancel 和 trace 继续约束。
- 第一版使用 conservative context estimator，不实现 provider-specific tokenizer；预算误判风险需要 Context Governance phase 用 safety margin、diagnostic 和 fallback test 覆盖。
- Purge tombstone 与共享 cold artifact ref 检查已经有方向，但仍需要 Storage phase 明确 tombstone 存储位置、引用计数或 ref check。

# Final Verdict

**not ready / fail**

当前设计不应直接进入 phase orchestration。主要原因不是实现细节缺失，而是：实施总控没有实际 phase 编排；WAITING / awaiting 的 canonical owner 存在 P0 级状态机冲突；context compaction、ToolBundle 注入和 lane pre-dispatch cancel 仍会迫使后续 phase plan 重新做架构裁决。修复上述 P0/P1 后，可以再做一次 readiness re-review。
