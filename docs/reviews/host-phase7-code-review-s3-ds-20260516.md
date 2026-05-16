# Code Review — Host Phase 7 P7-S3 resolve_wait Command And Resume Attempt

## Scope

- Mode: current changes (including fix pass)
- Branch: feat/host-phase7-tool-awaiting-resolve-wait
- Base: HEAD
- Output file: docs/reviews/host-phase7-code-review-s3-ds-20260516.md
- Fix artifact: docs/reviews/host-phase7-fix-s3-resolve-wait-resume-20260516.md
- Included scope:
  - `dayu/host/command.py` — resolve_wait public command
  - `dayu/host/waiting.py` — DefaultHostResolveWaitService、幂等、outcome dispatch
  - `dayu/host/durable/run_transition.py` — resume_run_from_waiting / _terminal_run_from_waiting
  - `dayu/host/durable/state.py` — resume_waiting_run_row
  - `dayu/host/run_input.py` — _resume_wait_message_from_current_start
  - `dayu/host/_event_payload.py` — resume_requested / tool_result_wait_resolution payload
  - `tests/host/test_resolve_wait_command.py` — 6 tests
  - `tests/host/test_phase7_waiting_integration.py` — integration stub
  - `tests/host/test_public_run_api.py` — resolve_wait 移出 deferred unsupported
  - `dayu/host/README.md` / `tests/README.md` — 同步 resolve_wait 行为与测试覆盖
- Excluded scope:
  - P7-S1 / P7-S2 committed changes, plan/design/control docs
  - Engine、contracts、fins、service、ui、recovery、outbox、audit、tool trace read-model
- Parallel review coverage: 无

## Fix Verification

### S3-F1 — 已修复 — LOST 终态重放缺口

- **原始 finding**: `ResolveWaitLostOutcome` 首次 resolve 后 wait record 进入 `LOST`，但 `_resolve_in_transaction` 终态重放分支只接受 `RESOLVED` / `FAILED`，导致同 key、同 digest 的 lost 重试返回 `INVALID_STATE`，违反 public idempotency contract。
- **修复**: `waiting.py:585-586` 将 `WaitRecordStatus.LOST` 纳入终态重放条件，使 `_replay_terminal_resolution` 对三种终态 wait record 统一处理。
- **测试**: `test_resolve_wait_command.py:211-231` 新增 `test_resolve_wait_lost_same_key_replays_terminal_snapshot`，断言 lost 同 key 重放返回同一 `RunStatus.LOST` snapshot 且不追加 EventLog。
- **状态**: 已关闭。

## Findings

未发现实质性问题。

### 逐项验证

#### 1. resolve_wait public command 入口

- **入口**: `command.py:489-512` `resolve_wait(host, wait_id, request) -> RunSnapshot`
- **路径**: `host._transaction_runner()` → `_raise_if_closed()` 守卫 → `DefaultHostResolveWaitService(transaction_runner, event_log_store, idempotency_store)` → `service.resolve_wait(wait_id, request)` → 仅对非重放 resume 结果调用 `host._admission_service.wakeup_port.wake_dispatch()` → `run_snapshot_from_row(result.run)`
- **关闭 handle**: `_transaction_runner()` 调用 `_raise_if_closed()`（`command.py:159`），handle 关闭时抛出 `HostApiError`。
- **缺失 wait**: `waiting.py:575-580` `wait_record is None → HostApiError(NOT_FOUND, retryable=False)`
- **非 WAITING 且非终态**: `waiting.py:593-598` `HostApiError(INVALID_STATE, retryable=False)`
- **幂等冲突**: `waiting.py:601-608` 同 key 异 digest → `IDEMPOTENCY_CONFLICT`；`waiting.py:700-704` 终态重放同 key 异 digest → `IDEMPOTENCY_CONFLICT`
- **结论**: 正确。

#### 2. (wait_id, idempotency_key) 幂等 scope、digest 与冲突/重放

- **scope**: `waiting.py:922-926` `IdempotencyScope(scope_kind="wait_resolution", scope_id=wait_id, idempotency_key=request.idempotency_key)` — scope 是 wait_id，key 是 caller 提供的 idempotency_key。
- **digest**: `waiting.py:929-945` `sha256_digest_json({wait_id, idempotency_key, source, observed_at, outcome})` — 包含所有影响语义的字段。observed_at 的 isoformat 精度参与 digest，要求同 key 重放使用完全一致的 observed_at。
- **WAITING wait + 无 idempotency record**: 进入首次 resolution，按 outcome 分发。
- **WAITING wait + 同 key 同 digest**: `waiting.py:599-609` → `_resolve_wait_result_from_existing`，返回 `idempotent_replay=True`，不追加事实。
- **WAITING wait + 同 key 异 digest**: `waiting.py:601-608` → `IDEMPOTENCY_CONFLICT`，不追加事实。
- **RESOLVED/FAILED/LOST wait + 同 key 同 digest**: `waiting.py:673-706` `_replay_terminal_resolution` → 通过 idempotency record 校验 → `_resolve_wait_result_from_existing`，返回 `idempotent_replay=True`。
- **RESOLVED/FAILED/LOST wait + 无 idempotency record**: `waiting.py:694-699` → `INVALID_STATE` "already resolved by another key"。
- **RESOLVED/FAILED/LOST wait + 同 key 异 digest**: `waiting.py:700-705` → `IDEMPOTENCY_CONFLICT`。
- **结论**: 三种终态（RESOLVED/FAILED/LOST）幂等契约一致；S3-F1 已修复 LOST 缺口。

#### 3. completed / tool-cancelled 原子 resume + commit 后 wake

- **事务边界**: `_resolve_in_transaction` 整体在 `run_write` 内执行（`waiting.py:548-551`）。
- **resume 事务内容**: `resume_run_from_waiting_in_transaction`（`run_transition.py:800-903`）在同一 transaction 内依次：
  1. `_invalid_waiting_resolution_precondition` 校验 Run `WAITING`、Attempt `SUSPENDED`、wait `WAITING`、active_waits 唯一、Run 无 terminal
  2. `append_event(RESUME_REQUESTED)` — payload 引用 wait created/updated event refs
  3. `append_event(TOOL_RESULT_ACCEPTED)` — payload 包含完整 tool fact（wait_id、tool_call_id、tool_name、resolution_kind、tool_fact_kind、result、adapter_key、external_job_ref 等）
  4. `mark_wait_record_resolved_row` — CAS wait WAITING → RESOLVED
  5. `append_event(RUN_STARTED)` — `start_reason=resume`，payload 引用 resume_requested 和 tool_result event refs
  6. `append_event(ATTEMPT_STARTED)`
  7. `insert_attempt` — 新 Attempt row
  8. `resume_waiting_run_row` — CAS Run `WAITING + suspended_attempt_id` → `RUNNING + resumed_attempt_id`，含 `NOT EXISTS` idle-session 互斥子查询
  9. `insert_dispatch_record` — pending dispatch record
- **commit 后 wake**: `command.py:508-511` 仅在 `result.dispatch_record is not None and not result.idempotent_replay` 时调用 `wake_dispatch`，确保只对首次完成的 resume Attempt 触发调度。
- **tool-cancelled 路径**: `waiting.py:613-615` `ResolveWaitCancelledOutcome` 与 `ResolveWaitCompletedOutcome` 走同一 `_resolve_resume` 路径，wait record 进入 `RESOLVED`（非 `CANCELLED`），创建新 Attempt 继续。测试 `test_resolve_wait_tool_cancelled_resumes_as_resolved_wait` 验证。
- **结论**: 原子性正确，事件顺序正确，CAS 保护正确，wake 语义正确。

#### 4. failed / lost terminal closeout

- **failed 路径**: `_resolve_failed` → `fail_run_from_waiting_in_transaction` → `_terminal_run_from_waiting_in_transaction(expected_run_status=FAILED, expected_wait_status=FAILED)`
  - 在同一 transaction 内：precondition → `TOOL_RESULT_ACCEPTED` → `mark_wait_record_failed_row` → `RUN_FAILED` → `terminal_run_row` → 返回 `dispatch_record=None`、`attempt=None`
- **lost 路径**: `_resolve_lost` → `mark_run_lost_from_waiting_in_transaction` → `_terminal_run_from_waiting_in_transaction(expected_run_status=LOST, expected_wait_status=LOST)`
  - 在同一 transaction 内：precondition → `TOOL_RESULT_ACCEPTED`（tool_fact_kind=lost）→ `mark_wait_record_lost_row` → `RUN_LOST` → `terminal_run_row` → 返回 `dispatch_record=None`、`attempt=None`
- **tool lost fact**: `_wait_resolution_payload_plan`（`waiting.py:1031-1043`）对 `ResolveWaitLostOutcome` 设置 `tool_fact_kind=_TOOL_FACT_KIND_LOST`，`result_json` 包含 `reason_code`、`message`、`provider_status_ref`。该 payload 写入 `TOOL_RESULT_ACCEPTED` 事件。
- **测试验证**: `test_resolve_wait_failed_and_lost_close_run_without_resume_attempt` 断言 `failed.status is RunStatus.FAILED`、`failed.current_attempt_id == failed_seeded.attempt_id`（未切换）、`lost.status is RunStatus.LOST`、`lost.current_attempt_id == lost_seeded.attempt_id`。
- **结论**: failed/lost 不创建 resume Attempt，lost 保留 tool lost fact 于 canonical EventLog，正确。

#### 5. RunInputBuilder canonical resume continuity

- **入口**: `run_input.py:1072-1115` `_resume_wait_message_from_current_start(transaction, current_facts)`
- **数据源链路**:
  1. 从 `current_facts.run_started_event` 读取 payload → 检查 `start_reason == "resume"`（`run_input.py:1084-1088`）
  2. 从 payload 中提取 `tool_result_event_ref.event_id`（`run_input.py:1089-1091`）→ 调用 `_event_id_from_payload_ref`
  3. 通过 `read_event_by_id` 读取 `TOOL_RESULT_ACCEPTED` canonical event（`run_input.py:1092`）
  4. 校验 event_type 为 `TOOL_RESULT_ACCEPTED`（`run_input.py:1095-1098`）
  5. 从该 canonical event 的 payload 中读取 wait_id、tool_call_id、tool_name、resolution_kind、tool_fact_kind、result，构造 SystemMessage（`run_input.py:1099-1115`）
- **未读取非真源**: 不读 wait_records 表、不读 dispatch_records 表、不读 idempotency_records 表、不读内存缓存。只从 EventLog canonical events 读取。
- **错误处理**: event 缺失 → `HostDurableError("resume tool result event not found")`；event_type 不匹配 → `_require_event` 抛出；payload 字段缺失 → `_required_payload_text` 抛出。
- **测试验证**: `test_resolve_wait_completed_resumes_run_and_wakes_dispatch` 中 `_build_resume_request` → `builder.build()` 后断言 messages 包含 "Accepted wait result fact:"、wait_id。
- **结论**: 只从 canonical events 重建，不读取非真源，正确。

#### 6. 越界修改检查

- `git diff HEAD --name-only` 仅包含：
  - `dayu/host/` 下 6 个文件
  - `tests/host/` 下 2 个文件
  - `tests/README.md`、`docs/` 下若干文件
- 未修改：`dayu/engine/`、`dayu/contracts/`、`dayu/fins/`、`dayu/service/`、`dayu/ui/`、recovery、outbox、audit、tool trace read-model。
- 新增 import 均为 Host 内部模块间依赖或 contracts 公共类型引用（`ToolAwaitKind`、`ToolAwaitSpec` 等），方向正确。
- **结论**: 无越界修改。

#### 7. README / test_public_run_api 迁移

- **test_public_run_api.py**: `resolve_wait` 从 `test_deferred_public_functions_are_stable_unsupported_without_writes` 移除，相关 import 清理。测试名与 docstring 同步更新为 `retry/replay/purge_session`。`for exc_info` 循环不再包含 `resolve_exc`。
- **dayu/host/README.md**: `resolve_wait` 从 deferred facade 移至新增 "Public Wait Command Path" 节，文档化幂等作用域 `(wait_id, idempotency_key)`、completed/cancelled 原子 resume、failed/lost terminal closeout 语义、commit 后 best-effort wake dispatch、RunInputBuilder resume continuity。deferred facade 列表更新。测试覆盖列表补充 resolve_wait 相关覆盖项。未实现项列表更新（移除已实现的 resolve_wait 条目）。
- **tests/README.md**: 新增 resolve_wait 测试运行命令，public run/wait API 覆盖描述更新。
- **结论**: 契约一致，文档同步正确。

## Open Questions

1. **observed_at 精度与幂等重放**: `_wait_resolution_digest` 使用 `request.observed_at.isoformat()` 参与 digest。Python `datetime.isoformat()` 默认输出微秒精度（`2026-05-16T01:05:07.000000+00:00`），但 SQLite 时间戳格式为毫秒（`2026-05-16T01:05:07.000Z`）。如果 caller 从不同精度来源重建 `observed_at`（例如从 EventLog payload 反序列化后再调用），digest 可能不匹配导致 IDEMPOTENCY_CONFLICT。这是否需要在 public API 文档中约定 observed_at 的精度要求？

2. **WAITING wait + 既有 idempotency record 路径**: `waiting.py:599-609` 当 wait_record 为 WAITING 但 idempotency record 已存在（同 key 同 digest）时，直接返回 `_resolve_wait_result_from_existing`，该函数对 WAITING run 返回 `dispatch_record=None`。此路径在 SQLite 事务原子性保证下实际不可达（idempotency record 与 wait record mutation 在同一事务内提交），仅作为 defense-in-depth。是否需要在注释中标注该路径的不可达性以便后续维护者理解？

## Residual Risk

- **CAS_LOST 与并发压力测试**: 与 P7-S2 的 CAS_CONFLICT 类似，`resume_waiting_run_row` 的 CAS 失败（WAITING + suspended_attempt_id 不匹配或 NOT EXISTS 互斥命中）在 IMMEDIATE transaction 下不可触发。并发 cancel-vs-resolve 竞态测试归 P7-S4。
- **wake_dispatch 失败**: `command.py:508-511` 的 `wake_dispatch` 调用未检查返回值（best-effort）。若 scheduler 临时不可用，pending dispatch record 依赖 scheduler drain loop 后续拾取。当前测试未覆盖 wake_dispatch 抛出异常的场景。
- **INVALID_ATTEMPT precondition 拒绝子分支**: 与 P7-S2 S2-F3 同源——`_invalid_waiting_resolution_precondition` 对 Run 非 WAITING、Attempt 非 SUSPENDED、wait 非 WAITING、active_waits != 1 等拒绝分支无直接测试。当前 `test_resolve_wait_command.py` 的 6 个测试均以合法 WAITING 状态为前提，INVALID_STATE 返回路径仅通过 CAS 失败后 transition.status != UPDATED 间接覆盖。这已在 P7-S2 S2-F3 中标记为低严重度 residual risk。
- **lost 工具事实在 RunInputBuilder 中的处理**: `_resume_wait_message_from_current_start` 仅处理 `start_reason=resume` 的 RUN_STARTED。对于 lost/failed 终态的 Run，不存在 resume Attempt 也不需要 _resume_wait_message。但如果后续有 retry 或 replay 跨 Run 引用 lost 工具事实，需要独立的 fact projection 逻辑。当前不属于 P7-S3 范围。

## Test Coverage Assessment

| 测试 | 覆盖路径 |
|------|----------|
| completed resume + dispatch wake + RunInputBuilder continuity | 主 happy path |
| 同 key 重放无第二 Attempt | 幂等重放（WAITING wait 同 key） |
| 同 key 异 outcome 冲突 | IDEMPOTENCY_CONFLICT |
| failed + lost closeout 无 resume Attempt | 终态 closeout |
| lost 同 key 重放终态 snapshot | S3-F1 修复覆盖 |
| tool-cancelled resume as resolved wait | cancelled → resume |
| P7-S3 integration stub | public entry importable |

## Conclusion

PASS。S3-F1（LOST 终态重放缺口）已修复。resolve_wait public command 的 handle 校验、wait 缺失/非法状态/幂等冲突语义正确；(wait_id, idempotency_key) 幂等 scope 严谨，三种终态重放与冲突语义一致；completed/tool-cancelled 在同一 transaction 内原子关闭 wait、写入必要 canonical facts、创建 resume Attempt 与 pending dispatch，commit 后才 best-effort wake；failed/lost 只做 terminal closeout 不创建 resume Attempt，lost 有 tool lost fact；RunInputBuilder resume continuity 只从 canonical events 重建，不读取非真源；无 Engine/contracts/fins/service/ui/recovery/outbox/audit/tool trace 越界修改；README/test_public_run_api 迁移与当前契约一致。
