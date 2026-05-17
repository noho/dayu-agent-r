# P9.5 Aggregate Accepted-Finding Fix Re-Review — AgentDS

**Review scope**: P9.5 aggregate accepted-finding fix（MiMo F1/F2/F3）独立复核
**Base artifact**: `docs/reviews/p9-5-aggregate-deepreview-mimo-20260517.md`
**Fix scope**: `event_log.py`, `transaction.py`, `connection.py`, `state.py`, `tool_runtime.py`, `dayu/host/README.md`, `tests/README.md`, 相关 tests, DS artifact 日期
**Reviewer**: AgentDS
**Date**: 2026-05-17
**Verdict**: **PASS** — 0 blocking, 0 high, 0 medium, 0 low findings

---

## F1 复核 — EventLog payload 阈值注入

**原 finding**: `event_log.py:45` — `_MAX_CANONICAL_INLINE_PAYLOAD_BYTES` 硬编码为 `_DEFAULT_PAYLOAD_INLINE_THRESHOLD_BYTES`，不读用户 `PayloadStoragePolicy` 配置。

**修复**: 移除模块级硬编码常量与 `_DEFAULT_PAYLOAD_INLINE_THRESHOLD_BYTES` import。注入链路: `PayloadStoragePolicy.payload_inline_threshold_bytes` → `HostDurableStore` → `HostTransactionRunner` → `HostTransaction.payload_inline_threshold_bytes` → `_validate_canonical_inline_payload_size`。

**独立验证**:
- `event_log.py`: import 与 `_MAX_CANONICAL_INLINE_PAYLOAD_BYTES` 已删除；`_validate_canonical_inline_payload_size` 签名新增 `transaction: HostTransaction`，用 `transaction.payload_inline_threshold_bytes` 比较 ✓
- `transaction.py`: `HostTransaction.__init__` 新增 `payload_inline_threshold_bytes: int` keyword-only 参数与 `@property`；`HostTransactionRunner` 同；`run_write` 与 `run_read` 均透传 ✓
- `connection.py:48-54`: `HostTransactionRunner` 构造传入 `options.payload_policy.payload_inline_threshold_bytes` ✓
- 全量 `HostTransactionRunner(` 调用点只有 2 处：`connection.py:48` 与 `test_durable_transaction.py:574`，均已更新 ✓
- 新测试 `test_canonical_inline_payload_limit_uses_store_policy`: custom threshold=8, payload="123456789"(9 bytes), assert `HostPayloadReferenceError` — 证明阈值确实从 store policy 读取 ✓
- 设计约束 "不得在 EventLog primitive 硬编码" 满足 ✓

**判定: FIXED**。

---

## F2 复核 — dispatch CAS 补齐 `cancelled_event_sequence IS NULL`

**原 finding**: `state.py:3076,3233` — `mark_dispatch_waiting_for_lane_row` 和 `mark_dispatch_worker_accepted_row` 只检查 `cancelled_event_id IS NULL`，缺少 `cancelled_event_sequence IS NULL`。

**修复**: 两个 WHERE 子句各新增 `AND cancelled_event_sequence IS NULL`。

**独立验证**:
- `mark_dispatch_waiting_for_lane_row`（`state.py:3095`）: `AND cancelled_event_sequence IS NULL` 已加入 ✓
- `mark_dispatch_worker_accepted_row`（`state.py:3248`）: `AND cancelled_event_sequence IS NULL` 已加入 ✓
- `mark_dispatch_dispatching_row`（`state.py:3182-3183`）本身已同时检查两者，现三个 CAS 对称 ✓
- cancel 流程中两字段同时写入（`state.py:3293-3305`），功能行为不变，defense-in-depth 对齐 ✓

**判定: FIXED**。

---

## F3 复核 — TruncationManager 截断后 cursor 泄漏

**原 finding**: `tool_runtime.py:1393-1404` — 截断结果仍超 LLM inline limit 时 early return 不清理已创建 cursor。

**修复**: 两处 `_store_cursor` 之后的 early return 路径新增 `self._cursors.pop(cursor.cursor_id, None)`：(1) `truncated_value is None`；(2) inline size 仍超限。

**独立验证**:
- `tool_runtime.py:1378`: `truncated_value is None` 路径新增 pop ✓
- `tool_runtime.py:1398`: 超限路径新增 pop ✓
- `_apply_truncation` 中 `_store_cursor` 只调用一次（line 1361），后共 3 条路径：2 条 failure（均已 pop）、1 条 success（保留 cursor） ✓
- 新测试 `test_truncation_discards_cursor_when_inline_result_still_too_large`: max_chars=70000, input="x"*70010, assert `cursor_hint is None` 且 `manager._cursors == {}` ✓

**判定: FIXED**。

---

## F7 自动消解

原 F7（`event_log.py:46` class 定义前缺少空行）因 `_MAX_CANONICAL_INLINE_PAYLOAD_BYTES` 行被移除而自动消解。当前 `_MIN_EVENT_CURSOR = 0` 与 `class EventClass` 之间有两个空行，符合 PEP 8 E302。

---

## DS Artifact 日期

`docs/reviews/p9-5-aggregate-deepreview-ds-20260517.md` 日期为 `2026-05-17`，与文件名一致。

---

## 结论

F1/F2/F3 修复正确、完整。注入链路从 construction root → primitive 清晰单向，dispatch CAS 对称，cursor 生命周期无泄漏。无新增 regression。77 targeted + 1068 full tests passed，pyright 0 errors，diff check clean。可以接受。
