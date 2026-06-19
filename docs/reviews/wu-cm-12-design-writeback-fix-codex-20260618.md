# WU-CM-12 Design Writeback Fix

## Scope

- 任务类型：pre-plan design truth repair fix
- 输入 review：
  - `docs/reviews/wu-cm-12-design-writeback-review-ds-20260618.md`
  - `docs/reviews/wu-cm-12-design-writeback-review-mimo-20260618.md`
  - `docs/reviews/wu-cm-12-design-writeback-codex-20260618.md`
- 修改文件：
  - `docs/host/design.md`
  - `docs/reviews/wu-cm-12-design-writeback-fix-codex-20260618.md`

本次只修复 AgentDS review 中已 accepted 的 3 个非阻塞设计 finding。未进入 plan gate、implementation gate 或 review gate；未修改生产代码、测试、配置、README 或控制文档；未新增 Host / Engine public API、durable schema、EventLog canonical semantics 或跨层 contract。

## Accepted Findings

### DS F1

结论：accepted。

原因：section-aware degrade 的 section 内 item 保留 / 丢弃顺序如果只写“确定性”，后续实现仍可能临时判断重要 / 不重要，导致 ordinary / compact / fallback 路径行为漂移。

修复：在 `docs/host/design.md:3263` 明确 section 内 item 的保留 / 丢弃顺序必须由设计固定，不得由实施代码临时判断重要 / 不重要；同时只固定设计原则，不在设计真源中过早选定具体排序字段。文档要求后续 code-generation-ready plan 基于该原则选择稳定排序字段和排序方向，并确保路径间复用同一规则。

### DS F2

结论：accepted。

原因：fail closed 条件分散会增加后续计划遗漏 durable corruption、provenance inconsistency、取消或会话关闭等硬停止条件的风险。

修复：在 `docs/host/design.md:3265` 集中写出 fallback fail closed 条件，覆盖：

- current input anchor 本身超过 hard context budget。
- durable EventLog、payload 或 artifact 损坏，无法构造可信 LLM-facing 输入。
- selected material provenance 不一致，继续 dispatch 会污染事实边界。
- cancellation、session closed 或当前 Run state 已不允许继续执行。

### DS F3

结论：accepted。

原因：只写允许动作会把禁止动作留给读者反推，后续实现可能误做截断、重新 summary、临时 compacted view 或 fallback memory projection。

修复：在 `docs/host/design.md:3263` 显式写出 degrade 禁止动作列表：

- 禁止截断 semantic item text。
- 禁止重新 summary 或改写 summary。
- 禁止改写 fact、answer anchor、forward intent 或 reference continuity item。
- 禁止临时生成新的 compacted view。
- 禁止让 fallback 产生新的 Session Semantic Memory。

## Verification

- `git diff --check`：通过，无输出。
- `rg -n "section 内 item 的保留 / 丢弃顺序必须由设计固定|排序字段和排序方向|Fallback fail closed 条件必须集中|current input anchor 本身超过 hard context budget|durable EventLog、payload 或 artifact 损坏|selected material provenance 不一致|cancellation、session closed|degrade 禁止动作列表固定|禁止截断 semantic item text|禁止重新 summary 或改写 summary|禁止改写 fact、answer anchor、forward intent 或 reference continuity item|禁止临时生成新的 compacted view|禁止让 fallback 产生新的 Session Semantic Memory" docs/host/design.md`：通过，命中 `docs/host/design.md:3263` 与 `docs/host/design.md:3265`。

## Residual Risks

- 本次仍只是设计真源补强，未验证现有实现是否符合更新后的 section-aware degrade、fallback fail closed 和 no-silent-truncation 边界。
- 设计文档仍未选定 section 内 item 的具体排序字段和方向；这是有意保留给后续 code-generation-ready plan 的决策，但该 plan 必须遵守本次补强的设计原则。
- 本次未运行测试或 pyright，因为任务明确限定为文档修复，且未修改生产代码、测试、配置或 schema。
