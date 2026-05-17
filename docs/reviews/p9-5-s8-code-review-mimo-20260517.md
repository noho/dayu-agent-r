# P9.5 S8 Engine Wait Confirmation Matching-Ref Hardening — Code Review (AgentMiMo)

## Gate

- Role: AgentMiMo, review-only.
- Gate: P9.5 S8 Engine Wait Confirmation Matching-Ref Hardening code review.
- Approved plan: `docs/host/p9-5-pre-p10-hardening-plan.md` section S8.
- Implementation artifact: `docs/reviews/p9-5-s8-engine-wait-confirmation-matching-ref-implementation-20260517.md`.
- Reviewed files: `dayu/host/engine_ingest.py`, `tests/host/test_engine_ingest_mapping.py`, `dayu/host/README.md`, `tests/README.md`.
- No code, tests, plan, or artifacts were modified. No commit, push, or PR.

## Review Focus Verification

### 1. EngineEventIngestor 对 TOOL_AWAITING / RUN_SUSPENDED 是否只能在 Host durable accepted wait record 与 canonical refs 全部匹配时记为 confirmation

**结论：通过。**

**核心匹配逻辑**（`engine_ingest.py` `_validate_waiting_confirmation`，新增 ~1249-1340 行）：

六层递进校验，全部通过才返回 `accepted=True`：

| 层 | 校验内容 | 拒绝原因 |
|---|---|---|
| 1 | `Run.status == WAITING` 且 `Attempt.status == SUSPENDED` | `run_attempt_not_waiting` |
| 2 | `read_active_wait_records_for_run` 按 `attempt_id` + `execution_id` 过滤后恰好 1 条 | `active_wait_record_not_unique` |
| 3 | wait record `status == WAITING` | `active_wait_record_not_waiting` |
| 4 | 回读最新 `TOOL_AWAITING` / `RUN_WAITING` / `ATTEMPT_SUSPENDED` canonical rows，校验 envelope identity（session/run/attempt/execution）、event_id/sequence 与 wait record created/updated refs、payload 中 wait_id/tool_call_id/tool_name/adapter_key/resume_policy/await_spec/snapshot/external_job_ref 一致性 | `accepted_wait_refs_mismatch` |
| 5 | Engine `ToolAwaitingData` / `RunSuspendedData` 的 awaiting record 与 Host accepted wait record 的 tool_call_id/tool_name/await_spec/deadline/snapshot 匹配 | `awaiting_tool_identity_mismatch` / `awaiting_spec_mismatch` / `awaiting_deadline_mismatch` / `awaiting_snapshot_mismatch` |
| 6 | `RunSuspendedData` 额外校验 `reason == TOOL_AWAITING` 且 `awaiting_records` 恰好 1 条 | `run_suspended_reason_mismatch` / `run_suspended_awaiting_record_count_mismatch` |

**confirmation 路径**（`_confirm_waiting_engine_event`）：
- `_validate_waiting_confirmation` 返回 `check`。
- `check.accepted == True` → reason 为 `"waiting_event_confirmation"`，payload 写入 `waiting_confirmation_accepted=True`、`wait_id`。
- `check.accepted == False` → reason 为 `"waiting_event_without_host_accepted_refs"`，payload 写入 `waiting_confirmation_accepted=False`、`waiting_confirmation_mismatch_reason`。
- 两种路径都只写 diagnostic event，不创建 wait record、不推进 Run/Attempt 状态。

**envelope identity 校验**（`_waiting_event_row_matches_context`）：校验 `EventClass.CANONICAL_FACT` + `session_id` + `run_id` + `attempt_id` + `execution_id`，基于 envelope 而非 in-process 对象引用，兼容未来 RemoteProxy。

### 2. Missing / mismatch / wrong attempt / wrong execution / old Attempt late confirmation 是否只 diagnostic / rejection，不创建 wait record、不推进 WAITING、不追加 canonical tool fact

**结论：通过。**

**代码路径验证**：
- `_validate_waiting_confirmation` 只读取 durable truth（`read_active_wait_records_for_run`、`read_latest_run_event_by_type`），不写任何行。
- `_confirm_waiting_engine_event` 调用 `_append_diagnostic_event` 写入 `EventClass.DIAGNOSTIC` event，不调用 `insert_wait_record` 或状态 mutation helper。
- `_canonical_tool_event_count` 在测试中验证确认前后 canonical count 不变（仍为 1，即 accept path 写入的那个）。

**测试覆盖**：

| 测试 | 场景 | 验证 |
|---|---|---|
| `test_tool_awaiting_confirms_only_matching_host_accepted_wait_refs` | 匹配 confirmation | `status==ACCEPTED`, `reason=="waiting_event_confirmation"`, `accepted==True`, `wait_id` 匹配, Run=WAITING, Attempt=SUSPENDED |
| `test_run_suspended_confirms_only_matching_host_accepted_wait_refs` | 匹配 confirmation | 同上 + `ATTEMPT_SUSPENDED` event 写入 |
| `test_tool_awaiting_rejects_mismatched_engine_record_without_state_change` | await_spec 不匹配 | `accepted==False`, `mismatch_reason=="awaiting_spec_mismatch"`, canonical count 不变, Run/Attempt 状态不变 |
| `test_waiting_confirmation_wrong_attempt_identity_is_rejected` | 错 attempt_id | `REJECTED`, `reason=="stale_execution_id"`（走 existing stale execution rejection） |
| `test_waiting_confirmation_wrong_execution_identity_is_rejected` | 错 execution_id | `REJECTED`, `reason=="stale_execution_id"`, canonical count 不变 |
| `test_old_attempt_late_waiting_confirmation_is_rejected_after_resolve` | resolve 后 late confirmation | `REJECTED`, `reason=="terminal_already_closed"`（existing late rejection） |

### 3. 是否违反 Host / Engine 边界、引入 Engine contract 修改、RemoteProxy / exactly-once / recovery / callback / poller 语义

**结论：通过。无违反。**

| 约束 | 验证 |
|---|---|
| Engine contract 修改 | ✅ 未修改 `dayu.engine.contracts`，只 import 已有 `ToolAwaitingData`、`RunSuspendedData`、`RUN_SUSPENDED_REASON_TOOL_AWAITING` |
| Host / Engine 边界 | ✅ `_validate_waiting_confirmation` 只在 Host transaction 内读取 durable truth，不向 Engine 写入 |
| RemoteProxy / wire protocol | ✅ 未引入；envelope identity 校验（session/run/attempt/execution）基于 durable row 字段，不依赖 in-process 对象引用 |
| Exactly-once delivery | ✅ 未引入 |
| Recovery / callback / poller | ✅ 未引入 |
| 新 wait state transition | ✅ 未引入，stop condition 未触发 |
| `resolve_wait` first-committer-wins 语义变更 | ✅ 未变更 |

### 4. 是否符合 AGENTS 硬约束

**结论：通过。无违反。**

| 约束 | 验证 |
|---|---|
| 禁止 `Any`/`object`/无类型签名 | ✅ 所有新增函数有完整类型签名 |
| 中文 docstring | ✅ 所有新增函数/dataclass 有中文 docstring |
| 无 magic string | ✅ 新增事件类型常量 `_EVENT_TYPE_TOOL_AWAITING` / `_EVENT_TYPE_RUN_WAITING` / `_EVENT_TYPE_ATTEMPT_SUSPENDED`；mismatch reason 用字符串常量（诊断内部，非 public error code） |
| 无兼容 wrapper | ✅ 未引入 |
| 无反向依赖 | ✅ `engine_ingest.py` import `dayu.host.durable.state.WaitRecordRow` / `read_active_wait_records_for_run`（同层） |
| 不新增 public facade | ✅ `_validate_waiting_confirmation` 是 private module-level function |
| README 只同步当前行为 | ✅ `dayu/host/README.md` 准确描述匹配契约，`tests/README.md` 同步覆盖说明 |

### 5. 测试是否覆盖 S8 要求

**结论：通过。**

S8 plan 要求的测试矩阵：

| 要求 | 测试 | 状态 |
|---|---|---|
| accepted refs replay（TOOL_AWAITING） | `test_tool_awaiting_confirms_only_matching_host_accepted_wait_refs` | ✅ |
| accepted refs replay（RUN_SUSPENDED） | `test_run_suspended_confirms_only_matching_host_accepted_wait_refs` | ✅ |
| mismatched Engine awaiting record | `test_tool_awaiting_rejects_mismatched_engine_record_without_state_change` | ✅ |
| wrong attempt | `test_waiting_confirmation_wrong_attempt_identity_is_rejected` | ✅ |
| wrong execution_id | `test_waiting_confirmation_wrong_execution_identity_is_rejected` | ✅ |
| old Attempt late confirmation | `test_old_attempt_late_waiting_confirmation_is_rejected_after_resolve` | ✅ |
| missing refs（Run not WAITING） | `_validate_waiting_confirmation` 第一层检查覆盖 | ✅ |
| missing refs（no active wait record） | `_validate_waiting_confirmation` 第二层检查覆盖 | ✅ |

全部 38 targeted tests passed，pyright 0 errors。

## Findings

### F1 [Info] mismatch reason 使用字符串常量而非 enum

- **File/line**: `engine_ingest.py` `_validate_waiting_confirmation` / `_waiting_confirmation_rejected` / `_engine_awaiting_record_mismatch`
- **Evidence**: `"run_attempt_not_waiting"`、`"active_wait_record_not_unique"`、`"accepted_wait_refs_mismatch"`、`"awaiting_spec_mismatch"` 等字符串作为 `mismatch_reason` 写入 diagnostic payload。
- **Impact**: 这些是 internal diagnostic reason，不是 public error code。字符串在 `_validate_waiting_confirmation` 和 `_engine_awaiting_record_mismatch` 中使用，不出现在 public facade 或 HostApiError 中。若未来需要结构化查询 diagnostic，可考虑改为 StrEnum，但当前只写入 diagnostic event payload 的 `waiting_confirmation_mismatch_reason` 字段，对 consumer 无格式承诺。
- **Blocking**: No.

### F2 [Info] _accepted_waiting_refs_or_none 回读三个 canonical event 的冗余性

- **File/line**: `engine_ingest.py` `_accepted_waiting_refs_or_none`（~1370-1440 行）
- **Evidence**: 回读 `TOOL_AWAITING`、`RUN_WAITING`、`ATTEMPT_SUSPENDED` 三个 latest canonical event 并逐一校验 payload。wait record 的 `created_event_id` / `updated_event_id` 已经指向这两个 row，第三个 `RUN_WAITING` 通过 `_run_waiting_payload_matches_wait` 校验 wait_id 和 `tool_awaiting_event_ref`。
- **Impact**: 三层回读 + payload 校验提供纵深防御。即使 wait record 的 refs 被某种方式篡改，canonical event payload 的一致性检查仍能捕获。这是 design.md 要求的 "Validate accepted refs against current run_id, attempt_id, execution_id, wait_id, and accepted ack refs available to ingest" 的直接实现。
- **Blocking**: No.

## Scope Adherence Verification

### Confirmed: plan boundaries honored

- 变更文件：`engine_ingest.py`、`test_engine_ingest_mapping.py`、`README.md`、`tests/README.md`。
- 未修改 `waiting.py` 或 `tool_runtime.py`（plan 允许但不需要）。
- 未修改 Engine contract。
- 未新增 public facade 或 public error code。

### Confirmed: no prohibited semantics introduced

- No new wait state transitions
- No `resolve_wait` first-committer-wins change
- No RemoteProxy / wire protocol
- No callback endpoint / poller / recovery
- No `Any`/`object`/untyped signatures
- No compatibility re-export/wrapper

## P9.5 Scope / Non-Goals Check

| Concern | Status |
|---|---|
| New wait state transitions | Not introduced |
| Engine contract changes | Not introduced |
| RemoteProxy / wire protocol | Not introduced |
| Callback endpoint | Not introduced |
| Poller / recovery | Not introduced |
| `resolve_wait` semantics change | Not introduced |
| New public facade | Not introduced |
| `Any`/`object`/untyped signatures | Not introduced |

## Summary

- **Blocking findings**: 0
- **Non-blocking findings**: 0
- **Info observations**: 2 (F1–F2)

S8 实现正确达成计划目标：`EngineEventIngestor` 对 `TOOL_AWAITING` / `RUN_SUSPENDED` 通过六层递进校验（Run/Attempt 状态 → active wait record → wait record status → canonical refs → payload identity → Engine awaiting record）确认 Host accepted refs，全部通过才记为 confirmation；missing / mismatch / wrong attempt / wrong execution / old Attempt late confirmation 只写 diagnostic / rejection，不创建 wait record、不推进 WAITING、不追加 canonical tool fact；envelope identity 校验基于 durable row 字段兼容未来 RemoteProxy；未引入 Engine contract 修改、RemoteProxy、exactly-once、recovery、callback、poller 语义。无硬约束违反。
