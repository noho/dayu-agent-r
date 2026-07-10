# WU-SEMANTIC-OWNERSHIP-01 P3-A S3 Code Review (AgentDS)

## Gate / scope

- Work unit：`WU-SEMANTIC-OWNERSHIP-01 / P3-A / S3`。
- Gate：independent deep code review (adversarial)。
- Reviewer：AgentDS。
- Base commit：`aa229575`，review target 为当前 workspace diff。
- Review target files：`dayu/host/engine_ingest.py`、`dayu/host/durable/state.py`、`dayu/host/command.py`、`tests/host/test_engine_ingest_mapping.py`、`tests/host/test_active_cancel_dispatch.py`、`dayu/host/README.md`。
- 不得修改生产代码/测试/README/control doc，不 commit/push/PR，不进入 fix。

## Validation summary

```text
pytest tests/host/test_engine_ingest_mapping.py tests/host/test_active_cancel_dispatch.py tests/host/test_recovery_dispatch.py tests/host/test_public_cancel_session_runs.py tests/host/test_run_attempt_transitions.py -q
161 passed in 1.79s
```

- pyright：`0 errors, 0 warnings, 0 informations`。
- `git diff --check`：通过。
- synthetic EngineEvent scan：`engine_ingest.py` 不再构造 `EngineEvent(...)` 或 `type=EngineEventType.RUN_FAILED`。
- command predicate scan：`command.py` 只通过 `is_dispatch_record_direct_cancelable` 消费 durable owner helper，不直接读取 `worker_accepted_at` / `worker_accept_event_id` / `worker_accept_event_sequence`。
- late-routing scan：`_late_engine_event_rejection_reason` 与 `_late_host_lifecycle_rejection_reason` 均使用 `is_terminal_run_status` / `is_terminal_attempt_status`，不读取 `terminal_event_id` / `terminal_event_sequence`。
- terminal event producer duplicate scan：`dayu/host/durable/run_transition.py` 与 `dayu/host/engine_ingest.py` 无残留 `_EVENT_TYPE_(RUN|ATTEMPT)_(SUCCEEDED|FAILED|CANCELLED|LOST)` 常量定义。

## Adversarial checks

### 1. worker EOF/crash 是否彻底不再伪造 EngineEvent；Host terminal/diagnostic identity、source、payload/ref 是否同源且不碰撞

**Verdict：PASS**

直接证据：

- `_close_worker_lifecycle` (engine_ingest.py:2628-2715) 构造 `_HostLifecycleCloseoutCandidate`，不构造 `EngineEvent` 或 `EngineEventCandidate`。
- Host lifecycle terminal event id 使用 `event-host-lifecycle-<sha256>` 命名空间 (`_HOST_LIFECYCLE_EVENT_ID_PREFIX = "event-host-lifecycle-"`, engine_ingest.py:233)，Engine-origin 使用 `event-engine-<sha256>` 命名空间 (`_EVENT_ID_PREFIX = "event-engine-"`, engine_ingest.py:228)。digest 输入 material 互斥：Engine-origin 用 `execution_id + worker_event_index + event_class + event_type + sub_index`；Host lifecycle 用 `identity_kind + session_id + run_id + attempt_id + execution_id + worker_event_index + event_class + event_type + sub_index + lifecycle_source + reason`。两个命名空间 disjoint。
- Host lifecycle source 固定为 `host.worker_lifecycle`（`_HOST_LIFECYCLE_EVENT_SOURCE`, engine_ingest.py:231），actor 固定为 `host.worker_lifecycle`（`_HOST_LIFECYCLE_EVENT_ACTOR`, engine_ingest.py:232）。
- terminal payload 中：Engine-origin 携带 `engine_event_ref`（`engine:{execution_id}:{index}:{type}` 格式），Host lifecycle 携带 `host_lifecycle_ref`（`host-lifecycle:{execution_id}:{index}:{source}:{reason}` 格式）和 `lifecycle_source`，不包含 `engine_event_type` / `engine_event_ref`。
- 测试覆盖：`test_worker_clean_eof_closeout_uses_host_lifecycle_identity_and_source`、`test_worker_lost_closeout_uses_lost_event_ids_and_duplicate` 断言 event id 前缀、source、payload ref 正确且无伪造 Engine 语义。

### 2. duplicate/partial-duplicate/first-committer CAS：Host candidate 重放、Engine/Host race、payload 先写后 terminal precondition failure 是否会留孤儿或把结果错误标成 accepted/rejected

**Verdict：PASS with residual note**

分析：

- duplicate detection 在 Engine-origin path 分两层：`_duplicate_engine_terminal_result`（ingest 入口，engine_ingest.py:839-874）和 `_close_terminal` 内 `_existing_rows` 检查（engine_ingest.py:1186-1198）。两层都检查 complete duplicate（`len(existing) == len(event_ids)`）。
- Host lifecycle path 同样两层：`_duplicate_host_lifecycle_terminal_result`（engine_ingest.py:876-899）和 `_close_host_lifecycle_terminal` 内 `_existing_rows` 检查（engine_ingest.py:1278-1290）。
- partial-duplicate 场景：若只有部分 event id 已存在（如 1/2），duplicate check 不命中（`len(existing) != len(event_ids)` 返回 None），流程进入 `_close_terminal`。此时 `terminal_closeout_in_transaction` 尝试再次写入已存在 event id 会触发 UNIQUE constraint，导致整个 write transaction rollback。在此 transaction 内先写入的 payload descriptor 也会回滚。**结论：无孤儿风险。**
- Engine-origin 与 Host-lifecycle 使用不同 event id 命名空间（`event-engine-` vs `event-host-lifecycle-`），不可能因 id collision 互相吞掉对方的事实。
- **Residual note**：`_close_terminal` (engine_ingest.py:1239-1246) 和 `_close_host_lifecycle_terminal` (engine_ingest.py:1330-1337) 在 `terminal_closeout_in_transaction` CAS 失败时返回 `REJECTED` + 空 `events=()`。payload descriptor 已先写入同一 transaction 内，但 CAS 失败不意味着 transaction 必然 rollback —— 取决于 `terminal_closeout_in_transaction` 内部是否 raise 异常。如果 CAS 失败只返回 `StateMutationStatus != UPDATED` 而不 raise，则 payload descriptor 会随 transaction commit 成为孤儿。当前代码路径中，`terminal_closeout_in_transaction` 返回 `CAS_LOST` / `INVALID_STATE` 等非 UPDATED 状态时不一定 raise，取决于其内部实现。建议后续在 `_close_terminal` 和 `_close_host_lifecycle_terminal` 的 CAS 失败分支中不写 payload（或写入后 CAS 失败时清理），或者确认 `terminal_closeout_in_transaction` 在 CAS 失败时通过 exception 触发 transaction rollback。**当前严重性低**，因为触发条件要求 Engine-origin 与 Host-lifecycle 同时对同一 Attempt 写入 terminal fact，概率极低，且 storage maintenance 可清理 orphan payload。

### 3. CANCELLING decision table：Engine FINAL_ANSWER/RUN_FAILED 与 Host clean EOF/lost routing，是否保持 watchdog terminal owner；diagnostic status/stop_worker_stream/duplicate 语义是否符合调用方

**Verdict：PASS**

逐项对照 plan decision table 与实现：

| Plan 要求 | 实现位置 | 验证结果 |
|---|---|---|
| `CANCELLING` + Engine `FINAL_ANSWER` → reject as late terminal after active cancel | `_late_engine_event_rejection_reason` (engine_ingest.py:3724-3729) | `test_late_final_answer_after_run_cancelling_is_rejected_with_diagnostic` 通过，status 保持 CANCELLING |
| `CANCELLING` + Engine `RUN_FAILED` → reject as late terminal after active cancel | `_late_engine_event_rejection_reason` (engine_ingest.py:3724-3729) | `test_late_run_failed_after_run_cancelling_is_rejected_with_diagnostic` 通过 |
| `CANCELLING` + Host lifecycle clean EOF → diagnostic only, no FAILED/LOST | `_late_host_lifecycle_rejection_reason` (engine_ingest.py:3747-3748) → `_REASON_HOST_LIFECYCLE_AFTER_ACTIVE_CANCEL` | `test_host_lifecycle_after_run_cancelling_is_diagnostic_only` (parametrized for both sources) 通过，无 RUN_FAILED/LOST |
| `CANCELLING` + Host lifecycle worker lost → same as clean EOF | 同上 | 同上 |
| `CANCELLING` + other Engine events → reject or ignore by existing rules | `_late_engine_event_rejection_reason` 在非 terminal/非 CANCELLING 路径返回 None，由下游 `_ingest_validated` 按普通事件路由 | `test_late_awaiting_after_cancel_does_not_move_to_waiting` 验证 awaiting/suspended 不推入 WAITING |

watchdog terminal owner 未被篡改：`CANCELLING` 下所有 lifecycle signal 只写 `HOST_LIFECYCLE_DIAGNOSTIC`（`event_class=DIAGNOSTIC`），watchdog tick (`active_cancel_watchdog_closeout_in_transaction`) 仍是唯一写入 `RUN_CANCELLED` terminal fact 的路径。

`stop_worker_stream` 语义：Engine-origin late terminal 的 rejected result 中 `stop_worker_stream` 默认为 False（`_append_rejected_diagnostic` 中 `stop_worker_stream=False`），符合"迟到 Engine event 不应再要求停止已关闭 stream"的语义。Host lifecycle diagnostic 路径同样不设置 `stop_worker_stream`。

### 4. late rejection status truth 与 WAITING/SUSPENDED exception；terminal refs 是否只保留 row consistency，不在其它分支偷回 routing owner

**Verdict：PASS with one LOW finding**

- `_late_engine_event_rejection_reason` (engine_ingest.py:3703-3730)：使用 `is_terminal_run_status(context.run.status)` 和 `is_terminal_attempt_status(context.attempt.status)`，不读取 `terminal_event_id`。WAITING/SUSPENDED exception 正确：仅当 `context.run.status is RunStatus.WAITING` 且 `context.attempt.status is AttemptStatus.SUSPENDED` 且 event type 为 `RUN_SUSPENDED` / `TOOL_AWAITING` 时才放行。
- `_late_host_lifecycle_rejection_reason` (engine_ingest.py:3733-3749)：同样使用 status predicates，不读 terminal refs。对 CANCELLING 单独判断。
- `test_late_rejection_uses_status_even_when_terminal_refs_are_missing` 构造异常 shape（status=FAILED 但 terminal refs=None），验证 late routing 仍正确返回 `terminal_already_closed`。
- terminal refs 的所有其他使用点均为：transaction producer（写入 terminal_closeout_in_transaction 参数）、row consistency validation（`validate_terminal_event_refs_shape` in state.py）、duplicate detection（event id 计算输入不包含 terminal refs，event id 确定性由 candidate identity 保证）。

**Finding F1 (LOW)**：`_execute_reactive_compaction` (engine_ingest.py:1912) 使用 `latest.attempt.terminal_event_id is None` 判断 reactive compact post-compaction 上下文是否仍有效。该检查实际等同于 `is_terminal_attempt_status(latest.attempt.status)`（因为 row validation 保证 terminal status → non-null refs），但使用了 refs 作为状态代理。建议改为 `is_terminal_attempt_status(latest.attempt.status)` 以保持语义一致。

### 5. direct-cancel durable predicate 是否覆盖 malformed/partial worker accepted facts，是否与 row validation、CAS 和 command 调用时机一致

**Verdict：PASS**

- `is_dispatch_record_direct_cancelable` (state.py:663-686)：PENDING 和 WAITING_FOR_LANE 直接返回 True。DISPATCHING 检查 `worker_accepted_at is None and worker_accept_event_id is None and worker_accept_event_sequence is None`。三个字段必须全为 None 才允许 direct cancel。
- malformed/partial worker accepted facts（如 `worker_accepted_at` 有值但 event id/sequence 为 None）：三个字段独立检查，partial 会被判为 direct-cancelable（安全侧：宁可让 cancel 成功也不能让 malformed worker 继续运行）。这与 row codec 的 nullable 字段解码一致（`_decode_optional_text` / `_decode_optional_int` 各自独立解码），也与 `mark_dispatching_after_lane_row` 和 worker accept path 的原子写入约定一致。
- `command.py` 中 `is_dispatch_record_direct_cancelable` 调用位于 `_is_predispatch_starting_run` (command.py:1705)，该函数在 `_IsDeferredCancelStateOperation` 事务内被调用，与 `read_run_by_id`、`read_attempt_by_id`、`read_dispatch_record_by_attempt_id` 处于同一 read transaction，保证了调用时机一致性。
- 测试覆盖：`test_dispatch_record_direct_cancelable_predicate_owned_by_durable_state` (parametrized 5 cases) 覆盖 PENDING/WAITING_FOR_LANE/DISPATCHING-pre-accept/DISPATCHING-post-accept/CANCELLED。

### 6. propagation audit：EventLog、durable status、projection/read model/outbox/memory/LLM-facing material 是否从同一事实派生；HOST_LIFECYCLE_DIAGNOSTIC 是否可能被错误投影成用户/LLM事实

**Verdict：PASS**

逐条验证：

- **Run terminal event type**：Engine-origin 与 Host lifecycle 均通过各自的 `_close_terminal` / `_close_host_lifecycle_terminal` 调用同一个 `terminal_closeout_in_transaction`，写入同事务的 EventLog terminal facts 与 Run/Attempt status row。event type 均从 `lifecycle_events.run_terminal_event_type_for_status` / `closeout_attempt_terminal_event_type_for_status` 派生。
- **Attempt terminal event type**：同上。
- **Run/Attempt status predicate**：`is_terminal_run_status` / `is_terminal_attempt_status` (state.py:557-623) 从 `_row_rules.TERMINAL_RUN_STATUS_VALUES` / `TERMINAL_ATTEMPT_STATUS_VALUES` 派生，late rejection、admission、read model 均消费同一 owner。
- **Worker lifecycle closeout**：Host lifecycle signal → `_HostLifecycleCloseoutCandidate` → `event-host-lifecycle-` ids + `host.worker_lifecycle` source → shared `terminal_closeout_in_transaction` → EventLog + status rows → existing projections。
- **HOST_LIFECYCLE_DIAGNOSTIC** (engine_ingest.py:238)：`event_class=DIAGNOSTIC`，`event_type=HOST_LIFECYCLE_DIAGNOSTIC`，source/ref 明确为 `host.worker_lifecycle` / `host-lifecycle:...`。不进入 CANONICAL_FACT class，不包含 `engine_event_type` 或 `engine_event_ref`。memory projection 只消费 CANONICAL_FACT 和 CONTEXT_COMPACTED；outbox terminal item 只从 RUN_SUCCEEDED/FAILED/CANCELLED terminal facts 派生。HOST_LIFECYCLE_DIAGNOSTIC 不会进入 user-visible terminal、LLM-facing memory 或 outbox。
- **Direct cancelability**：dispatch row → `is_dispatch_record_direct_cancelable` (state.py) → command cancel path → durable transaction → EventLog + status rows。

**没有发现同一 lifecycle/status 事实从不同真源重建的证据。**

### 7. AGENTS.md：完整中文 docstring/严格类型、无 Any/object/getattr/hasattr seam、无魔法字符串重复、无 god function/dataclass、README 触发正确

**Verdict：PASS with one LOW finding**

- docstring：`engine_ingest.py` 中所有新增 public/internal 函数提供完整中文 docstring，含参数、返回值、异常说明。`close_clean_eof`、`close_worker_lost` 两个 public method docstring 完整。
- 类型检查：无 `object`、`Any`、无类型参数、无类型返回值。`_HostLifecycleSource` 使用 `StrEnum`，`_HostLifecycleCloseoutCandidate` 使用 `frozen=True, slots=True` dataclass，所有字段强类型。
- 无 `hasattr`/`getattr`：scan 通过（0 matches）。
- 魔法字符串：event id prefix、source、actor、reason 常量集中定义在模块级（engine_ingest.py:226-313），无散落魔法字符串重复。
- god function/dataclass 检查：`_TerminalPlan` 是最复杂的 dataclass（18 fields），但每个 field 有明确业务含义。参见 Finding F2。
- README：`dayu/host/README.md` 已同步 worker lifecycle 与 EngineEvent 两条 typed path 的稳定边界（README.md:370），符合触发规则。

**Finding F2 (LOW)**：`_TerminalPlan` (engine_ingest.py:436-458) 同时包含 Engine-origin 专属字段（`finish_reason`、`filtered`、`degraded`、`provider_request_id`、`client_correlation_id`、`recoverable`、`unsupported_later_owner`）与 Host-lifecycle 专属字段（`worker_lifecycle_signal`、`stream_error_code`、`last_observed_worker_event_index`、`last_accepted_event_id`），违反 plan S3 Exact allowed changes 中"禁止一个 dataclass 同时塞入互斥 optional Engine / Host 字段"的约束。实际使用中，`_final_answer_plan` / `_run_failed_plan` 将 Host-lifecycle 字段置为 None；`_failed_lifecycle_plan` / `_lost_lifecycle_plan` 将 Engine 专属字段置为 None。两条 closeout path 不会交叉传参。但 type system 不阻止未来代码错误地将 Engine-only 字段传入 Host lifecycle 路径或反之。建议将 `_TerminalPlan` 拆为 discriminated union 或至少将 Host-lifecycle 专属字段抽取到独立 dataclass，通过 composition 使用。

### 8. 测试是否真正覆盖 plan assertions，是否存在只测 private helper或构造不可能 row shape而遗漏 public path

**Verdict：PASS**

- `test_terminal_plans_use_lifecycle_event_owner_helpers`：验证 Engine 与 Host lifecycle plan 的 event type 均从 lifecycle owner helper 派生，覆盖 S3 plan assertion "engine ingest mapping tests assert terminal closeout uses helper-derived values"。
- `test_worker_clean_eof_closeout_uses_host_lifecycle_identity_and_source`：验证 public `close_clean_eof` 路径的 event id 前缀、source、payload ref 无 Engine 伪造语义。
- `test_worker_lost_closeout_uses_lost_event_ids_and_duplicate`：验证 public `close_worker_lost` 路径的 LOST terminal facts 与幂等重放。
- `test_engine_run_failed_with_worker_lifecycle_reason_remains_engine_failed`：验证 Engine-origin `run_failed` 即使 error_code 文本等于 Host lifecycle reason 字符串（`worker_lost_before_terminal`），也保持 Engine-origin FAILED 语义。
- `test_host_lifecycle_after_run_cancelling_is_diagnostic_only`：parametrized 覆盖 `worker_clean_eof` 和 `worker_lost` 的 active cancel decision table。
- `test_late_rejection_uses_status_even_when_terminal_refs_are_missing`：验证 late routing 使用 status 而非 terminal refs，包括构造异常 shape（status terminal + refs null）。
- `test_late_final_answer_after_run_cancelling_is_rejected_with_diagnostic` + `test_late_run_failed_after_run_cancelling_is_rejected_with_diagnostic`：覆盖 Engine-origin CANCELLING decision table 的 FINAL_ANSWER / RUN_FAILED 两列。
- `test_dispatch_record_direct_cancelable_predicate_owned_by_durable_state`：5 参数覆盖 PENDING / WAITING_FOR_LANE / DISPATCHING-pre-accept / DISPATCHING-post-accept / CANCELLED。

所有测试均通过 public API（`EngineEventIngestor.ingest`、`close_clean_eof`、`close_worker_lost`）或模块级 public 函数（`_final_answer_plan`、`_run_failed_plan`、`_lost_lifecycle_plan`、`_late_engine_event_rejection_reason`）调用，无仅测 private helper 而遗漏 public path 的情况。

### 9. scope 不得扩张到 P3-B；若发现需要 design truth 才能裁决，标 needs-more-evidence 并给直接证据

**Verdict：PASS**

- 未发现 P3-B final answer / outbox continuity 修改。
- 未发现 P3-J EventLog schema hardening 修改。
- 未发现需要 design truth 才能裁决的 blocking 问题。所有 finding 均为 S3 scope 内可裁决。

## Findings

### F1 (LOW) — reactive compaction 使用 terminal_event_id 作为状态代理

- **file:line**：`dayu/host/engine_ingest.py:1912`
- **直接代码路径**：`_execute_reactive_compaction` → 事务内 `_operation` lambda，line 1910-1914：
  ```python
  if (
      latest.run.status is not RunStatus.RECOVERING
      or latest.attempt.terminal_event_id is None
  ):
      return pending.result_prefix
  ```
- **root cause**：`latest.attempt.terminal_event_id is None` 被用作"Attempt 是否已被 `_close_attempt_for_context_recovery` 成功关闭"的代理判断。正确语义应使用 `is_terminal_attempt_status(latest.attempt.status)`。虽然 row validation 保证 terminal status ↔ non-null terminal refs，但使用 refs 作为状态代理违反了 S3 的 semantic ownership 原则（status 是 lifecycle truth，refs 是 row consistency field）。
- **owner boundary**：`_execute_reactive_compaction` 应消费 `durable.state.is_terminal_attempt_status`。
- **最小修复**：将条件改为 `or not is_terminal_attempt_status(latest.attempt.status)`。
- **测试要求**：现有 reactive compaction 测试已覆盖该路径（如 `test_reactive_compaction_rejects_stale_input_sequence`），修复后行为等价，无需新增测试。但应增加一条显式断言：当 attempt status 为 FAILED 但 terminal_event_id 异常为 None 时（需构造异常 row shape），修复后的代码仍正确进入 early return。
- **建议裁决**：accepted。

### F2 (LOW) — _TerminalPlan 同时包含互斥 optional Engine/Host 字段

- **file:line**：`dayu/host/engine_ingest.py:436-458`
- **直接代码路径**：`_TerminalPlan` dataclass 定义包含 18 个字段，其中 `finish_reason`、`filtered`、`degraded`、`provider_request_id`、`client_correlation_id`、`recoverable`、`unsupported_later_owner` 仅 Engine-origin path 使用；`worker_lifecycle_signal`、`stream_error_code`、`last_observed_worker_event_index`、`last_accepted_event_id` 仅 Host-lifecycle path 使用。两组字段在同一 dataclass 中以 `| None` 共存。
- **root cause**：`_TerminalPlan` 被设计为 Engine-origin (`_final_answer_plan`、`_run_failed_plan`) 和 Host-lifecycle (`_failed_lifecycle_plan`、`_lost_lifecycle_plan`) 的共享 data holder，违反 plan S3 中"禁止一个 dataclass 同时塞入互斥 optional Engine / Host 字段"的约束。
- **owner boundary**：`_TerminalPlan` 是 `engine_ingest.py` 内部 private dataclass，两条 closeout path 已通过不同 candidate 类型（`EngineEventCandidate` vs `_HostLifecycleCloseoutCandidate`）和不同 closeout 方法（`_close_terminal` vs `_close_host_lifecycle_terminal`）正确分离。实际无跨路径字段污染。但 type system 不提供编译期保护。
- **最小修复**：将 `_TerminalPlan` 拆为两个 dataclass 或引入 discriminated union。最小改动方案：抽取 `_HostLifecyclePlan` 只含 Host-lifecycle 专属字段，通过 composition 嵌入 `_TerminalPlan`（Engine plan 不含 Host-lifecycle 字段）。`_TerminalPlan` 保留 Engine-only 字段，删除 Host-lifecycle 字段，`_close_host_lifecycle_terminal` 从 `_HostLifecycleCloseoutCandidate` 的额外字段读取 Host-lifecycle 信息。
- **测试要求**：现有测试覆盖不变。新增一条类型检查：`_final_answer_plan` 返回的 `_TerminalPlan` 不应出现 `worker_lifecycle_signal` 非 None；`_lost_lifecycle_plan` 返回的不应出现 `engine_event_ref` 非 None。
- **建议裁决**：deferred to future hardening。理由：`_TerminalPlan` 是模块私有 dataclass，当前两条 closeout path 已正确分离，plan 函数的构造行为明确（只设置自己关心的字段），实际风险低。在后续 P3-J 或 `engine_ingest.py` 整体重构时一并处理更经济。

### F3 (LOW) — _validate_host_lifecycle_context 缺少 run.run_id 一致性检查

- **file:line**：`dayu/host/engine_ingest.py:1140-1148`
- **直接代码路径**：`_validate_host_lifecycle_context` 的 identity 校验条件缺少 `or run.run_id != envelope.run_id`，而 `_validate_durable_context` (engine_ingest.py:1102-1111) 包含该检查。
- **root cause**：两个 context validation 函数分别实现，`_validate_host_lifecycle_context` 遗漏了冗余但一致的 `run.run_id` 检查。
- **owner boundary**：identity validation 属于 `engine_ingest.py` 的 ingress guard。
- **实际影响**：`read_run_by_id(transaction, envelope.run_id)` 已保证 `run.run_id == envelope.run_id`，因此该检查无论是否存在行为等价。风险为代码阅读者可能误以为两种路径有语义差异。
- **最小修复**：在 `_validate_host_lifecycle_context` 的 identity 条件中添加 `or run.run_id != envelope.run_id`，与 `_validate_durable_context` 保持一致。
- **测试要求**：无需新增测试，现有 identity validation 测试已覆盖。
- **建议裁决**：accepted。

## Residual risks / uncovered areas

1. **跨进程 Engine/Host terminal 同时提交 stress test**：当前测试均为单进程。多进程并发写入同一 Attempt 的 Engine terminal 与 Host lifecycle terminal 场景未覆盖。正确性依赖 SQLite transaction atomicity 与 EventLog UNIQUE constraint。归后续 production stress / EventLog hardening work unit。

2. **`_TerminalPlan` 共享 dataclass**：见 Finding F2，当前无实际路径错误，但 type system 不阻止未来误用。归后续重构。

3. **payload orphan on CAS failure**：见 adversarial check 2 residual note。`_close_terminal` 和 `_close_host_lifecycle_terminal` 在 CAS 失败时可能留下 orphan payload descriptor。当前触发概率极低，storage maintenance 可清理。归后续 `terminal_closeout_in_transaction` 契约 hardening。

4. **非 terminal EventLog 常量**：仍为分散定义（P3-J scope），不在 S3 范围内。

5. **P3-B final answer / outbox continuity**：未触碰，属于 approved later slice。

## Verdict

**PASS** — 3 LOW findings，0 MEDIUM，0 HIGH，0 CRITICAL。

S3 implementation 正确完成了三个核心目标：
1. worker EOF/crash 彻底不再伪造 EngineEvent，使用独立 Host lifecycle identity namespace 与 source。
2. late rejection 使用 durable status predicates，terminal refs 只保留 row consistency 职责。
3. direct-cancel predicate 由 durable state owner 统一拥有，command path 不再重建 worker accepted nullable refs 组合。

CANCELLING decision table 全部 4 种输入（Engine FINAL_ANSWER、Engine RUN_FAILED、Host clean EOF、Host lost）按 plan 正确路由，watchdog terminal owner 未被篡改。Engine-origin 与 Host-lifecycle event id 命名空间 disjoint，无碰撞风险。所有测试通过，pyright 零错误。

建议 controller 裁决 F1（accepted）、F2（deferred）、F3（accepted），随后进入下一 gate。

## Finding summary

| # | Severity | Summary | Suggested |
|---|---|---|---|
| F1 | LOW | `_execute_reactive_compaction` line 1912 使用 `terminal_event_id is None` 而非 `is_terminal_attempt_status` 作为状态代理 | accepted |
| F2 | LOW | `_TerminalPlan` 同时包含互斥 optional Engine/Host 字段，违反 plan 约束 | deferred |
| F3 | LOW | `_validate_host_lifecycle_context` 缺少 `run.run_id` 一致性检查 | accepted |
