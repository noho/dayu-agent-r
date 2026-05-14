# Gateflow Re-Review: Host P3-S4 Admission And Queue Promotion — P3S4-C-001 Fix

- **gate**: focused re-review
- **work unit**: Host Phase 3 Session / Run / Attempt 状态机与 Admission
- **slice**: P3-S4 Admission And Queue Promotion
- **reviewer**: AgentMiMo
- **re-review date**: 2026-05-14
- **source adjudication**: `docs/reviews/gateflow-code-review-host-p3-s4-admission-queue-controller-adjudication-20260514.md`
- **fix artifact**: `docs/reviews/gateflow-fix-host-p3-s4-admission-queue-20260514.md`
- **scope**: P3S4-C-001 only

## P3S4-C-001: queued idempotency retry no-extra-events assertion — FIXED

### Review Target

`tests/host/test_admission_queue.py` `test_duplicate_idempotency_returns_same_run_without_extra_events`（L297-356）

### Fix Verification

原 finding 指出：queued retry 后没有立即断言 no-extra-events，后续 direct path 会合法追加事件，导致测试无法直接证明 queued retry 无副作用。

修复后的断言结构：

| 步骤 | 行号 | 操作 | 断言 |
|------|------|------|------|
| 1 | 305-311 | 创建 active Run | — |
| 2 | 312-323 | 创建 queued follow-up Run | — |
| 3 | 324 | `before_queued_retry = _event_count(...)` | 记录基线 |
| 4 | 325-328 | 执行 queued retry（幂等重放） | — |
| **5** | **329** | — | **`assert _event_count(...) == before_queued_retry`** |
| 6 | 331-343 | 创建 direct session，执行 direct first admission | — |
| 7 | 344 | `before_direct_retry = _event_count(...)` | 记录基线 |
| 8 | 345-348 | 执行 direct retry（幂等重放） | — |
| 9 | 350-351 | — | queued idempotency 断言 |
| 10 | 352 | — | `assert _event_count(...) == before_direct_retry` |
| 11 | 353 | — | `assert before_direct_retry > before_queued_retry` |

### 判定

- **L329**: queued retry 后立即断言 no-extra-events — **满足 controller 要求**
- **L352**: direct retry 断言保留 — **满足 controller 要求**
- **L353**: 确认 direct first admission 合法追加了事件，证明 L329 和 L352 断言基线不同 — **增强测试证据链**
- 生产代码 `dayu/host/admission.py` — **未修改**，符合 controller 指令

### 结论

**P3S4-C-001: FIXED**

修复正确且最小化。queued idempotency retry 的 no-extra-events 断言现在是直接证据（retry 后立即断言），不再是间接推断。direct retry 断言完整保留。无新 findings。

## Validation Results

```
source .venv/bin/activate && pytest tests/host/test_admission_queue.py tests/host/test_run_attempt_transitions.py -q
-> 20 passed in 0.18s

source .venv/bin/activate && python -m pyright dayu/host tests/host
-> 0 errors, 0 warnings, 0 informations

git diff --check
-> (clean)
```

## Residual Risk

无。该修复只增强既有测试断言的直接性，不改变生产语义，不引入新依赖或新路径。
