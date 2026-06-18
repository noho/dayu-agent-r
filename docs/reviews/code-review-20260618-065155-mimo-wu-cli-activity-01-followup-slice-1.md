# Code Review

## Scope

- Mode: current changes
- Branch: `wu-cli-activity-01`
- Base: `main`
- Output file: `docs/reviews/code-review-20260618-065155-mimo-wu-cli-activity-01-followup-slice-1.md`
- Included scope:
  - `docs/host/design.md` (unstaged working tree changes)
  - `docs/host/issues-implementation-control.md` (unstaged working tree changes)
  - `docs/reviews/wu-cli-activity-01-followup-slice-1-implementation-codex-20260618.md` (untracked implementation artifact)
- Excluded scope: production code, tests, schema, README (docs-only Slice 1)
- Parallel review coverage: 无

## Review Focus

按 accepted plan `docs/host/host-issues/wu-cli-activity-01-followup-delta-eventlog-projection-catchup-plan.md` Slice 1 scope：

1. 设计真源是否正确更新 non-durable per-delta 默认、durable replay non-goal、memory catch-up page-size 语义、hot-path no-unbounded-sync-catch-up 约束。
2. 控制文档是否准确记录当前 gate，不损坏已有 WU 状态。
3. 是否遵守 docs-only scope。
4. validation 和 residual risks 是否正确分类。

## Findings

未发现实质性问题。

以下为验证性观察，不构成 defect：

### 观察-WU-CLI-ACTIVITY-01 状态从 `ready-to-open-draft-PR` 回退到 `implementation`

- **入口/函数**: `docs/host/issues-implementation-control.md` 当前状态表和 WU 表
- **文件(行号)**: 行 146-148 (`gate` / `implementation status` / `active work unit`)，行 215 (WU 表 `WU-CLI-ACTIVITY-01` 行)
- **输入场景**: follow-up plan 被接受后，control doc 将 WU-CLI-ACTIVITY-01 的状态从 `ready-to-open-draft-PR` 改回 `implementation`
- **实际分支**: 当前 control doc 写 `gate: implementation`，`WU-CLI-ACTIVITY-01` 状态为 `implementation`
- **预期行为**: 原始 activity stream 工作已完成并处于 `ready-to-open-draft-PR` 状态；follow-up 是同一 WU 下的新增 scope
- **实际行为**: 状态回退到 `implementation`，但 `implementation status` 描述中保留了"Original activity stream work completed locally and remains ready for draft PR"的记录
- **直接证据**: 行 215 当前文本明确区分原始完成状态和 follow-up 进行中状态
- **影响**: 不影响 correctness；但若后续 merge PR 时只看 WU 状态列，可能误以为原始 activity stream 工作尚未完成。`implementation status` 列的详细描述已包含足够消歧信息。
- **建议改法和验证点**: 无需修改；controller 或未来 PR reviewer 只需同时读 `implementation status` 列即可消歧。若认为需要更清晰，可考虑在 `implementation status` 中将原始完成状态和 follow-up 进行中状态用分号更显式分隔。
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低

## Open Questions

无。

## Residual Risk

- `RR-S1-01` 至 `RR-S1-04` 由 implementation artifact 正确分类为 covered by later approved slices，owner 分别为 Slice 2、Slice 3、后续 approved slices、实现代码的后续 slices。分类正确。
- 本 slice 未运行代码测试或 pyright，因为 docs-only scope 不要求。后续 slices 的 validation 必须覆盖。

## Validation Summary

| 检查项 | 结果 |
|---|---|
| `git diff --check` | clean (exit 0) |
| 旧 budget wording grep (`catch-up 执行预算\|budget_exhausted`) | 无匹配 (exit 1) |
| 新 wording grep (`accepted non-durable delta\|page-bounded\|latency-only maintenance` 等) | 全部匹配 |
| docs-only scope | 仅修改 `docs/host/design.md` 和 `docs/host/issues-implementation-control.md`；implementation artifact 为 untracked review 文件 |
| control doc 已有 WU 状态 | WU-CLI-FINS-OBS-01、WU-CLI-FINS-DIAG-01、WU-CLI-SESSION-01、WU-CLI-INTERACTIVE-RESUME-01 等保持原状不变 |
| residual risk 表 | 新增 WU-CLI-INTERACTIVE-RESUME-01-R1/R2 保留原状；无已有 residual risk 被修改或删除 |

## Design Truth Alignment Check

| Plan 要求的设计真源更新 | design.md 对应位置 | 验证结果 |
|---|---|---|
| Host 默认不持久化 per-delta EventLog rows | 行 339 stream 术语约束段落；行 1593 映射原则；行 1601-1604 映射表 | ✅ 三处一致表达 non-durable delta 默认 |
| durable replay 不承诺 token-level delta replay | 行 339 "durable replay、Host event stream 补读、memory、audit 与 RunResult 不能承诺 token-level delta replay" | ✅ |
| memory catch-up page-size 语义 | 行 99 "`memory_projection_catchup_batch_size` 只表示 required catch-up / rebuild 的内部读取页大小和单批 transaction 粒度" | ✅ |
| hot-path no-unbounded-sync-catch-up | 行 3217 "Dispatch hot path 不得做无上限同步补账" + after-commit / after-compact latency-only maintenance 约束 | ✅ |
| 移除旧 "执行预算" 表述 | grep 无匹配 | ✅ 已清除 |

## Conclusion

**PASS**。Slice 1 docs-only 实现正确更新了设计真源和控制文档，符合 accepted plan Slice 1 scope 和 completion signal。无实质性 defect。唯一低严重度观察是 WU 状态回退可能造成轻微阅读歧义，但 implementation status 列已包含充分消歧信息。
