# Code Review: WU-CLI-ACTIVITY-01 follow-up Slice 1

## Scope

- Mode: current changes
- Branch: wu-cli-activity-01
- Base: HEAD (working tree changes against last commit)
- Output file: `docs/reviews/wu-cli-activity-01-followup-slice-1-ds-review-20260618-065202.md`
- Included scope:
  - `docs/host/design.md` (staged changes)
  - `docs/host/issues-implementation-control.md` (staged changes)
  - `docs/reviews/wu-cli-activity-01-followup-slice-1-implementation-codex-20260618.md` (untracked, implementation artifact)
- Excluded scope: 所有生产代码、测试、schema、README。本 Slice 为 docs-only。
- Parallel review coverage: 无
- Reference plan: `docs/host/host-issues/wu-cli-activity-01-followup-delta-eventlog-projection-catchup-plan.md`
- Accepted plan commit: `906c1ffa`

## Findings

### DS-S1-01-未修复-低-design.md 中 EngineEvent 映射表 `content_delta` 与 `tool_call_delta` 的 non-durable 标注缺少 `reasoning_delta` 的明确对等覆盖——实际已覆盖，无缺陷

- **入口/函数**: `docs/host/design.md` 第 13.4 节 EngineEvent 映射表
- **文件(行号)**: `docs/host/design.md:1601-1604`
- **输入场景**: 审阅者逐行比对 plan 要求的三类 delta（`content_delta`、`reasoning_delta`、`tool_call_delta`）是否均在映射表中标注为 non-durable
- **实际分支**: N/A——检查通过
- **预期行为**: 三类 delta 应全部标注为 `accepted non-durable delta; no EventLog row by default`
- **实际行为**: 三类 delta 全部正确标注。`reasoning_delta` 在行 1602，`content_delta` 在行 1601，`tool_call_delta` 在行 1604
- **直接证据**: `docs/host/design.md:1601-1604`；`rg -n "accepted non-durable delta" docs/host/design.md` 返回三条命中，分别对应三类 delta
- **影响**: 无。此为验证确认项，非缺陷。
- **建议改法和验证点**: 无需修改。
- **修复风险（低）**: 无。
- **严重程度（低）**: 无缺陷。记录为确认项。

### DS-S1-02-未修复-低-控制文档 `当前状态` 表 gate 从 `ready-to-open-draft-PR` 变更为 `implementation` 的转换路径可追溯性偏弱

- **入口/函数**: `docs/host/issues-implementation-control.md` 当前状态表
- **文件(行号)**: `docs/host/issues-implementation-control.md:143-152`
- **输入场景**: 审阅者追溯控制文档状态变更历史，验证 gate 从 `ready-to-open-draft-PR`（WU-CLI-INTERACTIVE-RESUME-01 final closeout）切换到 `implementation`（WU-CLI-ACTIVITY-01 follow-up）的完整链路
- **实际分支**: 状态表显示了新状态，WU-CLI-INTERACTIVE-RESUME-01 的详细状态节（行 321+）仍保留 `ready-to-open-draft-PR`，WU-CLI-ACTIVITY-01 表行状态从 `ready-to-open-draft-PR` 变更为 `implementation`，并在 `当前定位` 列中说明"Original activity stream work completed locally and remains ready for draft PR"
- **预期行为**: 控制文档应准确记录当前 gate，且不破坏此前已完成 WU 的状态记录
- **实际行为**: 当前 gate 记录正确。此前 WU 的状态均完整保留：WU-CLI-INTERACTIVE-RESUME-01 仍为 `ready-to-open-draft-PR`（行 216），WU-CLI-SESSION-01 仍为 `completed`（行 215），WU-CLI-FINS-OBS-01 仍为 `completed`（行 212），WU-CLI-FINS-DIAG-01 仍为 `completed`（行 213）。但 WU-CLI-ACTIVITY-01 自身的表行状态从 `ready-to-open-draft-PR` 变更为 `implementation`，而原始 activity stream 工作本身已具备 draft-PR-ready 条件。这一变更的语义是"同一 WU 下启动了 follow-up implementation 阶段"，但状态列的单值模型不区分"原始工作已 ready-for-draft-PR"与"follow-up 仍在 implementation"。
- **直接证据**:
  - 变更前行 146: `| gate | ready-to-open-draft-PR |`
  - 变更后行 146: `| gate | implementation |`
  - 变更前行 215: `| WU-CLI-ACTIVITY-01 | ready-to-open-draft-PR | ...`
  - 变更后行 215: `| WU-CLI-ACTIVITY-01 | implementation | ... Original activity stream work completed locally and remains ready for draft PR`
  - 行 216: WU-CLI-INTERACTIVE-RESUME-01 的 `ready-to-open-draft-PR` 未变
  - 行 310-319: 新增的 follow-up 子节正确记录了 Slice 1 范围与状态
- **影响**: 低。`当前定位` 列中的详细说明已充分传达"原始工作已完成、follow-up 正在实施"的语义。表状态列的 `implementation` 反映了该 WU 当前整体的真实状态。不构成信息丢失或状态腐败。
- **建议改法和验证点**: 可选：在 follow-up 子节（行 310-319）显式标注"原始 activity stream 工作的 draft-PR-ready 状态由 follow-up 完成后统一推进"，以避免将表状态 `implementation` 误读为原始工作回退。当前文档已通过 `当前定位` 列文本充分缓解此歧义，非必须修改。
- **修复风险（低）**: 无需修复。
- **严重程度（低）**: 文档可读性微调，非缺陷。

## Open Questions

无。

## Residual Risk

- `RR-S1-01`（实现报告已记录）: Production code 仍未实现 per-delta non-durable ingest。分类正确：covered by Slice 2。
- `RR-S1-02`（实现报告已记录）: Filter-aware EventLog read 与 ProjectionRunner catch-up 语义仍未实现。分类正确：covered by Slice 3。
- `RR-S1-03`（实现报告已记录）: Memory repair budget removal、after-commit / after-compact maintenance 调整和 inline repair shared filter 仍未实现。分类正确：covered by 后续 approved slices。
- `RR-S1-04`（实现报告已记录）: 本 slice 未运行代码测试或 pyright。分类正确：covered by 后续实现代码的 slices。本 slice 仅验证文档 diff 与 grep。
- 以上四项均已有明确后续 Slice owner，符合 deferred-with-owner 分类标准。

## Review Conclusion

**PASS** — 无阻塞性缺陷。

### 逐项核验结果

| 审阅关注点 | 结论 | 证据 |
|---|---|---|
| non-durable per-delta 默认 | 正确更新 | `design.md:339` 明确三类 delta 不写入主 EventLog；`design.md:1593` 明确 per-delta 默认不 durable；`design.md:1601-1604` 映射表正确标注 |
| durable replay non-goal | 正确更新 | `design.md:339` 明确"durable replay、Host event stream 补读、memory、audit 与 RunResult 不能承诺 token-level delta replay" |
| memory catch-up page-size 语义 | 正确更新 | `design.md:99,117` 将 `batch_size` 重述为"内部读取页大小和单批 transaction 粒度"；`design.md:3215` 明确不得作为 correctness 停止条件 |
| hot-path no-unbounded-sync-catch-up | 正确更新并强化 | `design.md:3217` 新增独立段落，明确 after-commit / after-compact 只能做 latency-only maintenance 或不执行，且 latency-only maintenance 页数上限不得被解释为 memory 已追平 |
| 控制文档当前 gate 记录 | 正确 | gate 切换到 `implementation`，active work unit 切换为 `WU-CLI-ACTIVITY-01 follow-up`，next entry point 切换为 Slice 1 review gate |
| 此前 WU 状态未腐败 | 确认未腐败 | WU-CLI-INTERACTIVE-RESUME-01 仍为 `ready-to-open-draft-PR`（行 216）；WU-CLI-SESSION-01、WU-CLI-FINS-OBS-01、WU-CLI-FINS-DIAG-01 仍为 `completed`；Residual Risk 追踪表条目完整保留 |
| docs-only scope 被遵守 | 确认遵守 | `git diff --stat` 仅两文件变更；无生产代码、测试、schema、README 修改；`docs/engine/design.md` 未修改且有合理理由说明 |
| validation 正确 | 确认 | `git diff --check` clean；grep 确认旧 `catch-up 执行预算` / `budget_exhausted` 措辞不存在；grep 确认新 non-durable delta / page-size 措辞存在 |
| residual risk 分类正确 | 确认 | 四项 RR 均分类为 "covered by later approved slice"，owner 明确（Slice 2/3/后续 slices），不阻塞 Slice 1 review gate |
