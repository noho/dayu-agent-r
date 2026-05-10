# PR #40 P8 Correctness Final Convergence Re-Review

## Scope

- **Mode**: Narrow re-review of accepted P8 correctness fixes
- **PR**: #40 — `[codex] Host P8 durable attempt governance`
- **Branch**: `migration/host-p8-attempt-lease-recovery`
- **Baseline reviews**: `pr-40-review-20260510-2242.md`、`pr-40-review-20260510-2247.md`
- **Output file**: `docs/reviews/pr-40-review-20260510-2242-2247-fix-rereview.md`
- **本次 re-review 范围**: 只覆盖 10 项 accepted P8 correctness fixes，不覆盖 deferred 项

## 总结论

**PASSED**

全部 10 项 accepted findings 均已正确修复。未发现新 blocker。deferred 项归属正确。验证命令全部通过。

## 逐项 Verdict

### 1. F11/F12/2247-1: durable 路径 terminal draft 路由 — PASSED

**修复内容**:

- 新增 `_append_terminal_draft_for_active_attempt` 方法（`_run_harness.py:1711`），统一判断 `_can_atomic_terminal_close` 后路由到 `_append_terminal_and_close`（durable supervisor 路径）或 `_scope_appender().append()`（非 supervisor 测试路径）。
- `_compact_or_fail` 三条失败路径（retry limit / trace missing / decision FAILED）全部从 `_scope_appender().append(terminal_draft)` 改为 `_append_terminal_draft_for_active_attempt`。
- `_append_compact_exception_failure` 同步适配。
- `_append_missing_terminal_failure_if_needed` 同步适配。
- `_append_worker_failure_if_needed` 从内联 supervisor 逻辑重构为复用 `_append_terminal_draft_for_active_attempt`。

**验证**:

- `grep '_scope_appender().append(.*terminal'` — 无匹配，确认无残留。
- `_compact_or_fail` 签名新增 `active_attempt` 参数，所有调用点已正确传入。
- `_append_terminal_draft_for_active_attempt` 的 fallback 路径（`_scope_appender().append(draft)`）仅在 `active_attempt is None` 或 `not _can_atomic_terminal_close` 时触发，对应非 supervisor 测试路径，`PlainRunEventAppender` 不 guard terminal types，行为正确。
- 新增测试 `test_verify_owner_with_null_owner_hash_returns_typed_fence`（F8 相关但覆盖同一代码区域）。

**结论**: terminal draft 在 durable 路径下全部走 `append_terminal_and_close` 原子收口，无 `_scope_appender().append(terminal draft)` 残留。

### 2. F13/2247-2: durable memory repair 按 run 分组 — PASSED

**修复内容**:

- 新增 `_group_terminal_canonical_events_by_run` 方法（`_conversation_memory_durable.py:420`），按 `run_id` 分组 canonical events，只返回含 terminal event 的 run 批次。
- `_repair_missing_session_snapshots_locked` 从 `self._project_in_tx(tx=tx, events=canonical_events)` 改为逐 run batch 调用 `self._project_in_tx(tx=tx, events=run_events)`。
- 无 terminal event 的 run 批次被过滤（`if not terminal_run_batches: continue`），与 observer 路径语义一致。

**验证**:

- 分组逻辑正确：按 `run_id` 分组 → 过滤 `_has_terminal_event` → 保留首次出现顺序。
- 新增测试 `test_startup_reconcile_repairs_multi_run_session_by_run_batches`：构造两轮 run session，删除 snapshot，repair 后断言两轮 raw turns 均保留。
- `_project_raw_turn` 契约（"同一 run 事件"）不再被违反。

**结论**: repair 路径不再把跨 run canonical events 作为单 run batch 传入投影，多 run session 的 raw turns 全部保留。

### 3. F14: mark_stale_or_lost 非 orphan CAS 加入 lease_expires_at 约束 — PASSED

**修复内容**:

- 非 orphan 路径 WHERE 子句从 `state IN ('running', 'created') AND fencing_token = ?` 改为 `state = ? AND fencing_token = ? AND lease_expires_at IS NOT NULL AND lease_expires_at <= ?`。
- orphan 路径（`source_fencing_token is None`）保持不变，仍匹配 `state IN ('running', 'created') AND fencing_token IS NULL`。
- 方法签名 `source_fencing_token` 从 `int | None` 改为 `FencingToken | None`，内部使用 `.value`。

**验证**:

- SQL 条件 `lease_expires_at <= now` 确保只收口 lease 确实过期的 attempt。
- renew-after-scan-before-mark 场景：renew 把 `lease_expires_at` 刷新到未来 → `lease_expires_at <= now` 不成立 → CAS 返回 `NOOP_TERMINAL` → 不误标 LOST。
- 新增测试 `test_recover_noop_when_candidate_lease_is_renewed_before_mark`：通过 monkeypatch 在 `list_recovery_candidates` 返回前 renew lease，验证 `NOOP_TERMINAL`。

**结论**: renew-after-scan-before-mark 竞态不会误标 LOST。

### 4. F17: expired cursor 路径先写 EventLog 再 remove cursor — PASSED

**修复内容**:

- `_fetch_more` 过期路径从先 `_remove_cursor` 再 `_append_cursor_expired` 改为先 `_append_cursor_expired` + `_fetch_failure` 成功后，再 `_remove_cursor`。
- 代码从 `self._remove_cursor(record.cursor)` 移到 `await self._append_cursor_expired(...)` 和 `await self._fetch_failure(...)` 成功之后。

**验证**:

- 新增测试 `test_fetch_more_expired_fencing_preserves_old_cursor`：`_append_cursor_expired` 被 fenced 时，旧 cursor 仍在 maps 中。
- "先写 EventLog 再变内存" 不变量得到遵守。

**结论**: expired cursor 路径不再违反 EventLog-before-memory 不变量。

### 5. F18: 初始截断 cursor pure build + deferred commit — PASSED

**修复内容**:

- `_store_cursor` 重命名为 `_build_cursor`，docstring 更新为"纯构建初始截断 cursor，不写入内存 maps"。
- 调用方 `_build_cursor` 后先 append `TOOL_RESULT_TRUNCATED` + `TOOL_CURSOR_ISSUED`，全部成功后调用 `_commit_cursor_creation` 注册 cursor。
- `_store_cursor_from_record`（dead code）和 `_create_cursor`（build+commit 一体化旧方法）全部删除。

**验证**:

- `grep '_store_cursor_from_record\|_create_cursor'` — 无匹配，确认已删除。
- 新增断言 `assert runtime._records_by_cursor == {}` 在 fencing 测试中，确认 fencing 时无孤儿 cursor。
- `_build_cursor` docstring 明确说明调用方必须先写 EventLog 再 commit。

**结论**: 初始截断路径采用 pure build + deferred commit，fencing race 下无孤儿 cursor。

### 6. F8: _diagnose_fence 对 None owner_token_hash 返回 typed FENCED — PASSED

**修复内容**:

- `_run_state_store.py:1162` 从 `if not hmac.compare_digest(current_hash, expected_hash)` 改为 `if not isinstance(current_hash, str) or not hmac.compare_digest(current_hash, expected_hash)`。

**验证**:

- `current_hash is None` 时 `not isinstance(None, str)` 为 `True`，短路求值不进入 `hmac.compare_digest`，直接返回 `OWNER_MISMATCH` typed result。
- 新增测试 `test_verify_owner_with_null_owner_hash_returns_typed_fence`：设置 `owner_token_hash = NULL`，验证 `AttemptFencingReason.OWNER_MISMATCH`。

**结论**: `hmac.compare_digest` 不再收到 `None` 参数导致 `TypeError`。

### 7. F16: worker failure atomic terminal close 后清空 active attempt — PASSED (with minor residual)

**修复内容**:

- `_append_worker_failure_if_needed` 成功后新增 `if terminal_seen and current_active_attempt is not None and self._can_atomic_terminal_close(current_active_attempt): current_active_attempt = None`。
- `_append_compact_exception_failure` 调用处同步新增相同逻辑。
- `_compact_or_fail` 返回 `None` 的正常路径同步新增相同逻辑。
- `_append_overflow_acquire_failure_terminal` 调用处同步新增相同逻辑。

**验证**:

- `_append_terminal_and_close` 在单一事务内完成 owner verify + terminal append + attempt close，之后 attempt 已是终态。
- 设置 `current_active_attempt = None` 防止外层 finally 的 `_finish_attempt_if_durable` 二次 close（CAS miss + warning 日志）。

**minor residual**: compact exception 路径中，`_append_compact_exception_failure` 内部调用 `_append_terminal_draft_for_active_attempt` 已完成 atomic close，但外层 caller 的 `terminal_seen` 条件检查可能在 `terminal_seen=False` 时跳过 `current_active_attempt = None`（具体取决于 `_append_compact_exception_failure` 返回值）。此时 `_finish_attempt_if_durable` 会被调用但因 attempt 已终态而成为 CAS miss no-op。**非 blocker**：无数据损坏，仅浪费一次 DB round-trip + warning 日志。可作为 P9 cleanup。

**结论**: 主要路径（worker failure、正常 compact failure、overflow acquire failure）均正确清空 active attempt。异常路径有 minor residual 但不影响正确性。

### 8. F22: _build_busy_result 填充 current_fencing_token — PASSED

**修复内容**:

- SELECT 从 `SELECT state, owner_id, lease_expires_at` 改为 `SELECT state, owner_id, fencing_token, lease_expires_at`。
- 构造 `AttemptLeaseResult` 时新增 `current_fencing_token` 字段，从 `row["fencing_token"]` 解析。

**验证**:

- 新增测试 `test_busy_acquire_result_includes_current_fencing_token`：验证 BUSY 结果的 `current_fencing_token` 等于首次 acquire 获得的 `fencing_token`。

**结论**: BUSY 诊断结果不再丢失 `current_fencing_token`。

### 9. 2247-7: mark_stale_or_lost 参数改为 FencingToken | None — PASSED

**修复内容**:

- 签名从 `source_fencing_token: int | None` 改为 `source_fencing_token: FencingToken | None`。
- 非 orphan 路径内部使用 `source_fencing_token.value` 传入 SQL。
- 调用方（`_attempt_supervisor.py:826,844`）从 `candidate.fencing_token.value` 改为直接传 `candidate.fencing_token`。

**验证**:

- `FencingToken.__post_init__` 校验 `value > 0`，类型系统阻止传入非正整数。
- orphan 路径（`source_fencing_token is None`）行为不变。

**结论**: 类型契约统一，调用方不再绕过 `FencingToken` 校验。

### 10. 2247-8: close_terminal docstring 补充 LOST — PASSED

**修复内容**:

- docstring 从 `(SUCCEEDED/FAILED/CANCELLED/SUSPENDED)` 改为 `(SUCCEEDED/FAILED/CANCELLED/SUSPENDED/LOST)`。

**验证**:

- `_ATTEMPT_CLOSE_TERMINAL_VALID_STATES` 包含 `LOST`，docstring 与运行时行为一致。

**结论**: docstring 完整列出全部合法终态。

## 新 Blocker 检查

**未发现新 blocker。**

所有修改遵循已建立的 `_append_terminal_draft_for_active_attempt` 统一模式，无引入新不一致。

## Deferred 项归属确认

| 项 | 归属 | 确认 |
|---|---|---|
| `fetch_more` 专属 RunEventType + multi-fact partial risk | P8.5 | 正确 — 事件模型 root cause 与 batch 原子性需统一裁决 |
| repair O(N×M) | P9 / capacity | 正确 — SQL 优化需索引 + 查询改写 |
| sync trace I/O | 后续 owner | 正确 — 非正确性问题 |
| payload size | 后续 owner | 正确 — 监控优先 |
| damaged snapshot repair | 后续 owner | 正确 — 运维边界 |
| coverage-only gaps (F4/F5/F6/F7) | 后续 owner | 正确 — 测试质量补充 |
| `_compact_or_fail` exception path minor residual | P9 cleanup | 正确 — CAS miss no-op，无数据损坏 |

## 验证命令与结果

```
$ source .venv/bin/activate && pytest tests/host -q
348 passed, 1 warning in 2.64s

$ source .venv/bin/activate && python -m pyright dayu/host tests/host utils
0 errors, 0 warnings, 0 informations

$ python utils/smoke_host_p8_attempt_lease.py
7 scenarios passed

$ git diff --check
(clean)
```

## 代码变更摘要

| 文件 | 变更 |
|---|---|
| `_attempt_supervisor.py` | `mark_stale_or_lost` 调用方改传 `FencingToken` |
| `_conversation_memory_durable.py` | 新增 `_group_terminal_canonical_events_by_run`；repair 路径逐 run batch 投影 |
| `_run_harness.py` | 新增 `_append_terminal_draft_for_active_attempt`；terminal draft 全部路由到原子收口；`current_active_attempt` 清空逻辑；`_compact_or_fail` / `_append_compact_exception_failure` / `_append_missing_terminal_failure_if_needed` 新增 `active_attempt` 参数 |
| `_run_state_store.py` | `mark_stale_or_lost` 非 orphan CAS 加 `lease_expires_at` 约束；签名改 `FencingToken \| None`；`_diagnose_fence` 守卫 `None` hash；`_build_busy_result` 填充 `current_fencing_token`；`close_terminal` docstring 补 `LOST` |
| `_tool_runtime.py` | `_store_cursor` → `_build_cursor`（pure build）；`_commit_cursor_creation` 延迟到 EventLog 成功后；expired cursor 先写 EventLog 再 remove；删除 `_store_cursor_from_record` 和 `_create_cursor` |
| `test_phase8_attempt_fencing.py` | 新增 F8、F22 回归测试 |
| `test_phase8_attempt_recovery.py` | 新增 F14 renew-after-scan 回归测试 |
| `test_phase8_durable_memory_recovery.py` | 新增 F13 多 run session repair 回归测试 |
| `test_phase8_tool_runtime_fencing.py` | 新增 F17 expired fencing 测试；F18 fencing 断言 cursor maps 为空；新增 `_FencingOnExpiredAppender` |
