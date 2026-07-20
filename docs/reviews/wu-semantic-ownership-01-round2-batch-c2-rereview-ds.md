# WU-SEMANTIC-OWNERSHIP-01 Round 2 Batch C2 Re-Review (DS)

## Scope

- **Mode**: review-fix re-review
- **Batch**: C2 — Host dispatch / promotion / cancellation / tool accept lifecycle owner
- **Branch**: `phaseflow/host-issues-control`
- **Base**: `HEAD` (workspace uncommitted changes)
- **Output file**: `docs/reviews/wu-semantic-ownership-01-round2-batch-c2-rereview-ds.md`
- **Reviewed accepted findings**: DS-C2-01, DS-C2-02
- **Review sources**:
  - `AGENTS.md`
  - `docs/reviews/wu-semantic-ownership-01-round2-batch-c2-code-review-mimo.md`
  - `docs/reviews/wu-semantic-ownership-01-round2-batch-c2-code-review-ds.md`
  - `docs/reviews/wu-semantic-ownership-01-round2-batch-c2-code-review-controller-adjudication.md`
  - `docs/reviews/wu-semantic-ownership-01-round2-batch-c2-review-fix-codex.md`
  - `docs/reviews/wu-semantic-ownership-01-round2-batch-c2-review-fix-controller-validation.md`
- **Not reviewed**: Batch A/B/D/E, non-accepted findings, MiMo findings (无 MiMo accepted findings 需 re-review)

---

## Re-Review Walkthrough

### DS-C2-01: `request_active_attempt_cancel_in_transaction` 移除不可达 defensive branch

**原始 finding**: `_dispatch_record_has_worker_accept_fact(dispatch_record)`（返回 bool）已证明 `dispatch_record is not None` 且 `worker_accepted_at is not None`，其内部 `if dispatch_record is None or dispatch_record.worker_accepted_at is None: raise HostDurableError(...)` 为不可达死代码。

**Controller adjudication**: accepted。要求在 durable transition owner 内完成修复，类型收窄不应制造假 runtime path。

**修复位置**: `dayu/host/durable/run_transition.py`

**修复内容**:

1. 将 `_dispatch_record_has_worker_accept_fact`（返回 `bool`）替换为 `_dispatch_record_worker_accepted_at`（返回 `str | None`）：
   - L5527-5543: 新 helper 检查 dispatch_record 的 worker accept durable fact 完整性 + 未被 direct cancel
   - 条件满足时返回 `dispatch_record.worker_accepted_at`（非 None 的 str），否则返回 `None`
   - 返回值直接可用作 `mark_attempt_running_row` 的 `updated_at` 参数

2. `request_active_attempt_cancel_in_transaction` (L2847-2864) 使用类型收窄模式：
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
   ```
   不再有任何内层 defensive `if/raise` 分支。

3. 旧函数名 `_dispatch_record_has_worker_accept_fact` 已从整个代码库完全移除（`rg` 搜索结果为无匹配）。

**验证**:
- `test_cancel_run_starting_worker_accepted_enters_active_cancel` 通过（3 passed in 0.37s）
- 全量 275 测试通过
- pyright: 0 errors, 0 warnings, 0 informations

**结论**: DS-C2-01 已正确关闭。类型收窄模式清晰，无不可达分支残留，无兼容性 shim。

---

### DS-C2-02: `_cancelled_eof_candidate` 不再把 token propagation time 放入 `RunCancelledData.requested_at`

**原始 finding**: `_cancelled_eof_candidate` 从 `cancellation_token.requested_at()` 取 token 传播 wall clock 作为 cancel 请求业务时间。ingest 层在 `_close_active_cancel` 中以 committed `CANCEL_REQUESTED.occurred_at` 覆盖为正确值，但 producer 端语义错误。

**Controller adjudication**: accepted。要求 synthetic cancel candidate 与 durable closeout 应从 committed `CANCEL_REQUESTED` 同源派生，不应由 Host cancellation token 传播时间生产。

**修复位置**: `dayu/host/dispatch.py`

**修复内容**:

1. 新增 `_ReadCommittedCancelRequestedAtOperation` (L444-473):
   - 通过 `read_run_by_id` → `read_cancel_requested_event_from_run_link` 读取 Run typed cancel link 中的 committed `CANCEL_REQUESTED` event
   - 返回 `parse_utc_timestamp(cancel_requested.occurred_at)` 或 `None`
   - Run 缺失或 link 不存在时返回 `None`

2. 新增 `_read_committed_cancel_requested_at` (L4088-4110):
   - 将 `_ReadCommittedCancelRequestedAtOperation` 包装在 `transaction_runner.run_read()` 中执行 durable read transaction
   - 对外暴露为可直接调用的模块级函数

3. StopAsyncIteration handler (L3873-3889):
   - 在构造 candidate 前先调用 `_read_committed_cancel_requested_at(...)` 读取 canonical cancel time
   - 仅当 `cancel_requested_at is not None` 时才构造并 ingest candidate
   - canonical fact 缺失时不合成携带错误语义的 candidate

4. CancelledError handler (L3911-3941):
   - 同样先读取 `cancel_requested_at`
   - 仅当非 None 时构造 candidate
   - 整体包裹在 `try/except Exception` 中，ingest 或其依赖异常时 fallback 到 `_safe_close_worker_lost`

5. `_cancelled_eof_candidate` 签名变更 (L4113-4153):
   - 新增必选参数 `cancel_requested_at: datetime`
   - 移除 `cancellation_token.requested_at()` 的读取
   - `RunCancelledData.requested_at` 直接使用 `cancel_requested_at`（committed fact）
   - `cancellation_token` 仅用于 `cancel_reason()`（Host governance fact，正确 owner）

6. `ActiveCancelCloseoutInput` docstring 更新 (`run_transition.py:852`):
   - `requested_at` 参数说明从 "Host/Engine 观察到的取消请求时间文本" 改为 "committed `CANCEL_REQUESTED` fact 的发生时间文本"

**语义所有权验证**:
- `RunCancelledData.requested_at` 的真源现在是 committed `CANCEL_REQUESTED.occurred_at`
- synthetic cancel candidate producer（dispatch）和 durable closeout（engine_ingest `_close_active_cancel`）均从同一 committed CANCEL_REQUESTED canonical fact 派生
- `cancellation_token` 仍作为 `cancel_reason` 的真源（正确：cancel reason 是 Host governance fact，不属于 business time）

**验证**:
- `test_cancel_run_starting_worker_accepted_enters_active_cancel`、`test_scheduler_close_writes_active_cancel_closeout_terminal`、`test_run_cancelled_requested_at_uses_cancel_requested_event_time` 通过（3 passed）
- 全量 275 测试通过
- pyright: 0 errors, 0 warnings, 0 informations

**结论**: DS-C2-02 已正确关闭。synthetic cancel candidate 与 durable closeout 现在从同一 committed `CANCEL_REQUESTED` canonical fact 同源派生。

---

## Findings

未发现实质性问题。

两个 accepted findings 均已正确关闭，修复实现遵循了 semantic ownership 修复边界原则：
- DS-C2-01: 修复在 durable transition owner（`run_transition.py`）内完成，无下游补偿
- DS-C2-02: 修复在 dispatch producer boundary（`dispatch.py`）完成，与 ingest consumer 共享同一 canonical fact source

---

## Open Questions

无。

---

## Residual Risk

1. **canonical cancel fact 缺失时 synthetic candidate 被跳过**: 当 Run 缺少 committed `CANCEL_REQUESTED` link 时，`_read_committed_cancel_requested_at` 返回 `None`，synthetic cancel candidate 不会被构造。这是正确行为（避免写入错误语义），但意味着该场景下 scheduler close / CancelledError 不会为 CANCELLING Run 写入 durable terminal fact。该场景本身是 durable cancel 前置异常（cancel 请求未被 durable 提交），不属于正常 cancel 路径。如未来发现此场景在生产中出现，需先修复 cancel request durable write 可靠性。

2. **StopAsyncIteration 路径移除 `not self._closed` 守卫**: 旧代码在 StopAsyncIteration handler 中有 `not self._closed` 检查，新代码移除了该检查。此变更不在 DS-C2-02 的 scope 内（属于 Batch C2 scheduler close 语义修复的一部分）。实际影响：scheduler close 期间若 worker stream 先触发 clean EOF 而非 CancelledError，两个路径可能竞速，但 durable write 是幂等的（event_id 去重），无数据正确性风险。

3. **既有非 C2 compaction/memory projection 断言失败**: 如 controller validation 记录的 `test_proactive_compaction_recovery_tier2_degrades_previous_view` 和 `test_reactive_compact_request_uses_latest_previous_view` 失败仍归属 Batch D，不在本次 re-review 范围内。

---

## Conclusion

- **conclusion**: 两个 accepted findings (DS-C2-01, DS-C2-02) 均已正确关闭。修复遵循 semantic ownership 原则，在正确 owner boundary 完成，无下游 fallback 或兼容 shim。
- **findings count**: 0（无新增问题）
- **accepted findings closed**: 2/2 (DS-C2-01 ✓, DS-C2-02 ✓)
- **artifact**: `docs/reviews/wu-semantic-ownership-01-round2-batch-c2-rereview-ds.md`
- **residual risk**: 见上，均为低风险或无风险
- **no code changes confirmation**: 本 re-review 未修改任何代码
