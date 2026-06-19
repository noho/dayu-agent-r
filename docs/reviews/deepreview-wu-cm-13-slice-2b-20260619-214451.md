# WU-CM-13 Code Review — Slice 2b Deepreview

## Reviewed Target

- **Scope**: workspace uncommitted diff — Slice 2b of WU-CM-13 (reactive ingest wiring)
- **Changed files**:
  - `dayu/host/engine_ingest.py` — MODIFIED (−251 / +70 net lines)
  - `tests/host/test_dispatch_scheduler.py` — MODIFIED (1 test renamed + strengthened)
- **Design sources**: `docs/host/design.md`, `docs/engine/design.md`
- **Accepted plan**: `docs/host/host-issues/wu-cm-13-unified-compact-pipeline-plan.md`
- **Pre-verified**: `pytest tests/host/test_dispatch_scheduler.py tests/host/test_compact_pipeline.py -q` → 88 passed; `pyright dayu/ tests/ utils/` → 0 errors; `git diff --check` clean

## Review Methodology

1. 验证 Slice 2b 是否只 wire reactive ingest
2. 验证 CONTEXT_COMPACTION_REQUESTED append、Attempt closeout、RUN_RECOVERING、commit guards 仍在 engine_ingest.py
3. 验证 policy digest 从 memory policy 派生
4. 验证 frozen material semantics 保留
5. 验证未触碰 dispatch proactive、run_input raw-tail、tier 5、fallback_tier、public API/schema
6. 验证 tests 是否削弱

## Findings

### 无 material findings

Slice 2b 实现与 accepted plan 一致，无 material findings。

## Verification Details

### 1. Reactive ingest wiring — PASS

| Plan requirement | engine_ingest.py 实现 | 验证 |
|---|---|---|
| `_reactive_compaction_request` 被 `build_normal_compact_request_plan(...)` 替代 | 行 1615-1627：`request_plan = build_normal_compact_request_plan(source_snapshot=..., selection_policy_digest=digest_memory_projection_policy(memory_policy), ...)` | ✅ 旧函数 `_reactive_compaction_request(...)` 已删除 |
| `_reactive_compaction_pass_queue` 被 `build_reactive_pass_queue_plan(...)` 替代 | 行 1628-1631：`pass_queue = build_reactive_pass_queue_plan(source_snapshot=..., root_request_plan=request_plan).pass_requests` | ✅ 旧函数 `_reactive_compaction_pass_queue(...)` 已删除 |
| `_reactive_fallback_decision` 被 `build_fallback_decision_input(...)` 替代 | 行 1723-1736：`fallback_decision = build_fallback_decision_input(source_snapshot=..., context_policy=..., memory_policy=..., ...)` | ✅ 旧函数 `_reactive_fallback_decision(...)` 和 `_ReactiveFallbackDecision` dataclass 已删除 |
| `compact_pipeline_source_snapshot_from_pre_dispatch_view(...)` 构造 source_snapshot | 行 1314-1318：`source_snapshot = compact_pipeline_source_snapshot_from_pre_dispatch_view(trigger_source=REACTIVE, run=context.run, material_view=material_view)` | ✅ |
| `_ReactiveCompactPending` 存储 `source_snapshot` | 行 499：`source_snapshot: CompactPipelineSourceSnapshot`；旧字段 `display_text`、`frozen_material_blocks`、`previous_compacted_view`、`frozen_material_list_digest`、`frozen_material_refs`、`selected_recent_window_turn_floor` 已删除 | ✅ |

### 2. Lifecycle ownership preserved — PASS

| Engine-ingest-owned responsibility | 验证 |
|---|---|
| `CONTEXT_COMPACTION_REQUESTED` append | 行 1337：`self._append_reactive_compaction_requested_event(...)` unchanged |
| Attempt closeout | 行 1350-1358：`self._close_attempt_for_context_recovery(...)` unchanged |
| `RUN_RECOVERING` | 行 230：`_EVENT_TYPE_RUN_RECOVERING` unchanged |
| Stale cursor guard | 行 1674-1676：`if latest.run.status is RunStatus.RECOVERING and sequence_stale` preserved |
| Execution mismatch guard | 行 1698：`latest.run.status is not RunStatus.RECOVERING` check preserved |
| Cancellation token pass-through | 行 1654-1655：`cancellation_token=pending.context.candidate.envelope.cancellation_token` preserved |
| Recovery Attempt creation | 行 1750-1760：`_ReactiveRecoveryAccepted` with `PendingDispatchRecord` preserved |
| `CONTEXT_COMPACTED` append on success | 行 1700-1712：`self._append_reactive_compaction_accepted_event(...)` preserved |
| `CONTEXT_COMPACTION_FAILED` append on failure | 行 1740-1755：`self._append_reactive_compaction_failed_event(...)` preserved |

### 3. Policy digest source — PASS

- **旧代码**：`policy_digest=pending.frozen_material_list_digest`（frozen material list digest）
- **新代码**：`selection_policy_digest=digest_memory_projection_policy(memory_policy)`（行 1621）
- **验证**：`frozen_material_list_digest` 仍用于 `CONTEXT_COMPACTION_REQUESTED` payload（行 1599），这是正确的——它是 frozen material list 的 digest，不是 selection policy digest
- **区分**：`estimator_digest` 仍用于 budget snapshot（行 1591/1593），与 selection policy digest 独立

### 4. Frozen material semantics — PASS

- `source_snapshot` 由 `compact_pipeline_source_snapshot_from_pre_dispatch_view(...)` 从同一个 `material_view` 构造（行 1314-1318）
- `material_view` 来自 `build_pre_dispatch_compact_material_view(...)`（行 1305-1310），与旧代码相同
- `source_snapshot.material_blocks` 等价于旧 `frozen_material_blocks`
- `source_snapshot.previous_compacted_view` 等价于旧 `previous_compacted_view`
- `source_snapshot.material_view_digest` 等价于旧 `frozen_material_list_digest`（但用于不同目的）
- `source_snapshot.material_source_refs` 等价于旧 `frozen_material_refs`

### 5. Boundary compliance — PASS

| Boundary | 验证 |
|---|---|
| 未触碰 dispatch proactive | `dispatch` 不在 engine_ingest.py import 中 |
| 未触碰 run_input raw-tail | `run_input` 不在 engine_ingest.py import 中 |
| 无 tier 5 | `grep "tier_5\|tier 5\|current_input_only" dayu/host/engine_ingest.py` → 无命中 |
| 无 fallback_tier | `grep "fallback_tier" dayu/host/engine_ingest.py` → 无命中 |
| 无 public API/schema 变更 | 无新增 public exports |
| 无 EventLog event type 变更 | `CONTEXT_COMPACTED` / `CONTEXT_COMPACTION_FAILED` / `CONTEXT_COMPACTION_REQUESTED` payload 格式不变 |

### 6. Removed code — PASS

以下 helper 函数和类型已从 engine_ingest.py 删除，无 dangling references：

- `_reactive_compaction_request(...)` — 删除
- `_reactive_compaction_pass_queue(...)` — 删除
- `_reactive_fallback_decision(...)` — 删除
- `_ReactiveFallbackDecision` dataclass — 删除
- `_single_block_segment_selection(...)` — 删除
- `_fallback_selection_failure_reason(...)` — 删除
- `build_compact_material_pack`、`select_compact_segment`、`selected_material_source_refs` import — 删除
- `CompactSegmentSelection`、`CompactSegmentTrigger`、`CompactMaterialBlock` import — 删除
- `RecentWindowFallbackSelection`、`build_recent_window_fallback_selection`、`estimate_recent_window_fallback_budget` 等 import — 删除

`grep` 确认 engine_ingest.py 中无上述符号的残留引用。

### 7. Test changes — PASS (strengthened, not weakened)

**唯一修改的测试**：`test_reactive_fallback_decision_uses_memory_policy_caps` → `test_reactive_fallback_pipeline_uses_memory_policy_caps`

| 维度 | 旧测试 | 新测试 |
|---|---|---|
| 测试对象 | 构造 `_ReactiveCompactPending` → 调用 `_reactive_fallback_decision(...)` | 构造 `CompactPipelineSourceSnapshot` → 调用 `build_fallback_decision_input(...)` |
| 断言 1 | `decision.action == "dispatch"` | `decision.action_hint == "dispatch"` |
| 断言 2 | `decision.input_window["selected_block_ids"] == [...]` | `failed_input.fallback_input_window["selected_block_ids"] == [...]` |
| 断言 3 | dropped block ids 检查 | dropped block ids 检查 |
| 断言 4 | 无 | **新增**：`"fallback_tier" not in failed_input.fallback_input_window` |
| 评估 | **更强**：新增 fallback_tier 断言，测试 pipeline 函数而非内部 helper |  |

**测试数量**：78 → 78（1 个重命名，0 个删除，0 个新增）

## Architecture Boundary Review

### Layering
- engine_ingest.py 位于 Host 内部 Engine event ingest 层，正确 import compact_pipeline helper。
- 不新增对 dispatch / run_input 的依赖。

### Dependency Direction
- `engine_ingest.py → compact_pipeline.py → compact_material.py`（正确方向）
- compact_pipeline 不 import engine_ingest（单向依赖）

### Public Contracts
- 无 public API / schema / EventLog event type 变更
- `_ReactiveCompactPending` 是 Host 内部 dataclass，不暴露给外部

## Residual Risks

| ID | 风险 | 严重程度 | 追踪 |
|---|---|---|---|
| RR-1 | Slice 2c (RunInput raw-tail wiring) 尚未实施 | 中 | WU-CM-13 Slice 2c |

## Final Code Review Conclusion

**pass**

Slice 2b 正确实现 reactive ingest wiring：

- `build_normal_compact_request_plan(...)` 替代 `_reactive_compaction_request(...)`
- `build_reactive_pass_queue_plan(...)` 替代 `_reactive_compaction_pass_queue(...)`
- `build_fallback_decision_input(...)` 替代 `_reactive_fallback_decision(...)`
- `selection_policy_digest` 从 `digest_memory_projection_policy(memory_policy)` 派生
- `CONTEXT_COMPACTION_REQUESTED` append、Attempt closeout、`RUN_RECOVERING`、stale cursor guard、execution mismatch guard、cancellation token、recovery Attempt creation 全部保留在 engine_ingest.py
- `_ReactiveCompactPending` 简化为存储 `source_snapshot` 而非 6 个独立字段
- 未触碰 dispatch proactive、run_input raw-tail、tier 5、fallback_tier、public API/schema
- 测试新增 `fallback_tier` 断言，覆盖更强
- pyright 0 errors，88 tests passed，git diff --check clean
