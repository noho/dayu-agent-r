# Gateflow Controller Adjudication: Host P3-S4 Admission And Queue Promotion Code Review

- **gate**: code review adjudication
- **work unit**: Host Phase 3 Session / Run / Attempt 状态机与 Admission
- **assigned slice**: P3-S4 Admission And Queue Promotion
- **review artifact**: `docs/reviews/gateflow-code-review-host-p3-s4-admission-queue-mimo-20260514.md`
- **controller**: Codex
- **artifact path**: `docs/reviews/gateflow-code-review-host-p3-s4-admission-queue-controller-adjudication-20260514.md`

## Controller Conclusion

MiMo review 对 P3-S4 的实现边界、幂等语义、policy 分支、promotion FIFO 与 wakeup non-goals 的审查有效；总控同意实现方向可接受。但总控新增一个低严重测试覆盖 finding：queued idempotency retry 的 no-extra-events 断言不够直接，必须补强后再进入 accepted slice commit。

## Finding Decisions

| Finding | Severity | Decision | Owner | Required Action |
|---------|----------|----------|-------|-----------------|
| P3S4-C-001 | low | accepted | AgentCodex | 补强 queued retry no-extra-events 断言。 |
| F001 / observation | info | deferred | P3-S5 owner | `wake_queue_promotion` 接入 terminal/cancel 后 promotion trigger 时处理。 |
| F002 / observation | info | accepted-as-non-issue | controller | `promote_next_queued_run` 不要求 Session OPEN，已有 queued Run 可在 Session closed 后继续被 promotion；无需修改。 |

## P3S4-C-001: queued idempotency retry no-extra-events assertion is indirect

### Direct Evidence

`tests/host/test_admission_queue.py` 的 `test_duplicate_idempotency_returns_same_run_without_extra_events` 当前流程为：

1. 创建 active Run。
2. 创建 queued follow-up Run。
3. 记录 `before_queued_retry = _event_count(...)`。
4. 执行 queued retry。
5. 继续创建另一个 Session，并执行 direct running follow-up path。
6. 最后断言 `_event_count(...) == before_direct_retry`，该断言只直接证明 direct retry 没有追加事件。

因此，queued retry 的 no-extra-events 没有在 retry 后立即断言。后续 direct path 会合法追加新的 EventLog rows，使测试无法直接证明 queued retry 无副作用。实现当前看起来正确，但测试证据不够硬。

### Required Fix

- 在 queued retry 后立即断言 `_event_count(...) == before_queued_retry`。
- 保留 direct path retry 的现有 no-extra-events 断言。
- 不修改生产代码，除非补测试暴露真实实现问题。
- 写 fix artifact：`docs/reviews/gateflow-fix-host-p3-s4-admission-queue-20260514.md`。

## Required Validation

- `source .venv/bin/activate && pytest tests/host/test_admission_queue.py tests/host/test_run_attempt_transitions.py -q`
- `source .venv/bin/activate && python -m pyright dayu/host tests/host`
- `git diff --check`

## README Decision

P3-S4 新增 Host admission service 与 admission tests，触发 `dayu/host/README.md` 与 `tests/README.md` 检查。当前 fix 先只处理 accepted code review finding；README 同步在 P3-S4 re-review 通过后由总控统一执行。
