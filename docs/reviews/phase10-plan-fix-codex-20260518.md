# Phase 10 Plan Fix — AgentCodex

- Date: 2026-05-18
- Plan artifact: `docs/host/phase10-context-governance-plan.md`
- Review artifacts:
  - `docs/reviews/phase10-plan-review-mimo-20260518.md`
  - `docs/reviews/phase10-plan-review-ds-20260518.md`
- Gate: Phase 10 implementation-ready handoff plan fix

## 修复摘要

本次只修 plan，不修改生产代码。已按总控裁决修复 MiMo B1/B2/B3 blocking findings，并补齐需要计划澄清的 high / medium / low findings。

核心变更：

- 明确 `RunStatus.ACCEPTED` 的 cancel path：`ACCEPTED` 可被 `cancel_run` 取消，只写 `RUN_CANCELLED` / terminal closeout，不创建 Attempt、dispatch record 或 active worker target。
- 明确 queued promotion 方案：不做 `QUEUED -> ACCEPTED` 持久中间态；同一个 pre-start governance gate 接收 `origin=accepted | queued`，queued path 在同一 governance gate 中按 FIFO 选择最早 queued Run，再通过新的 post-governance start helper 创建 `RUN_STARTED` / `ATTEMPT_STARTED`。
- 明确 pre-start governance wakeup 与现有 dispatch scheduler 的边界：新增独立 governance wakeup / loop，只有 governance 通过后才创建 pending dispatch record 并唤醒现有 dispatch scheduler。
- 明确 `ATTACH_ACTIVE` / `REJECT` 遇到 `ACCEPTED` 的行为：`ACCEPTED` 是 start-blocking 但不可 attach；`REJECT` 和 `ATTACH_ACTIVE` 均 conflict，`QUEUE` / `submit_followup(queue)` 排队。
- 明确 `CONTEXT_COMPACTED` memory projection 的 helper 级解析路径、episode summary 映射和 pinned state patch 三态语义；`CONTEXT_COMPACTION_FAILED` 不进入 memory projection filter。
- 明确 per-Run compact count 从 committed EventLog facts 在同一 write transaction 中查询，查询失败 fail-closed。
- 明确 production wiring 字段入口、conservative estimator 常量示例、fresh schema 起库约定、`RunStartReason.RECOVERY` 必须新增且 `STEER` 不属于 P10、DurableCompactArtifactProvider message 边界。

## Finding 处理表

| Finding | 处理结果 | Plan fix |
|---|---|---|
| MiMo B1 `cancel_run` 不识别 `ACCEPTED` | Fixed | 在 Pre-start Governance Gate 与 Slice 4 tests 中明确 `ACCEPTED` cancel path：追加 `RUN_CANCELLED`，不创建 Attempt / dispatch record。 |
| MiMo B2 queued promotion 绕过 governance | Fixed | 明确选择 queued in-place governance 方案；旧 `promote_queued_run_in_transaction` 不再由 production 直接调用。 |
| MiMo B3 `CONTEXT_COMPACTED` projection 解析不具体 | Fixed | 增加 `_compact_episode_summary_from_projection_event`、`_apply_pinned_state_patch_candidate`、三态 patch 与 verified facts 边界。 |
| MiMo H1 per-Run trigger count 查询未说明 | Fixed | 新增 transaction-scoped EventLog count helper、同事务查询、fail-closed 行为。 |
| MiMo H2 新旧 start helper 关系不清楚 | Fixed | 明确 `start_accepted_run_with_starting_attempt_in_transaction` 复用既有 `RUN_ACCEPTED`，旧 combined helper 不再走 production start path。 |
| MiMo M1 estimator 常量未指定 | Fixed | 补充 `DEFAULT_CONTEXT_SAFETY_MARGIN_RATIO`、`DEFAULT_ESTIMATOR_CHARS_PER_TOKEN` 等常量示例和放置模块。 |
| MiMo M2 production wiring 不细 | Fixed | 明确 `HostCommandHandleOptions` / `HostLocalExecutionOptions` 字段和 Service composition root 传参路径。 |
| MiMo M3 `CONTEXT_COMPACTED` 状态表述 | Fixed | 改为 event payload 不编码状态变更；状态由同事务序列中的 Run / Attempt facts 表达。 |
| MiMo M4 schema CHECK 兼容性 | Fixed | 明确按 fresh schema 起库，不做旧库兼容 / migration tests。 |
| MiMo L1 fake compactor import boundary | Fixed | 明确 fake compactor 只可显式注入测试 / local dev，不能被默认 production path 隐式导入。 |
| MiMo L2 usage payload 扩展范围 | Fixed | 明确 P10 不扩展 `USAGE_REPORTED` EventLog payload。 |
| MiMo L3 tests README 更新类别 | Fixed | 明确 `tests/README.md` 增加 `test_context_budget`、`test_compaction_contract`、`test_compact_artifact_store`、`test_context_compact_events`。 |
| MiMo L4 fake compactor placement | Fixed | 同 L1，补 production 包内 docstring 与显式注入约束。 |
| DS H1 pre-start wakeup 未指定 | Fixed | 明确新增 dedicated pre-start governance wakeup / loop，并与 pending dispatch record scheduler 分离。 |
| DS H2 `ACCEPTED` 与 `ATTACH_ACTIVE` | Fixed | 明确 `ACCEPTED` start-blocking 但不可 attach；`ATTACH_ACTIVE` conflict。 |
| DS H3 queued promotion 状态机 | Fixed | 明确选择 queued in-place governance，不做 `QUEUED -> ACCEPTED` 中间态。 |
| DS M1 `RunStartReason.RECOVERY` | Fixed | 改为必须新增 `RECOVERY`，不再用条件语气。 |
| DS M2 `RunStartReason.STEER` | Fixed | 明确 `STEER` 不属于 P10。 |
| DS M3 schema CHECK migration awareness | Fixed | 明确 fresh schema 起库约定。 |
| DS M4 `EPISODE_SUMMARY_ACCEPTED` removal scope | Fixed | 明确移出 memory compact truth path，并要求先确认无非测试消费者。 |
| DS M5 DurableCompactArtifactProvider message semantics | Fixed | 补充 system message 内容、边界、是否可为空和 artifact refs explainability。 |
| DS L1 estimator coefficient constants | Fixed | 同 MiMo M1，补常量示例。 |
| DS L3 `CONTEXT_COMPACTION_FAILED` memory projection | Fixed | 明确不进入 production consumer filter。 |
| DS L4 fake compactor placement | Fixed | 同 MiMo L1/L4，补显式注入和 docstring 要求。 |

## 剩余风险

- `RunStatus.ACCEPTED` 仍是 public state-machine/schema 变更，implementation 需要同步 admission、cancel、read-model/public contract tests。
- pre-start governance wakeup 是新增执行环节；P10 只覆盖同进程 wakeup，进程重启后的 orphan/startup scan 仍归 Phase 11。
- queued in-place governance 避免额外 accepted 中间态，但 implementation 必须严格用同一 write transaction 保持 FIFO 和 single-start arbitration。
- conservative estimator 仍可能偏早 compact；provider-specific tokenizer adapter 继续 deferred。

## Re-review 建议

需要 re-review。MiMo blocking findings 已修复，但本次新增了更具体的 pre-start governance wakeup、queued promotion 方案和 compact projection helper 设计，建议进入 Phase 10 plan re-review 后再派 implementation agent。
