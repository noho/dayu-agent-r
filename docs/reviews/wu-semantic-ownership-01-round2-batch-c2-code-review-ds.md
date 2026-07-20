# Code Review — WU-SEMANTIC-OWNERSHIP-01 Round 2 Batch C2

## Scope

- **Mode**: current changes
- **Branch**: `phaseflow/host-issues-control`
- **Base**: `HEAD` (workspace uncommitted changes)
- **Output file**: `docs/reviews/wu-semantic-ownership-01-round2-batch-c2-code-review-ds.md`
- **Included scope**: Batch C2 — Host dispatch / promotion / cancellation / tool accept lifecycle owner 修复
- **Excluded scope**: Batch A/B/D/E, OpenAI retry off-by-one, compaction/memory projection, async DB actor, God module 拆分
- **Parallel review coverage**: 无（单一 reviewer 全链路走读）
- **Review sources**:
  - `AGENTS.md` / `CLAUDE.md`
  - `docs/reviews/wu-semantic-ownership-01-fullrepo-round2-controller-adjudication.md`
  - `docs/reviews/wu-semantic-ownership-01-round2-batch-c2-implementation-codex.md`
  - `docs/reviews/wu-semantic-ownership-01-round2-batch-c2-controller-validation.md`

### Changed Files (production)

| File | Change Summary |
|---|---|
| `dayu/host/dispatch.py` | scheduler close 语义、drain_once retry requeue、promotion 三类异常 backoff requeue、worker stream CancelledError 收口 |
| `dayu/host/admission.py` | `_promote_after_release` skip_reason 修正、`_idempotent_session_cancel_result` / `_active_cancelling_targets_for_session_replay` 注入 EventLogStore |
| `dayu/host/durable/run_transition.py` | `DELEGATED_TO_GOVERNANCE` 枚举、`cancel_recovering_run_in_transaction` current_attempt_id 前置检查、`request_active_attempt_cancel_in_transaction` STARTING+worker_accepted 收窄、`_dispatch_record_has_worker_accept_fact` helper |
| `dayu/host/durable/state.py` | `cancel_recovering_run_row` CAS 增加 `current_attempt_id` |
| `dayu/host/engine_ingest.py` | `_close_active_cancel` `requested_at` 改用 `cancel_requested.occurred_at` |
| `dayu/host/recovery.py` | `defer_accepted_cancel_to_watchdog` 增加 `dispatch_wakeup_port is not None` 守卫 |
| `dayu/host/tool_runtime.py` | `_record_duplicate_accepted` 对 `record_accepted` 异常捕获并 emit diagnostic |

### Changed Files (tests)

| File | New Tests |
|---|---|
| `tests/host/test_active_cancel_dispatch.py` | `test_cancel_run_starting_worker_accepted_enters_active_cancel`；`test_scheduler_close_writes_active_cancel_closeout_terminal`（重命名+断言变更）；`_mark_worker_accepted_without_attempt_running` helper |
| `tests/host/test_dispatch_scheduler.py` | `test_dispatch_first_durable_retry_exhausted_requeues_current_record`；`test_wake_queue_promotion_requeues_after_transient_exception`；`test_scheduler_wake_methods_fail_after_close_and_close_is_idempotent` 更新 |
| `tests/host/test_engine_ingest_mapping.py` | `test_run_cancelled_requested_at_uses_cancel_requested_event_time` |
| `tests/host/test_recovery_scan.py` | `test_scan_accepted_cancel_without_scheduler_uses_recovery_fallback`；既有测试增加 `dispatch_wakeup_port` 注入 |
| `tests/host/test_toolruntime_executor.py` | `test_duplicate_accepted_index_failure_keeps_durable_accept_outcome` |
| `tests/host/test_public_cancel_session_runs.py` | `test_cancel_session_runs_includes_recovering_without_fail_closed` / `test_cancel_run_recovering_replay_is_idempotent_per_run_id` 增加 RECOVERING Run 的 ACCEPTED→RECOVERING 状态准备 |
| `tests/host/test_run_attempt_transitions.py` | `test_cancel_recovering_run_row_cas_requires_current_attempt` |
| `tests/host/test_admission_queue.py` | `test_promote_after_release_reports_delegated_to_governance`；`test_cancel_session_replay_uses_injected_event_log_store`；`_CountingEventLogStore`、`_cancel_session_request`、`_accept_active_worker` helpers |

## Review Walkthrough

以下按 review focus 逐条走读关键调用链，每条均从真实入口追踪到副作用，不依赖间接推断。

### 1. scheduler close / CancelledError / recovery fallback closeout

**入口 1**: `HostDispatchScheduler.close()` (`dispatch.py:2486`)

close 流程：
1. 设 `_closed = True` (L2494)
2. cancel heartbeat_task、drain_task、promotion_drain_task、**watchdog_task**（L2503-2518）
3. `_active_registry.cancel_all()` → 触发各 worker stream 的 `CancelledError`（L2519）
4. cancel 所有 active_tasks（L2520-2522）→ 触发 `_consume_worker_events` 的 `CancelledError`
5. 关闭所有 active_handles（L2523-2525）

**关键链路**: `_consume_worker_events` (`dispatch.py:3871-3895`) — CancelledError handler

旧代码在 `except asyncio.CancelledError` 分支只有 `raise`（裸透传）。新代码在 `raise` 前插入：
- 检查 `cancellation_token.is_cancelled()`（L3872）
- 若 True：调用 `ingestor.ingest(_cancelled_eof_candidate(...))` 写入 terminal RUN_CANCELLED（L3873-3882）
- 若 ingest 失败：fallback 到 `_safe_close_worker_lost(...)`（L3883-3894）
- 无论成功与否，始终 `raise` 透传 CancelledError

**证据**: `_close_active_cancel` (`engine_ingest.py:1436-1453`) 通过 `active_cancel_closeout_in_transaction` 写入 `RUN_CANCELLED` + `ATTEMPT_CANCELLED` durable facts。

**StopAsyncIteration 路径** (L3839-3870)：同样在 `cancellation_token.is_cancelled()` 时写入 cancel EOF candidate。此路径在 worker stream 干净结束时触发（非 CancelledError），补全了 cancel 后 clean EOF 无 terminal 的缺口。

**验证**: `test_scheduler_close_writes_active_cancel_closeout_terminal` 从旧断言 `CANCELLING / RUNNING / 0 RUN_CANCELLED` 改为 `CANCELLED / CANCELLED / 1 RUN_CANCELLED`。

**结论**: scheduler close 现在对 active CANCELLING Run 写入 durable terminal facts，不再 orphan active slot。Cancel closeout 失败时 fallback 到 `_safe_close_worker_lost`（best-effort），不降级成功 closeout。

**入口 2**: `StartupRecoveryScanner._classify_active_or_cancelling` (`recovery.py:288-306`)

旧代码仅检查 `defer_accepted_cancel_to_watchdog`。新代码增加 `and self.dispatch_wakeup_port is not None`（L292）。当 `dispatch_wakeup_port` 为 `None`（scheduler 未注入）时，recovery 不再 defer，改为走 `_classify_active_or_cancelling` → orphan proof → `RUN_LOST`。

**验证**: `test_scan_accepted_cancel_without_scheduler_uses_recovery_fallback` 构造 `dispatch_wakeup_port=None`（默认）场景，断言 `RUN_LOST` 被写入。

**结论**: recovery 不再在 watchdog 不可用时永久 defer CANCELLING Run。语义 owner 清晰：scheduler watchdog 有 port 时由 watchdog 收口，无 port 时 recovery 执行 orphan proof fallback。

### 2. dispatch first durable write retry exhausted

**入口**: `HostDispatchScheduler.drain_once()` (`dispatch.py:2452-2484`)

旧代码在 `_dispatch_one(record)` 调用处无 try/except。新代码 catch `HostTransactionRetryExhaustedError`（L2470-2472）：
```python
except HostTransactionRetryExhaustedError:
    self._queue.put_nowait(record)
    raise
```
将当前 dequeued record 重新放回队列后 re-raise，由上层 `_drain_loop` 的 sleep-backoff 处理。

**关键约束**: `_dispatch_one` 的第一步是 `_mark_waiting_for_lane(record)`（L2863），此 durable write 可能因 SQLite busy 而 retry exhausted。此时 record 已从 `_queue` 出队但未持久化任何状态——重新入队是正确的恢复策略。

**验证**: `test_dispatch_first_durable_retry_exhausted_requeues_current_record` monkeypatch `_mark_waiting_for_lane` 为始终抛 `HostTransactionRetryExhaustedError`，断言 `_queue.qsize() == 1` 且 record 字段匹配。

**结论**: 当前 dispatch record 在 durable retry exhausted 后不会从内存队列丢失。

### 3. promotion transient exceptions requeue/backoff

**入口**: `HostDispatchScheduler._promotion_drain_loop()` (`dispatch.py:2784-2838`)

旧代码仅在 `RuntimeError` 非 close 路径 log warning，不 requeue。新代码新增三类 catch：

| 异常类型 | 行为 |
|---|---|
| `RuntimeError`（非 close） | `_requeue_promotion_after_backoff` + warning |
| `HostTransactionRetryExhaustedError` | `_requeue_promotion_after_backoff` + warning（新增 catch） |
| `Exception`（兜底） | `_requeue_promotion_after_backoff` + warning（新增 catch） |

**`_requeue_promotion_after_backoff`** (`dispatch.py:2840-2854`):
- 检查 `_closed`：已关闭则跳过
- `loop.call_later(interval, self._promotion_queue.put_nowait, session_id)`：延迟后重新投递

**验证**: `test_wake_queue_promotion_requeues_after_transient_exception` monkeypatch `run_queue_promotion` 为首次抛 `RuntimeError`、第二次成功，断言 `attempts == 2`。

**注意**: `_requeue_promotion_after_backoff` 中的 `call_later` 使用的是 `asyncio.get_running_loop()`，callback 是 `put_nowait`（同步方法）——在 asyncio 事件循环回调中调用同步 Queue.put_nowait 是安全的。

**结论**: promotion transient exception 后 session wakeup 会被 backoff requeue，不会因单次 wakeup 丢失导致 accepted/queued Run 永久停滞。

### 4. cancel predispatch RUNNING+STARTING+WORKER_ACCEPTED race

**入口**: `request_active_attempt_cancel_in_transaction()` (`run_transition.py:2810-2889`)

新增逻辑（L2848-2865）：
```python
dispatch_record = _read_dispatch_for_attempt(transaction, attempt)
if (
    attempt is not None
    and attempt.status is AttemptStatus.STARTING
    and _dispatch_record_has_worker_accept_fact(dispatch_record)
):
    # 收窄 Attempt 为 RUNNING
    attempt_result = mark_attempt_running_row(...)
    attempt = attempt_result.row
```

`_dispatch_record_has_worker_accept_fact` (`run_transition.py:5528-5543`) 检查 dispatch record 是否已提交完整的 worker accept durable fact（`worker_accepted_at`、`worker_accept_event_id`、`worker_accept_event_sequence` 均非空，且未被 direct cancel）。

**语义 owner**: dispatch record 的 worker accept fact 由 `accept_worker_running_in_transaction` 在 Engine `ATTEMPT_RUNNING` event 到达时写入。此时 durable 事实是"worker 已接受"，Attempt 应该在 RUNNING 状态，但由于竞态可能仍为 STARTING。本修复在此窗口将 Attempt 收窄为 RUNNING，然后正常进入 active cancel 流程。

**验证**: `test_cancel_run_starting_worker_accepted_enters_active_cancel` 构造 dispatch worker accepted + Attempt STARTING 窗口，断言 cancel 后 Run=CANCELLING、Attempt=RUNNING。

**结论**: 竞态窗口按 active worker cancel 正确处理。

### 5. cancellation terminal requested_at

**入口**: `EngineEventIngestor._close_active_cancel()` (`engine_ingest.py:1425-1450`)

旧代码：
```python
requested_at=format_utc_timestamp(data.requested_at),
```
新代码：
```python
requested_at=cancel_requested.occurred_at,
```

`cancel_requested` 通过 `read_cancel_requested_event_from_run_link` 从 EventLog 读取 committed `CANCEL_REQUESTED` event（L1425-1429）。`occurred_at` 是 EventLog row 的持久化字段，代表 cancel 请求被提交的时间。

**验证**: `test_run_cancelled_requested_at_uses_cancel_requested_event_time` 构造 Engine `requested_at` 与 CANCEL_REQUESTED `occurred_at` 不同的场景，断言 durable payload 中的 `requested_at` 等于 CANCEL_REQUESTED 的 `occurred_at`（`2026-05-15T01:02:03.000000Z`），不等于 Engine 传来的时间。

**附带观察**: `_cancelled_eof_candidate` (`dispatch.py:4042-4082`) 仍使用 `cancellation_token.requested_at()`（token 传播时间）构造合成 EngineEvent candidate 的 `data.requested_at`。此值在 `_close_active_cancel` 中被 `cancel_requested.occurred_at` 覆盖，不影响 durable fact。但合成 candidate 携带了语义错误的时间——若未来有代码路径直接消费 `data.requested_at`（如 duplicate 检测、diagnostic 序列化），会得到 token 时间而非 cancel 请求时间。见 Finding 2。

**结论**: durable cancel terminal payload 的 `requested_at` 正确派生自 committed `CANCEL_REQUESTED` canonical fact。

### 6. durable tool accept remains authoritative

**入口**: `ToolRuntimeExecutor._record_duplicate_accepted()` (`tool_runtime.py:3695-3738`)

旧代码直接 `await self._duplicate_governance.record_accepted(...)` 无异常处理。新代码 catch `Exception`（L3728-3737）：
```python
except Exception:
    self._diagnostic_emitter.emit(
        ToolTraceDiagnosticRecord(
            reason_code="duplicate_accepted_index_failed",
            message="工具结果已完成持久化接受；重复调用索引更新失败，后续治理必须以已持久化事实为准。",
        )
    )
```
函数仍返回 `True`（L3738），表示工具结果已持久化接受。

**语义 owner**: durable tool accept（`_duplicate_governance.record_accepted` 之前的工具执行与 durable 写入）是权威真源。duplicate accepted index 是 attempt-local 治理辅助数据结构，其更新失败不应推翻已完成的工具接受结果。

**验证**: `test_duplicate_accepted_index_failure_keeps_durable_accept_outcome` monkeypatch `record_accepted` 抛 `RuntimeError`，断言 outcome 仍为 `ToolCompletedOutcome`、`durable_missing_reasons` 为空、diagnostic 包含 `duplicate_accepted_index_failed`。

**结论**: duplicate accepted index 更新失败只产生诊断，不推翻已持久化接受的工具结果。

### 7. cancel_recovering_run_row CAS

**入口**: `cancel_recovering_run_row()` (`state.py:4159-4220`)

新增：
- 参数 `current_attempt_id: str`（L4162）
- `_require_non_empty_text(current_attempt_id, ...)` 校验（L4187-4189）
- SQL WHERE 增加 `AND current_attempt_id = ?`（L4203）
- 参数绑定增加 `current_attempt_id`（L4215）

**上游调用**: `cancel_recovering_run_in_transaction` (`run_transition.py:2587-2593`) 在调用 `cancel_recovering_run_row` 前新增 `run.current_attempt_id is None` 前置检查，返回 `INVALID_STATE`。这确保 transition 层不会将无 current Attempt 的 RECOVERING Run 传入 state 层。

**验证**: `test_cancel_recovering_run_row_cas_requires_current_attempt` 构造 wrong attempt id 和 correct attempt id 两次 CAS 调用，断言 wrong=CAS_LOST、correct=UPDATED、最终 Run=CANCELLED。

**结论**: recovering cancel CAS 正确包含 `current_attempt_id`，transition 层拒绝无 current Attempt 的 RECOVERING cancel。

### 8. _promote_after_release reason

**入口**: `_promote_after_release()` (`admission.py:4432-4458`)

旧代码 `skip_reason=PromotionSkipReason.ACTIVE_RUN_EXISTS`，新代码 `skip_reason=PromotionSkipReason.DELEGATED_TO_GOVERNANCE`。

**语义分析**: `_promote_after_release` 的语义是"active slot 释放后唤醒 pre-start governance"。此时已无 active Run——active slot 已释放。返回 `ACTIVE_RUN_EXISTS` 是错误语义（暗示 active Run 仍存在并阻塞 promotion）。`DELEGATED_TO_GOVERNANCE` 正确描述实际情况：promotion 决策已委托给 scheduler governance gate，当前 admission 层不做裁决。

**验证**: `test_promote_after_release_reports_delegated_to_governance` 断言 `result.skip_reason is PromotionSkipReason.DELEGATED_TO_GOVERNANCE` 且 spy 记录了 promotion wakeup。

**结论**: `_promote_after_release` 报告 truthful owner-level reason。

### 9. session cancel replay uses injected EventLogStore

**入口**: `_CancelSessionRunsOperation._execute()` (`admission.py:1994-2001`)

旧代码 `_idempotent_session_cancel_result(transaction, existing, reason=...)` 不传 `event_log_store`。新代码传 `event_log_store=self.event_log_store`。

**传递链**:
- `_idempotent_session_cancel_result` (`admission.py:4059`) → 新增 `event_log_store` 参数
- → `_active_cancelling_targets_for_session_replay` (`admission.py:4223`) → 新增 `event_log_store` 参数
- → `event_log_store.read_event_by_id(transaction, record.created_event_id)` (L4241) 替代旧代码的 `EventLogStore().read_event_by_id(...)`

旧代码在 helper path 中自行构造 `EventLogStore()`——这破坏了 DI 模式，使测试无法验证注入的 store 是否被使用。

**验证**: `test_cancel_session_replay_uses_injected_event_log_store` 注入 `_CountingEventLogStore`，断言 `read_event_by_id_count >= 1` 且 replay 结果与首次一致。

**结论**: session cancel replay 使用注入的 EventLogStore，不再自行构造。

### 10. Batch D/E scope creep / compatibility shim / weak typing 检查

逐文件检查：

- `dispatch.py`: 所有新增函数（`_requeue_promotion_after_backoff`）有完整 docstring 和类型注解。无 Batch D（public contract）或 Batch E（Fins typing）变更。
- `admission.py`: 参数签名扩展（`event_log_store: EventLogStore`）有完整 docstring。无 scope creep。
- `run_transition.py`: 新增 `DELEGATED_TO_GOVERNANCE` 枚举值、`_dispatch_record_has_worker_accept_fact` helper 有完整 docstring 和类型注解。无 scope creep。
- `state.py`: `cancel_recovering_run_row` 新增参数有 docstring 和校验。无 scope creep。
- `engine_ingest.py`: 单行变更，语义 owner 修正。无 scope creep。
- `recovery.py`: 新增 `and self.dispatch_wakeup_port is not None` 守卫。无 scope creep。
- `tool_runtime.py`: 新增 except 块，有完整中文 diagnostic message。无 scope creep。
- 所有测试文件：新增测试函数有完整 docstring 和类型注解。helper 函数有 docstring。

**未发现**：兼容性 re-export、兼容性常量、兼容性 wrapper/facade、`hasattr`/`getattr` 逃避类型设计、魔法数字/字符串、无类型参数/返回值。

## Findings

### 1-未修复-低-`request_active_attempt_cancel_in_transaction` 包含不可达的 defensive check

- **入口/函数**: `request_active_attempt_cancel_in_transaction`
- **文件(行号)**: `dayu/host/durable/run_transition.py:2849-2855`
- **输入场景**: RUNNING Run + STARTING Attempt + worker accepted dispatch record → 进入 cancel 流程
- **实际分支**: 外层 `if` 条件要求 `_dispatch_record_has_worker_accept_fact(dispatch_record)` 为 `True`，内层 `if dispatch_record is None or dispatch_record.worker_accepted_at is None` 作为 defensive check
- **预期行为**: defensive check 在真异常时捕获并抛 `HostDurableError`
- **实际行为**: `_dispatch_record_has_worker_accept_fact` (L5528-5543) 已保证 `dispatch_record is not None` 且 `dispatch_record.worker_accepted_at is not None`，内层 `if` 条件永远为 `False`，`raise HostDurableError(...)` 是不可达死代码
- **直接证据**:
  - L5531-5533: `dispatch_record is not None and dispatch_record.worker_accepted_at is not None` — 此检查与外层条件 AND 短路，保证进入内层时这两个条件均已满足
  - L2854: `if dispatch_record is None or dispatch_record.worker_accepted_at is None:` — 条件与外层保证矛盾
- **影响**: 无运行时影响（不可达代码不改变行为）。但误导后续维护者以为此路径可达，可能在重构时引入错误依赖
- **建议改法和验证点**: 移除不可达的 `if/raise` 块（L2854-2855），或若意图是防御性编程，将检查提升为 `assert`（仅在 debug 模式生效）。若保留，补充注释说明这是类型收窄 guard 而非运行时 guard
- **修复风险（低）**: 纯删除死代码，不影响行为
- **严重程度（低）**: 死代码，不影响正确性

### 2-未修复-低-`_cancelled_eof_candidate` 合成 candidate 的 `requested_at` 语义不一致

- **入口/函数**: `_cancelled_eof_candidate`
- **文件(行号)**: `dayu/host/dispatch.py:4059-4061`
- **输入场景**: worker stream 因 cancel 被取消或 clean EOF 后 `cancellation_token.is_cancelled()` 为 True
- **实际分支**: `requested_at = cancellation_token.requested_at()` — 取 token 传播时间
- **预期行为**: `requested_at` 应反映 cancel 请求的实际提交时间（即 committed `CANCEL_REQUESTED.occurred_at`）
- **实际行为**: 合成 EngineEvent candidate 的 `data.requested_at` 携带 token 传播时间（wall clock），而非 cancel 请求时间。此值进入 `_close_active_cancel` 后被 `cancel_requested.occurred_at` 覆盖，**durable fact 正确**。但合成 candidate 中途携带了语义错误的时间
- **直接证据**:
  - L4059: `requested_at = cancellation_token.requested_at()` — 取 token 时间
  - `engine_ingest.py:1450`: `requested_at=cancel_requested.occurred_at` — 覆盖为正确时间
  - 两个时间在语义上不同：token 传播时间取决于调度延迟，cancel 请求时间是业务事实
- **影响**: 当前无运行时影响（durable fact 被覆盖为正确值）。若未来有代码路径在 `_close_active_cancel` 之前消费 `data.requested_at`（如 duplicate 检测、diagnostic payload 序列化），会得到错误时间。属于语义所有权微漂移：candidate producer 拥有错误语义，consumer 静默修正
- **建议改法和验证点**: `_cancelled_eof_candidate` 不应自行决定 `requested_at`——要么从 CANCEL_REQUESTED event 读取（需要传入 EventLogStore），要么将字段标记为"将被 ingest 层覆盖"。如果 token 时间不需要进入 candidate，将其设为 `observed_at` 并加注释说明 actual value is resolved by the ingestor from the committed CANCEL_REQUESTED fact
- **修复风险（低）**: 仅影响合成 candidate 的中间字段，durable fact 不受影响
- **严重程度（低）**: 当前无运行时影响，属语义一致性改进

## Open Questions

1. `_cancelled_eof_candidate` 的 `requested_at` 字段是否还有其他消费者（如 diagnostic artifact、trace、telemetry）直接读取 `data.requested_at` 而不经过 `_close_active_cancel` 的覆盖？当前走读未发现，但无法排除 EngineEventCandidate 被序列化到 log/trace 的路径。建议后续搜索 `RunCancelledData.requested_at` 的全部引用。

## Residual Risk

1. **CancelledError handler closeout 失败路径未直接测试**: `_consume_worker_events` 中 CancelledError handler 的 `except Exception as closeout_exc` → `_safe_close_worker_lost` fallback 路径没有专门测试。此路径需要 cancel closeout ingestion 本身失败（极端罕见：SQLite 写入在已成功执行多次 ingest 后突然失败）。风险极低，因为 `_safe_close_worker_lost` 自身有独立的测试覆盖。

2. **`_requeue_promotion_after_backoff` 回调与 close 的竞态**: `call_later` 回调触发时，scheduler 可能已关闭。此时 `_promotion_queue.put_nowait` 会将 session_id 写入无人消费的队列。此行为无害（进程关闭中），但若 scheduler close → reopen 模式存在，可能残留 stale wakeup。当前系统无 close→reopen 模式，风险为零。

3. **`_cancelled_eof_candidate` 在 StopAsyncIteration 路径和 CancelledError 路径均被调用**: 两个路径都走 `_close_active_cancel` → `active_cancel_closeout_in_transaction`，durable 写入是幂等的（event_id 去重）。但 StopAsyncIteration 路径先于 CancelledError 路径——如果 worker stream 在 CancelledError 前先触发 clean EOF（StopAsyncIteration），两个路径可能竞速。当前 `_close_active_cancel` 的 duplicate 检测（L1417-1424）通过 event_id 去重处理此情况，风险为零。

4. **非 C2 测试失败**: 实现 artifact 记录了两个 `test_dispatch_scheduler.py` 中 compaction/memory projection 断言失败（`test_proactive_compaction_recovery_tier2_degrades_previous_view`、`test_reactive_compact_request_uses_latest_previous_view`），不在 Batch C2 scope。本 review 未验证这些失败是否与 C2 变更存在间接关联。

5. **`_CountingEventLogStore` 的 `read_event_by_id_count >= 1` 断言**: 此断言验证了注入的 store 被调用，但未验证在没有注入 store 时的行为（即未回归测试旧路径）。实际上旧路径已被删除（`EventLogStore()` 自构造不再存在），所以无需回归测试旧路径。

## Conclusion

- **findings count**: 2（均为低严重度）
- **material defects**: 0
- **artifact**: `docs/reviews/wu-semantic-ownership-01-round2-batch-c2-code-review-ds.md`
- **residual risk**: 见上，均为低风险或零风险
- **no code changes confirmation**: 本 review 未修改任何代码

Batch C2 的实现正确完成了所有 claimed finding 的修复。9 个 review focus 的语义 owner 修复均有直接证据支撑，测试覆盖了关键行为、失败路径和边界条件。两个低严重度 finding 均不影响正确性：一个是不可达死代码，一个是合成 candidate 的中间字段语义不一致（durable fact 已正确）。未发现 Batch D/E scope creep、兼容性 shim 或弱类型/docstring 违规。
