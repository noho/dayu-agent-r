# Host Issues Implementation Control

## 文档职责

本文档是 Host follow-up 中已由 GitHub Issue、umbrella issue、依赖链或过期裁决承接的 work units 实施总控文档。

本文档只承担实施编排职责：记录 issue-backed work unit 的范围、当前状态、issue owner / destination、进入条件、交付物、验证要求、review 结果、residual risk 和下一步入口。

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

本文档不管理未建立 GitHub Issue 且可独立推进的 work unit。若某个 work unit 后续获得新的 GitHub Issue owner / destination，必须先在本文档中新增或更新对应条目，再按本文档状态进入 discussion / plan / implementation gate。

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

进入 draft PR gate 前，本文档必须更新当前 work unit 状态、plan artifact、review artifact、accepted commit、remaining risks / owners、GitHub Issue destination 和 next entry point。用户授权进入 draft PR gate 后，按既定 gate workflow 自动推进到 `draft-PR-pass`；merge、approve、mark ready for review、request reviewers、delete branch、对外 comment 或创建 / 修改外部 issue 仍需额外授权。

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
| gate | accepted-slice-commit |
| implementation status | WU-DUR-P01 / WU-OBS-P00 / WU-CM-01-F02 / WU-CM-01-F01 closeout chain plan-ready |
| active work unit | WU-DUR-P01 / WU-OBS-P00 / WU-CM-01-F02 / WU-CM-01-F01 |
| default next work unit | WU-DUR-P01 |
| next entry point | Create accepted Slice 0 commit for docs/host/design.md contract writeback and design review artifacts |
| design source | 由 phaseflow 调用参数提供；本文档只维护 issue-backed 实施总控状态 |
| plan artifacts | docs/host/wu-cm-01-conversation-memory-plan.md; docs/host/wu-dur-obs-cm-closeout-plan.md |
| implementation commits | WU-DUR-P01 / WU-OBS-P00 / WU-CM-01-F02 / WU-CM-01-F01 closeout chain accepted plan commit c1e9de3f; WU-CM-01 accepted plan commit 14d28009; WU-CM-01 plan reslice accepted commit a92416ec; WU-CM-01 compact contract closure accepted plan commit daa01004; WU-CM-01 compact contract closure blocker follow-up accepted commit ff6c225a; WU-CM-01 compact contract closure accepted slice commit b2b57c18; WU-CM-01 Slice C policy contract plan fix accepted commit 49990e97; WU-CM-01 Slice C accepted commit 29c86355; WU-CM-01 Slice D accepted commit 30a426b4; WU-CM-01 aggregate deepreview accepted commit 2248a395; WU-CM-01 accepted PR review commit f2db943f; WU-CM-01 deferred risk cleanup accepted commit 30759116d00d0ca58308e74b9f61a0ecc5b6ad9a; WU-CM-01 Slice A accepted commit f060853d; WU-CM-01 Slice B accepted commit 74fbb5e6; WU-ENG-02 merged via PR 114 as 58fb7a42a2a096ab279863250a9ffe63f63f0edc; WU-ENG-01 accepted commit 70a5a4e merged via PR 113 |
| review artifacts | docs/reviews/wu-cm-01-plan-review-mimo.md; docs/reviews/wu-cm-01-plan-review-ds.md; docs/reviews/wu-cm-01-plan-review-controller-adjudication.md; docs/reviews/wu-cm-01-plan-fix-codex.md; docs/reviews/wu-cm-01-plan-rereview-mimo.md; docs/reviews/wu-cm-01-plan-rereview-ds.md; docs/reviews/wu-cm-01-plan-rereview-controller-adjudication.md; docs/reviews/wu-cm-01-implementation-codex.md; docs/reviews/wu-cm-01-plan-reslice-fix-codex.md; docs/reviews/wu-cm-01-plan-reslice-rereview-mimo.md; docs/reviews/wu-cm-01-plan-reslice-rereview-ds.md; docs/reviews/wu-cm-01-plan-reslice-rereview-controller-adjudication.md; docs/reviews/wu-cm-01-slice-a-implementation-codex.md; docs/reviews/wu-cm-01-slice-a-code-review-mimo.md; docs/reviews/wu-cm-01-slice-a-code-review-ds.md; docs/reviews/wu-cm-01-slice-a-code-review-controller-adjudication.md; docs/reviews/wu-cm-01-slice-a-fix-codex.md; docs/reviews/wu-cm-01-slice-a-rereview-mimo.md; docs/reviews/wu-cm-01-slice-a-rereview-ds.md; docs/reviews/wu-cm-01-slice-a-rereview-controller-adjudication.md; docs/reviews/wu-cm-01-slice-b-implementation-codex.md; docs/reviews/wu-cm-01-slice-b-blocker-controller-adjudication.md; docs/reviews/wu-cm-01-slice-b-plan-fix-codex.md; docs/reviews/wu-cm-01-slice-b-plan-fix-rereview-mimo.md; docs/reviews/wu-cm-01-slice-b-plan-fix-rereview-ds.md; docs/reviews/wu-cm-01-slice-b-plan-fix-rereview-controller-adjudication.md; docs/reviews/wu-cm-01-slice-b-plan-fix-followup-codex.md; docs/reviews/wu-cm-01-slice-b-plan-fix-followup-controller-adjudication.md; docs/reviews/wu-cm-01-slice-b-code-review-mimo.md; docs/reviews/wu-cm-01-slice-b-code-review-ds.md; docs/reviews/wu-cm-01-slice-b-code-review-controller-adjudication.md; docs/reviews/wu-cm-01-slice-b-fix-codex.md; docs/reviews/wu-cm-01-slice-b-rereview-mimo.md; docs/reviews/wu-cm-01-slice-b-rereview-ds.md; docs/reviews/wu-cm-01-slice-b-rereview-controller-adjudication.md; docs/reviews/wu-cm-01-slice-c-implementation-codex.md; docs/reviews/wu-cm-01-slice-c-blocker-controller-adjudication.md; docs/reviews/wu-cm-01-slice-c-plan-fix-codex.md; docs/reviews/wu-cm-01-compact-contract-closure-plan-codex.md |
| slice c plan fix follow-up artifacts | docs/reviews/wu-cm-01-slice-c-plan-fix-rereview-mimo.md; docs/reviews/wu-cm-01-slice-c-plan-fix-rereview-ds.md; docs/reviews/wu-cm-01-slice-c-plan-fix-rereview-controller-adjudication.md; docs/reviews/wu-cm-01-slice-c-plan-fix-followup-codex.md; docs/reviews/wu-cm-01-slice-c-plan-fix-followup-controller-adjudication.md |
| slice c plan boundary follow-up artifacts | docs/reviews/wu-cm-01-slice-c-plan-boundary-followup-codex.md; docs/reviews/wu-cm-01-slice-c-plan-boundary-followup-controller-adjudication.md |
| slice c implementation blocker artifacts | docs/reviews/wu-cm-01-slice-c-implementation-codex.md; docs/reviews/wu-cm-01-slice-c-implementation-blocker-controller-adjudication.md; docs/reviews/wu-cm-01-slice-c-implementation-retry-codex.md; docs/reviews/wu-cm-01-slice-c-implementation-retry-blocker-controller-adjudication.md |
| slice c policy contract plan fix artifacts | docs/reviews/wu-cm-01-slice-c-policy-contract-plan-fix-codex.md |
| slice c policy contract plan fix review artifacts | docs/reviews/wu-cm-01-slice-c-policy-contract-plan-fix-review-mimo.md; docs/reviews/wu-cm-01-slice-c-policy-contract-plan-fix-review-ds.md |
| slice c policy contract plan fix artifacts after review | docs/reviews/wu-cm-01-slice-c-policy-contract-plan-fix-review-fix-codex.md |
| slice c policy contract plan fix re-review artifacts | docs/reviews/wu-cm-01-slice-c-policy-contract-plan-fix-rereview-mimo.md; docs/reviews/wu-cm-01-slice-c-policy-contract-plan-fix-rereview-ds.md; docs/reviews/wu-cm-01-slice-c-policy-contract-plan-fix-rereview-controller-adjudication.md |
| slice c implementation retry2 artifacts | docs/reviews/wu-cm-01-slice-c-implementation-retry2-codex.md |
| slice c code review artifacts | docs/reviews/wu-cm-01-slice-c-code-review-mimo.md; docs/reviews/wu-cm-01-slice-c-code-review-ds.md; docs/reviews/wu-cm-01-slice-c-code-review-controller-adjudication.md |
| slice c fix artifacts | docs/reviews/wu-cm-01-slice-c-fix-codex.md |
| slice c fix re-review artifacts | docs/reviews/wu-cm-01-slice-c-rereview-mimo.md; docs/reviews/wu-cm-01-slice-c-rereview-ds.md; docs/reviews/wu-cm-01-slice-c-rereview-controller-adjudication.md |
| slice d implementation artifacts | docs/reviews/wu-cm-01-slice-d-implementation-codex.md |
| slice d code review artifacts | docs/reviews/wu-cm-01-slice-d-code-review-mimo.md; docs/reviews/wu-cm-01-slice-d-code-review-ds.md; docs/reviews/wu-cm-01-slice-d-code-review-controller-adjudication.md |
| slice c engine ingest / context governance boundary follow-up artifacts | docs/reviews/wu-cm-01-slice-c-engine-ingest-context-governance-boundary-followup-codex.md; docs/reviews/wu-cm-01-slice-c-engine-ingest-context-governance-boundary-followup-controller-adjudication.md |
| slice c compact contract blocker artifacts | docs/reviews/wu-cm-01-slice-c-implementation-codex.md; docs/reviews/wu-cm-01-slice-c-compact-contract-blocker-controller-adjudication.md |
| compact contract closure plan artifacts | docs/reviews/wu-cm-01-compact-contract-closure-plan-codex.md |
| compact contract closure plan review artifacts | docs/reviews/wu-cm-01-compact-contract-closure-plan-review-mimo.md; docs/reviews/wu-cm-01-compact-contract-closure-plan-review-ds.md; docs/reviews/wu-cm-01-compact-contract-closure-plan-review-controller-adjudication.md |
| compact contract closure plan fix artifacts | docs/reviews/wu-cm-01-compact-contract-closure-plan-fix-codex.md |
| compact contract closure plan re-review artifacts | docs/reviews/wu-cm-01-compact-contract-closure-plan-rereview-mimo.md; docs/reviews/wu-cm-01-compact-contract-closure-plan-rereview-ds.md; docs/reviews/wu-cm-01-compact-contract-closure-plan-rereview-controller-adjudication.md |
| compact contract closure implementation blocker artifacts | docs/reviews/wu-cm-01-compact-contract-closure-implementation-codex.md; docs/reviews/wu-cm-01-compact-contract-closure-blocker-controller-adjudication.md |
| compact contract closure plan blocker fix artifacts | docs/reviews/wu-cm-01-compact-contract-closure-plan-blocker-fix-codex.md |
| compact contract closure plan blocker fix re-review artifacts | docs/reviews/wu-cm-01-compact-contract-closure-plan-blocker-fix-rereview-mimo.md; docs/reviews/wu-cm-01-compact-contract-closure-plan-blocker-fix-rereview-ds.md; docs/reviews/wu-cm-01-compact-contract-closure-plan-blocker-fix-rereview-controller-adjudication.md |
| compact contract closure plan blocker follow-up fix artifacts | docs/reviews/wu-cm-01-compact-contract-closure-plan-blocker-followup-fix-codex.md |
| compact contract closure plan blocker follow-up fix re-review artifacts | docs/reviews/wu-cm-01-compact-contract-closure-plan-blocker-followup-fix-rereview-mimo.md; docs/reviews/wu-cm-01-compact-contract-closure-plan-blocker-followup-fix-rereview-ds.md; docs/reviews/wu-cm-01-compact-contract-closure-plan-blocker-followup-fix-rereview-controller-adjudication.md |
| compact contract closure implementation artifacts | docs/reviews/wu-cm-01-compact-contract-closure-implementation-retry-codex.md |
| compact contract closure code review artifacts | docs/reviews/wu-cm-01-compact-contract-closure-code-review-mimo.md; docs/reviews/wu-cm-01-compact-contract-closure-code-review-ds.md; docs/reviews/wu-cm-01-compact-contract-closure-code-review-controller-adjudication.md |
| compact contract closure fix artifacts | docs/reviews/wu-cm-01-compact-contract-closure-fix-codex.md |
| compact contract closure fix re-review artifacts | docs/reviews/wu-cm-01-compact-contract-closure-fix-rereview-mimo.md; docs/reviews/wu-cm-01-compact-contract-closure-fix-rereview-ds.md; docs/reviews/wu-cm-01-compact-contract-closure-fix-rereview-controller-adjudication.md |
| closeout chain plan review artifacts | docs/reviews/wu-dur-obs-cm-closeout-plan-review-mimo.md; docs/reviews/wu-dur-obs-cm-closeout-plan-review-ds.md; docs/reviews/wu-dur-obs-cm-closeout-plan-review-controller-adjudication.md |
| closeout chain plan fix artifacts | docs/reviews/wu-dur-obs-cm-closeout-plan-fix-codex.md |
| closeout chain plan re-review artifacts | docs/reviews/wu-dur-obs-cm-closeout-plan-rereview-mimo.md; docs/reviews/wu-dur-obs-cm-closeout-plan-rereview-ds.md; docs/reviews/wu-dur-obs-cm-closeout-plan-rereview-controller-adjudication.md |
| closeout chain slice 0 implementation artifacts | docs/reviews/wu-dur-obs-cm-closeout-slice0-implementation-codex.md |
| closeout chain slice 0 design review artifacts | docs/reviews/wu-dur-obs-cm-closeout-design-review-mimo.md; docs/reviews/wu-dur-obs-cm-closeout-design-review-ds.md; docs/reviews/wu-dur-obs-cm-closeout-design-review-controller-adjudication.md |
| aggregate review artifacts | docs/reviews/wu-cm-01-aggregate-deepreview-mimo.md; docs/reviews/wu-cm-01-aggregate-deepreview-ds.md; docs/reviews/wu-cm-01-aggregate-deepreview-controller-adjudication.md; docs/reviews/wu-cm-01-aggregate-deepreview-fix-codex.md; docs/reviews/wu-cm-01-aggregate-rereview-mimo.md; docs/reviews/wu-cm-01-aggregate-rereview-ds.md; docs/reviews/wu-cm-01-aggregate-rereview-controller-adjudication.md |
| PR review artifacts | docs/reviews/wu-cm-01-pr-review-mimo.md; docs/reviews/wu-cm-01-pr-review-ds.md; docs/reviews/wu-cm-01-pr-review-controller-adjudication.md; docs/reviews/wu-cm-01-pr-review-fix-codex.md; docs/reviews/wu-cm-01-pr-rereview-mimo.md; docs/reviews/wu-cm-01-pr-rereview-ds.md; docs/reviews/wu-cm-01-pr-rereview-controller-adjudication.md; docs/reviews/wu-cm-01-pr-deferred-risk-controller-adjudication.md; docs/host/wu-cm-01-deferred-risk-cleanup-plan.md; docs/reviews/wu-cm-01-deferred-risk-cleanup-implementation-codex.md; docs/reviews/wu-cm-01-deferred-risk-cleanup-review-mimo.md; docs/reviews/wu-cm-01-deferred-risk-cleanup-review-ds.md; docs/reviews/wu-cm-01-deferred-risk-cleanup-rereview-mimo.md; docs/reviews/wu-cm-01-deferred-risk-cleanup-rereview-ds.md; docs/reviews/wu-cm-01-deferred-risk-cleanup-controller-adjudication.md |
| draft PR status | WU-CM-01 draft PR 116 open at https://github.com/noho/dayu-agent-r/pull/116; branch `phaseflow/wu-cm-01` pushed through control-doc bookkeeping commit a63351d62da313b233ff18825c6e59f1f2ce0ef7 before final closeout record; GitHub reported no checks on branch `phaseflow/wu-cm-01`; WU-ENG-02 PR 114 merged at 2026-06-03 09:33:38 UTC as 58fb7a42a2a096ab279863250a9ffe63f63f0edc; WU-ENG-01 PR 113 merged at 2026-06-03 05:14:07 UTC as bc50e26c45296171487272ff5fc2293db67a9246 |
| blocking open questions | none |
| current inspection note | 2026-06-05 phaseflow resumed after WU-CM-01 PR merge. Goal confirmation accepted the dependency chain WU-DUR-P01 -> WU-OBS-P00 -> WU-CM-01-F02 -> WU-CM-01-F01, with WU-CM-01-F01 as public smoke validation for the first three WU. AgentCodex completed plan artifact `docs/host/wu-dur-obs-cm-closeout-plan.md`; AgentMiMo and AgentDS plan review found blocking plan specificity gaps. Controller accepted the blocking findings in `docs/reviews/wu-dur-obs-cm-closeout-plan-review-controller-adjudication.md`; AgentCodex completed plan fix artifact `docs/reviews/wu-dur-obs-cm-closeout-plan-fix-codex.md`; AgentMiMo and AgentDS re-review both passed with 0 unfixed / partial findings and 0 new blocking findings. Accepted plan commit is c1e9de3f. AgentCodex completed Slice 0 design contract writeback artifact `docs/reviews/wu-dur-obs-cm-closeout-slice0-implementation-codex.md`; AgentMiMo and AgentDS Slice 0.5 design review both returned pass-with-findings with 0 blocking findings. Controller accepted Slice 0; next gate is accepted Slice 0 commit. |

状态约定：

- `not-started`：尚未进入 plan / implementation。
- `discussion-ready`：已具备讨论和代码 / issue 核对入口，但还未形成 code-generation-ready plan。
- `blocked-by-issue`：需要等待指定 GitHub Issue / umbrella / dependency 完成。
- `obsolete`：已裁决过期失效，不作为实施入口。
- `planning`：正在形成或 review code-generation-ready plan。
- `implementation`：正在实施或修复。
- `review`：正在进行 code review、re-review 或 aggregate deepreview。
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
- 每个 work unit 进入 plan、implementation、review、ready-to-open-draft-PR 或 draft-PR-pass 时，必须更新“当前状态”中的 gate、active work unit、artifact、commit、review 和 residual risk 信息。

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

| ID | 来源 | 类型 | 状态 | Owner / Destination | 下一步 | 记录 |
|---|---|---|---|---|---|---|
| WU-ENG-02-S3-R1 | WU-ENG-02 Slice 3 code review | analyzer 需求边界 | deferred-with-owner | WU-OBS-00 / GitHub Issue #70 analyzer | analyzer 实施时确认 usage observation projection signal 是否需要 `client_correlation_id` 与 `provider_request_id`，若需要先扩展 Engine `UsageReportedData` / Runner usage event contract，再补 Host payload / Tool Trace tests | PR 114 residual review 裁决保留 defer：usage 是 post-call observation / analyzer signal，不是 provider debugging terminal 主链路；`UsageReportedData` 当前无 correlation fields，且 usage event 发生时 provider request id 不总是可用，不能在 residual fix gate 单独定死 analyzer 关联语义。已在 issue-70 留痕：https://github.com/noho/dayu-agent-r/issues/70#issuecomment-4610820571 |

## 当前 Work Units

| Work Unit | 状态 | 主题 | Owner / Destination | 当前定位 |
|---|---|---|---|---|
| WU-ENG-01 | completed | provider_state 与 reasoning_content 写回策略优化 | GitHub Issue #10 | completed；PR 113 已 merge，稳定结论是 provider reasoning roundtrip 为协议要求，不进入 payload behavior change |
| WU-ENG-02 | completed-with-follow-up | Provider request identity and vendor debugging correlation | GitHub Issue #63 closed；#64 current shared scope completed, native adapter-specific scope remains open | tool trace analyze 发现 provider/model bug 后，用 provider 可查 request id 向厂商报障；typed request identity 与 OpenAI-compatible correlation scope 已完成，#64 保留 native Anthropic / Claude Code gateway adapter-specific 后续语义 |
| WU-CM-01 | final-closeout-follow-up | Conversation Memory overall optimization | GitHub Issue #81 | #81 umbrella 的正式 implementation entry point |
| WU-CM-01-F01 | planned-validation-slice | Conversation Memory smoke correctness closeout | GitHub Issue #81 / WU-CM-01 final closeout | 当前 closeout chain 的最终 public smoke validation slice；验证 WU-DUR-P01 / WU-OBS-P00 / WU-CM-01-F02 后的 runner-call input manifest、compact query readability 与 prompt 语义收敛 |
| WU-CM-01-F02 | planned-after-dur | Compact evidence query readability quality closeout | GitHub Issue #81 / WU-CM-01 final closeout；depends on WU-DUR-P01 durable tool-call atoms | 当前 closeout chain 的 compact evidence readability slice；必须消费 WU-DUR-P01 durable tool-call arguments / semantic query atom，不用 prompt 猜测或 hardcode 伪造 query text |
| WU-CM-02 | closed | working_assumptions 生产者语义 | GitHub Issue #81 / WU-CM-01 | 已裁决；reject 旧 `working_assumptions` 独立语义，不单独实施，删除 / 迁移旧字段由 WU-CM-01 schema / projection slice 承接 |
| WU-CM-03 | closed | fact-candidate-only validation failure 策略 | GitHub Issue #81 / WU-CM-01 | 已裁决；fact candidate invalid 必须 fail closed / whole-candidate repair retry，不 partial materialize，独立 WU closed |
| WU-CM-04 | closed | minimum preserve 与 Fins 事实边界 | GitHub Issue #81 / Fins integration | 已裁决；minimum preserve 是 bounded continuity item，不是事实真源，独立 WU closed；后续 Fins integration 继承该边界 |
| WU-TOOLS-01 | pending | Fins / Web / Doc tools migration with shared document foundations | GitHub Issue #82 / #97 / #98 | 单一 work unit，先迁移 shared document foundations，再按 Doc tools、Fins、Web tools slice 实施 |
| WU-PROJ-01 | pending | Projection catch-up budgeting | GitHub Issue #86 | memory pre-dispatch projection catch-up budgeting |
| WU-DUR-P01 | accepted-slice-0-pending-commit | EventLog runner-call reconstruction atoms | GitHub Issue #117 | Slice 0 design contract writeback 已通过 design review；等待 accepted Slice 0 commit 后进入 Slice 1 durable tool-call request atoms implementation |
| WU-OBS-P00 | planned-after-dur | Runner call input reconstruction signals | GitHub Issue #70 / #117 | 当前 closeout chain 的 Tool Trace signal slice；只能消费 WU-DUR-P01 refs / digests / projector metadata，不把 Tool Trace 提升为事实真源 |
| WU-OBS-P01 | pending | Tool Trace context budget snapshot signals | GitHub Issue #29 | WU-OBS-00 前置；NEW / dayu-agent-r 对齐 OLD / dayu-agent analyzer 的 context pressure 信号 |
| WU-OBS-P02 | pending | Tool Trace tool latency signals | GitHub Issue #30 | WU-OBS-00 前置；NEW / dayu-agent-r 补齐 tool latency stable signal |
| WU-OBS-P03 | pending | Tool Trace structured failure metadata | GitHub Issue #31 | WU-OBS-00 前置；NEW / dayu-agent-r 补齐 failure signature / repair hint stable signal |
| WU-OBS-P04 | pending | Provider protocol partial tool-call trace signals | GitHub Issue #35 | WU-OBS-00 前置；NEW / dayu-agent-r 补齐 provider protocol error partial tool-call stable trace signal |
| WU-OBS-00 | pending-prerequisite | Tool Trace analyzer | GitHub Issue #70 | trace 文件 / 目录输入的 Host / Engine / Tool 分层诊断；WU-OBS-01 的诊断底座 |
| WU-OBS-00A | pending-parent | Tool Trace analyzer integrity and large payload diagnostics | GitHub Issue #34 / #70 child | #70 analyzer 子项；不单独实现一套 analyzer |
| WU-OBS-01 | pending-prerequisite | Prompt-based Tool Trace diagnostics | GitHub Issue #71；GitHub Issue #27 superseded | #71 作为主 issue，吸收 #27 的 prompt / final answer 反查诉求 |
| WU-AUDIT-01 | pending | Audit Ledger viewer and integrity report | GitHub Issue #72 | read-only audit JSONL ledger viewer；审计责任链 / 完整性校验，不做 Tool Trace root-cause analyzer |
| WU-AUDIT-02 | pending | External audit delivery contract with local validation adapters | GitHub Issue #75 | async external audit delivery 语义；无真实外部系统时先用 Noop / FileMirror adapter 验证 contract |
| WU-RET-00 | in-progress-partial | Host storage lifecycle retention policy | GitHub Issue #43 | retention umbrella；purge 已完成，剩余 payload / descriptor / DB / workspace-level cleanup |
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
| WU-CM-05 | deferred | LLM compaction proposal typed parsing | GitHub Issue #93 / #81 child | deferred behind #81 |
| WU-CM-06 | deferred | Terminal summary text policy convergence | GitHub Issue #94 / #81 child | deferred behind #81 |
| WU-CM-07 | obsolete | Evidence validation and pinned state cleanup | obsolete / #81 semantic model | 过期失效，不独立推进 |
| WU-CM-08 | deferred | Compaction material readability and smoke maintenance | GitHub Issue #95 / #81 child | #81 子任务，测试可维护性 cleanup |
| WU-CM-09 | deferred | Durable memory snapshot corruption policy | GitHub Issue #41 | deferred behind #81；post-#81 durable memory hardening / operator repair policy |
| WU-CM-10 | deferred | Conversation Memory eval benchmark | GitHub Issue #80 / #81 follow-up | deferred behind #81；post-#81 memory semantic contract 稳定后再实施 |
| WU-CM-11 | deferred | User Profile Memory durable boundary and cross-session profile | GitHub Issue #115 / #81 child | deferred behind #81；#81 只固定 User Profile 不混入 session Conversation Memory 的边界，跨 session durable profile 独立后续实施 |

## WU-ENG-01 Provider State And Reasoning Content Roundtrip Policy

### 状态

completed。PR 113 已 merge，merge commit 为 `bc50e26c45296171487272ff5fc2293db67a9246`。GitHub Issue #10 当前仍为 OPEN，但 discussion / 代码 / provider API 文档核对后裁决：原先把 `AssistantMessage.reasoning_content is not None` 时写回 outbound `reasoning_content` 视为“无条件写回 bug”的动机被高估。MiMo、DeepSeek、Qwen 等 thinking + tool-call provider 要求把上一轮 assistant 的 `reasoning_content` 原样带回；Gemini 要求把 `thought_signature` 原样带回。因此当前 work unit 不进入 payload behavior change，已收敛为 issue 记录、docstring / 测试说明修正与 provider roundtrip 证据固化。

### 设计与代码核对

- `docs/host/design.md` 仅涉及 Host 如何暴露 thinking / tool events，不拥有 provider-specific reasoning roundtrip 策略。
- `docs/engine/design.md` 已定义 `ToolCallProviderState` 是封闭 provider-specific 联合，当前成员为 `GeminiToolCallState`，用于 Gemini `thought_signature` roundtrip。
- `docs/engine/migration-plan.md` 曾把 Phase 3 的 `reasoning_content` 写回标为过渡实现；本次核对后裁决为：不能在没有 provider API / 真实 smoke 证据证明当前 payload 错误时改动 request / response 行为。
- `dayu/contracts/tool_call.py` 已实现 `GeminiToolCallState` 与 `ToolCallProviderState` 强类型通道。
- `dayu/engine/runners/openai/payload.py` 在 assistant message serialization 中保留非空 `reasoning_content`，该字段来自 provider response / Engine 历史回放，不由 Host 或 payload builder 凭空生成。
- `tests/engine/runners/openai/test_payload_assistant_reasoning_content_preserved.py` 应从“OLD 兼容保留性”改写为“thinking tool-call roundtrip provider requirement”测试说明。
- Provider API 证据：MiMo / DeepSeek thinking mode 在多轮 tool-call 场景要求 assistant `reasoning_content` 原样回传；Qwen thinking tool-call 文档要求发送 tool results 时包含 assistant `reasoning_content`；Gemini thinking / function calling 要求回传 thought signature。

### 目标

- 不改变当前已能运行的 provider request / response payload；只有 API 文档、真实 smoke 或可复现 provider 行为证明当前 payload 错误时，才允许 provider-specific payload 调整。
- 固化 reasoning / thinking roundtrip 证据：MiMo / DeepSeek / Qwen 的 `reasoning_content` 与 Gemini 的 `thought_signature` 是 provider 协议的一部分，不是 Host 治理字段。
- 修正文档和测试描述，避免把正确的 provider roundtrip 行为继续写成“OLD 过渡兼容”或“待删除的无条件写回”。
- 若未来 provider 需要新增 roundtrip state，仍优先通过 `ToolCallProviderState` 封闭联合扩展，或通过 provider adapter 的显式请求投影表达。
- 保持 Runner / Agent / ToolExecutor 边界：Runner 只做 provider payload 投影，不重新执行工具，不依赖 `ToolExecutor`。
- 更新 payload builder docstring、tests 和相关 Engine README，使当前稳定行为按 provider API contract 表述。

### 非目标

- 不把 `reasoning_content` 塞进 `metadata`、裸 dict、`Any` 或 provider 字符串分支。
- 不伪造尚无证据的 provider-specific state。
- 不让 Host / EngineWorker 的治理所有权进入 `provider_state`。
- 不让 Engine 反向依赖 Host / Service / UI / Fins。
- 不在本条内实现 Host ToolRuntime、WAIT、memory、context governance 或 UI behavior。

### 验收信号

- 每个 provider 的 reasoning roundtrip 策略有明确证据来源。
- 当前已能运行的 MiMo / DeepSeek / Qwen / Gemini request / response 行为不被改变。
- MiMo / DeepSeek / Qwen 的 `reasoning_content` roundtrip 与 Gemini 的 `thought_signature` roundtrip 在 docstring / tests 中被明确为 provider API requirement。
- `ToolCallProviderState` 仍是封闭强类型联合；新增成员时所有 parser / serializer match 分支穷尽。
- 相关 tests 从“OLD 兼容保留性”改为 thinking tool-call roundtrip requirement 测试。
- pyright 不新增或扩散类型错误。

## WU-ENG-02 Provider Request Identity And Vendor Debugging Correlation

### 状态

GitHub Issue #63 已关闭，关闭依据为 WU-ENG-02 / PR 114 accepted scope 已完成 OpenAI-compatible provider debugging correlation。GitHub Issue #64 保持 OPEN；WU-ENG-02 已完成 #64 在当前仓库可实施的 shared typed request identity / provider policy boundary scope，剩余 native Anthropic response `request-id` 与 Claude Code gateway `X-Claude-Code-Session-Id` 行为属于未来 native adapter-specific scope。两条 issue 的共同目标不是引入用户治理字段，而是：当 `tool trace analyze` 发现 provider/model 行为疑似 bug 时，分析报告里必须能给出 provider 厂商可定位的 request id，并能回链到本地 `run_id` / iteration / attempt / tool trace。

Plan gate 已完成，artifact 为 `docs/host/wu-eng-02-provider-request-identity-plan.md`，无 blocking open questions。Plan review gate 已完成，AgentMiMo 与 AgentDS 均裁决 `pass-with-findings` 且无 blocking open questions。Plan fix gate 已完成，artifact 为 `docs/reviews/wu-eng-02-plan-fix-codex.md`，8 条 accepted findings 均标记已修复。Plan re-review gate 已完成，AgentMiMo 与 AgentDS 均裁决 `pass`，0 条未修复 / 部分修复，无新增 blocking issue。当前 plan 已接受，accepted plan commit 为 `59f66b7`。Implementation Slice 1（Engine contract and Agent identity）已由 AgentCodex 实施，artifact 为 `docs/reviews/wu-eng-02-slice1-implementation-codex.md`；验证结果为 127 个受影响 Engine tests passed，pyright 0 errors。Slice 1 code review gate 已完成，AgentMiMo 裁决 `pass`，AgentDS 裁决 `pass-with-findings`，均无 blocking open questions。当前进入 Slice 1 fix gate。

Slice 1 code review findings 裁决：

- accepted：EngineEvent / Agent outcome 中的 `client_correlation_id` 值缺少直接断言；应在现有 Engine Agent 测试中补齐关键 emitted event 的 correlation id 断言。
- accepted：`_validate_batch_bijection` 生成的 `RunFailedData` 未携带当前 tool batch 的 `client_correlation_id`，与同一路径 duplicate 检查不一致；应传入并写入该字段。
- rejected-with-reason：`RunnerRequestIdentity.__post_init__` 与 builder 重复校验属于防御性冗余，直接构造路径需要保留，不要求修改。
- rejected-with-reason：canonical part 编码方案已由类型前缀与长度前缀证明无歧义，不要求修改。
- deferred-with-owner：OpenAI header policy、Host projection / ingest、Tool Trace、README sync 按 accepted plan 进入 Slice 2 / Slice 3 / Slice 4。

Slice 1 fix gate 已完成，artifact 为 `docs/reviews/wu-eng-02-slice1-fix-codex.md`。两个 accepted findings 均标记已修复；验证结果为 127 个受影响 Engine tests passed，pyright 0 errors。Slice 1 re-review gate 已完成，AgentMiMo 与 AgentDS 均裁决 `pass`，0 条未修复 / 部分修复，无 blocking open questions。Slice 1 accepted commit 为 `c4826e0`。Slice 2 implementation gate 已完成，artifact 为 `docs/reviews/wu-eng-02-slice2-implementation-codex.md`；验证结果为 61 个受影响 tests passed，pyright 0 errors。Slice 2 code review gate 已完成，AgentMiMo 与 AgentDS 均裁决 `pass`，无 blocking open questions。Slice 2 fix gate 已完成，artifact 为 `docs/reviews/wu-eng-02-slice2-fix-codex.md`；已补充 `ClientCorrelationPolicy.DISABLED` 且 `request_identity=None` 时不发送 `X-Client-Request-Id` 的直接测试；验证结果为 40 个受影响 tests passed，pyright 0 errors。Slice 2 re-review gate 已完成，AgentMiMo 与 AgentDS 均裁决 `pass`，0 条 blocking findings；本地复验 `pytest tests/engine/runners/openai/test_request_identity.py tests/engine/contracts/test_runner_spec.py tests/engine/runners/openai/test_streaming_capability_and_content_type.py tests/engine/runners/openai/test_http_error_event.py tests/host/test_effective_execution_config.py` 结果为 62 passed，pyright 0 errors。Slice 2 accepted commit 为 `c3856b9`。Slice 3 implementation gate 已完成，artifact 为 `docs/reviews/wu-eng-02-slice3-implementation-codex.md`；验证结果为 184 个受影响 Host tests passed，pyright 0 errors。Slice 3 code review gate 已完成，AgentMiMo 裁决 `pass-with-findings`，AgentDS 裁决 `pass`，0 条 blocking findings；Controller 裁决无 accepted fix，新增 residual risks `WU-ENG-02-S3-R1` / `WU-ENG-02-S3-R2`。Slice 3 accepted commit 为 `5ddc4cb`。Slice 4 implementation gate 已完成，artifact 为 `docs/reviews/wu-eng-02-slice4-implementation-codex.md`；验证结果为 174 个 Engine tests passed、198 个 Host tests passed，pyright 0 errors。Slice 4 code review gate 已完成，AgentMiMo 与 AgentDS 均裁决 `pass`，0 条 blocking findings；Controller 裁决无 accepted fix，并关闭 `WU-ENG-02-S2-R1`。Slice 4 accepted commit 为 `896d483`。Aggregate deepreview gate 已完成，AgentMiMo 裁决 `pass-with-findings`，AgentDS 裁决 `pass`，0 条 blocking findings；Controller 裁决无 accepted fix，existing residual risks 均已有 owner。Accepted deepreview commit 为 `24af62b`。WU-ENG-02 draft PR 已创建：`https://github.com/noho/dayu-agent-r/pull/114`。PR review gate 已完成，AgentMiMo 与 AgentDS 均裁决 `pass`，0 条 blocking findings，PR diff 与本地 diff 一致，372 tests passed，pyright 0 errors。Accepted PR review commit 为 `824665c`。用户裁决 residual risks 若无硬性 defer 理由则在 PR 114 内关闭；residual risk fix gate 已由 AgentCodex 完成，artifact 为 `docs/reviews/wu-eng-02-residual-risk-fix-codex.md`。`WU-ENG-02-S1-R1`、`WU-ENG-02-S1-R2`、`WU-ENG-02-S2-R2`、`WU-ENG-02-S3-R2` 已改为 closed；`WU-ENG-02-S3-R1` 保留 deferred-with-owner，理由是需要 WU-OBS-00 / GitHub Issue #70 先扩展 usage observation / analyzer signal contract。Residual risk review gate 已完成，AgentMiMo 裁决 pass，AgentDS 裁决 pass-with-finding；Controller 接受 DS 低严重度测试覆盖 finding。Residual risk review fix gate 已完成，artifact 为 `docs/reviews/wu-eng-02-residual-risk-review-fix-codex.md`；已补齐第三个工具超时变体的 `client_correlation_id` 断言，验证结果为 125 tests passed，pyright 0 errors。Residual risk re-review gate 已完成，AgentMiMo 与 AgentDS 均裁决 pass，0 条 blocking findings；Controller 最终复验 125 个受影响 tests passed、71 个相关回归 tests passed、pyright 0 errors。Residual risk accepted commit 为 `8298958`。Residual Risk Reconciliation 已完成，artifact 为 `docs/reviews/wu-eng-02-residual-risk-reconciliation.md`；已关闭的 residual risk 已从 active residual 表删除，当前仅保留 `WU-ENG-02-S3-R1`，且 owner 为 WU-OBS-00 / GitHub Issue #70 analyzer。GitHub Issue #63 已关闭；GitHub Issue #64 已更新说明当前 shared contract scope 已由 PR 114 完成，native Anthropic / Claude Code gateway adapter-specific scope 继续保留。PR 114 已于 2026-06-03 09:33:38 UTC merge，merge commit 为 `58fb7a42a2a096ab279863250a9ffe63f63f0edc`。当前状态为 completed；后续入口已转入 WU-CM-01。

Slice 2 code review findings 裁决：

- accepted：补充 `ClientCorrelationPolicy.DISABLED` 且 `request_identity=None` 时不发送 `X-Client-Request-Id` 的直接测试。
- rejected-with-reason：`_has_client_request_id_header` 的 `:raises Exception: 不主动抛出异常。` 符合本仓库中文 docstring 异常说明风格，不要求修改。
- rejected-with-reason：`_build_request_headers` 的不可达 `ValueError` 是枚举扩展时的 fail-fast 防御分支，保留。
- deferred-with-owner：production assembly 默认 `DISABLED`、静态 header 冲突 `ValueError` 是否需上层结构化收口，交由 Slice 3 / aggregate review 裁决。

Slice 3 code review findings 裁决：

- deferred-with-owner：usage observation payload 不含 `client_correlation_id`。当前 `UsageReportedData` Engine contract 不含该字段，且该 projection signal 的 `provider_request_id` 是 hardcoded `None`，不属于本 Slice provider-related EngineEvent payload 主链路；若 issue-70 analyzer 需要该信号，交由 WU-OBS-00 / analyzer gate 先扩展 contract。
- rejected-with-reason：`CONTEXT_COMPACTION_REQUESTED` payload 通过 dict spread 附加 `client_correlation_id` 当前符合 plan，因为 context compaction builder / validator 负责 base payload，Host ingest 附加诊断字段不改变 base schema；未来若 builder 引入 strict whitelist，再由对应变更同步处理。
- rejected-with-reason：`_close_worker_lifecycle` 合成 `RunFailedData` 未显式传 `client_correlation_id=None` 只有风格差异，运行时语义与默认值一致，不进入 fix。
- rejected-with-reason：`_TerminalPlan` 无默认值而 `TerminalCloseoutInput` / `ContextRecoveryCloseInput` 有默认值是合理边界差异：内部 plan 强制调用方显式思考，run_transition 公共输入保持可选字段默认 `None`。
- deferred-with-owner：`ContextRecoveryCloseInput.client_correlation_id` 是否需要专用 validation / payload 单测交由 Slice 4 final validation 核对；当前间接覆盖与对称校验足以通过 Slice 3。

Plan review findings 裁决：

- accepted：force-answer / continuation / fallback 等所有 logical Runner call 都必须递增 `runner_call_index`，并补计划测试要求。
- accepted：`request_identity: RunnerRequestIdentity | None` 只允许 direct Runner / compactor 等非普通 Agent path 显式传 `None`；普通 Agent -> Runner call path 必须传 non-None identity，计划完成信号需改写。
- accepted：`AsyncRunner.call` 只新增 keyword-only `request_identity`，保留 `messages/options/tools` 位置参数以最小化变更。
- accepted：计划需避免 `_AsyncAgent` 重复散落 correlation 取值逻辑，优先模块级 helper 或 iteration state。
- accepted：`EngineRunOutcomeFailed` 应明确归类为 `AgentRunResult` outcome，不是 EngineEvent data class。
- accepted：`client_correlation_id` digest 长度需明确为完整 SHA-256 hex，即 `dayu-` + 64 hex。
- accepted：`ClientCorrelationPolicy` docstring 需说明 enum 是 provider-protocol-specific outbound mapping policy，不是 provider 名称分支。
- rejected-with-reason：`iteration_id` 与 `run_id` digest input 冗余不要求修改；冗余不影响正确性，且保留 `run_id` 作为本地根关联更贴合 issue-63 / issue-64。

### 设计与代码核对

- `docs/host/design.md` 已要求普通 Run 的 request metadata 可包含必要的 `client_request_id`、actor / source refs，但没有把 provider request identity 下沉成 Runner 公共契约。
- `AsyncRunner.call(messages, options, tools)` 当前没有 per-call request context；Agent 虽然拥有 `session_id` / `run_id` / `iteration_id`，但调用 runner 时只传 messages、options、tools。
- OpenAI-compatible runner 当前通过 response header `x-request-id` 提取 `provider_request_id`，并通过 RunnerEvent / Engine ingest / Tool Trace 热表进入本地诊断链路。
- OpenAI-compatible runner 当前构造 request headers 时只能合并 `RunnerSpec.headers`；`RunnerSpec.headers` 是 construction-time provider 配置，不适合写入 per-run / per-attempt 的动态 request id。
- 当前仓库没有 native Anthropic runner；#64 不能落成散落在 Host / Agent 里的 Anthropic 字符串分支，应先通过 provider capability / adapter policy 表达 native Anthropic 与 Claude Code gateway 的差异。
- 设计讨论记录：`run_id` 适合作为本地排障根 ID；`attempt_id` 更接近一次 Host 执行尝试，但仍不一定等于单次 provider HTTP 请求。tool calling 场景下同一 Attempt 可能包含多轮 iteration；runner transport retry 也可能产生多次 provider call。因此是否直接使用 `run_id`、`attempt_id` 或派生值，不在本总控提前定死，应在实施 plan gate 根据代码中的 Attempt / iteration / runner retry 边界确定。

### 目标

- 引入强类型 per-call Runner request identity / correlation context，由 Agent 在每次 runner call 时基于 `run_id`、iteration、attempt 或等价 execution context 构造，并传给 Runner。
- request identity 设计应保留 `run_id` 作为本地根关联，优先评估以 `attempt_id` + iteration / provider call index 派生 provider-call-level client correlation id；具体格式留到实施时结合真实 ID 约束、长度限制和 retry 语义裁决。
- 明确本地分析链路：`tool trace analyze` 输出能从 tool trace / terminal diagnostic 找到 provider-native request id，并回链到本地 `run_id` / iteration / attempt。
- OpenAI-compatible provider 在显式 capability / policy 允许时，把 per-call correlation id 映射为 `X-Client-Request-Id`，并继续采集响应 `x-request-id`。
- Anthropic native provider 的目标是采集响应 header `request-id`；Claude Code / gateway 场景只有在显式兼容模式开启时才映射 `X-Claude-Code-Session-Id`。
- 未来若公共契约显式提供 opaque end-user / actor id，可再映射 OpenAI `safety_identifier` 或 Anthropic `metadata.user_id`；当前不从内部 `session_id` 推导。

### 非目标

- 不把 `session_id`、`run_id` 或 UI / Service 用户概念伪装成 provider 的 end-user governance field。
- 不把 per-run / per-attempt 动态 ID 写进 `RunnerSpec.headers`。
- 不在 Host / Agent 中写 `if provider == "openai"` / `if provider == "anthropic"` 这类硬编码分支。
- 不要求本 work unit 同时实现 native Anthropic runner；若没有 native runner，先完成公共契约、adapter policy 与测试替身。
- 不改变 `RunnerEvent` 不携带 session/run ownership 的边界；关联应由 Agent / Host ingest 在 execution context 内完成。

### 验收信号

- Runner 公共契约有强类型 request identity / correlation 输入，且测试覆盖 Agent 传递、Runner 消费与无动态 ID 时的行为。
- 实施 plan 明确记录 client correlation id 的来源选择：裸 `run_id`、裸 `attempt_id` 或派生 provider-call-level ID，并说明为什么不会在多 iteration / retry 场景造成厂商定位歧义。
- OpenAI-compatible 请求在 policy 开启时包含合法 `X-Client-Request-Id`；值必须满足 provider 约束，例如 ASCII 与长度上限。
- provider response request id 继续被采集，并能在 tool trace analyze / diagnostic query 中与本地 run / attempt / tool trace 关联。
- Anthropic native / Claude Code gateway 的 request id / session header 语义在 adapter policy 中分开，不会误传 `metadata.user_id` 或普通 Anthropic API 不需要的 session header。
- 代码不出现新增 raw provider string 硬编码治理分支、裸 dict payload bag 或 fake user id。
- 相关 Engine / Host / Tool Trace analyzer tests 与 pyright 通过。

## WU-CM-01 Conversation Memory Overall Optimization

### 状态

GitHub Issue #81 当前是 Conversation Memory 整体优化 umbrella issue。Issue body 明确它不是 code-generation-ready implementation plan；本 work unit 是将 #81 通过 phaseflow / gateflow 转化为可实施 scope、plan、slices、review 和验收闭环的正式入口。

GitHub Issue #80 是 Conversation Memory 的评测标准真源。#80 的具体 eval 实现可以等待 #81 完成或形成稳定 post-#81 memory contract 后推进，但 #80 定义的评测维度会反过来约束 WU-CM-01 / #81 的设计：任何 WU-CM-01 design / plan 都必须说明 #80 的评测维度哪些由当前 scope 满足、哪些 deferred-with-owner、哪些是 explicit non-goal。若某个 #81 方案让 #80 的核心评测维度不可测试、不可审计或不可实现，必须先回到设计讨论修正。

WU-CM-01 的实施设计真源为 `docs/host/design.md` 的 `24. Conversation Memory` 与 `25. Context Governance`。plan、implementation、review、fix 与 re-review 不得从讨论稿、旧代码或 GitHub Issue body 重新解释 compact I/O、memory snapshot、prompt assembly、compact repair / fallback 或 context governance 边界；若发现第 24 / 25 章仍不足以生成 code-generation-ready plan，必须先回到 Host 设计真源修正，再更新本文档。

Plan gate 已完成，artifact 为 `docs/host/wu-cm-01-conversation-memory-plan.md`。Plan review gate 已完成，AgentMiMo 与 AgentDS 均裁决 `pass-with-findings`；Controller 接受 6 组 plan fix findings，裁决 artifact 为 `docs/reviews/wu-cm-01-plan-review-controller-adjudication.md`。Plan fix gate 已完成，artifact 为 `docs/reviews/wu-cm-01-plan-fix-codex.md`；accepted fix scope 是补齐 issue-80 评测维度映射、旧 continuity / compact candidate / material section / quality checker 迁移规则，以及 slice 可编译性验证边界。Plan re-review gate 已完成，AgentMiMo 与 AgentDS 均裁决 `pass`，Controller 裁决 artifact 为 `docs/reviews/wu-cm-01-plan-rereview-controller-adjudication.md`。Accepted plan commit 为 `14d28009`。Implementation gate 预检由 AgentCodex 停止，artifact 为 `docs/reviews/wu-cm-01-implementation-codex.md`；直接证据显示当前 plan 的概念域 Slice 1-5 不是可编译闭环，若直接实施会违反 pyright 硬约束。Plan reslice fix gate 已完成，artifact 为 `docs/reviews/wu-cm-01-plan-reslice-fix-codex.md`。Plan reslice re-review gate 已完成，AgentMiMo 裁决 `pass`，AgentDS 裁决 `pass-with-findings`，Controller 裁决 artifact 为 `docs/reviews/wu-cm-01-plan-reslice-rereview-controller-adjudication.md`。Plan reslice accepted commit 为 `a92416ec`。Slice A implementation gate 已完成，artifact 为 `docs/reviews/wu-cm-01-slice-a-implementation-codex.md`；验证结果为 100 focused tests passed，pyright 0 errors。Slice A code review gate 已完成，AgentMiMo 与 AgentDS 均裁决 `pass-with-findings`，0 条 blocking finding；Controller 接受 `__all__` 导出、vNext label contract 去重、material mapping 独立测试三类 fix，裁决 artifact 为 `docs/reviews/wu-cm-01-slice-a-code-review-controller-adjudication.md`。Slice A fix gate 已完成，artifact 为 `docs/reviews/wu-cm-01-slice-a-fix-codex.md`；验证结果为 105 focused tests passed，pyright 0 errors。Slice A re-review gate 已完成，AgentMiMo 裁决 `pass`，AgentDS 裁决 `fix-accepted`，Controller 裁决 artifact 为 `docs/reviews/wu-cm-01-slice-a-rereview-controller-adjudication.md`；Controller 复验 105 focused tests passed，pyright 0 errors。Slice A accepted commit 为 `f060853d`。Slice B implementation gate 触发 allowed-files blocker，artifact 为 `docs/reviews/wu-cm-01-slice-b-implementation-codex.md`；直接证据显示 reactive accepted compaction closeout owner 是未列入 Slice B allowed files 的 `dayu/host/engine_ingest.py`，且 proactive subsequent run input failure 属于 Slice C/D 的 memory projection / RunInputBuilder 消费边界。Controller 接受 blocker，裁决 artifact 为 `docs/reviews/wu-cm-01-slice-b-blocker-controller-adjudication.md`。Slice B plan fix gate 已完成，artifact 为 `docs/reviews/wu-cm-01-slice-b-plan-fix-codex.md`。Slice B plan fix re-review gate 已完成，AgentMiMo 裁决 `pass-with-risks`，AgentDS 裁决 `pass-with-findings`，Controller 接受 4 项 plan clarification finding，裁决 artifact 为 `docs/reviews/wu-cm-01-slice-b-plan-fix-rereview-controller-adjudication.md`。Slice B plan fix follow-up gate 已完成，artifact 为 `docs/reviews/wu-cm-01-slice-b-plan-fix-followup-codex.md`；accepted clarification 包括 `engine_ingest.py` 非 closeout 旧 import / annotation 边界、proactive subsequent run input 测试归属、vNext artifact writer shared helper 策略，以及 `tests/host/test_engine_ingest_mapping.py` 的 Slice B 受限测试范围。Controller 接受 follow-up，裁决 artifact 为 `docs/reviews/wu-cm-01-slice-b-plan-fix-followup-controller-adjudication.md`。Slice B implementation gate 已完成，artifact 为 `docs/reviews/wu-cm-01-slice-b-implementation-codex.md`；Controller 复验 270 focused tests passed，pyright 0 errors。Slice B code review gate 已完成，AgentMiMo 与 AgentDS 均裁决 `pass-with-findings`，0 条 blocking finding；Controller 接受删除 `context_events.py` 旧 compact payload dead helper 与修正 vNext 测试命名 / 断言两项 fix，裁决 artifact 为 `docs/reviews/wu-cm-01-slice-b-code-review-controller-adjudication.md`。Slice B fix gate 已完成，artifact 为 `docs/reviews/wu-cm-01-slice-b-fix-codex.md`；Controller 复验 270 focused tests passed，pyright 0 errors。Slice B re-review gate 已完成，AgentMiMo 与 AgentDS 均裁决 `pass`，0 条 blocking finding；Controller 裁决 artifact 为 `docs/reviews/wu-cm-01-slice-b-rereview-controller-adjudication.md`。Slice B accepted commit 为 `74fbb5e6`。Slice C implementation gate 触发 allowed-files blocker，artifact 为 `docs/reviews/wu-cm-01-slice-c-implementation-codex.md`；直接证据显示旧 `ConversationMemorySnapshot` / `MemoryProjectionPolicy` 的 production consumers 分布在 `run_input.py`、`compact_material.py`、`dispatch.py`、`service/host_assembly.py`、`runtime/config_loader.py` 与多份非 Slice C 测试中，当前 Slice C allowed files 无法形成 pyright-clean closure 且不能通过兼容桥绕过。Controller 接受 blocker，裁决 artifact 为 `docs/reviews/wu-cm-01-slice-c-blocker-controller-adjudication.md`。Slice C plan fix/reslice gate 已完成，artifact 为 `docs/reviews/wu-cm-01-slice-c-plan-fix-codex.md`；plan 选择扩大 Slice C 为 memory contract / projection / prompt assembly / dispatch / config assembly 的 pyright-clean vertical slice，直接纳入 blocker 证明的 production consumers 与 tests，禁止兼容 wrapper、re-export、old-field alias 和旧 snapshot -> vNext bridge helper。Slice C plan fix re-review gate 已完成，AgentMiMo 与 AgentDS 均裁决 `pass-with-findings`，0 条 blocking finding；Controller 接受 material contract、config field inventory、config file boundary、memory repair test 与 durable fail-fast clarification，裁决 artifact 为 `docs/reviews/wu-cm-01-slice-c-plan-fix-rereview-controller-adjudication.md`。Slice C plan fix follow-up gate 已完成，artifact 为 `docs/reviews/wu-cm-01-slice-c-plan-fix-followup-codex.md`；Controller 接受 follow-up，裁决 artifact 为 `docs/reviews/wu-cm-01-slice-c-plan-fix-followup-controller-adjudication.md`。Slice C plan boundary follow-up gate 已完成，artifact 为 `docs/reviews/wu-cm-01-slice-c-plan-boundary-followup-codex.md`；Controller 接受 boundary follow-up，裁决 artifact 为 `docs/reviews/wu-cm-01-slice-c-plan-boundary-followup-controller-adjudication.md`。Slice C implementation blocker 已由 Controller 接受，artifact 为 `docs/reviews/wu-cm-01-slice-c-implementation-blocker-controller-adjudication.md`；本次 engine ingest / context governance boundary follow-up 已完成，artifact 为 `docs/reviews/wu-cm-01-slice-c-engine-ingest-context-governance-boundary-followup-codex.md`，只补 `engine_ingest.py`、`context_governance.py`、`test_engine_ingest_mapping.py`、context governance 现有测试覆盖说明与测试命令，未触碰 production code、tests、schema、config JSON 或 README，未创建 Slice C implementation commit。Compact contract closure plan gate 已完成，artifact 为 `docs/reviews/wu-cm-01-compact-contract-closure-plan-codex.md`；plan review gate 已完成，AgentMiMo 裁决 `pass-with-findings`，AgentDS 裁决 `pass-with-findings`，Controller 裁决 artifact 为 `docs/reviews/wu-cm-01-compact-contract-closure-plan-review-controller-adjudication.md`；plan fix gate 已完成，artifact 为 `docs/reviews/wu-cm-01-compact-contract-closure-plan-fix-codex.md`；plan re-review gate 已完成，AgentMiMo 与 AgentDS 均裁决 `pass`，Controller 裁决 artifact 为 `docs/reviews/wu-cm-01-compact-contract-closure-plan-rereview-controller-adjudication.md`。下一入口为 WU-CM-01 compact contract closure implementation gate。

### 目标

- 将 Conversation Memory 的语义类型与 prompt assembly / deterministic bounded selection policy 分离，避免继续把 `stable layer`、`history pool`、`recent raw turns floor` 这类预算策略当作顶层 memory 心智模型。
- 固定 Memory Truth / Store、Conversation Memory Projection、Prompt Assembly 与 Context Governance 边界：EventLog / artifacts / accepted evidence 保持真源地位，memory snapshot 保持 bounded read model，不成为新的事实真源，Context Governance 只负责编排 compact / fallback / budget governance，不直接写 memory projection。
- 裁决并实现 #81 scope 内优先级最高的语义 memory 能力，例如 Trace Memory、Evidence / Fact Memory、Session Summary Memory、Answer Anchor Memory 与 Forward Intent Memory；User Profile Memory 只在 #81 固定“不混入 session Conversation Memory”的边界，跨 session durable profile 设计与实施交给 WU-CM-11 / GitHub Issue #115。
- 将 WU-CM-02、WU-CM-03、WU-CM-04 等已并入 #81 的问题纳入统一 semantic model 裁决，不再对旧 memory shape 做局部补丁。
- 为 compact repair 固定策略：采用 whole-candidate repair retry；一次 repair attempt 可以向 LLM 提供多个 Host-neutral invalid reasons / validation issues，但必须重新产出完整 candidate。Host 不要求 LLM 返回 repair patch，不合并旧 proposal 的 valid fields 与新 patch；只有完整 candidate 通过 JSON/schema/value mapping、provenance、quality check 与必要预算闸门后，才可写 `CONTEXT_COMPACTED`。
- 明确第一阶段不做 prompt-conditioned recall、semantic search、vector recall、LLM reranker 或 recall tool；deep historical recall / semantic search 由 GitHub Issue #39 承接。
- 以 GitHub Issue #80 的分层评测标准约束语义设计，确保 Memory Truth / Store、Memory Projection、Prompt Assembly 与 Agent Outcome 都保留可审计、可断言的验证入口。
- 产出 code-generation-ready plan，明确 slices、allowed files / modules、schema / contract 变更、测试矩阵、migration strategy 和 residual risk owner。

### 非目标

- 不把 #81 issue body 直接当作 implementation plan。
- 不一次性实现所有 speculative memory 能力；必须按可验证闭环切 slice。
- 不让 assistant final answer、summary、answer anchor、user claim 或 user profile 自动升级为 evidence-backed facts。
- 不让 memory snapshot 替代 EventLog / artifacts / accepted evidence。
- 不在 WU-CM-01 内实现跨 session User Profile Memory；durable profile store、profile update event、privacy / reset / deletion、supersession、confidence、confirmation policy 和用户可见解释由 WU-CM-11 / GitHub Issue #115 独立跟踪。
- 不在 WU-CM-01 内实现 prompt-conditioned recall、semantic search、vector recall、LLM reranker 或 recall tool；deep historical recall / semantic search 由 GitHub Issue #39 承接。
- 不在 #81 内直接落地完整 #80 eval benchmark；#80 的实现等待稳定 post-#81 memory contract，但其评测标准立即约束 #81 设计。
- 不为旧 `pinned_state` / `working_assumptions` 结构保留兼容 wrapper 或局部止血。

### 验收信号

- #81 被拆成 code-generation-ready phase plan 和可 review 的 implementation slices。
- #81 的 design / plan 明确映射 #80 评测维度：每个维度必须标记为 current scope satisfied、deferred-with-owner 或 explicit non-goal。
- 设计真源明确 semantic memory categories 与 prompt assembly / deterministic bounded selection policy 的边界。
- User Profile Memory 在 #81 中被标记为 deferred-with-owner，并指向 WU-CM-11 / GitHub Issue #115；session Conversation Memory 不伪装、内嵌或兼容实现跨 session profile。
- tests 能区分 trace continuity、evidence-backed facts、session summary、answer anchors、forward intent、profile boundary 和 prompt assembly bounded behavior。
- compact repair 测试覆盖多个 invalid reasons 触发一次 whole-candidate repair retry、rejected candidate 不被部分采用、完整 candidate 重新通过全量 revalidation、repair exhausted fail closed。
- 现有 `utils/` 下的 Host public smoke 必须通过，作为 WU-CM-01 的初步验收标准；至少覆盖 `utils/smoke_host_public_conversation_memory.py`、`utils/smoke_host_public_conversation_memory_scenarios.py` 与 `utils/smoke_host_public_multiturn.py`，后续若 smoke 脚本新增、拆分或改名，WU-CM-01 plan 必须同步列出实际验证命令。
- deep historical recall / semantic search / recall tool 若进入后续 scope，必须由 GitHub Issue #39 先形成 research artifact 和明确 design constraints。
- WU-CM-01-F01、WU-CM-01-F02、WU-CM-02、WU-CM-03、WU-CM-04、WU-CM-05、WU-CM-06、WU-CM-08、WU-CM-11 的后续状态被更新为 closed、deferred-with-owner 或 transferred-to-issue。

## WU-CM-01-F01 Conversation Memory Smoke Correctness Closeout

### 状态

GitHub Issue #81 / WU-CM-01 final closeout follow-up。Host public smoke 用于验证 Conversation Memory 与 Host 整体设计是否在 public path 上成立；如果 smoke 输入、断言或观测点本身偏离设计真源，就无法提供有效验收信号。本条作为 WU-CM-01 的 smoke correctness 收尾追踪项，不占用已有 WU-CM-05 编号。后续若继续发现这些 smoke 自身不符合设计验证目的的问题，统一在本条追踪，而不是散落到新的编号。

### 当前已知修正项

- 2026-06-05 Host public conversation memory smoke 的 round1 final Runner-call messages dump 显示当前有两条 `system` role message：一条为 scene / behavior prompt，一条为 Host execution context。协议层面这不是非法 messages，但 smoke 作为 public conversation memory 验收入口，应收敛到一个 `system` role message，降低 provider-compatible 路径的歧义。
- 2026-06-05 round2 compact 后 Runner-call dump 发现观测闭环不一致：`workspace/tmp/smoke01.log` 中 round2 `runner_call_start` 记录 `message_count=9`，但从当前 durable DB + EventLog 重建 cursor=121 的 memory / compact 投影只能得到 7 条 messages。round2 是 Conversation Memory compact 后 public path 验收点；smoke / dump 必须能解释或直接验证这 2 条差异来自哪里，不能让 compact 后实际 LLM-facing input 只能靠日志计数间接判断。
- 2026-06-05 round2 proactive compact compactor messages dump 暴露 compactor prompt 设计问题：`dayu/config/prompts/scenes/conversation_compaction.md` / `conversation_compaction_user.md` 中存在面向内部实现者的术语和无状态 LLM 不具备的上下文，例如 `Host-owned context compaction`、`ConversationCompactOutputVNext`、`prompt-local evidence labels`、`vNext 字段`。这会增加无状态、有限上下文、偏模式匹配的 LLM 的认知负担，降低 strict JSON compaction 稳定性。`utils/smoke_host_public_conversation_memory.py` 与 `utils/smoke_host_public_conversation_memory_scenarios.py` 需确认是否都装配该 compactor prompt；当前直接 `rg` 证据显示这些术语来自 `dayu/config/prompts/scenes/conversation_compaction*.md`，不是 smoke 脚本内联字符串。
- 2026-06-05 scope review 确认本条不得只检查 `utils/smoke_host_public_conversation_memory.py`；同组 Host public smoke 入口 `utils/smoke_host_public_diagnostics.py`、`utils/smoke_host_public_conversation_memory_scenarios.py`、`utils/smoke_host_public_multiturn.py` 也必须检查是否存在相同修正项，包括多 `system` role message、compact 后 Runner-call message 观测闭环缺口、以及 LLM-facing prompt / evidence material 使用内部实现术语的问题。

### 目标

- 修正 `utils/` 下 Host public smoke 中无法有效验证 Conversation Memory / Host 设计的偏差；当前审计范围至少包括 `utils/smoke_host_public_conversation_memory.py`、`utils/smoke_host_public_diagnostics.py`、`utils/smoke_host_public_conversation_memory_scenarios.py`、`utils/smoke_host_public_multiturn.py`。
- 对每个新增 smoke correctness 问题，先用设计真源与代码直接证据确认 smoke 错在输入构造、断言、观测点、fixture、projection expectation 还是生产实现偏离设计；只有确认是 smoke 偏差时才纳入本条修正。
- 当前已知修正：修改 `utils/smoke_host_public_conversation_memory.py` 及必要的同组 smoke helper，使 smoke 构造的 round1 final Runner-call messages 只包含一个 `system` role message，并增加直接验收；同时审计另外三个 Host public smoke 是否经由相同 prompt assembly 路径产生多 `system` role message，若存在则一并修正并加验收。
- 当前已知修正：补齐 round2 compact 后 RunInput / Runner-call message shape 的 smoke 验收信号，使日志记录的 `message_count`、durable 可重建 messages、memory snapshot / compact artifact 投影三者能对齐；若无法完整重建，smoke 必须输出明确 limited-signal 诊断。
- 当前已知修正：审计 4 个 Host public smoke 的 compactor prompt 装配路径，并修正 `dayu/config/prompts/scenes/conversation_compaction*.md` 中面向内部实现的 prompt 表述；prompt 应以最低认知负担描述下一步动作、输入 JSON、输出 JSON、label 引用规则和禁止项，不要求 LLM 理解 Host 内部命名、Python 类型名或 vNext 历史迁移语义。
- 保持 smoke 能验证真实 public Host path，不通过测试私有入口、伪造 durable atom 或绕过 Host / Engine contract 来获得通过。

### 非目标

- 不修改 production Conversation Memory、compact、RunInputBuilder、Engine runner 或 provider payload 行为。
- 不把 production 实现偏离设计的问题伪装成 smoke 修改；若根因是生产代码，应回到对应 production work unit 或设计真源处理。
- 不通过只改 smoke prompt、测试 fixture 或 dump 脚本来掩盖 `dayu/config/prompts` 真源 prompt 的问题；如果真实 compactor prompt 是根因，必须修 prompt asset 本身并让 smoke 覆盖真实装配路径。
- 不把 smoke 可读性、输出格式美化或普通维护项纳入本条，除非它直接影响 smoke 对 Conversation Memory / Host 设计的验收能力。
- 不补 EventLog runner-call reconstruction atoms；该工作由 WU-DUR-P01 / GitHub Issue #117 承接。
- 不实现 Tool Trace analyzer 或 messages dump 工具；该工作由 WU-OBS-P00 / WU-OBS-00 承接。
- 不引入新的 smoke 私有生产入口或测试专用 durable bridge。

### 验收信号

- 每个纳入本条的 smoke correctness 问题都有直接证据说明为什么 smoke 当前无法验证对应设计点，以及修正后验证的设计点是什么。
- 当前已知项修正后，4 个 Host public smoke 入口通过，并能证明各自 final Runner-call messages 至多只有一个 `system` role message；若某个 smoke 不触发 Runner-call 或 compact，应明确记录它不适用该断言的直接原因。
- 若当前已知项修正后 smoke 仍产生多条 `system` role message，必须 fail fast，而不是只在事后 dump 中发现。
- round2 compact 后 `runner_call_start.message_count` 与 smoke / dump 可观测的 message items 数量一致；若不一致，smoke 失败或输出明确 limited-signal 诊断并指向缺失的投影来源。
- compactor prompt dump 中不再出现要求 LLM 理解内部实现身份或 Python 类型名的表达，例如 `Host-owned context compaction`、`ConversationCompactOutputVNext`、`prompt-local evidence labels`、`vNext 字段`；对应规则必须改写成面向无状态 LLM 的直接任务说明、输入字段说明、输出 JSON 字段说明与引用 label 约束。
- 4 个 Host public smoke 入口均完成 compactor prompt 装配路径审计；凡会触发 compact 的入口，都能证明它们使用的 compactor prompt 来自同一稳定 prompt asset，且该 prompt 通过上述可读性 / 可执行性检查。
- smoke 修改后，相关 Host public smoke 入口通过；pyright 0 errors。

## WU-CM-01-F02 Compact Evidence Query Readability Quality Closeout

### 状态

GitHub Issue #81 / WU-CM-01 final closeout follow-up，依赖 WU-DUR-P01 补齐 accepted tool call request durable atoms。本条处理 compact 输入质量问题，不处理 analyzer dump 可观测性本身；dump / trace 能否轻量重建仍由 WU-DUR-P01 / WU-OBS-P00 承接。

### 设计与代码核对

- 2026-06-05 round2 proactive compact messages dump 显示 `evidence_material[*].query_text` 退化为 `tool_call_id=call_5c4a39a2ea37464a82357cce`。本次 smoke 仍能 compact 成功，是因为 `response_text` 的 mock tool result 自解释且包含完整结构化 facts；但泛化场景下，compactor 会缺少“工具为什么被调用、调用参数是什么、该 evidence 对应哪个用户问题”的语义锚点。
- 当前生产路径为 `build_accepted_tool_evidence_material_blocks` -> `collect_selected_compaction_request_evidence_inputs` -> `_readable_query_text(envelope)`；`_readable_query_text` 目前只返回 `tool_call_id={envelope.tool_call_id}`。
- 根因与 WU-DUR-P01 同源：canonical `TOOL_CALL_REQUESTED` 当前没有可读取的 arguments / semantic query durable atom，因此 compact material projection 无法稳定生成 tool name + arguments / semantic query 的 LLM-readable query text。

### 目标

- 让 compact `evidence_material[*].query_text` 使用 durable tool call request atom 生成可读查询文本，至少包含 tool name 与稳定规范化 arguments；在工具提供 semantic query / readable input 时优先使用该语义文本。
- 保持 query text 是 LLM-readable material，不包含 EventLog id、payload ref、digest、cursor、artifact descriptor 或其它 Host 内部账本细节。
- 与 WU-DUR-P01 对齐：若 durable tool-call arguments / semantic query 尚未补齐，本条不得用 prompt 猜测、tool behavior 推断或当前代码 hardcode 伪造 query text。
- 覆盖 accepted evidence chunking：同一 tool result 被切成 `E1.1`、`E1.2` 等 evidence chunks 时，各 chunk 的 query text 应保持同源、稳定、简洁，不因 chunk 数量重复注入大段参数文本。
- 保持 compact quality owner 边界：本条只改善 compactor LLM-facing evidence material 的查询语义，不改变 accepted tool result truth、不改变 evidence-backed fact accept barrier、不改变 compact candidate schema。

### 非目标

- 不补 EventLog / payload durable atoms；该工作由 WU-DUR-P01 / GitHub Issue #117 承接。
- 不实现 Tool Trace analyzer 或 dump 工具；该工作由 WU-OBS-P00 / WU-OBS-00 承接。
- 不把 tool call request 原文、provider payload 或 Host 内部 refs 直接塞进 compact prompt。
- 不把业务工具 schema 特例硬编码进 compact material projection；若工具需要更好的 semantic query，应通过 typed durable atom / projection contract 表达。
- 不修改 compactor output schema 或 evidence-backed fact candidate 语义。

### 验收信号

- compact material 单元测试覆盖 accepted tool evidence query text：给定 durable tool call name + normalized arguments，`ConversationCompactInputVNext.evidence_material[*].query_text` 输出业务可读查询，而不是裸 `tool_call_id=...`。
- Host public conversation memory smoke 或 focused compact smoke 覆盖 round2 proactive compact：dump 中 `evidence_material[*].query_text` 能看到 tool name / arguments 或 semantic query；若 durable atoms 缺失，smoke 必须输出明确 limited-signal 诊断，而不是静默退化。
- query text 不包含 `event-`、`payload-`、`sha256:`、`compact-artifact:`、cursor、policy ref 等 Host 内部账本标识。
- compact 后 accepted candidate 仍只引用 prompt-local labels，不引用 `C1` 或 Host internal refs。
- 受影响 focused tests 通过；pyright 0 errors。

## WU-CM-02 Working Assumptions Producer Semantics

### 状态

已裁决；独立 WU rejected / closed。`working_assumptions` 不作为 #81 第一阶段 semantic memory category 保留，不再为旧字段补生产者语义。旧 schema / snapshot / renderer 中的 `working_assumptions` 删除或迁移由 WU-CM-01 的 schema / projection / RunInputBuilder slice 承接。

### 目标

- 固定裁决：reject 旧 `working_assumptions` 独立语义，不把它作为 Trace / Evidence-Fact / Session Summary / Answer Anchor / Forward Intent 之外的第六个 session-scoped memory。
- WU-CM-01 plan 必须明确旧 `working_assumptions` 字段的删除 / 迁移边界，覆盖 schema、snapshot codec、durable projection、RunInputBuilder 与 tests。
- 后续若需要 hypotheses / candidate claims，必须另起设计并绑定 source、status、confidence 与 user-visible boundary；不得复用旧 `working_assumptions` 名称做兼容 wrapper。

### 非目标

- 不让 `working_assumptions` 承载工具事实、财报事实、任务状态或长期用户画像。
- 不绕过 evidence-backed fact 主链路。
- 不在 #81 / WU-CM-01 中为旧 memory shape 做局部修补或兼容 wrapper。

### 验收信号

- WU-CM-01 plan 明确旧 `working_assumptions` 的删除 / 迁移 slices 与测试入口。
- 字段不存在时，schema、snapshot codec、durable items、RunInputBuilder 和测试全部同步收敛。
- 若实现阶段发现仍有字段残留，必须作为 WU-CM-01 schema / projection finding 修复，不能重新打开 WU-CM-02。

## WU-CM-03 Fact-candidate-only Validation Failure Policy

### 状态

已裁决；独立 WU closed。fact-candidate-only validation failure 统一采用 fail closed / whole-candidate repair retry，不允许 partial materialize。

### 目标

- 裁决 `CONTEXT_COMPACTED` 中 fact candidates 非法但其它 compact output 合法时必须 fail closed：rejected candidate 不得 partial materialize，不得写 `CONTEXT_COMPACTED`，只允许进入 bounded whole-candidate repair retry 或最终 `CONTEXT_COMPACTION_FAILED` / fallback policy。
- 统一 quality check、payload validation、memory projection、diagnostic 与用户可见失败策略，作为 WU-CM-01 compact accept barrier / repair tests 的输入约束。

### 非目标

- 不重新开放 fact-candidate-only partial materialize 作为实现选项。
- 不让非法 fact candidates 进入 evidence-backed facts。

### 验收信号

- 测试覆盖 fact candidates invalid / non-fact compact fields invalid 两类路径，均验证 rejected candidate 不进入 memory projection。
- fail closed / whole-candidate repair retry 的策略在 projection、diagnostic 和用户可见结果上一致。

## WU-CM-04 Minimum Preserve And Fins Fact Boundary

### 状态

已裁决；独立 WU closed。Minimum Preserve 保留为 bounded continuity item，不是事实真源；后续 Fins integration 必须继承该边界。

### 目标

- 确认 `minimum preserve` 继续作为 bounded continuity item，而不是事实真源。
- 明确后续 Fins 接入时不得把 minimum preserve 文本当作财报事实引用。

### 非目标

- 不把 minimum preserve 标成 verified / sourced fact。
- 不让 UI / Service 把 continuity item 当作财报引用真源。

### 验收信号

- Fins / ToolRuntime / RunInputBuilder 文档和测试均不把 minimum preserve 当 stable fact。
- minimum preserve 的 source refs 只服务 continuity，不成为财报引用真源。

## WU-TOOLS-01 Fins / Web / Doc Tools Migration With Shared Document Foundations

### 状态

已纳入 GitHub Issue #82、#97 与 #98。三条 issue 必须作为同一个 work unit 实施，可以分 slice 推进。原因是旧 `dayu-agent/dayu/fins`、旧 Web tools 与旧 Doc tools 共享多类文档基础能力，不只是 Docling runtime：Doc tools 依赖 engine processors，Fins 也大量依赖 engine processors，Web tools 依赖 Docling conversion path。拆成多个独立 work unit 容易产生重复 processor 迁移、重复 Docling adapter、重复 package placement 决策和不一致的测试替身。

### 设计与代码核对

- 旧仓库 Fins source scope 是 `dayu-agent/dayu/fins`，不是 `dayu-agent/fins`。
- 旧仓库 Fins 通过 `dayu-agent/dayu/fins/docling_export.py` 使用共享 `dayu.docling_runtime`。
- 旧仓库 Fins processors 明确依赖 engine processors：`FinsBSProcessor -> BSProcessor`、`FinsDoclingProcessor -> DoclingProcessor`、`FinsMarkdownProcessor -> MarkdownProcessor`，并复用 `ProcessorRegistry`、`Source`、`text_utils`、`search_utils`、`table_utils` 等公共处理器基础能力。
- 旧仓库 Doc tools source scope 是 `dayu-agent/dayu/engine/tools/doc_tools.py` 与其依赖的 `dayu-agent/dayu/engine/processors/*` 文档处理器链路。
- 旧仓库 Doc tools 通过 `create_doc_file_processor(...)` 间接使用 `DoclingProcessor`；`DoclingProcessor` 读取 `*_docling.json` 时依赖 `docling-core` 的 `DoclingDocument`。
- 用户请求提到 `dayu-agent/dayu/web`；代码核对显示该路径主要是旧 UI 适配层（Streamlit / FastAPI），不是 Web tools 主实现。
- 旧仓库真正的 Web tools 代码主要出现在 `dayu-agent/dayu/engine/tools/web_*.py`，包括 `search_web`、`fetch_web_page`、search provider、challenge detection、fetch orchestrator 与 Playwright fallback 等。
- 旧仓库 Web tools 通过 `dayu-agent/dayu/engine/tools/web_fetch_orchestrator.py` 使用共享 `dayu.docling_runtime`。
- 旧仓库 Web tools 相关 typed config 分布在 `WebToolsConfig`、execution options、toolset config 与 scene / contract preparation 相关代码中；迁移时必须只做当前 `dayu-agent-r` ToolDiscovery / ToolRuntime 所需的 typed config 适配。
- `dayu-agent-r` 当前已有 `docling` / `docling-core` 依赖，但没有等价的共享 Docling runtime ownership，也没有旧仓库 engine processors / doc tool chain。
- 本条不是 UI 入口迁移；CLI / Web / GUI 入口分别由 UI 总控中的 #83 / #84 / #85 处理。

### Slice 切分

1. Shared document foundations slice：先裁决并迁移 / 建立共享文档基础能力，包括 engine processors、processor registry、document source / text / table / search utils、Docling runtime / conversion path、Docling JSON loading、package placement、import path 和测试替身。
2. Doc tools slice：从 `dayu-agent/dayu/engine/tools/doc_tools.py` 迁移长期运行验证可靠的通用文档工具，只允许做最小 `@tool` adapter、ToolDiscovery provider / entry-point adapter、import / package 位置和 package name 调整。
3. Fins slice：从 `dayu-agent/dayu/fins` 迁移长期运行验证可靠的 Fins 代码，只允许修改 `@tool` 与 ToolDiscovery 接口适配部分，不允许修改其它 Fins 业务代码。
4. Web tools slice：从核定后的旧 Web tools source files 迁移长期运行验证可靠的 Web tools 代码，只允许做最小 `@tool` adapter、ToolDiscovery provider / entry-point adapter、import / package 位置和 package name 调整。

### 迁移原则

- 三类工具迁移原则一致：Doc tools、Fins tools、Web tools 都按可靠旧代码迁移，不按新设计重写。
- 允许搬迁代码。
- 允许调整 import、package 位置和 package name。
- 允许做最小必要的 `@tool` adapter changes。
- 允许做最小必要的 ToolDiscovery provider / entry-point adapter changes。
- 禁止修改被迁移旧代码的 class / function signature。
- 禁止修改被迁移旧代码的函数实现代码。
- 如当前 `dayu-agent-r` 的 typed config、path safety、ToolRuntime 或 ToolDiscovery contract 需要适配，必须通过外层 adapter / provider / assembly code 解决，不得借机改旧函数签名或旧函数体。

### 目标

- 建立单一共享文档基础能力 owner，供 Fins、Doc tools 和 Web tools 复用，避免重复迁移 engine processors、重复实现转换、Docling JSON loading、backend fallback、device fallback、error classification 或测试替身。
- 迁移通用 Doc tools 与 processor chain，使 `list_files`、`get_file_sections`、`search_files`、`read_file`、`read_file_section` 等能力能通过当前 ToolDiscovery / ToolRuntime 使用。
- 保留 Docling JSON processor 对 `*_docling.json` 的章节、表格、section ref、table ref 与搜索行为。
- 新增或接入 `dayu.fins.storage` 下的财报仓储协议与实现。
- 财报工具 provider 通过 ToolDiscovery 进入 Host，而不是由 Host 扫描业务工具。
- 财报工具结果进入 accepted evidence 主链路。
- 核定旧仓库 Web tools 的准确 source scope，记录哪些旧文件被作为 Web tools 迁移，哪些 `dayu.web` UI 文件被明确排除。
- 将验证可靠的 Web tools 代码迁入 `dayu-agent-r` 合适包位置，并保留源行为。
- Web tools 能通过当前 ToolDiscovery 显式配置 / entry point 被发现，并通过当前 tool contract 调用。
- Web tool results 通过 ToolRuntime / Tool Trace / accepted evidence path 流转；不得绕过 Host 工具治理。
- 使用 deterministic fixtures / mocks 覆盖代表性 engine processors、Docling conversion、Docling JSON processing、Doc tools、Fins、search / fetch 行为，不能只依赖 live network 或真实 Docling heavyweight execution。

### 非目标

- 不把财报原文存取放入 Host / Service / runtime。
- 不把 minimum preserve 或 compact summary 当作财报事实真源。
- 不重写 Doc tools / processor business logic，尤其不重写章节、表格、section ref、table ref、snippet search、HTML / Markdown / Docling JSON fallback 语义。
- 不修改已长期运行验证可靠的 Fins 业务代码，除外层 `@tool` adapter 与 ToolDiscovery provider / entry-point adapter 外。
- 不重构 Web tool 业务逻辑。
- 不重写搜索、抓取、正文抽取、URL safety、private network filtering、truncation、challenge detection、Playwright fallback 或 diagnostic payload 语义。
- 不迁移旧 `dayu.web` UI / FastAPI / Streamlit entrypoints。
- 不让 Host 直接 import 或 scan Fins / Doc / Web tool implementation modules。
- 不把多套 processor / Docling runtime adapter 分别塞进 Fins、Doc tools 和 Web tools。
- 不让 `dayu.runtime` 依赖 Web tool implementation、Host、Engine、Service、UI 或 Fins；是否把 shared document foundations 的某部分放入 `dayu.runtime` 必须先经过分层设计裁决，不能因为复用方便直接下沉。
- 不把网络权限、私网访问开关或浏览器配置隐藏到全局变量 / 临时环境读取；必须走显式 typed config / policy。

### 验收信号

- 共享文档基础能力只有一个 owner，Fins、Doc tools 与 Web tools 复用同一套 processor chain、conversion / Docling JSON loading / backend fallback / device fallback 语义。
- 通用 Doc tools 与 processor chain 被迁入 `dayu-agent-r`，且 ToolDiscovery 能发现 Doc tools provider。
- Doc tools 能通过当前 tool contract 调用，并能处理 Markdown、HTML 与 `*_docling.json` deterministic fixtures。
- Fins storage、tool provider、ToolDiscovery 和 ToolRuntime accept path 有端到端测试。
- `evidence_backed_facts` 仍只由 Host-governed compact extraction 生成。
- 迁移后的 Web tools 存在于 `dayu-agent-r`，并记录 source scope 与排除的旧 UI files。
- Fins、Doc tools 和 Web tools 的旧代码只发生允许范围内的迁移变更：搬迁代码、import / package 位置 / package name 调整、最小 `@tool` adapter、最小 ToolDiscovery provider / entry-point adapter；旧 class / function signature 和函数实现代码保持不变。
- ToolDiscovery 能发现 Fins、Doc tools 与 Web tools provider，代表性 tool 可通过当前 tool contract 调用。
- ToolRuntime / Tool Trace / accepted evidence path 能接收 Fins / Doc / Web tool result。
- import-boundary tests 证明 runtime / Host / Service / UI 不获得对 Fins / Doc / Web tool implementation internals 的 forbidden direct dependency。
- deterministic tests 覆盖代表性 engine processors、Docling conversion、Docling JSON processor、Doc tools、Fins storage / provider、search / fetch / URL safety / truncation / fallback 或对应 mock 行为。
- 任何源行为偏离都被记录，并证明是当前接口适配所必需。

## WU-PROJ-01 Projection Catch-up Budgeting For Memory Pre-dispatch Path

### 状态

由 GitHub Issue #86 跟踪并实施。

### 目标

- 聚焦 memory projection catch-up / rebuild 在 pre-dispatch 路径上的预算、背压和诊断边界。
- 为 memory catch-up 定义总预算，而不仅是单批大小，例如 max batches、max scanned events、timeout 或等价 bounded execution policy。
- 明确 admission after-commit 的 catch-up 只能是 bounded best-effort 或 wake background supervisor，不得在 command path 上无上限追平。
- 明确 dispatch 前 catch-up / rebuild 的行为：成功追到 required cursor 时继续 dispatch；超预算或失败时产生结构化 diagnostic。

### 非目标

- 不改变 EventLog 作为投影真源的语义。
- 不让 projection lag 影响 recovery truth。
- 不把 Audit / Tool Trace / Outbox 纳入本条。
- 不重写 ProjectionRunner 为大型调度系统。
- 不把所有 projection sink 合并成 God runner。

### 验收信号

- memory projection catch-up 的单批大小与单次总预算边界均有明确代码或配置表达。
- admission after-commit catch-up 不会无上限同步追平大量 EventLog。
- dispatch 前 memory catch-up / rebuild 超预算或失败时有结构化 diagnostic，且不会改写 EventLog / Run / Attempt governance truth。
- 测试覆盖 bounded catch-up、required cursor 已覆盖、lag / failure / rebuild 超预算不误触发 recovery，以及 Audit / Tool Trace / Outbox 不被改成 command-path blocking sink。

## WU-DUR-P01 EventLog Runner-call Reconstruction Atoms

### 状态

GitHub Issue #117 当前为 OPEN。本条是 WU-OBS-P00 / WU-OBS-00 的 durable truth 前置 work unit，负责补齐 EventLog / payload / artifact 中用于还原历史 Runner 调用 LLM-facing messages 的原子字段。本条不把完整 provider request payload/messages 明文保存为新的 canonical fact；目标是让 provider request 作为派生视图，能由 durable atoms 与版本化 projector 稳定重建。

上位架构原则以 `docs/host/design.md` 为准：EventLog 是 Host durable fact 真源；tool trace、audit、usage、timeline、outbox 与 memory snapshot 都是从 committed EventLog 投影出的 read model / diagnostic view，不能反向成为 EventLog、recovery、resume、memory 或 Run 状态迁移真源。

重要约束：本条不得削弱 EventLog 原子性。补字段不是把 RunInput、provider request、messages dump、memory snapshot、compact material 或 analyzer bundle 一股脑塞进 EventLog；EventLog 仍只记录治理与恢复需要的 canonical facts、refs、digests、版本化 projector metadata 与最小必要原子。大体积 LLM-facing projection 必须走 payload descriptor / artifact ref，并保持可由 source refs / digests 校验。

### 设计与代码核对

- 2026-06-05 smoke 检查结论：当前 `USER_INPUT_ACCEPTED` 保存了 `system_prompt` / `user_prompt`，`TOOL_RESULT_ACCEPTED` 有完整 tool result payload，但 canonical `TOOL_CALL_REQUESTED` 只保存 `normalized_arguments_digest`，没有 tool call arguments 明文。GitHub Issue #117 已记录该 durable atom 缺口。
- Engine `ToolCallRequestedData` 内部包含 `arguments`，但 Host ingest preview event 只落 `argument_key_count`、`tool_name`、`tool_call_id` 和 `provider_state_present`。
- ToolRuntime accept barrier 写入的 canonical `TOOL_CALL_REQUESTED` 当前只包含 `tool_name`、`tool_call_id`、`tool_schema_digest`、`tool_identity_digest`、`normalized_arguments_digest`、`semantic_input_digest` 等摘要字段。
- `payload_descriptors` 当前没有 tool-call-arguments payload；round1 第二次 Runner call dump 只能从用户 prompt / 当前代码 / smoke 工具行为推断 arguments，不能从 durable atoms 直接读取。
- 2026-06-05 round2 proactive compact dump 显示 `evidence_material[*].query_text` 只能投影为 `tool_call_id=...`。直接代码证据是 `dayu/host/compaction_evidence.py::_readable_query_text(envelope)` 当前只返回 tool call id；根因是 durable truth 缺少可读取的 accepted tool call arguments / semantic query atom，导致 compact evidence material 无法稳定生成业务可读 query text。
- Host execution context system message 当前可由字段重建，但缺少显式 scene-message projector version / schema id。
- LLM-facing tool message content 当前依赖 Engine 投影代码；历史 dump 若不读当前代码，需要 durable projector version / schema digest 或等价 contract。
- 2026-06-05 round2 compact 后 dump 暴露更大缺口：`smoke01.log` 中 `runner_call_start` 记录 `message_count=9`，但当前 durable DB + EventLog 重建 cursor=121 的 memory / compact 投影只能得到 7 条 messages。现有 EventLog 有 `CONTEXT_COMPACTED`、compact artifact、当前 user input、terminal summary refs 等原子，但缺少“本次 Runner call 使用了哪些 LLM-facing material / memory / compact / continuity blocks、按何种 projector 版本拼成几个 message”的 durable assembly manifest。
- 2026-06-05 round2 proactive compact 内部 compactor call 也暴露同类缺口：Engine log 中 `context-compactor:vnext` run `context-compactor-vnext-10e0d9ae533d4673a430cedddac55b5d` 的 final proposal call `message_count=2`，当前可通过 EventLog / payload / compact artifact refs 与当前 compactor projector 代码重建 system+user messages，且重建 `compaction_request_digest=sha256:4013a39b85957a9463b8755976809fea47eb0ecc90ea38263ddb9ba4cb405abc` 与 artifact 一致；但 EventLog / compact artifact 没有保存 compactor runner-call input manifest、message role sequence digest 或 LLM-facing `ConversationCompactInputVNext` projection artifact ref，因此仍不能只靠轻量渲染完成历史 dump。
- `host_memory_snapshots` 当前只保留 latest snapshot row；该 smoke 完成后 snapshot cursor 已推进到 269，无法直接读取 round2 dispatch 时 cursor=121 的 historical memory read model。虽然 memory 可由 EventLog 重建，但若缺少本次 RunInput 所用 snapshot/material cursor、projector id、block ids 与 role sequence digest，历史重放仍会退化为读当前代码推断。
- 当前 Engine `ITERATION_STARTED` / verbose log 只给出 `message_count`，没有 message role sequence、message digests、source block refs、RunInput projector id 或 projection artifact ref。日志计数不能作为 durable truth，也不足以解释 9 与 7 的差异来源。

### 目标

- 实施前必须先把 EventLog 补字段的稳定 contract 写回 `docs/host/design.md`，包括新增 canonical atoms / refs / digests / projector metadata、payload descriptor / artifact ref 边界、schema 语义与不得削弱 EventLog 原子性的约束；implementation 只能按 design.md 的稳定设计落地。
- 补齐 EventLog / payload / artifact 原子字段，使历史 Runner 调用的 LLM-facing messages 可由 durable truth 与版本化 projector 重建。
- 将 accepted tool call arguments 作为可恢复、可校验的 durable atom 保存；可采用 canonical event payload 或 payload ref，但必须保留 digest/ref 链路。
- 为 compact evidence query projection 提供 durable 输入：accepted tool call request 至少要能恢复 tool name、normalized arguments 与可选 semantic query / readable input，使 `evidence_material[*].query_text` 不必退化为裸 `tool_call_id`。
- 明确 assistant tool_calls message 重建所需字段，包括 `content`、`reasoning_content`、`tool_calls`、provider state 边界与空值语义。
- 为 scene / Host execution context message 与 LLM-facing tool result projection 记录稳定 projector id、schema version 或 digest。
- 为每次 Runner call 记录 durable input assembly manifest：至少包含 `runner_call_index`、`iteration_id`、message_count、message role sequence digest、source block refs、source cursor、RunInput projector id/schema version/digest、tool schema snapshot refs、compact artifact refs、memory snapshot/material cursor refs、continuity refs 与 context fallback decision refs。
- 覆盖 Host-owned compactor 内部 Runner call：compactor 不是 Host admission 产生的用户 Run，但它仍是 Engine Runner 调用，manifest / projection refs 必须能表达 compactor system prompt、user prompt template、`ConversationCompactInputVNext` projection artifact/ref、compaction request digest、accepted compact artifact ref 与 compactor projector id/schema version。
- 区分 durable truth atoms 与派生 LLM-facing projection：EventLog 不保存完整 provider request 作为 canonical fact，但可以保存 derived projection artifact 的 ref/digest/producer projector metadata；artifact 内容必须能由 source refs/digests 校验，且不能反向成为 recovery / memory / Run 状态迁移真源。
- 保持 manifest 原子化：manifest 只列出本次 Runner call 采用的 source atom / projection artifact / digest / projector version / role-sequence 等可校验索引，不内联完整 messages、长 prompt、完整 tool result、完整 memory snapshot 或 compact material。
- 覆盖 compact 后 no-tool / empty-tool Runner call input，不只覆盖 tool call roundtrip；round2 这类 compact artifact + memory material + current large user prompt 场景必须能重建或明确报告 limited signal。
- 为 WU-OBS-P00 / WU-OBS-00 提供可消费的 durable refs / metadata，使 analyzer 不依赖当前代码或 prompt 猜测来重建 Runner call input。

### 非目标

- 不把完整 provider request payload/messages 明文作为 EventLog canonical fact 重复保存。
- 不把 EventLog 改成 messages dump store、provider request store、memory material store 或 analyzer bundle store。
- 不让 Tool Trace、Audit、Outbox、timeline 或 memory snapshot 反向成为恢复、resume、memory 或 Run 状态迁移真源。
- 不实现 Tool Trace analyzer、prompt-based diagnostics 或 operator bundle。
- 不要求 EventLog inline 大体积 LLM-facing messages；大 payload 应通过 payload descriptor / artifact ref / digest 管理。
- 不用 untyped extra payload 承载显式字段；新增字段必须是 typed canonical atom、typed ref / digest 或版本化 projector metadata。
- 不改变 ToolRuntime accept / governance 语义，除非字段补齐需要同步更新同源 contract。
- 不通过兼容 wrapper、旧字段 alias 或 extra payload 保留旧 schema。

### 验收信号

- 至少一个包含 tool call 的历史 Runner call，可只凭 EventLog + payload/artifact store + projector metadata 重建 LLM-facing messages。
- 至少一个 compact 后 follow-up Runner call，可只凭 durable input assembly manifest + source payload/artifact refs 重建 LLM-facing messages，或在历史字段不足时输出明确 limited-signal 诊断；不得出现日志 `message_count` 与 dump item 数量无法解释的状态。
- 至少一个 proactive compactor internal Runner call，可只凭 durable input assembly manifest + compactor projection artifact refs 轻量 dump 出 system/user messages，并能校验 `compaction_request_digest`、message_count 与 accepted compact artifact digest；不得要求 analyzer 重新执行 `_proactive_material_blocks` / `select_compact_segment` / `build_compact_material_pack` / compactor prompt rendering。
- EventLog 新增字段保持原子化；测试或 review 必须能证明没有把完整 provider request/messages、完整 memory snapshot、完整 compact material 或 analyzer bundle 内联进 EventLog canonical payload。
- accepted tool call arguments 可从 durable truth 读取，并能与 `normalized_arguments_digest` 校验一致。
- compact evidence query text 可由 durable tool call request atoms 生成，并能校验其 source 与 accepted evidence / tool result 同源；不得只剩 `tool_call_id=...`，除非输出明确 limited-signal 诊断。
- assistant tool_calls message 重建不依赖用户 prompt 文本推断。
- tests 覆盖 tool call -> tool result -> 第二次 Runner call messages reconstruction，以及 compact -> memory/material -> follow-up Runner call messages reconstruction 两条 durable atom 路径。
- Tool Trace / analyzer 相关字段仍只消费 refs / digest / metadata，不变成事实真源。

## WU-OBS-P00 Runner Call Input Reconstruction Signals

### 状态

GitHub Issue #70 当前为 OPEN，GitHub Issue #117 为本条的 durable atom 前置 owner。本条是 WU-OBS-00 / GitHub Issue #70 的前置 signal-contract work unit：在 WU-DUR-P01 补齐 EventLog 原子字段后，定义 Tool Trace analyzer 如何通过 refs / digest / projector metadata 定位并重建某次 Runner 调用的 LLM-facing messages。

上位架构原则以 `docs/host/design.md` 为准：Tool Trace / Audit 只能是 EventLog 的投影结果；它们可以服务分析、解释和 operator dump，但不能拥有或补造 Host durable truth，也不能成为恢复、resume、memory 或 Run 状态迁移依据。

重要约束：WU-OBS-P00 只能消费 WU-DUR-P01 提供的原子 refs / digests / projection artifact refs；不得反向要求 EventLog 保存完整 dump，也不得把 Tool Trace 提升为事实真源。

### 设计与代码核对

- `docs/host/issues-implementation-control.md` 已明确 WU-OBS-00 是 Tool Trace analyzer，Tool Trace 是 committed EventLog 的派生 projection，不是 Host recovery、resume、memory 或 Run 状态迁移真源。
- 当前 `tool-trace-cold.jsonl` 可投影 `TOOL_CALL_REQUESTED`、`TOOL_RESULT_ACCEPTED`、`USAGE_REPORTED`、`RUN_SUCCEEDED` 等 trace 行，但没有 system/user message、tool arguments 明文、assistant tool_calls content / reasoning_content，也没有 runner call message role index。
- 当前 tool trace 有 tool result / terminal summary payload refs，但只靠 trace 文件本身不能展开 tool role message content 或 final summary。
- WU-DUR-P01 解决 durable truth 缺口后，WU-OBS-P00 仍需裁决 trace projection schema：是否在 Tool Trace 中提供足够 refs / metadata，或新增 runner-call / run-input trace artifact。
- 2026-06-05 round2 dump 显示 analyzer 若只读取当前 DB、EventLog 与当前代码，可能得到与真实运行日志 `message_count=9` 不一致的 7 条重建结果。WU-OBS-P00 必须把这种 mismatch 变成结构化诊断：指出缺少 runner-call input manifest、historical memory/material snapshot、projection artifact 或 role sequence digest，而不是静默输出看似完整的 messages dump。
- 2026-06-05 round2 compact 内部 compactor dump 显示 analyzer 若要输出 `context-compactor:vnext` final proposal call messages，目前必须重跑 compactor input projector 与 prompt rendering；这不是轻量 renderer。WU-OBS-P00 必须让 analyzer 能把 Host-owned compactor Engine call 标识为 internal runner call，并通过 trace refs / projection artifact refs dump 或报告 limited-signal，而不是把它误判为普通 Host admitted Run。
- 2026-06-05 round2 compact dump 还显示 `evidence_material[*].query_text` 退化为 `tool_call_id=...`。Analyzer 不负责修复 compact 质量，但必须能把该退化标记为 durable atoms / projection signal 不足，而不是把只有 tool_call_id 的 query_text 当作完整可读 query。

### 目标

- 定义 Tool Trace analyzer 所需的 runner-call input reconstruction signal contract。
- 明确 trace 中应暴露的 refs / digest / projector metadata，例如 `runner_call_index`、`iteration_id`、message role index、tool call arguments payload ref、tool result projection ref、scene projector id。
- 明确 analyzer 消费的 runner-call input artifact / manifest contract：message item count、role sequence、per-message source refs / digests、projection artifact ref、RunInput projector id、tool-result projector id、memory-material projector id、compact artifact projector id，以及 provider serializer id / schema version。
- 将 compactor internal runner call 纳入同一 signal contract：trace / diagnostic artifact 必须能表达 parent Host run id、`context-compactor:vnext` run id、runner_call_index、compactor projector id/schema version、compaction request digest、`ConversationCompactInputVNext` projection artifact ref、accepted compact artifact ref，以及该调用不是 Host admitted user Run 的语义边界。
- 保持信号来源同源：只能来自 EventLog canonical facts、payload descriptors、artifact refs 或 Host-owned projection metadata；不得从日志、prompt 文本或当前代码猜测补造。
- analyzer 对 compact evidence material 应报告 query readability diagnostics：当 `query_text` 只能解析为裸 `tool_call_id` 且没有 tool name / normalized arguments / semantic query projection refs 时，输出 structured limited-signal，而不是静默通过。
- 保持 trace signal 轻量化：Tool Trace 可保存 manifest ref / projection artifact ref / digest / role-sequence summary / mismatch diagnostic，但不内联长 prompt、完整 messages、完整 tool result 或完整 memory material。
- 让 WU-OBS-00 analyzer 能输出某次 Runner 调用的 messages dump，或明确报告 limited signal / mismatch reason；特别要覆盖 compact 后 follow-up 的 memory/material/compact source gap。
- 将 dump 复杂度限制为轻量 renderer：resolve refs、verify digests、expand payload/artifact、render Markdown / JSON。Analyzer 不得复刻 RunInputBuilder、Engine tool message injection、tool result projection 或 provider payload serializer。

### 非目标

- 不把 Tool Trace 变成事实真源。
- 不在本条补 EventLog 原子字段；该工作由 WU-DUR-P01 / GitHub Issue #117 承接。
- 不实现完整 Tool Trace analyzer report。
- 不默认在 hot trace 中内联大 payload、敏感 provider raw payload 或完整 tool result。
- 不要求 Tool Trace 自身保存所有 LLM-facing messages；可以保存 message projection artifact ref / manifest ref / digest，但必须让 analyzer 能定位并校验派生 artifact。
- 不借 analyzer 需求反向污染 EventLog 原子事实；若需要完整 LLM-facing projection，使用派生 artifact，并用 refs / digests 连接到 EventLog atoms。
- 不改变 ToolRuntime / Engine / Runner 执行语义。
- 不在 analyzer 中用当前生产代码、prompt 文本或工具行为反推历史 messages；若 projector version 不受支持，必须报告 limited signal。

### 验收信号

- Tool Trace analyzer fixture 能从 trace refs 回链到 durable atoms，并生成 Runner call messages dump，或在字段缺失时输出明确 limited-signal 诊断。
- trace projection tests 覆盖 tool-call roundtrip、compact 后 follow-up、proactive compactor internal runner call 的 runner_call_index / iteration / refs / projector metadata / message_count 对齐。
- analyzer 不读取日志、不依赖 prompt 猜测、不把 Tool Trace 当作 truth。
- analyzer 能检测 `runner_call_start.message_count`、manifest message_count、dump item 数量不一致，并输出缺失字段 / 缺失 projection artifact 的 structured mismatch diagnostic。
- analyzer 能检测 compact evidence `query_text` 退化为 `tool_call_id` 的情况，并指向缺失的 tool-call arguments / semantic query durable atom 或 projection ref。
- analyzer dump 路径只有轻量渲染逻辑；若仍需要重写复杂 prompt assembly / tool projection，视为本条未通过。
- WU-OBS-00 plan 可以直接消费本条 signal contract。

## WU-OBS-P01 Tool Trace Context Budget Snapshot Signals

### 状态

GitHub Issue #29 当前为 OPEN。本条是 WU-OBS-00 / GitHub Issue #70 的前置 signal-contract work unit，而不是 analyzer 本体。Issue 中的 NEW 指 `dayu-agent-r`，OLD 指 `dayu-agent`。当前 NEW 已有 context budget / compaction / usage observation 相关 canonical facts 与 projection signal，但 Tool Trace analyzer 所需的 OLD 等价 context pressure 信号尚未形成稳定 trace contract。

### 设计与代码核对

- `docs/host/design.md` 已要求 trace / audit 能解释 context pressure、truncation、召回失败、预算未纳入 RunInput 等原因。
- `dayu/host/context_budget.py` 已有 `BudgetEstimate`、`ContextBudgetDecision`、`UsageObservationDiagnostic` 和 post-call usage observation 诊断。
- `dayu/host/context_events.py` 已有 `budget_snapshot_ref`、`budget_reason`、`budget_after_compact`、`budget_after_attempted_compact` 等 context compaction event payload 字段。
- `dayu/host/dispatch.py` 与 `dayu/host/engine_ingest.py` 会写入 context compaction / usage observation 相关事件。
- `dayu/host/tool_trace.py` 当前只把 usage projection signal 的 `usage_observation_digest` / `estimator_digest` 放入 diagnostic refs；hot `trace_summary` 尚未直接提供 OLD analyzer 等价的 `is_over_soft_limit`、compaction count、continuation count 等 context pressure 诊断字段。
- 代码核对未发现 `IterationUsageRecord` / `budget_snapshot` analyzer parity contract；当前也没有 operator-facing Tool Trace analyzer。

### 目标

- 先定义 NEW / dayu-agent-r 的 Host-owned context pressure trace signal contract，再由 WU-OBS-00 analyzer 消费。
- 评估 context pressure 所需字段应来自 `BudgetEstimate`、context compaction events、usage observation diagnostics、Run / Attempt facts 还是 Tool Trace projection summary。
- 补齐 analyzer 所需的 `is_over_soft_limit`、hard threshold / soft threshold reason、compaction count、continuation count 或等价稳定字段。
- 字段必须能追溯到 durable EventLog facts、projection signals 或 artifact refs；不得从日志、进程内缓存或 prompt 文本旁路补造。
- 保持分层：Engine 只上报 provider usage / protocol facts；Host 负责预算治理、context pressure 解释与 Tool Trace projection。

### 非目标

- 不复刻 OLD / dayu-agent 的数据结构名称作为 NEW 稳定契约。
- 不让 Engine 理解 Host context budget policy。
- 不把 analyzer 需要的字段塞进 untyped metadata / extra payload。
- 不在本条实现完整 Tool Trace analyzer；本条只补 signal contract 与 projection / fixture。

### 验收信号

- NEW / dayu-agent-r 的 Tool Trace 或 analyzer fixture 能表达与 OLD / dayu-agent 等价或明确增强的 context pressure 诊断。
- 新增字段有 contract / serializer / projection 测试。
- analyzer fixture 能覆盖 over soft limit、hard threshold、compaction happened、continuation happened / not happened 等代表场景。
- 不使用日志、进程内缓存或 prompt 文本旁路补造 budget snapshot。

## WU-OBS-P02 Tool Trace Tool Latency Signals

### 状态

GitHub Issue #30 当前为 OPEN。本条是 WU-OBS-00 / GitHub Issue #70 的前置 signal-contract work unit。Issue 中的 NEW 指 `dayu-agent-r`，OLD 指 `dayu-agent`。当前 NEW 的 ToolRuntime / Tool Trace 已能表达 tool call、outcome、truncation、duplicate、diagnostic refs 和 result digest，但尚未看到稳定 tool latency projection 字段。

### 设计与代码核对

- `docs/host/design.md` 的 Tool Trace hot / cold storage 设计允许保存 duration / attempt refs / diagnostic 等可诊断字段。
- `dayu/host/tool_runtime.py` 当前治理路径有 timeout、duplicate、truncation、accept retry、diagnostic refs 等结果，但代码核对未发现稳定 `latency_ms` / `duration_ms` 进入 accepted EventLog payload 或 Tool Trace summary。
- `dayu/host/tool_trace.py` 当前 `trace_summary` 包含 schema digest、identity digest、duplicate、truncation、diagnostic refs、provider / engine refs、policy decision 和 operation context refs；未包含 tool latency。
- `tests/host/test_tool_trace_projection.py` 已覆盖 hot / cold projection、digest conflict、query helper，但未覆盖 latency 统计字段。

### 目标

- 定义 tool latency 的稳定事实来源：ToolRuntime execution boundary、Tool result meta、accepted EventLog payload 或等价 Host-owned diagnostic event。
- 在 Tool Trace projection 中加入 `latency_ms`、duration bucket 或等价可聚合耗时信号。
- WU-OBS-00 analyzer 应能基于该信号输出 median latency / latency distribution / slow tool candidates。
- latency 语义必须明确包含或排除排队、duplicate reuse、truncation、accept retry、awaiting 外部 job 等阶段。

### 非目标

- 不用 wall-clock 日志解析 latency。
- 不把 latency 写成非持久进程内统计。
- 不在本条实现完整 analyzer report。
- 不让 latency 信号改变 ToolRuntime accept / governance 语义。

### 验收信号

- Tool Trace record 字段来源可追溯到 durable EventLog facts 或 Host-owned projection signal。
- analyzer fixture 能输出工具级耗时统计。
- projection、serializer / codec、analyzer fixture 覆盖普通 success、failure、duplicate / reuse、timeout 或 awaiting 代表路径。

## WU-OBS-P03 Tool Trace Structured Failure Metadata

### 状态

GitHub Issue #31 当前为 OPEN。本条是 WU-OBS-00 / GitHub Issue #70 的前置 signal-contract work unit。Issue 中的 NEW 指 `dayu-agent-r`，OLD 指 `dayu-agent`。当前 NEW 已有 failure error code / diagnostic refs / governed error 等路径，但 analyzer 若只靠文本与错误码分类，会低于 OLD 冷存 `meta.repair_hint` 等结构化诊断粒度。

### 设计与代码核对

- `dayu/host/tool_runtime.py` 当前有 governed error、timeout、accept failure、awaiting configuration failure、duplicate diagnostic refs、`last_error_code` 等结构化路径。
- `dayu/host/tool_trace.py` 当前会把 provider / engine / diagnostic refs、policy decision、truncation、duplicate decision 投影进 `trace_summary`。
- 代码核对未发现稳定 `error_signature`、`repair_hint`、`policy_block_reason`、`provider_error_code` 字段进入 Tool Trace hot / cold projection。
- 现有诊断 refs 可以定位部分失败来源，但 WU-OBS-00 analyzer 若没有结构化 failure metadata，仍会倾向脆弱文本分类。

### 目标

- 设计 Host-owned tool trace failure metadata：`error_signature`、`repair_hint`、`policy_block_reason`、`provider_error_code` 或等价字段。
- 明确字段生产者：ToolRuntime、provider / Engine error classifier、tool result envelope、ToolPolicy decision 或 diagnostic event。
- analyzer 使用结构化字段优先，文本分类只作为 fallback。
- OLD / dayu-agent 可迁移的业务无关 repair hint 语义可以进入 fixture；业务语义或财报领域判断不得进入 Host / Engine。

### 非目标

- 不把字符串正则分类作为唯一真源。
- 不把财报业务 repair hint 写入 Host / Engine。
- 不在 Tool Trace projection 中保存敏感 raw provider payload。
- 不改变 ToolRuntime failure / accept governance 语义。

### 验收信号

- failure pattern / detailed failure pattern 能输出结构化签名。
- analyzer fixture 覆盖 policy block、provider error、tool exception、timeout、schema / value error、truncation failure 等代表路径。
- 文本分类只作为 fallback，有测试证明结构化字段优先。
- 字段来源、redaction 和 durable refs 边界有测试覆盖。

## WU-OBS-P04 Provider Protocol Partial Tool-call Trace Signals

### 状态

GitHub Issue #35 当前为 OPEN。本条是 WU-OBS-00 / GitHub Issue #70 的前置 signal-contract work unit，而不是 analyzer 本体。当前 Engine / Runner 已有 bounded partial tool-call summary contract，但 Host ingest 与 Tool Trace projection 只保留 `partial_tool_call_count`，不足以支撑 #70 analyzer 区分 provider protocol error 无 partial、partial 摘要缺失、partial tool call 存在但 malformed 等诊断。

### 设计与代码核对

- `docs/engine/design.md` 已把 `provider_protocol_error` 定义为 provider 协议解析错误。
- `docs/host/design.md` 的 EventLog matrix 已列出 `PROVIDER_PROTOCOL_ERROR`，但必需 payload 仍是 provider / error code / request ref 级别，未明确 partial tool-call summary 的 Host trace payload。
- `dayu/engine/contracts/partial_tool_call.py` 已定义 `PartialToolCallSummary`，只包含 `tool_call_index`、bounded `tool_call_id`、bounded `name_fragment`、`arguments_byte_size`、`arguments_sha256`，不包含 raw arguments。
- `dayu/engine/contracts/engine_events.py` 的 `ProviderProtocolErrorData` 已包含 `partial_tool_calls: tuple[PartialToolCallSummary, ...]`。
- `dayu/engine/runners/openai/sse_parser.py` 与 `dayu/engine/runners/openai/tool_call_aggregator.py` 会在 provider protocol error 中带上 bounded partial summaries。
- `tests/engine/runners/openai/test_protocol_error.py` 已覆盖 SSE 中途失败时携带 bounded partial tool-call 摘要、摘要条数和字段长度受限、不包含 raw arguments。
- `dayu/host/engine_ingest.py` 当前 `PROVIDER_PROTOCOL_ERROR` diagnostic payload 只写 `partial_tool_call_count`，没有写 partial summaries。
- `dayu/host/tool_trace.py` 当前 diagnostic trace summary 未投影 partial tool-call summary 或 partial malformed 分类字段。

### 目标

- 将 Engine 已提供的 bounded partial tool-call summary 作为 Host-owned diagnostic / trace signal 持久化或投影出来，供 WU-OBS-00 analyzer 消费。
- 明确 `PROVIDER_PROTOCOL_ERROR` 中 partial tool-call 的 Hot / Cold 分层：hot summary 只能保存有界、脱敏、可聚合字段；任何 raw provider payload 仍必须走 payload descriptor / artifact ref 且受 scrub 边界约束。
- 让 analyzer 能稳定区分：无 partial、partial summary missing、partial tool call 存在但 arguments malformed、partial tool name / id 已知但 arguments 不完整、provider raw payload 可用 / 不可用。
- 保持信号来源同源：只能来自 Engine `ProviderProtocolErrorData.partial_tool_calls` 或 Host committed diagnostic event / Tool Trace projection，不从 provider raw stream、日志文本或 analyzer 猜测补造事实。

### 非目标

- 不把 raw arguments 写入 hot trace、EventLog inline payload 或 analyzer report。
- 不让 Host 重新解析 provider raw stream。
- 不改变 Runner / Agent 的 tool-call 解析语义。
- 不在本条实现完整 #70 analyzer report。
- 不把 pending pairing / owner / fencing / recovery 策略混进本条；如仍有该类治理缺口，必须由对应 lifecycle / recovery work unit 承接。

### 验收信号

- `PROVIDER_PROTOCOL_ERROR` 的 Host diagnostic payload 或 Tool Trace projection 中存在可消费的 bounded partial tool-call summary 或等价结构化字段。
- 字段只包含 bounded id / name fragment、arguments size、arguments digest、index 等脱敏摘要，不包含 raw arguments。
- Tool Trace fixture 能覆盖 provider protocol error 无 partial、partial summary present、partial arguments malformed、raw payload present / absent 等代表场景。
- WU-OBS-00 analyzer 可基于该信号输出 provider protocol partial tool-call 诊断；信号缺失时必须报告 limited signal。
- pyright 不新增或扩散类型错误。

## WU-OBS-00 Tool Trace Analyzer

### 状态

GitHub Issue #70 当前为 OPEN。本条是 Tool Trace observability / debug tooling 的基础 work unit：输入已经存在的 Tool Trace 文件或目录，输出结构化 Host / Engine / Tool 分层诊断报告。它不是 #71 的重复，而是 #71 的自然前置能力；#71 负责“先按 prompt / final answer 找到 run 并导出 bundle”，本条负责“对 trace / bundle 做诊断归因”。本条依赖 WU-OBS-P00 / #70 + #117、WU-OBS-P01 / #29、WU-OBS-P02 / #30、WU-OBS-P03 / #31、WU-OBS-P04 / #35 先裁决或补齐 analyzer 所需的核心 trace signals，避免先做出一个只能覆盖 OLD / dayu-agent 受限子集的 analyzer。对 provider / model bug 报障场景，本条应消费 WU-ENG-02 / #63 已完成的 OpenAI-compatible provider debugging correlation signals；#64 的 native Anthropic / Claude Code gateway adapter-specific signals 若尚未实现，报告必须明确 limited signal。GitHub Issue #34 是本条的 analyzer integrity / large payload diagnostics 子项，不单独实现平行 analyzer。

### 设计与代码核对

- `docs/host/design.md` 明确 Tool Trace 是 committed EventLog 的派生 projection，不是 Host recovery、resume、memory 或 Run 状态迁移真源。
- `docs/host/design.md` 要求 trace / audit 能解释工具结果保留、压缩、丢弃、召回失败、证据不足、预算未纳入 RunInput 等原因。
- `dayu/host/tool_trace.py` 当前负责从 committed EventLog 投影 Tool Trace hot row 与 cold JSONL line。
- `dayu/host/durable/tool_trace.py` 当前提供按 `run_id`、`tool_call_id`、`provider_request_id`、`diagnostic_ref` 查询 hot rows 的内部 helper。
- `tests/host/test_tool_trace_projection.py` 与 `tests/host/test_tool_trace_queries.py` 已覆盖 Tool Trace 生产、冷热投影、query helper 与分页。
- `tests/host/test_tool_trace_queries.py` 已覆盖 `provider_request_id` 可查询 terminal diagnostic chain；但当前没有 analyzer report，因此尚未覆盖“报告必须展示 provider 厂商可查 request id”的输出要求。
- 代码核对未发现现有 operator-facing Tool Trace analyzer；也未发现可对 trace 文件 / 目录生成 Host / Engine / Tool 分层诊断 Markdown / structured report 的入口。
- #29 / #30 / #31 / #35 暴露的 context budget snapshot、tool latency、structured failure metadata、provider protocol partial tool-call semantics 尚未全部成为 NEW / dayu-agent-r 的稳定 trace contract。
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

GitHub Issue #93，作为 GitHub Issue #81 的后续子任务；deferred behind #81。#81 会调整 Conversation Memory 与 compact JSON 的目标 shape；本条不应抢先实施。

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

GitHub Issue #94，作为 GitHub Issue #81 的后续子任务；deferred behind #81。terminal summary、assistant conclusion、episode summary、answer anchor 与 continuity 的语义边界会受 #81 Conversation Memory 整体优化影响。

### 目标

- 在 #81 后收敛 terminal summary 的来源、截断、渲染和 fallback policy。
- 避免 terminal summary 与 compact summary、assistant conclusion 语义重叠。
- 固定成功、失败、取消、lost、governance failure 与 compacted episode summary 的文本 policy 矩阵。

### 非目标

- 不在 #81 前抢先实现。
- 不把 terminal summary 变成事实引用源。
- 不改变 Run terminal taxonomy。
- 不让 compact / episode summary 冒充 terminal summary 或 final answer。
- 不借本条引入新的 public result read API。

### 验收信号

- terminal summary 在 success、failure、cancel、governance failure 下语义一致。
- 渲染测试覆盖空 summary、长 summary 和 compact 后 summary。
- memory projection 只在 policy 允许时把 terminal summary 用作 continuity，不得升级为 evidence-backed fact。

## WU-CM-07 Evidence Validation And Pinned State Cleanup

### 状态

过期失效，不再作为独立 work unit 推进。Conversation Memory semantic model cleanup 由 GitHub Issue #81 跟踪。

### 目标

- 无独立实施目标。
- 后续若 #81 仍需要 evidence validation 子任务，应按新的 semantic memory 分类重新建 issue / work unit，不复用本条。

### 非目标

- 不再围绕 `pinned_state` 做局部 cleanup。
- 不在 #81 前为 confirmed subjects、current goal、open questions 等字段预设最终 owner。

### 验收信号

- 无独立验收信号；由 #81 及其后续 scoped issues 重新定义。

## WU-CM-08 Compaction Material Readability And Smoke Maintenance

### 状态

GitHub Issue #95，作为 GitHub Issue #81 的子任务；定位为测试可维护性和 compaction material readability cleanup，不负责裁决 Conversation Memory 语义模型。

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

GitHub Issue #41 当前为 OPEN，已标注 deferred behind #81。当前代码已经具备 P8.5 的保守行为：读到 corrupt / schema-mismatched / digest-mismatched memory snapshot 时 fail closed，进入 typed repair-required 或 projection failure / WARNING，不会自动覆盖损坏 row。本条不在 #81 前实施；#81 完成后再基于 post-#81 memory snapshot contract 设计 quarantine、operator repair command 或自动 rebuild / overwrite policy。

### 设计与代码核对

- `docs/host/design.md` 明确 memory snapshot 是 EventLog 派生 read model，可重建、可修复，不是 Host truth；memory snapshot 与 projection checkpoint 使用同一 SQLite durable store transaction 提交。
- `dayu/host/durable/memory.py` 的 `write_memory_snapshot_with_checkpoint(...)` 在同一 transaction 内写入 snapshot 并推进 projection checkpoint。
- `write_memory_snapshot(...)` 写入前调用 `_validate_snapshot_digest(...)`，并在写入后读回校验。
- `read_memory_snapshot(...)`、`read_latest_memory_snapshot(...)` 与 `read_latest_memory_snapshot_at_or_before(...)` 会解析 snapshot JSON、恢复 typed snapshot、校验 digest，并校验 durable item kind。
- `tests/host/test_run_input_builder.py` 已覆盖 snapshot 缺失和损坏时进入 `MemoryProjectionRepairRequired`，且不改 Run / Attempt / EventLog。
- `tests/host/test_memory_projection.py` 已覆盖旧 `verified_facts` key、旧 durable `verified_fact` item kind fail closed，以及 projection catch-up 遇到 damaged snapshot 时保留 projection failure row。

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
