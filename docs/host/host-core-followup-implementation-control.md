# Host Follow-up Implementation Control

## 文档职责

本文档是 Host follow-up work units 的实施总控文档，负责记录未单独建立 GitHub Issue 跟踪、仍需要后续设计、计划、实施或测试补强的工作项。

本文档只承担实施编排职责：记录 work unit 范围、当前状态、进入 / 退出条件、交付物、验证要求、review 结果、residual risk 和下一步入口。已经有独立 GitHub Issue 跟踪、已经过期失效或已合并到其它 umbrella issue 的条目不进入本文档。

本文档不替代 Host 设计真源，不承载新的架构决策，不作为实现细节说明书。若某个 work unit 的讨论发现需要修改架构边界、状态机、公共接口、durable schema、EventLog 语义或跨层契约，必须先更新设计真源，再更新本文档中的实施编排。

## 设计目标

Host follow-up 实施必须始终服务于以下目标：

- 生产级买方财报分析 Agent。
- 范式是“宿主强约束下的 LLM in the loop”。
- Host 对 Agent / Runner 的生命周期、取消、恢复、等待、上下文治理、审计与 durable truth 保持强约束。
- 严格遵守 `UI -> Service -> Host -> Engine` 分层边界，禁止反向依赖和跨层泄漏实现细节。
- 只补仍真实存在的 correctness、durability、observability、recovery、context governance、tool governance、layering 或测试缺口；不为已经过期、已经有 Issue owner 或已由代码覆盖的问题制造表面 work。
- 每个 work unit 必须形成可验证的行为闭环，且不引入过度设计、过度耦合或无 owner 的 residual risk。

任何 plan、implementation slice、review finding 裁决和 scope 调整，都必须显式对齐这些目标。若某项选择削弱这些目标，应停下来修正设计真源或本文档后再继续。

## 真源层级

Host follow-up 实施遵循以下真源层级：

```text
dayu/README.md
  -> 项目级术语真源
  -> 约束跨层、跨 phase 的稳定术语含义

docs/host/design.md
  -> Host 架构真源
  -> 定义架构边界、状态机、公共接口、EventLog、恢复、并发、等待、上下文治理和关键治理路径

docs/host/host-core-followup-implementation-control.md
  -> follow-up 实施编排文档
  -> 只记录未单独建 Issue 的 work units、当前状态、进入 / 退出条件、交付物、验证要求、review 结论和 residual risk
```

本文档不得引入新的架构边界、状态机、公共接口或事件语义。若实施编排过程中发现需要新的架构决策，应先和用户讨论并同步到设计真源，再更新本文档对应 work unit 的范围、非目标和验收信号。

术语必须遵循项目级术语真源和 Host 设计真源。planning、implementation、review、fix 与 re-review 不得自行重解释 `Session`、`Run`、`Attempt`、`EventLog`、`HostEvent`、`EngineEvent`、`WAITING`、`RECOVERING`、`CONTEXT_COMPACTED`、`CONTEXT_COMPACTION_FAILED`、`ToolRuntime`、`Conversation Memory` 等术语。若发现术语缺失或冲突，应先讨论并同步真源文档，再继续推进。

## 工作流

Host follow-up work unit 采用以下工作流：

```text
read host-core-followup-implementation-control.md
  -> select one work unit
  -> inspect current code and tests
  -> discuss scope, non-goals, risk, and design sufficiency with the user
  -> update docs/host/design.md first if architecture or public contract changes are needed
  -> update this control doc if scope, status, owner, residual risk, or entry point changes
  -> generate code-generation-ready plan for the selected work unit
  -> review plan
  -> user confirmation
  -> implement through the current gate workflow
  -> verify tests, pyright, and relevant README/doc sync
  -> run review / re-review
  -> update current status, artifacts, commits, residual risk, and next entry point
```

每次只推进一个 work unit。进入 plan gate 前，必须先完成代码核对和 scope discussion，确认该 work unit 的风险仍真实存在，且本文档中的目标、非目标和验收信号足以支撑 implementation-ready plan。

work unit plan 必须基于：

- Host 设计真源；
- 本文档中对应 work unit 的背景、目标、非目标、验收信号；
- 代码核对得到的直接证据。

plan 不得从旧设计稿、旧代码路径、非真源讨论记录或 reviewer 个人偏好推导架构边界。
plan 必须避免过度设计；只能解决由代码核对、设计真源和本文档验收信号直接支撑的当前 work unit 风险，不得把局部缺口扩大成通用框架、平台化能力或未来阶段能力。

plan 文档应放在 `docs/host/` 下；plan review、plan fix、plan re-review、implementation review、fix、re-review 和总控裁决 artifact 放在 `docs/reviews/` 下。

每个 work unit discussion 至少需要确认：

- work unit 目标与 success signal；
- 是否服务于本文档的设计目标；
- Host 设计真源是否足够具体；
- scope boundary、non-goals 与 stop conditions；
- 是否需要修改设计真源；
- 是否存在会阻塞 code-generation-ready plan 的架构、状态机、公共接口、schema、持久化或测试问题。

## 仓库发布约定

Host follow-up 实施相关分支的 GitHub remote 名称为 `github`。提交后推送当前分支时使用：

```bash
git push -u github <branch>
```

不得假设 remote 名称为 `origin`。

进入 draft PR gate 前，本文档必须更新当前 work unit 状态、plan artifact、review artifact、accepted commit、remaining risks / owners 和 next entry point。用户授权进入 draft PR gate 后，按既定 gate workflow 自动推进到 `draft-PR-pass`；merge、approve、mark ready for review、request reviewers、delete branch、对外 comment 或创建 / 修改外部 issue 仍需额外授权。

## Slice 切分原则

每个 work unit 内的 implementation slices 在 discussion / plan 阶段再具体确定；总控阶段不预先替 work units 固定 slice。

slice 切分必须同时满足三个约束：

- 模型上下文窗口与 review 可承载复杂度：implementation agent 必须能在一个上下文中理解目标、边界、相关代码和验证要求；review agent 必须能在一个上下文中有效审查。
- 代码依赖边界：slice 应沿稳定模块 ownership、公共契约、状态机边界、存储边界、projection 边界或测试矩阵边界切分，避免一个 slice 同时跨越过多治理 owner。
- 可独立验证的行为闭环：slice 应大到能形成可测试的语义闭环，小到能一次实现、一次验证、一次 review。除非明确是 contract-only slice，否则不得留下只有类型、没有路径，或只有存储、没人调用的孤立半成品。

slice 不是按代码行数切，也不是只要不超过上下文窗口就算合理。好的 slice 应当有明确输入、输出、non-goals、allowed files / modules、验证命令和后续 slice 可依赖的稳定交付物。

如果一个 work unit 的自然闭环超过单个 implementation agent 的上下文容量，应优先按依赖边界拆成多个 slices，并在 plan 中说明前后 slice 的 contract handoff。如果某个 slice 需要跨模块修改，plan 必须解释为什么这是同一个可验证闭环，而不是拆分失败。

## 当前状态

| 项目 | 当前值 |
|---|---|
| phase | Host follow-up implementation backlog |
| gate | implementation |
| implementation status | WU-DUR-01 + WU-DUR-02 已完成：draft-PR-pass；WU-LIFE-01 + WU-LIFE-02 Slice A implementation / review / fix / re-review 已通过；下一步 Slice B implementation |
| active work unit | WU-LIFE-01 + WU-LIFE-02 |
| default next work unit | WU-LIFE-01 + WU-LIFE-02 |
| next entry point | WU-LIFE-01 + WU-LIFE-02 Slice B implementation gate；WU-DUR-01 + WU-DUR-02 merge / ready-for-review / reviewer request require separate authorization |
| design source | docs/host/design.md |
| plan artifacts | docs/host/wu-runtime-01-filelock-contraction-plan.md；docs/host/wu-runtime-02-lane-clock-cancellation-plan.md；docs/host/wu-stress-01-host-production-stress-suite-plan.md；docs/host/wu-dur-01-02-durable-bootstrap-concurrency-plan.md；docs/host/wu-life-01-02-recovery-scheduler-lifecycle-plan.md |
| plan review artifacts | WU-STRESS-01 discussion/code inspection: docs/reviews/wu-stress-01-discussion-code-inspection-20260601.md；plan review: docs/reviews/wu-stress-01-plan-review-mimo-20260601.md, docs/reviews/wu-stress-01-plan-review-ds-20260601.md；controller adjudication: docs/reviews/wu-stress-01-plan-controller-adjudication-20260601.md；plan re-review: docs/reviews/wu-stress-01-plan-rereview-mimo-20260601.md, docs/reviews/wu-stress-01-plan-rereview-ds-20260601.md；WU-DUR-01 + WU-DUR-02 discussion/code inspection: docs/reviews/wu-dur-01-02-discussion-code-inspection-20260601.md；plan review: docs/reviews/wu-dur-01-02-plan-review-mimo-20260601.md, docs/reviews/wu-dur-01-02-plan-review-ds-20260601.md；controller adjudication: docs/reviews/wu-dur-01-02-plan-controller-adjudication-20260601.md；plan fix: docs/reviews/wu-dur-01-02-plan-fix-codex-20260601.md；plan re-review: docs/reviews/wu-dur-01-02-plan-rereview-mimo-20260601.md, docs/reviews/wu-dur-01-02-plan-rereview-ds-20260601.md；WU-LIFE-01 + WU-LIFE-02 discussion/code inspection: docs/reviews/wu-life-01-02-discussion-code-inspection-20260601.md；controller adjudication: docs/reviews/wu-life-01-02-discussion-controller-adjudication-20260601.md；plan review: docs/reviews/wu-life-01-02-plan-review-mimo-20260601.md, docs/reviews/wu-life-01-02-plan-review-ds-20260601.md；plan controller adjudication: docs/reviews/wu-life-01-02-plan-controller-adjudication-20260601.md |
| code review artifacts | WU-STRESS-01 slice1 implementation: docs/reviews/wu-stress-01-implementation-slice1-codex-20260601.md；slice1 code review: docs/reviews/wu-stress-01-code-review-slice1-mimo-20260601.md, docs/reviews/wu-stress-01-code-review-slice1-ds-20260601.md；slice1 controller adjudication: docs/reviews/wu-stress-01-code-controller-adjudication-slice1-20260601.md；slice2 implementation: docs/reviews/wu-stress-01-implementation-slice2-codex-20260601.md；slice2 code review: docs/reviews/wu-stress-01-code-review-slice2-mimo-20260601.md, docs/reviews/wu-stress-01-code-review-slice2-ds-20260601.md；slice2 fix: docs/reviews/wu-stress-01-fix-slice2-codex-20260601.md；slice2 re-review: docs/reviews/wu-stress-01-code-rereview-slice2-mimo-20260601.md, docs/reviews/wu-stress-01-code-rereview-slice2-ds-20260601.md；slice2 controller adjudication: docs/reviews/wu-stress-01-code-controller-adjudication-slice2-20260601.md；slice3 implementation: docs/reviews/wu-stress-01-implementation-slice3-codex-20260601.md；slice3 code review: docs/reviews/wu-stress-01-code-review-slice3-mimo-20260601.md, docs/reviews/wu-stress-01-code-review-slice3-ds-20260601.md；slice3 fix: docs/reviews/wu-stress-01-fix-slice3-codex-20260601.md；slice3 re-review: docs/reviews/wu-stress-01-code-rereview-slice3-mimo-20260601.md, docs/reviews/wu-stress-01-code-rereview-slice3-ds-20260601.md；slice3 final re-review: docs/reviews/wu-stress-01-code-final-rereview-slice3-mimo-20260601.md, docs/reviews/wu-stress-01-code-final-rereview-slice3-ds-20260601.md；slice3 controller adjudication: docs/reviews/wu-stress-01-code-controller-adjudication-slice3-20260601.md；slice4 implementation: docs/reviews/wu-stress-01-implementation-slice4-codex-20260601.md；slice4 code review: docs/reviews/wu-stress-01-code-review-slice4-mimo-20260601.md, docs/reviews/wu-stress-01-code-review-slice4-ds-20260601.md；slice4 fix: docs/reviews/wu-stress-01-fix-slice4-codex-20260601.md；slice4 re-review: docs/reviews/wu-stress-01-code-rereview-slice4-mimo-20260601.md, docs/reviews/wu-stress-01-code-rereview-slice4-ds-20260601.md；slice4 final re-review: docs/reviews/wu-stress-01-code-final-rereview-slice4-mimo-20260601.md, docs/reviews/wu-stress-01-code-final-rereview-slice4-ds-20260601.md；slice4 controller adjudication: docs/reviews/wu-stress-01-code-controller-adjudication-slice4-20260601.md；slice5 implementation: docs/reviews/wu-stress-01-implementation-slice5-codex-20260601.md；slice5 code review: docs/reviews/wu-stress-01-code-review-slice5-mimo-20260601.md, docs/reviews/wu-stress-01-code-review-slice5-ds-20260601.md；slice5 fix: docs/reviews/wu-stress-01-fix-slice5-codex-20260601.md；slice5 re-review: docs/reviews/wu-stress-01-code-rereview-slice5-mimo-20260601.md, docs/reviews/wu-stress-01-code-rereview-slice5-ds-20260601.md；slice5 controller adjudication: docs/reviews/wu-stress-01-code-controller-adjudication-slice5-20260601.md；WU-DUR-01 + WU-DUR-02 slice1 implementation: docs/reviews/wu-dur-01-02-implementation-slice1-codex-20260601.md；slice1 code review: docs/reviews/wu-dur-01-02-code-review-slice1-mimo-20260601.md, docs/reviews/wu-dur-01-02-code-review-slice1-ds-20260601.md；slice1 controller adjudication: docs/reviews/wu-dur-01-02-code-controller-adjudication-slice1-20260601.md；slice1 fix: docs/reviews/wu-dur-01-02-fix-slice1-codex-20260601.md；slice1 re-review: docs/reviews/wu-dur-01-02-code-rereview-slice1-mimo-20260601.md, docs/reviews/wu-dur-01-02-code-rereview-slice1-ds-20260601.md；slice2 implementation: docs/reviews/wu-dur-01-02-implementation-slice2-codex-20260601.md；slice2 code review: docs/reviews/wu-dur-01-02-code-review-slice2-mimo-20260601.md, docs/reviews/wu-dur-01-02-code-review-slice2-ds-20260601.md；slice2 controller adjudication: docs/reviews/wu-dur-01-02-code-controller-adjudication-slice2-20260601.md；slice2 fix: docs/reviews/wu-dur-01-02-fix-slice2-codex-20260601.md；slice2 re-review: docs/reviews/wu-dur-01-02-code-rereview-slice2-mimo-20260601.md, docs/reviews/wu-dur-01-02-code-rereview-slice2-ds-20260601.md；slice3 implementation: docs/reviews/wu-dur-01-02-implementation-slice3-codex-20260601.md；slice3 code review: docs/reviews/wu-dur-01-02-code-review-slice3-mimo-20260601.md, docs/reviews/wu-dur-01-02-code-review-slice3-ds-20260601.md；slice3 controller adjudication: docs/reviews/wu-dur-01-02-code-controller-adjudication-slice3-20260601.md；slice4 implementation: docs/reviews/wu-dur-01-02-implementation-slice4-codex-20260601.md；slice4 code review: docs/reviews/wu-dur-01-02-code-review-slice4-mimo-20260601.md, docs/reviews/wu-dur-01-02-code-review-slice4-ds-20260601.md；slice4 controller adjudication: docs/reviews/wu-dur-01-02-code-controller-adjudication-slice4-20260601.md；slice4 fix: docs/reviews/wu-dur-01-02-fix-slice4-codex-20260601.md；slice4 re-review: docs/reviews/wu-dur-01-02-code-rereview-slice4-mimo-20260601.md, docs/reviews/wu-dur-01-02-code-rereview-slice4-ds-20260601.md |
| implementation commits | WU-RUNTIME-01 accepted plan: 929d01c；WU-RUNTIME-01 accepted slice1: 7b5b3aa；WU-RUNTIME-01 accepted slice2: 51648be；WU-RUNTIME-01 accepted deepreview: 6980c96；WU-RUNTIME-01 accepted PR review: 9bf87a4；WU-RUNTIME-02 accepted plan: fa34592；WU-RUNTIME-02 accepted slice1: 1be0259；WU-RUNTIME-02 accepted slice2: 5675886；WU-RUNTIME-02 accepted deepreview: ce36bff；WU-RUNTIME-02 accepted PR review: 442e05b；WU-STRESS-01 accepted plan: cb599e9；WU-STRESS-01 accepted slice1: ffcc7e5；WU-STRESS-01 accepted slice2: 8cc6668；WU-STRESS-01 accepted slice3: 4bb6eea；WU-STRESS-01 accepted slice4: 633e373；WU-STRESS-01 accepted slice5: 969f757；WU-STRESS-01 accepted deepreview: 38d4b7e；WU-STRESS-01 accepted PR review: 878eb15；WU-DUR-01 + WU-DUR-02 accepted plan: d6837eb；WU-DUR-01 + WU-DUR-02 accepted slice1: 8da01e4；WU-DUR-01 + WU-DUR-02 accepted slice2: 5046255；WU-DUR-01 + WU-DUR-02 accepted slice3: 796119d；WU-DUR-01 + WU-DUR-02 accepted slice4: 6c32bdf；WU-DUR-01 + WU-DUR-02 accepted deepreview: 503fe51；WU-DUR-01 + WU-DUR-02 accepted PR review: 103a909；WU-LIFE-01 + WU-LIFE-02 accepted plan: 975b9ba |
| review artifacts | docs/reviews/wu-runtime-01-plan-review-mimo-20260601.md；docs/reviews/wu-runtime-01-plan-review-ds-20260601.md；docs/reviews/wu-runtime-01-plan-rereview-mimo-20260601.md；docs/reviews/wu-runtime-01-plan-rereview-ds-20260601.md；docs/reviews/wu-runtime-01-plan-controller-adjudication-20260601.md；docs/reviews/wu-runtime-01-implementation-slice1-codex-20260601.md；docs/reviews/wu-runtime-01-fix-slice1-codex-20260601.md；docs/reviews/wu-runtime-01-code-review-mimo-20260601.md；docs/reviews/wu-runtime-01-code-review-ds-20260601.md；docs/reviews/wu-runtime-01-code-rereview-mimo-20260601.md；docs/reviews/wu-runtime-01-code-rereview-ds-20260601.md；docs/reviews/wu-runtime-01-code-controller-adjudication-20260601.md；docs/reviews/wu-runtime-01-implementation-slice2-codex-20260601.md；docs/reviews/wu-runtime-01-code-review-slice2-mimo-20260601.md；docs/reviews/wu-runtime-01-code-review-slice2-ds-20260601.md；docs/reviews/wu-runtime-01-code-rereview-slice2-mimo-20260601.md；docs/reviews/wu-runtime-01-code-rereview-slice2-ds-20260601.md；docs/reviews/wu-runtime-01-code-controller-adjudication-slice2-20260601.md；docs/reviews/wu-runtime-01-pr-review-mimo-20260601.md；docs/reviews/wu-runtime-01-pr-review-ds-20260601.md；docs/reviews/wu-runtime-01-pr-review-controller-adjudication-20260601.md；docs/reviews/wu-runtime-02-plan-review-mimo-20260601.md；docs/reviews/wu-runtime-02-plan-review-ds-20260601.md；docs/reviews/wu-runtime-02-plan-rereview-mimo-20260601.md；docs/reviews/wu-runtime-02-plan-rereview-ds-20260601.md；docs/reviews/wu-runtime-02-plan-controller-adjudication-20260601.md；docs/reviews/wu-runtime-02-implementation-slice1-codex-20260601.md；docs/reviews/wu-runtime-02-code-review-slice1-mimo-20260601.md；docs/reviews/wu-runtime-02-code-review-slice1-ds-20260601.md；docs/reviews/wu-runtime-02-code-controller-adjudication-slice1-20260601.md；docs/reviews/wu-runtime-02-implementation-slice2-codex-20260601.md；docs/reviews/wu-runtime-02-code-review-slice2-mimo-20260601.md；docs/reviews/wu-runtime-02-code-review-slice2-ds-20260601.md；docs/reviews/wu-runtime-02-fix-slice2-codex-20260601.md；docs/reviews/wu-runtime-02-code-rereview-slice2-mimo-20260601.md；docs/reviews/wu-runtime-02-code-rereview-slice2-ds-20260601.md；docs/reviews/wu-runtime-02-code-controller-adjudication-slice2-20260601.md；docs/reviews/wu-runtime-02-pr-review-mimo-20260601.md；docs/reviews/wu-runtime-02-pr-review-ds-20260601.md；docs/reviews/wu-runtime-02-pr-review-controller-adjudication-20260601.md；docs/reviews/wu-stress-01-discussion-code-inspection-20260601.md；docs/reviews/wu-dur-01-02-discussion-code-inspection-20260601.md；docs/reviews/wu-life-01-02-discussion-code-inspection-20260601.md；docs/reviews/wu-life-01-02-discussion-controller-adjudication-20260601.md；docs/reviews/wu-life-01-02-plan-review-mimo-20260601.md；docs/reviews/wu-life-01-02-plan-review-ds-20260601.md；docs/reviews/wu-life-01-02-plan-controller-adjudication-20260601.md |
| aggregate review artifacts | docs/reviews/wu-runtime-01-aggregate-deepreview-mimo-20260601.md；docs/reviews/wu-runtime-01-aggregate-deepreview-ds-20260601.md；docs/reviews/wu-runtime-01-aggregate-controller-adjudication-20260601.md；docs/reviews/wu-runtime-02-aggregate-deepreview-mimo-20260601.md；docs/reviews/wu-runtime-02-aggregate-deepreview-ds-20260601.md；docs/reviews/wu-runtime-02-aggregate-controller-adjudication-20260601.md；docs/reviews/wu-stress-01-aggregate-deepreview-mimo-20260601.md；docs/reviews/wu-stress-01-aggregate-deepreview-ds-20260601.md；docs/reviews/wu-stress-01-aggregate-controller-adjudication-20260601.md；WU-DUR-01 + WU-DUR-02 aggregate deepreview: docs/reviews/wu-dur-01-02-aggregate-deepreview-mimo-20260601.md, docs/reviews/wu-dur-01-02-aggregate-deepreview-ds-20260601.md；controller adjudication: docs/reviews/wu-dur-01-02-aggregate-controller-adjudication-20260601.md；aggregate fix: docs/reviews/wu-dur-01-02-fix-aggregate-codex-20260601.md；focused re-review: docs/reviews/wu-dur-01-02-aggregate-rereview-mimo-20260601.md, docs/reviews/wu-dur-01-02-aggregate-rereview-ds-20260601.md |
| PR review artifacts | WU-STRESS-01 PR review: docs/reviews/wu-stress-01-pr-review-mimo-20260601.md, docs/reviews/wu-stress-01-pr-review-ds-20260601.md；PR fix: docs/reviews/wu-stress-01-fix-pr-codex-20260601.md；PR focused re-review: docs/reviews/wu-stress-01-pr-rereview-mimo-20260601.md, docs/reviews/wu-stress-01-pr-rereview-ds-20260601.md；controller adjudication: docs/reviews/wu-stress-01-pr-review-controller-adjudication-20260601.md；WU-DUR-01 + WU-DUR-02 PR review: docs/reviews/wu-dur-01-02-pr-review-mimo-20260601.md, docs/reviews/wu-dur-01-02-pr-review-ds-20260601.md；controller adjudication: docs/reviews/wu-dur-01-02-pr-review-controller-adjudication-20260601.md |
| draft PR status | WU-DUR-01 + WU-DUR-02 draft PR opened and PR review passed: https://github.com/noho/dayu-agent-r/pull/103；WU-STRESS-01 draft PR opened and PR review passed: https://github.com/noho/dayu-agent-r/pull/102；WU-RUNTIME-02 draft PR opened and PR review passed: https://github.com/noho/dayu-agent-r/pull/101；WU-RUNTIME-01 previous draft PR opened and PR review passed: https://github.com/noho/dayu-agent-r/pull/100 |
| blocking open questions | none |

### WU-LIFE-01 + WU-LIFE-02 当前 Gate Artifacts

| Gate / Slice | 状态 | Artifacts | Validation |
|---|---|---|---|
| discussion / code inspection | passed | docs/reviews/wu-life-01-02-discussion-code-inspection-20260601.md；docs/reviews/wu-life-01-02-discussion-controller-adjudication-20260601.md | n/a |
| plan | accepted | docs/host/wu-life-01-02-recovery-scheduler-lifecycle-plan.md；docs/reviews/wu-life-01-02-plan-review-mimo-20260601.md；docs/reviews/wu-life-01-02-plan-review-ds-20260601.md；docs/reviews/wu-life-01-02-plan-controller-adjudication-20260601.md | n/a |
| Slice A implementation / review / fix / re-review | passed | docs/reviews/wu-life-01-02-implementation-sliceA-codex-20260601.md；docs/reviews/wu-life-01-02-code-review-sliceA-mimo-20260601.md；docs/reviews/wu-life-01-02-code-review-sliceA-ds-20260601.md；docs/reviews/wu-life-01-02-code-controller-adjudication-sliceA-20260601.md；docs/reviews/wu-life-01-02-fix-sliceA-codex-20260601.md；docs/reviews/wu-life-01-02-code-rereview-sliceA-mimo-20260601.md；docs/reviews/wu-life-01-02-code-rereview-sliceA-ds-20260601.md | `pytest tests/host/test_recovery_scan.py tests/host/test_recovery_dispatch.py tests/host/test_recovery_orphan_classifier.py -q` -> 33 passed；`python -m pyright dayu/ tests/ utils/` -> 0 errors |

状态约定：

- `not-started`：尚未进入 plan / implementation。
- `discussion-ready`：已具备讨论和代码核对入口，但还未形成 code-generation-ready plan。
- `planning`：正在形成或 review code-generation-ready plan。
- `implementation`：正在实施或修复。
- `review`：正在进行 code review、re-review 或 aggregate deepreview。
- `ready-to-open-draft-PR`：本轮 work unit 已完成本地 gate，等待进入 draft PR gate。
- `draft-PR-pass`：draft PR gate 已通过。

## 推进规则

- 每次只推进一个 work unit。
- 先做代码核对，再进入方案和实现。
- 涉及 public contract、durable schema、状态机、跨层依赖或用户可见行为时，必须先形成明确 design decision。
- 测试优先按风险边界补齐；压力测试和长耗时测试必须与常规测试入口分开。
- 实施完成后必须更新对应测试、类型检查和稳定文档说明。
- 每个 work unit 进入 plan、implementation、review、ready-to-open-draft-PR 或 draft-PR-pass 时，必须更新“当前状态”中的 gate、active work unit、artifact、commit、review 和 residual risk 信息。

## Residual Risk / 遗留问题追踪

本章节专门追踪实施过程中发现但未在当前 work unit 内关闭的 residual risk、遗留问题、测试缺口、设计疑问和后续 owner。不得把这类事项只停留在对话、review artifact 或 implementation report 中。

追踪规则：

- 每条 tracking item 必须有稳定 id、来源 work unit、状态、owner / destination 和下一步动作。
- `ready-to-open-draft-PR` 前，所有 tracking items 必须处于 `closed`、`deferred-with-owner` 或 `transferred-to-issue`，不得保留无 owner 的 open item。
- 如果 residual risk 需要修改 Host 架构、公共契约、状态机、durable schema 或 EventLog 语义，必须先同步设计真源，再更新本表。
- 如果 residual risk 已由代码核对证明不存在，应标记 `closed` 并记录关闭依据，不继续保留为模糊风险。

状态值：

- `open`：仍需当前 work unit 或本轮 phase 处理。
- `deferred-with-owner`：明确后续 owner / work unit / issue，当前 work unit 不处理。
- `transferred-to-issue`：已迁移到独立 GitHub Issue 或等价外部追踪项。
- `closed`：已通过实现、测试、设计裁决或代码核对关闭。

| ID | 来源 | 类型 | 状态 | Owner / Destination | 下一步 | 记录 |
|---|---|---|---|---|---|---|
| RR-STRESS-01 | WU-STRESS-01 aggregate deepreview | 测试边界 | deferred-with-owner | WU-STRESS residual risk / future hardening if needed | 当前 work unit 不扩展为 fuzz / soak；若未来需要更高规格覆盖，单独开 hardening work unit | 当前 stress suite 是可重复、确定性、有限预算 production hardening suite，验收信号未要求不可控 fuzz 或长时 soak。 |
| RR-STRESS-02 | WU-STRESS-01 aggregate deepreview | 测试工具限制 | deferred-with-owner | pytest-timeout limitation accepted by WU-STRESS-01 | 保留 pytest-timeout 作为外层兜底；若 event loop 全局卡死，允许 timeout 先于内部 summary 终止 | 内部摘要覆盖可恢复失败；全局卡死时测试框架强杀是预期兜底，不改变 Host 语义。 |
| RR-DUR-01 | WU-DUR-01 + WU-DUR-02 aggregate deepreview | projection checkpoint 真实多进程 CAS race 证明 | closed | WU-LIFE-01 + WU-LIFE-02 discussion/code inspection | 无后续动作 | WU-LIFE code inspection 证明 recovery scanner 只依赖 Run / Attempt / dispatch / liveness durable truth，不依赖 projection checkpoint；已有 recovery projection-lag 测试与 deterministic checkpoint CAS 测试足以支撑当前 work unit，不把真实多进程 projection CAS race 纳入 WU-LIFE。 |
| RR-DUR-02 | WU-DUR-01 + WU-DUR-02 aggregate deepreview | WAL checkpoint connection / db_path 一致性校验 | deferred-with-owner | future Host maintenance hardening | 若后续把 checkpoint primitive 接入 production maintenance caller，先增加 connection 与 db_path 一致性校验 | 当前 primitive 是内部 diagnostic-only/test entry，未接入 hot path 或 public API，现有调用方传入同一 store 的 connection/path pair。 |
| RR-DUR-03 | WU-DUR-01 + WU-DUR-02 aggregate deepreview | schema validation 批量缺失对象诊断 | deferred-with-owner | WU-LAYER-01 schema invariant hardening | 后续 schema invariant hardening 可把 fail-fast 单对象错误升级为批量缺失对象报告 | 当前 fail-closed 行为满足 WU-DUR 验收信号；批量诊断属于运维可读性增强。 |
| RR-DUR-04 | WU-DUR-01 + WU-DUR-02 aggregate deepreview | production long read transaction governance scan | closed | WU-LIFE-01 Slice A recovery lifecycle proof | 无后续动作 | Slice A 已将 RR-DUR-04 纳入 recovery lifecycle proof matrix，并由 tests/host/test_recovery_scan.py 的 deterministic scanner tests 与既有 projection-lag recovery tests 证明 recovery scanner 使用 durable truth；未发现 long read transaction 或 projection lag 作为 governance truth 的生产误用。 |
| RR-DUR-05 | WU-DUR-01 + WU-DUR-02 aggregate deepreview | index definition / DDL text invariant validation | deferred-with-owner | WU-LAYER-01 schema invariant hardening | 后续如需抵御同名但定义错误的 index，再扩展 schema invariant validation | WU-DUR 当前只要求 required table/index existence fail-closed；full DDL text/index definition validation 已由 plan 明确 defer。 |

## 当前 Work Units

| Work Unit | 主题 | 当前定位 | 完成状态 |
|---|---|---|---|
| WU-AUDIT-01 | Purge audit orphan reconciliation | purge audit JSONL 与 SQLite tombstone 一致性 | 已完成 |
| WU-STRESS-01 | Host production stress suite | crash / recovery / watch / scheduler 组合压力 | 已完成：draft-PR-pass |
| WU-DUR-01 | Schema bootstrap / WAL checkpoint | durable bootstrap 原子性与维护策略 | 已完成：draft-PR-pass |
| WU-DUR-02 | Durable concurrency matrix | durable 并发冲突测试矩阵 | 已完成：draft-PR-pass |
| WU-LIFE-01 | Recovery lifecycle proof | recovery 决策矩阵与诊断 | Slice A implementation / review / fix / re-review 已通过 |
| WU-LIFE-02 | Scheduler close / cancel_all | scheduler close 极端窗口治理 | plan review passed；等待 Slice B implementation |
| WU-CTX-02 | Compact failure policy | compact failure 策略矩阵与 E2E | 未开始 |
| WU-CTX-03 | Reactive overflow loop E2E | reactive overflow 循环收口测试 | 未开始 |
| WU-TOOL-01 | Duplicate governance scope | duplicate governance 从 run-scope 改为 attempt-scope | 未开始 |
| WU-TOOL-02 | Accept candidate cleanup | ToolRuntime accept candidate 结构拆分 | 未开始 |
| WU-ENGINE-01 | Runner diagnostic payload audit | provider state 降级为 diagnostic payload audit | 未开始 |
| WU-LAYER-01 | Durable row primitive cleanup | 显式 SQL / typed row / schema invariant 收口 | 未开始 |
| WU-LAYER-02 | Shared helper consolidation | 层中立 validation / redaction / JSON helper 小清理 | 未开始 |
| WU-RUNTIME-01 | Runtime file lock wrapper contraction | 收缩 `RuntimeFileLock`，只保留必要异常边界 / parent directory / audit 文件互斥职责 | 已完成 |
| WU-RUNTIME-02 | Runtime lane clock and cancellation simplification | 保留多进程 named semaphore 抽象，修正跨进程 TTL 时间真源和无限等待控制流 | 已完成 |

## WU-AUDIT-01 Purge Audit Cross-medium Orphan Reconciliation

### 背景

`purge_session` 会产生 destructive 操作审计。审计 JSONL append 与 SQLite tombstone commit 不是同一个持久介质里的同一个事务，因此可能出现 JSONL 已经写入、SQLite tombstone 没有提交成功的 orphan 状态。

### 目标

- 将 purge audit JSONL 定义为 destructive 操作流水，而不是 purge 完成真源。
- 至少区分 `purge_started` 与 `purge_completed`：`purge_started` 只表示 purge attempt 已发起；`purge_completed` 必须在 SQLite tombstone commit 成功后写入，并引用 tombstone id / digest。
- 可选写入 `purge_failed`，记录失败阶段和原因。
- audit 查询 / analyze 必须以 SQLite tombstone 判断 purge 是否完成；只有 started 而无 completed / tombstone 时，只能报告 incomplete attempt，不得报告 purge 已完成。

### 非目标

- 不扩大为通用审计管道治理。
- 不让 audit JSONL 反向成为 Host durable truth。

### 验收信号

- 测试覆盖 started audit 写入成功但 SQLite purge / tombstone commit 失败的路径，并断言不会误报 purge 已完成。
- 测试覆盖 tombstone commit 成功后 completed audit line 引用 tombstone id / digest。
- audit analyze / diagnostic 能解释 started-only、completed-with-tombstone、failed 三类状态。

## WU-STRESS-01 Host Crash / Recovery / Watch Production Stress Suite

### 背景

现有普通 SQLite 多进程压力测试足够作为日常语义回归，可覆盖主要 EventLog sequence、identity conflict、admission invariant、recovery takeover 与 runtime lane capacity 回归。更高规格的慢盘 / Docker Linux / 高延迟文件系统 SQLite 压力由既有外部跟踪项负责。本条聚焦 Host 组合行为压力：crash recovery、watch 轮询 / cursor lag、scheduler / liveness 长时间运行，以及这些行为同时发生时的可恢复性。

### 目标

- 建立可重复运行的 production hardening stress suite。
- 覆盖 repeated startup / recovery / crash E2E：反复启动 Host、提交 Run、在 worker accepted / running / terminal closeout 附近制造进程退出，再 reopen，验证不会重复 terminal、不会漏 recovery event、不会错误恢复 live owner。
- 覆盖 sustained watch stress：多个 session / run 持续产生日志与 terminal event，watcher 长时间消费、慢消费、断开后重连时，验证 cursor 不倒退、不漏关键 terminal、observer lag 有上界且有诊断输出。
- 覆盖 scheduler / liveness long-run stress：大量 queued / active / terminal / cancel / recovery 混合流转下，验证 scheduler 不停摆、host instance heartbeat / stale 判断可解释、close 后无遗留 active task。
- 覆盖 mixed Host stress：在 fake worker / fake clock / deterministic fault injection 下组合 crash、recovery、watch 和 scheduler 压力，证明 Host 仍然可恢复、可观察、可终止。

### 非目标

- 不用 stress suite 替代精确单元测试。
- 不放进默认常规测试入口；pressure / stress 测试必须与 unit / integration / public smoke 分开。
- 不在测试中依赖不可控睡眠或外部服务。
- 不重复实现 SQLite 多进程压力测试的高规格环境版。

### 验收信号

- stress suite 有独立运行入口、明确 marker / 命令、超时预算和失败诊断；默认快速 pytest / 常规 CI 可以排除它。
- 每类压力测试输出结构化摘要，包括 session / run 数、crash 次数、recovery 次数、watch lag、scheduler drain 状态、liveness stale 判断和 terminal 去重结果。
- 压测失败能定位到 durable、scheduler、watch、liveness 或 recovery 边界。

## WU-DUR-01 Schema Bootstrap / DDL Atomicity / WAL Checkpoint Policy

### 背景

Durable store 已有 `BEGIN IMMEDIATE`、WAL、busy retry 和 after-commit 多错误聚合测试。剩余风险集中在 fresh bootstrap DDL 与 `user_version` 是否同成同败、current-version DB 是否会被静默补表、WAL checkpoint 是否有 Host-owned maintenance policy，以及 read transaction 的 stale snapshot 语义是否被治理路径误用。

### 目标

- 明确 fresh bootstrap 原子性：fresh DB 的全量 DDL 与 `PRAGMA user_version` 必须同成同败；DDL 中途失败不得留下带 current `user_version` 的半初始化 durable store。
- 明确 current-version schema validation：普通 opener 不得把缺表 / 缺索引的 current-version DB 静默修好；需要结构化失败或显式 offline repair / rebuild 工具。
- 设计 WAL checkpoint 策略：现有 auto-checkpoint 是 baseline；后续 maintenance checkpoint 必须有独立触发点、运行时机、失败诊断、WAL size / checkpoint result 观测，不得把 checkpoint 成功作为 EventLog correctness 前置条件。
- 定义 read stale 语义：单个 read transaction 内允许稳定旧快照；需要 fresh truth 的 public read / recovery / scheduler governance 必须开启新的短 read / write transaction。

### 非目标

- 不重做已存在的 busy retry、after-commit aggregation 或基础 transaction wrapper。
- 不引入旧 schema 兼容迁移。
- 不在 Host hot write path 内做阻塞型 WAL checkpoint。
- 不把 read model / projection lag 当作 Host governance truth。

### 验收信号

- 有直接测试模拟 bootstrap DDL 中途失败，断言不会留下 current `user_version` + 半初始化 schema。
- 有直接测试构造 current `user_version` 但缺少 required table / index 的 DB，断言 opener 不静默补建并继续运行。
- WAL checkpoint 行为可观测、可测试，且不破坏并发读写；checkpoint busy / failure 有诊断，不改变 EventLog / state truth。
- read stale 语义有直接测试：长 read transaction 可观察旧快照，新 read transaction 必须观察到已提交事实；public read / recovery governance 不依赖长 read transaction 或 projection lag。

## WU-DUR-02 Durable Concurrency Conflict Matrix

### 背景

Projection checkpoint、memory snapshot、transaction retry 已有专门测试。剩余缺口是把 EventLog append、idempotency write、session ensure、projection CAS、memory CAS、liveness update 放入同一个并发冲突矩阵验证。

### 目标

- 先整理 durable 并发冲突矩阵，核对已有测试覆盖，再只补缺口测试。
- 梳理 durable 写入面的唯一键冲突、CAS 失败、busy retry、rollback failure 与 liveness update 行为。
- 补齐直接单元测试和必要的多进程压力测试。
- 只有当新增测试暴露错误分类、诊断或并发语义不稳定时，才修改生产代码。

### 非目标

- 不把所有 durable 操作抽象成同一个 God helper。
- 不用 broad exception catch 掩盖 SQLite extended result code。
- 不为了统一测试而重构已有稳定 durable API。

### 验收信号

- durable concurrency matrix 明确列出每类场景的已有测试、缺口测试、期望错误分类和是否需要多进程验证。
- 每类冲突都有稳定 reason / diagnostic。
- 并发测试能区分可重试 busy、业务冲突、CAS stale 和不可恢复 I/O 错误。

## WU-LIFE-01 Recovery Lifecycle Proof and Diagnostics

### 背景

Host 已有 startup recovery、public lifecycle 和 orphan/recovery 相关测试。剩余项主要是 recovery lifecycle 决策矩阵与测试矩阵补强，不预设需要重写 recovery 生产逻辑。

### 目标

- 整理 recovery lifecycle matrix，列出 Run 状态、owner proof、dispatch / startup / stream 失败点、期望 decision、期望 durable mutation、期望 diagnostic reason。
- 对照已有测试只补缺口测试；只有当测试暴露 reason 不可区分、diagnostic payload 不足或状态转换不稳定时，才修改生产代码。
- 补齐 liveness proof、promotion deferred result、startup timeout closeout diagnostic、recovery orphan proof 的组合验证。
- 明确 `WAITING` startup recovery 仅 diagnostic 的用户可见语义。

### 非目标

- 不改变 `WAITING` 本身的 durable 状态语义，除非先形成新的设计裁决。
- 不把 recovery proof 写成只验证实现细节的 brittle test。

### 验收信号

- recovery 后每类 orphan / deferred / startup-timeout 状态都有唯一解释路径。
- diagnostic payload 足以区分恢复、关闭、取消和 fatal stream。
- 测试矩阵能标注每个场景是已有覆盖、新增覆盖还是明确非目标；新增测试不依赖竞态运气或实现私有顺序。

## WU-LIFE-02 Scheduler Close / Cancel-all Lifecycle Hardening

### 背景

Scheduler close 已有基本治理和测试：关闭 flag、取消 heartbeat / dispatch drain / promotion drain task、调用 active worker 快照取消、关闭 lane controller，并 best-effort 标记 host instance stopping / stopped。剩余风险集中在 close / cancel_all 的极端窗口矩阵。

### 目标

- 整理 scheduler close / cancel_all lifecycle matrix，明确 close 前、close 中、close 后各窗口的期望行为。
- 明确 `cancel_all` 是快照取消语义；后续注册 / 启动窗口必须由 close gate、active task cancellation、lane close 与 next-open recovery 兜底。
- 明确 close 不无限 drain dispatch / promotion queue；内存队列剩余项不在 close 中强行执行，durable pending / running 状态由下次 open 的 recovery / promotion / dispatch 解释。
- 明确 scheduler close 本身不写 cancel / failed / lost terminal facts；只有已经进入明确 worker stream / engine ingest closeout 的路径可以写 terminal facts。
- 对照已有测试只补缺口测试；只有测试暴露资源泄漏、terminal fact 误写或诊断不可解释时，才修改生产代码。

### 非目标

- 不把 close 设计成无限 drain。
- 不让 close 隐式创建新 Run terminal 状态。

### 验收信号

- close 中途取消、重复 close、queue 非空、worker 已启动但未入 durable 状态、cancel_all 快照后新注册窗口都有稳定行为。
- close 后 wake 方法 fail closed；close 不无限 drain，也不静默丢失 durable truth。
- scheduler close 不因自身动作追加 cancel / failed / lost terminal facts。
- 测试矩阵能标注每个场景是已有覆盖、新增覆盖还是明确非目标；新增测试不依赖竞态运气。

## WU-CTX-02 Compact Failure User-visible Policy and E2E Matrix

### 背景

Compact 是 Host 核心组件，因此不允许无解释失败、半成功提交或状态不清。但 LLM compactor、provider、artifact I/O 和 token sizing 都可能失败，生产语义必须是分层兜底与 fail-safe，而不是假设组件永不失败。

### 目标

- 建立 compact failure 策略矩阵，列出触发来源、失败类型、retry / repair 策略、是否允许 deterministic fallback、最终 EventLog、Run 终态、用户可见结果和测试入口。
- 明确 compact failure 何时 retry、何时 partial materialize、何时 fail closed、何时只记录 diagnostic。
- 补齐 proactive / reactive compact failure E2E。
- 将默认 `max_compaction_attempts_per_operation` 提升到 5 次，并对齐 execution profile 默认值与 Host policy code fallback 默认值。
- 默认 compact 模型使用低延迟 flash-tier 模型；高规格模型只能由 profile 显式选择。
- 清理 compactor model 默认来源不一致，确保 packaged default 不互相矛盾。
- 为核心 compact 可靠性定义分层兜底：deterministic material selection / 去重 / 分段缩小输入、LLM compactor bounded repair、deterministic recent-window fallback、明确 rejected / failed terminal。
- deterministic recent-window fallback 不是 compact 成功：它不提交 `CONTEXT_COMPACTED`，不生成 episode summary、minimum preserve 或 stable facts，只为本次 dispatch 构造 bounded input view；但它必须通过 `CONTEXT_COMPACTION_FAILED` 或等价 diagnostic 记录 compact 失败、fallback policy decision、fallback input window / digest 与重新估算结果，不能静默发生。
- fallback 后必须重新估算预算；能放下才 dispatch，仍超预算则 fail closed。

### 非目标

- 不改变 fact-candidate-only 的裁决，除非先形成新的设计裁决。
- 不吞掉 compactor 失败。
- 不承诺 LLM compactor 永不失败。
- 不让 deterministic fallback 生成 evidence-backed facts 或替代 accepted evidence。
- 不把 deterministic recent-window fallback 写成 durable memory projection。

### 验收信号

- 每类 compact failure 都有用户可见或 diagnostic 结果。
- 默认 compact retry budget 为 5 次 semantic proposal / repair attempts；测试覆盖首轮失败、repair 成功、repair 耗尽与 fallback 收口。
- packaged 默认 compact model 与 scene / execution profile 配置一致；默认路径使用 flash-tier 模型，高规格模型只能由 profile 显式选择。
- post-compact budget estimate 失败不会产生 silent overflow。
- proactive / reactive / semantic repair / post-compact overflow 的组合矩阵标注已有测试、新增测试或明确非目标。
- deterministic recent-window fallback 不得伪造 stable facts；采用 fallback 时必须有 EventLog / diagnostic 痕迹，watch / diagnostic / 测试可观察；仍超预算时必须明确 terminal，不得继续 dispatch。
- compact failure 不会留下 orphan Attempt、重复 terminal、partial compacted event 或 memory projection 半物化。

## WU-CTX-03 Reactive Overflow Dispatch Loop E2E

### 背景

Deterministic recent-window fallback 落地后，reactive overflow 反复 compact / dispatch 的概率会显著降低；但仍需要一条 dispatch-loop E2E 证明 fallback 未兜住、估算偏差或 provider 持续 overflow 时，Host 会按上限明确收口，不会无限创建 Attempt / compact / dispatch。

### 目标

- 建立 reactive overflow 从 RunInputBuilder、compaction、retry 到 terminal / diagnostic 的端到端测试。
- 确认循环上限和失败收敛路径。
- 验证 deterministic recent-window fallback 未能放下输入或 policy 不允许继续时，仍由 reactive 上限兜底收口。

### 非目标

- 不提高默认 compact 次数来掩盖 sizing 错误。
- 不把 overflow 处理放进 Engine。
- 不重复测试 ingest 层已经覆盖的单点计数逻辑；本条只补 dispatch-loop 组合路径。

### 验收信号

- 连续 overflow 不会无限循环。
- terminal / diagnostic 能说明 compact 次数、最后一次失败原因和是否已 fail closed。
- E2E 能观察到 Attempt 数、`CONTEXT_COMPACTION_REQUESTED` / `CONTEXT_COMPACTED` / `CONTEXT_COMPACTION_FAILED` 事件数和最终 Run terminal 状态均符合上限策略。

## WU-TOOL-01 Duplicate Governance Concurrency and Cross-attempt Semantics

### 背景

当前 duplicate governance 按 run-scope 记忆 duplicate。后续需要改为 attempt-scope，只治理同一次 LLM 调用 / 同一 Attempt 内的重复工具执行风险。跨 Attempt 的同 tool + 同 args 调用默认视为新的工具请求，不由 duplicate governance 复用或阻断。

### 目标

- 将 duplicate governance key / index 从 run-local 改为 attempt-scoped，scope 必须包含 `attempt_id`。
- 验证同一 Attempt 内同工具同 args 并发调用只执行一次、复用已有 accepted result、提示或按 policy 明确拒绝。
- 明确 cross-Attempt ToolRuntime state 不继承 duplicate index；resume、steer、recovery 或 compact recovery 创建的新 Attempt 中，重复工具调用按新的工具请求处理。
- 清理或改写当前 run-local duplicate index 代码路径，避免 worker-local cache 成为跨 Attempt correctness 前提。
- 修改 production diagnostic / trace，使 `TOOL_CALL_GOVERNED` 或等价 diagnostic 能表达 duplicate scope 是当前 Attempt，并记录当前 Attempt 内 prior event refs。

### 非目标

- 不改变 accepted evidence 的事实语义。
- 不让 worker-local cache 成为 durable correctness 依赖。
- 不引入 tool result freshness、汇率 / 行情当前性、side-effect 幂等或跨 Attempt retrieval 复用策略。
- 不从 EventLog 重建 durable duplicate ledger。

### 验收信号

- 同一 Attempt 内并发 duplicate 有明确测试，且不会无解释重复执行。
- 跨 Attempt duplicate 有明确测试，证明不会命中旧 Attempt 的 duplicate index；新的 Attempt 按新工具请求执行或由工具自身 policy 处理。
- worker restart / Host restart 后不要求继承 duplicate index，测试或文档明确该行为不是 correctness 前提。
- diagnostic 能区分 attempt-scoped dedup 命中、重复拒绝、执行失败和 durable 缺失。
- 现有依赖 run-scope duplicate 命中的测试被删除或改写；不得通过兼容分支同时保留 run-scope 与 attempt-scope 两套行为。

## WU-TOOL-02 Accept Candidate Structure Cleanup

### 背景

当前 `ToolFactAcceptCandidate` / accept candidate 同时承载 Attempt identity、tool call identity、schema / args digest、outcome / payload、truncation、duplicate governance、policy decision、diagnostic refs、accept idempotency、semantic digest 与 raw tool outcome，字段职责已经过宽。

### 目标

- 收敛 accept candidate 的 typed structure、命名、producer 和 consumer。
- 将大 candidate 拆成组合结构，例如 identity、call、result、governance、accept idempotency、diagnostics 等分组；具体命名以实现时局部代码边界为准，不预设 public API。
- 让普通 result、reuse、governed error 等不同 fact kind 的构造路径只填充各自需要的子结构。
- 删除无生产者或无消费者的字段。
- 更新 `TOOL_RESULT_ACCEPTED` payload 构造、accept barrier validation、tool trace / memory / compaction 消费路径，使其通过新的 typed 子结构读取字段。
- 在 duplicate governance 改为 attempt-scoped 后，再整理 duplicate / reuse 相关子结构，避免围绕旧 run-scope 语义返工。

### 非目标

- 不改变 evidence-backed fact 的生成门槛。
- 不引入兼容 wrapper 或旧字段 re-export。
- 不把内部 accept candidate 变成 Host public API。
- 不借结构清理改变 duplicate、freshness、side-effect、wait 或 accepted evidence 语义。

### 验收信号

- ToolRuntime、compaction extraction、memory projection 和测试使用同一 candidate 类型。
- 类型检查不依赖 `object` / `Any` / magic payload。
- 测试 helper 不再到处手写超宽 `ToolFactAcceptCandidate` 构造参数。
- 拆分后无 god dataclass / god builder 回流，普通 result、reuse、governed error 的校验逻辑各自清晰。

## WU-ENGINE-01 Provider State Neutralization and Runner Abstraction

### 背景

现有 typed provider class / sealed union 已经是避免 raw JSON provider payload 泄漏的正确方向；本条不再围绕 provider state 做大改。剩余可疑点主要是 runner error / diagnostic 中的 `raw_payload` 是否过宽，以及 stream / non-stream error object 是否一致。

### 目标

- 不推倒现有 typed provider state；后续新增 provider state 继续通过 typed class / sealed union 扩展。
- 将本条收窄为 Engine runner diagnostic payload audit：核查 `RunnerProtocolErrorData` / `RunnerHTTPErrorData` / `ProviderProtocolErrorData` 中 raw payload 的边界、脱敏、安全性和大小约束。
- 补或核对 stream / non-stream error object consistency 测试。

### 非目标

- 不把 Host 状态机逻辑下沉到 Engine。
- 不为单个 provider 保留兼容 facade。
- 不把 typed provider class 退回 raw JSON / metadata bag。
- 不重写已稳定的 provider extension config / reasoning / tool call state 投影。

### 验收信号

- OpenAI / Gemini 等 provider state 继续通过统一 typed contract 暴露，且无 raw SDK object 泄漏。
- stream / non-stream error object consistency 有测试。
- diagnostic raw payload 若保留，必须有明确边界；若删除或摘要化，Host / Engine 测试同步收敛。

## WU-LAYER-01 Durable Row Primitive / Type Owner Cleanup

### 背景

Host durable 是状态机治理数据库，不是普通 CRUD。显式 SQL / 轻量 Data Mapper 是当前保守方向；CAS、短事务、DDL CHECK、partial index、EventLog append 与状态迁移需要 SQL 语义可见、事务边界可控。问题不在于“不用 ORM”，而在于 row codec、validation owner 与 schema invariant 还需要收敛。

### 目标

- 保留显式 SQL、显式 transaction 和 typed durable row dataclass。
- 收敛 durable row primitive 与 public type owner。
- 清理 durable bootstrap、schema CHECK、terminal CAS null-check 的重复规则。
- 让 row decode / encode / validation 有统一 owner，避免 Python dataclass 校验、SQLite CHECK 与 CAS null-check 三套规则漂移。

### 非目标

- 不引入 ORM，不让 ORM 自动生成 schema、隐式迁移或隐藏 CAS 条件。
- 不改变 public contract。
- 不创建仅透传的兼容 re-export。
- 不把 durable row dataclass 扩展成承载业务行为的 domain object。

### 验收信号

- durable 层不向上依赖 Host 业务实现细节。
- row decode / encode 失败有稳定错误类型和测试。
- current-version DB 缺表、缺索引或 schema invariant 缺失时，普通 open path 结构化失败；不得因 `CREATE IF NOT EXISTS` 静默补齐后继续运行。
- terminal Run / Attempt / WaitRecord 的 schema CHECK、Python validation 与 CAS null-check 语义一致。

## WU-LAYER-02 Shared Validation / Redaction / JSON Helper Consolidation

### 背景

Runtime 已承担层中立基础能力，Host / Engine import boundary guard 已存在。validation、JSON、redaction、token estimate helper 仍可能存在跨模块重复实现。只有层中立、无业务语义、跨层确实重复的 helper 才考虑下沉到 `dayu.runtime`；Host durable 专用 canonical format、状态机规则和业务字段校验不得为了复用强行搬迁。

### 目标

- 核对并合并层中立 helper 到合适 runtime 模块，优先处理跨层 redaction / bounded diagnostic helper。
- 删除 Host / Engine / Service 内语义重复但实现分叉的 helper。
- 保持 digest、canonical JSON、timestamp 的 truth owner 清晰：runtime digest 与 Host durable codec 各自边界明确，不互相偷换。

### 非目标

- 不把业务层专用规则搬到 runtime。
- 不为了复用制造过宽抽象。
- 不机械迁移 Host durable canonical JSON / digest / timestamp helper。
- 不改变既有 digest 文本、JSON canonicalization、audit / tool trace / EventLog 语义。

### 验收信号

- 合并后的 helper 有直接测试。
- runtime 不 import Host / Engine / Service / UI / Fins。
- 被保留在业务层的 helper 必须有明确 owner 理由，不把“看起来重复”当作重构理由。

## WU-RUNTIME-01 Runtime File Lock Wrapper Contraction

### 背景

`RuntimeFileLock` 的生产用途是 audit / tool trace JSONL 写入互斥。当前 wrapper 同时维护 `_active_token` 与 `RuntimeFileLockToken.released`，复制了第三方 `FileLock` 的生命周期状态，并在多轮 review 中持续暴露 release 边界 bug。

### 目标

- 核对生产调用面是否只需要 `file_lock(...)`、parent directory 准备、timeout 校验和统一 runtime 异常。
- 收缩 `dayu.runtime.filelock`，让第三方 `FileLock` 继续持有实际 acquire / release 生命周期真源。
- 删除或隐藏无生产调用方依赖的 token released 状态；若保留 token，必须证明它不是第二套 lifecycle truth。

### 非目标

- 不让 Host / Service / Engine 直接 import 第三方 `filelock`。
- 不引入 stale takeover、break lock、async wrapper 或 durable lease 语义。
- 不为旧 token 状态提供兼容 wrapper。

### 验收信号

- release 失败不会被标记成成功 released。
- audit / tool trace 文件互斥路径测试通过。
- runtime import boundary 仍证明第三方 `filelock` 只由 runtime filelock 边界持有。

## WU-RUNTIME-02 Runtime Lane Clock and Cancellation Simplification

### 背景

`lane` 的作用是多进程并发 named semaphore，核心抽象成立，不能用 `FileLock` 替代。当前风险集中在实现细节：跨进程 TTL 判断使用每个进程的 `_LaneClock` monotonic anchor 推导 UTC，可能与真实 UTC / 其它进程时钟漂移；outer cancellation 后等待 shielded task 的 helper 也存在无限等待复杂度。

### 目标

- 保留 SQLite-backed 多进程 named semaphore / capacity claim 抽象。
- 将 stale cleanup、claim expiry、heartbeat refresh 等跨进程可见 TTL 判断统一到明确时间真源；优先评估真实 UTC 或 SQLite 时间真源。
- 简化 `_await_task_after_outer_cancellation`，让极端取消路径有明确上限、失败语义或证明其必须无限等待。

### 非目标

- 不把 lane 退化成单进程 semaphore。
- 不用 `FileLock` 替代 capacity > 1 的 named semaphore。
- 不让 lane 表达 Host durable truth、Attempt owner、EventLog ordering、lease / fencing 或 recovery proof。

### 验收信号

- 多进程 capacity invariant、non-blocking timeout、release 后 acquire、crashed holder TTL cleanup 测试继续通过。
- 新增或更新测试覆盖跨进程 TTL 时间真源选择。
- 取消路径不会在底层 thread / SQLite 极端阻塞时无限消耗事件循环而无诊断。
