# WU-CM-01-F04 Plan Review — MiMo

## Verdict

**pass-with-findings**

## Summary

Plan 从第一性原理正确识别了根因：proactive scheduler tests 使用 legacy `FakeContextCompactor`（只实现 `compact()` 协议），不走 `CompactorProposalPreparedCompactor` 路径，因此 `run_compaction_operation` 无法产出 proposal manifest ref / digest，导致 `dispatch.py` 的 fail-closed guard 抛出 `RuntimeError`。Plan 的 scope 正确限定在 test seam closeout，不修改生产 guard、schema、public interface 或 Engine contract。四层 slice 切分逻辑清晰，implementation agent 可据此生成代码。

## Findings

### F1 — `_StaleMutatingCompactor` 迁移判断需修正（non-blocking / clarity）

- **severity**: low
- **evidence**: Plan Slice 1 Implementation Decisions 第 8 条："`_TransactionReadableCompactor` 和 `_StaleMutatingCompactor` 若当前 selected tests 会触发 accepted compact，也应迁移到 prepared helper 路径"。
- **实际**: `test_compaction_stale_result_does_not_write_compacted_event` 使用 `_StaleMutatingCompactor`，该 compactor 在 compact 返回前先把 Run 标记为 FAILED，导致 stale check 失败，**不写 `CONTEXT_COMPACTED`**（断言 `_event_count(..., CONTEXT_COMPACTED) == 0`）。因此该 test 不触发 accepted compact guard，不需要迁移到 prepared helper。
- **为什么影响当前 phase**: Implementation agent 可能误判该 test 需要迁移，浪费时间或引入不必要的改动。
- **建议裁决**: accepted（clarify）。Plan 应在 Slice 1 或 Slice 4 中明确说明 `_StaleMutatingCompactor` 不需要迁移，因为其 test 不走 accepted compact 路径。

### F2 — `_RaisingCompactor` 迁移改变了 failure 时序语义（non-blocking / design clarity）

- **severity**: low
- **evidence**: `_RaisingCompactor`（`test_dispatch_scheduler.py:479`-`495`）在 legacy `compact()` 中直接 raise，导致 `_prepare_compactor_proposal` 的 `proposal_manifest_reference=None`。Plan Slice 3 建议改为 prepared helper 的 `fail_run=True`，此时 failure 发生在 manifest record 之后。
- **实际**: 这是**有意的语义变更**：从"proposal 未发起即失败（无 manifest）"变为"proposal 已发起、manifest 已记录、执行阶段失败（有 manifest）"。当前 `_RaisingCompactor` 的 test `test_compaction_repair_attempt_rejection_is_recorded_in_eventlog` 不断言 manifest ref/digit，只断言 `operation_id`、`attempt_count`、`fallback_action`。迁移后 test 会新增 manifest 断言。
- **为什么影响当前 phase**: 不影响正确性，但 implementation agent 应理解这是有意的 test 语义升级，不是无意行为变更。
- **建议裁决**: accepted（acknowledged）。Plan 已在 Slice 3 Invariants 中声明"不把 proposal failure 伪装成 quality rejection"，但应补充说明 failure 时序从 pre-manifest 变为 post-manifest 是有意升级。

### F3 — `_QualityRejectOnceCompactor` 第一次 quality rejection 的 manifest 覆盖范围（non-blocking / coverage）

- **severity**: low
- **evidence**: Plan Slice 3 声明"对 `_QualityRejectOnceCompactor` 的第一次 quality rejection，补充 rejected payload manifest assertions"。
- **实际**: 当前 `_QualityRejectOnceCompactor` 使用 legacy `compact()` 路径，第一次 quality rejection 的 `proposal_manifest_reference=None`（`compaction_operation.py:478` 初始化为 `None`，`compact()` 路径不更新该值）。迁移为 prepared helper 后，第一次 quality rejection 会有 manifest ref。Plan 正确识别了这一点，但应明确说明当前 test 没有对 rejected payload 做 manifest 断言，迁移后是新增覆盖。
- **为什么影响当前 phase**: 不影响实现，但有助于 implementation agent 区分"修复已有断言"和"新增断言覆盖"。
- **建议裁决**: accepted（clarify）。

### F4 — Slice 4 broad scan 范围确认（non-blocking / completeness）

- **severity**: low
- **evidence**: Plan Slice 4 声明扫描所有 `context_compactor=FakeContextCompactor()` proactive compaction usages。当前 `-k` 命令选中的 8 个 test 中，`test_compaction_stale_result_does_not_write_compacted_event` 使用 `_StaleMutatingCompactor`（非 `FakeContextCompactor`），`test_wake_queue_promotion_logs_promotion_task_exception` 不涉及 compactor。因此实际需要迁移的是 Slice 2/3 已列出的 7 个 test。
- **为什么影响当前 phase**: Slice 4 的 broad scan 应确认无遗漏，但当前 evidence 表明 Slice 2/3 已覆盖所有需要迁移的 test。
- **建议裁决**: accepted（informational）。Slice 4 作为安全网仍然合理，但 implementation agent 可预期 Slice 4 不会发现额外需要迁移的 test。

## Blocking Open Questions

无。

## Plan Readiness Assessment

| 维度 | 评估 |
| --- | --- |
| 目标明确性 | ✅ 目标、动机、成功信号清晰定义 |
| 根因证据 | ✅ 直接证据链完整：test seam → legacy compact() → no manifest → fail-closed guard |
| Scope 边界 | ✅ Non-goals 明确，不修改生产 guard / schema / Engine / public interface |
| Slice 切分 | ✅ 四层 slice 逻辑清晰：new helper → accepted migration → rejected migration → broad validation |
| 实现细节 | ✅ 具体类名、方法签名、imports、常量、call paths、invariants 均已指定 |
| 测试策略 | ✅ Focused validation commands 和 expected assertions 明确 |
| 架构边界 | ✅ 只修改 test seam，不改生产代码 |
| 验证命令 | ✅ 包含 focused、broad、pyright 三组验证 |

**结论**: Plan code-generation-ready，可直接交给 implementation agent。

## Over-design / Under-design Check

**Over-design**: 无。Plan 不抽取 shared production abstraction，不修改 `FakeContextCompactor`，不新增 compatibility facade，不改 schema/EventLog builder。每个 test 的 compactor 迁移保持 test-scoped 私有。

**Under-design**: 无实质遗漏。F1（`_StaleMutatingCompactor` 不需迁移）是 clarity 问题而非设计缺失。Plan 正确识别了 `_TransactionReadableCompactor` 需要迁移（`test_proactive_compaction_calls_llm_outside_write_transaction` 触发 accepted compact）。

## Residual Risks / Uncovered Areas

1. **`-k` 范围外的 proactive test**: 若存在不在给定 `-k` 命令范围内、但同样使用 legacy `FakeContextCompactor()` 并接受 proactive compact 的 test，Slice 4 的 broad scan 应能捕获。当前 evidence 表明风险低。
2. **pyright 签名对齐**: `CompactorProposalPreparedCompactor` 是 `@runtime_checkable Protocol`，helper 的方法签名必须严格对齐。Plan 已识别此风险。
3. **`RUNNER_CALL_INPUT_ASSEMBLED` event count**: Plan 建议在 Slice 2 断言该 count 与 compaction accepted attempt 数一致。需确认该 event 在 proactive compact 路径中确实被写入。

## Validation Performed

1. 读取 plan artifact 全文并逐节审查。
2. 读取 `dayu/host/dispatch.py` 生产 fail-closed guard（`_required_compactor_manifest_ref` / `_required_compactor_manifest_digest`，行 3734-3759）。
3. 读取 `dayu/host/dispatch.py` proactive compact accepted event 写入路径（行 1264-1269, 1648-1671）。
4. 读取 `dayu/host/dispatch.py` proactive rejected event 写入路径（行 1982-2023）。
5. 读取 `dayu/host/compaction_operation.py` `_prepare_compactor_proposal` 的 prepared vs legacy 路径分叉（行 749-784）。
6. 读取 `dayu/host/compaction_operation.py` `run_compaction_operation` 的 rejected attempt 处理（行 507-560）。
7. 读取 `dayu/host/compaction_operation.py` `CompactorProposalPreparedCompactor` protocol 定义（行 134-167）。
8. 读取 `tests/host/test_dispatch_scheduler.py` 的 `_RequestCapturingCompactor`（行 536-559）、`_TransactionReadableCompactor`（行 403-431）、`_StaleMutatingCompactor`（行 433-476）、`_RaisingCompactor`（行 479-495）、`_QualityRejectOnceCompactor`（行 498-533）。
9. 读取 plan 列出的全部 7 个 proactive test 的 test body，确认当前使用的 compactor 类型和断言内容。
10. 读取 `tests/host/test_compaction_operation.py` 的 `_PreparedManifestCompactor`（行 490-549）和 `tests/host/test_engine_ingest_mapping.py` 的 `_PreparedManifestReactiveCompactor`（行 273-344），确认已有 prepared manifest test seam 示例。
11. 读取 `docs/host/issues-implementation-control.md` 的 WU-CM-01-F04 定义（行 540-571）。
12. 读取 `docs/engine/design.md` 确认 Engine 不做 proactive threshold compaction（行 414-423）。
13. 读取 `dayu/host/context_events.py` 的 `build_context_compaction_attempt_rejected_payload`（行 552-599），确认 rejected payload 包含 `proposal_manifest_ref` / `proposal_manifest_digest` 字段。
