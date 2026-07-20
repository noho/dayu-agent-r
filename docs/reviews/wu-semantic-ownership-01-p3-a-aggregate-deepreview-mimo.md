# WU-SEMANTIC-OWNERSHIP-01 P3-A Aggregate Deep Review — AgentMiMo

## Gate / scope

- Work unit：`WU-SEMANTIC-OWNERSHIP-01 / P3-A — Host lifecycle, run status, and terminal event source of truth`。
- Review base：`2400a04c`（accepted plan bookkeeping 后、S1 implementation 前）。
- Review head：`3649c9ea`。
- Reviewer：AgentMiMo。
- Review type：aggregate adversarial deep review，跨 S1/S2/S3 全量变更。
- 只做 review，不修改生产代码/测试/README/control doc，不 commit/push/PR。

## Verdict

**PASS with 2 accepted low/medium findings** — P3-A 语义所有权修复跨三个 slice 闭合，核心目标全部达成。发现 1 项 medium severity（`_read_active_run_id` SQL status 硬编码残留）和 1 项 low severity（`NOT EXISTS` 子查询 status set 未迁移），均不阻塞 P3-A acceptance，建议在后续 durable state hardening 或 P3-J 中修复。

## Required validation 执行结果

```text
# P3-A affected test matrix（332 tests）
pytest tests/host/test_lifecycle_events.py tests/host/test_state_schema.py \
  tests/host/test_run_attempt_transitions.py tests/host/test_engine_ingest_mapping.py \
  tests/host/test_public_run_api.py tests/host/test_active_cancel_dispatch.py \
  tests/host/test_recovery_dispatch.py tests/host/test_public_cancel_session_runs.py \
  tests/host/test_phase5_local_execution_integration.py tests/host/test_dispatch_scheduler.py -q
332 passed in 3.83s

# pyright
0 errors, 0 warnings, 0 informations

# git diff --check 2400a04c..3649c9ea
(clean)

# Terminal constant source scan
rg "_EVENT_TYPE_(RUN|ATTEMPT)_(SUCCEEDED|FAILED|CANCELLED|LOST)" dayu/host/durable/run_transition.py dayu/host/engine_ingest.py
(exit 1 — clean, no matches)

# Synthetic EngineEvent construction scan
rg "EngineEvent\(|type=EngineEventType\.RUN_FAILED|RunFailedData\(" dayu/host/engine_ingest.py
(exit 1 — clean, no matches)

# Legacy _TerminalPlan scan
rg "_TerminalPlan[^A-Za-z]" dayu/host/engine_ingest.py
(exit 1 — clean, no matches)

# hasattr/getattr scan
rg "hasattr|getattr" dayu/host/engine_ingest.py dayu/host/durable/state.py dayu/host/command.py
(exit 1 — clean, no matches)

# Import cycle validation
python -c "from dayu.host.lifecycle_events import ...; import dayu.host.durable.state; import dayu.host.durable.run_transition; import dayu.host.engine_ingest; print('import-ok')"
import-ok
```

## Adversarial focus 逐项裁决

### 1. 生命周期 event/status 唯一真源跨 S1/S2/S3 闭合

**结论：通过。**

S1 建立的 owner helper 链路完整：

- `RunStatus` → `lifecycle_events.run_terminal_event_type_for_status()` → `HostRunEventType`
- `AttemptStatus` → `lifecycle_events.attempt_terminal_event_type_for_status()` → `HostAttemptEventType`
- `AttemptStatus` → `lifecycle_events.closeout_attempt_terminal_event_type_for_status()` → closeout subset
- `_row_rules.TERMINAL_RUN_STATUS_VALUES` → `state.TERMINAL_RUN_STATUSES` → `state.is_terminal_run_status()`
- `_row_rules.TERMINAL_ATTEMPT_STATUS_VALUES` → `state.TERMINAL_ATTEMPT_STATUSES` → `state.is_terminal_attempt_status()`

S2 迁移的消费者：

- `run_transition.py`：删除 8 个 terminal `_EVENT_TYPE_*` 常量，`_attempt_terminal_event_type` / `_run_terminal_event_type` 委托 owner helper；`_TERMINAL_STATUS_PAIRS` 改为从 owner 派生。
- `engine_ingest.py`：删除 8 个 terminal `_EVENT_TYPE_*` 常量，`_final_answer_plan` / `_run_failed_plan` / `_failed_terminal_fact_plan` / `_closeout_attempt_event_type` / `_run_terminal_event_type` 全部委托 owner helper。
- `admission.py`：删除 `_is_terminal_run_status`，改用 `state.is_terminal_run_status`。
- `read_model.py`：删除 `_TERMINAL_RUN_STATUSES`，改用 `state.is_terminal_run_status`。
- `state.py`：`read_active_run_for_session` / `read_non_terminal_runs_for_session` / `read_non_terminal_runs` 改用 `run_status_in_clause` helper。
- `purge.py`：`_NON_TERMINAL_RUN_STATUS_VALUES` / `_TERMINAL_RUN_STATUS_VALUES` 改用 `serialized_run_status_values`。

S3 修复的深层问题：

- `_late_rejection_reason` 拆分为 `_late_engine_event_rejection_reason` 和 `_late_host_lifecycle_rejection_reason`，均使用 `is_terminal_run_status` / `is_terminal_attempt_status`，不读取 nullable terminal refs。
- worker EOF/crash 从 synthetic `EngineEvent(RUN_FAILED)` 改为 `_HostLifecycleCloseoutCandidate`，Host lifecycle identity namespace (`event-host-lifecycle-`) 与 Engine namespace (`event-engine-`) 不相交。
- `command.py` 的 `_is_direct_cancelable_dispatch_record` 下移到 `state.is_dispatch_record_direct_cancelable`。

### 2. 是否仍有重复 terminal mapping / terminal status set / SQL hardcoded IN

**结论：有 2 项残留，见 Finding F01 / F02。**

全量扫描 `dayu/host` 结果：

- `run_transition.py` 和 `engine_ingest.py` 的 terminal `_EVENT_TYPE_*` 常量已全部删除（source scan clean）。
- `admission.py` 的内联 terminal tuple 已删除。
- `read_model.py` 的 `_TERMINAL_RUN_STATUSES` 已删除。
- `state.py` 的 `_is_terminal_run_status` 私有 helper 已删除，替换为公开 `is_terminal_run_status`。
- `state.py:_TERMINAL_ATTEMPT_STATUSES` 已升级为公开 `TERMINAL_ATTEMPT_STATUSES`。
- **残留 1**：`state.py:_read_active_run_id`（line 6486）仍硬编码 `status IN (?, ?, ?, ?, ?)`，与 `START_BLOCKING_RUN_STATUSES` 语义重复。
- **残留 2**：`state.py` 的 4 个 `NOT EXISTS` 子查询（lines 3219/3305/3772/4051）硬编码 5-status 集合。

### 3. Engine-origin 与 Host-lifecycle-origin typed path、identity namespace

**结论：通过。**

- 两条 typed closeout path 编译期分离：`_close_terminal` 接收 `_EngineTerminalPlan`，`_close_host_lifecycle_terminal` 接收 `_HostLifecycleTerminalPlan`。
- identity namespace 不相交：Engine 使用 `event-engine-{digest}`，Host lifecycle 使用 `event-host-lifecycle-{digest}`。
- Host lifecycle candidate 不伪造 Engine event ref；`_host_lifecycle_ref` 只是治理来源标签。
- `_duplicate_terminal_result` 拆分为 `_duplicate_engine_terminal_result` 和 `_duplicate_host_lifecycle_terminal_result`。
- `_HostLifecycleCloseoutCandidate` 字段全部必填，无 optional probing。
- `_TerminalCloseoutRollback` 异常保证 non-UPDATED terminal mutation 触发整笔事务回滚。

### 4. Active cancel、WAITING/SUSPENDED confirmation、recovery 的组合状态机反例

**结论：通过。**

Active cancel decision table 已验证：

| Run 状态 | Incoming fact | 实际行为 | 测试覆盖 |
|---|---|---|---|
| `CANCELLING` | Engine `FINAL_ANSWER` | late terminal rejected | `test_late_run_failed_after_run_cancelling_is_rejected_with_diagnostic` |
| `CANCELLING` | Engine `RUN_FAILED` | late terminal rejected | 同上 |
| `CANCELLING` | Host lifecycle clean EOF | diagnostic only, no terminal fact | `test_host_lifecycle_after_run_cancelling_is_diagnostic_only` |
| `CANCELLING` | Host lifecycle worker lost | diagnostic only, no terminal fact | 同上（parametrized） |

WAITING/SUSPENDED confirmation exception：`_late_engine_event_rejection_reason` line 3743-3749 保留 `RunStatus.WAITING` + `AttemptStatus.SUSPENDED` 时返回 `None`（允许 waiting confirmation event 通过）。

Reactive compaction gate：`_execute_reactive_compaction` line 1933 改用 `is_terminal_attempt_status(latest.attempt.status)`，不再读取 nullable `terminal_event_id`。测试 `test_reactive_compaction_gate_consumes_terminal_attempt_status_truth` 通过 monkeypatch 验证。

### 5. `_TerminalFactPlan` 共享是否只包含真正 canonical facts

**结论：通过。**

- `_TerminalFactPlan`（6 fields）：`attempt_event_type`、`run_event_type`、`attempt_status`、`run_status`、`reason`、`terminal_payload` — 全部是两类来源共享的 canonical fact。
- `_EngineTerminalPlan`（10 fields）：`terminal` + Engine 专属字段（`finish_reason`、`filtered`、`degraded`、`error_code`、`message`、`provider_request_id`、`client_correlation_id`、`recoverable`、`unsupported_later_owner`）。
- `_HostLifecycleTerminalPlan`（8 fields）：`terminal` + Host lifecycle 专属字段（`error_code`、`message`、`recoverable`、`worker_lifecycle_signal`、`stream_error_code`、`last_observed_worker_event_index`、`last_accepted_event_id`）。
- 两个 plan 类型字段互斥（除 `terminal`），编译期静态分离。
- 测试 `test_terminal_plans_use_lifecycle_event_owner_helpers` 断言字段集合精确匹配。
- 无 god-bag、无 optional probing、无 hasattr/getattr。

### 6. lifecycle helper 的 import boundary / deterministic ordering

**结论：通过。**

Import graph 验证：
```text
dayu.host.lifecycle_events -> dayu.host.api（RunStatus, AttemptStatus, HostTerminalStatus）
dayu.host.durable.state -> dayu.host.api + durable row rules
dayu.host.durable.run_transition -> dayu.host.lifecycle_events + dayu.host.durable.state
dayu.host.engine_ingest -> dayu.host.lifecycle_events + dayu.host.durable.state
dayu.host.admission -> dayu.host.durable.state
dayu.host.command -> dayu.host.durable.state
```

无循环依赖。`lifecycle_events` 不导入 `durable.*`。`durable.state` 不导入 `lifecycle_events`。

`_TERMINAL_STATUS_PAIRS` 改为 `_derive_terminal_status_pairs()` 运行时派生，从 `TERMINAL_ATTEMPT_STATUSES` + `closeout_attempt_terminal_event_type_for_status` + `TERMINAL_RUN_STATUSES` + `run_terminal_event_type_for_status` 交叉验证。`SUSPENDED` / `STEERED` 被 closeout helper 排除。

### 7. Propagation audit

**结论：通过。**

逐条验证：

| 传播路径 | 真源 | 验证 |
|---|---|---|
| Run terminal event type | `RunStatus` → `lifecycle_events.run_terminal_event_type_for_status` | transition tests assert EventLog event_type equals helper value |
| Attempt terminal event type | `AttemptStatus` → `lifecycle_events.closeout_attempt_terminal_event_type_for_status` | transition tests + engine ingest mapping tests |
| Run status predicate | `_row_rules.TERMINAL_RUN_STATUS_VALUES` → `state.TERMINAL_RUN_STATUSES` → consumers | state schema tests assert derivation; consumers call `state.is_terminal_run_status` |
| Worker lifecycle closeout | Host lifecycle candidate → `event-host-lifecycle-*` ids → shared terminal transaction | tests assert ids start with `event-host-lifecycle-`, source is `host.worker_lifecycle` |
| Late event rejection | `is_terminal_run_status` / `is_terminal_attempt_status` | late rejection helpers use predicates, not nullable refs |
| Direct cancelability | `state.is_dispatch_record_direct_cancelable` | command.py calls helper; tests cover 5 status/accept combos |

durable state、EventLog、diagnostic、projection、用户/LLM 可见输出没有从不同真源重建同一 lifecycle/status 事实。

### 8. 测试覆盖

**结论：通过，覆盖充分。**

| 测试文件 | 测试数 | 覆盖范围 |
|---|---|---|
| `test_lifecycle_events.py` | 新增 149 行 | Run/Attempt terminal event type helper、closeout subset、fail-fast |
| `test_state_schema.py` | 新增 286 行 | terminal status derivation、start-blocking explicit set、SQL helper、query equivalence |
| `test_engine_ingest_mapping.py` | 新增 733 行 | terminal plan type separation、worker clean EOF/lost identity、active cancel decision table、invalid-state rollback、CAS-lost rollback、host lifecycle ingress guard、reactive compaction gate |
| `test_active_cancel_dispatch.py` | 新增 60 行 | dispatch record direct-cancelable predicate 5-case parametrized |
| `test_run_attempt_transitions.py` | 新增 39 行 | terminal closeout status pair invariant from lifecycle owner |
| `test_public_run_api.py` | 修改 8 行 | 使用 `TERMINAL_RUN_STATUSES` 替代内联 frozenset |

覆盖了 public path、SQL/query-plan equivalence、invalid row shape fail-closed、transaction rollback（4 条 adversarial 测试比较 sqlite payload/descriptor/EventLog/status 前后快照）、duplicate/race。无脆弱 private-only 测试或错误正向断言。

### 9. AGENTS.md 合规

**结论：通过。**

| 检查项 | 结论 |
|---|---|
| 完整中文 docstring | 通过。新增/修改函数均有完整中文 docstring（参数、返回值、异常） |
| 严格类型 | 通过。pyright 零错误 |
| 无 `Any`/`object`/无类型参数/返回值 | 通过 |
| 无 `hasattr`/`getattr` seam | 通过（scan clean） |
| 无魔法字符串重复 | 通过。prefix、source、actor、reason 常量集中定义 |
| 无 God function / dataclass | 通过。`_TerminalFactPlan`(6)、`_EngineTerminalPlan`(10)、`_HostLifecycleTerminalPlan`(8) 字段明确 |
| 无兼容性代码 | 通过。无 compat wrapper/re-export/facade |
| README 触发正确 | 通过。`dayu/host/README.md` 已按 S3 controller validation 更新 |

### 10. Scope：不得扩张 P3-B/P3-J

**结论：通过。**

- 未触碰 P3-B final answer / outbox continuity。
- 未修改 EventLog schema 或非 terminal EventLog 常量统一（按 plan 归 P3-J）。
- 未引入 schema migration、dispatch state machine 或 wait lifecycle 变更。
- 未修改 `docs/host/issues-implementation-control.md`（control doc 不在 review 范围）。

## Findings

### F01 — `_read_active_run_id` SQL status 硬编码残留

**Severity**：Medium

**File:line**：`dayu/host/durable/state.py:6486`

**直接反例**：

```python
# state.py:6472-6499 — _read_active_run_id
def _read_active_run_id(transaction: HostTransaction, session_id: str) -> str | None:
    row = transaction.fetchone(
        f"""
        SELECT run_id
        FROM {TABLE_HOST_RUNS}
        WHERE session_id = ?
          AND status IN (?, ?, ?, ?, ?)    # <-- hardcoded
        ORDER BY accepted_event_sequence ASC, run_id ASC
        LIMIT 1
        """,
        (
            session_id,
            serialize_run_status(RunStatus.ACCEPTED),
            serialize_run_status(RunStatus.RUNNING),
            serialize_run_status(RunStatus.WAITING),
            serialize_run_status(RunStatus.CANCELLING),
            serialize_run_status(RunStatus.RECOVERING),
        ),
    )
```

与已迁移的 `read_active_run_for_session`（line 1660）语义完全相同，但未使用 `run_status_in_clause(START_BLOCKING_RUN_STATUSES)`。

**Owner root cause**：S2 迁移了公开 `read_active_run_for_session` 但遗漏了私有 `_read_active_run_id`。两者使用相同 status set，但 `_read_active_run_id` 是独立副本。

**影响**：`_read_active_run_id` 被 `session_snapshot_from_row`（line 5069）调用，是用户可见 `SessionSnapshot.active_run_id` 的来源。新增非终态 `RunStatus` 时，`read_active_run_for_session` 会自动包含新状态（因为 `START_BLOCKING_RUN_STATUSES` 从 `NON_TERMINAL_RUN_STATUSES` 派生），但 `_read_active_run_id` 会遗漏。

**最佳实践最小修复**：将 `_read_active_run_id` 改为调用 `run_status_in_clause(START_BLOCKING_RUN_STATUSES)`，或直接委托 `read_active_run_for_session` 返回 `run_id`。

**测试要求**：现有 `test_run_status_in_clause_matches_durable_read_queries` 覆盖公开函数但不覆盖私有函数。修复后应增加断言 `_read_active_run_id` 与 `read_active_run_for_session` 对同一 session 返回相同 active run。

**建议**：accepted — 后续 durable state hardening 中修复，不阻塞 P3-A acceptance。

---

### F02 — `NOT EXISTS` 子查询 status set 未从 owner helper 派生

**Severity**：Low

**File:line**：`dayu/host/durable/state.py:3219, 3305, 3772, 4051`

**直接反例**：

```python
# state.py:3219 — promote_queued_run_row
AND NOT EXISTS (
    SELECT 1
    FROM {TABLE_HOST_RUNS} active_run
    WHERE active_run.session_id = ?
      AND active_run.run_id <> ?
      AND active_run.status IN (?, ?, ?, ?, ?)   # <-- hardcoded
)
```

4 个 transition 函数（`promote_queued_run_row`、`start_unstarted_run_row`、`resume_waiting_run_row`、`start_recovering_run_row`）在写入前用 `NOT EXISTS` 子查询检查同一 session 是否有冲突 active run。它们硬编码了与 `START_BLOCKING_RUN_STATUSES` 相同的 5 个状态。

**Owner root cause**：这些是 CAS guard 子查询，不在 S2 的 read helper 迁移范围内。但 status set 语义相同。

**影响**：新增非终态 `RunStatus` 时，这些 guard 可能允许不应并发的 run 同时存在。风险低于 F01，因为这些是写路径 guard 且 `QUEUED` 在当前设计中不与 running 并发。

**最佳实践最小修复**：抽取 `START_BLOCKING_RUN_STATUSES` 的 SQL 片段复用，或在 `_NOT_EXISTS_ACTIVE_RUN_SQL` 模块常量中集中定义。

**测试要求**：现有 transition 测试覆盖 happy path 和 CAS 竞争。修复后应增加测试断言新增 non-terminal status 时 guard 自动包含。

**建议**：accepted — 后续 durable state hardening 中修复。

---

### F03 — 非 terminal EventLog 常量残留（informational）

**Severity**：Informational

**描述**：`run_transition.py` 仍定义 `_EVENT_TYPE_RUN_ACCEPTED`、`_EVENT_TYPE_RUN_QUEUED`、`_EVENT_TYPE_RUN_STARTED`、`_EVENT_TYPE_ATTEMPT_STARTED`、`_EVENT_TYPE_RUN_RECOVERING`、`_EVENT_TYPE_ATTEMPT_RUNNING`、`_EVENT_TYPE_CANCEL_REQUESTED`、`_EVENT_TYPE_RUN_CANCELLING`、`_EVENT_TYPE_RESUME_REQUESTED`、`_EVENT_TYPE_TOOL_RESULT_ACCEPTED`。`engine_ingest.py` 仍定义 `_EVENT_TYPE_RUN_RECOVERING`、`_EVENT_TYPE_ATTEMPT_SUSPENDED`、`_EVENT_TYPE_RUN_WAITING` 等。

这些是非 terminal 常量，按 plan 归 P3-J / EventLog schema hardening scope，P3-A 不处理。

**建议**：deferred — assigned to P3-J。

## Residual risks

| 风险 | 分类 |
|---|---|
| F01 `_read_active_run_id` SQL 硬编码 | assigned to durable state hardening / P3-J |
| F02 `NOT EXISTS` 子查询 status set | assigned to durable state hardening / P3-J |
| 非 terminal EventLog 常量统一 | assigned to P3-J |
| 跨进程 Engine terminal 与 Host lifecycle terminal 同时提交 stress | assigned to production stress / EventLog hardening |
| P3-B final answer / outbox continuity | covered by later approved slice |
| `_TerminalCloseoutRollback` 作为控制流异常（非错误语义） | design pattern choice, no defect |

无未分类 residual risk、blocking open question 或 deferred accepted finding。

## Aggregate compliance summary

| 维度 | 状态 |
|---|---|
| S1 lifecycle/status owner helpers | PASS — 14 accepted findings from S1 review all closed |
| S2 terminal status/event consumer migration | PASS — source scan clean, SQL helper migrated |
| S3 Host lifecycle closeout + lifecycle predicates | PASS — 4 accepted findings from S3 review all closed |
| Cross-slice propagation audit | PASS — all 6 paths verified |
| AGENTS.md compliance | PASS |
| Scope discipline | PASS — no P3-B/P3-J expansion |
| Test coverage | PASS — 332 tests, adversarial rollback/identity/decision-table coverage |
| Type safety | PASS — pyright 0 errors |
| New material defect from fix | 0 |

## Artifact

- artifact path：`docs/reviews/wu-semantic-ownership-01-p3-a-aggregate-deepreview-mimo.md`
- aggregate verdict：**PASS with 2 accepted low/medium findings**
- finding 数：2 accepted（1 medium, 1 low）+ 1 informational deferred
- residual risk 数：6（all assigned to later work units）
- blockers：0
