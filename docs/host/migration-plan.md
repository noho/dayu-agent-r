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

- 当前 phase：P8 Attempt Lease / Recovery / 多进程并发基础。
- 当前分支：`migration/host-p8-attempt-lease-recovery`。
- 当前 PR：#40 — `[codex] Host P8 durable attempt governance`。
- 当前 gate：PR review fix loop。
- 最新 accepted commit：`756f150 gateflow: accept pr-40 review fixes`。
- 最新 PR review artifact：`docs/reviews/pr-40-review-20260510-1808.md`。
- 当前待处理 review findings：
  - accepted：compact / worker 异常路径中的 `AttemptFencingError` 需统一 owner-lost 收口，且不能恢复裸 terminal append。
  - accepted：owner token hash 比较改用 `hmac.compare_digest`。
  - accepted：`RunInputContextSnapshotBuiltData` 等活跃 `RunEventData` 嵌套类型补齐包根导出。
  - deferred-with-owner：durable memory repair 全 EventLog 扫描性能，owner 为 P9 / capacity。
- 下一入口：完成 PR review 1808 findings 的 fix / re-review / user confirmation / accepted fix commit。

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
| P8 | Attempt Lease / Recovery / Multiprocessing | PR #40 open | owner token、fencing、attempt supervisor、diagnostic recovery、durable memory、multiprocessing stress | 迟到 owner 被 fenced；terminal close 原子；P8 smoke 通过 |
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

以下表格保留 P9 及以后未实施 phase 的关键输出与明确非目标；完整实现细节仍必须在对应
`phase{N}-plan.md` 中重新写成 handoff-ready plan。

| Phase | 关键输出 | 明确非目标 |
| --- | --- | --- |
| P9 | SessionManager、RunManager、RunSupervisor、`client_request_id` 幂等、同 Session active Run 仲裁、`cancel_run`、生产级 admission policy、Host public interface 契约、OLD wechat / web / prompt / interactive 调用需求调研、`utils/smoke_host_p9_lifecycle.py` | 不做 issue #3 强制终止增强；不做 wait / suspend / resume；不做 Remote RPC；不迁移业务工具 |
| P10 | ToolRegistry / tool catalog、display metadata、permission policy、middleware chain、framework tool registration、schema / binding 校验、registry audit facts、`utils/smoke_host_p10_tool_registry.py` | 不迁移 business fins / doc / web 工具；不让 Host / Engine 承载财报业务语义；不让 Engine 持有 registry |
| P10.5 | 代表性 web tool `@tool` declaration、ToolRegistry 注册、permission / middleware / display metadata 对接、ToolRuntime truncate / fetch_more 适配、tool trace / memory facts smoke、`utils/smoke_host_p10_5_web_tools.py` | 不迁移 fins / doc 全量业务工具；不把 web 业务语义塞进 Host / Engine；不扩大 P10 ToolRegistry 契约；不实现 P11 validation replay |
| P11 | OutputContractRef、ValidationDecision fact、validator execution boundary、replay attempt policy、replay 上限、恢复 / 失败收口测试、`utils/smoke_host_p11_validation_replay.py` | 不把 validation 混入 P4 compact retry；不把 audit hard-gate 当成 validation replay；不实现业务 validator 全量规则库 |
| P12 | Outbox 状态机、delivery key、claim / retry / reconcile、`utils/smoke_host_p12_reply_outbox.py` | 不实现具体 WeChat / Web delivery 业务适配 |
| P13 | RemoteProxy、RemoteStub、cursor / ack / reconnect、remote cancel、`utils/smoke_host_p13_remote_proxy.py` | 不让远程 Engine 回调 Host 执行工具 |
| P14 | WaitRecord、awaiting outcome、自动 resume、状态机与恢复测试、取消 / 超时语义、`utils/smoke_host_p14_wait_resume.py` | 不把 `resume_run` 暴露为普通 public API；不把 wait 伪装成普通 tool failure |
| P15 | issue #3 增强、watchdog、强制终止、required projection、schema bootstrap 严格事务化 / 半失败治理评估、运维可观测性、`utils/smoke_host_p15_governance_hardening.py` | 不扩大 Host 业务语义；不补 business tools 迁移 |
| P16 | full-governance smoke CLI / test harness、与 P5 / P10.5 对齐的验证面清单、代表性 web tool 完整治理链路 smoke、`InMemoryRunEventStore` 收口决策、Engine / Host interface freeze、契约变更治理规则、`docs/code_review.md` 当前事实专项、必要 README、issue / PR 收口、phase 文档归档策略 | 不新增治理能力；不写未来设计为已落地事实；不误删 review 证据；不把 smoke failure 用文档绕过；不允许未走接口变更流程的 Engine / Host 契约修改；不迁移 fins / doc 全量业务工具 |

## 5. P8 当前事实摘要

P8 当前在 PR #40 review/fix loop，已落地或正在收口的核心事实如下：

- `AttemptLeaseStore` / `AttemptSupervisor` 提供 owner token、全局单调 fencing token、lease renew、owner CAS。
- terminal close 通过 `append_terminal_and_close` 在单个 `BEGIN IMMEDIATE` 事务内完成 owner verify、terminal RunEvent append、attempt close 和 `terminal_event_position` 写入。
- recovery scan 在 P8 cleanup 后只做 diagnostic close：候选 attempt 进入 `MARK_LOST` / `NOOP_TERMINAL`，不再创建无人持有 owner secret 的 recovery attempt。
- durable path 不允许 `PlainRunEventAppender` fallback；ToolRuntime facts 和 framework `fetch_more` 均必须在 owner scope 内写入。
- legacy public/default harness/fetch_more bypass 已删除；`build_durable_harness()` 是 production-like durable 装配入口。
- production `InMemoryConversationMemoryStore` 已删除；durable harness 默认装配 `DurableConversationMemoryStore`，并支持 checkpoint caught-up 后 missing snapshot repair。
- multiprocessing stress 覆盖 file SQLite append、terminal close、stale recovery、observer startup reconcile 既有语义；慢硬盘 / Docker Linux stress 仍由 issue #38 跟踪。

P8 cleanup 后的 stale / orphan recovery 旧术语（`MARK_RECOVERING_AND_CREATE_ATTEMPT`、新 recovery attempt、`recovered_from_attempt_id` 自动写入等）均已废弃。若历史 phase plan / review artifact 仍保留这些词，只作为审计上下文；当前实现真源以代码、`dayu/host/README.md`、`docs/host/design.md` 和 PR #40 review artifacts 为准。

## 6. Residual Risk Registry

| Risk | Owner / Destination | Status |
| --- | --- | --- |
| P8 PR review 1808 F1/F2：compact / worker 异常路径 `AttemptFencingError` 可能导致 stream 无 terminal / hang | PR #40 current fix loop | accepted，待 fix / re-review |
| P8 PR review 1808 F3：owner token hash 比较未使用 `hmac.compare_digest` | PR #40 current fix loop | accepted，待 fix / re-review |
| P8 PR review 1808 F5：活跃 `RunEventData` 嵌套类型未从 `dayu.host` 包根导出 | PR #40 current fix loop | accepted，待 fix / re-review |
| durable memory repair 按 session 扫描 EventLog 的容量风险 | P9 / capacity | deferred-with-owner |
| `recover_stale_attempts(run_id=None)` 全局扫描路径未单测 | P9 / test hardening | deferred-with-owner |
| `next_attempt_index` 未独立单测 | P9 / test hardening | deferred-with-owner |
| recovery scan 自动接入生产启动链路 | P9 / Session lifecycle | deferred-with-owner |
| `startup_reconcile` 自动接入 Host 启动流程 | P9 / Session lifecycle | deferred-with-owner |
| `HostStorage.close()` 对后台 task / `to_thread` commit 无生命周期保护 | P9 lifecycle | deferred-with-owner |
| compact 成功但后续 durable append 失败时的诊断事件精度 | P15 governance hardening | deferred-with-owner |
| observer 在空 EventLog 且 `last_success_position is None` 时无法明确转 `CAUGHT_UP` | P15 governance hardening | deferred-with-owner |
| observer buffered drain / best-effort observer 解耦 / observer claim lease | GitHub issue #28 / P15 | deferred-with-owner |
| 慢硬盘 + Docker Linux multiprocessing stress 稳定性 | GitHub issue #38 | tracked |
| Tool Trace JSONL 文件滚动边界 | GitHub issue #36 | tracked |
| compact retry 合成 `RunInputContextSnapshotBuiltData` 的 `iteration_index` / `attempt_index` 语义对齐 | P7 follow-up / P9 | deferred-with-owner |
| SSE 中途失败导致 partial tool call 缺少完整 trace 语义 | P9 / P15 | deferred-with-owner |
| `RUN_INPUT_CONTEXT_SNAPSHOT_BUILT` 内联 raw payload 造成 EventLog 热冷混合与体积增长 | P9 / capacity | deferred-with-owner |
| `LocalRunHarness` 职责继续膨胀，接近 God Object 阈值 | P9 / P16 architecture | deferred-with-owner |
| schema bootstrap 半失败治理 / 严格事务化 DDL | P15 | deferred-with-owner |
| observer claim / lease / hard-gate | P15 | deferred-with-owner |
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
