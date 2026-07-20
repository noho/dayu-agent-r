# WU-SEMANTIC-OWNERSHIP-01 Round 2 Batch C2 Re-Review (MiMo)

## Scope

- Mode: current changes
- Branch: `phaseflow/host-issues-control`
- Base: `HEAD` (workspace uncommitted changes)
- Timestamp: 20260711-184726
- Re-review target: accepted findings `DS-C2-01`, `DS-C2-02` from controller adjudication
- Review-fix artifact: `docs/reviews/wu-semantic-ownership-01-round2-batch-c2-review-fix-codex.md`
- Controller validation artifact: `docs/reviews/wu-semantic-ownership-01-round2-batch-c2-review-fix-controller-validation.md`

## Re-Review Method

对每个 accepted finding，沿真实代码路径走读修复后的实现，验证：
1. finding 描述的问题是否被消除
2. 修复是否引入新问题
3. 测试是否覆盖修复后的行为

---

## DS-C2-01: request_active_attempt_cancel_in_transaction 不再保留不可达 defensive branch

### Finding 回顾

原 finding 指出 `request_active_attempt_cancel_in_transaction` 中，`_dispatch_record_has_worker_accept_fact(...)` 已经证明 `dispatch_record is not None` 且 `worker_accepted_at is not None`，但内层仍有 `if dispatch_record is None or dispatch_record.worker_accepted_at is None` 的 defensive check，是不可达死代码。

### 修复走读

**文件**: `dayu/host/durable/run_transition.py:2848-2864`

修复前（DS review 记录）：
```python
dispatch_record = _read_dispatch_for_attempt(transaction, attempt)
if (
    attempt is not None
    and attempt.status is AttemptStatus.STARTING
    and _dispatch_record_has_worker_accept_fact(dispatch_record)
):
    # 内层有不可达的 defensive check
    if dispatch_record is None or dispatch_record.worker_accepted_at is None:
        raise HostDurableError(...)
    attempt_result = mark_attempt_running_row(...)
```

修复后（当前代码 L2848-2864）：
```python
dispatch_record = _read_dispatch_for_attempt(transaction, attempt)
worker_accepted_at = _dispatch_record_worker_accepted_at(dispatch_record)
if (
    attempt is not None
    and attempt.status is AttemptStatus.STARTING
    and worker_accepted_at is not None
):
    attempt_result = mark_attempt_running_row(
        transaction,
        attempt_id=attempt.attempt_id,
        updated_at=worker_accepted_at,
    )
    attempt_result = _require_attempt_mutation_updated(
        attempt_result,
        mutation_name="mark accepted worker Attempt running before cancel",
    )
    attempt = attempt_result.row
```

**`_dispatch_record_worker_accepted_at`** (L5530-5549): 返回 `str | None`，仅当 `dispatch_record` 非空、`worker_accepted_at` 非空、`worker_accept_event_id` 非空、`worker_accept_event_sequence` 非空、且 `cancelled_event_id` / `cancelled_event_sequence` 为 None 时返回 accepted 时间。

**验证**:
- 不可达的 `if dispatch_record is None or dispatch_record.worker_accepted_at is None: raise HostDurableError(...)` 已被删除
- 类型收窄通过 `_dispatch_record_worker_accepted_at` 的返回值 `str | None` 完成，`worker_accepted_at is not None` 即为运行时 guard
- `mark_attempt_running_row` 使用 `worker_accepted_at` 作为 `updated_at`，语义一致

### 验证测试

`test_cancel_run_starting_worker_accepted_enters_active_cancel`: 通过 ✅

### 结论

DS-C2-01 已关闭。不可达 defensive branch 已移除，类型收窄通过返回值 `str | None` 实现，不再制造假 runtime path。

---

## DS-C2-02: _cancelled_eof_candidate 不再把 token propagation time 放入 RunCancelledData.requested_at

### Finding 回顾

原 finding 指出 `_cancelled_eof_candidate` 的 `RunCancelledData.requested_at` 使用 `cancellation_token.requested_at()`（token 传播时间），而非 committed `CANCEL_REQUESTED.occurred_at`。虽然 `_close_active_cancel` 在 ingest 层覆盖了正确值，但 producer 侧的语义错误属于 semantic ownership drift。

### 修复走读

**文件**: `dayu/host/dispatch.py`

#### 1. 新增 `_ReadCommittedCancelRequestedAtOperation` (L444-473)

```python
@dataclass(frozen=True, slots=True)
class _ReadCommittedCancelRequestedAtOperation:
    event_log_store: EventLogStore
    run_id: str

    def __call__(self, transaction: HostTransaction) -> datetime | None:
        run = read_run_by_id(transaction, self.run_id)
        if run is None:
            return None
        cancel_requested = read_cancel_requested_event_from_run_link(
            transaction, self.event_log_store, run,
        )
        if cancel_requested is None:
            return None
        return parse_utc_timestamp(cancel_requested.occurred_at)
```

从 Run 的 durable link 读取 committed `CANCEL_REQUESTED` event 的 `occurred_at`，返回 `datetime | None`。

#### 2. 新增 `_read_committed_cancel_requested_at` (L4088-4110)

模块级 helper，包装 `_ReadCommittedCancelRequestedAtOperation`，通过 `transaction_runner.run_read` 执行 durable read。

#### 3. `_cancelled_eof_candidate` 签名变更 (L4113-4153)

旧签名：
```python
def _cancelled_eof_candidate(
    *, envelope, worker_event_index, observed_at, cancellation_token,
) -> EngineEventCandidate:
    requested_at = cancellation_token.requested_at()
    if requested_at is None:
        requested_at = observed_at
```

新签名：
```python
def _cancelled_eof_candidate(
    *, envelope, worker_event_index, observed_at, cancel_requested_at, cancellation_token,
) -> EngineEventCandidate:
    # 直接使用传入的 cancel_requested_at
```

`RunCancelledData.requested_at=cancel_requested_at` (L4147)，不再读取 `cancellation_token.requested_at()`。

#### 4. StopAsyncIteration 路径 (L3871-3889)

```python
except StopAsyncIteration:
    if not terminal_seen:
        if cancellation_token.is_cancelled():
            cancel_requested_at = _read_committed_cancel_requested_at(
                transaction_runner=self._transaction_runner,
                event_log_store=self._event_log_store,
                run_id=record.run_id,
            )
            if cancel_requested_at is not None:
                result = ingestor.ingest(
                    _cancelled_eof_candidate(
                        ..., cancel_requested_at=cancel_requested_at, ...
                    )
                )
                run_terminal_closed = _ingest_closed_run(result)
```

#### 5. CancelledError 路径 (L3910-3941)

同样的模式：先 `_read_committed_cancel_requested_at`，非 None 时构造 candidate。

**关键行为变化**: 若 committed `CANCEL_REQUESTED` link 缺失（`cancel_requested_at is None`），不合成 candidate，避免写入错误 `requested_at` 语义。

#### 6. 测试验证

`test_run_cancelled_requested_at_uses_cancel_requested_event_time`: 通过 ✅

该测试构造 Engine `requested_at` 与 CANCEL_REQUESTED `occurred_at` 不同的场景，断言 durable payload 中的 `requested_at` 等于 CANCEL_REQUESTED 的 `occurred_at`。

### 结论

DS-C2-02 已关闭。`_cancelled_eof_candidate` 不再从 `cancellation_token.requested_at()` 读取 token 传播时间，改为接收 committed `CANCEL_REQUESTED.occurred_at`。两个 cancel closeout 路径（StopAsyncIteration、CancelledError）均从同一 canonical fact 派生 `requested_at`，语义 owner 清晰。

---

## Residual Risk

- **canonical cancel request link 缺失**: 若 active cancel path 缺失 committed `CANCEL_REQUESTED` link，`_read_committed_cancel_requested_at` 返回 None，dispatch producer 不合成 `RUN_CANCELLED` candidate。这避免了写入错误 `requested_at` 语义，但可能导致 CANCELLING Run 无 durable terminal。该场景本身是 durable cancel 前置异常，不属于本次两个 accepted findings 的正常路径。
- **非 C2 测试失败**: 既有 controller validation 记录的两个 `tests/host/test_dispatch_scheduler.py` compaction / memory projection 断言失败（`test_proactive_compaction_recovery_tier2_degrades_previous_view`、`test_reactive_compact_request_uses_latest_previous_view`）仍未处理，继续归属 Batch D / 非 C2 范围。

## Conclusion

- **conclusion**: 两个 accepted findings 均已正确关闭，修复实现符合语义所有权约束
- **findings count**: 0（未发现新问题）
- **accepted findings closed**: DS-C2-01 ✅, DS-C2-02 ✅
- **artifact**: `docs/reviews/wu-semantic-ownership-01-round2-batch-c2-rereview-mimo.md`
- **residual risk**: canonical cancel request link 缺失场景（前置异常，非正常路径）；非 C2 compaction/memory projection 测试失败（归属 Batch D）
- **no code changes confirmation**: 本 re-review 未修改任何代码
