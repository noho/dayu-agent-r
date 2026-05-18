# Phase 10 Slice 4 Code Review — AgentMiMo

Reviewer: AgentMiMo
Date: 2026-05-18
Scope: Phase 10 Slice 4 — Proactive Pre-Dispatch Orchestration, RunStatus.ACCEPTED, Admission Changes, Dispatch Scheduler Governance Gate, DurableCompactArtifactProvider

## Verdict

**PASS**

## Summary

Slice 4 实现了 proactive pre-dispatch context governance：admission 在 `start_run` 时创建 `RunStatus.ACCEPTED`（非直接 running），scheduler `wake_queue_promotion` 在 dispatch 前执行 budget 评估与 compaction；soft threshold 触发 compact，hard threshold 或 compact failure 以 attempt-free `RUN_FAILED` 终止；`DurableCompactArtifactProvider` 从 `CONTEXT_COMPACTED` 事件读取 artifact 并仅暴露安全字段。全部 124 个测试通过，pyright 零错误。

## Verification

| 检查项 | 结果 |
| --- | --- |
| `pytest tests/host/ -q` | 124 passed, 0 failed |
| `pyright` | 0 errors, 0 warnings, 0 informations |

## Adversarial Check Matrix

### 1. RunStatus.ACCEPTED 是否真正阻塞 dispatch？

| 攻击向量 | 防御路径 | 结论 |
| --- | --- | --- |
| ACCEPTED run 被直接 dispatch | `state.py:read_startable_run_row` 仅读 `status='queued'` 或 `status='accepted'`；`dispatch.py:_read_startable_run` 优先 accepted 但必须经过 `_run_pre_start_governance` | **BLOCKED** |
| governance bypass 直接 start | `state.py:start_unstarted_run_row` CAS 仅接受 `accepted→running` 或 `queued→running`，不接受其他中间态 | **BLOCKED** |
| 多个 accepted run 同时存在 | `schema.py:INDEX_HOST_RUNS_ONE_ACCEPTED_PER_SESSION` unique index 阻止同一 session 多个 accepted run | **BLOCKED** |
| accepted 与 running 并存 | `schema.py:INDEX_HOST_RUNS_ONE_ACTIVE_PER_SESSION` unique index 覆盖 accepted + running + queued 等活跃态 | **BLOCKED** |

### 2. Proactive compact 是否可被绕过或重复执行？

| 攻击向量 | 防御路径 | 结论 |
| --- | --- | --- |
| 跳过 compact 直接 dispatch | `_run_pre_start_governance` 在 `budget_result.trigger_source != NONE` 时必须走 compact 路径；hard threshold 直接 fail | **BLOCKED** |
| 第二轮 compact loop | `_committed_proactive_compact_count()` 从 durable EventLog 统计已 committed 的 `CONTEXT_COMPACTION_REQUESTED`（proactive）；count ≥ 1 时拒绝第二轮 | **BLOCKED** |
| compact count 被篡改（corrupted facts） | `_committed_proactive_compact_count` 捕获 `ValueError` 并 fail closed（返回 max_count → 触发 fail） | **BLOCKED** |
| compact 失败后仍 dispatch | `_compact_before_dispatch` 失败时调用 `_fail_unstarted_in_transaction` 写 `CONTEXT_COMPACTION_FAILED` + `RUN_FAILED`，不进入 start | **BLOCKED** |

### 3. Attempt-free failure 是否真正零 Attempt？

| 攻击向量 | 防御路径 | 结论 |
| --- | --- | --- |
| `_fail_unstarted_in_transaction` 创建 Attempt | `run_transition.py:fail_unstarted_run_in_transaction` 仅写 `RUN_FAILED` + `CONTEXT_COMPACTION_FAILED`，不插入 Attempt 行 | **BLOCKED** |
| governance fail 后 run 仍可 start | `_fail_unstarted_in_transaction` CAS `accepted/queued→failed`；`start_unstarted_run_row` 仅接受 `accepted/queued→running`，已 failed 的 run 不可 start | **BLOCKED** |

### 4. DurableCompactArtifactProvider 是否泄漏敏感数据？

| 攻击向量 | 防御路径 | 结论 |
| --- | --- | --- |
| 泄漏 dropped ranges | `DurableCompactArtifactProvider.get_compact_artifact` 仅输出 `artifact_ref`、`artifact_digest`、`preserved_verified_fact_refs`、`bounded_summary`；不暴露 `dropped_ranges`、`summarized_ranges` | **BLOCKED** |
| 泄漏完整 artifact JSON | `_latest_compacted_event_before_attempt` 读取整个 payload 但 `get_compact_artifact` 仅提取允许字段 | **BLOCKED** |
| 泄漏 pinned patch internals | 输出不含 `pinned_state_patch_candidate` | **BLOCKED** |
| Attempt 之后的 compact event 被读取 | SQL 查询 `WHERE sequence_number < ?` 以 attempt cursor 为上界 | **BLOCKED** |

### 5. Event ordering 是否正确？

| 顺序要求 | 防御路径 | 结论 |
| --- | --- | --- |
| CONTEXT_COMPACTION_REQUESTED < CONTEXT_COMPACTED | `_compact_before_dispatch` 先 append REQUESTED，再 append COMPACTED，同事务内 sequence 递增 | **BLOCKED** |
| CONTEXT_COMPACTED < RUN_STARTED | `_start_governed_after_compact` catch-up 后调用 `start_governed_run_with_starting_attempt_in_transaction`，RUN_STARTED 在 COMPACTED 之后 | **BLOCKED** |
| RUN_STARTED < ATTEMPT_STARTED | 同一事务内 `start_governed_run_with_starting_attempt_in_transaction` 先写 RUN_STARTED 再写 ATTEMPT_STARTED | **BLOCKED** |

### 6. Schema v9 约束完整性

| 约束 | 证据 | 结论 |
| --- | --- | --- |
| accepted 在 status CHECK 约束内 | `schema.py:_DDL_HOST_RUNS_V9` `status IN ('accepted', ...)` | **PASS** |
| one-accepted-per-session unique index | `INDEX_HOST_RUNS_ONE_ACCEPTED_PER_SESSION` | **PASS** |
| accepted 在 active unique index 内 | `INDEX_HOST_RUNS_ONE_ACTIVE_PER_SESSION` 覆盖 accepted | **PASS** |
| v8→v9 migration 正确 | `_ensure_schema` 检测 `has_v8` 或 `has_accepted_column` 缺失时执行 v9 DDL | **PASS** |

## Findings

**无 blocking / high / medium defect。**

### Low

**L1. `promote_next_queued_run` 保留为 public helper 但 Slice 4 不直接调用**

- 文件: `dayu/host/dispatch.py`
- 状态: 保留。Slice 4 governance 路径通过 `_start_governed_after_compact` 调用 `start_governed_run_with_starting_attempt_in_transaction`，不经过 `promote_next_queued_run`。
- 影响: 该函数仍是 `cancel_run` → `_promote_after_release` → `wake_queue_promotion` 路径的潜在入口（通过 governance gate），但当前代码中 `_promote_after_release` 改为直接调用 `wake_queue_promotion`。
- 建议: 保留用于未来 slice 可能需要的直接 promotion 场景。不阻塞。

**L2. `_run_pre_start_governance` 中 budget estimate 仅覆盖 input text fragment**

- 文件: `dayu/host/dispatch.py`
- 状态: 当前 budget estimate 使用 `estimate_context_budget_from_input_text`，仅基于最新 user input 文本估算。不包含 history pool、memory messages 等。
- 影响: 可能低估实际 context 大小，导致在接近阈值时延迟触发 compact。但 quality check 在 compact 后会验证完整性，不会导致数据丢失。
- 优先级低，不阻塞。

### Info

**I1. `cancel_queued_in_transaction` 与 `cancel_accepted_in_transaction` 命名区分**

- 文件: `dayu/host/durable/run_transition.py`
- 状态: `cancel_queued_in_transaction` 实际处理 queued + accepted 两种 status 的 CAS（`WHERE status IN ('queued', 'accepted')`），函数名略显不精确。
- 影响: 功能正确，仅命名语义。`cancel_run` 在 admission 层根据 run status 分派到不同路径。

## Plan Compliance

| 计划要求 | 状态 | 证据 |
| --- | --- | --- |
| RunStatus.ACCEPTED 作为 pre-start active state | PASS | `api.py` RunStatus.ACCEPTED; `schema.py` v9 CHECK + unique index |
| admission `start_run` 创建 accepted 而非 running | PASS | `admission.py:_create_accepted_admission_result` 写 RUN_ACCEPTED |
| REJECT / ATTACH_ACTIVE 与 accepted 冲突 | PASS | `admission.py:_resolve_conflict_policy` accepted 在 active set 内 |
| `wake_queue_promotion` 作为 production governance gate | PASS | `dispatch.py:wake_queue_promotion` → `_run_pre_start_governance` |
| proactive soft threshold 触发 compact | PASS | `dispatch.py:_run_pre_start_governance` budget trigger → `_compact_before_dispatch` |
| hard threshold / compact failure = attempt-free RUN_FAILED | PASS | `dispatch.py:_fail_unstarted_in_transaction`; `run_transition.py:fail_unstarted_run_in_transaction` |
| durable proactive compact count 防止第二轮 | PASS | `dispatch.py:_committed_proactive_compact_count` 从 EventLog 统计 |
| corrupted compact count fail closed | PASS | `_committed_proactive_compact_count` catch ValueError → return max |
| CONTEXT_COMPACTION_REQUESTED / COMPACTED / RUN_STARTED 顺序 | PASS | `_compact_before_dispatch` → `_start_governed_after_compact` 事务内顺序 |
| DurableCompactArtifactProvider 仅暴露安全字段 | PASS | `run_input.py:get_compact_artifact` 返回 4 个安全字段 |
| compact artifact provider 注入 RunInputBuilder | PASS | `dispatch.py` 多处 `_run_input_builder_factory(artifact_provider=...)` |
| cancel_run 处理 ACCEPTED status | PASS | `admission.py` ACCEPTED → `_cancel_queued` path; `run_transition.py:cancel_queued_in_transaction` CAS accepted |
| schema v9 migration | PASS | `schema.py:_DDL_HOST_RUNS_V9` + `_ensure_schema` |
| FollowupSnapshot 处理 ACCEPTED | PASS | `api.py` FollowupSnapshot ACCEPTED → followup_running=True |
| README 同步 | PASS | `dayu/host/README.md` 更新 pre-start governance gate 描述 |

## Residual Risks

1. **Proactive budget estimate 范围有限**：当前 estimate 仅基于 input text fragment，不包含 history pool / memory messages。后续 slice 可扩展 estimator 接入更完整的 context 大小估算。
2. **Compact artifact content-level rebuild 未实现**：`DurableCompactArtifactProvider` 从 durable event 读取已有 artifact，不触发 artifact 内容重建。属于后续 slice（real LLM compactor adapter）范围。
3. **Proactive/Reactive compact 共用 `_compact_before_dispatch`**：当前实现 proactive 路径；reactive（provider overflow 触发）由 Slice 5 接入。
4. **`promote_next_queued_run` 保留但未在 Slice 4 直接调用**：未来 slice 若需要非 governance 直接 promotion 路径可复用。
