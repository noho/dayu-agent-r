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

- 每个 work unit 内的 implementation slices 在 discussion / plan 阶段再具体确定；总控阶段不预先替 work units 固定 slice。
- slice 切分的初始出发点成立：单个 slice 太大时，implementation agent 容易因为上下文过长、局部约束丢失或跨边界状态过多而实现漂移。
- slice 必须控制模型一次实施和 reviewer 一次审查能够稳定承载的上下文规模。
- “上下文规模”不得粗暴等同于文件数、模块数、代码行数或 owner 数；更可靠的切分依据是语义闭环、依赖顺序、失败 / 回滚风险和验证矩阵。
- slice 必须满足模型上下文窗口与 review 可承载复杂度：implementation agent 能在一个上下文中理解目标、边界、相关代码和验证要求；review agent 能在一个上下文中有效审查。
- slice 必须沿稳定代码依赖边界切分：公共契约、状态机边界、存储边界、projection 边界、issue dependency 边界或测试矩阵边界。
- slice 必须形成可独立验证的行为闭环：大到能形成可测试语义，小到能一次实现、一次验证、一次 review。
- 除非明确是 contract-only slice，否则不得留下只有类型、没有路径，或只有存储、没人调用的孤立半成品。
- slice 不是按代码行数切，也不是只要不超过上下文窗口就算合理；好的 slice 必须有明确输入、输出、non-goals、allowed files / modules、验证命令、issue handoff 和后续 slice 可依赖的稳定交付物。
- 不得按模块数量、文件数量或 reviewer ownership 机械拆分。对代码量较小、语义上属于同一个 contract cleanup / config cleanup / schema cleanup 的 work unit，即使会同时触及配置、runtime、Service composition、provider、scene manifest、测试和 README，也应优先合并为少量可验证闭环 slices，而不是每个模块单独切片。
- 只有当某部分存在独立失败 / 回滚风险、需要独立设计裁决、会阻塞后续代码导入，或 review 上下文确实无法承载时，才继续拆分。
- 小型跨模块 cleanup 的默认切分上限是 3 个 implementation slices：
  - contract / config / composition slice：稳定公共语义、typed config、composition root effective config、旧字段拒绝与基础测试；
  - provider / behavior slice：业务 provider 行为、tool schema、存储 / 权限边界、provider 投影测试；
  - scene / docs / final validation slice：默认 scene 暴露面、README / design 同步、stale-field grep、pyright 与受影响测试矩阵。
- 默认 slice budget：
  - 小型同一语义 cleanup：1-3 个 implementation slices。
  - 中型跨 contract / provider / projection work：3-5 个 implementation slices。
  - 超过 5 个 implementation slices：必须有明确证据表明单个 implementation agent / reviewer 的上下文容量无法稳定承载，或存在必须隔离的 schema、状态机、持久化、外部依赖、回滚风险。
- 如果 plan 提出超过 3 个 implementation slices，必须显式说明为什么不能按上述闭环合并；仅以“涉及多个文件 / 多个模块 / 多个 owner”为理由不充分。
- 总控裁决时必须评估 gate 成本：每增加一个 slice 都会增加 implementation artifact、双路 review、controller 裁决、测试复跑和 accepted commit 成本；当流程成本明显超过实现风险时，应倾向合并 slice。
- 如果一个 work unit 的自然闭环超过单个 implementation agent 的上下文容量，应优先按依赖边界拆成多个 slices，并在 plan 中说明前后 slice 的 contract handoff。
- 如果某个 slice 需要跨模块修改，plan 必须解释为什么这是同一个可验证闭环，而不是拆分失败。

## 当前状态

| 项目 | 当前值 |
|---|---|
| phase | Host issue-backed follow-up implementation backlog |
| gate | final-closeout-pass |
| implementation status | WU-WAIT-01 / GitHub Issue #89 merged via PR #163 on 2026-07-01; WU-WAIT-02 / GitHub Issue #90 merged via PR #165 on 2026-07-03 and issue #90 closed automatically; WU-WAIT-03 / GitHub Issue #92 merged via PR #166 on 2026-07-04 and issue #92 closed automatically; WU-LIFE-03 / GitHub Issue #91 merged via PR #167 on 2026-07-04 and issue #91 closed automatically. WU-LIFE-04 draft PR #169 final closeout completed; waiting for user / maintainer to handle draft PR #169. |
| active work unit | WU-LIFE-04 |
| default next work unit | WU-LIFE-04 is the current implementation entry point; after WU-LIFE-04 completes, WU-TOOLS-CANCEL-01 becomes the next entry point, followed by WU-WAIT-04. |
| next entry point | Wait for user / maintainer to handle draft PR #169. After PR #169 merges, pull updated `main` and start WU-TOOLS-CANCEL-01. |
| design source | `docs/host/design.md` and `docs/engine/design.md` for Host / Engine stream terminology, CLI diagnostics, logging, and UI / Service / Host / Engine ownership boundaries. |
| issue status comments | Active/backlog issue owners retained here: #129 / #70 / #34 / #119 / #71 / #27 / #72 / #75 / #43 / #36 / #78 / #156 / #96 / #38 / #91 / #87 / #168 / #88 / #112 / #20 / #80 / #115, plus residual-risk destinations #121 / #122. Completed WU history, draft PR closeout records, merged PR notes, and closed issue notes are archived in `docs/host/issues-implementation-control-archive.md`; #63 / #89 / #90 / #92 / #111 / #130 / #133 are no longer active implementation owners. |
| blocking open questions | None. User confirmed WU-LIFE-04 goal and explicitly prefers deleting `active_cancel_timeout_seconds`; if deletion is not justified by direct implementation evidence, it must at least stop being public API. |

状态约定：

- `not-started`：尚未进入 plan / implementation。
- `discussion-ready`：已具备讨论和代码 / issue 核对入口，但还未形成 code-generation-ready plan。
- `pending-next`：当前 final-closeout-pass work unit merge 后的下一个默认 implementation entry point。
- `blocked-by-issue`：需要等待指定 GitHub Issue / umbrella / dependency 完成。
- `obsolete`：已裁决过期失效，不作为实施入口。
- `planning`：正在形成或 review code-generation-ready plan。
- `accepted-plan`：plan / review / re-review 已通过，等待 accepted plan commit 或进入 implementation。
- `implementation`：正在实施或修复。
- `review`：正在进行 code review、re-review 或 aggregate deepreview。
- `accepted-slice`：implementation slice 已通过 code review / re-review，等待 accepted slice commit 或 aggregate deepreview。
- `ready-to-open-draft-PR`：本轮 work unit 已完成本地 gate，等待进入 draft PR gate。
- `draft-PR-pass`：draft PR gate 已通过。
- `final-closeout-pass`：draft PR、PR review、accepted PR review commit、follow-up push、issue closeout handling 和 final closeout summary 均已记录；等待用户 merge 当前 PR 后从 base branch 进入下一 work unit。

## 推进规则

- 每次只推进一个 work unit。
- 先做 GitHub Issue / dependency / 代码核对，再进入方案和实现。
- Work units 必须按依赖顺序推进：底层 Engine / provider contract 优先于依赖该 contract 的 Host / Service / UI follow-up；umbrella issue 优先于其 child issue；dependent smoke 必须等待前置 production capability 完成。
- 已明确 `blocked-by-issue` 或 `obsolete` 的 work unit 不得绕过状态进入 implementation gate。
- 涉及 public contract、durable schema、状态机、跨层依赖或用户可见行为时，必须先形成明确 design decision。
- 测试优先按风险边界补齐；压力测试和长耗时测试必须与常规测试入口分开。
- 实施完成后必须更新对应测试、类型检查、稳定文档说明和对应 GitHub Issue 状态。
- 每个 work unit 进入 plan、implementation、review、ready-to-open-draft-PR 或 draft-PR-pass 时，必须更新“当前状态”中的 gate、active work unit、next entry point 和 blocking open questions；artifact、commit、review 与历史验证记录写入对应 work unit、review artifact 或 closeout artifact，不在“当前状态”表中累积流水账。

## 实施顺序

本节记录用户在 2026-06-21 裁决的工具调用治理推进顺序。该顺序只约束当前 Host tool-call governance follow-up lane；如果后续 discussion 发现设计真源、GitHub Issue scope 或代码直接证据与本节冲突，必须先更新设计真源、本文档和对应 GitHub Issue，再调整顺序。

1. 先清理已完成 WU 与 GitHub 状态不一致：PR 160 已 merge 且 #133 已关闭，PR 159 已 merge 且 #63 已关闭，PR 135 已 merge 后 #130 已关闭。上述条目不得再作为 active implementation entry point。
2. 以执行正确性为默认下一步，优先推进 WU-TOOLS-AWAIT-FANOUT-01 / #111。目标是在现有 attempt-scoped duplicate governance 与 awaiting accept barrier 之上，先设计重复 awaiting owner / waiter 的单 wait owner 与 fanout follower 语义，再进入 implementation gate。
3. #111 形成稳定设计和验收边界后，再推进 #129 的 awaiting external job two-phase activation。#129 需要修 submit-before-accept 窗口，不能用 Fins-only workaround 绕过 Host awaiting activation contract；如果 #111 改变 wait record alias / follower 表达，#129 plan 必须消费该结论。
4. #129 之后推进 production WAIT hardening：#89 callback endpoint / auth / replay、#90 production poller loop / backoff / fencing / retry、#92 external job physical cancel / revoke / abandon。#92 继续归属 #87 lifecycle watchdog / supervisor umbrella，不另建第二套 watchdog runtime。
5. #89 / #90 / #92 完成后，先推进 WU-LIFE-03 / GitHub Issue #91，固定 active cancel watchdog、post-cancel timeout、Run / Attempt closeout、late terminal race 和 diagnostic 语义。WU-LIFE-03 必须只定义 Host-level cancel governance 和 timeout closeout：cancel command 接受后 Host truth 不等待 worker / provider 配合，超时后有明确终态或 diagnostic，迟到 terminal first-committer-wins / rejection 可验证；不得把 provider-specific kill API 硬编码进 Host 核心。
6. WU-LIFE-03 完成后，先推进 WU-LIFE-04 / GitHub Issue #168，固定 tool execution deadline 与 Host watchdog closeout 的边界：`tool_execution_timeout_seconds` 是单次工具调用最长运行时间，取消 / 收口不得覆盖或延长原始 tool deadline；裁决独立 `active_cancel_timeout_seconds` 的移除、降级或 derived deadline 处理，并为 #87 umbrella 的 scan query optimization、clock skew、diagnostics / audit hooks 和 shared supervisor 验收指定 owner / destination。
7. WU-LIFE-04 完成后，再推进 WU-TOOLS-CANCEL-01，补齐 tool/provider runtime 的实际 interrupt boundary 与 escalation 能力：cooperative token、request / stream abort、subprocess / process-group / sandbox termination、hard-kill diagnostic closeout。目标是获得 Codex / Claude Code 类似的用户体感：取消后 Host 迅速回到可交互状态，旧 tool/provider 结果不得污染已取消 Run，且不得延长 WU-LIFE-04 固定的单次工具执行 deadline。若 tool/provider 在 Host 不可抢占的同进程 blocking I/O 中执行，本 WU 必须迁移到可中断 execution capsule 或明确禁止该执行形态进入 production-grade cancel path。
8. WU-LIFE-03、WU-LIFE-04 与 WU-TOOLS-CANCEL-01 完成后，WU-WAIT-04 才能进入 implementation gate，用 UI / Service production-grade awaiting E2E smoke 验证 public watcher、WAITING 展示、production wait resolution、terminal event、outbox 补读，以及取消后的可交互恢复体验。不得用 manual resolve、测试私有 durable wait id 或只靠 cooperative tool 配合伪造 production-grade 验收。
9. #70 / #34 / #119 / #71 作为 Tool Trace diagnostics lane 可以并行做 discussion / design，但不得替代 #111 / #129 / #89-#92 / #91 / #168 / WU-TOOLS-CANCEL-01 的 ToolRuntime、wait lifecycle 与 cancel root-cause 修复。诊断 lane 的输出可以反向补充验收信号，例如重复调用、awaiting fanout、late result、oversized payload、limited-signal report 和 post-cancel stale output。

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

## 当前 Work Units

| Work Unit | 状态 | 主题 | Owner / Destination | 当前定位 |
|---|---|---|---|---|
| WU-TOOLS-01-F01-02-R1 | final-closeout-pass | Awaiting external job two-phase activation | GitHub Issue #129 / draft PR #162 | Final closeout 已完成；等待 maintainer/user 处理 draft PR #162。PR body 使用 `Closes #129`，merge 会自动关闭 issue。当前目标是 Host 支持 accepted-wait 后 activation hook，且 Fins download / preprocess / upload awaiting tools 本轮直接迁移到 prepare / activate；禁止过度设计。 |
| WU-TOOLS-AWAIT-FANOUT-01 | completed | Host ToolRuntime awaiting fanout governance hardening | GitHub Issue #111 / PR #161 | PR 161 merged on 2026-06-21; not an active implementation entry point. |
| WU-TOOLS-01-F03-R4 | completed | Tools Discovery spec semantics cleanup | GitHub Issue #133 / PR #160 | PR 160 merged on 2026-06-21 and issue #133 is closed; not an active implementation entry point. |
| WU-ENG-02-R1 | completed | Provider debugging correlation default enablement and fallback diagnostics | GitHub Issue #63 / PR #159 | PR 159 merged on 2026-06-20 and issue #63 is closed; not an active WU for this branch. |
| WU-OBS-00 | pending | Tool Trace analyzer | GitHub Issue #70 | 前置 signal bundle 已完成；trace 文件 / 目录输入的 Host / Engine / Tool 分层诊断；WU-OBS-01 的诊断底座 |
| WU-OBS-00A | pending-parent | Tool Trace analyzer integrity and large payload diagnostics | GitHub Issue #34 / #70 child | #70 analyzer 子项；不单独实现一套 analyzer |
| WU-OBS-00B | pending-parent | Usage observation projection correlation boundary | GitHub Issue #119 / #70 child | #70 analyzer 子项；owner for residual `WU-ENG-02-S3-R1` |
| WU-OBS-01 | pending-prerequisite | Prompt-based Tool Trace diagnostics | GitHub Issue #71；GitHub Issue #27 superseded | #71 作为主 issue，吸收 #27 的 prompt / final answer 反查诉求 |
| WU-AUDIT-01 | pending | Audit Ledger viewer and integrity report | GitHub Issue #72 | read-only audit JSONL ledger viewer；审计责任链 / 完整性校验，不做 Tool Trace root-cause analyzer |
| WU-AUDIT-02 | pending | External audit delivery contract with local validation adapters | GitHub Issue #75 | async external audit delivery 语义；无真实外部系统时先用 Noop / FileMirror adapter 验证 contract |
| WU-RET-01 | pending | Tool Trace cold JSONL storage governance | GitHub Issue #36 / #43 child | Retention lane 默认第 1 项；Tool Trace cold JSONL rotation / retention / compaction / size reporting；不作为 #70 前置 |
| WU-RET-03 | pending | purge_session-driven retention cleanup | GitHub Issue #78 / #43 child | Retention lane 默认第 2 项；定义 `purge_session` 驱动的 session-scoped retention cleanup owner；解锁 WU-RET-04 |
| WU-RET-04 | pending-prerequisite | Compaction artifact retention | GitHub Issue #156 / #78 child | Retention lane 默认第 3 项；必须等待 WU-RET-03 / #78 固定 purge cleanup 边界后实施 |
| WU-RET-02 | pending | Audit JSONL storage governance | GitHub Issue #96 / #43 child | Retention lane 默认第 4 项；Audit JSONL rotation / retention / compaction / size reporting；保留 purge tombstone 可验证关联 |
| WU-STRESS-SQLITE-01 | pending | SQLite multiprocess high-spec stress | GitHub Issue #38 | 现有 SQLite 多进程压力测试链路的慢盘 / Docker Linux 高规格版本 |
| WU-LIFE-03 | completed | Active cancel watchdog | GitHub Issue #91 / #87 umbrella / PR #167 | PR 167 merged on 2026-07-04 and issue #91 closed automatically; not an active implementation entry point. 固定 Host-level active cancel watchdog、post-cancel timeout closeout、late terminal race 和 diagnostic 语义。只负责 Host truth / timeout closeout，不负责 tool/provider hard interrupt。 |
| WU-LIFE-04 | final-closeout-pass | Tool execution deadline and #87 watchdog closeout | GitHub Issue #168 / #87 umbrella / draft PR #169 | #87 umbrella follow-up；已确认 `tool_execution_timeout_seconds` 是单次工具调用最长运行时间，取消/收口机制不得覆盖或延长该 deadline。Goal confirmation 已由用户确认，用户裁决优先删除 `active_cancel_timeout_seconds`；若直接实现证据不支持删除，至少不得继续作为 public API 暴露。Plan artifact 为 `docs/host/wu-life-04-tool-execution-deadline-watchdog-plan.md`，plan review artifacts 为 `docs/reviews/wu-life-04-plan-review-mimo.md` 与 `docs/reviews/wu-life-04-plan-review-ds.md`；controller adjudication 为 `docs/reviews/wu-life-04-plan-review-controller-adjudication.md`。Plan fix artifact 为 `docs/reviews/wu-life-04-plan-fix-codex.md`；AgentCodex reported PLAN-F01 / F02 / F03 / F04 / F05 and PLAN-I01 fixed and `git diff --check` passed. Plan re-review artifacts 为 `docs/reviews/wu-life-04-plan-rereview-mimo.md` 与 `docs/reviews/wu-life-04-plan-rereview-ds.md`；controller adjudication 为 `docs/reviews/wu-life-04-plan-rereview-controller-adjudication.md`。两路 re-review 均通过，所有 accepted findings 已修复，无 blocking open question。Accepted plan commit 为 `59be8480`。Slice 1 implementation artifact 为 `docs/reviews/wu-life-04-slice1-implementation-codex.md`。Slice 2 implementation artifact 为 `docs/reviews/wu-life-04-slice2-implementation-codex.md`。Controller reran `pytest tests/engine/test_agent_phase3_tool_call.py -q` with 44 passed, Host focused tests with 250 passed, pyright with 0 errors, and `git diff --check` passed. Grep checks for `active_cancel_timeout_seconds` and `active_cancel_timeout|timeout_seconds.*active` returned no matches in the required scope. Code review artifacts 为 `docs/reviews/wu-life-04-slice-code-review-mimo.md` 与 `docs/reviews/wu-life-04-slice-code-review-ds.md`；controller adjudication 为 `docs/reviews/wu-life-04-slice-code-review-controller-adjudication.md`。Controller accepted dead helper cleanup finding S1S2-CR-F01 and deferred watchdog loop fatal-exit operability risk to Issue #87 umbrella. Fix artifact 为 `docs/reviews/wu-life-04-slice-fix-codex.md`。Code re-review artifacts 为 `docs/reviews/wu-life-04-slice-code-rereview-mimo.md` 与 `docs/reviews/wu-life-04-slice-code-rereview-ds.md`；controller adjudication 为 `docs/reviews/wu-life-04-slice-code-rereview-controller-adjudication.md`。两路 re-review 均通过，S1S2-CR-F01 已修复，无新增 material blocker。Controller reran engine target tests with 44 passed, Host focused tests with 250 passed, pyright 0 errors, `git diff --check` passed, and required grep checks returned no matches. Accepted Slice 1 + Slice 2 implementation commit 为 `c75205c5`。Aggregate deepreview artifacts 为 `docs/reviews/wu-life-04-aggregate-deepreview-mimo.md` 与 `docs/reviews/wu-life-04-aggregate-deepreview-ds.md`；controller adjudication 为 `docs/reviews/wu-life-04-aggregate-deepreview-controller-adjudication.md`。Controller accepted AGG-F01 stale watchdog eligible docstring finding and deferred remaining residual risks to WU-TOOLS-CANCEL-01 or Issue #87. Aggregate fix artifact 为 `docs/reviews/wu-life-04-aggregate-fix-codex.md`；AgentCodex reported AGG-F01 fixed, pyright 0 errors, `git diff --check` passed, and stale docstring grep returned no matches. Aggregate re-review artifacts 为 `docs/reviews/wu-life-04-aggregate-rereview-mimo.md` 与 `docs/reviews/wu-life-04-aggregate-rereview-ds.md`；controller adjudication 为 `docs/reviews/wu-life-04-aggregate-rereview-controller-adjudication.md`。两路 re-review 均通过，AGG-F01 已修复，无新增 material blocker。Accepted aggregate deepreview commit 为 `cd92dbb9`。Draft PR #169 created: https://github.com/noho/dayu-agent-r/pull/169. PR body uses `Closes #168`; #87 remains related umbrella owner only. PR review artifacts 为 `docs/reviews/wu-life-04-pr-169-review-mimo.md` 与 `docs/reviews/wu-life-04-pr-169-review-ds.md`；controller adjudication 为 `docs/reviews/wu-life-04-pr-169-review-controller-adjudication.md`。两路 PR review 均通过，无 accepted findings。Accepted PR review commit 为 `52cf5dc9`，并已 push 到 draft PR #169。Final closeout artifact 为 `docs/reviews/wu-life-04-final-closeout.md`。Issue closeout comment 已发布：https://github.com/noho/dayu-agent-r/issues/168#issuecomment-4881439527。PR body 使用 `Closes #168`，merge 会自动关闭 #168；#87 仅作为 umbrella owner 保留。Remaining risks are deferred-with-owner to WU-TOOLS-CANCEL-01 or Issue #87 follow-ups. 当前进入 final-closeout-pass，等待用户 / maintainer 处理 draft PR #169；不得未经授权 mark ready、merge、close issue、request reviewers 或 delete branch。Merge PR #169 后，应从 `main` 拉取最新代码，再按本文档 next entry point 进入 WU-TOOLS-CANCEL-01。 |
| WU-GOV-01 | pending | Host policy refusal terminal taxonomy | GitHub Issue #88 | 引入 `RunStatus.REJECTED` 表达权限、租户、额度、配额、速率限制、工具权限 / 审批等 Host policy refusal；compact failure 默认不迁移到 `REJECTED`。 |
| WU-CTX-04 | pending-low | Run-level compaction concurrency boundary | GitHub Issue #112 | 低优先级设计核对：不引入 EventLog fencing；证明当前状态机 / request 计数 / stale recheck 足够，或在未来并发模型需要时设计 EventLog 外的最小 pointer / CAS。 |
| WU-CTX-01 | pending | Provider tokenizer / sizing adapter | GitHub Issue #20 | provider/model-aware context sizing；仍有效，需先收敛 budget policy 设计表述 |
| WU-WAIT-01 | completed | Callback endpoint / auth / replay | GitHub Issue #89 / PR #163 | PR 163 merged on 2026-07-01; not an active implementation entry point. 当前实现提供 Host wait callback typed boundary 与 Service framework-neutral mapper；不包含真实 HTTP route、secret backend、HMAC / bearer verifier、production poller、physical cancel、Engine contract 或 UI surface。 |
| WU-WAIT-02 | completed | Production poller loop / backoff / fencing / retry | GitHub Issue #90 / PR #165 | PR 165 merged on 2026-07-03 and issue #90 closed automatically; not an active implementation entry point. |
| WU-WAIT-03 | completed | External job physical cancel / revoke / abandon | GitHub Issue #92 / #87 umbrella / PR #166 | PR 166 merged on 2026-07-04 and issue #92 closed automatically; not an active implementation entry point. |
| WU-TOOLS-CANCEL-01 | pending-prerequisite | Tool/provider blocking I/O cancellation hardening | follows WU-LIFE-04 | WU-LIFE-04 完成后实施；设计 Host-owned tool/provider execution interrupt boundary 与 escalation：cooperative token、request / stream abort、subprocess / process-group / sandbox termination、hard-kill diagnostic closeout。生产级目标是 Codex / Claude Code 类似 interrupt 体感：取消后 Host 迅速回到可交互状态，旧结果不能污染已取消 Run，且不得延长单次工具执行 deadline；不可抢占 blocking I/O 必须迁移到可中断 capsule 或被禁止进入 production cancel path。 |
| WU-WAIT-04 | pending-prerequisite | UI / Service production-grade awaiting E2E smoke | depends on #89 / #90 / #92 + WU-LIFE-03 + WU-LIFE-04 + WU-TOOLS-CANCEL-01 | dependent smoke；等待 #89 / #90 / #92 merge，并完成 WU-LIFE-03、WU-LIFE-04 与 WU-TOOLS-CANCEL-01 后进入 implementation gate。覆盖原 WU-WAIT-03-R1：验证 Service / composition 在生产等待路径启用并装配 wait poller / adapter registry，使 cancelled WAITING external lifecycle action 能在 public workflow 中执行，并验证取消后的 public 可交互恢复体验。 |
| WU-CM-10 | deferred | Conversation Memory eval benchmark | GitHub Issue #80 / #81 follow-up | deferred behind #81；post-#81 memory semantic contract 稳定后再实施 |
| WU-CM-11 | deferred | User Profile Memory durable boundary and cross-session profile | GitHub Issue #115 / #81 child | deferred behind #81；#81 只固定 User Profile 不混入 session Conversation Memory 的边界，跨 session durable profile 独立后续实施 |

## WU-WAIT-03 External Job Physical Cancel / Revoke / Abandon

### 状态

GitHub Issue #92 当前为 OPEN，归属 #87 Host Lifecycle Watchdog / Supervisor umbrella。WU-WAIT-01 / GitHub Issue #89 已通过 PR #163 于 2026-07-01 merge 到 `main`；WU-WAIT-02 / GitHub Issue #90 已通过 PR #165 于 2026-07-03 merge 到 `main`。Goal confirmation 已由用户确认。Plan artifact 为 `docs/host/wu-wait-03-external-job-lifecycle-plan.md`。Plan、Slice 1、Slice 2、aggregate deepreview、README sync fix、aggregate re-review、draft PR、PR review 和 final closeout gate 均已完成；完整 artifact 记录见本文档后续 WU-WAIT-03 active section 以及 `docs/reviews/wu-wait-03-*`。Draft PR #166 已创建：https://github.com/noho/dayu-agent-r/pull/166。PR body 使用 `Closes #92`，merge 会自动关闭 #92。Issue closeout comment 已发布：https://github.com/noho/dayu-agent-r/issues/92#issuecomment-4880126795。当前进入 final-closeout-pass，等待用户 / maintainer 处理 draft PR #166；不得未经授权 mark ready、merge、close issue、request reviewers 或 delete branch。

### 设计与代码核对

- Host 设计真源规定 Host 是 Session / Run / Attempt / EventLog / wait record 的治理真源；provider lifecycle 动作不得成为 Host cancellation correctness 的前置条件。
- Engine 设计真源规定 Engine 不轮询外部长事务、不持久化 wait record、不恢复旧 Agent / Runner，也不拥有 external job lifecycle。
- 代码核对显示 `cancel_run` / `cancel_session_runs` 取消 `WAITING` Run 时只走 Host durable cancel 收口；external job lifecycle 当前落点是 wait poller 对 cancelled wait 调用 `WaitPollAdapter.abandon_wait(...)`。
- 当前 `WaitPollAdapter.abandon_wait(...)` 只能通过返回 `None` 或抛异常表达结果，尚不能区分 physical cancel / revoke / abandon、unsupported、noop、timeout 或 transient failure。

### 目标

- 固化 WAITING external job physical cancel / revoke / abandon 的 typed adapter capability 与 best-effort diagnostic 语义。
- Host-side `RUN_CANCELLED` 正确性不得依赖外部 cancel 成功；external lifecycle failure / timeout 不得 reopen 或改写已 cancelled Run。
- late callback / poll / manual result 仍必须通过 common `resolve_wait(...)` path，被 late-result diagnostic 拒绝，不创建 resume Attempt。

### 非目标

- 不修改 Engine awaiting public model。
- 不让 Engine 拥有等待、取消、轮询、恢复或 external job lifecycle。
- 不把 external job id 变成 Host durable primary key。
- 不要求所有 provider 支持 physical cancel。
- 不绕过 `resolve_wait(...)` / late-result rejection。
- 不创建 #87 之外的第二套 watchdog/runtime。
- 不做 WU-WAIT-04 UI / Service production-grade awaiting E2E smoke。

### Plan Review Gate 约束

- Review 必须审查 plan 是否 code-generation-ready，是否从直接代码证据定位 root cause，是否存在把 Host cancel correctness 绑定到 provider cancel 成功的设计错误。
- Review 必须审查 Slice 切分是否符合本文档 Slice 切分原则；本 WU 当前 plan 为 2 个 implementation slices，超过 3 个 slices 的替代建议必须有明确上下文容量、失败/回滚风险或依赖顺序证据。
- Review 必须审查 plan 是否误引入新的 public Host API、Engine contract、durable schema、provider capability registry、第二套 watchdog 或过度设计。
- Review findings 必须能裁决为 `accepted`、`rejected-with-reason`、`deferred-with-owner` 或 `needs-more-evidence`。

## WU-WAIT-02 Production Poller Loop / Backoff / Fencing / Retry

### 状态

GitHub Issue #90 当前为 OPEN。WU-WAIT-01 / GitHub Issue #89 已通过 PR #163 于 2026-07-01 merge 到 `main`，本文档先前记录的 “等待 PR #163 后进入 WU-WAIT-02” 前置条件已满足。Goal confirmation 已由用户确认。Plan artifact 为 `docs/host/wu-wait-02-production-poller-plan.md`。Plan review artifacts 为 `docs/reviews/plan-review-20260701-135815.md` 与 `docs/reviews/plan-review-20260701-140124.md`，controller adjudication 为 `docs/reviews/wu-wait-02-plan-review-controller-adjudication.md`。Plan-fix artifact 为 `docs/reviews/wu-wait-02-plan-fix-codex.md`。Plan re-review artifacts 为 `docs/reviews/plan-review-20260701-141039.md` 与 `docs/reviews/plan-review-20260701-141200.md`，controller adjudication 为 `docs/reviews/wu-wait-02-plan-rereview-controller-adjudication.md`。两路 re-review 均通过，所有 accepted findings 已修复。Accepted plan commit 为 `350e1dbf`。Slice 1 implementation artifact 为 `docs/reviews/wu-wait-02-slice1-implementation-codex.md`；AgentCodex reported focused Host durable / wait adapter tests 102 passed, pyright 0 errors, and `git diff --check` passed. Controller reran the same focused tests with 102 passed, pyright with 0 errors, and `git diff --check` passed. Slice 1 code review artifacts 为 `docs/reviews/code-review-20260701-143921.md` 与 `docs/reviews/code-review-20260701-144036.md`；controller adjudication 为 `docs/reviews/wu-wait-02-slice1-code-review-controller-adjudication.md`。两路 code review 均通过，无 required current fix；DS low-severity items 已裁决为 non-blocking / Slice 2 optional coverage。Accepted Slice 1 commit 为 `b7447316`。Slice 2 implementation artifact 为 `docs/reviews/wu-wait-02-slice2-implementation-codex.md`；AgentCodex reported wait poller runtime focused tests 20 passed, schema / wait record tests 57 passed, pyright 0 errors, and `git diff --check` passed. Controller reran the same focused test sets with 20 passed and 57 passed, pyright with 0 errors, and `git diff --check` passed. Slice 2 code review artifacts 为 `docs/reviews/code-review-20260701-150341.md` 与 `docs/reviews/code-review-20260701-150525.md`；controller adjudication 为 `docs/reviews/wu-wait-02-slice2-code-review-controller-adjudication.md`。Controller accepted S2-CR-F01 unsafe default direct factory, S2-CR-F02 constructor dead parameters, S2-CR-F03 self-close contract gap, S2-CR-F04 double-close transient state, and S2-CR-F05 close drain timeout `None` contract mismatch. Fix artifact 为 `docs/reviews/wu-wait-02-slice2-fix-codex.md`；AgentCodex reported wait poller runtime focused tests 24 passed, schema / wait record tests 57 passed, pyright 0 errors, and `git diff --check` passed. Controller reran the same focused test sets with 24 passed and 57 passed, pyright with 0 errors, and `git diff --check` passed. Slice 2 code re-review artifacts 为 `docs/reviews/code-review-20260701-151948.md` 与 `docs/reviews/code-review-20260701-152140.md`；controller adjudication 为 `docs/reviews/wu-wait-02-slice2-code-rereview-controller-adjudication.md`。两路 code re-review 均通过，S2-CR-F01 / F02 / F03 / F04 / F05 均已关闭，无新增 material defect。Accepted Slice 2 commit 为 `2974b5a2`。Slice 3 implementation artifact 为 `docs/reviews/wu-wait-02-slice3-implementation-codex.md`；AgentCodex reported open_host / poller / resolve focused tests 51 passed, public lifecycle smoke 2 passed, pyright 0 errors, and `git diff --check` passed. Controller reran the same validation with 51 passed, 2 passed, pyright 0 errors, and `git diff --check` passed. Slice 3 code review artifacts 为 `docs/reviews/code-review-20260701-154721.md` 与 `docs/reviews/code-review-20260701-154834.md`；controller adjudication 为 `docs/reviews/wu-wait-02-slice3-code-review-controller-adjudication.md`。两路 code review 均通过，无 required current fix。Accepted Slice 3 commit 为 `1486e5a9`。Aggregate deepreview artifacts 为 `docs/reviews/code-review-20260701-155500.md` 与 `docs/reviews/code-review-20260701-160040.md`；controller adjudication 为 `docs/reviews/wu-wait-02-aggregate-deepreview-controller-adjudication.md`。两路 aggregate deepreview 均通过，无 blocking finding；residual risks 已归属 Service composition / WU-WAIT-03 / WU-WAIT-04 或 accepted design tradeoff。Accepted aggregate deepreview commit 为 `346b5ae7`。Draft PR #165 已创建：https://github.com/noho/dayu-agent-r/pull/165。PR review artifacts 为 `docs/reviews/pr-165-review-20260701-164627.md` 与 `docs/reviews/pr-165-review-20260701-164858.md`；AgentCodex fix artifact 为 `docs/reviews/wu-wait-02-pr-review-fix-codex.md`；PR re-review artifacts 为 `docs/reviews/pr-165-re-review-20260701-170000.md` 与 `docs/reviews/pr-165-re-review-20260701-170022.md`；controller adjudication 为 `docs/reviews/wu-wait-02-pr-review-controller-adjudication.md`。DS Finding 01 已接受并修复，两路 re-review 均裁决已修复；DS Finding 02 已裁决为 rejected-with-reason；MiMo findings 均为 non-blocking notes / design confirmations。Accepted PR review commit 为 `0bfedacf`，并已 push 到 draft PR #165。`gh pr checks 165` reported no checks on branch `work/wu-wait-02-issue-90`。Final closeout artifact 为 `docs/reviews/wu-wait-02-final-closeout.md`。Issue closeout comment 已发布：https://github.com/noho/dayu-agent-r/issues/90#issuecomment-4852470129。PR body 使用 `Closes #90`，merge 会自动关闭 #90。当前进入 final-closeout-pass gate，等待用户 / maintainer 处理 draft PR #165；不得未经授权 mark ready、merge、close issue、request reviewers 或 delete branch。Merge PR #165 后，应从 `main` 拉取最新代码，再按本文档 next entry point 进入 WU-WAIT-03 / GitHub Issue #92。Review / implementation / fix / re-review artifact 放在 `docs/reviews/` 下。

### 设计与代码核对

- Host 设计真源规定：wait poller 是 background runtime 中的 trigger / adapter。它观察 wait record 与外部 job，但只能通过 `resolve_wait` command path 提交结果；不得持有 EventLog appender，不得直接更新 Run / Attempt / wait record terminal state。
- Host 设计真源规定：`poll`、`callback`、`manual` 只是发现等待结果已经到达的 adapter；稳定核心是共同的 Host `resolve_wait` pipeline。
- Host 设计真源规定：poll adapter 从 wait record 读取 `external_job_id` / `await_spec` 后继续轮询，并在完成时调用同一个 `resolve_wait`；`cancelled` / `lost` wait record 的迟到结果不得作为 canonical fact 进入 EventLog。
- Engine 设计真源规定：Engine 不等待外部长事务完成，不轮询 job，不持久化 wait record，不保留可恢复的 Agent / Runner；长事务 awaiting、orphan cleanup 和工具级取消属于 Host / ToolRuntime。
- GitHub Issue #90 明确当前已有最小 `WaitPoller.poll_once()`：读取 active poll / cancelled wait records，在 Host transaction 外调用 adapter，ready / lost 结果通过 `resolve_wait`，not-ready 不动作，cancelled 调用 `abandon_wait`，adapter 异常按单条 wait 隔离。
- 代码核对显示 `dayu/host/wait_adapter.py` 当前 `WaitPoller` 是同步单轮 primitive，返回 `WaitPollOnceResult(observed, not_ready, resolved, lost, abandoned, adapter_errors)`；当前没有后台循环、生命周期 start / stop / close drain、退避策略、in-flight claim / fencing、运行状态诊断或 supervisor 集成。
- 代码核对显示 `tests/host/test_wait_adapter_polling.py` 已覆盖 ready、not-ready、lost、cancelled abandon-once、missing adapter、adapter error isolation、resolve_wait error isolation 与 abandon failure retry；尚未覆盖 production loop lifecycle、backoff、concurrent poller claim conflict、resolve retry / idempotency 与 shutdown behavior。

### 目标

- 在 Host 层设计并实现 production wait poller loop，围绕现有 `poll_once` / batch poll 语义提供可启动、可停止、可关闭收尾的后台 runtime。
- 引入 bounded backoff，覆盖 adapter exception、rate limit / provider busy、重复 not-ready、cancelled wait abandon failure 与 transient `resolve_wait` failure，避免 tight loop。
- 引入最小 in-flight claim / fencing，防止多个 poller 或 Host 进程并发处理同一 wait record；claim 只防重复 polling / duplicate resolve，不表达 Attempt ownership、EventLog truth、外部 job ownership、旧 Attempt takeover 或重 lease。
- poller ready / lost 结果必须继续走共同 Host `resolve_wait` pipeline；不得直接 append EventLog、更新 Run / Attempt / wait record terminal state、创建 resume Attempt 或绕过幂等检查。
- 提供可测试、可观测的 poll loop diagnostics：running / stopped、observed / claimed / skipped、ready / lost / not-ready、adapter errors、resolve failures、backoff decisions、claim expiration / conflict。
- 通过 existing `watch_session_events(...)` / outbox 观察 Host 状态推进，不把 poller 设计成 UI event iterator。

### 非目标

- 不实现 HTTP callback auth / replay；该能力已由 WU-WAIT-01 / GitHub Issue #89 处理。
- 不实现 external job physical cancel / revoke / abandon 的完整 provider lifecycle；该能力归 WU-WAIT-03 / GitHub Issue #92。
- 不实现 UI / Service production-grade awaiting E2E smoke；该验收归 WU-WAIT-04，必须等待 #89 / #90 / #92 完成。
- 不把 poller 变成通用 scheduler、watcher、UI event iterator、lifecycle supervisor 或分布式 lease / Attempt takeover 系统。
- 不让 backoff state 成为 Host durable truth，除非 plan 基于直接代码证据证明某个最小 durable 字段是 claim / multi-process correctness 必需。
- 不改变 Engine awaiting 公共模型，不让 Engine 拥有 wait record、poller、activation 或 external job lifecycle truth。

### Plan Gate 约束

- Plan 必须先裁决 claim / fencing 放置位置：是扩展 wait record durable row、增加独立 poll claim 表，还是使用其它最小 Host durable primitive；必须说明为什么该选择不是 lease / takeover。
- Plan 必须明确 poll loop 的 lifecycle API、Host opener / close 集成方式、sleep cancellation、in-flight adapter 调用边界、close drain 和异常上报。
- Plan 必须明确 backoff policy 的 owner、状态存储位置、重试节奏、上限、诊断表达和测试注入点；不得用魔法数字散落实现。
- Plan 必须明确 resolve retry / idempotency 语义：poller 失败重试不得 double-resolve，必须复用稳定 poll idempotency key 或明确新的幂等键策略。
- Plan 必须明确 diagnostics 是否只是 runtime read view / log / result summary，还是需要进入 EventLog diagnostic；若进入 EventLog，必须先对齐 Host 设计真源。
- Plan 必须按本文档 Slice 切分原则控制 gate 成本。当前属于中型 Host durable/runtime work，默认优先 2-3 个可验证 implementation slices；超过 3 个 slices 必须说明不能合并的独立失败 / 回滚风险。

### 验收信号

- Production poller loop 可以后台运行并在 Host close / explicit stop 时干净停止，不留下 sleep 或 in-flight wait 悬挂。
- 多个 poller 不会并发 resolve 同一 wait；claim conflict / expiration 行为可测试。
- Adapter 间歇失败、重复 not-ready、abandon failure 和 transient `resolve_wait` failure 不会丢失 wait，也不会 tight-loop。
- Ready / lost outcomes 仍通过共同 `resolve_wait` 管线推进 Host EventLog、wait record、Run / Attempt 与 resume dispatch。
- UI / Service 通过现有 Host event watch / outbox 能观察 poller 推进后的状态；poller 不直接返回 UI events。
- 受影响 Host tests、Service assembly tests、pyright 通过；涉及 Host public contract、durable schema、状态机或 README 职责范围的变化必须同步设计真源与对应 README。

## WU-TOOLS-01-F01-02-R1 Awaiting External Job Two-Phase Activation

### 状态

GitHub Issue #129 当前为 OPEN。本条来自 `WU-TOOLS-01-F01-02` residual risk：Fins awaiting external job 当前存在 submit-before-accept 窗口。PR 161 / WU-TOOLS-AWAIT-FANOUT-01 已 merge，#111 的单 owner / fanout 语义已可作为本条设计依据。用户在 2026-06-21 goal confirmation 中确认本条进入 plan gate，并补充裁决：本 WU 必须一次到位实现 Host two-phase activation 支持，并让当前 Fins download / preprocess / upload awaiting tools 直接使用 two-phase；禁止引入过度设计。Plan artifact 为 `docs/host/wu-tools-01-f01-02-r1-plan.md`。Plan review artifacts 为 `docs/reviews/plan-review-20260621-180827.md` 与 `docs/reviews/plan-review-20260621-181350.md`，controller adjudication 为 `docs/reviews/wu-tools-01-f01-02-r1-plan-review-controller-adjudication.md`。Plan-fix artifact 为 `docs/reviews/wu-tools-01-f01-02-r1-plan-fix-codex.md`。Plan re-review artifacts 为 `docs/reviews/plan-review-20260621-182034.md` 与 `docs/reviews/plan-review-20260621-182047.md`，controller adjudication 为 `docs/reviews/wu-tools-01-f01-02-r1-plan-rereview-controller-adjudication.md`。两路 re-review 均通过，所有 accepted findings 已修复。Accepted plan commit 为 `478f5f77`。Slice 1 implementation artifact 为 `docs/reviews/wu-tools-01-f01-02-r1-slice1-implementation-codex.md`；focused test reported `34 passed` and pyright reported 0 errors. Slice 1 code review artifacts 为 `docs/reviews/wu-tools-01-f01-02-r1-slice1-code-review-mimo.md` 与 `docs/reviews/wu-tools-01-f01-02-r1-slice1-code-review-ds.md`；controller adjudication 为 `docs/reviews/wu-tools-01-f01-02-r1-slice1-code-review-controller-adjudication.md`。Fix artifact 为 `docs/reviews/wu-tools-01-f01-02-r1-slice1-fix-codex.md`；focused test reported `37 passed` and pyright reported 0 errors. Slice 1 code re-review artifacts 为 `docs/reviews/wu-tools-01-f01-02-r1-slice1-code-rereview-mimo.md` 与 `docs/reviews/wu-tools-01-f01-02-r1-slice1-code-rereview-ds.md`；controller adjudication 为 `docs/reviews/wu-tools-01-f01-02-r1-slice1-code-rereview-controller-adjudication.md`。Accepted Slice 1 commit 为 `e10f2e99`。Slice 2 implementation artifact 为 `docs/reviews/wu-tools-01-f01-02-r1-slice2-implementation-codex.md`；Fins focused tests reported `51 passed` and `68 passed`, pyright reported 0 errors. Slice 2 code review artifacts 为 `docs/reviews/wu-tools-01-f01-02-r1-slice2-code-review-mimo.md` 与 `docs/reviews/wu-tools-01-f01-02-r1-slice2-code-review-ds.md`；controller adjudication 为 `docs/reviews/wu-tools-01-f01-02-r1-slice2-code-review-controller-adjudication.md`。Fix artifact 为 `docs/reviews/wu-tools-01-f01-02-r1-slice2-fix-codex.md`；Fins focused tests reported `68 passed` and `51 passed`, pyright reported 0 errors. Slice 2 code re-review artifacts 为 `docs/reviews/wu-tools-01-f01-02-r1-slice2-code-rereview-mimo.md` 与 `docs/reviews/wu-tools-01-f01-02-r1-slice2-code-rereview-ds.md`；controller adjudication 为 `docs/reviews/wu-tools-01-f01-02-r1-slice2-code-rereview-controller-adjudication.md`。Accepted Slice 2 commit 为 `4f45f8de`。Slice 3 implementation artifact 为 `docs/reviews/wu-tools-01-f01-02-r1-slice3-implementation-codex.md`；Service test reported `52 passed`, focused Host/Fins tests reported `159 passed`, pyright reported 0 errors. Slice 3 code review artifacts 为 `docs/reviews/wu-tools-01-f01-02-r1-slice3-code-review-mimo.md` 与 `docs/reviews/wu-tools-01-f01-02-r1-slice3-code-review-ds.md`；controller adjudication 为 `docs/reviews/wu-tools-01-f01-02-r1-slice3-code-review-controller-adjudication.md`。Fix artifact 为 `docs/reviews/wu-tools-01-f01-02-r1-slice3-fix-codex.md`；Service test reported `52 passed`, focused Host/Fins tests reported `159 passed`, pyright reported 0 errors. Slice 3 code re-review artifacts 为 `docs/reviews/wu-tools-01-f01-02-r1-slice3-code-rereview-mimo.md` 与 `docs/reviews/wu-tools-01-f01-02-r1-slice3-code-rereview-ds.md`；controller adjudication 为 `docs/reviews/wu-tools-01-f01-02-r1-slice3-code-rereview-controller-adjudication.md`。Narrow fix artifact 为 `docs/reviews/wu-tools-01-f01-02-r1-slice3-rereview-fix-codex.md`；narrow code re-review artifacts 为 `docs/reviews/wu-tools-01-f01-02-r1-slice3-narrow-rereview-mimo.md` 与 `docs/reviews/wu-tools-01-f01-02-r1-slice3-narrow-rereview-ds.md`；controller adjudication 为 `docs/reviews/wu-tools-01-f01-02-r1-slice3-narrow-rereview-controller-adjudication.md`。两路 narrow re-review 均通过，S3-RR-F01 已关闭。Accepted Slice 3 commit 为 `80ab56ab`。Aggregate deepreview artifacts 为 `docs/reviews/wu-tools-01-f01-02-r1-aggregate-deepreview-mimo.md` 与 `docs/reviews/wu-tools-01-f01-02-r1-aggregate-deepreview-ds.md`；aggregate fix artifact 为 `docs/reviews/wu-tools-01-f01-02-r1-aggregate-fix-codex.md`；aggregate fix narrow re-review artifacts 为 `docs/reviews/wu-tools-01-f01-02-r1-aggregate-rereview-mimo.md` 与 `docs/reviews/wu-tools-01-f01-02-r1-aggregate-rereview-ds.md`；controller adjudication 为 `docs/reviews/wu-tools-01-f01-02-r1-aggregate-deepreview-controller-adjudication.md`。AGG-F01 已关闭，controller 裁决无当前 WU 未归属 residual risk。Accepted deepreview commit 为 `95f652de`。Draft PR #162 已创建：https://github.com/noho/dayu-agent-r/pull/162。`gh pr checks 162` reported no checks on branch `phase/wu-tools-01-f01-02-r1`。PR review artifacts 为 `docs/reviews/wu-tools-01-f01-02-r1-pr-review-mimo.md` 与 `docs/reviews/wu-tools-01-f01-02-r1-pr-review-ds.md`；controller adjudication 为 `docs/reviews/wu-tools-01-f01-02-r1-pr-review-controller-adjudication.md`。两路 PR review 均通过，无 accepted current fix。Accepted PR review commit 为 `50431ab2` 并已 push 到 draft PR #162。Final closeout artifact 为 `docs/reviews/wu-tools-01-f01-02-r1-final-closeout.md`。Issue closeout comment 已发布：https://github.com/noho/dayu-agent-r/issues/129#issuecomment-4762165431。PR body 使用 `Closes #129`，merge 会自动关闭 #129。当前进入 final-closeout-pass gate，等待用户 / maintainer 处理 draft PR #162；不得未经授权 mark ready、merge、close issue、request reviewers 或 delete branch。Merge PR #162 后，应从 `main` 拉取最新代码，再按本文档 next entry point 进入 WU-WAIT-01 / GitHub Issue #89。

### 设计与代码核对

- Engine 设计真源规定：Engine 只消费 `ToolExecutor.execute(...)` 的 bounded handshake outcome；长事务 awaiting、orphan cleanup、工具级取消和 batch 内执行策略属于 Host / ToolRuntime，不属于 Engine。
- Host 设计真源规定：`ToolAwaitingOutcome` 只能经 ToolRuntime Host awaiting accept path 写入 `TOOL_AWAITING`、`RUN_WAITING`、`ATTEMPT_SUSPENDED` 与 wait record；Engine `tool_awaiting` / `run_suspended` 只能作为确认或诊断，不创建 wait record。
- `dayu/fins/tools/download_tools.py`、`dayu/fins/tools/preprocess_tools.py` 与 `dayu/fins/tools/upload_tools.py` 当前在工具 callable 内调用 `runtime.start_observed_download(...)`、`runtime.start_observed_preprocess(...)`、`runtime.start_observed_upload(...)`，随后才返回 `ToolAwaitingOutcome`。
- `dayu/fins/ingestion_runtime.py` 当前 `start_observed_*` 会注册 process-local observation，并立即调用 `executor.submit(...)`。Host wait record 写入发生在 `dayu/host/tool_runtime.py` 的 `_accept_awaiting(...)` 之后，因此存在 external job 已启动但 Host wait truth 尚未 durable accepted 的窗口。
- `FinsIngestionJobStatus` 当前只有 `queued / running / cancelling / succeeded / failed / cancelled`，没有 prepared / activated 语义；`claim_running_or_cancelled(...)` 是 executor operation 内部进入 running 的 claim，不等价于 Host accepted-wait 后 activation。
- Fins wait adapter 当前已覆盖 `start_fins_download`、`start_fins_preprocess`、`start_fins_upload`，通过 lightweight observation handle poll completion；仅调整 poller 不能关闭 submit-before-accept root cause。

### 目标

- 设计并实现最小 two-phase activation：Fins awaiting tool 先 prepare / 登记可观察长事务，不 submit 后台 executor；Host awaiting accept 成功后通过 activation hook 触发 activate / submit。
- Host / ToolRuntime 必须只在 awaiting accept ack 成立后触发 activation；accept rejected、accept timeout、pre-accept cancellation 或 stale execution 不得启动外部长事务。
- Fins download / preprocess / upload awaiting tools 本轮直接迁移到 prepare / activate，不能只预留 Host hook。
- Activation 必须幂等；同一 prepared operation 重试 activation 不得 double-submit。
- Cancellation between prepare and activate 必须能关闭 prepared operation，不启动后台执行。
- Poller / wait adapter 对 prepared-but-not-active 状态必须有明确行为，不误报 terminal 或 lost；activation failure after accepted wait 必须有结构化收口。

### 非目标

- 不改变 Engine awaiting 公共模型，不让 Engine 拥有 activation、wait record 或 external job lifecycle truth。
- 不把 activation、execution context、cancellation token 或 Host governance id 暴露到 LLM-facing tool schema。
- 不为未来所有 provider 设计通用 lifecycle supervisor、durable follower ledger、跨 Attempt duplicate table、通用 wait alias schema 或新的 public await contract。
- 不在本条实现 #89 callback endpoint / auth / replay、#90 production poller loop / backoff / fencing / retry，或 #92 external job physical cancel / revoke / abandon 全量能力。
- 不用 Fins-only workaround 绕过 Host awaiting accept barrier；如新增 Host hook，必须是当前 ToolRuntime accepted-wait 后 activation 所需的最小层内契约。

### Plan Gate 约束

- Plan 必须明确 Host activation hook 放置位置、调用时机、失败收口、幂等语义和不暴露 LLM-facing schema 的证据。
- Plan 必须明确 Fins runtime prepare / activate API、prepared 状态表达、activation 幂等、pre-activation cancel、activation failure 和 poller prepared 状态行为。
- Plan 必须覆盖 download / preprocess / upload 三类 awaiting tools，不能只覆盖其中一个。
- Plan 必须按本文档 Slice 切分原则控制 gate 成本。小型跨模块 cleanup 默认上限为 3 个 implementation slices；若超过 3 个 slices，必须证明不能合并为更少的语义闭环。
- Plan 必须说明为什么没有过度设计，尤其是为什么没有引入通用 lifecycle supervisor、跨 provider activation 平台或新的 public await contract。

### 验收信号

- 受控测试能证明 awaiting accept 成功前不会 submit / activate Fins background job。
- Accept rejected / timeout / stale execution / pre-accept cancel 不会 activate prepared operation。
- Accepted wait 后 activation 成功会进入当前 Fins observation / poll / resolve path，download / preprocess / upload 均覆盖。
- Activation retry 不 double-submit；prepared operation 被取消或 abandoned 时不启动执行。
- Activation failure after accepted wait 有结构化 failed / lost / diagnostic 收口，且不让 Run 永久卡在无法解释的 WAITING。
- 受影响 Host / Fins tests、pyright 通过；涉及 Host / Engine contract 或 Fins runtime contract 的设计变化同步到设计真源和必要 README。

## WU-TOOLS-AWAIT-FANOUT-01 Host ToolRuntime Awaiting Fanout Governance Hardening

### 状态

GitHub Issue #111 当前为 OPEN。用户在 2026-06-21 裁决将本条作为工具调用治理执行正确性的默认下一步。Goal confirmation 已完成。Plan gate artifact 为 `docs/host/wu-tools-await-fanout-01-plan.md`。Plan review artifacts 为 `docs/reviews/wu-tools-await-fanout-01-plan-review-mimo.md` 与 `docs/reviews/wu-tools-await-fanout-01-plan-review-ds.md`，controller adjudication 为 `docs/reviews/wu-tools-await-fanout-01-plan-review-controller-adjudication.md`。Plan-fix artifact 为 `docs/reviews/wu-tools-await-fanout-01-plan-fix-codex.md`。Plan re-review artifacts 为 `docs/reviews/wu-tools-await-fanout-01-plan-rereview-mimo.md` 与 `docs/reviews/wu-tools-await-fanout-01-plan-rereview-ds.md`，controller adjudication 为 `docs/reviews/wu-tools-await-fanout-01-plan-rereview-controller-adjudication.md`。两路 re-review 均通过，0 个未修复 accepted finding，0 个新增 blocking finding。Accepted plan commit 为 `29b211d7`。Implementation artifact 为 `docs/reviews/wu-tools-await-fanout-01-implementation-codex.md`，唯一 implementation slice `S1 轻量 awaiting cleanup terminal marker` 已完成，focused tests 报告 `182 passed`，pyright 报告 0 errors。Code review artifacts 为 `docs/reviews/wu-tools-await-fanout-01-code-review-mimo.md` 与 `docs/reviews/wu-tools-await-fanout-01-code-review-ds.md`。Controller adjudication 为 `docs/reviews/wu-tools-await-fanout-01-code-review-controller-adjudication.md`。Fix artifact 为 `docs/reviews/wu-tools-await-fanout-01-fix-codex.md`，accepted findings DS-F01 与 DS-F03 已由 AgentCodex 处理，focused tests 报告 `184 passed`，pyright 报告 0 errors。Code re-review artifacts 为 `docs/reviews/wu-tools-await-fanout-01-code-rereview-mimo.md` 与 `docs/reviews/wu-tools-await-fanout-01-code-rereview-ds.md`，controller adjudication 为 `docs/reviews/wu-tools-await-fanout-01-code-rereview-controller-adjudication.md`。两路 code re-review 均通过，0 个未修复 accepted finding，0 个新增 blocking finding。Accepted slice commit 为 `2e5791c9`。Aggregate deepreview artifacts 为 `docs/reviews/wu-tools-await-fanout-01-aggregate-deepreview-mimo.md` 与 `docs/reviews/wu-tools-await-fanout-01-aggregate-deepreview-ds.md`，controller adjudication 为 `docs/reviews/wu-tools-await-fanout-01-aggregate-deepreview-controller-adjudication.md`。两路 aggregate deepreview 均通过，0 个 blocking finding；MiMo 的低风险 WU 表格状态同步 finding 已由本文档更新关闭。Accepted deepreview commit 为 `cf125c4c`。Draft PR #161 已创建：https://github.com/noho/dayu-agent-r/pull/161。`gh pr checks` reported no checks on branch `phase/wu-tools-await-fanout-01`。Final closeout artifact 为 `docs/reviews/wu-tools-await-fanout-01-final-closeout.md`，裁决无当前 #111 active residual risk；`AWAITING_FANOUT` production reachability 与 DS-F02 diagnostic visibility 仅作为 future-change guardrails 留痕，不作为本 WU residual 或后续 owner。当前进入 final-closeout-pass gate，等待用户 / maintainer 处理 draft PR #161；不得未经授权 mark ready、merge、close issue、request reviewers 或 delete branch。

### 设计与代码核对

- Host 设计真源规定 ToolRuntime / TruncationManager 是工具执行治理、截断、`fetch_more`、等待与重复调用治理 owner；工具事实必须走 Host accept barrier。
- Engine 设计真源规定 Engine 只通过 `ToolExecutor.execute(...)` 做 bounded handshake；batch 内执行策略、权限、审批、限流、内部 timeout、审计、长事务 awaiting、orphan cleanup 和工具级取消属于 Host / ToolRuntime。
- 当前 attempt-scoped duplicate governance 已覆盖同一 Attempt 内重复工具调用的 in-flight owner / waiter 基本窗口，但 #111 指出 awaiting 路径缺少 fanout 设计。
- 当前 Host waiting 状态迁移要求 awaiting canonical facts 由 ToolRuntime Host accept path 拥有；Engine `tool_awaiting` / `run_suspended` 只能作为 preview、diagnostic 或 idempotent confirmation，不能创建 wait record 或关闭 Attempt。
- #111 的直接问题是：duplicate owner 返回 `ToolAwaitingOutcome` 并创建 durable wait record 后，重复 waiter 不能简单再创建第二个 wait record，也不能没有 durable owner 地返回 waiting；否则 external job、resolve、cancel、late result 和 idempotency conflict 语义都会分裂。
- 2026-06-21 goal confirmation 补充约束：awaiting / Fins ingestion 方向刚从较重的 durable 设计收缩到当前薄 wait record + lightweight observation handle 实现。本 WU 的 plan 必须优先在 attempt-local duplicate governance、已有 awaiting accept ack、现有 wait record 与 RunInputBuilder resume material 上补齐 fanout 语义；不得重新引入重型 durable follower ledger、通用 wait alias schema、跨 Attempt durable duplicate table、外部 job activation 两阶段协议或新的 Host public await contract，除非代码直接证据证明没有轻量方案可满足 #111。

### 目标

- 设计并实现重复 awaiting owner / waiter 的单 owner fanout 语义。
- 同一 duplicate key 的 awaiting owner 只创建一个 durable wait record / external job owner；waiter 不重复启动外部 job。
- 明确 waiter 的 follower / alias / diagnostic 表达，或明确由 resume input / RunInputBuilder material 把 shared waiting result 表示为共享事实。
- `resolve_wait` 后，resume input 必须能让模型看到等待结果足以覆盖重复调用语义，不依赖模型天然记住上一 Attempt 的 tool call。
- 明确 cancel、late result、idempotency conflict、owner lost、external job lost 和 awaiting accept rejected / timeout 的收口规则。
- 增加 focused tests 覆盖重复 awaiting owner / waiter 并发、owner accepted waiting、owner awaiting accept rejected / timeout、resolve_wait 成功、cancel / late result。

### 非目标

- 不把 `ToolAwaitingOutcome` 简单当作 completed result 写入 duplicate accepted index。
- 不绕过 Host awaiting accept barrier。
- 不让 Engine、wait adapter 或 provider runtime 直接拥有 Host durable truth。
- 不在本条实现 #129 的 external job two-phase activation；本条只固定 duplicate awaiting fanout 语义。
- 不在本条实现 #89 / #90 / #92 的 production callback、poller 或 physical cancel 能力。
- 不重新扩大刚收缩过的 awaiting durable 设计；禁止以“未来通用 fanout”为理由新增重型 wait follower 表、durable duplicate ledger、跨进程等待者队列或新的 public await lifecycle contract。

### 依赖与后续

- 本条依赖现有 attempt-scoped duplicate governance、ToolRuntime awaiting accept barrier 和 wait record durable truth。
- 本条完成后，#129 two-phase activation plan 必须消费本条对 wait owner / follower / alias 的设计结论。
- #89 / #90 / #92 的 production WAIT hardening 不应先行定义与本条冲突的 wait owner 或 external job fanout 语义。
- #70 Tool Trace analyzer 可以并行 discussion，但 analyzer 只能报告 duplicate awaiting / fanout 证据或 limited signal，不能替代本条的 Host governance 修复。

### 验收信号

- 同一 Attempt 内重复 awaiting call 不会启动多个 external jobs，也不会创建语义冲突的多个 wait records。
- waiter 有可恢复、可审计、可诊断的 fanout 表达；不是只存在于内存里的临时等待者。
- wait resolution 后的 resume material 能表达 shared waiting result，且不泄漏 Host internal refs 到 LLM-facing 文本。
- cancel、late result、owner lost、accept rejected / timeout 都有结构化 diagnostic 或 governed outcome。
- 受影响 tests 与 pyright 通过；若修改 Host / Engine public contract 或 EventLog / wait schema，先更新 `docs/host/design.md` 和必要 README。

## WU-TOOLS-01-F03-R4 Tools Discovery Spec Semantics Cleanup

### 状态

GitHub Issue #133 已 CLOSED，PR 160 已于 2026-06-21 merge。本 WU 从 WU-TOOLS-01-F03 final closeout residual risk 转入独立实施入口，goal confirmation 已由用户确认，plan gate 已完成，plan review completed with blocking findings，plan-fix gate 已完成，plan re-review passed，accepted plan commit 已创建，Slice 1 implementation / code review / accepted slice commit 已完成，Slice 2 已由 controller 裁决为 covered by Slice 1，Slice 3 implementation / code review / accepted slice commit 已完成，Slice 4 implementation / code review / accepted slice commit 已完成，Slice 5 implementation / code review / fix / re-review / accepted slice commit 已完成，Slice 6 implementation / code review / accepted slice commit 已完成，Slice 7 final validation 已完成，aggregate deepreview 已完成且无阻塞 finding，accepted deepreview commit 已创建，ready-to-open-draft-PR gate 已完成，push gate 已完成，draft PR 160 已创建，PR review 已完成且无需当前修复，accepted PR review commit 已创建并推送，draft-PR-pass 已达成，final closeout comment 已发布，当前已完成，不再作为 active implementation entry point。

Plan artifact:

- `docs/host/host-issues/wu-tools-01-f03-r4-tools-discovery-spec-plan.md`

Plan review artifacts:

- `docs/reviews/wu-tools-01-f03-r4-plan-review-mimo.md` by AgentMiMo, verdict `pass-with-findings`, blocking findings `1`
- `docs/reviews/wu-tools-01-f03-r4-plan-review-ds.md` by AgentDS, verdict `pass-with-findings`, blocking findings `2`

Controller plan-review judgment:

- `accepted`：MiMo F01 — plan 必须明确 `_fins_wait_adapter_registry_from_provider_configs` 使用 effective provider configs，或复用同一 relative-to-absolute workspace 解析逻辑；否则 packaged `workspace/` 会让 wait adapter 构造直接失败。
- `accepted`：MiMo F02 / DS F6 — plan 必须明确 `workspace/` 的解析基准为 Service request/runtime `workspace_root` 下的 `workspace/`，并给出具体测试断言；不得把该决策留给 implementation owner 猜测。
- `accepted`：MiMo F03 / DS F5 — upload 默认注册后可能扩大 scene tool exposure，plan 必须加入默认 scene manifest / tool selection 验证步骤。
- `accepted`：DS F1 — Doc provider 决策必须收敛为单一路径：packaged `doc-tools.enabled=false`，且 Doc provider 在 enabled + empty `allowed_paths` 时 fail fast with business-specific error；implementation agent 不得在两个方案之间自行裁决。
- `accepted`：DS F2 — `ToolsDiscoveryProviderSpec.allow_empty` 删除与 `host_assembly.py` 映射删除必须位于同一可独立验证 slice，避免 slice 间代码库不可导入。
- `accepted`：DS F3 — plan 必须读取并记录 Web provider 是否存在空输出路径；若存在，需在 plan 中裁决处理方式。
- `accepted`：DS F4 — plan 必须显式确认 Fins download / preprocess providers 在有效 config 下是否返回非空 definitions。

Plan-fix artifact:

- `docs/reviews/wu-tools-01-f03-r4-plan-fix-codex.md` by AgentCodex

Plan-fix summary:

- MiMo F01：已修复，plan 要求 wait adapter construction 消费与 discovery 同一 effective provider config tuple，raw packaged `workspace/` 不得进入 `_fins_wait_adapter_registry_from_provider_configs(...)`。
- MiMo F02 / DS F6：已修复，plan 固定相对 Fins `workspace_root` 语义：Service request/runtime `workspace_root=/path/to/project` 加 packaged `workspace/` 解析为 `/path/to/project/workspace`。
- MiMo F03 / DS F5：已修复，plan 将默认 scene upload exposure 纳入当前 WU implementation item，要求默认非 upload scenes 不再通过 broad `fins` tag 选中 `start_fins_upload`。
- DS F1：已修复，Doc provider 单一路径为 packaged `doc-tools.enabled=false`，且 enabled Doc provider missing / empty `allowed_paths` 必须 Doc-specific fail fast。
- DS F2：已修复，plan 合并 provider-level `allow_empty` config 删除、`ToolsDiscoveryProviderSpec.allow_empty` 删除与 `host_assembly.py` mapping 删除到同一个可独立验证 Slice 1。
- DS F3：已修复，plan 记录 Web provider 直接证据：`dayu.tools.web:discover_tools` 到 `dayu/tools/web/provider.py`，definitions 必须为 `search_web` / `fetch_web_page`，无正常空输出路径。
- DS F4：已修复，plan 记录 Fins download / preprocess provider 在有效 absolute `workspace_root` 下各返回一个 awaiting tool definition。

Plan re-review artifacts:

- `docs/reviews/wu-tools-01-f03-r4-plan-rereview-mimo.md` by AgentMiMo, verdict `pass`, blocking findings `0`
- `docs/reviews/wu-tools-01-f03-r4-plan-rereview-ds.md` by AgentDS, verdict `pass`, blocking findings `0`

Plan re-review final finding status:

- MiMo F01：已修复。
- MiMo F02 / DS F6：已修复。
- MiMo F03 / DS F5：已修复。
- DS F1：已修复。
- DS F2：已修复。
- DS F3：已修复。
- DS F4：已修复。
- MiMo F04：non-blocking low severity；implementation 时核对 scene manifest 显式 `tool_names` 完整性，Slice 4 验证命令可捕获遗漏，不阻塞 accepted plan commit。

Accepted plan commit:

- `fe212365` (`gateflow: accept plan for WU-TOOLS-01-F03-R4`)

Slice 1 implementation artifact:

- `docs/reviews/wu-tools-01-f03-r4-slice1-implementation-codex.md` by AgentCodex

Slice 1 implementation validation:

- `pytest tests/runtime/test_config_loader.py -q`: `41 passed`
- `pytest tests/runtime/test_tools_discovery.py tests/runtime/test_tools_discovery_digest.py -q`: `19 passed`
- `pytest tests/service/test_host_assembly.py tests/runtime/test_smoke_host_public_multiturn_assembly.py -q`: `54 passed`, 3 upstream `edgar` deprecation warnings
- `pytest tests/tools/test_combined_tools_acceptance.py -q`: `8 passed`, 3 upstream `edgar` deprecation warnings
- `pyright dayu tests utils`: `0 errors, 0 warnings, 0 informations`

Slice 1 code review focus:

- Verify whether implementing Fins relative `workspace_root` effective resolution in `dayu/service/host_assembly.py` is an acceptable Slice 1 dependency needed to keep Service discovery callable after packaged `"workspace/"`, or a scope overrun that must be split / adjusted before acceptance.
- Verify whether updating `utils/diagnose_web_access.py` is an acceptable signature-update fallout from `ToolsDiscoveryProviderSpec.allow_empty` removal, despite `utils/` not being part of production/test allowed files in the original dispatch.
- Verify packaged `financial-upload-tools.enabled=false` is acceptable as a temporary Slice 1 bridge until the later upload provider slice removes `allowed_upload_roots` behavior and restores intended default registration.

Slice 1 code review artifacts:

- `docs/reviews/wu-tools-01-f03-r4-slice1-code-review-mimo.md` by AgentMiMo, verdict `pass`, blocking findings `0`
- `docs/reviews/wu-tools-01-f03-r4-slice1-code-review-ds.md` by AgentDS, verdict `pass-with-findings`, blocking findings `0`

Controller Slice 1 code-review judgment:

- `accepted`：DS-F01 — `_effective_fins_workspace_root_config_value()` 的非字符串、空字符串 / 全空白字符串、相对路径但缺少 runtime `workspace_root` 三条错误边界应由直接测试锁定。Controller 已在 `tests/service/test_host_assembly.py` 补测试并关闭。
- `rejected-with-reason`：DS-F02 — `workspace_root: null` 且 runtime `workspace_root=None` 时保留原始 config、由 provider / wait adapter fail fast 是 accepted plan 的有意决策，不作为 Slice 1 缺陷。
- `deferred-with-owner`：DS-F03 — packaged `financial-upload-tools.enabled=false` 是 Slice 1 临时桥接，owner 为本 WU Slice 4；Slice 4 必须移除 upload provider 内部 `allowed_upload_roots` 行为并恢复默认注册。
- `informational`：DS-F04 — `dict()` 浅复制与 frozen dataclass `replace(...)` 行为正确，已有测试覆盖原始 config 未被修改。
- `informational`：DS-F05 — `utils/diagnose_web_access.py` 修改是 `ToolsDiscoveryProviderSpec.allow_empty` 构造参数删除后的签名 fallout，可接受。
- `accepted`：MiMo review — 无实质性问题；Slice 1 可进入 accepted slice commit gate。

Slice 1 code-review fix validation:

- `pytest tests/service/test_host_assembly.py -q`: `51 passed`, 3 upstream `edgar` deprecation warnings
- `pyright dayu tests utils`: `0 errors, 0 warnings, 0 informations`

Accepted Slice 1 commit:

- `c785f218` (`gateflow: accept WU-TOOLS-01-F03-R4 slice 1`)

Slice 2 controller closure:

- `closed-covered-by-slice-1`：Accepted Slice 1 commit `c785f218` already implemented Service effective Fins workspace path resolution, `_effective_fins_workspace_root_config_value(...)`, wait adapter construction through the same effective provider config tuple, packaged `"workspace/"` resolution tests, raw config immutability tests, and direct error-boundary tests. No separate Slice 2 implementation dispatch is needed; next implementation slice is Slice 3.

Slice 3 implementation artifact:

- `docs/reviews/wu-tools-01-f03-r4-slice3-implementation-codex.md` by AgentCodex

Slice 3 implementation validation:

- `pytest tests/fins/test_fins_storage_provider.py tests/fins/test_fins_ingestion_tools.py tests/tools/test_combined_tools_acceptance.py -q`: `77 passed`, 3 upstream `edgar` deprecation warnings
- `pyright dayu tests utils`: `0 errors, 0 warnings, 0 informations`
- `rg -n "include_read_tools|_CONFIG_INCLUDE_READ_TOOLS_FIELD|_parse_bool_default" -g '*.py' dayu tests utils`: no production or test Python references

Slice 3 code review focus:

- Verify `dayu/fins/tools/provider.py` no longer has any internal read-provider disable path and enabled provider always requires explicit absolute `workspace_root`, parses limits, builds `DefaultFinsRuntime`, and returns exactly nine read tool definitions.
- Verify deleting the explicit `tests/runtime/test_config_loader.py` string assertion for `include_read_tools` is acceptable because Slice 3 completion requires no production or test code references to that removed field, while Slice 1 already asserted packaged config cleanup.
- Verify minimal updates to `dayu/fins/README.md` and `tests/README.md` are required by AGENTS README triggers and are not an uncontrolled docs-slice overrun; stale `dayu/config/README.md` content remains intentionally deferred to the later docs slice.
- Verify remaining `include_read_tools` grep hits are only historical plans/review artifacts, current WU control/plan text, or deferred docs content; no active production/test Python path still consumes the field.

Slice 3 code review artifacts:

- `docs/reviews/wu-tools-01-f03-r4-slice3-code-review-mimo.md` by AgentMiMo, verdict `pass`, blocking findings `0`
- `docs/reviews/wu-tools-01-f03-r4-slice3-code-review-ds.md` by AgentDS, verdict `pass`, blocking findings `0`

Controller Slice 3 code-review judgment:

- `accepted`：AgentMiMo and AgentDS both confirmed the read provider no longer has an `include_read_tools` branch, enabled provider parses limits / absolute workspace root, creates `DefaultFinsRuntime`, validates definitions, and returns exactly nine read tools.
- `accepted`：Deleting the explicit `tests/runtime/test_config_loader.py` string assertion for `include_read_tools` is acceptable. Slice 1 already covered packaged config cleanup, and Slice 3 completion requires no production/test Python references to the removed field.
- `accepted`：Minimal `dayu/fins/README.md` and `tests/README.md` updates are required by AGENTS README triggers and directly match the changed Fins read provider semantics.
- `deferred-with-owner`：`dayu/config/README.md` still contains old config text; owner is WU-TOOLS-01-F03-R4 Slice 6 docs synchronization.
- `deferred-with-owner`：DS noted non-string / blank-string `workspace_root` provider parse boundaries are not directly tested; existing guard covers them and severity is low. Owner is Slice 7 final validation if broader provider parse boundary hardening is still needed.

Slice 3 controller validation:

- `pytest tests/fins/test_fins_storage_provider.py tests/fins/test_fins_ingestion_tools.py tests/tools/test_combined_tools_acceptance.py tests/runtime/test_config_loader.py -q`: `118 passed`, 3 upstream `edgar` deprecation warnings
- `pyright dayu tests utils`: `0 errors, 0 warnings, 0 informations`

Accepted Slice 3 commit:

- `3f7fd44a` (`gateflow: accept WU-TOOLS-01-F03-R4 slice 3`)

Slice 4 implementation artifact:

- `docs/reviews/wu-tools-01-f03-r4-slice4-implementation-codex.md` by AgentCodex

Slice 4 implementation validation:

- `pytest tests/fins/test_fins_ingestion_tools.py -q`: `47 passed`, 3 upstream `edgar` deprecation warnings
- `pytest tests/runtime/test_scene_prepare.py tests/runtime/test_smoke_host_public_multiturn_assembly.py -q`: `38 passed`, 3 upstream `edgar` deprecation warnings
- `pytest tests/tools/test_combined_tools_acceptance.py -q`: `8 passed`, 3 upstream `edgar` deprecation warnings
- `pytest tests/runtime/test_config_loader.py -q`: `41 passed`
- `pyright dayu tests utils`: `0 errors, 0 warnings, 0 informations`
- `git diff --check`: no output
- `rg -n "allowed_upload_roots|_CONFIG_ALLOWED_UPLOAD_ROOTS_FIELD|parse_allowed_upload_roots_config" dayu tests utils`: only expected negative assertion in `tests/runtime/test_config_loader.py`

Slice 4 code review focus:

- Verify `dayu/fins/tools/upload_provider.py` no longer has an empty-output branch or `allowed_upload_roots` parser and always registers `start_fins_upload` after parsing absolute effective `workspace_root`.
- Verify `dayu/fins/tools/upload_tools.py` removed allowlist containment but still validates action/file count, existing regular file, and non-empty file before starting observation; delete still forbids files.
- Verify repository/write boundary was not weakened: local file path is source input only, output path remains governed by `FinsIngestionRuntime` / repository-backed runtime; new tests should not rely on obsolete job-store internals.
- Verify packaged `financial-upload-tools.enabled=true` is correct after removing provider allowlist behavior and no `allowed_upload_roots` returns to config.
- Verify default manifests no longer select `start_fins_upload` via broad `"fins"` / `"ingestion"` tags, while intended read/download/preprocess and web tools remain selected. Scene `tool_selection.allow_empty` must remain unchanged.
- Verify LLM-facing upload schema text no longer claims configured upload roots and remains self-explanatory.
- Verify README updates are minimal direct-trigger sync, not uncontrolled docs-slice overrun.

Slice 4 code review artifacts:

- `docs/reviews/wu-tools-01-f03-r4-slice4-code-review-mimo.md` by AgentMiMo, verdict `pass`, blocking findings `0`
- `docs/reviews/wu-tools-01-f03-r4-slice4-code-review-ds.md` by AgentDS, verdict `pass`, blocking findings `0`

Controller Slice 4 code-review judgment:

- `accepted`：AgentMiMo and AgentDS both confirmed upload provider no longer parses `allowed_upload_roots`, no longer has an empty-output branch, and enabled provider registers `start_fins_upload` after valid absolute effective `workspace_root`.
- `accepted`：Upload tool no longer applies provider-local allowlist containment, but still validates action/file count, existing regular file, non-empty file, and delete-with-files before observation start.
- `accepted`：Packaged `financial-upload-tools.enabled=true` is correct after removing the temporary Slice 1 bridge; packaged upload config still has no `allowed_upload_roots`.
- `accepted`：Default manifests no longer select upload through broad `"fins"` / `"ingestion"` tags, and `tool_selection.allow_empty` remains unchanged.
- `accepted`：LLM-facing upload schema text no longer mentions configured upload roots and remains self-explanatory.
- `accepted`：README updates are AGENTS-triggered minimal factual sync for changed config / Fins / tests behavior.
- `deferred-with-owner`：DS-F1 symlink path behavior has no direct test. Current implementation follows symlinks through `Path.resolve(...)`, which is acceptable. Owner is Slice 7 final validation / future provider path-boundary hardening if needed.
- `deferred-with-owner`：DS-F2 scene test uses a hardcoded default scene id list. Current package manifests are covered and grep-confirmed; owner is Slice 7 final validation if dynamic manifest discovery becomes necessary.
- `rejected-with-reason`：DS-F3 asks for deeper repository write-boundary penetration in the new source-side upload test. This is not a Slice 4 defect: the test intentionally proves local source path acceptance/no source-side governance side effects, while destination repository writes remain covered by existing Fins upload pipeline / storage tests.

Slice 4 controller validation:

- `pytest tests/fins/test_fins_ingestion_tools.py tests/runtime/test_scene_prepare.py tests/runtime/test_smoke_host_public_multiturn_assembly.py tests/tools/test_combined_tools_acceptance.py tests/runtime/test_config_loader.py -q`: `134 passed`, 3 upstream `edgar` deprecation warnings
- `pyright dayu tests utils`: `0 errors, 0 warnings, 0 informations`
- `rg -n "allowed_upload_roots|_CONFIG_ALLOWED_UPLOAD_ROOTS_FIELD|parse_allowed_upload_roots_config" dayu tests utils`: only `tests/runtime/test_config_loader.py` negative assertion
- `rg -n '"fins"|fins-upload|"ingestion"|start_fins_upload' dayu/config/prompts/manifests`: no matches

Accepted Slice 4 commit:

- `4514f550` (`gateflow: accept WU-TOOLS-01-F03-R4 slice 4`)

Slice 5 implementation artifact:

- `docs/reviews/wu-tools-01-f03-r4-slice5-implementation-codex.md` by AgentCodex

Slice 5 implementation validation:

- `pytest tests/runtime/test_config_loader.py tests/tools/test_doc_tools_provider.py tests/fins/test_fins_storage_provider.py -q`: `97 passed`, 3 upstream `edgar` deprecation warnings
- `pytest tests/tools/test_combined_tools_acceptance.py -q`: `8 passed`, 3 upstream `edgar` deprecation warnings
- `pyright dayu tests utils`: `0 errors, 0 warnings, 0 informations`

Slice 5 code review focus:

- Verify enabled Doc provider with missing or empty `allowed_paths` raises the Doc-specific `ValueError` at provider boundary and no longer returns empty `definitions`.
- Verify Doc provider limits parsing remains provider-owned, ConfigLoader does not parse provider-specific limits, and packaged config values remain explicitly asserted.
- Verify new Doc explicit limits test actually checks schema maximums and truncate specs produced from config, not dataclass defaults.
- Verify new Fins explicit limits test checks all ToolDefinition-visible limits and correctly treats `processor_cache_max_entries` as runtime cache input that is not visible in `ToolDefinition`.
- Verify README update is minimal tests README sync and not a docs/design Slice 6 overrun.

Slice 5 code review artifacts:

- `docs/reviews/wu-tools-01-f03-r4-slice5-code-review-mimo.md` by AgentMiMo, verdict `accept-with-conditions`, blocking findings `0`
- `docs/reviews/wu-tools-01-f03-r4-slice5-code-review-ds.md` by AgentDS, verdict `pass`, blocking findings `0`

Controller Slice 5 code-review judgment:

- `accepted`：MiMo F1 — Fins explicit limits test should assert `processor_cache_max_entries` is not projected into any ToolDefinition truncate limits. This directly matches Slice 5 focus on treating that field as runtime-only.
- `accepted`：MiMo F2 — Partial limits fallback to dataclass defaults is a plan invariant and should have a focused test. Low risk but cheap to cover in the same fix.
- `accepted`：DS review — no blocking findings; DS residual risks are informational and consistent with the accepted fix items.

Slice 5 fix artifact:

- `docs/reviews/wu-tools-01-f03-r4-slice5-fix-codex.md` by AgentCodex

Slice 5 fix validation:

- `pytest tests/tools/test_doc_tools_provider.py tests/fins/test_fins_storage_provider.py -q`: `57 passed`, 3 upstream `edgar` deprecation warnings
- `pytest tests/runtime/test_config_loader.py tests/tools/test_combined_tools_acceptance.py -q`: `49 passed`, 3 upstream `edgar` deprecation warnings
- `pyright dayu tests utils`: `0 errors, 0 warnings, 0 informations`

Slice 5 fix re-review artifacts:

- `docs/reviews/wu-tools-01-f03-r4-slice5-fix-rereview-mimo.md` by AgentMiMo, verdict `accept`, F1 closed, F2 closed
- `docs/reviews/wu-tools-01-f03-r4-slice5-fix-rereview-ds.md` by AgentDS, verdict `pass`, F1 closed, F2 closed

Controller Slice 5 final judgment:

- `closed`：MiMo F1 — fixed by asserting `processor_cache_max_entries` is absent from every Fins ToolDefinition `truncate.limits` while preserving all visible limit assertions.
- `closed`：MiMo F2 — fixed by adding partial Doc limits fallback coverage: explicit `list_files_max=99` overrides default, missing visible Doc limits fall back to `DocToolLimits()` defaults.
- `accepted`：No production code was changed by the fix; review agents found no regressions.

Slice 5 controller validation:

- `pytest tests/runtime/test_config_loader.py tests/tools/test_doc_tools_provider.py tests/fins/test_fins_storage_provider.py tests/tools/test_combined_tools_acceptance.py -q`: `106 passed`, 3 upstream `edgar` deprecation warnings
- `pyright dayu tests utils`: `0 errors, 0 warnings, 0 informations`

Accepted Slice 5 commit:

- `ee5f2e19` (`gateflow: accept WU-TOOLS-01-F03-R4 slice 5`)

Slice 6 implementation artifact:

- `docs/reviews/wu-tools-01-f03-r4-slice6-implementation-codex.md` by AgentCodex

Slice 6 implementation validation:

- `python -m pyright dayu/ tests/ utils/`: `0 errors, 0 warnings, 0 informations`
- `git diff --check -- dayu/config/README.md dayu/fins/README.md docs/host/design.md tests/README.md docs/reviews/wu-tools-01-f03-r4-slice6-implementation-codex.md`: no output
- Active README/design grep: remaining `allow_empty` hits are scene `tool_selection.allow_empty` independent semantics or old provider-level field rejection tests; `include_read_tools` and `allowed_upload_roots` no longer appear as current active config.

Slice 6 code review focus:

- Verify `docs/host/design.md` no longer describes provider-level `allow_empty` as current `tool_discovery.json` field and accurately states enabled provider empty output is configuration error.
- Verify `dayu/config/README.md` documents packaged `workspace/` relative default, Service effective absolute resolution, explicit Doc/Fins limits, `doc-tools.enabled=false`, no `include_read_tools`, no upload `allowed_upload_roots`, and scene selection avoiding broad Fins tag upload exposure.
- Verify `dayu/fins/README.md` describes all four Fins providers requiring effective absolute `workspace_root`, provider-level `enabled` as read switch, upload local source file authorization not being provider-owned, and repository writes staying under `dayu.fins.storage`.
- Verify `tests/README.md` coverage descriptions match current tests and do not describe old allowlist / empty-output behavior as current.
- Verify no README/design process/gate/PR status leaked into stable docs.

Slice 6 code review artifacts:

- `docs/reviews/wu-tools-01-f03-r4-slice6-code-review-mimo.md` by AgentMiMo, verdict `accept`, blocking findings `0`
- `docs/reviews/wu-tools-01-f03-r4-slice6-code-review-ds.md` by AgentDS, verdict `pass`, blocking findings `0`

Controller Slice 6 code-review judgment:

- `accepted`：Design and README text now match implemented facts for provider fields, empty provider output, Fins `workspace/` effective resolution, Doc/Fins limits, `doc-tools.enabled=false`, upload allowlist removal, and scene selection separation.
- `accepted`：Remaining active `allow_empty` mentions are scene `tool_selection.allow_empty` independent semantics or old provider-level field rejection test coverage. `include_read_tools` and `allowed_upload_roots` are absent from active current README/design descriptions.
- `accepted`：No process/gate/PR status leaked into stable README/design documents.

Slice 6 controller validation:

- `pyright dayu tests utils`: `0 errors, 0 warnings, 0 informations`
- `git diff --check` on Slice 6 docs/review files: no output
- Active docs grep for `allow_empty|include_read_tools|allowed_upload_roots`: remaining matches are allowed scene/test-rejection classifications only.

Accepted Slice 6 commit:

- `d8db0b49` (`gateflow: accept WU-TOOLS-01-F03-R4 slice 6`)

Slice 7 final validation artifact:

- `docs/reviews/wu-tools-01-f03-r4-slice7-final-validation-codex.md` by AgentCodex

Slice 7 final validation changes:

- `tests/runtime/test_scene_assets_migration.py` fake tool catalog updated to include the current explicit default-scene Fins read / download / preprocess tool names after Slice 4 removed broad `"fins"` / `"ingestion"` default selection.

Slice 7 final validation:

- `pytest tests/runtime/test_config_loader.py tests/runtime/test_tools_discovery.py tests/runtime/test_tools_discovery_digest.py -q`: `60 passed`
- `pytest tests/service/test_host_assembly.py tests/runtime/test_smoke_host_public_multiturn_assembly.py -q`: `58 passed`, 3 upstream `edgar` deprecation warnings
- `pytest tests/fins/test_fins_storage_provider.py tests/fins/test_fins_ingestion_tools.py -q`: `70 passed`, 3 upstream `edgar` deprecation warnings
- `pytest tests/runtime/test_scene_prepare.py -q`: `31 passed`
- `pytest tests/tools/test_doc_tools_provider.py tests/tools/test_combined_tools_acceptance.py -q`: `42 passed`, 3 upstream `edgar` deprecation warnings
- `pytest tests/runtime/test_scene_assets_migration.py -q`: `7 passed`
- `pytest tests/fins/test_sec_downloader.py::test_sec_request_debug_logs_success_response -q`: `1 passed`
- `pytest tests/runtime tests/service tests/fins tests/tools -q --ignore=tests/tools/web/test_smoke_web_ci.py`: `866 passed, 1 skipped, 3 upstream edgar deprecation warnings`
- Historical `pytest tests/tools/web -q` result before web smoke reconciliation: `75 passed, 1 failed, 3 upstream edgar deprecation warnings`; failing test was `tests/tools/web/test_smoke_web_ci.py::test_default_run_executes_local_html_pdf_and_browser_cases`, where the test asserted diagnostic log text in stdout instead of pytest captured log.
- Post-reconciliation `python utils/smoke_web_ci.py --output-dir workspace/output/web_smoke/manual-wu-tools-f03-r4-final --run-label manual-wu-tools-f03-r4-final`: `SMOKE STATUS passed`, `SMOKE EXIT_CODE 0`, `SMOKE FAILURES 0`.
- Post-reconciliation `pytest tests/tools/web -q`: `76 passed, 3 upstream edgar deprecation warnings`.
- `pyright dayu tests utils`: `0 errors, 0 warnings, 0 informations`
- `rg -n "include_read_tools|allowed_upload_roots" dayu tests README.md`: only `allowed_upload_roots` hit is the packaged config negative assertion in `tests/runtime/test_config_loader.py`; `include_read_tools` has no active production/test/README hits.
- `rg -n "workspace_root\": null" dayu/config/tool_discovery.json tests`: no matches.
- `rg -n "\"allow_empty\"|allow_empty" dayu/config dayu/runtime dayu/service dayu/fins dayu/tools tests README.md`: remaining hits are scene `tool_selection.allow_empty`, runtime internal `ToolBundle._allow_empty`, direct event string validation, and old provider-level field rejection tests / documentation.

Slice 7 residual risk:

- No active WU-TOOLS-01-F03-R4 residual risk remains after reconciliation. Fresh web smoke passed after removing the obsolete smoke overlay `allow_empty` field, and the web smoke test now asserts diagnostic logs through pytest log capture instead of stdout.

Aggregate deepreview artifacts:

- `docs/reviews/wu-tools-01-f03-r4-aggregate-deepreview-mimo.md` by AgentMiMo, verdict `pass`, blocking findings `0`
- `docs/reviews/wu-tools-01-f03-r4-aggregate-deepreview-ds.md` by AgentDS, verdict `pass`, blocking findings `0`

Aggregate deepreview validation:

- AgentMiMo reran focused tests, broad affected suite excluding the then-classified web smoke caveat, pyright, and stale-field grep; result `pass`.
- AgentDS reran focused tests, web smoke caveat confirmation, broad affected suite excluding the then-classified web smoke caveat, pyright, stale-field grep, and scene manifest grep; result `pass`.

Controller aggregate deepreview judgment:

- `accepted`：AgentMiMo found no substantive issues and confirmed all seven WU success dimensions: provider-level `allow_empty` removal, `include_read_tools` removal, Fins `workspace/` effective resolution, Doc/Fins packaged limits, upload `allowed_upload_roots` removal, default scene upload non-exposure, and docs/tests/control semantic consistency.
- `rejected-with-reason`：AgentDS F-01 notes `ToolBundle._allow_empty=True` has insufficient semantic distinction. This is not a current defect: `_allow_empty=True` is only used to construct the legitimate zero-enabled-provider empty bundle, while enabled provider output still passes `_validate_provider_output(...)` and cannot return empty definitions. No code change is warranted in this WU.
- `rejected-with-reason`：AgentDS F-02 notes double `enabled` filtering in `ToolsDiscovery.discover(...)` and `discover_from_bindings(...)`. This is an intentional defensive boundary for the public `discover_from_bindings(...)` method and does not create incorrect behavior or maintenance risk requiring a fix.
- `accepted`：No active WU-TOOLS-01-F03-R4 residual risk remains after residual reconciliation.

Accepted deepreview commit:

- `3463ae9d` (`gateflow: accept deepreview for WU-TOOLS-01-F03-R4`)

Draft PR readiness artifact:

- `docs/reviews/wu-tools-01-f03-r4-draft-pr-readiness-codex.md` by AgentCodex

Draft PR readiness decision:

- Branch `phase/wu-tools-01-f03-r4` contains only WU-TOOLS-01-F03-R4 gate commits from `fe212365` through `3463ae9d`.
- All approved slices and aggregate deepreview are complete; no accepted finding requires fix / re-review.
- Validation is recorded: focused WU suites passed, `pyright dayu tests utils` passed, broad affected suite excluding the historical web smoke caveat passed, and post-reconciliation `tests/tools/web` plus fresh web smoke passed.
- No active WU-TOOLS-01-F03-R4 residual risk remains after residual reconciliation.
- GitHub issue-133 is CLOSED after PR 160 merged on 2026-06-21. The six requested Tools Discovery spec items were implemented, tested, and documented; the PR body used `Closes #133` and listed deferred owners.

Draft PR:

- PR 160: `https://github.com/noho/dayu-agent-r/pull/160`
- Branch pushed: `github/phase/wu-tools-01-f03-r4`
- Base: `main`
- Draft status: draft
- Issue association: PR body uses `Closes #133` and lists deferred owners.

PR review artifacts:

- `docs/reviews/wu-tools-01-f03-r4-pr-review-mimo.md` by AgentMiMo, verdict `pass`, blocking findings `0`
- `docs/reviews/wu-tools-01-f03-r4-pr-review-ds.md` by AgentDS, verdict `pass-with-findings`, blocking findings `0`

Controller PR review judgment:

- `accepted`：AgentMiMo verified PR 160 metadata, body, issue-133 completion, residual owners, diff scope, validation claims, and stale-field grep; no issues found.
- `rejected-with-reason`：AgentDS F01 notes `start_fins_upload.files` description no longer carries path authorization semantics. This is not a current defect. The accepted design deliberately removed provider-local upload allowlists, and the current tool schema truthfully states the active tool boundary: files must be existing non-empty regular files. Adding generic "system administrator controls allowed directories" wording before Host / policy owns a concrete contract would create an implicit rule with no enforcement source.
- `accepted`：PR body `Closes #133` is correct because all six issue-133 requested Tools Discovery spec changes are implemented, tested, and documented. Deferred risks are separately owned and do not leave issue-133 partially implemented.
- `accepted`：No active WU-TOOLS-01-F03-R4 residual risk remains after residual reconciliation; the historical web smoke caveat has been rechecked and fixed by aligning the smoke overlay and test assertions with current logging/config semantics.
- `accepted`：User-requested process improvement was written into the Slice 切分原则 section: small cross-module cleanup work should default to 2-3 semantic slices and any plan exceeding 3 implementation slices must justify why the work cannot be merged into those verification loops.

Accepted PR review commit and final push:

- `ecf83c5f` (`gateflow: accept PR review for WU-TOOLS-01-F03-R4`)
- Pushed to `github/phase/wu-tools-01-f03-r4`; PR 160 head after PR review pass was `ecf83c5f13d4b74d7f58f120c46bac3fa389c64f`.

Final closeout artifact:

- `docs/reviews/wu-tools-01-f03-r4-final-closeout-codex.md` by AgentCodex

Final closeout status:

- Draft PR URL: `https://github.com/noho/dayu-agent-r/pull/160`
- Issue link status: PR body uses `Closes #133`, correctly closing issue-133 on merge because all six requested spec changes are complete.
- Issue closeout comment status: posted to GitHub issue-133 at `https://github.com/noho/dayu-agent-r/issues/133#issuecomment-4760536817`.
- Work unit completion status: completed; PR 160 merged on 2026-06-21 and issue #133 is closed.

当前裁决来自 controller 对 `docs/host/design.md`、`docs/engine/design.md`、`dayu/config/tool_discovery.json`、`dayu/runtime/tools_discovery.py`、`dayu/runtime/config_loader.py`、`dayu/service/host_assembly.py`、Fins / Doc provider、Fins upload tool、Fins storage repository 与 OLD `/Users/leo/workspace/dayu-agent` 配置的代码核对。

### 目标

- 收敛 Tools Discovery spec 语义，删除 provider-level `allow_empty` 字段。空工具输出不再由通用 runtime 布尔开关授权；provider 是否启用由 `enabled` 表达，provider 自身业务配置必须直接决定是否暴露工具或 fail fast。
- 删除 Fins read provider 的 `include_read_tools` 字段。`financial-read-tools` 是独立 provider，启停必须只通过 provider-level `enabled` 表达，不保留 provider 内二级开关。
- 将 Fins workspace root packaged 默认值从 `null` 改为显式 `workspace/`。ConfigLoader 只原样读取配置；Service / composition root 负责把相对 workspace path 解析为 effective absolute path；Fins provider 继续只接收 absolute path，不自行猜 cwd、环境变量或 workspace。
- 将 OLD `doc_tool_limits` 与 `fins_tool_limits` 的默认值迁移到 `dayu/config/tool_discovery.json` 的 `doc-tools.config.limits` 与 `financial-read-tools.config.limits`，让 packaged config 自解释；provider dataclass 默认值只能作为代码层 fallback / 测试构造便利，不作为 packaged 默认配置唯一真源。
- 删除 `financial-upload-tools.config.allowed_upload_roots` 与上传工具本地文件 allowlist 限制。当前裁决为：本地文件读取暂不由 tool provider 自行授权或限制，未来权限治理统一进入 Host / policy 设计，不在工具内部保留一套并行 allowlist。
- 保持 Fins repository 写入目标边界：上传写入仍必须通过 `dayu.fins.storage` 仓储协议和 repository implementation；LLM / tool caller 不得指定仓储写入目录或绕过 repository。
- 同步更新相关测试、README 和设计 / 总控文档，使默认配置、typed config、Service effective config、provider 行为和文档语义一致。

### 非目标

- 不实现 Host 统一权限系统、文件访问策略、sandbox、capability token 或 per-tool authorization policy；upload 本地文件读取权限治理只作为后续 Host / policy 方向记录，不在本 WU 落地。
- 不把工具发现、业务工具注册、provider lifecycle 或 Fins workspace 推断放进 Host / Engine。Host / Engine 仍不读取 `tool_discovery.json`，不 import Fins / Doc / Web provider。
- 不保留旧 schema 兼容读取；本 WU 按全新 `tool_discovery.json` schema 起库处理，除非后续用户明确要求兼容迁移。
- 不修改 scene manifest 的 `tool_selection.allow_empty` 语义；该字段属于 scene 工具选择空匹配控制，不是 ToolsDiscovery provider 空输出控制。
- 不改变 Host public request / response dataclass、Engine `AgentRunRequest`、ToolRuntime callable dispatch 或 framework tool 注入契约。
- 不实现 SEC/Fins CI pipeline、CN/HK Docling CI pipeline、Web smoke 扩展或 Issue #121 / #122 范围。
- 不重新设计 upload ingestion workflow、Docling upload conversion、Fins repository schema 或 DocumentRepository 存储布局。

### 直接代码证据

- `dayu/runtime/tools_discovery.py` 当前用 `ToolsDiscoveryProviderSpec.allow_empty` 判断 provider 空输出是否允许通过。
- `dayu/config/tool_discovery.json` 当前所有 packaged providers 均携带 `allow_empty`，Fins providers 的 `workspace_root` 仍为 `null`，`financial-read-tools` 仍携带 `include_read_tools`，Doc / Fins read limits 仍为空 object，upload provider 仍携带 `allowed_upload_roots`。
- `dayu/fins/tools/provider.py` 当前在 `include_read_tools=false` 时返回空工具集并跳过 `workspace_root` 解析；这与独立 `financial-read-tools.enabled` 职责重复。
- `dayu/service/host_assembly.py` 当前只在 raw config `workspace_root is None` 且调用方传入 runtime workspace root 时注入 absolute path；改为 packaged `workspace/` 后需要明确相对 path effective resolution。
- OLD `/Users/leo/workspace/dayu-agent/dayu/config/run.json` 中 `doc_tool_limits` 与 `fins_tool_limits` 已给出默认业务 limits，当前 dataclass 默认值与其基本一致，但 packaged config 未显式承载。
- `dayu/fins/tools/upload_provider.py` 当前用 `allowed_upload_roots=[]` 返回空工具集；`dayu/fins/tools/upload_tools.py` 当前用 allowlist 校验工具参数中的本地 `files` 路径；`dayu.fins.storage` repository 写入仍由 `SourceHandle` / `ProcessedHandle` 与 filename 派生目标，不允许调用方指定任意仓储写入目录。

### 成功信号

- Packaged `tool_discovery.json` 不再包含 provider-level `allow_empty`、Fins read `include_read_tools` 或 upload `allowed_upload_roots`。
- ConfigLoader typed view、ToolsDiscovery provider spec、Service assembly 和 provider tests 均对新 schema 通过；旧字段在当前 schema 下 fail fast 或不再被接受。
- Fins workspace relative default `workspace/` 能通过 Service effective assembly 解析为 absolute path，并被 Fins read / download / preprocess / upload provider 一致消费。
- Fins read / Doc limits 在 packaged config 中显式出现，测试覆盖它们进入 tool definitions / truncate specs。
- Upload provider 不再因空 allowlist 返回空工具集；上传工具不再拒绝 allowlist 外本地路径，但仍校验文件存在、普通文件、非空与上传动作约束，并继续通过 Fins repository 写入。
- `pytest` 覆盖受影响 runtime / service / tools / fins 测试，`pyright dayu tests utils` 无新增或扩散错误。

### Gate 入口

Plan gate 交给 AgentCodex，计划 artifact 应写入 `docs/host/host-issues/wu-tools-01-f03-r4-tools-discovery-spec-plan.md`，并明确 implementation slices、allowed files、测试命令、README 更新决策和 residual risks。

## WU-ENG-02-R1 Provider Debugging Correlation Default Enablement And Fallback Diagnostics

### 状态

GitHub Issue #63 reopened on 2026-06-20 and was closed after PR 159 merged on 2026-06-20. Reopen comment:
https://github.com/noho/dayu-agent-r/issues/63#issuecomment-4756101567

本 WU 是 WU-ENG-02 / PR 114 的 reopened follow-up。WU-ENG-02 已完成 lower-level typed `RunnerRequestIdentity`、`ClientCorrelationPolicy`、OpenAI-compatible `X-Client-Request-Id` 映射能力、provider `x-request-id` 采集、Host ingest 与 Tool Trace 投影；reopen comment 指出真实 Service / CLI 默认路径没有启用该能力。本 WU 已通过 PR 159 修复默认启用路径，当前已完成，不再作为 active WU。

当前 gate 是 `completed`。Goal confirmation、plan gate、plan review、plan-fix、plan re-review、accepted plan commit、implementation、code review、code-review fix、code re-review、accepted slice commit、aggregate deepreview、accepted deepreview commit、push、create draft PR、PR review、accepted PR review commit、follow-up push、draft-PR-pass、final closeout 和 PR merge 已完成。

Plan artifact:

- `docs/host/host-issues/wu-eng-02-r1-provider-debugging-correlation-plan.md`

Plan review artifacts:

- `docs/reviews/plan-review-20260620-210618.md` by AgentDS
- `docs/reviews/plan-review-20260620-210656.md` by AgentMiMo

Plan fix artifact:

- `docs/reviews/wu-eng-02-r1-plan-fix-codex-20260620.md` by AgentCodex

Plan re-review artifacts:

- `docs/reviews/plan-rereview-wu-eng-02-r1-ds-20260620.md` by AgentDS, conclusion `pass`, blocking findings `0`
- `docs/reviews/plan-rereview-wu-eng-02-r1-mimo-20260620.md` by AgentMiMo, conclusion `pass`, blocking findings `0`

Accepted plan commit:

- `913875da` (`docs: accept WU-ENG-02-R1 plan`)

Implementation artifact:

- `docs/reviews/implementation-wu-eng-02-r1-codex-20260620.md` by AgentCodex

Code review artifacts:

- `docs/reviews/code-review-20260620-213746.md` by AgentDS, conclusion `pass`, blocking findings `0`
- `docs/reviews/code-review-20260620-214050.md` by AgentMiMo, conclusion `pass`, blocking findings `0`

Controller code-review judgment:

- `accepted`：补充 `dayu.host._terminal_diagnostics` 直接测试，覆盖 only provider id、only client id、both ids、both absent、`message=None` 以及 id 截断，降低后续 projection helper 格式回归风险。
- `accepted`：补充双 id 同时存在时的 terminal suffix 格式测试，确保 provider id 与 client correlation id 同时输出且顺序稳定。
- `accepted`：补充 Tool Trace diagnostic 在 `provider_request_id=None`、`client_correlation_id` 存在且 `raw_payload_ref` 存在时保留 `diagnostic_ref=raw_payload_ref` 的测试。
- `accepted`：`message=""` 是当前 production call path 不应传入的边界，但 helper 签名允许 `str`；可用最小逻辑把空字符串按 no-message 处理并用测试锁定，避免 future internal caller 产生前导空行。
- `rejected-with-reason`：`_lost_host_event` 当前不追加 diagnostic suffix 不影响本 WU；direct evidence 显示 `_lost_lifecycle_plan` 当前写入 `provider_request_id=None` 与 `client_correlation_id=None`，且 accepted plan scope 是 failed terminal。该 future sync risk 不在当前 fix 中处理。

Code-review fix artifact:

- `docs/reviews/fix-wu-eng-02-r1-code-review-codex-20260620.md` by AgentCodex

Code re-review artifacts:

- `docs/reviews/code-review-20260620-214954.md` by AgentDS, conclusion `pass`, blocking findings `0`
- `docs/reviews/re-review-wu-eng-02-r1-20260620-215031.md` by AgentMiMo, conclusion `pass`, blocking findings `0`

Final slice validation:

- `pytest tests/service/test_host_assembly.py tests/runtime/test_smoke_host_public_multiturn_assembly.py -q`: `53 passed, 3 warnings`
- `pytest tests/engine/runners/openai/test_request_identity.py tests/engine/runners/openai/test_streaming_capability_and_content_type.py tests/engine/runners/openai/test_http_error_event.py tests/engine/runners/openai/test_runner_diagnostics.py -q`: `38 passed`
- `pytest tests/host/test_terminal_diagnostics.py tests/host/test_read_api_terminal_policy.py tests/host/test_tool_trace_projection.py tests/host/test_tool_trace_queries.py -q`: `51 passed`
- `pytest tests/service/test_entrypoint_runtime.py tests/service/test_entrypoint_runtime_prompt_path.py tests/cli/test_prompt_command.py -q`: `69 passed, 3 warnings`
- `pyright`: `0 errors, 0 warnings, 0 informations`
- `git diff --check`: passed

Accepted slice commit:

- `150875e9` (`fix: enable provider debugging correlation by default`)

Aggregate deepreview artifacts:

- `docs/reviews/code-review-20260620-215431.md` by AgentMiMo, conclusion `pass`, blocking findings `0`
- `docs/reviews/code-review-20260620-215556.md` by AgentDS, conclusion `pass`, blocking findings `0`

Controller aggregate deepreview judgment:

- `rejected-with-reason`：`runner.http.response` 在 `client_correlation_id=None` 时输出字面量 `None` 与同日志行既有 `provider_request_id=None` 语义一致，不影响状态、持久化或 LLM-facing material；不为可读性微调追加 fix。
- `deferred-with-owner`：`_lost_host_event` / `_cancelled_host_event` 不追加 suffix 是当前 WU scope 内的有意选择；当前 lifecycle plan 不携带 provider/client correlation ids。若后续 WU 让 lost/cancelled lifecycle payload 携带 correlation ids，由对应 WU plan reviewer 复核 terminal projection 同步。

Accepted deepreview commit:

- `c9659dce` (`docs: accept WU-ENG-02-R1 deepreview`)

Draft PR readiness:

- Status: draft PR created.
- Branch: `phase/wu-eng-02-r1`
- Remote: `github`
- PR: https://github.com/noho/dayu-agent-r/pull/159
- Remaining risks: no blocking risks. Deferred projection-sync risk for future lost/cancelled lifecycle payload correlation ids is owned by the future WU that changes those payloads.

PR review artifacts:

- `docs/reviews/pr-159-review-20260620-220319.md` by AgentDS, conclusion `pass`, blocking findings `0`
- `docs/reviews/pr-159-review-20260620-220735.md` by AgentMiMo, conclusion `pass`, blocking findings `0`

Controller PR review judgment:

- `rejected-with-reason`：`client_correlation_id=None` 日志可读性观察与同一日志行既有 `provider_request_id=None` 行为一致，不影响状态、持久化或 LLM-facing material；不进入 fix。
- `deferred-with-owner`：per-model opt-out 不在本 WU 目标内；当前 reopen 要求 default enabled，若未来 provider 证明拒绝该 header，由新的 provider-specific WU 裁决 typed policy 或 opt-out。
- `deferred-with-owner`：lost/cancelled terminal suffix sync 仅在未来 lifecycle payload 携带 correlation ids 时需要，由对应 WU plan reviewer 复核。
- `accepted`：GitHub PR 当前无 reported CI checks；本轮以本地 pytest / pyright / `git diff --check` 作为验证证据，merge 前若仓库启用 CI/branch protection 再按 checks 处理。

Accepted PR review commit:

- `2d1737f1` (`docs: accept WU-ENG-02-R1 PR review`)

Draft PR pass:

- Status: pass.
- PR: https://github.com/noho/dayu-agent-r/pull/159
- Last pushed commit: `2d1737f1`

Final closeout:

- Status: final-closeout-pass.
- PR: https://github.com/noho/dayu-agent-r/pull/159
- PR state after user disposition: merged on 2026-06-20.
- Branch: `phase/wu-eng-02-r1`
- Branch head before final closeout record: `d96dcb65`
- GitHub checks at closeout: none reported on branch.
- Issue closeout handling: PR body contained `Closes #63`; Issue #63 closed after PR 159 merged.
- Validation retained from accepted slice / PR body: assembly 53 passed, runner 38 passed, Host terminal / Tool Trace 51 passed, Service / CLI 69 passed, pyright 0 errors, `git diff --check` passed.
- Remaining risks: no blocking risks. Non-blocking deferred risk remains limited to future WU changes that make lost/cancelled lifecycle payloads carry provider/client correlation ids; that future WU must re-check terminal projection suffix behavior.
- Post-closeout user-requested PR update: OpenAI-compatible Runner `runner.http.response` log now labels the protocol fields as `x-request-id` and `X-Client-Request-Id` instead of semantic internal field names, preserving the same log site, same log level, and same log line. Validation: OpenAI runner focused tests 22 passed, pyright 0 errors, `git diff --check` passed.
- Post-closeout user-requested PR update: OpenAI-compatible Runner now maps DeepSeek `x-ds-trace-id` into `provider_request_id` when standard `x-request-id` is absent. The existing response DEBUG line logs only present provider request id headers, falls back to `x-request-id=None` when none exist, and continues logging `X-Client-Request-Id` without dumping full response headers. Validation: OpenAI runner focused tests 23 passed, pyright 0 errors, `git diff --check` passed.

Controller plan-review judgment:

- `accepted`：终端诊断可见性不能留给 implementation agent 二选一；plan 必须收敛到最小 public contract 变更方案，在 Host public projection 边界追加 bounded diagnostic suffix，不修改 durable terminal payload message / payload digest。
- `accepted`：live watcher 与 outbox fallback 是两条独立 projection path；plan 必须要求共享同一 suffix formatting helper，并测试两条路径在 `provider_request_id=None` 且 `client_correlation_id` 存在时输出一致 fallback id。
- `accepted`：用户明确要求 log 中可见，因此 Python runner log 可见性是当前 WU 验收项；plan 必须去掉 escape hatch，要求在既有 `runner.http.response` log site 和既有 log level 上携带 `client_correlation_id`，不新增日志点、日志行或日志等级。
- `accepted`：provider request id header allowlist 缺少当前 issue 直接证据；plan 必须保持当前 `x-request-id` 提取，不把 `x-trace-id`、`x-correlation-id`、`cf-ray` 等 tracing / infrastructure header 伪装为 provider request id。若需要 header diagnostic，只能记录有界安全 header name presence，不输出 header values。
- `accepted`：Tool Trace `diagnostic_ref=None` 当前 validation 允许；plan 必须删除“可能需要 event_id fallback”的过度设计风险，明确不伪造 provider request id 或 diagnostic ref。
- `accepted`：Slice 1 实施前需要基线验证受影响 assembly tests，再区分期望行为变化和 regression。

### Reopen 直接证据

- GitHub Issue #63 曾在 2026-06-20 进入 `OPEN / REOPENED`，PR 159 merge 后当前已关闭。
- Reopen comment 明确：PR 114 已实现底层机制，但当时真实 CLI 路径未启用；reopen-time 代码中 `dayu/service/host_assembly.py` 把 `RunnerSpec.client_correlation_policy` 固定为 `ClientCorrelationPolicy.DISABLED`。
- Reopen-time 本地代码核对确认：`dayu/service/host_assembly.py` 的 `_runner_spec_from_model(...)` 返回 `RunnerSpec(..., client_correlation_policy=ClientCorrelationPolicy.DISABLED, ...)`。
- 因此 reopen-time 的 `dayu-cli prompt` 等默认 Service assembly 路径不会向 OpenAI-compatible / mimo-v2.5-pro 发送 `X-Client-Request-Id`；PR 159 已修复该默认路径。
- Reopen comment 记录实际日志中 `provider_request_id=None`，说明 mimo response 没有通过当时的 `x-request-id` 采集路径给出厂商侧 request id；同时因为 client correlation 默认未发送，也没有可提供给 vendor debugging 的 fallback request-level id。PR 159 关闭了默认 client correlation 未发送的问题，后续 provider-native header coverage 仍按 provider-specific WU 裁决。

### 目标

- 默认启用 OpenAI-compatible client correlation：不新增配置项，Service / CLI default assembly 不再把 `client_correlation_policy` 硬编码为 `DISABLED`。
- 保持 typed provider policy 边界：default enablement 应通过现有 `ClientCorrelationPolicy.OPENAI_X_CLIENT_REQUEST_ID` 或等价 typed policy 进入 RunnerSpec，不在 Host / Agent / Service 中写 provider 字符串治理分支。
- 保证真实 CLI / Service path 的普通 Agent -> Runner call 默认发送合法 `X-Client-Request-Id`，且仍不传 `safety_identifier`、fake `user_id` 或 UI / Service 用户概念。
- 现有日志 / 诊断 / Tool Trace / terminal diagnostic 中应能看到 `client_correlation_id`；当 `provider_request_id=None` 时，`client_correlation_id` 至少可作为向厂商报障的 fallback id。不得为此新增日志点，也不得为此修改日志等级；实现只能让现有日志或诊断输出携带 / 展示同源字段。
- 若 mimo 或 OpenAI-compatible provider 使用非 `x-request-id` 响应 header，应在 plan gate 核对当前 response header access path 后，补充 provider request id 提取策略或输出有界响应头诊断摘要，避免漏采无法定位。

### 非目标

- 不新增用户配置项或 profile switch 来控制 #63 的默认行为；reopen comment 要求 default enabled。
- 不把 `session_id`、Service 用户身份、UI 用户身份或内部治理 id 伪装成 provider end-user / safety governance field。
- 不改变 WU-ENG-02 已接受的 per-call identity derivation、RunnerRequestIdentity schema 或 provider-call-level correlation id 格式，除非代码核对证明当前格式无法满足 provider header 约束。
- 不在本 WU 实现完整 Tool Trace analyzer；WU-OBS-00 / #70 仍负责 analyzer。
- 不在本 WU 处理 usage observation 是否需要 correlation fields；该 residual 仍由 WU-OBS-00B / #119 裁决。
- 不实现 native Anthropic / Claude Code gateway adapter-specific request id semantics；该 scope 仍属于 #64 或后续 adapter-specific work unit。
- 不为 `client_correlation_id` 新增专用日志事件、额外日志行或提高日志等级；日志可见性必须复用已有 runner / Host / CLI diagnostics 输出边界。

### 验收信号

- Service / CLI default assembly path 的 `RunnerSpec.client_correlation_policy` 默认启用 OpenAI-compatible `X-Client-Request-Id` 映射。
- 受影响 tests 覆盖 default Service assembly 不再产生 `ClientCorrelationPolicy.DISABLED`。
- OpenAI-compatible Runner 在 policy 默认启用且 request identity 存在时发送合法 `X-Client-Request-Id`；policy 显式 disabled 的底层契约测试仍能表达 direct Runner / special path 的关闭行为。
- 现有日志输出能看见 `client_correlation_id`，但不新增日志点、不新增额外日志行、不调整日志等级。
- Tool Trace hot / cold projection 能看见 `client_correlation_id`，且测试覆盖 `provider_request_id=None` 时仍保留 fallback `client_correlation_id`。
- Host ingest / Tool Trace / diagnostics 能保留并展示 `client_correlation_id`；当 `provider_request_id=None` 时，诊断输出明确给出 fallback `client_correlation_id`，而不是只显示空 provider id。
- 若响应 header 中存在 provider request id 的非 `x-request-id` 形式，提取或有界 header diagnostic 能证明是否漏采；不得把完整敏感 header 无界输出到日志或 LLM-facing material。
- README / CLI help / diagnostics docs 按触发规则检查并按需更新。
- 受影响测试、pyright 和 `git diff --check` 通过。

### 初始 allowed files / modules for plan gate

- `docs/host/issues-implementation-control.md`
- `docs/engine/design.md`
- `docs/host/design.md`
- `dayu/service/host_assembly.py`
- Service / runtime assembly tests covering `ServiceOpenHostAssemblyResult` / default RunnerSpec assembly
- `dayu/engine/contracts/runner_spec.py`
- `dayu/engine/runners/openai/*`
- `dayu/host/engine_ingest.py`
- `dayu/host/tool_trace.py`
- CLI / runtime diagnostics modules and tests if needed for fallback diagnostic display
- README files only if their local update constraints say this user-visible diagnostics/default behavior change belongs there

### Stop conditions

- 如果 goal confirmation 发现 default enablement conflicts with a provider contract, security boundary, or existing config schema invariant, stop before plan and update design/control docs with the evidence.
- 如果 provider response header access is unavailable or would require leaking sensitive headers, plan must define a bounded diagnostic alternative before implementation.
- 如果 implementation would require changing public schema, durable EventLog semantics, or LLM-facing diagnostics wording, plan must call out exact contract and README/doc updates before implementation.

## Retention Issue Dependency / Implementation Order

GitHub Issue #43 是 storage lifecycle umbrella。`WU-RET-00` 已完成并归档，它不再作为 active implementation 入口；当前 active retention children 必须按以下关系裁决依赖和默认实施顺序：

```text
#43 storage lifecycle umbrella
├─ #36 Tool Trace cold JSONL retention
├─ #78 purge_session-driven retention cleanup
│  └─ #156 compaction artifact retention
└─ #96 Audit JSONL retention
```

默认实施顺序：

1. `WU-RET-01` / GitHub Issue #36：先处理 Tool Trace cold JSONL retention。它是 #43 child，不是 WU-OBS-00 / #70 analyzer 前置；analyzer 只能报告 cold trace retention limited signal，不能代替 retention 实施。
2. `WU-RET-03` / GitHub Issue #78：再处理 `purge_session` 驱动的 session-scoped retention cleanup。它定义 purge cleanup owner、可删除对象边界和 destructive cleanup 证明。
3. `WU-RET-04` / GitHub Issue #156：在 WU-RET-03 完成后处理 compaction artifact retention。#156 是 #78 child，不能绕过 purge cleanup 边界独立实现 artifact retention 或新增 Host background scheduler。
4. `WU-RET-02` / GitHub Issue #96：最后处理 Audit JSONL retention，保留 purge tombstone / audit ledger 可验证关联，并避免把 audit JSONL 误用为 purge completion truth。

只有 `WU-RET-04` 对 `WU-RET-03` 有硬前置依赖。`WU-RET-01` 与 `WU-RET-02` 是 #43 下的 sibling storage-governance work units；除非后续 issue / code 核对发现新的共享 contract，二者不互相阻塞。

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

## WU-RET-01 Tool Trace Cold JSONL Storage Governance

### 状态

GitHub Issue #36 是 GitHub Issue #43 storage lifecycle umbrella 的 child，已 currentize：旧 P7 `ToolTraceJsonlSink._select_jsonl_file()` / `tool_calls_*.jsonl` 分片滚动描述已过期，当前定位改为 Tool Trace cold JSONL 长期存储治理。本条是 retention lane 默认第 1 项，不作为 WU-OBS-00 / #70 的前置；#70 analyzer 可以报告 cold JSONL 过大、重复行或完整性问题，但不负责实施 rotation / retention / compaction。GitHub Issue #79 已被本条吸收：#79 的 cold trace retention / purge 后保留边界由 #36 承接；其中 shared artifact / 跨 Session 引用的删除证明属于 #43 umbrella 下已完成的 WU-RET-00 storage lifecycle safety boundary，以及后续 WU-RET-03 / #78 的 purge cleanup owner。

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

## WU-RET-03 purge_session-driven Retention Cleanup

### 状态

GitHub Issue #78 是 GitHub Issue #43 storage lifecycle umbrella 的 child，也是 WU-RET-04 / GitHub Issue #156 的 parent。本条是 retention lane 默认第 2 项，应在 WU-RET-01 / #36 后进入 goal confirmation；它不是重新实现已完成的 `purge_session` command，而是固定 `purge_session` 驱动的 session-scoped retention cleanup owner、cleanup 触发边界、可删除对象集合、删除证明和诊断输出。

### 设计与代码核对

- `docs/host/design.md` 已定义 `purge_session` 是第一版 destructive EventLog retention exception，purge completion truth 仍是 SQLite tombstone，而不是 audit JSONL 或 projection。
- WU-RET-00 已完成 storage lifecycle safety boundary：清理不能破坏 EventLog truth、payload descriptor、projection、audit、trace、analyzer 或共享 artifact 引用。
- WU-CM-15 closeout 已把 compaction artifact retention 转移到 GitHub Issue #156 under #78，说明 #156 必须依赖 #78 的 purge cleanup ownership。
- 当前主控不应让 #156 先于 #78 实施；否则 compaction artifact retention 会缺少 session purge 删除证明、共享引用判断和 Host maintenance 边界。

### 目标

- 固定 `purge_session` 驱动的 retention cleanup owner：哪些 cleanup 属于 purge transaction 内，哪些必须是 purge 后显式 maintenance / report。
- 定义 session-scoped cleanup 对象边界：payload descriptor、SQLite payload、artifact descriptor、compact artifacts、memory projection artifacts、diagnostic payloads、tool trace hot rows、cold refs、audit refs 与其它派生数据。
- 定义 shared artifact / cross-session ref 的删除证明，禁止删除仍被其它 Session、EventLog、projection、audit、trace、analyzer 或 retention policy 需要的对象。
- 定义 cleanup report / diagnostic：已删除、保留、跳过、shared-ref blocked、missing、digest mismatch、manual action required。
- 为 WU-RET-04 / #156 输出明确 handoff：compaction artifacts 哪些受 `purge_session` cleanup 控制，哪些属于 broader artifact retention 或 operator maintenance。

### 非目标

- 不重新实现 `purge_session` command 的核心状态机。
- 不实现 Tool Trace cold JSONL rotation / compaction；该能力由 WU-RET-01 / #36 承接。
- 不实现 Audit JSONL rotation / compaction；该能力由 WU-RET-02 / #96 承接。
- 不提前实现 WU-RET-04 / #156 的 compaction artifact retention policy。
- 不新增 Host background scheduler；是否需要 scheduler 必须先由 #78 的 cleanup owner / trigger 边界证明。

### 验收信号

- `purge_session` cleanup owner、trigger boundary、deletion proof 和 diagnostic 输出有设计与测试覆盖。
- shared artifact / cross-session ref 场景不会被误删，且保留原因可诊断。
- purge tombstone 仍是 destructive purge completion truth；audit / trace / report 只是 projection 或 operator evidence。
- WU-RET-04 / #156 的 entry condition 清晰：只能在 #78 完成后基于其 cleanup boundary 实施 compaction artifact retention。

## WU-RET-04 Compaction Artifact Retention

### 状态

GitHub Issue #156 是 GitHub Issue #78 的 child，归属于 GitHub Issue #43 storage lifecycle umbrella。本条状态为 `pending-prerequisite`：必须等待 WU-RET-03 / #78 完成后才能进入 implementation gate。它处理 Conversation Memory / Context Governance compaction artifacts 的 retention 与 cleanup，不得绕过 #78 自行定义 `purge_session` cleanup owner，也不得新增无设计依据的 Host background scheduler。

### 设计与代码核对

- `docs/host/design.md` 将 Conversation Memory 定义为 EventLog 与 accepted compact projection 的 read model，不是事实真源；Context Governance 负责 compact 编排与事件收口，不直接写 memory truth。
- Compaction artifacts 服务诊断、恢复、review 和 operator closeout；它们不是 EventLog canonical truth，但删除必须尊重 EventLog refs、artifact descriptors、digest、purge tombstone 与 shared refs。
- WU-CM-15 closeout 已明确：compaction artifact retention transferred to GitHub Issue #156 under #78，且 #156 可以依赖 #78 的 purge ownership 定义 artifact retention cleanup，而不是新增 Host background scheduler。

### 目标

- 基于 WU-RET-03 / #78 的 purge cleanup boundary，定义 compaction artifact retention policy。
- 明确 accepted / rejected / failed / fallback compaction artifacts 的保留窗口、删除条件、诊断价值和 purge 后行为。
- 定义 artifact descriptor / digest / source event refs 的保留与删除证明，避免 artifact 文件与 durable refs 漂移。
- 增加 operator-visible report：compaction artifact count、size、age、source run/session、retention reason、deletion eligibility、blocked reason。
- 对 purge-driven cleanup 与非 purge maintenance cleanup 做清晰区分。

### 非目标

- 不绕过 WU-RET-03 / #78 定义 `purge_session` cleanup owner。
- 不改变 compact proposal / validation / repair / fallback 的 Host 状态机。
- 不把 compaction artifact 变成 memory truth 或 EventLog truth。
- 不实现 Tool Trace cold JSONL 或 Audit JSONL retention。
- 不新增周期后台 GC，除非 #78 已明确批准 scheduler / maintenance owner。

### 验收信号

- WU-RET-03 完成后，本条 plan 能直接引用其 purge cleanup owner、deletion proof 和 diagnostic contract。
- Compaction artifact retention 不破坏 recovery、diagnostics、review artifacts、accepted compact refs 或 fallback auditability。
- 删除、保留、shared-ref blocked、missing artifact 和 digest mismatch 场景有测试。
- Operator 能看见 compaction artifact storage usage、eligible cleanup 和保留原因。

## WU-RET-02 Audit JSONL Storage Governance

### 状态

GitHub Issue #96 是 GitHub Issue #43 storage lifecycle umbrella 的 child，跟踪 Audit JSONL 长期存储治理。本条是 retention lane 默认第 4 项。Audit 与 Tool Trace 都有 append-only JSONL 长期累积占用本地存储的问题，但 Audit 承载治理动作和责任链 projection，尤其 purge audit line 需要和 SQLite purge tombstone 形成可解释的 destructive 操作流水，因此必须单独实施。WU-RET-03 / #78 与 WU-RET-04 / #156 不阻塞本条的 JSONL-specific rotation / retention / compaction 设计，但本条必须尊重 purge tombstone / destructive cleanup 真源边界。

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

已纳入 GitHub Issue #91；GitHub Issue #87 是 Host Lifecycle Watchdog / Supervisor umbrella。本条是 #87 下的 active Attempt cancel watchdog target，不单独引入第二套 watchdog runtime。PR #166 已于 2026-07-04 merge，GitHub Issue #92 已自动关闭，本条已进入当前 implementation entry point。Goal confirmation 已由用户确认。Plan artifact 为 `docs/host/wu-life-03-active-cancel-watchdog-plan.md`，plan decision 为 ready。Plan review artifacts 为 `docs/reviews/plan-review-20260704-105429.md` 与 `docs/reviews/plan-review-20260704-105503.md`；controller adjudication 为 `docs/reviews/wu-life-03-plan-review-controller-adjudication.md`。Controller accepted recovery scanner / watchdog ordering, late terminal race, watchdog scheduling, clock policy, diagnostic payload mapping, projection compatibility, and scan strategy findings。Plan fix artifact 为 `docs/reviews/wu-life-03-plan-fix-codex.md`；AgentCodex reported all accepted findings fixed and `git diff --check` passed。Plan re-review artifacts 为 `docs/reviews/plan-review-20260704-110623.md` 与 `docs/reviews/plan-review-20260704-110719.md`；controller adjudication 为 `docs/reviews/wu-life-03-plan-rereview-controller-adjudication.md`。两路 re-review 均通过，F01-F07 均已修复，无 blocking open question。Accepted plan commit 为 `50d34e52`。Slice 1 implementation artifact 为 `docs/reviews/wu-life-03-slice1-implementation-codex.md`；AgentCodex reported focused tests 122 passed, pyright 0 errors, and `git diff --check` passed. Controller reran the same validation with 122 passed, pyright 0 errors, and `git diff --check` passed. Slice 1 code review artifacts 为 `docs/reviews/code-review-20260704-112548.md` 与 `docs/reviews/code-review-20260704-112608.md`；controller adjudication 为 `docs/reviews/wu-life-03-slice1-code-review-controller-adjudication.md`。Controller accepted parser reuse, timestamp normalization, optional diagnostic payload test, malformed payload test, and timeout self-replay test findings。Slice 1 fix artifact 为 `docs/reviews/wu-life-03-slice1-fix-codex.md`；AgentCodex reported all accepted findings fixed, focused tests 123 passed, pyright 0 errors, and `git diff --check` passed. Controller reran the same validation with 123 passed, pyright 0 errors, and `git diff --check` passed. Slice 1 code re-review artifacts 为 `docs/reviews/code-review-20260704-113656.md` 与 `docs/reviews/code-review-20260704-113657.md`；controller adjudication 为 `docs/reviews/wu-life-03-slice1-code-rereview-controller-adjudication.md`。两路 re-review 均通过，S1-CR-F01 / F02 / F03 / F04 / F05 均已关闭，无 blocking open question。Accepted Slice 1 commit 为 `ef2d3644`。Slice 2 implementation artifact 为 `docs/reviews/wu-life-03-slice2-implementation-codex.md`；AgentCodex reported lifecycle watchdog focused tests 140 passed, transition / ingest regression tests 123 passed, pyright 0 errors, and `git diff --check` passed. Controller reran the same validation with 140 passed and 123 passed, pyright with 0 errors, and `git diff --check` passed. Slice 2 code review artifacts 为 `docs/reviews/wu-life-03-slice2-code-review-mimo.md` 与 `docs/reviews/wu-life-03-slice2-code-review-ds.md`；controller adjudication 为 `docs/reviews/wu-life-03-slice2-code-review-controller-adjudication.md`。Controller accepted malformed `RUN_CANCELLING` recovery payload handling and watchdog loop transient exception resilience as current fixes；Protocol location and overlapping precondition notes are non-blocking. Slice 2 fix artifact 为 `docs/reviews/wu-life-03-slice2-fix-codex.md`；AgentCodex reported lifecycle watchdog focused tests 142 passed, transition / ingest regression tests 123 passed, pyright 0 errors, and `git diff --check` passed. Controller reran the same validation with 142 passed and 123 passed, pyright with 0 errors, and `git diff --check` passed. Slice 2 code re-review artifacts 为 `docs/reviews/wu-life-03-slice2-code-rereview-mimo.md` 与 `docs/reviews/wu-life-03-slice2-code-rereview-ds.md`；controller adjudication 为 `docs/reviews/wu-life-03-slice2-code-rereview-controller-adjudication.md`。两路 re-review 均通过，S2-CR-F01 / S2-CR-F02 均已关闭，无新增 material defect。Accepted Slice 2 commit 为 `3ff42b15`。Aggregate deepreview artifacts 为 `docs/reviews/wu-life-03-aggregate-deepreview-mimo.md` 与 `docs/reviews/wu-life-03-aggregate-deepreview-ds.md`；controller adjudication 为 `docs/reviews/wu-life-03-aggregate-deepreview-controller-adjudication.md`。两路 aggregate deepreview 均通过，无 blocking finding；watchdog scan SQL optimization 已归属 #87 umbrella 后续 tuning（非 #91 / WU-LIFE-03 closeout blocker），provider/tool physical cleanup 已归属 WU-TOOLS-CANCEL-01，theoretical `payload_json=None` boundary 已裁决为 accepted risk。Accepted aggregate deepreview commit 为 `e42346d7`。Draft PR #167 已创建：https://github.com/noho/dayu-agent-r/pull/167。PR body 使用 `Closes #91`，merge 会自动关闭 #91；#87 仅作为 umbrella follow-up owner 保留。`gh pr checks 167` reported no checks on branch `phase/host-engine-next`。PR review artifacts 为 `docs/reviews/wu-life-03-pr-167-review-mimo.md` 与 `docs/reviews/wu-life-03-pr-167-review-ds.md`；controller adjudication 为 `docs/reviews/wu-life-03-pr-167-review-controller-adjudication.md`。两路 PR review 均通过，无 blocking finding；watchdog scan optimization 继续归属 #87 umbrella 后续 tuning，非当前 #91 blocker。Accepted PR review commit 为 `4f3d9d81`，并已 push 到 draft PR #167。Final closeout artifact 为 `docs/reviews/wu-life-03-final-closeout.md`。Issue closeout comment 已发布：https://github.com/noho/dayu-agent-r/issues/91#issuecomment-4880685816。当前进入 final-closeout-pass，等待用户 / maintainer 处理 draft PR #167；不得未经授权 mark ready、merge、close issue、request reviewers 或 delete branch。Merge PR #167 后，应从 `main` 拉取最新代码，再按本文档 next entry point 进入 WU-LIFE-04。

### 目标

- 复用 #87 的 Host lifecycle watchdog / supervisor，不另建 active cancel 专属 watchdog。
- 裁决 active cancel watchdog owner、timeout policy、Run / Attempt 终态、diagnostic payload、late terminal race 与 session cancel replay 语义。
- 明确 post-cancel timeout 后 Run / Attempt / diagnostic 的收敛路径，以及 first-committer-wins / late rejection 规则。
- 保证 active cancel 被 Host 接受后，Host durable truth 不等待 worker / provider 配合；即使 worker stream 不结束、provider 不返回、worker task 不响应 token，也必须有可测试的 timeout closeout 或 diagnostic 收敛。
- 为 WU-TOOLS-CANCEL-01 提供稳定输入契约：哪些状态进入 timeout closeout、哪些迟到事件被接受 / 拒绝 / quarantine、哪些 diagnostic 字段用于定位不配合的 execution boundary。

### 非目标

- 不直接 kill 不属于 Host 管理的外部进程。
- 不把 provider-specific cancel API 硬编码进 Host 核心。
- 不把 scheduler close 设计成 active cancel timeout closeout。
- 不设计 tool/provider execution capsule、不定义 subprocess / process-group / sandbox kill 策略；这些归 WU-TOOLS-CANCEL-01。

### 验收信号

- provider 卡死、stream 不结束、worker task 不响应 cancellation 时，Host truth 都有可测试 closeout 或 diagnostic 收敛。
- terminal event 与 diagnostic 不重复、不互相矛盾。
- active cancel command replay、session-scope cancel replay 与 late terminal race 都符合 first-committer-wins。
- WU-TOOLS-CANCEL-01 可以直接消费本条输出的 timeout closeout / diagnostic contract，不需要重新裁决 Host terminal 语义。
- GitHub Issue #87 明确跟踪设计问题、非目标和验收测试；实施前需要先回到 design gate。

## WU-LIFE-04 Tool Execution Deadline And #87 Watchdog Closeout

### 状态

已纳入 GitHub Issue #168；GitHub Issue #87 是 Host Lifecycle Watchdog / Supervisor umbrella。本条是 #87 的 umbrella closeout follow-up，当前为 WU-LIFE-03 merge 后的 pending-next implementation entry point，并且必须在 WU-TOOLS-CANCEL-01 之前完成。当前讨论已确认：`tool_execution_timeout_seconds` 是单次工具调用最长运行时间，任何取消 / 收口机制不得覆盖或延长单个 tool call 的原始 deadline。

### 目标

- 固定业务语义：`tool_execution_timeout_seconds` 是单次工具调用最长运行时间，配置真源继续是 `execution_profiles.json -> agent_policy.tool_execution_timeout_seconds`，不迁移到 `host_runtime.json`。
- 裁决 Host cancel watchdog 如何消费已有 execution deadlines；用户 Esc 取消不得重置、覆盖或延长正在运行 tool call 的原始 deadline。
- 避免引入第二套 active cancel timeout；若现有实现已暴露或默认化 `active_cancel_timeout_seconds`，本 WU 必须裁决移除、降级为内部过渡实现或改为 derived deadline 逻辑。
- 收敛 #87 shared supervisor 验收语义：接受共享 lifecycle governance 概念加 target-specific runtime，或要求抽取共享 supervisor runtime abstraction。
- 评估 active watchdog scan query optimization 是否进入本 WU，或转交更窄的 performance follow-up。
- 为 clock skew、diagnostics / audit hooks 和其他 #87 umbrella residual 指定明确 owner / destination。

### 非目标

- 不实现 tool/provider physical interruption、request abort、process-group termination 或 hard-kill；这些仍归 WU-TOOLS-CANCEL-01。
- 不修改 Engine awaiting 或 tool-calling public contract。
- 不新增 `active_cancel_timeout_seconds` 作为取消后的额外预算。
- 不把 `tool_execution_timeout_seconds` 放入 `host_runtime.json`；它属于 execution profile / Agent policy 执行策略。
- 不为了形式一致抽取 generic supervisor；只有直接正确性、可运维性或可维护性证据成立时才进入设计。

### Discussion Gate 约束

- 必须先确认 Host cancel watchdog 在 tool call 执行期如何取得并遵守本次 tool execution deadline，再决定是否修改设计真源、本文档、GitHub Issue 或进入 plan gate。
- 必须基于代码直接证据确认当前配置链路：`execution_profiles.json` 配置 `AgentPolicy.tool_execution_timeout_seconds`，并将其作为单次工具调用最长运行时间的业务真源。
- 必须明确本 WU 与 WU-TOOLS-CANCEL-01 的顺序关系；不得用本 WU 替代 tool/provider interrupt boundary。

## WU-TOOLS-CANCEL-01 Tool/provider Blocking I/O Cancellation Hardening

### 状态

等待 WU-LIFE-04 固定 tool execution deadline 与 Host watchdog closeout 边界后实施。本条是 tool/provider runtime 的实际 interrupt boundary 与 escalation 能力，不是 WU-WAIT-03 / GitHub Issue #92 residual，也不是 WU-WAIT-04 smoke。当前代码已有 Host cancellation token、部分工具 cooperative checkpoint、局部 Playwright process terminate / kill，但缺少通用 ToolRuntime / worker-owned interruptible capsule；本条必须补齐该通用边界，并不得延长 WU-LIFE-04 固定的单次工具执行 deadline。

### 目标

- 设计 Host-owned tool/provider execution interrupt boundary，使取消后 Host 能迅速回到可交互状态。
- 定义取消升级链路：cooperative cancellation token、request / stream abort、subprocess / process-group / sandbox termination、hard-kill diagnostic closeout。
- 固化旧 tool/provider 迟到结果的拒绝 / quarantine 语义，确保已取消 Run 不被旧结果污染。
- 为不配合的 blocking tool/provider 提供可测试 fixture，验证取消体感接近 Codex / Claude Code interrupt：用户取消后不继续输出旧执行结果，且新输入可继续推进。
- 明确哪些 tool/provider 必须进入 interruptible execution capsule；不可抢占的同进程 blocking I/O 不得作为 production-grade cancel path 的默认执行形态。
- 复用 WU-LIFE-03 的 Host terminal / diagnostic contract，不重新定义 Run / Attempt 终态。
- 消费 WU-LIFE-04 固定的 tool execution deadline contract；用户取消、执行中断、迟到结果 quarantine 或 hard-kill diagnostic 均不得延长单次工具调用的原始 `tool_execution_timeout_seconds` deadline。

### 非目标

- 不把 provider-specific kill / cancel API 硬编码进 Host 核心。
- 不承诺外部 provider 已接收的远端任务一定物理停止；若 provider 不支持 cancel API，本条只保证本地执行边界停止等待、迟到结果不污染 Host truth，并记录诊断。
- 不替代 WU-LIFE-03 的 Host-level timeout closeout；本条消费 WU-LIFE-03 的 Run / Attempt / diagnostic 语义。
- 不重新裁决 WU-LIFE-04 的 tool execution deadline 语义，也不引入取消后的第二套工具执行预算。
- 不重新实现 WU-WAIT-03 的 WAITING external job lifecycle contract。
- 不把“工具自愿检查 cancellation token”当作唯一 production 方案；cooperative checkpoint 只是升级链路第一层。

### 验收信号

- 至少一个不配合的 blocking tool/provider fixture 可被 cancel 后快速释放 Host 可交互路径。
- cancellation escalation 的每个阶段都有 typed diagnostic 或明确 terminal closeout。
- 被 hard interrupt 或迟到返回的 tool/provider 不得写入已取消 Run 的 terminal fact、final answer 或 accepted tool result。
- smoke 必须证明 cancel 后可以提交并推进新的用户输入；旧执行即使稍后返回也只能进入 diagnostic / quarantine。
- 对 subprocess / process-group / sandbox 型执行边界，测试覆盖 graceful interrupt、terminate 和 hard kill 至少两级升级。
- WU-WAIT-04 可把本条能力作为 production-grade awaiting smoke 的前置取消体验能力。

## WU-GOV-01 Host Policy Refusal Terminal Taxonomy

### 状态

GitHub Issue #88 当前为 OPEN。已裁决长期需要引入 `RunStatus.REJECTED`，但它的动机不是 compact failure，而是生产级 Host policy refusal：权限、租户、额度、配额、速率限制、工具权限 / 审批策略、admission validation、workflow / scene / tool set policy 等在执行前或执行外明确拒绝整个 Run 的场景。

本条是后续 policy / permission / tenancy / quota / rate-limit / tool approval feature 的状态机前向约束：这些 feature 在 plan / implementation 时必须先判断拒绝是否属于 `REJECTED`，避免先落成含糊的 `FAILED` 后再迁移。

### 目标

- 引入 `RunStatus.REJECTED`，用于表达 Host policy gate 明确拒绝接受 / 继续整个 Run，且该拒绝不是执行、compact、recovery、外部 job 或 worker lifecycle 尝试失败的结果。
- 裁决 rejected Run 的 canonical EventLog taxonomy；优先设计独立 `RUN_REJECTED` terminal fact。若复用 `RUN_FAILED`，必须证明 public terminal status、projection、outbox 和 retry / replay 不会混淆。
- 明确应归入 `REJECTED` 的场景：admission 阶段用户输入不合法且不能自动修复；权限、租户、额度、配额、速率限制拒绝；工具权限 / 审批策略拒绝整个 Run；context hard limit 下当前输入本身不可执行且 fallback 也无法构造合法输入；policy 明确禁止某个 workflow / scene / tool set；请求与 session state 冲突且 Host 明确不应启动执行。
- 明确不应归入 `REJECTED` 的场景：Engine 已经创建 Attempt 后 runner / provider / tool 失败；reactive compact failure 后 recovery 失败；外部 job 执行失败；worker crash、orphan、lost proof；用户取消；compact proposal 被 reject 但 fallback 可以继续 dispatch；compact / fallback 尝试最终 fail closed，除非另有独立 policy gate 在 compact 前已经拒绝该目标。
- 同步 Run status、EventLog terminal taxonomy、projection、public contract、retry / replay 前置条件、outbox / HostEvent 映射、文档与测试。

### 非目标

- 不为单个 failure reason 临时增加状态。
- 不让 Attempt terminal taxonomy 承担 Run-level governance 语义。
- 不把 `REJECTED` 做成更细的 `FAILED`，也不把 compact failure、runner failure、tool failure、external job failure、recovery failure 或 worker crash 纳入 `REJECTED`。
- 不把普通 diagnostic rejected event，例如 late wait result rejected 或 EngineEvent rejected，等同于 Run terminal rejected。

### 验收信号

- Public `RunStatus` 包含 `REJECTED`，并在终态集合、public contract freeze tests、read API、HostEvent、outbox、retry / replay 和 projection 中一致处理。
- Durable transition helper 支持 attempt-free rejected Run；已有 Attempt 的执行失败路径仍使用 `FAILED`。
- 权限 / 租户 / quota / rate limit / tool approval policy 至少一个代表性 gate 能产生 `REJECTED`，并有端到端测试。
- compact failure、fallback fail-closed 和 reactive recovery failure 默认不迁移到 `REJECTED`；如未来要例外处理，必须先证明它是独立 policy refusal，而不是治理执行失败。
- 文档同步说明 `FAILED` 与 `REJECTED` 的边界、用户动作差异、retry / replay 语义，以及本 WU 对后续 feature 的前向约束。

## WU-CTX-04 Run-level Compaction Concurrency Boundary

### 状态

GitHub Issue #112 当前为 OPEN。PR #150 / #152 后已重新裁决：当前正常路径下，同一 `run_id` 同一时间出现多个有效 compact commit 不是已知 bug，也不是普通执行路径下容易复现的问题。本条不要求当前实现 EventLog fencing，而是保留为低优先级设计核对项。

### 目标

- 明确当前 Host compaction 调度模型是否已经通过 Run / Attempt 状态机、compaction request 计数、事务外执行后的 stale result recheck，足以保证同一 `run_id` 不会产生多个有效 compact commit。
- 若当前调度模型足够，补充或引用并发 / 重复触发测试与设计说明后关闭 #112。
- 若未来引入更多 Host worker、并发 EngineEvent ingest、跨进程调度器或更复杂 compaction 触发路径，则在 EventLog 之外设计最小 durable pointer / CAS，例如 run-scoped current compact pointer 或 operation state row。
- 保持 EventLog 只记录已经发生的 canonical facts，不承载 mutex、lease、owner token 或 fencing 语义。

### 非目标

- 不给 EventLog 增加 fencing / lease / lock 语义。
- 不把 compact artifact 改成 `run_id` 唯一覆盖文件；compact artifact 仍是内容寻址、不可变、可审计材料。
- 不在 dispatch 或 engine_ingest 单侧增加只能覆盖单进程的 in-memory lock。
- 不为了未来并发风险提前引入复杂 durable lock 表。

### 验收信号

- 明确结论：当前实现是否需要额外 run-level compaction CAS。
- 如果不需要：证明现有状态机、request 计数与 stale recheck 足以覆盖当前调度模型，并关闭 #112。
- 如果需要：实现 EventLog 外的最小 durable pointer / CAS，并让 proactive / reactive 写回路径复用同一契约。
- README 或设计文档同步说明：EventLog 不承载 fencing；compact artifact 是不可变审计产物；`run_id` 唯一当前 compact 视图只能是 projection / pointer。

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

GitHub Issue #89 当前为 OPEN。research 已写入 issue；本条后续按 callback adapter -> common `resolve_wait` pipeline 的方向实施。Claude Code 的 background subagent / lifecycle completion 行为可作为参考；Codex 具备 subagent orchestration，但公开 callback / hook surface 不应被假设为稳定生产 primitive。

2026-06-21 goal confirmation 已完成。PR #162 已 merge，本地 `main` 已包含 WU-TOOLS-01-F01-02-R1 two-phase activation 前置能力。代码核对显示 `resolve_wait` 已覆盖幂等重放、同 key 不同 outcome conflict、late result rejection、completed / failed / cancelled / lost outcome 和 poller 共用路径；`dayu/host/wait_adapter.py` 当前明确不实现 callback endpoint。Plan artifact 已创建：`docs/host/wu-wait-01-callback-endpoint-auth-replay-plan.md`。Plan review artifacts 为 `docs/reviews/plan-review-20260621-220834.md` 与 `docs/reviews/plan-review-20260621-221033.md`；controller adjudication 为 `docs/reviews/wu-wait-01-plan-review-controller-adjudication.md`。Controller 接受全部 material findings。Plan fix artifact 为 `docs/reviews/wu-wait-01-plan-fix-codex.md`，记录 F01-F09 已全部修复。Plan re-review artifacts 为 `docs/reviews/plan-review-20260621-222106.md` 与 `docs/reviews/plan-review-20260621-222241.md`；controller adjudication 为 `docs/reviews/wu-wait-01-plan-rereview-controller-adjudication.md`。两路 re-review 均通过，F01-F09 最终状态均为已修复。Accepted plan commit 为 `bf359ebb`。Slice 1 implementation artifact 为 `docs/reviews/wu-wait-01-slice1-implementation-codex.md`；AgentCodex reported `tests/host/test_wait_callback.py` 11 passed, focused Host wait callback / resolve / late-result / package-export / import-boundary tests 54 passed, pyright 0 errors, and `git diff --check` passed. Controller reran focused tests with 54 passed and pyright with 0 errors. Slice 1 code review artifacts 为 `docs/reviews/code-review-20260621-224502.md` 与 `docs/reviews/code-review-20260621-224440.md`；controller adjudication 为 `docs/reviews/wu-wait-01-slice1-code-review-controller-adjudication.md`。Controller accepted S1-CR-F01 digest material projection deduplication and S1-CR-F02 Host timestamp helper reuse; S1-CR-F03 is covered by S1-CR-F02. Fix artifact 为 `docs/reviews/wu-wait-01-slice1-fix-codex.md`；AgentCodex reported focused tests 56 passed, pyright 0 errors, and `git diff --check` passed. Controller reran focused tests with 56 passed, pyright with 0 errors, and `git diff --check` passed. Slice 1 code re-review artifacts 为 `docs/reviews/code-review-20260621-225901.md` 与 `docs/reviews/code-review-20260621-225831.md`；controller adjudication 为 `docs/reviews/wu-wait-01-slice1-code-rereview-controller-adjudication.md`。两路 re-review 均通过，无 material finding；S1-CR-F01 / S1-CR-F02 / S1-CR-F03 均关闭。Accepted Slice 1 commit 为 `6f919bb7`。Slice 2 implementation artifact 为 `docs/reviews/wu-wait-01-slice2-implementation-codex.md`；AgentCodex reported Service focused tests 28 passed, Service focused plus weak typing 29 passed, Host callback focused tests 56 passed, pyright 0 errors, and `git diff --check` passed. Controller reran Service focused plus weak typing tests with 29 passed, Host callback focused tests with 56 passed, pyright with 0 errors, and `git diff --check` passed. Slice 2 code review artifacts 为 `docs/reviews/code-review-20260621-231602.md` 与 `docs/reviews/code-review-20260621-231811.md`；controller adjudication 为 `docs/reviews/wu-wait-01-slice2-code-review-controller-adjudication.md`。Controller accepted S2-CR-F01 missing request id sentinel rejection and S2-CR-F02 fail-closed mapper branch tests. Slice 2 fix artifact 为 `docs/reviews/wu-wait-01-slice2-fix-codex.md`；AgentCodex reported Service focused tests 47 passed, Host callback focused tests 56 passed, pyright 0 errors, and `git diff --check` passed. Controller reran Service focused tests with 47 passed, Host callback focused tests with 56 passed, pyright with 0 errors, and `git diff --check` passed. Slice 2 code re-review artifacts 为 `docs/reviews/code-review-20260621-232753.md` 与 `docs/reviews/code-review-20260621-232916.md`；controller adjudication 为 `docs/reviews/wu-wait-01-slice2-code-rereview-controller-adjudication.md`。两路 re-review 均通过，无 material finding；S2-CR-F01 / S2-CR-F02 均关闭。Accepted Slice 2 commit 为 `9d77e641`。Aggregate deepreview artifacts 为 `docs/reviews/code-review-20260621-234334.md` 与 `docs/reviews/code-review-20260621-233742.md`；controller adjudication 为 `docs/reviews/wu-wait-01-aggregate-deepreview-controller-adjudication.md`。两路 aggregate deepreview 均通过，无 material finding；controller accepted all residual risks as non-blocking. Accepted deepreview commit 为 `ab2a6997`。Draft PR #163 已创建：https://github.com/noho/dayu-agent-r/pull/163。`gh pr checks 163` reported no checks on branch `phase/wu-wait-01-issue-89`。PR review artifacts 为 `docs/reviews/wu-wait-01-pr-review-mimo.md` 与 `docs/reviews/wu-wait-01-pr-review-ds.md`；controller adjudication 为 `docs/reviews/wu-wait-01-pr-review-controller-adjudication.md`。两路 PR review 均通过，无 material finding。Accepted PR review commit 为 `36eda549` 并已 push 到 draft PR #163。Final closeout artifact 为 `docs/reviews/wu-wait-01-final-closeout.md`。Issue closeout comment 已发布：https://github.com/noho/dayu-agent-r/issues/89#issuecomment-4762516139。PR body 使用 `Closes #89`，merge 会自动关闭 #89。当前进入 final-closeout-pass gate，等待用户 / maintainer 处理 draft PR #163；不得未经授权 mark ready、merge、close issue、request reviewers 或 delete branch。Merge PR #163 后，应从 `main` 拉取最新代码，再按本文档 next entry point 进入 WU-WAIT-02 / GitHub Issue #90。

### 设计与代码核对

- `docs/host/design.md` 规定 Host 是 Session / Run / Attempt / EventLog / wait governance 真源；callback transport 不得拥有 Host durable state transition。
- `docs/engine/design.md` 规定 Engine 不持久化 wait record，不等待外部长事务完成；恢复由调用方构造新 `AgentRunRequest`，Host 负责等待治理。
- `dayu/host/api.py` 已有 `WaitResolutionSource.CALLBACK`，但缺少 callback adapter 的 typed envelope、auth source、payload digest 校验和错误分类契约。
- `dayu/host/waiting.py` 的 `DefaultHostResolveWaitService.resolve_wait(...)` 是当前 wait completion 的状态迁移 owner；callback 必须调用该路径，不得直接 append EventLog 或修改 Run / Attempt / wait record。
- `dayu/host/wait_adapter.py` 已有 poller adapter 和 activation adapter 边界，模块 docstring 明确当前不实现 callback endpoint；callback adapter 应与 poller/manual converge 到同一 `ResolveWaitRequest`。
- `tests/host/test_resolve_wait_command.py` 已覆盖 resolve wait replay、idempotency conflict、failed/lost terminal、cancelled outcome 和 late rejection；plan 应复用这些测试边界，不重复设计状态机。

### Plan Gate 约束

- Plan 必须明确 callback endpoint 的形式：Host core 提供框架无关 typed callback contract / adapter；Service / Web 层负责真实 HTTP route、header/body 读取和 transport status mapping。不得把 FastAPI、Flask 或其它 HTTP framework 放入 Host core。
- Plan 必须定义 callback request envelope 的字段语义：auth source / claims、wait id、idempotency key、payload digest、observed/completed timestamp、typed outcome refs/payload，以及哪些字段属于 transport 诊断而不是 Host durable truth。
- Plan 必须说明认证失败、malformed payload、payload digest mismatch、unknown wait id、cancelled/lost late callback、同 key 不同 outcome digest conflict、successful replay 分别如何映射为 typed result / HostApiError / diagnostic / HTTP adapter status。
- Plan 必须证明 endpoint adapter 不直接写 EventLog、Run、Attempt 或 wait record；所有 terminal state changes 只能通过 `resolve_wait`。
- Plan 必须控制 slice 成本。小型同一语义 cleanup 默认 1-3 个 implementation slices；如果超过 3 个 slices，必须证明不能按 callback contract / adapter mapping / Service route or tests 的闭环合并。
- Plan 不得实现 #90 production poller loop、#92 physical cancel / revoke / abandon、Claude Code / Codex UI parity、Engine awaiting model 变更或新的 public wait lifecycle。

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

Goal confirmation 已由用户确认。Plan artifact 为 `docs/host/wu-wait-03-external-job-lifecycle-plan.md`。Plan review artifacts 为 `docs/reviews/wu-wait-03-plan-review-mimo.md` 与 `docs/reviews/wu-wait-03-plan-review-ds.md`，controller adjudication 为 `docs/reviews/wu-wait-03-plan-review-controller-adjudication.md`。Plan-fix artifact 为 `docs/reviews/wu-wait-03-plan-fix-codex.md`。Plan re-review artifacts 为 `docs/reviews/wu-wait-03-plan-rereview-mimo.md` 与 `docs/reviews/wu-wait-03-plan-rereview-ds.md`，controller adjudication 为 `docs/reviews/wu-wait-03-plan-rereview-controller-adjudication.md`。Accepted plan commit 为 `6be72997`。Slice 1 implementation artifact 为 `docs/reviews/wu-wait-03-slice1-implementation-codex.md`；code review artifacts 为 `docs/reviews/wu-wait-03-slice1-code-review-mimo.md` 与 `docs/reviews/wu-wait-03-slice1-code-review-ds.md`；controller adjudication 为 `docs/reviews/wu-wait-03-slice1-code-review-controller-adjudication.md`。Slice 1 fix artifact 为 `docs/reviews/wu-wait-03-slice1-fix-codex.md`；code re-review artifacts 为 `docs/reviews/wu-wait-03-slice1-code-rereview-mimo.md` 与 `docs/reviews/wu-wait-03-slice1-code-rereview-ds.md`；controller adjudication 为 `docs/reviews/wu-wait-03-slice1-code-rereview-controller-adjudication.md`。Accepted Slice 1 commit 为 `4e661cee`。Slice 2 implementation artifact 为 `docs/reviews/wu-wait-03-slice2-implementation-codex.md`；AgentCodex reported Fins focused tests 125 passed, Host focused tests 35 passed, pyright 0 errors, and `git diff --check` passed. Controller reran the same validation with 125 passed and 35 passed, pyright with 0 errors, and `git diff --check` passed. Slice 2 code review artifacts 为 `docs/reviews/wu-wait-03-slice2-code-review-mimo.md` 与 `docs/reviews/wu-wait-03-slice2-code-review-ds.md`；controller adjudication 为 `docs/reviews/wu-wait-03-slice2-code-review-controller-adjudication.md`。Controller accepted one current-slice test coverage fix for cancel-side non-transient observation errors. Fix artifact 为 `docs/reviews/wu-wait-03-slice2-fix-codex.md`；AgentCodex reported Fins focused tests 126 passed, Host focused tests 35 passed, pyright 0 errors, and `git diff --check` passed. Controller reran the same validation with 126 passed and 35 passed, pyright with 0 errors, and `git diff --check` passed. Slice 2 code re-review artifacts 为 `docs/reviews/wu-wait-03-slice2-code-rereview-mimo.md` 与 `docs/reviews/wu-wait-03-slice2-code-rereview-ds.md`；controller adjudication 为 `docs/reviews/wu-wait-03-slice2-code-rereview-controller-adjudication.md`。两路 code re-review 均通过，accepted finding 已关闭，无 current-slice fix remaining。Accepted Slice 2 commit 为 `04fadb84`。Aggregate deepreview artifacts 为 `docs/reviews/wu-wait-03-aggregate-deepreview-mimo.md` 与 `docs/reviews/wu-wait-03-aggregate-deepreview-ds.md`；controller adjudication 为 `docs/reviews/wu-wait-03-aggregate-deepreview-controller-adjudication.md`。两路 aggregate deepreview 均无 blocking finding；controller accepted README sync fixes for `dayu/host/README.md` and `tests/README.md`。Aggregate fix artifact 为 `docs/reviews/wu-wait-03-aggregate-fix-codex.md`；AgentCodex reported `git diff --check` passed and no code/config/test logic changed。Controller reran `git diff --check` with pass。Aggregate re-review artifacts 为 `docs/reviews/wu-wait-03-aggregate-rereview-mimo.md` 与 `docs/reviews/wu-wait-03-aggregate-rereview-ds.md`；controller adjudication 为 `docs/reviews/wu-wait-03-aggregate-rereview-controller-adjudication.md`。两路 aggregate re-review 均通过，README sync findings 已关闭，无 aggregate fix remaining。Accepted aggregate commit 为 `848839e9`。Draft PR #166 已创建：https://github.com/noho/dayu-agent-r/pull/166。PR body 使用 `Closes #92`，merge 会自动关闭 #92。PR review artifacts 为 `docs/reviews/wu-wait-03-pr-166-review-mimo.md` 与 `docs/reviews/wu-wait-03-pr-166-review-ds.md`；controller adjudication 为 `docs/reviews/wu-wait-03-pr-166-review-controller-adjudication.md`。两路 PR review 均通过，无 blocking finding；DS low-severity stale control-doc gate text finding 已接受并修复。Final closeout artifact 为 `docs/reviews/wu-wait-03-final-closeout.md`。Residual risk reconciliation artifact 为 `docs/reviews/wu-wait-03-residual-risk-reconciliation.md`；provider best-effort、future `CANCEL` / `REVOKE` diagnostics、missing GitHub checks 和 tool/provider blocking I/O hard interruption 均已裁决为非当前 residual；production poller composition validation 由 WU-WAIT-04 追踪，generic tool/provider hardening 由普通 deferred WU `WU-TOOLS-CANCEL-01` 追踪。Issue closeout comment 已发布：https://github.com/noho/dayu-agent-r/issues/92#issuecomment-4880126795。当前进入 final-closeout-pass，等待用户 / maintainer 处理 draft PR #166；不得未经授权 mark ready、merge、close issue、request reviewers 或 delete branch。

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

依赖 WU-WAIT-01 / GitHub Issue #89、WU-WAIT-02 / GitHub Issue #90、WU-WAIT-03 / GitHub Issue #92、WU-LIFE-03、WU-LIFE-04 与 WU-TOOLS-CANCEL-01；不是可独立实施的 work unit。前置能力完成后，本条才作为 production-grade end-to-end smoke 进入 implementation gate。

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
