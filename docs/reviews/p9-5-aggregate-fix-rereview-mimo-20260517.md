# P9.5 Aggregate Deepreview Accepted-Finding Fix Re-Review — AgentMiMo

## Review Context

- Reviewer: AgentMiMo
- Scope: MiMo aggregate deepreview accepted-finding fix（F1/F2/F3）+ AgentDS artifact 日期修正
- 原始 artifact: `docs/reviews/p9-5-aggregate-deepreview-mimo-20260517.md`
- DS artifact: `docs/reviews/p9-5-aggregate-deepreview-ds-20260517.md`
- 验证结果: pytest 77 passed (targeted) + 1068 passed (full)；pyright 0 errors；git diff --check clean

## Verdict: PASS

F1、F2、F3 修复正确、完整，测试覆盖关键行为，README 同步更新。DS artifact 日期已修正。无 blocking/high/medium/low finding。

---

## F1 — EventLog canonical inline payload size 从 store policy 注入

**原 finding**: `event_log.py:45` — `_MAX_CANONICAL_INLINE_PAYLOAD_BYTES` 硬编码为 `_DEFAULT_PAYLOAD_INLINE_THRESHOLD_BYTES`（65536），不读取用户配置的 `PayloadStoragePolicy.payload_inline_threshold_bytes`。

**Severity: MEDIUM → FIXED**

### 修复验证

**移除硬编码常量**（`event_log.py` diff）:
```python
# 删除:
-from dayu.host.durable.options import (
-    _DEFAULT_PAYLOAD_INLINE_THRESHOLD_BYTES as _DEFAULT_INLINE_PAYLOAD_MAX_BYTES,
-)
-_MAX_CANONICAL_INLINE_PAYLOAD_BYTES = _DEFAULT_INLINE_PAYLOAD_MAX_BYTES

# 不再有模块级常量
```

**注入链路**（`transaction.py` + `connection.py` diff）:
```
HostDurableStoreOptions.payload_policy.payload_inline_threshold_bytes
  → HostDurableStore.__init__（connection.py:51-53）
    → HostTransactionRunner.__init__(payload_inline_threshold_bytes=)（transaction.py:221）
      → HostTransaction.__init__(payload_inline_threshold_bytes=)（transaction.py:137）
        → HostTransaction.payload_inline_threshold_bytes property（transaction.py:150-156）
```

**使用注入值**（`event_log.py:597`）:
```python
def _validate_canonical_inline_payload_size(
    transaction: HostTransaction,  # ← 新增参数
    request: EventLogAppendRequest,
    encoded: _EncodedAppendRequest,
) -> None:
    # ...
    if payload_size_bytes <= transaction.payload_inline_threshold_bytes:  # ← 从 transaction 读取
        return
```

**调用点更新**（`event_log.py:249`）:
```python
-    _validate_canonical_inline_payload_size(request, encoded)
+    _validate_canonical_inline_payload_size(transaction, request, encoded)
```

**测试**（`test_event_log_store.py:181-209`）:
- `test_canonical_inline_payload_limit_uses_store_policy`：使用 `_CUSTOM_INLINE_THRESHOLD_BYTES = 8`，构造 9 字节 payload（`"123456789"`），验证 `HostPayloadReferenceError` 被抛出
- 通过 `PayloadStoragePolicy(payload_inline_threshold_bytes=8)` 注入自定义阈值

**README 同步**（`dayu/host/README.md:129`）:
```
-受当前 payload inline 阈值约束
+受当前 durable store 注入的 payload inline 阈值约束
```

**tests/README.md 同步**（line 131）:
```
-canonical fact inline payload size guard
+canonical fact inline payload size guard 与 store policy 注入
```

**判定**: 修复完整。硬编码常量已移除，阈值通过 `HostTransaction` 从 `PayloadStoragePolicy` 注入，测试验证自定义阈值生效，README 同步更新。

---

## F2 — dispatch CAS 补齐 `cancelled_event_sequence IS NULL`

**原 finding**: `state.py:3076,3233` — `mark_dispatch_waiting_for_lane_row` 和 `mark_dispatch_worker_accepted_row` WHERE 子句只检查 `cancelled_event_id IS NULL`，缺少 `cancelled_event_sequence IS NULL`。

**Severity: LOW → FIXED**

### 修复验证

**`mark_dispatch_waiting_for_lane_row`**（`state.py:3094-3095`）:
```sql
WHERE attempt_id = ?
  AND status = ?
  AND waiting_for_lane_at IS NULL
  AND lane_name IS NULL
  AND lane_claim_id IS NULL
  AND lane_owner_id IS NULL
  AND lane_acquired_at IS NULL
  AND dispatching_at IS NULL
  AND worker_accept_event_id IS NULL
  AND cancelled_event_id IS NULL
  AND cancelled_event_sequence IS NULL  -- ← 新增
```

**`mark_dispatch_worker_accepted_row`**（`state.py:3247-3248`）:
```sql
WHERE attempt_id = ?
  AND status = ?
  AND worker_accepted_at IS NULL
  AND worker_accept_event_id IS NULL
  AND worker_accept_event_sequence IS NULL
  AND cancelled_event_id IS NULL
  AND cancelled_event_sequence IS NULL  -- ← 新增
```

**与 `mark_dispatch_dispatching_row`（state.py:3182-3183）对齐**: 三个函数现在都同时检查 `cancelled_event_id IS NULL` 和 `cancelled_event_sequence IS NULL`。

**测试**: `test_run_attempt_transitions.py` 无变更。现有 `test_cancel_starting_dispatch_record_absorbs_already_cancelled` 等测试覆盖 cancel CAS 行为。此修复是 defense-in-depth 对齐，不改变功能行为（`cancelled_event_id` 和 `cancelled_event_sequence` 在 cancel 流程中同时写入）。

**判定**: 修复正确。WHERE 子句补齐，三个 dispatch 状态转换函数 defense-in-depth 对称。

---

## F3 — TruncationManager 截断后超限时清理 cursor

**原 finding**: `tool_runtime.py:1393-1404` — 截断结果仍超过 LLM inline limit 时 early return 不清理已创建的 cursor。

**Severity: LOW → FIXED**

### 修复验证

**替换失败路径**（`tool_runtime.py:1377-1378`）:
```python
if truncated_value is None:
    self._cursors.pop(cursor.cursor_id, None)  # ← 新增：清理 cursor
    return TruncationAppliedOutcome(
        outcome=_truncation_failure(
            _TRUNCATION_UNSUPPORTED_REASON,
            "tool result target cannot be replaced safely",
        ),
        cursor_hint=None,
        fact=None,
    )
```

**超限路径**（`tool_runtime.py:1398`）:
```python
if (
    _tool_outcome_inline_size_bytes(truncated_outcome)
    > _MAX_LLM_INLINE_TOOL_RESULT_BYTES
):
    self._cursors.pop(cursor.cursor_id, None)  # ← 新增：清理 cursor
    return TruncationAppliedOutcome(
        outcome=_truncation_failure(
            _TOOL_RUNTIME_RESULT_TOO_LARGE_REASON,
            "truncated tool result exceeded LLM inline size limit",
        ),
        cursor_hint=None,
        fact=None,
    )
```

**测试**（`test_toolruntime_executor.py:499-532`）:
- `test_truncation_discards_cursor_when_inline_result_still_too_large`：
  - 构造 spec `max_chars=70000`，输入 `"x" * 70010`
  - 截断后仍超限（70000 > `_MAX_LLM_INLINE_TOOL_RESULT_BYTES`）
  - 断言 `isinstance(applied.outcome, ToolFailedOutcome)`
  - 断言 `applied.cursor_hint is None`
  - 断言 `manager._cursors == {}` — **验证 cursor 已清理**

**README 同步**（`dayu/host/README.md:100`）:
```
-超限时返回普通工具错误，不进入 wait / recovery。
+超限时返回普通工具错误，不进入 wait / recovery，且不会保留未返回的截断 cursor。
```

**tests/README.md 同步**（line 131）:
```
+截断后仍超限时 cursor cleanup
```

**判定**: 修复完整。两个 failure 路径都清理 cursor，测试直接断言 `manager._cursors == {}`，README 同步更新。

---

## 设计真源合规性

逐项检查 `docs/host/design.md` 约束：

| 约束 | F1 | F2 | F3 |
|------|----|----|-----|
| Host 是治理真源 | ✓ 阈值从 Host options 注入 | ✓ CAS 守卫 dispatch 状态 | ✓ cursor 生命周期在 ToolRuntime 内 |
| 禁止反向依赖 | ✓ event_log 不导入 options 常量 | ✓ state.py 无新依赖 | ✓ tool_runtime.py 无新依赖 |
| 禁止 God object | ✓ 阈值通过 transaction 传递 | ✓ WHERE 子句局部修改 | ✓ cursor cleanup 局部修改 |
| 禁止魔法数字/字符串 | ✓ 移除硬编码常量 | ✓ — | ✓ — |
| 类型/docstring 约束 | ✓ `payload_inline_threshold_bytes: int` 有 docstring | ✓ — | ✓ — |

**判定**: 无设计真源违反。

---

## DS Artifact 日期修正

`docs/reviews/p9-5-aggregate-deepreview-ds-20260517.md` 当前日期为 `2026-05-17`，与文件名一致。日期修正已完成。

---

## Summary

| Finding | 修复项 | 验证 | 判定 |
|---------|--------|------|------|
| F1 | EventLog payload 阈值从 store policy 注入 | 移除硬编码常量 → HostTransaction 注入链路 → 测试验证自定义阈值 → README 同步 | FIXED |
| F2 | dispatch CAS 补齐 cancelled_event_sequence | 两个 WHERE 子句补充 IS NULL 检查 → 与 mark_dispatch_dispatching_row 对齐 | FIXED |
| F3 | 截断后超限 cursor cleanup | 两个 failure 路径 pop cursor → 测试断言 `_cursors == {}` → README 同步 | FIXED |

## 结论

三个 accepted findings 修复正确、完整。注入链路清晰（`PayloadStoragePolicy` → `HostTransactionRunner` → `HostTransaction` → `event_log`），CAS defense-in-depth 对称，cursor 生命周期不泄漏。1068 tests passed，pyright 0 errors。可以接受。
