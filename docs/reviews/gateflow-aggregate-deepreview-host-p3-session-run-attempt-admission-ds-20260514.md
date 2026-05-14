# Aggregate Deepreview: Host Phase 3 Session / Run / Attempt Admission (AgentDS)

- **Reviewer**: AgentDS (deepseek-v4-pro)
- **Date**: 2026-05-14
- **Scope**: Host Phase 3 (P3-S1 .. P3-S6) — Session lifecycle, Run/Attempt state machine, internal admission, queue promotion, cancel, terminal closeout, multiprocess invariants, docs
- **Benchmark**: `docs/host/phase3-session-run-attempt-admission-plan.md`, `docs/host/design.md` §5-§10, `docs/host/implementation-control.md` §Phase 3
- **Branch**: `feat/host-phase3-admission-state-machine`
- **HEAD**: 49fc1d5

## Verification

| Check | Result |
|-------|--------|
| `pytest tests/host -q` | 157 passed in 1.78s |
| `python -m pyright dayu/host tests/host` | 0 errors, 0 warnings, 0 informations |
| `git diff --check` | clean (exit 0) |

## Review Scope

**Production files (5):**

| File | Lines | Purpose |
|------|-------|---------|
| `dayu/host/durable/schema.py` | 485 | DDL, indexes, CHECK constraints, bootstrap |
| `dayu/host/durable/state.py` | 2338 | Row dataclasses, status enums, row codecs, CAS mutation helpers |
| `dayu/host/durable/session_lifecycle.py` | 873 | ensure/create/close Session lifecycle commands |
| `dayu/host/durable/run_transition.py` | 1807 | Run/Attempt/dispatch transition primitives |
| `dayu/host/admission.py` | 1925 | Internal admission service orchestration |

**Test files (5):**

| File | Test Functions | Focus |
|------|---------------|-------|
| `tests/host/test_state_schema.py` | 9 | Schema, index shape, CHECK enforcement, row codec |
| `tests/host/test_session_lifecycle.py` | 9 | Session lifecycle single-process |
| `tests/host/test_run_attempt_transitions.py` | 11 | Transition primitives single-process |
| `tests/host/test_admission_queue.py` | 17 | Admission queue single-process |
| `tests/host/test_admission_multiprocess.py` | 6 | Multiprocess durable invariants |

**Docs (1):** `dayu/host/README.md`

## Findings

### Severity: Non-blocking

**N-1. `_require_event_sequence` 使用硬编码字符串而非 `TABLE_EVENT_LOG` 常量**

- File: `dayu/host/admission.py:1659`
- Evidence:
  ```python
  row = transaction.fetchone(
      "SELECT event_sequence FROM event_log WHERE event_id = ?",
      (event_id,),
  )
  ```
  对比 `dayu/host/durable/schema.py:17` 已定义 `TABLE_EVENT_LOG = "event_log"`，且 `event_log.py:241` 使用 `f"INSERT INTO {TABLE_EVENT_LOG}"` 拼接 SQL。
- Impact: 两者当前值相同（`"event_log"`），不会产生功能 bug。但如果将来表名变更，`schema.py` 中的常量更新不会传播到此硬编码字符串，导致不一致。
- Fix: 将 `"event_log"` 替换为 `from dayu.host.durable.schema import TABLE_EVENT_LOG` 后的 `TABLE_EVENT_LOG`。
- Classification: non-blocking — 不影响当前正确性，属于代码一致性改进。

**N-2. `terminal_run_row` 允许 `WAITING` 作为源状态但 Phase 3 前置检查拒绝它**

- File: `dayu/host/durable/state.py:1518-1530`
- Evidence:
  ```python
  WHERE run_id = ?
    AND status IN (?, ?)   -- RUNNING, WAITING
    AND current_attempt_id = ?
  ```
  同时 `run_transition.py:1470` 的 `_invalid_terminal_precondition` 要求 `run.status == RunStatus.RUNNING`，因此 Phase 3 中 `WAITING` 源状态不可达。
- Impact: `WAITING` 是 forward-looking 设计，为 Phase 7 (`resolve_wait`) 预留。当前 Phase 3 不实现 `WAITING` 状态转换，所以该 CAS 宽松不会产生实际影响。但文档注释（docstring）仅写 "CAS 将 active Run 推进到具体终态"，未明确说明 `WAITING` 是 forward-looking。
- Fix: 在 `terminal_run_row` docstring 中补充说明 `WAITING` 源状态是为后续 phase 预留，Phase 3 调用方通过前置检查保证只传 `RUNNING`。
- Classification: non-blocking — forward-looking 设计，当前不可达，建议补充注释。

### Severity: Observation (informational, no action required)

**O-1. `promote_queued_run_row` 使用 NOT EXISTS 子查询保证 active Run invariant**

- File: `dayu/host/durable/state.py:1307-1343`
- Evidence: `UPDATE ... WHERE status = 'queued' AND NOT EXISTS (SELECT 1 FROM host_runs WHERE session_id = ? AND run_id <> ? AND status IN ('running','waiting','cancelling','recovering'))`
- Impact: 这是 active Run 唯一性的真正守护。`run_transition.py:484` 的 `read_active_run_for_session` 前置检查是 early-exit 优化（避免不必要的 EventLog append）。即使前置检查存在 TOCTOU 窗口，NOT EXISTS 子查询在 SQLite write lock 下提供原子性保证。设计正确。
- Suggestion: 无需修改。

**O-2. EventLog append 先于 CAS mutation，rollback 保证一致性**

- File: `dayu/host/durable/run_transition.py` (promote, cancel, terminal closeout 等函数均遵循此模式)
- Evidence: 所有 transition helper 先 append EventLog，再执行 CAS mutation。CAS 失败时 `_require_*_mutation_updated` 抛出 `HostDurableError`，事务回滚，已追加的 EventLog rows 被丢弃。
- Impact: EventLog append 和 state row mutation 在同一 `BEGIN IMMEDIATE` write transaction 内，SQLite 保证原子性。不存在"orphan EventLog row"问题。
- Suggestion: 无需修改。设计正确。

**O-3. `close_session` 中 EventLog append 在 CAS 之前，回滚覆盖**

- File: `dayu/host/durable/session_lifecycle.py:398-420`
- Evidence: 先 `append_event(SESSION_CLOSED)`, 再 `close_open_session_row` CAS。CAS 失败时重新读取 snapshot 并抛出 `HostApiError`（CAS loser 场景），事务回滚丢弃 SESSION_CLOSED event。
- Impact: 如果并发 close 同一 Session，winner 的 CAS 成功，loser 的事务回滚后重新读取 winner 写入的状态。loser 不会留下孤立 SESSION_CLOSED event。设计正确。
- Suggestion: 无需修改。

**O-4. `cancel_predispatch_starting_in_transaction` 事件追加顺序**

- File: `dayu/host/durable/run_transition.py:725-788`
- Evidence: 顺序为 CANCEL_REQUESTED → ATTEMPT_CANCELLED → RUN_CANCELLED（EventLog append），然后 CAS dispatch record → Attempt → Run。CAS 失败时 `HostDurableError` 触发回滚。
- Impact: 事件顺序表达取消意图的因果链：先表达取消请求，再收口 Attempt，最后收口 Run。CAS 在三层 row 上的原子性由同事务保证。
- Suggestion: 无需修改。

**O-5. `ensure_session` 使用 slot PK 作为隐式幂等，不写 `idempotency_records`**

- File: `dayu/host/durable/session_lifecycle.py:191-208`
- Evidence: `read_session_slot(transaction, scope, slot_key)` 后若已有绑定则直接返回。`create_session` 则使用 `IdempotencyStore` 按 `client_request_id` 幂等。
- Impact: Slot PK `(scope, slot_key)` 天然提供幂等语义——同一 slot 只绑定一个 Session。`ensure_session` 不需要额外幂等记录。`create_session` 需要幂等记录是因为 `bind_slot=true` 时同一 slot 可被不同 `client_request_id` 重绑定。设计正确。
- Suggestion: 无需修改。

**O-6. `_followup_queue_semantic_digest` 不包含 `resolved_execution_target`**

- File: `dayu/host/admission.py:1780-1788`
- Evidence: digest 计算包含 `operation`、`input_digest`、`behavior`、`caller_semantic_digest`、`call_context_digest`，但不包含 `execution_target`。
- Impact: 与 plan 明确要求一致（P3-S4 idempotency contract: "follow-up queue digest 不包含 `resolved_execution_target`"）。`execution_target` 是调用方归一化的结果，不应影响幂等判断。`start_run` 的 digest 包含 `execution_target`，因为它是请求的直接字段。设计正确。
- Suggestion: 无需修改。

**O-7. `host_attempt` CHECK 约束允许 `running` 状态无 terminal refs**

- File: `dayu/host/durable/schema.py:325-338`
- Evidence: CHECK 约束只对 `succeeded/failed/cancelled/suspended/steered/lost` 要求 terminal refs。`starting` 和 `running` 状态不需要 terminal refs。
- Impact: 正确的 schema 设计——`starting` 是 pre-dispatch 状态，`running` 是 active execution 状态，都不应有 terminal refs。Phase 3 虽不实现 `ATTEMPT_RUNNING`，但 schema 覆盖了设计文档定义的完整 Attempt 状态集。
- Suggestion: 无需修改。

**O-8. 多进程测试使用 `multiprocessing.Process`，每个进程独立 SQLite connection**

- File: `tests/host/test_admission_multiprocess.py`
- Evidence: 所有 6 个测试函数使用独立进程，每个进程通过 `create_host_admission_service` 创建自己的 SQLite connection。
- Impact: SQLite 的锁语义在多进程下比多线程更严格（每个进程有独立 file descriptor）。多进程测试验证了真实的跨进程 durable invariant，而非线程级内存共享。测试策略正确。
- Suggestion: 无需修改。

**O-9. `HostDurableError` 仅在同事务 EventLog append 之后、CAS 失败时抛出**

- File: `dayu/host/durable/run_transition.py` (多处)
- Evidence: `_require_run_mutation_updated`、`_require_attempt_mutation_updated`、`_require_dispatch_record_mutation_updated` 在 CAS `rowcount=0` 时抛出 `HostDurableError`。这些调用均在 EventLog append 之后。
- Impact: 如果 CAS 失败的 `HostDurableError` 被抛出且事务回滚，已追加的 EventLog rows 被丢弃。关键点：如果 EventLog append 之后、CAS 之前抛出其他异常（如 Python 运行时错误），同样会触发回滚。`HostDurableError` 不是唯一回滚路径——任何异常都会回滚。设计正确。
- Suggestion: 无需修改。事务回滚语义由 SQLite 和 `HostTransactionRunner` 保证。

**O-10. `_promote_after_release` 在新事务中执行 promotion，失败不影响主事务**

- File: `dayu/host/admission.py:1565-1600`
- Evidence: `cancel_run` 和 `closeout_attempt_terminal` 在释放 active slot 后调用 `_promote_after_release`，该方法打开新事务执行 promotion。promotion 失败仅记录 skip reason，不抛异常。
- Impact: 设计正确——after-commit promotion 在独立事务中执行，即使失败也不会回滚已经提交的主事务（cancel 或 terminal closeout）。queued Run 留在队列中等待下次 wakeup。
- Suggestion: 无需修改。

## Review Goals Assessment

### G1. Phase 3 设计目标是否全部实现

**Status: PASS**

Plan 定义的 P3-S1 到 P3-S6 全部实现：

| Slice | Plan Item | Implementation |
|-------|-----------|---------------|
| P3-S1 | Schema + row codec + CAS helpers | `schema.py` (DDL, indexes, CHECK), `state.py` (row dataclasses, serde, CAS mutations) |
| P3-S2 | Session lifecycle + idempotency | `session_lifecycle.py` (ensure, create, close + idempotency) |
| P3-S3 | Run/Attempt transition primitives | `run_transition.py` (create queued/running, promote, terminal closeout, cancel queued/pre-dispatch) |
| P3-S4 | Admission queue | `admission.py` (start_run with queue/reject/attach_active, submit_followup_queue) |
| P3-S5 | Cancel + terminal closeout | `admission.py` (cancel_run, closeout_attempt_terminal, after-commit promotion) |
| P3-S6 | Multiprocess tests + docs | `test_admission_multiprocess.py` (6 tests), `dayu/host/README.md` |

实现与 plan handoff 文档 (`phase3-session-run-attempt-admission-plan.md`) 完全一致。所有 transition contract table 中 Phase 3 owned 行均已实现。

### G2. EventLog 一致性

**Status: PASS**

逐项验证：

1. **EventLog append 与 state row mutation 同事务**: 所有 5 个生产模块中的 mutating 操作均在 `BEGIN IMMEDIATE` write transaction 内完成。验证点：
   - `session_lifecycle.py`: ensure/create/close 在 `HostTransactionRunner` 事务内
   - `run_transition.py`: 所有 transition helper 接收 `HostTransaction` 参数，不自行管理事务边界
   - `admission.py`: start_run/submit_followup_queue/cancel_run/closeout_attempt_terminal 通过 `HostTransactionRunner` 管理事务

2. **`event_sequence` 全局唯一递增**: `event_log` 表使用 `event_sequence INTEGER PRIMARY KEY AUTOINCREMENT`，SQLite 保证单调递增。多进程测试 `test_admission_event_sequence_is_global_unique_and_increasing` 验证跨进程 sequence 唯一。

3. **CAS 失败时无孤立 EventLog**: 所有 transition helper 遵循 "append EventLog → CAS mutation → 失败则 raise → 事务回滚" 模式。验证 `promote_queued_run_in_transaction` 的 CAS 失败处理：`_require_run_mutation_updated` 在 `rowcount=0` 时 raise `HostDurableError`，触发回滚。

4. **EventLog 作为 canonical fact 源**: `event_class` 字段区分 `canonical_fact`/`preview`/`diagnostic`/`projection_signal`。当前 Phase 3 所有 event 均为 `canonical_fact` class。

5. **幂等记录与 EventLog 同事务**: `IdempotencyStore.record_idempotent_result` 和 `EventLogStore.append_event` 在同一事务内调用。

### G3. Invariant 守护

**Status: PASS**

逐项验证多进程 durable invariant：

| Invariant | Guard Mechanism | Test Coverage |
|-----------|----------------|---------------|
| 同 Session 至多一个 active Run | SQLite partial unique index `host_runs_one_active_per_session` + `promote_queued_run_row` NOT EXISTS 子查询 | `test_same_session_admission_keeps_one_active_run` (multiprocess) |
| 同 slot ensure 只绑定一个 Session | `host_session_slots` PK `(scope, slot_key)` 唯一约束 | `test_same_slot_ensure_returns_one_bound_session` (multiprocess) |
| FIFO promotion 按 accepted `event_sequence` | `host_runs_queue_fifo` index `(session_id, accepted_event_sequence, run_id)` + `ORDER BY accepted_event_sequence ASC, run_id ASC` | `test_queued_followups_promote_by_accepted_sequence` (multiprocess) |
| First-committer-wins (cancel vs promotion) | SQLite write lock + CAS `rowcount=0` 检测 | `test_cancel_queued_vs_promotion_first_committer_wins` (multiprocess) |
| 跨进程幂等 (同一 key + 不同 digest = conflict) | `idempotency_records` PK `(scope_kind, scope_id, idempotency_key)` + semantic digest 冲突检测 | `test_duplicate_followup_idempotency_returns_one_result` (multiprocess) |
| EventLog `event_sequence` 全局唯一递增 | SQLite `INTEGER PRIMARY KEY AUTOINCREMENT` | `test_admission_event_sequence_is_global_unique_and_increasing` (multiprocess) |

**CAS first-committer-wins 深度分析**:

- `promote_queued_run_row`: WHERE `status = 'queued'` AND NOT EXISTS (active Run). 如果并发 cancel 先提交（Run 已变 CANCELLED），promotion 的 CAS `rowcount=0`，返回 `CAS_LOST_OR_NO_LONGER_ELIGIBLE`.
- `cancel_queued_run_row`: WHERE `status = 'queued'`. 如果并发 promotion 先提交（Run 已变 RUNNING），cancel 的 CAS `rowcount=0`，返回 `CAS_LOST`.
- `cancel_running_run_row`: WHERE `status = 'running' AND current_attempt_id = ?`. 如果并发 terminal closeout 先提交（Run 已变 terminal），cancel 的 CAS `rowcount=0`.
- `terminal_run_row`: WHERE `status IN ('running','waiting') AND current_attempt_id = ?`. 如果并发 cancel 先提交，terminal closeout 的 CAS `rowcount=0`.

所有 CAS 竞争场景都有正确的 `rowcount=0` 检测和结构化结果分类。

### G4. Scope 边界

**Status: PASS**

逐项验证 non-goals 未实现：

| Non-goal | Verification |
|----------|-------------|
| Public Host command facade | 未实现。`admission.py` 是 internal module，`HostAdmissionService` 不从包根导出 |
| Engine dispatch | 未实现。dispatch record 只写 `pending`/`cancelled`，无 scheduler/WorkerProxy |
| WorkerProxy / LocalProxy / RemoteProxy | 未实现。代码中无相关类或函数 |
| Scheduler / lane acquire | 未实现。`AdmissionWakeupPort` 只提供 no-op/test spy，不在事务内等待 |
| EngineEvent ingest | 未实现。无 EngineEvent 映射或 ingest 逻辑 |
| ToolRuntime / wait / resolve_wait | 未实现。无 ToolRuntime construction 或 wait management |
| Steer / retry / replay | 未实现。`FollowupBehavior.STEER` 在 admission 中被拒绝（`_throw_invalid_behavior`） |
| Recovery classifier / lease / fencing | 未实现。无 recovery scan 或 Attempt takeover 逻辑 |
| `ATTEMPT_RUNNING` | 未实现。Attempt 只从 STARTING 直接到 terminal closeout |

Scope 严格控制在 Phase 3 implementation-control.md 和 plan 定义的范围内。

### G5. 层合规

**Status: PASS**

逐文件 import 边界验证：

| File | Imports from | Forbidden imports absent? |
|------|-------------|--------------------------|
| `schema.py` | stdlib only | YES |
| `state.py` | `dayu.host.api`, `dayu.host.durable.*` | YES |
| `session_lifecycle.py` | `dayu.contracts.json_value`, `dayu.host.api`, `dayu.host.durable.*` | YES |
| `run_transition.py` | `dayu.host.api`, `dayu.host.durable.*` | YES |
| `admission.py` | `dayu.contracts.json_value`, `dayu.host.api`, `dayu.host.durable.*` | YES |

无任何文件导入 `dayu.engine` / `dayu.fins` / `dayu.service` / `dayu.ui` / `dayu.runtime`。

`dayu.contracts.json_value.JsonValue` 的导入是允许的——它在 contracts 层，属于 Host 与 Engine/ToolRuntime 的共同协作契约，不违反分层方向。

`dayu.host.durable` 不从 `dayu.host` 包根导出。`dayu.host.admission` 不从包根导出。符合 design.md §11 的类型归属规则。

### G6. 测试覆盖

**Status: PASS**

测试矩阵：

| Category | Count | Coverage Area |
|----------|-------|---------------|
| Schema validation | 9 | DDL, index shape, CHECK enforcement, row codec round-trip, status deserializer rejection |
| Session lifecycle | 9 | ensure, create, close, idempotency, concurrent same-slot ensure, close CAS loser |
| Transition primitives | 11 | create running/queued, promote FIFO, terminal closeout (succeeded/failed/lost), CAS loser, cancel queued/pre-dispatch, rollback scenarios |
| Admission single-process | 17 | start with queue/reject/attach_active, followup queue, idempotency replay/conflict, promotion skip/promote, cancel, terminal closeout, rollback before commit, concurrent promotion |
| Admission multiprocess | 6 | slot ensure, active run invariant, idempotency, FIFO promotion, cancel vs promotion race, event sequence global order |

**测试覆盖的失败路径**:

- CAS loser: `test_run_attempt_transitions.py` — `test_promote_queued_run_cas_loser_after_concurrent_promotion`
- Rollback: `test_admission_queue.py` — `test_rollback_before_commit_noop`
- 幂等冲突: `test_admission_queue.py` — `test_start_run_different_digest_returns_conflict`
- 并发 promotion: `test_admission_queue.py` — `test_concurrent_promotion_only_one_succeeds`
- 多进程 race: `test_admission_multiprocess.py` — 6 tests covering slot, active invariant, idempotency, FIFO, cancel vs promotion, event sequence

**潜在测试覆盖差距**:

1. `terminal_run_row` 的 `WAITING` 源状态路径无测试覆盖 — 但这是 forward-looking 设计，Phase 3 不可达。
2. `close_session` CAS loser 路径在 `test_session_lifecycle.py` 中有覆盖。
3. dispatch record `pending → cancelled` 路径在 cancel pre-dispatch starting 测试中有覆盖。

### G7. 延迟风险与文档记录

**Status: DOCUMENTED**

Phase 3 README 和 design docs 明确记录了所有 non-goals 和后续 phase ownership：

- `dayu/host/README.md:92-99`: 明确列出未实现的 9 项能力（public facade, dispatch, scheduler, WorkerProxy, EngineEvent ingest, wait, recovery, artifact cleanup, ToolRuntime）
- `dayu/host/README.md:49`: 明确说明 durable foundation 不实现 public facade, admission orchestration 等
- `dayu/host/README.md:66`: 明确说明 internal admission 不实现 public facade, dispatch, EngineEvent ingest 等

**延迟风险的 phase owner 追踪**:
- Phase 4: public command facade
- Phase 5: scheduler, lane acquire, WorkerProxy, Engine dispatch, `ATTEMPT_RUNNING`
- Phase 7: ToolRuntime, wait, `resolve_wait`
- Phase 8: steer, retry/replay
- Phase 11: recovery classifier, `RECOVERING` dispatch
- Phase 15: `purge_session`

## Blocking / Non-blocking / Residual Risk

### Blocking Findings

**无 blocking finding。**

### Non-blocking Findings

1. **N-1**: `_require_event_sequence` 使用硬编码 `"event_log"` 而非 `TABLE_EVENT_LOG` 常量 — 代码一致性改进，不影响功能。
2. **N-2**: `terminal_run_row` 允许 `WAITING` 源状态但 docstring 未说明 forward-looking 意图 — 建议补充注释。

### Residual Risk

1. **After-commit promotion 失败**: `_promote_after_release` 在新事务中执行。如果 promotion 事务失败（例如 SQLite busy），queued Run 留在队列中。上层通过 `AdmissionWakeupPort` 可实现重试或定时扫描。当前 no-op wakeup 下，queued Run 只能通过手动调用 `promote_next_queued_run` 推进。这是 Phase 5 (scheduler/dispatch) 接管前的预期行为。

2. **Cancel mode 限制**: Phase 3 只支持 `CancelMode.GRACEFUL`。Force cancel 对 `CANCELLING` 状态的处理是后续 Phase 的职责。当前 cancel 测试覆盖了 queued cancel 和 pre-dispatch STARTING cancel，这两种路径都不涉及 active worker 取消传播。

3. **Attempt RUNNING 状态**: Phase 3 schema 定义了 `running` Attempt 状态，但 `terminal_closeout_in_transaction` 的前置检查只允许 `STARTING` Attempt。Attempt 从 `STARTING` 进入 `RUNNING` 需要 Phase 5 (Engine dispatch + `ATTEMPT_RUNNING` event ingest)。当前 Attempt 的生命周期是 `STARTING → terminal`（跳过 RUNNING），这对 Phase 3 测试闭环是正确的。

4. **SQLite 并发写冲突重试**: `HostTransactionRunner` 的 retry policy 只包裹 `SQLITE_BUSY`/`SQLITE_LOCKED` 类错误。CAS `rowcount=0`（业务竞争）不被 retry——这是正确的，CAS loser 应返回结构化结果而非重试。但需要确认 busy retry 的退避参数和次数上限适合预期的多进程并发负载。

5. **事件 ID 前缀硬编码**: `admission.py` 中的 `_EVENT_ID_PREFIX = "event"`、`_RUN_ID_PREFIX = "run"` 等是模块级常量。如果未来多个 admission service 实例需要不同的 ID 命名空间（例如不同 Host instance），这些硬编码前缀可能需要改为可注入参数。当前 Phase 3 单 Host instance 场景下无影响。

## Architecture Boundary Deep-Check

### 导入方向验证

```
dayu.contracts (层间协作契约)
    ↓
dayu.host.api (公共 API 类型)
    ↓
dayu.host.durable (内部 durable foundation)
    ↓
dayu.host.admission (内部 admission 编排)
```

所有 import 遵循 `UI → Service → Host → Engine` 依赖方向。未发现反向导入。

### 类型归属验证

- `SessionStatus`, `RunStatus`, `AttemptStatus` → 在 `dayu.host.api`，不在 `dayu.contracts`
- `SessionSnapshot`, `RunSnapshot`, `FollowupSnapshot` → 在 `dayu.host.api`
- `HostApiError`, `HostApiErrorCode` → 在 `dayu.host.api`
- `SessionRow`, `RunRow`, `AttemptRow`, `DispatchRecordRow` → 在 `dayu.host.durable.state`，不导出
- `IdempotencyRecord`, `IdempotencyScope` → 在 `dayu.host.durable.idempotency`，不导出

与 design.md §11 的类型归属规则一致。

### README 准确性验证

`dayu/host/README.md` (113 lines) 与当前 Phase 3 实现一致：

- Public namespace 列表与 `dayu/host/__init__.py` 导出匹配
- Durable foundation 描述与 `schema.py` + `event_log.py` + `idempotency.py` + `state.py` 匹配
- Internal admission 描述与 `admission.py` 匹配
- "当前未实现" 列表准确反映 Phase 3 non-goals
- 测试命令与实际 test 文件匹配

## Acceptance

**Accepted. No blocking findings.**

Phase 3 实现与 plan handoff 文档完全一致。Schema 设计（partial unique index, FIFO index, CHECK constraints）、CAS mutation（NOT EXISTS 子查询, rowcount=0 检测）、EventLog 一致性（同事务 append + rollback）、幂等（scope/key/digest 三层绑定）、FIFO promotion（accepted event_sequence 排序）、多进程 invariant（6 tests covering 6 invariants）全部通过验证。

157 测试通过，0 pyright 错误，0 pyright 警告。Scope 边界严格遵守 implementation-control.md Phase 3 定义。层合规无违规——无任何 forbidden import。README 与代码一致。

2 个 non-blocking findings（硬编码表名、docstring 不足），5 个 residual risk（均为已记录的 Phase 3 范围外能力）。可以进入 PR 创建阶段。
