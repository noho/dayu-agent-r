# Gateflow Re-Review: Host P5-S4 B1 Fix

- **Review role**: AgentMiMo
- **Gate**: P5-S4 B1 blocking fix re-review
- **Fix artifact**: `docs/reviews/gateflow-fix-host-p5-s4-engine-event-ingest-20260515.md`
- **Original review**: `docs/reviews/gateflow-code-review-host-p5-s4-engine-event-ingest-mimo-20260515.md`
- **Date**: 2026-05-15

## B1 Fix Verification

**Finding**: DUPLICATE terminal result 未触发 `wake_queue_promotion`。

**Fix approach**: 提取共用 `_with_terminal_promotion_retry()` 方法，`terminal_closeout=True` 且 `status in (ACCEPTED, DUPLICATE)` 时统一触发 wakeup。

### Code trace

1. **`_with_terminal_promotion_retry()`** (line 798-820): 新增共用方法，检查 `terminal_closeout=True` AND `status in (ACCEPTED, DUPLICATE)` → 调用 `wake_queue_promotion(session_id)` → 返回 `promotion_triggered=True`。

2. **`ingest()`** (line 267-271): transaction 结束后调用 `_with_terminal_promotion_retry(result, session_id=candidate.envelope.session_id)`。覆盖 normal ingest 路径的 ACCEPTED 与 DUPLICATE。

3. **`_close_worker_lifecycle()`** (line 792-796): transaction 结束后调用 `_with_terminal_promotion_retry(result, session_id=envelope.session_id)`。覆盖 clean EOF / worker lost 路径的 ACCEPTED 与 DUPLICATE。

4. **`_duplicate_terminal_result()`** (line 273-295): 仍返回 `promotion_triggered=False`——正确，实际 promotion 由上层 wrapper 触发。

5. **`_close_terminal()`** / **`_close_active_cancel()`**: 仍返回 `promotion_triggered=False`——正确，同上。

**B1 verdict: FIXED.** Normal ingest 与 worker lifecycle closeout 两条路径在 `terminal_closeout=True` 且 `status=DUPLICATE` 时均触发 `wake_queue_promotion` 并返回 `promotion_triggered=True`。

## Regression Test Verification

| 测试 | 覆盖场景 | 文件:行 |
| --- | --- | --- |
| `test_duplicate_candidate_returns_existing_result` | duplicate `final_answer` 重放 → `promotion_triggered=True`，wakeup spy 记录两次同 session_id | test_engine_ingest_mapping.py:306-343 |
| `test_clean_eof_without_terminal_closes_failed` | duplicate clean EOF 重放 → `promotion_triggered=True`，wakeup spy 记录两次同 session_id | test_phase5_local_execution_integration.py:135-171 |

两个回归测试均验证：
- 首次调用 `status=ACCEPTED`, `promotion_triggered=True`
- 重复调用 `status=DUPLICATE`, `promotion_triggered=True`
- `wakeup.promoted_session_ids == [session_id, session_id]`

## New Blocking Issues

**无新增 blocking issue。**

Fix 仅新增一个 `_with_terminal_promotion_retry()` 方法并在两处调用点替换原有条件判断，未改变 transaction 内逻辑、未引入新的控制流分支、未改变 durable state mutation 语义。

## Validation Results

| 验证项 | 结果 |
| --- | --- |
| `pytest tests/host/test_engine_ingest_mapping.py tests/host/test_phase5_local_execution_integration.py -q` | **10 passed** (0.23s) |
| `pyright dayu/host tests/host` | **0 errors, 0 warnings, 0 informations** |
| `git diff --check` | **passed** |

## Summary

- **B1**: **Fixed** — `_with_terminal_promotion_retry()` 统一覆盖 ACCEPTED 与 DUPLICATE terminal closeout 的 promotion wakeup
- **New blockers**: 0
- **Regression coverage**: duplicate final_answer + duplicate clean EOF promotion retry 均已覆盖
- **Artifact**: `docs/reviews/gateflow-code-re-review-host-p5-s4-engine-event-ingest-mimo-20260515.md`
