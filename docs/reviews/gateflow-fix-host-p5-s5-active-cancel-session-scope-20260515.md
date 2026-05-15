# Gateflow Fix: Host P5-S5 Active Cancel And Session-scope Cancel

- Fix Agent: AgentCodex
- Date: 2026-05-15
- Source Reviews:
  - `docs/reviews/gateflow-code-review-host-p5-s5-active-cancel-session-scope-mimo-20260515.md`
  - `docs/reviews/gateflow-code-review-host-p5-s5-active-cancel-session-scope-ds-20260515.md`
- Scope: P5-S5 review fix only

## Accepted Findings

1. DS Finding 1: `tests/host/test_public_cancel_session_runs.py` 用裸 SQL 只改 `host_attempts.status` 伪造 active worker，绕过 `ATTEMPT_RUNNING` fact 与 dispatch worker accepted 状态联动。
2. MiMo Finding F2 / DS Finding 6.1 follow-up: `HostDispatchScheduler._consume_worker_events` 创建 `EngineEventIngestor` 时使用默认 noop wakeup port，worker terminal closeout 后不能由 scheduler 自身触发 queued Run promotion 与 promoted dispatch wakeup。
3. 文本修复：`admission.py` 中 `cancel_session_runs` unsupported error message 仍写 Phase 4。

## Fix Summary

- `dayu/host/dispatch.py`
  - 让 `HostDispatchScheduler` 实现 `wake_queue_promotion(session_id)`。
  - `wake_queue_promotion` 内创建 admission service，并以 scheduler 自身作为 wakeup port 调用 `promote_next_queued_run(session_id)`；promotion 成功后 admission 会回调 `scheduler.wake_dispatch(...)` 唤醒 promoted pending dispatch。
  - `_consume_worker_events` 创建 `EngineEventIngestor` 时显式传入 `wakeup_port=self`，不再落到 `NoopAdmissionWakeupPort`。

- `tests/host/test_active_cancel_dispatch.py`
  - 新增 `test_worker_terminal_promotes_and_dispatches_queued_run`，覆盖 active worker `final_answer` terminal 后 queued Run 被 promotion，并由同一 scheduler 处理 promoted dispatch。
  - 测试断言两个 worker dispatch 均发生，并产生两个 `ATTEMPT_RUNNING` fact，证明路径不是 noop wakeup。

- `tests/host/test_public_cancel_session_runs.py`
  - 删除 active worker 测试里的裸 SQL `host_attempts.status = running` helper。
  - 新增 `_accept_active_worker(...)`，在 durable write transaction 内注册 host instance，推进 dispatch `pending -> waiting_for_lane -> dispatching`，再调用 `accept_worker_running_in_transaction(...)` 追加 `ATTEMPT_RUNNING` 并记录 dispatch worker accepted refs。
  - `WAITING` deferred 分类测试仍直接改 Run status，并已加中文注释说明该直改只用于 deferred state classification，不作为生产 transition。

- `dayu/host/admission.py`
  - 将 `cancel_session_runs` 文本与 unsupported error message 从 Phase 4 子集改为当前 Host cancel scope 表述。
  - 更新 wakeup port docstring，明确端口是 commit 后轻量唤醒边界。

- `dayu/host/command.py`、`dayu/host/README.md`、`tests/README.md`
  - 同步当前 active worker cancel 与 scheduler terminal promotion 行为说明，清理与本次代码不一致的 Phase 4 cancel 描述。

## Validation

已运行并通过：

```bash
source .venv/bin/activate && pytest tests/host/test_active_cancel_dispatch.py tests/host/test_public_cancel_session_runs.py tests/host/test_public_run_api.py -q
```

结果：`22 passed in 0.37s`

```bash
source .venv/bin/activate && python -m pyright dayu/host tests/host
```

结果：`0 errors, 0 warnings, 0 informations`

```bash
git diff --check
```

结果：通过，无 whitespace error。

## Residual Risks

- 按 controller 裁决，本轮未修复 MiMo F1 / DS Finding 2 的多 active target session cancel replay 限制；当前同 Session 单 active invariant 下不作为 blocking，后续如扩展多 active 语义应重新设计 replay target truth。
- Active cancel watchdog 仍属于后续 phase 风险：worker 收到 cancel 后若长期不产出 terminal，Run 仍可能停留在 `CANCELLING`。
- 本轮未扩大 schema，也未引入兼容性迁移。
