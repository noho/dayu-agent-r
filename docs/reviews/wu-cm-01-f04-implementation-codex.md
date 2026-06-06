# WU-CM-01-F04 Implementation Artifact

## Gate

- Work unit: WU-CM-01-F04 Proactive Compaction Manifest-producing Test Seam Closeout
- Gate: implementation
- Status: ready
- Implementer: AgentCodex

## First-principles Judgment

问题动机成立。proactive compaction accepted / rejected event 是 Host durable canonical fact，事件 payload 必须携带 proposal manifest ref / digest，才能把 accepted candidate 或 rejected attempt 与 proposal runner call manifest 同源关联。当前失败根因不是生产 guard 过严，而是 `tests/host/test_dispatch_scheduler.py` 中部分 proactive seam 仍走 legacy `compact()` fake，没有触发 `CompactorProposalPreparedCompactor` 的 manifest recorder 路径。

因此本 gate 只修测试 seam，不修改 `dayu/host/dispatch.py`，不放宽 fail-closed guard，不改生产 contract / schema / Engine。

## Proactive Compactor Injection Inventory

implementation 前按语义枚举了 `tests/host/test_dispatch_scheduler.py` 内 proactive path compactor 注入点，而不是只搜索 `FakeContextCompactor` 字面量。

迁移为 manifest-producing prepared seam：

- `test_pre_start_governance_soft_threshold_compacts_before_attempt`
- `test_proactive_compaction_uses_selected_material_not_session_start_range`
- `test_proactive_material_pack_not_larger_than_ordinary_material_for_same_view`
- `test_wake_queue_promotion_uses_tracked_async_promotion_task`
- `test_proactive_compaction_calls_llm_outside_write_transaction`
- `test_multi_turn_proactive_compact_feeds_subsequent_run_input`
- `test_proactive_compaction_retries_quality_rejection_before_accept`
- `test_compaction_repair_attempt_rejection_is_recorded_in_eventlog`

明确不迁移：

- `_StaleMutatingCompactor` / `test_compaction_stale_result_does_not_write_compacted_event`：该用例验证 stale result 不写 `CONTEXT_COMPACTED`，Host 在 accepted guard 前写 `CONTEXT_COMPACTION_FAILED`，迁移会额外记录 proposal manifest event 并改变测试关注点。
- proactive compact count limit / corrupted count tests：这些路径在 compaction operation 前 fail closed，不触发 accepted/rejected manifest payload contract。
- reactive tests：不是本 work unit 的 proactive seam closeout 范围。

`_RaisingCompactor` 只有 proactive rejected test 使用，已迁移为 prepared post-manifest run failure；这是有意语义升级，用于断言 rejected payload 带 manifest ref / digest。

## Changed Files

- `tests/host/test_dispatch_scheduler.py`
- `docs/reviews/wu-cm-01-f04-implementation-codex.md`

## Implementation Summary

- 新增 `_PreparedManifestProactiveCompactor`，实现 `prepare_compactor_proposal_run_input(...)` 与 `run_prepared_compactor_proposal(...)`，通过 `conversation_compact_input_vnext_from_material_pack(...)`、`CompactorProposalRunInput` 与真实 role sequence digest 触发 durable manifest recorder。
- `_RequestCapturingCompactor` 迁移到 prepared seam，并在 prepare 阶段保留 request 捕获语义。
- `_TransactionReadableCompactor` 迁移到 prepared seam，并在 run 阶段保留独立读事务读取 Run 的原测试语义。
- `_QualityRejectOnceCompactor` 迁移到 prepared seam，第一次 quality rejection 和第二次 accepted 都经过 proposal manifest recorder。
- `_RaisingCompactor` 迁移为 prepared run failure，确保 rejected attempts 发生在 manifest record 之后。
- proactive accepted tests 直接断言 `CONTEXT_COMPACTED` payload 的 `accepted_proposal_manifest_ref` / `accepted_proposal_manifest_digest`。
- proactive rejected tests 直接断言 `CONTEXT_COMPACTION_ATTEMPT_REJECTED` payload 的 `proposal_manifest_ref` / `proposal_manifest_digest`；repair attempt rejection 用例断言两次 rejected payload 均带 manifest。
- 未加入脆弱的 `RUNNER_CALL_INPUT_ASSEMBLED` 固定计数断言；核心验收保持为 compacted/rejected payload manifest ref / digest。

## Validation

通过：

```bash
source .venv/bin/activate && pytest tests/host/test_dispatch_scheduler.py -k "proactive or soft_threshold or wake_queue_promotion_uses_tracked_async_promotion_task"
```

结果：8 passed, 54 deselected。

通过：

```bash
source .venv/bin/activate && pytest tests/host/test_dispatch_scheduler.py::test_pre_start_governance_soft_threshold_compacts_before_attempt tests/host/test_dispatch_scheduler.py::test_proactive_compaction_retries_quality_rejection_before_accept tests/host/test_dispatch_scheduler.py::test_compaction_repair_attempt_rejection_is_recorded_in_eventlog
```

结果：3 passed。

通过：

```bash
source .venv/bin/activate && pyright
```

结果：0 errors, 0 warnings, 0 informations。

## README Decision

已检查 `tests/README.md`。本次只迁移 `tests/host/test_dispatch_scheduler.py` 内部测试 seam，并补 payload assertions；没有新增测试层级、测试运行方式、维护规则或 Host 测试职责说明变化。现有 README 中 Host compaction / dispatch scheduler 描述仍准确，因此无需修改。

## Residual Risks / Uncovered Areas

- 未运行整个 `tests/host/test_dispatch_scheduler.py` 文件或全量测试套件；本 gate 按总控要求执行 focused validation 与 pyright。
- reactive compaction seam 未改动；该范围由既有 reactive prepared manifest tests 覆盖，不属于本 work unit。

## Blocking Open Questions

无。
