# S7 Code Review: Compaction Attempt Cancellation 与 Pre-call Recheck

## Scope

- Mode: current changes
- Base: `c893c77f`
- Branch: `phaseflow/host-issues-control`
- Output file: `docs/reviews/wu-semantic-ownership-01-round3-r3-a-s7-code-review-mimo.md`
- Included scope: S7 implementation per `docs/reviews/wu-semantic-ownership-01-round3-r3-a-s7-implementation-codex.md`

## Findings

**PASS — 未发现实质性问题。**

## Review Analysis

### 1. Parent/child cancellation precedence

`_CompactionAttemptCancellationToken` (`dayu/host/compaction_operation.py:563-638`) 的三个读方法均先检查 parent：

- `is_cancelled()`: `if self._parent.is_cancelled(): return True` (line 595)
- `cancel_reason()`: `parent_reason = self._parent.cancel_reason(); if parent_reason is not None: return parent_reason` (line 607-609)
- `requested_at()`: `if self._parent.cancel_reason() is not None: return self._parent.requested_at()` (line 620-621)

Parent cancellation 永终优先于 attempt-local timeout。`request_cancel()` (line 625-638) 只写 `_local_reason` / `_local_requested_at`，不触及 parent。Thread safety 通过 `Lock()` 保护 local state。

### 2. Fresh child token per attempt

`run_compaction_operation()` (line 705-706) 在每次 attempt 循环内创建新 child：

```python
attempt_cancellation_token = _CompactionAttemptCancellationToken(cancellation_token)
```

测试 `test_attempt_timeout_does_not_cancel_parent_or_next_attempt` 验证两个 token 实例不同 (`observed_tokens[0] is not observed_tokens[1]`)，首次 timeout 后第二次 child 未取消 (`is_cancelled() is False`)，parent 未取消。

### 3. Timeout 不污染 parent token

`_CompactionAttemptCancellationToken.request_cancel()` 只写 local state。`_signal_timeout_cancellation` 在 `llm_compaction.py` 中对传入的 token 调用 `request_cancel()`，传入对象现为 attempt child（line 712 传入 `attempt_cancellation_token`），不触及 parent。

测试 `test_parent_cancel_after_timeout_wins_before_retry` 验证：timeout signal 写 child 后，parent 取消优先，child 最终 `cancel_reason() == _PARENT_REASON`，`requested_at() == parent.requested_at()`。

### 4. Provider-call 前 durable recheck

`_ensure_compactor_proposal_active()` (line 1061-1082) 在 manifest recorder 返回后、provider await 前调用：

- Prepared path: line 1015-1018（manifest record 后、`run_prepared_compactor_proposal` 前）
- Non-prepared path: line 1042-1045（`compact()` 前）

对于 proactive path，parent 为 `_DurableRunCancellationToken` (`dispatch.py:876-938`)，其 `is_cancelled()` 通过 `run_read` 重新读取 durable Run status / input cursor。因此 manifest commit 后 Run 失效时，pre-call recheck 通过 child→parent 链触发 durable re-read，阻止 provider。

测试 `test_proactive_compaction_rechecks_durable_state_after_manifest` 使用真实 SQLite store，在 manifest commit 后用独立事务 fail Run，断言 `compactor.calls == 0`。

### 5. Engine diff 为空

`git diff --name-only -- dayu/engine/` 无输出。`llm_compaction.py` 无 diff。`CancellationToken` 协议保持只读观察，未引入 writable Engine contract。

### 6. 无跨 transaction provider await

`_prepare_compactor_proposal()` 中，manifest record（durable write）与 provider call（`await compactor.run_prepared_compactor_proposal` / `await compactor.compact`）不在同一事务内。Provider 调用为独立 await，不持有 SQLite write lock。

### 7. Exception handling consistency

`asyncio.CancelledError` 在 provider await 时检查 `cancellation_token.is_cancelled()`：若已取消则包装为 `_CompactorProposalCancelledError`（含 manifest ref），否则原样 re-raise。这区分了 Host cancellation 与 caller task cancellation（测试 `test_outer_task_cancellation_is_not_reclassified` 验证后者透传 `CancelledError`，不写 parent）。

## Residual Risk

- Provider 物理停止取决于 Engine/runner 对只读 cancellation token 的协作观察，不在 S7 scope。
- `_CompactionAttemptCancellationToken.requested_at()` 存在 parent 在两次调用间取消的理论竞态（`cancel_reason()` 非 None 但 `requested_at()` 返回 parent 时间而非 local），但语义正确：parent 取消是终局事实，返回 parent 时间是正确行为。
