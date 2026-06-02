# WU-TOOL-02 Aggregate Deepreview Handoff

## Assignment

你是独立 aggregate deepreview agent。当前 gate: WU-TOOL-02 aggregate deepreview。请对当前分支相对 `main` 的 `WU-TOOL-02 Accept Candidate Structure Cleanup` 改动做严格 code review。

## Scope

- 当前分支：`refactor/wu-tool-02-accept-candidate-cleanup`
- Review base：`main`
- Work unit：`WU-TOOL-02 Accept Candidate Structure Cleanup`
- 设计真源：`docs/host/design.md`
- 总控真源：`docs/host/host-core-followup-implementation-control.md`
- Approved plan：`docs/host/wu-tool-02-accept-candidate-cleanup-plan.md`

重点审查本 work unit 的完整 diff，而不是单个 slice：

- `ToolFactAcceptCandidate` 是否已收敛为内部 typed composition root，且没有旧字段 facade / wrapper / re-export。
- producer、accept barrier consumer、event payload、accepted evidence envelope、ack、logging、tests 是否一致读取新子结构。
- EventLog event type、payload key、event id 派生、accepted evidence envelope、idempotency scope、duplicate governance、reuse、wait、retry、replay、resume、memory、compaction、tool trace 语义是否保持不变。
- 是否违反 AGENTS.md：类型签名、中文 docstring、分层边界、runtime 边界、README 触发规则、禁止兼容 wrapper、禁止 extra payload、禁止 god dataclass / god builder。
- 测试是否覆盖普通 result、failed/cancelled、plain governed error、duplicate governed error、reuse、diagnostics、truncation、payload consumers。
- Slice 5 controller verification 已通过：affected Host tests 206 passed，全量 pyright 0 errors；请仍独立审查测试覆盖是否足以证明关键行为。

## Review Method

按 deepreview 方法执行：

- 从 change intent、approved plan 和总控状态建立 review map。
- 对关键真实路径做直接代码走读：producer -> candidate validation -> accept barrier -> EventLog request/payload -> ack -> projection consumers。
- 执行 adversarial failure pass，重点查 correctness、stability、maintainability、overcoupling、state machine、idempotency、durable truth、EventLog payload 和 testing gaps。
- findings 必须有直接证据，包含文件/行号、同一逻辑/数据路径上的 root cause、风险影响和具体修复建议。

## Required Output

写入你自己的 review artifact：

- AgentMiMo：`docs/reviews/wu-tool-02-aggregate-deepreview-mimo-20260602.md`
- AgentDS：`docs/reviews/wu-tool-02-aggregate-deepreview-ds-20260602.md`

Artifact 必须包含：

- scope 与 reviewed inputs
- findings，按 severity 排序；没有 blocking finding 时明确写 `No blocking findings`
- adversarial failure pass
- AGENTS.md / architecture boundary check
- overcoupling / structural clarity check
- tests and validation coverage judgment
- residual risks / uncovered areas
- final verdict：`pass`、`pass-with-nonblocking-notes` 或 `fail`

## Constraints

- 严格遵守 AGENTS.md，中文输出。
- 不修改 source、tests、README、plan、总控文档或其它 agent artifact。
- 只允许写自己的 review artifact。
- 不 commit、push、PR。
