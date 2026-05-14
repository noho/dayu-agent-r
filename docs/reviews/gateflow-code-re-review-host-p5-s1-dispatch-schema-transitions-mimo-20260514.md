# Re-Review: Host Phase 5 P5-S1 Dispatch Schema And Transition Primitives

- gate: Host Phase 5 P5-S1 code re-review
- reviewer role: independent code reviewer
- review date: 2026-05-14
- source fix artifact: `docs/reviews/gateflow-fix-host-p5-s1-dispatch-schema-transitions-20260514.md`
- source reviews:
  - `docs/reviews/gateflow-code-review-host-p5-s1-dispatch-schema-transitions-mimo-20260514.md`
  - `docs/reviews/gateflow-code-review-host-p5-s1-dispatch-schema-transitions-ds-20260514.md`

## Re-Review Scope

复查 controller fix 后的当前未提交 diff，确认 F2 / DS M1 关于 `mark_dispatching_after_lane_row` 的问题是否已修复，以及是否引入新 blocker。

Production files:

- `dayu/host/durable/schema.py`
- `dayu/host/durable/state.py`
- `dayu/host/durable/run_transition.py`

Test files:

- `tests/host/test_state_schema.py`
- `tests/host/test_run_attempt_transitions.py`
- `tests/host/test_weak_typing_guard.py`

## Validation Reconfirmed

```
pytest tests/host/test_state_schema.py tests/host/test_run_attempt_transitions.py tests/host/test_weak_typing_guard.py -q => 34 passed (was 33, +1 regression test)
python -m pyright dayu/host tests/host => 0 errors, 0 warnings, 0 informations
git diff --check => passed
```

## Fix Verification

### MiMo F2 / DS M1 — `mark_dispatching_after_lane_row` PENDING 不能跳过 waiting_for_lane

**Status**: FIXED

**修复前问题**: `mark_dispatching_after_lane_row` 的 WHERE 子句接受 `status IN (PENDING, WAITING_FOR_LANE)`，允许 PENDING 直接跳到 DISPATCHING，违反 plan 规定的状态序列 `pending -> waiting_for_lane -> dispatching`。且使用 `COALESCE(waiting_for_lane_at, dispatching_at)` 合成缺失的等待时间戳。

**修复后代码** (`state.py:1991-2030`)：

```sql
UPDATE host_attempt_dispatch_records
SET
  status = ?,
  owner_host_instance_id = ?,
  lane_name = ?,
  lane_claim_id = ?,
  lane_owner_id = ?,
  lane_acquired_at = ?,
  dispatching_at = ?,
  updated_at = ?
WHERE attempt_id = ?
  AND status = ?                              -- ← 只接受 WAITING_FOR_LANE
  AND waiting_for_lane_at IS NOT NULL         -- ← 新增：确保已走过 waiting 阶段
  AND lane_name = ?                           -- ← 新增：匹配 lane name 一致性
  AND lane_claim_id IS NULL
  AND lane_owner_id IS NULL
  AND lane_acquired_at IS NULL
  AND dispatching_at IS NULL
  AND worker_accept_event_id IS NULL
  AND cancelled_event_id IS NULL
```

关键变化：

1. `status IN (?, ?)` → `status = ?`，只接受 `WAITING_FOR_LANE`。
2. 新增 `AND waiting_for_lane_at IS NOT NULL`，确保记录已走过 waiting 阶段。
3. 新增 `AND lane_name = ?`，匹配 SET 的 lane_name，防止 lane 不一致。
4. 移除 `COALESCE(waiting_for_lane_at, dispatching_at)`，不再合成缺失时间戳。
5. 改用专用 mutation result classifier `_dispatch_record_mutation_result_for_lane_dispatching`（state.py:2943-2969），PENDING 源返回 `INVALID_STATE` 而非 `CAS_LOST`。

**新增 regression test** (`test_run_attempt_transitions.py:834-863`)：

```python
def test_dispatching_requires_waiting_for_lane_source(tmp_path: Path) -> None:
    """pending dispatch record 不能跳过 waiting_for_lane 直接进入 dispatching。"""
    # ...
    assert store.transaction_runner.run_write(operation) == (
        StateMutationStatus.INVALID_STATE.value,
        DispatchRecordStatus.PENDING.value,
    )
```

测试确认：对 PENDING 记录直接调用 `mark_dispatching_after_lane_row` 返回 `INVALID_STATE`，记录状态保持 `PENDING` 不变。

**Verdict**: 修复完整且正确。WHERE 子句从 source status、`waiting_for_lane_at` 非空、`lane_name` 匹配三个维度锁定了只有 `WAITING_FOR_LANE` 记录可以进入 `DISPATCHING`。专用 classifier 确保 PENDING 源返回语义正确的 `INVALID_STATE` 而非可重试的 `CAS_LOST`。

---

### 新引入问题检查

**Status**: NO NEW BLOCKERS

逐项检查 fix 是否引入新问题：

1. **`_dispatch_record_mutation_result_for_lane_dispatching` classifier 语义** (state.py:2943-2969):
   - `rowcount == 1` → `UPDATED` ✓
   - `latest is None` → `NOT_FOUND` ✓
   - `latest.status == WAITING_FOR_LANE` → `CAS_LOST`（其他事务抢先消耗）✓
   - 其它 → `INVALID_STATE`（PENDING / DISPATCHING / CANCELLED）✓
   - 语义清晰，无歧义。

2. **`mark_dispatch_waiting_for_lane_row` 未受影响** (state.py:1896-1953):
   - WHERE 子句仍为 `status = PENDING`，与 `mark_dispatching_after_lane_row` 的 `status = WAITING_FOR_LANE` 无缝衔接。
   - 仍使用 `_dispatch_record_mutation_result_for_dispatch_start` classifier，正确。

3. **`_dispatch_record_mutation_result_for_dispatch_start` classifier 仍正确** (state.py:2877-2906):
   - 此 classifier 供 `mark_dispatch_waiting_for_lane_row` 使用，PENDING / WAITING_FOR_LANE → `CAS_LOST`，其它 → `INVALID_STATE`。
   - `mark_dispatching_after_lane_row` 已改用专用 classifier，不再共用。

4. **`cancel_starting_dispatch_record_row` 与修复后的一致性**:
   - WHERE 子句 `status IN (PENDING, WAITING_FOR_LANE, DISPATCHING)` + `worker_accepted_at/event_id/sequence IS NULL`。
   - PENDING 直接 cancel ✓；WAITING_FOR_LANE 直接 cancel ✓；DISPATCHING 无 worker refs 时 cancel ✓。
   - 与 `mark_dispatching_after_lane_row` 的状态推进路径无冲突。

5. **`_dispatch_record_is_direct_cancelable` 与修复后的一致性**:
   - PENDING → True ✓；WAITING_FOR_LANE → True ✓；DISPATCHING 无 worker refs → True ✓。
   - `mark_dispatching_after_lane_row` 只从 WAITING_FOR_LANE 推进到 DISPATCHING，cancel 逻辑无影响。

6. **`accept_worker_running_in_transaction` 无变化**:
   - 前置检查 `dispatch_record.status != DispatchRecordStatus.DISPATCHING` 不受影响。
   - `mark_dispatch_worker_accepted_row` WHERE 子句只接受 DISPATCHING + worker refs 全空，不受影响。

7. **Schema DDL 无变化**: fix 只修改 `state.py` 和测试，schema 不受影响。

---

## 原 Review Findings 状态

| Finding | 状态 | 说明 |
|---|---|---|
| F1 (Medium) — ATTEMPT_RUNNING payload 缺少 4 字段 | **仍为 P5-S3 handoff risk** | fix artifact 已记录，P5-S3 必须扩展 `AcceptWorkerRunningInput` 和 payload。 |
| F2 (Low) — mark_dispatching_after_lane_row WHERE 子句 | **FIXED** | 见上方详细验证。 |
| F3 (Info) — _dispatch_record_is_direct_cancelable 一致性 | **仍为正面观察** | 与修复后代码一致。 |
| F4 (Info) — accept_worker_running 返回值来源 | **无变化** | 仍正确。 |
| F5 (Info) — request_active_cancel 幂等路径 | **无变化** | 仍正确。 |
| F6 (Info) — Schema DDL dispatching worker refs paired | **无变化** | 仍正确。 |
| F7 (Info) — 测试覆盖度 | **已增强** | +1 regression test，34 passed。 |
| F8 (Info) — 弱类型守卫 | **无变化** | 仍通过。 |
| F9 (Info) — 非目标遵守 | **无变化** | 仍遵守。 |

## Summary

| Severity | Count | Blocks? |
|---|---|---|
| Medium | 1 (F1, P5-S3 handoff risk) | No |
| Low | 0 | — |
| Info | 0 new | — |

## Verdict

**No new blockers. Fix 完整正确。Slice P5-S1 可以接受。**

F2 / DS M1 已通过三个维度修复：WHERE 子句锁定 `WAITING_FOR_LANE` source status、`waiting_for_lane_at IS NOT NULL` 前置检查、`lane_name` 匹配一致性。专用 mutation result classifier 确保 PENDING 源返回 `INVALID_STATE`。新增 regression test 直接验证 PENDING 不能跳过 waiting_for_lane。

F1（ATTEMPT_RUNNING payload 缺少字段）仍为 P5-S3 handoff risk，已在 fix artifact 中记录。
