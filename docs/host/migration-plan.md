# Host 迁移总控计划

## 1. 计划状态

本文档是 Host 迁移总控计划草稿，用于指导总控 Agent 分阶段指挥迁移 Agent、review Agent
完成整个 Host 迁移。它不是单阶段 handoff plan，也不是实现文档。

当前总控状态：

- P1 已通过 PR #16 合入 `main`，当前确认基线为 `051cf20`。
- P1.5 已通过 PR #17 合入 `main`，merge commit 为 `ec1627c94f352205ee77bcd992d652e677fa0ebb`。
- P2 已通过 PR #18 合入 `main`，merge commit 为 `3d86eefd4bd8b99b24c638735220d9ee571255f7`。
- P3 已通过 PR #19 合入 `main`，merge commit 为 `b20e792 Host P3 conversation memory (#19)`。
- P4 已通过 PR #21 合入 `main`，merge commit 为 `843fb99 Host P4 context overflow compact (#21)`。
- 当前进入 P5 plan 修订阶段：No-Full-Governance Multi-Turn Smoke；当前分支为
  `codex/host-p5-multiturn-smoke`。P5 phase handoff plan、常规 plan review 与 OLD / NEW
  纵向语义 review 曾复审通过；用户人工 review 后先提出 tool declaration 方向调整，又进一步将 smoke tool
  目标改为真实 provider `mimo-v2.5-pro-plan` + `huge_echo` tool calling。P5 huge_echo plan review
  的两个非阻断实现 gate 已写回 P5 plan 并复审通过；旧 `double_echo` 临时方向废弃，
  `huge_echo` 必须通过公共 `@tool(..., truncate=ToolTruncateSpec(...))` 声明，并跑通真实 Host ToolRuntime
  truncate / fetch_more。当前决策记录见 `docs/host/phase5-huge-echo-plan-note.md`，review gate 见
  `docs/host/phase5-huge-echo-plan-review.md`；当前等待用户人工 review。

每个 Phase 进入实现前，必须另写可交接的 phase plan，细化到迁移 Agent 可以直接接手：
目标、非目标、边界、文件级改动清单、契约变化、状态机、测试清单、验证命令、review gate、
停止条件、风险、待确认项、实施完成汇报格式。

本文档只固定总控节奏、阶段顺序、阶段边界和每阶段必须产出的文档 / review / GitHub 工件。

## 2. 依据

本计划依据以下材料：

- `docs/host/design.md`
- `docs/host/interface-discussion-notes.md`
- `docs/host/design-best-practice-review.md`
- `docs/host/design-optimal-review.md`
- `docs/engine/design.md`
- `docs/engine/migration-plan.md`
- GitHub issue #3：取消治理增强。
- GitHub issue #4：wait / suspend / resume 协作。
- OLD conversation memory 设计：`https://github.com/noho/dayu-agent/issues/48`
- `AGENTS.md`

`docs/host/design.md` 是 Host 接口与架构边界真源。Engine 只提供强类型 `EngineEvent`、
函数式入口和 `ToolExecutor` 协议，不能把 Host ToolRuntime、trace、memory、transcript、
context overflow 治理回流到 Engine。

## 3. 总控工作流

每个 Phase 都必须使用独立分支。默认分支名：

```text
migration/host-p{phase}-{short-name}
```

如果用户指定其它分支名，以用户指令为准。

每个 Phase 的固定节奏：

1. 从最新主线或用户指定基线开新分支。
2. 派 Agent 写 phase handoff plan。
3. 派 review Agent 做 plan review，必要时派第二个 review Agent 做 OLD / NEW 对比或最佳实践 review。
4. plan review 不通过时，派 Agent 修 plan，并在对应 review 文档的finding标题上标注修复状态。
5. 派 review Agent 复审修复后的 plan；若仍不通过，重复步骤 4-5，直到 review Agent 明确通过。
6. plan review 通过后，停下来等用户人工 review。
7. 用户确认后，commit phase plan 与 review 文档。
8. 派迁移 Agent 按通过的 plan 生成代码。
9. 派 code review Agent 做 code review，必要时派额外 review Agent 做 OLD / NEW 对比、架构边界、
   类型安全或并发专项 review。
10. code review 不通过时，派 Agent 修复代码，并在对应 code review 文档的finding标题上标注修复状态。
11. 派 code review Agent 复审修复后的代码；若仍不通过，重复步骤 10-11，直到 review Agent 明确通过。
12. code review 通过后，停下来等用户人工 review。
13. 用户确认后，commit 代码、测试和必要 README / docs 更新。
14. 准备 PR 时，确认只包含本 Phase 范围内提交，push 并创建 ready PR；不创建 draft PR，
    除非用户明确要求。
15. 派 PR code review Agent 审查 PR diff，必要时继续修复、复审、补 commit，直到 PR review
    Agent 明确通过。
16. PR review 通过后，停下来等用户确认。
17. squash merge PR 并删除远端分支默认由用户执行；只有用户明确指示总控 Agent 执行时，
    总控 Agent 才能执行 squash merge / delete branch。用户手工 merge 后，总控只记录状态。

禁止事项：

- 不在未通过 plan review 的情况下写生产代码。
- 不用总控 Agent 自己的复核替代 review Agent 的通过结论。
- 不在 review finding 未标注修复状态的情况下声称 review 通过。
- 不把多个 Phase 的实现混进一个 PR，除非用户明确批准合并。
- 不在用户确认前 commit / push / create PR / merge。
- 不把迁移过程要求写进 `docs/code_review.md`；该文档只写日常 review 当前事实专项。

## 4. 阶段总览

前半段目标是先跑通一个“没有完整生产治理”的多轮会话 smoke：

```text
EngineWorker
  -> Minimal EventLog / RunEventStore
  -> truncate / fetch_more
  -> Conversation Memory
  -> context overflow / compaction 协作
  -> no-full-governance multi-turn smoke
  -> deferred-scope reconciliation
```

这里的“没有完整生产治理”只表示先不实现完整多进程并发、恢复、Remote、Outbox、
audit hard-gate 等生产治理；不表示可以破坏分层、跳过强类型契约、绕过
`dayu.fins.storage`、绕过 append-before-stream EventLog 事实层，或把 Host 职责塞回 Engine。

| Phase | 名称 | 目标 | 主要输出 | 明确不做 | 验收信号 |
| --- | --- | --- | --- | --- | --- |
| P0 | 计划与议题同步 | 固定 Host 迁移总控计划，创建 / 更新必要 issue 与 review prompt 事实 | 本文档、plan review、必要 issue comment | 不写生产代码 | 用户确认可以进入 P1 |
| P1 | EngineWorker + 最小 Run Harness | 落地与 Engine 最接近的 Host capability：Local EngineWorker、最小 WorkerProxy、最小 Run 执行装配 | `dayu.host` 最小入口、LocalProxy、EngineWorker wrapper、EngineEvent -> RunEvent 翻译薄层、最小 `start_run` 测试入口 | 不做 Remote RPC、不做完整 Session governance、不做 memory、不做 truncate/fetch_more | 单 Run 可通过 Host 调 Engine 函数式入口并流出事件；EngineWorker / ToolExecutor 不暴露为 Host public API |
| P1.5 | Minimal EventLog / RunEventStore | 固定 P2-P5 共同依赖的最小事件事实层，避免旁路 transcript / memory facts | append-before-stream EventLog 契约、per-run cursor、canonical / preview 分层、最小 Run state 调和 | 不做完整 observer、不做 trace / audit sink、不做完整多进程 recovery | P2-P5 只能依赖 RunEventStore / canonical facts，不需要未来 P6 倒改事实来源 |
| P2 | ToolRuntime truncate / fetch_more | 把 OLD TruncationManager / cursor / TTL / scope token 迁到 Host / ToolRuntime 边界 | 工具结果截断契约、fetch_more 调用路径、cursor storage、TTL / scope token 测试、ToolRuntime 最小运行事实 | 不做完整 ToolRegistry 权限、不做业务工具迁移、不让 Engine 持有 cursor 管理；不实现 tool trace / audit / timeline observer | 工具结果可被截断，后续 fetch_more 可补读；截断 / 补读不是不可审计黑盒 |
| P3 | Conversation Memory / RunInputBuilder | 迁移 Host 上下文治理核心，使多轮上下文可构造 | RunInputBuilder 可消费事实、客户端 timeline 展示事实、只可观测 facts 三类边界；pinned_state、memory pool、tool facts projection | 不做 context overflow 完整协作、不做 Reply Outbox、不把 reasoning 回流运行态 | 多轮 Run 可以基于 Session / memory 构造下一轮输入；reasoning 只进展示 read model |
| P4 | Host Compact for Context Overflow | 把 OLD 中原本在 Engine 内做的 compact 搬到 Host，使 Engine context overflow 时仍能继续运行 | Host compact 入口、compact 输入 / 输出、Engine overflow 事件 / 错误映射、compact 后 attempt 输入重建 | 不实现完整 context governance；不引入 replay / validation 联动；不在 Engine 内实现 compact/retry | Engine 遇到 context overflow 时，Host 完成 compact 后继续运行或明确失败收口 |
| P5 | No-Full-Governance Multi-Turn Smoke | 将 P1-P4 与 P1.5 串成最小纵向 smoke，并落地最小公共 tool declaration 与 framework `fetch_more` 能力 | smoke CLI / test harness、端到端多轮测试、公共 `@tool` declaration / `ToolDefinition`、LLM-facing truncation hint、framework `fetch_more` schema、必要 README / tests 文档 | 不做完整多进程治理、不做 Remote、不做 Outbox、不做 audit hard-gate；不验证 `start_run` 幂等、active Run 并发仲裁或调用重试语义；不做完整 ToolRegistry / 权限治理 / 业务工具迁移；不做自动透明补读 | 一个单调用方、顺序执行的无完整生产治理多轮会话可按目标事实层跑通，含工具截断补读、memory、compaction；手工 smoke 真实向 `mimo-v2.5-pro-plan` 发送 prompt，由模型调用公共声明的 `huge_echo`，再由模型根据 `truncation.next_action=fetch_more` 调用 framework `fetch_more` |
| P5.5 | Deferred Scope Reconciliation | 回看 P1-P5 所有“本阶段不实现”能力，确认没有遗留能力被漏排或误排 | deferred-scope inventory、能力归属表、后续 Phase 调整建议、必要的新 Phase / issue / plan 修订 | 不写生产代码；不把未落地能力补写成已落地事实；不直接修改后续 Phase 代码边界 | P1-P5 的非目标均被明确标记为已实现、已安排到 P6+、新增 Phase / issue 承接，或经用户确认关闭 |
| P6 | EventLog Persistence / Projection / Observers Hardening | 在 P1.5 最小事实层上建立可靠持久化与派生机制 | 持久 EventLog、projection checkpoint、tool trace observer、audit observer、timeline projection、observer retry / lag | 不把 trace 写回 Engine，不要求所有 observer hard-gate | tool trace / audit / timeline 可由 EventLog 幂等派生 |
| P7 | Session / Run Lifecycle Governance | 完整落地 Session / Run 状态机、admission policy、取消基础治理 | SessionManager、RunManager、RunSupervisor、状态机测试、cancel_run、生产级 admission policy | 不做 issue #3 的强制终止增强、不做 wait / suspend | 同 Session 单 active Run、幂等 start_run、取消基础收口稳定 |
| P8 | Attempt Lease / Recovery / 多进程并发 | 落地 AttemptSupervisor、lease / fencing、startup recovery | attempt 表 / store、owner token、stale cleanup、orphan recovery、多进程测试、lane runtime dependency 判断 | 不做 Remote RPC；不把 lane 实现为 Host 私有能力 | 多进程下迟到 owner 写入被拒绝，orphan / stale 可恢复或 LOST |
| P9 | Reply Outbox | 将 RunResult / final answer 可靠投影到外部信道 outbox | Outbox 状态机、delivery key、claim / retry / reconcile | 不实现具体 WeChat / Web delivery 业务适配 | final answer 到 outbox 无丢失窗口，重复 projection 不重复投递 |
| P10 | RemoteProxy / RemoteStub | 落地远程执行边界 | RemoteProxy、RemoteStub、cursor / ack / reconnect、remote cancel | 不让远程 Engine 回调 Host 执行工具 | Remote Agent = Engine + tools execute remotely |
| P11 | Wait / Suspend / Resume 协作 | 按 issue #4 拆子设计并落地等待协作能力 | WaitRecord、awaiting outcome、自动 resume、状态机与恢复测试 | 不把 `resume_run` 暴露为普通 public API | 等待型工具 / 长事务可 suspend、恢复、取消、超时 |
| P12 | Governance Hardening | 补齐取消增强、policy hard-gate、audit hard-gate、运行治理 | issue #3 增强、watchdog、强制终止、required projection、运维可观测性 | 不扩大 Host 业务语义 | Host 可作为强约束真源运行生产治理 |
| P13 | Full-Governance Multi-Turn Smoke / 文档收口 | 在 P6-P12 完整治理能力打开后，按 P5 同一验证面跑最终纵向 smoke，并更新当前事实文档、归档迁移过程文档 | full-governance smoke CLI / test harness、与 P5 对齐的验证面清单、`docs/code_review.md` 当前事实专项、必要 README、issue / PR 收口、phase 文档归档策略 | 不新增治理能力；不写未来设计为已落地事实；不误删 review 证据；不把 smoke failure 用文档绕过 | Full-Governance Multi-Turn Smoke 覆盖 P5 同一语义面：真实模型 tool calling、ToolRuntime truncate / framework `fetch_more`、Conversation Memory、context compact、EventLog persistence / observers、lifecycle / admission / recovery / audit hard-gate；日常 review prompt 与 README 均只描述当前已落地事实，迁移审计记录可追溯 |

### 4.1 第一批能力边界

P2 的 `truncate / fetch_more` 不绑定 P6 的 tool trace observer、audit observer 或 timeline projection。
这些 observer 只是后续阅读者，不能反向决定 P2 的实现形状。

P2 需要保证的是 ToolRuntime 最小运行事实不成为黑盒，例如：

- result truncated。
- cursor issued。
- fetch_more requested。
- fetch_more completed / failed。
- cursor expired / denied。

这些事实可以在 P2 phase plan 中选择进入 canonical RunEvent 或 ToolRuntime fact store；P6 observer
后续可以读取这些事实，但 P2 不实现 observer。

P3 的 Conversation Memory 必须提前对齐 EventLog / projection 边界。P3 phase plan 必须显式列出：

- RunInputBuilder 可消费事实，例如 pinned_state、memory pool、结构化 tool facts、
  evidence anchors、source references。
- 客户端 timeline 展示事实，例如 answer、reasoning 展示字段、tool summary、warnings/errors。
- 只可观测 / audit / trace 事实，例如内部治理事件、trace-only payload、debug sampling。

reasoning / preview delta 只能进入展示 read model，不得进入 RunInput replay、Memory pool 或
RunInputBuilder 运行态输入。P3 不能绕过 P1.5 的 RunEventStore 直接制造独立 transcript 真源。

P4 到 smoke 阶段只迁移 compact 的归属：把 OLD 中原本在 Engine 内完成的上下文压缩搬到 Host。
它的目标只是让 Engine 遇到 context overflow 时，Host 能基于 P3 的 RunInputBuilder 可消费事实
完成 compact，并用 compact 后的输入重建 attempt 继续运行。P4 不牵扯 replay、validation、
OutputContract 或完整 context governance。

P5 smoke 只覆盖单进程、单调用方、顺序执行 happy path：每轮等待上一轮 terminal 后再启动下一轮。
P5 需要最小 Run 创建事实和 Session 下多轮顺序，但不以生产级 `start_run` 幂等、
同 Session active Run admission policy、断线重试或并发输入仲裁为前提。这些治理能力仍留在 P7。
用户人工 review 后，P5 同时承接最小公共 tool declaration 与 framework `fetch_more` 能力：OLD-like
`@tool(..., truncate=ToolTruncateSpec(...))` 需要产出强类型 `ToolDefinition` / `ToolBundle`，
同源携带 LLM-facing schema、executor binding、Host ToolRuntime truncate metadata 与 display metadata。
这不是完整 ToolRegistry，也不恢复权限治理 / middleware / 业务工具迁移；但 P5 必须恢复 OLD 语义中的
LLM-facing truncation hint 与 framework `fetch_more` tool，使模型在同一个 run 内自行补读。
`huge_echo` 是该声明能力的首个 smoke/test 工具。
用户人工 review 已将手工 smoke 主目标改为真实 provider `mimo-v2.5-pro-plan` tool calling，缺配置应清晰失败，
不能把 fake provider 或 scripted WorkerProxy 作为主 smoke 成功证据。

P5.5 是非生产代码的总控核对阶段。它必须逐项回看 P1、P1.5、P2、P3、P4、P5 phase plan 中
“本阶段不实现”“明确不做”“后移”的能力，判断每项是否已经被后续 Phase 承接、需要调整到现有
P6+、需要新增 Phase / issue，或应经用户确认关闭。P5.5 的输出是排期与边界修订，不直接补实现；
如果发现某个能力会改变 P6+ 的目标、非目标或验收信号，必须更新总控计划并走对应 review gate。

P7 实施 `start_run` 幂等时，必须重新讨论并固定 `(session_id, client_request_id)` 如何幂等映射到
同一个 `run_id`：包括 `run_id` 由 Host 生成还是由持久 Run 创建事实确定、重复请求返回同一
`RunStream` / `RunHandle` 的精确语义、原 Run 已 terminal 或事件 cursor 已推进时的补读起点、
以及该映射依赖的持久唯一约束 / compare-and-set 边界。

## 5. Phase 文档命名

每个 Phase 使用固定文档命名：

```text
docs/host/phase{N}-plan.md
docs/host/phase{N}-plan-review.md
docs/host/phase{N}-code-review.md
docs/host/phase{N}-old-new-review.md
docs/host/phase{N}-pr-review.md
```

如果某个 Phase 需要专项 review，可追加：

```text
docs/host/phase{N}-{topic}-review.md
```

例如：

```text
docs/host/phase1_5-plan.md
docs/host/phase5_5-plan.md
docs/host/phase8-concurrency-review.md
docs/host/phase11-wait-state-review.md
```

小数 Phase 的文件名使用下划线，例如 P1.5 对应 `phase1_5-*`，P5.5 对应 `phase5_5-*`。

所有 review finding 修复后，必须在对应 review 文档的 finding 标题上标注修复状态；可在正文保留
“修复状态”说明作为证据，但标题状态是必需项。

## 6. Phase Plan 必填模板

每个 `phase{N}-plan.md` 必须包含：

- 目标。
- 非目标。
- 前置条件。
- 架构边界。
- 文件级改动清单。
- 新增 / 修改契约。
- 状态机变化。
- 数据持久化 / schema 变化。
- 多进程并发影响。
- ToolRuntime / EngineWorker / Engine 边界影响。
- EventLog / RunEventStore / projection 影响。
- 可接受临时实现 / 不可接受临时实现。
- runtime dependency；若涉及 lane，必须说明是否复用或扩展 `dayu.runtime`。
- 测试清单。
- 验证命令。
- README / docs 触发判断。
- review gate。
- 停止条件。
- 风险与回滚。
- 待用户确认项。
- 迁移 Agent 实施完成汇报格式。

涉及 schema 变更时，必须同时说明：

- NEW 按全新 schema 起库处理，不做旧库兼容读取。
- 是否需要将旧库迁移动作作为 `workspace_migrations` 插件进入 `dayu-cli init` 流程。

## 7. Review Gate

每个 Phase 至少需要两个 gate：

- plan review gate。
- code review gate。

必要时增加：

- OLD / NEW 对比 review。
- 最佳实践 review。
- 并发 / recovery 专项 review。
- 类型 / import boundary 专项 review。
- PR diff review。

P1 必须增加 EngineWorker public boundary gate：

- `EngineWorker.run_agent_messages` 不得成为 Host public API。
- `ToolExecutor.execute` 不得成为 Host public API。
- 调用方只能通过 Host 的 Run 入口或测试 harness 触达 Engine。
- EngineWorker 只能作为 Host capability / 内部 protocol 被装配和测试。
- 若 P1 代码或文档把 EngineWorker、ToolExecutor 暴露给 UI / Service 调用方，则 plan review
  或 code review 必须判定不通过。

P2 必须增加 OLD / NEW code review gate：

- P2 代码 review 除常规 code review Agent 外，必须额外派 OLD / NEW 对比 review Agent。
- OLD / NEW review 必须对照 OLD `TruncationManager`、OLD `fetch_more` schema、OLD
  `project_for_llm` 与 OLD 测试，确认 NEW 继承 cursor lifecycle、scope token、TTL、
  single-use、limit clamp、page structure 等底层可靠语义。
- OLD / NEW review 同时必须确认 P2 不误恢复 OLD LLM-facing `fetch_more` 半协议，也没有把
  OLD Engine 归属的实现机械迁回 `dayu.engine`。P5 若恢复 framework `fetch_more`，必须走 Host ToolRuntime
  ownership 与 Engine 普通 tool call 边界，不能恢复 OLD 完整 ToolRegistry / Engine-owned cursor manager。
- P2 code review 只有常规 code review 与 OLD / NEW 对比 review 均明确通过后，才允许停下来等用户
  人工 review。

review Agent 不能只按 checklist 打勾；OLD Host 中可靠行为应作为强参考源，review 应开放式寻找
遗漏能力、边界泄漏、状态机漏洞、幂等缺口、数据丢失窗口和多进程竞争问题。

## 8. 验证与文档规则

每个代码 Phase 必须运行：

```bash
source .venv/bin/activate
python -m pyright
```

并运行该 Phase 影响范围内的测试。若某 Phase 只改文档，可以只运行 pyright，并在最终说明中说明
未跑 pytest 的原因。

README 更新遵循 `AGENTS.md`：

- 除 `tests/README.md` 外，其它 README 默认等迁移结束或对应代码事实落地后再改。
- 命中 README 触发条件时，必须先判断是否属于该 README 的职责范围。
- README 只写当前已落地事实，不写未来设计。

`docs/code_review.md` 更新规则：

- 每完成一个代码 Phase 且用户确认该 Phase 事实已经落地后，更新日常 review prompt 的当前事实专项。
- `docs/code_review.md` 不要求 review Agent 理解迁移过程，只描述当前代码事实和 review 应检查的边界。

## 9. GitHub / PR 规则

每个 Phase 默认一个 ready PR。

PR 准备前必须确认：

- 当前分支只包含本 Phase 范围内提交。
- plan commit 与 code commit 边界清楚。
- review 文档中的 finding 修复状态已经标注。
- 测试与 pyright 结果已记录。
- README / docs 触发判断已记录。

PR 创建后：

- 派 PR review Agent 审查 PR diff。
- PR review 不通过时，继续修复、补 review 修复状态、补 commit、复审。
- PR review 通过后停下来等用户确认。
- squash merge PR 并删除远端分支默认由用户执行；只有用户明确指示总控 Agent 执行时，
  总控 Agent 才能执行 squash merge / delete branch。
- 用户手工 merge 后，总控记录结果，确认目标分支已包含该 PR 后再进入下一 Phase。

## 10. 总控检查清单

每个 Phase 结束前，总控 Agent 必须确认：

- Phase 目标已完成，非目标未被偷做。
- 没有旧接口兼容 wrapper / facade / re-export。
- 没有 Engine -> Host / Service / UI 反向依赖。
- 没有 Host / Engine 内嵌业务知识。
- 财报文档访问仍只能通过 `dayu.fins.storage` 由业务工具 / tool 边界保证。
- 没有 `Any`、`object`、无类型参数、无类型返回值扩散到公共契约。
- review finding 已修复或明确后移，且 review 文档有修复状态。
- 测试与 pyright 通过，或阻塞原因清楚。
- `docs/code_review.md` 与 README 的触发判断已完成。
- phase plan / review / code review 默认保留为迁移审计记录；迁移结束后只有经用户确认才归档或移动。

## 11. 第一批 Phase 的启动顺序

P1、P1.5 与 P2 已完成并合入 `main`。当前启动 P3；P3 的 handoff plan 应重点回答：

- RunInputBuilder 可消费哪些 canonical RunEvent / ToolRuntime facts，哪些事实只进入展示 read model。
- Conversation Memory 的最小 Host 边界是什么，哪些属于 public Run / Session 级接口，哪些必须保持
  Host 内部 projection / store。
- P3 如何强参考 GitHub issue #48 与 OLD `conversation_memory.py` / `conversation_store.py` /
  `conversation_session_archive.py` / `scene_preparer.py`，守住 `pinned_state` 全量独立、历史单总池、
  最近 N 轮 raw turn 下限保底、memory 克制等财报 Agent 记忆不变量。
- preview / reasoning / delta 是否严格禁止进入 RunInput replay、Memory pool 与 RunInputBuilder 运行态输入。
- P3 如何使用 P1.5 EventLog 与 P2 ToolRuntime facts，避免旁路 transcript、memory facts 或 tool result
  真源。
- 多轮 Session 的最小顺序 smoke 如何表达，且不提前实现 P7 active Run admission、幂等或完整 lifecycle
  governance。
- P3 不提前实现 P4 context overflow compact、P6 persistent projection / observer、P7 lifecycle governance、
  P9 outbox 或完整多进程 recovery。

P3 plan review 通过且用户确认后，才能进入 P3 代码实现。
