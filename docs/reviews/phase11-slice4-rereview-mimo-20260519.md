# Phase 11 Slice 4 Re-Review - AgentMiMo - 2026-05-19

## Scope

- Work unit: Phase 11 Host Lifecycle / Recovery / Multi-process Hardening
- Slice: Slice 4 RECOVERING Cancel, Graceful Shutdown, And Public Contract Preservation
- Fix artifact: `docs/reviews/phase11-slice4-fix-codex-20260519.md`
- Controller adjudication: `docs/reviews/phase11-slice4-code-review-controller-adjudication-20260519.md`

## Fix Item Verification

### S4-F1: `cancel_session_runs` unsupported error message stale

- Fix claim: 更新 error message 加入 `RECOVERING`。
- Evidence: `dayu/host/admission.py:2058-2060` 错误信息已改为 `"cancel_session_runs supports only queued, pre-dispatch STARTING, active worker, WAITING, and RECOVERING Runs in the current Host cancel scope"`。
- Status: **RESOLVED**。public-facing diagnostic 已与当前 supported target contract 一致。

### S4-F2: `released_active_slot=True` intent needs local clarification

- Fix claim: 在 `_cancel_recovering` 的 `released_active_slot=True` 旁补充注释。
- Evidence: `dayu/host/admission.py:1755` 注释为 `# 这里释放的是 session active slot / queue promotion 资格，不是 active worker cancel。`，精准区分了 slot release 与 active worker cancel 语义。
- Status: **RESOLVED**。注释窄而准确，未改字段语义，降低后续维护误判风险。

### S4-F3: Add `cancel_run` RECOVERING idempotency focused test

- Fix claim: 新增 `test_cancel_run_recovering_replay_is_idempotent_per_run_id`。
- Evidence: `tests/host/test_public_cancel_session_runs.py:495-533`，测试覆盖：
  1. 同一 `(run_id, client_request_id)` 重放返回相同结果，不追加第二组 `CANCEL_REQUESTED` / `RUN_CANCELLED`。
  2. 同一 `client_request_id` 用于不同 `run_id`（peer run）时独立取消，证明幂等 scope 未从 `run_id` 漂移。
- Status: **RESOLVED**。幂等 scope 隔离已验证。

## New Blocker Check

### admission.py diff

- `_CancelRunOperation._cancel_recovering`（L1695-1757）：结构与 `_cancel_waiting` 对称，调用 `cancel_recovering_run_in_transaction`，记录幂等结果，返回 `CancelRunResult`。无 active worker 传播，无 Attempt terminal fact。正确。
- `_CancelSessionRunsOperation._cancel_recovering_target`（L2221-2252）：session-scope 版本，结构与 `_cancel_waiting_target` 对称。正确。
- `_session_cancel_target_for_run`（L4289-4307）：RECOVERING 分支返回 `recovering=True, active_worker=False` 的 target，dispatch 顺序正确（L2082 在 L2084 之前）。
- `_SupportedSessionCancelTarget` dataclass 新增 `recovering: bool` 字段，所有构造点均显式赋值。
- import 新增 `CancelRecoveringRunInput` 和 `cancel_recovering_run_in_transaction`，已确认 `run_transition.py` 中存在。

### test diff

- 旧测试 `test_cancel_session_runs_unsupported_non_terminal_has_no_partial_mutation` 已删除：该测试假设 RECOVERING 为 unsupported，与当前 contract 矛盾。正确删除。
- 新测试 `test_cancel_run_recovering_appends_no_attempt_terminal`（L458-492）：验证 RECOVERING cancel 不追加 `ATTEMPT_CANCELLED`，Attempt 状态保持 `STARTING`。正确。
- 新测试 `test_cancel_run_recovering_replay_is_idempotent_per_run_id`（L495-533）：S4-F3 的验证，见上。
- 新测试 `test_cancel_session_runs_includes_recovering_without_fail_closed`（L535-557）：验证 session-scope cancel 覆盖 RECOVERING 且不阻断同批 queued Run。正确。
- import 清理：移除未使用的 `pytest`、`FollowupBehavior`、`HostApiError`、`HostApiErrorCode`、`SubmitFollowupRequest`、`submit_followup`；新增 `AttemptStatus`、`CancelRunRequest`、`cancel_run`、`TABLE_EVENT_LOG`。无遗漏。

### 结构完整性

- `_cancel_recovering` 与 `_cancel_recovering_target` 两条路径均存在，分别服务 `cancel_run` 和 `cancel_session_runs`。
- 幂等 scope 正确：`cancel_run` 路径的 scope 含 `run_id`，session-scope 路径的 scope 含 `session_id`。
- 无新增 `hasattr`/`getattr`/`Any`/魔法数字。
- 无新增兼容性 re-export 或 wrapper。

### New Blocker Count: 0

## Validation Results

```
$ pytest tests/host/test_public_cancel_session_runs.py -q
8 passed in 0.25s

$ pytest tests/host/test_public_cancel_smoke.py tests/host/test_public_lifecycle_smoke.py tests/host/test_watch_session_events.py -q
12 passed in 0.55s

$ python -m pyright dayu/host tests/host
0 errors, 0 warnings, 0 informations

$ git diff --check
(no output)
```

## Conclusion

**PASS**

S4-F1 / S4-F2 / S4-F3 全部收口，fix 未引入新 blocker。验证命令全部通过。
