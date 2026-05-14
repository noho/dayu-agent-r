# Gateflow Fix: Host P3-S3 Run / Attempt Transition Primitives

- **gate**: code review fix
- **work unit**: Host Phase 3 Session / Run / Attempt 状态机与 Admission
- **slice**: P3-S3 Run / Attempt Transition Primitives
- **fix owner**: AgentCodex
- **fix date**: 2026-05-14
- **source review artifacts**:
  - `docs/reviews/gateflow-code-review-host-p3-s3-run-attempt-transitions-mimo-20260514.md`
  - `docs/reviews/gateflow-code-review-host-p3-s3-run-attempt-transitions-controller-adjudication-20260514.md`
- **accepted finding ids**:
  - `P3S3-C-001`
- **artifact path**: `docs/reviews/gateflow-fix-host-p3-s3-run-attempt-transitions-20260514.md`

## Fix Summary

`P3S3-C-001` 的动机成立：EventLog 是 Host canonical fact truth，transition helper 不能在 append `RUN_STARTED` / terminal / cancel facts 后，把后续 state mutation 的 `CAS_LOST` / `NOT_FOUND` / `INVALID_STATE` 作为普通结果返回给调用方正常 commit。

本次修复采用抛 `HostDurableError` 的方案：

- skip / not_found / invalid_state 等可在 append 前判断的路径继续在 append 前返回结构化结果，不新增 EventLog。
- append canonical EventLog 后，任何后续 state mutation 非 `UPDATED` 都抛 `HostDurableError`，由 `HostTransactionRunner` rollback 整个 write transaction。
- 未引入 savepoint、admission、Engine、WorkerProxy、scheduler、lane 或 public facade。

## Changed Files

- `dayu/host/durable/run_transition.py`
  - 引入 append 后 mutation 必须 `UPDATED` 的内部断言 helper。
  - 覆盖 promotion、terminal closeout、queued cancel、pre-dispatch cancel 中 append 后的 Run / Attempt / dispatch mutation。
- `tests/host/test_run_attempt_transitions.py`
  - 改写 `test_promote_cas_loser_keeps_queued_state`：模拟 append 后 CAS loser，断言 helper 抛 `HostDurableError` 且 rollback 后不残留 queued Run 的 `RUN_STARTED`。
  - 新增 active Run skip 测试，断言 promotion skip 不追加 queued Run 的 `RUN_STARTED`，queued Run 保持 `QUEUED`。

## Per-Finding Status

### P3S3-C-001: fixed

修复后：

- `promote_queued_run_in_transaction` 在 active Run 存在或无 queued Run 时不会 append EventLog；若 append `RUN_STARTED` 后 promotion CAS 非 `UPDATED`，立即抛 `HostDurableError`。
- `terminal_closeout_in_transaction` 在 precondition 不满足时不会 append EventLog；若 append terminal events 后 Attempt 或 Run CAS 非 `UPDATED`，立即抛 `HostDurableError`。
- `cancel_queued_in_transaction` 在 Run 不存在或不是 `QUEUED` 时不会 append EventLog；若 append cancel events 后 Run CAS 非 `UPDATED`，立即抛 `HostDurableError`。
- `cancel_predispatch_starting_in_transaction` 在 Run / Attempt / dispatch precondition 不满足时不会 append EventLog；若 append cancel events 后 dispatch / Attempt / Run 任一 mutation 非 `UPDATED`，立即抛 `HostDurableError`。

## Validation

```bash
source .venv/bin/activate && pytest tests/host/test_run_attempt_transitions.py tests/host/test_session_lifecycle.py -q
```

Result: `18 passed in 0.40s`

```bash
source .venv/bin/activate && python -m pyright dayu/host tests/host
```

Result: `0 errors, 0 warnings, 0 informations`

```bash
git diff --check
```

Result: passed with no output.

## README Decision

未修改 README。检查结果：

- `dayu/host/README.md` 当前仍把 promotion / cancel 归在 durable foundation 未实现范围内；P3-S3 已新增低层 transition primitives 后，这段表述可能需要总控在 slice acceptance 前统一更新。
- `tests/README.md` 的 Host durable foundation 覆盖说明未列出 Run / Attempt transition primitive 测试；建议总控在文档同步 gate 中补充。

本次 fix scope 仅处理 `P3S3-C-001`，未擅自扩大到 README 文档重写。

## Residual Risks

- 低层 `state.py` CAS helper 仍保持结构化 mutation result，不追加 EventLog；孤立事实风险已在 `run_transition.py` helper 层阻断。
- 本次只用 monkeypatch 模拟 append 后 CAS loser；真实并发 race 仍依赖后续 admission / scheduler 接入后的更高层并发测试覆盖。
