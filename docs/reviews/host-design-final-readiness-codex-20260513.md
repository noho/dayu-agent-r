# Host Design Final Readiness Review

- **Review target**: `docs/host/design.md`, `docs/host/implementation-control.md`
- **Terminology source**: `dayu/README.md`
- **Review date**: 2026-05-13
- **Reviewer**: Codex
- **Verdict**: pass with non-blocking findings
- **Blocker**: none

## Scope And Method

本次 review 只按 `docs/host/design.md` 的最终结论判断，并用 `dayu/README.md` 校验术语边界。未读取或引用 `docs/host/discussion-note.md`、旧 design、旧 issue 或 archive 内容。

本次 readiness 标准不是要求 SQL DDL、远程 wire protocol 或测试代码已经写完，而是判断当前设计是否足以进入后续 phase discussion、phase design 与 phase plan，并且不会迫使 implementation agent 在架构边界、状态机或 semantic contract 上重新猜测。

## Assumptions Tested

- Host 是 Session / Run / Attempt / EventLog / admission / cancel / recovery / ToolRuntime / memory / projection 的治理真源；Engine 只执行单次 `AgentRunRequest`。
- EventLog canonical facts 是恢复、resume、memory、audit、outbox 派生的事实源。
- Projection / Sink / Outbox / memory snapshot 只消费已提交事实，不能反向成为治理真源。
- RemoteProxy / RemoteStub / EngineWorker 只负责执行与事件回传，不拥有 Host 状态。
- ToolRuntime 必须通过 Host accept barrier 让工具事实先 durable accepted，再把结果交给 Engine。
- 当前设计阶段允许把 DDL、具体 wire protocol、具体测试代码留给 phase plan，但不允许留下互相冲突的 semantic owner。

## Findings

### Blocker

无。

### High

#### H1-未修复-高-工具事实 canonical 写入 owner 在 ToolRuntime accept path 与 EngineEvent ingest 之间有重叠

- **位置**: `docs/host/design.md:984`, `docs/host/design.md:986`, `docs/host/design.md:1242`, `docs/host/design.md:1283`, `docs/host/design.md:1291`-`1295`
- **问题类型**: 架构边界 / 契约缺失 / 过度耦合
- **当前写法**: EngineEvent 映射把 `tool_result_accepted -> TOOL_RESULT_ACCEPTED`、`tool_awaiting -> TOOL_AWAITING`；同时 ToolRuntime accept barrier 要求 ToolRuntime 先向 Host submit tool fact candidate，Host append `TOOL_*` canonical facts 并返回 accepted ack 后，ToolRuntime 才能把 tool result 返回给 Engine。
- **反例/失败场景**: 一个工具调用执行成功后，ToolRuntime accept path 已经 append `TOOL_RESULT_ACCEPTED`；随后 Engine 因收到 accepted tool result 再 emit `tool_result_accepted`。如果 EngineEvent ingest 也按映射 append canonical fact，后续实现要么重复写工具事实，要么依赖临时去重规则，要么绕过 accept barrier 改成 EngineEvent 才是真正事实入口。
- **为什么有问题**: `dayu/README.md` 定义 ToolRuntime 必须通过 Host accept barrier，Engine 只调用 `ToolExecutor.execute(...)`，不理解工具治理。当前设计没有明确“工具事实 canonical write 的唯一 owner”，会让 ToolRuntime phase、EngineEvent ingest phase 和 Remote phase 在同一个事实上产生双写路径。
- **直接证据**: `docs/host/design.md:1283` 要求 LLM 不得消费未 durable accepted 的工具事实；`docs/host/design.md:1291`-`1295` 写明 Host 在 ToolRuntime accept path append `TOOL_*` canonical facts；但 `docs/host/design.md:984` 和 `docs/host/design.md:986` 又把 EngineEvent 直接映射到同类 canonical facts。
- **影响**: 生成重复 canonical event、破坏 tool fact idempotency、让 remote ack 重放与 EngineEvent 重放互相耦合，或者让 implementation agent 自行选择事实入口。
- **建议改法和验证点**: 在进入 ToolRuntime / EngineEvent ingest / Remote phase 前裁决一个唯一 owner。推荐裁决为：ToolRuntime accept path 是工具事实 canonical owner；Engine 后续 `tool_result_accepted` / `tool_awaiting` event 只能携带 accepted event refs，用于 preview / diagnostic / trace，或在同一 accept idempotency key 下成为明确 no-op，不再创建第二条 canonical fact。验证点应覆盖本地与远端 ack 丢失、EngineEvent 重放、同一 tool result 重复回传均不追加第二份 canonical fact。
- **修复风险（低/中/高）**: 中
- **严重程度（低/中/高/严重）**: 高

#### H2-未修复-高-cancel 与 suspend 竞态下已接受取消可能落成长期 WAITING

- **位置**: `docs/host/design.md:355`, `docs/host/design.md:395`, `docs/host/design.md:1569`, `docs/host/design.md:1574`-`1575`, `docs/host/design.md:1789`
- **问题类型**: 状态机漏洞 / 并发恢复风险 / 契约缺失
- **当前写法**: active cancel 路径允许后续进入 `CANCELLED / WAITING / RECOVERING / LOST`；`WAITING` Run 被 cancel 时会直接收口为 `CANCELLED`；但 cancel 与 suspend 同时发生时，已接受 awaiting outcome 和 `run_suspended` 不被 late cancel 覆盖。
- **反例/失败场景**: 用户对 `RUNNING` Run 发起 cancel，Host 已提交 `CANCEL_REQUESTED + RUN_CANCELLING`。旧 Attempt 随后回传 `TOOL_AWAITING + run_suspended`。如果 Host 接受 suspend 并让 Run 进入 `WAITING`，这次已经接受的 cancel request 没有明确自动应用到 wait record；recovery 又规定 `WAITING` 只等待 wait record resolution。结果是用户以为已取消，但 Session active slot 可能被一个等待外部 job 的 Run 长期占住。
- **为什么有问题**: 取消是用户可见治理语义。当前文档说明了“已经 WAITING 后再 cancel”的路径，也说明了“late cancel 不覆盖 accepted suspend”，但没有裁决“cancel request 已 durable accepted 后再收到 suspend”时是否要原子取消 wait record、拒绝 suspend canonical 化，还是显式让 suspend 胜出。
- **直接证据**: `docs/host/design.md:355` 把 active cancel 后续状态列入 `WAITING`；`docs/host/design.md:1569` 又规定 `WAITING` cancel 直接 `CANCELLED`；`docs/host/design.md:1574`-`1575` 规定 accepted suspend 不被 late cancel 覆盖。
- **影响**: 不同 phase agent 可能实现出不同 cancel/suspend 排序语义；最坏情况下取消请求不能释放 active slot，queued Run 无法 promotion，外部 job 结果迟到后还要额外防污染。
- **建议改法和验证点**: 在 State machine / Tool Awaiting phase 前补一条确定性规则。推荐规则：若 `CANCEL_REQUESTED` 已在当前 Attempt suspend 事件前提交，则 Host 可以接受 `TOOL_AWAITING` 作为诊断或工具轨迹，但必须在同一治理事务中把 wait record 标记 cancelled 并让 Run 进入 `CANCELLED`，或明确拒绝该 suspend 进入 canonical facts；若 suspend terminal 先提交，后续 cancel 走现有 `WAITING -> CANCELLED` 路径。验证点应覆盖 cancel-first、suspend-first、重复 cancel、迟到 callback / poll result。
- **修复风险（低/中/高）**: 中
- **严重程度（低/中/高/严重）**: 高

### Medium

#### M1-未修复-中-purge_session 与 EventLog append-only 需要显式例外和 purge 后幂等凭据

- **位置**: `docs/host/design.md:76`, `docs/host/design.md:139`-`143`, `docs/host/design.md:675`, `docs/host/design.md:798`-`802`, `docs/host/implementation-control.md:216`-`217`
- **问题类型**: 契约缺失 / audit 与恢复边界
- **当前写法**: EventLog 被定义为 append-only 且“不 update、不 delete”；`purge_session` 又明确删除该 Session 的 EventLog rows，并按 `(session_id, client_request_id)` 幂等，只保留最小 tombstone / audit record。
- **反例/失败场景**: Storage phase agent 可能把 EventLog append-only 当成绝对约束而不删除 EventLog rows；也可能执行删除后把幂等记录、semantic input digest 或 enough audit material 一并删掉，导致同一 purge request 重试无法返回既有结果，或不同 `client_request_id` / reason 无法区分是 gone、conflict 还是新 purge。
- **为什么有问题**: destructive purge 是设计明确纳入第一版的公共 API，不是普通实现细节。当前 implementation-control 已追踪 purge request、幂等、tombstone 位置和共享 artifact ref 检查，但还没有点名它是 EventLog append-only 的显式例外，以及 purge tombstone 必须保存哪些幂等与审计字段。
- **直接证据**: `docs/host/design.md:802` 说 EventLog 不 delete；`docs/host/design.md:139` 说 purge 删除 EventLog rows；`docs/host/design.md:675` 说 purge 按 `(session_id, client_request_id)` 幂等。
- **影响**: Storage phase 需要重新裁决 purge 是否允许删除 EventLog；实现不一致会影响 audit、重试、gone/not_found 错误形状和共享 cold artifact 清理安全。
- **建议改法和验证点**: 在 Public API / Storage phase 明确：`purge_session` 是 EventLog append-only 的唯一 destructive exception，且只在严格前置条件成立后执行。purge tombstone 应至少包含 `session_id`、purge `client_request_id`、semantic request digest、actor/source/request refs、terminal precondition digest、deleted counts / digest、tombstone event / record id。验证点覆盖同一 purge 重试、不同 payload 同幂等键冲突、purged 后读取、共享 artifact 不被误删。
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 中

#### M2-未修复-中-implementation-control 尚未承载实际 phase 清单、依赖和退出条件

- **位置**: `docs/host/implementation-control.md:5`, `docs/host/implementation-control.md:35`, `docs/host/implementation-control.md:64`-`67`, `docs/host/implementation-control.md:253`-`258`
- **问题类型**: Phase readiness gap / 不可直接实施
- **当前写法**: implementation-control 声明负责记录 phases、依赖、phase 进入 / 退出条件、交付物和验证要求；当前正文主要包含工作流、强制约束、风险追踪和当前状态，尚无可选择的 phase inventory。
- **反例/失败场景**: 下一步如果直接让 agent “选择一个 phase”并生成 handoff plan，agent 只能从 design 章节自行切分，容易把 Storage、EventLog、State machine、ToolRuntime、Remote、Projection、Recovery 的依赖顺序切错，或把 Engine cleanup 与 Host Context Governance 的前置关系漏掉。
- **为什么有问题**: 这不阻塞设计进入 phase 编排，但阻塞“直接进入某个 phase plan”。phase plan 必须基于 design 和 implementation-control 中对应 phase 的范围、依赖和退出条件；现在后一部分还没落地。
- **直接证据**: `docs/host/implementation-control.md:64`-`67` 要求 phase plan 基于本文档中对应 phase 的范围、依赖和退出条件；`docs/host/implementation-control.md:253`-`258` 仍表示当前阶段是设计收口、进入 phase plan 前还要讨论细化。
- **影响**: phase agent 会重新设计切片，增加跨层改动、遗漏 deferred risk owner，或提前做 future-slice work。
- **建议改法和验证点**: 在首个 phase plan 前，先补 implementation-control 的 phase inventory：phase 名称、目标、输入章节、明确 non-goals、前置依赖、退出条件、验证类型、必须回写的追踪项。该补充不应新增架构语义，只承载编排。
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 中

### Low

#### L1-未修复-低-StartRunRequest 暴露 execution_target / queue_policy 需要防止上层变成 Host policy owner

- **位置**: `docs/host/design.md:490`, `docs/host/design.md:609`-`610`, `docs/host/design.md:682`
- **问题类型**: 过度耦合 / 架构边界
- **当前写法**: Host policy provider set 包含 worker selection policy；第一版公共 API 不暴露开放式 policy knobs；但 `StartRunRequest` 片段包含 `execution_target` 和 `queue_policy`。
- **反例/失败场景**: UI / Service phase 把 `execution_target` 当作直接选择 Local / Remote worker 的命令，把 `queue_policy` 当作绕过 Host admission 的策略输入。后续 worker selection、admission policy 或多入口默认策略变化时，需要跨 UI / Service / Host 同步修改。
- **为什么有问题**: 该字段可能只是调用方语义偏好，也可能是 Host policy input。当前命名和边界没有说清，会削弱 Host 对 admission 与 worker selection 的治理 ownership。
- **直接证据**: `docs/host/design.md:490` 把 worker selection policy 放在 Host policy provider；`docs/host/design.md:609`-`610` 又把 target / policy 字段放进公共 request；`docs/host/design.md:682` 禁止开放式 policy knobs。
- **影响**: 轻度跨层耦合风险。它不阻塞 phase 编排，但 Public API phase 需要裁决字段语义。
- **建议改法和验证点**: Public API phase 明确这些字段是“调用方偏好 / admission behavior request”，必须经 Host policy 校验与归一化；或改名为更窄的 semantic intent。验证点覆盖上层请求 remote 但 Host policy 改派 local / reject 时，错误分类和 audit policy decision 可解释。
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低

## Over-coupling / Overengineering Findings

- **Over-coupling**: H1 是最重要的过度耦合风险。ToolRuntime accept path 与 EngineEvent ingest 同时看起来能写工具 canonical facts，会把 ToolRuntime、Engine、Remote ack 和 EventLog ingest 绑定成双 owner。
- **Over-coupling**: L1 是轻度跨层耦合风险。`execution_target` / `queue_policy` 若不被限制为 Host policy 的输入，会让 UI / Service 参与 Host admission 与 worker selection 决策。
- **Overengineering**: 未发现需要阻止 phase 编排的过度设计。当前的 EventLog、Projection、Outbox、Recovery、ToolRuntime port、Context Governance 等复杂度与生产级本地多进程、远程执行、可恢复事实链目标相匹配。后续 phase plan 应避免一次性实现全部可选 port，只按退出条件切片。

## Phase Readiness Gaps

- **可进入 phase 编排**: design 的核心边界、状态集合、EventLog 真源、Remote non-ownership、ToolRuntime Host ownership、Outbox 边界和 Recovery 正向孤儿证明已经足够支撑 phase 编排。
- **不可直接进入某个 implementation-ready phase plan**: implementation-control 还缺 phase inventory、依赖顺序、每 phase 退出条件和验证矩阵，见 M2。
- **必须在相关 phase 前裁决**: ToolRuntime / EngineEvent ingest / Remote phase 前裁决 H1；State machine / Cancel / Tool Awaiting phase 前裁决 H2；Public API / Storage phase 前裁决 M1；Public API phase 前裁决 L1。
- **Context Governance phase 前置依赖清楚**: implementation-control 已把 Engine context compaction event cleanup 作为前置追踪项，避免 Host 消费 `0/0/0` budget 占位。

## Residual Risks That Should Stay In implementation-control

已覆盖且应继续保留：

- Engine Context Compaction Event 语义前置：`docs/host/implementation-control.md:120`-`143`
- External Job Cancel Adapter 能力追踪：`docs/host/implementation-control.md:145`-`158`
- Tool Trace / Provider Request 排错追踪：`docs/host/implementation-control.md:160`-`173`
- SQLite 多进程写入正确性验证：`docs/host/implementation-control.md:175`-`188`
- Remote 物理执行 exactly-once 非目标：`docs/host/implementation-control.md:190`-`203`
- Session Purge / Archive 追踪：`docs/host/implementation-control.md:205`-`217`
- Host 跨层测试策略追踪：`docs/host/implementation-control.md:220`-`235`
- UI / Service Outbox 去重边界追踪：`docs/host/implementation-control.md:237`-`250`

建议新增或扩展追踪：

- Tool fact canonical owner：记录 H1 的裁决，归属 ToolRuntime / EngineEvent ingest / Remote phase。
- Cancel-suspend race：记录 H2 的确定性排序规则，归属 State machine / Tool Awaiting / Cancel phase。
- Purge append-only exception：扩展现有 Session Purge / Archive 追踪，加入 append-only 例外和 tombstone 幂等字段。
- Phase inventory：在首个 phase plan 前补齐 phase 清单、依赖、进入 / 退出条件和验证要求。

## Open Questions

- 工具事实 canonical owner 是否按推荐方案归 ToolRuntime accept path，还是由 EngineEvent ingest 统一写入并让 ToolRuntime accept path 只做预提交校验？当前设计更支持前者。
- cancel-first / suspend-late 场景中，Host 是否应接受 `TOOL_AWAITING` canonical fact 后立即取消 wait record，还是直接把迟到 suspend 降级为 diagnostic？两者都可实施，但必须只有一个默认语义。
- purge tombstone 是否需要保存完整 idempotency ledger，还是保存足以回答同一 request 重试和冲突判断的最小 digest？Public API / Storage phase 需要确定。

## Final Conclusion

当前 Host design v2 可以进入 phase 编排：核心架构边界与术语总体稳定，未发现必须退回重写的 blocker。

但它还不应直接交给 implementation agent 做某个大 phase。下一步应先补 implementation-control 的 phase inventory，并把 H1、H2、M1 纳入对应 phase 的进入条件或追踪项。只要这些裁决在相关 phase plan 前完成，当前 findings 均可作为非阻塞风险处理。
