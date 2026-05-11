# Host 迁移总控计划

本文档是 Dayu Host 迁移的**总控状态索引**。它只记录 phase 边界、当前 gate、
Dayu 项目级约束、artifact 索引和仍需追踪的 residual risks；不复制 `$gateflow`
通用流程，也不保存每个 slice 的实施流水账。

具体设计与执行细节分别以这些文件为真源：

- 通用流程：`/Users/leo/.codex/skills/gateflow/SKILL.md`
- Host 架构与接口边界：`docs/host/design.md`
- 当前已落地 Host 开发事实：`dayu/host/README.md`
- 每个 phase 的 handoff plan：`docs/host/phase{N}-plan.md`
- 每个 review gate 的 artifact：`docs/host/phase*-review*.md`、`docs/reviews/*.md`

## 1. 当前总控状态

- 当前 phase：P8.5 — P8 Stabilization / ToolRuntime Event Model。
- 当前分支：`migration/host-p8-5-stabilization`。
- P8 PR：#40 已 merge。
- 当前 gate：P8.5 implementation slices complete；按用户指令停下汇报，不自动 push / PR / merge。
- 最新 plan artifact：`docs/host/phase8.5-plan.md`。
- 最新 plan review artifact：`docs/host/phase8.5-plan-review.md`（fail，7 findings 全部 accepted）；
  `docs/host/phase8.5-plan-rereview.md` 已通过。
- 当前待处理事项：无剩余 implementation slice；等待用户授权是否进入 P8.5 PR gate。
- 下一入口：P8.5 PR gate / PR review gate；P8.5 PR closeout 后进入 P8.6 Recovery Model Re-challenge。

## 2. Dayu Host Gateflow 扩展

除非用户明确改变流程，Host 迁移按 `$gateflow` 执行。本文档只补充 Dayu 项目级约束：

- 每个 phase 默认使用独立工作分支，命名为 `migration/host-p{phase}-{short-name}`。
- 当前远端名是 `github`；push / PR 前必须用 `git remote -v` 或等价命令确认，不假设远端叫 `origin`。
- controller 负责维护 gate 状态、裁决 findings、生成 worker handoff prompt、检查 artifact 与 residual owner。
- worker prompt 不得要求 worker 启动 `$gateflow`；worker 只执行当前 handoff 的 implementation / fix / review / re-review 角色。
- review artifact 必须落盘；conversation-only review 不足以通过 gate。
- 每个 finding 必须裁决为 `accepted`、`rejected-with-reason`、`deferred-with-owner` 或 `needs-more-evidence`。
- accepted finding 必须修复并 re-review；deferred finding 必须有 phase、issue 或 user decision owner。
- PR 创建默认由 controller 执行；merge / delete branch 默认由用户执行，除非用户明确授权 controller 操作。

## 3. 分层与文档约束

- 严格遵守 `UI -> Service -> Host -> Engine`；Host 是 Agent / Run / ToolRuntime lifecycle 与治理真源。
- `dayu.runtime` 只能承载层中立运行期基础设施，不得 import Host / Engine / Service / UI。
- Engine 只提供强类型 `EngineEvent`、函数式入口、Runner / Agent 事件流和 `ToolExecutor` 协议；Host ToolRuntime、trace、memory、attempt ownership 不得回流 Engine。
- Dayu 是本地 Agent。EventLog / trace 对普通 tool calling payload 默认保留，只做窄 credential scrub：
  除 `API_KEY` / 明确凭证外，不得仅因字段名是 cursor、`scope_token`、tool args 或 tool result 就删除或遮蔽。
  Conversation Memory / RunInput 是独立 ingestion policy：短期 cursor / `scope_token` capability 不进入长期
  memory 或下一轮 RunInput，但这不是 EventLog / trace 字段级遮蔽。
- README 只写当前已落地事实：
  - `dayu/host/README.md` 面向开发者，写接口、架构、边界、执行路径、状态机、事件流、关键治理机制。
  - `docs/host/design.md` 在 README 基础上稍加机制细节和取舍，但不展开成源码说明书。
  - `dayu/engine/README.md` 不写 Host P8 实现细节。
- `docs/code_review.md` 只写日常 review 当前事实专项，不写迁移过程要求。

## 4. Phase 总览

| Phase | 名称 | 状态 | 核心目标 | 验收信号 |
| --- | --- | --- | --- | --- |
| P0 | 计划与议题同步 | completed | 固定 Host 迁移总控计划与初始议题 | 用户确认进入 P1 |
| P1 | EngineWorker + 最小 Run Harness | merged PR #16 | Host 可通过 local worker 调 Engine 函数式入口 | 单 Run 经 Host 流出事件，EngineWorker 不成为 public API |
| P1.5 | Minimal EventLog / RunEventStore | merged PR #17 | 建立 append-before-stream 最小事件事实层 | P2-P5 不再旁路 transcript / memory facts |
| P2 | ToolRuntime truncate / fetch_more | merged PR #18 | 迁移 truncation / cursor / TTL / scope token | 工具结果可截断并经 framework tool call 补读 |
| P3 | Conversation Memory / RunInputBuilder | merged PR #19 | Host 基于 facts 构造多轮 RunInput | 多轮 Run 可从 memory snapshot 构造下一轮输入 |
| P4 | Host Compact for Context Overflow | merged PR #21 | context overflow 后由 Host compact 并 retry | overflow 后继续运行或明确失败收口 |
| P5 | No-Full-Governance Multi-Turn Smoke | merged PR #22 | P1-P4/P1.5 串成无完整治理纵向 smoke | 单调用方顺序多轮含 tool truncation / fetch_more / memory / compact |
| P5.5 | Deferred Scope Reconciliation | merged PR #25 | 重新归属 P1-P5 deferred scope | 漏排能力被安排到后续 phase / issue / user decision |
| P6 | Durable EventLog / Run State / Projection | merged PR #26 | SQLite WAL durable facts、Run state、projection checkpoint、observer 基础 | durable append / replay / checkpoint / projection smoke 通过 |
| P7 | Tool Trace Projection / Sink | merged PR #37 | Host observer / sink 派生 tool trace | trace projection 从 canonical facts 幂等重建 |
| P8 | Attempt Lease / Recovery / Multiprocessing | merged PR #40 | owner token、fencing、attempt supervisor、diagnostic recovery、durable memory、multiprocessing stress | 迟到 owner 被 fenced；terminal close 原子；P8 smoke 通过 |
| P8.5 | P8 Stabilization / ToolRuntime Event Model | implementation complete | 在 P9 lifecycle 前收口 P8 稳定性尾巴：纠正 framework `fetch_more` / cursor / truncation 专属 RunEventType 事件模型，并补齐 durable memory / trace / capacity / adversarial coverage 稳定性问题 | EventLog 只记录普通 tool calling；`fetch_more` 作为 Host 私有 framework built-in tool 投影 schema；`RuntimeTruncateManager` 持有截断 / cursor 状态；P8 已落地 attempt lease / recovery / multiprocessing 在 P8.5 后稳定可用 |
| P8.6 | Recovery Model Re-challenge | planned | 在 P9 lifecycle 前重新挑战 P8 的 recovery 概念边界：corrupt memory snapshot row、recovery scan、startup_reconcile 是否应作为正常恢复路径存在，还是暴露了 Attempt Lease / Recovery / Multiprocessing 设计不够闭合 | 形成 handoff-ready 调查 plan；明确哪些 recovery 是 self-healing system invariant，哪些属于 operator repair / quarantine / disaster recovery，哪些应回到 P9/P15/P16 |
| P9 | Session / Run Lifecycle Governance / Public Interface | planned | admission、同 Session active Run、cancel 基础治理、Host public interface 固定 | lifecycle/admission/cancel smoke 通过，public exports 冻结 |
| P10 | ToolRegistry Governance | planned | 通用工具注册、权限、middleware、registry audit | 通用工具可注册、授权、审计，Engine 只见 schema / executor |
| P10.5 | Web Tools Migration Smoke | planned | 迁移代表性 web tool 验证真实工具链路 | 至少一个 web tool 通过 ToolRegistry / ToolRuntime / trace / memory smoke |
| P11 | OutputContract / Validation Replay | planned | 输出契约、验证决策、replay attempt | validation decision / replay 可审计且恢复后不丢 |
| P12 | Reply Outbox | planned | final answer / RunResult 可靠投影到外部 outbox | outbox claim / retry / reconcile smoke 通过 |
| P13 | RemoteProxy / RemoteStub | planned | 远程执行边界、cursor / ack / reconnect / cancel | remote smoke 可观察断线恢复与 cancel |
| P14 | Wait / Suspend / Resume | planned | 等待型工具 / 长事务 suspend-resume 协作 | wait / resume / timeout / cancel 状态机稳定 |
| P15 | Governance Hardening | planned | watchdog、hard-gate、schema bootstrap 严格治理、可观测性 | hard-gate / watchdog / 强制终止 smoke 通过 |
| P16 | Full-Governance Smoke / Docs / Interface Freeze | planned | 全治理纵向 smoke、文档收口、Engine/Host interface freeze | full-governance smoke 覆盖 P5/P10.5 语义面，契约变更治理固定 |

### 4.1 未实施 Phase 边界索引

以下表格保留 P8.5 及以后未实施 phase 的关键输出与明确非目标；完整实现细节仍必须在对应
`phase{N}-plan.md` 中重新写成 handoff-ready plan。

| Phase | 关键输出 | 明确非目标 |
| --- | --- | --- |
| P8.5 | ToolRuntime event model root-cause plan、删除 `TOOL_FETCH_MORE_REQUESTED` / `TOOL_FETCH_MORE_COMPLETED` / `TOOL_FETCH_MORE_FAILED`、`TOOL_CURSOR_*`、`TOOL_RESULT_TRUNCATED` 等专属 RunEventType 的实施决策、EventLog 只记录普通 `TOOL_CALL_REQUESTED` / `TOOL_RESULT_ACCEPTED`、Host 私有 `fetch_more` framework tool schema 投影、`RuntimeTruncateManager` 截断 / cursor 状态边界、serializer / contracts / trace / memory / smoke / docs 同步、durable memory repair 容量与 damaged snapshot 策略、ToolTraceObserver async I/O 边界、RunInput snapshot side store 策略、P8 adversarial coverage gaps、`docs/host/phase8.5-plan.md` | 不恢复 legacy public fetch_more handle；不提前实现完整 P10 ToolRegistry；不把 ToolRuntime 业务语义放入 `dayu.runtime`；不把具体工具名、cursor 或 truncation 继续编码成 RunEventType；不在缺少直接证据时断言 EventLog batch append 一定需要或一定不需要；不做 P9 Session / Run lifecycle admission；不做 P16 public/internal bundle interface freeze |
| P8.6 | Recovery Model Re-challenge plan、对 `corrupt durable memory snapshot row` / `recovery scan` / `startup_reconcile` 的同源调查、Attempt Lease / Recovery / Multiprocessing 自愈边界审计、与 ZooKeeper / Kafka / etcd 等成熟系统的 recovery / operator intervention 原则对照、operator repair / quarantine / auto-rebuild policy 候选、后续 phase owner 重新归档 | 不在 P8.6 plan 前改 recovery 代码；不把“能 repair”默认当成“应存在 recovery”；不把运维手工介入当作正常路径；不做 P9 Session lifecycle admission；不做 P15 hard-gate/watchdog；不做 P16 interface freeze |
| P9 | SessionManager、RunManager、RunSupervisor、`client_request_id` 幂等、同 Session active Run 仲裁、`cancel_run`、生产级 admission policy、Host public interface 契约、OLD wechat / web / prompt / interactive 调用需求调研、`utils/smoke_host_p9_lifecycle.py` | 不做 issue #3 强制终止增强；不做 wait / suspend / resume；不做 Remote RPC；不迁移业务工具 |
| P10 | ToolRegistry / tool catalog、display metadata、permission policy、middleware chain、framework tool registration、schema / binding 校验、registry audit facts、`utils/smoke_host_p10_tool_registry.py` | 不迁移 business fins / doc / web 工具；不让 Host / Engine 承载财报业务语义；不让 Engine 持有 registry |
| P10.5 | 代表性 web tool `@tool` declaration、ToolRegistry 注册、permission / middleware / display metadata 对接、ToolRuntime truncate / fetch_more 适配、tool trace / memory facts smoke、`utils/smoke_host_p10_5_web_tools.py` | 不迁移 fins / doc 全量业务工具；不把 web 业务语义塞进 Host / Engine；不扩大 P10 ToolRegistry 契约；不实现 P11 validation replay |
| P11 | OutputContractRef、ValidationDecision fact、validator execution boundary、replay attempt policy、replay 上限、恢复 / 失败收口测试、`utils/smoke_host_p11_validation_replay.py` | 不把 validation 混入 P4 compact retry；不把 audit hard-gate 当成 validation replay；不实现业务 validator 全量规则库 |
| P12 | Outbox 状态机、delivery key、claim / retry / reconcile、`utils/smoke_host_p12_reply_outbox.py` | 不实现具体 WeChat / Web delivery 业务适配 |
| P13 | RemoteProxy、RemoteStub、cursor / ack / reconnect、remote cancel、`utils/smoke_host_p13_remote_proxy.py` | 不让远程 Engine 回调 Host 执行工具 |
| P14 | WaitRecord、awaiting outcome、自动 resume、状态机与恢复测试、取消 / 超时语义、`utils/smoke_host_p14_wait_resume.py` | 不把 `resume_run` 暴露为普通 public API；不把 wait 伪装成普通 tool failure |
| P15 | issue #3 增强、watchdog、强制终止、required projection、schema bootstrap 严格事务化 / 半失败治理评估、运维可观测性、`utils/smoke_host_p15_governance_hardening.py` | 不扩大 Host 业务语义；不补 business tools 迁移 |
| P16 | full-governance smoke CLI / test harness、与 P5 / P10.5 对齐的验证面清单、代表性 web tool 完整治理链路 smoke、`InMemoryRunEventStore` 收口决策、Engine / Host interface freeze、契约变更治理规则、`docs/code_review.md` 当前事实专项、必要 README、issue / PR 收口、phase 文档归档策略 | 不新增治理能力；不写未来设计为已落地事实；不误删 review 证据；不把 smoke failure 用文档绕过；不允许未走接口变更流程的 Engine / Host 契约修改；不迁移 fins / doc 全量业务工具 |

## 5. P8 / P8.5 当前事实摘要

P8 已在 PR #40 merge。当前 P8 事实以代码、`dayu/host/README.md`、`docs/host/design.md` 和 PR #40
review artifacts 为准：

- `AttemptLeaseStore` / `AttemptSupervisor` 提供 owner token、全局单调 fencing token、lease renew、owner CAS。
- terminal close 通过 `append_terminal_and_close` 在单个 `BEGIN IMMEDIATE` 事务内完成 owner verify、
  terminal RunEvent append、attempt close 和 `terminal_event_position` 写入。
- recovery scan 只做 diagnostic close：候选 attempt 进入 `MARK_LOST` / `NOOP_TERMINAL`，不创建无人持有
  owner secret 的 recovery attempt。
- durable path 不允许 `PlainRunEventAppender` fallback；attempt-scoped canonical fact 写入必须在 owner scope
  内完成。
- production `InMemoryConversationMemoryStore` 已删除；durable harness 默认装配
  `DurableConversationMemoryStore`，并支持 checkpoint caught-up 后 missing snapshot repair。
- multiprocessing stress 覆盖 file SQLite append、terminal close、stale recovery、observer startup reconcile
  既有语义；慢硬盘 / Docker Linux stress 仍由 issue #38 跟踪。

P8.5 当前 Slice 1 至 Slice 6 均已通过 implementation review loop，并已创建 accepted local commits：

- ToolRuntime / EventLog 已收敛为 generic tool-calling event model。EventLog 只记录普通
  `TOOL_CALL_REQUESTED` / `TOOL_RESULT_ACCEPTED`；`fetch_more` 是 Host 私有 framework built-in tool，
  对 Engine 只是普通 tool schema / tool request / tool outcome。
- `RuntimeTruncateManager` 持有 Host 私有截断状态机和 cursor store；Runtime 只组合 manager，在普通 tool result
  返回前做可选截断，并通过闭包把补读能力传给私有 `fetch_more` callable。
- P8.5 follow-up fixed residual：`ToolTruncationInfo` public contract leakage 已移除；`ToolResultSuccess`
  不再携带 top-level `truncation` 字段，LLM-facing truncation / `fetch_more_args` 只作为 Host 注入的普通
  `ToolResultSuccess.value` JSON payload 存在，Engine 只做普通 JSON tool result projection。
- EventLog / trace 默认保留 ordinary tool args/result payload，只 scrub API key、Authorization、cookie、
  client secret、private key、password 等明确凭证；cursor、`scope_token`、普通 `token`、tool args/results
  不是敏感字段 scrub 触发条件。
- Conversation Memory / RunInput 是独立 ingestion policy：raw cursor、raw `scope_token` 和可复用的
  `truncation.fetch_more_args` 不进入长期 memory 或下一轮 RunInput。
- corrupt memory snapshot row 不自动覆盖；P8.5 只提供 typed diagnostic + WARNING。其产生根因、quarantine、
  运维命令与长期自动覆盖策略由 GitHub issue #41 跟踪。
- non-required trace JSONL/blob sink 采用事务外 at-least-once 写入；checkpoint 只在 sink success 后推进，重复
  JSONL/blob 由 reader / analyzer 按 `idempotency_key` 去重。
- `RUN_INPUT_CONTEXT_SNAPSHOT_BUILT` hot row 不再内联无界 raw payload；raw input messages / tool schemas 写入
  `run_input_raw_payloads` side-store，并与 EventLog fact append 在同一 Host storage transaction 内提交。
- P15 hard-gate / required projection enforcement / watchdog、P9 Session / Run lifecycle admission、P16
  public/internal bundle freeze 均不是 P8.5 已实现内容。
- P8.6 将在 P8.5 PR closeout 后专门重审 recovery 概念：corrupt durable memory snapshot row、
  recovery scan、startup_reconcile 不能分散作为孤立 residual 处理；需要从 Attempt Lease / Recovery /
  Multiprocessing 的自愈不变量出发，挑战“实现良好的系统是否还应需要 recovery / 运维干预”。

P8 cleanup 后的 stale / orphan recovery 旧术语（`MARK_RECOVERING_AND_CREATE_ATTEMPT`、新 recovery attempt、
`recovered_from_attempt_id` 自动写入等）均已废弃。若历史 phase plan / review artifact 仍保留这些词，只作为
审计上下文。

## 6. Residual Risk Registry

| Risk | Owner / Destination | Status |
| --- | --- | --- |
| P8 PR review 1939-F1：ToolRuntime catch-all 吞 `AttemptFencingError` | PR #40 | fixed, validated |
| P8 PR review 1939-F3：`_handle_owner_lost` 普通异常后 active attempt 未清理 | PR #40 | fixed, validated |
| P8 PR review 1939-F4：STALE fencing 诊断未归类为 terminal | PR #40 | fixed, validated |
| P8 PR review 1939-F5：durable memory snapshot clock 未注入 | PR #40 | fixed, validated |
| P8 PR review 1943-F1：durable memory observer 非终态 checkpoint 后重启丢 pending facts | PR #40 | fixed, validated |
| P8 PR review 1943-F2：旧 public `ToolFetchMoreHandle*` contracts 仍导出 | PR #40 | fixed, validated |
| P8 PR review 1948-F1：durable `_scope_appender()` 无 owner scope 静默 fallback | PR #40 | fixed, validated |
| P8 PR review 2044-F1~F6：scope 调用 / RECOVERING / lease_exit_stack / cursor mutation / terminal set / diagnostic log | PR #40 | fixed, validated |
| P8 PR review 2044-F4 residual：`fetch_more` 曾用专属 RunEventType + 多 fact 表达，暴露 completed + cursor issued partial fact 风险；P8.5 已删除专属 facts，EventLog batch append 仍为非目标，除非出现新的非 cursor 专属 facts 直接证据 | P8.5 Slice 1 | fixed, validated |
| `TOOL_FETCH_MORE_REQUESTED` / `TOOL_FETCH_MORE_COMPLETED` / `TOOL_FETCH_MORE_FAILED` 将具体 Host built-in tool 名编码进 RunEventType，未来每新增内置工具都可能诱导新增事件类型 | P8.5 Slice 1 | fixed, validated |
| `TOOL_CURSOR_ISSUED` / `TOOL_CURSOR_EXPIRED` / `TOOL_CURSOR_DENIED` / `TOOL_RESULT_TRUNCATED` 已裁决为不进入 EventLog 专属 facts；cursor / truncation 只作为普通 tool call/result payload 或 Host 私有 manager 状态存在 | P8.5 Slice 1 | fixed, validated |
| P8 PR review 2051-F1~F5 + T2~T4：session leak / verify_run_id / observer CAUGHT_UP / lastrowid / RECOVERING / coverage tests | PR #40 | fixed, validated |
| P8 PR review 1948-F2：`_verify_run_id_matches()` 缺独立 RUN_ID_MISMATCH reason，run_id 不匹配的内部不变量违反不应与 owner token mismatch 共用 `OWNER_MISMATCH` | P8.5 Slice 5a | fixed, validated |
| durable memory repair 按 session 扫描 EventLog 的容量风险 | P8.5 Slice 2 | fixed, validated |
| durable memory snapshot row 存在但 payload 损坏时 repair 不可见 | P8.5 Slice 2 | fixed, validated：typed diagnostic + WARNING，不自动覆盖 |
| corrupt durable memory snapshot row 的产生根因、quarantine / 运维命令 / 长期自动覆盖策略 | P8.6 / GitHub issue #41 | tracked; not solved by P8.5 |
| `recover_stale_attempts(run_id=None)` 全局扫描路径未单测 | PR #40 | fixed (T2 test added) |
| `next_attempt_index` 未独立单测 | P8.5 Slice 5a | fixed, validated |
| P8 PR review 2242/2247 coverage-only gaps：renew/terminal race、recovery CAS miss、owner-lost late event、terminal override、expired/denied fencing 等 adversarial tests | P8.5 Slice 5b | fixed, validated |
| P8 PR review 0612/0613 low findings：`_renew_loop` STORAGE_ERROR 异常分类、BUSY reason 细化、`lease_context` 参数校验等 attempt lease 诊断 / 防御性边界 | P8.5 Slice 5a / Slice 5b | fixed, validated for approved scope |
| recovery scan 是否应作为正常生产启动链路存在，还是暴露 Attempt Lease / Recovery 模型未闭合 | P8.6 | deferred-with-owner |
| `startup_reconcile` 是否应作为正常启动恢复路径存在，还是应被更强 lifecycle / projection invariant 取代 | P8.6 | deferred-with-owner |
| `HostStorage.close()` 对后台 task / `to_thread` commit 无生命周期保护 | P9 lifecycle | deferred-with-owner |
| compact 成功 / 失败路径中诊断 fact 与 terminal fact 分步 append 导致的诊断事件精度、孤立诊断 fact 与原子性取舍 | P8.5 Slice 4 | fixed for approved compact / SSE partial semantics; broader lifecycle admission remains P9 |
| observer 在空 EventLog 且 `last_success_position is None` 时无法明确转 `CAUGHT_UP` | PR #40 | fixed (zero-event observer advance) |
| non-required trace observer I/O 与 checkpoint transaction 解耦 | P8.5 Slice 3 | fixed, validated; at-least-once duplicate 由 `idempotency_key` 去重 |
| observer claim lease / hard-gate / required projection enforcement / watchdog | P15 / GitHub issue #28 | deferred-with-owner; not implemented by P8.5 |
| 慢硬盘 + Docker Linux multiprocessing stress 稳定性 | GitHub issue #38 | tracked |
| Tool Trace JSONL 文件滚动边界 | GitHub issue #36 | tracked |
| `ToolTraceObserver.process` 在 async observer 协议内执行同步 JSONL / blob 文件 I/O，需评估 executor / outbox / backpressure 边界 | P8.5 Slice 3 | fixed, validated：non-required sink 使用 `process_non_transactional` + `asyncio.to_thread` |
| compact retry 合成 `RunInputContextSnapshotBuiltData` 的 `iteration_index` / `attempt_index` 语义对齐 | P8.5 Slice 4 | fixed, validated |
| SSE 中途失败导致 provider protocol error 缺少完整 trace 语义，主要验收入口是 `utils/analyze_tool_trace_host.py` 能显示 bounded partial tool-call summary | P8.5 Slice 4 | fixed, validated for provider protocol errors |
| provider stream transport-layer read failure 仍走 HTTP error 语义，缺少 partial tool-call diagnostic 覆盖 | P16 interface freeze | deferred-with-owner; provider adapter coverage to be rechecked with Engine / Host contract freeze |
| `RUN_INPUT_CONTEXT_SNAPSHOT_BUILT` 内联 raw payload 造成 EventLog 热冷混合与体积增长 | P8.5 Slice 4 | fixed, validated：raw payload moved to `run_input_raw_payloads` side-store |
| `LocalRunHarness` 职责继续膨胀，接近 God Object 阈值 | P9 / P16 architecture | deferred-with-owner |
| `DurableHarnessBundle` 暴露 attempt supervisor / lease store 等 Host internal 治理对象，public/internal bundle 边界需在接口冻结前收口 | P16 interface freeze | deferred-with-owner |
| `_LeaseSession.stopped_event` 死同步原语、`_tool_outcome_name` fallback、legacy `AttemptStateStore.update_state` CAS 保护、internal module `__all__` 清理等非阻塞内部清洁度问题 | P16 interface freeze | deferred-with-owner |
| schema bootstrap 半失败治理 / 严格事务化 DDL | P15 | deferred-with-owner |
| observer hard-gate / required projection enforcement / watchdog 级治理 | P15 | deferred-with-owner |
| `InMemoryRunEventStore` 生产语义最终收口 | P16 interface freeze | deferred-with-owner |
| observer direct-call 测试 fake transaction 类型收口 | P16 interface freeze | deferred-with-owner |
| P8-S3 测试 fake 依赖具体 `AttemptSupervisor`，是否抽 `AttemptSupervisorPort` | P16 interface freeze | deferred-with-owner |
| Engine / Host public contract freeze | P16 | deferred-with-owner |

已完成且有 artifact 的历史 findings 不在本 registry 重复展开；需要审计时回看对应 phase review / rereview artifact。

## 7. Artifact 命名

默认命名：

```text
docs/host/phase{N}-plan.md
docs/host/phase{N}-plan-review.md
docs/host/phase{N}-plan-rereview.md
docs/host/phase{N}-s{slice}-code-review.md
docs/host/phase{N}-s{slice}-fix-rereview.md
docs/reviews/pr-{number}-review-{yyyymmdd-hhmm}.md
docs/reviews/pr-{number}-fix-rereview-{yyyymmdd}.md
```

专项 review 可在主题名中体现，例如：

```text
docs/host/phase8-concurrency-review.md
docs/host/phase14-wait-state-review.md
docs/reviews/code-review-cleanup-rereview-20260510.md
```

## 8. Closeout Checklist

每个 phase / PR closeout 前，controller 必须确认：

- 当前 branch 只包含该 work unit intended commits。
- plan / code / PR review artifacts 均已落盘并记录。
- accepted findings 已修复并 re-reviewed。
- rejected findings 有 reason；deferred findings 有 owner / issue / phase。
- required tests、smoke、pyright、`git diff --check` 已运行或失败已说明。
- README / design.md / tests README 的触发判断已完成，只写当前事实。
- residual risk registry 已更新。
- PR summary 与真实代码一致，不把 future work 写成已完成。
