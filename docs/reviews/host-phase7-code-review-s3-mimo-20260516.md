# Code Review

## Scope

- Mode: current changes
- Branch: feat/host-phase7-tool-awaiting-resolve-wait
- Base: main
- Output file: docs/reviews/host-phase7-code-review-s3-mimo-20260516.md
- Included scope: Host Phase 7 P7-S3 resolve_wait Command And Resume Attempt — 当前未提交改动
- Excluded scope: Engine、contracts、fins、service、ui、recovery、outbox、audit、tool trace read-model
- Parallel review coverage: 无

## Findings

未发现实质性问题。

以下是对 7 个审查焦点的逐项 evidence-based 结论：

### 1. resolve_wait public command

`command.py:489-512`：`resolve_wait` 通过 `host._transaction_runner()` 隐式打开 handle，构造 `DefaultHostResolveWaitService` 后委托 `service.resolve_wait()`。dispatch wakeup 在事务提交后执行（`command.py:508-511`），条件为 `dispatch_record is not None and not idempotent_replay`，与 `start_run` 等其他 command 的 handle 使用模式一致。

- wait 缺失：`waiting.py:574-580` → `HostApiErrorCode.NOT_FOUND`
- 状态非法：`waiting.py:593-598` → `HostApiErrorCode.INVALID_STATE`
- 幂等冲突：`waiting.py:602-608` → `HostApiErrorCode.IDEMPOTENCY_CONFLICT`

handle 关闭后访问 `host._transaction_runner()` 会由 HostCommandHandle 内部保护抛出异常，行为与其它 command 一致。

### 2. (wait_id, idempotency_key) 幂等 scope、semantic digest、冲突与重放

- scope：`waiting.py:914-926`，`IdempotencyScope(scope_kind="wait_resolution", scope_id=wait_id, idempotency_key=idempotency_key)`
- digest：`waiting.py:929-945`，`sha256_digest_json({wait_id, idempotency_key, source, observed_at, outcome})`，outcome 内含 kind + result + payload_ref，确保不同 outcome 产生不同 digest
- 非终态同 key 同 digest 重放：`waiting.py:599-609`，读取 idempotency record 后比对 digest，匹配则从 durable truth 重建结果
- 非终态同 key 不同 digest 冲突：`waiting.py:603-608`，抛 `IDEMPOTENCY_CONFLICT`
- 终态重放：`waiting.py:673-706`，对 RESOLVED/FAILED wait record 检查 idempotency record 存在性与 digest 匹配，不匹配则分别抛 `INVALID_STATE` 或 `IDEMPOTENCY_CONFLICT`
- idempotency record 写入时机：`waiting.py:660-670`，在事务内、run 状态转换之后，与 run transition 原子提交

### 3. completed/cancelled 同一 transaction 内原子操作 + commit 后 wake

`run_transition.py:800-903` `resume_run_from_waiting_in_transaction` 在单事务内完成：

1. `append_event(RESUME_REQUESTED)` — line 831-833
2. `append_event(TOOL_RESULT_ACCEPTED)` — line 834-836
3. `mark_wait_record_resolved_row` (CAS on WAITING) — line 838-847
4. `append_event(RUN_STARTED, start_reason=resume)` — line 851-859
5. `append_event(ATTEMPT_STARTED)` — line 860-862
6. `insert_attempt` — line 876
7. `resume_waiting_run_row` (CAS WAITING→RUNNING with suspended_attempt_id) — line 877-886
8. `insert_dispatch_record` — line 890

dispatch wakeup 在 `command.py:508-511` 事务返回后、条件检查通过时才执行，不在事务内。

CAS 失败处理：`waiting.py:768-773`，`StateMutationStatus` 非 UPDATED 时抛 `INVALID_STATE(retryable=True)`。

### 4. failed/lost 只 terminal closeout 不创建 resume Attempt

`run_transition.py:952+` `_terminal_run_from_waiting_in_transaction`：

- `append_event(TOOL_RESULT_ACCEPTED)` — line 991-993
- `mark_wait_record_failed_row` / `mark_wait_record_lost_row` (CAS) — line 995-1016
- `append_event(RUN_TERMINAL)` — line 1022-1027
- `terminal_run_row` + `terminal_attempt_row` — line 1028+

不创建新 Attempt、不创建 dispatch record。`_resolve_failed` 和 `_resolve_lost` 返回 `dispatch_record=None`（`waiting.py:837, 900`）。

lost 的 tool lost fact：`_resolve_lost` 传入 `tool_fact_kind="tool_result_lost"`、`resolution_kind="tool_result_lost"`，payload 含 `reason_code`、`message`、`provider_status_ref`（`waiting.py:1031-1043, 1287-1300`），写入 TOOL_RESULT_ACCEPTED 事件。

### 5. RunInputBuilder resume continuity 只从 canonical events 重建

`run_input.py:1072-1115` `_resume_wait_message_from_current_start`：

1. 从当前 `RUN_STARTED` 事件读取 `start_reason` — line 1083-1087
2. 非 `"resume"` 返回 None — line 1087-1088
3. 从 `RUN_STARTED` payload 的 `tool_result_event_ref` 读取引用事件 id — line 1089-1091
4. `read_event_by_id` 读取 TOOL_RESULT_ACCEPTED 事件 — line 1092
5. 校验事件类型为 TOOL_RESULT_ACCEPTED — line 1095-1098
6. 从 TOOL_RESULT_ACCEPTED payload 构建 system message — line 1099-1115

只读取 `RUN_STARTED` 和其引用的 `TOOL_RESULT_ACCEPTED` 两个 canonical event，不读取 wait record、idempotency record 或其它非真源。

### 6. 边界：未越界修改

变更文件清单（未提交改动中 P7-S3 相关）：

- `dayu/host/command.py` — resolve_wait command
- `dayu/host/waiting.py` — DefaultHostResolveWaitService
- `dayu/host/durable/run_transition.py` — resume/terminal transition functions
- `dayu/host/durable/state.py` — resume_waiting_run_row
- `dayu/host/_event_payload.py` — resume_requested_payload, tool_result_wait_resolution_payload
- `dayu/host/run_input.py` — resume continuity
- `tests/host/test_resolve_wait_command.py` — P7-S3 测试
- `tests/host/test_public_run_api.py` — 移除旧 unsupported 断言
- `dayu/host/README.md`, `tests/README.md` — 文档同步

未修改 Engine、contracts、fins、service、ui、recovery、outbox、audit、tool trace read-model。

### 7. README/test_public_run_api 迁移

- `test_public_run_api.py`：移除了 `resolve_wait` 的 `UNSUPPORTED_OPERATION` 断言和 `ResolveWaitRequest`/`WaitResolutionSource` import，保留 retry/replay/purge deferred unsupported 覆盖
- `dayu/host/README.md`：同步当前 resolve wait 行为说明
- `tests/README.md`：同步测试覆盖事实

## Open Questions

无。

## Residual Risk

- P7-S4 范围的 late result diagnostic、cancel-vs-resolve race 与 CAS_LOST 并发压力测试未实现，属于 P7-S4 非目标。
- `test_resolve_wait_command.py` 未覆盖 handle 已关闭后调用 `resolve_wait` 的行为，但此行为由 HostCommandHandle 内部保护统一处理，非 P7-S3 特有风险。
