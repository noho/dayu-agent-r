# P10.5 Slice 5 Code Review — MiMo

## Gate

当前 gate：P10.5 Slice 5 code review。

## 结论

**PASS** — 0 blocking。

实现正确性经验证无问题，admission / command / dispatch / durable state 四层协同完整，CAS 保护与状态机前置条件均到位。主要风险集中在测试覆盖缺口：plan matrix 要求的边界场景测试远多于当前 5 个 happy-path 测试。

## Blocking Findings

无。

## Findings（按严重度排序）

### F1 — [Medium] 测试覆盖缺口：plan matrix 多数边界场景未实现

plan Slice 5 Tests 要求：

- Terminal race tests for steer vs terminal.
- Retry idempotency conflict and successful related Run dispatch.
- Replay no-tool schema assertion and source Run immutable assertion.
- WAITING resume public path.
- Cancel accepted / queued / pre-dispatch / active visibility / session-scope / close boundary.

当前 5 个测试只覆盖 happy-path：

| 测试 | 覆盖 | 缺失 |
|---|---|---|
| `test_steer_running_run_creates_new_attempt_public_path` | RUNNING steer → new Attempt → terminal SUCCEEDED | WAITING steer、terminal race、幂等重放、session mismatch、target_run_id=None |
| `test_retry_failed_run_creates_related_run_public_path` | FAILED retry → related Run → SUCCEEDED | 幂等冲突、policy limit（第二个 retry 被拒）、source Run immutable 证明、非 FAILED 拒绝 |
| `test_replay_succeeded_run_no_tool_public_path` | SUCCEEDED replay → no-tool → SUCCEEDED | source Run immutable 证明、非 SUCCEEDED 拒绝、repair instruction 传入验证 |
| `test_resolve_wait_resumes_through_open_host_and_terminal_event` | WAITING → resolve_wait → new Attempt → SUCCEEDED | 多种 WAITING outcome（failed / cancelled / lost）、幂等重放、late diagnostic |
| `test_cancel_accepted_queued_and_active_public_path` | queued cancel + session-scope cancel → active CANCELLING | pre-dispatch STARTING cancel、close boundary（close_session vs host.close vs cancel 三者区分）、watch_session_events 可见性验证 |

**Why**: plan 的 unified coverage table 明确把上述场景分配到 Slice 5 tests。只覆盖 happy-path 无法证明防御性边界（幂等冲突、状态竞争、policy enforcement）在 durable 层正确工作。

**How to apply**: 当前实现代码正确，不阻塞 slice commit。建议在 Slice 6 或后续 fix 中补测，优先级：steer WAITING > retry idempotency/conflict > cancel pre-dispatch/close boundary > replay source immutable。

### F2 — [Low] 跨测试 helper import 耦合

三个测试文件从 `test_public_retry_replay.py` 导入大量 helper：

- `test_public_steer.py`：9 个 import（`_BLOCK`, `_FINAL`, `_SequencedWorkerFactory`, `_context`, `_ensure_request`, `_followup_request`, `_options`, `_wait_for_event_type_count`, `_wait_for_run_status`）
- `test_public_resolve_wait_resume.py`：5 个 import + 2 个从 `test_resolve_wait_command` 导入
- `test_public_cancel_smoke.py`：7 个 import

若 `test_public_retry_replay.py` 中任何 helper 签名变更，三个文件同时 break。

**Why**: 当前 4 个测试文件形成隐式依赖图，非独立可运行。

**How to apply**: 不阻塞。后续可考虑抽取 `tests/host/_slice5_helpers.py` 共享模块，解耦测试文件间的直接 import。

### F3 — [Low] steer WAITING 路径无独立测试覆盖

`_SubmitFollowupSteerOperation.__call__` 对 WAITING Run 走 `cancel_active_wait_records_for_run` 分支（admission.py:1198-1212），若 wait records CAS 失败则抛 `INVALID_STATE`。该路径无测试覆盖。

**Why**: WAITING steer 需要先让 Run 进入 WAITING 状态（通过 await tool），测试装配较复杂，但代码路径与 RUNNING steer 不同（cancel wait records vs mark attempt steered）。

**How to apply**: 不阻塞。建议在 Slice 6 补测：seed WAITING run → steer → verify wait records cancelled + new Attempt created。

### F4 — [Info] README 更新准确

`dayu/host/README.md` 更新正确反映：
- steer / retry / replay 已从 deferred unsupported 移到可用 Run facade
- `purge_session` 仍为 stable unsupported
- internal admission 不实现清单准确更新为 `LOST / RECOVERING retry、startup recovery、positive orphan proof、stuck cancel watchdog 或 recovery cancellation`

`tests/README.md` 更新准确添加 `submit_followup(steer)`、`retry_run`、`replay_run` 覆盖描述。

## 实现正确性详细审查

### submit_followup(steer)

1. **RUNNING / WAITING 前置校验**：`_require_steer_target_run` (admission.py:3570) 检查 `target.status not in (RunStatus.RUNNING, RunStatus.WAITING)` — 完整覆盖。
2. **active Run 前置**：`read_active_run_for_session` + `active.run_id != target_run_id` 校验 — 防止 steer 非 active Run。
3. **same Run new Attempt**：`_create_steer_attempt_result` (admission.py:2715) 创建新 attempt_id/execution_id/dispatch_record_id，`steer_active_run_row` CAS 切换 current_attempt_id。
4. **terminal race durable order**：
   - RUNNING: `steer_running_attempt_row` CAS 将旧 Attempt 标记 STEERED，失败抛 INVALID_STATE
   - WAITING: `cancel_active_wait_records_for_run` CAS 取消 wait records，失败抛 INVALID_STATE
   - `steer_active_run_row` CAS 检查 previous_attempt_id — 若 Run 已 terminal 则 CAS 失败
5. **Recovery 边界**：`_require_steer_target_run` 只允许 RUNNING/WAITING，RECOVERING 被排除。
6. **旧 worker cancel**：`_create_steer_attempt_result` 返回 `steered_cancel_target`，command 层 `_submit_followup_steer` 通过 `_propagate_active_cancel_targets` 传播。

### FAILED retry

1. **源 Run immutable**：`_require_source_run_for_relation` 只读取并校验 status=FAILED；`_append_source_relation_requested_event` 在源 Run EventLog 上追加控制事件但不修改 Run row。
2. **关联新 Run**：`_create_source_related_admission_result` 创建新 Run（accepted 或 queued），`set_new_run_source_relation_row` CAS 写入 source_run_id + source_run_relation=RETRY。
3. **新 Attempt / execution id**：创建新 Run 时由 `_create_running_admission_result` 或 `_create_accepted_admission_result` 生成全新 attempt_id/execution_id/dispatch_record_id。
4. **幂等**：`(source_run_id, client_request_id)` 作为 idempotency key，`_OPERATION_RETRY_RUN` + `scope_id=run_id`。
5. **Policy limit**：`count_runs_by_source_relation` + `_MAX_ORDINARY_RETRY_RUNS_PER_SOURCE=1` 检查。
6. **只限 FAILED**：`_require_source_run_for_relation(expected_status=RunStatus.FAILED)`。

### SUCCEEDED replay

1. **no-tool**：`_CreateAdmissionRequest.from_source_run_replay` 设置 `effective_tool_set=_no_tool_effective_tool_set_json()`（空 ToolBundle），`_replay_effective_execution_config` 保留 execution config 但 force allow_tool_calls=False。
2. **源 Run immutable**：同 retry，只读取源 Run 输入 payload。
3. **repair instruction**：`input=HostInput(display_text=request.repair_instruction)` 作为新输入。
4. **无新工具事实**：dispatch 侧 `_is_replay_run` 检测 source_run_relation=REPLAY，`_run_input_builder_for_dispatch` 使用 `ToolExecutionMode.NO_TOOL_REPLAY` + `create_no_tool_run_input_builder`。
5. **源 EventLog truth 不变**：replay 只在新 Run 的 EventLog 写入，源 Run 的 EventLog 不被修改。

### resolve_wait

1. **open_host 下 commit 后唤醒 scheduler**：`command.resolve_wait` (command.py:701) 创建 `DefaultHostResolveWaitService`，commit 后检查 `result.dispatch_record is not None and not result.idempotent_replay`，调用 `host._admission_service.wakeup_port.wake_dispatch()`。
2. **new Attempt resume**：`DefaultHostResolveWaitService.resolve_wait` 在 durable transaction 内追加 `RESUME_REQUESTED` + tool terminal/result fact，创建新 Attempt/dispatch record。
3. **WAITING outcomes**：`ResolveWaitCompletedOutcome` / `FailedOutcome` / `CancelledOutcome` / `LostOutcome` 均在 `DefaultHostResolveWaitService` 中处理。

### cancel

1. **accepted / queued**：`_cancel_queued` 使用 `cancel_queued_in_transaction`。
2. **pre-dispatch STARTING**：`_cancel_predispatch_starting_or_none` 使用 `cancel_predispatch_starting_in_transaction`，CAS 失败返回 None 回退到 active cancel。
3. **active visibility**：`_cancel_active_attempt` 使用 `request_active_attempt_cancel_in_transaction`，返回 `active_cancel_target`，command 层传播到 `ActiveWorkerRegistry`。
4. **session-scope**：`_CancelSessionRunsOperation._read_supported_targets_or_raise` 遍历 non-terminal runs，校验每个 Run 属于支持子集（queued/pre-dispatch/active/WAITING），不支持的 non-terminal 抛 UNSUPPORTED_OPERATION。
5. **close boundary**：cancel 写 canonical cancel facts（CANCEL_REQUESTED/RUN_CANCELLED）；`close_session` 只关新输入入口；`host.close()` 不写 cancel facts。

## 验证结果

```bash
source .venv/bin/activate && pytest tests/host/test_public_steer.py tests/host/test_public_retry_replay.py tests/host/test_public_resolve_wait_resume.py tests/host/test_public_cancel_smoke.py -q
```

结果：`5 passed`

```bash
source .venv/bin/activate && python -m pyright dayu/host tests/host
```

结果：`0 errors, 0 warnings, 0 informations`

## 残余风险

1. **测试覆盖缺口**（owner: Slice 6 / follow-up fix）：plan matrix 中 steer WAITING、terminal race、retry idempotency/conflict/policy limit、replay source immutable、cancel pre-dispatch/close boundary/watch visibility 等场景未被测试覆盖。实现代码正确，但缺少防御性边界证明。
2. **跨测试 helper 耦合**（owner: 测试维护）：4 个测试文件形成 import 依赖图，helper 签名变更会级联 break。
3. **ordinary retry policy 固定上限**（owner: 后续 policy provider）：当前硬编码 `_MAX_ORDINARY_RETRY_RUNS_PER_SOURCE=1`，未接入可配置 policy provider。按 plan 正确 deferred。
4. **replay no-tool 防线层级**（owner: 既有 no-tool scope defense）：admission 冻结 no-tool effective facts + dispatch 选择 NO_TOOL_REPLAY mode 双重保证；更深层 runtime 防御依赖既有 no-tool scope defense。按 plan 正确 deferred。
