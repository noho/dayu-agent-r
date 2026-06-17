# Codex Plan Review Fix: WU-CLI-ACTIVITY-01 follow-up

## 元数据

- Gate：plan review fix
- Work unit：`WU-CLI-ACTIVITY-01 follow-up`
- 修复者：AgentCodex
- 日期：2026-06-18
- Target plan：`docs/host/host-issues/wu-cli-activity-01-followup-delta-eventlog-projection-catchup-plan.md`
- Review artifacts：
  - `docs/reviews/plan-review-20260618-063322.md`
  - `docs/reviews/plan-review-20260618-063418-ds-wu-cli-activity-01-followup.md`
- Artifact path：`docs/reviews/plan-review-fix-20260618-codex-wu-cli-activity-01-followup.md`

## Scope

本次只修订 plan artifact 和新增本 fix artifact。不实现生产代码、不修改测试代码、不提交、不 push。

## Findings 裁决与状态

| Finding | 裁决 | 修复状态 | 处理 |
|---|---|---|---|
| MiMo F1 / DS-01 | accepted | 已修复 | Plan 区分 required correctness catch-up 与 hot-path opportunity path。required catch-up 删除 LIMIT N 语义预算并运行到 target / idle / failure；after-commit / after-compact 不得执行无界同步补账，只能改为 bounded latency-only maintenance，或直接移除机会性 hook。 |
| DS-02 | accepted | 已修复 | Contract 段改为 Public Host API 签名不变，但 EventLog-backed stream / read 默认不再包含 per-delta rows。 |
| MiMo F2 / DS-03 | accepted | 已修复 | `FilteredEventLogPage` 规格补充空 EventLog、cursor at/beyond latest、`max_event_sequence` 超出 actual latest、`max_event_sequence` 无精确 row 的边界不变量，并要求需要推进时必须使用真实 EventLog row id。 |
| MiMo F3 / DS-04 | accepted | 已修复 | Plan 固定使用模块级 `conversation_memory_projection_event_filter()` 作为单一 filter 真源；修正动机为当前列表语义等价、风险是未来漂移。 |
| DS-05 | accepted | 已修复 | Plan 要求 filtered read 的 matching rows 查询与 covered cursor 查询必须在调用方提供的同一个 transaction 内完成。 |
| DS-06 | accepted | 已修复 | Plan 要求 docstring / README / design wording 明确 `memory_projection_catchup_batch_size` 是内部 page size，不是 semantic budget；本 WU 不重命名字段。 |

Rejected findings：无。

Deferred findings：无。

## 计划改动摘要

- 修正 Goal / Motivation：将 follow-up 描述为三个同源问题，并降低 inline repair filter 问题的严重性表述。
- 修正 Success Signals / Contract：明确 EventLog-backed public stream 行为变化，API signature 不变。
- 修正 Design Alignment / Slice 1：保留 `docs/host/design.md` 的 hot path 约束，不把去预算化解释成允许无界同步补账。
- 修正 Implementation Decision 3 / Slice 3：补全 `FilteredEventLogPage` 边界、真实 row id 约束、同 transaction 约束和对应测试。
- 修正 Implementation Decision 6 / Slice 4：required catch-up 无语义预算；after-commit / after-compact 只能 bounded maintenance 或删除 hook。
- 修正 Implementation Decision 7 / Slice 5：固定 `conversation_memory_projection_event_filter()` helper 单一真源，不再保留 consumer 实例方案。
- 修正 Docs Decision / Risks / No-overdesign：将 DS-01 风险纳入本 WU 解决，补充 batch size 命名 tradeoff 与文档要求。

## Validation

- `git diff --check -- docs/host/host-issues/wu-cli-activity-01-followup-delta-eventlog-projection-catchup-plan.md docs/reviews/plan-review-fix-20260618-codex-wu-cli-activity-01-followup.md`：通过，无输出。
- 由于本轮目标文档当前是未跟踪文件，额外对两个文件分别运行 `git diff --check --no-index /dev/null <file>`；两次均无 whitespace diagnostics。该模式 exit code 为 1 是 Git 对 new-file diff 的正常返回，不表示 whitespace 校验失败。

## Residual Risks

| ID | 分类 | Owner / Destination | 描述 |
|---|---|---|---|
| RR-01 | covered by later approved slice | Slice 4 implementation | Hot-path opportunity path 必须选择 bounded latency-only maintenance 或删除 hook；plan 已规定，不在本 fix gate 实现。 |
| RR-02 | fixed in current slice | Plan artifact | `FilteredEventLogPage` 边界语义已在 plan 中冻结；实现阶段仍需按测试覆盖。 |
| RR-03 | assigned to later work unit | Future config cleanup WU | `memory_projection_catchup_batch_size` 名称保留但语义变为 page size；本 WU 通过文档消歧，是否重命名另立后续 WU。 |

## Completion Status

Plan review accepted findings 已全部反映到 target plan。下一步入口是 plan re-review。
