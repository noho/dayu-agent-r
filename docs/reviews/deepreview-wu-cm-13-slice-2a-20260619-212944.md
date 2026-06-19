# WU-CM-13 Code Review — Slice 2a Deepreview

## Reviewed Target

- **Scope**: workspace uncommitted diff — Slice 2a of WU-CM-13 (proactive dispatch wiring)
- **Changed files**:
  - `dayu/host/dispatch.py` — MODIFIED (−345 / +90 net lines)
  - `tests/host/test_dispatch_scheduler.py` — MODIFIED (1 test renamed + strengthened)
- **Design sources**: `docs/host/design.md`, `docs/engine/design.md`
- **Accepted plan**: `docs/host/host-issues/wu-cm-13-unified-compact-pipeline-plan.md`
- **Pre-verified**: `pytest tests/host/test_dispatch_scheduler.py tests/host/test_compact_pipeline.py -q` → 88 passed; `pyright dayu/ tests/ utils/` → 0 errors; `git diff --check` clean

## Review Methodology

1. 验证 Slice 2a 是否只 wire proactive dispatch
2. 验证 EventLog append、artifact write、fail-unstarted、commit guard、lifecycle 仍在 dispatch.py
3. 验证 policy digest 从 memory policy 派生
4. 验证 stale/cursor guard 保留
5. 验证未触碰 engine_ingest reactive、run_input raw-tail、tier 5、fallback_tier、public API/schema
6. 验证 tests 是否削弱

## Findings

### 无 material findings

Slice 2a 实现与 accepted plan 一致，无 material findings。

## Verification Details

### 1. Proactive dispatch wiring — PASS

| Plan requirement | dispatch.py 实现 | 验证 |
|---|---|---|
| normal request 使用 `build_normal_compact_request_plan(...)` | 行 1750-1764：`source_snapshot = compact_pipeline_source_snapshot_from_pre_dispatch_view(...)` → `request_plan = build_normal_compact_request_plan(...)` → `request = request_plan.request` | ✅ |
| tier 1-3 recovery 使用 `build_tier_recovery_request_plans(...)` | 行 1509-1515：`build_tier_recovery_request_plans(source_snapshot=pending.source_snapshot, root_request_plan=pending.request_plan, memory_policy=...)` | ✅ |
| fallback selection/payload input 使用 `build_fallback_decision_input(...)` | 行 1991-2015：`fallback_decision = build_fallback_decision_input(source_snapshot=..., context_policy=policy, memory_policy=..., ...)` | ✅ |
| `_GovernanceCompactPending` 存储 `source_snapshot` 和 `request_plan` | 行 433-434：新增 `source_snapshot: CompactPipelineSourceSnapshot` 和 `request_plan: CompactPipelineRequestPlan` | ✅ |

### 2. Lifecycle ownership preserved — PASS

| Dispatch-owned responsibility | 验证 |
|---|---|
| EventLog append (`CONTEXT_COMPACTED`) | 行 1004：`compact_accepted is not None` → dispatch appends event |
| EventLog append (`CONTEXT_COMPACTION_FAILED`) | 行 2076-2098：`_append_compaction_failed_event(...)` unchanged |
| Artifact write | 行 1004-1019：dispatch writes artifact after accepted compact |
| Fail-unstarted | 行 1061/1114：`_fail_unstarted_in_transaction(...)` preserved |
| Pending dispatch / start | 行 1049：`_start_governed_in_transaction(...)` preserved |
| Commit guard | `_GovernanceCompactPending.expected_status` / `expected_input_event_sequence` unchanged |
| Recovery attempt dispatch | 行 1004-1019：dispatch starts same Run after accepted compact |

### 3. Policy digest source — PASS

- **旧代码**：`policy_digest=estimate.estimator_digest`（BudgetEstimate digest）
- **新代码**：`selection_policy_digest=digest_memory_projection_policy(memory_policy)`（行 1758）
- **验证**：`estimator_digest` 仍用于 logging/预算 snapshot（行 359/1143/1930/2102），但不再作为 selection policy digest
- **测试断言**：`test_proactive_compact_selection_passes_protected_recent_floor` 新增 `assert request.segment_selection.policy_digest == digest_memory_projection_policy(memory_policy)`（行 4265-4267）

### 4. Stale/cursor guard — PASS

- `_GovernanceCompactPending` 保留 `expected_status: RunStatus` 和 `expected_input_event_sequence: int`（行 430-431）
- Commit guard 检查在 `_commit_compact_result(...)` 中（行 739-741）：`if run.input_event_sequence != self.expected_input_event_sequence` / `if run.status != self.expected_status`
- 这些 guard 未被 Slice 2a 修改

### 5. Boundary compliance — PASS

| Boundary | 验证 |
|---|---|
| 未触碰 engine_ingest reactive | `engine_ingest` import 是 pre-existing（行 97），非 Slice 2a 新增；reactive 路径代码未修改 |
| 未触碰 run_input raw-tail | `run_input` import 是 pre-existing（行 109），非 Slice 2a 新增；raw-tail 相关代码未修改 |
| 无 tier 5 | `grep "tier_5\|tier 5\|current_input_only" dayu/host/dispatch.py` → 无命中 |
| 无 fallback_tier | `grep "fallback_tier" dayu/host/dispatch.py` → 无命中 |
| 无 public API/schema 变更 | 无新增 public exports；`_GovernanceCompactPending` 是 Host 内部类型 |
| 无 EventLog event type 变更 | `CONTEXT_COMPACTED` / `CONTEXT_COMPACTION_FAILED` payload 格式不变 |

### 6. Removed code — PASS

以下 helper 函数和 import 已从 dispatch.py 删除，无 dangling references：

- `_proactive_compaction_recovery_request(...)` — 删除
- `_build_proactive_fallback_selection(...)` — 删除
- `_proactive_fallback_material_blocks(...)` — 删除
- `_current_input_material_block(...)` — 删除
- `_selected_evidence_refs(...)` — 删除
- `_selected_raw_turn_refs(...)` — 删除
- `_dedupe_texts(...)` — 删除
- `select_compact_segment`、`build_compact_material_pack`、`degrade_previous_compacted_view_for_recovery`、`run_input_material_block`、`selected_material_source_refs` import — 删除
- `CompactMaterialBlock`、`CompactMaterialBlockKind`、`CompactMaterialSection`、`CompactSegmentSelection`、`CompactSegmentTrigger` import — 删除
- `RecentWindowFallbackSelection`、`build_recent_window_fallback_selection`、`estimate_recent_window_fallback_budget` 等 import — 删除

`grep` 确认 dispatch.py 中无上述符号的残留引用。

### 7. Test changes — PASS (strengthened, not weakened)

**唯一修改的测试**：`test_proactive_fallback_material_blocks_append_current_input_once` → `test_proactive_fallback_payload_appends_current_input_once`

| 维度 | 旧测试 | 新测试 |
|---|---|---|
| 测试对象 | 直接调用 `_proactive_fallback_material_blocks(...)` helper | 通过 scheduler 端到端触发 proactive fallback |
| 断言 | 检查 helper 返回的 material blocks 中 current input anchor 出现一次 | 检查 EventLog `CONTEXT_COMPACTION_FAILED` payload 中 `fallback_input_window.selected_block_ids` 包含 current input 一次 |
| 覆盖 | 只验证 helper 逻辑 | 验证完整 dispatch → compact failure → fallback → EventLog payload 路径 |
| 评估 | **更强**：端到端验证 production path，而非孤立 helper |  |

**新增断言**：`test_proactive_compact_selection_passes_protected_recent_floor` 新增 `assert request.segment_selection.policy_digest == digest_memory_projection_policy(memory_policy)`（行 4265-4267），验证 policy digest 来源。

**测试数量**：78 → 78（1 个重命名，0 个删除，0 个新增）

## Architecture Boundary Review

### Layering
- dispatch.py 位于 Host 内部调度层，正确 import compact_pipeline helper。
- 不新增对 engine_ingest / run_input 的依赖（pre-existing imports unchanged）。

### Dependency Direction
- `dispatch.py → compact_pipeline.py → compact_material.py`（正确方向）
- compact_pipeline 不 import dispatch（单向依赖）

### Public Contracts
- 无 public API / schema / EventLog event type 变更
- `_GovernanceCompactPending` 是 Host 内部 dataclass，不暴露给外部

## Residual Risks

| ID | 风险 | 严重程度 | 追踪 |
|---|---|---|---|
| RR-1 | Slice 2b (reactive ingest wiring) / 2c (RunInput raw-tail wiring) 尚未实施 | 中 | WU-CM-13 Slice 2b/2c |

## Final Code Review Conclusion

**pass**

Slice 2a 正确实现 proactive dispatch wiring：

- `build_normal_compact_request_plan(...)` 替代手动 request construction
- `build_tier_recovery_request_plans(...)` 替代 `_proactive_compaction_recovery_attempts`
- `build_fallback_decision_input(...)` 替代 `_build_proactive_fallback_selection` 和手动 fallback 逻辑
- `selection_policy_digest` 从 `digest_memory_projection_policy(memory_policy)` 派生，不再用 `estimate.estimator_digest`
- EventLog append、artifact write、fail-unstarted、commit guard、lifecycle 全部保留在 dispatch.py
- 未触碰 engine_ingest reactive、run_input raw-tail、tier 5、fallback_tier、public API/schema
- 测试从孤立 helper 测试升级为端到端 scheduler 测试，覆盖更强
- pyright 0 errors，88 tests passed，git diff --check clean
