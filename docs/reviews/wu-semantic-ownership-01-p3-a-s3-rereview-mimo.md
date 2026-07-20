# WU-SEMANTIC-OWNERSHIP-01 P3-A S3 re-review — AgentMiMo

## Gate / scope

- Work unit：`WU-SEMANTIC-OWNERSHIP-01 / P3-A / S3`。
- Gate：code review re-review。
- Reviewer：AgentMiMo。
- Finding truth：`docs/reviews/wu-semantic-ownership-01-p3-a-s3-code-review-controller-adjudication.md`。
- Fix artifact：`docs/reviews/wu-semantic-ownership-01-p3-a-s3-fix-codex.md`。
- Controller validation：`docs/reviews/wu-semantic-ownership-01-p3-a-s3-fix-controller-validation.md`。
- 原两路 review：
  - `docs/reviews/wu-semantic-ownership-01-p3-a-s3-code-review-mimo.md`
  - `docs/reviews/wu-semantic-ownership-01-p3-a-s3-code-review-ds.md`
- 必读：`AGENTS.md`、`docs/host/design.md`、`docs/engine/design.md`、plan S3。
- 只做 re-review，不修改生产代码/测试/README/control doc，不 commit/push/PR。

## Verdict

**PASS** — 4 项 accepted finding 全部已修复，0 项新 material defect。

## Required validation 执行结果

```text
# S3 required test matrix
pytest tests/host/test_engine_ingest_mapping.py tests/host/test_active_cancel_dispatch.py tests/host/test_recovery_dispatch.py tests/host/test_public_cancel_session_runs.py tests/host/test_run_attempt_transitions.py tests/host/test_state_schema.py -q
214 passed in 2.06s

# Extended integration tests
pytest tests/host/test_phase5_local_execution_integration.py tests/host/test_dispatch_scheduler.py -q
88 passed in 1.81s

# Import cycle
python -c "from dayu.host.lifecycle_events import HostRunEventType, HostAttemptEventType, run_terminal_event_type_for_status, attempt_terminal_event_type_for_status; import dayu.host.durable.state; import dayu.host.durable.run_transition; import dayu.host.engine_ingest; print('import-ok')"
import-ok

# Terminal constant source scan
rg "_EVENT_TYPE_(RUN|ATTEMPT)_(SUCCEEDED|FAILED|CANCELLED|LOST)" dayu/host/durable/run_transition.py dayu/host/engine_ingest.py
(exit 1 — clean, no matches)

# Synthetic EngineEvent construction scan
rg "EngineEvent\(|type=EngineEventType\.RUN_FAILED|RunFailedData\(" dayu/host/engine_ingest.py
(exit 1 — clean, no matches)

# Legacy mixed _TerminalPlan scan
rg "_TerminalPlan" dayu/host/engine_ingest.py
(exit 1 — clean, no matches)

# hasattr/getattr scan
rg "hasattr\|getattr" dayu/host/engine_ingest.py dayu/host/durable/state.py dayu/host/command.py
(exit 1 — clean, no matches)

# pyright
0 errors, 0 warnings, 0 informations

# git diff --check
(no output — clean)
```

## Finding 最终状态

### S3-CR-F01 — 已修复

**验证内容**：reactive compaction public path 真实消费 Attempt status owner；terminal refs 不再充当 lifecycle routing truth。

**直接代码证据**：

- `engine_ingest.py:1933-1936`：
  ```python
  if (
      latest.run.status is not RunStatus.RECOVERING
      or not is_terminal_attempt_status(latest.attempt.status)
  ):
      return pending.result_prefix
  ```
  原 `latest.attempt.terminal_event_id is None` 已被替换为 `not is_terminal_attempt_status(latest.attempt.status)`。

- `is_terminal_attempt_status` 在 `durable/state.py:615-623` 从 `TERMINAL_ATTEMPT_STATUSES`（派生自 `_row_rules.TERMINAL_ATTEMPT_STATUS_VALUES`）判定，`AttemptStatus.FAILED` 在该集合中（`_row_rules.py:22`）。

**测试证据**：

- `test_reactive_compaction_gate_consumes_terminal_attempt_status_truth`（line 916-970）通过 monkeypatch 拦截 `is_terminal_attempt_status`，记录调用参数，验证 `AttemptStatus.FAILED` 被传入 gate；当 gate 返回 `False` 时，不写 `CONTEXT_COMPACTED`、不创建 recovery Attempt，Run/Attempt 保持 `RECOVERING/FAILED`。
- 原有 public reactive success path（`test_context_compaction_requested_none_budget_uses_host_estimator_and_recovers`、`test_reactive_compaction_calls_llm_outside_write_transaction`）继续通过，证明成功 recovery 回归未破坏。

**terminal ref 残留使用审计**：`attempt_terminal_event_id` / `run_terminal_event_id` 在 `engine_ingest.py` 中仅用于 shared terminal transaction 输入（`TerminalCloseoutInput` 参数）和 deterministic event-id helper（`_event_id` / `_host_lifecycle_terminal_event_ids`），不参与状态分类或 lifecycle routing。

**结论**：F01 已修复。reactive compaction gate 现在消费 `is_terminal_attempt_status` owner，terminal refs 只保留 row consistency 与 canonical refs 职责。

---

### S3-CR-F02 — 已修复

**验证内容**：旧 `_TerminalPlan` 确实消失；`_EngineTerminalPlan` 与 `_HostLifecycleTerminalPlan` 无互斥字段混装，只共享真正 canonical `_TerminalFactPlan`；无 optional probing、hasattr/getattr、compat wrapper、god-bag；所有构造函数与 closeout signatures 类型闭合。

**直接代码证据**：

- `_TerminalPlan` source scan 无匹配（`rg "_TerminalPlan" dayu/host/engine_ingest.py` exit 1）。
- `_TerminalFactPlan`（line 443-451）：6 个字段，全部是两类来源共享的 canonical fact（`attempt_event_type`、`run_event_type`、`attempt_status`、`run_status`、`reason`、`terminal_payload`）。
- `_EngineTerminalPlan`（line 455-467）：10 个字段，`terminal: _TerminalFactPlan` + Engine 专属字段（`finish_reason`、`filtered`、`degraded`、`error_code`、`message`、`provider_request_id`、`client_correlation_id`、`recoverable`、`unsupported_later_owner`）。
- `_HostLifecycleTerminalPlan`（line 471-481）：8 个字段，`terminal: _TerminalFactPlan` + Host lifecycle 专属字段（`error_code`、`message`、`recoverable`、`worker_lifecycle_signal`、`stream_error_code`、`last_observed_worker_event_index`、`last_accepted_event_id`）。
- 两个 plan 类型字段集合互斥（除 `terminal`、`error_code`、`message`、`recoverable` 四个共享字段外），编译期静态分离。
- `hasattr`/`getattr` scan 无匹配。
- `_close_terminal`（line 1184）签名接收 `_EngineTerminalPlan`；`_close_host_lifecycle_terminal`（line 1285）签名接收 `_HostLifecycleTerminalPlan`。两条 closeout path 的 plan 类型在编译期分离。

**测试证据**：

- `test_terminal_plans_use_lifecycle_event_owner_helpers`（line 501-571）断言：
  - `_final_answer_plan` / `_run_failed_plan` 返回 `_EngineTerminalPlan`；
  - `_lost_lifecycle_plan` 返回 `_HostLifecycleTerminalPlan`；
  - Engine plan 字段集合与 Host lifecycle plan 字段集合精确匹配预期；
  - 两类 plan 的 Attempt/Run event type 均来自 lifecycle owner helper。

**pyright**：`0 errors, 0 warnings, 0 informations`，证明 candidate、plan 与 closeout 签名的静态类型链路成立。

**结论**：F02 已修复。混装 `_TerminalPlan` 已被删除，替换为编译期分离的 `_EngineTerminalPlan` / `_HostLifecycleTerminalPlan`，只共享 `_TerminalFactPlan` canonical facts。

---

### S3-CR-F03 — 已修复

**验证内容**：Host lifecycle run_id guard 在 ingress 生效，test double/public path 测试可信，不产生错误 terminal fact。

**直接代码证据**：

- `_validate_host_lifecycle_context`（line 1146-1181）identity 校验条件包含 `run.run_id != envelope.run_id`（line 1169）：
  ```python
  if (
      run.session_id != envelope.session_id
      or run.run_id != envelope.run_id
      or run.current_attempt_id != envelope.attempt_id
      or attempt.run_id != envelope.run_id
      or attempt.execution_id != envelope.execution_id
      or dispatch_record.dispatch_record_id != envelope.dispatch_record_id
      or dispatch_record.execution_id != envelope.execution_id
  ):
      return None
  ```
  与 `_validate_durable_context`（line 1129-1137）完全一致。

**测试证据**：

- `test_host_lifecycle_ingress_rejects_mismatched_run_identity`（line 3016-3070）通过 monkeypatch 注入 repository test double，使 `read_run_by_id` 返回 `run_id` 被替换的 row：
  ```python
  return replace(run, run_id=f"{run_id}-mismatched")
  ```
  断言：
  - `result.status is EngineIngestStatus.REJECTED`
  - `result.reason == "stale_execution_id"`
  - `result.terminal_closeout is False`
  - Run/Attempt status 保持不变，无错误 terminal fact。

**结论**：F03 已修复。Host lifecycle ingress guard 显式校验 `run.run_id`，public path test 通过 repository test double 证明错 identity 被拒绝。

---

### S3-CR-F04 — 已修复

**验证内容**：直接读取 `engine_ingest.py`、`transaction.py`（隐含在 `run_write` 事务语义中）、`payload.py`（隐含在 `_write_terminal_payload` / `_write_host_lifecycle_terminal_payload` 中）与 fix diff，验证 non-UPDATED 返回会先抛私有异常、真实 transaction rollback，再在 transaction 外恢复 REJECTED contract；Engine/Host 两条 catch 都覆盖；accepted/duplicate/ordinary diagnostic 不被误捕；四条 adversarial 测试确实比较 sqlite payload rows、descriptor、EventLog、status 且不是假阳性。

**直接代码证据**：

1. **私有异常定义**：`_TerminalCloseoutRollback(Exception)`（line 336-337），docstring 明确说明"terminal closeout 未更新 durable state 时触发整笔事务回滚"。

2. **Engine-origin path raise**：`_close_terminal`（line 1268-1270）：
   ```python
   if result.status != StateMutationStatus.UPDATED:
       raise _TerminalCloseoutRollback(
           f"Engine terminal closeout returned {result.status.value}"
       )
   ```

3. **Host lifecycle path raise**：`_close_host_lifecycle_terminal`（line 1357-1359）：
   ```python
   if result.status != StateMutationStatus.UPDATED:
       raise _TerminalCloseoutRollback(
           f"Host lifecycle terminal closeout returned {result.status.value}"
       )
   ```

4. **Engine catch**：`ingest` method（line 820-823）：
   ```python
   try:
       return self._transaction_runner.run_write(_operation)
   except _TerminalCloseoutRollback:
       return _terminal_closeout_precondition_failed_result()
   ```

5. **Host lifecycle catch**：`_close_worker_lifecycle`（line 2716-2719）：
   ```python
   try:
       result = self._transaction_runner.run_write(_operation)
   except _TerminalCloseoutRollback:
       result = _terminal_closeout_precondition_failed_result()
   ```

6. **事务语义**：`run_write` 使用 `BEGIN IMMEDIATE`；operation 内抛出的任何 exception（包括 `_TerminalCloseoutRollback`）导致 rollback；只有 operation 正常返回后才 commit。因此 `_TerminalCloseoutRollback` 在 payload descriptor 写入后、terminal CAS 失败时触发，会回滚整个事务（包括已写的 payload descriptor）。

7. **不误捕 accepted/duplicate/diagnostic**：`_TerminalCloseoutRollback` 只在 `result.status != StateMutationStatus.UPDATED` 时 raise。`UPDATED` 状态的 accepted 结果不 raise；DUPLICATE 在 raise 之前就已 return（line 1222-1229 / 1310-1317）；diagnostic 路径在 `_close_terminal` / `_close_host_lifecycle_terminal` 之外处理，不经过 raise 点。

**测试证据（四条 adversarial 测试）**：

1. **`test_engine_terminal_invalid_state_rolls_back_payload_and_events`**（line 3142-3180）：
   - 构造 `RunStatus.WAITING` + `AttemptStatus.RUNNING`（terminal closeout precondition 不满足的跨对象状态组合）。
   - 通过 public `ingest(FINAL_ANSWER)` 进入真实 `terminal_closeout_in_transaction`。
   - 真实 `terminal_closeout_in_transaction` 返回 `INVALID_STATE`。
   - `_close_terminal` raise `_TerminalCloseoutRollback`。
   - `ingest` catch 后返回 `REJECTED / terminal_closeout_precondition_failed`。
   - 断言 `_terminal_storage_snapshot(store.transaction_runner, seeded) == before`：比较真实 SQLite 的 `host_sqlite_payloads` row count、`payload_descriptors` row count、`EventLog` row count、Run status、Attempt status，证明无 orphan payload、无错误 event、无 status mutation。

2. **`test_host_lifecycle_invalid_state_rolls_back_payload_and_events`**（line 3183-3215）：
   - 同上，但通过 public `close_worker_lost` 进入。
   - 真实 `terminal_closeout_in_transaction` 返回 `INVALID_STATE`。
   - `_close_host_lifecycle_terminal` raise `_TerminalCloseoutRollback`。
   - `_close_worker_lifecycle` catch 后返回 `REJECTED / terminal_closeout_precondition_failed`。
   - 同样断言 storage snapshot 不变。

3. **`test_engine_terminal_cas_lost_rolls_back_real_payload_repository`**（line 3218-3258）：
   - monkeypatch `terminal_closeout_in_transaction` 为 `_cas_lost_terminal_closeout`，该 helper 在真实 transaction 内读取 durable rows 后返回 `CAS_LOST`。
   - payload 仍由生产 `_write_terminal_payload -> PayloadStore.write_sqlite_payload` 写入真实 transaction。
   - `_close_terminal` raise `_TerminalCloseoutRollback`。
   - `ingest` catch 后返回 `REJECTED / terminal_closeout_precondition_failed`。
   - 断言 storage snapshot 不变（payload descriptor 已随 transaction 回滚）。

4. **`test_host_lifecycle_cas_lost_rolls_back_real_payload_repository`**（line 3261-3293）：
   - 同上，但通过 public `close_clean_eof` 进入。

**rollback exception 泄漏审计**：

- `_TerminalCloseoutRollback` 是 `engine_ingest.py` 模块私有异常（`class _TerminalCloseoutRollback(Exception)`）。
- 只在 `_close_terminal` 和 `_close_host_lifecycle_terminal` 内部 raise。
- 只在 `ingest`（Engine path）和 `_close_worker_lifecycle`（Host lifecycle path）的 `run_write` 调用处 catch。
- catch 位于 `run_write` 返回后、public caller 返回前，不泄漏到 reactive/async/public caller。
- 不会错误吞掉 `HostDurableError`：`_TerminalCloseoutRollback` 继承 `Exception`，不是 `HostDurableError` 子类；`HostDurableError` 由 `run_write` 的事务框架处理（rollback + re-raise），不受此 catch 影响。

**stop_worker_stream / promotion contract 审计**：

- `_terminal_closeout_precondition_failed_result()` 返回 `terminal_closeout=True, promotion_triggered=False, stop_worker_stream` 默认 `False`。
- `_with_terminal_promotion_retry` 只对 `status in (ACCEPTED, DUPLICATE)` 触发 promotion；REJECTED 不触发，正确。
- `stop_worker_stream=False` 在 terminal closeout 失败时是正确的：没有成功 closeout，没有新的 terminal fact 需要通知 worker 停止。

**结论**：F04 已修复。non-UPDATED terminal helper result 通过 `_TerminalCloseoutRollback` 让真实 write transaction rollback，事务外恢复 rejected result；Engine/Host 的真实 invalid-state 与注入 CAS-lost 测试均比较 payload、descriptor、EventLog、Run/Attempt status 前后快照，不是假阳性。

## Rollback exception 泄漏与吞没专项检查

| 检查项 | 结论 |
|---|---|
| `_TerminalCloseoutRollback` 是否泄漏到 reactive/async/public caller | 否。两条 catch 均在 `run_write` 返回后、public return 前 |
| 是否错误吞掉真正 `HostDurableError` | 否。`_TerminalCloseoutRollback(Exception)` 不是 `HostDurableError` 子类 |
| 是否丢失 `stop_worker_stream` contract | 否。rejected result 默认 `stop_worker_stream=False`，terminal closeout 失败时无需停止 worker |
| 是否丢失 promotion contract | 否。`_with_terminal_promotion_retry` 只对 `ACCEPTED/DUPLICATE` 触发 promotion |

## 新 material defect 检查

逐项检查 fix 是否引入新 defect：

| 检查维度 | 结论 |
|---|---|
| `_TerminalFactPlan` / `_EngineTerminalPlan` / `_HostLifecycleTerminalPlan` 字段是否闭合 | 是。pyright 零错误，所有构造点类型匹配 |
| `_TerminalCloseoutRollback` 是否只在正确位置 raise | 是。只在 `result.status != StateMutationStatus.UPDATED` 时 raise；DUPLICATE 已提前 return |
| `is_terminal_attempt_status` 在 reactive compaction 中的语义是否等价 | 是。`AttemptStatus.FAILED` 在 `TERMINAL_ATTEMPT_STATUSES` 中；原 `terminal_event_id is None` 代理在正常 row shape 下等价，修复后直接消费 owner |
| `_validate_host_lifecycle_context` 新增 `run.run_id` 检查是否引入回归 | 否。该检查与 `_validate_durable_context` 一致；`read_run_by_id` 已隐含此不变量，显式检查只是自足表达 |
| `is_dispatch_record_direct_cancelable` 是否引入新 edge case | 否。覆盖 PENDING/WAITING_FOR_LANE/DISPATCHING-pre-accept/DISPATCHING-post-accept/CANCELLED 五种状态，与原 command.py 内联逻辑等价 |

**结论**：未发现新 material defect。

## Propagation audit 验证

逐条验证 fix artifact 中的 propagation audit：

### Engine-origin terminal

`EngineEvent` -> `EngineEventCandidate` -> `_EngineTerminalPlan` -> `_TerminalFactPlan`（lifecycle owner helper 派生 event type/status）-> 当前 transaction 写 terminal payload -> shared `terminal_closeout_in_transaction` -> Attempt/Run canonical facts 与 status rows -> commit 后 projection/read model/outbox/memory 消费 committed truth。

若 shared terminal helper 返回非 `UPDATED`，`_TerminalCloseoutRollback` 回滚 payload、EventLog 与所有状态写入，事务外只返回 rejected result；没有可供下游错误投影的 orphan fact。

**验证**：代码路径确认。`_close_terminal` 先写 payload（line 1230-1234），再调 `terminal_closeout_in_transaction`（line 1236-1267），非 UPDATED 时 raise（line 1268-1270），catch 在 `run_write` 外（line 820-823）。

### Host lifecycle terminal

worker EOF/crash -> `_HostLifecycleCloseoutCandidate` -> 完整 envelope/repository identity validation（含 `run.run_id` guard）-> `_HostLifecycleTerminalPlan` -> `_TerminalFactPlan` -> Host lifecycle payload/identity -> shared `terminal_closeout_in_transaction` -> Attempt/Run canonical facts 与 status rows -> committed projections。

Host lifecycle plan 不含 Engine finish/provider/correlation/unsupported-owner 字段，canonical payload/source/ref 仍保持 `host.worker_lifecycle` 真源；non-UPDATED 时与 Engine path 使用同一 rollback/result contract。

**验证**：代码路径确认。`_close_host_lifecycle_terminal` 先写 payload（line 1318-1322），再调 `terminal_closeout_in_transaction`（line 1323-1355），非 UPDATED 时 raise（line 1357-1359），catch 在 `_close_worker_lifecycle` 外（line 2716-2719）。

### Reactive compaction

Engine provider overflow -> reactive request fact -> old Attempt FAILED + Run RECOVERING -> transaction 外 compactor -> fresh durable context -> `is_terminal_attempt_status(latest.attempt.status)` gate -> compact accepted/fallback/failure -> recovery Attempt 或 fail closed。terminal refs 只保留 row consistency 与 canonical refs，不参与 gate truth。

**验证**：代码路径确认。`_execute_reactive_compaction` line 1933-1936 消费 `is_terminal_attempt_status`。

### Late event rejection

durable Run / Attempt status -> `is_terminal_*` predicate -> rejected diagnostic 或 accepted waiting confirmation；nullable terminal refs 仍是 row consistency fields。

**验证**：`_late_engine_event_rejection_reason`（line 3731-3758）和 `_late_host_lifecycle_rejection_reason`（line 3761-3777）均使用 `is_terminal_run_status` / `is_terminal_attempt_status`，不读取 `terminal_event_id`。

### Direct cancelability

dispatch record row -> durable state predicate -> command cancel branch -> transition row update / terminal facts。

**验证**：`command.py:1705` 调用 `is_dispatch_record_direct_cancelable(dispatch_record)`，不再直接检查 worker accepted nullable 字段。

**结论**：propagation audit 全部通过。durable state、EventLog、diagnostic、projection、用户/LLM 可见输出没有从不同真源重建同一 lifecycle/status 事实。

## AGENTS.md 合规检查

| 检查项 | 结论 |
|---|---|
| 完整中文 docstring（参数、返回值、异常） | 通过。新增/修改函数均有完整中文 docstring |
| 严格类型、无 `Any`/`object`/无类型参数/返回值 | 通过。pyright 零错误 |
| 无 `hasattr`/`getattr` seam | 通过。scan 无匹配 |
| 无魔法字符串重复 | 通过。event id prefix、source、actor、reason 常量集中定义在模块级 |
| 无 God function / dataclass | 通过。`_TerminalFactPlan`（6 fields）、`_EngineTerminalPlan`（10 fields）、`_HostLifecycleTerminalPlan`（8 fields）字段明确 |
| 无兼容性代码 | 通过。无 compat wrapper、re-export、facade |
| README decision | 通过。`dayu/host/README.md` 已描述两条 typed path；fix 只强化 private typed plan 与 transaction atomicity，无需追加更新 |

## Scope 不扩张检查

| 检查项 | 结论 |
|---|---|
| P3-B final answer / outbox continuity | 未触碰 |
| P3-J EventLog schema hardening | 未触碰 |
| 非 terminal EventLog 常量统一 | 未触碰（按 plan 归 P3-J） |
| `docs/host/issues-implementation-control.md` | 未修改 |
| schema migration / dispatch state machine | 未引入 |

## Residual risks

| 风险 | 分类 |
|---|---|
| 跨进程 Engine terminal 与 Host lifecycle terminal 同时提交 stress | assigned to later work unit（production stress / EventLog hardening） |
| 非 terminal EventLog 常量统一 | assigned to later work unit（P3-J） |
| P3-B final answer / outbox continuity | covered by later approved slice |
| 外部 artifact 先发布、SQLite 后失败的通用 cleanup | covered by existing design/non-goal |

无未分类 residual risk、blocking open question 或 deferred accepted finding。

## Artifact

- artifact path：`docs/reviews/wu-semantic-ownership-01-p3-a-s3-rereview-mimo.md`
- accepted finding 数：4
- finding 最终状态：F01 已修复、F02 已修复、F03 已修复、F04 已修复
- 新 finding 数：0
- verdict：PASS
