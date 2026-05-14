# Aggregate Deepreview: Host Phase 3 Session / Run / Attempt Admission (AgentMiMo)

- **Reviewer**: AgentMiMo (mimo-v2.5-pro)
- **Date**: 2026-05-14
- **Scope**: Host Phase 3 (P3-S1 .. P3-S6) — Session lifecycle, Run/Attempt state machine, internal admission, queue promotion, cancel, terminal closeout, multiprocess invariants, docs
- **Benchmark**: `docs/host/phase3-session-run-attempt-admission-plan.md`
- **Branch**: `feat/host-phase3-admission-state-machine`
- **HEAD**: 49fc1d5

## Verification

| Check | Result |
|-------|--------|
| `pytest tests/host -q` | 157 passed in 2.57s |
| `python -m pyright dayu/host tests/host` | 0 errors, 0 warnings, 0 informations |
| `git diff --check` | clean (exit 0) |

## Review Scope Files

Production:
- `dayu/host/durable/schema.py` — DDL, indexes, CHECK constraints, bootstrap
- `dayu/host/durable/state.py` — Row dataclasses, status enums, row codecs, CAS mutation helpers
- `dayu/host/durable/session_lifecycle.py` — ensure/create/close Session commands
- `dayu/host/durable/run_transition.py` — Run/Attempt/dispatch transition primitives
- `dayu/host/admission.py` — Internal admission service orchestration

Tests:
- `tests/host/test_state_schema.py` — Schema, index shape, CHECK enforcement, row codec
- `tests/host/test_session_lifecycle.py` — Session lifecycle single-process
- `tests/host/test_run_attempt_transitions.py` — Transition primitives single-process
- `tests/host/test_admission_queue.py` — Admission queue single-process
- `tests/host/test_admission_multiprocess.py` — Admission multiprocess durable invariants

Docs:
- `dayu/host/README.md`
- `tests/README.md`

## Findings

### Severity: Observation (informational, no action required)

**O-1. `promote_queued_run_row` 使用 NOT EXISTS 子查询保证 active Run invariant**

- File: `dayu/host/durable/state.py:1307-1343`
- Evidence: `UPDATE ... WHERE ... AND NOT EXISTS (SELECT 1 FROM host_runs active_run WHERE active_run.session_id = ? AND active_run.run_id <> ? AND active_run.status IN ('running', 'waiting', 'cancelling', 'recovering'))`
- Impact: 这是 active Run 唯一性的真正守护。`run_transition.py:484` 的 `read_active_run_for_session` 前置检查是 early-exit 优化，不是 invariant 保证。设计正确——即使前置检查存在 TOCTOU 窗口，NOT EXISTS 子查询仍然在 SQLite write lock 下提供原子性保证。
- Suggestion: 无需修改。前置检查避免了不必要的 EventLog append（如果 active 存在则直接 skip，不 append promotion event），这是正确的优化。

**O-2. `cancel_predispatch_starting_in_transaction` 事件追加顺序**

- File: `dayu/host/durable/run_transition.py:725-788`
- Evidence: 先 append CANCEL_REQUESTED，再 append ATTEMPT_CANCELLED，再 append RUN_CANCELLED，然后依次 CAS dispatch record、attempt、run。
- Impact: 事件追加在 CAS 之前。如果任何 CAS 失败，`_require_*_mutation_updated` 抛出 `HostDurableError`，事务回滚，已追加的事件也被丢弃。这是正确的——EventLog append 在同一事务内，回滚保证一致性。
- Suggestion: 无需修改。

**O-3. `close_session` 中 EventLog append 先于 CAS**

- File: `dayu/host/durable/session_lifecycle.py:398-420`
- Evidence: 先 append SESSION_CLOSED event，再调用 `close_open_session_row` CAS。CAS 失败时读最新状态并抛出 `HostApiError`。
- Impact: 如果 CAS 失败（例如并发 close），已 append 的 SESSION_CLOSED event 会在事务回滚时被丢弃。这不是"孤立 event"——它在同一 SQLite write transaction 内。设计正确。
- Suggestion: 无需修改。

**O-4. `_append_user_input_event` payload 包含冗余 `input_ref` 字段**

- File: `dayu/host/admission.py:1320-1328`
- Evidence: `payload_json` 同时包含 `"input_ref": request.input.payload_ref` 和 `"payload_ref": request.input.payload_digest`。`input_ref` 和 `payload_ref` 值相同。
- Impact: 信息性冗余，不影响正确性。可能是为不同消费者提供两种命名约定。
- Suggestion: 无需修改。payload 内部结构不影响 durable invariant。

**O-5. `ensure_session` 使用 slot PK 作为隐式幂等，不写 `idempotency_records`**

- File: `dayu/host/durable/session_lifecycle.py:191-208`
- Evidence: `existing_slot = read_session_slot(...)` 后直接返回。不经过 `IdempotencyStore`。
- Impact: 设计正确。Slot PK `(scope, slot_key)` 天然提供幂等语义——同一 slot 只绑定一个 Session。`ensure_session` 不需要额外的 idempotency_records 表条目。`create_session` 使用 `IdempotencyStore`，因为它的幂等 key 是 `client_request_id`，不是 slot PK。
- Suggestion: 无需修改。

**O-6. `_followup_queue_semantic_digest` 不包含 `resolved_execution_target`**

- File: `dayu/host/admission.py:1780-1788`
- Evidence: digest 计算包含 `operation`、`input_digest`、`behavior`、`caller_semantic_digest`、`call_context_digest`，但不包含 `execution_target`。
- Impact: 这是 plan 明确要求的行为——follow-up queue digest 不包含 `resolved_execution_target`，因为 target 是调用方归一化的，不应该影响幂等判断。`start_run` 的 digest 包含 `execution_target`，因为它是请求的直接字段。
- Suggestion: 无需修改。与 plan 一致。

**O-7. `host_attempt` CHECK 约束允许 `running` 状态无 terminal refs**

- File: `dayu/host/durable/schema.py:325-338`
- Evidence: CHECK 约束只对 `succeeded/failed/cancelled/suspended/steered/lost` 要求 terminal refs。`starting` 和 `running` 状态不需要 terminal refs。
- Impact: 这是正确的——`running` 是 Phase 3 中 promotion 后 Attempt 可能进入的状态（尽管当前 Phase 3 不实现 Attempt RUNNING 转换）。CHECK 约束覆盖了 schema 定义的所有状态，不仅是 Phase 3 当前使用的状态。
- Suggestion: 无需修改。

**O-8. 多进程测试使用 `multiprocessing.Process` 而非线程**

- File: `tests/host/test_admission_multiprocess.py`
- Evidence: 所有多进程测试使用独立进程，每个进程打开自己的 SQLite connection。
- Impact: 这是正确的测试策略——SQLite 的锁语义在多进程下比多线程更严格（每个进程有自己的 file descriptor）。多进程测试验证了真实的跨进程 durable invariant，而不是线程级内存共享。
- Suggestion: 无需修改。

## Review Goals Assessment

### G1. Phase 3 设计目标是否全部实现

**Status: PASS**

Plan 定义的 P3-S1 到 P3-S6 全部实现：

- P3-S1: Schema (session, slot, run, attempt, dispatch record) + row codec + CAS helpers — `schema.py`, `state.py`
- P3-S2: Session lifecycle (ensure, create, close) + idempotency — `session_lifecycle.py`
- P3-S3: Run/Attempt transition primitives (create queued, create running, promote, terminal closeout, cancel queued, cancel pre-dispatch) — `run_transition.py`
- P3-S4: Admission queue (start_run with queue/reject/attach_active, submit_followup_queue, promote_next_queued_run) — `admission.py`
- P3-S5: Cancel + terminal closeout (cancel_run, closeout_attempt_terminal, after-commit promotion) — `admission.py`
- P3-S6: Multiprocess tests + docs update — `test_admission_multiprocess.py`, READMEs

### G2. EventLog 一致性

**Status: PASS**

- 所有 canonical facts 通过 `EventLogStore.append_event` 在同一 SQLite write transaction 内追加。
- `event_sequence` 使用 `AUTOINCREMENT` 保证全局唯一递增。
- 状态 row mutation（CAS UPDATE）在 EventLog append 之后执行；mutation 失败时 `HostDurableError` 触发事务回滚，不会留下孤立 event 或不一致 state row。
- 多进程测试 `test_admission_event_sequence_is_global_unique_and_increasing` 验证了跨进程 `event_sequence` 唯一递增。

### G3. Invariant 守护

**Status: PASS**

- **同 Session active Run 唯一性**: `host_runs_one_active_per_session` partial unique index + `promote_queued_run_row` NOT EXISTS 子查询双重守护。多进程测试 `test_same_session_admission_keeps_one_active_run` 验证。
- **同 slot ensure 只绑定一个 Session**: slot PK `(scope, slot_key)` 唯一约束。多进程测试 `test_same_slot_ensure_returns_one_bound_session` 验证。
- **跨进程幂等**: `idempotency_records` PK `(scope_kind, scope_id, idempotency_key)` + semantic digest 冲突检测。多进程测试 `test_duplicate_followup_idempotency_returns_one_result` 验证。
- **FIFO promotion**: `host_runs_queue_fifo` index + `ORDER BY accepted_event_sequence ASC, run_id ASC`。多进程测试 `test_queued_followups_promote_by_accepted_sequence` 验证。
- **First-committer-wins**: CAS mutation 在 SQLite write lock 下原子执行。多进程测试 `test_cancel_queued_vs_promotion_first_committer_wins` 验证。

### G4. Scope 边界

**Status: PASS**

Phase 3 实现严格遵守 non-goals：

- 不实现 public Host command facade
- 不实现 Engine dispatch、WorkerProxy、LocalProxy、RemoteProxy
- 不实现 scheduler、lane acquire
- 不实现 EngineEvent ingest、recovery classifier
- 不实现 lease / fencing / takeover
- 不实现 ToolRuntime construction
- 不实现 wait cancellation、steer、retry / replay
- WakeupPort 只允许 no-op 或测试 spy

### G5. 层合规

**Status: PASS**

- `dayu.host.durable` 不从 `dayu.host` 包根导出，不进入 `dayu.host.api`。
- `dayu.host.admission` 不从 `dayu.host` 包根导出，不是 public facade。
- `dayu.host` 不导入 `dayu.engine`、`dayu.fins`、`dayu.service`、`dayu.ui`。
- 所有 import 遵循 `UI -> Service -> Host -> Engine` 依赖方向。
- `business_tool_bundle` 不进入 per-run request dataclass。

### G6. 测试覆盖

**Status: PASS**

测试覆盖全面：

- Schema: partial unique index shape, FIFO index shape, CHECK constraint enforcement, row codec round-trip, status deserializer rejection
- Session lifecycle: ensure, create, close, idempotency, concurrent same-slot ensure
- Transition primitives: create running/queued, promote FIFO, terminal closeout (succeeded/failed/lost), CAS loser, cancel queued/pre-dispatch, rollback
- Admission: start with queue/reject/attach_active, followup queue, idempotency replay/conflict, promotion skip/promote, cancel, terminal closeout, rollback before commit, concurrent promotion
- Multiprocess: slot ensure, active run invariant, idempotency, FIFO promotion, cancel vs promotion race, event sequence global order

157 tests passing, 0 pyright errors。

### G7. 延迟风险

**Status: DOCUMENTED**

Plan 和 README 明确记录了 Phase 3 不实现的能力：

- Public Host command facade、policy provider integration
- 真实 dispatch、dispatching / active worker cancel propagation
- EngineEvent ingest、steer、retry / replay
- Wait cancellation、recovery cancellation
- Session-scope cancel facade
- Artifact cleanup scheduler、diagnostics table
- ToolRuntime construction、policy resolution、framework tool injection
- ToolsDiscovery / ScenePrepare provider contract

这些都是后续 Phase 的职责，不在 Phase 3 scope 内。

## Blocking / Non-blocking / Residual Risk

### Blocking Findings

**无 blocking finding。**

### Non-blocking Findings

无。

### Residual Risk

1. **After-commit promotion 失败**: `_promote_after_release` 在新事务中执行 promotion。如果 promotion 失败（例如 SQLite busy），queued Run 会留在队列中直到下次 wakeup。这是可接受的——WakeupPort 允许上层实现重试策略。
2. **Cancel mode 限制**: Phase 3 只支持 `CancelMode.GRACEFUL`。Force cancel 是后续 Phase 的职责。
3. **Attempt RUNNING 状态**: Phase 3 schema 定义了 `running` Attempt 状态，但 terminal closeout 的前置检查只允许 `STARTING` Attempt。这是正确的——Phase 3 不实现真实 Engine dispatch，Attempt 不会从 STARTING 进入 RUNNING。

## Acceptance

**Accepted. No blocking findings.**

Phase 3 实现与 plan 完全一致。Schema 设计、CAS mutation、EventLog 一致性、幂等、FIFO promotion、多进程 invariant 全部通过验证。157 测试通过，0 pyright 错误。Scope 边界严格遵守，层合规无违规。可以进入 PR 创建阶段。
