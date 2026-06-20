# Host Issues Implementation Control

## 文档职责

本文档是 Host follow-up 中已由 GitHub Issue、umbrella issue、依赖链或过期裁决承接的 work units 实施总控文档。

本文档只承担实施编排职责：记录 issue-backed work unit 的范围、当前状态、issue owner / destination、进入条件、交付物、验证要求、review 结果、residual risk 和下一步入口。

已完成、已关闭、已并入、已通过最终 closeout、经用户裁决算作完成，或依附于已完成 work unit 的 obsolete 历史条目归档在 `docs/host/issues-implementation-control-archive.md`；本文档只保留仍可能影响下一步实施、裁决或留痕的 active/backlog 条目。

本文档不替代 Host 设计真源，不承载新的架构决策，不作为实现细节说明书。若某个 work unit 的讨论发现需要修改架构边界、状态机、公共接口、durable schema、EventLog 语义或跨层契约，必须先更新设计真源，再更新本文档和对应 GitHub Issue。

## 设计目标

Host issue-backed follow-up 实施必须始终服务于以下目标：

- 生产级通用 Agent，具备买方财报分析能力。
- 范式是“宿主强约束下的 LLM in the loop”。
- Host 对 Agent / Runner 的生命周期、取消、恢复、等待、上下文治理、审计与 durable truth 保持强约束。
- 严格遵守 `UI -> Service -> Host -> Engine` 分层边界，禁止反向依赖和跨层泄漏实现细节。
- 已有 GitHub Issue 的 work unit 必须尊重 issue owner / destination；不得在本文档中绕过 issue scope 抢先实施。
- 依赖型 work unit 必须等待前置 issue 完成后再进入 implementation gate；不得用测试私有入口或临时桥接伪造 production-grade 验收。
- 过期失效 work unit 只保留留痕，不作为实施入口。

任何 plan、implementation slice、review finding 裁决和 scope 调整，都必须显式对齐这些目标。若某项选择削弱这些目标，应停下来修正设计真源、本文档或对应 GitHub Issue 后再继续。

## 真源层级

Host issue-backed follow-up 实施遵循以下真源层级：

```text
dayu/README.md
  -> 项目级术语真源
  -> 约束跨层、跨 phase 的稳定术语含义

docs/host/design.md
  -> Host 架构真源
  -> 定义架构边界、状态机、公共接口、EventLog、恢复、并发、等待、上下文治理和关键治理路径

docs/engine/design.md
  -> Engine 架构真源
  -> issue 涉及 Engine provider、Runner、Agent 或 tool-calling contract 时必须同步核对

docs/host/issues-implementation-control.md
  -> issue-backed follow-up 实施编排文档
  -> 记录已由 GitHub Issue / umbrella / dependency / obsolete 裁决承接的 work units、当前状态、进入 / 退出条件、交付物、验证要求、review 结论和 residual risk

GitHub Issues
  -> 对应 work unit 的外部执行 owner / destination
  -> 记录 issue scope、讨论、PR 关联和跨文档追踪状态
```

本文档不得引入新的架构边界、状态机、公共接口或事件语义。若实施编排过程中发现需要新的架构决策，应先和用户讨论并同步到设计真源，再更新本文档对应 work unit 的范围、非目标、验收信号和对应 GitHub Issue。

术语必须遵循项目级术语真源和 Host 设计真源。planning、implementation、review、fix 与 re-review 不得自行重解释 `Session`、`Run`、`Attempt`、`EventLog`、`HostEvent`、`EngineEvent`、`WAITING`、`RECOVERING`、`CONTEXT_COMPACTED`、`CONTEXT_COMPACTION_FAILED`、`ToolRuntime`、`Conversation Memory` 等术语。若发现术语缺失或冲突，应先讨论并同步真源文档，再继续推进。

## 管理范围

本文档只管理以下类型的 work units：

- 已有独立 GitHub Issue owner / destination 的 work unit。
- 已有独立 GitHub Issue 且影响 Host / Engine 边界、provider/tool-calling contract、public product path 或后续 Host follow-up 的 cross-layer work unit。
- 已并入 umbrella issue 或 child issue 的 work unit。
- 必须等待其它 issue 完成后才能实施的依赖型 work unit。
- 已裁决过期失效，但仍需要在总控中保留留痕，避免后续误实施的 work unit。
- 经用户明确裁决要求纳入本文档留痕的 immediate residual work unit；这类条目必须在 Owner / Destination 中标明无 GitHub Issue，并记录用户裁决依据、进入条件和非目标。

除用户明确裁决的 immediate residual 记录项外，本文档不管理未建立 GitHub Issue 且可独立推进的 work unit。若某个 work unit 后续获得新的 GitHub Issue owner / destination，必须先在本文档中新增或更新对应条目，再按本文档状态进入 discussion / plan / implementation gate。

## 工作流

Host issue-backed work unit 采用以下工作流：

```text
read issues-implementation-control.md
  -> select one work unit
  -> inspect current GitHub Issue / dependency / obsolete status
  -> inspect current code and tests
  -> discuss scope, non-goals, risk, and design sufficiency with the user
  -> update docs/host/design.md first if architecture or public contract changes are needed
  -> update this control doc and the GitHub Issue if scope, status, owner, residual risk, or entry point changes
  -> generate code-generation-ready plan for the selected work unit when dependencies are satisfied
  -> review plan
  -> user confirmation
  -> implement through the current gate workflow
  -> verify tests, pyright, and relevant README/doc sync
  -> run review / re-review
  -> update current status, artifacts, commits, residual risk, GitHub Issue state, and next entry point
```

每次只推进一个 work unit。进入 plan gate 前，必须先完成 issue / dependency / code 核对和 scope discussion，确认该 work unit 仍应在当前 owner 下推进。

work unit plan 必须基于：

- Host 设计真源；
- 本文档中对应 work unit 的状态、issue owner / destination、目标、非目标、验收信号；
- 对应 GitHub Issue 的当前 scope；
- 代码核对得到的直接证据。

plan 不得从旧设计稿、旧代码路径、非真源讨论记录或 reviewer 个人偏好推导架构边界。
plan 必须避免过度设计；只能解决由 issue / dependency / 代码核对 / 设计真源直接支撑的当前 work unit 风险，不得把局部缺口扩大成通用框架、平台化能力或未来阶段能力。

plan 文档应放在 `docs/host/` 下；plan review、plan fix、plan re-review、implementation review、fix、re-review 和总控裁决 artifact 放在 `docs/reviews/` 下。

每个 work unit discussion 至少需要确认：

- work unit 目标与 success signal；
- 是否服务于本文档的设计目标；
- Host 设计真源是否足够具体；
- 对应 GitHub Issue 是否仍是正确 owner / destination；
- scope boundary、non-goals 与 stop conditions；
- 是否需要修改设计真源或 GitHub Issue；
- 是否存在会阻塞 code-generation-ready plan 的架构、状态机、公共接口、schema、持久化、依赖 issue 或测试问题。

## 仓库发布约定

Host issue-backed follow-up 实施相关分支的 GitHub remote 名称为 `github`。提交后推送当前分支时使用：

```bash
git push -u github <branch>
```

不得假设 remote 名称为 `origin`。

进入 draft PR gate 前，本文档必须更新当前 work unit 状态、plan artifact、review artifact、accepted commit、remaining risks / owners、GitHub Issue destination 和 next entry point。进入 draft PR gate 后，按既定 gate workflow 自动推进到 `draft-PR-pass`；merge、approve、mark ready for review、request reviewers、delete branch、对外 comment 或创建 / 修改外部 issue 仍需额外授权。

## Slice 切分原则

每个 work unit 内的 implementation slices 在 discussion / plan 阶段再具体确定；总控阶段不预先替 work units 固定 slice。

slice 切分必须同时满足三个约束：

- 模型上下文窗口与 review 可承载复杂度：implementation agent 必须能在一个上下文中理解目标、边界、相关代码和验证要求；review agent 必须能在一个上下文中有效审查。
- 代码依赖边界：slice 应沿稳定模块 ownership、公共契约、状态机边界、存储边界、projection 边界、issue dependency 边界或测试矩阵边界切分，避免一个 slice 同时跨越过多治理 owner。
- 可独立验证的行为闭环：slice 应大到能形成可测试的语义闭环，小到能一次实现、一次验证、一次 review。除非明确是 contract-only slice，否则不得留下只有类型、没有路径，或只有存储、没人调用的孤立半成品。

slice 不是按代码行数切，也不是只要不超过上下文窗口就算合理。好的 slice 应当有明确输入、输出、non-goals、allowed files / modules、验证命令、issue handoff 和后续 slice 可依赖的稳定交付物。

如果一个 work unit 的自然闭环超过单个 implementation agent 的上下文容量，应优先按依赖边界拆成多个 slices，并在 plan 中说明前后 slice 的 contract handoff。如果某个 slice 需要跨模块修改，plan 必须解释为什么这是同一个可验证闭环，而不是拆分失败。

## 当前状态

| 项目 | 当前值 |
|---|---|
| phase | Host issue-backed follow-up implementation backlog |
| gate | implementation |
| implementation status | WU-CLI-DEBUG-STREAM-01 Slice 2 accepted in commit `67ca96fb`. Next slice is Slice 3 prompt / interactive compatibility guard: ensure `--debug-stream` remains a global logging flag, does not become an unsupported Agent execution option, and does not pollute stdout. |
| active work unit | WU-CLI-DEBUG-STREAM-01 |
| default next work unit | WU-CLI-DEBUG-STREAM-01 |
| next entry point | AgentCodex implements WU-CLI-DEBUG-STREAM-01 Slice 3 prompt / interactive compatibility guard using the accepted plan. No push, PR, merge, mark-ready, reviewer request, branch deletion, issue closure, or out-of-scope work is authorized until later gates pass. |
| design source | `docs/host/design.md` and `docs/engine/design.md` for Host / Engine stream terminology, CLI diagnostics, logging, and UI / Service / Host / Engine ownership boundaries. |
| issue status comments | #81 closed https://github.com/noho/dayu-agent-r/issues/81; #117 closed https://github.com/noho/dayu-agent-r/issues/117; #82 https://github.com/noho/dayu-agent-r/issues/82#issuecomment-4637480828; #97 https://github.com/noho/dayu-agent-r/issues/97#issuecomment-4637480886; #98 https://github.com/noho/dayu-agent-r/issues/98#issuecomment-4637480924; #121 open https://github.com/noho/dayu-agent-r/issues/121; #122 open https://github.com/noho/dayu-agent-r/issues/122; #130 open https://github.com/noho/dayu-agent-r/issues/130; #86 updated https://github.com/noho/dayu-agent-r/issues/86#issuecomment-4679701213; #148 open https://github.com/noho/dayu-agent-r/issues/148; #156 open as #78 child https://github.com/noho/dayu-agent-r/issues/156; PR 128 merged 2026-06-09 https://github.com/noho/dayu-agent-r/pull/128; PR 131 merged 2026-06-09 https://github.com/noho/dayu-agent-r/pull/131; PR 132 merged 2026-06-10 https://github.com/noho/dayu-agent-r/pull/132; WU-PROJ-01 PR #136 merged 2026-06-11 https://github.com/noho/dayu-agent-r/pull/136; WU-OBS-SIGNALS-01 completed by control-doc裁决; draft PR #137 https://github.com/noho/dayu-agent-r/pull/137; WU-RET-00 draft PR #139 https://github.com/noho/dayu-agent-r/pull/139; WU-CM-05/06/08/09 draft PR #140 https://github.com/noho/dayu-agent-r/pull/140 final closeout recorded; WU-CLI-SESSION-01 draft PR #146 https://github.com/noho/dayu-agent-r/pull/146 final closeout recorded; WU-CLI-ACTIVITY-01 draft PR #149 https://github.com/noho/dayu-agent-r/pull/149 final closeout recorded; GitHub Issue #145 closed 2026-06-17 https://github.com/noho/dayu-agent-r/issues/145; WU-CM-12 PR #150 merged 2026-06-19 https://github.com/noho/dayu-agent-r/pull/150; WU-CM-13 / WU-CM-14 draft PR #152 open draft https://github.com/noho/dayu-agent-r/pull/152; WU-CM-15 draft PR #157 open draft https://github.com/noho/dayu-agent-r/pull/157; WU-CLI-DEBUG-STREAM-01 is backed by GitHub Issue #148; WU-CM-13 / WU-CM-14 / WU-CM-15 are user-directed work units without GitHub Issue; WU-OBS-P01 #29 open; WU-OBS-P02 #30 open; WU-OBS-P03 #31 open; WU-OBS-P04 #35 open |
| blocking open questions | None for WU-CLI-DEBUG-STREAM-01 Slice 3 implementation. Plan gate explicitly excludes `memory_repair.catch_up.budget_exhausted` from implementation scope because current code has already removed that stop reason and preserves warning only for actual memory repair failures. |

状态约定：

- `not-started`：尚未进入 plan / implementation。
- `discussion-ready`：已具备讨论和代码 / issue 核对入口，但还未形成 code-generation-ready plan。
- `blocked-by-issue`：需要等待指定 GitHub Issue / umbrella / dependency 完成。
- `obsolete`：已裁决过期失效，不作为实施入口。
- `planning`：正在形成或 review code-generation-ready plan。
- `accepted-plan`：plan / review / re-review 已通过，等待 accepted plan commit 或进入 implementation。
- `implementation`：正在实施或修复。
- `review`：正在进行 code review、re-review 或 aggregate deepreview。
- `accepted-slice`：implementation slice 已通过 code review / re-review，等待 accepted slice commit 或 aggregate deepreview。
- `ready-to-open-draft-PR`：本轮 work unit 已完成本地 gate，等待进入 draft PR gate。
- `draft-PR-pass`：draft PR gate 已通过。

## 推进规则

- 每次只推进一个 work unit。
- 先做 GitHub Issue / dependency / 代码核对，再进入方案和实现。
- Work units 必须按依赖顺序推进：底层 Engine / provider contract 优先于依赖该 contract 的 Host / Service / UI follow-up；umbrella issue 优先于其 child issue；dependent smoke 必须等待前置 production capability 完成。
- 已明确 `blocked-by-issue` 或 `obsolete` 的 work unit 不得绕过状态进入 implementation gate。
- 涉及 public contract、durable schema、状态机、跨层依赖或用户可见行为时，必须先形成明确 design decision。
- 测试优先按风险边界补齐；压力测试和长耗时测试必须与常规测试入口分开。
- 实施完成后必须更新对应测试、类型检查、稳定文档说明和对应 GitHub Issue 状态。
- 每个 work unit 进入 plan、implementation、review、ready-to-open-draft-PR 或 draft-PR-pass 时，必须更新“当前状态”中的 gate、active work unit、next entry point 和 blocking open questions；artifact、commit、review 与历史验证记录写入对应 work unit、review artifact 或 closeout artifact，不在“当前状态”表中累积流水账。

## Residual Risk / 遗留问题追踪

本章节专门追踪实施过程中发现但未在当前 work unit 内关闭的 residual risk、遗留问题、测试缺口、设计疑问、issue dependency 和后续 owner。不得把这类事项只停留在对话、review artifact、implementation report 或 GitHub Issue comment 中。

追踪规则：

- 每条 tracking item 必须有稳定 id、来源 work unit、状态、owner / destination 和下一步动作。
- `ready-to-open-draft-PR` 前，所有 tracking items 必须处于 `closed`、`deferred-with-owner` 或 `transferred-to-issue`，不得保留无 owner 的 open item。
- 如果 residual risk 需要修改 Host 架构、公共契约、状态机、durable schema 或 EventLog 语义，必须先同步设计真源，再更新本表和对应 GitHub Issue。
- 如果 residual risk 已由代码核对证明不存在，应标记 `closed` 并记录关闭依据，不继续保留为模糊风险。

状态值：

- `open`：仍需当前 work unit 或本轮 phase 处理。
- `deferred-with-owner`：明确后续 owner / work unit / issue，当前 work unit 不处理。
- `transferred-to-issue`：已迁移到独立 GitHub Issue 或等价外部追踪项。
- `closed`：已通过实现、测试、设计裁决或代码核对关闭。

Residual Risk Reconciliation 后，本表只保留仍存在的 residual risk；已关闭项从 active 表删除，关闭依据保存在对应 review / reconciliation artifact 中。

| ID | 状态 | Owner / Destination | 下一步 |
|---|---|---|---|
| WU-ENG-02-S3-R1 | transferred-to-issue | WU-OBS-00B / GitHub Issue #119 under #70 analyzer | analyzer 实施时确认 usage observation projection signal 是否需要扩展 correlation fields。 |
| WU-TOOLS-01-S1-R1 | transferred-to-issue | GitHub Issues #121 and #122 | SEC/Fins CI pipeline / smoke 与 CN/HK Docling CI pipeline / smoke 改由对应 issue 直接追踪；不再作为本文档默认 next work unit。 |
| WU-TOOLS-01-F01-02-R1 | transferred-to-issue | GitHub Issue #129 | 设计 awaiting 两阶段启动后，才能扩展 Host wait adapter 或 Fins runtime activation contract。 |
| WU-TOOLS-01-F01-02-R2 | deferred-with-owner | WU-WAIT-03 / GitHub Issue #92；provider-specific adapter owners | 由 WU-WAIT-03 统一裁决 external job physical cancel / revoke / abandon；具体 provider/runtime 只在支持时实现物理中断，当前 WU 使用 cooperative checkpoint 与 bounded wait。 |
| WU-TOOLS-01-F03-R4 | transferred-to-issue | GitHub Issue #133 | 评估并调整 Tools Discovery spec 语义：移除 `allow_empty` / `include_read_tools`、`workspace_root` 默认值、Fins read / Doc OLD limits、upload allowlist 归属。 |

## 当前 Work Units

| Work Unit | 状态 | 主题 | Owner / Destination | 当前定位 |
|---|---|---|---|---|
| WU-CLI-FINS-OBS-01 | completed | Fins direct CLI live event stream / log / UI print residual | 用户裁决；无 GitHub Issue | Replacement implementation final closeout completed locally; residuals R3/R5 closed by WU-CLI-FINS-DIAG-01; CLI session management follow-up transferred to #145 |
| WU-CLI-FINS-DIAG-01 | completed | CLI/Fins diagnostic output policy residual closeout | 用户裁决；无 GitHub Issue | Closed WU-CLI-FINS-OBS-01-R3/R5 locally: runtime/CLI diagnostics use stderr, stdout remains UI/result, Fins output no longer redacts paths as secrets, and Fins direct diagnostics include bounded useful summaries. |
| WU-CLI-SESSION-01 | completed | CLI session management: resume / list / purge and remove `--new-session` | GitHub Issue #145 | Final closeout completed in `docs/reviews/wu-cli-session-01-final-closeout-20260616.md`; draft PR #146 open; Host formally added public `list_sessions`; issue #145 closed on 2026-06-17 after user authorization |
| WU-CLI-ACTIVITY-01 | draft-PR-pass | Prompt / interactive user-visible activity stream UI | GitHub Issue #144 | Final closeout completed in `docs/reviews/wu-cli-activity-01-final-closeout-20260618.md`; draft PR #149 open; PR review and focused PR re-review PASS; residual `WU-CLI-ACTIVITY-01-PR-R1` closed by WU-CM-12 S5 public continuity smoke reconciliation. |
| WU-CLI-INTERACTIVE-RESUME-01 | ready-to-open-draft-PR | prompt / interactive existing-session startup resume semantics | 用户裁决；无 GitHub Issue | Final closeout completed locally: prompt does no startup backfill or unfinished-run wait/replay but records displayed terminal cursor; interactive existing-session entrypoints run watcher-first attach/reconnect before REPL, session-scoped Outbox backfill, idle-tail closure, active / queued barrier, and async CLI cursor store. Implementation review PASS from AgentMiMo / AgentDS; validation: `tests/service -q` 110 passed, affected CLI subset 74 passed, `pyright dayu/ tests/ utils/` 0 errors. |
| WU-OBS-00 | pending | Tool Trace analyzer | GitHub Issue #70 | 前置 signal bundle 已完成；trace 文件 / 目录输入的 Host / Engine / Tool 分层诊断；WU-OBS-01 的诊断底座 |
| WU-OBS-00A | pending-parent | Tool Trace analyzer integrity and large payload diagnostics | GitHub Issue #34 / #70 child | #70 analyzer 子项；不单独实现一套 analyzer |
| WU-OBS-00B | pending-parent | Usage observation projection correlation boundary | GitHub Issue #119 / #70 child | #70 analyzer 子项；owner for residual `WU-ENG-02-S3-R1` |
| WU-OBS-01 | pending-prerequisite | Prompt-based Tool Trace diagnostics | GitHub Issue #71；GitHub Issue #27 superseded | #71 作为主 issue，吸收 #27 的 prompt / final answer 反查诉求 |
| WU-AUDIT-01 | pending | Audit Ledger viewer and integrity report | GitHub Issue #72 | read-only audit JSONL ledger viewer；审计责任链 / 完整性校验，不做 Tool Trace root-cause analyzer |
| WU-AUDIT-02 | pending | External audit delivery contract with local validation adapters | GitHub Issue #75 | async external audit delivery 语义；无真实外部系统时先用 Noop / FileMirror adapter 验证 contract |
| WU-RET-00 | draft-PR-pass | Host storage lifecycle retention policy | GitHub Issue #43 | draft PR #139 open；retention umbrella first delivery ready for review / merge；GitHub Issue #43 remains open until PR merge |
| WU-RET-01 | pending | Tool Trace cold JSONL storage governance | GitHub Issue #36 | Tool Trace cold JSONL rotation / retention / compaction / size reporting；不作为 #70 前置 |
| WU-RET-02 | pending | Audit JSONL storage governance | GitHub Issue #96 | Audit JSONL rotation / retention / compaction / size reporting；保留 purge tombstone 可验证关联 |
| WU-STRESS-SQLITE-01 | pending | SQLite multiprocess high-spec stress | GitHub Issue #38 | 现有 SQLite 多进程压力测试链路的慢盘 / Docker Linux 高规格版本 |
| WU-LIFE-03 | pending | Active cancel watchdog | GitHub Issue #91 / #87 umbrella | Host lifecycle watchdog target |
| WU-GOV-01 | pending | Host governance terminal taxonomy | GitHub Issue #88 | 引入 `REJECTED` |
| WU-CTX-01 | pending | Provider tokenizer / sizing adapter | GitHub Issue #20 | provider/model-aware context sizing；仍有效，需先收敛 budget policy 设计表述 |
| WU-WAIT-01 | pending | Callback endpoint / auth / replay | GitHub Issue #89 | wait callback adapter |
| WU-WAIT-02 | pending | Production poller loop / backoff / fencing / retry | GitHub Issue #90 | production poller loop |
| WU-WAIT-03 | pending | External job physical cancel / revoke / abandon | GitHub Issue #92 / #87 umbrella | WAITING external job lifecycle |
| WU-WAIT-04 | pending-prerequisite | UI / Service production-grade awaiting E2E smoke | depends on #89 / #90 / #92 | dependent smoke，不独立实施 |
| WU-CM-05 | completed | LLM compaction proposal typed parsing | GitHub Issue #93 / #81 child | #81 已关闭；final closeout completed in `docs/reviews/final-closeout-20260614-cm-05-06-08-09.md`；accepted deepreview commit `492e5620` |
| WU-CM-06 | completed | Terminal summary text policy convergence | GitHub Issue #94 / #81 child | #81 已关闭；final closeout completed in `docs/reviews/final-closeout-20260614-cm-05-06-08-09.md`；accepted deepreview commit `246cd1c3` |
| WU-CM-08 | completed | Compaction material readability and smoke maintenance | GitHub Issue #95 / #81 child | #81 已关闭；final closeout completed in `docs/reviews/final-closeout-20260614-cm-05-06-08-09.md`；accepted deepreview commit `366d8df1` |
| WU-CM-09 | completed | Durable memory snapshot corruption policy | GitHub Issue #41 | #81 已关闭；final closeout completed in `docs/reviews/final-closeout-20260614-cm-05-06-08-09.md`；accepted deepreview commit `3e98565d` |
| WU-CM-10 | deferred | Conversation Memory eval benchmark | GitHub Issue #80 / #81 follow-up | deferred behind #81；post-#81 memory semantic contract 稳定后再实施 |
| WU-CM-11 | deferred | User Profile Memory durable boundary and cross-session profile | GitHub Issue #115 / #81 child | deferred behind #81；#81 只固定 User Profile 不混入 session Conversation Memory 的边界，跨 session durable profile 独立后续实施 |
| WU-CM-12 | completed | Conversation Memory design refinement and implementation drift repair | 用户裁决；无 GitHub Issue | PR #150 merged on 2026-06-19. Final closeout completed again on 2026-06-19 after three-way deepreview and focused re-review; proactive recovery diagnostics, reactive recovery catch-up handling, cancellation manifest preservation, and memory projection edge cases are closed. |
| WU-CM-13 | draft-PR-pass | Unified conversation compact pipeline convergence | WU-CM-12-S4-R1 follow-up；无 GitHub Issue | Draft PR #152 open draft. Accepted PR review commit `f2970512` pushed; final closeout recorded in `docs/reviews/wu-cm-13-final-closeout-20260619.md`; `WU-CM-12-S4-R1` and `WU-CM-13-S1-R1` closed. |
| WU-CM-14 | completed | Recent final answer preservation for ordinal follow-ups | CM semantic follow-up；无 GitHub Issue | Local phaseflow completed. Accepted slice commit `921c6219`; aggregate deepreview PASS after deleting dead `_current_only_material_blocks`. Root cause fixed by passing existing floor into compact selection, adding ordinary post-compaction protected raw tail rendering, and repairing reactive frozen material assembly for protected floor semantics. WU-CM-13 subsequently audited the preservation path into shared compact pipeline ownership. |
| WU-CM-15 | draft-PR-pass | Conversation memory public smoke reactive compact and fallback coverage | CM smoke / eval coverage follow-up；无 GitHub Issue | Draft PR #157 open draft. Accepted plan commit `97518e93`; accepted implementation slice commit `572a88df`; pre-PR closeout commit `0fe4e910`; accepted PR review / final closeout commit `5e04a841`. PR review PASS from AgentMiMo / AgentDS with no material findings; final closeout recorded in `docs/reviews/wu-cm-15-final-closeout-20260620.md`. |
| WU-CLI-DEBUG-STREAM-01 | implementation | CLI `--debug-stream` per-delta stream diagnostics | GitHub Issue #148 | Slice 2 accepted in commit `67ca96fb`. Current entry: Slice 3 prompt / interactive compatibility guard. Remaining approved slice after Slice 3: README/test README docs. `memory_repair.catch_up.budget_exhausted` is excluded from implementation scope as an already-closed bug, with only no-regression verification retained. |

## WU-CLI-ACTIVITY-01 CLI Activity Stream UI

### 状态

本 work unit 已完成 plan review / re-review。BQ-1 已由用户裁决解除：本 WU 允许修改 event 相关 contracts。Plan 方向为 contract-first：先扩展 Host public `HostEvent` activity projection，再由 Service / CLI 消费该 public activity view；CLI 不读取 Host durable internals、Tool Trace、payload ref / digest、logging 或 ToolBundle。

### Current gate artifacts

- plan: `docs/host/host-issues/wu-cli-activity-01-activity-composer-plan.md`
- plan review: `docs/reviews/plan-review-20260617-124817.md` (AgentMiMo); `docs/reviews/plan-review-20260617-124923.md` (AgentDS)
- plan review adjudication: `docs/reviews/plan-review-wu-cli-activity-01-adjudication-20260617-125229.md`
- plan re-review: `docs/reviews/plan-review-20260617-130417.md` (AgentMiMo); `docs/reviews/plan-review-20260617-130248.md` (AgentDS)
- plan gate validation: `git diff --check` clean; untracked plan artifact whitespace check clean via `git diff --no-index --check /dev/null docs/host/host-issues/wu-cli-activity-01-activity-composer-plan.md` with expected nonzero no-index exit and no whitespace output
- accepted plan commit: `012fee0a`

### Accepted plan scope

- Slice A: Host public activity event contract; `HostEvent` keeps coarse `HostEventKind` and adds existing `HostEventClass`, EventLog row `event_type`, and safe `HostActivityView`.
- Slice B: Service activity callback consumes Host public activity, without parsing durable internals.
- Slice C: Prompt activity renderer, visibility toggle, and running-state cancel behavior.
- Slice D: Interactive composer with multiline input, history search, external editor, and early prompt_toolkit compatibility validation.
- Slice E: Interactive running activity and cancel integration.
- Slice F: README/doc checks, affected tests, coverage, pyright, and validation cleanup.

### Slice A status

- implementation artifact: `docs/reviews/wu-cli-activity-01-slice-a-implementation-codex.md`
- code review: `docs/reviews/code-review-20260617-132628.md` (AgentMiMo); `docs/reviews/code-review-20260617-132508.md` (AgentDS)
- code review adjudication: `docs/reviews/code-review-wu-cli-activity-01-slice-a-adjudication-20260617-132855.md`
- fix artifact: `docs/reviews/wu-cli-activity-01-slice-a-fix-codex.md`
- re-review: `docs/reviews/code-review-wu-cli-activity-01-slice-a-re-review-20260617-133529.md` (AgentMiMo); `docs/reviews/code-review-20260617-133606.md` (AgentDS)
- validation: `pytest tests/host/test_public_host_event.py tests/host/test_public_open_host_options.py tests/host/test_package_exports.py tests/host/test_host_activity_event_projection.py tests/host/test_watch_session_events.py tests/host/test_context_compact_events.py tests/cli/test_interactive_command.py tests/cli/test_prompt_command.py tests/service/test_entrypoint_runtime.py tests/service/test_entrypoint_runtime_interactive_path.py tests/service/test_entrypoint_runtime_prompt_path.py -q` passed with 149 passed and 3 third-party edgar deprecation warnings; `python -m pyright dayu/ tests/ utils/` passed with 0 errors; `git diff --check` clean
- accepted slice commit: `992a641d`

### Slice B status

- implementation artifact: `docs/reviews/wu-cli-activity-01-slice-b-implementation-codex.md`
- code review: `docs/reviews/code-review-20260617-135557.md` (AgentMiMo); `docs/reviews/code-review-20260617-135353.md` (AgentDS)
- code review adjudication: `docs/reviews/code-review-wu-cli-activity-01-slice-b-adjudication-20260617-135835.md`
- fix artifact: `docs/reviews/wu-cli-activity-01-slice-b-fix-codex.md`
- re-review: `docs/reviews/code-review-wu-cli-activity-01-slice-b-rereview-mimo-20260617-140637.md` (AgentMiMo); `docs/reviews/code-review-wu-cli-activity-01-slice-b-rereview-ds-20260617-140637.md` (AgentDS)
- validation: `pytest tests/service/test_entrypoint_runtime.py tests/service/test_entrypoint_runtime_prompt_path.py tests/service/test_entrypoint_runtime_interactive_path.py -q` passed with 32 passed and 3 third-party edgar deprecation warnings; `python -m pyright dayu/ tests/ utils/` passed with 0 errors; `git diff --check` clean
- accepted slice commit: `152292da`

### CLI slices C/D/E/F status

- implementation artifact: `docs/reviews/wu-cli-activity-01-cli-implementation-codex.md`
- initial fix artifact: `docs/reviews/wu-cli-activity-01-cli-fix-codex.md`
- code review: `docs/reviews/code-review-wu-cli-activity-01-cli-mimo-20260617-145226.md` (AgentMiMo); `docs/reviews/code-review-wu-cli-activity-01-cli-ds-20260617-145226.md` (AgentDS)
- review fix artifact: `docs/reviews/wu-cli-activity-01-cli-review-fix-codex.md`
- targeted re-review: `docs/reviews/code-review-wu-cli-activity-01-cli-rereview-mimo-20260617-151159.md` (AgentMiMo); `docs/reviews/code-review-wu-cli-activity-01-cli-rereview-ds-20260617-151159.md` (AgentDS)
- validation: `pytest tests/service/test_entrypoint_runtime.py tests/service/test_entrypoint_runtime_prompt_path.py tests/service/test_entrypoint_runtime_interactive_path.py tests/cli/test_prompt_command.py tests/cli/test_interactive_command.py tests/cli/test_activity_renderer.py tests/cli/test_interactive_composer.py tests/cli/test_run_keys.py -q` passed with 97 passed and 3 third-party edgar deprecation warnings; `pytest tests/cli/test_activity_renderer.py tests/cli/test_interactive_composer.py tests/cli/test_run_keys.py --cov=dayu.cli.activity --cov=dayu.cli.composer --cov=dayu.cli.run_keys --cov-fail-under=80 -q` passed with 17 passed and total coverage 89.53%; `python -m pyright dayu/ tests/ utils/` passed with 0 errors; `git diff --check` clean
- accepted slice commit: `1a6f4bb2`

### Aggregate review and final closeout

- aggregate deepreview: `docs/reviews/deepreview-wu-cli-activity-01-aggregate-mimo-20260617-153030.md` (AgentMiMo, non-blocking with CLI subagent limitation noted); `docs/reviews/deepreview-wu-cli-activity-01-aggregate-ds-20260617-151950.md` (AgentDS, non-blocking)
- final validation: `pytest tests/host/test_public_host_event.py tests/host/test_public_open_host_options.py tests/host/test_package_exports.py tests/host/test_host_activity_event_projection.py tests/host/test_watch_session_events.py tests/host/test_context_compact_events.py tests/service/test_entrypoint_runtime.py tests/service/test_entrypoint_runtime_prompt_path.py tests/service/test_entrypoint_runtime_interactive_path.py tests/cli/test_prompt_command.py tests/cli/test_interactive_command.py tests/cli/test_activity_renderer.py tests/cli/test_interactive_composer.py tests/cli/test_run_keys.py -q` passed with 179 passed and 3 third-party edgar deprecation warnings; `pytest tests/cli/test_activity_renderer.py tests/cli/test_interactive_composer.py tests/cli/test_run_keys.py --cov=dayu.cli.activity --cov=dayu.cli.composer --cov=dayu.cli.run_keys --cov-fail-under=80 -q` passed with 17 passed and total coverage 89.53%; `python -m pyright dayu/ tests/ utils/` passed with 0 errors; `git diff --check` clean
- final closeout: `docs/reviews/wu-cli-activity-01-final-closeout-20260617.md`
- post-closeout fix: `docs/reviews/wu-cli-activity-01-interactive-composer-async-fix.md`; validation `pytest tests/cli/test_interactive_composer.py tests/cli/test_interactive_command.py tests/cli/test_prompt_command.py tests/cli/test_activity_renderer.py tests/cli/test_run_keys.py -q` passed with 66 passed and 3 third-party edgar deprecation warnings; `pytest tests/cli/test_activity_renderer.py tests/cli/test_interactive_composer.py tests/cli/test_run_keys.py --cov=dayu.cli.activity --cov=dayu.cli.composer --cov=dayu.cli.run_keys --cov-fail-under=80 -q` passed with 18 passed and total coverage 90.25%; `python -m pyright dayu/ tests/ utils/` passed with 0 errors; `git diff --check` clean

### Residual risks

- `RR-ACT-01` closed by Slice A: Host admission records Host-owned `effective_tool_display_names` without durable schema migration.
- `RR-ACT-02` closed by CLI implementation and tests: prompt_toolkit composer key bindings for Ctrl+J / Ctrl+R / Ctrl+X Ctrl+E are isolated in CLI and covered by `tests/cli/test_interactive_composer.py`.
- `RR-ACT-03` closed by CLI implementation and tests: activity renderer is TTY-gated, stderr-only, line-oriented, and closed before terminal rendering; prompt / interactive tests cover stdout cleanliness.
- `RR-ACT-04` closed by CLI fix and tests: repeated Ctrl+C local exit returns local 130 without forging Host terminal facts.
- `RR-ACT-05` closed by CLI fix and tests: prompt cancel terminal race prefers terminal when cancel terminal arrives before the second Ctrl+C local exit.

### Follow-up delta EventLog / projection catch-up status

- accepted follow-up plan: `docs/host/host-issues/wu-cli-activity-01-followup-delta-eventlog-projection-catchup-plan.md`
- accepted plan commit: `906c1ffa`
- current slice: follow-up implementation completed locally through aggregate deepreview and focused re-review; next gate is draft PR.
- Slice 1 scope: clarify Host default durable policy for `content_delta` / `reasoning_delta` / `tool_call_delta`, durable replay non-goal for token-level delta, memory projection catch-up cursor / idle / failure semantics, hot path no-unbounded-sync-catch-up constraint, and `memory_projection_catchup_batch_size` as internal page size.
- Slice 1 allowed files: `docs/host/design.md`, optional `docs/engine/design.md`, `docs/host/issues-implementation-control.md`, and implementation artifact under `docs/reviews/`.
- Slice 1 implementation artifact: `docs/reviews/wu-cli-activity-01-followup-slice-1-implementation-codex-20260618.md`
- Slice 1 validation: `git diff --check` clean; grep confirmed old catch-up budget wording is absent and new non-durable delta / page-size wording is present.
- Slice 1 accepted commit: `3cb5fcb4`.
- Slice 2 scope: Host ingest accepts `content_delta` / `reasoning_delta` / `tool_call_delta` after durable identity / stale / late governance but returns accepted no-row results by default; non-delta preview mapping remains durable preview.
- Slice 2 implementation artifact: `docs/reviews/wu-cli-activity-01-followup-slice-2-implementation-codex-20260618.md`.
- Slice 2 code review: `docs/reviews/code-review-20260618-065959-mimo-wu-cli-activity-01-followup-slice-2.md`; `docs/reviews/code-review-20260618-070001-ds-wu-cli-activity-01-followup-slice-2.md`.
- Slice 2 fix artifact: `docs/reviews/wu-cli-activity-01-followup-slice-2-fix-codex-20260618.md`.
- Slice 2 re-review: `docs/reviews/code-review-20260618-070713-mimo-rereview-wu-cli-activity-01-followup-slice-2.md`; `docs/reviews/code-review-20260618-070659-ds-rereview-wu-cli-activity-01-followup-slice-2.md`.
- Slice 2 validation: `pytest tests/host/test_engine_ingest_mapping.py` passed with 64 passed; `pyright dayu/host/engine_ingest.py tests/host/test_engine_ingest_mapping.py` passed with 0 errors; `git diff --check` clean.
- Slice 2 accepted commit: `8d0a06f1`.
- Slice 3 scope: add durable-neutral EventLog filtered read with covered cursor semantics; update ProjectionRunner to use consumer filter at read path, apply only matching rows, advance checkpoint over covered non-matching ranges without consumer apply, and preserve failure stop before failed matching row.
- Slice 3 implementation artifact: `docs/reviews/wu-cli-activity-01-followup-slice-3-implementation-codex-20260618.md`.
- Slice 3 code review: `docs/reviews/mimo-wu-cli-activity-01-followup-slice-3-20260618-072504.md`; `docs/reviews/ds-wu-cli-activity-01-followup-slice-3-20260618-072339.md`.
- Slice 3 fix artifact: `docs/reviews/wu-cli-activity-01-followup-slice-3-fix-codex-20260618.md`.
- Slice 3 re-review: `docs/reviews/mimo-rereview-wu-cli-activity-01-followup-slice-3-20260618-073105.md`; `docs/reviews/ds-rereview-wu-cli-activity-01-followup-slice-3-20260618-073110.md`.
- Slice 3 validation: `pytest tests/host/test_event_log_store.py tests/host/test_projection_runner.py tests/host/test_projection_read_model.py` passed with 46 passed; `pyright dayu/host/durable/event_log.py dayu/host/projection.py tests/host/test_event_log_store.py tests/host/test_projection_runner.py tests/host/test_projection_read_model.py` passed with 0 errors; `python -m pyright dayu/ tests/ utils/` passed with 0 errors; `git diff --check` clean.
- Slice 3 accepted commit: `f67a55b6`.
- Slice 4 scope: remove `MemoryProjectionCatchupBudget` / `MemoryProjectionRepairPurpose` / `BUDGET_EXHAUSTED` memory repair semantics, make catch-up / rebuild loop to target / idle / failure using page size only, remove open_host after-commit and dispatch compact accepted conversation-memory catch-up hooks, and delete the residual `ConversationMemoryProjectionCatchupPort` adapter.
- Slice 4 implementation artifact: `docs/reviews/wu-cli-activity-01-followup-slice-4-implementation-codex-20260618.md`.
- Slice 4 code review: `docs/reviews/mimo-wu-cli-activity-01-followup-slice-4-20260618-074855.md`; `docs/reviews/ds-wu-cli-activity-01-followup-slice-4-code-review-20260618-074930.md`.
- Slice 4 fix artifact: `docs/reviews/wu-cli-activity-01-followup-slice-4-fix-codex-20260618.md`.
- Slice 4 re-review: `docs/reviews/mimo-rereview-wu-cli-activity-01-followup-slice-4-20260618-075452.md`; `docs/reviews/ds-rereview-wu-cli-activity-01-followup-slice-4-20260618-075450.md`.
- Slice 4 validation: `pytest tests/host/test_memory_repair.py tests/host/test_toolruntime_accept_barrier.py tests/host/test_resolve_wait_command.py tests/host/test_admission_queue.py tests/host/test_open_host_runtime.py tests/host/test_dispatch_scheduler.py tests/host/test_logging.py -q` passed with 160 passed; relevant pyright passed with 0 errors; `python -m pyright dayu/ tests/ utils/` passed with 0 errors; `rg` found no `ConversationMemoryProjectionCatchupPort`, `MemoryProjectionCatchupBudget`, `MemoryProjectionRepairPurpose`, `MemoryProjectionRepairStopReason.BUDGET_EXHAUSTED`, or memory repair `budget_exhausted` in `dayu/` and `tests/`; `git diff --check` clean.
- Slice 4 accepted commit: `794d3b74`.
- Slice 5 scope: make Conversation Memory projection filter a single truth via `conversation_memory_projection_event_filter()`, reuse projection-to-EventLog read filter conversion in inline repair, remove RunInputBuilder-local memory event type filter, and use session-scoped `read_events_after_matching(...)` / covered cursor semantics for inline delta repair.
- Slice 5 implementation artifact: `docs/reviews/wu-cli-activity-01-followup-slice-5-implementation-codex-20260618.md`.
- Slice 5 code review: `docs/reviews/mimo-wu-cli-activity-01-followup-slice-5-review-20260618-081119.md`; `docs/reviews/ds-wu-cli-activity-01-followup-slice-5-20260618-080958.md`.
- Slice 5 validation: `pytest tests/host/test_run_input_builder.py tests/host/test_memory_projection.py` passed with 76 passed; relevant pyright passed with 0 errors; `python -m pyright dayu/ tests/ utils/` passed with 0 errors; `git diff --check` clean.
- Slice 5 accepted commit: `49c813a5`.
- Aggregate deepreview: `docs/reviews/mimo-aggregate-wu-cli-activity-01-followup-20260618-081816.md`; `docs/reviews/ds-aggregate-wu-cli-activity-01-followup-20260618-081532.md`.
- Aggregate fix: `docs/reviews/wu-cli-activity-01-followup-aggregate-fix-codex-20260618.md`.
- Aggregate focused re-review: `docs/reviews/mimo-aggregate-rereview-wu-cli-activity-01-followup-20260618.md`; `docs/reviews/ds-aggregate-rereview-wu-cli-activity-01-followup-20260618-082351.md`.
- Aggregate fix validation: `pytest tests/host/test_event_log_store.py tests/host/test_projection_runner.py tests/host/test_memory_repair.py tests/host/test_run_input_builder.py tests/host/test_memory_projection.py -q` passed with 120 passed; final follow-up validation `pytest tests/host/test_engine_ingest_mapping.py tests/host/test_event_log_store.py tests/host/test_projection_runner.py tests/host/test_projection_read_model.py tests/host/test_memory_repair.py tests/host/test_open_host_runtime.py tests/host/test_dispatch_scheduler.py tests/host/test_logging.py tests/host/test_toolruntime_accept_barrier.py tests/host/test_resolve_wait_command.py tests/host/test_admission_queue.py tests/host/test_run_input_builder.py tests/host/test_memory_projection.py -q` passed with 348 passed; `python -m pyright dayu/ tests/ utils/` passed with 0 errors; `git diff --check` clean.
- Draft PR: https://github.com/noho/dayu-agent-r/pull/149.
- PR review: `docs/reviews/wu-cli-activity-01-pr-review-mimo-20260618.md`; `docs/reviews/wu-cli-activity-01-pr-review-ds-20260618.md`.
- PR review fix: `docs/reviews/wu-cli-activity-01-pr-review-fix-codex-20260618.md`.
- PR review fix validation: `pytest tests/cli/test_prompt_command.py tests/cli/test_interactive_command.py tests/cli/test_activity_renderer.py tests/cli/test_interactive_composer.py tests/cli/test_run_keys.py tests/service/test_entrypoint_runtime.py tests/service/test_entrypoint_runtime_prompt_path.py tests/service/test_entrypoint_runtime_interactive_path.py -q` passed with 114 passed and 3 third-party edgar deprecation warnings; `python -m pyright dayu/ tests/ utils/` passed with 0 errors; grep found no duplicated `_cancel_and_await_task` in `dayu/cli`.
- PR focused re-review: `docs/reviews/wu-cli-activity-01-pr-rereview-mimo-20260618.md`; `docs/reviews/wu-cli-activity-01-pr-rereview-ds-20260618.md`.
- Final closeout: `docs/reviews/wu-cli-activity-01-final-closeout-20260618.md`.
- PR checks: GitHub reports no checks for branch `wu-cli-activity-01`; closeout relies on local validation and dual-agent review.
- next entry point: WU-OBS-00 preflight / planning when requested.

## WU-CLI-INTERACTIVE-RESUME-01 Prompt / Interactive Existing-Session Startup

### 状态

本 work unit 已完成本地 final closeout。语义裁决为：`prompt` 不执行离线 terminal backfill，也不等待 / 重放历史未完成 Run；`interactive` existing-session 入口在进入 REPL 前执行 attach / reconnect startup barrier，处理 selected Session 的离线 terminal、active Run 与 queued-only 状态。

### Gate artifacts

- initial plan: `docs/reviews/wu-cli-interactive-resume-01-plan-codex-20260617.md`
- plan reviews: `docs/reviews/plan-review-20260617-183641.md`; `docs/reviews/plan-review-20260617-183910.md`
- plan adjudication: `docs/reviews/wu-cli-interactive-resume-01-plan-adjudication-20260617.md`
- revised plan: `docs/reviews/wu-cli-interactive-resume-01-plan-fix-codex-20260617.md`
- idle-tail fix artifact: `docs/reviews/wu-cli-interactive-resume-01-idle-tail-fix-codex-20260617.md`
- implementation reviews: `docs/reviews/wu-cli-interactive-resume-01-implementation-review-mimo-20260617.md`; `docs/reviews/wu-cli-interactive-resume-01-implementation-review-20260617.md`

### Implementation summary

- Service 新增 `startup_reconnect_entrypoint_session(...)`，使用 watcher-first 顺序：先 attach `watch_session_events(session_id)` 并启动 drain task，再执行 session-scoped Outbox backfill。
- Startup backfill 不按 `run_id` 过滤；`CAUGHT_UP` 且无新 terminal 是正常 idle，不复用 run-scoped terminal fallback 的异常语义。
- idle snapshot 后增加 tail closure：再次 session-scoped Outbox backfill 并 drain watcher queue，发现 terminal 或首次 watcher failure 时重新读取 Session snapshot，避免 terminal 已提交但尚未进入 watcher queue 的窗口。
- interactive existing-session 入口在首条输入前执行 startup barrier；active Run 先观察 terminal，queued-only 按 bounded promotion wait，耗尽后结构化失败，不静默进入 REPL。
- prompt existing-session 入口不读 cursor、不补读旧 terminal、不等待旧 active / queued；仅在本次 terminal 成功渲染后推进 CLI terminal cursor。
- CLI terminal cursor 是 workspace-local UI state，通过 `asyncio.to_thread()` 包裹同步 JSON / file lock / atomic replace；腐坏 JSON 与非法字段 fail fast。

### Validation

- `source .venv/bin/activate && pytest tests/service -q` passed: 110 passed, 3 third-party edgar deprecation warnings.
- `source .venv/bin/activate && pytest tests/cli/test_session_terminal_cursor.py tests/cli/test_interactive_command.py tests/cli/test_prompt_command.py tests/cli/test_session_command.py -q` passed: 74 passed, 3 third-party edgar deprecation warnings. This CLI subset is slow; final run completed in 360.44s.
- `source .venv/bin/activate && python -m pyright dayu/ tests/ utils/` passed: 0 errors, 0 warnings.

### Residual risks

- `WU-CLI-INTERACTIVE-RESUME-01-R1` rejected by user裁决: workspace-local cursor is sufficient because CLI already has `--base` to select a workspace directory; no future per-client cursor identity WU is needed for this concern.
- `WU-CLI-INTERACTIVE-RESUME-01-R2` fixed immediately: `session resume --mode interactive` now catches startup `EntrypointRuntimeError` after target resolution and renders a structured CLI error containing selector, Session id, and startup message.
- Rendering success followed by cursor write crash can duplicate terminal on next startup; accepted by design because no terminal loss is preferred over false acknowledgement.

## WU-CLI-SESSION-01 CLI Session Management

### 状态

本 work unit 已完成 final closeout。PR #146 已创建并推送到 `github/wu-cli-session-01`；GitHub Issue #145 已在 2026-06-17 按用户授权关闭。

### Current gate artifacts

- plan: `docs/host/host-issues/wu-cli-session-01-cli-session-management-plan.md`
- plan accepted commit: `653c9966`
- slice accepted commits: S1 `8175b8cb`; S2 `f66d76e9`; S3 `cc76ff31`; S4 `07cc3010`; S5 `00b82bbb`; S6 `fc92286b`
- aggregate deepreview: `docs/reviews/deepreview-wu-cli-session-01-aggregate-ds-20260616.md`; `docs/reviews/deepreview-wu-cli-session-01-aggregate-mimo-20260616.md`
- aggregate adjudication: `docs/reviews/deepreview-wu-cli-session-01-aggregate-adjudication-20260616.md`
- aggregate accepted commit: `1ac06623`
- draft PR record commit: `5152028b`
- PR review: `docs/reviews/pr-146-review-wu-cli-session-01-mimo-20260616-222711.md`; `docs/reviews/pr-146-review-wu-cli-session-01-ds-20260616.md`
- PR review adjudication: `docs/reviews/pr-146-review-wu-cli-session-01-adjudication-20260616.md`
- PR review accepted commit: `c7f79f03`
- final closeout: `docs/reviews/wu-cli-session-01-final-closeout-20260616.md`
- final validation: `pytest tests/host/test_public_session_api.py tests/host/test_package_exports.py tests/cli/test_arg_parsing.py tests/cli/test_prompt_command.py tests/cli/test_interactive_command.py tests/cli/test_session_command.py -q` 120 passed, 3 third-party edgar deprecation warnings; `python -m pyright dayu/ tests/ utils/` 0 errors; `git diff --check` clean

### Final scope decision

- `resume`、`list`、`purge` 均为本 work unit 已实施内容，不是后续项。
- Host 正式新增 public `list_sessions` API；该 API 是 Host public read contract，不是 CLI 私有临时 helper。
- `interactive --new-session` 已从 CLI surface 删除。
- `session resume` 只对已有 OPEN Session 执行，不 create / ensure Session，不使用 Host wait-resume 语义。
- `session purge` 不自动 close / cancel；Host purge precondition 是最终治理真源。

### Residual risk reconciliation

当前没有阻塞 final closeout 的 residual risk。

已分类的非阻塞风险：

- `list_sessions` 无分页 / 无 query contract：deferred-with-owner；未来真实 Session cardinality 或外部 API consumer 需要时进入 Host session-list scale / pagination hardening。
- CLI list 文本表不做列宽裁剪：deferred-with-owner；未来由 CLI UX refinement 根据 operator feedback 处理。
- `session.py` 依赖 prompt / interactive sibling module 的 existing-session 窄入口：deferred-with-owner；未来 CLI command-entrypoint refactor 或 WU-CLI-ACTIVITY-01 若改变 prompt / interactive execution ownership 时处理。
- Draft PR 无 reported CI checks：non-blocking；本地验证为本 gate controller truth，pre-merge gate / repository branch protection 继续承担外部检查。

## WU-CLI-FINS-OBS-01 Fins Direct CLI Live Event Stream / Log / UI Print

### 状态

本条是用户裁决纳入本文档留痕的 immediate residual work unit，不创建 GitHub Issue。PR #143 已打开，但 2026-06-16 用户指出并经代码核对确认两个设计更正：CLI direct live events 没有 durable job 需求，正确模型是普通 `AsyncIterator[FinsEvent]`；Fins tool awaiting 返回 `ToolAwaitingOutcome(EXTERNAL_JOB)` 的方向成立，但把 awaiting observation handle 实现成 Fins 核心 durable job system 过重。因此 PR #143 的 durable sidecar plan / slice 记录不再作为当前实施真源。2026-06-16 replacement plan gate 已完成并通过 re-review；replacement implementation 已按 `docs/host/wu-cli-fins-obs-01-replacement-plan.md` 完成 final closeout。

### 用户裁决

- 不需要创建 GitHub Issue。
- 用户已恢复 `$phaseflow` 推进；当前按本文档 accepted replacement plan 进入 implementation gate。
- `download`、`process`、`upload_filing`、`upload_material`、`process_filing`、`process_material` 全部必须恢复 live event stream。
- 除 Fins direct commands 外，还必须核对所有其它 CLI commands 的 log 与 UI print 是否正常；正常的命令记录直接证据，不正常的命令纳入本条修复或明确转入后续 owner。
- 需要同时处理两个 residual：log / UI print 缺失，以及 Fins direct event stream 迁移缺失。

### 设计与代码核对

- `docs/host/design.md` 固定 `UI -> Service -> Host -> Engine` 分层边界：UI 负责展示、输入收集、流式订阅和用户动作触发；Service 负责业务入口、身份解析、场景装配和调用 Host。Fins direct command 不应伪装成 Host run，也不得让 CLI 绕过 Service / Fins boundary。
- `docs/engine/design.md` 固定 stream 术语边界：Fins direct live event stream 不是 `EngineEvent stream`，也不是 `Host event stream`；不得在设计或实现中混称。
- `dayu/README.md` 的“日志与可观测性”固定日志职责：日志用于诊断系统执行过程，不承担 UI 输出、审计真源、tool trace、EventLog canonical fact 或 projection checkpoint 职责。
- OLD `/Users/leo/workspace/dayu-agent/dayu/services/fins_service.py` 的 `FinsService.execute(...)` 返回 `FinsResult | AsyncIterator[FinsEvent]`；流式路径直接 `async for event in result: yield event`，没有 `job_id`、event sidecar 或 durable cursor。
- OLD `/Users/leo/workspace/dayu-agent/tests/cli/test_fins_commands.py` 的 `_consume_fins_stream` 测试直接消费 `AsyncIterator[FinsEvent]`，通过 `PROGRESS` / `RESULT` 事件完成 CLI live progress 与最终结果返回。
- WU-TOOLS-01-F01 引入 Fins durable job 的直接动机是 tool awaiting：LLM tool 不应阻塞在 download / upload / preprocess 长事务里，因此工具返回 `ToolAwaitingOutcome(EXTERNAL_JOB)`，Host wait adapter 后续观察 completion。这个 awaiting 方向成立，但不要求 Fins 核心 ingestion runtime 自己成为 durable job system。
- Fins ingestion 的业务真源是 `dayu.fins.storage` 中的 source / processed / upload 产物和有界结果摘要；Fins job record 只能作为 awaiting observation handle，不能被提升为财报处理事实真源，也不应污染 CLI direct。
- NEW `dayu/cli/main.py` 已解析 `--log-level`、`--debug`、`--verbose`、`--quiet`，但当前 CLI main 未完成日志装配，导致普通 CLI 命令缺少符合 README 语义的 dayu 日志输出。
- NEW `dayu/cli/commands/fins.py` 对 Fins direct 命令启动 job 后只等待 `FinsDirectCommandService.wait_for_terminal()`，运行中没有面向用户的 progress print；Ctrl+C 后才输出 cancel 文案。
- NEW `dayu/service/fins_direct.py` 的 `wait_for_terminal()` 当前仅周期性 `read_job()` 直到终态，无法向 CLI / 未来 WeChat / GUI 提供 live progress 事件。
- NEW `dayu/cli/commands/init.py` 已在 reset、success、usage error、operation error 和 copy failure 路径输出用户可见文本；下一轮实施前应通过测试确认 init 的 UI print 仍正常，而不是把 init 误归入 Fins live stream 缺口。
- NEW `dayu/cli/commands/prompt.py` 与 `dayu/cli/commands/interactive.py` 均通过 `dayu/cli/output.py` 输出终态 final answer / failure / cancel 文本；但 `dayu/service/entrypoint_runtime.py` 当前只用 `watch_session_events()` 和 outbox read 等待 terminal，不向 CLI 投影运行中 progress 或 content delta。下一轮 plan 必须裁决这是否属于本条 UI print 缺口、应在本条修复，还是仅作为非 Fins Agent command 的后续 streaming/UI work。
- NEW `dayu/cli/commands/fins.py` 的 `upload_filings_from` 当前生成并打印 batch script，不启动 live Fins job；下一轮 plan 必须把它作为其它 CLI command 输出审计项，而不是错误地要求它恢复 live job stream。
- NEW 底层 Fins pipeline 仍保留 `DownloadEvent` / `download_stream` 等事件能力，但 direct job adapter 路径把运行中事件压成终态 summary。下一步修正应优先恢复 Service 暴露 `AsyncIterator[FinsEvent]` 的简单边界，而不是在 CLI direct 上补 durable job event sidecar。

### 2026-06-16 架构更正裁决

- CLI direct 裁决：`download` / `process` / `upload_filing` / `upload_material` / `process_filing` / `process_material` 是一次性本地命令，没有 durable job、cross-restart resume 或后台追踪需求。它们应通过 Service / Fins boundary 消费普通 `AsyncIterator[FinsEvent]`，使用 `PROGRESS` 输出运行中进度，使用 `RESULT` 收口最终结果；取消走当前执行的 async cancellation / cancel checker / KeyboardInterrupt 传播。
- Tool awaiting 裁决：`ToolAwaitingOutcome(EXTERNAL_JOB)` 仍是正确方向，因为 Engine tool handshake 不应等待长事务完成。但 awaiting 需要的是可观察、可 poll 的轻量 handle，不是 Fins 核心 runtime 的 durable job 状态机。Host wait adapter 可以用轻量 await ref 观察业务产物、执行结果或 runtime-local operation 状态；只有在明确需要跨进程 / 跨重启恢复未完成 ingestion 时，才单独设计 durable operation ledger。
- Fins runtime 裁决：Fins ingestion runtime 应优先表达业务执行、事件流和 storage 产物写入；`dayu.fins.storage` 中的财报产物和有界 result summary 才是业务真源。当前 durable job record / job store / per-job cancel / job event sidecar 组合对 CLI direct 和基础 runtime 都过重，下一轮修正必须把它收敛到 tool awaiting 所需的最小 observation handle，或在没有必要时移除。

### Replacement Plan Handoff Hints

下次以 `$phaseflow docs/host/design.md docs/host/issues-implementation-control.md` 恢复时，controller 必须把本条当作 accepted replacement plan 的 implementation，而不是 PR #143 的普通 fix。原因是现有 `docs/host/wu-cli-fins-obs-01-fins-direct-live-events-plan.md`、PR #143 slice 记录和当前实现都以 durable Fins job event sidecar 为核心前提；该前提已经被 2026-06-16 裁决否定。当前 implementation 入口是 `docs/host/wu-cli-fins-obs-01-replacement-plan.md` 的 Slice A。

Goal confirmation 必须重新核对以下直接代码事实：

- `dayu/cli/commands/fins.py`：当前 CLI direct 仍是 `start_* -> FinsDirectJobHandle -> stream_job_events_until_terminal(...)`；SIGINT 仍映射到 `service.request_cancel(handle.job_id)`。这些是要移除的 durable job coupling，不是要保留的行为。
- `dayu/service/fins_direct.py`：当前 Service protocol 仍暴露 `FinsIngestionJobStart`、`read_job(...)`、`read_job_events(...)` 和 `request_cancel(...)`；replacement plan 应把 CLI-facing boundary 改为普通 `AsyncIterator[FinsEvent]`，避免 CLI 或 Service direct path 依赖 sidecar cursor。
- `dayu/fins/ingestion_runtime.py`：当前 `start_download` / `start_preprocess` / `start_upload` 先创建 durable queued job record 再提交后台 executor，并暴露 `read_job` / `read_job_events` / `request_cancel`。replacement plan 必须裁决哪些能力属于 tool awaiting 最小 observation handle，哪些应从 core runtime 移除或降级。
- `dayu/fins/ingestion/wait_adapter.py`、`dayu/fins/tools/*_tools.py`、`dayu/service/host_assembly.py`：tool awaiting 仍必须快速返回 `ToolAwaitingOutcome(EXTERNAL_JOB)` 并让 Host wait adapter 后续观察 completion；不能把这个裁决误读成删除 awaiting。
- `tests/cli/test_fins_commands.py`、`tests/service/test_fins_direct.py`、`tests/fins/test_fins_ingestion_runtime.py`、`tests/fins/test_fins_ingestion_tools.py`、`tests/service/test_host_assembly.py`：现有测试大量证明 durable job / sidecar 行为。replacement plan 必须明确哪些测试要改写为 `AsyncIterator[FinsEvent]` 语义，哪些 awaiting tool / wait adapter 测试仍保留但改为轻量 handle 语义。

Accepted replacement plan 按依赖边界切 slice，避免一次性大爆炸：

- Slice A：定义或复用 Fins direct `FinsEvent` typed contract / Service async iterator boundary；只固定 Service-facing runtime protocol，不做真实 runtime implementation。
- Slice B：重写 CLI direct command 消费路径和输出测试，确认六个 direct 命令不再需要 `job_id`、`read_job_events`、event sidecar 或 durable cancel。
- Slice D0：先做 lightweight observation handle contract-only checkpoint；在 Slice C 删除或降级 job store 前，固定 handle、poll / cancel / abandon API、durability / recovery 裁决。
- Slice C：收敛 Fins ingestion runtime 的 core execution API，区分 direct execution stream、business result summary 和 awaiting observation handle；删除或降级不再必要的 job event sidecar 前必须确认 D0 observation source 可支撑 wait adapter。
- Slice D：调整 Fins tool awaiting / wait adapter，使 `ToolAwaitingOutcome(EXTERNAL_JOB)` 保持非阻塞，但 await ref 轻量化；若当前需求要求任何 durable row，必须先给出 cross-process / cross-restart 恢复需求和最小 schema 理由。
- Slice E：README / design / tests 同步，清除 `dayu/README.md`、`dayu/service/README.md`、`dayu/fins/README.md`、`tests/README.md` 中把 CLI direct 或 core Fins runtime 描述成 durable job system 的文字。

Stop conditions：

- 如果 plan 需要修改 Host durable schema、EventLog、Run / Attempt 状态机、Engine `ToolExecutor` contract 或 `ToolAwaitingOutcome` union，必须停止并回到设计真源讨论；当前裁决不要求这些 Host / Engine 公共契约变更。
- 如果有人主张保留 Fins durable job store，必须说明它服务的明确需求是 tool awaiting observation、cross-process observation 还是 cross-restart recovery；不能用 CLI direct 或“以后可能有用”作为理由。
- 如果 direct CLI 修正必须依赖 sidecar JSONL、per-job sequence、`request_cancel(job_id)` 或 terminal fallback synthetic event，说明 plan 仍在沿用被否定前提，必须退回重写。
- 如果 awaiting handle 轻量化会导致 Host wait adapter 无法 poll/resolve 当前 tool awaiting path，必须在 plan gate 暴露为 blocker，不能在 implementation 中临时拼接。

### 目标

- 为 Fins direct commands 恢复 live event stream，覆盖 `download`、`process`、`upload_filing`、`upload_material`、`process_filing`、`process_material`。
- 审计全部 CLI commands 的 log 与 UI print 路径，至少覆盖 `init`、`prompt`、`interactive`、`download`、`upload_filing`、`upload_material`、`upload_filings_from`、`process`、`process_filing`、`process_material`；对每个命令记录“正常 / 本条修复 / 后续 owner”的裁决依据。
- 在 Service / Fins boundary 提供可复用的普通 `AsyncIterator[FinsEvent]` 事件接口，使 CLI 只是一个 UI consumer，未来 WeChat / GUI 可以复用同一 Service 能力。
- 为 tool awaiting 保留非阻塞启动语义：工具仍可快速返回 `ToolAwaitingOutcome(EXTERNAL_JOB)`，但 awaiting handle 必须轻量，不把 Fins runtime 核心执行模型固定成 durable job store。
- 恢复 CLI 日志装配，使 `--log-level`、`--debug`、`--verbose`、`--quiet` 符合 `dayu/README.md` 的日志级别语义。
- 明确区分 log 与 UI print：运行中 progress / result summary 是 UI 输出；诊断路径、执行骨架、错误上下文是日志。
- 保留 Fins direct command 的普通 CLI cancel 语义：用户中断后应通过 async task cancellation / cancel checker / KeyboardInterrupt 传播停止当前执行，并且本地退出行为要有明确、可测试的用户可见输出。

### 非目标

- 不全量搬迁 OLD `dayu-agent` CLI 实现。
- 不把 Fins direct commands 改造成 Host run、Host wait 或 Host event stream。
- 不把 CLI direct live events 改造成 durable Fins job、job event sidecar、per-job event sequence 或 Host wait adapter。
- 不把 `ToolAwaitingOutcome(EXTERNAL_JOB)` 等同于 Fins 核心 durable job system；awaiting 可以保留，但 durable operation ledger 只有在明确 cross-restart / cross-process 恢复需求成立时才允许单独设计。
- 不让 CLI、Service 或 Host 绕过 `dayu.fins.storage` 直接散落读取财报 storage。
- 不引入无当前需求支撑的通用跨进程 event bus、WebSocket 框架或平台化观察者系统。
- 不修改 Engine stream 术语或 Engine public contract。
- 不在本条恢复 `write` workflow 或旧 Fins workflow 全量实现。
- 不把 `upload_filings_from` 改造成 live job stream；它若继续只是脚本生成命令，验收重点是正常 UI print 和日志装配。
- 不在没有 goal confirmation / plan 裁决的情况下，把 `prompt` / `interactive` 的模型 token/content streaming 扩大成本条必做项；本条必须先基于现有 Host public event 能力和用户可见需求裁决是否纳入。

### 验收信号

- 运行 `dayu-cli download --ticker CME` 后，在下载进行中能持续看到用户可见进度输出；不需要等待 Ctrl+C 或终态才看到信息。
- `download`、`process`、`upload_filing`、`upload_material`、`process_filing`、`process_material` 都通过同一类 Service / Fins boundary 暴露 `AsyncIterator[FinsEvent]` live event stream，而不是各命令在 CLI 中复制底层 storage 或 pipeline 逻辑。
- Fins tool awaiting 仍能非阻塞返回 awaiting outcome，但其 observation handle 不要求 Fins runtime 维护 durable job record / job event sidecar；若实现保留任何 durable row，plan 必须给出明确 cross-restart / cross-process 需求证据。
- 终态成功、失败、取消均有用户可见输出；输出不得依赖日志级别才能看见。
- `--verbose` / `--debug` 能显示符合 README 语义的诊断日志；默认日志不淹没 UI progress，不输出 provider secret、完整业务 payload、财报原文或大段 tool result。
- `init`、`prompt`、`interactive`、`upload_filings_from` 等非 live Fins job 命令的 UI print 经代码核对与测试分类：已正常的命令有测试或直接证据；不正常的命令已在本条修复，或被明确转入有 owner 的后续 work unit。
- `prompt` / `interactive` 的终态输出必须保持正常；若本条裁决不实现运行中 Agent progress / content streaming，plan 必须说明直接代码证据、设计依据、用户影响和后续 owner。
- Ctrl+C 触发当前 CLI 执行的普通取消路径；取消不要求 durable `job_id`，也不把本地退出伪装成后台 job 终态。
- 测试覆盖 CLI 输出审计、Service event stream、cancel、日志装配和禁止 CLI 直接 import `dayu.fins.storage` 的边界约束。

### Current gate artifacts

- replacement plan: `docs/host/wu-cli-fins-obs-01-replacement-plan.md`
- replacement plan status: accepted; implementation next
- replacement accepted plan commit: `637d36a5`
- replacement plan review: `docs/reviews/plan-review-20260616-100941.md`; `docs/reviews/plan-review-20260616-101040.md`
- replacement plan review conclusion: both `pass-with-risks`; accepted blockers were lightweight observation handle underspecification, async bridge / cancellation underspecification, Slice A/C and C/D sequencing gaps, wait adapter recovery gap, and test coverage gaps
- replacement plan fix: integrated into `docs/host/wu-cli-fins-obs-01-replacement-plan.md` by AgentCodex
- replacement plan re-review: `docs/reviews/plan-rereview-20260616-102509-mimo.md`; `docs/reviews/plan-rereview-20260616-102606-ds.md`
- replacement plan re-review conclusion: AgentMiMo `pass`; AgentDS `pass-with-risks`; all high / medium findings fixed; no new material issues; nonblocking residual risks tracked as `WU-CLI-FINS-OBS-01-R6` / `R7` / `R8`
- implementation status: final closeout completed; Slice A/B/D0/C/D/E accepted, aggregate deepreview BF-1 fixed and re-reviewed, no blocking findings remain
- Slice A implementation: `docs/reviews/wu-cli-fins-obs-01-slice-a-implementation-codex.md`
- Slice B implementation: `docs/reviews/wu-cli-fins-obs-01-slice-b-implementation-codex.md`
- Slice A/B validation: `pytest tests/service/test_fins_direct.py tests/cli/test_fins_commands.py tests/cli/test_upload_filings_from_command.py tests/cli/test_init_command.py tests/cli/test_prompt_command.py tests/cli/test_interactive_command.py tests/cli/test_arg_parsing.py -q` 129 passed, 3 warnings; targeted `pyright` 0 errors
- Slice A/B code review: `docs/reviews/code-review-20260616-111036-mimo.md`; `docs/reviews/code-review-20260616-111112-ds.md`
- Slice A/B accepted findings requiring fix: MiMo R1/R2 SIGINT cancel race test and terminal result preservation; DS-001 user-visible `Fins job summary` terminology; DS-002 `_FinsSigintMonitor` docstring terminology
- Slice A/B review fix: `docs/reviews/wu-cli-fins-obs-01-slice-ab-review-fix-codex.md`
- Slice A/B re-review: `docs/reviews/wu-cli-fins-obs-01-slice-ab-rereview-mimo-20260616.md`; `docs/reviews/wu-cli-fins-obs-01-slice-ab-rereview-ds-20260616.md`
- Slice A/B re-review conclusion: PASS from both AgentMiMo and AgentDS; no blocking findings; nonblocking observations are deferred to existing Slice C / Slice E scope or defense-in-depth cleanup; post-review logger isolation follow-up was also checked by both reviewers and remains PASS
- Slice A/B post-review validation fix: added `tests/conftest.py` logger isolation because combined CLI -> Fins runtime test order exposed leaked `dayu` logger handlers bound to closed pytest capture streams; `tests/README.md` records this test infrastructure fact
- Slice A/B final validation: `pytest tests/service/test_fins_direct.py tests/cli/test_fins_commands.py tests/cli/test_upload_filings_from_command.py tests/cli/test_init_command.py tests/cli/test_prompt_command.py tests/cli/test_interactive_command.py tests/cli/test_arg_parsing.py tests/fins/test_fins_ingestion_runtime.py -q` 184 passed, 3 warnings; `pyright dayu/ tests/ utils/` 0 errors; import check passed; `git diff --check` clean
- Slice D0 implementation: `docs/reviews/wu-cli-fins-obs-01-slice-d0-implementation-codex.md`
- Slice D0 validation: `pytest tests/fins/test_fins_ingestion_tools.py -q` 48 passed, 3 warnings; targeted `pyright` 0 errors
- Slice D0 code review: `docs/reviews/wu-cli-fins-obs-01-slice-d0-review-mimo-20260616.md`; `docs/reviews/wu-cli-fins-obs-01-slice-d0-review-ds-20260616.md`
- Slice D0 review conclusion: AgentMiMo `PASS`; AgentDS `PASS-WITH-FINDINGS`; no blocking findings
- Slice D0 accepted findings requiring fix: DS-D0-01 handle id alphabet ambiguity; fixed by narrowing observation handle ids to hex-only `[a-f0-9]`
- Slice D0 review fix: `docs/reviews/wu-cli-fins-obs-01-slice-d0-review-fix-codex.md`
- Slice D0 review follow-up: both AgentMiMo and AgentDS appended follow-up PASS sections confirming DS-D0-01 fixed, `WU-CLI-FINS-OBS-01-R7` closed, and `WU-CLI-FINS-OBS-01-R9` correctly tracks Slice D retry guard / corrupt-token E2E LOST coverage
- Slice D0 final validation: `pytest tests/fins/test_fins_ingestion_tools.py tests/fins/test_fins_ingestion_runtime.py -q` 103 passed, 3 warnings; `pyright dayu/ tests/ utils/` 0 errors; import check passed; `git diff --check` clean
- Slice C implementation: `docs/reviews/wu-cli-fins-obs-01-slice-c-implementation-codex.md`
- Slice C validation: `pytest tests/fins/test_fins_ingestion_runtime.py -q` 59 passed, 3 warnings; targeted `pyright` 0 errors; `git diff --check` clean
- Slice C code review: `docs/reviews/wu-cli-fins-obs-01-slice-c-review-mimo-20260616.md`; `docs/reviews/wu-cli-fins-obs-01-slice-c-review-ds-20260616.md`
- Slice C review conclusion: AgentMiMo `PASS`; AgentDS `PASS-WITH-FINDINGS`; no blocking findings
- Slice C accepted findings requiring fix: DS-C01 runtime direct stream should synthesize a failure RESULT if a producer exits without a RESULT; DS-C02 `_put_direct_queue` cancel branch should document intentional event discard after consumer exit
- Slice C review fix: `docs/reviews/wu-cli-fins-obs-01-slice-c-review-fix-codex.md`
- Slice C re-review: `docs/reviews/wu-cli-fins-obs-01-slice-c-rereview-mimo-20260616.md`; `docs/reviews/wu-cli-fins-obs-01-slice-c-rereview-ds-20260616.md`
- Slice C re-review conclusion: PASS from both AgentMiMo and AgentDS; direct runtime now guarantees no silent end, does not create durable job records or job event sidecar, and keeps the sync adapter bridge bounded/internal
- Slice C final validation: `pytest tests/fins/test_fins_ingestion_runtime.py -q` 60 passed, 3 warnings; `pyright dayu/fins/ingestion_runtime.py dayu/fins/service_runtime.py tests/fins/test_fins_ingestion_runtime.py` 0 errors; `git diff --check` clean
- Slice D implementation: `docs/reviews/wu-cli-fins-obs-01-slice-d-implementation-codex.md`
- Slice D validation: `pytest tests/fins/test_fins_ingestion_tools.py tests/fins/test_fins_ingestion_runtime.py tests/service/test_host_assembly.py -q` 152 passed, 3 warnings; `pyright dayu/ tests/ utils/` 0 errors; import boundary check passed; `git diff --check` clean
- Slice D code review: `docs/reviews/wu-cli-fins-obs-01-slice-d-review-mimo-20260616.md`; `docs/reviews/wu-cli-fins-obs-01-slice-d-review-ds-20260616.md`
- Slice D review conclusion: PASS from both AgentMiMo and AgentDS; no blocking findings
- Slice D accepted review fix: `_FinsObservedOperationRecord` docstring now states the `_observation_lock` invariant for mutable registry snapshots
- Slice D review fix: `docs/reviews/wu-cli-fins-obs-01-slice-d-review-fix-codex.md`
- Slice D re-review: `docs/reviews/wu-cli-fins-obs-01-slice-d-rereview-mimo-20260616.md`; `docs/reviews/wu-cli-fins-obs-01-slice-d-rereview-ds-20260616.md`
- Slice D re-review conclusion: PASS from both AgentMiMo and AgentDS; `WU-CLI-FINS-OBS-01-R8` and `WU-CLI-FINS-OBS-01-R9` closed; slow-poller bounded queue backpressure was initially tracked as `WU-CLI-FINS-OBS-01-R10`
- Slice E implementation: `docs/reviews/wu-cli-fins-obs-01-slice-e-implementation-codex.md`
- Slice E validation: `pytest tests/service/test_fins_direct.py tests/cli/test_fins_commands.py tests/fins/test_fins_ingestion_runtime.py tests/fins/test_fins_ingestion_tools.py tests/service/test_host_assembly.py tests/cli/test_upload_filings_from_command.py tests/cli/test_init_command.py tests/cli/test_prompt_command.py tests/cli/test_interactive_command.py tests/cli/test_arg_parsing.py -q` 281 passed, 3 warnings; `pyright dayu/ tests/ utils/` 0 errors; `git diff --check` clean
- Slice E code review: `docs/reviews/wu-cli-fins-obs-01-slice-e-review-mimo-20260616.md`; `docs/reviews/wu-cli-fins-obs-01-slice-e-review-ds-20260616.md`
- Slice E review conclusion: PASS from both AgentMiMo and AgentDS; no blocking findings
- Slice E accepted review fix: DS-E01 Fins README caller example now shows direct async stream first, separates observation handle flow, and labels legacy job-store helper example explicitly
- Slice E review fix: `docs/reviews/wu-cli-fins-obs-01-slice-e-review-fix-codex.md`
- Slice E re-review: `docs/reviews/wu-cli-fins-obs-01-slice-e-rereview-mimo-20260616.md`; `docs/reviews/wu-cli-fins-obs-01-slice-e-rereview-ds-20260616.md`
- Slice E re-review conclusion: PASS from both AgentMiMo and AgentDS; no blocking findings
- aggregate deepreview: `docs/reviews/wu-cli-fins-obs-01-aggregate-deepreview-mimo-20260616.md`; `docs/reviews/wu-cli-fins-obs-01-aggregate-deepreview-ds-20260616.md`
- aggregate deepreview conclusion: AgentDS PASS; AgentMiMo found BF-1 blocking import-boundary test drift for `dayu.fins.direct_events`; all other direct stream / lightweight observation / runtime boundary / README / residual-risk checks passed
- aggregate fix: `docs/reviews/wu-cli-fins-obs-01-aggregate-fix-codex-20260616.md`
- aggregate fix validation: `pytest tests/service/test_import_boundary.py -q` 1 passed; BF-1 fixed by adding the precise Service import-boundary allowlist entry `dayu.fins.direct_events` and syncing `tests/README.md`
- aggregate fix re-review: `docs/reviews/wu-cli-fins-obs-01-aggregate-fix-rereview-mimo-20260616.md`; `docs/reviews/wu-cli-fins-obs-01-aggregate-fix-rereview-ds-20260616.md`
- aggregate fix re-review conclusion: PASS from both AgentMiMo and AgentDS; BF-1 closed, `dayu.fins` prefix remains forbidden except explicit public boundary allowlist, no new findings
- final closeout: `docs/reviews/wu-cli-fins-obs-01-final-closeout-20260616.md`
- final closeout accepted local commit: `f83fd497`
- final local validation: `pytest tests/service/test_fins_direct.py tests/cli/test_fins_commands.py tests/fins/test_fins_ingestion_runtime.py tests/fins/test_fins_ingestion_tools.py tests/service/test_host_assembly.py tests/service/test_import_boundary.py tests/cli/test_upload_filings_from_command.py tests/cli/test_init_command.py tests/cli/test_prompt_command.py tests/cli/test_interactive_command.py tests/cli/test_arg_parsing.py -q` 282 passed, 3 warnings; `pyright dayu/ tests/ utils/` 0 errors; `git diff --check` clean
- residual reconciliation: closed R6/R7/R8/R9/R10 removed from active residual table; R3/R5 closed by WU-CLI-FINS-DIAG-01 and removed from active residual table
- diagnostic output plan: `docs/host/wu-cli-fins-diagnostic-output-plan.md`
- diagnostic output plan review: `docs/reviews/wu-cli-fins-diagnostic-output-plan-review-ds-20260616.md`; `docs/reviews/plan-review-20260616-150120.md`
- diagnostic output plan fix: `docs/reviews/wu-cli-fins-diagnostic-output-plan-fix-codex-20260616.md`
- diagnostic output plan fix re-review: `docs/reviews/wu-cli-fins-diagnostic-output-plan-fix-rereview-ds-20260616.md`; `docs/reviews/wu-cli-fins-diagnostic-output-plan-fix-rereview-mimo-20260616.md`
- diagnostic output implementation: `docs/reviews/wu-cli-fins-diagnostic-output-implementation-codex-20260616.md`
- diagnostic output implementation review: `docs/reviews/wu-cli-fins-diagnostic-output-implementation-review-ds-20260616.md`; `docs/reviews/wu-cli-fins-diagnostic-output-implementation-review-mimo-20260616.md`
- diagnostic output review fix: `docs/reviews/wu-cli-fins-diagnostic-output-review-fix-controller-20260616.md`
- diagnostic output review fix re-review: `docs/reviews/wu-cli-fins-diagnostic-output-review-fix-rereview-ds-20260616.md`; `docs/reviews/wu-cli-fins-diagnostic-output-review-fix-rereview-mimo-20260616.md`
- diagnostic output final validation: `pytest tests/runtime/test_log.py tests/cli/test_arg_parsing.py tests/cli/test_prompt_command.py tests/cli/test_interactive_command.py tests/cli/test_fins_commands.py -q` 121 passed, 3 warnings; `pyright dayu/ tests/ utils/` 0 errors; `git diff --check` clean
- diagnostic output final closeout: `docs/reviews/wu-cli-fins-diagnostic-output-final-closeout-20260616.md`

### Superseded PR #143 durable sidecar artifacts

- superseded plan: `docs/host/wu-cli-fins-obs-01-fins-direct-live-events-plan.md`
- superseded plan status: no longer current after 2026-06-16 replacement裁决
- superseded plan review: `docs/reviews/plan-review-20260615-154655.md`; `docs/reviews/plan-review-20260615-180157.md`
- superseded plan review adjudication: `docs/reviews/wu-cli-fins-obs-01-plan-review-adjudication-20260615-180440.md`
- superseded accepted findings requiring plan fix: DS-001 / MiMo-001, DS-002 / MiMo-002, DS-003 / MiMo-003, MiMo-004, DS-004 / MiMo-005, DS-005 / MiMo-006, DS-006 / MiMo-007, MiMo-008
- superseded plan review fix: `docs/reviews/wu-cli-fins-obs-01-plan-review-fix-codex.md`
- superseded plan re-review: `docs/reviews/plan-review-20260615-181139.md`; `docs/reviews/plan-review-20260615-181200.md`
- superseded plan re-review conclusion: PASS under the old durable sidecar premise; not current after replacement裁决
- superseded accepted plan commit: `f9cb56de`
- slice 1 implementation: `docs/reviews/wu-cli-fins-obs-01-s1-implementation-codex.md`
- slice 1 validation: `pytest tests/fins/test_fins_ingestion_runtime.py -q` 47 passed, 3 warnings; `pyright dayu/fins/ingestion_events.py dayu/fins/ingestion_runtime.py tests/fins/test_fins_ingestion_runtime.py` 0 errors
- slice 1 code review: `docs/reviews/code-review-20260615-183010.md`; `docs/reviews/code-review-20260615-183203.md`
- slice 1 code review adjudication: `docs/reviews/wu-cli-fins-obs-01-s1-code-review-adjudication-20260615-183453.md`
- slice 1 accepted findings requiring fix: MiMo-001 test non-terminal event append failure WARN path; DS-F002 remove event type re-export from `ingestion_runtime.__all__`; DS-F003 update `dayu/fins/README.md` and `tests/README.md`
- slice 1 deferred findings: MiMo-002 / DS-F001 sidecar sequence lookup scalability deferred to Slice S2 before high-frequency progress events
- slice 1 fix: `docs/reviews/wu-cli-fins-obs-01-s1-fix-codex.md`
- slice 1 fix validation: `pytest tests/fins/test_fins_ingestion_runtime.py -q` 48 passed, 3 warnings; `pyright dayu/fins/ingestion_events.py dayu/fins/ingestion_runtime.py tests/fins/test_fins_ingestion_runtime.py` 0 errors
- slice 1 re-review: `docs/reviews/code-review-20260615-184311.md`; `docs/reviews/code-review-20260615-184409.md`
- slice 1 re-review conclusion: PASS; accepted findings fixed 3/3; remaining blockers none
- slice 1 final local validation: `pytest tests/fins/test_fins_ingestion_runtime.py -q` 48 passed, 3 warnings; `pyright dayu/fins/ingestion_events.py dayu/fins/ingestion_runtime.py tests/fins/test_fins_ingestion_runtime.py` 0 errors
- slice 1 accepted commit: `3787f43d`
- slice 5 implementation: `docs/reviews/wu-cli-fins-obs-01-s5-implementation-codex.md`
- slice 5 validation: `pytest tests/cli/test_arg_parsing.py tests/cli/test_init_command.py tests/cli/test_prompt_command.py tests/cli/test_interactive_command.py tests/cli/test_fins_commands.py tests/cli/test_upload_filings_from_command.py -q` 110 passed, 3 warnings; `pyright dayu/cli/main.py dayu/cli/commands/fins.py dayu/service/fins_direct.py tests/cli/test_arg_parsing.py tests/cli/test_init_command.py tests/cli/test_prompt_command.py tests/cli/test_interactive_command.py tests/cli/test_fins_commands.py tests/cli/test_upload_filings_from_command.py` 0 errors
- slice 5 code review: `docs/reviews/code-review-20260615-201047.md`; `docs/reviews/code-review-20260615-201327.md`
- slice 5 code review adjudication: `docs/reviews/wu-cli-fins-obs-01-s5-code-review-adjudication-20260615-201806.md`
- slice 5 accepted findings requiring fix: S5-FIX-01 shared runtime logging helpers; S5-FIX-02 avoid duplicate ERROR logs for one exception; S5-FIX-03 direct default log-level coverage
- slice 5 fix: `docs/reviews/wu-cli-fins-obs-01-s5-fix-codex.md`
- slice 5 fix validation: `pytest tests/cli/test_arg_parsing.py tests/cli/test_init_command.py tests/cli/test_prompt_command.py tests/cli/test_interactive_command.py tests/cli/test_fins_commands.py tests/cli/test_upload_filings_from_command.py tests/runtime/test_log.py -q` 137 passed, 3 warnings; `pyright dayu/runtime/log.py dayu/cli/main.py dayu/cli/commands/fins.py dayu/service/fins_direct.py tests/cli/test_arg_parsing.py tests/cli/test_init_command.py tests/cli/test_prompt_command.py tests/cli/test_interactive_command.py tests/cli/test_fins_commands.py tests/cli/test_upload_filings_from_command.py tests/runtime/test_log.py` 0 errors
- slice 5 re-review: `docs/reviews/wu-cli-fins-obs-01-s5-rereview-mimo-20260615-203350.md`; `docs/reviews/wu-cli-fins-obs-01-s5-rereview-ds-20260615-203350.md`
- slice 5 re-review adjudication: `docs/reviews/wu-cli-fins-obs-01-s5-rereview-adjudication-20260615-204204.md`
- slice 5 re-review conclusion: PASS; accepted findings fixed 3/3; remaining blockers none
- slice 5 accepted commit: `8d93dc68`
- slice 6 implementation: `docs/reviews/wu-cli-fins-obs-01-s6-implementation-codex.md`
- slice 6 validation: `git diff --check` passed; docs-only README text verified against S1-S5 code facts; no pytest / pyright required because production and test code were unchanged
- slice 6 code review: `docs/reviews/wu-cli-fins-obs-01-s6-review-mimo-20260615-204936.md`; `docs/reviews/wu-cli-fins-obs-01-s6-review-ds-20260615-204936.md`
- slice 6 code review adjudication: `docs/reviews/wu-cli-fins-obs-01-s6-review-adjudication-20260615-205433.md`
- slice 6 review conclusion: PASS; remaining blockers none
- slice 6 accepted commit: `2d4679af`
- aggregate deepreview: `docs/reviews/wu-cli-fins-obs-01-aggregate-deepreview-mimo-20260615-205916.md`; `docs/reviews/wu-cli-fins-obs-01-aggregate-deepreview-ds-20260615-205638.md`
- aggregate deepreview adjudication: `docs/reviews/wu-cli-fins-obs-01-aggregate-deepreview-adjudication-20260615-210618.md`
- aggregate accepted findings requiring fix: AGG-FIX-01 corrupted event sidecar line recovery; AGG-FIX-02 CLI synthetic terminal fallback rendering coverage; AGG-FIX-03 `_LOGGER` Final annotation consistency
- aggregate fix: `docs/reviews/wu-cli-fins-obs-01-aggregate-fix-codex.md`
- aggregate fix validation: `pytest tests/fins/test_fins_ingestion_runtime.py tests/cli/test_fins_commands.py -q` 83 passed, 3 warnings; `pyright dayu/fins/ingestion_runtime.py tests/fins/test_fins_ingestion_runtime.py tests/cli/test_fins_commands.py` 0 errors; `git diff --check` passed
- aggregate fix re-review: `docs/reviews/wu-cli-fins-obs-01-aggregate-fix-rereview-mimo-20260615-211431.md`; `docs/reviews/wu-cli-fins-obs-01-aggregate-fix-rereview-ds-20260615-211431.md`
- aggregate fix re-review adjudication: `docs/reviews/wu-cli-fins-obs-01-aggregate-fix-rereview-adjudication-20260615-211921.md`
- aggregate fix re-review conclusion: PASS; accepted findings fixed 3/3; remaining blockers none
- aggregate fix accepted commit: `804b3b7d`
- final local validation: `pytest tests/fins/test_fins_ingestion_runtime.py tests/service/test_fins_direct.py tests/cli/test_arg_parsing.py tests/cli/test_fins_commands.py tests/cli/test_upload_filings_from_command.py tests/cli/test_init_command.py tests/cli/test_prompt_command.py tests/cli/test_interactive_command.py tests/runtime/test_log.py -q` 210 passed, 3 warnings; `pyright dayu/fins/ingestion_events.py dayu/fins/ingestion_runtime.py dayu/service/fins_direct.py dayu/cli/main.py dayu/cli/commands/fins.py dayu/cli/output.py dayu/runtime/log.py tests/fins/test_fins_ingestion_runtime.py tests/service/test_fins_direct.py tests/cli/test_arg_parsing.py tests/cli/test_fins_commands.py tests/cli/test_upload_filings_from_command.py tests/cli/test_init_command.py tests/cli/test_prompt_command.py tests/cli/test_interactive_command.py tests/runtime/test_log.py` 0 errors
- closeout: `docs/reviews/wu-cli-fins-obs-01-closeout-20260615-212045.md`
- draft PR: #143 https://github.com/noho/dayu-agent-r/pull/143
- 2026-06-16 control-doc decision: PR #143 durable job event sidecar premise is invalid for CLI direct; additionally, Fins tool awaiting may keep `ToolAwaitingOutcome(EXTERNAL_JOB)` but must not force core Fins ingestion runtime into an over-heavy durable job system. Next fix gate must handle both corrections together before merge decision.

## WU-OBS-00 Tool Trace Analyzer

### 状态

GitHub Issue #70 当前为 OPEN。本条是 Tool Trace observability / debug tooling 的基础 work unit：输入已经存在的 Tool Trace 文件或目录，输出结构化 Host / Engine / Tool 分层诊断报告。它不是 #71 的重复，而是 #71 的自然前置能力；#71 负责“先按 prompt / final answer 找到 run 并导出 bundle”，本条负责“对 trace / bundle 做诊断归因”。WU-OBS-P00 / #70 + #117 与 WU-OBS-SIGNALS-01 已完成 analyzer 所需的前置核心 trace signals；本条状态为 pending，可进入 GitHub Issue / dependency / code scope 核对与 discussion gate。对 provider / model bug 报障场景，本条应消费 WU-ENG-02 / #63 已完成的 OpenAI-compatible provider debugging correlation signals；#64 的 native Anthropic / Claude Code gateway adapter-specific signals 若尚未实现，报告必须明确 limited signal。GitHub Issue #34 是本条的 analyzer integrity / large payload diagnostics 子项，不单独实现平行 analyzer。

### 设计与代码核对

- `docs/host/design.md` 明确 Tool Trace 是 committed EventLog 的派生 projection，不是 Host recovery、resume、memory 或 Run 状态迁移真源。
- `docs/host/design.md` 要求 trace / audit 能解释工具结果保留、压缩、丢弃、召回失败、证据不足、预算未纳入 RunInput 等原因。
- `dayu/host/tool_trace.py` 当前负责从 committed EventLog 投影 Tool Trace hot row 与 cold JSONL line。
- `dayu/host/durable/tool_trace.py` 当前提供按 `run_id`、`tool_call_id`、`provider_request_id`、`diagnostic_ref` 查询 hot rows 的内部 helper。
- `tests/host/test_tool_trace_projection.py` 与 `tests/host/test_tool_trace_queries.py` 已覆盖 Tool Trace 生产、冷热投影、query helper 与分页。
- `tests/host/test_tool_trace_queries.py` 已覆盖 `provider_request_id` 可查询 terminal diagnostic chain；但当前没有 analyzer report，因此尚未覆盖“报告必须展示 provider 厂商可查 request id”的输出要求。
- 代码核对未发现现有 operator-facing Tool Trace analyzer；也未发现可对 trace 文件 / 目录生成 Host / Engine / Tool 分层诊断 Markdown / structured report 的入口。
- WU-OBS-SIGNALS-01 已将 #29 / #30 / #31 / #35 的 context budget snapshot、tool latency、structured failure metadata、provider protocol partial tool-call semantics 收敛为前置 signal contract bundle；本条进入 implementation 前仍需核对当前代码与 trace fixture 的直接证据。
- GitHub Issue #34 的旧描述提到 P7 JSONL record 引用 raw payload 文件；当前 NEW / dayu-agent-r 已转为 committed EventLog -> Tool Trace hot row / cold JSONL projection，并通过 `payload_ref` / `payload_digest`、`source_payload_ref` / `source_payload_digest`、`cold_trace_ref` / `cold_trace_digest` 表达引用与完整性。因此 #34 的目标仍成立，但验收对象应更新为当前 Tool Trace hot / cold / payload descriptor 形态。

### 目标

- 新增本地 operator-facing Tool Trace analyzer，输入当前 Dayu 产生的 Tool Trace 文件或目录，输出结构化诊断报告。
- 报告按 Host / Engine / Tool 三层归因，并且每条诊断必须指向 trace 直接证据。
- 聚合 run、attempt / iteration、tool call、final response、protocol error、usage、diagnostic ref、payload digest / ref 等 trace 记录。
- 当诊断指向 provider / model bug、provider protocol error、filtering / safety signal 或 stream/non-stream 输出异常时，报告必须包含 provider/vendor debugging block：provider-native request id、client correlation id（若存在）、本地 `run_id` / iteration / attempt / tool trace refs；缺失时明确标注 limited signal。
- 识别重复调用、工具失败、异常延迟、过大 payload、截断与 fetch_more 缺失、trace 缺字段或冷热引用不一致。
- 覆盖 #34 的完整性检查：cold JSONL 行可解析性、`line_digest` / `cold_trace_digest` 一致性、hot row 与 cold line source key 一致性、`payload_ref` / `payload_digest` 可解析性或缺失报告、重复 / 缺失 ref 诊断。
- 覆盖 #34 的大 payload 诊断：large raw input、large tool result、large provider diagnostic payload、large prompt / messages 或等价 payload descriptor 的阈值告警与排名。
- 消费 WU-OBS-P01 / P02 / P03 提供的 context pressure、tool latency 和 structured failure metadata；缺失时必须在 report 中明确标注 limited signal，而不是静默降级。
- 消费 WU-OBS-P04 提供的 provider protocol partial tool-call signals；缺失时必须能区分 limited signal 与真正无 partial。
- 结合 context pressure / truncation / governance / wait / replay / projection signal，判断问题更像 Host 治理、Engine 输出 / 解析，还是 Tool schema / result contract。
- 输出 Markdown 或等价可读报告，包含问题摘要、分层归因、证据、优先级和建议动作。

### 非目标

- 不修改 Tool Trace 生产路径语义。
- 不把分析报告作为 Host durable truth。
- 不要求接入真实 provider 或外部服务。
- 不在本条重构 ToolRuntime、Engine、Host 生产模块。
- 不实现 prompt / final answer 反查；该能力由 WU-OBS-01 / GitHub Issue #71 承接。
- 不把财报业务判断写进 analyzer；只做 trace / protocol / contract / governance 层诊断。
- 不恢复旧 P7 `raw_payloads` 文件布局；analyzer 必须以当前 Dayu Tool Trace hot / cold / payload descriptor 形态为准。

### 验收信号

- 对当前 Tool Trace 文件或目录可以生成诊断报告。
- 报告明确分组 Host / Engine / Tool 问题，并给出直接 trace 证据。
- 至少覆盖重复调用、工具失败、SSE / protocol 异常、过大 payload、截断后未续读、trace 缺字段或冷热引用不一致。
- provider / model bug 相关报告必须展示厂商可查的 provider-native request id，并回链本地 `run_id` / iteration / attempt / tool trace；OpenAI-compatible path 应消费 #63 已完成的 client correlation signal；#64 native Anthropic / Claude Code gateway adapter-specific signal 尚不可用时，报告必须明确说明 limited signal，而不是静默省略。
- #34 覆盖的 integrity checks 有测试 fixture：missing cold line、corrupt JSONL line、line digest mismatch、hot / cold source key mismatch、payload ref missing / digest mismatch 或等价当前形态的不一致。
- #34 覆盖的 large payload diagnostics 有测试 fixture：large raw input、large tool result、large provider diagnostic payload、large prompt / messages 或等价 payload descriptor 超阈值。
- 核心解析、聚合逻辑和代表性诊断规则有测试。
- README 或 usage docs 说明输入、输出和典型命令。
- WU-OBS-01 能复用本条 analyzer 或其诊断规则，而不是重新实现一套分层归因。

## WU-OBS-00B Usage Observation Projection Correlation Boundary

### 状态

Pending。该 work unit 是 GitHub Issue #119 / #70 analyzer 子项，也是 residual `WU-ENG-02-S3-R1` 的 owner。

### 动机

WU-ENG-02 已完成 provider request identity 的 shared contract，但 Slice 3 review 发现 usage observation projection signal 是否需要 `client_correlation_id` 与 `provider_request_id` 还没有 analyzer 需求证据。当前 `UsageReportedData` 不包含这些字段，Host 也不能从 `iteration_id` 推断 provider request identity。这个问题应由 analyzer 需求确认，而不是在 Host payload 中提前硬塞 correlation 字段。

### 目标

- 在 WU-OBS-00 / #70 analyzer 设计和实现时，确认 usage observation 是否需要展示 client correlation id 或 provider request id。
- 若 analyzer 需要这些字段，先扩展 Runner usage / Engine `UsageReportedData` producer contract，再补 Host payload projection 和 Tool Trace analyzer tests。
- 若 analyzer 不需要这些字段，明确关闭 `WU-ENG-02-S3-R1`，记录 usage observation 只作为 post-call observation / analyzer signal。
- 保持 provider debugging terminal 主链路与 usage observation signal 分离，避免把 provider request identity 从非同源字段推断出来。

### 非目标

- 不在 WU-OBS-00B 中实现完整 Tool Trace analyzer。
- 不通过 Host 侧 hardcode 或 `iteration_id` 推断 provider request identity。
- 不修改 WU-ENG-02 已接受的 provider request identity contract。

### 验收信号

- Analyzer plan 或 implementation 明确裁决 usage observation 是否需要 correlation fields。
- 若需要扩展，Engine producer、Host projection 与 analyzer tests 同步通过。
- 若不需要扩展，`WU-ENG-02-S3-R1` 从 active residual 表移除或标记 closed，并记录关闭依据。

## WU-OBS-01 Prompt-based Tool Trace Diagnostics

### 状态

GitHub Issue #27 与 GitHub Issue #71 高度重复。#27 的核心诉求是按 prompt / final answer 片段反查完整 Tool Trace Run；#71 是更新、更完整的 operator diagnostic entry point，覆盖按 prompt fragment 定位 session / run / iteration、导出 Tool Trace bundle，并生成 Host / Engine / Tool 分层诊断。因此本总控不把 #27 拆成独立 work unit；后续应以 #71 作为主实施入口，#27 只作为 superseded / merged 线索保留。分层诊断能力应复用 WU-OBS-00 / GitHub Issue #70 的 analyzer 或诊断规则，不另建一套平行归因逻辑。若选中的 prompt / final answer 对应 provider / model bug，#71 输出的 diagnostic bundle / report 必须保留 WU-OBS-00 生成的 vendor debugging ids。

### 设计与代码核对

- `docs/host/design.md` 明确 Tool Trace / audit / outbox / memory snapshot 都是 committed EventLog 的派生 projection，不是 Host recovery、resume、Run 状态迁移或 EventLog truth。
- `docs/host/design.md` 要求 RunInputBuilder 的上下文构造与证据纳入观测进入 tool trace / trace 体系；trace / audit 能解释保留、压缩、丢弃、召回失败和预算原因。
- `dayu/host/tool_trace.py` 当前实现 `ToolTraceProjectionConsumer`，从 committed EventLog 投影 hot row 与 cold JSONL line。
- `dayu/host/durable/tool_trace.py` 当前已有按 `run_id`、`tool_call_id`、`provider_request_id`、`diagnostic_ref` 查询 Tool Trace hot rows 的内部 helper。
- `tests/host/test_tool_trace_queries.py` 已覆盖 run / tool call / provider request / diagnostic ref 查询与分页。
- 代码中尚未看到按 prompt fragment 或 final answer fragment 反查 session / run / iteration 的 operator-facing 入口；也未看到把匹配结果、Tool Trace、prompt / response / error context 和 Host / Engine / Tool 分层诊断组装成 debug bundle 的工具。
- `USER_INPUT_ACCEPTED` payload 当前包含 `user_prompt` / `display_text`，`RUN_SUCCEEDED` payload / outbox projection 当前包含 final answer 信息；这些是 prompt / final answer 反查的自然候选数据源，但不能让 outbox、timeline 或 Tool Trace projection 反向成为 Host truth。

### 目标

- 以 #71 为主 issue，实现 operator-facing diagnostic entry point：输入 prompt 或 prompt fragment，定位候选 session / run / iteration。
- 将 #27 的 final answer fragment 反查需求纳入同一入口，而不是另建一套查询工具。
- 明确 zero-match、multi-match、ambiguous-match 的安全行为，避免误导 operator 诊断错误 run。
- 对选中的 match 导出 diagnostic bundle，包含匹配证据、prompt、final response、error / terminal context、Tool Trace events、tool calls 和 final state。
- 在 bundle 上生成 Host / Engine / Tool 分层诊断，诊断必须引用持久化记录或 trace 直接证据；该分层诊断应复用 WU-OBS-00 的 analyzer 能力或规则集。
- 当分层诊断发现 provider / model bug 或 provider protocol anomaly 时，bundle / report 必须展示 provider-native request id、client correlation id（若存在）以及本地 `run_id` / iteration / attempt / tool trace 回链，便于直接交给模型厂商定位。
- 查询与导出只能读取 persisted local data，不要求 live provider，不改变 Tool Trace production semantics。
- 明确 redaction / sensitive-data 输出策略：完整 prompt / response / trace 只能在本地 operator 显式请求下输出。

### 非目标

- 不把诊断报告写成 durable Host truth。
- 不改变 EventLog、Tool Trace、Outbox 或 Memory projection 的生产语义。
- 不在 Host / Engine 中写入财报业务语义或 policy classification。
- 不要求一次性建设大型全文搜索基础设施；可以先使用 SQLite LIKE / FTS / bounded scan / indexed projection 的 plan gate 比较后选择。
- 不把 final answer 反查单独实现成绕过 #71 bundle / layered diagnostics 的平行工具。
- 不重新实现一套与 WU-OBS-00 分离的 Host / Engine / Tool analyzer。
- 不让 UI / Service 依赖内部 durable row 作为用户功能契约；第一阶段定位为本地 operator debug tooling。

### 验收信号

- prompt fragment 与 final answer fragment 都能定位候选 session / run / iteration，并给出匹配证据。
- zero-match / multi-match / ambiguous-match 有明确输出与测试。
- 选中 match 后能导出包含 prompt、response、errors、Tool Trace rows、tool calls、terminal state 的 diagnostic bundle。
- 分层诊断覆盖 provider / model failure、filtering / safety signal when present、tool-call leakage、tool failure、repeated calls、oversized payload、trace incompleteness。
- provider / model failure 报告包含厂商可查 request id 与本地回链信息；缺失时有 explicit limited-signal 说明。
- redaction / explicit local disclosure 行为有测试，不默认泄漏完整敏感 prompt / response。
- README 或 usage docs 说明输入、输出、redaction 预期和典型命令。
- GitHub Issue #27 后续应 comment / close as duplicate 或链接到 #71，避免两条 issue 分别驱动重复实现。

## WU-AUDIT-01 Audit Ledger Viewer And Integrity Report

### 状态

GitHub Issue #72 当前为 OPEN。本条是本地 operator-facing audit ledger viewer，不是 Tool Trace analyzer，也不是 UI / Service 审计产品。它读取当前 Host `LogAuditSink(JSONL)` 输出，帮助 operator 回答“谁在什么时候、以什么身份、对什么对象、基于什么 policy / reason 做了什么治理动作”，并校验 audit JSONL 自身是否可信。Host / Engine / Tool root-cause 诊断由 WU-OBS-00 / #70 与 WU-OBS-01 / #71 承接。

### 设计与代码核对

- `docs/host/design.md` 明确 Audit 是 committed EventLog projection / sink，不是 Host truth；audit projection 不得反向成为恢复、resume 或 memory 真源。
- `docs/host/design.md` 要求 `LogAuditSink` 记录 actor / principal、source / client、request id / client request id、operation context refs / digest、session / run / attempt / execution、policy decision、reason、payload ref / digest。
- `dayu/host/audit.py` 当前普通 audit line 包含 `schema_version`、`event_sequence`、`event_id`、`event_type`、`event_class`、`occurred_at`、`session_id`、`run_id`、`attempt_id`、`execution_id`、`actor`、`principal`、`source`、`client_request_id`、`operation_context_refs`、`operation_context_digest`、`policy_decision_ref`、`policy_decision_summary`、`reason`、`payload_ref`、`payload_digest`、`line_digest`。
- `dayu/host/audit.py` 当前 purge tombstone audit line 包含 `line_kind=purge_tombstone`、`audit_record_ref`、`purge_tombstone_ref`、`deleted_counts`、`deleted_counts_digest`、`precondition_digest`、`deleted_refs_digest`、`request_context`、`source_eventlog_facts_purged=true` 与 `line_digest` 等字段。
- `tests/host/test_audit_sink.py` 已覆盖 audit JSONL 最小字段、line digest、projection replay duplicate marker、purge tombstone audit line 幂等追加；但当前没有 read-only viewer / report 入口。
- WU-RET-02 / #96 将处理 Audit JSONL rotation / retention / compaction / size reporting；本条不实现存储治理，但 viewer 设计不得阻塞未来多 JSONL 文件或 audit directory 输入。

### 目标

- 新增 read-only Audit Ledger viewer，输入显式 audit JSONL 路径；可选支持从 artifact root 派生默认 `audit/host-audit.jsonl`。
- 输出 Markdown 和 / 或 JSON，服务本地 operator 审计 review 与 issue / debug handoff。
- 提供 Summary 视图：总行数、时间范围、event type 分布、actor / source / principal 分布、policy decision 分布、purge 行数量与 integrity 状态。
- 提供 Ledger Table 视图：按 `event_sequence` 排序展示时间、event type、session / run / attempt、actor / principal / source、client request id、operation refs、policy summary、reason、line digest。
- 提供 Detail 视图：按 `event_id`、`line_digest` 或 `purge_tombstone_ref` 展开单行 refs / digests / audit fields；默认不展开敏感 payload 内容。
- 提供 Purge View：展示 destructive-operation audit rows、purge tombstone ref、audit record ref、deleted counts、precondition / deleted refs digest、source event facts purged flag、actor / source / client request id 与 operation context refs。
- 提供 Integrity Report：JSONL parse error、schema version mismatch、line digest mismatch、duplicate `event_id`、duplicate `purge_tombstone_ref`、sequence ordering anomaly、required field omission、直接可观察的 source-key / digest conflict。
- 支持基础过滤：session / run / attempt / execution、event type / class、sequence / time range、actor / principal / source / client request id、operation context refs、line kind。

### 非目标

- 不诊断 Host / Engine / Tool root cause。
- 不分析 prompt failure、model behavior 或 tool behavior。
- 不默认 dump prompt、response、tool trace、large payload 或 payload ref 内容。
- 不修改 `LogAuditSink` 写入语义，不写 EventLog、Host DB、projection checkpoint、audit marker row 或 audit JSONL。
- 不把 viewer 输出变成 Host truth。
- 不新增 Service / UI audit product。
- 不要求 live provider、外部 audit service 或 Host public API 扩展。
- 不在本条实施 WU-RET-02 / #96 的 rotation / retention / compaction。

### 验收信号

- read-only 工具可以读取当前 Host audit JSONL 并生成 audit ledger 报告。
- 支持按审计责任链、operation、受影响 session / run / attempt、event type、line kind、time / sequence range 过滤。
- Markdown / JSON 输出至少覆盖 summary、ledger table、detail、purge view、integrity report 中的核心信息。
- digest、schema version、duplicate、required fields、sequence anomalies 有测试。
- purge tombstone audit line 有专门展示，不会把 audit JSONL alone 误判为 purge completed；完成真源仍需 SQLite tombstone 验证。
- 默认不展开敏感 payload content，redaction / explicit disclosure 行为有测试。
- README 或 usage docs 说明 viewer 用途、非用途、输入、过滤、输出、敏感数据默认值，以及与 WU-RET-02 / #96 的关系。

## WU-AUDIT-02 External Audit Delivery Contract

### 状态

GitHub Issue #75 当前为 OPEN，已 currentize 为 external audit delivery contract + local validation adapters。当前没有真实外部审计系统，因此本条不应直接实现 SIEM / S3 / Kafka / 合规平台集成；第一步应先定义异步投递语义、adapter contract、checkpoint / retry / diagnostic 行为，并用本地 Noop / FileMirror adapter 验证。

### 设计与代码核对

- `docs/host/design.md` 明确 Observer / Sink / Projection 只消费已提交 EventLog，用于派生 read model 或外部投递；外部投递不能成为 Host truth。
- `docs/host/design.md` 明确 `LogAuditSink` 写失败只更新 sink-local error / diagnostic / lag，不回滚 EventLog，不影响 Host command path。
- `dayu/host/audit.py` 当前只有本地 append-only JSONL sink 与 purge tombstone audit record 写入，没有 external delivery worker / adapter contract。
- `dayu/host/durable/audit.py` 只维护 audit sink-local marker，避免 JSONL projection retry 重复写同一个 logical audit event；它不是 external delivery checkpoint。
- WU-AUDIT-01 / #72 提供 read-only audit ledger viewer；WU-RET-02 / #96 处理 Audit JSONL rotation / retention / compaction。本条只处理异步外部投递语义，不处理 viewer 或 storage governance。

### 目标

- 定义 ExternalAuditDeliveryWorker / ExternalAuditDeliveryAdapter 的强类型 contract。
- delivery input 应来自已提交 audit ledger，例如 parsed audit JSONL record 或由 audit JSONL 派生的 typed delivery record。
- 定义幂等键：优先 `line_digest`，存在 `event_id` 或 `audit_record_ref` 时作为额外 semantic key。
- 定义 checkpoint：至少能在 retry / restart 后恢复，不漏投、不产生 semantic duplicate；具体使用 path + line offset / event_sequence / line_digest 等形态留到 plan gate 裁决。
- 定义 delivery result：`delivered`、`duplicate`、`retryable_failed`、`terminal_failed`。
- 实现 NoopAdapter，用于验证 worker flow、filtering、checkpoint、幂等、retry、disabled/default behavior 和 diagnostics。
- 实现 FileMirrorAdapter，把待投递 audit records mirror 到本地 JSONL 文件或目录，模拟外部接收端并验证 crash / retry / duplicate / purge tombstone 行为。
- 保留 purge tombstone audit line 的下游语义：外部系统必须能识别源 EventLog facts 已 purge，并能看到本地 tombstone refs / digests。

### 非目标

- 不在第一步实现真实 SIEM / S3 / Kafka / 合规平台 adapter。
- 不让 external delivery 成功成为 EventLog append、Run terminal、purge completion 或本地 audit JSONL 写入的前置条件。
- 不改变 `LogAuditSink` append-only JSONL 语义。
- 不把外部系统作为 Host governance truth。
- 不要求外部文件 watcher 成为唯一 delivery 机制；Vector / Fluent Bit / Filebeat 等 file tailer 只能作为部署选项，不是 Dayu delivery 语义真源。
- 不在本条实现 WU-RET-02 / #96 的 rotation / retention / compaction。
- 不扩散敏感 payload 内容；delivery 只投递 audit record 当前已包含的字段。

### 验收信号

- 有 typed worker / adapter contract，且不依赖具体外部平台。
- NoopAdapter 与 FileMirrorAdapter 能在无真实外部系统时验证 delivery flow。
- checkpoint resume 能避免漏投和 semantic duplicate delivery。
- delivered / duplicate / retryable_failed / terminal_failed 结果有明确状态机和测试。
- delivery failure 只产生 delivery-local diagnostic / retry state，不阻塞 Host command path，不修改 Host truth。
- purge tombstone audit records 被完整投递到 FileMirrorAdapter，且保留可供下游识别 purge audit meaning 的字段。
- 测试覆盖正常投递、重复投递、retryable failure、terminal failure、checkpoint resume、malformed audit line、purge tombstone delivery。
- README 或 usage docs 说明本地 adapters、delivery contract、当前不接真实外部平台，以及未来 adapter 接入方式。

## WU-RET-00 Host Storage Lifecycle Retention Policy

### 状态

GitHub Issue #43 当前为 OPEN，已 currentize 为 Host storage lifecycle / retention umbrella。它不是已实现的 `purge_session` 本身：session-scoped destructive purge 已经完成；本条继续跟踪长期运行下非手动 purge 的 payload / descriptor / DB / workspace-level retention policy 与 operator cleanup surface。Tool Trace cold JSONL storage governance 由 WU-RET-01 / #36 跟踪；Audit JSONL storage governance 由 WU-RET-02 / #96 跟踪。

### 设计与代码核对

- `docs/host/design.md` 明确 `purge_session` 是第一版唯一 destructive EventLog retention exception。
- `dayu/host/durable/purge.py` 已实现 `purge_session_durable(...)`，在同一 transaction 内删除目标 Session 的可恢复事实、写入 tombstone 与 purge idempotency record。
- `dayu/host/README.md` 明确第一版 purge 不实现 retention scheduler、周期 GC、DB vacuum、audit JSONL rotation / compaction、外部 audit 投递或 tool trace cold JSONL retention policy。
- purge 成功后会删除目标 Session 的 EventLog rows、payload descriptor / 本地 SQLite payload、memory snapshot、minimal read model、projection checkpoint / failure、outbox terminal projection、tool trace hot rows 和旧 command idempotency rows；共享 artifact 只在没有其它 durable ref 引用时清理。
- Host payload descriptor 当前用于把大 payload 从 EventLog inline JSON 中分离，ToolRuntime accept barrier、admission、compact artifact 等路径会写入 descriptor 或 SQLite payload；长期生命周期不能靠零散 best-effort DELETE 解决。

### 目标

- 设计 Host storage lifecycle / retention policy，明确 manual purge、scheduled retention、operator cleanup 和 DB maintenance 的边界。
- 覆盖 raw payload / payload descriptor / SQLite payload 的生命周期。
- 裁决 chat/session history 在手动 purge 之外是否支持 time-window、workspace、user、run 或 session-scope cleanup。
- 覆盖 compact artifacts、diagnostic payloads、memory snapshots、read-model snapshots 与其它派生数据的保留边界。
- 设计 operator-visible cleanup / report command 或 maintenance API。
- 设计 DB maintenance：VACUUM / incremental vacuum / WAL checkpoint / size reporting 的触发策略与非 command-path 执行边界。
- 保证 checkpoint / projection / analyzer safety：清理不能破坏 pending projection、diagnostic bundle、replay / recovery 所需事实或已经承诺保留的 audit trail。

### 非目标

- 不重新实现已完成的 `purge_session`。
- 不重复 WU-RET-01 / #36 与 WU-RET-02 / #96 的 JSONL-specific rotation / compaction 实施。
- 不在 command path 中做长耗时 cleanup、VACUUM 或文件扫描。
- 不静默删除仍被 EventLog、payload descriptor、projection、audit、trace 或 analyzer 需要的 artifact。
- 不把 credential scrub 与 retention / deletion 混为一谈。

### 验收信号

- storage lifecycle policy 明确区分 manual purge、scheduled retention、operator cleanup 和 DB maintenance。
- payload descriptor / SQLite payload / artifact refs 的删除证明有测试覆盖，尤其共享引用与 projection lag 场景。
- operator 能看到 storage usage report：EventLog rows、payload descriptors、SQLite payload size、artifact size、projection tables、WAL / DB size、JSONL sizes 或其它 owner 分类。
- cleanup / retention 不影响 Host recovery、retry、replay、RunInputBuilder、memory projection 或 analyzer 直接证据。
- slow maintenance 只在显式 maintenance entrypoint / scheduler 中运行，不阻塞 EventLog append、run admission、cancel、resume 或 terminal closeout。

### 当前 gate artifacts

- plan: `docs/host/wu-ret-00-storage-lifecycle-retention-plan.md`
- plan review: `docs/reviews/wu-ret-00-plan-review-mimo.md`; `docs/reviews/wu-ret-00-plan-review-ds.md`
- plan adjudication / fix: `docs/reviews/wu-ret-00-plan-review-adjudication.md`
- plan re-review: `docs/reviews/wu-ret-00-plan-rereview-mimo.md`; `docs/reviews/wu-ret-00-plan-rereview-ds.md`
- accepted plan decision: PASS; accepted findings 12/12 fixed; DB VACUUM / SQLite space reclamation deferred to GitHub Issue #76
- accepted plan commit: `a2f94be0`
- slice 1 implementation: `docs/reviews/wu-ret-00-slice1-implementation-codex.md`
- slice 1 code review: `docs/reviews/wu-ret-00-slice1-code-review-mimo.md`; `docs/reviews/wu-ret-00-slice1-code-review-ds.md`
- slice 1 fix: `docs/reviews/wu-ret-00-slice1-fix-codex.md`
- slice 1 re-review: `docs/reviews/wu-ret-00-slice1-rereview-mimo.md`; `docs/reviews/wu-ret-00-slice1-rereview-ds.md`
- slice 1 review conclusion: PASS; accepted findings fixed 3/3; validation `pytest tests/host/test_artifact_store.py -q` 16 passed; `pyright dayu/host/durable/artifact.py tests/host/test_artifact_store.py` 0 errors; full `pyright` 0 errors
- slice 1 accepted commit: `473f1e6d`
- slice 2 implementation: `docs/reviews/wu-ret-00-slice2-implementation-codex.md`
- slice 2 validation: `pytest tests/host/test_storage_usage_report.py -q` 5 passed; `pytest tests/host/test_package_exports.py tests/host/test_import_boundary.py tests/host/test_weak_typing_guard.py -q` 28 passed; target `pyright` 0 errors
- slice 2 code review: `docs/reviews/wu-ret-00-slice2-code-review-mimo.md`; `docs/reviews/wu-ret-00-slice2-code-review-ds.md`
- slice 2 finding adjudication: MiMo F01 accepted for fix; DS Finding 2 deferred in general but current public facade error mapping fixed now; all other findings accepted or deferred-with-owner by review
- slice 2 fix: `docs/reviews/wu-ret-00-slice2-fix-codex.md`
- slice 2 fix validation: `pytest tests/host/test_storage_usage_report.py -q` 7 passed; `pytest tests/host/test_package_exports.py tests/host/test_import_boundary.py tests/host/test_weak_typing_guard.py -q` 28 passed; `pyright dayu/host/storage_maintenance.py tests/host/test_storage_usage_report.py` 0 errors
- slice 2 re-review: `docs/reviews/wu-ret-00-slice2-rereview-mimo.md`; `docs/reviews/wu-ret-00-slice2-rereview-ds.md`
- slice 2 review conclusion: PASS; accepted findings fixed 1/1; validation `pytest tests/host/test_storage_usage_report.py -q` 7 passed; `pytest tests/host/test_package_exports.py tests/host/test_import_boundary.py tests/host/test_weak_typing_guard.py -q` 28 passed; full `pyright` 0 errors
- slice 2 accepted commit: `9c044934`
- slice 3 implementation: `docs/reviews/wu-ret-00-slice3-implementation-codex.md`
- slice 3 validation: `pytest tests/host/test_storage_orphan_proof.py tests/host/test_storage_maintenance.py -q` 10 passed; `pytest tests/host/test_storage_usage_report.py tests/host/test_artifact_store.py tests/host/test_package_exports.py tests/host/test_import_boundary.py tests/host/test_weak_typing_guard.py -q` 51 passed; target `pyright` 0 errors
- slice 3 code review: `docs/reviews/wu-ret-00-slice3-code-review-mimo.md`; `docs/reviews/wu-ret-00-slice3-code-review-ds.md`
- slice 3 review conclusion: PASS; blocking findings 0; validation full `pyright` 0 errors
- slice 3 accepted commit: `4691ad9b`
- slice 4 implementation: `docs/reviews/wu-ret-00-slice4-implementation-codex.md`
- slice 4 validation: `pytest tests/host/test_storage_maintenance.py -q` 9 passed; `pytest tests/host/test_artifact_store.py tests/host/test_storage_usage_report.py tests/host/test_storage_orphan_proof.py tests/host/test_purge_session.py -q` 56 passed; target `pyright` 0 errors; `git diff --check` passed
- slice 4 code review: `docs/reviews/wu-ret-00-slice4-code-review-mimo.md`; `docs/reviews/wu-ret-00-slice4-code-review-ds.md`
- slice 4 review conclusion: PASS; blocking findings 0; validation full `pyright` 0 errors
- slice 4 accepted commit: `f5b1cccd`
- aggregate deepreview: `docs/reviews/wu-ret-00-aggregate-deepreview-mimo.md`; `docs/reviews/wu-ret-00-aggregate-deepreview-ds.md`
- aggregate deepreview conclusion: PASS; blocking findings 0; DS Finding 001 accepted and fixed; DS Findings 002/003 deferred as non-blocking diagnostics/defensive hardening; DS Open Question Q1 fixed; DS Open Question Q2 deferred as non-blocking consistency question
- aggregate deepreview fix: `docs/reviews/wu-ret-00-aggregate-deepreview-fix-codex.md`
- aggregate deepreview re-review: `docs/reviews/wu-ret-00-aggregate-deepreview-rereview-mimo.md`; `docs/reviews/wu-ret-00-aggregate-deepreview-rereview-ds.md`
- aggregate deepreview re-review conclusion: PASS; blocking findings 0; validation `pyright dayu/host/api.py dayu/host/open_host.py` 0 errors; `git diff --check` passed
- aggregate deepreview accepted commit: `26439cb2`
- draft PR readiness: ready; remaining risks have owners/destinations: DB VACUUM / SQLite space reclamation remains deferred to GitHub Issue #76; Tool Trace JSONL retention remains WU-RET-01 / GitHub Issue #36; Audit JSONL retention remains WU-RET-02 / GitHub Issue #96; DS Finding 002/003 and Open Question Q2 are non-blocking diagnostics/defensive consistency items that do not change WU-RET-00 correctness and can be reconsidered with future maintenance ergonomics work.
- draft PR: https://github.com/noho/dayu-agent-r/pull/139
- PR review: `docs/reviews/wu-ret-00-pr139-review-mimo.md`; `docs/reviews/wu-ret-00-pr139-review-ds.md`
- PR review conclusion: PASS; blocking findings 0; accepted test/documentation findings fixed; DS async event-loop I/O and package-root constant export findings deferred as non-blocking maintenance ergonomics/public-surface choices; CI checks not reported on draft PR branch, local validation passed
- PR review fix: `docs/reviews/wu-ret-00-pr139-fix-codex.md`
- PR review re-review: `docs/reviews/wu-ret-00-pr139-rereview-mimo.md`; `docs/reviews/wu-ret-00-pr139-rereview-ds.md`
- PR review re-review conclusion: PASS; blocking findings 0; validation `pytest tests/host/test_storage_maintenance.py tests/host/test_storage_orphan_proof.py -q` 18 passed; `pyright tests/host/test_storage_maintenance.py tests/host/test_storage_orphan_proof.py` 0 errors
- PR review accepted commit: `20b1b4ac`
- post-PR-review push commit: `5f591ae4`; pushed to `github/work/wu-ret-00-retention`; PR 139 merge state CLEAN at closeout check; GitHub status check rollup empty on draft PR branch
- final validation: `pytest tests/host/test_artifact_store.py tests/host/test_storage_usage_report.py tests/host/test_storage_orphan_proof.py tests/host/test_storage_maintenance.py tests/host/test_purge_session.py tests/host/test_package_exports.py tests/host/test_import_boundary.py tests/host/test_weak_typing_guard.py -q` 97 passed; full `pyright` 0 errors; `git diff --check` passed
- final closeout: draft-PR-pass; GitHub Issue #43 not closed because PR 139 is still draft/open and merge/issue closure requires separate authorization; after PR 139 merge, next entry point is WU-OBS-00 discussion gate

## WU-RET-01 Tool Trace Cold JSONL Storage Governance

### 状态

GitHub Issue #36 已 currentize：旧 P7 `ToolTraceJsonlSink._select_jsonl_file()` / `tool_calls_*.jsonl` 分片滚动描述已过期，当前定位改为 Tool Trace cold JSONL 长期存储治理。本条不作为 WU-OBS-00 / #70 的前置；#70 analyzer 可以报告 cold JSONL 过大、重复行或完整性问题，但不负责实施 rotation / retention / compaction。GitHub Issue #79 已被本条吸收：#79 的 cold trace retention / purge 后保留边界由 #36 承接；其中 shared artifact / 跨 Session 引用的删除证明属于 WU-RET-00 / #43 的 Host storage lifecycle 安全边界。

### 设计与代码核对

- `docs/host/design.md` 明确 Tool Trace 是 committed EventLog 派生 projection，不是 Host recovery、resume、memory 或 Run 状态迁移真源。
- `docs/host/design.md` 允许 cold JSONL 按 run / 日期 / workspace 分片归档，但当前实现尚未落地。
- `dayu/host/tool_trace.py` 的 `ToolTraceSinkOptions` 只有 `cold_jsonl_path`、`create_parent_dirs`、`lock_path`，没有 size threshold、rotation、retention 或 compaction policy。
- `ToolTraceProjectionConsumer._append_line()` 只向 cold JSONL 幂等追加 line；默认路径由 `open_host` 派生为 `artifact_root / "tool-trace" / "tool-trace-cold.jsonl"`。
- 当前缺口不是旧实现的“单个分片超过阈值”，而是 cold JSONL 没有生产级长期存储治理，长期运行可能持续增长。
- `dayu/host/durable/tool_trace.py` hot row 持有 `cold_trace_ref` / `cold_trace_digest`，purge 删除 hot rows 后，cold JSONL 仍可能作为离线诊断 artifact 存在；retention 需要清楚区分 hot query path 与 cold diagnostic artifact。

### 目标

- 设计并实现 Tool Trace cold JSONL rotation policy，例如按大小、日期、run / workspace 或组合策略滚动。
- 设计 retention policy，明确保留窗口、最大本地占用、归档位置、删除条件和与 `purge_session` 的边界。
- 设计 compaction / dedup 行为，覆盖 projection replay / duplicate line 的可治理性；如果 compact 后生成新 artifact，必须保留可验证 digest / source key 关系。
- 增加 size reporting / maintenance diagnostics，让 operator 能看见 cold JSONL 当前占用、分片数量、最大分片、重复行或损坏行统计。
- 明确 cold trace retention 与 shared artifact / 跨 Session 引用的关系：本条不得删除仍被 EventLog、payload descriptor、projection、audit、analyzer 或 WU-RET-00 保留策略需要的 artifact。
- 保持 projection 异步语义：rotation / retention / compaction 不得进入 EventLog append、run admission、cancel、resume、terminal closeout 等 command path。

### 非目标

- 不把 cold JSONL 变成 Host durable truth。
- 不改变 EventLog canonical fact、Tool Trace hot row 或 command path 状态机语义。
- 不实现 operator-facing Tool Trace analyzer；该能力由 WU-OBS-00 / #70 跟踪。
- 不引入跨 EventLog checkpoint 与 JSONL 文件的二阶段提交。

### 验收信号

- 长期运行后 Tool Trace cold JSONL 不再无界增长，或在配置关闭 retention 时有明确 size reporting。
- rotation / retention / compaction 行为有稳定 policy、测试和文档。
- replay / duplicate append 不会导致不可解释的长期存储膨胀。
- purge 后 hot trace 不再作为普通 read path 事实来源；cold trace 缺失、归档或被保留都有明确 diagnostic / retention reason。
- cold JSONL 缺失或被归档只影响深度诊断 / 离线审计，不影响 Host 恢复、resume、memory 或 Run 状态。
- WU-OBS-00 analyzer 若读取已 rotation / archived 的 cold trace，能得到明确的 found / missing / archived / limited signal 结果，而不是静默误判。

## WU-RET-02 Audit JSONL Storage Governance

### 状态

GitHub Issue #96 跟踪 Audit JSONL 长期存储治理。Audit 与 Tool Trace 都有 append-only JSONL 长期累积占用本地存储的问题，但 Audit 承载治理动作和责任链 projection，尤其 purge audit line 需要和 SQLite purge tombstone 形成可解释的 destructive 操作流水，因此必须单独实施。

### 设计与代码核对

- `docs/host/design.md` 明确 `LogAuditSink` 是 projection / sink，不是 Host truth，按 committed EventLog 消费并写本地 append-only JSONL。
- `docs/host/design.md` 要求 purge 完成真源仍是 SQLite tombstone；audit JSONL 记录 destructive 操作流水，不得用只有 `purge_started` 的 audit line 证明 purge 已完成。
- `dayu/host/audit.py` 的 `LogAuditSinkOptions` 只有 `audit_jsonl_path`、`create_parent_dirs`、`lock_path`，没有 size threshold、rotation、retention 或 compaction policy。
- `default_log_audit_sink_options()` 默认路径为 `artifact_root / "audit" / "host-audit.jsonl"`。
- `_append_audit_line()` 只向 audit JSONL 幂等追加 line；`dayu/host/README.md` 明确第一版 purge 不实现 audit JSONL rotation / compaction。

### 目标

- 设计并实现 Audit JSONL rotation policy，例如按大小、日期、workspace 或组合策略滚动。
- 设计 retention policy，明确本地保留窗口、最大占用、归档位置、删除条件，以及 purge audit line 的最低保留 / tombstone 关联要求。
- 设计 compaction / archival 行为：允许压缩、归档或合并旧 audit JSONL，但必须保留 line digest、source event refs、purge tombstone refs / digest 等可验证关联。
- 增加 size reporting / maintenance diagnostics，让 operator 能看见 audit JSONL 当前占用、分片数量、最大分片、损坏行、digest mismatch、purge_started / purge_completed 不完整链路等统计。
- 保持异步 projection 语义：rotation / retention / compaction 不得拖慢 EventLog append、run admission、cancel、resume、terminal closeout 或 purge command transaction。

### 非目标

- 不实现外部 audit 系统投递保证。
- 不引入复杂 AuditPolicy 规则引擎。
- 不让 audit JSONL 成为 Session / Run / EventLog 恢复真源。
- 不删除或重写 EventLog canonical facts。
- 不把 purge 是否完成的判断从 SQLite tombstone 转移到 audit JSONL。

### 验收信号

- 长期运行后 Audit JSONL 不再无界增长，或在配置关闭 retention 时有明确 size reporting。
- rotation / retention / compaction 行为有稳定 policy、测试和文档。
- purge audit line 在 rotation / retention / compaction 后仍能和 SQLite tombstone 建立可验证关联。
- 只有 `purge_started` 而无 `purge_completed` / tombstone 的链路能被报告为 incomplete attempt，不会误报 purge 已完成。
- Audit sink 失败或 maintenance 失败只影响 audit projection / maintenance diagnostics，不影响 Host command path。

## WU-STRESS-SQLITE-01 SQLite Multiprocess High-spec Stress

### 状态

GitHub Issue #38 当前为 OPEN，且 issue body 已对齐当前定位：代码里已有普通 SQLite 多进程测试与压力覆盖，本条不是重新证明基础语义，而是在 Docker Linux + 外挂慢硬盘 / 高延迟文件系统上放大验证 SQLite WAL、busy timeout、write retry、fsync、文件锁、checkpoint 与 IO jitter 风险。该入口应与普通快速 pytest / 常规 workflow 分离。

### 设计与代码核对

- `docs/host/design.md` 明确 Host durable write transaction 使用短事务、WAL、busy timeout、`BEGIN IMMEDIATE` 与有限 busy / locked retry；`event_sequence` 是 Host durable store 分配的全局 cursor。
- `tests/host/test_event_log_multiprocess.py` 已覆盖多进程 EventLog append 后 `event_sequence` 全局唯一递增，以及同 `event_id` 多进程异体写入压力下的 winner / identity conflict 分类。
- `tests/host/test_admission_multiprocess.py` 已覆盖同 slot ensure、同 Session active Run 唯一性、duplicate follow-up idempotency、queued follow-up FIFO promotion、queued cancel / promotion first-committer-wins，以及 admission 后 EventLog sequence 全局唯一递增。
- `tests/host/test_recovery_multiprocess.py` 已覆盖 live owner 不被误恢复、owner crash 后 reopen recovery 并通过 public stream 产出 final answer、projection lag 不阻塞 durable recovery。
- `tests/runtime/test_lane_multiprocess.py` 已覆盖 runtime lane 跨进程 capacity invariant、non-blocking timeout、release 后其它进程可 acquire、crashed holder 经 TTL cleanup 后可 acquire。
- 因此，普通 deterministic SQLite multiprocessing tests 已足够作为日常语义回归；#38 的缺口是更高规格、更长耗时、更依赖环境的部署压力验证。

### 目标

- 定义并落地 Docker Linux + 外挂慢硬盘 / 高延迟文件系统上的 SQLite multiprocess stress 高规格入口。
- 复用或对齐现有普通 SQLite 多进程测试覆盖面：跨进程 append、同 `event_id` 竞争、admission 幂等 / active Run 唯一性、terminal race、lease expiry / renew、stale recovery、observer drain / startup reconcile、runtime lane capacity。
- 放大 WAL / busy_timeout / write retry / checkpoint / fsync / 文件锁在慢 IO 下的行为边界。
- 输出结构化摘要：进程数、运行轮数、busy_timeout、retry 配置、数据库路径、文件系统类型或挂载说明、storage latency、busy / locked 次数、fenced count、winner terminal、recovery attempts、observer lag。
- 明确失败诊断：锁超时、retry exhaustion、重复 sequence / position、event identity conflict 分类错误、terminal race 多 winner、late owner 未被 fence、observer checkpoint 不前进、WAL / checkpoint 异常增长或失败。

### 测试入口约束

- 高规格压力测试必须与常规 unit / integration / public smoke 分开。
- 必须有独立入口，例如 pytest stress marker、独立脚本或手动 workflow；具体形式在实施 gate 中裁决。
- 默认快速 pytest 和普通 GitHub workflow 可以排除该入口。
- 入口必须支持可配置参数：进程数、轮数、DB 目录、busy_timeout、总 timeout、输出摘要路径。
- 环境不满足时必须 preflight fail-fast，并说明缺少 Docker Linux、挂载目录或写入权限等具体原因；不得用 skip 掩盖真实 race。

### 非目标

- 不放进默认快速 pytest。
- 不要求普通 GitHub workflow 默认执行。
- 不依赖真实 provider / 外部服务。
- 不打印 owner token、scope token、大 prompt 或大 tool result。
- 不用 sleep 堆出偶然通过；需要明确 gate、barrier、timeout 与可诊断失败。
- 不替代 Host crash / watch / liveness 组合压力测试；本条只负责 SQLite 多进程压力链路的高规格环境版。
- 不把高规格 stress 的环境敏感失败反向解释为语义契约变化；语义契约仍以 deterministic tests 和设计真源为准。

### 验收信号

- 有文档说明如何在 Docker Linux 中把数据库目录挂到外挂慢硬盘 / 高延迟文件系统并运行 stress。
- 高规格 stress 能在指定轮数内稳定输出 pass/fail 摘要。
- 失败时能定位到 append lock、busy retry、WAL / checkpoint、terminal race、lease renew、fencing、recovery 或 observer drain 类别。
- 默认测试入口与 stress 入口清晰分离；普通快速测试不因该 stress 增加显著耗时。
- 与现有普通 SQLite 多进程测试的关系清楚：普通测试证明语义，高规格 slow-disk / Docker run 放大 IO / locking 风险。

## WU-LIFE-03 Active Cancel Watchdog And Post-cancel Timeout

### 状态

已纳入 GitHub Issue #91；GitHub Issue #87 是 Host Lifecycle Watchdog / Supervisor umbrella。本条是 #87 下的 active Attempt cancel watchdog target，不单独引入第二套 watchdog runtime。

### 目标

- 复用 #87 的 Host lifecycle watchdog / supervisor，不另建 active cancel 专属 watchdog。
- 裁决 active cancel watchdog owner、timeout policy、Run / Attempt 终态、diagnostic payload、late terminal race 与 session cancel replay 语义。
- 明确 post-cancel timeout 后 Run / Attempt / diagnostic 的收敛路径，以及 first-committer-wins / late rejection 规则。

### 非目标

- 不直接 kill 不属于 Host 管理的外部进程。
- 不把 provider-specific cancel API 硬编码进 Host 核心。
- 不把 scheduler close 设计成 active cancel timeout closeout。

### 验收信号

- provider 卡死、stream 不结束、worker task 不响应 cancellation 时都有可测试 closeout。
- terminal event 与 diagnostic 不重复、不互相矛盾。
- GitHub Issue #87 明确跟踪设计问题、非目标和验收测试；实施前需要先回到 design gate。

## WU-GOV-01 Host Governance Terminal Taxonomy

### 状态

已裁决需要引入 `REJECTED`；后续由 GitHub Issue #88 跟踪设计与实施。

### 目标

- 引入 `RunStatus.REJECTED`，用于表达 Host governance 在执行前或执行外拒绝 Run，而不是复用执行失败语义。
- 裁决 rejected Run 的 canonical EventLog taxonomy，例如是否新增 `RUN_REJECTED`。
- 明确 hard threshold / compact failure / pre-dispatch governance failure 等场景哪些进入 `REJECTED`，哪些仍保留为 `FAILED`。
- 同步 Run status、EventLog reason、projection、public contract、retry / replay 前置条件、outbox / HostEvent 映射、文档与测试。

### 非目标

- 不为单个 failure reason 临时增加状态。
- 不让 Attempt terminal taxonomy 承担 Run-level governance 语义。

### 验收信号

- 用户可见 terminal status 与治理失败 reason 单一、不重叠。
- public contract freeze test 同步更新。

## WU-CTX-01 Provider Tokenizer / Sizing Adapter

### 状态

GitHub Issue #20 当前仍为 OPEN，且 issue body 已对齐 WU-CTX-01 当前 scope。代码核对显示 Host 仍只有 conservative estimator，没有 provider/model-aware sizing adapter；本条仍有效。

### 设计与代码核对

- `docs/host/design.md` 明确 provider tokenizer adapter 是 Host 预算治理的后续精确能力，第一版使用 conservative estimator 与 provider-aware configured limits。
- `docs/host/design.md` 目前存在一处待收敛表述：配置章节说明 `ContextBudgetPolicy` 不暴露 `reserved_output_tokens`，但 Context Governance 章节仍写 `reserved_output_tokens` 是 Host context policy 的显式 typed input。当前代码实际是 ratio-first policy，没有 `reserved_output_tokens` 字段；进入 #20 plan 前必须先裁决并修正设计表述。
- `dayu/host/context_budget.py` 当前模块 docstring 明确是 conservative estimator，不读取 Engine spec、provider overflow payload、metadata 或 extra payload。
- `estimate_context_budget(...)` 当前按文本长度、canonical JSON byte length、message overhead 和 tool schema overhead 估算 token。
- `ContextBudgetPolicy` 当前只包含 `context_window_size`、soft / hard threshold ratio、compaction 次数上限和 `policy_ref`，没有 provider/model-aware tokenizer 或 sizing adapter 字段。
- Engine README 明确 Engine 不做 proactive threshold compaction、provider-aware tokenizer 或 Host budget policy。

### 目标

- 为不同 provider / model 的 token / context sizing 建立 typed adapter 或 compatible estimator boundary。
- 让 proactive compact、reactive compact、RunInputBuilder budget material、compact before / after estimate 和 usage-observation diagnostics 使用同一 sizing abstraction。
- 支持 provider / model dimension selection，但不得在 Context Governance policy code 中硬编码 provider 名称分支。
- 保留 conservative fallback estimator，并在 diagnostics / compact facts / budget traces 中记录 estimator / sizing adapter id 与版本。
- 覆盖中文 / 英文混合财报文本、JSON / table-like excerpts、tool facts、citation / source refs、memory material、compact artifacts 和 tool schema overhead。

### 非目标

- 不在 Context Governance 中硬编码 provider 名称分支。
- 不让 Engine provider 实现反向依赖 Host。
- 不把 compact / retry / proactive threshold governance 移入 Engine。
- 不移除 conservative fallback behavior。
- 不用 metadata 或 extra payload 夹带 sizing decision。

### 验收信号

- Host 有 typed provider/model-aware sizing adapter boundary，并保留 conservative fallback。
- Proactive / reactive compact decisions 使用同一 sizing entrypoint。
- RunInputBuilder budget material、compact before / after estimates 和 usage-observation diagnostics 能引用 estimator id / version。
- Provider / model selection 与 fallback behavior 有明确测试。
- 至少覆盖一个 provider-specific 或 provider-compatible sizing implementation 加 fallback。
- 测试覆盖中文 / 英文混合财报文本、JSON / table-like excerpts、tool facts、citation / source refs 和 tool schema overhead。
- Host / Engine layering tests 继续证明无反向依赖、无 Engine-owned Host compact policy。

## WU-WAIT-01 Callback Endpoint / Auth / Replay

### 状态

research 已写入 GitHub Issue #89；本条后续按 callback adapter -> common `resolve_wait` pipeline 的方向实施。Claude Code 的 background subagent / lifecycle completion 行为可作为参考；Codex 具备 subagent orchestration，但公开 callback / hook surface 不应被假设为稳定生产 primitive。

### 目标

- 设计 callback endpoint 的认证、幂等 replay、payload digest 和错误分类。
- 将 callback 与现有 wait resolve / idempotent replay 语义对齐。
- 明确 callback endpoint 只是 transport adapter：认证、解析、校验 envelope 后调用 Host `resolve_wait`；不得直接写 EventLog、Run、Attempt 或 wait record。
- callback / poller / manual resolve 必须共用同一个 durable wait resolution pipeline。

### 非目标

- 不把 HTTP framework 细节放入 Host 核心。
- 不绕过 durable wait state。
- 不追求 Claude Code background subagent UI parity；本条只跟踪 Host wait completion callback 语义。

### 验收信号

- callback 重放、乱序、摘要不匹配、未知 wait id 都有测试。
- endpoint 层只映射输入，状态裁决仍由 Host wait 语义完成。
- 认证失败、cancelled / lost wait 的迟到 callback、同 key 不同 outcome digest 的 idempotency conflict 都有明确 diagnostic。

## WU-WAIT-02 Production Poller Loop / Backoff / Fencing / Retry

### 状态

已确认是较大的 production feature，并已用 GitHub Issue #90 跟踪。本条实施前仍需回到 design gate 讨论并更新设计真源；当前文档只冻结问题定位与实施方向。

### 目标

- 实现或接入 production poller loop。
- 为 adapter error、rate limit、cancelled abandon 和 repeated not-ready 设计 backoff。
- 防止同一 wait 被并发 poller 重复处理。
- 明确 poller loop 只负责推进 Host wait 状态，不直接向 UI 返回事件；UI / Service 仍通过 `watch_session_events` 观察 `resolve_wait` 产生的 Host events。
- 设计短生命周期 in-flight claim / fencing，防止多 poller 同时 poll / resolve 同一 wait；该 claim 不是 Attempt owner、不是 EventLog truth、不是外部 job owner。

### 非目标

- 不把 poller 做成通用 scheduler God object。
- 不让 backoff 状态污染 wait durable contract。
- 不在本条内实现 callback auth / replay。
- 不在未完成 design gate 前修改设计真源的 poller production 细节。

### 验收信号

- 同一 wait 在多 poller 下不会并发 resolve。
- adapter intermittent failure 不会丢 wait，也不会 tight loop。
- production loop 能后台运行并可被 Host close / supervisor clean stop。
- ready / lost outcome 仍必须通过 common `resolve_wait` pipeline，事件由现有 Host watch path 观察。

## WU-WAIT-03 External Job Physical Cancel / Revoke / Abandon

### 状态

已纳入 GitHub Issue #92；GitHub Issue #87 是共享 Host Lifecycle Watchdog / Supervisor umbrella。本条是 #87 下的 WAITING external job cancel / revoke / abandon target，不单独引入第二套 watchdog runtime。

### 目标

- 为外部 job 定义 best-effort cancel / revoke / abandon 协议。
- 明确外部取消失败、超时、重复取消和晚到结果的处理方式。
- 复用 #87 的 Host lifecycle watchdog / supervisor，外部 job 作为 WAITING-state watch target；target-specific adapter 只负责 provider cancel / revoke / abandon 能力。

### 非目标

- 不要求所有 provider 都支持 physical cancel。
- 不把外部 job id 当作 Host durable 主键。
- 不另建独立 wait-job watchdog；不得与 #91 的 active Attempt watchdog target 形成两套 runtime。

### 验收信号

- 支持取消和不支持取消的 adapter 都有契约测试。
- late result 与已 abandon / cancelled wait 的 diagnostic 一致。

## WU-WAIT-04 UI / Service Production-grade Awaiting E2E Smoke

### 状态

依赖 WU-WAIT-01 / GitHub Issue #89、WU-WAIT-02 / GitHub Issue #90、WU-WAIT-03 / GitHub Issue #92；不是可独立实施的 work unit。前置能力完成后，本条才作为 production-grade end-to-end smoke 进入 implementation gate。

### 目标

- 增加一条 production-grade public E2E smoke，冻结 UI / Service 正常接入 Host wait governance 的生产工作流。
- 流程覆盖 `open_host` 装配、`ensure_session`、`submit_followup(queue)`、记录 `accepted_run_id`、watch / `get_run` 观察 `WAITING`、生产 poller 或 callback 入口完成 wait resolution、同一 Run 最终产生 terminal `HostEvent` / outbox item。
- 验证 UI / Service 不直接依赖 ToolRuntime、EngineEvent、dispatch row、scheduler internals 或 wait record durable row 作为展示契约。

### 非目标

- 不在本条重新实现 callback endpoint、production poller loop、backoff、fencing 或外部 job physical cancel。
- 不新增 UI 专用 Host 分支。
- 不把 wait record 列表查询提升为普通 UI 必需契约。
- 不接受仅用 manual resolve 或测试私有 durable wait id 桥接完成的 smoke 作为 production-grade 验收。

### 验收信号

- smoke 测试能证明同一个 public watcher 在 Run 进入 `WAITING` 后继续接收由生产 poller / callback 恢复后的 terminal event。
- smoke 测试断言 `get_run(run_id).status == WAITING` 时 UI 可展示等待态，生产 wait resolution 后 Run 继续推进并最终成功。
- offline / reconnect 场景至少通过 outbox 证明 terminal item 可补读。
- 测试代码不从 UI / Service 路径导入 Host 内部 ToolRuntime、dispatch、scheduler 或 durable wait mutation API。

## WU-CM-05 LLM Compaction Proposal Typed Parsing

### 状态

GitHub Issue #93，作为 GitHub Issue #81 的后续子任务。#81 已关闭，本条 deferred 前置条件已解除；用户指定恢复推进。Plan artifact 已生成并完成 fix：`docs/host/host-issues/wu-cm-05-llm-compaction-proposal-typed-parsing-plan.md`。Plan review artifacts：`docs/reviews/plan-review-20260612-140624.md`、`docs/reviews/plan-review-20260612-140644.md`；plan re-review artifacts：`docs/reviews/plan-review-20260612-141710.md`、`docs/reviews/plan-review-20260612-141946.md`。AgentMiMo / AgentDS re-review 均为 pass，accepted findings 全部已修复；accepted plan commit `153c43e3`。WU-CM-05-S1 implementation report：`docs/reviews/wu-cm-05-s1-implementation-report.md`。Code review artifacts：`docs/reviews/code-review-20260612-143526.md`、`docs/reviews/code-review-20260612-143730.md`；controller decision：`docs/reviews/wu-cm-05-s1-code-review-controller.md`。WU-CM-05-S1 accepted slice commit `7f2ce2c5`。WU-CM-05-S2 implementation report：`docs/reviews/wu-cm-05-s2-implementation-report.md`。S2 code review artifacts：`docs/reviews/code-review-20260612-144954.md`、`docs/reviews/code-review-20260612-145145.md`；S2 fix re-review artifacts：`docs/reviews/code-review-20260612-145931.md`、`docs/reviews/code-review-20260612-145954.md`。AgentDS / AgentMiMo re-review 均为 PASS，accepted finding 已修复；WU-CM-05-S2 accepted slice commit `da8cda65`。WU-CM-05-S3 implementation report：`docs/reviews/wu-cm-05-s3-implementation-report.md`。S3 code review artifacts：`docs/reviews/code-review-20260612-151038.md`、`docs/reviews/code-review-20260612-151142.md`；S3 fix re-review artifacts：`docs/reviews/code-review-20260612-151919.md`、`docs/reviews/code-review-20260612-151955.md`。AgentMiMo / AgentDS re-review 均为 PASS，accepted docstring fix 已修复；WU-CM-05-S3 accepted slice commit `f3a3c0e3`。Aggregate deepreview artifacts：`docs/reviews/code-review-20260612-152820.md`、`docs/reviews/code-review-20260612-153234.md`；AgentDS / AgentMiMo aggregate deepreview 均为 PASS。Controller validation：`pytest tests/host/test_llm_compaction.py -q` 37 passed；`pytest tests/host/test_compaction_contract.py -q` 13 passed；`python -m pyright dayu/ tests/ utils/` 0 errors。Post-closeout cleanup 已为 `tests/host/fake_compaction.py` 补齐 JSON object 递归校验并移除测试 helper `cast(...)` residual。

### 目标

- 在 #81 确定新的 compact JSON shape 后，将 LLM proposal parsing 收敛为显式 typed validation。
- 消除 unchecked cast、宽 payload 和模糊错误分类。
- 固定转换边界：LLM raw final answer -> parse JSON -> typed LLM compaction proposal -> Host-owned `CompactionCandidate` 或 #81 后等价 typed contract。

### 非目标

- 不在 #81 前抢先实现。
- 不改变 compact output 的业务含义。
- 不放宽非法 proposal 的接受条件。

### 验收信号

- 每个 post-#81 proposal 字段都有直接验证路径。
- invalid proposal 的 diagnostic 能定位字段和原因。
- malformed JSON、缺必填字段、字段类型错误、未知 label / ref、数组超限、非法 enum / patch operation 都有测试。

## WU-CM-06 Terminal Summary Text Policy Convergence

### 状态

GitHub Issue #94，作为 GitHub Issue #81 的后续子任务。#81 已关闭，本条 deferred 前置条件已解除；用户指定恢复推进。Plan artifact：`docs/host/host-issues/wu-cm-06-terminal-summary-text-policy-plan.md`。Plan review artifacts：`docs/reviews/plan-review-20260612-154220.md`、`docs/reviews/plan-review-20260612-154418.md`；plan re-review artifacts：`docs/reviews/plan-review-20260612-154915.md`、`docs/reviews/plan-review-20260612-154942.md`；focused plan re-review artifacts：`docs/reviews/plan-review-20260612-155743.md`、`docs/reviews/plan-review-20260612-155955.md`。Implementation preflight found and corrected a plan evidence issue: memory consumer is inline-only, while durable projection / run-input adapters may hydrate descriptor-backed terminal artifact `content` into transient `final_answer` before memory consumption. AgentDS / AgentMiMo focused re-review 均为 PASS；controller editorial fix removed ambiguity and fixed Slice 1 read API policy tests to create `tests/host/test_read_api_terminal_policy.py` explicitly. Corrected plan commit `e9ca9288`。WU-CM-06-S1 implementation report：`docs/reviews/wu-cm-06-s1-implementation-report.md`。S1 code review artifacts：`docs/reviews/code-review-20260612-160858.md`、`docs/reviews/code-review-20260612-161139.md`；accepted low findings fixed: durable projection hydration test naming and malformed `terminal_summary_digest` coverage。S1 fix re-review artifacts：`docs/reviews/code-review-20260612-162004.md`、`docs/reviews/code-review-20260612-162045.md`；AgentDS / AgentMiMo re-review 均为 PASS。WU-CM-06-S1 accepted slice commit `c46993d0`。WU-CM-06-S2 implementation report：`docs/reviews/wu-cm-06-s2-implementation-report.md`。S2 code review artifacts：`docs/reviews/code-review-20260612-162954.md`、`docs/reviews/code-review-20260612-163025.md`；AgentMiMo / AgentDS review 均为 PASS。WU-CM-06-S2 accepted slice commit `956c5840`。Aggregate deepreview artifacts：`docs/reviews/code-review-20260612-163719.md`、`docs/reviews/code-review-20260612-164013.md`；AgentDS / AgentMiMo aggregate deepreview 均为 PASS。Controller validation：`pytest tests/host/test_terminal_summary_payload.py tests/host/test_read_api_terminal_policy.py tests/host/test_engine_ingest_mapping.py tests/host/test_memory_projection.py -q` 95 passed；`python -m pyright dayu/ tests/ utils/` 0 errors；`git diff --check` clean。Residual risks: caller-side overlong truncation remains explicitly out of WU-CM-06 scope and owned by caller budget/display tests；private helper / integration imports in tests are nonblocking test-scope coupling；compaction evidence explicit naming / integration coverage remains low severity because strict resolver behavior is function-tested and current docstring is not contradictory。无阻断 residual risk。WU-CM-06 accepted deepreview commit `246cd1c3`。terminal summary、assistant conclusion、episode summary、answer anchor 与 continuity 的语义边界已在现有 Host 代码中部分落地，本条以 policy matrix tests 和必要 docstring 收敛为主，不重新设计 terminal taxonomy。

### 目标

- 在 #81 后收敛 terminal summary 的来源、截断、渲染和 fallback policy。
- 避免 terminal summary 与 compact summary、assistant conclusion 语义重叠。
- 固定成功、失败、取消、lost、governance failure 与 compacted episode summary 的文本 policy 矩阵。

### 非目标

- 不重新设计 #81 已落地的 Conversation Memory 语义。
- 不把 terminal summary 变成事实引用源。
- 不改变 Run terminal taxonomy。
- 不让 compact / episode summary 冒充 terminal summary 或 final answer。
- 不借本条引入新的 public result read API。

### 验收信号

- terminal summary 在 success、failure、cancel、governance failure 下语义一致。
- 渲染测试覆盖空 summary、长 summary 和 compact 后 summary。
- memory projection 只在 policy 允许时把 terminal summary 用作 continuity，不得升级为 evidence-backed fact。

## WU-CM-08 Compaction Material Readability And Smoke Maintenance

### 状态

GitHub Issue #95，作为 GitHub Issue #81 的子任务；#81 已关闭，本条前置条件已解除，用户指定恢复推进。Issue #95 当前为 OPEN。Preflight 结论：动机成立，但 issue body 中 `stable_input` / `history_input` / `evidence_input` 是旧命名；当前设计真源和代码使用 `previous_compacted_view`、`trace_material`、`evidence_material`、`answer_material`、`current_input_anchor`。本条定位为测试可维护性和 compaction material readability cleanup，不负责裁决 Conversation Memory 语义模型。Plan artifact：`docs/host/host-issues/wu-cm-08-compaction-material-readability-smoke-plan.md`。Plan review artifacts：`docs/reviews/plan-review-20260612-164857.md`、`docs/reviews/plan-review-20260612-165055.md`；accepted findings fixed by plan amendment。Plan re-review artifacts：`docs/reviews/plan-review-20260612-165449.md`、`docs/reviews/plan-review-20260612-191500.md`；AgentMiMo / AgentDS re-review 均为 PASS。Accepted plan commit `fce2fca0`。WU-CM-08-S1 implementation report：`docs/reviews/wu-cm-08-s1-implementation-report.md`；validation `pytest tests/host/test_compact_material.py -q` 35 passed，`python -m pyright dayu/ tests/ utils/` 0 errors，`git diff --check` clean。S1 code review artifacts：`docs/reviews/code-review-20260612-170451.md`、`docs/reviews/code-review-20260612-090406.md`；AgentMiMo / AgentDS review 均为 PASS。WU-CM-08-S1 accepted slice commit `bd3515d1`。WU-CM-08-S2 implementation report：`docs/reviews/wu-cm-08-s2-implementation-report.md`；validation `pytest tests/host/test_public_compact_smoke.py -q` 11 passed, 1 skipped，`python -m pyright dayu/ tests/ utils/` 0 errors，`git diff --check` clean。S2 code review artifacts：`docs/reviews/code-review-20260612-171737.md`、`docs/reviews/code-review-20260612-200000.md`；AgentMiMo / AgentDS review 均为 PASS。WU-CM-08-S2 accepted slice commit `5cb68505`。Aggregate deepreview artifacts：`docs/reviews/code-review-20260612-172729.md`、`docs/reviews/code-review-20260612-202833.md`；AgentMiMo / AgentDS aggregate deepreview 均为 PASS；blocking findings 0；validation `pytest tests/host/test_compact_material.py tests/host/test_public_compact_smoke.py -q` 46 passed, 1 skipped；`python -m pyright dayu/ tests/ utils/` 0 errors；AgentDS 额外验证相关 7 个测试文件 178 passed, 1 skipped；`compact_material.py` coverage 87%。Residual risks: `collect_selected_compaction_request_evidence_inputs` internal function name is not LLM-facing；AgentMiMo 提出的 helper 可复用性、defensive type check 深度、control-doc 引用完整性均为低严重度非阻断观察。无阻断 residual risk。Accepted deepreview commit `366d8df1`。

### 目标

- 改善 compaction material 的 chunking、可读性和测试 fixture 可维护性。
- 保持 public memory scenario smoke 覆盖关键用户路径。
- 让 smoke 失败能定位到输入构造、material pack / chunking / prompt-local labels、compactor request / proposal、memory projection 或 RunInput rendering 边界。

### 非目标

- 不改变 memory snapshot schema。
- 不裁决或实现 #81 semantic memory categories。
- 不用 snapshot 大量金文件掩盖语义测试缺失。
- 不引入新的 compactor JSON 语义。

### 验收信号

- compaction material 结构稳定、易读，且变更有小范围测试。
- smoke 失败能定位到输入构造、compaction、projection 或 rendering 边界。

## WU-CM-09 Durable Memory Snapshot Corruption Policy

### 状态

GitHub Issue #41 当前为 OPEN，原状态为 deferred behind #81；#81 已关闭，用户指定恢复推进。Preflight 结论：动机成立，但当前代码已经具备 P8.5 的保守行为，读到 corrupt / schema-mismatched / digest-mismatched memory snapshot 时 fail closed，进入 typed repair-required 或 projection failure / WARNING，不会自动覆盖损坏 row。本 WU 不修“静默吞错”，也不让 memory snapshot 成为 truth；真实缺口是 post-#81 operator-facing corruption policy、分类诊断与显式维护入口。Plan artifact：`docs/host/host-issues/wu-cm-09-durable-memory-snapshot-corruption-policy-plan.md`。Plan review artifacts：`docs/reviews/plan-review-20260612-173823.md`、`docs/reviews/plan-review-20260612-173831.md`；AgentMiMo / AgentDS review 均为 PASS-WITH-FINDINGS，无 blocker。Findings amendment：types / classifier 改为 `dayu.host.durable.memory` owner，明确 manual corruption 归入五类 failure kind，明确 `storage_read_failed` monkeypatch 目标，补充 result `__post_init__` 校验、baseline validation 与测试组织。Focused plan re-review artifacts：`docs/reviews/plan-review-20260612-174631.md`、`docs/reviews/plan-review-20260612-174632.md`；AgentMiMo / AgentDS re-review 均为 PASS，3/3 findings 已关闭，无 blocker。Accepted plan commit `e20a8a19`。WU-CM-09-S1 implementation report：`docs/reviews/wu-cm-09-s1-implementation-report.md`；validation `pytest tests/host/test_memory_projection.py -q` 26 passed，`pytest --cov=dayu.host.durable.memory --cov-report=term-missing tests/host/test_memory_projection.py -q` 26 passed / `dayu/host/durable/memory.py` 80%，`python -m pyright dayu/ tests/ utils/` 0 errors，`git diff --check` clean。S1 code review artifacts：`docs/reviews/code-review-20260612-180244.md`、`docs/reviews/code-review-20260612-180250.md`；AgentMiMo / AgentDS review 均为 PASS，low findings fixed before accepted slice commit。S1 focused code re-review artifacts：`docs/reviews/code-review-20260612-180748.md`、`docs/reviews/code-review-20260612-180754.md`；AgentMiMo / AgentDS re-review 均为 PASS。WU-CM-09-S1 accepted slice commit `a9f77611`。WU-CM-09-S2 implementation report：`docs/reviews/wu-cm-09-s2-implementation-report.md`；validation `pytest tests/host/test_storage_maintenance.py tests/host/test_package_exports.py -q` 25 passed，`pytest --cov=dayu.host.storage_maintenance --cov-report=term-missing tests/host/test_storage_maintenance.py -q` 12 passed / `dayu/host/storage_maintenance.py` 88%，`python -m pyright dayu/ tests/ utils/` 0 errors，`git diff --check` clean。S2 code review artifacts：`docs/reviews/code-review-20260612-181714.md`、`docs/reviews/code-review-20260612-181556.md`；AgentMiMo / AgentDS review 均为 PASS。WU-CM-09-S2 accepted slice commit `77c32c32`。WU-CM-09-S3 implementation report：`docs/reviews/wu-cm-09-s3-implementation-report.md`；validation `pytest tests/host/test_memory_projection.py tests/host/test_storage_maintenance.py tests/host/test_package_exports.py -q` 51 passed，`python -m pyright dayu/ tests/ utils/` 0 errors，`git diff --check` clean。S3 code review artifacts：`docs/reviews/code-review-20260612-182602.md`、`docs/reviews/code-review-20260612-182356.md`；AgentMiMo / AgentDS review 均为 PASS。Aggregate deepreview artifacts：`docs/reviews/code-review-20260612-183208.md`、`docs/reviews/code-review-20260612-183054.md`；AgentMiMo / AgentDS aggregate deepreview 均为 PASS，blocking findings 0；validation `pytest tests/host/test_memory_projection.py tests/host/test_storage_maintenance.py tests/host/test_package_exports.py -q` 51 passed；`python -m pyright dayu/ tests/ utils/` 0 errors；`git diff --check` clean。WU-CM-09 accepted deepreview commit `3e98565d`。Post-closeout cleanup 已补充 identity read failure defensive branch focused test；scan failure、row identity failure 与 row-level corruption classes 均已覆盖。无阻断 residual risk。当前处于 completed gate。

### 当前 gate artifacts

- plan: `docs/host/host-issues/wu-cm-09-durable-memory-snapshot-corruption-policy-plan.md`
- plan review: `docs/reviews/plan-review-20260612-173823.md`; `docs/reviews/plan-review-20260612-173831.md`
- plan re-review: `docs/reviews/plan-review-20260612-174631.md`; `docs/reviews/plan-review-20260612-174632.md`
- plan re-review conclusion: AgentMiMo / AgentDS 均为 PASS; blocking findings 0; accepted findings 3/3 closed by amendment
- accepted plan commit: `e20a8a19`
- aggregate deepreview: `docs/reviews/code-review-20260612-183208.md`; `docs/reviews/code-review-20260612-183054.md`
- aggregate deepreview conclusion: PASS; blocking findings 0; validation `pytest tests/host/test_memory_projection.py tests/host/test_storage_maintenance.py tests/host/test_package_exports.py -q` 51 passed; `python -m pyright dayu/ tests/ utils/` 0 errors
- accepted deepreview commit: `3e98565d`
- draft PR: https://github.com/noho/dayu-agent-r/pull/140
- PR review: `docs/reviews/pr-review-20260614-mimo.md`; `docs/reviews/pr-review-20260614-ds.md`
- PR review fix: `docs/reviews/pr-review-fix-20260614.md`
- PR review re-review: `docs/reviews/pr-review-rereview-20260614-ds.md`
- accepted PR review commit: `306b9011`
- final closeout: `docs/reviews/final-closeout-20260614-cm-05-06-08-09.md`

### 设计与代码核对

- `docs/host/design.md` 明确 memory snapshot 是 EventLog 派生 read model，可重建、可修复，不是 Host truth；memory snapshot 与 projection checkpoint 使用同一 SQLite durable store transaction 提交。
- `dayu/host/durable/memory.py` 的 `write_memory_snapshot_with_checkpoint(...)` 在同一 transaction 内写入 snapshot 并推进 projection checkpoint。
- `write_memory_snapshot(...)` 写入前调用 `_validate_snapshot_digest(...)`，并在写入后读回校验。
- `read_memory_snapshot(...)`、`read_latest_memory_snapshot(...)` 与 `read_latest_memory_snapshot_at_or_before(...)` 会解析 snapshot JSON、恢复 typed snapshot、校验 digest，并校验 durable item kind。
- `tests/host/test_run_input_builder.py` 已覆盖 snapshot 缺失和损坏时进入 `MemoryProjectionRepairRequired`，且不改 Run / Attempt / EventLog。
- `dayu/host/durable/memory.py` 已在 `_validate_snapshot_item_kinds(...)` 中拒绝旧 durable `verified_fact` item kind；WU-CM-09-S1 需补齐对应 integrity classification / fail-closed 测试，不能把当前未确认测试覆盖当作已完成事实。

### 目标

- 在 #81 完成后，重新核对 post-#81 memory snapshot shape 与 durable projection contract。
- 明确 corrupt snapshot row 的失败来源分类：partial write、schema drift、manual DB edit、serializer bug、unsupported old row、storage corruption 或 digest mismatch。
- 设计是否需要 quarantine table、operator command、maintenance repair entrypoint 或自动 rebuild / overwrite policy。
- 如果允许自动 rebuild / overwrite，必须有 proof、checksum、backup / quarantine 与测试，且不能静默发生在 command path。
- 明确 projection failure rows、memory repair logs、operator reports 与 future analyzer 如何暴露 corrupt snapshot 状态。

### 非目标

- 不在 #81 前围绕旧 snapshot shape 做 repair / quarantine 实现。
- 不让 memory snapshot 成为 Host durable truth、recovery truth 或 EventLog 替代品。
- 不添加旧 corrupt payload 兼容 reader，除非后续迁移明确要求。
- 不静默覆盖 damaged snapshot rows。
- 不把 corrupt snapshot 当作普通可忽略 projection lag。

### 验收信号

- post-#81 memory snapshot corruption policy 已同步设计真源与本总控。
- 测试覆盖 invalid JSON、schema-mismatched JSON、digest mismatch、unsupported item kind、manual corruption 和 storage-read failure 分类。
- corrupt latest snapshot 不会污染 RunInputBuilder、compact material、prompt assembly、recovery 或 projection checkpoint。
- rebuild / quarantine / overwrite 如被引入，必须由显式 operator-facing command 或 maintenance entrypoint 触发，且保留诊断证据。
- diagnostics 保留足够 operator 分析信息，但不泄漏大 prompt / tool payload 内容。
- LLM-facing material 保持可读，不暴露 EventLog ledger wrapper、payload descriptor、digest 或 Host provenance internals。

## WU-CM-10 Conversation Memory Eval Benchmark

### 状态

GitHub Issue #80 当前为 OPEN，定位为 Conversation Memory 的评测标准真源，也是 #81 Conversation Memory overall optimization 的后续 eval implementation work。#80 的评测实现不在 #81 前落地；它要评估的是 post-#81 的 memory semantic contract、compact shape、answer anchor、evidence refs、prompt assembly / budget policy 和 RunInputBuilder 行为，而不是锁定当前旧 memory snapshot shape。但 #80 定义的评测维度会反过来约束 #81：#81 design / plan 必须说明各评测维度如何被满足、延期或排除。

### 设计与代码核对

- #81 会先裁决 Conversation Memory 的语义类型、prompt assembly / budget policy、compact JSON shape、answer anchor、trace recall / evidence refs 等核心边界。
- 当前 #80 讨论借鉴 LongMemEval / PersonaMem，但 Dayu 的核心评测目标不是通用聊天长期记忆分数，而是财报分析中的 evidence-backed facts、answer anchors、forward intent、session summaries、tool provenance 与 context governance 协同。
- 如果在 #81 前按旧 `stable layer`、`history pool`、`working_assumptions` shape 写 eval，会反过来把旧设计固化为测试 truth。

### 目标

- 在 #81 完成或形成稳定 post-#81 memory contract 后，建立 Dayu Conversation Memory 评测体系；在 #81 设计与 plan 阶段，先用 #80 作为行为 oracle 与验收约束。
- 评测覆盖跨轮事实保留、证据链完整性、任务状态延续、回答锚点 / 上下文指代、重复工具调用治理、上下文压力与 compact、财报分析专属场景。
- 第一版优先做 deterministic offline eval：固定 multi-turn scenario fixture、mock finance tool、可控长 tool result、冲突 / 更新事实、Host public scenario harness。
- 检查 memory snapshot、RunInputBuilder messages、tool call counts、diagnostics 和 final response facts。
- 指标可以包括 fact recall accuracy、unsupported fact rate、provenance coverage、anchor resolution accuracy、tool reuse efficiency、update correctness、compact robustness、diagnostic precision。

### 非目标

- 不在 #81 前绑定旧 memory snapshot shape、旧 compact JSON shape 或旧 `working_assumptions` 语义。
- 不要求引入 long-term retrieval、向量索引、public memory edit / forget API。
- 不把 LongMemEval / PersonaMem 原始任务集直接当作 Dayu 评测真源。
- 不把 LLM judge 作为第一版唯一评分真源。

### 验收信号

- #81 已完成，或已形成稳定 post-#81 memory contract，足以定义 eval fixture 和 assertions。
- 明确 Dayu Conversation Memory eval 的 scope、non-goals 与目录边界。
- 至少落地三类核心 scenario：跨轮事实保留、compact / 长上下文压力、事实更新或冲突。
- 每个 scenario 至少验证 memory snapshot、RunInputBuilder memory messages、tool call behavior、diagnostics 中两类输出。
- 文档说明如何运行 eval，以及 eval 与普通单元测试 / smoke test 的关系。

## WU-CM-11 User Profile Memory Durable Boundary And Cross-session Profile

### 状态

GitHub Issue #115，作为 GitHub Issue #81 的后续子任务；deferred behind #81。User Profile Memory 是跨 session 用户画像能力，治理边界独立于 session Conversation Memory，不应被塞进 WU-CM-01 第一阶段。

### 目标

- 设计并实现独立的 durable User Profile Memory，而不是把用户画像伪装成 `pinned_state`、`working_assumptions`、answer anchor、episode summary 或 `evidence_backed_fact`。
- 明确 profile identity boundary：workspace、account、organization、user、subject partition 或其它显式 owner。
- 明确 profile item schema、source refs、observed_at / valid_from、supersedes、confidence、confirmation policy、撤销 / 过期状态和 current preference resolution。
- 明确 privacy / control：用户可见解释、reset、delete、export、disable 边界。
- 明确 prompt assembly 边界：User Profile 可以影响风格、优先级和偏好，但不能压过本轮明确用户输入或财报 evidence。
- 映射 GitHub Issue #80 的 dynamic profile 评测维度。

### 非目标

- 不在 WU-CM-01 / #81 第一阶段内实施 durable User Profile Memory。
- 不把跨 session profile 写入 session memory snapshot 作为捷径。
- 不让 profile entries 自动升级为 evidence-backed financial facts。
- 不让 profile memory 自动驱动工具执行。
- 不在未裁决 scope 前引入长期 retrieval、向量索引或 public memory edit API。

### 验收信号

- #81 设计真源和 WU-CM-01 plan 明确 User Profile Memory 是 deferred-with-owner，owner 为 WU-CM-11 / GitHub Issue #115。
- WU-CM-11 后续 plan 能定义 durable store / projection / prompt assembly / privacy controls / tests。
- tests 或 eval scenarios 能覆盖动态偏好更新、supersession、当前偏好选择、source refs，以及不能覆盖本轮用户输入或财报 evidence。
- GitHub Issue #80 dynamic profile 评测维度被映射为 current-scope behavior、deferred owner 或 explicit non-goal。

## WU-CM-12 Conversation Memory Design Refinement And Implementation Drift Repair

### 状态

本条是用户裁决纳入本文档留痕的 immediate residual work unit，不创建 GitHub Issue。目标是把 `docs/host/conversation-memory-material-budget-discussion.md` 中已经裁决清楚的 Conversation Memory material / assemble / compact / fallback / five semantic memories 语义写回 Host 设计真源，并据此修复当前实现漂移。

2026-06-18 pre-plan design truth repair 已完成：`docs/host/design.md` 已写入 expanded `assemble(...)`、五类 Session Semantic Memory 映射、`post_compact_delta_material` / `current_input_anchor` / selected recent window / protected floor 边界、tier 0-5 fallback 状态机、no silent truncation / preview / summary 化约束、`memory_projection_policy` owner 边界、section-aware degrade 禁止动作与 fail closed 条件。两路 review 与 focused re-review 均 PASS；后续 plan / implementation / review 必须以更新后的 `docs/host/design.md` 为设计真源。

### Current gate artifacts

- design write-back: `docs/reviews/wu-cm-12-design-writeback-codex-20260618.md`
- design write-back review: `docs/reviews/wu-cm-12-design-writeback-review-mimo-20260618.md`; `docs/reviews/wu-cm-12-design-writeback-review-ds-20260618.md`
- accepted design write-back fix: `docs/reviews/wu-cm-12-design-writeback-fix-codex-20260618.md`
- focused re-review: `docs/reviews/wu-cm-12-design-writeback-rereview-mimo-20260618.md`; `docs/reviews/wu-cm-12-design-writeback-rereview-ds-20260618.md`
- design write-back validation: `git diff --check` PASS; targeted `rg` checks for tier 0-5, expanded `assemble(...)`, no silent truncation, `host_run_id` turn group, policy owner, section-aware degrade restrictions, and fallback fail closed conditions PASS.
- plan: `docs/host/host-issues/wu-cm-12-conversation-memory-drift-plan.md`
- plan review: `docs/reviews/plan-review-20260618-135627.md`; `docs/reviews/plan-review-20260618-135902.md`
- plan review adjudication: `docs/reviews/plan-review-wu-cm-12-adjudication-20260618-140218.md`
- plan re-review: `docs/reviews/plan-review-20260618-140854.md`; `docs/reviews/plan-review-20260618-141022.md`
- plan gate validation: `git diff --check` PASS; plan artifact whitespace check PASS via `git diff --no-index --check /dev/null docs/host/host-issues/wu-cm-12-conversation-memory-drift-plan.md`; WU-CLI-ACTIVITY-01 residual public smokes re-adjudicated PASS (`2 passed`).
- accepted plan commit: `8186f678`
- Slice S1 implementation: `docs/reviews/wu-cm-12-s1-implementation-codex-20260618.md`
- Slice S1 code review: `docs/reviews/code-review-20260618-142551.md`; `docs/reviews/code-review-20260618-143243.md`
- Slice S1 code review adjudication: `docs/reviews/code-review-wu-cm-12-s1-adjudication-20260618-143543.md`
- Slice S1 fix: `docs/reviews/wu-cm-12-s1-fix-codex-20260618.md`
- Slice S1 focused re-review: `docs/reviews/code-review-20260618-143944.md`; `docs/reviews/code-review-20260618-144008.md`
- Slice S1 validation: `pytest tests/host/test_compact_material.py tests/host/test_memory_projection.py tests/host/test_run_input_builder.py -q` PASS (`118 passed`); `pyright dayu/ tests/ utils/` PASS (`0 errors`); `git diff --check` PASS.
- accepted Slice S1 commit: `7f71c731`
- Slice S2 implementation: `docs/reviews/wu-cm-12-s2-implementation-codex-20260618.md`
- Slice S2 code review: `docs/reviews/code-review-20260618-151719.md`; `docs/reviews/code-review-20260618-151848.md`
- Slice S2 code review adjudication: `docs/reviews/code-review-wu-cm-12-s2-adjudication-20260618-152125.md`
- Slice S2 focused re-review: `docs/reviews/code-review-20260618-152833.md`; `docs/reviews/code-review-20260618-152931.md`
- Slice S2 validation: `pytest tests/host/test_compact_material.py tests/host/test_memory_projection.py tests/host/test_run_input_builder.py tests/host/test_dispatch_scheduler.py::test_pre_start_governance_compact_failure_is_attempt_free tests/host/test_dispatch_scheduler.py::test_reactive_compact_failure_fallback_dispatch_uses_failed_view tests/host/test_dispatch_scheduler.py::test_reactive_fallback_decision_uses_memory_policy_caps -q` PASS (`130 passed`); `pyright dayu/ tests/ utils/` PASS (`0 errors`); `git diff --check` PASS.
- accepted Slice S2 commit: `7b239aef`
- Slice S3 implementation: `docs/reviews/wu-cm-12-s3-implementation-codex-20260618.md`
- Slice S3 code review: `docs/reviews/code-review-wu-cm-12-s3-mimo-20260618-160003.md`; `docs/reviews/code-review-wu-cm-12-s3-ds-20260618-160229.md`
- Slice S3 code review adjudication: `docs/reviews/code-review-wu-cm-12-s3-adjudication-20260618.md`
- Slice S3 focused re-review: `docs/reviews/code-review-wu-cm-12-s3-rereview-mimo-20260618-161132.md`; `docs/reviews/code-review-wu-cm-12-s3-rereview-ds-20260618-161031.md`
- Slice S3 validation: `pytest tests/host/test_run_input_builder.py tests/host/test_compact_material.py tests/host/test_dispatch_scheduler.py -q` PASS (`181 passed`); `pyright dayu/host/run_input.py dayu/host/compact_material.py dayu/host/context_fallback.py tests/host/test_run_input_builder.py tests/host/test_compact_material.py tests/host/test_dispatch_scheduler.py` PASS (`0 errors`); `git diff --check` PASS.
- accepted Slice S3 commit: `3bab485c`
- Slice S4 implementation: `docs/reviews/wu-cm-12-s4-implementation-codex-20260618.md`
- Slice S4 code review: `docs/reviews/code-review-wu-cm-12-s4-mimo-20260618-164733.md`; `docs/reviews/code-review-wu-cm-12-s4-ds-20260618-164407.md`
- Slice S4 code review adjudication: `docs/reviews/code-review-wu-cm-12-s4-adjudication-20260618.md`
- Slice S4 focused re-review: `docs/reviews/code-review-wu-cm-12-s4-rereview-mimo-20260618.md`; `docs/reviews/code-review-wu-cm-12-s4-rereview-ds-20260618.md`
- Slice S4 validation: `pytest tests/host/test_dispatch_scheduler.py tests/host/test_compaction_operation.py tests/host/test_compact_material.py -q` PASS (`166 passed`); `pyright dayu/host/dispatch.py dayu/host/compact_material.py dayu/host/compaction.py tests/host/test_dispatch_scheduler.py tests/host/test_compaction_operation.py tests/host/test_compact_material.py` PASS (`0 errors`); `git diff --check` PASS.
- accepted Slice S4 commit: `c12e9952`
- Slice S5 implementation: `docs/reviews/wu-cm-12-s5-implementation-codex-20260618.md`
- Slice S5 code review: `docs/reviews/code-review-wu-cm-12-s5-mimo-20260618.md`; `docs/reviews/code-review-wu-cm-12-s5-ds-20260618.md`
- Slice S5 code review adjudication: `docs/reviews/code-review-wu-cm-12-s5-adjudication-20260618.md`
- Slice S5 validation: `pytest tests/host/test_compact_material.py tests/host/test_memory_projection.py tests/host/test_run_input_builder.py tests/host/test_dispatch_scheduler.py tests/host/test_compaction_operation.py tests/host/test_context_compact_events.py -q` PASS (`312 passed`); public continuity smokes PASS (`2 passed`); `pytest tests/host/test_public_compact_smoke.py -q` PASS (`11 passed, 1 skipped`); `python -m pyright dayu/ tests/ utils/` PASS (`0 errors`); `git diff --check` PASS.
- accepted Slice S5 commit: `2c46631b`
- residual reconciliation: `WU-CLI-ACTIVITY-01-PR-R1` closed by passing public continuity smokes; `WU-CM-12-S1-R1` closed by root-cause fix to `_facts_from_accepted_event` and focused regression coverage; `WU-CM-12-S4-R1` remains deferred-with-owner as a future reactive compact recovery follow-up requiring explicit owner assignment before implementation.
- aggregate deepreview: `docs/reviews/deepreview-wu-cm-12-mimo-20260618.md`; `docs/reviews/deepreview-wu-cm-12-ds-20260618.md`
- aggregate deepreview focused re-review: `docs/reviews/deepreview-wu-cm-12-rereview-mimo-20260618.md`; `docs/reviews/deepreview-wu-cm-12-rereview-ds-20260618.md`
- aggregate deepreview validation: aggregate Host/public suite PASS (`330 passed, 1 skipped`); `pyright dayu/ tests/ utils/` PASS (`0 errors`); `git diff --check` PASS.
- final closeout: `docs/reviews/wu-cm-12-final-closeout-20260618.md`
- final closeout residuals before user review: `WU-CLI-ACTIVITY-01-PR-R1` and `WU-CM-12-S1-R1` closed; `WU-CM-12-S4-R1` deferred to WU-CM-13; accepted tool evidence material retrieval-volume audit item was initially deferred.
- draft PR #150 was opened at https://github.com/noho/dayu-agent-r/pull/150, but user review reopened WU-CM-12 before draft-PR-pass acceptance. Reopened fix scope `WU-CM-12-FIX-R1`: EventLog-derived LLM-facing input material is legal by default and must not be rejected by private compact DTO field-length guards, default evidence chunking, or `_ACCEPTED_TOOL_EVIDENCE_MATERIAL_LIMIT`; shrinkage must be expressed by selected-window policy, protected floor, context budget, provenance-preserving selection, or fail-closed behavior.
- WU-CM-12-FIX-R1 accepted repair plan: `docs/host/host-issues/wu-cm-12-fix-r1-material-guard-plan.md`
- WU-CM-12-FIX-R1 plan review: `docs/reviews/plan-review-20260618-182749.md`; `docs/reviews/plan-review-20260618-182916.md`
- WU-CM-12-FIX-R1 plan review adjudication: `docs/reviews/plan-review-wu-cm-12-fix-r1-adjudication-20260618-183756.md`
- WU-CM-12-FIX-R1 focused plan re-review: `docs/reviews/plan-review-20260618-183710.md`; `docs/reviews/plan-review-20260618-183827.md`
- WU-CM-12-FIX-R1 plan gate validation: `git diff --check` PASS. Review findings accepted and closed: Slice 2 material view mapping clarified; default evidence chunk helper retention ambiguity closed by delete-if-no-production-caller; no-default-chunk test assertions specified; long-session evidence scan performance residual deferred to a future Host material source performance hardening WU, not WU-CM-13.
- accepted WU-CM-12-FIX-R1 plan commit: `d904445e`
- WU-CM-12-FIX-R1 Slice 1 implementation: `docs/reviews/wu-cm-12-fix-r1-s1-implementation-codex-20260618.md`
- WU-CM-12-FIX-R1 Slice 1 code review: `docs/reviews/code-review-20260618-184822.md`; `docs/reviews/code-review-20260618-185121.md`
- WU-CM-12-FIX-R1 Slice 1 fix: `docs/reviews/wu-cm-12-fix-r1-s1-fix-codex-20260618.md`
- WU-CM-12-FIX-R1 Slice 1 focused re-review: `docs/reviews/code-review-20260618-185732.md`; `docs/reviews/code-review-20260618-185843.md`
- WU-CM-12-FIX-R1 Slice 1 validation: `pytest tests/host/test_compact_material.py tests/host/test_llm_compaction.py tests/host/test_compaction_operation.py -q` PASS (`127 passed`); `pyright dayu/host/compaction.py dayu/host/compact_material.py tests/host/test_compact_material.py tests/host/test_llm_compaction.py tests/host/test_compaction_operation.py` PASS (`0 errors`); `git diff --check` PASS.
- accepted WU-CM-12-FIX-R1 Slice 1 commit: `21ae992b`
- WU-CM-12-FIX-R1 Slice 2 implementation: `docs/reviews/wu-cm-12-fix-r1-s2-implementation-codex-20260618.md`
- WU-CM-12-FIX-R1 Slice 2 code review: `docs/reviews/code-review-20260618-191048.md`; `docs/reviews/code-review-20260618-191823.md`
- WU-CM-12-FIX-R1 Slice 2 code review adjudication: `docs/reviews/code-review-wu-cm-12-fix-r1-s2-adjudication-20260618.md`
- WU-CM-12-FIX-R1 Slice 2 validation: `pytest tests/host/test_run_input_builder.py tests/host/test_compact_material.py -q` PASS (`118 passed`); `pyright dayu/host/run_input.py tests/host/test_run_input_builder.py tests/host/test_compact_material.py` PASS (`0 errors`); old private accepted-evidence limit symbols absent from `dayu` and `tests`; `git diff --check` PASS.
- accepted WU-CM-12-FIX-R1 Slice 2 commit: `f468654c`
- WU-CM-12-FIX-R1 Slice 3 validation: `docs/reviews/wu-cm-12-fix-r1-s3-validation-codex-20260618.md`
- WU-CM-12-FIX-R1 Slice 3 code review: `docs/reviews/code-review-20260618-192722.md`; `docs/reviews/code-review-20260618-192801.md`
- WU-CM-12-FIX-R1 Slice 3 focused re-review: `docs/reviews/code-review-20260618-193123.md`; `docs/reviews/code-review-20260618-193135.md`
- WU-CM-12-FIX-R1 Slice 3 adjudication: `docs/reviews/code-review-wu-cm-12-fix-r1-s3-adjudication-20260618.md`
- WU-CM-12-FIX-R1 Slice 3 validation commands: combined Host memory/compact/run-input suite PASS (`240 passed`); repository pyright PASS (`0 errors`); old private guard symbols absent from `dayu` and `tests`; `git diff --check` PASS.
- accepted WU-CM-12-FIX-R1 Slice 3 commit: `cc30b304`
- WU-CM-12-FIX-R1 aggregate deepreview: `docs/reviews/code-review-20260618-193713.md`; `docs/reviews/code-review-20260618-195224.md`
- WU-CM-12-FIX-R1 aggregate accepted findings: DS low finding `_provenance_from_evidence_blocks` dead `evidence_blocks` parameter accepted and fixed; MiMo low finding stale chunking test name accepted and fixed. No blocking correctness findings remained.
- WU-CM-12-FIX-R1 aggregate fix: `docs/reviews/wu-cm-12-fix-r1-aggregate-fix-codex-20260618.md`
- WU-CM-12-FIX-R1 aggregate focused re-review: `docs/reviews/code-review-20260618-195017.md`; `docs/reviews/code-review-20260618-195038.md`
- WU-CM-12-FIX-R1 aggregate fix validation: `pytest tests/host/test_compact_material.py tests/host/test_compaction_operation.py -q` PASS (`90 passed`); `pyright dayu/host/compact_material.py tests/host/test_compaction_operation.py` PASS (`0 errors`); full `pyright dayu/ tests/ utils/` PASS (`0 errors`); `git diff --check` PASS.
- accepted WU-CM-12-FIX-R1 aggregate deepreview commit: `a729ab18`
- WU-CM-12-FIX-R1 local gate conclusion: implementation, slice reviews, aggregate deepreview fix and focused re-review are complete. `WU-CM-12-FIX-R1` is closed locally; next gate is push existing branch to update draft PR #150, then run PR review before draft-PR-pass / final closeout.
- WU-CM-12-FIX-R1 push to draft PR #150: branch `wu-cm-12-conversation-memory-drift` pushed through commit `5382afc7`; PR #150 remained open draft at https://github.com/noho/dayu-agent-r/pull/150.
- WU-CM-12-FIX-R1 PR review: `docs/reviews/pr-150-review-20260618-195915.md`; `docs/reviews/pr-150-review-20260618-200404.md`
- WU-CM-12-FIX-R1 PR review adjudication: core FIX-R1 material-guard objective PASS in both reviews. Accepted and fixed only local quality findings for fallback `current_input_ref` diagnostic ordering and fallback selected-window cap boundary tests. `compaction_evidence.py` cleanup and recovery-tier rejected-attempt diagnostic completeness remain deferred / non-blocking residuals for later cleanup or diagnostics owner; `_facts_from_accepted_event` old bug fix must be called out in final closeout. The earlier `_vnext_compact_candidate_semantic_lines` defensive-depth asymmetry residual was closed by the follow-up user裁决 deleting compact output `MAX_VNEXT_*` guards.
- WU-CM-12-FIX-R1 PR review fix: `docs/reviews/wu-cm-12-pr-review-fix-codex-20260618.md`
- WU-CM-12-FIX-R1 PR review focused re-review: `docs/reviews/code-review-20260618-201316.md`; `docs/reviews/code-review-20260618-201451.md`
- WU-CM-12-FIX-R1 PR review fix validation: `pytest tests/host/test_run_input_builder.py -q` PASS (`80 passed`); `pyright dayu/host/context_fallback.py tests/host/test_run_input_builder.py` PASS (`0 errors`); full `pyright dayu/ tests/ utils/` PASS (`0 errors`); `git diff --check` PASS.
- accepted WU-CM-12-FIX-R1 PR review commit: `6b66732f`
- WU-CM-12-FIX-R1 current next gate: push accepted PR review commit and control-doc record to existing draft PR #150, then complete draft-PR-pass / final closeout.
- WU-CM-12-FIX-R1 final push: branch `wu-cm-12-conversation-memory-drift` pushed to draft PR #150 through the final closeout commit; PR remains open draft with no GitHub status checks reported at closeout time.
- WU-CM-12-FIX-R1 final closeout: `docs/reviews/wu-cm-12-fix-r1-final-closeout-20260618.md`
- WU-CM-12-FIX-R1 follow-up user裁决: compact output `MAX_VNEXT_*` parser safety guards are deleted because model output size is already bounded by model/provider output limits; parser / DTO keep schema, type, non-empty, uniqueness and provenance validation only.
- WU-CM-12-FIX-R1 final closeout constant audit: no remaining production code constant acts as a private field-length cap, lossy preview / summary cap, default evidence chunk cap, accepted-evidence row cap, or compact output parser item / text cap for EventLog-derived LLM-facing material outside `memory_projection_policy`. Retained non-policy constants are fixed message-envelope estimators, diagnostics limits, projection maintenance batch size, or prompt-local label grammar constants.
- WU-CM-12-FIX-R1 final residual owners: `WU-CM-12-S4-R1` remains deferred to WU-CM-13 only when explicitly assigned; `WU-CM-12-PR-R1` compact evidence cleanup and `WU-CM-12-PR-R3` recovery-tier diagnostic completeness are deferred-with-owner and not blockers. `WU-CM-12-PR-R2` is closed by deleting compact output `MAX_VNEXT_*` guards.
- WU-CM-12-FIX-R1 final state: draft-PR-pass. PR #150 remains draft; no merge, mark-ready, reviewer request, external issue closure, or follow-up WU selection was performed.
- WU-CM-12 final closeout 2026-06-19 three-way deepreview artifacts: `docs/reviews/repo-review-20260619-164637.md`, `docs/reviews/repo-review-20260619-164912.md`, `docs/reviews/repo-review-20260619-165328.md`.
- WU-CM-12 final closeout 2026-06-19 accepted fixes: proactive compact recovery persists operation-level rejected attempts from initial and recovery tiers with continuous attempt numbers; reactive recovery catch-up failure no longer blocks recovery dispatch; reactive fail-closed propagates recovering fail rejection; proposal cancellation after manifest recording returns a cancellation rejected attempt with manifest ref when Host cancellation is active; memory projection skips missing-run-id turn-floor protection and JSON bool integer confusion is rejected.
- WU-CM-12 final closeout 2026-06-19 focused re-review: AgentCodex and AgentDS reported blocking findings closed; AgentMiMo reported high-priority coverage findings closed and only non-blocking old debt / broader design observations remaining. Accepted formatting observation in `dispatch.py` was fixed before closeout.
- WU-CM-12 final closeout 2026-06-19 validation: `pytest tests/host/test_dispatch_scheduler.py tests/host/test_engine_ingest_mapping.py tests/host/test_memory_projection.py tests/host/test_compact_material.py tests/host/test_compaction_operation.py -q` PASS (`277 passed`); focused dispatch regression after final formatting fix PASS (`2 passed`); `pyright dayu/ tests/ utils/` PASS (`0 errors`).
- WU-CM-12 final closeout 2026-06-19 artifact: `docs/reviews/wu-cm-12-final-closeout-20260619.md`.
- WU-CM-12 final closeout 2026-06-19 residual reconciliation: `WU-CM-12-PR-R3` is closed by persisted recovery-tier rejected attempts; `WU-CM-13` remains deferred and not default next entry; broader old-debt observations require separate owner assignment.

### Design source / phaseflow 启动裁决

下一轮启动 `$phaseflow` 时，推荐入口为：

```text
$phaseflow design_doc=docs/host/conversation-memory-material-budget-discussion.md control_doc=docs/host/issues-implementation-control.md
```

原因：本 WU 启动时 `docs/host/design.md` 尚未包含本轮讨论中对 normal path、five fallback tiers、展开版 `assemble(...)`、compact / dispatch fallback 输入输出、accepted compact 五类 memory 输出，以及 no silent truncation / cap ownership 的细化，因此先以讨论稿作为 phaseflow 启动设计输入完成 design truth repair。

本 WU 的 pre-plan design truth repair 已完成并通过两路 review / focused re-review。后续 plan、implementation、review 与 finding adjudication 必须以更新后的 `docs/host/design.md` 为设计真源；讨论稿只保留为 rationale / handoff reference，不再替代设计真源。

如果 plan 需要修改 Host / Engine public API、durable schema、EventLog canonical semantics、Engine provider contract 或跨层 contracts，必须在 plan gate 停下来交给用户裁决；不得在 implementation 中顺手修改。

### 目标

- 将 Conversation Memory 设计从以下源头无歧义细化到可实施层：

```text
rendered_context =
  assemble(
    latest_accepted_compacted_view,
    post_compact_delta_material,
    current_input_anchor,
    selected_recent_window_policy,
    protected_recent_floor_policy
  )
```

- 在 `docs/host/design.md` 中定义 normal path 与 five fallback tiers：
  - tier 0 normal；
  - tier 1 compact recovery with tighter recent window；
  - tier 2 compact recovery with section-aware compacted view degrade；
  - tier 3 compact recovery delta-only；
  - tier 4 dispatch fallback floor-only；
  - tier 5 dispatch fallback current-input-only。
- 明确 tier 1-3 送 LLM compactor，accepted output 可提交 `CONTEXT_COMPACTED` 并 projection 为五类 Session Semantic Memory；tier 4-5 不送 LLM compactor，不提交 `CONTEXT_COMPACTED`，不生成 compact artifact / memory snapshot / 五类 memory。
- 明确 accepted compact output 只能投影为：
  - `trace_memory.reference_continuity_items`；
  - `evidence_fact_memory.evidence_backed_facts`；
  - `session_summary_memory.summary_text`；
  - `answer_anchor_memory.anchors`；
  - `forward_intent_memory.intents`。
- 将 `memory_projection_policy` 在 Host 内部解释为明确分组的 typed sections，至少包括：
  - `selected_recent_window_policy`；
  - `fallback_selected_recent_window_policy`；
  - `protected_recent_floor_policy`；
  - `semantic_memory_section_caps`；
  - `projection_repair_policy`。
  JSON 结构是否保持 flat 可由 plan 裁决，但 Host 内部不得继续用零散字段和私有常量共同决定 LLM-facing material 产量。
- 强约束 Agent：`latest_accepted_compacted_view`、`post_compact_delta_material`、`current_input_anchor` 进入 LLM-facing memory / compact / RunInput material 时禁止截断、preview 化或 summary 化。上下文缩小只能通过 deterministic selection、whole-item / whole-section keep-drop、chunking with provenance 或 fail closed 表达；不能把这些源 material 改写成摘要、预览文本或字段级裁剪文本。
- 修复当前实现漂移：字段级 silent truncation、compact input DTO 私有 1200 cap、ordinary RunInput compact summary 旁路、compactor output schema cap 与 `memory_projection_policy` 双真源、fallback selected window policy 未真正生效、selection / rendering material id 空间漂移、turn floor 按 raw item 而非 `host_run_id` turn group 保护等问题。
- 覆盖 residual `WU-CLI-ACTIVITY-01-PR-R1`：重新裁决并修复 Host public multiturn / tool wiring conversation memory smoke 中 final answer / tool result continuity 相关失败，前提是修复必须对齐本 WU 写回后的 Conversation Memory 设计真源。
- 保持代码修复与设计写回同源：实现只能细化更新后的 `docs/host/design.md`，不得重新发明 compact selector、fallback selector、memory material 产量路径或 summary / preview 语义。

### 非目标

- 不引入 semantic search、vector recall、prompt-conditioned retrieval 或长期 memory retrieval framework。
- 不实现 User Profile Memory；该能力仍由 WU-CM-11 / GitHub Issue #115 承接。
- 不实现 Conversation Memory eval benchmark；该能力仍由 WU-CM-10 / GitHub Issue #80 承接。
- 不修改 UI / log / diagnostic preview 的展示截断规则，除非发现它们被错误投影进 LLM-facing memory material。
- 不修改 tool 原始输出抓取、下载、转换或 tool truncation policy。
- 不把 fallback tier / compact diagnostic / projection diagnostic 投影给 LLM 作为业务事实。
- 不把讨论稿中的 `Implementation Handoff Notes`、current code owner、current gap、allowed files、测试命令或 plan slice 参考写入 `docs/host/design.md` 作为设计真源。

### 验收信号

- `docs/host/design.md` 已写入 normal + five fallback tiers、展开版 `assemble(...)`、compact / dispatch fallback 输入输出、five semantic memory output、no silent truncation、cap ownership 与 fallback state machine。
- `docs/host/design.md` 写回内容足以让 Gateflow plan 从设计真源直接进入 implementation，不需要实施 Agent 再从讨论稿补设计。
- `dayu/config/execution_profiles.json` 中 `memory_projection_policy` 的字段在 Host 内部有单一 typed section 解释入口，至少覆盖 selected recent window、fallback selected recent window、protected floor、semantic memory section caps 与 projection repair；不再被 DTO / schema 私有 cap 改写为另一套 LLM-facing material 产量真源。
- normal RunInput、compact input、tier 1-3 compact recovery fallback、tier 4-5 dispatch fallback 共享同一个 material selection / rendering 语义，差异只在 renderer、source label、accept barrier 和 tier output。
- `protected_recent_floor_policy` 以 `host_run_id` 为 turn group 保护最近 N 个 Host admitted user Run；floor 超预算时进入 tier 5，而不是静默截断或打散 turn group。
- final closeout 必须输出一份代码常量审计清单：列出代码中仍出现、且没有在 `dayu/config/execution_profiles.json` 的 `memory_projection_policy` 中定义的 LLM-facing memory material / compact material 产量相关常量；对每个常量说明状态为“已删除 / 已迁入 policy / 保留但非 LLM-facing / 保留为 parser safety guard / deferred-with-owner”，并说明理由。
- 受影响 Host memory / compact / RunInput / fallback tests 和相关 smoke 已更新并通过；`python -m pyright dayu/ tests/ utils/` 通过且不新增类型错误。

## WU-CM-13 Unified Conversation Compact Pipeline Convergence

### 状态

Deferred destination only。当前不创建 GitHub Issue，不是默认 next entry point，不进入 implementation。它承接 `WU-CM-12-S4-R1`，但 owner 语义经代码核对后重新收敛：问题不是“reactive recovery sequencing 从零缺失”，而是 proactive / reactive 目前只共享部分 compact 内核，尚未共享从 Conversation Memory material 到 accepted compact / failed compact / fallback decision 的完整 Host compact pipeline。

当前代码事实：reactive path 已具备 Engine ingest recovery sequencing、run-local cancellation token 传递、execution / cursor commit guard、accepted compact 后 recovery Attempt 启动，以及 fallback dispatch / fail-closed ordering。`WU-CM-13` 不应再按“补 reactive 状态机”理解；它的目标是消除 compact semantic pipeline 分散在 `dispatch.py` 与 `engine_ingest.py` 后导致的语义漂移风险。

实施顺序允许 `WU-CM-14` 先于 `WU-CM-13`。若 `WU-CM-14` 先落地 recent final answer preservation 逻辑，`WU-CM-13` 后续激活时必须把该逻辑作为 compact semantic pipeline 的组成部分重新核对并纳入共享路径；不得把 `WU-CM-14` 留作 proactive-only、reactive-only 或 RunInput-only 的旁路例外。

### 背景与动机

从第一性原理看，proactive compact 与 reactive compact 的触发 envelope 不同，但 compact 语义本身应是同一套：给定同源 EventLog / material source、latest accepted compacted view、post-compact delta material 与 current input anchor，Host 应通过同一组 selection / rendering / compact operation / quality gate / accepted-or-failed result construction 得到：

- accepted `CONTEXT_COMPACTED`，由 Conversation Memory projection 物化为五类 Session Semantic Memory；
- 或 `CONTEXT_COMPACTION_FAILED`，携带 retry / repair / fallback diagnostic；
- 或 tier 4/5 fallback decision input，只影响本次 RunInput rendering，不提交 compacted memory truth。

当前实现已共享 `run_compaction_operation()`、compact material pack builder 与 context event payload builder，但 proactive 与 reactive 仍分别拥有 material-to-result orchestration、accepted compact event append、failed compact event append、fallback decision glue，以及 tier 1-3 / multi-pass / tier 4/5 的局部策略入口。若继续分散实现，五类 Session Semantic Memory、展开版 `assemble(...)`、tier 1-3 compact recovery、tier 4/5 fallback、artifact / payload descriptor、attempt_count / rejected-attempt diagnostic 和 accepted compacted view 语义都可能漂移。

`WU-CM-14` 的 recent final answer preservation 也是同一原则下的 compact / RunInput material 语义：触发方式可以不同，但给定同一段 history、同一个 current input anchor、同一个 compact candidate / fallback decision 时，preservation 结果不应因 proactive 或 reactive trigger 漂移。若 `WU-CM-14` 在 `WU-CM-13` 之前实现，`WU-CM-13` 需要把它纳入 unified pipeline audit，而不是只统一既有 compact event construction。

外层状态机仍必须分开：proactive 是 pre-dispatch input governance；reactive 是 Engine overflow 后关闭当前 Attempt、Run 进入 `RECOVERING`、再启动 recovery Attempt。`WU-CM-13` 只统一 compact semantic pipeline，不把 proactive / reactive lifecycle 强行合并。

### 目标

- 抽出一个 Host 内部 compact pipeline owner，使 proactive / reactive 共享从 material view / material blocks 到 compact result 的语义代码路径。
- 若 `WU-CM-14` 已先实施，审计其 recent final answer preservation owner，并将其纳入 proactive / reactive shared compact material、fallback material 或 RunInput assembly 路径；不得保留触发方式专属的 preservation 分支。
- 收口 `dayu/host/compaction_evidence.py` 的旧 owner 状态：若其能力已由 unified pipeline / `compact_material.py` 覆盖，则删除模块并迁移测试；若仍有必要能力，则迁入 unified pipeline，不保留无生产调用的旁路 material helper。
- 统一 compact request generation：latest accepted compacted view、post-compact delta material、current input anchor、selected material blocks、prompt-local labels、source boundary refs 与 accepted evidence mapping refs 必须同源。
- 统一 compact recovery tiers：tier 1 fallback selected recent window、tier 2 section-aware compacted view degrade、tier 3 delta-only compact input 必须对 proactive / reactive 使用同一组 request builder / renderer 规则；reactive 需要 multi-pass 时也必须建立在同一组 material block 与 provenance 语义上。
- 统一 accepted compact result construction：artifact JSON、payload descriptor、`CONTEXT_COMPACTED` payload、accepted proposal manifest refs、quality check result、budget after compact、projection signal 与 accepted compacted view 语义不得在 dispatch / engine ingest 两处重复漂移。
- 统一 failed compact / fallback result construction：`CONTEXT_COMPACTION_FAILED` payload、attempt_count、retry / repair budget exhausted、rejected attempt diagnostic refs、tier 4/5 fallback input window、fallback budget result 与 fallback action 必须由同一套 helper 生成。
- 保持五类 Session Semantic Memory projection 只消费 accepted `CONTEXT_COMPACTED`；fallback、diagnostic、Host governance state、Engine state 不得被投影为业务事实。

### 非目标

- 不新增另一套 reactive-only compact implementation。
- 不保留 `dayu/host/compaction_evidence.py` 作为无生产调用、仅测试依赖的 shadow owner。
- 不把 dispatch lifecycle、Engine ingest lifecycle、Attempt closeout、`RUN_RECOVERING`、recovery Attempt creation 合并成一个 God pipeline；这些仍由各自 outer orchestration 持有。
- 不修改 public API、durable schema、EventLog canonical semantics、Engine provider contract 或跨层 contract，除非 `WU-CM-13` 激活后在 plan gate 获得单独裁决。
- 不把 unified pipeline 用作私有 DTO 字段长度上限、preview 化、summary 化、默认 evidence 条数限制或字段级裁剪的依据。
- 不引入 semantic search、vector recall、长期 memory retrieval framework 或 User Profile Memory。
- 不改变 `WU-CM-12` 已接受的 proactive / reactive lifecycle 语义，除非后续设计真源明确修订。

### 激活条件

- 用户或 GitHub Issue 明确指定 `WU-CM-13` 为 active owner；仅有 `WU-CM-12-S4-R1` deferred row 不足以启动实现。
- 若 `WU-CM-14` 已经进入 plan 或 implementation，`WU-CM-13` preflight 必须读取其设计裁决、代码路径和测试，明确哪些 preservation helper 属于 unified compact pipeline audit 范围。
- 启动时重新核对 `docs/host/design.md`、`docs/engine/design.md` 与本总控，确认 unified compact pipeline 仍符合 Conversation Memory 的 normal / fallback state machine、five semantic memory、`assemble(...)` 与 no silent truncation 约束。
- 若计划触及 Host / Engine public API、durable schema、EventLog canonical semantics 或 provider contract，必须在 plan gate 停下交给用户裁决。

### 验收信号

- `WU-CM-13` plan 明确 shared compact pipeline owner、outer proactive / reactive lifecycle boundary、commit guard 输入、result shape、fallback ordering 与测试边界。
- `WU-CM-13` plan 明确 `WU-CM-14` recent final answer preservation 与 shared compact pipeline 的关系：若该逻辑已存在，必须说明它被迁入 / 复用 / 保持在共享 owner 下；若尚未存在，必须说明未来 `WU-CM-14` 不得绕过 shared owner。
- proactive 与 reactive 的 compact request builder 使用同一组 material selection / rendering helper；差异只来自 trigger envelope、attempt / execution identity、cancellation token 与 commit guard。
- proactive 与 reactive 下的 recent final answer preservation / fallback / RunInput assembly 语义一致；如果某一路径不适用，测试或 plan 必须用状态机证据说明它不会经过该 preservation owner。
- `dayu/host/compaction_evidence.py` 已删除并完成测试迁移，或其仍需要的能力已迁入 unified compact pipeline owner 且存在生产调用；不得留下只有测试 import 的 Host material owner。
- proactive 与 reactive 的 accepted compact artifact / payload descriptor / `CONTEXT_COMPACTED` payload 由同一组 helper 生成；测试断言同一 compact candidate 在两种触发路径下产生一致的 accepted compacted view 语义。
- proactive 与 reactive 的 `CONTEXT_COMPACTION_FAILED` / tier 4/5 fallback diagnostic 由同一组 helper 生成；测试覆盖 fallback dispatch 与 fail-closed。
- 测试覆盖 proactive tier 1、tier 2、tier 3；reactive tier 1、tier 2、tier 3；reactive multi-pass；run cancellation；execution identity mismatch；cursor mismatch；stale recovery proposal；accepted compact commit；fallback dispatch / fail-closed ordering。
- 验证 accepted compact output 仍只生成五类 Session Semantic Memory，并且 fallback / diagnostic / Host governance state / Engine state 不投影为业务事实。
- 受影响 Host dispatch / Engine ingest / compact / RunInput / memory projection tests 通过；`python -m pyright dayu/ tests/ utils/` 通过且不新增类型错误。
- `utils/smoke_host_public_conversation_memory_scenarios.py` 必须真实运行成功，作为 WU-CM-13 final acceptance 的硬门槛；不得通过修改该 smoke、降低覆盖、绕过场景、放宽断言或改成无效通过来满足验收。

### Current gate artifacts

- plan: `docs/host/host-issues/wu-cm-13-unified-compact-pipeline-plan.md`
- plan review: `docs/reviews/plan-review-20260619-194515.md`
- plan review: `docs/reviews/plan-review-20260619-194657.md`
- focused plan re-review: `docs/reviews/plan-review-20260619-195507.md`
- focused plan re-review: `docs/reviews/plan-review-20260619-195521.md`
- final focused plan re-review: `docs/reviews/plan-review-20260619-200133.md`
- final focused plan re-review: `docs/reviews/plan-review-20260619-200143.md`
- plan adjudication: `docs/reviews/plan-review-wu-cm-13-adjudication-20260619.md`
- accepted scope: thin `compact_pipeline.py` helper owner; no tier 5 current-input-only fallback implementation; lifecycle guards remain caller-owned; WU-CM-14 uses pipeline-owned audited second-read raw-tail selection; `compaction_evidence.py` must be removed or fully migrated.
- Slice 1 implementation: `dayu/host/compact_pipeline.py` helper contracts, `tests/host/test_compact_pipeline.py`, `compaction_evidence.py` deletion, migrated compact material / operation tests, and `tests/README.md` update.
- Slice 1 code review: `docs/reviews/deepreview-20260619-211229.md`; `docs/reviews/deepreview-wu-cm-13-slice-1-20260619-211311.md`.
- Slice 1 code review adjudication: `docs/reviews/code-review-wu-cm-13-slice-1-adjudication-20260619.md`.
- Slice 1 validation: `pytest tests/host/test_compact_pipeline.py tests/host/test_compact_material.py tests/host/test_compaction_operation.py -q` PASS (`91 passed`); `python -m pyright dayu/ tests/ utils/` PASS (`0 errors`); `git diff --check` PASS; old `compaction_evidence` helper symbols absent from `dayu` and `tests`.
- accepted Slice 1 commit: `0390c9ad`.
- Slice 1 residual reconciliation: `WU-CM-12-PR-R1` closed by deleting `dayu/host/compaction_evidence.py` and migrating useful tests to `compact_material.py` / `compact_pipeline.py`; `WU-CM-13-S1-R1` and `WU-CM-13-S1-R2` deferred to Slice 2.
- Slice 2a implementation: proactive `dispatch.py` normal request uses `build_normal_compact_request_plan(...)`; proactive tier 1-3 recovery uses `build_tier_recovery_request_plans(...)`; proactive fallback failed payload / decision input uses `build_fallback_decision_input(...)`; dispatch-owned lifecycle and EventLog writes remain in `dispatch.py`.
- Slice 2a code review: `docs/reviews/deepreview-20260619-212804.md`; `docs/reviews/deepreview-wu-cm-13-slice-2a-20260619-212944.md`.
- Slice 2a code review adjudication: `docs/reviews/code-review-wu-cm-13-slice-2a-adjudication-20260619.md`.
- Slice 2a validation: `pytest tests/host/test_dispatch_scheduler.py tests/host/test_compact_pipeline.py -q` PASS (`88 passed`); `python -m pyright dayu/ tests/ utils/` PASS (`0 errors`); `git diff --check` PASS; old proactive fallback helper / tier 5 / `fallback_tier` symbols absent from `dayu/host/dispatch.py`.
- accepted Slice 2a commit: `b180a510`.
- Slice 2a residual reconciliation: `WU-CM-13-S1-R2` is closed for proactive dispatch; the reactive ingest half remains tracked by the same residual until Slice 2b.
- Slice 2b implementation: reactive `engine_ingest.py` request construction uses `build_normal_compact_request_plan(...)`; reactive pass queue uses `build_reactive_pass_queue_plan(...)`; reactive fallback failed payload / decision input uses `build_fallback_decision_input(...)`; reactive lifecycle, cancellation, EventLog writes, and recovery Attempt creation remain in `engine_ingest.py`.
- Slice 2b code review: `docs/reviews/deepreview-20260619-214447.md`; `docs/reviews/deepreview-wu-cm-13-slice-2b-20260619-214451.md`.
- Slice 2b code review adjudication: `docs/reviews/code-review-wu-cm-13-slice-2b-adjudication-20260619.md`.
- Slice 2b validation: `pytest tests/host/test_dispatch_scheduler.py tests/host/test_compact_pipeline.py -q` PASS (`88 passed`); `python -m pyright dayu/ tests/ utils/` PASS (`0 errors`); `git diff --check` PASS; old reactive request / pass queue / fallback helper / tier 5 / `fallback_tier` symbols absent from `dayu/host/engine_ingest.py`.
- accepted Slice 2b commit: `7b0367ab`.
- Slice 2b residual reconciliation: `WU-CM-13-S1-R2` closed by removing proactive and reactive duplicate helper owners from `dispatch.py` / `engine_ingest.py`.
- Slice 2c implementation: `run_input.py` ordinary post-compaction protected raw-tail provider now consumes `CompactPipelineProtectedRawTailProvider`, returns `CompactPipelineOrdinaryRawTailHandoff`, and delegates protected recent group selection / memory dedup to `select_ordinary_protected_raw_tail(...)`; fallback RunInput assembly remains on `_fallback_context_messages(...)`.
- Slice 2c code review: `docs/reviews/deepreview-20260619-220450.md`; `docs/reviews/deepreview-wu-cm-13-slice-2c-20260619-220501.md`.
- Slice 2c code review adjudication: `docs/reviews/code-review-wu-cm-13-slice-2c-adjudication-20260619.md`.
- Slice 2c validation: `pytest tests/host/test_run_input_builder.py tests/host/test_compact_pipeline.py -q` PASS (`107 passed`); `python -m pyright dayu/ tests/ utils/` PASS (`0 errors`); `git diff --check` PASS; required search confirms `compact_pipeline.py` owns ordinary protected raw-tail selection and `run_input.py` retains `protected_recent_turn_group_ids_for_material_blocks` only for the explicit fallback branch non-goal.
- Slice 2c residual reconciliation: `WU-CM-14-RR-1` closed because WU-CM-14 preservation is now audited through shared proactive/reactive compact pipeline helpers plus pipeline-owned ordinary raw-tail selection; `WU-CM-14-RR-3` closed because the second EventLog read remains a durable freshness adapter, while selection semantics are shared in `compact_pipeline.py`. `WU-CM-13-S1-R1` remains deferred to aggregate deepreview / final smoke for whole-WU accepted compact quality/provenance audit.
- accepted Slice 2c commit: `7aab0f94`.
- aggregate deepreview: `docs/reviews/deepreview-wu-cm-13-aggregate-mimo-20260619.md`; `docs/reviews/deepreview-wu-cm-13-aggregate-ds-20260619.md`.
- aggregate deepreview adjudication: `docs/reviews/deepreview-wu-cm-13-aggregate-adjudication-20260619.md`.
- aggregate validation: `pytest tests/host/test_compact_pipeline.py tests/host/test_compact_material.py tests/host/test_compaction_operation.py tests/host/test_dispatch_scheduler.py tests/host/test_run_input_builder.py tests/host/test_memory_projection.py -q` PASS (`305 passed`); `python -m pyright dayu/ tests/ utils/` PASS (`0 errors, 0 warnings, 0 informations`); `python utils/smoke_host_public_conversation_memory_scenarios.py --suite memory-compact --pressure-mode auto` PASS (`SMOKE COMPACT_ACCEPTANCE status=pass requested_proactive=4 compacted_proactive=4 failed_total=0 artifact_files=12`); `git diff --check` PASS.
- aggregate residual reconciliation: `WU-CM-12-S4-R1` closed by accepted proactive/reactive shared compact pipeline convergence; `WU-CM-13-S1-R1` closed because the old malformed compacted payload fact-ref edge is closed by the typed `ConversationCompactOutputVNext` helper boundary plus operation-level candidate rejection coverage and compact payload/material provenance tests.
- accepted deepreview commit: `00da03a3`.
- PR preflight: `gh pr status` confirmed current branch has no associated PR; `gh pr view 150 --json ...` confirmed PR #150 is merged and came from `wu-cm-12-conversation-memory-drift`, not current branch.
- draft PR: #152 https://github.com/noho/dayu-agent-r/pull/152 (`wu-cm-14-final-answer-preservation` -> `main`, draft).
- PR review: `docs/reviews/pr-152-review-mimo-20260619.md`; `docs/reviews/pr-152-review-ds-20260619.md`.
- PR review adjudication: `docs/reviews/pr-152-review-adjudication-20260619.md`.
- PR review conclusion: PASS; no fix gate required. DS low finding about duplicated internal evidence source prefix constants is rejected because ordinary/fallback rendering path separation is intentional and extracting a shared owner now would add unnecessary coupling.
- accepted PR review commit: `f2970512`, pushed to #152.
- final closeout: `docs/reviews/wu-cm-13-final-closeout-20260619.md`.
- current gate: draft-PR-pass. PR #152 remains draft; mark-ready, reviewer requests, merge, branch deletion, and issue closure require separate user authorization.
- 若引入任何新的 LLM-facing memory material / compact material 产量常量，必须在 `dayu/config/execution_profiles.json` 的 `memory_projection_policy` 或本 WU 明确批准的 policy owner 中定义；否则 final closeout 的常量审计必须列为 open residual。

## WU-CM-14 Recent Final Answer Preservation for Ordinal Follow-ups

### 状态

`discussion-ready`。当前不创建 GitHub Issue，不进入 plan / implementation。本 WU 是 CM 语义讨论中新增的独立追踪项，承接 residual `WU-CM-14-R1`。

本 WU 不修改 `WU-CM-13` 的范围。`WU-CM-13` 只统一 proactive / reactive compact pipeline；本 WU 专注 compact 后 ordinary RunInput 是否仍具备回答局部序号追问所需的最近 assistant final answer 上下文。

两者存在实现约束关联：`WU-CM-14` 的 preservation 语义一旦被裁决为需要进入 compact material、compact accept quality gate、fallback material 或 ordinary RunInput assembly，就必须落在 proactive / reactive 共享的代码路径上，不得分别实现主动触发 compact 与被动触发 compact 的两套 preservation 逻辑。

### 场景

第 N 轮 assistant final answer 列出 4 条详细内容。第 N+1 轮用户输入“详细解释第三条”，并且本轮 dispatch 前触发 compact。

需求裁决：compact 后第 N+1 轮送给 Engine 的 messages 不能只等价于 `latest_accepted_compacted_view + current user prompt`。Host 必须在 compact boundary 后继续保留既有 protected recent raw tail；该 tail 复用现有 `selected_recent_window_turn_floor` / protected recent floor 语义，不新增 WU-CM-14 专属 floor、ordinal follow-up floor 或 prompt-pattern-specific cap。

protected recent raw tail 的基本单位仍是 turn group。最近 `selected_recent_window_turn_floor` 个 turn group 中已 committed、eligible、LLM-readable 的 material 应按 whole block / whole section keep-drop 进入 ordinary RunInput / fallback RunInput，至少覆盖历史 user prompt、assistant final answer、accepted readable tool evidence 与用户可见 Run outcome material。裸 tool request 不应单独作为 evidence；若 tool interaction 需要保留，必须通过 accepted readable evidence 或成对且自解释的 material 表达，不暴露 tool_call_id、digest、EventLog id、payload ref 或 Host 内部治理状态。

### 初步代码核对结论

- Answer Anchor Memory 已有实现路径：accepted compact output 中的 `answer_anchors` 会被 Conversation Memory projection 物化，并由 RunInputBuilder 渲染为 `## Prior Answer Anchors`。
- Answer Anchor Memory 的语义是“可被后续指代的历史回答轮廓”，不是原回答全文，也不是事实证明。
- selected recent window 按设计可以承载 post-compact delta material 中的 raw user input、assistant final answer、accepted tool evidence 和用户可见 outcome material。
- 一旦第 N 轮 final answer 被 compact 覆盖，而 accepted compact output 只保留短 answer anchor，第 N+1 轮 Engine 可能只能解析“第三条指什么”，但缺少“详细解释第三条”所需的完整文本和列表上下文。

### 设计裁决与剩余讨论点

- Answer Anchor Memory 负责指代解析，不负责承载完整展开所需的原回答上下文；recent raw tail 负责最近回答、工具证据和 outcome 的原始业务语义连续性。
- WU-CM-14 不新增 memory kind、不新增 floor、不实现 ordinal parser；preservation 复用 `selected_recent_window_turn_floor` / protected recent floor。
- compact accepted 后，`latest_accepted_compacted_view` 只代表 compact 覆盖范围内的旧历史语义视图；它不得吞掉仍处于 protected recent floor 内的 raw tail。
- preservation owner 初步归属于 selected recent window / protected recent floor 与 ordinary RunInput / fallback RunInput assembly 的共享 material selection 语义；plan gate 仍需用代码证据确认当前 owner 位置和最小改动点。
- preservation owner 如何复用 proactive / reactive shared compact pipeline，确保同一段 history、同一个 current input anchor 和同一项 accepted compact candidate 在两种触发方式下得到同义的 preservation / fallback / RunInput assembly 结果。
- 若第 N 轮 final answer 本身超预算，应采用 whole-item keep-drop、chunking with provenance、section-aware degrade 还是 fail closed；不得 silent truncation、preview 化或 summary 化后伪装为完整回答。
- 是否需要在 `docs/host/design.md` 增补 Answer Anchor Memory 与 recent raw final answer preservation 的边界说明。

### 非目标

- 不并入 `WU-CM-13`；不借本 WU 重新设计 proactive / reactive compact pipeline unification。
- 不允许为 proactive compact 与 reactive compact 分别实现语义不同的 recent final answer preservation 分支；触发方式不同不应改变 preservation 结果。
- 不新增 WU-CM-14 专属 protected floor、ordinal follow-up floor、recent answer cap 或另一套 selected recent window policy；复用 `selected_recent_window_turn_floor` / protected recent floor。
- 不引入 semantic search、vector recall、prompt-conditioned reranker 或长期 memory retrieval framework。
- 不实现 deterministic final answer outline parser 或“第三条”prompt-pattern parser。
- 不把 Answer Anchor Memory 升级成事实证明、完整回答存储或替代 raw final answer 的通用机制。
- 不通过字段级截断、固定 preview、私有 DTO cap 或 summary 化来保留超长 final answer。

### Entry Conditions

- 重新核对 `docs/host/design.md` 中 latest accepted compacted view、post-compact delta material、selected recent window、protected recent floor、Answer Anchor Memory、Reference Continuity 和 Prompt Assembly 的设计真源。
- 重新核对 RunInputBuilder、Conversation Memory projection、compact material selection 与相关测试，确认第 N+1 轮触发 compact 后 ordinary Engine messages 的实际组成。
- plan gate 先验证当前 `selected_recent_window_turn_floor` / protected recent floor 是否已经跨 compact boundary 生效；若未生效，plan 必须定位 root cause 并提出最小修复，不新增平行 policy owner。

### Acceptance Signals

- 文档明确裁决 ordinal follow-up 场景下，recent assistant final answer 与 Answer Anchor Memory 的职责边界。
- 文档和实现明确复用 `selected_recent_window_turn_floor` / protected recent floor；不得新增 WU-CM-14 专属 floor 或 prompt-pattern-specific retention rule。
- 文档明确裁决 WU-CM-14 preservation 逻辑与 WU-CM-13 shared compact pipeline 的关系：策略可以独立讨论，但实现必须避免 proactive / reactive 语义漂移。
- 测试必须覆盖：第 N 轮 final answer 列 4 条详细文本，第 N+1 轮“详细解释第三条”触发 compact，最终 Engine messages 除 accepted compacted view / memory sections 与 current user prompt 外，还包含 protected recent raw tail 中足以解释第三条的完整业务上下文。
- 测试必须覆盖 protected recent raw tail 的 eligible material 边界：history user prompt、assistant final answer、accepted readable tool evidence、user-visible outcome material；裸 tool request、Host internal refs / digest / EventLog id 不进入 LLM-facing tail。
- 测试还必须覆盖 proactive 与 reactive compact 触发下的同义 preservation 结果，除非 plan gate 明确证明某一路径不会经过该 preservation owner。
- 受影响 Host memory / compact / RunInput tests 通过；若发生代码修改，`python -m pyright dayu/ tests/ utils/` 通过且不新增类型错误。

### Current gate artifacts

- plan: `docs/host/host-issues/wu-cm-14-protected-recent-floor-plan.md`
- plan review: `docs/reviews/plan-review-wu-cm-14-mimo.md`
- plan review: `docs/reviews/plan-review-wu-cm-14-ds.md`
- plan adjudication: `docs/reviews/plan-review-wu-cm-14-adjudication-20260619.md`
- plan re-review: `docs/reviews/plan-rereview-wu-cm-14-mimo.md`
- plan re-review: `docs/reviews/plan-rereview-wu-cm-14-ds.md`
- plan re-review conclusion: AgentCodex fixed the plan; AgentMiMo PASS and AgentDS PASS. Accepted findings are closed: provider / transaction contract, activation condition, reactive compact-success and fallback regression coverage, duplicate prevention, allowed test boundary cleanup, and reactive frozen material stop condition. Plan is code-generation-ready.
- plan gate validation: `git diff --check` clean
- accepted plan commit: `d4b271cb`
- implementation review: `docs/reviews/code-review-20260619-190815.md`
- implementation review: `docs/reviews/code-review-20260619-191152.md`
- implementation focused re-review: `docs/reviews/code-review-20260619-192312.md`
- implementation focused re-review: `docs/reviews/code-review-20260619-192408.md`
- code review adjudication: `docs/reviews/code-review-wu-cm-14-adjudication-20260619.md`
- implementation validation: `pytest tests/host/test_run_input_builder.py tests/host/test_compact_material.py tests/host/test_dispatch_scheduler.py -q` passed 220 tests; `python -m pyright dayu/ tests/ utils/` passed 0 errors; `git diff --check` clean.
- accepted slice commit: `921c6219`
- aggregate deepreview: `docs/reviews/code-review-20260619-192740.md`
- aggregate deepreview: `docs/reviews/code-review-20260619-193018.md`
- aggregate focused re-review: `docs/reviews/code-review-20260619-193352.md`
- aggregate focused re-review: `docs/reviews/code-review-20260619-193419.md`
- aggregate adjudication: `docs/reviews/wu-cm-14-aggregate-deepreview-adjudication-20260619.md`
- aggregate validation: `rg -n "_current_only_material_blocks" dayu tests` returned no matches; `pytest tests/host/test_run_input_builder.py tests/host/test_compact_material.py tests/host/test_dispatch_scheduler.py -q` passed 220 tests; `python -m pyright dayu/ tests/ utils/` passed 0 errors; `git diff --check` clean.
- next gate: WU-CM-13 goal confirmation / plan gate

### Residual risks

- `WU-CM-14-RR-1` closed by WU-CM-13 Slice 2c: WU-CM-14 preservation is now audited through shared proactive/reactive compact pipeline helpers plus pipeline-owned ordinary raw-tail selection.
- `WU-CM-14-RR-3` closed by WU-CM-13 Slice 2c: the second EventLog read remains a durable freshness adapter, while protected recent group eligibility and memory dedup semantics are shared in `compact_pipeline.py`.

## WU-CM-15 Conversation Memory Public Smoke Reactive Compact And Fallback Coverage

### 状态

`draft-PR-pass`。当前不创建 GitHub Issue。Goal confirmation 已由用户裁决通过：本 WU 只是增加 public smoke 覆盖，覆盖被动 compact 和 fallback。Accepted plan commit `97518e93` 已创建；accepted implementation slice commit `572a88df` 已创建；aggregate deepreview / fix / focused re-review 已通过；closeout logging / pressure observability fix 已验证；draft PR #157 已创建；PR review PASS；final closeout 已完成。PR #157 仍为 open draft，merge / mark-ready / reviewer request / branch deletion 需要用户另行授权。

本 WU 是对 `utils/smoke_host_public_conversation_memory_scenarios.py` fresh run 后发现的 smoke coverage gap 的独立追踪项。当前 `memory-compact` suite 已覆盖真实 conversation memory 主干与 proactive compact accepted 路径，但没有显式覆盖 worker / provider overflow 触发的 reactive compact，也没有显式覆盖 compact 全部失败后的 deterministic fallback dispatch。

### 动机判断

问题真实存在，但严重性应按“smoke coverage gap”而不是“生产代码已知 bug”处理：

- fresh `memory-compact` run 通过，且观察到 `requested_proactive=4`、`compacted_proactive=4`、`failed_total=0`。
- 同一次 run 的 reactive 计数为 0，说明当前 public conversation memory smoke 没有 exercised reactive compact 主路径。
- 当前 `memory-compact` 验收把任何 `CONTEXT_COMPACTION_FAILED` 视为 hard fail，因此不能直接把 fallback 成功场景塞进同一 suite。
- 生产代码和 focused tests 已存在 reactive compact / fallback 相关覆盖，但 `utils/` public conversation memory smoke 尚未把这些路径作为一等 smoke target。

### 初步设计裁决

WU-CM-15 应新增显式 suite，而不是改变现有 `memory-compact` 的语义：

- 保持现有 `memory-compact`：继续作为 proactive compact accepted 与长会话 conversation memory 主干 smoke；不得为了 fallback 放宽 `failed_total == 0` 断言。
- 新增 reactive compact smoke suite：使用 public Host 路径，通过 deterministic worker 或等价测试 runner 在第一次 Attempt 返回 `context_compaction_requested`，模拟 provider overflow；Host 完成 reactive compact 后启动 recovery Attempt 并最终 succeeded。
- 新增 fallback smoke suite：通过 deterministic bad compactor / rejecting compactor / missing compactor 等可控方式让 compact operation 失败，触发 dispatch fallback；fallback succeeded 是该 suite 的目标行为，不得被现有 proactive acceptance 规则误判为失败。
- 不依赖真实 provider / 真实上下文窗口自然触发 reactive compact 或 fallback。真实 LLM smoke 可以保留为 `memory-compact`，reactive / fallback smoke 应优先 deterministic，避免不稳定、耗时和成本扩散。

### 目标

- `utils/smoke_host_public_conversation_memory_scenarios.py` 或相邻 public smoke 入口能够显式运行 reactive compact path。
- 同一 smoke 体系能够显式运行 deterministic fallback dispatch path。
- smoke log 能展示 reactive / fallback 的关键诊断信号，支持问题定位且不引入 per-delta stream 噪音。
- 现有 `memory-compact` suite 的 proactive compact accepted 验收保持不变。

### 非目标

- 不把 fallback 成功视为 `memory-compact` proactive acceptance 的通过条件。
- 不通过修改 smoke oracle、降低断言、跳过 compact audit 或允许 malformed compact output 来制造通过。
- 不新增 production-only hook、私有捷径或绕过 Host public path 的 smoke 实现。
- 不依赖真实 LLM / 真实 provider overflow 随机触发 reactive compact。
- 不改变 Host / Engine compact contract、EventLog canonical semantics、durable schema 或 Context Governance 状态机。
- 不把 #80 Conversation Memory benchmark 一次性并入本 WU；本 WU 只是补 public smoke 对 reactive / fallback 主路径的覆盖。

### Entry Conditions

- 重新核对 `docs/host/design.md` 中 Context Governance、reactive compact、fallback tier、Prompt Assembly 与 Conversation Memory 的设计真源。
- 核对 `docs/engine/design.md` 中 Engine 只上报 context compaction request、Host 负责 compact / recovery / fallback 的边界。
- 核对现有 `utils/smoke_host_public_conversation_memory_scenarios.py` 的 suite / pressure mode / compact audit / acceptance 结构。
- 核对 `tests/host/test_public_compact_smoke.py`、`tests/host/test_dispatch_scheduler.py` 与 `tests/host/test_run_input_builder.py` 中 reactive compact、fallback dispatch、fallback input rendering 的既有覆盖，避免重复发明测试机制。

### Acceptance Signals

- 现有 `memory-compact` suite 仍要求 proactive compact request / accepted compact / artifact files，且任何 compact failed 仍为 hard fail。
- 新增 reactive suite 至少断言：
  - `requested_reactive >= 1`。
  - `compacted_reactive >= 1`。
  - `failed_reactive == 0`。
  - recovery Attempt 被创建并最终 terminal succeeded。
  - recovery RunInput 保持 one-system-message contract、current input anchor 与 protected recent floor 语义。
- 新增 fallback suite 至少断言：
  - 观察到 `CONTEXT_COMPACTION_FAILED`。
  - failed payload 包含 `fallback_action=dispatch` 与可诊断的 fallback input window。
  - 不写 accepted `CONTEXT_COMPACTED`。
  - fallback dispatch 最终 terminal succeeded。
  - fallback RunInput 只渲染 selected recent window 与 current input，不生成或伪造五类 Session Semantic Memory。
- smoke stdout 必须打印 compact audit / operation / fallback 关键信号，但不得输出完整 pressure blob、per-delta stream log 或 Host internal refs 到 LLM-facing material。
- 受影响 smoke assembly tests / Host public compact tests / RunInput fallback tests 通过；若发生代码修改，`python -m pyright dayu/ tests/ utils/` 通过且不新增类型错误。

### 与 WU-CM-10 / GitHub Issue #80 的关系

WU-CM-15 是 public smoke coverage hardening，不替代 #80 的完整 Conversation Memory eval benchmark。它可以为 #80 提供稳定 public-path baseline：reactive compact、fallback dispatch、compact audit 与 final outcome 行为可作为后续 eval fixtures 的底层能力，但 #80 仍需单独覆盖 memory snapshot、RunInputBuilder messages、tool behavior、diagnostics、final response facts、事实更新 / 冲突和 provenance 指标。

### Implementation / Review 状态

- accepted plan: `docs/host/host-issues/wu-cm-15-public-smoke-reactive-fallback-plan.md`; accepted plan commit `97518e93`.
- initial plan review: `docs/reviews/plan-review-20260620-102108.md` (AgentMiMo); `docs/reviews/plan-review-20260620-102145.md` (AgentDS).
- plan review adjudication: `docs/reviews/wu-cm-15-plan-review-adjudication-20260620.md`.
- plan fix: `docs/reviews/wu-cm-15-plan-fix-codex-20260620.md`.
- focused plan re-review: `docs/reviews/plan-review-20260620-102923.md` (AgentMiMo); `docs/reviews/plan-review-20260620-102930.md` (AgentDS).
- implementation artifact: `docs/reviews/wu-cm-15-implementation-codex-20260620.md`.
- code review: `docs/reviews/code-review-20260620-112127.md` (AgentDS); `docs/reviews/code-review-20260620-112301.md` (AgentMiMo).
- code review adjudication: `docs/reviews/wu-cm-15-code-review-adjudication-20260620.md`.
- fix artifact: `docs/reviews/wu-cm-15-code-review-fix-codex-20260620.md`.
- focused re-review: `docs/reviews/code-review-20260620-115326.md` (AgentMiMo); `docs/reviews/code-review-rereview-ds-20260620.md` (AgentDS).
- focused re-review adjudication: `docs/reviews/wu-cm-15-code-review-rereview-adjudication-20260620.md`.
- accepted implementation slice commit: `572a88df`.
- aggregate deepreview: `docs/reviews/deepreview-wu-cm-15-aggregate-mimo-20260620.md` (AgentMiMo); `docs/reviews/deepreview-wu-cm-15-aggregate-ds-20260620.md` (AgentDS).
- aggregate fix: `docs/reviews/wu-cm-15-aggregate-fix-codex-20260620.md`.
- aggregate fix focused re-review: `docs/reviews/deepreview-wu-cm-15-aggregate-fix-rereview-mimo-20260620.md` (AgentMiMo); `docs/reviews/deepreview-wu-cm-15-aggregate-fix-rereview-ds-20260620.md` (AgentDS).
- aggregate adjudication: `docs/reviews/wu-cm-15-aggregate-deepreview-adjudication-20260620.md`.
- final closeout: `docs/reviews/wu-cm-15-final-closeout-20260620.md`.
- draft PR: https://github.com/noho/dayu-agent-r/pull/157.
- PR review artifacts: `docs/reviews/pr-157-review-20260620-134300.md` (AgentMiMo, PASS, no material findings); `docs/reviews/pr-157-review-20260620-134346.md` (AgentDS, PASS, no material findings).
- accepted PR review / final closeout commit: `5e04a841`.
- follow-up push: branch `phase/wu-cm-15` is pushed to PR #157 through accepted PR review commit `5e04a841` and this final hash-record update.
- Controller validation after fix: `pytest tests/runtime/test_smoke_host_public_conversation_memory_scenarios_assembly.py -q` passed (`20 passed`, existing edgar deprecation warnings); `DEEPSEEK_API_KEY=test-provider-key python utils/smoke_host_public_conversation_memory_scenarios.py --suite memory-reactive-compact --log-level CRITICAL` passed; `DEEPSEEK_API_KEY=test-provider-key python utils/smoke_host_public_conversation_memory_scenarios.py --suite memory-compact-fallback --pressure-mode auto --log-level CRITICAL` passed; `python -m pyright dayu/ tests/ utils/` passed (`0 errors`); `git diff --check` clean.
- Controller validation after aggregate fix: `pytest tests/runtime/test_smoke_host_public_conversation_memory_scenarios_assembly.py -q` passed (`20 passed`, existing edgar deprecation warnings); `DEEPSEEK_API_KEY=test-provider-key python utils/smoke_host_public_conversation_memory_scenarios.py --suite memory-reactive-compact --log-level CRITICAL` passed; `DEEPSEEK_API_KEY=test-provider-key python utils/smoke_host_public_conversation_memory_scenarios.py --suite memory-compact-fallback --pressure-mode auto --log-level CRITICAL` passed; `python -m pyright dayu/ tests/ utils/` passed (`0 errors`); `git diff --check` clean.
- Fresh full-suite smoke evaluation: `workspace/tmp/cm-smoke-fresh-20260620-125037` contains DEBUG logs for all four suites. `memory-core`, `memory-compact`, `memory-reactive-compact`, and `memory-compact-fallback` all passed after correcting the local rerun harness argument shape for the two `--pressure-mode auto` invocations. The logs are appropriate for diagnosis; high-volume per-delta stream output is assigned to GitHub Issue #148 / WU-CLI-DEBUG-STREAM-01 and is not counted as WU-CM-15 noise.
- Closeout logging / pressure fix validation: `pytest tests/host/test_compaction_operation.py::test_run_compaction_operation_logs_terminal_reject_as_warning tests/runtime/test_smoke_host_public_conversation_memory_scenarios_assembly.py::test_pressure_off_and_padding_helper_cover_runtime_pressure_bounds` passed (`2 passed`); `pytest tests/host/test_compaction_operation.py` passed (`31 passed`); `pytest tests/runtime/test_smoke_host_public_conversation_memory_scenarios_assembly.py` passed (`20 passed`); `pyright` passed (`0 errors`); `python utils/smoke_host_public_conversation_memory_scenarios.py --suite memory-compact-fallback --pressure-mode auto --log-level DEBUG > workspace/tmp/cm-smoke-fallback-log-fix-20260620-131005.log 2>&1` passed and emitted no `[ERROR]` lines.
- PR checks: `gh pr checks 157` reported no checks on branch `phase/wu-cm-15`; `statusCheckRollup` is empty. Local validation above is the recorded verification source for this WU.
- README trigger handled: `tests/README.md` updated only to reflect the added `memory-reactive-compact` / `memory-compact-fallback` assembly coverage and oracles.

### Residual risks

- Existing real-provider `memory-compact` smoke keeps strict proactive accepted compact semantics. The latest full four-suite run passed with the configured provider environment; future real-provider runs still require valid model / compactor provider keys as a normal smoke precondition.
- `_patched_compactor_runner` remains a smoke-local monkey patch around `dayu.host.llm_compaction._run_agent_request`; the fix adds fail-fast identity checking and `finally` restore, but future parallel smoke execution would need a different isolation strategy.
- The reactive suite uses a suite-local copied `MemoryProjectionPolicy` to bound selected recent items so that the old seed marker is truly written into r1 history but excluded from recovery dispatch; if the default selected recent turn floor grows beyond the six-round layout, the smoke fails closed instead of silently weakening the oracle.
- Deferred future smoke hardening: decide whether reactive acceptance should also reject nonzero `rejected_proactive`. Current aggregate-fix finding explicitly required requested / compacted / failed proactive zero checks; both focused re-reviews passed. If future config can emit proactive rejection without request/compacted/failed counts, add this as a small smoke hardening follow-up.
- Compaction artifact retention is tracked by GitHub Issue #156 as a child of #78. The relationship is explicit: #78 owns `purge_session`-driven session retention cleanup, and #156 can safely rely on that purge ownership to define artifact retention cleanup without adding a Host background scheduler.

Residual risk reconciliation:

- PR review found no material findings; no fix / re-review gate was required.
- `_patched_compactor_runner` risk is accepted as smoke-local and fail-closed; owner is future smoke maintenance only if parallel suite execution becomes a requirement.
- Provider key dependency is an operator/environment precondition for real-provider smoke, not a WU-CM-15 code residual.
- Per-delta DEBUG log volume is transferred to WU-CLI-DEBUG-STREAM-01 / GitHub Issue #148.
- Compaction artifact retention is transferred to GitHub Issue #156 under #78.
- Next entry point after user merges PR #157: pull latest `main` and start WU-CLI-DEBUG-STREAM-01.

## WU-CLI-DEBUG-STREAM-01 CLI `--debug-stream` Per-Delta Stream Diagnostics

### 状态

`planning`。Owner / destination is GitHub Issue #148: https://github.com/noho/dayu-agent-r/issues/148.

本 WU 是 WU-CM-12 final closeout 后新增的 issue-backed follow-up。Goal-confirmation、plan gate、plan review adjudication、plan fix、plan re-review、accepted plan commit 与 Slice 1 implementation 已完成；当前进入 Slice 1 code review gate。

Current gate artifacts:

- plan: `docs/host/host-issues/wu-cli-debug-stream-01-debug-stream-plan.md`
- plan review: `docs/reviews/plan-review-wu-cli-debug-stream-01-mimo-20260620.md` (AgentMiMo); `docs/reviews/plan-review-wu-cli-debug-stream-01-ds-20260620.md` (AgentDS)
- plan review adjudication: `docs/reviews/plan-review-wu-cli-debug-stream-01-adjudication-20260620.md`
- plan fix: `docs/reviews/plan-fix-wu-cli-debug-stream-01-20260620.md`
- plan re-review: `docs/reviews/plan-rereview-wu-cli-debug-stream-01-mimo-20260620.md` (AgentMiMo PASS); `docs/reviews/plan-rereview-wu-cli-debug-stream-01-ds-20260620.md` (AgentDS PASS)
- accepted plan commit: `61bc9a9d`
- Slice 1 implementation: `docs/reviews/implementation-wu-cli-debug-stream-01-slice1-20260620.md`
- Slice 1 validation: `pytest tests/runtime/test_log.py tests/runtime/test_log_levels.py tests/cli/test_arg_parsing.py -q` passed with 88 passed and 3 existing dependency warnings; `python -m pyright dayu/ tests/ utils/` passed with 0 errors; `git diff --check` clean.
- Slice 1 code review: `docs/reviews/code-review-wu-cli-debug-stream-01-slice1-mimo-20260620.md` (AgentMiMo APPROVED with deferred nits); `docs/reviews/code-review-wu-cli-debug-stream-01-slice1-ds-20260620.md` (AgentDS findings)
- Slice 1 code review adjudication: `docs/reviews/code-review-wu-cli-debug-stream-01-slice1-adjudication-20260620.md`
- Slice 1 fix: `docs/reviews/fix-wu-cli-debug-stream-01-slice1-20260620.md`
- Slice 1 fix validation: `pytest tests/runtime/test_log.py tests/runtime/test_log_levels.py tests/cli/test_arg_parsing.py -q` passed with 90 passed and 3 existing dependency warnings; `python -m pyright dayu/ tests/ utils/` passed with 0 errors; `git diff --check` clean.
- Slice 1 re-review: `docs/reviews/code-rereview-wu-cli-debug-stream-01-slice1-mimo-20260620.md` (AgentMiMo PASS); `docs/reviews/code-rereview-wu-cli-debug-stream-01-slice1-ds-20260620.md` (AgentDS PASS)
- accepted Slice 1 commit: `f53762a5`
- Slice 2 implementation: `docs/reviews/implementation-wu-cli-debug-stream-01-slice2-20260620.md`
- Slice 2 validation: `pytest tests/host/test_logging.py tests/engine/runners/openai/test_runner_diagnostics.py -q` passed with 13 passed; `python -m pyright dayu/ tests/ utils/` passed with 0 errors; `git diff --check` clean.
- Slice 2 code review: `docs/reviews/code-review-wu-cli-debug-stream-01-slice2-mimo-20260620.md` (AgentMiMo findings); `docs/reviews/code-review-wu-cli-debug-stream-01-slice2-ds-20260620.md` (AgentDS PASS with info findings)
- Slice 2 code review adjudication: `docs/reviews/code-review-wu-cli-debug-stream-01-slice2-adjudication-20260620.md`
- Slice 2 fix: `docs/reviews/fix-wu-cli-debug-stream-01-slice2-20260620.md`
- Slice 2 fix validation: `pytest tests/host/test_logging.py tests/engine/runners/openai/test_runner_diagnostics.py -q` passed with 13 passed; `python -m pyright dayu/ tests/ utils/` passed with 0 errors; `git diff --check` clean; diff scan confirms no newly added `type: ignore`, `Any`, or `object` in changed Slice 2 code/test lines.
- Slice 2 re-review: `docs/reviews/code-rereview-wu-cli-debug-stream-01-slice2-mimo-20260620.md` (AgentMiMo PASS); `docs/reviews/code-rereview-wu-cli-debug-stream-01-slice2-ds-20260620.md` (AgentDS PASS)
- Slice 2 re-review adjudication: `docs/reviews/code-rereview-wu-cli-debug-stream-01-slice2-adjudication-20260620.md`
- accepted Slice 2 commit: `67ca96fb`
- plan gate validation: `git diff --check` clean; untracked plan artifact whitespace check clean via `git diff --no-index --check /dev/null docs/host/host-issues/wu-cli-debug-stream-01-debug-stream-plan.md` with expected nonzero no-index exit and no whitespace output.
- plan fix validation: `git diff --check` clean; untracked fix artifact whitespace check clean via `git diff --no-index --check /dev/null docs/reviews/plan-fix-wu-cli-debug-stream-01-20260620.md` with expected nonzero no-index exit and no whitespace output.

### Issue Scope

Issue #148 要求把普通 `--debug` 与高噪音 stream delta diagnostics 分离：

- `--debug` 保持常规诊断级别，不输出大量 per `reasoning_delta` / `content_delta` ingest 日志。
- 新增显式 `--debug-stream`，仅在该开关启用时输出 stream delta / SSE / per-delta accepted / committed diagnostics。
- `--debug-stream` 可与 `--debug` 组合；具体日志级别和 handler owner 必须在 plan gate 核对当前 CLI / runtime log 装配后确定。
- `--help`、README 或对应 CLI 用户可见说明需要解释 `--debug` 与 `--debug-stream` 的差异。
- 需要覆盖 CLI parsing / logging switch tests，验证 `--debug` 不再开启海量 per-delta ingest 日志，`--debug-stream` 可开启这些诊断。

Issue comment 还要求核对 best-effort after-commit `host.memory_repair.catch_up.budget_exhausted` 的普通 `--debug` warning 噪音。Plan gate 已按当前代码证据和用户裁决确认：这是已修复 bug，不是本 WU 的噪音优化项；当前代码已无 `budget_exhausted` stop reason，required catch-up / rebuild / projection failures 仍应 warning，本 WU 只保留 no-regression verification。

### Non-goals

- 不改变 Host / Engine EventLog canonical fact contract。
- 不改变 activity stream 用户可见行为。
- 不把 final answer、业务正文或大块 LLM content 复制进 debug 日志，除非当前日志 contract 已允许且 `--debug-stream` 明确限定。
- 不借本 WU 重构整个 CLI logging subsystem；仅处理 Issue #148 直接支撑的开关、日志分类和测试。

### Entry Conditions

- 先核对 Issue #148 当前状态和评论。
- 核对 CLI parser、runtime logging、Engine / Host stream delta ingest logging sites、memory repair logging sites、现有 CLI tests 和 README 更新触发范围。
- 若发现需要新的 public CLI contract 或 README 用户说明，先在 plan 中明确。

### Acceptance Signals

- `--debug` 不再输出 massive per-delta reasoning/content ingest logs。
- `--debug-stream` 明确启用 stream delta / SSE / per-delta accepted / committed diagnostics。
- `--debug-stream` 可与 `--debug` 组合且行为可测试。
- CLI help / relevant README 更新完成并符合各 README 的更新约束。
- CLI parsing / logging switch tests 覆盖上述行为；pyright 通过；必要的 affected tests 通过。
