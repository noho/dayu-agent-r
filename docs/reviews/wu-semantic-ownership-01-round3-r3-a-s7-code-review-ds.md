# Code Review

## Scope

- Mode: current changes
- Branch: `phaseflow/host-issues-control`
- Base: S6 accepted commit `c893c77f` 之后的 S7 implementation workspace changes
- Output file: `docs/reviews/wu-semantic-ownership-01-round3-r3-a-s7-code-review-ds.md`
- Included scope:
  - Production: `dayu/host/compaction_operation.py`（`_CompactionAttemptCancellationToken`、`_ensure_compactor_proposal_active`、per-attempt fresh child、pre-call recheck、CancelledError 分类）
  - Tests: `tests/host/test_compaction_cancellation_scope.py`（新增，5 项 test）、`tests/host/test_dispatch_scheduler.py`（新增 `test_proactive_compaction_rechecks_durable_state_after_manifest`）
  - Docs: `docs/host/design.md`、`dayu/host/README.md`、`tests/README.md`
- Excluded scope: `dayu/engine/` diff 为空；`dayu/host/llm_compaction.py`、`dayu/host/dispatch.py`、`dayu/host/engine_ingest.py` 无需修改（确认不再修改）；Service/CLI/Fins 无变更。
- Parallel review coverage: 无。

## Review Method Summary

沿 S7 review focus 逐项走读 `_CompactionAttemptCancellationToken` 实现 → `run_compaction_operation` per-attempt child 创建 → `_prepare_compactor_proposal` pre-call recheck 两条路径（prepared/non-prepared）→ CancelledError 分类。随后走读全部 6 项 S7 测试：timeout-success、parent-cancel 优先、运行中 parent cancel、caller cancel 隔离、manifest-post-write durable recheck、proactive durable recheck。最后验证 Engine diff 为空、无跨 transaction provider await。

### 1. Parent/child cancellation precedence

`_CompactionAttemptCancellationToken`（`compaction_operation.py:563-638`）：

- **`is_cancelled()`**：先读 `self._parent.is_cancelled()`，为 True 立即返回；否则读 `_local_reason is not None`。
- **`cancel_reason()`**：先读 `self._parent.cancel_reason()`，非 None 直接返回；否则读 local。
- **`requested_at()`**：先读 `self._parent.cancel_reason()` 是否为 None（隐式 parent-first），非 None 返回 `self._parent.requested_at()`；否则读 local。
- **`request_cancel(reason)`**：只写 `_local_reason` 和 `_local_requested_at`，永不写 parent。

parent reason/time 无条件优先于 attempt-local timeout。`test_parent_cancel_after_timeout_wins_before_retry`（`test_compaction_cancellation_scope.py:152-211`）验证：timeout 后 parent cancel → `first_child.cancel_reason() == _PARENT_REASON`，非 `_TIMEOUT_REASON`；`provider_calls == 1`（retry 不启动）。

### 2. Fresh child per attempt

`run_compaction_operation` 的 attempt loop（`compaction_operation.py:705-707`）：
```python
attempt_cancellation_token = _CompactionAttemptCancellationToken(
    cancellation_token
)
```
每次 loop iteration 新建 `_CompactionAttemptCancellationToken` 实例，共享同一个 parent 但拥有独立的 `_local_reason`/`_local_requested_at`。

`test_attempt_timeout_does_not_cancel_parent_or_next_attempt`（`test_compaction_cancellation_scope.py:97-148`）验证：
- `observed_tokens[0] is not observed_tokens[1]`（不同对象）
- `observed_tokens[0].cancel_reason() == "compactor_proposal_timeout"`（timeout）
- `observed_tokens[1].is_cancelled() is False`（新 child 未污染）
- `parent.is_cancelled() is False`（parent 未污染）

### 3. Timeout doesn't pollute parent token

`request_cancel(reason)` 只写 `self._local_reason`/`self._local_requested_at`（`compaction_operation.py:625-638`），只有 `threading.Lock` 保护的 local 状态。parent 的 `request_cancel` 只由 Host 外部控制（`llm_compaction.py` 的 timeout handler 传入的是 attempt child token，不再是 parent）。

既有 `llm_compaction.py` 的 `_signal_timeout_cancellation` 仍对 request token 调 `request_cancel(...)`，但传入对象已由 S7 收窄为 attempt child。controller source scan 确认 `llm_compaction.py` timeout cancellation 只命中 attempt-local child。

### 4. Pre-call durable recheck

`_ensure_compactor_proposal_active()`（`compaction_operation.py:1061-1081`）被两条 provider 路径调用：

- **Prepared path**（`compaction_operation.py:1015-1018`）：manifest recorder 返回后、`run_prepared_compactor_proposal()` 前调用。传入 `manifest_reference`，失效时 `_CompactorProposalCancelledError` 携带 manifest ref 作为诊断。
- **Non-prepared path**（`compaction_operation.py:1042-1045`）：`compact()` 前调用。传入 `proposal_manifest_reference=None`。

recheck 调用 `cancellation_token.is_cancelled()`，对 `_CompactionAttemptCancellationToken` 而言先读 parent。Proactive parent `_DurableRunCancellationToken` 的 `is_cancelled()` 会重读 Run status/input cursor，因此已提交 manifest 但 Run 已失效的场景会被正确阻止。

**测试验证**：
- `test_manifest_post_write_recheck_blocks_provider_and_keeps_reference`（`test_compaction_cancellation_scope.py:327-371`）：recorder hook 让 parent 失效后 `provider_calls == 0`，`result.rejected_attempts[0].proposal_manifest_ref` 保留 manifest ref。
- `test_proactive_compaction_rechecks_durable_state_after_manifest`（`test_dispatch_scheduler.py:5189-5262`）：真实 SQLite store + durable manifest recorder；manifest commit 后独立 write transaction 改变 Run status → `compactor.calls == 0`，`RUNNER_CALL_INPUT_ASSEMBLED` fact 已提交（manifest 已持久化），`CONTEXT_COMPACTED` 为零（compactor provider 未调用）。

### 5. Engine diff 为空

Controller 独立确认 `git diff --name-only -- dayu/engine/` 零输出。`_CompactionAttemptCancellationToken` 实现 `CancellationToken` Protocol（只读观察协议），不新增 writable method。

### 6. 无跨 transaction provider await

- Manifest recording（`_record_compactor_proposal_manifest`）是同步调用，执行 write transaction 后 return。
- `_ensure_compactor_proposal_active` 是同步 `cancellation_token.is_cancelled()` 调用。对于 proactive `_DurableRunCancellationToken`，内部 `is_cancelled()` 打开一个短 read transaction 读取 Run status 后立即返回，不在 provider await 期间持 transaction。
- `compactor.run_prepared_compactor_proposal(prepared_input)` 和 `compactor.compact(request, cancellation_token)` 的 `await` 不持任何 Host write transaction。
- `asyncio.CancelledError` 异常处理（`compaction_operation.py:1023-1028, 1048-1053`）正确区分：token 未取消 → 透传 `CancelledError`（caller task cancel）；token 已取消 → 转为 `_CompactorProposalCancelledError`（Host cancellation result）。

`test_outer_task_cancellation_is_not_reclassified`（`test_compaction_cancellation_scope.py:279-325`）验证外层 `Task.cancel()` 仍抛 `asyncio.CancelledError`，不写 parent、不伪装为 Host cancellation result。

### 7. Scope creep 扫描

- `dayu/engine/` diff 空
- `dayu/host/llm_compaction.py`、`dayu/host/dispatch.py`、`dayu/host/engine_ingest.py` 无需修改（implementation report 确认既有实现已满足 S7 contract）
- No Service/CLI/Fins changes
- No `dayu/contracts/cancellation.py` changes（Engine public `CancellationToken` Protocol unchanged）
- No new schema/event type/payload shape

## Findings

未发现实质性问题。

所有 review focus 的代码实际行为与 plan Slice S7 冻结契约一致：

- **Parent/child precedence**：`is_cancelled()`/`cancel_reason()`/`requested_at()` 始终先读 parent；parent reason/time 无条件优先
- **Fresh child per attempt**：每次 attempt loop 新建 `_CompactionAttemptCancellationToken(parent)`；test 验证 token identity 不同
- **Timeout 不污染 parent**：`request_cancel()` 只写 `_local_reason`/`_local_requested_at`；test 验证 parent 在 timeout 后 `is_cancelled() is False`
- **Provider-call 前 durable recheck**：`_ensure_compactor_proposal_active()` 在 manifest 后/provider 前调用；test 验证 manifest commit 后 Run 失效时 `provider_calls == 0`
- **Engine diff 为空**：`git diff --name-only -- dayu/engine/` 零输出；`CancellationToken` 保持只读 Protocol
- **无跨 transaction provider await**：manifest write → commit → synchronous recheck → provider await；Proactive `_DurableRunCancellationToken.is_cancelled()` 在短 read transaction 内完成

## Open Questions

无。

## Residual Risk

- Provider 物理停止仍依赖 Engine/runner 对只读 `CancellationToken` 的协作观察；本 slice 保证 timeout scope 与 Host durable acceptance 正确性，不承诺远端 provider 已物理取消。这是既有取消契约和明确 non-goal。
- 未发现未归属 S7 residual risk。无 compaction schema、quality policy、memory 语义或 Engine provider timeout 分类变化。
