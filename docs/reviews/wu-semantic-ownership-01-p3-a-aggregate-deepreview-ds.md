# WU-SEMANTIC-OWNERSHIP-01 P3-A Aggregate Deepreview (AgentDS)

## Gate / scope

- Work unit：`WU-SEMANTIC-OWNERSHIP-01 / P3-A - Host lifecycle, run status, and terminal event source of truth`。
- Gate：aggregate deepreview（S1+S2+S3 全量）。
- Reviewer：AgentDS。
- Review base：`2400a04c`（accepted plan bookkeeping 后）。
- Review head：`3649c9ea`（P3-A S3 accepted implementation commit）。
- Review target：`git diff 2400a04c..3649c9ea` 下全部 15 个生产代码/测试文件。
- 只 review，不修改生产代码/测试/README/control doc，不 commit/push/PR。

## Validation summary

```text
pytest tests/host/test_lifecycle_events.py tests/host/test_state_schema.py \
  tests/host/test_run_attempt_transitions.py tests/host/test_engine_ingest_mapping.py \
  tests/host/test_public_run_api.py tests/host/test_active_cancel_dispatch.py \
  tests/host/test_recovery_dispatch.py tests/host/test_public_cancel_session_runs.py \
  tests/host/test_dispatch_scheduler.py -q
323 passed in 3.75s
```

- pyright：`0 errors, 0 warnings, 0 informations`。
- `git diff 2400a04c..3649c9ea --check`：通过。
- Import cycle validation：`import-ok`（`lifecycle_events → api; durable.state → api; durable.run_transition → lifecycle_events, state; engine_ingest → lifecycle_events, state` 均无循环）。

Source scans（全量，12 项）：

| Scan | 目标 | 结果 |
|---|---|---|
| `_EVENT_TYPE_(RUN\|ATTEMPT)_(SUCCEEDED\|FAILED\|CANCELLED\|LOST)` | terminal event 常量重复 | **0 匹配**（run_transition + engine_ingest 全部清除） |
| `_TerminalPlan`（旧 mixed god-bag） | legacy mixed plan | **0 匹配** |
| `EngineEvent(` / `RunFailedData(` 构造（非 Engine-origin 路径） | synthetic EngineEvent | **0 匹配** |
| `hasattr` / `getattr` seam | 逃逸类型边界 | **0 匹配**（全量 changed files） |
| `Any` / `object` 类型注解 | 弱类型 | **0 匹配**（全量 changed files） |
| `terminal_event_id is None` / `is not None`（非 row validation） | terminal refs 代理 status | **0 匹配**（late rejection + reactive gate 已全量迁移到 status predicate） |
| `worker_accepted_at` / `worker_accept_event_id` / `worker_accept_event_sequence`（command.py） | command 直接读 dispatch 内部字段 | **0 匹配** |
| `is_terminal_run_status` / `TERMINAL_RUN_STATUSES` / `run_status_in_clause` / `START_BLOCKING_RUN_STATUSES`（admission / read_model / purge） | 消费者使用 owner helper | **全部通过** — admission `is_terminal_run_status`，read_model `is_terminal_run_status`，purge `NON_TERMINAL_RUN_STATUSES` + `TERMINAL_RUN_STATUSES` + `serialized_run_status_values` |
| `is_dispatch_record_direct_cancelable`（command.py） | command 使用 durable owner predicate | **通过** — command.py:1705 调用，不直接读 nullable worker fields |
| `_EVENT_TYPE_RUN_ACCEPTED` 等非 terminal 常量 | 非 terminal 残留（记录为 P3-J residual） | **残留存在**（见 §10 residual risk），均在 P3-A scope 外 |
| `TERMINAL_RUN_STATUSES` / `NON_TERMINAL_RUN_STATUSES` / `START_BLOCKING_RUN_STATUSES` / `TERMINAL_ATTEMPT_STATUSES` 定义（state.py） | owner 定义完整性 | **通过** — 均从 `_row_rules` text-level truth 派生 |
| `host.worker_lifecycle` source / `event-host-lifecycle-` prefix / `HOST_LIFECYCLE_DIAGNOSTIC` event_type | diagnostic 不泄漏为业务事实 | **通过** — DIAGNOSTIC event_class，不进入 CANONICAL_FACT，不进入 memory/outbox/LLM-facing projection |

---

## 1. 生命周期 event/status 唯一真源跨 S1/S2/S3 闭合

**Verdict：PASS**

端到端 propagation audit（从 owner enum → producer → EventLog → durable rows → consumers）：

### 1.1 Run terminal event type 链

```
RunStatus (api.py)
  → _row_rules.TERMINAL_RUN_STATUS_VALUES (text-level truth)
    → state.TERMINAL_RUN_STATUSES (typed frozenset)
      → lifecycle_events.run_terminal_event_type_for_status(status) → HostRunEventType.value
        → run_transition: terminal_closeout_in_transaction 生成 EventLog event_type 字符串
          → EventLog row.event_type
            → read_model / outbox / HostEvent / memory 消费
```

- **owner helper 验证**：`run_terminal_event_type_for_status` 对非 terminal status fail-fast（`ValueError`），不接受 fallback 字符串（`lifecycle_events.py:189-192`）。
- **producer 验证**：`terminal_closeout_in_transaction` 的 EventLog append 使用 owner helper 派生的 `request.attempt_terminal_status` / `request.run_terminal_status` 构造 event payload；event_type 字符串由调用方通过 `closeout_attempt_terminal_event_type_for_status(...)` / `run_terminal_event_type_for_status(...)` 传入（`run_transition.py:2037-2055`）。
- **consumer 验证**：`read_model.py:467` 使用 `is_terminal_run_status`；`purge.py:127-130` 使用 `serialized_run_status_values(NON_TERMINAL_RUN_STATUSES)` / `serialized_run_status_values(TERMINAL_RUN_STATUSES)`；`admission.py:1574` 使用 `is_terminal_run_status`。
- **EventLog 消费验证**：`lifecycle_events.run_status_for_terminal_event(event_type)` 和 `is_host_run_terminal_event(event_type)` 提供从 EventLog 字符串反查的单一入口。

### 1.2 Attempt terminal event type 链

```
AttemptStatus (api.py)
  → _row_rules.TERMINAL_ATTEMPT_STATUS_VALUES (text-level truth)
    → state.TERMINAL_ATTEMPT_STATUSES (typed frozenset)
      → lifecycle_events.attempt_terminal_event_type_for_status(status) → HostAttemptEventType.value (全部 6 个)
      → lifecycle_events.closeout_attempt_terminal_event_type_for_status(status) → HostAttemptEventType.value (4 个 closeout-supported)
        → run_transition 或 engine_ingest 调用方选择正确的 helper
          → EventLog row.event_type
```

- **两套 helper 区分**：`attempt_terminal_event_type_for_status` 覆盖 SUSPENDED/STEERED（durable terminal 但不 supported closeout）；`closeout_attempt_terminal_event_type_for_status` 排除 SUSPENDED/STEERED（`lifecycle_events.py:69-74`）。closeout path 使用后者，fail-fast 对非法 status 抛 `ValueError`（`lifecycle_events.py:227-232`）。
- **测试覆盖**：`test_attempt_terminal_event_type_for_status_rejects_non_terminal` 断言非 terminal status 抛错；`test_attempt_terminal_to_status_roundtrip` 断言 supported subset 一致性。

### 1.3 Run/Attempt status predicate 链

```
_row_rules.TERMINAL_RUN_STATUS_VALUES / TERMINAL_ATTEMPT_STATUS_VALUES
  → state.TERMINAL_RUN_STATUSES / TERMINAL_ATTEMPT_STATUSES (typed frozenset)
  → state.NON_TERMINAL_RUN_STATUSES = RunStatus - TERMINAL_RUN_STATUSES (自动派生)
  → state.START_BLOCKING_RUN_STATUSES = NON_TERMINAL_RUN_STATUSES - {QUEUED} (自动派生)
  → state.is_terminal_run_status / is_terminal_attempt_status (predicate)
  → state.serialized_run_status_values / run_status_in_clause (SQL helpers)
```

- **自动派生验证**：新增 `RunStatus` 成员时，`NON_TERMINAL_RUN_STATUSES` 和 `START_BLOCKING_RUN_STATUSES` 自动更新。`START_BLOCKING_RUN_STATUSES` 的精确成员集合测试（`test_start_blocking_run_statuses_exact_members`）在新增非终态时强制失败，开发者必须显式审查 admission 语义。
- **SQL helper 验证**：`run_status_in_clause` 空集合 fail-fast（`state.py:598-599`），placeholder 数量与 params 数量一致（`test_run_status_in_clause_generates_matching_placeholders`）。

### 闭合结论

Run terminal event type、Attempt terminal event type、Run/Attempt status predicate 三条传播链均已在 owner → producer → EventLog → consumers 全链路闭合。无重复 mapping、无 SQL 硬编码 status 列表、无 nullable terminal ref 代理 status 判定。

---

## 2. 重复 terminal mapping / terminal status set / SQL 硬编码 IN / nullable terminal ref 状态代理

**Verdict：PASS（含 1 个 LOW residual note）**

### 2.1 Terminal event 字符串生产者

- `run_transition.py` 不再定义 `_EVENT_TYPE_RUN_SUCCEEDED` / `_EVENT_TYPE_ATTEMPT_SUCCEEDED` 等 terminal 常量。terminal event type 通过 `run_terminal_event_type_for_status(...)` / `closeout_attempt_terminal_event_type_for_status(...)` 从 lifecycle owner helper 派生。
- `engine_ingest.py` 不再定义 terminal `_EVENT_TYPE_RUN_*` 常量。Engine-origin terminal plan（`_final_answer_plan` / `_run_failed_plan` 等）使用 lifecycle owner helper 生成 event type。
- Source scan `_EVENT_TYPE_(RUN|ATTEMPT)_(SUCCEEDED|FAILED|CANCELLED|LOST)` 在 `run_transition.py` 与 `engine_ingest.py` 中 **0 匹配**。

### 2.2 Terminal status set 消费者

- `admission.py` 不再内联 `(RunStatus.SUCCEEDED, RunStatus.FAILED, RunStatus.CANCELLED, RunStatus.LOST)`，改用 `state.is_terminal_run_status`。
- `read_model.py` 删除本地 `_TERMINAL_RUN_STATUSES`，改用 `state.is_terminal_run_status`。
- `purge.py` 使用 `state.NON_TERMINAL_RUN_STATUSES` / `state.TERMINAL_RUN_STATUSES` + `serialized_run_status_values`。
- SQL read helpers（`read_active_run_for_session`、`read_non_terminal_runs_for_session`、`read_non_terminal_runs`）使用 `run_status_in_clause(START_BLOCKING_RUN_STATUSES)` / `run_status_in_clause(NON_TERMINAL_RUN_STATUSES)` 生成 `IN` clause。

### 2.3 CAS mutation helper 内部 status 列表（LOW residual）

`state.py` 中 CAS mutation helpers（`promote_queued_run_row`、`start_unstarted_run_row` 等）的 `UPDATE ... WHERE` 子查询 `NOT EXISTS (SELECT 1 FROM host_runs WHERE ... status IN (?, ?, ?, ?, ?))` 仍使用内联 `serialize_run_status(...)` 参数列表（`state.py:3219`、`3305`、`3772`、`4051`、`6486`）。这些是同一模块内的 low-level mutation guard，不是跨模块重复真源；但新增非终态 `RunStatus` 时需要人工审查这些 CAS guard 是否需要更新。

**建议**：后续 WU（如 P3-J 或 schema hardening）将 CAS mutation guard 的 status filter 也迁移到 `run_status_in_clause`，消除最后的手工 placeholder 计数。当前严重性 LOW，因为：
- 这 5 处都在 `state.py` 内，与 `NON_TERMINAL_RUN_STATUSES` 定义同文件。
- 新增 `RunStatus` 成员时 `START_BLOCKING_RUN_STATUSES` 精确成员测试会强制审查 admission 语义，间接覆盖 CAS guard 更新需求。
- 已有 `test_start_blocking_run_statuses_exact_members` 守卫。

### 2.4 Nullable terminal ref 状态代理

- `_late_engine_event_rejection_reason`（`engine_ingest.py:3731-3758`）：使用 `is_terminal_run_status(context.run.status)` / `is_terminal_attempt_status(context.attempt.status)`，不读取 `terminal_event_id`。
- `_late_host_lifecycle_rejection_reason`（`engine_ingest.py:3761-3777`）：同上。
- `_execute_reactive_compaction`（`engine_ingest.py:1934`）：使用 `is_terminal_attempt_status(latest.attempt.status)`，不读取 `terminal_event_id`（S3-CR-F01 已修复）。
- `terminal_event_id` 的唯一使用点已收缩为：transaction producer（写入入参）、row consistency validation（`validate_terminal_event_refs_shape`）、duplicate detection（event id 计算不使用 terminal refs）。

---

## 3. Engine-origin 与 Host-lifecycle-origin typed path、identity namespace、source/ref/payload、duplicate/partial-duplicate/first-committer、non-UPDATED rollback atomicity

**Verdict：PASS**

### 3.1 类型分离

- `_EngineTerminalPlan`（`engine_ingest.py:454-467`）：Engine-origin 专用字段（`finish_reason`、`filtered`、`degraded`、`error_code`、`message`、`provider_request_id`、`client_correlation_id`、`recoverable`、`unsupported_later_owner`）。
- `_HostLifecycleTerminalPlan`（`engine_ingest.py:470-481`）：Host lifecycle 专用字段（`error_code`、`message`、`recoverable`、`worker_lifecycle_signal`、`stream_error_code`、`last_observed_worker_event_index`、`last_accepted_event_id`）。
- `_TerminalFactPlan`（`engine_ingest.py:442-451`）：共享 canonical facts（`attempt_event_type`、`run_event_type`、`attempt_status`、`run_status`、`reason`、`terminal_payload`）。
- 两条 closeout path 构造 `TerminalCloseoutInput` 时显式写各自字段：Engine path 传 `worker_lifecycle_signal=None` 等（`engine_ingest.py:1262-1265`），Host path 传 `engine_event_ref=None, finish_reason=None` 等（`engine_ingest.py:1339-1348`）。
- 测试 `test_terminal_plans_use_lifecycle_event_owner_helpers` 精确断言两类 plan 的字段集合互斥。

### 3.2 Identity namespace

| 维度 | Engine-origin | Host-lifecycle |
|---|---|---|
| event id prefix | `event-engine-` | `event-host-lifecycle-` |
| digest input | `execution_id + worker_event_index + event_class + event_type + sub_index` | `identity_kind + session_id + run_id + attempt_id + execution_id + worker_event_index + event_class + event_type + sub_index + lifecycle_source + reason` |
| source | `host.engine_ingest` | `host.worker_lifecycle` |
| actor | `host.engine_ingest` | `host.worker_lifecycle` |
| payload ref prefix | `payload-engine-terminal` | `payload-host-lifecycle-terminal` |
| engine_event_ref | `engine:{execution_id}:{index}:{type}` | 不设置（`None`） |
| host_lifecycle_ref | 不设置 | `host-lifecycle:{execution_id}:{index}:{source}:{reason}` |

两个 namespace disjoint，duplicate detection 按最终 event ids 查重，Engine-origin 与 Host-lifecycle 不可能因 id collision 互相吞掉。

### 3.3 Duplicate / partial-duplicate / first-committer

- Engine-origin path 双重检测：`_duplicate_engine_terminal_result`（ingest 入口）+ `_close_terminal` 内 `_existing_rows` 检查。两层都检查 complete duplicate（`len(existing) == len(event_ids)`）。
- Host lifecycle path 双重检测：`_duplicate_host_lifecycle_terminal_result` + `_close_host_lifecycle_terminal` 内 `_existing_rows` 检查。同上。
- Partial-duplicate（如 2 个 event id 中只有 1 个已存在）：`len(existing) != len(event_ids)` → `None` → 流程进入 closeout → `terminal_closeout_in_transaction` 尝试写入已存在 event id → SQLite UNIQUE constraint → transaction rollback。同一 transaction 内先写入的 payload descriptor 也回滚。**无孤儿风险**。

### 3.4 non-UPDATED rollback atomicity

- `_TerminalCloseoutRollback`（`engine_ingest.py:336-338`）：私有 typed exception。
- `_close_terminal` / `_close_host_lifecycle_terminal`：`result.status != UPDATED` 时 `raise _TerminalCloseoutRollback(...)`（`engine_ingest.py:1268-1271` / `1357-1360`）。
- Transaction runner（`transaction.py:353-358`）：`except Exception` 捕获并执行 SQLite rollback，然后 re-raise。
- Catch site：`_ingest_before_reactive_compaction`（`engine_ingest.py:820-823`）和 `_close_worker_lifecycle`（`engine_ingest.py:2716-2719`）在 `run_write` 外捕获 `_TerminalCloseoutRollback`，映射为 `REJECTED / terminal_closeout_precondition_failed / events=()`。
- 测试 `test_engine_terminal_invalid_state_rolls_back_payload_and_events` 等 4 条 adversarial 测试比较真实 SQLite payload rows、descriptor、EventLog、status 的 before/after snapshot，验证无 orphan material。
- HostDurableError 误吞检查：`transaction.py:347 except HostDurableError` 在 `except Exception` 之前，不被 `_TerminalCloseoutRollback` catch site 拦截。

---

## 4. Active cancel / WAITING/SUSPENDED confirmation / recovery/reactive compaction / worker clean EOF/crash 组合状态机反例

**Verdict：PASS**

### 4.1 CANCELLING decision table 逐项验证

| Plan 要求 | 实现位置 | 测试覆盖 | 状态 |
|---|---|---|---|
| `CANCELLING` + Engine `FINAL_ANSWER` → reject as late terminal | `_late_engine_event_rejection_reason:3753-3757` | `test_late_final_answer_after_run_cancelling_is_rejected_with_diagnostic` | ✅ |
| `CANCELLING` + Engine `RUN_FAILED` → reject as late terminal | 同上 | `test_late_run_failed_after_run_cancelling_is_rejected_with_diagnostic` | ✅ |
| `CANCELLING` + Host lifecycle clean EOF → diagnostic only | `_late_host_lifecycle_rejection_reason:3775-3776` → `_REASON_HOST_LIFECYCLE_AFTER_ACTIVE_CANCEL` | `test_host_lifecycle_after_run_cancelling_is_diagnostic_only`（parametrized clean_eof + worker_lost） | ✅ |
| `CANCELLING` + Host lifecycle worker lost → same as clean EOF | 同上 | 同上 | ✅ |
| `CANCELLING` + other Engine events → reject/ignore by existing rules | `_late_engine_event_rejection_reason` 对非 terminal / 非 CANCELLING 路径返回 `None` | `test_late_awaiting_after_cancel_does_not_move_to_waiting` | ✅ |

watchdog terminal owner 未被篡改：所有 `CANCELLING` 下 lifecycle signal 只写 `HOST_LIFECYCLE_DIAGNOSTIC`（`event_class=DIAGNOSTIC`），`active_cancel_watchdog_closeout_in_transaction` 仍是唯一写入 `RUN_CANCELLED` terminal fact 的路径。

### 4.2 WAITING/SUSPENDED confirmation

- `_late_engine_event_rejection_reason`：仅当 `run.status is WAITING` 且 `attempt.status is SUSPENDED` 且 event type 为 `RUN_SUSPENDED` / `TOOL_AWAITING` 时放行（`engine_ingest.py:3741-3747`）。
- waiting confirmation 匹配通过 `_validate_waiting_confirmation` 检查 Host accepted refs 与 active wait record 的一致性。
- `stop_worker_stream`：确认成功时 `stop_worker_stream=True`（停止 worker stream 进入等待），确认失败时 `stop_worker_stream=False`。

### 4.3 Reactive compaction gate

- 旧：`latest.attempt.terminal_event_id is None`（S3-CR-F01）。
- 新：`not is_terminal_attempt_status(latest.attempt.status)`（`engine_ingest.py:1934`）。
- 测试 `test_reactive_compaction_gate_consumes_terminal_attempt_status_truth` 通过 `monkeypatch.setattr` 拦截 `is_terminal_attempt_status` 验证 gate 输入是 `AttemptStatus`。

### 4.4 Worker clean EOF / crash

- `_close_worker_lifecycle`（`engine_ingest.py:2651-2741`）：构造 `_HostLifecycleCloseoutCandidate`，不构造 `EngineEvent` 或 `EngineEventCandidate`。
- clean EOF → `_lost_lifecycle_plan`（`FAILED` closeout）或调用方指定 plan。
- worker lost → `_lost_lifecycle_plan`（`LOST` closeout）。
- 测试 `test_worker_clean_eof_closeout_uses_host_lifecycle_identity_and_source` / `test_worker_lost_closeout_uses_lost_event_ids_and_duplicate` 验证 event id、source、payload ref 正确。

### 4.5 Active cancel closeout

- Engine 路径：`_close_active_cancel` → `active_cancel_closeout_in_transaction`，校验 `cancel_request_event_id` 与 Run row typed link 匹配。
- Watchdog 路径：`active_cancel_watchdog_closeout_in_transaction`，校验 `RUN_CANCELLING` + `CANCEL_REQUESTED` dual facts 存在。
- `terminate` 尝试 CAS `terminal_closeout_in_transaction` 失败 → `_TerminalCloseoutRollback` → transaction rollback。

---

## 5. _TerminalFactPlan 共享真正 canonical facts；Engine/Host plans/candidates 静态闭合

**Verdict：PASS**

- `_TerminalFactPlan` 只包含 `attempt_event_type`、`run_event_type`、`attempt_status`、`run_status`、`reason`、`terminal_payload`。均为两类来源的真正 canonical 字段。
- `_EngineTerminalPlan` 与 `_HostLifecycleTerminalPlan` 字段集合互斥（`dataclasses.fields` 测试精确断言），编译期可区分。
- 无 optional-field probing：每条 closeout path 的类型是 `_EngineTerminalPlan` 或 `_HostLifecycleTerminalPlan`，不是带互斥 optional 的单一 dataclass。
- 无 `hasattr`/`getattr`、compatibility wrapper、god-bag。
- `_HostLifecycleCloseoutCandidate` 字段均为必填（`envelope`、`observed_at`、`worker_event_index`、`plan`、`lifecycle_source`），不用 optional-field 区分来源。
- Engine-origin 与 Host-lifecycle-origin 各有一组 typed plan builder（`_final_answer_plan`、`_run_failed_plan`、`_run_cancelled_plan`、`_lost_lifecycle_plan` 等），静态闭合，无 `**kwargs` 或 `extra_payload`。

---

## 6. Lifecycle helper import boundary/cycle、deterministic ordering、Attempt SUSPENDED/STEERED durable-only vs closeout-supported subset

**Verdict：PASS**

### 6.1 Import boundary

```
dayu.host.api
  → RunStatus, AttemptStatus, HostTerminalStatus（定义层）

dayu.host.lifecycle_events
  → imports api（RunStatus, AttemptStatus）
  → does NOT import durable.state, run_transition, engine_ingest

dayu.host.durable.state
  → imports api + _row_rules
  → does NOT import lifecycle_events

dayu.host.durable.run_transition
  → imports lifecycle_events helpers + state helpers

dayu.host.engine_ingest
  → imports lifecycle_events helpers + state helpers
```

验证结果：`python -c "from dayu.host.lifecycle_events import ...; import dayu.host.durable.state; import dayu.host.durable.run_transition; import dayu.host.engine_ingest; print('import-ok')"` 通过。

### 6.2 Deterministic ordering

- `serialized_run_status_values` 对 `frozenset` 输入按 `RunStatus` 定义顺序输出（`state.py:579-580`），对 `tuple` 输入保留调用方顺序。SQL 参数稳定。
- `run_status_in_clause` 空集合 fail-fast（不生成 `IN ()` 非法 SQL）。
- `event_type_values` / `attempt_event_type_values` 保留输入 tuple 顺序。

### 6.3 SUSPENDED/STEERED 分层

- `attempt_terminal_event_type_for_status`：支持全部 6 个 Attempt terminal status（含 SUSPENDED/STEERED）。适用于 durable-only terminal projection（如 recovery dispatch 读 Attempt 终态历史）。
- `closeout_attempt_terminal_event_type_for_status`：只支持 4 个 closeout-supported status（不含 SUSPENDED/STEERED）。closeout path 使用此 helper，对 SUSPENDED/STEERED fail-fast（`ValueError`）。
- 测试覆盖：`test_attempt_terminal_event_type_for_status_rejects_non_terminal` 验证非 terminal fail-fast；`test_attempt_terminal_to_status_roundtrip` 验证 supported subset 一致性。

---

## 7. Propagation audit：同一事实跨 durable state、EventLog、diagnostic、HostEvent/read model/outbox/memory/LLM-facing output 是否同源

**Verdict：PASS**

| 语义事实 | 产生 → 校验 → 持久化 → 投影 | 一致性 |
|---|---|---|
| Run terminal event type | `lifecycle_events.run_terminal_event_type_for_status(status)` → `TerminalCloseoutInput` → `terminal_closeout_in_transaction` → EventLog `event_type` + Run row `status` | ✅ 同源：一条 `TerminalCloseoutInput` 同时写入 EventLog 与 status row |
| Attempt terminal event type | `lifecycle_events.closeout_attempt_terminal_event_type_for_status(status)` → `TerminalCloseoutInput` → `terminal_closeout_in_transaction` → EventLog `event_type` + Attempt row `status` | ✅ 同源 |
| Run status predicate | `state.TERMINAL_RUN_STATUSES` → `is_terminal_run_status` → late rejection / admission / read model / purge | ✅ 全部消费同一 `is_terminal_run_status` 或 `run_status_in_clause` |
| Worker lifecycle closeout | `_HostLifecycleCloseoutCandidate` → `event-host-lifecycle-*` ids + `host.worker_lifecycle` source → `terminal_closeout_in_transaction` → EventLog + status rows | ✅ 与 Engine-origin 共享同一 durable closeout transaction |
| HOST_LIFECYCLE_DIAGNOSTIC | `event_class=DIAGNOSTIC`，`event_type=HOST_LIFECYCLE_DIAGNOSTIC`，不进入 CANONICAL_FACT | ✅ memory projection 只消费 CANONICAL_FACT + CONTEXT_COMPACTED；outbox terminal item 只从 RUN_SUCCEEDED/FAILED/CANCELLED 派生 |
| Direct cancelability | `state.is_dispatch_record_direct_cancelable(record)` → `command.py:_is_predispatch_starting_run` | ✅ command 调用 durable owner helper，不直接读 `worker_accepted_*` |

无"显示正确但持久化错误"或"trace 正确但 memory 错误"的语义分裂。

---

## 8. 测试覆盖

**Verdict：PASS（含 1 个 LOW coverage note）**

### 8.1 Public path 覆盖

| 测试文件 | 覆盖内容 | 测试数（估计） |
|---|---|---|
| `test_lifecycle_events.py` | owner enum、terminal set、fail-fast、roundtrip | ~40 |
| `test_state_schema.py` | status derivation、exact member sets、SQL helper、predicate | ~80 |
| `test_run_attempt_transitions.py` | transition CAS、terminal closeout、replay、watchdog | ~50 |
| `test_engine_ingest_mapping.py` | final answer / failed / cancel / lost closeout、worker EOF/lost、typed plans、late rejection、reactive compaction gate、transaction rollback | ~150 |
| `test_active_cancel_dispatch.py` | active cancel dispatch path | ~15 |
| `test_recovery_dispatch.py` | recovery dispatch path | ~20 |
| `test_public_cancel_session_runs.py` | public cancel session runs API | ~10 |
| `test_public_run_api.py` | public run API terminal status predicate | ~5 |

### 8.2 Adversarial 测试覆盖

- **Invalid row shape fail-closed**：`test_late_rejection_uses_status_even_when_terminal_refs_are_missing` 构造 status=FAILED 但 terminal refs=None 的异常 shape，验证 late routing 仍拒绝。
- **Transaction rollback**：4 条测试分别覆盖 Engine invalid-state / Host invalid-state / Engine CAS-lost / Host CAS-lost，每条比较真实 SQLite payload rows、descriptor、EventLog、status 的 before/after snapshot。
- **Duplicate/race**：`test_worker_lost_closeout_uses_lost_event_ids_and_duplicate` 验证 DUPLICATE 幂等；`test_engine_terminal_cas_lost_rolls_back_real_payload_repository` 验证 CAS-lost 回滚。
- **Identity mismatch**：`test_host_lifecycle_ingress_rejects_mismatched_run_identity` 通过 `monkeypatch.setattr` 注入错 identity row，验证 fail-closed。
- **Predicate injection**：`test_reactive_compaction_gate_consumes_terminal_attempt_status_truth` 通过 `monkeypatch.setattr` 拦截 `is_terminal_attempt_status`，验证 gate 真实消费 status owner。

### 8.3 Coverage note（LOW）

`test_dispatch_scheduler.py` 和 `test_phase5_local_execution_integration.py` 未在本次 required test list 中列出。当前 323 passed 已覆盖 plan 要求的全部测试类别。若后续 WU 要求 end-to-end 集成覆盖，可作为补充。

---

## 9. AGENTS.md 合规

**Verdict：PASS**

| 约束 | 验证 | 结果 |
|---|---|---|
| 中文 docstring | `lifecycle_events.py`、`state.py`、`run_transition.py`、`engine_ingest.py` 所有新增/修改函数均含中文 docstring | ✅ |
| 严格类型 | 无 `Any` / `object` / 无类型参数 / 无类型返回值（全量 scan 零匹配） | ✅ |
| 无 `hasattr`/`getattr` seam | 全量 changed files scan 零匹配 | ✅ |
| 无魔法字符串重复 | terminal event string 唯一真源在 `lifecycle_events.py`；reason 常量在模块级私有变量集中定义 | ✅ |
| 无兼容性代码 | 无 re-export、compatibility wrapper、compatibility 常量 | ✅ |
| README 触发 | `dayu/host/README.md` 已按 S3 implementation 更新（描述 Engine/Host lifecycle 两条 typed path） | ✅ |
| 模块间依赖最小化 | import graph 无循环，无反向依赖 | ✅ |

---

## 10. Scope 边界

**Verdict：PASS — 无 P3-B/P3-J 扩张**

- 未发现 P3-B final answer / outbox continuity 修改。
- 未发现 P3-J EventLog schema hardening 修改。
- 非 terminal EventLog 常量仍保持现有分散定义，作为 P3-J residual input 记录。
- 未发现新 public API、新 `RunStatus`/`AttemptStatus` 成员、schema migration 或 dispatch state machine 修改。

---

## Aggregate Finding Summary

### Material defect findings：0

无新 material defect。全部 4 项 S3-CR finding（F01-F04）已确认修复，S3 re-review 两路均 PASS。

### Residual risks

| ID | Severity | Owner/Destination | 描述 |
|---|---|---|---|
| P3-A-AGG-R1 | LOW | P3-J EventLog schema hardening | `run_transition.py` 与 `engine_ingest.py` 中非 terminal EventLog 常量（`_EVENT_TYPE_RUN_ACCEPTED`、`_EVENT_TYPE_CANCEL_REQUESTED` 等）尚未收敛到 `lifecycle_events.py` owner。P3-A 只收敛了 terminal event source-of-truth。 |
| P3-A-AGG-R2 | LOW | Future state.py CAS hardening | `state.py` 中 CAS mutation helpers 的 `NOT EXISTS (SELECT 1 ... status IN (?, ?, ?, ?, ?))` 仍使用内联 `serialize_run_status(...)` 参数列表（约 5 处），未使用 `run_status_in_clause`。新增 `RunStatus` 时需人工审查。已有 `START_BLOCKING_RUN_STATUSES` owner test 间接守卫。 |
| P3-A-AGG-R3 | INFO | P3-B final answer / outbox continuity | terminal closeout 的 `terminal_summary_ref` / `terminal_summary_digest` / `engine_event_ref` 字段由 P3-A 正确写入 EventLog，但 final answer / outbox terminal item 的内容投影和 LLM-facing continuity 由 P3-B 后续消费。P3-A 未改变 P3-B 的输入 contract。 |
| P3-A-AGG-R4 | INFO | Cross-process stress testing | Engine-origin 与 Host-lifecycle 对同一 Attempt 的并发 terminal closeout 正确性由 `BEGIN IMMEDIATE` + unique event id + shared CAS 保证，但未在测试中构造真实跨进程 race。归 production stress / EventLog hardening owner。 |
| P3-A-AGG-R5 | LOW | Admission `allowed_pairs` | `admission.py:4857-4861` 的 `allowed_pairs` 不包含 CANCELLED pair，因为 CANCELLED closeout 走独立的 `active_cancel_closeout_in_transaction` 路径。当前语义正确，但 admission validation 的 `allowed_pairs` 与 `CLOSEOUT_SUPPORTED_ATTEMPT_TERMINAL_EVENT_TYPES` 存在语义重叠——两者都表达"closeout 支持的 terminal status pair"。建议后续 WU 将 admission 的 pair validation 也收敛到 lifecycle owner helper，消除 admission 层对 closeout-supported subset 的独立定义。 |

### Uncovered areas（非 finding — 已知边界）

| 区域 | 原因 |
|---|---|
| P3-B final answer / outbox continuity | 独立 WU，P3-A plan non-goal |
| P3-J EventLog schema hardening（非 terminal 常量） | 独立 WU，P3-A plan non-goal |
| Engine runner assembly / Engine contracts | 不属于 Host lifecycle WU |
| Wait record lifecycle / wait poller abandon | P3-A plan rejected (SM-5) |
| `FollowupSnapshot` recovering accepted | P3-A plan rejected (SM-7 with needs-more-evidence) |
| Session timeline cursor | P3-A plan rejected (SM-8) |
| Cross-process multi-Attempt concurrent stress | 归 production stress / EventLog hardening |
| `_EVENT_TYPE_RUN_ACCEPTED` 等非 terminal 常量全局 owner | P3-A 只收敛 terminal event，非 terminal 归 P3-J/future |
| `test_dispatch_scheduler.py` / `test_phase5_local_execution_integration.py` | 未在 plan required test list 中；323 passed 已覆盖所有 plan-required 类别 |

---

## Verdict

**Aggregate PASS — 0 material defect finding。**

P3-A 的 S1（lifecycle/status owner helpers）、S2（terminal status/event consumer migration）、S3（Host lifecycle closeout and lifecycle predicates）三个 slice 均已在 review head `3649c9ea` 下闭合。10 项 aggregate adversarial focus 全部通过。4 项 S3-CR finding 已确认修复，S3 re-review 两路均 PASS，controller adjudication 接受。

生命周期 event/status 唯一真源从 `_row_rules`（text-level truth）→ `state.py`（typed frozenset + predicates + SQL helper）→ `lifecycle_events.py`（typed enum + mapping + fail-fast）→ `run_transition.py`（producer）→ EventLog → durable rows → read/admission/purge/query → projection/outbox/memory 全链路闭合。

---

## Completion

- Verdict：**PASS**。
- Material defect finding：**0**。
- Residual risks：5（全部 LOW/INFO，均有后续 owner）。
- Uncovered areas：8（全部为已知 P3-A non-goal 或独立 WU scope）。
- Artifact path：`docs/reviews/wu-semantic-ownership-01-p3-a-aggregate-deepreview-ds.md`。
