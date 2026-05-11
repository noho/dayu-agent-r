# P8.5 Slice 5b Code Review

- **review gate name**: code review
- **reviewed target**: P8.5 Slice 5b — Attempt Lease / Recovery Adversarial Hardening
- **approved plan**: `docs/host/phase8.5-plan.md`
- **implementation artifact**: `docs/host/phase8.5-s5b-implementation-report.md`
- **diff scope**: current uncommitted changes after Slice 5a commit `2ae71e0`
- **artifact path**: `docs/host/phase8.5-s5b-code-review.md`

## Reviewer Conclusion

**pass-with-risks**

未发现阻断性 correctness finding。实现只对 `_renew_loop` late-success 分支做窄修复，并通过测试补强覆盖 storage error、terminal override、recovery CAS miss、owner-lost late event、generic tool call fencing、`fetch_more` expired/denied 普通 failed outcome 等 Slice 5b 目标。

保留一个非阻断 residual risk：`renew/terminal race` 的覆盖不是当前 slice 指定 pytest 集合中的单一端到端测试直接驱动 `_renew_loop` 收到 `AttemptLeaseDecision.TERMINAL`；现有证据来自 store 级 `renew` terminal 诊断、terminal close/override 原子测试，以及多进程 terminal race。该覆盖足以说明核心不变量成立，但若 controller 要求 Slice 5b 对每个 bullet 都由本 slice 新增/指定测试直接命中，可以补一个 targeted supervisor test。

## Findings

No blocking findings.

## Evidence Review

### `_renew_loop` late-success / storage error

- `_renew_loop` 在 `renew()` 返回 `ACQUIRED` 后、刷新 `session.owner_context` 前再次检查 `session.loss_reason`；若并发路径已经标记 owner-lost，直接返回，避免 late renew 覆盖第一 loss reason 或刷新 owner context。证据：`dayu/host/_attempt_supervisor.py:1072-1078`。
- storage exception 被 catch 为普通 `Exception`，记录 masked ERROR 后调用 `_mark_owner_lost(... STORAGE_ERROR ...)` 并返回，background task 不向外泄漏异常。证据：`dayu/host/_attempt_supervisor.py:1053-1071`。
- 测试 `test_renew_late_success_does_not_overwrite_owner_lost_reason` 明确断言 loss reason 保持 `STORAGE_ERROR`，且 `session.owner_context is first_owner_context`。证据：`tests/host/test_phase8_attempt_supervisor.py:962-1013`。
- 测试 `test_renew_storage_error_marks_owner_lost_with_storage_reason` 明确断言 `renew_task.done()` 且 `renew_task.exception() is None`。证据：`tests/host/test_phase8_attempt_supervisor.py:1018-1068`。

### Terminal override / terminal truth

- `test_terminal_override_does_not_overwrite_existing_terminal_truth` 先写入 `FINAL_ANSWER` 成功终态，再尝试用 Host `RUN_FAILED` + `terminal_state_override=LOST` 覆盖；断言抛 `ATTEMPT_TERMINAL`、attempt 仍为 `SUCCEEDED`、EventLog 只有原始 `FINAL_ANSWER`。证据：`tests/host/test_phase8_attempt_fencing.py:281-319`。

### Recovery CAS miss

- `test_recover_returns_noop_when_cas_misses` 在 scan 与 mark 之间替换 `owner_id`、`owner_token_hash` 与 `fencing_token`，随后断言 recovery 返回 `NOOP_TERMINAL/cas_failed_noop`，且新 owner 字段保持替换后的值。证据：`tests/host/test_phase8_attempt_recovery.py:363-429`。

### Owner-lost late event

- unit-level race 测试确认 owner-lost 先到时 `_next_engine_event_or_lose_owner` 抛 `_OwnerLostDuringEngineWait`，不会继续消费 pending engine stream。证据：`tests/host/test_phase8_attempt_supervisor.py:1187-1280`。
- 端到端 owner-lost Case A / Case B 仍覆盖 CAS hit 写 Host `RUN_FAILED` 与 CAS miss 不写 stale terminal 的核心路径，且检查 late engine event 不进入 EventLog。证据：`tests/host/test_phase8_attempt_supervisor.py:1454-1844`。

### Generic tool call fencing / `fetch_more` failed outcome

- generic durable tool call 在业务 executor 前调用 appender owner 校验；fencing 时 executor 调用数为 0，append 调用数为 0，EventLog 为空。证据：`tests/host/test_phase8_tool_runtime_fencing.py:304-328`。
- `fetch_more` wrong-scope 与 expired cursor 都返回普通 `ToolFailedOutcome`，并断言不追加专属 facts。证据：`tests/host/test_phase8_tool_runtime_fencing.py:405-470`。
- 现有普通 truncate / `fetch_more` 成功测试也断言不恢复 cursor/truncation/fetch_more special RunEvents。证据：`tests/host/test_phase8_tool_runtime_fencing.py:370-402`。

## Scope Boundary Check

- 未看到恢复 `TOOL_CURSOR_*`、`TOOL_RESULT_TRUNCATED`、`TOOL_FETCH_MORE_*` 等 special RunEvents 的 diff。
- 未看到 P9 lifecycle admission、production process supervisor、PR/commit/closeout 范围漂移。
- 本 review 未修改生产代码或测试代码；仅按 handoff 要求写入本 durable review artifact。

## Validation

- `source .venv/bin/activate && python -m pyright dayu/host/ tests/host/`
  - 结果：通过，`0 errors, 0 warnings, 0 informations`
- `source .venv/bin/activate && pytest tests/host/test_phase8_attempt_supervisor.py tests/host/test_phase8_attempt_fencing.py tests/host/test_phase8_attempt_recovery.py tests/host/test_phase8_tool_runtime_fencing.py -q`
  - 结果：通过，`55 passed in 0.51s`
- `source .venv/bin/activate && pytest tests/host/test_phase8_multiprocess_stress.py -q`
  - 结果：通过，`4 passed in 1.73s`

## Open Questions And Residual Risk

- **renew/terminal race targeted supervisor coverage**: 当前代码路径正确性有直接实现证据与 lower-level store 证据，但本 slice 指定 pytest 集合没有新增一个直接让 `_renew_loop` 在 terminal close 后收到 `TERMINAL/ATTEMPT_TERMINAL` 的 test。建议 controller 判断是否接受现有覆盖，或要求后续 fix pass 补一个很窄的 supervisor-level test。

## Controller Decision Status

- No blocking findings: `pending-controller-decision`
- Residual risk `renew/terminal race targeted supervisor coverage`: `pending-controller-decision`
