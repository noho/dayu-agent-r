# Gateflow Fix: Host P3-S4 Admission And Queue Promotion

- **gate**: code review fix
- **work unit**: Host Phase 3 Session / Run / Attempt 状态机与 Admission
- **slice**: P3-S4 Admission And Queue Promotion
- **source review artifact**: `docs/reviews/gateflow-code-review-host-p3-s4-admission-queue-controller-adjudication-20260514.md`
- **accepted findings**: `P3S4-C-001`
- **fix agent**: AgentCodex
- **artifact path**: `docs/reviews/gateflow-fix-host-p3-s4-admission-queue-20260514.md`

## Motivation Check

P3S4-C-001 成立。`test_duplicate_idempotency_returns_same_run_without_extra_events` 原先只在 direct retry 后断言全局 EventLog 数量未变化，能够覆盖 direct retry，但 queued retry 后马上进入 direct path，后续 direct first admission 会合法追加事件。因此原断言不能直接证明 queued retry 没有 EventLog 副作用。

该 finding 只指向测试证据不足；当前未发现生产实现问题，因此未修改 `dayu/host/admission.py`。

## Fix Status

### P3S4-C-001-已修复-[低]-queued idempotency retry no-extra-events assertion is indirect

- **修复位置**: `tests/host/test_admission_queue.py`
- **修复内容**: 在 queued retry 完成后立即断言 `_event_count(store.transaction_runner) == before_queued_retry`。
- **保留行为**: direct retry 现有 no-extra-events 断言保持不变。
- **生产代码**: 未修改。

## Changed Files

- `tests/host/test_admission_queue.py`
- `docs/reviews/gateflow-fix-host-p3-s4-admission-queue-20260514.md`

## Validation

- `source .venv/bin/activate && pytest tests/host/test_admission_queue.py tests/host/test_run_attempt_transitions.py -q`
  - 结果：`20 passed in 0.20s`
- `source .venv/bin/activate && python -m pyright dayu/host tests/host`
  - 结果：`0 errors, 0 warnings, 0 informations`
- `git diff --check`
  - 结果：通过，无输出。

## README Decision

本次 fix 只增强既有测试断言，不改变测试分层、运行方式、维护约定、Host 公共契约或项目使用方式。已按触发规则检查 README 职责边界，当前无需修改 README。

## Residual Risk

无新增 residual risk。该修复只提升 queued idempotency retry 的测试证据直接性，不改变生产语义。
