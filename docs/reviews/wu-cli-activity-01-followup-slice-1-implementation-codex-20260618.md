# WU-CLI-ACTIVITY-01 follow-up Slice 1 implementation

## 元数据

- Gate: implementation
- Work unit: `WU-CLI-ACTIVITY-01 follow-up`
- Slice: Slice 1 design truth and control doc only
- Agent: AgentCodex
- Date: 2026-06-18
- Accepted plan commit: `906c1ffa`
- Plan artifact: `docs/host/host-issues/wu-cli-activity-01-followup-delta-eventlog-projection-catchup-plan.md`
- Implementation artifact: `docs/reviews/wu-cli-activity-01-followup-slice-1-implementation-codex-20260618.md`

## Scope

本 slice 只更新设计真源与总控文档，不修改生产代码、测试、schema 或 README。

Allowed files honored:

- `docs/host/design.md`
- `docs/host/issues-implementation-control.md`
- `docs/reviews/wu-cli-activity-01-followup-slice-1-implementation-codex-20260618.md`

`docs/engine/design.md` 未修改，因为现有 Engine 设计已经说明三类 delta 是否进入 Host preview、canonical EventLog、memory 或 audit 由 Host ingest 与治理策略决定，并且 EngineEvent 不提供 Host cursor、持久化或 replay 语义。

## First-principles judgment

动机成立。Host 的 durable truth 应保存可恢复、可审计、可重建的 facts，而不是默认保存每个 token / tool-call chunk 的展示增量。将 `content_delta`、`reasoning_delta`、`tool_call_delta` 写成默认 EventLog preview row 会让 Host event stream 补读和 durable replay 暗示 token-level 保真，也会让 projection catch-up 被大量不相关 rows 拖慢。

Memory projection catch-up 的 correctness 目标应是 consumer checkpoint 追到 required cursor、当前 idle 或 failure。`memory_projection_catchup_batch_size` 只能控制内部读取页大小和 transaction 粒度；把它写成“执行预算”会把分页参数误提升为语义停止条件。

## Changes

- `docs/host/design.md`
  - 在 stream 术语约束中明确 Host 默认不把 `content_delta`、`reasoning_delta`、`tool_call_delta` 写入主 EventLog。
  - 明确 durable replay、Host event stream 补读、memory、audit 与 RunResult 不承诺 token-level delta replay。
  - 更新 EngineEvent 映射表：三类 delta 是 accepted non-durable delta，默认不产生 EventLog row；非 delta UI / progress 事件仍可映射为 preview。
  - 将 `memory_projection_catchup_batch_size` 表述为 required catch-up / rebuild 的内部 page size，不是语义预算。
  - 将 ordinary dispatch 前 memory catch-up 语义改为追到 required cursor、idle 或 projection failure。
  - 保留并强化 hot path 约束：after-commit / after-compact 不得为 correctness 执行无界同步补账；只能不做机会性 projection，或做显式页数上限的 latency-only maintenance。

- `docs/host/issues-implementation-control.md`
  - 将当前状态切到 `WU-CLI-ACTIVITY-01 follow-up` implementation。
  - 记录 accepted follow-up plan commit `906c1ffa`。
  - 记录 Slice 1 docs-only scope、allowed files、implementation artifact 和下一入口。

## Validation

已运行：

- `git diff --check`: passed with no output.
- `rg -n "catch-up 执行预算|budget_exhausted|content_delta|tool_call_delta" docs/host/design.md docs/engine/design.md docs/host/issues-implementation-control.md`: passed. The remaining delta hits are expected Engine delta definitions, Host non-durable delta policy, and control-doc slice scope; no old catch-up budget wording appeared.
- `rg -n "catch-up 执行预算|budget_exhausted" docs/host/design.md docs/engine/design.md docs/host/issues-implementation-control.md`: expected no matches; command exited 1 with no output.
- `rg -n "accepted non-durable delta|memory_projection_catchup_batch_size|token-level delta|after-compact hook" docs/host/design.md docs/host/issues-implementation-control.md`: passed and confirmed the new Host design / control-doc wording.

本 slice 是 docs-only；按 accepted plan 不运行生产测试或 pyright。

## Docs decision

已更新 Host 设计真源与 Host issue implementation control doc。未更新 README，因为本 slice 不改变用户可见安装、CLI / Web / WeChat 入口、命令参数、日志位置、工作区文件位置、最终用户工作流或排障方式。

## Residual risks and uncovered areas

- `RR-S1-01`: Production code 仍未实现 per-delta non-durable ingest。分类：covered by later approved slice。Owner：Slice 2。
- `RR-S1-02`: Filter-aware EventLog read 与 ProjectionRunner catch-up 语义仍未实现。分类：covered by later approved slice。Owner：Slice 3。
- `RR-S1-03`: Memory repair budget removal、after-commit / after-compact maintenance 调整和 inline repair shared filter 仍未实现。分类：covered by later approved slice。Owner：后续 approved slices in the accepted plan。
- `RR-S1-04`: 本 slice 未运行代码测试或 pyright。分类：covered by later approved slice。Owner：实现代码的后续 slices；本 slice 只验证文档 diff 和 grep。

## Completion status

Implementation edits and validation completed.

Stop condition hit: no.
