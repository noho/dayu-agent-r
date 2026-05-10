# PR #40 N1 Follow-up Fix Re-review

## Scope

- Mode: PR #40 N1 follow-up fix re-review
- Base artifacts:
  - `docs/reviews/pr-40-review-20260510-1808.md`
  - `docs/reviews/pr-40-review-20260510-1808-fix-rereview.md`
- Focus files:
  - `dayu/host/_run_harness.py`
  - `tests/host/test_phase4_overflow_retry.py`
  - `docs/reviews/pr-40-review-20260510-1808-fix-rereview.md`
- Non-goals: 不复审 `docs/host/migration-plan.md` 流程精简改动; 不扩大到 PR #40 全量 diff; 不修改代码、不 commit、不 push。
- Parallel review coverage: 无。

## Conclusion

**PASSED**

N1 follow-up fix 成立。当前 N1 不再是 unresolved blocker。PR #40 原 F4 仍保持 `deferred-with-owner: P9 / capacity`，不属于本次 N1 行为修复范围。

## Findings

未发现实质性问题。

## N1 Verdict

N1 已 fixed。

直接证据:

- `dayu/host/_run_harness.py:1076-1096` 在 context overflow retry 的 new attempt acquire failure 分支中，将 `_append_overflow_acquire_failure_terminal(...)` 外包 `try/except AttemptFencingError`。
- `dayu/host/_run_harness.py:1087-1094` 捕获旧 attempt terminal close 的 `AttemptFencingError` 后，路由到 `_handle_owner_lost(..., loss_reason=AttemptOwnerLossReason.FENCED, ...)`。
- `dayu/host/_run_harness.py:1251-1345` 的 `_handle_owner_lost` 通过 `AttemptSupervisor.append_terminal_and_close` 再尝试 owner-scoped terminal close；CAS miss 时捕获 `AttemptFencingError`，记录 typed warning，不写 stale RunEvent，并安全返回 `False`。
- `dayu/host/_run_harness.py:1561-1624` 的 `_append_overflow_acquire_failure_terminal` 保持 CAS hit 语义：新 attempt acquire 失败但旧 owner 仍有效时，仍写 `RUN_FAILED(error_code=context_overflow_retry_acquire_failed)` 并经 owner-scoped terminal close 收口。
- `rg "event_store\.append\(host_failure_draft|fetch_more_tool_result|get_tool_fetch_more_handle|_default_harness_for_running_loop|_build_default_harness" dayu/host` 无命中，未恢复裸 `event_store.append(host_failure_draft(...))`、legacy fetch_more 或 default harness builder。
- `RunStream` public dataclass 字段未被修改，本次未新增 public close API。

## N1 Test Coverage

新增测试 `tests/host/test_phase4_overflow_retry.py::test_durable_overflow_acquire_failure_terminal_fencing_routes_owner_lost` 覆盖了 N1 关键窗口:

- `tests/host/test_phase4_overflow_retry.py:1240-1276` monkeypatch `AttemptSupervisor.lease_context`，第一次 acquire 成功，第二次 acquire 抛 `AttemptFencingError`，对应 context overflow compact 后 new attempt acquire 失败。
- `tests/host/test_phase4_overflow_retry.py:1280-1308` monkeypatch `AttemptSupervisor.append_terminal_and_close` 总是抛 `AttemptFencingError`，对应旧 attempt terminal close CAS miss。
- `tests/host/test_phase4_overflow_retry.py:1348-1351` 用 `asyncio.wait_for(..., timeout=5.0)` 收集 `RunStream`，证明 CAS miss 无 terminal RunEvent 时 stream 不 hang。
- `tests/host/test_phase4_overflow_retry.py:1353-1357` 断言 `append_terminal_and_close` 被调用两次：第一次来自 acquire-failure terminal close，第二次来自 `_handle_owner_lost` 的再收口尝试。
- `tests/host/test_phase4_overflow_retry.py:1358-1365` 断言没有通过 `DurableRunEventStore.append` 裸写 terminal，也没有 stale Host `RUN_FAILED` terminal RunEvent。
- `tests/host/test_phase4_overflow_retry.py:1366-1369` 断言没有 `host.run.background_task_failed`，即 background task 未以 uncaught `AttemptFencingError` 失败。

测试对 compact 成功的证明主要来自真实 overflow retry 路径与第二次 acquire 的到达条件；该路径在同文件既有 F5 回归测试中也直接断言了 `HostContextCompactCompletedData`。

## Artifact State

`docs/reviews/pr-40-review-20260510-1808-fix-rereview.md` 同时保留了两段历史事实:

- line 76-91: 历史 re-review 发现 `N1-未修复`，并给出 `CONDITIONALLY PASSED`。
- line 93-120: controller 接受 N1 后的修复状态、回归测试和验证结果。

如果只阅读该旧 artifact 的上半段，确实可能造成当前 gate 状态误读。本 artifact 是 N1 follow-up fix 的最新复审记录，应覆盖旧 artifact 中 `N1-未修复 / CONDITIONALLY PASSED` 的历史段落。旧 artifact 可作为审计历史保留，不需要为本次复审清理；controller / gate tracker 应引用本 artifact 作为 N1 当前状态真源。

## F4 Status

F4 仍保持 `deferred-with-owner: P9 / capacity`。本次 N1 fix 未触碰 durable memory repair scan 容量问题；该项不是当前 N1 gate blocker。

## Verification

| Command | Result |
| --- | --- |
| `source .venv/bin/activate && pytest tests/host/test_phase4_overflow_retry.py::test_durable_overflow_acquire_failure_terminal_fencing_routes_owner_lost -q` | 1 passed |
| `source .venv/bin/activate && pytest tests/host/test_phase4_overflow_retry.py -q` | 17 passed |
| `source .venv/bin/activate && pytest tests/host -q` | 323 passed |
| `source .venv/bin/activate && python -m pyright dayu/host tests/host utils` | 0 errors, 0 warnings |
| `source .venv/bin/activate && python utils/smoke_host_p8_attempt_lease.py` | s1-s7 passed |
| `git diff --check` | clean |
| `rg "event_store\.append\(host_failure_draft\|fetch_more_tool_result\|get_tool_fetch_more_handle\|_default_harness_for_running_loop\|_build_default_harness" dayu/host` | no matches |
| `rg "MARK_RECOVERING_AND_CREATE_ATTEMPT\|mark_recovering_and_create_attempt\|recovery_attempt_id\|recovery_attempt_index" dayu tests utils` | no matches |

## Required Answers

1. N1 是否 fixed: 是。
2. 是否还有未解决 blocker: 本次 N1 follow-up 范围内无未解决 blocker。
3. F4 是否仍保持 deferred-with-owner: P9 / capacity: 是。
4. 旧 artifact 是否会造成当前 gate 状态误读: 会，若只读 `N1-未修复 / CONDITIONALLY PASSED` 历史段落会误读；本 artifact 足以覆盖旧状态，不需要清理旧 artifact。

## Residual Risk

- 未运行全量 `pytest -q`；本次按 N1 窄范围复审运行了目标测试、`tests/host`、pyright、smoke 和禁止模式扫描。
- `docs/host/migration-plan.md` 属 unrelated 流程精简改动，本次未纳入代码行为复审。
