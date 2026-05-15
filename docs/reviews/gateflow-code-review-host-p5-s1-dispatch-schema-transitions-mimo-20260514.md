# Code Review: Host Phase 5 P5-S1 Dispatch Schema And Transition Primitives

- gate: Host Phase 5 P5-S1 code review
- reviewer role: independent code reviewer
- review date: 2026-05-14
- diff base: current uncommitted changes vs HEAD
- approved plan: `docs/host/phase5-runinputbuilder-local-dispatch-plan.md`, slice P5-S1

## Review Scope

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
pytest tests/host/test_state_schema.py tests/host/test_run_attempt_transitions.py tests/host/test_weak_typing_guard.py -q => 33 passed
python -m pyright dayu/host tests/host => 0 errors, 0 warnings, 0 informations
git diff --check => passed
```

## Findings

### F1 — ATTEMPT_RUNNING payload 缺少 plan §3.5 要求的四个字段

**Severity**: Medium (plan conformance gap)
**Blocks slice acceptance**: No (设计约束，非实现 bug)

**Evidence**:

Plan §3.5 要求 `ATTEMPT_RUNNING` payload 必须包含：

```text
attempt_id
execution_id
dispatch_record_id
worker_kind
execution_target
local_worker_id      ← 缺失
worker_accepted_at   ← 缺失
lane_name            ← 缺失
lane_claim_id        ← 缺失
```

实际 payload (`run_transition.py:_attempt_running_event_request`, diff line ~308-333)：

```python
payload_json={
    "attempt_id": attempt.attempt_id,
    "execution_id": attempt.execution_id,
    "dispatch_record_id": dispatch_record.dispatch_record_id,
    "worker_kind": dispatch_record.worker_kind.value,
    "execution_target": dispatch_record.execution_target,
    "reason": request.worker_accept_reason,
}
```

`local_worker_id` 由 `LocalProxy` 在 P5-S3 提供；`lane_name` / `lane_claim_id` 由 `DispatchScheduler` 在 P5-S3 写入 dispatch record 诊断字段。P5-S1 的 `AcceptWorkerRunningInput` 没有这些字段，因为 scheduler / local proxy 尚未实现。

**Impact**: `ATTEMPT_RUNNING` payload 在 P5-S1 产出时不完整。P5-S3 实现 scheduler / local proxy 后需要补充这些字段到 payload 和 input dataclass。如果 P5-S3 不回头修改此处，下游消费方会看到缺失字段。

**Recommendation**: 在 implementation artifact 的 Residual Risks 中明确记录此 gap，并标注 P5-S3 必须回头扩展 `AcceptWorkerRunningInput` 和 `_attempt_running_event_request`。或者，P5-S1 可选择将 `AcceptWorkerRunningInput` 的 `worker_accept_reason` 扩展为包含 lane / worker 身份的 optional 字段，为 P5-S3 预留接口，但这超出当前 slice scope。

---

### F2 — `mark_dispatching_after_lane_row` WHERE 子句未直接检查 source status

**Severity**: Low (防御性编码观察)
**Blocks slice acceptance**: No

**Evidence**:

`state.py:mark_dispatching_after_lane_row` 的 UPDATE WHERE 子句检查：

```sql
WHERE attempt_id = ?
  AND status IN (?, ?)          -- PENDING, WAITING_FOR_LANE
  AND lane_claim_id IS NULL
  AND lane_owner_id IS NULL
  AND lane_acquired_at IS NULL
  AND dispatching_at IS NULL
  AND worker_accept_event_id IS NULL
  AND cancelled_event_id IS NULL
```

此 WHERE 子句通过诊断字段 NULL 模式间接排除 DISPATCHING / CANCELLED 状态，而非直接检查 `status IN ('pending', 'waiting_for_lane')`。虽然 SQLite CHECK 约束确保 CANCELLED 记录的 `cancelled_event_id IS NOT NULL`，从而不会被此 WHERE 匹配，但依赖 CHECK 约束作为 UPDATE 正确性的隐式保证不够透明。

**Impact**: 当前正确，因为 CHECK 约束兜底。但如果未来 schema 演进放宽了 CANCELLED 的 nullability 约束，此 WHERE 子句可能意外匹配 CANCELLED 记录。

**Recommendation**: 当前可接受，因为 schema 版本固定且 CHECK 约束明确。P5-S3 后续如需修改此函数，应同时审视 WHERE 子句的 source status 检查。

---

### F3 — `_dispatch_record_is_direct_cancelable` 与 `cancel_starting_dispatch_record_row` 的语义一致性

**Severity**: Info (positive observation)
**Blocks slice acceptance**: No

**Evidence**:

`_dispatch_record_is_direct_cancelable` 在 `run_transition.py` 中判断 pre-worker cancel 窗口：

```python
if dispatch_record.status in (
    DispatchRecordStatus.PENDING,
    DispatchRecordStatus.WAITING_FOR_LANE,
):
    return True
return (
    dispatch_record.status == DispatchRecordStatus.DISPATCHING
    and dispatch_record.worker_accepted_at is None
    and dispatch_record.worker_accept_event_id is None
    and dispatch_record.worker_accept_event_sequence is None
)
```

`cancel_starting_dispatch_record_row` 在 `state.py` 中的 WHERE 子句：

```sql
WHERE attempt_id = ?
  AND status IN (?, ?, ?)       -- PENDING, WAITING_FOR_LANE, DISPATCHING
  AND worker_accepted_at IS NULL
  AND worker_accept_event_id IS NULL
  AND worker_accept_event_sequence IS NULL
```

两者语义完全对齐：PENDING / WAITING_FOR_LANE 无条件 cancelable，DISPATCHING 需要 worker accept refs 全空。

**Impact**: 无。两个层面的判断一致，且 `cancel_predispatch_starting_in_transaction` 先调用 `_dispatch_record_is_direct_cancelable` 做 Python 层检查，再由 `cancel_starting_dispatch_record_row` 的 WHERE 子句做 SQLite 层 CAS 保护。

---

### F4 — `accept_worker_running_in_transaction` 返回的 dispatch_record 取自 mutation result 而非重新读取

**Severity**: Info (positive observation)
**Blocks slice acceptance**: No

**Evidence**:

```python
dispatch_result = mark_dispatch_worker_accepted_row(...)
dispatch_result = _require_dispatch_record_mutation_updated(
    dispatch_result,
    mutation_name="record dispatch worker accept refs",
)
return RunTransitionResult(
    status=attempt_result.status,
    run=read_run_by_id(transaction, run.run_id),
    attempt=attempt_result.row,
    dispatch_record=dispatch_result.row,  # ← 来自 mutation result
)
```

`dispatch_result.row` 由 `_dispatch_record_mutation_result_for_dispatching` 内部的 `read_dispatch_record_by_attempt_id` 读取，是 mutation 后的最新状态。这与 `run=read_run_by_id(transaction, run.run_id)` 的重新读取模式一致，确保返回值反映事务内的最新写入。

**Impact**: 无问题。

---

### F5 — `request_active_attempt_cancel_in_transaction` 幂等路径的 attempt / dispatch_record 读取

**Severity**: Info (positive observation)
**Blocks slice acceptance**: No

**Evidence**:

```python
if run.status == RunStatus.CANCELLING and run.current_attempt_id is not None:
    attempt = read_attempt_by_id(transaction, run.current_attempt_id)
    return RunTransitionResult(
        status=StateMutationStatus.UPDATED,
        run=run,
        attempt=attempt,
        dispatch_record=_read_dispatch_for_attempt(transaction, attempt),
    )
```

幂等路径返回 `UPDATED` 而非专门的幂等状态码，但这是与现有 `cancel_queued_in_transaction` 等函数的惯例一致的。`_read_dispatch_for_attempt` 安全处理 `attempt is None` 的情况。

**Impact**: 无问题。测试 `test_active_cancel_appends_run_cancelling_once` 验证了重复调用的幂等行为。

---

### F6 — Schema DDL `dispatching` 状态的 worker accept refs 子句设计

**Severity**: Info (positive observation)
**Blocks slice acceptance**: No

**Evidence**:

Schema CHECK 约束对 `dispatching` 状态的 worker accept refs 处理：

```sql
(status = 'dispatching'
  ...
  AND (
    (worker_accepted_at IS NULL
      AND worker_accept_event_id IS NULL
      AND worker_accept_event_sequence IS NULL)
    OR
    (worker_accepted_at IS NOT NULL
      AND worker_accept_event_id IS NOT NULL
      AND worker_accept_event_sequence IS NOT NULL)
  ))
```

正确实现了"要么全空要么全有"的 paired 约束，与 `state.py:_require_dispatch_worker_accept_refs_paired` 的 Python 层校验完全对齐。

**Impact**: 无问题。DDL 层和 Python 层双重保护。

---

### F7 — 测试覆盖度评估

**Severity**: Info (positive observation)
**Blocks slice acceptance**: No

**Evidence**:

P5-S1 测试覆盖了 plan 要求的所有测试项：

| Plan 要求 | 测试函数 | 状态 |
|---|---|---|
| schema check 接受四个 dispatch 状态 | `test_dispatch_record_status_check_allows_phase5_statuses` | ✓ |
| 验证每个状态的 nullability | `test_dispatch_record_nullability_rules_reject_invalid_shapes` + DDL CHECK | ✓ |
| pending -> waiting -> dispatching -> accepted refs | `test_dispatch_record_waiting_dispatching_and_worker_accept_refs` | ✓ |
| pending / waiting / pre-accept dispatching direct cancel | `test_cancel_predispatch_starting_supports_all_pre_accept_dispatch_statuses` | ✓ |
| dispatching + worker accepted refs 不允许 direct cancel | `test_cancel_predispatch_rejects_dispatching_after_worker_accept_refs` | ✓ |
| ATTEMPT_RUNNING CAS 只允许 STARTING -> RUNNING | `test_mark_attempt_running_only_allows_starting_source` | ✓ |
| active cancel 只追加一次 RUN_CANCELLING | `test_active_cancel_appends_run_cancelling_once` | ✓ |

所有测试函数和辅助函数均提供完整中文 docstring。测试通过 pyright（0 errors）。

---

### F8 — 弱类型守卫测试未修改

**Severity**: Info
**Blocks slice acceptance**: No

**Evidence**: `tests/host/test_weak_typing_guard.py` 未修改，但作为 P5-S1 validation suite 的一部分被运行且通过（33 passed 包含此文件的测试）。新增代码无 `Any` / `object` / 无注解 / 裸容器违规。

---

### F9 — 非目标遵守情况

**Severity**: Info (positive observation)
**Blocks slice acceptance**: No

**Evidence**:

| 非目标项 | 遵守情况 |
|---|---|
| 不修改 Engine public contract | ✓ 未修改 `dayu/engine/` |
| 不引入旧 schema 兼容读取 | ✓ 按 fresh schema 起库 |
| 不把 dispatch record 当 lease / fencing / owner truth | ✓ docstring 和代码注释明确声明 |
| 不修改 scheduler / RunInputBuilder / LocalProxy | ✓ 仅修改 P5-S1 允许的三个文件 |
| 不修改 README / implementation-control | ✓ 未修改 |

---

## Summary

| Severity | Count | Blocks? |
|---|---|---|
| Medium | 1 (F1) | No |
| Low | 1 (F2) | No |
| Info | 7 (F3-F9) | No |

## Verdict

**No blocking findings. Slice P5-S1 可以接受。**

F1 是 plan conformance 而非实现 bug：`ATTEMPT_RUNNING` payload 缺少四个字段是因为 scheduler / local proxy 尚未实现（P5-S3 scope），`AcceptWorkerRunningInput` 没有这些字段来源。建议在 implementation artifact 的 Residual Risks 中补充此 gap 记录，确保 P5-S3 回头扩展 payload。

F2 是防御性编码观察，当前 SQLite CHECK 约束兜底，不构成正确性风险。

实现质量良好：
- Schema DDL nullability 约束与 Python 层校验完全对齐，双重保护。
- CAS mutation 函数遵循项目既有模式，precondition 检查完整。
- `cancel_predispatch_starting_in_transaction` 泛化正确，`_dispatch_record_is_direct_cancelable` 语义清晰。
- `request_active_attempt_cancel_in_transaction` 幂等路径正确，不重复追加 `RUN_CANCELLING`。
- 测试覆盖 plan P5-S1 所有测试要求，pyright 0 errors，无弱类型回归。
